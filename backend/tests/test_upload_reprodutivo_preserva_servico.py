"""
O upload do CSV reprodutivo não pode mais APAGAR o que só o app produz.

`_upsert_reprodutivo` deletava TODOS os `Servico` da fazenda a cada upload e
reinseria só o que vinha na planilha. Tudo que foi lançado no app e não existe
no CSV do Ideagri ia junto: a perda de prenhez lançada pelo produtor (data E
motivo), o retoque/reconfirmação marcados pelo veterinário, o tipo de sêmen e
o inseminador gravados na inseminação, e o carimbo de quem lançou.

O efeito prático era o pior possível para o bug que originou esta correção: o
produtor lançava o aborto, e o próximo upload de CSV apagava a perda de
prenhez em silêncio — a matriz voltava a constar como GESTANTE.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Servico

# Mesma matriz e mesma DATA DE SERVIÇO nos dois uploads — é (matriz, data) que
# identifica a mesma inseminação dos dois lados.
CSV_REPRO = (
    "NUMERO DA MATRIZ;ORDEM DE PARTO;DATA DO SERVICO;TIPO DO SERVICO;DIAGNOSTICO\n"
    "014;2;20/06/2025;IA;POSITIVO\n"
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
            s.add(Animal(numero="014", ativo=True, sexo="F"))
            s.commit()
        c._engine = engine  # type: ignore[attr-defined]
        yield c

    main.app.dependency_overrides.clear()


def test_reupload_preserva_perda_de_prenhez_lancada_no_app(client):
    """(e) do plano de verificação."""
    engine = client._engine  # type: ignore[attr-defined]
    assert client.post("/upload/reprodutivo", files={"file": ("repro.csv", CSV_REPRO, "text/csv")}).status_code == 200

    # O produtor lança o aborto pelo app: perda de prenhez + motivo no serviço.
    with Session(engine) as s:
        servico = s.exec(select(Servico).where(Servico.numero_matriz == "014")).one()
        servico.data_perda_prenhez = date(2025, 9, 1)
        servico.motivo_perda_prenhez = "aborto"
        servico.tipo_semen = "sexado"
        servico.inseminador = "João"
        servico.retoque = True
        servico.data_reconfirmacao = date(2025, 8, 20)
        servico.diagnostico_reconfirmacao = "POSITIVO"
        s.add(servico)
        s.commit()

    # Novo upload do MESMO CSV (que não traz nada disso).
    assert client.post("/upload/reprodutivo", files={"file": ("repro.csv", CSV_REPRO, "text/csv")}).status_code == 200

    with Session(engine) as s:
        servico = s.exec(select(Servico).where(Servico.numero_matriz == "014")).one()
        assert servico.data_perda_prenhez == date(2025, 9, 1), "o upload apagou a perda de prenhez do app"
        assert servico.motivo_perda_prenhez == "aborto"
        assert servico.tipo_semen == "sexado"
        assert servico.inseminador == "João"
        assert servico.retoque is True
        assert servico.data_reconfirmacao == date(2025, 8, 20)
        assert servico.diagnostico_reconfirmacao == "POSITIVO"


def test_csv_continua_mandando_no_que_ele_traz(client):
    """A planilha É a fonte para o que ela cobre: o guardado só preenche o que
    veio VAZIO do CSV. Aqui o diagnóstico vem preenchido no CSV e deve valer o
    do CSV, não um valor antigo."""
    engine = client._engine  # type: ignore[attr-defined]
    assert client.post("/upload/reprodutivo", files={"file": ("repro.csv", CSV_REPRO, "text/csv")}).status_code == 200

    with Session(engine) as s:
        servico = s.exec(select(Servico).where(Servico.numero_matriz == "014")).one()
        servico.diagnostico = "NEGATIVO"
        s.add(servico)
        s.commit()

    csv_positivo = (
        "NUMERO DA MATRIZ;ORDEM DE PARTO;DATA DO SERVICO;TIPO DO SERVICO;DIAGNOSTICO\n"
        "014;2;20/06/2025;IA;POSITIVO\n"
    ).encode("windows-1252")
    assert client.post("/upload/reprodutivo", files={"file": ("repro.csv", csv_positivo, "text/csv")}).status_code == 200

    with Session(engine) as s:
        assert s.exec(select(Servico).where(Servico.numero_matriz == "014")).one().diagnostico == "POSITIVO"
