#!/usr/bin/env python3
"""
Run Alembic migrations for FACEIT Telegram Bot.

This script runs database migrations by setting the environment variable
and executing the alembic command.
"""

import os
import sys
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    """Run migrations with proper environment setup."""
    print("Starting database migrations...")
    
    # Load environment from .env.docker
    from dotenv import load_dotenv
    load_dotenv('.env.docker')
    
    # Set database URL for localhost (replace postgres hostname)
    original_db_url = os.getenv('DATABASE_URL', '')
    if '@postgres:' in original_db_url:
        db_url = original_db_url.replace('@postgres:', '@localhost:')
        print("Using localhost database URL")
    else:
        db_url = original_db_url
    
    if not db_url:
        print("ERROR: DATABASE_URL not found in environment")
        return 1
    
    # Set environment variable
    os.environ['DATABASE_URL'] = db_url
    print(f"Database URL set: {db_url.split('@')[0] if '@' in db_url else 'No credentials'}@***")
    
    # Run Alembic upgrade
    try:
        print("Running Alembic upgrade to head...")
        result = subprocess.run(
            [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            capture_output=True,
            text=True,
            cwd=str(project_root)
        )
        
        if result.returncode == 0:
            print("SUCCESS: Migrations completed successfully!")
            print("Output:")
            if result.stdout:
                print(result.stdout)
            return 0
        else:
            print("ERROR: Migrations failed!")
            print("Error output:")
            if result.stderr:
                print(result.stderr)
            if result.stdout:
                print("Standard output:")
                print(result.stdout)
            return 1
            
    except Exception as e:
        print(f"EXCEPTION: Failed to run migrations: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())