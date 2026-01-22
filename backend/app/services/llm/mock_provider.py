"""
Mock LLM Provider
For testing and development without API costs
"""
import asyncio
import random
import time
from typing import AsyncIterator, Dict, List, Optional, Any

from app.services.llm.base import (
    LLMProvider,
    LLMResponse,
    LLMMessage,
    MessageRole,
    ToolCall,
)


class MockLLMProvider(LLMProvider):
    """
    Mock LLM provider for testing.
    Returns predefined responses based on context.
    """
    
    # Predefined responses for different scenarios
    CONVERSATION_RESPONSES = [
        "I understand. Let me help you with that.",
        "Of course! I'd be happy to assist you.",
        "That's a great question. Here's what I can tell you.",
        "I can help you schedule an appointment. What time works best for you?",
        "Let me check the available slots for you.",
        "I found some options that might work. Would 2 PM or 3 PM be better?",
        "Perfect! I've noted that down. Is there anything else you need?",
        "Thank you for that information. Let me process it.",
    ]
    
    SUMMARY_RESPONSES = [
        "Call Summary: The user inquired about scheduling. Key points discussed include availability and preferences.",
        "Session Recap: A productive conversation about appointment booking. User showed interest in afternoon slots.",
        "Conversation Summary: User engaged in a scheduling discussion. Main topics: time preferences, availability check.",
    ]
    
    def __init__(
        self,
        model: Optional[str] = None,
        latency_ms: float = 100.0,  # Simulated latency
        failure_rate: float = 0.0,  # Probability of failure (0-1)
        **kwargs
    ):
        super().__init__(model, **kwargs)
        self.latency_ms = latency_ms
        self.failure_rate = failure_rate
        self._call_count = 0
    
    @property
    def provider_name(self) -> str:
        return "mock"
    
    @property
    def default_model(self) -> str:
        return "mock-gpt-4"
    
    async def initialize(self) -> None:
        """Mock initialization"""
        print(f"[MockLLM] Initialized with model={self.model or self.default_model}")
        await asyncio.sleep(0.01)  # Simulate startup
    
    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a mock response based on context.
        """
        start_time = time.time()
        self._call_count += 1
        
        # Simulate network latency
        await asyncio.sleep(self.latency_ms / 1000.0)
        
        # Simulate random failures
        if random.random() < self.failure_rate:
            raise Exception("Mock LLM failure (simulated)")
        
        # Determine response type based on kwargs or message content
        response_type = kwargs.get("response_type", "conversation")
        
        # Get the last user message for context
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                last_user_msg = msg.content.lower()
                break
        
        # Generate contextual response
        if response_type == "summary" or "summary" in last_user_msg:
            content = random.choice(self.SUMMARY_RESPONSES)
        elif "book" in last_user_msg or "schedule" in last_user_msg or "appointment" in last_user_msg:
            content = "I can help you book an appointment. We have slots available at 2 PM and 3 PM today. Which would you prefer?"
        elif "time" in last_user_msg or "when" in last_user_msg:
            content = "I have the following times available: 10 AM, 2 PM, and 4 PM. Would any of these work for you?"
        elif "yes" in last_user_msg or "confirm" in last_user_msg:
            content = "Great! I've confirmed your appointment. You'll receive a confirmation shortly."
        elif "no" in last_user_msg or "cancel" in last_user_msg:
            content = "No problem. Let me know if you'd like to explore other options."
        elif "hello" in last_user_msg or "hi" in last_user_msg:
            content = "Hello! I'm your AI assistant. How can I help you today?"
        elif "bye" in last_user_msg or "thank" in last_user_msg:
            content = "You're welcome! Have a great day. Goodbye!"
        else:
            content = random.choice(self.CONVERSATION_RESPONSES)
        
        # Handle tool calls if tools are provided
        tool_calls = []
        if tools and ("check" in last_user_msg or "find" in last_user_msg or "search" in last_user_msg):
            tool_calls.append(
                ToolCall(
                    id=f"call_{self._call_count}",
                    name="fetch_slots",
                    arguments={"date": "today"}
                )
            )
        
        latency = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=content,
            finish_reason="stop",
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": sum(len(m.content.split()) for m in messages) * 2,
                "completion_tokens": len(content.split()) * 2,
                "total_tokens": sum(len(m.content.split()) for m in messages) * 2 + len(content.split()) * 2
            },
            model=self.model or self.default_model,
            latency_ms=latency,
            metadata={"call_count": self._call_count}
        )
    
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream mock response word by word.
        """
        # Get full response first
        response = await self.generate(messages, temperature, max_tokens, **kwargs)
        
        # Stream word by word
        words = response.content.split()
        for i, word in enumerate(words):
            await asyncio.sleep(0.05)  # 50ms per word
            yield word + (" " if i < len(words) - 1 else "")
    
    async def generate_turn_response(
        self,
        transcript: str,
        conversation_history: List[LLMMessage],
        session_id: str,
    ) -> LLMResponse:
        """
        Generate response for a conversation turn (after silence detection).
        This is called after each user utterance.
        """
        print(f"[MockLLM {session_id}] Turn response for: '{transcript[:50]}...'")
        
        # Add the transcript as user message
        messages = conversation_history + [
            LLMMessage(role=MessageRole.USER, content=transcript)
        ]
        
        return await self.generate(messages, response_type="conversation")
    
    async def generate_call_summary(
        self,
        conversation_history: List[LLMMessage],
        session_id: str,
        call_duration_seconds: float,
    ) -> LLMResponse:
        """
        Generate summary after call ends.
        This is called when user ends the call.
        """
        print(f"[MockLLM {session_id}] Generating call summary (duration: {call_duration_seconds:.1f}s)")
        
        # Create summary prompt
        summary_prompt = f"""
        Please provide a brief summary of this conversation.
        Call duration: {call_duration_seconds:.1f} seconds
        Total turns: {len([m for m in conversation_history if m.role == MessageRole.USER])}
        """
        
        messages = conversation_history + [
            LLMMessage(role=MessageRole.USER, content=summary_prompt)
        ]
        
        return await self.generate(messages, response_type="summary")
