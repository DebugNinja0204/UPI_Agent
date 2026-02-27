"""
Structured JSON logging module.

Provides structured logging with correlation IDs and sensitive field masking.
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional
from flask import request, g
from datetime import datetime


class StructuredJSONFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def __init__(self, fields_to_mask: Optional[list] = None):
        """
        Initialize the formatter.
        
        Args:
            fields_to_mask: List of field names to mask (e.g., 'vpa', 'amount')
        """
        super().__init__()
        self.fields_to_mask = fields_to_mask or [
            'vpa',
            'payer_vpa',
            'payee_vpa',
            'amount',
            'bank_rrn',
            'api_key',
            'password',
            'secret',
        ]
    
    def mask_sensitive_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively mask sensitive fields in a dictionary.
        
        Args:
            data: Dictionary to mask
        
        Returns:
            Dictionary with sensitive fields masked
        """
        if not isinstance(data, dict):
            return data
        
        masked_data = {}
        for key, value in data.items():
            if any(field.lower() in key.lower() for field in self.fields_to_mask):
                # Mask sensitive field
                if isinstance(value, str) and value:
                    # Show first 3 and last 3 characters
                    if len(value) > 6:
                        masked_value = f"{value[:3]}...{value[-3:]}"
                    else:
                        masked_value = '***'
                elif isinstance(value, (int, float)):
                    masked_value = '***'
                else:
                    masked_value = '***'
                masked_data[key] = masked_value
            elif isinstance(value, dict):
                # Recursively mask nested dictionaries
                masked_data[key] = self.mask_sensitive_fields(value)
            elif isinstance(value, list):
                # Mask items in lists
                masked_data[key] = [
                    self.mask_sensitive_fields(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked_data[key] = value
        
        return masked_data
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as JSON.
        
        Args:
            record: The LogRecord to format
        
        Returns:
            JSON-formatted log line
        """
        # Build log entry
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add correlation ID if available (only if in request context)
        try:
            from flask import g, has_request_context
            if has_request_context():
                correlation_id = getattr(g, 'correlation_id', None)
                if correlation_id:
                    log_entry['correlation_id'] = correlation_id
        except (RuntimeError, ImportError):
            pass
        
        # Add request context if available
        try:
            from flask import request, has_request_context
            if has_request_context():
                log_entry['request'] = {
                    'method': request.method,
                    'path': request.path,
                    'remote_addr': request.remote_addr,
                }
                
                # Add client info if authenticated
                from flask import g
                if hasattr(g, 'client_name'):
                    log_entry['client'] = {
                        'name': g.client_name,
                        'id': getattr(g, 'client_id', None),
                        'role': getattr(g, 'client_role', None),
                    }
        except (RuntimeError, ImportError):
            pass
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
            }
        
        # Add extra fields and mask sensitive data
        if hasattr(record, 'extra_fields'):
            extra = record.extra_fields.copy() if isinstance(record.extra_fields, dict) else {}
            extra = self.mask_sensitive_fields(extra)
            log_entry['extra'] = extra
        
        return json.dumps(log_entry, default=str)


class RequestLogger:
    """Helper class for consistent request logging."""
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize RequestLogger.
        
        Args:
            logger: The logger instance to use
        """
        self.logger = logger
    
    def log_request_start(self, method: str, path: str, **extra):
        """Log start of request processing."""
        log_data = {
            'event': 'request_start',
            'method': method,
            'path': path,
        }
        log_data.update(extra)
        self._log_with_context(logging.INFO, "Request started", log_data)
    
    def log_request_end(self, status_code: int, duration_ms: float, **extra):
        """Log end of request processing."""
        log_data = {
            'event': 'request_end',
            'status_code': status_code,
            'duration_ms': duration_ms,
        }
        log_data.update(extra)
        self._log_with_context(logging.INFO, "Request completed", log_data)
    
    def log_auth_failure(self, reason: str, **extra):
        """Log authentication failure."""
        log_data = {
            'event': 'auth_failure',
            'reason': reason,
        }
        log_data.update(extra)
        self._log_with_context(logging.WARNING, "Authentication failed", log_data)
    
    def log_rate_limit_exceeded(self, limit: int, window: int, **extra):
        """Log rate limit exceeded."""
        log_data = {
            'event': 'rate_limit_exceeded',
            'limit': limit,
            'window_seconds': window,
        }
        log_data.update(extra)
        self._log_with_context(logging.WARNING, "Rate limit exceeded", log_data)
    
    def log_validation_error(self, field: str, error: str, **extra):
        """Log validation error."""
        log_data = {
            'event': 'validation_error',
            'field': field,
            'error': error,
        }
        log_data.update(extra)
        self._log_with_context(logging.WARNING, "Validation error", log_data)
    
    def log_database_error(self, operation: str, error: str, **extra):
        """Log database error."""
        log_data = {
            'event': 'database_error',
            'operation': operation,
            'error': error,
        }
        log_data.update(extra)
        self._log_with_context(logging.ERROR, "Database error", log_data)
    
    def log_business_event(self, event_type: str, **data):
        """Log a business event (dispute created, refund processed, etc.)."""
        log_data = {
            'event': event_type,
        }
        log_data.update(data)
        self._log_with_context(logging.INFO, f"Business event: {event_type}", log_data)
    
    def _log_with_context(self, level: int, message: str, extra_fields: Dict):
        """
        Log with extra context fields.
        
        Args:
            level: Logging level (logging.INFO, logging.WARNING, etc.)
            message: Log message
            extra_fields: Dictionary of extra fields to include
        """
        # Mask sensitive fields
        formatter = StructuredJSONFormatter()
        extra_fields = formatter.mask_sensitive_fields(extra_fields)
        
        # Create log record with extra fields
        record = self.logger.makeRecord(
            self.logger.name,
            level,
            '',
            0,
            message,
            (),
            None,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)


def setup_request_logging(app):
    """
    Setup structured logging for Flask app.
    
    Configures Flask to use structured JSON logging and attaches correlation IDs.
    
    Args:
        app: Flask application instance
    """
    # Configure root logger
    root_logger = logging.getLogger()
    
    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add JSON handler
    json_handler = logging.StreamHandler()
    json_handler.setFormatter(StructuredJSONFormatter())
    root_logger.addHandler(json_handler)
    root_logger.setLevel(logging.INFO)
    
    # Get or create logger for the app
    app_logger = logging.getLogger('upi_dispute_resolution')
    app.logger = app_logger
    
    # Create request logger instance
    request_logger = RequestLogger(app_logger)
    
    @app.before_request
    def before_request():
        """Generate correlation ID and log request start."""
        # Generate or get correlation ID
        correlation_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
        g.correlation_id = correlation_id
        
        # Log request start
        request_logger.log_request_start(
            request.method,
            request.path,
            correlation_id=correlation_id,
        )
        
        # Store start time
        import time
        g.request_start_time = time.time()
    
    @app.after_request
    def after_request(response):
        """Log request completion."""
        import time
        duration_ms = (time.time() - g.request_start_time) * 1000
        
        request_logger.log_request_end(
            response.status_code,
            duration_ms,
            content_type=response.content_type,
        )
        
        # Add correlation ID to response headers
        response.headers['X-Correlation-ID'] = g.correlation_id
        
        return response
    
    return request_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
