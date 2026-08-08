"""Motor de cálculo nutricional — Fase 1 do módulo "Formulação de Dietas".

Implementação independente em Python das equações publicadas em NASEM
(2021). Não deriva do código-fonte de referência. Uso comercial pendente de
parecer jurídico.

API pública: `avaliar_dieta(entrada: EntradaFormulacao) -> ResultadoFormulacao`.

Todas as funções deste pacote são puras — sem `Session`, sem I/O, sem
`datetime.now()`. Ver a docstring de cada módulo para a ordem exata de
execução do motor (Blocos A a H, Etapas 1 a 14).
"""
# TODO(juridico): confirmar posição antes do lançamento comercial.
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import biblioteca
from .alimentos import (
    ConcentracoesDieta,
    concentracoes_dieta,
    normalizar_proporcoes,
    perfil_ingrediente,
)
from .balanco import montar_balanco
from .consumo import ResultadoConsumo, calcular_cms
from .digestao import ResultadoDigestao, calcular_digestao
from .energia import (
    ResultadoEnergia,
    ResultadoGestacao,
    calcular_energia,
    calcular_gestacao,
    composicao_corporal,
    composicao_ganho,
)
from .microbiana import ResultadoMicrobiana, calcular_microbiana
from .minerais import ResultadoMinerais, calcular_minerais
from .proteina import (
    ResultadoProteina,
    calcular_exigencias_manutencao,
    calcular_proteina,
    nitrogenio_urinario_g_dia,
)
from .tipos import (
    Aviso,
    CATEGORIAS_NASEM,
    EntradaFormulacao,
    ESTADOS_FISIOLOGICOS,
    IngredienteEntrada,
    LinhaBalanco,
    RACAS,
    ValorInvalidoError,
    validar_entrada,
)

VERSAO_MOTOR = "nasem2021-py-fase1.0"


@dataclass
class ResultadoAnimal:
    estado_fisiologico: str
    raca: str
    peso_vivo_kg: float
    peso_metabolico_kg: float
    peso_maturo_kg: float
    peso_vazio_kg: float
    peso_maturo_vazio_kg: float
    razao_peso_vazio: float


@dataclass
class ResultadoMantenca:
    nel_mcal_dia: float
    em_mcal_dia: float
    eficiencia_em_el: float


@dataclass
class ResultadoCorpo:
    ganho_estrutura_kg_dia: float
    ganho_reserva_kg_dia: float
    ganho_total_kg_dia: float
    gordura_ganho_kg_dia: float
    proteina_liquida_ganho_g_dia: float
    energia_retida_ganho_mcal_dia: float


@dataclass
class ResultadoLeite:
    producao_kg_dia: float
    gordura_pct: float | None
    proteina_pct: float | None
    lactose_pct: float
    nel_concentracao_mcal_kg: float
    nel_mcal_dia: float
    em_mcal_dia: float
    proteina_liquida_g_dia: float
    leite_permitido_por_el_kg_dia: float
    leite_permitido_por_pm_kg_dia: float | None


@dataclass
class IngredienteResultado:
    nome: str
    categoria_nasem: str
    proporcao_ms_pct: float
    kg_materia_seca_dia: float
    kg_materia_natural_dia: float
    custo_dia: float


@dataclass
class ResultadoFormulacao:
    motor_versao: str
    animal: ResultadoAnimal
    consumo: ResultadoConsumo
    dieta: ConcentracoesDieta
    digestao: ResultadoDigestao
    energia: ResultadoEnergia
    microbiana: ResultadoMicrobiana
    proteina: ResultadoProteina
    mantenca: ResultadoMantenca
    gestacao: ResultadoGestacao
    corpo: ResultadoCorpo
    leite: ResultadoLeite
    minerais: ResultadoMinerais
    ingredientes: list[IngredienteResultado]
    balanco: list[LinhaBalanco]
    avisos: list[Aviso]


def _preencher_ingredientes(
    ingredientes: list[IngredienteEntrada],
) -> tuple[list[IngredienteEntrada], list[str]]:
    """Preenche cada ingrediente com o template da sua categoria, e devolve
    também os nomes dos ingredientes que tinham algum campo nutricional
    faltando (para o aviso informativo)."""
    from .tipos import CAMPOS_NUTRICIONAIS

    preenchidos = []
    incompletos = []
    for ing in ingredientes:
        faltando = any(getattr(ing, campo) is None for campo in CAMPOS_NUTRICIONAIS)
        if faltando:
            incompletos.append(ing.nome)
        preenchidos.append(biblioteca.preencher_com_template(ing))
    return preenchidos, incompletos


def avaliar_dieta(entrada: EntradaFormulacao) -> ResultadoFormulacao:
    """Motor completo — ver o docstring do pacote para a ordem dos blocos.

    Levanta `ValorInvalidoError` se a entrada violar o contrato da Fase 1.
    """
    validar_entrada(entrada)
    animal = entrada.animal

    avisos: list[Aviso] = []

    # Etapa 1-2: normalizar proporções e completar ingredientes com o
    # template da categoria; Bloco A (perfil por ingrediente) — nada disso
    # depende do CMS.
    ingredientes_preenchidos, incompletos = _preencher_ingredientes(entrada.ingredientes)
    proporcoes = normalizar_proporcoes(ingredientes_preenchidos)
    perfis = [
        perfil_ingrediente(ing, prop)
        for ing, prop in zip(ingredientes_preenchidos, proporcoes)
    ]
    if incompletos:
        avisos.append(
            Aviso(
                codigo="ingrediente_completado_por_template",
                severidade="info",
                mensagem=(
                    "Ingredientes sem laudo completo usaram valores padrão da "
                    "categoria para os campos faltantes: " + ", ".join(incompletos)
                ),
            )
        )

    # Etapa 3: Bloco C — concentrações da dieta (não depende do CMS).
    dieta = concentracoes_dieta(perfis)

    # Etapa 4: Bloco B — CMS.
    consumo = calcular_cms(animal, dieta)
    cms = consumo.cms_kg_dia

    # Etapa 5-6: ingestões (kg/d) e Bloco D — digestão ruminal/trato total.
    digestao = calcular_digestao(dieta, animal, cms)

    # Etapa 7: Bloco E — proteína microbiana. dieta.rdp_pct_dm é a
    # concentração de PDR (% MS) da dieta, usada para o teto de 12%.
    microbiana = calcular_microbiana(dieta.rdp_pct_dm, digestao.ingestoes, digestao)

    # Etapa 8: Bloco F (primeira metade) — PM fornecida (calculada dentro de
    # calcular_proteina mais abaixo, reaproveitando suprimento).

    # Etapa 9: exigências de manutenção + fecha o nitrogênio urinário ANTES
    # da energia.
    manutencao = calcular_exigencias_manutencao(animal, dieta, cms)
    corpo_comp = composicao_corporal(animal)
    ganho = composicao_ganho(animal)
    gestacao = calcular_gestacao(animal)

    leite_np_g = 0.0
    if animal.producao_leite_kg_dia and animal.proteina_leite_pct:
        leite_np_g = animal.producao_leite_kg_dia * animal.proteina_leite_pct / 100.0 * 1000.0

    n_urinario = nitrogenio_urinario_g_dia(
        ingestoes=digestao.ingestoes,
        microbiana=microbiana,
        manutencao=manutencao,
        leite_np_g=leite_np_g,
        ganho_np_g=ganho.proteina_liquida_total_g,
        gestacao_cp_g=gestacao.proteina_bruta_g_dia,
    )

    # Etapa 10: Bloco G — energia completa.
    resultado_energia = calcular_energia(
        animal=animal,
        ge_mcal_dia=digestao.ingestoes.ge_mcal,
        de_base_mcal_dia=digestao.ingestoes.de_base_mcal,
        cms_kg_dia=cms,
        fdn_pct_dieta=dieta.fdn_pct,
        ag_pct_dieta=dieta.ag_pct,
        ndf_digerida_pct_dieta=digestao.ndf_digerida_pct_dieta,
        nitrogenio_urinario_g_dia=n_urinario,
        ganho=ganho,
        gestacao=gestacao,
    )
    if resultado_energia.aviso_metano_alternativo:
        avisos.append(
            Aviso(
                codigo="metano_referencia_alternativa",
                severidade="info",
                mensagem=(
                    "A perda de energia em gases (metano) para este estado "
                    "fisiológico tem uma segunda parametrização publicada na "
                    "literatura — o valor pode variar alguns pontos "
                    "percentuais dependendo da fonte."
                ),
            )
        )

    # Etapa 11: Bloco F (resto) — exigências finais de PM e balanço-alvo.
    resultado_proteina = calcular_proteina(
        animal=animal,
        dieta=dieta,
        ingestoes=digestao.ingestoes,
        microbiana=microbiana,
        ganho=ganho,
        gestacao=gestacao,
        corpo=corpo_comp,
        manutencao=manutencao,
        leite_np_g=leite_np_g,
        n_urinario_g=n_urinario,
    )
    if resultado_proteina.exigencias.ajuste_novilha_aplicado:
        avisos.append(
            Aviso(
                codigo="ajuste_novilha_pm_me",
                severidade="info",
                mensagem=(
                    "A exigência de proteína metabolizável para ganho desta "
                    "novilha foi ajustada para cima porque a razão PM:EM da "
                    "dieta estava abaixo do ótimo para o desenvolvimento."
                ),
            )
        )

    # Etapa 12: Bloco H — macrominerais + DCAD.
    resultado_minerais = calcular_minerais(
        animal=animal, dieta=dieta, ingestoes=digestao.ingestoes, ganho=ganho, gestacao=gestacao,
    )

    # Etapa 13: monta o balanço para a UI.
    custo_dieta_dia = dieta.custo_kg_ms * cms
    linhas_balanco = montar_balanco(
        dieta=dieta,
        ingestoes=digestao.ingestoes,
        energia=resultado_energia,
        proteina=resultado_proteina,
        minerais=resultado_minerais,
        custo_dieta_dia=custo_dieta_dia,
    )
    for linha in linhas_balanco:
        if linha.situacao == "deficit" and linha.exigencia > 0:
            avisos.append(
                Aviso(
                    codigo=f"deficit_{linha.nutriente.split()[0].lower()}",
                    severidade="atencao",
                    mensagem=f"{linha.nutriente}: déficit de {abs(linha.balanco):.2f} {linha.unidade}.",
                )
            )

    # Etapa 14: montar o resultado final.
    ingredientes_resultado = [
        IngredienteResultado(
            nome=perfil.nome,
            categoria_nasem=perfil.categoria_nasem,
            proporcao_ms_pct=perfil.proporcao_normalizada * 100.0,
            kg_materia_seca_dia=perfil.proporcao_normalizada * cms,
            kg_materia_natural_dia=(perfil.proporcao_normalizada * cms) / perfil.ms_fracao
            if perfil.ms_fracao > 0
            else 0.0,
            custo_dia=((perfil.proporcao_normalizada * cms) / perfil.ms_fracao if perfil.ms_fracao > 0 else 0.0)
            * perfil.custo_kg_mn,
        )
        for perfil in perfis
    ]

    animal_resultado = ResultadoAnimal(
        estado_fisiologico=animal.estado_fisiologico,
        raca=animal.raca,
        peso_vivo_kg=animal.peso_vivo_kg,
        peso_metabolico_kg=animal.peso_vivo_kg ** 0.75,
        peso_maturo_kg=animal.peso_maturo_kg,
        peso_vazio_kg=corpo_comp.peso_vazio_kg,
        peso_maturo_vazio_kg=corpo_comp.peso_maturo_vazio_kg,
        razao_peso_vazio=corpo_comp.razao_peso_vazio,
    )

    mantenca_resultado = ResultadoMantenca(
        nel_mcal_dia=resultado_energia.nel_mantenca_mcal,
        em_mcal_dia=resultado_energia.em_mantenca_mcal,
        eficiencia_em_el=resultado_energia.eficiencia_em_el_mantenca,
    )

    corpo_resultado = ResultadoCorpo(
        ganho_estrutura_kg_dia=animal.ganho_estrutura_kg_dia,
        ganho_reserva_kg_dia=animal.ganho_reserva_kg_dia,
        ganho_total_kg_dia=ganho.ganho_alvo_total_kg,
        gordura_ganho_kg_dia=ganho.gordura_total_kg,
        proteina_liquida_ganho_g_dia=ganho.proteina_liquida_total_g,
        energia_retida_ganho_mcal_dia=ganho.energia_retida_total_mcal,
    )

    leite_resultado = ResultadoLeite(
        producao_kg_dia=animal.producao_leite_kg_dia or 0.0,
        gordura_pct=animal.gordura_leite_pct,
        proteina_pct=animal.proteina_leite_pct,
        lactose_pct=animal.lactose_leite_pct,
        nel_concentracao_mcal_kg=resultado_energia.nel_leite_concentracao_mcal_kg,
        nel_mcal_dia=resultado_energia.nel_leite_mcal,
        em_mcal_dia=resultado_energia.em_leite_mcal,
        proteina_liquida_g_dia=leite_np_g,
        leite_permitido_por_el_kg_dia=resultado_energia.leite_permitido_por_el_kg_dia,
        leite_permitido_por_pm_kg_dia=resultado_proteina.leite_permitido_por_pm_kg_dia,
    )

    return ResultadoFormulacao(
        motor_versao=VERSAO_MOTOR,
        animal=animal_resultado,
        consumo=consumo,
        dieta=dieta,
        digestao=digestao,
        energia=resultado_energia,
        microbiana=microbiana,
        proteina=resultado_proteina,
        mantenca=mantenca_resultado,
        gestacao=gestacao,
        corpo=corpo_resultado,
        leite=leite_resultado,
        minerais=resultado_minerais,
        ingredientes=ingredientes_resultado,
        balanco=linhas_balanco,
        avisos=avisos,
    )


def resultado_para_dict(resultado: ResultadoFormulacao) -> dict:
    """Serializa `ResultadoFormulacao` (e todas as dataclasses aninhadas)
    para um `dict` pronto para `json.dumps`."""
    return asdict(resultado)


__all__ = [
    "VERSAO_MOTOR",
    "avaliar_dieta",
    "resultado_para_dict",
    "ResultadoFormulacao",
    "ResultadoAnimal",
    "ResultadoMantenca",
    "ResultadoCorpo",
    "ResultadoLeite",
    "IngredienteResultado",
    "EntradaFormulacao",
    "Aviso",
    "ValorInvalidoError",
    "CATEGORIAS_NASEM",
    "ESTADOS_FISIOLOGICOS",
    "RACAS",
]
