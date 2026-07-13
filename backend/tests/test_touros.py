"""Testes do catálogo de touros NAAB: importador da planilha completa
(dezenas de colunas, ex. Alta Genetics) e cadastro manual."""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Touro
from fazenda.rules.touros import eh_planilha_rica, importar_touros_planilha_rica


def _xlsx_bytes(headers, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Réplica em miniatura do cabeçalho real da Alta Genetics: "Gordura"/"%
# Gordura" e "Proteína"/"Prot%" normalizam para o mesmo apelido genérico, e "D
# / H" aparece duas vezes — exatamente os casos que o importador por posição
# precisa acertar.
HEADERS_RICOS = (
    ["Código NAAB", "Nome", "Nome completo", "Raça"]
    + [f"Col{i}" for i in range(4, 6)]
    + ["TPI", "NM$"]
    + [f"Col{i}" for i in range(8, 11)]
    + ["Leite", "Proteína", "Prot%", "Gordura", "% Gordura"]
    + [f"Col{i}" for i in range(16, 27)]
    + ["SCS"]
    + [f"Col{i}" for i in range(28, 64)]
    + ["PTAT"]
    + [f"Col{i}" for i in range(65, 71)]
    + ["D / H"]
    + [f"Col{i}" for i in range(72, 100)]
)


def _linha_completa(**overrides):
    linha = [None] * len(HEADERS_RICOS)
    for campo, valor in overrides.items():
        linha[HEADERS_RICOS.index(campo)] = valor
    return linha


class TestDeteccaoFormato:
    def test_planilha_rica_detectada(self):
        assert eh_planilha_rica(list(HEADERS_RICOS)) is True

    def test_planilha_simples_nao_e_rica(self):
        assert eh_planilha_rica(["NAAB", "Nome", "TPI"]) is False


class TestImportarPlanilhaRica:
    @pytest.fixture
    def session(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            yield s

    def test_mapeia_campos_curados_sem_trocar_kg_por_pct(self, session):
        # "Proteína"/"Gordura" (kg) não podem cair em proteina_pct/gordura_pct
        # só porque normalizam parecido com "Prot%"/"% Gordura".
        conteudo = _xlsx_bytes(HEADERS_RICOS, [_linha_completa(**{
            "Código NAAB": "007HO99999", "Nome": "TouroTeste", "Nome completo": "TOURO TESTE-ET",
            "Raça": "HO", "TPI": 3000, "NM$": 700, "Leite": 2500, "Proteína": 80, "Prot%": -0.05,
            "Gordura": 90, "% Gordura": -0.1, "SCS": 2.9, "PTAT": 1.2, "D / H": "10/5",
        })])
        resultado = importar_touros_planilha_rica(session, conteudo, "Alta", "Teste")
        assert resultado == {"criados": 1, "atualizados": 0, "erros": []}

        from sqlmodel import select
        t = session.exec(select(Touro).where(Touro.naab == "007HO99999")).first()
        assert t.nome == "TouroTeste"
        assert t.nome_completo == "TOURO TESTE-ET"
        assert t.tpi == 3000
        assert t.nm_dolar == 700
        assert t.leite_kg == 2500
        assert t.proteina_kg == 80
        assert t.proteina_pct == -0.05
        assert t.gordura_kg == 90
        assert t.gordura_pct == -0.1
        assert t.ccs_score == 2.9
        assert t.tipo_composto == 1.2

    def test_preserva_todos_os_dados_em_dados_extra(self, session):
        conteudo = _xlsx_bytes(HEADERS_RICOS, [_linha_completa(**{
            "Código NAAB": "007HO11111", "Nome": "OutroTouro", "D / H": "1/2",
        })])
        importar_touros_planilha_rica(session, conteudo, "Alta", "Teste")
        from sqlmodel import select
        t = session.exec(select(Touro).where(Touro.naab == "007HO11111")).first()
        extra = json.loads(t.dados_extra)
        assert ["Código NAAB", "007HO11111"] in extra
        assert ["Nome", "OutroTouro"] in extra
        assert ["D / H", "1/2"] in extra

    def test_cabecalho_duplicado_preserva_os_dois_valores(self, session):
        # A planilha real tem "D / H" duas vezes (produção e conformação) —
        # dados_extra precisa manter as duas ocorrências, sem uma sobrescrever
        # a outra.
        headers = ["Código NAAB", "Nome", "D / H", "D / H"]
        conteudo = _xlsx_bytes(headers, [["007HO12121", "Duplo", "10/5", "20/8"]])
        importar_touros_planilha_rica(session, conteudo, "Alta", "Teste")
        from sqlmodel import select
        t = session.exec(select(Touro).where(Touro.naab == "007HO12121")).first()
        extra = json.loads(t.dados_extra)
        assert extra.count(["D / H", "10/5"]) == 1
        assert extra.count(["D / H", "20/8"]) == 1

    def test_upsert_por_naab_nao_duplica(self, session):
        conteudo = _xlsx_bytes(HEADERS_RICOS, [
            _linha_completa(**{"Código NAAB": "007HO22222", "Nome": "Primeiro", "TPI": 100}),
        ])
        importar_touros_planilha_rica(session, conteudo, "Alta", None)
        conteudo2 = _xlsx_bytes(HEADERS_RICOS, [
            _linha_completa(**{"Código NAAB": "007HO22222", "Nome": "Atualizado", "TPI": 200}),
        ])
        resultado = importar_touros_planilha_rica(session, conteudo2, "Alta", None)
        assert resultado["criados"] == 0
        assert resultado["atualizados"] == 1
        from sqlmodel import select
        todos = session.exec(select(Touro).where(Touro.naab == "007HO22222")).all()
        assert len(todos) == 1
        assert todos[0].nome == "Atualizado"
        assert todos[0].tpi == 200


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


class TestCadastroManual:
    def test_criar_touro_so_com_naab_e_nome(self, client):
        c, _engine = client
        resp = c.post("/cadastro/touros", json={"naab": "007HO33333", "nome": "Manual"})
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["naab"] == "007HO33333"
        assert corpo["nome"] == "Manual"
        assert corpo["tpi"] is None

    def test_criar_touro_sem_nome_falha(self, client):
        c, _engine = client
        resp = c.post("/cadastro/touros", json={"naab": "007HO44444", "nome": "  "})
        assert resp.status_code == 400

    def test_criar_touro_com_dados_extra(self, client):
        c, _engine = client
        resp = c.post("/cadastro/touros", json={
            "naab": "007HO55555", "nome": "ComExtra", "tpi": 3100,
            "dados_extra": [["Feed Saved", "24"], ["EFI", "12.3"]],
        })
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert json.loads(corpo["dados_extra"]) == [["Feed Saved", "24"], ["EFI", "12.3"]]

    def test_naab_duplicado_falha(self, client):
        c, _engine = client
        c.post("/cadastro/touros", json={"naab": "007HO66666", "nome": "A"})
        resp = c.post("/cadastro/touros", json={"naab": "007HO66666", "nome": "B"})
        assert resp.status_code == 400

    def test_atualizar_touro(self, client):
        c, _engine = client
        criado = c.post("/cadastro/touros", json={"naab": "007HO77777", "nome": "Original"}).json()
        resp = c.put(f"/cadastro/touros/{criado['id']}", json={"naab": "007HO77777", "nome": "Editado", "tpi": 2900})
        assert resp.status_code == 200, resp.text
        assert resp.json()["nome"] == "Editado"
        assert resp.json()["tpi"] == 2900

    def test_excluir_touro(self, client):
        c, _engine = client
        criado = c.post("/cadastro/touros", json={"naab": "007HO88888", "nome": "ParaExcluir"}).json()
        resp = c.delete(f"/cadastro/touros/{criado['id']}")
        assert resp.status_code == 200
        assert c.get("/cadastro/touros").status_code == 200
        naabs = [t["naab"] for t in c.get("/cadastro/touros").json()]
        assert "007HO88888" not in naabs

    def test_campos_planilha_lista_rotulos_conhecidos(self, client):
        c, _engine = client
        resp = c.get("/cadastro/touros/campos-planilha")
        assert resp.status_code == 200
        rotulos = resp.json()
        assert "TPI" in rotulos
        assert "NM$" in rotulos
        assert "naab" not in [r.lower() for r in rotulos]

    def test_recarregar_catalogo_chama_bootstrap_forcado(self, client, monkeypatch):
        c, _engine = client
        chamadas = []

        def _fake_bootstrap(session, forcar=False):
            chamadas.append(forcar)
            session.add(Touro(naab="000FAKE001", nome="Recarregado"))
            session.commit()

        monkeypatch.setattr("fazenda.rules.touros.bootstrap_touros_naab", _fake_bootstrap)
        resp = c.post("/cadastro/touros/recarregar-catalogo")
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["touros_depois"] == corpo["touros_antes"] + 1
        assert chamadas == [True]
