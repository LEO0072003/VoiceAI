import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from app.core.redis_client import redis_client


class RedisSessionManager:
    """Redis-backed session manager ensuring isolation per session_id."""

    namespace = "voice:sessions"
    conversation_namespace = "voice:conversations"
    ttl_seconds = int(timedelta(hours=2).total_seconds())

    @classmethod
    def _key(cls, session_id: str) -> str:
        return f"{cls.namespace}:{session_id}"
    
    @classmethod
    def _conversation_key(cls, session_id: str) -> str:
        return f"{cls.conversation_namespace}:{session_id}"

    def create_session(self) -> Dict:
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        key = self._key(sid)
        now = datetime.utcnow().isoformat()
        start_time = datetime.utcnow().timestamp()

        redis_client.hset(key, mapping={
            "session_id": sid,
            "status": "initiated",
            "created_at": now,
            "start_time": str(start_time),
            "user_contact": "",
            "ws_active": "0"
        })
        redis_client.expire(key, self.ttl_seconds)

        return {"session_id": sid, "created_at": now, "status": "initiated"}

    def get(self, session_id: str) -> Optional[Dict]:
        key = self._key(session_id)
        data = redis_client.hgetall(key)
        return data or None

    def set_user(self, session_id: str, contact_number: str) -> None:
        key = self._key(session_id)
        if redis_client.exists(key):
            redis_client.hset(key, "user_contact", contact_number)

    def set_status(self, session_id: str, status: str) -> None:
        key = self._key(session_id)
        if redis_client.exists(key):
            redis_client.hset(key, "status", status)

    def set_ws_active(self, session_id: str, active: bool) -> None:
        key = self._key(session_id)
        if redis_client.exists(key):
            redis_client.hset(key, "ws_active", "1" if active else "0")

    def get_start_time(self, session_id: str) -> float:
        """Get session start time as Unix timestamp"""
        key = self._key(session_id)
        start_time = redis_client.hget(key, "start_time")
        if start_time:
            return float(start_time)
        return datetime.utcnow().timestamp()

    # --- Conversation History Management ---
    
    def init_conversation(self, session_id: str, system_prompt: str) -> None:
        """Initialize conversation with system prompt"""
        key = self._conversation_key(session_id)
        initial_message = {
            "role": "system",
            "content": system_prompt
        }
        redis_client.delete(key)  # Clear any existing
        redis_client.rpush(key, json.dumps(initial_message))
        redis_client.expire(key, self.ttl_seconds)
    
    def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str,
        tool_calls: Optional[List[Dict]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None
    ) -> None:
        """
        Add a message to conversation history.
        
        Args:
            session_id: Session identifier
            role: Message role (system, user, assistant, tool)
            content: Message content
            tool_calls: For assistant messages with tool calls
            tool_call_id: For tool response messages
            name: Tool name for tool response messages
        """
        key = self._conversation_key(session_id)
        message = {
            "role": role,
            "content": content
        }
        
        # Add tool_calls for assistant messages that include tool calls
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        # Add tool-specific fields for tool response messages
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        if name:
            message["name"] = name
            
        redis_client.rpush(key, json.dumps(message))
        
        # Trim to max 100 messages to prevent unbounded growth
        redis_client.ltrim(key, -100, -1)
    
    def get_conversation(self, session_id: str) -> List[Dict[str, str]]:
        """Get full conversation history"""
        key = self._conversation_key(session_id)
        messages = redis_client.lrange(key, 0, -1)
        return [json.loads(msg) for msg in messages] if messages else []
    
    def get_user_turn_count(self, session_id: str) -> int:
        """Count user messages in conversation"""
        messages = self.get_conversation(session_id)
        return len([m for m in messages if m.get("role") == "user"])
    
    def clear_conversation(self, session_id: str) -> None:
        """Clear conversation history"""
        key = self._conversation_key(session_id)
        redis_client.delete(key)

    def remove(self, session_id: str) -> None:
        """Remove session and associated data"""
        key = self._key(session_id)
        conv_key = self._conversation_key(session_id)
        redis_client.delete(key)
        redis_client.delete(conv_key)

    # --- Metadata Storage ---
    
    def set_metadata(self, session_id: str, field: str, value: Any) -> None:
        """Store arbitrary metadata for session"""
        key = self._key(session_id)
        if redis_client.exists(key):
            redis_client.hset(key, f"meta:{field}", json.dumps(value))
    
    def get_metadata(self, session_id: str, field: str, default: Any = None) -> Any:
        """Retrieve metadata for session"""
        key = self._key(session_id)
        value = redis_client.hget(key, f"meta:{field}")
        if value:
            return json.loads(value)
        return default


# Singleton instance - but state is in Redis, not in memory
session_manager = RedisSessionManager()
