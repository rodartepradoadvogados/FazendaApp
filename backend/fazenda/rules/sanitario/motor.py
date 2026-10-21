"""
Motor do Sanitário Preventivo v2 — UMA regra para todas as telas.

- `avaliar(cx, animal, ref)`: PURA. A função única de situação (prevista,
  aviso, janela, marcada, aplicada, atrasada, perdida, descartada,
  dispensada, saiu, fora). Espelha `situ()` do mockup aprovado. Agenda,
  Sanidade, Central, app e painel leem o resultado dela (direto ou pela
  tabela `sanitario_situacao` que `recalcular` mantém).
- `ok_na_data`/`motivo_inelegivel`: o animal estará pronto na data d? (curral,
  pop-up de consentimento, simulação).
- `simular_pura`/`simular`: riscos de marcar o dia numa data diferente da
  prevista (pariu, passou da idade, mudou de categoria, janela fecha, ainda
  não entrou) e quem ENTRA até a nova data. Nunca grava.
- `recalcular`: o único que grava `sanitario_situacao` — upsert pela chave
  única (fazenda, caixa, animal, ciclo, dose); nunca dá commit (roda dentro
  da transação de quem escreveu, ou do job diário).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from fazenda.rules.sanitario.ciclos import ciclo_de, janela_txt, sem_ciclo_txt
from fazenda.rules.sanitario.publico import idade_txt, publico
from fazenda.rules.sanitario.tipos import (
    FIM_NUNCA, INICIO_SEMPRE, AnimalCtx, CaixaDef, Ciclo, Motivo, NaData, Situacao,
)

logger = logging.getLogger(__name__)

# Estados que NÃO viram linha em `sanitario_situacao` (seriam N animais × M
# caixas de "fora"). Quem precisa do "fora" (prévia, consentimento) chama o
# motor puro.
ESTADOS_NAO_GRAVADOS = ("fora",)
ESTADOS_TERMINAIS_SAIDA = ("aplicada", "dispensada", "saiu")


def _fmt(d: date) -> str:
    return d.strftime("%d/%m")


def _dispensado(a: AnimalCtx, cx: CaixaDef, c: Ciclo, dose: int = 1) -> bool:
    return (cx.caixa_id, c.chave, dose) in a.dispensas


# ════════════════════════════════════════════════════════════════════════════
# A função única
# ════════════════════════════════════════════════════════════════════════════
def _avaliar_dose1(cx: CaixaDef, a: AnimalCtx, ref: date) -> Situacao:
    base = dict(caixa_id=cx.caixa_id, animal_id=a.id)
    if not a.ativo:
        txt = a.saida_txt or "Saiu do rebanho"
        return Situacao(**base, estado="saiu", texto=txt, motivos=[Motivo(False, txt, "saiu")])

    c = ciclo_de(cx, a, ref, "proximo")
    # Período com "manter aberta": o último ciclo que fechou sem receber
    # continua cobrando ("atrasada"), desde que a caixa já estivesse ativa
    # quando ele começou.
    if cx.eh_periodo and cx.ao_fechar == "manter":
        u = ciclo_de(cx, a, ref, "ultimo")
        if (
            u is not None and u.fim < ref
            and (cx.ativada_em is None or u.ini >= cx.ativada_em)
            and (c is None or c.ini > ref)
            and a.registro_valido(cx.caixa_id, u.chave) is None
            and not _dispensado(a, cx, u)
            and all(m.ok for m in publico(cx, a, u.base))
        ):
            c = replace(u, atrasado=True)

    if c is None:
        txt = sem_ciclo_txt(cx)
        return Situacao(**base, estado="fora", texto=txt, motivos=[Motivo(False, txt, "ciclo")])

    ap = a.registro_valido(cx.caixa_id, c.chave)
    if ap is not None:
        txt = ("Resultado " if cx.eh_exame else "Recebeu ") + _fmt(ap.data)
        return Situacao(
            **base, estado="aplicada", texto=txt, ciclo=c, registro_id=ap.id, elegivel=True,
            motivos=[Motivo(True, f"Recebeu em {ap.data.strftime('%d/%m/%Y')} (ciclo {c.rotulo})", "aplicada")],
        )
    if _dispensado(a, cx, c):
        return Situacao(**base, estado="dispensada", texto="Dispensada", ciclo=c,
                        motivos=[Motivo(False, "Dispensada neste ciclo", "dispensada")])

    d_eval = max(c.base, ref) if c.per else max(c.ini, ref)
    if c.chave == "C":
        d_eval = ref
    elif not c.per and not c.aberta and d_eval > c.fim:
        # Janela por evento já fechada: o público vale como estava no fim dela
        # (pariu sem receber = perdida, e não "fora por não estar prenhe").
        d_eval = c.fim
    R = [Motivo(True, janela_txt(cx, a, c), "janela"), *publico(cx, a, d_eval)]
    elig = all(m.ok for m in R)

    dia = a.dias.get(cx.caixa_id)
    if dia is not None:
        return Situacao(**base, estado="marcada", texto="Marcada " + _fmt(dia[1]), ciclo=c, motivos=R,
                        dia_id=dia[0], dia_data=dia[1], elegivel=elig)
    if not elig:
        fora = next(m for m in R if not m.ok)
        return Situacao(**base, estado="fora", texto="Fora: " + fora.texto, ciclo=c, motivos=R)
    if c.atrasado:
        return Situacao(**base, estado="atrasada", texto=f"Atrasada: ciclo {c.rotulo} fechou {_fmt(c.fim)}",
                        ciclo=c, motivos=R, elegivel=True)
    if c.ini <= ref <= c.fim:
        if c.per or c.fim != FIM_NUNCA and not c.aberta:
            txt = "Na janela até " + _fmt(c.fim) if c.fim != FIM_NUNCA else "Na janela"
        else:
            txt = "Na janela até o parto" if c.aberta else "Na janela"
        return Situacao(**base, estado="janela", texto=txt, ciclo=c, motivos=R, elegivel=True)
    if ref < c.ini:
        if c.per and ref >= c.base - timedelta(days=int(cx.aviso_antecedencia_dias or 0)):
            return Situacao(**base, estado="aviso", ciclo=c, motivos=R, elegivel=True,
                            texto=f"Abre {_fmt(c.ini)} · aviso de {cx.aviso_antecedencia_dias} d")
        return Situacao(**base, estado="prevista", texto="Entra " + _fmt(c.ini), ciclo=c, motivos=R, elegivel=True)
    k = {"perder": "perdida", "descartar": "descartada"}.get(cx.ao_fechar, "atrasada")
    prefixo = {"perdida": "Perdida: janela fechou ", "descartada": "Descartada: janela fechou "}.get(k, "Atrasada desde ")
    return Situacao(**base, estado=k, texto=prefixo + _fmt(c.fim), ciclo=c, motivos=R, elegivel=k == "atrasada")


def _avaliar_serie(cx: CaixaDef, a: AnimalCtx, ref: date, s1: Situacao) -> list[Situacao]:
    """Doses seguintes da série, dentro do MESMO ciclo. Iniciada a série, o
    animal continua até completar — mesmo mudando de categoria (o público
    não é reavaliado; só a saída do rebanho interrompe)."""
    out: list[Situacao] = []
    if not cx.serie or s1.estado != "aplicada" or s1.ciclo is None:
        return out
    c = s1.ciclo
    anterior = a.registro_valido(cx.caixa_id, c.chave, 1)
    for item in sorted(cx.serie, key=lambda x: int(x.get("dose", 2))):
        dose = int(item.get("dose", 2))
        if anterior is None:
            break
        base = dict(caixa_id=cx.caixa_id, animal_id=a.id, dose_num=dose)
        ini = anterior.data + timedelta(days=int(item.get("apos_dias", 30)))
        fim = ini + timedelta(days=int(item.get("janela_dias", 30)))
        cd = Ciclo(chave=c.chave, ini=ini, fim=fim, base=ini, rotulo=f"{c.rotulo} · D{dose}", per=c.per)
        if not a.ativo:
            out.append(Situacao(**base, estado="saiu", texto=a.saida_txt or "Saiu do rebanho", ciclo=cd))
            break
        r = a.registro_valido(cx.caixa_id, c.chave, dose)
        if r is not None:
            out.append(Situacao(**base, estado="aplicada", texto=f"D{dose} em {_fmt(r.data)}", ciclo=cd,
                                registro_id=r.id, elegivel=True))
            anterior = r
            continue
        if _dispensado(a, cx, cd, dose):
            out.append(Situacao(**base, estado="dispensada", texto=f"D{dose} dispensada", ciclo=cd))
            break
        R = [Motivo(True, f"Série: D{dose} de {_fmt(ini)} a {_fmt(fim)}", "serie")]
        dia = a.dias.get(cx.caixa_id)
        if dia is not None:
            est, txt = "marcada", "Marcada " + _fmt(dia[1])
        elif ref < ini:
            est, txt = "prevista", f"D{dose} a partir de {_fmt(ini)}"
        elif ref <= fim:
            est, txt = "janela", f"D{dose} na janela até {_fmt(fim)}"
        else:
            est, txt = "atrasada", f"D{dose} atrasada desde {_fmt(fim)}"
        out.append(Situacao(**base, estado=est, texto=txt, ciclo=cd, motivos=R, elegivel=True,
                            dia_id=dia[0] if dia else None, dia_data=dia[1] if dia else None))
        break
    return out


def avaliar(cx: CaixaDef, a: AnimalCtx, ref: Optional[date] = None) -> list[Situacao]:
    """Situação do animal na caixa em `ref` (padrão: o "hoje" do contexto).
    Devolve a dose 1 e, se for série iniciada, a dose seguinte em aberto.
    PURA: não lê nem grava banco."""
    ref = ref or a.hoje
    s1 = _avaliar_dose1(cx, a, ref)
    return [s1, *_avaliar_serie(cx, a, ref, s1)]


def situacao_atual(cx: CaixaDef, a: AnimalCtx, ref: Optional[date] = None) -> Situacao:
    """A situação "da vez": a primeira dose ainda não aplicada (ou a última)."""
    lista = avaliar(cx, a, ref)
    return next((s for s in lista if s.estado != "aplicada"), lista[-1])


# ════════════════════════════════════════════════════════════════════════════
# Pronto na data d? (simulação, curral, consentimento)
# ════════════════════════════════════════════════════════════════════════════
def ok_na_data(cx: CaixaDef, a: AnimalCtx, d: date) -> NaData:
    if not a.ativo:
        return NaData(False, a.saida_txt or "saiu do rebanho", "saiu")
    s = situacao_atual(cx, a, a.hoje)
    if s.estado == "aplicada":
        return NaData(False, f"já recebeu {cx.rotulo} neste ciclo", "aplicada")
    c = s.ciclo or ciclo_de(cx, a, d, "proximo")
    if c is None:
        return NaData(False, sem_ciclo_txt(cx).lower(), "ciclo")
    if s.dose_num > 1:
        if d < c.ini:
            return NaData(False, f"só entra na janela em {_fmt(c.ini)}", "antes", c.ini)
        return NaData(True)
    fim = max(c.fim_prev or c.fim, a.hoje) if c.aberta else c.fim
    R = publico(cx, a, d)
    f = next((m for m in R if not m.ok), None)
    g = a.gestacao_atual()
    if f is not None and f.chave == "prenhe_parido" and g is not None:
        return NaData(False, f"parto previsto para {_fmt(g.parto_previsto)}", "parto", g.parto_previsto)
    if f is not None:
        return NaData(False, f.texto, "publico")
    if d > fim and not c.atrasado:
        if cx.jan_usa_evento and cx.evento_tipo == "idade" and not c.per:
            meses = round((cx.evento_ate_dias or 0) / 30.44)
            dia = fim + timedelta(days=1)
            return NaData(False, f"passará de {meses} meses em {_fmt(dia)}: fora da idade da {cx.rotulo}", "idade", dia)
        if cx.jan_usa_evento and cx.evento_tipo == "pre_parto" and g is not None:
            return NaData(False, f"parto previsto para {_fmt(g.parto_previsto)}", "parto", g.parto_previsto)
        return NaData(False, f"a janela fecha em {_fmt(fim)}", "fecha", fim)
    if d < c.ini and c.ini != INICIO_SEMPRE:
        return NaData(False, f"só entra na janela em {_fmt(c.ini)}", "antes", c.ini)
    return NaData(True)


def motivo_inelegivel(cx: CaixaDef, a: AnimalCtx, d: date) -> Optional[str]:
    """Texto simples do pop-up de consentimento (o sistema avisa e pede
    consentimento; nunca trava). None = elegível."""
    r = ok_na_data(cx, a, d)
    if r.ok:
        return None
    if r.kind == "idade" and a.nasc is not None:
        return f"{idade_txt((d - a.nasc).days)} em {_fmt(d)}: fora da idade da {cx.rotulo}"
    return r.texto


# ════════════════════════════════════════════════════════════════════════════
# Simulação de outra data (pura)
# ════════════════════════════════════════════════════════════════════════════
def _juntar(itens: list[str]) -> str:
    return itens[0] if len(itens) < 2 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _texto_risco(kind: str, numeros: list[str], rotulos: list[str], msg: str, data: Optional[date], d: date) -> str:
    pl = len(numeros) > 1
    if kind == "parto" and data is not None:
        return (f"{_juntar(numeros)} {'têm' if pl else 'tem'} parto previsto para {_fmt(data)}: "
                f"{'terão' if pl else 'terá'} parido antes de {_fmt(d)}. A vacina de pré-parto "
                f"({_juntar(rotulos)}) pode não ser aplicada a tempo.")
    if kind == "idade":
        return f"{numeros[0]} {msg}."
    if kind == "antes":
        return (f"{_juntar(numeros)} ainda não {'estarão' if pl else 'estará'} na janela de "
                f"{_juntar(rotulos)} em {_fmt(d)} ({msg}).")
    return f"{_juntar(numeros)} · {_juntar(rotulos)}: {msg}."


def simular_pura(
    caixas: Iterable[CaixaDef], animais: dict[int, AnimalCtx], data: date,
    data_prevista: Optional[date] = None, selecionados: Optional[dict[int, set[int]]] = None,
) -> dict:
    """Riscos de marcar o dia em `data` (em vez de `data_prevista`).

    `selecionados`: {animal_id: {caixa_id,...}} já escolhidos para o dia; sem
    ele, vale quem estaria pronto na data prevista (ou hoje). Devolve
    `{"riscos": [{kind, animal_ids, numeros, caixa_ids, data, texto}],
    "entram": [{animal_id, numero, caixa_ids}], "animais": [...]}`."""
    caixas = list(caixas)
    if not animais:
        return {"riscos": [], "entram": [], "animais": []}
    hoje = next(iter(animais.values())).hoje
    prev = data_prevista or hoje
    if selecionados is None:
        selecionados = {}
        for cx in caixas:
            for a in animais.values():
                if a.dias.get(cx.caixa_id):
                    continue
                if ok_na_data(cx, a, prev).ok:
                    selecionados.setdefault(a.id, set()).add(cx.caixa_id)
    por_id = {cx.caixa_id: cx for cx in caixas}
    grupos: dict[tuple, dict] = {}
    for aid, cxs in selecionados.items():
        a = animais.get(aid)
        if a is None:
            continue
        for cid in sorted(cxs):
            cx = por_id.get(cid)
            if cx is None:
                continue
            r = ok_na_data(cx, a, data)
            if r.ok or r.kind == "aplicada":
                continue
            if r.kind == "parto":
                chave = ("parto", r.data)
            elif r.kind == "idade":
                chave = ("idade", cid, aid)
            else:
                chave = (r.kind, cid, r.data or r.texto)
            g = grupos.setdefault(chave, {"kind": r.kind, "animal_ids": [], "caixa_ids": [], "data": r.data, "msg": r.texto})
            if aid not in g["animal_ids"]:
                g["animal_ids"].append(aid)
            if cid not in g["caixa_ids"]:
                g["caixa_ids"].append(cid)
    riscos = []
    for g in grupos.values():
        numeros = [animais[i].numero for i in g["animal_ids"]]
        rotulos = [por_id[c].rotulo for c in g["caixa_ids"]]
        riscos.append({
            "kind": g["kind"], "animal_ids": g["animal_ids"], "numeros": numeros, "caixa_ids": g["caixa_ids"],
            "data": g["data"].isoformat() if g["data"] else None,
            "texto": _texto_risco(g["kind"], numeros, rotulos, g["msg"], g["data"], data),
        })
    entram: dict[int, set[int]] = defaultdict(set)
    for cx in caixas:
        for a in animais.values():
            if cx.caixa_id in selecionados.get(a.id, set()) or a.dias.get(cx.caixa_id):
                continue
            if ok_na_data(cx, a, data).ok and not ok_na_data(cx, a, prev).ok:
                entram[a.id].add(cx.caixa_id)
    prontos = []
    for aid, cxs in selecionados.items():
        a = animais.get(aid)
        if a is None:
            continue
        ok_cx = sorted(c for c in cxs if c in por_id and ok_na_data(por_id[c], a, data).ok)
        if ok_cx:
            prontos.append({"animal_id": aid, "numero": a.numero, "caixa_ids": ok_cx})
    return {
        "riscos": sorted(riscos, key=lambda r: (r["data"] or "", r["kind"])),
        "entram": [{"animal_id": aid, "numero": animais[aid].numero, "caixa_ids": sorted(c)} for aid, c in sorted(entram.items())],
        "animais": prontos,
    }


def simular(
    session: Session, fazenda_id: int, caixa_ids: list[int], data: date, *,
    animal_ids: Optional[list[int]] = None, data_prevista: Optional[date] = None,
    hoje: Optional[date] = None, so_ativas: bool = False,
) -> dict:
    """Simulação de outra data a partir do banco — SÓ LÊ (seguro para GET e
    para a prévia do cadastro). `animal_ids` = os escolhidos para o dia (cada
    um em todas as `caixa_ids`)."""
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas

    caixas = carregar_caixas(session, fazenda_id, caixa_ids=caixa_ids, so_ativas=so_ativas)
    animais = carregar_animais(session, fazenda_id, hoje=hoje)
    sel = None
    if animal_ids is not None:
        sel = {aid: {cx.caixa_id for cx in caixas} for aid in animal_ids}
    return simular_pura(caixas, animais, data, data_prevista, sel)


# ════════════════════════════════════════════════════════════════════════════
# recalcular — o único escritor de sanitario_situacao
# ════════════════════════════════════════════════════════════════════════════
def _campos(s: Situacao, cx: CaixaDef) -> dict:
    c = s.ciclo
    ini = c.ini if c and c.ini != INICIO_SEMPRE else None
    fim = c.fim if c and c.fim != FIM_NUNCA else None
    return {
        "caixa_versao_id": cx.versao_id,
        "estado": s.estado,
        "janela_inicio": ini,
        "janela_fim": fim,
        "data_base": c.base if c and c.chave != "C" else None,
        "motivo": (s.texto or "")[:500] or None,
        "dia_id": s.dia_id,
        "registro_id": s.registro_id,
    }


def recalcular(
    session: Session, fazenda_id: int, animal_ids: Optional[Iterable[int]] = None,
    caixa_ids: Optional[Iterable[int]] = None, motivo: str = "", hoje: Optional[date] = None,
) -> dict:
    """Recalcula a situação e faz upsert em `sanitario_situacao` pela chave
    única (fazenda, caixa, animal, ciclo, dose) — rodar duas vezes não
    duplica nada. Linhas que deixaram de valer (o animal mudou de ciclo ou
    ficou "fora") são apagadas, MENOS as dispensadas (decisão de gente).
    Animal que saiu do rebanho: as linhas abertas viram "saiu".
    Nunca dá commit; dá `flush` para quem chamou enxergar o resultado."""
    from fazenda.models import SanitarioCaixa, SanitarioSituacao
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas

    animal_ids = None if animal_ids is None else sorted({int(i) for i in animal_ids})
    caixa_ids = None if caixa_ids is None else sorted({int(i) for i in caixa_ids})
    cont = {"inseridas": 0, "atualizadas": 0, "removidas": 0, "avaliadas": 0}
    if animal_ids is not None and not animal_ids:
        return cont

    caixas = carregar_caixas(session, fazenda_id, caixa_ids=caixa_ids, so_ativas=True)
    animais = carregar_animais(session, fazenda_id, animal_ids=animal_ids, hoje=hoje)
    agora = datetime.utcnow()
    # SAVEPOINT só no Postgres (corrida real entre job e gancho); no SQLite da
    # suíte o pysqlite trataria o RELEASE como commit.
    pg = session.get_bind().dialect.name == "postgresql"

    q = select(SanitarioSituacao).where(SanitarioSituacao.fazenda_id == fazenda_id)
    if animal_ids is not None:
        q = q.where(SanitarioSituacao.animal_id.in_(animal_ids))
    if caixa_ids is not None:
        q = q.where(SanitarioSituacao.caixa_id.in_(caixa_ids))
    existentes = {(r.caixa_id, r.animal_id, r.ciclo_chave, r.dose_num): r for r in session.exec(q).all()}
    vistos: set[tuple] = set()
    ids_ativas = {cx.caixa_id for cx in caixas}

    for cx in caixas:
        for a in animais.values():
            cont["avaliadas"] += 1
            if not a.ativo:
                # Saiu do rebanho: só marca o que estava aberto; não cria linha.
                for chave, row in existentes.items():
                    if chave[0] == cx.caixa_id and chave[1] == a.id:
                        vistos.add(chave)
                        if row.estado not in ESTADOS_TERMINAIS_SAIDA:
                            row.estado, row.motivo, row.calculado_em = "saiu", (a.saida_txt or "Saiu do rebanho")[:500], agora
                            session.add(row)
                            cont["atualizadas"] += 1
                continue
            for s in avaliar(cx, a):
                if s.estado in ESTADOS_NAO_GRAVADOS or s.ciclo is None:
                    continue
                chave = (cx.caixa_id, a.id, s.ciclo.chave, s.dose_num)
                vistos.add(chave)
                campos = _campos(s, cx)
                row = existentes.get(chave)
                if row is None:
                    row = SanitarioSituacao(
                        fazenda_id=fazenda_id, caixa_id=cx.caixa_id, animal_id=a.id,
                        ciclo_chave=s.ciclo.chave, dose_num=s.dose_num, calculado_em=agora, **campos,
                    )
                    try:
                        if pg:
                            with session.begin_nested():
                                session.add(row)
                        else:
                            session.add(row)
                    except IntegrityError:
                        # Corrida com outro recalcular: a linha já existe — atualiza.
                        row = session.exec(select(SanitarioSituacao).where(
                            SanitarioSituacao.fazenda_id == fazenda_id, SanitarioSituacao.caixa_id == cx.caixa_id,
                            SanitarioSituacao.animal_id == a.id, SanitarioSituacao.ciclo_chave == s.ciclo.chave,
                            SanitarioSituacao.dose_num == s.dose_num,
                        )).one()
                    else:
                        existentes[chave] = row
                        cont["inseridas"] += 1
                        continue
                if row.dispensada_em is not None and s.estado != "aplicada":
                    campos["estado"] = "dispensada"
                if any(getattr(row, k) != v for k, v in campos.items()):
                    for k, v in campos.items():
                        setattr(row, k, v)
                    row.calculado_em = agora
                    session.add(row)
                    cont["atualizadas"] += 1

    # Linhas que deixaram de valer.
    caixas_no_escopo = set(caixa_ids) if caixa_ids is not None else None
    if caixas_no_escopo is None:
        # Recalculo de todas: caixa que não está mais ativa perde as linhas abertas.
        nao_ativas = set(session.exec(
            select(SanitarioCaixa.id).where(SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.estado != "ativa")
        ).all())
    else:
        nao_ativas = caixas_no_escopo - ids_ativas
    for chave, row in existentes.items():
        if chave in vistos or row.dispensada_em is not None:
            continue
        if chave[1] not in animais and chave[0] not in nao_ativas:
            continue  # animal fora do escopo carregado (não deveria acontecer)
        session.delete(row)
        cont["removidas"] += 1
    session.flush()
    if motivo:
        logger.debug("sanitario.recalcular fazenda=%s motivo=%s %s", fazenda_id, motivo, cont)
    return cont
