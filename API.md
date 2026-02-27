# API Endpoints Documentation

Complete reference for all UPI Dispute Resolution Agent API endpoints.

All endpoints require authentication and follow a consistent response format.

## Response Format

All responses follow this consistent format:

```json
{
    "success": true/false,
    "data": {},
    "error": null,
    "correlation_id": "corr-12345..."
}
```

- **success**: Boolean indicating if request succeeded
- **data**: Response payload (null on error)
- **error**: Error details (null on success)
- **correlation_id**: Unique ID for tracing request through logs

## Security & Authentication

### Required Headers

All requests require these headers:

```
X-API-Key: <api_key>
X-Timestamp: <UNIX timestamp in seconds>
X-Nonce: <unique nonce>
X-HMAC-Signature: <HMAC-SHA256 signature>
Idempotency-Key: <UUID for idempotent operations>
```

### Rate Limiting

- **Default**: 60 requests per minute per API key
- **Response Headers**:
  - `X-RateLimit-Limit`: Maximum requests allowed
  - `X-RateLimit-Remaining`: Requests remaining
  - `X-RateLimit-Reset`: Timestamp when limit resets

### Roles

- `MERCHANT`: Can create disputes and transactions
- `BANK`: Can view disputes and transaction status
- `ADMIN`: Full access including manual resolution
- `INTERNAL_AGENT`: Background processing only

---

## Disputes API

**Base URL**: `/api/disputes`  
**Required Role**: MERCHANT, ADMIN (except where noted)

### POST /api/disputes — Create Dispute

Raise a new dispute for a transaction.

**Idempotent**: Yes (uses Idempotency-Key)

**Request**:
```json
{
    "upi_txn_id": "UPI123456",
    "raised_by": "CUSTOMER|MERCHANT|BANK",
    "reason_code": "TRANSACTION_NOT_RECEIVED|DUPLICATE_TRANSACTION|WRONG_AMOUNT|UNAUTHORIZED_TRANSACTION|PARTIAL_CREDIT|TRANSACTION_TIMEOUT|CUSTOMER_DISPUTE|OTHER",
    "notes": "Optional notes about the dispute"
}
```

**Response**: 201 Created
```json
{
    "success": true,
    "data": {
        "id": 1,
        "upi_txn_id": "UPI123456",
        "state": "OPEN",
        "raised_by": "CUSTOMER",
        "reason_code": "TRANSACTION_NOT_RECEIVED",
        "notes": "Customer received no credit",
        "created_at": "2026-02-27T10:30:00Z"
    },
    "error": null,
    "correlation_id": "corr-..."
}
```

**Errors**:
- `400`: Missing or invalid fields
- `409`: Dispute already exists for transaction (DISPUTE_EXISTS)
- `429`: Rate limit exceeded
- `500`: Server error

**Example**:
```bash
curl -X POST http://localhost:5000/api/disputes \
  -H "X-API-Key: $API_KEY" \
  -H "X-Timestamp: $(date +%s)" \
  -H "X-Nonce: $(uuidgen)" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "upi_txn_id": "UPI123456",
    "raised_by": "CUSTOMER",
    "reason_code": "TRANSACTION_NOT_RECEIVED"
  }'
```

---

### GET /api/disputes — List Disputes

List all disputes with optional filters.

**Query Parameters**:
- `state`: Filter by state (OPEN, VERIFYING, ACTION_REQUIRED, REFUND_IN_PROGRESS, RESOLVED)
- `raised_by`: Filter by who raised (CUSTOMER, MERCHANT, BANK)
- `date_from`: ISO date (inclusive)
- `date_to`: ISO date (inclusive)
- `limit`: Max results (default 100, max 500)
- `offset`: Pagination offset (default 0)

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "disputes": [
            {
                "id": 1,
                "transaction_id": 1,
                "upi_txn_id": "UPI123456",
                "state": "VERIFYING",
                "raised_by": "CUSTOMER",
                "reason_code": "TRANSACTION_NOT_RECEIVED",
                "resolution": null,
                "retry_count": 1,
                "created_at": "2026-02-27T10:30:00Z",
                "updated_at": "2026-02-27T10:31:00Z"
            }
        ],
        "total": 42,
        "limit": 10,
        "offset": 0
    }
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/api/disputes \
  -H "X-API-Key: $API_KEY" \
  -H "X-Timestamp: $(date +%s)" \
  -H "X-Nonce: $(uuidgen)" \
  '?state=VERIFYING&limit=20&offset=0'
```

---

### GET /api/disputes/<dispute_id> — Get Dispute Details

Get full details of a dispute including verification checks and refunds.

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "id": 1,
        "transaction_id": 1,
        "upi_txn_id": "UPI123456",
        "state": "REFUND_IN_PROGRESS",
        "raised_by": "CUSTOMER",
        "reason_code": "TRANSACTION_NOT_RECEIVED",
        "resolution": "REFUND",
        "retry_count": 2,
        "notes": "Customer confirmed issue via email",
        "sla_deadline_at": "2026-03-06T10:30:00Z",
        "created_at": "2026-02-27T10:30:00Z",
        "updated_at": "2026-02-27T10:35:00Z",
        "verification_checks": [
            {
                "id": 1,
                "attempt_no": 1,
                "decision": "INCONCLUSIVE",
                "confidence_score": 0.65,
                "checked_at": "2026-02-27T10:31:00Z",
                "error": null
            },
            {
                "id": 2,
                "attempt_no": 2,
                "decision": "APPROVED",
                "confidence_score": 0.95,
                "checked_at": "2026-02-27T10:35:00Z",
                "error": null
            }
        ],
        "refunds": [
            {
                "id": 1,
                "refund_id": "REF-00000001",
                "status": "SUCCESS",
                "method": "INSTANT",
                "initiated_at": "2026-02-27T10:35:00Z",
                "completed_at": "2026-02-27T10:36:00Z",
                "bank_refund_ref": "BRF123456"
            }
        ]
    }
}
```

**Errors**:
- `404`: Dispute not found
- `500`: Server error

---

### POST /api/disputes/<dispute_id>/recheck — Force Verification

Force immediate re-run of verification for a dispute.

**Request**: Empty body
```json
{}
```

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "dispute_id": 1,
        "verification_check_id": 3,
        "decision": "APPROVED",
        "confidence_score": 0.95,
        "state": "ACTION_REQUIRED",
        "resolution": "REFUND",
        "message": "Verification completed"
    }
}
```

**Errors**:
- `404`: Dispute not found
- `500`: Verification or verification failed

---

### POST /api/disputes/<dispute_id>/note — Add Note

Add a timestamped note to a dispute.

**Request**:
```json
{
    "note": "Customer called and confirmed the issue"
}
```

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "dispute_id": 1,
        "notes": "Previous notes\n---\n[2026-02-27T10:35:00Z] Customer called and confirmed the issue"
    }
}
```

**Errors**:
- `400`: Note is required
- `404`: Dispute not found
- `500`: Server error

---

### POST /api/disputes/<dispute_id>/resolve — Manually Resolve

Manually resolve a dispute (ADMIN only).

**Required Role**: ADMIN

**Request**:
```json
{
    "resolution": "REFUND|TRANSACTION_SUCCESS|NO_DEBIT_FOUND|CUSTOMER_DISPUTE",
    "note": "Optional resolution notes"
}
```

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "dispute_id": 1,
        "state": "RESOLVED",
        "resolution": "REFUND"
    }
}
```

**Errors**:
- `400`: Invalid resolution code
- `403`: Insufficient permissions
- `404`: Dispute not found
- `500`: Server error

---

### POST /api/disputes/<dispute_id>/refund — Trigger Refund

Manually trigger refund for a dispute (ADMIN only, idempotent).

**Required Role**: ADMIN

**Idempotent**: Yes (uses Idempotency-Key)

**Request**: Empty body
```json
{}
```

**Response**: 201 Created (or 200 if already processed)
```json
{
    "success": true,
    "data": {
        "dispute_id": 1,
        "refund_id": "REF-00000001",
        "status": "SUCCESS",
        "initiated_at": "2026-02-27T10:35:00Z",
        "completed_at": "2026-02-27T10:36:00Z"
    }
}
```

**Errors**:
- `403`: Insufficient permissions
- `404`: Dispute not found
- `500`: Refund processing failed

---

## Transactions API

**Base URL**: `/api/transactions`  
**Required Role**: MERCHANT, ADMIN

### POST /api/transactions — Create Transaction

Create a new transaction record.

**Request**:
```json
{
    "upi_txn_id": "UPI123456",
    "payer_vpa": "customer@bank",
    "payee_vpa": "merchant@bank",
    "amount": 1000.00,
    "currency": "INR|USD|EUR|GBP|JPY",
    "merchant_order_id": "ORD123456",
    "merchant_txn_id": "MTXN123456",
    "status": "SUCCESS|FAILED|PENDING|UNKNOWN"
}
```

**Response**: 201 Created
```json
{
    "success": true,
    "data": {
        "id": 1,
        "upi_txn_id": "UPI123456",
        "payer_vpa": "customer@bank",
        "payee_vpa": "merchant@bank",
        "amount": 1000.00,
        "currency": "INR",
        "status": "SUCCESS",
        "merchant_order_id": "ORD123456",
        "merchant_txn_id": "MTXN123456",
        "created_at": "2026-02-27T10:30:00Z"
    }
}
```

**Errors**:
- `400`: Invalid fields
- `409`: Transaction already exists
- `500`: Server error

---

### GET /api/transactions/<upi_txn_id> — Get Transaction

Get transaction details including related disputes.

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "id": 1,
        "upi_txn_id": "UPI123456",
        "payer_vpa": "customer@bank",
        "payee_vpa": "merchant@bank",
        "amount": 1000.00,
        "currency": "INR",
        "status": "SUCCESS",
        "bank_rrn": "RRN123456",
        "merchant_order_id": "ORD123456",
        "merchant_txn_id": "MTXN123456",
        "created_at": "2026-02-27T10:30:00Z",
        "updated_at": "2026-02-27T10:35:00Z",
        "disputes": [
            {
                "id": 1,
                "state": "RESOLVED",
                "raised_by": "CUSTOMER",
                "reason_code": "TRANSACTION_NOT_RECEIVED",
                "created_at": "2026-02-27T10:31:00Z"
            }
        ]
    }
}
```

**Errors**:
- `404`: Transaction not found
- `500`: Server error

---

## Internal API

**Base URL**: `/internal`  
**Required Role**: INTERNAL_AGENT

### POST /internal/run-agent — Trigger Agent Processing

Trigger background processing loop to handle disputes and refunds.

**Request**: Empty body
```json
{}
```

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "disputes_processed": 5,
        "disputes_verified": 3,
        "disputes_refunded": 1,
        "disputes_failed": 1,
        "processed_disputes": [
            {
                "dispute_id": 1,
                "action": "VERIFIED",
                "decision": "APPROVED",
                "confidence_score": 0.95,
                "status": "success"
            },
            {
                "dispute_id": 2,
                "action": "REFUNDED",
                "refund_id": "REF-00000001",
                "refund_status": "SUCCESS",
                "status": "success"
            },
            {
                "dispute_id": 3,
                "action": "VERIFY_FAILED",
                "error": "Connection timeout",
                "status": "failed"
            }
        ]
    }
}
```

**Processing Steps**:
1. Find disputes in VERIFYING state where next_check_at <= now
2. Run verification for each dispute
3. Find disputes in ACTION_REQUIRED state with resolution but no refund
4. Process refund for each dispute
5. Return summary of all actions taken

**Errors**:
- `403`: Insufficient permissions
- `500`: Agent processing failed

---

## Analytics API

**Base URL**: `/api/analytics`  
**Required Role**: ADMIN

### GET /api/analytics/summary — Get Analytics Summary

Get high-level analytics and metrics for dispute resolution.

**Response**: 200 OK
```json
{
    "success": true,
    "data": {
        "total_disputes": 42,
        "disputes_by_state": {
            "OPEN": 5,
            "VERIFYING": 3,
            "ACTION_REQUIRED": 8,
            "REFUND_IN_PROGRESS": 2,
            "RESOLVED": 24
        },
        "disputes_by_resolution": {
            "REFUND": 18,
            "TRANSACTION_SUCCESS": 4,
            "NO_DEBIT_FOUND": 2,
            "CUSTOMER_DISPUTE": 0
        },
        "average_resolution_time_hours": 2.5,
        "auto_resolved_percentage": 45.24,
        "refund_success_rate": 85.71,
        "most_common_reason_code": "TRANSACTION_NOT_RECEIVED",
        "reason_code_distribution": {
            "TRANSACTION_NOT_RECEIVED": 25,
            "DUPLICATE_TRANSACTION": 10,
            "WRONG_AMOUNT": 5,
            "OTHER": 2
        },
        "average_retry_count": 1.2,
        "verification_decision_distribution": {
            "APPROVED": 20,
            "REJECTED": 8,
            "INCONCLUSIVE": 14
        },
        "confidence_score_stats": {
            "average": 0.73,
            "min": 0.25,
            "max": 0.99
        },
        "timestamp": "2026-02-27T10:30:00Z"
    }
}
```

**Metrics Explained**:
- **average_resolution_time_hours**: Avg time from creation to resolution
- **auto_resolved_percentage**: % resolved without manual intervention
- **refund_success_rate**: % of approved refunds that succeeded
- **confidence_score_stats**: Statistics on verification confidence scores

---

## Error Handling

All errors follow this format:

```json
{
    "success": false,
    "data": null,
    "error": {
        "message": "Detailed error message",
        "code": "ERROR_CODE"
    },
    "correlation_id": "corr-..."
}
```

### Common Error Codes

| Code | Status | Meaning |
|------|--------|---------|
| - | 400 | Bad request (validation error) |
| DISPUTE_EXISTS | 409 | Dispute already exists |
| TRANSACTION_EXISTS | 409 | Transaction already exists |
| - | 401 | Unauthorized (auth failed) |
| - | 403 | Forbidden (insufficient permissions) |
| - | 404 | Not found |
| - | 429 | Rate limit exceeded |
| - | 500 | Server error |

---

## Authentication Example

Here's how to construct a valid request with all security headers:

```bash
#!/bin/bash

API_KEY="demo-merchant-key"
SECRET=$(echo -n "$API_KEY" | sha256sum | awk '{print $1}')
TIMESTAMP=$(date +%s)
NONCE=$(uuid)
IDEMPOTENCY_KEY=$(uuid)

# Construct message for HMAC
METHOD="POST"
PATH="/api/disputes"
BODY='{"upi_txn_id":"UPI123456","raised_by":"CUSTOMER","reason_code":"TRANSACTION_NOT_RECEIVED"}'

MESSAGE="${TIMESTAMP}${METHOD}${PATH}${BODY}"
SIGNATURE=$(echo -n "$MESSAGE" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)

curl -X POST http://localhost:5000/api/disputes \
  -H "X-API-Key: $API_KEY" \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Nonce: $NONCE" \
  -H "X-HMAC-Signature: $SIGNATURE" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -H "Content-Type: application/json" \
  -d "$BODY"
```

---

## Testing Guide

### 1. Setup Mock Services

```bash
# Terminal 1: Bank API
python run_mock_bank.py   # Runs on localhost:5001

# Terminal 2: Merchant API
python run_mock_merchant.py  # Runs on localhost:5002

# Terminal 3: Main App
python run.py  # Runs on localhost:5000
```

### 2. Test Dispute Resolution Flow

```bash
# 1. Create transaction
curl POST /api/transactions ...

# 2. Create dispute
curl POST /api/disputes ...

# 3. Get dispute details (should be VERIFYING)
curl GET /api/disputes/1 ...

# 4. Trigger agent (verifies dispute)
curl POST /internal/run-agent ...

# 5. Get dispute details (should be ACTION_REQUIRED with decision)
curl GET /api/disputes/1 ...

# 6. Trigger refund
curl POST /api/disputes/1/refund ...

# 7. Get analytics
curl GET /api/analytics/summary ...
```

### 3. Test with Mock Scenarios

```bash
# Bank API supports scenarios
GET http://localhost:5001/bank/txn/UPI123?scenario=success
GET http://localhost:5001/bank/txn/UPI123?scenario=failed
GET http://localhost:5001/bank/txn/UPI123?scenario=pending

# Use these to test different decision engine paths
```

---

## Rate Limiting

Default rate limit: **60 requests per minute per API key**

Response headers show current limits:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1614355200
```

When limit exceeded, you'll get:
```
HTTP 429 Too Many Requests
Retry-After: 30
```

---

## Best Practices

1. **Use Idempotency Keys**: Always include `Idempotency-Key` header for POST requests
2. **Handle Rate Limits**: Respect `Retry-After` header when rate limited
3. **Use Timestamps**: Always use recent timestamps (within 5 minutes) for requests
4. **Monitor Correlation IDs**: Save correlation_id for debugging
5. **Batch Operations**: Use pagination to fetch large result sets
6. **Cache Reads**: Cache transaction/dispute details when possible

---

## Webhooks

(Future feature) Incoming webhooks for:
- Dispute state changes
- Refund completion
- Verification completion
