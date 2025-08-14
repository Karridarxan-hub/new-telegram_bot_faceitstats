#!/bin/bash
# Production deployment script for FACEIT Bot

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
VERSION_FILE="$PROJECT_DIR/VERSION"
DOCKER_COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_DIR/.env.docker"
BACKUP_DIR="$PROJECT_DIR/backups"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_prerequisites() {
    log_info "Checking deployment prerequisites..."
    
    # Check if Docker is installed and running
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker is not running"
        exit 1
    fi
    
    # Check if Docker Compose is available
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check if required files exist
    if [[ ! -f "$VERSION_FILE" ]]; then
        log_error "VERSION file not found"
        exit 1
    fi
    
    if [[ ! -f "$DOCKER_COMPOSE_FILE" ]]; then
        log_error "docker-compose.yml not found"
        exit 1
    fi
    
    if [[ ! -f "$ENV_FILE" ]]; then
        if [[ -f "$PROJECT_DIR/.env" ]]; then
            log_warning ".env.docker not found, creating from .env"
            cp "$PROJECT_DIR/.env" "$ENV_FILE"
        else
            log_error "No environment configuration found"
            exit 1
        fi
    fi
    
    log_success "Prerequisites check passed"
}

get_current_version() {
    if [[ -f "$VERSION_FILE" ]]; then
        cat "$VERSION_FILE"
    else
        echo "1.0.0"
    fi
}

backup_data() {
    log_info "Creating data backup..."
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    BACKUP_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    BACKUP_NAME="faceit_bot_backup_$BACKUP_TIMESTAMP"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
    
    mkdir -p "$BACKUP_PATH"
    
    # Backup JSON data if exists
    if [[ -d "$PROJECT_DIR/data" ]]; then
        log_info "Backing up JSON data..."
        cp -r "$PROJECT_DIR/data" "$BACKUP_PATH/"
    fi
    
    # Backup PostgreSQL database
    if docker ps | grep -q faceit-postgres; then
        log_info "Backing up PostgreSQL database..."
        docker exec faceit-postgres pg_dump -U faceit_user -d faceit_bot > "$BACKUP_PATH/postgres_dump.sql"
    fi
    
    # Backup Redis data
    if docker ps | grep -q faceit-redis; then
        log_info "Backing up Redis data..."
        docker exec faceit-redis redis-cli --rdb /data/backup.rdb
        docker cp faceit-redis:/data/backup.rdb "$BACKUP_PATH/"
    fi
    
    # Create backup archive
    cd "$BACKUP_DIR"
    tar -czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME"
    rm -rf "$BACKUP_NAME"
    
    log_success "Backup created: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
    echo "$BACKUP_DIR/$BACKUP_NAME.tar.gz"
}

run_pre_deployment_tests() {
    log_info "Running pre-deployment tests..."
    
    # Check if test script exists and run it
    if [[ -f "$PROJECT_DIR/tests/test_integration.py" ]]; then
        cd "$PROJECT_DIR"
        
        # Set test environment variables
        export TESTING=true
        export DATABASE_URL="postgresql+asyncpg://faceit_user:faceit_password@localhost:5432/faceit_bot_test"
        export REDIS_URL="redis://localhost:6379/15"
        
        # Run integration tests
        if python tests/test_integration.py --output "test_results_$(date +%Y%m%d_%H%M%S).json"; then
            log_success "Pre-deployment tests passed"
        else
            log_error "Pre-deployment tests failed"
            read -p "Continue with deployment anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    else
        log_warning "No integration tests found, skipping..."
    fi
}

build_images() {
    log_info "Building Docker images..."
    
    VERSION=$(get_current_version)
    export VERSION
    
    # Build the main application image
    docker-compose -f "$DOCKER_COMPOSE_FILE" build --no-cache
    
    # Tag the image with version
    docker tag faceit-bot:$VERSION faceit-bot:latest
    
    log_success "Docker images built successfully (version: $VERSION)"
}

deploy_services() {
    log_info "Deploying services..."
    
    VERSION=$(get_current_version)
    export VERSION
    
    # Stop existing services gracefully
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; then
        log_info "Stopping existing services..."
        docker-compose -f "$DOCKER_COMPOSE_FILE" down --timeout 30
    fi
    
    # Start services with new version
    log_info "Starting services..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to become healthy..."
    max_wait=300  # 5 minutes
    elapsed=0
    
    while [[ $elapsed -lt $max_wait ]]; do
        if check_service_health; then
            log_success "All services are healthy"
            break
        fi
        
        sleep 10
        elapsed=$((elapsed + 10))
        log_info "Waiting for services... (${elapsed}s/${max_wait}s)"
    done
    
    if [[ $elapsed -ge $max_wait ]]; then
        log_error "Services failed to become healthy within timeout"
        return 1
    fi
}

check_service_health() {
    # Check if all required containers are running and healthy
    required_services=("faceit-bot" "worker-priority" "worker-default" "redis" "postgres")
    
    for service in "${required_services[@]}"; do
        if ! docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "$service.*Up"; then
            return 1
        fi
    done
    
    # Additional health checks
    # Check Redis connectivity
    if ! docker exec faceit-redis redis-cli ping &>/dev/null; then
        return 1
    fi
    
    # Check PostgreSQL connectivity
    if ! docker exec faceit-postgres pg_isready -U faceit_user -d faceit_bot &>/dev/null; then
        return 1
    fi
    
    return 0
}

run_post_deployment_tests() {
    log_info "Running post-deployment tests..."
    
    # Basic connectivity tests
    services=("faceit-bot" "worker-priority" "worker-default" "redis" "postgres")
    
    for service in "${services[@]}"; do
        if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "$service.*Up"; then
            log_success "$service is running"
        else
            log_error "$service is not running"
            return 1
        fi
    done
    
    # Test Redis
    if docker exec faceit-redis redis-cli ping | grep -q "PONG"; then
        log_success "Redis connectivity test passed"
    else
        log_error "Redis connectivity test failed"
        return 1
    fi
    
    # Test PostgreSQL
    if docker exec faceit-postgres pg_isready -U faceit_user -d faceit_bot | grep -q "accepting connections"; then
        log_success "PostgreSQL connectivity test passed"
    else
        log_error "PostgreSQL connectivity test failed"
        return 1
    fi
    
    # Test worker queues
    if python3 -c "
import asyncio
import sys
sys.path.append('$PROJECT_DIR')
from queues.task_manager import get_task_manager

async def test():
    try:
        manager = get_task_manager()
        await manager.initialize()
        health = manager.health_check()
        print(f'Queue health: {health.get(\"redis_connection\", \"unknown\")}')
        return health.get('redis_connection') == 'healthy'
    except Exception as e:
        print(f'Queue test error: {e}')
        return False

result = asyncio.run(test())
exit(0 if result else 1)
    "; then
        log_success "Queue system test passed"
    else
        log_error "Queue system test failed"
        return 1
    fi
    
    log_success "Post-deployment tests passed"
    return 0
}

cleanup_old_images() {
    log_info "Cleaning up old Docker images..."
    
    # Remove old faceit-bot images (keep last 3 versions)
    docker images | grep faceit-bot | awk '{print $3}' | tail -n +4 | xargs -r docker rmi || true
    
    # Clean up dangling images
    docker image prune -f
    
    log_success "Old images cleaned up"
}

show_deployment_status() {
    log_info "Deployment Status Summary"
    echo "================================"
    
    VERSION=$(get_current_version)
    echo "Version: $VERSION"
    echo "Deployment Time: $(date)"
    echo
    
    echo "Service Status:"
    docker-compose -f "$DOCKER_COMPOSE_FILE" ps
    echo
    
    echo "Resource Usage:"
    docker stats --no-stream --format "table {{.Container}}\\t{{.CPUPerc}}\\t{{.MemPerc}}\\t{{.MemUsage}}" | head -10
    echo
    
    # Show recent logs
    echo "Recent Logs (last 20 lines):"
    docker-compose -f "$DOCKER_COMPOSE_FILE" logs --tail=20
}

rollback_deployment() {
    log_warning "Rolling back deployment..."
    
    # This would restore from the most recent backup
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/*.tar.gz | head -1)
    
    if [[ -n "$LATEST_BACKUP" ]]; then
        log_info "Restoring from backup: $LATEST_BACKUP"
        
        # Stop current services
        docker-compose -f "$DOCKER_COMPOSE_FILE" down
        
        # Extract backup
        cd "$BACKUP_DIR"
        tar -xzf "$(basename "$LATEST_BACKUP")"
        BACKUP_NAME=$(basename "$LATEST_BACKUP" .tar.gz)
        
        # Restore data
        if [[ -d "$BACKUP_NAME/data" ]]; then
            rm -rf "$PROJECT_DIR/data"
            cp -r "$BACKUP_NAME/data" "$PROJECT_DIR/"
        fi
        
        # Restore database
        if [[ -f "$BACKUP_NAME/postgres_dump.sql" ]]; then
            docker-compose -f "$DOCKER_COMPOSE_FILE" up -d postgres
            sleep 10
            docker exec -i faceit-postgres psql -U faceit_user -d faceit_bot < "$BACKUP_NAME/postgres_dump.sql"
        fi
        
        # Start services with previous version
        docker-compose -f "$DOCKER_COMPOSE_FILE" up -d
        
        log_success "Rollback completed"
    else
        log_error "No backup found for rollback"
        exit 1
    fi
}

main() {
    log_info "Starting FACEIT Bot deployment..."
    
    # Parse arguments
    SKIP_TESTS=false
    SKIP_BACKUP=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --skip-backup)
                SKIP_BACKUP=true
                shift
                ;;
            --rollback)
                rollback_deployment
                exit 0
                ;;
            --status)
                show_deployment_status
                exit 0
                ;;
            *)
                log_error "Unknown argument: $1"
                echo "Usage: $0 [--skip-tests] [--skip-backup] [--rollback] [--status]"
                exit 1
                ;;
        esac
    done
    
    # Deployment steps
    check_prerequisites
    
    if [[ "$SKIP_BACKUP" != true ]]; then
        backup_data
    fi
    
    if [[ "$SKIP_TESTS" != true ]]; then
        run_pre_deployment_tests
    fi
    
    build_images
    
    if deploy_services; then
        log_success "Services deployed successfully"
    else
        log_error "Service deployment failed"
        log_warning "Consider running rollback: $0 --rollback"
        exit 1
    fi
    
    if run_post_deployment_tests; then
        log_success "Post-deployment tests passed"
    else
        log_error "Post-deployment tests failed"
        log_warning "Deployment may be unstable"
    fi
    
    cleanup_old_images
    
    log_success "FACEIT Bot deployment completed successfully!"
    
    show_deployment_status
}

# Run main function with all arguments
main "$@"