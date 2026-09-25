"""
Painel CowData > Cotações — a CowData cotiza preços com os PRÓPRIOS
fornecedores (nunca os de uma fazenda-cliente) e atribui preços-base
sugeridos a um catálogo de produtos-padrão, que toda fazenda pode consultar
como referência em Cadastro > Estoque (leitura pública em
api/routers/estoque.py::precos_referencia_cowdata — nunca escreve, nunca
mostra fornecedor).

RLS: toda rota usa `Depends(get_session_manutencao)`, nunca `get_session` —
mesmo motivo de painel_cowdata_farmacia.py (o Painel CowData nunca tem
fazenda selecionada no token, e estas tabelas não têm fazenda_id nenhuma).

Consulta x edição: `_dep` (área "cotacoes") vai nas rotas de leitura;
`_dep_edicao` (área + `pode_editar_cotacoes`) vai em tudo que escreve —
mesma assimetria de Farmácia (ver fazenda/models/equipe_cowdata_acesso.py).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_area_painel_cowdata, exigir_permissao_painel_cowdata
from fazenda.database import get_session_manutencao
from fazenda.models import (
    ClassificacaoCowData, CotacaoCowData, CotacaoCowDataFornecedor, CotacaoCowDataItem,
    CotacaoCowDataResposta, FinalidadeCowData, FornecedorCowData, FornecedorCowDataClassificacao,
    FornecedorCowDataFinalidade, PrecoBaseSugerido, PrecoBaseSugeridoParticipanteMedia, ProdutoPadrao,
    ProdutoPadraoFinalidade, Usuario,
)
from fazenda.rules.cotacao_cowdata import rotulo_item_cotacao_cowdata, sugestoes_duplicata

router = APIRouter(prefix="/painel-cowdata/cotacoes", tags=["painel-cowdata-cotacoes"])

_dep = Depends(exigir_area_painel_cowdata("cotacoes"))
_dep_edicao = Depends(exigir_permissao_painel_cowdata("cotacoes", "pode_editar_cotacoes"))


# ---------------------------------------------------------------------------
# Classificações / Finalidades — cadastro simples, mesmo padrão de
# Laboratorio/CategoriaMedicamento em painel_cowdata_farmacia.py.
# ---------------------------------------------------------------------------
class NomeIn(BaseModel):
    nome: str
    ativo: bool = True


@router.get("/classificacoes")
def listar_classificacoes(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    linhas = session.exec(select(ClassificacaoCowData).order_by(ClassificacaoCowData.nome)).all()
    return [c.model_dump() for c in linhas]


@router.post("/classificacoes", status_code=201)
def criar_classificacao(dados: NomeIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    existente = session.exec(select(ClassificacaoCowData).where(ClassificacaoCowData.nome == nome)).first()
    if existente:
        return existente.model_dump()
    linha = ClassificacaoCowData(nome=nome, ativo=dados.ativo)
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha.model_dump()


@router.put("/classificacoes/{id}")
def editar_classificacao(id: int, dados: NomeIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    linha = session.get(ClassificacaoCowData, id)
    if not linha:
        raise HTTPException(status_code=404, detail="Classificação não encontrada")
    linha.nome = dados.nome.strip() or linha.nome
    linha.ativo = dados.ativo
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha.model_dump()


@router.get("/finalidades")
def listar_finalidades(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    linhas = session.exec(select(FinalidadeCowData).order_by(FinalidadeCowData.nome)).all()
    return [f.model_dump() for f in linhas]


@router.post("/finalidades", status_code=201)
def criar_finalidade(dados: NomeIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    existente = session.exec(select(FinalidadeCowData).where(FinalidadeCowData.nome == nome)).first()
    if existente:
        return existente.model_dump()
    linha = FinalidadeCowData(nome=nome, ativo=dados.ativo)
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha.model_dump()


@router.put("/finalidades/{id}")
def editar_finalidade(id: int, dados: NomeIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    linha = session.get(FinalidadeCowData, id)
    if not linha:
        raise HTTPException(status_code=404, detail="Finalidade não encontrada")
    linha.nome = dados.nome.strip() or linha.nome
    linha.ativo = dados.ativo
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha.model_dump()


# ---------------------------------------------------------------------------
# Fornecedores da CowData
# ---------------------------------------------------------------------------
class FornecedorCowDataIn(BaseModel):
    nome: str
    cnpj_cpf: str | None = None
    telefone: str | None = None
    email: str | None = None
    observacoes: str | None = None
    ativo: bool = True
    classificacao_ids: list[int] = []
    finalidade_ids: list[int] = []


def _montar_fornecedor_dict(session: Session, f: FornecedorCowData) -> dict:
    # Ver comentário equivalente em _montar_preco_dict — model_dump() não
    # recarrega um objeto expirado por conta própria.
    session.refresh(f)
    classificacoes = session.exec(
        select(ClassificacaoCowData)
        .join(FornecedorCowDataClassificacao, FornecedorCowDataClassificacao.classificacao_id == ClassificacaoCowData.id)
        .where(FornecedorCowDataClassificacao.fornecedor_cowdata_id == f.id)
    ).all()
    finalidades = session.exec(
        select(FinalidadeCowData)
        .join(FornecedorCowDataFinalidade, FornecedorCowDataFinalidade.finalidade_id == FinalidadeCowData.id)
        .where(FornecedorCowDataFinalidade.fornecedor_cowdata_id == f.id)
    ).all()
    dados = f.model_dump()
    dados["classificacoes"] = [{"id": c.id, "nome": c.nome} for c in classificacoes]
    dados["finalidades"] = [{"id": ff.id, "nome": ff.nome} for ff in finalidades]
    return dados


def _definir_vinculos_fornecedor(session: Session, fornecedor_id: int, classificacao_ids: list[int], finalidade_ids: list[int]) -> None:
    for vinculo in session.exec(select(FornecedorCowDataClassificacao).where(FornecedorCowDataClassificacao.fornecedor_cowdata_id == fornecedor_id)).all():
        session.delete(vinculo)
    for vinculo in session.exec(select(FornecedorCowDataFinalidade).where(FornecedorCowDataFinalidade.fornecedor_cowdata_id == fornecedor_id)).all():
        session.delete(vinculo)
    for cid in set(classificacao_ids):
        session.add(FornecedorCowDataClassificacao(fornecedor_cowdata_id=fornecedor_id, classificacao_id=cid))
    for fid in set(finalidade_ids):
        session.add(FornecedorCowDataFinalidade(fornecedor_cowdata_id=fornecedor_id, finalidade_id=fid))


@router.get("/fornecedores")
def listar_fornecedores(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    linhas = session.exec(select(FornecedorCowData).order_by(FornecedorCowData.nome)).all()
    return [_montar_fornecedor_dict(session, f) for f in linhas]


@router.post("/fornecedores", status_code=201)
def criar_fornecedor(dados: FornecedorCowDataIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    f = FornecedorCowData(
        nome=dados.nome.strip(), cnpj_cpf=dados.cnpj_cpf, telefone=dados.telefone, email=dados.email,
        observacoes=dados.observacoes, ativo=dados.ativo,
    )
    session.add(f)
    session.commit()
    session.refresh(f)
    _definir_vinculos_fornecedor(session, f.id, dados.classificacao_ids, dados.finalidade_ids)
    session.commit()
    return _montar_fornecedor_dict(session, f)


@router.put("/fornecedores/{id}")
def editar_fornecedor(id: int, dados: FornecedorCowDataIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    f = session.get(FornecedorCowData, id)
    if not f:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    f.nome = dados.nome.strip() or f.nome
    f.cnpj_cpf, f.telefone, f.email, f.observacoes, f.ativo = dados.cnpj_cpf, dados.telefone, dados.email, dados.observacoes, dados.ativo
    session.add(f)
    _definir_vinculos_fornecedor(session, f.id, dados.classificacao_ids, dados.finalidade_ids)
    session.commit()
    return _montar_fornecedor_dict(session, f)


# ---------------------------------------------------------------------------
# Produtos-padrão
# ---------------------------------------------------------------------------
class ProdutoPadraoIn(BaseModel):
    nome: str
    unidade: str | None = None
    classificacao_id: int | None = None
    medicamento_comercial_id: int | None = None
    finalidade_ids: list[int] = []
    ativo: bool = True


def _montar_produto_dict(session: Session, p: ProdutoPadrao) -> dict:
    # Ver comentário equivalente em _montar_preco_dict.
    session.refresh(p)
    finalidades = session.exec(
        select(FinalidadeCowData)
        .join(ProdutoPadraoFinalidade, ProdutoPadraoFinalidade.finalidade_id == FinalidadeCowData.id)
        .where(ProdutoPadraoFinalidade.produto_padrao_id == p.id)
    ).all()
    preco_atual = session.exec(
        select(PrecoBaseSugerido)
        .where(PrecoBaseSugerido.produto_padrao_id == p.id, PrecoBaseSugerido.publicado == True)  # noqa: E712
        .order_by(PrecoBaseSugerido.atribuido_em.desc())
    ).first()
    classificacao = session.get(ClassificacaoCowData, p.classificacao_id) if p.classificacao_id else None
    dados = p.model_dump()
    dados["classificacao_nome"] = classificacao.nome if classificacao else None
    dados["finalidades"] = [{"id": f.id, "nome": f.nome} for f in finalidades]
    dados["preco_atual"] = (
        {"valor": preco_atual.valor, "unidade": preco_atual.unidade, "atribuido_em": preco_atual.atribuido_em, "regiao": preco_atual.regiao}
        if preco_atual else None
    )
    return dados


@router.get("/produtos")
def listar_produtos(
    classificacao_id: int | None = None, busca: str | None = None,
    _: Usuario = _dep, session: Session = Depends(get_session_manutencao),
) -> list[dict]:
    query = select(ProdutoPadrao)
    if classificacao_id is not None:
        query = query.where(ProdutoPadrao.classificacao_id == classificacao_id)
    if busca:
        query = query.where(ProdutoPadrao.nome.ilike(f"%{busca}%"))
    linhas = session.exec(query.order_by(ProdutoPadrao.nome)).all()
    return [_montar_produto_dict(session, p) for p in linhas]


@router.get("/produtos/checar-duplicata")
def checar_duplicata_produto(
    nome: str, classificacao_id: int | None = None,
    _: Usuario = _dep, session: Session = Depends(get_session_manutencao),
) -> list[dict]:
    """Aviso ativo de possível duplicata (nunca uma trava) — granularidade do
    produto-padrão fora de medicamento não tem regra fixa imposta, depende de
    curadoria humana contínua. Restringe à mesma classificação quando
    informada, para não sugerir coisas de outra categoria."""
    query = select(ProdutoPadrao.id, ProdutoPadrao.nome)
    if classificacao_id is not None:
        query = query.where(ProdutoPadrao.classificacao_id == classificacao_id)
    candidatos = session.exec(query).all()
    return sugestoes_duplicata(nome, [(cid, cnome) for cid, cnome in candidatos])


@router.get("/produtos/{id}")
def obter_produto(id: int, _: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> dict:
    p = session.get(ProdutoPadrao, id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto-padrão não encontrado")
    dados = _montar_produto_dict(session, p)
    historico = session.exec(
        select(PrecoBaseSugerido).where(PrecoBaseSugerido.produto_padrao_id == id).order_by(PrecoBaseSugerido.atribuido_em.desc())
    ).all()
    dados["historico_precos"] = [_montar_preco_dict(session, pr) for pr in historico]
    return dados


def _definir_finalidades_produto(session: Session, produto_id: int, finalidade_ids: list[int]) -> None:
    for vinculo in session.exec(select(ProdutoPadraoFinalidade).where(ProdutoPadraoFinalidade.produto_padrao_id == produto_id)).all():
        session.delete(vinculo)
    for fid in set(finalidade_ids):
        session.add(ProdutoPadraoFinalidade(produto_padrao_id=produto_id, finalidade_id=fid))


@router.post("/produtos", status_code=201)
def criar_produto(dados: ProdutoPadraoIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    p = ProdutoPadrao(
        nome=dados.nome.strip(), unidade=dados.unidade, classificacao_id=dados.classificacao_id,
        medicamento_comercial_id=dados.medicamento_comercial_id, ativo=dados.ativo,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    _definir_finalidades_produto(session, p.id, dados.finalidade_ids)
    session.commit()
    return _montar_produto_dict(session, p)


@router.put("/produtos/{id}")
def editar_produto(id: int, dados: ProdutoPadraoIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    p = session.get(ProdutoPadrao, id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto-padrão não encontrado")
    p.nome = dados.nome.strip() or p.nome
    p.unidade, p.classificacao_id, p.medicamento_comercial_id, p.ativo = dados.unidade, dados.classificacao_id, dados.medicamento_comercial_id, dados.ativo
    session.add(p)
    _definir_finalidades_produto(session, p.id, dados.finalidade_ids)
    session.commit()
    return _montar_produto_dict(session, p)


# ---------------------------------------------------------------------------
# Preço-base sugerido — a atribuição SEMPRE pergunta "publicar para as
# fazendas ou manter oculto por enquanto" (pedido do usuário, decidido a
# cada atribuição, nunca herdado da anterior). Disponível tanto a partir de
# uma cotação fechada (fornecedor_escolhido_id OU eh_media+participantes)
# quanto direto, sem cotação nenhuma (pesquisa simples) — mesmo endpoint.
# ---------------------------------------------------------------------------
class ParticipanteMediaIn(BaseModel):
    fornecedor_cowdata_id: int
    valor_informado: float | None = None


class AtribuirPrecoIn(BaseModel):
    valor: float
    unidade: str | None = None
    regiao: str | None = None
    origem: str = "manual"  # "cotacao" | "manual"
    cotacao_cowdata_item_id: int | None = None
    fornecedor_escolhido_id: int | None = None
    eh_media: bool = False
    participantes_media: list[ParticipanteMediaIn] = []
    observacao: str | None = None
    publicar: bool  # a resposta ao popup — obrigatório, decidido sempre


def _montar_preco_dict(session: Session, pr: PrecoBaseSugerido) -> dict:
    # `pr` pode chegar aqui EXPIRADO (commit anterior de uma linha filha, ex.:
    # participante de média, sem relationship() nenhuma pra SQLAlchemy saber
    # que precisa recarregar) — SQLModel.model_dump() não dispara o reload
    # automático que um acesso normal a atributo (pr.algo) dispara; sem este
    # refresh explícito, model_dump() devolve {} em silêncio (reproduzido e
    # confirmado isoladamente). Refresh é barato e idempotente mesmo quando
    # pr já está com os dados frescos.
    session.refresh(pr)
    dados = pr.model_dump()
    if pr.eh_media:
        participantes = session.exec(
            select(PrecoBaseSugeridoParticipanteMedia, FornecedorCowData)
            .join(FornecedorCowData, FornecedorCowData.id == PrecoBaseSugeridoParticipanteMedia.fornecedor_cowdata_id)
            .where(PrecoBaseSugeridoParticipanteMedia.preco_base_sugerido_id == pr.id)
        ).all()
        dados["participantes_media"] = [
            {"fornecedor_cowdata_id": f.id, "fornecedor_nome": f.nome, "valor_informado": part.valor_informado}
            for part, f in participantes
        ]
    else:
        dados["participantes_media"] = []
    if pr.fornecedor_escolhido_id:
        fornecedor = session.get(FornecedorCowData, pr.fornecedor_escolhido_id)
        dados["fornecedor_escolhido_nome"] = fornecedor.nome if fornecedor else None
    else:
        dados["fornecedor_escolhido_nome"] = None
    return dados


@router.post("/produtos/{id}/atribuir-preco", status_code=201)
def atribuir_preco(id: int, dados: AtribuirPrecoIn, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    p = session.get(ProdutoPadrao, id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto-padrão não encontrado")
    if dados.eh_media and len(dados.participantes_media) < 2:
        raise HTTPException(status_code=400, detail="Média exige ao menos 2 fornecedores participantes")
    agora = datetime.utcnow()
    pr = PrecoBaseSugerido(
        produto_padrao_id=id, valor=dados.valor, unidade=dados.unidade or p.unidade, regiao=dados.regiao,
        origem=dados.origem, cotacao_cowdata_item_id=dados.cotacao_cowdata_item_id,
        fornecedor_escolhido_id=None if dados.eh_media else dados.fornecedor_escolhido_id,
        eh_media=dados.eh_media, observacao=dados.observacao,
        publicado=dados.publicar, publicado_em=agora if dados.publicar else None,
        usuario_id=usuario.id, atribuido_em=agora,
    )
    session.add(pr)
    session.commit()
    session.refresh(pr)
    if dados.eh_media:
        for part in dados.participantes_media:
            session.add(PrecoBaseSugeridoParticipanteMedia(
                preco_base_sugerido_id=pr.id, fornecedor_cowdata_id=part.fornecedor_cowdata_id,
                valor_informado=part.valor_informado,
            ))
        session.commit()
    return _montar_preco_dict(session, pr)


class PublicarPrecoIn(BaseModel):
    publicado: bool


@router.put("/precos/{id}/publicar")
def publicar_preco(id: int, dados: PublicarPrecoIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    pr = session.get(PrecoBaseSugerido, id)
    if not pr:
        raise HTTPException(status_code=404, detail="Preço não encontrado")
    pr.publicado = dados.publicado
    pr.publicado_em = datetime.utcnow() if dados.publicado else None
    session.add(pr)
    session.commit()
    session.refresh(pr)
    return _montar_preco_dict(session, pr)


# ---------------------------------------------------------------------------
# Cotações
# ---------------------------------------------------------------------------
class CotacaoCowDataIn(BaseModel):
    titulo: str


class ItemIn(BaseModel):
    modo: str  # "produto" | "classificacao" | "finalidade"
    produto_padrao_id: int | None = None
    classificacao_id: int | None = None
    finalidade_id: int | None = None
    descricao_livre: str | None = None


def _rotulo_item(session: Session, item: CotacaoCowDataItem) -> str:
    produto_nome = session.get(ProdutoPadrao, item.produto_padrao_id).nome if item.produto_padrao_id else None
    classificacao_nome = session.get(ClassificacaoCowData, item.classificacao_id).nome if item.classificacao_id else None
    finalidade_nome = session.get(FinalidadeCowData, item.finalidade_id).nome if item.finalidade_id else None
    return rotulo_item_cotacao_cowdata(
        item.modo, produto_nome=produto_nome, classificacao_nome=classificacao_nome, finalidade_nome=finalidade_nome,
    )


def _cotacao_ou_404(session: Session, id: int) -> CotacaoCowData:
    c = session.get(CotacaoCowData, id)
    if not c:
        raise HTTPException(status_code=404, detail="Cotação não encontrada")
    return c


def _montar_cotacao_detalhe(session: Session, c: CotacaoCowData) -> dict:
    # Ver comentário equivalente em _montar_preco_dict.
    session.refresh(c)
    itens = session.exec(select(CotacaoCowDataItem).where(CotacaoCowDataItem.cotacao_cowdata_id == c.id)).all()
    fornecedores_vinculo = session.exec(
        select(CotacaoCowDataFornecedor, FornecedorCowData)
        .join(FornecedorCowData, FornecedorCowData.id == CotacaoCowDataFornecedor.fornecedor_cowdata_id)
        .where(CotacaoCowDataFornecedor.cotacao_cowdata_id == c.id)
    ).all()
    respostas = session.exec(
        select(CotacaoCowDataResposta)
        .where(CotacaoCowDataResposta.cotacao_cowdata_item_id.in_([i.id for i in itens] or [-1]))
    ).all()
    dados = c.model_dump()
    dados["itens"] = [
        {**item.model_dump(), "rotulo": _rotulo_item(session, item)} for item in itens
    ]
    dados["fornecedores"] = [{"id": f.id, "nome": f.nome} for _, f in fornecedores_vinculo]
    dados["respostas"] = [r.model_dump() for r in respostas]
    return dados


@router.get("")
def listar_cotacoes(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    linhas = session.exec(select(CotacaoCowData).order_by(CotacaoCowData.criado_em.desc())).all()
    return [c.model_dump() for c in linhas]


@router.post("", status_code=201)
def criar_cotacao(dados: CotacaoCowDataIn, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    if not dados.titulo.strip():
        raise HTTPException(status_code=400, detail="Título é obrigatório")
    c = CotacaoCowData(titulo=dados.titulo.strip(), usuario_id=usuario.id)
    session.add(c)
    session.commit()
    session.refresh(c)
    return _montar_cotacao_detalhe(session, c)


@router.get("/{id}")
def obter_cotacao(id: int, _: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> dict:
    return _montar_cotacao_detalhe(session, _cotacao_ou_404(session, id))


@router.post("/{id}/itens", status_code=201)
def adicionar_item(id: int, dados: ItemIn, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    c = _cotacao_ou_404(session, id)
    if c.status not in ("rascunho", "em_andamento"):
        raise HTTPException(status_code=400, detail="Cotação não está mais aberta para edição")
    if dados.modo not in ("produto", "classificacao", "finalidade"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    alvo = {"produto": dados.produto_padrao_id, "classificacao": dados.classificacao_id, "finalidade": dados.finalidade_id}[dados.modo]
    if alvo is None:
        raise HTTPException(status_code=400, detail=f"Falta informar o alvo para modo '{dados.modo}'")
    item = CotacaoCowDataItem(
        cotacao_cowdata_id=id, modo=dados.modo, produto_padrao_id=dados.produto_padrao_id,
        classificacao_id=dados.classificacao_id, finalidade_id=dados.finalidade_id, descricao_livre=dados.descricao_livre,
    )
    session.add(item)
    session.commit()
    return _montar_cotacao_detalhe(session, c)


@router.delete("/{id}/itens/{item_id}")
def remover_item(id: int, item_id: int, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    c = _cotacao_ou_404(session, id)
    item = session.get(CotacaoCowDataItem, item_id)
    if not item or item.cotacao_cowdata_id != id:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    for resp in session.exec(select(CotacaoCowDataResposta).where(CotacaoCowDataResposta.cotacao_cowdata_item_id == item_id)).all():
        session.delete(resp)
    session.delete(item)
    session.commit()
    return _montar_cotacao_detalhe(session, c)


class FornecedoresIn(BaseModel):
    fornecedor_ids: list[int]


@router.post("/{id}/fornecedores")
def adicionar_fornecedores(id: int, dados: FornecedoresIn, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    c = _cotacao_ou_404(session, id)
    ja_vinculados = {
        v.fornecedor_cowdata_id
        for v in session.exec(select(CotacaoCowDataFornecedor).where(CotacaoCowDataFornecedor.cotacao_cowdata_id == id)).all()
    }
    for fid in dados.fornecedor_ids:
        if fid not in ja_vinculados:
            session.add(CotacaoCowDataFornecedor(cotacao_cowdata_id=id, fornecedor_cowdata_id=fid))
    session.commit()
    return _montar_cotacao_detalhe(session, c)


@router.delete("/{id}/fornecedores/{fornecedor_id}")
def remover_fornecedor(id: int, fornecedor_id: int, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    c = _cotacao_ou_404(session, id)
    vinculo = session.exec(
        select(CotacaoCowDataFornecedor).where(
            CotacaoCowDataFornecedor.cotacao_cowdata_id == id, CotacaoCowDataFornecedor.fornecedor_cowdata_id == fornecedor_id,
        )
    ).first()
    if vinculo:
        session.delete(vinculo)
        session.commit()
    return _montar_cotacao_detalhe(session, c)


class RespostaIn(BaseModel):
    valor: float | None = None
    condicao_pagamento: str | None = None
    prazo_entrega_dias: int | None = None
    observacao: str | None = None
    recusado: bool = False


@router.put("/{id}/itens/{item_id}/respostas/{fornecedor_id}")
def registrar_resposta(
    id: int, item_id: int, fornecedor_id: int, dados: RespostaIn,
    session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao,
) -> dict:
    """A equipe CowData digita aqui o que o fornecedor respondeu por
    telefone/e-mail/WhatsApp — não há disparo nem link público, diferente da
    Cotação de uma fazenda (fazenda.models.cotacao)."""
    c = _cotacao_ou_404(session, id)
    item = session.get(CotacaoCowDataItem, item_id)
    if not item or item.cotacao_cowdata_id != id:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    resposta = session.exec(
        select(CotacaoCowDataResposta).where(
            CotacaoCowDataResposta.cotacao_cowdata_item_id == item_id,
            CotacaoCowDataResposta.fornecedor_cowdata_id == fornecedor_id,
        )
    ).first()
    if not resposta:
        resposta = CotacaoCowDataResposta(cotacao_cowdata_item_id=item_id, fornecedor_cowdata_id=fornecedor_id)
    resposta.valor, resposta.condicao_pagamento, resposta.prazo_entrega_dias = dados.valor, dados.condicao_pagamento, dados.prazo_entrega_dias
    resposta.observacao, resposta.recusado, resposta.registrado_em = dados.observacao, dados.recusado, datetime.utcnow()
    session.add(resposta)
    if c.status == "rascunho":
        c.status = "em_andamento"
        session.add(c)
    session.commit()
    return _montar_cotacao_detalhe(session, c)


@router.post("/{id}/fechar")
def fechar_cotacao(id: int, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    c = _cotacao_ou_404(session, id)
    if c.status in ("fechada", "cancelada"):
        raise HTTPException(status_code=400, detail="Cotação já está fechada/cancelada")
    c.status = "fechada"
    c.fechada_em = datetime.utcnow()
    session.add(c)
    session.commit()
    return _montar_cotacao_detalhe(session, c)


@router.post("/{id}/cancelar")
def cancelar_cotacao(id: int, session: Session = Depends(get_session_manutencao), usuario: Usuario = _dep_edicao) -> dict:
    c = _cotacao_ou_404(session, id)
    if c.status in ("fechada", "cancelada"):
        raise HTTPException(status_code=400, detail="Cotação já está fechada/cancelada")
    c.status = "cancelada"
    session.add(c)
    session.commit()
    return _montar_cotacao_detalhe(session, c)
