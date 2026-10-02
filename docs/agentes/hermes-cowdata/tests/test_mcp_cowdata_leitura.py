"""
Testes da ponte MCP contra o backend de teste (SQLite em memoria, sem rede).

Como rodar (de dentro de backend/, com `mcp<2` instalado no mesmo ambiente):
  cd backend && env -u DATABASE_URL PYTHONPATH=../docs/agentes/hermes-cowdata \
    python -m pytest ../docs/agentes/hermes-cowdata/tests -q -p no:cacheprovider
"""
import asyncio
import json
import os
import tempfile

# Nunca tocar em banco real: forca SQLite descartavel ANTES de importar o backend.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest

pytest.importorskip("mcp")

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import mcp_cowdata_leitura as ponte

TOKEN = "m" * 48


class _ClienteTeste:
    """Faz o papel do httpx.Client da ponte, falando com o app em memoria."""

    def __init__(self, tc: TestClient, token: str):
        self.tc, self.token = tc, token

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, caminho, params=None):
        return self.tc.get(caminho, params=params, headers={"Authorization": f"Bearer {self.token}"})


@pytest.fixture
def backend(monkeypatch):
    import main
    import fazenda.database as database
    from fazenda.models import Animal, Fazenda, AssistenteEnsinamento

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(Animal(numero="500", nome="Estrela", sexo="F", fazenda_id=1))
        s.add(AssistenteEnsinamento(fazenda_id=1, usuario_id=1, titulo="Regra", texto="Lote 4 e de secas."))
        s.commit()

    def _sess():
        with Session(eng) as s:
            yield s

    for v in ("AGENTE_IPS_PERMITIDOS", "AGENTE_FAZENDA_ID", "AGENTE_MODULOS", "AGENTE_RATE_LIMIT_POR_MIN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("AGENTE_API_TOKEN", TOKEN)
    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as tc:
        estado = {"token": TOKEN}
        monkeypatch.setattr(ponte, "_criar_cliente", lambda: _ClienteTeste(tc, estado["token"]))
        yield estado
    main.app.dependency_overrides.clear()


def _chamar(servidor, nome, args):
    resultado = asyncio.run(servidor.call_tool(nome, args))
    # FastMCP 1.x devolve (conteudos, estruturado) ou lista de conteudos
    conteudos = resultado[0] if isinstance(resultado, tuple) else resultado
    return conteudos[0].text


def test_uma_ferramenta_por_ferramenta_da_api_mais_instrucoes(backend):
    from fazenda.rules.assistente import _TOOLS_DISPONIVEIS
    servidor = ponte.construir_servidor()
    nomes = {t.name for t in asyncio.run(servidor.list_tools())}
    esperado = {t["spec"]["name"] for t in _TOOLS_DISPONIVEIS} | {"instrucoes_cowdata"}
    assert nomes == esperado


def test_schema_dos_parametros(backend):
    servidor = ponte.construir_servidor()
    tools = {t.name: t for t in asyncio.run(servidor.list_tools())}
    esquema = tools["buscar_animal"].inputSchema
    assert "numero" in esquema["properties"] and "numero" in esquema.get("required", [])
    assert "limite" in esquema["properties"] and "limite" not in esquema.get("required", [])
    assert "Somente leitura" in tools["buscar_animal"].description or tools["buscar_animal"].description


def test_ferramentas_com_periodo_viram_ferramentas_mcp_com_parametros(backend):
    """As ferramentas com data_inicio/data_fim (ex.: taxa de concepcao do periodo) chegam ao Hermes com os
    parametros, sem 'limite'/'offset' duplicados, e a consulta devolve o numero do periodo."""
    servidor = ponte.construir_servidor()
    tools = {t.name: t for t in asyncio.run(servidor.list_tools())}
    esquema = tools["consultar_indicadores_reprodutivos"].inputSchema
    for p in ("data_inicio", "data_fim", "touro", "agrupar_por", "limite", "offset"):
        assert p in esquema["properties"], p
    assert not esquema.get("required")
    assert "relatorio" in tools["executar_relatorio"].inputSchema.get("required", [])
    assert {"consultar_pedidos", "consultar_cotacoes", "consultar_contas_financeiras", "consultar_estoque_itens",
            "consultar_producao_leite", "consultar_lista_espera_preventivo", "listar_relatorios"} <= set(tools)
    dados = json.loads(_chamar(servidor, "consultar_indicadores_reprodutivos",
                               {"data_inicio": "2026-01-01", "data_fim": "2026-07-01"}))
    assert dados["ferramenta"] == "consultar_indicadores_reprodutivos" and dados["resultado"]["servicos_total"] == 0
    erro = json.loads(_chamar(servidor, "consultar_indicadores_reprodutivos", {"data_inicio": "2026-13-01", "data_fim": "2026-07-01"}))
    assert "Data inválida" in erro["resultado"]["erro"] or "Data invalida" in erro["resultado"]["erro"]


def test_consulta_devolve_dados_reais(backend):
    servidor = ponte.construir_servidor()
    dados = json.loads(_chamar(servidor, "buscar_animal", {"numero": "500"}))
    assert dados["resultado"]["nome"] == "Estrela" and dados["ferramenta"] == "buscar_animal"


def test_ferramenta_sem_parametros(backend):
    servidor = ponte.construir_servidor()
    dados = json.loads(_chamar(servidor, "listar_lotes", {}))
    assert "resultado" in dados


def test_instrucoes(backend):
    servidor = ponte.construir_servidor()
    dados = json.loads(_chamar(servidor, "instrucoes_cowdata", {}))
    assert "Regra: Lote 4 e de secas." in dados["instrucoes"]


def test_token_errado_vira_erro_claro_sem_vazar(backend):
    servidor = ponte.construir_servidor()
    backend["token"] = "x" * 48
    texto = _chamar(servidor, "buscar_animal", {"numero": "500"})
    assert "Token do agente recusado" in texto and "x" * 48 not in texto and TOKEN not in texto


def test_modo_degradado_quando_a_lista_nao_carrega(backend):
    backend["token"] = "x" * 48  # /ferramentas devolve 401 na partida
    servidor = ponte.construir_servidor()
    nomes = {t.name for t in asyncio.run(servidor.list_tools())}
    assert nomes == {"instrucoes_cowdata", "consultar_cowdata"}


def test_timeout_e_rede(monkeypatch):
    class _Estoura:
        def __init__(self, exc): self.exc = exc
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): raise self.exc

    monkeypatch.setattr(ponte, "_criar_cliente", lambda: _Estoura(httpx.ReadTimeout("lento")))
    assert "timeout" in ponte._get("/agente/saude")["erro"].lower()
    monkeypatch.setattr(ponte, "_criar_cliente", lambda: _Estoura(httpx.ConnectError("dns")))
    assert "rede" in ponte._get("/agente/saude")["erro"].lower()


def test_sem_variaveis_de_ambiente(monkeypatch):
    monkeypatch.delenv("COWDATA_API_URL", raising=False)
    monkeypatch.delenv("COWDATA_AGENTE_TOKEN", raising=False)
    assert "COWDATA_API_URL" in ponte._get("/agente/saude")["erro"]


def test_so_usa_get():
    import inspect
    fonte = inspect.getsource(ponte)
    for verbo in (".post(", ".put(", ".patch(", ".delete("):
        assert verbo not in fonte
