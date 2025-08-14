#!/bin/bash
# Worker management script for FACEIT Bot

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Default values
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_DIR/.env.docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
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

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
}

show_help() {
    echo "FACEIT Bot Worker Management Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start           Start all services (bot + workers)"
    echo "  stop            Stop all services"
    echo "  restart         Restart all services"
    echo "  status          Show services status"
    echo "  logs            Show logs (specify service or 'all')"
    echo "  scale           Scale worker services"
    echo "  worker-status   Show worker queue status"
    echo "  cleanup         Clean up old containers and volumes"
    echo "  health          Check system health"
    echo ""
    echo "Options:"
    echo "  -f, --file      Docker compose file (default: docker-compose.yml)"
    echo "  -e, --env       Environment file (default: .env.docker)"
    echo "  -h, --help      Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start all services"
    echo "  $0 logs worker-priority     # Show priority worker logs"
    echo "  $0 scale worker-default=3   # Scale default workers to 3 instances"
    echo "  $0 worker-status            # Show RQ queue status"
}

start_services() {
    log_info "Starting FACEIT Bot services..."
    
    # Check if .env.docker exists
    if [[ ! -f "$ENV_FILE" ]]; then
        log_warning ".env.docker not found, creating from .env"
        if [[ -f "$PROJECT_DIR/.env" ]]; then
            cp "$PROJECT_DIR/.env" "$ENV_FILE"
        else
            log_error "No environment file found. Please create .env or .env.docker"
            exit 1
        fi
    fi
    
    # Start services
    docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
    
    log_success "Services started successfully"
    show_status
}

stop_services() {
    log_info "Stopping FACEIT Bot services..."
    docker-compose -f "$COMPOSE_FILE" down
    log_success "Services stopped"
}

restart_services() {
    log_info "Restarting FACEIT Bot services..."
    docker-compose -f "$COMPOSE_FILE" restart
    log_success "Services restarted"
    show_status
}

show_status() {
    log_info "Service Status:"
    docker-compose -f "$COMPOSE_FILE" ps
}

show_logs() {
    local service=${1:-""}
    
    if [[ -z "$service" ]]; then
        log_error "Please specify a service name or 'all'"
        log_info "Available services: faceit-bot, worker-priority, worker-default, worker-bulk, redis, postgres, rq-dashboard"
        return 1
    fi
    
    if [[ "$service" == "all" ]]; then
        docker-compose -f "$COMPOSE_FILE" logs -f
    else
        docker-compose -f "$COMPOSE_FILE" logs -f "$service"
    fi
}

scale_workers() {
    local scale_config="$1"
    
    if [[ -z "$scale_config" ]]; then
        log_error "Please specify scaling configuration"
        log_info "Example: worker-default=3"
        return 1
    fi
    
    log_info "Scaling workers: $scale_config"
    docker-compose -f "$COMPOSE_FILE" up -d --scale "$scale_config"
    log_success "Workers scaled successfully"
    show_status
}

show_worker_status() {
    log_info "Getting worker status..."
    
    # Check if bot container is running
    if ! docker ps | grep -q faceit-bot; then
        log_error "Bot container is not running"
        return 1
    fi
    
    # Execute admin queue status command
    docker exec faceit-bot python -c "
import asyncio
import sys
sys.path.append('/app')
from queues.task_manager import get_task_manager

async def get_status():
    try:
        manager = get_task_manager()
        stats = manager.get_queue_stats()
        health = manager.health_check()
        
        print('\\n=== Worker Queue Status ===')
        print(f'Redis Status: {health.get(\"redis_connection\", \"unknown\")}')
        print(f'Active Tasks: {health.get(\"active_tasks\", 0)}')
        print(f'Scheduled Tasks: {health.get(\"scheduled_tasks\", 0)}')
        print()
        
        for queue_name, queue_stats in stats.items():
            if isinstance(queue_stats, dict) and 'error' not in queue_stats:
                print(f'{queue_name}:')
                print(f'  Queued: {queue_stats.get(\"queued_jobs\", 0)}')
                print(f'  Running: {queue_stats.get(\"started_jobs\", 0)}')
                print(f'  Finished: {queue_stats.get(\"finished_jobs\", 0)}')
                print(f'  Failed: {queue_stats.get(\"failed_jobs\", 0)}')
                print()
    except Exception as e:
        print(f'Error getting status: {e}')

asyncio.run(get_status())
"
}

cleanup_system() {
    log_info "Cleaning up Docker system..."
    
    # Stop services first
    docker-compose -f "$COMPOSE_FILE" down
    
    # Remove old images
    log_info "Removing old FACEIT bot images..."
    docker images | grep faceit-bot | awk '{print $3}' | head -n -2 | xargs -r docker rmi || true
    
    # Clean up volumes (be careful with this)
    read -p "Do you want to clean up volumes? This will delete all data (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker volume ls | grep faceit | awk '{print $2}' | xargs -r docker volume rm || true
        log_success "Volumes cleaned up"
    fi
    
    # General cleanup
    docker system prune -f
    log_success "System cleanup completed"
}

check_health() {
    log_info "Checking system health..."
    
    # Check if services are running
    services=("faceit-bot" "worker-priority" "worker-default" "worker-bulk" "redis" "postgres")
    all_healthy=true
    
    for service in "${services[@]}"; do
        if docker-compose -f "$COMPOSE_FILE" ps | grep -q "$service.*Up.*healthy"; then
            log_success "$service is healthy"
        elif docker-compose -f "$COMPOSE_FILE" ps | grep -q "$service.*Up"; then
            log_warning "$service is running but health unknown"
        else
            log_error "$service is not running or unhealthy"
            all_healthy=false
        fi
    done
    
    # Check Redis connectivity
    if docker exec faceit-redis redis-cli ping &>/dev/null; then
        log_success "Redis is responding"
    else
        log_error "Redis is not responding"
        all_healthy=false
    fi
    
    # Check PostgreSQL connectivity
    if docker exec faceit-postgres pg_isready -U faceit_user -d faceit_bot &>/dev/null; then
        log_success "PostgreSQL is ready"
    else
        log_error "PostgreSQL is not ready"
        all_healthy=false
    fi
    
    if $all_healthy; then
        log_success "All systems are healthy"
    else
        log_error "Some systems are unhealthy"
        exit 1
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        -e|--env)
            ENV_FILE="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        start)
            check_docker
            start_services
            exit 0
            ;;
        stop)
            check_docker
            stop_services
            exit 0
            ;;
        restart)
            check_docker
            restart_services
            exit 0
            ;;
        status)
            check_docker
            show_status
            exit 0
            ;;
        logs)
            check_docker
            show_logs "$2"
            exit 0
            ;;
        scale)
            check_docker
            scale_workers "$2"
            exit 0
            ;;
        worker-status)
            check_docker
            show_worker_status
            exit 0
            ;;
        cleanup)
            check_docker
            cleanup_system
            exit 0
            ;;
        health)
            check_docker
            check_health
            exit 0
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
done

# If no arguments provided, show help
show_help