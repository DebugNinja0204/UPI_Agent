"""
Security module for authentication, authorization, encryption, and validation.

Exports:
- api_key_auth: API key authentication
- rbac: Role-based access control
- hmac_validator: HMAC signature validation
- replay_protection: Replay attack protection
- idempotency: Request idempotency
- rate_limiter: Rate limiting
- input_validator: Input validation utilities
- logger: Structured JSON logging
"""

from app.security.api_key_auth import (
    validate_api_key,
    check_ip_whitelist,
    require_api_key,
    APIKeyAuthError,
    hash_api_key,
)

from app.security.rbac import (
    require_role,
    require_any_role,
    get_current_client_role,
    get_current_client_name,
    get_current_client_id,
    RBACError,
)

from app.security.hmac_validator import (
    validate_hmac_signature,
    compute_request_signature,
    require_hmac_signature,
    HMACValidationError,
)

from app.security.replay_protection import (
    validate_timestamp,
    validate_nonce,
    enable_replay_protection,
    clean_expired_nonces,
    ReplayProtectionError,
)

from app.security.idempotency import (
    validate_idempotency_key,
    get_cached_response,
    cache_response,
    require_idempotency,
    clear_idempotency_cache,
    get_idempotency_cache_size,
    clean_expired_cache_entries,
    IdempotencyError,
)

from app.security.rate_limiter import (
    check_rate_limit,
    require_rate_limit,
    get_rate_limit_key,
    get_rate_limit_status,
    clear_rate_limit_cache,
    DEFAULT_RATE_LIMIT,
    DEFAULT_WINDOW_SECONDS,
    RateLimitError,
)

from app.security.input_validator import (
    validate_upi_vpa,
    validate_amount,
    validate_uuid,
    validate_currency,
    validate_enum_value,
    validate_transaction_id,
    validate_phone_number,
    validate_email,
    raise_if_invalid,
    ValidationError,
)

from app.security.logger import (
    StructuredJSONFormatter,
    RequestLogger,
    setup_request_logging,
    get_logger,
)

__all__ = [
    # API Key Auth
    'validate_api_key',
    'check_ip_whitelist',
    'require_api_key',
    'APIKeyAuthError',
    'hash_api_key',
    # RBAC
    'require_role',
    'require_any_role',
    'get_current_client_role',
    'get_current_client_name',
    'get_current_client_id',
    'RBACError',
    # HMAC
    'validate_hmac_signature',
    'compute_request_signature',
    'require_hmac_signature',
    'HMACValidationError',
    # Replay Protection
    'validate_timestamp',
    'validate_nonce',
    'enable_replay_protection',
    'clean_expired_nonces',
    'ReplayProtectionError',
    # Idempotency
    'validate_idempotency_key',
    'get_cached_response',
    'cache_response',
    'require_idempotency',
    'clear_idempotency_cache',
    'get_idempotency_cache_size',
    'clean_expired_cache_entries',
    'IdempotencyError',
    # Rate Limiting
    'check_rate_limit',
    'require_rate_limit',
    'get_rate_limit_key',
    'get_rate_limit_status',
    'clear_rate_limit_cache',
    'DEFAULT_RATE_LIMIT',
    'DEFAULT_WINDOW_SECONDS',
    'RateLimitError',
    # Input Validation
    'validate_upi_vpa',
    'validate_amount',
    'validate_uuid',
    'validate_currency',
    'validate_enum_value',
    'validate_transaction_id',
    'validate_phone_number',
    'validate_email',
    'raise_if_invalid',
    'ValidationError',
    # Logging
    'StructuredJSONFormatter',
    'RequestLogger',
    'setup_request_logging',
    'get_logger',
]
