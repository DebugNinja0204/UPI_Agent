"""
Mock Bank API Service

Simulates bank operations for testing the UPI Dispute Resolution Agent.
Runs on port 5001.
"""

from flask import Flask, request, jsonify, g
from datetime import datetime, timedelta
import uuid
import random
import json

app = Flask(__name__)

# Configuration
app.config['DEBUG'] = True
BANK_PORT = 5001

# In-memory storage for refunds
# Format: {refund_id: {status, upi_txn_id, amount, created_at, last_updated}}
refunds_storage = {}

# Track when refunds were initiated for processing simulation
refund_timestamps = {}


@app.before_request
def before_request():
    """Add request tracking"""
    g.request_id = str(uuid.uuid4())[:8]
    g.request_start = datetime.utcnow()


@app.after_request
def after_request(response):
    """Add response headers"""
    response.headers['X-Request-ID'] = g.request_id
    response.headers['X-Bank-Service'] = 'MockBank/1.0'
    return response


# =====================
# Transaction Endpoints
# =====================

@app.route('/bank/txn/<upi_txn_id>', methods=['GET'])
def get_transaction_status(upi_txn_id):
    """
    Get transaction status from bank.
    
    Query Parameters:
    - scenario: 'success' | 'failed' | 'pending' | 'notfound' | 'random' (default)
    
    Returns transaction status with bank details.
    """
    scenario = request.args.get('scenario', 'random').lower()
    
    # Determine status based on scenario
    statuses = {
        'success': 'DEBIT_SUCCESS',
        'failed': 'DEBIT_FAILED',
        'pending': 'PENDING',
        'notfound': 'NOT_FOUND',
    }
    
    if scenario == 'random':
        status = random.choice(['DEBIT_SUCCESS', 'DEBIT_FAILED', 'PENDING', 'NOT_FOUND'])
    else:
        status = statuses.get(scenario, 'DEBIT_SUCCESS')
    
    # Generate or retrieve bank RRN
    bank_rrn = f"RRN{upi_txn_id[:8].upper()}{random.randint(1000, 9999)}"
    
    # Simulate transaction details
    amount = round(random.uniform(10, 5000), 2)
    
    response_data = {
        'upi_txn_id': upi_txn_id,
        'bank_rrn': bank_rrn,
        'amount': amount,
        'currency': 'INR',
        'status': status,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'bank_name': 'Mock Bank',
        'payer_name': 'Payer Account Holder',
        'payee_name': 'Payee Account Holder',
    }
    
    # Add extra details based on status
    if status == 'DEBIT_SUCCESS':
        response_data['debit_timestamp'] = (datetime.utcnow() - timedelta(minutes=random.randint(1, 60))).isoformat() + 'Z'
        response_data['credited_to_account'] = True
    elif status == 'DEBIT_FAILED':
        response_data['failure_reason'] = random.choice([
            'Insufficient funds',
            'Account locked',
            'Invalid UPI handle',
            'Transaction timeout',
        ])
    elif status == 'PENDING':
        response_data['estimated_completion'] = (datetime.utcnow() + timedelta(minutes=random.randint(5, 30))).isoformat() + 'Z'
    
    return jsonify(response_data), 200


# =====================
# Refund Endpoints
# =====================

@app.route('/bank/refund', methods=['POST'])
def initiate_refund():
    """
    Initiate a refund for a transaction.
    
    Request Body:
    {
        "upi_txn_id": "UPI...",
        "amount": 500.00,
        "refund_id": "REF..." (idempotency key)
    }
    
    Returns refund record with INITIATED status.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Missing request body'}), 400
        
        # Validate required fields
        required = ['upi_txn_id', 'amount', 'refund_id']
        missing = [f for f in required if f not in data]
        
        if missing:
            return jsonify({'error': f'Missing fields: {missing}'}), 400
        
        upi_txn_id = data['upi_txn_id']
        amount = float(data['amount'])
        refund_id = data['refund_id']
        
        # Validate amount
        if amount <= 0:
            return jsonify({'error': 'Amount must be positive'}), 400
        
        # Check if refund already exists (idempotency)
        if refund_id in refunds_storage:
            existing = refunds_storage[refund_id]
            return jsonify({
                'refund_id': refund_id,
                'upi_txn_id': existing['upi_txn_id'],
                'amount': existing['amount'],
                'status': existing['status'],
                'created_at': existing['created_at'],
                'message': 'Refund already exists',
            }), 200  # Return 200 for idempotent operation
        
        # Create refund record
        now = datetime.utcnow().isoformat() + 'Z'
        refunds_storage[refund_id] = {
            'refund_id': refund_id,
            'upi_txn_id': upi_txn_id,
            'amount': amount,
            'status': 'INITIATED',
            'created_at': now,
            'updated_at': now,
            'bank_refund_ref': f"BREF{uuid.uuid4().hex[:12].upper()}",
        }
        
        # Store timestamp for status progression
        refund_timestamps[refund_id] = datetime.utcnow()
        
        return jsonify({
            'refund_id': refund_id,
            'upi_txn_id': upi_txn_id,
            'amount': amount,
            'status': 'INITIATED',
            'created_at': now,
            'bank_refund_ref': refunds_storage[refund_id]['bank_refund_ref'],
        }), 201
    
    except KeyError as e:
        return jsonify({'error': f'Missing field: {str(e)}'}), 400
    except ValueError as e:
        return jsonify({'error': f'Invalid value: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


@app.route('/bank/refund/<refund_id>', methods=['GET'])
def get_refund_status(refund_id):
    """
    Get refund status and simulate progression.
    
    Query Parameters:
    - scenario: 'success' | 'failed' | random (default)
    
    Simulates refund progression:
    INITIATED → PROCESSING → SUCCESS or FAILED
    """
    # Check if refund exists
    if refund_id not in refunds_storage:
        return jsonify({
            'error': 'Refund not found',
            'refund_id': refund_id,
        }), 404
    
    refund = refunds_storage[refund_id]
    scenario = request.args.get('scenario', 'random').lower()
    
    # Simulate progression based on time elapsed
    created_time = refund_timestamps.get(refund_id, datetime.utcnow())
    elapsed = (datetime.utcnow() - created_time).total_seconds()
    
    # Progression logic
    if refund['status'] == 'INITIATED':
        # After 2+ seconds, move to PROCESSING
        if elapsed >= 2:
            refund['status'] = 'PROCESSING'
            refund['updated_at'] = datetime.utcnow().isoformat() + 'Z'
    
    if refund['status'] == 'PROCESSING':
        # After 4+ seconds, move to final status
        if elapsed >= 4:
            if scenario == 'failed':
                final_status = 'FAILED'
            elif scenario == 'success':
                final_status = 'SUCCESS'
            else:
                # Random: 85% success, 15% failed
                final_status = 'SUCCESS' if random.random() < 0.85 else 'FAILED'
            
            refund['status'] = final_status
            refund['updated_at'] = datetime.utcnow().isoformat() + 'Z'
            
            if final_status == 'FAILED':
                refund['failure_reason'] = random.choice([
                    'Account does not exist',
                    'Refund limit exceeded',
                    'Bank processing error',
                    'Invalid bank account',
                ])
    
    # Build response
    response_data = {
        'refund_id': refund_id,
        'upi_txn_id': refund['upi_txn_id'],
        'amount': refund['amount'],
        'status': refund['status'],
        'created_at': refund['created_at'],
        'updated_at': refund['updated_at'],
        'bank_refund_ref': refund['bank_refund_ref'],
    }
    
    if 'failure_reason' in refund:
        response_data['failure_reason'] = refund['failure_reason']
    
    if refund['status'] == 'SUCCESS':
        response_data['refunded_at'] = refund['updated_at']
    
    return jsonify(response_data), 200


# =====================
# Health Endpoints
# =====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'mock-bank',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }), 200


@app.route('/bank/stats', methods=['GET'])
def bank_stats():
    """Get bank service statistics"""
    refund_statuses = {}
    for refund in refunds_storage.values():
        status = refund['status']
        refund_statuses[status] = refund_statuses.get(status, 0) + 1
    
    return jsonify({
        'total_refunds': len(refunds_storage),
        'refund_statuses': refund_statuses,
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
    print(f"🏦 Mock Bank API starting on http://0.0.0.0:{BANK_PORT}")
    print("Endpoints:")
    print(f"  GET  /bank/txn/<upi_txn_id>          - Get transaction status")
    print(f"  POST /bank/refund                    - Initiate refund")
    print(f"  GET  /bank/refund/<refund_id>        - Get refund status")
    print(f"  GET  /health                         - Health check")
    print(f"  GET  /bank/stats                     - Service statistics")
    print()
    
    app.run(host='0.0.0.0', port=BANK_PORT, debug=True, use_reloader=False)
