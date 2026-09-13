"""
Testes do protótipo do Assistente Claude — cobrem o que dá para testar sem
uma chave real da API (a conversa fica aberta a qualquer usuário logado,
permissões por ferramenta, mensagem vazia, ferramentas isoladas e o erro
claro quando ANTHROPIC_API_KEY não está configurada). O laço de tool-use em
si (que de fato chama a Claude) é coberto em TestSystemPromptComEnsinamentos
com a API mockada; os testes do gate de TREINO (admin-only) + isolamento de
ensinamentos entre fazendas ficam em test_assistente_ensinamentos.py
(fixture própria).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Animal, ContaGerencial, ContratoFazenda, Estoque, ExameResultado, Fazenda, Lote
from fazenda.models.sanidade import CalendarioSanitario, EventoSanitario
from fazenda.rules.assistente import (
    _executar_tool,
    _ferramentas_do_usuario,
    _tool_buscar_animal,
    _tool_consultar_calendario_sanitario,
    _tool_consultar_estoque,
    _tool_consultar_exames,
    _tool_consultar_financeiro,
    _tool_consultar_indicadores,
    _tool_consultar_lote,
    _tool_listar_lotes,
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
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import fazenda.database as database
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="admin")

    # Existindo fazenda cadastrada, `exigir_fazenda_selecionada` (main.py)
    # recusa toda rota de fazenda cuja sessão não diga em qual delas está —
    # e, com a fazenda selecionada, a trava de contrato ativo passa a valer
    # (as duas eram puladas juntas pela mesma tolerância a "sem fazenda").
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with Session(engine) as s:
        s.add(Animal(numero="500", nome="Estrela", sexo="F", raca="Girolando", fazenda_id=1))
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
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
    """A conversa é aberta a qualquer usuário logado da fazenda piloto — só o
    TREINO (ensinamentos) é restrito a admin (ver test_assistente_ensinamentos.py).
    Troca o papel para operador e confirma que /perguntar continua passando
    pelo gate — ainda 503 (sem chave), não 403."""
    c, engine = client
    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="operador", permissoes="")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
    # Ainda dá 503 (sem chave), não 403 — ou seja, passou pelo gate de acesso normalmente.
    assert r.status_code == 503


class TestPermissoesPorFerramenta:
    def test_admin_ve_todas_as_ferramentas(self):
        nomes = {t["name"] for t in _ferramentas_do_usuario(_Usuario(papel="admin"))}
        assert {"consultar_indicadores", "buscar_animal", "consultar_agenda_hoje",
                "consultar_financeiro", "consultar_estoque", "consultar_calendario_sanitario",
                "consultar_analise_reprodutiva", "listar_lotes", "consultar_lote", "consultar_exames"} <= nomes

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

    def test_listar_lotes(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="04", nome="SECAS"))
            s.add(Animal(numero="600", sexo="F", grupo_primario="04 - SECAS"))
            s.commit()
            resultado = _tool_listar_lotes(s)
        lote04 = next(l for l in resultado["lotes"] if l["codigo"] == "04")
        # "500" (fixture do client) fica sem grupo_primario e não conta em nenhum lote.
        assert lote04 == {"codigo": "04", "nome": "SECAS", "total_animais": 1}

    def test_consultar_lote_encontrado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="04", nome="SECAS"))
            s.add(Animal(numero="600", sexo="F", grupo_primario="04 - SECAS", del_dias=300))
            s.commit()
            resultado = _tool_consultar_lote(s, "4")
        assert resultado["nome"] == "SECAS"
        assert resultado["total_animais"] == 1
        assert resultado["animais"][0] == {
            "numero": "600", "categoria": None, "del_dias": 300, "sit_rep": None, "diagnostico": None,
        }

    def test_consultar_lote_inexistente(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_consultar_lote(s, "99")
        assert "erro" in resultado

    def test_consultar_exames_sem_filtro_pede_para_refinar(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_consultar_exames(s, None, None)
        assert "erro" in resultado

    def test_consultar_exames_por_data_e_doenca(self, client):
        c, engine = client
        with Session(engine) as s:
            evento = EventoSanitario(nome="Brucelose B19")
            s.add(evento)
            s.commit()
            s.refresh(evento)
            s.add(ExameResultado(numero_matriz="500", evento_sanitario_id=evento.id, data_exame=date(2026, 7, 16), resultado="positivo"))
            s.add(ExameResultado(numero_matriz="501", evento_sanitario_id=evento.id, data_exame=date(2026, 7, 10), resultado="negativo"))
            s.commit()
            por_data = _tool_consultar_exames(s, "2026-07-16", None)
            por_doenca = _tool_consultar_exames(s, None, "brucelose")
        assert por_data["total"] == 1
        assert por_data["exames"][0] == {"numero_animal": "500", "evento": "Brucelose B19", "data_exame": "2026-07-16", "resultado": "positivo", "veterinario": None}
        assert por_doenca["total"] == 2

    def test_consultar_exames_data_invalida(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_consultar_exames(s, "16/07/2026", None)
        assert "erro" in resultado

    def test_consultar_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração", categoria="alimento", quantidade=5, estoque_minimo=20, abaixo_minimo=True))
            s.add(Estoque(nome="Sal mineral", categoria="alimento", quantidade=100, estoque_minimo=10, abaixo_minimo=False))
            s.commit()
            resultado = _tool_consultar_estoque(s)
        assert resultado["qtd_abaixo_do_minimo"] == 1
        assert resultado["abaixo_do_minimo"][0]["nome"] == "Ração"


class TestFerramentasIsolamentoFazenda:
    """FURO DE MULTI-TENANT CORRIGIDO: `_tool_listar_lotes`/
    `_tool_consultar_lote` liam `Lote` (e `_tool_consultar_indicadores` lia
    `PesagemCorporal`) sem filtrar fazenda_id, com um comentário afirmando
    (incorretamente, desde a Fase 4A) que essas tabelas "ainda não têm
    fazenda_id" — o Assistente de uma fazenda via lotes/pesos de OUTRA."""

    def test_listar_lotes_nao_mistura_fazendas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="09", nome="Lote da fazenda 1", fazenda_id=1))
            s.add(Lote(codigo="09", nome="Lote da fazenda 2", fazenda_id=2))
            s.commit()
            resultado_f1 = _tool_listar_lotes(s, fazenda_id=1)
            resultado_f2 = _tool_listar_lotes(s, fazenda_id=2)
        assert resultado_f1["lotes"][0]["nome"] == "Lote da fazenda 1"
        assert resultado_f2["lotes"][0]["nome"] == "Lote da fazenda 2"

    def test_consultar_lote_nao_mistura_fazendas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="09", nome="Lote da fazenda 1", fazenda_id=1))
            s.add(Lote(codigo="09", nome="Lote da fazenda 2", fazenda_id=2))
            s.commit()
            resultado_f2 = _tool_consultar_lote(s, "9", fazenda_id=2)
        assert resultado_f2["nome"] == "Lote da fazenda 2"
