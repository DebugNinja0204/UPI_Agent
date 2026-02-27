"""
Merchant Client Service

Communicates with the Mock Merchant API to retrieve order status.
Handles errors and retries.
"""

import requests
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Configuration
MERCHANT_API_URL = "http://localhost:5002"
TIMEOUT_SECONDS = 5
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1


class MerchantStatus(Enum):
    """Normalized merchant order statuses"""
    ORDER_SUCCESS = "ORDER_SUCCESS"
    ORDER_FAILED = "ORDER_FAILED"
    ORDER_PENDING = "ORDER_PENDING"
    NOT_FOUND = "NOT_FOUND"


class MerchantClientError(Exception):
    """Exception raised for merchant client errors"""
    pass


class MerchantResponse:
    """Normalized merchant order response"""
    
    def __init__(
        self,
        upi_txn_id: str,
        status: MerchantStatus,
        merchant_order_id: Optional[str] = None,
        merchant_txn_id: Optional[str] = None,
        amount: Optional[float] = None,
        failure_reason: Optional[str] = None,
        raw_response: Optional[Dict] = None,
    ):
        self.upi_txn_id = upi_txn_id
        self.status = status
        self.merchant_order_id = merchant_order_id
        self.merchant_txn_id = merchant_txn_id
        self.amount = amount
        self.failure_reason = failure_reason
        self.raw_response = raw_response or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'upi_txn_id': self.upi_txn_id,
            'status': self.status.value,
            'merchant_order_id': self.merchant_order_id,
            'merchant_txn_id': self.merchant_txn_id,
            'amount': self.amount,
            'failure_reason': self.failure_reason,
            'timestamp': self.timestamp.isoformat(),
        }


class MerchantClient:
    """Client for communicating with Mock Merchant API"""
    
    def __init__(
        self,
        base_url: str = MERCHANT_API_URL,
        timeout: int = TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Initialize Merchant Client.
        
        Args:
            base_url: Base URL of merchant API (default: http://localhost:5002)
            timeout: Request timeout in seconds (default: 5)
            max_retries: Maximum number of retries (default: 3)
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
    
    def get_order_status(
        self,
        upi_txn_id: str,
        scenario: Optional[str] = None,
    ) -> MerchantResponse:
        """
        Get order status from the merchant.
        
        Args:
            upi_txn_id: UPI transaction ID
            scenario: Optional scenario for testing ('success', 'failed', 'pending', 'notfound')
        
        Returns:
            MerchantResponse with normalized status
        
        Raises:
            MerchantClientError: If request fails after retries
        """
        url = f"{self.base_url}/merchant/status"
        
        params = {'upi_txn_id': upi_txn_id}
        if scenario:
            params['scenario'] = scenario
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Fetching merchant order status for {upi_txn_id} "
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
                    logger.warning(f"Merchant order not found: {upi_txn_id}")
                    return MerchantResponse(
                        upi_txn_id=upi_txn_id,
                        status=MerchantStatus.NOT_FOUND,
                        raw_response={'error': 'Order not found'},
                    )
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"Merchant API error: {error_msg}")
                    last_error = MerchantClientError(error_msg)
                    
                    # Retry on server errors
                    if response.status_code >= 500 and attempt < self.max_retries - 1:
                        import time
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    
                    raise last_error
            
            except requests.Timeout as e:
                logger.warning(f"Merchant API timeout (attempt {attempt + 1}): {str(e)}")
                last_error = MerchantClientError(f"Request timeout: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                
                raise last_error
            
            except requests.ConnectionError as e:
                logger.error(f"Merchant API connection error (attempt {attempt + 1}): {str(e)}")
                last_error = MerchantClientError(f"Connection error: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                
                raise last_error
            
            except Exception as e:
                logger.error(f"Unexpected error fetching merchant status: {str(e)}")
                raise MerchantClientError(f"Unexpected error: {str(e)}")
        
        # All retries exhausted
        if last_error:
            raise last_error
        
        raise MerchantClientError("Failed to get order status after all retries")
    
    def _parse_response(self, upi_txn_id: str, data: Dict[str, Any]) -> MerchantResponse:
        """
        Parse and normalize merchant API response.
        
        Args:
            upi_txn_id: UPI transaction ID
            data: Response JSON data
        
        Returns:
            Normalized MerchantResponse
        """
        try:
            # Map merchant response status to normalized status
            raw_status = data.get('status', 'UNKNOWN')
            
            status_mapping = {
                'ORDER_SUCCESS': MerchantStatus.ORDER_SUCCESS,
                'ORDER_FAILED': MerchantStatus.ORDER_FAILED,
                'ORDER_PENDING': MerchantStatus.ORDER_PENDING,
                'NOT_FOUND': MerchantStatus.NOT_FOUND,
            }
            
            status = status_mapping.get(raw_status, MerchantStatus.NOT_FOUND)
            
            return MerchantResponse(
                upi_txn_id=upi_txn_id,
                status=status,
                merchant_order_id=data.get('merchant_order_id'),
                merchant_txn_id=data.get('merchant_txn_id'),
                amount=data.get('amount'),
                failure_reason=data.get('failure_reason'),
                raw_response=data,
            )
        
        except Exception as e:
            logger.error(f"Error parsing merchant response: {str(e)}")
            raise MerchantClientError(f"Failed to parse response: {str(e)}")
    
    def health_check(self) -> bool:
        """
        Check if merchant API is healthy.
        
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
            logger.error(f"Merchant health check failed: {str(e)}")
            return False
