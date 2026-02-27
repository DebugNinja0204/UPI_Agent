from datetime import datetime
from enum import Enum
from app import db


class TransactionStatus(Enum):
    """Enum for transaction status."""
    INITIATED = "INITIATED"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class Transaction(db.Model):
    """Transaction model for UPI transactions."""
    
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    upi_txn_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    bank_rrn = db.Column(db.String(255), nullable=True, index=True)
    payer_vpa = db.Column(db.String(255), nullable=False)
    payee_vpa = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='INR', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    merchant_order_id = db.Column(db.String(255), nullable=True, index=True)
    merchant_txn_id = db.Column(db.String(255), nullable=True, index=True)
    customer_complaint_id = db.Column(db.String(255), nullable=True, index=True)
    current_status = db.Column(
        db.Enum(TransactionStatus),
        default=TransactionStatus.INITIATED,
        nullable=False,
        index=True
    )
    
    # Relationships
    disputes = db.relationship('Dispute', backref='transaction', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Transaction {self.upi_txn_id}>'
    
    def to_dict(self):
        """Convert to dictionary representation."""
        return {
            'id': self.id,
            'upi_txn_id': self.upi_txn_id,
            'bank_rrn': self.bank_rrn,
            'payer_vpa': self.payer_vpa,
            'payee_vpa': self.payee_vpa,
            'amount': self.amount,
            'currency': self.currency,
            'created_at': self.created_at.isoformat(),
            'merchant_order_id': self.merchant_order_id,
            'merchant_txn_id': self.merchant_txn_id,
            'customer_complaint_id': self.customer_complaint_id,
            'current_status': self.current_status.value,
        }
