"""
Centros de custo canônicos da fazenda. Os dados vindos do Ideagri usavam siglas
(PL, C|26, ARR); por decisão do usuário passam a ter um nome único e legível,
selecionável em todos os lugares. Este módulo centraliza o mapeamento para o
parser (import), o seed e a normalização única do banco.
"""
from __future__ import annotations

# Sigla antiga (sempre comparada em MAIÚSCULAS, sem espaços) → nome canônico.
MAPA_CENTRO_CUSTO: dict[str, str] = {
    "PL": "Pecuária Leiteira",
    "C|26": "Financiamento 2026",
    "ARR": "Arrendamento",
}

# Nomes canônicos que devem existir no cadastro (Configurações) e nos seletores.
CENTROS_CANONICOS: list[str] = list(dict.fromkeys(MAPA_CENTRO_CUSTO.values()))


def mapear_centro_custo(valor: str | None) -> str | None:
    """Converte a sigla antiga no nome canônico; devolve o valor original se
    não for uma das siglas conhecidas (comparação sem caixa/espaços)."""
    if not valor:
        return valor
    return MAPA_CENTRO_CUSTO.get(valor.strip().upper(), valor)


def valor_gerencial_por_centro_custo(session, contas, centro_custo: str | None, ajustes: dict) -> dict:
    """{ContaGerencial.id: valor gerencial daquela conta/parcela ATRIBUÍVEL a
    `centro_custo`} — usado por todo relatório que soma ContaGerencial e
    aceita filtro de centro de custo (DRE, custo/hectare, custo/produção,
    custo/safra).

    Sem filtro (`centro_custo is None`): devolve `valor_gerencial(c, ajustes)`
    cheio pra cada conta — comportamento idêntico ao de antes do override por
    item existir (o TOTAL nunca muda, só a distribuição quando alguém filtra
    por centro de custo específico).

    Com filtro: uma nota pode ter itens (`LancamentoItem.centro_custo`) em
    centros diferentes do da nota (ver Financeiro > lançamento, campo
    "Centro de custo — só este item"). Rateia proporcionalmente pelo peso
    (`valor_total`) dos itens cujo centro EFETIVO (override do item, ou o da
    nota quando o item não tem override) bate com o filtro, sobre o
    `valor_gerencial` já ajustado de vale da conta/parcela — os itens não são
    por parcela (ligam por `numero_lancamento`), então parcelas da mesma nota
    dividem a MESMA fração. Nota sem item (importada) ou sem nenhum override
    cai no comportamento simples: conta inteira ou nada, conforme
    `conta.centro_custo` bate — sem rateio, sem margem de arredondamento nova.
    Item de vale nunca entra no rateio (não é despesa gerencial de nenhum
    centro de custo, ver rules/vale_item.py)."""
    from fazenda.models import LancamentoItem
    from fazenda.rules.vale_item import eh_item_de_vale, valor_gerencial
    from sqlmodel import select

    if centro_custo is None:
        return {c.id: valor_gerencial(c, ajustes) for c in contas if c.id is not None}

    numeros = {c.numero_lancamento for c in contas if c.numero_lancamento}
    itens_por_numero: dict[str, list] = {}
    if numeros:
        for it in session.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento.in_(numeros))).all():
            if eh_item_de_vale(it):
                continue
            itens_por_numero.setdefault(it.numero_lancamento, []).append(it)

    fracao_por_numero: dict[str, float] = {}

    def _fracao(c) -> float:
        itens = itens_por_numero.get(c.numero_lancamento) if c.numero_lancamento else None
        if not itens:
            return 1.0 if c.centro_custo == centro_custo else 0.0
        if c.numero_lancamento in fracao_por_numero:
            return fracao_por_numero[c.numero_lancamento]
        total = round(sum(it.valor_total or 0 for it in itens), 2)
        no_centro = round(sum(it.valor_total or 0 for it in itens if (it.centro_custo or c.centro_custo) == centro_custo), 2)
        fracao = (no_centro / total) if total > 0 else 0.0
        fracao_por_numero[c.numero_lancamento] = fracao
        return fracao

    return {c.id: round(valor_gerencial(c, ajustes) * _fracao(c), 2) for c in contas if c.id is not None}
