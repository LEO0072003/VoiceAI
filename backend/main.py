from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health, appointments, auth, voice, tavus, llm_proxy
from app.core.config import settings
from app.db.database import engine
from app.db import models
import logging
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables (won't drop existing - safe for restarts)
# Set RESET_DB=true env var to drop and recreate all tables
if os.environ.get('RESET_DB', '').lower() == 'true':
    logger.warning("RESET_DB=true - Dropping all tables and recreating fresh...")
    models.Base.metadata.drop_all(bind=engine)
    
models.Base.metadata.create_all(bind=engine)
logger.info("Database tables ready!")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI Voice Agent Backend API"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["Appointments"])
app.include_router(voice.router, tags=["Voice"])
app.include_router(tavus.router, prefix="/api/tavus", tags=["Tavus Avatar"])
app.include_router(llm_proxy.router, prefix="/api/llm", tags=["LLM Proxy for Tavus"])

@app.get("/")
async def root():
    return {
        "message": "AI Voice Agent API",
        "version": settings.VERSION,
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
