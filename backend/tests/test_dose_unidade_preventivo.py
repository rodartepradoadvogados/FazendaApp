"""Unidade da dose padrao do protocolo (wizard, passo Identificacao): a unidade
escolhida no cadastro vale na gaveta Aplicar, no registro, nos Concluidos e na
baixa de estoque. A unidade do produto no estoque e a referencia da baixa:
quando diferem nada e convertido em silencio (aviso claro e sem baixa)."""
from __future__ import annotations

from sqlmodel import Session

from tests.test_aplicar_agendamento_preventivo import (  # noqa: F401  (fixtures + helpers)
    HOJE, _aplicar, _agendar, _animal, _espera, _estoque, _pessoas, _regra, _saldo, ctx,
)


def _montar(ctx, *, unidade_estoque: str, unidade_dose: str):
    c, engine = ctx
    with Session(engine) as s:
        vet, _ = _pessoas(s)
        est, lotes = _estoque(s, "Vacina X", unidade=unidade_estoque)
        for n in ("1", "2"):
            _animal(s, n)
        cal = _regra(s, "Protocolo X", produto="Vacina X", dose=2.0, unidade=unidade_dose)
        _espera(s, cal, ["1", "2"])
    ag = _agendar(c, cal, ["1", "2"], vet=vet)
    return c, engine, ag["id"], vet, est


def test_contexto_mostra_unidade_da_dose_e_a_do_estoque(ctx):
    c, engine, ag, vet, est = _montar(ctx, unidade_estoque="ml", unidade_dose="ml")
    r = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
    assert r["unidade"] == "ml" and r["estoque"]["unidade"] == "ml"
    assert r["unidade_estoque"] == "ml" and r["unidade_diverge"] is False


def test_unidade_diferente_do_estoque_avisa_e_nao_baixa_sem_converter(ctx):
    c, engine, ag, vet, est = _montar(ctx, unidade_estoque="ml", unidade_dose="dose")
    ctxo = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
    assert ctxo["unidade"] == "dose" and ctxo["unidade_estoque"] == "ml" and ctxo["unidade_diverge"] is True
    assert "não é convertida" in ctxo["aviso_unidade"] or "converti" in ctxo["aviso_unidade"]
    r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est)
    assert r.status_code == 200, r.text
    dados = r.json()
    ap = dados["aplicacao"]
    assert ap["unidade"] == "dose" and ap["dose_total"] == 4
    assert ap["unidade_estoque"] == "ml" and ap["baixa_automatica"] is False
    assert any("equivalência" in a for a in dados["avisos"])
    assert any("unidade" in e.lower() for e in ap["excecoes"])
    assert _saldo(engine, est) == 100   # nada foi convertido nem baixado em silencio


def test_unidade_igual_baixa_normalmente(ctx):
    c, engine, ag, vet, est = _montar(ctx, unidade_estoque="ml", unidade_dose="ml")
    r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est)
    assert r.status_code == 200, r.text
    ap = r.json()["aplicacao"]
    assert ap["unidade"] == "ml" and ap["baixa_automatica"] is True
    assert _saldo(engine, est) == 96


def test_unidade_incompativel_com_o_produto_e_recusada(ctx):
    c, engine, ag, vet, est = _montar(ctx, unidade_estoque="ml", unidade_dose="comprimido")
    r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est)
    assert r.status_code == 400 and "comprimido" in r.text
