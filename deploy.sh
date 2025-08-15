#!/bin/bash

# FACEIT Telegram Bot - Production Deployment Script
# Запускать на VPS после подключения по SSH

set -e  # Exit on error

echo "========================================="
echo "FACEIT Telegram Bot - Production Deploy"
echo "========================================="

# 1. Обновление системы
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# 2. Установка необходимых пакетов
echo "🔧 Installing required packages..."
sudo apt install -y \
    curl \
    git \
    htop \
    nginx \
    certbot \
    python3-certbot-nginx \
    ufw

# 3. Установка Docker
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
else
    echo "✅ Docker already installed"
fi

# 4. Установка Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "🐳 Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
else
    echo "✅ Docker Compose already installed"
fi

# 5. Создание директории для бота
echo "📁 Creating project directory..."
mkdir -p ~/faceit-bot
cd ~/faceit-bot

# 6. Клонирование репозитория
echo "📥 Cloning repository..."
if [ -d ".git" ]; then
    echo "Repository exists, pulling latest changes..."
    git pull origin master
else
    git clone https://github.com/your-username/faceit-telegram-bot.git .
fi

# 7. Настройка environment
echo "⚙️ Setting up environment..."
if [ ! -f .env ]; then
    cp .env.production .env
    echo "❗ Please edit .env file with your credentials"
    nano .env
fi

# 8. Создание директорий для данных
echo "📁 Creating data directories..."
mkdir -p data logs

# 9. Настройка firewall
echo "🔒 Configuring firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 9181/tcp  # RQ Dashboard (опционально)
sudo ufw --force enable

# 10. Запуск бота
echo "🚀 Starting bot..."
docker-compose -f docker-compose.production.yml up -d

# 11. Проверка статуса
echo "✅ Checking status..."
sleep 5
docker-compose -f docker-compose.production.yml ps

# 12. Настройка автозапуска
echo "⚙️ Setting up auto-restart..."
cat > /tmp/faceit-bot.service << EOF
[Unit]
Description=FACEIT Telegram Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/$USER/faceit-bot
ExecStart=/usr/local/bin/docker-compose -f docker-compose.production.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.production.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/faceit-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable faceit-bot.service

echo "========================================="
echo "✅ Deployment completed successfully!"
echo "========================================="
echo ""
echo "📊 Useful commands:"
echo "  View logs:        docker-compose -f docker-compose.production.yml logs -f"
echo "  Restart bot:      docker-compose -f docker-compose.production.yml restart"
echo "  Stop bot:         docker-compose -f docker-compose.production.yml down"
echo "  Check status:     docker-compose -f docker-compose.production.yml ps"
echo ""
echo "🔗 Your bot: @faceitstatsme_bot"
echo "🔗 RQ Dashboard: http://your-vps-ip:9181"
echo ""