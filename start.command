#!/bin/bash
# Запустить Leto SM Dashboard (backend + frontend)

set -e

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo "🚀 Leto SM Dashboard — запуск..."

# Backend
if [ ! -d "$PROJECT_DIR/backend/venv" ]; then
    echo "📦 Установка backend зависимостей..."
    cd "$PROJECT_DIR/backend"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source "$PROJECT_DIR/backend/venv/bin/activate"
fi

# Frontend
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
    echo "📦 Установка frontend зависимостей..."
    cd "$PROJECT_DIR/frontend"
    npm install
fi

# Запуск backend
cd "$PROJECT_DIR/backend"
echo "🔥 Backend: http://127.0.0.1:8010"
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload &
BACKEND_PID=$!

# Запуск frontend
cd "$PROJECT_DIR/frontend"
echo "⚡ Frontend: http://127.0.0.1:5174"
npm run dev &
FRONTEND_PID=$!

# Ожидание завершения
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT TERM
wait
