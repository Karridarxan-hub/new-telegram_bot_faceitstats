#!/bin/bash
set -euo pipefail

# FACEIT Telegram Bot - New Feature Workflow Script
# Usage: ./new-feature.sh <feature-name>

FEATURE_NAME=${1:-}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${2:-$NC}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

log_info() { log "$1" "$BLUE"; }
log_success() { log "$1" "$GREEN"; }
log_warning() { log "$1" "$YELLOW"; }
log_error() { log "$1" "$RED"; }

# Error handling
error_exit() {
    log_error "$1"
    exit 1
}

# Validate feature name
validate_feature_name() {
    if [[ -z "$FEATURE_NAME" ]]; then
        echo "Usage: $0 <feature-name>"
        echo ""
        echo "Examples:"
        echo "  $0 user-analytics"
        echo "  $0 payment-integration"
        echo "  $0 match-notifications"
        exit 1
    fi
    
    # Check if feature name is valid (kebab-case)
    if [[ ! "$FEATURE_NAME" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
        error_exit "Feature name must be in kebab-case (lowercase letters, numbers, and hyphens only)"
    fi
    
    # Check if branch already exists
    if git show-ref --verify --quiet "refs/heads/feature/$FEATURE_NAME"; then
        error_exit "Feature branch 'feature/$FEATURE_NAME' already exists"
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if we're in a git repository
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        error_exit "This script must be run from within a Git repository"
    fi
    
    # Check if we're on develop branch
    CURRENT_BRANCH=$(git branch --show-current)
    if [[ "$CURRENT_BRANCH" != "develop" ]]; then
        log_warning "You're not on the develop branch (currently on: $CURRENT_BRANCH)"
        read -p "Do you want to switch to develop? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git checkout develop
        else
            error_exit "Please switch to develop branch before creating a new feature"
        fi
    fi
    
    # Check if working directory is clean
    if ! git diff-index --quiet HEAD --; then
        error_exit "Working directory is not clean. Please commit or stash your changes."
    fi
    
    # Check if develop is up to date
    git fetch origin
    LOCAL=$(git rev-parse develop)
    REMOTE=$(git rev-parse origin/develop)
    
    if [[ "$LOCAL" != "$REMOTE" ]]; then
        log_warning "Your develop branch is not up to date with origin/develop"
        read -p "Do you want to pull the latest changes? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git pull origin develop
        else
            error_exit "Please update your develop branch before creating a new feature"
        fi
    fi
    
    log_success "Prerequisites check passed"
}

# Create feature branch
create_feature_branch() {
    log_info "Creating feature branch: feature/$FEATURE_NAME"
    
    git checkout -b "feature/$FEATURE_NAME"
    log_success "Created and switched to branch: feature/$FEATURE_NAME"
}

# Create feature directory structure
create_feature_structure() {
    log_info "Creating feature directory structure..."
    
    # Create feature directory in appropriate location
    FEATURE_DIR="src/features/$FEATURE_NAME"
    mkdir -p "$FEATURE_DIR"
    
    # Create basic files
    cat > "$FEATURE_DIR/__init__.py" << EOF
"""
$FEATURE_NAME feature module.

This module implements $FEATURE_NAME functionality for the FACEIT Telegram Bot.
"""

from .handlers import *
from .services import *

__version__ = "0.1.0"
__author__ = "FACEIT Bot Team"
EOF

    cat > "$FEATURE_DIR/handlers.py" << EOF
"""
Telegram bot handlers for $FEATURE_NAME feature.
"""

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import logging

from .services import ${FEATURE_NAME//-/_}Service

logger = logging.getLogger(__name__)
router = Router()

${FEATURE_NAME//-/_}_service = ${FEATURE_NAME//-/_}Service()


@router.message(Command("${FEATURE_NAME//-/_}"))
async def handle_${FEATURE_NAME//-/_}_command(message: types.Message, state: FSMContext):
    """Handle /${FEATURE_NAME//-/_} command."""
    try:
        user_id = message.from_user.id
        
        # TODO: Implement $FEATURE_NAME functionality
        result = await ${FEATURE_NAME//-/_}_service.process_request(user_id)
        
        await message.answer(f"$FEATURE_NAME feature: {result}")
        
    except Exception as e:
        logger.error(f"Error in $FEATURE_NAME handler: {e}")
        await message.answer("Sorry, there was an error processing your request.")


@router.callback_query(lambda c: c.data.startswith("${FEATURE_NAME//-/_}_"))
async def handle_${FEATURE_NAME//-/_}_callback(callback: types.CallbackQuery, state: FSMContext):
    """Handle $FEATURE_NAME callback queries."""
    try:
        action = callback.data.split("_", 1)[1]
        user_id = callback.from_user.id
        
        # TODO: Implement callback handling
        result = await ${FEATURE_NAME//-/_}_service.handle_callback(user_id, action)
        
        await callback.message.edit_text(f"$FEATURE_NAME: {result}")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in $FEATURE_NAME callback: {e}")
        await callback.answer("Error processing request", show_alert=True)
EOF

    cat > "$FEATURE_DIR/services.py" << EOF
"""
Business logic services for $FEATURE_NAME feature.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from database.repositories.base import BaseRepository
from utils.cache import cache_result

logger = logging.getLogger(__name__)


class ${FEATURE_NAME//-/_}Service:
    """Service class for $FEATURE_NAME functionality."""
    
    def __init__(self):
        self.repository = BaseRepository()
    
    @cache_result(ttl=300)  # Cache for 5 minutes
    async def process_request(self, user_id: int) -> str:
        """
        Process $FEATURE_NAME request for user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            str: Result message
        """
        try:
            # TODO: Implement main business logic
            logger.info(f"Processing $FEATURE_NAME request for user {user_id}")
            
            # Example: Get user data
            user_data = await self.repository.get_user(user_id)
            if not user_data:
                return "User not found. Please register first."
            
            # TODO: Add your business logic here
            result = f"$FEATURE_NAME processed for user {user_id}"
            
            # TODO: Save results if needed
            await self._save_result(user_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing $FEATURE_NAME for user {user_id}: {e}")
            raise
    
    async def handle_callback(self, user_id: int, action: str) -> str:
        """
        Handle callback query for $FEATURE_NAME.
        
        Args:
            user_id: Telegram user ID
            action: Callback action
            
        Returns:
            str: Result message
        """
        try:
            logger.info(f"Handling $FEATURE_NAME callback: {action} for user {user_id}")
            
            # TODO: Implement callback handling based on action
            if action == "info":
                return f"$FEATURE_NAME information for user {user_id}"
            elif action == "settings":
                return f"$FEATURE_NAME settings for user {user_id}"
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            logger.error(f"Error handling $FEATURE_NAME callback {action} for user {user_id}: {e}")
            raise
    
    async def _save_result(self, user_id: int, result: str) -> None:
        """Save feature result to database."""
        try:
            # TODO: Implement data persistence if needed
            data = {
                'user_id': user_id,
                'feature': '$FEATURE_NAME',
                'result': result,
                'timestamp': datetime.utcnow()
            }
            # await self.repository.save_feature_result(data)
            pass
        except Exception as e:
            logger.error(f"Error saving $FEATURE_NAME result: {e}")
            # Don't raise - this is not critical
EOF

    cat > "$FEATURE_DIR/models.py" << EOF
"""
Data models for $FEATURE_NAME feature.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ${FEATURE_NAME//-/_}Request(BaseModel):
    """Request model for $FEATURE_NAME."""
    
    user_id: int
    feature_type: str = "$FEATURE_NAME"
    parameters: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ${FEATURE_NAME//-/_}Response(BaseModel):
    """Response model for $FEATURE_NAME."""
    
    success: bool
    message: str
    data: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ${FEATURE_NAME//-/_}Config(BaseModel):
    """Configuration model for $FEATURE_NAME."""
    
    enabled: bool = True
    cache_ttl: int = 300  # 5 minutes
    max_requests_per_hour: int = 100
    # TODO: Add feature-specific configuration
EOF

    # Create test files
    mkdir -p "tests/features/$FEATURE_NAME"
    
    cat > "tests/features/$FEATURE_NAME/test_handlers.py" << EOF
"""
Tests for $FEATURE_NAME handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram import types
from aiogram.fsm.context import FSMContext

from src.features.$FEATURE_NAME.handlers import handle_${FEATURE_NAME//-/_}_command, handle_${FEATURE_NAME//-/_}_callback


@pytest.mark.asyncio
async def test_${FEATURE_NAME//-/_}_command():
    """Test $FEATURE_NAME command handler."""
    # Mock message
    message = MagicMock(spec=types.Message)
    message.from_user.id = 123456
    message.answer = AsyncMock()
    
    # Mock state
    state = MagicMock(spec=FSMContext)
    
    # Call handler
    await handle_${FEATURE_NAME//-/_}_command(message, state)
    
    # Verify response
    message.answer.assert_called_once()
    call_args = message.answer.call_args[0][0]
    assert "$FEATURE_NAME feature:" in call_args


@pytest.mark.asyncio
async def test_${FEATURE_NAME//-/_}_callback():
    """Test $FEATURE_NAME callback handler."""
    # Mock callback query
    callback = MagicMock(spec=types.CallbackQuery)
    callback.data = "${FEATURE_NAME//-/_}_info"
    callback.from_user.id = 123456
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    
    # Mock state
    state = MagicMock(spec=FSMContext)
    
    # Call handler
    await handle_${FEATURE_NAME//-/_}_callback(callback, state)
    
    # Verify response
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()
EOF

    cat > "tests/features/$FEATURE_NAME/test_services.py" << EOF
"""
Tests for $FEATURE_NAME services.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.features.$FEATURE_NAME.services import ${FEATURE_NAME//-/_}Service


@pytest.fixture
def ${FEATURE_NAME//-/_}_service():
    """Create $FEATURE_NAME service instance for testing."""
    service = ${FEATURE_NAME//-/_}Service()
    service.repository = MagicMock()
    return service


@pytest.mark.asyncio
async def test_process_request(${FEATURE_NAME//-/_}_service):
    """Test processing $FEATURE_NAME request."""
    # Mock repository response
    ${FEATURE_NAME//-/_}_service.repository.get_user = AsyncMock(return_value={'id': 123456})
    ${FEATURE_NAME//-/_}_service._save_result = AsyncMock()
    
    # Call service method
    result = await ${FEATURE_NAME//-/_}_service.process_request(123456)
    
    # Verify result
    assert "$FEATURE_NAME processed for user 123456" in result
    ${FEATURE_NAME//-/_}_service.repository.get_user.assert_called_once_with(123456)


@pytest.mark.asyncio
async def test_handle_callback(${FEATURE_NAME//-/_}_service):
    """Test handling $FEATURE_NAME callback."""
    # Call service method
    result = await ${FEATURE_NAME//-/_}_service.handle_callback(123456, "info")
    
    # Verify result
    assert "$FEATURE_NAME information for user 123456" in result


@pytest.mark.asyncio
async def test_process_request_user_not_found(${FEATURE_NAME//-/_}_service):
    """Test processing request for non-existent user."""
    # Mock repository response
    ${FEATURE_NAME//-/_}_service.repository.get_user = AsyncMock(return_value=None)
    
    # Call service method
    result = await ${FEATURE_NAME//-/_}_service.process_request(123456)
    
    # Verify result
    assert "User not found" in result
EOF

    # Create documentation
    cat > "$FEATURE_DIR/README.md" << EOF
# $FEATURE_NAME Feature

## Overview

The $FEATURE_NAME feature provides [brief description of what this feature does].

## Usage

### Commands

- \`/${FEATURE_NAME//-/_}\` - Main command for $FEATURE_NAME functionality

### Callback Actions

- \`${FEATURE_NAME//-/_}_info\` - Show $FEATURE_NAME information
- \`${FEATURE_NAME//-/_}_settings\` - Access $FEATURE_NAME settings

## Configuration

The feature can be configured through the following environment variables:

- \`${FEATURE_NAME^^}_ENABLED\` - Enable/disable the feature (default: true)
- \`${FEATURE_NAME^^}_CACHE_TTL\` - Cache TTL in seconds (default: 300)
- \`${FEATURE_NAME^^}_MAX_REQUESTS_PER_HOUR\` - Rate limit (default: 100)

## API Integration

[Document any external API integrations]

## Database Schema

[Document any new database tables or changes]

## Testing

Run tests for this feature:

\`\`\`bash
pytest tests/features/$FEATURE_NAME/ -v
\`\`\`

## Development Notes

- TODO: [List of tasks to complete]
- TODO: [Any known limitations]
- TODO: [Future enhancements]
EOF

    log_success "Feature structure created in $FEATURE_DIR"
}

# Create GitHub issue
create_github_issue() {
    log_info "Creating GitHub issue for feature..."
    
    if command -v gh &> /dev/null; then
        ISSUE_BODY="## Feature Request: $FEATURE_NAME

### Description
[Describe what this feature does and why it's needed]

### Acceptance Criteria
- [ ] Implement basic $FEATURE_NAME functionality
- [ ] Add command handler for /${FEATURE_NAME//-/_}
- [ ] Add callback handlers
- [ ] Write unit tests
- [ ] Update documentation
- [ ] Add integration tests

### Technical Details
- Feature branch: \`feature/$FEATURE_NAME\`
- Estimated effort: [Small/Medium/Large]
- Dependencies: [List any dependencies]

### Definition of Done
- [ ] Code implemented and reviewed
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Feature tested in staging environment
- [ ] Ready for production deployment

---
Auto-generated by new-feature script"

        gh issue create \
            --title "Feature: $FEATURE_NAME" \
            --body "$ISSUE_BODY" \
            --label "feature,enhancement" \
            --assignee "@me"
        
        log_success "GitHub issue created"
    else
        log_warning "GitHub CLI not found. Please create issue manually."
    fi
}

# Update main bot integration
update_bot_integration() {
    log_info "Updating bot integration..."
    
    # Check if main bot file exists
    if [[ -f "src/bot/bot.py" ]]; then
        # Add import line if not exists
        if ! grep -q "from features.$FEATURE_NAME import router as ${FEATURE_NAME//-/_}_router" src/bot/bot.py; then
            # Find the imports section and add our import
            sed -i "/^from features\./a from features.$FEATURE_NAME import router as ${FEATURE_NAME//-/_}_router" src/bot/bot.py
            
            # Find where routers are included and add ours
            if grep -q "dp.include_router" src/bot/bot.py; then
                sed -i "/dp\.include_router/a dp.include_router(${FEATURE_NAME//-/_}_router)" src/bot/bot.py
            fi
            
            log_success "Updated bot integration"
        else
            log_info "Bot integration already exists"
        fi
    else
        log_warning "Main bot file not found. Please manually integrate the feature."
    fi
}

# Create PR template
create_pr_template() {
    log_info "Creating pull request template..."
    
    cat > ".github/PULL_REQUEST_TEMPLATE/$FEATURE_NAME.md" << EOF
## Feature: $FEATURE_NAME

### Description
Brief description of what this feature does.

### Changes Made
- [ ] Added $FEATURE_NAME handlers
- [ ] Implemented $FEATURE_NAME services
- [ ] Created data models
- [ ] Added unit tests
- [ ] Updated documentation

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed
- [ ] Performance impact assessed

### Deployment Notes
- [ ] No database migrations required
- [ ] No configuration changes required
- [ ] No breaking changes

### Screenshots/Demo
[Add screenshots or demo links if applicable]

### Checklist
- [ ] Code follows project standards
- [ ] Tests cover new functionality
- [ ] Documentation is updated
- [ ] Feature is backward compatible
- [ ] Ready for code review

Closes #[issue-number]
EOF

    log_success "PR template created"
}

# Display next steps
show_next_steps() {
    log_success "Feature setup completed! 🎉"
    echo ""
    echo "Next steps:"
    echo "1. Implement the feature logic in src/features/$FEATURE_NAME/"
    echo "2. Write comprehensive tests"
    echo "3. Update documentation"
    echo "4. Test locally: pytest tests/features/$FEATURE_NAME/"
    echo "5. Commit and push: git push origin feature/$FEATURE_NAME"
    echo "6. Create pull request"
    echo ""
    echo "Files created:"
    echo "- src/features/$FEATURE_NAME/ (feature implementation)"
    echo "- tests/features/$FEATURE_NAME/ (tests)"
    echo "- .github/PULL_REQUEST_TEMPLATE/$FEATURE_NAME.md (PR template)"
    echo ""
    echo "Happy coding! 🚀"
}

# Main function
main() {
    log_info "Starting new feature setup: $FEATURE_NAME"
    
    validate_feature_name
    check_prerequisites
    create_feature_branch
    create_feature_structure
    create_github_issue
    update_bot_integration
    create_pr_template
    show_next_steps
}

# Run script
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi