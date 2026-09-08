"""
Testes de POST/PUT /auth/usuarios — uma conta de login vincula a uma Pessoa já
cadastrada na fazenda (cada pessoa só pode estar vinculada a um único usuário
por vez), ver fazenda.api.routers.auth._validar_pessoa_ou_nome.

A fixture daqui NÃO cadastra fazenda nenhuma (tabela `fazenda` vazia), então
estes testes rodam do lado "multi-fazenda não provisionado" da linha divisória
(fazenda.auth.multifazenda_provisionado) — onde o caminho de `nome` livre, sem
Pessoa, ainda é aceito. A trava "todo usuário nasce dentro de uma fazenda", que
vale em qualquer ambiente com fazenda cadastrada (isto é: em produção), tem
arquivo próprio: tests/test_usuario_sempre_com_fazenda.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Pessoa, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        # /auth/usuarios (listar/criar/editar) é restrito ao proprietário
        # (exigir_dono) — o admin de teste precisa do e-mail do dono.
        s.add(Usuario(username="admin", nome="Admin", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.add(Pessoa(nome="João Silva", tipo="Funcionário"))
        s.add(Pessoa(nome="Maria Souza", tipo="Funcionário"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _login(c, username="admin"):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def _pessoa_id(engine, nome):
    with Session(engine) as s:
        return s.exec(select(Pessoa).where(Pessoa.nome == nome)).first().id


def test_criar_usuario_exige_pessoa_existente(client):
    c, engine = client
    token = _login(c)
    r = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": 9999, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_criar_usuario_deriva_nome_da_pessoa(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "João Silva")
    r = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["nome"] == "João Silva"
    assert dados["pessoa_id"] == pid
    assert dados["pessoa_nome"] == "João Silva"


def test_criar_usuario_sem_fazenda_usa_nome_livre(client):
    """Nome livre (sem pessoa_id) só continua aceito porque este banco não tem
    NENHUMA fazenda cadastrada — instalação anterior ao multi-fazenda, onde não
    há tenant a isolar (mesmo corte de fazenda.auth.multifazenda_provisionado).
    Havendo qualquer fazenda, este mesmo POST é recusado com
    auth.ERRO_USUARIO_SEM_FAZENDA — ver tests/test_usuario_sempre_com_fazenda.py.
    """
    c, engine = client
    token = _login(c)
    r = c.post(
        "/auth/usuarios",
        json={"username": "equipe_cowdata", "senha": "123", "nome": "Fulano da CowData", "papel": "admin", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["nome"] == "Fulano da CowData"
    assert dados["pessoa_id"] is None
    assert dados["pessoa_nome"] is None


def test_criar_usuario_sem_pessoa_id_nem_nome_e_rejeitado(client):
    c, engine = client
    token = _login(c)
    r = c.post(
        "/auth/usuarios",
        json={"username": "sememtudo", "senha": "123", "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_criar_usuario_rejeita_pessoa_ja_vinculada(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "João Silva")
    r1 = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    r2 = c.post(
        "/auth/usuarios",
        json={"username": "joao2", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 400
    assert "joao" in r2.json()["detail"]


def test_editar_usuario_associa_pessoa_retroativamente(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "Maria Souza")

    with Session(engine) as s:
        antigo = Usuario(username="legado", nome="Legado", senha_hash=hash_senha("123"), papel="operador")
        s.add(antigo)
        s.commit()
        s.refresh(antigo)
        legado_id = antigo.id

    r = c.put(
        f"/auth/usuarios/{legado_id}",
        json={"pessoa_id": pid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["pessoa_id"] == pid
    assert dados["nome"] == "Maria Souza"


def test_editar_usuario_rejeita_pessoa_ja_vinculada_a_outro(client):
    c, engine = client
    token = _login(c)
    pid_joao = _pessoa_id(engine, "João Silva")
    pid_maria = _pessoa_id(engine, "Maria Souza")

    c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid_joao, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    r_maria = c.post(
        "/auth/usuarios",
        json={"username": "maria", "senha": "123", "pessoa_id": pid_maria, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    maria_id = r_maria.json()["id"]

    r = c.put(
        f"/auth/usuarios/{maria_id}",
        json={"pessoa_id": pid_joao},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_editar_usuario_permite_manter_mesma_pessoa(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "João Silva")
    r_criado = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    user_id = r_criado.json()["id"]

    r = c.put(
        f"/auth/usuarios/{user_id}",
        json={"pessoa_id": pid, "email": "joao@x.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "joao@x.com"


def test_permissoes_vet_e_recria_nao_somem_ao_editar(client):
    """Regressão: 'vet' (Agenda do veterinário) e 'recria' ficavam fora do
    whitelist MODULOS em fazenda.auth e eram silenciosamente removidas de
    Usuario.permissoes em toda edição (mesmo uma edição sem relação com
    permissões), mesmo aparecendo marcadas no formulário."""
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "João Silva")
    r_criado = c.post(
        "/auth/usuarios",
        json={
            "username": "joao", "senha": "123", "pessoa_id": pid, "papel": "operador",
            "permissoes": ["agenda", "vet", "recria"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sorted(r_criado.json()["permissoes"]) == ["agenda", "recria", "vet"]
    user_id = r_criado.json()["id"]

    # Uma edição não relacionada (ex.: reenviando as mesmas permissões, como
    # o formulário do site faz ao salvar) não pode derrubar "vet"/"recria".
    r = c.put(
        f"/auth/usuarios/{user_id}",
        json={"permissoes": ["agenda", "vet", "recria"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert sorted(r.json()["permissoes"]) == ["agenda", "recria", "vet"]


def test_listar_usuarios_com_fazenda_selecionada_mostra_so_essa_fazenda(client):
    """Regressão: GET /auth/usuarios (Controle de Acesso) devolvia TODO
    Usuario do banco, de qualquer fazenda-cliente — bug real encontrado em
    produção via sessão de suporte CowData: "Fazenda Teste" via Controle de
    Acesso via /usuarios mostrava login de outra fazenda. Com fazenda_id
    selecionado no token, só entram usuários cuja Pessoa pertence a ela."""
    c, engine = client
    token = _login(c)
    with Session(engine) as s:
        from fazenda.models import Fazenda
        s.add(Fazenda(id=10, nome="Fazenda A"))
        s.add(Fazenda(id=20, nome="Fazenda B"))
        pessoa_a = Pessoa(nome="Funcionário A", tipo="Funcionário", fazenda_id=10)
        pessoa_b = Pessoa(nome="Funcionário B", tipo="Funcionário", fazenda_id=20)
        s.add(pessoa_a)
        s.add(pessoa_b)
        s.commit()
        s.refresh(pessoa_a)
        s.refresh(pessoa_b)
        pid_a, pid_b = pessoa_a.id, pessoa_b.id

    # TESTE CONSERTADO junto com a trava "todo usuário nasce dentro de uma
    # fazenda": estes dois POST rodavam com o token do admin SEM fazenda
    # selecionada, num banco que já tem fazenda cadastrada — ou seja, criavam
    # exatamente o usuário órfão que a trava passou a impedir (agora 409 de
    # get_fazenda_id_escrita: a sessão não sabe em que fazenda está). O
    # cenário que este teste quer continua idêntico — cada usuário na sua
    # fazenda —, só que agora criado de dentro de uma fazenda selecionada. A
    # fazenda do VÍNCULO vem da Pessoa (10 e 20, respectivamente), não deste
    # override, que só resolve "de onde o dono está criando".
    from fazenda.auth import get_fazenda_atual_id
    import main
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 10
    try:
        c.post(
            "/auth/usuarios",
            json={"username": "user_a", "senha": "123", "pessoa_id": pid_a, "papel": "operador", "permissoes": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        c.post(
            "/auth/usuarios",
            json={"username": "user_b", "senha": "123", "pessoa_id": pid_b, "papel": "operador", "permissoes": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        r = c.get("/auth/usuarios", headers={"Authorization": f"Bearer {token}"})
    finally:
        del main.app.dependency_overrides[get_fazenda_atual_id]
    assert r.status_code == 200
    usernames = {u["username"] for u in r.json()}
    assert "user_a" in usernames
    assert "user_b" not in usernames
