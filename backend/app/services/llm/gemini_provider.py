"""
Gemini LLM Provider
Google's Gemini API implementation with function calling support
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


class GeminiProvider(LLMProvider):
    """
    Google Gemini LLM provider.
    Implements the LLMProvider interface for Gemini API with function calling.
    """
    
    # Models to try in order (some may have more quota available)
    FALLBACK_MODELS = [
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro-latest",
        "gemini-2.0-flash-exp",
    ]
    
    def __init__(self, model: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self._model = None
        self._genai = None
        self._current_model_name = None
    
    @property
    def provider_name(self) -> str:
        return "gemini"
    
    @property
    def default_model(self) -> str:
        return "gemini-1.5-flash-latest"
    
    @property
    def api_key(self) -> str:
        return settings.GEMINI_API_KEY or ""
    
    async def initialize(self) -> None:
        """Initialize Gemini client"""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        
        try:
            import google.generativeai as genai
            self._genai = genai
            genai.configure(api_key=self.api_key)
            
            self._current_model_name = self.model or self.default_model
            self._model = genai.GenerativeModel(self._current_model_name)
            
            print(f"[Gemini] Initialized with model={self._current_model_name}")
        except ImportError:
            raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
    
    async def _try_with_fallback(self, func, *args, **kwargs):
        """Try the function with fallback models if rate limited"""
        import google.generativeai as genai
        
        models_to_try = [self._current_model_name] + [m for m in self.FALLBACK_MODELS if m != self._current_model_name]
        last_error = None
        
        for model_name in models_to_try:
            try:
                # Update model if different
                if model_name != self._current_model_name:
                    print(f"[Gemini] Trying fallback model: {model_name}")
                    self._model = genai.GenerativeModel(model_name)
                    self._current_model_name = model_name
                
                return await func(*args, **kwargs)
                
            except Exception as e:
                error_str = str(e)
                last_error = e
                
                # Check if it's a rate limit error
                if "429" in error_str or "quota" in error_str.lower() or "ResourceExhausted" in error_str:
                    print(f"[Gemini] Rate limited on {model_name}, trying next...")
                    continue
                elif "404" in error_str or "not found" in error_str.lower():
                    print(f"[Gemini] Model {model_name} not found, trying next...")
                    continue
                else:
                    # Non-rate-limit error, raise immediately
                    raise
        
        # All models failed
        raise last_error
    
    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate response using Gemini API with optional function calling.
        Uses fallback models if rate limited.
        """
        start_time = time.time()
        
        if not self._model:
            await self.initialize()
        
        # Convert messages to Gemini format
        gemini_contents = self._convert_messages_to_contents(messages)
        
        # Build generation config
        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens
        
        # Prepare tools if provided
        gemini_tools = None
        if tools:
            gemini_tools = self._convert_tools_to_gemini(tools)
        
        async def _do_generate():
            # Make API call
            if gemini_tools:
                return await asyncio.to_thread(
                    self._model.generate_content,
                    gemini_contents,
                    generation_config=generation_config,
                    tools=gemini_tools
                )
            else:
                return await asyncio.to_thread(
                    self._model.generate_content,
                    gemini_contents,
                    generation_config=generation_config
                )
        
        try:
            # Try with fallback models if rate limited
            response = await self._try_with_fallback(_do_generate)
            
            latency = (time.time() - start_time) * 1000
            
            # Extract content and tool calls
            content = ""
            tool_calls = []
            
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        content += part.text
                    elif hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        # Convert function call arguments
                        args = {}
                        if fc.args:
                            for key, value in fc.args.items():
                                args[key] = value
                        
                        tool_calls.append(ToolCall(
                            id=f"call_{len(tool_calls)}",
                            name=fc.name,
                            arguments=args
                        ))
            
            # Get finish reason
            finish_reason = "stop"
            if tool_calls:
                finish_reason = "tool_calls"
            
            return LLMResponse(
                content=content,
                finish_reason=finish_reason,
                tool_calls=tool_calls,
                model=self.model or self.default_model,
                latency_ms=latency,
                metadata={
                    "provider": "gemini"
                }
            )
            
        except Exception as e:
            error_str = str(e)
            print(f"[Gemini] Error: {error_str}")
            
            # Check for quota exceeded error
            if "429" in error_str or "quota" in error_str.lower() or "ResourceExhausted" in error_str:
                print("[Gemini] Quota exceeded - consider using mock provider or waiting for quota reset")
            
            raise
    
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream response from Gemini"""
        if not self._model:
            await self.initialize()
        
        gemini_contents = self._convert_messages_to_contents(messages)
        
        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens
        
        response = await asyncio.to_thread(
            self._model.generate_content,
            gemini_contents,
            generation_config=generation_config,
            stream=True
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
    
    def _convert_messages_to_contents(self, messages: List[LLMMessage]) -> List[Dict]:
        """Convert LLMMessage list to Gemini contents format"""
        contents = []
        system_instruction = None
        
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Gemini handles system as a separate parameter or prefixed to first user message
                system_instruction = msg.content
            elif msg.role == MessageRole.USER:
                content = msg.content
                if system_instruction and not contents:
                    # Prefix system instruction to first user message
                    content = f"{system_instruction}\n\nUser: {content}"
                    system_instruction = None
                contents.append({
                    "role": "user",
                    "parts": [content]
                })
            elif msg.role == MessageRole.ASSISTANT:
                contents.append({
                    "role": "model",
                    "parts": [msg.content]
                })
            elif msg.role == MessageRole.TOOL:
                # Tool response - add as function response
                contents.append({
                    "role": "function",
                    "parts": [{
                        "function_response": {
                            "name": msg.name or "tool",
                            "response": {"result": msg.content}
                        }
                    }]
                })
        
        return contents
    
    def _convert_tools_to_gemini(self, tools: List[Dict[str, Any]]) -> List[Any]:
        """Convert OpenAI-style tools to Gemini format"""
        try:
            from google.generativeai.types import FunctionDeclaration, Tool
            
            function_declarations = []
            for tool in tools:
                if tool.get("type") == "function":
                    func = tool["function"]
                    fd = FunctionDeclaration(
                        name=func["name"],
                        description=func["description"],
                        parameters=func.get("parameters", {})
                    )
                    function_declarations.append(fd)
            
            return [Tool(function_declarations=function_declarations)]
        except ImportError:
            print("[Gemini] Warning: Could not import types for tools")
            return None

