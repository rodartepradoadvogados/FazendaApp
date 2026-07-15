"""
Router da Agenda — calcula e retorna eventos do dia ou de um período.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import Usuario, get_current_user, tem_modulo
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, AgendamentoPesagem, Animal, AplicacaoAgendada, ColostragemBezerra, ContaGerencial, DietaLancamento, Estoque, EstoqueSemen, EventoRealizado, MovimentoEstoque, Parto,
    ProtocoloIatfAplicacao, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento, ProtocoloInducaoMedicamento,
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa, ProtocoloSanitarioLancamento, Sanidade,
    SeedFlag, Servico,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.agenda_engine import AgendaEngine, AgendaItem
from fazenda.rules.eventos_sanitarios import eventos_agenda as _eventos_sanitarios_agenda
from fazenda.rules.unidades import pode_dar_baixa_direta
from fazenda.rules.farmacia import pode_baixar_estoque
from fazenda.rules.pesagem_agenda import ocorrencias_pesagem, idade_dias

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

# Prefixos de eventos "comunicado" (aviso informativo, ex.: nova dieta) — ao
# contrário de uma atividade (alguém executa e dá baixa), um comunicado só
# informa: fica fixo enquanto vigora e some sozinho depois, sem poder ser
# marcado como realizado/excluído pelo usuário (ver marcar_realizado abaixo).
COMUNICADO_PREFIXOS = ("nova_dieta_",)

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
                apenas_admin=modelo.apenas_admin, link=modelo.link,
            ))
            session.commit()
            proxima = _proxima_ocorrencia(proxima, modelo.intervalo_dias, modelo.intervalo_meses)


_INSTRUCOES_TOUROS = (
    "Passo a passo para atualizar o banco de touros (provas NAAB):\n"
    "1) Entre no site do seu fornecedor de sêmen (ABS BullSearch, Alta, Select Sires, CRV...) "
    "e filtre/selecione os touros que você usa.\n"
    "2) Exporte a lista em Excel (.xlsx) ou CSV — geralmente há um botão 'Exportar'.\n"
    "3) Aqui no sistema: Configurações › Importar dados › 'Touros — catálogo NAAB'.\n"
    "4) Escolha o arquivo, informe a Central (ex.: Select Sires) e a Rodada da prova "
    "(ex.: Abr/2026) e clique em Enviar.\n"
    "5) Pronto: o banco de touros atualiza (nome, produção, TPI/NM$, tipo e saúde) e passa a "
    "aparecer na ficha do pai de cada animal.\n"
    "Obs.: as provas oficiais (CDCB) saem em abril, agosto e dezembro — são essas as importações "
    "que trazem números novos."
)


def seed_lembrete_touros(session: Session) -> None:
    """Cria (uma vez) o lembrete recorrente, só para o administrador, de importar
    o catálogo de touros a cada 3 meses — com o passo a passo e o link da tela de
    importação. Idempotente: guardado por flag."""
    chave = "lembrete_touros_v1"
    if session.get(SeedFlag, chave):
        return
    hoje = date.today()
    # Primeira ocorrência: dia 1º do próximo mês de trimestre (jan/abr/jul/out).
    mes = hoje.month
    prox_mes = next((m for m in (1, 4, 7, 10, 13) if m > mes), 13)
    ano = hoje.year + (1 if prox_mes == 13 else 0)
    prox_mes = 1 if prox_mes == 13 else prox_mes
    primeira = date(ano, prox_mes, 1)
    session.add(AgendaManual(
        data_evento=primeira,
        descricao="Atualizar banco de touros (provas NAAB) — importar catálogo do fornecedor",
        categoria="Atividades",
        tipo_evento="Outro",
        observacao=_INSTRUCOES_TOUROS,
        recorrente=True,
        intervalo_meses=3,
        apenas_admin=True,
        link="/configuracoes?aba=importar",
    ))
    session.add(SeedFlag(chave=chave))
    session.commit()


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

    # BST a cada 12 dias ancorado na ÚLTIMA APLICAÇÃO REAL lançada (não no
    # último serviço reprodutivo, que é só uma estimativa de reserva usada
    # quando a fazenda nunca lançou nenhuma aplicação de BST ainda). Calculado
    # ANTES do motor rodar, para que a projeção de DEL de cada animal na
    # próxima aplicação (bst_elegiveis/bst_nunca_aplicados) já use a data
    # certa — antes essa correção só acontecia depois, e nunca realimentava
    # o cálculo de elegibilidade, deixando animais entrarem cedo demais.
    # Casamento por palavra inteira (\b) — não por substring — para não achar
    # falso positivo em produtos como "carboidrato" ou "substância".
    MARCADORES_BST = re.compile(r"\b(lactotropin|boostin|bst|somatotropina)\b", re.IGNORECASE)
    sanidades_bst = [s for s in session.exec(select(Sanidade)).all() if MARCADORES_BST.search(s.produto or "")]
    datas_bst = [s.data_aplicacao for s in sanidades_bst if s.data_aplicacao]
    proxima_visita_bst_real: date | None = None
    if datas_bst:
        proxima_visita_bst_real = max(datas_bst) + timedelta(days=12)
        # A aplicação é sempre em ciclo fixo de 12 em 12 dias — se a última
        # dose+12 já ficou no passado (várias janelas puladas), avança até a
        # próxima ocorrência futura, em vez de mostrar uma data já vencida.
        while proxima_visita_bst_real <= data:
            proxima_visita_bst_real += timedelta(days=12)

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
        proxima_visita_bst_real=proxima_visita_bst_real,
    )

    # Candidatas aptas que NUNCA receberam nenhuma aplicação de BST — vaca que
    # acabou de atingir DEL 60 e ainda não entrou no ciclo de doses — mais as
    # excluídas manualmente (Animal.excluir_bst), que voltam para reanálise a
    # cada aplicação (bolinha amarela no front, ver requer_reanalise).
    animais_com_bst = {s.numero_matriz for s in sanidades_bst}
    bst_nunca_aplicados = (
        [{**b.__dict__, "requer_reanalise": False} for b in result.bst_elegiveis if b.numero_matriz not in animais_com_bst]
        + [{**b.__dict__, "requer_reanalise": True} for b in result.bst_reanalise]
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

    # Hormônios cadastrados por (lançamento, dia) + as opções de medicamento
    # (frascos em estoque) do princípio ativo de cada um, para o "qual
    # medicamento/frasco?" na hora de confirmar o dia (ex.: D9).
    from fazenda.models import MedicamentoComercial, PrincipioAtivo
    _todos_estoque = session.exec(select(Estoque)).all()
    _pa_por_nome = {(p.nome or "").strip().lower(): p for p in session.exec(select(PrincipioAtivo)).all()}

    def _opcoes_medicamento(produto: str) -> tuple[int | None, list[dict]]:
        """Dado o produto/princípio de um hormônio, resolve o princípio ativo e
        lista os frascos em estoque para o usuário escolher qual está usando."""
        item = next((e for e in _todos_estoque if (e.nome or "").strip().lower() == (produto or "").strip().lower()), None)
        pa_id = item.principio_ativo_id if item else None
        if pa_id is None:
            pa = _pa_por_nome.get((produto or "").strip().lower())
            pa_id = pa.id if pa else None
        opcoes = []
        for e in _todos_estoque:
            if pa_id is not None and e.principio_ativo_id == pa_id:
                opcoes.append({"estoque_id": e.id, "nome": e.nome, "marca": e.laboratorio,
                               "saldo": e.quantidade or 0, "unidade": e.unidade,
                               "estoque_inicializado": e.estoque_inicializado is not False})
        # Se o próprio produto é um item de estoque (sem princípio), ele é a opção.
        if not opcoes and item is not None:
            opcoes.append({"estoque_id": item.id, "nome": item.nome, "marca": item.laboratorio,
                           "saldo": item.quantidade or 0, "unidade": item.unidade,
                           "estoque_inicializado": item.estoque_inicializado is not False})
        return pa_id, opcoes

    hormonios_por_grupo: dict[tuple[int, int], list[dict]] = {}
    for h in session.exec(select(ProtocoloIatfHormonio)).all():
        pa_id, opcoes = _opcoes_medicamento(h.produto)
        hormonios_por_grupo.setdefault((h.lancamento_id, h.dia), []).append({
            "produto": h.produto, "dose": h.dose, "unidade": h.unidade, "via": h.via,
            "principio_ativo_id": pa_id, "opcoes": opcoes,
        })

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
            "hormonios": hormonios_por_grupo.get((lancamento_id, dia), []),
            "protocolo": lancamento.nome_protocolo,
        })

    # Protocolo de indução de lactação — agrupa por (lançamento, dia), igual
    # ao protocolo IATF: uma linha por dia mostrando todos os animais daquele
    # passo, com a observação de manejo (implante, adaptação na ordenha,
    # iniciar a ordenha) bem visível para o funcionário.
    lancamentos_inducao_por_id = {l.id: l for l in session.exec(select(ProtocoloInducaoLancamento)).all()}
    aplicacoes_inducao = [
        a for a in session.exec(
            select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.realizada == False)  # noqa: E712
        ).all()
        if a.data_prevista >= data
    ]
    grupos_inducao: dict[tuple[int, int], list[ProtocoloInducaoAplicacao]] = {}
    for ap in aplicacoes_inducao:
        grupos_inducao.setdefault((ap.lancamento_id, ap.dia), []).append(ap)

    eventos_inducao = []
    for (lancamento_id, dia), aps in grupos_inducao.items():
        chave = f"protocolo_inducao_{lancamento_id}_{dia}"
        if chave in realizados:
            continue
        lancamento = lancamentos_inducao_por_id.get(lancamento_id)
        if not lancamento:
            continue
        animais_grupo = sorted((a.numero_matriz for a in aps), key=chave_numero)
        eventos_inducao.append({
            "id": chave, "data": aps[0].data_prevista.isoformat(), "categoria": "Produção",
            "descricao": f"{lancamento.nome_protocolo} — D{dia}",
            "numero_animal": None, "observacao": aps[0].observacao_manejo,
            "fonte": "manual", "cor": "var(--dourado)", "ref": None,
            "tipo": "protocolo_inducao", "dia": dia, "animais": animais_grupo,
            "medicamentos": aps[0].descricao, "protocolo": lancamento.nome_protocolo,
        })

    # Eventos sanitários agendados (por época ou por evento de vida) — cada um
    # já traz o medicamento padrão para pré-preencher a Aplicação ao dar baixa.
    eventos_sanitarios = _eventos_sanitarios_agenda(session, data, realizados)

    # Aplicações programadas ("aplicado? não" / data futura) ainda não baixadas.
    # Dar baixa aqui gera a aplicação de verdade e a saída de estoque.
    aplic_agendadas = session.exec(
        select(AplicacaoAgendada).where(AplicacaoAgendada.aplicado == False)  # noqa: E712
    ).all()
    # Vacina(s) pré-parto (vindas da Secagem) formam um cartão só por animal —
    # o número do animal com o indicador "Vacina(s) pré-parto" e a lista das
    # vacinas logo abaixo — em vez de uma linha solta por vacina.
    VACINA_PRE_PARTO = "Vacina pré-parto"
    vacinas_pre_parto_rows = [a for a in aplic_agendadas if a.observacao == VACINA_PRE_PARTO]
    demais_agendadas = [a for a in aplic_agendadas if a.observacao != VACINA_PRE_PARTO]

    eventos_aplic_agendada = [{
        "id": f"aplic_agendada_{a.id}", "data": a.data.isoformat(), "categoria": "sanidade",
        "descricao": f"Aplicar {a.produto}"
        + (f" — {a.dose} {a.unidade or ''}" if a.dose is not None else "")
        + f" — matriz {a.numero_matriz}",
        "numero_animal": a.numero_matriz, "observacao": "Programada — dê baixa para aplicar e baixar o estoque.",
        "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "aplicacao_agendada",
        "produto": a.produto, "dose": a.dose, "unidade": a.unidade, "via": a.via,
    } for a in demais_agendadas if f"aplic_agendada_{a.id}" not in realizados]

    grupos_vacina_pre_parto: dict[tuple[str, date], list] = {}
    for a in vacinas_pre_parto_rows:
        grupos_vacina_pre_parto.setdefault((a.numero_matriz, a.data), []).append(a)
    eventos_vacina_pre_parto = []
    for (numero, data_evt), rows in grupos_vacina_pre_parto.items():
        chave = f"vacina_pre_parto_{numero}_{data_evt.isoformat()}"
        if chave in realizados:
            continue
        eventos_vacina_pre_parto.append({
            "id": chave, "data": data_evt.isoformat(), "categoria": "sanidade",
            "descricao": f"Vacina(s) pré-parto — matriz {numero}",
            "numero_animal": numero,
            "observacao": "\n".join(f"• {r.produto}" for r in rows),
            "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "vacina_pre_parto",
            "vacinas": [r.produto for r in rows],
        })

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
                            "link": f"/rebanho?aba=ficha&numero={cria.numero}&destacar=colostragem",
                        })
                if igg_falta:
                    chave = f"igg_pendente_{cria.numero}"
                    if chave not in realizados:
                        eventos_colostro.append({
                            "id": chave, "data": dia_seguinte, "categoria": "sanidade",
                            "descricao": f"Fazer exame de sangue (IgG) — bezerra {cria.numero}",
                            "numero_animal": cria.numero, "observacao": "Teste de sangue (Brix do soro) não lançado — registre na ficha do animal.",
                            "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "igg_pendente",
                            "link": f"/rebanho?aba=ficha&numero={cria.numero}&destacar=igg",
                        })

    # Nova dieta: alerta um dia antes ("para amanhã") e no dia ("hoje"), com
    # link para abrir a dieta. A chave inclui a data de referência → o alerta
    # de véspera e o do dia são eventos distintos (marcar um não some o outro).
    eventos_nova_dieta = []
    for d in session.exec(
        select(DietaLancamento).where(DietaLancamento.data_efetivo_encerramento == None)  # noqa: E711
    ).all():
        if d.data_abertura in (data, data + timedelta(days=1)):
            hoje_alerta = d.data_abertura == data
            chave = f"nova_dieta_{d.id}_{data.isoformat()}"
            if chave in realizados:
                continue
            eventos_nova_dieta.append({
                "id": chave, "data": d.data_abertura.isoformat(), "categoria": "alimentacao",
                "descricao": f"Atenção — nova dieta {'HOJE' if hoje_alerta else 'para AMANHÃ'} — lote {d.lote}",
                "numero_animal": None, "observacao": "Toque para ver a nova dieta (produtos, por trato e kg no vagão).",
                "fonte": "auto", "cor": "var(--dourado)", "ref": str(d.id), "tipo": "nova_dieta", "lote": d.lote,
                "comunicado": True,
            })

    # Pesagem do rebanho (acompanhamento da evolução de peso): cada agendamento
    # (fase) gera um lembrete na Agenda nos dias configurados (periodicidade +
    # dia da semana), com a contagem de animais da faixa de idade-alvo.
    eventos_pesagem = []
    agend_pesagem = session.exec(select(AgendamentoPesagem).where(AgendamentoPesagem.ativo == True)).all()  # noqa: E712
    if agend_pesagem:
        # Todos os animais ativos (inclui bezerros de ambos os sexos) com nascimento.
        todos_ativos = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
        animais_pesagem = [a for a in todos_ativos if not a.eh_semen]
        for ag in agend_pesagem:
            for dref in ocorrencias_pesagem(ag.data_referencia, ag.frequencia_valor, ag.frequencia_unidade,
                                            ag.dia_semana, data, data + timedelta(days=dias)):
                chave = f"pesagem_{ag.id}_{dref.isoformat()}"
                if chave in realizados:
                    continue
                # Conta os animais-alvo na data da pesagem (por idade e/ou categoria).
                alvo = []
                for a in animais_pesagem:
                    idade = idade_dias(a.data_nasc, dref)
                    if ag.idade_min_dias is not None and (idade is None or idade < ag.idade_min_dias):
                        continue
                    if ag.idade_max_dias is not None and (idade is None or idade > ag.idade_max_dias):
                        continue
                    if ag.categoria_alvo and (a.categoria_abrev or "").strip().lower() != ag.categoria_alvo.strip().lower():
                        continue
                    alvo.append(a.numero)
                if not alvo and (ag.idade_min_dias is not None or ag.idade_max_dias is not None or ag.categoria_alvo):
                    continue  # fase com alvo definido mas sem animais hoje → não polui a agenda
                eventos_pesagem.append({
                    "id": chave, "data": dref.isoformat(), "categoria": "Produção",
                    "descricao": f"Pesagem — {ag.nome}" + (f" ({len(alvo)} animais)" if alvo else ""),
                    "numero_animal": None, "observacao": "Pesagem corporal do rebanho (evolução de peso). Toque para lançar.",
                    "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "pesagem_rebanho",
                    "animais": sorted(alvo, key=chave_numero),
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
            "apenas_admin": getattr(e, "apenas_admin", False),
            "link": getattr(e, "link", None),
        }
        for e in eventos
    ] + eventos_dieta + eventos_protocolo + eventos_iatf + eventos_inducao + eventos_sanitarios + eventos_aplic_agendada + eventos_vacina_pre_parto + eventos_semen + eventos_colostro + eventos_nova_dieta + eventos_pesagem
    eh_admin = usuario.papel == "admin"
    eventos_visiveis = [
        e for e in eventos_visiveis
        if (MODULO_POR_CATEGORIA.get(e["categoria"], None) is None or MODULO_POR_CATEGORIA[e["categoria"]] in modulos)
        and (eh_admin or not e.get("apenas_admin"))  # eventos só-admin ocultos para os demais
    ]
    tem_financeiro = "financeiro" in modulos
    tem_reproducao = "reproducao" in modulos
    tem_estoque = tem_modulo(usuario, "estoque")

    # Alertas de estoque (negativo/abaixo do mínimo) — SEMPRE calculado (não
    # depende do opt-in "exibir necessidade de compra na agenda" por item, que
    # só vira um evento cronológico simples em Gestão/Financeiro). Aqui é uma
    # visão de "informações" da Agenda, incondicional para quem tem acesso ao
    # módulo de estoque. Só considera itens estocáveis (None/True).
    estoque_negativo = []
    estoque_abaixo_minimo = []
    if tem_estoque:
        for item in estoque:
            if item.get("estocavel") is False:
                continue
            qtd = item.get("quantidade")
            if qtd is None:
                continue
            minimo = item.get("estoque_minimo")
            linha = {"nome": item["nome"], "quantidade": qtd, "estoque_minimo": minimo, "unidade": item.get("unidade")}
            if qtd < 0:
                estoque_negativo.append(linha)
            elif minimo is not None and qtd < minimo:
                estoque_abaixo_minimo.append(linha)

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
        # "ja_aplicado_antes": indica se o animal já recebeu alguma aplicação de
        # BST no passado (produto casa MARCADORES_BST em Sanidade) — False =
        # a próxima aplicação seria a primeira vez desse animal.
        "bst_elegiveis": [{**b.__dict__, "ja_aplicado_antes": b.numero_matriz in animais_com_bst} for b in result.bst_elegiveis] if tem_reproducao else [],
        "bst_excluidos": [{**b.__dict__, "ja_aplicado_antes": b.numero_matriz in animais_com_bst} for b in result.bst_excluidos] if tem_reproducao else [],
        "bst_nunca_aplicados": [{**b, "ja_aplicado_antes": False} for b in bst_nunca_aplicados] if tem_reproducao else [],
        "contas_a_pagar": result.contas_a_pagar if tem_financeiro else [],
        "estoque_negativo": estoque_negativo,
        "estoque_abaixo_minimo": estoque_abaixo_minimo,
        "eventos": eventos_visiveis,
        "totais": {
            "candidatas_iatf": len(result.candidatas_iatf) if tem_reproducao else 0,
            "bst_elegiveis": len(result.bst_elegiveis) if tem_reproducao else 0,
            "bst_nunca_aplicados": len(bst_nunca_aplicados) if tem_reproducao else 0,
            "contas_a_pagar": len(result.contas_a_pagar) if tem_financeiro else 0,
            "eventos": len(eventos_visiveis),
        },
    }


class MedicamentoIatfIn(BaseModel):
    produto: str  # nome do medicamento/frasco escolhido (item de estoque)
    estoque_id: int | None = None  # "qual frasco?" — abate deste item específico
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None


class RealizadoIn(BaseModel):
    evento_id: str
    animais: list[str] | None = None  # subconjunto opcional (protocolo_iatf) — None = todos do grupo
    # Medicamentos efetivamente aplicados neste dia do protocolo IATF, com o
    # frasco escolhido ("qual medicamento você está usando?"). Quando vem, é ele
    # que gera a aplicação em Sanidade e a baixa; sem ele, cai nos hormônios
    # cadastrados no lançamento (comportamento anterior).
    medicamentos: list[MedicamentoIatfIn] | None = None


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
        protocolo_sanitario_lancamento_id=lancamento.id,
    ))

    estoque_item = session.exec(select(Estoque).where(Estoque.nome == produto)).first()
    if estoque_item and estoque_item.estocavel is not False and pode_baixar_estoque(estoque_item) and pode_dar_baixa_direta(etapa.unidade, estoque_item.unidade):
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
    if ag.dose and estoque_item and estoque_item.estocavel is not False and pode_baixar_estoque(estoque_item) and pode_dar_baixa_direta(ag.unidade, estoque_item.unidade):
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


def _baixar_vacina_pre_parto(session: Session, evento_id: str) -> None:
    """Confirma TODAS as vacinas pré-parto pendentes daquele cartão (mesmo
    animal + mesma data) de uma vez — cada uma vira um registro de Sanidade."""
    resto = evento_id.removeprefix("vacina_pre_parto_")
    numero_matriz, data_str = resto.rsplit("_", 1)
    data_evt = date.fromisoformat(data_str)
    rows = session.exec(
        select(AplicacaoAgendada).where(
            AplicacaoAgendada.numero_matriz == numero_matriz,
            AplicacaoAgendada.data == data_evt,
            AplicacaoAgendada.observacao == "Vacina pré-parto",
            AplicacaoAgendada.aplicado == False,  # noqa: E712
        )
    ).all()
    hoje = date.today()
    for ag in rows:
        ag.aplicado = True
        ag.data_aplicacao = hoje
        session.add(ag)
        session.add(Sanidade(
            numero_matriz=ag.numero_matriz, data_aplicacao=hoje, produto=ag.produto,
            via=ag.via, responsavel=ag.responsavel, obs=ag.observacao,
        ))
    session.commit()


def _marcar_protocolo_iatf_realizado(
    session: Session, evento_id: str, animais: list[str] | None,
    medicamentos: list["MedicamentoIatfIn"] | None = None,
) -> None:
    """
    Marca a(s) aplicação(ões) de um grupo (lançamento, dia) do protocolo IATF
    como realizadas. Sem `animais`, marca o grupo inteiro; com `animais`,
    confirma só esse subconjunto — os demais continuam pendentes no grupo.

    `medicamentos` (opcional): os frascos que o usuário escolheu na hora de
    confirmar o dia ("qual medicamento?"). Quando vem, é ele que gera a
    aplicação em Sanidade e a baixa (abatendo do frasco pelo estoque_id); sem
    ele, usa os hormônios cadastrados no lançamento.
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

    # Aplicados: o que o usuário escolheu ao confirmar (com o frasco), OU, na
    # falta disso, os hormônios cadastrados no lançamento. Normaliza os dois
    # numa lista de dicts {produto, dose, unidade, via, estoque_id}.
    if medicamentos:
        aplicados = [
            {"produto": m.produto, "dose": m.dose, "unidade": m.unidade, "via": m.via, "estoque_id": m.estoque_id}
            for m in medicamentos if (m.produto or "").strip()
        ]
    else:
        hormonios = session.exec(
            select(ProtocoloIatfHormonio).where(
                ProtocoloIatfHormonio.lancamento_id == lancamento_id,
                ProtocoloIatfHormonio.dia == dia,
            )
        ).all()
        aplicados = [
            {"produto": h.produto, "dose": h.dose, "unidade": h.unidade, "via": h.via, "estoque_id": None}
            for h in hormonios
        ]

    for ap in aplicacoes:
        ap.realizada = True
        ap.data_realizacao = hoje
        session.add(ap)
        for m in aplicados:
            session.add(Sanidade(
                numero_matriz=ap.numero_matriz, data_aplicacao=hoje, produto=m["produto"],
                dose=m["dose"], unidade=m["unidade"], via=m["via"], responsavel=responsavel,
                obs=f"Protocolo IATF — D{dia}",
                protocolo_iatf_lancamento_id=lancamento_id,
            ))

    # Baixa de estoque: uma vez por medicamento, dose × nº de vacas confirmadas.
    # Abate do frasco escolhido (estoque_id) ou, na falta, do item pelo nome.
    n_vacas = len(aplicacoes)
    if n_vacas:
        for m in aplicados:
            if not m["dose"]:
                continue
            estoque_item = None
            if m["estoque_id"] is not None:
                estoque_item = session.get(Estoque, m["estoque_id"])
            if estoque_item is None:
                estoque_item = session.exec(select(Estoque).where(Estoque.nome == m["produto"])).first()
            if not estoque_item or estoque_item.estocavel is False:
                continue
            if not pode_baixar_estoque(estoque_item):
                continue
            if not pode_dar_baixa_direta(m["unidade"], estoque_item.unidade):
                continue
            total = m["dose"] * n_vacas
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


def _marcar_protocolo_inducao_realizado(session: Session, evento_id: str, animais: list[str] | None) -> None:
    """
    Marca a(s) aplicação(ões) de um grupo (lançamento, dia) da indução de
    lactação como realizadas. Sem `animais`, marca o grupo inteiro; com
    `animais`, confirma só esse subconjunto. Etapas de manejo/dispositivo
    (sem medicamento) só marcam a aplicação — não geram Sanidade nem baixa.
    """
    resto = evento_id.removeprefix("protocolo_inducao_")
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloInducaoAplicacao).where(
            ProtocoloInducaoAplicacao.lancamento_id == lancamento_id,
            ProtocoloInducaoAplicacao.dia == dia,
            ProtocoloInducaoAplicacao.realizada == False,  # noqa: E712
        )
    ).all()
    if animais is not None:
        alvo = set(animais)
        aplicacoes = [a for a in aplicacoes if a.numero_matriz in alvo]

    hoje = date.today()
    lancamento = session.get(ProtocoloInducaoLancamento, lancamento_id)
    responsavel = getattr(lancamento, "responsavel", None)

    medicamentos = session.exec(
        select(ProtocoloInducaoMedicamento).where(
            ProtocoloInducaoMedicamento.lancamento_id == lancamento_id,
            ProtocoloInducaoMedicamento.dia == dia,
        )
    ).all()

    for ap in aplicacoes:
        ap.realizada = True
        ap.data_realizacao = hoje
        session.add(ap)
        for m in medicamentos:
            session.add(Sanidade(
                numero_matriz=ap.numero_matriz, data_aplicacao=hoje, produto=m.produto,
                dose=m.dose, unidade=m.unidade, via=m.via, responsavel=responsavel,
                obs=f"Indução de lactação — D{dia}",
            ))

    # Baixa de estoque: uma vez por medicamento, dose × nº de vacas confirmadas
    # (item cadastrado por nome exato — combina automaticamente quando o
    # princípio do protocolo já é um item de estoque real).
    n_vacas = len(aplicacoes)
    if n_vacas:
        for m in medicamentos:
            if not m.dose:
                continue
            estoque_item = session.exec(select(Estoque).where(Estoque.nome == m.produto)).first()
            if not estoque_item or estoque_item.estocavel is False:
                continue
            if not pode_baixar_estoque(estoque_item):
                continue
            if not pode_dar_baixa_direta(m.unidade, estoque_item.unidade):
                continue
            total = m.dose * n_vacas
            estoque_item.quantidade = (estoque_item.quantidade or 0) - total
            if estoque_item.estoque_minimo is not None:
                estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
            estoque_item.atualizado_em = datetime.utcnow()
            session.add(estoque_item)
            session.add(MovimentoEstoque(
                nome_item=estoque_item.nome, movimento="Aplicação", quantidade=total,
                unidade=estoque_item.unidade, data_movimento=hoje,
                observacao=f"Indução de lactação — D{dia} — {n_vacas} vaca(s)",
            ))
    session.commit()


def _desmarcar_protocolo_inducao_realizado(session: Session, evento_id: str) -> None:
    """Reverte um grupo (lançamento, dia) da indução de lactação marcado por engano."""
    resto = evento_id.removeprefix("protocolo_inducao_")
    lancamento_id_str, dia_str = resto.rsplit("_", 1)
    lancamento_id, dia = int(lancamento_id_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloInducaoAplicacao).where(
            ProtocoloInducaoAplicacao.lancamento_id == lancamento_id,
            ProtocoloInducaoAplicacao.dia == dia,
            ProtocoloInducaoAplicacao.realizada == True,  # noqa: E712
        )
    ).all()
    for ap in aplicacoes:
        ap.realizada = False
        ap.data_realizacao = None
        session.add(ap)
    session.commit()


@router.post("/realizados")
def marcar_realizado(dados: RealizadoIn, session: Session = Depends(get_session)) -> dict:
    """Marca um evento como realizado — ele sai da agenda (pendentes e futuros)."""
    if dados.evento_id.startswith(COMUNICADO_PREFIXOS):
        raise HTTPException(status_code=400, detail="Comunicados não podem ser marcados como realizados — eles somem sozinhos no dia seguinte.")
    if dados.evento_id.startswith("protocolo_iatf_"):
        _marcar_protocolo_iatf_realizado(session, dados.evento_id, dados.animais, dados.medicamentos)
        return {"marcado": True}
    if dados.evento_id.startswith("protocolo_inducao_"):
        _marcar_protocolo_inducao_realizado(session, dados.evento_id, dados.animais)
        return {"marcado": True}

    existe = session.exec(select(EventoRealizado).where(EventoRealizado.evento_id == dados.evento_id)).first()
    if not existe:
        session.add(EventoRealizado(evento_id=dados.evento_id))
        session.commit()
        if dados.evento_id.startswith("protocolo_sanitario_"):
            _baixar_protocolo_sanitario(session, dados.evento_id)
        elif dados.evento_id.startswith("aplic_agendada_"):
            _baixar_aplicacao_agendada(session, dados.evento_id)
        elif dados.evento_id.startswith("vacina_pre_parto_"):
            _baixar_vacina_pre_parto(session, dados.evento_id)
    return {"marcado": True}


class AplicarBstIn(BaseModel):
    numeros_matriz: list[str]
    data_aplicacao: date
    produto: str = "Lactotropin"
    dose: float | None = None
    unidade: str | None = None
    responsavel: str | None = None


@router.post("/bst/aplicar")
def aplicar_bst_lote(
    dados: AplicarBstIn, session: Session = Depends(get_session),
) -> dict:
    """Confirma a aplicação de BST (Lactotropin/Boostin) na visita de hoje para
    os animais informados — grava um registro de Sanidade por animal (e dá
    baixa de estoque quando o produto casa com um item cadastrado). A próxima
    visita (12 dias, ou o intervalo cadastrado em Configurações) recalcula
    sozinha a partir da data de aplicação mais recente, já usada por /agenda."""
    from fazenda.rules.parametros import get_param

    for numero in dados.numeros_matriz:
        session.add(Sanidade(
            numero_matriz=numero, data_aplicacao=dados.data_aplicacao, produto=dados.produto,
            dose=dados.dose, unidade=dados.unidade, responsavel=dados.responsavel, atividade="BST",
        ))
        if dados.dose:
            estoque_item = session.exec(select(Estoque).where(Estoque.nome == dados.produto)).first()
            if estoque_item and estoque_item.estocavel is not False and dados.unidade and pode_dar_baixa_direta(dados.unidade, estoque_item.unidade):
                estoque_item.quantidade = (estoque_item.quantidade or 0) - dados.dose
                if estoque_item.estoque_minimo is not None:
                    estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
                estoque_item.atualizado_em = datetime.utcnow()
                session.add(estoque_item)
    session.commit()

    intervalo = get_param("intervalo_bst", 12)
    return {
        "aplicados": len(dados.numeros_matriz),
        "intervalo_dias": intervalo,
        "proxima_aplicacao_calculada": (dados.data_aplicacao + timedelta(days=intervalo)).isoformat(),
    }


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


@router.get("/protocolo-inducao-lactacao/concluidos")
def listar_protocolo_inducao_concluidos(session: Session = Depends(get_session)) -> list[dict]:
    """Grupos (lançamento, dia) da indução de lactação já confirmados — para desfazer, se marcado por engano."""
    aplicacoes = session.exec(
        select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.realizada == True)  # noqa: E712
    ).all()
    lancamentos_por_id = {l.id: l for l in session.exec(select(ProtocoloInducaoLancamento)).all()}
    grupos: dict[tuple[int, int], list[ProtocoloInducaoAplicacao]] = {}
    for ap in aplicacoes:
        grupos.setdefault((ap.lancamento_id, ap.dia), []).append(ap)

    resultado = []
    for (lancamento_id, dia), aps in grupos.items():
        lancamento = lancamentos_por_id.get(lancamento_id)
        if not lancamento:
            continue
        datas_realizacao = [a.data_realizacao for a in aps if a.data_realizacao]
        resultado.append({
            "id": f"protocolo_inducao_{lancamento_id}_{dia}",
            "nome_protocolo": lancamento.nome_protocolo, "dia": dia,
            "animais": sorted((a.numero_matriz for a in aps), key=chave_numero),
            "data_realizacao": max(datas_realizacao).isoformat() if datas_realizacao else None,
        })
    resultado.sort(key=lambda r: r["data_realizacao"] or "", reverse=True)
    return resultado


@router.delete("/realizados/{evento_id}")
def desmarcar_realizado(evento_id: str, session: Session = Depends(get_session)) -> dict:
    """Desfaz a marcação de realizado — o evento volta a aparecer na agenda."""
    if evento_id.startswith(COMUNICADO_PREFIXOS):
        raise HTTPException(status_code=400, detail="Comunicados não podem ser excluídos — eles somem sozinhos no dia seguinte.")
    if evento_id.startswith("protocolo_iatf_"):
        _desmarcar_protocolo_iatf_realizado(session, evento_id)
        return {"desmarcado": True}
    if evento_id.startswith("protocolo_inducao_"):
        _desmarcar_protocolo_inducao_realizado(session, evento_id)
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
def adicionar_evento_manual(dados: AgendaManualIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
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
        usuario_id=user.id,
    )
    session.add(evento)
    session.commit()
    session.refresh(evento)
    return evento.model_dump()
