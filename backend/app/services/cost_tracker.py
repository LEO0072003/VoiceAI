"""
Cost Tracking Service
Tracks API usage costs for STT, LLM, and TTS services
"""
import json
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime

from app.core.redis_client import redis_client


@dataclass
class CostTracker:
    """
    Track costs for a voice session.
    Stores metrics in Redis for the session.
    
    Pricing (approximate, check actual provider pricing):
    - Deepgram STT: ~$0.0043/min (Nova-2)
    - Groq LLM: $0.59/1M input, $0.79/1M output (llama-3.3-70b-versatile)
    - Cartesia TTS: ~$0.015/1K chars
    - Tavus CVI: ~$0.35/min
    """
    session_id: str
    
    # Pricing constants (USD)
    DEEPGRAM_COST_PER_MINUTE: float = 0.0043  # Nova-2
    GROQ_COST_PER_1M_INPUT_TOKENS: float = 0.59  # llama-3.3-70b-versatile
    GROQ_COST_PER_1M_OUTPUT_TOKENS: float = 0.79  # llama-3.3-70b-versatile
    CARTESIA_COST_PER_1K_CHARS: float = 0.015
    TAVUS_COST_PER_MINUTE: float = 0.35  # CVI video avatar
    
    # Redis key prefix
    COST_KEY_PREFIX: str = "voice:costs"
    
    def _key(self) -> str:
        return f"{self.COST_KEY_PREFIX}:{self.session_id}"
    
    def _get_data(self) -> Dict:
        """Get cost data from Redis"""
        data = redis_client.get(self._key())
        if data:
            return json.loads(data)
        return {
            "stt_audio_seconds": 0,
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "tts_characters": 0,
            "tavus_seconds": 0,
            "total_requests": {
                "stt": 0,
                "llm": 0,
                "tts": 0
            },
            "started_at": datetime.utcnow().isoformat()
        }
    
    def _save_data(self, data: Dict) -> None:
        """Save cost data to Redis"""
        redis_client.set(self._key(), json.dumps(data))
        redis_client.expire(self._key(), 3600 * 24)  # 24 hour TTL
    
    def track_stt(self, audio_seconds: float) -> None:
        """Track STT usage"""
        data = self._get_data()
        data["stt_audio_seconds"] += audio_seconds
        data["total_requests"]["stt"] += 1
        self._save_data(data)
    
    def track_llm(self, input_tokens: int, output_tokens: int) -> None:
        """Track LLM usage"""
        data = self._get_data()
        data["llm_input_tokens"] += input_tokens
        data["llm_output_tokens"] += output_tokens
        data["total_requests"]["llm"] += 1
        self._save_data(data)
    
    def track_tts(self, characters: int) -> None:
        """Track TTS usage"""
        data = self._get_data()
        data["tts_characters"] += characters
        data["total_requests"]["tts"] += 1
        self._save_data(data)
    
    def track_tavus(self, seconds: float) -> None:
        """Track Tavus video duration"""
        data = self._get_data()
        data["tavus_seconds"] = seconds  # Set total, not accumulate
        self._save_data(data)
    
    def get_breakdown(self) -> Dict:
        """
        Get cost breakdown for the session.
        Returns detailed costs for each service.
        """
        data = self._get_data()
        
        # Calculate costs
        stt_minutes = data["stt_audio_seconds"] / 60
        stt_cost = stt_minutes * self.DEEPGRAM_COST_PER_MINUTE
        
        # LLM costs (per 1M tokens)
        llm_input_cost = (data["llm_input_tokens"] / 1_000_000) * self.GROQ_COST_PER_1M_INPUT_TOKENS
        llm_output_cost = (data["llm_output_tokens"] / 1_000_000) * self.GROQ_COST_PER_1M_OUTPUT_TOKENS
        llm_cost = llm_input_cost + llm_output_cost
        
        tts_cost = (data["tts_characters"] / 1000) * self.CARTESIA_COST_PER_1K_CHARS
        
        # Tavus video cost
        tavus_minutes = data.get("tavus_seconds", 0) / 60
        tavus_cost = tavus_minutes * self.TAVUS_COST_PER_MINUTE
        
        total_cost = stt_cost + llm_cost + tts_cost + tavus_cost
        
        return {
            "stt": {
                "provider": "Deepgram",
                "model": "nova-2",
                "audio_seconds": round(data["stt_audio_seconds"], 2),
                "audio_minutes": round(stt_minutes, 2),
                "requests": data["total_requests"]["stt"],
                "cost_usd": round(stt_cost, 6)
            },
            "llm": {
                "provider": "Groq",
                "model": "llama-3.3-70b-versatile",
                "input_tokens": data["llm_input_tokens"],
                "output_tokens": data["llm_output_tokens"],
                "total_tokens": data["llm_input_tokens"] + data["llm_output_tokens"],
                "requests": data["total_requests"]["llm"],
                "cost_usd": round(llm_cost, 6),
                "pricing": f"${self.GROQ_COST_PER_1M_INPUT_TOKENS}/1M in, ${self.GROQ_COST_PER_1M_OUTPUT_TOKENS}/1M out"
            },
            "tts": {
                "provider": "Cartesia",
                "model": "sonic-english",
                "characters": data["tts_characters"],
                "requests": data["total_requests"]["tts"],
                "cost_usd": round(tts_cost, 6)
            },
            "tavus": {
                "provider": "Tavus",
                "model": "CVI",
                "duration_seconds": round(data.get("tavus_seconds", 0), 2),
                "duration_minutes": round(tavus_minutes, 2),
                "cost_usd": round(tavus_cost, 6),
                "pricing": f"${self.TAVUS_COST_PER_MINUTE}/min"
            },
            "total_usd": round(total_cost, 6),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def clear(self) -> None:
        """Clear cost tracking data"""
        redis_client.delete(self._key())


def get_cost_tracker(session_id: str) -> CostTracker:
    """Factory function to get a cost tracker for a session"""
    return CostTracker(session_id=session_id)
