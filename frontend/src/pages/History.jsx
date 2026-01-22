import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api, { authAPI } from '../services/api'
import './History.css'

function History({ setIsAuthenticated }) {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('appointments')

  useEffect(() => {
    const userData = localStorage.getItem('user')
    if (userData) {
      setUser(JSON.parse(userData))
    }
    fetchHistory()
  }, [])

  const fetchHistory = async () => {
    try {
      setLoading(true)
      const response = await api.get('/api/tavus/history')
      setHistory(response.data)
    } catch (err) {
      console.error('Failed to fetch history:', err)
      setError('Failed to load history')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    authAPI.logout()
    setIsAuthenticated(false)
    navigate('/login')
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A'
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  }

  const formatTime = (timeStr) => {
    if (!timeStr) return 'N/A'
    const [hours, minutes] = timeStr.split(':')
    const hour = parseInt(hours)
    const ampm = hour >= 12 ? 'PM' : 'AM'
    const hour12 = hour % 12 || 12
    return `${hour12}:${minutes} ${ampm}`
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'scheduled': return 'status-scheduled'
      case 'completed': return 'status-completed'
      case 'cancelled': return 'status-cancelled'
      default: return ''
    }
  }

  // Show all appointments sorted by date (newest first)
  const appointmentsToShow = [...(history?.appointments || [])]
    .sort((a, b) => {
      const dateDiff = new Date(b.date || 0) - new Date(a.date || 0)
      if (dateDiff !== 0) return dateDiff
      return (b.time || '').localeCompare(a.time || '')
    })

  return (
    <div className="history-page">
      <header className="dashboard-header">
        <h1 className="dashboard-title">🎙️ Voice AI Agent</h1>
        <nav className="nav-links">
          <Link to="/dashboard" className="nav-link">Dashboard</Link>
          <Link to="/tavus" className="nav-link">Video Call</Link>
          <Link to="/history" className="nav-link active">History</Link>
        </nav>
        <div className="dashboard-user">
          {user && (
            <div className="user-info">
              <div className="user-name">{user.name || 'User'}</div>
              <div className="user-contact">{user.contact_number}</div>
            </div>
          )}
          <button className="btn btn-logout" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      <div className="history-content">
        <div className="history-header">
          <h2>📋 Your History</h2>
          <p>View your past appointments and conversations</p>
        </div>

        {loading ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading history...</p>
          </div>
        ) : error ? (
          <div className="error-state">
            <span>⚠️</span>
            <p>{error}</p>
            <button className="btn btn-primary" onClick={fetchHistory}>Retry</button>
          </div>
        ) : (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-icon">📅</span>
                <div className="stat-info">
                  <span className="stat-value">{history?.total_appointments || 0}</span>
                  <span className="stat-label">Total Appointments</span>
                </div>
              </div>
              <div className="stat-card">
                <span className="stat-icon">💬</span>
                <div className="stat-info">
                  <span className="stat-value">{history?.total_conversations || 0}</span>
                  <span className="stat-label">Conversations</span>
                </div>
              </div>
              <div className="stat-card">
                <span className="stat-icon">✅</span>
                <div className="stat-info">
                  <span className="stat-value">
                    {history?.appointments?.filter(a => a.status === 'scheduled').length || 0}
                  </span>
                  <span className="stat-label">Upcoming</span>
                </div>
              </div>
            </div>

            <div className="tabs">
              <button 
                className={`tab ${activeTab === 'appointments' ? 'active' : ''}`}
                onClick={() => setActiveTab('appointments')}
              >
                📅 Appointments
              </button>
              <button 
                className={`tab ${activeTab === 'conversations' ? 'active' : ''}`}
                onClick={() => setActiveTab('conversations')}
              >
                💬 Conversations
              </button>
            </div>

            <div className="tab-content">
              {activeTab === 'appointments' ? (
                <div className="appointments-list">
                  {appointmentsToShow.length > 0 ? (
                    appointmentsToShow.map((appt) => (
                      <div key={appt.id} className="history-card appointment-card">
                        <div className="card-header">
                          <span className={`status-badge ${getStatusColor(appt.status)}`}>
                            {appt.status}
                          </span>
                          <span className="card-date">{formatDate(appt.date)}</span>
                        </div>
                        <div className="card-body">
                          <div className="appointment-time">
                            <span className="time-icon">🕐</span>
                            <span>{formatTime(appt.time)}</span>
                          </div>
                          {appt.purpose && (
                            <div className="appointment-purpose">
                              <span className="purpose-icon">📝</span>
                              <span>{appt.purpose}</span>
                            </div>
                          )}
                        </div>
                        <div className="card-footer">
                          <span className="created-at">Created: {formatDate(appt.created_at)}</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">
                      <span className="empty-icon">📅</span>
                      <p>No appointments yet</p>
                      <Link to="/tavus" className="btn btn-primary">Book Your First Appointment</Link>
                    </div>
                  )}
                </div>
              ) : (
                <div className="conversations-list">
                  {history?.conversations?.length > 0 ? (
                    history.conversations.map((conv) => (
                      <div key={conv.id} className="history-card conversation-card">
                        <div className="card-header">
                          <span className="conv-icon">💬</span>
                          <span className="card-date">{formatDate(conv.created_at)}</span>
                        </div>
                        <div className="card-body">
                          <p className="conversation-summary">{conv.summary}</p>
                          {conv.appointments_discussed && (
                            <div className="conv-detail">
                              <span>📅</span>
                              <span>Discussed: {conv.appointments_discussed}</span>
                            </div>
                          )}
                          <div className="conv-stats">
                            {conv.duration_seconds && (
                              <span className="conv-stat">
                                ⏱️ {Math.round(conv.duration_seconds / 60)} min
                              </span>
                            )}
                            {conv.total_cost && (
                              <span className="conv-stat">
                                💰 ${conv.total_cost.toFixed(2)}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">
                      <span className="empty-icon">💬</span>
                      <p>No conversations yet</p>
                      <Link to="/tavus" className="btn btn-primary">Start Your First Call</Link>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default History
