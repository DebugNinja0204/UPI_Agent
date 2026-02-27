import os
from datetime import timedelta

class Config:
    """Base configuration."""
    
    # Flask configuration
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = False
    TESTING = False
    
    # Secret key for session management
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # SQLAlchemy configuration
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'timeout': 15},
    }
    
    # Database URI
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///upi_dispute_resolution.db'
    )
    
    # Rate limiting configuration
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "100/hour"  # 100 requests per hour
    RATELIMIT_STORAGE_URL = "memory://"  # In-memory storage (use Redis for production)
    
    # Dispute SLA configuration (in hours)
    DISPUTE_SLA_HOURS = 7 * 24  # 7 days
    
    # Verification retry configuration
    MAX_VERIFICATION_RETRIES = 3
    VERIFICATION_RETRY_INTERVAL_MINUTES = 30  # 30 minutes between retries

    # Gemini AI decision enhancement configuration
    GEMINI_DECISION_ENABLED = os.getenv('GEMINI_DECISION_ENABLED', 'true').lower() == 'true'
    GEMINI_CONFIDENCE_THRESHOLD = float(os.getenv('GEMINI_CONFIDENCE_THRESHOLD', '0.8'))
    GEMINI_ESCALATION_DECISIONS = {
        item.strip().upper()
        for item in os.getenv('GEMINI_ESCALATION_DECISIONS', 'RETRY,MANUAL_REVIEW').split(',')
        if item.strip()
    }
    
    # API configuration
    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = False
    
    # Logging configuration
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = True
    LOG_LEVEL = 'DEBUG'
    RATELIMIT_ENABLED = False  # Disable rate limiting in development
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    SQLALCHEMY_ECHO = False
    LOG_LEVEL = 'WARNING'
    RATELIMIT_ENABLED = True
    
    # Must be set via environment variable in production
    SECRET_KEY = os.getenv('SECRET_KEY', 'prod-secret-key-change-in-production')
    
    # Use environment variable for database URL
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///upi_dispute_resolution_prod.db'
    )
    
    # Use Redis for rate limiting in production
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'
    RATELIMIT_ENABLED = False
    WTF_CSRF_ENABLED = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
