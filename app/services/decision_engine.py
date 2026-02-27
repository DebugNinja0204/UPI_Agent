"""
Decision Engine Service

Takes bank and merchant statuses and determines dispute resolution decision
with confidence score based on pre-defined rules.
"""

from enum import Enum
from typing import NamedTuple
from .bank_client import BankStatus
from .merchant_client import MerchantStatus
import logging

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """Types of dispute resolution decisions"""
    REFUND = "REFUND"
    UPDATE_SUCCESS = "UPDATE_SUCCESS"
    NO_DEBIT_FOUND = "NO_DEBIT_FOUND"
    RETRY = "RETRY"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class Decision(NamedTuple):
    """Decision with confidence score"""
    decision: DecisionType
    confidence_score: float
    reasoning: str


class DecisionEngine:
    """Engine for making dispute resolution decisions"""
    
    def decide(
        self,
        bank_status: BankStatus,
        merchant_status: MerchantStatus,
        amount_match: bool = True,
    ) -> Decision:
        """
        Make a dispute resolution decision based on bank and merchant statuses.
        
        Decision Logic:
        - DEBIT_SUCCESS + ORDER_FAILED → REFUND (0.95)
        - DEBIT_SUCCESS + ORDER_SUCCESS → UPDATE_SUCCESS (0.99)
        - DEBIT_FAILED + ORDER_FAILED → NO_DEBIT_FOUND (0.97)
        - Any PENDING → RETRY (0.50)
        - Amount mismatch → MANUAL_REVIEW (0.30)
        - Merchant NOT_FOUND + DEBIT_SUCCESS → MANUAL_REVIEW (0.40)
        
        Args:
            bank_status: Status from bank API (BankStatus enum)
            merchant_status: Status from merchant API (MerchantStatus enum)
            amount_match: Whether amounts matched between bank and merchant (default: True)
        
        Returns:
            Decision with decision type and confidence score
        """
        logger.info(
            f"Making decision: bank={bank_status.value}, "
            f"merchant={merchant_status.value}, amount_match={amount_match}"
        )
        
        # Rule 1: Any PENDING status → RETRY with low confidence
        if bank_status == BankStatus.PENDING or merchant_status == MerchantStatus.ORDER_PENDING:
            reasoning = (
                f"Bank status is PENDING ({bank_status == BankStatus.PENDING}) or "
                f"Merchant order is PENDING ({merchant_status == MerchantStatus.ORDER_PENDING}). "
                "Waiting for more information."
            )
            return Decision(
                decision=DecisionType.RETRY,
                confidence_score=0.50,
                reasoning=reasoning,
            )
        
        # Rule 2: Amount mismatch → MANUAL_REVIEW
        if not amount_match:
            reasoning = (
                "Amount mismatch detected between bank debit and merchant order. "
                "Requires manual investigation."
            )
            return Decision(
                decision=DecisionType.MANUAL_REVIEW,
                confidence_score=0.30,
                reasoning=reasoning,
            )
        
        # Rule 3: DEBIT_SUCCESS + ORDER_FAILED → REFUND
        if (bank_status == BankStatus.DEBIT_SUCCESS and 
            merchant_status == MerchantStatus.ORDER_FAILED):
            reasoning = (
                "Bank confirms debit successful, but merchant order failed. "
                "Customer is overcharged - refund is warranted."
            )
            return Decision(
                decision=DecisionType.REFUND,
                confidence_score=0.95,
                reasoning=reasoning,
            )
        
        # Rule 4: DEBIT_SUCCESS + ORDER_SUCCESS → UPDATE_SUCCESS
        if (bank_status == BankStatus.DEBIT_SUCCESS and 
            merchant_status == MerchantStatus.ORDER_SUCCESS):
            reasoning = (
                "Bank confirms debit successful and merchant confirms order successful. "
                "Transaction completed normally - no action required."
            )
            return Decision(
                decision=DecisionType.UPDATE_SUCCESS,
                confidence_score=0.99,
                reasoning=reasoning,
            )
        
        # Rule 5: DEBIT_FAILED + ORDER_FAILED → NO_DEBIT_FOUND
        if (bank_status == BankStatus.DEBIT_FAILED and 
            merchant_status == MerchantStatus.ORDER_FAILED):
            reasoning = (
                "Bank confirms no debit was processed and merchant confirms order failed. "
                "Customer was not charged - dispute is invalid."
            )
            return Decision(
                decision=DecisionType.NO_DEBIT_FOUND,
                confidence_score=0.97,
                reasoning=reasoning,
            )
        
        # Rule 6: Merchant NOT_FOUND + DEBIT_SUCCESS → MANUAL_REVIEW
        if (bank_status == BankStatus.DEBIT_SUCCESS and 
            merchant_status == MerchantStatus.NOT_FOUND):
            reasoning = (
                "Bank confirms debit successful but merchant has no record of this transaction. "
                "Possible fraudulent merchant or system integration issue - manual review needed."
            )
            return Decision(
                decision=DecisionType.MANUAL_REVIEW,
                confidence_score=0.40,
                reasoning=reasoning,
            )
        
        # Rule 7: Other combinations with NOT_FOUND status
        if merchant_status == MerchantStatus.NOT_FOUND:
            reasoning = (
                "Merchant has no record of this transaction. "
                "Unable to verify merchant side - manual review required."
            )
            return Decision(
                decision=DecisionType.MANUAL_REVIEW,
                confidence_score=0.35,
                reasoning=reasoning,
            )
        
        if bank_status == BankStatus.NOT_FOUND:
            reasoning = (
                "Bank has no record of this transaction. "
                "Unable to verify bank side - manual review required."
            )
            return Decision(
                decision=DecisionType.MANUAL_REVIEW,
                confidence_score=0.40,
                reasoning=reasoning,
            )
        
        # Rule 8: Default → MANUAL_REVIEW (unknown combination)
        reasoning = (
            f"Unexpected combination of statuses: "
            f"bank={bank_status.value}, merchant={merchant_status.value}. "
            "Manual review required."
        )
        logger.warning(f"Unexpected status combination: {reasoning}")
        
        return Decision(
            decision=DecisionType.MANUAL_REVIEW,
            confidence_score=0.25,
            reasoning=reasoning,
        )
    
    def get_decision_documentation(self) -> str:
        """
        Get human-readable decision documentation.
        
        Returns:
            String documentation of all decision rules
        """
        return """
DISPUTE RESOLUTION DECISION ENGINE

Decision Rules (Priority Order):
1. Either party PENDING → RETRY with 50% confidence
   - Wait for system to settle before making decision
   
2. Amount mismatch between parties → MANUAL_REVIEW with 30% confidence
   - Discrepancies require human investigation
   
3. DEBIT_SUCCESS + ORDER_FAILED → REFUND with 95% confidence
   - Bank charged customer but merchant didn't fulfill order - refund warranted
   
4. DEBIT_SUCCESS + ORDER_SUCCESS → UPDATE_SUCCESS with 99% confidence
   - Both parties confirm transaction successful - no action needed
   
5. DEBIT_FAILED + ORDER_FAILED → NO_DEBIT_FOUND with 97% confidence
   - Neither party has records - no refund needed, dispute invalid
   
6. DEBIT_SUCCESS + MERCHANT_NOT_FOUND → MANUAL_REVIEW with 40% confidence
   - Bank processed but merchant has no record - possible fraud/integration issue
   
7. MERCHANT_NOT_FOUND (any bank status) → MANUAL_REVIEW with 35% confidence
   - Cannot verify merchant side - requires investigation
   
8. BANK_NOT_FOUND (any merchant status) → MANUAL_REVIEW with 40% confidence
   - Cannot verify bank side - requires investigation
   
9. Other combinations → MANUAL_REVIEW with 25% confidence
   - Unexpected state - escalate to human team

Confidence Scores Guide:
- 0.99: Very high confidence (both parties agree)
- 0.95: High confidence (one party failed)
- 0.97: High confidence (both parties failed)
- 0.50: Low confidence (system still processing)
- 0.40: Medium-low confidence (missing information)
- 0.30: Low confidence (conflicting data)
- 0.25: Very low confidence (unknown state)
"""
