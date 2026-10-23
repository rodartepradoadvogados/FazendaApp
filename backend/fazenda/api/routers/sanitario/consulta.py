"""
/sanitario — consultas (Sanidade › Preventiva, Agenda, ficha). SÓ LEITURA:
nenhum GET daqui grava (teste tests/test_sanitario_api.py conta as linhas
antes e depois). Contagens são sempre de animais DISTINTOS.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.api.routers.sanitario._comum import da_fazenda, exigir_admin_fazenda, exigir_fazenda
from fazenda.api.routers.sanitario.schemas import PrazoCumprirIn
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Animal, Estoque, SanitarioCaixa, SanitarioCaixaVersao, SanitarioDia, SanitarioLog, SanitarioNotaAgenda,
    SanitarioParametros, SanitarioPrazoLegal, SanitarioRegistro, SanitarioSituacao, Usuario,
)
from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario import consulta as regras_consulta
from fazenda.rules.sanitario.dias import ESTADOS_ABERTOS, dia_dict
from fazenda.rules.sanitario.leite import leite_separado
from fazenda.rules.sanitario.permissoes import eh_admin_fazenda
from fazenda.rules.sanitario.registro import _log, quantidade_baixa

router = APIRouter(tags=["sanitario-consulta"])

ESTADOS_PREVISTOS = ("janela", "aviso", "atrasada", "prevista", "marcada")


def _caixas(session: Session, fid: int, so_ativas: bool = True) -> dict[int, SanitarioCaixa]:
    q = select(SanitarioCaixa).where(SanitarioCaixa.fazenda_id == fid)
    q = q.where(SanitarioCaixa.estado == "ativa") if so_ativas else q.where(SanitarioCaixa.estado != "arquivada")
    return {c.id: c for c in session.exec(q).all()}


def _quando(row, hoje: date) -> Optional[date]:
    if row.estado in ("janela", "atrasada"):
        return hoje
    if row.estado in ("aviso", "prevista"):
        return row.data_base or row.janela_inicio
    return None


def _parametros(session: Session, fid: int) -> dict:
    p = session.exec(select(SanitarioParametros).where(SanitarioParametros.fazenda_id == fid)).first()
    return {"antecedencia_padrao_dias": p.antecedencia_padrao_dias if p else 30,
            "aviso_offline_horas": p.aviso_offline_horas if p else 24,
            "modo_tuberculina": p.modo_tuberculina if p else "so_resultado"}


def _prazo_dict(p: SanitarioPrazoLegal, caixas: dict) -> dict:
    cx = caixas.get(p.caixa_id)
    return {"id": p.id, "tipo": p.tipo, "caixa_id": p.caixa_id, "caixa": (cx.nome_curto or cx.nome) if cx else None,
            "referencia": p.referencia_chave, "registro_ids": p.registro_ids or [], "vence_em": p.vence_em.isoformat(),
            "destinatario": p.destinatario, "estado": p.estado,
            "cumprido_em": p.cumprido_em.isoformat() if p.cumprido_em else None,
            "documento_numero": p.documento_numero}


@router.get("/painel")
def painel(dias: int = Query(default=30, ge=1, le=365), session: Session = Depends(get_session),
           fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """Painel de Sanidade › Preventiva (30 d): cobertura das obrigatórias,
    caixas que aglomeraram, próximos 7 dias, atrasadas, em carência, consumo
    × estoque, prazos legais e custo. Os parâmetros usados vêm no corpo."""
    fid = exigir_fazenda(fazenda_id)
    hoje = hoje_local()
    ate = hoje + timedelta(days=dias)
    caixas = _caixas(session, fid)
    versoes = {c.id: session.get(SanitarioCaixaVersao, c.versao_atual_id) for c in caixas.values() if c.versao_atual_id}
    rows = session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fid, SanitarioSituacao.caixa_id.in_(list(caixas) or [-1]))).all()
    por_caixa: dict[int, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for r in rows:
        por_caixa[r.caixa_id][r.estado].add(r.animal_id)
    cobertura, aglomeradas, atrasadas = [], [], []
    for cid, cx in sorted(caixas.items(), key=lambda kv: kv[1].nome):
        e = por_caixa.get(cid, {})
        feitos = len(e.get("aplicada", set()))
        devidos = len(set().union(*(e.get(k, set()) for k in ("aplicada", "janela", "atrasada", "perdida", "marcada"))))
        if cx.obrigatoria:
            cobertura.append({"caixa_id": cid, "caixa": cx.nome_curto or cx.nome, "aplicados": feitos, "devidos": devidos,
                              "pct": round(feitos / devidos * 100) if devidos else None})
        na = set().union(*(e.get(k, set()) for k in ("janela", "aviso", "atrasada")))
        v = versoes.get(cid)
        minimo = v.aglo_min if v else 4
        if na and len(na) >= max(int(minimo or 1), 1):
            aglomeradas.append({"caixa_id": cid, "caixa": cx.nome_curto or cx.nome, "animais": len(na), "minimo": minimo})
        atr = set().union(*(e.get(k, set()) for k in ("atrasada", "perdida")))
        if atr:
            atrasadas.append({"caixa_id": cid, "caixa": cx.nome_curto or cx.nome, "animais": len(atr),
                              "animal_ids": sorted(atr)[:50]})
    proximos = [dia_dict(session, d, com_itens=False) for d in session.exec(select(SanitarioDia).where(
        SanitarioDia.fazenda_id == fid, SanitarioDia.estado.in_(ESTADOS_ABERTOS),
        SanitarioDia.data >= hoje, SanitarioDia.data <= hoje + timedelta(days=7)).order_by(SanitarioDia.data)).all()]
    car = session.exec(select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fid, SanitarioRegistro.estado == "valido",
        (SanitarioRegistro.carencia_leite_ate >= hoje) | (SanitarioRegistro.carencia_carne_ate >= hoje))).all()
    em_carencia = {
        "animais": len({r.animal_id or r.numero_animal_texto for r in car}),
        "leite": len({r.animal_id or r.numero_animal_texto for r in car if r.carencia_leite_ate and r.carencia_leite_ate >= hoje}),
        "carne": len({r.animal_id or r.numero_animal_texto for r in car if r.carencia_carne_ate and r.carencia_carne_ate >= hoje}),
    }
    # Consumo previsto × estoque (caixas com produto do estoque)
    consumo: dict[int, dict] = {}
    from fazenda.rules.sanitario.contexto import carregar_animais

    precisa = {r.animal_id for r in rows if r.estado in ESTADOS_PREVISTOS}
    ctxs = carregar_animais(session, fid, animal_ids=precisa, hoje=hoje) if precisa else {}
    for r in rows:
        v = versoes.get(r.caixa_id)
        if v is None or v.produto_modo != "estoque" or not v.estoque_id or r.estado not in ESTADOS_PREVISTOS:
            continue
        q = _quando(r, hoje)
        if r.estado != "marcada" and (q is None or q > ate):
            continue
        ctx = ctxs.get(r.animal_id)
        qtd = quantidade_baixa({"dose_valor": v.dose_valor, "dose_unidade": v.dose_unidade, "dose_x_kg": v.dose_x_kg},
                               ctx.peso if ctx else None)
        c = consumo.setdefault(v.estoque_id, {"estoque_id": v.estoque_id, "necessario": 0.0, "sem_peso": 0, "caixas": set()})
        if qtd is None:
            c["sem_peso"] += 1
        else:
            c["necessario"] += qtd
        c["caixas"].add(caixas[r.caixa_id].nome_curto or caixas[r.caixa_id].nome)
    lista_consumo = []
    for eid, c in consumo.items():
        e = session.get(Estoque, eid)
        saldo = e.quantidade if e else None
        lista_consumo.append({"estoque_id": eid, "produto": e.nome if e else None, "unidade": e.unidade if e else None,
                              "necessario": round(c["necessario"], 2), "saldo": saldo, "sem_peso": c["sem_peso"],
                              "falta": max(0.0, round(c["necessario"] - (saldo or 0), 2)), "caixas": sorted(c["caixas"])})
    todas = _caixas(session, fid, so_ativas=False)
    prazos = [_prazo_dict(p, todas) for p in session.exec(select(SanitarioPrazoLegal).where(
        SanitarioPrazoLegal.fazenda_id == fid, SanitarioPrazoLegal.estado == "aberto").order_by(SanitarioPrazoLegal.vence_em)).all()]
    custo = sum(r.custo or 0 for r in session.exec(select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fid, SanitarioRegistro.estado == "valido", SanitarioRegistro.so_registro == False,  # noqa: E712
        SanitarioRegistro.data >= hoje - timedelta(days=dias), SanitarioRegistro.data <= hoje)).all())
    return {
        "parametros": {"dias": dias, "hoje": hoje.isoformat(), **_parametros(session, fid)},
        "resumo": regras_consulta.resumo_30d(session, fid, hoje=hoje, dias=dias),
        "cobertura": cobertura, "aglomeradas": aglomeradas, "proximos_7_dias": proximos, "atrasadas": atrasadas,
        "em_carencia": em_carencia, "consumo": sorted(lista_consumo, key=lambda x: -x["falta"]), "prazos": prazos,
        "custo_periodo": round(custo, 2),
        "carencia_sem_aceite": [n.caixa_id for n in session.exec(select(SanitarioNotaAgenda).where(
            SanitarioNotaAgenda.fazenda_id == fid, SanitarioNotaAgenda.tipo == "carencia_pendente",
            SanitarioNotaAgenda.resolvida_em == None)).all()],  # noqa: E711
    }


@router.get("/janela")
def animais_na_janela(caixa_id: Optional[int] = None, estado: Optional[str] = None,
                      session: Session = Depends(get_session),
                      fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    """Animais na janela por caixa, com o "por quê" (motivos do motor)."""
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
    from fazenda.rules.sanitario.motor import avaliar

    fid = exigir_fazenda(fazenda_id)
    hoje = hoje_local()
    caixas = _caixas(session, fid)
    if caixa_id is not None:
        if caixa_id not in caixas:
            da_fazenda(session, SanitarioCaixa, caixa_id, fid, "Vacina/exame")
        caixas = {k: v for k, v in caixas.items() if k == caixa_id}
    estados = tuple(estado.split(",")) if estado else ("janela", "aviso", "atrasada", "marcada")
    rows = session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fid, SanitarioSituacao.caixa_id.in_(list(caixas) or [-1]),
        SanitarioSituacao.estado.in_(estados))).all()
    ids = {r.animal_id for r in rows}
    ctxs = carregar_animais(session, fid, animal_ids=ids, hoje=hoje) if ids else {}
    defs = {d.caixa_id: d for d in carregar_caixas(session, fid, caixa_ids=list(caixas), so_ativas=True)}
    animais = {a.id: a for a in session.exec(select(Animal).where(Animal.fazenda_id == fid, Animal.id.in_(ids or {-1}))).all()}
    por_caixa: dict[int, list] = defaultdict(list)
    for r in rows:
        ctx, cxd, a = ctxs.get(r.animal_id), defs.get(r.caixa_id), animais.get(r.animal_id)
        motivos = []
        if ctx is not None and cxd is not None:
            for s in avaliar(cxd, ctx):
                if s.ciclo is not None and s.ciclo.chave == r.ciclo_chave and s.dose_num == r.dose_num:
                    motivos = [{"ok": m.ok, "texto": m.texto} for m in s.motivos]
        por_caixa[r.caixa_id].append({
            "animal_id": r.animal_id, "numero": a.numero if a else None, "lote": a.grupo_primario if a else None,
            "categoria": ctx.categoria_em(hoje)[1] if ctx else None, "estado": r.estado, "texto": r.motivo,
            "ciclo_chave": r.ciclo_chave, "dose_num": r.dose_num,
            "janela_inicio": r.janela_inicio.isoformat() if r.janela_inicio else None,
            "janela_fim": r.janela_fim.isoformat() if r.janela_fim else None,
            "data_base": r.data_base.isoformat() if r.data_base else None, "dia_id": r.dia_id, "porque": motivos,
        })
    out = []
    for cid, cx in sorted(caixas.items(), key=lambda kv: kv[1].nome):
        v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
        lst = sorted(por_caixa.get(cid, []), key=lambda x: x["numero"] or "")
        out.append({"caixa_id": cid, "caixa": cx.nome_curto or cx.nome, "tipo": cx.tipo,
                    "minimo": v.aglo_min if v else None, "animais": len({x["animal_id"] for x in lst}), "itens": lst})
    return out


@router.get("/calendario")
def calendario(ano: Optional[int] = None, session: Session = Depends(get_session),
               fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """Calendário anual: por mês, ANIMAIS DISTINTOS previstos (situação) e
    aplicados (registros) — por caixa e no total do mês (união, sem somar)."""
    fid = exigir_fazenda(fazenda_id)
    hoje = hoje_local()
    ano = ano or hoje.year
    caixas = _caixas(session, fid, so_ativas=False)
    meses = {m: {"previstos": defaultdict(set), "aplicados": defaultdict(set), "dias": []} for m in range(1, 13)}
    for r in session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fid, SanitarioSituacao.estado.in_(ESTADOS_PREVISTOS),
        SanitarioSituacao.caixa_id.in_(list(caixas) or [-1]))).all():
        q = r.janela_inicio if r.estado == "marcada" else _quando(r, hoje)
        if r.estado == "marcada" and r.dia_id:
            d = session.get(SanitarioDia, r.dia_id)
            q = d.data if d else q
        if q is not None and q.year == ano:
            meses[q.month]["previstos"][r.caixa_id].add(r.animal_id)
    for reg in session.exec(select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fid, SanitarioRegistro.estado == "valido",
        SanitarioRegistro.data >= date(ano, 1, 1), SanitarioRegistro.data <= date(ano, 12, 31))).all():
        meses[reg.data.month]["aplicados"][reg.caixa_id or 0].add(reg.animal_id or reg.numero_animal_texto)
    for d in session.exec(select(SanitarioDia).where(
        SanitarioDia.fazenda_id == fid, SanitarioDia.estado != "cancelado",
        SanitarioDia.data >= date(ano, 1, 1), SanitarioDia.data <= date(ano, 12, 31))).all():
        meses[d.data.month]["dias"].append({"id": d.id, "data": d.data.isoformat(), "estado": d.estado})
    out = []
    for m, v in meses.items():
        def _lista(dd):
            return [{"caixa_id": cid, "caixa": ((caixas[cid].nome_curto or caixas[cid].nome) if cid in caixas else "Outro"),
                     "animais": len(s)} for cid, s in sorted(dd.items())]
        out.append({
            "mes": m, "previstos_total": len(set().union(*v["previstos"].values())) if v["previstos"] else 0,
            "aplicados_total": len(set().union(*v["aplicados"].values())) if v["aplicados"] else 0,
            "previstos": _lista(v["previstos"]), "aplicados": _lista(v["aplicados"]), "dias": v["dias"],
        })
    return {"ano": ano, "meses": out,
            "nota": "Contagens de animais distintos; o total do mês é a união das caixas (sem somar duplicado)."}


@router.get("/registros")
def listar_registros(de: Optional[date] = None, ate: Optional[date] = None, caixa_id: Optional[int] = None,
                     origem: Optional[str] = None, animal_id: Optional[int] = None,
                     incluir_estornados: bool = False, limite: int = Query(default=500, ge=1, le=5000),
                     session: Session = Depends(get_session),
                     fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    """Aplicações (histórico único), com os selos de origem."""
    fid = exigir_fazenda(fazenda_id)
    q = select(SanitarioRegistro).where(SanitarioRegistro.fazenda_id == fid)
    if not incluir_estornados:
        q = q.where(SanitarioRegistro.estado == "valido")
    if de:
        q = q.where(SanitarioRegistro.data >= de)
    if ate:
        q = q.where(SanitarioRegistro.data <= ate)
    if caixa_id is not None:
        q = q.where(SanitarioRegistro.caixa_id == caixa_id)
    if origem:
        q = q.where(SanitarioRegistro.origem == origem)
    if animal_id is not None:
        q = q.where(SanitarioRegistro.animal_id == animal_id)
    regs = session.exec(q.order_by(SanitarioRegistro.data.desc(), SanitarioRegistro.id.desc()).limit(limite)).all()
    caixas = _caixas(session, fid, so_ativas=False)
    return [regras_consulta.registro_dict(r, caixas.get(r.caixa_id)) for r in regs]


@router.get("/historico")
def historico(animal_id: Optional[int] = None, caixa_id: Optional[int] = None,
              session: Session = Depends(get_session),
              fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    """Histórico por animal ou por caixa (inclui estornados, marcados)."""
    fid = exigir_fazenda(fazenda_id)
    if animal_id is None and caixa_id is None:
        raise HTTPException(status_code=400, detail="Informe animal_id ou caixa_id.")
    q = select(SanitarioRegistro).where(SanitarioRegistro.fazenda_id == fid)
    if animal_id is not None:
        q = q.where(SanitarioRegistro.animal_id == animal_id)
    if caixa_id is not None:
        q = q.where(SanitarioRegistro.caixa_id == caixa_id)
    caixas = _caixas(session, fid, so_ativas=False)
    return [regras_consulta.registro_dict(r, caixas.get(r.caixa_id))
            for r in session.exec(q.order_by(SanitarioRegistro.data.desc(), SanitarioRegistro.id.desc())).all()]


@router.get("/animais/{animal_id}/situacao")
def situacao_animal(animal_id: int, session: Session = Depends(get_session),
                    fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    a = da_fazenda(session, Animal, animal_id, fid, "Animal")
    return {"animal_id": a.id, "numero": a.numero, "caixas": regras_consulta.situacao_do_animal(session, fid, a.id)}


@router.get("/animais/{animal_id}/historico")
def historico_animal(animal_id: int, session: Session = Depends(get_session),
                     fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    a = da_fazenda(session, Animal, animal_id, fid, "Animal")
    regs = regras_consulta.registros_do_animal(session, fid, a.id, incluir_estornados=True)
    return {"animal_id": a.id, "numero": a.numero, "registros": regs,
            "exames": [r for r in regs if r["tipo"] == "exame" and r["estado"] == "valido"]}


@router.get("/agenda/resumo")
def resumo_agenda(dias: int = Query(default=30, ge=1, le=365), session: Session = Depends(get_session),
                  fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """Card "Vacinas previstas" da Agenda: SÓ NÚMEROS (nunca lista animais)."""
    fid = exigir_fazenda(fazenda_id)
    return {**regras_consulta.resumo_30d(session, fid, dias=dias), "link": "/sanidade?aba=preventiva&sub=painel"}


@router.get("/notas")
def listar_notas(abertas: bool = True, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
                 fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    """Notas do sanitário na Agenda. As marcadas "só administradores" só
    aparecem para administradores da fazenda."""
    fid = exigir_fazenda(fazenda_id)
    adm = eh_admin_fazenda(session, user, fid)
    q = select(SanitarioNotaAgenda).where(SanitarioNotaAgenda.fazenda_id == fid)
    if abertas:
        q = q.where(SanitarioNotaAgenda.resolvida_em == None)  # noqa: E711
    if not adm:
        q = q.where(SanitarioNotaAgenda.so_admin == False)  # noqa: E712
    return [{
        "id": n.id, "tipo": n.tipo, "titulo": n.titulo, "texto": n.texto, "dados": n.dados, "caixa_id": n.caixa_id,
        "ciclo_chave": n.ciclo_chave, "dia_id": n.dia_id, "so_admin": n.so_admin,
        "data_ref": n.data_ref.isoformat() if n.data_ref else None,
        "resolvida_em": n.resolvida_em.isoformat() if n.resolvida_em else None,
        "push_enviado_em": n.push_enviado_em.isoformat() if n.push_enviado_em else None,
    } for n in session.exec(q.order_by(SanitarioNotaAgenda.data_ref.desc(), SanitarioNotaAgenda.id.desc())).all()]


@router.post("/notas/{nota_id}/resolver")
def resolver_nota(nota_id: int, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
                  fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    n = da_fazenda(session, SanitarioNotaAgenda, nota_id, fid, "Nota")
    if n.so_admin:
        exigir_admin_fazenda(session, user, fid)
    if n.resolvida_em is None:
        n.resolvida_em = datetime.utcnow()
        session.add(n)
        _log(session, fid, "nota.resolvida", caixa_id=n.caixa_id, dia_id=n.dia_id, usuario_id=user.id,
             texto_livre=f"Nota resolvida: {n.titulo}")
        session.commit()
    return {"id": n.id, "resolvida_em": n.resolvida_em.isoformat()}


@router.get("/prazos")
def listar_prazos(estado: Optional[str] = "aberto", session: Session = Depends(get_session),
                  fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    fid = exigir_fazenda(fazenda_id)
    q = select(SanitarioPrazoLegal).where(SanitarioPrazoLegal.fazenda_id == fid)
    if estado:
        q = q.where(SanitarioPrazoLegal.estado == estado)
    caixas = _caixas(session, fid, so_ativas=False)
    return [_prazo_dict(p, caixas) for p in session.exec(q.order_by(SanitarioPrazoLegal.vence_em)).all()]


@router.post("/prazos/{prazo_id}/cumprir")
def cumprir_prazo(prazo_id: int, dados: PrazoCumprirIn, session: Session = Depends(get_session),
                  user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Atestado enviado / comprovação feita (administrador). A próxima
    comprovação periódica é aberta pelo job a partir desta data."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    p = da_fazenda(session, SanitarioPrazoLegal, prazo_id, fid, "Prazo")
    p.estado, p.cumprido_em = "cumprido", dados.cumprido_em or hoje_local()
    p.documento_numero = dados.documento_numero
    session.add(p)
    from fazenda.rules.sanitario.notas import resolver_notas
    resolver_notas(session, fid, chave=f"prazo:{p.id}")
    _log(session, fid, "prazo.cumprido", caixa_id=p.caixa_id, usuario_id=user.id,
         texto_livre=f"{p.tipo.capitalize()} cumprido em {p.cumprido_em.strftime('%d/%m/%Y')}"
                     f"{' · doc ' + p.documento_numero if p.documento_numero else ''}.")
    session.commit()
    return _prazo_dict(p, _caixas(session, fid, so_ativas=False))


@router.get("/log")
def listar_log(dia_id: Optional[int] = None, caixa_id: Optional[int] = None, animal_id: Optional[int] = None,
               tipo: Optional[str] = None, limite: int = Query(default=200, ge=1, le=2000),
               session: Session = Depends(get_session),
               fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    from fazenda.api.routers.sanitario.dias import _log_dict

    fid = exigir_fazenda(fazenda_id)
    q = select(SanitarioLog).where(SanitarioLog.fazenda_id == fid)
    if dia_id is not None:
        q = q.where(SanitarioLog.dia_id == dia_id)
    if caixa_id is not None:
        q = q.where(SanitarioLog.caixa_id == caixa_id)
    if animal_id is not None:
        q = q.where(SanitarioLog.animal_id == animal_id)
    if tipo:
        q = q.where(SanitarioLog.tipo.startswith(tipo))
    return [_log_dict(lg) for lg in session.exec(q.order_by(SanitarioLog.em.desc(), SanitarioLog.id.desc()).limit(limite)).all()]


@router.get("/leite-separado")
def leite_separado_rota(session: Session = Depends(get_session),
                        fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """"Leite separado": curativos e preventivos JUNTOS (vacas ainda em carência de leite)."""
    fid = exigir_fazenda(fazenda_id)
    hoje = hoje_local()
    itens = leite_separado(session, fid, hoje)
    return {"hoje": hoje.isoformat(), "animais": len({i["numero"] for i in itens}), "itens": itens}
