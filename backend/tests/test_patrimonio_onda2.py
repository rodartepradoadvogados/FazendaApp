"""Onda 2 — cadastro fechado do patrimônio.

Cobre o que a onda introduziu: os 4 métodos de depreciação, a vida útil
estruturada (que substitui o texto livre culpado pelo erro de 12x da Onda 1),
o código sequencial PAT e a baixa com apuração de ganho/perda de capital.

Os casos numéricos são fechados à mão — a Onda 1 mostrou que depreciação sem
número conferido acumula divergência em silêncio.
"""
from datetime import date

import pytest

from fazenda.rules.patrimonio import (
    LINEAR, SALDO_DECRESCENTE, SOMA_DIGITOS, UNIDADES_PRODUZIDAS,
    METODOS_VALIDOS, MOTIVOS_BAIXA_COM_VENDA,
    calcular_depreciacao, metodo_normalizado, resultado_baixa, vida_util_em_anos,
)


def item_base(**extra):
    """Trator de R$ 145.000, 10 anos de vida útil, imobilizado em 01/01/2025."""
    base = dict(
        valor_total=145000.0, vida_util_anos=10, vida_util_meses=0, valor_residual=0.0,
        data_imobilizacao=date(2025, 1, 1), depreciavel=True,
    )
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Vida útil estruturada
# ---------------------------------------------------------------------------
def test_vida_util_estruturada_tem_precedencia_sobre_texto_livre():
    """O campo novo manda. O item legado tinha "10 anos e 6 meses" em texto e
    o parser antigo lia 0,83 ano (erro de 12x da Onda 1); com os steppers
    preenchidos não há o que interpretar."""
    item = {"vida_util": "texto que seria mal interpretado", "vida_util_anos": 10, "vida_util_meses": 6}
    assert vida_util_em_anos(item) == pytest.approx(10.5)


def test_vida_util_cai_no_texto_livre_quando_nao_ha_estruturada():
    """Item legado (só texto) continua sendo lido — a Onda 2 não invalida o
    que já estava cadastrado."""
    assert vida_util_em_anos({"vida_util": "7 Anos"}) == pytest.approx(7.0)


def test_vida_util_estruturada_so_em_meses():
    assert vida_util_em_anos({"vida_util_anos": 0, "vida_util_meses": 18}) == pytest.approx(1.5)


def test_vida_util_estruturada_zerada_e_invalida():
    """0 ano e 0 mês não é vida útil — vira inconsistência, não divisão por zero."""
    assert vida_util_em_anos({"vida_util_anos": 0, "vida_util_meses": 0}) is None


# ---------------------------------------------------------------------------
# Os 4 métodos — números fechados
# ---------------------------------------------------------------------------
def test_linear_e_o_padrao_do_legado():
    """Item sem método cadastrado (todo o legado) deprecia linear, como sempre
    depreciou — a Onda 2 não pode mudar número que o usuário já via."""
    assert metodo_normalizado(None) == LINEAR
    assert metodo_normalizado("") == LINEAR
    assert metodo_normalizado("qualquer coisa fora da lista") == LINEAR


def test_linear_18_meses():
    """145.000 / 120 meses = 1.208,33/mês x 18 meses = 21.750,00."""
    r = calcular_depreciacao(item_base(metodo_depreciacao=LINEAR), hoje=date(2026, 7, 1))
    assert r["depreciacao_acumulada"] == pytest.approx(21750.00, abs=0.01)
    assert r["valor_atual"] == pytest.approx(123250.00, abs=0.01)


def test_saldo_decrescente_18_meses():
    """taxa mensal = 2/120; saldo = 145.000 x (1 - 2/120)^18 = 107.147,42."""
    r = calcular_depreciacao(item_base(metodo_depreciacao=SALDO_DECRESCENTE), hoje=date(2026, 7, 1))
    assert r["valor_atual"] == pytest.approx(107147.42, abs=0.01)
    assert r["depreciacao_acumulada"] == pytest.approx(37852.58, abs=0.01)


def test_soma_digitos_18_meses():
    """n=120, m=18: [120x121 - 102x103] / [120x121] = 4014/14520 = 27,645%."""
    r = calcular_depreciacao(item_base(metodo_depreciacao=SOMA_DIGITOS), hoje=date(2026, 7, 1))
    assert r["depreciacao_acumulada"] == pytest.approx(40084.71, abs=0.01)


def test_metodos_acelerados_depreciam_mais_que_linear_no_inicio():
    """É a razão de existir dos dois métodos acelerados — se isso inverter,
    algum sinal foi trocado na fórmula."""
    hoje = date(2026, 7, 1)
    linear = calcular_depreciacao(item_base(metodo_depreciacao=LINEAR), hoje)["depreciacao_acumulada"]
    for acelerado in (SALDO_DECRESCENTE, SOMA_DIGITOS):
        assert calcular_depreciacao(item_base(metodo_depreciacao=acelerado), hoje)["depreciacao_acumulada"] > linear


def test_linear_e_soma_digitos_zeram_exatamente_no_residual():
    """No fim da vida útil os dois métodos chegam ao valor residual — nem um
    centavo abaixo (depreciar abaixo do residual é erro contábil)."""
    item = item_base(valor_total=100000.0, valor_residual=10000.0, data_imobilizacao=date(2015, 1, 1))
    for metodo in (LINEAR, SOMA_DIGITOS):
        r = calcular_depreciacao(dict(item, metodo_depreciacao=metodo), hoje=date(2026, 1, 31))
        assert r["valor_atual"] == pytest.approx(10000.00, abs=0.01), metodo


def test_saldo_decrescente_nunca_deprecia_abaixo_do_residual():
    """O saldo decrescente é assintótico — por natureza nunca zera sozinho.
    Sem o piso explícito ele passaria do residual e, no limite, de zero."""
    item = item_base(valor_total=100000.0, valor_residual=10000.0, data_imobilizacao=date(2000, 1, 1),
                     metodo_depreciacao=SALDO_DECRESCENTE)
    r = calcular_depreciacao(item, hoje=date(2026, 1, 31))
    assert r["valor_atual"] >= 10000.00


def test_unidades_produzidas_e_por_uso_nao_por_tempo():
    """1.250 de 5.000 horas = 25% da base depreciável."""
    item = item_base(valor_total=100000.0, valor_residual=10000.0, metodo_depreciacao=UNIDADES_PRODUZIDAS,
                     unidades_vida_util_total=5000, unidades_consumidas=1250)
    r = calcular_depreciacao(item, hoje=date(2026, 1, 31))
    assert r["depreciacao_acumulada"] == pytest.approx(22500.00, abs=0.01)


def test_unidades_produzidas_trator_parado_nao_deprecia():
    """A diferença essencial do método: passa o tempo, o bem não é usado, não
    deprecia. Nos outros três a mesma situação depreciaria."""
    item = item_base(metodo_depreciacao=UNIDADES_PRODUZIDAS, data_imobilizacao=date(2015, 1, 1),
                     unidades_vida_util_total=5000, unidades_consumidas=0)
    assert calcular_depreciacao(item, hoje=date(2026, 1, 31))["depreciacao_acumulada"] == 0.0


def test_unidades_produzidas_nao_passa_de_100_por_cento():
    """Uso além do previsto (bem que durou mais que a estimativa) não deprecia
    além da base."""
    item = item_base(metodo_depreciacao=UNIDADES_PRODUZIDAS,
                     unidades_vida_util_total=5000, unidades_consumidas=9999)
    r = calcular_depreciacao(item, hoje=date(2026, 1, 31))
    assert r["depreciacao_acumulada"] == pytest.approx(145000.00, abs=0.01)
    assert r["valor_atual"] == pytest.approx(0.0, abs=0.01)


def test_saldo_decrescente_com_vida_util_curta_demais_nao_estoura():
    """Vida útil de 2 meses com fator 2 dá taxa mensal = 1 (2/2): a fórmula
    (1 - taxa)^meses viraria 0^m, e qualquer fator maior deixaria a base
    negativa elevada a uma potência — a guarda deprecia tudo de uma vez, com
    o mesmo teto no residual."""
    item = item_base(vida_util_anos=0, vida_util_meses=2, valor_residual=5000.0,
                     metodo_depreciacao=SALDO_DECRESCENTE)
    r = calcular_depreciacao(item, hoje=date(2025, 3, 31))
    assert r["valor_atual"] == pytest.approx(5000.00, abs=0.01)


def test_saldo_decrescente_com_vida_util_curta_continua_assintotico():
    """Fora da guarda (taxa < 1) o método segue sua natureza: 6 meses de vida
    útil, taxa 2/6 = 33,3% ao mês, saldo = 145.000 x (1-1/3)^3 = 42.962,96
    depois de 3 meses. Não zera — nunca zera sozinho."""
    item = item_base(vida_util_anos=0, vida_util_meses=6, metodo_depreciacao=SALDO_DECRESCENTE)
    r = calcular_depreciacao(item, hoje=date(2025, 3, 31))
    assert r["valor_atual"] == pytest.approx(42962.96, abs=0.01)


# ---------------------------------------------------------------------------
# Baixa — ganho e perda de capital
# ---------------------------------------------------------------------------
def test_baixa_com_ganho_de_capital():
    """Vendeu por 130.000 um bem cujo valor contábil era 123.250 -> ganho de
    6.750. É resultado do exercício e vai para OUTRAS_REC_DESP na DRE."""
    item = item_base(metodo_depreciacao=LINEAR, data_baixa=date(2026, 7, 1),
                     motivo_baixa="VENDA", valor_baixa=130000.0)
    r = resultado_baixa(item)
    assert r["valor_contabil"] == pytest.approx(123250.00, abs=0.01)
    assert r["resultado"] == pytest.approx(6750.00, abs=0.01)


def test_baixa_com_perda_de_capital():
    item = item_base(metodo_depreciacao=LINEAR, data_baixa=date(2026, 7, 1),
                     motivo_baixa="VENDA", valor_baixa=100000.0)
    assert resultado_baixa(item)["resultado"] == pytest.approx(-23250.00, abs=0.01)


def test_baixa_sem_venda_perde_o_valor_contabil_inteiro():
    """Perda, sucateamento, doação e transferência não têm valor recebido — o
    resultado é a perda do que ainda restava nos livros."""
    for motivo in ("PERDA", "SUCATEAMENTO", "DOACAO", "TRANSFERENCIA"):
        assert motivo not in MOTIVOS_BAIXA_COM_VENDA
        item = item_base(metodo_depreciacao=LINEAR, data_baixa=date(2026, 7, 1),
                         motivo_baixa=motivo, valor_baixa=999999.0)
        r = resultado_baixa(item)
        # valor_baixa é ignorado nos motivos sem venda, mesmo se vier preenchido
        assert r["valor_recebido"] == 0.0, motivo
        assert r["resultado"] == pytest.approx(-123250.00, abs=0.01), motivo


def test_item_nao_baixado_nao_tem_resultado():
    assert resultado_baixa(item_base()) is None


def test_baixa_respeita_o_metodo_do_item():
    """O valor contábil na baixa vem do método cadastrado, não sempre do
    linear — senão o ganho/perda sai errado para todo bem acelerado."""
    comum = dict(data_baixa=date(2026, 7, 1), motivo_baixa="VENDA", valor_baixa=130000.0)
    linear = resultado_baixa(item_base(metodo_depreciacao=LINEAR, **comum))
    acelerado = resultado_baixa(item_base(metodo_depreciacao=SOMA_DIGITOS, **comum))
    assert acelerado["valor_contabil"] < linear["valor_contabil"]
    assert acelerado["resultado"] > linear["resultado"]


def test_baixa_de_item_com_cadastro_incompleto_sai_marcada_como_estimada():
    """Bem baixado sem vida útil não tem depreciação apurável — o resultado
    ainda sai (esconder a baixa seria pior), mas sinalizado."""
    item = dict(valor_total=145000.0, depreciavel=True, data_imobilizacao=None,
                data_baixa=date(2026, 7, 1), motivo_baixa="VENDA", valor_baixa=100000.0)
    r = resultado_baixa(item)
    assert r["estimado"] is True
    assert r["resultado"] == pytest.approx(-45000.00, abs=0.01)


def test_todos_os_metodos_validos_sao_reconhecidos():
    """Sentinela: se alguém adicionar um método à lista sem tratá-lo no
    despacho, ele cairia silenciosamente em LINEAR."""
    for metodo in METODOS_VALIDOS:
        assert metodo_normalizado(metodo) == metodo


# ---------------------------------------------------------------------------
# Testes de integração (via API) — código PAT, listas fechadas e baixa.
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from fazenda import database  # noqa: E402
from fazenda.models.financeiro import Patrimonio  # noqa: E402


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        c._engine = engine  # type: ignore[attr-defined]
        yield c

    main.app.dependency_overrides.clear()


def _criar(client, **campos):
    payload = {"nome": "Trator", "valor_total": 145000.0, "data_imobilizacao": "2025-01-01",
               "vida_util_anos": 10, "vida_util_meses": 0}
    payload.update(campos)
    r = client.post("/financeiro/patrimonio", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestCodigoPatrimonio:
    def test_primeiro_item_recebe_pat_0001(self, client):
        assert _criar(client)["codigo"] == "PAT-0001"

    def test_codigos_sao_sequenciais(self, client):
        assert [_criar(client, nome=f"Bem {i}")["codigo"] for i in range(3)] == [
            "PAT-0001", "PAT-0002", "PAT-0003"
        ]

    def test_backfill_do_legado_e_report_first(self, client):
        """Item que nasceu sem código (todo o legado) só recebe um quando o
        admin confirma — mesmo padrão de /depreciavel-corrigir."""
        with Session(client._engine) as s:
            s.add(Patrimonio(nome="Trator Velho", valor_total=1000.0))
            s.commit()

        previa = client.post("/financeiro/patrimonio/codigos-gerar").json()
        assert previa["total"] == 1 and previa["aplicado"] is False
        with Session(client._engine) as s:
            assert s.exec(select(Patrimonio)).first().codigo is None, "prévia não pode gravar"

        aplicado = client.post("/financeiro/patrimonio/codigos-gerar?confirmar=true").json()
        assert aplicado["aplicado"] is True and aplicado["total"] == 1
        with Session(client._engine) as s:
            assert s.exec(select(Patrimonio)).first().codigo == "PAT-0001"

    def test_backfill_nao_colide_com_codigo_ja_existente(self, client):
        """O legado entra DEPOIS do que já tem código — sem isso dois bens
        diferentes ficariam com o mesmo PAT."""
        _criar(client)  # PAT-0001
        with Session(client._engine) as s:
            s.add(Patrimonio(nome="Legado", valor_total=1000.0))
            s.commit()
        assert client.post("/financeiro/patrimonio/codigos-gerar?confirmar=true").json()["primeiro"] == "PAT-0002"


class TestListasFechadas:
    def test_opcoes_expoe_as_quatro_listas(self, client):
        opcoes = client.get("/financeiro/patrimonio/opcoes").json()
        assert len(opcoes["metodos"]) == 4
        assert {m["valor"] for m in opcoes["metodos"]} == set(METODOS_VALIDOS)
        assert "Trator" in opcoes["tipos"] and "un" in opcoes["unidades"]
        # Só o motivo VENDA pede valor recebido
        assert [m["valor"] for m in opcoes["motivos_baixa"] if m["tem_valor_venda"]] == ["VENDA"]

    def test_metodo_fora_da_lista_e_rejeitado(self, client):
        r = client.post("/financeiro/patrimonio", json={"nome": "X", "metodo_depreciacao": "INVENTADO"})
        assert r.status_code == 400 and "inválido" in r.json()["detail"]

    def test_unidades_produzidas_exige_o_total_de_unidades(self, client):
        """Sem o total não há fração a calcular — o bem nunca depreciaria e
        ninguém saberia por quê."""
        r = client.post("/financeiro/patrimonio",
                        json={"nome": "Trator", "metodo_depreciacao": "UNIDADES_PRODUZIDAS"})
        assert r.status_code == 400 and "unidades" in r.json()["detail"].lower()


class TestBaixa:
    def test_baixa_por_venda_apura_ganho_de_capital(self, client):
        item = _criar(client, metodo_depreciacao=LINEAR)
        r = client.post(f"/financeiro/patrimonio/{item['id']}/baixa",
                        json={"data_baixa": "2026-07-01", "motivo": "VENDA", "valor_recebido": 130000.0})
        assert r.status_code == 200, r.text
        assert r.json()["resultado"]["resultado"] == pytest.approx(6750.00, abs=0.01)

    def test_baixa_sem_venda_ignora_valor_recebido(self, client):
        item = _criar(client, metodo_depreciacao=LINEAR)
        r = client.post(f"/financeiro/patrimonio/{item['id']}/baixa",
                        json={"data_baixa": "2026-07-01", "motivo": "PERDA", "valor_recebido": 99999.0})
        assert r.json()["resultado"]["valor_recebido"] == 0.0

    def test_nao_baixa_duas_vezes(self, client):
        item = _criar(client)
        corpo = {"data_baixa": "2026-07-01", "motivo": "VENDA", "valor_recebido": 1.0}
        client.post(f"/financeiro/patrimonio/{item['id']}/baixa", json=corpo)
        r = client.post(f"/financeiro/patrimonio/{item['id']}/baixa", json=corpo)
        assert r.status_code == 400 and "já foi baixado" in r.json()["detail"]

    def test_baixa_anterior_a_imobilizacao_e_rejeitada(self, client):
        item = _criar(client)
        r = client.post(f"/financeiro/patrimonio/{item['id']}/baixa",
                        json={"data_baixa": "2024-01-01", "motivo": "VENDA", "valor_recebido": 1.0})
        assert r.status_code == 400 and "anterior" in r.json()["detail"]

    def test_motivo_invalido_e_rejeitado(self, client):
        item = _criar(client)
        r = client.post(f"/financeiro/patrimonio/{item['id']}/baixa",
                        json={"data_baixa": "2026-07-01", "motivo": "SUMIU"})
        assert r.status_code == 400

    def test_estornar_baixa_devolve_o_bem_ao_ativo(self, client):
        """Baixa lançada por engano: o bem volta e volta a depreciar da data
        de imobilização original — a depreciação nunca é perdida."""
        item = _criar(client, metodo_depreciacao=LINEAR)
        client.post(f"/financeiro/patrimonio/{item['id']}/baixa",
                    json={"data_baixa": "2026-07-01", "motivo": "VENDA", "valor_recebido": 130000.0})
        r = client.post(f"/financeiro/patrimonio/{item['id']}/estornar-baixa")
        assert r.status_code == 200
        assert r.json()["data_baixa"] is None and r.json()["motivo_baixa"] is None
        listagem = client.get("/financeiro/patrimonio").json()
        assert listagem["valor_atual_total"] > 0, "bem estornado volta a somar no ativo"

    def test_listagem_traz_resultado_da_baixa_e_rotulo_do_metodo(self, client):
        item = _criar(client, metodo_depreciacao=SOMA_DIGITOS)
        client.post(f"/financeiro/patrimonio/{item['id']}/baixa",
                    json={"data_baixa": "2026-07-01", "motivo": "VENDA", "valor_recebido": 130000.0})
        listado = client.get("/financeiro/patrimonio").json()["itens"][0]
        assert listado["baixa"]["motivo"] == "VENDA"
        assert "dígitos" in listado["metodo_rotulo"].lower()


class TestColisaoVidaUtil:
    """`calcular_depreciacao` devolve `vida_util_anos` como o TOTAL (10 anos e
    6 meses = 10,5); o cadastro tem um campo homônimo que é o inteiro do
    stepper (10). Se a listagem publicar o total sob o nome do campo, abrir a
    edição mostra 10,5 no campo de anos e salvar grava outra vida útil — sem
    nenhum erro visível."""

    def test_listagem_separa_campo_do_cadastro_e_total_calculado(self, client):
        item = _criar(client, vida_util_anos=10, vida_util_meses=6, metodo_depreciacao=LINEAR)
        listado = client.get("/financeiro/patrimonio").json()["itens"][0]
        assert listado["vida_util_anos"] == 10, "campo do cadastro, como digitado"
        assert listado["vida_util_meses"] == 6
        assert listado["vida_util_total_anos"] == pytest.approx(10.5), "total calculado"

    def test_editar_sem_mexer_na_vida_util_nao_altera_o_cadastro(self, client):
        """Ida e volta pela tela de edição tem que preservar 10 anos e 6 meses."""
        item = _criar(client, vida_util_anos=10, vida_util_meses=6)
        listado = client.get("/financeiro/patrimonio").json()["itens"][0]
        client.put(f"/financeiro/patrimonio/{item['id']}", json={
            "nome": item["nome"],
            "vida_util_anos": listado["vida_util_anos"],
            "vida_util_meses": listado["vida_util_meses"],
        })
        depois = client.get("/financeiro/patrimonio").json()["itens"][0]
        assert (depois["vida_util_anos"], depois["vida_util_meses"]) == (10, 6)
