"""
LLM Service Module
Provides a generic interface for LLM providers with Strategy pattern
"""
from app.services.llm.base import LLMProvider, LLMResponse, LLMMessage, MessageRole
from app.services.llm.factory import LLMFactory, get_llm_provider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.groq_provider import GroqProvider

__all__ = [
    "LLMProvider",
    "LLMResponse", 
    "LLMMessage",
    "MessageRole",
    "LLMFactory",
    "get_llm_provider",
    "MockLLMProvider",
    "GroqProvider",
]
