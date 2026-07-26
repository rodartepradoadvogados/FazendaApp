"""empresa_operadora: âncora para a empresa de software, separada da Fazenda

Fase 0 (fundação) da proposta de separação fazenda/empresa de software:
cria uma tabela nova e isolada, sem tocar nenhuma tabela existente. Nasce
com uma única linha (id=1), sem CNPJ preenchido — existe para servir de
âncora estável a quem vier depois (contrato/DPA de operador, cabeçalho de
e-mail, relatório), sem precisar reconstruir nada quando a empresa for
formalizada: só preencher `cnpj`. Ver fazenda/models/multitenant.py.

Revision ID: 63765dda4ff8
Revises: d00c11395f94
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '63765dda4ff8'
down_revision: Union[str, Sequence[str], None] = 'd00c11395f94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'empresa_operadora',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('cnpj', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('endereco', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO empresa_operadora (nome, criado_em, atualizado_em) "
        "VALUES (:nome, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"nome": "Empresa de software (nome/CNPJ a definir)"})


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('empresa_operadora')
