import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Flag to prevent multiple refresh attempts
let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

// Add token to requests if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 errors with token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    
    // If error is 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't try to refresh if we're on auth endpoints
      if (originalRequest.url?.includes('/api/auth/login') || 
          originalRequest.url?.includes('/api/auth/register') ||
          originalRequest.url?.includes('/api/auth/refresh')) {
        return Promise.reject(error)
      }
      
      if (isRefreshing) {
        // If already refreshing, queue this request
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(token => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        }).catch(err => {
          return Promise.reject(err)
        })
      }
      
      originalRequest._retry = true
      isRefreshing = true
      
      const refreshToken = localStorage.getItem('refreshToken')
      
      if (!refreshToken) {
        // No refresh token, redirect to login
        isRefreshing = false
        localStorage.removeItem('token')
        localStorage.removeItem('refreshToken')
        localStorage.removeItem('user')
        window.location.href = '/login'
        return Promise.reject(error)
      }
      
      try {
        // Try to refresh the token
        const response = await axios.post(`${API_URL}/api/auth/refresh`, {
          refresh_token: refreshToken
        })
        
        const { access_token, refresh_token: newRefreshToken } = response.data
        
        // Store new tokens
        localStorage.setItem('token', access_token)
        localStorage.setItem('refreshToken', newRefreshToken)
        
        // Update the authorization header
        api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
        originalRequest.headers.Authorization = `Bearer ${access_token}`
        
        processQueue(null, access_token)
        
        return api(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        
        // Refresh failed, clear storage and redirect to login
        localStorage.removeItem('token')
        localStorage.removeItem('refreshToken')
        localStorage.removeItem('user')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }
    
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export const authAPI = {
  register: async (data) => {
    const response = await api.post('/api/auth/register', data)
    return response.data
  },

  login: async (data) => {
    const response = await api.post('/api/auth/login', data)
    if (response.data.access_token) {
      localStorage.setItem('token', response.data.access_token)
    }
    if (response.data.refresh_token) {
      localStorage.setItem('refreshToken', response.data.refresh_token)
    }
    return response.data
  },

  refreshToken: async () => {
    const refreshToken = localStorage.getItem('refreshToken')
    if (!refreshToken) {
      throw new Error('No refresh token available')
    }
    
    const response = await api.post('/api/auth/refresh', {
      refresh_token: refreshToken
    })
    
    if (response.data.access_token) {
      localStorage.setItem('token', response.data.access_token)
    }
    if (response.data.refresh_token) {
      localStorage.setItem('refreshToken', response.data.refresh_token)
    }
    
    return response.data
  },

  getCurrentUser: async () => {
    const response = await api.get('/api/auth/me')
    localStorage.setItem('user', JSON.stringify(response.data))
    return response.data
  },

  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('user')
  },
}

export default api
