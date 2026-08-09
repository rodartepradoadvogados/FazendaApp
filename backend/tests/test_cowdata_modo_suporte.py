"""
Painel CowData como instância à parte: administradores CowData
(EMAILS_DONO_EQUIVALENTE) escolhem, ao logar, entre entrar DIRETO numa
fazenda vinculada (administrador — acesso de sempre, sem restrição) ou
entrar pelo Painel CowData (e, de lá, abrir uma fazenda como SUPORTE —
via Cofre de Acesso, token com validade curta e ações destrutivas
bloqueadas). Ver fazenda/api/routers/auth.py::login, cofre_acesso.py e
main.py::_bloquear_modo_suporte.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Fazenda, Usuario
from fazenda.models.multitenant import UsuarioFazenda


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fazenda = Fazenda(nome="Fazenda Jairo Nasser", ativa=True)
        s.add(fazenda)
        s.commit()
        s.refresh(fazenda)

        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        sem_vinculo = Usuario(username="dono-sem-vinculo", nome="Dono sem vínculo", senha_hash=hash_senha("123"), papel="admin", email="alexandrescarpazoo@yahoo.com.br")
        comum = Usuario(username="admin-comum", nome="Admin comum", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com")
        s.add_all([dono, sem_vinculo, comum])
        s.commit()
        s.refresh(dono)
        s.refresh(comum)

        s.add(UsuarioFazenda(usuario_id=dono.id, fazenda_id=fazenda.id, contratante=True))
        s.add(UsuarioFazenda(usuario_id=comum.id, fazenda_id=fazenda.id))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _fazenda_id(client) -> int:
    r = client.post("/auth/login", json={"username": "admin-comum", "senha": "123"})
    return r.json()["fazenda_atual"]["id"]


def test_dono_com_vinculo_sempre_ve_o_escolhedor(client):
    """Mesmo com só 1 fazenda vinculada — diferente do piloto multi-fazenda
    comum (que só mostra a tela com >1) — o dono-equivalente sempre escolhe
    conscientemente entre a fazenda e o Painel CowData."""
    r = client.post("/auth/login", json={"username": "dono", "senha": "123"})
    assert r.status_code == 200
    data = r.json()
    assert data["selecao_fazenda_necessaria"] is True
    nomes = {f["nome"] for f in data["fazendas_disponiveis"]}
    assert "Fazenda Jairo Nasser" in nomes
    assert "Painel CowData" in nomes
    cowdata = next(f for f in data["fazendas_disponiveis"] if f["nome"] == "Painel CowData")
    assert cowdata["cowdata"] is True
    assert cowdata["id"] == 0
    # Sem fazenda_atual — token emitido já vem sem "fid" até escolher.
    assert "fazenda_atual" not in data


def test_admin_comum_com_1_fazenda_continua_auto_selecionando(client):
    """Regressão: usuário comum (não dono-equivalente) com 1 fazenda vinculada
    continua exatamente como antes — sem tela de escolha nenhuma."""
    r = client.post("/auth/login", json={"username": "admin-comum", "senha": "123"})
    assert r.status_code == 200
    data = r.json()
    assert "selecao_fazenda_necessaria" not in data
    assert data["fazenda_atual"]["nome"] == "Fazenda Jairo Nasser"


def test_dono_sem_nenhum_vinculo_nao_forca_escolhedor(client):
    """Rede de segurança: dono-equivalente sem UsuarioFazenda gravado (só o
    bypass por e-mail) mantém o comportamento de sempre — nunca arrisca
    travar quem só tinha esse acesso indireto."""
    r = client.post("/auth/login", json={"username": "dono-sem-vinculo", "senha": "123"})
    assert r.status_code == 200
    data = r.json()
    assert "selecao_fazenda_necessaria" not in data
    r2 = client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {data['token']}"})
    assert r2.status_code == 200


def test_escolher_fazenda_direto_da_acesso_de_administrador_sem_restricao(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post("/auth/selecionar-fazenda", json={"fazenda_id": fid}, headers={"Authorization": f"Bearer {login['token']}"})
    assert r.status_code == 200
    token = r.json()["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["suporte_ativo"] is False
    assert me["sessao_suporte_id"] is None
    assert me["fazenda_atual"]["nome"] == "Fazenda Jairo Nasser"

    # DELETE em qualquer rota some/existente não é bloqueado pelo middleware
    # (o 404 de rota inexistente prova que passou direto, sem a mensagem
    # 403 do modo suporte).
    r = client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_entrar_pelo_painel_cowdata_e_abrir_fazenda_gera_token_de_suporte(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    # "Escolher Painel CowData" no frontend = simplesmente não chamar
    # /auth/selecionar-fazenda — o token do login (sem fid) já serve.
    token_cowdata = login["token"]
    r = client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {token_cowdata}"})
    assert r.status_code == 200

    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Auxílio/treinamento de usuário", "assunto_chamado": "Dúvida do cliente sobre relatório"},
        headers={"Authorization": f"Bearer {token_cowdata}"},
    )
    assert r.status_code == 200
    pedido = r.json()
    assert pedido["status"] == "aprovado"
    assert "token" in pedido and pedido["token"]
    assert pedido["sessao_id"] is not None
    assert pedido["sessao_expira_em"]

    token_suporte = pedido["token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token_suporte}"}).json()
    assert me["suporte_ativo"] is True
    assert me["sessao_suporte_id"] is not None
    assert me["fazenda_atual"]["nome"] == "Fazenda Jairo Nasser"


def _token_suporte(client) -> str:
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Configurar parâmetros da fazenda", "assunto_chamado": "Ajuste de parâmetro de teste"},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    return r.json()["token"]


def test_modo_suporte_bloqueia_delete(client):
    token = _token_suporte(client)
    r = client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "modo suporte" in r.json()["detail"].lower()


def test_modo_suporte_bloqueia_escrita_em_financeiro(client):
    token = _token_suporte(client)
    r = client.post("/financeiro/qualquer-coisa", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "modo suporte" in r.json()["detail"].lower()


def test_modo_suporte_nao_bloqueia_leitura(client):
    token = _token_suporte(client)
    r = client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_modo_suporte_consegue_encerrar_a_propria_sessao(client):
    """A própria rota de encerrar sessão do Cofre não pode ficar bloqueada
    pelo middleware — senão quem entra em modo suporte fica preso até expirar."""
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    pedido = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Diagnosticar erro relatado", "assunto_chamado": "Erro relatado pelo cliente"},
        headers={"Authorization": f"Bearer {login['token']}"},
    ).json()
    token_suporte = pedido["token"]
    sessoes = client.get("/painel-cowdata/cofre/sessoes-ativas", headers={"Authorization": f"Bearer {login['token']}"}).json()
    sessao_id = next(s["id"] for s in sessoes if s["fazenda_id"] == fid)

    r = client.post(f"/painel-cowdata/cofre/sessoes/{sessao_id}/encerrar", headers={"Authorization": f"Bearer {token_suporte}"})
    assert r.status_code == 200
    assert r.json()["encerrada_em"] is not None


def test_pedido_exige_assunto_chamado(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Diagnosticar erro relatado", "assunto_chamado": "   "},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert r.status_code == 400
    assert "assunto" in r.json()["detail"].lower()


def test_pedido_rejeita_motivo_fora_da_lista(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Motivo qualquer inventado", "assunto_chamado": "Teste"},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert r.status_code == 400


def test_pedido_e_sessao_trazem_protocolo_e_assunto(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    pedido = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Incidente de segurança", "assunto_chamado": "Verificar login suspeito", "observacao": "Relatado por e-mail"},
        headers={"Authorization": f"Bearer {login['token']}"},
    ).json()
    assert pedido["protocolo"] == f"SUP-{pedido['id']:06d}"
    assert pedido["assunto_chamado"] == "Verificar login suspeito"
    assert pedido["observacao"] == "Relatado por e-mail"

    sessoes = client.get("/painel-cowdata/cofre/sessoes-ativas", headers={"Authorization": f"Bearer {login['token']}"}).json()
    sessao = next(s for s in sessoes if s["fazenda_id"] == fid)
    assert sessao["protocolo"] == pedido["protocolo"]
    assert sessao["assunto_chamado"] == "Verificar login suspeito"


def test_fazendas_cofre_traz_plano_e_modulos(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    r = client.get("/painel-cowdata/cofre/fazendas", headers={"Authorization": f"Bearer {login['token']}"})
    assert r.status_code == 200
    fazenda = r.json()[0]
    assert "plano_nome" in fazenda
    assert "modulos" in fazenda
    assert isinstance(fazenda["modulos"], list)


def test_acoes_de_suporte_registram_escrita_bloqueada_e_permitida(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    token_suporte = _token_suporte(client)

    # DELETE é sempre bloqueado — vira uma linha "bloqueada" na auditoria.
    client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token_suporte}"})
    # POST fora de prefixo sensível passa (o 404 é da rota inexistente, não
    # do middleware) — vira uma linha "permitida", com o status real (404).
    client.post("/rota-inofensiva-qualquer", json={}, headers={"Authorization": f"Bearer {token_suporte}"})

    r = client.get("/painel-cowdata/cofre/acoes", headers={"Authorization": f"Bearer {login['token']}"})
    assert r.status_code == 200
    acoes = r.json()
    bloqueadas = [a for a in acoes if a["metodo"] == "DELETE" and a["caminho"] == "/rota-que-nao-existe"]
    permitidas = [a for a in acoes if a["metodo"] == "POST" and a["caminho"] == "/rota-inofensiva-qualquer"]
    assert len(bloqueadas) == 1 and bloqueadas[0]["bloqueado"] is True
    assert len(permitidas) == 1 and permitidas[0]["bloqueado"] is False and permitidas[0]["status_code"] == 404
    assert bloqueadas[0]["protocolo"] is not None


def test_acesso_a_minha_fazenda_acoes_exige_contratante_ou_dono(client):
    fid = _fazenda_id(client)
    token_suporte = _token_suporte(client)
    client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token_suporte}"})

    # O dono, com a fazenda selecionada, enxerga a auditoria da fazenda.
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    sel = client.post("/auth/selecionar-fazenda", json={"fazenda_id": fid}, headers={"Authorization": f"Bearer {login['token']}"}).json()
    r = client.get("/painel-cowdata/cofre/minha-fazenda/acoes", headers={"Authorization": f"Bearer {sel['token']}"})
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # Admin comum (vinculado, mas sem ser contratante) NÃO enxerga.
    login_comum = client.post("/auth/login", json={"username": "admin-comum", "senha": "123"}).json()
    r2 = client.get("/painel-cowdata/cofre/minha-fazenda/acoes", headers={"Authorization": f"Bearer {login_comum['token']}"})
    assert r2.status_code == 403
