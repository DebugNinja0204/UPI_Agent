# Mock Services Documentation

Two separate Flask applications for simulating external bank and merchant services for testing the UPI Dispute Resolution Agent.

## Quick Start

### Start Mock Bank API (Port 5001)
```bash
python run_mock_bank.py
```

### Start Mock Merchant API (Port 5002)
```bash
python run_mock_merchant.py
```

---

## Mock Bank API (Port 5001)

Simulates bank transaction processing and refund operations.

### Endpoints

#### GET /bank/txn/<upi_txn_id>
Get transaction status from the bank's perspective.

**Query Parameters:**
- `scenario` (optional): `success` | `failed` | `pending` | `notfound` | `random` (default)

**Example Request:**
```bash
curl "http://localhost:5001/bank/txn/UPI123456789?scenario=success"
```

**Success Response (200):**
```json
{
  "upi_txn_id": "UPI123456789",
  "bank_rrn": "RRN123456ab7890",
  "amount": 500.00,
  "currency": "INR",
  "status": "DEBIT_SUCCESS",
  "timestamp": "2026-02-27T12:00:00Z",
  "bank_name": "Mock Bank",
  "payer_name": "Payer Account Holder",
  "payee_name": "Payee Account Holder",
  "debit_timestamp": "2026-02-27T11:55:00Z",
  "credited_to_account": true
}
```

**Possible Status Values:**
- `DEBIT_SUCCESS` - Transaction debited successfully
- `DEBIT_FAILED` - Transaction failed to debit
- `PENDING` - Transaction still processing
- `NOT_FOUND` - Transaction not found in bank records

---

#### POST /bank/refund
Initiate a refund for a transaction.

**Request Body:**
```json
{
  "upi_txn_id": "UPI123456789",
  "amount": 500.00,
  "refund_id": "REF12345abcdef"
}
```

**Success Response (201):**
```json
{
  "refund_id": "REF12345abcdef",
  "upi_txn_id": "UPI123456789",
  "amount": 500.00,
  "status": "INITIATED",
  "created_at": "2026-02-27T12:00:00Z",
  "bank_refund_ref": "BREF1234567890AB"
}
```

**Idempotency:**
If the same `refund_id` is used again, returns the existing refund (HTTP 200).

**Error Responses:**
- `400` - Missing required fields or invalid amount
- `500` - Internal server error

---

#### GET /bank/refund/<refund_id>
Get refund status. Simulates refund progression.

**Query Parameters:**
- `scenario` (optional): `success` | `failed` | `random` (default)

**Example Request:**
```bash
curl "http://localhost:5001/bank/refund/REF12345abcdef?scenario=success"
```

**Response Progression:**
```
Time 0-2s:   INITIATED
Time 2-4s:   PROCESSING
Time 4+s:    SUCCESS or FAILED
```

**Success Response (200):**
```json
{
  "refund_id": "REF12345abcdef",
  "upi_txn_id": "UPI123456789",
  "amount": 500.00,
  "status": "SUCCESS",
  "created_at": "2026-02-27T12:00:00Z",
  "updated_at": "2026-02-27T12:00:04Z",
  "bank_refund_ref": "BREF1234567890AB",
  "refunded_at": "2026-02-27T12:00:04Z"
}
```

**Error Response (404):**
```json
{
  "error": "Refund not found",
  "refund_id": "REF12345abcdef"
}
```

---

#### GET /health
Health check endpoint.

**Response (200):**
```json
{
  "status": "healthy",
  "service": "mock-bank",
  "timestamp": "2026-02-27T12:00:00Z"
}
```

---

#### GET /bank/stats
Get service statistics.

**Response (200):**
```json
{
  "total_refunds": 5,
  "refund_statuses": {
    "INITIATED": 1,
    "PROCESSING": 2,
    "SUCCESS": 2
  },
  "timestamp": "2026-02-27T12:00:00Z"
}
```

---

## Mock Merchant API (Port 5002)

Simulates merchant order processing and reconciliation.

### Endpoints

#### GET /merchant/status
Get merchant's order/transaction status.

**Query Parameters:**
- `upi_txn_id` (required): UPI transaction ID
- `scenario` (optional): `success` | `failed` | `pending` | `notfound` | `random` (default)

**Example Request:**
```bash
curl "http://localhost:5002/merchant/status?upi_txn_id=UPI123456789&scenario=success"
```

**Success Response (200):**
```json
{
  "upi_txn_id": "UPI123456789",
  "merchant_order_id": "MO123456AB999999",
  "merchant_txn_id": "MT1234567890ABCD",
  "amount": 500.00,
  "currency": "INR",
  "status": "ORDER_SUCCESS",
  "timestamp": "2026-02-27T12:00:00Z",
  "merchant_id": "MERCHANT001",
  "merchant_name": "Mock Merchant Store",
  "order_received_at": "2026-02-27T12:00:00Z",
  "order_confirmed": true,
  "delivery_status": "PENDING"
}
```

**Possible Status Values:**
- `ORDER_SUCCESS` - Order received and confirmed
- `ORDER_FAILED` - Order rejected by merchant
- `ORDER_PENDING` - Order awaiting confirmation
- `NOT_FOUND` - Order not found at merchant

**Error Response (400):**
```json
{
  "error": "Missing required parameter: upi_txn_id"
}
```

---

#### POST /merchant/reconcile
Acknowledge and reconcile a dispute with the merchant.

**Request Body:**
```json
{
  "upi_txn_id": "UPI123456789",
  "resolution": "ACCEPTED",
  "refund_id": "REF12345abcdef"
}
```

**Resolution Values:**
- `ACCEPTED` - Merchant accepts the dispute
- `REJECTED` - Merchant rejects the dispute
- `PARTIAL_REFUND` - Merchant agrees to partial refund

**Success Response (200):**
```json
{
  "upi_txn_id": "UPI123456789",
  "resolution": "ACCEPTED",
  "acknowledged": true,
  "acknowledged_at": "2026-02-27T12:00:00Z",
  "refund_id": "REF12345abcdef",
  "merchant_action": "Acknowledged dispute, processing refund",
  "message": "Reconciliation accepted by merchant"
}
```

**Error Response (400):**
```json
{
  "error": "Invalid resolution. Allowed: ['ACCEPTED', 'REJECTED', 'PARTIAL_REFUND']"
}
```

---

#### GET /merchant/reconcile/<upi_txn_id>
Get reconciliation status for a transaction.

**Example Request:**
```bash
curl "http://localhost:5002/merchant/reconcile/UPI123456789"
```

**Success Response (200):**
```json
{
  "upi_txn_id": "UPI123456789",
  "resolution": "ACCEPTED",
  "refund_id": "REF12345abcdef",
  "acknowledged": true,
  "acknowledged_at": "2026-02-27T12:00:00Z",
  "updated_at": "2026-02-27T12:00:00Z",
  "merchant_action": "Acknowledged dispute, processing refund"
}
```

**Error Response (404):**
```json
{
  "error": "No reconciliation found",
  "upi_txn_id": "UPI123456789"
}
```

---

#### GET /health
Health check endpoint.

**Response (200):**
```json
{
  "status": "healthy",
  "service": "mock-merchant",
  "timestamp": "2026-02-27T12:00:00Z"
}
```

---

#### GET /merchant/stats
Get service statistics.

**Response (200):**
```json
{
  "total_orders": 10,
  "order_statuses": {
    "ORDER_SUCCESS": 7,
    "ORDER_FAILED": 2,
    "ORDER_PENDING": 1
  },
  "total_reconciliations": 5,
  "reconciliation_resolutions": {
    "ACCEPTED": 3,
    "REJECTED": 1,
    "PARTIAL_REFUND": 1
  },
  "timestamp": "2026-02-27T12:00:00Z"
}
```

---

## Testing Scenarios

Both APIs support the `?scenario` query parameter for deterministic testing:

### Scenario: success
- Bank: Returns `DEBIT_SUCCESS` or refund `SUCCESS`
- Merchant: Returns `ORDER_SUCCESS`

### Scenario: failed
- Bank: Returns `DEBIT_FAILED` or refund `FAILED`
- Merchant: Returns `ORDER_FAILED`

### Scenario: pending
- Bank: Returns `PENDING`
- Merchant: Returns `ORDER_PENDING`

### Scenario: notfound
- Bank/Merchant: Returns `NOT_FOUND`

### Scenario: random (default)
- Returns randomized response

---

## Testing Examples

### Test 1: Happy Path - Successful Transaction and Refund

**Terminal 1: Start Main App**
```bash
python run.py
```

**Terminal 2: Start Bank Mock**
```bash
python run_mock_bank.py
```

**Terminal 3: Start Merchant Mock**
```bash
python run_mock_merchant.py
```

**Terminal 4: Test Sequence**
```bash
# 1. Create a transaction
curl -X GET "http://localhost:5001/bank/txn/UPI123456789?scenario=success"

# 2. Get merchant order status
curl -X GET "http://localhost:5002/merchant/status?upi_txn_id=UPI123456789&scenario=success"

# 3. Initiate refund
curl -X POST http://localhost:5001/bank/refund \
  -H "Content-Type: application/json" \
  -d '{"upi_txn_id": "UPI123456789", "amount": 500, "refund_id": "REF12345abcdef"}'

# 4. Poll refund status
sleep 2
curl -X GET "http://localhost:5001/bank/refund/REF12345abcdef?scenario=success"

# 5. Reconcile with merchant
curl -X POST http://localhost:5002/merchant/reconcile \
  -H "Content-Type: application/json" \
  -d '{"upi_txn_id": "UPI123456789", "resolution": "ACCEPTED", "refund_id": "REF12345abcdef"}'
```

---

## In-Memory Storage

Both services store data in-memory dictionaries:
- Data is **NOT persisted** across restarts
- Useful for development and testing
- Not suitable for production

To persist data, integrate SQLAlchemy models similar to the main application.

---

## Customization

To add deterministic behavior, use the `?scenario` parameter in requests:

```bash
# Always return success
curl "http://localhost:5001/bank/txn/UPI123?scenario=success"

# Always return failure
curl "http://localhost:5001/bank/txn/UPI123?scenario=failed"

# Always return pending
curl "http://localhost:5001/bank/txn/UPI123?scenario=pending"

# Randomized response
curl "http://localhost:5001/bank/txn/UPI123?scenario=random"
```

---

## Notes

- Both services run independently on separate ports
- Responses include timestamps in UTC ISO 8601 format
- All responses include `X-Request-ID` header for tracking
- Services automatically generate IDs (RRN, merchant_txn_id, etc.)
- Refund progression simulates real bank processing (takes time)
