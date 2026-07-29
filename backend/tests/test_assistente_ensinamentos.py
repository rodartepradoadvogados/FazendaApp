"""
Testes do gate por usuário (dono da fazenda + parâmetro
`assistente_usuarios_liberados`) e da base de conhecimento
(AssistenteEnsinamento) do Assistente — ver fazenda/api/routers/assistente.py
e fazenda/rules/assistente.py::_system_prompt.

Fixture própria (mesmo padrão de test_isolamento_sanidade.py): engine
isolado, com `database.engine`/`main.engine` monkeypatchados, porque o gate
por usuário lê o parâmetro `assistente_usuarios_liberados` via
`get_param_texto` (fazenda/rules/parametros.py), que abre a própria Session
direto de `fazenda.database.engine` — sem o monkeypatch, o teste enxergaria o
banco de verdade em vez do banco de teste.
"""
from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import AssistenteEnsinamento, ContratoFazenda, Fazenda, ParametroFazenda, UsuarioFazenda
from fazenda.rules.assistente import SYSTEM_PROMPT


class _Usuario:
    def __init__(self, id=1, papel="operador", permissoes=""):
        self.id = id
        self.papel = papel
        self.permissoes = permissoes
        self.ativo = True
        self.username = f"user{id}"


def _resposta_mock(texto: str):
    bloco = MagicMock()
    bloco.type = "text"
    bloco.text = texto
    bloco.model_dump.return_value = {"type": "text", "text": texto}
    resposta = MagicMock()
    resposta.content = [bloco]
    resposta.stop_reason = "end_turn"
    return resposta


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        # exigir_contrato_ativo() (trava de tenant, main.py) exige contrato
        # ativo sempre que fazenda_id não é None — ortogonal ao que este
        # arquivo testa, então libera as duas fazendas.
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazenda(fazenda_id=2, status="ativo"))
        # Usuário 1 é o dono/contratante da fazenda 1; usuário 3, da fazenda
        # 2. Usuário 2 não tem vínculo nenhum (nem liberado por parâmetro).
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1, contratante=True))
        s.add(UsuarioFazenda(usuario_id=3, fazenda_id=2, contratante=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(id=1)
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como(usuario_id: int, fazenda_id: int):
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(id=usuario_id)
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


# ---------------------------------------------------------------------------
# Gate de acesso — dono da fazenda OU usuário liberado por parâmetro.
# ---------------------------------------------------------------------------
class TestGateAcesso:
    def test_dono_da_fazenda_acessa_perguntar(self, client, monkeypatch):
        c, engine = client
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
        # Passou do gate — só falta a chave (503), não 403.
        assert r.status_code == 503

    def test_usuario_nao_liberado_toma_403_no_perguntar(self, client):
        c, engine = client
        _como(2, 1)
        r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 403

    def test_usuario_liberado_via_parametro_acessa(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            # FAZENDA_TESTING (conftest.py) pula os seeds do lifespan — a linha
            # não existe de graça como no app real, então o teste cria a sua.
            s.add(ParametroFazenda(
                chave="assistente_usuarios_liberados", fazenda_id=None, grupo="agenda_sistema",
                label="Assistente — usuários liberados", valor="2", tipo="texto",
            ))
            s.commit()
        _como(2, 1)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503

    def test_usuario_nao_liberado_toma_403_nos_ensinamentos(self, client):
        c, engine = client
        _como(2, 1)
        assert c.get("/assistente/ensinamentos").status_code == 403
        assert c.post("/assistente/ensinamentos", json={"titulo": "x", "texto": "y"}).status_code == 403
        assert c.put("/assistente/ensinamentos/1", json={"titulo": "x", "texto": "y", "ativo": True}).status_code == 403
        assert c.delete("/assistente/ensinamentos/1").status_code == 403

    def test_endpoint_acesso_nunca_da_403(self, client):
        c, engine = client
        _como(2, 1)
        r = c.get("/assistente/acesso")
        assert r.status_code == 200
        assert r.json() == {"liberado": False}

        _como(1, 1)
        r = c.get("/assistente/acesso")
        assert r.status_code == 200
        assert r.json() == {"liberado": True}


# ---------------------------------------------------------------------------
# Ensinamentos entram (ou não) no SYSTEM_PROMPT enviado à Claude — API mockada.
# ---------------------------------------------------------------------------
class TestSystemPromptComEnsinamentos:
    def test_ensinamento_ativo_entra_no_system_prompt(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
        with Session(engine) as s:
            s.add(AssistenteEnsinamento(
                fazenda_id=1, usuario_id=1, titulo="Nome da fazenda",
                texto="O nome oficial é Fazenda Estreito Ponte de Pedra II.",
            ))
            s.commit()

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock("ok")
            r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
            assert r.status_code == 200, r.text
            kwargs = MockAnthropic.return_value.messages.create.call_args.kwargs

        assert "## O que o dono me ensinou sobre esta fazenda e este sistema" in kwargs["system"]
        assert "Nome da fazenda: O nome oficial é Fazenda Estreito Ponte de Pedra II." in kwargs["system"]
        assert kwargs["system"].startswith(SYSTEM_PROMPT)

    def test_ensinamento_inativo_nao_entra_no_system_prompt(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
        with Session(engine) as s:
            s.add(AssistenteEnsinamento(
                fazenda_id=1, usuario_id=1, titulo="Regra desativada",
                texto="Isto não deveria aparecer no prompt.", ativo=False,
            ))
            s.commit()

        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock("ok")
            r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
            assert r.status_code == 200, r.text
            kwargs = MockAnthropic.return_value.messages.create.call_args.kwargs

        # Sem nenhum ensinamento ATIVO, o prompt fica idêntico ao original.
        assert kwargs["system"] == SYSTEM_PROMPT
        assert "Regra desativada" not in kwargs["system"]


# ---------------------------------------------------------------------------
# Isolamento — ensinamento de uma fazenda nunca aparece/edita/apaga por outra.
# ---------------------------------------------------------------------------
class TestIsolamentoEnsinamentos:
    def test_fazenda_2_nao_le_nem_apaga_ensinamento_da_fazenda_1(self, client, monkeypatch):
        """FAZENDA_ID_PILOTO trava o Assistente na fazenda #1 por decisão de
        negócio (ver topo de fazenda/api/routers/assistente.py) — então a
        fazenda #2 nem chega a este código hoje, ela já toma 403 antes. Para
        testar o isolamento de DADOS em si (o filtro fazenda_id nas queries
        de ensinamentos, que é o que este teste cobre e precisa continuar
        correto quando o piloto abrir para mais fazendas), destrava o piloto
        temporariamente — sem isso não dá para exercitar a fazenda #2 aqui."""
        import fazenda.api.routers.assistente as assistente_router
        c, engine = client
        with Session(engine) as s:
            e = AssistenteEnsinamento(fazenda_id=1, usuario_id=1, titulo="Só da fazenda 1", texto="Segredo da fazenda 1.")
            s.add(e)
            s.commit()
            s.refresh(e)
            ensinamento_id = e.id

        monkeypatch.setattr(assistente_router, "FAZENDA_ID_PILOTO", 2)
        _como(3, 2)  # dono da fazenda 2

        r = c.get("/assistente/ensinamentos")
        assert r.status_code == 200
        assert ensinamento_id not in {x["id"] for x in r.json()}

        r = c.put(f"/assistente/ensinamentos/{ensinamento_id}", json={"titulo": "Sequestrado", "texto": "x", "ativo": True})
        assert r.status_code == 404

        r = c.delete(f"/assistente/ensinamentos/{ensinamento_id}")
        assert r.status_code == 404

        with Session(engine) as s:
            ainda_existe = s.get(AssistenteEnsinamento, ensinamento_id)
            assert ainda_existe is not None
            assert ainda_existe.titulo == "Só da fazenda 1"

        # O dono de verdade (fazenda 1) continua vendo e conseguindo mexer.
        monkeypatch.setattr(assistente_router, "FAZENDA_ID_PILOTO", 1)
        _como(1, 1)
        r = c.get("/assistente/ensinamentos")
        assert ensinamento_id in {x["id"] for x in r.json()}
        r = c.delete(f"/assistente/ensinamentos/{ensinamento_id}")
        assert r.status_code == 200

    def test_criar_ensinamento_fica_na_fazenda_do_criador(self, client):
        c, engine = client
        r = c.post("/assistente/ensinamentos", json={"titulo": "Manejo do lote 04", "texto": "Fica perto do curral velho."})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            e = s.get(AssistenteEnsinamento, r.json()["id"])
            assert e.fazenda_id == 1
            assert e.usuario_id == 1

    def test_atualizar_pode_desativar_ensinamento(self, client):
        c, engine = client
        r = c.post("/assistente/ensinamentos", json={"titulo": "T", "texto": "Texto original"})
        eid = r.json()["id"]
        r = c.put(f"/assistente/ensinamentos/{eid}", json={"titulo": "T", "texto": "Texto editado", "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False
        assert r.json()["texto"] == "Texto editado"
