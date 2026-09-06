"""folha_rubrica: vencimentos e descontos acrescentados ao holerite, com a
natureza (salarial × indenizatória) de cada rubrica

A folha só tinha dois campos livres de dinheiro — `valor_bruto` e `descontos`
(um float solto, sem itemização). Não havia onde lançar bonificação por
produtividade, aumento na folha, gueltas, indenização, reembolso, nem um
desconto associado a uma compra já realizada: ou o valor era somado à mão ao
salário bruto — e aí entrava nas bases de INSS/IRRF/FGTS mesmo quando é
indenizatório, o que faz o funcionário contribuir sobre dinheiro que só está
sendo devolvido a ele — ou ficava fora do documento.

A coluna `natureza` (mais `incide_inss`/`incide_irrf`/`incide_fgts`) é o que
torna o cálculo correto possível, e vai COPIADA do catálogo para cada linha:
o holerite é prova, e um recibo já emitido não pode mudar de conteúdo porque
o catálogo mudou depois (mesma regra de `RescisaoFuncionario.salario_base` e
de `folha_pagamento.discriminacao_congelada`). Ver
fazenda/models/folha_rubrica.py e fazenda/rules/rubrica_folha.py.

As duas colunas novas em `folha_pagamento` são cache do que as rubricas
somam: `valor_rubricas` (vencimentos − descontos) mantém a fórmula do líquido
num lugar só — sem ela, todo self-heal que recalcula o líquido apagaria em
silêncio o acréscimo lançado — e `valor_rubricas_tributaveis` é a parcela
SALARIAL, a que muda a base das retenções. Ambas com default no servidor:
folha já existente nasce com 0.0, que é exatamente "nenhuma rubrica".

Revision ID: b7d41f6a2c93
Revises: a1c4e7b93f52
Create Date: 2026-09-06 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d41f6a2c93'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7b93f52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'folha_rubrica',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('folha_id', sa.Integer(), nullable=False),
        sa.Column('pessoa_id', sa.Integer(), nullable=False),
        sa.Column('competencia', sa.String(), nullable=False),
        sa.Column('especie', sa.String(), nullable=False),
        sa.Column('codigo', sa.String(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=True),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('natureza', sa.String(), nullable=False),
        sa.Column('incide_inss', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('incide_irrf', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('incide_fgts', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('incorpora_base', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('conta_gerencial_id', sa.Integer(), nullable=True),
        sa.Column('numero_lancamento', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['folha_id'], ['folha_pagamento.id']),
        sa.ForeignKeyConstraint(['pessoa_id'], ['pessoa.id']),
        sa.ForeignKeyConstraint(['conta_gerencial_id'], ['conta_gerencial.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_folha_rubrica_fazenda_id'), 'folha_rubrica', ['fazenda_id'])
    op.create_index(op.f('ix_folha_rubrica_folha_id'), 'folha_rubrica', ['folha_id'])
    op.create_index(op.f('ix_folha_rubrica_pessoa_id'), 'folha_rubrica', ['pessoa_id'])
    op.create_index(op.f('ix_folha_rubrica_competencia'), 'folha_rubrica', ['competencia'])
    # `pessoa_id + competencia` é a varredura de `aumento_incorporado`, que
    # roda em TODA listagem de folha (dentro da geração por recorrência) —
    # sem este índice a incorporação do aumento custaria um seq scan por
    # modelo recorrente, toda vez que a tela abre.
    op.create_index(
        'ix_folha_rubrica_pessoa_competencia', 'folha_rubrica', ['pessoa_id', 'competencia'],
    )

    op.add_column('folha_pagamento', sa.Column(
        'valor_rubricas', sa.Float(), nullable=False, server_default='0',
    ))
    op.add_column('folha_pagamento', sa.Column(
        'valor_rubricas_tributaveis', sa.Float(), nullable=False, server_default='0',
    ))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('folha_pagamento', 'valor_rubricas_tributaveis')
    op.drop_column('folha_pagamento', 'valor_rubricas')
    op.drop_index('ix_folha_rubrica_pessoa_competencia', table_name='folha_rubrica')
    op.drop_index(op.f('ix_folha_rubrica_competencia'), table_name='folha_rubrica')
    op.drop_index(op.f('ix_folha_rubrica_pessoa_id'), table_name='folha_rubrica')
    op.drop_index(op.f('ix_folha_rubrica_folha_id'), table_name='folha_rubrica')
    op.drop_index(op.f('ix_folha_rubrica_fazenda_id'), table_name='folha_rubrica')
    op.drop_table('folha_rubrica')
