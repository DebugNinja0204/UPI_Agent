"""
Refund Service

Handles refund processing workflow:
1. Check if refund already exists (idempotency)
2. Create refund row in database
3. Call bank API to initiate refund
4. Poll refund status until completion
5. Update refund row and dispute state
6. Notify merchant of refund via reconciliation API
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Optional
from time import sleep
import uuid

from app.models.refund import Refund, RefundStatus, RefundMethod
from app.models.dispute import Dispute, DisputeState
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

# Configuration
BANK_API_URL = "http://localhost:5001"
MERCHANT_API_URL = "http://localhost:5002"
REQUEST_TIMEOUT = 5
POLL_INTERVAL_SECONDS = 2
MAX_POLL_ATTEMPTS = 30  # 60 seconds total
MAX_RETRIES = 3


class RefundServiceError(Exception):
    """Exception raised for refund service errors"""
    pass


class RefundResponse:
    """Refund response from API"""
    
    def __init__(
        self,
        refund_id: str,
        status: RefundStatus,
        bank_refund_ref: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ):
        self.refund_id = refund_id
        self.status = status
        self.bank_refund_ref = bank_refund_ref
        self.failure_reason = failure_reason
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'refund_id': self.refund_id,
            'status': self.status.value,
            'bank_refund_ref': self.bank_refund_ref,
            'failure_reason': self.failure_reason,
        }


class RefundService:
    """Service for handling refund workflow"""
    
    def __init__(
        self,
        bank_api_url: str = BANK_API_URL,
        merchant_api_url: str = MERCHANT_API_URL,
        timeout: int = REQUEST_TIMEOUT,
    ):
        """
        Initialize Refund Service.
        
        Args:
            bank_api_url: Base URL of bank API (default: http://localhost:5001)
            merchant_api_url: Base URL of merchant API (default: http://localhost:5002)
            timeout: Request timeout in seconds (default: 5)
        """
        self.bank_api_url = bank_api_url
        self.merchant_api_url = merchant_api_url
        self.timeout = timeout
    
    def process_refund(
        self,
        dispute: Dispute,
        refund_method: RefundMethod = RefundMethod.BANK_TRANSFER,
    ) -> Refund:
        """
        Process a refund for a dispute.
        
        Steps:
        1. Check if refund already exists (idempotency)
        2. Generate refund_id
        3. Create refund row with status INITIATED
        4. Call bank API to initiate refund
        5. Poll bank refund status until completion
        6. Update refund row
        7. Update dispute state
        8. Notify merchant via reconciliation API
        
        Args:
            dispute: Dispute to refund
            refund_method: Method of refund (default: INSTANT)
        
        Returns:
            Refund record
        
        Raises:
            RefundServiceError: If refund processing fails
        """
        from app import db
        
        logger.info(
            f"Processing refund for dispute {dispute.id} "
            f"(transaction: {dispute.transaction.upi_txn_id})"
        )
        
        try:
            # Step 1: Check if refund already exists (idempotency)
            existing_refund = db.session.query(Refund).filter_by(
                dispute_id=dispute.id
            ).first()
            
            if existing_refund:
                logger.info(
                    f"Refund already exists for dispute {dispute.id}: "
                    f"{existing_refund.refund_id}"
                )
                return existing_refund
            
            # Step 2: Generate refund ID
            refund_id = str(uuid.uuid4())
            
            # Step 3: Create refund row with status INITIATED
            logger.info(f"Creating refund record with ID: {refund_id}")
            refund = Refund(
                dispute_id=dispute.id,
                refund_id=refund_id,
                method=refund_method,
                status=RefundStatus.INITIATED,
                initiated_at=datetime.utcnow(),
            )
            db.session.add(refund)
            db.session.flush()  # Flush to get refund ID
            
            # Step 4: Call bank API to initiate refund
            logger.info("Initiating refund with bank...")
            try:
                self._initiate_bank_refund(
                    upi_txn_id=dispute.transaction.upi_txn_id,
                    amount=dispute.transaction.amount,
                    refund_id=refund_id,
                )
                logger.info(f"Bank refund initiated for {refund_id}")
            except RefundServiceError as e:
                logger.error(f"Failed to initiate bank refund: {str(e)}")
                refund.status = RefundStatus.FAILED
                refund.failure_reason = str(e)
                db.session.commit()
                raise
            
            # Step 5: Poll bank refund status
            logger.info(f"Polling refund status for {refund_id}...")
            bank_refund_ref, final_status = self._poll_refund_status(refund_id)
            
            # Step 6: Update refund row
            refund.status = final_status
            refund.bank_refund_ref = bank_refund_ref
            
            if final_status == RefundStatus.COMPLETED:
                refund.completed_at = datetime.utcnow()
                logger.info(f"Refund {refund_id} completed successfully")
            else:
                refund.failure_reason = f"Bank refund status: {final_status.value}"
                logger.error(f"Refund {refund_id} failed: {final_status.value}")
            
            # Step 7: Update dispute state
            if final_status == RefundStatus.COMPLETED:
                dispute.state = DisputeState.RESOLVED
                logger.info(f"Dispute {dispute.id} moved to RESOLVED")
            elif final_status == RefundStatus.IN_PROGRESS:
                dispute.state = DisputeState.REFUND_IN_PROGRESS
                logger.info(f"Dispute {dispute.id} moved to REFUND_IN_PROGRESS")
            else:
                # Keep in ACTION_REQUIRED if refund fails
                logger.warning(f"Refund failed, dispute {dispute.id} remains in ACTION_REQUIRED")
            
            # Step 8: Notify merchant via reconciliation API
            logger.info(f"Notifying merchant about refund {refund_id}...")
            try:
                self._notify_merchant_reconciliation(
                    dispute=dispute,
                    refund=refund,
                    refund_status=final_status,
                )
                logger.info(f"Merchant notified for dispute {dispute.id}")
            except RefundServiceError as e:
                logger.error(f"Failed to notify merchant: {str(e)}")
                # Don't fail the entire refund if merchant notification fails
                # Reconciliation can be manually triggered later
            
            # Commit all changes
            db.session.commit()
            logger.info(f"Refund processing completed for dispute {dispute.id}")
            
            return refund
        
        except RefundServiceError as e:
            db.session.rollback()
            logger.error(f"Refund processing failed: {str(e)}")
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error in refund processing: {str(e)}")
            raise RefundServiceError(f"Refund processing failed: {str(e)}")
    
    def _initiate_bank_refund(
        self,
        upi_txn_id: str,
        amount: float,
        refund_id: str,
    ) -> None:
        """
        Call bank API to initiate a refund.
        
        Args:
            upi_txn_id: UPI transaction ID
            amount: Refund amount
            refund_id: Refund ID (for idempotency)
        
        Raises:
            RefundServiceError: If API call fails
        """
        url = f"{self.bank_api_url}/bank/refund"
        
        payload = {
            'upi_txn_id': upi_txn_id,
            'amount': amount,
            'refund_id': refund_id,
        }
        
        logger.debug(f"Calling bank refund API: {url} with payload: {payload}")
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code not in (200, 201):
                error_msg = (
                    f"Bank refund API returned {response.status_code}: {response.text}"
                )
                logger.error(error_msg)
                raise RefundServiceError(error_msg)

            logger.info(
                f"Bank refund initiated successfully for {refund_id} "
                f"(status_code={response.status_code})"
            )
        
        except requests.Timeout as e:
            error_msg = f"Bank refund API timeout: {str(e)}"
            logger.error(error_msg)
            raise RefundServiceError(error_msg)
        
        except requests.ConnectionError as e:
            error_msg = f"Bank refund API connection error: {str(e)}"
            logger.error(error_msg)
            raise RefundServiceError(error_msg)
        
        except Exception as e:
            error_msg = f"Unexpected error calling bank refund API: {str(e)}"
            logger.error(error_msg)
            raise RefundServiceError(error_msg)
    
    def _poll_refund_status(
        self,
        refund_id: str,
        max_attempts: int = MAX_POLL_ATTEMPTS,
        poll_interval: int = POLL_INTERVAL_SECONDS,
    ) -> tuple:
        """
        Poll bank API for refund status until completion.
        
        Args:
            refund_id: Refund ID to poll
            max_attempts: Maximum number of poll attempts (default: 30)
            poll_interval: Interval between polls in seconds (default: 2)
        
        Returns:
            Tuple of (bank_refund_ref, final_status)
        
        Raises:
            RefundServiceError: If polling fails or times out
        """
        url = f"{self.bank_api_url}/bank/refund/{refund_id}"
        
        for attempt in range(max_attempts):
            try:
                logger.debug(f"Polling refund status (attempt {attempt + 1}/{max_attempts})")
                
                response = requests.get(
                    url,
                    timeout=self.timeout,
                )
                
                if response.status_code != 200:
                    logger.warning(
                        f"Refund status poll returned {response.status_code}: {response.text}"
                    )
                    sleep(poll_interval)
                    continue
                
                data = response.json()
                status = data.get('status', 'UNKNOWN')
                bank_refund_ref = data.get('refund_id')
                
                logger.debug(f"Refund status: {status}")
                
                # Check if refund is in terminal state
                if status in ['SUCCESS', 'FAILED']:
                    status_enum = (
                        RefundStatus.COMPLETED if status == 'SUCCESS'
                        else RefundStatus.FAILED
                    )
                    logger.info(
                        f"Refund reached terminal state: {status} "
                        f"(after {attempt + 1} polls)"
                    )
                    return bank_refund_ref, status_enum
                
                # Still processing - wait and retry
                if attempt < max_attempts - 1:
                    sleep(poll_interval)
            
            except Exception as e:
                logger.warning(f"Error polling refund status: {str(e)}")
                if attempt < max_attempts - 1:
                    sleep(poll_interval)
                    continue
                raise RefundServiceError(f"Failed to poll refund status: {str(e)}")
        
        # Timeout - refund still processing
        logger.warning(
            f"Refund polling timed out after {max_attempts} attempts. "
            "Returning PROCESSING status."
        )
        return None, RefundStatus.IN_PROGRESS
    
    def _notify_merchant_reconciliation(
        self,
        dispute: Dispute,
        refund: Refund,
        refund_status: RefundStatus,
    ) -> None:
        """
        Notify merchant of refund via reconciliation API.
        
        Args:
            dispute: Dispute being refunded
            refund: Refund record
            refund_status: Status of refund
        
        Raises:
            RefundServiceError: If notification fails
        """
        url = f"{self.merchant_api_url}/merchant/reconcile"
        
        # Map refund status to resolution
        resolution_mapping = {
            RefundStatus.COMPLETED: "REFUND_APPROVED",
            RefundStatus.IN_PROGRESS: "REFUND_IN_PROGRESS",
            RefundStatus.FAILED: "REFUND_FAILED",
            RefundStatus.INITIATED: "REFUND_INITIATED",
            RefundStatus.PENDING: "REFUND_PENDING",
        }
        
        resolution = resolution_mapping.get(refund_status, "UNKNOWN")
        
        payload = {
            'upi_txn_id': dispute.transaction.upi_txn_id,
            'resolution': resolution,
            'refund_id': refund.refund_id,
        }
        
        logger.debug(f"Calling merchant reconciliation API: {url} with payload: {payload}")
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            
            if response.status_code != 200:
                error_msg = (
                    f"Merchant reconciliation API returned {response.status_code}: "
                    f"{response.text}"
                )
                logger.error(error_msg)
                raise RefundServiceError(error_msg)
            
            logger.info(f"Merchant notified of refund {refund.refund_id}")
        
        except requests.Timeout as e:
            error_msg = f"Merchant reconciliation API timeout: {str(e)}"
            logger.error(error_msg)
            raise RefundServiceError(error_msg)
        
        except requests.ConnectionError as e:
            error_msg = f"Merchant reconciliation API connection error: {str(e)}"
            logger.error(error_msg)
            raise RefundServiceError(error_msg)
        
        except Exception as e:
            error_msg = f"Unexpected error calling merchant API: {str(e)}"
            logger.error(error_msg)
            raise RefundServiceError(error_msg)
