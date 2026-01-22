"""
LLM Provider Factory
Creates LLM provider instances using Factory pattern
No global state - providers created per-request
"""
from enum import Enum
from typing import Dict, Optional, Type

from app.services.llm.base import LLMProvider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.groq_provider import GroqProvider
from app.core.config import settings


class LLMProviderType(str, Enum):
    """Available LLM providers"""
    MOCK = "mock"
    GROQ = "groq"
    GEMINI = "gemini"
    OPENAI = "openai"  # Future
    ANTHROPIC = "anthropic"  # Future


class LLMFactory:
    """
    Factory for creating LLM provider instances.
    Stateless - creates new instances per request.
    """
    
    # Registry of available providers (class-level constant, not mutable state)
    _provider_registry: Dict[LLMProviderType, Type[LLMProvider]] = {
        LLMProviderType.MOCK: MockLLMProvider,
        LLMProviderType.GROQ: GroqProvider,
        LLMProviderType.GEMINI: GeminiProvider,
    }
    
    @classmethod
    def register_provider(
        cls,
        provider_type: LLMProviderType,
        provider_class: Type[LLMProvider]
    ) -> None:
        """
        Register a new provider type.
        Allows extending with custom providers.
        """
        cls._provider_registry[provider_type] = provider_class
    
    @classmethod
    def create(
        cls,
        provider_type: LLMProviderType = LLMProviderType.MOCK,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMProvider:
        """
        Create a new LLM provider instance.
        
        Args:
            provider_type: Type of provider to create
            model: Model to use (provider-specific)
            **kwargs: Provider-specific configuration
            
        Returns:
            New LLMProvider instance
        """
        provider_class = cls._provider_registry.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unknown provider type: {provider_type}")
        
        return provider_class(model=model, **kwargs)
    
    @classmethod
    def get_default_provider_type(cls) -> LLMProviderType:
        """
        Determine the default provider based on configuration.
        Priority: Groq > Gemini > Mock
        Falls back to mock if no API keys are configured.
        """
        if settings.GROQ_API_KEY:
            return LLMProviderType.GROQ
        if settings.GEMINI_API_KEY:
            return LLMProviderType.GEMINI
        return LLMProviderType.MOCK
    
    @classmethod
    def list_providers(cls) -> list:
        """List all registered provider types"""
        return list(cls._provider_registry.keys())


async def get_llm_provider(
    provider_type: Optional[LLMProviderType] = None,
    model: Optional[str] = None,
    use_mock: bool = False,  # Changed default to False for real LLM
    **kwargs
) -> LLMProvider:
    """
    Get an initialized LLM provider.
    Creates a new instance each time (stateless).
    
    Args:
        provider_type: Specific provider to use, or None for default
        model: Model to use
        use_mock: Force mock provider (default False for production)
        **kwargs: Provider-specific options
        
    Returns:
        Initialized LLMProvider ready for use
    """
    # Force mock if requested
    if use_mock:
        provider_type = LLMProviderType.MOCK
    elif provider_type is None:
        provider_type = LLMFactory.get_default_provider_type()
    
    # Create new provider instance
    provider = LLMFactory.create(
        provider_type=provider_type,
        model=model,
        **kwargs
    )
    
    # Initialize
    await provider.initialize()
    provider._initialized = True
    
    return provider


# Re-export prompts from tools module for convenience
from app.services.tools.definitions import (
    VOICE_AGENT_SYSTEM_PROMPT,
    CALL_SUMMARY_PROMPT as CALL_SUMMARY_SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
)


# Pre-defined prompts for voice AI
VOICE_AI_SYSTEM_PROMPT = """You are a helpful AI voice assistant for scheduling appointments. 
Your responses should be:
- Concise (under 50 words for voice)
- Natural and conversational
- Helpful and professional

You can help users:
- Schedule appointments
- Check availability
- Confirm or modify bookings
- Answer questions about services

Always be polite and confirm important details."""


CALL_SUMMARY_SYSTEM_PROMPT = """You are summarizing a voice call between an AI assistant and a user.
Provide a brief summary including:
- Main topic discussed
- Any appointments scheduled
- Key action items
- User sentiment (positive/neutral/negative)

Keep the summary under 100 words."""
