"""
Referência da curva de lactação por MESMA ordem de parto (`curva_referencia_
grupo_ordem_parto` na ficha do animal, `_curva_referencia_grupo_ordem_parto`
em `api/routers/animais.py`) — recorte mais fino que `curva_referencia_
rebanho`, que mistura primípara com vaca de 5ª cria.

Arquivo autocontido, seguindo o padrão de `test_isolamento_animal.py`
(fixture `client` + `_como_fazenda`) para poder testar isolamento por
fazenda_id.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, ControleLeiteiro, Parto


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    # GET /animais/* exige módulo "rebanho" contratado E ATIVO pela fazenda
    # (ver main.py: exigir_modulo_contratado("rebanho")) sempre que
    # get_fazenda_atual_id devolve um fazenda_id não-nulo — precisa deste
    # contrato para as duas fazendas usadas no teste de isolamento (1 e 2),
    # senão toda chamada volta 403 antes de chegar na lógica que queremos
    # testar (mesmo padrão de test_isolamento_animal.py).
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="rebanho", preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _semear_animal_com_partos_e_controle(
    s: Session, numero: str, fazenda_id: int, datas_partos: list[date],
    del_controle: int, kg_controle: float, data_controle: date,
):
    """Um animal com N partos produtivos e UM controle leiteiro (na faixa de
    DEL desejada) depois do último parto — o bastante para testar o
    agrupamento por ordem de parto sem ruído de outras variáveis."""
    animal = Animal(numero=numero, sexo="F", ativo=True, fazenda_id=fazenda_id)
    s.add(animal)
    for d in datas_partos:
        s.add(Parto(numero_matriz=numero, data_parto=d, fazenda_id=fazenda_id))
    s.add(ControleLeiteiro(
        numero_matriz=numero, data_controle=data_controle, producao_kg=kg_controle,
        del_no_controle=del_controle, fazenda_id=fazenda_id,
    ))


class TestGrupoPorOrdemDeParto:
    def test_animal_sem_nenhum_parto_nao_tem_grupo(self, client):
        """Uma novilha (nunca pariu) não tem ordem de parto para comparar —
        o campo vem None, não um grupo qualquer."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", sexo="F", ativo=True, fazenda_id=1))
            s.commit()

        r = c.get("/animais/1/ficha")
        assert r.status_code == 200
        assert r.json()["curva_referencia_grupo_ordem_parto"] is None

    def test_agrupa_so_com_vacas_da_mesma_ordem_de_parto(self, client):
        """Animal-alvo com 2 partos (3ª... não, 2ª cria em curso) só deve
        entrar no grupo com outra vaca também de 2ª cria — a de 1ª cria
        (primípara) fica de fora."""
        c, engine = client
        with Session(engine) as s:
            # Alvo: 2 partos, controle 30 kg no DEL 40 (faixa 31-60).
            _semear_animal_com_partos_e_controle(
                s, "A", 1, [date(2020, 1, 1), date(2023, 1, 1)],
                del_controle=40, kg_controle=30.0, data_controle=date(2023, 2, 10),
            )
            # Peer também de 2ª cria — mesma faixa de DEL.
            _semear_animal_com_partos_e_controle(
                s, "B", 1, [date(2019, 6, 1), date(2023, 1, 15)],
                del_controle=40, kg_controle=34.0, data_controle=date(2023, 2, 24),
            )
            # Primípara (1 parto só) — não deve entrar no grupo do animal A.
            _semear_animal_com_partos_e_controle(
                s, "C", 1, [date(2023, 1, 1)],
                del_controle=40, kg_controle=20.0, data_controle=date(2023, 2, 10),
            )
            s.commit()

        r = c.get("/animais/A/ficha")
        assert r.status_code == 200
        grupo = r.json()["curva_referencia_grupo_ordem_parto"]
        assert grupo is not None
        faixa = next(f for f in grupo if f["faixa_del"] == "31-60")
        # Só A (30) e B (34) — a primípara C (20) fica fora e não puxa a
        # média para baixo.
        assert faixa["controles"] == 2
        assert faixa["media_kg"] == pytest.approx(32.0)

    def test_animal_sem_ordem_de_parto_conhecida_nao_entra_no_grupo_de_ninguem(self, client):
        """Um `ControleLeiteiro` órfão (animal sem nenhum `Parto` lançado) não
        pode ser incluído por engano no grupo de outra ordem de parto — fica
        de fora de qualquer agrupamento."""
        c, engine = client
        with Session(engine) as s:
            _semear_animal_com_partos_e_controle(
                s, "A", 1, [date(2020, 1, 1), date(2023, 1, 1)],
                del_controle=40, kg_controle=30.0, data_controle=date(2023, 2, 10),
            )
            # "D" nunca teve parto lançado, mas tem controle leiteiro — não
            # tem ordem de parto conhecida, não pode entrar no grupo de A.
            animal_d = Animal(numero="D", sexo="F", ativo=True, fazenda_id=1)
            s.add(animal_d)
            s.add(ControleLeiteiro(
                numero_matriz="D", data_controle=date(2023, 2, 10), producao_kg=999.0,
                del_no_controle=40, fazenda_id=1,
            ))
            s.commit()

        r = c.get("/animais/A/ficha")
        grupo = r.json()["curva_referencia_grupo_ordem_parto"]
        faixa = next(f for f in grupo if f["faixa_del"] == "31-60")
        # Só o próprio A — "D" (999 kg) nunca entra.
        assert faixa["controles"] == 1
        assert faixa["media_kg"] == pytest.approx(30.0)

    def test_isolamento_por_fazenda(self, client):
        """O grupo de referência da fazenda #1 não pode incluir controle
        leiteiro de uma vaca da fazenda #2, mesmo com a mesma ordem de
        parto e a mesma faixa de DEL."""
        c, engine = client
        with Session(engine) as s:
            _semear_animal_com_partos_e_controle(
                s, "A", 1, [date(2020, 1, 1), date(2023, 1, 1)],
                del_controle=40, kg_controle=30.0, data_controle=date(2023, 2, 10),
            )
            # Mesma ordem de parto (2), mesma faixa de DEL, OUTRA fazenda —
            # um valor bem fora (999) que denunciaria vazamento se entrasse.
            _semear_animal_com_partos_e_controle(
                s, "E", 2, [date(2020, 1, 1), date(2023, 1, 1)],
                del_controle=40, kg_controle=999.0, data_controle=date(2023, 2, 10),
            )
            s.commit()

        r = c.get("/animais/A/ficha")
        grupo = r.json()["curva_referencia_grupo_ordem_parto"]
        faixa = next(f for f in grupo if f["faixa_del"] == "31-60")
        assert faixa["controles"] == 1
        assert faixa["media_kg"] == pytest.approx(30.0)

    def test_grupo_none_quando_nenhum_peer_sobra(self, client):
        """Animal alvo com ordem de parto própria, mas sem nenhuma outra vaca
        (nem ela mesma acumula mais de um controle) na mesma ordem —
        continua tendo o SEU PRÓPRIO controle no grupo (o grupo inclui o
        próprio animal), então só fica None se nem o alvo tiver controle."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="A", sexo="F", ativo=True, fazenda_id=1))
            s.add(Parto(numero_matriz="A", data_parto=date(2023, 1, 1), fazenda_id=1))
            # Sem NENHUM ControleLeiteiro para A.
            s.commit()

        r = c.get("/animais/A/ficha")
        assert r.json()["curva_referencia_grupo_ordem_parto"] is None
