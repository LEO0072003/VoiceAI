import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import api, { authAPI } from '../services/api'

function Dashboard({ setIsAuthenticated }) {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [stats, setStats] = useState({
    appointments: 0,
    upcoming: 0,
    conversations: 0
  })
  const [loadingStats, setLoadingStats] = useState(true)

  useEffect(() => {
    const userData = localStorage.getItem('user')
    if (userData) {
      setUser(JSON.parse(userData))
    }
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const response = await api.get('/api/tavus/history')
      setStats({
        appointments: response.data.total_appointments || 0,
        upcoming: response.data.appointments?.filter(a => a.status === 'scheduled').length || 0,
        conversations: response.data.total_conversations || 0
      })
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    } finally {
      setLoadingStats(false)
    }
  }

  const handleLogout = () => {
    authAPI.logout()
    setIsAuthenticated(false)
    navigate('/login')
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1 className="dashboard-title">🎙️ Voice AI Agent</h1>
        <nav className="nav-links">
          <Link to="/dashboard" className="nav-link active">Dashboard</Link>
          <Link to="/tavus" className="nav-link">Video Call</Link>
          <Link to="/history" className="nav-link">History</Link>
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

      <div className="dashboard-content">
        <section className="welcome-section">
          <div className="welcome-icon">👋</div>
          <h2>Welcome{user?.name ? `, ${user.name}` : ''}!</h2>
          <p>
            Experience intelligent voice conversations with AI-powered appointment booking,
            natural language understanding, and real-time responses.
          </p>
        </section>

        {/* Quick Stats */}
        <div className="stats-row">
          <div className="stat-box">
            <span className="stat-number">{loadingStats ? '...' : stats.upcoming}</span>
            <span className="stat-text">Upcoming Appointments</span>
          </div>
          <div className="stat-box">
            <span className="stat-number">{loadingStats ? '...' : stats.appointments}</span>
            <span className="stat-text">Total Appointments</span>
          </div>
          <div className="stat-box">
            <span className="stat-number">{loadingStats ? '...' : stats.conversations}</span>
            <span className="stat-text">Conversations</span>
          </div>
        </div>

        <div className="feature-grid">
          <div className="feature-card highlight">
            <span className="feature-icon">📹</span>
            <h3>Tavus Video Avatar</h3>
            <p>
              AI video avatar with realistic lip-sync, face-to-face video conversations
              powered by Tavus CVI technology.
            </p>
            <Link to="/tavus" className="feature-link">Start Video Call →</Link>
          </div>

          <div className="feature-card">
            <span className="feature-icon">🎤</span>
            <h3>Voice Conversations</h3>
            <p>
              Natural voice interactions with real-time speech recognition and
              text-to-speech capabilities powered by Deepgram and Cartesia.
            </p>
            <Link to="/voice" className="feature-link">Start Voice Call →</Link>
          </div>

          <div className="feature-card">
            <span className="feature-icon">📋</span>
            <h3>View History</h3>
            <p>
              Access your complete appointment history and past conversations
              with detailed summaries and cost tracking.
            </p>
            <Link to="/history" className="feature-link">View History →</Link>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
