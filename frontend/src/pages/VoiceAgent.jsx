import { useState, useRef, useEffect, useCallback } from 'react'
import api from '../services/api'
import Avatar from '../components/Avatar'
import './VoiceAgent.css'

// API Endpoints
const API_ENDPOINTS = {
  INITIATE_CALL: '/api/voice/initiate',
  WEBSOCKET: '/ws/voice'
}

const CALL_STATES = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  LISTENING: 'listening',
  PROCESSING: 'processing',
  TOOL_CALLING: 'tool_calling',
  SHOWING_RESULT: 'showing_result',  // New state: showing tool result with audio
  PLAYING_RESPONSE: 'playing_response',
  ENDED: 'ended'
}

// Friendly messages for tool calls
const TOOL_MESSAGES = {
  identify_user: { icon: '🔐', message: 'Identifying you...', success: 'User identified!' },
  fetch_slots: { icon: '📅', message: 'Fetching available slots...', success: 'Found available slots!' },
  book_appointment: { icon: '✅', message: 'Booking your appointment...', success: 'Appointment booked!' },
  retrieve_appointments: { icon: '📋', message: 'Retrieving your appointments...', success: 'Appointments retrieved!' },
  cancel_appointment: { icon: '❌', message: 'Cancelling appointment...', success: 'Appointment cancelled!' },
  modify_appointment: { icon: '✏️', message: 'Modifying appointment...', success: 'Appointment modified!' },
  end_conversation: { icon: '👋', message: 'Ending conversation...', success: 'Goodbye!' }
}

// Map call states to avatar states
const getAvatarState = (callState) => {
  switch (callState) {
    case CALL_STATES.LISTENING:
      return 'listening'
    case CALL_STATES.PROCESSING:
    case CALL_STATES.TOOL_CALLING:
    case CALL_STATES.CONNECTING:
      return 'thinking'
    case CALL_STATES.PLAYING_RESPONSE:
    case CALL_STATES.SHOWING_RESULT:
      return 'speaking'
    case CALL_STATES.ENDED:
      return 'ended'
    case CALL_STATES.IDLE:
    default:
      return 'idle'
  }
}

function VoiceAgent() {
  const [callState, setCallState] = useState(CALL_STATES.IDLE)
  const [sessionId, setSessionId] = useState(null)
  const [currentTool, setCurrentTool] = useState(null)
  const [toolResult, setToolResult] = useState(null)
  const [messages, setMessages] = useState([])
  const [error, setError] = useState('')
  const [audioLevel, setAudioLevel] = useState(0)
  const [showHistory, setShowHistory] = useState(false)
  const [callSummary, setCallSummary] = useState(null)
  const [costBreakdown, setCostBreakdown] = useState(null)
  const [currentTranscript, setCurrentTranscript] = useState('')
  const [aiResponse, setAiResponse] = useState('')
  const [persistedToolResult, setPersistedToolResult] = useState(null) // Keep result visible during audio
  const [currentVisemes, setCurrentVisemes] = useState([])
  const [isAudioPlaying, setIsAudioPlaying] = useState(false)

  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const processorRef = useRef(null)
  const streamRef = useRef(null)
  const websocketRef = useRef(null)
  const chunkNumberRef = useRef(0)
  const silenceTimerRef = useRef(null)
  const audioPlayerRef = useRef(null)
  const isListeningRef = useRef(false)
  const sessionIdRef = useRef(null)
  const hasSpokenRef = useRef(false)
  const currentToolRef = useRef(null)
  const persistedToolResultRef = useRef(null)

  useEffect(() => {
    return () => {
      cleanup()
    }
  }, [])

  const cleanup = useCallback(() => {
    console.log('[Cleanup] Cleaning up resources')
    isListeningRef.current = false
    
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (websocketRef.current) {
      websocketRef.current.close()
      websocketRef.current = null
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause()
      audioPlayerRef.current = null
    }
  }, [])

  const initiateCall = async () => {
    try {
      setError('')
      setCallState(CALL_STATES.CONNECTING)
      setMessages([])
      setCurrentTool(null)
      setToolResult(null)
      setPersistedToolResult(null)
      setCallSummary(null)
      setCostBreakdown(null)
      setShowHistory(false)
      setCurrentTranscript('')
      setAiResponse('')
      
      console.log('[Call] Initiating call...')
      const response = await api.post(API_ENDPOINTS.INITIATE_CALL)
      const { 
        session_id, 
        greeting_text,
        greeting_audio_data,
        greeting_sample_rate,
        greeting_visemes
      } = response.data
      
      setSessionId(session_id)
      sessionIdRef.current = session_id
      console.log('[Call] Session created:', session_id)
      
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        text: greeting_text,
        timestamp: new Date()
      }])
      
      setAiResponse(greeting_text)
      
      await setupWebSocket(session_id)
      await setupMicrophone()
      
      setCallState(CALL_STATES.PLAYING_RESPONSE)
      
      if (greeting_audio_data) {
        await playPCMAudio(greeting_audio_data, greeting_sample_rate || 16000, greeting_visemes || [])
      }
      
      startListening()
      
    } catch (err) {
      console.error('[Call] Error initiating call:', err)
      setError(err.response?.data?.detail || 'Failed to initiate call. Please try again.')
      setCallState(CALL_STATES.IDLE)
      cleanup()
    }
  }

  const setupWebSocket = (session_id) => {
    return new Promise((resolve, reject) => {
      const wsUrl = `${import.meta.env.VITE_WS_URL || 'ws://localhost:8000'}${API_ENDPOINTS.WEBSOCKET}`
      console.log('[WS] Connecting to:', wsUrl)
      
      websocketRef.current = new WebSocket(wsUrl)

      websocketRef.current.onopen = () => {
        console.log('[WS] Connected, sending auth...')
        websocketRef.current.send(JSON.stringify({
          type: 'auth',
          token: localStorage.getItem('token'),
          session_id: session_id
        }))
        resolve()
      }

      websocketRef.current.onmessage = async (event) => {
        const data = JSON.parse(event.data)
        console.log('[WS] Message received:', data.type)
        await handleWebSocketMessage(data)
      }

      websocketRef.current.onerror = (error) => {
        console.error('[WS] Error:', error)
        setError('Connection error. Please try again.')
        reject(error)
      }

      websocketRef.current.onclose = (event) => {
        console.log('[WS] Disconnected:', event.code, event.reason)
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop())
          streamRef.current = null
        }
        if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
          audioContextRef.current.close()
          audioContextRef.current = null
        }
      }
    })
  }

  const handleWebSocketMessage = async (data) => {
    switch (data.type) {
      case 'ready':
        console.log('[WS] Server ready')
        break
        
      case 'tool_call':
        setCallState(CALL_STATES.TOOL_CALLING)
        const newTool = {
          name: data.tool,
          arguments: data.arguments || {},
          status: 'in_progress'
        }
        setCurrentTool(newTool)
        currentToolRef.current = newTool
        setToolResult(null)
        setPersistedToolResult(null)
        persistedToolResultRef.current = null
        break
        
      case 'tool_result':
        setCurrentTool(prev => {
          const updated = prev ? { ...prev, status: 'completed' } : null
          currentToolRef.current = updated
          return updated
        })
        setToolResult(data.result)
        
        // Persist the result to show during audio playback
        if (data.result && (data.result.available_slots || data.result.upcoming || 
            data.result.appointment_id || data.result.contact_number)) {
          const persisted = { tool: data.tool, result: data.result }
          setPersistedToolResult(persisted)
          persistedToolResultRef.current = persisted
        }
        
        // Add to messages for history
        setMessages(prev => [...prev, {
          id: Date.now(),
          role: 'tool',
          tool: data.tool,
          result: data.result,
          timestamp: new Date()
        }])
        break
        
      case 'audio_response':
        stopListening()
        
        // Check if we have a persisted tool result using ref
        if (persistedToolResultRef.current) {
          setCallState(CALL_STATES.SHOWING_RESULT)
        } else {
          setCallState(CALL_STATES.PLAYING_RESPONSE)
        }
        
        if (data.user_transcript) {
          setCurrentTranscript(data.user_transcript)
          setMessages(prev => {
            const updated = [...prev]
            const lastUserIdx = updated.findLastIndex(m => m.role === 'user')
            if (lastUserIdx >= 0 && updated[lastUserIdx].text === '(Processing...)') {
              updated[lastUserIdx].text = data.user_transcript
            }
            return updated
          })
        }
        
        if (data.text) {
          setAiResponse(data.text)
          setMessages(prev => [...prev, {
            id: Date.now(),
            role: 'assistant',
            text: data.text,
            timestamp: new Date()
          }])
        }
        
        // Check if backend says we should end the call
        const shouldEndCall = data.should_end_call === true
        
        try {
          if (data.audio_data) {
            await playPCMAudio(data.audio_data, data.sample_rate || 16000, data.visemes || [])
          }
          
          // After audio finishes
          if (shouldEndCall) {
            // Automatically trigger end_call to get summary
            console.log('[Audio] should_end_call=true - triggering end_call')
            setCallState(CALL_STATES.PROCESSING)
            // Clear tool state
            setCurrentTool(null)
            currentToolRef.current = null
            setToolResult(null)
            setPersistedToolResult(null)
            persistedToolResultRef.current = null
            
            // Send end_call to backend
            if (websocketRef.current?.readyState === WebSocket.OPEN) {
              websocketRef.current.send(JSON.stringify({
                type: 'end_call',
                session_id: sessionIdRef.current
              }))
            }
          } else {
            setPersistedToolResult(null)
            persistedToolResultRef.current = null
            setCurrentTool(null)
            currentToolRef.current = null
            setToolResult(null)
            startListening()
          }
        } catch (err) {
          console.error('[Audio] Playback failed:', err)
          if (!shouldEndCall) {
            setPersistedToolResult(null)
            persistedToolResultRef.current = null
            setCurrentTool(null)
            currentToolRef.current = null
            setToolResult(null)
            startListening()
          }
        }
        break
        
      case 'call_summary':
        setCallSummary({
          text: data.summary,
          duration: data.duration_seconds,
          turns: data.total_turns
        })
        // Immediately show ended state when summary arrives
        stopListening()
        break
        
      case 'cost_breakdown':
        setCostBreakdown(data.costs)
        setCallState(CALL_STATES.ENDED)
        // Full cleanup
        stopListening()
        cleanup()
        break
        
      case 'error':
        setError(data.message)
        break
        
      default:
        console.log('[WS] Unknown message type:', data.type)
    }
  }

  const setupMicrophone = async () => {
    try {
      console.log('[Mic] Requesting microphone access...')
      
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        }
      })
      
      streamRef.current = stream
      
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000
      })
      
      if (audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume()
      }
      
      const source = audioContextRef.current.createMediaStreamSource(stream)
      
      analyserRef.current = audioContextRef.current.createAnalyser()
      analyserRef.current.fftSize = 2048
      source.connect(analyserRef.current)
      
      processorRef.current = audioContextRef.current.createScriptProcessor(4096, 1, 1)
      source.connect(processorRef.current)
      processorRef.current.connect(audioContextRef.current.destination)
      
      console.log('[Mic] Setup complete')
      
    } catch (err) {
      console.error('[Mic] Error:', err)
      setError('Could not access microphone. Please grant permission.')
      throw err
    }
  }

  const startListening = useCallback(() => {
    console.log('[Listen] Starting to listen...')
    setCallState(CALL_STATES.LISTENING)
    isListeningRef.current = true
    chunkNumberRef.current = 0
    hasSpokenRef.current = false
    setCurrentTranscript('')
    setAiResponse('')
    // Don't clear tool results here - let the audio_response handler manage them
    
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    
    if (!processorRef.current) {
      console.error('[Listen] No processor available')
      return
    }
    
    processorRef.current.onaudioprocess = (e) => {
      if (!isListeningRef.current) return
      
      const inputData = e.inputBuffer.getChannelData(0)
      
      let sum = 0
      for (let i = 0; i < inputData.length; i++) {
        sum += inputData[i] * inputData[i]
      }
      const rms = Math.sqrt(sum / inputData.length)
      const level = Math.min(100, Math.floor(rms * 1000))
      setAudioLevel(level)
      
      const SILENCE_THRESHOLD = 0.01
      const SILENCE_DURATION = 1500
      const SPEECH_THRESHOLD = 0.02
      
      if (rms >= SPEECH_THRESHOLD) {
        hasSpokenRef.current = true
      }
      
      if (rms < SILENCE_THRESHOLD && hasSpokenRef.current) {
        if (!silenceTimerRef.current) {
          silenceTimerRef.current = setTimeout(() => {
            if (isListeningRef.current && hasSpokenRef.current) {
              console.log('[VAD] Silence detected after speech')
              endOfSpeech()
            }
          }, SILENCE_DURATION)
        }
      } else if (rms >= SILENCE_THRESHOLD) {
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current)
          silenceTimerRef.current = null
        }
      }
      
      const int16Data = new Int16Array(inputData.length)
      for (let i = 0; i < inputData.length; i++) {
        int16Data[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7fff
      }
      
      if (websocketRef.current?.readyState === WebSocket.OPEN) {
        const chunk = {
          type: 'audio_chunk',
          session_id: sessionIdRef.current,
          chunk_number: chunkNumberRef.current++,
          data: btoa(String.fromCharCode(...new Uint8Array(int16Data.buffer))),
          is_final: false
        }
        websocketRef.current.send(JSON.stringify(chunk))
      }
    }
  }, [])

  const stopListening = useCallback(() => {
    console.log('[Listen] Stopping...')
    isListeningRef.current = false
    
    if (processorRef.current) {
      processorRef.current.onaudioprocess = null
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    setAudioLevel(0)
  }, [])

  const endOfSpeech = useCallback(() => {
    console.log('[Speech] End of speech detected')
    stopListening()
    setCallState(CALL_STATES.PROCESSING)
    
    setMessages(prev => [...prev, {
      id: Date.now(),
      role: 'user',
      text: '(Processing...)',
      timestamp: new Date()
    }])
    
    if (websocketRef.current?.readyState === WebSocket.OPEN) {
      websocketRef.current.send(JSON.stringify({
        type: 'end_of_speech',
        session_id: sessionIdRef.current,
        total_chunks: chunkNumberRef.current
      }))
    }
  }, [stopListening])

  const playPCMAudio = (base64Data, sampleRate = 16000, visemes = []) => {
    return new Promise((resolve) => {
      console.log('[Audio] Playing PCM audio')
      
      if (!base64Data) {
        resolve()
        return
      }
      
      try {
        // Set visemes for avatar lip sync
        setCurrentVisemes(visemes || [])
        setIsAudioPlaying(true)
        
        const binaryString = atob(base64Data)
        const bytes = new Uint8Array(binaryString.length)
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i)
        }
        
        const int16Data = new Int16Array(bytes.buffer)
        const float32Data = new Float32Array(int16Data.length)
        for (let i = 0; i < int16Data.length; i++) {
          float32Data[i] = int16Data[i] / 32768.0
        }
        
        const playbackContext = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: sampleRate
        })
        
        const audioBuffer = playbackContext.createBuffer(1, float32Data.length, sampleRate)
        audioBuffer.copyToChannel(float32Data, 0)
        
        const source = playbackContext.createBufferSource()
        source.buffer = audioBuffer
        source.connect(playbackContext.destination)
        
        source.onended = () => {
          setIsAudioPlaying(false)
          setCurrentVisemes([])
          playbackContext.close()
          resolve()
        }
        
        source.start(0)
        
      } catch (err) {
        console.error('[Audio] PCM playback error:', err)
        setIsAudioPlaying(false)
        setCurrentVisemes([])
        resolve()
      }
    })
  }

  const endCall = useCallback(() => {
    console.log('[Call] Ending call...')
    stopListening()
    setCallState(CALL_STATES.PROCESSING)
    
    if (websocketRef.current?.readyState === WebSocket.OPEN) {
      websocketRef.current.send(JSON.stringify({
        type: 'end_call',
        session_id: sessionIdRef.current
      }))
    } else {
      setCallState(CALL_STATES.ENDED)
      cleanup()
    }
  }, [stopListening, cleanup])

  const newCall = () => {
    setCallState(CALL_STATES.IDLE)
    setCurrentTool(null)
    setToolResult(null)
    setPersistedToolResult(null)
    setMessages([])
    setError('')
    setSessionId(null)
    setCallSummary(null)
    setCostBreakdown(null)
    setShowHistory(false)
    sessionIdRef.current = null
  }

  // Get current status display
  const getStatusDisplay = () => {
    switch (callState) {
      case CALL_STATES.IDLE:
        return { icon: '📞', text: 'Ready to start', subtext: 'Click the button below to begin' }
      case CALL_STATES.CONNECTING:
        return { icon: '🔄', text: 'Connecting...', subtext: 'Setting up your call' }
      case CALL_STATES.LISTENING:
        return { icon: '🎤', text: 'Listening...', subtext: 'Speak now' }
      case CALL_STATES.PROCESSING:
        return { icon: '⏳', text: 'Processing...', subtext: 'Understanding your request' }
      case CALL_STATES.TOOL_CALLING:
        if (currentTool) {
          const toolInfo = TOOL_MESSAGES[currentTool.name] || { icon: '🔧', message: 'Processing...' }
          return { icon: toolInfo.icon, text: toolInfo.message, subtext: '' }
        }
        return { icon: '⚙️', text: 'Processing...', subtext: '' }
      case CALL_STATES.SHOWING_RESULT:
        return { icon: '🔊', text: 'Here\'s what I found...', subtext: '' }
      case CALL_STATES.PLAYING_RESPONSE:
        return { icon: '🔊', text: 'Speaking...', subtext: '' }
      case CALL_STATES.ENDED:
        return { icon: '✅', text: 'Call Ended', subtext: 'View your summary below' }
      default:
        return { icon: '📞', text: 'Ready', subtext: '' }
    }
  }

  const status = getStatusDisplay()

  const renderToolBanner = () => {
    const displayTool = persistedToolResult?.tool || currentTool?.name
    if (!displayTool) return null
    const toolInfo = TOOL_MESSAGES[displayTool] || { icon: '🔧', message: 'Working...' }
    const isDone = persistedToolResult && !currentTool
    return (
      <div className={`tool-banner ${isDone ? 'done' : 'active'}`}>
        <span className="tool-icon">{toolInfo.icon}</span>
        <div className="tool-text">
          <div className="tool-title">{displayTool.replace('_', ' ')}</div>
          <div className="tool-message">{isDone ? (toolInfo.success || 'Completed') : toolInfo.message}</div>
        </div>
        {!isDone && <div className="tool-spinner" aria-label="tool in progress" />}
      </div>
    )
  }

  // Render available slots if tool result has them
  const renderToolResult = () => {
    // Use persisted result during audio playback, or current result during tool_calling
    const displayResult = persistedToolResult?.result || toolResult
    const displayTool = persistedToolResult?.tool || currentTool?.name
    
    if (!displayResult) return null
    
    if (displayResult.available_slots && displayResult.available_slots.length > 0) {
      return (
        <div className="slots-display">
          <h4>📅 Available Slots for {displayResult.date_display || displayResult.date}</h4>
          <div className="slots-grid">
            {displayResult.available_slots.map(slot => (
              <div key={slot} className="slot-chip">
                {slot}
              </div>
            ))}
          </div>
        </div>
      )
    }
    
    if (displayResult.appointment_id && displayResult.success) {
      return (
        <div className="booking-confirmation">
          <div className="confirmation-icon">✅</div>
          <h4>Appointment Booked!</h4>
          <p>{displayResult.date_display || displayResult.date} at {displayResult.time}</p>
          {displayResult.purpose && <p className="purpose">Purpose: {displayResult.purpose}</p>}
        </div>
      )
    }
    
    if (displayResult.upcoming && displayResult.upcoming.length > 0) {
      return (
        <div className="appointments-display">
          <h4>📋 Your Upcoming Appointments</h4>
          <div className="appointments-list">
            {displayResult.upcoming.map(appt => (
              <div key={appt.id} className="appointment-item">
                <span className="appt-date">{appt.date}</span>
                <span className="appt-time">{appt.time}</span>
                <span className="appt-status">{appt.status}</span>
              </div>
            ))}
          </div>
        </div>
      )
    }
    
    if (displayResult.contact_number && displayTool === 'identify_user') {
      return (
        <div className="user-identified">
          <div className="confirmation-icon">🔐</div>
          <p>Identified as: <strong>{displayResult.contact_number}</strong></p>
          {displayResult.existing_appointments_count > 0 && (
            <p className="existing-appts">You have {displayResult.existing_appointments_count} existing appointment(s)</p>
          )}
        </div>
      )
    }
    
    return null
  }

  // Render call summary at the end
  const renderEndScreen = () => {
    if (callState !== CALL_STATES.ENDED) return null
    
    return (
      <div className="end-screen">
        <div className="summary-section">
          <h3>📋 Call Summary</h3>
          {callSummary ? (
            <div className="summary-content">
              <p>{callSummary.text}</p>
              <div className="summary-stats">
                <span>⏱️ Duration: {Math.round(callSummary.duration)}s</span>
                <span>💬 Turns: {callSummary.turns}</span>
              </div>
            </div>
          ) : (
            <p className="loading-text">Loading summary...</p>
          )}
        </div>
        
        {costBreakdown && (
          <div className="cost-section">
            <h3>💰 Cost Breakdown</h3>
            <div className="cost-items">
              <div className="cost-item">
                <span className="cost-label">🎤 STT ({costBreakdown.stt?.provider || 'Deepgram'})</span>
                <span className="cost-detail">{costBreakdown.stt?.audio_seconds?.toFixed(1) || 0}s</span>
                <span className="cost-value">${costBreakdown.stt?.cost_usd?.toFixed(6) || '0.000000'}</span>
              </div>
              <div className="cost-item">
                <span className="cost-label">🤖 LLM ({costBreakdown.llm?.provider || 'Groq'})</span>
                <span className="cost-detail">{costBreakdown.llm?.total_tokens || 0} tokens</span>
                <span className="cost-value">${costBreakdown.llm?.cost_usd?.toFixed(6) || '0.000000'}</span>
              </div>
              <div className="cost-item">
                <span className="cost-label">🔊 TTS ({costBreakdown.tts?.provider || 'Cartesia'})</span>
                <span className="cost-detail">{costBreakdown.tts?.characters || 0} chars</span>
                <span className="cost-value">${costBreakdown.tts?.cost_usd?.toFixed(6) || '0.000000'}</span>
              </div>
              <div className="cost-item cost-total">
                <span className="cost-label">Total</span>
                <span className="cost-detail"></span>
                <span className="cost-value">${costBreakdown.total_usd?.toFixed(6) || '0.000000'}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="voice-agent">
      {/* Header */}
      <header className="voice-header">
        <h1 className="voice-title">🎙️ Voice AI Agent</h1>
        <p className="voice-subtitle">Book appointments with natural conversation</p>
      </header>

      <div className="voice-main">
        {/* Main Dynamic Card */}
        <div className="dynamic-card">
          {/* Avatar Component */}
          <Avatar 
            state={getAvatarState(callState)}
            visemes={currentVisemes}
            audioLevel={audioLevel}
            isPlaying={isAudioPlaying}
          />

          {/* Status Text */}
          <div className="status-display">
            <h2 className="status-text">{status.text}</h2>
            {status.subtext && <p className="status-subtext">{status.subtext}</p>}
          </div>

          {/* Tool call banner (prompt requirement: always surface tool activity) */}
          {renderToolBanner()}

          {/* Audio Level Bar (when listening) */}
          {callState === CALL_STATES.LISTENING && (
            <div className="audio-visualizer">
              <div className="audio-bar" style={{ height: `${Math.max(10, audioLevel)}%` }}></div>
              <div className="audio-bar" style={{ height: `${Math.max(10, audioLevel * 0.8)}%` }}></div>
              <div className="audio-bar" style={{ height: `${Math.max(10, audioLevel * 1.2)}%` }}></div>
              <div className="audio-bar" style={{ height: `${Math.max(10, audioLevel * 0.6)}%` }}></div>
              <div className="audio-bar" style={{ height: `${Math.max(10, audioLevel * 0.9)}%` }}></div>
            </div>
          )}

          {/* Tool Result Display - show during tool_calling, showing_result, or when we have persisted result */}
          {(callState === CALL_STATES.TOOL_CALLING || 
            callState === CALL_STATES.SHOWING_RESULT || 
            persistedToolResult) && renderToolResult()}

          {/* AI Response (when speaking without tool result) */}
          {callState === CALL_STATES.PLAYING_RESPONSE && aiResponse && !persistedToolResult && (
            <div className="ai-response-bubble">
              <p>{aiResponse}</p>
            </div>
          )}

          {/* End Screen */}
          {renderEndScreen()}

          {/* Error Display */}
          {error && (
            <div className="error-banner">
              <span>⚠️ {error}</span>
              <button onClick={() => setError('')}>×</button>
            </div>
          )}

          {/* Controls */}
          <div className="controls">
            {callState === CALL_STATES.IDLE && (
              <button className="btn-primary" onClick={initiateCall}>
                <span className="btn-icon">📞</span>
                Start Call
              </button>
            )}

            {callState === CALL_STATES.CONNECTING && (
              <button className="btn-secondary" disabled>
                <div className="btn-spinner"></div>
                Connecting...
              </button>
            )}

            {(callState === CALL_STATES.LISTENING || 
              callState === CALL_STATES.PROCESSING || 
              callState === CALL_STATES.TOOL_CALLING ||
              callState === CALL_STATES.SHOWING_RESULT ||
              callState === CALL_STATES.PLAYING_RESPONSE) && (
              <button className="btn-danger" onClick={endCall}>
                <span className="btn-icon">📵</span>
                End Call
              </button>
            )}

            {callState === CALL_STATES.ENDED && (
              <button className="btn-primary" onClick={newCall}>
                <span className="btn-icon">🔄</span>
                New Call
              </button>
            )}
          </div>
        </div>

        {/* Chat History Toggle */}
        {messages.length > 0 && callState !== CALL_STATES.IDLE && (
          <div className="history-section">
            <button 
              className="history-toggle"
              onClick={() => setShowHistory(!showHistory)}
            >
              <span>💬 Chat History ({messages.filter(m => m.role !== 'tool').length})</span>
              <span className={`toggle-arrow ${showHistory ? 'open' : ''}`}>▼</span>
            </button>
            
            {showHistory && (
              <div className="history-panel">
                {messages.filter(m => m.role !== 'tool').map(msg => (
                  <div key={msg.id} className={`history-message ${msg.role}`}>
                    <span className="msg-icon">
                      {msg.role === 'assistant' ? '🤖' : msg.role === 'system' ? '📋' : '👤'}
                    </span>
                    <div className="msg-content">
                      <span className="msg-role">
                        {msg.role === 'assistant' ? 'AI' : msg.role === 'system' ? 'System' : 'You'}
                      </span>
                      <p>{msg.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default VoiceAgent
