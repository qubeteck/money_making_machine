"""add job attempts

Revision ID: 7c1b9d2e4f60
Revises: fe5a4dfc46ef
Create Date: 2026-11-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c1b9d2e4f60'
down_revision: Union[str, Sequence[str], None] = 'fe5a4dfc46ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the retry-attempt counter to recorded job runs."""
    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='1')
        )


def downgrade() -> None:
    """Remove the retry-attempt counter."""
    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.drop_column('attempts')
