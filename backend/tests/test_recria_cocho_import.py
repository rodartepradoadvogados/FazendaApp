"""
Recria > Nutrição — importação de planilha (leitura de cocho / IMS de campo).
Cobre o modelo Excel baixável e o import (linhas válidas, erros de linha).
"""
from __future__ import annotations

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — garante que as tabelas estejam registradas no metadata antes do create_all


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1; papel = "admin"; ativo = True; username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _planilha(linhas: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Data", "Lote", "Número de animais", "Kg ofertado", "Kg sobra", "Kg formulado (meta, opcional)"])
    for linha in linhas:
        ws.append(linha)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestModeloExcel:
    def test_baixa_modelo(self, client):
        c, _ = client
        r = c.get("/recria/cocho/modelo-excel")
        assert r.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        assert wb.active["A1"].value == "Data"


class TestImportarCocho:
    def test_importa_linhas_validas(self, client):
        c, _ = client
        conteudo = _planilha([
            ["05/07/2026", "01 - Lactação Alta", 45, "900,0", "60,0", "850,0"],
            ["06/07/2026", "01 - Lactação Alta", 45, "910,0", "50,0", ""],
        ])
        r = c.post(
            "/recria/cocho/importar",
            files={"file": ("cocho.xlsx", conteudo, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert r.status_code == 200
        j = r.json()
        assert j["criados"] == 2
        assert j["erros"] == []

        registros = c.get("/recria/cocho").json()["registros"]
        assert len(registros) == 2
        assert any(reg["kg_ofertado"] == 900.0 and reg["kg_formulado"] == 850.0 for reg in registros)

    def test_linha_sem_lote_vira_erro(self, client):
        c, _ = client
        conteudo = _planilha([["05/07/2026", "", 45, "900,0", "60,0", ""]])
        r = c.post(
            "/recria/cocho/importar",
            files={"file": ("cocho.xlsx", conteudo, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        j = r.json()
        assert j["criados"] == 0
        assert len(j["erros"]) == 1

    def test_sobra_maior_que_ofertado_vira_erro(self, client):
        c, _ = client
        conteudo = _planilha([["05/07/2026", "Bezerras", 10, "100,0", "150,0", ""]])
        r = c.post(
            "/recria/cocho/importar",
            files={"file": ("cocho.xlsx", conteudo, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        j = r.json()
        assert j["criados"] == 0
        assert len(j["erros"]) == 1
