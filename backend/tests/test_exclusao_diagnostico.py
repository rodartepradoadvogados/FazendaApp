"""
Excluir lançamento › Diagnóstico de gestação (o exame, não a inseminação) e a ordem "mais recentes primeiro" das
listas de exclusão. Antes a lista ordenava pelo TEXTO do título ("<matriz> — dd/mm/aaaa") e cortava em 200: o
diagnóstico lançado hoje sumia atrás de matrizes de número maior e a tela mostrava 2023–2024.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, Servico
from fazenda.models.planos import MODULOS_COMERCIAIS

HOJE = date.today()


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _como_admin():
    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()


def _como_operador():
    import main
    from fazenda.auth import get_current_user

    class _FakeOperador:
        id = 2
        papel = "operador"
        ativo = True
        username = "operador-teste"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()




def _como_fazenda(fazenda_id):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _servico(engine, numero, dias_atras, **kw):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev="Vaca", sexo="F", ativo=True, fazenda_id=1))
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), ult_ocorrencia=1, fazenda_id=1, **kw))
        s.commit()


def _buscar(c, tipo, **q):
    r = c.get("/exclusoes/buscar", params={"tipo": tipo, **q})
    assert r.status_code == 200, r.text
    return r.json()


def _desfazer(c, tipo, id_):
    r = c.post("/exclusoes/impacto", json={"tipo": tipo, "id": id_})
    assert r.status_code == 200, r.text
    r2 = c.post("/exclusoes/confirmar", json={"tipo": tipo, "id": id_, "motivo": "teste", "confirmacao": "APAGAR"})
    assert r2.status_code == 200, r2.text
    return r.json(), r2.json()


class TestOrdemMaisRecentesPrimeiro:
    def _muitos_antigos(self, engine):
        # 230 inseminações antigas de matrizes com número ALTO (alfabeticamente "depois" de 11153) e uma de hoje.
        with Session(engine) as s:
            for i in range(230):
                n = f"9{i:03d}"
                s.add(Animal(numero=n, categoria_abrev="Vaca", sexo="F", ativo=True, fazenda_id=1))
                s.add(Servico(numero_matriz=n, data_servico=date(2024, 1, 1) + timedelta(days=i), fazenda_id=1, ult_ocorrencia=1))
            s.commit()

    def test_servico_de_hoje_vem_primeiro_mesmo_com_matriz_de_numero_menor(self, client):
        c, engine = client
        _como_fazenda(1)
        self._muitos_antigos(engine)
        _servico(engine, "11153", 0)
        itens = _buscar(c, "servico")
        assert len(itens) == 200
        assert itens[0]["titulo"].startswith("11153 —")
        datas = [i["titulo"].split("— ")[1] for i in itens]
        ordenadas = sorted(datas, key=lambda d: tuple(reversed(d.split("/"))), reverse=True)
        assert datas == ordenadas

    def test_diagnostico_de_hoje_aparece_na_lista_do_tipo_diagnostico(self, client):
        c, engine = client
        _como_fazenda(1)
        self._muitos_antigos(engine)
        with Session(engine) as s:
            for sv in s.exec(select(Servico)).all():
                sv.diagnostico, sv.data_diagnostico = "POSITIVO", sv.data_servico + timedelta(days=35)
                s.add(sv)
            s.commit()
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
        itens = _buscar(c, "diagnostico")
        assert itens[0]["titulo"].startswith("11153 — Toque")
        assert itens[0]["id"].endswith(":toque")

    def test_todos_lancamentos_tambem_traz_o_diagnostico(self, client):
        c, engine = client
        _como_fazenda(1)
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
        tipos = {i["tipo_real"] for i in _buscar(c, "todos_lancamentos")}
        assert {"servico", "diagnostico"} <= tipos


class TestExcluirDiagnostico:
    def _vaca_reconfirmada(self, engine):
        _servico(engine, "11153", 90, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=55), metodo_diagnostico="Palpação",
                 diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=HOJE - timedelta(days=20), retoque=False)

    def test_lista_o_toque_e_o_retoque_como_itens_separados(self, client):
        c, engine = client
        _como_fazenda(1)
        self._vaca_reconfirmada(engine)
        itens = _buscar(c, "diagnostico")
        assert [i["id"].split(":")[1] for i in itens] == ["reconfirmacao", "toque"]
        assert "Retoque" in itens[0]["titulo"] and "POSITIVO" in itens[0]["subtitulo"]

    def test_desfazer_o_retoque_volta_a_reconfirmar_e_preserva_o_toque(self, client):
        c, engine = client
        _como_fazenda(1)
        self._vaca_reconfirmada(engine)
        sid = _buscar(c, "diagnostico")[0]["id"]
        impacto, _ = _desfazer(c, "diagnostico", sid)
        assert any("Retoque de 11153" in i and "a reconfirmar" in i for i in impacto["impacto"])
        with Session(engine) as s:
            sv = s.exec(select(Servico)).one()
            assert sv.diagnostico == "POSITIVO" and sv.data_diagnostico == HOJE - timedelta(days=55)
            assert sv.diagnostico_reconfirmacao is None and sv.data_reconfirmacao is None and sv.retoque is True
        r = c.get("/reproducao/diagnostico/candidatas")
        assert [i["numero_matriz"] for i in r.json()["situacoes"]["a_reconfirmar"]] == ["11153"]

    def test_toque_com_retoque_fica_bloqueado_ate_apagar_o_retoque(self, client):
        c, engine = client
        _como_fazenda(1)
        self._vaca_reconfirmada(engine)
        toque = next(i["id"] for i in _buscar(c, "diagnostico") if i["id"].endswith(":toque"))
        r = c.post("/exclusoes/confirmar", json={"tipo": "diagnostico", "id": toque, "motivo": "teste", "confirmacao": "APAGAR"})
        assert r.status_code == 400 and "retoque" in r.json()["detail"].lower()
        with Session(engine) as s:
            assert s.exec(select(Servico)).one().diagnostico == "POSITIVO"

    def test_desfazer_o_toque_deixa_a_inseminacao_e_o_animal_volta_a_tocar(self, client):
        c, engine = client
        _como_fazenda(1)
        _servico(engine, "11153", 40)
        assert c.post("/reproducao/diagnostico", json={"numero_matriz": "11153", "data_diagnostico": HOJE.isoformat(), "resultado": "retoque"}).status_code == 200
        assert c.get("/reproducao/diagnostico/candidatas").json()["totais"]["a_reconfirmar"] == 1
        item = _buscar(c, "diagnostico")[0]
        assert item["titulo"].startswith("11153 — Toque")
        _desfazer(c, "diagnostico", item["id"])
        with Session(engine) as s:
            sv = s.exec(select(Servico)).one()      # a inseminação continua
            assert sv.diagnostico is None and sv.data_diagnostico is None and not sv.retoque
        corpo = c.get("/reproducao/diagnostico/candidatas").json()
        assert [i["numero_matriz"] for i in corpo["situacoes"]["a_tocar"]] == ["11153"]
        assert _buscar(c, "diagnostico") == []

    def test_desfazer_aborto_registrado_pelo_diagnostico(self, client):
        c, engine = client
        _como_fazenda(1)
        _servico(engine, "11153", 90, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=55),
                 diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=HOJE - timedelta(days=20), retoque=False)
        assert c.post("/reproducao/diagnostico", json={"numero_matriz": "11153", "data_diagnostico": HOJE.isoformat(), "resultado": "aborto"}).status_code == 200
        perda = next(i["id"] for i in _buscar(c, "diagnostico") if i["id"].endswith(":perda"))
        _desfazer(c, "diagnostico", perda)
        with Session(engine) as s:
            sv = s.exec(select(Servico)).one()
            assert sv.data_perda_prenhez is None and sv.motivo_perda_prenhez is None
        assert [i["numero_matriz"] for i in c.get("/reproducao/diagnostico/candidatas").json()["situacoes"]["reconfirmada"]] == ["11153"]

    def test_a_previa_nao_altera_nada(self, client):
        c, engine = client
        _como_fazenda(1)
        self._vaca_reconfirmada(engine)
        sid = _buscar(c, "diagnostico")[0]["id"]
        assert c.post("/exclusoes/impacto", json={"tipo": "diagnostico", "id": sid}).status_code == 200
        with Session(engine) as s:
            assert s.exec(select(Servico)).one().diagnostico_reconfirmacao == "POSITIVO"

    def test_outra_fazenda_nao_enxerga_nem_apaga(self, client):
        c, engine = client
        _como_fazenda(1)
        self._vaca_reconfirmada(engine)
        sid = _buscar(c, "diagnostico")[0]["id"]
        _como_fazenda(2)
        assert _buscar(c, "diagnostico") == []
        assert c.post("/exclusoes/impacto", json={"tipo": "diagnostico", "id": sid}).status_code == 404

    def test_id_invalido_e_exame_inexistente_da_404(self, client):
        c, engine = client
        _como_fazenda(1)
        self._vaca_reconfirmada(engine)
        for ruim in ("abc", "999:toque", "1:perda", "1:outro"):
            assert c.post("/exclusoes/impacto", json={"tipo": "diagnostico", "id": ruim}).status_code == 404

    def test_lote_de_diagnosticos_nao_e_recusado_por_nao_ter_objeto_a_apagar(self, client):
        c, engine = client
        _como_fazenda(1)
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE, retoque=True)
        _servico(engine, "11154", 40, diagnostico="NEGATIVO", data_diagnostico=HOJE)
        ids = [i["id"] for i in _buscar(c, "diagnostico")]
        r = c.post("/exclusoes/confirmar", json={"itens": [{"tipo": "diagnostico", "id": i} for i in ids], "motivo": "teste", "confirmacao": "APAGAR"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert all(sv.diagnostico is None for sv in s.exec(select(Servico)).all())
