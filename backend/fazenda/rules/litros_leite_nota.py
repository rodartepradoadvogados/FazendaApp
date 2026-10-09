"""
Litros do leite lidos da NOTA do laticínio (Financeiro › receita) — a parte com
Session da regra de `fazenda/rules/litros_leite.py` (que decide nota × reserva).

Reconhecimento do item de leite da nota (receita): o item entra quando

  - a conta gerencial do item tem `PlanoContaGerencial.rmca_receita_leite`; OU
  - o `produto` do item casa (nome, sem acento/caixa) com um `Estoque` da MESMA
    fazenda marcado `produto_leite` ("Produto de leite (venda ao laticínio)").

O item de estoque "Leite" que é INGREDIENTE de dieta dos bezerros
(`produto_leite` falso) nunca vira venda: nem reconhece um item da nota, nem
empresta a unidade dele.

Litros do item = `quantidade` convertida pela UNIDADE do `Estoque` marcado
(`LancamentoItem` não tem unidade): kg ÷ 1,029 (`leite_em_litros`) ou L. Item sem
unidade resolvida, ou sem quantidade, NÃO entra com chute — vira problema da nota
("nota X sem unidade") e o mês fica `nota_incompleta`: cai na reserva (Venda
mensal) ou fica sem dado. Quantidade 0 lançada de propósito é neutra (item que
só traz valor: bonificação, ajuste); item sem valor e sem quantidade é ignorado.

Mês: regime de COMPETÊNCIA = `data_competencia` do item (herdada da nota). Regime
de CAIXA = o mês em que cada parcela da nota foi paga (`saldo_conta.data_caixa`),
na proporção do valor da parcela — o litro anda junto com o dinheiro que a DRE de
caixa conta, e o preço por litro do mês não mistura litro de um mês com receita de
outro.

Só é chamado com a flag `financeiro_regras_v2` ligada.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_
from sqlmodel import Session, select

from fazenda.models import ContaGerencial, EntregaLeiteMensal, Estoque, LancamentoItem
from fazenda.rules import saldo_conta
from fazenda.rules.litros_leite import (
    FONTE_NOTA, FONTE_VENDA_MENSAL, LitrosMes, litros_do_leite, litros_no_periodo,
)
from fazenda.rules.unidades import leite_em_litros, unidade_leite_canonica
from fazenda.rules.vale_item import eh_item_de_vale

MOTIVO_SEM_UNIDADE = "sem_unidade"
MOTIVO_SEM_QUANTIDADE = "sem_quantidade"
LIMITE_NOTAS_NO_AVISO = 5


def _norm(texto: str | None) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(s.casefold().split())


def _unidade_venda_mensal(unidade: str | None) -> str:
    """Rótulo de unidade da Venda mensal (padrão kg, como sempre foi)."""
    return "L" if (unidade or "kg").strip().upper() == "L" else "kg"


@dataclass
class LitrosDasNotas:
    """O que as notas de leite deram, por competência (ou mês de caixa)."""

    litros_por_mes: dict[str, float] = field(default_factory=dict)
    unidades_por_mes: dict[str, set[str]] = field(default_factory=dict)
    # mês -> [{"numero_lancamento": ..., "motivo": "sem_unidade" | "sem_quantidade"}]
    problemas: dict[str, list[dict]] = field(default_factory=dict)
    # mês -> números de nota com item de leite reconhecido só pelo ESTOQUE, em conta
    # que NÃO está marcada "receita do leite" (o litro conta; a receita não).
    fora_da_conta: dict[str, list[str]] = field(default_factory=dict)

    @property
    def meses_incompletos(self) -> set[str]:
        return set(self.problemas)


@dataclass
class LitrosLeite:
    """Os litros do leite de uma fazenda, mês a mês, com a fonte de cada um."""

    meses: dict[str, LitrosMes]
    notas: LitrosDasNotas
    venda_mensal: dict[str, float]
    unidades_venda_mensal: dict[str, set[str]]

    def resumo(self, ini: date, fim: date) -> dict:
        return litros_no_periodo(self.meses, ini, fim)

    def unidades_usadas(self, resumo: dict) -> set[str]:
        """Unidades ("kg"/"L") dos lançamentos que de fato geraram os litros do resumo."""
        usadas: set[str] = set()
        for m in resumo["meses"]:
            if m["fonte"] == FONTE_NOTA:
                usadas |= self.notas.unidades_por_mes.get(m["competencia"], set())
            elif m["fonte"] == FONTE_VENDA_MENSAL:
                usadas |= self.unidades_venda_mensal.get(m["competencia"], set())
        return usadas

    def avisos(self, resumo: dict) -> list[str]:
        """Avisos de fonte dos meses que o período toca (estimado, nota incompleta, conta)."""
        comps = [m["competencia"] for m in resumo["meses"]]
        return avisos_de_litros(self.notas, comps, resumo["meses"])


def carregar_litros_venda_mensal(
    session: Session, fazenda_id: int | None,
) -> tuple[dict[str, float], dict[str, set[str]]]:
    """Venda mensal do leite (a RESERVA) em litros de verdade, por competência, e as
    unidades em que foi lançada (kg convertido por `leite_em_litros`)."""
    query = select(EntregaLeiteMensal)
    if fazenda_id is not None:
        query = query.where(EntregaLeiteMensal.fazenda_id == fazenda_id)
    litros: dict[str, float] = {}
    unidades: dict[str, set[str]] = {}
    for e in session.exec(query).all():
        litros[e.competencia] = litros.get(e.competencia, 0.0) + leite_em_litros(e.quantidade_litros or 0.0, e.unidade)
        unidades.setdefault(e.competencia, set()).add(_unidade_venda_mensal(e.unidade))
    return litros, unidades


def carregar_litros_das_notas(
    session: Session, fazenda_id: int | None, codigos_receita: set[str], *, regime: str = "competencia",
) -> LitrosDasNotas:
    """Litros dos itens de leite das notas de RECEITA da fazenda (ver o docstring do módulo)."""
    out = LitrosDasNotas()
    query_estoque = select(Estoque).where(Estoque.produto_leite == True)  # noqa: E712
    if fazenda_id is not None:
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
    estoque_leite: dict[str, Estoque] = {}
    for e in session.exec(query_estoque).all():
        estoque_leite.setdefault(_norm(e.nome), e)
    if not codigos_receita and not estoque_leite:
        return out

    query_itens = select(LancamentoItem).where(
        or_(LancamentoItem.tipo == "receita", LancamentoItem.tipo.is_(None)),  # type: ignore[union-attr]
        LancamentoItem.gerado_por.is_(None),  # type: ignore[union-attr]
    )
    if fazenda_id is not None:
        query_itens = query_itens.where(LancamentoItem.fazenda_id == fazenda_id)
    candidatos: list[tuple[LancamentoItem, Estoque | None, bool]] = []
    for it in session.exec(query_itens).all():
        if eh_item_de_vale(it):
            continue
        por_conta = it.codigo_conta_gerencial in codigos_receita if it.codigo_conta_gerencial else False
        estoque = estoque_leite.get(_norm(it.produto))
        if por_conta or estoque is not None:
            candidatos.append((it, estoque, por_conta))
    if not candidatos:
        return out

    numeros = {it.numero_lancamento for it, _e, _c in candidatos}
    query_contas = select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))
    if fazenda_id is not None:
        query_contas = query_contas.where(ContaGerencial.fazenda_id == fazenda_id)
    parcelas: dict[str, list[ContaGerencial]] = {}
    for c in session.exec(query_contas).all():
        parcelas.setdefault(c.numero_lancamento, []).append(c)

    for it, estoque, por_conta in candidatos:
        notas = parcelas.get(it.numero_lancamento) or []
        # Item sem `tipo` (importado): vale o tipo da nota. Despesa nunca é venda de leite.
        if it.tipo is None and not any(c.tipo == "receita" for c in notas):
            continue
        meses = _meses_do_item(it, notas, regime)
        if not meses:
            continue
        valor = it.valor_total or 0.0
        qtd = it.quantidade
        if (qtd is None or qtd == 0) and valor <= 0:
            continue  # linha sem valor e sem quantidade (desconto, texto): não é leite
        unidade = unidade_leite_canonica(estoque.unidade) if estoque is not None else None
        motivo = litros = None
        if qtd is None or qtd < 0:
            motivo = MOTIVO_SEM_QUANTIDADE
        elif qtd > 0 and unidade is None:
            motivo = MOTIVO_SEM_UNIDADE
        elif qtd > 0:
            litros = leite_em_litros(qtd, unidade)
        else:
            litros = 0.0  # quantidade 0 de propósito: item que só traz valor
        for mes, fracao in meses:
            if motivo:
                out.problemas.setdefault(mes, []).append({"numero_lancamento": it.numero_lancamento, "motivo": motivo})
                continue
            out.litros_por_mes[mes] = out.litros_por_mes.get(mes, 0.0) + litros * fracao
            if litros:
                out.unidades_por_mes.setdefault(mes, set()).add(unidade)
            if not por_conta and it.numero_lancamento not in out.fora_da_conta.get(mes, []):
                out.fora_da_conta.setdefault(mes, []).append(it.numero_lancamento)
    return out


def _meses_do_item(it: LancamentoItem, notas: list[ContaGerencial], regime: str) -> list[tuple[str, float]]:
    """Em que mês(es) o item conta, e a fração dele em cada um."""
    if regime == "caixa" and notas:
        pagas = [(saldo_conta.data_caixa(c), c.valor_total or 0.0) for c in notas]
        total = sum(v for _d, v in pagas)
        out: dict[str, float] = {}
        for data, valor in pagas:
            if data is None:
                continue  # parcela ainda não paga: a DRE de caixa também não conta
            fracao = (valor / total) if total > 0 else 1.0 / len(pagas)
            out[f"{data:%Y-%m}"] = out.get(f"{data:%Y-%m}", 0.0) + fracao
        return list(out.items())
    data = it.data_competencia or next((c.data_competencia for c in notas if c.data_competencia), None)
    return [(f"{data:%Y-%m}", 1.0)] if data else []


def carregar_litros_do_leite(
    session: Session, fazenda_id: int | None, codigos_receita: set[str], *, regime: str = "competencia",
) -> LitrosLeite:
    """Nota do laticínio > Venda mensal (reserva) > sem dado, mês a mês."""
    notas = carregar_litros_das_notas(session, fazenda_id, codigos_receita, regime=regime)
    venda, unidades_venda = carregar_litros_venda_mensal(session, fazenda_id)
    competencias = sorted(set(notas.litros_por_mes) | set(notas.problemas) | set(venda))
    meses = litros_do_leite(
        competencias, litros_notas=notas.litros_por_mes, litros_venda_mensal=venda,
        meses_nota_incompleta=notas.meses_incompletos,
    )
    return LitrosLeite(meses=meses, notas=notas, venda_mensal=venda, unidades_venda_mensal=unidades_venda)


def _lista_notas(numeros: list[str]) -> str:
    vistos = list(dict.fromkeys(numeros))
    texto = ", ".join(vistos[:LIMITE_NOTAS_NO_AVISO])
    return texto + (f" e mais {len(vistos) - LIMITE_NOTAS_NO_AVISO}" if len(vistos) > LIMITE_NOTAS_NO_AVISO else "")


def _rotulo_mes(comp: str) -> str:
    return f"{comp[5:7]}/{comp[:4]}"


def avisos_de_litros(notas: LitrosDasNotas, competencias: list[str], meses_resumo: list[dict]) -> list[str]:
    """As mensagens de fonte para a tela, só dos meses do período mostrado."""
    visiveis = set(competencias)
    avisos: list[str] = []
    for motivo, texto in (
        (MOTIVO_SEM_UNIDADE,
         'sem unidade: marque o item de estoque da nota como "Produto de leite" e informe a unidade (kg ou L)'),
        (MOTIVO_SEM_QUANTIDADE, "sem quantidade no item de leite: informe a quantidade da nota"),
    ):
        achadas = [(m, p["numero_lancamento"]) for m in sorted(notas.problemas) if m in visiveis
                   for p in notas.problemas[m] if p["motivo"] == motivo]
        if achadas:
            meses = ", ".join(_rotulo_mes(m) for m in dict.fromkeys(m for m, _n in achadas))
            avisos.append(f"Nota {_lista_notas([n for _m, n in achadas])} {texto} — os litros de {meses} não saem dessa nota.")
    fora = [n for m in sorted(notas.fora_da_conta) if m in visiveis for n in notas.fora_da_conta[m]]
    if fora:
        avisos.append(
            f'Nota {_lista_notas(fora)}: item de leite em conta que não está marcada como "Receita do leite" — '
            "os litros contam, a receita não."
        )
    estimados = [m["competencia"] for m in meses_resumo if m["fonte"] == FONTE_VENDA_MENSAL]
    if estimados:
        avisos.append(
            "Litros estimados pela Venda mensal do leite, sem nota do laticínio com quantidade e unidade, em: "
            + ", ".join(_rotulo_mes(m) for m in estimados) + "."
        )
    return avisos
