"""lancamento_item: vínculo com o vale gerado a partir do item

Um item de nota que na verdade é gasto pessoal de um funcionário/empreiteiro/
diarista vira um vale de verdade (ValeFuncionario ou ValeAvulso) e deixa de
entrar nos relatórios gerenciais. Duas colunas nullable, mutuamente
exclusivas — ver fazenda/models/financeiro.py::LancamentoItem e
fazenda/rules/vale_item.py.

Revision ID: e2f3a4b5c6d7
Revises: b3c4d5e6f7a1
Create Date: 2026-08-07 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Colunas aditivas e nulas, SEM FK real no banco — mesma convenção de
    # conta_corrente.fazenda_id (b2c3d4e5f6a8) e animal.fazenda_id
    # (f1a2b3c4d5e6). O `foreign_key=` do SQLModel serve ao metadata
    # (create_all em banco novo/teste); no Postgres de produção o vínculo é
    # aplicativo, e é a aplicação que garante a integridade (ver
    # rules/vale_item.py::limpar_vinculo_de_itens).
    op.add_column('lancamento_item', sa.Column('vale_funcionario_id', sa.Integer(), nullable=True))
    op.add_column('lancamento_item', sa.Column('vale_avulso_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_lancamento_item_vale_funcionario_id'), 'lancamento_item', ['vale_funcionario_id'], unique=False)
    op.create_index(op.f('ix_lancamento_item_vale_avulso_id'), 'lancamento_item', ['vale_avulso_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_lancamento_item_vale_avulso_id'), table_name='lancamento_item')
    op.drop_index(op.f('ix_lancamento_item_vale_funcionario_id'), table_name='lancamento_item')
    op.drop_column('lancamento_item', 'vale_avulso_id')
    op.drop_column('lancamento_item', 'vale_funcionario_id')
