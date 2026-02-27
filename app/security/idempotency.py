"""
Idempotency module for request deduplication.

Caches responses by Idempotency-Key header to ensure idempotent operations.
Returns cached responses if the same key is used within a time window.
"""

from datetime import datetime, timedelta
from flask import request, g
import json
from functools import wraps

# In-memory cache for idempotent responses
# Format: {idempotency_key: {'response': ..., 'status': ..., 'timestamp': ...}}
_idempotency_cache = {}

# Cache expiration time (24 hours)
IDEMPOTENCY_CACHE_TTL_SECONDS = 24 * 60 * 60


class IdempotencyError(Exception):
    """Exception raised for idempotency errors."""
    pass


def validate_idempotency_key():
    """
    Read and validate Idempotency-Key header.
    
    The key should be a UUID or similar unique identifier.
    
    Returns:
        The idempotency key if present and valid, None otherwise
    """
    key = request.headers.get('Idempotency-Key')
    
    if not key:
        return None
    
    if not isinstance(key, str) or len(key) > 255:
        raise IdempotencyError('Invalid Idempotency-Key format')
    
    return key


def get_cached_response(idempotency_key):
    """
    Get cached response for an idempotency key.
    
    Args:
        idempotency_key: The idempotency key
    
    Returns:
        Tuple of (response_body, status_code) or (None, None) if not cached or expired
    """
    if idempotency_key not in _idempotency_cache:
        return None, None
    
    cached_entry = _idempotency_cache[idempotency_key]
    timestamp = cached_entry['timestamp']
    
    # Check if cache entry has expired
    if datetime.utcnow() - timestamp > timedelta(seconds=IDEMPOTENCY_CACHE_TTL_SECONDS):
        del _idempotency_cache[idempotency_key]
        return None, None
    
    return cached_entry['response'], cached_entry['status']


def cache_response(idempotency_key, response, status_code):
    """
    Cache a response for an idempotency key.
    
    Args:
        idempotency_key: The idempotency key
        response: The response body (dict or JSON-serializable)
        status_code: The HTTP status code
    """
    _idempotency_cache[idempotency_key] = {
        'response': response,
        'status': status_code,
        'timestamp': datetime.utcnow(),
    }


def require_idempotency(max_idle_ttl_seconds=IDEMPOTENCY_CACHE_TTL_SECONDS):
    """
    Decorator to enable idempotency for a route.
    
    If the same Idempotency-Key is used within the TTL, returns the cached response.
    
    Usage:
        @app.route('/create-dispute', methods=['POST'])
        @require_idempotency()
        def create_dispute():
            # Your handler code
            return {'dispute_id': 123}, 201
    
    Args:
        max_idle_ttl_seconds: Cache TTL in seconds (default: 24 hours)
    
    Returns:
        Cached response if key was previously used, otherwise executes handler
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                idempotency_key = validate_idempotency_key()
            except IdempotencyError as e:
                return {'error': str(e)}, 400
            
            # If no idempotency key provided, just execute normally
            if not idempotency_key:
                return f(*args, **kwargs)
            
            # Check for cached response
            cached_response, cached_status = get_cached_response(idempotency_key)
            if cached_response is not None:
                return cached_response, cached_status
            
            # Execute the handler
            result = f(*args, **kwargs)
            
            # Handle different response formats
            if isinstance(result, tuple):
                response_body, status_code = result[0], result[1] if len(result) > 1 else 200
            else:
                response_body, status_code = result, 200
            
            # Cache the response
            cache_response(idempotency_key, response_body, status_code)
            
            return result
        
        return wrapper
    
    return decorator


def clear_idempotency_cache():
    """Clear all cached idempotency responses."""
    global _idempotency_cache
    _idempotency_cache.clear()


def get_idempotency_cache_size():
    """Get the current size of the idempotency cache."""
    return len(_idempotency_cache)


def clean_expired_cache_entries(max_idle_ttl_seconds=IDEMPOTENCY_CACHE_TTL_SECONDS):
    """
    Remove expired entries from idempotency cache.
    
    This should be called periodically in production.
    
    Args:
        max_idle_ttl_seconds: Remove entries older than this
    """
    current_time = datetime.utcnow()
    expired_keys = [
        key for key, entry in _idempotency_cache.items()
        if current_time - entry['timestamp'] > timedelta(seconds=max_idle_ttl_seconds)
    ]
    
    for key in expired_keys:
        del _idempotency_cache[key]
    
    return len(expired_keys)
