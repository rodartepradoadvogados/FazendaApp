"""
Cadastro > Empreitada, Contrato, Diária e Vale avulso — trabalho contratado
pago por frequência/etapa (Empreitada), contrato com ou sem frequência fixa
(Contrato), diária com saldo devedor acumulado (Diária) e o adiantamento
avulso comum às três (Vale avulso). Também expõe
`GET /folha-pagamento-unificada`, o ledger consolidado de TODOS os
lançamentos de RH (funcionário, empreita, contrato, diária) — por isso
importa `listar_folha_pagamento`/`_competencia_seguinte` de rh_folha.py.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, exigir_admin, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, ContaGerencial, Contrato, ContratoParcela, Diaria, DiariaAuditoria, DiariaPagamento, Empreitada,
    EmpreitadaEtapa, EmpreitadaParcela, ParametroDiariaPadrao, Pessoa, Usuario, ValeAvulso,
)
from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.rules.auditoria import fazenda_id_seguro

from .rh_folha import _competencia_seguinte, listar_folha_pagamento

router = APIRouter()

@router.get("/folha-pagamento-unificada")
def listar_folha_pagamento_unificada(session: Session = Depends(get_session)) -> list[dict]:
    """
    Visão consolidada de TODOS os lançamentos de folha — funcionário, empreita,
    contrato e diária — num único ledger ordenável/filtrável por vencimento,
    priorizando pendências (destacando as vencidas). `origem_tipo` (=`tipo`) +
    `origem_id` apontam para o registro de origem só para permitir excluir
    lançamentos ainda pendentes; a edição continua nas telas específicas.
    """
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    linhas: list[dict] = []

    for r in listar_folha_pagamento(session):
        linhas.append({
            "tipo": "funcionario", "origem_id": r["id"], "origem_subtipo": "folha",
            "pessoa_id": r["pessoa_id"], "pessoa_nome": r["pessoa_nome"],
            "descricao": f"Folha — {r['competencia']}",
            "valor": r["valor_liquido"],
            "data_vencimento": r["data_vencimento"],
            "data_pagamento": r["data_pagamento"],
            "status": r["status"],
            "pode_excluir": r["status"] == "pendente",
        })

    empreitadas = {e.id: e for e in session.exec(select(Empreitada)).all()}
    parcelas_empreita = session.exec(select(EmpreitadaParcela)).all()
    etapas_empreita = session.exec(
        select(EmpreitadaEtapa).where(EmpreitadaEtapa.concluida == True)  # noqa: E712
    ).all()
    numeros_empreita = [p.numero_lancamento_gerado for p in parcelas_empreita if p.numero_lancamento_gerado] + [
        et.numero_lancamento_gerado for et in etapas_empreita if et.numero_lancamento_gerado
    ]
    contas_empreita = {
        c.numero_lancamento: c
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros_empreita))).all()
    } if numeros_empreita else {}
    for p in parcelas_empreita:
        e = empreitadas.get(p.empreitada_id)
        if not e:
            continue
        conta = contas_empreita.get(p.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "empreita", "origem_id": p.id, "origem_subtipo": "parcela",
            "pessoa_id": e.pessoa_id, "pessoa_nome": pessoas.get(e.pessoa_id, "—"),
            "descricao": f"Empreita — {e.descricao}",
            "valor": p.valor,
            "data_vencimento": p.data_vencimento,
            "data_pagamento": conta.data_pagamento if conta else None,
            "status": "pago" if pago else "pendente",
            "pode_excluir": not pago,
        })
    for et in etapas_empreita:
        e = empreitadas.get(et.empreitada_id)
        if not e:
            continue
        conta = contas_empreita.get(et.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "empreita", "origem_id": et.id, "origem_subtipo": "etapa",
            "pessoa_id": e.pessoa_id, "pessoa_nome": pessoas.get(e.pessoa_id, "—"),
            "descricao": f"Empreita — {e.descricao} — etapa: {et.nome}",
            "valor": et.valor,
            "data_vencimento": conta.data_vencimento if conta else None,
            "data_pagamento": conta.data_pagamento if conta else None,
            "status": "pago" if pago else "pendente",
            "pode_excluir": False,
        })

    contratos = {c.id: c for c in session.exec(select(Contrato)).all()}
    parcelas_contrato = session.exec(select(ContratoParcela)).all()
    numeros_contrato = [p.numero_lancamento_gerado for p in parcelas_contrato if p.numero_lancamento_gerado]
    contas_contrato = {
        c.numero_lancamento: c
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros_contrato))).all()
    } if numeros_contrato else {}
    for p in parcelas_contrato:
        c = contratos.get(p.contrato_id)
        if not c:
            continue
        conta = contas_contrato.get(p.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "contrato", "origem_id": p.id, "origem_subtipo": "parcela",
            "pessoa_id": c.pessoa_id, "pessoa_nome": pessoas.get(c.pessoa_id, "—"),
            "descricao": f"Contrato — {c.descricao}",
            "valor": p.valor,
            "data_vencimento": p.data_vencimento,
            "data_pagamento": conta.data_pagamento if conta else None,
            "status": "pago" if pago else "pendente",
            "pode_excluir": not pago,
        })

    diarias = {d.id: d for d in session.exec(select(Diaria)).all()}
    for pg in session.exec(select(DiariaPagamento)).all():
        d = diarias.get(pg.diaria_id)
        if not d:
            continue
        linhas.append({
            "tipo": "diaria", "origem_id": pg.id, "origem_subtipo": "pagamento",
            "pessoa_id": d.pessoa_id, "pessoa_nome": pessoas.get(d.pessoa_id, "—"),
            "descricao": "Diária",
            "valor": pg.valor,
            "data_vencimento": pg.data_pagamento,
            "data_pagamento": pg.data_pagamento,
            "status": "pago",
            "pode_excluir": False,
        })

    hoje = date.today()
    for linha in linhas:
        linha["vencido"] = bool(
            linha["status"] == "pendente" and linha["data_vencimento"] and linha["data_vencimento"] < hoje
        )

    # Prioriza pendente-vencido, depois pendente, depois pago; dentro de cada
    # grupo, o vencimento mais próximo primeiro.
    def _chave_prioridade(linha: dict):
        grupo = 0 if linha["vencido"] else (1 if linha["status"] == "pendente" else 2)
        return (grupo, linha["data_vencimento"] or date.max)

    linhas.sort(key=_chave_prioridade)
    return linhas




# ---------------------------------------------------------------------------
# Empreitada — trabalho contratado com um empreiteiro (Financeiro > Ações >
# Folha de Pagamento > Empreita). Paga por frequência fixa (parcelas editáveis,
# mesmo padrão do parcelamento do lançamento financeiro) ou por etapa
# concluída (cada etapa gera a conta a pagar no dia 1º do mês seguinte).
# ---------------------------------------------------------------------------
FORMAS_PAGAMENTO_FREQUENCIA = ["mensal", "semanal", "quinzenal"]
# Pagamento único numa data fixa (não recorrente) — "ao final da empreita" ou
# "no início da empreita". O frontend pede só a data e monta 1 parcela com o
# valor_total inteiro; entram no mesmo fluxo de `dados.parcelas` que mensal/
# semanal/quinzenal (ver FORMAS_PAGAMENTO_PARCELA abaixo).
FORMAS_PAGAMENTO_DATA_UNICA = ["inicio_empreita", "fim_empreita"]
FORMAS_PAGAMENTO_PARCELA = FORMAS_PAGAMENTO_FREQUENCIA + FORMAS_PAGAMENTO_DATA_UNICA
TIPOS_PAGAMENTO_EMPREITADA = FORMAS_PAGAMENTO_PARCELA + ["por_etapa"]


class EmpreitadaParcelaIn(BaseModel):
    data_vencimento: date
    valor: float


class EmpreitadaEtapaIn(BaseModel):
    nome: str
    valor: float


class EmpreitadaIn(BaseModel):
    pessoa_id: int
    descricao: str
    valor_total: float
    tipo_pagamento: str  # mensal | semanal | quinzenal | inicio_empreita | fim_empreita | por_etapa
    observacao: str | None = None
    # Preenchido quando tipo_pagamento é mensal/semanal/quinzenal (parcelamento
    # calculado e editável no frontend, mesmo padrão do Financeiro) ou
    # início/fim da empreita (1 única parcela, na data informada, valor cheio).
    parcelas: list[EmpreitadaParcelaIn] = []
    # Preenchido quando tipo_pagamento == "por_etapa" — nome + valor de cada
    # etapa (dividido proporcionalmente ou lançado específico, editável).
    etapas: list[EmpreitadaEtapaIn] = []
    centro_custo: str = "Pecuária Leiteira"


def _serializar_empreitada(session: Session, e: Empreitada) -> dict:
    parcelas = session.exec(
        select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == e.id).order_by(EmpreitadaParcela.data_vencimento)
    ).all()
    etapas = session.exec(
        select(EmpreitadaEtapa).where(EmpreitadaEtapa.empreitada_id == e.id).order_by(EmpreitadaEtapa.ordem, EmpreitadaEtapa.id)
    ).all()
    numeros = [n for n in [p.numero_lancamento_gerado for p in parcelas] + [et.numero_lancamento_gerado for et in etapas] if n]
    pagos = set()
    if numeros:
        contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all()
        pagos = {c.numero_lancamento for c in contas if c.valor_pago is not None}
    return {
        **e.model_dump(),
        "parcelas": [
            {**p.model_dump(), "status": "pago" if p.numero_lancamento_gerado in pagos else "pendente"} for p in parcelas
        ],
        "etapas": [
            {**et.model_dump(), "status_pagamento": "pago" if et.numero_lancamento_gerado in pagos else "pendente"}
            for et in etapas
        ],
        "vales": _listar_vales_avulsos(session, "empreitada", e.id),
    }


@router.get("/empreitadas")
def listar_empreitadas(session: Session = Depends(get_session)) -> list[dict]:
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    empreitadas = session.exec(select(Empreitada).order_by(Empreitada.criado_em.desc())).all()
    return [{**_serializar_empreitada(session, e), "pessoa_nome": pessoas.get(e.pessoa_id, "—")} for e in empreitadas]


@router.post("/empreitadas")
def criar_empreitada(
    dados: EmpreitadaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.tipo_pagamento not in TIPOS_PAGAMENTO_EMPREITADA:
        raise HTTPException(status_code=400, detail="Tipo de pagamento inválido")
    if dados.tipo_pagamento in FORMAS_PAGAMENTO_PARCELA and not dados.parcelas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma parcela para o pagamento por frequência")
    if dados.tipo_pagamento == "por_etapa" and not dados.etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa")

    empreitada = Empreitada(
        pessoa_id=dados.pessoa_id, descricao=dados.descricao, valor_total=dados.valor_total,
        tipo_pagamento=dados.tipo_pagamento, observacao=dados.observacao, usuario_id=user.id,
        centro_custo=dados.centro_custo,
    )
    session.add(empreitada)
    session.commit()
    session.refresh(empreitada)

    if dados.tipo_pagamento in FORMAS_PAGAMENTO_PARCELA:
        for parcela in dados.parcelas:
            numero_lancamento = _proximo_numero_lancamento(session, parcela.data_vencimento.year)
            session.add(EmpreitadaParcela(
                empreitada_id=empreitada.id, data_vencimento=parcela.data_vencimento, valor=parcela.valor,
                numero_lancamento_gerado=numero_lancamento,
            ))
            session.add(ContaGerencial(
                numero_lancamento=numero_lancamento,
                descricao=f"Empreita — {pessoa.nome} ({dados.descricao})",
                data_vencimento=parcela.data_vencimento,
                data_competencia=parcela.data_vencimento.replace(day=1),
                fornecedor_cliente=pessoa.nome,
                tipo_documento="Empreitada",
                centro_custo=dados.centro_custo,
                valor_total=parcela.valor,
                parcela_num=1, parcela_total=1,
                tipo="despesa", origem="auto",
                fazenda_id=fazenda_id,
            ))
    else:
        for i, etapa in enumerate(dados.etapas):
            session.add(EmpreitadaEtapa(empreitada_id=empreitada.id, nome=etapa.nome, valor=etapa.valor, ordem=i))
    session.commit()
    return _serializar_empreitada(session, empreitada)


@router.put("/empreitadas/{empreitada_id}/etapas/{etapa_id}/concluir")
def concluir_etapa_empreitada(
    empreitada_id: int, etapa_id: int, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Marca uma etapa como concluída e lança a conta a pagar correspondente no
    dia 1º do mês seguinte — cai automaticamente na Agenda (Gestão/Financeiro,
    a partir da própria data_vencimento da conta) e em Contas a Pagar, para
    análise/pagamento.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    etapa = session.get(EmpreitadaEtapa, etapa_id)
    if not etapa or etapa.empreitada_id != empreitada_id:
        raise HTTPException(status_code=404, detail="Etapa não encontrada")
    if etapa.concluida:
        raise HTTPException(status_code=400, detail="Etapa já concluída")
    empreitada = session.get(Empreitada, empreitada_id)
    pessoa = session.get(Pessoa, empreitada.pessoa_id)

    hoje = date.today()
    proximo = _competencia_seguinte(hoje.strftime("%Y-%m"))
    ano, mes = (int(x) for x in proximo.split("-"))
    data_analise = date(ano, mes, 1)
    numero_lancamento = _proximo_numero_lancamento(session, ano)

    etapa.concluida = True
    etapa.data_conclusao = hoje
    etapa.numero_lancamento_gerado = numero_lancamento
    session.add(etapa)
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Empreita — {pessoa.nome} ({empreitada.descricao}) — etapa: {etapa.nome}",
        data_vencimento=data_analise,
        data_competencia=data_analise,
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Empreitada",
        centro_custo=empreitada.centro_custo,
        valor_total=etapa.valor,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        fazenda_id=fazenda_id,
    ))
    # Autoflush reflete etapa.concluida=True antes desta consulta — se não
    # sobrar nenhuma etapa pendente, a empreitada como um todo está concluída.
    etapas_pendentes = session.exec(
        select(EmpreitadaEtapa).where(EmpreitadaEtapa.empreitada_id == empreitada_id, EmpreitadaEtapa.concluida == False)  # noqa: E712
    ).all()
    if not etapas_pendentes:
        empreitada.status = "concluida"
        session.add(empreitada)
    session.commit()
    return _serializar_empreitada(session, empreitada)


@router.delete("/empreitadas/parcelas/{parcela_id}")
def excluir_parcela_empreitada(parcela_id: int, session: Session = Depends(get_session)) -> dict:
    parcela = session.get(EmpreitadaParcela, parcela_id)
    if not parcela:
        raise HTTPException(status_code=404, detail="Parcela de empreitada não encontrada")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado]):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser excluída aqui — exclua em Lançamentos > Excluir lançamento.")
    if parcela.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == parcela.numero_lancamento_gerado)
        ).first()
        if conta:
            session.delete(conta)
    session.delete(parcela)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Contrato — valor total pago por frequência fixa (parcelas editáveis, mesmo
# padrão do Financeiro) ou, sem frequência definida, com lembrete mensal na
# Agenda (todo dia 1º) para pagar ou definir uma nova data.
# ---------------------------------------------------------------------------
FORMAS_PAGAMENTO_CONTRATO = ["mensal", "quinzenal", "semanal"]


class ContratoParcelaIn(BaseModel):
    data_vencimento: date
    valor: float


class ContratoIn(BaseModel):
    pessoa_id: int
    descricao: str
    valor_total: float
    forma_pagamento: str | None = None  # None => sem frequência definida
    observacao: str | None = None
    # Preenchido quando forma_pagamento está definida — já calculado (a partir
    # de data de término estimada, número de parcelas ou lançamento livre) e
    # editável no frontend, mesmo padrão do parcelamento do Financeiro.
    parcelas: list[ContratoParcelaIn] = []
    centro_custo: str = "Pecuária Leiteira"


def _serializar_contrato(session: Session, c: Contrato) -> dict:
    parcelas = session.exec(
        select(ContratoParcela).where(ContratoParcela.contrato_id == c.id).order_by(ContratoParcela.data_vencimento)
    ).all()
    numeros = [p.numero_lancamento_gerado for p in parcelas if p.numero_lancamento_gerado]
    pagos = set()
    if numeros:
        contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all()
        pagos = {conta.numero_lancamento for conta in contas if conta.valor_pago is not None}
    return {
        **c.model_dump(),
        "parcelas": [
            {**p.model_dump(), "status": "pago" if p.numero_lancamento_gerado in pagos else "pendente"} for p in parcelas
        ],
        "vales": _listar_vales_avulsos(session, "contrato", c.id),
    }


@router.get("/contratos")
def listar_contratos(session: Session = Depends(get_session)) -> list[dict]:
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    contratos = session.exec(select(Contrato).order_by(Contrato.criado_em.desc())).all()
    return [{**_serializar_contrato(session, c), "pessoa_nome": pessoas.get(c.pessoa_id, "—")} for c in contratos]


@router.post("/contratos")
def criar_contrato(
    dados: ContratoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.forma_pagamento is not None and dados.forma_pagamento not in FORMAS_PAGAMENTO_CONTRATO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.forma_pagamento and not dados.parcelas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma parcela para a frequência escolhida")

    contrato = Contrato(
        pessoa_id=dados.pessoa_id, descricao=dados.descricao, valor_total=dados.valor_total,
        forma_pagamento=dados.forma_pagamento, observacao=dados.observacao, usuario_id=user.id,
        centro_custo=dados.centro_custo,
    )
    session.add(contrato)
    session.commit()
    session.refresh(contrato)

    if dados.forma_pagamento:
        for parcela in dados.parcelas:
            numero_lancamento = _proximo_numero_lancamento(session, parcela.data_vencimento.year)
            session.add(ContratoParcela(
                contrato_id=contrato.id, data_vencimento=parcela.data_vencimento, valor=parcela.valor,
                numero_lancamento_gerado=numero_lancamento,
            ))
            session.add(ContaGerencial(
                numero_lancamento=numero_lancamento,
                descricao=f"Contrato — {pessoa.nome} ({dados.descricao})",
                data_vencimento=parcela.data_vencimento,
                data_competencia=parcela.data_vencimento.replace(day=1),
                fornecedor_cliente=pessoa.nome,
                tipo_documento="Contrato",
                centro_custo=dados.centro_custo,
                valor_total=parcela.valor,
                parcela_num=1, parcela_total=1,
                tipo="despesa", origem="auto",
                fazenda_id=fazenda_id,
            ))
    else:
        # Sem frequência definida: lembrete mensal na Agenda (todo dia 1º) para
        # pagar ou definir uma nova data — reaproveita o motor de recorrência
        # já existente da Agenda (_gerar_agenda_recorrente, chamado a cada GET
        # /agenda/), sem precisar de nenhuma lógica de recorrência nova aqui.
        proximo = _competencia_seguinte(date.today().strftime("%Y-%m"))
        ano, mes = (int(x) for x in proximo.split("-"))
        lembrete = AgendaManual(
            data_evento=date(ano, mes, 1),
            descricao=f"Contrato sem frequência definida — {pessoa.nome} ({dados.descricao}): pagar ou definir nova data",
            categoria="Gestão/Financeiro",
            tipo_evento="Outro",
            recorrente=True,
            intervalo_meses=1,
            usuario_id=user.id,
        )
        session.add(lembrete)
        session.commit()
        session.refresh(lembrete)
        contrato.origem_lembrete_agenda_id = lembrete.id
        session.add(contrato)
    session.commit()
    return _serializar_contrato(session, contrato)


@router.put("/contratos/{contrato_id}/encerrar")
def encerrar_contrato(contrato_id: int, session: Session = Depends(get_session)) -> dict:
    contrato = session.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    contrato.status = "encerrado"
    session.add(contrato)
    if contrato.origem_lembrete_agenda_id:
        modelo = session.get(AgendaManual, contrato.origem_lembrete_agenda_id)
        if modelo:
            modelo.recorrente = False
            session.add(modelo)
    session.commit()
    return _serializar_contrato(session, contrato)


@router.delete("/contratos/parcelas/{parcela_id}")
def excluir_parcela_contrato(parcela_id: int, session: Session = Depends(get_session)) -> dict:
    parcela = session.get(ContratoParcela, parcela_id)
    if not parcela:
        raise HTTPException(status_code=404, detail="Parcela de contrato não encontrada")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado]):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser excluída aqui — exclua em Lançamentos > Excluir lançamento.")
    if parcela.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == parcela.numero_lancamento_gerado)
        ).first()
        if conta:
            session.delete(conta)
    session.delete(parcela)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Diária — valor da diária + data de início; o sistema conta diariamente até
# hoje e mantém o saldo devedor a partir dos pagamentos registrados.
# ---------------------------------------------------------------------------
class DiariaIn(BaseModel):
    pessoa_id: int
    valor_diaria: float
    data_inicio: date
    observacao: str | None = None
    centro_custo: str = "Pecuária Leiteira"
    conta_dia_a_dia: bool = True
    # None = herda o padrão de ParametroDiariaPadrao no momento do cadastro.
    auditar_periodicamente: bool | None = None
    frequencia_auditoria: str | None = None
    dia_semana_auditoria: int | None = None
    intervalo_dias_auditoria: int | None = None


class DiariaPagamentoIn(BaseModel):
    data_pagamento: date
    valor: float
    observacao: str | None = None


def _dias_confirmados_diaria(session: Session, diaria_id: int) -> tuple[int, date | None]:
    """Soma os dias efetivamente confirmados nas auditorias JÁ RESPONDIDAS
    desta diária, e devolve também até que data essa contagem cobre
    (`periodo_fim` da última auditoria respondida — os dias corridos depois
    dela ainda não foram auditados, então continuam contados no "olho" pela
    regra antiga, dia a dia, até a próxima resposta)."""
    respondidas = session.exec(
        select(DiariaAuditoria)
        .where(DiariaAuditoria.diaria_id == diaria_id, DiariaAuditoria.dias_trabalhados.is_not(None))
        .order_by(DiariaAuditoria.periodo_fim)
    ).all()
    if not respondidas:
        return 0, None
    return sum(a.dias_trabalhados for a in respondidas), respondidas[-1].periodo_fim


def _resumo_diaria(session: Session, d: Diaria, pessoa_nome: str) -> dict:
    hoje = date.today()
    dias_confirmados, cobertura_ate = _dias_confirmados_diaria(session, d.id)
    if cobertura_ate is not None:
        # Períodos já auditados usam o valor confirmado (pode ser < dias
        # corridos, se o diarista faltou); o restante (da última auditoria
        # até hoje, ainda sem resposta) continua contado dia a dia — mesma
        # regra de sempre, só que sem sobrescrever o que já foi confirmado.
        dias_desde_cobertura = max((hoje - cobertura_ate).days, 0)
        numero_diarias = dias_confirmados + dias_desde_cobertura
    else:
        numero_diarias = max((hoje - d.data_inicio).days + 1, 0)
    total_ate_hoje = round(numero_diarias * d.valor_diaria, 2)
    pagamentos = sorted(
        session.exec(select(DiariaPagamento).where(DiariaPagamento.diaria_id == d.id)).all(),
        key=lambda p: p.data_pagamento,
    )
    valor_pago = round(sum(p.valor for p in pagamentos), 2)
    vales = _listar_vales_avulsos(session, "diaria", d.id)
    valor_vale = round(sum(v["valor"] for v in vales), 2)
    auditorias_pendentes = session.exec(
        select(DiariaAuditoria)
        .where(DiariaAuditoria.diaria_id == d.id, DiariaAuditoria.dias_trabalhados.is_(None))
        .order_by(DiariaAuditoria.periodo_fim)
    ).all()
    return {
        **d.model_dump(),
        "pessoa_nome": pessoa_nome,
        "numero_diarias": numero_diarias,
        "total_ate_hoje": total_ate_hoje,
        "valor_pago": valor_pago,
        "valor_vale": valor_vale,
        "saldo_devedor": round(total_ate_hoje - valor_pago - valor_vale, 2),
        "pagamentos": [p.model_dump() for p in pagamentos],
        "vales": vales,
        "auditorias_pendentes": [a.model_dump() for a in auditorias_pendentes],
    }


@router.get("/diarias")
def listar_diarias(session: Session = Depends(get_session)) -> list[dict]:
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    diarias = session.exec(select(Diaria).order_by(Diaria.criado_em.desc())).all()
    return [_resumo_diaria(session, d, pessoas.get(d.pessoa_id, "—")) for d in diarias]


def _parametro_diaria_padrao(session: Session) -> ParametroDiariaPadrao:
    padrao = session.get(ParametroDiariaPadrao, 1)
    if not padrao:
        padrao = ParametroDiariaPadrao(id=1)
        session.add(padrao)
        session.commit()
        session.refresh(padrao)
    return padrao


@router.get("/diarias/parametro-padrao")
def obter_parametro_diaria_padrao(session: Session = Depends(get_session)) -> dict:
    return _parametro_diaria_padrao(session).model_dump()


class ParametroDiariaPadraoIn(BaseModel):
    auditar_periodicamente: bool
    frequencia_auditoria: str  # semanal | intervalo_dias | mensal
    dia_semana_auditoria: int = 0
    intervalo_dias_auditoria: int = 7


@router.put("/diarias/parametro-padrao")
def salvar_parametro_diaria_padrao(
    dados: ParametroDiariaPadraoIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)
) -> dict:
    if dados.frequencia_auditoria not in ("semanal", "intervalo_dias", "mensal"):
        raise HTTPException(status_code=400, detail="Frequência inválida")
    padrao = _parametro_diaria_padrao(session)
    padrao.auditar_periodicamente = dados.auditar_periodicamente
    padrao.frequencia_auditoria = dados.frequencia_auditoria
    padrao.dia_semana_auditoria = dados.dia_semana_auditoria
    padrao.intervalo_dias_auditoria = dados.intervalo_dias_auditoria
    padrao.atualizado_em = datetime.utcnow()
    session.add(padrao)
    session.commit()
    session.refresh(padrao)
    return padrao.model_dump()


@router.post("/diarias")
def criar_diaria(dados: DiariaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.valor_diaria <= 0:
        raise HTTPException(status_code=400, detail="Valor da diária deve ser positivo")
    # Campos de auditoria não informados herdam o padrão configurado em
    # Configurações > Parâmetros — cada diária pode depois editar a própria
    # cadência sem afetar as demais.
    padrao = _parametro_diaria_padrao(session)
    auditar = dados.auditar_periodicamente if dados.auditar_periodicamente is not None else padrao.auditar_periodicamente
    frequencia = dados.frequencia_auditoria or padrao.frequencia_auditoria
    dia_semana = dados.dia_semana_auditoria if dados.dia_semana_auditoria is not None else padrao.dia_semana_auditoria
    intervalo = dados.intervalo_dias_auditoria if dados.intervalo_dias_auditoria is not None else padrao.intervalo_dias_auditoria
    diaria = Diaria(
        pessoa_id=dados.pessoa_id, valor_diaria=dados.valor_diaria, data_inicio=dados.data_inicio,
        observacao=dados.observacao, usuario_id=user.id, centro_custo=dados.centro_custo,
        conta_dia_a_dia=dados.conta_dia_a_dia, auditar_periodicamente=auditar,
        frequencia_auditoria=frequencia, dia_semana_auditoria=dia_semana, intervalo_dias_auditoria=intervalo,
    )
    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    return _resumo_diaria(session, diaria, pessoa.nome)


class DiariaAuditoriaResponderIn(BaseModel):
    dias_trabalhados: int


@router.put("/diarias/auditorias/{auditoria_id}")
def responder_auditoria_diaria(
    auditoria_id: int, dados: DiariaAuditoriaResponderIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)
) -> dict:
    auditoria = session.get(DiariaAuditoria, auditoria_id)
    if not auditoria:
        raise HTTPException(status_code=404, detail="Auditoria não encontrada")
    dias_no_periodo = (auditoria.periodo_fim - auditoria.periodo_inicio).days + 1
    if not (0 <= dados.dias_trabalhados <= dias_no_periodo):
        raise HTTPException(status_code=400, detail=f"Dias trabalhados deve estar entre 0 e {dias_no_periodo}")
    auditoria.dias_trabalhados = dados.dias_trabalhados
    auditoria.confirmado_em = datetime.utcnow()
    auditoria.usuario_id = user.id
    session.add(auditoria)
    session.commit()
    diaria = session.get(Diaria, auditoria.diaria_id)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    return _resumo_diaria(session, diaria, pessoa.nome)


@router.post("/diarias/{diaria_id}/pagamentos")
def registrar_pagamento_diaria(
    diaria_id: int, dados: DiariaPagamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = session.get(Diaria, diaria_id)
    if not diaria:
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do pagamento deve ser positivo")
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    numero_lancamento = _proximo_numero_lancamento(session, dados.data_pagamento.year)
    session.add(DiariaPagamento(
        diaria_id=diaria_id, data_pagamento=dados.data_pagamento, valor=dados.valor,
        observacao=dados.observacao, numero_lancamento_gerado=numero_lancamento,
    ))
    # Pagamento de diária já nasce quitado — reflete direto em Contas Pagas/relatórios.
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Diária — {pessoa.nome}",
        data_vencimento=dados.data_pagamento,
        data_competencia=dados.data_pagamento.replace(day=1),
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Diária",
        centro_custo=diaria.centro_custo,
        valor_total=dados.valor,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        data_pagamento=dados.data_pagamento,
        valor_pago=dados.valor,
        fazenda_id=fazenda_id,
    ))
    session.commit()
    return _resumo_diaria(session, diaria, pessoa.nome)


# ---------------------------------------------------------------------------
# Vale (adiantamento) para Empreitada/Contrato/Diária — mesma ideia do Vale de
# funcionário, mas sem competência/folha mensal para descontar: o valor é
# abatido direto da(s) próxima(s) parcela(s)/etapa(s) pendente(s) (Empreitada/
# Contrato) ou do saldo devedor acumulado (Diária).
# ---------------------------------------------------------------------------
ORIGENS_VALE_AVULSO = ["empreitada", "contrato", "diaria"]
FORMAS_PAGAMENTO_VALE_AVULSO = ["dinheiro", "pix", "transferencia", "desconto_proximo_pagamento"]


class ValeAvulsoIn(BaseModel):
    origem_tipo: str  # empreitada | contrato | diaria
    origem_id: int
    valor: float
    forma_pagamento: str  # dinheiro | pix | transferencia | desconto_proximo_pagamento
    data_pagamento: date
    observacao: str | None = None


def _listar_vales_avulsos(session: Session, origem_tipo: str, origem_id: int) -> list[dict]:
    vales = session.exec(
        select(ValeAvulso)
        .where(ValeAvulso.origem_tipo == origem_tipo, ValeAvulso.origem_id == origem_id)
        .order_by(ValeAvulso.data_pagamento)
    ).all()
    return [v.model_dump() for v in vales]


def _numeros_pagos(session: Session, numeros: list[str]) -> set[str]:
    if not numeros:
        return set()
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all()
    return {c.numero_lancamento for c in contas if c.valor_pago is not None}


def _aplicar_vale_avulso(session: Session, origem_tipo: str, origem_id: int, valor: float) -> None:
    """
    Abate `valor` da(s) próxima(s) parcela(s)/etapa(s) PENDENTE(S), na ordem em
    que vencem — mesmo efeito do vale de funcionário (reduzir o valor líquido
    a receber), só que aqui não há um documento mensal (folha) para descontar,
    então o alvo é o próprio saldo em aberto de cada entidade:
    - Empreitada: reduz as próximas EmpreitadaParcela (ou EmpreitadaEtapa, se
      "por_etapa") ainda não pagas, e sincroniza a ContaGerencial vinculada
      (só quando ela já existe e ainda não foi paga).
    - Contrato: mesma lógica com ContratoParcela.
    - Diária: não há parcela agendada (o pagamento é sob demanda) — o valor só
      soma ao "saldo abatido", já calculado em `_resumo_diaria`.
    """
    restante = round(valor, 2)
    if restante <= 0 or origem_tipo == "diaria":
        return

    if origem_tipo == "empreitada":
        empreitada = session.get(Empreitada, origem_id)
        if empreitada and empreitada.tipo_pagamento == "por_etapa":
            itens = session.exec(
                select(EmpreitadaEtapa)
                .where(EmpreitadaEtapa.empreitada_id == origem_id, EmpreitadaEtapa.concluida == False)  # noqa: E712
                .order_by(EmpreitadaEtapa.ordem, EmpreitadaEtapa.id)
            ).all()
        else:
            todas = session.exec(
                select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == origem_id).order_by(EmpreitadaParcela.data_vencimento)
            ).all()
            pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in todas if p.numero_lancamento_gerado])
            itens = [p for p in todas if p.numero_lancamento_gerado not in pagos]
    elif origem_tipo == "contrato":
        todas = session.exec(
            select(ContratoParcela).where(ContratoParcela.contrato_id == origem_id).order_by(ContratoParcela.data_vencimento)
        ).all()
        pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in todas if p.numero_lancamento_gerado])
        itens = [p for p in todas if p.numero_lancamento_gerado not in pagos]
    else:
        return

    for item in itens:
        if restante <= 0:
            break
        abatido = min(item.valor, restante)
        item.valor = round(item.valor - abatido, 2)
        restante = round(restante - abatido, 2)
        session.add(item)
        numero = getattr(item, "numero_lancamento_gerado", None)
        if numero:
            conta = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()
            if conta and conta.valor_pago is None:
                conta.valor_total = item.valor
                session.add(conta)


@router.get("/vale-avulso")
def listar_vales_avulsos_endpoint(origem_tipo: str, origem_id: int, session: Session = Depends(get_session)) -> list[dict]:
    if origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    return _listar_vales_avulsos(session, origem_tipo, origem_id)


@router.post("/vale-avulso")
def criar_vale_avulso(dados: ValeAvulsoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    """
    Lança um vale (adiantamento) para Empreitada/Contrato/Diária — análogo ao
    Vale de funcionário, permitindo controlar o que já foi adiantado a
    empreiteiros/contratados/diaristas antes do pagamento final.
    """
    if dados.origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")

    if dados.origem_tipo == "empreitada":
        origem = session.get(Empreitada, dados.origem_id)
    elif dados.origem_tipo == "contrato":
        origem = session.get(Contrato, dados.origem_id)
    else:
        origem = session.get(Diaria, dados.origem_id)
    if not origem:
        raise HTTPException(status_code=404, detail=f"{dados.origem_tipo.capitalize()} não encontrado(a)")

    vale = ValeAvulso(
        origem_tipo=dados.origem_tipo, origem_id=dados.origem_id, pessoa_id=origem.pessoa_id,
        valor=dados.valor, forma_pagamento=dados.forma_pagamento, data_pagamento=dados.data_pagamento,
        observacao=dados.observacao, usuario_id=user.id,
    )
    session.add(vale)
    session.commit()

    _aplicar_vale_avulso(session, dados.origem_tipo, dados.origem_id, dados.valor)
    session.commit()

    if dados.origem_tipo == "empreitada":
        resultado = _serializar_empreitada(session, origem)
    elif dados.origem_tipo == "contrato":
        resultado = _serializar_contrato(session, origem)
    else:
        pessoa = session.get(Pessoa, origem.pessoa_id)
        resultado = _resumo_diaria(session, origem, pessoa.nome if pessoa else "—")
    return {"vale": vale.model_dump(), "origem": resultado}




