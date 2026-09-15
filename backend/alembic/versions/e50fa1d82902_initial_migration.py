"""initial migration

Revision ID: e50fa1d82902
Revises: 
Create Date: 2026-09-15 13:29:12.031553

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e50fa1d82902'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'cases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('pattern_type', sa.String(), nullable=False),
        sa.Column('cluster_id', sa.String(), nullable=True),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('risk_bucket', sa.String(), nullable=False),
        sa.Column('evidence_summary', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cases_account_id'), 'cases', ['account_id'], unique=False)
    op.create_index(op.f('ix_cases_id'), 'cases', ['id'], unique=False)

    op.create_table(
        'payer_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('payer_account_id', sa.String(), nullable=False),
        sa.Column('payee_account_id', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('risk_score_at_time', sa.Float(), nullable=True),
        sa.Column('risk_bucket_at_time', sa.String(), nullable=True),
        sa.Column('user_action', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payer_events_id'), 'payer_events', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_payer_events_id'), table_name='payer_events')
    op.drop_table('payer_events')
    op.drop_index(op.f('ix_cases_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_account_id'), table_name='cases')
    op.drop_table('cases')
