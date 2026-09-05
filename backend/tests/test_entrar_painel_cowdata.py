"""
POST /auth/entrar-painel-cowdata e GET /auth/contas-disponiveis — "tela-eixo"
de troca de conta (ver frontend/components/EscolherConta.tsx e
frontend/app/escolher-conta/page.tsx).

O ponto delicado: o Painel CowData opera com token SEM a claim "fid" (ver
fazenda/auth.py::get_fazenda_atual_id). No login isso é de graça — a opção
"Painel CowData" só navega usando o token que POST /auth/login já emitiu
sem fid. Mas quem JÁ escolheu uma fazenda antes (token COM fid) e pede para
trocar para o Painel CowData no meio da sessão precisa de um token NOVO,
sem fid — e reemitir um token sem fid para QUALQUER usuário autenticado
reabriria o buraco que a auditoria de segurança encontrou (token sem fid
tolera leitura/escrita cross-tenant em várias rotas ainda não migradas para
get_fazenda_id_escrita, ver docs/security-audit/achados.json). Por isso
este arquivo cobre, em especial, que um usuário comum NUNCA consegue esse
token por aqui.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, TOKEN_VALIDADE_LONGA_S, TOKEN_VALIDADE_S, _validar_token_payload, hash_senha
from fazenda.api.routers.painel_cowdata import seed_cowdata_empresa
from fazenda.models import Fazenda, Usuario, UsuarioFazenda


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        comum = Usuario(username="funcionario", nome="Funcionário", senha_hash=hash_senha("123"), papel="operador", email="func@x.com")
        # Vinculado a 2 fazendas — o único jeito de um usuário comum ter um
        # token SEM "fid" logo após o login (com 1 só, login auto-seleciona;
        # ver login()). Usado só por test_usuario_comum_sem_fid_tambem_
        # recebe_403, para não misturar com o cenário de 1 fazenda só que
        # as demais funções deste arquivo já cobrem via `funcionario`.
        comum_multi = Usuario(username="funcionario-multi", nome="Funcionário Multi", senha_hash=hash_senha("123"), papel="operador", email="func-multi@x.com")
        s.add_all([dono, comum, comum_multi])
        s.commit()
        # A fazenda-cliente que o dono/funcionário vão selecionar antes de
        # pedir a troca para o Painel CowData (token com "fid" gravado).
        fazenda = Fazenda(nome="Fazenda Jairo Nasser")
        fazenda2 = Fazenda(nome="Fazenda 2")
        s.add(fazenda); s.add(fazenda2)
        s.commit()
        s.refresh(dono); s.refresh(comum); s.refresh(comum_multi); s.refresh(fazenda); s.refresh(fazenda2)
        s.add(UsuarioFazenda(usuario_id=dono.id, fazenda_id=fazenda.id))
        s.add(UsuarioFazenda(usuario_id=comum.id, fazenda_id=fazenda.id))
        s.add(UsuarioFazenda(usuario_id=comum_multi.id, fazenda_id=fazenda.id))
        s.add(UsuarioFazenda(usuario_id=comum_multi.id, fazenda_id=fazenda2.id))
        s.commit()
        # A seed de verdade só roda no startup do app (main.py) — o
        # TestClient isolado precisa da própria fazenda "CowData (empresa)"
        # para eh_membro_equipe_cowdata funcionar via Pessoa vinculada.
        seed_cowdata_empresa(s)
        fazenda_id = fazenda.id

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, fazenda_id
    main.app.dependency_overrides.clear()


def _entrar_na_fazenda(client, username: str, fazenda_id: int, manter_conectado: bool = False) -> str:
    """Login + POST /auth/selecionar-fazenda — devolve um token COM "fid"
    gravado (o cenário em que o token do login por si só não serve mais
    para o Painel CowData)."""
    r = client.post("/auth/login", json={"username": username, "senha": "123", "manter_conectado": manter_conectado})
    assert r.status_code == 200
    token = r.json()["token"]
    r2 = client.post("/auth/selecionar-fazenda", json={"fazenda_id": fazenda_id}, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    novo_token = r2.json()["token"]
    assert _validar_token_payload(novo_token)["fid"] == fazenda_id
    return novo_token


def test_dono_reemite_token_sem_fid(client):
    c, fazenda_id = client
    token_com_fid = _entrar_na_fazenda(c, "dono", fazenda_id)

    r = c.post("/auth/entrar-painel-cowdata", headers={"Authorization": f"Bearer {token_com_fid}"})
    assert r.status_code == 200
    payload = _validar_token_payload(r.json()["token"])
    assert "fid" not in payload


def test_membro_equipe_cowdata_reemite_token_sem_fid(client):
    c, fazenda_id = client
    token_dono = c.post("/auth/login", json={"username": "dono", "senha": "123"}).json()["token"]
    pessoa = c.post(
        "/painel-cowdata/equipe/pessoas", json={"nome": "Maria Consultora", "cargo": "Consultor"},
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()
    c.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario",
        json={"username": "maria.consultora", "email": "maria@x.com", "senha": "senha123", "areas": ["equipe"]},
        headers={"Authorization": f"Bearer {token_dono}"},
    )

    # A membro da equipe não está vinculada a nenhuma fazenda-cliente —
    # login dela já sai sem fid (não passa por _entrar_na_fazenda). Simula
    # mesmo assim o pedido de reentrada no Painel CowData, que deve
    # continuar funcionando (é o cenário comum, não o de troca).
    token = c.post("/auth/login", json={"username": "maria.consultora", "senha": "senha123"}).json()["token"]
    r = c.post("/auth/entrar-painel-cowdata", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "fid" not in _validar_token_payload(r.json()["token"])


def test_usuario_comum_recebe_403(client):
    """O achado CRÍTICO que este endpoint não pode reabrir: um usuário
    comum (nem dono-equivalente, nem Equipe CowData) jamais pode obter um
    token sem "fid" por aqui — token sem fid desliga o filtro por fazenda
    em rotas ainda não migradas para get_fazenda_id_escrita."""
    c, fazenda_id = client
    token_com_fid = _entrar_na_fazenda(c, "funcionario", fazenda_id)

    r = c.post("/auth/entrar-painel-cowdata", headers={"Authorization": f"Bearer {token_com_fid}"})
    assert r.status_code == 403
    # E o token antigo (com fid) continua intacto — a tentativa negada não
    # deve ter efeito colateral nenhum sobre a sessão existente.
    assert _validar_token_payload(token_com_fid)["fid"] == fazenda_id


def test_usuario_comum_sem_fid_tambem_recebe_403(client):
    """Mesma trava mesmo quando o usuário comum tem um token SEM fid (aqui,
    vinculado a 2 fazendas — login não auto-seleciona, ver login() — e
    ainda não chamou /auth/selecionar-fazenda) — o critério é sempre quem é
    (dono-equivalente/Equipe CowData), nunca o formato do token que ele já
    tem."""
    c, _ = client
    r_login = c.post("/auth/login", json={"username": "funcionario-multi", "senha": "123"})
    token = r_login.json()["token"]
    assert "fid" not in _validar_token_payload(token)

    r = c.post("/auth/entrar-painel-cowdata", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_preserva_validade_longa_do_manter_conectado(client):
    c, fazenda_id = client
    token_com_fid = _entrar_na_fazenda(c, "dono", fazenda_id, manter_conectado=True)
    payload_intermediario = _validar_token_payload(token_com_fid)
    assert payload_intermediario["lembrar"] is True

    r = c.post("/auth/entrar-painel-cowdata", headers={"Authorization": f"Bearer {token_com_fid}"})
    assert r.status_code == 200
    payload = _validar_token_payload(r.json()["token"])
    assert payload["lembrar"] is True
    assert TOKEN_VALIDADE_LONGA_S - 5 <= payload["exp"] - time.time() <= TOKEN_VALIDADE_LONGA_S + 5


def test_sem_manter_conectado_usa_validade_padrao(client):
    c, fazenda_id = client
    token_com_fid = _entrar_na_fazenda(c, "dono", fazenda_id, manter_conectado=False)

    r = c.post("/auth/entrar-painel-cowdata", headers={"Authorization": f"Bearer {token_com_fid}"})
    assert r.status_code == 200
    payload = _validar_token_payload(r.json()["token"])
    assert "lembrar" not in payload
    assert TOKEN_VALIDADE_S - 5 <= payload["exp"] - time.time() <= TOKEN_VALIDADE_S + 5


def test_endpoint_exige_autenticacao(client):
    c, _ = client
    r = c.post("/auth/entrar-painel-cowdata")
    assert r.status_code == 401


# ── GET /auth/contas-disponiveis ──

def test_contas_disponiveis_lista_fazenda_e_painel_cowdata_para_dono(client):
    c, fazenda_id = client
    token = c.post("/auth/login", json={"username": "dono", "senha": "123"}).json()["token"]

    r = c.get("/auth/contas-disponiveis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    opcoes = r.json()["opcoes"]
    assert len(opcoes) == 2
    assert any(o.get("cowdata") for o in opcoes)
    assert any(o["id"] == fazenda_id for o in opcoes)


def test_contas_disponiveis_nao_mostra_painel_cowdata_para_usuario_comum(client):
    c, fazenda_id = client
    token = c.post("/auth/login", json={"username": "funcionario", "senha": "123"}).json()["token"]

    r = c.get("/auth/contas-disponiveis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    opcoes = r.json()["opcoes"]
    assert len(opcoes) == 1
    assert opcoes[0]["id"] == fazenda_id
    assert not opcoes[0].get("cowdata")


def test_contas_disponiveis_reflete_a_mesma_lista_do_login(client):
    """Mesmo critério do login (_opcoes_de_conta compartilhado) — chamar
    esta rota a qualquer momento depois não pode divergir do que o login já
    mostrou (ver docstring de _opcoes_de_conta em auth.py)."""
    c, fazenda_id = client
    r_login = c.post("/auth/login", json={"username": "dono", "senha": "123"})
    token = r_login.json()["token"]
    esperado = r_login.json()["fazendas_disponiveis"]

    r = c.get("/auth/contas-disponiveis", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["opcoes"] == esperado
