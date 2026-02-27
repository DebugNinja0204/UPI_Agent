#!/usr/bin/env python
"""
Entry point for running the UPI Dispute Resolution Agent.
"""

import os
from app import create_app

if __name__ == '__main__':
    # Get configuration from environment, default to development
    config_name = os.getenv('FLASK_ENV', 'development')
    
    # Create Flask app
    app = create_app(config_name)
    
    # Run the development server
    # For production, use gunicorn or another WSGI server
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=app.debug,
        use_reloader=app.debug
    )
