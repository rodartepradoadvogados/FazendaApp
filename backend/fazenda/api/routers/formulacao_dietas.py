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

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.models import (
    Alimento, AlimentoNutricional, AnaliseBromatologica, Animal, DietaSimulacao, DietaSimulacaoItem,
    PesagemCorporal, Secagem, Usuario,
)
from fazenda.models.formulacao import CAMPOS_CNCPS_FRACIONAMENTO
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.biblioteca_alimentos import (
    avisos_fechamento_fracoes, excluir_ou_restaurar, gerar_modelo_planilha, importar_planilha, listar_biblioteca,
    obter_para_editar,
)
from fazenda.rules.busca import casa_busca
from fazenda.rules.dieta_lancamento import contexto_lote, criar_lancamento_programado
from fazenda.rules.nutricao import VERSAO_MOTOR, avaliar_dieta, resultado_para_dict
from fazenda.rules.nutricao.balanco import situacao_da_linha
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
    # "kg" = -0,30 kg MS/dia (Duffield et al., 2008) | "pct" = -2% do CMS |
    # "manual" = o valor de monensina_reducao_manual. Ver constantes do motor.
    monensina_modo: str = "kg"
    monensina_reducao_manual: float | None = None
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
    # Overrides manuais da coluna "Exigência" da Etapa 4, {nutriente: valor}
    # — ver docstring de DietaSimulacao.exigencias_editadas_json.
    exigencias_editadas: dict[str, float] | None = None


class CalcularIn(BaseModel):
    animal: AnimalIn
    itens: list[IngredienteIn]
    exigencias_editadas: dict[str, float] | None = None


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
    # Faixa típica de inclusão na dieta, % da MS TOTAL da dieta — ver
    # docstring de AlimentoNutricional.inclusao_min_pct/inclusao_max_pct.
    inclusao_min_pct: float | None = None
    inclusao_max_pct: float | None = None
    valores: dict[str, float | None] = {}
    # Quais chaves de `valores` foram digitadas à mão pelo usuário desta
    # fazenda (em vez de ainda serem o valor puxado da linha mestre CowData)
    # — mesma convenção `campos_editados` de DietaSimulacaoItem/GradeAlimentos
    # (ver docstring de AlimentoNutricional.campos_editados_json). Puramente
    # de exibição (cinza/preto na tela); não afeta cálculo nenhum.
    campos_editados: list[str] = []


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


def _aplicar_exigencias_editadas(resultado_dict: dict, exigencias_editadas: dict[str, float] | None) -> dict:
    """Sobrepõe manualmente a "Exigência" de uma ou mais linhas do balanço
    (Etapa 4) com o valor que o nutricionista digitou, recalculando
    balanço/situação daquela linha a partir do MESMO "fornecido" que o motor
    já calculou — o resto da dieta (CMS, energia, proteína, minerais) não
    muda, só a leitura daquela exigência específica. Sem overrides, devolve
    `resultado_dict` intacto (é o caminho comum — Etapa 4 sem edição manual)."""
    if not exigencias_editadas:
        return resultado_dict
    for linha in resultado_dict.get("balanco") or []:
        if linha["nutriente"] not in exigencias_editadas:
            continue
        exigencia = exigencias_editadas[linha["nutriente"]]
        balanco = linha["fornecido"] - exigencia
        linha["exigencia"] = exigencia
        linha["balanco"] = balanco
        linha["situacao"] = situacao_da_linha(balanco, exigencia)
    return resultado_dict


def _calcular(animal_in: AnimalIn, itens_in: list[IngredienteIn], exigencias_editadas: dict[str, float] | None = None) -> dict:
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
    resultado_dict = resultado_para_dict(resultado)
    return _aplicar_exigencias_editadas(resultado_dict, exigencias_editadas)


# ---------------------------------------------------------------------------
# Cálculo stateless — o motor do balanço ao vivo (Etapa 4)
# ---------------------------------------------------------------------------
@router.post("/calcular")
def calcular(dados: CalcularIn) -> dict:
    return _calcular(dados.animal, dados.itens, dados.exigencias_editadas)


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
    dados: SimulacaoCriarIn, fazenda_id: int | None = Depends(get_fazenda_id_escrita),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    # `DietaSimulacao.fazenda_id` é obrigatório (não Optional) — mantém a
    # guarda mesmo depois do resolvedor porque ele só devolve None em
    # silêncio no ambiente sem multi-fazenda provisionado nenhum (ver
    # docstring de resolver_fazenda_id_escrita); em qualquer outro caso
    # ambíguo ele mesmo já recusa com 409.
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
    dados["exigencias_editadas"] = json.loads(sim.exigencias_editadas_json) if sim.exigencias_editadas_json else {}
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

    resultado_dict = _calcular(dados.animal, dados.itens, dados.exigencias_editadas)

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
    sim.exigencias_editadas_json = json.dumps(dados.exigencias_editadas) if dados.exigencias_editadas else None
    sim.atualizado_em = datetime.utcnow()
    if sim.status == "rascunho" and resultado_dict.get("consumo", {}).get("cms_kg_dia"):
        sim.status = "concluida"
    session.add(sim)

    for ordem, item_in in enumerate(dados.itens):
        session.add(DietaSimulacaoItem(
            # `sim.fazenda_id` (obrigatório, já resolvido na criação da
            # simulação — ver criar_simulacao), NUNCA a variável `fazenda_id`
            # tolerante a nulo desta função (usada só para o filtro de
            # LEITURA acima): um dono-equivalente editando sem fazenda
            # selecionada faria `fazenda_id` chegar None aqui e gravaria o
            # item órfão, mesmo a simulação-pai já tendo fazenda_id certo.
            fazenda_id=sim.fazenda_id, simulacao_id=simulacao_id, ordem=ordem,
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

    # `original.fazenda_id` (obrigatório, já resolvido quando a simulação
    # original foi criada) — NÃO a variável `fazenda_id` tolerante a nulo
    # desta função: duplicar sempre pertence à MESMA fazenda da original,
    # então nem precisa re-resolver do token (evita um dono-equivalente sem
    # fazenda selecionada gravar a cópia órfã, igual ao bug corrigido em
    # salvar_simulacao acima).
    nova = DietaSimulacao(
        nome=dados.nome.strip() or f"{original.nome} (cópia)", lote=original.lote, fazenda_id=original.fazenda_id,
        usuario_id=user.id, status="rascunho", etapa_atual=original.etapa_atual,
        **{f: getattr(original, f) for f in AnimalIn.model_fields},
        resultado_json=original.resultado_json, avisos_json=original.avisos_json,
        motor_versao=original.motor_versao, calculado_em=original.calculado_em,
        exigencias_editadas_json=original.exigencias_editadas_json,
    )
    session.add(nova)
    session.commit()
    session.refresh(nova)
    for item in itens_originais:
        session.add(DietaSimulacaoItem(
            fazenda_id=nova.fazenda_id, simulacao_id=nova.id, ordem=item.ordem, alimento_id=item.alimento_id,
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
    exigencias_editadas = json.loads(sim.exigencias_editadas_json) if sim.exigencias_editadas_json else None
    resultado_dict = _calcular(animal_in, itens_in, exigencias_editadas)  # sempre recalcula fresco antes de aplicar (RA5)

    cms = (resultado_dict.get("consumo") or {}).get("cms_kg_dia")
    if not cms or cms <= 0 or (isinstance(cms, float) and math.isnan(cms)):
        raise HTTPException(status_code=422, detail="O consumo de matéria seca calculado é inválido — revise os dados do animal antes de aplicar.")
    if any(a.get("severidade") == "bloqueante" for a in resultado_dict.get("avisos") or []):
        raise HTTPException(status_code=422, detail="Há um aviso bloqueante nesta simulação — resolva-o antes de aplicar na dieta.")

    # `sim.fazenda_id` (obrigatório, resolvido na criação da simulação) daqui
    # pra baixo — não a variável `fazenda_id` tolerante a nulo desta função
    # (só serve para a LEITURA da própria simulação acima): o lançamento
    # gerado tem que pertencer à fazenda da simulação, nunca a uma fazenda
    # nula/errada por causa de token sem "fid".
    contexto = contexto_lote(session, sim.fazenda_id, dados.lote)
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
        session, sim.fazenda_id, user.id,
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
# Biblioteca de alimentos — Etapa 1 (grade) + aba "Biblioteca de referência"
# ---------------------------------------------------------------------------
def _nutricional_publico(a: AlimentoNutricional) -> dict:
    valores = {campo: getattr(a, campo) for campo in CAMPOS_NUTRICIONAIS if campo != "custo_kg_mn"}
    valores["custo_kg_mn"] = a.custo_kg_mn
    # Frações CNCPS (fora de CAMPOS_NUTRICIONAIS de propósito — ver docstring
    # de CAMPOS_CNCPS_FRACIONAMENTO) entram no mesmo dict `valores` que o
    # resto — a tela não distingue tecnicamente as duas origens, só agrupa
    # visualmente por seção.
    for campo in CAMPOS_CNCPS_FRACIONAMENTO:
        valores[campo] = getattr(a, campo)
    if a.extras_json:
        valores.update(json.loads(a.extras_json))
    eh_mestre = a.fazenda_id is None
    return {
        "id": a.id, "alimento_id": a.alimento_id, "nome": a.nome, "categoria_nasem": a.categoria_nasem,
        "conc_pct": a.conc_pct, "fonte": a.fonte, "observacao": a.observacao, "ativo": a.ativo,
        "inclusao_min_pct": a.inclusao_min_pct, "inclusao_max_pct": a.inclusao_max_pct,
        # eh_mestre: item da biblioteca padrão CowData, ainda não copiado por
        # esta fazenda — só pode ser editado/excluído via copy-on-write (o
        # PUT/DELETE fazem isso sozinhos, a tela só precisa saber pra rotular
        # "CowData"/"Restaurar padrão" em vez de "Excluir"). eh_copia_editada:
        # já é uma cópia desta fazenda de um item mestre (editou ou ocultou).
        "eh_mestre": eh_mestre,
        "eh_copia_editada": (not eh_mestre) and a.origem_mestre_id is not None,
        # Cinza/preto na tela — ver AlimentoNutricional.campos_editados_json.
        "campos_editados": json.loads(a.campos_editados_json or "[]"),
        # Checagem de fechamento das frações CNCPS (nunca bloqueia — ver
        # avisos_fechamento_fracoes); vazio = fecha dentro da tolerância ou
        # nada foi preenchido ainda.
        "avisos_fechamento": avisos_fechamento_fracoes(a),
        "valores": valores,
    }


@router.get("/alimentos")
def listar_alimentos_nutricionais(
    busca: str | None = None, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    biblioteca = listar_biblioteca(session, fazenda_id)
    if busca:
        # casa_busca ignora caixa/acento/hífen/underscore/espaço — mesmo
        # critério de qualquer outra busca textual do sistema (rules/busca.py).
        biblioteca = [a for a in biblioteca if casa_busca(busca, a.nome)]
    com_composicao = {a.alimento_id for a in biblioteca if a.alimento_id}

    query_alimento = select(Alimento).where(Alimento.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_alimento = query_alimento.where(Alimento.fazenda_id == fazenda_id)
    cadastrados = session.exec(query_alimento).all()
    if busca:
        cadastrados = [a for a in cadastrados if casa_busca(busca, a.nome)]

    return {
        "biblioteca": [_nutricional_publico(a) for a in sorted(biblioteca, key=lambda a: a.nome)],
        "cadastrados": [
            {"id": a.id, "nome": a.nome, "sem_composicao": a.id not in com_composicao}
            for a in sorted(cadastrados, key=lambda a: a.nome)
        ],
    }


@router.post("/alimentos", status_code=201)
def criar_alimento_nutricional(
    dados: AlimentoNutricionalIn, fazenda_id: int | None = Depends(get_fazenda_id_escrita),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    # Guarda explícita (não confia só no resolvedor): `fazenda_id` é a ÚNICA
    # coluna do sistema em que NULO é um valor legítimo (marca a biblioteca
    # MESTRE) — se deixasse passar None aqui, o item "próprio" desta fazenda
    # viraria indistinguível de um item mestre global, visível para TODAS as
    # outras fazendas. Nas demais tabelas do módulo um fazenda_id nulo já é
    # barrado pelo próprio resolvedor (409); aqui precisa ser barrado também
    # no caminho "multi-fazenda não provisionado" (resolvedor devolve None
    # em silêncio nesse caso — ver docstring de resolver_fazenda_id_escrita).
    if fazenda_id is None:
        raise HTTPException(status_code=400, detail="Selecione a fazenda antes de cadastrar")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe um nome para o alimento")
    if dados.categoria_nasem not in CATEGORIAS_NASEM:
        raise HTTPException(status_code=400, detail=f"categoria_nasem inválida: {dados.categoria_nasem!r}")
    campos = {c: dados.valores.get(c) for c in CAMPOS_NUTRICIONAIS}
    campos_cncps = {c: dados.valores.get(c) for c in CAMPOS_CNCPS_FRACIONAMENTO}
    extras = {k: v for k, v in dados.valores.items() if k not in CAMPOS_NUTRICIONAIS and k not in CAMPOS_CNCPS_FRACIONAMENTO}
    item = AlimentoNutricional(
        alimento_id=dados.alimento_id, nome=dados.nome.strip(), categoria_nasem=dados.categoria_nasem, conc_pct=dados.conc_pct,
        fonte=dados.fonte, observacao=dados.observacao, fazenda_id=fazenda_id, usuario_id=user.id,
        inclusao_min_pct=dados.inclusao_min_pct, inclusao_max_pct=dados.inclusao_max_pct,
        campos_editados_json=json.dumps(dados.campos_editados) if dados.campos_editados else None,
        extras_json=json.dumps(extras) if extras else None, **campos, **campos_cncps,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _nutricional_publico(item)


@router.put("/alimentos/{item_id}")
def atualizar_alimento_nutricional(
    item_id: int, dados: AlimentoNutricionalIn, fazenda_id: int | None = Depends(get_fazenda_id_escrita),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    """Editar um item da biblioteca MESTRE nunca grava na linha mestre — cria
    (ou reaproveita) a cópia-por-fazenda via `obter_para_editar` (copy-on-write,
    ver fazenda.rules.biblioteca_alimentos). As outras fazendas continuam
    vendo a mestre original, intocada."""
    # Sem fazenda resolvida, `obter_para_editar` devolveria a PRÓPRIA linha
    # mestre para edição direta (ver seu docstring) — o oposto do
    # copy-on-write que este endpoint promete. Trava aqui, não lá: a função
    # de regra continua servindo outros chamadores tolerantes a fazenda nula.
    if fazenda_id is None:
        raise HTTPException(status_code=400, detail="Selecione a fazenda antes de editar")
    if dados.categoria_nasem not in CATEGORIAS_NASEM:
        raise HTTPException(status_code=400, detail=f"categoria_nasem inválida: {dados.categoria_nasem!r}")
    item = obter_para_editar(session, fazenda_id, item_id)
    item.nome, item.categoria_nasem, item.conc_pct = dados.nome.strip() or item.nome, dados.categoria_nasem, dados.conc_pct
    item.fonte, item.observacao = dados.fonte, dados.observacao
    item.alimento_id = dados.alimento_id
    item.inclusao_min_pct, item.inclusao_max_pct = dados.inclusao_min_pct, dados.inclusao_max_pct
    for campo in CAMPOS_NUTRICIONAIS:
        setattr(item, campo, dados.valores.get(campo))
    for campo in CAMPOS_CNCPS_FRACIONAMENTO:
        setattr(item, campo, dados.valores.get(campo))
    extras = {k: v for k, v in dados.valores.items() if k not in CAMPOS_NUTRICIONAIS and k not in CAMPOS_CNCPS_FRACIONAMENTO}
    item.extras_json = json.dumps(extras) if extras else None
    item.campos_editados_json = json.dumps(dados.campos_editados) if dados.campos_editados else None
    item.atualizado_em = datetime.utcnow()
    if item.usuario_id is None:
        item.usuario_id = user.id
    session.add(item)
    session.commit()
    session.refresh(item)
    return _nutricional_publico(item)


@router.delete("/alimentos/{item_id}")
def excluir_alimento_nutricional(
    item_id: int, fazenda_id: int | None = Depends(get_fazenda_id_escrita), session: Session = Depends(get_session),
) -> dict:
    """Um único botão de excluir cobre os 3 casos do CRUD (ver
    `excluir_ou_restaurar`): item próprio some de vez; cópia editada de um
    item mestre "volta ao padrão CowData"; item mestre nunca editado é
    ocultado só para esta fazenda, sem afetar as outras."""
    # Sem isto, `excluir_ou_restaurar` com fazenda_id=None pula a checagem
    # de isolamento entre fazendas (ela só compara `item.fazenda_id !=
    # fazenda_id` quando fazenda_id não é nulo) — deixaria excluir/restaurar
    # item de OUTRA fazenda sem dono resolvido barrar o acesso.
    if fazenda_id is None:
        raise HTTPException(status_code=400, detail="Selecione a fazenda antes de remover um item da biblioteca")
    return excluir_ou_restaurar(session, fazenda_id, item_id)


@router.get("/alimentos/modelo")
def baixar_modelo_biblioteca() -> Response:
    """Planilha-modelo (.xlsx) para carregar alimentos em lote — cabeçalho já
    com os nomes de coluna reconhecidos + uma linha de exemplo preenchida
    (ver POST /formulacao/alimentos/importar e o mini manual da aba)."""
    conteudo = gerar_modelo_planilha()
    return Response(
        content=conteudo, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="biblioteca_alimentos_modelo.xlsx"'},
    )


@router.post("/alimentos/importar")
async def importar_biblioteca(
    file: UploadFile, fazenda_id: int | None = Depends(get_fazenda_id_escrita), session: Session = Depends(get_session),
) -> dict:
    """Importa alimentos em lote de um .xlsx ou .csv — cria/atualiza sempre
    na biblioteca DESTA fazenda (copy-on-write se o nome bater com um item
    mestre ainda não sobrescrito). Ver mini manual da aba "Biblioteca de
    referência" pras regras de coluna obrigatória/reconhecida/faixa válida."""
    conteudo = await file.read()
    return importar_planilha(session, fazenda_id, file.filename or "", conteudo)


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
            "inclusao_min_pct": entrada_biblioteca.inclusao_min_pct, "inclusao_max_pct": entrada_biblioteca.inclusao_max_pct,
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
            "alimento_nutricional_id": None, "analise_bromatologica_id": laudo.id,
            "inclusao_min_pct": None, "inclusao_max_pct": None, "valores": valores,
        }

    return {
        "nome": alimento.nome, "categoria_nasem": "Outros", "conc_pct": 0.0, "origem": "template",
        "alimento_nutricional_id": None, "analise_bromatologica_id": None,
        "inclusao_min_pct": None, "inclusao_max_pct": None, "valores": template_por_categoria("Outros"),
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
