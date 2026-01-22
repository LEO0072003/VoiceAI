from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
from pydantic import field_validator

class Settings(BaseSettings):
    # Pydantic v2 style config - no .env to avoid JSON decoding issues
    model_config = SettingsConfigDict(
        env_file=None,
        env_ignore_empty=True,
        case_sensitive=True
    )

    PROJECT_NAME: str = "AI Voice Agent"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "postgresql://voiceai:voiceai123@postgres:5432/voiceai_db"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379"
    
    # Backend URL (for webhooks - must be publicly accessible for Tavus)
    BACKEND_PUBLIC_URL: str = ""  # e.g., "https://your-ngrok-url.ngrok.io" or your public domain
    
    # API Keys (to be configured)
    DEEPGRAM_API_KEY: str = ""
    CARTESIA_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    TAVUS_API_KEY: str = ""
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    def cors_origins(self) -> List[str]:
        raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:80")
        return [o.strip() for o in raw.split(',') if o.strip()]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Exclude dotenv_settings to avoid JSON parsing issues
        return (init_settings, env_settings, file_secret_settings)

settings = Settings()
