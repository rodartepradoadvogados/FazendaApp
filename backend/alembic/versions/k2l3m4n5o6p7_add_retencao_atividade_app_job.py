"""add_retencao_atividade_app_job

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-10-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'k2l3m4n5o6p7'
down_revision = 'j1k2l3m4n5o6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Create a simple SQL function for cleanup (PostgreSQL)
    # For SQLite, we'll rely on a scheduled job instead
    if insp.dialect.name == 'postgresql':
        op.execute(text("""
            CREATE OR REPLACE FUNCTION limpar_atividade_app_antiga()
            RETURNS void AS $$
            BEGIN
                DELETE FROM atividade_app
                WHERE ocorrido_em < NOW() - INTERVAL '90 days';
            END;
            $$ LANGUAGE plpgsql;
        """))
        # Create pg_cron job if extension exists (optional)
        # SELECT cron.schedule('limpar-atividade-app-90d', '0 3 * * *', 'SELECT limpar_atividade_app_antiga();');
    
    # For SQLite, add a comment/placeholder - the cleanup will be a scheduled task
    # No DDL needed for SQLite; the job runs externally


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    if insp.dialect.name == 'postgresql':
        op.execute(text("DROP FUNCTION IF EXISTS limpar_atividade_app_antiga();"))
        # SELECT cron.unschedule('limpar-atividade-app-90d');