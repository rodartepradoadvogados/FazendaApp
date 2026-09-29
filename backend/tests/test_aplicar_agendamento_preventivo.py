"""
Fatia 8 do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, secao 7): UM endpoint para aplicar um
agendamento preventivo (Protocolos > Acompanhamento e Agenda usam o mesmo),
com aplicador obrigatorio (B19/TB so veterinario), frasco/lote/validade, dose
(por peso individual quando houver), baixa de estoque ou 'desconsiderar estoque'
com motivo, ciencia dos itens pendentes, carencia, log com quem/quando/canal,
Desfazer <= 10 s (sem motivo) e depois so Estornar (admin, com motivo) —
a original nunca some: vira 'estornada'. Idempotente.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, CalendarioSanitario, ChecklistItem, ChecklistTemplateItem, ContratoFazenda, ContratoFazendaModulo,
    CronogramaSanitario, CronogramaSanitarioAnimal, CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacaoAnimal,
    CronogramaSanitarioLog, Estoque, EventoSanitario, Fazenda, LoteEstoque, MedicamentoComercial, MovimentoEstoque,
    ParametroFazenda, Pessoa, PesagemCorporal, PrincipioAtivo, Sanidade,
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
        s.add(Fazenda(id=1, nome="Fazenda 1"))
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


def _estoque(
    s: Session, nome: str = "B19", *, lotes: list[tuple[str, float, date | None]] | None = None,
    unidade: str = "dose", carencia_carne: int | None = None, carencia_leite: int | None = None,
    por_peso: bool = False, valor_unitario: float | None = 6.4, fazenda_id: int = 1,
) -> tuple[int, list[int]]:
    """Item de estoque com lotes (numero, saldo, validade). Devolve (estoque_id, [lote_ids])."""
    pa = PrincipioAtivo(nome=f"PA {nome}", fazenda_id=fazenda_id)
    s.add(pa)
    s.commit()
    s.refresh(pa)
    mc = MedicamentoComercial(
        principio_ativo_id=pa.id, nome_comercial=nome, fazenda_id=fazenda_id,
        carencia_carne_dias=carencia_carne, carencia_leite_dias=carencia_leite,
        dose_base="por_kg_pv" if por_peso else "por_animal", dose_padrao=1.0,
        dose_referencia_kg=50.0 if por_peso else None, unidade_dose=unidade,
    )
    s.add(mc)
    s.commit()
    s.refresh(mc)
    lotes = lotes if lotes is not None else [("L1", 100.0, HOJE + timedelta(days=200))]
    item = Estoque(
        nome=nome, unidade=unidade, quantidade=sum(l[1] for l in lotes), valor_unitario=valor_unitario,
        principio_ativo_id=pa.id, medicamento_comercial_id=mc.id, fazenda_id=fazenda_id, finalidade="Medicamento",
    )
    s.add(item)
    s.commit()
    s.refresh(item)
    ids = []
    for numero, saldo, validade in lotes:
        lote = LoteEstoque(
            estoque_id=item.id, numero_lote=numero, data_compra=HOJE - timedelta(days=30), quantidade_comprada=saldo,
            quantidade_restante=saldo, validade=validade, fazenda_id=fazenda_id,
        )
        s.add(lote)
        s.commit()
        s.refresh(lote)
        ids.append(lote.id)
    return item.id, ids


def _animal(s: Session, numero: str, *, grupo: str = "Bezerreiro", fazenda_id: int = 1) -> None:
    s.add(Animal(numero=numero, nome=f"Bezerra {numero}", sexo="F", ativo=True, grupo_primario=grupo,
                 data_nasc=HOJE - timedelta(days=150), fazenda_id=fazenda_id))


def _peso(s: Session, numero: str, kg: float) -> None:
    s.add(PesagemCorporal(numero_matriz=numero, data_pesagem=HOJE - timedelta(days=5), peso_kg=kg, fazenda_id=1))


def _regra(
    s: Session, nome: str = "Brucelose B19", *, produto: str = "B19", categoria: str = "vacina", fazenda_id: int = 1,
    dose: float = 1.0, unidade: str = "dose",
) -> int:
    ev = EventoSanitario(
        nome=nome, tipo_agendamento="epoca", categoria_preventiva=categoria, produto_padrao=produto, dose_padrao=dose,
        unidade_padrao=unidade, via_padrao="Subcutânea", fazenda_id=fazenda_id,
    )
    s.add(ev)
    s.commit()
    s.refresh(ev)
    cal = CalendarioSanitario(
        evento_sanitario_id=ev.id, categoria_alvo="Bezerra", produto=produto, frequencia_valor=6,
        frequencia_unidade="meses", data_evento=HOJE - timedelta(days=2), usa_cronograma=True, fazenda_id=fazenda_id,
    )
    s.add(cal)
    s.commit()
    s.refresh(cal)
    return cal.id


def _template(s: Session, chaves: tuple[str, ...] = ("estoque", "vet", "horario")) -> None:
    nomes = {"estoque": "Estoque suficiente?", "vet": "Confirmação com o veterinário", "horario": "Horário da aplicação",
             "lotes": "Lotes de manejo atuais", "financeiro": "Lançamento financeiro"}
    for i, k in enumerate(chaves, 1):
        s.add(ChecklistTemplateItem(tipo="vacina", chave=k, nome=nomes[k], ordem=i, fazenda_id=None))
    s.commit()


def _espera(s: Session, cal_id: int, numeros: list[str], *, fazenda_id: int = 1) -> int:
    cron = CronogramaSanitario(calendario_sanitario_id=cal_id, data_evento=HOJE - timedelta(days=2), status="aberto",
                               fazenda_id=fazenda_id)
    s.add(cron)
    s.commit()
    s.refresh(cron)
    for n in numeros:
        s.add(CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=n, status="sugerido",
                                        data_sugestao=HOJE, fazenda_id=fazenda_id))
    s.commit()
    return cron.id


def _agendar(c, cal_id: int, janela: list[str], *, fora: list[dict] | None = None, data: date | None = None,
             vet: int | None = None, **extra) -> dict:
    corpo = {
        "calendario_sanitario_id": cal_id, "animais_janela": janela, "animais_fora": fora or [],
        "data_evento": (data or HOJE).isoformat(), "hora": "15:30",
    }
    if vet:
        corpo.update(modo_execucao="veterinario", veterinario_pessoa_id=vet)
    corpo.update(extra)
    r = c.post("/sanidade/cronogramas/agendamentos", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _aplicar(c, ag_id: int, **kw):
    corpo = {"canal": "Protocolos", "animais_aplicados": kw.pop("animais_aplicados", None)}
    corpo.update(kw)
    return c.post(f"/sanidade/cronogramas/{ag_id}/aplicar", json=corpo)


@pytest.fixture
def cenario(ctx):
    """B19 com 3 animais no agendamento de hoje, checklist limpo (sem itens), 1 lote com 100 doses."""
    c, engine = ctx
    with Session(engine) as s:
        vet, peao = _pessoas(s)
        est, lotes = _estoque(s, carencia_carne=28)
        for n in ("1", "2", "3", "9"):
            _animal(s, n)
        cal = _regra(s)
        _espera(s, cal, ["1", "2", "3"])
    ag = _agendar(c, cal, ["1", "2", "3"], fora=[{"numero_matriz": "9", "motivo": "Aproveitar a visita do veterinário"}], vet=vet)
    return {"c": c, "engine": engine, "ag": ag["id"], "cal": cal, "vet": vet, "peao": peao, "est": est, "lotes": lotes}


def _materializar_template(cenario, chaves: tuple[str, ...]) -> None:
    """Template do checklist criado DEPOIS do agendamento: materializa na mao."""
    from fazenda.rules.checklist_sanitario import materializar_checklist
    with Session(cenario["engine"]) as s:
        _template(s, chaves)
        cron = s.get(CronogramaSanitario, cenario["ag"])
        materializar_checklist(s, cron, s.get(EventoSanitario, s.get(CalendarioSanitario, cron.calendario_sanitario_id).evento_sanitario_id))


def _saldo(engine, est: int) -> float:
    with Session(engine) as s:
        return s.get(Estoque, est).quantidade


def _movs(engine, est: int) -> list[MovimentoEstoque]:
    with Session(engine) as s:
        return list(s.exec(select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == est)).all())


def _status(engine, ag: int) -> dict[str, str]:
    with Session(engine) as s:
        return {l.numero_matriz: l.status for l in s.exec(
            select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == ag)).all()}


# ─────────────────────────────── aplicar ───────────────────────────────
class TestAplicarTotal:
    def test_aplica_todos_baixa_estoque_grava_sanidade_carencia_e_log(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, hora="15:40",
                     estoque_id=est, lote_id=cenario["lotes"][0], canal="Agenda")
        assert r.status_code == 200, r.text
        dados = r.json()
        ap = dados["aplicacao"]
        assert ap["estado"] == "aplicada" and ap["canal"] == "Agenda"
        assert ap["aplicador_nome"] == "Dr. Paulo" and ap["aplicador_crmv"] == "CRMV-MG 12345"
        assert ap["dose_total"] == 4 and ap["lote_texto"] == "L1" and ap["produto"] == "B19"
        assert ap["carencia_carne_ate"] == (HOJE + timedelta(days=28)).isoformat()
        assert ap["carencia_leite_ate"] is None
        assert ap["custo"] == pytest.approx(25.6)
        assert dados["agendamento"]["status"] == "concluido"
        assert dados["desfazer_segundos"] == 10
        assert _saldo(engine, est) == 96
        baixas = [m for m in _movs(engine, est) if m.movimento == "Aplicação"]
        assert len(baixas) == 4 and all(m.quantidade == 1 for m in baixas)
        with Session(engine) as s:
            lote = s.get(LoteEstoque, cenario["lotes"][0])
            assert lote.quantidade_restante == 96
            sans = s.exec(select(Sanidade).order_by(Sanidade.numero_matriz)).all()
            assert [x.numero_matriz for x in sans] == ["1", "2", "3", "9"]
            assert all(x.natureza == "preventivo" and x.produto == "B19" and x.dose == 1 and x.unidade == "dose"
                       and x.via == "Subcutânea" and x.responsavel == "Dr. Paulo" and x.lote == "L1"
                       and x.data_aplicacao == HOJE for x in sans)
            assert s.get(CronogramaSanitario, ag).concluido_em is not None
            log = s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag)).all()
            aplic = [l for l in log if l.acao == "Aplicou"]
            assert len(aplic) == 1 and aplic[0].canal == "Agenda" and aplic[0].usuario_id == 1 and aplic[0].criado_em
        assert set(_status(engine, ag).values()) == {"aplicado"}

    def test_animais_por_origem_ficam_no_registro_e_fora_da_janela_vira_excecao(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert any("fora da janela" in e.lower() for e in ap["excecoes"])
        por_animal = {a["numero_matriz"]: a for a in ap["animais"]}
        assert por_animal["9"]["origem"] == "fora_janela" and por_animal["9"]["motivo_origem"] == "Aproveitar a visita do veterinário"
        assert por_animal["1"]["origem"] == "janela" and por_animal["1"]["resultado"] == "aplicado"

    def test_canal_so_protocolos_ou_agenda(self, cenario):
        c, ag, vet = cenario["c"], cenario["ag"], cenario["vet"]
        r = _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=vet, canal="Celular", estoque_id=cenario["est"])
        assert r.status_code == 400 and "canal" in r.json()["detail"].lower()

    def test_data_futura_e_recusada_e_passada_marca_retroativo(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est,
                     data_aplicacao=(HOJE + timedelta(days=1)).isoformat())
        assert r.status_code == 400 and "futura" in r.json()["detail"].lower()
        assert _saldo(engine, est) == 100
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est,
                     data_aplicacao=(HOJE - timedelta(days=1)).isoformat())
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["retroativo"] is True and any("retroativ" in e.lower() for e in ap["excecoes"])
        assert ap["data_aplicacao"] == (HOJE - timedelta(days=1)).isoformat()

    def test_agendamento_que_nao_esta_agendado_e_recusado(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, _ = _estoque(s)
            _animal(s, "1")
            cal = _regra(s)
            espera = _espera(s, cal, ["1"])
        r = _aplicar(c, espera, animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est)  # lista de espera
        assert r.status_code == 400
        ag = _agendar(c, cal, ["1"], rascunho=True)
        r = _aplicar(c, ag["id"], animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 400 and "agendado" in r.json()["detail"].lower()


class TestAplicador:
    def test_aplicador_obrigatorio(self, cenario):
        c, ag, est = cenario["c"], cenario["ag"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1"], estoque_id=est)
        assert r.status_code in (400, 422)
        r = _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=999999, estoque_id=est)
        assert r.status_code == 400 and "aplicador" in r.json()["detail"].lower()

    def test_b19_so_veterinario(self, cenario):
        c, engine, ag, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=cenario["peao"], estoque_id=est)
        assert r.status_code == 400 and "veterinário" in r.json()["detail"].lower()
        assert _saldo(engine, est) == 100
        assert _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=cenario["vet"], estoque_id=est).status_code == 200

    def test_tuberculose_tambem_exige_veterinario_mas_vermifugo_nao(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, peao = _pessoas(s)
            est_tb, _ = _estoque(s, "Tuberculina PPD")
            est_v, _ = _estoque(s, "Ivermectina 1%", unidade="ml")
            _animal(s, "1")
            _animal(s, "2")
            tb = _regra(s, "Teste de tuberculose", produto="Tuberculina PPD")
            verm = _regra(s, "Vermifugação", produto="Ivermectina 1%", categoria="tratamento", unidade="ml")
            _espera(s, tb, ["1"])
            _espera(s, verm, ["2"])
        ag_tb = _agendar(c, tb, ["1"])
        ag_v = _agendar(c, verm, ["2"])
        assert _aplicar(c, ag_tb["id"], animais_aplicados=["1"], aplicador_pessoa_id=peao, estoque_id=est_tb).status_code == 400
        assert _aplicar(c, ag_v["id"], animais_aplicados=["2"], aplicador_pessoa_id=peao, estoque_id=est_v).status_code == 200


class TestAplicacaoParcial:
    def test_nao_aplicado_exige_motivo_e_nada_e_gravado(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est,
                     nao_aplicados=[{"numero_matriz": "3", "destino": "espera"}])  # 9 tambem ficou de fora, sem entrada
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()
        assert _saldo(engine, est) == 100
        with Session(engine) as s:
            assert s.exec(select(Sanidade)).all() == []
            assert s.exec(select(CronogramaSanitarioAplicacao)).all() == []
            assert s.get(CronogramaSanitario, ag).status == "agendado"

    def test_todo_incluido_fora_dos_aplicados_precisa_de_destino(self, cenario):
        c, ag, vet, est = cenario["c"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est,
                     nao_aplicados=[{"numero_matriz": "3", "motivo": "Doente", "destino": "espera"}])
        assert r.status_code == 400 and "9" in r.json()["detail"]

    def test_parcial_devolve_a_lista_de_espera_ou_desconsidera(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est, nao_aplicados=[
            {"numero_matriz": "3", "motivo": "Doente", "destino": "espera"},
            {"numero_matriz": "9", "motivo": "Vendido", "destino": "naoSeAplica"},
        ])
        assert r.status_code == 200, r.text
        assert _saldo(engine, est) == 98
        st = _status(engine, ag)
        assert st == {"1": "aplicado", "2": "aplicado", "9": "excluido"}   # o 3 saiu deste agendamento, de volta a lista de espera
        with Session(engine) as s:
            linhas = s.exec(select(CronogramaSanitarioAnimal).order_by(CronogramaSanitarioAnimal.numero_matriz)).all()
            por = {(l.numero_matriz): l for l in linhas}
            assert por["1"].status == "aplicado" and por["1"].data_aplicacao == HOJE
            assert por["3"].status == "sugerido" and por["3"].cronograma_id != ag   # de volta a lista de espera
            assert por["9"].status == "excluido" and por["9"].motivo == "Vendido"
            assert s.get(CronogramaSanitario, ag).status == "concluido"
            ap = s.exec(select(CronogramaSanitarioAplicacaoAnimal).where(
                CronogramaSanitarioAplicacaoAnimal.resultado == "nao_aplicado")).all()
            assert {(a.numero_matriz, a.motivo_nao, a.destino_nao) for a in ap} == {("3", "Doente", "espera"), ("9", "Vendido", "naoSeAplica")}
        espera = c.get("/sanidade/cronogramas/lista-espera").json()
        assert [x["numero_matriz"] for g in espera["grupos"] for x in g["animais"]] == ["3"]

    def test_animal_que_nao_esta_no_agendamento_e_recusado(self, cenario):
        c, ag, vet, est = cenario["c"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "77"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 400 and "77" in r.json()["detail"]

    def test_sem_animal_aplicado_e_recusado(self, cenario):
        c, ag, vet, est = cenario["c"], cenario["ag"], cenario["vet"], cenario["est"]
        assert _aplicar(c, ag, animais_aplicados=[], aplicador_pessoa_id=vet, estoque_id=est).status_code == 400


class TestFrascoEstoque:
    def test_frasco_vencido_exige_ciencia_e_registra_excecao(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, lotes = _estoque(s, lotes=[("VELHO", 10.0, HOJE - timedelta(days=3)), ("NOVO", 50.0, HOJE + timedelta(days=90))])
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"], vet=vet)["id"]
        r = _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est, lote_id=lotes[0])
        assert r.status_code == 400 and "vencido" in r.json()["detail"].lower()
        assert _saldo(engine, est) == 60
        r = _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est, lote_id=lotes[0], ciente_vencido=True)
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["frasco_vencido_ciente"] is True and any("vencido" in e.lower() for e in ap["excecoes"])
        assert ap["lote_texto"] == "VELHO" and ap["validade"] == (HOJE - timedelta(days=3)).isoformat()

    def test_sem_lote_escolhido_usa_o_lote_valido_mais_antigo_nunca_o_vencido(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, lotes = _estoque(s, lotes=[("VELHO", 10.0, HOJE - timedelta(days=3)), ("NOVO", 50.0, HOJE + timedelta(days=90))])
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"], vet=vet)["id"]
        r = _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"]["lote_texto"] == "NOVO"
        with Session(engine) as s:
            assert s.get(LoteEstoque, lotes[1]).quantidade_restante == 49
            assert s.get(LoteEstoque, lotes[0]).quantidade_restante == 10

    def test_estoque_de_outra_fazenda_e_recusado(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est_alheio, _ = _estoque(s, "B19", fazenda_id=2)
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"], vet=vet)["id"]
        r = _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est_alheio)
        assert r.status_code == 400
        assert _saldo(engine, est_alheio) == 100

    def test_sem_frasco_nem_desconsiderar_e_recusado(self, cenario):
        c, ag, vet = cenario["c"], cenario["ag"], cenario["vet"]
        with Session(cenario["engine"]) as s:
            s.exec(select(Estoque)).first().nome = "Outro produto"   # produto do protocolo nao existe mais
            s.commit()
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet)
        assert r.status_code == 400 and "estoque" in r.json()["detail"].lower()

    def test_saldo_insuficiente_nao_bloqueia_mas_avisa(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, lotes = _estoque(s, lotes=[("L1", 1.0, HOJE + timedelta(days=90))])
            for n in ("1", "2"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1", "2"])
        ag = _agendar(c, cal, ["1", "2"], vet=vet)["id"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 200, r.text
        assert any("negativo" in a.lower() for a in r.json()["avisos"])


class TestDesconsiderarEstoque:
    def test_exige_motivo_e_nao_baixa(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        corpo = dict(animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, desconsiderar_estoque=True)
        r = _aplicar(c, ag, **corpo)
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()
        r = _aplicar(c, ag, **corpo, motivo_desconsiderar_estoque="Frasco do veterinário", lote_veterinario="VET-778",
                     validade_veterinario=(HOJE + timedelta(days=120)).isoformat())
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["estoque_desconsiderado"] is True and ap["estoque_motivo"] == "Frasco do veterinário"
        assert ap["lote_texto"] == "VET-778" and ap["validade"] == (HOJE + timedelta(days=120)).isoformat()
        assert ap["custo"] is None
        assert any("sem baixa" in e.lower() for e in ap["excecoes"])
        assert _saldo(engine, est) == 100 and _movs(engine, est) == []
        with Session(engine) as s:
            assert len(s.exec(select(Sanidade)).all()) == 4      # a aplicacao aconteceu; so o estoque nao baixou
            assert all(x.lote == "VET-778" for x in s.exec(select(Sanidade)).all())


class TestDosePorPeso:
    def _cena(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, lotes = _estoque(s, "Ivermectina 1%", unidade="ml", por_peso=True, lotes=[("IV1", 500.0, HOJE + timedelta(days=90))])
            for n in ("1", "2", "3"):
                _animal(s, n, grupo="Recria 1")
            _animal(s, "4", grupo="Recria 1")
            _peso(s, "1", 250.0)     # 250/50 = 5 mL
            _peso(s, "2", 400.0)     # 8 mL
            _peso(s, "3", 300.0)
            cal = _regra(s, "Vermifugação", produto="Ivermectina 1%", categoria="tratamento", unidade="ml")
            _espera(s, cal, ["1", "2", "3", "4"])
            s.commit()
        return c, engine, cal, vet, est

    def test_dose_individual_pelo_peso_de_cada_animal_e_estimativa_pelo_lote(self, ctx):
        c, engine, cal, vet, est = self._cena(ctx)
        ag = _agendar(c, cal, ["1", "2", "3", "4"], vet=vet)["id"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "4"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        por = {a["numero_matriz"]: a for a in ap["animais"]}
        assert por["1"]["dose"] == pytest.approx(5.0) and por["1"]["peso_kg"] == 250 and por["1"]["peso_estimado"] is False
        assert por["2"]["dose"] == pytest.approx(8.0)
        # animal 4 nao tem pesagem: estimativa = media do lote (250, 400, 300 -> 316,67 kg)
        assert por["4"]["peso_estimado"] is True and por["4"]["peso_kg"] == pytest.approx(316.67, abs=0.01)
        assert por["4"]["dose"] == pytest.approx(316.67 / 50, abs=0.01)
        assert ap["dose_total"] == pytest.approx(5 + 8 + 6 + 316.67 / 50, abs=0.01)
        assert _saldo(engine, est) == pytest.approx(500 - ap["dose_total"], abs=0.01)
        with Session(engine) as s:
            doses = {x.numero_matriz: x.dose for x in s.exec(select(Sanidade)).all()}
        assert doses["1"] == pytest.approx(5.0) and doses["2"] == pytest.approx(8.0)

    def test_peso_informado_na_hora_vale_mais_que_a_pesagem(self, ctx):
        c, engine, cal, vet, est = self._cena(ctx)
        ag = _agendar(c, cal, ["1", "2", "3", "4"], vet=vet)["id"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "4"], aplicador_pessoa_id=vet, estoque_id=est, pesos={"4": 200})
        assert r.status_code == 200, r.text
        por = {a["numero_matriz"]: a for a in r.json()["aplicacao"]["animais"]}
        assert por["4"]["peso_kg"] == 200 and por["4"]["peso_estimado"] is False and por["4"]["dose"] == pytest.approx(4.0)

    def test_sem_nenhum_peso_nem_estimativa_pede_o_peso(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, _ = _estoque(s, "Ivermectina 1%", unidade="ml", por_peso=True)
            _animal(s, "1", grupo="Sozinha")
            cal = _regra(s, "Vermifugação", produto="Ivermectina 1%", categoria="tratamento", unidade="ml")
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"], vet=vet)["id"]
        r = _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 400 and "peso" in r.json()["detail"].lower() and "1" in r.json()["detail"]
        assert _saldo(engine, est) == 100


class TestCienciaDosPendentes:
    def _cena(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, lotes = _estoque(s)
            _template(s, ("estoque", "vet", "horario"))
            for n in ("1", "2"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1", "2"])
        ag = _agendar(c, cal, ["1", "2"], vet=vet)["id"]
        return c, engine, ag, vet, est

    def test_pendentes_pedem_ciencia_que_fica_gravada_com_quem_e_quando(self, ctx):
        c, engine, ag, vet, est = self._cena(ctx)
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 400 and "ciência" in r.json()["detail"].lower() and "3" in r.json()["detail"]
        assert _saldo(engine, est) == 100
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est,
                     ciencia_pendentes=True, ciencia_motivo="Veterinário já combinou")
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert {i["chave"] for i in ap["ciencia_itens"]} == {"estoque", "vet", "horario"}
        assert ap["ciencia_motivo"] == "Veterinário já combinou" and ap["ciencia_usuario_id"] == 1 and ap["ciencia_em"]
        assert any("ciência" in e.lower() for e in ap["excecoes"])

    def test_checklist_resolvido_nao_pede_ciencia(self, ctx):
        c, engine, ag, vet, est = self._cena(ctx)
        with Session(engine) as s:
            for item in s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag)).all():
                item.status = "cumprido"
                s.add(item)
            s.commit()
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"]["ciencia_itens"] in (None, [])

    def test_checklist_desconsiderado_tambem_nao_pede_ciencia(self, ctx):
        c, engine, ag, vet, est = self._cena(ctx)
        with Session(engine) as s:
            cron = s.get(CronogramaSanitario, ag)
            cron.checklist_desconsiderado = True
            s.add(cron)
            s.commit()
        assert _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est).status_code == 200


class TestIdempotencia:
    def test_mesma_chave_devolve_o_mesmo_registro_sem_baixar_de_novo(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        corpo = dict(animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est, chave_idempotencia="abc-123")
        r1 = _aplicar(c, ag, **corpo)
        r2 = _aplicar(c, ag, **corpo)
        assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
        assert r1.json()["aplicacao"]["id"] == r2.json()["aplicacao"]["id"]
        assert r2.json()["idempotente"] is True and r1.json()["idempotente"] is False
        assert _saldo(engine, est) == 96
        with Session(engine) as s:
            assert len(s.exec(select(CronogramaSanitarioAplicacao)).all()) == 1
            assert len(s.exec(select(Sanidade)).all()) == 4

    def test_sem_chave_a_segunda_tentativa_e_recusada(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        corpo = dict(animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est)
        assert _aplicar(c, ag, **corpo).status_code == 200
        r = _aplicar(c, ag, **corpo)
        assert r.status_code == 400 and "já foi aplicado" in r.json()["detail"].lower()
        assert _saldo(engine, est) == 96

    def test_cabecalho_idempotency_key_tambem_vale(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        corpo = {"canal": "Agenda", "animais_aplicados": ["1", "2", "3", "9"], "aplicador_pessoa_id": vet, "estoque_id": est}
        h = {"Idempotency-Key": "hdr-1"}
        a = c.post(f"/sanidade/cronogramas/{ag}/aplicar", json=corpo, headers=h)
        b = c.post(f"/sanidade/cronogramas/{ag}/aplicar", json=corpo, headers=h)
        assert a.status_code == 200 and b.status_code == 200
        assert _saldo(engine, est) == 96


# ───────────────────────── desfazer e estornar ─────────────────────────
class TestDesfazer:
    def _aplicado(self, cenario, **extra):
        c, ag, vet, est = cenario["c"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est,
                     lote_id=cenario["lotes"][0], **extra)
        assert r.status_code == 200, r.text
        return r.json()["aplicacao"]["id"]

    def test_ate_10_segundos_sem_motivo_reverte_tudo_e_preserva_a_original(self, cenario):
        c, engine, ag, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["est"]
        ap_id = self._aplicado(cenario)
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer")
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["estado"] == "estornada" and ap["tipo_estorno"] == "desfazer" and ap["motivo_estorno"] is None
        assert ap["estornado_em"] and ap["estornado_por_usuario_id"] == 1
        assert r.json()["agendamento"]["status"] == "agendado"
        assert _saldo(engine, est) == 100
        with Session(engine) as s:
            assert s.get(LoteEstoque, cenario["lotes"][0]).quantidade_restante == 100
            assert s.exec(select(Sanidade)).all() == []
            original = s.get(CronogramaSanitarioAplicacao, ap_id)
            assert original is not None and original.produto == "B19" and original.dose_total == 4   # preservada
            assert len(s.exec(select(CronogramaSanitarioAplicacaoAnimal).where(
                CronogramaSanitarioAplicacaoAnimal.aplicacao_id == ap_id)).all()) == 4
            assert s.get(CronogramaSanitario, ag).concluido_em is None
            assert [l.acao for l in s.exec(select(CronogramaSanitarioLog).where(
                CronogramaSanitarioLog.cronograma_id == ag).order_by(CronogramaSanitarioLog.id)).all()][-2:] == ["Aplicou", "Desfez"]
        assert set(_status(engine, ag).values()) == {"incluido"}
        # o agendamento volta a poder ser aplicado (e os movimentos de estorno ficam no rastro)
        movs = _movs(engine, est)
        assert len([m for m in movs if m.movimento == "Aplicação"]) == 4 and len([m for m in movs if m.movimento == "Entrada de ajuste"]) == 4

    def test_depois_de_10_segundos_nao_desfaz(self, cenario):
        c, engine = cenario["c"], cenario["engine"]
        ap_id = self._aplicado(cenario)
        with Session(engine) as s:
            ap = s.get(CronogramaSanitarioAplicacao, ap_id)
            ap.registrado_em = datetime.utcnow() - timedelta(seconds=11)
            s.add(ap)
            s.commit()
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer")
        assert r.status_code == 409 and "estornar" in r.json()["detail"].lower()
        assert _saldo(engine, cenario["est"]) == 96

    def test_desfazer_so_o_mesmo_usuario_ou_admin(self, cenario):
        c, engine = cenario["c"], cenario["engine"]
        ap_id = self._aplicado(cenario)
        _USUARIO.update(id=2, papel="operador")
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer")
        assert r.status_code == 403
        _USUARIO.update(id=1, papel="operador")
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer").status_code == 200

    def test_nao_desfaz_duas_vezes(self, cenario):
        c = cenario["c"]
        ap_id = self._aplicado(cenario)
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer").status_code == 200
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer").status_code == 400

    def test_desfazer_desconsiderando_estoque_nao_mexe_no_estoque(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, desconsiderar_estoque=True,
                     motivo_desconsiderar_estoque="Frasco do veterinário")
        ap_id = r.json()["aplicacao"]["id"]
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer").status_code == 200
        assert _saldo(engine, est) == 100 and _movs(engine, est) == []


class TestEstornar:
    def _aplicado_ha(self, cenario, segundos: int = 60, **extra) -> int:
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2"], aplicador_pessoa_id=vet, estoque_id=est, nao_aplicados=[
            {"numero_matriz": "3", "motivo": "Doente", "destino": "espera"},
            {"numero_matriz": "9", "motivo": "Vendido", "destino": "naoSeAplica"}], **extra)
        assert r.status_code == 200, r.text
        ap_id = r.json()["aplicacao"]["id"]
        with Session(engine) as s:
            ap = s.get(CronogramaSanitarioAplicacao, ap_id)
            ap.registrado_em = datetime.utcnow() - timedelta(seconds=segundos)
            s.add(ap)
            s.commit()
        return ap_id

    def test_exige_admin_e_motivo(self, cenario):
        c, engine, est = cenario["c"], cenario["engine"], cenario["est"]
        ap_id = self._aplicado_ha(cenario)
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": ""})
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={})
        assert r.status_code in (400, 422)
        _USUARIO.update(id=2, papel="operador")
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": "Errei o animal"})
        assert r.status_code == 403
        assert _saldo(engine, est) == 98

    def test_estorno_preserva_original_devolve_estoque_e_reabre_o_agendamento(self, cenario):
        c, engine, ag, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["est"]
        ap_id = self._aplicado_ha(cenario)
        r = c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": "Errei o animal"})
        assert r.status_code == 200, r.text
        ap = r.json()["aplicacao"]
        assert ap["estado"] == "estornada" and ap["tipo_estorno"] == "estorno" and ap["motivo_estorno"] == "Errei o animal"
        assert ap["estornado_por_usuario_id"] == 1 and ap["estornado_em"]
        assert r.json()["agendamento"]["status"] == "agendado"
        assert _saldo(engine, est) == 100
        with Session(engine) as s:
            assert s.exec(select(Sanidade)).all() == []
            assert s.get(CronogramaSanitarioAplicacao, ap_id).dose_total == 2            # original intacta
            log = [l for l in s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag)).all()
                   if l.acao == "Estornou"]
            assert len(log) == 1 and log[0].motivo == "Errei o animal" and log[0].usuario_id == 1
        # 3 saiu da lista de espera e 9 do excluido: os quatro voltam a estar no agendamento
        assert _status(engine, ag) == {"1": "incluido", "2": "incluido", "3": "incluido", "9": "incluido"}
        assert c.get("/sanidade/cronogramas/lista-espera").json()["total"] == 0

    def test_depois_do_estorno_da_para_aplicar_de_novo(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        ap_id = self._aplicado_ha(cenario)
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": "A aplicação não aconteceu"}).status_code == 200
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est)
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"]["id"] != ap_id and _saldo(engine, est) == 96

    def test_nao_estorna_duas_vezes(self, cenario):
        c = cenario["c"]
        ap_id = self._aplicado_ha(cenario)
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": "x y"}).status_code == 200
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": "x y"}).status_code == 400


# ───────────────────────── concluidos e acompanhamento ─────────────────────────
class TestConcluidos:
    def test_lista_com_selos_de_excecao_retroativo_e_estorno(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est,
                     data_aplicacao=(HOJE - timedelta(days=1)).isoformat(), canal="Agenda")
        ap_id = r.json()["aplicacao"]["id"]
        dados = c.get("/sanidade/cronogramas/concluidos").json()
        assert dados["total"] == 1
        linha = dados["itens"][0]
        assert linha["id"] == ap_id and linha["estado"] == "aplicada" and linha["protocolo_nome"] == "Brucelose B19"
        assert linha["animais_aplicados"] == 4 and linha["animais_nao_aplicados"] == 0 and linha["fora_janela"] == 1
        assert linha["retroativo"] is True and linha["canal"] == "Agenda" and linha["aplicador_nome"] == "Dr. Paulo"
        assert linha["com_excecao"] is True and linha["frasco"] == "L1" and linha["custo"] == pytest.approx(25.6)
        assert linha["carencia_carne_ate"] == (HOJE - timedelta(days=1) + timedelta(days=28)).isoformat()
        with Session(engine) as s:
            ap = s.get(CronogramaSanitarioAplicacao, ap_id)
            ap.registrado_em = datetime.utcnow() - timedelta(minutes=5)
            s.add(ap)
            s.commit()
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": "Errei o frasco ou o produto"}).status_code == 200
        dados = c.get("/sanidade/cronogramas/concluidos").json()
        assert dados["itens"][0]["estado"] == "estornada" and dados["itens"][0]["motivo_estorno"] == "Errei o frasco ou o produto"
        assert dados["itens"][0]["pode_desfazer"] is False

    def test_detalhe_traz_animais_ciencia_e_trilha(self, cenario):
        c, ag, vet, est = cenario["c"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est)
        ap_id = r.json()["aplicacao"]["id"]
        det = c.get(f"/sanidade/cronogramas/aplicacoes/{ap_id}").json()
        assert [a["numero_matriz"] for a in det["animais"]] == ["1", "2", "3", "9"]
        assert [l["acao"] for l in det["log"]] == ["Agendou", "Aplicou"] and det["log"][1]["usuario_nome"] == "teste"

    def test_filtros_protocolo_periodo_fora_da_janela_e_busca(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, _ = _estoque(s)
            est2, _ = _estoque(s, "Leptospirose")
            for n in ("1", "2", "9"):
                _animal(s, n)
            a = _regra(s)
            b = _regra(s, "Leptospirose", produto="Leptospirose")
            _espera(s, a, ["1"])
            _espera(s, b, ["2"])
        ag_a = _agendar(c, a, ["1"], fora=[{"numero_matriz": "9", "motivo": "Outro"}], vet=vet)["id"]
        ag_b = _agendar(c, b, ["2"], vet=vet)["id"]
        _aplicar(c, ag_a, animais_aplicados=["1", "9"], aplicador_pessoa_id=vet, estoque_id=est)
        _aplicar(c, ag_b, animais_aplicados=["2"], aplicador_pessoa_id=vet, estoque_id=est2)
        assert c.get("/sanidade/cronogramas/concluidos").json()["total"] == 2
        assert c.get("/sanidade/cronogramas/concluidos", params={"calendario_id": b}).json()["total"] == 1
        assert c.get("/sanidade/cronogramas/concluidos", params={"fora_janela": True}).json()["total"] == 1
        assert c.get("/sanidade/cronogramas/concluidos", params={"q": "9"}).json()["total"] == 1
        amanha = (HOJE + timedelta(days=1)).isoformat()
        assert c.get("/sanidade/cronogramas/concluidos", params={"de": amanha}).json()["total"] == 0

    def test_cancelados_aparecem_no_historico_com_o_motivo(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"])["id"]
        assert c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Veterinário não pode"}).status_code == 200
        itens = c.get("/sanidade/cronogramas/concluidos").json()["itens"]
        assert len(itens) == 1 and itens[0]["estado"] == "cancelado" and itens[0]["motivo"] == "Veterinário não pode"


class TestAcompanhamento:
    def test_lista_so_agendamentos_com_checklist_estado_e_responsavel(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            _estoque(s)
            _template(s, ("estoque", "vet", "horario"))
            for n in ("1", "2", "3", "4"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1", "2", "3", "4"])
        hoje = _agendar(c, cal, ["1"], vet=vet)
        atrasado = _agendar(c, cal, ["2"], data=HOJE - timedelta(days=1))
        futuro = _agendar(c, cal, ["3"], data=HOJE + timedelta(days=4))
        rascunho = _agendar(c, cal, ["4"], rascunho=True)   # o que sobra na lista de espera nao entra
        dados = c.get("/sanidade/cronogramas/acompanhamento").json()
        por = {i["id"]: i for i in dados["agendamentos"]}
        assert set(por) == {hoje["id"], atrasado["id"], futuro["id"], rascunho["id"]}
        assert por[hoje["id"]]["estado_visual"] == "hoje" and por[atrasado["id"]]["estado_visual"] == "atrasado"
        assert por[futuro["id"]]["estado_visual"] == "agendado" and por[rascunho["id"]]["estado_visual"] == "em_montagem"
        h = por[hoje["id"]]
        assert h["responsavel"]["nome"] == "Dr. Paulo" and h["responsavel"]["crmv"] == "CRMV-MG 12345"
        # fatia 9: o agendamento de vacina traz o item de compra; com o estoque cobrindo ele ja nasce "Nao necessaria"
        assert h["checklist"]["total"] == 4 and h["checklist"]["resolvidos"] == 1 and h["animais_total"] == 1
        assert h["protocolo_nome"] == "Brucelose B19" and h["exige_veterinario"] is True and h["lotes"] == ["Bezerreiro"]
        assert dados["totais"] == {"hoje": 1, "atrasados": 1, "agendados": 3}

    def test_adiado_mostra_estado_e_a_data_original(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"])["id"]
        nova = (HOJE + timedelta(days=2)).isoformat()
        r = c.post(f"/sanidade/cronogramas/{ag}/adiar", json={"nova_data": nova, "motivo": "Chuva"})
        assert r.status_code == 200
        item = c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"][0]
        assert item["estado_visual"] == "adiado" and item["motivo_adiamento"] == "Chuva"
        assert item["data_antes_do_adiamento"] == HOJE.isoformat() and item["data_evento"] == nova

    def test_nao_lista_agendamento_de_outra_fazenda_nem_aplicado(self, cenario):
        c, ag, vet, est = cenario["c"], cenario["ag"], cenario["vet"], cenario["est"]
        assert len(c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"]) == 1
        _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est)
        assert c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"] == []
        _USUARIO["fazenda"] = 2
        assert c.get("/sanidade/cronogramas/concluidos").json()["total"] == 0


class TestAdiarExigeMotivo:
    def test_adiar_agendamento_preventivo_sem_motivo_e_recusado_e_o_erro_de_id_vem_antes(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"])["id"]
        nova = (HOJE + timedelta(days=2)).isoformat()
        for motivo in (None, "", "  "):
            corpo = {"nova_data": nova} if motivo is None else {"nova_data": nova, "motivo": motivo}
            r = c.post(f"/sanidade/cronogramas/{ag}/adiar", json=corpo)
            assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()
        assert c.post("/sanidade/cronogramas/99999/adiar", json={"nova_data": nova}).status_code == 404
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, ag).data_evento == HOJE

    def test_adiar_e_cancelar_entram_no_log(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"])["id"]
        c.post(f"/sanidade/cronogramas/{ag}/adiar", json={"nova_data": (HOJE + timedelta(days=2)).isoformat(), "motivo": "Chuva"})
        c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano"})
        with Session(engine) as s:
            log = s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag).order_by(CronogramaSanitarioLog.id)).all()
        assert [(l.acao, l.motivo) for l in log] == [("Agendou", None), ("Adiou", "Chuva"), ("Cancelou", "Mudança de plano")]


# ─────────────────────────── checklist do agendamento ───────────────────────────
class TestChecklistDoAgendamento:
    def _cena(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, peao = _pessoas(s)
            est, lotes = _estoque(s)
            _template(s, ("estoque", "vet", "horario", "financeiro"))
            for n in ("1", "2"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1", "2"])
        return c, engine, cal, vet, est, lotes

    def _itens(self, engine, ag) -> dict[str, ChecklistItem]:
        with Session(engine) as s:
            return {i.chave: i for i in s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag)).all()}

    def test_veterinario_confirmado_estoque_vinculado_e_data(self, ctx):
        c, engine, cal, vet, est, lotes = self._cena(ctx)
        ag = _agendar(c, cal, ["1", "2"])["id"]
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={
            "veterinario": {"estado": "confirmado", "pessoa_id": vet},
            "estoque": {"estado": "vinculado", "estoque_id": est, "lote_id": lotes[0]},
            "data": {"estado": "confirmado"},
        })
        assert r.status_code == 200, r.text
        it = self._itens(engine, ag)
        assert it["vet"].status == "cumprido" and it["vet"].resposta == "sim"
        assert it["estoque"].status == "cumprido" and json.loads(it["estoque"].resposta) == {"estoque_id": est, "lote_id": lotes[0]}
        assert it["horario"].status == "cumprido" and it["horario"].resposta == "15:30"
        assert it["financeiro"].status == "pendente"
        assert r.json()["checklist"]["resolvidos"] == 4 and r.json()["checklist"]["total"] == 5   # + compra (Nao necessaria)
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, ag).veterinario_pessoa_id == vet

    def test_desconsiderar_veterinario_e_estoque_exige_motivo(self, ctx):
        c, engine, cal, vet, est, lotes = self._cena(ctx)
        ag = _agendar(c, cal, ["1", "2"])["id"]
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"veterinario": {"estado": "desconsiderado"}})
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"estoque": {"estado": "desconsiderado", "motivo": " "}})
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={
            "veterinario": {"estado": "desconsiderado", "motivo": "Aplico eu mesmo"},
            "estoque": {"estado": "desconsiderado", "motivo": "Frasco do veterinário", "lote": "VET-1", "validade": (HOJE + timedelta(days=90)).isoformat()},
        })
        assert r.status_code == 200, r.text
        it = self._itens(engine, ag)
        assert it["vet"].status == "pulado" and it["vet"].observacao == "Aplico eu mesmo"
        assert it["estoque"].status == "pulado" and it["estoque"].observacao == "Frasco do veterinário"
        assert json.loads(it["estoque"].resposta) == {"lote": "VET-1", "validade": (HOJE + timedelta(days=90)).isoformat()}

    def test_estoque_de_outra_fazenda_nao_vincula(self, ctx):
        c, engine, cal, vet, est, lotes = self._cena(ctx)
        with Session(engine) as s:
            alheio, _ = _estoque(s, "B19", fazenda_id=2)
        ag = _agendar(c, cal, ["1", "2"])["id"]
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"estoque": {"estado": "vinculado", "estoque_id": alheio}})
        assert r.status_code == 400

    def test_outros_itens_extras_e_cumprir_pular_reabrir(self, ctx):
        c, engine, cal, vet, est, lotes = self._cena(ctx)
        ag = _agendar(c, cal, ["1", "2"])["id"]
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"extras": [{"texto": "Separar os animais no curral"}]})
        assert r.status_code == 200, r.text
        it = self._itens(engine, ag)
        assert it["custom"].nome == "Separar os animais no curral" and it["custom"].status == "pendente"
        fin, cus = it["financeiro"].id, it["custom"].id
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"itens": [
            {"item_id": fin, "acao": "pular", "motivo": "Sem custo"}, {"item_id": cus, "acao": "cumprir"}]})
        assert r.status_code == 200, r.text
        it = self._itens(engine, ag)
        assert it["financeiro"].status == "pulado" and it["financeiro"].observacao == "Sem custo" and it["custom"].status == "cumprido"
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"itens": [{"item_id": cus, "acao": "reabrir"}]})
        assert self._itens(engine, ag)["custom"].status == "pendente"
        r = c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"itens": [{"item_id": fin, "acao": "pular"}]})
        assert r.status_code == 400 and "motivo" in r.json()["detail"].lower()

    def test_checklist_entra_no_criar_agendamento(self, ctx):
        c, engine, cal, vet, est, lotes = self._cena(ctx)
        ag = _agendar(c, cal, ["1", "2"], vet=vet, checklist={
            "veterinario": {"estado": "confirmado", "pessoa_id": vet},
            "estoque": {"estado": "vinculado", "estoque_id": est},
            "data": {"estado": "confirmado"}, "extras": [{"texto": "Levar luvas"}],
        })
        it = self._itens(engine, ag["id"])
        assert it["vet"].status == "cumprido" and it["estoque"].status == "cumprido" and it["horario"].status == "cumprido"
        assert it["custom"].nome == "Levar luvas"
        assert ag["checklist"]["resolvidos"] == 4   # + compra (Nao necessaria)

    def test_checklist_de_agendamento_de_outra_fazenda_devolve_404(self, ctx):
        c, engine, cal, vet, est, lotes = self._cena(ctx)
        ag = _agendar(c, cal, ["1", "2"])["id"]
        _USUARIO["fazenda"] = 2
        assert c.put(f"/sanidade/cronogramas/{ag}/checklist", json={"data": {"estado": "confirmado"}}).status_code == 404


# ─────────────────────── contexto da gaveta, isolamento, agenda ───────────────────────
class TestContextoDaGaveta:
    def test_traz_animais_com_dose_frascos_pessoas_pendentes_e_carencia(self, cenario):
        c = cenario["c"]
        _materializar_template(cenario, ("estoque", "horario"))
        ctxo = c.get(f"/sanidade/cronogramas/{cenario['ag']}/aplicar-contexto").json()
        assert ctxo["protocolo_nome"] == "Brucelose B19" and ctxo["produto"] == "B19" and ctxo["exige_veterinario"] is True
        assert ctxo["dose_texto"] and ctxo["via"] == "Subcutânea" and ctxo["por_peso"] is False
        assert [a["numero_matriz"] for a in ctxo["animais"]] == ["1", "2", "3", "9"]
        assert ctxo["animais"][3]["origem"] == "fora_janela" and ctxo["animais"][0]["dose"] == 1
        frasco = ctxo["estoque"]["lotes"][0]
        assert frasco["numero_lote"] == "L1" and frasco["saldo"] == 100 and frasco["vencido"] is False and frasco["validade"]
        assert ctxo["estoque"]["saldo"] == 100 and ctxo["estoque"]["estoque_id"] == cenario["est"]
        assert {p["nome"] for p in ctxo["pessoas"]} == {"Dr. Paulo", "Zeca"}
        assert next(p for p in ctxo["pessoas"] if p["nome"] == "Dr. Paulo")["veterinario"] is True
        assert ctxo["carencia"]["carne_dias"] == 28
        assert ctxo["checklist"]["pendentes"] and {i["chave"] for i in ctxo["checklist"]["pendentes"]} == {"estoque", "horario"}
        assert ctxo["desfazer_segundos"] == 10 and ctxo["estado"] == "agendado"

    def test_dose_por_peso_no_contexto(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            _estoque(s, "Ivermectina 1%", unidade="ml", por_peso=True)
            _animal(s, "1", grupo="R1")
            _peso(s, "1", 350.0)
            cal = _regra(s, "Vermifugação", produto="Ivermectina 1%", categoria="tratamento", unidade="ml")
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"])["id"]
        ctxo = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
        assert ctxo["por_peso"] is True and ctxo["animais"][0]["peso_kg"] == 350 and ctxo["animais"][0]["dose"] == pytest.approx(7.0)
        assert ctxo["exige_veterinario"] is False


class TestIsolamento:
    def test_outra_fazenda_nao_ve_nem_mexe(self, cenario):
        c, engine, ag, vet, est = cenario["c"], cenario["engine"], cenario["ag"], cenario["vet"], cenario["est"]
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est)
        ap_id = r.json()["aplicacao"]["id"]
        _USUARIO["fazenda"] = 2
        assert _aplicar(c, ag, animais_aplicados=["1"], aplicador_pessoa_id=vet, estoque_id=est).status_code == 404
        assert c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").status_code == 404
        assert c.get(f"/sanidade/cronogramas/aplicacoes/{ap_id}").status_code == 404
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/desfazer").status_code == 404
        assert c.post(f"/sanidade/cronogramas/aplicacoes/{ap_id}/estornar", json={"motivo": "teste"}).status_code == 404
        assert c.get("/sanidade/cronogramas/concluidos").json()["total"] == 0
        assert c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"] == []


class TestAgendaMesmoEndpoint:
    def test_evento_da_agenda_traz_o_cronograma_e_o_resumo_do_checklist(self, cenario):
        c = cenario["c"]
        _materializar_template(cenario, ("estoque", "vet", "horario"))
        dia = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        ev = next(e for e in dia["eventos"] if e["id"] == f"cronograma_sanitario_aplicar_{cenario['ag']}")
        assert ev["cronograma_id"] == cenario["ag"] and ev["checklist_total"] == 3 and ev["checklist_resolvidos"] == 0
        assert ev["protocolo_nome"] == "Brucelose B19"

    def test_apos_aplicar_pela_agenda_o_evento_some(self, cenario):
        c, ag, vet, est = cenario["c"], cenario["ag"], cenario["vet"], cenario["est"]
        assert _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est, canal="Agenda").status_code == 200
        dia = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        assert not [e for e in dia["eventos"] if str(e["id"]).startswith("cronograma_sanitario_aplicar_")]


# ───────────────────── cancelar com destino dos animais e continuar rascunho ─────────────────────
class TestCancelarComDestino:
    def _cena(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            for n in ("1", "2", "9"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1", "2"])
        ag = _agendar(c, cal, ["1", "2"], fora=[{"numero_matriz": "9", "motivo": "Outro"}])["id"]
        return c, engine, ag

    def test_padrao_devolve_a_lista_de_espera(self, ctx):
        c, engine, ag = self._cena(ctx)
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano"})
        assert r.status_code == 200 and r.json()["devolvidos"] == 2
        assert c.get("/sanidade/cronogramas/lista-espera").json()["total"] == 2

    def test_desconsiderar_os_animais_nao_devolve_e_guarda_o_motivo(self, ctx):
        c, engine, ag = self._cena(ctx)
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={
            "motivo": "Campanha oficial cobre", "destino_animais": "naoSeAplica", "destino_conta": "manter"})
        assert r.status_code == 200, r.text
        assert r.json()["devolvidos"] == 0
        assert c.get("/sanidade/cronogramas/lista-espera").json()["total"] == 0
        assert set(_status(engine, ag).values()) == {"excluido"}
        with Session(engine) as s:
            assert all(l.motivo == "Campanha oficial cobre" for l in s.exec(
                select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.cronograma_id == ag)).all())

    def test_destino_invalido_e_recusado(self, ctx):
        c, engine, ag = self._cena(ctx)
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "x", "destino_animais": "sumir"})
        assert r.status_code == 400 and "destino" in r.json()["detail"].lower()
        assert c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"]


class TestConfirmarRascunho:
    def _cena(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            _estoque(s)
            _template(s, ("estoque", "vet", "horario"))
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        rasc = _agendar(c, cal, ["1"], rascunho=True, data=HOJE + timedelta(days=3), hora=None)
        assert rasc["status"] == "em_montagem"
        return c, engine, rasc["id"], vet

    def test_confirma_com_data_hora_responsavel_e_checklist_e_vai_para_a_agenda(self, ctx):
        c, engine, ag, vet = self._cena(ctx)
        dia = HOJE + timedelta(days=3)
        r = c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={
            "data_evento": dia.isoformat(), "hora": "09:00", "modo_execucao": "veterinario", "veterinario_pessoa_id": vet,
            "checklist": {"veterinario": {"estado": "confirmado", "pessoa_id": vet}, "data": {"estado": "confirmado"}}})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "agendado" and r.json()["hora"] == "09:00" and r.json()["checklist"]["resolvidos"] == 3
        assert r.json()["veterinario_pessoa_id"] == vet
        no_dia = c.get("/agenda/", params={"data": dia.isoformat()}).json()
        assert [e for e in no_dia["eventos"] if e["id"] == f"cronograma_sanitario_aplicar_{ag}"]
        with Session(engine) as s:
            assert "Agendou" in [l.acao for l in s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag)).all()]

    def test_validacoes(self, ctx):
        c, engine, ag, vet = self._cena(ctx)
        dia = (HOJE + timedelta(days=3)).isoformat()
        assert c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={"data_evento": dia, "hora": "9h"}).status_code == 400
        r = c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={"data_evento": dia, "modo_execucao": "veterinario"})
        assert r.status_code == 400 and "veterin" in r.json()["detail"].lower()
        assert c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={"data_evento": dia, "hora": "09:00"}).status_code == 200
        r = c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={"data_evento": dia, "hora": "09:00"})
        assert r.status_code == 400 and "montagem" in r.json()["detail"].lower()
        _USUARIO["fazenda"] = 2
        assert c.post(f"/sanidade/cronogramas/{ag}/confirmar", json={"data_evento": dia}).status_code == 404


class TestCrmvDoVeterinario:
    def test_cadastro_grava_o_crmv_e_a_gaveta_mostra_ao_escolher_quem_aplica(self, ctx):
        c, engine = ctx
        r = c.post("/cadastro/pessoas", json={"nome": "Dra. Ana", "tipos": ["Veterinário"], "crmv": "CRMV-SP 999"})
        assert r.status_code == 200, r.text
        assert r.json()["crmv"] == "CRMV-SP 999"
        r2 = c.put(f"/cadastro/pessoas/{r.json()['id']}", json={"nome": "Dra. Ana", "tipos": ["Veterinário"], "crmv": "CRMV-SP 1000"})
        assert r2.status_code == 200 and r2.json()["crmv"] == "CRMV-SP 1000"
        with Session(engine) as s:
            _estoque(s)
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"])["id"]
        ctxo = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
        ana = next(p for p in ctxo["pessoas"] if p["nome"] == "Dra. Ana")
        assert ana["crmv"] == "CRMV-SP 1000" and ana["veterinario"] is True
