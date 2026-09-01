"""
Painel CowData > Farmácia — cadastro CENTRAL do catálogo padrão (Doença/
categoria de indicação, Princípio ativo, Medicamento) que o CowData mantém
para todas as fazendas-cliente. Pedido do usuário (31/08/2026): "tem que ser
possível adicionar doença, Reprodutivo, Produtivo, Preventivo e Suporte, por
meio do Painel CowData, aba farmácia, pois o painel CowData é responsável
por cadastrar a farmácia de todas as fazendas, padrão."

Duas mecânicas de propagação bem diferentes, cada uma já usada em outro
canto do sistema:

1. Doença/Princípio ativo/Indicação são CATÁLOGO GLOBAL (`fazenda_id=None`)
   — ficam automaticamente visíveis a toda fazenda via `rules.visibilidade.
   visivel()` (união "minha OU global"), sem precisar duplicar linha
   nenhuma. Mesmo mecanismo que já existe em farmacia.py, só que aqui com
   autenticação de Painel CowData (`exigir_area_painel_cowdata`) em vez de
   `get_fazenda_id_escrita` (que EXIGE uma fazenda do token — nunca resolve
   None num ambiente com fazendas cadastradas, ver
   `auth.resolver_fazenda_id_escrita`) — por isso farmacia.py não serve
   para esta tela.

2. Medicamento (item de ESTOQUE) precisa de FAN-OUT de verdade: um item de
   Estoque OWNED por fazenda (`fazenda_id=fid`), pré-preenchido e inativo/
   não-estocável (pedido: "não marcados como ativos e não marcados como
   estocáveis, para que o usuário o ative, se quiser") — Estoque não tem o
   conceito de linha global visível a todos, ao contrário do catálogo
   acima. Mesmo padrão de fan-out idempotente de
   `painel_cowdata_cadastros.aplicar_item` (get-or-create por nome por
   fazenda), adaptado ao formato bem maior do Estoque.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_area_painel_cowdata
from fazenda.database import get_session
from fazenda.models import (
    CategoriaMedicamento, ClassificacaoMedicamento, Doenca, Estoque, EstoqueCategoriaMedicamento,
    EstoqueClassificacaoMedicamento, Fazenda, IndicacaoTerapeutica, Laboratorio, MedicamentoCategoria,
    MedicamentoClassificacao, MedicamentoComercial, MedicamentoPrincipioAtivo, PrincipioAtivo, Usuario,
)
from fazenda.rules.farmacia_multi_principio import (
    checar_e_desvincular_exclusao_principio, definir_principios_estoque, definir_principios_medicamento,
    principios_do_medicamento,
)
from fazenda.rules.farmacia_tags import definir_tags, tags_de

router = APIRouter(prefix="/painel-cowdata/farmacia", tags=["painel-cowdata-farmacia"])

_dep = Depends(exigir_area_painel_cowdata("farmacia"))


def _fazendas_cliente_ativas(session: Session) -> list[Fazenda]:
    return session.exec(
        select(Fazenda).where(Fazenda.eh_empresa_cowdata == False, Fazenda.ativa == True)  # noqa: E712
    ).all()


# ---------------------------------------------------------------------------
# Categorias (Doenca.tipo: doenca/reprodutivo/produtivo/preventivo/suporte) —
# catálogo global, mesmo modelo já usado por Sanidade/Central de Protocolos.
# ---------------------------------------------------------------------------
class CategoriaIn(BaseModel):
    nome: str
    tipo: str = "doenca"
    descricao: str | None = None
    ativo: bool = True


@router.get("/categorias")
def listar_categorias_globais(_: Usuario = _dep, session: Session = Depends(get_session)) -> list[dict]:
    doencas = session.exec(select(Doenca).where(Doenca.fazenda_id.is_(None)).order_by(Doenca.tipo, Doenca.nome)).all()
    return [d.model_dump() for d in doencas]


@router.post("/categorias", status_code=201)
def criar_categoria_global(
    dados: CategoriaIn, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if dados.tipo not in Doenca.TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido — use um de {Doenca.TIPOS}")
    if session.exec(select(Doenca).where(Doenca.nome == nome, Doenca.fazenda_id.is_(None))).first():
        raise HTTPException(status_code=409, detail=f"Já existe a categoria/doença global '{nome}'")
    doenca = Doenca(nome=nome, tipo=dados.tipo, descricao=dados.descricao, ativo=dados.ativo, fazenda_id=None)
    session.add(doenca)
    session.commit()
    session.refresh(doenca)
    return doenca.model_dump()


@router.put("/categorias/{doenca_id}")
def atualizar_categoria_global(
    doenca_id: int, dados: CategoriaIn, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    doenca = session.get(Doenca, doenca_id)
    if not doenca or doenca.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Categoria/doença global não encontrada")
    if dados.tipo not in Doenca.TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido — use um de {Doenca.TIPOS}")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    doenca.nome, doenca.tipo, doenca.descricao, doenca.ativo = nome, dados.tipo, dados.descricao, dados.ativo
    session.add(doenca)
    session.commit()
    session.refresh(doenca)
    return doenca.model_dump()


# ---------------------------------------------------------------------------
# Princípios ativos — lista fechada, catálogo global. CRUD completo com
# checagem de impacto na exclusão (mesma regra de exclusoes.py/farmacia.py,
# reusada via rules/farmacia_multi_principio.py pra não duplicar a lógica).
# ---------------------------------------------------------------------------
class PrincipioGlobalIn(BaseModel):
    nome: str
    ativo: bool = True
    categoria_software: str | None = None
    uso_principal: str | None = None
    justificativa: str | None = None
    eh_biologico: bool = False
    unidade_base: str | None = None
    unidade_apresentacao: str | None = None
    estoque_minimo_apresentacoes: float = 1.0


@router.get("/principios")
def listar_principios_globais(_: Usuario = _dep, session: Session = Depends(get_session)) -> list[dict]:
    principios = session.exec(select(PrincipioAtivo).where(PrincipioAtivo.fazenda_id.is_(None)).order_by(PrincipioAtivo.nome)).all()
    return [p.model_dump() for p in principios]


@router.post("/principios", status_code=201)
def criar_principio_global(
    dados: PrincipioGlobalIn, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == nome, PrincipioAtivo.fazenda_id.is_(None))).first():
        raise HTTPException(status_code=409, detail=f"Já existe o princípio ativo global '{nome}'")
    pa = PrincipioAtivo(**{**dados.model_dump(), "nome": nome, "fazenda_id": None})
    session.add(pa)
    session.commit()
    session.refresh(pa)
    return pa.model_dump()


@router.put("/principios/{principio_id}")
def atualizar_principio_global(
    principio_id: int, dados: PrincipioGlobalIn, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    pa = session.get(PrincipioAtivo, principio_id)
    if not pa or pa.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Princípio ativo global não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    for k, v in {**dados.model_dump(), "nome": nome}.items():
        setattr(pa, k, v)
    session.add(pa)
    session.commit()
    session.refresh(pa)
    return pa.model_dump()


@router.delete("/principios/{principio_id}")
def excluir_principio_global(
    principio_id: int, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    pa = session.get(PrincipioAtivo, principio_id)
    if not pa or pa.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Princípio ativo global não encontrado")
    impacto, alvos = checar_e_desvincular_exclusao_principio(session, pa)
    for obj in alvos:
        session.delete(obj)
    session.commit()
    return {"excluido": True, "impacto": impacto}


# ---------------------------------------------------------------------------
# Laboratório / Categoria (medicamento) / Classificação do medicamento —
# três catálogos "nome + ativo" globais, mesmo padrão de Princípios ativos
# acima. Pedido do usuário (01/09/2026): "princípio ativo, categoria e
# classificação do medicamento pode ser cumulativo" — Categoria/Classificação
# viram tags multi-valor (ver rules/farmacia_tags.py); Laboratório continua
# alimentando o campo de texto livre já existente (MedicamentoComercial.
# laboratorio/Estoque.laboratorio), só como fonte do seletor.
# ---------------------------------------------------------------------------
class NomeAtivoGlobalIn(BaseModel):
    nome: str
    ativo: bool = True


def _crud_catalogo_global(model, router: APIRouter, prefixo: str):
    @router.get(f"/{prefixo}")
    def listar(_: Usuario = _dep, session: Session = Depends(get_session)) -> list[dict]:
        itens = session.exec(select(model).where(model.fazenda_id.is_(None)).order_by(model.nome)).all()
        return [i.model_dump() for i in itens]

    @router.post(f"/{prefixo}", status_code=201)
    def criar(dados: NomeAtivoGlobalIn, _: Usuario = _dep, session: Session = Depends(get_session)) -> dict:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        if session.exec(select(model).where(model.nome == nome, model.fazenda_id.is_(None))).first():
            raise HTTPException(status_code=409, detail=f"Já existe '{nome}' cadastrado")
        obj = model(nome=nome, ativo=dados.ativo, fazenda_id=None)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    @router.put(f"/{prefixo}/{{item_id}}")
    def atualizar(item_id: int, dados: NomeAtivoGlobalIn, _: Usuario = _dep, session: Session = Depends(get_session)) -> dict:
        obj = session.get(model, item_id)
        if not obj or obj.fazenda_id is not None:
            raise HTTPException(status_code=404, detail="Registro global não encontrado")
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        obj.nome, obj.ativo = nome, dados.ativo
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()


_crud_catalogo_global(Laboratorio, router, "laboratorios")
_crud_catalogo_global(CategoriaMedicamento, router, "categorias-medicamento")
_crud_catalogo_global(ClassificacaoMedicamento, router, "classificacoes-medicamento")


# ---------------------------------------------------------------------------
# Medicamentos — catálogo global (MedicamentoComercial) + fan-out para
# Estoque de toda fazenda-cliente. Multi-princípio (item 2 do pedido) e
# multi-doença (via IndicacaoTerapeutica, uma por combinação princípio×
# doença) desde a criação.
# ---------------------------------------------------------------------------
class MedicamentoGlobalIn(BaseModel):
    nome_comercial: str
    principio_ativo_ids: list[int]
    doenca_ids: list[int] = []
    laboratorio: str | None = None
    ativo: bool = True
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
    # Cumulativos (pedido do usuário, 01/09/2026) — ver rules/farmacia_tags.py.
    # `classificacao_medicamento` (escalar) é preenchido automaticamente com o
    # nome da 1ª categoria escolhida, por compatibilidade com quem já lê só o
    # escalar (ver _sincronizar_tags_medicamento).
    categoria_medicamento_ids: list[int] = []
    classificacao_medicamento_ids: list[int] = []
    classificacao_medicamento: str | None = None


def _sincronizar_indicacoes_globais(session: Session, principio_ids: list[int], doenca_ids: list[int]) -> None:
    """Garante 1 `IndicacaoTerapeutica` global por combinação princípio×
    doença informada — não remove combinações que já existiam e não foram
    citadas desta vez (o médico-veterinário do CowData pode estar só
    ACRESCENTANDO uma indicação nova a um princípio que já trata outras
    doenças)."""
    for pid in principio_ids:
        for did in doenca_ids:
            existe = session.exec(
                select(IndicacaoTerapeutica).where(
                    IndicacaoTerapeutica.principio_ativo_id == pid,
                    IndicacaoTerapeutica.doenca_id == did,
                    IndicacaoTerapeutica.fazenda_id.is_(None),
                )
            ).first()
            if not existe:
                session.add(IndicacaoTerapeutica(principio_ativo_id=pid, doenca_id=did, prioridade=2, fazenda_id=None))


def _sincronizar_tags_medicamento(session: Session, medicamento: MedicamentoComercial, categoria_ids: list[int], classificacao_ids: list[int]) -> None:
    """Grava as tags cumulativas de Categoria (medicamento)/Classificação do
    medicamento e espelha a 1ª categoria escolhida no campo escalar legado
    `classificacao_medicamento` — mesmo espírito do "principal" de
    multi-princípio, sem impor ordem de importância às demais."""
    definir_tags(session, MedicamentoCategoria, "medicamento_comercial_id", medicamento.id, "categoria_medicamento_id", categoria_ids)
    definir_tags(session, MedicamentoClassificacao, "medicamento_comercial_id", medicamento.id, "classificacao_medicamento_id", classificacao_ids)
    if categoria_ids:
        primeira = session.get(CategoriaMedicamento, categoria_ids[0])
        medicamento.classificacao_medicamento = primeira.nome if primeira else medicamento.classificacao_medicamento
    else:
        medicamento.classificacao_medicamento = None
    session.add(medicamento)


def _doencas_dos_principios(session: Session, principio_ids: list[int]) -> set[int]:
    return {
        ind.doenca_id for pid in principio_ids
        for ind in session.exec(
            select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.principio_ativo_id == pid, IndicacaoTerapeutica.fazenda_id.is_(None))
        ).all()
    }


def _montar_medicamento_dict(session: Session, m: MedicamentoComercial) -> dict:
    principio_ids = principios_do_medicamento(session, m.id)
    doenca_ids = sorted(_doencas_dos_principios(session, principio_ids))
    total_fazendas = len(_fazendas_cliente_ativas(session))
    em_fazendas = session.exec(select(Estoque).where(Estoque.medicamento_comercial_id == m.id)).all()
    categoria_medicamento_ids = tags_de(session, MedicamentoCategoria, "medicamento_comercial_id", m.id, "categoria_medicamento_id")
    classificacao_medicamento_ids = tags_de(session, MedicamentoClassificacao, "medicamento_comercial_id", m.id, "classificacao_medicamento_id")
    return {
        **m.model_dump(), "principio_ativo_ids": principio_ids, "doenca_ids": doenca_ids,
        "categoria_medicamento_ids": categoria_medicamento_ids, "classificacao_medicamento_ids": classificacao_medicamento_ids,
        "fan_out_fazendas": len(em_fazendas), "fan_out_total_fazendas": total_fazendas,
    }


@router.get("/medicamentos")
def listar_medicamentos_globais(_: Usuario = _dep, session: Session = Depends(get_session)) -> list[dict]:
    medicamentos = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.fazenda_id.is_(None)).order_by(MedicamentoComercial.nome_comercial)
    ).all()
    return [_montar_medicamento_dict(session, m) for m in medicamentos]


def _fan_out_medicamento(session: Session, medicamento: MedicamentoComercial, principio_ids: list[int]) -> dict:
    """Cria (get-or-create, idempotente) o item de Estoque correspondente em
    toda fazenda-cliente ativa — pedido: "automaticamente, fazer parte do
    estoque de todos os tenants, já com finalidade medicamento e princípio
    ativo automaticamente preenchido e classificação (medicamentos), mas não
    marcados como ativos e não marcados como estocáveis". NUNCA sobrescreve
    um item já existente com o mesmo nome (pode ser dado real do tenant)."""
    principal = session.get(PrincipioAtivo, principio_ids[0])
    categoria_ids = tags_de(session, MedicamentoCategoria, "medicamento_comercial_id", medicamento.id, "categoria_medicamento_id")
    classificacao_ids = tags_de(session, MedicamentoClassificacao, "medicamento_comercial_id", medicamento.id, "classificacao_medicamento_id")
    criados = ja_existiam = 0
    for fazenda in _fazendas_cliente_ativas(session):
        existente = session.exec(
            select(Estoque).where(Estoque.nome == medicamento.nome_comercial, Estoque.fazenda_id == fazenda.id)
        ).first()
        if existente:
            ja_existiam += 1
            continue
        item = Estoque(
            nome=medicamento.nome_comercial, fazenda_id=fazenda.id, finalidade="Medicamento",
            categoria="Medicamentos", classificacao_medicamento=medicamento.classificacao_medicamento,
            principio_ativo=principal.nome if principal else None,
            principio_ativo_id=principio_ids[0], medicamento_comercial_id=medicamento.id,
            laboratorio=medicamento.laboratorio, carencia_dias=medicamento.carencia_leite_dias,
            carencia_leite_dias=medicamento.carencia_leite_dias, carencia_carne_dias=medicamento.carencia_carne_dias,
            proibido_lactacao=medicamento.proibido_lactacao, ativo=False, estocavel=False,
        )
        session.add(item)
        session.flush()  # precisa do item.id antes de gravar a junção
        definir_principios_estoque(session, item, principio_ids)
        definir_tags(session, EstoqueCategoriaMedicamento, "estoque_id", item.id, "categoria_medicamento_id", categoria_ids)
        definir_tags(session, EstoqueClassificacaoMedicamento, "estoque_id", item.id, "classificacao_medicamento_id", classificacao_ids)
        criados += 1
    return {"criados": criados, "ja_existiam": ja_existiam}


@router.post("/medicamentos", status_code=201)
def criar_medicamento_global(
    dados: MedicamentoGlobalIn, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    nome = dados.nome_comercial.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome comercial é obrigatório")
    if not dados.principio_ativo_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um princípio ativo")
    if session.exec(select(MedicamentoComercial).where(MedicamentoComercial.nome_comercial == nome, MedicamentoComercial.fazenda_id.is_(None))).first():
        raise HTTPException(status_code=409, detail=f"Já existe o medicamento global '{nome}'")
    for pid in dados.principio_ativo_ids:
        pa = session.get(PrincipioAtivo, pid)
        if not pa or pa.fazenda_id is not None:
            raise HTTPException(status_code=400, detail=f"Princípio ativo {pid} inválido")
    campos_excluidos = {"principio_ativo_ids", "doenca_ids", "categoria_medicamento_ids", "classificacao_medicamento_ids"}
    campos_medicamento = dados.model_dump(exclude=campos_excluidos)
    medicamento = MedicamentoComercial(**campos_medicamento, principio_ativo_id=dados.principio_ativo_ids[0], fazenda_id=None)
    session.add(medicamento)
    session.commit()
    session.refresh(medicamento)

    definir_principios_medicamento(session, medicamento, dados.principio_ativo_ids, fazenda_id=None)
    _sincronizar_indicacoes_globais(session, dados.principio_ativo_ids, dados.doenca_ids)
    _sincronizar_tags_medicamento(session, medicamento, dados.categoria_medicamento_ids, dados.classificacao_medicamento_ids)
    session.commit()

    resultado_fanout = _fan_out_medicamento(session, medicamento, dados.principio_ativo_ids)
    session.commit()
    session.refresh(medicamento)
    return {**_montar_medicamento_dict(session, medicamento), "fan_out": resultado_fanout}


@router.put("/medicamentos/{medicamento_id}")
def atualizar_medicamento_global(
    medicamento_id: int, dados: MedicamentoGlobalIn, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    """Edita a bula/princípios/doenças do medicamento PADRÃO — NÃO propaga
    automaticamente para os itens de Estoque já fanned-out (cada fazenda que
    já ativou/personalizou o item mantém o que tem; ver "restaurar padrão",
    POST /estoque/{id}/restaurar-padrao, pra quem quiser trazer o valor novo
    de propósito)."""
    medicamento = session.get(MedicamentoComercial, medicamento_id)
    if not medicamento or medicamento.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Medicamento global não encontrado")
    if not dados.principio_ativo_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um princípio ativo")
    nome = dados.nome_comercial.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome comercial é obrigatório")
    campos_excluidos = {"principio_ativo_ids", "doenca_ids", "categoria_medicamento_ids", "classificacao_medicamento_ids"}
    campos_medicamento = dados.model_dump(exclude=campos_excluidos)
    for k, v in {**campos_medicamento, "nome_comercial": nome}.items():
        setattr(medicamento, k, v)
    session.add(medicamento)
    definir_principios_medicamento(session, medicamento, dados.principio_ativo_ids, fazenda_id=None)
    _sincronizar_indicacoes_globais(session, dados.principio_ativo_ids, dados.doenca_ids)
    _sincronizar_tags_medicamento(session, medicamento, dados.categoria_medicamento_ids, dados.classificacao_medicamento_ids)
    session.commit()
    session.refresh(medicamento)
    return _montar_medicamento_dict(session, medicamento)


@router.post("/medicamentos/{medicamento_id}/fanout")
def reexecutar_fanout(
    medicamento_id: int, _: Usuario = _dep, session: Session = Depends(get_session),
) -> dict:
    """Roda o fan-out de novo — pra preencher fazendas novas (cadastradas
    depois do medicamento) ou nunca alcançadas por algum motivo. Idempotente
    (get-or-create por nome+fazenda), nunca duplica nem sobrescreve item já
    existente."""
    medicamento = session.get(MedicamentoComercial, medicamento_id)
    if not medicamento or medicamento.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Medicamento global não encontrado")
    principio_ids = principios_do_medicamento(session, medicamento.id)
    resultado = _fan_out_medicamento(session, medicamento, principio_ids)
    session.commit()
    return resultado


# ---------------------------------------------------------------------------
# Substitutivos — tabela dinâmica de cruzamento (Fase E, pedido do usuário
# 01/09/2026): "duas filtros em cascata (Seção 1 ou 2 + item específico) →
# lista de medicamentos que batem → clique num medicamento → rankeia os
# demais pelo número de atributos clínicos coincidentes." Decisão já
# confirmada com o usuário: só contam atributos CLÍNICOS (princípio ativo,
# indicação/doença, categoria e classificação do medicamento) — laboratório
# nunca soma ponto de coincidência, é só informação no card.
# ---------------------------------------------------------------------------
EIXOS_FILTRO_SUBSTITUTIVOS = ("doenca", "principio", "categoria", "classificacao", "laboratorio")


@router.get("/substitutivos")
def listar_medicamentos_por_filtro(
    eixo: str, valor_id: int, _: Usuario = _dep, session: Session = Depends(get_session),
) -> list[dict]:
    """1º nível da tabela dinâmica: dado um eixo (Seção 1 = indicação, ou um
    dos catálogos de Seção 2) e um item específico dele, devolve os
    medicamentos globais que batem — ponto de partida antes de escolher um
    pivô para ver os substitutos ranqueados."""
    if eixo not in EIXOS_FILTRO_SUBSTITUTIVOS:
        raise HTTPException(status_code=400, detail=f"Eixo inválido — use um de {EIXOS_FILTRO_SUBSTITUTIVOS}")
    medicamentos_globais = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.fazenda_id.is_(None)).order_by(MedicamentoComercial.nome_comercial)
    ).all()

    if eixo == "doenca":
        principios_da_doenca = {
            ind.principio_ativo_id for ind in session.exec(
                select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.doenca_id == valor_id, IndicacaoTerapeutica.fazenda_id.is_(None))
            ).all()
        }
        medicamentos = [m for m in medicamentos_globais if principios_da_doenca & set(principios_do_medicamento(session, m.id))]
    elif eixo == "principio":
        medicamentos = [m for m in medicamentos_globais if valor_id in principios_do_medicamento(session, m.id)]
    elif eixo == "categoria":
        ids_com_categoria = {
            v.medicamento_comercial_id for v in session.exec(
                select(MedicamentoCategoria).where(MedicamentoCategoria.categoria_medicamento_id == valor_id)
            ).all()
        }
        medicamentos = [m for m in medicamentos_globais if m.id in ids_com_categoria]
    elif eixo == "classificacao":
        ids_com_classificacao = {
            v.medicamento_comercial_id for v in session.exec(
                select(MedicamentoClassificacao).where(MedicamentoClassificacao.classificacao_medicamento_id == valor_id)
            ).all()
        }
        medicamentos = [m for m in medicamentos_globais if m.id in ids_com_classificacao]
    else:  # laboratorio — MedicamentoComercial.laboratorio continua texto livre, casa pelo nome do catálogo
        laboratorio = session.get(Laboratorio, valor_id)
        nome_laboratorio = laboratorio.nome if laboratorio else None
        medicamentos = [m for m in medicamentos_globais if nome_laboratorio and m.laboratorio == nome_laboratorio]

    return [_montar_medicamento_dict(session, m) for m in medicamentos]


def _atributos_clinicos_medicamento(session: Session, medicamento_id: int) -> dict[str, set[int]]:
    principio_ids = set(principios_do_medicamento(session, medicamento_id))
    return {
        "principio_ativo_ids": principio_ids,
        "doenca_ids": _doencas_dos_principios(session, list(principio_ids)),
        "categoria_medicamento_ids": set(tags_de(session, MedicamentoCategoria, "medicamento_comercial_id", medicamento_id, "categoria_medicamento_id")),
        "classificacao_medicamento_ids": set(tags_de(session, MedicamentoClassificacao, "medicamento_comercial_id", medicamento_id, "classificacao_medicamento_id")),
    }


@router.get("/medicamentos/{medicamento_id}/substitutivos")
def listar_substitutivos_de_medicamento(
    medicamento_id: int, _: Usuario = _dep, session: Session = Depends(get_session),
) -> list[dict]:
    """2º nível: dado um medicamento pivô, ranqueia os demais medicamentos
    globais por número de atributos clínicos coincidentes (princípio ativo,
    indicação, categoria, classificação — sem laboratório), do mais para o
    menos parecido. Só entram na lista os que coincidem em pelo menos um
    atributo — zero coincidências não é um substituto."""
    pivo = session.get(MedicamentoComercial, medicamento_id)
    if not pivo or pivo.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Medicamento global não encontrado")

    atributos_pivo = _atributos_clinicos_medicamento(session, medicamento_id)
    outros = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.fazenda_id.is_(None), MedicamentoComercial.id != medicamento_id)
    ).all()

    resultado = []
    for m in outros:
        atributos = _atributos_clinicos_medicamento(session, m.id)
        coincidencias = {chave: sorted(atributos_pivo[chave] & atributos[chave]) for chave in atributos_pivo}
        pontuacao = sum(len(v) for v in coincidencias.values())
        if pontuacao == 0:
            continue
        resultado.append({**_montar_medicamento_dict(session, m), "pontuacao_substituto": pontuacao, "coincidencias": coincidencias})

    resultado.sort(key=lambda r: r["pontuacao_substituto"], reverse=True)
    return resultado
