from flask import Flask, request, g
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(config_name='development'):
    """
    Application factory for creating Flask app instance.
    
    Args:
        config_name: Configuration environment ('development', 'production', 'testing')
    
    Returns:
        Flask application instance
    """
    # Import here to avoid circular imports
    from config.settings import config
    
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize SQLAlchemy with app
    db.init_app(app)
    
    # Setup structured logging
    from app.security.logger import setup_request_logging
    setup_request_logging(app)
    
    # Register global before_request middleware
    _register_security_middleware(app)
    
    # Register API blueprints
    from app.api import disputes_bp, transactions_bp, analytics_bp, dashboard_bp
    from app.api.internal import internal_bp
    
    app.register_blueprint(disputes_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(internal_bp)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app


def _register_security_middleware(app):
    """
    Register security-related before_request handlers.
    
    These run in order:
    1. Timestamp validation (replay protection)
    2. API key authentication
    3. IP whitelist check
    4. Rate limiting
    
    Args:
        app: Flask application instance
    """
    # Import here to avoid circular imports
    from app.security import (
        validate_api_key,
        check_ip_whitelist,
        check_rate_limit,
        validate_timestamp,
        APIKeyAuthError,
        RateLimitError,
        ReplayProtectionError,
    )
    
    # Skip security checks for health check endpoints
    SKIP_SECURITY_PATHS = {'/health', '/healthz', '/ping', '/metrics'}
    SKIP_SECURITY_PREFIXES = ('/dashboard',)
    
    def should_skip_security():
        """Check if current request should skip security checks."""
        if request.path in SKIP_SECURITY_PATHS:
            return True
        return request.path.startswith(SKIP_SECURITY_PREFIXES)
    
    @app.before_request
    def validate_request_timestamp():
        """
        Validate X-Timestamp header for replay protection.
        
        Only enforced for non-idempotent operations.
        """
        if should_skip_security() or request.method in ['GET', 'HEAD', 'OPTIONS']:
            return None
        
        try:
            validate_timestamp()
        except ReplayProtectionError as e:
            return {'error': str(e)}, 401
    
    @app.before_request
    def authenticate_api_key():
        """
        Authenticate request using API key.
        
        Requires X-API-Key header.
        Attaches client info to g object.
        """
        if should_skip_security():
            return None
        
        try:
            validate_api_key()
            check_ip_whitelist()
        except APIKeyAuthError as e:
            return {'error': str(e)}, 401
    
    @app.before_request
    def apply_rate_limiting():
        """
        Apply rate limiting by API key.
        
        Default: 60 requests per minute.
        """
        if should_skip_security() or not app.config.get('RATELIMIT_ENABLED', True):
            return None
        
        # Get configured rate limit
        default_limit = app.config.get('RATELIMIT_DEFAULT', '100/hour')
        try:
            limit_str = default_limit.split('/')[0]
            limit = int(limit_str)
            window = 60  # 1 minute default
        except (ValueError, IndexError):
            limit = 60
            window = 60
        
        try:
            check_rate_limit(limit=limit, window_seconds=window)
        except RateLimitError as e:
            # Get retry-after from error
            retry_after = e.args[1] if len(e.args) > 1 else 60
            return {
                'error': e.args[0],
                'limit': limit,
                'window_seconds': window,
            }, 429, {'Retry-After': str(retry_after)}
    
    @app.after_request
    def add_rate_limit_headers(response):
        """Add rate limit info to response headers."""
        if hasattr(g, 'rate_limit_remaining'):
            response.headers['X-RateLimit-Limit'] = str(g.rate_limit_limit)
            response.headers['X-RateLimit-Remaining'] = str(g.rate_limit_remaining)
            response.headers['X-RateLimit-Reset'] = str(g.rate_limit_reset)
        
        return response
