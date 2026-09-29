"""aplicacao do agendamento preventivo: registro, animais, log; validade do lote; CRMV

Fatia 8 do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, secao 7). Migracao ADITIVA (tabelas
novas e colunas anulaveis), sem backfill:

  cronograma_sanitario_aplicacao          -- uma linha por 'Aplicar' (quem, quando,
      canal, frasco/lote/validade, ciencia dos pendentes, carencia, estorno);
  cronograma_sanitario_aplicacao_animal   -- animais aplicados/nao aplicados;
  cronograma_sanitario_log                -- trilha imutavel do agendamento;
  lote_estoque.validade                   -- validade do frasco/lote;
  pessoa.crmv                             -- registro do veterinario.

Revision ID: c4e8a1f7b352
Revises: a7c1e5d94b20
Create Date: 2026-09-29 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1f7b352'
down_revision: Union[str, Sequence[str], None] = 'a7c1e5d94b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tem_coluna(insp, tabela: str, coluna: str) -> bool:
    return any(c['name'] == coluna for c in insp.get_columns(tabela))


def upgrade() -> None:
    """Upgrade schema. Idempotente: um banco montado por create_all ja pode ter tudo isto."""
    insp = sa.inspect(op.get_bind())
    if not _tem_coluna(insp, 'lote_estoque', 'validade'):
        op.add_column('lote_estoque', sa.Column('validade', sa.Date(), nullable=True))
    if not _tem_coluna(insp, 'pessoa', 'crmv'):
        op.add_column('pessoa', sa.Column('crmv', sa.String(), nullable=True))
    if insp.has_table('cronograma_sanitario_aplicacao'):
        return

    op.create_table(
        'cronograma_sanitario_aplicacao',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('cronograma_id', sa.Integer(), sa.ForeignKey('cronograma_sanitario.id'), nullable=False),
        sa.Column('estado', sa.String(), nullable=False, server_default='aplicada'),
        sa.Column('canal', sa.String(), nullable=False, server_default='Protocolos'),
        sa.Column('aplicador_pessoa_id', sa.Integer(), sa.ForeignKey('pessoa.id'), nullable=True),
        sa.Column('aplicador_nome', sa.String(), nullable=True),
        sa.Column('aplicador_crmv', sa.String(), nullable=True),
        sa.Column('data_aplicacao', sa.Date(), nullable=False),
        sa.Column('hora', sa.String(), nullable=True),
        sa.Column('produto', sa.String(), nullable=True),
        sa.Column('unidade', sa.String(), nullable=True),
        sa.Column('via', sa.String(), nullable=True),
        sa.Column('dose_total', sa.Float(), nullable=True),
        sa.Column('estoque_id', sa.Integer(), sa.ForeignKey('estoque.id'), nullable=True),
        sa.Column('lote_id', sa.Integer(), sa.ForeignKey('lote_estoque.id'), nullable=True),
        sa.Column('lote_texto', sa.String(), nullable=True),
        sa.Column('validade', sa.Date(), nullable=True),
        sa.Column('frasco_vencido_ciente', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('estoque_desconsiderado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('estoque_motivo', sa.String(), nullable=True),
        sa.Column('custo', sa.Float(), nullable=True),
        sa.Column('carencia_leite_ate', sa.Date(), nullable=True),
        sa.Column('carencia_carne_ate', sa.Date(), nullable=True),
        sa.Column('carencia_texto', sa.String(), nullable=True),
        sa.Column('ciencia_itens', sa.String(), nullable=True),
        sa.Column('ciencia_motivo', sa.String(), nullable=True),
        sa.Column('ciencia_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('ciencia_em', sa.DateTime(), nullable=True),
        sa.Column('retroativo', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('excecoes', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('chave_idempotencia', sa.String(), nullable=True),
        sa.Column('registrado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('registrado_em', sa.DateTime(), nullable=False),
        sa.Column('tipo_estorno', sa.String(), nullable=True),
        sa.Column('estornado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('estornado_em', sa.DateTime(), nullable=True),
        sa.Column('motivo_estorno', sa.String(), nullable=True),
    )
    op.create_index(op.f('ix_cronograma_sanitario_aplicacao_fazenda_id'), 'cronograma_sanitario_aplicacao', ['fazenda_id'])
    op.create_index(op.f('ix_cronograma_sanitario_aplicacao_cronograma_id'), 'cronograma_sanitario_aplicacao', ['cronograma_id'])
    op.create_index(op.f('ix_cronograma_sanitario_aplicacao_estado'), 'cronograma_sanitario_aplicacao', ['estado'])
    op.create_index(op.f('ix_cronograma_sanitario_aplicacao_chave_idempotencia'), 'cronograma_sanitario_aplicacao', ['chave_idempotencia'])

    op.create_table(
        'cronograma_sanitario_aplicacao_animal',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('aplicacao_id', sa.Integer(), sa.ForeignKey('cronograma_sanitario_aplicacao.id'), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('numero_matriz', sa.String(), nullable=False),
        sa.Column('resultado', sa.String(), nullable=False, server_default='aplicado'),
        sa.Column('origem', sa.String(), nullable=False, server_default='janela'),
        sa.Column('motivo_origem', sa.String(), nullable=True),
        sa.Column('dose', sa.Float(), nullable=True),
        sa.Column('unidade', sa.String(), nullable=True),
        sa.Column('peso_kg', sa.Float(), nullable=True),
        sa.Column('peso_estimado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('sanidade_id', sa.Integer(), nullable=True),
        sa.Column('motivo_nao', sa.String(), nullable=True),
        sa.Column('destino_nao', sa.String(), nullable=True),
    )
    op.create_index(op.f('ix_cronograma_sanitario_aplicacao_animal_aplicacao_id'), 'cronograma_sanitario_aplicacao_animal', ['aplicacao_id'])
    op.create_index(op.f('ix_cronograma_sanitario_aplicacao_animal_fazenda_id'), 'cronograma_sanitario_aplicacao_animal', ['fazenda_id'])
    op.create_index(op.f('ix_cronograma_sanitario_aplicacao_animal_numero_matriz'), 'cronograma_sanitario_aplicacao_animal', ['numero_matriz'])

    op.create_table(
        'cronograma_sanitario_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('cronograma_id', sa.Integer(), sa.ForeignKey('cronograma_sanitario.id'), nullable=False),
        sa.Column('aplicacao_id', sa.Integer(), sa.ForeignKey('cronograma_sanitario_aplicacao.id'), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('usuario_nome', sa.String(), nullable=True),
        sa.Column('acao', sa.String(), nullable=False),
        sa.Column('canal', sa.String(), nullable=True),
        sa.Column('motivo', sa.String(), nullable=True),
        sa.Column('detalhe', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_cronograma_sanitario_log_fazenda_id'), 'cronograma_sanitario_log', ['fazenda_id'])
    op.create_index(op.f('ix_cronograma_sanitario_log_cronograma_id'), 'cronograma_sanitario_log', ['cronograma_id'])
    op.create_index(op.f('ix_cronograma_sanitario_log_aplicacao_id'), 'cronograma_sanitario_log', ['aplicacao_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('cronograma_sanitario_log')
    op.drop_table('cronograma_sanitario_aplicacao_animal')
    op.drop_table('cronograma_sanitario_aplicacao')
    op.drop_column('pessoa', 'crmv')
    op.drop_column('lote_estoque', 'validade')
