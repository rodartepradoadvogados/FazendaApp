"""lancamento_anexo: comprovante de vale (vale_funcionario_id/vale_avulso_id)

Comprovante de pagamento de `ValeFuncionario`/`ValeAvulso` (Frente D da
sessão de ajustes de tela) reaproveita `LancamentoAnexo` — mesmo mecanismo
de Storage + metadados já usado pelos anexos de lançamento — em vez de uma
tabela nova. A diferença é o vínculo: um anexo "de lançamento" é achado por
`numero_lancamento` (ContaGerencial), mas nem todo vale tem um
ContaGerencial por trás (forma_pagamento "desconto_integral_folha" ou
"desconto_proximo_pagamento" não move caixa na hora — ver
`_sincronizar_conta_vale` em rh_folha.py) — por isso `numero_lancamento`
passa a ser OPCIONAL, e dois FKs novos (`vale_funcionario_id`,
`vale_avulso_id`, sempre nullable e mutuamente exclusivos entre si e com
`numero_lancamento`) cobrem o vínculo do anexo de vale. Ver
fazenda/api/routers/cadastro/rh_folha.py, rotas
/cadastro/vales/{tipo}/{id}/comprovante.

Revision ID: 2e06861217cc
Revises: d8f1a2c47b93
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e06861217cc'
down_revision: Union[str, Sequence[str], None] = 'd8f1a2c47b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('lancamento_anexo', sa.Column('vale_funcionario_id', sa.Integer(), nullable=True))
    op.add_column('lancamento_anexo', sa.Column('vale_avulso_id', sa.Integer(), nullable=True))
    op.create_index(
        op.f('ix_lancamento_anexo_vale_funcionario_id'), 'lancamento_anexo', ['vale_funcionario_id'], unique=False,
    )
    op.create_index(
        op.f('ix_lancamento_anexo_vale_avulso_id'), 'lancamento_anexo', ['vale_avulso_id'], unique=False,
    )
    # batch mode: SQLite (dev/testes) não suporta ALTER COLUMN/ADD CONSTRAINT
    # direto — precisa recriar a tabela por baixo dos panos; Postgres
    # (produção) ignora o batch e faz os comandos normais.
    with op.batch_alter_table('lancamento_anexo') as batch_op:
        batch_op.alter_column('numero_lancamento', existing_type=sa.String(), nullable=True)
        batch_op.create_foreign_key(
            'fk_lancamento_anexo_vale_funcionario_id', 'vale_funcionario', ['vale_funcionario_id'], ['id'],
        )
        batch_op.create_foreign_key(
            'fk_lancamento_anexo_vale_avulso_id', 'vale_avulso', ['vale_avulso_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('lancamento_anexo') as batch_op:
        batch_op.drop_constraint('fk_lancamento_anexo_vale_avulso_id', type_='foreignkey')
        batch_op.drop_constraint('fk_lancamento_anexo_vale_funcionario_id', type_='foreignkey')
        batch_op.alter_column('numero_lancamento', existing_type=sa.String(), nullable=False)
    op.drop_index(op.f('ix_lancamento_anexo_vale_avulso_id'), table_name='lancamento_anexo')
    op.drop_index(op.f('ix_lancamento_anexo_vale_funcionario_id'), table_name='lancamento_anexo')
    op.drop_column('lancamento_anexo', 'vale_avulso_id')
    op.drop_column('lancamento_anexo', 'vale_funcionario_id')
