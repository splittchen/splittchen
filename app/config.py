"""Application configuration management."""

import os
from datetime import timedelta
from typing import Dict, Any


class Config:
    """Application configuration class."""
    
    @staticmethod
    def get_required_env(key: str) -> str:
        """Get required environment variable or raise ValueError."""
        value = os.environ.get(key)
        if not value:
            raise ValueError(f"{key} environment variable must be set")
        return value
    
    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        """Load and validate all configuration from environment."""
        config = {}
        
        # Required settings
        config['SECRET_KEY'] = cls.get_required_env('SECRET_KEY')
        config['SQLALCHEMY_DATABASE_URI'] = cls.get_required_env('DATABASE_URL')
        config['BASE_URL'] = cls.get_required_env('BASE_URL')
        
        # SQLAlchemy settings
        config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # CSRF Configuration
        config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour timeout
        config['WTF_CSRF_ENABLED'] = True
        config['SESSION_COOKIE_HTTPONLY'] = True
        config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        
        # Session persistence - 90 days for group access
        config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=90)
        
        # Security Configuration
        secure_cookies = os.environ.get('SECURE_COOKIES', 'false').lower() == 'true'
        if secure_cookies:
            config['SESSION_COOKIE_SECURE'] = True
        
        # Email configuration (required for invitations and settlements)
        config['SMTP_HOST'] = cls.get_required_env('SMTP_HOST')
        config['SMTP_PORT'] = int(os.environ.get('SMTP_PORT', 587))
        config['SMTP_USERNAME'] = cls.get_required_env('SMTP_USERNAME')
        config['SMTP_PASSWORD'] = cls.get_required_env('SMTP_PASSWORD')
        config['SMTP_USE_TLS'] = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'
        config['FROM_EMAIL'] = os.environ.get('FROM_EMAIL', config['SMTP_USERNAME'])
        
        # Application settings
        config['APP_NAME'] = os.environ.get('APP_NAME', 'Splittchen')
        config['ACTIVITY_LOG_LIMIT'] = int(os.environ.get('ACTIVITY_LOG_LIMIT', '100'))
        
        # Currency settings
        config['DEFAULT_CURRENCY'] = os.environ.get('DEFAULT_CURRENCY', 'USD')
        
        # Email rate limiting settings (per-group)
        config['EMAIL_RATE_LIMITING_ENABLED'] = os.environ.get('EMAIL_RATE_LIMITING_ENABLED', 'true').lower() == 'true'
        config['EMAIL_LIMIT_REMINDER'] = int(os.environ.get('EMAIL_LIMIT_REMINDER', '1'))
        config['EMAIL_LIMIT_SETTLEMENT'] = int(os.environ.get('EMAIL_LIMIT_SETTLEMENT', '5'))
        config['EMAIL_LIMIT_INVITATION'] = int(os.environ.get('EMAIL_LIMIT_INVITATION', '25'))
        config['EMAIL_LIMIT_PRECREATED_INVITATION'] = int(os.environ.get('EMAIL_LIMIT_PRECREATED_INVITATION', '25'))
        config['EMAIL_LIMIT_GROUP_CREATED'] = int(os.environ.get('EMAIL_LIMIT_GROUP_CREATED', '19'))
        config['EMAIL_LIMIT_TOTAL_DAILY'] = int(os.environ.get('EMAIL_LIMIT_TOTAL_DAILY', '50'))
        
        # Scheduler configuration
        config['SCHEDULER_SETTLEMENT_TIME'] = os.environ.get('SCHEDULER_SETTLEMENT_TIME', '23:30')
        config['SCHEDULER_REMINDER_TIME'] = os.environ.get('SCHEDULER_REMINDER_TIME', '09:00')
        
        # SEO Configuration (disabled by default for compatibility)
        config['SEO_ENABLED'] = os.environ.get('SEO_ENABLED', 'false').lower() == 'true'
        config['SEO_SITE_NAME'] = os.environ.get('SEO_SITE_NAME', 'Splittchen')
        config['SEO_DESCRIPTION'] = os.environ.get(
            'SEO_DESCRIPTION',
            'Splittchen - Split expenses effortlessly. Create groups, add expenses, and settle up with friends, no registration required.'
        )
        config['SEO_KEYWORDS'] = os.environ.get(
            'SEO_KEYWORDS',
            'split expenses, split bills, expense splitter, group expenses, bill splitting app'
        )
        config['SEO_IMAGE_URL'] = os.environ.get('SEO_IMAGE_URL', '')
        
        return config