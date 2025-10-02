"""Security configuration and utilities."""

from flask import request


def configure_security(app):
    """Configure security headers and settings for the Flask app."""
    
    @app.after_request
    def security_headers(response):
        """Add security headers to all responses."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; font-src 'self' fonts.gstatic.com cdn.jsdelivr.net; img-src 'self' data: blob: cdn.jsdelivr.net; connect-src 'self'; form-action 'self'; base-uri 'self'"
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Only add HSTS for HTTPS connections
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response