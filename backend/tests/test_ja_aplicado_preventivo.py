"""Animal que JA recebeu o produto da regra no ciclo (lancado por qualquer caminho):
sai da lista de espera, nao entra em agendamento e, na gaveta Aplicar, exige
decisao por animal (aplicar mesmo assim com motivo | desconsiderar)."""
from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from fazenda.models import (
    CalendarioSanitario, CronogramaSanitario, CronogramaSanitarioAnimal, EventoSanitario, Sanidade,
)
from tests.test_aplicar_agendamento_preventivo import (  # noqa: F401  (fixtures + helpers)
    HOJE, _agendar, _aplicar, _animal, _espera, _estoque, _pessoas, _regra, _saldo, _status, cenario, ctx,
)


def _san(engine, numero, produto="B19", dias_atras=90, **kw):
    with Session(engine) as s:
        s.add(Sanidade(numero_matriz=numero, data_aplicacao=HOJE - timedelta(days=dias_atras), produto=produto,
                       dose=1, unidade="dose", fazenda_id=1, **kw))
        s.commit()


def _base(ctx, animais=("1", "2", "3")):
    c, engine = ctx
    with Session(engine) as s:
        vet, _ = _pessoas(s)
        est, lotes = _estoque(s)
        for n in animais:
            _animal(s, n)
        cal = _regra(s)
        cron = _espera(s, cal, list(animais))
    return c, engine, cal, cron, vet, est


def _linhas(engine, cron):
    with Session(engine) as s:
        return {l.numero_matriz: l for l in s.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == cron)).all()}


# ─────────────────────────── lista de espera ───────────────────────────
class TestListaDeEspera:
    def test_animal_com_lancamento_antigo_no_ciclo_sai_da_lista_ao_abrir(self, ctx):
        c, engine, cal, cron, vet, est = _base(ctx)
        _san(engine, "2", "B19", 90, usuario_id=None)        # historico importado (Sanidade legada)
        r = c.get("/sanidade/cronogramas/lista-espera").json()
        nums = [a["numero_matriz"] for g in r["grupos"] for a in g["animais"]]
        assert sorted(nums) == ["1", "3"] and r["total"] == 2
        rec = r["reconciliados"]
        assert [x["numero_matriz"] for x in rec] == ["2"]
        assert rec[0]["data"] == (HOJE - timedelta(days=90)).isoformat() and rec[0]["produto"] == "B19"
        ln = _linhas(engine, cron)["2"]
        assert ln.status == "excluido" and "Já aplicado em" in ln.motivo and (HOJE - timedelta(days=90)).strftime("%d/%m/%Y") in ln.motivo

    def test_aplicacao_fora_do_ciclo_ou_de_outro_produto_nao_tira(self, ctx):
        c, engine, cal, cron, vet, est = _base(ctx)
        _san(engine, "1", "B19", 400)            # ha mais de um ciclo
        _san(engine, "2", "Ivermectina", 10)     # outro produto
        r = c.get("/sanidade/cronogramas/lista-espera").json()
        assert r["total"] == 3 and r["reconciliados"] == []

    def test_aplicado_por_lancamento_de_sanidade_do_usuario_tambem_sai(self, ctx):
        c, engine, cal, cron, vet, est = _base(ctx)
        _san(engine, "3", "b19 ", 5, usuario_id=None, natureza="curativo")   # caixa/espaco diferentes, natureza qualquer
        r = c.get("/sanidade/cronogramas/lista-espera").json()
        assert [x["numero_matriz"] for x in r["reconciliados"]] == ["3"]

    def test_resumo_da_agenda_e_painel_nao_conta_quem_ja_foi_aplicado(self, ctx):
        from fazenda.rules import cronograma_sanitario as crono
        c, engine, cal, cron, vet, est = _base(ctx)
        _san(engine, "1", "B19", 30)
        with Session(engine) as s:
            resumo = crono.resumo_lista_espera(s, 1)
        assert resumo and resumo[0]["quantidade"] == 2

    def test_mesmo_principio_ativo_conta_como_mesmo_produto(self, ctx):
        c, engine, cal, cron, vet, est = _base(ctx)
        with Session(engine) as s:   # segundo item de estoque (marca antiga) com o MESMO principio ativo do B19
            from fazenda.models import Estoque
            item = s.get(Estoque, est)
            s.add(Estoque(nome="Brucella Abortus Marca Antiga", unidade="dose", quantidade=0, principio_ativo_id=item.principio_ativo_id,
                          fazenda_id=1, finalidade="Medicamento"))
            s.commit()
        _san(engine, "1", "Brucella Abortus Marca Antiga", 20)
        r = c.get("/sanidade/cronogramas/lista-espera").json()
        assert [x["numero_matriz"] for x in r["reconciliados"]] == ["1"]

    def test_regra_por_evento_de_vida_conta_a_partir_do_gatilho(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            _estoque(s)
            _animal(s, "1")   # nasceu ha 150 dias
            _animal(s, "2")
            cal_id = _regra(s)
            cal = s.get(CalendarioSanitario, cal_id)
            ev = s.get(EventoSanitario, cal.evento_sanitario_id)
            ev.tipo_agendamento, ev.gatilho, ev.offset_dias = "evento", "nascimento", 0
            s.add(ev); s.commit()
            _espera(s, cal_id, ["1", "2"])
        _san(engine, "1", "B19", 100)   # depois do nascimento (150 d atras) -> ja aplicado
        _san(engine, "2", "B19", 200)   # antes do nascimento -> nao vale para este gatilho
        r = c.get("/sanidade/cronogramas/lista-espera").json()
        assert [x["numero_matriz"] for x in r["reconciliados"]] == ["1"]
        assert [a["numero_matriz"] for g in r["grupos"] for a in g["animais"]] == ["2"]

    def test_rotina_e_sugestao_nao_recolocam_quem_ja_foi_aplicado(self, ctx):
        from fazenda.rules import cronograma_sanitario as crono
        c, engine = ctx
        with Session(engine) as s:
            _pessoas(s); _estoque(s)
            for n in ("1", "2"):
                _animal(s, n)
            cal = s.get(CalendarioSanitario, _regra(s))
        _san(engine, "1", "B19", 20)
        with Session(engine) as s:
            cal = s.exec(select(CalendarioSanitario)).first()
            crono.sugerir_animais_em_lote(s, cal, ["1", "2"], HOJE)
            assert crono.sugerir_animal(s, cal, "1", HOJE) is None
            nums = sorted(l.numero_matriz for l in s.exec(select(CronogramaSanitarioAnimal)).all())
        assert nums == ["2"]


# ─────────────────────────── criar agendamento ───────────────────────────
def test_criar_agendamento_recusa_e_reconcilia_animal_ja_aplicado(ctx):
    c, engine, cal, cron, vet, est = _base(ctx)
    _san(engine, "2", "B19", 30)
    r = c.post("/sanidade/cronogramas/agendamentos", json={
        "calendario_sanitario_id": cal, "animais_janela": ["1", "2"], "animais_fora": [],
        "data_evento": HOJE.isoformat(), "hora": "10:00",
    })
    assert r.status_code == 400 and "já recebeu" in r.text and "2" in r.text
    assert _linhas(engine, cron)["2"].status == "excluido"      # reconciliou mesmo recusando
    ok = c.post("/sanidade/cronogramas/agendamentos", json={
        "calendario_sanitario_id": cal, "animais_janela": ["1", "3"], "animais_fora": [],
        "data_evento": HOJE.isoformat(), "hora": "10:00",
    })
    assert ok.status_code == 200, ok.text


# ─────────────────────────── gaveta Aplicar ───────────────────────────
def _agendado(ctx, animais=("1", "2", "3")):
    c, engine, cal, cron, vet, est = _base(ctx, animais)
    ag = _agendar(c, cal, list(animais), vet=vet)["id"]
    return c, engine, cal, ag, vet, est


class TestAplicar:
    def test_contexto_marca_o_animal_que_ja_tem_aplicacao_no_ciclo(self, ctx):
        c, engine, cal, ag, vet, est = _agendado(ctx)
        _san(engine, "2", "B19", 45, usuario_id=None)
        r = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
        por = {a["numero_matriz"]: a for a in r["animais"]}
        assert por["1"]["ja_aplicado"] is None
        j = por["2"]["ja_aplicado"]
        assert j["data"] == (HOJE - timedelta(days=45)).isoformat() and j["produto"] == "B19" and j["dias"] == 45
        assert r["n_ja_aplicados"] == 1 and r["motivos_ja_aplicado"] == ["Dose extra", "Reforço", "Outro"]

    def test_aplicar_sem_decisao_e_recusado_e_nada_e_gravado(self, ctx):
        c, engine, cal, ag, vet, est = _agendado(ctx)
        _san(engine, "2", "B19", 45)
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 400 and "Animal 2" in r.text and "Aplicar mesmo assim" in r.text
        assert _saldo(engine, est) == 100
        with Session(engine) as s:
            assert len(s.exec(select(Sanidade)).all()) == 1   # so a antiga

    def test_aplicar_mesmo_assim_exige_motivo_valido_e_fica_registrado(self, ctx):
        c, engine, cal, ag, vet, est = _agendado(ctx)
        _san(engine, "2", "B19", 45)
        ruim = _aplicar(c, ag, animais_aplicados=["1", "2", "3"], aplicador_pessoa_id=vet, estoque_id=est,
                        ja_aplicados={"2": {"motivo": "Porque sim"}})
        assert ruim.status_code == 400
        sem_obs = _aplicar(c, ag, animais_aplicados=["1", "2", "3"], aplicador_pessoa_id=vet, estoque_id=est,
                           ja_aplicados={"2": {"motivo": "Outro"}})
        assert sem_obs.status_code == 400
        ok = _aplicar(c, ag, animais_aplicados=["1", "2", "3"], aplicador_pessoa_id=vet, estoque_id=est,
                      ja_aplicados={"2": {"motivo": "Reforço"}})
        assert ok.status_code == 200, ok.text
        ap = ok.json()["aplicacao"]
        assert any("Animal 2 aplicado mesmo já tendo recebido" in e and "Reforço" in e for e in ap["excecoes"])
        with Session(engine) as s:
            san = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "2").order_by(Sanidade.id.desc())).first()
            assert "Reforço" in san.obs and "já aplicado em" in san.obs

    def test_desconsiderar_tira_do_agendamento_sem_precisar_de_decisao(self, ctx):
        c, engine, cal, ag, vet, est = _agendado(ctx)
        _san(engine, "2", "B19", 45)
        r = _aplicar(c, ag, animais_aplicados=["1", "3"], aplicador_pessoa_id=vet, estoque_id=est,
                     nao_aplicados=[{"numero_matriz": "2", "motivo": "Já aplicado em outro lançamento", "destino": "naoSeAplica"}])
        assert r.status_code == 200, r.text
        assert _status(engine, ag) == {"1": "aplicado", "2": "excluido", "3": "aplicado"}
        assert _saldo(engine, est) == 98

    def test_aplicacao_do_curral_vira_ja_aplicado_no_agendamento_seguinte(self, ctx):
        c, engine, cal, ag, vet, est = _agendado(ctx, ("1", "2"))
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est, canal="Curral")
        assert r.status_code == 200, r.text
        with Session(engine) as s:   # animal volta a um novo cronograma da mesma regra (ex.: cadastro/correcao)
            cron2 = CronogramaSanitario(calendario_sanitario_id=cal, data_evento=HOJE, status="agendado", modo_execucao="propria", fazenda_id=1)
            s.add(cron2); s.commit(); s.refresh(cron2)
            s.add(CronogramaSanitarioAnimal(cronograma_id=cron2.id, numero_matriz="1", status="incluido", data_sugestao=HOJE, fazenda_id=1))
            s.commit()
            novo = cron2.id
        ctxo = c.get(f"/sanidade/cronogramas/{novo}/aplicar-contexto").json()
        j = ctxo["animais"][0]["ja_aplicado"]
        assert j["fonte"] == "Protocolo preventivo · Curral" and j["dias"] == 0

    def test_animal_sem_historico_aplica_normalmente_como_antes(self, ctx):
        c, engine, cal, ag, vet, est = _agendado(ctx)
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 200 and _saldo(engine, est) == 97


def test_acompanhamento_conta_animais_ja_aplicados_do_agendamento(ctx):
    c, engine, cal, ag, vet, est = _agendado(ctx)
    _san(engine, "2", "B19", 45)
    itens = c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"]
    assert [i["animais_ja_aplicados"] for i in itens if i["id"] == ag] == [1]
