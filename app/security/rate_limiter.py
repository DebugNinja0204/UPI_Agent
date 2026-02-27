"""
Rate limiting module.

Enforces rate limits by API key using token bucket algorithm.
Default: 60 requests per minute per API key.
"""

from datetime import datetime, timedelta
from flask import request, g
from functools import wraps
import math

# In-memory storage for rate limit buckets
# Format: {client_id: {'tokens': ..., 'last_refill': ..., 'limit': ..., 'window': ...}}
_rate_limit_buckets = {}

# Default rate limit: 60 requests per minute
DEFAULT_RATE_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60


class RateLimitError(Exception):
    """Exception raised for rate limiting violations."""
    pass


def get_rate_limit_key():
    """
    Get the rate limit key for the current request.
    
    Prefers API key (client_id) if available, otherwise uses IP address.
    
    Returns:
        Rate limit key string
    """
    if hasattr(g, 'client_id'):
        return f"api_key:{g.client_id}"
    else:
        return f"ip:{request.remote_addr}"


def get_bucket(key, limit=DEFAULT_RATE_LIMIT, window_seconds=DEFAULT_WINDOW_SECONDS):
    """
    Get or create a rate limit bucket for a key.
    
    Args:
        key: The rate limit key
        limit: Max requests per window
        window_seconds: Time window in seconds
    
    Returns:
        Tuple of (tokens_remaining, reset_timestamp)
    """
    now = datetime.utcnow()
    
    if key not in _rate_limit_buckets:
        # Create new bucket
        _rate_limit_buckets[key] = {
            'tokens': limit,
            'last_refill': now,
            'limit': limit,
            'window': window_seconds,
        }
        return limit, now + timedelta(seconds=window_seconds)
    
    bucket = _rate_limit_buckets[key]
    
    # Calculate tokens to add based on time elapsed
    time_elapsed = (now - bucket['last_refill']).total_seconds()
    
    # If a full window has passed, reset the bucket
    if time_elapsed >= bucket['window']:
        bucket['tokens'] = bucket['limit']
        bucket['last_refill'] = now
        reset_time = now + timedelta(seconds=bucket['window'])
    else:
        # Refill tokens proportionally
        refill_rate = bucket['limit'] / bucket['window']
        tokens_to_add = refill_rate * time_elapsed
        bucket['tokens'] = min(bucket['limit'], bucket['tokens'] + tokens_to_add)
        bucket['last_refill'] = now
        reset_time = bucket['last_refill'] + timedelta(seconds=bucket['window'])
    
    return bucket['tokens'], reset_time


def check_rate_limit(limit=DEFAULT_RATE_LIMIT, window_seconds=DEFAULT_WINDOW_SECONDS):
    """
    Check if current request is within rate limit.
    
    Uses token bucket algorithm for smooth rate limiting.
    
    Args:
        limit: Max requests per window
        window_seconds: Time window in seconds
    
    Raises:
        RateLimitError: If rate limit is exceeded
    """
    key = get_rate_limit_key()
    tokens, reset_time = get_bucket(key, limit, window_seconds)
    
    if tokens < 1:
        # Convert reset_time to seconds until reset
        seconds_until_reset = (reset_time - datetime.utcnow()).total_seconds()
        seconds_until_reset = max(1, math.ceil(seconds_until_reset))
        
        raise RateLimitError(
            f'Rate limit exceeded. Max {limit} requests per {window_seconds}s. '
            f'Retry after {seconds_until_reset}s.',
            seconds_until_reset
        )
    
    # Consume a token
    bucket = _rate_limit_buckets[key]
    bucket['tokens'] -= 1
    
    # Store info for response headers
    g.rate_limit_remaining = int(bucket['tokens'])
    g.rate_limit_reset = int(reset_time.timestamp())
    g.rate_limit_limit = limit


def require_rate_limit(limit=DEFAULT_RATE_LIMIT, window_seconds=DEFAULT_WINDOW_SECONDS):
    """
    Decorator to enforce rate limiting on a route.
    
    Returns 429 Too Many Requests if limit is exceeded.
    
    Usage:
        @app.route('/limited-endpoint', methods=['GET'])
        @require_rate_limit(limit=100, window_seconds=60)
        def limited_endpoint():
            return {'message': 'Request counted'}
    
    Args:
        limit: Max requests per window (default: 60)
        window_seconds: Time window in seconds (default: 60)
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                check_rate_limit(limit, window_seconds)
            except RateLimitError as e:
                # Extract retry-after from exception
                retry_after = e.args[1] if len(e.args) > 1 else 60
                return {
                    'error': e.args[0],
                    'limit': limit,
                    'window_seconds': window_seconds,
                }, 429, {'Retry-After': str(retry_after)}
            
            return f(*args, **kwargs)
        
        return wrapper
    
    return decorator


def get_rate_limit_status(key=None):
    """
    Get current rate limit status for a key.
    
    Args:
        key: Rate limit key (uses current request key if not provided)
    
    Returns:
        Dict with tokens, reset_time, and other info
    """
    if not key:
        key = get_rate_limit_key()
    
    if key not in _rate_limit_buckets:
        return None
    
    bucket = _rate_limit_buckets[key]
    reset_time = bucket['last_refill'] + timedelta(seconds=bucket['window'])
    
    return {
        'key': key,
        'tokens_remaining': int(bucket['tokens']),
        'limit': bucket['limit'],
        'window_seconds': bucket['window'],
        'reset_timestamp': int(reset_time.timestamp()),
        'reset_time': reset_time.isoformat(),
    }


def clear_rate_limit_cache():
    """Clear all rate limit buckets."""
    global _rate_limit_buckets
    _rate_limit_buckets.clear()
