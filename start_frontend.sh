#!/bin/bash
# Start frontend server from the correct directory

cd "$(dirname "$0")/frontend" || exit 1

echo "Starting frontend from: $(pwd)"
echo ""

# Start Next.js dev server
npm run dev
