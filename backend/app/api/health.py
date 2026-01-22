from fastapi import APIRouter
from redis import Redis
from app.core.config import settings

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    
    # Check Redis connection
    redis_status = "disconnected"
    try:
        r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        if r.ping():
            redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "redis": redis_status
    }
