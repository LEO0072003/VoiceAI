import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authAPI } from '../services/api'

console.log('Register component loaded')

function Register({ setIsAuthenticated }) {
  console.log('Register component rendering')
  const navigate = useNavigate()
  const [formData, setFormData] = useState({
    contact_number: '',
    name: '',
    email: '',
    password: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (e) => {
    const { name, value } = e.target
    console.log('Field changed:', name, value)
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }))
    setError('')
  }

  const handleSubmit = async (e) => {
    console.log('Form submitted')
    e.preventDefault()
    console.log('preventDefault called')
    
    setError('')
    setLoading(true)

    // Basic validation
    if (formData.password.length < 6) {
      console.log('Password too short')
      setError('Password must be at least 6 characters long')
      setLoading(false)
      return
    }

    try {
      console.log('Registering with:', formData)
      const registerRes = await authAPI.register(formData)
      console.log('Registration response:', registerRes)
      
      console.log('Auto-logging in...')
      const loginRes = await authAPI.login({
        contact_number: formData.contact_number,
        password: formData.password,
      })
      console.log('Login response:', loginRes)
      
      const userData = await authAPI.getCurrentUser()
      console.log('User data:', userData)
      
      console.log('Setting authenticated and navigating')
      setIsAuthenticated(true)
      navigate('/dashboard')
    } catch (err) {
      console.error('Full error object:', err)
      console.error('Error response:', err.response)
      console.error('Error message:', err.message)
      
      const errorMsg = err.response?.data?.detail || err.message || 'Registration failed. Please try again.'
      console.log('Setting error:', errorMsg)
      setError(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <span className="auth-icon">✨</span>
          <h1>Create Account</h1>
          <p>Start your journey with Voice AI Agent</p>
        </div>

        {error && (
          <div className="error-message">
            <span>⚠️</span>
            {error}
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="contact_number">Phone Number *</label>
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
            <label htmlFor="name">Full Name</label>
            <input
              type="text"
              id="name"
              name="name"
              className="form-input"
              placeholder="John Doe"
              value={formData.name}
              onChange={handleChange}
            />
          </div>

          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              type="email"
              id="email"
              name="email"
              className="form-input"
              placeholder="john@example.com"
              value={formData.email}
              onChange={handleChange}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password *</label>
            <input
              type="password"
              id="password"
              name="password"
              className="form-input"
              placeholder="Min 6 characters"
              value={formData.password}
              onChange={handleChange}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? (
              <>
                <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }}></span>
                Creating account...
              </>
            ) : (
              <>
                <span>✓</span>
                Create Account
              </>
            )}
          </button>
        </form>

        <div className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
      </div>
    </div>
  )
}

export default Register
