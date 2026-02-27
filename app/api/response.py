"""
Consistent response formatting for all API endpoints.
"""

from flask import jsonify, g
from typing import Any, Optional, Dict


def success_response(data: Any = None, status_code: int = 200) -> tuple:
    """
    Format a successful API response.
    
    Args:
        data: Response data (dict, list, or any JSON-serializable object)
        status_code: HTTP status code (default: 200)
    
    Returns:
        Tuple of (response dict, status_code)
    """
    response = {
        'success': True,
        'data': data or {},
        'error': None,
        'correlation_id': getattr(g, 'correlation_id', 'unknown'),
    }
    return jsonify(response), status_code


def error_response(
    error_message: str,
    status_code: int = 400,
    error_code: Optional[str] = None,
) -> tuple:
    """
    Format an error API response.
    
    Args:
        error_message: Human-readable error message
        status_code: HTTP status code (default: 400)
        error_code: Optional error code for client handling
    
    Returns:
        Tuple of (response dict, status_code)
    """
    error_data = {
        'message': error_message,
    }
    if error_code:
        error_data['code'] = error_code
    
    response = {
        'success': False,
        'data': None,
        'error': error_data,
        'correlation_id': getattr(g, 'correlation_id', 'unknown'),
    }
    return jsonify(response), status_code


def created_response(data: Any) -> tuple:
    """
    Format a 201 Created response.
    
    Args:
        data: Response data
    
    Returns:
        Tuple of (response dict, 201)
    """
    return success_response(data, status_code=201)
