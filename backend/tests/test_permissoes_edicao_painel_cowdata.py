"""
As SETE permissões de EDIÇÃO no Painel CowData (set/2026) e a mudança de casa
da manutenção do catálogo global de touros NAAB.

O que está em julgamento, item por item:

  1. edição de cadastros globais   — consulta livre, escrita com permissão
  2. edição de touros NAAB         — consulta livre, escrita com permissão
  3. edição de Farmácia            — consulta livre, escrita com permissão
  4. consulta de usuários
  5. edição de usuários
  6. controle de acesso de usuários CowData
  7. edição de News

Nos três primeiros a assimetria é o ponto: DESMARCAR a permissão não pode
tirar a visualização de ninguém — só trancar a escrita. Por isso cada um
deles tem três testes: lê sem permissão nenhuma, não escreve sem permissão,
escreve com ela.

TOKEN DE VERDADE (`criar_token`), nunca `dependency_overrides` na
autenticação: o que se testa aqui é o caminho token -> get_current_user ->
PermissaoEquipeCowData -> rota. Falsificar o meio dele testaria outra coisa.
Mesmo espírito de tests/test_seguranca_acesso_documentos_multitenant.py.

Todo teste de bloqueio vem com o controle positivo ao lado — teste que só
prova bloqueio pode estar bloqueando tudo.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.api.routers.painel_cowdata import seed_cowdata_empresa
from fazenda.auth import EMAIL_DONO, criar_token, hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Doenca, Fazenda, MotivoBaixa, Pessoa, Touro, Usuario, UsuarioFazenda,
)
from fazenda.models.equipe_cowdata_acesso import (
    CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA, PermissaoEquipeCowData,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

# Áreas que o membro de teste carrega — ele VÊ tudo que interessa aqui. O que
# muda de um teste para o outro é só a permissão booleana de escrita, que é
# exatamente a separação sob teste.
AREAS_DO_MEMBRO = "cadastros,farmacia,produto"


@pytest.fixture
def ambiente(monkeypatch):
    """Uma fazenda-cliente (1), a fazenda interna da CowData (2), o dono, o
    administrador da fazenda-cliente e um membro da Equipe CowData sem
    NENHUMA das sete permissões novas — o estado em que a migração deixa
    todo mundo."""
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Cliente"))
        s.add(Fazenda(id=2, nome="CowData", eh_empresa_cowdata=True))
        s.commit()
        # A seed de verdade só roda no startup contra o engine de produção —
        # este TestClient isolado precisa dos cargos (TipoPessoa) da fazenda
        # interna para POST /equipe/pessoas funcionar.
        seed_cowdata_empresa(s)
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))

        # Administrador da fazenda-cliente — quem hoje conseguia reescrever o
        # catálogo global de touros de todo mundo.
        admin = Usuario(username="admin1", senha_hash=hash_senha("x"), papel="admin", ativo=True)
        dono = Usuario(username="dono", senha_hash=hash_senha("x"), papel="admin", email=EMAIL_DONO, ativo=True)
        s.add_all([admin, dono])
        s.commit()
        s.refresh(admin)
        s.add(UsuarioFazenda(usuario_id=admin.id, fazenda_id=1))

        # Pessoa da fazenda-cliente, para as rotas de Painel CowData > Usuários.
        operador_pessoa = Pessoa(nome="Operador da Fazenda", tipo="Funcionário", fazenda_id=1, ativo=True)
        sem_login_pessoa = Pessoa(nome="Ainda Sem Login", tipo="Funcionário", fazenda_id=1, ativo=True)
        membro_pessoa = Pessoa(nome="Membro CowData", tipo="Funcionário", fazenda_id=2, ativo=True)
        s.add_all([operador_pessoa, sem_login_pessoa, membro_pessoa])
        s.commit()
        s.refresh(operador_pessoa)
        s.refresh(sem_login_pessoa)
        s.refresh(membro_pessoa)

        operador = Usuario(
            username="operador", nome="Operador da Fazenda", pessoa_id=operador_pessoa.id,
            senha_hash=hash_senha("senha-original"), papel="operador", permissoes="rebanho", ativo=True,
        )
        # O membro da Equipe CowData já nasce com a flag antiga do blog
        # ligada: assim o teste de News mede a permissão NOVA, e não a flag
        # que sempre existiu.
        membro = Usuario(
            username="membro", nome="Membro CowData", pessoa_id=membro_pessoa.id,
            senha_hash=hash_senha("x"), papel="operador", email="membro@cowdata.com.br", ativo=True,
            pode_publicar_materias_blog=True,
        )
        s.add_all([operador, membro])
        s.commit()
        s.refresh(operador)
        s.refresh(membro)

        s.add(PermissaoEquipeCowData(usuario_id=membro.id, areas=AREAS_DO_MEMBRO))

        # Dados para as rotas de leitura/escrita sob teste.
        s.add(MotivoBaixa(nome="Morte", ativo=True, fazenda_id=1))
        s.add(Doenca(nome="Mastite", ativo=True, fazenda_id=None))
        s.add(Touro(naab="007HO11111", nome="TOURO DO CATALOGO", tpi=2800))
        s.commit()

        ids.update(
            operador=operador.id, membro=membro.id,
            pessoa_sem_login=sem_login_pessoa.id,
            touro=s.exec(select(Touro).where(Touro.naab == "007HO11111")).first().id,
            doenca=s.exec(select(Doenca).where(Doenca.nome == "Mastite")).first().id,
        )

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab_membro():
    """Token REAL do membro da Equipe CowData — sem "fid": o Painel CowData
    administra todas as fazendas e não fica dentro de nenhuma."""
    return {"Authorization": f"Bearer {criar_token('membro')}"}


def _cab_dono():
    return {"Authorization": f"Bearer {criar_token('dono')}"}


def _cab_admin_fazenda():
    """Token REAL do administrador da fazenda-cliente, com "fid" carimbado."""
    return {"Authorization": f"Bearer {criar_token('admin1', fazenda_id=1)}"}


def _liberar(engine, **permissoes) -> None:
    """Liga permissões do membro — o que o dono faz na tela de equipe."""
    with Session(engine) as s:
        perm = s.exec(select(PermissaoEquipeCowData)).first()
        for campo, valor in permissoes.items():
            assert campo in CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA, campo
            setattr(perm, campo, valor)
        s.add(perm)
        s.commit()


# ---------------------------------------------------------------------------
# A migração não dá nada a ninguém
# ---------------------------------------------------------------------------
def test_membro_existente_nasce_sem_nenhuma_das_sete_permissoes(ambiente):
    """"Ninguém ganha nada; você libera depois" — decisão explícita do dono.
    Uma linha de PermissaoEquipeCowData gravada só com `areas` (como é toda
    linha que já existia antes da migração c3a91f4d20b7) tem as sete
    permissões desligadas."""
    c, engine, ids = ambiente
    with Session(engine) as s:
        perm = s.exec(select(PermissaoEquipeCowData)).first()
        desligadas = {campo: getattr(perm, campo) for campo in CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA}
    assert desligadas == dict.fromkeys(CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA, False), desligadas


def test_a_tela_de_equipe_nao_liga_nada_por_omissao(ambiente):
    """Um cliente desatualizado que salve o login SEM mandar os campos novos
    não pode abrir acesso — o default do schema é False em todos."""
    c, engine, ids = ambiente
    pessoa = c.post(
        "/painel-cowdata/equipe/pessoas", json={"nome": "Novato", "cargo": "Suporte"}, headers=_cab_dono(),
    ).json()
    r = c.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario",
        json={"username": "novato", "email": "novato@x.com", "senha": "123456", "areas": ["cadastros"]},
        headers=_cab_dono(),
    )
    assert r.status_code == 200, r.text
    assert all(r.json()[campo] is False for campo in CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA), r.json()


def test_o_dono_liga_uma_a_uma_pela_tela_de_equipe(ambiente):
    """Controle positivo do formulário: o que o dono marca é o que fica
    gravado — e nada além."""
    c, engine, ids = ambiente
    pessoa = c.post(
        "/painel-cowdata/equipe/pessoas", json={"nome": "Editor", "cargo": "Suporte"}, headers=_cab_dono(),
    ).json()
    r = c.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario",
        json={
            "username": "editor", "email": "editor@x.com", "senha": "123456",
            "areas": ["cadastros"], "pode_editar_touros_naab": True,
        },
        headers=_cab_dono(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pode_editar_touros_naab"] is True
    assert r.json()["pode_editar_cadastros_globais"] is False


# ---------------------------------------------------------------------------
# 1) Cadastros globais — consulta livre, edição com permissão
# ---------------------------------------------------------------------------
def test_cadastros_globais_a_consulta_e_livre_sem_permissao(ambiente):
    c, engine, ids = ambiente
    for rota in ("/painel-cowdata/cadastros/categorias", "/painel-cowdata/cadastros/motivo_baixa"):
        r = c.get(rota, headers=_cab_membro())
        assert r.status_code == 200, (rota, r.text)


def test_cadastros_globais_nao_edita_sem_permissao(ambiente):
    c, engine, ids = ambiente
    r = c.post(
        "/painel-cowdata/cadastros/motivo_baixa/aplicar",
        json={"nome": "Descarte por permissão", "fazenda_ids": [1]}, headers=_cab_membro(),
    )
    assert r.status_code == 403, r.text
    with Session(engine) as s:
        assert s.exec(select(MotivoBaixa).where(MotivoBaixa.nome == "Descarte por permissão")).first() is None


def test_cadastros_globais_edita_com_permissao(ambiente):
    c, engine, ids = ambiente
    _liberar(engine, pode_editar_cadastros_globais=True)
    r = c.post(
        "/painel-cowdata/cadastros/motivo_baixa/aplicar",
        json={"nome": "Descarte por permissão", "fazenda_ids": [1]}, headers=_cab_membro(),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.exec(select(MotivoBaixa).where(MotivoBaixa.nome == "Descarte por permissão")).first() is not None


# ---------------------------------------------------------------------------
# 2) Touros NAAB — consulta livre, edição com permissão
# ---------------------------------------------------------------------------
def test_touros_a_consulta_e_livre_sem_permissao(ambiente):
    c, engine, ids = ambiente
    r = c.get("/painel-cowdata/touros", headers=_cab_membro())
    assert r.status_code == 200, r.text
    assert [t["naab"] for t in r.json()] == ["007HO11111"]


def test_touros_nao_edita_sem_permissao(ambiente):
    c, engine, ids = ambiente
    tentativas = [
        ("post", "/painel-cowdata/touros", {"naab": "007HO22222", "nome": "Intruso"}),
        ("put", f"/painel-cowdata/touros/{ids['touro']}", {"naab": "007HO11111", "nome": "Renomeado"}),
        ("delete", f"/painel-cowdata/touros/{ids['touro']}", None),
        ("post", "/painel-cowdata/touros/recarregar-catalogo", None),
    ]
    for metodo, rota, corpo in tentativas:
        r = getattr(c, metodo)(rota, headers=_cab_membro(), **({"json": corpo} if corpo else {}))
        assert r.status_code == 403, (metodo, rota, r.text)
    with Session(engine) as s:
        assert s.exec(select(Touro).where(Touro.naab == "007HO22222")).first() is None
        assert s.get(Touro, ids["touro"]).nome == "TOURO DO CATALOGO"


def test_touros_edita_com_permissao(ambiente):
    c, engine, ids = ambiente
    _liberar(engine, pode_editar_touros_naab=True)
    assert c.post(
        "/painel-cowdata/touros", json={"naab": "007HO22222", "nome": "Novo"}, headers=_cab_membro(),
    ).status_code == 200
    assert c.put(
        f"/painel-cowdata/touros/{ids['touro']}", json={"naab": "007HO11111", "nome": "Renomeado"},
        headers=_cab_membro(),
    ).status_code == 200
    assert c.delete(f"/painel-cowdata/touros/{ids['touro']}", headers=_cab_membro()).status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Touro).where(Touro.naab == "007HO22222")).first() is not None
        assert s.get(Touro, ids["touro"]) is None


# ---------------------------------------------------------------------------
# 2b) O catálogo global saiu do alcance da fazenda-cliente
# ---------------------------------------------------------------------------
def test_administrador_de_fazenda_nao_altera_mais_o_catalogo_de_touros(ambiente):
    """O furo: `Touro` não tem fazenda_id — é uma tabela só, lida por todas
    as fazendas-cliente — e a escrita morava no router da fazenda sob
    `exigir_admin`. O administrador de QUALQUER fazenda reescrevia ou apagava
    o catálogo de todas. As rotas foram removidas de lá, então a recusa vem
    do próprio roteador (404/405), não de uma dependência que alguém possa
    trocar por engano depois."""
    c, engine, ids = ambiente
    tentativas = [
        ("post", "/cadastro/touros", {"naab": "007HO99999", "nome": "Touro Invasor"}),
        ("put", f"/cadastro/touros/{ids['touro']}", {"naab": "007HO11111", "nome": "Sequestrado"}),
        ("delete", f"/cadastro/touros/{ids['touro']}", None),
        ("post", "/cadastro/touros/recarregar-catalogo", None),
    ]
    for metodo, rota, corpo in tentativas:
        r = getattr(c, metodo)(rota, headers=_cab_admin_fazenda(), **({"json": corpo} if corpo else {}))
        assert r.status_code in (403, 404, 405), (metodo, rota, r.status_code, r.text)
    with Session(engine) as s:
        assert s.exec(select(Touro).where(Touro.naab == "007HO99999")).first() is None
        touro = s.get(Touro, ids["touro"])
        assert touro is not None and touro.nome == "TOURO DO CATALOGO"


def test_administrador_de_fazenda_nao_importa_mais_a_planilha_do_catalogo(ambiente):
    """Mesmo furo pelo outro caminho: `POST /importar/touros_naab` fazia
    upsert no catálogo global protegido só por `exigir_modulo("upload")`."""
    c, engine, ids = ambiente
    r = c.post(
        "/importar/touros_naab", files={"file": ("catalogo.csv", b"naab,nome\n007HO99999,Invasor\n", "text/csv")},
        headers=_cab_admin_fazenda(),
    )
    assert r.status_code in (403, 404, 405), r.text
    with Session(engine) as s:
        assert s.exec(select(Touro).where(Touro.naab == "007HO99999")).first() is None


def test_a_fazenda_continua_lendo_o_catalogo_de_touros(ambiente):
    """Controle positivo, e o coração do pedido: "qualquer fazenda usa". A
    listagem do catálogo, a prova média e a prova ao vivo (estudo de touros)
    continuam abertas para a fazenda — é delas que saem a inseminação com
    touro fora do estoque, a seleção para compra e a sugestão de
    acasalamento."""
    c, engine, ids = ambiente
    r = c.get("/cadastro/touros", headers=_cab_admin_fazenda())
    assert r.status_code == 200, r.text
    assert [t["naab"] for t in r.json()] == ["007HO11111"]
    for rota in ("/cadastro/estoque-semen/prova-media", "/cadastro/estoque-semen/prova-ao-vivo"):
        assert c.get(rota, headers=_cab_admin_fazenda()).status_code == 200, rota


# ---------------------------------------------------------------------------
# 3) Farmácia — consulta livre, edição com permissão
# ---------------------------------------------------------------------------
def test_farmacia_a_consulta_e_livre_sem_permissao(ambiente):
    c, engine, ids = ambiente
    for rota in ("/painel-cowdata/farmacia/categorias", "/painel-cowdata/farmacia/principios",
                 "/painel-cowdata/farmacia/medicamentos"):
        r = c.get(rota, headers=_cab_membro())
        assert r.status_code == 200, (rota, r.text)


def test_farmacia_nao_edita_sem_permissao(ambiente):
    c, engine, ids = ambiente
    r = c.post("/painel-cowdata/farmacia/categorias", json={"nome": "Categoria Intrusa"}, headers=_cab_membro())
    assert r.status_code == 403, r.text
    r = c.put(
        f"/painel-cowdata/farmacia/categorias/{ids['doenca']}", json={"nome": "Renomeada"}, headers=_cab_membro(),
    )
    assert r.status_code == 403, r.text
    with Session(engine) as s:
        assert s.exec(select(Doenca).where(Doenca.nome == "Categoria Intrusa")).first() is None
        assert s.get(Doenca, ids["doenca"]).nome == "Mastite"


def test_farmacia_edita_com_permissao(ambiente):
    c, engine, ids = ambiente
    _liberar(engine, pode_editar_farmacia=True)
    r = c.post("/painel-cowdata/farmacia/categorias", json={"nome": "Categoria Nova"}, headers=_cab_membro())
    assert r.status_code == 201, r.text
    with Session(engine) as s:
        assert s.exec(select(Doenca).where(Doenca.nome == "Categoria Nova")).first() is not None


# ---------------------------------------------------------------------------
# 4, 5, 6) Usuários — consulta, edição e controle de acesso
# ---------------------------------------------------------------------------
def test_usuarios_nao_consulta_sem_permissao(ambiente):
    """Aqui NÃO há "consulta livre": ver a lista de logins de uma fazenda-
    cliente é a própria permissão nº 4."""
    c, engine, ids = ambiente
    for rota in ("/painel-cowdata/usuarios/1", "/painel-cowdata/usuarios/1/pessoas"):
        assert c.get(rota, headers=_cab_membro()).status_code == 403, rota


def test_usuarios_consulta_com_permissao(ambiente):
    c, engine, ids = ambiente
    _liberar(engine, pode_consultar_usuarios=True)
    for rota in ("/painel-cowdata/usuarios/1", "/painel-cowdata/usuarios/1/pessoas"):
        r = c.get(rota, headers=_cab_membro())
        assert r.status_code == 200, (rota, r.text)


def test_usuarios_nao_edita_so_com_a_consulta(ambiente):
    c, engine, ids = ambiente
    _liberar(engine, pode_consultar_usuarios=True)
    r = c.put(
        f"/painel-cowdata/usuarios/1/{ids['operador']}", json={"username": "renomeado"}, headers=_cab_membro(),
    )
    assert r.status_code == 403, r.text
    with Session(engine) as s:
        assert s.get(Usuario, ids["operador"]).username == "operador"


def test_usuarios_edita_o_que_nao_e_acesso_com_a_permissao_de_edicao(ambiente):
    """Quem tem "editar usuários" mexe em login e e-mail — o que não decide
    quem entra nem até onde vai."""
    c, engine, ids = ambiente
    _liberar(engine, pode_consultar_usuarios=True, pode_editar_usuarios=True)
    r = c.put(
        f"/painel-cowdata/usuarios/1/{ids['operador']}",
        json={"username": "renomeado", "email": "novo@x.com"}, headers=_cab_membro(),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(Usuario, ids["operador"]).username == "renomeado"


def test_usuarios_nao_mexe_em_senha_papel_permissoes_nem_ativo_sem_controle_de_acesso(ambiente):
    """Permissão nº 6. Sem ela, "editar usuários" para nos campos que DÃO
    ACESSO — inclusive trocar a senha, que é o caminho clássico de assumir
    um login alheio."""
    c, engine, ids = ambiente
    _liberar(engine, pode_consultar_usuarios=True, pode_editar_usuarios=True)
    for corpo in ({"senha": "trocada"}, {"papel": "admin"}, {"permissoes": ["financeiro"]}, {"ativo": False}):
        r = c.put(f"/painel-cowdata/usuarios/1/{ids['operador']}", json=corpo, headers=_cab_membro())
        assert r.status_code == 403, (corpo, r.text)
    with Session(engine) as s:
        u = s.get(Usuario, ids["operador"])
        assert u.papel == "operador" and u.permissoes == "rebanho" and u.ativo is True
    assert c.post("/auth/login", json={"username": "operador", "senha": "senha-original"}).status_code == 200


def test_usuarios_mexe_no_acesso_com_a_permissao_de_controle(ambiente):
    c, engine, ids = ambiente
    _liberar(engine, pode_consultar_usuarios=True, pode_editar_usuarios=True, pode_controlar_acesso_usuarios=True)
    r = c.put(
        f"/painel-cowdata/usuarios/1/{ids['operador']}",
        json={"permissoes": ["rebanho", "financeiro"]}, headers=_cab_membro(),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert "financeiro" in s.get(Usuario, ids["operador"]).permissoes


def test_criar_login_exige_edicao_e_controle_de_acesso(ambiente):
    """Criar um login É dar acesso: nasce com senha, papel e permissões. Só
    "editar usuários" não basta."""
    c, engine, ids = ambiente
    _liberar(engine, pode_consultar_usuarios=True, pode_editar_usuarios=True)
    corpo = {
        "pessoa_id": ids["pessoa_sem_login"], "username": "novo-login", "senha": "123456",
        "papel": "admin", "permissoes": [],
    }
    assert c.post("/painel-cowdata/usuarios/1", json=corpo, headers=_cab_membro()).status_code == 403
    with Session(engine) as s:
        assert s.exec(select(Usuario).where(Usuario.username == "novo-login")).first() is None

    _liberar(engine, pode_controlar_acesso_usuarios=True)
    assert c.post("/painel-cowdata/usuarios/1", json=corpo, headers=_cab_membro()).status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Usuario).where(Usuario.username == "novo-login")).first() is not None


def test_a_trava_contra_escalada_de_privilegio_nao_afrouxou(ambiente):
    """A guarda que já existia (nenhum membro da equipe altera um login
    DONO-EQUIVALENTE por esta rota) continua valendo COM as três permissões
    novas ligadas no máximo — a permissão nova é camada a mais, nunca um
    caminho alternativo em volta dela. Roda ANTES da checagem de campos de
    acesso, então nem os campos "inofensivos" passam."""
    c, engine, ids = ambiente
    _liberar(engine, pode_consultar_usuarios=True, pode_editar_usuarios=True, pode_controlar_acesso_usuarios=True)
    with Session(engine) as s:
        pessoa = Pessoa(nome="Sócio", tipo="Funcionário", fazenda_id=1, ativo=True)
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        socio = Usuario(
            username="socio", nome="Sócio", pessoa_id=pessoa.id, senha_hash=hash_senha("senha-do-socio"),
            papel="admin", email=EMAIL_DONO, ativo=True,
        )
        s.add(socio)
        s.commit()
        s.refresh(socio)
        socio_id = socio.id

    for corpo in ({"senha": "escolhida-pelo-atacante"}, {"username": "sequestrado"}, {"ativo": False},
                  {"email": "outro@x.com"}):
        r = c.put(f"/painel-cowdata/usuarios/1/{socio_id}", json=corpo, headers=_cab_membro())
        assert r.status_code == 403, (corpo, r.text)
    assert c.post("/auth/login", json={"username": "socio", "senha": "senha-do-socio"}).status_code == 200
    with Session(engine) as s:
        u = s.get(Usuario, socio_id)
        assert u.username == "socio" and u.ativo is True


# ---------------------------------------------------------------------------
# 7) News
# ---------------------------------------------------------------------------
def test_news_nao_edita_sem_permissao(ambiente):
    """O membro já tem a flag antiga (`pode_publicar_materias_blog`) ligada —
    o que barra aqui é só a permissão nova, que é o ponto: para quem é da
    Equipe CowData ela SOMA à flag, nunca a substitui."""
    c, engine, ids = ambiente
    assert c.get("/news/materias", headers=_cab_membro()).status_code == 403
    r = c.post(
        "/news/materias",
        json={"manchete": "Matéria intrusa", "corpo": "texto", "resumo": "resumo"}, headers=_cab_membro(),
    )
    assert r.status_code == 403, r.text
    assert c.get("/fotos-news/pastas", headers=_cab_membro()).status_code == 403


def test_news_edita_com_permissao(ambiente):
    c, engine, ids = ambiente
    _liberar(engine, pode_editar_news=True)
    assert c.get("/news/materias", headers=_cab_membro()).status_code == 200
    assert c.get("/fotos-news/pastas", headers=_cab_membro()).status_code == 200


def test_a_tela_de_equipe_liga_a_flag_do_blog_junto_com_a_permissao_de_news(ambiente):
    """A caixa "Editar News" tem de ser suficiente sozinha: o gate real cobra
    a flag antiga E a permissão nova, então gravar só a permissão deixaria a
    caixa marcada dando 403 — uma armadilha. Ver
    painel_cowdata.py::_aplicar_permissao_news."""
    c, engine, ids = ambiente
    pessoa = c.post(
        "/painel-cowdata/equipe/pessoas", json={"nome": "Redator", "cargo": "Suporte"}, headers=_cab_dono(),
    ).json()
    c.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario",
        json={
            "username": "redator", "email": "redator@x.com", "senha": "123456",
            "areas": ["cadastros"], "pode_editar_news": True,
        },
        headers=_cab_dono(),
    )
    with Session(engine) as s:
        redator = s.exec(select(Usuario).where(Usuario.username == "redator")).first()
        assert redator.pode_publicar_materias_blog is True
    assert c.get(
        "/news/materias", headers={"Authorization": f"Bearer {criar_token('redator')}"},
    ).status_code == 200


def test_usuario_de_fazenda_com_a_flag_do_blog_nao_precisa_da_permissao_nova(ambiente):
    """A camada nova só vale para quem é da Equipe CowData. Um usuário de
    fazenda-cliente com a flag antiga continua publicando como sempre — a
    mudança tinha de ser um aperto, nunca uma quebra."""
    c, engine, ids = ambiente
    with Session(engine) as s:
        u = s.exec(select(Usuario).where(Usuario.username == "admin1")).first()
        u.pode_publicar_materias_blog = True
        s.add(u)
        s.commit()
    assert c.get("/news/materias", headers=_cab_admin_fazenda()).status_code == 200


# ---------------------------------------------------------------------------
# O dono continua podendo tudo
# ---------------------------------------------------------------------------
def test_dono_equivalente_passa_em_todas_as_sete_sem_linha_de_permissao(ambiente):
    """O dono nunca teve PermissaoEquipeCowData e não vai passar a ter —
    mesmo bypass de `exigir_area_painel_cowdata`, agora também no eixo novo."""
    c, engine, ids = ambiente
    assert c.post(
        "/painel-cowdata/touros", json={"naab": "007HO33333", "nome": "Do dono"}, headers=_cab_dono(),
    ).status_code == 200
    assert c.post(
        "/painel-cowdata/farmacia/categorias", json={"nome": "Do dono"}, headers=_cab_dono(),
    ).status_code == 201
    assert c.post(
        "/painel-cowdata/cadastros/motivo_baixa/aplicar",
        json={"nome": "Do dono", "fazenda_ids": [1]}, headers=_cab_dono(),
    ).status_code == 200
    assert c.get("/painel-cowdata/usuarios/1", headers=_cab_dono()).status_code == 200
