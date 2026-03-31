#!/bin/bash
# Start both backend and frontend
set -e
cd "$(dirname "$0")"

echo "Starting QuantAgent Dashboard..."
echo "  Backend → http://localhost:8001"
echo "  Frontend → http://localhost:5173"
echo ""

(cd backend && uvicorn app:app --host 0.0.0.0 --port 8001 --reload) &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
