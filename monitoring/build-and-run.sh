#!/bin/bash

# Скрипт для сборки и запуска FACEIT Monitoring Service
# Использование: ./build-and-run.sh [build|run|stop|logs|clean]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="faceit-monitoring"
CONTAINER_NAME="faceit-monitoring"
MONITORING_PORT="9181"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Функция сборки образа
build_image() {
    log_info "Собираем Docker образ для monitoring службы..."
    cd "$SCRIPT_DIR"
    
    # Проверяем наличие Dockerfile
    if [ ! -f "Dockerfile" ]; then
        log_error "Dockerfile не найден в директории $SCRIPT_DIR"
        exit 1
    fi
    
    # Собираем образ с тегами
    docker build \
        --tag "$IMAGE_NAME:latest" \
        --tag "$IMAGE_NAME:$(date +%Y%m%d-%H%M%S)" \
        --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
        .
    
    log_info "Образ $IMAGE_NAME собран успешно"
}

# Функция запуска контейнера
run_container() {
    log_info "Запускаем monitoring контейнер..."
    
    # Останавливаем существующий контейнер если он есть
    if docker ps -a --format "table {{.Names}}" | grep -q "$CONTAINER_NAME"; then
        log_warn "Контейнер $CONTAINER_NAME уже существует, останавливаем..."
        docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
        docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
    
    # Запускаем новый контейнер
    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -p "$MONITORING_PORT:9181" \
        -e REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}" \
        -e DATABASE_URL="${DATABASE_URL:-}" \
        -e MONITORING_PORT="9181" \
        -e FLASK_ENV="production" \
        --memory="256m" \
        --cpus="0.5" \
        "$IMAGE_NAME:latest"
    
    log_info "Monitoring контейнер запущен на порту $MONITORING_PORT"
    log_info "Dashboard доступен по адресу: http://localhost:$MONITORING_PORT"
    log_info "Health check: http://localhost:$MONITORING_PORT/api/health"
}

# Функция остановки контейнера
stop_container() {
    log_info "Останавливаем monitoring контейнер..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || log_warn "Контейнер $CONTAINER_NAME не запущен"
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
    log_info "Контейнер остановлен"
}

# Функция просмотра логов
show_logs() {
    log_info "Показываем логи контейнера $CONTAINER_NAME..."
    docker logs -f "$CONTAINER_NAME" 2>/dev/null || log_error "Контейнер $CONTAINER_NAME не найден"
}

# Функция очистки
cleanup() {
    log_info "Очищаем неиспользуемые Docker ресурсы..."
    docker system prune -f
    log_info "Очистка завершена"
}

# Функция проверки статуса
check_status() {
    log_info "Проверяем статус monitoring службы..."
    
    if docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -q "$CONTAINER_NAME"; then
        log_info "Контейнер запущен:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep "$CONTAINER_NAME"
        
        # Проверяем health check
        if curl -s "http://localhost:$MONITORING_PORT/api/health" >/dev/null; then
            log_info "✅ Service health check: OK"
        else
            log_warn "❌ Service health check: FAILED"
        fi
    else
        log_warn "Контейнер $CONTAINER_NAME не запущен"
    fi
}

# Основная логика
case "${1:-run}" in
    "build")
        build_image
        ;;
    "run")
        build_image
        run_container
        sleep 5
        check_status
        ;;
    "stop")
        stop_container
        ;;
    "logs")
        show_logs
        ;;
    "status")
        check_status
        ;;
    "clean")
        stop_container
        cleanup
        ;;
    "restart")
        stop_container
        sleep 2
        build_image
        run_container
        sleep 5
        check_status
        ;;
    *)
        echo -e "${BLUE}Использование:${NC} $0 [build|run|stop|logs|status|clean|restart]"
        echo ""
        echo -e "${BLUE}Команды:${NC}"
        echo "  build   - Собрать Docker образ"
        echo "  run     - Собрать и запустить контейнер (по умолчанию)"
        echo "  stop    - Остановить контейнер"
        echo "  logs    - Показать логи контейнера"
        echo "  status  - Проверить статус службы"
        echo "  clean   - Остановить контейнер и очистить ресурсы"
        echo "  restart - Перезапустить службу"
        echo ""
        echo -e "${BLUE}Переменные окружения:${NC}"
        echo "  REDIS_URL     - URL для подключения к Redis"
        echo "  DATABASE_URL  - URL для подключения к PostgreSQL"
        ;;
esac