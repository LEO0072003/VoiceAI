"""
Voice WebSocket API with full LLM tool calling integration.
Handles: STT (Deepgram) → LLM (Groq with tools) → Tool execution → TTS (Cartesia) → Response
"""
import asyncio
import base64
import json
import logging
import math
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.db.database import SessionLocal
from app.db import models

from app.core.security import get_current_user, decode_token
from app.core.session_manager import session_manager
from app.services.deepgram_service import DeepgramStreamingClient
from app.services.tts_service import get_tts_service, synthesize_speech
from app.services.cost_tracker import get_cost_tracker, CostTracker
from app.services.llm import (
    get_llm_provider,
    LLMMessage,
    MessageRole,
)
from app.services.llm.factory import (
    VOICE_AGENT_SYSTEM_PROMPT,
    CALL_SUMMARY_SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
)
from app.services.tools import ToolExecutor


router = APIRouter()
logger = logging.getLogger(__name__)

# Maximum tool call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 10


def _generate_tone_wav_data_url(freq_hz: float = 440.0, duration_s: float = 0.5, sample_rate: int = 16000, amplitude: float = 0.3) -> str:
    """
    Generate a simple mono WAV data URL containing a sine tone.
    """
    n_samples = int(duration_s * sample_rate)
    # 16-bit PCM
    data = bytearray()

    # WAV header
    byte_rate = sample_rate * 2  # 16-bit mono
    block_align = 2
    subchunk2_size = n_samples * 2
    chunk_size = 36 + subchunk2_size

    def _write_u32_le(val: int):
        data.extend(val.to_bytes(4, byteorder="little", signed=False))

    def _write_u16_le(val: int):
        data.extend(val.to_bytes(2, byteorder="little", signed=False))

    def _write_bytes(b: bytes):
        data.extend(b)

    _write_bytes(b"RIFF")
    _write_u32_le(chunk_size)
    _write_bytes(b"WAVE")

    # fmt chunk
    _write_bytes(b"fmt ")
    _write_u32_le(16)  # PCM
    _write_u16_le(1)   # Audio format: PCM
    _write_u16_le(1)   # Num channels: mono
    _write_u32_le(sample_rate)
    _write_u32_le(byte_rate)
    _write_u16_le(block_align)
    _write_u16_le(16)  # bits per sample

    # data chunk
    _write_bytes(b"data")
    _write_u32_le(subchunk2_size)

    # Samples
    for i in range(n_samples):
        t = i / sample_rate
        sample = int(amplitude * 32767.0 * math.sin(2 * math.pi * freq_hz * t))
        _write_u16_le(sample & 0xFFFF)

    b64 = base64.b64encode(bytes(data)).decode("ascii")
    return f"data:audio/wav;base64,{b64}"


def _format_conversation_for_summary(messages: List[Dict[str, str]]) -> str:
    """Format conversation history (from Redis) for summary generation"""
    lines = []
    for msg in messages:
        if msg.get("role") == "system":
            continue  # Skip system prompts in summary
        role_name = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role_name}: {msg.get('content', '')}")
    return "\n".join(lines) if lines else "No conversation recorded."


def _redis_messages_to_llm_messages(messages: List[Dict[str, str]]) -> List[LLMMessage]:
    """Convert Redis message dicts to LLMMessage objects"""
    result = []
    for msg in messages:
        role_str = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Handle tool role messages
        if role_str == "tool":
            result.append(LLMMessage(
                role=MessageRole.TOOL,
                content=content,
                tool_call_id=msg.get("tool_call_id"),
                name=msg.get("name")
            ))
        # Handle assistant messages with tool calls
        elif role_str == "assistant" and msg.get("tool_calls"):
            from app.services.llm.base import ToolCall
            tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("name", ""),
                    arguments=tc.get("arguments", {})
                )
                for tc in msg.get("tool_calls", [])
            ]
            result.append(LLMMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                tool_calls=tool_calls
            ))
        else:
            role = MessageRole(role_str) if role_str in [r.value for r in MessageRole] else MessageRole.USER
            result.append(LLMMessage(role=role, content=content))
    return result


@router.post("/api/voice/initiate")
async def initiate_call(current_user=Depends(get_current_user)):
    """
    Initiate a voice session and return session info with greeting.
    Requires Bearer token.
    """
    sess = session_manager.create_session()
    session_manager.set_user(sess["session_id"], getattr(current_user, "contact_number", "unknown"))
    session_manager.set_status(sess["session_id"], "greet_ready")

    # Get user's name for personalized greeting
    user_name = getattr(current_user, "name", "there")
    greeting_text = f"Hello {user_name}! I'm your AI appointment assistant. I can help you book, check, modify, or cancel appointments. How can I assist you today?"
    
    # Generate TTS for greeting
    tts_response = await synthesize_speech(greeting_text)

    return JSONResponse({
        "session_id": sess["session_id"],
        "greeting_text": greeting_text,
        "greeting_audio_data": tts_response.audio_base64,
        "greeting_audio_format": "pcm_16000",
        "greeting_sample_rate": tts_response.sample_rate,
        "greeting_duration_ms": tts_response.duration_ms,
        "greeting_visemes": tts_response.visemes,
    })


async def _process_llm_with_tools(
    session_id: str,
    websocket: WebSocket,
    tool_executor: ToolExecutor,
    cost_tracker: Optional[CostTracker] = None
) -> tuple[str, bool]:
    """
    Process LLM response with tool calling loop.
    
    This implements the agentic loop:
    1. Send conversation to LLM with tools
    2. If LLM returns tool calls, execute them
    3. Add tool results to conversation
    4. Repeat until LLM returns text (no tool calls)
    
    Returns a tuple of (final_text_response, should_end_conversation).
    """
    logger.info(f"[CONV {session_id}] ========== Starting LLM processing ==========")
    
    # Try real LLM first, fall back to mock if rate limited
    try:
        llm = await get_llm_provider(use_mock=False)
        logger.info(f"[CONV {session_id}] Using real LLM provider")
    except Exception as e:
        logger.warning(f"[CONV {session_id}] Failed to init LLM, using mock: {e}")
        llm = await get_llm_provider(use_mock=True)
    
    iteration = 0
    end_conversation = False
    
    while iteration < MAX_TOOL_ITERATIONS:
        iteration += 1
        
        # Get conversation from Redis and convert to LLMMessage
        redis_messages = session_manager.get_conversation(session_id)
        logger.info(f"[CONV {session_id}] Iteration {iteration}: {len(redis_messages)} messages in history")
        llm_messages = _redis_messages_to_llm_messages(redis_messages)
        
        # Generate response with tools
        logger.info(f"[LLM {session_id}] Generating response with {len(TOOL_DEFINITIONS)} tools available")
        start_time = time.time()
        
        try:
            llm_response = await llm.generate(
                messages=llm_messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.7,
                max_tokens=500,
            )
            
            # Track LLM usage
            if cost_tracker and llm_response.usage:
                cost_tracker.track_llm(
                    input_tokens=llm_response.usage.get("input_tokens", 0),
                    output_tokens=llm_response.usage.get("output_tokens", 0)
                )
                logger.info(f"[LLM {session_id}] Token usage: in={llm_response.usage.get('input_tokens', 0)}, out={llm_response.usage.get('output_tokens', 0)}")
        except Exception as e:
            error_str = str(e)
            # Check if rate limited
            if "429" in error_str or "quota" in error_str.lower() or "ResourceExhausted" in error_str:
                logger.warning(f"[LLM {session_id}] Rate limited, falling back to mock provider")
                llm = await get_llm_provider(use_mock=True)
                llm_response = await llm.generate(
                    messages=llm_messages,
                    tools=TOOL_DEFINITIONS,
                    temperature=0.7,
                    max_tokens=500,
                )
            else:
                raise
        
        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"[LLM {session_id}] Response latency: {latency_ms:.1f}ms")
        
        # Check if LLM made tool calls
        if llm_response.tool_calls:
            logger.info(f"[LLM {session_id}] Tool calls requested: {[tc.name for tc in llm_response.tool_calls]}")
            
            # Store assistant message with tool calls in Redis
            tool_calls_data = [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments
                }
                for tc in llm_response.tool_calls
            ]
            session_manager.add_message(
                session_id, 
                "assistant", 
                llm_response.content or "",
                tool_calls=tool_calls_data
            )
            
            # Execute each tool and send updates to frontend
            for tool_call in llm_response.tool_calls:
                # Send tool_call event to frontend (assignment requirement)
                await websocket.send_text(json.dumps({
                    "type": "tool_call",
                    "tool": tool_call.name,
                    "tool_call_id": tool_call.id,
                    "arguments": tool_call.arguments,
                    "status": "in_progress",
                    "message": f"Executing {tool_call.name}..."
                }))
                
                # Execute the tool
                logger.info(f"[TOOL {session_id}] >>>>>>> Executing: {tool_call.name}")
                logger.info(f"[TOOL {session_id}] Arguments: {json.dumps(tool_call.arguments, indent=2)}")
                tool_result = await tool_executor.execute(
                    tool_call.name,
                    tool_call.arguments
                )
                logger.info(f"[TOOL {session_id}] <<<<<<< Result: {json.dumps(tool_result, indent=2, default=str)}")
                
                # Check for end_conversation
                if tool_call.name == "end_conversation":
                    end_conversation = True
                
                # Send tool_result event to frontend
                await websocket.send_text(json.dumps({
                    "type": "tool_result",
                    "tool": tool_call.name,
                    "tool_call_id": tool_call.id,
                    "status": tool_result.get("status", "success"),
                    "result": tool_result
                }))
                
                # Add tool result to conversation in Redis
                session_manager.add_message(
                    session_id,
                    "tool",
                    json.dumps(tool_result),
                    tool_call_id=tool_call.id,
                    name=tool_call.name
                )
            
            # If end_conversation was called, generate final summary
            if end_conversation:
                logger.info(f"[CONV {session_id}] End conversation triggered, generating final response...")
                # Continue loop to get LLM's final response after tool execution
                continue
        else:
            # No tool calls - LLM returned final text response
            final_response = llm_response.content or "I'm sorry, I couldn't generate a response."
            logger.info(f"[CONV {session_id}] Final text response: {final_response[:150]}...")
            
            # Store assistant response in Redis
            session_manager.add_message(session_id, "assistant", final_response)
            
            return final_response, end_conversation
    
    # Max iterations reached
    logger.warning(f"[CONV {session_id}] Max tool iterations ({MAX_TOOL_ITERATIONS}) reached")
    return "I apologize, but I'm having trouble processing your request. Could you please try again?", False


@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket):
    """
    Voice WebSocket endpoint with full tool calling support.
    
    Flow:
    1. Auth → Create session
    2. Audio chunks → Deepgram STT
    3. End of speech → LLM with tools → Tool execution loop → Response
    4. End call → Generate summary + cost breakdown
    """
    # Accept first to receive auth message
    await websocket.accept()

    session_id = None
    deepgram_client: Optional[DeepgramStreamingClient] = None
    tool_executor: Optional[ToolExecutor] = None
    cost_tracker: Optional[CostTracker] = None
    audio_start_time: Optional[float] = None
    
    try:
        # Expect an auth message first
        auth_raw = await websocket.receive_text()
        auth_msg = json.loads(auth_raw)
        if auth_msg.get("type") != "auth":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        token = auth_msg.get("token")
        session_id = auth_msg.get("session_id")
        if not token or not session_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Validate token and session
        payload = decode_token(token)
        if not session_manager.get(session_id):
            # Unknown session
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        contact_number = payload.get("sub", "unknown")
        session_manager.set_user(session_id, contact_number)
        session_manager.set_ws_active(session_id, True)
        session_manager.set_status(session_id, "connected")

        logger.info(f"[WS {session_id}] ========== Session Started ==========")
        logger.info(f"[WS {session_id}] Authenticated user: {contact_number}")

        # Load user from DB to capture user_id/name for tool executor and ownership tracking
        db = SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.contact_number == contact_number).first()
        finally:
            db.close()

        if not user:
            logger.error(f"[WS {session_id}] User not found for contact_number={contact_number}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        logger.info(f"[WS {session_id}] Loaded user from DB: id={user.id}, name={user.name}, contact={user.contact_number}")

        # Initialize conversation history in Redis with system prompt including user context
        user_context = f"""

## User Context
- The user's name is {user.name}
- User ID: {user.id}
- The user is already authenticated - do NOT ask for phone number or identification
- You can directly help with their appointment requests
"""
        full_system_prompt = VOICE_AGENT_SYSTEM_PROMPT + user_context
        session_manager.init_conversation(session_id, full_system_prompt)
        logger.info(f"[WS {session_id}] Initialized conversation with system prompt and user context")
        
        # Initialize tool executor for this session
        tool_executor = ToolExecutor(session_id, user_id=user.id, user_name=user.name)
        logger.info(f"[WS {session_id}] Tool executor ready for user_id={user.id}")
        
        # Initialize cost tracker for this session
        cost_tracker = get_cost_tracker(session_id)

        # Initialize Deepgram streaming client (local to this connection)
        deepgram_client = DeepgramStreamingClient(
            session_id=session_id,
            on_transcript=lambda text, is_final: None,  # We'll use console logging in the service
            sample_rate=16000,
            encoding="linear16",
            channels=1,
        )
        
        # Connect to Deepgram
        connected = await deepgram_client.connect()
        if connected:
            print(f"[WS {session_id}] Deepgram streaming ready")
        else:
            print(f"[WS {session_id}] Deepgram connection failed, will log audio chunks only")

        # Send 'ready' message
        await websocket.send_text(json.dumps({
            "type": "ready",
            "session_id": session_id,
            "sample_rate": 16000,
            "deepgram_connected": connected
        }))

        # Message loop (isolated per session)
        while True:
            raw = await websocket.receive_text()
            msg: Dict = json.loads(raw)
            mtype = msg.get("type")
            msg_sid = msg.get("session_id")

            # Enforce isolation: ignore messages not matching this session
            if msg_sid != session_id:
                print(f"[WS] Ignored message for wrong session: got={msg_sid}, expected={session_id}")
                continue

            if mtype == "audio_chunk":
                chunk_num = msg.get("chunk_number")
                b64 = msg.get("data", "")
                try:
                    raw_bytes = base64.b64decode(b64)
                    
                    # Track first audio chunk to calculate STT duration
                    if audio_start_time is None:
                        audio_start_time = time.time()
                    
                    # Send to Deepgram for transcription
                    if deepgram_client and deepgram_client.is_connected:
                        await deepgram_client.send_audio(raw_bytes)
                    else:
                        # Fallback: just log the chunk info
                        print(f"[WS {session_id}] audio_chunk #{chunk_num}: bytes={len(raw_bytes)} (no Deepgram)")
                        
                except Exception as e:
                    print(f"[WS {session_id}] audio_chunk #{chunk_num}: error - {e}")

            elif mtype == "end_of_speech":
                total = msg.get("total_chunks")
                logger.info(f"[WS {session_id}] ========== End of Speech ==========")
                logger.info(f"[WS {session_id}] Total audio chunks: {total}")
                
                # Track STT audio duration
                if audio_start_time and cost_tracker:
                    audio_duration = time.time() - audio_start_time
                    cost_tracker.track_stt(audio_duration)
                    logger.info(f"[COST {session_id}] STT audio duration: {audio_duration:.2f}s")
                audio_start_time = None  # Reset for next utterance
                
                # Signal Deepgram to finish and get final transcript
                final_transcript = ""
                if deepgram_client and deepgram_client.is_connected:
                    await deepgram_client.finish_stream()
                    final_transcript = deepgram_client.get_full_transcript()
                    logger.info(f"[STT {session_id}] Transcript: '{final_transcript}'")

                # --- LLM with Tool Calling ---
                llm_response_text = ""
                should_end_call = False
                if final_transcript.strip():
                    try:
                        # Add user message to conversation history in Redis
                        logger.info(f"[CONV {session_id}] Adding user message to history")
                        session_manager.add_message(session_id, "user", final_transcript)
                        
                        # Process with LLM and execute any tool calls
                        llm_response_text, should_end_call = await _process_llm_with_tools(
                            session_id,
                            websocket,
                            tool_executor,
                            cost_tracker
                        )
                        logger.info(f"[CONV {session_id}] LLM response received, should_end_call={should_end_call}")
                        
                    except Exception as e:
                        logger.error(f"[LLM {session_id}] Error: {e}", exc_info=True)
                        llm_response_text = "I'm sorry, I had trouble processing that. Could you please repeat?"

                # Send audio response with TTS-generated audio
                response_text = llm_response_text or "I'm listening. Please continue."
                
                # Generate TTS audio
                logger.info(f"[TTS {session_id}] Synthesizing: {response_text[:80]}...")
                tts_start = time.time()
                tts_response = await synthesize_speech(response_text)
                tts_latency = (time.time() - tts_start) * 1000
                logger.info(f"[TTS {session_id}] Latency: {tts_latency:.1f}ms, Duration: {tts_response.duration_ms}ms")
                
                # Track TTS usage
                if cost_tracker:
                    cost_tracker.track_tts(len(response_text))
                
                await websocket.send_text(json.dumps({
                    "type": "audio_response",
                    "text": response_text,
                    "audio_data": tts_response.audio_base64,
                    "audio_format": "pcm_16000",  # PCM 16-bit 16kHz mono
                    "sample_rate": tts_response.sample_rate,
                    "duration_ms": tts_response.duration_ms,
                    "visemes": tts_response.visemes,
                    "user_transcript": final_transcript,
                    "should_end_call": should_end_call  # Signal frontend to trigger end_call
                }))
                
                # Reset Deepgram for next utterance - reconnect
                if deepgram_client:
                    await deepgram_client.close()
                    deepgram_client = DeepgramStreamingClient(
                        session_id=session_id,
                        sample_rate=16000,
                        encoding="linear16",
                        channels=1,
                    )
                    await deepgram_client.connect()

            elif mtype == "end_call":
                print(f"[WS {session_id}] end_call received. Generating call summary...")
                
                # --- LLM Call: Generate call summary ---
                try:
                    # Try real LLM, fall back to mock if rate limited
                    try:
                        llm = await get_llm_provider(use_mock=False)
                    except Exception:
                        llm = await get_llm_provider(use_mock=True)
                    
                    # Calculate call duration from Redis
                    call_duration = time.time() - session_manager.get_start_time(session_id)
                    user_turns = session_manager.get_user_turn_count(session_id)
                    
                    # Get conversation from Redis
                    redis_messages = session_manager.get_conversation(session_id)
                    
                    # Create summary request with different system prompt
                    summary_messages = [
                        LLMMessage(role=MessageRole.SYSTEM, content=CALL_SUMMARY_SYSTEM_PROMPT),
                        LLMMessage(
                            role=MessageRole.USER, 
                            content=f"""Please summarize this conversation:
                            
Call Duration: {call_duration:.1f} seconds
User Turns: {user_turns}

Conversation:
{_format_conversation_for_summary(redis_messages)}
"""
                        )
                    ]
                    
                    print(f"[LLM {session_id}] Generating call summary...")
                    logger.info(f"[SUMMARY {session_id}] Generating call summary...")
                    logger.info(f"[SUMMARY {session_id}] Call duration: {call_duration:.1f}s, User turns: {user_turns}")
                    try:
                        summary_response = await llm.generate(
                            messages=summary_messages,
                            temperature=0.5,  # Lower temp for more factual summary
                            max_tokens=300,
                            response_type="summary"
                        )
                        
                        # Track summary LLM usage
                        if cost_tracker and summary_response.usage:
                            cost_tracker.track_llm(
                                input_tokens=summary_response.usage.get("input_tokens", 0),
                                output_tokens=summary_response.usage.get("output_tokens", 0)
                            )
                    except Exception as e:
                        # Fall back to mock on rate limit
                        error_str = str(e)
                        if "429" in error_str or "quota" in error_str.lower():
                            print(f"[LLM {session_id}] Rate limited, using mock for summary")
                            llm = await get_llm_provider(use_mock=True)
                            summary_response = await llm.generate(
                                messages=summary_messages,
                                temperature=0.5,
                                max_tokens=300,
                                response_type="summary"
                            )
                        else:
                            raise
                    
                    logger.info(f"[SUMMARY {session_id}] === CALL SUMMARY ===")
                    logger.info(f"[SUMMARY {session_id}] {summary_response.content}")
                    logger.info(f"[SUMMARY {session_id}] Latency: {summary_response.latency_ms:.1f}ms")
                    print(f"[LLM {session_id}] === CALL SUMMARY ===")
                    print(f"{summary_response.content}")
                    print(f"[LLM {session_id}] ===================")
                    print(f"[LLM {session_id}] Summary latency: {summary_response.latency_ms:.1f}ms")
                    
                    # Get any appointments booked during this session
                    appointments_booked = tool_executor.get_session_appointments() if tool_executor else []
                    logger.info(f"[SUMMARY {session_id}] Appointments booked in session: {len(appointments_booked)}")
                    for appt in appointments_booked:
                        logger.info(f"[SUMMARY {session_id}]   - id={appt.get('id')}, date={appt.get('date')}, time={appt.get('time')}")

                    # Persist conversation summary with user reference
                    cost_breakdown = cost_tracker.get_breakdown() if cost_tracker else None
                    logger.info(f"[SUMMARY {session_id}] Persisting to DB: user_id={user.id if user else None}")
                    db = SessionLocal()
                    try:
                        db.add(models.ConversationSummary(
                            user_id=user.id if user else None,
                            session_id=session_id,
                            summary=summary_response.content,
                            appointments_discussed=json.dumps(appointments_booked) if appointments_booked else None,
                            duration_seconds=round(call_duration, 1),
                            total_cost=cost_breakdown.get("total_usd") if cost_breakdown else None,
                        ))
                        db.commit()
                        logger.info(f"[SUMMARY {session_id}] Conversation summary saved to DB")
                    except Exception as e:
                        logger.error(f"[WS {session_id}] Failed to persist conversation summary: {e}", exc_info=True)
                    finally:
                        db.close()
                    
                    # Send summary to client
                    await websocket.send_text(json.dumps({
                        "type": "call_summary",
                        "summary": summary_response.content,
                        "duration_seconds": round(call_duration, 1),
                        "total_turns": user_turns,
                        "appointments_booked": appointments_booked
                    }))
                    
                    # Send cost breakdown (bonus feature)
                    if cost_breakdown:
                        print(f"[COST {session_id}] Total: ${cost_breakdown['total_usd']:.6f}")
                        await websocket.send_text(json.dumps({
                            "type": "cost_breakdown",
                            "costs": cost_breakdown
                        }))
                    
                except Exception as e:
                    print(f"[LLM {session_id}] Summary error: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # Send a basic summary even on error
                    call_duration = time.time() - session_manager.get_start_time(session_id)
                    user_turns = session_manager.get_user_turn_count(session_id)
                    await websocket.send_text(json.dumps({
                        "type": "call_summary",
                        "summary": "Call ended. Summary generation failed due to service limits.",
                        "duration_seconds": round(call_duration, 1),
                        "total_turns": user_turns,
                        "appointments_booked": []
                    }))
                    
                    # Still send cost breakdown even if summary fails
                    if cost_tracker:
                        await websocket.send_text(json.dumps({
                            "type": "cost_breakdown",
                            "costs": cost_tracker.get_breakdown()
                        }))
                
                session_manager.set_status(session_id, "ended")
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                break

            elif mtype == "text_input":
                # Allow text input for testing (bypasses STT)
                text = msg.get("text", "").strip()
                if text:
                    print(f"[WS {session_id}] Text input: {text}")
                    
                    # Add user message to conversation
                    session_manager.add_message(session_id, "user", text)
                    
                    # Process with LLM
                    try:
                        llm_response_text, should_end_call = await _process_llm_with_tools(
                            session_id,
                            websocket,
                            tool_executor,
                            cost_tracker
                        )
                        
                        # Generate TTS audio
                        tts_response = await synthesize_speech(llm_response_text)
                        
                        # Track TTS usage
                        if cost_tracker:
                            cost_tracker.track_tts(len(llm_response_text))
                        
                        await websocket.send_text(json.dumps({
                            "type": "audio_response",
                            "text": llm_response_text,
                            "audio_data": tts_response.audio_base64,
                            "audio_format": "pcm_16000",
                            "sample_rate": tts_response.sample_rate,
                            "duration_ms": tts_response.duration_ms,
                            "visemes": tts_response.visemes,
                            "user_transcript": text,
                            "should_end_call": should_end_call
                        }))
                    except Exception as e:
                        print(f"[LLM {session_id}] Error: {e}")
                        await websocket.send_text(json.dumps({
                            "type": "audio_response",
                            "text": "I'm sorry, I had trouble processing that.",
                            "audio_data": "",
                            "audio_format": "pcm_16000",
                            "sample_rate": 16000,
                            "duration_ms": 0,
                            "visemes": [],
                            "user_transcript": text,
                            "should_end_call": False
                        }))

            else:
                print(f"[WS {session_id}] Unknown message type: {mtype}")

    except WebSocketDisconnect:
        print(f"[WS {session_id}] client disconnected")
    except Exception as e:
        print(f"[WS {session_id}] error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        # Clean up Deepgram client (local to this connection)
        if deepgram_client:
            try:
                await deepgram_client.close()
                print(f"[WS {session_id}] Deepgram client closed")
            except Exception as e:
                print(f"[WS {session_id}] Error closing Deepgram: {e}")
        
        # Clean up session data in Redis
        if session_id:
            session_manager.set_ws_active(session_id, False)
            session_manager.set_status(session_id, "closed")
            # remove() also clears conversation history from Redis
            session_manager.remove(session_id)
            print(f"[WS] session cleaned up: {session_id}")
