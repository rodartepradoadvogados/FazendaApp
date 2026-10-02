"""
Segunda leva de ferramentas de leitura do Assistente/agente
(fazenda/rules/assistente_consultas_extra.py): indicadores por data, ficha
completa do animal, sêmen e touros, fluxo de caixa/caixa real, RMCA, dietas e
remédios por doença.

Mesmo padrão de tests/test_assistente_consultas.py:
- contrato (nome, schema, descrição em português, módulo, sem limite/offset);
- somente leitura (TODA execução roda na sessão read-only do /agente);
- isolamento por fazenda (a "fazenda 2" tem linhas marcadas SEGREDO);
- permissão de módulo;
- sanitização/paginação na saída HTTP;
- validação de parâmetros;
- CONSISTÊNCIA com o número que o site/endpoint equivalente devolve.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import MODULOS
from fazenda.models import Animal, Fazenda, Lactacao, Lote
from fazenda.rules import agente_leitura as al
from fazenda.rules import assistente_consultas_extra as ace
from fazenda.rules.assistente import _TOOLS_DISPONIVEIS, _executar_tool, _ferramentas_do_usuario
from fazenda.rules.parametros import fazenda_atual

HOJE = date.today()
TOKEN = "t" * 20 + "-token-de-teste-do-agente-" + "x" * 10
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class _Usuario:
    def __init__(self, papel="admin", permissoes=""):
        self.id, self.papel, self.permissoes, self.email = 1, papel, permissoes, None


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for v in ("AGENTE_API_TOKEN", "AGENTE_FAZENDA_ID", "AGENTE_IPS_PERMITIDOS", "AGENTE_RATE_LIMIT_POR_MIN",
              "AGENTE_MAX_BYTES", "AGENTE_MODULOS"):
        monkeypatch.delenv(v, raising=False)
    al._resetar_estado_para_testes()


def _popular(s: Session) -> None:
    """Dados de duas fazendas: a 1 é a consultada; a 2 só tem linhas 'SEGREDO'."""
    s.add(Fazenda(id=1, nome="Fazenda Um"))
    s.add(Fazenda(id=2, nome="Fazenda Dois"))
    s.commit()
    for cod, nome, st, fid in (("01", "Lactação A", "lactacao", 1), ("04", "Secas", "seca", 1), ("01", "SEGREDO", "lactacao", 2)):
        s.add(Lote(codigo=cod, nome=nome, status_lactacao=st, fazenda_id=fid, ativo=True))
    for num, nome, sexo, grupo, fid in (
        ("500", "Estrela", "F", "01 - LACTACAO A", 1), ("501", "Mimosa", "F", "01 - LACTACAO A", 1),
        ("502", "Fofa", "F", "04 - SECAS", 1), ("900", "SEGREDO", "F", "01 - LACTACAO A", 2),
    ):
        s.add(Animal(numero=num, nome=nome, sexo=sexo, fazenda_id=fid, grupo_primario=grupo, ativo=True))
    # lactações: 500 (mar–ago/2026, já secou), 501 (aberta desde jun/2026), 502 (aberta desde 2025-12 e fechada em 2026-06-15)
    s.add(Lactacao(numero_matriz="500", data_inicio=date(2026, 3, 1), data_fim=date(2026, 8, 1), fazenda_id=1))
    s.add(Lactacao(numero_matriz="501", data_inicio=date(2026, 6, 1), fazenda_id=1))
    s.add(Lactacao(numero_matriz="502", data_inicio=date(2025, 12, 1), data_fim=date(2026, 6, 15), fazenda_id=1))
    s.add(Lactacao(numero_matriz="900", data_inicio=date(2026, 1, 1), fazenda_id=2))
    s.commit()


def _preparar(s: Session) -> None:
    _popular(s)
    for fn in _POPULADORES:
        fn(s)


_POPULADORES: list = []  # cada área acrescenta o seu bloco de dados (ver mais abaixo)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        _preparar(s)
    return eng


def _rodar(engine, nome, entrada=None, fid=1, usuario=None):
    """Executa a ferramenta como o /agente: sessão SOMENTE LEITURA + contexto de fazenda."""
    with Session(engine) as s:
        gen = al.sessao_somente_leitura(s)
        next(gen)
        marca = fazenda_atual.set(fid)
        try:
            return _executar_tool(nome, dict(entrada or {}), s, usuario or _Usuario(), fid)
        finally:
            fazenda_atual.reset(marca)
            gen.close()


NOVAS = sorted(ace.NOMES)

# Parâmetros "típicos" para exercitar cada ferramenta de ponta a ponta.
TIPICOS: dict[str, dict] = {
    "consultar_indicadores_na_data": {"data": "2026-06-30"},
}
# Módulo(s) esperado(s) de cada ferramenta (qualquer um libera).
MODULOS_ESPERADOS: dict[str, tuple[str, ...]] = {
    "consultar_indicadores_na_data": ("indicadores",),
}


def test_todas_as_ferramentas_novas_tem_parametros_tipicos():
    assert set(TIPICOS) == set(NOVAS) == set(MODULOS_ESPERADOS)


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------
class TestContrato:
    @pytest.mark.parametrize("nome", NOVAS)
    def test_spec(self, nome):
        t = next(t for t in _TOOLS_DISPONIVEIS if t["spec"]["name"] == nome)
        spec = t["spec"]
        assert spec["name"] == nome and len(spec["description"]) > 120
        assert "Use para" in spec["description"]
        esquema = spec["input_schema"]
        assert esquema["type"] == "object" and esquema["additionalProperties"] is False
        # a ponte MCP acrescenta limite/offset sozinha: repetir quebraria a assinatura
        assert "limite" not in esquema["properties"] and "offset" not in esquema["properties"]
        assert set(esquema.get("required", [])) <= set(esquema["properties"])
        for k, v in esquema["properties"].items():
            assert v["type"] in ("string", "integer", "boolean") and v["description"], k
            if k.startswith("data") or k == "ancora":
                assert "AAAA-MM-DD" in v["description"], k
        modulos = (t["modulo"],) if isinstance(t["modulo"], str) else tuple(t["modulo"])
        assert set(modulos) <= set(MODULOS)
        assert set(modulos) == set(MODULOS_ESPERADOS[nome])

    def test_nomes_unicos_em_toda_a_lista(self):
        nomes = [t["spec"]["name"] for t in _TOOLS_DISPONIVEIS]
        assert len(nomes) == len(set(nomes))

    def test_modulo_fonte_nao_escreve(self):
        import inspect
        fonte = inspect.getsource(ace)
        for proibido in ("session.add(", "session.commit(", "session.flush(", "session.delete(", ".post(",
                         "_dar_baixa_automatica", "reconciliar=True", "obter_alimentacao", "necessidade_mensal("):
            assert proibido not in fonte, proibido


# ---------------------------------------------------------------------------
# Somente leitura + execução + isolamento + permissão
# ---------------------------------------------------------------------------
class TestExecucao:
    @pytest.mark.parametrize("nome", NOVAS)
    def test_executa_na_sessao_read_only(self, engine, nome):
        r = _rodar(engine, nome, TIPICOS[nome])
        assert isinstance(r, dict) and "erro" not in r, (nome, r)

    @pytest.mark.parametrize("nome", NOVAS)
    def test_nao_vaza_outra_fazenda(self, engine, nome):
        texto = json.dumps(_rodar(engine, nome, TIPICOS[nome]), default=str, ensure_ascii=False)
        assert "SEGREDO" not in texto, nome

    @pytest.mark.parametrize("nome", NOVAS)
    def test_executar_sem_modulo_e_barrado(self, engine, nome):
        r = _rodar(engine, nome, TIPICOS[nome], usuario=_Usuario("operador", ""))
        assert "erro" in r and "permissão" in r["erro"]

    @pytest.mark.parametrize("nome", NOVAS)
    def test_qualquer_modulo_da_tupla_libera(self, engine, nome):
        for modulo in MODULOS_ESPERADOS[nome]:
            nomes = {t["name"] for t in _ferramentas_do_usuario(_Usuario("operador", modulo))}
            assert nome in nomes, (nome, modulo)


# ---------------------------------------------------------------------------
# 1. Indicadores gerais por data
# ---------------------------------------------------------------------------
class TestIndicadoresNaData:
    def test_bate_com_o_endpoint_do_site(self, engine):
        from fazenda.api.routers.indicadores import calcular_indicadores_fazenda
        for data in (date(2026, 6, 30), date(2026, 9, 1), HOJE):
            r = _rodar(engine, "consultar_indicadores_na_data", {"data": data.isoformat(), "secao": "tudo"})
            with Session(engine) as s:
                site = calcular_indicadores_fazenda(s, 1, data)
            assert r["data_referencia"] == data.isoformat() == site["data_referencia"]
            assert r["rebanho"] == site["rebanho"]
            for k in ("taxa_prenhez_pct", "taxa_concepcao_pct", "iep_dias", "prenhes", "vazias", "aptas"):
                assert r["reproducao"][k] == site["reproducao"][k], k
            for k in ("producao_total_dia_kg", "del_medio", "vacas_lactacao"):
                assert r["producao"][k] == site["producao"][k], k
            assert r["benchmark"] == site["benchmark"]

    def test_lactacao_na_data_acompanha_a_tabela_lactacao(self, engine):
        # 30/06/2026: 500 (mar–ago), 501 (desde jun) e 502 (fechou 15/06 -> fora) => 2
        r = _rodar(engine, "consultar_indicadores_na_data", {"data": "30/06/2026"})
        assert r["lactacao_na_data_pela_tabela_lactacao"]["vacas_em_lactacao"] == 2
        # DEL médio = ((30/06 - 01/03)=121 + (30/06 - 01/06)=29)/2 = 75
        assert r["lactacao_na_data_pela_tabela_lactacao"]["del_medio_dias"] == 75.0
        assert _rodar(engine, "consultar_indicadores_na_data", {"data": "2026-09-01"})["lactacao_na_data_pela_tabela_lactacao"]["vacas_em_lactacao"] == 1
        assert _rodar(engine, "consultar_indicadores_na_data", {"data": "2025-12-01"})["lactacao_na_data_pela_tabela_lactacao"]["vacas_em_lactacao"] == 1
        # dia da secagem conta como FECHADA (regra de rules/lactacao.py)
        assert _rodar(engine, "consultar_indicadores_na_data", {"data": "2026-08-01"})["lactacao_na_data_pela_tabela_lactacao"]["vacas_em_lactacao"] == 1

    def test_lactacao_isolada_por_fazenda(self, engine):
        r = _rodar(engine, "consultar_indicadores_na_data", {"data": "2026-06-30"}, fid=2)
        assert r["lactacao_na_data_pela_tabela_lactacao"]["vacas_em_lactacao"] == 1
        assert r["rebanho"]["total"] == 1

    def test_aviso_de_historico_so_quando_a_data_nao_e_hoje(self, engine):
        passado = _rodar(engine, "consultar_indicadores_na_data", {"data": "2026-06-30"})
        assert passado["e_hoje"] is False and any("snapshot" in x for x in passado["limitacoes"])
        hoje = _rodar(engine, "consultar_indicadores_na_data", {})
        assert hoje["e_hoje"] is True and hoje["data_referencia"] == HOJE.isoformat()

    def test_listas_nominais_so_se_pedidas(self, engine):
        sem = _rodar(engine, "consultar_indicadores_na_data", {"secao": "reproducao"})
        com = _rodar(engine, "consultar_indicadores_na_data", {"secao": "reproducao", "incluir_listas_nominais": "true"})
        assert "gestantes_detalhe" not in sem["reproducao"] and "gestantes_detalhe" in com["reproducao"]
        assert "rebanho" not in sem and "producao" not in sem

    def test_validacao(self, engine):
        assert "Data inválida" in _rodar(engine, "consultar_indicadores_na_data", {"data": "2026-02-30"})["erro"]
        assert "5 anos" in _rodar(engine, "consultar_indicadores_na_data", {"data": "2015-01-01"})["erro"]
        assert "secao" in _rodar(engine, "consultar_indicadores_na_data", {"secao": "xyz"})["erro"]


# ---------------------------------------------------------------------------
# Sanitização e paginação na saída HTTP (/agente)  +  chat do site
# ---------------------------------------------------------------------------
@pytest.fixture
def client(engine, monkeypatch):
    import main
    import fazenda.database as database

    def _sess():
        with Session(engine) as s:
            yield s
    monkeypatch.setenv("AGENTE_API_TOKEN", TOKEN)
    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


class TestHttpEChat:
    @pytest.mark.parametrize("nome", NOVAS)
    def test_todas_respondem_200_pelo_agente(self, client, nome):
        r = client.get(f"/agente/consultar/{nome}", params=TIPICOS[nome], headers=AUTH)
        assert r.status_code == 200, (nome, r.text)
        assert "resultado" in r.json() and "SEGREDO" not in r.text

    @pytest.mark.parametrize("nome", NOVAS)
    def test_aparecem_na_lista_de_ferramentas_do_agente(self, client, nome):
        nomes = {f["nome"] for f in client.get("/agente/ferramentas", headers=AUTH).json()["ferramentas"]}
        assert nome in nomes

    def test_chat_usa_o_formatador_no_laco_de_tool_use(self, engine, monkeypatch):
        from fazenda.rules import assistente, assistente_llm
        respostas = iter([
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "consultar_indicadores_na_data", "arguments": {"data": "2026-06-30"}}]},
            {"role": "assistant", "content": "ok"},
        ])
        monkeypatch.setattr(assistente_llm, "completar", lambda *a, **k: next(respostas))
        with Session(engine) as s:
            out = assistente.responder("indicadores de 30/06?", [], s, _Usuario(), 1)
        tool_msg = next(m for m in out["historico"] if m.get("role") == "tool")
        assert "lactacao_na_data_pela_tabela_lactacao" in tool_msg["content"]
