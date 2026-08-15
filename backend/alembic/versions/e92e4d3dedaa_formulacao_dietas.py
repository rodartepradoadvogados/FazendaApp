"""Formulação de Dietas — biblioteca nutricional, simulações e vínculo com dieta lançada

Módulo novo (motor NASEM/NRC Dairy 2021, wizard de 10 etapas — ver
fazenda/rules/nutricao/ e fazenda/api/routers/formulacao_dietas.py). Três
tabelas novas, todas com fazenda_id OBRIGATÓRIO (sem retrocompatibilidade a
acomodar, diferente do resto do repo) + uma coluna nova em dieta_lancamento
para rastrear "esta dieta veio de uma simulação aplicada".

Revision ID: e92e4d3dedaa
Revises: 680c43957617
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e92e4d3dedaa'
down_revision: Union[str, Sequence[str], None] = '680c43957617'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'alimento_nutricional',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
        sa.Column('alimento_id', sa.Integer(), sa.ForeignKey('alimento.id'), nullable=True),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('categoria_nasem', sa.String(), nullable=False),
        sa.Column('conc_pct', sa.Float(), nullable=False),
        sa.Column('fonte', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('ms_pct', sa.Float(), nullable=True),
        sa.Column('pb_pct', sa.Float(), nullable=True),
        sa.Column('fdn_pct', sa.Float(), nullable=True),
        sa.Column('fda_pct', sa.Float(), nullable=True),
        sa.Column('lignina_pct', sa.Float(), nullable=True),
        sa.Column('amido_pct', sa.Float(), nullable=True),
        sa.Column('acucares_pct', sa.Float(), nullable=True),
        sa.Column('ee_pct', sa.Float(), nullable=True),
        sa.Column('ag_pct', sa.Float(), nullable=True),
        sa.Column('cinzas_pct', sa.Float(), nullable=True),
        sa.Column('dndf48_fdn_pct', sa.Float(), nullable=True),
        sa.Column('pb_a_pct', sa.Float(), nullable=True),
        sa.Column('pb_b_pct', sa.Float(), nullable=True),
        sa.Column('pb_c_pct', sa.Float(), nullable=True),
        sa.Column('kd_pb_b_pct_h', sa.Float(), nullable=True),
        sa.Column('nnp_pb_pct', sa.Float(), nullable=True),
        sa.Column('pidn_pct', sa.Float(), nullable=True),
        sa.Column('pida_pct', sa.Float(), nullable=True),
        sa.Column('dig_amido_pct', sa.Float(), nullable=True),
        sa.Column('dig_pndr_pct', sa.Float(), nullable=True),
        sa.Column('dig_ag_pct', sa.Float(), nullable=True),
        sa.Column('ca_pct', sa.Float(), nullable=True),
        sa.Column('p_pct', sa.Float(), nullable=True),
        sa.Column('p_inorg_p_pct', sa.Float(), nullable=True),
        sa.Column('p_org_p_pct', sa.Float(), nullable=True),
        sa.Column('mg_pct', sa.Float(), nullable=True),
        sa.Column('k_pct', sa.Float(), nullable=True),
        sa.Column('na_pct', sa.Float(), nullable=True),
        sa.Column('cl_pct', sa.Float(), nullable=True),
        sa.Column('s_pct', sa.Float(), nullable=True),
        sa.Column('abs_ca', sa.Float(), nullable=True),
        sa.Column('abs_p_total', sa.Float(), nullable=True),
        sa.Column('abs_mg', sa.Float(), nullable=True),
        sa.Column('abs_na', sa.Float(), nullable=True),
        sa.Column('abs_cl', sa.Float(), nullable=True),
        sa.Column('abs_k', sa.Float(), nullable=True),
        sa.Column('custo_kg_mn', sa.Float(), nullable=True),
        sa.Column('extras_json', sa.Text(), nullable=True),
        sa.UniqueConstraint('alimento_id', 'fazenda_id', name='uq_alimento_nutricional_alimento_fazenda'),
    )
    op.create_index('ix_alimento_nutricional_fazenda_id', 'alimento_nutricional', ['fazenda_id'])
    op.create_index('ix_alimento_nutricional_alimento_id', 'alimento_nutricional', ['alimento_id'])
    op.create_index('ix_alimento_nutricional_nome', 'alimento_nutricional', ['nome'])

    op.create_table(
        'dieta_simulacao',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('lote', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('etapa_atual', sa.Integer(), nullable=False),
        sa.Column('estado_fisiologico', sa.String(), nullable=False),
        sa.Column('raca', sa.String(), nullable=False),
        sa.Column('peso_vivo_kg', sa.Float(), nullable=False),
        sa.Column('peso_maturo_kg', sa.Float(), nullable=False),
        sa.Column('ecc', sa.Float(), nullable=False),
        sa.Column('paridade', sa.Float(), nullable=False),
        sa.Column('idade_dias', sa.Integer(), nullable=True),
        sa.Column('del_dias', sa.Integer(), nullable=True),
        sa.Column('dias_gestacao', sa.Integer(), nullable=True),
        sa.Column('duracao_gestacao_dias', sa.Integer(), nullable=False),
        sa.Column('peso_bezerro_nascer_kg', sa.Float(), nullable=False),
        sa.Column('del_concepcao', sa.Integer(), nullable=True),
        sa.Column('idade_concepcao_1a_dias', sa.Integer(), nullable=True),
        sa.Column('ganho_estrutura_kg_dia', sa.Float(), nullable=False),
        sa.Column('ganho_reserva_kg_dia', sa.Float(), nullable=False),
        sa.Column('producao_leite_kg_dia', sa.Float(), nullable=True),
        sa.Column('gordura_leite_pct', sa.Float(), nullable=True),
        sa.Column('proteina_leite_pct', sa.Float(), nullable=True),
        sa.Column('lactose_leite_pct', sa.Float(), nullable=False),
        sa.Column('potencial_genetico_pl_305', sa.Float(), nullable=False),
        sa.Column('temperatura_c', sa.Float(), nullable=False),
        sa.Column('distancia_sala_m', sa.Float(), nullable=False),
        sa.Column('viagens_sala_dia', sa.Integer(), nullable=False),
        sa.Column('desnivel_diario_m', sa.Float(), nullable=False),
        sa.Column('eq_cms', sa.Integer(), nullable=False),
        sa.Column('cms_informado_kg_dia', sa.Float(), nullable=True),
        sa.Column('usa_monensina', sa.Boolean(), nullable=False),
        sa.Column('eq_microbiana', sa.Integer(), nullable=False),
        sa.Column('usa_dndf48', sa.Integer(), nullable=False),
        sa.Column('motor_versao', sa.String(), nullable=True),
        sa.Column('calculado_em', sa.DateTime(), nullable=True),
        sa.Column('resultado_json', sa.Text(), nullable=True),
        sa.Column('avisos_json', sa.Text(), nullable=True),
        sa.Column('dieta_lancamento_id', sa.Integer(), sa.ForeignKey('dieta_lancamento.id'), nullable=True),
        sa.Column('aplicada_em', sa.DateTime(), nullable=True),
        sa.Column('aplicada_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
    )
    op.create_index('ix_dieta_simulacao_fazenda_id', 'dieta_simulacao', ['fazenda_id'])
    op.create_index('ix_dieta_simulacao_nome', 'dieta_simulacao', ['nome'])
    op.create_index('ix_dieta_simulacao_lote', 'dieta_simulacao', ['lote'])
    op.create_index('ix_dieta_simulacao_status', 'dieta_simulacao', ['status'])

    op.create_table(
        'dieta_simulacao_item',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
        sa.Column('simulacao_id', sa.Integer(), sa.ForeignKey('dieta_simulacao.id'), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False),
        sa.Column('alimento_id', sa.Integer(), sa.ForeignKey('alimento.id'), nullable=True),
        sa.Column('alimento_nutricional_id', sa.Integer(), sa.ForeignKey('alimento_nutricional.id'), nullable=True),
        sa.Column('analise_bromatologica_id', sa.Integer(), sa.ForeignKey('analise_bromatologica.id'), nullable=True),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('origem', sa.String(), nullable=False),
        sa.Column('proporcao_ms_pct', sa.Float(), nullable=False),
        sa.Column('categoria_nasem', sa.String(), nullable=False),
        sa.Column('conc_pct', sa.Float(), nullable=False),
        sa.Column('ms_pct', sa.Float(), nullable=True),
        sa.Column('custo_kg_mn', sa.Float(), nullable=True),
        sa.Column('valores_json', sa.Text(), nullable=False),
        sa.Column('campos_editados_json', sa.Text(), nullable=True),
    )
    op.create_index('ix_dieta_simulacao_item_fazenda_id', 'dieta_simulacao_item', ['fazenda_id'])
    op.create_index('ix_dieta_simulacao_item_simulacao_id', 'dieta_simulacao_item', ['simulacao_id'])

    op.add_column('dieta_lancamento', sa.Column('dieta_simulacao_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('dieta_lancamento') as batch_op:
        batch_op.create_foreign_key(
            'fk_dieta_lancamento_dieta_simulacao_id', 'dieta_simulacao', ['dieta_simulacao_id'], ['id'],
        )
    op.create_index('ix_dieta_lancamento_dieta_simulacao_id', 'dieta_lancamento', ['dieta_simulacao_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_dieta_lancamento_dieta_simulacao_id', table_name='dieta_lancamento')
    with op.batch_alter_table('dieta_lancamento') as batch_op:
        batch_op.drop_constraint('fk_dieta_lancamento_dieta_simulacao_id', type_='foreignkey')
    op.drop_column('dieta_lancamento', 'dieta_simulacao_id')

    op.drop_index('ix_dieta_simulacao_item_simulacao_id', table_name='dieta_simulacao_item')
    op.drop_index('ix_dieta_simulacao_item_fazenda_id', table_name='dieta_simulacao_item')
    op.drop_table('dieta_simulacao_item')

    op.drop_index('ix_dieta_simulacao_status', table_name='dieta_simulacao')
    op.drop_index('ix_dieta_simulacao_lote', table_name='dieta_simulacao')
    op.drop_index('ix_dieta_simulacao_nome', table_name='dieta_simulacao')
    op.drop_index('ix_dieta_simulacao_fazenda_id', table_name='dieta_simulacao')
    op.drop_table('dieta_simulacao')

    op.drop_index('ix_alimento_nutricional_nome', table_name='alimento_nutricional')
    op.drop_index('ix_alimento_nutricional_alimento_id', table_name='alimento_nutricional')
    op.drop_index('ix_alimento_nutricional_fazenda_id', table_name='alimento_nutricional')
    op.drop_table('alimento_nutricional')
