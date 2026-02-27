"""
API Key authentication module.

Validates API keys from X-API-Key header and attaches client information to Flask g object.
"""

import hashlib
from functools import wraps
from flask import request, g, current_app
from app.models import APIKey
from app import db


class APIKeyAuthError(Exception):
    """Exception raised for API key authentication errors."""
    pass


def hash_api_key(api_key):
    """
    Hash an API key using SHA-256.
    
    Args:
        api_key: The plain text API key
    
    Returns:
        SHA-256 hash of the API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def validate_api_key():
    """
    Validate API key from X-API-Key header.
    
    Checks:
    - Header is present
    - Key hash exists in database
    - Key is not revoked
    - Attaches client_id, client_name, and client_role to g object
    
    Raises:
        APIKeyAuthError: If validation fails
    """
    api_key = request.headers.get('X-API-Key')
    
    if not api_key:
        raise APIKeyAuthError('Missing X-API-Key header')
    
    # Hash the provided key
    key_hash = hash_api_key(api_key)
    
    # Look up in database
    api_key_record = APIKey.query.filter_by(key_hash=key_hash).first()
    
    if not api_key_record:
        raise APIKeyAuthError('Invalid API key')
    
    # Check if revoked
    if not api_key_record.is_active():
        raise APIKeyAuthError('API key has been revoked')
    
    # Attach to g object for use in request handlers
    g.client_id = api_key_record.id
    g.client_name = api_key_record.client_name
    g.client_role = api_key_record.role
    g.allowed_ips = api_key_record.allowed_ips or []


def check_ip_whitelist():
    """
    Check if request IP is in the whitelist for this API key.
    
    Only enforced if allowed_ips is defined for the key.
    """
    if not hasattr(g, 'allowed_ips') or not g.allowed_ips:
        return  # No IP restriction
    
    client_ip = request.remote_addr
    
    if client_ip not in g.allowed_ips:
        raise APIKeyAuthError(f'IP {client_ip} not whitelisted for this API key')


def require_api_key(f):
    """
    Decorator to require valid API key for a route.
    
    Usage:
        @app.route('/protected')
        @require_api_key
        def protected_route():
            return {'client': g.client_name}
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            validate_api_key()
            check_ip_whitelist()
        except APIKeyAuthError as e:
            return {'error': str(e)}, 401
        
        return f(*args, **kwargs)
    
    return decorated_function
