# Background Agent Documentation

## Overview

The Dispute Resolution Agent (`app/agent/dispute_agent.py`) is the core automation system that continuously processes disputes and refunds without manual intervention.

## Architecture

```
┌──────────────────────────────────┐
│    Dispute Resolution Agent      │
│  (DisputeAgent class)            │
└────────────┬─────────────────────┘
             │
      ┌──────┴──────┐
      │             │
    ┌─▼──────┐  ┌──▼──────┐
    │Verify  │  │Refund   │
    │Disputes│  │Polling  │
    └─┬──────┘  └──┬──────┘
      │             │
 ┌────▼─────┐  ┌───▼──────┐
 │Verific.  │  │Refund    │
 │Service   │  │Service   │
 └──────────┘  └──────────┘
```

## Components

### 1. DisputeAgent Class (`dispute_agent.py`)

**Main agent logic**

```python
class DisputeAgent:
    def run_cycle() -> Dict[str, Any]:
        # Run one complete processing cycle
        # 1. Query disputes needing processing
        # 2. Run verifications for OPEN/VERIFYING disputes
        # 3. Poll refunds for REFUND_IN_PROGRESS disputes
        # 4. Commit changes
        # 5. Return results

    def _get_disputes_needing_verification() -> List[Dispute]:
        # Find OPEN/VERIFYING disputes where next_check_at <= now

    def _get_disputes_needing_refund_polling() -> List[Dispute]:
        # Find REFUND_IN_PROGRESS disputes with pending refunds

    def _process_verification(dispute: Dispute) -> None:
        # Run verification for single dispute
        # Update dispute state based on decision

    def _process_refund_polling(dispute: Dispute) -> None:
        # Poll refund status via bank API
        # Update refund and dispute state
```

### 2. Entry Points

#### A. CLI Command (`run_agent.py`)

Three modes of execution:

```bash
# Run one cycle immediately
python run_agent.py run

# Run with scheduler (every 120 seconds)
python run_agent.py schedule --interval 120

# Run continuously (simple daemon loop)
python run_agent.py daemon --delay 1
```

#### B. API Endpoint

```bash
# Trigger one cycle via HTTP
POST /internal/run-agent
X-API-Key: <INTERNAL_AGENT_key>

# Response
{
    "success": true,
    "data": {
        "disputes_processed": 5,
        "disputes_verified": 3,
        "disputes_refunded": 1,
        "disputes_failed": 0,
        ...
    }
}
```

#### C. Programmatic Usage

```python
from app.agent import run_agent_cycle

results = run_agent_cycle()
# results contains cycle summary
```

### 3. Scheduler (`scheduler.py`)

**Optional APScheduler integration** (development mode only)

```python
from app.agent.scheduler import init_scheduler

# In Flask app initialization
init_scheduler(app)  # Runs agent every 120 seconds
```

## Processing Logic

### Cycle Workflow

```
START CYCLE
    │
    ├─→ Query OPEN/VERIFYING disputes
    │   (where next_check_at <= now)
    │
    ├─→ For each dispute:
    │   └─→ Run VerificationService.verify_dispute()
    │       ├─→ Fetch bank status
    │       ├─→ Fetch merchant status
    │       ├─→ Run decision engine
    │       └─→ Update dispute state
    │
    ├─→ Query REFUND_IN_PROGRESS disputes
    │   (with pending refunds)
    │
    ├─→ For each dispute:
    │   └─→ Poll refund status via bank API
    │       ├─→ Check if refund completed
    │       ├─→ Update refund status
    │       └─→ Update dispute state
    │
    ├─→ Commit all database changes
    │
    └─→ Log cycle summary
        ├─→ Disputes processed
        ├─→ Verification decisions
        ├─→ Refund statuses
        └─→ Errors encountered

END CYCLE
```

## Dispute States

### State Transitions

```
OPEN
  └─→ run_agent_cycle()
      └─→ verify_dispute()
          ├─→ Decision: RETRY
          │   └─→ State: VERIFYING
          │       next_check_at: +5 min
          │
          ├─→ Decision: APPROVED/REFUND
          │   └─→ State: ACTION_REQUIRED
          │       resolution: REFUND
          │       (human approves refund)
          │
          ├─→ Decision: REJECTED/NO_DEBIT
          │   └─→ State: RESOLVED
          │
          └─→ Decision: MANUAL_REVIEW
              └─→ State: ACTION_REQUIRED

ACTION_REQUIRED (with REFUND resolution)
  └─→ Manual approval or admin action
      └─→ process_refund()
          └─→ State: REFUND_IN_PROGRESS
              refund.status: INITIATED

REFUND_IN_PROGRESS
  └─→ run_agent_cycle()
      └─→ poll_refund_status()
          ├─→ Bank status: SUCCESS
          │   └─→ State: RESOLVED
          │       refund.status: SUCCESS
          │       refund.completed_at: now
          │
          └─→ Bank status: FAILED
              └─→ State: ACTION_REQUIRED
                  refund.status: FAILED
```

## Query Patterns

### Finding Disputes to Verify

```python
# Disputes in OPEN state (initial verification)
# OR VERIFYING state where next check is due

disputes = db.session.query(Dispute).filter(
    Dispute.state.in_([DisputeState.OPEN, DisputeState.VERIFYING]),
    (Dispute.next_check_at.is_(None)) |  # First check
    (Dispute.next_check_at <= datetime.utcnow())  # Scheduled check due
).order_by(Dispute.created_at.asc()).all()
```

### Finding Disputes to Poll Refunds

```python
# Disputes in REFUND_IN_PROGRESS with pending refunds

disputes = db.session.query(Dispute).filter(
    Dispute.state == DisputeState.REFUND_IN_PROGRESS
).all()

# Filter to those with pending refunds
pending = [d for d in disputes
           if d.refunds and d.refunds[0].status in [
               RefundStatus.INITIATED,
               RefundStatus.PROCESSING
           ]]
```

## Response Format

### Cycle Results

```json
{
    "disputes_processed": 5,
    "disputes_verified": 3,
    "disputes_refunded": 1,
    "disputes_failed": 0,
    "verification_decisions": {
        "APPROVED": 2,
        "INCONCLUSIVE": 1,
        "REJECTED": 0
    },
    "refund_statuses": {
        "SUCCESS": 1,
        "PROCESSING": 0,
        "INITIATED": 0,
        "FAILED": 0
    },
    "processed_disputes": [
        {
            "dispute_id": 1,
            "action": "VERIFIED",
            "decision": "APPROVED",
            "confidence_score": 0.95,
            "attempt_no": 1,
            "status": "success",
            "timestamp": "2026-02-27T10:35:00Z"
        },
        {
            "dispute_id": 2,
            "action": "REFUND_POLLED",
            "refund_id": "REF-00000001",
            "refund_status": "SUCCESS",
            "dispute_state": "RESOLVED",
            "status": "success",
            "timestamp": "2026-02-27T10:35:02Z"
        }
    ],
    "errors": [
        {
            "type": "VERIFICATION_ERROR",
            "dispute_id": 3,
            "message": "Bank API timeout"
        }
    ]
}
```

## Exponential Backoff Schedule

Retries use increasing delays to avoid overwhelming systems:

| Attempt | Reason | Delay | Status |
|---------|--------|-------|--------|
| 1 | Both PENDING | 5 min | VERIFYING |
| 2 | Still PENDING | 15 min | VERIFYING |
| 3 | Still PENDING | 60 min | VERIFYING |
| 4 | Still PENDING | 360 min (6h) | VERIFYING |
| 5+ | Max retries reached | - | ACTION_REQUIRED |

## Error Handling

### Error Types

- **VERIFICATION_ERROR**: Failed to run verification
- **REFUND_POLLING_ERROR**: Failed to poll refund status
- **COMMIT_FAILED**: Failed to commit database changes
- **CYCLE_FAILED**: Critical error in cycle execution
- **UNEXPECTED_ERROR**: Unhandled exception

### Error Recovery

**Non-fatal errors**:
- Individual dispute verification failures
- Individual refund polling failures
- These disputes are skipped, others continue processing

**Fatal errors**:
- Database commit failures
- Entire cycle is rolled back and reported

## Logging

### Log Levels

- **INFO**: Cycle start/end, disputes processed, decisions made
- **WARNING**: Disputes in unexpected states, max retries reached
- **ERROR**: Service failures, verification errors, refund failures

### Log Output Example

```
2026-02-27 10:35:00 - app.agent.dispute_agent - INFO - ============================================================
2026-02-27 10:35:00 - app.agent.dispute_agent - INFO - Starting agent cycle at 2026-02-27T10:35:00Z
2026-02-27 10:35:00 - app.agent.dispute_agent - INFO - ============================================================
2026-02-27 10:35:00 - app.agent.dispute_agent - INFO - Found 3 disputes needing verification
2026-02-27 10:35:00 - app.agent.dispute_agent - INFO - Found 1 disputes needing refund polling
2026-02-27 10:35:01 - app.agent.dispute_agent - INFO - Processing verification for dispute 1
2026-02-27 10:35:02 - app.agent.dispute_agent - INFO - Dispute 1 verified: decision=APPROVED, confidence=0.95, new_state=ACTION_REQUIRED
2026-02-27 10:35:02 - app.agent.dispute_agent - INFO - Processing verification for dispute 2
2026-02-27 10:35:03 - app.agent.dispute_agent - INFO - Dispute 2 verified: decision=INCONCLUSIVE, confidence=0.65, new_state=VERIFYING
2026-02-27 10:35:03 - app.agent.dispute_agent - INFO - Polling refund status for dispute 10 (refund_id=REF-00000001)
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Refund REF-00000001 status changed: PROCESSING → SUCCESS
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - All changes committed successfully
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - ============================================================
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - AGENT CYCLE SUMMARY
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - ============================================================
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Total disputes processed: 4
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Disputes verified: 3
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Disputes refunded: 1
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Disputes failed: 0
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Verification decisions:
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO -   - APPROVED: 2
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO -   - INCONCLUSIVE: 1
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Refund statuses:
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO -   - SUCCESS: 1
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - Cycle completed in 4.23 seconds
2026-02-27 10:35:04 - app.agent.dispute_agent - INFO - ============================================================
```

## Usage Examples

### Example 1: Run One Cycle via CLI

```bash
$ python run_agent.py run

Starting agent cycle...
============================================================
CYCLE RESULTS
============================================================
Processed: 5
Verified: 3
Refunded: 1
Failed: 0
============================================================
```

### Example 2: Run Scheduler

```bash
$ python run_agent.py schedule --interval 120

Starting agent scheduler (interval: 120s)...
Agent scheduler started (interval: 120s)
Press Ctrl+C to stop

2026-02-27 10:35:00 - Cycle completed: processed=5, verified=3, refunded=1, failed=0
2026-02-27 10:37:00 - Cycle completed: processed=2, verified=2, refunded=0, failed=0
2026-02-27 10:39:00 - Cycle completed: processed=0, verified=0, refunded=0, failed=0
```

### Example 3: Run Daemon

```bash
$ python run_agent.py daemon --delay 2

Agent daemon started
Press Ctrl+C to stop

2026-02-27 10:35:00 - Cycle #1: processed=5, verified=3, refunded=1
2026-02-27 10:35:02 - Cycle #2: processed=2, verified=2, refunded=0
2026-02-27 10:35:04 - Cycle #3: processed=0, verified=0, refunded=0
```

### Example 4: API Trigger

```bash
curl -X POST http://localhost:5000/internal/run-agent \
  -H "X-API-Key: internal-agent-key" \
  -H "X-Timestamp: $(date +%s)" \
  -H "X-Nonce: $(uuidgen)" \
  -H "X-HMAC-Signature: ..."

# Response
{
    "success": true,
    "data": {
        "disputes_processed": 5,
        "disputes_verified": 3,
        "disputes_refunded": 1,
        ...
    }
}
```

## Performance Characteristics

### Time Complexity

- **Per verification**: ~5-10 seconds (includes API calls with retries)
- **Per refund poll**: ~2-10 seconds (includes periodic polling)
- **Per cycle**: N * (avg_time_per_operation) + 0.5 seconds (DB commit)

### Scalability

**Current implementation**:
- Single-threaded synchronous processing
- Handles ~10-50 disputes per minute per instance
- Suitable for small-to-medium deployments

**For scaling**:
- Multiple agent instances with load balancing
- Message queue (Celery/RabbitMQ) for true parallelism
- Horizontal scaling with partitioned queues

## Monitoring & Debugging

### Check Agent Status

```bash
# Via API
curl http://localhost:5000/api/analytics/summary \
  -H "X-API-Key: admin-key"

# Via CLI
python run_agent.py run  # Shows results
```

### Monitor Logs

```bash
# Real-time logs
tail -f logs/agent.log

# Filter by severity
tail -f logs/agent.log | grep ERROR
```

### Debug Single Dispute

```python
# In Python shell
from app import create_app, db
from app.models.dispute import Dispute
from app.agent import run_agent_cycle

app = create_app()
with app.app_context():
    # Check dispute state
    dispute = db.session.get(Dispute, 1)
    print(f"State: {dispute.state}")
    print(f"Next check: {dispute.next_check_at}")
    print(f"Retries: {dispute.retry_count}")
    
    # Run cycle
    results = run_agent_cycle()
    print(results)
```

## Configuration

### Optional: APScheduler Integration

To enable auto-scheduling in development mode:

1. Install APScheduler: `pip install apscheduler`
2. Modify `app/__init__.py` to call `init_scheduler(app)`
3. Agent will run automatically every 2 minutes

**Note**: APScheduler is optional. The agent works fine with manual triggers via CLI or API.

## Testing

### Test Scenarios

```python
# 1. Create dispute in OPEN state
dispute = Dispute(
    transaction_id=1,
    raised_by='CUSTOMER',
    reason_code='TRANSACTION_NOT_RECEIVED',
    state=DisputeState.OPEN
)
db.session.add(dispute)
db.session.commit()

# 2. Run agent cycle
results = run_agent_cycle()

# 3. Check that dispute was verified
dispute = db.session.get(Dispute, dispute.id)
assert dispute.state in [DisputeState.VERIFYING, DisputeState.RESOLVED, DisputeState.ACTION_REQUIRED]
```

---

The background agent is the core automation engine that enables fully autonomous dispute resolution without human intervention (except for manual reviews escalated to ACTION_REQUIRED state).
