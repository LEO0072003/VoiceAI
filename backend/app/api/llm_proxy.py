"""
LLM Proxy Endpoint for Tavus External LLM Mode

This creates an OpenAI-compatible endpoint that Tavus can call.
We intercept the request, run our LLM with tool calling, execute tools locally,
and return the final response to Tavus for avatar rendering.

Flow:
1. Tavus STT captures user speech
2. Tavus calls THIS endpoint with the transcript
3. We call Groq LLM with tools
4. If LLM wants to call a tool, we execute it locally
5. We return the final text response to Tavus
6. Tavus renders avatar with TTS
"""
import json
import logging
import time
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.llm import get_llm_provider, LLMMessage, MessageRole
from app.services.llm.factory import TOOL_DEFINITIONS
from app.services.tools import ToolExecutor
from app.services.cost_tracker import get_cost_tracker
from app.db.database import SessionLocal
from app.db import models

logger = logging.getLogger(__name__)
router = APIRouter()

# Store conversation contexts (conversation_id -> user context)
_llm_contexts: Dict[str, Dict[str, Any]] = {}

# Store conversation messages for summary generation
_conversation_messages: Dict[str, List[Dict[str, str]]] = {}

# Cache the LLM provider to avoid re-initialization on every request
_cached_llm_provider = None


async def get_cached_llm_provider():
    """Get or create a cached LLM provider for better performance"""
    global _cached_llm_provider
    if _cached_llm_provider is None:
        _cached_llm_provider = await get_llm_provider(use_mock=False)
        logger.info("[LLM_PROXY] Created cached LLM provider")
    return _cached_llm_provider


def store_llm_context(conversation_id: str, user_id: int, user_name: str):
    """Store user context for LLM proxy"""
    _llm_contexts[conversation_id] = {
        "user_id": user_id,
        "user_name": user_name,
        "tool_executor": None  # Will be created on first use
    }
    _conversation_messages[conversation_id] = []
    logger.info(f"[LLM_PROXY] Stored context for {conversation_id}: user_id={user_id}")


def get_llm_context(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get user context for a conversation"""
    return _llm_contexts.get(conversation_id)


def get_conversation_messages(conversation_id: str) -> List[Dict[str, str]]:
    """Get stored conversation messages for summary"""
    return _conversation_messages.get(conversation_id, [])


def add_conversation_message(conversation_id: str, role: str, content: str):
    """Add a message to conversation history for summary"""
    if conversation_id not in _conversation_messages:
        _conversation_messages[conversation_id] = []
    _conversation_messages[conversation_id].append({"role": role, "content": content})


def clear_llm_context(conversation_id: str):
    """Clear context when conversation ends"""
    if conversation_id in _llm_contexts:
        del _llm_contexts[conversation_id]
        logger.info(f"[LLM_PROXY] Cleared context for {conversation_id}")
    if conversation_id in _conversation_messages:
        del _conversation_messages[conversation_id]


# Maximum tool iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 5

import re

def parse_text_tool_calls(content: str) -> tuple[str, list]:
    """
    Parse tool calls that are embedded in text (Groq sometimes outputs these).
    Returns (clean_content, list of parsed tool calls)
    
    Patterns to detect:
    - <function=name>{"args": "value"}</function>
    - <function=name={"args": "value"}>
    """
    from app.services.llm.base import ToolCall
    import uuid
    
    tool_calls = []
    clean_content = content
    
    # Pattern 1: <function=name>{"args"}</function>
    pattern1 = r'<function=(\w+)>(\{[^}]+\})</function>'
    # Pattern 2: <function=name={"args"}>
    pattern2 = r'<function=(\w+)=?(\{[^}]+\})>?'
    # Pattern 3: <function=name{"args"}>
    pattern3 = r'<function=(\w+)(\{[^}]+\})>?'
    
    for pattern in [pattern1, pattern2, pattern3]:
        matches = re.findall(pattern, content)
        for match in matches:
            func_name = match[0]
            try:
                args = json.loads(match[1])
            except json.JSONDecodeError:
                args = {}
            
            tool_calls.append(ToolCall(
                id=f"call_{uuid.uuid4().hex[:8]}",
                name=func_name,
                arguments=args
            ))
    
    # Remove all function call syntax from content
    clean_content = re.sub(r'<function=\w+[=>]?\{[^}]+\}>?(?:</function>)?', '', content)
    clean_content = clean_content.strip()
    
    return clean_content, tool_calls


def clean_response_for_speech(content: str) -> str:
    """Remove any remaining function call syntax that shouldn't be spoken"""
    # Remove any <function...> tags
    content = re.sub(r'<function[^>]*>.*?(?:</function>|$)', '', content, flags=re.DOTALL)
    # Remove any {..."json"...} that looks like function args
    content = re.sub(r'\{"[^"]+":.*?\}', '', content)
    # Clean up extra spaces
    content = re.sub(r'\s+', ' ', content).strip()
    return content


class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 500
    stream: Optional[bool] = False


class ChatCompletionChoice(BaseModel):
    index: int
    message: Dict[str, Any]
    finish_reason: str


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


@router.post("/chat/completions")
@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint for Tavus.
    
    Tavus sends conversation here, we process with our LLM + tools,
    and return the response for avatar to speak.
    """
    body = await request.json()
    logger.info(f"[LLM_PROXY] ========== Chat Completion Request ==========")
    logger.info(f"[LLM_PROXY] Model: {body.get('model')}")
    
    stream_requested = body.get("stream", False)
    logger.info(f"[LLM_PROXY] Stream requested: {stream_requested}")
    logger.info(f"[LLM_PROXY] Full request body keys: {list(body.keys())}")
    
    messages = body.get("messages", [])
    temperature = body.get("temperature", 0.7)
    max_tokens = body.get("max_tokens", 500)
    
    # Log the last user message
    user_messages = [m for m in messages if m.get("role") == "user"]
    if user_messages:
        last_user_msg = user_messages[-1].get("content", "")[:100]
        logger.info(f"[LLM_PROXY] Last user message: {last_user_msg}...")
    
    # Try to extract conversation_id from context or headers
    conversation_id = request.headers.get("x-conversation-id", "unknown")
    
    # Try to find user context from system message
    user_id = None
    user_name = "User"
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            # Extract user_id from system prompt if present
            if "User ID:" in content:
                try:
                    user_id_str = content.split("User ID:")[1].split(".")[0].strip()
                    user_id = int(user_id_str)
                except:
                    pass
            if "user's name is" in content.lower():
                try:
                    user_name = content.split("name is")[1].split(".")[0].strip()
                except:
                    pass
    
    logger.info(f"[LLM_PROXY] Extracted user_id={user_id}, user_name={user_name}")
    
    # Create tool executor if we have user context
    tool_executor = None
    if user_id:
        tool_executor = ToolExecutor(
            session_id=conversation_id,
            user_id=user_id,
            user_name=user_name
        )
    
    # Convert messages to LLMMessage format
    llm_messages = []
    for msg in messages:
        role_str = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role_str == "system":
            llm_messages.append(LLMMessage(role=MessageRole.SYSTEM, content=content))
        elif role_str == "assistant":
            llm_messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=content))
        else:
            llm_messages.append(LLMMessage(role=MessageRole.USER, content=content))
    
    # Get cached LLM provider (avoids re-initialization overhead)
    try:
        llm = await get_cached_llm_provider()
    except Exception as e:
        logger.warning(f"[LLM_PROXY] Failed to get LLM provider: {e}, using mock")
        llm = await get_llm_provider(use_mock=True)
    
    # Process with tool calling loop
    final_response = ""
    iteration = 0
    
    # Initialize cost tracker for this conversation
    cost_tracker = get_cost_tracker(conversation_id)
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    while iteration < MAX_TOOL_ITERATIONS:
        iteration += 1
        iter_start = time.time()
        logger.info(f"[LLM_PROXY] Iteration {iteration}: Calling LLM...")
        
        try:
            # Call LLM with tools
            llm_start = time.time()
            llm_response = await llm.generate(
                messages=llm_messages,
                tools=TOOL_DEFINITIONS if tool_executor else None,
                temperature=temperature,
                max_tokens=max_tokens
            )
            llm_time = (time.time() - llm_start) * 1000
            logger.info(f"[LLM_PROXY] LLM response in {llm_time:.0f}ms")
            
            # Track token usage from LLM response
            if llm_response.usage:
                prompt_tokens = llm_response.usage.get("prompt_tokens", 0)
                completion_tokens = llm_response.usage.get("completion_tokens", 0)
                total_prompt_tokens += prompt_tokens
                total_completion_tokens += completion_tokens
                logger.info(f"[LLM_PROXY] Tokens: +{prompt_tokens} prompt, +{completion_tokens} completion")
            
            # Get tool calls - either from proper response or parse from text
            tool_calls_to_execute = llm_response.tool_calls or []
            response_content = llm_response.content or ""
            
            # If no proper tool calls, check if they're embedded in text (Groq quirk)
            if not tool_calls_to_execute and tool_executor and '<function=' in response_content:
                logger.info(f"[LLM_PROXY] Parsing text-based tool calls from response")
                clean_content, parsed_calls = parse_text_tool_calls(response_content)
                if parsed_calls:
                    tool_calls_to_execute = parsed_calls
                    response_content = clean_content
                    logger.info(f"[LLM_PROXY] Parsed tool calls from text: {[tc.name for tc in parsed_calls]}")
            
            # Check if LLM wants to call tools
            if tool_calls_to_execute and tool_executor:
                logger.info(f"[LLM_PROXY] Tool calls: {[tc.name for tc in tool_calls_to_execute]}")
                
                # Add assistant message with tool calls
                from app.services.llm.base import ToolCall
                llm_messages.append(LLMMessage(
                    role=MessageRole.ASSISTANT,
                    content=response_content,
                    tool_calls=tool_calls_to_execute
                ))
                
                # Execute each tool
                for tool_call in tool_calls_to_execute:
                    logger.info(f"[LLM_PROXY] Executing tool: {tool_call.name}")
                    logger.info(f"[LLM_PROXY] Arguments: {tool_call.arguments}")
                    
                    tool_start = time.time()
                    result = await tool_executor.execute(tool_call.name, tool_call.arguments)
                    tool_time = (time.time() - tool_start) * 1000
                    logger.info(f"[LLM_PROXY] Tool result ({tool_time:.0f}ms): {json.dumps(result, default=str)[:200]}...")
                    
                    # Add tool result to messages
                    llm_messages.append(LLMMessage(
                        role=MessageRole.TOOL,
                        content=json.dumps(result),
                        tool_call_id=tool_call.id,
                        name=tool_call.name
                    ))
                
                # Continue loop to get final response
                continue
            else:
                # No tool calls - we have final response
                final_response = response_content or "I'm sorry, I couldn't generate a response."
                # Clean any remaining function syntax from the response
                final_response = clean_response_for_speech(final_response)
                break
                
        except Exception as e:
            logger.error(f"[LLM_PROXY] Error: {e}", exc_info=True)
            final_response = "I'm sorry, I had trouble processing that. Could you please try again?"
            break
    
    # Store conversation messages for summary generation
    # Extract user message from this turn
    if user_messages:
        last_user_content = user_messages[-1].get("content", "")
        add_conversation_message(conversation_id, "user", last_user_content)
    # Store assistant response
    add_conversation_message(conversation_id, "assistant", final_response)
    
    # Track accumulated token usage
    if total_prompt_tokens > 0 or total_completion_tokens > 0:
        cost_tracker.track_llm(total_prompt_tokens, total_completion_tokens)
        logger.info(f"[LLM_PROXY] Total tokens tracked: {total_prompt_tokens} prompt, {total_completion_tokens} completion")
    
    logger.info(f"[LLM_PROXY] Final response: {final_response[:100]}...")
    
    # If streaming requested, return SSE stream
    if stream_requested:
        logger.info(f"[LLM_PROXY] Returning STREAMING response to Tavus")
        
        async def generate_stream() -> AsyncGenerator[str, None]:
            """Generate SSE stream chunks - send full response then done"""
            completion_id = f"chatcmpl-{int(time.time())}"
            model_name = body.get("model", "groq-proxy")
            
            logger.info(f"[LLM_PROXY] Starting SSE stream with completion_id={completion_id}")
            
            # First chunk: role
            role_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant"
                        },
                        "finish_reason": None
                    }
                ]
            }
            logger.info(f"[LLM_PROXY] Sending role chunk")
            yield f"data: {json.dumps(role_chunk)}\n\n"
            
            # Second chunk: full content
            content_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": final_response
                        },
                        "finish_reason": None
                    }
                ]
            }
            logger.info(f"[LLM_PROXY] Sending content chunk: {len(final_response)} chars")
            yield f"data: {json.dumps(content_chunk)}\n\n"
            
            # Final chunk with finish_reason
            final_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }
                ]
            }
            logger.info(f"[LLM_PROXY] Sending final chunk with stop")
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"
            logger.info(f"[LLM_PROXY] SSE stream complete")
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    # Non-streaming response
    logger.info(f"[LLM_PROXY] Returning non-streaming response to Tavus")
    
    # Build OpenAI-compatible response
    response = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "groq-proxy"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": final_response
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": sum(len(m.get("content", "").split()) for m in messages),
            "completion_tokens": len(final_response.split()),
            "total_tokens": sum(len(m.get("content", "").split()) for m in messages) + len(final_response.split())
        }
    }
    
    logger.info(f"[LLM_PROXY] Returning response to Tavus")
    return response


@router.get("/v1/models")
async def list_models():
    """OpenAI-compatible models endpoint"""
    return {
        "object": "list",
        "data": [
            {
                "id": "groq-llama-3.3-70b",
                "object": "model",
                "created": 1700000000,
                "owned_by": "groq-proxy"
            }
        ]
    }


# Summary generation prompt
CALL_SUMMARY_PROMPT = """You are summarizing a voice call between an AI assistant and a user about appointment booking.

Based on the conversation below, provide a JSON response with:
1. "summary": A brief 2-3 sentence summary of the conversation
2. "appointments_discussed": List of any appointments mentioned (booked, cancelled, modified, or viewed)
3. "user_preferences": Any preferences the user mentioned (preferred times, dates, etc.)
4. "actions_taken": List of actions completed (e.g., "Booked appointment for Feb 3rd at 5pm")
5. "sentiment": User sentiment - "positive", "neutral", or "negative"

IMPORTANT: Return ONLY valid JSON, no markdown or extra text.

Conversation:
{conversation}

Return JSON:"""


async def generate_call_summary(conversation_id: str) -> Dict[str, Any]:
    """Generate an LLM summary for a conversation"""
    messages = get_conversation_messages(conversation_id)
    
    if not messages:
        return {
            "summary": "No conversation recorded.",
            "appointments_discussed": [],
            "user_preferences": [],
            "actions_taken": [],
            "sentiment": "neutral"
        }
    
    # Format conversation for summary
    conversation_text = ""
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        conversation_text += f"{role}: {msg['content']}\n"
    
    # Get LLM provider
    try:
        llm = await get_cached_llm_provider()
    except Exception as e:
        logger.error(f"[SUMMARY] Failed to get LLM: {e}")
        return {
            "summary": "Unable to generate summary.",
            "appointments_discussed": [],
            "user_preferences": [],
            "actions_taken": [],
            "sentiment": "neutral"
        }
    
    # Generate summary
    try:
        summary_prompt = CALL_SUMMARY_PROMPT.format(conversation=conversation_text)
        response = await llm.generate(
            messages=[LLMMessage(role=MessageRole.USER, content=summary_prompt)],
            temperature=0.3,
            max_tokens=500
        )
        
        # Parse JSON response
        content = response.content.strip()
        # Clean up any markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        summary_data = json.loads(content)
        logger.info(f"[SUMMARY] Generated summary for {conversation_id}")
        return summary_data
        
    except json.JSONDecodeError as e:
        logger.error(f"[SUMMARY] Failed to parse JSON: {e}, content: {response.content[:200]}")
        return {
            "summary": response.content[:200] if response else "Call completed.",
            "appointments_discussed": [],
            "user_preferences": [],
            "actions_taken": [],
            "sentiment": "neutral"
        }
    except Exception as e:
        logger.error(f"[SUMMARY] Error generating summary: {e}")
        return {
            "summary": "Call completed successfully.",
            "appointments_discussed": [],
            "user_preferences": [],
            "actions_taken": [],
            "sentiment": "neutral"
        }


@router.get("/conversations/{conversation_id}/summary")
async def get_call_summary(conversation_id: str):
    """Get LLM-generated summary for a conversation"""
    summary = await generate_call_summary(conversation_id)
    return {
        "conversation_id": conversation_id,
        "summary": summary
    }
