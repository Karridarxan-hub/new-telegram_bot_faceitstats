# Complete Cloud Migration & Development Workflow Guide
## FACEIT Telegram Bot - Production-Ready Implementation

---

## 📋 Table of Contents
1. [Executive Summary](#executive-summary)
2. [Infrastructure Architecture](#infrastructure-architecture)
3. [DigitalOcean Setup](#digitalocean-setup)
4. [GitHub Repository Structure](#github-repository-structure)
5. [CI/CD Pipeline Implementation](#cicd-pipeline-implementation)
6. [Development Workflow](#development-workflow)
7. [Bug Fixing Process](#bug-fixing-process)
8. [Database Migration Strategy](#database-migration-strategy)
9. [Rollback Procedures](#rollback-procedures)
10. [Monitoring & Alerting](#monitoring--alerting)
11. [Cost Breakdown](#cost-breakdown)
12. [Security & Backup Strategy](#security--backup-strategy)
13. [Quick Start Commands](#quick-start-commands)

---

## Executive Summary

This guide provides a complete, production-ready cloud migration solution for the FACEIT Telegram Bot project, designed for a solo developer or small team with limited budget. The solution uses DigitalOcean for infrastructure, GitHub Actions for CI/CD, and implements a safe staging/production separation.

### Key Features:
- **Total Monthly Cost**: $35-45 (staging + production)
- **Zero-downtime deployments**
- **Automatic rollback on failures**
- **Complete monitoring and alerting**
- **Database migration safety**
- **Development → Staging → Production workflow**

---

## Infrastructure Architecture

```mermaid
graph TB
    subgraph "Development Environment"
        DEV[Local Development<br/>Windows/Docker]
    end
    
    subgraph "GitHub"
        REPO[GitHub Repository]
        ACTIONS[GitHub Actions CI/CD]
    end
    
    subgraph "DigitalOcean - Staging"
        STAGING_DROP[Staging Droplet<br/>$6/month]
        STAGING_DB[Managed PostgreSQL<br/>Dev Plan $15/month]
        STAGING_REDIS[Redis on Droplet]
    end
    
    subgraph "DigitalOcean - Production"
        PROD_DROP[Production Droplet<br/>$12/month]
        PROD_DB[Managed PostgreSQL<br/>Basic Plan $15/month]
        PROD_REDIS[Redis on Droplet]
        BACKUP[Automated Backups]
    end
    
    subgraph "Monitoring"
        DO_MONITOR[DigitalOcean Monitoring]
        UPTIME[UptimeRobot Free]
        ALERTS[Email/Telegram Alerts]
    end
    
    DEV --> |Push| REPO
    REPO --> |Trigger| ACTIONS
    ACTIONS --> |Deploy Dev Branch| STAGING_DROP
    ACTIONS --> |Deploy Main Branch| PROD_DROP
    PROD_DROP --> BACKUP
    STAGING_DROP --> DO_MONITOR
    PROD_DROP --> DO_MONITOR
    DO_MONITOR --> ALERTS
    UPTIME --> ALERTS
```

---

## DigitalOcean Setup

### Step 1: Create DigitalOcean Account
```bash
# Sign up at https://digitalocean.com
# Use referral link for $200 credit: https://m.do.co/c/your-referral
```

### Step 2: Create Staging Environment

#### 2.1 Create Staging Droplet
```bash
# Via DigitalOcean CLI (doctl)
doctl compute droplet create faceit-bot-staging \
  --region nyc3 \
  --size s-1vcpu-1gb \
  --image ubuntu-22-04-x64 \
  --ssh-keys $(doctl compute ssh-key list --format ID --no-header) \
  --tag-names faceit-bot,staging \
  --user-data-file cloud-init-staging.yaml
```

#### 2.2 Create cloud-init-staging.yaml
```yaml
#cloud-config
package_update: true
package_upgrade: true

packages:
  - docker.io
  - docker-compose
  - git
  - htop
  - ufw
  - fail2ban
  - nginx
  - certbot
  - python3-certbot-nginx

users:
  - name: deploy
    groups: docker
    shell: /bin/bash
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    ssh_authorized_keys:
      - ssh-rsa YOUR_SSH_PUBLIC_KEY

runcmd:
  # Configure firewall
  - ufw allow OpenSSH
  - ufw allow http
  - ufw allow https
  - ufw --force enable
  
  # Configure Docker
  - systemctl enable docker
  - systemctl start docker
  
  # Create app directory
  - mkdir -p /opt/faceit-bot
  - chown deploy:deploy /opt/faceit-bot
  
  # Setup swap (for small droplets)
  - fallocate -l 2G /swapfile
  - chmod 600 /swapfile
  - mkswap /swapfile
  - swapon /swapfile
  - echo '/swapfile none swap sw 0 0' >> /etc/fstab
  
  # Install monitoring agent
  - curl -sSL https://repos.insights.digitalocean.com/install.sh | sudo bash

write_files:
  - path: /etc/systemd/system/faceit-bot.service
    content: |
      [Unit]
      Description=FACEIT Telegram Bot
      After=docker.service
      Requires=docker.service
      
      [Service]
      Type=simple
      Restart=always
      RestartSec=10
      User=deploy
      WorkingDirectory=/opt/faceit-bot
      ExecStart=/usr/bin/docker-compose up
      ExecStop=/usr/bin/docker-compose down
      
      [Install]
      WantedBy=multi-user.target
```

### Step 3: Create Production Environment

#### 3.1 Create Production Droplet
```bash
doctl compute droplet create faceit-bot-production \
  --region nyc3 \
  --size s-1vcpu-2gb \
  --image ubuntu-22-04-x64 \
  --ssh-keys $(doctl compute ssh-key list --format ID --no-header) \
  --tag-names faceit-bot,production \
  --user-data-file cloud-init-production.yaml \
  --enable-backups
```

### Step 4: Create Managed Database

#### 4.1 Staging Database
```bash
doctl databases create faceit-bot-staging \
  --engine pg \
  --region nyc3 \
  --size db-s-1vcpu-1gb \
  --version 15 \
  --num-nodes 1
```

#### 4.2 Production Database with Read Replica
```bash
doctl databases create faceit-bot-production \
  --engine pg \
  --region nyc3 \
  --size db-s-1vcpu-2gb \
  --version 15 \
  --num-nodes 1

# Add read replica for production
doctl databases replica create <db-id> faceit-bot-replica \
  --size db-s-1vcpu-1gb
```

### Step 5: Configure Spaces for Backups
```bash
# Create Space for backups
doctl spaces create faceit-bot-backups --region nyc3

# Generate access keys
doctl spaces access-key create
```

---

## GitHub Repository Structure

### Branching Strategy
```
main (production)
├── develop (staging)
│   ├── feature/new-feature
│   ├── bugfix/fix-issue
│   └── hotfix/urgent-fix
└── release/v1.2.0
```

### Repository Structure
```
faceit-telegram-bot/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # Continuous Integration
│   │   ├── cd-staging.yml      # Deploy to Staging
│   │   ├── cd-production.yml   # Deploy to Production
│   │   ├── backup.yml          # Automated Backups
│   │   └── security.yml        # Security Scanning
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── dependabot.yml
├── infrastructure/
│   ├── terraform/              # IaC for DigitalOcean
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── staging.tfvars
│   │   └── production.tfvars
│   ├── ansible/               # Configuration Management
│   │   ├── playbooks/
│   │   └── inventory/
│   └── scripts/
│       ├── deploy.sh
│       ├── rollback.sh
│       └── backup.sh
├── docker/
│   ├── Dockerfile.staging
│   ├── Dockerfile.production
│   ├── docker-compose.staging.yml
│   └── docker-compose.production.yml
├── src/                       # Application code
├── tests/
├── docs/
├── .env.example
├── .gitignore
└── README.md
```

---

## CI/CD Pipeline Implementation

### GitHub Actions Workflows

#### 1. Continuous Integration (.github/workflows/ci.yml)
```yaml
name: CI Pipeline

on:
  push:
    branches: [develop, main]
  pull_request:
    branches: [develop, main]

env:
  PYTHON_VERSION: '3.13'
  NODE_VERSION: '18'

jobs:
  lint:
    name: Lint Code
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Cache pip packages
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ruff black mypy
          pip install -r requirements.txt
      
      - name: Run Ruff
        run: ruff check .
      
      - name: Run Black
        run: black --check .
      
      - name: Run MyPy
        run: mypy --ignore-missing-imports .

  test:
    name: Run Tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: testdb
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      
      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://postgres:testpass@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379
          TELEGRAM_BOT_TOKEN: ${{ secrets.TEST_BOT_TOKEN }}
          FACEIT_API_KEY: ${{ secrets.TEST_FACEIT_API_KEY }}
        run: |
          pytest tests/ --cov=. --cov-report=xml --cov-report=html
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          file: ./coverage.xml

  security:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'
      
      - name: Run Snyk security scan
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=high

  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    needs: [lint, test, security]
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to DockerHub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ secrets.DOCKER_USERNAME }}/faceit-bot
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix={{branch}}-
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=registry,ref=${{ secrets.DOCKER_USERNAME }}/faceit-bot:buildcache
          cache-to: type=registry,ref=${{ secrets.DOCKER_USERNAME }}/faceit-bot:buildcache,mode=max
          build-args: |
            VERSION=${{ github.sha }}
```

#### 2. Deploy to Staging (.github/workflows/cd-staging.yml)
```yaml
name: Deploy to Staging

on:
  push:
    branches: [develop]
  workflow_dispatch:
    inputs:
      version:
        description: 'Version to deploy'
        required: false
        default: 'latest'

jobs:
  deploy:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.8.0
        with:
          ssh-private-key: ${{ secrets.STAGING_SSH_KEY }}
      
      - name: Add server to known hosts
        run: |
          mkdir -p ~/.ssh
          ssh-keyscan -H ${{ secrets.STAGING_HOST }} >> ~/.ssh/known_hosts
      
      - name: Create deployment package
        run: |
          tar -czf deploy.tar.gz \
            docker-compose.staging.yml \
            .env.staging \
            infrastructure/scripts/deploy.sh
      
      - name: Copy files to server
        run: |
          scp deploy.tar.gz deploy@${{ secrets.STAGING_HOST }}:/opt/faceit-bot/
          ssh deploy@${{ secrets.STAGING_HOST }} "cd /opt/faceit-bot && tar -xzf deploy.tar.gz"
      
      - name: Deploy application
        run: |
          ssh deploy@${{ secrets.STAGING_HOST }} "cd /opt/faceit-bot && bash infrastructure/scripts/deploy.sh staging"
      
      - name: Health check
        run: |
          sleep 30
          curl -f http://${{ secrets.STAGING_HOST }}/health || exit 1
      
      - name: Run smoke tests
        run: |
          npm install -g newman
          newman run tests/postman/staging-smoke-tests.json
      
      - name: Notify deployment
        if: always()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Staging deployment ${{ job.status }}'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

#### 3. Deploy to Production (.github/workflows/cd-production.yml)
```yaml
name: Deploy to Production

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:
    inputs:
      version:
        description: 'Version tag to deploy'
        required: true

jobs:
  approval:
    name: Request Approval
    runs-on: ubuntu-latest
    environment: production-approval
    steps:
      - name: Request manual approval
        run: echo "Waiting for manual approval..."

  backup:
    name: Backup Current Production
    runs-on: ubuntu-latest
    needs: approval
    steps:
      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.8.0
        with:
          ssh-private-key: ${{ secrets.PRODUCTION_SSH_KEY }}
      
      - name: Backup database
        run: |
          ssh deploy@${{ secrets.PRODUCTION_HOST }} "
            cd /opt/faceit-bot && 
            docker-compose exec -T postgres pg_dump -U faceit_user faceit_bot | 
            gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz &&
            aws s3 cp backup-*.sql.gz s3://faceit-bot-backups/
          "
      
      - name: Backup application data
        run: |
          ssh deploy@${{ secrets.PRODUCTION_HOST }} "
            cd /opt/faceit-bot && 
            tar -czf data-backup-$(date +%Y%m%d-%H%M%S).tar.gz data/ &&
            aws s3 cp data-backup-*.tar.gz s3://faceit-bot-backups/
          "

  deploy:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: backup
    environment: production
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.inputs.version || github.ref }}
      
      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.8.0
        with:
          ssh-private-key: ${{ secrets.PRODUCTION_SSH_KEY }}
      
      - name: Blue-Green Deployment
        run: |
          ssh deploy@${{ secrets.PRODUCTION_HOST }} "
            cd /opt/faceit-bot &&
            
            # Pull new image
            docker pull ${{ secrets.DOCKER_USERNAME }}/faceit-bot:${{ github.event.inputs.version || github.ref_name }} &&
            
            # Start new containers (green)
            docker-compose -f docker-compose.production.yml -p faceit-bot-green up -d &&
            
            # Wait for health check
            sleep 30 &&
            
            # Run migrations
            docker-compose -f docker-compose.production.yml -p faceit-bot-green exec -T faceit-bot python run_migrations.py &&
            
            # Switch traffic (update nginx)
            sudo nginx -s reload &&
            
            # Stop old containers (blue)
            docker-compose -f docker-compose.production.yml -p faceit-bot-blue down &&
            
            # Rename green to blue for next deployment
            docker-compose -f docker-compose.production.yml -p faceit-bot-green down &&
            docker-compose -f docker-compose.production.yml -p faceit-bot-blue up -d
          "
      
      - name: Verify deployment
        run: |
          sleep 30
          response=$(curl -s http://${{ secrets.PRODUCTION_HOST }}/health)
          if [[ "$response" != *"healthy"* ]]; then
            echo "Health check failed, initiating rollback"
            exit 1
          fi
      
      - name: Run production tests
        run: |
          npm install -g newman
          newman run tests/postman/production-smoke-tests.json

  rollback:
    name: Rollback if Failed
    runs-on: ubuntu-latest
    needs: deploy
    if: failure()
    steps:
      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.8.0
        with:
          ssh-private-key: ${{ secrets.PRODUCTION_SSH_KEY }}
      
      - name: Rollback deployment
        run: |
          ssh deploy@${{ secrets.PRODUCTION_HOST }} "
            cd /opt/faceit-bot &&
            bash infrastructure/scripts/rollback.sh
          "
      
      - name: Notify rollback
        uses: 8398a7/action-slack@v3
        with:
          status: 'failure'
          text: 'Production deployment failed and rolled back!'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

---

## Development Workflow

### Local Development Setup

#### 1. Clone Repository
```bash
git clone https://github.com/yourusername/faceit-telegram-bot.git
cd faceit-telegram-bot
```

#### 2. Setup Development Environment
```bash
# Create Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Setup pre-commit hooks
pre-commit install
```

#### 3. Configure Environment Variables
```bash
# Copy example environment
cp .env.example .env.local

# Edit with your local settings
nano .env.local
```

#### 4. Start Local Services
```bash
# Start local Docker services
docker-compose -f docker-compose.local.yml up -d

# Or use individual services
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=localpass postgres:15
docker run -d -p 6379:6379 redis:7-alpine
```

### Daily Development Workflow

#### 1. Start New Feature
```bash
# Update develop branch
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b feature/new-awesome-feature

# Make changes
code .  # Open in VS Code
```

#### 2. Test Locally
```bash
# Run tests
pytest tests/ -v

# Run linting
ruff check .
black .

# Test with Docker
docker-compose -f docker-compose.local.yml up --build
```

#### 3. Commit Changes
```bash
# Stage changes
git add .

# Commit with conventional commits
git commit -m "feat: add new awesome feature

- Implemented X functionality
- Added Y configuration
- Updated Z documentation"
```

#### 4. Push and Create PR
```bash
# Push feature branch
git push origin feature/new-awesome-feature

# Create PR via GitHub CLI
gh pr create \
  --base develop \
  --title "feat: add new awesome feature" \
  --body "## Description\n\nAdded new awesome feature\n\n## Testing\n- [x] Unit tests pass\n- [x] Integration tests pass\n- [x] Manual testing completed"
```

#### 5. After PR Approval
```bash
# Merge to develop (auto-deploys to staging)
gh pr merge --squash

# After staging validation, create release
git checkout develop
git pull origin develop
git checkout -b release/v1.2.0

# Update version
echo "1.2.0" > VERSION
git commit -am "chore: bump version to 1.2.0"

# Merge to main
git checkout main
git merge --no-ff release/v1.2.0
git tag -a v1.2.0 -m "Release version 1.2.0"
git push origin main --tags
```

---

## Bug Fixing Process

### Hotfix for Production Issues

#### 1. Create Hotfix Branch
```bash
# Start from main (production)
git checkout main
git pull origin main
git checkout -b hotfix/critical-bug-fix
```

#### 2. Fix and Test
```bash
# Make fix
nano src/problematic_file.py

# Test locally
pytest tests/test_specific_bug.py

# Test with production-like environment
docker-compose -f docker-compose.production.yml up --build
```

#### 3. Deploy Hotfix
```bash
# Commit fix
git commit -am "fix: resolve critical bug in payment processing"

# Push and create PR directly to main
git push origin hotfix/critical-bug-fix
gh pr create --base main --title "Hotfix: Critical bug in payment processing"

# After approval, merge and tag
git checkout main
git merge --no-ff hotfix/critical-bug-fix
git tag -a v1.1.1 -m "Hotfix: Critical bug fix"
git push origin main --tags

# Merge back to develop
git checkout develop
git merge main
git push origin develop
```

### Standard Bug Fix Process

#### 1. Create Bug Fix Branch
```bash
git checkout develop
git pull origin develop
git checkout -b bugfix/issue-123-user-stats
```

#### 2. Reproduce Bug
```bash
# Create test that reproduces bug
cat > tests/test_bug_123.py << 'EOF'
import pytest
from bot.handlers import get_user_stats

def test_user_stats_bug():
    """Test for issue #123: User stats showing incorrect values"""
    result = get_user_stats(user_id=12345)
    assert result['wins'] >= 0  # Should never be negative
EOF

# Run test (should fail)
pytest tests/test_bug_123.py
```

#### 3. Fix Bug
```bash
# Make fix
# ... edit files ...

# Verify fix
pytest tests/test_bug_123.py  # Should pass now
```

#### 4. Submit Fix
```bash
git add .
git commit -m "fix: ensure user stats are never negative

Fixes #123"
git push origin bugfix/issue-123-user-stats
```

---

## Database Migration Strategy

### Migration Files Structure
```
alembic/
├── versions/
│   ├── 001_initial_schema.py
│   ├── 002_add_subscriptions.py
│   ├── 003_add_indexes.py
│   └── 004_add_analytics.py
├── alembic.ini
├── env.py
└── script.py.mako
```

### Creating New Migration
```bash
# Generate migration
alembic revision --autogenerate -m "add new feature tables"

# Review generated migration
cat alembic/versions/xxx_add_new_feature_tables.py

# Test migration locally
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

### Safe Production Migration Process

#### 1. Pre-Migration Backup
```bash
# Backup production database
ssh deploy@production "
  pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME | gzip > backup-pre-migration-$(date +%Y%m%d).sql.gz
  aws s3 cp backup-pre-migration-*.sql.gz s3://faceit-bot-backups/migrations/
"
```

#### 2. Test Migration on Staging
```bash
# Deploy to staging first
git push origin develop

# Run migration on staging
ssh deploy@staging "
  cd /opt/faceit-bot
  docker-compose exec faceit-bot alembic upgrade head
"

# Verify staging works correctly
# Run comprehensive tests
```

#### 3. Production Migration
```bash
# During low-traffic period
ssh deploy@production "
  cd /opt/faceit-bot
  
  # Put app in maintenance mode
  touch maintenance.flag
  
  # Run migration
  docker-compose exec faceit-bot alembic upgrade head
  
  # Remove maintenance mode
  rm maintenance.flag
"
```

#### 4. Migration Rollback Plan
```bash
# If migration fails
ssh deploy@production "
  # Rollback migration
  docker-compose exec faceit-bot alembic downgrade -1
  
  # If database is corrupted, restore from backup
  gunzip < backup-pre-migration-*.sql.gz | psql -h $DB_HOST -U $DB_USER -d $DB_NAME
"
```

---

## Rollback Procedures

### Automatic Rollback Script
```bash
#!/bin/bash
# infrastructure/scripts/rollback.sh

set -e

echo "Starting rollback procedure..."

# Get previous version
PREVIOUS_VERSION=$(docker images --format "table {{.Tag}}" | grep -v latest | head -n 2 | tail -n 1)

echo "Rolling back to version: $PREVIOUS_VERSION"

# Stop current deployment
docker-compose -p faceit-bot-current down

# Start previous version
docker pull faceit-bot:$PREVIOUS_VERSION
docker-compose -p faceit-bot-previous up -d

# Verify rollback
sleep 30
if curl -f http://localhost/health; then
    echo "Rollback successful"
    
    # Clean up failed deployment
    docker image prune -f
else
    echo "Rollback failed! Manual intervention required!"
    exit 1
fi

# Notify team
curl -X POST $SLACK_WEBHOOK -d "{\"text\": \"Production rolled back to $PREVIOUS_VERSION\"}"
```

### Manual Rollback Procedures

#### 1. Application Rollback
```bash
# SSH to production
ssh deploy@production

# List available versions
docker images faceit-bot

# Rollback to specific version
docker-compose down
docker run -d --name faceit-bot-rollback faceit-bot:v1.0.9
```

#### 2. Database Rollback
```bash
# Rollback last migration
alembic downgrade -1

# Or restore from backup
psql -h localhost -U faceit_user -d faceit_bot < backup-20250815.sql
```

#### 3. Full System Restore
```bash
# Restore from DigitalOcean snapshot
doctl compute droplet-action snapshot <droplet-id> --snapshot-name "pre-deploy-backup"

# Restore database from backup
doctl databases restore <database-id> --backup-id <backup-id>
```

---

## Monitoring & Alerting

### DigitalOcean Monitoring Setup

#### 1. Enable Monitoring
```bash
# Install monitoring agent on droplets
curl -sSL https://repos.insights.digitalocean.com/install.sh | sudo bash
```

#### 2. Configure Alerts
```yaml
# monitoring/alerts.yml
alerts:
  - name: High CPU Usage
    type: v1/insights/droplet/cpu
    compare: GreaterThan
    value: 80
    window: 5m
    entities:
      - faceit-bot-production
    
  - name: Low Memory
    type: v1/insights/droplet/memory
    compare: GreaterThan
    value: 90
    window: 5m
    
  - name: Disk Space
    type: v1/insights/droplet/disk
    compare: GreaterThan
    value: 85
    window: 5m
    
  - name: Database Connection Pool
    type: v1/insights/dbaas/connection_pool
    compare: GreaterThan
    value: 80
    window: 5m
```

### Application Monitoring

#### 1. Health Check Endpoint
```python
# src/monitoring/health.py
from fastapi import FastAPI
from datetime import datetime
import asyncpg
import redis
import psutil

app = FastAPI()

@app.get("/health")
async def health_check():
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    # Check database
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.fetchval("SELECT 1")
        await conn.close()
        checks["checks"]["database"] = "healthy"
    except Exception as e:
        checks["checks"]["database"] = f"unhealthy: {str(e)}"
        checks["status"] = "unhealthy"
    
    # Check Redis
    try:
        r = redis.Redis.from_url(REDIS_URL)
        r.ping()
        checks["checks"]["redis"] = "healthy"
    except Exception as e:
        checks["checks"]["redis"] = f"unhealthy: {str(e)}"
        checks["status"] = "unhealthy"
    
    # Check system resources
    checks["checks"]["cpu_percent"] = psutil.cpu_percent()
    checks["checks"]["memory_percent"] = psutil.virtual_memory().percent
    checks["checks"]["disk_percent"] = psutil.disk_usage('/').percent
    
    return checks

@app.get("/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint"""
    return PlainTextResponse(generate_metrics())
```

#### 2. Logging Configuration
```python
# src/config/logging.py
import logging
import sys
from logging.handlers import RotatingFileHandler
import json

def setup_logging():
    # JSON formatter for structured logging
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_obj = {
                'timestamp': self.formatTime(record),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            if record.exc_info:
                log_obj['exception'] = self.formatException(record.exc_info)
            return json.dumps(log_obj)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    return logger
```

### External Monitoring

#### 1. UptimeRobot Configuration
```yaml
# Free tier: 50 monitors, 5-minute checks
monitors:
  - name: FACEIT Bot Production
    url: https://bot.yourdomain.com/health
    type: HTTP
    interval: 5
    
  - name: FACEIT Bot Staging
    url: https://staging-bot.yourdomain.com/health
    type: HTTP
    interval: 10
    
  - name: Production Database
    url: <database-endpoint>
    type: Port
    port: 5432
    interval: 5
```

#### 2. Telegram Alerts Bot
```python
# src/monitoring/telegram_alerts.py
import asyncio
from aiogram import Bot
import aiohttp

class AlertBot:
    def __init__(self, token, admin_chat_id):
        self.bot = Bot(token=token)
        self.admin_chat_id = admin_chat_id
    
    async def send_alert(self, level, message, details=None):
        emoji = {
            'critical': '🔴',
            'warning': '🟡',
            'info': 'ℹ️',
            'success': '✅'
        }
        
        text = f"{emoji.get(level, '⚪')} *{level.upper()}*\n\n"
        text += f"{message}\n"
        
        if details:
            text += f"\n*Details:*\n```\n{details}\n```"
        
        await self.bot.send_message(
            self.admin_chat_id,
            text,
            parse_mode='Markdown'
        )
    
    async def monitor_health(self):
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get('http://localhost/health') as resp:
                        data = await resp.json()
                        
                        if data['status'] != 'healthy':
                            await self.send_alert(
                                'critical',
                                'Health check failed!',
                                json.dumps(data['checks'], indent=2)
                            )
            except Exception as e:
                await self.send_alert(
                    'critical',
                    'Health check error!',
                    str(e)
                )
            
            await asyncio.sleep(60)  # Check every minute
```

---

## Cost Breakdown

### Monthly Costs (DigitalOcean)

#### Staging Environment
- **Droplet (s-1vcpu-1gb)**: $6/month
- **Managed Database (Dev)**: $15/month (optional, can use droplet)
- **Total Staging**: $6-21/month

#### Production Environment
- **Droplet (s-1vcpu-2gb)**: $12/month
- **Managed Database (Basic)**: $15/month
- **Backups**: $2.40/month (20% of droplet cost)
- **Spaces (100GB)**: $5/month
- **Total Production**: $34.40/month

#### Additional Services
- **Domain**: $12/year (~$1/month)
- **SSL Certificate**: Free (Let's Encrypt)
- **Monitoring**: Free (DigitalOcean + UptimeRobot)
- **CI/CD**: Free (GitHub Actions - 2000 minutes/month)

### Total Monthly Cost
- **Minimal Setup** (shared staging/prod): ~$20/month
- **Recommended Setup**: ~$40-45/month
- **High Availability Setup**: ~$80-100/month

### Cost Optimization Tips

#### 1. Use Reserved Instances
```bash
# Not available on DigitalOcean, but consider:
# - Yearly billing for 10% discount
# - Committed use discounts
```

#### 2. Autoscaling Configuration
```yaml
# infrastructure/autoscaling.yml
autoscaling:
  min_instances: 1
  max_instances: 3
  triggers:
    - metric: cpu_utilization
      threshold: 70
      duration: 5m
    - metric: memory_utilization
      threshold: 80
      duration: 5m
  scale_down:
    cooldown: 10m
    threshold: 30
```

#### 3. Resource Optimization
```python
# Monitor and optimize resource usage
async def optimize_resources():
    # Cache expensive operations
    @cache(ttl=300)
    async def get_user_stats(user_id):
        # Expensive database query
        pass
    
    # Use connection pooling
    async_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        max_queries=50000,
        max_inactive_connection_lifetime=300
    )
    
    # Batch operations
    async def batch_process(items, batch_size=100):
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            await process_batch(batch)
```

---

## Security & Backup Strategy

### Security Implementation

#### 1. Environment Variables Security
```bash
# Never commit .env files
echo ".env*" >> .gitignore

# Use GitHub Secrets for CI/CD
gh secret set TELEGRAM_BOT_TOKEN
gh secret set FACEIT_API_KEY
gh secret set DATABASE_URL
```

#### 2. Network Security
```bash
# Configure UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw allow from 10.0.0.0/8 to any port 5432  # Database access only from private network
ufw --force enable

# Configure Fail2ban
apt-get install fail2ban
systemctl enable fail2ban
```

#### 3. Database Security
```sql
-- Create read-only user for analytics
CREATE USER analytics_user WITH PASSWORD 'strong_password';
GRANT CONNECT ON DATABASE faceit_bot TO analytics_user;
GRANT USAGE ON SCHEMA public TO analytics_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_user;

-- Enable SSL connections
ALTER SYSTEM SET ssl = on;
```

#### 4. API Security
```python
# src/security/rate_limiter.py
from aioredis import Redis
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def check_rate_limit(self, user_id: int, limit: int = 100, window: int = 60):
        key = f"rate_limit:{user_id}"
        current = await self.redis.incr(key)
        
        if current == 1:
            await self.redis.expire(key, window)
        
        if current > limit:
            ttl = await self.redis.ttl(key)
            raise RateLimitExceeded(f"Rate limit exceeded. Try again in {ttl} seconds")
        
        return current
```

### Backup Strategy

#### 1. Automated Daily Backups
```bash
#!/bin/bash
# infrastructure/scripts/backup.sh

set -e

# Configuration
BACKUP_DIR="/backups"
S3_BUCKET="s3://faceit-bot-backups"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d-%H%M%S)

# Database backup
echo "Backing up database..."
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME | gzip > $BACKUP_DIR/db-$DATE.sql.gz

# Application data backup
echo "Backing up application data..."
tar -czf $BACKUP_DIR/data-$DATE.tar.gz /opt/faceit-bot/data

# Redis backup
echo "Backing up Redis..."
redis-cli --rdb $BACKUP_DIR/redis-$DATE.rdb

# Upload to S3
echo "Uploading to S3..."
aws s3 cp $BACKUP_DIR/db-$DATE.sql.gz $S3_BUCKET/database/
aws s3 cp $BACKUP_DIR/data-$DATE.tar.gz $S3_BUCKET/application/
aws s3 cp $BACKUP_DIR/redis-$DATE.rdb $S3_BUCKET/redis/

# Clean old local backups
find $BACKUP_DIR -type f -mtime +7 -delete

# Clean old S3 backups
aws s3 ls $S3_BUCKET/database/ | while read -r line; do
    createDate=$(echo $line | awk '{print $1" "$2}')
    createDate=$(date -d "$createDate" +%s)
    olderThan=$(date -d "$RETENTION_DAYS days ago" +%s)
    if [[ $createDate -lt $olderThan ]]; then
        fileName=$(echo $line | awk '{print $4}')
        aws s3 rm $S3_BUCKET/database/$fileName
    fi
done

echo "Backup completed successfully"
```

#### 2. Backup Verification
```python
# src/monitoring/backup_verify.py
import asyncio
import asyncpg
import boto3
from datetime import datetime, timedelta

async def verify_backup():
    """Verify backup integrity"""
    s3 = boto3.client('s3')
    
    # Check if today's backup exists
    today = datetime.now().strftime('%Y%m%d')
    response = s3.list_objects_v2(
        Bucket='faceit-bot-backups',
        Prefix=f'database/db-{today}'
    )
    
    if 'Contents' not in response:
        raise Exception(f"No backup found for {today}")
    
    # Test restore to temporary database
    backup_file = response['Contents'][0]['Key']
    
    # Download and test restore
    s3.download_file('faceit-bot-backups', backup_file, '/tmp/test-backup.sql.gz')
    
    # Create test database
    conn = await asyncpg.connect('postgresql://postgres@localhost/postgres')
    await conn.execute('CREATE DATABASE backup_test')
    await conn.close()
    
    # Restore backup
    os.system(f'gunzip < /tmp/test-backup.sql.gz | psql backup_test')
    
    # Verify data
    test_conn = await asyncpg.connect('postgresql://postgres@localhost/backup_test')
    count = await test_conn.fetchval('SELECT COUNT(*) FROM users')
    
    if count == 0:
        raise Exception("Backup verification failed: No data in users table")
    
    # Cleanup
    await test_conn.close()
    await conn.execute('DROP DATABASE backup_test')
    
    return True
```

#### 3. Disaster Recovery Plan
```markdown
# Disaster Recovery Runbook

## Recovery Time Objectives
- RTO (Recovery Time Objective): 1 hour
- RPO (Recovery Point Objective): 24 hours

## Recovery Procedures

### 1. Complete System Failure
1. Create new droplet from snapshot
2. Restore database from latest backup
3. Update DNS records
4. Verify application functionality

### 2. Database Corruption
1. Stop application
2. Restore database from backup
3. Run integrity checks
4. Resume application

### 3. Application Failure
1. Check logs for errors
2. Rollback to previous version
3. Restore from application backup if needed
4. Investigate root cause

## Contact Information
- DevOps Lead: +1-xxx-xxx-xxxx
- Database Admin: +1-xxx-xxx-xxxx
- On-call Engineer: Via PagerDuty
```

---

## Quick Start Commands

### Initial Setup (One-Time)
```bash
# 1. Fork and clone repository
gh repo fork original-repo/faceit-telegram-bot
git clone https://github.com/yourusername/faceit-telegram-bot
cd faceit-telegram-bot

# 2. Setup GitHub Secrets
gh secret set TELEGRAM_BOT_TOKEN --body "your-bot-token"
gh secret set FACEIT_API_KEY --body "your-api-key"
gh secret set DOCKER_USERNAME --body "your-docker-username"
gh secret set DOCKER_PASSWORD --body "your-docker-password"
gh secret set STAGING_HOST --body "staging-server-ip"
gh secret set STAGING_SSH_KEY < ~/.ssh/staging_key
gh secret set PRODUCTION_HOST --body "production-server-ip"
gh secret set PRODUCTION_SSH_KEY < ~/.ssh/production_key

# 3. Create DigitalOcean resources
doctl auth init
bash infrastructure/scripts/setup-digitalocean.sh

# 4. Initialize staging
ssh deploy@staging-ip "
  git clone https://github.com/yourusername/faceit-telegram-bot /opt/faceit-bot
  cd /opt/faceit-bot
  docker-compose -f docker-compose.staging.yml up -d
"

# 5. Initialize production
ssh deploy@production-ip "
  git clone https://github.com/yourusername/faceit-telegram-bot /opt/faceit-bot
  cd /opt/faceit-bot
  docker-compose -f docker-compose.production.yml up -d
"
```

### Daily Operations
```bash
# Start new feature
./scripts/new-feature.sh feature-name

# Deploy to staging
git push origin develop

# Deploy to production
./scripts/release.sh v1.2.0

# Check logs
ssh deploy@production "docker logs faceit-bot --tail 100 -f"

# Run migrations
ssh deploy@production "cd /opt/faceit-bot && docker-compose exec faceit-bot alembic upgrade head"

# Backup database
ssh deploy@production "bash /opt/faceit-bot/infrastructure/scripts/backup.sh"

# Monitor health
curl https://bot.yourdomain.com/health | jq

# Scale workers
ssh deploy@production "docker-compose scale worker=3"
```

### Emergency Commands
```bash
# Immediate rollback
ssh deploy@production "bash /opt/faceit-bot/infrastructure/scripts/rollback.sh"

# Stop bot (maintenance mode)
ssh deploy@production "docker-compose stop faceit-bot"

# Emergency backup
ssh deploy@production "pg_dump faceit_bot | gzip > emergency-backup.sql.gz"

# View error logs
ssh deploy@production "grep ERROR /opt/faceit-bot/logs/app.log | tail -50"

# Restart everything
ssh deploy@production "docker-compose restart"

# Check resource usage
ssh deploy@production "docker stats"
```

---

## Conclusion

This comprehensive guide provides a complete, production-ready solution for migrating your FACEIT Telegram Bot to the cloud with proper development workflows. The setup ensures:

1. **Safe Development**: Complete separation between development, staging, and production
2. **Cost-Effective**: ~$40-45/month for full setup
3. **Automated Workflows**: CI/CD pipelines handle testing and deployment
4. **Zero Downtime**: Blue-green deployments ensure no service interruption
5. **Disaster Recovery**: Automated backups and rollback procedures
6. **Monitoring**: Complete observability of your application
7. **Security**: Industry-standard security practices

Follow this guide step-by-step, and you'll have a professional, scalable deployment that prevents the "breaking production" issues you've experienced. The workflow supports both solo developers and small teams, with room to grow as your project scales.

For questions or issues, refer to the specific sections above or consult the emergency commands section for quick troubleshooting.