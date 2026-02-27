"""
Dispute Resolution Background Agent

Core logic for automated dispute processing.
Runs verification checks and refund polling cycles.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any
from sqlalchemy import and_
import traceback

from app import db
from app.models.dispute import Dispute, DisputeState
from app.models.refund import Refund, RefundStatus
from app.services import (
    VerificationService,
    RefundService,
    VerificationServiceError,
    RefundServiceError,
)

logger = logging.getLogger(__name__)


class DisputeAgent:
    """Background agent for automated dispute resolution processing."""
    
    def __init__(self):
        """Initialize the dispute agent."""
        self.verification_service = VerificationService()
        self.refund_service = RefundService()
        self.cycle_start_time = None
        self.cycle_results = {
            'disputes_processed': 0,
            'disputes_verified': 0,
            'disputes_refunded': 0,
            'disputes_failed': 0,
            'verification_decisions': {},
            'refund_statuses': {},
            'errors': [],
            'processed_disputes': [],
        }
    
    def run_cycle(self) -> Dict[str, Any]:
        """
        Run one complete agent processing cycle.
        
        Steps:
        1. Query disputes needing processing
        2. Verify OPEN/VERIFYING disputes
        3. Poll refunds for REFUND_IN_PROGRESS disputes
        4. Commit all changes
        5. Return cycle summary
        
        Returns:
            Dictionary with cycle results and statistics
        """
        self.cycle_start_time = datetime.utcnow()
        self.cycle_results = {
            'disputes_processed': 0,
            'disputes_verified': 0,
            'disputes_refunded': 0,
            'disputes_failed': 0,
            'verification_decisions': {},
            'refund_statuses': {},
            'errors': [],
            'processed_disputes': [],
        }
        
        logger.info("=" * 60)
        logger.info("Starting agent cycle at %s", self.cycle_start_time.isoformat())
        logger.info("=" * 60)
        
        try:
            # Get disputes needing verification
            verification_disputes = self._get_disputes_needing_verification()
            logger.info(f"Found {len(verification_disputes)} disputes needing verification")

            # Get disputes needing refund initiation
            refund_initiation_disputes = self._get_disputes_needing_refund_initiation()
            logger.info(f"Found {len(refund_initiation_disputes)} disputes needing refund initiation")
            
            # Get disputes needing refund polling
            refund_disputes = self._get_disputes_needing_refund_polling()
            logger.info(f"Found {len(refund_disputes)} disputes needing refund polling")
            
            # Process verifications
            for dispute in verification_disputes:
                self._process_verification(dispute)

            # Process refund initiation
            for dispute in refund_initiation_disputes:
                self._process_refund_initiation(dispute)
            
            # Process refund polling
            for dispute in refund_disputes:
                self._process_refund_polling(dispute)
            
            # Commit all changes
            try:
                db.session.commit()
                logger.info("All changes committed successfully")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to commit changes: {str(e)}")
                self.cycle_results['errors'].append({
                    'type': 'COMMIT_FAILED',
                    'message': str(e),
                    'traceback': traceback.format_exc(),
                })
            
            # Log cycle summary
            self._log_cycle_summary()
            
            return self.cycle_results
        
        except Exception as e:
            logger.error(f"Agent cycle failed: {str(e)}")
            logger.error(traceback.format_exc())
            self.cycle_results['errors'].append({
                'type': 'CYCLE_FAILED',
                'message': str(e),
                'traceback': traceback.format_exc(),
            })
            return self.cycle_results
    
    def _get_disputes_needing_verification(self) -> List[Dispute]:
        """
        Get disputes that need verification.
        
        Returns disputes in OPEN or VERIFYING state where:
        - next_check_at is None (first check) OR
        - next_check_at <= now
        
        Returns:
            List of Dispute objects
        """
        now = datetime.utcnow()
        
        disputes = db.session.query(Dispute).filter(
            Dispute.state.in_([DisputeState.OPEN, DisputeState.VERIFYING]),
            (Dispute.next_check_at.is_(None)) | (Dispute.next_check_at <= now)
        ).order_by(Dispute.created_at.asc()).all()
        
        return disputes
    
    def _get_disputes_needing_refund_initiation(self) -> List[Dispute]:
        """
        Get disputes that need refund initiation.

        Returns disputes in ACTION_REQUIRED state with no refunds yet.

        Returns:
            List of Dispute objects
        """
        disputes = db.session.query(Dispute).filter(
            Dispute.state == DisputeState.ACTION_REQUIRED,
            ~Dispute.refunds.any(),
        ).order_by(Dispute.updated_at.asc()).all()

        return disputes

    def _get_disputes_needing_refund_polling(self) -> List[Dispute]:
        """
        Get disputes that need refund status polling.
        
        Returns disputes in REFUND_IN_PROGRESS state that have
        associated refunds in IN_PROGRESS or INITIATED status.
        
        Returns:
            List of Dispute objects
        """
        disputes = db.session.query(Dispute).filter(
            Dispute.state == DisputeState.REFUND_IN_PROGRESS,
        ).order_by(Dispute.updated_at.asc()).all()
        
        # Filter to only those with pending refunds
        pending_disputes = []
        for dispute in disputes:
            if dispute.refunds:
                refund = dispute.refunds[0]
                if refund.status in [RefundStatus.INITIATED, RefundStatus.IN_PROGRESS]:
                    pending_disputes.append(dispute)
        
        return pending_disputes
    
    def _process_verification(self, dispute: Dispute) -> None:
        """
        Process verification for a single dispute.
        
        Args:
            dispute: Dispute to verify
        """
        dispute_id = dispute.id
        
        try:
            logger.info(f"Processing verification for dispute {dispute_id}")
            
            # Run verification
            verification_check = self.verification_service.verify_dispute(dispute_id)
            
            # Record result
            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_verified'] += 1
            
            decision = verification_check.decision
            confidence = verification_check.confidence_score
            
            # Track decisions
            if decision not in self.cycle_results['verification_decisions']:
                self.cycle_results['verification_decisions'][decision] = 0
            self.cycle_results['verification_decisions'][decision] += 1
            
            result = {
                'dispute_id': dispute_id,
                'action': 'VERIFIED',
                'decision': decision,
                'confidence_score': confidence,
                'attempt_no': verification_check.attempt_no,
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat(),
            }
            
            self.cycle_results['processed_disputes'].append(result)
            
            logger.info(
                f"Dispute {dispute_id} verified: "
                f"decision={decision}, confidence={confidence}, "
                f"new_state={dispute.state.value}"
            )
        
        except VerificationServiceError as e:
            logger.error(f"Verification failed for dispute {dispute_id}: {str(e)}")
            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_failed'] += 1
            
            self.cycle_results['processed_disputes'].append({
                'dispute_id': dispute_id,
                'action': 'VERIFY_FAILED',
                'error': str(e),
                'status': 'failed',
                'timestamp': datetime.utcnow().isoformat(),
            })
            
            self.cycle_results['errors'].append({
                'type': 'VERIFICATION_ERROR',
                'dispute_id': dispute_id,
                'message': str(e),
            })
        
        except Exception as e:
            logger.error(f"Unexpected error verifying dispute {dispute_id}: {str(e)}")
            logger.error(traceback.format_exc())
            
            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_failed'] += 1
            
            self.cycle_results['processed_disputes'].append({
                'dispute_id': dispute_id,
                'action': 'VERIFY_ERROR',
                'error': str(e),
                'status': 'failed',
                'timestamp': datetime.utcnow().isoformat(),
            })
            
            self.cycle_results['errors'].append({
                'type': 'UNEXPECTED_ERROR',
                'dispute_id': dispute_id,
                'message': str(e),
                'traceback': traceback.format_exc(),
            })

    def _process_refund_initiation(self, dispute: Dispute) -> None:
        """
        Initiate refund for a single ACTION_REQUIRED dispute.

        Args:
            dispute: Dispute to initiate refund for
        """
        dispute_id = dispute.id

        try:
            logger.info(f"Processing refund initiation for dispute {dispute_id}")

            refund = self.refund_service.process_refund(dispute)

            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_refunded'] += 1

            status_str = refund.status.value
            if status_str not in self.cycle_results['refund_statuses']:
                self.cycle_results['refund_statuses'][status_str] = 0
            self.cycle_results['refund_statuses'][status_str] += 1

            self.cycle_results['processed_disputes'].append({
                'dispute_id': dispute_id,
                'action': 'REFUND_INITIATED',
                'refund_id': refund.refund_id,
                'refund_status': refund.status.value,
                'dispute_state': dispute.state.value,
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat(),
            })

            logger.info(
                f"Refund initiation completed for dispute {dispute_id}: "
                f"refund_id={refund.refund_id}, status={refund.status.value}, state={dispute.state.value}"
            )

        except RefundServiceError as e:
            logger.error(f"Refund initiation failed for dispute {dispute_id}: {str(e)}")
            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_failed'] += 1

            self.cycle_results['processed_disputes'].append({
                'dispute_id': dispute_id,
                'action': 'REFUND_INIT_FAILED',
                'error': str(e),
                'status': 'failed',
                'timestamp': datetime.utcnow().isoformat(),
            })

            self.cycle_results['errors'].append({
                'type': 'REFUND_INIT_ERROR',
                'dispute_id': dispute_id,
                'message': str(e),
            })

        except Exception as e:
            logger.error(f"Unexpected error initiating refund for dispute {dispute_id}: {str(e)}")
            logger.error(traceback.format_exc())
            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_failed'] += 1

            self.cycle_results['processed_disputes'].append({
                'dispute_id': dispute_id,
                'action': 'REFUND_INIT_ERROR',
                'error': str(e),
                'status': 'failed',
                'timestamp': datetime.utcnow().isoformat(),
            })

            self.cycle_results['errors'].append({
                'type': 'UNEXPECTED_REFUND_INIT_ERROR',
                'dispute_id': dispute_id,
                'message': str(e),
                'traceback': traceback.format_exc(),
            })
    
    def _process_refund_polling(self, dispute: Dispute) -> None:
        """
        Process refund status polling for a single dispute.
        
        Args:
            dispute: Dispute to poll refund status for
        """
        dispute_id = dispute.id
        refund = dispute.refunds[0] if dispute.refunds else None
        
        if not refund:
            logger.warning(f"Dispute {dispute_id} in REFUND_IN_PROGRESS but has no refund")
            return
        
        try:
            logger.info(
                f"Polling refund status for dispute {dispute_id} "
                f"(refund_id={refund.refund_id})"
            )
            
            # Poll refund status
            bank_refund_ref, final_status = self.refund_service._poll_refund_status(
                refund.refund_id
            )
            
            # Update refund if status changed
            if final_status != refund.status:
                logger.info(
                    f"Refund {refund.refund_id} status changed: "
                    f"{refund.status.value} → {final_status.value}"
                )
                
                refund.status = final_status
                refund.bank_refund_ref = bank_refund_ref
                
                if final_status == RefundStatus.COMPLETED:
                    refund.completed_at = datetime.utcnow()
                    dispute.state = DisputeState.RESOLVED
                    logger.info(
                        f"Refund {refund.refund_id} completed successfully, "
                        f"dispute {dispute_id} marked RESOLVED"
                    )
                elif final_status == RefundStatus.FAILED:
                    dispute.state = DisputeState.ACTION_REQUIRED
                    logger.error(
                        f"Refund {refund.refund_id} failed, "
                        f"dispute {dispute_id} moved back to ACTION_REQUIRED"
                    )
            
            # Record result
            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_refunded'] += 1
            
            # Track refund statuses
            status_str = final_status.value
            if status_str not in self.cycle_results['refund_statuses']:
                self.cycle_results['refund_statuses'][status_str] = 0
            self.cycle_results['refund_statuses'][status_str] += 1
            
            result = {
                'dispute_id': dispute_id,
                'action': 'REFUND_POLLED',
                'refund_id': refund.refund_id,
                'refund_status': final_status.value,
                'dispute_state': dispute.state.value,
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat(),
            }
            
            self.cycle_results['processed_disputes'].append(result)
            
            logger.info(f"Refund polling completed for dispute {dispute_id}")
        
        except Exception as e:
            logger.error(f"Refund polling failed for dispute {dispute_id}: {str(e)}")
            logger.error(traceback.format_exc())
            
            self.cycle_results['disputes_processed'] += 1
            self.cycle_results['disputes_failed'] += 1
            
            self.cycle_results['processed_disputes'].append({
                'dispute_id': dispute_id,
                'action': 'REFUND_POLL_FAILED',
                'refund_id': refund.refund_id if refund else None,
                'error': str(e),
                'status': 'failed',
                'timestamp': datetime.utcnow().isoformat(),
            })
            
            self.cycle_results['errors'].append({
                'type': 'REFUND_POLLING_ERROR',
                'dispute_id': dispute_id,
                'refund_id': refund.refund_id if refund else None,
                'message': str(e),
            })
    
    def _log_cycle_summary(self) -> None:
        """Log a summary of the cycle results."""
        logger.info("=" * 60)
        logger.info("AGENT CYCLE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total disputes processed: {self.cycle_results['disputes_processed']}")
        logger.info(f"Disputes verified: {self.cycle_results['disputes_verified']}")
        logger.info(f"Disputes refunded: {self.cycle_results['disputes_refunded']}")
        logger.info(f"Disputes failed: {self.cycle_results['disputes_failed']}")
        
        if self.cycle_results['verification_decisions']:
            logger.info("Verification decisions:")
            for decision, count in self.cycle_results['verification_decisions'].items():
                logger.info(f"  - {decision}: {count}")
        
        if self.cycle_results['refund_statuses']:
            logger.info("Refund statuses:")
            for status, count in self.cycle_results['refund_statuses'].items():
                logger.info(f"  - {status}: {count}")
        
        if self.cycle_results['errors']:
            logger.warning(f"Errors: {len(self.cycle_results['errors'])}")
            for error in self.cycle_results['errors'][:5]:  # Show first 5
                logger.warning(f"  - {error['type']}: {error.get('message', 'N/A')}")
            
            if len(self.cycle_results['errors']) > 5:
                logger.warning(f"  ... and {len(self.cycle_results['errors']) - 5} more")
        
        cycle_duration = (datetime.utcnow() - self.cycle_start_time).total_seconds()
        logger.info(f"Cycle completed in {cycle_duration:.2f} seconds")
        logger.info("=" * 60)


# Global agent instance
_agent = None


def get_agent() -> DisputeAgent:
    """Get or create the global dispute agent instance."""
    global _agent
    if _agent is None:
        _agent = DisputeAgent()
    return _agent


def run_agent_cycle() -> Dict[str, Any]:
    """
    Run one complete agent processing cycle.
    
    This is the main entry point for agent execution.
    Can be called:
    - Via API: POST /internal/run-agent
    - Via CLI: python run_agent.py run
    - Via scheduler: APScheduler auto-runs every 2 minutes
    
    Returns:
        Dictionary with cycle results and statistics
    """
    agent = get_agent()
    return agent.run_cycle()
