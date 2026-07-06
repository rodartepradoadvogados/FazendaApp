"""
Análise reprodutiva — transforma os serviços em registros achatados com as
dimensões usadas nos dashboards (concepção/perda por categoria, raça, ordem
de parto/tentativa, condição de IA, inseminador, mês, DEL no serviço).

O front consome esses registros e fatia/agrega conforme os filtros escolhidos.
Métrica central: TAXA DE CONCEPÇÃO = positivos / serviços diagnosticados.
"""
from __future__ import annotations

from datetime import date


def _del_servico(data_servico, data_ult_parto) -> int | None:
    if isinstance(data_servico, date) and isinstance(data_ult_parto, date) and data_servico >= data_ult_parto:
        return (data_servico - data_ult_parto).days
    return None


def analisar_servicos(servicos: list[dict]) -> list[dict]:
    """Achata os serviços para análise. Um registro por serviço."""
    registros: list[dict] = []
    for s in servicos:
        ds = s.get("data_servico")
        diag = (s.get("diagnostico") or "").strip().upper() or None
        diagnosticado = diag in ("POSITIVO", "NEGATIVO")
        ano = ds.year if isinstance(ds, date) else None
        mes = f"{ds.year}-{ds.month:02d}" if isinstance(ds, date) else None

        registros.append({
            "numero": s.get("numero_matriz"),
            "raca": s.get("raca_matriz") or "(sem raça)",
            "categoria": s.get("categoria") or "(sem categoria)",
            "ordem_parto": s.get("ordem_parto"),
            "ordem_tentativa": s.get("ordem_tentativa"),
            "tipo_servico": s.get("tipo_servico") or "(sem tipo)",
            "protocolo": s.get("protocolo") or "(sem protocolo)",
            "inseminador": s.get("reprodutor") or "(sem inseminador)",
            "ano": ano,
            "mes": mes,
            "del_servico": _del_servico(ds, s.get("data_ult_parto")),
            "diagnostico": diag,
            "diagnosticado": diagnosticado,
            "positivo": diag == "POSITIVO",
            "perda": bool(s.get("data_perda_prenhez")),
        })
    return registros
