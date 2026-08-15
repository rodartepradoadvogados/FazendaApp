"""Templates nutricionais por `categoria_nasem` e biblioteca semente de
ingredientes brasileiros de uso corrente.

Os templates cobrem TODOS os ~38 campos nutricionais de `IngredienteEntrada`
com "valores padrão da categoria, sem laudo/composição real — servem só de
ponto de partida" para que nenhum ingrediente sem dado nenhum trave o motor.
Não representam nenhuma tabela de composição publicada específica — são
estimativas de bom senso zootécnico para uso como fallback.
"""
from __future__ import annotations

from dataclasses import replace

from .tipos import CAMPOS_NUTRICIONAIS, CATEGORIAS_NASEM, IngredienteEntrada

# ---------------------------------------------------------------------------
# Templates por categoria
# ---------------------------------------------------------------------------

_BASE_GENERICA: dict[str, float] = {
    "ms_pct": 88.0,
    "pb_pct": 12.0,
    "fdn_pct": 35.0,
    "fda_pct": 22.0,
    "lignina_pct": 4.0,
    "amido_pct": 20.0,
    "acucares_pct": 4.0,
    "ee_pct": 3.5,
    "ag_pct": 2.8,
    "cinzas_pct": 7.0,
    "dndf48_fdn_pct": 55.0,
    "pb_a_pct": 25.0,
    "pb_b_pct": 60.0,
    "pb_c_pct": 15.0,
    "kd_pb_b_pct_h": 8.0,
    "nnp_pb_pct": 15.0,
    "pidn_pct": 1.0,
    "pida_pct": 0.4,
    "dig_amido_pct": 90.0,
    "dig_pndr_pct": 80.0,
    "dig_ag_pct": 75.0,
    "ca_pct": 0.6,
    "p_pct": 0.35,
    "p_inorg_p_pct": 50.0,
    "p_org_p_pct": 50.0,
    "mg_pct": 0.20,
    "k_pct": 1.2,
    "na_pct": 0.05,
    "cl_pct": 0.2,
    "s_pct": 0.20,
    "abs_ca": 0.60,
    "abs_p_total": 0.70,
    "abs_mg": 0.20,
    "abs_na": 0.90,
    "abs_cl": 0.92,
    "abs_k": 0.90,
    "custo_kg_mn": 1.00,
}


def _template(**overrides: float) -> dict[str, float]:
    valores = dict(_BASE_GENERICA)
    valores.update(overrides)
    return valores


_TEMPLATES_POR_CATEGORIA: dict[str, dict[str, float]] = {
    "Forragem": _template(
        ms_pct=35.0,
        pb_pct=9.0,
        fdn_pct=58.0,
        fda_pct=38.0,
        lignina_pct=5.5,
        amido_pct=3.0,
        acucares_pct=3.0,
        ee_pct=3.0,
        ag_pct=2.2,
        cinzas_pct=7.5,
        dndf48_fdn_pct=48.3,
        pb_a_pct=20.0,
        pb_b_pct=65.0,
        pb_c_pct=15.0,
        kd_pb_b_pct_h=6.0,
        nnp_pb_pct=40.0,
        pidn_pct=1.2,
        pida_pct=0.5,
        dig_amido_pct=90.0,
        dig_pndr_pct=75.0,
        dig_ag_pct=70.0,
        ca_pct=0.40,
        p_pct=0.25,
        mg_pct=0.20,
        k_pct=1.6,
        na_pct=0.02,
        cl_pct=0.30,
        s_pct=0.15,
        abs_ca=0.30,
        abs_p_total=0.65,
        abs_mg=0.16,
        custo_kg_mn=0.35,
    ),
    "Pastagem": _template(
        ms_pct=22.0,
        pb_pct=14.0,
        fdn_pct=60.0,
        fda_pct=34.0,
        lignina_pct=4.5,
        amido_pct=1.5,
        acucares_pct=6.0,
        ee_pct=2.5,
        ag_pct=1.8,
        cinzas_pct=9.5,
        dndf48_fdn_pct=48.3,
        pb_a_pct=35.0,
        pb_b_pct=50.0,
        pb_c_pct=15.0,
        kd_pb_b_pct_h=9.0,
        nnp_pb_pct=35.0,
        dig_amido_pct=88.0,
        dig_pndr_pct=70.0,
        ca_pct=0.45,
        p_pct=0.30,
        mg_pct=0.22,
        k_pct=2.2,
        na_pct=0.03,
        s_pct=0.18,
        abs_ca=0.30,
        abs_p_total=0.65,
        abs_mg=0.14,
        custo_kg_mn=0.05,
    ),
    "Concentrado energetico": _template(
        ms_pct=88.0,
        pb_pct=9.5,
        fdn_pct=11.0,
        fda_pct=3.5,
        lignina_pct=0.7,
        amido_pct=68.0,
        acucares_pct=2.5,
        ee_pct=4.0,
        ag_pct=3.6,
        cinzas_pct=1.6,
        dndf48_fdn_pct=65.0,
        pb_a_pct=25.0,
        pb_b_pct=68.0,
        pb_c_pct=7.0,
        kd_pb_b_pct_h=10.0,
        nnp_pb_pct=5.0,
        dig_amido_pct=94.0,
        dig_pndr_pct=85.0,
        ca_pct=0.05,
        p_pct=0.30,
        mg_pct=0.13,
        k_pct=0.40,
        na_pct=0.02,
        s_pct=0.12,
        abs_p_total=0.72,
        custo_kg_mn=1.10,
    ),
    "Concentrado proteico": _template(
        ms_pct=89.0,
        pb_pct=46.0,
        fdn_pct=14.0,
        fda_pct=9.0,
        lignina_pct=1.0,
        amido_pct=6.0,
        acucares_pct=8.0,
        ee_pct=2.0,
        ag_pct=1.6,
        cinzas_pct=6.5,
        dndf48_fdn_pct=65.0,
        pb_a_pct=15.0,
        pb_b_pct=75.0,
        pb_c_pct=10.0,
        kd_pb_b_pct_h=12.0,
        nnp_pb_pct=2.0,
        dig_amido_pct=94.0,
        dig_pndr_pct=93.0,
        ca_pct=0.30,
        p_pct=0.65,
        mg_pct=0.30,
        k_pct=2.0,
        na_pct=0.02,
        s_pct=0.40,
        abs_p_total=0.72,
        custo_kg_mn=2.60,
    ),
    "Proteina animal": _template(
        ms_pct=93.0,
        pb_pct=60.0,
        fdn_pct=2.0,
        fda_pct=1.0,
        lignina_pct=0.2,
        amido_pct=0.0,
        acucares_pct=0.0,
        ee_pct=10.0,
        ag_pct=8.5,
        cinzas_pct=20.0,
        pb_a_pct=10.0,
        pb_b_pct=55.0,
        pb_c_pct=35.0,
        kd_pb_b_pct_h=5.0,
        nnp_pb_pct=1.0,
        dig_pndr_pct=80.0,
        ca_pct=5.0,
        p_pct=2.8,
        mg_pct=0.10,
        k_pct=0.60,
        na_pct=0.60,
        s_pct=0.50,
        abs_p_total=0.75,
        custo_kg_mn=4.50,
    ),
    "Suplemento de gordura": _template(
        ms_pct=98.0,
        pb_pct=0.0,
        fdn_pct=0.0,
        fda_pct=0.0,
        lignina_pct=0.0,
        amido_pct=0.0,
        acucares_pct=0.0,
        ee_pct=92.0,
        ag_pct=86.0,
        cinzas_pct=2.0,
        pb_a_pct=0.0,
        pb_b_pct=0.0,
        pb_c_pct=0.0,
        nnp_pb_pct=0.0,
        dig_ag_pct=78.0,
        ca_pct=0.10,
        p_pct=0.02,
        mg_pct=0.02,
        k_pct=0.02,
        na_pct=0.02,
        s_pct=0.01,
        custo_kg_mn=6.50,
    ),
    "Suplemento de acido graxo": _template(
        ms_pct=99.0,
        pb_pct=0.0,
        fdn_pct=0.0,
        fda_pct=0.0,
        lignina_pct=0.0,
        amido_pct=0.0,
        acucares_pct=0.0,
        ee_pct=98.0,
        ag_pct=96.0,
        cinzas_pct=1.0,
        pb_a_pct=0.0,
        pb_b_pct=0.0,
        pb_c_pct=0.0,
        nnp_pb_pct=0.0,
        dig_ag_pct=85.0,
        ca_pct=0.05,
        p_pct=0.01,
        mg_pct=0.01,
        k_pct=0.01,
        na_pct=0.01,
        s_pct=0.0,
        custo_kg_mn=9.00,
    ),
    "Acucar/alcool de acucar": _template(
        ms_pct=92.0,
        pb_pct=6.0,
        fdn_pct=0.0,
        fda_pct=0.0,
        lignina_pct=0.0,
        amido_pct=0.0,
        acucares_pct=85.0,
        ee_pct=0.5,
        ag_pct=0.3,
        cinzas_pct=2.0,
        pb_a_pct=100.0,
        pb_b_pct=0.0,
        pb_c_pct=0.0,
        nnp_pb_pct=90.0,
        ca_pct=0.10,
        p_pct=0.05,
        mg_pct=0.05,
        k_pct=0.20,
        na_pct=0.02,
        s_pct=0.05,
        custo_kg_mn=1.50,
    ),
    "Vitaminico/mineral": _template(
        ms_pct=98.0,
        pb_pct=0.0,
        fdn_pct=0.0,
        fda_pct=0.0,
        lignina_pct=0.0,
        amido_pct=0.0,
        acucares_pct=0.0,
        ee_pct=0.0,
        ag_pct=0.0,
        cinzas_pct=85.0,
        pb_a_pct=0.0,
        pb_b_pct=0.0,
        pb_c_pct=0.0,
        nnp_pb_pct=0.0,
        dig_amido_pct=0.0,
        dig_pndr_pct=0.0,
        dig_ag_pct=0.0,
        ca_pct=18.0,
        p_pct=8.0,
        p_inorg_p_pct=100.0,
        p_org_p_pct=0.0,
        mg_pct=6.0,
        k_pct=1.0,
        na_pct=8.0,
        cl_pct=12.0,
        s_pct=1.0,
        abs_ca=0.50,
        abs_p_total=0.75,
        abs_mg=0.20,
        abs_na=0.95,
        abs_cl=0.95,
        abs_k=0.90,
        custo_kg_mn=5.50,
    ),
    "Leite/sucedaneo": _template(
        ms_pct=96.0,
        pb_pct=22.0,
        fdn_pct=0.0,
        fda_pct=0.0,
        lignina_pct=0.0,
        amido_pct=0.5,
        acucares_pct=38.0,
        ee_pct=18.0,
        ag_pct=17.0,
        cinzas_pct=8.0,
        pb_a_pct=90.0,
        pb_b_pct=10.0,
        pb_c_pct=0.0,
        nnp_pb_pct=2.0,
        dig_pndr_pct=95.0,
        dig_ag_pct=90.0,
        ca_pct=0.90,
        p_pct=0.70,
        mg_pct=0.10,
        k_pct=1.30,
        na_pct=0.45,
        s_pct=0.30,
        custo_kg_mn=12.0,
    ),
    "Outros": _template(),
}


def template_por_categoria(categoria_nasem: str) -> dict[str, float]:
    """Devolve o dicionário de valores-padrão (fallback) da categoria
    informada, com todos os campos de `CAMPOS_NUTRICIONAIS` preenchidos.

    Levanta `KeyError` se `categoria_nasem` não pertencer ao vocabulário
    fechado — a validação de entrada (`tipos.validar_entrada`) já garante
    isso antes deste ponto no fluxo normal de `avaliar_dieta`.
    """
    if categoria_nasem not in CATEGORIAS_NASEM:
        raise KeyError(f"categoria_nasem desconhecida: {categoria_nasem!r}")
    return dict(_TEMPLATES_POR_CATEGORIA[categoria_nasem])


def preencher_com_template(ingrediente: IngredienteEntrada) -> IngredienteEntrada:
    """Devolve uma cópia de `ingrediente` com todo campo nutricional `None`
    preenchido pelo template de `ingrediente.categoria_nasem`."""
    template = template_por_categoria(ingrediente.categoria_nasem)
    preenchidos = {
        campo: getattr(ingrediente, campo)
        if getattr(ingrediente, campo) is not None
        else template[campo]
        for campo in CAMPOS_NUTRICIONAIS
    }
    return replace(ingrediente, **preenchidos)


# ---------------------------------------------------------------------------
# Biblioteca semente — 12 ingredientes brasileiros de uso corrente
# ---------------------------------------------------------------------------

_FONTE_GENERICA = "Referência genérica — ajuste com o laudo da sua fazenda"

# Faixa típica de inclusão na dieta, % da MS TOTAL da dieta (não da MS do
# próprio ingrediente) — bom senso zootécnico de mercado, não uma restrição
# do motor; vira `inclusao_min_pct`/`inclusao_max_pct` na biblioteca mestre
# semeada em AlimentoNutricional (ver fazenda.rules.biblioteca_alimentos) e
# alimenta a sugestão automática da Etapa 1 (grade de alimentos).
_INCLUSAO_SUGERIDA_POR_NOME: dict[str, tuple[float, float]] = {
    "Silagem de milho": (15.0, 40.0),
    "Silagem de sorgo": (10.0, 35.0),
    "Silagem/pré-secado de capim": (10.0, 30.0),
    "Feno de tifton": (5.0, 20.0),
    "Cana-de-açúcar": (5.0, 25.0),
    "Milho moído": (10.0, 35.0),
    "Farelo de soja": (5.0, 20.0),
    "Farelo de algodão 38": (3.0, 12.0),
    "Caroço de algodão": (3.0, 10.0),
    "Polpa cítrica": (5.0, 20.0),
    "Farelo de trigo": (3.0, 15.0),
    # NNP puro — dose baixa por risco de intoxicação amoniacal, nunca a base
    # da fração proteica da dieta.
    "Ureia pecuária": (0.0, 1.5),
}

_CAMPOS_SEMENTE: tuple[str, ...] = (
    "ms_pct",
    "pb_pct",
    "fdn_pct",
    "fda_pct",
    "lignina_pct",
    "amido_pct",
    "ee_pct",
    "cinzas_pct",
    "ca_pct",
    "p_pct",
)

_BIBLIOTECA_SEMENTE_BRUTA: list[dict] = [
    dict(
        nome="Silagem de milho",
        categoria_nasem="Forragem",
        conc_pct=10.0,
        ms_pct=33.0,
        pb_pct=8.5,
        fdn_pct=45.0,
        fda_pct=26.0,
        lignina_pct=3.0,
        amido_pct=30.0,
        ee_pct=3.0,
        cinzas_pct=4.5,
        ca_pct=0.25,
        p_pct=0.22,
    ),
    dict(
        nome="Silagem de sorgo",
        categoria_nasem="Forragem",
        conc_pct=8.0,
        ms_pct=30.0,
        pb_pct=7.5,
        fdn_pct=53.0,
        fda_pct=32.0,
        lignina_pct=4.0,
        amido_pct=18.0,
        ee_pct=2.5,
        cinzas_pct=5.5,
        ca_pct=0.40,
        p_pct=0.22,
    ),
    dict(
        nome="Silagem/pré-secado de capim",
        categoria_nasem="Forragem",
        conc_pct=5.0,
        ms_pct=35.0,
        pb_pct=16.0,
        fdn_pct=60.0,
        fda_pct=37.0,
        lignina_pct=5.0,
        amido_pct=2.0,
        ee_pct=2.5,
        cinzas_pct=9.0,
        ca_pct=0.45,
        p_pct=0.28,
    ),
    dict(
        nome="Feno de tifton",
        categoria_nasem="Forragem",
        conc_pct=3.0,
        ms_pct=88.0,
        pb_pct=11.0,
        fdn_pct=68.0,
        fda_pct=36.0,
        lignina_pct=5.5,
        amido_pct=1.5,
        ee_pct=1.8,
        cinzas_pct=7.5,
        ca_pct=0.40,
        p_pct=0.22,
    ),
    dict(
        nome="Cana-de-açúcar",
        categoria_nasem="Forragem",
        conc_pct=2.0,
        ms_pct=28.0,
        pb_pct=2.5,
        fdn_pct=52.0,
        fda_pct=32.0,
        lignina_pct=6.0,
        amido_pct=1.0,
        ee_pct=1.0,
        cinzas_pct=3.0,
        ca_pct=0.30,
        p_pct=0.10,
    ),
    dict(
        nome="Milho moído",
        categoria_nasem="Concentrado energetico",
        conc_pct=100.0,
        ms_pct=88.0,
        pb_pct=9.5,
        fdn_pct=10.0,
        fda_pct=3.5,
        lignina_pct=0.6,
        amido_pct=71.0,
        ee_pct=4.0,
        cinzas_pct=1.4,
        ca_pct=0.03,
        p_pct=0.28,
    ),
    dict(
        nome="Farelo de soja",
        categoria_nasem="Concentrado proteico",
        conc_pct=100.0,
        ms_pct=89.0,
        pb_pct=48.0,
        fdn_pct=13.0,
        fda_pct=8.5,
        lignina_pct=0.8,
        amido_pct=6.5,
        ee_pct=1.8,
        cinzas_pct=6.5,
        ca_pct=0.30,
        p_pct=0.65,
    ),
    dict(
        nome="Farelo de algodão 38",
        categoria_nasem="Concentrado proteico",
        conc_pct=100.0,
        ms_pct=90.0,
        pb_pct=38.0,
        fdn_pct=28.0,
        fda_pct=20.0,
        lignina_pct=6.0,
        amido_pct=2.5,
        ee_pct=2.5,
        cinzas_pct=6.5,
        ca_pct=0.20,
        p_pct=1.00,
    ),
    dict(
        nome="Caroço de algodão",
        categoria_nasem="Suplemento de gordura",
        conc_pct=100.0,
        ms_pct=90.0,
        pb_pct=22.0,
        fdn_pct=48.0,
        fda_pct=36.0,
        lignina_pct=13.0,
        amido_pct=1.0,
        ee_pct=19.0,
        cinzas_pct=4.0,
        ca_pct=0.15,
        p_pct=0.60,
    ),
    dict(
        nome="Polpa cítrica",
        categoria_nasem="Concentrado energetico",
        conc_pct=100.0,
        ms_pct=88.0,
        pb_pct=7.0,
        fdn_pct=22.0,
        fda_pct=17.0,
        lignina_pct=2.0,
        amido_pct=3.0,
        ee_pct=2.5,
        cinzas_pct=6.5,
        ca_pct=1.80,
        p_pct=0.13,
    ),
    dict(
        nome="Farelo de trigo",
        categoria_nasem="Concentrado energetico",
        conc_pct=100.0,
        ms_pct=88.0,
        pb_pct=16.5,
        fdn_pct=40.0,
        fda_pct=13.0,
        lignina_pct=3.5,
        amido_pct=24.0,
        ee_pct=4.0,
        cinzas_pct=5.5,
        ca_pct=0.13,
        p_pct=1.00,
    ),
    dict(
        nome="Ureia pecuária",
        categoria_nasem="Concentrado proteico",
        conc_pct=100.0,
        ms_pct=99.0,
        pb_pct=281.0,
        fdn_pct=0.0,
        fda_pct=0.0,
        lignina_pct=0.0,
        amido_pct=0.0,
        ee_pct=0.0,
        cinzas_pct=0.0,
        ca_pct=0.0,
        p_pct=0.0,
    ),
]


def biblioteca_semente() -> list[dict]:
    """Devolve os 12 ingredientes brasileiros de uso corrente da biblioteca
    semente, cada um com `nome`, `categoria_nasem`, `conc_pct`, os 10 campos
    bromatológicos de `_CAMPOS_SEMENTE`, `fonte` e a faixa sugerida de
    inclusão (`inclusao_min_pct`/`inclusao_max_pct`)."""
    itens = []
    for bruto in _BIBLIOTECA_SEMENTE_BRUTA:
        item = dict(bruto)
        item["fonte"] = _FONTE_GENERICA
        minimo, maximo = _INCLUSAO_SUGERIDA_POR_NOME.get(item["nome"], (None, None))
        item["inclusao_min_pct"] = minimo
        item["inclusao_max_pct"] = maximo
        itens.append(item)
    return itens


def ingrediente_semente_para_entrada(nome: str, proporcao_ms_pct: float) -> IngredienteEntrada:
    """Constrói um `IngredienteEntrada` a partir de um item da biblioteca
    semente pelo nome (usado por testes e por quem monta uma dieta a partir
    da biblioteca). Levanta `KeyError` se `nome` não existir na semente."""
    for item in _BIBLIOTECA_SEMENTE_BRUTA:
        if item["nome"] == nome:
            dados = {campo: item[campo] for campo in _CAMPOS_SEMENTE}
            return IngredienteEntrada(
                nome=item["nome"],
                categoria_nasem=item["categoria_nasem"],
                conc_pct=item["conc_pct"],
                proporcao_ms_pct=proporcao_ms_pct,
                **dados,
            )
    raise KeyError(f"Ingrediente não encontrado na biblioteca semente: {nome!r}")


__all__ = [
    "template_por_categoria",
    "preencher_com_template",
    "biblioteca_semente",
    "ingrediente_semente_para_entrada",
]
