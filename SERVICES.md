# Core Business Logic Services

This document describes the five core service modules that implement the dispute resolution business logic for the UPI Dispute Resolution Agent.

## Architecture Overview

The services follow a layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                  Verification Service (Orchestrator)        │
│  Coordinates entire verification workflow                   │
└────────┬──────────────────────────────────────┬─────────────┘
         │                                      │
    ┌────▼────────┐                 ┌──────────▼──────┐
    │ Bank Client │                 │ Merchant Client │
    │ (Calls Bank)│                 │ (Calls Merchant)│
    └────┬────────┘                 └──────────┬──────┘
         │                                     │
         └──────────────┬──────────────────────┘
                        │
                  ┌─────▼──────────┐
                  │Decision Engine │
                  │   (Decides)    │
                  └────────────────┘
         
    ┌──────────────────────────────────┐
    │     Refund Service (Actions)     │
    │ Creates & tracks refund workflow │
    └──────────────────────────────────┘
```

## 1. Bank Client (`bank_client.py`)

**Purpose**: Communicate with Mock Bank API to retrieve transaction status.

### Quick Start

```python
from app.services import BankClient, BankStatus

# Create client
bank = BankClient()

# Get transaction status
try:
    response = bank.get_transaction_status("UPI123456")
    print(f"Status: {response.status.value}")  # DEBIT_SUCCESS, DEBIT_FAILED, PENDING, NOT_FOUND
    print(f"RRN: {response.bank_rrn}")
    print(f"Amount: {response.amount}")
except BankClientError as e:
    print(f"Error: {e}")
```

### API Endpoints Used

#### GET /bank/txn/<upi_txn_id>
Get transaction status from bank.

**Response Format**:
```json
{
    "upi_txn_id": "UPI123456",
    "status": "DEBIT_SUCCESS",
    "bank_rrn": "RRN123456",
    "amount": 1000.00,
    "timestamp": "2026-02-27T10:30:00Z"
}
```

**BankStatus Enum**:
- `DEBIT_SUCCESS`: Transaction was successfully debited from customer
- `DEBIT_FAILED`: Transaction failed, no debit occurred
- `PENDING`: Bank still processing the transaction
- `NOT_FOUND`: Bank has no record of this transaction

### Features

- **Automatic Retries**: 3 attempts with 1-second delays
- **Error Handling**: 
  - HTTP errors (404, 500+) trigger retries
  - Timeouts (>5s) trigger retries
  - Connection errors trigger retries
- **Health Check**: `health_check()` method to verify bank API availability

### Configuration

```python
bank = BankClient(
    base_url="http://localhost:5001",  # Bank API URL
    timeout=5,                         # Request timeout (seconds)
    max_retries=3,                     # Number of retries
)
```

---

## 2. Merchant Client (`merchant_client.py`)

**Purpose**: Communicate with Mock Merchant API to retrieve order status.

### Quick Start

```python
from app.services import MerchantClient, MerchantStatus

# Create client
merchant = MerchantClient()

# Get order status
try:
    response = merchant.get_order_status("UPI123456")
    print(f"Status: {response.status.value}")  # ORDER_SUCCESS, ORDER_FAILED, ORDER_PENDING, NOT_FOUND
    print(f"Order ID: {response.merchant_order_id}")
    print(f"Txn ID: {response.merchant_txn_id}")
except MerchantClientError as e:
    print(f"Error: {e}")
```

### API Endpoints Used

#### GET /merchant/status?upi_txn_id=...
Get order status from merchant.

**Response Format**:
```json
{
    "upi_txn_id": "UPI123456",
    "status": "ORDER_SUCCESS",
    "merchant_order_id": "ORD123456",
    "merchant_txn_id": "MTXN123456",
    "amount": 1000.00,
    "timestamp": "2026-02-27T10:30:00Z"
}
```

**MerchantStatus Enum**:
- `ORDER_SUCCESS`: Merchant confirms order successful
- `ORDER_FAILED`: Merchant confirms order failed
- `ORDER_PENDING`: Merchant still processing the order
- `NOT_FOUND`: Merchant has no record of this transaction

### Features

- **Automatic Retries**: Same retry logic as BankClient
- **Query Parameters**: Supports scenario parameter for testing
- **Health Check**: `health_check()` method to verify merchant API availability

### Configuration

```python
merchant = MerchantClient(
    base_url="http://localhost:5002",  # Merchant API URL
    timeout=5,                         # Request timeout (seconds)
    max_retries=3,                     # Number of retries
)
```

---

## 3. Decision Engine (`decision_engine.py`)

**Purpose**: Analyze bank and merchant statuses to determine dispute resolution decision.

### Quick Start

```python
from app.services import DecisionEngine, BankStatus, MerchantStatus

# Create engine
engine = DecisionEngine()

# Make decision
decision = engine.decide(
    bank_status=BankStatus.DEBIT_SUCCESS,
    merchant_status=MerchantStatus.ORDER_FAILED,
    amount_match=True,
)

print(f"Decision: {decision.decision.value}")       # REFUND, UPDATE_SUCCESS, etc.
print(f"Confidence: {decision.confidence_score}")   # 0.95
print(f"Reasoning: {decision.reasoning}")           # Human-readable explanation
```

### Decision Rules

**Priority Order** (first match wins):

1. **Either Party PENDING → RETRY (50% confidence)**
   - Bank or merchant still processing
   - Wait for system to settle before deciding

2. **Amount Mismatch → MANUAL_REVIEW (30% confidence)**
   - Amounts differ between bank and merchant
   - Requires human investigation

3. **DEBIT_SUCCESS + ORDER_FAILED → REFUND (95% confidence)**
   - Bank charged customer but merchant didn't fulfill order
   - Clear case for refund

4. **DEBIT_SUCCESS + ORDER_SUCCESS → UPDATE_SUCCESS (99% confidence)**
   - Both parties confirm transaction successful
   - Most reliable scenario

5. **DEBIT_FAILED + ORDER_FAILED → NO_DEBIT_FOUND (97% confidence)**
   - Neither party has records
   - No refund needed

6. **DEBIT_SUCCESS + MERCHANT_NOT_FOUND → MANUAL_REVIEW (40% confidence)**
   - Bank processed but merchant doesn't have record
   - Possible fraud or integration issue

7. **Merchant/Bank NOT_FOUND → MANUAL_REVIEW (35-40% confidence)**
   - Cannot verify one side of transaction

8. **Other Combinations → MANUAL_REVIEW (25% confidence)**
   - Unexpected state, escalate to humans

### Decision Enum

```python
class DecisionType(Enum):
    REFUND = "REFUND"               # Initiate refund
    UPDATE_SUCCESS = "UPDATE_SUCCESS"  # Mark as successful, no action
    NO_DEBIT_FOUND = "NO_DEBIT_FOUND"  # No debit found, dispute invalid
    RETRY = "RETRY"                 # Wait and retry verification
    MANUAL_REVIEW = "MANUAL_REVIEW" # Escalate to human specialists
```

### Decision Object

```python
Decision(
    decision: DecisionType,
    confidence_score: float,  # 0.25 - 0.99
    reasoning: str,           # Explanation for the decision
)
```

### Usage Example

```python
# Scenario: Customer claims refund but bank shows success and merchant shows failed
decision = engine.decide(
    bank_status=BankStatus.DEBIT_SUCCESS,
    merchant_status=MerchantStatus.ORDER_FAILED,
    amount_match=True,
)
# Result: REFUND with 95% confidence
# Reasoning: "Bank confirms debit successful, but merchant order failed."

# Scenario: Both still processing
decision = engine.decide(
    bank_status=BankStatus.PENDING,
    merchant_status=MerchantStatus.ORDER_PENDING,
)
# Result: RETRY with 50% confidence
# Reasoning: "Bank status is PENDING..."
```

---

## 4. Verification Service (`verification_service.py`)

**Purpose**: Orchestrate the entire verification workflow for a dispute.

### Quick Start

```python
from app.services import VerificationService

# Create service
verifier = VerificationService()

# Verify a dispute
try:
    verification_check = verifier.verify_dispute(dispute_id=1)
    print(f"Decision: {verification_check.decision}")
    print(f"Confidence: {verification_check.confidence_score}")
    print(f"Attempt: {verification_check.attempt_no}")
except VerificationServiceError as e:
    print(f"Verification failed: {e}")
```

### Workflow Steps

```
1. Load Dispute & Transaction
   └─→ Fetch dispute from DB by ID
   └─→ Load related transaction

2. Fetch Bank Status
   └─→ Call BankClient.get_transaction_status()
   └─→ Handle errors/timeouts with retry logic

3. Fetch Merchant Status
   └─→ Call MerchantClient.get_order_status()
   └─→ Handle errors/timeouts with retry logic

4. Check Amount Match
   └─→ Compare transaction.amount with bank.amount and merchant.amount
   └─→ Allow ±0.01 tolerance for floating point

5. Run Decision Engine
   └─→ DecisionEngine.decide(bank_status, merchant_status, amount_match)
   └─→ Get decision with confidence score

6. Create Verification Check
   └─→ Store bank response, merchant response, decision, confidence
   └─→ Create VerificationCheck record in DB

7. Update Dispute State
   └─→ If REFUND: state = ACTION_REQUIRED, resolution = REFUND
   └─→ If UPDATE_SUCCESS: state = RESOLVED
   └─→ If NO_DEBIT_FOUND: state = RESOLVED
   └─→ If RETRY: schedule next check
   └─→ If MANUAL_REVIEW: state = ACTION_REQUIRED

8. Schedule Retry (if needed)
   └─→ Use exponential backoff:
       Attempt 1: +5 minutes
       Attempt 2: +15 minutes
       Attempt 3: +60 minutes
       Attempt 4: +360 minutes (6 hours)
       After 5 attempts: escalate to ACTION_REQUIRED
```

### Exponential Backoff Schedule

Retries are scheduled at increasing intervals:

| Attempt | Delay | Total Time |
|---------|-------|-----------|
| 1       | 5 min | 5 min     |
| 2       | 15 min| 20 min    |
| 3       | 60 min| 80 min    |
| 4       | 6 hrs | 6h 80min  |
| 5+      | Escalate to ACTION_REQUIRED |

### Usage Example

```python
from app.services import VerificationService
from app.models.dispute import Dispute

verifier = VerificationService()

# Verify dispute
verification = verifier.verify_dispute(dispute_id=123)

# Check the result
if verification.decision == "APPROVED":
    print("Verification approved - dispute valid")
elif verification.decision == "REJECTED":
    print("Verification rejected - dispute invalid")
elif verification.decision == "INCONCLUSIVE":
    print("Verification inconclusive - needs retry")
```

### State Transitions

```
Dispute States During Verification:

OPEN
  ↓
VERIFYING → (BankClient.get_txn_status)
         → (MerchantClient.get_order_status)
         → (DecisionEngine.decide)
         ↓
    ├─ REFUND? → ACTION_REQUIRED
    ├─ APPROVED? → RESOLVED
    ├─ REJECTED? → RESOLVED
    ├─ RETRY? → VERIFYING (scheduled for later)
    └─ MANUAL_REVIEW? → ACTION_REQUIRED
```

---

## 5. Refund Service (`refund_service.py`)

**Purpose**: Handle refund processing workflow from initiation to completion.

### Quick Start

```python
from app.services import RefundService
from app.models.dispute import Dispute

# Create service
refunder = RefundService()

# Process refund
dispute = db.session.get(Dispute, dispute_id)
try:
    refund = refunder.process_refund(dispute)
    print(f"Refund ID: {refund.refund_id}")
    print(f"Status: {refund.status.value}")
except RefundServiceError as e:
    print(f"Refund failed: {e}")
```

### Workflow Steps

```
1. Check Idempotency
   └─→ Query DB for existing refund for this dispute
   └─→ Return existing refund if found (idempotent)

2. Generate Refund ID
   └─→ Create UUID v4 for unique refund ID

3. Create Refund Row
   └─→ Insert into refunds table with status = INITIATED
   └─→ Set initiated_at timestamp

4. Initiate Bank Refund
   └─→ POST to /bank/refund with upi_txn_id, amount, refund_id
   └─→ Handle errors (timeout, connection, HTTP errors)
   └─→ Fail refund if POST fails

5. Poll Refund Status
   └─→ GET /bank/refund/<refund_id> repeatedly
   └─→ Poll interval: 2 seconds
   └─→ Max polls: 30 (60 seconds total timeout)
   └─→ Stop when status = SUCCESS or FAILED

6. Update Refund Row
   └─→ status = SUCCESS (completed) or FAILED
   └─→ bank_refund_ref = Reference from bank
   └─→ completed_at = Timestamp if SUCCESS
   └─→ failure_reason = Error message if FAILED

7. Update Dispute State
   └─→ If SUCCESS: state = REFUND_IN_PROGRESS
   └─→ If FAILED: state = ACTION_REQUIRED (retry manual approval)

8. Notify Merchant
   └─→ POST to /merchant/reconcile with refund details
   └─→ Map refund status to resolution (REFUND_APPROVED, etc.)
   └─→ Non-blocking (failure doesn't fail entire refund)
```

### API Endpoints Used

#### POST /bank/refund
Initiate refund with bank.

**Request**:
```json
{
    "upi_txn_id": "UPI123456",
    "amount": 1000.00,
    "refund_id": "REF-00000001"
}
```

**Response**:
```json
{
    "status": "INITIATED",
    "refund_id": "REF-00000001",
    "timestamp": "2026-02-27T10:30:00Z"
}
```

#### GET /bank/refund/<refund_id>
Poll refund status until completion.

**Response**:
```json
{
    "refund_id": "REF-00000001",
    "status": "PROCESSING|SUCCESS|FAILED",
    "bank_ref": "BRF123456",
    "timestamp": "2026-02-27T10:31:00Z"
}
```

#### POST /merchant/reconcile
Notify merchant of refund.

**Request**:
```json
{
    "upi_txn_id": "UPI123456",
    "resolution": "REFUND_APPROVED",
    "refund_id": "REF-00000001"
}
```

### Refund Status Enum

```python
class RefundStatus(Enum):
    INITIATED = "INITIATED"       # Refund created, bank not yet called
    PROCESSING = "PROCESSING"     # Bank processing the refund
    SUCCESS = "SUCCESS"           # Refund completed successfully
    FAILED = "FAILED"             # Refund failed
```

### Refund Method Enum

```python
class RefundMethod(Enum):
    INSTANT = "INSTANT"           # Immediate refund
    SCHEDULED = "SCHEDULED"       # Scheduled for later
    MANUAL = "MANUAL"             # Manual refund needed
    BANK_TRANSFER = "BANK_TRANSFER"  # Via bank transfer
```

### Usage Example

```python
from app.services import RefundService
from app.models.dispute import Dispute
from app.models.refund import RefundMethod

refunder = RefundService()
dispute = db.session.get(Dispute, 123)

# Process refund
try:
    refund = refunder.process_refund(
        dispute=dispute,
        refund_method=RefundMethod.INSTANT
    )
    
    if refund.status.value == "SUCCESS":
        print(f"Refund successful! Bank ref: {refund.bank_refund_ref}")
    else:
        print(f"Refund failed: {refund.failure_reason}")
        
except RefundServiceError as e:
    print(f"Refund processing error: {e}")
```

### Idempotency

Refund processing is fully idempotent:
- If refund already exists for dispute, returns existing refund
- Can safely retry process_refund() without creating duplicates
- No side effects if called multiple times

---

## Integration Example: Complete Verification + Refund Flow

```python
from app.services import VerificationService, RefundService, DecisionType
from app.models.dispute import Dispute
from app import db

def handle_dispute(dispute_id: int):
    """Complete dispute resolution workflow"""
    
    # Step 1: Verify dispute
    verifier = VerificationService()
    verification = verifier.verify_dispute(dispute_id)
    
    # Step 2: Check decision
    dispute = db.session.get(Dispute, dispute_id)
    
    if verification.decision == "APPROVED":
        # Step 3: Process refund if approved
        refunder = RefundService()
        refund = refunder.process_refund(dispute)
        
        if refund.status.value == "SUCCESS":
            print(f"Dispute {dispute_id} resolved: Refund successful")
        else:
            print(f"Dispute {dispute_id}: Refund in progress...")
    
    elif verification.decision == "REJECTED":
        print(f"Dispute {dispute_id}: Rejected (not refund eligible)")
    
    elif verification.decision == "INCONCLUSIVE":
        print(f"Dispute {dispute_id}: Retry scheduled")
    
    else:  # MANUAL_REVIEW
        print(f"Dispute {dispute_id}: Escalated to human team")

# Usage
handle_dispute(dispute_id=1)
```

---

## Testing & Scenarios

Mock Bank/Merchant APIs support scenario parameters for deterministic testing:

```python
# Get success scenario
bank = BankClient()
response = bank.get_transaction_status("UPI123", scenario="success")
# Returns: DEBIT_SUCCESS

# Get failure scenario
response = bank.get_transaction_status("UPI123", scenario="failed")
# Returns: DEBIT_FAILED

# Get pending scenario
response = bank.get_transaction_status("UPI123", scenario="pending")
# Returns: PENDING

# Get not found scenario
response = bank.get_transaction_status("UPI123", scenario="notfound")
# Returns: NOT_FOUND

# Random scenario (default)
response = bank.get_transaction_status("UPI123")
# Returns: Random status
```

---

## Configuration & Customization

### Environment Variables

```bash
# Bank API settings
BANK_API_URL=http://localhost:5001
BANK_API_TIMEOUT=5
BANK_MAX_RETRIES=3

# Merchant API settings
MERCHANT_API_URL=http://localhost:5002
MERCHANT_API_TIMEOUT=5
MERCHANT_MAX_RETRIES=3
```

### Retry Configuration

Adjust retry behavior in service initialization:

```python
# Custom bank retries
bank = BankClient(
    base_url="http://bank.example.com:5001",
    timeout=10,      # 10 second timeout
    max_retries=5,   # 5 retry attempts
)

# Custom verification schedule
verifier = VerificationService(bank_client=bank)
# Retry schedule is fixed in RETRY_SCHEDULE dict
```

---

## Error Handling

All services raise specific exception types for proper error handling:

```python
from app.services import (
    BankClientError,
    MerchantClientError,
    VerificationServiceError,
    RefundServiceError,
)

try:
    bank = BankClient()
    response = bank.get_transaction_status("UPI123")
except BankClientError as e:
    print(f"Bank error: {e}")

try:
    verifier = VerificationService()
    verification = verifier.verify_dispute(1)
except VerificationServiceError as e:
    print(f"Verification error: {e}")
```

---

## Performance Considerations

### Bank/Merchant Clients
- **Timeout**: 5 seconds per request (configurable)
- **Retries**: 3 attempts with 1-second delays between attempts
- **Total Max Time**: ~8 seconds per status fetch

### Verification Service
- **Bank API Call**: ~5 seconds (average with retries)
- **Merchant API Call**: ~5 seconds (average with retries)
- **Decision Processing**: <100ms
- **DB Operations**: <100ms
- **Total**: ~10 seconds per verification attempt

### Refund Service
- **Refund Initiation**: ~5 seconds
- **Status Polling**: 2-second intervals, max 60 seconds
- **Merchant Notification**: ~5 seconds
- **Total**: ~70 seconds end-to-end

---

## Database Schema Integration

Services use these SQLAlchemy models:

- `Dispute`: state, resolution, retry_count, next_check_at
- `VerificationCheck`: attempt_no, bank_result, merchant_result, decision, confidence_score
- `Refund`: refund_id, status, bank_refund_ref, failure_reason
- `Transaction`: upi_txn_id, amount, status
- `APIKey`: role-based access control

---

## Logging

All services use structured JSON logging with correlation IDs:

```
{
    "timestamp": "2026-02-27T10:30:00Z",
    "level": "INFO",
    "logger": "app.services.bank_client",
    "message": "Fetching bank status for UPI123456 (attempt 1/3)",
    "correlation_id": "corr-12345",
    "client_id": "demo-merchant-1"
}
```
