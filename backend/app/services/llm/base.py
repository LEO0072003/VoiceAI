"""
Base LLM Provider Interface
Defines the contract for all LLM providers using Protocol pattern
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Dict, List, Optional, Any


class MessageRole(str, Enum):
    """Role of the message sender"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    """Represents a tool/function call from the LLM"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMMessage:
    """Represents a message in the conversation"""
    role: MessageRole
    content: str
    name: Optional[str] = None  # For tool messages
    tool_call_id: Optional[str] = None  # For tool responses
    tool_calls: List['ToolCall'] = field(default_factory=list)  # For assistant messages with tool calls
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls"""
        result = {
            "role": self.role.value,
            "content": self.content
        }
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in self.tool_calls
            ]
        return result


@dataclass 
class LLMResponse:
    """Response from LLM provider"""
    content: str
    finish_reason: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Optional[Dict[str, int]] = None  # tokens used
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    Implements Strategy pattern for swappable LLM backends.
    """
    
    def __init__(self, model: Optional[str] = None, **kwargs):
        self.model = model
        self.config = kwargs
        self._initialized = False
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the provider (e.g., 'openai', 'gemini', 'mock')"""
        pass
    
    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the default model for this provider"""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the provider (API client setup, auth, etc.)
        Called once before first use.
        """
        pass
    
    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a response from the LLM.
        
        Args:
            messages: Conversation history
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            tools: List of tool/function definitions
            **kwargs: Provider-specific options
            
        Returns:
            LLMResponse with generated content
        """
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream response tokens from the LLM.
        
        Yields:
            String chunks as they arrive
        """
        pass
    
    async def generate_simple(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Simple generation with just a prompt.
        Convenience method that wraps generate().
        """
        messages = []
        if system_prompt:
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system_prompt))
        messages.append(LLMMessage(role=MessageRole.USER, content=prompt))
        
        response = await self.generate(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.content
    
    async def __aenter__(self):
        """Async context manager entry"""
        if not self._initialized:
            await self.initialize()
            self._initialized = True
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        pass


class ConversationContext:
    """
    Manages conversation state and history for LLM interactions.
    """
    
    def __init__(
        self,
        session_id: str,
        system_prompt: Optional[str] = None,
        max_history: int = 20
    ):
        self.session_id = session_id
        self.system_prompt = system_prompt
        self.max_history = max_history
        self._messages: List[LLMMessage] = []
        self._metadata: Dict[str, Any] = {}
        
        if system_prompt:
            self._messages.append(
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)
            )
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to history"""
        self._messages.append(LLMMessage(role=MessageRole.USER, content=content))
        self._trim_history()
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant response to history"""
        self._messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=content))
        self._trim_history()
    
    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        """Add a tool result to history"""
        self._messages.append(
            LLMMessage(
                role=MessageRole.TOOL,
                content=result,
                name=name,
                tool_call_id=tool_call_id
            )
        )
    
    def get_messages(self) -> List[LLMMessage]:
        """Get all messages for API call"""
        return self._messages.copy()
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Store session metadata"""
        self._metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Retrieve session metadata"""
        return self._metadata.get(key, default)
    
    def clear_history(self, keep_system: bool = True) -> None:
        """Clear conversation history"""
        if keep_system and self.system_prompt:
            self._messages = [
                LLMMessage(role=MessageRole.SYSTEM, content=self.system_prompt)
            ]
        else:
            self._messages = []
    
    def _trim_history(self) -> None:
        """Trim history to max_history, keeping system message"""
        if len(self._messages) <= self.max_history:
            return
            
        # Keep system message if present
        has_system = (
            self._messages and 
            self._messages[0].role == MessageRole.SYSTEM
        )
        
        if has_system:
            # Keep system + last (max_history - 1) messages
            self._messages = [self._messages[0]] + self._messages[-(self.max_history - 1):]
        else:
            self._messages = self._messages[-self.max_history:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the conversation"""
        return {
            "session_id": self.session_id,
            "message_count": len(self._messages),
            "has_system_prompt": self.system_prompt is not None,
            "metadata": self._metadata
        }
