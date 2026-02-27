# UPI Dispute Resolution Agent

An automated, intelligent system for handling UPI (Unified Payments Interface) payment disputes with end-to-end workflow automation, from dispute creation to refund completion.

## 🚀 Overview

This platform automates the entire dispute resolution lifecycle: validating claims, verifying with banks and merchants, making rule-based decisions (with optional AI enhancement), initiating refunds, and tracking completion—all without manual intervention.

**Resolution time:** 5-15 seconds (vs. days with manual processes)

## ✨ Key Features

- **Automated Dispute Processing** - Background agent processes disputes every 5 seconds
- **Multi-Party Verification** - Integrates with bank and merchant APIs for real-time validation
- **Rule-Based Decision Engine** - Consistent, unbiased decision-making with configurable rules
- **Optional AI Enhancement** - Gemini AI integration for complex edge cases
- **Autonomous Refund Workflow** - Auto-initiates and polls refund status until completion
- **Real-Time Dashboard** - Live dispute tracking with state transitions
- **Enterprise Security** - API key authentication, replay protection, idempotency, rate limiting
- **Complete Audit Trail** - Full logging and state history for compliance

## 🏗️ Architecture

```
User/Client → Flask API Gateway → Security Layer → Business Logic
                                                      ↓
                            Background Agent ← Decision Engine ← Verification Service
                                  ↓                                  ↓
                            SQLite Database                    Bank/Merchant APIs
                                  ↓
                            Refund Service → Bank Refund API
```

### Dispute State Machine
```
OPEN → VERIFYING → ACTION_REQUIRED → REFUND_IN_PROGRESS → RESOLVED
```

## 🛠️ Tech Stack

- **Backend:** Python 3.12, Flask
- **Database:** SQLite (dev), PostgreSQL-ready
- **ORM:** SQLAlchemy
- **Background Processing:** APScheduler
- **AI (Optional):** Google Gemini API
- **Security:** HMAC, JWT-style authentication, replay protection
- **API:** RESTful with JSON responses

## 📦 Installation

### Prerequisites
- Python 3.12+
- pip
- Git

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/DebugNinja0204/UPI_Agent.git
cd UPI_Agent
```

2. **Create virtual environment**
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# or
source .venv/bin/activate  # Linux/Mac
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Seed database** (optional, for testing)
```bash
python seed_data.py
```

## 🚀 Usage

### Start All Services

**Terminal 1 - Main API:**
```bash
python run.py
```
→ Runs on http://localhost:5000

**Terminal 2 - Mock Bank:**
```bash
python run_mock_bank.py
```
→ Runs on http://localhost:5001

**Terminal 3 - Mock Merchant:**
```bash
python run_mock_merchant.py
```
→ Runs on http://localhost:5002

**Terminal 4 - Background Agent:**
```bash
python run_agent.py daemon --delay 5
```
→ Processes disputes every 5 seconds

### Access Dashboard
Open browser: http://localhost:5000/dashboard

**API Key for testing:** `test_merchant_eval_2026`

## 📡 API Endpoints

### Create Dispute
```http
POST /api/disputes
Headers:
  X-API-Key: test_merchant_eval_2026
  X-Timestamp: 2026-02-28T10:00:00Z
  X-Nonce: <uuid>
  Idempotency-Key: <uuid>
Body:
{
  "upi_txn_id": "UPI_TEST_1001",
  "raised_by": "MERCHANT",
  "reason_code": "WRONG_AMOUNT",
  "amount": 500.0
}
```

### Get Dispute Status
```http
GET /api/disputes/{dispute_id}
Headers:
  X-API-Key: test_merchant_eval_2026
```

### List Disputes
```http
GET /api/disputes?state=OPEN&page=1&per_page=10
Headers:
  X-API-Key: test_merchant_eval_2026
```

## 🔐 Security Features

- **API Key Authentication** - Role-based access control (MERCHANT, BANK, ADMIN)
- **Replay Protection** - Timestamp validation (5-minute window)
- **Idempotency** - Prevent duplicate dispute creation
- **Rate Limiting** - Configurable per-client limits
- **HMAC Signatures** - Request integrity verification
- **Input Validation** - Pydantic schemas for all endpoints

## 📊 Decision Engine

### Rule-Based Logic
- `WRONG_AMOUNT` → Refund
- `DUPLICATE_TRANSACTION` → Refund
- `TRANSACTION_NOT_RECEIVED` → Refund
- `FRAUDULENT_TRANSACTION` → Manual Review
- Bank/Merchant down → Retry with backoff

### Optional AI Enhancement
Enable Gemini for low-confidence cases:
```bash
export GEMINI_API_KEY="your-api-key"
export GEMINI_DECISION_ENABLED="true"
```

## 🧪 Testing

### Test Credentials
```
API Keys:
  Merchant: test_merchant_eval_2026
  Bank: test_bank_key_20260227
  Admin: test_admin_key_20260227

UPI IDs:
  UPI_TEST_1001
  UPI_TEST_1002
  UPI_NISHA_2026_01
```

### Run Single Agent Cycle (Manual Test)
```bash
python run_agent.py run
```

### Example Test Flow
1. Create dispute via dashboard (OPEN)
2. Agent detects and verifies (VERIFYING)
3. Decision made (ACTION_REQUIRED)
4. Refund initiated (REFUND_IN_PROGRESS)
5. Refund confirmed (RESOLVED) ✓

**Expected completion:** ~5-15 seconds

## 📂 Project Structure

```
upi_agent/
├── app/
│   ├── agent/              # Background processing
│   ├── api/                # REST endpoints
│   ├── models/             # Database models
│   ├── security/           # Authentication & protection
│   ├── services/           # Business logic
│   └── templates/          # Dashboard UI
├── config/                 # Configuration
├── mock_bank/              # Mock bank service
├── mock_merchant/          # Mock merchant service
├── instance/               # Database files (gitignored)
├── requirements.txt        # Python dependencies
├── run.py                  # Main API server
├── run_agent.py            # Background agent
└── seed_data.py            # Test data generator
```

## 🔄 Workflow

1. **Dispute Created** → API validates and stores in DB (state: OPEN)
2. **Agent Detects** → Background daemon picks up dispute every 5s
3. **Verification** → Calls Bank + Merchant APIs for validation
4. **Decision** → Rule engine (+ optional AI) determines outcome
5. **Refund Initiation** → If approved, calls Bank refund API
6. **Polling** → Checks refund status every 2 seconds (max 60s)
7. **Resolution** → Updates dispute to RESOLVED when complete

## 📈 Performance

| Metric | Value |
|--------|-------|
| Dispute creation | < 100ms |
| Verification | 500-1000ms |
| Decision | < 50ms |
| Full resolution | 5-15 seconds |
| Agent cycle | Every 5 seconds |
| Concurrent disputes | 1000+ |

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License.

## 👥 Authors

- **Nisha** - [@DebugNinja0204](https://github.com/DebugNinja0204)

## 🙏 Acknowledgments

- UPI ecosystem documentation
- Flask and SQLAlchemy communities
- Google Gemini AI team

## 📞 Support

For issues or questions:
- Open an issue on GitHub
- Check existing documentation in `/docs` folder

---

**Built with ❤️ for automated financial dispute resolution**
