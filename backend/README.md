# AI Voice Agent - Backend

FastAPI-based backend for the AI Voice Agent application with PostgreSQL and Redis.

## 🏗️ Architecture

- **Framework**: FastAPI
- **Database**: PostgreSQL 16
- **Cache**: Redis 7
- **ORM**: SQLAlchemy
- **API Docs**: Auto-generated Swagger/OpenAPI

## 📋 Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (for local development)

## 🚀 Quick Start

### Using Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone <your-backend-repo-url>
cd voiceai-backend

# 2. Configure environment
cp .env.example .env
# Edit .env and add your API keys

# 3. Start all services (with hot reload)
docker-compose up

# Backend will be available at:
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

**📖 For detailed development workflow, see [DEVELOPMENT.md](DEVELOPMENT.md)**

The development setup uses bind mounts and auto-reload, so you can edit code and see changes immediately without rebuilding!

### Stop Services

```bash
docker-compose down

# Remove volumes as well (clears database)
docker-compose down -v
```

## 🔧 Local Development (Without Docker)

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# 4. Ensure PostgreSQL and Redis are running
# Update DATABASE_URL and REDIS_URL in .env accordingly

# 5. Run development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 📁 Project Structure

```
backend/
├── app/
│   ├── api/                 # API routes
│   │   ├── health.py       # Health check endpoint
│   │   └── appointments.py # Appointment endpoints
│   ├── core/               # Core configuration
│   │   └── config.py       # Settings and config
│   ├── db/                 # Database
│   │   ├── database.py     # DB connection
│   │   └── models.py       # SQLAlchemy models
│   └── schemas/            # Pydantic schemas
│       └── schemas.py      # Request/response models
├── main.py                 # FastAPI app entry point
├── requirements.txt        # Python dependencies
├── Dockerfile             # Production Docker image
├── docker-compose.yml     # Docker services config
└── .env.example          # Environment variables template
```

## 🔌 API Endpoints

### Health Check
- `GET /health` - Check service health and Redis connectivity

### Appointments
- `POST /api/appointments` - Create new appointment
- `GET /api/appointments` - Get all appointments (with optional user filter)
- `GET /api/appointments/{id}` - Get specific appointment
- `PUT /api/appointments/{id}` - Update appointment
- `DELETE /api/appointments/{id}` - Cancel appointment

Full API documentation: http://localhost:8000/docs

## 🗄️ Database Schema

### Users Table
```sql
- id: INTEGER (Primary Key)
- contact_number: STRING (Unique, Indexed)
- name: STRING (Optional)
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### Appointments Table
```sql
- id: INTEGER (Primary Key)
- user_contact: STRING (Indexed)
- appointment_date: STRING
- appointment_time: STRING
- status: STRING (scheduled/cancelled/completed)
- notes: STRING (Optional)
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### Conversation Summaries Table
```sql
- id: INTEGER (Primary Key)
- user_contact: STRING (Optional, Indexed)
- summary: STRING
- appointments_discussed: STRING (Optional)
- user_preferences: STRING (Optional)
- created_at: TIMESTAMP
```

## ⚙️ Environment Variables

Required variables in `.env`:

```env
# Database
DATABASE_URL=postgresql://voiceai:voiceai123@postgres:5432/voiceai_db

# Redis
REDIS_URL=redis://redis:6379

# API Keys
DEEPGRAM_API_KEY=your_deepgram_api_key
CARTESIA_API_KEY=your_cartesia_api_key
GEMINI_API_KEY=your_gemini_api_key
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:80
```

## 🐳 Docker Commands

```bash
# Build and start
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down

# Access PostgreSQL
docker exec -it voiceai-postgres psql -U voiceai -d voiceai_db

# Access Redis CLI
docker exec -it voiceai-redis redis-cli
```

## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests (to be implemented)
pytest
```

## 📊 Database Management

### Using psql
```bash
docker exec -it voiceai-postgres psql -U voiceai -d voiceai_db
```

### Using GUI Tools
- **Tool**: pgAdmin, DBeaver, or TablePlus
- **Host**: localhost
- **Port**: 5432
- **Database**: voiceai_db
- **Username**: voiceai
- **Password**: voiceai123

## 🚢 Production Deployment

### Docker Build
```bash
docker build -t voiceai-backend:latest .
docker run -p 8000:8000 --env-file .env voiceai-backend:latest
```

### Environment Configuration
1. Set strong database passwords
2. Configure all API keys
3. Update ALLOWED_ORIGINS for production domains
4. Use managed PostgreSQL and Redis services
5. Enable HTTPS/SSL

## 🔐 Security Notes

- Never commit `.env` file
- Use strong passwords in production
- Keep API keys secure
- Enable rate limiting for production
- Use HTTPS in production

## 📝 Next Steps

- [ ] Integrate LiveKit Agents
- [ ] Add Deepgram speech-to-text
- [ ] Add Cartesia text-to-speech
- [ ] Implement conversation management
- [ ] Add tool calling functionality
- [ ] Create conversation summary generation
- [ ] Implement cost tracking
- [ ] Add authentication/authorization
- [ ] Add comprehensive tests
