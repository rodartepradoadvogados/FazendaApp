"""
Painel CowData > Cadastros globais — gerencia listas de referência
(motivos, raças, grau de sangue, unidades/categorias de estoque, tipos e
métodos de serviço reprodutivo) em TODAS as fazendas-cliente de uma vez, ou
só nas selecionadas, sem precisar entrar em cada uma via modo suporte.

Reaproveita os MESMOS modelos que cada fazenda já usa em Configurações >
Cadastro (nome + fazenda_id + ativo — ver
fazenda.api.routers.cadastro._comum._crud_nome_ativo): aqui a "fazenda" é
sempre uma lista explícita de fazenda_ids no corpo do pedido (Painel
CowData não tem uma fazenda selecionada no token, ver
fazenda.auth.get_fazenda_atual_id), nunca implícita.

Escrita é deliberadamente só ADITIVA (criar/reativar/renomear) — nunca
exclui em massa de várias fazendas de uma vez: apagar de verdade continua
sendo uma ação de UMA fazenda por vez, na tela de Cadastro dela mesma (ou
via suporte), pra nunca virar um botão que some com dado real de vários
clientes ao mesmo tempo por engano. "Remover" aqui só desativa (ativo=False).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_area_painel_cowdata
from fazenda.database import get_session
from fazenda.models import (
    Fazenda, GrauSangue, MetodoServicoReprodutivo, MotivoBaixa, MotivoMovimentacao, Raca, TipoServicoReprodutivo, Usuario,
)
from fazenda.models.estoque import (
    CategoriaEstoque, FinalidadeEstoque, LocalArmazenamento, UnidadeEmbalagemEstoque, UnidadeEstoque,
    UnidadeMedidaEmbalagemEstoque,
)

router = APIRouter(prefix="/painel-cowdata/cadastros", tags=["painel-cowdata-cadastros"])

# categoria (chave usada pelo frontend) -> Model. Todas seguem o mesmo
# formato (nome + fazenda_id + ativo); "grau_sangue" tem o campo extra
# fracao_holandes, tratado à parte abaixo. "metodo_servico" fica de fora
# desta tabela — tem uma FK (tipo_servico_id) que também é por fazenda, por
# isso ganha seu próprio conjunto de rotas mais abaixo.
_CATEGORIAS: dict[str, type] = {
    "motivo_baixa": MotivoBaixa,
    "motivo_movimentacao": MotivoMovimentacao,
    "raca": Raca,
    "grau_sangue": GrauSangue,
    "tipo_servico": TipoServicoReprodutivo,
    "estoque_local": LocalArmazenamento,
    "estoque_categoria": CategoriaEstoque,
    "estoque_finalidade": FinalidadeEstoque,
    "estoque_unidade": UnidadeEstoque,
    "estoque_unidade_embalagem": UnidadeEmbalagemEstoque,
    "estoque_unidade_medida_embalagem": UnidadeMedidaEmbalagemEstoque,
}
_LABELS: dict[str, str] = {
    "motivo_baixa": "Motivos de baixa", "motivo_movimentacao": "Motivos de movimentação",
    "raca": "Raças", "grau_sangue": "Grau de sangue", "tipo_servico": "Tipos de serviço reprodutivo",
    "metodo_servico": "Métodos de serviço reprodutivo",
    "estoque_local": "Estoque · Local de armazenamento", "estoque_categoria": "Estoque · Categoria",
    "estoque_finalidade": "Estoque · Finalidade", "estoque_unidade": "Estoque · Unidade",
    "estoque_unidade_embalagem": "Estoque · Unidade (embalagem)",
    "estoque_unidade_medida_embalagem": "Estoque · Unidade de medida (embalagem)",
}


def _model(categoria: str) -> type:
    modelo = _CATEGORIAS.get(categoria)
    if not modelo:
        raise HTTPException(status_code=404, detail=f"Categoria '{categoria}' não existe")
    return modelo


def _fazendas_ativas(session: Session) -> list[Fazenda]:
    fazendas = session.exec(select(Fazenda).where(Fazenda.eh_empresa_cowdata == False, Fazenda.ativa == True)).all()  # noqa: E712
    return sorted(fazendas, key=lambda f: f.nome)


def _fazendas_alvo(session: Session, fazenda_ids: list[int] | None) -> list[int]:
    """None (ou lista vazia) = TODAS as fazendas-cliente ativas — o padrão
    pedido explicitamente ("se alterado no painel CowData, altera o
    parâmetro de todas as fazendas"). Lista com ids = só essas."""
    todas = [f.id for f in _fazendas_ativas(session)]
    if not fazenda_ids:
        return todas
    validos = set(todas)
    return [fid for fid in fazenda_ids if fid in validos]


@router.get("/categorias")
def listar_categorias(_: Usuario = Depends(exigir_area_painel_cowdata("cadastros"))) -> list[dict]:
    chaves = list(_CATEGORIAS.keys()) + ["metodo_servico"]
    return [{"chave": k, "label": _LABELS[k]} for k in chaves]


@router.get("/fazendas")
def listar_fazendas_alvo(
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> list[dict]:
    return [{"id": f.id, "nome": f.nome} for f in _fazendas_ativas(session)]


### ATENÇÃO: rotas com prefixo fixo ("/metodo_servico/...") precisam ficar
### DECLARADAS ANTES de qualquer "/{categoria}" — FastAPI casa rotas na
### ordem de declaração, e "/{categoria}" também bateria com "metodo_servico"
### como valor de `categoria`, nunca chegando nas rotas específicas abaixo.

# ---------------------------------------------------------------------------
# Métodos de serviço reprodutivo — mesma mecânica dos cadastros simples, mas
# cada linha pertence a um Tipo (tipo_servico_id), que também é por fazenda:
# pra criar "IATF" na Fazenda X é preciso que o Tipo "IA" já exista NAQUELA
# fazenda (ver /tipo_servico/aplicar para garantir isso primeiro). Fazendas
# onde o tipo informado não existe são puladas, não erram a chamada inteira.
# ---------------------------------------------------------------------------
@router.get("/metodo_servico/listar")
def listar_metodos_agregado(
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    fazendas = _fazendas_ativas(session)
    total = len(fazendas)
    tipos_por_id = {t.id: t for t in session.exec(select(TipoServicoReprodutivo)).all()}
    agregado: dict[tuple[str, str], dict] = {}
    for linha in session.exec(select(MetodoServicoReprodutivo)).all():
        if linha.fazenda_id is None:
            continue
        tipo = tipos_por_id.get(linha.tipo_servico_id)
        if not tipo:
            continue
        chave = (tipo.nome, linha.nome)
        item = agregado.setdefault(chave, {"tipo_nome": tipo.nome, "nome": linha.nome, "fazenda_ids": set()})
        item["fazenda_ids"].add(linha.fazenda_id)
    itens = [
        {"tipo_nome": v["tipo_nome"], "nome": v["nome"], "em_fazendas": sorted(v["fazenda_ids"]), "total_fazendas": total}
        for v in sorted(agregado.values(), key=lambda v: (v["tipo_nome"], v["nome"]))
    ]
    return {"itens": itens, "fazendas": [{"id": f.id, "nome": f.nome} for f in fazendas]}


class AplicarMetodoIn(BaseModel):
    tipo_nome: str
    nome: str
    fazenda_ids: list[int] | None = None


@router.post("/metodo_servico/aplicar")
def aplicar_metodo(
    dados: AplicarMetodoIn,
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    nome = dados.nome.strip()
    tipo_nome = dados.tipo_nome.strip()
    if not nome or not tipo_nome:
        raise HTTPException(status_code=400, detail="Tipo e nome do método são obrigatórios")
    alvo = _fazendas_alvo(session, dados.fazenda_ids)
    criados = reativados = ja_existiam = sem_tipo = 0
    for fid in alvo:
        tipo = session.exec(
            select(TipoServicoReprodutivo).where(TipoServicoReprodutivo.nome == tipo_nome, TipoServicoReprodutivo.fazenda_id == fid)
        ).first()
        if not tipo:
            sem_tipo += 1
            continue
        existente = session.exec(
            select(MetodoServicoReprodutivo).where(MetodoServicoReprodutivo.nome == nome, MetodoServicoReprodutivo.fazenda_id == fid)
        ).first()
        if existente:
            if not existente.ativo:
                existente.ativo = True
                session.add(existente)
                reativados += 1
            else:
                ja_existiam += 1
            continue
        session.add(MetodoServicoReprodutivo(nome=nome, tipo_servico_id=tipo.id, fazenda_id=fid, ativo=True))
        criados += 1
    session.commit()
    return {"criados": criados, "atualizados": reativados, "ja_existiam": ja_existiam, "sem_tipo_correspondente": sem_tipo, "total_fazendas": len(alvo)}


@router.get("/{categoria}")
def listar_item_agregado(
    categoria: str, _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    """Visão agregada: cada NOME distinto que existe em pelo menos uma
    fazenda, com em quantas/quais já está cadastrado — pra ver de cara o que
    já é "padrão da casa" (está em todas) vs. o que só uma fazenda tem."""
    modelo = _model(categoria)
    fazendas = _fazendas_ativas(session)
    total = len(fazendas)
    agregado: dict[str, dict] = {}
    for linha in session.exec(select(modelo)).all():
        if linha.fazenda_id is None:
            continue  # não deveria existir linha "global" nestas tabelas — ignora com segurança
        item = agregado.setdefault(linha.nome, {
            "nome": linha.nome, "fazenda_ids": set(), "fracao_holandes": getattr(linha, "fracao_holandes", None),
        })
        item["fazenda_ids"].add(linha.fazenda_id)
    itens = [
        {
            "nome": v["nome"], "fracao_holandes": v["fracao_holandes"],
            "em_fazendas": sorted(v["fazenda_ids"]), "total_fazendas": total,
        }
        for v in sorted(agregado.values(), key=lambda v: v["nome"])
    ]
    return {"itens": itens, "fazendas": [{"id": f.id, "nome": f.nome} for f in fazendas]}


class AplicarIn(BaseModel):
    nome: str
    fracao_holandes: float | None = None
    fazenda_ids: list[int] | None = None  # None/vazio = todas as fazendas ativas


@router.post("/{categoria}/aplicar")
def aplicar_item(
    categoria: str, dados: AplicarIn,
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    """Cria (ou reativa, se existia desativado) este item nas fazendas
    alvo — todas por padrão, ou só as selecionadas. Nunca duplica: se já
    existe e está ativo, só atualiza fracao_holandes (grau de sangue) quando
    informado."""
    modelo = _model(categoria)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    alvo = _fazendas_alvo(session, dados.fazenda_ids)
    if not alvo:
        raise HTTPException(status_code=400, detail="Nenhuma fazenda-alvo válida")
    criados = reativados = ja_existiam = 0
    for fid in alvo:
        existente = session.exec(select(modelo).where(modelo.nome == nome, modelo.fazenda_id == fid)).first()
        if existente:
            mudou = False
            if not existente.ativo:
                existente.ativo = True
                mudou = True
            if categoria == "grau_sangue" and dados.fracao_holandes is not None and existente.fracao_holandes != dados.fracao_holandes:
                existente.fracao_holandes = dados.fracao_holandes
                mudou = True
            if mudou:
                session.add(existente)
                reativados += 1
            else:
                ja_existiam += 1
            continue
        extras = {"fracao_holandes": dados.fracao_holandes} if categoria == "grau_sangue" else {}
        session.add(modelo(nome=nome, fazenda_id=fid, ativo=True, **extras))
        criados += 1
    session.commit()
    return {"criados": criados, "atualizados": reativados, "ja_existiam": ja_existiam, "total_fazendas": len(alvo)}


class RenomearIn(BaseModel):
    nome_atual: str
    novo_nome: str
    fazenda_ids: list[int] | None = None


@router.put("/{categoria}/renomear")
def renomear_item(
    categoria: str, dados: RenomearIn,
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    modelo = _model(categoria)
    novo_nome = dados.novo_nome.strip()
    if not novo_nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    alvo = _fazendas_alvo(session, dados.fazenda_ids)
    renomeados = pulados_conflito = nao_encontrados = 0
    for fid in alvo:
        linha = session.exec(select(modelo).where(modelo.nome == dados.nome_atual, modelo.fazenda_id == fid)).first()
        if not linha:
            nao_encontrados += 1
            continue
        conflito = session.exec(select(modelo).where(modelo.nome == novo_nome, modelo.fazenda_id == fid)).first()
        if conflito and conflito.id != linha.id:
            pulados_conflito += 1
            continue
        linha.nome = novo_nome
        session.add(linha)
        renomeados += 1
    session.commit()
    return {"renomeados": renomeados, "pulados_por_conflito": pulados_conflito, "nao_encontrados": nao_encontrados}


class DesativarIn(BaseModel):
    nome: str
    fazenda_ids: list[int] | None = None


@router.post("/{categoria}/desativar")
def desativar_item(
    categoria: str, dados: DesativarIn,
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    modelo = _model(categoria)
    alvo = _fazendas_alvo(session, dados.fazenda_ids)
    desativados = 0
    for fid in alvo:
        linha = session.exec(select(modelo).where(modelo.nome == dados.nome, modelo.fazenda_id == fid)).first()
        if linha and linha.ativo:
            linha.ativo = False
            session.add(linha)
            desativados += 1
    session.commit()
    return {"desativados": desativados}
