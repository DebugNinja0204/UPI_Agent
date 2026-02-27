"""
Mock Merchant API Service

Simulates merchant operations for testing the UPI Dispute Resolution Agent.
Runs on port 5002.
"""

from flask import Flask, request, jsonify, g
from datetime import datetime
import uuid
import random

app = Flask(__name__)

# Configuration
app.config['DEBUG'] = True
MERCHANT_PORT = 5002

# In-memory storage for reconciliations
# Format: {upi_txn_id: {merchant_order_id, merchant_txn_id, status, reconciliation_status, ...}}
merchant_storage = {}

# In-memory storage for orders
# Format: {upi_txn_id: {merchant_order_id, amount, status, ...}}
orders_storage = {}


@app.before_request
def before_request():
    """Add request tracking"""
    g.request_id = str(uuid.uuid4())[:8]
    g.request_start = datetime.utcnow()


@app.after_request
def after_request(response):
    """Add response headers"""
    response.headers['X-Request-ID'] = g.request_id
    response.headers['X-Merchant-Service'] = 'MockMerchant/1.0'
    return response


# =====================
# Order Status Endpoints
# =====================

@app.route('/merchant/status', methods=['GET'])
def get_order_status():
    """
    Get order/transaction status from merchant perspective.
    
    Query Parameters:
    - upi_txn_id: UPI transaction ID (required)
    - scenario: 'success' | 'failed' | 'pending' | 'notfound' | 'random' (default)
    
    Returns order status with merchant details.
    """
    upi_txn_id = request.args.get('upi_txn_id')
    
    if not upi_txn_id:
        return jsonify({'error': 'Missing required parameter: upi_txn_id'}), 400
    
    scenario = request.args.get('scenario', 'random').lower()
    
    # Determine status based on scenario
    statuses = {
        'success': 'ORDER_SUCCESS',
        'failed': 'ORDER_FAILED',
        'pending': 'ORDER_PENDING',
        'notfound': 'NOT_FOUND',
    }
    
    if scenario == 'random':
        status = random.choice(['ORDER_SUCCESS', 'ORDER_FAILED', 'ORDER_PENDING', 'NOT_FOUND'])
    else:
        status = statuses.get(scenario, 'ORDER_SUCCESS')
    
    # Check if we have stored data for this transaction
    if upi_txn_id in orders_storage:
        order = orders_storage[upi_txn_id]
    else:
        # Generate merchant transaction details
        merchant_order_id = f"MO{upi_txn_id[:8].upper()}{random.randint(100000, 999999)}"
        merchant_txn_id = f"MT{uuid.uuid4().hex[:12].upper()}"
        amount = round(random.uniform(10, 5000), 2)
        
        order = {
            'merchant_order_id': merchant_order_id,
            'merchant_txn_id': merchant_txn_id,
            'amount': amount,
            'status': status,
        }
        orders_storage[upi_txn_id] = order
    
    # Build response
    response_data = {
        'upi_txn_id': upi_txn_id,
        'merchant_order_id': order['merchant_order_id'],
        'merchant_txn_id': order['merchant_txn_id'],
        'amount': order['amount'],
        'currency': 'INR',
        'status': status,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'merchant_id': 'MERCHANT001',
        'merchant_name': 'Mock Merchant Store',
    }
    
    # Add details based on status
    if status == 'ORDER_SUCCESS':
        response_data['order_received_at'] = (datetime.utcnow()).isoformat() + 'Z'
        response_data['order_confirmed'] = True
        response_data['delivery_status'] = random.choice(['PENDING', 'SHIPPED', 'DELIVERED'])
    elif status == 'ORDER_FAILED':
        response_data['failure_reason'] = random.choice([
            'Out of stock',
            'Payment declined by merchant',
            'Product unavailable',
            'Order rejected',
        ])
        response_data['order_confirmed'] = False
    elif status == 'ORDER_PENDING':
        response_data['order_confirmed'] = False
        response_data['estimated_confirmation'] = (datetime.utcnow()).isoformat() + 'Z'
    
    return jsonify(response_data), 200


# =====================
# Reconciliation Endpoints
# =====================

@app.route('/merchant/reconcile', methods=['POST'])
def reconcile_order():
    """
    Update reconciliation record for a dispute.
    
    Request Body:
    {
        "upi_txn_id": "UPI...",
        "resolution": "ACCEPTED" | "REJECTED" | "PARTIAL_REFUND",
        "refund_id": "REF..." (optional)
    }
    
    Returns acknowledged reconciliation record.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Missing request body'}), 400
        
        # Validate required fields
        required = ['upi_txn_id', 'resolution']
        missing = [f for f in required if f not in data]
        
        if missing:
            return jsonify({'error': f'Missing fields: {missing}'}), 400
        
        upi_txn_id = data['upi_txn_id']
        resolution = data['resolution'].upper()
        refund_id = data.get('refund_id')
        
        # Validate resolution
        allowed_resolutions = ['ACCEPTED', 'REJECTED', 'PARTIAL_REFUND']
        if resolution not in allowed_resolutions:
            return jsonify({
                'error': f'Invalid resolution. Allowed: {allowed_resolutions}',
            }), 400
        
        # Create reconciliation record
        now = datetime.utcnow().isoformat() + 'Z'
        reconciliation = {
            'upi_txn_id': upi_txn_id,
            'resolution': resolution,
            'refund_id': refund_id,
            'acknowledged': True,
            'acknowledged_at': now,
            'updated_at': now,
            'merchant_action': _get_merchant_action(resolution),
        }
        
        merchant_storage[upi_txn_id] = reconciliation
        
        return jsonify({
            'upi_txn_id': upi_txn_id,
            'resolution': resolution,
            'acknowledged': True,
            'acknowledged_at': now,
            'refund_id': refund_id,
            'merchant_action': reconciliation['merchant_action'],
            'message': f'Reconciliation {resolution.lower()} by merchant',
        }), 200
    
    except ValueError as e:
        return jsonify({'error': f'Invalid value: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/merchant/reconcile/<upi_txn_id>', methods=['GET'])
def get_reconciliation_status(upi_txn_id):
    """
    Get reconciliation status for a transaction.
    
    Returns the last reconciliation record if exists.
    """
    if upi_txn_id not in merchant_storage:
        return jsonify({
            'error': 'No reconciliation found',
            'upi_txn_id': upi_txn_id,
        }), 404
    
    reconciliation = merchant_storage[upi_txn_id]
    
    return jsonify({
        'upi_txn_id': upi_txn_id,
        'resolution': reconciliation['resolution'],
        'refund_id': reconciliation.get('refund_id'),
        'acknowledged': reconciliation['acknowledged'],
        'acknowledged_at': reconciliation['acknowledged_at'],
        'updated_at': reconciliation['updated_at'],
        'merchant_action': reconciliation['merchant_action'],
    }), 200


def _get_merchant_action(resolution):
    """Map resolution to merchant action"""
    actions = {
        'ACCEPTED': 'Acknowledged dispute, processing refund',
        'REJECTED': 'Rejected dispute claim',
        'PARTIAL_REFUND': 'Processing partial refund',
    }
    return actions.get(resolution, 'Pending action')


# =====================
# Health Endpoints
# =====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'mock-merchant',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }), 200


@app.route('/merchant/stats', methods=['GET'])
def merchant_stats():
    """Get merchant service statistics"""
    order_statuses = {}
    for order in orders_storage.values():
        status = order['status']
        order_statuses[status] = order_statuses.get(status, 0) + 1
    
    resolution_stats = {}
    for record in merchant_storage.values():
        resolution = record['resolution']
        resolution_stats[resolution] = resolution_stats.get(resolution, 0) + 1
    
    return jsonify({
        'total_orders': len(orders_storage),
        'order_statuses': order_statuses,
        'total_reconciliations': len(merchant_storage),
        'reconciliation_resolutions': resolution_stats,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }), 200


# =====================
# Error Handlers
# =====================

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not found',
        'path': request.path,
        'method': request.method,
    }), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    return jsonify({
        'error': 'Internal server error',
        'message': str(e),
    }), 500


if __name__ == '__main__':
    print(f"🏪 Mock Merchant API starting on http://0.0.0.0:{MERCHANT_PORT}")
    print("Endpoints:")
    print(f"  GET  /merchant/status                - Get order status")
    print(f"  POST /merchant/reconcile             - Reconcile dispute")
    print(f"  GET  /merchant/reconcile/<upi_txn_id> - Get reconciliation status")
    print(f"  GET  /health                         - Health check")
    print(f"  GET  /merchant/stats                 - Service statistics")
    print()
    
    app.run(host='0.0.0.0', port=MERCHANT_PORT, debug=True, use_reloader=False)
