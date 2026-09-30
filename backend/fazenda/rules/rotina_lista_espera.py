"""
Rotina automática da lista de espera do preventivo.

Especificação aprovada pelo dono: docs/agents/auditoria-preventivo-agenda/
planejamento/11-rotina-lista-de-espera.md. Em uma frase: animais que se
aproximam da janela de uma regra de vacina/exame JÁ cadastrada entram sozinhos
na lista de espera ("sugerido" do cronograma aberto da regra).

SÓ atua quando as três condições valem:
  1. a fazenda marcou "Ativar rotina da lista de espera" em Parâmetros (padrão
     desligado — sem linha de parâmetro, é desligado);
  2. existem regras de vacina ou exame ativas no calendário sanitário;
  3. tudo o mais vem da regra/evento já cadastrado (categoria-alvo, produto,
     frequência/data devida, sexo, ciclo) — nada é configurado em dobro. A
     única opção nova é o número de dias de antecedência (valor da fazenda,
     que a regra pode sobrescrever em `dias_antecedencia_lista_espera`).

O QUE A ROTINA NUNCA FAZ: aplicar, baixar estoque, criar agendamento, lançar
Sanidade ou gerar tarefa do "Dia a dia". Só cria/atualiza a lista de espera, e
com as mesmas travas do fluxo manual (`sugerir_animais_em_lote`): idempotente,
R8 (um animal por lista/agendamento ativo por protocolo), macho fora do B19,
reagente de exame fora, e já vacinado no ciclo fora. Vendido/baixado nunca
entra.

Concorrência (várias instâncias da API, deploy no meio da rotina, clique duplo
em "Executar agora"): o estado por fazenda (`RotinaListaEsperaEstado`) guarda
um arrendamento `em_execucao_ate` tomado por UPDATE atômico, e a execução
DIÁRIA só passa se `ultima_diaria_em` ainda não for hoje. Além disso a própria
escrita é idempotente, então o pior caso de uma corrida é não fazer nada.

Todas as funções recebem `fazenda_id` explícito e filtram por ele; a sessão
pode ser a de manutenção (o loop de fundo enumera fazendas antes de saber qual
está processando), mas o recorte por fazenda nunca depende de RLS.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from fazenda.models import (
    CalendarioSanitario, CronogramaSanitarioAnimal, EventoSanitario, ParametroFazenda, RotinaListaEsperaEstado,
)
from fazenda.rules import cronograma_sanitario as crono
from fazenda.rules.checklist_sanitario import materializar_checklist
from fazenda.rules.parametros import fazenda_atual
from fazenda.rules.projecao_categoria import animais_projetados_na_categoria

log = logging.getLogger("fazenda.rotina_lista_espera")

CHAVE_ATIVA = "lista_espera_rotina_ativa"
CHAVE_DIAS = "lista_espera_dias_antecedencia"
CHAVE_AVISO = "lista_espera_aviso_diario"
CHAVES = (CHAVE_ATIVA, CHAVE_DIAS, CHAVE_AVISO)

DIAS_ANTECEDENCIA_PADRAO = 15
DIAS_ANTECEDENCIA_MAX = 365
# Arrendamento do lock: bem acima do tempo de uma passada, e curto o bastante
# para uma instância que morreu no meio não travar a fazenda até o dia seguinte.
LEASE = timedelta(minutes=20)

ORIGENS = ("diaria", "parametros", "manual")
_VERDADEIRO = ("1", "true", "sim", "yes")


class RotinaError(Exception):
    """Uso indevido (ex.: executar agora com a rotina desligada)."""


# ---------------------------------------------------------------------------
# Parâmetros da fazenda (explícitos por fazenda_id, sem depender do contexto)
# ---------------------------------------------------------------------------
def _linha_param(session: Session, chave: str, fazenda_id: int | None) -> ParametroFazenda | None:
    if fazenda_id is not None:
        propria = session.exec(
            select(ParametroFazenda).where(ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == fazenda_id)
        ).first()
        if propria is not None:
            return propria
    return session.exec(
        select(ParametroFazenda).where(ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id.is_(None))
    ).first()


def _bool(linha: ParametroFazenda | None, padrao: bool = False) -> bool:
    if linha is None or linha.valor is None:
        return padrao
    return linha.valor.strip().lower() in _VERDADEIRO


def config_da_fazenda(session: Session, fazenda_id: int | None) -> dict:
    """Os três parâmetros da fazenda. Sem linha nenhuma: rotina desligada."""
    dias = DIAS_ANTECEDENCIA_PADRAO
    linha = _linha_param(session, CHAVE_DIAS, fazenda_id)
    if linha is not None:
        try:
            dias = int(float(linha.valor))
        except (TypeError, ValueError):
            dias = DIAS_ANTECEDENCIA_PADRAO
    dias = max(0, min(DIAS_ANTECEDENCIA_MAX, dias))
    return {
        "ativa": _bool(_linha_param(session, CHAVE_ATIVA, fazenda_id)),
        "dias_antecedencia": dias,
        "aviso_diario": _bool(_linha_param(session, CHAVE_AVISO, fazenda_id)),
    }


# ---------------------------------------------------------------------------
# Estado por fazenda + lock
# ---------------------------------------------------------------------------
def _estado(session: Session, fazenda_id: int) -> RotinaListaEsperaEstado:
    estado = session.exec(
        select(RotinaListaEsperaEstado).where(RotinaListaEsperaEstado.fazenda_id == fazenda_id)
    ).first()
    if estado is not None:
        return estado
    try:
        estado = RotinaListaEsperaEstado(fazenda_id=fazenda_id)
        session.add(estado)
        session.commit()
    except IntegrityError:   # outra instância criou no mesmo instante (unique por fazenda)
        session.rollback()
        estado = session.exec(
            select(RotinaListaEsperaEstado).where(RotinaListaEsperaEstado.fazenda_id == fazenda_id)
        ).first()
    return estado


def _tomar_lock(session: Session, fazenda_id: int, agora: datetime, hoje: date, diaria: bool) -> bool:
    """UPDATE atômico: só UMA instância vence. A diária ainda exige que hoje
    não tenha tido outra execução diária."""
    condicoes = [
        RotinaListaEsperaEstado.fazenda_id == fazenda_id,
        or_(RotinaListaEsperaEstado.em_execucao_ate.is_(None), RotinaListaEsperaEstado.em_execucao_ate < agora),
    ]
    if diaria:
        condicoes.append(or_(
            RotinaListaEsperaEstado.ultima_diaria_em.is_(None), RotinaListaEsperaEstado.ultima_diaria_em < hoje,
        ))
    resultado = session.execute(
        update(RotinaListaEsperaEstado).where(*condicoes).values(em_execucao_ate=agora + LEASE)
    )
    session.commit()
    return (resultado.rowcount or 0) == 1


# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------
def regras_de_vacina_ou_exame(session: Session, fazenda_id: int) -> list[tuple[CalendarioSanitario, EventoSanitario | None]]:
    """Regras ativas do calendário cujo evento é vacina ou exame (evento sem
    tipo é vacina, como no resto da Agenda; tratamento fica de fora)."""
    regras = session.exec(
        select(CalendarioSanitario)
        .where(CalendarioSanitario.ativo == True)  # noqa: E712
        .where(CalendarioSanitario.fazenda_id == fazenda_id)
        .order_by(CalendarioSanitario.id)
    ).all()
    eventos = {
        e.id: e for e in session.exec(select(EventoSanitario).where(EventoSanitario.fazenda_id == fazenda_id)).all()
    }
    saida = []
    for regra in regras:
        evento = eventos.get(regra.evento_sanitario_id)
        if evento is None or evento.ativo is False:
            continue
        if (evento.categoria_preventiva or "vacina") not in ("vacina", "exame"):
            continue
        saida.append((regra, evento))
    return saida


def _dias_da_regra(regra: CalendarioSanitario, dias_fazenda: int) -> int:
    if regra.dias_antecedencia_lista_espera is not None and regra.dias_antecedencia_lista_espera >= 0:
        return min(regra.dias_antecedencia_lista_espera, DIAS_ANTECEDENCIA_MAX)
    return dias_fazenda


def _sugeridos_da_regra(session: Session, calendario_id: int) -> int:
    return sum(1 for linha, _ in crono._linhas_da_regra(session, calendario_id) if linha.status == "sugerido")


def _processar(session: Session, fazenda_id: int, cfg: dict, hoje: date) -> dict:
    regras = regras_de_vacina_ou_exame(session, fazenda_id)
    resultado = {"regras": len(regras), "regras_na_janela": 0, "entraram": 0, "por_regra": []}
    if not regras:
        return resultado

    dados_criterios: dict | None = None
    for calendario, evento in regras:
        if evento is not None and evento.tipo_agendamento == "evento":
            continue   # regra por evento de vida: alimentada pelo gatilho próprio, sem "janela" de época
        existente, devida = crono._lista_de_espera_da_regra(session, calendario)
        dias = _dias_da_regra(calendario, cfg["dias_antecedencia"])
        if hoje < devida - timedelta(days=dias):
            continue   # ainda longe da janela desta regra
        resultado["regras_na_janela"] += 1

        cron = existente or crono.cronograma_aberto(session, calendario)
        if evento is not None:
            materializar_checklist(session, cron, evento)   # idempotente; o cronograma nasce como na Agenda

        if dados_criterios is None:
            from fazenda.api.routers.lotes import coletar_dados_criterios
            dados_criterios = coletar_dados_criterios(session, fazenda_id)
        numeros = animais_projetados_na_categoria(calendario.categoria_alvo or "", crono._data_devida(cron), dados_criterios)
        baixados = {
            a["numero"] for a in dados_criterios["animais"]
            if a.get("ativo") is False or a.get("data_baixa") or a.get("motivo_baixa")
        }
        numeros = [n for n in numeros if n not in baixados]
        produto = calendario.produto or (evento.produto_padrao if evento else None)
        vacinados = crono._ja_vacinados_no_ciclo(session, cron, calendario, produto, numeros)
        numeros = [n for n in numeros if n not in vacinados]

        antes = _sugeridos_da_regra(session, calendario.id)
        if numeros:
            crono.sugerir_animais_em_lote(session, calendario, numeros, hoje)
        novos = _sugeridos_da_regra(session, calendario.id) - antes
        if novos > 0:
            from fazenda.rules.aplicacao_preventiva import registrar_log
            registrar_log(
                session, cron, "Lista de espera (rotina)", canal="rotina",
                detalhe=f"{novos} animal(is) entraram na lista de espera, {dias} dia(s) antes da janela",
            )
            session.commit()
        resultado["entraram"] += max(novos, 0)
        resultado["por_regra"].append({"calendario_id": calendario.id, "entraram": max(novos, 0)})
    return resultado


def total_na_lista_de_espera(session: Session, fazenda_id: int | None) -> int:
    """Quantos animais estão hoje na lista de espera da fazenda (o número do
    card do Painel; mesma conta do atalho da Agenda)."""
    return sum(r.get("quantidade") or 0 for r in crono.resumo_lista_espera(session, fazenda_id))


def executar_fazenda(
    session: Session, fazenda_id: int, origem: str = "diaria", hoje: date | None = None, agora: datetime | None = None,
) -> dict:
    """Roda a rotina de UMA fazenda. Nunca levanta por falha de dado: o erro
    fica no estado (`ultimo_erro`) e no log. Devolve `{"executou": bool,
    "motivo": ..., ...}` — motivo em: ok | desligada | sem_regras | ja_executou_hoje
    | em_execucao | erro."""
    if origem not in ORIGENS:
        raise ValueError(f"origem invalida: {origem}")
    hoje = hoje or date.today()
    agora = agora or datetime.now()
    cfg = config_da_fazenda(session, fazenda_id)
    if not cfg["ativa"]:
        return {"executou": False, "motivo": "desligada", "entraram": 0}

    _estado(session, fazenda_id)
    diaria = origem == "diaria"
    if not _tomar_lock(session, fazenda_id, agora, hoje, diaria):
        estado = _estado(session, fazenda_id)
        session.refresh(estado)
        ja_diaria = diaria and estado.ultima_diaria_em is not None and estado.ultima_diaria_em >= hoje and (
            estado.em_execucao_ate is None or estado.em_execucao_ate < agora
        )
        return {"executou": False, "motivo": "ja_executou_hoje" if ja_diaria else "em_execucao", "entraram": 0}

    token = fazenda_atual.set(fazenda_id)
    try:
        try:
            resultado = _processar(session, fazenda_id, cfg, hoje)
            status, erro = ("ok" if resultado["regras"] else "sem_regras"), None
        except Exception as exc:  # noqa: BLE001 — falha de uma fazenda nunca derruba as outras nem o loop
            session.rollback()
            log.exception("rotina da lista de espera falhou (fazenda %s)", fazenda_id)
            resultado = {"regras": 0, "regras_na_janela": 0, "entraram": 0, "por_regra": []}
            status, erro = "erro", f"{type(exc).__name__}: {exc}"[:500]

        estado = _estado(session, fazenda_id)
        estado.ultima_execucao_em = agora
        estado.ultima_execucao_origem = origem
        estado.ultima_execucao_status = status
        estado.ultima_execucao_entraram = resultado["entraram"]
        estado.ultima_execucao_regras = resultado["regras"]
        estado.ultima_execucao_regras_na_janela = resultado["regras_na_janela"]
        estado.ultimo_erro = erro
        if diaria and status != "erro":
            estado.ultima_diaria_em = hoje
        aviso_emitido = False
        if status != "erro" and cfg["aviso_diario"] and estado.ultimo_aviso_em != hoje:
            if total_na_lista_de_espera(session, fazenda_id) > 0:
                estado.ultimo_aviso_em = hoje   # no máximo 1 aviso por dia por fazenda
                aviso_emitido = True
        estado.em_execucao_ate = None
        session.add(estado)
        session.commit()
        log.info(
            "rotina da lista de espera: fazenda=%s origem=%s status=%s regras=%s na_janela=%s entraram=%s aviso=%s",
            fazenda_id, origem, status, resultado["regras"], resultado["regras_na_janela"], resultado["entraram"],
            aviso_emitido,
        )
        return {
            "executou": True, "motivo": status, "entraram": resultado["entraram"], "regras": resultado["regras"],
            "regras_na_janela": resultado["regras_na_janela"], "aviso_emitido": aviso_emitido, "erro": erro,
        }
    finally:
        fazenda_atual.reset(token)


def fazendas_com_rotina_ativa(session: Session) -> list[int]:
    """Fazendas com a rotina ligada. Enumera TODAS as fazendas — o loop de fundo
    chama com a conexão de manutenção. Vale a linha própria da fazenda; sem
    ela, vale o padrão global (o Painel CowData pode ligar para todas)."""
    from fazenda.models import Fazenda
    linhas = session.exec(select(ParametroFazenda).where(ParametroFazenda.chave == CHAVE_ATIVA)).all()
    global_ligada = any(l.fazenda_id is None and _bool(l) for l in linhas)
    proprias = {l.fazenda_id: _bool(l) for l in linhas if l.fazenda_id is not None}
    if not global_ligada:
        return sorted(f for f, ligada in proprias.items() if ligada)
    todas = session.exec(select(Fazenda.id)).all()
    return sorted(f for f in todas if proprias.get(f, True))


def executar_todas_as_fazendas(session: Session, hoje: date | None = None, agora: datetime | None = None) -> dict:
    """Passada diária do loop de fundo. Fazenda que já rodou hoje (outra
    instância, ou este mesmo loop numa volta anterior) é pulada."""
    resumo = {"processadas": 0, "puladas": 0, "entraram": 0, "erros": 0}
    for fazenda_id in fazendas_com_rotina_ativa(session):
        try:
            r = executar_fazenda(session, fazenda_id, "diaria", hoje, agora)
        except Exception:  # noqa: BLE001
            session.rollback()
            log.exception("rotina da lista de espera: fazenda %s", fazenda_id)
            resumo["erros"] += 1
            continue
        if r["executou"]:
            resumo["processadas"] += 1
            resumo["entraram"] += r["entraram"]
            if r["motivo"] == "erro":
                resumo["erros"] += 1
        else:
            resumo["puladas"] += 1
    return resumo


# ---------------------------------------------------------------------------
# Leitura (status por fazenda e resumo do Painel CowData) — não escrevem
# ---------------------------------------------------------------------------
def _iso(valor) -> str | None:
    return valor.isoformat() if valor is not None else None


def status_da_fazenda(session: Session, fazenda_id: int | None, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    cfg = config_da_fazenda(session, fazenda_id)
    estado = session.exec(
        select(RotinaListaEsperaEstado).where(RotinaListaEsperaEstado.fazenda_id == fazenda_id)
    ).first() if fazenda_id is not None else None
    tem_regras = bool(regras_de_vacina_ou_exame(session, fazenda_id)) if fazenda_id is not None else False
    return {
        **cfg,
        "tem_regras": tem_regras,
        "ultima_execucao_em": _iso(estado.ultima_execucao_em) if estado else None,
        "ultima_execucao_origem": estado.ultima_execucao_origem if estado else None,
        "ultima_execucao_status": estado.ultima_execucao_status if estado else None,
        "entraram": estado.ultima_execucao_entraram if estado else 0,
        "regras_avaliadas": estado.ultima_execucao_regras if estado else 0,
        "regras_na_janela": estado.ultima_execucao_regras_na_janela if estado else 0,
        "ultimo_erro": estado.ultimo_erro if estado else None,
        "ultimo_aviso_em": _iso(estado.ultimo_aviso_em) if estado else None,
        "aviso_de_hoje": bool(estado and estado.ultimo_aviso_em == hoje),
        "na_lista_de_espera": total_na_lista_de_espera(session, fazenda_id) if fazenda_id is not None else 0,
    }


def deve_mostrar_card_no_painel(session: Session, fazenda_id: int | None, total_lista: int) -> bool:
    """O card "Animais na lista de espera" do Painel só aparece com a rotina
    ativa E o aviso diário ligado E lista de espera não vazia."""
    if fazenda_id is None or total_lista <= 0:
        return False
    cfg = config_da_fazenda(session, fazenda_id)
    return bool(cfg["ativa"] and cfg["aviso_diario"])


def resumo_global(session: Session, hoje: date | None = None) -> dict:
    """Painel CowData (admin global, somente leitura): última execução, quantas
    fazendas processadas hoje e os erros."""
    from fazenda.models import Fazenda
    hoje = hoje or date.today()
    ativas = fazendas_com_rotina_ativa(session)
    nomes = {f.id: f.nome for f in session.exec(select(Fazenda)).all()}
    ids_ativos = set(ativas)
    estados = {
        e.fazenda_id: e for e in session.exec(select(RotinaListaEsperaEstado)).all() if e.fazenda_id in ids_ativos
    }
    ultima = max((e.ultima_execucao_em for e in estados.values() if e.ultima_execucao_em), default=None)
    fazendas = []
    for fid in ativas:
        e = estados.get(fid)
        fazendas.append({
            "fazenda_id": fid, "fazenda_nome": nomes.get(fid, f"Fazenda {fid}"),
            "ultima_execucao_em": _iso(e.ultima_execucao_em) if e else None,
            "status": e.ultima_execucao_status if e else None, "entraram": e.ultima_execucao_entraram if e else 0,
            "ultimo_erro": e.ultimo_erro if e else None,
        })
    return {
        "fazendas_ativas": len(ativas),
        "fazendas_processadas_hoje": sum(
            1 for e in estados.values() if e.ultima_execucao_em and e.ultima_execucao_em.date() == hoje
        ),
        "ultima_execucao_em": _iso(ultima),
        "entraram_ultima_passada": sum(e.ultima_execucao_entraram for e in estados.values()),
        "erros": [f for f in fazendas if f["status"] == "erro"],
        "fazendas": fazendas,
    }
