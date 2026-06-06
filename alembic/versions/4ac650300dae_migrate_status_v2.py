"""migrate_status_v2

Revision ID: 4ac650300dae
Revises: 
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '4ac650300dae'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migration status → status_v2 pour les candidatures existantes
    op.execute("UPDATE applications SET status_v2 = 'REJECTED_AUTO' WHERE status = 'REJETÉ'")
    op.execute("UPDATE applications SET status_v2 = 'PRESELECTED'   WHERE status = 'ENTRETIEN'")
    op.execute("UPDATE applications SET status_v2 = 'MATCHED'       WHERE status = 'EN_ATTENTE' AND score_final IS NOT NULL")
    op.execute("UPDATE applications SET status_v2 = 'APPLIED'       WHERE status_v2 IS NULL")


def downgrade() -> None:
    # Rollback — remettre status_v2 à NULL
    op.execute("UPDATE applications SET status_v2 = NULL")