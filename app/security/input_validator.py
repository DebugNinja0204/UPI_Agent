"""
Input validation utilities module.

Provides validation functions for common UPI Dispute Resolution data types.
"""

import re
import uuid
from typing import Tuple


class ValidationError(Exception):
    """Exception raised for validation errors."""
    pass


def validate_upi_vpa(vpa: str) -> Tuple[bool, str]:
    """
    Validate UPI Virtual Payment Address (VPA) format.
    
    UPI VPA format: username@bankprovider
    Example: user@okhdfcbank, merchant@airtel
    
    Args:
        vpa: The VPA string to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(vpa, str):
        return False, f"VPA must be a string, got {type(vpa).__name__}"
    
    vpa = vpa.strip()
    
    if not vpa:
        return False, "VPA cannot be empty"
    
    if len(vpa) > 255:
        return False, "VPA cannot exceed 255 characters"
    
    # UPI VPA pattern: username@provider
    # username: alphanumeric, dots, hyphens, underscores (3-30 chars)
    # provider: alphanumeric (2-20 chars)
    vpa_pattern = r'^[a-zA-Z0-9._-]{3,30}@[a-zA-Z0-9]{2,20}$'
    
    if not re.match(vpa_pattern, vpa):
        return False, (
            f"Invalid VPA format: {vpa}. "
            f"Expected format: username@bankprovider (e.g., user@okhdfcbank)"
        )
    
    return True, ""


def validate_amount(amount, min_amount=0.01, max_amount=100000.00) -> Tuple[bool, str]:
    """
    Validate transaction amount.
    
    Args:
        amount: The amount to validate (float or int)
        min_amount: Minimum allowed amount (default: 0.01 INR)
        max_amount: Maximum allowed amount (default: 100000 INR)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return False, f"Amount must be a number, got {type(amount).__name__}"
    
    if amount_float < min_amount:
        return False, f"Amount must be at least {min_amount}"
    
    if amount_float > max_amount:
        return False, f"Amount cannot exceed {max_amount}"
    
    # Check for valid decimal places (max 2 for currency)
    if amount_float != round(amount_float, 2):
        return False, "Amount can have at most 2 decimal places"
    
    return True, ""


def validate_uuid(value: str, version=4) -> Tuple[bool, str]:
    """
    Validate UUID format.
    
    Args:
        value: The UUID string to validate
        version: Expected UUID version (default: 4, can be 1, 3, 4, or 5)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(value, str):
        return False, f"UUID must be a string, got {type(value).__name__}"
    
    try:
        uuid_obj = uuid.UUID(value)
        if version and uuid_obj.version != version:
            return False, f"Expected UUID version {version}, got version {uuid_obj.version}"
        return True, ""
    except ValueError:
        return False, f"Invalid UUID format: {value}"


def validate_currency(currency: str) -> Tuple[bool, str]:
    """
    Validate currency code.
    
    Accepts ISO 4217 3-letter currency codes. Currently only supports common currencies.
    
    Args:
        currency: The currency code to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(currency, str):
        return False, f"Currency must be a string, got {type(currency).__name__}"
    
    currency = currency.upper()
    
    # Common supported currencies
    supported_currencies = {
        'INR',  # Indian Rupee
        'USD',  # US Dollar
        'EUR',  # Euro
        'GBP',  # British Pound
        'JPY',  # Japanese Yen
    }
    
    if currency not in supported_currencies:
        return False, (
            f"Unsupported currency: {currency}. "
            f"Supported: {', '.join(sorted(supported_currencies))}"
        )
    
    return True, ""


def validate_enum_value(value: str, allowed_values: list) -> Tuple[bool, str]:
    """
    Validate that a value is in the allowed list.
    
    Args:
        value: The value to validate
        allowed_values: List of allowed values
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not value:
        return False, "Value cannot be empty"
    
    if value not in allowed_values:
        return False, (
            f"Invalid value: {value}. "
            f"Allowed values: {', '.join(map(str, allowed_values))}"
        )
    
    return True, ""


def validate_transaction_id(txn_id: str) -> Tuple[bool, str]:
    """
    Validate transaction ID format.
    
    Expected format: UPI prefix + alphanumeric characters
    
    Args:
        txn_id: The transaction ID to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(txn_id, str):
        return False, f"Transaction ID must be a string, got {type(txn_id).__name__}"
    
    txn_id = txn_id.strip()
    
    if not txn_id:
        return False, "Transaction ID cannot be empty"
    
    if len(txn_id) > 255:
        return False, "Transaction ID cannot exceed 255 characters"
    
    # Allow alphanumeric and common separators
    txn_pattern = r'^[a-zA-Z0-9\-_]{3,255}$'
    
    if not re.match(txn_pattern, txn_id):
        return False, f"Invalid transaction ID format: {txn_id}"
    
    return True, ""


def validate_phone_number(phone: str) -> Tuple[bool, str]:
    """
    Validate Indian phone number format.
    
    Args:
        phone: The phone number to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(phone, str):
        return False, f"Phone must be a string, got {type(phone).__name__}"
    
    # Remove common separators
    phone = re.sub(r'[\s\-\+\(\)]', '', phone)
    
    if not phone.isdigit():
        return False, "Phone number must contain only digits"
    
    # Indian phone numbers: 10 digits
    if len(phone) != 10:
        return False, "Indian phone numbers must be 10 digits"
    
    # First digit should be 6-9 for mobile
    if phone[0] not in '6789':
        return False, "Indian mobile numbers must start with 6, 7, 8, or 9"
    
    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email address format.
    
    Args:
        email: The email to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(email, str):
        return False, f"Email must be a string, got {type(email).__name__}"
    
    email = email.strip()
    
    # Simple email regex (RFC 5322 simplified)
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return False, f"Invalid email format: {email}"
    
    if len(email) > 254:
        return False, "Email cannot exceed 254 characters"
    
    return True, ""


def raise_if_invalid(is_valid: bool, error_message: str):
    """
    Helper to raise ValidationError if validation failed.
    
    Usage:
        is_valid, error = validate_upi_vpa(vpa)
        raise_if_invalid(is_valid, error)
    
    Args:
        is_valid: Boolean indicating if validation passed
        error_message: Error message if validation failed
    
    Raises:
        ValidationError: If is_valid is False
    """
    if not is_valid:
        raise ValidationError(error_message)
