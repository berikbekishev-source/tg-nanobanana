#!/bin/bash
set -e

echo "Starting web service..."

# Run migrations
echo "Running migrations..."
python manage.py collectstatic --noinput
python manage.py migrate

# Set webhook
echo "Setting Telegram webhook..."
python manage.py set_webhook || echo "Warning: Failed to set webhook, continuing..."

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn -k uvicorn.workers.UvicornWorker config.asgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
