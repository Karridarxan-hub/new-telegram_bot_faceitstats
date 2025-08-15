#!/bin/bash

# FACEIT Telegram Bot - Automatic VPS Deploy Script
# ==================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# VPS Configuration
VPS_IP="185.224.132.36"
VPS_USER="root"
SSH_KEY="./vps-key.pem"
PROJECT_NAME="faceit-telegram-bot"
REPO_URL="https://github.com/Karridarxan-hub/new-telegram_bot_faceitstats.git"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  FACEIT Bot VPS Automatic Deploy${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# Function to run command on VPS
run_on_vps() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "$1"
}

# Function to copy file to VPS
copy_to_vps() {
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "$1" "$VPS_USER@$VPS_IP:$2"
}

echo -e "${YELLOW}Step 1/8: Testing SSH connection...${NC}"
if run_on_vps "echo 'SSH connection successful'"; then
    echo -e "${GREEN}✅ SSH connection established${NC}"
else
    echo -e "${RED}❌ SSH connection failed. Check VPS IP and SSH key.${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 2/8: Setting correct SSH key permissions...${NC}"
chmod 600 "$SSH_KEY"
echo -e "${GREEN}✅ SSH key permissions set${NC}"

echo -e "${YELLOW}Step 3/8: Installing Docker and Docker Compose...${NC}"
run_on_vps "
    # Update system
    apt update && apt upgrade -y
    
    # Install Docker if not exists
    if ! command -v docker &> /dev/null; then
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        rm get-docker.sh
        systemctl enable docker
        systemctl start docker
        echo 'Docker installed successfully'
    else
        echo 'Docker already installed'
    fi
    
    # Install Docker Compose if not exists
    if ! command -v docker-compose &> /dev/null; then
        curl -L \"https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)\" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        echo 'Docker Compose installed successfully'
    else
        echo 'Docker Compose already installed'
    fi
"
echo -e "${GREEN}✅ Docker and Docker Compose ready${NC}"

echo -e "${YELLOW}Step 4/8: Cloning project repository...${NC}"
run_on_vps "
    # Remove existing project if exists
    if [ -d '$PROJECT_NAME' ]; then
        rm -rf $PROJECT_NAME
        echo 'Removed existing project directory'
    fi
    
    # Clone repository
    git clone $REPO_URL $PROJECT_NAME
    cd $PROJECT_NAME
    echo 'Repository cloned successfully'
"
echo -e "${GREEN}✅ Project repository cloned${NC}"

echo -e "${YELLOW}Step 5/8: Copying production environment file...${NC}"
if [ -f ".env.production" ]; then
    copy_to_vps ".env.production" "/root/$PROJECT_NAME/.env.docker"
    echo -e "${GREEN}✅ Production environment file copied${NC}"
else
    echo -e "${RED}❌ .env.production file not found. Creating it now...${NC}"
    
    # Create production env file with real tokens
    cat > .env.production << EOF
# FACEIT Telegram Bot Production Configuration
# ============================================

# Telegram Bot Token
TELEGRAM_BOT_TOKEN=8200317917:AAE3wSxtG6N7wKeLJezgNaQsCd5uHMcXjVk

# FACEIT API Key
FACEIT_API_KEY=41f48f43-609c-4639-b821-360b039f18b4

# Admin Configuration
ADMIN_USER_IDS=123456789

# Redis Configuration (Upstash Cloud Redis)
REDIS_URL=rediss://default:AZn7AAIncDFmZDE2ZDI4YTQ3Y2I0OWVkYTZjYjkzYWQ5OTIzNWRiMHAxMzk0MTk@enjoyed-tick-39419.upstash.io:6379/0

# Database Configuration (Supabase Cloud PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres:b6Sfj*D!Gr98vPY@db.emzlxdutmhmbvaetphpu.supabase.co:5432/postgres

# Logging Configuration
LOG_LEVEL=INFO

# Bot Configuration
CHECK_INTERVAL_MINUTES=10

# Optional: Telegram Chat ID for notifications
TELEGRAM_CHAT_ID=

# Queue settings
QUEUE_REDIS_URL=rediss://default:AZn7AAIncDFmZDE2ZDI4YTQ3Y2I0OWVkYTZjYjkzYWQ5OTIzNWRiMHAxMzk0MTk@enjoyed-tick-39419.upstash.io:6379/1
QUEUE_MAX_WORKERS=3
QUEUE_ENABLE_MONITORING=true

# Version
VERSION=1.0.0

# Environment
ENVIRONMENT=production
DEBUG=false
EOF
    
    copy_to_vps ".env.production" "/root/$PROJECT_NAME/.env.docker"
    echo -e "${GREEN}✅ Production environment file created and copied${NC}"
fi

echo -e "${YELLOW}Step 6/8: Building Docker images...${NC}"
run_on_vps "
    cd $PROJECT_NAME
    docker-compose build --no-cache
    echo 'Docker images built successfully'
"
echo -e "${GREEN}✅ Docker images built${NC}"

echo -e "${YELLOW}Step 7/8: Starting bot services...${NC}"
run_on_vps "
    cd $PROJECT_NAME
    
    # Stop existing containers if any
    docker-compose down 2>/dev/null || true
    
    # Start all services
    docker-compose up -d
    
    echo 'Bot services started'
"
echo -e "${GREEN}✅ Bot services started${NC}"

echo -e "${YELLOW}Step 8/8: Checking deployment status...${NC}"
sleep 10  # Wait for containers to start

echo -e "${BLUE}Container Status:${NC}"
run_on_vps "cd $PROJECT_NAME && docker-compose ps"

echo ""
echo -e "${BLUE}Recent Logs:${NC}"
run_on_vps "cd $PROJECT_NAME && docker-compose logs --tail=20 faceit-bot"

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  🎉 DEPLOYMENT COMPLETED! 🎉${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${BLUE}Your bot is now running on VPS: $VPS_IP${NC}"
echo -e "${BLUE}RQ Dashboard: http://$VPS_IP:9181${NC}"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo -e "• Check status: ${BLUE}ssh -i $SSH_KEY $VPS_USER@$VPS_IP 'cd $PROJECT_NAME && docker-compose ps'${NC}"
echo -e "• View logs: ${BLUE}ssh -i $SSH_KEY $VPS_USER@$VPS_IP 'cd $PROJECT_NAME && docker-compose logs -f faceit-bot'${NC}"
echo -e "• Restart bot: ${BLUE}ssh -i $SSH_KEY $VPS_USER@$VPS_IP 'cd $PROJECT_NAME && docker-compose restart faceit-bot'${NC}"
echo -e "• Update bot: ${BLUE}./deploy-to-vps.sh${NC}"
echo ""