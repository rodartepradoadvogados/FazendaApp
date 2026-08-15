"""lancamento_anexo: numero_documento e data_documento

Central de Documentos — cada anexo de lançamento (boleto, nota fiscal, OS,
orçamento, comprovante...) passa a guardar o número impresso no próprio
documento e a data dele, além de quando foi enviado (`criado_em`). É por
aqui que vários documentos de tipos diferentes ligados ao mesmo lançamento
(orçamento + pedido + nota fiscal + boleto + comprovante) ficam achável por
qualquer um dos números ou por período. Ver
fazenda/api/routers/central_documentos.py.

Revision ID: a8b9c0d1e2f3
Revises: 40b30b737e30
Create Date: 2026-08-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = '40b30b737e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('lancamento_anexo', sa.Column('numero_documento', sa.String(), nullable=True))
    op.create_index(op.f('ix_lancamento_anexo_numero_documento'), 'lancamento_anexo', ['numero_documento'], unique=False)
    op.add_column('lancamento_anexo', sa.Column('data_documento', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('lancamento_anexo', 'data_documento')
    op.drop_index(op.f('ix_lancamento_anexo_numero_documento'), table_name='lancamento_anexo')
    op.drop_column('lancamento_anexo', 'numero_documento')
