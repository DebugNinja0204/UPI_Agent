"""
Dashboard UI (server-rendered).

Provides minimal Jinja2 pages for disputes and analytics.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, g, abort
from sqlalchemy import func

from app import db
from app.models.dispute import Dispute, DisputeState
from app.models.refund import Refund, RefundStatus
from app.models.verification_check import VerificationCheck


dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


def _enum_value(value):
    if hasattr(value, 'value'):
        return value.value
    return value


def _get_upi_txn_id(dispute):
    if hasattr(dispute, 'upi_txn_id') and dispute.upi_txn_id:
        return dispute.upi_txn_id
    transaction = getattr(dispute, 'transaction', None)
    if transaction and getattr(transaction, 'upi_txn_id', None):
        return transaction.upi_txn_id
    return 'unknown'


def _get_state_filter():
    state_filter = request.args.get('state', '').strip().upper()
    if not state_filter:
        return None
    try:
        return DisputeState[state_filter]
    except KeyError:
        return None


@dashboard_bp.route('', methods=['GET'])
def list_dashboard_disputes():
    state_filter = _get_state_filter()
    query = db.session.query(Dispute)
    if state_filter:
        query = query.filter(Dispute.state == state_filter)

    disputes = query.order_by(Dispute.created_at.desc()).all()

    dispute_rows = []
    for dispute in disputes:
        dispute_rows.append({
            'id': dispute.id,
            'upi_txn_id': _get_upi_txn_id(dispute),
            'state': _enum_value(dispute.state),
            'reason_code': _enum_value(dispute.reason_code),
            'raised_by': _enum_value(dispute.raised_by),
            'sla_deadline_at': dispute.sla_deadline_at,
            'retry_count': dispute.retry_count,
        })

    return render_template(
        'dashboard/list.html',
        disputes=dispute_rows,
        state_filter=_enum_value(state_filter) if state_filter else None,
        states=[state.value for state in DisputeState],
        correlation_id=getattr(g, 'correlation_id', 'unknown'),
        now=datetime.utcnow(),
    )


@dashboard_bp.route('/dispute/<int:dispute_id>', methods=['GET'])
def dispute_detail(dispute_id):
    dispute = db.session.query(Dispute).filter_by(id=dispute_id).first()
    if not dispute:
        abort(404)

    verifications = (
        db.session.query(VerificationCheck)
        .filter_by(dispute_id=dispute_id)
        .order_by(VerificationCheck.attempt_no.asc())
        .all()
    )

    refunds = list(dispute.refunds)
    latest_refund = refunds[-1] if refunds else None

    notes = []
    if dispute.notes:
        notes = [note.strip() for note in dispute.notes.split('\n---\n') if note.strip()]

    dispute_info = {
        'id': dispute.id,
        'upi_txn_id': _get_upi_txn_id(dispute),
        'state': _enum_value(dispute.state),
        'raised_by': _enum_value(dispute.raised_by),
        'reason_code': _enum_value(dispute.reason_code),
        'resolution': _enum_value(dispute.resolution) if dispute.resolution else None,
        'sla_deadline_at': dispute.sla_deadline_at,
        'retry_count': dispute.retry_count,
        'created_at': dispute.created_at,
        'updated_at': dispute.updated_at,
    }

    verification_rows = []
    for check in verifications:
        verification_rows.append({
            'id': check.id,
            'attempt_no': check.attempt_no,
            'checked_at': check.checked_at,
            'decision': _enum_value(check.decision),
            'confidence_score': check.confidence_score,
            'bank_result': check.bank_result,
            'merchant_result': check.merchant_result,
            'error': check.error,
        })

    refund_rows = []
    for refund in refunds:
        refund_rows.append({
            'id': refund.id,
            'refund_id': refund.refund_id,
            'status': _enum_value(refund.status),
            'method': _enum_value(refund.method),
            'initiated_at': refund.initiated_at,
            'completed_at': refund.completed_at,
            'bank_refund_ref': refund.bank_refund_ref,
            'failure_reason': refund.failure_reason,
        })

    latest_refund_row = refund_rows[-1] if refund_rows else None

    return render_template(
        'dashboard/detail.html',
        dispute=dispute_info,
        verifications=verification_rows,
        refunds=refund_rows,
        latest_refund=latest_refund_row,
        notes=notes,
        correlation_id=getattr(g, 'correlation_id', 'unknown'),
        now=datetime.utcnow(),
    )


def _build_analytics_summary():
    total_disputes = db.session.query(func.count(Dispute.id)).scalar() or 0

    state_counts = db.session.query(
        Dispute.state,
        func.count(Dispute.id).label('count')
    ).group_by(Dispute.state).all()

    disputes_by_state = {
        _enum_value(state): count
        for state, count in state_counts
    }

    resolved_disputes = db.session.query(Dispute).filter(
        Dispute.state == DisputeState.RESOLVED
    ).all()

    if resolved_disputes:
        total_hours = 0
        for dispute in resolved_disputes:
            if dispute.updated_at:
                duration = dispute.updated_at - dispute.created_at
                total_hours += duration.total_seconds() / 3600
        avg_resolution_time = total_hours / len(resolved_disputes)
    else:
        avg_resolution_time = None

    avg_retry_count = db.session.query(
        func.avg(Dispute.retry_count)
    ).scalar() or 0

    successful_refunds = db.session.query(func.count(Refund.id)).filter(
        Refund.status == RefundStatus.COMPLETED
    ).scalar() or 0

    total_refunds = db.session.query(func.count(Refund.id)).scalar() or 0
    refund_success_rate = (successful_refunds / total_refunds * 100) if total_refunds > 0 else None

    reason_counts = db.session.query(
        Dispute.reason_code,
        func.count(Dispute.id).label('count')
    ).group_by(Dispute.reason_code).order_by(
        func.count(Dispute.id).desc()
    ).all()

    most_common_reason = _enum_value(reason_counts[0][0]) if reason_counts else None

    return {
        'total_disputes': total_disputes,
        'disputes_by_state': disputes_by_state,
        'average_resolution_time_hours': round(avg_resolution_time, 2) if avg_resolution_time else None,
        'refund_success_rate': round(refund_success_rate, 2) if refund_success_rate else None,
        'most_common_reason_code': most_common_reason,
        'average_retry_count': round(float(avg_retry_count), 2) if avg_retry_count else 0,
    }


@dashboard_bp.route('/analytics', methods=['GET'])
def dashboard_analytics():
    summary = _build_analytics_summary()

    return render_template(
        'dashboard/analytics.html',
        summary=summary,
        correlation_id=getattr(g, 'correlation_id', 'unknown'),
        now=datetime.utcnow(),
    )


@dashboard_bp.route('/raise', methods=['GET'])
def raise_dispute_page():
    return render_template(
        'dashboard/create_dispute.html',
        correlation_id=getattr(g, 'correlation_id', 'unknown'),
        now=datetime.utcnow(),
    )
