"""
Groq LLM Provider
Ultra-fast inference with Llama models and function calling support
"""
import asyncio
import json
import time
from typing import AsyncIterator, Dict, List, Optional, Any

from app.services.llm.base import (
    LLMProvider,
    LLMResponse,
    LLMMessage,
    MessageRole,
    ToolCall,
)
from app.core.config import settings


class GroqProvider(LLMProvider):
    """
    Groq LLM provider using their ultra-fast LPU inference.
    Supports function calling with Llama models.
    
    Free tier: 14,400 requests/day, 6,000 tokens/min
    """
    
    # Available models on Groq with function calling support
    AVAILABLE_MODELS = [
        "llama-3.3-70b-versatile",      # Best for complex tasks
        "llama-3.1-70b-versatile",      # Good balance
        "llama-3.1-8b-instant",         # Fast, good for simple tasks
        "mixtral-8x7b-32768",           # Good for longer context
        "gemma2-9b-it",                 # Google's Gemma 2
    ]
    
    def __init__(self, model: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return "groq"
    
    @property
    def default_model(self) -> str:
        return "llama-3.3-70b-versatile"
    
    @property
    def api_key(self) -> str:
        return settings.GROQ_API_KEY or ""
    
    async def initialize(self) -> None:
        """Initialize Groq client"""
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not configured")
        
        try:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
            print(f"[Groq] Initialized with model={self.model or self.default_model}")
        except ImportError:
            raise ImportError("groq package not installed. Run: pip install groq")
    
    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate response using Groq API with optional function calling.
        """
        start_time = time.time()
        
        if not self._client:
            await self.initialize()
        
        # Convert messages to OpenAI format (Groq uses same format)
        groq_messages = self._convert_messages(messages)
        
        # Build request params
        params = {
            "model": self.model or self.default_model,
            "messages": groq_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        
        # Add tools if provided (OpenAI format)
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        
        try:
            response = await self._client.chat.completions.create(**params)
            
            latency = (time.time() - start_time) * 1000
            
            # Extract content and tool calls
            choice = response.choices[0]
            content = choice.message.content or ""
            tool_calls = []
            
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    # Parse arguments from JSON string
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args
                    ))
            
            # Determine finish reason
            finish_reason = choice.finish_reason
            if tool_calls:
                finish_reason = "tool_calls"
            
            # Extract usage for cost tracking
            usage = None
            if response.usage:
                usage = {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            
            return LLMResponse(
                content=content,
                finish_reason=finish_reason,
                tool_calls=tool_calls,
                usage=usage,
                model=response.model,
                latency_ms=latency,
                metadata={
                    "provider": "groq",
                }
            )
            
        except Exception as e:
            print(f"[Groq] Error: {e}")
            raise
    
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream response from Groq"""
        if not self._client:
            await self.initialize()
        
        groq_messages = self._convert_messages(messages)
        
        stream = await self._client.chat.completions.create(
            model=self.model or self.default_model,
            messages=groq_messages,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
            stream=True,
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict]:
        """Convert LLMMessage list to OpenAI/Groq format"""
        result = []
        
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                result.append({
                    "role": "system",
                    "content": msg.content
                })
            elif msg.role == MessageRole.USER:
                result.append({
                    "role": "user",
                    "content": msg.content
                })
            elif msg.role == MessageRole.ASSISTANT:
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or ""
                }
                # Add tool calls if present
                if msg.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                result.append(assistant_msg)
            elif msg.role == MessageRole.TOOL:
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content
                })
        
        return result
