"""Biblioteca de alimentos — mestre CowData + cópia por fazenda, faixa de inclusão, exigências editadas

Formulação de Dietas > aba "Biblioteca de referência" (#155). Três mudanças:
1. `alimento_nutricional.fazenda_id` deixa de ser obrigatório — `NULL` passa
   a marcar as linhas da biblioteca mestre CowData (global, semeada em
   runtime por `fazenda.rules.biblioteca_alimentos.semear_biblioteca_mestre`,
   não por esta migração — mesmo padrão preguiçoso de `_seed_tabela_nutricional`
   em alimentacao.py, ver justificativa lá).
2. `alimento_nutricional` ganha `origem_mestre_id` (self-FK — aponta pra
   linha mestre da qual esta é cópia-por-fazenda) e a faixa de inclusão
   sugerida (`inclusao_min_pct`/`inclusao_max_pct`).
3. `dieta_simulacao` ganha `exigencias_editadas_json` — overrides manuais da
   coluna "Exigência" da Etapa 4 (balanço ao vivo).

Revision ID: 39bcd3f22a95
Revises: 810153450ce9
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39bcd3f22a95'
down_revision: Union[str, Sequence[str], None] = '810153450ce9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # FK auto-sinalizada (sem `name=`) dentro de um `add_column` do batch mode
    # quebra no SQLite ("Constraint must have a name") — coluna e FK entram
    # em duas operações batch separadas, a FK com nome explícito, mesmo
    # padrão de fk_dieta_lancamento_dieta_simulacao_id em e92e4d3dedaa.
    with op.batch_alter_table('alimento_nutricional') as batch_op:
        batch_op.alter_column('fazenda_id', existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column('origem_mestre_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('inclusao_min_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('inclusao_max_pct', sa.Float(), nullable=True))
    with op.batch_alter_table('alimento_nutricional') as batch_op:
        batch_op.create_foreign_key(
            'fk_alimento_nutricional_origem_mestre_id', 'alimento_nutricional', ['origem_mestre_id'], ['id'],
        )
    op.create_index('ix_alimento_nutricional_origem_mestre_id', 'alimento_nutricional', ['origem_mestre_id'])

    op.add_column('dieta_simulacao', sa.Column('exigencias_editadas_json', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dieta_simulacao', 'exigencias_editadas_json')

    op.drop_index('ix_alimento_nutricional_origem_mestre_id', table_name='alimento_nutricional')
    with op.batch_alter_table('alimento_nutricional') as batch_op:
        batch_op.drop_constraint('fk_alimento_nutricional_origem_mestre_id', type_='foreignkey')
    with op.batch_alter_table('alimento_nutricional') as batch_op:
        batch_op.drop_column('inclusao_max_pct')
        batch_op.drop_column('inclusao_min_pct')
        batch_op.drop_column('origem_mestre_id')
        batch_op.alter_column('fazenda_id', existing_type=sa.Integer(), nullable=False)
