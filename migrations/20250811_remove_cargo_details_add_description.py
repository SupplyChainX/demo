"""
Migration: Remove cargo_details from shipments, add description
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Remove cargo_details column
    with op.batch_alter_table('shipments') as batch_op:
        batch_op.drop_column('cargo_details')
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))

def downgrade():
    # Re-add cargo_details column
    with op.batch_alter_table('shipments') as batch_op:
        batch_op.add_column(sa.Column('cargo_details', sa.JSON(), nullable=True))
        batch_op.drop_column('description')
