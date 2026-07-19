"""
Testes de:
- histórico de últimos acessos (3 mais recentes) em GET /auth/usuarios/acessos;
- GET /auditoria/opcoes e GET /auditoria/atividades — restritos ao
  proprietário (mesma regra de exigir_dono), consultando lançamentos por
  usuário em qualquer módulo.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import ContaGerencial, Sanidade, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.add(Usuario(username="outro-admin", nome="Outro", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com"))
        s.add(Usuario(username="operador", nome="Operador", senha_hash=hash_senha("123"), papel="operador"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _login(c, username):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_acessos_traz_ate_3_ultimos_por_usuario(client):
    c, _ = client
    # 4 logins seguidos do mesmo usuário — só os 3 mais recentes devem aparecer.
    for _ in range(4):
        token_operador = _login(c, "operador")
    token_dono = _login(c, "dono")

    r = c.get("/auth/usuarios/acessos", headers={"Authorization": f"Bearer {token_dono}"})
    assert r.status_code == 200
    por_username = {u["username"]: u for u in r.json()}
    assert len(por_username["operador"]["ultimos_acessos"]) == 3
    assert len(por_username["dono"]["ultimos_acessos"]) == 1
    # mais recente primeiro
    acessos = por_username["operador"]["ultimos_acessos"]
    assert acessos == sorted(acessos, reverse=True)


def _semear_lancamentos(engine):
    op_id = None
    with Session(engine) as s:
        op_id = s.exec(select(Usuario).where(Usuario.username == "operador")).first().id
        s.add(ContaGerencial(descricao="Compra de ração", codigo_conta="1.1", data_emissao=date(2026, 7, 1), usuario_id=op_id))
        s.add(ContaGerencial(descricao="Venda de leite", codigo_conta="4.1", data_emissao=date(2026, 7, 10), usuario_id=op_id))
        s.add(Sanidade(numero_matriz="123", produto="Vacina X", data_aplicacao=date(2026, 7, 5), usuario_id=op_id))
        s.commit()
    return op_id


def test_opcoes_liberado_para_dono(client):
    c, _ = client
    token = _login(c, "dono")
    r = c.get("/auditoria/opcoes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    dados = r.json()
    assert any(t["chave"] == "conta_gerencial" for t in dados["tipos"])
    assert {u["username"] for u in dados["usuarios"]} == {"dono", "outro-admin", "operador"}


def test_opcoes_bloqueado_para_outro_admin(client):
    c, _ = client
    token = _login(c, "outro-admin")
    r = c.get("/auditoria/opcoes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_atividades_retorna_lancamentos_do_usuario(client):
    c, engine = client
    op_id = _semear_lancamentos(engine)
    token = _login(c, "dono")

    r = c.get(f"/auditoria/atividades?usuario_id={op_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    dados = r.json()
    assert dados["total"] == 3
    chaves = {i["chave"] for i in dados["itens"]}
    assert chaves == {"conta_gerencial", "sanidade"}
    # mais recente primeiro
    datas = [i["data"] for i in dados["itens"]]
    assert datas == sorted(datas, reverse=True)


def test_atividades_filtra_por_tipo_e_periodo(client):
    c, engine = client
    op_id = _semear_lancamentos(engine)
    token = _login(c, "dono")

    r = c.get(
        f"/auditoria/atividades?usuario_id={op_id}&chaves=conta_gerencial&data_inicio=2026-07-05&data_fim=2026-07-31",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["total"] == 1
    assert dados["itens"][0]["resumo"].startswith("Venda de leite")


def test_atividades_bloqueado_para_operador(client):
    c, engine = client
    op_id = _semear_lancamentos(engine)
    token = _login(c, "operador")
    r = c.get(f"/auditoria/atividades?usuario_id={op_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
