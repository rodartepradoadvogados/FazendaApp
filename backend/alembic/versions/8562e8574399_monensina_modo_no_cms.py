"""dieta_simulacao: como a monensina desconta do CMS

Duas colunas novas para a decisão que o usuário passou a tomar na Etapa 2 da
Formulação de Dietas (ago/2026): a monensina agora reduz o CONSUMO de matéria
seca (antes ela só mexia na energia — metano e ED), e a redução tem três
parametrizações à escolha, porque a literatura reporta o efeito das duas
formas e nenhuma serve bem para todo rebanho:

  - "kg" (padrão) ... -0,30 kg de MS/dia, meta-análise de Duffield et al. (2008)
  - "pct" .......... -2% do CMS, desconto proporcional ao tamanho do animal
  - "manual" ....... o valor medido no próprio rebanho, em monensina_reducao_manual

Simulação antiga fica com "kg"/NULL, que é exatamente o comportamento padrão —
nenhuma simulação salva muda de resultado por causa desta migração (quem não
usa monensina não é afetado de forma alguma).

Revision ID: 8562e8574399
Revises: 13fe8233d2c1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8562e8574399'
down_revision: Union[str, Sequence[str], None] = '13fe8233d2c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'dieta_simulacao',
        sa.Column('monensina_modo', sa.String(), nullable=False, server_default='kg'),
    )
    op.add_column(
        'dieta_simulacao',
        sa.Column('monensina_reducao_manual', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('dieta_simulacao', 'monensina_reducao_manual')
    op.drop_column('dieta_simulacao', 'monensina_modo')
