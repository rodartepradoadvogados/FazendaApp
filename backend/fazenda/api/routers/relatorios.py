"""
Router de relatórios gerenciais e de manejo reprodutivo.

Endpoints:
- GET /relatorios/manejo — 8 listas semaforizadas (o que fazer hoje).
- GET /relatorios/gerencial/distribuicao-del?ordem&del_min&del_max
- GET /relatorios/gerencial/prenhezes-por-del?del_min&del_max
- GET /relatorios/gerencial/dias-diagnostico?del_min&del_max
- GET /relatorios/gerencial/intervalo-servicos
- GET /relatorios/gerencial/dias-reinseminacao
- GET /relatorios/gerencial/taxa-servico-prenhez
- GET /relatorios/gerencial/fluxo-lactacao?meses
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Animal, EstoqueSemen, Lactacao, Parto, PesagemCorporal, ProtocoloIatfAplicacao, Secagem, Servico
from fazenda.rules import relatorios_gerenciais as rg

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


def _dados(session: Session, fazenda_id: int | None = None):
    query_animais = select(Animal)
    query_servicos = select(Servico)
    query_partos = select(Parto)
    query_secagens = select(Secagem)
    # Piloto conservador de multi-fazenda (ver animais.py:listar_animais): só
    # filtra quando o token carrega uma fazenda selecionada.
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
        query_secagens = query_secagens.where(Secagem.fazenda_id == fazenda_id)
    animais = [a.model_dump() for a in session.exec(query_animais).all()]
    servicos = [s.model_dump() for s in session.exec(query_servicos).all()]
    partos = [p.model_dump() for p in session.exec(query_partos).all()]
    secagens = [s.model_dump() for s in session.exec(query_secagens).all()]
    return animais, servicos, partos, secagens


def _dados_estado_vivo(session: Session, fazenda_id: int | None = None):
    """As duas cargas extras que só o estado reprodutivo ao vivo usa.

    Ficam fora de `_dados` de propósito: os seis endpoints de gráfico desta
    rota pedem só `servicos`/`partos` e pagariam duas varreduras de tabela
    inteira para jogar o resultado fora.
    """
    # SEM filtro de `realizada`: a linha de D0 já está realizada quando o
    # implante foi colocado — sem ela o estado EM_PROTOCOLO nunca sai (ver
    # mesmo padrão em agenda.py::calcular_agenda).
    query_iatf = select(ProtocoloIatfAplicacao)
    query_pesagens = select(PesagemCorporal)
    query_lactacao = select(Lactacao)
    if fazenda_id is not None:
        query_iatf = query_iatf.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
        query_pesagens = query_pesagens.where(PesagemCorporal.fazenda_id == fazenda_id)
        query_lactacao = query_lactacao.where(Lactacao.fazenda_id == fazenda_id)
    aplicacoes_iatf = [ap.model_dump() for ap in session.exec(query_iatf).all()]
    # Peso vivo mais recente por matriz — entra na aptidão da novilha
    # nulípara no estado ao vivo (mesmo padrão de agenda.py e reproducao.py).
    peso_por_animal: dict[str, float] = {}
    ultima_pesagem: dict[str, date] = {}
    for pes in session.exec(query_pesagens).all():
        if pes.numero_matriz not in ultima_pesagem or pes.data_pesagem > ultima_pesagem[pes.numero_matriz]:
            ultima_pesagem[pes.numero_matriz] = pes.data_pesagem
            peso_por_animal[pes.numero_matriz] = pes.peso_kg
    # Lactações abertas sem Parto (indução, aborto) — "parto virtual" pro PEV
    # e pro "a inseminar" de relatorios_gerenciais.relatorios_manejo, mesma
    # lógica de agenda.py/indicadores.py/reproducao.py.
    inicio_lactacao_por_animal: dict[str, date] = {}
    for lact in session.exec(query_lactacao).all():
        if lact.data_fim is not None:
            continue
        if lact.data_inicio is None:
            continue
        inicio_lactacao_por_animal[lact.numero_matriz] = lact.data_inicio
    return aplicacoes_iatf, peso_por_animal, inicio_lactacao_por_animal


@router.get("/manejo")
def relatorios_manejo(
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    animais, servicos, partos, secagens = _dados(session, fazenda_id)
    aplicacoes_iatf, peso_por_animal, inicio_lactacao_por_animal = _dados_estado_vivo(session, fazenda_id)
    # BUG DE SEGURANÇA CORRIGIDO: sem o filtro, este relatório de manejo
    # trazia o estoque de sêmen (touro/NAAB/doses) de TODAS as fazendas —
    # mesma classe de vazamento já corrigida em relatorio_acasalamento.py
    # (ver tests/test_isolamento_relatorios_fornecedor.py).
    query_semen = select(EstoqueSemen)
    if fazenda_id is not None:
        query_semen = query_semen.where(EstoqueSemen.fazenda_id == fazenda_id)
    semen = [s.model_dump() for s in session.exec(query_semen).all()]
    return rg.relatorios_manejo(animais, servicos, partos, semen, date.today(), secagens=secagens,
                                 aplicacoes_iatf=aplicacoes_iatf, peso_por_animal=peso_por_animal,
                                 inicio_lactacao_por_animal=inicio_lactacao_por_animal)


@router.get("/gerencial/distribuicao-del")
def gerencial_distribuicao_del(
    ordem: int = Query(1, ge=1, le=4, description="1, 2, 3 ou 4 (=4º ou mais)"),
    del_min: int = Query(0, ge=0),
    del_max: int = Query(350, ge=0),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, _, _ = _dados(session, fazenda_id)
    return rg.distribuicao_del(servicos, ordem, del_min, del_max)


@router.get("/gerencial/prenhezes-por-del")
def gerencial_prenhezes_por_del(
    del_min: int = Query(0, ge=0),
    del_max: int = Query(400, ge=0),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, _, _ = _dados(session, fazenda_id)
    return rg.prenhezes_por_del(servicos, del_min, del_max)


@router.get("/gerencial/dias-diagnostico")
def gerencial_dias_diagnostico(
    del_min: int = Query(0, ge=0),
    del_max: int = Query(400, ge=0),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, _, _ = _dados(session, fazenda_id)
    return rg.dias_para_diagnostico(servicos, del_min, del_max)


@router.get("/gerencial/intervalo-servicos")
def gerencial_intervalo_servicos(
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, _, _ = _dados(session, fazenda_id)
    return rg.intervalo_entre_servicos(servicos)


@router.get("/gerencial/dias-reinseminacao")
def gerencial_dias_reinseminacao(
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, partos, _ = _dados(session, fazenda_id)
    return rg.dias_para_reinseminacao(servicos, partos)


@router.get("/gerencial/taxa-servico-prenhez")
def gerencial_taxa_servico_prenhez(
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    animais, servicos, partos, _ = _dados(session, fazenda_id)
    return rg.taxa_servico_prenhez(animais, servicos, partos, date.today())


@router.get("/gerencial/fluxo-lactacao")
def gerencial_fluxo_lactacao(
    meses: int = Query(8, ge=1, le=24),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    animais, servicos, partos, secagens = _dados(session, fazenda_id)
    return rg.fluxo_lactacao(animais, servicos, partos, date.today(), meses, secagens=secagens)
