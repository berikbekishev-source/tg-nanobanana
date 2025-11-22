#!/bin/bash
set -e

echo "Starting web service (with webhook setup)..."

# Run migrations
echo "Running migrations..."
./.venv/bin/python manage.py collectstatic --noinput
./.venv/bin/python manage.py migrate

# Set webhook (don't fail if it errors due to flood control)
echo "Setting Telegram webhook..."
timeout 5 ./.venv/bin/python manage.py set_webhook 2>&1 | head -20 || echo "Warning: Webhook setup skipped or failed (may already be set)"

# Start Gunicorn
echo "Starting Gunicorn..."
exec ./.venv/bin/gunicorn -k uvicorn.workers.UvicornWorker config.asgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120