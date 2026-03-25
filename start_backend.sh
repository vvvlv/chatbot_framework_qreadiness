#!/bin/bash
# Start backend server from the correct directory

cd "$(dirname "$0")/backend" || exit 1

echo "Starting backend from: $(pwd)"
echo ""

# Kill any existing uvicorn processes on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start uvicorn
python -m uvicorn api.main:app --reload --port 8000 --host 127.0.0.1
