#!/usr/bin/env python3
"""
Migration script to add enhanced assistant tables to the database
"""

import os
import sys
import logging
from datetime import datetime

# Ensure the app directory is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('enhanced_assistant_migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the database migration to create enhanced assistant tables"""
    logger.info("Starting enhanced assistant tables migration")
    
    try:
        # Import necessary modules
        from app import db
        from app.models_enhanced import ChatSession, ChatMessage, UserPersonalization, AuditLogEnhanced
        
        logger.info("Creating tables if they don't exist...")
        
        try:
            # Create tables - they may already exist
            db.create_all()
            logger.info("Tables created successfully")
        except Exception as table_error:
            if "already defined" in str(table_error):
                logger.info("Tables already exist, continuing...")
            else:
                raise table_error
        
        logger.info("Migration completed successfully")
        return True
        
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Please ensure that app/models_enhanced.py exists and can be imported")
        return False
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
