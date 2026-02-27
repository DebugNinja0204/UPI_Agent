from datetime import datetime
from enum import Enum
from app import db


class RefundMethod(Enum):
    """Enum for refund method."""
    DIRECT_DEPOSIT = "DIRECT_DEPOSIT"
    ACCOUNT_CREDIT = "ACCOUNT_CREDIT"
    BANK_TRANSFER = "BANK_TRANSFER"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class RefundStatus(Enum):
    """Enum for refund status."""
    PENDING = "PENDING"
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Refund(db.Model):
    """Refund model for dispute refunds."""
    
    __tablename__ = 'refunds'
    
    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey('disputes.id'), nullable=False, index=True)
    refund_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    method = db.Column(db.Enum(RefundMethod), nullable=False)
    status = db.Column(
        db.Enum(RefundStatus),
        default=RefundStatus.PENDING,
        nullable=False,
        index=True
    )
    initiated_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    bank_refund_ref = db.Column(db.String(255), nullable=True, index=True)
    failure_reason = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<Refund {self.refund_id}>'
    
    def to_dict(self):
        """Convert to dictionary representation."""
        return {
            'id': self.id,
            'dispute_id': self.dispute_id,
            'refund_id': self.refund_id,
            'method': self.method.value,
            'status': self.status.value,
            'initiated_at': self.initiated_at.isoformat() if self.initiated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'bank_refund_ref': self.bank_refund_ref,
            'failure_reason': self.failure_reason,
        }
