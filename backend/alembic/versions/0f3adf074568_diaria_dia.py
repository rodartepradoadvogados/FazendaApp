"""diaria_dia: calendario esparso de dias trabalhados/folga por diaria

Rebuild da Diária para rastrear estado real por dia (trabalhado/folga) em vez
de presumir 100% trabalhado no intervalo de datas. `diaria_dia` guarda só as
EXCEÇÕES (dias marcados como folga) — sem linha para um dia = trabalhado.
`diaria.controle_por_dia_desde` é o marco: NULL mantém a diária 100% na
regra antiga (auditorias agregadas + ajuste manual + contagem cega); quando
o usuário salva o calendário pela 1ª vez, vira a data mais antiga já coberta
pelo envio, e dali em diante quem manda é `diaria_dia`. Ver
fazenda/models/pessoal.py::DiariaDia e
fazenda/api/routers/cadastro/rh_contratos.py::_resumo_diaria.

Também repara os dados de um bug real (Bug A): `_gerar_auditorias_diarias`
(agenda.py) criava `DiariaAuditoria` sem `fazenda_id`, fazendo qualquer
usuário com fazenda_id no token levar 404 ao tentar responder a auditoria —
UPDATE idempotente abaixo preenche o fazenda_id que faltou nas linhas já
gravadas, herdando da `diaria` pai.

Revision ID: 0f3adf074568
Revises: c4060566a25b
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f3adf074568'
down_revision: Union[str, Sequence[str], None] = 'c4060566a25b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'diaria_dia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('diaria_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('trabalhado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('registrado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['diaria_id'], ['diaria.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('diaria_id', 'data', name='uq_diaria_dia_diaria_data'),
    )
    op.create_index(op.f('ix_diaria_dia_diaria_id'), 'diaria_dia', ['diaria_id'])
    op.create_index(op.f('ix_diaria_dia_data'), 'diaria_dia', ['data'])
    op.create_index(op.f('ix_diaria_dia_fazenda_id'), 'diaria_dia', ['fazenda_id'])

    op.add_column('diaria', sa.Column('controle_por_dia_desde', sa.Date(), nullable=True))

    # Reparo de dados do Bug A (ver docstring acima): DiariaAuditoria criada
    # pela Agenda sem fazenda_id ficava eternamente 404 ao responder — ainda
    # que o app pare de errar dali pra frente, as linhas já gravadas seguiam
    # travadas até este reparo. `diaria_auditoria` é uma das tabelas sem
    # migração de criação própria (nasceu depois da adoção do Alembic, ver
    # a1b2c3d4e5f6) — num banco totalmente novo ela ainda não existe neste
    # ponto da cadeia (só nasce pelo `create_all` de segurança, chamado
    # depois do `upgrade head`), então o reparo só roda se a tabela já
    # existir.
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table('diaria_auditoria'):
        conn.execute(sa.text("""
            UPDATE diaria_auditoria
               SET fazenda_id = (SELECT d.fazenda_id FROM diaria d WHERE d.id = diaria_auditoria.diaria_id)
             WHERE fazenda_id IS NULL
        """))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_diaria_dia_fazenda_id'), table_name='diaria_dia')
    op.drop_index(op.f('ix_diaria_dia_data'), table_name='diaria_dia')
    op.drop_index(op.f('ix_diaria_dia_diaria_id'), table_name='diaria_dia')
    op.drop_table('diaria_dia')
    op.drop_column('diaria', 'controle_por_dia_desde')
