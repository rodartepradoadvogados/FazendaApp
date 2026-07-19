"""
Regressão do bug de PARTOS DUPLICADOS: o upload do CSV reprodutivo só inseria
os partos, sem limpar os anteriores — cada reenvio empilhava os mesmos partos
(uma vaca com N uploads ficava com N partos iguais). O upload agora reimporta
sem duplicar, e há uma limpeza única (deduplicar_partos) para os dados antigos.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Parto


# CSV mínimo no formato REPRODUTIVO — uma matriz (068) com um parto real.
# Cabeçalhos batem com o mapa de colunas em parsers/reprodutivo.py.
CSV_REPRO = (
    "NUMERO DA MATRIZ;ORDEM DE PARTO;DATA DO SERVICO;TIPO DO SERVICO;"
    "DIAGNOSTICO;PARTO_REAL;TIPO_PARTO_REAL\n"
    "068;5;20/06/2025;IA;POSITIVO;10/03/2025;Natimorto\n"
).encode("windows-1252")


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
        with Session(engine) as s:
            s.add(Animal(numero="068", grupo_primario="03 - Secas", ativo=True))
            s.commit()
        c._engine = engine  # type: ignore[attr-defined]
        yield c

    main.app.dependency_overrides.clear()


def _partos_068(engine) -> list[Parto]:
    with Session(engine) as s:
        return s.exec(select(Parto).where(Parto.numero_matriz == "068")).all()


def test_reupload_nao_duplica_partos(client):
    engine = client._engine  # type: ignore[attr-defined]
    for _ in range(3):
        r = client.post("/upload/reprodutivo", files={"file": ("repro.csv", CSV_REPRO, "text/csv")})
        assert r.status_code == 200, r.text
    # Depois de 3 uploads do MESMO CSV, ainda deve haver UM único parto.
    partos = _partos_068(engine)
    assert len(partos) == 1, f"esperava 1 parto, achou {len(partos)}"
    assert partos[0].tipo_parto == "Natimorto"


def test_reupload_preserva_numero_cria_ja_associado(client):
    """O CSV do reprodutivo não traz numero_cria_1/2/gemelar_sexo — antes do
    fix, o reenvio apagava e recriava o Parto do zero, perdendo esse vínculo
    (lançado à mão ou pelo backfill). Agora deve preservar."""
    engine = client._engine  # type: ignore[attr-defined]
    r = client.post("/upload/reprodutivo", files={"file": ("repro.csv", CSV_REPRO, "text/csv")})
    assert r.status_code == 200, r.text

    with Session(engine) as s:
        p = s.exec(select(Parto).where(Parto.numero_matriz == "068")).first()
        p.numero_cria_1 = "068-C1"
        s.add(p)
        s.commit()

    r = client.post("/upload/reprodutivo", files={"file": ("repro.csv", CSV_REPRO, "text/csv")})
    assert r.status_code == 200, r.text

    partos = _partos_068(engine)
    assert len(partos) == 1
    assert partos[0].numero_cria_1 == "068-C1"
