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

from fazenda.auth import Usuario, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita, tem_modulo
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, AgendamentoPesagem, Animal, AplicacaoAgendada, CalendarioSanitario, ColostragemBezerra, ContaGerencial,
    CronogramaSanitario, DietaLancamento, Diaria,
    DiariaAuditoria, DiariaDia, Estoque, EstoqueSemen, EventoRealizado, Lote, MedicamentoComercial, ParametroSugestaoMovimentacao, Parto,
    Patrimonio, Pessoa, PrincipioAtivo, ProtocoloIatfAplicacao, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento, ProtocoloInducaoMedicamento,
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa, ProtocoloSanitarioLancamento, Sanidade,
    Secagem, SeedFlag, Servico,
)
from fazenda.api.routers.lotes import coletar_dados_criterios
from fazenda.ordenacao import chave_numero
from fazenda.rules.agenda_engine import AgendaEngine, AgendaItem
from fazenda.rules.eventos_sanitarios import eventos_agenda as _eventos_sanitarios_agenda
from fazenda.rules import cronograma_sanitario as _cronograma_sanitario_rules
from fazenda.rules.cronograma_sanitario import PREFIXO_CRONOGRAMA as _PREFIXO_CRONOGRAMA, CronogramaError
from fazenda.rules.cura_protocolo import protocolo_terminado
from fazenda.rules.protocolo_customizado import (
    eventos_agenda as _eventos_protocolo_custom_agenda,
    marcar_realizado as _marcar_protocolo_custom_realizado,
    desmarcar_realizado as _desmarcar_protocolo_custom_realizado,
    PREFIXO_EVENTO as PREFIXO_PROTOCOLO_CUSTOM,
    JANELA_ATRASO_DIAS as JANELA_ATRASO_PROTOCOLO_DIAS,
)
from fazenda.rules.lida import (
    eventos_agenda as _eventos_lida_agenda,
    marcar_realizado as _marcar_lida_realizado,
    desmarcar_realizado as _desmarcar_lida_realizado,
    PREFIXO_EVENTO as PREFIXO_LIDA,
)
from fazenda.rules.lote_criterios import lote_tem_criterio, sugerir_movimentacoes
from fazenda.rules import estoque_baixa
from fazenda.rules.pesagem_agenda import ocorrencias_pesagem, idade_dias
from fazenda.rules.nomenclatura_protocolo import nome_curto
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro
from fazenda.rules.parametros import bst_ajuste_ancora_data, intervalo_bst, minimos_semen_por_tipo, patrimonio_atualizacao_valor_mercado_meses
from fazenda.rules.patrimonio import proxima_atualizacao_valor_mercado, status_manutencao

router = APIRouter(prefix="/agenda", tags=["agenda"])

# Reconhece uma aplicação como BST pelo nome do produto — casamento por
# palavra inteira (\b), não substring, para não achar falso positivo em
# produtos como "carboidrato" ou "substância". Usado tanto para ancorar a
# "próxima visita BST" na última aplicação real quanto para saber quando uma
# aplicação confirmada deve limpar Animal.aguardando_nova_aplicacao_bst.
MARCADORES_BST = re.compile(r"\b(lactotropi[nm]|boostin|bst|somatotropina)\b", re.IGNORECASE)

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
    "Rebanho": "rebanho",
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
                apenas_admin=modelo.apenas_admin, link=modelo.link, fazenda_id=modelo.fazenda_id,
            ))
            session.commit()
            proxima = _proxima_ocorrencia(proxima, modelo.intervalo_dias, modelo.intervalo_meses)


def _gerar_auditorias_diarias(session: Session) -> None:
    """
    Para cada Diária com `auditar_periodicamente` ligado, cria (uma vez por
    período fechado — idempotente por periodo_inicio/periodo_fim) a pendência
    que a Agenda vai perguntar: "o diarista trabalhou os N dias do período?".
    - semanal: dispara no dia da semana escolhido (`dia_semana_auditoria`),
      perguntando pelos 7 dias terminados ontem.
    - intervalo_dias: dispara a cada N dias corridos desde o fim do último
      período já criado (ou desde o início da diária, se ainda não houve
      nenhum) — em loop, para recuperar períodos perdidos se o app ficou
      fora do ar por mais de um ciclo.
    - mensal: dispara todo dia 1º, perguntando pelo mês calendário anterior.
    """
    hoje = date.today()
    diarias = session.exec(
        select(Diaria).where(
            Diaria.status == "ativo", Diaria.auditar_periodicamente == True,  # noqa: E712
            Diaria.controle_por_dia_desde.is_(None),
        )
    ).all()
    for d in diarias:
        freq = d.frequencia_auditoria or "semanal"
        periodos: list[tuple[date, date]] = []
        if freq == "semanal":
            dia_semana = d.dia_semana_auditoria if d.dia_semana_auditoria is not None else 0
            if hoje.weekday() == dia_semana:
                fim = hoje - timedelta(days=1)
                periodos.append((fim - timedelta(days=6), fim))
        elif freq == "intervalo_dias":
            intervalo = d.intervalo_dias_auditoria or 7
            ultima = session.exec(
                select(DiariaAuditoria).where(DiariaAuditoria.diaria_id == d.id).order_by(DiariaAuditoria.periodo_fim.desc())
            ).first()
            base = ultima.periodo_fim if ultima else (d.data_inicio - timedelta(days=1))
            fim = base + timedelta(days=intervalo)
            while fim < hoje:
                periodos.append((base + timedelta(days=1), fim))
                base = fim
                fim = base + timedelta(days=intervalo)
        elif freq == "mensal":
            if hoje.day == 1:
                ultimo_dia_mes_passado = hoje.replace(day=1) - timedelta(days=1)
                periodos.append((ultimo_dia_mes_passado.replace(day=1), ultimo_dia_mes_passado))
        for periodo_inicio, periodo_fim in periodos:
            if periodo_inicio < d.data_inicio:
                periodo_inicio = d.data_inicio
            if periodo_inicio > periodo_fim:
                continue
            ja_existe = session.exec(
                select(DiariaAuditoria).where(
                    DiariaAuditoria.diaria_id == d.id,
                    DiariaAuditoria.periodo_inicio == periodo_inicio,
                    DiariaAuditoria.periodo_fim == periodo_fim,
                )
            ).first()
            if ja_existe:
                continue
            session.add(DiariaAuditoria(
                diaria_id=d.id, periodo_inicio=periodo_inicio, periodo_fim=periodo_fim, fazenda_id=d.fazenda_id,
            ))
            session.commit()


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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Calcula a agenda preditiva para a data informada (padrão: hoje).
    `dias` é a janela de contas a pagar/receber (padrão 10, o front pede mais
    quando o usuário amplia o filtro "Até").
    Retorna candidatas IATF, checagem de hormônios, BST e todos os eventos.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    _gerar_agenda_recorrente(session)
    _gerar_auditorias_diarias(session)
    # Toda a base da agenda é escopada pela fazenda atual — sem isso a tela
    # mais usada do sistema misturava animal, serviço, parto, estoque e
    # financeiro de fazendas diferentes no mesmo cálculo.
    #
    # Filtro ESTRITO — usado inclusive nas tabelas de protocolo de indução de
    # lactação (ProtocoloInducaoLancamento/Aplicacao/Medicamento), que até o
    # PR claude/fazenda-id-raiz precisavam de uma variante tolerante a
    # `fazenda_id IS NULL` (`_da_fazenda_tolerante`, removida): um lançamento
    # gravado por rota de escrita que não resolvia a fazenda (token legado,
    # usuário sem fazenda vinculada, chamada fora do ciclo HTTP — ver
    # fazenda.auth.get_fazenda_id_escrita) nascia com `fazenda_id` NULO e um
    # `== fazenda_id` estrito nunca casa com NULL, então a etapa (ex.: D6 de
    # uma indução) sumia da Agenda sem sumir da Central de Protocolos (que já
    # tolerava NULL) — o sintoma que abriu este PR. A tolerância voltou a
    # estrita só depois de dois reforços: (1) toda rota de escrita passou a
    # recusar gravar `fazenda_id` nulo (`get_fazenda_id_escrita`) e (2) a
    # migração 029227481e9e preencheu o histórico que já tinha ficado nulo —
    # sem isso, voltar ao filtro estrito faria o dado legado desaparecer.
    def _da_fazenda(query, modelo):
        if fazenda_id is None:
            return query
        return query.where(modelo.fazenda_id == fazenda_id)

    animais = [
        _model_to_dict(a)
        for a in session.exec(_da_fazenda(select(Animal).where(Animal.ativo == True), Animal)).all()  # noqa: E712
        if not a.eh_semen and a.sexo != "M"
    ]
    servicos_ult = [
        _model_to_dict(s) for s in session.exec(
            _da_fazenda(select(Servico).where(Servico.ult_ocorrencia == 1), Servico)
        ).all()
    ]
    partos = [_model_to_dict(p) for p in session.exec(_da_fazenda(select(Parto), Parto)).all()]
    # Alimenta o DEL AO VIVO no motor (ver AgendaEngine.calcular, param
    # `secagens`) — sem isso, Secagem/Pré-parto e o DEL usado no BST ficavam
    # presos ao `Animal.del_dias` congelado no último GERAL.csv.
    secagens = [_model_to_dict(s) for s in session.exec(_da_fazenda(select(Secagem), Secagem)).all()]
    estoque = [_model_to_dict(e) for e in session.exec(_da_fazenda(select(Estoque), Estoque)).all()]
    # Só a janela que agenda_engine.calcular() de fato usa (contas_a_pagar
    # filtra por data_referencia <= data_vencimento <= data_referencia+dias) —
    # antes lia a tabela inteira (todo o histórico de contas da fazenda) e
    # descartava o resto em Python a cada chamada da Agenda.
    contas = [
        _model_to_dict(c) for c in session.exec(
            _da_fazenda(
                select(ContaGerencial).where(
                    ContaGerencial.data_vencimento >= data,
                    ContaGerencial.data_vencimento <= data + timedelta(days=dias),
                ),
                ContaGerencial,
            )
        ).all()
    ]
    # Cadastro de lotes (identifica qual é o lote "Pré-parto" pela flag real —
    # ver AgendaEngine.calcular, param `lotes`) para não repetir o alerta
    # "Pré-parto" de quem já foi movido para esse lote.
    lotes = [_model_to_dict(l) for l in session.exec(_da_fazenda(select(Lote), Lote)).all()]
    query_manuais = select(AgendaManual)
    if fazenda_id is not None:
        query_manuais = query_manuais.where(AgendaManual.fazenda_id.in_((fazenda_id, None)))
    manuais = [_model_to_dict(m) for m in session.exec(query_manuais).all()]

    # BST a cada intervalo_bst() dias ancorado na ÚLTIMA APLICAÇÃO REAL lançada
    # (não no último serviço reprodutivo, que é só uma estimativa de reserva
    # usada quando a fazenda nunca lançou nenhuma aplicação de BST ainda).
    # Calculado ANTES do motor rodar, para que a projeção de DEL de cada
    # animal na próxima aplicação (bst_elegiveis/bst_nunca_aplicados) já use a
    # data certa — antes essa correção só acontecia depois, e nunca
    # realimentava o cálculo de elegibilidade, deixando animais entrarem cedo
    # demais.
    sanidades_bst = [
        s for s in session.exec(_da_fazenda(select(Sanidade), Sanidade)).all()
        if s.atividade == "BST" or MARCADORES_BST.search(s.produto or "")
    ]
    datas_bst = [s.data_aplicacao for s in sanidades_bst if s.data_aplicacao]
    intervalo_bst_dias = intervalo_bst()
    # `bst_ajuste_ancora_data` é o override manual gravado por
    # POST /producao/bst/ajustar-proxima-aplicacao (opção "considerar essa
    # nova data a referência") — só vale enquanto for mais recente que a
    # última aplicação real; assim que uma aplicação real mais nova é
    # lançada, ela retoma a âncora naturalmente, sem precisar limpar nada.
    ancora_bst = max(datas_bst) if datas_bst else None
    ancora_manual = bst_ajuste_ancora_data()
    if ancora_manual is not None and (ancora_bst is None or ancora_manual > ancora_bst):
        ancora_bst = ancora_manual
    proxima_visita_bst_real: date | None = None
    if ancora_bst is not None:
        proxima_visita_bst_real = ancora_bst + timedelta(days=intervalo_bst_dias)
        # A aplicação é sempre em ciclo fixo — se a última dose+intervalo já
        # ficou no passado (várias janelas puladas), avança até a próxima
        # ocorrência futura, em vez de mostrar uma data já vencida. Usa "<"
        # (não "<="): quando a próxima aplicação cai exatamente hoje, ela deve
        # PERMANECER hoje — antes, o "<=" empurrava a data de hoje para a
        # janela seguinte e a aplicação do dia sumia da Agenda.
        while proxima_visita_bst_real < data:
            proxima_visita_bst_real += timedelta(days=intervalo_bst_dias)

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
        lotes=lotes,
        secagens=secagens,
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
    query_realizados = select(EventoRealizado)
    if fazenda_id is not None:
        query_realizados = query_realizados.where(EventoRealizado.fazenda_id.in_((fazenda_id, None)))
    realizados = {r.evento_id for r in session.exec(query_realizados).all()}
    eventos = [e for e in result.eventos if e.chave not in realizados]

    # Compromisso de agenda para o dia da aplicação de BST — antes disso a
    # "próxima aplicação" só existia como número informativo (proxima_visita_bst)
    # e nos indicadores/tabelas aptos-excluídos-nunca aplicados, sem nunca virar
    # um evento cronológico de verdade no dia certo. Carrega os números dos
    # animais direto no evento (aptas/incluir no próximo/inaptas) para que o
    # app também consiga mostrar as três listas sem precisar de outra chamada.
    eventos_bst = []
    if proxima_visita_bst_real is not None and proxima_visita_bst_real == data:
        total_aptos = len(result.bst_elegiveis)
        total_incluir = len(bst_nunca_aplicados)
        total_inaptos = len(result.bst_excluidos)
        chave_bst = f"bst_aplicacao_{data.isoformat()}"
        if chave_bst not in realizados:
            eventos_bst.append({
                "id": chave_bst, "data": data.isoformat(), "categoria": "Reprodutivo",
                "descricao": f"Aplicação de BST hoje — {total_aptos} apta(s), {total_incluir} para incluir no próximo BST",
                "numero_animal": None,
                "observacao": f"Vacas em lactação inaptas (não elegíveis): {total_inaptos}. Toque para ver as listas.",
                "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "bst_aplicacao",
                "aptas": sorted((b.numero_matriz for b in result.bst_elegiveis), key=chave_numero),
                "incluir_proximo": sorted((b["numero_matriz"] for b in bst_nunca_aplicados), key=chave_numero),
                "inaptas": sorted((b.numero_matriz for b in result.bst_excluidos), key=chave_numero),
            })

    # Dietas ativas com encerramento previsto: evento de análise (chave própria,
    # fora do AgendaEngine para não mexer no cálculo delicado já testado dele).
    dietas_para_analise = session.exec(
        _da_fazenda(select(DietaLancamento).where(
            DietaLancamento.data_efetivo_encerramento == None,  # noqa: E711
            DietaLancamento.data_prevista_encerramento != None,  # noqa: E711
        ), DietaLancamento)
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
        _da_fazenda(select(ProtocoloSanitarioAplicacao).where(ProtocoloSanitarioAplicacao.realizada == False), ProtocoloSanitarioAplicacao)  # noqa: E712
    ).all()
    # ProtocoloSanitarioEtapa nunca grava fazenda_id (é o "molde" da etapa —
    # criado em cadastro/protocolos_sanitarios.py sem esse campo, escopado
    # indiretamente via protocolo_id -> ProtocoloSanitario, que esse sim tem
    # fazenda_id de verdade); filtrar aqui por _da_fazenda excluía TODAS as
    # etapas, já que a coluna sempre está NULL (regressão do PR #467/#468 —
    # não repetir). Em vez de ler a tabela inteira (todas as etapas de TODAS
    # as fazendas-cliente), busca só os ids que `aplicacoes_pendentes` (essa
    # sim corretamente escopada por fazenda) realmente referencia — mesmo
    # resultado, sem depender de uma coluna que não existe na prática.
    ids_etapa_necessarios = {ap.etapa_id for ap in aplicacoes_pendentes}
    etapas_por_id = {
        e.id: e for e in session.exec(
            select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.id.in_(ids_etapa_necessarios))
        ).all()
    } if ids_etapa_necessarios else {}
    lancamentos_por_id = {l.id: l for l in session.exec(_da_fazenda(select(ProtocoloSanitarioLancamento), ProtocoloSanitarioLancamento)).all()}
    protocolos_por_id = {p.id: p for p in session.exec(_da_fazenda(select(ProtocoloSanitario), ProtocoloSanitario)).all()}
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

    # Protocolo IATF — agrupa por (DATA PREVISTA, dia): uma linha por etapa do
    # protocolo, não uma por animal, mostrando todos os animais daquele passo
    # de uma vez. Agrupa pela data, não pelo lançamento — animais com o mesmo
    # D0 incluídos em lançamentos separados (ex.: adicionados um de cada vez,
    # em vez de "em lote") continuam caindo na mesma etapa/data e têm que
    # aparecer juntos; agrupar por lancamento_id fragmentava esse caso em N
    # cards de 1 animal cada (relato: 9 animais em D11, só 1 aparecendo na
    # Agenda).
    #
    # Etapa VENCIDA continua cobrando por até JANELA_ATRASO_DIAS — mesma regra
    # do protocolo customizado. Antes, a etapa cujo dia passou simplesmente
    # sumia daqui; e como a Agenda era o único lugar do sistema que gravava
    # `realizada = True`, o protocolo ficava travado em "em andamento" para
    # sempre, sem nenhuma tela capaz de fechá-lo (relato do usuário: três
    # protocolos IATF parados em 18/36, 15/20 e 8/16). Lançamento RETROATIVO
    # (IATF sem protocolo, D0 no passado) segue sem janela nenhuma: as etapas
    # vencidas dele são justamente o que se quer ver. Passada a janela, a
    # baixa continua possível pela Central de Protocolos.
    limite_atraso = data - timedelta(days=JANELA_ATRASO_PROTOCOLO_DIAS)
    lancamentos_iatf_por_id = {l.id: l for l in session.exec(_da_fazenda(select(ProtocoloIatfLancamento), ProtocoloIatfLancamento)).all()}
    aplicacoes_iatf = [
        a for a in session.exec(
            _da_fazenda(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.realizada == False), ProtocoloIatfAplicacao)  # noqa: E712
        ).all()
        if not getattr(lancamentos_iatf_por_id.get(a.lancamento_id), "encerrado_em", None)
        and (a.data_prevista >= limite_atraso
             or getattr(lancamentos_iatf_por_id.get(a.lancamento_id), "retroativo", False))
    ]
    grupos_iatf: dict[tuple[date, int], list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes_iatf:
        grupos_iatf.setdefault((ap.data_prevista, ap.dia), []).append(ap)

    # Hormônios cadastrados por (lançamento, dia) + as opções de medicamento
    # (frascos em estoque) do princípio ativo de cada um, para o "qual
    # medicamento/frasco?" na hora de confirmar o dia (ex.: D9).
    # `_opcoes_medicamento` pré-carrega estoque/princípios uma vez e reusa em
    # cada chamada — mesmo mecanismo compartilhado com a Central de
    # Protocolos, ver fazenda.rules.estoque_baixa.opcoes_medicamento.
    _query_estoque_agenda = select(Estoque)
    if fazenda_id is not None:
        _query_estoque_agenda = _query_estoque_agenda.where(Estoque.fazenda_id == fazenda_id)
    _todos_estoque = session.exec(_query_estoque_agenda).all()
    _query_pa_agenda = select(PrincipioAtivo)
    if fazenda_id is not None:
        _query_pa_agenda = _query_pa_agenda.where(PrincipioAtivo.fazenda_id == fazenda_id)
    _pa_por_nome = {(p.nome or "").strip().lower(): p for p in session.exec(_query_pa_agenda).all()}
    # MedicamentoComercial é catálogo global (sem fazenda_id) — carregado uma
    # vez só aqui e reusado por chamada de _opcoes_medicamento em vez de uma
    # consulta nova por hormônio/medicamento (antes eram dezenas de consultas
    # idênticas por carregamento da Agenda).
    _marcas_por_pa: dict[int, list] = {}
    for _mc in session.exec(select(MedicamentoComercial)).all():
        _marcas_por_pa.setdefault(_mc.principio_ativo_id, []).append(_mc)

    def _opcoes_medicamento(produto: str) -> tuple[int | None, list[dict]]:
        return estoque_baixa.opcoes_medicamento(
            session, fazenda_id=fazenda_id, produto=produto,
            todos_estoque=_todos_estoque, principios_por_nome=_pa_por_nome,
            marcas_por_principio_id=_marcas_por_pa,
        )

    hormonios_por_grupo: dict[tuple[int, int], list[dict]] = {}
    for h in session.exec(_da_fazenda(select(ProtocoloIatfHormonio), ProtocoloIatfHormonio)).all():
        pa_id, opcoes = _opcoes_medicamento(h.produto)
        hormonios_por_grupo.setdefault((h.lancamento_id, h.dia), []).append({
            "produto": h.produto, "dose": h.dose, "unidade": h.unidade, "via": h.via,
            "principio_ativo_id": pa_id, "opcoes": opcoes,
        })

    eventos_iatf = []
    DIAS_PROTOCOLO_IATF = [0, 7, 9, 11]
    for (data_prevista, dia), aps in grupos_iatf.items():
        chave = f"protocolo_iatf_{data_prevista.isoformat()}_{dia}"
        if chave in realizados:
            continue
        lancamento_ids_grupo = sorted({a.lancamento_id for a in aps})
        lancamentos_grupo = [lancamentos_iatf_por_id[lid] for lid in lancamento_ids_grupo if lancamentos_iatf_por_id.get(lid)]
        if not lancamentos_grupo:
            continue
        # Vários lançamentos podem cair no mesmo grupo (ver comentário acima)
        # — normalmente é o mesmo protocolo, então o nome coincide; quando não
        # coincide (lançamentos de nomes diferentes com o mesmo D0/dia, raro),
        # mostra os dois nomes em vez de escolher um arbitrariamente.
        nome_protocolo = " + ".join(sorted({l.nome_protocolo for l in lancamentos_grupo}))
        animais_grupo = sorted((a.numero_matriz for a in aps), key=chave_numero)
        proximos_dias = [d for d in DIAS_PROTOCOLO_IATF if d > dia]
        proxima_etapa = None
        if proximos_dias:
            proximo_dia = proximos_dias[0]
            # data_prevista já é "D{dia}" deste grupo — a próxima etapa é só
            # avançar a diferença de dias, sem depender de um único data_d0
            # (lançamentos diferentes do grupo compartilham essa mesma data
            # prevista por construção, então o resultado é idêntico).
            proxima_data = data_prevista + timedelta(days=proximo_dia - dia)
            proxima_etapa = f"Próxima etapa: D{proximo_dia} em {proxima_data.strftime('%d/%m/%Y')}"
        hormonios_grupo: list[dict] = []
        vistos_hormonio: set[tuple] = set()
        for lid in lancamento_ids_grupo:
            for h in hormonios_por_grupo.get((lid, dia), []):
                chave_h = (h["produto"], h["dose"], h["unidade"], h["via"])
                if chave_h in vistos_hormonio:
                    continue
                vistos_hormonio.add(chave_h)
                hormonios_grupo.append(h)
        eventos_iatf.append({
            "id": chave, "data": data_prevista.isoformat(), "categoria": "Reprodutivo",
            "descricao": f"{nome_curto(nome_protocolo)} — D{dia}",
            "numero_animal": None, "observacao": proxima_etapa,
            "fonte": "manual", "cor": "var(--dourado)", "ref": None,
            "tipo": "protocolo_iatf", "dia": dia, "animais": animais_grupo, "hormonio": aps[0].descricao,
            "hormonios": hormonios_grupo,
            "protocolo": nome_protocolo,
        })

    # Protocolo de indução de lactação — agrupa por (lançamento, dia), igual
    # ao protocolo IATF: uma linha por dia mostrando todos os animais daquele
    # passo, com a observação de manejo (implante, adaptação na ordenha,
    # iniciar a ordenha) bem visível para o funcionário.
    # Mesma janela de atraso do IATF/customizado — ver o comentário lá em cima.
    lancamentos_inducao_por_id = {l.id: l for l in session.exec(_da_fazenda(select(ProtocoloInducaoLancamento), ProtocoloInducaoLancamento)).all()}
    aplicacoes_inducao = [
        a for a in session.exec(
            _da_fazenda(select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.realizada == False), ProtocoloInducaoAplicacao)  # noqa: E712
        ).all()
        if a.data_prevista >= limite_atraso
        and not getattr(lancamentos_inducao_por_id.get(a.lancamento_id), "encerrado_em", None)
    ]
    grupos_inducao: dict[tuple[int, int], list[ProtocoloInducaoAplicacao]] = {}
    for ap in aplicacoes_inducao:
        grupos_inducao.setdefault((ap.lancamento_id, ap.dia), []).append(ap)

    # Medicamentos cadastrados por (lançamento, dia) + as opções de estoque do
    # princípio ativo de cada um — mesmo mecanismo do protocolo IATF acima
    # (_opcoes_medicamento), pra dar o campo clicável "qual frasco?" na hora
    # de confirmar, em vez de resolver por nome sozinho.
    medicamentos_por_grupo_inducao: dict[tuple[int, int], list[dict]] = {}
    for m in session.exec(_da_fazenda(select(ProtocoloInducaoMedicamento), ProtocoloInducaoMedicamento)).all():
        pa_id, opcoes = _opcoes_medicamento(m.produto)
        medicamentos_por_grupo_inducao.setdefault((m.lancamento_id, m.dia), []).append({
            "produto": m.produto, "dose": m.dose, "unidade": m.unidade, "via": m.via,
            "principio_ativo_id": pa_id, "opcoes": opcoes,
        })

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
            "descricao": f"{nome_curto(lancamento.nome_protocolo)} — D{dia}",
            "numero_animal": None, "observacao": aps[0].observacao_manejo,
            "fonte": "manual", "cor": "var(--dourado)", "ref": None,
            "tipo": "protocolo_inducao", "dia": dia, "animais": animais_grupo,
            "medicamentos_opcoes": medicamentos_por_grupo_inducao.get((lancamento_id, dia), []),
            "medicamentos": aps[0].descricao, "protocolo": lancamento.nome_protocolo,
        })

    # Eventos sanitários agendados (por época ou por evento de vida) — cada um
    # já traz o medicamento padrão para pré-preencher a Aplicação ao dar baixa.
    eventos_sanitarios = _eventos_sanitarios_agenda(session, data, realizados)

    # Protocolos personalizados (Configurações > Cadastro > Protocolos
    # personalizados) — fonte ADITIVA de tarefas: o cronograma que o próprio
    # produtor cadastrou, lançado contra animais/lote/fazenda, agrupado por
    # (lançamento, dia). Fora do AgendaEngine de propósito, para não mexer no
    # cálculo já testado dele.
    eventos_protocolo_custom = _eventos_protocolo_custom_agenda(session, data, realizados, fazenda_id)

    # Lida (tarefas gerais da fazenda que não são protocolo de animal — ver
    # fazenda/models/lida.py) — mesmo espírito do protocolo personalizado
    # acima: fonte ADITIVA, fora do AgendaEngine de propósito.
    eventos_lida = _eventos_lida_agenda(session, data, realizados, fazenda_id)

    # Cronograma sanitário (regras do calendário sanitário marcadas
    # usa_cronograma=True) — trilha do animal (incluir/excluir) + trilha do
    # agendamento (decidir modo/adiar/aplicar). Fora do AgendaEngine de
    # propósito, mesmo espírito do protocolo personalizado acima.
    eventos_cronograma_sanitario = _cronograma_sanitario_rules.eventos_agenda(session, data, realizados, fazenda_id)

    # NOTA: o alerta "bezerras entrando na janela de risco de doença" (Ponto
    # Crítico da Recria) foi retirado da Agenda a pedido do dono do produto —
    # o cadastro JanelaPontoCritico continua existindo/editável em Recria,
    # só não gera mais esse aviso automático aqui (ver fazenda.rules.coorte.
    # ponto_critico(), que é o cálculo ESTATÍSTICO usado no card do dashboard
    # e não tem relação com isto).

    # Aplicações programadas ("aplicado? não" / data futura) ainda não baixadas.
    # Dar baixa aqui gera a aplicação de verdade e a saída de estoque.
    # Uma vez criada, essa linha ficava pendurada pra sempre — mesmo que o
    # animal fosse baixado depois (relato: "03M" macho e já baixado ainda
    # aparecendo pra vacina). Exclui só quem está CONFIRMADAMENTE baixado —
    # um numero_matriz sem cadastro em Animal (ex.: lançamento avulso/animal
    # ainda não importado) continua aparecendo normalmente, como sempre.
    animais_baixados = set(session.exec(_da_fazenda(select(Animal.numero).where(Animal.ativo == False), Animal)))  # noqa: E712
    aplic_agendadas = [
        a for a in session.exec(_da_fazenda(select(AplicacaoAgendada).where(AplicacaoAgendada.aplicado == False), AplicacaoAgendada))  # noqa: E712
        if a.numero_matriz not in animais_baixados
    ]
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
        _da_fazenda(select(Parto).where(Parto.data_parto >= limite_parto, Parto.data_parto <= data), Parto)
    ).all()
    if partos_recentes:
        colostro_por_animal = {c.numero_animal: c for c in session.exec(_da_fazenda(select(ColostragemBezerra), ColostragemBezerra)).all()}
        # Bezerras (crias) por (mãe, data de nascimento) para casar com o parto.
        crias_por_chave: dict[tuple[str, object], list[Animal]] = {}
        for a in session.exec(_da_fazenda(select(Animal).where(Animal.ativo == True, Animal.mae_numero != None), Animal)).all():  # noqa: E711,E712
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

    # Confirmação de cura — SÓ para aplicação de PROTOCOLO SANITÁRIO
    # pré-cadastrado em Sanidade Curativa (nunca para lançamento avulso, nem
    # para preventivo — esses nunca passam por ProtocoloSanitarioLancamento).
    # Pergunta "curado? sim/não" no dia seguinte a TODOS os medicamentos do
    # ÚLTIMO DIA do protocolo terem sido efetivamente lançados (não basta a
    # data ter passado — se faltar aplicar algum medicamento do último dia,
    # o evento não aparece). Diferente das pendências "realizado" comuns: a
    # resposta é PERSISTIDA (ProtocoloSanitarioLancamento.curada) e alimenta o
    # relatório Taxa de cura — marcar "realizado" sozinho não basta, por isso
    # o frontend chama primeiro POST .../cura e só depois marca o evento.
    eventos_cura = []
    limite_cura = data - timedelta(days=60)
    lancamentos_protocolo_abertos = session.exec(
        _da_fazenda(select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.curada == None), ProtocoloSanitarioLancamento)  # noqa: E711
    ).all()
    if lancamentos_protocolo_abertos:
        aplicacoes_por_lancamento: dict[int, list] = {}
        for a in session.exec(_da_fazenda(select(ProtocoloSanitarioAplicacao), ProtocoloSanitarioAplicacao)).all():
            aplicacoes_por_lancamento.setdefault(a.lancamento_id, []).append(a)
        for lanc in lancamentos_protocolo_abertos:
            terminou, ultimo_dia = protocolo_terminado(aplicacoes_por_lancamento.get(lanc.id, []))
            if not terminou:
                continue  # falta aplicar algum medicamento do último dia — ainda não pergunta
            dia_seguinte = ultimo_dia + timedelta(days=1)
            if dia_seguinte > data or dia_seguinte < limite_cura:
                continue
            chave = f"cura_protocolo_{lanc.id}"
            if chave in realizados:
                continue
            eventos_cura.append({
                "id": chave, "data": dia_seguinte.isoformat(), "categoria": "sanidade",
                "descricao": f"Confirmar cura — matriz {lanc.numero_matriz} (protocolo sanitário)",
                "numero_animal": lanc.numero_matriz, "observacao": None,
                "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "confirmar_cura",
                "cura_origem": "protocolo", "cura_id": lanc.id,
            })

    # Nova dieta: alerta um dia antes ("para amanhã") e no dia ("hoje"), com
    # link para abrir a dieta. A chave inclui a data de referência → o alerta
    # de véspera e o do dia são eventos distintos (marcar um não some o outro).
    eventos_nova_dieta = []
    for d in session.exec(
        _da_fazenda(select(DietaLancamento).where(DietaLancamento.data_efetivo_encerramento == None), DietaLancamento)  # noqa: E711
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
    agend_pesagem = session.exec(
        _da_fazenda(select(AgendamentoPesagem).where(AgendamentoPesagem.ativo == True), AgendamentoPesagem)  # noqa: E712
    ).all()
    if agend_pesagem:
        # Todos os animais ativos (inclui bezerros de ambos os sexos) com nascimento.
        todos_ativos = session.exec(
            _da_fazenda(select(Animal).where(Animal.ativo == True), Animal)  # noqa: E712
        ).all()
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

    # Sugestão automática de movimentação entre lotes (Rebanho > Sugestões de
    # movimentação): aparece na Agenda no dia definido pelo parâmetro
    # (Configurações > Parâmetros) — no próprio dia em que o animal passa a
    # atender outro lote, ou só no dia fixo da semana escolhido (ex.: toda
    # sexta), agrupando as sugestões pendentes daquela semana. A chave inclui
    # o lote atual do animal: se ele mudar de lote (aceitando a sugestão ou
    # manualmente), uma eventual nova sugestão a partir do novo lote é tratada
    # como uma pendência nova, mesmo que o animal já tenha dispensado uma
    # sugestão antes a partir do lote anterior.
    parametro_movimentacao = session.get(ParametroSugestaoMovimentacao, 1) or ParametroSugestaoMovimentacao(id=1)
    eventos_movimentacao = []
    mostra_hoje = (
        parametro_movimentacao.modo == "dia_fixo_semana" and data.weekday() == parametro_movimentacao.dia_semana
    ) or parametro_movimentacao.modo != "dia_fixo_semana"
    if mostra_hoje:
        fazenda_id_res = fazenda_id_seguro(fazenda_id)
        query_lotes_mov = select(Lote)
        if fazenda_id_res is not None:
            query_lotes_mov = query_lotes_mov.where(Lote.fazenda_id == fazenda_id_res)
        lotes_mov = session.exec(query_lotes_mov).all()
        dados_criterios_mov = coletar_dados_criterios(session, fazenda_id_res)
        for s in sugerir_movimentacoes(lotes_mov, dados_criterios_mov["animais"], data, dados_criterios_mov):
            chave = f"sugestao_movimentacao_{s['numero_matriz']}_{s['lote_atual'] or 'sem_lote'}"
            if chave in realizados:
                continue
            nomes_sugeridos = ", ".join(l["rotulo"] for l in s["lotes_sugeridos"])
            lote_atual_label = s["lote_atual"] or "sem lote"
            eventos_movimentacao.append({
                "id": chave, "data": data.isoformat(), "categoria": "Rebanho",
                "descricao": f"Sugestão de mudança de lote — matriz {s['numero_matriz']}: {lote_atual_label} → {nomes_sugeridos}",
                "numero_animal": s["numero_matriz"], "observacao": s["motivo"],
                "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "sugestao_movimentacao",
                "lote": s["lote_atual"], "lotes_sugeridos": s["lotes_sugeridos"], "motivo": s["motivo"],
            })

    # Estoque mínimo de sêmen POR CATEGORIA — abaixo do mínimo, um alerta
    # DIÁRIO na agenda (a chave inclui a data → reaparece todo dia até a NF
    # repor). Mínimos editáveis em Configurações > Cadastro > Central de
    # Sêmen > Estoque mínimo (ver parametros.minimos_semen_por_tipo).
    totais_semen = {"convencional": 0, "sexado": 0}
    for s in session.exec(_da_fazenda(select(EstoqueSemen), EstoqueSemen)).all():
        if s.ativo and s.tipo in totais_semen:
            totais_semen[s.tipo] += s.doses or 0
    eventos_semen = []
    hoje_iso = data.isoformat()
    for cat, minimo in minimos_semen_por_tipo().items():
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

    # Manutenção preventiva de patrimônio vencida (ou a vencer em até 15 dias,
    # ver DIAS_ALERTA_MANUTENCAO_PROXIMA) — um alerta por item, sem sufixo de
    # data (a chave é só o id do item): some sozinho quando a manutenção é
    # registrada (POST /financeiro/patrimonio/{id}/manutencao recalcula
    # data_proxima_manutencao) e não pode ser dispensado sem registrá-la (ver
    # bloqueio em marcar_realizado, mesmo padrão de colostragem/IgG).
    eventos_patrimonio = []
    itens_patrimonio = session.exec(
        _da_fazenda(select(Patrimonio).where(Patrimonio.data_proxima_manutencao != None), Patrimonio)  # noqa: E711
    ).all()
    for item in itens_patrimonio:
        if item.data_baixa:
            continue
        situacao = status_manutencao(item.model_dump(), data)["situacao_manutencao"]
        if situacao not in ("vencida", "proxima"):
            continue
        chave = f"patrimonio_manutencao_{item.id}"
        if chave in realizados:
            continue
        vencida = situacao == "vencida"
        eventos_patrimonio.append({
            "id": chave, "data": item.data_proxima_manutencao.isoformat(), "categoria": "Gestão/Financeiro",
            "descricao": f"Manutenção preventiva {'VENCIDA' if vencida else 'próxima'} — {item.nome}"
            + (f" (nº {item.numero})" if item.numero else ""),
            "numero_animal": None, "observacao": item.observacao_manutencao,
            "fonte": "auto", "cor": "var(--red)" if vencida else "var(--dourado)", "ref": None,
            "tipo": "patrimonio_manutencao", "patrimonio_id": item.id, "situacao_manutencao": situacao,
        })

    # Atualização de valor de mercado vencida — só para patrimônio não
    # depreciável (ex.: terra, ver Patrimonio.depreciavel). Some sozinha
    # quando o valor é registrado (PUT /financeiro/patrimonio/{id}/valor-mercado
    # recalcula a data base) — não pode ser dispensada sem registrar (mesmo
    # padrão da manutenção preventiva acima).
    frequencia_padrao_valor_mercado = patrimonio_atualizacao_valor_mercado_meses()
    itens_nao_depreciaveis = session.exec(
        _da_fazenda(select(Patrimonio).where(Patrimonio.depreciavel == False), Patrimonio)  # noqa: E712
    ).all()
    for item in itens_nao_depreciaveis:
        if item.data_baixa:
            continue
        prox = proxima_atualizacao_valor_mercado(item.model_dump(), frequencia_padrao_valor_mercado)
        if not prox or prox > data:
            continue
        chave = f"patrimonio_valor_mercado_{item.id}"
        if chave in realizados:
            continue
        eventos_patrimonio.append({
            "id": chave, "data": prox.isoformat(), "categoria": "Gestão/Financeiro",
            "descricao": f"Atualizar valor de mercado — {item.nome}" + (f" (nº {item.numero})" if item.numero else ""),
            "numero_animal": None,
            "observacao": f"Última avaliação: {item.valor_mercado_atual if item.valor_mercado_atual is not None else item.valor_total}",
            "fonte": "auto", "cor": "var(--dourado)", "ref": None,
            "tipo": "patrimonio_valor_mercado", "patrimonio_id": item.id,
        })

    # Perda de prenhez sem motivo cadastrado — detectada automaticamente pelo
    # sistema (nova inseminação sobre um diagnóstico POSITIVO vigente sem
    # perda registrada, ver fazenda.rules.perda_prenhez) ou lançada manualmente
    # sem motivo. Fica pendente até o usuário "Cadastrar motivo" ou
    # "Descartar" (grava o sentinela `nao_informado` — a perda continua
    # registrada, só o motivo que não foi informado; ver PUT
    # /reproducao/servicos/{id}). Sem piso de data: uma perda de dias atrás
    # continua pendente até ser resolvida, mesmo padrão de Pré-parto/Secagem
    # em agenda_engine.py.
    eventos_perda_prenhez_pendente = []
    query_perda_pendente = select(Servico).where(
        Servico.data_perda_prenhez.is_not(None), Servico.motivo_perda_prenhez.is_(None),
    )
    if fazenda_id is not None:
        query_perda_pendente = query_perda_pendente.where(Servico.fazenda_id == fazenda_id)
    for s in session.exec(query_perda_pendente).all():
        chave = f"perda_prenhez_motivo_{s.id}"
        if chave in realizados:
            continue
        origem_txt = (
            f" — detectada pela nova inseminação de {s.numero_matriz}" if s.origem_perda_prenhez == "reinseminacao" else ""
        )
        eventos_perda_prenhez_pendente.append({
            "id": chave, "data": s.data_perda_prenhez.isoformat(), "categoria": "Reprodutivo",
            "descricao": f"Cadastrar motivo da perda de prenhez — {s.numero_matriz}",
            "numero_animal": s.numero_matriz,
            "observacao": f"Perda em {s.data_perda_prenhez.strftime('%d/%m/%Y')}{origem_txt}.",
            "fonte": "auto", "cor": "var(--red)", "ref": None,
            "tipo": "perda_prenhez_motivo", "servico_id": s.id,
        })

    # Diarista com diária ativa cobrindo `data` e sem folga marcada nesse dia —
    # a Agenda passa a refletir o mesmo estado do controle de diárias.
    eventos_diaria_trabalho = []
    q_diaria_trabalho = select(Diaria, Pessoa).join(Pessoa, Diaria.pessoa_id == Pessoa.id).where(
        Diaria.status == "ativo",
        Diaria.data_inicio <= data,
        (Diaria.data_fim == None) | (Diaria.data_fim >= data),  # noqa: E711
    )
    if fazenda_id is not None:
        q_diaria_trabalho = q_diaria_trabalho.where(Diaria.fazenda_id == fazenda_id)
    folgas_hoje = {
        r.diaria_id for r in session.exec(
            _da_fazenda(select(DiariaDia).where(DiariaDia.data == data, DiariaDia.trabalhado == False), DiariaDia)  # noqa: E712
        ).all()
    }
    for diaria, pessoa in session.exec(q_diaria_trabalho).all():
        if diaria.id in folgas_hoje:
            continue
        chave = f"diaria_trabalho_{diaria.id}_{data.isoformat()}"
        if chave in realizados:
            continue
        eventos_diaria_trabalho.append({
            "id": chave, "data": data.isoformat(), "categoria": "Gestão/Financeiro",
            "descricao": f"{pessoa.nome} — diária de hoje ({diaria.valor_diaria:.2f}/dia)",
            "numero_animal": None,
            "observacao": "Se não veio hoje, marque como folga no controle de diárias.",
            "fonte": "auto", "cor": "var(--dourado)", "ref": None,
            "tipo": "diaria_trabalho", "diaria_id": diaria.id,
            # Deep-link pro Controle de diárias (Financeiro > Ações > Folha de
            # pagamento > Diária) — mesmo mecanismo `?ir=` que a central de
            # alertas já usa pra pular pra A pagar/A receber (ver
            # app/financeiro/page.tsx). ANTES esta URL usava `?aba=folha`, uma
            # chave que financeiro/page.tsx nunca leu — o clique caía na tela
            # em branco de Financeiro, sem abrir aba nenhuma; corrigido junto
            # com a troca dos botões "Importar agora"/"Realizado" por "Contar
            # diária"/"Descartar diária" (ver app/agenda/page.tsx).
            "link": f"/financeiro?ir=folha&categoria=diarias&diaria={diaria.id}&calendario=ultimo_periodo",
        })

    # Diária com data de fim prevista chegando hoje — avisa no próprio dia
    # (não antes, não depois) para o usuário decidir se encerra ou estende.
    eventos_diaria_fim = []
    diarias_com_fim_query = (
        select(Diaria, Pessoa)
        .join(Pessoa, Diaria.pessoa_id == Pessoa.id)
        .where(Diaria.status == "ativo", Diaria.data_fim == data)
    )
    if fazenda_id is not None:
        diarias_com_fim_query = diarias_com_fim_query.where(Diaria.fazenda_id == fazenda_id)
    diarias_com_fim = session.exec(diarias_com_fim_query).all()
    for diaria, pessoa in diarias_com_fim:
        chave = f"diaria_fim_{diaria.id}_{data.isoformat()}"
        if chave in realizados:
            continue
        eventos_diaria_fim.append({
            "id": chave, "data": data.isoformat(), "categoria": "Gestão/Financeiro",
            "descricao": f"Diária de {pessoa.nome} encerra hoje",
            "numero_animal": None, "observacao": "Confira o total apurado e registre o pagamento final, ou edite a data de fim para estender.",
            "fonte": "auto", "cor": "var(--dourado)", "ref": None, "tipo": "diaria_fim", "diaria_id": diaria.id,
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
    ] + eventos_dieta + eventos_protocolo + eventos_iatf + eventos_inducao + eventos_sanitarios + eventos_aplic_agendada + eventos_vacina_pre_parto + eventos_semen + eventos_colostro + eventos_cura + eventos_nova_dieta + eventos_pesagem + eventos_patrimonio + eventos_movimentacao + eventos_bst + eventos_diaria_fim + eventos_diaria_trabalho + eventos_protocolo_custom + eventos_lida + eventos_cronograma_sanitario + eventos_perda_prenhez_pendente
    eh_admin = usuario.papel == "admin"
    eventos_visiveis = [
        e for e in eventos_visiveis
        if (MODULO_POR_CATEGORIA.get(e["categoria"], None) is None or MODULO_POR_CATEGORIA[e["categoria"]] in modulos)
        and (eh_admin or not e.get("apenas_admin"))  # eventos só-admin ocultos para os demais
    ]
    tem_financeiro = "financeiro" in modulos
    tem_reproducao = "reproducao" in modulos
    tem_estoque = tem_modulo(usuario, "estoque")

    diaria_auditorias_pendentes = []
    if tem_financeiro:
        query_pendentes = (
            select(DiariaAuditoria, Diaria, Pessoa)
            .join(Diaria, DiariaAuditoria.diaria_id == Diaria.id)
            .join(Pessoa, Diaria.pessoa_id == Pessoa.id)
            .where(DiariaAuditoria.dias_trabalhados.is_(None))
            .order_by(DiariaAuditoria.periodo_fim)
        )
        if fazenda_id is not None:
            query_pendentes = query_pendentes.where(DiariaAuditoria.fazenda_id == fazenda_id)
        pendentes = session.exec(query_pendentes).all()
        diaria_auditorias_pendentes = [
            {
                "id": auditoria.id,
                "diaria_id": diaria.id,
                "pessoa_nome": pessoa.nome,
                "periodo_inicio": auditoria.periodo_inicio.isoformat(),
                "periodo_fim": auditoria.periodo_fim.isoformat(),
            }
            for auditoria, diaria, pessoa in pendentes
        ]

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
        "intervalo_bst": intervalo_bst_dias if tem_reproducao else None,
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
        "diaria_auditorias_pendentes": diaria_auditorias_pendentes,
        "totais": {
            "candidatas_iatf": len(result.candidatas_iatf) if tem_reproducao else 0,
            "bst_elegiveis": len(result.bst_elegiveis) if tem_reproducao else 0,
            "bst_nunca_aplicados": len(bst_nunca_aplicados) if tem_reproducao else 0,
            "contas_a_pagar": len(result.contas_a_pagar) if tem_financeiro else 0,
            "eventos": len(eventos_visiveis),
            "diaria_auditorias_pendentes": len(diaria_auditorias_pendentes),
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
    animais: list[str] | None = None  # subconjunto opcional (protocolo_iatf/protocolo_inducao) — None = todos do grupo
    # Medicamentos efetivamente aplicados neste dia do protocolo IATF ou de
    # indução de lactação, com o frasco escolhido ("qual medicamento você
    # está usando?"). Quando vem, é ele que gera a aplicação em Sanidade e a
    # baixa; sem ele, cai nos hormônios/medicamentos cadastrados no
    # lançamento (comportamento anterior).
    medicamentos: list[MedicamentoIatfIn] | None = None
    # Overrides opcionais do produto/dose/unidade/via aplicados de fato — só
    # usados quando evento_id é de uma aplicação agendada ("aplic_agendada_");
    # sem eles, mantém os valores gravados na hora do agendamento.
    produto: str | None = None
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None
    # Cronograma sanitário — cada campo só é lido pelo prefixo correspondente
    # (ver marcar_realizado abaixo); nos demais tipos de evento, ignorados.
    incluir: bool | None = None                    # cronograma_sanitario_animal_ — incluir/excluir o animal
    modo: str | None = None                        # cronograma_sanitario_modo_ — "veterinario" | "propria"
    veterinario_pessoa_id: int | None = None        # cronograma_sanitario_modo_ (modo="veterinario")
    nova_data: date | None = None                   # cronograma_sanitario_modo_ — presente = adiar em vez de decidir
    motivo: str | None = None                       # cronograma_sanitario_modo_ — motivo do adiamento (opcional)
    responsavel: str | None = None                  # cronograma_sanitario_aplicar_
    observacao: str | None = None                   # cronograma_sanitario_aplicar_


def _decidir_cronograma_animal(session: Session, evento_id: str, incluir: bool | None) -> None:
    if incluir is None:
        raise HTTPException(status_code=400, detail="Informe se o animal deve ser incluído ou excluído do cronograma")
    linha_id = int(evento_id.removeprefix(f"{_PREFIXO_CRONOGRAMA}animal_"))
    try:
        _cronograma_sanitario_rules.decidir_animal(session, linha_id, incluir, date.today())
    except CronogramaError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _decidir_cronograma_modo(
    session: Session, evento_id: str, modo: str | None, veterinario_pessoa_id: int | None,
    nova_data: date | None, motivo: str | None,
) -> None:
    cronograma_id = int(evento_id.removeprefix(f"{_PREFIXO_CRONOGRAMA}modo_"))
    cronograma = session.get(CronogramaSanitario, cronograma_id)
    if not cronograma:
        raise HTTPException(status_code=404, detail="Cronograma não encontrado")
    try:
        if nova_data is not None:
            _cronograma_sanitario_rules.adiar(session, cronograma, nova_data, motivo)
        else:
            _cronograma_sanitario_rules.decidir_modo(session, cronograma, modo, veterinario_pessoa_id)
    except CronogramaError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _aplicar_cronograma(
    session: Session, evento_id: str, animais: list[str] | None, responsavel: str | None, observacao: str | None,
    produto: str | None, dose: float | None, unidade: str | None, via: str | None,
    fazenda_id: int | None, user: Usuario,
) -> list[str]:
    """Aplica o produto padrão do evento sanitário nos animais incluídos no
    cronograma — em lote (animais=None, aplica todo mundo incluído) ou
    individualizado (animais=[um número]), site e app chamam o mesmo
    endpoint. Reaproveita 100% a lógica de baixa de estoque/Sanidade já
    usada por /sanidade/calendario/cadastrar-preventivo."""
    cronograma_id = int(evento_id.removeprefix(f"{_PREFIXO_CRONOGRAMA}aplicar_"))
    cronograma = session.get(CronogramaSanitario, cronograma_id)
    if not cronograma:
        raise HTTPException(status_code=404, detail="Cronograma não encontrado")
    if cronograma.status != "agendado":
        raise HTTPException(status_code=400, detail="Este cronograma ainda não tem veterinário/aplicação própria confirmado")
    calendario = session.get(CalendarioSanitario, cronograma.calendario_sanitario_id)
    if not calendario:
        raise HTTPException(status_code=404, detail="Regra do calendário sanitário não encontrada")

    incluidos = _cronograma_sanitario_rules.animais_por_status(session, cronograma.id, "incluido")
    alvo = set(animais) if animais else {l.numero_matriz for l in incluidos}
    animais_aplicar = [l.numero_matriz for l in incluidos if l.numero_matriz in alvo]
    if not animais_aplicar:
        raise HTTPException(status_code=400, detail="Nenhum animal incluído para aplicar")

    from fazenda.api.routers.sanidade import CadastrarPreventivoIn, cadastrar_preventivo
    cadastrar_preventivo(
        CadastrarPreventivoIn(
            evento_sanitario_id=calendario.evento_sanitario_id, categoria_alvo=calendario.categoria_alvo,
            data_evento=date.today(), calendario_id=calendario.id, animais=animais_aplicar,
            aplicar=True, aplicado=True, responsavel=responsavel, observacao=observacao,
            produto=produto, dose=dose, unidade=unidade, via=via,
        ),
        session=session, user=user, fazenda_id=fazenda_id,
    )
    _cronograma_sanitario_rules.concluir(session, cronograma, animais_aplicar, date.today())
    restantes = len(incluidos) - len(animais_aplicar)
    return [f"Aplicado em {len(animais_aplicar)} animal(is)."] + (
        [f"{restantes} animal(is) do cronograma seguem pendentes de aplicação."] if restantes else []
    )


def _baixar_protocolo_sanitario(
    session: Session, evento_id: str, fazenda_id: int | None = None, usuario_id: int | None = None,
) -> list[str]:
    """
    Ao marcar "realizado" um evento de protocolo sanitário: registra a
    aplicação em Sanidade e dá baixa automática do produto no Estoque (quando
    a unidade da etapa bate com a unidade de estoque do produto).
    """
    aplicacao_id = int(evento_id.removeprefix("protocolo_sanitario_"))
    aplicacao = session.get(ProtocoloSanitarioAplicacao, aplicacao_id)
    if not aplicacao or aplicacao.realizada:
        return []
    etapa = session.get(ProtocoloSanitarioEtapa, aplicacao.etapa_id)
    lancamento = session.get(ProtocoloSanitarioLancamento, aplicacao.lancamento_id)
    if not etapa or not lancamento:
        return []

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

    estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=produto)
    avisos = estoque_baixa.baixar(
        session, item=estoque_item, quantidade=etapa.dosagem, unidade=etapa.unidade, data=hoje,
        fazenda_id=fazenda_id, observacao=f"Protocolo sanitário — matriz {lancamento.numero_matriz} — D{etapa.dia}",
        usuario_id=usuario_id, origem_tipo="protocolo_sanitario", origem_id=aplicacao.id, produto=produto,
    )
    session.commit()
    return avisos


def _baixar_aplicacao_agendada(
    session: Session, evento_id: str,
    produto: str | None = None, dose: float | None = None, unidade: str | None = None, via: str | None = None,
    fazenda_id: int | None = None, usuario_id: int | None = None,
) -> list[str]:
    """Confirma uma aplicação programada: cria o registro de Sanidade e dá a
    baixa de estoque (quando a unidade bate com a do estoque). Os overrides
    (produto/dose/unidade/via) vêm do painel de "dar baixa" do app/site — o
    usuário pode ajustar o que foi de fato aplicado antes de confirmar; sem
    eles, usa os valores gravados na hora do agendamento."""
    aid = int(evento_id.removeprefix("aplic_agendada_"))
    ag = session.get(AplicacaoAgendada, aid)
    if not ag or ag.aplicado:
        return []
    hoje = date.today()
    produto_final = produto or ag.produto
    dose_final = dose if dose is not None else ag.dose
    unidade_final = unidade or ag.unidade
    via_final = via or ag.via
    ag.aplicado = True
    ag.data_aplicacao = hoje
    ag.produto = produto_final
    ag.dose = dose_final
    ag.unidade = unidade_final
    ag.via = via_final
    session.add(ag)

    session.add(Sanidade(
        numero_matriz=ag.numero_matriz, data_aplicacao=hoje, produto=produto_final,
        dose=dose_final, unidade=unidade_final, via=via_final, responsavel=ag.responsavel, obs=ag.observacao,
        natureza=ag.natureza or "curativo",
    ))

    # Aplicação de BST confirmada (produto reconhecido) — fecha o ciclo do
    # "Reverter (voltar a apta)", igual à aplicação direta em aplicar_bst_lote.
    if MARCADORES_BST.search(produto_final or ""):
        animal = session.exec(select(Animal).where(Animal.numero == ag.numero_matriz)).first()
        if animal and animal.aguardando_nova_aplicacao_bst:
            animal.aguardando_nova_aplicacao_bst = False
            session.add(animal)

    avisos: list[str] = []
    if dose_final:
        estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=produto_final)
        avisos = estoque_baixa.baixar(
            session, item=estoque_item, quantidade=dose_final, unidade=unidade_final, data=hoje,
            fazenda_id=fazenda_id, observacao=f"Aplicação programada — matriz {ag.numero_matriz}",
            usuario_id=usuario_id, origem_tipo="aplicacao_agendada", origem_id=ag.id, produto=produto_final,
        )
    session.commit()
    return avisos


def _baixar_vacina_pre_parto(
    session: Session, evento_id: str, fazenda_id: int | None = None, usuario_id: int | None = None,
) -> list[str]:
    """Confirma TODAS as vacinas pré-parto pendentes daquele cartão (mesmo
    animal + mesma data) de uma vez — cada uma vira um registro de Sanidade e
    dá baixa de estoque (dose=1, unidade="dose"), igualando o comportamento ao
    caminho da Secagem (ver registrar_secagem em producao.py) — antes esta
    função só marcava a AplicacaoAgendada e criava a Sanidade, sem tocar o
    Estoque: o mesmo evento tinha dois comportamentos diferentes conforme
    fosse confirmado por aqui ou pela Secagem."""
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
    avisos: list[str] = []
    for ag in rows:
        ag.aplicado = True
        ag.data_aplicacao = hoje
        session.add(ag)
        sanidade = Sanidade(
            numero_matriz=ag.numero_matriz, data_aplicacao=hoje, produto=ag.produto,
            via=ag.via, responsavel=ag.responsavel, obs=ag.observacao,
        )
        session.add(sanidade)
        session.flush()
        estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=ag.produto)
        avisos.extend(estoque_baixa.baixar(
            session, item=estoque_item, quantidade=1, unidade="dose", data=hoje, fazenda_id=fazenda_id,
            observacao=f"Vacina pré-parto — matriz {ag.numero_matriz}", usuario_id=usuario_id,
            origem_tipo="vacina_pre_parto", origem_id=sanidade.id, produto=ag.produto,
        ))
    session.commit()
    return avisos


def _marcar_protocolo_iatf_realizado(
    session: Session, evento_id: str, animais: list[str] | None,
    medicamentos: list["MedicamentoIatfIn"] | None = None,
    fazenda_id: int | None = None, usuario_id: int | None = None,
    data_realizacao: date | None = None, lancamento_id: int | None = None,
) -> list[str]:
    """
    Marca a(s) aplicação(ões) de um grupo (DATA PREVISTA, dia) do protocolo
    IATF como realizadas. O grupo pode reunir animais de mais de um
    ProtocoloIatfLancamento — acontece quando animais com o mesmo D0 foram
    incluídos em lançamentos separados em vez de um único lote (ver o
    agrupamento por data em `calcular_agenda`). Sem `animais`, marca o grupo
    inteiro; com `animais`, confirma só esse subconjunto — os demais
    continuam pendentes no grupo.

    `medicamentos` (opcional): os frascos que o usuário escolheu na hora de
    confirmar o dia ("qual medicamento?"), aplicado ao grupo inteiro. Sem
    ele, usa os hormônios cadastrados em cada lançamento — como lançamentos
    diferentes do mesmo grupo podem ter hormônios cadastrados diferentes, a
    baixa de estoque nesse caso é calculada por lançamento, não pro grupo
    inteiro de uma vez.

    `data_realizacao` (opcional): o dia em que a aplicação REALMENTE
    aconteceu. É o que a baixa retroativa da Central de Protocolos usa para
    não carimbar "hoje" numa aplicação feita há três semanas. Sem ele, hoje.

    `lancamento_id` (opcional): restringe a baixa a UM lançamento. Pela
    Agenda não se passa — o grupo (data, dia) é justamente o que se quer
    confirmar de uma vez. Pela Central, sim: lá se está olhando um lançamento
    específico, e confirmar por tabela arrastaria junto outro lote que por
    acaso tem o mesmo D0.
    """
    resto = evento_id.removeprefix("protocolo_iatf_")
    data_str, dia_str = resto.rsplit("_", 1)
    data_prevista, dia = date.fromisoformat(data_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.data_prevista == data_prevista,
            ProtocoloIatfAplicacao.dia == dia,
            ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
        )
    ).all()
    if lancamento_id is not None:
        aplicacoes = [a for a in aplicacoes if a.lancamento_id == lancamento_id]
    if animais is not None:
        alvo = set(animais)
        aplicacoes = [a for a in aplicacoes if a.numero_matriz in alvo]

    avisos: list[str] = []
    if not aplicacoes:
        return avisos

    hoje = data_realizacao or date.today()

    # Aplicados: o que o usuário escolheu ao confirmar (com o frasco) vale
    # pro grupo inteiro, OU, na falta disso, os hormônios cadastrados em CADA
    # lançamento (podem diferir entre lançamentos do mesmo grupo).
    aplicados_fixos = None
    if medicamentos:
        aplicados_fixos = [
            {"produto": m.produto, "dose": m.dose, "unidade": m.unidade, "via": m.via, "estoque_id": m.estoque_id}
            for m in medicamentos if (m.produto or "").strip()
        ]

    lancamentos_cache: dict[int, ProtocoloIatfLancamento | None] = {}
    hormonios_cache: dict[int, list[dict]] = {}
    aplicacoes_por_lancamento: dict[int, list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes:
        aplicacoes_por_lancamento.setdefault(ap.lancamento_id, []).append(ap)
        if ap.lancamento_id not in lancamentos_cache:
            lancamentos_cache[ap.lancamento_id] = session.get(ProtocoloIatfLancamento, ap.lancamento_id)
        if aplicados_fixos is None and ap.lancamento_id not in hormonios_cache:
            hormonios = session.exec(
                select(ProtocoloIatfHormonio).where(
                    ProtocoloIatfHormonio.lancamento_id == ap.lancamento_id,
                    ProtocoloIatfHormonio.dia == dia,
                )
            ).all()
            hormonios_cache[ap.lancamento_id] = [
                {"produto": h.produto, "dose": h.dose, "unidade": h.unidade, "via": h.via, "estoque_id": None}
                for h in hormonios
            ]
        responsavel = getattr(lancamentos_cache[ap.lancamento_id], "responsavel", None)
        ap.realizada = True
        ap.data_realizacao = hoje
        session.add(ap)
        aplicados_ap = aplicados_fixos if aplicados_fixos is not None else hormonios_cache[ap.lancamento_id]
        for m in aplicados_ap:
            session.add(Sanidade(
                numero_matriz=ap.numero_matriz, data_aplicacao=hoje, produto=m["produto"],
                dose=m["dose"], unidade=m["unidade"], via=m["via"], responsavel=responsavel,
                obs=f"Protocolo IATF — D{dia}",
                protocolo_iatf_lancamento_id=ap.lancamento_id,
            ))

    # Baixa de estoque: uma vez por medicamento, dose × nº de vacas confirmadas.
    # Abate do frasco escolhido (estoque_id) ou, na falta, do item pelo nome.
    # Com medicamento explícito, o frasco vale pro grupo inteiro — mas a baixa
    # em si é sempre lançada POR LANÇAMENTO (uma chamada a `baixar` por
    # lancamento_id do grupo, com origem_id=lancamento_id), nunca como um
    # bloco único com origem_id=None. Motivo: `cancelar()` (central_protocolos.py)
    # estorna filtrando MovimentoEstoque por origem_id == lancamento_id; uma
    # baixa gravada sem origem_id nunca é encontrada por nenhum cancelamento,
    # e o estoque que ela consumiu fica órfão pra sempre quando o grupo reúne
    # mais de um lançamento (mesmo D0, lotes lançados separados). O rateio é
    # exato porque a dose é a mesma pra todo o grupo: dose × nº de vacas DAQUELE
    # lançamento, sem dízima nem resto pra ajustar — a soma bate com dose × total.
    if aplicados_fixos is not None:
        for m in aplicados_fixos:
            if not m["dose"]:
                continue
            estoque_item = estoque_baixa.resolver_item(
                session, fazenda_id=fazenda_id, produto=m["produto"], estoque_id=m["estoque_id"],
            )
            for lancamento_id, aps in aplicacoes_por_lancamento.items():
                n_vacas_lanc = len(aps)
                total_lanc = m["dose"] * n_vacas_lanc
                avisos.extend(estoque_baixa.baixar(
                    session, item=estoque_item, quantidade=total_lanc, unidade=m["unidade"], data=hoje,
                    fazenda_id=fazenda_id, observacao=f"Protocolo IATF — D{dia} — {n_vacas_lanc} vaca(s)",
                    usuario_id=usuario_id, origem_tipo="iatf", origem_id=lancamento_id, produto=m["produto"],
                ))
    else:
        for lancamento_id, aps in aplicacoes_por_lancamento.items():
            n_vacas = len(aps)
            for m in hormonios_cache.get(lancamento_id, []):
                if not m["dose"]:
                    continue
                estoque_item = estoque_baixa.resolver_item(
                    session, fazenda_id=fazenda_id, produto=m["produto"], estoque_id=m["estoque_id"],
                )
                total = m["dose"] * n_vacas
                avisos.extend(estoque_baixa.baixar(
                    session, item=estoque_item, quantidade=total, unidade=m["unidade"], data=hoje,
                    fazenda_id=fazenda_id, observacao=f"Protocolo IATF — D{dia} — {n_vacas} vaca(s)",
                    usuario_id=usuario_id, origem_tipo="iatf", origem_id=lancamento_id, produto=m["produto"],
                ))
    session.commit()
    # Com medicamento explícito e o grupo rateado por lançamento, o mesmo
    # aviso ("não está no estoque", "ficou negativo" etc.) pode se repetir
    # uma vez por lançamento — dedup preservando a ordem de aparição.
    return list(dict.fromkeys(avisos))


def _marcar_protocolo_inducao_realizado(
    session: Session, evento_id: str, animais: list[str] | None,
    medicamentos: list["MedicamentoIatfIn"] | None = None,
    fazenda_id: int | None = None, usuario_id: int | None = None,
    data_realizacao: date | None = None,
) -> list[str]:
    """
    Marca a(s) aplicação(ões) de um grupo (lançamento, dia) da indução de
    lactação como realizadas. Sem `animais`, marca o grupo inteiro; com
    `animais`, confirma só esse subconjunto. Etapas de manejo/dispositivo
    (sem medicamento) só marcam a aplicação — não geram Sanidade nem baixa.

    `medicamentos` (opcional): os frascos que o usuário escolheu na hora de
    confirmar o dia ("qual medicamento?"), mesmo mecanismo do protocolo IATF.
    Quando vem, é ele que gera a aplicação em Sanidade e a baixa (abatendo do
    frasco pelo estoque_id); sem ele, usa os medicamentos cadastrados no
    lançamento e resolve o item de estoque só pelo nome (comportamento antigo).

    `data_realizacao` (opcional): o dia real da aplicação, para a baixa
    retroativa da Central de Protocolos — ver _marcar_protocolo_iatf_realizado.
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

    hoje = data_realizacao or date.today()
    lancamento = session.get(ProtocoloInducaoLancamento, lancamento_id)
    responsavel = getattr(lancamento, "responsavel", None)

    if medicamentos:
        aplicados = [
            {"produto": m.produto, "dose": m.dose, "unidade": m.unidade, "via": m.via, "estoque_id": m.estoque_id}
            for m in medicamentos if (m.produto or "").strip()
        ]
    else:
        cadastrados = session.exec(
            select(ProtocoloInducaoMedicamento).where(
                ProtocoloInducaoMedicamento.lancamento_id == lancamento_id,
                ProtocoloInducaoMedicamento.dia == dia,
            )
        ).all()
        aplicados = [
            {"produto": m.produto, "dose": m.dose, "unidade": m.unidade, "via": m.via, "estoque_id": None}
            for m in cadastrados
        ]

    for ap in aplicacoes:
        ap.realizada = True
        ap.data_realizacao = hoje
        session.add(ap)
        for m in aplicados:
            session.add(Sanidade(
                numero_matriz=ap.numero_matriz, data_aplicacao=hoje, produto=m["produto"],
                dose=m["dose"], unidade=m["unidade"], via=m["via"], responsavel=responsavel,
                obs=f"Indução de lactação — D{dia}",
                protocolo_inducao_lancamento_id=lancamento_id,
            ))

    # Baixa de estoque: uma vez por medicamento, dose × nº de vacas confirmadas.
    # Abate do frasco escolhido (estoque_id) ou, na falta, do item pelo nome.
    avisos: list[str] = []
    n_vacas = len(aplicacoes)
    if n_vacas:
        for m in aplicados:
            if not m["dose"]:
                continue
            estoque_item = estoque_baixa.resolver_item(
                session, fazenda_id=fazenda_id, produto=m["produto"], estoque_id=m["estoque_id"],
            )
            total = m["dose"] * n_vacas
            avisos.extend(estoque_baixa.baixar(
                session, item=estoque_item, quantidade=total, unidade=m["unidade"], data=hoje,
                fazenda_id=fazenda_id, observacao=f"Indução de lactação — D{dia} — {n_vacas} vaca(s)",
                usuario_id=usuario_id, origem_tipo="inducao", origem_id=lancamento_id, produto=m["produto"],
            ))
    session.commit()
    return avisos


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
def marcar_realizado(
    dados: RealizadoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
    user: Usuario = Depends(get_current_user),
) -> dict:
    """Marca um evento como realizado — ele sai da agenda (pendentes e futuros)."""
    usuario_id = usuario_id_seguro(user)
    if dados.evento_id.startswith(COMUNICADO_PREFIXOS):
        raise HTTPException(status_code=400, detail="Comunicados não podem ser marcados como realizados — eles somem sozinhos no dia seguinte.")
    if dados.evento_id.startswith("colostragem_pendente_") or dados.evento_id.startswith("igg_pendente_"):
        raise HTTPException(status_code=400, detail="Esta pendência não pode ser dispensada — preencha o dado que falta na ficha do animal.")
    if dados.evento_id.startswith("patrimonio_manutencao_"):
        raise HTTPException(status_code=400, detail="Esta pendência não pode ser dispensada — registre a manutenção no item de patrimônio (isso atualiza a próxima data sozinho).")
    if dados.evento_id.startswith("patrimonio_valor_mercado_"):
        raise HTTPException(status_code=400, detail="Esta pendência não pode ser dispensada — registre o novo valor de mercado no item de patrimônio (isso atualiza a próxima data sozinho).")
    if dados.evento_id.startswith("protocolo_iatf_"):
        avisos = _marcar_protocolo_iatf_realizado(
            session, dados.evento_id, dados.animais, dados.medicamentos, fazenda_id=fazenda_id, usuario_id=usuario_id,
        )
        return {"marcado": True, "avisos": avisos}
    if dados.evento_id.startswith("protocolo_inducao_"):
        avisos = _marcar_protocolo_inducao_realizado(
            session, dados.evento_id, dados.animais, dados.medicamentos, fazenda_id=fazenda_id, usuario_id=usuario_id,
        )
        return {"marcado": True, "avisos": avisos}
    if dados.evento_id.startswith(PREFIXO_PROTOCOLO_CUSTOM):
        _marcar_protocolo_custom_realizado(session, dados.evento_id, dados.animais)
        return {"marcado": True}
    if dados.evento_id.startswith(PREFIXO_LIDA):
        avisos = _marcar_lida_realizado(
            session, dados.evento_id, dados.animais, fazenda_id=fazenda_id, usuario_id=usuario_id,
        )
        return {"marcado": True, "avisos": avisos}
    if dados.evento_id.startswith(f"{_PREFIXO_CRONOGRAMA}animal_"):
        _decidir_cronograma_animal(session, dados.evento_id, dados.incluir)
        return {"marcado": True}
    if dados.evento_id.startswith(f"{_PREFIXO_CRONOGRAMA}modo_"):
        _decidir_cronograma_modo(session, dados.evento_id, dados.modo, dados.veterinario_pessoa_id, dados.nova_data, dados.motivo)
        return {"marcado": True}
    if dados.evento_id.startswith(f"{_PREFIXO_CRONOGRAMA}aplicar_"):
        avisos = _aplicar_cronograma(
            session, dados.evento_id, dados.animais, dados.responsavel, dados.observacao,
            dados.produto, dados.dose, dados.unidade, dados.via, fazenda_id, user,
        )
        return {"marcado": True, "avisos": avisos}

    query_existe = select(EventoRealizado).where(EventoRealizado.evento_id == dados.evento_id)
    if fazenda_id is not None:
        query_existe = query_existe.where(EventoRealizado.fazenda_id.in_((fazenda_id, None)))
    existe = session.exec(query_existe).first()
    avisos: list[str] = []
    if not existe:
        session.add(EventoRealizado(evento_id=dados.evento_id, fazenda_id=fazenda_id))
        session.commit()
        if dados.evento_id.startswith("protocolo_sanitario_"):
            avisos = _baixar_protocolo_sanitario(session, dados.evento_id, fazenda_id=fazenda_id, usuario_id=usuario_id)
        elif dados.evento_id.startswith("aplic_agendada_"):
            avisos = _baixar_aplicacao_agendada(
                session, dados.evento_id, dados.produto, dados.dose, dados.unidade, dados.via,
                fazenda_id=fazenda_id, usuario_id=usuario_id,
            )
        elif dados.evento_id.startswith("vacina_pre_parto_"):
            avisos = _baixar_vacina_pre_parto(session, dados.evento_id, fazenda_id=fazenda_id, usuario_id=usuario_id)
    return {"marcado": True, "avisos": avisos}


class AplicarBstIn(BaseModel):
    numeros_matriz: list[str]
    data_aplicacao: date
    produto: str = "Lactotropin"
    dose: float | None = None
    unidade: str | None = None
    responsavel: str | None = None
    # "Já foi aplicado?" — igual a Sanidade/AplicacaoIn: quando a data é futura
    # (ou aplicado=False), NADA é baixado do estoque agora — fica programada
    # na Agenda até a visita ser confirmada.
    aplicado: bool = True


@router.post("/bst/aplicar")
def aplicar_bst_lote(
    dados: AplicarBstIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Confirma (ou agenda) a aplicação de BST (Lactotropin/Boostin) para os
    animais informados. Data retroativa/hoje + aplicado=True materializa na
    hora (Sanidade + baixa de estoque); data futura sempre vira uma pendência
    na Agenda (AplicacaoAgendada), confirmada depois como qualquer outra —
    mesma regra de "aplicar agora vs. agendar" usada em /sanidade/aplicacoes.
    A próxima visita (12 dias, ou o intervalo cadastrado em Configurações)
    recalcula sozinha a partir da data de aplicação mais recente."""
    from fazenda.rules.parametros import get_param

    usuario_id = usuario_id_seguro(user)
    materializar = dados.aplicado and dados.data_aplicacao <= date.today()

    if not materializar:
        for numero in dados.numeros_matriz:
            session.add(AplicacaoAgendada(
                numero_matriz=numero, data=dados.data_aplicacao, produto=dados.produto,
                dose=dados.dose, unidade=dados.unidade, responsavel=dados.responsavel,
                usuario_id=usuario_id, natureza="preventivo", fazenda_id=fazenda_id,
            ))
        session.commit()
        intervalo = get_param("intervalo_bst", 12)
        return {"aplicados": 0, "agendados": len(dados.numeros_matriz), "programado": True, "intervalo_dias": intervalo}

    avisos: list[str] = []
    for numero in dados.numeros_matriz:
        sanidade = Sanidade(
            numero_matriz=numero, data_aplicacao=dados.data_aplicacao, produto=dados.produto,
            dose=dados.dose, unidade=dados.unidade, responsavel=dados.responsavel, atividade="BST",
            usuario_id=usuario_id, natureza="preventivo", fazenda_id=fazenda_id,
        )
        session.add(sanidade)
        session.flush()
        if dados.dose and dados.unidade:
            # Antes esta baixa não gravava MovimentoEstoque nenhum — saldo caía
            # sem deixar rastro no histórico/RMCA (ver auditoria).
            estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=dados.produto)
            avisos.extend(estoque_baixa.baixar(
                session, item=estoque_item, quantidade=dados.dose, unidade=dados.unidade, data=dados.data_aplicacao,
                fazenda_id=fazenda_id, observacao=f"BST — matriz {numero}", usuario_id=usuario_id,
                origem_tipo="bst", origem_id=sanidade.id, produto=dados.produto,
            ))
        # Nova aplicação de fato lançada — fecha o ciclo de "Reverter (voltar
        # a apta)": o animal deixa de ficar em bst_reanalise e volta a contar
        # normalmente pela avaliação de elegibilidade (ver agenda_engine.py).
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if animal and animal.aguardando_nova_aplicacao_bst:
            animal.aguardando_nova_aplicacao_bst = False
            session.add(animal)
    session.commit()

    intervalo = get_param("intervalo_bst", 12)
    return {
        "aplicados": len(dados.numeros_matriz),
        "agendados": 0,
        "programado": False,
        "intervalo_dias": intervalo,
        "proxima_aplicacao_calculada": (dados.data_aplicacao + timedelta(days=intervalo)).isoformat(),
        "avisos": avisos,
    }


class MarcarInaptaBstIn(BaseModel):
    numeros_matriz: list[str]
    # True = marca como inapta para a próxima aplicação/retira voluntariamente
    # (Animal.excluir_bst); False = reverte ("Reverter (voltar a apta)").
    inapta: bool = True


@router.post("/bst/marcar-inapta")
def marcar_inapta_bst(dados: MarcarInaptaBstIn, session: Session = Depends(get_session)) -> dict:
    """Marca (ou reverte) animais como inaptos para a próxima aplicação de BST
    — ação distinta de aplicar: não lança nenhuma Sanidade nem mexe em
    estoque, só sinaliza para a Agenda/relatórios via Animal.excluir_bst.

    Reverter (inapta=False) NÃO torna o animal apto imediatamente — ele vai
    para "Incluir no próximo BST" (bst_reanalise) e só volta a bst_elegiveis
    depois que uma aplicação de fato é lançada (ver aplicar_bst_lote, que
    limpa aguardando_nova_aplicacao_bst)."""
    atualizados = 0
    for numero in dados.numeros_matriz:
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if not animal:
            continue
        animal.excluir_bst = dados.inapta
        animal.aguardando_nova_aplicacao_bst = False if dados.inapta else True
        session.add(animal)
        atualizados += 1
    session.commit()
    return {"atualizados": atualizados, "inapta": dados.inapta}


def _desmarcar_protocolo_iatf_realizado(session: Session, evento_id: str) -> None:
    """
    Reverte um grupo (DATA PREVISTA, dia) do protocolo IATF marcado por
    engano — volta todas as aplicações do grupo para pendente (sem registro
    de qual subconjunto foi confirmado, reverter o grupo inteiro é o único
    comportamento coerente).
    """
    resto = evento_id.removeprefix("protocolo_iatf_")
    data_str, dia_str = resto.rsplit("_", 1)
    data_prevista, dia = date.fromisoformat(data_str), int(dia_str)

    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.data_prevista == data_prevista,
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
    """Grupos (data prevista, dia) do protocolo IATF já confirmados — para desfazer, se marcado por engano."""
    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.realizada == True)  # noqa: E712
    ).all()
    lancamentos_por_id = {l.id: l for l in session.exec(select(ProtocoloIatfLancamento)).all()}
    grupos: dict[tuple[date, int], list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes:
        grupos.setdefault((ap.data_prevista, ap.dia), []).append(ap)

    resultado = []
    for (data_prevista, dia), aps in grupos.items():
        nomes_protocolo = sorted({
            lancamentos_por_id[lid].nome_protocolo
            for lid in {a.lancamento_id for a in aps} if lancamentos_por_id.get(lid)
        })
        if not nomes_protocolo:
            continue
        datas_realizacao = [a.data_realizacao for a in aps if a.data_realizacao]
        resultado.append({
            "id": f"protocolo_iatf_{data_prevista.isoformat()}_{dia}",
            "nome_protocolo": " + ".join(nomes_protocolo), "dia": dia,
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
def desmarcar_realizado(
    evento_id: str, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Desfaz a marcação de realizado — o evento volta a aparecer na agenda."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if evento_id.startswith(COMUNICADO_PREFIXOS):
        raise HTTPException(status_code=400, detail="Comunicados não podem ser excluídos — eles somem sozinhos no dia seguinte.")
    if evento_id.startswith("protocolo_iatf_"):
        _desmarcar_protocolo_iatf_realizado(session, evento_id)
        return {"desmarcado": True}
    if evento_id.startswith("protocolo_inducao_"):
        _desmarcar_protocolo_inducao_realizado(session, evento_id)
        return {"desmarcado": True}
    if evento_id.startswith(PREFIXO_PROTOCOLO_CUSTOM):
        _desmarcar_protocolo_custom_realizado(session, evento_id)
        return {"desmarcado": True}
    if evento_id.startswith(PREFIXO_LIDA):
        _desmarcar_lida_realizado(session, evento_id)
        return {"desmarcado": True}
    if evento_id.startswith(_PREFIXO_CRONOGRAMA):
        raise HTTPException(
            status_code=400,
            detail="Decisões do cronograma sanitário não se desfazem por aqui — ajuste em Sanidade > Preventivo > Cronogramas.",
        )

    query_existe = select(EventoRealizado).where(EventoRealizado.evento_id == evento_id)
    if fazenda_id is not None:
        query_existe = query_existe.where(EventoRealizado.fazenda_id.in_((fazenda_id, None)))
    existe = session.exec(query_existe).first()
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
def adicionar_evento_manual(
    dados: AgendaManualIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
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
        fazenda_id=fazenda_id,
    )
    session.add(evento)
    session.commit()
    session.refresh(evento)
    return evento.model_dump()
