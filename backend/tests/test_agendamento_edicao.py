"""
Fatia 9b, item C do planejamento unificado: editar um agendamento ja criado.

  * "Reabrir para editar": agendado -> em montagem (sai da Agenda, animais e checklist ficam; a data nao muda);
    nao vale depois de aplicado/cancelado nem depois da inoculacao de um exame.
  * "Tirar animal": motivo em chips; volta a lista de espera (janela) — ou fica "baixado" se foi vendido/saiu do
    rebanho; o de fora da janela so sai (nao ha lista para onde voltar); nunca o ultimo animal.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from sqlmodel import Session, select

from fazenda.models import (
    Animal, CronogramaSanitario, CronogramaSanitarioAnimal, CronogramaSanitarioLog,
)

from tests.test_exame_preventivo import (  # noqa: F401  (fixtures e montagem do cenario)
    HOJE, _USUARIO, _agendar, _animal, _aplicar, _espera, _estoque, _pessoas, _regra, ctx, tb,
)


@pytest.fixture
def vac(ctx):
    """Vacina com 4 animais no agendamento de hoje (1 fora da janela) e o resto na lista de espera."""
    c, engine = ctx
    with Session(engine) as s:
        vet, peao = _pessoas(s)
        est, lote = _estoque(s, "Raiva")
        for n in ("1", "2", "3", "4", "9"):
            _animal(s, n)
        cal = _regra(s, "Raiva", produto="Raiva", categoria="vacina", via="Subcutânea")
        _espera(s, cal, ["1", "2", "3", "4"])
    r = c.post("/sanidade/cronogramas/agendamentos", json={
        "calendario_sanitario_id": cal, "animais_janela": ["1", "2", "3"], "data_evento": HOJE.isoformat(), "hora": "10:00",
        "animais_fora": [{"numero_matriz": "9", "motivo": "Aproveitar a visita do veterinário"}],
        "modo_execucao": "veterinario", "veterinario_pessoa_id": vet})
    assert r.status_code == 200, r.text
    return {"c": c, "engine": engine, "ag": r.json()["id"], "cal": cal, "vet": vet, "peao": peao, "est": est}


def _linhas(engine, cron_id):
    with Session(engine) as s:
        return {l.numero_matriz: l for l in s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron_id)).all()}


class TestReabrirParaEditar:
    def test_agendado_volta_a_montagem_sem_mudar_data_nem_animais(self, vac):
        c, engine, ag = vac["c"], vac["engine"], vac["ag"]
        r = c.post(f"/sanidade/cronogramas/{ag}/reabrir-para-editar", json={"motivo": "Trocar o veterinário"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "em_montagem" and r.json()["data_evento"] == HOJE.isoformat() and r.json()["hora"] == "10:00"
        with Session(engine) as s:
            cron = s.get(CronogramaSanitario, ag)
            assert cron.status == "em_montagem" and cron.data_evento == HOJE
            log = [l for l in s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag)).all() if l.acao == "Reabriu para editar"]
            assert len(log) == 1 and log[0].motivo == "Trocar o veterinário" and log[0].usuario_id == 1
        assert {n for n, l in _linhas(engine, ag).items() if l.status == "incluido"} == {"1", "2", "3", "9"}
        # em montagem NAO entra na Agenda
        dia = c.get("/agenda", params={"data": HOJE.isoformat()}).json()
        assert not [e for e in dia["eventos"] if e["id"] == f"cronograma_sanitario_aplicar_{ag}"]
        ac = c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"]
        assert next(a for a in ac if a["id"] == ag)["estado_visual"] == "em_montagem"

    def test_pode_confirmar_de_novo_e_volta_para_a_agenda(self, vac):
        c, ag = vac["c"], vac["ag"]
        assert c.post(f"/sanidade/cronogramas/{ag}/reabrir-para-editar", json={}).status_code == 200
        r = c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={"data_evento": HOJE.isoformat(), "hora": "11:00",
                                                                   "modo_execucao": "veterinario", "veterinario_pessoa_id": vac["vet"]})
        assert r.status_code == 200, r.text
        dia = c.get("/agenda", params={"data": HOJE.isoformat()}).json()
        assert [e for e in dia["eventos"] if e["id"] == f"cronograma_sanitario_aplicar_{ag}"]

    def test_nao_reabre_o_que_ja_foi_aplicado_cancelado_ou_esta_em_montagem(self, vac):
        c, ag = vac["c"], vac["ag"]
        assert c.post(f"/sanidade/cronogramas/{ag}/reabrir-para-editar", json={}).status_code == 200
        r = c.post(f"/sanidade/cronogramas/{ag}/reabrir-para-editar", json={})
        assert r.status_code == 400 and "montagem" in r.json()["detail"].lower()
        c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={"data_evento": HOJE.isoformat(), "modo_execucao": "propria"})
        assert _aplicar(c, ag, aplicador_pessoa_id=vac["peao"], animais_aplicados=["1", "2", "3", "9"], estoque_id=vac["est"]).status_code == 200
        r = c.post(f"/sanidade/cronogramas/{ag}/reabrir-para-editar", json={})
        assert r.status_code == 400 and "aplicado" in r.json()["detail"].lower()

    def test_nao_reabre_exame_ja_inoculado(self, tb):
        from tests.test_exame_preventivo import _inocular
        assert _inocular(tb).status_code == 200
        r = tb["c"].post(f"/sanidade/cronogramas/{tb['ag']}/reabrir-para-editar", json={})
        assert r.status_code == 400 and "inocul" in r.json()["detail"].lower()

    def test_outra_fazenda_e_404(self, vac):
        _USUARIO["fazenda"] = 2
        assert vac["c"].post(f"/sanidade/cronogramas/{vac['ag']}/reabrir-para-editar", json={}).status_code == 404


class TestTirarAnimal:
    def _tirar(self, t, numero, motivo, **kw):
        return t["c"].post(f"/sanidade/cronogramas/{t['ag']}/animais/remover", json={"numero_matriz": numero, "motivo": motivo, **kw})

    def test_da_janela_volta_a_lista_de_espera_com_o_motivo(self, vac):
        c, engine, ag = vac["c"], vac["engine"], vac["ag"]
        r = self._tirar(vac, "2", "Doente")
        assert r.status_code == 200, r.text
        assert r.json()["destino"] == "espera"
        assert {n for n, l in _linhas(engine, ag).items() if l.status == "incluido"} == {"1", "3", "9"}
        espera = c.get("/sanidade/cronogramas/lista-espera").json()
        nums = [a["numero_matriz"] for g in espera["grupos"] for a in g["animais"]]
        assert sorted(nums) == ["2", "4"]
        with Session(engine) as s:
            log = [l for l in s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag)).all() if l.acao == "Tirou animal"]
            assert len(log) == 1 and log[0].motivo == "Doente" and "2" in log[0].detalhe

    def test_vendido_fica_baixado_e_nao_volta_para_a_lista(self, vac):
        c, engine, ag = vac["c"], vac["engine"], vac["ag"]
        r = self._tirar(vac, "3", "Vendido")
        assert r.status_code == 200 and r.json()["destino"] == "baixado"
        linha = _linhas(engine, ag)["3"]
        assert linha.status == "excluido" and "vendido" in (linha.motivo or "").lower()
        espera = c.get("/sanidade/cronogramas/lista-espera").json()
        assert "3" not in [a["numero_matriz"] for g in espera["grupos"] for a in g["animais"]]

    def test_animal_que_ja_saiu_do_rebanho_tambem_e_baixado(self, vac):
        with Session(vac["engine"]) as s:
            a = s.exec(select(Animal).where(Animal.numero == "1")).first()
            a.ativo = False
            s.add(a)
            s.commit()
        r = self._tirar(vac, "1", "Outro", motivo_outro="Saiu para o abate")
        assert r.status_code == 200 and r.json()["destino"] == "baixado"

    def test_fora_da_janela_so_sai(self, vac):
        r = self._tirar(vac, "9", "Não localizado")
        assert r.status_code == 200 and r.json()["destino"] == "saiu"
        espera = vac["c"].get("/sanidade/cronogramas/lista-espera").json()
        assert "9" not in [a["numero_matriz"] for g in espera["grupos"] for a in g["animais"]]

    def test_exige_motivo_e_animal_do_agendamento(self, vac):
        assert self._tirar(vac, "2", "").status_code == 400
        r = self._tirar(vac, "4", "Doente")          # 4 esta na lista de espera, nao no agendamento
        assert r.status_code == 400 and "não está" in r.json()["detail"].lower()
        r = self._tirar(vac, "2", "Motivo inventado")
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()

    def test_outro_exige_texto(self, vac):
        assert self._tirar(vac, "2", "Outro").status_code == 400
        assert self._tirar(vac, "2", "Outro", motivo_outro="Mudou de lote").status_code == 200

    def test_nao_tira_o_ultimo_animal(self, vac):
        for n in ("1", "2", "3"):
            assert self._tirar(vac, n, "Doente").status_code == 200
        r = self._tirar(vac, "9", "Doente")
        assert r.status_code == 400 and "cancele" in r.json()["detail"].lower()

    def test_nao_tira_de_agendamento_aplicado(self, vac):
        c = vac["c"]
        assert _aplicar(c, vac["ag"], aplicador_pessoa_id=vac["peao"], animais_aplicados=["1", "2", "3", "9"], estoque_id=vac["est"]).status_code == 200
        r = self._tirar(vac, "2", "Doente")
        assert r.status_code == 400

    def test_nao_tira_animal_de_exame_ja_inoculado(self, tb):
        from tests.test_exame_preventivo import _inocular
        assert _inocular(tb).status_code == 200
        r = tb["c"].post(f"/sanidade/cronogramas/{tb['ag']}/animais/remover", json={"numero_matriz": "1", "motivo": "Doente"})
        assert r.status_code == 400 and "inocul" in r.json()["detail"].lower()

    def test_funciona_em_montagem_e_reflete_no_checklist_e_no_financeiro(self, vac):
        c, ag = vac["c"], vac["ag"]
        assert c.post(f"/sanidade/cronogramas/{ag}/reabrir-para-editar", json={}).status_code == 200
        r = self._tirar(vac, "2", "Doente")
        assert r.status_code == 200
        assert r.json()["agendamento"]["animais_contagem"]["incluido"] == 3
        fin = c.get(f"/sanidade/cronogramas/{ag}/financeiro").json()
        assert fin["necessidade"]["animais"] == 3

    def test_outra_fazenda_e_404(self, vac):
        _USUARIO["fazenda"] = 2
        assert self._tirar(vac, "2", "Doente").status_code == 404
