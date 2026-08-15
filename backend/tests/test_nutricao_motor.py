"""Testes do motor de cálculo nutricional (Fase 1) de
`fazenda.rules.nutricao` — reimplementação independente das equações
publicadas em NASEM (2021) para Formulação de Dietas.
"""
from __future__ import annotations

import dataclasses
import math

import pytest

from fazenda.rules.nutricao import ResultadoFormulacao, avaliar_dieta
from fazenda.rules.nutricao.biblioteca import ingrediente_semente_para_entrada
from fazenda.rules.nutricao.tipos import (
    AnimalEntrada,
    EntradaFormulacao,
    IngredienteEntrada,
    ValorInvalidoError,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def animal_lactante(**overrides) -> AnimalEntrada:
    base = dict(
        estado_fisiologico="vaca_lactante",
        raca="Holandes",
        peso_vivo_kg=650.0,
        peso_maturo_kg=680.0,
        ecc=3.0,
        paridade=2.0,
        del_dias=150,
        dias_gestacao=None,
        ganho_estrutura_kg_dia=0.0,
        ganho_reserva_kg_dia=0.0,
        producao_leite_kg_dia=35.0,
        gordura_leite_pct=3.8,
        proteina_leite_pct=3.2,
        lactose_leite_pct=4.78,
        eq_cms=8,
    )
    base.update(overrides)
    return AnimalEntrada(**base)


def dieta_referencia() -> list[IngredienteEntrada]:
    """Dieta do caso de referência: silagem de milho 45%, milho moído 22%,
    farelo de soja 15%, silagem de capim 13%, núcleo mineral 5%."""
    return [
        ingrediente_semente_para_entrada("Silagem de milho", 45.0),
        ingrediente_semente_para_entrada("Milho moído", 22.0),
        ingrediente_semente_para_entrada("Farelo de soja", 15.0),
        ingrediente_semente_para_entrada("Silagem/pré-secado de capim", 13.0),
        IngredienteEntrada(
            nome="Núcleo mineral",
            categoria_nasem="Vitaminico/mineral",
            conc_pct=100.0,
            proporcao_ms_pct=5.0,
        ),
    ]


def resultado_referencia() -> ResultadoFormulacao:
    return avaliar_dieta(EntradaFormulacao(animal=animal_lactante(), ingredientes=dieta_referencia()))


def cenario_vaca_seca() -> EntradaFormulacao:
    animal = animal_lactante(
        estado_fisiologico="vaca_seca",
        producao_leite_kg_dia=0.0,
        gordura_leite_pct=None,
        proteina_leite_pct=None,
        eq_cms=10,
        dias_gestacao=250,
        del_dias=None,
        paridade=2.0,
    )
    ingredientes = [
        ingrediente_semente_para_entrada("Silagem de milho", 50.0),
        ingrediente_semente_para_entrada("Silagem/pré-secado de capim", 40.0),
        IngredienteEntrada(
            nome="Núcleo", categoria_nasem="Vitaminico/mineral", conc_pct=100.0, proporcao_ms_pct=10.0
        ),
    ]
    return EntradaFormulacao(animal=animal, ingredientes=ingredientes)


def cenario_novilha() -> EntradaFormulacao:
    animal = animal_lactante(
        estado_fisiologico="novilha",
        paridade=0.0,
        producao_leite_kg_dia=None,
        gordura_leite_pct=None,
        proteina_leite_pct=None,
        eq_cms=2,
        peso_vivo_kg=300.0,
        peso_maturo_kg=650.0,
        del_dias=None,
        dias_gestacao=None,
    )
    ingredientes = [
        ingrediente_semente_para_entrada("Silagem/pré-secado de capim", 60.0),
        ingrediente_semente_para_entrada("Milho moído", 30.0),
        IngredienteEntrada(
            nome="Núcleo", categoria_nasem="Vitaminico/mineral", conc_pct=100.0, proporcao_ms_pct=10.0
        ),
    ]
    return EntradaFormulacao(animal=animal, ingredientes=ingredientes)


def cenario_1_ingrediente() -> EntradaFormulacao:
    return EntradaFormulacao(
        animal=animal_lactante(),
        ingredientes=[ingrediente_semente_para_entrada("Silagem de milho", 100.0)],
    )


def cenario_100_mineral() -> EntradaFormulacao:
    return EntradaFormulacao(
        animal=animal_lactante(),
        ingredientes=[
            IngredienteEntrada(
                nome="Mineral puro", categoria_nasem="Vitaminico/mineral", conc_pct=100.0,
                proporcao_ms_pct=100.0,
            )
        ],
    )


CENARIOS_PARA_INVARIANTES = {
    "referencia": lambda: EntradaFormulacao(animal=animal_lactante(), ingredientes=dieta_referencia()),
    "vaca_seca": cenario_vaca_seca,
    "novilha": cenario_novilha,
    "1_ingrediente": cenario_1_ingrediente,
    "100_mineral": cenario_100_mineral,
}

# Cenários com conteúdo energético real — usados nas invariantes de fluxo de
# energia (EB >= ED >= EM >= EL, todos positivos). Uma dieta 100% mineral não
# tem energia digestível nenhuma por definição (ED=0 é o resultado correto,
# não um bug), então essa invariante de positividade não se aplica a ela.
CENARIOS_COM_ENERGIA = {
    nome: fabrica for nome, fabrica in CENARIOS_PARA_INVARIANTES.items() if nome != "100_mineral"
}


def _assert_sem_nan_inf(obj, caminho: tuple = ()):
    """Percorre `obj` recursivamente garantindo que nenhum campo numérico
    seja NaN/Inf. `None` é sempre aceitável (não é NaN nem Inf) — os campos
    que podem legitimamente ser `None` (ganho permitido por EL, dias para 1
    ECC, leite permitido por PM quando não há alvo definido) são cobertos
    por asserção dedicada em `test_ganho_zero_devolve_none_nao_erro_nao_nan`."""
    if dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            valor = getattr(obj, f.name)
            _assert_sem_nan_inf(valor, caminho + (f.name,))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _assert_sem_nan_inf(item, caminho + (i,))
    elif isinstance(obj, dict):
        for chave, item in obj.items():
            _assert_sem_nan_inf(item, caminho + (chave,))
    elif isinstance(obj, float):
        assert not math.isnan(obj), f"NaN em {'.'.join(map(str, caminho))}"
        assert not math.isinf(obj), f"Inf em {'.'.join(map(str, caminho))}"


# ---------------------------------------------------------------------------
# Invariantes gerais
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_cenario", list(CENARIOS_PARA_INVARIANTES.keys()))
def test_proporcoes_normalizadas_somam_um(nome_cenario):
    entrada = CENARIOS_PARA_INVARIANTES[nome_cenario]()
    resultado = avaliar_dieta(entrada)
    soma = sum(i.proporcao_ms_pct for i in resultado.ingredientes)
    assert abs(soma - 100.0) < 1e-7


@pytest.mark.parametrize("nome_cenario", list(CENARIOS_PARA_INVARIANTES.keys()))
def test_sem_nan_ou_inf(nome_cenario):
    entrada = CENARIOS_PARA_INVARIANTES[nome_cenario]()
    resultado = avaliar_dieta(entrada)
    _assert_sem_nan_inf(resultado)


@pytest.mark.parametrize("nome_cenario", list(CENARIOS_PARA_INVARIANTES.keys()))
def test_escala_invariancia_proporcoes(nome_cenario):
    """Multiplicar todas as proporcoes_ms_pct por um fator não muda nenhuma
    concentração da dieta nem o CMS."""
    entrada = CENARIOS_PARA_INVARIANTES[nome_cenario]()
    resultado_original = avaliar_dieta(entrada)

    ingredientes_escalados = [
        dataclasses.replace(i, proporcao_ms_pct=i.proporcao_ms_pct * 2.7)
        for i in entrada.ingredientes
    ]
    entrada_escalada = EntradaFormulacao(animal=entrada.animal, ingredientes=ingredientes_escalados)
    resultado_escalado = avaliar_dieta(entrada_escalada)

    assert resultado_original.consumo.cms_kg_dia == pytest.approx(
        resultado_escalado.consumo.cms_kg_dia, rel=1e-9
    )
    for campo in ("pb_pct", "fdn_pct", "fda_pct", "amido_pct", "ge_mcal_kg", "ca_pct", "k_pct"):
        assert getattr(resultado_original.dieta, campo) == pytest.approx(
            getattr(resultado_escalado.dieta, campo), rel=1e-9
        )


@pytest.mark.parametrize("nome_cenario", list(CENARIOS_PARA_INVARIANTES.keys()))
def test_em_igual_ed_menos_gases_menos_urina(nome_cenario):
    entrada = CENARIOS_PARA_INVARIANTES[nome_cenario]()
    resultado = avaliar_dieta(entrada)
    en = resultado.energia
    esperado = en.energia_digestivel_mcal - en.perda_gases_mcal - en.perda_urina_mcal
    assert en.energia_metabolizavel_mcal == pytest.approx(esperado, abs=1e-6)


@pytest.mark.parametrize("nome_cenario", list(CENARIOS_PARA_INVARIANTES.keys()))
def test_el_igual_066_vezes_em(nome_cenario):
    entrada = CENARIOS_PARA_INVARIANTES[nome_cenario]()
    resultado = avaliar_dieta(entrada)
    en = resultado.energia
    assert en.energia_liquida_mcal == pytest.approx(0.66 * en.energia_metabolizavel_mcal, abs=1e-6)


@pytest.mark.parametrize("nome_cenario", list(CENARIOS_COM_ENERGIA.keys()))
def test_eb_ed_em_el_decrescentes_e_positivos(nome_cenario):
    entrada = CENARIOS_COM_ENERGIA[nome_cenario]()
    resultado = avaliar_dieta(entrada)
    en = resultado.energia
    assert en.energia_bruta_mcal > 0
    assert en.energia_digestivel_mcal > 0
    assert en.energia_metabolizavel_mcal > 0
    assert en.energia_liquida_mcal > 0
    assert en.energia_bruta_mcal >= en.energia_digestivel_mcal
    assert en.energia_digestivel_mcal >= en.energia_metabolizavel_mcal
    assert en.energia_metabolizavel_mcal >= en.energia_liquida_mcal


@pytest.mark.parametrize("nome_cenario", list(CENARIOS_PARA_INVARIANTES.keys()))
def test_linhas_balanco_consistentes(nome_cenario):
    entrada = CENARIOS_PARA_INVARIANTES[nome_cenario]()
    resultado = avaliar_dieta(entrada)
    for linha in resultado.balanco:
        assert linha.balanco == pytest.approx(linha.fornecido - linha.exigencia, abs=1e-6)


# ---------------------------------------------------------------------------
# Caso de referência — faixas auditadas
# ---------------------------------------------------------------------------


def test_referencia_cms():
    r = resultado_referencia()
    assert 20.0 <= r.consumo.cms_kg_dia <= 27.0


def test_referencia_ell_mantenca():
    r = resultado_referencia()
    assert 12.3 <= r.mantenca.nel_mcal_dia <= 13.4


def test_referencia_ell_dieta_concentracao():
    r = resultado_referencia()
    assert 1.45 <= r.energia.energia_liquida_concentracao_mcal_kg <= 1.80


def test_referencia_pb_dieta():
    r = resultado_referencia()
    assert 15.0 <= r.dieta.pb_pct <= 18.0


def test_referencia_pdr_dieta():
    r = resultado_referencia()
    assert 8.0 <= r.dieta.rdp_pct_dm <= 12.0


def test_referencia_pb_microbiana():
    r = resultado_referencia()
    assert 1500.0 <= r.microbiana.proteina_microbiana_bruta_g_dia <= 3000.0


def test_referencia_pm_fornecida():
    r = resultado_referencia()
    assert 2000.0 <= r.proteina.suprimento.pm_fornecida_g <= 3000.0


def test_referencia_ca_exigencia_absorvido():
    r = resultado_referencia()
    assert 45.0 <= r.minerais.calcio.exigencia <= 75.0


def test_referencia_dcad():
    r = resultado_referencia()
    assert 150.0 <= r.minerais.dcad_meq_kg <= 450.0


# ---------------------------------------------------------------------------
# Casos-limite
# ---------------------------------------------------------------------------


def test_1_ingrediente_nao_quebra():
    r = avaliar_dieta(cenario_1_ingrediente())
    assert r.consumo.cms_kg_dia > 0
    assert len(r.ingredientes) == 1
    assert r.ingredientes[0].proporcao_ms_pct == pytest.approx(100.0)


def test_100_mineral_guarda_divisoes():
    r = avaliar_dieta(cenario_100_mineral())
    assert r.dieta.fdn_pct == 0.0
    assert r.dieta.amido_pct == 0.0
    # piso de 10 g/d no nitrogênio microbiano, mesmo sem substrato fermentável
    assert r.microbiana.nitrogenio_microbiano_g_dia == pytest.approx(10.0)


def test_vaca_seca():
    r = avaliar_dieta(cenario_vaca_seca())
    assert r.consumo.cms_kg_dia > 0
    assert r.animal.estado_fisiologico == "vaca_seca"


def test_novilha():
    r = avaliar_dieta(cenario_novilha())
    assert r.consumo.cms_kg_dia > 0
    assert r.animal.estado_fisiologico == "novilha"


def test_proporcoes_somando_99_7_normaliza():
    ingredientes = [
        ingrediente_semente_para_entrada("Silagem de milho", 44.865),
        ingrediente_semente_para_entrada("Milho moído", 21.934),
        ingrediente_semente_para_entrada("Farelo de soja", 14.955),
        ingrediente_semente_para_entrada("Silagem/pré-secado de capim", 12.958),
        IngredienteEntrada(
            nome="Núcleo mineral", categoria_nasem="Vitaminico/mineral", conc_pct=100.0,
            proporcao_ms_pct=4.985,
        ),
    ]
    soma_bruta = sum(i.proporcao_ms_pct for i in ingredientes)
    assert soma_bruta == pytest.approx(99.697)

    r = avaliar_dieta(EntradaFormulacao(animal=animal_lactante(), ingredientes=ingredientes))
    soma_normalizada = sum(i.proporcao_ms_pct for i in r.ingredientes)
    assert soma_normalizada == pytest.approx(100.0, abs=1e-6)
    # As concentrações devem ficar muito próximas do caso de referência
    # (mesma mistura relativa, só a soma bruta que não batia 100%).
    r_ref = resultado_referencia()
    assert r.dieta.pb_pct == pytest.approx(r_ref.dieta.pb_pct, rel=1e-3)


def test_cms_informado_pelo_usuario():
    entrada = EntradaFormulacao(
        animal=animal_lactante(eq_cms=0, cms_informado_kg_dia=22.0),
        ingredientes=dieta_referencia(),
    )
    r = avaliar_dieta(entrada)
    assert r.consumo.cms_kg_dia == pytest.approx(22.0)


def test_ganho_zero_devolve_none_nao_erro_nao_nan():
    entrada = EntradaFormulacao(
        animal=animal_lactante(ganho_estrutura_kg_dia=0.0, ganho_reserva_kg_dia=0.0),
        ingredientes=dieta_referencia(),
    )
    r = avaliar_dieta(entrada)
    assert r.energia.ganho_permitido_por_el_kg_dia is None
    assert r.energia.dias_para_1_ponto_ecc is None


def test_ganho_nao_zero_devolve_valor_numerico():
    entrada = EntradaFormulacao(
        animal=animal_lactante(ganho_reserva_kg_dia=0.2),
        ingredientes=dieta_referencia(),
    )
    r = avaliar_dieta(entrada)
    assert r.energia.ganho_permitido_por_el_kg_dia is not None
    assert r.energia.dias_para_1_ponto_ecc is not None


# ---------------------------------------------------------------------------
# Validações
# ---------------------------------------------------------------------------


def test_validacao_leite_sem_gordura_proteina():
    entrada = EntradaFormulacao(
        animal=animal_lactante(gordura_leite_pct=None, proteina_leite_pct=None, producao_leite_kg_dia=30.0),
        ingredientes=dieta_referencia(),
    )
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


def test_validacao_eq_cms_estado_incompativel():
    entrada = EntradaFormulacao(
        animal=animal_lactante(eq_cms=8, estado_fisiologico="novilha"),
        ingredientes=dieta_referencia(),
    )
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


def test_validacao_bezerra():
    entrada = EntradaFormulacao(
        animal=animal_lactante(estado_fisiologico="bezerra"),
        ingredientes=dieta_referencia(),
    )
    with pytest.raises(ValorInvalidoError, match="fase futura"):
        avaliar_dieta(entrada)


def test_validacao_mais_de_60_ingredientes():
    ingredientes = [ingrediente_semente_para_entrada("Silagem de milho", 1.0) for _ in range(61)]
    entrada = EntradaFormulacao(animal=animal_lactante(), ingredientes=ingredientes)
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


def test_validacao_eq_cms_zero_sem_cms_informado():
    entrada = EntradaFormulacao(
        animal=animal_lactante(eq_cms=0, cms_informado_kg_dia=None),
        ingredientes=dieta_referencia(),
    )
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


def test_validacao_eq_microbiana_invalido():
    entrada = EntradaFormulacao(
        animal=animal_lactante(eq_microbiana=2), ingredientes=dieta_referencia()
    )
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


def test_validacao_usa_dndf48_invalido():
    entrada = EntradaFormulacao(
        animal=animal_lactante(usa_dndf48=1), ingredientes=dieta_referencia()
    )
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


def test_validacao_categoria_nasem_invalida():
    ingredientes = dieta_referencia()
    ingredientes[0] = dataclasses.replace(ingredientes[0], categoria_nasem="Categoria inexistente")
    entrada = EntradaFormulacao(animal=animal_lactante(), ingredientes=ingredientes)
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


def test_validacao_soma_proporcoes_zero():
    ingredientes = [
        dataclasses.replace(i, proporcao_ms_pct=0.0) for i in dieta_referencia()
    ]
    entrada = EntradaFormulacao(animal=animal_lactante(), ingredientes=ingredientes)
    with pytest.raises(ValorInvalidoError):
        avaliar_dieta(entrada)


# ---------------------------------------------------------------------------
# CMS nas DUAS equações (sem fibra × com fibra) e efeito da monensina — ago/2026
# ---------------------------------------------------------------------------
class TestConsumoDuploEMonensina:
    def _consumo(self, **overrides):
        entrada = EntradaFormulacao(animal=animal_lactante(**overrides), ingredientes=dieta_referencia())
        return avaliar_dieta(entrada).consumo

    def test_calcula_as_duas_equacoes_da_categoria_lactante(self):
        c = self._consumo()
        assert c.equacao_sem_fibra == 8
        assert c.equacao_com_fibra == 9
        assert c.cms_sem_fibra_kg_dia > 0
        assert c.cms_com_fibra_kg_dia > 0

    def test_novilha_usa_o_par_2_e_3(self):
        c = self._consumo(
            estado_fisiologico="novilha", eq_cms=2, paridade=0.0, del_dias=None,
            producao_leite_kg_dia=None, gordura_leite_pct=None, proteina_leite_pct=None,
            peso_vivo_kg=400.0, idade_dias=540,
        )
        assert (c.equacao_sem_fibra, c.equacao_com_fibra) == (2, 3)

    def test_sem_consumo_definido_o_padrao_e_a_estimativa_pelo_animal(self):
        # Mesmo desenho do NASEM Dairy 8: as duas estimativas são leitura e o
        # "Consumo total" é campo à parte. Sem valor definido, vale a do
        # ANIMAL — a da fibra depende da grade estar montada.
        c = self._consumo()
        assert c.cms_kg_dia == pytest.approx(c.cms_sem_fibra_kg_dia)
        assert c.equacao_usada == c.equacao_sem_fibra

    def test_escolher_eq_9_nao_muda_mais_o_resultado(self):
        # eq_cms agora só define a CATEGORIA, não qual número aparece.
        assert self._consumo(eq_cms=8).cms_kg_dia == pytest.approx(self._consumo(eq_cms=9).cms_kg_dia)

    def test_fibra_limitante_e_a_diferenca_entre_as_duas(self):
        c = self._consumo()
        assert c.fibra_limita_kg_dia == pytest.approx(c.cms_sem_fibra_kg_dia - c.cms_com_fibra_kg_dia)
        assert c.fibra_e_limitante is (c.fibra_limita_kg_dia > 0.1)

    def test_cms_informado_vence_as_duas_estimativas(self):
        c = self._consumo(eq_cms=0, cms_informado_kg_dia=22.0)
        assert c.cms_kg_dia == pytest.approx(22.0)
        assert c.equacao_usada == 0
        # As estimativas continuam disponíveis para comparação.
        assert c.cms_sem_fibra_kg_dia > 0 and c.cms_com_fibra_kg_dia > 0

    def test_monensina_kg_desconta_030_dos_dois_cms(self):
        sem = self._consumo(usa_monensina=False)
        com = self._consumo(usa_monensina=True, monensina_modo="kg")
        assert com.cms_sem_fibra_kg_dia == pytest.approx(sem.cms_sem_fibra_kg_dia - 0.30)
        assert com.cms_com_fibra_kg_dia == pytest.approx(sem.cms_com_fibra_kg_dia - 0.30)
        assert com.monensina_reducao_kg_dia == pytest.approx(0.30)

    def test_monensina_pct_desconta_2_por_cento(self):
        sem = self._consumo(usa_monensina=False)
        com = self._consumo(usa_monensina=True, monensina_modo="pct")
        assert com.cms_com_fibra_kg_dia == pytest.approx(sem.cms_com_fibra_kg_dia * 0.98)

    def test_monensina_manual_usa_o_valor_digitado(self):
        sem = self._consumo(usa_monensina=False)
        com = self._consumo(usa_monensina=True, monensina_modo="manual", monensina_reducao_manual=0.8)
        assert com.cms_com_fibra_kg_dia == pytest.approx(sem.cms_com_fibra_kg_dia - 0.8)

    def test_monensina_nunca_zera_ou_inverte_o_cms(self):
        c = self._consumo(usa_monensina=True, monensina_modo="manual", monensina_reducao_manual=999.0)
        assert c.cms_kg_dia > 0

    def test_monensina_desligada_nao_desconta_nada(self):
        assert self._consumo(usa_monensina=False).monensina_reducao_kg_dia == 0.0

    def test_modo_invalido_e_recusado(self):
        with pytest.raises(ValorInvalidoError):
            self._consumo(usa_monensina=True, monensina_modo="inventado")

    def test_modo_manual_sem_valor_e_recusado(self):
        with pytest.raises(ValorInvalidoError):
            self._consumo(usa_monensina=True, monensina_modo="manual", monensina_reducao_manual=None)

    def test_consumo_total_digitado_nao_leva_desconto_de_monensina(self):
        # O valor digitado é respeitado como está: se veio de medição no
        # cocho, o efeito da monensina já está embutido nele.
        c = self._consumo(usa_monensina=True, monensina_modo="kg", cms_informado_kg_dia=21.0)
        assert c.cms_kg_dia == pytest.approx(21.0)
        # As estimativas ao lado continuam descontadas.
        sem = self._consumo(usa_monensina=False)
        assert c.cms_sem_fibra_kg_dia == pytest.approx(sem.cms_sem_fibra_kg_dia - 0.30)

    def test_consumo_total_vence_mesmo_com_categoria_definida(self):
        # eq_cms diz só a CATEGORIA; quem manda no balanço é o Consumo total.
        c = self._consumo(eq_cms=8, cms_informado_kg_dia=19.5)
        assert c.cms_kg_dia == pytest.approx(19.5)
        assert c.equacao_usada == 0
