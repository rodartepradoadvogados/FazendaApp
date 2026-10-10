"""Excluir lançamentos (Fase 1): trilha + pedidos estruturados

- Nova tabela `exclusao_registro` — trilha de auditoria de exclusões, também
  para administrador (quem/apagou/aprovou/rejeitou; resumo do impacto; snapshot
  das linhas apagadas para restauração futura, SEM CPF/dado de saúde).
- Nova tabela `solicitacao_exclusao_apoio` — segundo apoiador de um pedido já
  pendente (deduplicação: em vez de um segundo pedido, um "apoio").
- `solicitacao_exclusao` ganha `motivo`, `risco` e `impacto_resumo_json`
  (motivo do solicitante, risco calculado e foto do impacto na hora do pedido,
  para o admin comparar com o impacto "de agora").

Migração 100% ADITIVA (nenhuma linha existente muda de significado). O índice de
deduplicação em `(fazenda_id, tipo, id_alvo)` foi criado NÃO-único de propósito:
`fazenda_id` pode ser NULL em linhas legadas e já pode haver pendentes duplicados
na base — um índice único parcial quebraria o upgrade. A deduplicação é feita em
código (`confirmar` retorna "ja_pedido"/apoio); o índice só acelera a checagem.

Idempotente por tabela (`insp.has_table`) — igual à migração de criação das
tabelas sem `create_table` (4ede0ee68b09): em produção a subida da app chama
`create_all` como rede de segurança, então `exclusao_registro` e
`solicitacao_exclusao_apoio` já existem quando esta migração roda, e o
`op.create_table` sem guarda quebra o upgrade.

Revision ID: 78dbbd8c8c0f
Revises: d4a8e1b7c935
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78dbbd8c8c0f'
down_revision: Union[str, Sequence[str], None] = 'd4a8e1b7c935'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    insp = sa.inspect(op.get_bind())

    if not insp.has_table('exclusao_registro'):
        op.create_table(
            'exclusao_registro',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('codigo', sa.String(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('username', sa.String(), nullable=True),
            sa.Column('papel', sa.String(), nullable=True),
            sa.Column('acao', sa.String(), nullable=False),
            sa.Column('tipo', sa.String(), nullable=True),
            sa.Column('id_alvo', sa.String(), nullable=True),
            sa.Column('titulo', sa.String(), nullable=True),
            sa.Column('motivo', sa.String(), nullable=True),
            sa.Column('resumo_json', sa.Text(), nullable=True),
            sa.Column('snapshot_json', sa.Text(), nullable=True),
            sa.Column('solicitacao_id', sa.Integer(), nullable=True),
            sa.Column('solicitado_por', sa.String(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_exclusao_registro_codigo'), 'exclusao_registro', ['codigo'], unique=False)
        op.create_index(op.f('ix_exclusao_registro_fazenda_id'), 'exclusao_registro', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_exclusao_registro_acao'), 'exclusao_registro', ['acao'], unique=False)
        # Listagem da trilha: por fazenda, mais recente primeiro.
        op.create_index(
            op.f('ix_exclusao_registro_fazenda_criadoem'),
            'exclusao_registro', ['fazenda_id', 'criado_em'], unique=False,
        )

    if not insp.has_table('solicitacao_exclusao_apoio'):
        op.create_table(
            'solicitacao_exclusao_apoio',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('solicitacao_id', sa.Integer(), nullable=False),
            sa.Column('username', sa.String(), nullable=False),
            sa.Column('motivo', sa.String(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['solicitacao_id'], ['solicitacao_exclusao.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            op.f('ix_solicitacao_exclusao_apoio_solicitacao_id'),
            'solicitacao_exclusao_apoio', ['solicitacao_id'], unique=False,
        )

    op.add_column('solicitacao_exclusao', sa.Column('motivo', sa.String(), nullable=True))
    op.add_column('solicitacao_exclusao', sa.Column('risco', sa.String(), nullable=True))
    op.add_column('solicitacao_exclusao', sa.Column('impacto_resumo_json', sa.Text(), nullable=True))
    # Acelera a checagem de duplicidade em confirmar (dedup é feito em código).
    op.create_index(
        op.f('ix_solicitacao_exclusao_pendente_dedup'),
        'solicitacao_exclusao', ['fazenda_id', 'tipo', 'id_alvo'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    insp = sa.inspect(op.get_bind())

    op.drop_index(op.f('ix_solicitacao_exclusao_pendente_dedup'), table_name='solicitacao_exclusao')
    op.drop_column('solicitacao_exclusao', 'impacto_resumo_json')
    op.drop_column('solicitacao_exclusao', 'risco')
    op.drop_column('solicitacao_exclusao', 'motivo')

    if insp.has_table('solicitacao_exclusao_apoio'):
        op.drop_index(op.f('ix_solicitacao_exclusao_apoio_solicitacao_id'), table_name='solicitacao_exclusao_apoio')
        op.drop_table('solicitacao_exclusao_apoio')

    if insp.has_table('exclusao_registro'):
        op.drop_index(op.f('ix_exclusao_registro_fazenda_criadoem'), table_name='exclusao_registro')
        op.drop_index(op.f('ix_exclusao_registro_acao'), table_name='exclusao_registro')
        op.drop_index(op.f('ix_exclusao_registro_fazenda_id'), table_name='exclusao_registro')
        op.drop_index(op.f('ix_exclusao_registro_codigo'), table_name='exclusao_registro')
        op.drop_table('exclusao_registro')