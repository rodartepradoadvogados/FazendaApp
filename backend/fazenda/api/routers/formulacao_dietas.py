"""
Formulação de Dietas — wizard de 10 etapas (motor NASEM/NRC Dairy 2021, ver
fazenda/rules/nutricao/). Restrito ao administrador da fazenda e ao
consultor vinculado (ver fazenda.auth.exigir_admin_ou_consultor_fazenda,
aplicado no include_router de main.py junto com exigir_modulo_contratado
("formulacao_dietas") — módulo comercial avulso, fora de todo plano do
catálogo).
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.models import (
    Alimento, AlimentoNutricional, AnaliseBromatologica, Animal, DietaSimulacao, DietaSimulacaoItem,
    PesagemCorporal, Secagem, Usuario,
)
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.dieta_lancamento import contexto_lote, criar_lancamento_programado
from fazenda.rules.nutricao import VERSAO_MOTOR, avaliar_dieta, resultado_para_dict
from fazenda.rules.nutricao.biblioteca import biblioteca_semente, template_por_categoria
from fazenda.rules.nutricao.tipos import (
    CAMPOS_NUTRICIONAIS, CATEGORIAS_NASEM, AnimalEntrada, EntradaFormulacao, IngredienteEntrada, ValorInvalidoError,
)

router = APIRouter(prefix="/formulacao", tags=["formulacao"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AnimalIn(BaseModel):
    estado_fisiologico: str = "vaca_lactante"
    raca: str = "Holandes"
    peso_vivo_kg: float = 0.0
    peso_maturo_kg: float = 680.0
    ecc: float = 3.0
    paridade: float = 1.0
    idade_dias: int | None = None
    del_dias: int | None = None
    dias_gestacao: int | None = None
    duracao_gestacao_dias: int = 283
    peso_bezerro_nascer_kg: float = 44.1
    del_concepcao: int | None = None
    idade_concepcao_1a_dias: int | None = None
    ganho_estrutura_kg_dia: float = 0.0
    ganho_reserva_kg_dia: float = 0.0
    producao_leite_kg_dia: float | None = None
    gordura_leite_pct: float | None = None
    proteina_leite_pct: float | None = None
    lactose_leite_pct: float = 4.78
    potencial_genetico_pl_305: float = 280.0
    temperatura_c: float = 24.0
    distancia_sala_m: float = 0.0
    viagens_sala_dia: int = 4
    desnivel_diario_m: float = 0.0
    eq_cms: int = 8
    cms_informado_kg_dia: float | None = None
    usa_monensina: bool = False
    eq_microbiana: int = 1
    usa_dndf48: int = 0


class IngredienteIn(BaseModel):
    nome: str
    categoria_nasem: str
    conc_pct: float = 0.0
    proporcao_ms_pct: float = 0.0
    origem: str = "manual"
    alimento_id: int | None = None
    alimento_nutricional_id: int | None = None
    analise_bromatologica_id: int | None = None
    campos_editados: list[str] | None = None

    ms_pct: float | None = None
    pb_pct: float | None = None
    fdn_pct: float | None = None
    fda_pct: float | None = None
    lignina_pct: float | None = None
    amido_pct: float | None = None
    acucares_pct: float | None = None
    ee_pct: float | None = None
    ag_pct: float | None = None
    cinzas_pct: float | None = None
    dndf48_fdn_pct: float | None = None
    pb_a_pct: float | None = None
    pb_b_pct: float | None = None
    pb_c_pct: float | None = None
    kd_pb_b_pct_h: float | None = None
    nnp_pb_pct: float | None = None
    pidn_pct: float | None = None
    pida_pct: float | None = None
    dig_amido_pct: float | None = None
    dig_pndr_pct: float | None = None
    dig_ag_pct: float | None = None
    ca_pct: float | None = None
    p_pct: float | None = None
    p_inorg_p_pct: float | None = None
    p_org_p_pct: float | None = None
    mg_pct: float | None = None
    k_pct: float | None = None
    na_pct: float | None = None
    cl_pct: float | None = None
    s_pct: float | None = None
    abs_ca: float | None = None
    abs_p_total: float | None = None
    abs_mg: float | None = None
    abs_na: float | None = None
    abs_cl: float | None = None
    abs_k: float | None = None
    custo_kg_mn: float | None = None


class SimulacaoCriarIn(BaseModel):
    nome: str
    lote: int | None = None


class SimulacaoSalvarIn(BaseModel):
    animal: AnimalIn
    itens: list[IngredienteIn]
    etapa_atual: int = 1
    # Trava otimista — o cliente devolve o `atualizado_em` que recebeu no
    # último GET/PUT; se a simulação foi alterada em outra aba nesse meio
    # tempo, o valor não bate e a gravação é recusada (ver RA2 da auditoria).
    atualizado_em: datetime | None = None


class CalcularIn(BaseModel):
    animal: AnimalIn
    itens: list[IngredienteIn]


class DuplicarIn(BaseModel):
    nome: str


class AplicarIn(BaseModel):
    lote: int
    data_abertura: date
    base_quantidade: str = "total"  # "total" (padrão) | "animal"
    responsavel: str | None = None
    data_prevista_encerramento: date | None = None
    encerrar_anterior: bool = False


class AlimentoNutricionalIn(BaseModel):
    alimento_id: int | None = None
    nome: str
    categoria_nasem: str
    conc_pct: float = 0.0
    fonte: str | None = None
    observacao: str | None = None
    valores: dict[str, float | None] = {}


# ---------------------------------------------------------------------------
# Conversão entrada HTTP <-> dataclasses do motor
# ---------------------------------------------------------------------------
def _animal_entrada(a: AnimalIn) -> AnimalEntrada:
    return AnimalEntrada(**a.model_dump())


def _ingrediente_entrada(i: IngredienteIn) -> IngredienteEntrada:
    return IngredienteEntrada(
        nome=i.nome, categoria_nasem=i.categoria_nasem, conc_pct=i.conc_pct, proporcao_ms_pct=i.proporcao_ms_pct,
        **{campo: getattr(i, campo) for campo in CAMPOS_NUTRICIONAIS},
    )


def _validar_ranges(dados: AnimalIn | CalcularIn, itens: list[IngredienteIn]) -> None:
    """Validação de payload (RA3 da auditoria) — antes de chegar no motor,
    que já valida o resto (combinação eq_cms×estado_fisiologico, etc)."""
    if len(itens) > 60:
        raise HTTPException(status_code=422, detail="No máximo 60 ingredientes por simulação.")
    if not itens:
        raise HTTPException(status_code=422, detail="A dieta precisa ter ao menos um ingrediente.")
    for it in itens:
        if not (0 <= it.proporcao_ms_pct <= 100):
            raise HTTPException(status_code=422, detail=f'proporcao_ms_pct inválida em "{it.nome}" — deve ser entre 0 e 100.')
        if not (0 <= it.conc_pct <= 100):
            raise HTTPException(status_code=422, detail=f'conc_pct inválido em "{it.nome}" — deve ser entre 0 e 100.')
        if it.categoria_nasem not in CATEGORIAS_NASEM:
            raise HTTPException(status_code=422, detail=f'categoria_nasem inválida em "{it.nome}": {it.categoria_nasem!r}.')


def _calcular(animal_in: AnimalIn, itens_in: list[IngredienteIn]) -> dict:
    if not (0 < animal_in.peso_vivo_kg <= 1500):
        raise HTTPException(status_code=422, detail="peso_vivo_kg deve ser maior que 0 e no máximo 1500.")
    if animal_in.cms_informado_kg_dia is not None and not (0 < animal_in.cms_informado_kg_dia <= 100):
        raise HTTPException(status_code=422, detail="cms_informado_kg_dia deve ser maior que 0 e no máximo 100.")
    _validar_ranges(animal_in, itens_in)
    entrada = EntradaFormulacao(
        animal=_animal_entrada(animal_in),
        ingredientes=[_ingrediente_entrada(i) for i in itens_in],
    )
    try:
        resultado = avaliar_dieta(entrada)
    except ValorInvalidoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return resultado_para_dict(resultado)


# ---------------------------------------------------------------------------
# Cálculo stateless — o motor do balanço ao vivo (Etapa 4)
# ---------------------------------------------------------------------------
@router.post("/calcular")
def calcular(dados: CalcularIn) -> dict:
    return _calcular(dados.animal, dados.itens)


# ---------------------------------------------------------------------------
# CRUD de simulações
# ---------------------------------------------------------------------------
def _resumo_simulacao(sim: DietaSimulacao) -> dict:
    resumo = {"cms_kg_dia": None, "balanco_ell_mcal": None, "balanco_pm_g": None, "custo_dia": None}
    if sim.resultado_json:
        try:
            r = json.loads(sim.resultado_json)
        except (json.JSONDecodeError, TypeError):
            r = {}
        resumo["cms_kg_dia"] = (r.get("consumo") or {}).get("cms_kg_dia")
        resumo["balanco_pm_g"] = (r.get("proteina") or {}).get("balanco_g")
        resumo["custo_dia"] = sum((i.get("custo_dia") or 0) for i in (r.get("ingredientes") or []))
        for linha in r.get("balanco") or []:
            if linha.get("nutriente") == "ELl":
                resumo["balanco_ell_mcal"] = linha.get("balanco")
    return {
        "id": sim.id, "nome": sim.nome, "lote": sim.lote, "status": sim.status, "etapa_atual": sim.etapa_atual,
        "calculado_em": sim.calculado_em.isoformat() if sim.calculado_em else None,
        "aplicada_em": sim.aplicada_em.isoformat() if sim.aplicada_em else None,
        "criado_em": sim.criado_em.isoformat(), "atualizado_em": sim.atualizado_em.isoformat(),
        "usuario_id": sim.usuario_id, **resumo,
    }


@router.get("/simulacoes")
def listar_simulacoes(
    lote: int | None = None, status: str | None = None,
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(DietaSimulacao)
    if fazenda_id is not None:
        query = query.where(DietaSimulacao.fazenda_id == fazenda_id)
    if lote is not None:
        query = query.where(DietaSimulacao.lote == lote)
    if status is not None:
        query = query.where(DietaSimulacao.status == status)
    simulacoes = session.exec(query).all()
    saida = [_resumo_simulacao(s) for s in sorted(simulacoes, key=lambda s: s.atualizado_em, reverse=True)]
    nomes = mapa_usuarios(session, {s["usuario_id"] for s in saida if s["usuario_id"]})
    for s in saida:
        s["usuario_nome"] = nomes.get(s["usuario_id"])
    return saida


@router.post("/simulacoes", status_code=201)
def criar_simulacao(
    dados: SimulacaoCriarIn, fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is None:
        raise HTTPException(status_code=400, detail="Selecione a fazenda antes de criar uma simulação")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe um nome para a simulação")
    sim = DietaSimulacao(nome=dados.nome.strip(), lote=dados.lote, fazenda_id=fazenda_id, usuario_id=user.id)
    session.add(sim)
    session.commit()
    session.refresh(sim)
    return _resumo_simulacao(sim)


def _buscar_simulacao(session: Session, fazenda_id: int | None, simulacao_id: int) -> DietaSimulacao:
    sim = session.get(DietaSimulacao, simulacao_id)
    if not sim or (fazenda_id is not None and sim.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Simulação não encontrada")
    return sim


def _itens_da_simulacao(session: Session, fazenda_id: int | None, simulacao_id: int) -> list[DietaSimulacaoItem]:
    query = select(DietaSimulacaoItem).where(DietaSimulacaoItem.simulacao_id == simulacao_id)
    if fazenda_id is not None:
        query = query.where(DietaSimulacaoItem.fazenda_id == fazenda_id)
    return sorted(session.exec(query).all(), key=lambda i: i.ordem)


def _item_publico(item: DietaSimulacaoItem) -> dict:
    valores = json.loads(item.valores_json or "{}")
    return {
        "id": item.id, "ordem": item.ordem, "alimento_id": item.alimento_id,
        "alimento_nutricional_id": item.alimento_nutricional_id, "analise_bromatologica_id": item.analise_bromatologica_id,
        "nome": item.nome, "origem": item.origem, "proporcao_ms_pct": item.proporcao_ms_pct,
        "categoria_nasem": item.categoria_nasem, "conc_pct": item.conc_pct, "ms_pct": item.ms_pct,
        "custo_kg_mn": item.custo_kg_mn, "campos_editados": json.loads(item.campos_editados_json or "[]"),
        **valores,
    }


def _cabecalho_publico(sim: DietaSimulacao) -> dict:
    dados = sim.model_dump()
    dados["criado_em"] = sim.criado_em.isoformat()
    dados["atualizado_em"] = sim.atualizado_em.isoformat()
    dados["calculado_em"] = sim.calculado_em.isoformat() if sim.calculado_em else None
    dados["aplicada_em"] = sim.aplicada_em.isoformat() if sim.aplicada_em else None
    return dados


@router.get("/simulacoes/{simulacao_id}")
def obter_simulacao(
    simulacao_id: int, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    sim = _buscar_simulacao(session, fazenda_id, simulacao_id)
    itens = _itens_da_simulacao(session, fazenda_id, simulacao_id)
    resultado = json.loads(sim.resultado_json) if sim.resultado_json else None
    avisos = json.loads(sim.avisos_json) if sim.avisos_json else None
    return {"cabecalho": _cabecalho_publico(sim), "itens": [_item_publico(i) for i in itens], "resultado": resultado, "avisos": avisos}


@router.put("/simulacoes/{simulacao_id}")
def salvar_simulacao(
    simulacao_id: int, dados: SimulacaoSalvarIn, fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    sim = _buscar_simulacao(session, fazenda_id, simulacao_id)
    if sim.status == "aplicada":
        raise HTTPException(status_code=409, detail="Esta simulação já foi aplicada numa dieta — duplique-a para continuar editando.")
    if dados.atualizado_em is not None and sim.atualizado_em.replace(microsecond=0) != dados.atualizado_em.replace(microsecond=0):
        raise HTTPException(status_code=409, detail="Esta simulação foi alterada em outra guia — recarregue antes de salvar.")

    resultado_dict = _calcular(dados.animal, dados.itens)

    # Substitui a grade inteira numa única transação (delete + insert +
    # atualização do cabeçalho) — nunca fica com um commit intermediário sem
    # itens se o cálculo acima já não tiver levantado (RA2 da auditoria).
    query_antigos = select(DietaSimulacaoItem).where(DietaSimulacaoItem.simulacao_id == simulacao_id)
    if fazenda_id is not None:
        query_antigos = query_antigos.where(DietaSimulacaoItem.fazenda_id == fazenda_id)
    for antigo in session.exec(query_antigos).all():
        session.delete(antigo)

    for animal_field, valor in dados.animal.model_dump().items():
        setattr(sim, animal_field, valor)
    sim.etapa_atual = dados.etapa_atual
    sim.motor_versao = VERSAO_MOTOR
    sim.calculado_em = datetime.utcnow()
    sim.resultado_json = json.dumps(resultado_dict)
    sim.avisos_json = json.dumps(resultado_dict.get("avisos") or [])
    sim.atualizado_em = datetime.utcnow()
    if sim.status == "rascunho" and resultado_dict.get("consumo", {}).get("cms_kg_dia"):
        sim.status = "concluida"
    session.add(sim)

    for ordem, item_in in enumerate(dados.itens):
        session.add(DietaSimulacaoItem(
            fazenda_id=fazenda_id, simulacao_id=simulacao_id, ordem=ordem,
            alimento_id=item_in.alimento_id, alimento_nutricional_id=item_in.alimento_nutricional_id,
            analise_bromatologica_id=item_in.analise_bromatologica_id, nome=item_in.nome, origem=item_in.origem,
            proporcao_ms_pct=item_in.proporcao_ms_pct, categoria_nasem=item_in.categoria_nasem, conc_pct=item_in.conc_pct,
            ms_pct=item_in.ms_pct, custo_kg_mn=item_in.custo_kg_mn,
            valores_json=json.dumps({campo: getattr(item_in, campo) for campo in CAMPOS_NUTRICIONAIS}),
            campos_editados_json=json.dumps(item_in.campos_editados or []),
        ))
    session.commit()
    session.refresh(sim)

    itens = _itens_da_simulacao(session, fazenda_id, simulacao_id)
    return {"cabecalho": _cabecalho_publico(sim), "itens": [_item_publico(i) for i in itens], "resultado": resultado_dict}


@router.delete("/simulacoes/{simulacao_id}")
def excluir_simulacao(
    simulacao_id: int, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    sim = _buscar_simulacao(session, fazenda_id, simulacao_id)
    if sim.status == "aplicada":
        raise HTTPException(status_code=409, detail="Esta simulação já foi aplicada numa dieta e não pode ser excluída.")
    for item in _itens_da_simulacao(session, fazenda_id, simulacao_id):
        session.delete(item)
    session.delete(sim)
    session.commit()
    return {"ok": True}


@router.post("/simulacoes/{simulacao_id}/duplicar", status_code=201)
def duplicar_simulacao(
    simulacao_id: int, dados: DuplicarIn, fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    original = _buscar_simulacao(session, fazenda_id, simulacao_id)
    itens_originais = _itens_da_simulacao(session, fazenda_id, simulacao_id)

    nova = DietaSimulacao(
        nome=dados.nome.strip() or f"{original.nome} (cópia)", lote=original.lote, fazenda_id=fazenda_id, usuario_id=user.id,
        status="rascunho", etapa_atual=original.etapa_atual,
        **{f: getattr(original, f) for f in AnimalIn.model_fields},
        resultado_json=original.resultado_json, avisos_json=original.avisos_json,
        motor_versao=original.motor_versao, calculado_em=original.calculado_em,
    )
    session.add(nova)
    session.commit()
    session.refresh(nova)
    for item in itens_originais:
        session.add(DietaSimulacaoItem(
            fazenda_id=fazenda_id, simulacao_id=nova.id, ordem=item.ordem, alimento_id=item.alimento_id,
            alimento_nutricional_id=item.alimento_nutricional_id, analise_bromatologica_id=item.analise_bromatologica_id,
            nome=item.nome, origem=item.origem, proporcao_ms_pct=item.proporcao_ms_pct, categoria_nasem=item.categoria_nasem,
            conc_pct=item.conc_pct, ms_pct=item.ms_pct, custo_kg_mn=item.custo_kg_mn,
            valores_json=item.valores_json, campos_editados_json=item.campos_editados_json,
        ))
    session.commit()
    itens = _itens_da_simulacao(session, fazenda_id, nova.id)
    return {"cabecalho": _cabecalho_publico(nova), "itens": [_item_publico(i) for i in itens]}


# ---------------------------------------------------------------------------
# Aplicar na dieta atual
# ---------------------------------------------------------------------------
@router.post("/simulacoes/{simulacao_id}/aplicar", status_code=201)
def aplicar_simulacao(
    simulacao_id: int, dados: AplicarIn, fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    sim = _buscar_simulacao(session, fazenda_id, simulacao_id)
    itens = _itens_da_simulacao(session, fazenda_id, simulacao_id)
    if not itens:
        raise HTTPException(status_code=422, detail="Esta simulação não tem ingredientes para aplicar.")

    animal_in = AnimalIn(**{f: getattr(sim, f) for f in AnimalIn.model_fields})
    itens_in = [IngredienteIn(**_item_publico(i)) for i in itens]
    resultado_dict = _calcular(animal_in, itens_in)  # sempre recalcula fresco antes de aplicar (RA5)

    cms = (resultado_dict.get("consumo") or {}).get("cms_kg_dia")
    if not cms or cms <= 0 or (isinstance(cms, float) and math.isnan(cms)):
        raise HTTPException(status_code=422, detail="O consumo de matéria seca calculado é inválido — revise os dados do animal antes de aplicar.")
    if any(a.get("severidade") == "bloqueante" for a in resultado_dict.get("avisos") or []):
        raise HTTPException(status_code=422, detail="Há um aviso bloqueante nesta simulação — resolva-o antes de aplicar na dieta.")

    contexto = contexto_lote(session, fazenda_id, dados.lote)
    qtd_animais = contexto["qtd_animais"] or 1

    itens_lancamento = []
    for ingrediente_resultado, item_db in zip(resultado_dict.get("ingredientes") or [], itens):
        kg_mn_animal = ingrediente_resultado.get("kg_materia_natural_dia") or 0.0
        if kg_mn_animal is None or (isinstance(kg_mn_animal, float) and (math.isnan(kg_mn_animal) or kg_mn_animal < 0)):
            raise HTTPException(status_code=422, detail=f'Quantidade calculada inválida para "{item_db.nome}".')
        quantidade = kg_mn_animal * qtd_animais if dados.base_quantidade == "total" else kg_mn_animal
        itens_lancamento.append({
            "alimento": item_db.nome, "alimento_id": item_db.alimento_id, "quantidade": round(quantidade, 3),
            "unidade": "kg", "base": "MN", "ms_pct": item_db.ms_pct,
        })

    dieta = criar_lancamento_programado(
        session, fazenda_id, user.id,
        lote=dados.lote, responsavel=dados.responsavel, data_abertura=dados.data_abertura,
        data_prevista_encerramento=dados.data_prevista_encerramento, observacao=f"Gerada pela simulação \"{sim.nome}\"",
        base_quantidade=dados.base_quantidade, leite_bezerros_kg_dia=None,
        itens=itens_lancamento, encerrar_anterior=dados.encerrar_anterior, dieta_simulacao_id=sim.id,
    )

    sim.dieta_lancamento_id = dieta.id
    sim.aplicada_em = datetime.utcnow()
    sim.aplicada_por_usuario_id = user.id
    sim.status = "aplicada"
    sim.atualizado_em = datetime.utcnow()
    session.add(sim)
    session.commit()

    return {"dieta_lancamento_id": dieta.id, "itens_criados": len(itens_lancamento), "qtd_animais": qtd_animais}


# ---------------------------------------------------------------------------
# Biblioteca de alimentos (Etapa 1)
# ---------------------------------------------------------------------------
def _nutricional_publico(a: AlimentoNutricional) -> dict:
    valores = {campo: getattr(a, campo) for campo in CAMPOS_NUTRICIONAIS if campo != "custo_kg_mn"}
    valores["custo_kg_mn"] = a.custo_kg_mn
    if a.extras_json:
        valores.update(json.loads(a.extras_json))
    return {
        "id": a.id, "alimento_id": a.alimento_id, "nome": a.nome, "categoria_nasem": a.categoria_nasem,
        "conc_pct": a.conc_pct, "fonte": a.fonte, "observacao": a.observacao, "ativo": a.ativo, "valores": valores,
    }


@router.get("/alimentos")
def listar_alimentos_nutricionais(
    busca: str | None = None, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_nutri = select(AlimentoNutricional).where(AlimentoNutricional.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_nutri = query_nutri.where(AlimentoNutricional.fazenda_id == fazenda_id)
    biblioteca = session.exec(query_nutri).all()
    com_composicao = {a.alimento_id for a in biblioteca if a.alimento_id}

    query_alimento = select(Alimento).where(Alimento.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_alimento = query_alimento.where(Alimento.fazenda_id == fazenda_id)
    cadastrados = session.exec(query_alimento).all()
    if busca:
        termo = busca.strip().lower()
        cadastrados = [a for a in cadastrados if termo in a.nome.lower()]

    return {
        "biblioteca": [_nutricional_publico(a) for a in biblioteca],
        "cadastrados": [
            {"id": a.id, "nome": a.nome, "sem_composicao": a.id not in com_composicao}
            for a in sorted(cadastrados, key=lambda a: a.nome)
        ],
    }


@router.post("/alimentos", status_code=201)
def criar_alimento_nutricional(
    dados: AlimentoNutricionalIn, fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is None:
        raise HTTPException(status_code=400, detail="Selecione a fazenda antes de cadastrar")
    if dados.categoria_nasem not in CATEGORIAS_NASEM:
        raise HTTPException(status_code=400, detail=f"categoria_nasem inválida: {dados.categoria_nasem!r}")
    campos = {c: dados.valores.get(c) for c in CAMPOS_NUTRICIONAIS}
    extras = {k: v for k, v in dados.valores.items() if k not in CAMPOS_NUTRICIONAIS}
    item = AlimentoNutricional(
        alimento_id=dados.alimento_id, nome=dados.nome, categoria_nasem=dados.categoria_nasem, conc_pct=dados.conc_pct,
        fonte=dados.fonte, observacao=dados.observacao, fazenda_id=fazenda_id, usuario_id=user.id,
        extras_json=json.dumps(extras) if extras else None, **campos,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _nutricional_publico(item)


@router.put("/alimentos/{item_id}")
def atualizar_alimento_nutricional(
    item_id: int, dados: AlimentoNutricionalIn, fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(AlimentoNutricional, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Não encontrado")
    if dados.categoria_nasem not in CATEGORIAS_NASEM:
        raise HTTPException(status_code=400, detail=f"categoria_nasem inválida: {dados.categoria_nasem!r}")
    item.nome, item.categoria_nasem, item.conc_pct = dados.nome, dados.categoria_nasem, dados.conc_pct
    item.fonte, item.observacao = dados.fonte, dados.observacao
    for campo in CAMPOS_NUTRICIONAIS:
        setattr(item, campo, dados.valores.get(campo))
    extras = {k: v for k, v in dados.valores.items() if k not in CAMPOS_NUTRICIONAIS}
    item.extras_json = json.dumps(extras) if extras else None
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    return _nutricional_publico(item)


@router.delete("/alimentos/{item_id}")
def excluir_alimento_nutricional(
    item_id: int, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(AlimentoNutricional, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Não encontrado")
    session.delete(item)
    session.commit()
    return {"ok": True}


@router.get("/alimentos/{alimento_id}/resolver")
def resolver_alimento(
    alimento_id: int, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """Resolve em cascata biblioteca → análise bromatológica mais recente →
    template por categoria (ver Etapa 1, "Importar do cadastro")."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    alimento = session.get(Alimento, alimento_id)
    if not alimento or (fazenda_id is not None and alimento.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Alimento não encontrado")

    query_nutri = select(AlimentoNutricional).where(AlimentoNutricional.alimento_id == alimento_id, AlimentoNutricional.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_nutri = query_nutri.where(AlimentoNutricional.fazenda_id == fazenda_id)
    entrada_biblioteca = session.exec(query_nutri).first()
    if entrada_biblioteca:
        pub = _nutricional_publico(entrada_biblioteca)
        return {
            "nome": alimento.nome, "categoria_nasem": entrada_biblioteca.categoria_nasem, "conc_pct": entrada_biblioteca.conc_pct,
            "origem": "biblioteca", "alimento_nutricional_id": entrada_biblioteca.id, "analise_bromatologica_id": None,
            "valores": pub["valores"],
        }

    # Análise bromatológica mais recente — casa por alimento_id OU (sem
    # alimento_id e nome igual), já que muitos laudos existentes só têm o
    # nome em texto livre (RA12 da auditoria).
    query_analise = select(AnaliseBromatologica).where(
        (AnaliseBromatologica.alimento_id == alimento_id)
        | ((AnaliseBromatologica.alimento_id == None) & (AnaliseBromatologica.alimento == alimento.nome))  # noqa: E711
    )
    if fazenda_id is not None:
        query_analise = query_analise.where(AnaliseBromatologica.fazenda_id == fazenda_id)
    analises = sorted(session.exec(query_analise).all(), key=lambda a: a.data, reverse=True)
    if analises:
        laudo = analises[0]
        template = template_por_categoria("Outros")
        valores = dict(template)
        for campo in ("ms_pct", "pb_pct", "fdn_pct", "fda_pct", "ee_pct", "cinzas_pct", "ca_pct", "p_pct"):
            valor_laudo = getattr(laudo, campo, None)
            if valor_laudo is not None:
                valores[campo] = valor_laudo
        return {
            "nome": alimento.nome, "categoria_nasem": "Outros", "conc_pct": 0.0, "origem": "bromatologica",
            "alimento_nutricional_id": None, "analise_bromatologica_id": laudo.id, "valores": valores,
        }

    return {
        "nome": alimento.nome, "categoria_nasem": "Outros", "conc_pct": 0.0, "origem": "template",
        "alimento_nutricional_id": None, "analise_bromatologica_id": None, "valores": template_por_categoria("Outros"),
    }


@router.get("/templates")
def listar_templates() -> dict:
    return {
        "categorias": {cat: template_por_categoria(cat) for cat in sorted(CATEGORIAS_NASEM)},
        "biblioteca_semente": biblioteca_semente(),
    }


# ---------------------------------------------------------------------------
# Contexto do lote (Etapa 2)
# ---------------------------------------------------------------------------
@router.get("/contexto/{lote}")
def contexto_formulacao(
    lote: int, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    base = contexto_lote(session, fazenda_id, lote)
    campos_estimados: list[str] = []

    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais = [a for a in session.exec(query_animais).all() if not a.eh_semen and a.sexo != "M"]
    numeros_do_lote = {a.numero for a in animais if (a.grupo_primario or "").split(" - ")[0].strip() == f"{lote:02d}"}

    peso_vivo_kg = None
    if numeros_do_lote:
        query_peso = select(PesagemCorporal).where(PesagemCorporal.numero_matriz.in_(numeros_do_lote))
        if fazenda_id is not None:
            query_peso = query_peso.where(PesagemCorporal.fazenda_id == fazenda_id)
        pesagens = session.exec(query_peso).all()
        recentes: dict[str, PesagemCorporal] = {}
        limite = date.today().replace(year=date.today().year - 1)
        for p in pesagens:
            if p.data_pesagem < limite:
                continue
            atual = recentes.get(p.numero_matriz)
            if not atual or p.data_pesagem > atual.data_pesagem:
                recentes[p.numero_matriz] = p
        if len(recentes) >= max(1, round(0.3 * len(numeros_do_lote))):
            pesos = [p.peso_kg for p in recentes.values()]
            peso_vivo_kg = round(sum(pesos) / len(pesos), 1)
            campos_estimados.append("peso_vivo_kg")

    ecc = None
    if numeros_do_lote:
        query_secagem = select(Secagem).where(Secagem.numero_matriz.in_(numeros_do_lote), Secagem.escore_condicao_corporal != None)  # noqa: E711
        if fazenda_id is not None:
            query_secagem = query_secagem.where(Secagem.fazenda_id == fazenda_id)
        limite = date.today().replace(year=date.today().year - 1)
        escores = [s.escore_condicao_corporal for s in session.exec(query_secagem).all() if s.data_secagem >= limite]
        if len(escores) >= 3:
            ecc = round(sum(escores) / len(escores), 2)
            campos_estimados.append("ecc")

    if base.get("del_medio") is not None:
        campos_estimados.append("del_dias")
    if base.get("media_cl") is not None:
        campos_estimados.append("producao_leite_kg_dia")

    return {
        **base, "peso_vivo_kg": peso_vivo_kg, "ecc": ecc,
        "del_dias": base.get("del_medio"), "producao_leite_kg_dia": base.get("media_cl"),
        "campos_estimados": campos_estimados,
    }
