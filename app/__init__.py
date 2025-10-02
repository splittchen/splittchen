"""Splittchen Flask Application Factory."""

import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
csrf = CSRFProtect()


def create_app():
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    from app.config import Config
    app.config.update(Config.load_config())
    
    # Logging configuration
    log_level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Only configure logging if not already configured (e.g., by gunicorn)
    # This prevents duplicate log handlers with gevent workers
    if not logging.root.handlers:
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s %(levelname)s %(name)s %(message)s'
        )
    else:
        # If gunicorn already configured logging, just set the level
        logging.root.setLevel(log_level)

    # Set Flask app logger level
    app.logger.setLevel(log_level)
    
    # Log the current configuration for debugging
    app.logger.info(f'Application starting with log level: {log_level_name}')
    
    # Initialize extensions with app
    db.init_app(app)
    
    # Import models so they are registered with SQLAlchemy
    from app import models
    
    # Register blueprints BEFORE CSRF to ensure proper context
    from app.routes import main
    app.register_blueprint(main)
    
    # Add custom template filters
    @app.template_filter('currency_suffix')
    def currency_suffix_filter(amount, currency='USD'):
        """Template filter to format currency with symbol after amount."""
        from app.utils import format_currency_suffix
        return format_currency_suffix(float(amount), currency)
    
    # Initialize CSRF after blueprint registration
    csrf.init_app(app)
    
    # Configure security headers
    from app.security import configure_security
    configure_security(app)
    
    # Initialize database on startup
    from app.database import init_database
    with app.app_context():
        init_database()

    # Initialize background scheduler for automatic settlements (always enabled)
    try:
        from app.scheduler import start_scheduler
        start_scheduler(
            settlement_time=app.config['SCHEDULER_SETTLEMENT_TIME'],
            reminder_time=app.config['SCHEDULER_REMINDER_TIME']
        )
        # Get current timezone for logging
        tz_env = os.environ.get('TZ', 'UTC')
        app.logger.info(f"Background scheduler initialized (timezone: {tz_env}, settlement: {app.config['SCHEDULER_SETTLEMENT_TIME']}, reminders: {app.config['SCHEDULER_REMINDER_TIME']})")
    except Exception as e:
        app.logger.error(f"Failed to start background scheduler: {e}")
        # Don't raise - let the app continue but log the error
        app.logger.warning("Some features may not work without the scheduler (recurring settlements, expiration handling)")
    
    # Register CLI commands
    from app.cli import register_cli_commands
    register_cli_commands(app)
    
    # Register error handlers
    from app.error_handlers import register_error_handlers
    register_error_handlers(app)
    
    # Initialize SocketIO for real-time features
    from app.socketio_app import create_socketio_app
    socketio = create_socketio_app(app)
    app._socketio = socketio  # Store for later access
    
    app.logger.info("Application initialization completed with WebSocket support")
    
    return app, socketio