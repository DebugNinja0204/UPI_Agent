"""Configuration for Mock Bank API"""

import os
from datetime import timedelta

class Config:
    """Base configuration for Mock Bank"""
    DEBUG = True
    PORT = 5001
    HOST = '0.0.0.0'
    
    # In-memory storage
    REFUNDS_STORAGE = {}
    
    # Processing delays (in seconds)
    REFUND_PROCESSING_DELAY = 2  # Simulate processing time


config = {
    'development': Config,
    'default': Config,
}
