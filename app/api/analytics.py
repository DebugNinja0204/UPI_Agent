"""
Analytics API Endpoints

Routes for analytics and reporting.
Roles: ADMIN only
"""

from flask import Blueprint
from datetime import datetime, timedelta
from sqlalchemy import func
import logging

from app import db
from app.models.dispute import Dispute, DisputeState, DisputeResolution
from app.models.refund import Refund, RefundStatus
from app.models.verification_check import VerificationCheck
from app.security import require_api_key, require_role
from .response import success_response, error_response

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')


@analytics_bp.route('/summary', methods=['GET'])
@require_api_key
@require_role('ADMIN')
def get_summary():
    """
    Get high-level analytics summary of dispute resolution.
    
    Returns:
    - Average resolution time (in hours)
    - Percentage of disputes auto-resolved (without manual intervention)
    - Refund success rate (% of approved refunds that succeeded)
    - Most common reason code
    - Distribution of disputes by state
    - Distribution of disputes by resolution
    
    Response: 200 OK
    {
        "success": true,
        "data": {
            "total_disputes": 42,
            "disputes_by_state": {
                "OPEN": 5,
                "VERIFYING": 3,
                "ACTION_REQUIRED": 8,
                "REFUND_IN_PROGRESS": 2,
                "RESOLVED": 24
            },
            "disputes_by_resolution": {
                "REFUND": 18,
                "TRANSACTION_SUCCESS": 4,
                "NO_DEBIT_FOUND": 2,
                "CUSTOMER_DISPUTE": 0
            },
            "average_resolution_time_hours": 2.5,
            "auto_resolved_percentage": 45,
            "refund_success_rate": 85,
            "most_common_reason_code": "TRANSACTION_NOT_RECEIVED",
            "reason_code_distribution": {
                "TRANSACTION_NOT_RECEIVED": 25,
                "DUPLICATE_TRANSACTION": 10,
                "WRONG_AMOUNT": 5,
                "OTHER": 2
            },
            "average_retry_count": 1.2,
            "verification_decision_distribution": {
                "APPROVED": 20,
                "REJECTED": 8,
                "INCONCLUSIVE": 14
            },
            "confidence_score_stats": {
                "average": 0.73,
                "min": 0.25,
                "max": 0.99
            },
            "timestamp": "2026-02-27T10:30:00Z"
        }
    }
    """
    try:
        # Get total disputes
        total_disputes = db.session.query(func.count(Dispute.id)).scalar() or 0
        
        if total_disputes == 0:
            return success_response({
                'total_disputes': 0,
                'disputes_by_state': {},
                'disputes_by_resolution': {},
                'average_resolution_time_hours': None,
                'auto_resolved_percentage': None,
                'refund_success_rate': None,
                'most_common_reason_code': None,
                'reason_code_distribution': {},
                'average_retry_count': 0,
                'verification_decision_distribution': {},
                'confidence_score_stats': {},
                'timestamp': datetime.utcnow().isoformat(),
            })
        
        # Disputes by state
        state_counts = db.session.query(
            Dispute.state,
            func.count(Dispute.id).label('count')
        ).group_by(Dispute.state).all()
        
        disputes_by_state = {
            state.value: count
            for state, count in state_counts
        }
        
        # Disputes by resolution
        resolution_counts = db.session.query(
            Dispute.resolution,
            func.count(Dispute.id).label('count')
        ).filter(
            Dispute.resolution.isnot(None)
        ).group_by(Dispute.resolution).all()
        
        disputes_by_resolution = {
            resolution.value: count
            for resolution, count in resolution_counts
        }
        
        # Average resolution time
        resolved_disputes = db.session.query(Dispute).filter(
            Dispute.state == DisputeState.RESOLVED
        ).all()
        
        if resolved_disputes:
            total_hours = 0
            for dispute in resolved_disputes:
                if dispute.updated_at:
                    duration = dispute.updated_at - dispute.created_at
                    hours = duration.total_seconds() / 3600
                    total_hours += hours
            
            avg_resolution_time = total_hours / len(resolved_disputes)
        else:
            avg_resolution_time = None
        
        # Auto-resolved percentage (resolved without ACTION_REQUIRED)
        auto_resolved = db.session.query(func.count(Dispute.id)).filter(
            Dispute.state == DisputeState.RESOLVED,
            Dispute.retry_count <= 1,  # Simple heuristic: resolved on first attempt
        ).scalar() or 0
        
        auto_resolved_percentage = (auto_resolved / total_disputes * 100) if total_disputes > 0 else None
        
        # Refund success rate
        successful_refunds = db.session.query(func.count(Refund.id)).filter(
            Refund.status == RefundStatus.COMPLETED
        ).scalar() or 0
        
        total_refunds = db.session.query(func.count(Refund.id)).scalar() or 0
        
        refund_success_rate = (successful_refunds / total_refunds * 100) if total_refunds > 0 else None
        
        # Most common reason code
        reason_counts = db.session.query(
            Dispute.reason_code,
            func.count(Dispute.id).label('count')
        ).group_by(Dispute.reason_code).order_by(
            func.count(Dispute.id).desc()
        ).all()
        
        reason_code_distribution = {
            reason_code: count
            for reason_code, count in reason_counts
        }
        
        most_common_reason = reason_counts[0][0] if reason_counts else None
        
        # Average retry count
        avg_retry_count = db.session.query(
            func.avg(Dispute.retry_count)
        ).scalar() or 0
        
        # Verification decision distribution
        decision_counts = db.session.query(
            VerificationCheck.decision,
            func.count(VerificationCheck.id).label('count')
        ).group_by(VerificationCheck.decision).all()
        
        verification_decision_distribution = {
            decision: count
            for decision, count in decision_counts
        }
        
        # Confidence score statistics
        confidence_stats = db.session.query(
            func.avg(VerificationCheck.confidence_score).label('avg'),
            func.min(VerificationCheck.confidence_score).label('min'),
            func.max(VerificationCheck.confidence_score).label('max'),
        ).first()
        
        confidence_score_stats = {
            'average': round(float(confidence_stats.avg), 2) if confidence_stats.avg else 0,
            'min': round(float(confidence_stats.min), 2) if confidence_stats.min else 0,
            'max': round(float(confidence_stats.max), 2) if confidence_stats.max else 0,
        }
        
        return success_response({
            'total_disputes': total_disputes,
            'disputes_by_state': disputes_by_state,
            'disputes_by_resolution': disputes_by_resolution,
            'average_resolution_time_hours': round(avg_resolution_time, 2) if avg_resolution_time else None,
            'auto_resolved_percentage': round(auto_resolved_percentage, 2) if auto_resolved_percentage else None,
            'refund_success_rate': round(refund_success_rate, 2) if refund_success_rate else None,
            'most_common_reason_code': most_common_reason,
            'reason_code_distribution': reason_code_distribution,
            'average_retry_count': round(avg_retry_count, 2) if avg_retry_count else 0,
            'verification_decision_distribution': verification_decision_distribution,
            'confidence_score_stats': confidence_score_stats,
            'timestamp': datetime.utcnow().isoformat(),
        })
    
    except Exception as e:
        logger.error(f"Error getting analytics summary: {str(e)}")
        return error_response(f"Error getting analytics: {str(e)}", 500)
