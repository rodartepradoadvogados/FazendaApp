"""Snapshot de salario, abono persistido e parcela real do 13o

Revision ID: e0b7c3a91d24
Revises: d4a1f6c2b9e7
Create Date: 2026-09-06

Quatro buracos de dinheiro no módulo de Férias/13º, todos resolvidos por
colunas que faltavam.

1. SNAPSHOT DO SALÁRIO (`ferias_funcionario.salario_base`,
   `decimo_terceiro.salario_base`). O PUT desses dois endpoints — que é o
   que o botão "Marcar como pago" da tela dispara — recalculava o valor a
   partir do `pessoa.salario_base` de HOJE e sobrescrevia a conta a pagar em
   silêncio. Férias lançadas em janeiro por R$ 2.666,67 (salário R$ 2.000)
   viravam R$ 4.000 em março se o salário tivesse subido no cadastro.
   `RescisaoFuncionario.salario_base` já fazia certo desde sempre; estas duas
   tabelas ficaram para trás.

   Backfill EXATO, por inversão da própria fórmula do cálculo:
   - férias: `salario_base = valor_ferias / dias_gozados × 30`
     (`calcular_ferias`: valor_ferias = salario/30 × dias_gozados);
   - 13º: `salario_base = valor_bruto × 12 / meses_trabalhados`
     (`calcular_decimo_terceiro`: salario/12 × meses).
   Fica NULL só onde a divisão é impossível (dias_gozados/meses zerados ou
   nulos, que não deveria existir mas não custa não explodir) — e nesse caso
   os endpoints voltam a usar o salário atual, como faziam antes.

2. ABONO PECUNIÁRIO PERSISTIDO (`ferias_funcionario.valor_abono`).
   `calcular_ferias` devolvia `valor_abono`, ele entrava em `valor_total`, e
   o POST simplesmente descartava o campo: no banco,
   `valor_ferias + valor_terco_constitucional != valor_total` sempre que
   havia venda de dias, sem nenhuma coluna que explicasse a diferença.

   Backfill: `valor_abono = valor_total − valor_ferias −
   valor_terco_constitucional` — a mesma subtração que o recibo já fazia na
   hora de montar a linha, agora gravada de uma vez.

3. PARCELA REAL DO 13º (`decimo_terceiro.valor_integral`). Era o defeito
   mais caro: `valor_bruto` guardava o 13º CHEIO para "unica", "primeira" e
   "segunda" — a parcela só mudava o rótulo e o vencimento. Lançar 1ª + 2ª
   parcela de um salário de R$ 3.000 punha R$ 6.000 em Contas a Pagar.
   Agora `valor_integral` é o 13º do ano e `valor_bruto` é o que se paga
   NESTA parcela (até 50% na 1ª — adiantamento, Lei 4.749/1965, art. 2º; o
   saldo na 2ª/única).

   Backfill CONSERVADOR: `valor_integral = valor_bruto` em todas as linhas
   existentes, porque é exatamente o que elas guardam hoje. Os valores JÁ
   LANÇADOS não são mexidos — inclusive os dobrados. Corrigir aqui
   significaria reescrever conta a pagar (algumas já pagas) a partir de uma
   suposição sobre qual das duas linhas o dono considerou certa, e isso é
   decisão dele, na tela, lançamento a lançamento. A migração só para a
   hemorragia daqui pra frente.

4. CANCELAMENTO POR RESCISÃO (`status` novo + `rescisao_id` nas duas
   tabelas). Férias/13º pendentes sobreviviam à rescisão: o 13º de 2026
   lançado em novembro continuava como conta a pagar de 20/12 mesmo depois
   de a rescisão de 10/12 ser fechada JÁ COM o 13º proporcional dentro.
   `rescisao_id` é a coluna que torna o cancelamento rastreável e reversível
   — o registro nunca é apagado, só marcado.

   Sem backfill: não há como saber, olhando para trás, qual férias/13º
   pendente foi ou não pago à parte da rescisão já fechada. Vale só para
   fechamentos daqui em diante.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e0b7c3a91d24"
down_revision: Union[str, Sequence[str], None] = "d4a1f6c2b9e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUNAS_FERIAS = [
    ("salario_base", sa.Float()),
    ("valor_abono", sa.Float()),
    ("rescisao_id", sa.Integer()),
]

COLUNAS_DECIMO = [
    ("salario_base", sa.Float()),
    ("valor_integral", sa.Float()),
    ("rescisao_id", sa.Integer()),
]


def upgrade() -> None:
    """Upgrade schema."""
    for nome, tipo in COLUNAS_FERIAS:
        op.add_column("ferias_funcionario", sa.Column(nome, tipo, nullable=True))
    for nome, tipo in COLUNAS_DECIMO:
        op.add_column("decimo_terceiro", sa.Column(nome, tipo, nullable=True))

    conexao = op.get_bind()

    # Férias — salário reconstituído pela inversão de `calcular_ferias` e
    # abono pela diferença que já estava implícita no total gravado.
    conexao.execute(sa.text(
        "UPDATE ferias_funcionario SET salario_base = "
        "ROUND(valor_ferias * 30.0 / dias_gozados, 2) "
        "WHERE salario_base IS NULL AND dias_gozados IS NOT NULL AND dias_gozados > 0"
    ))
    conexao.execute(sa.text(
        "UPDATE ferias_funcionario SET valor_abono = ROUND("
        "COALESCE(valor_total, 0) - COALESCE(valor_ferias, 0) "
        "- COALESCE(valor_terco_constitucional, 0), 2) "
        "WHERE valor_abono IS NULL"
    ))
    # Ruído de arredondamento das somas antigas não vira "abono de 1 centavo".
    conexao.execute(sa.text(
        "UPDATE ferias_funcionario SET valor_abono = 0 "
        "WHERE valor_abono IS NOT NULL AND ("
        "abono_pecuniario_dias IS NULL OR abono_pecuniario_dias = 0 OR valor_abono < 0)"
    ))

    # 13º — ver item 3 da docstring: `valor_integral` recebe o que já está
    # gravado, sem reescrever nenhum valor lançado.
    conexao.execute(sa.text(
        "UPDATE decimo_terceiro SET valor_integral = valor_bruto WHERE valor_integral IS NULL"
    ))
    conexao.execute(sa.text(
        "UPDATE decimo_terceiro SET salario_base = "
        "ROUND(valor_bruto * 12.0 / meses_trabalhados, 2) "
        "WHERE salario_base IS NULL AND meses_trabalhados IS NOT NULL AND meses_trabalhados > 0"
    ))


def downgrade() -> None:
    """Downgrade schema."""
    for nome, _tipo in reversed(COLUNAS_DECIMO):
        op.drop_column("decimo_terceiro", nome)
    for nome, _tipo in reversed(COLUNAS_FERIAS):
        op.drop_column("ferias_funcionario", nome)
