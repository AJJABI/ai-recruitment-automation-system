"""drop slot_id from interviews

Revision ID: a1b2c3d4e5f6
Revises: 72ceb9b1845a
Create Date: 2026-05-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '72ceb9b1845a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Supprime la colonne slot_id de la table interviews."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('interviews')]

    if 'slot_id' in columns:
        op.drop_column('interviews', 'slot_id')


def downgrade() -> None:
    """Restaure la colonne slot_id si besoin."""
    op.add_column(
        'interviews',
        sa.Column('slot_id', sa.Integer(), nullable=True)
    )