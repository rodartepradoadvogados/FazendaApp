"""
Testes do protótipo do Assistente Claude — cobrem o que dá para testar sem
uma chave real da API (aberto a qualquer usuário, permissões por ferramenta,
mensagem vazia, ferramentas isoladas e o erro claro quando ANTHROPIC_API_KEY
não está configurada). O laço de tool-use em si (que de fato chama a Claude)
não é coberto aqui — é comportamento da API externa, não lógica nossa.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Animal, ContaGerencial, Estoque
from fazenda.models.sanidade import CalendarioSanitario, EventoSanitario
from fazenda.rules.assistente import (
    _executar_tool,
    _ferramentas_do_usuario,
    _tool_buscar_animal,
    _tool_consultar_calendario_sanitario,
    _tool_consultar_estoque,
    _tool_consultar_financeiro,
    _tool_consultar_indicadores,
)


class _Usuario:
    def __init__(self, papel="admin", permissoes=""):
        self.id = 1
        self.papel = papel
        self.permissoes = permissoes
        self.ativo = True
        self.username = "teste"


@pytest.fixture
def client():
    import main
    from fazenda.auth import get_current_user

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import fazenda.database as database
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="admin")

    with Session(engine) as s:
        s.add(Animal(numero="500", nome="Estrela", sexo="F", raca="Girolando"))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def test_rejeita_mensagem_vazia(client):
    c, engine = client
    r = c.post("/assistente/perguntar", json={"mensagem": "   "})
    assert r.status_code == 400


def test_sem_api_key_retorna_503(client, monkeypatch):
    c, engine = client
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_usuario_comum_tambem_acessa_o_endpoint(client, monkeypatch):
    """Qualquer usuário logado pode falar com o assistente — não é mais admin-only."""
    c, engine = client
    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="operador", permissoes="")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
    # Ainda dá 503 (sem chave), não 403 — ou seja, passou pela autenticação normalmente.
    assert r.status_code == 503


class TestPermissoesPorFerramenta:
    def test_admin_ve_todas_as_ferramentas(self):
        nomes = {t["name"] for t in _ferramentas_do_usuario(_Usuario(papel="admin"))}
        assert {"consultar_indicadores", "buscar_animal", "consultar_agenda_hoje",
                "consultar_financeiro", "consultar_estoque", "consultar_calendario_sanitario",
                "consultar_analise_reprodutiva"} <= nomes

    def test_usuario_sem_permissoes_nao_ve_nenhuma(self):
        assert _ferramentas_do_usuario(_Usuario(papel="operador", permissoes="")) == []

    def test_usuario_so_com_financeiro_so_ve_essa_ferramenta(self):
        nomes = {t["name"] for t in _ferramentas_do_usuario(_Usuario(papel="operador", permissoes="financeiro"))}
        assert nomes == {"consultar_financeiro"}

    def test_executar_tool_bloqueia_sem_permissao(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _executar_tool("consultar_financeiro", {}, s, _Usuario(papel="operador", permissoes="rebanho"))
        assert "erro" in resultado
        assert "permissão" in resultado["erro"]


class TestFerramentas:
    def test_consultar_indicadores(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_consultar_indicadores(s)
        assert "rebanho" in resultado
        assert "reproducao" in resultado

    def test_buscar_animal_encontrado(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_buscar_animal(s, "500")
        assert resultado["nome"] == "Estrela"

    def test_buscar_animal_inexistente(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_buscar_animal(s, "999")
        assert "erro" in resultado

    def test_consultar_financeiro(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(ContaGerencial(tipo="despesa", valor_total=1000.0, valor_pago=0.0, data_vencimento=date.today() - timedelta(days=5)))
            s.add(ContaGerencial(tipo="receita", valor_total=500.0, valor_pago=0.0, data_vencimento=date.today() + timedelta(days=5)))
            s.commit()
            resultado = _tool_consultar_financeiro(s)
        assert resultado["total_em_aberto_a_pagar"] == 1000.0
        assert resultado["total_em_aberto_a_receber"] == 500.0
        assert resultado["qtd_contas_vencidas_a_pagar"] == 1
        assert resultado["qtd_contas_vencidas_a_receber"] == 0

    def test_consultar_calendario_sanitario_chamado_direto_sem_fazenda_resolvida(self, client):
        """listar_calendario é chamado diretamente (sem passar por FastAPI/Depends)
        por este tool — fazenda_id chega como o sentinel Depends(...) não resolvido,
        não como int/None. Sem normalizar via fazenda_id_seguro(), o filtro
        `CalendarioSanitario.fazenda_id == fazenda_id` compara contra esse objeto
        e nunca bate com a regra legada (fazenda_id=None), quebrando a ferramenta."""
        c, engine = client
        with Session(engine) as s:
            evento = EventoSanitario(nome="Vermífugo")
            s.add(evento)
            s.commit()
            s.refresh(evento)
            s.add(CalendarioSanitario(
                evento_sanitario_id=evento.id, frequencia_valor=5, frequencia_unidade="dias",
                data_evento=date.today(),
            ))
            s.commit()
            resultado = _tool_consultar_calendario_sanitario(s)
        assert resultado["total"] == 1
        assert resultado["proximos"][0]["evento"] == "Vermífugo"

    def test_consultar_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração", categoria="alimento", quantidade=5, estoque_minimo=20, abaixo_minimo=True))
            s.add(Estoque(nome="Sal mineral", categoria="alimento", quantidade=100, estoque_minimo=10, abaixo_minimo=False))
            s.commit()
            resultado = _tool_consultar_estoque(s)
        assert resultado["qtd_abaixo_do_minimo"] == 1
        assert resultado["abaixo_do_minimo"][0]["nome"] == "Ração"
