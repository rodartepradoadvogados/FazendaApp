"""servico: perda_causada_por_servico_id (reverte perda automática ao excluir a IA causadora)

A detecção automática de perda de prenhez por reinseminação (ver
fazenda/rules/perda_prenhez.py) grava a perda no serviço ANTERIOR sem
guardar qual serviço novo a causou — excluir essa nova inseminação (ex.:
lançamento em duplicidade) não tinha como desfazer a perda que ela mesma
disparou. Esta FK aponta, no serviço que recebeu a perda automática, para o
serviço novo que a causou; `exclusoes.py` usa-a para reverter a perda quando
esse causador é excluído (e o motivo ainda não foi confirmado por alguém).

Coluna aditiva e nula: nenhum registro existente muda de comportamento.

Revision ID: 52e4041d41d7
Revises: 77c6d0d3e55c
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52e4041d41d7'
down_revision: Union[str, Sequence[str], None] = '77c6d0d3e55c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('servico', sa.Column('perda_causada_por_servico_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('servico') as batch_op:
        batch_op.create_foreign_key(
            'fk_servico_perda_causada_por_servico_id', 'servico',
            ['perda_causada_por_servico_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('servico') as batch_op:
        batch_op.drop_constraint('fk_servico_perda_causada_por_servico_id', type_='foreignkey')
    op.drop_column('servico', 'perda_causada_por_servico_id')
