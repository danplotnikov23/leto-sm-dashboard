#!/bin/bash
# Production startup script for Leto SM Dashboard
# Usage: ./start-production.sh

set -e

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

# Load environment variables
export $(grep -v '^#' .env | xargs) 2>/dev/null || true

# Activate virtual environment
source "$PROJECT_DIR/venv/bin/activate"

# Start backend with uvicorn (no reload, production mode)
cd "$PROJECT_DIR/backend"
exec uvicorn app.main:app --host 0.0.0.0 --port 8010 --workers 2
