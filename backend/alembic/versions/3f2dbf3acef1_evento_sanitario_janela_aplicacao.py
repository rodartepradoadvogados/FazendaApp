"""evento_sanitario: janela de aplicação, ação ao sair, teto etário, veterinário padrão

Cadastro de vacina/exame (EventoSanitario) ganha a janela de aplicação do
modelo aprovado (Central de Protocolos > Cadastro > Sanitário > Preventivo):
De X até Y [dias|meses] após o gatilho, o que fazer quando a janela se
encerra sem aplicação (sair/manter/notificar), um teto etário opcional (trava
biológica, independente da ação) e o veterinário padrão sugerido no
agendamento (FK a Pessoa, mesmo padrão de CronogramaSanitario.
veterinario_pessoa_id). Migração ADITIVA, SEM BACKFILL — todo evento
existente nasce sem janela cadastrada (nenhuma regra de hoje muda de
comportamento).

Revision ID: a1b2c3d4e5f6
Revises: f3c5e07b91aa
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f2dbf3acef1'
down_revision: Union[str, Sequence[str], None] = 'f3c5e07b91aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('evento_sanitario', sa.Column('janela_de_valor', sa.Integer(), nullable=True))
    op.add_column('evento_sanitario', sa.Column('janela_de_unidade', sa.String(), nullable=True))
    op.add_column('evento_sanitario', sa.Column('janela_ate_valor', sa.Integer(), nullable=True))
    op.add_column('evento_sanitario', sa.Column('janela_ate_unidade', sa.String(), nullable=True))
    op.add_column('evento_sanitario', sa.Column('acao_fora_janela', sa.String(), nullable=True))
    op.add_column('evento_sanitario', sa.Column('teto_etario_valor', sa.Integer(), nullable=True))
    op.add_column('evento_sanitario', sa.Column('teto_etario_unidade', sa.String(), nullable=True))
    op.add_column('evento_sanitario', sa.Column('veterinario_padrao_pessoa_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('evento_sanitario', schema=None) as batch_op:
        batch_op.create_index(
            op.f('ix_evento_sanitario_veterinario_padrao_pessoa_id'),
            ['veterinario_padrao_pessoa_id'], unique=False,
        )
        batch_op.create_foreign_key(
            'fk_evento_sanitario_veterinario_padrao_pessoa_id_pessoa',
            'pessoa', ['veterinario_padrao_pessoa_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('evento_sanitario', schema=None) as batch_op:
        batch_op.drop_constraint('fk_evento_sanitario_veterinario_padrao_pessoa_id_pessoa', type_='foreignkey')
        batch_op.drop_index(op.f('ix_evento_sanitario_veterinario_padrao_pessoa_id'))
    op.drop_column('evento_sanitario', 'veterinario_padrao_pessoa_id')
    op.drop_column('evento_sanitario', 'teto_etario_unidade')
    op.drop_column('evento_sanitario', 'teto_etario_valor')
    op.drop_column('evento_sanitario', 'acao_fora_janela')
    op.drop_column('evento_sanitario', 'janela_ate_unidade')
    op.drop_column('evento_sanitario', 'janela_ate_valor')
    op.drop_column('evento_sanitario', 'janela_de_unidade')
    op.drop_column('evento_sanitario', 'janela_de_valor')
