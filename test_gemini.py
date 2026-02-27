#!/usr/bin/env python
"""
Quick test script for Gemini API integration.

Run this to verify:
1. Gemini API key is set
2. Package is installed
3. Connection works
"""

import os
import sys
from datetime import datetime

print("=" * 60)
print("🤖 Gemini AI Integration Test")
print("=" * 60)
print()

# Check 1: Is the package installed?
print("1️⃣  Checking if google-generativeai is installed...")
try:
    import google.generativeai as genai
    print("   ✅ Package installed")
except ImportError:
    print("   ❌ Package NOT installed")
    print("   Install with: pip install google-generativeai")
    sys.exit(1)

print()

# Check 2: Is API key set?
print("2️⃣  Checking GEMINI_API_KEY environment variable...")
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("   ❌ GEMINI_API_KEY not set")
    print()
    print("   SET IT NOW:")
    print("   Option A - Command:")
    print('     $env:GEMINI_API_KEY = "your-key-here"')
    print()
    print("   Option B - Create .env file:")
    print("     GEMINI_API_KEY=your-key-here")
    print()
    print("   Get API key at: https://ai.google.dev")
    sys.exit(1)

print(f"   ✅ API key found: {api_key[:10]}...{api_key[-5:]}")
print()

# Check 3: Can we connect to Gemini?
print("3️⃣  Testing connection to Gemini API...")
try:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    # Simple test prompt
    response = model.generate_content("Respond with just 'OK'")
    
    if response and response.text:
        print("   ✅ Connection successful")
        print(f"   Response: {response.text[:50]}")
    else:
        print("   ⚠️  No response from API")
        sys.exit(1)

except Exception as e:
    print(f"   ❌ Connection failed: {str(e)}")
    sys.exit(1)

print()

# Check 4: Can we use the Gemini decision engine?
print("4️⃣  Testing GeminiDecisionEngine...")
try:
    from app.services.gemini_decision_engine import get_gemini_engine
    from app.services.bank_client import BankStatus
    from app.services.merchant_client import MerchantStatus
    
    engine = get_gemini_engine()
    
    if not engine.enabled:
        print("   ❌ Gemini engine not enabled")
        sys.exit(1)
    
    print("   ✅ Engine initialized")
    
    # Quick analysis
    print()
    print("5️⃣  Running sample analysis...")
    print("   (This will take 5-10 seconds)")
    print()
    
    analysis = engine.analyze_with_gemini(
        bank_status=BankStatus.DEBIT_SUCCESS,
        merchant_status=MerchantStatus.ORDER_FAILED,
        dispute_reason="TRANSACTION_NOT_RECEIVED",
        dispute_notes="I was charged but never received my order",
        amount=500.0,
        amount_match=True
    )
    
    if not analysis:
        print("   ❌ Analysis failed")
        sys.exit(1)
    
    print("   ✅ Analysis completed!")
    print()
    print("   RESULT:")
    print(f"   Decision: {analysis['decision']}")
    print(f"   Confidence: {analysis['confidence_score']:.0%}")
    print(f"   Reasoning: {analysis['reasoning'][:100]}...")

except Exception as e:
    print(f"   ❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 60)
print("✅ ALL CHECKS PASSED!")
print("=" * 60)
print()
print("Your Gemini AI integration is ready to use! 🚀")
print()
print("Next steps:")
print("1. Review GEMINI_SETUP.md for integration details")
print("2. Update your dispute resolution logic to use enhance_decision()")
print("3. Test with real disputes")
print()
print("Questions? See GEMINI_SETUP.md")
