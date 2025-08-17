#!/usr/bin/env python3
"""
SupplyChainX Application Entry Point
"""
import os
import logging
from app import create_app, socketio

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Get configuration from environment
config_name = os.getenv('FLASK_CONFIG', 'development')

# Create application
app = create_app(config_name)

if __name__ == '__main__':
    # Run with Socket.IO (disable reloader to prevent infinite restart loop)
    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=False,  # Temporarily disable debug mode
        use_reloader=False  # Disable auto-reloader to prevent restart loop
    )
