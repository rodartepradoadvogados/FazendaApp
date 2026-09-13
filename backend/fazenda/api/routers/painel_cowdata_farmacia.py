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

RLS (auditoria de 11/09/2026, ver docs/security-audit/roteiro-seguranca.md):
toda rota deste arquivo usa `Depends(get_session_manutencao)`, não
`get_session` — o Painel CowData nunca tem fazenda selecionada no token, e
sob RLS: (a) a ESCRITA de uma linha de catálogo global (`fazenda_id=None`)
falharia com 500 mesmo sendo a coisa certa — o `WITH CHECK` da política não
tem exceção para NULL; (b) o fan-out (leitura E escrita de `Estoque` por
`fazenda_id` real, em laço sobre todas as fazendas) falharia com 500 na
primeira; (c) leituras que hoje funcionam sob RLS (catálogo global, graças
ao `OR fazenda_id IS NULL` da política) ainda assim ficam aqui, por
uniformidade e porque `_montar_medicamento_dict` lê `Estoque` (não
catálogo) para contar `fan_out_fazendas`.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_area_painel_cowdata, exigir_permissao_painel_cowdata
from fazenda.database import get_session_manutencao
from fazenda.models import (
    CategoriaMedicamento, ClassificacaoMedicamento, Doenca, Estoque, Fazenda, IndicacaoTerapeutica,
    Laboratorio, MedicamentoCategoria, MedicamentoClassificacao, MedicamentoComercial,
    MedicamentoPrincipioAtivo, PrincipioAtivo, Usuario,
)
from fazenda.rules.farmacia_identidade_padrao import aplicar_identidade_padrao
from fazenda.rules.farmacia_multi_principio import (
    checar_e_desvincular_exclusao_principio, definir_principios_medicamento, principios_do_medicamento,
)
from fazenda.rules.farmacia_tags import definir_tags, tags_de

router = APIRouter(prefix="/painel-cowdata/farmacia", tags=["painel-cowdata-farmacia"])

_dep = Depends(exigir_area_painel_cowdata("farmacia"))
# CONSULTA x EDIÇÃO (set/2026). A área "farmacia" dava as duas coisas de uma
# vez; o dono pediu a separação — "edição de Farmácia: consulta, todos
# podem". `_dep` (só a área) continua nas rotas de leitura; `_dep_edicao`
# (área + `pode_editar_farmacia`) vai em tudo que escreve no catálogo global
# ou faz fan-out de Estoque para as fazendas-cliente. A permissão é camada A
# MAIS: sem a área, `exigir_permissao_painel_cowdata` recusa antes mesmo de
# olhar a permissão.
_dep_edicao = Depends(exigir_permissao_painel_cowdata("farmacia", "pode_editar_farmacia"))


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
def listar_categorias_globais(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    doencas = session.exec(select(Doenca).where(Doenca.fazenda_id.is_(None)).order_by(Doenca.tipo, Doenca.nome)).all()
    return [d.model_dump() for d in doencas]


@router.post("/categorias", status_code=201)
def criar_categoria_global(
    dados: CategoriaIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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
    doenca_id: int, dados: CategoriaIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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
def listar_principios_globais(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    principios = session.exec(select(PrincipioAtivo).where(PrincipioAtivo.fazenda_id.is_(None)).order_by(PrincipioAtivo.nome)).all()
    return [p.model_dump() for p in principios]


@router.post("/principios", status_code=201)
def criar_principio_global(
    dados: PrincipioGlobalIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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


@router.post("/principios/restaurar-catalogo")
def restaurar_catalogo_principios(_: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
    """(Re)semeia o catálogo base de princípios ativos (documento base da
    farmácia) — add-missing e idempotente: só cria os que faltam e não
    sobrescreve edições. Útil quando o banco foi criado antes do catálogo
    completo existir.

    MOVIDA DE `cadastro/sanitario.py` (achado 35 da auditoria). Lá ela era
    `POST /cadastro/principios-ativos/restaurar-catalogo`, sem dependência de
    fazenda e SEM GATE DE PAPEL NENHUM: qualquer usuário de qualquer fazenda
    com o módulo sanitário liberado reescrevia o catálogo global que todas as
    fazendas-cliente enxergam por `rules.visibilidade.visivel()`.

    O lugar dela é aqui, e não um `exigir_admin` lá: `seed_farmacia` grava
    `PrincipioAtivo` com `fazenda_id=None`, o que é dado da CowData, não da
    fazenda. É a mesma correção estrutural que o catálogo de touros NAAB já
    recebeu (PR #702). O gate passa a ser o das outras escritas do catálogo
    global desta tela — área "farmacia" + `pode_editar_farmacia`."""
    from fazenda.rules.farmacia import seed_farmacia

    antes = len(session.exec(select(PrincipioAtivo)).all())
    seed_farmacia(session)
    total = len(session.exec(select(PrincipioAtivo)).all())
    return {"criados": total - antes, "total": total}


@router.put("/principios/{principio_id}")
def atualizar_principio_global(
    principio_id: int, dados: PrincipioGlobalIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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
    principio_id: int, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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
    def listar(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
        itens = session.exec(select(model).where(model.fazenda_id.is_(None)).order_by(model.nome)).all()
        return [i.model_dump() for i in itens]

    @router.post(f"/{prefixo}", status_code=201)
    def criar(dados: NomeAtivoGlobalIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
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
    def atualizar(item_id: int, dados: NomeAtivoGlobalIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao)) -> dict:
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
    definir_tags(
        session, MedicamentoCategoria, "medicamento_comercial_id", medicamento.id, "categoria_medicamento_id",
        categoria_ids, fazenda_id=medicamento.fazenda_id,
    )
    definir_tags(
        session, MedicamentoClassificacao, "medicamento_comercial_id", medicamento.id, "classificacao_medicamento_id",
        classificacao_ids, fazenda_id=medicamento.fazenda_id,
    )
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
def listar_medicamentos_globais(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    medicamentos = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.fazenda_id.is_(None)).order_by(MedicamentoComercial.nome_comercial)
    ).all()
    return [_montar_medicamento_dict(session, m) for m in medicamentos]


@router.get("/medicamentos/{medicamento_id}")
def detalhar_medicamento_global(
    medicamento_id: int, _: Usuario = _dep, session: Session = Depends(get_session_manutencao),
) -> dict:
    """Detalhe de UM medicamento do catálogo padrão — bug real (01/09/2026):
    "editar bula em Painel CowData deu 404". A tela de "Editar bula" (mesmo
    componente usado no catálogo da fazenda, `FormEdicaoMarca` em
    Farmacia.tsx) chamava a rota do TENANT (`GET /farmacia/principios/{id}`,
    que exige `pa.fazenda_id == fazenda_id do token`) mesmo estando dentro do
    Painel CowData — o princípio ali é GLOBAL (`fazenda_id=None`), então
    aquela rota sempre devolvia 404. Esta rota é o equivalente pro contexto
    global: sem fazenda nenhuma envolvida, 404 só quando o medicamento não
    existe ou não é global."""
    medicamento = session.get(MedicamentoComercial, medicamento_id)
    if not medicamento or medicamento.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Medicamento global não encontrado")
    return _montar_medicamento_dict(session, medicamento)


def _criar_item_fanout(session: Session, medicamento: MedicamentoComercial, fazenda_id: int) -> Estoque | None:
    """Get-or-create idempotente de UM item de Estoque, em UMA fazenda, pro
    medicamento padrão informado — núcleo do fan-out em massa (abaixo) e da
    ativação avulsa (Diagnóstico > "Ausente", só 1 fazenda de cada vez).
    NUNCA sobrescreve um item já existente com o mesmo nome (pode ser dado
    real do tenant) — devolve None nesse caso, pra quem chama contar."""
    existente = session.exec(
        select(Estoque).where(Estoque.nome == medicamento.nome_comercial, Estoque.fazenda_id == fazenda_id)
    ).first()
    if existente:
        return None
    item = Estoque(nome=medicamento.nome_comercial, fazenda_id=fazenda_id, ativo=False, estocavel=False)
    aplicar_identidade_padrao(session, item, medicamento, renomear=False)
    return item


def _fan_out_medicamento(session: Session, medicamento: MedicamentoComercial, principio_ids: list[int]) -> dict:
    """Cria (get-or-create, idempotente) o item de Estoque correspondente em
    toda fazenda-cliente ativa — pedido: "automaticamente, fazer parte do
    estoque de todos os tenants, já com finalidade medicamento e princípio
    ativo automaticamente preenchido e classificação (medicamentos), mas não
    marcados como ativos e não marcados como estocáveis". `principio_ids` foi
    mantido no assinatura por compatibilidade com quem já chama esta função,
    mas não é mais usado — a identidade completa vem do medicamento mesmo
    (ver aplicar_identidade_padrao), sempre lida ao vivo do banco."""
    criados = ja_existiam = 0
    for fazenda in _fazendas_cliente_ativas(session):
        if _criar_item_fanout(session, medicamento, fazenda.id) is None:
            ja_existiam += 1
        else:
            criados += 1
    return {"criados": criados, "ja_existiam": ja_existiam}


@router.post("/medicamentos", status_code=201)
def criar_medicamento_global(
    dados: MedicamentoGlobalIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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
    medicamento_id: int, dados: MedicamentoGlobalIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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
    medicamento_id: int, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
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


@router.get("/fazendas")
def listar_fazendas_farmacia(_: Usuario = _dep, session: Session = Depends(get_session_manutencao)) -> list[dict]:
    """Fazendas-cliente ativas — alimenta o seletor da tela de Diagnóstico
    (abaixo). Espelha /painel-cowdata/cadastros/fazendas, só que sob a
    permissão de área "farmacia" em vez de "cadastros"."""
    return [{"id": f.id, "nome": f.nome} for f in _fazendas_cliente_ativas(session)]


# ---------------------------------------------------------------------------
# Diagnóstico (proposta validada em artefato, 04/09/2026) — audita, fazenda
# por fazenda, se o catálogo central chegou direito no estoque do tenant.
# Três estados:
#   Casado   — Estoque.medicamento_comercial_id aponta pra um medicamento
#              central de verdade (fan-out funcionou).
#   Órfão    — item de Estoque com finalidade "Medicamento" nesta fazenda,
#              sem vínculo nenhum com o central. Nasceu antes do medicamento
#              central existir (ou com nome levemente diferente), então o
#              fan-out (que casa por nome exato) nunca conseguiu ligar os
#              dois — caso real reportado: Draxxin KP, Tulatromicina.
#   Ausente  — medicamento central sem NENHUM item de Estoque nesta fazenda
#              — normalmente porque ela foi ativada/reativada depois do
#              fan-out original rodar (fan-out só roda no momento da criação/
#              edição do medicamento, nunca fica "escutando" fazenda nova).
# ---------------------------------------------------------------------------
def _fazenda_cliente_ou_404(session: Session, fazenda_id: int) -> Fazenda:
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda or fazenda.eh_empresa_cowdata or not fazenda.ativa:
        raise HTTPException(status_code=404, detail="Fazenda-cliente ativa não encontrada")
    return fazenda


@router.get("/diagnostico")
def diagnostico_farmacia(
    fazenda_id: int, _: Usuario = _dep, session: Session = Depends(get_session_manutencao),
) -> dict:
    _fazenda_cliente_ou_404(session, fazenda_id)

    itens_fazenda = session.exec(select(Estoque).where(Estoque.fazenda_id == fazenda_id)).all()
    casados = []
    for item in itens_fazenda:
        if item.medicamento_comercial_id is None:
            continue
        medicamento = session.get(MedicamentoComercial, item.medicamento_comercial_id)
        casados.append({
            "estoque_id": item.id, "nome": item.nome,
            "medicamento_comercial_id": item.medicamento_comercial_id,
            "nome_comercial_central": medicamento.nome_comercial if medicamento else None,
            "principio_ativo": item.principio_ativo, "categoria": item.categoria,
            "classificacao_medicamento": item.classificacao_medicamento,
        })

    orfaos = [
        {
            "estoque_id": item.id, "nome": item.nome,
            "principio_ativo": item.principio_ativo, "categoria": item.categoria,
            "classificacao_medicamento": item.classificacao_medicamento, "ativo": item.ativo,
        }
        for item in itens_fazenda
        if item.finalidade == "Medicamento" and item.medicamento_comercial_id is None
    ]

    medicamentos_globais = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.fazenda_id.is_(None), MedicamentoComercial.ativo == True)  # noqa: E712
        .order_by(MedicamentoComercial.nome_comercial)
    ).all()
    ids_presentes_na_fazenda = set(session.exec(
        select(Estoque.medicamento_comercial_id).where(
            Estoque.fazenda_id == fazenda_id, Estoque.medicamento_comercial_id.is_not(None),
        )
    ).all())
    ausentes = [
        {**_montar_medicamento_dict(session, m), "estoque_id": None}
        for m in medicamentos_globais if m.id not in ids_presentes_na_fazenda
    ]

    return {"fazenda_id": fazenda_id, "casados": casados, "orfaos": orfaos, "ausentes": ausentes}


class VincularDiagnosticoIn(BaseModel):
    fazenda_id: int
    estoque_id: int
    medicamento_comercial_id: int


@router.post("/diagnostico/vincular")
def vincular_item_ao_catalogo(
    dados: VincularDiagnosticoIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
) -> dict:
    """Resolve um 'Órfão': liga um item de Estoque já existente (nome mantido
    — pode ser diferente do nome comercial central, ex. "Tulatromicina 100mg
    (genérico)" ligado a "Tulatromicina Injetável") ao medicamento central
    escolhido, adotando princípio(s)/categoria/classificação/carência/
    laboratório. Se dois itens da fazenda representam o MESMO produto físico
    (duplicado de verdade), o caminho é mesclar (POST /estoque/{id}/mesclar),
    não vincular — esta ação não apaga nem funde nada."""
    _fazenda_cliente_ou_404(session, dados.fazenda_id)
    item = session.get(Estoque, dados.estoque_id)
    if not item or item.fazenda_id != dados.fazenda_id:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado nesta fazenda")
    if item.medicamento_comercial_id is not None:
        raise HTTPException(status_code=400, detail="Este item já está vinculado ao catálogo central")
    medicamento = session.get(MedicamentoComercial, dados.medicamento_comercial_id)
    if not medicamento or medicamento.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Medicamento global não encontrado")

    aplicar_identidade_padrao(session, item, medicamento, renomear=False)
    session.commit()
    session.refresh(item)
    return item.model_dump()


class AtivarDiagnosticoIn(BaseModel):
    fazenda_id: int
    medicamento_comercial_id: int


@router.post("/diagnostico/ativar", status_code=201)
def ativar_medicamento_em_fazenda(
    dados: AtivarDiagnosticoIn, _: Usuario = _dep_edicao, session: Session = Depends(get_session_manutencao),
) -> dict:
    """Resolve um 'Ausente': cria nesta fazenda o item de Estoque que o
    fan-out em massa não alcançou (mesma regra idempotente do fan-out — não
    ativo, não estocável, quem quiser usar de verdade ativa/personaliza
    depois)."""
    _fazenda_cliente_ou_404(session, dados.fazenda_id)
    medicamento = session.get(MedicamentoComercial, dados.medicamento_comercial_id)
    if not medicamento or medicamento.fazenda_id is not None:
        raise HTTPException(status_code=404, detail="Medicamento global não encontrado")
    item = _criar_item_fanout(session, medicamento, dados.fazenda_id)
    if item is None:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um item de estoque chamado '{medicamento.nome_comercial}' nesta fazenda — "
                   "se for o mesmo produto sem vínculo, use 'Vincular ao catálogo central' em vez desta ação.",
        )
    session.commit()
    session.refresh(item)
    return item.model_dump()


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
    eixo: str, valor_id: int, _: Usuario = _dep, session: Session = Depends(get_session_manutencao),
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
    medicamento_id: int, _: Usuario = _dep, session: Session = Depends(get_session_manutencao),
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
