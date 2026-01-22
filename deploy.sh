#!/bin/bash

#######################################
# VoiceAI Deployment Script
# For EC2 Ubuntu/Amazon Linux instances
#######################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="voiceai"
PROJECT_DIR="/opt/voiceai"
REPO_URL=""  # Will be set with token
BRANCH="main"

#######################################
# Utility Functions
#######################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_banner() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════╗"
    echo "║       VoiceAI Deployment Script          ║"
    echo "║         Backend + Frontend + Nginx       ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_command() {
    if ! command -v $1 &> /dev/null; then
        return 1
    fi
    return 0
}

#######################################
# Installation Functions
#######################################

install_docker() {
    log_info "Installing Docker..."
    
    if check_command docker; then
        log_success "Docker is already installed"
        return
    fi

    # Detect OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    fi

    case $OS in
        ubuntu|debian)
            sudo apt-get update
            sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
            curl -fsSL https://download.docker.com/linux/$OS/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/$OS $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo apt-get update
            sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
            ;;
        amzn|rhel|centos)
            sudo yum install -y yum-utils
            sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
            sudo systemctl start docker
            sudo systemctl enable docker
            ;;
        *)
            log_error "Unsupported OS: $OS"
            exit 1
            ;;
    esac

    # Add current user to docker group
    sudo usermod -aG docker $USER
    log_success "Docker installed successfully"
}

install_git() {
    log_info "Checking Git installation..."
    
    if check_command git; then
        log_success "Git is already installed"
        return
    fi

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    fi

    case $OS in
        ubuntu|debian)
            sudo apt-get update
            sudo apt-get install -y git
            ;;
        amzn|rhel|centos)
            sudo yum install -y git
            ;;
    esac
    
    log_success "Git installed successfully"
}

#######################################
# Deployment Functions
#######################################

get_git_credentials() {
    echo ""
    log_info "Git Repository Configuration"
    echo "--------------------------------"
    
    # Get GitHub username
    read -p "Enter GitHub username: " GITHUB_USER
    
    # Get GitHub token (hidden input)
    read -s -p "Enter GitHub Personal Access Token: " GITHUB_TOKEN
    echo ""
    
    # Get repository name
    read -p "Enter repository name (e.g., username/voiceai): " REPO_NAME
    
    # Construct repo URL with token
    REPO_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${REPO_NAME}.git"
    
    # Get branch
    read -p "Enter branch name [main]: " INPUT_BRANCH
    BRANCH=${INPUT_BRANCH:-main}
    
    log_success "Git credentials configured"
}

setup_env_file() {
    log_info "Setting up environment variables..."
    
    ENV_FILE="$PROJECT_DIR/.env"
    
    if [ -f "$ENV_FILE" ]; then
        read -p "Environment file exists. Overwrite? (y/N): " OVERWRITE
        if [ "$OVERWRITE" != "y" ] && [ "$OVERWRITE" != "Y" ]; then
            log_info "Keeping existing .env file"
            return
        fi
    fi

    echo ""
    log_info "Enter environment variables (press Enter for defaults):"
    echo "--------------------------------"
    
    read -p "POSTGRES_USER [voiceai]: " POSTGRES_USER
    POSTGRES_USER=${POSTGRES_USER:-voiceai}
    
    read -s -p "POSTGRES_PASSWORD [voiceai123]: " POSTGRES_PASSWORD
    POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-voiceai123}
    echo ""
    
    read -p "POSTGRES_DB [voiceai_db]: " POSTGRES_DB
    POSTGRES_DB=${POSTGRES_DB:-voiceai_db}
    
    read -s -p "GROQ_API_KEY: " GROQ_API_KEY
    echo ""
    
    read -s -p "TAVUS_API_KEY: " TAVUS_API_KEY
    echo ""
    
    read -p "TAVUS_REPLICA_ID: " TAVUS_REPLICA_ID
    
    read -p "TAVUS_PERSONA_ID: " TAVUS_PERSONA_ID
    
    read -p "PUBLIC_URL (e.g., https://yourdomain.com): " PUBLIC_URL
    
    read -s -p "JWT_SECRET [auto-generated]: " JWT_SECRET
    JWT_SECRET=${JWT_SECRET:-$(openssl rand -hex 32)}
    echo ""

    # Create .env file
    cat > "$ENV_FILE" << EOF
# Database
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB}

# API Keys
GROQ_API_KEY=${GROQ_API_KEY}
TAVUS_API_KEY=${TAVUS_API_KEY}
TAVUS_REPLICA_ID=${TAVUS_REPLICA_ID}
TAVUS_PERSONA_ID=${TAVUS_PERSONA_ID}

# Application
PUBLIC_URL=${PUBLIC_URL}
JWT_SECRET=${JWT_SECRET}

# Environment
NODE_ENV=production
EOF

    chmod 600 "$ENV_FILE"
    log_success "Environment file created at $ENV_FILE"
}

clone_or_pull_repo() {
    log_info "Setting up repository..."
    
    if [ -d "$PROJECT_DIR/.git" ]; then
        log_info "Repository exists, pulling latest changes..."
        cd "$PROJECT_DIR"
        
        # Stash any local changes
        git stash --include-untracked 2>/dev/null || true
        
        # Pull latest
        git fetch origin
        git checkout $BRANCH
        git pull origin $BRANCH
        
        log_success "Repository updated"
    else
        log_info "Cloning repository..."
        sudo mkdir -p "$PROJECT_DIR"
        sudo chown -R $USER:$USER "$PROJECT_DIR"
        
        git clone -b $BRANCH "$REPO_URL" "$PROJECT_DIR"
        
        log_success "Repository cloned"
    fi
    
    cd "$PROJECT_DIR"
}

create_ssl_directory() {
    log_info "Creating SSL directory..."
    mkdir -p "$PROJECT_DIR/nginx/ssl"
    log_info "Place your SSL certificates in $PROJECT_DIR/nginx/ssl/"
    log_info "  - fullchain.pem"
    log_info "  - privkey.pem"
}

build_and_deploy() {
    log_info "Building and deploying containers..."
    
    cd "$PROJECT_DIR"
    
    # Stop existing containers
    log_info "Stopping existing containers..."
    docker compose -f docker-compose.prod.yml down 2>/dev/null || true
    
    # Build containers
    log_info "Building containers (this may take a few minutes)..."
    docker compose -f docker-compose.prod.yml build --no-cache
    
    # Start containers
    log_info "Starting containers..."
    docker compose -f docker-compose.prod.yml up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to start..."
    sleep 10
    
    # Check status
    docker compose -f docker-compose.prod.yml ps
    
    log_success "Deployment complete!"
}

show_status() {
    echo ""
    log_info "Container Status:"
    echo "--------------------------------"
    docker compose -f docker-compose.prod.yml ps
    
    echo ""
    log_info "Service URLs:"
    echo "--------------------------------"
    echo "  Frontend: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')"
    echo "  Backend API: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')/api/"
    echo "  Health Check: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')/health"
}

show_logs() {
    log_info "Showing container logs (Ctrl+C to exit)..."
    docker compose -f docker-compose.prod.yml logs -f
}

#######################################
# Main Menu
#######################################

show_menu() {
    echo ""
    echo "Select an option:"
    echo "--------------------------------"
    echo "1) Full deployment (fresh install)"
    echo "2) Update and redeploy"
    echo "3) Restart containers"
    echo "4) Stop containers"
    echo "5) Show status"
    echo "6) Show logs"
    echo "7) Setup environment variables"
    echo "8) Exit"
    echo ""
    read -p "Enter choice [1-8]: " CHOICE
}

full_deploy() {
    install_git
    install_docker
    get_git_credentials
    clone_or_pull_repo
    setup_env_file
    create_ssl_directory
    build_and_deploy
    show_status
}

update_deploy() {
    get_git_credentials
    clone_or_pull_repo
    build_and_deploy
    show_status
}

restart_containers() {
    cd "$PROJECT_DIR"
    log_info "Restarting containers..."
    docker compose -f docker-compose.prod.yml restart
    show_status
}

stop_containers() {
    cd "$PROJECT_DIR"
    log_info "Stopping containers..."
    docker compose -f docker-compose.prod.yml down
    log_success "Containers stopped"
}

#######################################
# Entry Point
#######################################

main() {
    print_banner
    
    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        log_warning "Running as root. Consider running as a regular user with sudo privileges."
    fi

    # Parse command line arguments
    case "${1:-}" in
        --full)
            full_deploy
            exit 0
            ;;
        --update)
            update_deploy
            exit 0
            ;;
        --restart)
            restart_containers
            exit 0
            ;;
        --stop)
            stop_containers
            exit 0
            ;;
        --status)
            cd "$PROJECT_DIR"
            show_status
            exit 0
            ;;
        --logs)
            cd "$PROJECT_DIR"
            show_logs
            exit 0
            ;;
        --help)
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --full      Full deployment (fresh install)"
            echo "  --update    Update and redeploy"
            echo "  --restart   Restart containers"
            echo "  --stop      Stop containers"
            echo "  --status    Show status"
            echo "  --logs      Show logs"
            echo "  --help      Show this help"
            echo ""
            echo "Without options, interactive menu is shown."
            exit 0
            ;;
    esac

    # Interactive mode
    while true; do
        show_menu
        
        case $CHOICE in
            1) full_deploy ;;
            2) update_deploy ;;
            3) restart_containers ;;
            4) stop_containers ;;
            5) cd "$PROJECT_DIR" 2>/dev/null && show_status || log_error "Project not deployed yet" ;;
            6) cd "$PROJECT_DIR" 2>/dev/null && show_logs || log_error "Project not deployed yet" ;;
            7) cd "$PROJECT_DIR" 2>/dev/null && setup_env_file || log_error "Project not deployed yet" ;;
            8) log_info "Goodbye!"; exit 0 ;;
            *) log_error "Invalid option" ;;
        esac
    done
}

main "$@"
