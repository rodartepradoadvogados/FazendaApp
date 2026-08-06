"""
Router de estoque — inventário completo de insumos e lançamento de
entradas/saídas (dá baixa ou soma direto em Estoque.quantidade).
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Estoque, EstoqueSemen, Fornecedor, MovimentoEstoque, SeedFlag, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios

router = APIRouter(prefix="/estoque", tags=["estoque"])

MOVIMENTOS_ENTRADA = ["Entrada de ajuste", "Entrada de cortesia"]
MOVIMENTOS_SAIDA = ["Aplicação", "Saída de ajuste", "Doação"]
MOVIMENTOS_VALIDOS = set(MOVIMENTOS_ENTRADA + MOVIMENTOS_SAIDA)


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
# Só itens estocáveis podem ser doados ou recebidos de cortesia — itens não
# estocáveis existem só para lançamento financeiro, sem controle de quantidade.
MOVIMENTOS_SOMENTE_ESTOCAVEL = {"Doação", "Entrada de cortesia"}


def _casar_estoque_semen(nome_item: str, session: Session) -> EstoqueSemen | None:
    """Casa um item de Estoque genérico com um touro do Estoque de Sêmen pelo
    nome (igual, sem acento/caixa) ou por conter o NAAB/código do touro no
    nome — usado para vincular automaticamente `Estoque.estoque_semen_id`
    sem exigir escolha manual quando o nome já deixa claro de qual touro se
    trata (ex.: item "Sêmen ABS 7HO12345" casa pelo NAAB)."""
    alvo = _sem_acento(nome_item).strip().lower()
    if not alvo:
        return None
    for touro in session.exec(select(EstoqueSemen)).all():
        nome_touro = _sem_acento(touro.touro_nome or "").strip().lower()
        if nome_touro and nome_touro == alvo:
            return touro
    for touro in session.exec(select(EstoqueSemen)).all():
        naab = _sem_acento(touro.naab or "").strip().lower()
        codigo = _sem_acento(touro.codigo or "").strip().lower()
        if (naab and naab in alvo) or (codigo and codigo in alvo):
            return touro
    return None


def sindicar_estoque_semen(session: Session) -> None:
    """Vincula cada item de Estoque genérico sem `estoque_semen_id` ao touro
    correspondente do Estoque de Sêmen (por nome ou NAAB/código — ver
    `_casar_estoque_semen`), para que entrada/saída deste item também
    atualize `EstoqueSemen.doses` (ver `_criar_movimento_estoque`). Nunca
    sobrescreve um vínculo já existente. Roda uma única vez."""
    chave = "estoque_vinculo_semen_202607"
    if session.get(SeedFlag, chave):
        return
    for item in session.exec(select(Estoque).where(Estoque.estoque_semen_id.is_(None))).all():  # type: ignore[union-attr]
        touro = _casar_estoque_semen(item.nome, session)
        if touro:
            item.estoque_semen_id = touro.id
            session.add(item)
    session.add(SeedFlag(chave=chave))
    session.commit()


def sincronizar_item_estoque_semen(estoque_semen: EstoqueSemen, session: Session) -> None:
    """Espelha um touro do Estoque de Sêmen (`EstoqueSemen`) num item de
    `Estoque` genérico (categoria "Sêmen e genética"), casado por
    `estoque_semen_id` — sem isso, uma compra de sêmen só aparecia em
    Rebanho > Touros > Sêmen (que lê `EstoqueSemen` direto), nunca na
    listagem/filtro de Estoque (que lê só a tabela `Estoque`). Chamado toda
    vez que `EstoqueSemen.doses` muda (compra, movimentação vinculada).
    Não mexe em `estoque_minimo`/`abaixo_minimo` por item — o "estoque
    mínimo" de sêmen é tratado à parte, agregado por tipo (ver
    `cadastro.MINIMO_SEMEN`), não por touro individual. Touro "fazenda" (monta
    natural) não entra — não é dose comprável/estocável, não faz sentido
    virar item de Estoque."""
    if estoque_semen.tipo == "fazenda":
        return
    item = session.exec(select(Estoque).where(Estoque.estoque_semen_id == estoque_semen.id)).first()
    nome = f"Sêmen — {estoque_semen.touro_nome}" + (f" ({estoque_semen.naab})" if estoque_semen.naab else "")
    valor_total = (
        (estoque_semen.doses or 0) * estoque_semen.valor_unitario if estoque_semen.valor_unitario is not None else None
    )
    if item:
        item.nome = nome
        item.quantidade = estoque_semen.doses
        item.valor_unitario = estoque_semen.valor_unitario
        item.valor_total = valor_total
        item.tipo_semen = estoque_semen.tipo
        item.ativo = estoque_semen.ativo
        item.atualizado_em = datetime.utcnow()
        session.add(item)
    else:
        session.add(Estoque(
            nome=nome, categoria="Sêmen e genética", unidade="dose",
            quantidade=estoque_semen.doses, valor_unitario=estoque_semen.valor_unitario, valor_total=valor_total,
            estocavel=True, ativo=estoque_semen.ativo,
            estoque_semen_id=estoque_semen.id, tipo_semen=estoque_semen.tipo,
        ))


def backfill_estoque_semen_generico(session: Session) -> None:
    """Roda uma única vez: cria/atualiza o item de `Estoque` espelhado (ver
    `sincronizar_item_estoque_semen`) para cada touro já existente em
    `EstoqueSemen` — corrige o histórico de compras de sêmen registradas
    antes desta sincronização existir, que nunca apareceram na listagem/
    filtro de Estoque (só em Rebanho > Touros > Sêmen)."""
    chave = "estoque_semen_backfill_202607"
    if session.get(SeedFlag, chave):
        return
    for touro in session.exec(select(EstoqueSemen)).all():
        sincronizar_item_estoque_semen(touro, session)
    session.add(SeedFlag(chave=chave))
    session.commit()


@router.get("/")
def listar_estoque(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """Todos os itens de estoque para o dashboard interativo (filtra no cliente)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_fornecedor = select(Fornecedor)
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query_fornecedor = query_fornecedor.where(Fornecedor.fazenda_id == fazenda_id)
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
    fornecedores = {f.id: f.nome for f in session.exec(query_fornecedor).all()}
    itens = [
        {**e.model_dump(), "fornecedor_nome": fornecedores.get(e.fornecedor_id)}
        for e in session.exec(query_estoque.order_by(Estoque.nome)).all()
    ]
    return {"itens": itens, "total": len(itens)}


class EstoqueIn(BaseModel):
    nome: str
    categoria: str | None = None
    finalidade: str | None = None
    numero_produto: str | None = None
    unidade: str | None = None
    quantidade: float | None = None
    estoque_minimo: float | None = None
    valor_unitario: float | None = None
    local_armazenamento: str | None = None
    unidade_embalagem: str | None = None
    medida_embalagem: str | None = None
    quantidade_embalagem: float | None = None
    fornecedor_id: int | None = None
    ativo: bool = True
    observacao: str | None = None
    carencia_dias: int | None = None
    centro_custo_padrao: str | None = None
    conta_gerencial_despesa_padrao: str | None = None
    conta_gerencial_receita_padrao: str | None = None
    gera_receita: bool = False
    gera_patrimonio: bool = False
    exibir_necessidade_compra_agenda: bool = False
    estocavel: bool = True
    data_inicio_controle: date | None = None
    principio_ativo: str | None = None
    principio_ativo_id: int | None = None
    classificacao_medicamento: str | None = None
    alimento_id: int | None = None
    estoque_semen_id: int | None = None
    tipo_semen: str | None = None


@router.post("/", status_code=201)
def criar_item_estoque(
    dados: EstoqueIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """Cadastra um item de estoque novo (não existe ainda um com esse nome)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_existente = select(Estoque).where(Estoque.nome == dados.nome)
    if fazenda_id is not None:
        query_existente = query_existente.where(Estoque.fazenda_id == fazenda_id)
    existente = session.exec(query_existente).first()
    if existente:
        raise HTTPException(status_code=409, detail=f'Já existe um item de estoque chamado "{dados.nome}"')
    valor_total = (dados.quantidade or 0) * (dados.valor_unitario or 0) if dados.quantidade and dados.valor_unitario else None
    item = Estoque(
        nome=dados.nome,
        categoria=dados.categoria,
        finalidade=dados.finalidade,
        numero_produto=dados.numero_produto,
        unidade=dados.unidade,
        quantidade=dados.quantidade,
        estoque_minimo=dados.estoque_minimo,
        valor_unitario=dados.valor_unitario,
        valor_total=valor_total,
        abaixo_minimo=(dados.quantidade is not None and dados.estoque_minimo is not None and dados.quantidade < dados.estoque_minimo),
        local_armazenamento=dados.local_armazenamento,
        unidade_embalagem=dados.unidade_embalagem,
        medida_embalagem=dados.medida_embalagem,
        quantidade_embalagem=dados.quantidade_embalagem,
        fornecedor_id=dados.fornecedor_id,
        ativo=dados.ativo,
        observacao=dados.observacao,
        carencia_dias=dados.carencia_dias,
        centro_custo_padrao=dados.centro_custo_padrao,
        conta_gerencial_despesa_padrao=dados.conta_gerencial_despesa_padrao,
        conta_gerencial_receita_padrao=dados.conta_gerencial_receita_padrao,
        gera_receita=dados.gera_receita,
        gera_patrimonio=dados.gera_patrimonio,
        exibir_necessidade_compra_agenda=dados.exibir_necessidade_compra_agenda,
        estocavel=dados.estocavel,
        data_inicio_controle=dados.data_inicio_controle if dados.estocavel else None,
        principio_ativo=dados.principio_ativo,
        principio_ativo_id=dados.principio_ativo_id,
        classificacao_medicamento=dados.classificacao_medicamento,
        alimento_id=dados.alimento_id,
        estoque_semen_id=dados.estoque_semen_id or (t.id if (t := _casar_estoque_semen(dados.nome, session)) else None),
        tipo_semen=dados.tipo_semen,
        fazenda_id=fazenda_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.put("/{item_id}")
def atualizar_item_estoque(
    item_id: int, dados: EstoqueIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """Edita o cadastro completo de um item de estoque já existente — mesmos
    campos do cadastro (POST /), usado pelo botão "editar" da tabela filtrada
    de Estoque (site)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(Estoque, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    query_existente = select(Estoque).where(Estoque.nome == dados.nome, Estoque.id != item_id)
    if fazenda_id is not None:
        query_existente = query_existente.where(Estoque.fazenda_id == fazenda_id)
    existente = session.exec(query_existente).first()
    if existente:
        raise HTTPException(status_code=409, detail=f'Já existe outro item de estoque chamado "{dados.nome}"')
    item.nome = dados.nome
    item.categoria = dados.categoria
    item.finalidade = dados.finalidade
    item.numero_produto = dados.numero_produto
    item.unidade = dados.unidade
    item.quantidade = dados.quantidade
    item.estoque_minimo = dados.estoque_minimo
    item.valor_unitario = dados.valor_unitario
    item.valor_total = (dados.quantidade or 0) * (dados.valor_unitario or 0) if dados.quantidade and dados.valor_unitario else None
    item.abaixo_minimo = dados.quantidade is not None and dados.estoque_minimo is not None and dados.quantidade < dados.estoque_minimo
    item.local_armazenamento = dados.local_armazenamento
    item.unidade_embalagem = dados.unidade_embalagem
    item.medida_embalagem = dados.medida_embalagem
    item.quantidade_embalagem = dados.quantidade_embalagem
    item.fornecedor_id = dados.fornecedor_id
    item.ativo = dados.ativo
    item.observacao = dados.observacao
    item.carencia_dias = dados.carencia_dias
    item.centro_custo_padrao = dados.centro_custo_padrao
    item.conta_gerencial_despesa_padrao = dados.conta_gerencial_despesa_padrao
    item.conta_gerencial_receita_padrao = dados.conta_gerencial_receita_padrao
    item.gera_receita = dados.gera_receita
    item.gera_patrimonio = dados.gera_patrimonio
    item.exibir_necessidade_compra_agenda = dados.exibir_necessidade_compra_agenda
    item.estocavel = dados.estocavel
    item.data_inicio_controle = dados.data_inicio_controle if dados.estocavel else None
    item.principio_ativo = dados.principio_ativo
    item.principio_ativo_id = dados.principio_ativo_id
    item.classificacao_medicamento = dados.classificacao_medicamento
    item.alimento_id = dados.alimento_id
    if dados.estoque_semen_id is not None:
        item.estoque_semen_id = dados.estoque_semen_id
    item.tipo_semen = dados.tipo_semen
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


def _eh_medicamento(e: Estoque) -> bool:
    """Item "candidato a medicamento" — usado quando NENHUM critério (princípio
    ativo/classificação/doença/secagem/vacina) foi passado, para que os
    seletores gerais de medicamento/hormônio (ex.: EditorHormoniosIatf, "todos"
    em Sanidade avulsa) não mostrem ração/material/equipamento junto."""
    return (
        e.finalidade == "Medicamento"
        or e.classificacao_medicamento is not None
        or e.principio_ativo_id is not None
        or bool((e.principio_ativo or "").strip())
    )


@router.get("/medicamentos")
def listar_medicamentos(
    principio_ativo: str = "", classificacao: str = "", doenca: str = "",
    finalidade: str = "", incluir_sem_estoque: bool = False,
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Medicamentos (itens de estoque) que cumprem um critério — usado ao
    lançar por princípio ativo, por classificação OU por doença. Sem nenhum
    critério, vira o catálogo geral de medicamento/hormônio/vacina (ver
    `_eh_medicamento`) — o que faz deste endpoint a fonte única para qualquer
    seletor que hoje mostrava todo o estoque sem filtro.

    Por padrão só entram itens com saldo em estoque (`quantidade > 0`) e
    ativos — `incluir_sem_estoque=true` resolve o problema na hora e ignora
    esse filtro (mesma ideia do "incluir touros sem estoque" da Inseminação).

    O casamento por princípio ativo/doença usa a Farmácia: além do texto legado
    `principio_ativo`, resolve o vínculo relacional (principio_ativo_id →
    PrincipioAtivo.nome / PrincipioAtivo.doenca_id → Doenca.nome), para que os
    medicamentos ligados ao princípio/doença apareçam mesmo sem o campo texto."""
    from fazenda.models import Doenca, PrincipioAtivo

    fazenda_id = fazenda_id_seguro(fazenda_id)

    algum_criterio = bool(principio_ativo or classificacao or doenca or finalidade)

    query_pa = select(PrincipioAtivo)
    query_doenca = select(Doenca)
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query_pa = query_pa.where(PrincipioAtivo.fazenda_id == fazenda_id)
        query_doenca = query_doenca.where(Doenca.fazenda_id == fazenda_id)
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)

    pa_ids: set[int] = set()
    if principio_ativo:
        alvo = principio_ativo.strip().lower()
        for pa in session.exec(query_pa).all():
            if (pa.nome or "").strip().lower() == alvo:
                pa_ids.add(pa.id)

    # Doença → princípios ativos ligados a ela (via doenca_id da Farmácia).
    pa_ids_doenca: set[int] = set()
    if doenca:
        alvo_d = doenca.strip().lower()
        doenca_ids = {d.id for d in session.exec(query_doenca).all() if (d.nome or "").strip().lower() == alvo_d}
        for pa in session.exec(query_pa).all():
            if pa.doenca_id in doenca_ids:
                pa_ids_doenca.add(pa.id)

    # Finalidade: "secagem" = antimicrobianos intramamários de vaca seca;
    # "vacina" = todos os biológicos; "vacina_pre_parto" = só as vacinas
    # aplicadas na vaca seca/pré-parto (Clostridiose, Diarreia Neonatal,
    # Reprodutiva/Leptospirose — primovacinação — e Pasteurelose/Paratifo dos
    # Bezerros), excluindo biológicos que não são pré-parto (Brucelose,
    # Tuberculina). Casa pela categoria da Farmácia (categoria_software /
    # eh_biologico / doença) e, como reforço, pelo texto da classificação do
    # estoque.
    DOENCAS_VACINA_PRE_PARTO = {
        "clostridiose", "diarreia neonatal", "leptospirose", "pasteurelose e paratifo dos bezerros",
    }
    pa_ids_secagem: set[int] = set()
    pa_ids_vacina: set[int] = set()
    pa_ids_vacina_pre_parto: set[int] = set()
    if finalidade in ("secagem", "vacina", "vacina_pre_parto"):
        doencas_por_id = {d.id: (d.nome or "").strip().lower() for d in session.exec(query_doenca).all()}
        for pa in session.exec(query_pa).all():
            cat = (getattr(pa, "categoria_software", "") or "").lower()
            if ("vaca seca" in cat) or ("intramamario" in _sem_acento(cat)):
                pa_ids_secagem.add(pa.id)
            if getattr(pa, "eh_biologico", False) or "vacina" in cat:
                pa_ids_vacina.add(pa.id)
            if getattr(pa, "eh_biologico", False) and doencas_por_id.get(pa.doenca_id) in DOENCAS_VACINA_PRE_PARTO:
                pa_ids_vacina_pre_parto.add(pa.id)

    itens = session.exec(query_estoque).all()
    saida = []
    for e in itens:
        if e.ativo is False:
            continue
        if not algum_criterio and not _eh_medicamento(e):
            continue
        if principio_ativo:
            casa_texto = (e.principio_ativo or "").strip().lower() == principio_ativo.strip().lower()
            casa_link = e.principio_ativo_id in pa_ids
            if not (casa_texto or casa_link):
                continue
        if doenca and e.principio_ativo_id not in pa_ids_doenca:
            continue
        if classificacao and (e.classificacao_medicamento or "").strip().lower() != classificacao.strip().lower():
            continue
        if finalidade == "secagem":
            classe = _sem_acento((e.classificacao_medicamento or "").lower())
            if e.principio_ativo_id not in pa_ids_secagem and "vaca seca" not in classe and "intramamario" not in classe:
                continue
        if finalidade == "vacina":
            classe = (e.classificacao_medicamento or "").lower()
            if e.principio_ativo_id not in pa_ids_vacina and "vacina" not in classe:
                continue
        if finalidade == "vacina_pre_parto" and e.principio_ativo_id not in pa_ids_vacina_pre_parto:
            continue
        # Saldo None = item nunca inventariado (não é a mesma coisa que
        # confirmadamente zerado) — só esconde quando o saldo é conhecido e
        # <= 0, para não sumir com itens legados sem saldo lançado ainda.
        if not incluir_sem_estoque and e.quantidade is not None and e.quantidade <= 0:
            continue
        saida.append({
            "nome": e.nome, "unidade": e.unidade, "quantidade": e.quantidade,
            "principio_ativo": e.principio_ativo, "classificacao_medicamento": e.classificacao_medicamento,
            "laboratorio": e.laboratorio, "estoque_id": e.id,
        })
    return sorted(saida, key=lambda x: x["nome"])


@router.get("/movimentos")
def listar_movimentos(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """Histórico de entradas/saídas lançadas manualmente."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(MovimentoEstoque)
    if fazenda_id is not None:
        query = query.where(MovimentoEstoque.fazenda_id == fazenda_id)
    movs = session.exec(query.order_by(MovimentoEstoque.data_movimento.desc())).all()
    nomes = mapa_usuarios(session, {m.usuario_id for m in movs})
    movimentos = [{**m.model_dump(), "usuario_nome": nomes.get(m.usuario_id)} for m in movs]
    return {"movimentos": movimentos, "total": len(movs)}


class MovimentoIn(BaseModel):
    nome: str
    movimento: str
    quantidade: float
    unidade: str | None = None
    data_movimento: date
    observacao: str | None = None
    # Vincula esta entrada física a um item de Pedido de compra — é só a
    # partir deste vínculo que o pedido passa a refletir em Estoque.
    pedido_id: int | None = None
    pedido_item_id: int | None = None


def _criar_movimento_estoque(
    dados: MovimentoIn, session: Session, usuario_id: int | None = None, fazenda_id: int | None = None,
) -> Estoque:
    """Lógica de fato de um lançamento de movimento (sem o commit ser feito
    pelo chamador direto) — usada pelo endpoint HTTP e pela importação de CSV
    (fazenda.api.routers.importar), que chama isto fora do ciclo de requisição
    e por isso não tem um usuário logado (usuario_id fica None nesse caso)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.movimento not in MOVIMENTOS_VALIDOS:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido")
    if dados.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero")

    query_item = select(Estoque).where(Estoque.nome == dados.nome)
    if fazenda_id is not None:
        query_item = query_item.where(Estoque.fazenda_id == fazenda_id)
    item = session.exec(query_item).first()
    if not item:
        raise HTTPException(status_code=404, detail=f'Item de estoque "{dados.nome}" não encontrado')
    if dados.movimento in MOVIMENTOS_SOMENTE_ESTOCAVEL and item.estocavel is False:
        raise HTTPException(status_code=400, detail="Somente itens estocáveis podem ser doados ou recebidos de cortesia")

    baixa = dados.movimento in MOVIMENTOS_SAIDA
    item.quantidade = (item.quantidade or 0) + (-dados.quantidade if baixa else dados.quantidade)
    if item.estoque_minimo is not None:
        item.abaixo_minimo = item.quantidade < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)

    # Item vinculado a um touro do Estoque de Sêmen (ver `estoque_semen_id`) —
    # toda entrada/saída física deste item também atualiza as doses do touro,
    # para que o Estoque de Sêmen nunca fique desatualizado em relação às
    # compras/baixas lançadas por aqui.
    if item.estoque_semen_id:
        touro = session.get(EstoqueSemen, item.estoque_semen_id)
        if touro:
            touro.doses = touro.doses + (-round(dados.quantidade) if baixa else round(dados.quantidade))
            touro.atualizado_em = datetime.utcnow()
            session.add(touro)

    session.add(MovimentoEstoque(
        nome_item=dados.nome,
        movimento=dados.movimento,
        quantidade=dados.quantidade,
        unidade=dados.unidade or item.unidade,
        data_movimento=dados.data_movimento,
        observacao=dados.observacao,
        usuario_id=usuario_id,
        pedido_id=dados.pedido_id,
        pedido_item_id=dados.pedido_item_id,
        fazenda_id=fazenda_id,
        estoque_id=item.id,
    ))
    session.commit()
    session.refresh(item)

    if dados.pedido_item_id and not baixa:
        from fazenda.api.routers.pedidos import atualizar_status_por_movimento_estoque
        atualizar_status_por_movimento_estoque(session, dados.pedido_item_id, dados.quantidade)

    return item


@router.post("/movimentar")
def movimentar_estoque(
    dados: MovimentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    item = _criar_movimento_estoque(dados, session, usuario_id=user.id, fazenda_id=fazenda_id)
    return item.model_dump()
