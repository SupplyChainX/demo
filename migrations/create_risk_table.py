"""
Create Risk table for risk management system
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from datetime import datetime

def create_risk_table():
    """Create the Risk table with comprehensive risk tracking"""
    
    # Create Risk table
    with db.engine.connect() as conn:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS risks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                
                -- Risk identification
                risk_type VARCHAR(50) NOT NULL,  -- weather, geopolitical, supplier, etc.
                title VARCHAR(200) NOT NULL,
                description TEXT,
                
                -- Risk assessment
                severity VARCHAR(20) NOT NULL,  -- low, medium, high, critical
                probability FLOAT,  -- 0.0 to 1.0
                confidence FLOAT,   -- 0.0 to 1.0 
                impact_score FLOAT, -- 0.0 to 100.0
                
                -- Location and scope
                location_data JSON,  -- {lat, lon, region, country}
                impact_radius_km FLOAT,
                
                -- External data
                data_sources JSON,  -- [source names]
                raw_data JSON,      -- Original API response
                external_id VARCHAR(100),  -- External system ID
                
                -- Lifecycle
                status VARCHAR(50) DEFAULT 'active',  -- active, resolved, monitoring
                detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                
                -- Analysis
                affected_entities JSON,  -- {shipments: [], suppliers: [], routes: []}
                risk_factors JSON,       -- [{type, description, weight}]
                
                -- Audit
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(50) DEFAULT 'risk_predictor_agent',
                
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            )
        """))
        
        # Create indexes for performance
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_risks_workspace ON risks(workspace_id)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_risks_type_severity ON risks(risk_type, severity)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_risks_status ON risks(status)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_risks_detected ON risks(detected_at)"))
        
        # Create risk_alerts association table
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS risk_alerts (
                risk_id INTEGER NOT NULL,
                alert_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (risk_id, alert_id),
                FOREIGN KEY (risk_id) REFERENCES risks(id),
                FOREIGN KEY (alert_id) REFERENCES alerts(id)
            )
        """))
        
        conn.commit()
    
    print("✅ Risk table and associations created successfully")

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        create_risk_table()
