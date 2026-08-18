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

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import CompraSemen, Estoque, EstoqueSemen, Fornecedor, MovimentoEstoque, SeedFlag, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.estoque_baixa import carencia_para_item, incrementar_quantidade_atomico, resolver_marca_comercial
from fazenda.rules.visibilidade import visivel

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
        # Autocura: item espelhado criado antes da correção do bug acima
        # (fazenda_id NULL) — toda vez que a sincronização toca nele de novo
        # (nova compra, baixa vinculada), aproveita para consertar, sem
        # esperar o backfill único rodar. Só assume o fazenda_id do touro
        # quando o item ainda está sem fazenda (nunca sobrescreve um valor
        # já preenchido).
        if item.fazenda_id is None and estoque_semen.fazenda_id is not None:
            item.fazenda_id = estoque_semen.fazenda_id
        session.add(item)
    else:
        session.add(Estoque(
            nome=nome, categoria="Sêmen e genética", unidade="dose",
            quantidade=estoque_semen.doses, valor_unitario=estoque_semen.valor_unitario, valor_total=valor_total,
            estocavel=True, ativo=estoque_semen.ativo,
            estoque_semen_id=estoque_semen.id, tipo_semen=estoque_semen.tipo,
            # BUG corrigido: este item nascia sem fazenda_id (ficava NULL),
            # então `listar_estoque`/`criar_item_estoque` (que filtram por
            # `Estoque.fazenda_id == fazenda_id`) ou vazavam o item de sêmen
            # de uma fazenda para todas as outras (quando `fazenda_id is None`,
            # o filtro nem entra) ou faziam o item sumir de qualquer listagem
            # filtrada por fazenda (quando o filtro entra e não bate com NULL).
            # `EstoqueSemen.fazenda_id` é a fonte da verdade aqui — o item
            # espelhado tem que pertencer à mesma fazenda do touro que ele espelha.
            fazenda_id=estoque_semen.fazenda_id,
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


def backfill_estoque_semen_fazenda_id(session: Session) -> None:
    """Roda uma única vez: corrige o `fazenda_id` (NULL) dos itens de
    `Estoque` espelhados de sêmen criados antes da correção do bug em
    `sincronizar_item_estoque_semen` — a criação nunca gravava `fazenda_id`,
    então esses itens vazavam para todas as fazendas nas listagens sem filtro
    de fazenda, ou simplesmente sumiam das listagens que já filtram por
    `Estoque.fazenda_id` (ex.: `listar_estoque`). Preenche a partir do
    `EstoqueSemen.fazenda_id` do touro vinculado (fonte da verdade) — nunca
    sobrescreve um `fazenda_id` já preenchido, mesmo que divirja do touro."""
    chave = "estoque_semen_backfill_fazenda_id_202608"
    if session.get(SeedFlag, chave):
        return
    query = select(Estoque).where(Estoque.fazenda_id.is_(None), Estoque.estoque_semen_id.is_not(None))  # type: ignore[union-attr]
    for item in session.exec(query).all():
        touro = session.get(EstoqueSemen, item.estoque_semen_id)
        if touro and touro.fazenda_id is not None:
            item.fazenda_id = touro.fazenda_id
            session.add(item)
    session.add(SeedFlag(chave=chave))
    session.commit()


def mesclar_estoque_semen(sobrevivente: EstoqueSemen, perdedor: EstoqueSemen, session: Session) -> None:
    """Funde `perdedor` em `sobrevivente` — mesmo touro, duas linhas de
    `EstoqueSemen` por engano (nome batendo, mas nunca casadas por NAAB; ver
    o bug corrigido em `compra_semen.registrar_compra`). Não soma doses (a
    contagem do sobrevivente já é a considerada correta por quem chama) —
    só preserva histórico e metadados, sem inventar total:

    - `CompraSemen.estoque_semen_id` do perdedor passa a apontar pro
      sobrevivente — nenhuma compra "desaparece" do relatório de compras.
    - O item de `Estoque` espelhado (ver `sincronizar_item_estoque_semen`) do
      perdedor, se existir, funde no do sobrevivente: `MovimentoEstoque`
      vinculado ao espelho do perdedor passa a apontar pro espelho do
      sobrevivente (criando um se o sobrevivente ainda não tinha), e o
      espelho do perdedor é removido.
    - Metadados (`naab`, `codigo`, `central`, `local_armazenamento`,
      `observacao`, `valor_unitario`) do sobrevivente só são completados a
      partir do perdedor quando estão em branco — nunca sobrescreve um valor
      já preenchido.
    - `perdedor` é removido no final. `Servico.reprodutor` grava o nome do
      touro como texto (não uma referência a esta tabela), então nenhum
      histórico de inseminação/relatório reprodutivo se perde — eles casam
      pelo nome, que permanece o mesmo.

    Não dá commit — quem chama decide quando persistir."""
    for campo in ("naab", "codigo", "central", "local_armazenamento", "observacao", "valor_unitario"):
        if getattr(sobrevivente, campo) in (None, "") and getattr(perdedor, campo) not in (None, ""):
            setattr(sobrevivente, campo, getattr(perdedor, campo))

    for compra in session.exec(select(CompraSemen).where(CompraSemen.estoque_semen_id == perdedor.id)).all():
        compra.estoque_semen_id = sobrevivente.id
        session.add(compra)

    espelho_perdedor = session.exec(select(Estoque).where(Estoque.estoque_semen_id == perdedor.id)).first()
    if espelho_perdedor is not None:
        espelho_sobrevivente = session.exec(select(Estoque).where(Estoque.estoque_semen_id == sobrevivente.id)).first()
        if espelho_sobrevivente is not None:
            for mov in session.exec(select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == espelho_perdedor.id)).all():
                mov.estoque_id = espelho_sobrevivente.id
                session.add(mov)
            session.delete(espelho_perdedor)
        else:
            espelho_perdedor.estoque_semen_id = sobrevivente.id
            session.add(espelho_perdedor)

    session.add(sobrevivente)
    session.delete(perdedor)
    session.flush()
    sincronizar_item_estoque_semen(sobrevivente, session)


def backfill_estoque_semen_duplicados_mesmo_tipo(session: Session) -> None:
    """Roda uma única vez: funde linhas de `EstoqueSemen` duplicadas — mesmo
    touro (nome, sem acento/caixa), mesmo tipo, mesma fazenda — em uma só.
    Nenhuma fazenda cadastra de propósito duas linhas convencionais para o
    mesmo touro; sempre que isso existe é engano (ex.: uma compra pelo
    catálogo NAAB que devia ter somado dose numa linha já cadastrada só pelo
    nome, e criou uma segunda por não achar o NAAB — ver `registrar_compra`).

    Sobrevivente: a linha com mais doses (critério do produtor — "o correto
    é o que tem mais doses"); empate desfeito por quem já tem compra
    registrada (`CompraSemen`) e, por último, pela linha mais antiga (id
    menor). Ver `mesclar_estoque_semen` para o que é preservado."""
    chave = "estoque_semen_backfill_duplicados_mesmo_tipo_202608"
    if session.get(SeedFlag, chave):
        return
    grupos: dict[tuple[int | None, str, str], list[EstoqueSemen]] = {}
    for touro in session.exec(select(EstoqueSemen).where(EstoqueSemen.ativo == True)).all():  # noqa: E712
        chave_grupo = (touro.fazenda_id, _sem_acento(touro.touro_nome or "").strip().lower(), touro.tipo)
        if not chave_grupo[1]:
            continue
        grupos.setdefault(chave_grupo, []).append(touro)

    ids_com_compra = {
        c.estoque_semen_id for c in session.exec(select(CompraSemen)).all()
    }
    for linhas in grupos.values():
        if len(linhas) < 2:
            continue
        linhas.sort(key=lambda t: (-(t.doses or 0), t.id not in ids_com_compra, t.id))
        sobrevivente, *perdedores = linhas
        for perdedor in perdedores:
            mesclar_estoque_semen(sobrevivente, perdedor, session)
    session.add(SeedFlag(chave=chave))
    session.commit()


# Nomes confirmados pelo produtor (ago/2026) como sêmen comprado — nunca
# touro de monta natural na fazenda dele — que ficaram cadastrados também
# como `tipo="fazenda"` por engano (provável cadastro manual anterior à
# compra de sêmen catalogada). Lista fechada e nomeada de propósito: uma
# fusão automática "sempre que o nome bater entre tipos diferentes" seria
# arriscada em multi-tenant — outra fazenda pode legitimamente ter um touro
# de monta natural com o mesmo nome popular de um touro NAAB comprado por
# outra. Só funde quando o NOME e a FAZENDA batem — nunca entre fazendas.
NOMES_SEMPRE_COMPRADO = {"henessy", "heineken", "halle"}


def backfill_estoque_semen_fazenda_para_convencional_nomeados(session: Session) -> None:
    """Roda uma única vez: para os touros em `NOMES_SEMPRE_COMPRADO`, funde a
    linha `tipo="fazenda"` (touro de monta natural) na linha convencional/
    sexada do mesmo nome, dentro da mesma fazenda — só quando as duas
    existem. Sem isso, esses touros apareciam ao mesmo tempo na lista de
    "sêmen convencional" (correto) e em "touros da fazenda"/monta natural
    (errado), inclusive no seletor de cobertura por monta natural."""
    chave = "estoque_semen_backfill_fazenda_para_convencional_nomeados_202608"
    if session.get(SeedFlag, chave):
        return
    fazenda_rows = session.exec(select(EstoqueSemen).where(EstoqueSemen.tipo == "fazenda", EstoqueSemen.ativo == True)).all()  # noqa: E712
    for row in fazenda_rows:
        nome_norm = _sem_acento(row.touro_nome or "").strip().lower()
        if nome_norm not in NOMES_SEMPRE_COMPRADO:
            continue
        query = select(EstoqueSemen).where(
            EstoqueSemen.tipo.in_(["convencional", "sexado"]), EstoqueSemen.ativo == True,  # noqa: E712
        )
        if row.fazenda_id is not None:
            query = query.where(EstoqueSemen.fazenda_id == row.fazenda_id)
        else:
            query = query.where(EstoqueSemen.fazenda_id.is_(None))  # type: ignore[union-attr]
        candidatos = [
            t for t in session.exec(query).all()
            if _sem_acento(t.touro_nome or "").strip().lower() == nome_norm
        ]
        if len(candidatos) != 1:
            continue  # nenhum ou mais de um candidato — não decide sozinho, evita ambiguidade
        sobrevivente = candidatos[0]
        mesclar_estoque_semen(sobrevivente, row, session)
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
    dados: EstoqueIn, fazenda_id: int = Depends(get_fazenda_id_escrita), session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
) -> dict:
    """Cadastra um item de estoque novo (não existe ainda um com esse nome)."""
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

    if item.estocavel is not False and item.quantidade and item.quantidade > 0:
        session.add(MovimentoEstoque(
            nome_item=item.nome, movimento="Saldo inicial", quantidade=item.quantidade, unidade=item.unidade,
            data_movimento=item.data_inicio_controle or date.today(), observacao="Saldo inicial do cadastro",
            usuario_id=user.id if isinstance(user, Usuario) else None, fazenda_id=fazenda_id,
            estoque_id=item.id, origem_tipo="cadastro_estoque", origem_id=item.id,
        ))
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
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
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


@router.delete("/{item_id}")
def excluir_item_estoque(
    item_id: int, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """Exclui um item de estoque de fato — só permitido quando não há nenhum
    `MovimentoEstoque` vinculado (409 caso contrário, orientando a desativar
    em vez de excluir), já que `MovimentoEstoque.estoque_id` é FK real para
    `estoque.id` (o único FK do repo apontando pra essa tabela)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(Estoque, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    total_movimentos = len(session.exec(select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == item_id)).all())
    if total_movimentos:
        raise HTTPException(
            status_code=409,
            detail=(
                f'Não é possível excluir "{item.nome}" — há {total_movimentos} movimento(s) de estoque '
                'vinculado(s) a ele. Desative o item (campo "Ativo") em vez de excluir.'
            ),
        )
    session.delete(item)
    session.commit()
    return {"excluido": True}


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
    medicamentos ligados ao princípio/doença apareçam mesmo sem o campo texto.

    `incluir_sem_estoque` também acrescenta, pra critério `principio_ativo` ou
    `doenca`, toda marca comercial cadastrada (`MedicamentoComercial`) que
    ainda não tem item de Estoque nenhum — mesmo mecanismo de
    `estoque_baixa.opcoes_medicamento` (usado no picker de Central de
    Protocolos/Agenda), só que aqui o resultado é achatado no mesmo formato
    de item de estoque, com `estoque_id: None` e `sem_estoque: True`, porque
    o Protocolo Sanitário resolve o medicamento pelo NOME digitado no
    lançamento (`escolhas_medicamento`), não por estoque_id."""
    from fazenda.models import Doenca, IndicacaoTerapeutica, MedicamentoComercial, PrincipioAtivo

    fazenda_id = fazenda_id_seguro(fazenda_id)

    algum_criterio = bool(principio_ativo or classificacao or doenca or finalidade)

    # Catálogo (princípio ativo, doença) é global + da fazenda — ver
    # rules/visibilidade. Estoque é dado real da fazenda: filtro estrito.
    query_pa = visivel(select(PrincipioAtivo), PrincipioAtivo, fazenda_id)
    query_doenca = visivel(select(Doenca), Doenca, fazenda_id)
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)

    pa_ids: set[int] = set()
    if principio_ativo:
        alvo = principio_ativo.strip().lower()
        for pa in session.exec(query_pa).all():
            if (pa.nome or "").strip().lower() == alvo:
                pa_ids.add(pa.id)

    # Doença → princípios ativos ligados a ela: pelo vínculo direto
    # PrincipioAtivo.doenca_id (1-pra-1, só biológicos) E pela indicação
    # terapêutica N-pra-N (IndicacaoTerapeutica — o caso geral, ex.: um
    # antibiótico tratando mais de uma doença). Sem a segunda parte, um
    # protocolo cadastrado "por doença" só encontrava vacina — nunca o
    # antibiótico/anti-inflamatório indicado pra ela.
    pa_ids_doenca: set[int] = set()
    if doenca:
        alvo_d = doenca.strip().lower()
        doenca_ids = {d.id for d in session.exec(query_doenca).all() if (d.nome or "").strip().lower() == alvo_d}
        for pa in session.exec(query_pa).all():
            if pa.doenca_id in doenca_ids:
                pa_ids_doenca.add(pa.id)
        query_ind = visivel(
            select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.doenca_id.in_(doenca_ids)),
            IndicacaoTerapeutica, fazenda_id,
        )
        for ind in session.exec(query_ind).all():
            pa_ids_doenca.add(ind.principio_ativo_id)

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
    # Cache de marcas por princípio ativo — carrega uma vez por pa_id (não uma
    # vez por item) para casar cada item de Estoque com sua carência/bula sem
    # repetir a mesma query dezenas de vezes num catálogo grande.
    marcas_por_pa: dict[int, list] = {}

    def _marcas_do(pa_id: int | None) -> list:
        if pa_id is None:
            return []
        if pa_id not in marcas_por_pa:
            marcas_por_pa[pa_id] = session.exec(
                select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == pa_id)
            ).all()
        return marcas_por_pa[pa_id]

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
        marca = resolver_marca_comercial(
            session, item=e, principio_ativo_id=e.principio_ativo_id, candidatos=_marcas_do(e.principio_ativo_id),
        )
        saida.append({
            "nome": e.nome, "unidade": e.unidade, "quantidade": e.quantidade,
            "principio_ativo": e.principio_ativo, "classificacao_medicamento": e.classificacao_medicamento,
            "laboratorio": e.laboratorio, "estoque_id": e.id, "sem_estoque": False,
            "carencia": carencia_para_item(e, marca),
            "proibido_lactacao": bool(marca.proibido_lactacao) if marca else False,
            "alerta": marca.alerta if marca else None,
        })

    # incluir_sem_estoque + critério por princípio ativo/doença: acrescenta
    # toda marca comercial do catálogo que ainda não apareceu acima (nenhum
    # item de Estoque criado pra ela) — dá liberdade pro operador escolher o
    # que realmente usou mesmo sem frasco cadastrado. Só faz sentido pra
    # princípio ativo/doença: "classificação"/"finalidade" não têm uma marca
    # comercial associada diretamente (são agrupamentos do item de estoque).
    pa_ids_sem_estoque = pa_ids | pa_ids_doenca if incluir_sem_estoque else set()
    if pa_ids_sem_estoque:
        ja_listados = {(x["nome"] or "").strip().lower() for x in saida}
        query_mc = visivel(
            select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id.in_(pa_ids_sem_estoque)),
            MedicamentoComercial, fazenda_id,
        )
        for mc in session.exec(query_mc).all():
            nome_norm = (mc.nome_comercial or "").strip().lower()
            if not nome_norm or nome_norm in ja_listados:
                continue
            ja_listados.add(nome_norm)
            saida.append({
                "nome": mc.nome_comercial, "unidade": None, "quantidade": None,
                "principio_ativo": None, "classificacao_medicamento": None,
                "laboratorio": mc.laboratorio, "estoque_id": None, "sem_estoque": True,
                "carencia": carencia_para_item(None, mc),
                "proibido_lactacao": bool(mc.proibido_lactacao),
                "alerta": mc.alerta,
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
    delta = -dados.quantidade if baixa else dados.quantidade
    incrementar_quantidade_atomico(session, "estoque", item.id, "quantidade", delta)
    session.flush()
    session.refresh(item)
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
            incrementar_quantidade_atomico(session, "estoque_semen", touro.id, "doses", round(delta))
            session.flush()
            session.refresh(touro)
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
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    item = _criar_movimento_estoque(dados, session, usuario_id=user.id, fazenda_id=fazenda_id)
    return item.model_dump()


class MovimentoEditIn(BaseModel):
    """Edição de um `MovimentoEstoque` lançado manualmente (G1). Não permite
    trocar `nome`/`movimento` — isso é excluir e relançar, não editar.
    `extra="allow"` só para conseguirmos detectar `nome`/`movimento` no corpo
    e devolver uma mensagem de erro explicativa em vez do 422 genérico do
    FastAPI para campo desconhecido."""

    model_config = {"extra": "allow"}

    quantidade: float
    unidade: str | None = None
    data_movimento: date
    observacao: str | None = None


def _resolver_item_do_movimento(mov: MovimentoEstoque, session: Session, fazenda_id: int | None) -> Estoque | None:
    """`MovimentoEstoque.estoque_id` pode ser `None` em movimentos legados —
    nesse caso resolve o item por `nome_item` + `fazenda_id`, igual ao
    lançamento (`_criar_movimento_estoque`)."""
    if mov.estoque_id:
        item = session.get(Estoque, mov.estoque_id)
        if item:
            return item
    query_item = select(Estoque).where(Estoque.nome == mov.nome_item)
    if fazenda_id is not None:
        query_item = query_item.where(Estoque.fazenda_id == fazenda_id)
    return session.exec(query_item).first()


@router.put("/movimentos/{movimento_id}")
def editar_movimento_estoque(
    movimento_id: int, dados: MovimentoEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Edita quantidade/unidade/data/observação de um movimento manual
    (`origem_tipo is None`). Aplica o *delta* da quantidade no saldo do item
    (e no `EstoqueSemen.doses`, quando o item for de sêmen) — não refaz o
    movimento do zero, para não perder o histórico de outros movimentos do
    mesmo item entre o lançamento original e esta edição."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    extras = dados.model_extra or {}
    if "nome" in extras or "movimento" in extras:
        raise HTTPException(
            status_code=400,
            detail="Não é possível trocar o item ou o tipo (entrada/saída) de um movimento existente — "
            "exclua este movimento e lance um novo.",
        )
    mov = session.get(MovimentoEstoque, movimento_id)
    if not mov or (fazenda_id is not None and mov.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Movimento de estoque não encontrado")
    if mov.origem_tipo is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Este movimento foi gerado por um lançamento de {mov.origem_tipo} — desfaça pelo próprio "
            "lançamento (Sanidade, Protocolo, Secagem…), não pelo histórico de estoque.",
        )
    if mov.pedido_item_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Esta entrada está vinculada a um item de pedido — desfaça pelo Pedido.",
        )
    if dados.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero")

    item = _resolver_item_do_movimento(mov, session, fazenda_id)
    if not item:
        raise HTTPException(status_code=404, detail=f'Item de estoque "{mov.nome_item}" não encontrado')

    sinal = -1 if mov.movimento in MOVIMENTOS_SAIDA else 1
    delta = sinal * (dados.quantidade - mov.quantidade)
    incrementar_quantidade_atomico(session, "estoque", item.id, "quantidade", delta)
    session.flush()
    session.refresh(item)
    if item.estoque_minimo is not None:
        item.abaixo_minimo = item.quantidade < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)

    if item.estoque_semen_id:
        touro = session.get(EstoqueSemen, item.estoque_semen_id)
        if touro:
            incrementar_quantidade_atomico(session, "estoque_semen", touro.id, "doses", round(delta))
            session.flush()
            session.refresh(touro)
            touro.atualizado_em = datetime.utcnow()
            session.add(touro)

    mov.quantidade = dados.quantidade
    mov.unidade = dados.unidade
    mov.data_movimento = dados.data_movimento
    mov.observacao = dados.observacao
    session.add(mov)
    session.commit()
    session.refresh(mov)
    session.refresh(item)

    return {**mov.model_dump(), "saldo_item": item.quantidade}
