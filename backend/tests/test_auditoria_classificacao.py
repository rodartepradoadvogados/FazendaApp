"""
Auditoria da classificação reprodutiva (GET /reproducao/auditoria-classificacao): estado ao vivo × roteiro do
veterinário × registros brutos. Cada cenário abaixo é uma das formas reais de um animal «positivo e reconfirmado»
aparecer como vazio/atrasado (caso do animal 11153).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Lactacao, Parto, Servico

HOJE = date.today()


def dia(n: int) -> date:
    return HOJE - timedelta(days=n)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _sessao():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _Admin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin"
        email = "admin@example.com"

    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[get_current_user] = lambda: _Admin()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _animal(engine, numero, categoria="Vaca"):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev=categoria, sexo="F", ativo=True, grupo_primario="05 - Secas",
                     data_nasc=dia(2500 if categoria == "Vaca" else 700)))
        s.commit()


def _servico(engine, numero, ds, **kw):
    kw.setdefault("ult_ocorrencia", 1)
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=ds, **kw))
        s.commit()


def _prenha_reconfirmada(engine, numero, dias_servico=150):
    _servico(engine, numero, dia(dias_servico), diagnostico="POSITIVO", data_diagnostico=dia(dias_servico - 35),
             diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=dia(dias_servico - 70), retoque=False)


def _auditar(c, animal=None):
    r = c.get("/reproducao/auditoria-classificacao", params={"animal": animal} if animal else {})
    assert r.status_code == 200, r.text
    return r.json()


def _codigos(corpo, numero):
    return sorted({a["codigo"] for a in corpo["achados"] if a["numero"] == numero})


class TestAuditoria:
    def test_vaca_prenha_reconfirmada_normal_nao_tem_achado(self, client):
        c, engine = client
        _animal(engine, "100")
        _prenha_reconfirmada(engine, "100")
        corpo = _auditar(c)
        assert corpo["total_achados"] == 0 and corpo["total_animais"] == 1

    def test_servico_com_data_futura_e_apontado(self, client):
        c, engine = client
        _animal(engine, "11153")
        _servico(engine, "11153", HOJE + timedelta(days=10), diagnostico="POSITIVO", data_diagnostico=dia(5),
                 diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=dia(2), retoque=False)
        corpo = _auditar(c)
        a = next(x for x in corpo["achados"] if x["codigo"] == "reconfirmada_nao_gestante")
        assert a["causa"] == "data_futura" and a["severidade"] == "alta" and "futura" in a["explicacao"]

    def test_servico_sem_data_e_apontado(self, client):
        c, engine = client
        _animal(engine, "11153")
        _servico(engine, "11153", None, diagnostico="POSITIVO", data_diagnostico=dia(60),
                 diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=dia(30), retoque=False)
        corpo = _auditar(c)
        assert next(x for x in corpo["achados"] if x["codigo"] == "reconfirmada_nao_gestante")["causa"] == "sem_data"
        assert "datas_incoerentes" not in _codigos(corpo, "11153")  # as datas dos exames em si estão coerentes

    def test_lactacao_aberta_depois_do_servico_sem_parto_e_apontada_e_os_classificadores_concordam(self, client):
        # Desde o PR #930 (matriz 422) o roteiro do veterinário também ancora na Lactacao aberta sem Parto, como o
        # estado ao vivo: os dois concordam (não é mais "classificadores_divergem"); a prenhez sem parto que a explique
        # continua apontada.
        c, engine = client
        _animal(engine, "11153")
        _prenha_reconfirmada(engine, "11153", dias_servico=150)
        with Session(engine) as s:
            s.add(Lactacao(numero_matriz="11153", data_inicio=dia(120), origem="inducao"))
            s.commit()
        corpo = _auditar(c)
        codigos = _codigos(corpo, "11153")
        assert "reconfirmada_nao_gestante" in codigos and "classificadores_divergem" not in codigos
        a = next(x for x in corpo["achados"] if x["codigo"] == "reconfirmada_nao_gestante")
        assert a["causa"] == "lactacao_sem_parto" and "lactação aberta" in a["explicacao"]

    def test_parto_depois_do_servico_explica_e_nao_e_inconsistencia(self, client):
        c, engine = client
        _animal(engine, "100")
        _prenha_reconfirmada(engine, "100", dias_servico=400)
        with Session(engine) as s:
            s.add(Parto(numero_matriz="100", data_parto=dia(120), ordem_parto=1))
            s.commit()
        corpo = _auditar(c)
        assert "reconfirmada_nao_gestante" not in _codigos(corpo, "100")

    def test_nova_inseminacao_depois_da_prenhez_nao_e_inconsistencia(self, client):
        c, engine = client
        _animal(engine, "100")
        _servico(engine, "100", dia(200), diagnostico="POSITIVO", data_diagnostico=dia(160), data_perda_prenhez=dia(100), ult_ocorrencia=0)
        _servico(engine, "100", dia(90))
        assert "reconfirmada_nao_gestante" not in _codigos(_auditar(c), "100")

    def test_datas_incoerentes(self, client):
        c, engine = client
        _animal(engine, "100")
        _servico(engine, "100", dia(100), diagnostico="POSITIVO", data_diagnostico=dia(130))  # toque ANTES da inseminação
        a = next(x for x in _auditar(c)["achados"] if x["codigo"] == "datas_incoerentes")
        assert "antes da inseminação" in a["explicacao"] and a["severidade"] == "media"

    def test_resultado_sem_data_e_fora_do_vocabulario(self, client):
        c, engine = client
        _animal(engine, "100")
        _servico(engine, "100", dia(100), diagnostico="TALVEZ", diagnostico_reconfirmacao="POSITIVO")
        texto = " ".join(a["explicacao"] for a in _auditar(c)["achados"] if a["codigo"] == "datas_incoerentes")
        assert "fora do vocabulário" in texto and "retoque sem data" in texto

    def test_ult_ocorrencia_que_nao_aponta_o_mais_recente(self, client):
        c, engine = client
        _animal(engine, "100")
        _servico(engine, "100", dia(200), ult_ocorrencia=1, diagnostico="NEGATIVO", data_diagnostico=dia(165))
        _servico(engine, "100", dia(90), ult_ocorrencia=0)
        assert "ult_ocorrencia_diverge" in _codigos(_auditar(c), "100")

    def test_gestante_alem_do_parto_previsto(self, client):
        c, engine = client
        _animal(engine, "100", "Novilha")
        _servico(engine, "100", dia(340), diagnostico="POSITIVO", data_diagnostico=dia(300))
        assert "gestante_alem_do_parto_previsto" in _codigos(_auditar(c), "100")

    def test_animal_marcado_a_descartar_e_bezerra_ficam_de_fora(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="200", categoria_abrev="Vaca", sexo="F", ativo=True, a_descartar=True))
            s.add(Animal(numero="201", categoria_abrev="Bezerra", sexo="F", ativo=True))
            s.commit()
        _servico(engine, "200", dia(100))
        assert _auditar(c)["total_animais"] == 0


class TestExplicacaoDoAnimal:
    def test_traz_linha_do_tempo_e_passo_a_passo(self, client):
        c, engine = client
        _animal(engine, "11153")
        _prenha_reconfirmada(engine, "11153", dias_servico=150)
        with Session(engine) as s:
            s.add(Lactacao(numero_matriz="11153", data_inicio=dia(120), origem="inducao"))
            s.commit()
        corpo = _auditar(c, "11153")["animal"]
        assert corpo["numero"] == "11153"
        tipos = [l["tipo"] for l in corpo["linha_do_tempo"]]
        assert tipos == ["servico", "lactacao"]
        texto = " ".join(corpo["passos"])
        assert "Âncora do ciclo" in texto and "início da lactação" in texto and "Nenhum serviço vigente" in texto

    def test_animal_inexistente_da_404(self, client):
        c, engine = client
        assert c.get("/reproducao/auditoria-classificacao", params={"animal": "999"}).status_code == 404

    def test_so_administrador(self, client):
        c, engine = client
        import main
        from fazenda.auth import get_current_user

        class _Operador:
            id = 2
            papel = "operador"
            ativo = True
            username = "op"
            email = "op@example.com"

        main.app.dependency_overrides[get_current_user] = lambda: _Operador()
        assert c.get("/reproducao/auditoria-classificacao").status_code == 403
