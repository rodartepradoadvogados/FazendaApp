"""Contrato de entrada/saída do motor nutricional e vocabulário fechado.

Reimplementação independente das equações publicadas em NASEM (2021). Ver
`fazenda.rules.nutricao.__init__` para o aviso de propriedade intelectual
completo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Vocabulário fechado
# ---------------------------------------------------------------------------

CATEGORIAS_NASEM: frozenset[str] = frozenset(
    {
        "Forragem",
        "Pastagem",
        "Concentrado energetico",
        "Concentrado proteico",
        "Proteina animal",
        "Suplemento de gordura",
        "Suplemento de acido graxo",
        "Acucar/alcool de acucar",
        "Vitaminico/mineral",
        "Leite/sucedaneo",
        "Outros",
    }
)

ESTADOS_FISIOLOGICOS: frozenset[str] = frozenset(
    {"vaca_lactante", "vaca_seca", "novilha", "bezerra"}
)

RACAS: frozenset[str] = frozenset({"Holandes", "Jersey", "Outra"})

EQUACOES_CMS_VALIDAS: frozenset[int] = frozenset({0, 2, 3, 8, 9, 10, 11})
MODOS_MONENSINA: frozenset[str] = frozenset({"kg", "pct", "manual"})

SeveridadeAviso = Literal["info", "atencao", "bloqueante"]


class ValorInvalidoError(ValueError):
    """Levantado quando a entrada de `avaliar_dieta` viola o contrato de
    validação da Fase 1. O chamador HTTP converte isso em 400/422."""


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


@dataclass
class AnimalEntrada:
    """Espelha os campos de animal/lote de `DietaSimulacao`
    (ver `fazenda/models/formulacao.py`)."""

    estado_fisiologico: str = "vaca_lactante"
    raca: str = "Holandes"
    peso_vivo_kg: float = 0.0
    peso_maturo_kg: float = 680.0
    ecc: float = 3.0
    paridade: float = 1.0
    idade_dias: Optional[int] = None
    del_dias: Optional[int] = None
    dias_gestacao: Optional[int] = None
    duracao_gestacao_dias: int = 283
    peso_bezerro_nascer_kg: float = 44.1
    del_concepcao: Optional[int] = None
    idade_concepcao_1a_dias: Optional[int] = None
    ganho_estrutura_kg_dia: float = 0.0
    ganho_reserva_kg_dia: float = 0.0
    producao_leite_kg_dia: Optional[float] = None
    gordura_leite_pct: Optional[float] = None
    proteina_leite_pct: Optional[float] = None
    lactose_leite_pct: float = 4.78
    potencial_genetico_pl_305: float = 280.0

    temperatura_c: float = 24.0
    distancia_sala_m: float = 0.0
    viagens_sala_dia: int = 4
    desnivel_diario_m: float = 0.0

    eq_cms: int = 8
    cms_informado_kg_dia: Optional[float] = None
    usa_monensina: bool = False
    # Como descontar o efeito da monensina sobre o CMS quando `usa_monensina`
    # (ver constantes.MONENSINA_CMS_*): "kg" = desconto fixo de 0,30 kg/dia
    # (Duffield et al., 2008); "pct" = 2% do CMS; "manual" = o valor digitado
    # em `monensina_reducao_manual`. Ignorado quando usa_monensina é False.
    monensina_modo: str = "kg"
    monensina_reducao_manual: Optional[float] = None
    eq_microbiana: int = 1
    usa_dndf48: int = 0


# Os ~38 campos nutricionais opcionais de AlimentoNutricional, compartilhados
# entre IngredienteEntrada e os dicionários de template/biblioteca semente.
CAMPOS_NUTRICIONAIS: tuple[str, ...] = (
    "ms_pct",
    "pb_pct",
    "fdn_pct",
    "fda_pct",
    "lignina_pct",
    "amido_pct",
    "acucares_pct",
    "ee_pct",
    "ag_pct",
    "cinzas_pct",
    "dndf48_fdn_pct",
    "pb_a_pct",
    "pb_b_pct",
    "pb_c_pct",
    "kd_pb_b_pct_h",
    "nnp_pb_pct",
    "pidn_pct",
    "pida_pct",
    "dig_amido_pct",
    "dig_pndr_pct",
    "dig_ag_pct",
    "ca_pct",
    "p_pct",
    "p_inorg_p_pct",
    "p_org_p_pct",
    "mg_pct",
    "k_pct",
    "na_pct",
    "cl_pct",
    "s_pct",
    "abs_ca",
    "abs_p_total",
    "abs_mg",
    "abs_na",
    "abs_cl",
    "abs_k",
    "custo_kg_mn",
)


@dataclass
class IngredienteEntrada:
    """Um item da grade de ingredientes (espelha `AlimentoNutricional` +
    `DietaSimulacaoItem.proporcao_ms_pct`/`categoria_nasem`)."""

    nome: str
    categoria_nasem: str
    conc_pct: float = 0.0
    proporcao_ms_pct: float = 0.0

    ms_pct: Optional[float] = None
    pb_pct: Optional[float] = None
    fdn_pct: Optional[float] = None
    fda_pct: Optional[float] = None
    lignina_pct: Optional[float] = None
    amido_pct: Optional[float] = None
    acucares_pct: Optional[float] = None
    ee_pct: Optional[float] = None
    ag_pct: Optional[float] = None
    cinzas_pct: Optional[float] = None
    dndf48_fdn_pct: Optional[float] = None

    pb_a_pct: Optional[float] = None
    pb_b_pct: Optional[float] = None
    pb_c_pct: Optional[float] = None
    kd_pb_b_pct_h: Optional[float] = None
    nnp_pb_pct: Optional[float] = None
    pidn_pct: Optional[float] = None
    pida_pct: Optional[float] = None

    dig_amido_pct: Optional[float] = None
    dig_pndr_pct: Optional[float] = None
    dig_ag_pct: Optional[float] = None

    ca_pct: Optional[float] = None
    p_pct: Optional[float] = None
    p_inorg_p_pct: Optional[float] = None
    p_org_p_pct: Optional[float] = None
    mg_pct: Optional[float] = None
    k_pct: Optional[float] = None
    na_pct: Optional[float] = None
    cl_pct: Optional[float] = None
    s_pct: Optional[float] = None

    abs_ca: Optional[float] = None
    abs_p_total: Optional[float] = None
    abs_mg: Optional[float] = None
    abs_na: Optional[float] = None
    abs_cl: Optional[float] = None
    abs_k: Optional[float] = None

    custo_kg_mn: Optional[float] = None


@dataclass
class EntradaFormulacao:
    animal: AnimalEntrada
    ingredientes: list[IngredienteEntrada]


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


@dataclass
class Aviso:
    codigo: str
    severidade: SeveridadeAviso
    mensagem: str


@dataclass
class LinhaBalanco:
    nutriente: str
    unidade: str
    exigencia: float
    fornecido: float
    balanco: float
    situacao: Literal["adequado", "deficit", "excesso"]


MAXIMO_INGREDIENTES = 60


def validar_entrada(entrada: EntradaFormulacao) -> None:
    """Valida `entrada` segundo o contrato da Fase 1, levantando
    `ValorInvalidoError` com mensagem clara em caso de violação."""
    animal = entrada.animal

    if animal.estado_fisiologico not in ESTADOS_FISIOLOGICOS:
        raise ValorInvalidoError(
            f"estado_fisiologico inválido: {animal.estado_fisiologico!r}. "
            f"Valores aceitos: {sorted(ESTADOS_FISIOLOGICOS)}"
        )
    if animal.estado_fisiologico == "bezerra":
        raise ValorInvalidoError(
            "Bezerras ficam para uma fase futura do módulo (Fase 3) — "
            "o motor da Fase 1 cobre vaca lactante, vaca seca e novilha."
        )
    if animal.raca not in RACAS:
        raise ValorInvalidoError(
            f"raca inválida: {animal.raca!r}. Valores aceitos: {sorted(RACAS)}"
        )

    if animal.usa_monensina:
        modo = (animal.monensina_modo or "").lower()
        if modo not in MODOS_MONENSINA:
            raise ValorInvalidoError(
                f"monensina_modo inválido: {animal.monensina_modo!r}. Aceitos: {sorted(MODOS_MONENSINA)}"
            )
        if modo == "manual" and (animal.monensina_reducao_manual is None or animal.monensina_reducao_manual < 0):
            raise ValorInvalidoError(
                "monensina_modo='manual' exige monensina_reducao_manual informado e não negativo (kg de MS/dia)."
            )

    if animal.eq_cms not in EQUACOES_CMS_VALIDAS:
        raise ValorInvalidoError(
            f"eq_cms inválido: {animal.eq_cms!r}. Valores aceitos na Fase 1: "
            f"{sorted(EQUACOES_CMS_VALIDAS)}"
        )

    if animal.eq_cms == 0:
        if not animal.cms_informado_kg_dia or animal.cms_informado_kg_dia <= 0:
            raise ValorInvalidoError(
                "eq_cms=0 exige cms_informado_kg_dia informado e maior que zero."
            )
    elif animal.eq_cms in (2, 3):
        if animal.estado_fisiologico != "novilha":
            raise ValorInvalidoError(
                "eq_cms=2/3 (equações de novilha) só podem ser usadas com "
                "estado_fisiologico='novilha'."
            )
    elif animal.eq_cms in (8, 9):
        if animal.estado_fisiologico != "vaca_lactante":
            raise ValorInvalidoError(
                "eq_cms=8/9 (equações de vaca lactante) só podem ser usadas "
                "com estado_fisiologico='vaca_lactante'."
            )
        if animal.del_dias is None:
            raise ValorInvalidoError("eq_cms=8/9 exige del_dias informado.")
        if animal.producao_leite_kg_dia is None:
            raise ValorInvalidoError(
                "eq_cms=8/9 exige producao_leite_kg_dia informado."
            )
    elif animal.eq_cms in (10, 11):
        if animal.estado_fisiologico != "vaca_seca":
            raise ValorInvalidoError(
                "eq_cms=10/11 (equações de vaca seca) só podem ser usadas "
                "com estado_fisiologico='vaca_seca'."
            )
        if animal.dias_gestacao is None:
            raise ValorInvalidoError("eq_cms=10/11 exige dias_gestacao informado.")

    if (
        animal.estado_fisiologico == "vaca_lactante"
        and (animal.producao_leite_kg_dia or 0) > 0
    ):
        if animal.gordura_leite_pct is None or animal.proteina_leite_pct is None:
            raise ValorInvalidoError(
                "Vaca lactante com produção de leite > 0 exige "
                "gordura_leite_pct e proteina_leite_pct informados — sem "
                "eles o nitrogênio urinário e a energia do leite ficam "
                "indeterminados."
            )

    if animal.eq_microbiana != 1:
        raise ValorInvalidoError(
            "eq_microbiana só aceita o valor 1 (NASEM 2021) na Fase 1."
        )
    if animal.usa_dndf48 != 0:
        raise ValorInvalidoError("usa_dndf48 só aceita o valor 0 na Fase 1.")

    if len(entrada.ingredientes) > MAXIMO_INGREDIENTES:
        raise ValorInvalidoError(
            f"No máximo {MAXIMO_INGREDIENTES} ingredientes são aceitos por "
            f"dieta (recebidos: {len(entrada.ingredientes)})."
        )
    if not entrada.ingredientes:
        raise ValorInvalidoError("A dieta precisa ter ao menos um ingrediente.")

    soma_proporcoes = sum(i.proporcao_ms_pct for i in entrada.ingredientes)
    if soma_proporcoes <= 0:
        raise ValorInvalidoError(
            "A soma de proporcao_ms_pct de todos os ingredientes precisa "
            "ser maior que zero."
        )

    for ingrediente in entrada.ingredientes:
        if ingrediente.categoria_nasem not in CATEGORIAS_NASEM:
            raise ValorInvalidoError(
                f"categoria_nasem inválida em {ingrediente.nome!r}: "
                f"{ingrediente.categoria_nasem!r}. "
                f"Valores aceitos: {sorted(CATEGORIAS_NASEM)}"
            )


__all__ = [
    "CATEGORIAS_NASEM",
    "ESTADOS_FISIOLOGICOS",
    "RACAS",
    "EQUACOES_CMS_VALIDAS",
    "CAMPOS_NUTRICIONAIS",
    "ValorInvalidoError",
    "AnimalEntrada",
    "IngredienteEntrada",
    "EntradaFormulacao",
    "Aviso",
    "LinhaBalanco",
    "MAXIMO_INGREDIENTES",
    "validar_entrada",
]
