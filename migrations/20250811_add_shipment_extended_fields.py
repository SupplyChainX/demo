#!/usr/bin/env python3
"""Add extended shipment structured fields.

Fields: transport_mode, container_number, container_count, weight_tons, cargo_value_usd
Idempotent: checks for existence before adding.
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

def add_shipment_extended_fields():
    app = create_app('development')
    with app.app_context():
        inspector = db.inspect(db.engine)
        columns = {c['name'] for c in inspector.get_columns('shipments')}
        ddl_statements = []
        if 'transport_mode' not in columns:
            ddl_statements.append('ALTER TABLE shipments ADD COLUMN transport_mode VARCHAR(20)')
        if 'container_number' not in columns:
            ddl_statements.append('ALTER TABLE shipments ADD COLUMN container_number VARCHAR(30)')
        if 'container_count' not in columns:
            ddl_statements.append('ALTER TABLE shipments ADD COLUMN container_count INTEGER')
        if 'weight_tons' not in columns:
            ddl_statements.append('ALTER TABLE shipments ADD COLUMN weight_tons FLOAT')
        if 'cargo_value_usd' not in columns:
            ddl_statements.append('ALTER TABLE shipments ADD COLUMN cargo_value_usd FLOAT')
        if not ddl_statements:
            print('No new shipment columns needed.')
            return
        for stmt in ddl_statements:
            try:
                db.session.execute(text(stmt))
                db.session.commit()
                print(f"✅ Executed: {stmt}")
            except Exception as e:
                db.session.rollback()
                print(f"❌ Failed: {stmt} -> {e}")

if __name__ == '__main__':
    add_shipment_extended_fields()
