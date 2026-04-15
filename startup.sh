#!/bin/bash
# startup.sh — production startup for Azure.
pip install -r requirements.txt
gunicorn \
    --bind 0.0.0.0:${PORT:-8050} \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:server
