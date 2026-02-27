#!/usr/bin/env python
"""
Seed database with sample data for development and testing.
"""

import os
from datetime import datetime, timedelta
import uuid
from app import create_app, db
from app.models import (
    Transaction,
    Dispute,
    VerificationCheck,
    Refund,
    APIKey,
)
from app.models.transaction import TransactionStatus
from app.models.dispute import DisputeRaisedBy, DisputeReasonCode, DisputeState, DisputeResolution
from app.models.verification_check import VerificationDecision
from app.models.refund import RefundMethod, RefundStatus
from app.models.api_key import APIKeyRole


def seed_database():
    """Seed the database with sample data."""
    
    # Create app context
    app = create_app('development')
    
    with app.app_context():
        # Clear existing data
        print("Clearing existing data...")
        db.drop_all()
        db.create_all()
        print("Database tables created successfully!")
        
        # Seed API Keys (one per role)
        print("\nSeeding API Keys...")
        api_keys_data = [
            {
                'client_name': 'Demo Merchant',
                'api_key': 'merchant_key_demo_123456789',
                'role': APIKeyRole.MERCHANT,
                'allowed_ips': ['192.168.1.100', '10.0.0.1'],
            },
            {
                'client_name': 'Demo Bank',
                'api_key': 'bank_key_demo_987654321',
                'role': APIKeyRole.BANK,
                'allowed_ips': ['192.168.1.200', '10.0.0.2'],
            },
            {
                'client_name': 'Admin Account',
                'api_key': 'admin_key_admin_111222333',
                'role': APIKeyRole.ADMIN,
                'allowed_ips': None,
            },
            {
                'client_name': 'Internal Agent',
                'api_key': 'agent_key_internal_444555666',
                'role': APIKeyRole.INTERNAL_AGENT,
                'allowed_ips': ['localhost', '127.0.0.1'],
            },
            {
                'client_name': 'Test Merchant 1',
                'api_key': 'test_merchant_key_20260227',
                'role': APIKeyRole.MERCHANT,
                'allowed_ips': None,
            },
            {
                'client_name': 'Test Merchant 2',
                'api_key': 'test_merchant_eval_2026',
                'role': APIKeyRole.MERCHANT,
                'allowed_ips': None,
            },
            {
                'client_name': 'Test Bank 1',
                'api_key': 'test_bank_key_20260227',
                'role': APIKeyRole.BANK,
                'allowed_ips': None,
            },
            {
                'client_name': 'Test Admin',
                'api_key': 'test_admin_key_20260227',
                'role': APIKeyRole.ADMIN,
                'allowed_ips': None,
            },
        ]
        
        api_key_instances = []
        for key_data in api_keys_data:
            api_key = APIKey.create_key(
                client_name=key_data['client_name'],
                api_key=key_data['api_key'],
                role=key_data['role'],
                allowed_ips=key_data['allowed_ips']
            )
            api_key_instances.append(api_key)
            db.session.add(api_key)
            print(f"  [OK] Created {key_data['role'].value} API key for {key_data['client_name']}")
        
        db.session.commit()
        
        # Seed Transactions
        print("\nSeeding Transactions...")
        transactions = [
            Transaction(
                upi_txn_id='UPI' + str(uuid.uuid4())[:20],
                bank_rrn='RRN' + str(uuid.uuid4())[:15],
                payer_vpa='customer1@upi',
                payee_vpa='merchant1@upi',
                amount=500.00,
                currency='INR',
                merchant_order_id='ORD001',
                merchant_txn_id='MER001',
                current_status=TransactionStatus.SUCCESS,
                created_at=datetime.utcnow() - timedelta(days=5)
            ),
            Transaction(
                upi_txn_id='UPI' + str(uuid.uuid4())[:20],
                bank_rrn='RRN' + str(uuid.uuid4())[:15],
                payer_vpa='customer2@upi',
                payee_vpa='merchant2@upi',
                amount=1200.00,
                currency='INR',
                merchant_order_id='ORD002',
                merchant_txn_id='MER002',
                current_status=TransactionStatus.SUCCESS,
                created_at=datetime.utcnow() - timedelta(days=3)
            ),
            Transaction(
                upi_txn_id='UPI' + str(uuid.uuid4())[:20],
                bank_rrn=None,
                payer_vpa='customer3@upi',
                payee_vpa='merchant3@upi',
                amount=750.00,
                currency='INR',
                merchant_order_id='ORD003',
                merchant_txn_id='MER003',
                current_status=TransactionStatus.PENDING,
                created_at=datetime.utcnow() - timedelta(hours=2)
            ),
        ]
        
        for txn in transactions:
            db.session.add(txn)
            print(f"  [OK] Created transaction {txn.upi_txn_id}")
        
        db.session.commit()
        
        # Seed Disputes
        print("\nSeeding Disputes...")
        disputes = []
        sla_deadline = datetime.utcnow() + timedelta(hours=7*24)
        
        dispute1 = Dispute(
            upi_txn_id=transactions[0].upi_txn_id,
            raised_by=DisputeRaisedBy.CUSTOMER,
            reason_code=DisputeReasonCode.TRANSACTION_NOT_RECEIVED,
            state=DisputeState.VERIFYING,
            resolution=DisputeResolution.PENDING,
            sla_deadline_at=sla_deadline,
            next_check_at=datetime.utcnow() - timedelta(minutes=1),
            retry_count=0,
            notes='Customer claims transaction was not received in their account.',
            created_at=datetime.utcnow() - timedelta(days=4)
        )
        disputes.append(dispute1)
        db.session.add(dispute1)
        print(f"  [OK] Created dispute for transaction {transactions[0].upi_txn_id}")
        
        dispute2 = Dispute(
            upi_txn_id=transactions[1].upi_txn_id,
            raised_by=DisputeRaisedBy.MERCHANT,
            reason_code=DisputeReasonCode.DUPLICATE_TRANSACTION,
            state=DisputeState.OPEN,
            resolution=DisputeResolution.PENDING,
            sla_deadline_at=sla_deadline,
            retry_count=0,
            notes='Merchant reports duplicate debit. Transaction processed twice.',
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        disputes.append(dispute2)
        db.session.add(dispute2)
        print(f"  [OK] Created dispute for transaction {transactions[1].upi_txn_id}")
        
        db.session.commit()
        
        # Seed Verification Checks
        print("\nSeeding Verification Checks...")
        verification1 = VerificationCheck(
            dispute_id=dispute1.id,
            attempt_no=1,
            checked_at=datetime.utcnow() - timedelta(hours=2),
            bank_result={
                'status': 'received',
                'recipient_name': 'John Doe',
                'credit_amount': 500.00
            },
            merchant_result={
                'status': 'awaiting_confirmation',
                'order_status': 'pending'
            },
            decision=VerificationDecision.INCONCLUSIVE,
            confidence_score=0.65,
        )
        db.session.add(verification1)
        print(f"  [OK] Created verification check for dispute {dispute1.id}")
        
        verification2 = VerificationCheck(
            dispute_id=dispute2.id,
            attempt_no=1,
            checked_at=datetime.utcnow() - timedelta(hours=1),
            bank_result={
                'status': 'duplicate_confirmed',
                'debit_count': 2,
                'amounts': [1200.00, 1200.00]
            },
            merchant_result={
                'status': 'order_received_once',
                'order_count': 1
            },
            decision=VerificationDecision.APPROVED,
            confidence_score=0.95,
        )
        db.session.add(verification2)
        print(f"  [OK] Created verification check for dispute {dispute2.id}")
        
        db.session.commit()
        
        # Seed Refunds
        print("\nSeeding Refunds...")
        refund1 = Refund(
            dispute_id=dispute2.id,
            refund_id='REF' + str(uuid.uuid4())[:20],
            method=RefundMethod.DIRECT_DEPOSIT,
            status=RefundStatus.COMPLETED,
            initiated_at=datetime.utcnow() - timedelta(hours=1),
            completed_at=datetime.utcnow() - timedelta(minutes=30),
            bank_refund_ref='BREF001',
        )
        db.session.add(refund1)
        print(f"  [OK] Created refund for dispute {dispute2.id}")
        
        db.session.commit()
        
        print("\n" + "="*50)
        print("[OK] Database seeding completed successfully!")
        print("="*50)
        print(f"\nSeeded data summary:")
        print(f"  • API Keys: {len(api_key_instances)} (1 per role)")
        print(f"  • Transactions: {len(transactions)}")
        print(f"  • Disputes: {len(disputes)}")
        print(f"  • Verification Checks: 2")
        print(f"  • Refunds: 1")


if __name__ == '__main__':
    seed_database()
