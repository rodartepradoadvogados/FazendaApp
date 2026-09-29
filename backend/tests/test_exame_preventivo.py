"""
Fatia 9b do planejamento unificado: EXAME no aplicar unico (POST /sanidade/cronogramas/{id}/aplicar).

Tuberculina (TB): 1a etapa = inoculacao (data/hora, veterinario, frasco, baixa de estoque; NAO vai para
Concluidos e marca a leitura para 72 h depois, na Agenda); 2a etapa = leitura (resultado por animal:
negativo / reagente / inconclusivo, espessura da pele em mm, tipo de teste, laudo; janela de 72-96 h
sinalizada; antes de 72 h so com justificativa) — esse e o registro concluido ("Exame realizado").
Reagente: banner persistente com a notificacao (quem/quando), o animal sai dos agendamentos/lista de
espera de outras vacinas e nao entra em novos, o comprovante e bloqueado so para ele. Inconclusivo:
reteste 60 dias depois na lista de espera ("Reteste atrasado" quando passa). Exame sem leitura
(brucelose): coleta em uma etapa so, com laudo. Desfazer/estornar revertem tudo e preservam a original.
Tambem: canal "Curral" (app do peao) e a trava do B19 (so femea de 3 a 8 meses).
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, CalendarioSanitario, ContratoFazenda, ContratoFazendaModulo, CronogramaSanitario, CronogramaSanitarioAnimal,
    CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacaoAnimal, CronogramaSanitarioLog, Estoque, EventoSanitario,
    ExameResultado, Fazenda, LoteEstoque, MedicamentoComercial, Pessoa, PrincipioAtivo,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.parametros import fazenda_atual

HOJE = date.today()
_USUARIO = {"id": 1, "papel": "admin"}


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    _USUARIO.update(id=1, papel="admin")
    _USUARIO.pop("fazenda", None)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Estreito"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id
    from fastapi import HTTPException

    class _FakeUser:
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""
        nome = "Gestor Teste"

        @property
        def id(self):
            return _USUARIO["id"]

        @property
        def papel(self):
            return _USUARIO["papel"]

    def _admin():
        if _USUARIO["papel"] != "admin":
            raise HTTPException(status_code=403, detail="Requer administrador")
        return _FakeUser()

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[exigir_admin] = _admin
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: _USUARIO.get("fazenda", 1)
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()
    fazenda_atual.set(None)


# ─────────────────────────── montagem do cenario ───────────────────────────
def _pessoas(s: Session) -> tuple[int, int]:
    vet = Pessoa(nome="Dr. Paulo", tipo="Veterinário", crmv="CRMV-MG 12345", fazenda_id=1)
    peao = Pessoa(nome="Zeca", tipo="Funcionário", fazenda_id=1)
    s.add(vet)
    s.add(peao)
    s.commit()
    s.refresh(vet)
    s.refresh(peao)
    return vet.id, peao.id


def _estoque(s: Session, nome: str, saldo: float = 100.0, unidade: str = "dose", valor: float | None = 9.0,
             numero_lote: str = "TB-1") -> tuple[int, int]:
    pa = PrincipioAtivo(nome=f"PA {nome}", fazenda_id=1)
    s.add(pa)
    s.commit()
    s.refresh(pa)
    mc = MedicamentoComercial(principio_ativo_id=pa.id, nome_comercial=nome, fazenda_id=1, dose_base="por_animal",
                              dose_padrao=1.0, unidade_dose=unidade)
    s.add(mc)
    s.commit()
    s.refresh(mc)
    item = Estoque(nome=nome, unidade=unidade, quantidade=saldo, valor_unitario=valor, principio_ativo_id=pa.id,
                   medicamento_comercial_id=mc.id, fazenda_id=1, finalidade="Medicamento")
    s.add(item)
    s.commit()
    s.refresh(item)
    lote = LoteEstoque(estoque_id=item.id, numero_lote=numero_lote, data_compra=HOJE - timedelta(days=30),
                       quantidade_comprada=saldo, quantidade_restante=saldo, validade=HOJE + timedelta(days=200), fazenda_id=1)
    s.add(lote)
    s.commit()
    s.refresh(lote)
    return item.id, lote.id


def _animal(s: Session, numero: str, *, sexo: str = "F", meses: int = 5, grupo: str = "Lote 02", ativo: bool = True) -> None:
    s.add(Animal(numero=numero, nome=f"Animal {numero}", sexo=sexo, ativo=ativo, grupo_primario=grupo,
                 data_nasc=HOJE - timedelta(days=int(meses * 30.5)), fazenda_id=1))


def _regra(s: Session, nome: str, *, produto: str | None, categoria: str = "exame", dose: float | None = 1.0,
           unidade: str | None = "dose", via: str | None = "Intradérmica") -> int:
    ev = EventoSanitario(nome=nome, tipo_agendamento="epoca", categoria_preventiva=categoria, produto_padrao=produto,
                         dose_padrao=dose if produto else None, unidade_padrao=unidade if produto else None,
                         via_padrao=via, fazenda_id=1)
    s.add(ev)
    s.commit()
    s.refresh(ev)
    cal = CalendarioSanitario(evento_sanitario_id=ev.id, categoria_alvo="Rebanho", produto=produto, frequencia_valor=12,
                              frequencia_unidade="meses", data_evento=HOJE - timedelta(days=2), usa_cronograma=True, fazenda_id=1)
    s.add(cal)
    s.commit()
    s.refresh(cal)
    return cal.id


def _espera(s: Session, cal_id: int, numeros: list[str]) -> int:
    cron = CronogramaSanitario(calendario_sanitario_id=cal_id, data_evento=HOJE - timedelta(days=2), status="aberto", fazenda_id=1)
    s.add(cron)
    s.commit()
    s.refresh(cron)
    for n in numeros:
        s.add(CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=n, status="sugerido", data_sugestao=HOJE, fazenda_id=1))
    s.commit()
    return cron.id


def _agendar(c, cal_id: int, janela: list[str], *, vet: int | None = None, data: date | None = None, hora: str = "08:00") -> dict:
    corpo = {"calendario_sanitario_id": cal_id, "animais_janela": janela, "animais_fora": [],
             "data_evento": (data or HOJE).isoformat(), "hora": hora}
    if vet:
        corpo.update(modo_execucao="veterinario", veterinario_pessoa_id=vet)
    r = c.post("/sanidade/cronogramas/agendamentos", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _aplicar(c, ag_id: int, **kw):
    corpo = {"canal": "Protocolos"}
    corpo.update(kw)
    return c.post(f"/sanidade/cronogramas/{ag_id}/aplicar", json=corpo)


@pytest.fixture
def tb(ctx):
    """Exame de TB (tuberculina em estoque, 100 doses) com 4 animais agendados para hoje, veterinario e peao."""
    c, engine = ctx
    with Session(engine) as s:
        vet, peao = _pessoas(s)
        est, lote = _estoque(s, "Tuberculina PPD")
        for n in ("1", "2", "3", "4"):
            _animal(s, n)
        cal = _regra(s, "Exame de Tuberculose (TB)", produto="Tuberculina PPD")
        _espera(s, cal, ["1", "2", "3", "4"])
    ag = _agendar(c, cal, ["1", "2", "3", "4"], vet=vet)
    return {"c": c, "engine": engine, "ag": ag["id"], "cal": cal, "vet": vet, "peao": peao, "est": est, "lote": lote}


def _inocular(t, *, data: date | None = None, hora: str = "08:00", animais: list[str] | None = None, **kw):
    corpo = {"aplicador_pessoa_id": t["vet"], "animais_aplicados": animais or ["1", "2", "3", "4"], "estoque_id": t["est"],
             "lote_id": t["lote"], "data_aplicacao": (data or HOJE).isoformat(), "hora": hora}
    corpo.update(kw)
    return _aplicar(t["c"], t["ag"], **corpo)


def _ler(t, resultados: dict[str, str], *, data: date | None = None, hora: str = "10:00", mm: float = 3.0, **kw):
    corpo = {"aplicador_pessoa_id": t["vet"], "data_aplicacao": (data or HOJE).isoformat(), "hora": hora,
             "resultados": resultados, "espessuras_mm": {n: mm for n in resultados}, "tipo_teste": "Cervical simples"}
    corpo.update(kw)
    return _aplicar(t["c"], t["ag"], **corpo)


def _pronto_para_ler(t):
    """Inoculacao ha 3 dias as 08:00 (hoje e o dia da leitura, 72 h + 2 h as 10:00)."""
    r = _inocular(t, data=HOJE - timedelta(days=3), hora="08:00")
    assert r.status_code == 200, r.text
    return r.json()


def _saldo(engine, est: int) -> float:
    with Session(engine) as s:
        return s.get(Estoque, est).quantidade


# ─────────────────────────────── inoculacao ───────────────────────────────
class TestInoculacao:
    def test_inoculacao_baixa_estoque_marca_leitura_em_72h_e_nao_vai_para_concluidos(self, tb):
        c, engine, ag = tb["c"], tb["engine"], tb["ag"]
        r = _inocular(tb, hora="08:30", tipo_teste="Cervical comparativo")
        assert r.status_code == 200, r.text
        dados = r.json()
        ap = dados["aplicacao"]
        assert ap["fase"] == "inoculacao" and ap["estado"] == "aplicada"
        assert ap["aplicador_nome"] == "Dr. Paulo" and ap["aplicador_crmv"] == "CRMV-MG 12345"
        assert ap["tipo_teste"] == "Cervical comparativo"
        assert ap["lote_texto"] == "TB-1" and ap["dose_total"] == 4
        assert ap["leitura_prevista_em"].startswith((HOJE + timedelta(days=3)).isoformat() + "T08:30")
        assert ap["leitura_limite_em"].startswith((HOJE + timedelta(days=4)).isoformat() + "T08:30")
        assert _saldo(engine, tb["est"]) == 96
        cron = dados["agendamento"]
        assert cron["status"] == "agendado"                 # continua agendado: falta a leitura
        assert cron["data_evento"] == (HOJE + timedelta(days=3)).isoformat() and cron["hora"] == "08:30"
        # Concluidos so tem o exame quando a leitura sair
        assert c.get("/sanidade/cronogramas/concluidos").json()["itens"] == []
        # a inoculacao nao gera resultado de exame nem linha de Sanidade
        with Session(engine) as s:
            assert s.exec(select(ExameResultado)).all() == []
            log = s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag)).all()
            assert [l.acao for l in log if l.acao.startswith("Aplicou")] == ["Aplicou (inoculação)"]

    def test_contexto_muda_de_fase_e_traz_a_inoculacao_e_a_janela_de_leitura(self, tb):
        c, ag = tb["c"], tb["ag"]
        antes = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
        assert antes["tipo"] == "exame" and antes["exame"]["fase"] == "inoculacao"
        assert antes["exame"]["tipo_exame"] == "tuberculina" and antes["exame"]["leitura_horas"] == 72
        assert antes["exame"]["tipos_teste"] == ["Cervical simples", "Cervical comparativo", "Prega caudal"]
        assert antes["exame"]["inoculacao"] is None and antes["exige_veterinario"] is True
        _pronto_para_ler(tb)
        depois = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
        ex = depois["exame"]
        assert ex["fase"] == "leitura" and ex["inoculacao"]["lote_texto"] == "TB-1"
        assert ex["inoculacao"]["data"] == (HOJE - timedelta(days=3)).isoformat() and ex["inoculacao"]["hora"] == "08:00"
        assert ex["leitura_prevista_em"].startswith(HOJE.isoformat() + "T08:00")
        assert ex["leitura_limite_em"].startswith((HOJE + timedelta(days=1)).isoformat() + "T08:00")
        assert {a["numero_matriz"] for a in depois["animais"]} == {"1", "2", "3", "4"}

    def test_so_veterinario_com_crmv_inocula(self, tb):
        r = _inocular(tb, aplicador_pessoa_id=tb["peao"])
        assert r.status_code == 400 and "veterinário" in r.json()["detail"].lower()
        assert _saldo(tb["engine"], tb["est"]) == 100

    def test_quem_nao_foi_inoculado_sai_do_agendamento_com_motivo(self, tb):
        r = _inocular(tb, animais=["1", "2", "3"])
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()
        r = _inocular(tb, animais=["1", "2", "3"], nao_aplicados=[{"numero_matriz": "4", "motivo": "Doente", "destino": "espera"}])
        assert r.status_code == 200, r.text
        assert _saldo(tb["engine"], tb["est"]) == 97
        ctx = tb["c"].get(f"/sanidade/cronogramas/{tb['ag']}/aplicar-contexto").json()
        assert {a["numero_matriz"] for a in ctx["animais"]} == {"1", "2", "3"}
        espera = tb["c"].get("/sanidade/cronogramas/lista-espera").json()
        assert [a["numero_matriz"] for g in espera["grupos"] for a in g["animais"]] == ["4"]

    def test_estoque_desconsiderado_nao_baixa(self, tb):
        r = _inocular(tb, estoque_id=None, lote_id=None, desconsiderar_estoque=True,
                      motivo_desconsiderar_estoque="Frasco do veterinário", lote_veterinario="VET-778")
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"]["lote_texto"] == "VET-778" and r.json()["aplicacao"]["estoque_desconsiderado"] is True
        assert _saldo(tb["engine"], tb["est"]) == 100

    def test_inoculacao_nao_pode_repetir(self, tb):
        assert _inocular(tb).status_code == 200
        # agora e a fase de leitura: pedir "inoculacao" de novo sem resultados nao vale
        r = _aplicar(tb["c"], tb["ag"], aplicador_pessoa_id=tb["vet"], animais_aplicados=["1"], estoque_id=tb["est"])
        assert r.status_code == 400 and "resultado" in r.json()["detail"].lower()

    def test_desfazer_em_10s_devolve_estoque_e_data_do_agendamento(self, tb):
        c, engine, ag = tb["c"], tb["engine"], tb["ag"]
        ap = _inocular(tb).json()["aplicacao"]
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/desfazer")
        assert r.status_code == 200, r.text
        assert _saldo(engine, tb["est"]) == 100
        with Session(engine) as s:
            cron = s.get(CronogramaSanitario, ag)
            assert cron.status == "agendado" and cron.data_evento == HOJE and cron.hora == "08:00"
        ctx = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
        assert ctx["exame"]["fase"] == "inoculacao" and ctx["exame"]["inoculacao"] is None

    def test_estornar_inoculacao_so_admin_e_so_sem_leitura_ativa(self, tb):
        c, engine = tb["c"], tb["engine"]
        ap = _pronto_para_ler(tb)["aplicacao"]
        assert _ler(tb, {"1": "negativo", "2": "negativo", "3": "negativo", "4": "negativo"}).status_code == 200
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/estornar", json={"motivo": "Errei o frasco"})
        assert r.status_code == 400 and "leitura" in r.json()["detail"].lower()
        # estorna a leitura (admin) e depois a inoculacao
        leitura_id = c.get("/sanidade/cronogramas/concluidos").json()["itens"][0]["id"]
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{leitura_id}/estornar", json={"motivo": "Errei o animal"}).status_code == 200
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/estornar", json={"motivo": "Errei o frasco ou o produto"})
        assert r.status_code == 200, r.text
        assert _saldo(engine, tb["est"]) == 100
        with Session(engine) as s:
            cron = s.get(CronogramaSanitario, tb["ag"])
            assert cron.status == "agendado" and cron.data_evento == HOJE
        _USUARIO["papel"] = "gestor"
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/estornar", json={"motivo": "x"}).status_code == 403


# ─────────────────────────────── leitura ───────────────────────────────
class TestLeitura:
    def test_resultado_por_animal_grava_exame_reagente_e_reteste(self, tb):
        c, engine, ag = tb["c"], tb["engine"], tb["ag"]
        _pronto_para_ler(tb)
        r = _ler(tb, {"1": "negativo", "2": "negativo", "3": "reagente", "4": "inconclusivo"}, laudo="L-2609", hora="10:15")
        assert r.status_code == 200, r.text
        dados = r.json()
        ap = dados["aplicacao"]
        assert ap["fase"] == "leitura" and ap["laudo"] == "L-2609" and ap["tipo_teste"] == "Cervical simples"
        assert ap["leitura_fora_janela"] is False and ap["leitura_horas"] == pytest.approx(74.25)
        assert dados["agendamento"]["status"] == "concluido"
        por = {a["numero_matriz"]: a for a in ap["animais"]}
        assert por["1"]["exame_resultado"] == "negativo" and por["1"]["espessura_mm"] == 3.0
        assert por["3"]["exame_resultado"] == "reagente" and por["4"]["exame_resultado"] == "inconclusivo"
        assert por["4"]["reteste_em"] == (HOJE + timedelta(days=60)).isoformat() and por["1"]["reteste_em"] is None
        with Session(engine) as s:
            res = {e.numero_matriz: e for e in s.exec(select(ExameResultado)).all()}
            assert res["1"].resultado == "negativo" and res["3"].resultado == "positivo" and res["4"].resultado == "indefinido"
            assert res["3"].data_exame == HOJE and res["3"].veterinario == "Dr. Paulo"
            animais = {a.numero: a for a in s.exec(select(Animal)).all()}
            assert animais["3"].a_descartar is True and animais["1"].a_descartar is False
            linhas = {l.numero_matriz: l.status for l in s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == ag)).all()}
            assert set(linhas.values()) == {"aplicado"}
        # Concluidos: "Exame realizado", resumo do resultado e campos do exame
        item = c.get("/sanidade/cronogramas/concluidos").json()["itens"][0]
        assert item["id"] == ap["id"] and item["tipo"] == "exame" and item["rotulo_estado"] == "Exame realizado"
        ex = item["exame"]
        assert ex["negativos"] == 2 and ex["reagentes"] == 1 and ex["inconclusivos"] == 1
        assert ex["tipo_teste"] == "Cervical simples" and ex["laudo"] == "L-2609"
        assert ex["inoculacao_data"] == (HOJE - timedelta(days=3)).isoformat() and ex["inoculacao_hora"] == "08:00"
        assert ex["leitura_horas"] == pytest.approx(74.25) and ex["reagentes_pendentes_notificacao"] == 1
        assert ex["reteste_em"] == (HOJE + timedelta(days=60)).isoformat()

    def test_exige_resultado_mm_e_tipo_de_teste_de_todos(self, tb):
        _pronto_para_ler(tb)
        base = {"1": "negativo", "2": "negativo", "3": "negativo", "4": "negativo"}
        r = _ler(tb, {"1": "negativo", "2": "negativo", "3": "negativo"})
        assert r.status_code == 400 and "resultado de cada animal" in r.json()["detail"].lower()
        r = _ler(tb, base, espessuras_mm={"1": 3, "2": 3, "3": 3})
        assert r.status_code == 400 and "espessura" in r.json()["detail"].lower()
        r = _ler(tb, base, tipo_teste="")
        assert r.status_code == 400 and "tipo de teste" in r.json()["detail"].lower()
        r = _ler(tb, base, tipo_teste="Teste inventado")
        assert r.status_code == 400 and "tipo de teste" in r.json()["detail"].lower()
        r = _ler(tb, {**base, "4": "talvez"})
        assert r.status_code == 400 and "resultado" in r.json()["detail"].lower()
        r = _ler(tb, base, espessuras_mm={"1": 3, "2": 3, "3": 3, "4": -1})
        assert r.status_code == 400 and "espessura" in r.json()["detail"].lower()
        assert tb["c"].get("/sanidade/cronogramas/concluidos").json()["itens"] == []

    def test_leitura_antes_de_72h_so_com_justificativa(self, tb):
        assert _inocular(tb, data=HOJE, hora="00:00").status_code == 200
        base = {"1": "negativo", "2": "negativo", "3": "negativo", "4": "negativo"}
        r = _ler(tb, base, data=HOJE, hora="12:00")
        assert r.status_code == 400 and "72 h" in r.json()["detail"]
        r = _ler(tb, base, data=HOJE, hora="12:00", justificativa_leitura="Veterinário só passa hoje")
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["leitura_fora_janela"] is True and ap["leitura_justificativa"] == "Veterinário só passa hoje"
        assert any("antes de 72 h" in e.lower() for e in ap["excecoes"])

    def test_leitura_depois_de_96h_fica_sinalizada(self, tb):
        assert _inocular(tb, data=HOJE - timedelta(days=5), hora="08:00").status_code == 200
        r = _ler(tb, {"1": "negativo", "2": "negativo", "3": "negativo", "4": "negativo"}, hora="10:00")
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["leitura_fora_janela"] is True and ap["leitura_horas"] == pytest.approx(122.0)
        assert any("72–96 h" in e for e in ap["excecoes"])

    def test_leitura_nao_pode_ser_antes_da_inoculacao(self, tb):
        assert _inocular(tb, data=HOJE, hora="10:00").status_code == 200
        r = _ler(tb, {n: "negativo" for n in "1234"}, data=HOJE, hora="09:00", justificativa_leitura="x")
        assert r.status_code == 400 and "anterior" in r.json()["detail"].lower()

    def test_quem_le_precisa_ser_veterinario(self, tb):
        _pronto_para_ler(tb)
        r = _ler(tb, {n: "negativo" for n in "1234"}, aplicador_pessoa_id=tb["peao"])
        assert r.status_code == 400 and "veterinário" in r.json()["detail"].lower()

    def test_leitura_nao_baixa_estoque_de_novo(self, tb):
        _pronto_para_ler(tb)
        assert _saldo(tb["engine"], tb["est"]) == 96
        assert _ler(tb, {n: "negativo" for n in "1234"}).status_code == 200
        assert _saldo(tb["engine"], tb["est"]) == 96

    def test_desfazer_leitura_restaura_tudo(self, tb):
        c, engine, ag = tb["c"], tb["engine"], tb["ag"]
        _pronto_para_ler(tb)
        with Session(engine) as s:   # animal 3 tambem esta na lista de espera de outra vacina (sai quando for reagente)
            cal2 = _regra(s, "Aftosa", produto=None, categoria="vacina", dose=None, unidade=None)
            _espera(s, cal2, ["3"])
        ap = _ler(tb, {"1": "negativo", "2": "negativo", "3": "reagente", "4": "inconclusivo"}).json()["aplicacao"]
        with Session(engine) as s:
            assert s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.numero_matriz == "4")
                          .where(CronogramaSanitarioAnimal.reteste == True)).all()   # noqa: E712
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/desfazer")
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.exec(select(ExameResultado)).all() == []
            a3 = s.exec(select(Animal).where(Animal.numero == "3")).first()
            assert a3.a_descartar is False and a3.a_descartar_em is None
            assert s.get(CronogramaSanitario, ag).status == "agendado"
            assert {l.status for l in s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == ag)).all()} == {"incluido"}
            assert not s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.reteste == True)).all()   # noqa: E712
            aftosa = s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.numero_matriz == "3")
                            .where(CronogramaSanitarioAnimal.cronograma_id != ag)).first()
            assert aftosa.status == "sugerido"     # voltou como estava
        assert c.get("/sanidade/cronogramas/reagentes").json()["itens"] == []
        item = c.get("/sanidade/cronogramas/concluidos").json()["itens"][0]
        assert item["estado"] == "estornada" and item["rotulo_estado"] == "Estornada"

    def test_estornar_leitura_com_motivo_preserva_a_original(self, tb):
        c, engine = tb["c"], tb["engine"]
        _pronto_para_ler(tb)
        ap = _ler(tb, {n: "negativo" for n in "1234"}, laudo="L-1").json()["aplicacao"]
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/estornar", json={"motivo": "Errei o animal"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            orig = s.get(CronogramaSanitarioAplicacao, ap["id"])
            assert orig.estado == "estornada" and orig.motivo_estorno == "Errei o animal" and orig.laudo == "L-1"
            assert s.exec(select(ExameResultado)).all() == []
        # e da para ler de novo
        assert _ler(tb, {n: "negativo" for n in "1234"}).status_code == 200


# ─────────────────────────────── reagente ───────────────────────────────
class TestReagente:
    def _leitura_com_reagente(self, tb):
        _pronto_para_ler(tb)
        return _ler(tb, {"1": "negativo", "2": "negativo", "3": "reagente", "4": "negativo"}, laudo="L-77").json()["aplicacao"]

    def test_banner_persistente_lista_o_reagente_com_a_notificacao_pendente(self, tb):
        c = tb["c"]
        ap = self._leitura_com_reagente(tb)
        d = c.get("/sanidade/cronogramas/reagentes").json()
        assert d["total"] == 1 and d["pendentes_notificacao"] == 1
        it = d["itens"][0]
        assert it["numero_matriz"] == "3" and it["aplicacao_id"] == ap["id"] and it["protocolo_nome"] == "Exame de Tuberculose (TB)"
        assert it["laudo"] == "L-77" and it["espessura_mm"] == 3.0 and it["notificado_em"] is None and it["pendente_notificacao"] is True
        assert it["data"] == HOJE.isoformat()

    def test_registrar_notificacao_grava_quem_e_quando_e_o_banner_continua(self, tb):
        c, engine = tb["c"], tb["engine"]
        ap = self._leitura_com_reagente(tb)
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/notificar",
                   json={"animais": ["3"], "referencia": "IMA · protocolo 2026/8891"})
        assert r.status_code == 200, r.text
        d = c.get("/sanidade/cronogramas/reagentes").json()
        it = d["itens"][0]
        assert d["total"] == 1 and d["pendentes_notificacao"] == 0     # o banner NAO some depois de notificar
        assert it["notificado_por"] == "Gestor Teste" and it["notificado_em"] and it["notificacao_ref"] == "IMA · protocolo 2026/8891"
        assert it["pendente_notificacao"] is False
        with Session(engine) as s:
            logs = list(s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == tb["ag"])).all())
            reg = [l for l in logs if "notificação" in l.acao.lower()]
            assert len(reg) == 1 and reg[0].usuario_id == 1 and "3" in (reg[0].detalhe or "")
        # nao notifica duas vezes o mesmo animal
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/notificar", json={"animais": ["3"]})
        assert r.status_code == 400 and "já" in r.json()["detail"].lower()

    def test_so_notifica_animal_reagente_da_propria_fazenda(self, tb):
        c = tb["c"]
        ap = self._leitura_com_reagente(tb)
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/notificar", json={"animais": ["1"]})
        assert r.status_code == 400 and "reagente" in r.json()["detail"].lower()
        _USUARIO["fazenda"] = 2
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/notificar", json={}).status_code == 404
        assert c.get("/sanidade/cronogramas/reagentes").json()["total"] == 0

    def test_notificar_sem_lista_notifica_todos_os_reagentes_da_aplicacao(self, tb):
        c = tb["c"]
        _pronto_para_ler(tb)
        ap = _ler(tb, {"1": "reagente", "2": "reagente", "3": "negativo", "4": "negativo"}).json()["aplicacao"]
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/notificar", json={}).status_code == 200
        assert c.get("/sanidade/cronogramas/reagentes").json()["pendentes_notificacao"] == 0

    def test_reagente_sai_de_outros_agendamentos_e_da_lista_de_espera(self, tb):
        c, engine = tb["c"], tb["engine"]
        with Session(engine) as s:
            _estoque(s, "Aftosa", 50, numero_lote="AF-1")
            cal2 = _regra(s, "Aftosa", produto="Aftosa", categoria="vacina")
            _animal(s, "7")
            _espera(s, cal2, ["3", "7"])
        aftosa = _agendar(c, cal2, ["3", "7"], vet=tb["vet"], data=HOJE + timedelta(days=30))
        _pronto_para_ler(tb)
        assert _ler(tb, {"1": "negativo", "2": "negativo", "3": "reagente", "4": "negativo"}).status_code == 200
        with Session(engine) as s:
            linhas = {l.numero_matriz: l for l in s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == aftosa["id"])).all()}
            assert linhas["3"].status == "excluido" and "reagente" in (linhas["3"].motivo or "").lower()
            assert linhas["7"].status == "incluido"
            log = list(s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == aftosa["id"])).all())
            assert any("reagente" in (l.acao + (l.detalhe or "") + (l.motivo or "")).lower() for l in log)
        ctx = c.get(f"/sanidade/cronogramas/{aftosa['id']}/aplicar-contexto").json()
        assert [a["numero_matriz"] for a in ctx["animais"]] == ["7"]

    def test_reagente_nao_entra_em_novo_agendamento_nem_e_sugerido_de_novo(self, tb):
        c, engine = tb["c"], tb["engine"]
        with Session(engine) as s:
            cal2 = _regra(s, "Raiva", produto=None, categoria="vacina", dose=None, unidade=None)
            _espera(s, cal2, ["1"])
        _pronto_para_ler(tb)
        assert _ler(tb, {"1": "negativo", "2": "negativo", "3": "reagente", "4": "negativo"}).status_code == 200
        r = c.post("/sanidade/cronogramas/agendamentos", json={
            "calendario_sanitario_id": cal2, "animais_janela": [], "data_evento": HOJE.isoformat(), "hora": "09:00",
            "animais_fora": [{"numero_matriz": "3", "motivo": "Aproveitar a visita"}]})
        assert r.status_code == 400 and "reagente" in r.json()["detail"].lower()
        from fazenda.rules.cronograma_sanitario import sugerir_animais_em_lote
        with Session(engine) as s:
            cal = s.get(CalendarioSanitario, cal2)
            sugerir_animais_em_lote(s, cal, ["3", "2"], HOJE)
            numeros = {l.numero_matriz for l in s.exec(select(CronogramaSanitarioAnimal).join(
                CronogramaSanitario, CronogramaSanitario.id == CronogramaSanitarioAnimal.cronograma_id)
                .where(CronogramaSanitario.calendario_sanitario_id == cal2)).all()}
            assert "3" not in numeros and "2" in numeros

    def test_aplicar_vacina_recusa_animal_reagente(self, tb):
        c, engine = tb["c"], tb["engine"]
        with Session(engine) as s:
            est2, lote2 = _estoque(s, "Clostridial", numero_lote="CL-1")
            cal2 = _regra(s, "Clostridioses", produto="Clostridial", categoria="vacina", via="Subcutânea")
            _espera(s, cal2, ["1", "3"])
        ag2 = _agendar(c, cal2, ["1", "3"])
        _pronto_para_ler(tb)
        assert _ler(tb, {"1": "negativo", "2": "negativo", "3": "reagente", "4": "negativo"}).status_code == 200
        # o reagente ja saiu do agendamento; se alguem reinserir na marra, aplicar recusa
        with Session(engine) as s:
            linha = s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.numero_matriz == "3")
                           .where(CronogramaSanitarioAnimal.cronograma_id == ag2["id"])).first()
            linha.status = "incluido"
            s.add(linha)
            s.commit()
        r = _aplicar(c, ag2["id"], aplicador_pessoa_id=tb["peao"], animais_aplicados=["1", "3"], estoque_id=est2)
        assert r.status_code == 400 and "reagente" in r.json()["detail"].lower()

    def test_comprovante_bloqueado_so_para_o_reagente(self, tb):
        c = tb["c"]
        ap = self._leitura_com_reagente(tb)
        r = c.get(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/comprovante")
        assert r.status_code == 200, r.text
        comp = r.json()
        assert comp["tipo"] == "exame" and comp["laudo"] == "L-77" and comp["tipo_teste"] == "Cervical simples"
        assert comp["fazenda_nome"] == "Fazenda Estreito" and comp["aplicador_nome"] == "Dr. Paulo" and comp["aplicador_crmv"] == "CRMV-MG 12345"
        assert comp["inoculacao"]["data"] == (HOJE - timedelta(days=3)).isoformat() and comp["leitura"]["data"] == HOJE.isoformat()
        assert [a["numero_matriz"] for a in comp["animais"]] == ["1", "2", "4"]           # negativos emitem
        assert all(a["resultado"] == "negativo" and a["espessura_mm"] == 3.0 for a in comp["animais"])
        assert [b["numero_matriz"] for b in comp["bloqueados"]] == ["3"] and "reagente" in comp["bloqueados"][0]["motivo"].lower()
        assert comp["bloqueado_total"] is False

    def test_comprovante_bloqueado_por_inteiro_quando_todos_sao_reagentes(self, tb):
        c = tb["c"]
        _pronto_para_ler(tb)
        ap = _ler(tb, {n: "reagente" for n in "1234"}).json()["aplicacao"]
        r = c.get(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/comprovante")
        assert r.status_code == 409 and "reagente" in r.json()["detail"].lower()

    def test_comprovante_de_estornada_e_recusado_e_de_outra_fazenda_e_404(self, tb):
        c = tb["c"]
        _pronto_para_ler(tb)
        ap = _ler(tb, {n: "negativo" for n in "1234"}).json()["aplicacao"]
        _USUARIO["fazenda"] = 2
        assert c.get(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/comprovante").status_code == 404
        _USUARIO.pop("fazenda")
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/estornar", json={"motivo": "Errei o animal"}).status_code == 200
        r = c.get(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/comprovante")
        assert r.status_code == 409 and "estornad" in r.json()["detail"].lower()

    def test_comprovante_de_vacina_tambem_existe(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, lote = _estoque(s, "Raiva")
            _animal(s, "1")
            _animal(s, "2")
            cal = _regra(s, "Raiva", produto="Raiva", categoria="vacina", via="Subcutânea")
            _espera(s, cal, ["1", "2"])
        ag = _agendar(c, cal, ["1", "2"], vet=vet)
        ap = _aplicar(c, ag["id"], aplicador_pessoa_id=vet, animais_aplicados=["1", "2"], estoque_id=est).json()["aplicacao"]
        comp = c.get(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/comprovante").json()
        assert comp["tipo"] == "vacina" and [a["numero_matriz"] for a in comp["animais"]] == ["1", "2"] and comp["bloqueados"] == []
        assert comp["lote_texto"] == "TB-1" and comp["produto"] == "Raiva"


# ─────────────────────────────── reteste ───────────────────────────────
class TestReteste:
    def _inconclusivo(self, tb):
        _pronto_para_ler(tb)
        return _ler(tb, {"1": "negativo", "2": "negativo", "3": "negativo", "4": "inconclusivo"}).json()["aplicacao"]

    def test_reteste_so_aparece_na_lista_de_espera_a_partir_da_data_devida(self, tb):
        c, engine = tb["c"], tb["engine"]
        self._inconclusivo(tb)
        espera = c.get("/sanidade/cronogramas/lista-espera").json()
        assert espera["total"] == 0          # ainda faltam 60 dias
        with Session(engine) as s:
            linha = s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.reteste == True)).one()   # noqa: E712
            assert linha.numero_matriz == "4" and linha.status == "sugerido"
            assert linha.data_devida == HOJE + timedelta(days=60)
            assert "Reteste" in linha.motivo_entrada and "inconclusivo" in linha.motivo_entrada.lower()
            linha.data_devida = HOJE - timedelta(days=4)
            s.add(linha)
            s.commit()
        espera = c.get("/sanidade/cronogramas/lista-espera").json()
        item = espera["grupos"][0]["animais"][0]
        assert item["numero_matriz"] == "4" and item["reteste"] is True and item["situacao"] == "atrasada"
        assert item["dias_atraso"] == 4 and item["situacao_rotulo"] == "Reteste atrasado"
        assert "inconclusivo" in item["motivo_entrada"].lower()

    def test_reteste_no_dia_esta_na_janela_sem_atraso(self, tb):
        c, engine = tb["c"], tb["engine"]
        self._inconclusivo(tb)
        with Session(engine) as s:
            linha = s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.reteste == True)).one()   # noqa: E712
            linha.data_devida = HOJE
            s.add(linha)
            s.commit()
        item = c.get("/sanidade/cronogramas/lista-espera").json()["grupos"][0]["animais"][0]
        assert item["situacao"] == "na_janela" and item["situacao_rotulo"] == "Reteste" and item["dias_atraso"] == 0

    def test_reteste_pode_virar_agendamento_e_ser_aplicado(self, tb):
        c, engine = tb["c"], tb["engine"]
        self._inconclusivo(tb)
        with Session(engine) as s:
            linha = s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.reteste == True)).one()   # noqa: E712
            linha.data_devida = HOJE
            s.add(linha)
            s.commit()
        ag2 = _agendar(c, tb["cal"], ["4"], vet=tb["vet"])
        r = _aplicar(c, ag2["id"], aplicador_pessoa_id=tb["vet"], animais_aplicados=["4"], estoque_id=tb["est"], lote_id=tb["lote"])
        assert r.status_code == 200 and r.json()["aplicacao"]["fase"] == "inoculacao"

    def test_estornar_a_leitura_tira_o_reteste_da_lista(self, tb):
        c, engine = tb["c"], tb["engine"]
        ap = self._inconclusivo(tb)
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap['id']}/estornar", json={"motivo": "Errei o animal"}).status_code == 200
        with Session(engine) as s:
            assert not s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.reteste == True)).all()   # noqa: E712

    def test_pendencias_de_reteste_no_endpoint_de_exames(self, tb):
        c, engine = tb["c"], tb["engine"]
        self._inconclusivo(tb)
        d = c.get("/sanidade/cronogramas/retestes").json()
        assert d["total"] == 1 and d["itens"][0]["numero_matriz"] == "4" and d["itens"][0]["situacao"] == "aguardando"
        assert d["itens"][0]["reteste_em"] == (HOJE + timedelta(days=60)).isoformat()
        with Session(engine) as s:
            a = s.exec(select(CronogramaSanitarioAplicacaoAnimal).where(CronogramaSanitarioAplicacaoAnimal.exame_resultado == "inconclusivo")).one()
            a.reteste_em = HOJE - timedelta(days=3)
            s.add(a)
            s.commit()
        it = c.get("/sanidade/cronogramas/retestes").json()["itens"][0]
        assert it["situacao"] == "atrasado" and it["rotulo"] == "Reteste atrasado" and it["dias_atraso"] == 3


# ─────────────────────────────── coleta (brucelose) ───────────────────────────────
class TestColeta:
    @pytest.fixture
    def bru(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, peao = _pessoas(s)
            for n in ("1", "2"):
                _animal(s, n, meses=30)
            cal = _regra(s, "Exame de brucelose (sorologia)", produto=None, via="Coleta de sangue")
            _espera(s, cal, ["1", "2"])
        ag = _agendar(c, cal, ["1", "2"], vet=vet)
        return {"c": c, "engine": engine, "ag": ag["id"], "vet": vet, "peao": peao}

    def test_exame_sem_leitura_e_uma_etapa_so_com_laudo(self, bru):
        c = bru["c"]
        ctx = c.get(f"/sanidade/cronogramas/{bru['ag']}/aplicar-contexto").json()
        assert ctx["exame"]["fase"] == "coleta" and ctx["exame"]["tipo_exame"] == "brucelose" and ctx["exame"]["leitura_horas"] == 0
        r = _aplicar(c, bru["ag"], aplicador_pessoa_id=bru["vet"], animais_aplicados=["1", "2"], laudo="LAB-9912")
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["fase"] == "coleta" and ap["laudo"] == "LAB-9912" and r.json()["agendamento"]["status"] == "concluido"
        assert {a["exame_resultado"] for a in ap["animais"]} == {"coletado"}
        item = c.get("/sanidade/cronogramas/concluidos").json()["itens"][0]
        assert item["rotulo_estado"] == "Exame realizado" and item["exame"]["fase"] == "coleta" and item["exame"]["laudo"] == "LAB-9912"

    def test_brucelose_so_veterinario(self, bru):
        r = _aplicar(bru["c"], bru["ag"], aplicador_pessoa_id=bru["peao"], animais_aplicados=["1", "2"])
        assert r.status_code == 400 and "veterinário" in r.json()["detail"].lower()

    def test_resultado_conhecido_na_coleta_reagente_dispara_o_banner(self, bru):
        c = bru["c"]
        r = _aplicar(bru["c"], bru["ag"], aplicador_pessoa_id=bru["vet"], animais_aplicados=["1", "2"],
                     resultados={"1": "negativo", "2": "reagente"}, laudo="LAB-1")
        assert r.status_code == 200, r.text
        d = c.get("/sanidade/cronogramas/reagentes").json()
        assert d["total"] == 1 and d["itens"][0]["numero_matriz"] == "2"
        with Session(bru["engine"]) as s:
            assert {e.numero_matriz: e.resultado for e in s.exec(select(ExameResultado)).all()} == {"1": "negativo", "2": "positivo"}


# ─────────────────────────────── canal, idempotencia, agenda ───────────────────────────────
class TestCanalEAgenda:
    def test_canal_curral_do_app_do_peao_e_aceito_e_gravado(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, peao = _pessoas(s)
            est, lote = _estoque(s, "Raiva")
            _animal(s, "1")
            cal = _regra(s, "Raiva", produto="Raiva", categoria="vacina", via="Subcutânea")
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"], vet=vet)
        r = _aplicar(c, ag["id"], canal="Curral", aplicador_pessoa_id=peao, animais_aplicados=["1"], estoque_id=est)
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"]["canal"] == "Curral"
        item = c.get("/sanidade/cronogramas/concluidos").json()["itens"][0]
        assert item["canal"] == "Curral"
        with Session(engine) as s:
            assert [l.canal for l in s.exec(select(CronogramaSanitarioLog)).all() if l.acao == "Aplicou"] == ["Curral"]
        r = _aplicar(c, ag["id"], canal="Celular", aplicador_pessoa_id=peao, animais_aplicados=["1"], estoque_id=est)
        assert r.status_code == 400 and "canal" in r.json()["detail"].lower()

    def test_exame_idempotente_pela_chave(self, tb):
        r1 = _inocular(tb, chave_idempotencia="k-1")
        r2 = _inocular(tb, chave_idempotencia="k-1")
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.json()["idempotente"] is True and r1.json()["aplicacao"]["id"] == r2.json()["aplicacao"]["id"]
        assert _saldo(tb["engine"], tb["est"]) == 96

    def test_agenda_mostra_o_dia_da_leitura_com_a_fase(self, tb):
        c = tb["c"]
        _pronto_para_ler(tb)
        dia = c.get("/agenda", params={"data": HOJE.isoformat()}).json()
        ev = next(e for e in dia["eventos"] if e["id"] == f"cronograma_sanitario_aplicar_{tb['ag']}")
        assert ev["fase"] == "leitura" and ev["descricao"].startswith("Registrar leitura")
        assert ev["exame_leitura_prevista_em"].startswith(HOJE.isoformat())

    def test_acompanhamento_marca_a_fase_do_exame(self, tb):
        c = tb["c"]
        ag = c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"][0]
        assert ag["fase"] == "inoculacao" and ag["tipo"] == "exame"
        _pronto_para_ler(tb)
        ag = c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"][0]
        assert ag["fase"] == "leitura" and ag["leitura_prevista_em"].startswith(HOJE.isoformat())


# ─────────────────────────────── B19 ───────────────────────────────
class TestB19:
    def _b19(self, ctx, animais: list[tuple[str, str, int]]):
        c, engine = ctx
        with Session(engine) as s:
            vet, peao = _pessoas(s)
            est, lote = _estoque(s, "B19")
            for numero, sexo, meses in animais:
                _animal(s, numero, sexo=sexo, meses=meses)
            cal = _regra(s, "Brucelose B19", produto="B19", categoria="vacina", via="Subcutânea")
            _espera(s, cal, [a[0] for a in animais])
        return {"c": c, "engine": engine, "cal": cal, "vet": vet, "est": est}

    def test_macho_nao_entra_no_agendamento_da_b19(self, ctx):
        t = self._b19(ctx, [("1", "F", 5)])
        with Session(t["engine"]) as s:
            _animal(s, "9", sexo="M", meses=5)
            s.commit()
        r = t["c"].post("/sanidade/cronogramas/agendamentos", json={
            "calendario_sanitario_id": t["cal"], "animais_janela": ["1"], "data_evento": HOJE.isoformat(),
            "animais_fora": [{"numero_matriz": "9", "motivo": "Aproveitar a visita do veterinário"}]})
        assert r.status_code == 400 and "b19" in r.json()["detail"].lower() and "fêmea" in r.json()["detail"].lower()

    def test_aplicar_b19_recusa_idade_fora_de_3_a_8_meses(self, ctx):
        t = self._b19(ctx, [("1", "F", 5), ("2", "F", 14), ("3", "F", 2)])
        ag = _agendar(t["c"], t["cal"], ["1", "2", "3"], vet=t["vet"])
        r = _aplicar(t["c"], ag["id"], aplicador_pessoa_id=t["vet"], animais_aplicados=["1", "2", "3"], estoque_id=t["est"])
        assert r.status_code == 400 and "3 a 8 meses" in r.json()["detail"]
        assert "2" in r.json()["detail"] and "3" in r.json()["detail"]
        r = _aplicar(t["c"], ag["id"], aplicador_pessoa_id=t["vet"], animais_aplicados=["1"], estoque_id=t["est"],
                     nao_aplicados=[{"numero_matriz": "2", "motivo": "Outro", "destino": "naoSeAplica"},
                                    {"numero_matriz": "3", "motivo": "Outro", "destino": "naoSeAplica"}])
        assert r.status_code == 200, r.text

    def test_contexto_do_b19_avisa_a_restricao_por_animal(self, ctx):
        t = self._b19(ctx, [("1", "F", 5), ("2", "F", 14)])
        ag = _agendar(t["c"], t["cal"], ["1", "2"], vet=t["vet"])
        animais = {a["numero_matriz"]: a for a in t["c"].get(f"/sanidade/cronogramas/{ag['id']}/aplicar-contexto").json()["animais"]}
        assert animais["1"]["restricao"] is None and "3 a 8 meses" in animais["2"]["restricao"]
