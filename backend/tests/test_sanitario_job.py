"""
Sanitário v2 — job diário: fuso America/Sao_Paulo (22h BRT ainda é "hoje"),
lock + 1×/dia, aglomeração só pelo mínimo da caixa (sem duplicar nota),
véspera, fechamento automático às 23:59 do dia seguinte e aviso de animal que
saiu da janela depois de marcado.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from fazenda.models import (
    SanitarioDia, SanitarioDiaCaixa, SanitarioDiaItem, SanitarioJobEstado, SanitarioLog, SanitarioNotaAgenda,
)
from fazenda.rules.sanitario.job import executar_diaria, fechar_dias_vencidos, notas_aglomeracao, tick
from fazenda.rules.sanitario.motor import recalcular
from tests.sanitario_cenario import (  # noqa: F401  (fixtures)
    F1, F2, HOJE, animal, caixa, def_b19, def_pre_parto, engine, servico, session,
)

UTC = timezone.utc


def _utc(ano, mes, dia, hora, minuto=0):
    return datetime(ano, mes, dia, hora, minuto, tzinfo=UTC)


def _notas(session, tipo):
    return session.exec(select(SanitarioNotaAgenda).where(SanitarioNotaAgenda.tipo == tipo)).all()


def _dia(session, data, caixa_id, animal_ids, estado="marcado"):
    d = SanitarioDia(fazenda_id=F1, data=data, estado=estado, hora="07:00")
    session.add(d)
    session.flush()
    session.add(SanitarioDiaCaixa(fazenda_id=F1, dia_id=d.id, caixa_id=caixa_id))
    for aid in animal_ids:
        session.add(SanitarioDiaItem(fazenda_id=F1, dia_id=d.id, animal_id=aid, caixa_id=caixa_id))
    session.flush()
    return d


# ── aglomeração ─────────────────────────────────────────────────────────────
def test_aglomera_so_pelo_minimo_e_nao_duplica(session):
    caixa(session, def_b19(aglo_min=4))
    for i in range(3):
        animal(session, f"24{i:02d}", idade_dias=150 + i)
    recalcular(session, F1, hoje=HOJE)
    notas_aglomeracao(session, F1, HOJE)
    assert _notas(session, "aglomerou") == []                # 3 < mínimo 4
    animal(session, "2499", idade_dias=160)
    recalcular(session, F1, hoje=HOJE)
    notas_aglomeracao(session, F1, HOJE)
    notas_aglomeracao(session, F1, HOJE + timedelta(days=1))  # dia seguinte: mesma nota, sem duplicar
    notas = _notas(session, "aglomerou")
    assert len(notas) == 1
    assert "aglomerou 4 animais" in notas[0].titulo and notas[0].so_admin
    assert notas[0].chave_dedupe.startswith("aglo:") and "4" not in notas[0].chave_dedupe.split(":")[-1][:1]


def test_aglomeracao_abaixo_do_minimo_resolve_a_nota(session):
    cx = caixa(session, def_b19(aglo_min=1))
    a = animal(session, "2401", idade_dias=150)
    recalcular(session, F1, hoje=HOJE)
    notas_aglomeracao(session, F1, HOJE)
    _dia(session, HOJE + timedelta(days=3), cx.id, [a.id])  # marcado: sai da contagem
    recalcular(session, F1, hoje=HOJE)
    notas_aglomeracao(session, F1, HOJE)
    assert _notas(session, "aglomerou")[0].resolvida_em is not None


# ── diária: fuso e lock ─────────────────────────────────────────────────────
def test_diaria_roda_uma_vez_por_dia_local_mesmo_as_22h_brt(session):
    caixa(session, def_b19(aglo_min=1))
    animal(session, "2401", idade_dias=150)
    session.commit()
    manha = _utc(2026, 10, 21, 11)          # 08h BRT de 21/10
    noite = _utc(2026, 10, 22, 1)           # 22h BRT de 21/10 (já é 22/10 em UTC)
    madrugada = _utc(2026, 10, 22, 3, 30)   # 00h30 BRT de 22/10
    assert executar_diaria(session, F1, manha) is not None
    assert executar_diaria(session, F1, noite) is None      # ainda é 21/10 em Brasília
    estado = session.exec(select(SanitarioJobEstado).where(SanitarioJobEstado.fazenda_id == F1)).one()
    assert str(estado.ultima_diaria_em) == "2026-10-21"
    assert executar_diaria(session, F1, madrugada) is not None
    session.refresh(estado)
    assert str(estado.ultima_diaria_em) == "2026-10-22" and estado.status == "ok"


def test_lock_impede_execucao_concorrente(session):
    caixa(session, def_b19())
    session.add(SanitarioJobEstado(fazenda_id=F1, em_execucao_ate=datetime(2026, 10, 21, 12, 0)))
    session.commit()
    assert executar_diaria(session, F1, _utc(2026, 10, 21, 11, 50)) is None  # outro processo segura o lock
    assert executar_diaria(session, F1, _utc(2026, 10, 21, 12, 10)) is not None  # lock expirou


def test_vespera_vai_para_todos(session):
    cx = caixa(session, def_b19())
    a = animal(session, "2401", idade_dias=150)
    _dia(session, HOJE + timedelta(days=1), cx.id, [a.id])
    session.commit()
    executar_diaria(session, F1, _utc(2026, 10, 21, 12))
    v = _notas(session, "vespera")
    assert len(v) == 1 and not v[0].so_admin and v[0].titulo.startswith("Amanhã: Vacina · B19 · 22/10")


# ── fechamento automático ───────────────────────────────────────────────────
def test_fechamento_automatico_as_23h59_do_dia_seguinte(session):
    cx = caixa(session, def_b19())
    a = animal(session, "2401", idade_dias=150)
    d = _dia(session, HOJE - timedelta(days=1), cx.id, [a.id])   # dia 20/10
    session.commit()
    assert fechar_dias_vencidos(session, F1, _utc(2026, 10, 22, 1)) == 0      # 22h BRT de 21/10
    assert fechar_dias_vencidos(session, F1, _utc(2026, 10, 22, 2, 58)) == 0  # 23h58 BRT de 21/10
    assert fechar_dias_vencidos(session, F1, _utc(2026, 10, 22, 3, 0)) == 1   # 00h00 BRT de 22/10
    session.refresh(d)
    assert d.estado == "fechado" and d.fechamento_auto
    item = session.exec(select(SanitarioDiaItem).where(SanitarioDiaItem.dia_id == d.id)).one()
    assert item.estado == "faltou"
    assert session.exec(select(SanitarioLog).where(SanitarioLog.tipo == "dia.fechado_auto")).first()
    assert len(_notas(session, "fechamento_auto")) == 1
    from fazenda.models import SanitarioSituacao
    sit = session.exec(select(SanitarioSituacao).where(SanitarioSituacao.animal_id == a.id)).one()
    assert sit.estado == "janela"  # pendente voltou para a caixa


def test_tick_so_toca_fazenda_com_caixa(session):
    caixa(session, def_b19(), fazenda_id=F2)
    session.commit()
    out = tick(session, _utc(2026, 10, 21, 12))
    assert set(out) == {F2}


# ── animal saiu da janela depois de marcado ─────────────────────────────────
def test_aviso_quando_animal_marcado_sai_da_janela(session):
    cx = caixa(session, def_b19())
    a = animal(session, "2410", idade_dias=235)  # passa de 240 d antes do dia
    _dia(session, HOJE + timedelta(days=10), cx.id, [a.id])
    session.commit()
    executar_diaria(session, F1, _utc(2026, 10, 21, 12))
    n = _notas(session, "animal_saiu_janela")
    assert len(n) == 1 and "fora da idade da B19" in n[0].texto
