"""
Login + permissões de um membro da Equipe CowData no próprio Painel CowData
(ago/2026) — ver fazenda/models/equipe_cowdata_acesso.py,
fazenda/api/routers/painel_cowdata.py e fazenda/auth.py::
exigir_area_painel_cowdata. Cobre: criação do login (só o dono pode),
login do membro cai na tela de escolha com "Painel CowData" mesmo sem
nenhuma fazenda vinculada, e as áreas liberadas controlam o que ele acessa.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.api.routers.painel_cowdata import seed_cowdata_empresa
from fazenda.models import Fazenda, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        outro_admin = Usuario(username="outro-admin", nome="Outro admin", senha_hash=hash_senha("123"), papel="admin", email="admin-qualquer@x.com")
        s.add_all([dono, outro_admin])
        s.commit()
        # A seed de verdade só roda no startup do app, contra o engine de
        # produção (main.py) — o TestClient isolado precisa da sua própria
        # fazenda "CowData (empresa)" + cargos pra POST /equipe/pessoas funcionar.
        seed_cowdata_empresa(s)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _token_dono(client) -> str:
    return client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()["token"]


def _criar_membro_com_login(client, token_dono: str, areas: list[str], **extra_perm) -> dict:
    pessoa = client.post(
        "/painel-cowdata/equipe/pessoas",
        json={"nome": "Maria Consultora", "cargo": "Consultor"},
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()
    payload = {
        "username": "maria.consultora", "email": "maria@x.com", "senha": "senha123",
        "areas": areas, **extra_perm,
    }
    usuario = client.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario", json=payload,
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()
    return {"pessoa": pessoa, "usuario": usuario}


def test_criar_login_de_equipe_exige_dono(client):
    token_dono = _token_dono(client)
    pessoa = client.post(
        "/painel-cowdata/equipe/pessoas", json={"nome": "Fulano", "cargo": "Suporte"},
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()

    token_outro_admin = client.post("/auth/login", json={"username": "outro-admin", "senha": "123"}).json()["token"]
    r = client.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario",
        json={"username": "fulano", "email": "f@x.com", "senha": "123456", "areas": ["equipe"]},
        headers={"Authorization": f"Bearer {token_outro_admin}"},
    )
    assert r.status_code == 403


def test_login_de_membro_cowdata_mostra_escolhedor_mesmo_sem_fazenda(client):
    token_dono = _token_dono(client)
    _criar_membro_com_login(client, token_dono, areas=["equipe"])

    r = client.post("/auth/login", json={"username": "maria.consultora", "senha": "senha123"})
    assert r.status_code == 200
    data = r.json()
    assert data["usuario"]["eh_equipe_cowdata"] is True
    assert data["usuario"]["areas_painel_cowdata"] == ["equipe"]
    assert data["selecao_fazenda_necessaria"] is True
    opcoes = data["fazendas_disponiveis"]
    assert len(opcoes) == 1
    assert opcoes[0]["cowdata"] is True
    assert "fazenda_atual" not in data


def test_membro_com_area_equipe_acessa_equipe_mas_nao_financeiro(client):
    token_dono = _token_dono(client)
    _criar_membro_com_login(client, token_dono, areas=["equipe"])
    token = client.post("/auth/login", json={"username": "maria.consultora", "senha": "senha123"}).json()["token"]

    r_equipe = client.get("/painel-cowdata/equipe/pessoas", headers={"Authorization": f"Bearer {token}"})
    assert r_equipe.status_code == 200

    r_financeiro = client.get("/painel-cowdata/financeiro/categorias", headers={"Authorization": f"Bearer {token}"})
    assert r_financeiro.status_code == 403


def test_membro_com_area_cofre_acessa_suporte(client):
    token_dono = _token_dono(client)
    _criar_membro_com_login(client, token_dono, areas=["cofre"])
    token = client.post("/auth/login", json={"username": "maria.consultora", "senha": "senha123"}).json()["token"]

    r = client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    r_equipe = client.get("/painel-cowdata/equipe/pessoas", headers={"Authorization": f"Bearer {token}"})
    assert r_equipe.status_code == 403


def test_membro_sem_nenhuma_area_fica_bloqueado_em_tudo(client):
    token_dono = _token_dono(client)
    _criar_membro_com_login(client, token_dono, areas=[])
    token = client.post("/auth/login", json={"username": "maria.consultora", "senha": "senha123"}).json()["token"]

    assert client.get("/painel-cowdata/equipe/pessoas", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get("/painel-cowdata/financeiro/categorias", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_editar_permissoes_reflete_no_proximo_login(client):
    token_dono = _token_dono(client)
    criado = _criar_membro_com_login(client, token_dono, areas=["equipe"])
    pessoa_id = criado["pessoa"]["id"]

    r = client.put(
        f"/painel-cowdata/equipe/pessoas/{pessoa_id}/usuario",
        json={
            "username": "maria.consultora", "email": "maria@x.com", "areas": ["equipe", "cofre"],
            "pode_acessar_fazendas": True, "pode_vincular_usuarios": True,
        },
        headers={"Authorization": f"Bearer {token_dono}"},
    )
    assert r.status_code == 200
    assert set(r.json()["areas"]) == {"equipe", "cofre"}
    assert r.json()["pode_vincular_usuarios"] is True

    token = client.post("/auth/login", json={"username": "maria.consultora", "senha": "senha123"}).json()["token"]
    assert client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_subpermissoes_de_fazendas_exigem_pode_acessar_fazendas(client):
    token_dono = _token_dono(client)
    criado = _criar_membro_com_login(
        client, token_dono, areas=["equipe"],
        pode_acessar_fazendas=False, pode_vincular_usuarios=True,  # tentativa inconsistente
    )
    # O backend zera as sub-permissões quando pode_acessar_fazendas é False,
    # mesmo que o cliente tenha mandado True numa delas.
    assert criado["usuario"]["pode_acessar_fazendas"] is False
    assert criado["usuario"]["pode_vincular_usuarios"] is False


def test_nao_pode_criar_dois_logins_para_o_mesmo_membro(client):
    token_dono = _token_dono(client)
    criado = _criar_membro_com_login(client, token_dono, areas=["equipe"])
    pessoa_id = criado["pessoa"]["id"]

    r = client.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa_id}/usuario",
        json={"username": "outro.login", "email": "x@x.com", "senha": "123456", "areas": ["equipe"]},
        headers={"Authorization": f"Bearer {token_dono}"},
    )
    assert r.status_code == 400
