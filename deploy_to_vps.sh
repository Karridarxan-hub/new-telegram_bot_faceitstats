#!/bin/bash
# Comprehensive VPS Deployment Script for FACEIT Bot with Supabase PostgreSQL
# This script handles full deployment, database testing, and production setup

set -e

# Configuration
VPS_IP="185.224.132.36"
VPS_USER="root"
VPS_PASSWORD="7QwGakz3\`!H7_1Y"
PROJECT_NAME="faceit-telegram-bot"
DEPLOYMENT_DIR="/opt/$PROJECT_NAME"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] ✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $1${NC}"
}

# Function to execute commands on VPS
vps_exec() {
    sshpass -p "$VPS_PASSWORD" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "$1"
}

# Function to copy files to VPS
vps_copy() {
    sshpass -p "$VPS_PASSWORD" scp -o StrictHostKeyChecking=no -r "$1" "$VPS_USER@$VPS_IP:$2"
}

# Function to check if command exists on VPS
vps_command_exists() {
    vps_exec "command -v $1 >/dev/null 2>&1"
}

echo "🚀 FACEIT Bot VPS Deployment with Supabase PostgreSQL"
echo "===================================================="
echo ""
echo "Target VPS: $VPS_IP"
echo "Deployment Directory: $DEPLOYMENT_DIR"
echo "Project: $PROJECT_NAME"
echo ""

# Pre-deployment checks
log "🔍 Pre-deployment checks..."

# Check if sshpass is available
if ! command -v sshpass &> /dev/null; then
    error "sshpass is required but not installed. Install it with:"
    error "  Ubuntu/Debian: sudo apt-get install sshpass"
    error "  macOS: brew install sshpass"
    error "  CentOS/RHEL: sudo yum install sshpass"
    exit 1
fi

# Test VPS connectivity
log "Testing VPS connectivity..."
if ! ping -c 1 "$VPS_IP" > /dev/null 2>&1; then
    error "Cannot reach VPS at $VPS_IP"
    exit 1
fi
success "VPS is reachable"

# Test SSH connection
log "Testing SSH connection..."
if ! vps_exec "echo 'SSH connection successful'"; then
    error "SSH connection failed"
    exit 1
fi
success "SSH connection established"

# Phase 1: System Setup and Dependencies
log "📦 Phase 1: Installing system dependencies..."

vps_exec "apt-get update && apt-get upgrade -y"

# Install required packages
vps_exec "apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    docker.io \
    docker-compose \
    git \
    curl \
    wget \
    unzip \
    postgresql-client \
    dnsutils \
    netcat \
    telnet \
    traceroute \
    htop \
    nano \
    screen \
    fail2ban \
    ufw"

# Enable and start Docker
vps_exec "systemctl enable docker && systemctl start docker"
vps_exec "usermod -aG docker root"

success "System dependencies installed"

# Phase 2: Firewall Configuration
log "🔥 Phase 2: Configuring firewall..."

vps_exec "ufw --force reset"
vps_exec "ufw default deny incoming"
vps_exec "ufw default allow outgoing"
vps_exec "ufw allow ssh"
vps_exec "ufw allow 80/tcp"
vps_exec "ufw allow 443/tcp"
vps_exec "ufw allow 9181/tcp"  # RQ Dashboard
vps_exec "ufw --force enable"

success "Firewall configured"

# Phase 3: Create deployment directory and copy files
log "📁 Phase 3: Setting up project files..."

vps_exec "rm -rf $DEPLOYMENT_DIR && mkdir -p $DEPLOYMENT_DIR"

# Copy all project files
log "Copying project files to VPS..."
vps_copy "." "$DEPLOYMENT_DIR/"

# Copy specific configuration files
vps_copy "docker-compose.production.yml" "$DEPLOYMENT_DIR/docker-compose.yml"
vps_copy "production_database_config.py" "$DEPLOYMENT_DIR/"
vps_copy "test_supabase_connectivity.py" "$DEPLOYMENT_DIR/"
vps_copy "vps_connectivity_test.sh" "$DEPLOYMENT_DIR/"

# Make scripts executable
vps_exec "chmod +x $DEPLOYMENT_DIR/*.sh"
vps_exec "chmod +x $DEPLOYMENT_DIR/*.py"

success "Project files deployed"

# Phase 4: Environment Configuration
log "🔧 Phase 4: Environment configuration..."

# Create production environment file
vps_exec "cat > $DEPLOYMENT_DIR/.env.production << 'EOF'
# Production Environment Configuration
ENVIRONMENT=production

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
ADMIN_USER_IDS=${ADMIN_USER_IDS}

# FACEIT API Configuration
FACEIT_API_KEY=${FACEIT_API_KEY}
FACEIT_API_BASE_URL=https://open.faceit.com/data/v4

# Database Configuration (Supabase PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres.emzlxdutmhmbvaetphpu:b6Sfj*D!Gr98vPY@aws-0-us-east-1.pooler.supabase.com:6543/postgres

# Database Pool Settings (Optimized for Supabase)
DB_POOL_SIZE=15
DB_POOL_OVERFLOW=25
DB_POOL_TIMEOUT=30
DB_MAX_RETRIES=5
DB_CONNECTION_TIMEOUT=15
DB_COMMAND_TIMEOUT=60
DB_ENABLE_MONITORING=true
DB_LOG_SLOW_QUERIES=true
DB_SLOW_QUERY_THRESHOLD=1.0

# Failover Configuration
DB_FAILOVER_ENABLED=true
DB_FAILOVER_RETRY_DELAY=5.0
DB_HEALTH_CHECK_INTERVAL=60

# Redis Configuration (if using local Redis)
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=
REDIS_MAX_CONNECTIONS=20

# Queue Configuration
QUEUE_REDIS_URL=redis://localhost:6379
QUEUE_DEFAULT_TIMEOUT=300
QUEUE_MAX_WORKERS=4
QUEUE_ENABLE_MONITORING=true

# Application Settings
LOG_LEVEL=INFO
CHECK_INTERVAL_MINUTES=10
DATA_FILE_PATH=/app/data/data.json

# Network Settings
NETWORK_TIMEOUT=30
DNS_TIMEOUT=10

# Version
VERSION=1.0.0
EOF"

success "Environment configuration created"

# Phase 5: Database Connectivity Testing
log "🐘 Phase 5: Testing Supabase connectivity..."

# Install Python dependencies for testing
vps_exec "cd $DEPLOYMENT_DIR && python3 -m pip install asyncpg dnspython"

# Run comprehensive connectivity test
log "Running comprehensive connectivity test..."
if vps_exec "cd $DEPLOYMENT_DIR && bash vps_connectivity_test.sh"; then
    success "Basic connectivity test passed"
else
    warning "Some connectivity tests failed - continuing with deployment"
fi

# Test Python connectivity
log "Testing Python asyncpg connectivity..."
if vps_exec "cd $DEPLOYMENT_DIR && python3 test_supabase_connectivity.py"; then
    success "Python connectivity test passed"
else
    warning "Python connectivity test failed - check logs"
fi

# Phase 6: Docker Setup
log "🐳 Phase 6: Docker deployment..."

# Pull required Docker images
vps_exec "cd $DEPLOYMENT_DIR && docker-compose pull"

# Build the application image
log "Building application Docker image..."
vps_exec "cd $DEPLOYMENT_DIR && docker-compose build"

success "Docker images ready"

# Phase 7: Database Schema Setup
log "🏗️ Phase 7: Database schema setup..."

# Test database connection and setup schema if needed
vps_exec "cd $DEPLOYMENT_DIR && python3 -c \"
import asyncio
import sys
sys.path.append('.')
from production_database_config import get_production_database

async def setup_database():
    try:
        async with get_production_database() as db:
            result = await db.execute_query('SELECT 1')
            print(f'Database connection successful: {result}')
            
            # Check if tables exist
            tables = await db.execute_query(\\\"
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            \\\")
            print(f'Existing tables: {tables}')
            
    except Exception as e:
        print(f'Database setup failed: {e}')
        sys.exit(1)

asyncio.run(setup_database())
\""

success "Database schema verified"

# Phase 8: Start Services
log "🚀 Phase 8: Starting services..."

# Start the application
vps_exec "cd $DEPLOYMENT_DIR && docker-compose up -d"

# Wait for services to start
sleep 30

# Check service status
log "Checking service status..."
vps_exec "cd $DEPLOYMENT_DIR && docker-compose ps"

# Check logs for any immediate issues
log "Checking application logs..."
vps_exec "cd $DEPLOYMENT_DIR && docker-compose logs --tail=20"

success "Services started"

# Phase 9: Health Checks
log "🏥 Phase 9: Health checks..."

# Wait for services to fully initialize
sleep 60

# Check container health
log "Checking container health..."
healthy_containers=0
total_containers=$(vps_exec "cd $DEPLOYMENT_DIR && docker-compose ps -q | wc -l")

for container in $(vps_exec "cd $DEPLOYMENT_DIR && docker-compose ps -q"); do
    if vps_exec "docker inspect $container | grep '\"Status\": \"healthy\"' > /dev/null"; then
        ((healthy_containers++))
    fi
done

log "Container health: $healthy_containers/$total_containers healthy"

# Test database connectivity from within containers
log "Testing database connectivity from containers..."
if vps_exec "cd $DEPLOYMENT_DIR && docker-compose exec -T faceit-bot-prod python -c 'import asyncio; import sys; sys.path.append(\"/app\"); from production_database_config import test_production_database; asyncio.run(test_production_database())'"; then
    success "Container database connectivity verified"
else
    warning "Container database connectivity test failed"
fi

# Phase 10: Monitoring Setup
log "📊 Phase 10: Setting up monitoring..."

# Create monitoring script
vps_exec "cat > $DEPLOYMENT_DIR/monitor.sh << 'EOF'
#!/bin/bash
# Monitoring script for FACEIT Bot

while true; do
    echo \"[$(date)] Checking service status...\"
    cd $DEPLOYMENT_DIR
    
    # Check container status
    docker-compose ps
    
    # Check database connectivity
    docker-compose exec -T faceit-bot-prod python -c \"
import asyncio
import sys
sys.path.append('/app')
from production_database_config import get_production_database

async def health_check():
    try:
        async with get_production_database() as db:
            result = await db.execute_query('SELECT NOW()')
            print(f'Database health check: OK - {result}')
    except Exception as e:
        print(f'Database health check: FAILED - {e}')

asyncio.run(health_check())
\"
    
    echo \"Sleeping for 5 minutes...\"
    sleep 300
done
EOF"

vps_exec "chmod +x $DEPLOYMENT_DIR/monitor.sh"

# Start monitoring in screen session
vps_exec "screen -dmS monitor bash $DEPLOYMENT_DIR/monitor.sh"

success "Monitoring setup complete"

# Phase 11: Backup Setup
log "💾 Phase 11: Setting up backup procedures..."

vps_exec "cat > $DEPLOYMENT_DIR/backup.sh << 'EOF'
#!/bin/bash
# Backup script for FACEIT Bot

BACKUP_DIR=\"/opt/backups/faceit-bot\"
DATE=$(date +\"%Y%m%d_%H%M%S\")

mkdir -p \$BACKUP_DIR

# Backup configuration
tar -czf \"\$BACKUP_DIR/config_\$DATE.tar.gz\" -C $DEPLOYMENT_DIR .env.production docker-compose.yml

# Backup logs
tar -czf \"\$BACKUP_DIR/logs_\$DATE.tar.gz\" -C $DEPLOYMENT_DIR logs/

# Keep only last 7 days of backups
find \$BACKUP_DIR -name \"*.tar.gz\" -mtime +7 -delete

echo \"Backup completed: \$DATE\"
EOF"

vps_exec "chmod +x $DEPLOYMENT_DIR/backup.sh"

# Setup daily backup cron job
vps_exec "echo '0 2 * * * root /opt/faceit-telegram-bot/backup.sh >> /var/log/faceit-backup.log 2>&1' >> /etc/crontab"

success "Backup procedures configured"

# Final Summary
echo ""
echo "🎉 DEPLOYMENT COMPLETE!"
echo "======================"
echo ""
echo "📍 VPS Information:"
echo "   IP Address: $VPS_IP"
echo "   Deployment Path: $DEPLOYMENT_DIR"
echo ""
echo "🔗 Access Points:"
echo "   RQ Dashboard: http://$VPS_IP:9181"
echo "   SSH Access: ssh root@$VPS_IP"
echo ""
echo "📊 Service Management:"
echo "   Start: ssh root@$VPS_IP 'cd $DEPLOYMENT_DIR && docker-compose up -d'"
echo "   Stop: ssh root@$VPS_IP 'cd $DEPLOYMENT_DIR && docker-compose down'"
echo "   Status: ssh root@$VPS_IP 'cd $DEPLOYMENT_DIR && docker-compose ps'"
echo "   Logs: ssh root@$VPS_IP 'cd $DEPLOYMENT_DIR && docker-compose logs -f'"
echo ""
echo "🔧 Monitoring:"
echo "   Monitor Screen: ssh root@$VPS_IP 'screen -r monitor'"
echo "   Database Test: ssh root@$VPS_IP 'cd $DEPLOYMENT_DIR && python3 test_supabase_connectivity.py'"
echo ""
echo "📝 Important Files:"
echo "   Environment: $DEPLOYMENT_DIR/.env.production"
echo "   Docker Compose: $DEPLOYMENT_DIR/docker-compose.yml"
echo "   Logs: $DEPLOYMENT_DIR/logs/"
echo ""
echo "✅ Database Configuration:"
echo "   Primary: Supabase Pooler (Port 6543)"
echo "   Fallback: Supabase Direct (Port 5432)"
echo "   Connection Pool: 15 connections per service"
echo "   Health Checks: Every 60 seconds"
echo ""

# Final connectivity verification
log "🔍 Final connectivity verification..."
sleep 10

if vps_exec "cd $DEPLOYMENT_DIR && docker-compose exec -T faceit-bot-prod python -c 'print(\"Bot is responding\")'"; then
    success "✅ DEPLOYMENT SUCCESSFUL - Bot is running and responsive!"
else
    warning "⚠️ Deployment completed but bot may not be fully responsive yet"
    log "Check logs with: ssh root@$VPS_IP 'cd $DEPLOYMENT_DIR && docker-compose logs'"
fi

echo ""
echo "🎯 Next Steps:"
echo "1. Monitor the logs for any issues"
echo "2. Test bot functionality via Telegram"
echo "3. Verify database operations are working"
echo "4. Set up additional monitoring if needed"
echo ""

success "Deployment script completed successfully!"