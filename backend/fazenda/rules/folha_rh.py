"""
Cálculo de Férias e 13º salário — RH ampliado (item de auditoria "RH
ampliado (férias/13º/eSocial)"). A integração com o eSocial (envio ao
governo) está EXPLICITAMENTE FORA de escopo aqui — inviável sem certificado
digital e infraestrutura própria; este módulo só cobre o cálculo interno
usado pelo lançamento em `fazenda.api.routers.cadastro` (endpoints
`/cadastro/ferias` e `/cadastro/decimo-terceiro`).

Funções puras, sem I/O — fáceis de testar isoladamente (ver
`backend/tests/test_folha_rh.py`).
"""
from __future__ import annotations

TERCO_CONSTITUCIONAL_PADRAO = 1 / 3


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
