"""Encerramento cobravel da diaria + numero/valor contratado das parcelas

Revision ID: d4a1f6c2b9e7
Revises: 20ce5bb183b1
Create Date: 2026-09-06

Três buracos, um de cada vez.

1. DIÁRIA — encerrar o período de um diarista devendo dinheiro não gerava
   conta a pagar nenhuma. O trabalho ficava registrado em `diaria` e sumia do
   radar financeiro: nem Agenda, nem Contas a Pagar. As colunas novas de
   `diaria` são o que permite emitir essa conta (`numero_lancamento_gerado`,
   pela receita canônica do projeto) e CONGELAR o período no fechamento
   (`data_encerramento` + as cinco `encerramento_*`), para o valor cobrado
   não mudar sozinho depois de emitido.

   Migração ADITIVA, SEM BACKFILL de propósito: toda diária hoje marcada como
   "encerrado" fica com `data_encerramento` NULL, e é exatamente esse NULL que
   `_resumo_diaria` usa para manter o comportamento antigo (recalcular tudo)
   nesses registros. Inventar aqui um valor congelado para eles seria
   inventar um passado — não existe registro de QUANDO nem de QUANTO cada um
   desses períodos foi fechado.

2. PARCELA (empreitada/contrato) — `numero`/`numero_total`. A tela numerava
   pela posição na lista ordenada por vencimento, então excluir a parcela 3
   de 5 fazia a 4 virar "3": todo recibo já impresso passava a apontar para
   outra parcela. Backfill: numera as parcelas EXISTENTES na mesma ordem que
   a tela já usava (vencimento, id) — o que ela mostra hoje continua valendo,
   só que a partir de agora congelado.

   O que o backfill NÃO recupera: parcela excluída ANTES desta migração. Se a
   empreitada nasceu com 5 parcelas e a 3 foi excluída, as 4 restantes serão
   numeradas 1..4 de 4, não 1, 2, 4, 5 de 5 — o buraco daquela exclusão é
   irrecuperável, porque a linha excluída não deixou rastro em lugar nenhum.
   Vale só para o passado; toda exclusão daqui em diante preserva o buraco.

3. PARCELA — `valor_contratado` (o bruto acordado, antes dos vales
   adiantados). Backfill pelo melhor valor possível:
   `valor_contratado = valor + Σ vale_avulso_abatimento.valor_abatido`.

   O que o backfill NÃO recupera:
   - Parcela que passou por REDISTRIBUIÇÃO depois de um vale: a
     redistribuição reescreve `valor` sem tocar nos abatimentos, então a soma
     acima devolve um bruto que nunca foi acordado. O total da empreitada
     continua certo; a divisão por parcela, não. (É justamente por isso que
     `valor_contratado` passa a ser um campo persistido em vez de conta
     feita na hora.)
   - Parcela editada à mão (`PUT /empreitadas|contratos/parcelas/{id}`) sem
     vale nenhum: o bruto original foi sobrescrito e não existe mais em
     lugar algum; o backfill grava o valor atual, que é o único dado que
     sobrou.
   Nos dois casos o resultado é o melhor palpite disponível, e nenhum deles
   piora o que a tela mostra hoje (que não mostrava bruto nenhum).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a1f6c2b9e7"
down_revision: Union[str, Sequence[str], None] = "20ce5bb183b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUNAS_DIARIA = [
    ("data_encerramento", sa.Date()),
    ("numero_lancamento_gerado", sa.String()),
    ("encerramento_numero_diarias", sa.Float()),
    ("encerramento_total_apurado", sa.Float()),
    ("encerramento_valor_pago", sa.Float()),
    ("encerramento_valor_vale", sa.Float()),
    ("encerramento_saldo_devedor", sa.Float()),
]

# (tabela da parcela, coluna do pai, item_tipo em vale_avulso_abatimento)
TABELAS_PARCELA = [
    ("empreitada_parcela", "empreitada_id", "empreitada_parcela"),
    ("contrato_parcela", "contrato_id", "contrato_parcela"),
]


def _backfill_parcelas(conexao, tabela: str, coluna_pai: str, item_tipo: str) -> None:
    """Numera as parcelas existentes (1..n por pai, na ordem que a tela já
    usava) e reconstrói o bruto contratado somando os abatimentos de vale
    registrados para cada uma. Feito em Python, e não com `row_number()`,
    para não depender da versão do SQLite do ambiente de dev."""
    abatido_por_item: dict[int, float] = {}
    for item_id, valor in conexao.execute(
        sa.text(
            "SELECT item_id, COALESCE(SUM(valor_abatido), 0) FROM vale_avulso_abatimento "
            "WHERE item_tipo = :tipo GROUP BY item_id"
        ),
        {"tipo": item_tipo},
    ).fetchall():
        abatido_por_item[item_id] = float(valor or 0)

    linhas = conexao.execute(
        sa.text(
            f"SELECT id, {coluna_pai}, valor FROM {tabela} ORDER BY {coluna_pai}, data_vencimento, id"
        )
    ).fetchall()

    por_pai: dict[int, list] = {}
    for parcela_id, pai_id, valor in linhas:
        por_pai.setdefault(pai_id, []).append((parcela_id, float(valor or 0)))

    sql = sa.text(
        f"UPDATE {tabela} SET numero = :numero, numero_total = :total, valor_contratado = :bruto WHERE id = :id"
    )
    for _pai_id, parcelas in por_pai.items():
        total = len(parcelas)
        for posicao, (parcela_id, valor) in enumerate(parcelas, start=1):
            bruto = round(valor + abatido_por_item.get(parcela_id, 0.0), 2)
            conexao.execute(sql, {"numero": posicao, "total": total, "bruto": bruto, "id": parcela_id})


def upgrade() -> None:
    """Upgrade schema."""
    for nome, tipo in COLUNAS_DIARIA:
        op.add_column("diaria", sa.Column(nome, tipo, nullable=True))

    for tabela, _coluna_pai, _item_tipo in TABELAS_PARCELA:
        op.add_column(tabela, sa.Column("numero", sa.Integer(), nullable=True))
        op.add_column(tabela, sa.Column("numero_total", sa.Integer(), nullable=True))
        op.add_column(tabela, sa.Column("valor_contratado", sa.Float(), nullable=True))

    conexao = op.get_bind()
    for tabela, coluna_pai, item_tipo in TABELAS_PARCELA:
        _backfill_parcelas(conexao, tabela, coluna_pai, item_tipo)


def downgrade() -> None:
    """Downgrade schema."""
    for tabela, _coluna_pai, _item_tipo in TABELAS_PARCELA:
        op.drop_column(tabela, "valor_contratado")
        op.drop_column(tabela, "numero_total")
        op.drop_column(tabela, "numero")
    for nome, _tipo in reversed(COLUNAS_DIARIA):
        op.drop_column("diaria", nome)
