#!/bin/bash
set -euo pipefail

# FACEIT Telegram Bot Deployment Script
# Usage: ./deploy.sh <environment> [version]

ENVIRONMENT=${1:-staging}
VERSION=${2:-latest}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/opt/faceit-bot"
DOCKER_COMPOSE_FILE="docker-compose.${ENVIRONMENT}.yml"
BACKUP_DIR="/opt/backups"
LOG_FILE="/var/log/faceit-bot-deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${2:-$NC}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

log_info() { log "$1" "$BLUE"; }
log_success() { log "$1" "$GREEN"; }
log_warning() { log "$1" "$YELLOW"; }
log_error() { log "$1" "$RED"; }

# Error handling
error_exit() {
    log_error "Deployment failed: $1"
    exit 1
}

# Pre-deployment checks
pre_deployment_checks() {
    log_info "Running pre-deployment checks..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        error_exit "Docker is not running"
    fi
    
    # Check if docker-compose file exists
    if [[ ! -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" ]]; then
        error_exit "Docker compose file not found: $DOCKER_COMPOSE_FILE"
    fi
    
    # Check if environment file exists
    if [[ ! -f "$PROJECT_DIR/.env.$ENVIRONMENT" ]]; then
        error_exit "Environment file not found: .env.$ENVIRONMENT"
    fi
    
    # Check disk space (require at least 2GB free)
    AVAILABLE_SPACE=$(df /opt | awk 'NR==2 {print $4}')
    if [[ $AVAILABLE_SPACE -lt 2097152 ]]; then  # 2GB in KB
        error_exit "Insufficient disk space. At least 2GB required."
    fi
    
    # Verify database connectivity
    if ! timeout 10 docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgres pg_isready; then
        log_warning "Database connectivity check failed - continuing anyway"
    fi
    
    log_success "Pre-deployment checks passed"
}

# Create backup before deployment
create_backup() {
    log_info "Creating backup before deployment..."
    
    mkdir -p "$BACKUP_DIR"
    BACKUP_TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    
    # Backup database
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q postgres; then
        log_info "Backing up database..."
        docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgres pg_dump -U faceit_user faceit_bot | gzip > "$BACKUP_DIR/db-backup-$BACKUP_TIMESTAMP.sql.gz"
        
        if [[ -f "$BACKUP_DIR/db-backup-$BACKUP_TIMESTAMP.sql.gz" ]]; then
            log_success "Database backup created: db-backup-$BACKUP_TIMESTAMP.sql.gz"
        else
            error_exit "Database backup failed"
        fi
    fi
    
    # Backup application data
    if [[ -d "$PROJECT_DIR/data" ]]; then
        log_info "Backing up application data..."
        tar -czf "$BACKUP_DIR/data-backup-$BACKUP_TIMESTAMP.tar.gz" -C "$PROJECT_DIR" data/
        log_success "Application data backup created: data-backup-$BACKUP_TIMESTAMP.tar.gz"
    fi
    
    # Upload to S3 if configured
    if command -v aws &> /dev/null && [[ -n "${AWS_S3_BUCKET:-}" ]]; then
        log_info "Uploading backups to S3..."
        aws s3 cp "$BACKUP_DIR/db-backup-$BACKUP_TIMESTAMP.sql.gz" "s3://$AWS_S3_BUCKET/database/"
        aws s3 cp "$BACKUP_DIR/data-backup-$BACKUP_TIMESTAMP.tar.gz" "s3://$AWS_S3_BUCKET/application/"
        log_success "Backups uploaded to S3"
    fi
    
    # Keep only last 7 days of local backups
    find "$BACKUP_DIR" -type f -mtime +7 -delete
}

# Pull new Docker images
pull_images() {
    log_info "Pulling Docker images..."
    
    # Export environment variables
    export $(grep -v '^#' "$PROJECT_DIR/.env.$ENVIRONMENT" | xargs)
    
    # Pull new images
    if ! docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" pull; then
        error_exit "Failed to pull Docker images"
    fi
    
    log_success "Docker images pulled successfully"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    for i in {1..30}; do
        if docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" exec -T postgres pg_isready -U faceit_user -d faceit_bot; then
            break
        fi
        if [[ $i -eq 30 ]]; then
            error_exit "Database failed to become ready after 5 minutes"
        fi
        sleep 10
    done
    
    # Run Alembic migrations
    if docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" run --rm faceit-bot alembic upgrade head; then
        log_success "Database migrations completed successfully"
    else
        error_exit "Database migrations failed"
    fi
}

# Deploy application using blue-green strategy
deploy_blue_green() {
    log_info "Starting blue-green deployment..."
    
    cd "$PROJECT_DIR"
    
    # Export environment variables
    export $(grep -v '^#' ".env.$ENVIRONMENT" | xargs)
    
    # Determine current and new environments
    if docker-compose -p faceit-bot-blue ps | grep -q "Up"; then
        CURRENT_ENV="blue"
        NEW_ENV="green"
    else
        CURRENT_ENV="green"
        NEW_ENV="blue"
    fi
    
    log_info "Deploying to $NEW_ENV environment (current: $CURRENT_ENV)"
    
    # Start new environment
    log_info "Starting $NEW_ENV environment..."
    if ! docker-compose -f "$DOCKER_COMPOSE_FILE" -p "faceit-bot-$NEW_ENV" up -d; then
        error_exit "Failed to start $NEW_ENV environment"
    fi
    
    # Wait for health check
    log_info "Waiting for health check..."
    for i in {1..30}; do
        if curl -f "http://localhost:8080/health" >/dev/null 2>&1; then
            log_success "Health check passed"
            break
        fi
        if [[ $i -eq 30 ]]; then
            log_error "Health check failed, rolling back..."
            docker-compose -f "$DOCKER_COMPOSE_FILE" -p "faceit-bot-$NEW_ENV" down
            error_exit "Health check failed after 5 minutes"
        fi
        sleep 10
    done
    
    # Run smoke tests
    run_smoke_tests
    
    # Switch traffic (update nginx configuration)
    if [[ -f "/etc/nginx/sites-available/faceit-bot" ]]; then
        log_info "Updating nginx configuration..."
        sudo sed -i "s/faceit-bot-$CURRENT_ENV/faceit-bot-$NEW_ENV/g" /etc/nginx/sites-available/faceit-bot
        sudo nginx -t && sudo nginx -s reload
        log_success "Nginx configuration updated"
    fi
    
    # Stop old environment
    log_info "Stopping $CURRENT_ENV environment..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" -p "faceit-bot-$CURRENT_ENV" down
    
    log_success "Blue-green deployment completed successfully"
}

# Run smoke tests
run_smoke_tests() {
    log_info "Running smoke tests..."
    
    # Test health endpoint
    if ! curl -f "http://localhost:8080/health" >/dev/null 2>&1; then
        error_exit "Health endpoint test failed"
    fi
    
    # Test database connectivity
    if ! docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" exec -T faceit-bot python -c "
import asyncio
import asyncpg
import os

async def test_db():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    result = await conn.fetchval('SELECT 1')
    await conn.close()
    return result == 1

if not asyncio.run(test_db()):
    exit(1)
"; then
        error_exit "Database connectivity test failed"
    fi
    
    # Test Redis connectivity
    if ! docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" exec -T faceit-bot python -c "
import redis
import os

r = redis.Redis.from_url(os.getenv('REDIS_URL'))
r.ping()
"; then
        error_exit "Redis connectivity test failed"
    fi
    
    log_success "All smoke tests passed"
}

# Cleanup old Docker images and containers
cleanup() {
    log_info "Cleaning up old Docker resources..."
    
    # Remove unused images
    docker image prune -f
    
    # Remove unused containers
    docker container prune -f
    
    # Remove unused volumes (be careful with this in production)
    if [[ "$ENVIRONMENT" != "production" ]]; then
        docker volume prune -f
    fi
    
    log_success "Cleanup completed"
}

# Send deployment notification
send_notification() {
    local status=$1
    local message="Deployment to $ENVIRONMENT completed with status: $status"
    
    # Slack notification
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"$message\"}" \
            "$SLACK_WEBHOOK_URL"
    fi
    
    # Telegram notification
    if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && [[ -n "${TELEGRAM_CHAT_ID:-}" ]]; then
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="$message"
    fi
    
    # Email notification (requires mailutils)
    if command -v mail &> /dev/null && [[ -n "${NOTIFICATION_EMAIL:-}" ]]; then
        echo "$message" | mail -s "FACEIT Bot Deployment" "$NOTIFICATION_EMAIL"
    fi
}

# Rollback function
rollback() {
    log_error "Rolling back deployment..."
    
    # Find previous backup
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/db-backup-*.sql.gz 2>/dev/null | head -n 1)
    
    if [[ -n "$LATEST_BACKUP" ]]; then
        log_info "Restoring from backup: $(basename "$LATEST_BACKUP")"
        
        # Stop current containers
        docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" down
        
        # Restore database
        gunzip < "$LATEST_BACKUP" | docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" exec -T postgres psql -U faceit_user faceit_bot
        
        # Start containers with previous image
        docker-compose -f "$PROJECT_DIR/$DOCKER_COMPOSE_FILE" up -d
        
        log_success "Rollback completed"
    else
        log_error "No backup found for rollback"
    fi
}

# Main deployment function
main() {
    log_info "Starting deployment of FACEIT Telegram Bot"
    log_info "Environment: $ENVIRONMENT"
    log_info "Version: $VERSION"
    
    # Trap errors and perform rollback
    trap 'rollback; send_notification "FAILED"; exit 1' ERR
    
    # Run deployment steps
    pre_deployment_checks
    create_backup
    pull_images
    
    if [[ "$ENVIRONMENT" == "production" ]]; then
        deploy_blue_green
    else
        # Simple deployment for staging
        cd "$PROJECT_DIR"
        export $(grep -v '^#' ".env.$ENVIRONMENT" | xargs)
        
        docker-compose -f "$DOCKER_COMPOSE_FILE" down
        run_migrations
        docker-compose -f "$DOCKER_COMPOSE_FILE" up -d
        
        # Wait and test
        sleep 30
        run_smoke_tests
    fi
    
    cleanup
    
    log_success "Deployment completed successfully!"
    send_notification "SUCCESS"
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Check if running as root (exit if true, except for nginx reload)
    if [[ $EUID -eq 0 ]] && [[ "$1" != "nginx-reload" ]]; then
        error_exit "This script should not be run as root"
    fi
    
    # Create log directory
    sudo mkdir -p "$(dirname "$LOG_FILE")"
    sudo touch "$LOG_FILE"
    sudo chown "$(whoami):$(whoami)" "$LOG_FILE"
    
    # Start deployment
    main "$@"
fi