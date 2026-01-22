"""
Text-to-Speech Service using Cartesia
Converts text to natural sounding speech with optional viseme data
"""
import asyncio
import base64
import httpx
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class TTSResponse:
    """Response from TTS service"""
    audio_data: bytes  # Raw audio bytes (PCM or WAV)
    audio_base64: str  # Base64 encoded audio
    content_type: str  # MIME type (audio/wav, audio/pcm, etc.)
    duration_ms: int  # Estimated duration
    sample_rate: int  # Sample rate
    visemes: List[Dict[str, Any]]  # Viseme data for lip sync


class CartesiaTTSService:
    """
    Cartesia TTS integration for natural voice synthesis.
    
    API Docs: https://docs.cartesia.ai/
    
    Features:
    - Ultra-low latency streaming
    - Natural voices
    - Word timestamps for sync
    """
    
    BASE_URL = "https://api.cartesia.ai"
    
    # Voice IDs from Cartesia (these are example IDs - get actual ones from dashboard)
    VOICES = {
        "professional_female": "a0e99841-438c-4a64-b679-ae501e7d6091",  # Sonic English
        "friendly_male": "694f9389-aac1-45b6-b726-9d9369183238",
        "default": "a0e99841-438c-4a64-b679-ae501e7d6091",
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model: str = "sonic-english",
        output_format: str = "pcm_16000",  # or "pcm_22050", "pcm_44100"
    ):
        self.api_key = api_key or settings.CARTESIA_API_KEY
        self.voice_id = voice_id or self.VOICES["default"]
        self.model = model
        self.output_format = output_format
        self._client: Optional[httpx.AsyncClient] = None
        
        # Parse sample rate from format
        self.sample_rate = int(output_format.split("_")[1]) if "_" in output_format else 16000
        
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={
                    "X-API-Key": self.api_key,
                    "Cartesia-Version": "2024-06-10",
                    "Content-Type": "application/json",
                }
            )
        return self._client
    
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        emotion: Optional[str] = None,
    ) -> TTSResponse:
        """
        Synthesize speech from text.
        
        Args:
            text: Text to convert to speech
            voice_id: Override voice ID
            speed: Speech speed (0.5-2.0)
            emotion: Emotion modifier (optional)
            
        Returns:
            TTSResponse with audio data and metadata
        """
        if not self.api_key:
            # Return silence/mock if no API key
            return self._generate_mock_response(text)
        
        client = await self._get_client()
        
        # Build request payload
        payload = {
            "model_id": self.model,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": voice_id or self.voice_id,
            },
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": self.sample_rate,
            },
            "language": "en",
        }
        
        # Add optional speed control
        if speed != 1.0:
            payload["voice"]["__experimental_controls"] = {
                "speed": speed
            }
        
        try:
            response = await client.post(
                f"{self.BASE_URL}/tts/bytes",
                json=payload,
            )
            response.raise_for_status()
            
            audio_data = response.content
            
            # Calculate duration from audio data
            # PCM 16-bit mono: bytes / (sample_rate * 2)
            duration_s = len(audio_data) / (self.sample_rate * 2)
            duration_ms = int(duration_s * 1000)
            
            # Convert to base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Generate simple viseme data based on text
            visemes = self._generate_visemes(text, duration_ms)
            
            return TTSResponse(
                audio_data=audio_data,
                audio_base64=audio_base64,
                content_type="audio/pcm",
                duration_ms=duration_ms,
                sample_rate=self.sample_rate,
                visemes=visemes,
            )
            
        except httpx.HTTPStatusError as e:
            print(f"[TTS] Cartesia API error: {e.response.status_code} - {e.response.text}")
            return self._generate_mock_response(text)
        except Exception as e:
            print(f"[TTS] Synthesis error: {e}")
            return self._generate_mock_response(text)
    
    async def synthesize_streaming(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ):
        """
        Stream audio chunks as they're generated.
        Yields (chunk_bytes, is_final) tuples.
        """
        if not self.api_key:
            # Yield mock audio
            mock = self._generate_mock_response(text)
            yield mock.audio_data, True
            return
            
        client = await self._get_client()
        
        payload = {
            "model_id": self.model,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": voice_id or self.voice_id,
            },
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": self.sample_rate,
            },
            "language": "en",
        }
        
        try:
            async with client.stream("POST", f"{self.BASE_URL}/tts/bytes", json=payload) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk, False
                yield b"", True
        except Exception as e:
            print(f"[TTS] Streaming error: {e}")
            mock = self._generate_mock_response(text)
            yield mock.audio_data, True
    
    def _generate_mock_response(self, text: str) -> TTSResponse:
        """Generate a mock/silent audio response when TTS is unavailable"""
        # Generate 0.5s of silence per 10 words
        word_count = len(text.split())
        duration_s = max(1.0, word_count * 0.15)  # ~150ms per word
        duration_ms = int(duration_s * 1000)
        
        # Generate silent PCM (16-bit, mono)
        num_samples = int(duration_s * self.sample_rate)
        silence = bytes(num_samples * 2)  # 2 bytes per sample (16-bit)
        
        return TTSResponse(
            audio_data=silence,
            audio_base64=base64.b64encode(silence).decode('utf-8'),
            content_type="audio/pcm",
            duration_ms=duration_ms,
            sample_rate=self.sample_rate,
            visemes=self._generate_visemes(text, duration_ms),
        )
    
    def _generate_visemes(self, text: str, duration_ms: int) -> List[Dict[str, Any]]:
        """
        Generate approximate viseme data for lip sync.
        
        Viseme mapping (simplified):
        - AA, AH, AO: Open mouth
        - EE, IH: Wide mouth
        - OO, UH: Rounded mouth
        - PP, BB, MM: Closed lips
        - FF, VV: Teeth on lip
        - TH: Tongue between teeth
        - etc.
        """
        # Simple phoneme-to-viseme mapping
        CHAR_TO_VISEME = {
            'a': 'AA', 'e': 'EE', 'i': 'IH', 'o': 'OO', 'u': 'UH',
            'p': 'PP', 'b': 'PP', 'm': 'MM',
            'f': 'FF', 'v': 'FF',
            't': 'DD', 'd': 'DD', 'n': 'NN',
            's': 'SS', 'z': 'SS',
            'k': 'KK', 'g': 'KK',
            'r': 'RR', 'l': 'NN',
            'w': 'WW', 'y': 'EE',
            ' ': 'sil',
        }
        
        # Generate visemes for each character
        words = text.lower().split()
        visemes = []
        
        if not words:
            return visemes
            
        # Time per word (evenly distributed)
        time_per_word = duration_ms / len(words)
        current_time = 0
        
        for word in words:
            chars = [c for c in word if c.isalpha()]
            if not chars:
                current_time += time_per_word
                continue
                
            time_per_char = time_per_word / len(chars)
            
            for char in chars:
                viseme_id = CHAR_TO_VISEME.get(char, 'DD')
                visemes.append({
                    "id": viseme_id,
                    "start": int(current_time),
                    "end": int(current_time + time_per_char),
                })
                current_time += time_per_char
            
            # Add silence between words
            visemes.append({
                "id": "sil",
                "start": int(current_time),
                "end": int(current_time + 50),
            })
            current_time += 50
        
        return visemes
    
    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Global instance for easy access
_tts_service: Optional[CartesiaTTSService] = None


async def get_tts_service() -> CartesiaTTSService:
    """Get or create TTS service instance"""
    global _tts_service
    if _tts_service is None:
        _tts_service = CartesiaTTSService()
    return _tts_service


async def synthesize_speech(text: str) -> TTSResponse:
    """Convenience function to synthesize speech"""
    service = await get_tts_service()
    return await service.synthesize(text)
