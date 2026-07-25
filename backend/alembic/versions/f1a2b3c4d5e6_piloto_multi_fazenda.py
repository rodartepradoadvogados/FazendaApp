"""piloto conservador de multi-fazenda

Revision ID: f1a2b3c4d5e6
Revises: a3f7c9d1e246
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'a3f7c9d1e246'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Tabelas novas e isoladas — não alteram nenhuma tabela de domínio já
    # existente. Ver fazenda/models/multitenant.py.
    op.create_table(
        'fazenda',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('cidade', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('uf', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('ativa', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'usuario_fazenda',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('usuario_id', 'fazenda_id', name='uq_usuario_fazenda'),
    )
    op.create_index(op.f('ix_usuario_fazenda_usuario_id'), 'usuario_fazenda', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_usuario_fazenda_fazenda_id'), 'usuario_fazenda', ['fazenda_id'], unique=False)

    # animal.fazenda_id: coluna NULLABLE e aditiva — nenhum código existente
    # precisa dela para continuar funcionando; só os endpoints já preparados
    # (ver fazenda/api/routers/animais.py e cadastro/animais.py) passam a
    # ler/gravar este campo quando o login carrega uma fazenda selecionada.
    # Sem constraint de FK real na coluna (SQLite não altera constraints in
    # place; mesmo padrão já usado nas demais colunas soft-FK do sistema,
    # onde o vínculo é garantido pelo SQLModel/Python, não pelo banco).
    op.add_column('animal', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_animal_fazenda_id'), 'animal', ['fazenda_id'], unique=False)

    # Seed + backfill: cria a fazenda real (mesmo nome fixo que já aparecia
    # embaixo do logo CowData hoje — "Jairo Nasser" — para não mudar NADA
    # visualmente pra quem já usa o sistema), vincula TODOS os usuários já
    # cadastrados a ela, e carimba fazenda_id em todo animal já existente.
    # Depois disto, todo mundo que já tinha login continua com exatamente 1
    # fazenda vinculada — login auto-seleciona, sem tela nova, sem filtro
    # extra visível (ver fazenda/api/routers/auth.py::login).
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO fazenda (nome, ativa, criado_em) VALUES (:nome, true, CURRENT_TIMESTAMP)"
    ), {"nome": "Jairo Nasser"})
    fazenda_id = conn.execute(sa.text("SELECT id FROM fazenda WHERE nome = :nome ORDER BY id DESC LIMIT 1"), {"nome": "Jairo Nasser"}).scalar()
    conn.execute(sa.text(
        "INSERT INTO usuario_fazenda (usuario_id, fazenda_id, criado_em) "
        "SELECT id, :fazenda_id, CURRENT_TIMESTAMP FROM usuario"
    ), {"fazenda_id": fazenda_id})
    conn.execute(sa.text("UPDATE animal SET fazenda_id = :fazenda_id"), {"fazenda_id": fazenda_id})


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_animal_fazenda_id'), table_name='animal')
    op.drop_column('animal', 'fazenda_id')
    op.drop_index(op.f('ix_usuario_fazenda_fazenda_id'), table_name='usuario_fazenda')
    op.drop_index(op.f('ix_usuario_fazenda_usuario_id'), table_name='usuario_fazenda')
    op.drop_table('usuario_fazenda')
    op.drop_table('fazenda')
