"""
Gemini AI Enhanced Decision Engine

Enhances dispute resolution decisions using Google's Gemini API for intelligent analysis.
Combines rule-based logic with AI reasoning for better accuracy and context awareness.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from enum import Enum
from .bank_client import BankStatus
from .merchant_client import MerchantStatus
from .decision_engine import DecisionType, Decision

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("Gemini API not available. Install with: pip install google-generativeai")


class GeminiDecisionEngine:
    """Enhanced decision engine using Gemini AI for intelligent analysis"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini API client.
        
        Args:
            api_key: Google Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        self.model_name = "gemini-1.5-flash"
        self.enabled = False
        
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini not installed. Falling back to rule-based engine.")
            return
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY environment variable not set.")
            return
        
        try:
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model_name)
            self.enabled = True
            logger.info("✓ Gemini AI decision engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {str(e)}")
    
    def analyze_with_gemini(
        self,
        bank_status: BankStatus,
        merchant_status: MerchantStatus,
        dispute_reason: str,
        dispute_notes: str,
        amount: float,
        amount_match: bool,
    ) -> Dict[str, Any]:
        """
        Use Gemini to analyze dispute and provide intelligent reasoning.
        
        Args:
            bank_status: Status from bank API
            merchant_status: Status from merchant API
            dispute_reason: Why the dispute was raised
            dispute_notes: Additional notes from customer/merchant
            amount: Transaction amount
            amount_match: Whether amounts matched
        
        Returns:
            Dict with decision recommendation and confidence
        """
        if not self.enabled:
            return None
        
        try:
            prompt = self._build_analysis_prompt(
                bank_status=bank_status,
                merchant_status=merchant_status,
                dispute_reason=dispute_reason,
                dispute_notes=dispute_notes,
                amount=amount,
                amount_match=amount_match,
            )
            
            logger.info("Sending dispute analysis to Gemini...")
            response = self.client.generate_content(prompt)
            
            analysis = self._parse_gemini_response(response.text)
            logger.info(f"Gemini analysis received: {analysis}")
            
            return analysis
        
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            return None
    
    def _build_analysis_prompt(
        self,
        bank_status: BankStatus,
        merchant_status: MerchantStatus,
        dispute_reason: str,
        dispute_notes: str,
        amount: float,
        amount_match: bool,
    ) -> str:
        """Build the analysis prompt for Gemini."""
        return f"""
You are an expert UPI dispute resolution analyst. Analyze this dispute and provide a recommendation.

DISPUTE DETAILS:
- Reason: {dispute_reason}
- Amount: ₹{amount:.2f}
- Notes: {dispute_notes if dispute_notes else 'None'}

SYSTEM STATUS:
- Bank Status: {bank_status.value}
- Merchant Status: {merchant_status.value}
- Amount Match: {amount_match}

DECISION OPTIONS:
1. REFUND - Approve refund to customer
2. UPDATE_SUCCESS - Transaction is valid, no action needed
3. NO_DEBIT_FOUND - No debit occurred, dispute is invalid
4. MANUAL_REVIEW - Escalate to human team
5. RETRY - Wait and check again later

TASK:
Based on the dispute details and system statuses, provide:
1. Your recommended decision (must be one of the 5 options above)
2. Confidence score (0.0 to 1.0)
3. Brief reasoning (max 100 words)

Format your response as JSON:
{{
    "decision": "REFUND|UPDATE_SUCCESS|NO_DEBIT_FOUND|MANUAL_REVIEW|RETRY",
    "confidence_score": 0.95,
    "reasoning": "Your detailed reasoning here"
}}

Respond with ONLY the JSON object, no other text.
"""
    
    def _parse_gemini_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Gemini response and extract decision."""
        try:
            # Extract JSON from response (Gemini might add extra text)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON in Gemini response")
                return None
            
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)
            
            # Validate response structure
            required_fields = ['decision', 'confidence_score', 'reasoning']
            if not all(field in data for field in required_fields):
                logger.warning(f"Incomplete Gemini response: {data}")
                return None
            
            # Validate decision type
            if data['decision'] not in ['REFUND', 'UPDATE_SUCCESS', 'NO_DEBIT_FOUND', 'MANUAL_REVIEW', 'RETRY']:
                logger.warning(f"Invalid decision from Gemini: {data['decision']}")
                return None
            
            # Validate confidence score
            confidence = float(data['confidence_score'])
            if not 0 <= confidence <= 1:
                confidence = max(0, min(1, confidence))
                logger.warning(f"Confidence score out of range, clamped to {confidence}")
            
            return {
                'decision': data['decision'],
                'confidence_score': confidence,
                'reasoning': data['reasoning'][:500],  # Limit reasoning length
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error processing Gemini response: {str(e)}")
            return None
    
    def enhance_decision(
        self,
        base_decision: Decision,
        bank_status: BankStatus,
        merchant_status: MerchantStatus,
        dispute_reason: str,
        dispute_notes: str,
        amount: float,
        amount_match: bool,
    ) -> Decision:
        """
        Enhance a rule-based decision with Gemini AI analysis.
        
        Uses Gemini to validate and potentially improve the confidence score
        or even suggest a different decision based on context.
        
        Args:
            base_decision: Initial decision from rule-based engine
            bank_status: Status from bank API
            merchant_status: Status from merchant API
            dispute_reason: Why dispute was raised
            dispute_notes: Additional notes
            amount: Transaction amount
            amount_match: Whether amounts matched
        
        Returns:
            Enhanced decision (or original if Gemini unavailable)
        """
        if not self.enabled:
            logger.info("Gemini not enabled, using base decision only")
            return base_decision
        
        # Analyze with Gemini
        gemini_analysis = self.analyze_with_gemini(
            bank_status=bank_status,
            merchant_status=merchant_status,
            dispute_reason=dispute_reason,
            dispute_notes=dispute_notes,
            amount=amount,
            amount_match=amount_match,
        )
        
        if not gemini_analysis:
            logger.info("Gemini analysis failed, using base decision")
            return base_decision
        
        # Compare with base decision
        gemini_decision_type = DecisionType[gemini_analysis['decision']]
        
        if gemini_decision_type != base_decision.decision:
            logger.warning(
                f"Gemini suggests different decision: "
                f"{base_decision.decision.value} → {gemini_decision_type.value}"
            )
        
        # Use Gemini decision if confidence is higher
        if gemini_analysis['confidence_score'] > base_decision.confidence_score:
            logger.info(
                f"Using Gemini decision (confidence: {gemini_analysis['confidence_score']:.2f} "
                f"vs base: {base_decision.confidence_score:.2f})"
            )
            return Decision(
                decision=gemini_decision_type,
                confidence_score=gemini_analysis['confidence_score'],
                reasoning=f"[Gemini Analysis] {gemini_analysis['reasoning']}"
            )
        
        # Otherwise keep base decision but note Gemini agreement
        logger.info(
            f"Keeping base decision (Gemini confidence: {gemini_analysis['confidence_score']:.2f})"
        )
        return base_decision


# Global instance
_gemini_engine = None


def get_gemini_engine() -> GeminiDecisionEngine:
    """Get or create global Gemini engine instance."""
    global _gemini_engine
    if _gemini_engine is None:
        _gemini_engine = GeminiDecisionEngine()
    return _gemini_engine
