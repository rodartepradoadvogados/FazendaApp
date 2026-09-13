"""Congela a discriminacao do holerite no pagamento da folha

Revision ID: b2f7c1a83d59
Revises: e0b7c3a91d24
Create Date: 2026-09-06

C7 — O RECIBO DA FOLHA PAGA NÃO BATIA COM O LÍQUIDO QUE FOI PAGO.

`_detalhe_folha` (routers/cadastro/rh_folha.py) montava a discriminação do
holerite A CADA LEITURA, consultando `vale_parcela` ao vivo — inclusive para
folha `status = 'pago'`. Só que o `valor_liquido` do pagamento ficou GRAVADO
em `folha_pagamento`, e os self-heals do módulo pulam folha paga de propósito
(não se reescreve dinheiro que já saiu). Os dois números chegavam à tela por
caminhos diferentes: editar um vale, quitá-lo, estorná-lo ou remanejar a
parcela para outra competência DEPOIS do pagamento fazia o holerite impresso
hoje deixar de ser o recibo do que foi efetivamente pago. Num documento
trabalhista isso é grave — o holerite é prova.

As duas colunas novas guardam a FOTOGRAFIA do recibo no momento do pagamento
(`discriminacao_congelada`, JSON com as linhas no formato de
`fazenda.rules.holerite.linha`) e o marco que diz que ela existe
(`discriminacao_congelada_em`). Mesmo desenho de `Diaria.encerramento_*`:
congela no fechamento, a leitura passa a ler a fotografia, e descongelar exige
um ato explícito — `POST /folha-pagamento/{id}/estornar`.

BACKFILL — O QUE ELE FAZ. Para toda folha já `pago` sem fotografia, remonta a
discriminação com os dados que existem HOJE (o próprio lançamento, as
`vale_parcela` da competência, o `vale_funcionario` de cada parcela e a nota
fiscal de origem, quando o vale nasceu de um `lancamento_item`) e grava. A
partir daí aquela folha para de se mexer: qualquer edição futura de vale não
alcança mais o recibo dela.

BACKFILL — O QUE ELE NÃO CONSEGUE RECUPERAR (e por que fingir o contrário
seria pior que admitir):

1. A discriminação de HOJE pode já não ser a do DIA DO PAGAMENTO. Não existe
   histórico de `vale_parcela`: se um vale foi editado, quitado, excluído ou
   teve a parcela remanejada depois que a folha foi paga, o que este backfill
   congela é o estado pós-mudança. O congelamento passa a valer daqui para
   frente; ele não reconstrói o passado.

2. Por consequência, uma folha paga que JÁ ESTÁ divergente continua
   divergente depois desta migração — a soma da discriminação congelada pode
   não bater com o `valor_liquido` gravado. Isso é DELIBERADO. As duas saídas
   possíveis seriam mentir: reescrever `valor_liquido` (reescrever dinheiro
   que já saiu, a partir de um estado que talvez não seja o do pagamento) ou
   forjar linhas de vale que fechassem a conta (inventar fato em documento
   trabalhista). A divergência fica visível na tela — o cartão "Recibo não
   soma o líquido pago" — para conferência humana, que é decisão do dono,
   lançamento a lançamento.

3. `discriminacao_congelada_em` recebe o instante da MIGRAÇÃO, não o do
   pagamento. É a verdade: foi neste instante que a fotografia foi tirada.
   `data_pagamento` continua sendo a data do pagamento.

4. Vale excluído depois do pagamento não deixa rastro nenhum em
   `vale_parcela`; sua linha simplesmente não existe para ser congelada.

Nada é reescrito: `valor_liquido`, `valor_vale`, a conta a pagar e o status
ficam exatamente como estão. A migração só grava as duas colunas novas.

O código que remonta as linhas abaixo é uma CÓPIA CONGELADA da lógica de
`_detalhe_folha`/`fazenda.rules.holerite` desta data — de propósito, e não um
import: uma migração tem de continuar produzindo o mesmo resultado quando o
código da aplicação mudar depois dela.
"""
from datetime import date, datetime
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2f7c1a83d59"
down_revision: Union[str, Sequence[str], None] = "e0b7c3a91d24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUNAS = [
    ("discriminacao_congelada", sa.Text()),
    ("discriminacao_congelada_em", sa.DateTime()),
]

DIAS_DO_MES = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
TOLERANCIA_CONFERENCIA = 0.01


# ── Cópia congelada de fazenda.rules.holerite (ver docstring) ───────────────
def _brl(valor: float) -> str:
    inteiro, centavos = f"{abs(valor):.2f}".split(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {'.'.join(grupos)},{centavos}"


def _percentual(valor: float) -> str:
    return f"{f'{valor:g}'.replace('.', ',')}%"


def _como_data(valor) -> date | None:
    """A mesma coluna volta como `date` no Postgres e como texto no SQLite —
    o backfill roda nos dois."""
    if valor is None or isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _data_br(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


def _linha(tipo, label, valor, descricao, referencia, provento=None, desconto=None, origem=None) -> dict:
    return {
        "label": label, "valor": valor, "tipo": tipo, "descricao": descricao,
        "referencia": referencia, "provento": provento, "desconto": desconto, "origem": origem,
    }


def _dias_do_mes(competencia: str) -> int:
    ano, mes = (int(x) for x in competencia.split("-"))
    if mes == 2 and (ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)):
        return 29
    return DIAS_DO_MES[mes - 1]


def _referencia_bruto(data_admissao: date | None, competencia: str, dias_mes: int) -> str:
    if data_admissao and data_admissao.strftime("%Y-%m") == competencia and dias_mes:
        trabalhados = dias_mes - data_admissao.day + 1
        return f"Admissão em {data_admissao.strftime('%d/%m')} · {trabalhados} de {dias_mes} dias do mês"
    return "Mensal"


def _referencia_retencao(valor: float, percentual: float, valor_bruto: float) -> tuple:
    if not percentual:
        return "Valor informado, sem percentual", {
            "tipo": "retencao", "percentual": None, "base": None, "confere": None, "diferenca": None,
        }
    esperado = round(valor_bruto * percentual / 100, 2)
    diferenca = round(valor - esperado, 2)
    confere = abs(diferenca) <= TOLERANCIA_CONFERENCIA
    texto = f"{_percentual(percentual)} sobre {_brl(valor_bruto)}"
    if not confere:
        texto = f"{texto} · valor ajustado à mão"
    return texto, {
        "tipo": "retencao", "percentual": percentual, "base": round(valor_bruto, 2),
        "confere": confere, "diferenca": diferenca,
    }


def _descricao_vale(observacao, origem_lancamento) -> str:
    if origem_lancamento:
        nota = origem_lancamento.get("numero_documento")
        produto = origem_lancamento.get("produto")
        if nota and produto:
            return f"Vale — nota {nota} ({produto})"
        if nota:
            return f"Vale — nota {nota}"
        if produto:
            return f"Vale — {produto}"
    texto = (observacao or "").strip()
    return f"Vale — {texto}" if texto else "Vale"


def _referencia_vale(parcela: int, total: int, data_pagamento: date | None) -> str:
    ordinal = f"Parcela {parcela} de {total}" if total > 1 else "Parcela única"
    return f"{ordinal} · vale de {_data_br(data_pagamento)}" if data_pagamento else ordinal


def _origem_vale(vale, parcela, k: int, n: int, origem_lancamento) -> dict:
    data_vale = _como_data(vale["data_pagamento"])
    return {
        "tipo": "vale",
        "vale_id": vale["id"],
        "parcela_id": parcela["id"],
        "parcela": k,
        "parcelas_total": n,
        "valor_total": round(vale["valor_total"] or 0, 2),
        "data_pagamento": data_vale.isoformat() if data_vale else None,
        "forma_pagamento": vale["forma_pagamento"],
        "observacao": vale["observacao"],
        "numero_documento_pagamento": vale["numero_documento_pagamento"],
        "numero_lancamento_gerado": vale["numero_lancamento_gerado"],
        "sem_saida_de_caixa": vale["forma_pagamento"] == "desconto_integral_folha",
        "origem_lancamento": origem_lancamento,
        "aplicada": bool(parcela["aplicada"]),
    }


# ── Backfill ────────────────────────────────────────────────────────────────
def _linhas_da_folha(folha, admissao, parcelas, irmas_por_vale, vales, origens) -> list[dict]:
    """Cópia congelada de `_detalhe_folha` — mesma ordem, mesmos campos."""
    competencia = folha["competencia"]
    bruto = folha["valor_bruto"] or 0.0
    detalhe = [_linha(
        "bruto", "Salário bruto", bruto, "Salário",
        _referencia_bruto(admissao, competencia, _dias_do_mes(competencia)),
        provento=round(bruto, 2),
    )]
    for tipo, rotulo, valor, percentual in (
        ("inss", "INSS", folha["valor_inss"] or 0.0, folha["percentual_inss"] or 0.0),
        ("ir", "IR", folha["valor_ir"] or 0.0, folha["percentual_ir"] or 0.0),
    ):
        if not valor:
            continue
        sufixo = f" ({percentual:g}%)" if percentual else ""
        referencia, origem = _referencia_retencao(valor, percentual, bruto)
        detalhe.append(_linha(
            tipo, f"{rotulo}{sufixo}", -valor, rotulo, referencia,
            desconto=round(valor, 2), origem=origem,
        ))
    for p in parcelas:
        irmas = irmas_por_vale.get(p["vale_id"], [p])
        n = len(irmas)
        k = next((i + 1 for i, x in enumerate(irmas) if x["id"] == p["id"]), 1)
        vale = vales.get(p["vale_id"])
        origem_lancamento = origens.get(p["vale_id"])
        detalhe.append(_linha(
            "vale", f"Vale (parcela {k}/{n})", -(p["valor"] or 0.0),
            _descricao_vale(vale["observacao"] if vale else None, origem_lancamento),
            _referencia_vale(k, n, _como_data(vale["data_pagamento"]) if vale else None),
            desconto=round(p["valor"] or 0.0, 2),
            origem=_origem_vale(vale, p, k, n, origem_lancamento) if vale else None,
        ))
    descontos = folha["descontos"] or 0.0
    if abs(descontos) > 0.001:
        detalhe.append(_linha(
            "outros", "Outros descontos", -descontos, "Outros descontos",
            "Valor único, sem detalhamento gravado", desconto=round(descontos, 2),
        ))
    detalhe.append(_linha("liquido", "Valor líquido", folha["valor_liquido"] or 0.0, "Líquido", ""))
    return detalhe


def _congelar_folhas_pagas(conexao) -> None:
    folhas = [
        dict(linha._mapping) for linha in conexao.execute(sa.text(
            "SELECT id, pessoa_id, competencia, valor_bruto, descontos, percentual_inss, valor_inss, "
            "percentual_ir, valor_ir, valor_liquido FROM folha_pagamento "
            "WHERE status = 'pago' AND discriminacao_congelada IS NULL"
        ))
    ]
    if not folhas:
        return

    pessoa_ids = sorted({f["pessoa_id"] for f in folhas if f["pessoa_id"] is not None})
    admissoes = {
        linha._mapping["id"]: _como_data(linha._mapping["data_admissao"])
        for linha in conexao.execute(
            sa.text("SELECT id, data_admissao FROM pessoa WHERE id IN :ids").bindparams(
                sa.bindparam("ids", value=tuple(pessoa_ids), expanding=True)
            )
        )
    } if pessoa_ids else {}

    # Todas as parcelas das pessoas envolvidas — as de outras competências
    # entram só para numerar "k de n" na sequência completa do vale, exatamente
    # como `_contexto_discriminacao` faz.
    parcelas = [
        dict(linha._mapping) for linha in conexao.execute(
            sa.text(
                "SELECT id, vale_id, pessoa_id, competencia, valor, aplicada FROM vale_parcela "
                "WHERE pessoa_id IN :ids"
            ).bindparams(sa.bindparam("ids", value=tuple(pessoa_ids), expanding=True))
        )
    ] if pessoa_ids else []

    irmas_por_vale: dict = {}
    for p in parcelas:
        irmas_por_vale.setdefault(p["vale_id"], []).append(p)
    for lista in irmas_por_vale.values():
        lista.sort(key=lambda x: (x["competencia"], x["id"] or 0))

    por_pessoa_competencia: dict = {}
    for p in parcelas:
        por_pessoa_competencia.setdefault((p["pessoa_id"], p["competencia"]), []).append(p)
    for lista in por_pessoa_competencia.values():
        lista.sort(key=lambda x: (x["vale_id"], x["id"] or 0))

    vale_ids = sorted({p["vale_id"] for p in parcelas if p["vale_id"] is not None})
    vales = {
        linha._mapping["id"]: dict(linha._mapping)
        for linha in conexao.execute(
            sa.text(
                "SELECT id, valor_total, forma_pagamento, data_pagamento, observacao, "
                "numero_documento_pagamento, numero_lancamento_gerado FROM vale_funcionario "
                "WHERE id IN :ids"
            ).bindparams(sa.bindparam("ids", value=tuple(vale_ids), expanding=True))
        )
    } if vale_ids else {}

    origens = _origens_por_vale(conexao, vale_ids)

    agora = datetime.utcnow()
    for folha in folhas:
        linhas = _linhas_da_folha(
            folha,
            admissoes.get(folha["pessoa_id"]),
            por_pessoa_competencia.get((folha["pessoa_id"], folha["competencia"]), []),
            irmas_por_vale, vales, origens,
        )
        conexao.execute(
            sa.text(
                "UPDATE folha_pagamento SET discriminacao_congelada = :linhas, "
                "discriminacao_congelada_em = :quando WHERE id = :id"
            ),
            {"linhas": json.dumps(linhas, ensure_ascii=False), "quando": agora, "id": folha["id"]},
        )


def _origens_por_vale(conexao, vale_ids) -> dict:
    """Cópia congelada de `origens_lancamento_por_vale` — a nota fiscal que
    gerou o vale, quando ele nasceu de um item de lançamento."""
    if not vale_ids:
        return {}
    itens = [
        dict(linha._mapping) for linha in conexao.execute(
            sa.text(
                "SELECT id, numero_lancamento, produto, valor_total, vale_funcionario_id "
                "FROM lancamento_item WHERE vale_funcionario_id IN :ids"
            ).bindparams(sa.bindparam("ids", value=tuple(vale_ids), expanding=True))
        )
    ]
    if not itens:
        return {}
    numeros = sorted({it["numero_lancamento"] for it in itens if it["numero_lancamento"]})
    contas: dict = {}
    if numeros:
        for linha in conexao.execute(
            sa.text(
                "SELECT numero_lancamento, parcela_num, fornecedor_cliente, numero_nota, data_emissao "
                "FROM conta_gerencial WHERE numero_lancamento IN :numeros"
            ).bindparams(sa.bindparam("numeros", value=tuple(numeros), expanding=True))
        ):
            conta = dict(linha._mapping)
            atual = contas.get(conta["numero_lancamento"])
            if atual is None or (conta["parcela_num"] or 0) < (atual["parcela_num"] or 0):
                contas[conta["numero_lancamento"]] = conta

    resultado: dict = {}
    for it in itens:
        conta = contas.get(it["numero_lancamento"])
        emissao = _como_data(conta["data_emissao"]) if conta else None
        resultado[it["vale_funcionario_id"]] = {
            "item_id": it["id"],
            "numero_lancamento": it["numero_lancamento"],
            "produto": it["produto"],
            "valor_item": it["valor_total"],
            "fornecedor_cliente": conta["fornecedor_cliente"] if conta else None,
            "numero_documento": conta["numero_nota"] if conta else None,
            "data_emissao": emissao.isoformat() if emissao else None,
        }
    return resultado


def upgrade() -> None:
    """Upgrade schema."""
    for nome, tipo in COLUNAS:
        op.add_column("folha_pagamento", sa.Column(nome, tipo, nullable=True))
    _congelar_folhas_pagas(op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    for nome, _tipo in reversed(COLUNAS):
        op.drop_column("folha_pagamento", nome)
