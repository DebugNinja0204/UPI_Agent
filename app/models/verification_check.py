from datetime import datetime
from enum import Enum
from app import db


class VerificationDecision(Enum):
    """Enum for verification check decision."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    PENDING = "PENDING"


class VerificationCheck(db.Model):
    """Verification check model for dispute verification."""
    
    __tablename__ = 'verification_checks'
    
    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey('disputes.id'), nullable=False, index=True)
    attempt_no = db.Column(db.Integer, nullable=False)
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    bank_result = db.Column(db.JSON, nullable=True)
    merchant_result = db.Column(db.JSON, nullable=True)
    decision = db.Column(
        db.Enum(VerificationDecision),
        default=VerificationDecision.PENDING,
        nullable=False
    )
    confidence_score = db.Column(db.Float, nullable=True)  # 0.0 to 1.0
    error = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<VerificationCheck Dispute:{self.dispute_id} - Attempt:{self.attempt_no}>'
    
    def to_dict(self):
        """Convert to dictionary representation."""
        return {
            'id': self.id,
            'dispute_id': self.dispute_id,
            'attempt_no': self.attempt_no,
            'checked_at': self.checked_at.isoformat(),
            'bank_result': self.bank_result,
            'merchant_result': self.merchant_result,
            'decision': self.decision.value,
            'confidence_score': self.confidence_score,
            'error': self.error,
        }
