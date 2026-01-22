"""
Tavus API Routes
Handles Tavus CVI persona and conversation management
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import json
import redis

from app.services import tavus_service
from app.services.tavus_service import persona_manager
from app.core.config import settings
from app.core.security import get_current_user
from app.db import models
from app.db.database import SessionLocal
from app.services.tools import ToolExecutor

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis client for distributed context storage (works across multiple workers)
_redis_client = None

def get_redis_client():
    """Get Redis client for context storage"""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis_client.ping()  # Test connection
            logger.info(f"[TAVUS] Connected to Redis at {settings.REDIS_URL}")
        except Exception as e:
            logger.error(f"[TAVUS] Failed to connect to Redis: {e}")
            _redis_client = None
    return _redis_client


# =============================================================================
# Request/Response Models
# =============================================================================

class CreatePersonaRequest(BaseModel):
    name: str = "Appointment Assistant"
    replica_id: str = tavus_service.DEFAULT_REPLICA_ID
    custom_greeting: Optional[str] = None
    use_external_llm: bool = False  # If true, use Groq instead of Tavus LLM


class CreateConversationRequest(BaseModel):
    persona_id: Optional[str] = None  # If not provided, uses default persona
    conversation_name: str = "Appointment Call"
    custom_greeting: Optional[str] = None
    conversation_context: Optional[str] = None
    max_call_duration: int = 600  # 10 minutes


class ConversationResponse(BaseModel):
    conversation_id: str
    conversation_url: str
    status: str
    persona_id: str


class PersonaResponse(BaseModel):
    persona_id: str
    persona_name: str
    created_at: Optional[str] = None


# =============================================================================
# Health Check
# =============================================================================

@router.get("/health")
async def tavus_health():
    """Check if Tavus API is configured"""
    has_key = bool(settings.TAVUS_API_KEY)
    return {
        "configured": has_key,
        "status": "ready" if has_key else "missing_api_key"
    }


# =============================================================================
# Persona Management
# =============================================================================

@router.post("/personas", response_model=PersonaResponse)
async def create_persona(request: CreatePersonaRequest):
    """Create a new Tavus persona"""
    try:
        if request.use_external_llm:
            result = await tavus_service.create_persona_with_external_llm(
                name=request.name,
                replica_id=request.replica_id
            )
        else:
            result = await tavus_service.create_persona(
                name=request.name,
                replica_id=request.replica_id,
                custom_greeting=request.custom_greeting
            )
        
        return PersonaResponse(
            persona_id=result.get("persona_id", ""),
            persona_name=request.name,
            created_at=result.get("created_at")
        )
    except Exception as e:
        logger.error(f"Failed to create persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/personas")
async def list_personas():
    """List all personas"""
    try:
        return await tavus_service.list_personas()
    except Exception as e:
        logger.error(f"Failed to list personas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/personas/{persona_id}")
async def get_persona(persona_id: str):
    """Get persona by ID"""
    try:
        return await tavus_service.get_persona(persona_id)
    except Exception as e:
        logger.error(f"Failed to get persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str):
    """Delete a persona"""
    try:
        success = await tavus_service.delete_persona(persona_id)
        if success:
            return {"status": "deleted", "persona_id": persona_id}
        raise HTTPException(status_code=404, detail="Persona not found")
    except Exception as e:
        logger.error(f"Failed to delete persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Conversation Management
# =============================================================================

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(request: CreateConversationRequest):
    """
    Create a new conversation session
    
    Returns conversation_url that can be used to join the video call
    """
    try:
        # Get or create default persona if not provided
        persona_id = request.persona_id
        if not persona_id:
            persona_id = await persona_manager.get_or_create_persona()
        
        result = await tavus_service.create_conversation(
            persona_id=persona_id,
            conversation_name=request.conversation_name,
            custom_greeting=request.custom_greeting,
            conversation_context=request.conversation_context,
            max_call_duration=request.max_call_duration
        )
        
        return ConversationResponse(
            conversation_id=result.get("conversation_id", ""),
            conversation_url=result.get("conversation_url", ""),
            status=result.get("status", "active"),
            persona_id=persona_id
        )
    except Exception as e:
        logger.error(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation details"""
    try:
        return await tavus_service.get_conversation(conversation_id)
    except Exception as e:
        logger.error(f"Failed to get conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{conversation_id}/end")
async def end_conversation(conversation_id: str):
    """End an active conversation and return summary with full cost breakdown"""
    from app.services.cost_tracker import get_cost_tracker
    from app.api.llm_proxy import generate_call_summary, clear_llm_context
    
    try:
        # Get conversation details before ending
        conversation = await tavus_service.get_conversation(conversation_id)
        
        # Generate LLM summary BEFORE ending (while we still have context)
        logger.info(f"[END_CONV] Generating LLM summary for {conversation_id}")
        llm_summary = await generate_call_summary(conversation_id)
        logger.info(f"[END_CONV] Summary generated: {llm_summary.get('summary', '')[:100]}")
        
        # End the conversation
        success = await tavus_service.end_conversation(conversation_id)
        
        # Calculate duration
        from datetime import datetime
        created_at = conversation.get("created_at", "")
        duration_seconds = 120  # Default 2 min
        
        if created_at:
            try:
                start_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                duration_seconds = max(60, (datetime.now(start_time.tzinfo) - start_time).total_seconds())
            except:
                pass
        
        # Get cost tracker and update Tavus duration
        cost_tracker = get_cost_tracker(conversation_id)
        cost_tracker.track_tavus(duration_seconds)
        
        # Get full cost breakdown (includes LLM costs tracked during conversation)
        cost_breakdown = cost_tracker.get_breakdown()
        
        # Clear context after getting summary
        clear_llm_context(conversation_id)
        
        return {
            "status": "ended",
            "conversation_id": conversation_id,
            "summary": {
                "conversation_name": conversation.get("conversation_name", "Appointment Call"),
                "duration_seconds": round(duration_seconds, 2),
                "duration_minutes": round(duration_seconds / 60, 2),
                "status": "completed",
                # LLM-generated summary
                "llm_summary": llm_summary.get("summary", ""),
                "appointments_discussed": llm_summary.get("appointments_discussed", []),
                "user_preferences": llm_summary.get("user_preferences", []),
                "actions_taken": llm_summary.get("actions_taken", []),
                "sentiment": llm_summary.get("sentiment", "neutral")
            },
            "cost_breakdown": {
                "llm": {
                    "provider": cost_breakdown["llm"]["provider"],
                    "model": cost_breakdown["llm"]["model"],
                    "input_tokens": cost_breakdown["llm"]["input_tokens"],
                    "output_tokens": cost_breakdown["llm"]["output_tokens"],
                    "total_tokens": cost_breakdown["llm"]["total_tokens"],
                    "cost_usd": cost_breakdown["llm"]["cost_usd"]
                },
                "tavus": {
                    "provider": "Tavus",
                    "service": "CVI Video Avatar",
                    "duration_minutes": cost_breakdown["tavus"]["duration_minutes"],
                    "cost_usd": cost_breakdown["tavus"]["cost_usd"]
                },
                "total_usd": cost_breakdown["total_usd"]
            }
        }
    except Exception as e:
        logger.error(f"Failed to end conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{conversation_id}/save-summary")
async def save_conversation_summary(
    conversation_id: str,
    current_user: models.User = Depends(get_current_user)
):
    """
    Save conversation summary with cost to database.
    Called when conversation ends to persist the record.
    """
    from app.services.cost_tracker import get_cost_tracker
    
    try:
        # Get cost breakdown
        cost_tracker = get_cost_tracker(conversation_id)
        cost_breakdown = cost_tracker.get_breakdown()
        
        db = SessionLocal()
        try:
            # Create conversation summary record
            summary = models.ConversationSummary(
                user_id=current_user.id,
                session_id=conversation_id,
                summary=f"Video call completed",
                duration_seconds=int(cost_breakdown["tavus"]["duration_seconds"]),
                total_cost=cost_breakdown["total_usd"]
            )
            db.add(summary)
            db.commit()
            db.refresh(summary)
            
            logger.info(f"Saved conversation summary: id={summary.id}, cost=${cost_breakdown['total_usd']}")
            
            # Clear the cost tracker data from Redis
            cost_tracker.clear()
            
            return {
                "success": True,
                "summary_id": summary.id,
                "conversation_id": conversation_id,
                "duration_seconds": summary.duration_seconds,
                "total_cost_usd": summary.total_cost
            }
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Failed to save conversation summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Stock Replicas
# =============================================================================

@router.get("/replicas")
async def list_replicas():
    """List available stock replicas"""
    try:
        return await tavus_service.list_stock_replicas()
    except Exception as e:
        logger.error(f"Failed to list replicas: {e}")
        # Return hardcoded list as fallback
        return {
            "replicas": [
                {"replica_id": "rfe12d8b9597", "name": "Nathan", "gender": "male"},
                {"replica_id": "r79e1c033f", "name": "Charlie", "gender": "male"},
            ]
        }


# =============================================================================
# Quick Start - Combined endpoint for easy frontend use
# =============================================================================

@router.post("/start")
async def quick_start(current_user: models.User = Depends(get_current_user)):
    """
    Quick start endpoint - creates persona if needed and returns conversation URL
    
    This is the main endpoint the frontend should call to start a video call.
    Requires authentication - uses logged-in user's info for personalization.
    """
    try:
        # Get user info for personalized greeting
        user_name = current_user.name or "there"
        user_phone = current_user.contact_number
        user_id = current_user.id
        
        # Reset and create fresh persona to avoid stale cache issues
        persona_manager.reset()
        persona_id = await persona_manager.get_or_create_persona()
        
        # Create a personalized greeting with user context
        personalized_greeting = f"Hello {user_name}! I'm your appointment assistant. I can help you book, view, modify, or cancel appointments. What would you like to do today?"
        
        # Build callback URL for tool webhooks if backend URL is configured
        callback_url = None
        if settings.BACKEND_PUBLIC_URL:
            callback_url = f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/api/tavus/webhook/tool"
            logger.info(f"Using callback URL for tools: {callback_url}")
        
        # Create a new conversation with user context and callback
        result = await tavus_service.create_conversation(
            persona_id=persona_id,
            conversation_name=f"Appointment Call - {user_name}",
            custom_greeting=personalized_greeting,
            conversation_context={
                "user_id": user_id,
                "user_name": user_name,
                "user_phone": user_phone
            },
            callback_url=callback_url
        )
        
        # Store conversation context for webhook to use
        conversation_id = result.get("conversation_id")
        if conversation_id:
            store_conversation_context(conversation_id, user_id, user_name)
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "conversation_url": result.get("conversation_url"),
            "persona_id": persona_id,
            "user_name": user_name,
            "user_id": user_id,
            "message": "Conversation ready. Join using the conversation_url."
        }
    except Exception as e:
        logger.error(f"Quick start failed: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")


# =============================================================================
# User History
# =============================================================================

@router.get("/history")
async def get_user_history(current_user: models.User = Depends(get_current_user)):
    """
    Get conversation and appointment history for the logged-in user.
    Returns all conversation summaries and appointments.
    """
    db = SessionLocal()
    try:
        # Get conversation summaries
        summaries = db.query(models.ConversationSummary).filter(
            models.ConversationSummary.user_id == current_user.id
        ).order_by(models.ConversationSummary.created_at.desc()).all()
        
        # Get appointments
        appointments = db.query(models.Appointment).filter(
            models.Appointment.user_id == current_user.id
        ).order_by(models.Appointment.appointment_date.desc()).all()
        
        return {
            "user_id": current_user.id,
            "user_name": current_user.name,
            "conversations": [
                {
                    "id": s.id,
                    "session_id": s.session_id,
                    "summary": s.summary,
                    "appointments_discussed": s.appointments_discussed,
                    "duration_seconds": s.duration_seconds,
                    "total_cost": s.total_cost,
                    "created_at": s.created_at.isoformat() if s.created_at else None
                }
                for s in summaries
            ],
            "appointments": [
                {
                    "id": a.id,
                    "date": a.appointment_date,
                    "time": a.appointment_time,
                    "purpose": a.purpose,
                    "status": a.status,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                }
                for a in appointments
            ],
            "total_conversations": len(summaries),
            "total_appointments": len(appointments)
        }
    finally:
        db.close()


# =============================================================================
# Tavus Tool Webhook - Receives tool calls from Tavus
# =============================================================================

# Redis-based context storage (works across multiple workers/containers)
CONTEXT_TTL = 3600  # 1 hour TTL for conversation context


def store_conversation_context(conversation_id: str, user_id: int, user_name: str):
    """Store user context for a conversation in Redis so webhook can access it across workers"""
    redis_client = get_redis_client()
    if redis_client:
        try:
            context = json.dumps({
                "user_id": user_id,
                "user_name": user_name
            })
            redis_client.setex(f"tavus_context:{conversation_id}", CONTEXT_TTL, context)
            logger.info(f"[TAVUS] Stored context in Redis for conversation {conversation_id}: user_id={user_id}")
        except Exception as e:
            logger.error(f"[TAVUS] Failed to store context in Redis: {e}")
    else:
        logger.warning(f"[TAVUS] Redis not available, context will not persist across workers")


def get_conversation_context(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get user context for a conversation from Redis"""
    redis_client = get_redis_client()
    if redis_client:
        try:
            context_str = redis_client.get(f"tavus_context:{conversation_id}")
            if context_str:
                context = json.loads(context_str)
                logger.info(f"[TAVUS] Retrieved context from Redis for {conversation_id}: user_id={context.get('user_id')}")
                return context
            logger.warning(f"[TAVUS] No context found in Redis for {conversation_id}")
        except Exception as e:
            logger.error(f"[TAVUS] Failed to get context from Redis: {e}")
    return None


def clear_conversation_context(conversation_id: str):
    """Clear context when conversation ends"""
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.delete(f"tavus_context:{conversation_id}")
            logger.info(f"[TAVUS] Cleared context from Redis for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"[TAVUS] Failed to clear context from Redis: {e}")


class TavusToolCallRequest(BaseModel):
    """Request body from Tavus when it calls a tool"""
    conversation_id: str
    tool_name: str
    tool_call_id: str
    arguments: Dict[str, Any]


class TavusToolCallResponse(BaseModel):
    """Response to Tavus with tool result"""
    tool_call_id: str
    result: Dict[str, Any]


@router.post("/webhook/tool")
async def tavus_tool_webhook(request: Request):
    """
    Webhook endpoint for Tavus to call when it needs to execute a tool.
    
    Tavus sends tool call requests here, we execute them and return results.
    This allows Tavus to use our actual database for appointments.
    """
    # Parse the raw body for flexibility
    body = await request.json()
    logger.info(f"[TAVUS WEBHOOK] ========== Tool Call Received ==========")
    logger.info(f"[TAVUS WEBHOOK] Raw body: {json.dumps(body, indent=2)}")
    
    # Check for system events that aren't tool calls
    event_type = body.get("event_type", "")
    message_type = body.get("message_type", "")
    
    # Skip system events - these are not tool calls
    if event_type in ["system.replica_joined", "system.shutdown", "application.transcription_ready"]:
        logger.info(f"[TAVUS WEBHOOK] Skipping system event: {event_type}")
        return {"status": "ok", "event_type": event_type}
    
    # Extract tool call info (Tavus format may vary)
    conversation_id = body.get("conversation_id", "")
    tool_name = body.get("tool_name") or body.get("function_name") or body.get("name", "")
    tool_call_id = body.get("tool_call_id") or body.get("id", "unknown")
    arguments = body.get("arguments") or body.get("parameters") or {}
    
    # If no tool name, it's not a tool call
    if not tool_name:
        logger.info(f"[TAVUS WEBHOOK] No tool_name in request, skipping")
        return {"status": "ok", "message": "No tool to execute"}
    
    # If arguments is a string, parse it
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except:
            arguments = {}
    
    logger.info(f"[TAVUS WEBHOOK] Conversation: {conversation_id}")
    logger.info(f"[TAVUS WEBHOOK] Tool: {tool_name}")
    logger.info(f"[TAVUS WEBHOOK] Arguments: {arguments}")
    
    # Get user context for this conversation
    context = get_conversation_context(conversation_id)
    if not context:
        logger.warning(f"[TAVUS WEBHOOK] No context found for conversation {conversation_id}")
        # Try to extract from arguments or use default
        user_id = arguments.get("user_id") or body.get("user_id")
        user_name = arguments.get("user_name") or body.get("user_name") or "User"
    else:
        user_id = context.get("user_id")
        user_name = context.get("user_name", "User")
    
    logger.info(f"[TAVUS WEBHOOK] User context: user_id={user_id}, user_name={user_name}")
    
    if not user_id:
        logger.error("[TAVUS WEBHOOK] No user_id available for tool execution")
        return {
            "tool_call_id": tool_call_id,
            "result": {
                "success": False,
                "error": "User not authenticated for this conversation"
            }
        }
    
    # Create tool executor with user context
    tool_executor = ToolExecutor(
        session_id=conversation_id,
        user_id=user_id,
        user_name=user_name
    )
    
    # Execute the tool
    try:
        logger.info(f"[TAVUS WEBHOOK] Executing tool: {tool_name}")
        result = await tool_executor.execute(tool_name, arguments)
        logger.info(f"[TAVUS WEBHOOK] Tool result: {json.dumps(result, indent=2, default=str)}")
    except Exception as e:
        logger.error(f"[TAVUS WEBHOOK] Tool execution error: {e}", exc_info=True)
        result = {
            "success": False,
            "error": str(e)
        }
    
    # Return result to Tavus
    response = {
        "tool_call_id": tool_call_id,
        "result": result
    }
    logger.info(f"[TAVUS WEBHOOK] Returning response to Tavus")
    return response


@router.post("/webhook/events")
async def tavus_events_webhook(request: Request):
    """
    Webhook for Tavus conversation events (optional).
    Receives events like conversation_started, conversation_ended, etc.
    """
    body = await request.json()
    logger.info(f"[TAVUS EVENT] ========== Event Received ==========")
    logger.info(f"[TAVUS EVENT] {json.dumps(body, indent=2)}")
    
    event_type = body.get("event_type") or body.get("type", "unknown")
    conversation_id = body.get("conversation_id", "")
    
    if event_type == "conversation_ended":
        # Clean up context
        clear_conversation_context(conversation_id)
    
    return {"status": "received", "event_type": event_type}
