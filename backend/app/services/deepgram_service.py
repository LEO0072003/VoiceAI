"""
Deepgram Streaming STT Service
Handles real-time speech-to-text conversion using Deepgram's WebSocket API
"""
import asyncio
import json
import os
from typing import Callable, Optional
import websockets
from app.core.config import settings


class DeepgramStreamingClient:
    """
    Manages a streaming connection to Deepgram for real-time transcription.
    Includes audio buffering for cost optimization.
    """
    
    DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
    
    # Buffer settings for cost optimization
    # At 16kHz 16-bit mono = 32KB/sec
    # 200ms worth of audio = ~6.4KB
    BUFFER_SIZE_BYTES = 16384  # ~500ms of audio - send in larger batches
    BUFFER_TIMEOUT_MS = 500    # Max wait before flushing buffer
    
    def __init__(
        self,
        session_id: str,
        on_transcript: Optional[Callable[[str, bool], None]] = None,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        channels: int = 1,
        language: str = "en-US",
    ):
        self.session_id = session_id
        self.on_transcript = on_transcript
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.channels = channels
        self.language = language
        
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._buffer_task: Optional[asyncio.Task] = None
        self._is_connected = False
        self._full_transcript = ""
        
        # Audio buffer for batching
        self._audio_buffer = bytearray()
        self._buffer_lock = asyncio.Lock()
        self._last_send_time = 0.0
        
    @property
    def api_key(self) -> str:
        """Get Deepgram API key from settings or environment"""
        key = settings.DEEPGRAM_API_KEY or os.getenv("DEEPGRAM_API_KEY", "")
        return key
    
    def _build_url(self) -> str:
        """Build the Deepgram WebSocket URL with query parameters"""
        params = [
            f"encoding={self.encoding}",
            f"sample_rate={self.sample_rate}",
            f"channels={self.channels}",
            f"language={self.language}",
            "model=nova-2",
            "punctuate=true",
            "interim_results=true",
            "endpointing=300",  # 300ms silence triggers endpoint
            "vad_events=true",  # Get speech start/end events
        ]
        return f"{self.DEEPGRAM_WS_URL}?{'&'.join(params)}"
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection to Deepgram.
        Returns True if successful, False otherwise.
        """
        if not self.api_key:
            print(f"[Deepgram {self.session_id}] ERROR: No API key configured")
            return False
        
        try:
            url = self._build_url()
            headers = {"Authorization": f"Token {self.api_key}"}
            
            print(f"[Deepgram {self.session_id}] Connecting to Deepgram...")
            
            self._ws = await websockets.connect(
                url,
                extra_headers=headers
            )
            self._is_connected = True
            self._last_send_time = asyncio.get_event_loop().time()
            
            # Start the receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            # Start buffer flush task
            self._buffer_task = asyncio.create_task(self._buffer_flush_loop())
            
            print(f"[Deepgram {self.session_id}] Connected successfully")
            return True
            
        except Exception as e:
            print(f"[Deepgram {self.session_id}] Connection failed: {e}")
            self._is_connected = False
            return False
    
    async def _receive_loop(self):
        """
        Background task that receives transcription results from Deepgram.
        """
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                
                data = json.loads(message)
                await self._handle_message(data)
                
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[Deepgram {self.session_id}] Connection closed: {e}")
        except Exception as e:
            print(f"[Deepgram {self.session_id}] Receive error: {e}")
        finally:
            self._is_connected = False
    
    async def _handle_message(self, data: dict):
        """
        Handle incoming Deepgram messages.
        """
        msg_type = data.get("type")
        
        if msg_type == "Results":
            channel = data.get("channel", {})
            alternatives = channel.get("alternatives", [])
            
            if alternatives:
                transcript = alternatives[0].get("transcript", "")
                is_final = data.get("is_final", False)
                speech_final = data.get("speech_final", False)
                
                if transcript:
                    # Print to console
                    status = "FINAL" if is_final else "INTERIM"
                    print(f"[Deepgram {self.session_id}] [{status}] {transcript}")
                    
                    # Update full transcript on final results
                    if is_final:
                        self._full_transcript += transcript + " "
                    
                    # Call the callback if provided
                    if self.on_transcript:
                        self.on_transcript(transcript, is_final)
                        
        elif msg_type == "Metadata":
            print(f"[Deepgram {self.session_id}] Metadata received: request_id={data.get('request_id')}")
            
        elif msg_type == "UtteranceEnd":
            print(f"[Deepgram {self.session_id}] Utterance ended")
            
        elif msg_type == "SpeechStarted":
            print(f"[Deepgram {self.session_id}] Speech started")
            
        elif msg_type == "Error":
            print(f"[Deepgram {self.session_id}] Error: {data}")
    
    async def _buffer_flush_loop(self):
        """
        Periodically flush the audio buffer if it hasn't been sent.
        This ensures we don't hold audio too long even if buffer isn't full.
        """
        try:
            while self._is_connected:
                await asyncio.sleep(self.BUFFER_TIMEOUT_MS / 1000.0)
                await self._flush_buffer()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Deepgram {self.session_id}] Buffer flush error: {e}")
    
    async def _flush_buffer(self):
        """Send buffered audio to Deepgram"""
        async with self._buffer_lock:
            if len(self._audio_buffer) > 0 and self._is_connected and self._ws:
                try:
                    await self._ws.send(bytes(self._audio_buffer))
                    self._last_send_time = asyncio.get_event_loop().time()
                    self._audio_buffer.clear()
                except Exception as e:
                    print(f"[Deepgram {self.session_id}] Flush error: {e}")
    
    async def send_audio(self, audio_bytes: bytes):
        """
        Buffer audio data and send to Deepgram when buffer is full.
        This reduces the number of WebSocket sends for cost optimization.
        Audio should be raw PCM bytes (16-bit, mono, 16kHz).
        """
        if not self._is_connected or not self._ws:
            return
        
        async with self._buffer_lock:
            self._audio_buffer.extend(audio_bytes)
            
            # Send when buffer reaches threshold
            if len(self._audio_buffer) >= self.BUFFER_SIZE_BYTES:
                try:
                    await self._ws.send(bytes(self._audio_buffer))
                    self._last_send_time = asyncio.get_event_loop().time()
                    self._audio_buffer.clear()
                except Exception as e:
                    print(f"[Deepgram {self.session_id}] Send error: {e}")
    
    async def finish_stream(self):
        """
        Signal to Deepgram that we're done sending audio.
        This triggers final transcription results.
        """
        if not self._is_connected or not self._ws:
            return
        
        try:
            # Flush any remaining buffered audio first
            await self._flush_buffer()
            
            # Send close stream message
            await self._ws.send(json.dumps({"type": "CloseStream"}))
            print(f"[Deepgram {self.session_id}] Sent CloseStream")
            
            # Wait a bit for final results
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[Deepgram {self.session_id}] Finish error: {e}")
    
    async def close(self):
        """
        Close the Deepgram connection and cleanup.
        """
        self._is_connected = False
        
        # Cancel buffer flush task
        if self._buffer_task:
            self._buffer_task.cancel()
            try:
                await self._buffer_task
            except asyncio.CancelledError:
                pass
            self._buffer_task = None
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        
        # Clear buffer
        self._audio_buffer.clear()
        
        print(f"[Deepgram {self.session_id}] Connection closed")
    
    def get_full_transcript(self) -> str:
        """
        Get the accumulated full transcript from final results.
        """
        return self._full_transcript.strip()
    
    @property
    def is_connected(self) -> bool:
        return self._is_connected
