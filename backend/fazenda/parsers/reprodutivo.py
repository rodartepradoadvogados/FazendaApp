"""
Parser do Consulta_SQL_Dados_Reprodutivos_e_Produtivos_Versao_8.csv
Arquivo com 62 colunas, uma linha por serviço (IA/IATF/Cobertura).

Mapeamento de colunas (índices 1-based conforme inspeção real do CSV):
  04 NÚMERO DA MATRIZ
  08 RAÇA DA MATRIZ
  05 DATA DE NASCIMENTO
  18 DATA DO ÚLTIMO PARTO
  20 ORDEM DE PARTO
  28 DATA DO SERVIÇO
  29 TIPO DO SERVIÇO
  32 PROTOCOLO
  33 REPRODUTOR
  37 ORDEM DE TENTATIVA
  38 INTERVALO ENTRE TENTATIVAS
  41 DATA DO DIAGNOSTICO
  42 DIAGNÓSTICO
  43 DATA DA PERDA DE PRENHEZ
  47 PRODUÇÃO LACTAÇÃO ANTERIOR
  48 DURAÇÃO DA LACTAÇÃO ANTERIOR
  49 PERIODO SECO ANTERIOR
  54 PEV
  55 PARTO_REAL
  56 TIPO_PARTO_REAL
  57 SEXO CRIA 1 - ÚLTIMO PARTO REAL
  58 SEXO CRIA 2 - ÚLTIMO PARTO REAL
  21 RETENÇÃO DE PLACENTA
  22 GEMELAR ÚLTIMO PARTO

NOTA: A coluna ÚLT OCORR do contexto não existe no export CSV atual.
      Calculamos a última ocorrência por animal em Python:
      = linha com maior ORDEM DE TENTATIVA por animal (por último parto).
"""
from __future__ import annotations

from fazenda.models import Parto, Servico
from fazenda.parsers.utils import (
    iter_csv_rows,
    parse_date,
    parse_float,
    parse_int,
)

# Mapeamento robusto: chave interna → candidatos de nome de coluna
# (suporta encoding Latin-1 com caracteres substituídos por '?')
_CAMPO = {
    "numero_matriz":    ["NÚMERO DA MATRIZ", "N\xdaMERO DA MATRIZ", "N?MERO DA MATRIZ", "NUMERO DA MATRIZ"],
    "raca":             ["RAÇA DA MATRIZ", "RA\xc7A DA MATRIZ", "RA?A DA MATRIZ", "RACA DA MATRIZ"],
    "data_nasc":        ["DATA DE NASCIMENTO"],
    "data_ult_parto":   ["DATA DO ÚLTIMO PARTO", "DATA DO ?LTIMO PARTO", "DATA DO ULTIMO PARTO"],
    "ordem_parto":      ["ORDEM DE PARTO"],
    "data_servico":     ["DATA DO SERVIÇO", "DATA DO SERVI?O", "DATA DO SERVICO"],
    "tipo_servico":     ["TIPO DO SERVIÇO", "TIPO DO SERVI?O", "TIPO DO SERVICO"],
    "protocolo":        ["PROTOCOLO"],
    "reprodutor":       ["REPRODUTOR"],
    "ordem_tentativa":  ["ORDEM DE TENTATIVA"],
    "intervalo":        ["INTERVALO ENTRE TENTATIVAS"],
    "data_diagnostico": ["DATA DO DIAGNOSTICO"],
    "diagnostico":      ["DIAGNÓSTICO", "DIAGN?STICO", "DIAGNOSTICO"],
    "data_perda":       ["DATA DA PERDA DE PRENHEZ"],
    "pev":              ["PEV"],
    "categoria":        ["CATEGORIA"],
    "prod_lac_ant":     ["PRODUÇÃO LACTAÇÃO ANTERIOR", "PRODU?O LACTA?O ANTERIOR", "PRODUCAO LACTACAO ANTERIOR",
                         "PRODU\xc7\xc3O LACTA\xc7\xc3O ANTERIOR"],
    "dur_lac_ant":      ["DURAÇÃO DA LACTAÇÃO ANTERIOR (D", "DURA?O DA LACTA?O ANTERIOR (D",
                         "DURACAO DA LACTACAO ANTERIOR (D"],
    "periodo_seco":     ["PERIODO SECO ANTERIOR (DIAS)"],
    "parto_real":       ["PARTO_REAL"],
    "tipo_parto_real":  ["TIPO_PARTO_REAL"],
    "sexo_cria_1":      ["SEXO CRIA 1 - ÚLTIMO PARTO REAL", "SEXO CRIA 1 - ?LTIMO PARTO REAL",
                         "SEXO CRIA 1 - ULTIMO PARTO REAL"],
    "sexo_cria_2":      ["SEXO CRIA 2 - ÚLTIMO PARTO REAL", "SEXO CRIA 2 - ?LTIMO PARTO REAL",
                         "SEXO CRIA 2 - ULTIMO PARTO REAL"],
    "retencao":         ["RETENÇÃO DE PLACENTA", "RETEN?O DE PLACENTA", "RETENCAO DE PLACENTA"],
    "gemelar":          ["GEMELAR ÚLTIMO PARTO", "GEMELAR ?LTIMO PARTO", "GEMELAR ULTIMO PARTO"],
}

# Cache de colunas mapeadas (construído na primeira linha processada)
_col_cache: dict[str, str | None] = {}


def _resolver_colunas(row: dict[str, str]) -> None:
    """Mapeia nomes de colunas reais do CSV para as chaves internas."""
    global _col_cache
    if _col_cache:
        return
    cols_disponiveis = set(row.keys())
    for chave, candidatos in _CAMPO.items():
        encontrado = None
        for c in candidatos:
            if c in cols_disponiveis:
                encontrado = c
                break
        if encontrado is None:
            # Fallback: case-insensitive sem acentos
            chave_lower = chave.replace("_", " ").lower()
            for col in cols_disponiveis:
                if col.lower() == chave_lower:
                    encontrado = col
                    break
        _col_cache[chave] = encontrado


def _get(row: dict[str, str], chave: str) -> str:
    col = _col_cache.get(chave)
    return row.get(col, "") if col else ""


def parse_reprodutivo(content: bytes) -> tuple[list[Servico], list[Parto]]:
    """
    Retorna (servicos, partos) prontos para upsert.

    A última ocorrência por animal é calculada aqui:
    - Agrupa por número de matriz
    - A linha com maior ORDEM DE TENTATIVA (e mais recente DATA DO SERVIÇO) = ult_ocorrencia=1
    """
    global _col_cache
    _col_cache = {}  # reseta cache a cada chamada

    servicos_raw: list[Servico] = []
    partos_vistos: set[tuple[str, str]] = set()
    partos: list[Parto] = []

    for row in iter_csv_rows(content):
        _resolver_colunas(row)

        numero = _get(row, "numero_matriz").strip()
        if not numero:
            continue

        ordem_tent = parse_int(_get(row, "ordem_tentativa")) or 0

        servico = Servico(
            numero_matriz=numero,
            raca_matriz=_get(row, "raca") or None,
            data_nasc_matriz=parse_date(_get(row, "data_nasc")),
            data_ult_parto=parse_date(_get(row, "data_ult_parto")),
            ordem_parto=parse_int(_get(row, "ordem_parto")),
            data_servico=parse_date(_get(row, "data_servico")),
            tipo_servico=_get(row, "tipo_servico") or None,
            protocolo=_get(row, "protocolo") or None,
            reprodutor=_get(row, "reprodutor") or None,
            ordem_tentativa=ordem_tent,
            intervalo_tentativas=parse_int(_get(row, "intervalo")),
            data_diagnostico=parse_date(_get(row, "data_diagnostico")),
            diagnostico=_get(row, "diagnostico") or None,
            data_perda_prenhez=parse_date(_get(row, "data_perda")),
            pev_dias=parse_int(_get(row, "pev")),
            ult_ocorrencia=0,  # calculado abaixo
            categoria=_get(row, "categoria") or None,
            producao_lactacao_anterior=parse_float(_get(row, "prod_lac_ant")),
            duracao_lactacao_anterior=parse_int(_get(row, "dur_lac_ant")),
            periodo_seco_anterior=parse_int(_get(row, "periodo_seco")),
        )
        servicos_raw.append(servico)

        # Extrai parto real (deduplica por numero+data)
        data_parto_raw = _get(row, "parto_real")
        if data_parto_raw:
            key = (numero, data_parto_raw)
            if key not in partos_vistos:
                partos_vistos.add(key)
                gemelar_raw = _get(row, "gemelar")
                retencao_raw = _get(row, "retencao")
                partos.append(Parto(
                    numero_matriz=numero,
                    data_parto=parse_date(data_parto_raw),
                    ordem_parto=parse_int(_get(row, "ordem_parto")),
                    tipo_parto=_get(row, "tipo_parto_real") or None,
                    sexo_cria_1=_get(row, "sexo_cria_1") or None,
                    sexo_cria_2=_get(row, "sexo_cria_2") or None,
                    gemelar=gemelar_raw.upper() in ("SIM", "S") if gemelar_raw else None,
                    retencao_placenta=retencao_raw.upper() in ("SIM", "S") if retencao_raw else None,
                ))

    # ── Calcula ult_ocorrencia: maior ordem_tentativa por animal = 1
    # Agrupa por numero_matriz
    por_animal: dict[str, list[int]] = {}
    for i, s in enumerate(servicos_raw):
        por_animal.setdefault(s.numero_matriz, []).append(i)

    for indices in por_animal.values():
        # Ordena por ordem_tentativa desc, depois data_servico desc
        indices_sorted = sorted(
            indices,
            key=lambda i: (
                servicos_raw[i].ordem_tentativa or 0,
                servicos_raw[i].data_servico or __import__("datetime").date.min,
            ),
            reverse=True,
        )
        # O primeiro (maior tentativa) = última ocorrência
        servicos_raw[indices_sorted[0]].ult_ocorrencia = 1

    return servicos_raw, partos
