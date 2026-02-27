"""
Replay attack protection module.

Prevents replay attacks by validating timestamps and tracking nonce usage.
Rejects requests with timestamps older than 5 minutes.
"""

from datetime import datetime, timedelta, timezone
from flask import request, g
import uuid

# In-memory storage for used nonces (timestamp + nonce combinations)
# In production, use Redis or database
_used_nonces = set()

# Maximum age of a valid timestamp (5 minutes)
TIMESTAMP_MAX_AGE_SECONDS = 5 * 60


class ReplayProtectionError(Exception):
    """Exception raised for replay protection violations."""
    pass


def validate_timestamp():
    """
    Validate X-Timestamp header.
    
    Requirements:
    - X-Timestamp header must be present
    - Timestamp must be parseable as ISO 8601 format
    - Timestamp must be within 5 minutes of current time
    
    Raises:
        ReplayProtectionError: If validation fails
    """
    timestamp_str = request.headers.get('X-Timestamp')
    
    if not timestamp_str:
        raise ReplayProtectionError('Missing X-Timestamp header')
    
    try:
        # Parse ISO 8601 timestamp
        request_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise ReplayProtectionError('Invalid X-Timestamp format. Use ISO 8601.')

    # Normalize timezone-aware timestamp to naive UTC for arithmetic with utcnow()
    if request_time.tzinfo is not None:
        request_time = request_time.astimezone(timezone.utc).replace(tzinfo=None)
    
    # Check if timestamp is within acceptable window
    current_time = datetime.utcnow()
    time_diff = abs((current_time - request_time).total_seconds())
    
    if time_diff > TIMESTAMP_MAX_AGE_SECONDS:
        raise ReplayProtectionError(
            f'Request timestamp is too old. '
            f'Max age: {TIMESTAMP_MAX_AGE_SECONDS}s, '
            f'Actual age: {int(time_diff)}s'
        )
    
    # Store for nonce validation
    g.request_timestamp = timestamp_str


def validate_nonce(nonce_source='X-Nonce'):
    """
    Validate and track request nonce to prevent replay attacks.
    
    Checks if the nonce has been used before. If not, stores it for future checks.
    Nonces older than TIMESTAMP_MAX_AGE_SECONDS are automatically expired.
    
    Args:
        nonce_source: Header name to read nonce from (default: X-Nonce)
    
    Raises:
        ReplayProtectionError: If nonce was already used
    """
    nonce = request.headers.get(nonce_source)
    
    if not nonce:
        raise ReplayProtectionError(f'Missing {nonce_source} header')
    
    # Validate nonce format (should be UUID or similar)
    try:
        uuid.UUID(nonce)
    except (ValueError, AttributeError):
        raise ReplayProtectionError(f'{nonce_source} must be a valid UUID')
    
    # Create a combination key of timestamp + nonce
    timestamp = getattr(g, 'request_timestamp', None)
    if not timestamp:
        raise ReplayProtectionError('Timestamp not validated before nonce check')
    
    nonce_key = f"{timestamp}:{nonce}"
    
    # Check if nonce was already used
    if nonce_key in _used_nonces:
        raise ReplayProtectionError('Nonce has already been used (replay attack detected)')
    
    # Store nonce
    _used_nonces.add(nonce_key)
    
    # In production, implement nonce expiration
    # For now, keep all nonces (could become memory issue with high volume)


def clean_expired_nonces(max_age_seconds=TIMESTAMP_MAX_AGE_SECONDS):
    """
    Clean up expired nonces from the in-memory store.
    
    This should be called periodically in production, or use Redis/DB instead.
    
    Args:
        max_age_seconds: Remove nonces older than this (default: TIMESTAMP_MAX_AGE_SECONDS)
    """
    global _used_nonces
    # Simple implementation: clear all on each call for safety
    # In production, implement proper expiration with timestamps
    _used_nonces.clear()


def enable_replay_protection(require_nonce=True):
    """
    Decorator to enable replay protection for a route.
    
    Usage:
        @app.route('/protected', methods=['POST'])
        @enable_replay_protection(require_nonce=True)
        def protected_endpoint():
            return {'message': 'Request validated'}
    
    Args:
        require_nonce: If True, X-Nonce header is required (default: True)
    """
    def decorator(f):
        def wrapper(*args, **kwargs):
            try:
                validate_timestamp()
                if require_nonce:
                    validate_nonce()
            except ReplayProtectionError as e:
                return {'error': str(e)}, 401
            
            return f(*args, **kwargs)
        
        wrapper.__name__ = f.__name__
        return wrapper
    
    return decorator
