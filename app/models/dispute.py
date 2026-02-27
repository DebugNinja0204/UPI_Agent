from datetime import datetime
from enum import Enum
from app import db


class DisputeRaisedBy(Enum):
    """Enum for who raised the dispute."""
    CUSTOMER = "CUSTOMER"
    MERCHANT = "MERCHANT"
    BANK = "BANK"


class DisputeReasonCode(Enum):
    """Enum for dispute reason codes."""
    TRANSACTION_NOT_RECEIVED = "TRANSACTION_NOT_RECEIVED"
    TRANSACTION_NOT_DEBITED = "TRANSACTION_NOT_DEBITED"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    INCORRECT_AMOUNT = "INCORRECT_AMOUNT"
    UNAUTHORISED_TRANSACTION = "UNAUTHORISED_TRANSACTION"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    CHARGEBACK = "CHARGEBACK"
    OTHER = "OTHER"


class DisputeState(Enum):
    """Enum for dispute state."""
    OPEN = "OPEN"
    VERIFYING = "VERIFYING"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    REFUND_IN_PROGRESS = "REFUND_IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class DisputeResolution(Enum):
    """Enum for dispute resolution."""
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PARTIAL_REFUND = "PARTIAL_REFUND"
    PENDING = "PENDING"


class Dispute(db.Model):
    """Dispute model for transaction disputes."""
    
    __tablename__ = 'disputes'
    
    id = db.Column(db.Integer, primary_key=True)
    upi_txn_id = db.Column(
        db.String(255),
        db.ForeignKey('transactions.upi_txn_id'),
        nullable=False,
        index=True
    )
    raised_by = db.Column(db.Enum(DisputeRaisedBy), nullable=False)
    reason_code = db.Column(db.Enum(DisputeReasonCode), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    state = db.Column(
        db.Enum(DisputeState),
        default=DisputeState.OPEN,
        nullable=False,
        index=True
    )
    resolution = db.Column(
        db.Enum(DisputeResolution),
        default=DisputeResolution.PENDING,
        nullable=True
    )
    sla_deadline_at = db.Column(db.DateTime, nullable=True, index=True)
    next_check_at = db.Column(db.DateTime, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    verification_checks = db.relationship(
        'VerificationCheck',
        backref='dispute',
        lazy=True,
        cascade='all, delete-orphan'
    )
    refunds = db.relationship('Refund', backref='dispute', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Dispute {self.id} - {self.upi_txn_id}>'
    
    def to_dict(self):
        """Convert to dictionary representation."""
        return {
            'id': self.id,
            'upi_txn_id': self.upi_txn_id,
            'raised_by': self.raised_by.value,
            'reason_code': self.reason_code.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'state': self.state.value,
            'resolution': self.resolution.value if self.resolution else None,
            'sla_deadline_at': self.sla_deadline_at.isoformat() if self.sla_deadline_at else None,
            'next_check_at': self.next_check_at.isoformat() if self.next_check_at else None,
            'retry_count': self.retry_count,
            'notes': self.notes,
        }
