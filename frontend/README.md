# AI Voice Agent - Frontend

React + Vite frontend for the AI Voice Agent application.

## 🏗️ Architecture

- **Framework**: React 18
- **Build Tool**: Vite 5
- **Styling**: CSS
- **HTTP Client**: Axios
- **Server**: Nginx (production)

## 📋 Prerequisites

- Node.js 20+ and npm
- Docker and Docker Compose (optional)

## 🚀 Quick Start

### Using Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone <your-frontend-repo-url>
cd voiceai-frontend

# 2. Configure environment
cp .env.example .env
# Edit .env and set VITE_API_URL to your backend URL

# 3. Start development server (with HMR)
docker-compose up

# Frontend will be available at:
# http://localhost:3000
```

**📖 For detailed development workflow, see [DEVELOPMENT.md](DEVELOPMENT.md)**

The development setup uses Vite HMR with bind mounts, so code changes appear instantly in your browser!

### Local Development (Without Docker)

```bash
# 1. Install dependencies
npm install

# 2. Configure environment
cp .env.example .env
# Edit .env and set VITE_API_URL

# 3. Start development server
npm run dev

# Frontend will be available at:
# http://localhost:3000
```

## 📁 Project Structure

```
frontend/
├── src/
│   ├── main.jsx           # Application entry point
│   ├── App.jsx            # Main App component
│   ├── App.css            # App styles
│   └── index.css          # Global styles
├── public/                # Static assets
├── index.html            # HTML template
├── vite.config.js        # Vite configuration
├── package.json          # Dependencies
├── Dockerfile            # Production build (Nginx)
├── Dockerfile.dev        # Development build
├── nginx.conf            # Nginx configuration
├── docker-compose.yml    # Docker services config
└── .env.example         # Environment variables template
```

## 🔧 Available Scripts

```bash
# Development server with hot reload
npm run dev

# Build for production
npm run build

# Preview production build locally
npm run preview

# Run linter
npm run lint
```

## 🐳 Docker Commands

### Development Mode
```bash
# Start development server
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Production Mode
```bash
# Build and run production container with Nginx
docker-compose --profile production up --build frontend-prod

# Or build directly
docker build -t voiceai-frontend .
docker run -p 80:80 voiceai-frontend
```

## ⚙️ Environment Variables

Create a `.env` file in the root directory:

```env
# Backend API URL
VITE_API_URL=http://localhost:8000
```

**Note**: Environment variables in Vite must be prefixed with `VITE_` to be exposed to the client.

### For Production
Update `VITE_API_URL` to your production backend URL:
```env
VITE_API_URL=https://api.yourapp.com
```

## 🎨 Features

- ✅ Health check integration with backend
- ✅ Responsive design
- ✅ Modern React 18 with hooks
- ✅ Fast HMR with Vite
- ✅ Production-ready Nginx configuration
- 🔄 Voice agent interface (coming soon)
- 🔄 Avatar integration (coming soon)
- 🔄 Real-time conversation UI (coming soon)

## 🚢 Production Deployment

### Using Docker (Recommended)

1. **Build production image:**
```bash
docker build -t voiceai-frontend:latest .
```

2. **Run container:**
```bash
docker run -p 80:80 voiceai-frontend:latest
```

### Using Netlify/Vercel

1. **Install Netlify/Vercel CLI:**
```bash
npm install -g netlify-cli
# or
npm install -g vercel
```

2. **Build project:**
```bash
npm run build
```

3. **Deploy:**
```bash
netlify deploy --prod
# or
vercel --prod
```

4. **Configure environment variables:**
   - Set `VITE_API_URL` to your backend API URL
   - Configure in Netlify/Vercel dashboard

### Manual Deployment

1. **Build:**
```bash
npm run build
```

2. **Deploy `dist/` folder** to your hosting service

3. **Configure web server** to serve SPA correctly (all routes → index.html)

## 🔌 Backend Integration

The frontend expects the backend API to be available at the URL specified in `VITE_API_URL`.

### API Endpoints Used
- `GET /health` - Health check
- `POST /api/appointments` - Create appointment
- `GET /api/appointments` - Get appointments
- More endpoints will be added as features are implemented

### CORS Configuration
Ensure your backend has CORS configured to allow requests from your frontend domain:

```python
# In backend/app/core/config.py
ALLOWED_ORIGINS = [
    "http://localhost:3000",  # Development
    "https://yourapp.com",    # Production
]
```

## 📝 Next Steps

- [ ] Implement voice call interface
- [ ] Integrate LiveKit Web SDK
- [ ] Add avatar display component
- [ ] Create tool call visualization
- [ ] Add conversation summary display
- [ ] Implement real-time transcription display
- [ ] Add appointment booking UI
- [ ] Create cost tracking display
- [ ] Add error handling and loading states
