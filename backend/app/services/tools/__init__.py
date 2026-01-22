"""
Tools Module
Defines tool schemas and execution for the voice agent
"""
from app.services.tools.definitions import (
    TOOL_DEFINITIONS,
    VOICE_AGENT_SYSTEM_PROMPT,
    CALL_SUMMARY_PROMPT,
)
from app.services.tools.executor import ToolExecutor

__all__ = [
    "TOOL_DEFINITIONS",
    "VOICE_AGENT_SYSTEM_PROMPT",
    "CALL_SUMMARY_PROMPT",
    "ToolExecutor",
]
