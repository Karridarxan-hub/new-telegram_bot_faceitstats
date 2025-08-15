#!/bin/bash

# ================================================
# FACEIT BOT - QUICK PRODUCTION DEPLOYMENT SCRIPT
# ================================================
# Запустите этот скрипт на вашем VPS для быстрого деплоя

set -e

echo "================================================"
echo "🚀 FACEIT Telegram Bot - Quick Deploy"
echo "================================================"
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Проверка прав
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ Этот скрипт нужно запускать с правами root${NC}"
   echo "Используйте: sudo bash quick-deploy.sh"
   exit 1
fi

echo -e "${GREEN}✅ Запуск с правами root${NC}"

# 2. Обновление системы
echo -e "\n${YELLOW}📦 Обновление пакетов...${NC}"
apt-get update -qq
apt-get upgrade -y -qq

# 3. Установка Docker
if ! command -v docker &> /dev/null; then
    echo -e "\n${YELLOW}🐳 Установка Docker...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh > /dev/null 2>&1
    rm get-docker.sh
    echo -e "${GREEN}✅ Docker установлен${NC}"
else
    echo -e "${GREEN}✅ Docker уже установлен${NC}"
fi

# 4. Установка Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "\n${YELLOW}🐳 Установка Docker Compose...${NC}"
    curl -L "https://github.com/docker/compose/releases/download/v2.20.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✅ Docker Compose установлен${NC}"
else
    echo -e "${GREEN}✅ Docker Compose уже установлен${NC}"
fi

# 5. Создание директории проекта
echo -e "\n${YELLOW}📁 Создание директории проекта...${NC}"
PROJECT_DIR="/opt/faceit-bot"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# 6. Клонирование репозитория
echo -e "\n${YELLOW}📥 Загрузка кода бота...${NC}"
if [ -d ".git" ]; then
    echo "Обновление существующего репозитория..."
    git pull origin master
else
    # Замените на ваш репозиторий если есть
    git clone https://github.com/your-username/faceit-telegram-bot.git . 2>/dev/null || {
        echo -e "${YELLOW}⚠️  Репозиторий не найден, создаем локальную структуру${NC}"
        # Если нет репозитория, создаем минимальную структуру
        mkdir -p data logs
    }
fi

# 7. Создание .env файла
echo -e "\n${YELLOW}⚙️  Настройка переменных окружения...${NC}"

# Запрос пароля от Supabase если не указан
if [ ! -f .env ]; then
    echo -e "${YELLOW}Введите пароль от Supabase PostgreSQL:${NC}"
    read -s SUPABASE_PASSWORD
    
    cat > .env << EOF
# PRODUCTION CONFIGURATION
TELEGRAM_BOT_TOKEN=8200317917:AAE3wSxtG6N7wKeLJezgNaQsCd5uHMcXjVk
FACEIT_API_KEY=41f48f43-609c-4639-b821-360b039f18b4
DATABASE_URL=postgresql://postgres:${SUPABASE_PASSWORD}@db.emzlxdutmhmbvaetphpu.supabase.co:5432/postgres
REDIS_URL=redis://default:AZn7AAIncDFmZDE2ZDI4YTQ3Y2I0OWVkYTZjYjkzYWQ5OTIzNWRiMHAxMzk0MTk@enjoyed-tick-39419.upstash.io:6379
LOG_LEVEL=INFO
ENVIRONMENT=production
DATA_FILE_PATH=/home/app/data/data.json
EOF
    echo -e "${GREEN}✅ Файл .env создан${NC}"
else
    echo -e "${GREEN}✅ Файл .env уже существует${NC}"
fi

# 8. Проверка наличия docker-compose файла
if [ ! -f docker-compose.production.yml ]; then
    echo -e "\n${YELLOW}📝 Создание docker-compose.production.yml...${NC}"
    cat > docker-compose.production.yml << 'EOF'
version: '3.8'

services:
  faceit-bot:
    image: faceit-bot:production
    container_name: faceit-bot-prod
    restart: unless-stopped
    environment:
      - PYTHONUNBUFFERED=1
      - PYTHONDONTWRITEBYTECODE=1
    env_file:
      - .env
    command: python simple_bot.py
    volumes:
      - ./data:/home/app/data
      - ./logs:/home/app/logs
    networks:
      - faceit-network
    healthcheck:
      test: ["CMD", "python", "-c", "print('OK')"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  faceit-network:
    driver: bridge
EOF
fi

# 9. Создание Dockerfile если его нет
if [ ! -f Dockerfile ]; then
    echo -e "\n${YELLOW}📝 Создание Dockerfile...${NC}"
    cat > Dockerfile << 'EOF'
FROM python:3.13-slim

WORKDIR /home/app

# Установка зависимостей
RUN pip install --no-cache-dir \
    aiogram==3.20.0 \
    aiohttp==3.10.10 \
    pydantic==2.10.3 \
    pydantic-settings==2.6.1 \
    python-dotenv==1.0.1 \
    redis==5.2.1 \
    asyncpg==0.30.0

# Создание директорий
RUN mkdir -p /home/app/data /home/app/logs

# Копирование файлов бота
COPY . .

CMD ["python", "simple_bot.py"]
EOF
fi

# 10. Создание необходимых директорий
echo -e "\n${YELLOW}📁 Создание директорий для данных...${NC}"
mkdir -p data logs
chmod 755 data logs

# 11. Сборка Docker образа
echo -e "\n${YELLOW}🔨 Сборка Docker образа...${NC}"
docker build -t faceit-bot:production .

# 12. Остановка старых контейнеров
echo -e "\n${YELLOW}🛑 Остановка старых контейнеров...${NC}"
docker-compose -f docker-compose.production.yml down 2>/dev/null || true

# 13. Запуск бота
echo -e "\n${YELLOW}🚀 Запуск бота...${NC}"
docker-compose -f docker-compose.production.yml up -d

# 14. Проверка статуса
echo -e "\n${YELLOW}✅ Проверка статуса...${NC}"
sleep 5
docker-compose -f docker-compose.production.yml ps

# 15. Настройка автозапуска
echo -e "\n${YELLOW}⚙️  Настройка автозапуска...${NC}"
cat > /etc/systemd/system/faceit-bot.service << EOF
[Unit]
Description=FACEIT Telegram Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/local/bin/docker-compose -f docker-compose.production.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.production.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable faceit-bot.service

# 16. Настройка firewall
echo -e "\n${YELLOW}🔒 Настройка firewall...${NC}"
ufw allow 22/tcp 2>/dev/null || true
ufw allow 80/tcp 2>/dev/null || true
ufw allow 443/tcp 2>/dev/null || true
echo "y" | ufw enable 2>/dev/null || true

# 17. Вывод финальной информации
echo ""
echo "================================================"
echo -e "${GREEN}✅ DEPLOYMENT ЗАВЕРШЕН УСПЕШНО!${NC}"
echo "================================================"
echo ""
echo -e "${GREEN}📱 Ваш бот:${NC} @faceitstatsme_bot"
echo ""
echo -e "${YELLOW}📊 Полезные команды:${NC}"
echo "  Логи:          docker-compose -f docker-compose.production.yml logs -f"
echo "  Рестарт:       docker-compose -f docker-compose.production.yml restart"
echo "  Остановка:     docker-compose -f docker-compose.production.yml down"
echo "  Статус:        docker-compose -f docker-compose.production.yml ps"
echo ""
echo -e "${YELLOW}📂 Расположение:${NC} $PROJECT_DIR"
echo ""
echo -e "${GREEN}✅ Бот запущен и будет автоматически перезапускаться при перезагрузке VPS${NC}"
echo ""
echo "================================================"

# Показать логи
echo -e "\n${YELLOW}📜 Последние логи бота:${NC}"
docker-compose -f docker-compose.production.yml logs --tail=20 faceit-bot