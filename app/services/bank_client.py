"""
Bank Client Service

Communicates with the Mock Bank API to retrieve transaction status.
Handles retries and error scenarios.
"""

import requests
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Configuration
BANK_API_URL = "http://localhost:5001"
TIMEOUT_SECONDS = 5
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1


class BankStatus(Enum):
    """Normalized bank transaction statuses"""
    DEBIT_SUCCESS = "DEBIT_SUCCESS"
    DEBIT_FAILED = "DEBIT_FAILED"
    PENDING = "PENDING"
    NOT_FOUND = "NOT_FOUND"


class BankClientError(Exception):
    """Exception raised for bank client errors"""
    pass


class BankResponse:
    """Normalized bank transaction response"""
    
    def __init__(
        self,
        upi_txn_id: str,
        status: BankStatus,
        bank_rrn: Optional[str] = None,
        amount: Optional[float] = None,
        failure_reason: Optional[str] = None,
        raw_response: Optional[Dict] = None,
    ):
        self.upi_txn_id = upi_txn_id
        self.status = status
        self.bank_rrn = bank_rrn
        self.amount = amount
        self.failure_reason = failure_reason
        self.raw_response = raw_response or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'upi_txn_id': self.upi_txn_id,
            'status': self.status.value,
            'bank_rrn': self.bank_rrn,
            'amount': self.amount,
            'failure_reason': self.failure_reason,
            'timestamp': self.timestamp.isoformat(),
        }


class BankClient:
    """Client for communicating with Mock Bank API"""
    
    def __init__(
        self,
        base_url: str = BANK_API_URL,
        timeout: int = TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Initialize Bank Client.
        
        Args:
            base_url: Base URL of bank API (default: http://localhost:5001)
            timeout: Request timeout in seconds (default: 5)
            max_retries: Maximum number of retries (default: 3)
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
    
    def get_transaction_status(
        self,
        upi_txn_id: str,
        scenario: Optional[str] = None,
    ) -> BankResponse:
        """
        Get transaction status from the bank.
        
        Args:
            upi_txn_id: UPI transaction ID
            scenario: Optional scenario for testing ('success', 'failed', 'pending', 'notfound')
        
        Returns:
            BankResponse with normalized status
        
        Raises:
            BankClientError: If request fails after retries
        """
        url = f"{self.base_url}/bank/txn/{upi_txn_id}"
        
        params = {}
        if scenario:
            params['scenario'] = scenario
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Fetching bank status for {upi_txn_id} "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                
                response = requests.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )
                
                # Check HTTP status
                if response.status_code == 200:
                    return self._parse_response(upi_txn_id, response.json())
                elif response.status_code == 404:
                    logger.warning(f"Transaction not found: {upi_txn_id}")
                    return BankResponse(
                        upi_txn_id=upi_txn_id,
                        status=BankStatus.NOT_FOUND,
                        raw_response={'error': 'Transaction not found'},
                    )
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"Bank API error: {error_msg}")
                    last_error = BankClientError(error_msg)
                    
                    # Retry on server errors
                    if response.status_code >= 500 and attempt < self.max_retries - 1:
                        import time
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    
                    raise last_error
            
            except requests.Timeout as e:
                logger.warning(f"Bank API timeout (attempt {attempt + 1}): {str(e)}")
                last_error = BankClientError(f"Request timeout: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                
                raise last_error
            
            except requests.ConnectionError as e:
                logger.error(f"Bank API connection error (attempt {attempt + 1}): {str(e)}")
                last_error = BankClientError(f"Connection error: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                
                raise last_error
            
            except Exception as e:
                logger.error(f"Unexpected error fetching bank status: {str(e)}")
                raise BankClientError(f"Unexpected error: {str(e)}")
        
        # All retries exhausted
        if last_error:
            raise last_error
        
        raise BankClientError("Failed to get transaction status after all retries")
    
    def _parse_response(self, upi_txn_id: str, data: Dict[str, Any]) -> BankResponse:
        """
        Parse and normalize bank API response.
        
        Args:
            upi_txn_id: UPI transaction ID
            data: Response JSON data
        
        Returns:
            Normalized BankResponse
        """
        try:
            # Map bank response status to normalized status
            raw_status = data.get('status', 'UNKNOWN')
            
            status_mapping = {
                'DEBIT_SUCCESS': BankStatus.DEBIT_SUCCESS,
                'DEBIT_FAILED': BankStatus.DEBIT_FAILED,
                'PENDING': BankStatus.PENDING,
                'NOT_FOUND': BankStatus.NOT_FOUND,
            }
            
            status = status_mapping.get(raw_status, BankStatus.NOT_FOUND)
            
            return BankResponse(
                upi_txn_id=upi_txn_id,
                status=status,
                bank_rrn=data.get('bank_rrn'),
                amount=data.get('amount'),
                failure_reason=data.get('failure_reason'),
                raw_response=data,
            )
        
        except Exception as e:
            logger.error(f"Error parsing bank response: {str(e)}")
            raise BankClientError(f"Failed to parse response: {str(e)}")
    
    def health_check(self) -> bool:
        """
        Check if bank API is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=self.timeout,
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Bank health check failed: {str(e)}")
            return False
