"""
Ponto único de baixa/devolução de estoque.

Antes deste módulo não existia uma função central: `_criar_movimento_estoque`
(fazenda/api/routers/estoque.py) só cobria o lançamento manual (POST
/estoque/movimentar) e a importação de CSV — todo o resto (Sanidade, Agenda,
Secagem, IATF, BST, dose de sêmen, Alimentação) reimplementava a baixa na mão,
cada um com um subconjunto diferente das verificações (alguns sem gravar
MovimentoEstoque nenhum, outros sem `fazenda_id`, outros buscando o item só
pelo nome sem filtrar a fazenda). Ver auditoria completa no changelog do PR
que introduziu este arquivo.

`fazenda.api.routers.sanidade` (`registrar_aplicacao` /
`_ajustar_estoque_por_aplicacao`) era a referência de comportamento correto
(portões, aviso de saldo negativo, estorno) — os mesmos portões viraram
`movimentar()` abaixo, na mesma ordem, para que todo chamador (Sanidade,
protocolo sanitário, protocolo IATF, indução, BST, Secagem, vacina pré-parto,
Alimentação) se comporte de modo idêntico.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session, select

from fazenda.models import Estoque, EstoqueSemen, MedicamentoComercial, MovimentoEstoque, PrincipioAtivo
from fazenda.rules.farmacia import pode_baixar_estoque
from fazenda.rules.unidades import pode_dar_baixa_direta


def resolver_item(
    session: Session, *, fazenda_id: int | None, produto: str | None = None, estoque_id: int | None = None,
) -> Estoque | None:
    """Resolve o item de estoque respeitando a fazenda. Tenta primeiro
    `estoque_id` (o frasco/apresentação escolhido) — um id de OUTRA fazenda é
    ignorado (nunca baixa estoque alheio) e cai para a busca por `produto`
    (nome), também filtrada pela fazenda."""
    item = None
    if estoque_id is not None:
        item = session.get(Estoque, estoque_id)
        if item is not None and fazenda_id is not None and item.fazenda_id != fazenda_id:
            item = None
    if item is None and produto:
        query = select(Estoque).where(Estoque.nome == produto)
        if fazenda_id is not None:
            query = query.where(Estoque.fazenda_id == fazenda_id)
        item = session.exec(query).first()
    return item


def opcoes_medicamento(
    session: Session, *, fazenda_id: int | None, produto: str | None,
    todos_estoque: list[Estoque] | None = None,
    principios_por_nome: dict[str, PrincipioAtivo] | None = None,
    incluir_sem_estoque: bool = False,
) -> tuple[int | None, list[dict]]:
    """Dado o produto/princípio ativo de um hormônio/medicamento de protocolo,
    resolve o princípio ativo e lista os frascos em estoque (DA FAZENDA) para
    o usuário escolher qual está usando — o "qual medicamento/frasco?" da
    Agenda e da Central de Protocolos.

    `todos_estoque`/`principios_por_nome` são pré-carregados opcionalmente
    pelo chamador (Agenda e Central chamam isto uma vez por hormônio/dia — sem
    isso cada chamada faria duas consultas extras ao banco).

    `incluir_sem_estoque`: além dos frascos já em Estoque, acrescenta toda
    marca comercial cadastrada (`MedicamentoComercial`) do mesmo princípio
    ativo que ainda não apareceu na lista — com `estoque_id=None` e
    `sem_estoque=True`. Dá liberdade pro operador flagar o que realmente
    usou mesmo quando ninguém cadastrou o frasco em Estoque; escolher uma
    dessas opções não abate estoque nenhum (mesmo aviso "não está no
    estoque desta fazenda" de sempre, só que como escolha explícita, não
    fallback silencioso).
    """
    if todos_estoque is None:
        query = select(Estoque)
        if fazenda_id is not None:
            query = query.where(Estoque.fazenda_id == fazenda_id)
        todos_estoque = session.exec(query).all()
    if principios_por_nome is None:
        query_pa = select(PrincipioAtivo)
        if fazenda_id is not None:
            query_pa = query_pa.where(PrincipioAtivo.fazenda_id == fazenda_id)
        principios_por_nome = {(p.nome or "").strip().lower(): p for p in session.exec(query_pa).all()}

    item = next((e for e in todos_estoque if (e.nome or "").strip().lower() == (produto or "").strip().lower()), None)
    pa_id = item.principio_ativo_id if item else None
    if pa_id is None:
        pa = principios_por_nome.get((produto or "").strip().lower())
        pa_id = pa.id if pa else None
    opcoes = []
    for e in todos_estoque:
        if pa_id is not None and e.principio_ativo_id == pa_id:
            opcoes.append({"estoque_id": e.id, "nome": e.nome, "marca": e.laboratorio,
                           "saldo": e.quantidade or 0, "unidade": e.unidade,
                           "estoque_inicializado": e.estoque_inicializado is not False,
                           "sem_estoque": False})
    # Se o próprio produto é um item de estoque (sem princípio), ele é a opção.
    if not opcoes and item is not None:
        opcoes.append({"estoque_id": item.id, "nome": item.nome, "marca": item.laboratorio,
                       "saldo": item.quantidade or 0, "unidade": item.unidade,
                       "estoque_inicializado": item.estoque_inicializado is not False,
                       "sem_estoque": False})
    if incluir_sem_estoque and pa_id is not None:
        ja_listados = {(o["nome"] or "").strip().lower() for o in opcoes}
        for mc in session.exec(
            select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == pa_id)
        ).all():
            nome_norm = (mc.nome_comercial or "").strip().lower()
            if not nome_norm or nome_norm in ja_listados:
                continue
            ja_listados.add(nome_norm)
            opcoes.append({"estoque_id": None, "nome": mc.nome_comercial, "marca": mc.laboratorio,
                           "saldo": None, "unidade": None, "estoque_inicializado": False,
                           "sem_estoque": True})
    return pa_id, opcoes


def movimentar(
    session: Session, *, item: Estoque | None, quantidade: float, unidade: str | None, data: date,
    fazenda_id: int | None, movimento: str, observacao: str, usuario_id: int | None = None,
    origem_tipo: str | None = None, origem_id: int | None = None, sinal: int = -1,
    produto: str | None = None,
) -> list[str]:
    """Aplica `sinal * quantidade` a `item`, grava o MovimentoEstoque
    correspondente (com `fazenda_id`, `estoque_id` e origem) e devolve a lista
    de avisos — NUNCA bloqueia a baixa por saldo (decisão de produto: negativo
    só avisa). `produto` é só o nome usado na mensagem de "não encontrado"
    quando `item` já vem None."""
    if item is None:
        return [f'"{produto or "?"}" não está no estoque desta fazenda — lançamento registrado sem baixa.']
    if item.estocavel is False:
        # Item só financeiro (não controla quantidade) — comportamento atual
        # intencional: não mexe, sem aviso.
        return []
    if not pode_baixar_estoque(item):
        return [
            f'Lançamento de "{item.nome}" registrado, mas sem baixa: registre o estoque inicial '
            f'ou a primeira compra do item para começar o controle de baixas.'
        ]
    if not pode_dar_baixa_direta(unidade, item.unidade):
        return [
            f'Baixa de estoque de "{item.nome}" não aplicada — cadastre a equivalência entre '
            f'"{unidade}" e "{item.unidade}" (unidade de estoque do produto).'
        ]

    item.quantidade = (item.quantidade or 0) + sinal * quantidade
    if item.estoque_minimo is not None:
        item.abaixo_minimo = item.quantidade < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.add(MovimentoEstoque(
        nome_item=item.nome, movimento=movimento, quantidade=abs(quantidade), unidade=item.unidade,
        data_movimento=data, observacao=observacao, usuario_id=usuario_id, fazenda_id=fazenda_id,
        estoque_id=item.id, origem_tipo=origem_tipo, origem_id=origem_id,
    ))

    avisos: list[str] = []
    if item.quantidade < 0:
        avisos.append(
            f'Estoque de "{item.nome}" ficou negativo (saldo: {item.quantidade:g} {item.unidade or ""}). '
            f'Registre a entrada/compra que faltou.'
        )
    return avisos


def baixar(
    session: Session, *, item: Estoque | None, quantidade: float, unidade: str | None, data: date,
    fazenda_id: int | None, observacao: str, usuario_id: int | None = None,
    origem_tipo: str | None = None, origem_id: int | None = None, produto: str | None = None,
) -> list[str]:
    return movimentar(
        session, item=item, quantidade=quantidade, unidade=unidade, data=data, fazenda_id=fazenda_id,
        movimento="Aplicação", observacao=observacao, usuario_id=usuario_id,
        origem_tipo=origem_tipo, origem_id=origem_id, sinal=-1, produto=produto,
    )


def devolver(
    session: Session, *, item: Estoque | None, quantidade: float, unidade: str | None, data: date,
    fazenda_id: int | None, observacao: str, usuario_id: int | None = None,
    origem_tipo: str | None = None, origem_id: int | None = None, produto: str | None = None,
) -> list[str]:
    return movimentar(
        session, item=item, quantidade=quantidade, unidade=unidade, data=data, fazenda_id=fazenda_id,
        movimento="Entrada de ajuste", observacao=observacao, usuario_id=usuario_id,
        origem_tipo=origem_tipo, origem_id=origem_id, sinal=+1, produto=produto,
    )


def _movimentar_dose_semen(
    session: Session, *, touro: EstoqueSemen, doses: float, data: date, fazenda_id: int | None,
    usuario_id: int | None, observacao: str, origem_tipo: str | None, origem_id: int | None,
    movimento: str, sinal: int,
) -> list[str]:
    """Aplica `sinal * doses` a `touro.doses` e grava o MovimentoEstoque
    correspondente — base compartilhada de `baixar_dose_semen` (sinal=-1) e
    `devolver_dose_semen` (sinal=+1, usada para estornar uma baixa de dose,
    ex.: exclusão do Serviço/IA que a gerou — ver rotas/exclusoes.py)."""
    touro.doses = (touro.doses or 0) + sinal * doses
    touro.atualizado_em = datetime.utcnow()
    session.add(touro)

    item_espelho = session.exec(select(Estoque).where(Estoque.estoque_semen_id == touro.id)).first()
    if item_espelho is not None:
        item_espelho.quantidade = (item_espelho.quantidade or 0) + sinal * doses
        if item_espelho.estoque_minimo is not None:
            item_espelho.abaixo_minimo = item_espelho.quantidade < item_espelho.estoque_minimo
        item_espelho.atualizado_em = datetime.utcnow()
        session.add(item_espelho)

    session.add(MovimentoEstoque(
        nome_item=touro.touro_nome, movimento=movimento, quantidade=abs(doses), unidade="dose",
        data_movimento=data, observacao=observacao, usuario_id=usuario_id, fazenda_id=fazenda_id,
        estoque_id=item_espelho.id if item_espelho is not None else None,
        origem_tipo=origem_tipo, origem_id=origem_id,
    ))

    avisos: list[str] = []
    if touro.doses < 0:
        avisos.append(
            f'Estoque de sêmen de "{touro.touro_nome}" ficou negativo (saldo: {touro.doses} doses). '
            f'Registre a entrada/compra que faltou.'
        )
    return avisos


def baixar_dose_semen(
    session: Session, *, touro: EstoqueSemen, doses: float, data: date, fazenda_id: int | None,
    usuario_id: int | None = None, observacao: str, origem_tipo: str | None = None, origem_id: int | None = None,
) -> list[str]:
    """Desconta `doses` de `touro.doses` e — diferente do comportamento antigo
    de `_baixar_dose_semen` (reproducao.py) — grava um MovimentoEstoque, para a
    baixa deixar rastro no histórico/RMCA. Se existir um item de `Estoque`
    espelhado (`Estoque.estoque_semen_id == touro.id`), mantém os dois em
    sincronia — o mesmo espelhamento que `_criar_movimento_estoque`
    (estoque.py) já faz no sentido inverso (compra de sêmen -> Estoque)."""
    return _movimentar_dose_semen(
        session, touro=touro, doses=doses, data=data, fazenda_id=fazenda_id, usuario_id=usuario_id,
        observacao=observacao, origem_tipo=origem_tipo, origem_id=origem_id, movimento="Aplicação", sinal=-1,
    )


def devolver_dose_semen(
    session: Session, *, touro: EstoqueSemen, doses: float, data: date, fazenda_id: int | None,
    usuario_id: int | None = None, observacao: str, origem_tipo: str | None = None, origem_id: int | None = None,
) -> list[str]:
    """Devolve `doses` a `touro.doses` — estorno de `baixar_dose_semen`, usado
    quando o Serviço/IA que gerou a baixa é excluído (ver rotas/exclusoes.py)."""
    return _movimentar_dose_semen(
        session, touro=touro, doses=doses, data=data, fazenda_id=fazenda_id, usuario_id=usuario_id,
        observacao=observacao, origem_tipo=origem_tipo, origem_id=origem_id, movimento="Entrada de ajuste", sinal=+1,
    )
