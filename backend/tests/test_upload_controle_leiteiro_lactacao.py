"""
POST /upload/controle_leiteiro — checagem de lactação aberta.

Antes deste conserto, esta era a ÚNICA das 5 vias de entrada de
`ControleLeiteiro` sem checagem nenhuma de `Lactacao` aberta na data: o
lançamento manual (estrito), a planilha de confirmação, o app mobile e o bot
do Telegram já recusavam/ignoravam uma vaca sem lactação (ver
`_gravar_controles` em `api/routers/producao.py` e `test_lactacao.py`), mas a
reimportação bruta do CSV do Ideagri inseria a linha sem checar nada. Caso
real: novilha "14" (primeira gestação, sem Parto/Lactacao nenhum) tinha
controles leiteiros lançados só por essa via.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ControleLeiteiro, Lactacao


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
        c._engine = engine  # type: ignore[attr-defined]
        yield c

    main.app.dependency_overrides.clear()


def _csv(linhas: list[str]) -> bytes:
    cabecalho = "NUMERO;NOME_RESUMIDO;RGD;RACA;DATA_LEITE;PESO_TOTAL_LEITE;DATA_ULTIMO_PARTO;DATA_BAIXA"
    return "\n".join([cabecalho, *linhas]).encode("windows-1252")


def test_matriz_sem_lactacao_aberta_e_ignorada_nao_gravada(client):
    """A novilha "14" — sem Parto/Lactacao nenhum — não pode ganhar
    ControleLeiteiro só porque a planilha bruta do Ideagri trouxe a linha."""
    engine = client._engine  # type: ignore[attr-defined]
    with Session(engine) as s:
        s.add(Animal(numero="14", raca="Girolando", ativo=True))
        s.commit()

    csv_bytes = _csv(["14;;;Girolando;08/07/2026;18,5;;"])
    r = client.post("/upload/controle_leiteiro", files={"file": ("cl.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["registros"] == 0
    assert corpo["ignorados"] == 1

    with Session(engine) as s:
        assert s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "14")).first() is None


def test_matriz_com_lactacao_aberta_e_gravada_normalmente(client):
    engine = client._engine  # type: ignore[attr-defined]
    with Session(engine) as s:
        s.add(Animal(numero="131", raca="Girolando", ativo=True))
        s.add(Lactacao(numero_matriz="131", data_inicio=date(2026, 6, 19)))
        s.commit()

    csv_bytes = _csv(["131;;;Girolando;08/07/2026;22,3;19/06/2026;"])
    r = client.post("/upload/controle_leiteiro", files={"file": ("cl.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["registros"] == 1
    assert corpo["ignorados"] == 0

    with Session(engine) as s:
        reg = s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "131")).one()
        assert reg.producao_kg == 22.3


def test_mistura_de_matrizes_grava_so_quem_tem_lactacao_aberta(client):
    """Uma linha ruim não pode derrubar o arquivo inteiro — mesma filosofia
    de `_gravar_controles(estrito=False)` na planilha de confirmação."""
    engine = client._engine  # type: ignore[attr-defined]
    with Session(engine) as s:
        s.add(Animal(numero="14", raca="Girolando", ativo=True))
        s.add(Animal(numero="131", raca="Girolando", ativo=True))
        s.add(Lactacao(numero_matriz="131", data_inicio=date(2026, 6, 19)))
        s.commit()

    csv_bytes = _csv([
        "14;;;Girolando;08/07/2026;18,5;;",
        "131;;;Girolando;08/07/2026;22,3;19/06/2026;",
    ])
    r = client.post("/upload/controle_leiteiro", files={"file": ("cl.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["registros"] == 1
    assert corpo["ignorados"] == 1
    assert corpo["vacas"] == 1

    with Session(engine) as s:
        numeros = {r_.numero_matriz for r_ in s.exec(select(ControleLeiteiro)).all()}
        assert numeros == {"131"}


def test_reimportacao_reaplica_a_checagem_sempre(client):
    """"Apaga tudo e reimporta" é o comportamento normal deste endpoint — a
    checagem tem que valer em TODA reimportação, não só na primeira."""
    engine = client._engine  # type: ignore[attr-defined]
    with Session(engine) as s:
        s.add(Animal(numero="14", raca="Girolando", ativo=True))
        s.commit()

    csv_bytes = _csv(["14;;;Girolando;08/07/2026;18,5;;"])
    for _ in range(2):
        r = client.post("/upload/controle_leiteiro", files={"file": ("cl.csv", csv_bytes, "text/csv")})
        assert r.status_code == 200, r.text
        assert r.json()["ignorados"] == 1

    with Session(engine) as s:
        assert s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "14")).first() is None
