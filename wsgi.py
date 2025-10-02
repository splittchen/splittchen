#!/usr/bin/env python3
"""WSGI entry point for production deployment.

NOTE: When using gunicorn with --worker-class gevent:
- Gunicorn's GeventWorker calls monkey_patch() in init_process()
- Then it calls load_wsgi() which imports this module
- Therefore monkey patching is already done by the time we get here
- Do NOT call monkey.patch_all() here
"""

from app import create_app

# Create Flask application with SocketIO
app, socketio = create_app()

# Export the Flask app with integrated SocketIO support
application = app