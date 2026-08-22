"""lactacao: a entidade que faltava (+ backfill a partir dos partos)

Cria a tabela `lactacao` e reconstrói o histórico dela a partir do que já
existe no banco.

## Por que a tabela existe

O sistema não tinha lactação: cada tela inferia "está em lactação" de um
jeito (existir um `Parto`, `Animal.del_dias > 0`, o código do lote ser
01/02/03) e as inferências discordavam entre si. O sintoma que originou a
correção: uma matriz com aborto lançado — que no caminho antigo não gerava
`Parto` nenhum — continuava na Ficha como "novilha gestante, sem parto"
mesmo já estando no lote de lactação e com controle leiteiro lançado.

Ver `fazenda/models/producao.py::Lactacao` e `fazenda/rules/lactacao.py`.

## O backfill

Uma `Lactacao` por `Parto` PRODUTIVO já gravado (aborto importado não gera —
ver a justificativa em `rules.lactacao.backfill_lactacoes`), com
`data_inicio` = data do parto, `origem = "importacao"`, fechada pela
`Secagem` seguinte daquele animal ou pelo parto seguinte, o que vier
primeiro. Tudo determinístico a partir dos dados existentes — nenhuma data
inventada.

Idempotente: reexecutar não duplica (a abertura reaproveita por matriz +
data de início).

Revision ID: c1a2b3d4e5f6
Revises: b7c04e91d2af
Create Date: 2026-08-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'b7c04e91d2af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if 'lactacao' not in insp.get_table_names():
        op.create_table(
            'lactacao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('animal_id', sa.Integer(), nullable=True),
            sa.Column('numero_matriz', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('data_inicio', sa.Date(), nullable=False),
            sa.Column('origem', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('parto_id', sa.Integer(), nullable=True),
            sa.Column('numero_lactacao', sa.Integer(), nullable=False),
            sa.Column('data_fim', sa.Date(), nullable=True),
            sa.Column('secagem_id', sa.Integer(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.ForeignKeyConstraint(['animal_id'], ['animal.id']),
            sa.ForeignKeyConstraint(['parto_id'], ['parto.id']),
            sa.ForeignKeyConstraint(['secagem_id'], ['secagem.id']),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_lactacao_fazenda_id'), 'lactacao', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_lactacao_animal_id'), 'lactacao', ['animal_id'], unique=False)
        op.create_index(op.f('ix_lactacao_numero_matriz'), 'lactacao', ['numero_matriz'], unique=False)
        op.create_index(op.f('ix_lactacao_data_inicio'), 'lactacao', ['data_inicio'], unique=False)
        op.create_index(op.f('ix_lactacao_data_fim'), 'lactacao', ['data_fim'], unique=False)
        op.create_index(op.f('ix_lactacao_parto_id'), 'lactacao', ['parto_id'], unique=False)
        op.create_index(op.f('ix_lactacao_secagem_id'), 'lactacao', ['secagem_id'], unique=False)

    _backfill(conn)


def _backfill(conn) -> None:
    """Reconstrói as lactações a partir dos partos/secagens já gravados.

    Reaproveita `fazenda.rules.lactacao.backfill_lactacoes` — a MESMA função
    que o app pode reexecutar depois de uma importação de CSV — em vez de
    reescrever a regra em SQL aqui. Duas implementações da mesma
    reconstrução divergiriam no primeiro ajuste feito só de um lado.
    """
    from sqlmodel import Session

    from fazenda.rules.lactacao import backfill_lactacoes

    with Session(bind=conn) as session:
        backfill_lactacoes(session)
        session.flush()
        # Sem `session.commit()`: a conexão é a da própria transação do
        # Alembic (`op.get_bind()`), que ele commita ao fim da migração.
        # Commitar aqui encerraria a transação por baixo do Alembic.


def downgrade() -> None:
    op.drop_index(op.f('ix_lactacao_secagem_id'), table_name='lactacao')
    op.drop_index(op.f('ix_lactacao_parto_id'), table_name='lactacao')
    op.drop_index(op.f('ix_lactacao_data_fim'), table_name='lactacao')
    op.drop_index(op.f('ix_lactacao_data_inicio'), table_name='lactacao')
    op.drop_index(op.f('ix_lactacao_numero_matriz'), table_name='lactacao')
    op.drop_index(op.f('ix_lactacao_animal_id'), table_name='lactacao')
    op.drop_index(op.f('ix_lactacao_fazenda_id'), table_name='lactacao')
    op.drop_table('lactacao')
