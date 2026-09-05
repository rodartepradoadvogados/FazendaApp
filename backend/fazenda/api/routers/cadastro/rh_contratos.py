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

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, exigir_admin, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, ContaCorrente, ContaGerencial, Contrato, ContratoParcela, DecimoTerceiro, Diaria, DiariaAuditoria,
    DiariaDia, DiariaPagamento, Empreitada, EmpreitadaEtapa, EmpreitadaParcela, FeriasFuncionario, ParametroDiariaPadrao,
    Pessoa, Usuario, ValeAvulso, ValeAvulsoAbatimento,
)
from fazenda.api.routers.financeiro import _proximo_numero_lancamento, rotulo_conta_corrente
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.vale_item import limpar_vinculo_de_itens, origens_lancamento_por_vale

from .rh_folha import _competencia_seguinte, _resolver_conta_corrente, listar_folha_pagamento

router = APIRouter()

@router.get("/folha-pagamento-unificada")
def listar_folha_pagamento_unificada(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Visão consolidada de TODOS os lançamentos de folha — funcionário, empreita,
    contrato, diária e férias/13º salário — num único ledger ordenável/
    filtrável por vencimento, priorizando pendências (destacando as vencidas).
    `origem_tipo` (=`tipo`) + `origem_id` apontam para o registro de origem só
    para permitir excluir lançamentos ainda pendentes; a edição continua nas
    telas específicas.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    linhas: list[dict] = []

    for r in listar_folha_pagamento(session, fazenda_id=fazenda_id):
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

    query_empreitadas = select(Empreitada)
    query_parcelas_empreita = select(EmpreitadaParcela)
    query_etapas_empreita = select(EmpreitadaEtapa).where(EmpreitadaEtapa.concluida == True)  # noqa: E712
    if fazenda_id is not None:
        query_empreitadas = query_empreitadas.where(Empreitada.fazenda_id == fazenda_id)
        query_parcelas_empreita = query_parcelas_empreita.where(EmpreitadaParcela.fazenda_id == fazenda_id)
        query_etapas_empreita = query_etapas_empreita.where(EmpreitadaEtapa.fazenda_id == fazenda_id)
    empreitadas = {e.id: e for e in session.exec(query_empreitadas).all()}
    parcelas_empreita = session.exec(query_parcelas_empreita).all()
    etapas_empreita = session.exec(query_etapas_empreita).all()
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

    query_contratos = select(Contrato)
    query_parcelas_contrato = select(ContratoParcela)
    if fazenda_id is not None:
        query_contratos = query_contratos.where(Contrato.fazenda_id == fazenda_id)
        query_parcelas_contrato = query_parcelas_contrato.where(ContratoParcela.fazenda_id == fazenda_id)
    contratos = {c.id: c for c in session.exec(query_contratos).all()}
    parcelas_contrato = session.exec(query_parcelas_contrato).all()
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

    query_diarias = select(Diaria)
    query_pagamentos_diaria = select(DiariaPagamento)
    if fazenda_id is not None:
        query_diarias = query_diarias.where(Diaria.fazenda_id == fazenda_id)
        query_pagamentos_diaria = query_pagamentos_diaria.where(DiariaPagamento.fazenda_id == fazenda_id)
    diarias = {d.id: d for d in session.exec(query_diarias).all()}
    for pg in session.exec(query_pagamentos_diaria).all():
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

    # Férias e 13º salário — mesmo padrão de Empreita/Contrato: o vencimento e
    # o status de pagamento vêm da ContaGerencial gerada junto (numero_
    # lancamento_gerado), já que os dois modelos não têm data_vencimento
    # própria. Faltavam neste ledger unificado (item aprovado da proposta de
    # Folha de Pagamento) — o filtro "Todos"/"Férias / 13º" agora inclui os dois.
    query_ferias = select(FeriasFuncionario)
    query_decimo = select(DecimoTerceiro)
    if fazenda_id is not None:
        query_ferias = query_ferias.where(FeriasFuncionario.fazenda_id == fazenda_id)
        query_decimo = query_decimo.where(DecimoTerceiro.fazenda_id == fazenda_id)
    ferias = session.exec(query_ferias).all()
    decimos = session.exec(query_decimo).all()
    numeros_ferias_decimo = [f.numero_lancamento_gerado for f in ferias if f.numero_lancamento_gerado] + [
        d.numero_lancamento_gerado for d in decimos if d.numero_lancamento_gerado
    ]
    contas_ferias_decimo = {
        c.numero_lancamento: c
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros_ferias_decimo))).all()
    } if numeros_ferias_decimo else {}
    for f in ferias:
        conta = contas_ferias_decimo.get(f.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "ferias_decimo", "origem_id": f.id, "origem_subtipo": "ferias",
            "pessoa_id": f.pessoa_id, "pessoa_nome": pessoas.get(f.pessoa_id, "—"),
            "descricao": f"Férias — {f.data_inicio_gozo.isoformat()} a {f.data_fim_gozo.isoformat()}",
            "valor": f.valor_total,
            "data_vencimento": conta.data_vencimento if conta else None,
            "data_pagamento": conta.data_pagamento if conta else f.data_pagamento,
            "status": "pago" if pago else "pendente",
            "pode_excluir": not pago,
        })
    for d in decimos:
        conta = contas_ferias_decimo.get(d.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "ferias_decimo", "origem_id": d.id, "origem_subtipo": "decimo_terceiro",
            "pessoa_id": d.pessoa_id, "pessoa_nome": pessoas.get(d.pessoa_id, "—"),
            "descricao": f"13º salário — {d.ano} ({d.parcela})",
            "valor": d.valor_liquido,
            "data_vencimento": conta.data_vencimento if conta else None,
            "data_pagamento": conta.data_pagamento if conta else d.data_pagamento,
            "status": "pago" if pago else "pendente",
            "pode_excluir": not pago,
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
def listar_empreitadas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(Empreitada)
    if fazenda_id is not None:
        query = query.where(Empreitada.fazenda_id == fazenda_id)
    empreitadas = session.exec(query.order_by(Empreitada.criado_em.desc())).all()
    return [{**_serializar_empreitada(session, e), "pessoa_nome": pessoas.get(e.pessoa_id, "—")} for e in empreitadas]


@router.post("/empreitadas")
def criar_empreitada(
    dados: EmpreitadaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
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
        centro_custo=dados.centro_custo, fazenda_id=fazenda_id,
    )
    session.add(empreitada)
    session.commit()
    session.refresh(empreitada)

    if dados.tipo_pagamento in FORMAS_PAGAMENTO_PARCELA:
        for parcela in dados.parcelas:
            numero_lancamento = _proximo_numero_lancamento(session, parcela.data_vencimento.year)
            session.add(EmpreitadaParcela(
                empreitada_id=empreitada.id, data_vencimento=parcela.data_vencimento, valor=parcela.valor,
                numero_lancamento_gerado=numero_lancamento, fazenda_id=fazenda_id,
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
            session.add(EmpreitadaEtapa(
                empreitada_id=empreitada.id, nome=etapa.nome, valor=etapa.valor, ordem=i, fazenda_id=fazenda_id,
            ))
    session.commit()
    return _serializar_empreitada(session, empreitada)


@router.put("/empreitadas/{empreitada_id}/etapas/{etapa_id}/concluir")
def concluir_etapa_empreitada(
    empreitada_id: int, etapa_id: int, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Marca uma etapa como concluída e lança a conta a pagar correspondente no
    dia 1º do mês seguinte — cai automaticamente na Agenda (Gestão/Financeiro,
    a partir da própria data_vencimento da conta) e em Contas a Pagar, para
    análise/pagamento.
    """
    etapa = session.get(EmpreitadaEtapa, etapa_id)
    if not etapa or etapa.empreitada_id != empreitada_id or (etapa.fazenda_id != fazenda_id):
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
def excluir_parcela_empreitada(
    parcela_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(EmpreitadaParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
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


class ParcelaEditIn(BaseModel):
    data_vencimento: date
    valor: float


def _sincronizar_conta_parcela(session: Session, numero_lancamento: str | None, data_vencimento: date, valor: float) -> None:
    """Mantém o lançamento gerado (ContaGerencial) alinhado após editar/
    redistribuir uma parcela de Empreitada/Contrato — só toca contas ainda
    não pagas (parcela paga é bloqueada antes de chegar aqui)."""
    if not numero_lancamento:
        return
    conta = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
    if conta and conta.valor_pago is None:
        conta.data_vencimento = data_vencimento
        conta.data_competencia = data_vencimento.replace(day=1)
        conta.valor_total = valor
        session.add(conta)


def _redistribuir_parcelas_pendentes(session: Session, pendentes: list) -> None:
    """Redivide igualmente o total das parcelas pendentes informadas (mantendo
    as datas de vencimento de cada uma), ajustando o arredondamento na
    última para o somatório bater exatamente com o total original."""
    if len(pendentes) < 2:
        raise HTTPException(status_code=400, detail="É preciso ao menos 2 parcelas pendentes para redistribuir.")
    total = round(sum(p.valor for p in pendentes), 2)
    valor_base = round(total / len(pendentes), 2)
    restante = total
    for i, p in enumerate(pendentes):
        valor = valor_base if i < len(pendentes) - 1 else round(restante, 2)
        restante = round(restante - valor, 2)
        p.valor = valor
        session.add(p)
        _sincronizar_conta_parcela(session, p.numero_lancamento_gerado, p.data_vencimento, valor)


@router.put("/empreitadas/parcelas/{parcela_id}")
def atualizar_parcela_empreitada(
    parcela_id: int, dados: ParcelaEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(EmpreitadaParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Parcela de empreitada não encontrada")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor da parcela deve ser positivo")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado]):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser editada aqui — edite em Lançamentos > Financeiro.")
    parcela.data_vencimento = dados.data_vencimento
    parcela.valor = dados.valor
    session.add(parcela)
    _sincronizar_conta_parcela(session, parcela.numero_lancamento_gerado, dados.data_vencimento, dados.valor)
    session.commit()
    empreitada = session.get(Empreitada, parcela.empreitada_id)
    return _serializar_empreitada(session, empreitada)


@router.post("/empreitadas/{empreitada_id}/parcelas/redistribuir")
def redistribuir_parcelas_empreitada(
    empreitada_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Redivide igualmente o valor total ainda pendente entre as parcelas
    pendentes da empreitada (ex.: após um vale abater desproporcionalmente
    uma única parcela, redistribui o saldo entre as próximas)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    empreitada = session.get(Empreitada, empreitada_id)
    if not empreitada or (empreitada.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Empreitada não encontrada")
    parcelas = session.exec(
        select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada_id).order_by(EmpreitadaParcela.data_vencimento)
    ).all()
    pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in parcelas if p.numero_lancamento_gerado])
    pendentes = [p for p in parcelas if p.numero_lancamento_gerado not in pagos]
    _redistribuir_parcelas_pendentes(session, pendentes)
    session.commit()
    return _serializar_empreitada(session, empreitada)


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
def listar_contratos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(Contrato)
    if fazenda_id is not None:
        query = query.where(Contrato.fazenda_id == fazenda_id)
    contratos = session.exec(query.order_by(Contrato.criado_em.desc())).all()
    return [{**_serializar_contrato(session, c), "pessoa_nome": pessoas.get(c.pessoa_id, "—")} for c in contratos]


@router.post("/contratos")
def criar_contrato(
    dados: ContratoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.forma_pagamento is not None and dados.forma_pagamento not in FORMAS_PAGAMENTO_CONTRATO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.forma_pagamento and not dados.parcelas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma parcela para a frequência escolhida")

    contrato = Contrato(
        pessoa_id=dados.pessoa_id, descricao=dados.descricao, valor_total=dados.valor_total,
        forma_pagamento=dados.forma_pagamento, observacao=dados.observacao, usuario_id=user.id,
        centro_custo=dados.centro_custo, fazenda_id=fazenda_id,
    )
    session.add(contrato)
    session.commit()
    session.refresh(contrato)

    if dados.forma_pagamento:
        for parcela in dados.parcelas:
            numero_lancamento = _proximo_numero_lancamento(session, parcela.data_vencimento.year)
            session.add(ContratoParcela(
                contrato_id=contrato.id, data_vencimento=parcela.data_vencimento, valor=parcela.valor,
                numero_lancamento_gerado=numero_lancamento, fazenda_id=fazenda_id,
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
def encerrar_contrato(
    contrato_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    contrato = session.get(Contrato, contrato_id)
    if not contrato or (contrato.fazenda_id != fazenda_id):
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
def excluir_parcela_contrato(
    parcela_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(ContratoParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
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


@router.put("/contratos/parcelas/{parcela_id}")
def atualizar_parcela_contrato(
    parcela_id: int, dados: ParcelaEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(ContratoParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Parcela de contrato não encontrada")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor da parcela deve ser positivo")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado]):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser editada aqui — edite em Lançamentos > Financeiro.")
    parcela.data_vencimento = dados.data_vencimento
    parcela.valor = dados.valor
    session.add(parcela)
    _sincronizar_conta_parcela(session, parcela.numero_lancamento_gerado, dados.data_vencimento, dados.valor)
    session.commit()
    contrato = session.get(Contrato, parcela.contrato_id)
    return _serializar_contrato(session, contrato)


@router.post("/contratos/{contrato_id}/parcelas/redistribuir")
def redistribuir_parcelas_contrato(
    contrato_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    contrato = session.get(Contrato, contrato_id)
    if not contrato or (contrato.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    parcelas = session.exec(
        select(ContratoParcela).where(ContratoParcela.contrato_id == contrato_id).order_by(ContratoParcela.data_vencimento)
    ).all()
    pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in parcelas if p.numero_lancamento_gerado])
    pendentes = [p for p in parcelas if p.numero_lancamento_gerado not in pagos]
    _redistribuir_parcelas_pendentes(session, pendentes)
    session.commit()
    return _serializar_contrato(session, contrato)


# ---------------------------------------------------------------------------
# Diária — valor da diária + data de início; o sistema conta diariamente até
# hoje e mantém o saldo devedor a partir dos pagamentos registrados.
# ---------------------------------------------------------------------------
class DiariaIn(BaseModel):
    pessoa_id: int
    valor_diaria: float
    data_inicio: date
    data_fim: date | None = None
    observacao: str | None = None
    centro_custo: str = "Pecuária Leiteira"
    conta_dia_a_dia: bool = True
    # None = herda o padrão de ParametroDiariaPadrao no momento do cadastro.
    auditar_periodicamente: bool | None = None
    frequencia_auditoria: str | None = None
    dia_semana_auditoria: int | None = None
    intervalo_dias_auditoria: int | None = None


class DiariaEditIn(BaseModel):
    """Edição via botão no controle — sempre substitui os 3 campos por
    inteiro (envie null para limpar data_fim/ajuste_numero_diarias)."""
    data_inicio: date
    data_fim: date | None = None
    ajuste_numero_diarias: int | None = None


class DiariaPagamentoIn(BaseModel):
    data_pagamento: date
    valor: float
    observacao: str | None = None
    # Conta bancária de onde sai o pagamento — OPCIONAL (ver
    # _resolver_conta_corrente em rh_folha.py).
    conta_corrente_id: int | None = None


def _dias_confirmados_diaria(session: Session, diaria_id: int, ate: date | None = None) -> tuple[int, date | None]:
    """Soma os dias efetivamente confirmados nas auditorias JÁ RESPONDIDAS
    desta diária, e devolve também até que data essa contagem cobre
    (`periodo_fim` da última auditoria respondida — os dias corridos depois
    dela ainda não foram auditados, então continuam contados no "olho" pela
    regra antiga, dia a dia, até a próxima resposta).

    `ate` (opcional): descarta auditorias cujo `periodo_fim` passa de `ate` —
    usado por `_dias_legado_ate` para truncar a contagem legada num corte
    diferente de hoje. `ate=None` mantém o comportamento de sempre
    (considera todas as auditorias respondidas, sem limite)."""
    query = select(DiariaAuditoria).where(
        DiariaAuditoria.diaria_id == diaria_id, DiariaAuditoria.dias_trabalhados.is_not(None)
    )
    if ate is not None:
        query = query.where(DiariaAuditoria.periodo_fim <= ate)
    respondidas = session.exec(query.order_by(DiariaAuditoria.periodo_fim)).all()
    if not respondidas:
        return 0, None
    return sum(a.dias_trabalhados for a in respondidas), respondidas[-1].periodo_fim


def _dias_legado_ate(session: Session, d: Diaria, ate: date) -> int:
    """O mesmo cálculo do bloco legado abaixo (auditorias respondidas +
    ajuste manual + dias corridos), truncado em `ate` em vez de
    `hoje_ou_fim` — usado para somar a parte "antes do corte" de uma diária
    que passou a ser controlada por calendário (ver `controle_por_dia_desde`).
    """
    if ate < d.data_inicio:
        return 0
    dias_confirmados, cobertura_ate = _dias_confirmados_diaria(session, d.id, ate=ate)
    if d.ajuste_numero_diarias is not None and d.ajuste_numero_diarias_em is not None and (
        cobertura_ate is None or d.ajuste_numero_diarias_em >= cobertura_ate
    ):
        base, desde = d.ajuste_numero_diarias, d.ajuste_numero_diarias_em
    else:
        base, desde = dias_confirmados, cobertura_ate
    if desde is not None:
        return max(base + max((ate - desde).days, 0), 0)
    return max((ate - d.data_inicio).days + 1, 0)


def _fracao_dia(linha: DiariaDia) -> float:
    """Fração da diária cumprida num dia com linha de exceção — 1.0 = dia
    cheio (nunca gravado como linha; só chega aqui quem já tem exceção),
    0.5 = meia diária, 0.0 = folga. `fracao=None` (dado histórico, de antes
    desta feature) sempre significava folga, então cai em 0.0."""
    return linha.fracao if linha.fracao is not None else 0.0


def _dias_por_dia(session: Session, d: Diaria, desde: date, ate: date) -> tuple[float, int, int]:
    """(dias_efetivos, dias_folga, dias_meia_diaria) no intervalo [desde,
    ate], pelo modelo esparso de `DiariaDia`: todo dia corrido é trabalhado
    (fração 1.0) por padrão — só os dias com linha de exceção reduzem a
    contagem, por fração de dia perdida (1.0 = folga, 0.5 = meia diária)."""
    corridos = max((ate - desde).days + 1, 0)
    if corridos == 0:
        return 0.0, 0, 0
    excecoes = session.exec(
        select(DiariaDia).where(
            DiariaDia.diaria_id == d.id, DiariaDia.trabalhado == False,  # noqa: E712
            DiariaDia.data >= desde, DiariaDia.data <= ate,
        )
    ).all()
    dias_folga = sum(1 for e in excecoes if _fracao_dia(e) == 0.0)
    dias_meia = sum(1 for e in excecoes if _fracao_dia(e) == 0.5)
    perdido = sum(1 - _fracao_dia(e) for e in excecoes)
    dias_efetivos = max(round(corridos - perdido, 2), 0)
    return dias_efetivos, dias_folga, dias_meia


def _pago_ate_diaria(session: Session, diaria_id: int) -> date | None:
    """Data do pagamento mais recente registrado para esta diária, ou None
    se nunca houve pagamento — usado para travar a edição do calendário num
    período já quitado (ver `salvar_dias_diaria`) sem confirmação explícita."""
    ultimo = session.exec(
        select(DiariaPagamento)
        .where(DiariaPagamento.diaria_id == diaria_id)
        .order_by(DiariaPagamento.data_pagamento.desc())
    ).first()
    return ultimo.data_pagamento if ultimo else None


def _ultima_folga_diaria(session: Session, diaria_id: int, antes_de: date) -> date | None:
    """Data da folga (`DiariaDia.trabalhado=False`) mais recente ANTES de
    `antes_de` (estritamente — não inclui o próprio dia). Usado tanto no
    resumo (`ultima_folga`) quanto no modo `ultimo_periodo` do calendário: ao
    excluir o próprio dia de hoje, uma folga marcada hoje nunca colapsa a
    janela editável a vazio (senão o usuário ficaria travado sem conseguir
    desfazer o próprio toque)."""
    return session.exec(
        select(DiariaDia.data)
        .where(
            DiariaDia.diaria_id == diaria_id, DiariaDia.trabalhado == False,  # noqa: E712
            DiariaDia.data < antes_de,
        )
        .order_by(DiariaDia.data.desc())
    ).first()


def _diaria_ou_404(session: Session, diaria_id: int, fazenda_id: int | None) -> Diaria:
    diaria = session.get(Diaria, diaria_id)
    if not diaria or (diaria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    return diaria


def _resumo_diaria(session: Session, d: Diaria, pessoa_nome: str) -> dict:
    # "Hoje" nunca passa da data de fim — depois que a diária encerra, o
    # contador para de correr (sem isso, teria que ser marcada como
    # "encerrado" manualmente no dia certo pra não seguir somando diárias).
    hoje = date.today()
    hoje_ou_fim = min(hoje, d.data_fim) if d.data_fim else hoje
    if d.controle_por_dia_desde is None:
        # bloco atual, byte-for-byte intocado — os 5 testes existentes de
        # TestDiaria dependem deste caminho continuar idêntico ao de sempre.
        dias_confirmados, cobertura_ate = _dias_confirmados_diaria(session, d.id)
        # O ajuste manual (botão de editar) e a cobertura de auditoria são dois
        # "checkpoints" concorrentes — o mais recente vence como base da
        # contagem, e os dias corridos desde ele são somados por cima.
        if d.ajuste_numero_diarias is not None and d.ajuste_numero_diarias_em is not None and (
            cobertura_ate is None or d.ajuste_numero_diarias_em >= cobertura_ate
        ):
            base, desde = d.ajuste_numero_diarias, d.ajuste_numero_diarias_em
        else:
            base, desde = dias_confirmados, cobertura_ate
        if desde is not None:
            numero_diarias = base + max((hoje_ou_fim - desde).days, 0)
        else:
            numero_diarias = max((hoje_ou_fim - d.data_inicio).days + 1, 0)
        dias_folga = 0
        dias_meia_diaria = 0
    else:
        # Calendário assumiu o controle a partir de `controle_por_dia_desde`
        # — tudo antes do corte continua pela regra legada (auditorias +
        # ajuste manual + dias corridos), tudo a partir dele vem do
        # calendário esparso de DiariaDia. As duas janelas são disjuntas por
        # construção (ver `salvar_dias_diaria`), então soma sem sobreposição.
        corte = d.controle_por_dia_desde
        legado = _dias_legado_ate(session, d, corte - timedelta(days=1))
        por_dia, dias_folga, dias_meia_diaria = _dias_por_dia(session, d, corte, hoje_ou_fim)
        numero_diarias = legado + por_dia
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
        "dias_folga": dias_folga,
        "dias_meia_diaria": dias_meia_diaria,
        "ultima_folga": _ultima_folga_diaria(session, d.id, hoje_ou_fim),
        "pago_ate": pagamentos[-1].data_pagamento if pagamentos else None,
    }


@router.get("/diarias")
def listar_diarias(
    incluir_finalizadas: bool = False,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Por padrão só lista quem ainda está fazendo diárias (status "ativo") —
    ver `incluir_finalizadas` para trazer também as encerradas."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(Diaria)
    if fazenda_id is not None:
        query = query.where(Diaria.fazenda_id == fazenda_id)
    if not incluir_finalizadas:
        query = query.where(Diaria.status != "encerrado")
    diarias = session.exec(query.order_by(Diaria.criado_em.desc())).all()
    return [_resumo_diaria(session, d, pessoas.get(d.pessoa_id, "—")) for d in diarias]


def _parametro_diaria_padrao(session: Session, fazenda_id: int | None = None) -> ParametroDiariaPadrao:
    """Configuração-padrão da fazenda informada — get-or-create por
    `fazenda_id` (era um singleton id=1 global; agora uma linha por
    fazenda, ver fazenda/models/pessoal.py::ParametroDiariaPadrao)."""
    query = select(ParametroDiariaPadrao)
    query = query.where(ParametroDiariaPadrao.fazenda_id == fazenda_id) if fazenda_id is not None else query.where(
        ParametroDiariaPadrao.fazenda_id.is_(None)
    )
    padrao = session.exec(query).first()
    if not padrao:
        padrao = ParametroDiariaPadrao(fazenda_id=fazenda_id)
        session.add(padrao)
        session.commit()
        session.refresh(padrao)
    return padrao


@router.get("/diarias/parametro-padrao")
def obter_parametro_diaria_padrao(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return _parametro_diaria_padrao(session, fazenda_id_seguro(fazenda_id)).model_dump()


class ParametroDiariaPadraoIn(BaseModel):
    auditar_periodicamente: bool
    frequencia_auditoria: str  # semanal | intervalo_dias | mensal
    dia_semana_auditoria: int = 0
    intervalo_dias_auditoria: int = 7


@router.put("/diarias/parametro-padrao")
def salvar_parametro_diaria_padrao(
    dados: ParametroDiariaPadraoIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.frequencia_auditoria not in ("semanal", "intervalo_dias", "mensal"):
        raise HTTPException(status_code=400, detail="Frequência inválida")
    padrao = _parametro_diaria_padrao(session, fazenda_id)
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
def criar_diaria(
    dados: DiariaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.valor_diaria <= 0:
        raise HTTPException(status_code=400, detail="Valor da diária deve ser positivo")
    # Campos de auditoria não informados herdam o padrão configurado em
    # Configurações > Parâmetros — cada diária pode depois editar a própria
    # cadência sem afetar as demais.
    padrao = _parametro_diaria_padrao(session, fazenda_id)
    auditar = dados.auditar_periodicamente if dados.auditar_periodicamente is not None else padrao.auditar_periodicamente
    frequencia = dados.frequencia_auditoria or padrao.frequencia_auditoria
    dia_semana = dados.dia_semana_auditoria if dados.dia_semana_auditoria is not None else padrao.dia_semana_auditoria
    intervalo = dados.intervalo_dias_auditoria if dados.intervalo_dias_auditoria is not None else padrao.intervalo_dias_auditoria
    diaria = Diaria(
        pessoa_id=dados.pessoa_id, valor_diaria=dados.valor_diaria, data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        observacao=dados.observacao, usuario_id=user.id, centro_custo=dados.centro_custo,
        conta_dia_a_dia=dados.conta_dia_a_dia, auditar_periodicamente=auditar,
        frequencia_auditoria=frequencia, dia_semana_auditoria=dia_semana, intervalo_dias_auditoria=intervalo,
        fazenda_id=fazenda_id,
    )
    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    return _resumo_diaria(session, diaria, pessoa.nome)


@router.put("/diarias/{diaria_id}")
def editar_diaria(
    diaria_id: int, dados: DiariaEditIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = session.get(Diaria, diaria_id)
    if not diaria or (diaria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    if dados.ajuste_numero_diarias is not None and dados.ajuste_numero_diarias < 0:
        raise HTTPException(status_code=400, detail="Número de diárias não pode ser negativo")
    diaria.data_inicio = dados.data_inicio
    diaria.data_fim = dados.data_fim
    if dados.ajuste_numero_diarias is not None:
        diaria.ajuste_numero_diarias = dados.ajuste_numero_diarias
        diaria.ajuste_numero_diarias_em = date.today()
    else:
        diaria.ajuste_numero_diarias = None
        diaria.ajuste_numero_diarias_em = None
    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    return _resumo_diaria(session, diaria, pessoa.nome)


@router.put("/diarias/{diaria_id}/encerrar")
def encerrar_diaria(
    diaria_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Marca a diária como finalizada — some do Controle de Diárias por
    padrão (ver `incluir_finalizadas` em `listar_diarias`) e para de gerar
    card "diária de hoje"/auditoria periódica na Agenda (que já filtram por
    `status == "ativo"`, ver routers/agenda.py)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = _diaria_ou_404(session, diaria_id, fazenda_id)
    diaria.status = "encerrado"
    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    return _resumo_diaria(session, diaria, pessoa.nome if pessoa else "—")


class DiariaAuditoriaResponderIn(BaseModel):
    dias_trabalhados: int


@router.put("/diarias/auditorias/{auditoria_id}")
def responder_auditoria_diaria(
    auditoria_id: int, dados: DiariaAuditoriaResponderIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    auditoria = session.get(DiariaAuditoria, auditoria_id)
    if not auditoria or (auditoria.fazenda_id != fazenda_id):
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
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    diaria = session.get(Diaria, diaria_id)
    if not diaria or (diaria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do pagamento deve ser positivo")
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    numero_lancamento = _proximo_numero_lancamento(session, dados.data_pagamento.year)
    session.add(DiariaPagamento(
        diaria_id=diaria_id, data_pagamento=dados.data_pagamento, valor=dados.valor,
        observacao=dados.observacao, numero_lancamento_gerado=numero_lancamento,
        conta_corrente_id=conta_corrente.id if conta_corrente else None, fazenda_id=fazenda_id,
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
        conta_bancaria=rotulo_conta_corrente(conta_corrente) if conta_corrente else None,
        fazenda_id=fazenda_id,
    ))
    session.commit()
    # `numero_lancamento_gerado` no topo (fora do resumo) — é o que a tela
    # usa pra anexar o comprovante logo em seguida via o mecanismo genérico
    # POST /financeiro/lancamentos/{numero_lancamento}/anexos, sem precisar
    # adivinhar qual dos pagamentos da lista é o que acabou de ser criado.
    return {**_resumo_diaria(session, diaria, pessoa.nome), "numero_lancamento_gerado": numero_lancamento}


# ---------------------------------------------------------------------------
# Calendário de dias trabalhados/folga da diária — modelo esparso (só existe
# linha de exceção pro dia que FOGE do padrão trabalhado). Convive com o
# modelo legado de contagem cega: `Diaria.controle_por_dia_desde` marca a
# partir de quando o calendário manda (None = diária nunca tocou o
# calendário, 100% regra antiga). Ver `_resumo_diaria` para o dispatch entre
# as duas regras.
# ---------------------------------------------------------------------------
class DiariaDiasPutIn(BaseModel):
    periodo_inicio: date
    periodo_fim: date
    dias_nao_trabalhados: list[date] = []
    # Meia diária — metade do valor de uma diária cheia (ver _fracao_dia).
    dias_meia_diaria: list[date] = []
    confirmar_periodo_pago: bool = False


@router.get("/diarias/{diaria_id}/dias")
def obter_dias_diaria(
    diaria_id: int, modo: str = "completo", desde: date | None = None, ate: date | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = _diaria_ou_404(session, diaria_id, fazenda_id)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    hoje = date.today()
    hoje_ou_fim = min(hoje, diaria.data_fim) if diaria.data_fim else hoje
    ultima_folga = _ultima_folga_diaria(session, diaria.id, hoje_ou_fim)
    if modo == "ultimo_periodo":
        periodo_inicio = (ultima_folga + timedelta(days=1)) if ultima_folga else diaria.data_inicio
        periodo_fim = hoje_ou_fim
    else:
        modo = "completo"
        periodo_inicio = max(desde or diaria.data_inicio, diaria.data_inicio)
        periodo_fim = min(ate or hoje_ou_fim, hoje_ou_fim)
    pago_ate = _pago_ate_diaria(session, diaria.id)
    fracao_no_periodo = {
        e.data: _fracao_dia(e) for e in session.exec(
            select(DiariaDia).where(
                DiariaDia.diaria_id == diaria.id, DiariaDia.trabalhado == False,  # noqa: E712
                DiariaDia.data >= periodo_inicio, DiariaDia.data <= periodo_fim,
            )
        ).all()
    }
    dias = []
    cursor = periodo_inicio
    soma_fracao = 0.0
    while cursor <= periodo_fim:
        fracao = fracao_no_periodo.get(cursor, 1.0)
        soma_fracao += fracao
        dias.append({
            "data": cursor,
            "trabalhado": fracao == 1.0,
            "meia_diaria": fracao == 0.5,
            "pago": pago_ate is not None and cursor <= pago_ate,
        })
        cursor += timedelta(days=1)
    dias_trabalhados_periodo = sum(1 for x in dias if x["trabalhado"])
    dias_meia_periodo = sum(1 for x in dias if x["meia_diaria"])
    dias_folga_periodo = len(dias) - dias_trabalhados_periodo - dias_meia_periodo
    return {
        "diaria_id": diaria.id,
        "pessoa_nome": pessoa.nome if pessoa else "—",
        "valor_diaria": diaria.valor_diaria,
        "data_inicio": diaria.data_inicio,
        "data_fim": diaria.data_fim,
        "hoje": hoje,
        "modo": modo,
        "periodo_inicio": periodo_inicio,
        "periodo_fim": periodo_fim,
        "ultima_folga": ultima_folga,
        "controle_por_dia_desde": diaria.controle_por_dia_desde,
        "nunca_auditado": diaria.controle_por_dia_desde is None,
        "pago_ate": pago_ate,
        "dias": dias,
        "resumo_periodo": {
            "dias_no_periodo": len(dias),
            "dias_trabalhados": dias_trabalhados_periodo,
            "dias_folga": dias_folga_periodo,
            "dias_meia_diaria": dias_meia_periodo,
            "valor_periodo": round(soma_fracao * diaria.valor_diaria, 2),
        },
    }


@router.put("/diarias/{diaria_id}/dias")
def salvar_dias_diaria(
    diaria_id: int, dados: DiariaDiasPutIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Substitui (replace, não merge) o estado dos dias no período informado
    — o cliente sempre manda o estado corrigido inteiro da janela visível."""
    diaria = _diaria_ou_404(session, diaria_id, fazenda_id)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    if dados.periodo_inicio > dados.periodo_fim:
        raise HTTPException(status_code=400, detail="Período inválido: início não pode ser depois do fim")
    hoje = date.today()
    hoje_ou_fim = min(hoje, diaria.data_fim) if diaria.data_fim else hoje
    if dados.periodo_inicio < diaria.data_inicio:
        raise HTTPException(status_code=400, detail="Não dá para auditar dia antes do início da diária")
    if dados.periodo_fim > hoje_ou_fim:
        raise HTTPException(status_code=400, detail="Não dá para auditar dia que ainda não aconteceu")
    dias_informados: set[date] = set()
    for dia in dados.dias_nao_trabalhados:
        if dia < dados.periodo_inicio or dia > dados.periodo_fim:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} fora do período informado")
        if dia in dias_informados:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} duplicada em dias_nao_trabalhados")
        dias_informados.add(dia)
    dias_meia: set[date] = set()
    for dia in dados.dias_meia_diaria:
        if dia < dados.periodo_inicio or dia > dados.periodo_fim:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} fora do período informado")
        if dia in dias_informados or dia in dias_meia:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} não pode ser folga e meia diária ao mesmo tempo")
        dias_meia.add(dia)
    pago_ate = _pago_ate_diaria(session, diaria_id)
    if pago_ate is not None and dados.periodo_inicio <= pago_ate and not dados.confirmar_periodo_pago:
        raise HTTPException(
            status_code=409,
            detail=f"Este período já tem pagamento registrado (até {pago_ate}). Alterar os dias trabalhados vai "
                   "mudar o total apurado e o saldo devedor de um período já quitado. Confirme se quiser prosseguir.",
        )

    # 1) Substitui as exceções do período (replace, não merge).
    existentes = session.exec(
        select(DiariaDia).where(
            DiariaDia.diaria_id == diaria_id,
            DiariaDia.data >= dados.periodo_inicio, DiariaDia.data <= dados.periodo_fim,
        )
    ).all()
    for e in existentes:
        session.delete(e)
    for dia in sorted(dias_informados):
        session.add(DiariaDia(
            diaria_id=diaria_id, data=dia, trabalhado=False, fracao=0.0, usuario_id=user.id, fazenda_id=fazenda_id,
        ))
    for dia in sorted(dias_meia):
        session.add(DiariaDia(
            diaria_id=diaria_id, data=dia, trabalhado=False, fracao=0.5, usuario_id=user.id, fazenda_id=fazenda_id,
        ))

    # 2) Marca/recua o marco do calendário — nunca avança, só recua, e nunca
    # invade um período de auditoria legada já RESPONDIDO (mantém as duas
    # janelas disjuntas).
    _, ultimo_respondido_fim = _dias_confirmados_diaria(session, diaria_id)
    corte_candidato = dados.periodo_inicio
    if ultimo_respondido_fim is not None and ultimo_respondido_fim >= corte_candidato:
        corte_candidato = ultimo_respondido_fim + timedelta(days=1)
    diaria.controle_por_dia_desde = (
        min(diaria.controle_por_dia_desde, corte_candidato) if diaria.controle_por_dia_desde else corte_candidato
    )
    session.add(diaria)

    # 3) Descarta auditorias pendentes (nunca respondidas) que ficaram
    # cobertas pelo calendário — nada se perde porque nunca foram respondidas.
    pendentes_superadas = session.exec(
        select(DiariaAuditoria).where(
            DiariaAuditoria.diaria_id == diaria_id, DiariaAuditoria.dias_trabalhados.is_(None),
            DiariaAuditoria.periodo_fim >= diaria.controle_por_dia_desde,
        )
    ).all()
    for a in pendentes_superadas:
        session.delete(a)

    session.commit()
    session.refresh(diaria)
    return _resumo_diaria(session, diaria, pessoa.nome if pessoa else "—")


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
    # Conta bancária da fazenda de onde sai o vale — obrigatória quando o
    # dinheiro sai AGORA (dinheiro/pix/transferência); irrelevante para
    # "desconto_proximo_pagamento" (não há saída de caixa nenhuma agora — ver
    # `_validar_conta_vale_avulso`).
    conta_corrente_id: int | None = None
    # Só usados em PUT (edição) quando `valor` diverge do valor atual do vale
    # — mesma semântica de ValeParcelaEditIn.acao em rh_folha.py: "conceder"
    # (o vale muda de valor, o alvo absorve a diferença naturalmente ao
    # reaplicar o abatimento — comportamento padrão, sem redistribuir mais
    # nada); "redistribuir_igual" (depois de reaplicar, redivide igualmente
    # as parcelas/etapas do alvo ainda pendentes); "redistribuir_livre"
    # (idem, mas com o valor de cada parcela/etapa informado explicitamente).
    acao: str | None = None
    valores_itens: dict[int, float] | None = None
    confirmar: bool = False


def _info_parcelas_vale_avulso(session: Session, vale: ValeAvulso) -> dict:
    """Pra exibir no relatório de vales: quantas parcelas/etapas tem a
    origem do vale avulso, e a qual(is) delas ele se refere (via
    ValeAvulsoAbatimento) — só se aplica a empreitada/contrato; diária não
    tem parcela agendada, então volta sempre vazio."""
    if vale.origem_tipo == "diaria":
        return {"total_parcelas_origem": None, "parcelas_referenciadas": []}
    if vale.origem_tipo == "empreitada":
        empreitada = session.get(Empreitada, vale.origem_id)
        if empreitada and empreitada.tipo_pagamento == "por_etapa":
            todos = session.exec(
                select(EmpreitadaEtapa).where(EmpreitadaEtapa.empreitada_id == vale.origem_id).order_by(EmpreitadaEtapa.ordem, EmpreitadaEtapa.id)
            ).all()
            item_tipo = "empreitada_etapa"
        else:
            todos = session.exec(
                select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == vale.origem_id).order_by(EmpreitadaParcela.data_vencimento)
            ).all()
            item_tipo = "empreitada_parcela"
    else:
        todos = session.exec(
            select(ContratoParcela).where(ContratoParcela.contrato_id == vale.origem_id).order_by(ContratoParcela.data_vencimento)
        ).all()
        item_tipo = "contrato_parcela"

    posicao = {item.id: i + 1 for i, item in enumerate(todos)}
    abatimentos = session.exec(select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale.id)).all()
    referenciadas = [
        {"numero_parcela": posicao.get(ab.item_id), "valor_abatido": ab.valor_abatido}
        for ab in abatimentos if ab.item_tipo == item_tipo
    ]
    return {"total_parcelas_origem": len(todos), "parcelas_referenciadas": referenciadas}


def _listar_vales_avulsos(session: Session, origem_tipo: str, origem_id: int) -> list[dict]:
    vales = session.exec(
        select(ValeAvulso)
        .where(ValeAvulso.origem_tipo == origem_tipo, ValeAvulso.origem_id == origem_id)
        .order_by(ValeAvulso.data_pagamento)
    ).all()
    return [{**v.model_dump(), **_info_parcelas_vale_avulso(session, v)} for v in vales]


def _numeros_pagos(session: Session, numeros: list[str]) -> set[str]:
    if not numeros:
        return set()
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all()
    return {c.numero_lancamento for c in contas if c.valor_pago is not None}


def _itens_pendentes_vale_avulso(session: Session, origem_tipo: str, origem_id: int) -> tuple[str, list]:
    """Retorna (item_tipo, itens pendentes em ordem de vencimento) para o
    abatimento/reversão de um vale avulso de Empreitada/Contrato."""
    if origem_tipo == "empreitada":
        empreitada = session.get(Empreitada, origem_id)
        if empreitada and empreitada.tipo_pagamento == "por_etapa":
            itens = session.exec(
                select(EmpreitadaEtapa)
                .where(EmpreitadaEtapa.empreitada_id == origem_id, EmpreitadaEtapa.concluida == False)  # noqa: E712
                .order_by(EmpreitadaEtapa.ordem, EmpreitadaEtapa.id)
            ).all()
            return "empreitada_etapa", list(itens)
        todas = session.exec(
            select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == origem_id).order_by(EmpreitadaParcela.data_vencimento)
        ).all()
        pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in todas if p.numero_lancamento_gerado])
        return "empreitada_parcela", [p for p in todas if p.numero_lancamento_gerado not in pagos]
    if origem_tipo == "contrato":
        todas = session.exec(
            select(ContratoParcela).where(ContratoParcela.contrato_id == origem_id).order_by(ContratoParcela.data_vencimento)
        ).all()
        pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in todas if p.numero_lancamento_gerado])
        return "contrato_parcela", [p for p in todas if p.numero_lancamento_gerado not in pagos]
    return "", []


def _modelo_item_vale_avulso(item_tipo: str):
    return {"empreitada_parcela": EmpreitadaParcela, "empreitada_etapa": EmpreitadaEtapa, "contrato_parcela": ContratoParcela}[item_tipo]


def _sincronizar_conta_do_item(session: Session, item) -> None:
    numero = getattr(item, "numero_lancamento_gerado", None)
    if numero:
        conta = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()
        if conta and conta.valor_pago is None:
            conta.valor_total = item.valor
            session.add(conta)


def _aplicar_vale_avulso(
    session: Session, vale_avulso_id: int, origem_tipo: str, origem_id: int, valor: float,
    fazenda_id: int | None = None,
) -> None:
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

    Cada abatimento é registrado em `ValeAvulsoAbatimento`, para permitir
    reverter exatamente ao editar/excluir o vale (ver `_reverter_vale_avulso`).
    """
    restante = round(valor, 2)
    if restante <= 0 or origem_tipo == "diaria":
        return

    item_tipo, itens = _itens_pendentes_vale_avulso(session, origem_tipo, origem_id)
    if not item_tipo:
        return

    for item in itens:
        if restante <= 0:
            break
        abatido = min(item.valor, restante)
        if abatido <= 0:
            continue
        item.valor = round(item.valor - abatido, 2)
        restante = round(restante - abatido, 2)
        session.add(item)
        _sincronizar_conta_do_item(session, item)
        session.add(ValeAvulsoAbatimento(
            vale_avulso_id=vale_avulso_id, item_tipo=item_tipo, item_id=item.id, valor_abatido=abatido,
            fazenda_id=fazenda_id,
        ))


def _redistribuir_itens_pendentes_igual(session: Session, itens: list) -> None:
    """Como `_redistribuir_parcelas_pendentes` (empreitada/contrato), mas sem
    tocar `data_vencimento` — serve tanto para parcela quanto para etapa
    (EmpreitadaEtapa não tem data de vencimento própria)."""
    if len(itens) < 2:
        raise HTTPException(status_code=400, detail="É preciso ao menos 2 parcelas/etapas pendentes para redistribuir.")
    total = round(sum(i.valor for i in itens), 2)
    valor_base = round(total / len(itens), 2)
    restante = total
    for i, item in enumerate(itens):
        valor = valor_base if i < len(itens) - 1 else round(restante, 2)
        restante = round(restante - valor, 2)
        item.valor = valor
        session.add(item)
        _sincronizar_conta_do_item(session, item)


def _redistribuir_itens_pendentes_livre(session: Session, itens: list, valores: dict[int, float]) -> None:
    ids_pendentes = {i.id for i in itens}
    if set(valores.keys()) != ids_pendentes:
        raise HTTPException(status_code=400, detail="Informe o valor de todas as parcelas/etapas pendentes, e só delas.")
    for item in itens:
        novo = valores[item.id]
        if novo < 0:
            raise HTTPException(status_code=400, detail="Valor de parcela/etapa não pode ser negativo.")
        item.valor = round(novo, 2)
        session.add(item)
        _sincronizar_conta_do_item(session, item)


def _reverter_vale_avulso(session: Session, vale_avulso_id: int) -> None:
    """Desfaz o efeito de `_aplicar_vale_avulso`: devolve a cada item exatamente
    o valor que foi abatido dele (registrado em ValeAvulsoAbatimento), na
    ordem inversa em que foi abatido, e sincroniza a ContaGerencial vinculada."""
    abatimentos = session.exec(
        select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale_avulso_id).order_by(ValeAvulsoAbatimento.id.desc())
    ).all()
    for ab in abatimentos:
        Modelo = _modelo_item_vale_avulso(ab.item_tipo)
        item = session.get(Modelo, ab.item_id)
        if item:
            item.valor = round(item.valor + ab.valor_abatido, 2)
            session.add(item)
            _sincronizar_conta_do_item(session, item)
        session.delete(ab)


@router.get("/vale-avulso")
def listar_vales_avulsos_endpoint(
    origem_tipo: str, origem_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    if origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is not None:
        _origem_vale_avulso(session, origem_tipo, origem_id, fazenda_id)
    return _listar_vales_avulsos(session, origem_tipo, origem_id)


def _origem_vale_avulso(session: Session, origem_tipo: str, origem_id: int, fazenda_id: int | None):
    """Busca a origem (Empreitada/Contrato/Diária) de um vale avulso já
    verificando que pertence à `fazenda_id` informada — 404 se não existir ou
    for de outra fazenda."""
    if origem_tipo == "empreitada":
        origem = session.get(Empreitada, origem_id)
    elif origem_tipo == "contrato":
        origem = session.get(Contrato, origem_id)
    else:
        origem = session.get(Diaria, origem_id)
    if not origem or (origem.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail=f"{origem_tipo.capitalize()} não encontrado(a)")
    return origem


def _validar_conta_vale_avulso(
    session: Session, forma_pagamento: str, conta_corrente_id: int | None, fazenda_id: int | None,
) -> ContaCorrente | None:
    """Análogo a `_validar_conta_vale` (rh_folha.py) para o vale avulso —
    obrigatória só quando o dinheiro sai AGORA (dinheiro/pix/transferência);
    "desconto_proximo_pagamento" não movimenta banco nenhum na hora do vale
    (o efeito é só reduzir a próxima parcela/etapa/saldo devedor)."""
    if forma_pagamento == "desconto_proximo_pagamento":
        return None
    if not conta_corrente_id:
        raise HTTPException(status_code=400, detail="Selecione a conta bancária de onde sai o vale.")
    conta = session.get(ContaCorrente, conta_corrente_id)
    if not conta or (conta.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada")
    return conta


def _sincronizar_conta_vale_avulso(
    session: Session, vale: ValeAvulso, pessoa_nome: str, conta: ContaCorrente | None, fazenda_id: int | None,
) -> None:
    """
    Cria (ou, numa edição, atualiza) o lançamento (ContaGerencial) que
    representa a SAÍDA de caixa do vale avulso — análogo a
    `_sincronizar_conta_vale` (rh_folha.py) e a `registrar_pagamento_diaria`
    acima: já nasce PAGO, porque o vale é entregue no ato.

    NÃO duplica valor no extrato: `_aplicar_vale_avulso` só reduz a
    PRÓXIMA parcela/etapa (ou o saldo da diária) que ainda vai ser paga —
    exatamente como a folha de funcionário lança o líquido já descontado do
    vale. Antes desta função existir, o dinheiro do vale avulso saía do
    caixa/banco no ato e não aparecia em lugar nenhum do Financeiro; este
    lançamento é o que fecha esse furo. NÃO remova achando que é bug de
    duplicidade.

    Quando `conta` é None (forma_pagamento == "desconto_proximo_pagamento"),
    não há saída de caixa nenhuma a registrar — nenhum ContaGerencial é
    criado/mantido (removendo um lançamento de edição anterior, se houver).
    """
    conta_existente = None
    if vale.numero_lancamento_gerado:
        conta_existente = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado)
        ).first()

    if conta is None:
        if conta_existente:
            session.delete(conta_existente)
        vale.numero_lancamento_gerado = None
        session.add(vale)
        return

    descricao = f"Vale — {pessoa_nome} ({vale.origem_tipo})"
    if conta_existente:
        conta_existente.descricao = descricao
        conta_existente.fornecedor_cliente = pessoa_nome
        conta_existente.data_vencimento = vale.data_pagamento
        conta_existente.data_competencia = vale.data_pagamento.replace(day=1)
        conta_existente.valor_total = vale.valor
        conta_existente.data_pagamento = vale.data_pagamento
        conta_existente.valor_pago = vale.valor
        conta_existente.conta_bancaria = rotulo_conta_corrente(conta)
        conta_existente.forma_pagamento = vale.forma_pagamento
        session.add(conta_existente)
    else:
        numero_lancamento = _proximo_numero_lancamento(session, vale.data_pagamento.year)
        vale.numero_lancamento_gerado = numero_lancamento
        session.add(vale)
        session.add(ContaGerencial(
            numero_lancamento=numero_lancamento,
            descricao=descricao,
            data_vencimento=vale.data_pagamento,
            data_competencia=vale.data_pagamento.replace(day=1),
            fornecedor_cliente=pessoa_nome,
            tipo_documento="Vale avulso",
            centro_custo="Pecuária Leiteira",
            valor_total=vale.valor,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            data_pagamento=vale.data_pagamento,
            valor_pago=vale.valor,
            conta_bancaria=rotulo_conta_corrente(conta),
            forma_pagamento=vale.forma_pagamento,
            fazenda_id=fazenda_id,
        ))


@router.post("/vale-avulso")
def criar_vale_avulso(
    dados: ValeAvulsoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
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
    origem = _origem_vale_avulso(session, dados.origem_tipo, dados.origem_id, fazenda_id)
    conta = _validar_conta_vale_avulso(session, dados.forma_pagamento, dados.conta_corrente_id, fazenda_id)
    pessoa = session.get(Pessoa, origem.pessoa_id)

    vale = ValeAvulso(
        origem_tipo=dados.origem_tipo, origem_id=dados.origem_id, pessoa_id=origem.pessoa_id,
        valor=dados.valor, forma_pagamento=dados.forma_pagamento, data_pagamento=dados.data_pagamento,
        observacao=dados.observacao, conta_corrente_id=conta.id if conta else None,
        usuario_id=user.id, fazenda_id=fazenda_id,
    )
    session.add(vale)
    session.commit()
    session.refresh(vale)

    _aplicar_vale_avulso(session, vale.id, dados.origem_tipo, dados.origem_id, dados.valor, fazenda_id=vale.fazenda_id)
    # Gera (quando aplicável) o lançamento que faltava no extrato para a
    # saída de caixa do vale — ver `_sincronizar_conta_vale_avulso`.
    _sincronizar_conta_vale_avulso(session, vale, pessoa.nome if pessoa else "—", conta, fazenda_id)
    session.commit()

    if dados.origem_tipo == "empreitada":
        resultado = _serializar_empreitada(session, origem)
    elif dados.origem_tipo == "contrato":
        resultado = _serializar_contrato(session, origem)
    else:
        resultado = _resumo_diaria(session, origem, pessoa.nome if pessoa else "—")
    return {"vale": vale.model_dump(), "origem": resultado}


@router.get("/vale-avulso/todos")
def listar_todos_vales_avulsos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Relatório unificado de vales avulsos (Empreitada/Contrato/Diária), para
    aparecer junto do Relatório de vales e descontos (vale de funcionário)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ValeAvulso)
    if fazenda_id is not None:
        query = query.where(ValeAvulso.fazenda_id == fazenda_id)
    vales = session.exec(query.order_by(ValeAvulso.data_pagamento.desc())).all()
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    empreitadas = {e.id: e.descricao for e in session.exec(select(Empreitada)).all()}
    contratos = {c.id: c.descricao for c in session.exec(select(Contrato)).all()}
    origens_lancamento = origens_lancamento_por_vale(session, {v.id for v in vales}, "vale_avulso_id")
    saida = []
    for v in vales:
        if v.origem_tipo == "empreitada":
            origem_descricao = f"Empreitada — {empreitadas.get(v.origem_id, '—')}"
        elif v.origem_tipo == "contrato":
            origem_descricao = f"Contrato — {contratos.get(v.origem_id, '—')}"
        else:
            origem_descricao = "Diária"
        saida.append({
            **v.model_dump(), "pessoa_nome": pessoas.get(v.pessoa_id, "—"), "origem_descricao": origem_descricao,
            **_info_parcelas_vale_avulso(session, v),
            "origem_lancamento": origens_lancamento.get(v.id),
        })
    return saida


@router.put("/vale-avulso/{vale_id}")
def atualizar_vale_avulso(
    vale_id: int, dados: ValeAvulsoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    vale = session.get(ValeAvulso, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    if dados.origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.origem_tipo != vale.origem_tipo or dados.origem_id != vale.origem_id:
        raise HTTPException(status_code=400, detail="Não é possível trocar a origem (Empreitada/Contrato/Diária) de um vale já lançado")
    conta = _validar_conta_vale_avulso(session, dados.forma_pagamento, dados.conta_corrente_id, fazenda_id)

    diferenca = round(dados.valor - vale.valor, 2)
    if diferenca != 0 and not dados.confirmar:
        raise HTTPException(status_code=409, detail={
            "mensagem": "O valor informado é diferente do valor atual deste vale.",
            "valor_calculado": vale.valor,
            "valor_informado": dados.valor,
            "diferenca": diferenca,
        })

    _reverter_vale_avulso(session, vale_id)
    session.commit()

    vale.valor = dados.valor
    vale.forma_pagamento = dados.forma_pagamento
    vale.data_pagamento = dados.data_pagamento
    vale.observacao = dados.observacao
    vale.conta_corrente_id = conta.id if conta else None
    session.add(vale)
    session.commit()

    _aplicar_vale_avulso(session, vale_id, dados.origem_tipo, dados.origem_id, dados.valor, fazenda_id=vale.fazenda_id)
    pessoa = session.get(Pessoa, vale.pessoa_id)
    # Mantém o lançamento gerado (ContaGerencial) da saída de caixa do vale
    # em sincronia com a edição — cria/atualiza/remove conforme a mudança.
    _sincronizar_conta_vale_avulso(session, vale, pessoa.nome if pessoa else "—", conta, fazenda_id)
    session.commit()

    # "conceder" (ou diferenca == 0) não precisa de mais nada: o alvo já
    # absorveu naturalmente a diferença ao reaplicar o abatimento acima.
    # "redistribuir_*" reequilibra as parcelas/etapas do alvo ainda
    # pendentes, para o efeito não ficar concentrado só na primeira delas.
    if diferenca != 0 and dados.acao in ("redistribuir_igual", "redistribuir_livre") and dados.origem_tipo in ("empreitada", "contrato"):
        _, itens_pendentes = _itens_pendentes_vale_avulso(session, dados.origem_tipo, dados.origem_id)
        if dados.acao == "redistribuir_igual":
            _redistribuir_itens_pendentes_igual(session, itens_pendentes)
        else:
            if not dados.valores_itens:
                raise HTTPException(status_code=400, detail="Informe o valor de cada parcela/etapa pendente.")
            _redistribuir_itens_pendentes_livre(session, itens_pendentes, dados.valores_itens)
        session.commit()

    session.refresh(vale)
    if dados.origem_tipo == "empreitada":
        origem = session.get(Empreitada, dados.origem_id)
        resultado = _serializar_empreitada(session, origem)
    elif dados.origem_tipo == "contrato":
        origem = session.get(Contrato, dados.origem_id)
        resultado = _serializar_contrato(session, origem)
    else:
        origem = session.get(Diaria, dados.origem_id)
        pessoa = session.get(Pessoa, origem.pessoa_id)
        resultado = _resumo_diaria(session, origem, pessoa.nome if pessoa else "—")
    return {"vale": vale.model_dump(), "origem": resultado}


@router.delete("/vale-avulso/{vale_id}")
def excluir_vale_avulso(
    vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeAvulso, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    _reverter_vale_avulso(session, vale_id)
    # Remove também o lançamento (ContaGerencial) gerado para a saída de
    # caixa do vale — sem isso, excluir o vale deixaria um lançamento órfão
    # no extrato, sem vale nenhum por trás dele.
    if vale.numero_lancamento_gerado:
        conta_gerada = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado)
        ).first()
        if conta_gerada:
            session.delete(conta_gerada)
    # Zera o vínculo em qualquer LancamentoItem que apontava para este vale
    # (caminho inverso: usuário excluiu o vale direto no Relatório de vales,
    # não pelo checkbox do item) — sem isso ficaria FK pendurada e o item
    # sumido dos relatórios gerenciais para sempre (ver rules/vale_item.py).
    limpar_vinculo_de_itens(session, vale_avulso_id=vale_id)
    session.delete(vale)
    session.commit()
    return {"ok": True}




