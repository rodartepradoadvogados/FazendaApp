"""Corrige a dose truncada na descricao das aplicacoes de inducao de lactacao

Revision ID: 7a2b67d909e8
Revises: 810153450ce9
Create Date: 2026-08-11

Até ago/2026, `_descricao_medicamentos_dia` (fazenda/api/routers/producao.py)
montava o texto do medicamento com `f"{dose:g}".rstrip("0").rstrip(".")`. O
`:g` já entrega "30" para 30.0; o `.rstrip("0")` seguinte comia o zero
SIGNIFICATIVO e gravava "3". Toda dose múltipla de 10 saiu errada: 30→3,
20→2, 10→1, 100→1.

Esse texto é PERSISTIDO em `protocolo_inducao_aplicacao.descricao` no momento
do lançamento e nunca é recalculado depois — corrigir só o código conserta
lançamentos futuros e deixa os antigos mostrando a dose errada para sempre
na Agenda e no card do app. Daí esta migração de dados.

A reconstrução sai de `protocolo_inducao_medicamento`, que guarda a dose
NUMÉRICA (30.0) e nunca passou pelo formatador quebrado — é a fonte
confiável. Corrigir por regex no texto seria ambíguo: "3 ml" pode ter sido
3, 30 ou 300, e não dá para saber olhando só a string.

Só o texto estava errado. A baixa de estoque sempre usou o campo numérico
(ver agenda.py), então nenhum saldo precisa de acerto.
"""
from alembic import op
import sqlalchemy as sa

revision = "7a2b67d909e8"
down_revision = "810153450ce9"
branch_labels = None
depends_on = None


def _formatar_dose(dose) -> str:
    """Mesma regra de `_descricao_medicamentos_dia` DEPOIS da correção —
    duplicada aqui de propósito: migração não importa código de aplicação,
    que pode mudar de forma e quebrar a reprodutibilidade histórica."""
    return f"{dose:g}" if isinstance(dose, float) else str(dose)


def upgrade() -> None:
    conexao = op.get_bind()

    # Ordem por id reproduz a ordem em que as linhas foram inseridas no
    # lançamento, que é a mesma ordem das etapas do dia — é ela que define
    # a sequência do " + " no texto original.
    medicamentos = conexao.execute(
        sa.text(
            "SELECT lancamento_id, dia, produto, dose, unidade "
            "FROM protocolo_inducao_medicamento ORDER BY id"
        )
    ).fetchall()

    por_dia: dict[tuple, list] = {}
    for lancamento_id, dia, produto, dose, unidade in medicamentos:
        por_dia.setdefault((lancamento_id, dia), []).append((produto, dose, unidade))

    # `IS DISTINCT FROM` não existe em SQLite antigo; o `<>` simples basta
    # aqui porque `descricao` é NOT NULL no modelo.
    comparador = "IS DISTINCT FROM" if conexao.dialect.name == "postgresql" else "<>"
    sql = sa.text(
        "UPDATE protocolo_inducao_aplicacao SET descricao = :nova "
        f"WHERE lancamento_id = :lanc AND dia = :dia AND descricao {comparador} :nova"
    )

    for (lancamento_id, dia), itens in por_dia.items():
        partes = []
        for produto, dose, unidade in itens:
            if dose:
                partes.append(" ".join(p for p in (_formatar_dose(dose), unidade, produto) if p))
            else:
                partes.append(produto)
        descricao = " + ".join(partes) if partes else "-"
        # Filtra pela descrição atual para não reescrever o que já está
        # correto — a maioria dos dias, já que só dose múltipla de 10 quebrou.
        conexao.execute(sql, {"nova": descricao, "lanc": lancamento_id, "dia": dia})


def downgrade() -> None:
    """Sem volta — reintroduzir a dose truncada seria recriar o bug. O texto
    corrigido é o que o protocolo sempre mandou aplicar."""
    pass
