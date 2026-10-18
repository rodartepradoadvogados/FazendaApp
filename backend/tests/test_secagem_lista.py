"""
GET /producao/secagem-lista — a tabela da tela de Secagem em uma chamada só.

Regra de ouro: a previsão por vaca é a MESMA de GET /producao/secagem-info (a tela com uma só
vaca marcada mostra o /secagem-info; a tabela mostra a lista) — por isso há um teste de
consistência entre as duas rotas. Só entra quem tem lactação ABERTA hoje.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Lactacao, Secagem, Servico


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


def _vaca(s: Session, numero: str, *, inicio_lactacao: date | None, fazenda_id: int | None = None, **kw):
    s.add(Animal(numero=numero, raca=kw.pop("raca", "Girolando"), grupo_primario=kw.pop("grupo", "02 - Vacas Alta"),
                 ativo=True, fazenda_id=fazenda_id, **kw))
    if inicio_lactacao is not None:
        s.add(Lactacao(numero_matriz=numero, data_inicio=inicio_lactacao, fazenda_id=fazenda_id))


def _por_numero(corpo: dict) -> dict:
    return {a["numero_matriz"]: a for a in corpo["animais"]}


def test_so_entra_quem_tem_lactacao_aberta_com_del_ao_vivo(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        _vaca(s, "100", inicio_lactacao=hoje - timedelta(days=200))
        _vaca(s, "101", inicio_lactacao=None)                      # nunca lactou (novilha)
        s.add(Animal(numero="102", raca="Girolando", ativo=True, sexo="M"))   # macho
        _vaca(s, "103", inicio_lactacao=hoje - timedelta(days=300))
        s.add(Lactacao(numero_matriz="103", data_inicio=hoje - timedelta(days=300), data_fim=hoje - timedelta(days=10)))
        s.commit()

    r = c.get("/producao/secagem-lista")
    assert r.status_code == 200
    corpo = r.json()
    linhas = _por_numero(corpo)
    assert "100" in linhas and "101" not in linhas and "102" not in linhas
    assert linhas["100"]["del_atual"] == 200
    assert linhas["100"]["grupo_primario"] == "02 - Vacas Alta"
    # sem serviço positivo: previsão vazia, e isso não esconde a vaca
    assert linhas["100"]["data_prevista_secagem"] is None
    assert linhas["100"]["dias_gestacao"] is None


def test_previsao_e_a_mesma_do_secagem_info(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        # `del_dias` > 0 porque /secagem-info ainda decide "em lactação" pelo campo congelado; a lista usa a Lactacao aberta.
        _vaca(s, "200", inicio_lactacao=hoje - timedelta(days=150), del_dias=150)
        s.add(Servico(numero_matriz="200", data_servico=hoje - timedelta(days=210), diagnostico="POSITIVO", ordem_parto=2))
        s.commit()

    lista = _por_numero(c.get("/producao/secagem-lista").json())["200"]
    info = c.get("/producao/secagem-info", params={"numero_matriz": "200"}).json()
    assert lista["data_prevista_secagem"] == info["data_prevista_secagem"]
    assert lista["dias_gestacao"] == info["dias_gestacao"] == 210
    assert lista["deve_secar"] is True and info["deve_secar"] is True
    # Girolando 287 d − 60 d de período seco = secagem 227 dias depois da IA → faltam 17
    assert lista["dias_para_secagem"] == 17


def test_secagem_atrasada_tem_dias_negativos(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        _vaca(s, "300", inicio_lactacao=hoje - timedelta(days=300))
        s.add(Servico(numero_matriz="300", data_servico=hoje - timedelta(days=240), diagnostico="POSITIVO", ordem_parto=1))
        s.commit()
    linha = _por_numero(c.get("/producao/secagem-lista").json())["300"]
    assert linha["dias_para_secagem"] == 227 - 240


def test_novilha_de_primeira_cria_vem_com_motivo_de_nao_secar(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        _vaca(s, "400", inicio_lactacao=hoje - timedelta(days=100))
        s.add(Servico(numero_matriz="400", data_servico=hoje - timedelta(days=100), diagnostico="POSITIVO", ordem_parto=0))
        s.commit()
    linha = _por_numero(c.get("/producao/secagem-lista").json())["400"]
    assert linha["deve_secar"] is False
    assert "1ª cria" in linha["motivo_exclusao"]


def test_ultima_secagem_lancada(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        _vaca(s, "500", inicio_lactacao=hoje - timedelta(days=100))
        s.add(Secagem(numero_matriz="9", data_secagem=hoje - timedelta(days=30), motivo="rotina"))
        s.add(Secagem(numero_matriz="8", data_secagem=hoje - timedelta(days=5), motivo="rotina"))
        s.commit()
    corpo = c.get("/producao/secagem-lista").json()
    assert corpo["ultima_secagem"] == (hoje - timedelta(days=5)).isoformat()
    assert corpo["hoje"] == hoje.isoformat()


def test_isolamento_por_fazenda(client):
    import main
    from fazenda.auth import get_fazenda_atual_id

    c, engine = client
    hoje = date.today()
    from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
    from fazenda.models.planos import MODULOS_COMERCIAIS

    with Session(engine) as s:
        for fid in (1, 2):   # com fazenda selecionada, o middleware exige contrato ativo
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        _vaca(s, "600", inicio_lactacao=hoje - timedelta(days=100), fazenda_id=1)
        _vaca(s, "601", inicio_lactacao=hoje - timedelta(days=100), fazenda_id=2)
        s.add(Secagem(numero_matriz="601", data_secagem=hoje - timedelta(days=2), motivo="rotina", fazenda_id=2))
        s.commit()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    r = c.get("/producao/secagem-lista")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert set(_por_numero(corpo)) == {"600"}
    assert corpo["ultima_secagem"] is None   # a secagem da fazenda 2 não vaza
