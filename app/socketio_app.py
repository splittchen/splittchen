"""SocketIO application initialization and configuration.

This module sets up Flask-SocketIO for real-time bidirectional communication
between the server and clients. It's configured to work with Gunicorn's
gevent worker class for production deployment.
"""

from flask import current_app
from flask_socketio import SocketIO
import logging


def create_socketio_app(app):
    """Initialize SocketIO with the Flask app.
    
    Args:
        app: Flask application instance
        
    Returns:
        SocketIO instance configured for gevent async mode
        
    Configuration:
        - async_mode='gevent': Matches Gunicorn worker class
        - cors_allowed_origins="*": Allow all origins (configure for production)
        - ping_timeout/interval: Connection health monitoring
    """
    
    # Simple SocketIO configuration for Gunicorn + gevent deployment
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",  # Configure based on deployment needs
        async_mode='gevent',       # Use gevent (matches Gunicorn worker class)
        logger=app.logger,         # Use app logger directly
        engineio_logger=False,     # Disable engine.io logging for cleaner logs
        ping_timeout=60,           # Connection timeout (seconds)
        ping_interval=25,          # Heartbeat interval (seconds)
    )
    
    # Import and register event handlers
    from app.socketio_events.connection import init_connection_handlers
    
    # Register connection handlers with the socketio instance
    init_connection_handlers(socketio)
    
    app.logger.info("SocketIO initialized successfully with event handlers")
    return socketio


def get_socketio():
    """Get the SocketIO instance from current app context.
    
    Returns:
        SocketIO instance or None if not initialized
    """
    if hasattr(current_app, '_socketio'):
        return current_app._socketio
    return None