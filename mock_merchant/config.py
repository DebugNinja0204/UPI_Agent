"""Configuration for Mock Merchant API"""

import os

class Config:
    """Base configuration for Mock Merchant"""
    DEBUG = True
    PORT = 5002
    HOST = '0.0.0.0'
    
    # In-memory storage
    RECONCILIATIONS_STORAGE = {}


config = {
    'development': Config,
    'default': Config,
}
