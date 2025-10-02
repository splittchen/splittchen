"""Error handlers for the application."""

from flask import render_template, request, current_app
from app import db


def register_error_handlers(app):
    """Register all error handlers with the Flask app."""
    
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors with custom page."""
        current_app.logger.warning(f"404 error for URL: {request.url} from IP: {request.remote_addr}")
        return render_template('404.html'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 errors with custom page."""
        current_app.logger.warning(f"403 error for URL: {request.url} from IP: {request.remote_addr}")
        return render_template('403.html'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors with custom page and database rollback."""
        db.session.rollback()
        current_app.logger.error(f"500 error for URL: {request.url} from IP: {request.remote_addr}: {error}")
        return render_template('500.html'), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handle unexpected exceptions."""
        # Log the error with full context
        current_app.logger.error(f"Unhandled exception: {error}", exc_info=True)
        
        # Rollback any pending database transactions
        try:
            db.session.rollback()
        except Exception:
            pass
        
        # Return generic error page
        return render_template('500.html'), 500