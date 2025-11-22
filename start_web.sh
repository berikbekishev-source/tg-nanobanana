#!/bin/bash
set -e

echo "Starting web service..."

# Run migrations
echo "Running migrations..."
./.venv/bin/python manage.py collectstatic --noinput
./.venv/bin/python manage.py migrate

# Set webhook
echo "Setting Telegram webhook..."
./.venv/bin/python manage.py set_webhook || echo "Warning: Failed to set webhook, continuing..."

# Start Gunicorn
echo "Starting Gunicorn..."
exec ./.venv/bin/gunicorn -k uvicorn.workers.UvicornWorker config.asgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120