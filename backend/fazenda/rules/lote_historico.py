"""
Lote do animal NUMA DATA e DEL numa data, em lote (uma consulta por tabela).

## Por que existe

Os relatórios de Produção (controle leiteiro, qualidade, secagens, BST,
pesagens) mostravam e filtravam o lote ATUAL do animal (`Animal.grupo_primario`)
em todo o histórico. Uma vaca que estava no lote 01 em agosto e foi para o 04
em setembro aparecia com os controles de agosto "no lote 04" — e filtrar pelo
lote 01 escondia a produção que ela de fato deu ali. Decisão do dono (espec de
Produção, out/2026): o filtro por lote é o lote do animal NAQUELA DATA.

A resposta sai, em ordem de preferência, de:

1. o lote gravado no próprio lançamento (`ControleLeiteiro.lote_no_dia`,
   `Sanidade.lote_no_dia`, `PesagemCorporal.grupo_primario`) — `fonte="dia"`;
2. a reconstrução pelo histórico de `MovimentoLote`: o último movimento com
   `data_movimento <= data` dá o `lote_destino`; se a data é ANTERIOR ao
   primeiro movimento, vale o `lote_origem` dele — `fonte="historico"`;
3. sem histórico nenhum: o lote atual do cadastro — `fonte="atual"`, que a tela
   mostra como "lote atual" discreto, para não fingir uma precisão que não há.

## Por que em memória e não `del_vivo`/consulta por linha

`fazenda.rules.lactacao.del_vivo` faz uma consulta por chamada; o relatório de
BST sem filtro (o site chama assim) cobre o histórico inteiro — milhares de
linhas viravam milhares de consultas. `MapaLactacoes.del_na_data` aplica
EXATAMENTE a mesma regra de `lactacao_aberta` (início <= dia e fim ausente ou
> dia; empate → a mais recente) sobre as lactações já carregadas — o teste
`test_producao_filtros.py::test_del_na_data_igual_del_vivo` amarra as duas.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlmodel import Session, select

from fazenda.models import Animal, Lactacao, MovimentoLote

FONTE_DIA = "dia"
FONTE_HISTORICO = "historico"
FONTE_ATUAL = "atual"


def codigo_do_lote(rotulo: str | None) -> str | None:
    """'04 - Secas' -> '04' (pelo separador " - ", mesma regra de
    api/routers/lotes.py::_codigo_do_grupo — repetida aqui porque regra não
    importa router)."""
    if not rotulo:
        return None
    return rotulo.split(" - ", 1)[0].strip() or None


def _mesmo_codigo(a: str | None, b: str | None) -> bool:
    """Tolera zero à esquerda ('5' == '05'), como api/routers/lotes.py."""
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return int(a) == int(b)
    except ValueError:
        return False


def normalizar_lista(valores: Iterable[str] | None) -> list[str]:
    """Aceita tanto `?lotes=01&lotes=02` quanto `?lotes=01,02` (e mistura) —
    devolve os itens não vazios, sem espaços nas pontas."""
    saida: list[str] = []
    for v in valores or []:
        for parte in str(v).split(","):
            parte = parte.strip()
            if parte:
                saida.append(parte)
    return saida


def lote_casa(rotulo: str | None, filtros: list[str]) -> bool:
    """O lote `rotulo` ("01 - Lactação") é um dos `filtros`? Cada filtro pode
    ser o código ("01"/"1") ou o rótulo inteiro — compara pelo CÓDIGO, que é
    estável quando o lote é renomeado (o rótulo antigo gravado no histórico
    continua casando com o lote de hoje)."""
    if not rotulo or not filtros:
        return False
    cod = codigo_do_lote(rotulo)
    for f in filtros:
        if f == rotulo or _mesmo_codigo(cod, codigo_do_lote(f)):
            return True
    return False


class MapaLotes:
    """Lote de cada animal em qualquer data, carregado uma vez por requisição.

    Sempre escopado por `fazenda_id` — o histórico de movimentação de outra
    fazenda (mesmo número de brinco) nunca entra na conta.
    """

    def __init__(self, session: Session, fazenda_id: int | None, numeros: Iterable[str] | None = None):
        q_mov = select(MovimentoLote)
        q_ani = select(Animal)
        if fazenda_id is not None:
            q_mov = q_mov.where(MovimentoLote.fazenda_id == fazenda_id)
            q_ani = q_ani.where(Animal.fazenda_id == fazenda_id)
        alvo = set(numeros) if numeros is not None else None
        if alvo is not None:
            q_mov = q_mov.where(MovimentoLote.numero_matriz.in_(list(alvo)))
            q_ani = q_ani.where(Animal.numero.in_(list(alvo)))
        self.movimentos: dict[str, list[MovimentoLote]] = {}
        for m in session.exec(q_mov).all():
            if m.data_movimento is None:
                continue
            self.movimentos.setdefault(m.numero_matriz, []).append(m)
        for lista in self.movimentos.values():
            lista.sort(key=lambda m: (m.data_movimento, m.id or 0))
        self.animais: dict[str, Animal] = {a.numero: a for a in session.exec(q_ani).all()}

    def atual(self, numero: str) -> str | None:
        a = self.animais.get(numero)
        return a.grupo_primario if a else None

    def na_data(
        self, numero: str, data: date | None, *, gravado: str | None = None, antes_do_dia: bool = False,
    ) -> tuple[str | None, str]:
        """(rótulo do lote, fonte) do animal em `data`.

        `antes_do_dia=True` ignora os movimentos do PRÓPRIO dia — usado na
        secagem: a vaca seca costuma ser movida para o lote de secas no mesmo
        dia, e o lote que interessa ao relatório é o de onde ela saiu.
        """
        if gravado:
            return gravado, FONTE_DIA
        movs = self.movimentos.get(numero) or []
        if data is not None and movs:
            anteriores = [m for m in movs if (m.data_movimento < data if antes_do_dia else m.data_movimento <= data)]
            if anteriores:
                return anteriores[-1].lote_destino, FONTE_HISTORICO
            if movs[0].lote_origem:
                return movs[0].lote_origem, FONTE_HISTORICO
        return self.atual(numero), FONTE_ATUAL

    def esteve_em(self, numero: str, filtros: list[str], inicio: date | None, fim: date | None) -> bool:
        """O animal esteve em algum dos lotes `filtros` em algum dia de
        [inicio, fim]? Vale o lote no início do período e todo destino de
        movimento dentro dele (sem período nenhum: só o lote atual)."""
        if inicio is None and fim is None:
            return lote_casa(self.atual(numero), filtros)
        movs = self.movimentos.get(numero) or []
        if inicio is not None:
            no_inicio, _ = self.na_data(numero, inicio)
        else:
            no_inicio = movs[0].lote_origem if movs and movs[0].lote_origem else self.atual(numero)
        if lote_casa(no_inicio, filtros):
            return True
        return any(
            lote_casa(m.lote_destino, filtros) for m in movs
            if (inicio is None or m.data_movimento >= inicio) and (fim is None or m.data_movimento <= fim)
        )


def lote_na_data(
    session: Session, *, numero_matriz: str, data: date | None, fazenda_id: int | None,
    animal: Animal | None = None,
) -> str | None:
    """Rótulo do lote de UM animal em `data` — usado na gravação do lote do dia
    (controle leiteiro, aplicação de BST/sanidade). Para lançamento de hoje sem
    movimento futuro registrado é o próprio `grupo_primario` atual; para um
    lançamento retroativo, reconstrói pelo histórico."""
    q = select(MovimentoLote).where(MovimentoLote.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        q = q.where(MovimentoLote.fazenda_id == fazenda_id)
    movs = sorted(
        (m for m in session.exec(q).all() if m.data_movimento is not None),
        key=lambda m: (m.data_movimento, m.id or 0),
    )
    if data is not None and movs:
        anteriores = [m for m in movs if m.data_movimento <= data]
        if anteriores:
            return anteriores[-1].lote_destino
        if movs[0].lote_origem:
            return movs[0].lote_origem
    if animal is None:
        qa = select(Animal).where(Animal.numero == numero_matriz)
        if fazenda_id is not None:
            qa = qa.where(Animal.fazenda_id == fazenda_id)
        animal = session.exec(qa).first()
    return animal.grupo_primario if animal else None


class MapaLactacoes:
    """Lactações da fazenda em memória — "em lactação em D" e "DEL em D" sem
    uma consulta por linha. Mesma regra de `rules/lactacao.py::lactacao_aberta`."""

    def __init__(self, session: Session, fazenda_id: int | None, numeros: Iterable[str] | None = None):
        q = select(Lactacao)
        if fazenda_id is not None:
            q = q.where(Lactacao.fazenda_id == fazenda_id)
        if numeros is not None:
            q = q.where(Lactacao.numero_matriz.in_(list(set(numeros))))
        self.por_matriz: dict[str, list[Lactacao]] = {}
        for l in session.exec(q).all():
            self.por_matriz.setdefault(l.numero_matriz, []).append(l)
        for lista in self.por_matriz.values():
            lista.sort(key=lambda l: l.data_inicio)

    def aberta(self, numero: str, dia: date | None) -> Lactacao | None:
        if dia is None:
            return None
        candidatas = [
            l for l in self.por_matriz.get(numero, [])
            if l.data_inicio <= dia and (l.data_fim is None or l.data_fim > dia)
        ]
        return candidatas[-1] if candidatas else None

    def del_na_data(self, numero: str, dia: date | None) -> int | None:
        lact = self.aberta(numero, dia)
        return (dia - lact.data_inicio).days if lact is not None and dia is not None else None


def erro_periodo(inicio: date | None, fim: date | None) -> str | None:
    """Mensagem de período invertido (início depois do fim) ou None. Antes as
    telas consultavam assim mesmo e mostravam "nenhum registro", como se não
    houvesse dado — o erro era de digitação, não de rebanho."""
    if inicio is not None and fim is not None and inicio > fim:
        return (
            f"Período inválido: a data inicial ({inicio.strftime('%d/%m/%Y')}) é posterior à final "
            f"({fim.strftime('%d/%m/%Y')})."
        )
    return None


def no_periodo(dia: date | None, inicio: date | None, fim: date | None) -> bool:
    """`dia` está em [inicio, fim]? Sem período nenhum, tudo entra (compat. com
    quem chama sem filtro). COM período, registro sem data NÃO entra — antes
    ele aparecia em qualquer período escolhido."""
    if inicio is None and fim is None:
        return True
    if dia is None:
        return False
    return (inicio is None or dia >= inicio) and (fim is None or dia <= fim)
