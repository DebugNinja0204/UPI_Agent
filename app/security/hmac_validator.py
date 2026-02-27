"""
HMAC Signature validation module.

Validates X-HMAC-Signature header to ensure request integrity and authenticity.
Uses HMAC-SHA256 with a shared secret.
"""

import hmac
import hashlib
from flask import request, g
import base64


class HMACValidationError(Exception):
    """Exception raised for HMAC validation errors."""
    pass


def compute_request_signature(timestamp, method, path, body, secret):
    """
    Compute HMAC-SHA256 signature for a request.
    
    Signature is computed over: timestamp + method + path + body
    
    Args:
        timestamp: X-Timestamp header value (string)
        method: HTTP method (GET, POST, etc.)
        path: URL path (without domain)
        body: Request body (empty string if no body)
        secret: Shared secret key
    
    Returns:
        Base64-encoded HMAC-SHA256 signature
    """
    # Construct the message to sign
    message = f"{timestamp}{method}{path}{body}"
    
    # Compute HMAC-SHA256
    signature = hmac.new(
        secret.encode() if isinstance(secret, str) else secret,
        message.encode(),
        hashlib.sha256
    ).digest()
    
    # Return base64-encoded signature
    return base64.b64encode(signature).decode('utf-8')


def validate_hmac_signature(secret):
    """
    Validate HMAC-SHA256 signature from X-HMAC-Signature header.
    
    Requirements:
    - X-HMAC-Signature header must be present
    - X-Timestamp header must be present
    - Computed signature must match the provided signature
    
    Args:
        secret: Shared secret for HMAC computation
    
    Raises:
        HMACValidationError: If validation fails
    """
    # Get headers
    provided_signature = request.headers.get('X-HMAC-Signature')
    timestamp = request.headers.get('X-Timestamp')
    
    if not provided_signature:
        raise HMACValidationError('Missing X-HMAC-Signature header')
    
    if not timestamp:
        raise HMACValidationError('Missing X-Timestamp header')
    
    # Get request details
    method = request.method
    path = request.path
    
    # Get body
    if request.is_json:
        body = request.get_data(as_text=True)
    elif request.data:
        body = request.get_data(as_text=True)
    else:
        body = ''
    
    # Compute expected signature
    expected_signature = compute_request_signature(
        timestamp, method, path, body, secret
    )
    
    # Compare signatures using constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise HMACValidationError('Invalid HMAC signature')


def require_hmac_signature(secret=None):
    """
    Decorator to require valid HMAC signature for a route.
    
    The secret should be stored securely, ideally retrieved from the API key record
    or configuration. If not provided, it will use the API key as the secret.
    
    Usage:
        @app.route('/signed-endpoint', methods=['POST'])
        @require_hmac_signature(secret='shared-secret-key')
        def signed_endpoint():
            return {'message': 'Signature validated'}
    
    Args:
        secret: Optional shared secret. If None, will try to use Secret from API key.
    """
    def decorator(f):
        def wrapper(*args, **kwargs):
            # Use provided secret or try to get from context
            validation_secret = secret or getattr(g, 'api_secret', None)
            
            if not validation_secret:
                return {'error': 'HMAC validation not configured'}, 500
            
            try:
                validate_hmac_signature(validation_secret)
            except HMACValidationError as e:
                return {'error': str(e)}, 401
            
            return f(*args, **kwargs)
        
        wrapper.__name__ = f.__name__
        return wrapper
    
    return decorator
