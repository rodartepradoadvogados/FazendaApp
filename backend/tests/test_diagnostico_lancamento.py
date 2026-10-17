"""
Lançamento do diagnóstico de gestação (reformulação): quem aparece (`GET /reproducao/diagnostico/candidatas`),
o resultado "Aborto", a reconfirmação inconclusiva e a trava do método "Cio de repasse".

Testa a fiação completa (banco -> estados ao vivo -> fase), não a regra de fase em si (test_fase_toque.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ParametroFazenda, Parto, RepasseConfig, Servico

HOJE = date(2026, 7, 8)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _animal(engine, numero, categoria="Vaca", lote="05 - Secas"):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev=categoria, sexo="F", grupo_primario=lote, ativo=True,
                     data_nasc=HOJE - timedelta(days=2000 if categoria == "Vaca" else 600)))
        s.commit()


def _servico(engine, numero, dias_atras, **kw):
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), ult_ocorrencia=1, **kw))
        s.commit()


def _adesivo_param(engine, ligado: bool):
    with Session(engine) as s:
        s.add(ParametroFazenda(chave="usa_adesivo_deteccao_cio", fazenda_id=None, grupo="reinseminacao_cio",
                               label="Utiliza adesivos?", valor="true" if ligado else "false", tipo="bool"))
        s.commit()


def _candidatas(c):
    r = c.get("/reproducao/diagnostico/candidatas", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def _numeros(corpo, fase):
    return sorted(i["numero_matriz"] for i in corpo["situacoes"][fase])


def _dg(c, numero, resultado, dias_atras=0, **extra):
    return c.post("/reproducao/diagnostico", json={
        "numero_matriz": numero, "data_diagnostico": (HOJE - timedelta(days=dias_atras)).isoformat(),
        "resultado": resultado, **extra,
    })


class TestCandidatas:
    def _rebanho(self, engine):
        for n in ("1", "3", "4", "5", "6", "7", "8"):
            _animal(engine, n)
        _animal(engine, "2", "Novilha", "13 - Novilhas Novas")
        _servico(engine, "1", 35)                                                        # a tocar, no prazo
        _servico(engine, "2", 12)                                                        # a tocar, AINDA NÃO
        _servico(engine, "3", 80, diagnostico="POSITIVO", retoque=True,
                 data_diagnostico=HOJE - timedelta(days=45))                             # a reconfirmar, no prazo
        _servico(engine, "4", 40, diagnostico="POSITIVO", retoque=True,
                 data_diagnostico=HOJE - timedelta(days=10))                             # a reconfirmar, AINDA NÃO
        _servico(engine, "5", 100, diagnostico="POSITIVO", diagnostico_reconfirmacao="POSITIVO", retoque=False,
                 data_diagnostico=HOJE - timedelta(days=70), data_reconfirmacao=HOJE - timedelta(days=40))
        _servico(engine, "6", 100, diagnostico="NEGATIVO", data_diagnostico=HOJE - timedelta(days=70))   # vazia
        with Session(engine) as s:
            s.add(Parto(numero_matriz="7", data_parto=HOJE - timedelta(days=10), ordem_parto=1))     # PEV
            s.commit()
        _servico(engine, "8", 33, diagnostico="INDEFINIDO", retoque=True,
                 data_diagnostico=HOJE - timedelta(days=3))                              # indefinido volta a "a tocar"

    def test_separa_por_situacao_e_deixa_de_fora_vazia_e_pev(self, client):
        c, engine = client
        self._rebanho(engine)
        corpo = _candidatas(c)
        assert _numeros(corpo, "a_tocar") == ["1", "2", "8"]
        assert _numeros(corpo, "a_reconfirmar") == ["3", "4"]
        assert _numeros(corpo, "reconfirmada") == ["5"]
        todos = {n for f in corpo["situacoes"] for n in _numeros(corpo, f)}
        assert "6" not in todos and "7" not in todos
        assert corpo["totais"] == {"a_tocar": 3, "a_reconfirmar": 2, "reconfirmada": 1}

    def test_ainda_nao_segue_os_parametros_e_nunca_bloqueia(self, client):
        c, engine = client
        self._rebanho(engine)
        corpo = _candidatas(c)
        por = {i["numero_matriz"]: i for f in corpo["situacoes"].values() for i in f}
        assert corpo["parametros"] == {"dias_toque": 30, "dias_reconfirmacao": 30}
        assert por["1"]["ainda_nao"] is False
        assert por["2"]["ainda_nao"] is True and por["2"]["dias_para_prazo"] == 18
        assert por["3"]["ainda_nao"] is False
        assert por["4"]["ainda_nao"] is True and por["4"]["dias_para_prazo"] == 20      # 30 + 30 - 40

    def test_item_traz_o_que_a_tabela_mostra(self, client):
        c, engine = client
        self._rebanho(engine)
        item = next(i for i in _candidatas(c)["situacoes"]["a_reconfirmar"] if i["numero_matriz"] == "3")
        assert item["lote_atual"] == "05 - Secas" and item["categoria"] == "vaca"
        assert item["dias_desde_servico"] == 80
        assert item["diagnostico"] == "POSITIVO" and item["data_diagnostico"] == (HOJE - timedelta(days=45)).isoformat()
        assert item["data_reconfirmacao"] is None and item["fase"] == "a_reconfirmar"

    def test_usa_adesivo_acompanha_a_chave_mestra(self, client):
        c, engine = client
        assert _candidatas(c)["usa_adesivo"] is False
        with Session(engine) as s:
            s.add(RepasseConfig(fazenda_id=None, usar=True))
            s.commit()
        assert _candidatas(c)["usa_adesivo"] is True


class TestIdaEVolta:
    """Lançar na tela muda o grupo em que o animal aparece na própria tela (front envia -> back grava -> back devolve)."""

    def test_positivo_para_retoque_vai_de_a_tocar_para_a_reconfirmar(self, client):
        c, engine = client
        _animal(engine, "1")
        _servico(engine, "1", 35)
        assert _numeros(_candidatas(c), "a_tocar") == ["1"]
        assert _dg(c, "1", "retoque").status_code == 200
        corpo = _candidatas(c)
        assert _numeros(corpo, "a_tocar") == [] and _numeros(corpo, "a_reconfirmar") == ["1"]

    def test_reconfirmada_vai_para_reconfirmadas(self, client):
        c, engine = client
        _animal(engine, "3")
        _servico(engine, "3", 80, diagnostico="POSITIVO", retoque=True, data_diagnostico=HOJE - timedelta(days=45))
        assert _dg(c, "3", "reconfirmada").status_code == 200
        corpo = _candidatas(c)
        assert _numeros(corpo, "a_reconfirmar") == [] and _numeros(corpo, "reconfirmada") == ["3"]

    def test_negativo_tira_o_animal_da_tela(self, client):
        c, engine = client
        _animal(engine, "1")
        _servico(engine, "1", 35)
        assert _dg(c, "1", "negativo").status_code == 200
        corpo = _candidatas(c)
        assert all(not corpo["situacoes"][f] for f in corpo["situacoes"])


class TestReconfirmacaoIndefinida:
    def _vaca_a_reconfirmar(self, engine):
        _animal(engine, "3")
        _servico(engine, "3", 80, diagnostico="POSITIVO", retoque=True, data_diagnostico=HOJE - timedelta(days=45))

    def test_preserva_o_primeiro_toque_positivo(self, client):
        c, engine = client
        self._vaca_a_reconfirmar(engine)
        r = _dg(c, "3", "indefinido")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["diagnostico"] == "POSITIVO" and corpo["data_diagnostico"] == (HOJE - timedelta(days=45)).isoformat()
        assert corpo["diagnostico_reconfirmacao"] == "INDEFINIDO" and corpo["data_reconfirmacao"] == HOJE.isoformat()
        assert corpo["retoque"] is True

    def test_depois_um_exame_resolve_nao_e_descartado(self, client):
        c, engine = client
        self._vaca_a_reconfirmar(engine)
        _dg(c, "3", "indefinido", dias_atras=2)
        r = _dg(c, "3", "reconfirmada")
        assert r.status_code == 200
        assert r.json()["diagnostico_reconfirmacao"] == "POSITIVO" and r.json().get("aborto_detectado") is None
        assert _numeros(_candidatas(c), "reconfirmada") == ["3"]

    def test_toque_indefinido_continua_gravando_no_toque(self, client):
        c, engine = client
        _animal(engine, "1")
        _servico(engine, "1", 35)
        r = _dg(c, "1", "indefinido")
        assert r.json()["diagnostico"] == "INDEFINIDO" and r.json()["diagnostico_reconfirmacao"] is None


class TestAborto:
    def _prenha(self, engine, numero="3", reconfirmada=False):
        _animal(engine, numero)
        extra = {"diagnostico_reconfirmacao": "POSITIVO", "data_reconfirmacao": HOJE - timedelta(days=30)} if reconfirmada else {}
        _servico(engine, numero, 90, diagnostico="POSITIVO", retoque=not reconfirmada,
                 data_diagnostico=HOJE - timedelta(days=55), **extra)

    def test_grava_a_perda_na_data_do_diagnostico_com_motivo_pendente(self, client):
        c, engine = client
        self._prenha(engine, reconfirmada=True)
        r = _dg(c, "3", "aborto", dias_atras=1)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["perda_registrada"] is True
        assert corpo["data_perda_prenhez"] == (HOJE - timedelta(days=1)).isoformat()
        assert corpo["motivo_perda_prenhez"] is None
        with Session(engine) as s:
            sv = s.exec(select(Servico).where(Servico.numero_matriz == "3")).one()
            assert sv.data_perda_prenhez == HOJE - timedelta(days=1) and sv.motivo_perda_prenhez is None
            assert sv.diagnostico == "POSITIVO"          # o histórico do toque fica

    def test_animal_sai_da_tela_depois_do_aborto(self, client):
        c, engine = client
        self._prenha(engine, reconfirmada=True)
        assert _numeros(_candidatas(c), "reconfirmada") == ["3"]
        _dg(c, "3", "aborto")
        corpo = _candidatas(c)
        assert all("3" not in _numeros(corpo, f) for f in corpo["situacoes"])

    def test_vale_tambem_para_a_reconfirmar(self, client):
        c, engine = client
        self._prenha(engine)
        assert _dg(c, "3", "aborto").status_code == 200

    def test_sem_prenhez_confirmada_422(self, client):
        c, engine = client
        _animal(engine, "1")
        _servico(engine, "1", 35)
        r = _dg(c, "1", "aborto")
        assert r.status_code == 422
        with Session(engine) as s:
            assert s.exec(select(Servico)).one().data_perda_prenhez is None

    def test_nao_registra_duas_vezes(self, client):
        c, engine = client
        self._prenha(engine, reconfirmada=True)
        assert _dg(c, "3", "aborto").status_code == 200
        assert _dg(c, "3", "aborto").status_code == 422

    def test_matriz_sem_servico_404(self, client):
        c, engine = client
        _animal(engine, "9")
        assert _dg(c, "9", "aborto").status_code == 404


class TestCioDeRepasse:
    def test_fazenda_sem_adesivo_recusa(self, client):
        c, engine = client
        _animal(engine, "1")
        _servico(engine, "1", 35)
        r = _dg(c, "1", "negativo", metodo="Cio de repasse")
        assert r.status_code == 400 and "adesivo" in r.json()["detail"].lower()
        with Session(engine) as s:
            assert s.exec(select(Servico)).one().diagnostico is None

    def test_fazenda_com_adesivo_aceita_negativo(self, client):
        c, engine = client
        _adesivo_param(engine, True)
        _animal(engine, "1")
        _servico(engine, "1", 35)
        r = _dg(c, "1", "negativo", metodo="Cio de repasse")
        assert r.status_code == 200
        assert r.json()["metodo_diagnostico"] == "Cio de repasse" and r.json()["diagnostico"] == "NEGATIVO"

    @pytest.mark.parametrize("resultado", ["retoque", "reconfirmada", "indefinido", "aborto"])
    def test_so_vale_para_negativo(self, client, resultado):
        c, engine = client
        _adesivo_param(engine, True)
        _animal(engine, "1")
        _servico(engine, "1", 35)
        assert _dg(c, "1", resultado, metodo="Cio de repasse").status_code == 400

    def test_palpacao_e_ultrassom_seguem_livres(self, client):
        c, engine = client
        _animal(engine, "1")
        _servico(engine, "1", 35)
        assert _dg(c, "1", "retoque", metodo="Palpação").status_code == 200
