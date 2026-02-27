"""
Verification Service

Orchestrates the dispute verification workflow:
1. Fetch bank transaction status
2. Fetch merchant order status
3. Run decision engine
4. Create verification_checks record
5. Update dispute state based on decision
6. Schedule retry if needed
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.dispute import Dispute, DisputeState, DisputeResolution
from app.models.verification_check import VerificationCheck
from app.models.transaction import Transaction
from .bank_client import BankClient, BankClientError
from .merchant_client import MerchantClient, MerchantClientError
from .decision_engine import DecisionEngine, DecisionType
from .gemini_decision_engine import get_gemini_engine

logger = logging.getLogger(__name__)

# Exponential backoff retry schedule (in minutes)
RETRY_SCHEDULE = {
    1: 5,      # 1st retry: +5 minutes
    2: 15,     # 2nd retry: +15 minutes
    3: 60,     # 3rd retry: +1 hour
    4: 360,    # 4th retry: +6 hours
}
MAX_RETRIES = 5  # After 5 retries, escalate to ACTION_REQUIRED


class VerificationServiceError(Exception):
    """Exception raised for verification service errors"""
    pass


class VerificationService:
    """Service for orchestrating dispute verification workflow"""
    
    def __init__(
        self,
        bank_client: Optional[BankClient] = None,
        merchant_client: Optional[MerchantClient] = None,
        decision_engine: Optional[DecisionEngine] = None,
    ):
        """
        Initialize Verification Service.
        
        Args:
            bank_client: Bank client instance (creates default if None)
            merchant_client: Merchant client instance (creates default if None)
            decision_engine: Decision engine instance (creates default if None)
        """
        self.bank_client = bank_client or BankClient()
        self.merchant_client = merchant_client or MerchantClient()
        self.decision_engine = decision_engine or DecisionEngine()
        self.gemini_engine = get_gemini_engine()
    
    def verify_dispute(self, dispute_id: int) -> VerificationCheck:
        """
        Run full verification workflow for a dispute.
        
        Steps:
        1. Load dispute from database
        2. Load related transaction
        3. Fetch bank transaction status
        4. Fetch merchant order status
        5. Check if amounts match
        6. Run decision engine
        7. Create verification_checks record
        8. Update dispute state based on decision
        9. Schedule retry if decision is RETRY
        
        Args:
            dispute_id: ID of dispute to verify
        
        Returns:
            VerificationCheck record created
        
        Raises:
            VerificationServiceError: If verification fails
        """
        from app import db
        
        logger.info(f"Starting verification workflow for dispute {dispute_id}")
        
        try:
            # Load dispute and transaction
            dispute = db.session.query(Dispute).filter_by(id=dispute_id).first()
            if not dispute:
                raise VerificationServiceError(f"Dispute {dispute_id} not found")
            
            transaction = db.session.query(Transaction).filter_by(
                upi_txn_id=dispute.upi_txn_id
            ).first()
            if not transaction:
                raise VerificationServiceError(
                    f"Transaction for dispute {dispute_id} not found"
                )
            
            logger.info(
                f"Verifying dispute {dispute_id} for transaction {transaction.upi_txn_id}"
            )
            
            # Fetch bank status
            logger.info("Fetching bank transaction status...")
            try:
                bank_response = self.bank_client.get_transaction_status(
                    transaction.upi_txn_id
                )
                bank_status = bank_response.status
                bank_rrn = bank_response.bank_rrn
                bank_amount = bank_response.amount
                logger.info(f"Bank status: {bank_status.value}, RRN: {bank_rrn}")
            except BankClientError as e:
                logger.error(f"Failed to fetch bank status: {str(e)}")
                bank_status = None
                bank_rrn = None
                bank_amount = None
            
            # Fetch merchant status
            logger.info("Fetching merchant order status...")
            try:
                merchant_response = self.merchant_client.get_order_status(
                    transaction.upi_txn_id
                )
                merchant_status = merchant_response.status
                merchant_order_id = merchant_response.merchant_order_id
                merchant_amount = merchant_response.amount
                logger.info(f"Merchant status: {merchant_status.value}")
            except MerchantClientError as e:
                logger.error(f"Failed to fetch merchant status: {str(e)}")
                merchant_status = None
                merchant_order_id = None
                merchant_amount = None
            
            # If unable to fetch either status, schedule retry
            if not bank_status or not merchant_status:
                logger.warning(
                    "Unable to fetch both statuses - scheduling retry"
                )
                return self._schedule_retry(
                    dispute, dispute.retry_count + 1,
                    "Unable to fetch bank or merchant status"
                )
            
            # Check amount match
            amount_match = self._check_amount_match(
                transaction.amount, bank_amount, merchant_amount
            )
            if not amount_match:
                logger.warning(
                    f"Amount mismatch: transaction={transaction.amount}, "
                    f"bank={bank_amount}, merchant={merchant_amount}"
                )
            
            # Run decision engine
            logger.info("Running decision engine...")
            decision = self.decision_engine.decide(
                bank_status=bank_status,
                merchant_status=merchant_status,
                amount_match=amount_match,
            )

            if self._should_use_gemini(decision):
                decision = self._enhance_with_gemini(
                    dispute=dispute,
                    transaction=transaction,
                    bank_status=bank_status,
                    merchant_status=merchant_status,
                    amount_match=amount_match,
                    base_decision=decision,
                )

            logger.info(
                f"Decision: {decision.decision.value} "
                f"(confidence: {decision.confidence_score})"
            )
            
            # Create verification_checks record
            verification_check = self._create_verification_check(
                dispute=dispute,
                attempt_no=dispute.retry_count + 1,
                bank_result=bank_response.to_dict() if bank_status else None,
                merchant_result=merchant_response.to_dict() if merchant_status else None,
                decision=decision.decision,
                confidence_score=decision.confidence_score,
                reasoning=decision.reasoning,
            )
            db.session.add(verification_check)
            
            # Update dispute state based on decision
            logger.info(f"Updating dispute state based on decision...")
            self._update_dispute_state(dispute, decision, verification_check)
            
            # Handle RETRY decision
            if decision.decision == DecisionType.RETRY:
                self._schedule_retry(
                    dispute,
                    dispute.retry_count + 1,
                    f"Decision engine returned RETRY: {decision.reasoning}"
                )
            
            # Commit changes
            db.session.commit()
            logger.info(f"Verification workflow completed for dispute {dispute_id}")
            
            return verification_check
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Verification workflow failed: {str(e)}")
            raise VerificationServiceError(f"Verification failed: {str(e)}")

    def _should_use_gemini(self, base_decision) -> bool:
        """
        Decide whether Gemini should be invoked for decision enhancement.

        Gemini is used only for uncertain/escalation-prone outcomes and never
        replaces the deterministic engine as the default path.
        """
        if not getattr(self.gemini_engine, 'enabled', False):
            return False

        if not current_app.config.get('GEMINI_DECISION_ENABLED', True):
            return False

        threshold = current_app.config.get('GEMINI_CONFIDENCE_THRESHOLD', 0.8)
        escalation_decisions = current_app.config.get(
            'GEMINI_ESCALATION_DECISIONS',
            {'RETRY', 'MANUAL_REVIEW'}
        )

        if isinstance(escalation_decisions, str):
            escalation_decisions = {
                item.strip().upper() for item in escalation_decisions.split(',') if item.strip()
            }

        if base_decision.confidence_score < threshold:
            return True

        if base_decision.decision.value in escalation_decisions:
            return True

        return False

    def _enhance_with_gemini(
        self,
        dispute: Dispute,
        transaction: Transaction,
        bank_status,
        merchant_status,
        amount_match: bool,
        base_decision,
    ):
        """Enhance rule-based decision with Gemini, with safe fallback."""
        try:
            reason_code = dispute.reason_code.value if hasattr(dispute.reason_code, 'value') else str(dispute.reason_code)
            notes = dispute.notes or ''

            enhanced_decision = self.gemini_engine.enhance_decision(
                base_decision=base_decision,
                bank_status=bank_status,
                merchant_status=merchant_status,
                dispute_reason=reason_code,
                dispute_notes=notes,
                amount=transaction.amount,
                amount_match=amount_match,
            )

            if enhanced_decision != base_decision:
                logger.info(
                    f"Gemini enhanced decision for dispute {dispute.id}: "
                    f"{base_decision.decision.value}({base_decision.confidence_score:.2f}) -> "
                    f"{enhanced_decision.decision.value}({enhanced_decision.confidence_score:.2f})"
                )

            return enhanced_decision

        except Exception as e:
            logger.warning(
                f"Gemini enhancement failed for dispute {dispute.id}; "
                f"using base decision. Error: {str(e)}"
            )
            return base_decision
    
    def _check_amount_match(
        self,
        transaction_amount: float,
        bank_amount: Optional[float],
        merchant_amount: Optional[float],
    ) -> bool:
        """
        Check if amounts match across transaction, bank, and merchant.
        
        Args:
            transaction_amount: Amount from transaction record
            bank_amount: Amount from bank response
            merchant_amount: Amount from merchant response
        
        Returns:
            True if all amounts match (within 0.01 tolerance), False otherwise
        """
        tolerance = 0.01
        
        if bank_amount is None or merchant_amount is None:
            return True  # Can't determine mismatch without all amounts
        
        bank_match = abs(transaction_amount - bank_amount) < tolerance
        merchant_match = abs(transaction_amount - merchant_amount) < tolerance
        
        return bank_match and merchant_match
    
    def _create_verification_check(
        self,
        dispute: Dispute,
        attempt_no: int,
        bank_result: Optional[dict],
        merchant_result: Optional[dict],
        decision: DecisionType,
        confidence_score: float,
        reasoning: str,
        error_message: Optional[str] = None,
    ) -> VerificationCheck:
        """
        Create a verification_checks record.
        
        Args:
            dispute: Dispute being verified
            attempt_no: Attempt number
            bank_result: Bank API response (as dict)
            merchant_result: Merchant API response (as dict)
            decision: Decision type from engine
            confidence_score: Confidence score (0.0-1.0)
            reasoning: Human-readable reasoning
            error_message: Optional error message if verification failed
        
        Returns:
            VerificationCheck record (not yet committed)
        """
        # Map decision to verification decision
        decision_mapping = {
            DecisionType.REFUND: "APPROVED",
            DecisionType.UPDATE_SUCCESS: "APPROVED",
            DecisionType.NO_DEBIT_FOUND: "REJECTED",
            DecisionType.RETRY: "INCONCLUSIVE",
            DecisionType.MANUAL_REVIEW: "INCONCLUSIVE",
        }
        
        verification_decision = decision_mapping.get(decision, "INCONCLUSIVE")
        
        return VerificationCheck(
            dispute_id=dispute.id,
            attempt_no=attempt_no,
            checked_at=datetime.utcnow(),
            bank_result=bank_result,
            merchant_result=merchant_result,
            decision=verification_decision,
            confidence_score=confidence_score,
            error=error_message,
        )
    
    def _update_dispute_state(
        self,
        dispute: Dispute,
        decision: any,
        verification_check: VerificationCheck,
    ) -> None:
        """
        Update dispute state based on verification decision.
        
        Args:
            dispute: Dispute to update
            decision: Decision from decision engine
            verification_check: VerificationCheck record created
        """
        # Update dispute with verification result
        dispute.retry_count += 1
        
        if decision.decision == DecisionType.REFUND:
            dispute.state = DisputeState.ACTION_REQUIRED
            dispute.resolution = DisputeResolution.ACCEPTED
            logger.info(
                f"Dispute {dispute.id} marked for REFUND "
                f"(confidence: {decision.confidence_score})"
            )
        
        elif decision.decision == DecisionType.UPDATE_SUCCESS:
            dispute.state = DisputeState.RESOLVED
            dispute.resolution = DisputeResolution.REJECTED
            logger.info(
                f"Dispute {dispute.id} RESOLVED as successful transaction "
                f"(confidence: {decision.confidence_score})"
            )
        
        elif decision.decision == DecisionType.NO_DEBIT_FOUND:
            dispute.state = DisputeState.RESOLVED
            dispute.resolution = DisputeResolution.REJECTED
            logger.info(
                f"Dispute {dispute.id} RESOLVED - no debit found "
                f"(confidence: {decision.confidence_score})"
            )
        
        elif decision.decision == DecisionType.RETRY:
            # State stays VERIFYING, next_check_at will be set by _schedule_retry
            logger.info(
                f"Dispute {dispute.id} scheduled for retry "
                f"(attempt: {dispute.retry_count})"
            )
        
        elif decision.decision == DecisionType.MANUAL_REVIEW:
            dispute.state = DisputeState.ACTION_REQUIRED
            logger.info(
                f"Dispute {dispute.id} escalated to ACTION_REQUIRED "
                f"(confidence: {decision.confidence_score})"
            )
    
    def _schedule_retry(
        self,
        dispute: Dispute,
        next_attempt: int,
        reason: str,
    ) -> VerificationCheck:
        """
        Schedule a retry for the dispute.
        
        Uses exponential backoff:
        - Attempt 1: +5 min
        - Attempt 2: +15 min
        - Attempt 3: +60 min
        - Attempt 4: +360 min (6 hours)
        - Attempt 5+: escalate to ACTION_REQUIRED
        
        Args:
            dispute: Dispute to schedule retry for
            next_attempt: Next attempt number
            reason: Reason for scheduling retry
        
        Returns:
            VerificationCheck record for this retry scheduling
        """
        from app import db
        
        if next_attempt > MAX_RETRIES:
            # Escalate to manual review
            dispute.state = DisputeState.ACTION_REQUIRED
            logger.warning(
                f"Dispute {dispute.id} escalated to ACTION_REQUIRED "
                f"after {MAX_RETRIES} retries"
            )
        else:
            # Schedule next retry
            delay_minutes = RETRY_SCHEDULE.get(next_attempt, 360)
            dispute.next_check_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
            dispute.retry_count = next_attempt - 1
            logger.info(
                f"Dispute {dispute.id} scheduled for retry in {delay_minutes} minutes "
                f"(attempt {next_attempt})"
            )
        
        # Create verification_checks record
        verification_check = VerificationCheck(
            dispute_id=dispute.id,
            attempt_no=next_attempt,
            checked_at=datetime.utcnow(),
            bank_result=None,
            merchant_result=None,
            decision="INCONCLUSIVE",
            confidence_score=0.0,
            error=reason,
        )
        
        db.session.add(verification_check)
        return verification_check
