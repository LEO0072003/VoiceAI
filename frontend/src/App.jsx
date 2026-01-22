import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import VoiceAgent from './pages/VoiceAgent'
import TavusVoiceAgent from './pages/TavusVoiceAgent'
import History from './pages/History'
import './App.css'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check if user has valid token
    const token = localStorage.getItem('token')
    if (token) {
      setIsAuthenticated(true)
    }
    setLoading(false)
  }, [])

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
      </div>
    )
  }

  return (
    <Routes>
      <Route 
        path="/login" 
        element={
          isAuthenticated ? <Navigate to="/dashboard" /> : <Login setIsAuthenticated={setIsAuthenticated} />
        } 
      />
      <Route 
        path="/register" 
        element={
          isAuthenticated ? <Navigate to="/dashboard" /> : <Register setIsAuthenticated={setIsAuthenticated} />
        } 
      />
      <Route 
        path="/dashboard" 
        element={
          isAuthenticated ? <Dashboard setIsAuthenticated={setIsAuthenticated} /> : <Navigate to="/login" />
        } 
      />
      <Route 
        path="/voice" 
        element={
          isAuthenticated ? <VoiceAgent /> : <Navigate to="/login" />
        } 
      />
      <Route 
        path="/tavus" 
        element={
          isAuthenticated ? <TavusVoiceAgent /> : <Navigate to="/login" />
        } 
      />
      <Route 
        path="/history" 
        element={
          isAuthenticated ? <History setIsAuthenticated={setIsAuthenticated} /> : <Navigate to="/login" />
        } 
      />
      <Route path="/" element={<Navigate to="/login" />} />
    </Routes>
  )
}

export default App
