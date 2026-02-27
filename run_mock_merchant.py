#!/usr/bin/env python
"""
Launcher script for Mock Merchant API
Run this to start the Mock Merchant service on port 5002
"""

if __name__ == '__main__':
    from mock_merchant.app import app
    print("\n" + "="*60)
    print("🏪 Mock Merchant API")
    print("="*60)
    print("Service: Merchant Order & Reconciliation")
    print("Port: 5002")
    print("\nEndpoints:")
    print("  • GET  /merchant/status            - Order status")
    print("  • POST /merchant/reconcile         - Reconcile dispute")
    print("  • GET  /merchant/reconcile/<id>    - Reconciliation status")
    print("  • GET  /health                     - Health check")
    print("  • GET  /merchant/stats             - Statistics")
    print("\nTest with scenario parameter:")
    print("  ?scenario=success|failed|pending|notfound|random")
    print("="*60)
    print()
    
    app.run(host='0.0.0.0', port=5002, debug=True, use_reloader=False)
