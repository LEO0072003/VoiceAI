# VoiceAI Deployment Guide

## Quick Start

### Prerequisites
- EC2 instance (Ubuntu 22.04 or Amazon Linux 2023 recommended)
- At least 2GB RAM, 20GB storage
- Security group with ports 80, 443, and 22 open
- GitHub repository with your code
- GitHub Personal Access Token with repo access

### One-Line Deploy

```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/voiceai/main/deploy.sh | bash -s -- --full
```

Or download and run manually:

```bash
# Download the script
wget https://raw.githubusercontent.com/YOUR_USERNAME/voiceai/main/deploy.sh
chmod +x deploy.sh

# Run full deployment
./deploy.sh --full
```

## Deployment Options

### Interactive Mode
```bash
./deploy.sh
```
This shows a menu with options to deploy, update, restart, etc.

### Command Line Options
```bash
./deploy.sh --full      # Fresh installation
./deploy.sh --update    # Pull latest and redeploy
./deploy.sh --restart   # Restart all containers
./deploy.sh --stop      # Stop all containers
./deploy.sh --status    # Show container status
./deploy.sh --logs      # Follow container logs
./deploy.sh --help      # Show help
```

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              EC2 Instance               │
                    │                                         │
    Internet ──────►│  ┌─────────────────────────────────┐   │
        :80/:443    │  │           Nginx                  │   │
                    │  │     (Reverse Proxy)              │   │
                    │  └─────────┬───────────┬───────────┘   │
                    │            │           │               │
                    │      /api/*│           │/*             │
                    │            ▼           ▼               │
                    │  ┌─────────────┐ ┌─────────────┐      │
                    │  │   Backend   │ │  Frontend   │      │
                    │  │  (FastAPI)  │ │   (React)   │      │
                    │  │   :8000     │ │    :80      │      │
                    │  └──────┬──────┘ └─────────────┘      │
                    │         │                              │
                    │    ┌────┴────┐                        │
                    │    ▼         ▼                        │
                    │  ┌─────┐  ┌─────┐                     │
                    │  │ DB  │  │Redis│                     │
                    │  └─────┘  └─────┘                     │
                    └─────────────────────────────────────────┘
```

## Environment Variables

Create a `.env` file in the project root:

```bash
# Database
POSTGRES_USER=voiceai
POSTGRES_PASSWORD=secure-password
POSTGRES_DB=voiceai_db

# API Keys
GROQ_API_KEY=your-groq-key
TAVUS_API_KEY=your-tavus-key
TAVUS_REPLICA_ID=your-replica-id
TAVUS_PERSONA_ID=your-persona-id

# Application
PUBLIC_URL=https://your-domain.com
JWT_SECRET=$(openssl rand -hex 32)
NODE_ENV=production
```

## SSL/HTTPS Setup

### Option 1: Let's Encrypt (Recommended)

```bash
# Install certbot
sudo apt install certbot

# Get certificate
sudo certbot certonly --standalone -d your-domain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./nginx/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ./nginx/ssl/
```

Then uncomment the SSL sections in `nginx/nginx.prod.conf`.

### Option 2: AWS Certificate Manager
Use an Application Load Balancer with ACM certificate in front of your EC2.

## Common Operations

### View Logs
```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f nginx
```

### Database Access
```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U voiceai -d voiceai_db
```

### Restart Specific Service
```bash
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml restart nginx
```

### Clean Up
```bash
# Remove stopped containers and unused images
docker system prune -a

# Remove volumes (WARNING: deletes data)
docker volume prune
```

## Troubleshooting

### Containers not starting
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs

# Check if ports are in use
sudo lsof -i :80
sudo lsof -i :443
```

### Database connection issues
```bash
# Check if postgres is healthy
docker compose -f docker-compose.prod.yml ps postgres

# Check database logs
docker compose -f docker-compose.prod.yml logs postgres
```

### API not responding
```bash
# Check backend health
curl http://localhost:8000/health

# Check backend logs
docker compose -f docker-compose.prod.yml logs backend
```

## Security Recommendations

1. **Change default passwords** in `.env`
2. **Use HTTPS** - Set up SSL certificates
3. **Firewall** - Only open required ports (80, 443, 22)
4. **Regular updates** - Keep Docker and system packages updated
5. **Backup** - Set up regular database backups

## Backup Database

```bash
# Create backup
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U voiceai voiceai_db > backup_$(date +%Y%m%d).sql

# Restore backup
cat backup.sql | docker compose -f docker-compose.prod.yml exec -T postgres psql -U voiceai voiceai_db
```
