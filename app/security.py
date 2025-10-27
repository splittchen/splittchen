"""Security configuration and utilities."""

from flask import request


def configure_security(app):
    """Configure security headers and settings for the Flask app.
    
    Applies comprehensive security headers to all HTTP responses including:
    - Content Security Policy (CSP) to prevent XSS attacks
    - X-Frame-Options to prevent clickjacking
    - HSTS for HTTPS enforcement
    - Various other security headers per OWASP recommendations
    """
    
    @app.after_request
    def security_headers(response):
        """Add security headers to all responses."""
        # Prevent MIME-type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Prevent embedding in frames (clickjacking protection)
        response.headers['X-Frame-Options'] = 'DENY'
        
        # XSS Protection (legacy header for older browsers)
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content Security Policy - allows Bootstrap CDN and inline styles/scripts
        # unsafe-inline needed for Flask flash messages and inline event handlers
        # unsafe-eval needed for Socket.IO client
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
            "font-src 'self' fonts.gstatic.com cdn.jsdelivr.net; "
            "img-src 'self' data: blob: cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "base-uri 'self'"
        )
        
        # Permissions Policy - disable unnecessary browser features
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Only add HSTS for HTTPS connections
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response