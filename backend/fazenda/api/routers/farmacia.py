"""
Router da Farmácia — o estoque de medicamentos/hormônios/vacinas organizado pela
hierarquia PRINCÍPIO ATIVO → marcas comerciais → apresentações (itens de
estoque). Expõe a visão gerencial unificada (somatório por princípio, mínimo por
apresentações, alerta de "inicializar estoque") e os utilitários usados no
curral: listar apresentações para o menu "qual frasco você está usando?" e
registrar o estoque inicial/primeira compra (gatilho de comunicação).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Doenca, Estoque, IndicacaoTerapeutica, MedicamentoComercial, MovimentoEstoque, ParametroMinimoFarmacia, PrincipioAtivo,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.validacao import link_http_seguro
from fazenda.rules.busca import normalizar_busca
from fazenda.rules.carencia import carencia_dict
from fazenda.rules.farmacia import resumo_principios
from fazenda.rules.farmacia_multi_principio import checar_e_desvincular_exclusao_principio
from fazenda.rules.visibilidade import visivel

router = APIRouter(prefix="/farmacia", tags=["farmacia"])


@router.get("/principios")
def listar_principios(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Visão gerencial completa: princípio → total unificado, apresentações,
    mínimo/alerta e a lista de itens de estoque (marcas/tamanhos)."""
    return resumo_principios(session, fazenda_id_seguro(fazenda_id))


@router.get("/principios/{principio_id}")
def detalhar_principio(
    principio_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa = session.get(PrincipioAtivo, principio_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Princípio ativo não encontrado")
    resumo = next((r for r in resumo_principios(session, fazenda_id) if r["id"] == principio_id), None)
    marcas = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == principio_id)
        .order_by(MedicamentoComercial.nome_comercial)
    ).all()
    return {**(resumo or {}), "marcas": [m.model_dump() for m in marcas]}


class PrincipioIn(BaseModel):
    nome: str
    ativo: bool = True
    categoria_software: str | None = None
    uso_principal: str | None = None
    justificativa: str | None = None
    doenca_id: int | None = None
    eh_biologico: bool = False
    unidade_base: str | None = None
    unidade_apresentacao: str | None = None
    estoque_minimo_apresentacoes: float = 1.0


@router.post("/principios", status_code=201)
def criar_principio(
    dados: PrincipioIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(PrincipioAtivo).where(PrincipioAtivo.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(PrincipioAtivo.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe o princípio ativo '{nome}'")
    pa = PrincipioAtivo(**{**dados.model_dump(), "nome": nome, "fazenda_id": fazenda_id})
    session.add(pa)
    session.commit()
    session.refresh(pa)
    return pa.model_dump()


@router.put("/principios/{principio_id}")
def atualizar_principio(
    principio_id: int, dados: PrincipioIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa = session.get(PrincipioAtivo, principio_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Princípio ativo não encontrado")
    for k, v in dados.model_dump().items():
        setattr(pa, k, v)
    session.add(pa)
    session.commit()
    session.refresh(pa)
    return pa.model_dump()


@router.delete("/principios/{principio_id}")
def excluir_principio(
    principio_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Exclui um princípio ativo checando impacto nas 7 tabelas que hoje têm
    FK pra ele — mesma regra de `POST /exclusoes/impacto` (tipo=
    principio_ativo), extraída pra rules/farmacia_multi_principio.py."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa = session.get(PrincipioAtivo, principio_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Princípio ativo não encontrado")
    impacto, alvos = checar_e_desvincular_exclusao_principio(session, pa)
    for obj in alvos:
        session.delete(obj)
    session.commit()
    return {"excluido": True, "impacto": impacto}


class EstoqueMinimoIn(BaseModel):
    estoque_minimo_base: float


@router.put("/principios/{principio_id}/estoque-minimo")
def definir_estoque_minimo_base(
    principio_id: int, dados: EstoqueMinimoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Define o estoque mínimo de UM princípio ativo, em `unidade_base` (ml/L/
    g/unidade) — pedido do usuário (31/08/2026): "estoque mínimo... tem que
    ser em unidade de medida, e não em pacotes/frascos". Um princípio de
    cada vez, ação deliberada — nunca em lote, nunca automática (ver
    docstring de ParametroMinimoFarmacia).

    Grava numa tabela À PARTE do princípio (nunca no próprio `PrincipioAtivo`,
    que pode ser um registro GLOBAL do catálogo padrão CowData e nunca é
    clonado) — por isso funciona também para princípios globais que esta
    fazenda usa, sem afetar o mínimo de nenhuma outra fazenda-cliente."""
    if dados.estoque_minimo_base < 0:
        raise HTTPException(status_code=400, detail="Estoque mínimo não pode ser negativo")
    pa = session.exec(visivel(select(PrincipioAtivo).where(PrincipioAtivo.id == principio_id), PrincipioAtivo, fazenda_id)).first()
    if not pa:
        raise HTTPException(status_code=404, detail="Princípio ativo não encontrado")
    if not pa.unidade_base:
        raise HTTPException(
            status_code=400,
            detail=f"'{pa.nome}' ainda não tem unidade de medida (unidade_base) cadastrada — defina-a antes do mínimo.",
        )
    existente = session.exec(
        select(ParametroMinimoFarmacia).where(
            ParametroMinimoFarmacia.fazenda_id == fazenda_id, ParametroMinimoFarmacia.principio_ativo_id == principio_id,
        )
    ).first()
    if existente:
        existente.estoque_minimo_base = dados.estoque_minimo_base
        existente.atualizado_em = datetime.utcnow()
        session.add(existente)
    else:
        session.add(ParametroMinimoFarmacia(
            fazenda_id=fazenda_id, principio_ativo_id=principio_id, estoque_minimo_base=dados.estoque_minimo_base,
        ))
    session.commit()
    resumo = next((r for r in resumo_principios(session, fazenda_id) if r["id"] == principio_id), None)
    return resumo or {"ok": True}


class MarcaIn(BaseModel):
    principio_ativo_id: int
    nome_comercial: str
    laboratorio: str | None = None
    ativo: bool = True
    # ── Bula (editável por fazenda — ver MedicamentoComercial em models/sanidade.py) ──
    uso_principal: str | None = None
    concentracao: str | None = None
    dose_padrao: float | None = None
    unidade_dose: str | None = None
    dose_base: str | None = None
    dose_referencia_kg: float | None = None
    dose_texto: str | None = None
    via_padrao: str | None = None
    link_bula: str | None = None
    carencia_leite_dias: int | None = None
    carencia_carne_dias: int | None = None
    proibido_lactacao: bool | None = None
    alerta_gestacao: bool | None = None
    alerta: str | None = None

    # BUG DE SEGURANÇA CORRIGIDO: link_bula vira <a href> no frontend — sem
    # validar o esquema, um valor "javascript:..." executava no clique.
    @field_validator("link_bula")
    @classmethod
    def _validar_link_bula(cls, v: str | None) -> str | None:
        return link_http_seguro(v)


@router.post("/medicamentos", status_code=201)
def criar_marca(
    dados: MarcaIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    nome = dados.nome_comercial.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome comercial é obrigatório")
    pa = session.get(PrincipioAtivo, dados.principio_ativo_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Princípio ativo inexistente")
    existe = session.exec(
        select(MedicamentoComercial).where(
            MedicamentoComercial.principio_ativo_id == dados.principio_ativo_id,
            MedicamentoComercial.nome_comercial == nome,
        )
    ).first()
    if existe:
        raise HTTPException(status_code=409, detail=f"'{nome}' já está cadastrado neste princípio")
    m = MedicamentoComercial(**{**dados.model_dump(), "nome_comercial": nome, "fazenda_id": fazenda_id})
    session.add(m)
    session.commit()
    session.refresh(m)
    return m.model_dump()


@router.put("/medicamentos/{marca_id}")
def atualizar_marca(
    marca_id: int, dados: MarcaIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Edita uma marca comercial — inclusive os campos de bula.

    404 de verdade só quando o registro é de OUTRA fazenda (isolamento) ou não
    existe. Quando a marca é GLOBAL (padrão CowData) e há uma fazenda
    resolvida, a edição personaliza automaticamente num passo só: clona a(s)
    indicação(ões) que usam o princípio dessa marca (ver `_clonar_doenca`) e
    aplica a edição no clone da fazenda — o global nunca é tocado. A resposta
    inclui `personalizou_automaticamente` para a tela avisar o usuário.

    `fazenda_id` vem de `get_fazenda_id_escrita` (nunca None em produção) —
    antes, com o resolvedor tolerante, um token legado sem "fid" (mesmo de um
    usuário vinculado a uma única fazenda de verdade) caía no ramo "sem
    fazenda resolvida" abaixo e editava o registro GLOBAL direto, vazando a
    edição de UMA fazenda pro catálogo padrão de TODAS as outras.
    """
    m = session.get(MedicamentoComercial, marca_id)
    if not m:
        raise HTTPException(status_code=404, detail="Marca não encontrada")

    personalizou = False
    if m.fazenda_id is not None:
        if fazenda_id is None or m.fazenda_id != fazenda_id:
            raise HTTPException(status_code=404, detail="Marca não encontrada")
    elif fazenda_id is not None:
        for doenca_id in _doencas_globais_do_principio(session, m.principio_ativo_id):
            doenca = session.get(Doenca, doenca_id)
            if doenca is not None:
                _clonar_doenca(session, doenca, fazenda_id)
        m = _clonar_marca(session, m, fazenda_id)
        personalizou = True

    for k, v in dados.model_dump().items():
        setattr(m, k, v)
    session.add(m)
    session.commit()
    session.refresh(m)
    return {
        **m.model_dump(),
        "carencia": carencia_dict(m.carencia_leite_dias, m.carencia_carne_dias, m.proibido_lactacao),
        "personalizou_automaticamente": personalizou,
    }


@router.delete("/medicamentos/{marca_id}")
def excluir_marca(
    marca_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    m = session.get(MedicamentoComercial, marca_id)
    if not m or (fazenda_id is not None and m.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    session.delete(m)
    session.commit()
    return {"ok": True}


@router.get("/apresentacoes")
def listar_apresentacoes(
    principio_ativo_id: int | None = None, produto: str | None = None, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Apresentações (frascos/potes) em estoque de um princípio — alimenta o menu
    "qual frasco você está usando?" no lançamento da aplicação. Pode filtrar pelo
    princípio ou pelo nome de um produto (deriva o princípio dele).

    Restrito à fazenda atual: sem o filtro, o menu listava os frascos de TODAS as
    fazendas, expondo o estoque de uma cliente para outra."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa_id = principio_ativo_id
    if pa_id is None and produto:
        query_produto = select(Estoque).where(Estoque.nome == produto)
        if fazenda_id is not None:
            query_produto = query_produto.where(Estoque.fazenda_id == fazenda_id)
        item = session.exec(query_produto).first()
        pa_id = item.principio_ativo_id if item else None
    if pa_id is None:
        return []
    query_itens = select(Estoque).where(Estoque.principio_ativo_id == pa_id)
    if fazenda_id is not None:
        query_itens = query_itens.where(Estoque.fazenda_id == fazenda_id)
    itens = session.exec(query_itens.order_by(Estoque.nome)).all()
    return [
        {
            "estoque_id": it.id, "nome": it.nome, "marca": it.laboratorio,
            "saldo": it.quantidade or 0, "unidade": it.unidade,
            "volume_por_apresentacao": it.volume_por_apresentacao, "volume_unidade": it.volume_unidade,
            "estoque_inicializado": it.estoque_inicializado is not False,
        }
        for it in itens
    ]


class InicializarIn(BaseModel):
    quantidade: float
    data: date | None = None
    observacao: str | None = None


@router.post("/estoque/{estoque_id}/inicializar")
def inicializar_estoque(
    estoque_id: int, dados: InicializarIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Registra o Estoque Inicial / Primeira Compra de um item: define o saldo,
    liga o gatilho (a partir daqui aplicações e dietas passam a dar baixa real) e
    grava o movimento para o histórico."""
    item = session.get(Estoque, estoque_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    if dados.quantidade < 0:
        raise HTTPException(status_code=400, detail="Quantidade não pode ser negativa")
    item.quantidade = dados.quantidade
    item.estoque_inicializado = True
    if item.estoque_minimo is not None:
        item.abaixo_minimo = (item.quantidade or 0) < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.add(MovimentoEstoque(
        nome_item=item.nome, movimento="Estoque inicial", quantidade=dados.quantidade,
        unidade=item.unidade, data_movimento=dados.data or date.today(),
        observacao=dados.observacao or "Estoque inicial — início do controle de baixas",
        # `fazenda_id` não era gravado aqui (bug pré-existente, achado nesta
        # varredura) — o movimento nascia sempre órfão, mesmo com o item de
        # Estoque de origem já escopado corretamente.
        fazenda_id=fazenda_id, estoque_id=item.id, valor_unitario=item.valor_unitario,
    ))
    session.commit()
    return {"ok": True, "estoque_inicializado": True, "quantidade": item.quantidade}


# ── Indicações terapêuticas (princípio ativo ↔ doença ↔ prioridade) ─────────
# Base do "substituto inteligente": gerenciado na edição do princípio ativo
# (Configurações > Cadastro > Sanitário > Princípio ativo), consultado por
# doença em GET /sanidade/indicacoes-doenca/{id}.
@router.get("/indicacoes")
def listar_indicacoes(
    principio_ativo_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = visivel(
        select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.principio_ativo_id == principio_ativo_id),
        IndicacaoTerapeutica, fazenda_id,
    )
    indicacoes = session.exec(query.order_by(IndicacaoTerapeutica.prioridade)).all()
    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    return [
        {"id": i.id, "doenca_id": i.doenca_id, "doenca": doencas.get(i.doenca_id, "—"), "prioridade": i.prioridade}
        for i in indicacoes
    ]


class IndicacaoIn(BaseModel):
    principio_ativo_id: int
    doenca_id: int
    prioridade: int = 2


@router.post("/indicacoes", status_code=201)
def criar_indicacao(
    dados: IndicacaoIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pa = session.get(PrincipioAtivo, dados.principio_ativo_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Princípio ativo inexistente")
    doenca = session.get(Doenca, dados.doenca_id)
    if not doenca or (fazenda_id is not None and doenca.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Doença inexistente")
    if dados.prioridade < 1:
        raise HTTPException(status_code=400, detail="Prioridade deve ser 1 ou maior")
    existe = session.exec(
        select(IndicacaoTerapeutica).where(
            IndicacaoTerapeutica.principio_ativo_id == dados.principio_ativo_id,
            IndicacaoTerapeutica.doenca_id == dados.doenca_id,
            IndicacaoTerapeutica.fazenda_id == fazenda_id,
        )
    ).first()
    if existe:
        raise HTTPException(status_code=409, detail=f"'{pa.nome}' já está indicado para '{doenca.nome}'")
    ind = IndicacaoTerapeutica(**dados.model_dump(), fazenda_id=fazenda_id)
    session.add(ind)
    session.commit()
    session.refresh(ind)
    return {"id": ind.id, "doenca_id": ind.doenca_id, "doenca": doenca.nome, "prioridade": ind.prioridade}


@router.delete("/indicacoes/{indicacao_id}")
def excluir_indicacao(
    indicacao_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    ind = session.get(IndicacaoTerapeutica, indicacao_id)
    if not ind or (fazenda_id is not None and ind.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Indicação não encontrada")
    session.delete(ind)
    session.commit()
    return {"ok": True}


class IndicacaoUpdateIn(BaseModel):
    prioridade: int = 2
    nota: str | None = None


@router.put("/indicacoes/{indicacao_id}")
def atualizar_indicacao(
    indicacao_id: int, dados: IndicacaoUpdateIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Edita prioridade/nota de um vínculo princípio↔doença.

    Mesma lógica de `atualizar_marca`: 404 de verdade só para vínculo de
    OUTRA fazenda ou inexistente. Vínculo GLOBAL (`fazenda_id` nulo) com
    fazenda resolvida personaliza a indicação automaticamente (clona a
    Doenca inteira via `_clonar_doenca`) e edita o vínculo já no clone.
    """
    ind = session.get(IndicacaoTerapeutica, indicacao_id)
    if not ind:
        raise HTTPException(status_code=404, detail="Indicação não encontrada")

    personalizou = False
    if ind.fazenda_id is not None:
        if fazenda_id is None or ind.fazenda_id != fazenda_id:
            raise HTTPException(status_code=404, detail="Indicação não encontrada")
    elif fazenda_id is not None:
        doenca = session.get(Doenca, ind.doenca_id)
        if not doenca or (doenca.fazenda_id is not None and doenca.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Indicação não encontrada")
        if doenca.fazenda_id is None:
            _clonar_doenca(session, doenca, fazenda_id)
        ind_clone = session.exec(
            select(IndicacaoTerapeutica).where(
                IndicacaoTerapeutica.origem_id == ind.id, IndicacaoTerapeutica.fazenda_id == fazenda_id,
            )
        ).first()
        if ind_clone is None:
            raise HTTPException(status_code=404, detail="Indicação não encontrada")
        ind = ind_clone
        personalizou = True

    if dados.prioridade < 1:
        raise HTTPException(status_code=400, detail="Prioridade deve ser 1 ou maior")
    ind.prioridade = dados.prioridade
    ind.nota = dados.nota
    session.add(ind)
    session.commit()
    session.refresh(ind)
    return {
        "id": ind.id, "doenca_id": ind.doenca_id, "principio_ativo_id": ind.principio_ativo_id,
        "prioridade": ind.prioridade, "nota": ind.nota,
        "personalizou_automaticamente": personalizou,
    }


# ── Catálogo de indicações da aba Farmácia (personalização por fazenda) ────
# Tela única que junta INDICAÇÃO (Doenca) → PRINCÍPIOS que tratam (via
# IndicacaoTerapeutica, com prioridade/nota) → MARCAS de cada princípio (com a
# bula completa). O catálogo nasce global (fazenda_id nulo); é só leitura
# para todas as fazendas até alguém editar algo. Editar um campo do padrão
# (bula de marca, prioridade/nota do vínculo) PERSONALIZA (clona) a indicação
# automaticamente, num passo só — ver PUT /medicamentos, PUT /indicacoes e
# os helpers `_clonar_doenca`/`_clonar_marca` logo abaixo. O botão
# POST/DELETE .../personalizar continua existindo para quem prefere
# personalizar antes de editar, mas deixou de ser pré-requisito. Nos dois
# caminhos o global nunca é alterado, e 404 continua reservado a registro de
# OUTRA fazenda ou inexistente — isolamento, não fricção de UX.

def _sem_duplicata_do_padrao(itens: list, fazenda_id: int | None) -> list:
    """Some com a linha GLOBAL quando a fazenda atual já tem um clone dela
    (`origem_id` apontando para o id da linha global) — sem isso a tela
    mostraria o padrão E a personalização lado a lado, duplicado. Genérica:
    serve tanto para `Doenca` quanto para `MedicamentoComercial` (mesmo trio
    de campos id/fazenda_id/origem_id nos dois modelos)."""
    if fazenda_id is None:
        return itens
    clonados = {it.origem_id for it in itens if it.fazenda_id == fazenda_id and it.origem_id}
    return [it for it in itens if not (it.fazenda_id is None and it.id in clonados)]


def _clonar_marca(session: Session, marca: MedicamentoComercial, fazenda_id: int) -> MedicamentoComercial:
    """Clona uma MedicamentoComercial GLOBAL para a fazenda — idempotente (se
    já existe um clone com `origem_id` apontando pra esta marca, devolve ele
    em vez de duplicar). Assume `marca.fazenda_id is None`; quem chama já
    garantiu isso."""
    existente = session.exec(
        select(MedicamentoComercial).where(
            MedicamentoComercial.origem_id == marca.id, MedicamentoComercial.fazenda_id == fazenda_id,
        )
    ).first()
    if existente is not None:
        return existente
    clone = MedicamentoComercial(
        principio_ativo_id=marca.principio_ativo_id, nome_comercial=marca.nome_comercial,
        laboratorio=marca.laboratorio, ativo=marca.ativo,
        uso_principal=marca.uso_principal, concentracao=marca.concentracao,
        dose_padrao=marca.dose_padrao, unidade_dose=marca.unidade_dose,
        dose_base=marca.dose_base, dose_referencia_kg=marca.dose_referencia_kg,
        dose_texto=marca.dose_texto, via_padrao=marca.via_padrao, link_bula=marca.link_bula,
        carencia_leite_dias=marca.carencia_leite_dias, carencia_carne_dias=marca.carencia_carne_dias,
        proibido_lactacao=marca.proibido_lactacao, alerta_gestacao=marca.alerta_gestacao,
        alerta=marca.alerta, fazenda_id=fazenda_id, origem_id=marca.id,
    )
    session.add(clone)
    session.commit()
    session.refresh(clone)
    return clone


def _clonar_doenca(session: Session, doenca: Doenca, fazenda_id: int) -> Doenca:
    """A trava de personalização, extraída para ser reutilizada tanto pelo
    POST .../personalizar explícito quanto pela personalização automática de
    PUT /medicamentos e PUT /indicacoes: clona a indicação global (Doenca +
    IndicacaoTerapeutica + as MedicamentoComercial dos princípios envolvidos,
    via `_clonar_marca`) para a fazenda atual.

    NUNCA clona `PrincipioAtivo` — é a âncora de `Estoque.principio_ativo_id`
    da fazenda e de todo o histórico de baixa (MovimentoEstoque, Sanidade
    referenciam o item de estoque, que referencia o princípio). Clonar o
    princípio criaria um segundo id para a mesma molécula e quebraria esse
    vínculo para todo item de estoque e toda aplicação já lançada.

    Idempotente: se a fazenda já tem um clone desta doença (`origem_id`
    apontando pra cá), devolve o clone existente em vez de duplicar. Assume
    `doenca.fazenda_id is None`; quem chama já garantiu isso.
    """
    clone = session.exec(
        select(Doenca).where(Doenca.origem_id == doenca.id, Doenca.fazenda_id == fazenda_id)
    ).first()
    if clone is not None:
        return clone

    clone = Doenca(
        nome=doenca.nome, tipo=doenca.tipo, descricao=doenca.descricao, ativo=doenca.ativo,
        fazenda_id=fazenda_id, origem_id=doenca.id,
    )
    session.add(clone)
    session.commit()
    session.refresh(clone)

    indicacoes_originais = session.exec(
        visivel(
            select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.doenca_id == doenca.id),
            IndicacaoTerapeutica, fazenda_id,
        )
    ).all()
    for orig in indicacoes_originais:
        session.add(IndicacaoTerapeutica(
            principio_ativo_id=orig.principio_ativo_id, doenca_id=clone.id,
            prioridade=orig.prioridade, nota=orig.nota,
            fazenda_id=fazenda_id, origem_id=orig.id,
        ))
    session.commit()

    # Marcas comerciais dos princípios envolvidos — só as GLOBAIS (a fazenda
    # pode já ter a própria/clonada de uma personalização anterior que
    # compartilha o mesmo princípio; `_clonar_marca` não duplica).
    principios_ids = {i.principio_ativo_id for i in indicacoes_originais}
    for pid in principios_ids:
        marcas_globais = session.exec(
            select(MedicamentoComercial).where(
                MedicamentoComercial.principio_ativo_id == pid, MedicamentoComercial.fazenda_id.is_(None),
            )
        ).all()
        for marca in marcas_globais:
            _clonar_marca(session, marca, fazenda_id)

    return clone


def _doencas_globais_do_principio(session: Session, principio_ativo_id: int) -> set[int]:
    """Ids das Doenca GLOBAIS indicadas (via IndicacaoTerapeutica global) para
    este princípio — usado pela personalização automática de PUT
    /medicamentos: ao editar uma marca do padrão, personaliza também a(s)
    indicação(ões) que a usam."""
    return {
        i.doenca_id for i in session.exec(
            select(IndicacaoTerapeutica).where(
                IndicacaoTerapeutica.principio_ativo_id == principio_ativo_id,
                IndicacaoTerapeutica.fazenda_id.is_(None),
            )
        ).all()
    }


def _montar_indicacao_dict(
    session: Session, doenca: Doenca, fazenda_id: int | None,
    resumo_por_pa: dict[int, dict], principios_cache: dict[int, PrincipioAtivo | None],
) -> dict:
    """Monta uma linha completa do catálogo (indicação → princípios → marcas)
    para a resposta de GET /indicacoes-catalogo e do POST .../personalizar."""
    indicacoes = session.exec(
        visivel(
            select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.doenca_id == doenca.id),
            IndicacaoTerapeutica, fazenda_id,
        )
    ).all()

    principios_out = []
    for ind in indicacoes:
        pa = principios_cache.get(ind.principio_ativo_id)
        if pa is None and ind.principio_ativo_id not in principios_cache:
            pa = session.get(PrincipioAtivo, ind.principio_ativo_id)
            principios_cache[ind.principio_ativo_id] = pa
        if pa is None:
            continue  # princípio referenciado não existe mais — pula em silêncio

        marcas = session.exec(
            visivel(
                select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == pa.id),
                MedicamentoComercial, fazenda_id,
            )
        ).all()
        marcas = _sem_duplicata_do_padrao(marcas, fazenda_id)
        marcas.sort(key=lambda m: m.nome_comercial or "")

        resumo = resumo_por_pa.get(pa.id, {})
        principios_out.append({
            "id": pa.id,
            "nome": pa.nome,
            "categoria_software": pa.categoria_software,
            "prioridade": ind.prioridade,
            "nota": ind.nota,
            "indicacao_id": ind.id,  # id do vínculo — usado por PUT /indicacoes/{id}
            "abaixo_minimo": resumo.get("abaixo_minimo", False),
            "total_apresentacoes": resumo.get("total_apresentacoes", 0),
            "precisa_inicializar": resumo.get("precisa_inicializar", False),
            "marcas": [
                {
                    "id": m.id,
                    "nome_comercial": m.nome_comercial,
                    "laboratorio": m.laboratorio,
                    "uso_principal": m.uso_principal,
                    "concentracao": m.concentracao,
                    "dose_texto": m.dose_texto,
                    "dose_padrao": m.dose_padrao,
                    "unidade_dose": m.unidade_dose,
                    "via_padrao": m.via_padrao,
                    "link_bula": m.link_bula,
                    "alerta": m.alerta,
                    "alerta_gestacao": m.alerta_gestacao,
                    "carencia": carencia_dict(m.carencia_leite_dias, m.carencia_carne_dias, m.proibido_lactacao),
                    "editavel": fazenda_id is not None and m.fazenda_id == fazenda_id,
                }
                for m in marcas
            ],
        })
    principios_out.sort(key=lambda p: (p["prioridade"], p["nome"] or ""))

    return {
        "id": doenca.id,
        "nome": doenca.nome,
        "tipo": doenca.tipo,
        "descricao": doenca.descricao,
        "personalizada": fazenda_id is not None and doenca.fazenda_id == fazenda_id,
        "origem_id": doenca.origem_id,
        "principios": principios_out,
    }


@router.get("/indicacoes-catalogo")
def listar_indicacoes_catalogo(
    tipo: str | None = None, busca: str | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Alimenta a aba Farmácia: cada indicação (doença/manejo) com a cadeia
    completa princípios → marcas → bula/carência, pronta pra tela. `tipo`
    filtra por Doenca.tipo; `busca` casa (sem acento/caixa/hífen/underscore/
    espaço — rules/busca.py) pelo nome da indicação, do princípio ou da marca."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = visivel(select(Doenca), Doenca, fazenda_id)
    if tipo:
        query = query.where(Doenca.tipo == tipo)
    doencas = session.exec(query).all()
    doencas = _sem_duplicata_do_padrao(doencas, fazenda_id)
    doencas.sort(key=lambda d: (d.tipo or "", d.nome or ""))

    resumo_por_pa = {r["id"]: r for r in resumo_principios(session, fazenda_id)}
    principios_cache: dict[int, PrincipioAtivo | None] = {}
    saida = [_montar_indicacao_dict(session, d, fazenda_id, resumo_por_pa, principios_cache) for d in doencas]

    if busca:
        alvo = normalizar_busca(busca)

        def _casa(item: dict) -> bool:
            if alvo in normalizar_busca(item["nome"]):
                return True
            for p in item["principios"]:
                if alvo in normalizar_busca(p["nome"]):
                    return True
                if any(alvo in normalizar_busca(m["nome_comercial"]) for m in p["marcas"]):
                    return True
            return False

        saida = [item for item in saida if _casa(item)]

    return saida


@router.post("/indicacoes/{doenca_id}/personalizar", status_code=201)
def personalizar_indicacao(
    doenca_id: int, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Personalização explícita e manual (o botão "Personalizar para minha
    fazenda"): clona a indicação global via `_clonar_doenca` — a mesma
    função que a personalização automática de PUT /medicamentos e PUT
    /indicacoes usa por baixo dos panos ao editar direto num campo do
    padrão. Continua útil pra quem prefere personalizar antes de editar, mas
    deixou de ser pré-requisito para editar.

    Idempotente: se a fazenda já tem um clone desta doença (`origem_id`
    apontando pra cá), devolve o clone existente em vez de duplicar.
    """
    if fazenda_id is None:
        raise HTTPException(status_code=400, detail="Fazenda não resolvida — não é possível personalizar")

    doenca = session.get(Doenca, doenca_id)
    if not doenca or (doenca.fazenda_id is not None and doenca.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Indicação não encontrada")
    if doenca.fazenda_id == fazenda_id:
        raise HTTPException(status_code=400, detail="Esta indicação já é da fazenda — nada para personalizar")

    clone = _clonar_doenca(session, doenca, fazenda_id)

    resumo_por_pa = {r["id"]: r for r in resumo_principios(session, fazenda_id)}
    return _montar_indicacao_dict(session, clone, fazenda_id, resumo_por_pa, {})


@router.delete("/indicacoes/{doenca_id}/personalizar")
def despersonalizar_indicacao(
    doenca_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Desfaz a personalização: apaga o clone da fazenda (a Doenca, suas
    IndicacaoTerapeutica e as MedicamentoComercial clonadas dos princípios
    envolvidos) e volta a enxergar o catálogo padrão global.

    Só apaga linha com `origem_id` preenchido — nunca uma indicação ou marca
    que o produtor tenha criado do zero em cima do clone (ex.: adicionou um
    princípio extra à indicação personalizada). Marca clonada só é removida
    se nenhuma outra indicação desta fazenda ainda usa o mesmo princípio —
    marcas são compartilhadas entre indicações que citam o mesmo princípio.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    doenca = session.get(Doenca, doenca_id)
    if not doenca or doenca.origem_id is None or (fazenda_id is not None and doenca.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Não é uma personalização desta fazenda")

    indicacoes_clonadas = session.exec(
        select(IndicacaoTerapeutica).where(
            IndicacaoTerapeutica.doenca_id == doenca.id,
            IndicacaoTerapeutica.fazenda_id == fazenda_id,
            IndicacaoTerapeutica.origem_id.is_not(None),
        )
    ).all()
    principios_ids = {i.principio_ativo_id for i in indicacoes_clonadas}
    for ind in indicacoes_clonadas:
        session.delete(ind)
    session.commit()

    for pid in principios_ids:
        ainda_em_uso = session.exec(
            select(IndicacaoTerapeutica).where(
                IndicacaoTerapeutica.principio_ativo_id == pid,
                IndicacaoTerapeutica.fazenda_id == fazenda_id,
            )
        ).first()
        if ainda_em_uso:
            continue
        marcas_clonadas = session.exec(
            select(MedicamentoComercial).where(
                MedicamentoComercial.principio_ativo_id == pid,
                MedicamentoComercial.fazenda_id == fazenda_id,
                MedicamentoComercial.origem_id.is_not(None),
            )
        ).all()
        for m in marcas_clonadas:
            session.delete(m)
    session.commit()

    session.delete(doenca)
    session.commit()
    return {"ok": True}
