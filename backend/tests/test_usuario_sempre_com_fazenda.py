"""
Trava "todo usuário nasce dentro de uma fazenda" — POST /auth/usuarios.

A regra do dono, textual: "não pode ser possível criar usuário sem fazenda. O
CowData cria a fazenda, daí depois cria uma pessoa lá dentro, cria o usuário
dela e atribui as credenciais do contratante... depois disso, sempre se cria
pessoa dentro de uma fazenda e depois usuário." Fazenda → pessoa → usuário,
nessa ordem, sempre.

Por que isso é segurança e não cadastro: um `Usuario` sem nenhum
`UsuarioFazenda` faz o login emitir token SEM a claim "fid" (ver
routers/auth.py::login), e o sistema inteiro recorta tenant pelo padrão
tolerante `if fazenda_id is not None: query = query.where(...)` — token sem
"fid" não restringe nada, ele DESLIGA o recorte por fazenda. Criar usuário
órfão é fabricar a chave que abre as outras fazendas.

Cobre, nesta ordem: (a) a recusa e a mensagem que ensina o caminho; (b) o
caminho certo funcionando ponta a ponta, do cadastro da fazenda até o login do
funcionário caindo nela; (c) o login da própria equipe CowData, exceção
declarada, continuando a nascer sem vínculo; (d) falha ao gravar o vínculo não
deixando `Usuario` órfão para trás (o vínculo é do mesmo commit, não de um
segundo).

A tolerância do lado "sem nenhuma fazenda cadastrada" (instalação anterior ao
multi-fazenda) fica em tests/test_auth_usuarios.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers.auth import ERRO_USUARIO_SEM_FAZENDA
from fazenda.api.routers.painel_cowdata import seed_cowdata_empresa
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import ContratoFazenda, Fazenda, Pessoa, Usuario, UsuarioFazenda


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        # /auth/usuarios é restrito ao proprietário (exigir_dono).
        s.add(Usuario(username="dono", nome="Dono", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(c, username="dono", senha="123") -> dict:
    r = c.post("/auth/login", json={"username": username, "senha": senha})
    assert r.status_code == 200, r.text
    return r.json()


def _criar_fazenda(c, token: str, nome="Fazenda Boa Vista") -> int:
    """Passo 1 do fluxo: o CowData cria a fazenda (provisiona contas, centros
    de custo, tipos de pessoa e o contrato aguardando aprovação)."""
    r = c.post("/fazendas", json={"nome": nome}, headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _ativar_contrato(engine, fazenda_id: int) -> None:
    """A fazenda nova nasce com contrato "aguardando_aprovacao" e nada
    funciona até o passo comercial (escolher plano/módulos e aprovar). Isso é
    outro fluxo — aqui só destravamos o contrato direto no banco para poder
    chegar ao Cadastro de Pessoas, que é o que estes testes querem exercitar."""
    with Session(engine) as s:
        contrato = s.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
        contrato.status = "ativo"
        s.add(contrato)
        s.commit()


def _entrar_na_fazenda(c, token: str, fazenda_id: int) -> str:
    """O dono nunca cai direto numa fazenda-cliente (o login sempre lhe
    oferece a escolha entre a fazenda e o Painel CowData) — ele escolhe, e o
    token novo é que carrega o "fid"."""
    r = c.post("/auth/selecionar-fazenda", json={"fazenda_id": fazenda_id}, headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _fazenda_pronta_com_dono_dentro(c, engine) -> tuple[str, int]:
    """Fazenda criada, contrato ativo, dono vinculado e já com o token da
    fazenda selecionada — o ponto de partida de quem vai cadastrar gente."""
    token = _login(c)["token"]
    fazenda_id = _criar_fazenda(c, token)
    _ativar_contrato(engine, fazenda_id)
    r = c.post(
        f"/fazendas/{fazenda_id}/vincular-usuario",
        json={"username": "dono", "contratante": True}, headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return _entrar_na_fazenda(c, token, fazenda_id), fazenda_id


def _vinculos(engine, username: str) -> list[UsuarioFazenda]:
    with Session(engine) as s:
        u = s.exec(select(Usuario).where(Usuario.username == username)).first()
        if not u:
            return []
        return list(s.exec(select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == u.id)).all())


# ---------------------------------------------------------------------------
# (a) Criar usuário sem fazenda é recusado — e a recusa ensina o caminho
# ---------------------------------------------------------------------------
def test_criar_usuario_sem_pessoa_e_recusado_com_mensagem_que_ensina_o_caminho(client):
    """`nome` livre, sem pessoa nenhuma, é literalmente "usuário sem fazenda":
    era por aqui que nascia a conta órfã. Agora recusa — e a mensagem diz a
    ordem certa, porque ela é a única explicação que quem tentou vai receber."""
    c, engine = client
    token, _ = _fazenda_pronta_com_dono_dentro(c, engine)

    r = c.post(
        "/auth/usuarios",
        json={"username": "solto", "senha": "123", "nome": "Conta Solta", "papel": "admin", "permissoes": []},
        headers=_auth(token),
    )
    assert r.status_code == 400
    detalhe = r.json()["detail"]
    assert detalhe == ERRO_USUARIO_SEM_FAZENDA
    assert "primeiro a fazenda" in detalhe
    assert "pessoa dentro dela" in detalhe

    # E a recusa não pode ter deixado nada gravado pelo caminho.
    with Session(engine) as s:
        assert s.exec(select(Usuario).where(Usuario.username == "solto")).first() is None


def test_criar_usuario_sem_fazenda_selecionada_e_recusado(client):
    """Mesma trava pelo outro lado: com fazendas no banco, uma sessão que não
    diz em que fazenda está não consegue criar login nenhum (409 de
    get_fazenda_id_escrita) — antes o usuário nascia órfão exatamente assim,
    e é essa conta que depois circulava com token sem "fid"."""
    c, engine = client
    token = _login(c)["token"]  # token sem "fid": o dono ainda não escolheu fazenda
    fazenda_id = _criar_fazenda(c, token)
    _ativar_contrato(engine, fazenda_id)

    with Session(engine) as s:
        pessoa = Pessoa(nome="Zé da Roça", tipo="Funcionário", fazenda_id=fazenda_id)
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        pessoa_id = pessoa.id

    r = c.post(
        "/auth/usuarios",
        json={"username": "ze", "senha": "123", "pessoa_id": pessoa_id, "papel": "operador", "permissoes": []},
        headers=_auth(token),
    )
    assert r.status_code == 409
    with Session(engine) as s:
        assert s.exec(select(Usuario).where(Usuario.username == "ze")).first() is None


# ---------------------------------------------------------------------------
# (b) O caminho certo — fazenda → pessoa → usuário — ponta a ponta
# ---------------------------------------------------------------------------
def test_fluxo_correto_fazenda_pessoa_usuario_funciona_ponta_a_ponta(client):
    """O fluxo inteiro na ordem do dono: cria a fazenda, cadastra a pessoa
    DENTRO dela, cria o login dessa pessoa — e o funcionário loga já caindo
    naquela fazenda, com o token carregando o "fid" (que é o que faz o recorte
    por fazenda valer de verdade nas consultas)."""
    c, engine = client
    token, fazenda_id = _fazenda_pronta_com_dono_dentro(c, engine)

    r_pessoa = c.post(
        "/cadastro/pessoas",
        json={"nome": "Maria Ordenhadora", "tipos": ["Funcionário"]},
        headers=_auth(token),
    )
    assert r_pessoa.status_code == 200, r_pessoa.text
    pessoa_id = r_pessoa.json()["id"]

    r = c.post(
        "/auth/usuarios",
        json={"username": "maria", "senha": "senha123", "pessoa_id": pessoa_id,
              "papel": "operador", "permissoes": ["rebanho"]},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["nome"] == "Maria Ordenhadora"
    assert r.json()["pessoa_id"] == pessoa_id

    # O vínculo nasceu junto, na fazenda da pessoa — não em outra, e não
    # depois, num segundo commit.
    vinculos = _vinculos(engine, "maria")
    assert [v.fazenda_id for v in vinculos] == [fazenda_id]
    # Vínculo simples: o papel de contratante é sempre atribuição deliberada
    # (POST /fazendas/{id}/vincular-usuario ou Painel CowData), nunca efeito
    # colateral de criar um login.
    assert vinculos[0].contratante is False

    # A prova final é o login: uma fazenda vinculada, auto-selecionada, token
    # com "fid" — nada de conta que entra "sem fazenda".
    dados_login = _login(c, "maria", "senha123")
    assert dados_login["fazenda_atual"]["id"] == fazenda_id
    assert "selecao_fazenda_necessaria" not in dados_login

    from fazenda.auth import _validar_token_payload
    assert _validar_token_payload(dados_login["token"])["fid"] == fazenda_id


def test_pessoa_legada_sem_fazenda_usa_a_fazenda_da_sessao(client):
    """Pessoa cadastrada antes do backfill de multi-fazenda tem `fazenda_id`
    nulo e não há tela para corrigir isso retroativamente — bloquear o login
    dela quebraria um fluxo real sem saída. O usuário então cai na fazenda em
    que o Controle de Acesso está aberto: continua sem órfão, que é o ponto."""
    c, engine = client
    token, fazenda_id = _fazenda_pronta_com_dono_dentro(c, engine)

    with Session(engine) as s:
        pessoa = Pessoa(nome="João Legado", tipo="Funcionário")  # fazenda_id=None, de propósito
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        pessoa_id = pessoa.id

    r = c.post(
        "/auth/usuarios",
        json={"username": "joao.legado", "senha": "123", "pessoa_id": pessoa_id,
              "papel": "operador", "permissoes": []},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert [v.fazenda_id for v in _vinculos(engine, "joao.legado")] == [fazenda_id]


# ---------------------------------------------------------------------------
# (c) Exceção declarada: o login da própria equipe CowData
# ---------------------------------------------------------------------------
def test_usuario_da_equipe_cowdata_continua_nascendo_sem_vinculo(client):
    """Suporte/consultoria da CowData não é usuário de tenant nenhum: a Pessoa
    dele vive na fazenda "lógica" da CowData (eh_empresa_cowdata), o login sai
    com ZERO vínculos de propósito e ele só entra numa fazenda-cliente pelo
    Cofre de acesso, que carimba o "fid" com motivo, protocolo e auditoria.
    A trava de POST /auth/usuarios não pode ter alcançado este caminho."""
    c, engine = client
    token = _login(c)["token"]
    with Session(engine) as s:
        seed_cowdata_empresa(s)

    r_pessoa = c.post(
        "/painel-cowdata/equipe/pessoas",
        json={"nome": "Carla Suporte", "cargo": "Suporte"}, headers=_auth(token),
    )
    assert r_pessoa.status_code == 200, r_pessoa.text

    r = c.post(
        f"/painel-cowdata/equipe/pessoas/{r_pessoa.json()['id']}/usuario",
        json={"username": "carla.suporte", "email": "carla@cowdata.com", "senha": "senha123",
              "areas": ["equipe"]},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert _vinculos(engine, "carla.suporte") == []

    # E o login dele continua caindo na escolha com o Painel CowData, sem
    # fazenda auto-selecionada.
    dados_login = _login(c, "carla.suporte", "senha123")
    assert dados_login["selecao_fazenda_necessaria"] is True
    assert any(op.get("cowdata") for op in dados_login["fazendas_disponiveis"])


# ---------------------------------------------------------------------------
# (d) Falhando o vínculo, não sobra Usuario órfão
# ---------------------------------------------------------------------------
def test_falha_ao_gravar_vinculo_nao_deixa_usuario_orfao(client, monkeypatch):
    """A razão de o vínculo ser do MESMO commit, e não de um segundo: validar a
    entrada não bastaria — se a gravação do vínculo falhasse depois de o
    `Usuario` já estar comitado, o estado órfão voltaria a existir, e desta vez
    sem ninguém para reclamar. Aqui a criação do vínculo explode no meio; o
    `Usuario` já foi ao banco pelo flush e mesmo assim não pode sobreviver."""
    c, engine = client
    token, fazenda_id = _fazenda_pronta_com_dono_dentro(c, engine)

    r_pessoa = c.post(
        "/cadastro/pessoas", json={"nome": "Pedro Tratorista", "tipos": ["Funcionário"]}, headers=_auth(token),
    )
    assert r_pessoa.status_code == 200, r_pessoa.text
    pessoa_id = r_pessoa.json()["id"]

    import fazenda.api.routers.auth as router_auth

    def _explode(*args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o vínculo UsuarioFazenda")

    monkeypatch.setattr(router_auth, "UsuarioFazenda", _explode)

    with pytest.raises(RuntimeError):
        c.post(
            "/auth/usuarios",
            json={"username": "pedro", "senha": "123", "pessoa_id": pessoa_id,
                  "papel": "operador", "permissoes": []},
            headers=_auth(token),
        )

    with Session(engine) as s:
        assert s.exec(select(Usuario).where(Usuario.username == "pedro")).first() is None


# ---------------------------------------------------------------------------
# (e) PUT /auth/usuarios/{id} fecha o mesmo furo pelo lado da edição
# ---------------------------------------------------------------------------
def test_vincular_pessoa_a_usuario_existente_sem_vinculo_cria_o_vinculo_que_faltava(client):
    """Caso real de produção (12/09/2026): um funcionário ficou preso em
    "fazenda não selecionada" em toda tela. Causa raiz, achada direto no
    banco: `Usuario` com `pessoa_id` apontando para uma Pessoa de uma fazenda
    real, mas ZERO linhas em `UsuarioFazenda` — o mesmo estado órfão que
    POST /auth/usuarios já bloqueia na criação, só que este nasceu depois,
    por PUT /auth/usuarios/{id} atribuindo (ou trocando) a Pessoa de um login
    que já existia sem o vínculo correspondente nunca ter sido criado.

    Aqui o Usuario nasce direto no banco sem `pessoa_id` (simulando o estado
    órfão pré-existente, de antes desta trava) e o teste prova que vincular a
    Pessoa por PUT agora cria o `UsuarioFazenda` que faltava, na fazenda da
    Pessoa — em vez de só trocar `pessoa_id` e manter o login preso."""
    c, engine = client
    token, fazenda_id = _fazenda_pronta_com_dono_dentro(c, engine)

    r_pessoa = c.post(
        "/cadastro/pessoas", json={"nome": "Rosivaldo Lourenço Ferreira", "tipos": ["Funcionário"]}, headers=_auth(token),
    )
    assert r_pessoa.status_code == 200, r_pessoa.text
    pessoa_id = r_pessoa.json()["id"]

    with Session(engine) as s:
        orfao = Usuario(username="rosivaldo", nome="Conta Órfã", senha_hash=hash_senha("123"), papel="operador", permissoes="agenda", ativo=True)
        s.add(orfao)
        s.commit()
        s.refresh(orfao)
        usuario_id = orfao.id
    assert _vinculos(engine, "rosivaldo") == []  # o estado órfão pré-existente

    r = c.put(f"/auth/usuarios/{usuario_id}", json={"pessoa_id": pessoa_id}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["pessoa_id"] == pessoa_id

    vinculos = _vinculos(engine, "rosivaldo")
    assert [v.fazenda_id for v in vinculos] == [fazenda_id]

    dados_login = _login(c, "rosivaldo", "123")
    assert dados_login["fazenda_atual"]["id"] == fazenda_id
    assert "selecao_fazenda_necessaria" not in dados_login


def test_vincular_pessoa_a_usuario_que_ja_tem_o_vinculo_nao_duplica(client):
    """Editar outros campos (ou reenviar o mesmo `pessoa_id`) de um usuário que
    JÁ tem o vínculo certo não pode tentar criar um segundo — estouraria a
    UniqueConstraint(usuario_id, fazenda_id)."""
    c, engine = client
    token, fazenda_id = _fazenda_pronta_com_dono_dentro(c, engine)

    r_pessoa = c.post("/cadastro/pessoas", json={"nome": "Maria Ordenhadora", "tipos": ["Funcionário"]}, headers=_auth(token))
    pessoa_id = r_pessoa.json()["id"]
    r = c.post(
        "/auth/usuarios",
        json={"username": "maria", "senha": "123", "pessoa_id": pessoa_id, "papel": "operador", "permissoes": []},
        headers=_auth(token),
    )
    usuario_id = r.json()["id"]
    assert len(_vinculos(engine, "maria")) == 1

    r2 = c.put(f"/auth/usuarios/{usuario_id}", json={"pessoa_id": pessoa_id}, headers=_auth(token))
    assert r2.status_code == 200, r2.text
    assert len(_vinculos(engine, "maria")) == 1
