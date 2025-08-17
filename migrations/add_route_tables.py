#!/usr/bin/env python3
"""
Add Route and IntegrationLog tables to the database
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Route, IntegrationLog

def add_route_tables():
    """Add new tables for route optimization"""
    app = create_app('development')
    
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Verify tables were created
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'routes' in tables:
            print("✅ Routes table created successfully")
        else:
            print("❌ Failed to create routes table")
            
        if 'integration_logs' in tables:
            print("✅ IntegrationLog table created successfully")
        else:
            print("❌ Failed to create integration_logs table")
            
        # Check columns in routes table
        columns = [col['name'] for col in inspector.get_columns('routes')]
        print(f"\nRoutes table columns: {', '.join(columns)}")
        
        # Add indexes for performance
        try:
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_routes_shipment_id ON routes(shipment_id)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_routes_is_current ON routes(is_current)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_routes_risk_score ON routes(risk_score)')
            db.session.execute('CREATE INDEX IF NOT EXISTS idx_integration_logs_timestamp ON integration_logs(timestamp)')
            db.session.commit()
            print("\n✅ Indexes created successfully")
        except Exception as e:
            print(f"\n❌ Error creating indexes: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    add_route_tables()
