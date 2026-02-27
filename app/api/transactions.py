"""
Transactions API Endpoints

Routes for managing transactions.
Roles: MERCHANT, ADMIN
"""

from flask import Blueprint, request
from datetime import datetime
import logging
import uuid

from app import db
from app.models.transaction import Transaction
from app.security import require_api_key, require_role, input_validator
from .response import success_response, error_response, created_response

logger = logging.getLogger(__name__)

transactions_bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')


@transactions_bp.route('', methods=['POST'])
@require_api_key
@require_role('MERCHANT', 'ADMIN')
def create_transaction():
    """
    Create a new transaction.
    
    Request Body:
    {
        "upi_txn_id": "UPI123456",
        "payer_vpa": "customer@bank",
        "payee_vpa": "merchant@bank",
        "amount": 1000.00,
        "currency": "INR",
        "merchant_order_id": "ORD123456",
        "merchant_txn_id": "MTXN123456",
        "status": "SUCCESS|FAILED|PENDING|UNKNOWN"
    }
    
    Response: 201 Created
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
            "created_at": "2026-02-27T10:30:00Z"
        }
    }
    """
    try:
        data = request.get_json() or {}
        
        # Extract fields
        upi_txn_id = data.get('upi_txn_id', '').strip()
        payer_vpa = data.get('payer_vpa', '').strip()
        payee_vpa = data.get('payee_vpa', '').strip()
        amount = data.get('amount')
        currency = data.get('currency', 'INR').strip().upper()
        merchant_order_id = data.get('merchant_order_id', '').strip() or None
        merchant_txn_id = data.get('merchant_txn_id', '').strip() or None
        status = data.get('status', 'UNKNOWN').strip().upper()
        
        # Validate required fields
        if not upi_txn_id:
            return error_response("upi_txn_id is required", 400)
        
        # Validate optional UPI VPA fields
        if payer_vpa:
            is_valid, error_msg = input_validator.validate_upi_vpa(payer_vpa)
            if not is_valid:
                return error_response(f"Invalid payer_vpa: {error_msg}", 400)
        
        if payee_vpa:
            is_valid, error_msg = input_validator.validate_upi_vpa(payee_vpa)
            if not is_valid:
                return error_response(f"Invalid payee_vpa: {error_msg}", 400)
        
        # Validate amount
        if amount:
            is_valid, error_msg = input_validator.validate_amount(amount)
            if not is_valid:
                return error_response(f"Invalid amount: {error_msg}", 400)
        
        # Validate currency
        is_valid, error_msg = input_validator.validate_currency(currency)
        if not is_valid:
            return error_response(f"Invalid currency: {error_msg}", 400)
        
        # Validate status
        if status not in ['SUCCESS', 'FAILED', 'PENDING', 'UNKNOWN']:
            return error_response(
                "status must be one of: SUCCESS, FAILED, PENDING, UNKNOWN",
                400
            )
        
        # Check if transaction already exists
        existing = db.session.query(Transaction).filter_by(
            upi_txn_id=upi_txn_id
        ).first()
        
        if existing:
            logger.warning(f"Transaction already exists: {upi_txn_id}")
            return error_response(
                f"Transaction already exists (ID: {existing.id})",
                409,
                error_code='TRANSACTION_EXISTS'
            )
        
        # Create transaction
        transaction = Transaction(
            upi_txn_id=upi_txn_id,
            payer_vpa=payer_vpa or 'unknown@bank',
            payee_vpa=payee_vpa or 'unknown@merchant',
            amount=float(amount) if amount else 0.0,
            currency=currency,
            merchant_order_id=merchant_order_id,
            merchant_txn_id=merchant_txn_id,
        )
        
        # Map status
        status_mapping = {
            'SUCCESS': 'SUCCESS',
            'FAILED': 'FAILED',
            'PENDING': 'PENDING',
            'UNKNOWN': 'UNKNOWN',
        }
        transaction.current_status = status_mapping.get(status, 'UNKNOWN')
        
        db.session.add(transaction)
        db.session.commit()
        
        logger.info(f"Transaction created: {upi_txn_id} (ID: {transaction.id})")
        
        return created_response({
            'id': transaction.id,
            'upi_txn_id': transaction.upi_txn_id,
            'payer_vpa': transaction.payer_vpa,
            'payee_vpa': transaction.payee_vpa,
            'amount': transaction.amount,
            'currency': transaction.currency,
            'status': transaction.current_status,
            'merchant_order_id': transaction.merchant_order_id,
            'merchant_txn_id': transaction.merchant_txn_id,
            'created_at': transaction.created_at.isoformat(),
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating transaction: {str(e)}")
        return error_response(f"Error creating transaction: {str(e)}", 500)


@transactions_bp.route('/<upi_txn_id>', methods=['GET'])
@require_api_key
@require_role('MERCHANT', 'ADMIN')
def get_transaction(upi_txn_id):
    """
    Get transaction details.
    
    Response: 200 OK
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
            "disputes": [
                {
                    "id": 1,
                    "state": "RESOLVED",
                    "raised_by": "CUSTOMER"
                }
            ]
        }
    }
    """
    try:
        transaction = db.session.query(Transaction).filter_by(
            upi_txn_id=upi_txn_id
        ).first()
        
        if not transaction:
            return error_response(
                f"Transaction not found: {upi_txn_id}",
                404
            )
        
        # Format disputes
        disputes_data = []
        for dispute in transaction.disputes:
            disputes_data.append({
                'id': dispute.id,
                'state': dispute.state.value,
                'raised_by': dispute.raised_by,
                'reason_code': dispute.reason_code,
                'created_at': dispute.created_at.isoformat(),
            })
        
        return success_response({
            'id': transaction.id,
            'upi_txn_id': transaction.upi_txn_id,
            'payer_vpa': transaction.payer_vpa,
            'payee_vpa': transaction.payee_vpa,
            'amount': transaction.amount,
            'currency': transaction.currency,
            'status': transaction.current_status,
            'bank_rrn': transaction.bank_rrn,
            'merchant_order_id': transaction.merchant_order_id,
            'merchant_txn_id': transaction.merchant_txn_id,
            'created_at': transaction.created_at.isoformat(),
            'updated_at': transaction.updated_at.isoformat(),
            'disputes': disputes_data,
        })
    
    except Exception as e:
        logger.error(f"Error getting transaction {upi_txn_id}: {str(e)}")
        return error_response(f"Error getting transaction: {str(e)}", 500)
