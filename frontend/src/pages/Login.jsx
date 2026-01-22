import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authAPI } from '../services/api'

function Login({ setIsAuthenticated }) {
  const navigate = useNavigate()
  const [formData, setFormData] = useState({
    contact_number: '',
    password: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    })
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await authAPI.login(formData)
      await authAPI.getCurrentUser()
      setIsAuthenticated(true)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <span className="auth-icon">🎙️</span>
          <h1>Welcome Back</h1>
          <p>Sign in to continue to Voice AI Agent</p>
        </div>

        {error && (
          <div className="error-message">
            <span>⚠️</span>
            {error}
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="contact_number">Phone Number</label>
            <input
              type="text"
              id="contact_number"
              name="contact_number"
              className="form-input"
              placeholder="+1234567890"
              value={formData.contact_number}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              name="password"
              className="form-input"
              placeholder="Enter your password"
              value={formData.password}
              onChange={handleChange}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? (
              <>
                <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }}></span>
                Signing in...
              </>
            ) : (
              <>
                <span>→</span>
                Sign In
              </>
            )}
          </button>
        </form>

        <div className="auth-footer">
          Don't have an account? <Link to="/register">Create one</Link>
        </div>
      </div>
    </div>
  )
}

export default Login
