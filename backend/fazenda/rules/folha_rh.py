"""
Cálculo de Férias, 13º salário e Rescisão — RH ampliado (item de auditoria
"RH ampliado (férias/13º/eSocial)" e, na parte 2, "regras específicas de
rescisão"). A integração com o eSocial (envio ao governo) está
EXPLICITAMENTE FORA de escopo aqui — inviável sem certificado digital e
infraestrutura própria; este módulo só cobre o cálculo interno usado pelo
lançamento em `fazenda.api.routers.cadastro` (endpoints `/cadastro/ferias`,
`/cadastro/decimo-terceiro` e `/cadastro/rescisao`).

Funções puras, sem I/O — fáceis de testar isoladamente (ver
`backend/tests/test_folha_rh.py`).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from dateutil.relativedelta import relativedelta

TERCO_CONSTITUCIONAL_PADRAO = 1 / 3

TIPOS_RESCISAO = ("sem_justa_causa", "pedido_demissao", "justa_causa", "acordo_mutuo")
TipoRescisao = Literal["sem_justa_causa", "pedido_demissao", "justa_causa", "acordo_mutuo"]


def calcular_ferias(
    salario_base: float,
    dias_gozados: int,
    abono_pecuniario_dias: int = 0,
    percentual_terco: float = TERCO_CONSTITUCIONAL_PADRAO,
) -> dict:
    """
    Calcula o valor de um período de férias:
    - `valor_ferias` = valor do dia (salário/30) × dias efetivamente gozados;
    - `valor_terco_constitucional` = 1/3 constitucional sobre os dias gozados;
    - `valor_abono` = valor do abono pecuniário (dias "vendidos", art. 143
      CLT), incluindo o respectivo 1/3, quando `abono_pecuniario_dias > 0`;
    - `valor_total` = soma dos três.
    """
    valor_dia = salario_base / 30
    valor_ferias = round(valor_dia * dias_gozados, 2)
    valor_terco_constitucional = round(valor_ferias * percentual_terco, 2)
    valor_abono = 0.0
    if abono_pecuniario_dias > 0:
        valor_abono = round(valor_dia * abono_pecuniario_dias * (1 + percentual_terco), 2)
    valor_total = round(valor_ferias + valor_terco_constitucional + valor_abono, 2)
    return {
        "valor_ferias": valor_ferias,
        "valor_terco_constitucional": valor_terco_constitucional,
        "valor_abono": valor_abono,
        "valor_total": valor_total,
    }


def calcular_decimo_terceiro(salario_base: float, meses_trabalhados: int) -> float:
    """Valor bruto do 13º salário, proporcional aos meses trabalhados no ano
    (1 a 12) — `salario_base / 12 * meses_trabalhados`."""
    return round(salario_base / 12 * meses_trabalhados, 2)


# ---------------------------------------------------------------------------
# Rescisão contratual (CLT) — verbas rescisórias das 4 modalidades mais
# comuns. Cobre só o "core" comum a praticamente toda rescisão CLT (saldo de
# salário, aviso prévio, férias vencidas/proporcionais, 13º proporcional,
# multa do FGTS); NÃO cobre verbas específicas de convenção coletiva, multas
# contratuais, estabilidades (gestante, CIPA, acidentário...) nem o eSocial/
# TRCT oficial — tudo isso fica fora de escopo (mesma linha do aviso já
# registrado para férias/13º).
# ---------------------------------------------------------------------------
def _meses_regra_15_dias(inicio: date, fim: date, limite: int | None = 12) -> int:
    """Meses completos entre duas datas aplicando a "regra dos 15 dias"
    (Súmula 45 do TST — usada tanto para 13º salário quanto para férias
    proporcionais): uma fração de mês igual ou superior a 15 dias trabalhados
    conta como mês integral; fração menor é desprezada. `limite` corta o
    resultado (12 para contagens dentro de um único ano/período aquisitivo;
    `None` para o tempo total de casa, usado na estimativa de FGTS)."""
    if fim <= inicio:
        return 0
    diferenca = relativedelta(fim, inicio)
    meses = diferenca.years * 12 + diferenca.months
    if diferenca.days >= 15:
        meses += 1
    meses = max(meses, 0)
    if limite is not None:
        meses = min(meses, limite)
    return meses


def _anos_completos(inicio: date, fim: date) -> int:
    """Anos completos de serviço, SEM arredondamento por fração (diferente de
    `_meses_regra_15_dias`) — é o que a Lei 12.506/2011 usa para os 3 dias
    extras de aviso prévio por "ano completo de serviço"."""
    anos = fim.year - inicio.year
    if (fim.month, fim.day) < (inicio.month, inicio.day):
        anos -= 1
    return max(anos, 0)


def _inicio_periodo_aquisitivo_atual(data_admissao: date, data_referencia: date) -> date:
    """Início do período aquisitivo de férias em curso na data de
    referência — o aniversário de admissão mais recente que seja anterior ou
    igual a ela (ou a própria admissão, se ainda não completou 1 ano)."""
    anos = _anos_completos(data_admissao, data_referencia)
    return data_admissao + relativedelta(years=anos)


def calcular_rescisao(
    salario_base: float,
    data_admissao: date,
    data_desligamento: date,
    tipo_rescisao: TipoRescisao,
    dias_ferias_vencidas: int = 0,
    aviso_previo_trabalhado: bool = False,
    percentual_terco: float = TERCO_CONSTITUCIONAL_PADRAO,
    percentual_estimado_fgts_mensal: float = 0.08,
) -> dict:
    """
    Verbas rescisórias da CLT para as 4 modalidades mais comuns de
    desligamento. Retorna um dict detalhado (cada verba separada + total),
    para o usuário auditar de onde veio cada valor — não só o número final.

    Modalidades (`tipo_rescisao`) e o que cada uma paga:
    - `sem_justa_causa` (iniciativa do empregador): todas as verbas abaixo,
      aviso prévio integral, multa de 40% do FGTS.
    - `pedido_demissao` (iniciativa do empregado): saldo de salário + férias
      vencidas/proporcionais + 13º proporcional. SEM aviso prévio (é o
      empregado quem deveria dar o aviso ao empregador — se não der, o
      empregador PODE descontar o equivalente do saldo, o que este cálculo
      não modela) e SEM multa/saque do FGTS.
    - `justa_causa` (falta grave do empregado, art. 482 CLT): só saldo de
      salário + férias vencidas (direito adquirido, não se perde mesmo na
      justa causa). SEM aviso prévio, SEM férias/13º proporcionais (art. 146,
      parágrafo único, CLT e Lei 4.090/62, art. 3º, respectivamente) e SEM
      multa/saque do FGTS.
    - `acordo_mutuo` (distrato — art. 484-A CLT, Lei 13.467/2017): como
      `sem_justa_causa`, mas com aviso prévio pago pela METADE, multa do
      FGTS de 20% (em vez de 40%) e saque limitado a 80% do saldo do FGTS
      (informativo — este módulo não controla saldo real de FGTS).

    Fórmulas de cada verba:
    - `saldo_salario`: dias corridos trabalhados no mês da rescisão (o dia do
      mês de `data_desligamento`) × (`salario_base` / 30).
    - `aviso_previo` (só sem_justa_causa/acordo_mutuo): 30 dias + 3 dias por
      ano completo de serviço, limitado a 90 dias (Lei 12.506/2011); metade
      disso no acordo mútuo. Se `aviso_previo_trabalhado=True`, só os dias
      ADICIONAIS (além dos 30 iniciais) são indenizados em dinheiro — os 30
      dias-base são considerados trabalhados (folha normal, fora deste
      cálculo). O aviso prévio indenizado PROJETA o fim do contrato (Súmula
      371 TST): os dias indenizados são somados a `data_desligamento` antes
      de calcular férias/13º proporcionais e o tempo total para o FGTS.
    - `ferias_vencidas`: reaproveita `calcular_ferias(salario_base,
      dias_ferias_vencidas)` — dias já adquiridos e não gozados, + 1/3.
    - `ferias_proporcionais`: meses completos do período aquisitivo em curso
      (regra dos 15 dias) convertidos em dias equivalentes (30/12 × meses) e
      passados por `calcular_ferias`, também com 1/3. Zerada na justa causa.
    - `decimo_terceiro_proporcional`: reaproveita `calcular_decimo_terceiro`
      com os meses completos (regra dos 15 dias) trabalhados no ano da
      rescisão. Zerada na justa causa.
    - `fgts` — **ESTIMATIVA**: o sistema não rastreia os depósitos mensais
      reais de FGTS, então o total depositado é aproximado por
      `salario_base × percentual_estimado_fgts_mensal (padrão 8%) × meses de
      casa`; a multa é esse total estimado × 40% (sem_justa_causa), 20%
      (acordo_mutuo) ou 0% (pedido_demissao/justa_causa). Use o valor real do
      extrato do FGTS sempre que disponível — este número é só uma
      referência.
    """
    if tipo_rescisao not in TIPOS_RESCISAO:
        raise ValueError(f"tipo_rescisao inválido: {tipo_rescisao!r} (esperado um de {TIPOS_RESCISAO})")

    # --- Saldo de salário ---------------------------------------------------
    dias_trabalhados_no_mes = data_desligamento.day
    saldo_salario = round(salario_base / 30 * dias_trabalhados_no_mes, 2)

    # --- Aviso prévio (Lei 12.506/2011) --------------------------------------
    devido_aviso_previo = tipo_rescisao in ("sem_justa_causa", "acordo_mutuo")
    dias_aviso_previo = min(30 + 3 * _anos_completos(data_admissao, data_desligamento), 90)
    if tipo_rescisao == "acordo_mutuo":
        dias_aviso_previo = dias_aviso_previo // 2  # art. 484-A CLT — pela metade
    dias_aviso_indenizados = 0
    valor_aviso_previo = 0.0
    if devido_aviso_previo:
        dias_aviso_indenizados = max(dias_aviso_previo - 30, 0) if aviso_previo_trabalhado else dias_aviso_previo
        valor_aviso_previo = round(salario_base / 30 * dias_aviso_indenizados, 2)

    # Projeção do aviso prévio indenizado (Súmula 371 TST) sobre o tempo de
    # serviço considerado nas verbas abaixo — só quando NÃO foi trabalhado
    # (se foi, `data_desligamento` já é o fim real do contrato).
    if dias_aviso_indenizados and not aviso_previo_trabalhado:
        data_referencia = data_desligamento + timedelta(days=dias_aviso_previo)
    else:
        data_referencia = data_desligamento

    # --- Férias vencidas (direito adquirido — devidas mesmo na justa causa) -
    ferias_vencidas = calcular_ferias(salario_base, dias_ferias_vencidas, 0, percentual_terco)

    # --- Férias proporcionais (perdidas na justa causa — art. 146, § único, CLT)
    meses_ferias_proporcionais = 0
    ferias_proporcionais = {"valor_ferias": 0.0, "valor_terco_constitucional": 0.0, "valor_abono": 0.0, "valor_total": 0.0}
    if tipo_rescisao != "justa_causa":
        inicio_periodo_aquisitivo = _inicio_periodo_aquisitivo_atual(data_admissao, data_referencia)
        meses_ferias_proporcionais = _meses_regra_15_dias(inicio_periodo_aquisitivo, data_referencia, limite=12)
        dias_equivalentes = round(30 / 12 * meses_ferias_proporcionais, 4)
        ferias_proporcionais = calcular_ferias(salario_base, dias_equivalentes, 0, percentual_terco)

    # --- 13º proporcional (perdido na justa causa — Lei 4.090/62, art. 3º) ---
    meses_decimo_terceiro = 0
    valor_decimo_terceiro_proporcional = 0.0
    if tipo_rescisao != "justa_causa":
        inicio_ano = date(data_referencia.year, 1, 1)
        inicio_contagem_ano = max(data_admissao, inicio_ano)
        meses_decimo_terceiro = _meses_regra_15_dias(inicio_contagem_ano, data_referencia, limite=12)
        valor_decimo_terceiro_proporcional = calcular_decimo_terceiro(salario_base, meses_decimo_terceiro)

    # --- Multa do FGTS (ESTIMATIVA — ver docstring) --------------------------
    percentual_multa_fgts = {
        "sem_justa_causa": 0.40,
        "acordo_mutuo": 0.20,
        "pedido_demissao": 0.0,
        "justa_causa": 0.0,
    }[tipo_rescisao]
    percentual_saque_fgts_permitido = {
        "sem_justa_causa": 1.0,
        "acordo_mutuo": 0.80,
        "pedido_demissao": 0.0,
        "justa_causa": 0.0,
    }[tipo_rescisao]
    meses_de_casa_estimados = _meses_regra_15_dias(data_admissao, data_referencia, limite=None)
    deposito_fgts_estimado = round(salario_base * percentual_estimado_fgts_mensal * meses_de_casa_estimados, 2)
    multa_fgts = round(deposito_fgts_estimado * percentual_multa_fgts, 2)

    valor_ferias_proporcionais_total = ferias_proporcionais["valor_total"]
    valor_total = round(
        saldo_salario
        + valor_aviso_previo
        + ferias_vencidas["valor_total"]
        + valor_ferias_proporcionais_total
        + valor_decimo_terceiro_proporcional
        + multa_fgts,
        2,
    )

    return {
        "tipo_rescisao": tipo_rescisao,
        "saldo_salario": {"dias_trabalhados_mes": dias_trabalhados_no_mes, "valor": saldo_salario},
        "aviso_previo": {
            "devido": devido_aviso_previo,
            "dias": dias_aviso_previo if devido_aviso_previo else 0,
            "dias_indenizados": dias_aviso_indenizados,
            "trabalhado": aviso_previo_trabalhado,
            "valor": valor_aviso_previo,
        },
        "ferias_vencidas": ferias_vencidas,
        "ferias_proporcionais": {**ferias_proporcionais, "meses": meses_ferias_proporcionais},
        "decimo_terceiro_proporcional": {"meses": meses_decimo_terceiro, "valor": valor_decimo_terceiro_proporcional},
        "fgts": {
            "estimativa": True,
            "percentual_mensal_estimado": percentual_estimado_fgts_mensal,
            "meses_considerados": meses_de_casa_estimados,
            "deposito_total_estimado": deposito_fgts_estimado,
            "percentual_multa": percentual_multa_fgts,
            "multa": multa_fgts,
            "percentual_saque_permitido": percentual_saque_fgts_permitido,
        },
        "data_referencia_tempo_servico": data_referencia,
        "valor_total": valor_total,
    }
