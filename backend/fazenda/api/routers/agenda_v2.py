"""
Agenda v2 (fatia 10) — endpoints de LEITURA das duas sub-abas + configuração
do repasse.

  GET  /agenda/dia        Dia a dia: tarefas atrasadas, de hoje e dos próximos
                          dias (lista/semana/mês). Sem cards, sem candidatas,
                          sem lista de espera (R1: animal na janela NUNCA é
                          tarefa).
  GET  /agenda/painel     Painel: tudo o que estava nos cards da Agenda antiga
                          (candidatas IATF, BST, pendências, estoque, contas a
                          pagar, comunicados) + atalho da lista de espera + o
                          resumo do repasse.
  GET  /agenda/projecao   Programação projetada (30/60/90 dias): repasse, BST,
                          IATF, vacinas, exames, estoque, pendências — só
                          números por semana, nunca a lista de animais.
  GET/PUT /agenda/repasse/config, GET /agenda/repasse/produtos,
  POST /agenda/repasse/produtos/{id}/classificar
                          Detecção de cio de repasse configurável por fazenda.

Os três GET reutilizam o motor existente (`calcular_agenda`) e NÃO escrevem no
banco (a escrita continua em POST /agenda/materializar). Tudo escopado pela
fazenda atual.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.agenda import (
    MODULO_TECNICO_PARA_COMERCIAL, _model_to_dict, _modulos_liberados, calcular_agenda,
)
from fazenda.auth import (
    Usuario, fazenda_tem_modulo_contratado, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita,
)
from fazenda.database import get_session
from fazenda.models import (
    Animal, CalendarioSanitario, CronogramaSanitario, CronogramaSanitarioAnimal, Estoque, EventoSanitario,
    ProtocoloIatfAplicacao, Servico,
)
from fazenda.rules import repasse as repasse_rules
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro

router = APIRouter(prefix="/agenda", tags=["agenda-v2"])

DIAS_JANELA_PADRAO = 10          # mesma janela da Agenda antiga ("próximos 10 dias")
HORIZONTES = (7, 30, 60, 90)


# ── helpers ──────────────────────────────────────────────────────────────────
def _modulos(session: Session, usuario: Usuario, fazenda_id: int | None) -> set[str]:
    """Mesma dupla checagem do `calcular_agenda` (funcionário E fazenda)."""
    liberados = _modulos_liberados(usuario)
    return {
        m for m in liberados
        if MODULO_TECNICO_PARA_COMERCIAL.get(m) is None
        or fazenda_tem_modulo_contratado(session, fazenda_id, MODULO_TECNICO_PARA_COMERCIAL[m])
    }


def _semanas(hoje: date, ate: date) -> list[date]:
    """Segundas-feiras das semanas que cobrem [hoje, ate]."""
    ini = hoje - timedelta(days=hoje.weekday())
    n = (ate - ini).days // 7 + 1
    return [ini + timedelta(days=7 * i) for i in range(n)]


def _por_semana(datas_e_pesos: list[tuple[date, int]], semanas: list[date]) -> list[int]:
    saida = [0] * len(semanas)
    for d, peso in datas_e_pesos:
        i = (d - semanas[0]).days // 7
        if 0 <= i < len(saida):
            saida[i] += peso
    return saida


def _eh_comunicado(e: dict) -> bool:
    return bool(e.get("comunicado"))


def _pendencias(eventos: list[dict], hoje: date) -> dict:
    atrasados = [e for e in eventos if not _eh_comunicado(e) and e["data"] < hoje.isoformat()]
    por_cat: dict[str, int] = defaultdict(int)
    for e in atrasados:
        por_cat[e.get("categoria") or "Outros"] += 1
    mais_antiga = min((e["data"] for e in atrasados), default=None)
    return {
        "n": len(atrasados),
        "por_categoria": dict(por_cat),
        "mais_antiga_dias": (hoje - date.fromisoformat(mais_antiga)).days if mais_antiga else None,
    }


# ── GET /agenda/dia ──────────────────────────────────────────────────────────
@router.get("/dia")
def agenda_dia(
    data: date | None = None,
    ate: date | None = None,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Dia a dia: atrasadas (todas), hoje e dias seguintes até `ate` (padrão
    +10 dias). Só tarefas (`eventos`); os comunicados vão como contagem. Não
    devolve candidatas, listas de BST nem lista de espera — isso é do Painel."""
    hoje = data or date.today()
    limite = ate or hoje + timedelta(days=DIAS_JANELA_PADRAO)
    if limite < hoje:
        raise HTTPException(status_code=422, detail="`ate` não pode ser anterior a `data`.")
    dias = max(DIAS_JANELA_PADRAO, (limite - hoje).days)
    base = calcular_agenda(data=hoje, dias=dias, session=session, usuario=usuario, fazenda_id=fazenda_id)
    iso_hoje, iso_limite = hoje.isoformat(), limite.isoformat()
    tarefas = [e for e in base["eventos"] if not _eh_comunicado(e) and e["data"] <= iso_limite]
    sete = (hoje + timedelta(days=7)).isoformat()
    return {
        "data_referencia": base["data_referencia"],
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "ate": iso_limite,
        "resumo": {
            "atrasadas": sum(1 for e in tarefas if e["data"] < iso_hoje),
            "hoje_total": sum(1 for e in tarefas if e["data"] == iso_hoje),
            "proximos_7d": sum(1 for e in tarefas if iso_hoje < e["data"] <= sete),
            "avisos": sum(1 for e in base["eventos"] if _eh_comunicado(e)),
            # selo da sub-aba Painel (estoque negativo/abaixo do mínimo) sem pedir o Painel inteiro
            "alertas_estoque": len(base["estoque_negativo"]) + len(base["estoque_abaixo_minimo"]),
        },
        "eventos": tarefas,
        "hormonios_check": base["hormonios_check"],
        "proxima_visita_iatf": base["proxima_visita_iatf"],
        "proxima_visita_bst": base["proxima_visita_bst"],
        "diaria_auditorias_pendentes": base["diaria_auditorias_pendentes"],
    }


# ── GET /agenda/painel ───────────────────────────────────────────────────────
def resumo_repasse(session: Session, fazenda_id: int | None, hoje: date, horizonte: int = 30) -> dict:
    cfg = repasse_rules.ler_config(session, fazenda_id)
    produto = repasse_rules.produto_da_config(session, cfg)
    calc = _checagens_repasse(session, fazenda_id, cfg, hoje, hoje + timedelta(days=horizonte))
    return {**cfg, "produto": produto, "horizonte_dias": horizonte, **calc["resumo"]}


def _checagens_repasse(session: Session, fazenda_id: int | None, cfg: dict, hoje: date, ate: date) -> dict:
    """Checagens de repasse previstas em [hoje, ate]. Cálculo por serviço
    (último de cada vaca ativa); as vacas que ainda estão em protocolo IATF
    (Dia 11 futuro) entram como ESTIMADAS (Dia 11 + dias)."""
    if not cfg.get("usar"):
        return {"resumo": {"checagens": 0, "vacas": 0, "estimadas": 0, "proxima": None}, "datas": [], "estimadas": []}
    q_animais = select(Animal.numero).where(Animal.ativo == True)  # noqa: E712
    q_serv = select(Servico).where(Servico.ult_ocorrencia == 1)
    if fazenda_id is not None:
        q_animais = q_animais.where(Animal.fazenda_id == fazenda_id)
        q_serv = q_serv.where(Servico.fazenda_id == fazenda_id)
    ativos = set(session.exec(q_animais).all())
    servicos = [_model_to_dict(s) for s in session.exec(q_serv).all() if s.numero_matriz in ativos]
    reais = repasse_rules.projetar(servicos, cfg, hoje, ate)

    estimadas: list[tuple[date, str]] = []
    if cfg["quem_entra"] != "monta_natural":
        q_ap = select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.dia == 11, ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
            ProtocoloIatfAplicacao.data_prevista >= hoje,
        )
        if fazenda_id is not None:
            q_ap = q_ap.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
        for ap in session.exec(q_ap).all():
            if ap.numero_matriz not in ativos:
                continue
            for d in repasse_rules.datas_checagem(ap.data_prevista, cfg):
                if hoje <= d <= ate:
                    estimadas.append((d, ap.numero_matriz))
    datas = [c["data"] for c in reais] + [d for d, _ in estimadas]
    return {
        "resumo": {
            "checagens": len(datas),
            "vacas": len({c["numero"] for c in reais} | {n for _, n in estimadas}),
            "estimadas": len(estimadas),
            "proxima": min(datas).isoformat() if datas else None,
        },
        "datas": [c["data"] for c in reais],
        "estimadas": [d for d, _ in estimadas],
    }


@router.get("/painel")
def agenda_painel(
    data: date | None = None,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Painel: o estado de AGORA, agrupado em Reprodução · Sanidade · Estoque e
    gestão. As chaves planas repetem as da Agenda antiga (o `PainelLancarBst`
    lê `bst_elegiveis` etc.). A projeção do futuro vem de /agenda/projecao."""
    hoje = data or date.today()
    fazenda_id_ = fazenda_id
    base = calcular_agenda(data=hoje, dias=DIAS_JANELA_PADRAO, session=session, usuario=usuario, fazenda_id=fazenda_id_)
    modulos = _modulos(session, usuario, fazenda_id_)
    lista_espera = base["lista_espera_sanitaria"]
    resumo_rep = resumo_repasse(session, fazenda_id_, hoje) if "reproducao" in _modulos_liberados(usuario) else None
    return {
        "data_referencia": base["data_referencia"],
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "candidatas_iatf": base["candidatas_iatf"],
        "necessidade_iatf": base["necessidade_iatf"],
        "proxima_visita_iatf": base["proxima_visita_iatf"],
        "proxima_visita_bst": base["proxima_visita_bst"],
        "intervalo_bst": base["intervalo_bst"],
        "bst_elegiveis": base["bst_elegiveis"],
        "bst_excluidos": base["bst_excluidos"],
        "bst_nunca_aplicados": base["bst_nunca_aplicados"],
        "contas_a_pagar": base["contas_a_pagar"],
        "estoque_negativo": base["estoque_negativo"],
        "estoque_abaixo_minimo": base["estoque_abaixo_minimo"],
        "hormonios_check": base["hormonios_check"],
        "comunicados": [e for e in base["eventos"] if _eh_comunicado(e)],
        "pendencias": _pendencias(base["eventos"], hoje),
        "lista_espera_sanitaria": lista_espera,
        "lista_espera_total": sum(r.get("quantidade") or 0 for r in lista_espera),
        "repasse": resumo_rep,
        "totais": base["totais"],
        "modulos": sorted(m for m in modulos if m in ("reproducao", "sanidade", "estoque", "financeiro")),
    }


# ── GET /agenda/projecao ─────────────────────────────────────────────────────
def _grupo_do_evento(e: dict) -> str:
    desc = (e.get("descricao") or "").lower()
    tipo = e.get("tipo") or ""
    if "detector de cio" in desc or "scratch" in desc or "cio de repasse" in desc:
        return "repasse"
    if tipo == "protocolo_iatf":
        return "iatf"
    if tipo == "bst_aplicacao":
        return "bst"
    if tipo in ("semen_minimo",):
        return "estoque"
    if e.get("categoria") == "Gestão/Financeiro":
        return "pendencias"
    if e.get("categoria") == "Reprodutivo":
        return "reproducao"
    return "outros"


@router.get("/projecao")
def agenda_projecao(
    dias: int = 30,
    data: date | None = None,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Programação projetada. `dias` = horizonte (7/30/60/90). Devolve, por
    card, totais e `por_semana[]` (mesmo tamanho de `semanas[]`); nenhum card
    lista brinco de animal."""
    if dias not in HORIZONTES:
        raise HTTPException(status_code=422, detail=f"Horizonte inválido. Use um de: {', '.join(map(str, HORIZONTES))}.")
    hoje = data or date.today()
    ate = hoje + timedelta(days=dias)
    semanas = _semanas(hoje, ate)
    base = calcular_agenda(data=hoje, dias=dias, session=session, usuario=usuario, fazenda_id=fazenda_id)
    liberados = _modulos_liberados(usuario)
    modulos = _modulos(session, usuario, fazenda_id)
    q = fazenda_id
    cards: dict = {}

    # Repasse ───────────────────────────────────────────────────────────────
    if "reproducao" in liberados:
        cfg = repasse_rules.ler_config(session, q)
        calc = _checagens_repasse(session, q, cfg, hoje, ate)
        produto = repasse_rules.produto_da_config(session, cfg)
        demanda = calc["resumo"]["checagens"]
        cards["repasse"] = {
            "usar": cfg["usar"], "configurado": cfg["configurado"], "mostrar_na_agenda": cfg["mostrar_na_agenda"],
            "quem_entra": cfg["quem_entra"], "dias_apos_servico": cfg["dias_apos_servico"],
            "repetir": cfg["repetir"], "repetir_cada_dias": cfg["repetir_cada_dias"], "repeticoes": cfg["repeticoes"],
            **calc["resumo"],
            "por_semana": _por_semana([(d, 1) for d in calc["datas"]] + [(d, 1) for d in calc["estimadas"]], semanas),
            "produto": ({**produto, "demanda": demanda, "falta": max(0, demanda - (produto["quantidade"] or 0))} if produto else None),
            "link": "/protocolos",
        }

        # BST ──────────────────────────────────────────────────────────────
        prox_bst = base["proxima_visita_bst"]
        intervalo = base["intervalo_bst"] or 14
        aptas = len(base["bst_elegiveis"])
        visitas: list[date] = []
        if prox_bst:
            d = date.fromisoformat(prox_bst)
            while d <= ate:
                if d >= hoje:
                    visitas.append(d)
                d += timedelta(days=intervalo)
        cards["bst"] = {
            "aptas": aptas, "excluidas": len(base["bst_excluidos"]), "nunca_aplicadas": len(base["bst_nunca_aplicados"]),
            "intervalo_dias": intervalo, "proxima": prox_bst, "visitas": [d.isoformat() for d in visitas],
            "total": aptas * len(visitas),
            "por_semana": _por_semana([(d, aptas) for d in visitas], semanas),
        }

        # IATF ─────────────────────────────────────────────────────────────
        q_ap = select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
            ProtocoloIatfAplicacao.data_prevista >= hoje, ProtocoloIatfAplicacao.data_prevista <= ate,
        )
        if q is not None:
            q_ap = q_ap.where(ProtocoloIatfAplicacao.fazenda_id == q)
        etapas = session.exec(q_ap).all()
        cards["iatf"] = {
            "etapas": len(etapas), "protocolos": len({a.lancamento_id for a in etapas}),
            "por_semana": _por_semana([(a.data_prevista, 1) for a in etapas], semanas),
            "proxima_visita": base["proxima_visita_iatf"], "candidatas": len(base["candidatas_iatf"]),
        }

    # Vacinas e exames (agendamentos do preventivo) ────────────────────────
    if "sanidade" in modulos:
        q_c = (
            select(CronogramaSanitario, CalendarioSanitario)
            .join(CalendarioSanitario, CalendarioSanitario.id == CronogramaSanitario.calendario_sanitario_id)
            .where(CronogramaSanitario.status.in_(("agendado", "aguardando_confirmacao")))
            .where(CronogramaSanitario.data_evento >= hoje, CronogramaSanitario.data_evento <= ate)
        )
        if q is not None:
            q_c = q_c.where(CalendarioSanitario.fazenda_id == q)
        pares = session.exec(q_c).all()
        eventos_san = {e.id: e for e in session.exec(
            select(EventoSanitario).where(EventoSanitario.fazenda_id == q) if q is not None else select(EventoSanitario)
        ).all()}
        incluidos: dict[int, int] = defaultdict(int)
        if pares:
            for linha in session.exec(
                select(CronogramaSanitarioAnimal)
                .where(CronogramaSanitarioAnimal.cronograma_id.in_([c.id for c, _ in pares]))
                .where(CronogramaSanitarioAnimal.status == "incluido")
            ).all():
                incluidos[linha.cronograma_id] += 1
        grupos: dict[str, list[dict]] = {"vacinas": [], "exames": []}
        for cron, cal in pares:
            ev = eventos_san.get(cal.evento_sanitario_id)
            chave = "exames" if ev is not None and ev.categoria_preventiva == "exame" else "vacinas"
            grupos[chave].append({
                "cronograma_id": cron.id, "nome": ev.nome if ev else "Evento sanitário", "data": cron.data_evento.isoformat(),
                "hora": cron.hora, "n_animais": incluidos.get(cron.id, 0), "checklist_pendente": None,
            })
        for chave, itens in grupos.items():
            itens.sort(key=lambda i: (i["data"], i["hora"] or ""))
            cards[chave] = {
                "agendadas": len(itens),
                "n_animais": sum(i["n_animais"] for i in itens),
                "por_semana": _por_semana([(date.fromisoformat(i["data"]), 1) for i in itens], semanas),
                "proximas": itens[:5],
                "link": "/protocolos",
            }
        # Só contagem da lista de espera (R1): nenhum animal sai daqui.
        cards["lista_espera"] = {
            "n": sum(r.get("quantidade") or 0 for r in base["lista_espera_sanitaria"]),
            "protocolos": len(base["lista_espera_sanitaria"]), "link": "/protocolos",
        }

    # Estoque ──────────────────────────────────────────────────────────────
    if "estoque" in modulos:
        rup = []
        rep = cards.get("repasse")
        if rep and rep.get("produto") and rep["produto"]["falta"] > 0:
            rup.append({
                "item": rep["produto"]["nome"], "unidade": rep["produto"]["unidade"], "saldo": rep["produto"]["quantidade"],
                "demanda": rep["produto"]["demanda"], "motivo": "repasse",
            })
        cards["estoque"] = {
            "negativo": len(base["estoque_negativo"]), "abaixo_minimo": len(base["estoque_abaixo_minimo"]),
            "itens": base["estoque_negativo"] + base["estoque_abaixo_minimo"],
            "rupturas": rup,
        }

    # Pendências / contas ──────────────────────────────────────────────────
    contas = base["contas_a_pagar"]
    pend = _pendencias(base["eventos"], hoje)
    cards["pendencias"] = {
        "atrasadas": pend["n"],
        "contas": len(contas),
        "valor_contas": round(sum(max(0.0, (c.get("valor_total") or 0) - (c.get("valor_pago") or 0)) for c in contas), 2),
        "por_semana": _por_semana(
            [(c["data_vencimento"] if isinstance(c["data_vencimento"], date) else date.fromisoformat(str(c["data_vencimento"])[:10]), 1)
             for c in contas if c.get("data_vencimento")], semanas,
        ),
    }

    # Programação (linhas) — só números por (data, tipo, texto) ─────────────
    contagem: dict[tuple, dict] = {}
    for e in base["eventos"]:
        if _eh_comunicado(e) or not (hoje.isoformat() <= e["data"] <= ate.isoformat()):
            continue
        if str(e.get("tipo") or "").startswith("cronograma_sanitario"):
            continue
        chave = (e["data"], _grupo_do_evento(e), e.get("descricao") or "")
        linha = contagem.setdefault(chave, {"data": e["data"], "grupo": chave[1], "descricao": chave[2], "n": 0, "lote": e.get("lote")})
        linha["n"] += 1
    linhas = sorted(contagem.values(), key=lambda l: (l["data"], l["grupo"]))
    for grupo in ("vacinas", "exames"):
        for item in (cards.get(grupo) or {}).get("proximas", []):
            linhas.append({"data": item["data"], "grupo": grupo, "descricao": item["nome"], "n": item["n_animais"], "lote": None})
    linhas.sort(key=lambda l: (l["data"], l["grupo"]))

    return {
        "de": hoje.isoformat(), "ate": ate.isoformat(), "dias": dias,
        "semanas": [s.isoformat() for s in semanas],
        "cards": cards,
        "linhas": linhas[:300],
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


# ── Detecção de cio de repasse: configuração por fazenda ─────────────────────
class RepasseConfigIn(BaseModel):
    usar: bool = True
    estoque_id: int | None = None
    dias_apos_servico: int = repasse_rules.DIAS_PADRAO
    repetir: bool = False
    repetir_cada_dias: int = 21
    repeticoes: int = 1
    mostrar_na_agenda: bool = True
    quem_entra: str = "todas"


def _exigir_pode_configurar(usuario: Usuario) -> None:
    liberados = _modulos_liberados(usuario)
    if not ({"sanidade", "reproducao"} & liberados):
        raise HTTPException(status_code=403, detail="Sem permissão para configurar a detecção de cio de repasse.")


@router.get("/repasse/config")
def ler_repasse_config(
    session: Session = Depends(get_session), usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cfg = repasse_rules.ler_config(session, fazenda_id)
    return {
        **cfg, "produto": repasse_rules.produto_da_config(session, cfg),
        "categoria_produto": repasse_rules.CATEGORIA_PRODUTO_REPASSE,
        "ciclo_sugerido": list(repasse_rules.CICLO_SUGERIDO),
        "quem_entra_opcoes": [{"valor": k, "rotulo": v} for k, v in repasse_rules.ROTULO_QUEM.items()],
    }


@router.put("/repasse/config")
def salvar_repasse_config(
    dados: RepasseConfigIn, session: Session = Depends(get_session), usuario: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    _exigir_pode_configurar(usuario)
    try:
        cfg, avisos = repasse_rules.salvar_config(session, fazenda_id, dados.model_dump(), usuario_id_seguro(usuario.id))
    except repasse_rules.RepasseError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {**cfg, "produto": repasse_rules.produto_da_config(session, cfg), "avisos": avisos}


@router.get("/repasse/produtos")
def listar_produtos_repasse(
    session: Session = Depends(get_session), usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Itens de estoque já classificados na categoria "Detecção de cio de
    repasse" e, à parte, os demais itens ativos (candidatos a classificar)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    q = select(Estoque)
    if fazenda_id is not None:
        q = q.where(Estoque.fazenda_id == fazenda_id)
    itens = [e for e in session.exec(q).all() if e.ativo is not False]
    da_categoria = [
        {"id": e.id, "nome": e.nome, "quantidade": e.quantidade, "unidade": e.unidade}
        for e in itens if repasse_rules.categoria_e_repasse(e.categoria)
    ]
    outros = [
        {"id": e.id, "nome": e.nome, "categoria": e.categoria}
        for e in sorted(itens, key=lambda x: x.nome.lower()) if not repasse_rules.categoria_e_repasse(e.categoria)
    ]
    return {"categoria": repasse_rules.CATEGORIA_PRODUTO_REPASSE, "produtos": da_categoria, "outros_itens": outros}


@router.post("/repasse/produtos/{estoque_id}/classificar")
def classificar_produto_repasse(
    estoque_id: int, session: Session = Depends(get_session), usuario: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Classifica UM item de estoque na categoria de repasse (só o campo
    `categoria`; o resto do cadastro não é tocado)."""
    _exigir_pode_configurar(usuario)
    item = session.get(Estoque, estoque_id)
    if item is None or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado.")
    item.categoria = repasse_rules.CATEGORIA_PRODUTO_REPASSE
    session.add(item)
    session.commit()
    return {"id": item.id, "nome": item.nome, "categoria": item.categoria}
