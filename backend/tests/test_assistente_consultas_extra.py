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
from fazenda.models import (
    Animal, BaixaAnimal, CompraAnimal, ControleLeiteiro, EventoSanitario, ExameResultado, Fazenda, Lactacao, Lote,
    CompraSemen, EstoqueSemen, MovimentoLote, OcorrenciaClinica, Parto, PesagemCorporal, Sanidade, Secagem, Servico, Touro,
)
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


# ---------------------------------------------------------------------------
# Dados da ficha do animal (a "500" existe nas duas fazendas: a da fazenda 2 é toda SEGREDO)
# ---------------------------------------------------------------------------
def _popular_ficha(s: Session) -> None:
    s.add(Animal(numero="500", nome="SEGREDO", sexo="F", fazenda_id=2, grupo_primario="01 - SEGREDO", ativo=True, mae_numero="SEGREDO"))
    a = s.exec(select(Animal).where(Animal.numero == "500", Animal.fazenda_id == 1)).one()
    a.mae_numero, a.mae_nome, a.pai_nome, a.pai_naab = "100", "Vaca Mae", "TouroA", "7HO00001"
    a.avo_paterno_nome = "AvoPat"
    s.add(a)
    s.add(Animal(numero="100", nome="Vaca Mae", sexo="F", fazenda_id=1, grupo_primario="04 - SECAS", ativo=True))
    s.add(Parto(numero_matriz="500", data_parto=date(2026, 3, 1), tipo_parto="normal", ordem_parto=1, fazenda_id=1))
    s.add(Parto(numero_matriz="500", data_parto=date(2025, 1, 10), tipo_parto="normal", ordem_parto=1, fazenda_id=1))
    s.add(Parto(numero_matriz="500", data_parto=date(2026, 3, 1), tipo_parto="SEGREDO", fazenda_id=2))
    for dia, diag, touro, fid in ((date(2026, 4, 10), "NEGATIVO", "TouroA", 1), (date(2026, 5, 10), "POSITIVO", "TouroB", 1),
                                  (date(2026, 5, 11), "POSITIVO", "TouroSEGREDO", 2)):
        s.add(Servico(numero_matriz="500", data_servico=dia, tipo_servico="Inseminação", reprodutor=touro, diagnostico=diag,
                      data_diagnostico=dia + timedelta(days=30), ordem_tentativa=1, fazenda_id=fid))
    for d, kg, fid in ((date(2026, 3, 20), 30.0, 1), (date(2026, 4, 20), 28.0, 1), (date(2026, 5, 20), 26.5, 1), (date(2026, 4, 20), 99.0, 2)):
        s.add(ControleLeiteiro(numero_matriz="500", data_controle=d, producao_kg=kg, fazenda_id=fid))
    s.add(PesagemCorporal(numero_matriz="500", data_pesagem=date(2026, 2, 1), peso_kg=610.0, fazenda_id=1))
    s.add(PesagemCorporal(numero_matriz="500", data_pesagem=date(2026, 2, 1), peso_kg=999.0, fazenda_id=2))
    s.add(Sanidade(numero_matriz="500", data_aplicacao=date(2026, 3, 5), produto="Ivermectina", fazenda_id=1,
                   obs="contato fulano@exemplo.com CPF 123.456.789-09"))
    s.add(Sanidade(numero_matriz="500", data_aplicacao=date(2026, 3, 5), produto="Produto SEGREDO", fazenda_id=2))
    s.add(MovimentoLote(numero_matriz="500", lote_origem="04", lote_destino="01", data_movimento=date(2026, 3, 2), fazenda_id=1))
    s.add(MovimentoLote(numero_matriz="500", lote_origem="04", lote_destino="SEGREDO", data_movimento=date(2026, 3, 2), fazenda_id=2))
    s.add(Secagem(numero_matriz="500", data_secagem=date(2025, 11, 10), motivo="rotina", fazenda_id=1))
    s.add(OcorrenciaClinica(numero_matriz="500", doenca="Mastite", data_ocorrencia=date(2026, 4, 2), fazenda_id=1))
    s.add(OcorrenciaClinica(numero_matriz="500", doenca="Doenca SEGREDO", data_ocorrencia=date(2026, 4, 2), fazenda_id=2))
    s.add(CompraAnimal(numero_animal="500", vendedor="Vendedor X", valor=9000.0, tipo_valor="por_animal", data_compra=date(2024, 5, 1),
                       gta="GTA-1", fazenda_id=1))
    s.add(CompraAnimal(numero_animal="500", vendedor="Vendedor SEGREDO", valor=1.0, tipo_valor="por_animal", data_compra=date(2024, 5, 1), fazenda_id=2))
    ev = EventoSanitario(nome="Brucelose", fazenda_id=1)
    s.add(ev)
    s.commit()
    s.add(ExameResultado(numero_matriz="500", evento_sanitario_id=ev.id, data_exame=date(2026, 2, 2), resultado="negativo",
                         veterinario="Dr. A", fazenda_id=1))
    s.commit()


_POPULADORES.append(_popular_ficha)


# ---------------------------------------------------------------------------
# Sêmen e touros
# ---------------------------------------------------------------------------
def _popular_semen(s: Session) -> None:
    s.add(Touro(naab="7HO00001", nome="TouroA", central="ABS", raca="Holandês", tpi=2800.0, nm_dolar=700.0, leite_kg=900.0,
                dados_extra=json.dumps([["Prodigens", "123"]])))
    s.add(Touro(naab="7HO00002", nome="TouroB", central="Alta", raca="Holandês", tpi=2950.0, nm_dolar=650.0))
    s.add(Touro(naab="7JE00003", nome="TouroJersey", central="ABS", raca="Jersey", tpi=None, nm_dolar=None))
    ea = EstoqueSemen(touro_nome="TouroA", naab="7HO00001", central="ABS", tipo="convencional", doses=5, valor_unitario=50.0,
                      local_armazenamento="Caneca 1", fazenda_id=1)
    eb = EstoqueSemen(touro_nome="TouroB", naab="7HO00002", tipo="sexado", doses=0, valor_unitario=120.0, fazenda_id=1)
    ec = EstoqueSemen(touro_nome="Sevaverde", tipo="fazenda", doses=0, fazenda_id=1)
    ed = EstoqueSemen(touro_nome="TouroInativo", tipo="convencional", doses=9, ativo=False, fazenda_id=1)
    es = EstoqueSemen(touro_nome="TouroSEGREDO", naab="7HO00001", tipo="convencional", doses=77, fazenda_id=2)
    s.add_all([ea, eb, ec, ed, es])
    s.commit()
    s.add(CompraSemen(estoque_semen_id=ea.id, touro_nome="TouroA", naab="7HO00001", origem="estoque", tipo="convencional", doses=10,
                      valor_unitario=50.0, vendedor="Central ABS", data_compra=date(2026, 2, 1), fazenda_id=1))
    s.add(CompraSemen(estoque_semen_id=es.id, touro_nome="TouroSEGREDO", origem="estoque", tipo="convencional", doses=99,
                      valor_unitario=1.0, vendedor="SEGREDO", data_compra=date(2026, 2, 1), fazenda_id=2))
    s.add(Servico(numero_matriz="501", data_servico=date(2026, 2, 10), tipo_servico="Inseminação", reprodutor="TouroA", diagnostico="POSITIVO",
                  data_diagnostico=date(2026, 3, 10), fazenda_id=1))
    s.commit()


_POPULADORES.append(_popular_semen)


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
    "consultar_ficha_animal": {"numero": "500", "secoes": "todas"},
    "consultar_estoque_semen": {"incluir_provas": "true"},
    "consultar_touros_catalogo": {},
    "consultar_uso_semen": {"data_inicio": "2026-01-01", "data_fim": "2026-07-01", "incluir_prova_ao_vivo": "true"},
}
# Módulo(s) esperado(s) de cada ferramenta (qualquer um libera).
MODULOS_ESPERADOS: dict[str, tuple[str, ...]] = {
    "consultar_indicadores_na_data": ("indicadores",),
    "consultar_ficha_animal": ("rebanho",),
    "consultar_estoque_semen": ("rebanho", "reproducao"),
    "consultar_touros_catalogo": ("rebanho", "reproducao"),
    "consultar_uso_semen": ("rebanho", "reproducao", "analise"),
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
        assert r["rebanho"]["total"] == 2  # 900 e a 500 da fazenda 2

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
# 2. Ficha completa do animal
# ---------------------------------------------------------------------------
class TestFichaAnimal:
    def _ficha_site(self, engine, numero="500", fid=1):
        from fazenda.api.routers.animais import ficha_animal
        with Session(engine) as s:
            return ficha_animal(numero=numero, session=s, fazenda_id=fid)

    def test_secoes_batem_com_o_endpoint_da_ficha(self, engine):
        site = self._ficha_site(engine)
        r = _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "todas"})
        assert r["totais"]["partos"] == len(site["partos"]) == 2
        assert r["totais"]["servicos"] == len(site["servicos"]) == 2
        assert r["totais"]["producao"] == len(site["controles_leiteiros"]) == 3
        assert [p["data_parto"] for p in r["partos"]] == ["2026-03-01", "2025-01-10"]  # mais recente primeiro
        assert [p["ordem_parto"] for p in r["partos"]] == ["2 de 2", "1 de 2"]  # ordem cronológica, como a tela
        assert r["cadastro"]["nome"] == "Estrela" and r["cadastro"]["del_dias"] == site["animal"]["del_dias"]
        assert r["previsoes"]["previsao_parto"] == site["previsao_parto"].isoformat()
        assert r["lactacoes"]["quadro_por_parto"] == site["resumo_partos"]
        assert [(x["numero_lactacao"], x["aberta"]) for x in r["lactacoes"]["registros_de_lactacao"]] == [(1, False)]
        assert r["genealogia"]["mae_numero"] == "100" and r["genealogia"]["pai_nome"] == "TouroA"
        assert r["totais"]["sanidade"] == 1 and r["totais"]["exames"] == 1 and r["totais"]["ocorrencias"] == 1
        assert r["comercial"]["gtas"] == ["GTA-1"] and r["comercial"]["compras"][0]["vendedor"] == "Vendedor X"
        assert r["totais"]["movimentacoes"] == 1 and r["totais"]["secagens"] == 1 and r["totais"]["pesagens"] == 1

    def test_estado_reprodutivo_ao_vivo_igual_ao_endpoint(self, engine):
        from fazenda.api.routers.indicadores import estados_reprodutivos
        with Session(engine) as s:
            site = next(e for e in estados_reprodutivos(data=HOJE, fazenda_id=1, session=s)["animais"] if e["numero"] == "500")
        r = _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "estado_reprodutivo"})
        assert r["estado_reprodutivo"] == site and list(r) == ["numero", "secoes_incluidas", "totais", "estado_reprodutivo", "como_ler"]

    def test_diagnosticos_sao_a_visao_dos_servicos(self, engine):
        r = _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "diagnosticos"})
        assert [(d["data_servico"], d["diagnostico"], d["reprodutor"]) for d in r["diagnosticos"]] == [
            ("2026-05-10", "POSITIVO", "TouroB"), ("2026-04-10", "NEGATIVO", "TouroA")]

    def test_padrao_e_compacto_e_secoes_selecionaveis(self, engine):
        r = _rodar(engine, "consultar_ficha_animal", {"numero": "500"})
        assert set(r) >= {"cadastro", "genealogia", "estado_reprodutivo", "previsoes", "lactacoes"} and "producao" not in r and "partos" not in r
        r = _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "pesagens, Produção"})
        assert "pesagens" in r and "producao" in r and "cadastro" not in r
        assert "curva_wood" in _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "curvas"})["curvas"]

    def test_periodo_e_max_itens(self, engine):
        r = _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "producao", "data_inicio": "2026-04-01", "data_fim": "2026-05-31"})
        assert [c["data_controle"] for c in r["producao"]] == ["2026-05-20", "2026-04-20"] and r["totais"]["producao"] == 2
        r = _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "producao", "max_itens": "1"})
        assert len(r["producao"]) == 1 and r["totais"]["producao"] == 3 and r["limitado_pelo_max_itens"] == ["producao"]

    def test_isolamento_mesmo_numero_em_duas_fazendas(self, engine):
        r2 = _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "todas"}, fid=2)
        assert r2["cadastro"]["nome"] == "SEGREDO" and r2["totais"]["servicos"] == 1 and r2["totais"]["producao"] == 1
        r1 = json.dumps(_rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "todas"}, fid=1), default=str)
        assert "SEGREDO" not in r1 and "999" not in r1 and "99.0" not in r1
        assert "erro" in _rodar(engine, "consultar_ficha_animal", {"numero": "900"}, fid=1)  # animal da fazenda 2

    def test_animal_inexistente_e_numero_obrigatorio(self, engine):
        assert "não encontrado" in _rodar(engine, "consultar_ficha_animal", {"numero": "99999"})["erro"]
        assert "numero" in _rodar(engine, "consultar_ficha_animal", {})["erro"]

    def test_validacao(self, engine):
        assert "inválida" in _rodar(engine, "consultar_ficha_animal", {"numero": "500", "secoes": "xyz"})["erro"]
        assert "Data inválida" in _rodar(engine, "consultar_ficha_animal", {"numero": "500", "data_inicio": "2026-13-01", "data_fim": "2026-12-01"})["erro"]
        assert "invertido" in _rodar(engine, "consultar_ficha_animal", {"numero": "500", "data_inicio": "2026-07-01", "data_fim": "2026-01-01"})["erro"]
        assert "5 anos" in _rodar(engine, "consultar_ficha_animal", {"numero": "500", "data_inicio": "2019-01-01", "data_fim": "2026-01-01"})["erro"]
        assert "max_itens" in _rodar(engine, "consultar_ficha_animal", {"numero": "500", "max_itens": "0"})["erro"]

    def test_sanitizacao_na_saida_http(self, client):
        r = client.get("/agente/consultar/consultar_ficha_animal", params={"numero": "500", "secoes": "sanidade"}, headers=AUTH)
        assert "fulano@exemplo.com" not in r.text and "123.456.789-09" not in r.text
        assert "[e-mail oculto]" in r.text and "***.***.***-09" in r.text

    def test_listas_paginadas_no_agente(self, client):
        r = client.get("/agente/consultar/consultar_ficha_animal", params={"numero": "500", "secoes": "producao", "limite": "1"}, headers=AUTH).json()
        assert r["truncado"] is True and len(r["resultado"]["producao"]) == 1 and r["resultado"]["totais"]["producao"] == 3

# ---------------------------------------------------------------------------
# 3. Sêmen e touros
# ---------------------------------------------------------------------------
class TestSemenETouros:
    def test_estoque_bate_com_o_endpoint_do_site(self, engine):
        from fazenda.api.routers.cadastro.genetica import listar_estoque_semen, semen_disponivel
        with Session(engine) as s:
            site = [i for i in listar_estoque_semen(session=s, fazenda_id=1) if i["ativo"]]
            painel = semen_disponivel(session=s, fazenda_id=1)
        r = _rodar(engine, "consultar_estoque_semen", {})
        assert {i["touro"]: i["doses"] for i in r["itens"]} == {i["touro_nome"]: i["doses"] for i in site}
        assert r["total_doses"] == sum(i["doses"] for i in site) == 5
        assert r["painel_do_site"]["totais_convencional_sexado"] == painel["totais"]
        assert r["painel_do_site"]["minimos"] == painel["minimos"]
        a = next(i for i in r["itens"] if i["touro"] == "TouroA")
        assert a["valor_total_em_estoque"] == 250.0 and a["local_armazenamento"] == "Caneca 1" and a["naab"] == "7HO00001"

    def test_estoque_filtros(self, engine):
        nomes = lambda **kw: {i["touro"] for i in _rodar(engine, "consultar_estoque_semen", kw)["itens"]}  # noqa: E731
        assert nomes(situacao="disponivel") == {"TouroA"}
        assert nomes(situacao="zerado") == {"TouroB", "Sevaverde"}
        assert nomes(tipo="sexado") == {"TouroB"} and nomes(tipo="fazenda") == {"Sevaverde"}
        assert nomes(touro="7ho0000") == {"TouroA", "TouroB"} and nomes(local="caneca 1") == {"TouroA"}
        assert "TouroInativo" in nomes(incluir_inativos="true") and "TouroInativo" not in nomes()

    def test_estoque_provas_e_prova_media_do_site(self, engine):
        from fazenda.api.routers.cadastro.genetica import prova_media_semen
        r = _rodar(engine, "consultar_estoque_semen", {"incluir_provas": "true"})
        assert next(i for i in r["itens"] if i["touro"] == "TouroA")["prova"]["tpi"] == 2800.0
        with Session(engine) as s:
            assert r["prova_media_do_estoque"] == prova_media_semen(session=s, fazenda_id=1)
        assert "prova" not in _rodar(engine, "consultar_estoque_semen", {})["itens"][0]

    def test_estoque_isolado(self, engine):
        r2 = _rodar(engine, "consultar_estoque_semen", {}, fid=2)
        assert [i["touro"] for i in r2["itens"]] == ["TouroSEGREDO"] and r2["total_doses"] == 77
        assert "SEGREDO" not in json.dumps(_rodar(engine, "consultar_estoque_semen", {"incluir_provas": "true"}))

    def test_catalogo_ordenacao_e_filtros(self, engine):
        from fazenda.api.routers.cadastro.genetica import listar_touros
        with Session(engine) as s:
            site = listar_touros(session=s)
        r = _rodar(engine, "consultar_touros_catalogo", {})
        assert [t["naab"] for t in r["touros"]] == [t["naab"] for t in site] == ["7HO00002", "7HO00001", "7JE00003"]  # TPI desc, sem prova por último
        assert r["total_no_catalogo"] == 3 and "dados_extra" not in r["touros"][0]
        assert [t["naab"] for t in _rodar(engine, "consultar_touros_catalogo", {"ordenar_por": "nm_dolar"})["touros"]][:2] == ["7HO00001", "7HO00002"]
        assert [t["nome"] for t in _rodar(engine, "consultar_touros_catalogo", {"central": "abs"})["touros"]] == ["TouroA", "TouroJersey"]
        assert [t["nome"] for t in _rodar(engine, "consultar_touros_catalogo", {"raca": "jersey"})["touros"]] == ["TouroJersey"]
        assert [t["nome"] for t in _rodar(engine, "consultar_touros_catalogo", {"busca": "touroa"})["touros"]] == ["TouroA"]

    def test_catalogo_estoque_da_fazenda_e_dados_extra(self, engine):
        r = _rodar(engine, "consultar_touros_catalogo", {"apenas_no_estoque": "true", "incluir_dados_extra": "true"})
        assert [(t["nome"], t["doses_em_estoque_na_fazenda"]) for t in r["touros"]] == [("TouroA", 5)]
        assert r["touros"][0]["dados_extra_da_planilha"] == [["Prodigens", "123"]]
        # a fazenda 2 tem 77 doses cadastradas sob o NAAB do TouroA: não pode somar na fazenda 1
        todos = _rodar(engine, "consultar_touros_catalogo", {}, fid=1)["touros"]
        assert next(t for t in todos if t["naab"] == "7HO00001")["doses_em_estoque_na_fazenda"] == 5
        todos2 = _rodar(engine, "consultar_touros_catalogo", {}, fid=2)["touros"]
        assert next(t for t in todos2 if t["naab"] == "7HO00001")["doses_em_estoque_na_fazenda"] == 77

    def test_uso_por_touro_bate_com_a_analise_reprodutiva(self, engine):
        r = _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-01-01", "data_fim": "2026-07-01"})
        por = {t["touro"]: t for t in r["por_touro"]}
        # TouroA: 501 (02/10 POSITIVO) + 500 (04/10 NEGATIVO) => 2 serviços, 2 diagnosticados, 1 positivo => 50%
        assert (por["TouroA"]["servicos"], por["TouroA"]["diagnosticados"], por["TouroA"]["positivos"], por["TouroA"]["taxa_concepcao_pct"]) == (2, 2, 1, 50.0)
        assert por["TouroB"]["taxa_concepcao_pct"] == 100.0 and por["TouroA"]["doses_em_estoque_hoje"] == 5
        # a MESMA quebra que consultar_indicadores_reprodutivos(agrupar_por='touro') devolve
        q = _rodar(engine, "consultar_indicadores_reprodutivos", {"data_inicio": "2026-01-01", "data_fim": "2026-07-01", "agrupar_por": "touro"})["quebra"]
        assert {x["grupo"]: (x["servicos"], x["positivos"], x["taxa_concepcao_pct"]) for x in q} == {
            k: (v["servicos"], v["positivos"], v["taxa_concepcao_pct"]) for k, v in por.items() if v["diagnosticados"]}
        assert r["total_servicos"] == sum(t["servicos"] for t in r["por_touro"])

    def test_uso_compras_e_filtros(self, engine):
        r = _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-01-01", "data_fim": "2026-07-01"})
        assert r["compras_no_periodo"] == {"total_doses": 10, "valor_total": 500.0, "por_touro": [{"touro": "TouroA", "doses": 10, "valor_total": 500.0}]}
        r = _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-01-01", "data_fim": "2026-07-01", "touro": "touroB"})
        assert [t["touro"] for t in r["por_touro"]] == ["TouroB"] and r["compras_no_periodo"]["total_doses"] == 0
        r = _rodar(engine, "consultar_uso_semen", {"data_inicio": "2027-01-01", "data_fim": "2027-02-01"})
        assert r["por_touro"] == [] and r["total_servicos"] == 0

    def test_uso_isolado_e_prova_ao_vivo(self, engine):
        r2 = _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-01-01", "data_fim": "2026-07-01"}, fid=2)
        assert [t["touro"] for t in r2["por_touro"]] == ["TouroSEGREDO"] and r2["compras_no_periodo"]["total_doses"] == 99
        r = _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-01-01", "data_fim": "2026-07-01", "incluir_prova_ao_vivo": "true"})
        assert r["prova_ao_vivo"]["touros_considerados"] == 2 and r["prova_ao_vivo"]["total_servicos"] == 3

    def test_validacao(self, engine):
        assert "pergunte" in _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-01-01"})["erro"].lower()
        assert "Data inválida" in _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-02-30", "data_fim": "2026-07-01"})["erro"]
        assert "invertido" in _rodar(engine, "consultar_uso_semen", {"data_inicio": "2026-07-01", "data_fim": "2026-01-01"})["erro"]
        assert "5 anos" in _rodar(engine, "consultar_uso_semen", {"data_inicio": "2019-01-01", "data_fim": "2026-01-01"})["erro"]
        assert "tipo" in _rodar(engine, "consultar_estoque_semen", {"tipo": "xyz"})["erro"]
        assert "ordenar_por" in _rodar(engine, "consultar_touros_catalogo", {"ordenar_por": "xyz"})["erro"]


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
