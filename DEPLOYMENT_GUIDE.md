# FACEIT Bot - Production Deployment Guide

## Overview

This guide covers the complete deployment of the FACEIT Telegram Bot with enterprise-grade architecture including:

- **Multi-container Docker deployment** with orchestration
- **Background worker processes** with RQ (Redis Queue) 
- **PostgreSQL database** with async SQLAlchemy
- **Redis caching** with distributed architecture
- **Automated scaling** and monitoring
- **Zero-downtime deployments** with rollback capability

## Architecture Summary

### System Components

1. **Main Bot Service** (`faceit-bot`)
   - Telegram Bot API handling
   - User command processing 
   - Task dispatch to worker queues

2. **Worker Services**
   - `worker-priority`: Critical & high priority tasks
   - `worker-default`: Standard background tasks  
   - `worker-bulk`: Low priority bulk operations

3. **Infrastructure Services**
   - `redis`: Caching and task queues
   - `postgres`: Primary data storage
   - `rq-dashboard`: Queue monitoring UI

### Technology Stack

- **Python 3.13** - Latest Python with performance improvements
- **aiogram 3.x** - Async Telegram Bot framework
- **PostgreSQL 15** - Primary database with async drivers
- **Redis 7** - Caching and task queue backend
- **RQ (Redis Queue)** - Background task processing
- **Docker & Docker Compose** - Container orchestration
- **SQLAlchemy 2.0** - Async ORM with repository pattern

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 20.04+ recommended), macOS, or Windows with WSL2
- **RAM**: 2GB minimum, 4GB recommended
- **CPU**: 2 cores minimum, 4 cores recommended  
- **Disk**: 10GB free space minimum
- **Network**: Stable internet connection

### Required Software

```bash
# Docker & Docker Compose
sudo apt update
sudo apt install docker.io docker-compose
sudo systemctl start docker
sudo usermod -aG docker $USER

# Python 3.11+ (for management scripts)
sudo apt install python3 python3-pip

# Git (for repository management)
sudo apt install git
```

### Required Credentials

1. **Telegram Bot Token** - From @BotFather
2. **FACEIT API Key** - From developers.faceit.com  
3. **Database Credentials** - Generated during setup
4. **Redis Password** - Generated during setup

## Installation Steps

### 1. Clone and Setup Repository

```bash
# Clone repository
git clone <repository-url>
cd faceit-telegram-bot

# Create environment file
cp .env.example .env.docker
```

### 2. Configure Environment

Edit `.env.docker` with your credentials:

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# FACEIT API
FACEIT_API_KEY=your_faceit_api_key_here

# Database Configuration  
DATABASE_URL=postgresql+asyncpg://faceit_user:faceit_password@postgres:5432/faceit_bot
DB_HOST=postgres
DB_PORT=5432
DB_NAME=faceit_bot
DB_USER=faceit_user
DB_PASSWORD=faceit_password

# Redis Configuration
REDIS_URL=redis://redis:6379/0
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=faceit_redis_2024

# Application Settings
LOG_LEVEL=INFO
CHECK_INTERVAL_MINUTES=10
QUEUE_MAX_WORKERS=3
ENABLE_MONITORING=true
```

### 3. Deploy Services

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Run full deployment
./scripts/deploy.sh

# Or step by step:
./scripts/manage_workers.sh start
```

### 4. Verify Deployment

```bash
# Check service status
./scripts/manage_workers.sh status

# Check service health
./scripts/manage_workers.sh health

# View logs
./scripts/manage_workers.sh logs all

# Check worker queues
./scripts/manage_workers.sh worker-status
```

## Service Management

### Basic Operations

```bash
# Start all services
./scripts/manage_workers.sh start

# Stop all services  
./scripts/manage_workers.sh stop

# Restart services
./scripts/manage_workers.sh restart

# View status
./scripts/manage_workers.sh status
```

### Scaling Workers

```bash
# Scale default workers to 3 instances
./scripts/manage_workers.sh scale worker-default=3

# Scale priority workers to 2 instances  
./scripts/manage_workers.sh scale worker-priority=2

# View current scaling
docker-compose ps
```

### Log Management

```bash
# View all logs
./scripts/manage_workers.sh logs all

# View specific service logs
./scripts/manage_workers.sh logs worker-priority

# Follow logs in real-time
docker-compose logs -f faceit-bot
```

## Monitoring and Maintenance

### Built-in Monitoring

1. **RQ Dashboard** - http://localhost:9181
   - Queue status and job history
   - Worker performance metrics
   - Job retry and failure analysis

2. **Queue Monitoring Script**
   ```bash
   python scripts/monitor_workers.py --interval 30
   ```

3. **Worker Autoscaler**
   ```bash
   python scripts/worker_autoscaler.py
   ```

### Health Checks

```bash
# System health check
./scripts/manage_workers.sh health

# Detailed monitoring report
python scripts/monitor_workers.py --report

# Integration test suite
python tests/test_integration.py --verbose
```

### Performance Optimization

#### Database Optimization

```sql
-- Connect to PostgreSQL
docker exec -it faceit-postgres psql -U faceit_user -d faceit_bot

-- Create indexes for better performance
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_faceit_player_id ON users(faceit_player_id);  
CREATE INDEX idx_match_analysis_user_id ON match_analysis(user_id);
CREATE INDEX idx_match_analysis_created_at ON match_analysis(created_at);
```

#### Redis Optimization

```bash
# Connect to Redis  
docker exec -it faceit-redis redis-cli

# Check memory usage
INFO memory

# Monitor performance
MONITOR
```

#### Worker Performance

```bash
# Monitor worker resource usage
docker stats

# Adjust worker scaling based on load
./scripts/manage_workers.sh scale worker-default=5

# Enable autoscaling
python scripts/worker_autoscaler.py &
```

## Security Configuration

### Environment Security

```bash
# Set proper file permissions
chmod 600 .env.docker
chmod 600 config/redis.conf

# Use Docker secrets (production)
docker secret create postgres_password postgres_password.txt
docker secret create redis_password redis_password.txt
```

### Network Security

```yaml
# docker-compose.yml network configuration
networks:
  faceit-network:
    driver: bridge
    internal: true  # Restrict external access
    
# Expose only necessary ports
ports:
  - "127.0.0.1:6379:6379"  # Redis (localhost only)
  - "127.0.0.1:5432:5432"  # PostgreSQL (localhost only)
  - "127.0.0.1:9181:9181"  # RQ Dashboard (localhost only)
```

### Database Security

```sql
-- Create read-only user for monitoring
CREATE ROLE monitoring_user WITH LOGIN PASSWORD 'secure_password';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO monitoring_user;

-- Enable SSL connections (production)
ALTER SYSTEM SET ssl = on;
```

## Backup and Recovery

### Automated Backups

```bash
# Create backup
./scripts/deploy.sh --skip-tests --skip-backup
# Backup is created automatically before deployment

# Manual backup
docker exec faceit-postgres pg_dump -U faceit_user -d faceit_bot > backup_$(date +%Y%m%d).sql
docker exec faceit-redis redis-cli BGSAVE
```

### Restore Procedures

```bash
# Restore from backup  
./scripts/deploy.sh --rollback

# Manual restore
docker exec -i faceit-postgres psql -U faceit_user -d faceit_bot < backup_20241201.sql
```

## Troubleshooting

### Common Issues

#### Bot Not Responding

```bash
# Check bot container status
docker-compose ps faceit-bot

# Check bot logs
docker-compose logs faceit-bot

# Restart bot service
docker-compose restart faceit-bot
```

#### Worker Queue Buildup

```bash
# Check queue status
./scripts/manage_workers.sh worker-status

# Scale up workers
./scripts/manage_workers.sh scale worker-default=5

# Clear queues if needed
python worker.py clear default high
```

#### Database Connection Issues

```bash
# Check PostgreSQL status
docker-compose ps postgres

# Test connection
docker exec faceit-postgres pg_isready -U faceit_user -d faceit_bot

# Check connection limits
docker exec faceit-postgres psql -U faceit_user -d faceit_bot -c "SELECT count(*) FROM pg_stat_activity;"
```

#### Redis Memory Issues

```bash
# Check Redis memory usage
docker exec faceit-redis redis-cli INFO memory

# Clear cache if needed
docker exec faceit-redis redis-cli FLUSHDB

# Adjust Redis memory limit
# Edit config/redis.conf and restart
```

### Log Analysis

```bash
# View error logs only
docker-compose logs | grep ERROR

# Monitor real-time logs
docker-compose logs -f --tail=100

# Export logs for analysis
docker-compose logs > logs_$(date +%Y%m%d_%H%M%S).log
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Run performance tests
python tests/test_integration.py --verbose

# Monitor queue performance
python scripts/monitor_workers.py --status
```

## Scaling for Production

### Horizontal Scaling

```yaml
# docker-compose.override.yml for production scaling
version: '3.8'
services:
  worker-default:
    deploy:
      replicas: 5
      
  worker-priority:
    deploy:
      replicas: 3
      
  worker-bulk:
    deploy:
      replicas: 2
```

### Load Balancing

```bash
# Use Docker Swarm for load balancing
docker swarm init
docker stack deploy -c docker-compose.yml faceit-bot-stack
```

### Multi-Server Deployment

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    deploy:
      placement:
        constraints: [node.role == manager]
        
  postgres:
    image: postgres:15-alpine
    deploy:
      placement:
        constraints: [node.hostname == db-server]
        
  faceit-bot:
    deploy:
      replicas: 2
      placement:
        constraints: [node.role == worker]
```

## Monitoring and Alerting

### Prometheus Integration

```yaml
# monitoring/docker-compose.monitoring.yml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      
  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

### Custom Alerts

```bash
# Setup webhook alerts
export MONITORING_WEBHOOK_URL="https://your-webhook-url"

# Enable monitoring with alerts
python scripts/monitor_workers.py --interval 30 &
```

## Version Management

### Semantic Versioning

```bash
# Update version
./scripts/version.sh patch  # 1.0.0 -> 1.0.1
./scripts/version.sh minor  # 1.0.1 -> 1.1.0  
./scripts/version.sh major  # 1.1.0 -> 2.0.0

# Deploy specific version
VERSION=1.2.0 ./scripts/deploy.sh
```

### Rolling Updates

```bash
# Zero-downtime deployment
./scripts/deploy.sh

# Rollback if needed
./scripts/deploy.sh --rollback

# Check deployment status
./scripts/deploy.sh --status
```

## Support and Maintenance

### Regular Maintenance Tasks

```bash
# Weekly maintenance
./scripts/manage_workers.sh cleanup
docker system prune -f

# Monthly maintenance  
python tests/test_integration.py --output monthly_test_report.json
./scripts/deploy.sh  # Update to latest version

# Database maintenance
docker exec faceit-postgres psql -U faceit_user -d faceit_bot -c "VACUUM ANALYZE;"
```

### Update Procedures

1. **Backup current system**
2. **Run integration tests**  
3. **Deploy to staging environment**
4. **Run acceptance tests**
5. **Deploy to production with rollback plan**
6. **Monitor post-deployment metrics**

### Getting Help

- **Logs**: Check `./scripts/manage_workers.sh logs all`
- **Health**: Run `./scripts/manage_workers.sh health`  
- **Tests**: Execute `python tests/test_integration.py`
- **Monitoring**: Use `python scripts/monitor_workers.py --report`

## Conclusion

This deployment guide provides a complete production-ready setup for the FACEIT Telegram Bot. The architecture supports:

- ✅ **High Availability** - Multiple worker instances with auto-scaling
- ✅ **Performance** - Redis caching and async processing  
- ✅ **Reliability** - Automated backups and rollback capability
- ✅ **Monitoring** - Comprehensive metrics and alerting
- ✅ **Scalability** - Horizontal scaling and load balancing
- ✅ **Security** - Proper isolation and access controls

Follow the maintenance procedures to ensure optimal performance and reliability in production.