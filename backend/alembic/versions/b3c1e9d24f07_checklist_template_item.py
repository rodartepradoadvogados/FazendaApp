"""checklist_template_item + cronograma_sanitario_checklist_item

Fase 0, passo 3 do redesenho do evento sanitário
(docs/redesenho-evento-sanitario.md) — checklist por Ocorrência
(`CronogramaSanitario`, ver seção 1 do documento) e o cadastro do template
padrão por tipo de evento (seção 3.7.3). Migração ADITIVA — a única linha
nova é o seed dos 9 itens canônicos do template global (fazenda_id NULL,
seção 3.4: 5 de vacina, 4 de exame), para toda fazenda nascer com o mesmo
ponto de partida de hoje seria manual. Nenhuma regra de hoje muda de
comportamento (a leitura/escrita destas duas tabelas só entra na Fase 1).

Revision ID: b3c1e9d24f07
Revises: 3f2dbf3acef1
Create Date: 2026-09-11 00:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1e9d24f07'
down_revision: Union[str, Sequence[str], None] = '3f2dbf3acef1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Redação exata da seção 3.4 do redesenho — mesma ordem, mesma chave (decide
# o comportamento especial na UI: estoque nunca bloqueia, vet exige Sim/Não,
# horario/lotes exigem preencher/revisar antes de confirmar, financeiro abre
# o modal). "tratamento" reaproveita o template de "vacina" (seção 3.7.0).
_ITENS_VACINA = [
    (1, "estoque", "Estoque suficiente?"),
    (2, "vet", "Confirmação com o veterinário selecionado"),
    (3, "horario", "Horário da aplicação"),
    (4, "lotes", "Lotes de manejo atuais"),
    (5, "financeiro", "Lançamento financeiro"),
]
_ITENS_EXAME = [
    (1, "vet", "Confirmação com o veterinário selecionado"),
    (2, "horario", "Horário da coleta/realização do exame"),
    (3, "lotes", "Lotes de manejo atuais"),
    (4, "financeiro", "Lançamento financeiro"),
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Idempotente por tabela (`insp.has_table`, mesmo padrão de
    # 4ede0ee68b09) — precisa ser seguro quando a tabela já existe via
    # `SQLModel.metadata.create_all` (rede de segurança da subida da app),
    # cenário coberto por tests/test_migracao_tabelas_faltantes.py.
    if not insp.has_table('checklist_template_item'):
        op.create_table(
            'checklist_template_item',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tipo', sa.String(), nullable=False),
            sa.Column('nome', sa.String(), nullable=False),
            sa.Column('chave', sa.String(), nullable=False, server_default='custom'),
            sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_checklist_template_item_tipo'), 'checklist_template_item', ['tipo'])
        op.create_index(op.f('ix_checklist_template_item_fazenda_id'), 'checklist_template_item', ['fazenda_id'])

    # Seed condicionado a "tabela vazia" (não a "acabei de criar") — cobre
    # tanto a tabela nova quanto a que já existia via create_all mas sem os
    # itens ainda (create_all só cria a estrutura, nunca semeia dados);
    # numa 2ª chamada (tabela já semeada) não duplica.
    conn = op.get_bind()
    ja_tem_linha = conn.execute(sa.text("SELECT 1 FROM checklist_template_item LIMIT 1")).first()
    if not ja_tem_linha:
        checklist_template_item = sa.table(
            'checklist_template_item',
            sa.column('tipo', sa.String()), sa.column('nome', sa.String()), sa.column('chave', sa.String()),
            sa.column('ordem', sa.Integer()), sa.column('ativo', sa.Boolean()),
            sa.column('criado_em', sa.DateTime()), sa.column('fazenda_id', sa.Integer()),
        )
        agora = datetime.utcnow()
        linhas = [
            {"tipo": "vacina", "nome": nome, "chave": chave, "ordem": ordem, "ativo": True, "criado_em": agora, "fazenda_id": None}
            for ordem, chave, nome in _ITENS_VACINA
        ] + [
            {"tipo": "exame", "nome": nome, "chave": chave, "ordem": ordem, "ativo": True, "criado_em": agora, "fazenda_id": None}
            for ordem, chave, nome in _ITENS_EXAME
        ]
        op.bulk_insert(checklist_template_item, linhas)

    if not insp.has_table('cronograma_sanitario_checklist_item'):
        op.create_table(
            'cronograma_sanitario_checklist_item',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('cronograma_id', sa.Integer(), nullable=False),
            sa.Column('chave', sa.String(), nullable=False),
            sa.Column('nome', sa.String(), nullable=False),
            sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('status', sa.String(), nullable=False, server_default='pendente'),
            sa.Column('resposta', sa.String(), nullable=True),
            sa.Column('observacao', sa.String(), nullable=True),
            sa.Column('responsavel_usuario_id', sa.Integer(), nullable=True),
            sa.Column('respondido_em', sa.DateTime(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['cronograma_id'], ['cronograma_sanitario.id']),
            sa.ForeignKeyConstraint(['responsavel_usuario_id'], ['usuario.id']),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            op.f('ix_cronograma_sanitario_checklist_item_cronograma_id'),
            'cronograma_sanitario_checklist_item', ['cronograma_id'],
        )
        op.create_index(
            op.f('ix_cronograma_sanitario_checklist_item_status'),
            'cronograma_sanitario_checklist_item', ['status'],
        )
        op.create_index(
            op.f('ix_cronograma_sanitario_checklist_item_fazenda_id'),
            'cronograma_sanitario_checklist_item', ['fazenda_id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_cronograma_sanitario_checklist_item_fazenda_id'),
        table_name='cronograma_sanitario_checklist_item',
    )
    op.drop_index(
        op.f('ix_cronograma_sanitario_checklist_item_status'),
        table_name='cronograma_sanitario_checklist_item',
    )
    op.drop_index(
        op.f('ix_cronograma_sanitario_checklist_item_cronograma_id'),
        table_name='cronograma_sanitario_checklist_item',
    )
    op.drop_table('cronograma_sanitario_checklist_item')

    op.drop_index(op.f('ix_checklist_template_item_fazenda_id'), table_name='checklist_template_item')
    op.drop_index(op.f('ix_checklist_template_item_tipo'), table_name='checklist_template_item')
    op.drop_table('checklist_template_item')
