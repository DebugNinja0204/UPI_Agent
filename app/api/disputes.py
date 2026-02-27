"""
Disputes API Endpoints

Routes for managing disputes.
Roles: MERCHANT, ADMIN
"""

from flask import Blueprint, request, g
from datetime import datetime, timedelta
from sqlalchemy import and_, or_
import logging

from app import db
from app.models.dispute import (
    Dispute,
    DisputeState,
    DisputeResolution,
    DisputeRaisedBy,
    DisputeReasonCode,
)
from app.models.transaction import Transaction
from app.models.verification_check import VerificationCheck
from app.security import (
    require_api_key,
    require_role,
    require_idempotency,
    input_validator,
)
from app.services import (
    VerificationService,
    VerificationServiceError,
    RefundService,
    RefundServiceError,
)
from .response import success_response, error_response, created_response

logger = logging.getLogger(__name__)

disputes_bp = Blueprint('disputes', __name__, url_prefix='/api/disputes')


@disputes_bp.route('', methods=['POST'])
@require_api_key
@require_role('MERCHANT', 'ADMIN')
@require_idempotency()
def create_dispute():
    """
    Raise a new dispute for a transaction.
    
    Request Body:
    {
        "upi_txn_id": "UPI123456",
        "raised_by": "CUSTOMER|MERCHANT|BANK",
        "reason_code": "TRANSACTION_NOT_RECEIVED|DUPLICATE_TRANSACTION|...",
        "notes": "Optional notes about the dispute"
    }
    
    Response: 201 Created
    {
        "success": true,
        "data": {
            "id": 1,
            "upi_txn_id": "UPI123456",
            "state": "OPEN",
            "raised_by": "CUSTOMER",
            "reason_code": "TRANSACTION_NOT_RECEIVED",
            "created_at": "2026-02-27T10:30:00Z"
        }
    }
    """
    try:
        # Parse request
        data = request.get_json() or {}
        
        upi_txn_id = data.get('upi_txn_id', '').strip()
        raised_by = data.get('raised_by', '').strip().upper()
        reason_code = data.get('reason_code', '').strip().upper()
        notes = data.get('notes', '').strip() or None

        requested_amount = data.get('amount')
        try:
            requested_amount = float(requested_amount) if requested_amount is not None else None
        except (TypeError, ValueError):
            requested_amount = None
        
        # Validate input
        if not upi_txn_id:
            return error_response("upi_txn_id is required", 400)
        
        if not raised_by or raised_by not in ['CUSTOMER', 'MERCHANT', 'BANK']:
            return error_response(
                "raised_by must be one of: CUSTOMER, MERCHANT, BANK",
                400
            )

        # Normalize UI/API aliases to model enum values
        reason_code_aliases = {
            'WRONG_AMOUNT': 'INCORRECT_AMOUNT',
            'UNAUTHORIZED_TRANSACTION': 'UNAUTHORISED_TRANSACTION',
            'PARTIAL_CREDIT': 'OTHER',
            'TRANSACTION_TIMEOUT': 'PROCESSING_ERROR',
            'CUSTOMER_DISPUTE': 'CHARGEBACK',
        }
        normalized_reason_code = reason_code_aliases.get(reason_code, reason_code)

        valid_reason_codes = {reason.value for reason in DisputeReasonCode}
        if not normalized_reason_code or normalized_reason_code not in valid_reason_codes:
            return error_response(
                "Invalid reason_code",
                400
            )
        
        # Find or create transaction
        transaction = db.session.query(Transaction).filter_by(
            upi_txn_id=upi_txn_id
        ).first()
        
        if not transaction:
            logger.info(f"Creating new transaction for {upi_txn_id}")
            fallback_amount = requested_amount if requested_amount and requested_amount > 0 else 500.0
            transaction = Transaction(
                upi_txn_id=upi_txn_id,
                payer_vpa='unknown@bank',
                payee_vpa='unknown@merchant',
                amount=fallback_amount,
                currency='INR',
            )
            db.session.add(transaction)
            db.session.flush()
        
        # Check if dispute already exists
        existing_dispute = db.session.query(Dispute).filter_by(
            upi_txn_id=transaction.upi_txn_id
        ).first()
        
        if existing_dispute:
            logger.warning(
                f"Dispute already exists for transaction {upi_txn_id}: {existing_dispute.id}"
            )
            return error_response(
                f"Dispute already exists for this transaction (ID: {existing_dispute.id})",
                409,
                error_code='DISPUTE_EXISTS'
            )
        
        # Create dispute
        dispute = Dispute(
            upi_txn_id=transaction.upi_txn_id,
            raised_by=DisputeRaisedBy[raised_by],
            reason_code=DisputeReasonCode(normalized_reason_code),
            state=DisputeState.OPEN,
            notes=notes,
        )
        db.session.add(dispute)
        db.session.commit()
        
        logger.info(
            f"Dispute created: ID={dispute.id}, "
            f"upi_txn_id={upi_txn_id}, raised_by={raised_by}"
        )
        
        return created_response({
            'id': dispute.id,
            'upi_txn_id': upi_txn_id,
            'state': dispute.state.value,
            'raised_by': dispute.raised_by.value,
            'reason_code': dispute.reason_code.value,
            'notes': dispute.notes,
            'created_at': dispute.created_at.isoformat(),
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating dispute: {str(e)}")
        return error_response(f"Error creating dispute: {str(e)}", 500)


@disputes_bp.route('', methods=['GET'])
@require_api_key
@require_role('MERCHANT', 'ADMIN')
def list_disputes():
    """
    List all disputes with optional filters.
    
    Query Parameters:
    - state: Filter by dispute state (OPEN, VERIFYING, ACTION_REQUIRED, etc.)
    - raised_by: Filter by who raised dispute (CUSTOMER, MERCHANT, BANK)
    - date_from: ISO date (inclusive)
    - date_to: ISO date (inclusive)
    - limit: Max results (default: 100, max: 500)
    - offset: Pagination offset (default: 0)
    
    Response: 200 OK
    {
        "success": true,
        "data": {
            "disputes": [...],
            "total": 42,
            "limit": 10,
            "offset": 0
        }
    }
    """
    try:
        # Parse query parameters
        state_filter = request.args.get('state', '').strip().upper() or None
        raised_by_filter = request.args.get('raised_by', '').strip().upper() or None
        date_from = request.args.get('date_from', '').strip() or None
        date_to = request.args.get('date_to', '').strip() or None
        limit = min(int(request.args.get('limit', '100')), 500)
        offset = int(request.args.get('offset', '0'))
        
        # Build query
        query = db.session.query(Dispute)
        
        # Apply filters
        if state_filter:
            try:
                state_enum = DisputeState[state_filter]
                query = query.filter_by(state=state_enum)
            except KeyError:
                return error_response(f"Invalid state: {state_filter}", 400)
        
        if raised_by_filter:
            query = query.filter_by(raised_by=raised_by_filter)
        
        if date_from:
            try:
                date_from_dt = datetime.fromisoformat(date_from)
                query = query.filter(Dispute.created_at >= date_from_dt)
            except ValueError:
                return error_response("Invalid date_from format (use ISO format)", 400)
        
        if date_to:
            try:
                date_to_dt = datetime.fromisoformat(date_to) + timedelta(days=1)
                query = query.filter(Dispute.created_at < date_to_dt)
            except ValueError:
                return error_response("Invalid date_to format (use ISO format)", 400)
        
        # Get total count
        total = query.count()
        
        # Fetch disputes
        disputes = query.order_by(Dispute.created_at.desc()).limit(limit).offset(offset).all()
        
        # Format response
        disputes_data = []
        for dispute in disputes:
            disputes_data.append({
                'id': dispute.id,
                'transaction_id': dispute.transaction_id,
                'upi_txn_id': dispute.transaction.upi_txn_id,
                'state': dispute.state.value,
                'raised_by': dispute.raised_by,
                'reason_code': dispute.reason_code,
                'resolution': dispute.resolution.value if dispute.resolution else None,
                'retry_count': dispute.retry_count,
                'created_at': dispute.created_at.isoformat(),
                'updated_at': dispute.updated_at.isoformat(),
            })
        
        return success_response({
            'disputes': disputes_data,
            'total': total,
            'limit': limit,
            'offset': offset,
        })
    
    except Exception as e:
        logger.error(f"Error listing disputes: {str(e)}")
        return error_response(f"Error listing disputes: {str(e)}", 500)


@disputes_bp.route('/<int:dispute_id>', methods=['GET'])
@require_api_key
@require_role('MERCHANT', 'ADMIN')
def get_dispute(dispute_id):
    """
    Get full details of a dispute including verification checks and refunds.
    
    Response: 200 OK
    {
        "success": true,
        "data": {
            "id": 1,
            "upi_txn_id": "UPI123456",
            "state": "VERIFYING",
            "raised_by": "CUSTOMER",
            "reason_code": "TRANSACTION_NOT_RECEIVED",
            "resolution": null,
            "verification_checks": [
                {
                    "id": 1,
                    "attempt_no": 1,
                    "decision": "INCONCLUSIVE",
                    "confidence_score": 0.65,
                    "checked_at": "2026-02-27T10:30:00Z"
                }
            ],
            "refunds": [
                {
                    "id": 1,
                    "refund_id": "REF-00000001",
                    "status": "SUCCESS",
                    "initiated_at": "2026-02-27T10:35:00Z",
                    "completed_at": "2026-02-27T10:36:00Z"
                }
            ]
        }
    }
    """
    try:
        dispute = db.session.query(Dispute).filter_by(id=dispute_id).first()
        if not dispute:
            return error_response(f"Dispute {dispute_id} not found", 404)
        
        # Get verification checks
        verifications = db.session.query(VerificationCheck).filter_by(
            dispute_id=dispute_id
        ).order_by(VerificationCheck.attempt_no).all()
        
        verification_data = []
        for v in verifications:
            verification_data.append({
                'id': v.id,
                'attempt_no': v.attempt_no,
                'decision': v.decision,
                'confidence_score': v.confidence_score,
                'checked_at': v.checked_at.isoformat(),
                'error': v.error,
            })
        
        # Get refunds
        refunds_data = []
        for r in dispute.refunds:
            refunds_data.append({
                'id': r.id,
                'refund_id': r.refund_id,
                'status': r.status.value,
                'method': r.method.value,
                'initiated_at': r.initiated_at.isoformat(),
                'completed_at': r.completed_at.isoformat() if r.completed_at else None,
                'bank_refund_ref': r.bank_refund_ref,
            })
        
        return success_response({
            'id': dispute.id,
            'transaction_id': dispute.transaction_id,
            'upi_txn_id': dispute.transaction.upi_txn_id,
            'state': dispute.state.value,
            'raised_by': dispute.raised_by,
            'reason_code': dispute.reason_code,
            'resolution': dispute.resolution.value if dispute.resolution else None,
            'retry_count': dispute.retry_count,
            'notes': dispute.notes,
            'sla_deadline_at': dispute.sla_deadline_at.isoformat() if dispute.sla_deadline_at else None,
            'created_at': dispute.created_at.isoformat(),
            'updated_at': dispute.updated_at.isoformat(),
            'verification_checks': verification_data,
            'refunds': refunds_data,
        })
    
    except Exception as e:
        logger.error(f"Error getting dispute {dispute_id}: {str(e)}")
        return error_response(f"Error getting dispute: {str(e)}", 500)


@disputes_bp.route('/<int:dispute_id>/recheck', methods=['POST'])
@require_api_key
@require_role('MERCHANT', 'ADMIN')
def recheck_dispute(dispute_id):
    """
    Force immediate re-run of verification for a dispute.
    
    Response: 200 OK
    {
        "success": true,
        "data": {
            "dispute_id": 1,
            "verification_check_id": 5,
            "decision": "APPROVED",
            "confidence_score": 0.95,
            "message": "Verification completed"
        }
    }
    """
    try:
        dispute = db.session.query(Dispute).filter_by(id=dispute_id).first()
        if not dispute:
            return error_response(f"Dispute {dispute_id} not found", 404)
        
        logger.info(f"Forcing verification recheck for dispute {dispute_id}")
        
        # Run verification
        verifier = VerificationService()
        try:
            verification_check = verifier.verify_dispute(dispute_id)
        except VerificationServiceError as e:
            return error_response(f"Verification failed: {str(e)}", 500)
        
        # Reload dispute to get updated state
        db.session.refresh(dispute)
        
        return success_response({
            'dispute_id': dispute.id,
            'verification_check_id': verification_check.id,
            'decision': verification_check.decision,
            'confidence_score': verification_check.confidence_score,
            'state': dispute.state.value,
            'resolution': dispute.resolution.value if dispute.resolution else None,
            'message': 'Verification completed',
        })
    
    except Exception as e:
        logger.error(f"Error rechecking dispute {dispute_id}: {str(e)}")
        return error_response(f"Error rechecking dispute: {str(e)}", 500)


@disputes_bp.route('/<int:dispute_id>/note', methods=['POST'])
@require_api_key
@require_role('MERCHANT', 'ADMIN')
def add_note(dispute_id):
    """
    Add a note to a dispute.
    
    Request Body:
    {
        "note": "Customer called and confirmed the issue"
    }
    
    Response: 200 OK
    {
        "success": true,
        "data": {
            "dispute_id": 1,
            "notes": "Previous notes\n---\nCustomer called..."
        }
    }
    """
    try:
        dispute = db.session.query(Dispute).filter_by(id=dispute_id).first()
        if not dispute:
            return error_response(f"Dispute {dispute_id} not found", 404)
        
        data = request.get_json() or {}
        note = data.get('note', '').strip()
        
        if not note:
            return error_response("note is required", 400)
        
        # Append note with timestamp
        timestamp = datetime.utcnow().isoformat()
        new_note = f"[{timestamp}] {note}"
        
        if dispute.notes:
            dispute.notes += f"\n---\n{new_note}"
        else:
            dispute.notes = new_note
        
        db.session.commit()
        logger.info(f"Added note to dispute {dispute_id}")
        
        return success_response({
            'dispute_id': dispute.id,
            'notes': dispute.notes,
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding note to dispute {dispute_id}: {str(e)}")
        return error_response(f"Error adding note: {str(e)}", 500)


@disputes_bp.route('/<int:dispute_id>/resolve', methods=['POST'])
@require_api_key
@require_role('ADMIN')
def resolve_dispute(dispute_id):
    """
    Manually resolve a dispute (ADMIN only).
    
    Request Body:
    {
        "resolution": "REFUND|TRANSACTION_SUCCESS|NO_DEBIT_FOUND|CUSTOMER_DISPUTE",
        "note": "Optional resolution notes"
    }
    
    Response: 200 OK
    {
        "success": true,
        "data": {
            "dispute_id": 1,
            "state": "RESOLVED",
            "resolution": "REFUND"
        }
    }
    """
    try:
        dispute = db.session.query(Dispute).filter_by(id=dispute_id).first()
        if not dispute:
            return error_response(f"Dispute {dispute_id} not found", 404)
        
        data = request.get_json() or {}
        resolution = data.get('resolution', '').strip().upper()
        note = data.get('note', '').strip() or None
        
        if not resolution or resolution not in [
            'REFUND',
            'TRANSACTION_SUCCESS',
            'NO_DEBIT_FOUND',
            'CUSTOMER_DISPUTE',
        ]:
            return error_response("Invalid resolution code", 400)
        
        # Update dispute
        dispute.state = DisputeState.RESOLVED
        dispute.resolution = DisputeResolution[resolution]
        
        if note:
            timestamp = datetime.utcnow().isoformat()
            admin_note = f"[ADMIN RESOLUTION {timestamp}] {note}"
            dispute.notes = admin_note if not dispute.notes else f"{dispute.notes}\n---\n{admin_note}"
        
        db.session.commit()
        logger.info(
            f"Dispute {dispute_id} manually resolved as {resolution} by {g.client_name}"
        )
        
        return success_response({
            'dispute_id': dispute.id,
            'state': dispute.state.value,
            'resolution': dispute.resolution.value,
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error resolving dispute {dispute_id}: {str(e)}")
        return error_response(f"Error resolving dispute: {str(e)}", 500)


@disputes_bp.route('/<int:dispute_id>/refund', methods=['POST'])
@require_api_key
@require_role('ADMIN')
@require_idempotency()
def trigger_refund(dispute_id):
    """
    Manually trigger refund for a dispute (ADMIN only, idempotent).
    
    Request Body:
    {}
    
    Response: 200 OK or 201 Created
    {
        "success": true,
        "data": {
            "dispute_id": 1,
            "refund_id": "REF-00000001",
            "status": "SUCCESS",
            "completed_at": "2026-02-27T10:36:00Z"
        }
    }
    """
    try:
        dispute = db.session.query(Dispute).filter_by(id=dispute_id).first()
        if not dispute:
            return error_response(f"Dispute {dispute_id} not found", 404)
        
        # Check if refund already exists
        existing_refund = dispute.refunds[0] if dispute.refunds else None
        if existing_refund:
            logger.info(f"Refund already exists for dispute {dispute_id}")
            return success_response({
                'dispute_id': dispute.id,
                'refund_id': existing_refund.refund_id,
                'status': existing_refund.status.value,
                'completed_at': existing_refund.completed_at.isoformat() if existing_refund.completed_at else None,
                'message': 'Refund already processed',
            })
        
        logger.info(f"Triggering refund for dispute {dispute_id} (admin initiated)")
        
        # Process refund
        refunder = RefundService()
        try:
            refund = refunder.process_refund(dispute)
        except RefundServiceError as e:
            return error_response(f"Refund processing failed: {str(e)}", 500)
        
        return created_response({
            'dispute_id': dispute.id,
            'refund_id': refund.refund_id,
            'status': refund.status.value,
            'initiated_at': refund.initiated_at.isoformat(),
            'completed_at': refund.completed_at.isoformat() if refund.completed_at else None,
        })
    
    except Exception as e:
        logger.error(f"Error triggering refund for dispute {dispute_id}: {str(e)}")
        return error_response(f"Error triggering refund: {str(e)}", 500)
