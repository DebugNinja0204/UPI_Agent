"""
Internal API Endpoints

Routes for internal background processing and agent operations.
Roles: INTERNAL_AGENT only
"""

from flask import Blueprint, request, g
from datetime import datetime, timedelta
import logging

from app import db
from app.models.dispute import Dispute, DisputeState
from app.security import require_api_key, require_role
from app.services import (
    VerificationService,
    RefundService,
    VerificationServiceError,
    RefundServiceError,
)
from .response import success_response, error_response

logger = logging.getLogger(__name__)

internal_bp = Blueprint('internal', __name__, url_prefix='/internal')


@internal_bp.route('/run-agent', methods=['POST'])
@require_api_key
@require_role('INTERNAL_AGENT')
def run_agent():
    """
    Trigger background processing loop for dispute resolution agent.
    
    This endpoint processes disputes that are in VERIFYING state
    and have reached their next_check_at time.
    
    Response: 200 OK
    {
        "success": true,
        "data": {
            "disputes_processed": 5,
            "disputes_verified": 3,
            "disputes_refunded": 1,
            "disputes_failed": 1,
            "processed_disputes": [
                {
                    "dispute_id": 1,
                    "action": "VERIFIED",
                    "decision": "APPROVED",
                    "status": "success"
                },
                ...
            ]
        }
    }
    """
    try:
        logger.info(f"Agent run triggered by {g.client_name}")
        
        # Find disputes that need processing
        now = datetime.utcnow()
        
        # Disputes in VERIFYING state where next_check_at <= now
        disputes_to_verify = db.session.query(Dispute).filter(
            Dispute.state == DisputeState.VERIFYING,
            (Dispute.next_check_at.is_(None)) | (Dispute.next_check_at <= now)
        ).all()
        
        logger.info(f"Found {len(disputes_to_verify)} disputes to verify")
        
        # Disputes in ACTION_REQUIRED state that need refunds
        disputes_to_refund = db.session.query(Dispute).filter(
            Dispute.state == DisputeState.ACTION_REQUIRED,
            Dispute.resolution_id.isnot(None),  # Has resolution
            ~Dispute.refunds.any(),  # No refunds yet
        ).all()
        
        logger.info(f"Found {len(disputes_to_refund)} disputes to refund")
        
        # Process results
        results = {
            'disputes_processed': 0,
            'disputes_verified': 0,
            'disputes_refunded': 0,
            'disputes_failed': 0,
            'processed_disputes': [],
        }
        
        # Initialize services
        verifier = VerificationService()
        refunder = RefundService()
        
        # Process verifications
        for dispute in disputes_to_verify:
            try:
                logger.info(f"Verifying dispute {dispute.id}")
                verification_check = verifier.verify_dispute(dispute.id)
                
                results['disputes_processed'] += 1
                results['disputes_verified'] += 1
                
                results['processed_disputes'].append({
                    'dispute_id': dispute.id,
                    'action': 'VERIFIED',
                    'decision': verification_check.decision,
                    'confidence_score': verification_check.confidence_score,
                    'status': 'success',
                })
                
                logger.info(
                    f"Dispute {dispute.id} verified: "
                    f"decision={verification_check.decision}, "
                    f"confidence={verification_check.confidence_score}"
                )
            
            except VerificationServiceError as e:
                logger.error(f"Verification failed for dispute {dispute.id}: {str(e)}")
                
                results['disputes_processed'] += 1
                results['disputes_failed'] += 1
                
                results['processed_disputes'].append({
                    'dispute_id': dispute.id,
                    'action': 'VERIFY_FAILED',
                    'error': str(e),
                    'status': 'failed',
                })
            
            except Exception as e:
                logger.error(f"Unexpected error verifying dispute {dispute.id}: {str(e)}")
                
                results['disputes_processed'] += 1
                results['disputes_failed'] += 1
                
                results['processed_disputes'].append({
                    'dispute_id': dispute.id,
                    'action': 'VERIFY_FAILED',
                    'error': str(e),
                    'status': 'failed',
                })
        
        # Process refunds
        for dispute in disputes_to_refund:
            try:
                logger.info(f"Processing refund for dispute {dispute.id}")
                refund = refunder.process_refund(dispute)
                
                results['disputes_processed'] += 1
                results['disputes_refunded'] += 1
                
                results['processed_disputes'].append({
                    'dispute_id': dispute.id,
                    'action': 'REFUNDED',
                    'refund_id': refund.refund_id,
                    'refund_status': refund.status.value,
                    'status': 'success',
                })
                
                logger.info(
                    f"Dispute {dispute.id} refund processed: "
                    f"refund_id={refund.refund_id}, "
                    f"status={refund.status.value}"
                )
            
            except RefundServiceError as e:
                logger.error(f"Refund processing failed for dispute {dispute.id}: {str(e)}")
                
                results['disputes_processed'] += 1
                results['disputes_failed'] += 1
                
                results['processed_disputes'].append({
                    'dispute_id': dispute.id,
                    'action': 'REFUND_FAILED',
                    'error': str(e),
                    'status': 'failed',
                })
            
            except Exception as e:
                logger.error(f"Unexpected error refunding dispute {dispute.id}: {str(e)}")
                
                results['disputes_processed'] += 1
                results['disputes_failed'] += 1
                
                results['processed_disputes'].append({
                    'dispute_id': dispute.id,
                    'action': 'REFUND_FAILED',
                    'error': str(e),
                    'status': 'failed',
                })
        
        logger.info(
            f"Agent run completed: "
            f"verified={results['disputes_verified']}, "
            f"refunded={results['disputes_refunded']}, "
            f"failed={results['disputes_failed']}"
        )
        
        return success_response(results)
    
    except Exception as e:
        logger.error(f"Agent run failed: {str(e)}")
        return error_response(f"Agent run failed: {str(e)}", 500)
