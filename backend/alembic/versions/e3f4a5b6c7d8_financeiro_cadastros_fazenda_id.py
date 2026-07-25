"""financeiro: fazenda_id em PlanoContaGerencial/TipoDocumento/FormaPagamentoCadastro (Fase 3B)

Fecha o gap dos cadastros do Financeiro no retrofit multi-tenant: mesma
coluna aditiva (nullable, com índice) já usada em ContaGerencial/
LancamentoItem/LancamentoAnexo (Fase 3A — d2e3f4a5b6c7), backfillada para a
fazenda #1 (grandfathered) quando ela já existir — sem retroatividade em
nenhuma outra fazenda.

Os três cadastros têm campo único globalmente (plano_conta_gerencial.codigo,
tipo_documento.nome, forma_pagamento_cadastro.nome) e trocam esse
unique(campo) por unique(campo, fazenda_id), mesmo padrão de
centro_custo/sanidade (c9d1e2f3a4b5) — senão a 2ª fazenda nunca conseguiria
cadastrar um item com código/nome já usado pela 1ª.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, coluna do campo único, nome da constraint nova)
_TABELAS_CAMPO_UNICO = [
    ('plano_conta_gerencial', 'codigo', 'uq_plano_conta_gerencial_codigo_fazenda'),
    ('tipo_documento', 'nome', 'uq_tipo_documento_nome_fazenda'),
    ('forma_pagamento_cadastro', 'nome', 'uq_forma_pagamento_cadastro_nome_fazenda'),
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    for tabela, campo, nome_constraint in _TABELAS_CAMPO_UNICO:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            try:
                batch_op.drop_index(f'ix_{tabela}_{campo}')
            except Exception:
                pass
            batch_op.create_index(f'ix_{tabela}_{campo}', [campo], unique=False)
            batch_op.create_unique_constraint(nome_constraint, [campo, 'fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    for tabela, campo, nome_constraint in reversed(_TABELAS_CAMPO_UNICO):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_constraint(nome_constraint, type_='unique')
            batch_op.drop_index(f'ix_{tabela}_{campo}')
            batch_op.create_index(f'ix_{tabela}_{campo}', [campo], unique=True)
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
