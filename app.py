#!/usr/bin/env python3
"""Splittchen Flask Application Entry Point."""

# CRITICAL: Monkey patch MUST happen before ANY other imports
import gevent_patch  # noqa: F401

import os
from app import create_app, db

# Create Flask application with SocketIO
app, socketio = create_app()

if __name__ == '__main__':
    print("WARNING: This is for local development only!")
    print("Production: Use 'docker-compose up' or Gunicorn")
    
    # Get port from environment
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Splittchen with WebSocket support on port {port}")
    
    # Use socketio.run instead of app.run for WebSocket support
    socketio.run(app, host='0.0.0.0', port=port, debug=False)