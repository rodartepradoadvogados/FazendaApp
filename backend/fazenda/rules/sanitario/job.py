"""
Rotina do sanitário — o job diário e o fechamento automático dos dias.

`executar_diaria(session, fazenda_id, agora)` roda UMA vez por dia LOCAL
(America/Sao_Paulo — às 22h de Brasília ainda é "hoje", embora o servidor em
UTC já esteja no dia seguinte), com lock por UPDATE atômico em
`sanitario_job_estado`. Passos:
  1. `recalcular` tudo (mudança de categoria por idade é absorvida aqui);
  2. notas "aglomerou" (só pelo mínimo da caixa; uma por caixa × ciclo,
     sem o N na chave) e "fim de janela";
  3. véspera dos dias de amanhã (para todos os usuários do app);
  4. "animal saiu da janela depois de marcado o dia";
  5. prazos legais (atestado a vencer, comprovação periódica);
  6. caixas ativas com carência sem aceite;
  7. celulares com fila e sem contato há mais de N horas (aviso ao admin);
  8. fechamento automático: o dia D fecha às 23:59 do dia D+1 (local).

`tick(session, agora)` é o que o loop de 30 min do main.py chama: fecha os
dias vencidos de todas as fazendas e roda a diária de quem ainda não rodou.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, update
from sqlmodel import Session, select

from fazenda.rules.datas import FUSO_FAZENDA, agora_local, hoje_local
from fazenda.rules.sanitario.notas import resolver_notas, upsert_nota

logger = logging.getLogger(__name__)

LOCK_MINUTOS = 15
AVISO_ATESTADO_DIAS = 7


def _utc_ingenuo(agora: Optional[datetime]) -> datetime:
    if agora is None:
        return datetime.utcnow()
    if agora.tzinfo is None:
        return agora
    return agora.astimezone(timezone.utc).replace(tzinfo=None)


def nome_dia(session: Session, dia) -> str:
    """"Vacina · B19 · 25/12" / "Exame · Exame TB + 1 · 03/04"."""
    from fazenda.models import SanitarioCaixa, SanitarioDiaCaixa

    nomes = [
        (c.nome_curto or c.nome) for c in session.exec(
            select(SanitarioCaixa).join(SanitarioDiaCaixa, SanitarioDiaCaixa.caixa_id == SanitarioCaixa.id).where(
                SanitarioDiaCaixa.dia_id == dia.id, SanitarioDiaCaixa.fazenda_id == dia.fazenda_id,
            ).order_by(SanitarioDiaCaixa.id)
        ).all()
    ]
    rot = " e ".join(nomes) if len(nomes) <= 2 else f"{nomes[0]} + {len(nomes) - 1}"
    tipo = "Exame" if dia.tipo == "exame" else "Vacina"
    return f"{tipo} · {rot} · {dia.data.strftime('%d/%m')}" if rot else f"{tipo} · {dia.data.strftime('%d/%m')}"


# ════════════════════════════════════════════════════════════════════════════
# Fechamento automático
# ════════════════════════════════════════════════════════════════════════════
def fechar_dias_vencidos(session: Session, fazenda_id: int, agora: Optional[datetime] = None) -> int:
    """Fecha o dia D quando o relógio LOCAL passa de D+1 23:59. Os pendentes
    voltam para a caixa (o motor os devolve sozinho: o dia deixa de estar
    aberto) e uma nota pede a conferência. O que o celular mandar depois
    entra como "lançado após o fechamento" (registrar, F5). Não dá commit."""
    from fazenda.models import SanitarioDia, SanitarioDiaItem, SanitarioLog

    local = agora_local(agora)
    limite = (local - timedelta(days=1)).date()
    # D fecha quando local > D+1 23:59 -> D < local.date() - 1, ou D == local.date()-1 e já passou das 23:59
    candidatos = session.exec(select(SanitarioDia).where(
        SanitarioDia.fazenda_id == fazenda_id, SanitarioDia.estado.in_(("marcado", "em_execucao")),
        SanitarioDia.data <= limite,
    )).all()
    agora_utc = _utc_ingenuo(agora)
    n = 0
    afetados: set[int] = set()
    for dia in candidatos:
        fecha_em = datetime.combine(dia.data + timedelta(days=1), time(23, 59), tzinfo=FUSO_FAZENDA)
        if local <= fecha_em:
            continue
        pend = session.exec(select(SanitarioDiaItem).where(
            SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
            SanitarioDiaItem.estado == "pendente",
        )).all()
        for it in pend:
            it.estado = "faltou"
            session.add(it)
            afetados.add(it.animal_id)
        dia.estado, dia.fechamento_auto, dia.fechado_em = "fechado", True, agora_utc
        dia.versao_lock = (dia.versao_lock or 1) + 1
        session.add(dia)
        nome = nome_dia(session, dia)
        session.add(SanitarioLog(
            fazenda_id=fazenda_id, tipo="dia.fechado_auto", dia_id=dia.id, em=agora_utc,
            texto_livre=f"{nome} fechado automaticamente às 23:59 do dia seguinte: {len(pend)} pendente(s) voltaram para a caixa.",
            payload={"faltantes": [it.animal_id for it in pend]},
        ))
        upsert_nota(
            session, fazenda_id, f"fechamento_auto:{dia.id}", tipo="fechamento_auto", dia_id=dia.id,
            titulo=f"{nome} foi fechado automaticamente — conferir",
            texto=f"{len(pend)} animal(is) não registrado(s) voltaram para a caixa." if pend else "Todos registrados.",
            data_ref=hoje_local(agora), so_admin=True,
        )
        n += 1
    if afetados:
        from fazenda.rules.sanitario.motor import recalcular
        recalcular(session, fazenda_id, animal_ids=afetados, motivo="fechamento_auto", hoje=hoje_local(agora))
    return n


# ════════════════════════════════════════════════════════════════════════════
# Passos da diária
# ════════════════════════════════════════════════════════════════════════════
def notas_aglomeracao(session: Session, fazenda_id: int, hoje: date) -> dict:
    """"Vacina X aglomerou N animais — marcar o dia" para os administradores.
    Só pelo mínimo da CAIXA (inclusive na contínua, como a B19). Chave sem o
    N: `aglo:{caixa}:{ciclo}` (período) ou uma nota aberta por vez (contínua/
    evento). Abaixo do mínimo, a nota aberta é resolvida."""
    from fazenda.models import SanitarioSituacao
    from fazenda.rules.sanitario.contexto import carregar_caixas

    out = {"aglomerou": 0, "fim_janela": 0}
    caixas = carregar_caixas(session, fazenda_id, so_ativas=True)
    if not caixas:
        return out
    rows = session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fazenda_id, SanitarioSituacao.estado.in_(("janela", "aviso", "atrasada")),
    )).all()
    por_caixa: dict[int, list] = defaultdict(list)
    for r in rows:
        por_caixa[r.caixa_id].append(r)
    for cx in caixas:
        membros = por_caixa.get(cx.caixa_id, [])
        animais = sorted({r.animal_id for r in membros})
        n = len(animais)
        prefixo = f"aglo:{cx.caixa_id}:"
        if n == 0 or n < max(int(cx.aglo_min or 1), 1):
            resolver_notas(session, fazenda_id, prefixo=prefixo)
        else:
            if cx.eh_periodo:
                foco = [r.ciclo_chave for r in membros if r.estado in ("aviso", "janela")] or [r.ciclo_chave for r in membros]
                ciclo = Counter(foco).most_common(1)[0][0]
                chave = f"{prefixo}{ciclo}"
            else:
                from fazenda.models import SanitarioNotaAgenda
                aberta = session.exec(select(SanitarioNotaAgenda).where(
                    SanitarioNotaAgenda.fazenda_id == fazenda_id,
                    SanitarioNotaAgenda.chave_dedupe.startswith(prefixo),
                    SanitarioNotaAgenda.resolvida_em == None,  # noqa: E711
                )).first()
                ciclo = membros[0].ciclo_chave
                chave = aberta.chave_dedupe if aberta else f"{prefixo}{hoje.isoformat()}"
            tipo = "Exame" if cx.eh_exame else "Vacina"
            _nota, criada = upsert_nota(
                session, fazenda_id, chave, tipo="aglomerou", caixa_id=cx.caixa_id, ciclo_chave=ciclo,
                titulo=f"{tipo} {cx.rotulo} aglomerou {n} animais — marcar o dia",
                texto=f"Mínimo da caixa: {cx.aglo_min}.", dados={"n": n, "animal_ids": animais},
                so_admin=True, data_ref=hoje,
            )
            out["aglomerou"] += int(criada)
        if cx.aviso_fim_janela_dias:
            perto = [r for r in membros if r.estado == "janela" and r.janela_fim
                     and (r.janela_fim - hoje).days <= int(cx.aviso_fim_janela_dias)]
            if perto and n < max(int(cx.aglo_min or 1), 1):
                ciclo = perto[0].ciclo_chave
                fim = min(r.janela_fim for r in perto)
                _nota, criada = upsert_nota(
                    session, fazenda_id, f"fimjan:{cx.caixa_id}:{ciclo}", tipo="fim_janela", caixa_id=cx.caixa_id,
                    ciclo_chave=ciclo, titulo=f"{cx.rotulo}: janela fecha em {fim.strftime('%d/%m')}",
                    texto=f"{len({r.animal_id for r in perto})} animal(is) ainda sem receber (abaixo do mínimo de {cx.aglo_min}).",
                    dados={"animal_ids": sorted({r.animal_id for r in perto})}, so_admin=True, data_ref=hoje,
                )
                out["fim_janela"] += int(criada)
    return out


def notas_vespera(session: Session, fazenda_id: int, hoje: date) -> int:
    from fazenda.models import SanitarioDia

    n = 0
    for dia in session.exec(select(SanitarioDia).where(
        SanitarioDia.fazenda_id == fazenda_id, SanitarioDia.estado == "marcado",
        SanitarioDia.data == hoje + timedelta(days=1),
    )).all():
        nome = nome_dia(session, dia)
        _nota, criada = upsert_nota(
            session, fazenda_id, f"vespera:{dia.id}", tipo="vespera", dia_id=dia.id,
            titulo=f"Amanhã: {nome}", texto=f"Às {dia.hora}." if dia.hora else None,
            so_admin=False, data_ref=hoje,
        )
        n += int(criada)
    return n


def verificar_dias_abertos(session: Session, fazenda_id: int, animal_ids=None, hoje: Optional[date] = None) -> int:
    """Animal que veio pela janela e deixou de cumprir a regra na data do dia
    (pariu, passou da idade, mudou de categoria, saiu do rebanho): AVISA na
    Agenda e no dia — o produtor decide (nunca tira sozinho)."""
    from fazenda.models import SanitarioDia, SanitarioDiaItem
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
    from fazenda.rules.sanitario.motor import ok_na_data

    q = select(SanitarioDiaItem, SanitarioDia).where(
        SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == SanitarioDia.id,
        SanitarioDia.fazenda_id == fazenda_id, SanitarioDia.estado.in_(("marcado", "em_execucao")),
        SanitarioDiaItem.estado == "pendente", SanitarioDiaItem.origem == "janela",
    )
    if animal_ids is not None:
        ids = [int(i) for i in animal_ids]
        if not ids:
            return 0
        q = q.where(SanitarioDiaItem.animal_id.in_(ids))
    pares = session.exec(q).all()
    if not pares:
        return 0
    caixas = {cx.caixa_id: cx for cx in carregar_caixas(
        session, fazenda_id, caixa_ids={it.caixa_id for it, _ in pares}, so_ativas=False)}
    animais = carregar_animais(session, fazenda_id, animal_ids={it.animal_id for it, _ in pares}, hoje=hoje)
    n = 0
    for it, dia in pares:
        cx, a = caixas.get(it.caixa_id), animais.get(it.animal_id)
        if cx is None or a is None:
            continue
        # Avalia como se o animal NÃO estivesse no dia (senão sairia "marcada").
        a_sem = a
        if cx.caixa_id in a.dias:
            from dataclasses import replace
            a_sem = replace(a, dias={k: v for k, v in a.dias.items() if k != cx.caixa_id}, _cache_cat=a._cache_cat)
        r = ok_na_data(cx, a_sem, dia.data)
        if r.ok or r.kind == "aplicada":
            continue
        nome = nome_dia(session, dia)
        _nota, criada = upsert_nota(
            session, fazenda_id, f"saiu_janela:{dia.id}:{a.id}:{cx.caixa_id}", tipo="animal_saiu_janela",
            caixa_id=cx.caixa_id, dia_id=dia.id, titulo=f"{a.numero} saiu da janela de {cx.rotulo} ({nome})",
            texto=f"{a.numero}: {r.texto}. Decida se mantém no dia ou retira.",
            dados={"animal_id": a.id, "kind": r.kind}, so_admin=True, data_ref=a.hoje,
        )
        n += int(criada)
    return n


def notas_prazos_legais(session: Session, fazenda_id: int, hoje: date) -> int:
    from fazenda.models import SanitarioCaixa, SanitarioCaixaVersao, SanitarioPrazoLegal
    from fazenda.rules.sanitario.legal import deve_avisar, vencimento_comprovacao

    n = 0
    # Comprovação periódica (ex.: 180 dias) das caixas ativas que a pedem.
    for caixa, v in session.exec(select(SanitarioCaixa, SanitarioCaixaVersao).where(
        SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.estado == "ativa",
        SanitarioCaixaVersao.id == SanitarioCaixa.versao_atual_id, SanitarioCaixaVersao.fazenda_id == fazenda_id,
    )).all():
        if not v.legal_comprovacao:
            continue
        cumpridas = [p.cumprido_em for p in session.exec(select(SanitarioPrazoLegal).where(
            SanitarioPrazoLegal.fazenda_id == fazenda_id, SanitarioPrazoLegal.caixa_id == caixa.id,
            SanitarioPrazoLegal.tipo == "comprovacao", SanitarioPrazoLegal.estado == "cumprido",
        )).all() if p.cumprido_em]
        ultima = max(cumpridas) if cumpridas else caixa.ativada_em
        if ultima is None:
            continue
        # Já há uma comprovação em aberto (criada pelo registro da aplicação,
        # rules/sanitario/registro.py): não abre uma segunda.
        if session.exec(select(SanitarioPrazoLegal.id).where(
            SanitarioPrazoLegal.fazenda_id == fazenda_id, SanitarioPrazoLegal.caixa_id == caixa.id,
            SanitarioPrazoLegal.tipo == "comprovacao", SanitarioPrazoLegal.estado == "aberto",
        )).first() is not None:
            continue
        vence = vencimento_comprovacao(v.legal_comprovacao, ultima)
        ref = f"data:{vence.isoformat()}"
        prazo = session.exec(select(SanitarioPrazoLegal).where(
            SanitarioPrazoLegal.fazenda_id == fazenda_id, SanitarioPrazoLegal.tipo == "comprovacao",
            SanitarioPrazoLegal.caixa_id == caixa.id, SanitarioPrazoLegal.referencia_chave == ref,
        )).first()
        if prazo is None:
            prazo = SanitarioPrazoLegal(
                fazenda_id=fazenda_id, tipo="comprovacao", caixa_id=caixa.id, referencia_chave=ref, vence_em=vence,
                destinatario=(v.legal_atestado or {}).get("destinatario_texto"),
            )
            session.add(prazo)
            session.flush()
    for p in session.exec(select(SanitarioPrazoLegal).where(
        SanitarioPrazoLegal.fazenda_id == fazenda_id, SanitarioPrazoLegal.estado == "aberto",
    )).all():
        caixa = session.get(SanitarioCaixa, p.caixa_id)
        v = session.get(SanitarioCaixaVersao, caixa.versao_atual_id) if caixa and caixa.versao_atual_id else None
        aviso = AVISO_ATESTADO_DIAS
        if p.tipo == "comprovacao" and v is not None and v.legal_comprovacao:
            aviso = int(v.legal_comprovacao.get("aviso_dias") or 30)
        if not deve_avisar(p.vence_em, hoje, aviso):
            continue
        nome = caixa.nome_curto or caixa.nome if caixa else "caixa"
        o_que = "Atestado" if p.tipo == "atestado" else "Comprovação de vacinação"
        _nota, criada = upsert_nota(
            session, fazenda_id, f"prazo:{p.id}", tipo="prazo_legal", caixa_id=p.caixa_id,
            titulo=f"{o_que} {nome} vence em {p.vence_em.strftime('%d/%m/%Y')}",
            texto=f"Destinatário: {p.destinatario}." if p.destinatario else None,
            dados={"prazo_id": p.id}, so_admin=True, data_ref=hoje,
        )
        n += int(criada)
    return n


def notas_carencia_sem_aceite(session: Session, fazenda_id: int, hoje: date) -> int:
    from fazenda.models import SanitarioCaixa, SanitarioCaixaVersao, SanitarioCarenciaAceite

    n = 0
    for caixa, v in session.exec(select(SanitarioCaixa, SanitarioCaixaVersao).where(
        SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.estado == "ativa", SanitarioCaixa.tipo != "exame",
        SanitarioCaixaVersao.id == SanitarioCaixa.versao_atual_id, SanitarioCaixaVersao.fazenda_id == fazenda_id,
    )).all():
        chave = f"carencia:{v.id}"
        aceite = session.exec(select(SanitarioCarenciaAceite).where(
            SanitarioCarenciaAceite.fazenda_id == fazenda_id, SanitarioCarenciaAceite.escopo == "caixa_versao",
            SanitarioCarenciaAceite.caixa_versao_id == v.id,
        )).first()
        if aceite is not None:
            resolver_notas(session, fazenda_id, chave=chave)
            continue
        _nota, criada = upsert_nota(
            session, fazenda_id, chave, tipo="carencia_pendente", caixa_id=caixa.id,
            titulo=f"Carência de {caixa.nome_curto or caixa.nome} sem aceite do administrador",
            texto="Enquanto não houver aceite, o leite vai para o tanque e o log registra \"sem aceite\".",
            so_admin=True, data_ref=hoje,
        )
        n += int(criada)
    return n


def notas_celular_offline(session: Session, fazenda_id: int, agora: Optional[datetime] = None) -> int:
    from fazenda.models import SanitarioDispositivo, SanitarioParametros

    agora_utc = _utc_ingenuo(agora)
    par = session.exec(select(SanitarioParametros).where(SanitarioParametros.fazenda_id == fazenda_id)).first()
    horas = int(par.aviso_offline_horas if par and par.aviso_offline_horas else 24)
    n = 0
    for d in session.exec(select(SanitarioDispositivo).where(
        SanitarioDispositivo.fazenda_id == fazenda_id, SanitarioDispositivo.fila_pendentes > 0,
        SanitarioDispositivo.ultimo_contato_em != None,  # noqa: E711
        SanitarioDispositivo.ultimo_contato_em < agora_utc - timedelta(hours=horas),
    )).all():
        if d.aviso_admin_em is not None and d.aviso_admin_em >= d.ultimo_contato_em:
            continue
        desde = agora_local(d.ultimo_contato_em.replace(tzinfo=timezone.utc))
        upsert_nota(
            session, fazenda_id, f"offline:{d.id}:{d.ultimo_contato_em.isoformat()}", tipo="celular_offline",
            titulo=f"Celular {d.nome or d.dispositivo_uid}: {d.fila_pendentes} registro(s) sem enviar desde "
                   f"{desde.strftime('%d/%m %H:%M')}",
            dados={"dispositivo_id": d.id, "fila_pendentes": d.fila_pendentes}, so_admin=True,
            data_ref=hoje_local(agora),
        )
        d.aviso_admin_em = agora_utc
        session.add(d)
        n += 1
    return n


# ════════════════════════════════════════════════════════════════════════════
# Diária com lock
# ════════════════════════════════════════════════════════════════════════════
def _adquirir_lock(session: Session, fazenda_id: int, hoje: date, agora_utc: datetime, forcar: bool) -> bool:
    from fazenda.models import SanitarioJobEstado

    if session.exec(select(SanitarioJobEstado).where(SanitarioJobEstado.fazenda_id == fazenda_id)).first() is None:
        session.add(SanitarioJobEstado(fazenda_id=fazenda_id))
        try:
            session.commit()
        except Exception:  # corrida: outro processo criou a linha
            session.rollback()
    cond = [
        SanitarioJobEstado.fazenda_id == fazenda_id,
        or_(SanitarioJobEstado.em_execucao_ate == None, SanitarioJobEstado.em_execucao_ate < agora_utc),  # noqa: E711
    ]
    if not forcar:
        cond.append(or_(SanitarioJobEstado.ultima_diaria_em == None, SanitarioJobEstado.ultima_diaria_em < hoje))  # noqa: E711
    res = session.exec(update(SanitarioJobEstado).where(*cond).values(
        em_execucao_ate=agora_utc + timedelta(minutes=LOCK_MINUTOS), status="executando", atualizado_em=agora_utc,
    ))
    session.commit()
    return res.rowcount == 1


def executar_diaria(session: Session, fazenda_id: int, agora: Optional[datetime] = None,
                    forcar: bool = False) -> Optional[dict]:
    """Roda a diária da fazenda se ainda não rodou HOJE (dia local). Devolve
    as contagens, ou None quando não era a vez (já rodou / outro processo com
    o lock). Faz o próprio commit (é rotina de topo, não roda em requisição)."""
    from fazenda.models import SanitarioJobEstado
    from fazenda.rules.sanitario.motor import recalcular

    hoje = hoje_local(agora)
    agora_utc = _utc_ingenuo(agora)
    if not _adquirir_lock(session, fazenda_id, hoje, agora_utc, forcar):
        return None
    cont: dict = {}
    try:
        cont["recalcular"] = recalcular(session, fazenda_id, motivo="diaria", hoje=hoje)
        cont.update(notas_aglomeracao(session, fazenda_id, hoje))
        cont["vespera"] = notas_vespera(session, fazenda_id, hoje)
        cont["saiu_janela"] = verificar_dias_abertos(session, fazenda_id, hoje=hoje)
        cont["prazos"] = notas_prazos_legais(session, fazenda_id, hoje)
        cont["carencia"] = notas_carencia_sem_aceite(session, fazenda_id, hoje)
        cont["offline"] = notas_celular_offline(session, fazenda_id, agora)
        cont["fechados_auto"] = fechar_dias_vencidos(session, fazenda_id, agora)
        estado = session.exec(select(SanitarioJobEstado).where(SanitarioJobEstado.fazenda_id == fazenda_id)).one()
        estado.ultima_diaria_em, estado.em_execucao_ate = hoje, None
        estado.status, estado.erro, estado.contagens, estado.atualizado_em = "ok", None, cont, agora_utc
        session.add(estado)
        session.commit()
        return cont
    except Exception as erro:
        session.rollback()
        logger.exception("sanitario: diária da fazenda %s falhou", fazenda_id)
        estado = session.exec(select(SanitarioJobEstado).where(SanitarioJobEstado.fazenda_id == fazenda_id)).first()
        if estado is not None:
            estado.em_execucao_ate, estado.status = None, "erro"
            estado.erro, estado.atualizado_em = str(erro)[:1000], agora_utc
            session.add(estado)
            session.commit()
        raise


def tick(session: Session, agora: Optional[datetime] = None) -> dict:
    """Uma volta do loop (main.py, a cada 30 min), para todas as fazendas
    com caixa: fecha os dias vencidos e roda a diária de quem ainda não rodou."""
    from fazenda.models import Fazenda, SanitarioCaixa

    fazendas = session.exec(
        select(Fazenda.id).where(Fazenda.ativa == True, Fazenda.id.in_(  # noqa: E712
            select(SanitarioCaixa.fazenda_id).where(SanitarioCaixa.estado != "arquivada")))
    ).all()
    out = {}
    for fid in fazendas:
        try:
            fechados = fechar_dias_vencidos(session, fid, agora)
            session.commit()
            out[fid] = {"fechados": fechados, "diaria": executar_diaria(session, fid, agora)}
            # Push das notas novas (aglomerou, véspera, prazos, celular offline) —
            # depois do commit da diária; cada nota sai uma vez (push_enviado_em).
            from fazenda.rules.sanitario.push import despachar_push_notas
            out[fid]["push"] = despachar_push_notas(session, fid)
        except Exception:
            session.rollback()
            logger.exception("sanitario: tick da fazenda %s falhou", fid)
            out[fid] = {"erro": True}
    return out
