"""
Tavus CVI (Conversational Video Interface) Service
Manages personas and conversations for AI video avatar
"""
import httpx
from typing import Dict, Any, Optional, List
import logging
from app.core.config import settings
from app.services.tools.definitions import VOICE_AGENT_SYSTEM_PROMPT, TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

TAVUS_API_BASE = "https://tavusapi.com/v2"

# Stock replica IDs available in Tavus free tier
STOCK_REPLICAS = {
    "nathan": "rfe12d8b9597",      # Male, professional
    "charlie": "r79e1c033f",       # Male, friendly  
    "mary": "r3b7f9a2d4e",         # Female, professional
    "sabrina": "r8c2d5e7f1a",      # Female, warm
}

DEFAULT_REPLICA_ID = "rfe12d8b9597"  # Nathan


def get_tavus_headers() -> Dict[str, str]:
    """Get headers for Tavus API requests"""
    return {
        "Content-Type": "application/json",
        "x-api-key": settings.TAVUS_API_KEY
    }


def convert_tools_to_tavus_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI-style tools to Tavus format"""
    tavus_tools = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            tavus_tools.append({
                "type": "function",
                "function": {
                    "name": func["name"],
                    "description": func["description"],
                    "parameters": func["parameters"]
                }
            })
    return tavus_tools


async def create_persona(
    name: str = "Appointment Assistant",
    replica_id: str = DEFAULT_REPLICA_ID,
    custom_greeting: Optional[str] = None,
    tool_webhook_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a Tavus persona for the voice agent
    
    Args:
        name: Name of the persona
        replica_id: Tavus replica ID to use
        custom_greeting: Custom greeting message
        tool_webhook_url: Webhook URL for tool execution
        
    Returns:
        Persona creation response with persona_id
    """
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    # Build the persona configuration - simple, no tools (Tavus handles internally)
    persona_config = {
        "persona_name": name,
        "system_prompt": VOICE_AGENT_SYSTEM_PROMPT,
        "context": """You are an AI appointment booking assistant. 
        Help users book, view, modify, and cancel appointments.
        Be friendly, professional, and concise in your responses.
        The user is already authenticated - do NOT ask for phone number or identification.""",
        "default_replica_id": replica_id,
        "pipeline_mode": "full",
        "layers": {
            "stt": {
                "smart_turn_detection": True
            },
            "llm": {
                "model": "tavus-gpt-4o-mini",
                "speculative_inference": True
            }
        }
    }
    
    # Log for debugging
    logger.info(f"Creating persona with config (no tools)")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TAVUS_API_BASE}/personas",
            headers=get_tavus_headers(),
            json=persona_config,
            timeout=30.0
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to create persona: {response.status_code} - {response.text}")
            raise Exception(f"Tavus API error: {response.text}")
        
        result = response.json()
        logger.info(f"Created Tavus persona: {result.get('persona_id')}")
        return result


async def create_persona_with_external_llm(
    name: str = "Appointment Assistant",
    replica_id: str = DEFAULT_REPLICA_ID,
    llm_base_url: str = None,
    llm_api_key: str = "not-needed-for-proxy"
) -> Dict[str, Any]:
    """
    Create a Tavus persona using external LLM endpoint (our proxy).
    
    This allows using our own LLM + tool execution while Tavus handles avatar rendering.
    Tavus will call our /api/llm/v1/chat/completions endpoint.
    """
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    # Use our LLM proxy endpoint
    if not llm_base_url:
        if not settings.BACKEND_PUBLIC_URL:
            raise ValueError("BACKEND_PUBLIC_URL required for external LLM mode")
        llm_base_url = f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/api/llm"
    
    logger.info(f"Creating persona with external LLM: {llm_base_url}")
    
    persona_config = {
        "persona_name": name,
        "system_prompt": VOICE_AGENT_SYSTEM_PROMPT,
        "context": """You are an AI appointment booking assistant. 
        Help users book, view, modify, and cancel appointments.
        Be friendly, professional, and concise in your responses.
        The user is already authenticated - do NOT ask for phone number or identification.""",
        "default_replica_id": replica_id,
        "pipeline_mode": "full",
        "layers": {
            "llm": {
                "model": "custom",
                "base_url": llm_base_url,
                "api_key": llm_api_key
            }
        }
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{TAVUS_API_BASE}/personas",
            headers=get_tavus_headers(),
            json=persona_config
        )
        
        if response.status_code not in (200, 201):
            logger.error(f"Failed to create persona with external LLM: {response.status_code} - {response.text}")
            raise Exception(f"Tavus API error: {response.text}")
        
        result = response.json()
        logger.info(f"Created Tavus persona with external LLM: {result.get('persona_id')}")
        return result


async def list_personas() -> List[Dict[str, Any]]:
    """List all personas"""
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{TAVUS_API_BASE}/personas",
            headers=get_tavus_headers(),
            timeout=30.0
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to list personas: {response.status_code}")
            raise Exception(f"Tavus API error: {response.text}")
        
        return response.json()


async def get_persona(persona_id: str) -> Dict[str, Any]:
    """Get persona by ID"""
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{TAVUS_API_BASE}/personas/{persona_id}",
            headers=get_tavus_headers(),
            timeout=30.0
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get persona: {response.status_code}")
            raise Exception(f"Tavus API error: {response.text}")
        
        return response.json()


async def delete_persona(persona_id: str) -> bool:
    """Delete a persona"""
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{TAVUS_API_BASE}/personas/{persona_id}",
            headers=get_tavus_headers(),
            timeout=30.0
        )
        
        return response.status_code == 200


async def create_conversation(
    persona_id: str,
    conversation_name: str = "Appointment Call",
    custom_greeting: Optional[str] = None,
    conversation_context: Optional[Dict[str, Any]] = None,
    max_call_duration: int = 600,  # 10 minutes max
    participant_left_timeout: int = 60,
    callback_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new conversation session
    
    Args:
        persona_id: The persona ID to use
        conversation_name: Name for the conversation
        custom_greeting: Override persona's default greeting
        conversation_context: Additional context dict for this conversation (user_id, user_name, etc.)
        max_call_duration: Max duration in seconds (default 10 min)
        participant_left_timeout: Timeout after participant leaves
        callback_url: Webhook URL for conversation events
        
    Returns:
        Conversation details including conversation_url for joining
    """
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    conversation_config = {
        "persona_id": persona_id,
        "conversation_name": conversation_name,
        "properties": {
            "max_call_duration": max_call_duration,
            "participant_left_timeout": participant_left_timeout
        }
    }
    
    if custom_greeting:
        conversation_config["custom_greeting"] = custom_greeting
    
    # Build conversational context string from dict
    if conversation_context:
        context_parts = []
        if conversation_context.get("user_name"):
            context_parts.append(f"The user's name is {conversation_context['user_name']}.")
        if conversation_context.get("user_id"):
            context_parts.append(f"User ID: {conversation_context['user_id']}.")
        if conversation_context.get("user_phone"):
            context_parts.append(f"User's phone: {conversation_context['user_phone']}.")
        context_parts.append("The user is already authenticated - do NOT ask for phone number or identification.")
        context_parts.append("You can directly help with their appointment requests.")
        
        conversation_config["conversational_context"] = " ".join(context_parts)
    
    if callback_url:
        conversation_config["callback_url"] = callback_url
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TAVUS_API_BASE}/conversations",
            headers=get_tavus_headers(),
            json=conversation_config,
            timeout=30.0
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to create conversation: {response.status_code} - {response.text}")
            raise Exception(f"Tavus API error: {response.text}")
        
        result = response.json()
        logger.info(f"Created conversation: {result.get('conversation_id')} - URL: {result.get('conversation_url')}")
        return result


async def get_conversation(conversation_id: str) -> Dict[str, Any]:
    """Get conversation details"""
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{TAVUS_API_BASE}/conversations/{conversation_id}",
            headers=get_tavus_headers(),
            timeout=30.0
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get conversation: {response.status_code}")
            raise Exception(f"Tavus API error: {response.text}")
        
        return response.json()


async def end_conversation(conversation_id: str) -> bool:
    """End an active conversation"""
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TAVUS_API_BASE}/conversations/{conversation_id}/end",
            headers=get_tavus_headers(),
            timeout=30.0
        )
        
        return response.status_code == 200


async def list_stock_replicas() -> List[Dict[str, Any]]:
    """List available stock replicas"""
    if not settings.TAVUS_API_KEY:
        raise ValueError("TAVUS_API_KEY is not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{TAVUS_API_BASE}/replicas",
            headers=get_tavus_headers(),
            params={"type": "stock"},
            timeout=30.0
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to list replicas: {response.status_code}")
            raise Exception(f"Tavus API error: {response.text}")
        
        return response.json()


# Singleton persona manager
class TavusPersonaManager:
    """Manages a single persona for the application"""
    
    _persona_id: Optional[str] = None
    
    @classmethod
    async def get_or_create_persona(cls, use_external_llm: bool = True) -> str:
        """
        Get existing persona or create new one.
        
        If BACKEND_PUBLIC_URL is configured and use_external_llm=True,
        creates persona with external LLM mode for full tool control.
        """
        logger.info(f"[PERSONA] get_or_create_persona called. use_external_llm={use_external_llm}, BACKEND_PUBLIC_URL={settings.BACKEND_PUBLIC_URL}")
        
        # Always create a fresh persona to ensure correct config
        if cls._persona_id:
            try:
                await delete_persona(cls._persona_id)
            except:
                pass
            cls._persona_id = None
        
        # Use external LLM mode if backend URL is configured
        if use_external_llm and settings.BACKEND_PUBLIC_URL:
            logger.info(f"Creating persona with external LLM (our proxy)")
            result = await create_persona_with_external_llm(
                name="Appointment Assistant"
            )
        else:
            # Fallback to simple Tavus-managed persona
            logger.info(f"Creating simple Tavus-managed persona (no tool execution). Reason: use_external_llm={use_external_llm}, BACKEND_PUBLIC_URL={settings.BACKEND_PUBLIC_URL}")
            result = await create_persona(
                name="Appointment Assistant",
                custom_greeting="Hello! I'm your appointment assistant. How can I help you today?"
            )
        
        cls._persona_id = result.get("persona_id")
        logger.info(f"Created persona: {cls._persona_id}")
        return cls._persona_id
    
    @classmethod
    def reset(cls):
        """Reset the cached persona"""
        cls._persona_id = None


# Export default manager
persona_manager = TavusPersonaManager()
