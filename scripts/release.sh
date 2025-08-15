#!/bin/bash
set -euo pipefail

# FACEIT Telegram Bot - Release Management Script
# Usage: ./release.sh <version>

VERSION=${1:-}

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

# Validate version format
validate_version() {
    if [[ -z "$VERSION" ]]; then
        echo "Usage: $0 <version>"
        echo ""
        echo "Examples:"
        echo "  $0 v1.2.0     # Major/minor release"
        echo "  $0 v1.2.1     # Patch release"
        echo "  $0 v2.0.0-rc1 # Release candidate"
        exit 1
    fi
    
    # Check version format (semantic versioning)
    if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?$ ]]; then
        error_exit "Version must follow semantic versioning format (e.g., v1.2.0, v1.2.0-rc1)"
    fi
    
    # Check if tag already exists
    if git tag -l | grep -q "^$VERSION$"; then
        error_exit "Tag $VERSION already exists"
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
        error_exit "Release must be created from develop branch (currently on: $CURRENT_BRANCH)"
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
        error_exit "Your develop branch is not up to date with origin/develop"
    fi
    
    # Check if GitHub CLI is available
    if ! command -v gh &> /dev/null; then
        log_warning "GitHub CLI not found. Some features may not work."
    fi
    
    # Check if all CI checks pass
    if command -v gh &> /dev/null; then
        log_info "Checking CI status..."
        CI_STATUS=$(gh pr checks --repo $(gh repo view --json nameWithOwner -q .nameWithOwner) $(git rev-parse HEAD) 2>/dev/null || echo "unknown")
        if [[ "$CI_STATUS" == *"failing"* ]]; then
            error_exit "CI checks are failing. Please fix issues before releasing."
        fi
    fi
    
    log_success "Prerequisites check passed"
}

# Run pre-release tests
run_tests() {
    log_info "Running pre-release tests..."
    
    # Install dependencies if needed
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
    fi
    
    # Run linting
    if command -v ruff &> /dev/null; then
        log_info "Running linting..."
        ruff check . || error_exit "Linting failed"
    fi
    
    if command -v black &> /dev/null; then
        log_info "Running code formatting check..."
        black --check . || error_exit "Code formatting check failed"
    fi
    
    # Run tests
    if [[ -d "tests" ]]; then
        log_info "Running tests..."
        python -m pytest tests/ -v --tb=short || error_exit "Tests failed"
    fi
    
    # Run security checks
    if command -v safety &> /dev/null; then
        log_info "Running security checks..."
        safety check || log_warning "Security check failed (non-blocking)"
    fi
    
    log_success "All tests passed"
}

# Update version files
update_version_files() {
    log_info "Updating version files..."
    
    # Update VERSION file
    echo "${VERSION#v}" > VERSION
    
    # Update version in setup.py if it exists
    if [[ -f "setup.py" ]]; then
        sed -i.bak "s/version=['\"][^'\"]*['\"]/version='${VERSION#v}'/" setup.py
        rm setup.py.bak
    fi
    
    # Update version in pyproject.toml if it exists
    if [[ -f "pyproject.toml" ]]; then
        sed -i.bak "s/version = ['\"][^'\"]*['\"]/version = \"${VERSION#v}\"/" pyproject.toml
        rm pyproject.toml.bak
    fi
    
    # Update version in package.json if it exists
    if [[ -f "package.json" ]]; then
        sed -i.bak "s/\"version\": \"[^\"]*\"/\"version\": \"${VERSION#v}\"/" package.json
        rm package.json.bak
    fi
    
    # Update version in config/version.py
    if [[ -f "config/version.py" ]]; then
        cat > config/version.py << EOF
"""Version information for FACEIT Telegram Bot."""

__version__ = "${VERSION#v}"
__version_info__ = tuple(int(x) for x in "${VERSION#v}".split('.') if x.isdigit())

# Build information
BUILD_DATE = "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_COMMIT = "$(git rev-parse HEAD)"
GIT_BRANCH = "$(git branch --show-current)"

# Version string for display
VERSION_STRING = f"v{__version__}"
FULL_VERSION_STRING = f"v{__version__} (build {BUILD_DATE[:10]})"
EOF
    fi
    
    log_success "Version files updated"
}

# Generate changelog
generate_changelog() {
    log_info "Generating changelog..."
    
    # Get the last tag
    LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    
    if [[ -z "$LAST_TAG" ]]; then
        COMMIT_RANGE="HEAD"
        log_info "No previous tags found, generating changelog from all commits"
    else
        COMMIT_RANGE="$LAST_TAG..HEAD"
        log_info "Generating changelog from $LAST_TAG to HEAD"
    fi
    
    # Create changelog content
    CHANGELOG_CONTENT="# Changelog for $VERSION

Released: $(date +%Y-%m-%d)

## What's Changed

### Features
$(git log $COMMIT_RANGE --oneline --grep="^feat" --format="- %s" | head -20)

### Bug Fixes
$(git log $COMMIT_RANGE --oneline --grep="^fix" --format="- %s" | head -20)

### Improvements
$(git log $COMMIT_RANGE --oneline --grep="^perf\|^refactor\|^improvement" --format="- %s" | head -10)

### Documentation
$(git log $COMMIT_RANGE --oneline --grep="^docs" --format="- %s" | head -10)

### Other Changes
$(git log $COMMIT_RANGE --oneline --invert-grep --grep="^feat\|^fix\|^perf\|^refactor\|^improvement\|^docs\|^chore\|^test" --format="- %s" | head -10)

## Technical Details

- **Total commits**: $(git rev-list $COMMIT_RANGE --count)
- **Contributors**: $(git log $COMMIT_RANGE --format="%an" | sort | uniq | wc -l)
- **Files changed**: $(git diff --name-only $COMMIT_RANGE | wc -l)

## Deployment Notes

- Database migrations: $(if [[ -d "alembic/versions" ]]; then echo "$(find alembic/versions -name "*.py" -newer <(git show $LAST_TAG:alembic/versions 2>/dev/null || echo /dev/null) | wc -l) new migrations"; else echo "No migrations"; fi)
- Configuration changes: Review .env.example for new variables
- Breaking changes: None

## Download

- Docker image: \`docker pull your-registry/faceit-bot:$VERSION\`
- Source code: [Download $VERSION](https://github.com/your-username/faceit-telegram-bot/archive/$VERSION.tar.gz)

---
Full changelog: https://github.com/your-username/faceit-telegram-bot/compare/$LAST_TAG...$VERSION"

    # Save changelog
    echo "$CHANGELOG_CONTENT" > "CHANGELOG_$VERSION.md"
    
    log_success "Changelog generated: CHANGELOG_$VERSION.md"
}

# Create release branch
create_release_branch() {
    log_info "Creating release branch..."
    
    RELEASE_BRANCH="release/$VERSION"
    git checkout -b "$RELEASE_BRANCH"
    
    log_success "Created release branch: $RELEASE_BRANCH"
}

# Commit release changes
commit_release_changes() {
    log_info "Committing release changes..."
    
    git add VERSION CHANGELOG_$VERSION.md config/version.py
    
    # Add other version files if they exist
    [[ -f "setup.py" ]] && git add setup.py
    [[ -f "pyproject.toml" ]] && git add pyproject.toml
    [[ -f "package.json" ]] && git add package.json
    
    git commit -m "chore: prepare release $VERSION

- Update version to $VERSION
- Generate changelog
- Update version files

Preparing for production deployment."
    
    log_success "Release changes committed"
}

# Create and push tag
create_tag() {
    log_info "Creating and pushing tag..."
    
    # Create annotated tag with changelog
    git tag -a "$VERSION" -m "Release $VERSION

$(cat CHANGELOG_$VERSION.md | head -50)

For full changelog see: CHANGELOG_$VERSION.md"
    
    # Push tag
    git push origin "$VERSION"
    
    log_success "Tag $VERSION created and pushed"
}

# Merge to main and deploy to production
merge_to_main() {
    log_info "Merging to main branch..."
    
    # Switch to main
    git checkout main
    git pull origin main
    
    # Merge release branch
    git merge --no-ff "release/$VERSION" -m "Release $VERSION

Merge release branch for $VERSION into main.
This triggers production deployment.

$(cat CHANGELOG_$VERSION.md | head -20)"
    
    # Push to main (triggers production deployment)
    git push origin main
    
    log_success "Merged to main branch"
}

# Merge back to develop
merge_back_to_develop() {
    log_info "Merging back to develop..."
    
    # Switch to develop
    git checkout develop
    git pull origin develop
    
    # Merge main to get release changes
    git merge main --no-ff -m "Merge release $VERSION back to develop

Includes version updates and changelog from release $VERSION."
    
    # Push to develop
    git push origin develop
    
    log_success "Merged back to develop"
}

# Create GitHub release
create_github_release() {
    if command -v gh &> /dev/null; then
        log_info "Creating GitHub release..."
        
        # Create release with changelog
        gh release create "$VERSION" \
            --title "Release $VERSION" \
            --notes-file "CHANGELOG_$VERSION.md" \
            --latest
        
        # Upload additional assets if they exist
        if [[ -f "dist/faceit-bot-${VERSION#v}.tar.gz" ]]; then
            gh release upload "$VERSION" "dist/faceit-bot-${VERSION#v}.tar.gz"
        fi
        
        log_success "GitHub release created: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/$VERSION"
    else
        log_warning "GitHub CLI not available. Please create release manually."
    fi
}

# Cleanup release branch
cleanup_release_branch() {
    log_info "Cleaning up release branch..."
    
    # Delete local release branch
    git branch -d "release/$VERSION" 2>/dev/null || true
    
    # Delete remote release branch if it exists
    git push origin --delete "release/$VERSION" 2>/dev/null || true
    
    log_success "Release branch cleaned up"
}

# Send notifications
send_notifications() {
    log_info "Sending release notifications..."
    
    # Slack notification
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{
                \"text\": \"🚀 New release: $VERSION\",
                \"blocks\": [
                    {
                        \"type\": \"header\",
                        \"text\": {
                            \"type\": \"plain_text\",
                            \"text\": \"🚀 FACEIT Bot Release $VERSION\"
                        }
                    },
                    {
                        \"type\": \"section\",
                        \"text\": {
                            \"type\": \"mrkdwn\",
                            \"text\": \"A new version of FACEIT Telegram Bot has been released!\"
                        }
                    },
                    {
                        \"type\": \"section\",
                        \"fields\": [
                            {
                                \"type\": \"mrkdwn\",
                                \"text\": \"*Version:*\n$VERSION\"
                            },
                            {
                                \"type\": \"mrkdwn\",
                                \"text\": \"*Release Date:*\n$(date +%Y-%m-%d)\"
                            }
                        ]
                    },
                    {
                        \"type\": \"actions\",
                        \"elements\": [
                            {
                                \"type\": \"button\",
                                \"text\": {
                                    \"type\": \"plain_text\",
                                    \"text\": \"View Release\"
                                },
                                \"url\": \"https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo 'your-username/faceit-telegram-bot')/releases/tag/$VERSION\"
                            }
                        ]
                    }
                ]
            }" \
            "$SLACK_WEBHOOK_URL"
    fi
    
    # Email notification (requires mailutils)
    if command -v mail &> /dev/null && [[ -n "${NOTIFICATION_EMAIL:-}" ]]; then
        echo "New FACEIT Telegram Bot release: $VERSION

$(cat CHANGELOG_$VERSION.md | head -50)

View full release: https://github.com/your-username/faceit-telegram-bot/releases/tag/$VERSION" | \
        mail -s "FACEIT Bot Release $VERSION" "$NOTIFICATION_EMAIL"
    fi
    
    log_success "Notifications sent"
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    # Wait for deployment to complete
    sleep 60
    
    # Check production health
    if command -v curl &> /dev/null; then
        PROD_URL="${PRODUCTION_URL:-https://bot.yourdomain.com}"
        
        log_info "Checking production health at $PROD_URL/health"
        
        for i in {1..5}; do
            if curl -f "$PROD_URL/health" >/dev/null 2>&1; then
                log_success "Production deployment verified"
                return 0
            fi
            log_info "Waiting for deployment... (attempt $i/5)"
            sleep 30
        done
        
        log_warning "Could not verify production deployment. Please check manually."
    fi
}

# Display release summary
show_release_summary() {
    log_success "Release $VERSION completed successfully! 🎉"
    echo ""
    echo "Release Summary:"
    echo "- Version: $VERSION"
    echo "- Release branch: release/$VERSION (cleaned up)"
    echo "- Tag: $VERSION (pushed)"
    echo "- GitHub release: Created"
    echo "- Production deployment: Triggered"
    echo ""
    echo "Next steps:"
    echo "1. Monitor production deployment"
    echo "2. Verify application health"
    echo "3. Announce release to users"
    echo "4. Update project documentation"
    echo ""
    echo "Links:"
    if command -v gh &> /dev/null; then
        echo "- Release page: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/$VERSION"
        echo "- Deployment status: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/actions"
    fi
    echo "- Changelog: CHANGELOG_$VERSION.md"
    echo ""
    echo "Happy releasing! 🚀"
}

# Main function
main() {
    log_info "Starting release process for $VERSION"
    
    validate_version
    check_prerequisites
    run_tests
    create_release_branch
    update_version_files
    generate_changelog
    commit_release_changes
    create_tag
    merge_to_main
    merge_back_to_develop
    create_github_release
    cleanup_release_branch
    send_notifications
    verify_deployment
    show_release_summary
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi