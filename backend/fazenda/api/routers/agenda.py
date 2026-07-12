"""
Router da Agenda — calcula e retorna eventos do dia ou de um período.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import Usuario, get_current_user
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, Animal, AplicacaoAgendada, ColostragemBezerra, ContaGerencial, DietaLancamento, Estoque, EstoqueSemen, EventoRealizado, MovimentoEstoque, Parto,
    ProtocoloIatfAplicacao, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa, ProtocoloSanitarioLancamento, Sanidade,
    Servico,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.agenda_engine import AgendaEngine, AgendaItem
from fazenda.rules.eventos_sanitarios import eventos_agenda as _eventos_sanitarios_agenda
from fazenda.rules.unidades import pode_dar_baixa_direta

router = APIRouter(prefix="/agenda", tags=["agenda"])

# Categoria do evento -> módulo cujo acesso o usuário precisa ter para ver o
# evento na Agenda (e no sininho de notificações, ver notificacoes.py).
# "Atividades" é o balde genérico de eventos manuais — exige só o acesso à
# própria Agenda, não um módulo mais específico.
MODULO_POR_CATEGORIA = {
    "Reprodutivo": "reproducao",
    "Produção": "producao",
    "Gestão/Financeiro": "financeiro",
    "alimentacao": "alimentacao",
    "sanidade": "sanidade",
    "Sanidade": "sanidade",
    "Atividades": "agenda",
}

TIPOS_EVENTO = ["Compra", "Venda", "Serviço", "Outro"]


def _modulos_liberados(usuario: Usuario) -> set[str]:
    if usuario.papel == "admin":
        return set(MODULO_POR_CATEGORIA.values()) | {"reproducao"}
    return {m.strip() for m in (usuario.permissoes or "").split(",") if m.strip()}


def _model_to_dict(obj) -> dict:
    return obj.model_dump()


def _proxima_ocorrencia(base: date, intervalo_dias: int | None, intervalo_meses: int | None) -> date:
    if intervalo_dias:
        return base + timedelta(days=intervalo_dias)
    mes_total = base.month - 1 + (intervalo_meses or 1)
    ano = base.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _gerar_agenda_recorrente(session: Session) -> None:
    """
    Para cada evento manual de agenda marcado como recorrente (o "modelo"),
    gera automaticamente as próximas ocorrências até hoje — mesmo padrão
    "lazy pull" da folha de pagamento recorrente (_gerar_folha_recorrente).
    """
    hoje = date.today()
    modelos = session.exec(
        select(AgendaManual).where(
            AgendaManual.recorrente == True,  # noqa: E712
            AgendaManual.origem_recorrencia_id == None,  # noqa: E711
        )
    ).all()
    for modelo in modelos:
        if not modelo.intervalo_dias and not modelo.intervalo_meses:
            continue
        ultima = session.exec(
            select(AgendaManual)
            .where(AgendaManual.origem_recorrencia_id == modelo.id)
            .order_by(AgendaManual.data_evento.desc())
        ).first()
        proxima = _proxima_ocorrencia(ultima.data_evento if ultima else modelo.data_evento, modelo.intervalo_dias, modelo.intervalo_meses)
        while proxima <= hoje:
            session.add(AgendaManual(
                data_evento=proxima, descricao=modelo.descricao, categoria=modelo.categoria,
                numero_animal=modelo.numero_animal, lotes=modelo.lotes, tipo_evento=modelo.tipo_evento,
                observacao=modelo.observacao, origem_recorrencia_id=modelo.id,
            ))
            session.commit()
            proxima = _proxima_ocorrencia(proxima, modelo.intervalo_dias, modelo.intervalo_meses)


@router.get("/")
def calcular_agenda(
    data: date = date.today(),
    dias: int = 10,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
) -> dict:
    """
    Calcula a agenda preditiva para a data informada (padrão: hoje).
    `dias` é a janela de contas a pagar/receber (padrão 10, o front pede mais
    quando o usuário amplia o filtro "Até").
    Retorna candidatas IATF, checagem de hormônios, BST e todos os eventos.
    """
    _gerar_agenda_recorrente(session)
    animais = [_model_to_dict(a) for a in session.exec(select(Animal).where(Animal.ativo == True)).all() if not a.eh_semen and a.sexo != "M"]
    servicos_ult = [
        _model_to_dict(s) for s in session.exec(
            select(Servico).where(Servico.ult_ocorrencia == 1)
        ).all()
    ]
    partos = [_model_to_dict(p) for p in session.exec(select(Parto)).all()]
    estoque = [_model_to_dict(e) for e in session.exec(select(Estoque)).all()]
    contas = [_model_to_dict(c) for c in session.exec(select(ContaGerencial)).all()]
    manuais = [_model_to_dict(m) for m in session.exec(select(AgendaManual)).all()]

    engine = AgendaEngine()
    result = engine.calcular(
        data_referencia=data,
        animais=animais,
        servicos=servicos_ult,
        partos=partos,
        estoque=estoque,
        contas=contas,
        eventos_manuais=manuais,
        dias_contas_a_pagar=dias,
    )

    # Remove da lista os eventos já marcados como "realizado" (workflow da agenda).
    realizados = {r.evento_id for r in session.exec(select(EventoRealizado)).all()}
    eventos = [e for e in result.eventos if e.chave not in realizados]

    # Dietas ativas com encerramento previsto: evento de análise (chave própria,
    # fora do AgendaEngine para não mexer no cálculo delicado já testado dele).
    dietas_para_analise = session.exec(
        select(DietaLancamento).where(
            DietaLancamento.data_efetivo_encerramento == None,  # noqa: E711
            DietaLancamento.data_prevista_encerramento != None,  # noqa: E711
        )
    ).all()
    eventos_dieta = [
        {
            "id": f"dieta_analise_{d.id}", "data": d.data_prevista_encerramento.isoformat(), "categoria": "alimentacao",
            "descricao": f"Analisar dieta do lote {d.lote} (encerramento previsto)",
            "numero_animal": None, "observacao": d.observacao, "fonte": "auto", "cor": "var(--dourado)", "ref": None,
            "lote": d.lote,
        }
        for d in dietas_para_analise
        if f"dieta_analise_{d.id}" not in realizados
    ]

    # Protocolo sanitário (mastite e outros) — uma etapa/dia pendente vira um
    # evento na Agenda; a baixa de estoque só acontece quando o usuário marca
    # "realizado" (ver POST /agenda/realizados).
    aplicacoes_pendentes = session.exec(
        select(ProtocoloSanitarioAplicacao).where(ProtocoloSanitarioAplicacao.realizada == False)  # noqa: E712
    ).all()
    etapas_por_id = {e.id: e for e in session.exec(select(ProtocoloSanitarioEtapa)).all()}
    lancamentos_por_id = {l.id: l for l in session.exec(select(ProtocoloSanitarioLancamento)).all()}
    protocolos_por_id = {p.id: p for p in session.exec(select(ProtocoloSanitario)).all()}
    eventos_protocolo = []
    for ap in aplicacoes_pendentes:
        chave = f"protocolo_sanitario_{ap.id}"
        if chave in realizados:
            continue
        etapa = etapas_por_id.get(ap.etapa_id)
        lancamento = lancamentos_por_id.get(ap.lancamento_id)
        protocolo = protocolos_por_id.get(lancamento.protocolo_id) if lancamento else None
        if not etapa or not lancamento or not protocolo:
            continue
        produto = ap.produto or etapa.produto
        eventos_protocolo.append({
            "id": chave, "data": ap.data_prevista.isoformat(), "categoria": "sanidade",
            "descricao": f"{protocolo.nome} — D{etapa.dia} — matriz {lancamento.numero_matriz} — {produto}",
            "numero_animal": lancamento.numero_matriz, "observacao": lancamento.observacao,
            "fonte": "auto", "cor": "var(--dourado)", "ref": None,
            # Agrupa no app as aplicações do mesmo protocolo/dia/data (lote) para
            # oferecer "lote ou individual". Cada evento continua confirmável por
            # si (id próprio), então o backend não muda.
            "tipo": "protocolo_sanitario",
            "grupo": f"psan_{lancamento.protocolo_id}_{etapa.dia}_{ap.data_prevista.isoformat()}",
            "grupo_titulo": f"{protocolo.nome} — D{etapa.dia}",
            "produto": produto,
        })

    # Protocolo IATF — agrupa por (lançamento, dia): uma linha por etapa do
    # protocolo, não uma por animal, mostrando todos os animais daquele passo
    # de uma vez. Em protocolos normais só entram etapas de hoje em diante
    # (retroativo não spamma passos já vencidos); em protocolos lançados
    # RETROATIVAMENTE (IATF sem protocolo, D0 no passado), as etapas vencidas
    # aparecem como pendência.
    lancamentos_iatf_por_id = {l.id: l for l in session.exec(select(ProtocoloIatfLancamento)).all()}
    aplicacoes_iatf = [
        a for a in session.exec(
            select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.realizada == False)  # noqa: E712
        ).all()
        if a.data_prevista >= data or getattr(lancamentos_iatf_por_id.get(a.lancamento_id), "retroativo", False)
    ]
    grupos_iatf: dict[tuple[int, int], list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes_iatf:
        grupos_iatf.setdefault((ap.lancamento_id, ap.dia), []).append(ap)

    eventos_iatf = []
    DIAS_PROTOCOLO_IATF = [0, 7, 9, 11]
    for (lancamento_id, dia), aps in grupos_iatf.items():
        chave = f"protocolo_iatf_{lancamento_id}_{dia}"
        if chave in realizados:
            continue
        lancamento = lancamentos_iatf_por_id.get(lancamento_id)
        if not lancamento:
            continue
        animais_grupo = sorted((a.numero_matriz for a in aps), key=chave_numero)
        proximos_dias = [d for d in DIAS_PROTOCOLO_IATF if d > dia]
        proxima_etapa = None
        if proximos_dias:
            proximo_dia = proximos_dias[0]
            proxima_data = lancamento.data_d0 + timedelta(days=proximo_dia)
            proxima_etapa = f"Próxima etapa: D{proximo_dia} em {proxima_data.strftime('%d/%m/%Y')}"
        eventos_iatf.append({
            "id": chave, "data": aps[0].data_prevista.isoformat(), "categoria": "Reprodutivo",
            "descricao": f"{lancamento.nome_protocolo} — D{dia}",
            "numero_animal": None, "observacao": proxima_etapa,
            "fonte": "manual", "cor": "var(--dourado)", "ref": None,
            "tipo": "protocolo_iatf", "dia": dia, "animais": animais_grupo, "hormonio": aps[0].descricao,
            "protocolo": lancamento.nome_protocolo,
        })

    # Eventos sanitários agendados (por época ou por evento de vida) — cada um
    # já traz o medicamento padrão para pré-preencher a Aplicação ao dar baixa.
    eventos_sanitarios = _eventos_sanitarios_agenda(session, data, realizados)

    # Aplicações programadas ("aplicado? não" / data futura) ainda não baixadas.
    # Dar baixa aqui gera a aplicação de verdade e a saída de estoque.
    aplic_agendadas = session.exec(
        select(AplicacaoAgendada).where(AplicacaoAgendada.aplicado == False)  # noqa: E712
    ).all()
    eventos_aplic_agendada = [{
        "id": f"aplic_agendada_{a.id}", "data": a.data.isoformat(), "categoria": "sanidade",
        "descricao": f"Aplicar {a.produto}"
        + (f" — {a.dose} {a.unidade or ''}" if a.dose is not None else "")
        + f" — matriz {a.numero_matriz}",
        "numero_animal": a.numero_matriz, "observacao": "Programada — dê baixa para aplicar e baixar o estoque.",
        "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "aplicacao_agendada",
        "produto": a.produto, "dose": a.dose, "unidade": a.unidade, "via": a.via,
    } for a in aplic_agendadas if f"aplic_agendada_{a.id}" not in realizados]

    # Colostragem + exame de sangue (IgG) das bezerras recém-nascidas —
    # 24h após o parto (sempre no dia seguinte). Se ao lançar o parto não se
    # preencheu a colostragem ou o IgG, entram como pendência até completar.
    # Só considera partos dos últimos 30 dias (não spamma nascimentos antigos).
    eventos_colostro = []
    limite_parto = data - timedelta(days=30)
    partos_recentes = session.exec(
        select(Parto).where(Parto.data_parto >= limite_parto, Parto.data_parto <= data)
    ).all()
    if partos_recentes:
        colostro_por_animal = {c.numero_animal: c for c in session.exec(select(ColostragemBezerra)).all()}
        # Bezerras (crias) por (mãe, data de nascimento) para casar com o parto.
        crias_por_chave: dict[tuple[str, object], list[Animal]] = {}
        for a in session.exec(select(Animal).where(Animal.ativo == True, Animal.mae_numero != None)).all():  # noqa: E711,E712
            crias_por_chave.setdefault((a.mae_numero, a.data_nasc), []).append(a)
        for parto in partos_recentes:
            dia_seguinte = (parto.data_parto + timedelta(days=1)).isoformat()
            for cria in crias_por_chave.get((parto.numero_matriz, parto.data_parto), []):
                col = colostro_por_animal.get(cria.numero)
                colostro_falta = col is None or (col.litros_colostro is None and col.brix_colostro is None)
                igg_falta = col is None or col.brix_soro is None
                if colostro_falta:
                    chave = f"colostragem_pendente_{cria.numero}"
                    if chave not in realizados:
                        eventos_colostro.append({
                            "id": chave, "data": dia_seguinte, "categoria": "sanidade",
                            "descricao": f"Preencher dados da colostragem — bezerra {cria.numero}",
                            "numero_animal": cria.numero, "observacao": "Colostro/Brix não lançados no parto — registre na ficha do animal.",
                            "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "colostragem_pendente",
                        })
                if igg_falta:
                    chave = f"igg_pendente_{cria.numero}"
                    if chave not in realizados:
                        eventos_colostro.append({
                            "id": chave, "data": dia_seguinte, "categoria": "sanidade",
                            "descricao": f"Fazer exame de sangue (IgG) — bezerra {cria.numero}",
                            "numero_animal": cria.numero, "observacao": "Teste de sangue (Brix do soro) não lançado — registre na ficha do animal.",
                            "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "igg_pendente",
                        })

    # Estoque mínimo de sêmen POR CATEGORIA — abaixo do mínimo, um alerta
    # DIÁRIO na agenda (a chave inclui a data → reaparece todo dia até a NF
    # repor). Mínimos: convencional 20, sexado 5 (ver cadastro.MINIMO_SEMEN).
    MINIMO_SEMEN = {"convencional": 20, "sexado": 5}
    totais_semen = {"convencional": 0, "sexado": 0}
    for s in session.exec(select(EstoqueSemen)).all():
        if s.ativo and s.tipo in totais_semen:
            totais_semen[s.tipo] += s.doses or 0
    eventos_semen = []
    hoje_iso = data.isoformat()
    for cat, minimo in MINIMO_SEMEN.items():
        total = totais_semen[cat]
        if total < minimo:
            chave = f"semen_minimo_{cat}_{hoje_iso}"
            if chave in realizados:
                continue
            eventos_semen.append({
                "id": chave, "data": hoje_iso, "categoria": "Reprodutivo",
                "descricao": f"Estoque de sêmen {cat} abaixo do mínimo: {total} de {minimo} doses",
                "numero_animal": None, "observacao": f"Comprar sêmen {cat} — falta(m) {minimo - total} dose(s). Alerta diário até a NF repor.",
                "fonte": "auto", "cor": "var(--red)", "ref": None, "tipo": "semen_minimo",
            })

    # Só mostra o que o usuário tem permissão de ver — se falta acesso a um
    # módulo (ex.: "financeiro"), nenhum vestígio dele aparece na Agenda: nem
    # os eventos daquela categoria, nem as contas a pagar, nem os painéis
    # reprodutivos (candidatas IATF, BST).
    modulos = _modulos_liberados(usuario)
    eventos_visiveis = [
        {
            "id": e.chave,
            "data": e.data.isoformat(),
            "categoria": e.categoria,
            "descricao": e.descricao,
            "numero_animal": e.numero_animal,
            "observacao": e.observacao,
            "fonte": e.fonte,
            "cor": e.cor,
            "ref": e.ref,
            "lote": e.lote,
            "tipo_evento": e.tipo_evento,
        }
        for e in eventos
    ] + eventos_dieta + eventos_protocolo + eventos_iatf + eventos_sanitarios + eventos_aplic_agendada + eventos_semen + eventos_colostro
    eventos_visiveis = [
        e for e in eventos_visiveis
        if MODULO_POR_CATEGORIA.get(e["categoria"], None) is None or MODULO_POR_CATEGORIA[e["categoria"]] in modulos
    ]
    tem_financeiro = "financeiro" in modulos
    tem_reproducao = "reproducao" in modulos

    return {
        "data_referencia": result.data_referencia.isoformat(),
        "candidatas_iatf": [
            {"numero_matriz": c.numero_matriz, "sit_rep": c.sit_rep, "del_dias": c.del_dias, "motivo": c.motivo}
            for c in result.candidatas_iatf
        ] if tem_reproducao else [],
        "necessidade_iatf": (result.necessidade_iatf.__dict__ if result.necessidade_iatf else None) if tem_reproducao else None,
        "proxima_visita_iatf": (result.proxima_visita_iatf.isoformat() if result.proxima_visita_iatf else None) if tem_reproducao else None,
        "proxima_visita_bst": (result.proxima_visita_bst.isoformat() if result.proxima_visita_bst else None) if tem_reproducao else None,
        "hormonios_check": [h.__dict__ for h in result.hormonios_check] if tem_reproducao else [],
        "bst_elegiveis": [b.__dict__ for b in result.bst_elegiveis] if tem_reproducao else [],
        "bst_excluidos": [b.__dict__ for b in result.bst_excluidos] if tem_reproducao else [],
        "contas_a_pagar": result.contas_a_pagar if tem_financeiro else [],
        "eventos": eventos_visiveis,
        "totais": {
            "candidatas_iatf": len(result.candidatas_iatf) if tem_reproducao else 0,
            "bst_elegiveis": len(result.bst_elegiveis) if tem_reproducao else 0,
            "contas_a_pagar": len(result.contas_a_pagar) if tem_financeiro else 0,
            "eventos": len(eventos_visiveis),
        },
    }


class RealizadoIn(BaseModel):
    evento_id: str
    animais: list[str] | None = None  # subconjunto opcional (protocolo_iatf) — None = todos do grupo


def _baixar_protocolo_sanitario(session: Session, evento_id: str) -> None:
    """
    Ao marcar "realizado" um evento de protocolo sanitário: registra a
    aplicação em Sanidade e dá baixa automática do produto no Estoque (quando
    a unidade da etapa bate com a unidade de estoque do produto).
    """
    aplicacao_id = int(evento_id.removeprefix("protocolo_sanitario_"))
    aplicacao = session.get(ProtocoloSanitarioAplicacao, aplicacao_id)
    if not aplicacao or aplicacao.realizada:
        return
    etapa = session.get(ProtocoloSanitarioEtapa, aplicacao.etapa_id)
    lancamento = session.get(ProtocoloSanitarioLancamento, aplicacao.lancamento_id)
    if not etapa or not lancamento:
        return

    hoje = date.today()
    aplicacao.realizada = True
    aplicacao.data_realizacao = hoje
    session.add(aplicacao)

    # Se a etapa foi cadastrada por princípio ativo/classificação, usa o
    # medicamento escolhido no lançamento; senão, o produto da própria etapa.
    produto = aplicacao.produto or etapa.produto

    session.add(Sanidade(
        numero_matriz=lancamento.numero_matriz, data_aplicacao=hoje, produto=produto,
        dose=etapa.dosagem, unidade=etapa.unidade, via=etapa.via, responsavel=lancamento.responsavel,
        obs=f"Protocolo sanitário — D{etapa.dia}" + (f" — {lancamento.observacao}" if lancamento.observacao else ""),
    ))

    estoque_item = session.exec(select(Estoque).where(Estoque.nome == produto)).first()
    if estoque_item and estoque_item.estocavel is not False and pode_dar_baixa_direta(etapa.unidade, estoque_item.unidade):
        estoque_item.quantidade = (estoque_item.quantidade or 0) - etapa.dosagem
        if estoque_item.estoque_minimo is not None:
            estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
        estoque_item.atualizado_em = datetime.utcnow()
        session.add(estoque_item)
        session.add(MovimentoEstoque(
            nome_item=estoque_item.nome, movimento="Aplicação", quantidade=etapa.dosagem,
            unidade=estoque_item.unidade, data_movimento=hoje,
            observacao=f"Protocolo sanitário — matriz {lancamento.numero_matriz} — D{etapa.dia}",
        ))
    session.commit()


def _baixar_aplicacao_agendada(session: Session, evento_id: str) -> None:
    """Confirma uma aplicação programada: cria o registro de Sanidade e dá a
    baixa de estoque (quando a unidade bate com a do estoque)."""
    aid = int(evento_id.removeprefix("aplic_agendada_"))
    ag = session.get(AplicacaoAgendada, aid)
    if not ag or ag.aplicado:
        return
    hoje = date.today()
    ag.aplicado = True
    ag.data_aplicacao = hoje
    session.add(ag)

    session.add(Sanidade(
        numero_matriz=ag.numero_matriz, data_aplicacao=hoje, produto=ag.produto,
        dose=ag.dose, unidade=ag.unidade, via=ag.via, responsavel=ag.responsavel, obs=ag.observacao,
    ))

    estoque_item = session.exec(select(Estoque).where(Estoque.nome == ag.produto)).first()
    if ag.dose and estoque_item and estoque_item.estocavel is not False and pode_dar_baixa_direta(ag.unidade, estoque_item.unidade):
        estoque_item.quantidade = (estoque_item.quantidade or 0) - ag.dose
        if estoque_item.estoque_minimo is not None:
            estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
        estoque_item.atualizado_em = datetime.utcnow()
        session.add(estoque_item)
        session.add(MovimentoEstoque(
            nome_item=estoque_item.nome, movimento="Aplicação", quantidade=ag.dose,
            unidade=estoque_item.unidade, data_movimento=hoje,
            observacao=f"Aplicação programada — matriz {ag.numero_matriz}",
        ))
    session.commit()


def _marcar_protocolo_iatf_realizado(session: Session, evento_id: str, animais: list[str] | None) -> None:
    """
    Marca a(s) aplicação(ões) de um grupo (lançamento, dia) do protocolo IATF
    como realizadas. Sem `animais`, marca o grupo inteiro; com `animais`,
    confirma só esse subconjunto — os demais continuam pendentes no grupo.
    """
    resto = evento_id.removeprefix("protocolo_iatf_")
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.lancamento_id == lancamento_id,
            ProtocoloIatfAplicacao.dia == dia,
            ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
        )
    ).all()
    if animais is not None:
        alvo = set(animais)
        aplicacoes = [a for a in aplicacoes if a.numero_matriz in alvo]

    hoje = date.today()
    lancamento = session.get(ProtocoloIatfLancamento, lancamento_id)
    responsavel = getattr(lancamento, "responsavel", None)

    # Hormônios cadastrados para este dia (ex.: D0 = 1ml SincroCP + 2ml Estron).
    # Cada vaca confirmada gera uma aplicação em Sanidade e uma baixa de estoque.
    hormonios = session.exec(
        select(ProtocoloIatfHormonio).where(
            ProtocoloIatfHormonio.lancamento_id == lancamento_id,
            ProtocoloIatfHormonio.dia == dia,
        )
    ).all()

    for ap in aplicacoes:
        ap.realizada = True
        ap.data_realizacao = hoje
        session.add(ap)
        for h in hormonios:
            session.add(Sanidade(
                numero_matriz=ap.numero_matriz, data_aplicacao=hoje, produto=h.produto,
                dose=h.dose, unidade=h.unidade, via=h.via, responsavel=responsavel,
                obs=f"Protocolo IATF — D{dia}",
            ))

    # Baixa de estoque: uma vez por hormônio, dose × nº de vacas confirmadas.
    n_vacas = len(aplicacoes)
    if n_vacas:
        for h in hormonios:
            if not h.dose:
                continue
            estoque_item = session.exec(select(Estoque).where(Estoque.nome == h.produto)).first()
            if estoque_item and estoque_item.estocavel is not False and pode_dar_baixa_direta(h.unidade, estoque_item.unidade):
                total = h.dose * n_vacas
                estoque_item.quantidade = (estoque_item.quantidade or 0) - total
                if estoque_item.estoque_minimo is not None:
                    estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
                estoque_item.atualizado_em = datetime.utcnow()
                session.add(estoque_item)
                session.add(MovimentoEstoque(
                    nome_item=estoque_item.nome, movimento="Aplicação", quantidade=total,
                    unidade=estoque_item.unidade, data_movimento=hoje,
                    observacao=f"Protocolo IATF — D{dia} — {n_vacas} vaca(s)",
                ))
    session.commit()


@router.post("/realizados")
def marcar_realizado(dados: RealizadoIn, session: Session = Depends(get_session)) -> dict:
    """Marca um evento como realizado — ele sai da agenda (pendentes e futuros)."""
    if dados.evento_id.startswith("protocolo_iatf_"):
        _marcar_protocolo_iatf_realizado(session, dados.evento_id, dados.animais)
        return {"marcado": True}

    existe = session.exec(select(EventoRealizado).where(EventoRealizado.evento_id == dados.evento_id)).first()
    if not existe:
        session.add(EventoRealizado(evento_id=dados.evento_id))
        session.commit()
        if dados.evento_id.startswith("protocolo_sanitario_"):
            _baixar_protocolo_sanitario(session, dados.evento_id)
        elif dados.evento_id.startswith("aplic_agendada_"):
            _baixar_aplicacao_agendada(session, dados.evento_id)
    return {"marcado": True}


def _desmarcar_protocolo_iatf_realizado(session: Session, evento_id: str) -> None:
    """
    Reverte um grupo (lançamento, dia) do protocolo IATF marcado por engano —
    volta todas as aplicações do grupo para pendente (sem registro de qual
    subconjunto foi confirmado, reverter o grupo inteiro é o único
    comportamento coerente).
    """
    resto = evento_id.removeprefix("protocolo_iatf_")
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.lancamento_id == lancamento_id,
            ProtocoloIatfAplicacao.dia == dia,
            ProtocoloIatfAplicacao.realizada == True,  # noqa: E712
        )
    ).all()
    for ap in aplicacoes:
        ap.realizada = False
        ap.data_realizacao = None
        session.add(ap)
    session.commit()


@router.get("/protocolo-iatf/concluidos")
def listar_protocolo_iatf_concluidos(session: Session = Depends(get_session)) -> list[dict]:
    """Grupos (lançamento, dia) do protocolo IATF já confirmados — para desfazer, se marcado por engano."""
    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.realizada == True)  # noqa: E712
    ).all()
    lancamentos_por_id = {l.id: l for l in session.exec(select(ProtocoloIatfLancamento)).all()}
    grupos: dict[tuple[int, int], list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes:
        grupos.setdefault((ap.lancamento_id, ap.dia), []).append(ap)

    resultado = []
    for (lancamento_id, dia), aps in grupos.items():
        lancamento = lancamentos_por_id.get(lancamento_id)
        if not lancamento:
            continue
        datas_realizacao = [a.data_realizacao for a in aps if a.data_realizacao]
        resultado.append({
            "id": f"protocolo_iatf_{lancamento_id}_{dia}",
            "nome_protocolo": lancamento.nome_protocolo, "dia": dia,
            "animais": sorted((a.numero_matriz for a in aps), key=chave_numero),
            "data_realizacao": max(datas_realizacao).isoformat() if datas_realizacao else None,
        })
    resultado.sort(key=lambda r: r["data_realizacao"] or "", reverse=True)
    return resultado


@router.delete("/realizados/{evento_id}")
def desmarcar_realizado(evento_id: str, session: Session = Depends(get_session)) -> dict:
    """Desfaz a marcação de realizado — o evento volta a aparecer na agenda."""
    if evento_id.startswith("protocolo_iatf_"):
        _desmarcar_protocolo_iatf_realizado(session, evento_id)
        return {"desmarcado": True}

    existe = session.exec(select(EventoRealizado).where(EventoRealizado.evento_id == evento_id)).first()
    if existe:
        session.delete(existe)
        session.commit()
    return {"desmarcado": True}


class AgendaManualIn(BaseModel):
    data_evento: date
    descricao: str
    categoria: str = "Gestão/Financeiro"
    numero_animal: str | None = None  # CSV de números, quando vinculado a um ou mais animais
    lotes: str | None = None  # CSV de códigos de lote, quando vinculado a um ou mais lotes
    tipo_evento: str | None = None  # Compra, Venda, Serviço, Outro
    observacao: str | None = None
    recorrente: bool = False
    intervalo_dias: int | None = None
    intervalo_meses: int | None = None


@router.post("/manual")
def adicionar_evento_manual(dados: AgendaManualIn, session: Session = Depends(get_session)) -> dict:
    """Adiciona um evento manual à agenda (equivalente à aba AGENDA_MANUAL do Excel)."""
    if dados.tipo_evento and dados.tipo_evento not in TIPOS_EVENTO:
        raise HTTPException(status_code=400, detail=f"tipo_evento inválido. Use um de: {', '.join(TIPOS_EVENTO)}")
    if dados.recorrente and not dados.intervalo_dias and not dados.intervalo_meses:
        raise HTTPException(status_code=400, detail="Informe o intervalo (dias ou meses) da recorrência.")
    if dados.intervalo_dias and dados.intervalo_meses:
        raise HTTPException(status_code=400, detail="Escolha só uma frequência: dias OU meses.")
    evento = AgendaManual(
        data_evento=dados.data_evento,
        descricao=dados.descricao,
        categoria=dados.categoria,
        numero_animal=dados.numero_animal,
        lotes=dados.lotes,
        tipo_evento=dados.tipo_evento,
        observacao=dados.observacao,
        recorrente=dados.recorrente,
        intervalo_dias=dados.intervalo_dias if dados.recorrente else None,
        intervalo_meses=dados.intervalo_meses if dados.recorrente else None,
    )
    session.add(evento)
    session.commit()
    session.refresh(evento)
    return evento.model_dump()
