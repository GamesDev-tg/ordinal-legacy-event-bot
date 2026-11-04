#!/usr/bin/env bash
set -e
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-mock_bot_token_for_dev}"
export PORT="${PORT:-8000}"
export HOST="${HOST:-0.0.0.0}"

python3 -c "from app.database import init_db; init_db(); print('Database ready.')"
python3 scripts/seed_data.py
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
