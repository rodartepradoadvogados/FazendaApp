"""Testes de 'acasalamento direcionado': sugestão de touro por vaca, evitando
consanguinidade, complementando características e só considerando touros com
sêmen em estoque (ver `fazenda.rules.acasalamento` e o router
`relatorio_acasalamento`)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, EstoqueSemen, Touro
from fazenda.rules.acasalamento import criterios_explicacao, sugerir_touros


# ---------------------------------------------------------------------------
# Testes unitários puros de `sugerir_touros` (sem DB)
# ---------------------------------------------------------------------------
class TestSugerirTouros:
    def _vaca(self, **overrides):
        base = {
            "numero": "1001",
            "mae_numero": None,
            "pai_nome": "Touro Pai", "pai_naab": "007HO00001",
            "avo_paterno_nome": "Touro Avo", "avo_paterno_naab": "007HO00002",
            "bisavo_paterno_nome": "Touro Bisavo", "bisavo_paterno_naab": "007HO00003",
        }
        base.update(overrides)
        return base

    def test_ordena_por_tpi_quando_sem_ancestral_comum(self):
        vaca = self._vaca()
        touros = [
            {"naab": "9HO111", "nome": "Baixo", "tpi": 2500, "doses": 10, "tipo": "convencional"},
            {"naab": "9HO222", "nome": "Alto", "tpi": 2900, "doses": 5, "tipo": "convencional"},
        ]
        resultado = sugerir_touros(vaca, touros)
        assert [t["naab"] for t in resultado] == ["9HO222", "9HO111"]
        assert all(t["motivo"] for t in resultado)
        assert all(t["tem_ancestral_comum"] is False for t in resultado)

    def test_touro_igual_ao_pai_naab_cai_para_o_fim_com_alerta(self):
        vaca = self._vaca()
        touros = [
            {"naab": "007HO00001", "nome": "Pai Repetido", "tpi": 3200, "doses": 20, "tipo": "sexado"},
            {"naab": "9HO222", "nome": "Outro", "tpi": 2000, "doses": 5, "tipo": "convencional"},
        ]
        resultado = sugerir_touros(vaca, touros)
        assert resultado[0]["naab"] == "9HO222"
        assert resultado[-1]["naab"] == "007HO00001"
        assert resultado[-1]["tem_ancestral_comum"] is True
        assert "Ancestral comum" in resultado[-1]["motivo"]
        assert resultado[-1]["score"] < resultado[0]["score"]

    def test_ancestral_materno_penaliza_quando_informado(self):
        vaca = self._vaca()
        touros = [
            {"naab": "AVO-MATERNO", "nome": "Avo Materno", "tpi": 3000, "doses": 8, "tipo": "convencional"},
            {"naab": "9HO333", "nome": "Neutro", "tpi": 2100, "doses": 8, "tipo": "convencional"},
        ]
        resultado = sugerir_touros(vaca, touros, ancestrais_maternos=["AVO-MATERNO"])
        assert resultado[0]["naab"] == "9HO333"
        assert resultado[-1]["naab"] == "AVO-MATERNO"
        assert resultado[-1]["tem_ancestral_comum"] is True

    def test_sem_ancestrais_maternos_nao_penaliza_por_esse_lado(self):
        vaca = self._vaca()
        # Mesmo NAAB que seria "avô materno" em outro teste, mas aqui
        # `ancestrais_maternos` não foi resolvido (None) — não há como avaliar,
        # então não deve penalizar por consanguinidade materna.
        touros = [{"naab": "AVO-MATERNO", "nome": "Avo Materno", "tpi": 3000, "doses": 8, "tipo": "convencional"}]
        resultado = sugerir_touros(vaca, touros, ancestrais_maternos=None)
        assert resultado[0]["tem_ancestral_comum"] is False

    def test_touro_sem_doses_nao_quebra(self):
        vaca = self._vaca()
        touros = [{"naab": "9HO444", "nome": "SemEstoque", "tpi": 2200, "doses": None, "tipo": "convencional"}]
        resultado = sugerir_touros(vaca, touros)
        assert len(resultado) == 1
        assert resultado[0]["motivo"]

    def test_touro_fazenda_sem_naab_funciona(self):
        vaca = self._vaca()
        touros = [{"naab": None, "nome": "Sevaverde", "tpi": None, "doses": 0, "tipo": "fazenda"}]
        resultado = sugerir_touros(vaca, touros)
        assert len(resultado) == 1
        assert "monta natural" in resultado[0]["motivo"].lower()

    def test_respeita_top_n(self):
        vaca = self._vaca()
        touros = [{"naab": f"9HO{i}", "nome": f"T{i}", "tpi": i, "doses": 1, "tipo": "convencional"} for i in range(10)]
        resultado = sugerir_touros(vaca, touros, top_n=3)
        assert len(resultado) == 3

    def test_criterios_explicacao_tem_3_itens(self):
        criterios = criterios_explicacao()
        assert len(criterios) == 3
        assert all(isinstance(c, str) and c for c in criterios)


# ---------------------------------------------------------------------------
# Testes de integração do endpoint
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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


class TestEndpointSugestao:
    def test_animal_inexistente_404(self, client):
        c, _engine = client
        resp = c.get("/reproducao/acasalamento/sugestao", params={"numero_matriz": "9999"})
        assert resp.status_code == 404

    def test_caso_feliz_com_genealogia_e_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="2001", sexo="F", pai_nome="Reprodutor X", pai_naab="007HO90001"))
            s.add(Touro(naab="007HO90001", nome="Reprodutor X", tpi=2000))
            s.add(Touro(naab="007HO90002", nome="Reprodutor Y", tpi=3100, nm_dolar=900))
            s.add(EstoqueSemen(touro_nome="Reprodutor X", naab="007HO90001", tipo="convencional", doses=5))
            s.add(EstoqueSemen(touro_nome="Reprodutor Y", naab="007HO90002", tipo="sexado", doses=12))
            s.commit()

        resp = c.get("/reproducao/acasalamento/sugestao", params={"numero_matriz": "2001"})
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert len(corpo["criterios"]) == 3
        naabs = [s["naab"] for s in corpo["sugestoes"]]
        assert "007HO90002" in naabs
        assert "007HO90001" in naabs
        # O pai (mesmo NAAB) deve cair para o fim e vir com alerta.
        pai = next(s for s in corpo["sugestoes"] if s["naab"] == "007HO90001")
        assert pai["tem_ancestral_comum"] is True
        assert naabs[-1] == "007HO90001"
        assert all(s["motivo"] for s in corpo["sugestoes"])

    def test_mae_nao_cadastrada_como_animal_nao_quebra(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="2002", sexo="F", mae_numero="INEXISTENTE-999"))
            s.add(Touro(naab="007HO90003", nome="Reprodutor Z", tpi=2800))
            s.add(EstoqueSemen(touro_nome="Reprodutor Z", naab="007HO90003", tipo="convencional", doses=3))
            s.commit()

        resp = c.get("/reproducao/acasalamento/sugestao", params={"numero_matriz": "2002"})
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["ancestrais_maternos_avaliados"] is False
        assert len(corpo["sugestoes"]) == 1
        assert corpo["sugestoes"][0]["naab"] == "007HO90003"
