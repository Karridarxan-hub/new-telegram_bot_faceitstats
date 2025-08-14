# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Bot

**Simple Version (Recommended for development):**
```bash
python simple_bot.py             # Simple version with JSON storage
python simple_bot.py | tee bot.log  # With log output to file
```

**Enterprise Version (For production):**
```bash
python main.py                    # Enterprise version with PostgreSQL/Redis
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
docker-compose up -d            # Full enterprise architecture
docker-compose down             # Stop all enterprise services
```

### Linting and Code Quality
- No specific linting configuration found
- Use standard Python best practices
- Follow existing code style patterns

### Testing
```bash
python test_match_analysis.py   # Run match analysis tests
```

## Architecture Overview

### Core System Design
This is a **FACEIT Telegram Bot** with a subscription-based business model. The architecture follows a modular design:

- **Bot Layer** (`bot/`): Telegram Bot API integration using aiogram 3.x
- **FACEIT Integration** (`faceit/`): API client and data models for FACEIT platform
- **Business Logic** (`utils/`): Core functionality modules
- **Configuration** (`config/`): Settings management with pydantic

### Key Technical Patterns

**Asynchronous Architecture**: 
- All I/O operations use async/await
- `aiohttp` for HTTP requests to FACEIT API
- `aiogram` for Telegram Bot API with async handlers

**Data Flow**:
1. User commands → `bot/handlers.py` 
2. FACEIT API calls → `faceit/api.py`
3. Data processing → `utils/formatter.py`
4. Response formatting → back to user

**Storage Strategy**:
- JSON file-based storage (`data.json`) for user data
- In-memory caching for performance optimization
- Plans for PostgreSQL migration (see `database/` files)

### Business Logic Components

**Subscription System** (`utils/subscription.py`):
- Three tiers: FREE, PREMIUM, PRO
- Telegram Stars payment integration
- Rate limiting based on subscription level

**Match Analysis** (`utils/match_analyzer.py`):
- Pre-game analysis with URL parsing
- Player danger level calculation (1-5 scale)  
- Team analysis with parallel processing
- HLTV 2.1 rating calculations

**Performance Optimizations** (`utils/cache.py`):
- Multi-level caching system (player, match, stats)
- TTL-based cache expiration
- Parallel processing with semaphores
- Analysis time reduced from 60-120s to 10-30s

### Critical Configuration

**Environment Variables Required**:
```bash
TELEGRAM_BOT_TOKEN=              # From @BotFather
FACEIT_API_KEY=                 # From developers.faceit.com
TELEGRAM_CHAT_ID=               # Optional notification target
CHECK_INTERVAL_MINUTES=10       # Match monitoring frequency
LOG_LEVEL=INFO                  # Logging verbosity
```

**Settings Management**:
- Uses `pydantic-settings` for type-safe configuration
- Validation in `config/settings.py`
- Call `validate_settings()` before bot startup

### Data Models

**User Data Structure** (`utils/storage.py`):
- `UserData`: Main user record with FACEIT linking
- `UserSubscription`: Subscription status and limits
- JSON serialization with datetime handling

**FACEIT Models** (`faceit/models.py`):
- Pydantic models for API response validation
- `FaceitPlayer`, `FaceitMatch`, `MatchStatsResponse`
- Handles nested data structures from FACEIT API

### Message Processing

**Command Handlers** (`bot/handlers.py`):
- Router-based command handling
- Rate limiting integration
- Payment flow handling for Telegram Stars
- Admin commands with permission checking

**Message Formatting** (`utils/formatter.py`):
- HTML formatting for Telegram
- HLTV 2.1 rating calculations
- Match statistics presentation
- Multi-language support structure

### Performance Considerations

**Caching Strategy**:
- Player cache: 5 minutes TTL
- Match cache: 2 minutes TTL  
- Stats cache: 10 minutes TTL
- 70-80% API request reduction achieved

**Parallel Processing**:
- Team analysis runs in parallel
- Player statistics gathered concurrently
- Semaphore limiting (5 concurrent requests max)
- Background match monitoring

## Development Notes

### API Integration
- FACEIT API has rate limits (500 requests/10 minutes)
- Use cached API wrapper (`CachedFaceitAPI`) for optimization
- Handle `FaceitAPIError` exceptions properly

### Bot Command Structure
Commands support both subscription-gated and free functionality:
- `/analyze <match_url>` - Match analysis (rate limited)
- `/profile <nickname>` - Player profile
- `/subscription` - Subscription management
- `/admin_*` - Administrative commands (restricted)

### Database Migration Plan  
The project is prepared for PostgreSQL migration:
- Schema files in `database/` directory
- Repository pattern implementation ready
- Current JSON storage to be replaced
- Migration scripts and procedures available

### Testing Approach
- Manual testing with `test_match_analysis.py`
- No comprehensive test suite currently
- Integration testing against live FACEIT API
- Consider adding unit tests for core utilities

### Subscription Business Logic
- Free tier: 5 requests/day
- Premium: $9.99/month, 100 requests
- Pro: $19.99/month, 500 requests  
- Telegram Stars payment integration
- Referral system with bonus rewards

## Bot Versions

This project has **2 main versions** optimized for different use cases:

### Simple Version (`simple_bot.py`)
- **Purpose**: Development and simple deployment
- **Storage**: JSON files (`data.json`)
- **Architecture**: Single file, minimal dependencies
- **Users**: Up to 200 users
- **Features**: Full bot functionality with FSM, menus, callbacks

### Enterprise Version (`main.py`) 
- **Purpose**: Production and high-load environments
- **Storage**: PostgreSQL + Redis + RQ queues
- **Architecture**: Modular, microservices-based
- **Users**: 1000+ users
- **Features**: Everything + workers, monitoring, advanced subscriptions

**See `VERSIONS_GUIDE.md` for detailed comparison and setup instructions.**

## Important File Locations

### Core Files (Both Versions):
- **FACEIT API client**: `faceit/api.py`
- **User data storage**: `utils/storage.py`
- **Message formatting**: `utils/formatter.py`
- **Configuration**: `config/settings.py`

### Simple Version Files:
- **Main entry**: `simple_bot.py`
- **All functionality**: Self-contained in single file

### Enterprise Version Files:
- **Main entry**: `main.py`
- **Bot initialization**: `bot/bot.py`
- **Command handlers**: `bot/handlers.py`
- **Database models**: `database/models.py`
- **Queue workers**: `worker.py`
- **Background jobs**: `queues/jobs.py`

### Documentation:
- **Version comparison**: `VERSIONS_GUIDE.md`
- **Technical architecture**: `TECHNICAL_ARCHITECTURE.md`
- **Deployment guide**: `DEPLOYMENT.md`