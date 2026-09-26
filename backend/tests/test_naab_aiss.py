"""Catálogo AISS da NAAB (fazenda/rules/naab_aiss.py) — Fase 1 do catálogo
NAAB (ver docs/agents/naab-catalogo-firecrawl.md).

As duas linhas de fixture abaixo (LINHA_A / LINHA_B) são REAIS, coladas do
arquivo AISS baixado da NAAB, e foram validadas manualmente contra as
páginas públicas de dois touros (TIMETRAVELER/200HO13678, central Semex, e
SABOTAGE/796HO10329, central United Sires) em 26/09/2026. Os valores
esperados nos testes abaixo vêm dessa validação — qualquer teste que falhar
aqui é sinal de que `CAMPOS_AISS` (a ordem dos campos) ou o parsing
numérico divergiu do formato real do arquivo."""
from __future__ import annotations

import io
import zipfile

import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import Touro
from fazenda.rules import naab_aiss
from fazenda.rules.naab_aiss import (
    LB_PARA_KG,
    MARCA_MANTIDO,
    baixar_catalogo_aiss,
    comparar_catalogo,
    ler_catalogo_aiss,
    mapear_para_touro,
    marcar_mantido,
    parse_valor_americano,
)
from fazenda.rules.touros import aplicar_atualizacoes_confirmadas

LINHA_A = (
    '"HO","CAN","000015327904",0200,200,"HO",13678,"200HO13678","PROGENESIS TIMETRAVELER-ET    "," 99","  ",100,'
    '     ,     ," ",    ,79,"U",  589, 147,+.46,  61,+.15,  943, 1150, 1117,2.95,75, 2.9,74, 1.1,75,     ,  ,'
    '       ,  1.1,74,      ,  2.4,74,      , -1.5,71,      , 1089,72,99, 1.5,61,    0, 1.9,58,    0, 3.8,58,'
    '    0, 4.3,56,    0,"G", 1.31,78, 3590,  1.07, 0.24, 0.53,-0.08, 0.17, 1.73,-0.33, 0.49, 0.68, 0.13, 0.58,'
    ' 0.40, 1.21, 1.13, 1.87, 0.67, 0.65, 0.85, 1.12,-0.72, 0.0,  ,     ,"      ","        ",   ,20250504,'
    '"TIMETRAVELER        ","CAN000014766535","840003241772811",'
    '"                                                                 ","G",-2.00,73,      , 0.00,62,      ,'
    '-0.10,71,      , 0.60,69,      , 0.10,72,      , 1.80,69,      , 0.30,70,      ,  4.9,73,      , 0.20,53,'
    '      ,   55,47,      ,"A1A2 ","AA   ","     ", 7.45,63,      ,  -0.65,  11.6,   13.1,    ,    , -1.2,43,'
    ' -1.0,50,  6.6,74,  1.66,'
)

LINHA_B = (
    '"HO","840","003297710322",0796,796,"HO",10329,"796HO10329","OCD WHOOPS SABOTAGE-ET        "," 99"," I",100,'
    '     ,     ," ",    ,80,"U", 1227, 117,+.24,  63,+.08,  979, 1111, 1085,2.85,76, 4.3,75, 1.3,75,     ,  ,'
    '       ,  1.5,74,      ,  2.8,75,      , -0.4,72,      , 1071,73,99, 1.4,63,    0, 1.6,58,    0, 3.5,60,'
    '    0, 4.2,56,    0,"G", 1.47,79, 3597,  1.17, 1.02, 0.02, 0.03,-0.13, 0.98,-0.81, 1.58, 0.16, 1.04, 0.64,'
    ' 0.94, 1.02, 1.27, 1.90, 0.95, 0.44, 0.70, 0.90,-0.77, 0.0,  ,     ,"423   ","        ",   ,20250225,'
    '"SABOTAGE            ","840003247091703","840003214541170",'
    '"TD TC TL TR TP TE TV TY                                          ","G",-0.90,73,      , 0.00,62,      ,'
    ' 0.00,72,      , 0.80,69,      , 2.20,72,      , 1.30,70,      , 0.20,70,      ,  5.0,74,      , 0.80,54,'
    '      ,  128,48,      ,"A1A2 ","AB   ","     ", 7.38,64,      ,  -0.18,  11.4,   13.0,    ,    , -1.0,44,'
    '  1.3,52,  7.3,75,  2.08,'
)


# ---------------------------------------------------------------------------
# parse_valor_americano
# ---------------------------------------------------------------------------
class TestParseValorAmericano:
    @pytest.mark.parametrize("bruto,esperado", [
        ("+.46", 0.46),
        ("-.07", -0.07),
        ("", None),
        ("   ", None),
        ("  129", 129.0),
        ("1089", 1089.0),
        (" 1.1", 1.1),
        ("-1.5", -1.5),
        (None, None),
    ])
    def test_casos_de_borda(self, bruto, esperado):
        resultado = parse_valor_americano(bruto)
        if esperado is None:
            assert resultado is None
        else:
            assert resultado == pytest.approx(esperado)

    def test_nunca_devolve_zero_para_campo_vazio(self):
        # Vazio é ausência de dado, não zero — nunca pode virar 0.0.
        assert parse_valor_americano("") is None
        assert parse_valor_americano("     ") is None


# ---------------------------------------------------------------------------
# ler_catalogo_aiss + mapear_para_touro, contra as duas linhas reais
# ---------------------------------------------------------------------------
class TestLerEMapearCatalogo:
    def test_le_as_duas_linhas(self):
        linhas = ler_catalogo_aiss(LINHA_A + "\n" + LINHA_B)
        assert len(linhas) == 2
        assert linhas[0]["Full NAAB Code"] == "200HO13678"
        assert linhas[1]["Full NAAB Code"] == "796HO10329"

    def test_ignora_linha_malformada_sem_derrubar_as_outras(self):
        texto = "muito,poucos,campos\n" + LINHA_A + "\n" + LINHA_B
        linhas = ler_catalogo_aiss(texto)
        assert len(linhas) == 2  # a linha de 3 campos foi pulada, não quebrou nada

    def test_ignora_linha_em_branco(self):
        texto = LINHA_A + "\n\n" + LINHA_B + "\n"
        linhas = ler_catalogo_aiss(texto)
        assert len(linhas) == 2

    def _mapa(self, linha_bruta: str) -> dict:
        linhas = ler_catalogo_aiss(linha_bruta)
        assert len(linhas) == 1
        return mapear_para_touro(linhas[0])

    def test_timetraveler_naab_e_identidade(self):
        m = self._mapa(LINHA_A)
        assert m["naab"] == "200HO13678"
        assert m["nome"] == "TIMETRAVELER"
        assert m["nome_completo"] == "PROGENESIS TIMETRAVELER-ET"
        assert m["raca"] == "HO"
        assert m["central"] == "Semex"

    def test_timetraveler_provas_curadas(self):
        m = self._mapa(LINHA_A)
        assert m["leite_kg"] == round(589 * LB_PARA_KG, 2)
        assert m["gordura_kg"] == round(147 * LB_PARA_KG, 2)
        assert m["gordura_pct"] == pytest.approx(0.46)
        assert m["proteina_kg"] == round(61 * LB_PARA_KG, 2)
        assert m["proteina_pct"] == pytest.approx(0.15)
        assert m["nm_dolar"] == pytest.approx(1089)
        assert m["tpi"] == pytest.approx(3590)
        assert m["tipo_composto"] == pytest.approx(1.31)
        assert m["ubere_composto"] == pytest.approx(1.07)
        assert m["pernas_composto"] == pytest.approx(0.24)
        assert m["fertilidade_filhas"] == pytest.approx(1.1)
        assert m["ccs_score"] == pytest.approx(2.95)

    def test_sabotage_naab_e_identidade(self):
        m = self._mapa(LINHA_B)
        assert m["naab"] == "796HO10329"
        assert m["nome"] == "SABOTAGE"
        assert m["nome_completo"] == "OCD WHOOPS SABOTAGE-ET"
        assert m["raca"] == "HO"
        assert m["central"] == "United Sires"

    def test_sabotage_provas_curadas(self):
        m = self._mapa(LINHA_B)
        assert m["leite_kg"] == round(1227 * LB_PARA_KG, 2)
        assert m["gordura_kg"] == round(117 * LB_PARA_KG, 2)
        assert m["gordura_pct"] == pytest.approx(0.24)
        assert m["proteina_kg"] == round(63 * LB_PARA_KG, 2)
        assert m["proteina_pct"] == pytest.approx(0.08)
        assert m["nm_dolar"] == pytest.approx(1071)
        assert m["tpi"] == pytest.approx(3597)
        assert m["tipo_composto"] == pytest.approx(1.47)
        assert m["ubere_composto"] == pytest.approx(1.17)
        assert m["pernas_composto"] == pytest.approx(1.02)
        assert m["fertilidade_filhas"] == pytest.approx(1.3)
        assert m["ccs_score"] == pytest.approx(2.85)

    def test_campo_ausente_nao_entra_no_dict_de_saida(self):
        # "SCR" (linha bruta) não tem campo curado equivalente e não deveria
        # aparecer; confirmamos também que um campo N/D não vira 0.0 — aqui
        # simulamos removendo PTA Type da linha crua.
        linhas = ler_catalogo_aiss(LINHA_A)
        bruta = dict(linhas[0])
        bruta["PTA Type"] = "     "  # em branco
        m = mapear_para_touro(bruta)
        assert "tipo_composto" not in m


# ---------------------------------------------------------------------------
# comparar_catalogo (SÓ LEITURA)
# ---------------------------------------------------------------------------
@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


class TestCompararCatalogo:
    def test_touro_alterado_aparece_so_com_os_campos_que_mudaram(self, session):
        # TPI do banco está velho (2800); o resto já bate com o AISS.
        session.add(Touro(
            naab="200HO13678", nome="TIMETRAVELER", tpi=2800,
            leite_kg=round(589 * LB_PARA_KG, 2), gordura_kg=round(147 * LB_PARA_KG, 2),
            gordura_pct=0.46, proteina_kg=round(61 * LB_PARA_KG, 2), proteina_pct=0.15,
            nm_dolar=1089, tipo_composto=1.31, ubere_composto=1.07, pernas_composto=0.24,
            ccs_score=2.95, fertilidade_filhas=1.1, facilidade_parto=1.5,
        ))
        session.commit()

        linhas = ler_catalogo_aiss(LINHA_A)
        relatorio = comparar_catalogo(session, linhas)

        assert relatorio.total_comparados == 1
        assert len(relatorio.alterados) == 1
        item = relatorio.alterados[0]
        assert item["naab"] == "200HO13678"
        assert item["mudancas"] == {"tpi": {"antes": 2800, "depois": pytest.approx(3590)}}
        assert relatorio.saidos == []
        assert relatorio.novos == []

    def test_diferenca_dentro_da_tolerancia_nao_conta_como_mudanca(self, session):
        session.add(Touro(
            naab="200HO13678", nome="TIMETRAVELER",
            tpi=3590.005,  # diferença de 0.005 < tolerância de 0.01
            leite_kg=round(589 * LB_PARA_KG, 2), gordura_kg=round(147 * LB_PARA_KG, 2),
            gordura_pct=0.46, proteina_kg=round(61 * LB_PARA_KG, 2), proteina_pct=0.15,
            nm_dolar=1089, tipo_composto=1.31, ubere_composto=1.07, pernas_composto=0.24,
            ccs_score=2.95, fertilidade_filhas=1.1, facilidade_parto=1.5,
        ))
        session.commit()
        relatorio = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A))
        assert relatorio.alterados == []

    def test_touro_que_saiu_do_catalogo_aparece_so_com_naab_e_nome(self, session):
        session.add(Touro(naab="000FORADOCATALOGO", nome="FORADOCATALOGO", tpi=2000))
        session.commit()

        relatorio = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A))
        assert relatorio.saidos == [{"naab": "000FORADOCATALOGO", "nome": "FORADOCATALOGO"}]
        # Formato do item: só naab e nome — nenhuma prova/dado de performance.
        assert set(relatorio.saidos[0].keys()) == {"naab", "nome"}

    def test_touro_marcado_como_mantido_nao_repete_em_saidos(self, session):
        session.add(Touro(
            naab="000FORADOCATALOGO", nome="FORADOCATALOGO", tpi=2000,
            observacao=f"{MARCA_MANTIDO} em 01/01/2026: decisão do dono",
        ))
        session.commit()

        relatorio = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A))
        assert relatorio.saidos == []

    def test_touro_novo_traz_todos_os_campos_mapeados_de_todas_as_centrais(self, session):
        # Nenhum touro no banco ainda — os dois da fixture (Semex e United
        # Sires, centrais DIFERENTES) devem aparecer em "novos", sem filtro.
        relatorio = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A + "\n" + LINHA_B))
        naabs_novos = {n["naab"] for n in relatorio.novos}
        assert naabs_novos == {"200HO13678", "796HO10329"}
        centrais = {n["central"] for n in relatorio.novos}
        assert centrais == {"Semex", "United Sires"}
        item_a = next(n for n in relatorio.novos if n["naab"] == "200HO13678")
        assert item_a["tpi"] == pytest.approx(3590)
        assert item_a["leite_kg"] == round(589 * LB_PARA_KG, 2)

    def test_nunca_escreve_no_banco(self, session):
        session.add(Touro(naab="200HO13678", nome="TIMETRAVELER", tpi=2800))
        session.commit()
        comparar_catalogo(session, ler_catalogo_aiss(LINHA_A))
        # Reabre e confere que nada foi persistido além do que já estava lá.
        touro = session.exec(select(Touro).where(Touro.naab == "200HO13678")).first()
        assert touro.tpi == 2800  # não foi atualizado por comparar_catalogo

    def test_rodada_extraida_do_nome_do_arquivo(self, session):
        relatorio = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A), nome_arquivo="Aug122026-CompleteAISS.txt")
        assert relatorio.rodada == "Ago/2026"

    def test_rodada_sem_padrao_reconhecido_devolve_nome_bruto(self, session):
        relatorio = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A), nome_arquivo="arquivo-estranho.txt")
        assert relatorio.rodada == "arquivo-estranho.txt"


# ---------------------------------------------------------------------------
# marcar_mantido
# ---------------------------------------------------------------------------
class TestMarcarMantido:
    def test_acrescenta_sem_apagar_observacao_existente(self, session):
        session.add(Touro(naab="000FORADOCATALOGO", nome="FORADOCATALOGO", observacao="nota antiga do plantel"))
        session.commit()

        marcar_mantido(session, "000foradocatalogo", motivo="genética boa, mantém no plantel")

        touro = session.exec(select(Touro).where(Touro.naab == "000FORADOCATALOGO")).first()
        assert "nota antiga do plantel" in touro.observacao
        assert MARCA_MANTIDO in touro.observacao
        assert "genética boa, mantém no plantel" in touro.observacao

    def test_sem_observacao_previa_grava_so_a_marca(self, session):
        session.add(Touro(naab="000SEMOBS", nome="SEMOBS"))
        session.commit()
        marcar_mantido(session, "000SEMOBS")
        touro = session.exec(select(Touro).where(Touro.naab == "000SEMOBS")).first()
        assert touro.observacao.startswith(MARCA_MANTIDO)
        assert "sem motivo registrado" in touro.observacao

    def test_touro_inexistente_levanta_value_error(self, session):
        with pytest.raises(ValueError):
            marcar_mantido(session, "000NAOEXISTE")

    def test_depois_de_marcado_nao_aparece_mais_em_saidos(self, session):
        session.add(Touro(naab="000FORADOCATALOGO", nome="FORADOCATALOGO"))
        session.commit()

        # Antes de marcar: aparece em "saídos".
        relatorio_antes = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A))
        assert any(s["naab"] == "000FORADOCATALOGO" for s in relatorio_antes.saidos)

        marcar_mantido(session, "000FORADOCATALOGO", motivo="mantém no plantel")

        relatorio_depois = comparar_catalogo(session, ler_catalogo_aiss(LINHA_A))
        assert all(s["naab"] != "000FORADOCATALOGO" for s in relatorio_depois.saidos)


# ---------------------------------------------------------------------------
# aplicar_atualizacoes_confirmadas (touros.py) — só grava o que o dono
# confirmou, nunca apaga, upsert por NAAB.
# ---------------------------------------------------------------------------
class TestAplicarAtualizacoesConfirmadas:
    def test_so_grava_os_naabs_confirmados(self, session):
        linhas = ler_catalogo_aiss(LINHA_A + "\n" + LINHA_B)
        resultado = aplicar_atualizacoes_confirmadas(
            session, ["200HO13678"], linhas, fonte="NAAB AISS", rodada="Ago/2026",
        )
        assert resultado["criados"] == 1
        assert resultado["atualizados"] == 0

        touro = session.exec(select(Touro).where(Touro.naab == "200HO13678")).first()
        assert touro is not None
        assert touro.tpi == pytest.approx(3590)
        assert touro.fonte == "NAAB AISS"
        assert touro.rodada_prova == "Ago/2026"
        assert touro.central == "Semex"

        # SABOTAGE não foi confirmado — não deve ter sido criado.
        assert session.exec(select(Touro).where(Touro.naab == "796HO10329")).first() is None

    def test_upsert_nao_apaga_touro_existente_nem_zera_campo(self, session):
        session.add(Touro(naab="200HO13678", nome="TIMETRAVELER", observacao="nota manual"))
        session.commit()

        linhas = ler_catalogo_aiss(LINHA_A)
        aplicar_atualizacoes_confirmadas(session, ["200HO13678"], linhas, fonte="NAAB AISS", rodada="Ago/2026")

        touro = session.exec(select(Touro).where(Touro.naab == "200HO13678")).first()
        assert touro.tpi == pytest.approx(3590)  # atualizado
        assert touro.observacao == "nota manual"  # preservado — não veio no AISS, não foi tocado

        todos = session.exec(select(Touro)).all()
        assert len(todos) == 1  # upsert, não duplicou


# ---------------------------------------------------------------------------
# baixar_catalogo_aiss — rede mockada (mesmo padrão de tests/test_firecrawl.py)
# ---------------------------------------------------------------------------
def _zip_bytes(nome_arquivo: str, conteudo: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(nome_arquivo, conteudo)
    return buf.getvalue()


class TestBaixarCatalogoAiss:
    HTML_PAGINA = """
    <html><body>
    <ul>
      <li><a href="/wp-content/uploads/2026/08/Complete%20AISS(13).zip">Complete List of All Active (A),
        Foreign (F) and Genomic (G) AI Bulls</a></li>
      <li><a href="/wp-content/uploads/2026/08/OtherFile.zip">Outro arquivo qualquer</a></li>
    </ul>
    </body></html>
    """

    def test_baixa_acha_o_link_e_extrai_o_txt(self, monkeypatch):
        conteudo_txt = (LINHA_A + "\n").encode("latin-1")
        zip_bytes = _zip_bytes("Aug122026-CompleteAISS.txt", conteudo_txt)

        chamadas = []

        def fake_get(url, timeout=None, follow_redirects=None):
            chamadas.append(url)
            req = httpx.Request("GET", url)
            if url == naab_aiss.URL_DATABASE_FILES:
                return httpx.Response(200, text=self.HTML_PAGINA, request=req)
            assert "Complete%20AISS" in url or "Complete AISS" in url
            return httpx.Response(200, content=zip_bytes, request=req)

        monkeypatch.setattr(httpx, "get", fake_get)
        texto, nome = baixar_catalogo_aiss()
        assert nome == "Aug122026-CompleteAISS.txt"
        assert "200HO13678" in texto
        assert len(chamadas) == 2

    def test_link_nao_encontrado_levanta_runtime_error_claro(self, monkeypatch):
        def fake_get(url, timeout=None, follow_redirects=None):
            return httpx.Response(200, text="<html><body>nada aqui</body></html>", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(RuntimeError, match="Complete List of All Active"):
            baixar_catalogo_aiss()

    def test_zip_invalido_levanta_runtime_error_claro(self, monkeypatch):
        def fake_get(url, timeout=None, follow_redirects=None):
            req = httpx.Request("GET", url)
            if url == naab_aiss.URL_DATABASE_FILES:
                return httpx.Response(200, text=self.HTML_PAGINA, request=req)
            return httpx.Response(200, content=b"isto nao e um zip", request=req)

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(RuntimeError, match="ZIP"):
            baixar_catalogo_aiss()

    def test_erro_de_rede_levanta_runtime_error_claro(self, monkeypatch):
        def fake_get(url, timeout=None, follow_redirects=None):
            raise httpx.ConnectError("falha de rede simulada")

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(RuntimeError, match="Falha ao baixar"):
            baixar_catalogo_aiss()
