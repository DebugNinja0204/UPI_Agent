"""
Role-Based Access Control (RBAC) module.

Provides decorators to enforce role-based access control on routes.
"""

from functools import wraps
from flask import g


class RBACError(Exception):
    """Exception raised for RBAC violations."""
    pass


def require_role(*allowed_roles):
    """
    Decorator to require specific role(s) for a route.
    
    The API key authentication middleware must be applied first.
    Uses the client_role attached to g object by api_key_auth.
    
    Args:
        *allowed_roles: Variable number of APIKeyRole enum values or strings
    
    Returns:
        403 Forbidden if user role not in allowed_roles
    
    Usage:
        @app.route('/admin')
        @require_role(APIKeyRole.ADMIN, APIKeyRole.INTERNAL_AGENT)
        def admin_route():
            return {'message': 'Admin access granted'}
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Ensure client_role is set (should be from api_key_auth)
            if not hasattr(g, 'client_role'):
                return {'error': 'Unauthorized'}, 401
            
            # Allow string or Enum comparison
            client_role = g.client_role
            client_role_value = client_role.value if hasattr(client_role, 'value') else client_role
            
            # Check if client's role is in allowed roles
            allowed_role_values = [
                role.value if hasattr(role, 'value') else role
                for role in allowed_roles
            ]
            
            if client_role_value not in allowed_role_values:
                return {
                    'error': 'Insufficient permissions',
                    'required_roles': allowed_role_values,
                    'your_role': client_role_value,
                }, 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    
    return decorator


def require_any_role(*allowed_roles):
    """Alias for require_role for backward compatibility."""
    return require_role(*allowed_roles)


def get_current_client_role():
    """Get the current client's role from g object."""
    return getattr(g, 'client_role', None)


def get_current_client_name():
    """Get the current client's name from g object."""
    return getattr(g, 'client_name', None)


def get_current_client_id():
    """Get the current client's ID from g object."""
    return getattr(g, 'client_id', None)
