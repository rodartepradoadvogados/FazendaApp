"""
Painel CowData > Cadastros globais — motivos/raças/grau de sangue/unidades de
estoque/tipos e métodos de serviço reprodutivo aplicados a todas as
fazendas-cliente de uma vez, ou só às selecionadas, sem precisar entrar em
cada uma via modo suporte. Ver fazenda/api/routers/painel_cowdata_cadastros.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Fazenda, MotivoBaixa, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Fazenda A", ativa=True)
        fb = Fazenda(nome="Fazenda B", ativa=True)
        inativa = Fazenda(nome="Fazenda Inativa", ativa=False)
        s.add_all([fa, fb, inativa])
        s.commit()
        s.refresh(fa)
        s.refresh(fb)
        s.refresh(inativa)
        fa_id, fb_id, inativa_id = fa.id, fb.id, inativa.id

        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        comum = Usuario(username="admin-comum", nome="Admin comum", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com")
        s.add_all([dono, comum])
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine, fa_id, fb_id, inativa_id
    main.app.dependency_overrides.clear()


def _login(c, username="dono"):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_nao_dono_sem_area_e_bloqueado(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c, "admin-comum")
    r = c.get("/painel-cowdata/cadastros/fazendas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_listar_fazendas_exclui_inativas(client):
    c, engine, fa_id, fb_id, inativa_id = client
    token = _login(c)
    r = c.get("/painel-cowdata/cadastros/fazendas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    ids = {f["id"] for f in r.json()}
    assert ids == {fa_id, fb_id}


def test_aplicar_sem_fazenda_ids_cria_em_todas_as_ativas(client):
    c, engine, fa_id, fb_id, inativa_id = client
    token = _login(c)
    r = c.post(
        "/painel-cowdata/cadastros/motivo_baixa/aplicar", json={"nome": "Morte"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == {"criados": 2, "atualizados": 0, "ja_existiam": 0, "total_fazendas": 2}
    with Session(engine) as s:
        nomes_fazenda = {m.fazenda_id for m in s.exec(select(MotivoBaixa)).all()}
        assert nomes_fazenda == {fa_id, fb_id}


def test_aplicar_com_fazenda_ids_restringe_ao_selecionado(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    r = c.post(
        "/painel-cowdata/cadastros/motivo_baixa/aplicar",
        json={"nome": "Descarte voluntário", "fazenda_ids": [fa_id]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["criados"] == 1
    with Session(engine) as s:
        linhas = s.exec(select(MotivoBaixa).where(MotivoBaixa.nome == "Descarte voluntário")).all()
        assert [linha.fazenda_id for linha in linhas] == [fa_id]


def test_aplicar_de_novo_nao_duplica(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    c.post("/painel-cowdata/cadastros/raca/aplicar", json={"nome": "Girolando"}, headers={"Authorization": f"Bearer {token}"})
    r2 = c.post("/painel-cowdata/cadastros/raca/aplicar", json={"nome": "Girolando"}, headers={"Authorization": f"Bearer {token}"})
    assert r2.json() == {"criados": 0, "atualizados": 0, "ja_existiam": 2, "total_fazendas": 2}


def test_desativar_reativa_ao_aplicar_de_novo(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    c.post("/painel-cowdata/cadastros/raca/aplicar", json={"nome": "Gir"}, headers={"Authorization": f"Bearer {token}"})
    r_desat = c.post(
        "/painel-cowdata/cadastros/raca/desativar", json={"nome": "Gir", "fazenda_ids": [fa_id]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_desat.json()["desativados"] == 1
    r_reaplicar = c.post(
        "/painel-cowdata/cadastros/raca/aplicar", json={"nome": "Gir", "fazenda_ids": [fa_id]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_reaplicar.json()["atualizados"] == 1


def test_grau_sangue_fracao_holandes_aplicada(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    r = c.post(
        "/painel-cowdata/cadastros/grau_sangue/aplicar",
        json={"nome": "1/2 Holandês x Gir", "fracao_holandes": 0.5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    listagem = c.get("/painel-cowdata/cadastros/grau_sangue", headers={"Authorization": f"Bearer {token}"}).json()
    item = next(i for i in listagem["itens"] if i["nome"] == "1/2 Holandês x Gir")
    assert item["fracao_holandes"] == 0.5
    assert item["total_fazendas"] == 2
    assert len(item["em_fazendas"]) == 2


def test_renomear_pula_fazenda_onde_nao_existe(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    c.post("/painel-cowdata/cadastros/motivo_movimentacao/aplicar", json={"nome": "Troca de lote", "fazenda_ids": [fa_id]}, headers={"Authorization": f"Bearer {token}"})
    r = c.put(
        "/painel-cowdata/cadastros/motivo_movimentacao/renomear",
        json={"nome_atual": "Troca de lote", "novo_nome": "Mudança de lote"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == {"renomeados": 1, "pulados_por_conflito": 0, "nao_encontrados": 1}


def test_metodo_servico_pula_fazenda_sem_o_tipo(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    # Tipo "IA" só na Fazenda A.
    c.post("/painel-cowdata/cadastros/tipo_servico/aplicar", json={"nome": "IA", "fazenda_ids": [fa_id]}, headers={"Authorization": f"Bearer {token}"})
    r = c.post(
        "/painel-cowdata/cadastros/metodo_servico/aplicar",
        json={"tipo_nome": "IA", "nome": "IATF"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == {"criados": 1, "atualizados": 0, "ja_existiam": 0, "sem_tipo_correspondente": 1, "total_fazendas": 2}
    listagem = c.get("/painel-cowdata/cadastros/metodo_servico/listar", headers={"Authorization": f"Bearer {token}"}).json()
    item = next(i for i in listagem["itens"] if i["nome"] == "IATF")
    assert item["em_fazendas"] == [fa_id]
