"""
Item de lançamento financeiro que é, na verdade, gasto pessoal de um
funcionário/empreiteiro/diarista — ponto ÚNICO de exclusão desses itens dos
relatórios gerenciais.

Duas camadas, porque a camada de relatórios do Financeiro tem duas famílias:
 A) endpoints que somam LancamentoItem (RMCA, custo/litro, DRE detalhado,
    orçado x realizado) — usam `sem_itens_de_vale(query)`;
 B) endpoints que somam ContaGerencial, isto é, a NOTA inteira (DRE, custo por
    hectare, custo por vaca/lote, custo por safra) — usam
    `ajuste_vale_por_conta(...)` + `valor_gerencial(...)`, que descontam de
    cada parcela a fatia proporcional do que virou vale naquela nota.

NUNCA repita o WHERE na mão num endpoint novo: qualquer soma gerencial de
LancamentoItem/ContaGerencial passa por aqui.
"""
from __future__ import annotations

from sqlmodel import Session, or_, select

from fazenda.models import ContaGerencial, LancamentoItem


# ── Camada A ────────────────────────────────────────────────────────────────
def sem_itens_de_vale(query):
    """Exclui do `select(LancamentoItem)` recebido os itens que geraram vale.
    Devolve o próprio query encadeável (idempotente: aplicar 2x não muda nada)."""
    return query.where(
        LancamentoItem.vale_funcionario_id.is_(None),
        LancamentoItem.vale_avulso_id.is_(None),
    )


def eh_item_de_vale(item: LancamentoItem) -> bool:
    """Mesma regra de `sem_itens_de_vale`, para filtrar listas já carregadas."""
    return item.vale_funcionario_id is not None or item.vale_avulso_id is not None


# ── Camada B ────────────────────────────────────────────────────────────────
def valor_vale_por_lancamento(session: Session, fazenda_id: int | None) -> dict[str, float]:
    """{numero_lancamento: soma dos valor_total dos itens que viraram vale}."""
    query = select(LancamentoItem).where(
        or_(LancamentoItem.vale_funcionario_id.is_not(None), LancamentoItem.vale_avulso_id.is_not(None))
    )
    if fazenda_id is not None:
        query = query.where(LancamentoItem.fazenda_id == fazenda_id)
    resultado: dict[str, float] = {}
    for it in session.exec(query).all():
        if not it.numero_lancamento:
            continue
        resultado[it.numero_lancamento] = round(resultado.get(it.numero_lancamento, 0.0) + (it.valor_total or 0), 2)
    return resultado


def ajuste_vale_por_conta(
    session: Session, contas: list[ContaGerencial], fazenda_id: int | None
) -> dict[int, float]:
    """{ContaGerencial.id: valor a DESCONTAR daquela parcela}.

    Rateio: a nota LC-x tem R$ 1.000 em 2 parcelas de R$ 500 e R$ 180 de vale
    → cada parcela é ajustada em R$ 90 (proporcional ao valor_total da
    parcela sobre o total das parcelas do mesmo numero_lancamento). A última
    parcela absorve o arredondamento, como em `criar_lancamento`. Notas sem
    item de vale não aparecem no dict. Conta com numero_lancamento nulo
    (importada) nunca é ajustada.
    """
    vale_por_lancamento = valor_vale_por_lancamento(session, fazenda_id)
    numeros = {c.numero_lancamento for c in contas if c.numero_lancamento and c.numero_lancamento in vale_por_lancamento}
    if not numeros:
        return {}

    # Busca TODAS as parcelas de cada numero_lancamento afetado — não só as
    # que vieram em `contas` — porque o rateio é proporcional ao total real
    # da nota, não ao subconjunto que o endpoint chamador filtrou (ex.:
    # regime de caixa pode trazer só algumas parcelas de uma nota parcelada).
    query = select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    todas_parcelas = session.exec(query).all()

    por_numero: dict[str, list[ContaGerencial]] = {}
    for c in todas_parcelas:
        por_numero.setdefault(c.numero_lancamento, []).append(c)

    ajustes: dict[int, float] = {}
    for numero, parcelas in por_numero.items():
        valor_vale = vale_por_lancamento.get(numero, 0.0)
        if valor_vale <= 0:
            continue
        total = round(sum(p.valor_total or 0 for p in parcelas), 2)
        if total <= 0:
            continue
        parcelas_ordenadas = sorted(parcelas, key=lambda p: (p.parcela_num or 0, p.id or 0))
        acumulado = 0.0
        for i, p in enumerate(parcelas_ordenadas):
            if p.id is None:
                continue
            if i < len(parcelas_ordenadas) - 1:
                fatia = round(valor_vale * (p.valor_total or 0) / total, 2)
            else:
                fatia = round(valor_vale - acumulado, 2)
            acumulado = round(acumulado + fatia, 2)
            ajustes[p.id] = fatia
    return ajustes


def valor_gerencial(conta: ContaGerencial, ajustes: dict[int, float]) -> float:
    """(conta.valor_total or 0) - ajustes.get(conta.id, 0.0), arredondado a 2."""
    return round((conta.valor_total or 0) - ajustes.get(conta.id, 0.0), 2)


# ── Coluna "Origem" do relatório de vales (§3.7) ────────────────────────────
def origens_lancamento_por_vale(session: Session, vale_ids: set[int] | list[int], campo: str) -> dict[int, dict]:
    """{vale_id: origem_lancamento} para os relatórios de vale (`GET
    /cadastro/vales` e `GET /cadastro/vale-avulso/todos`) — reverse lookup a
    partir de LancamentoItem, sem nenhuma coluna nova em ValeFuncionario/
    ValeAvulso. `campo` é "vale_funcionario_id" ou "vale_avulso_id". Zero
    N+1: duas queries batch (itens + contas), nunca uma por vale."""
    ids = {i for i in vale_ids if i is not None}
    if not ids:
        return {}
    coluna = getattr(LancamentoItem, campo)
    itens = session.exec(select(LancamentoItem).where(coluna.in_(ids))).all()
    if not itens:
        return {}
    numeros = {it.numero_lancamento for it in itens if it.numero_lancamento}
    contas_por_numero: dict[str, ContaGerencial] = {}
    if numeros:
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all():
            atual = contas_por_numero.get(c.numero_lancamento)
            if atual is None or (c.parcela_num or 0) < (atual.parcela_num or 0):
                contas_por_numero[c.numero_lancamento] = c

    resultado: dict[int, dict] = {}
    for it in itens:
        vale_id = getattr(it, campo)
        conta = contas_por_numero.get(it.numero_lancamento)
        resultado[vale_id] = {
            "item_id": it.id,
            "numero_lancamento": it.numero_lancamento,
            "produto": it.produto,
            "valor_item": it.valor_total,
            "fornecedor_cliente": conta.fornecedor_cliente if conta else None,
            "numero_documento": conta.numero_nota if conta else None,
            "data_emissao": conta.data_emissao.isoformat() if conta and conta.data_emissao else None,
        }
    return resultado


# ── Divisão de um item entre "vale da pessoa" e "despesa da fazenda" ────────
def dividir_item_de_lancamento(
    session: Session, item: LancamentoItem, valor_que_fica: float, *, sufixo_descricao: str,
) -> LancamentoItem:
    """Parte `item` em dois: ele mesmo encolhe para `valor_que_fica` e nasce
    um GÊMEO com o resto, na mesma nota, sem nenhum vínculo de vale.

    Existe porque "metade disto é vale" não cabe numa flag no item. A camada
    A de exclusão gerencial (`sem_itens_de_vale`) é um WHERE que tira a LINHA
    inteira, e a camada B rateia o `valor_total` da linha inteira pelas
    parcelas — as duas somam `LancamentoItem.valor_total` cru depois de
    filtrar. Uma coluna "quanto deste item é vale" obrigaria todo somatório
    gerencial do sistema (DRE, RMCA, custo/litro, custo por hectare,
    orçado × realizado) a aprender a subtrair uma fração; duas linhas, cada
    uma inteiramente de um lado, mantêm todos eles corretos sem tocar em
    nenhum. Foi por isso que o dono descreveu o caso como "o lançamento se
    divide".

    O gêmeo herda conta gerencial, centro de custo, produto e tipo do
    original — é a mesma compra —, e `quantidade` é rateada na proporção do
    valor (2/3 da ração são 2/3 dos quilos). `valor_total` NÃO é recalculado
    de quantidade × valor_unitario de propósito: com preço unitário quebrado
    os dois pedaços não fechariam a soma da nota, e a nota tem de fechar.

    Não commita — quem chama decide quando (o item ainda vai receber o
    vínculo do vale)."""
    valor_original = round(item.valor_total or 0, 2)
    valor_que_fica = round(valor_que_fica, 2)
    resto = round(valor_original - valor_que_fica, 2)
    if resto <= 0:
        raise ValueError("A divisão do item precisa deixar um resto positivo para a fazenda")

    fracao_resto = resto / valor_original if valor_original else 0.0
    quantidade_resto = round(item.quantidade * fracao_resto, 4) if item.quantidade else None

    gemeo = LancamentoItem(
        fazenda_id=item.fazenda_id,
        numero_lancamento=item.numero_lancamento,
        tipo=item.tipo,
        data_competencia=item.data_competencia,
        codigo_conta_gerencial=item.codigo_conta_gerencial,
        nome_conta_gerencial=item.nome_conta_gerencial,
        centro_custo=item.centro_custo,
        produto=item.produto,
        tipo_item=item.tipo_item,
        descricao=" — ".join(x for x in ((item.descricao or "").strip(), sufixo_descricao) if x),
        quantidade=quantidade_resto,
        valor_unitario=item.valor_unitario,
        valor_total=resto,
    )
    session.add(gemeo)

    item.valor_total = valor_que_fica
    if item.quantidade:
        item.quantidade = round(item.quantidade - (quantidade_resto or 0), 4)
    session.add(item)
    return gemeo


def itens_do_vale(session: Session, vale_funcionario_id: int) -> list[LancamentoItem]:
    """Os itens de nota que geraram este vale de funcionário (na prática 0 ou
    1 — só o checkbox "é vale?" cria o vínculo, e ele é por item)."""
    return list(session.exec(
        select(LancamentoItem).where(LancamentoItem.vale_funcionario_id == vale_funcionario_id)
    ).all())


# ── Vínculo item ↔ vale ──────────────────────────────────────────────────────
def limpar_vinculo_de_itens(
    session: Session, *, vale_funcionario_id: int | None = None, vale_avulso_id: int | None = None,
) -> None:
    """Zera o vínculo em qualquer LancamentoItem que apontava para o vale
    excluído — sem isso ficaria FK pendurada e o item sumido dos relatórios
    para sempre. Não commita — quem chama decide quando commitar."""
    if vale_funcionario_id is not None:
        itens = session.exec(
            select(LancamentoItem).where(LancamentoItem.vale_funcionario_id == vale_funcionario_id)
        ).all()
        for it in itens:
            it.vale_funcionario_id = None
            session.add(it)
    if vale_avulso_id is not None:
        itens = session.exec(
            select(LancamentoItem).where(LancamentoItem.vale_avulso_id == vale_avulso_id)
        ).all()
        for it in itens:
            it.vale_avulso_id = None
            session.add(it)
