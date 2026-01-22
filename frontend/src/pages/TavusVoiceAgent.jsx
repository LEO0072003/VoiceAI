import { useState, useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'
import './TavusVoiceAgent.css'

// API endpoint for Tavus
const TAVUS_START_ENDPOINT = '/api/tavus/start'

// Call states
const CALL_STATES = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  ACTIVE: 'active',
  ENDED: 'ended',
  ERROR: 'error'
}

function TavusVoiceAgent() {
  const [callState, setCallState] = useState(CALL_STATES.IDLE)
  const [conversationUrl, setConversationUrl] = useState(null)
  const [conversationId, setConversationId] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [callSummary, setCallSummary] = useState(null)
  const [costBreakdown, setCostBreakdown] = useState(null)
  
  const iframeRef = useRef(null)
  const dailyCallRef = useRef(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (dailyCallRef.current) {
        dailyCallRef.current.destroy()
      }
    }
  }, [])

  // Start a new Tavus conversation
  const startCall = useCallback(async () => {
    try {
      setError('')
      setIsLoading(true)
      setCallState(CALL_STATES.CONNECTING)

      // Call backend to create Tavus conversation
      const response = await api.post(TAVUS_START_ENDPOINT)
      
      if (response.data.success) {
        setConversationUrl(response.data.conversation_url)
        setConversationId(response.data.conversation_id)
        setCallState(CALL_STATES.ACTIVE)
      } else {
        throw new Error(response.data.detail || 'Failed to start conversation')
      }
    } catch (err) {
      console.error('[Tavus] Start call error:', err)
      setError(err.response?.data?.detail || err.message || 'Failed to start call')
      setCallState(CALL_STATES.ERROR)
    } finally {
      setIsLoading(false)
    }
  }, [])

  // End the call
  const endCall = useCallback(async () => {
    try {
      if (conversationId) {
        const response = await api.post(`/api/tavus/conversations/${conversationId}/end`)
        if (response.data.summary) {
          setCallSummary(response.data.summary)
        }
        if (response.data.cost_breakdown) {
          setCostBreakdown(response.data.cost_breakdown)
        }
      }
    } catch (err) {
      console.error('[Tavus] End call error:', err)
    } finally {
      setConversationUrl(null)
      setConversationId(null)
      setCallState(CALL_STATES.ENDED)
    }
  }, [conversationId])

  // Reset to start a new call
  const resetCall = useCallback(() => {
    setConversationUrl(null)
    setConversationId(null)
    setError('')
    setCallSummary(null)
    setCostBreakdown(null)
    setCallState(CALL_STATES.IDLE)
  }, [])

  // Render the appropriate content based on call state
  const renderContent = () => {
    switch (callState) {
      case CALL_STATES.IDLE:
        return (
          <div className="tavus-start-screen">
            <div className="tavus-avatar-placeholder">
              <div className="avatar-icon">🤖</div>
              <div className="avatar-glow"></div>
            </div>
            <h2>AI Appointment Assistant</h2>
            <p>Start a video call with your AI assistant to book, view, or manage appointments.</p>
            <button 
              className="btn-primary" 
              onClick={startCall}
              disabled={isLoading}
            >
              <span className="btn-icon">📹</span>
              Start Video Call
            </button>
            <p className="powered-by">Powered by Tavus AI</p>
          </div>
        )

      case CALL_STATES.CONNECTING:
        return (
          <div className="tavus-connecting">
            <div className="connecting-spinner"></div>
            <h2>Connecting...</h2>
            <p>Setting up your AI assistant...</p>
          </div>
        )

      case CALL_STATES.ACTIVE:
        return (
          <div className="tavus-call-active">
            {conversationUrl && (
              <iframe
                ref={iframeRef}
                src={conversationUrl}
                className="tavus-iframe"
                allow="camera; microphone; autoplay; display-capture"
                title="Tavus AI Conversation"
              />
            )}
            <div className="call-controls">
              <button className="btn-danger" onClick={endCall}>
                <span className="btn-icon">📵</span>
                End Call
              </button>
            </div>
          </div>
        )

      case CALL_STATES.ENDED:
        return (
          <div className="tavus-ended">
            <div className="ended-icon">✅</div>
            <h2>Call Ended</h2>
            
            {/* Call Summary */}
            {callSummary && (
              <div className="call-summary-card">
                <h3>📋 Call Summary</h3>
                <div className="summary-details">
                  {/* LLM Generated Summary */}
                  {callSummary.llm_summary && (
                    <div className="llm-summary">
                      <p className="summary-text">{callSummary.llm_summary}</p>
                    </div>
                  )}
                  
                  {/* Actions Taken */}
                  {callSummary.actions_taken && callSummary.actions_taken.length > 0 && (
                    <div className="summary-section">
                      <h4>✅ Actions Taken</h4>
                      <ul>
                        {callSummary.actions_taken.map((action, idx) => (
                          <li key={idx}>{action}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* Appointments Discussed */}
                  {callSummary.appointments_discussed && callSummary.appointments_discussed.length > 0 && (
                    <div className="summary-section">
                      <h4>📅 Appointments Discussed</h4>
                      <ul>
                        {callSummary.appointments_discussed.map((appt, idx) => (
                          <li key={idx}>{typeof appt === 'string' ? appt : JSON.stringify(appt)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* User Preferences */}
                  {callSummary.user_preferences && callSummary.user_preferences.length > 0 && (
                    <div className="summary-section">
                      <h4>⭐ User Preferences</h4>
                      <ul>
                        {callSummary.user_preferences.map((pref, idx) => (
                          <li key={idx}>{pref}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* Session Info */}
                  <div className="session-info">
                    <p><strong>Duration:</strong> {callSummary.duration_minutes?.toFixed(1) || '0'} minute(s)</p>
                    {callSummary.sentiment && (
                      <p><strong>Sentiment:</strong> {callSummary.sentiment === 'positive' ? '😊' : callSummary.sentiment === 'negative' ? '😔' : '😐'} {callSummary.sentiment}</p>
                    )}
                  </div>
                </div>
              </div>
            )}
            
            {/* Cost Breakdown */}
            {costBreakdown && (
              <div className="cost-breakdown-card">
                <h3>💰 Cost Breakdown</h3>
                <div className="cost-items">
                  {/* LLM Costs */}
                  {costBreakdown.llm && (
                    <div className="cost-item">
                      <span className="cost-label">🤖 {costBreakdown.llm.provider} ({costBreakdown.llm.model})</span>
                      <span className="cost-value">${costBreakdown.llm.cost_usd?.toFixed(6) || '0.000000'}</span>
                      <span className="cost-unit">{costBreakdown.llm.total_tokens || 0} tokens</span>
                    </div>
                  )}
                  {/* Tavus Costs */}
                  {costBreakdown.tavus && (
                    <div className="cost-item">
                      <span className="cost-label">🎥 {costBreakdown.tavus.provider} ({costBreakdown.tavus.service})</span>
                      <span className="cost-value">${costBreakdown.tavus.cost_usd?.toFixed(4) || '0.0000'}</span>
                      <span className="cost-unit">{costBreakdown.tavus.duration_minutes?.toFixed(1) || '0'} min</span>
                    </div>
                  )}
                  {/* Legacy format support */}
                  {costBreakdown.tavus_cvi && (
                    <div className="cost-item">
                      <span className="cost-label">{costBreakdown.tavus_cvi.description}</span>
                      <span className="cost-value">${costBreakdown.tavus_cvi.cost?.toFixed(4) || '0.0000'}</span>
                      <span className="cost-unit">{costBreakdown.tavus_cvi.unit}</span>
                    </div>
                  )}
                  <div className="cost-total">
                    <span>Total</span>
                    <span className="total-value">${costBreakdown.total_usd?.toFixed(4) || '0.0000'}</span>
                  </div>
                </div>
              </div>
            )}
            
            <p className="thank-you">Thank you for using AI Appointment Assistant!</p>
            <button className="btn-primary" onClick={resetCall}>
              <span className="btn-icon">🔄</span>
              Start New Call
            </button>
          </div>
        )

      case CALL_STATES.ERROR:
        return (
          <div className="tavus-error">
            <div className="error-icon">⚠️</div>
            <h2>Connection Error</h2>
            <p>{error || 'Unable to connect. Please try again.'}</p>
            <button className="btn-primary" onClick={resetCall}>
              <span className="btn-icon">🔄</span>
              Try Again
            </button>
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="tavus-voice-agent">
      <header className="tavus-header">
        <div className="tavus-header-content">
          <h1>🎙️ AI Voice Agent</h1>
          <nav className="nav-links">
            <Link to="/dashboard" className="nav-link">Dashboard</Link>
            <Link to="/tavus" className="nav-link active">Video Call</Link>
            <Link to="/history" className="nav-link">History</Link>
          </nav>
        </div>
        <p>Book appointments with natural conversation</p>
      </header>

      <main className="tavus-main">
        {renderContent()}
      </main>

      <footer className="tavus-footer">
        <div className="features">
          <span>📅 Book Appointments</span>
          <span>📋 View Schedule</span>
          <span>✏️ Modify Bookings</span>
          <span>❌ Cancel Anytime</span>
        </div>
      </footer>
    </div>
  )
}

export default TavusVoiceAgent
