# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Bot

**Simple Version (Recommended for development):**
```bash
python simple_bot.py              # Simple version with JSON storage
python simple_bot.py | tee bot.log  # With log output to file
```

**Enterprise Version (For production):**
```bash
python main.py                    # Enterprise version with PostgreSQL/Redis/RQ
python main.py | tee bot.log     # With log output to file
```

### Development Setup
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env             # Configure environment variables
```

### Docker Operations

**Simple Docker Setup:**
```bash
docker build -t faceit-bot .
docker-compose -f docker-compose.simple.yml up -d   # Simple version with basic services
docker-compose -f docker-compose.simple.yml down    # Stop simple setup
```

**Enterprise Docker Setup:**
```bash
docker build -t faceit-bot .
docker-compose up -d                     # Full enterprise architecture
docker-compose down                      # Stop all enterprise services
docker-compose -f docker-compose.production.yml up -d  # Production deployment
```

### Database Operations
```bash
python run_migrations.py         # Run Alembic database migrations
python validate_database.py      # Validate database schema
alembic upgrade head            # Manual migration to latest
alembic revision --autogenerate -m "description"  # Create new migration
```

### Queue Worker Management
```bash
python worker.py                 # Start RQ worker for background tasks
python manage_queues.py          # Queue management utilities
python simple_worker.py          # Simple worker for testing
```

### Monitoring Operations
```bash
# Start monitoring dashboard (Enterprise version)
cd monitoring && python monitoring.py    # Start monitoring on port 9181
cd monitoring && ./build-and-run.sh      # Docker monitoring setup

# Access monitoring dashboard
# Local: http://localhost:9181
# Production: http://185.224.132.36:9181

# Monitoring API endpoints
curl http://localhost:9181/api/health     # Health check
curl http://localhost:9181/api/metrics    # System metrics JSON
curl http://localhost:9181/api/errors     # Recent errors
```

### Testing
```bash
python test_match_analysis.py   # Test match analysis functionality
python test_integration.py      # Integration tests
python test_subscription_comprehensive.py  # Subscription system tests
python test_error_handling.py   # Error handling tests
python test_statistics_functionality.py    # Statistics tests
python test_supabase_connectivity.py       # Database connectivity tests
```

### Deployment and Release
```bash
# Windows:
release.bat patch               # Increment patch version (1.0.0 -> 1.0.1)
release.bat minor               # Increment minor version (1.0.0 -> 1.1.0)
release.bat major               # Increment major version (1.0.0 -> 2.0.0)
update.bat                      # Update bot with current version

# Linux:
./deploy.sh                     # Production deployment script
./quick-deploy.sh              # Quick deployment
```

## Architecture Overview

### Core System Design
This is a **FACEIT Telegram Bot** with a subscription-based business model. The architecture follows a modular design with two deployment modes:

**Simple Version** (`simple_bot.py`):
- Single-file implementation with JSON storage
- Suitable for up to 200 users
- Minimal dependencies and infrastructure

**Enterprise Version** (`main.py`):
- Microservices architecture with PostgreSQL, Redis, and RQ queues
- Scalable for 1000+ users
- Background workers, monitoring, and advanced features

### Key Technical Patterns

**Asynchronous Architecture**: 
- All I/O operations use async/await pattern
- `aiohttp` for HTTP requests to FACEIT API
- `aiogram 3.20` for Telegram Bot API with async handlers
- `asyncpg` for database operations
- Semaphore limiting for concurrent requests (max 5)

**Data Flow**:
1. User commands → `bot/handlers.py` (Enterprise) or `simple_bot.py` (Simple)
2. FACEIT API calls → `faceit/api.py` with caching layer
3. Data processing → `utils/formatter.py` and analyzers
4. Queue tasks → `queues/` for background processing (Enterprise only)
5. Response formatting → back to user via Telegram

**Storage Strategy**:
- **Simple Version**: JSON file-based storage (`data.json`)
- **Enterprise Version**: PostgreSQL with SQLAlchemy ORM
- Redis caching layer for both versions
- Migration support via Alembic

### Business Logic Components

**Subscription System** (`utils/subscription.py`):
- Three tiers: FREE (10 req/day), PREMIUM (100 req/day, 199⭐/month), PRO (unlimited, 299⭐/month)
- Telegram Stars payment integration
- Rate limiting based on subscription level
- Referral system with bonus rewards

**Match Analysis** (`utils/match_analyzer.py`):
- Pre-game analysis with URL parsing
- Player danger level calculation (1-5 scale)
- Team analysis with parallel processing
- HLTV 2.1 rating calculations
- Analysis time: 10-30s (optimized from 60-120s)

**Performance Optimizations** (`utils/cache.py`, `utils/redis_cache.py`):
- Multi-level caching (player: 5min, match: 2min, stats: 10min TTL)
- 70-80% API request reduction
- Circuit breaker pattern for API failures
- Background prefetching for frequently accessed data

### Critical Configuration

**Environment Variables Required**:
```bash
TELEGRAM_BOT_TOKEN=              # From @BotFather
FACEIT_API_KEY=                 # From developers.faceit.com
TELEGRAM_CHAT_ID=               # Optional notification target
CHECK_INTERVAL_MINUTES=10       # Match monitoring frequency
LOG_LEVEL=INFO                  # Logging verbosity

# Enterprise Version Only:
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/faceit_bot
REDIS_URL=redis://localhost:6379/0
QUEUE_REDIS_URL=redis://localhost:6379/1
```

### Data Models

**User Data Structure**:
- `UserData`: Main user record with FACEIT linking (Simple version)
- `User`, `Subscription`, `Match` models in `database/models.py` (Enterprise)
- Repository pattern in `database/repositories/` for data access
- JSON serialization with datetime handling

**FACEIT Models** (`faceit/models.py`):
- Pydantic models for API response validation
- `FaceitPlayer`, `FaceitMatch`, `MatchStatsResponse`
- Nested data structure handling

### Bot Command Structure

Commands support both subscription-gated and free functionality:
- `/start` - Initial setup and welcome
- `/setplayer <nickname>` - Link FACEIT account
- `/analyze <match_url>` - Match analysis (rate limited)
- `/profile [nickname]` - Player profile with CS2-only statistics
- `/stats` - Detailed statistics with advanced metrics
- `/matches [number]` - Recent matches history (up to 200 for PRO)
- `/today` - Gaming session overview
- `/subscription` - Manage subscription and payments
- `/help` - Complete bot guide
- `/admin_*` - Administrative commands (restricted)

**Key Features**:
- CS2-only data filtering
- Moscow timezone (UTC+3) for all timestamps
- Enhanced navigation with back buttons
- Session analysis for gaming patterns
- Map-specific statistics
- Visual enhancements with progress bars and emojis

### Queue System (Enterprise Only)

**Queue Priorities** (`queues/config.py`):
- HIGH: Critical tasks (payments, notifications)
- NORMAL: Standard operations (match analysis)
- LOW: Background tasks (cache updates, cleanup)

**Background Jobs** (`queues/jobs.py`):
- Match monitoring and notifications
- Player statistics updates
- Cache management
- Analytics processing
- Subscription renewals

**Worker Management** (`worker.py`):
- Auto-scaling based on queue length
- Health monitoring and restart
- Distributed task processing

### Database Schema (Enterprise Only)

**Tables**:
- `users`: User accounts and FACEIT linking
- `subscriptions`: Subscription status and billing
- `matches`: Match history and statistics
- `player_stats`: Cached player statistics
- `payments`: Payment history and transactions

**Migrations** (`alembic/versions/`):
- Version-controlled schema changes
- Rollback support
- Data migration utilities

### Testing Approach
- Manual testing with standalone test scripts
- Integration testing against live FACEIT API
- Subscription flow testing with mock payments
- Error handling validation
- Performance benchmarking with load tests

### Monitoring and Observability

**Monitoring Dashboard** (Enterprise):
- Custom Flask-based monitoring system on port 9181
- Replaces RQ Dashboard (resolved Upstash Redis DB limitation)
- Real-time metrics with 5-second auto-refresh
- Bootstrap 5 + Chart.js responsive interface
- Available at: http://localhost:9181 (dev) or http://185.224.132.36:9181 (prod)

**Dashboard Features**:
- Service status for all 5 containers (bot + 3 workers + monitoring)
- User analytics: total users, active today, top users by requests
- Request graphs: hourly distribution over 24h, command type distribution
- Queue statistics: high/default/low priority queues, failed jobs
- Worker monitoring: active/idle status for all workers
- PostgreSQL stats: database size, connections, user counts
- Redis metrics: memory usage, connected clients, queue lengths

**Logging**:
- Structured logging with levels (DEBUG, INFO, WARNING, ERROR)
- File output to `bot.log`, `worker.log`
- Rotation and retention policies

**Metrics Collection** (Enterprise):
- Queue length and processing times
- API request counts and latencies  
- Cache hit rates
- Subscription conversion rates
- Hourly request patterns
- Command usage statistics

**Health Checks**:
- Database connectivity
- Redis availability
- FACEIT API status
- Worker process monitoring
- Docker container health checks

## Important Notes

### API Integration
- FACEIT API rate limit: 500 requests/10 minutes
- Use `CachedFaceitAPI` wrapper for optimization
- Handle `FaceitAPIError` exceptions gracefully
- Implement exponential backoff for retries

### Security Considerations
- Never commit `.env` files
- Use environment variables for all secrets
- Validate user input before API calls
- Implement rate limiting per user
- Sanitize HTML in messages

### Performance Guidelines
- Batch API requests when possible
- Use Redis caching aggressively
- Implement circuit breakers for external services
- Monitor memory usage in long-running processes
- Clean up old data periodically

### Development Best Practices
- Follow existing code patterns and style
- Use type hints for all functions
- Handle all exceptions explicitly
- Add logging for debugging
- Write integration tests for new features
- Update this CLAUDE.md when adding major features