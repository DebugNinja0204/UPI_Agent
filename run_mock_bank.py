#!/usr/bin/env python
"""
Launcher script for Mock Bank API
Run this to start the Mock Bank service on port 5001
"""

if __name__ == '__main__':
    from mock_bank.app import app
    print("\n" + "="*60)
    print("🏦 Mock Bank API")
    print("="*60)
    print("Service: Bank Transaction & Refund Processing")
    print("Port: 5001")
    print("\nEndpoints:")
    print("  • GET  /bank/txn/<upi_txn_id>     - Transaction status")
    print("  • POST /bank/refund                - Initiate refund")
    print("  • GET  /bank/refund/<refund_id>   - Refund status")
    print("  • GET  /health                     - Health check")
    print("  • GET  /bank/stats                 - Statistics")
    print("\nTest with scenario parameter:")
    print("  ?scenario=success|failed|pending|notfound|random")
    print("="*60)
    print()
    
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
