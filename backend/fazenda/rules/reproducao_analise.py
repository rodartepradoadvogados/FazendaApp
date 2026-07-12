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


def _metodo_ia(tipo_servico: str | None, protocolo: str | None) -> str:
    """
    Classifica como o serviço foi feito:
      - Inseminação artificial COM protocolo hormonal  -> 'IATF'
      - Inseminação artificial SEM protocolo (em cio)   -> 'IA em cio natural'
      - Cobertura/monta                                 -> 'Monta natural'
    """
    tipo = (tipo_servico or "").strip().lower()
    tem_protocolo = bool((protocolo or "").strip())
    if "insemin" in tipo or tipo in ("ia", "iatf"):
        return "IATF" if tem_protocolo else "IA em cio natural"
    if "cobertura" in tipo or "monta" in tipo:
        return "Monta natural"
    # Sem tipo declarado: infere pelo protocolo.
    return "IATF" if tem_protocolo else "(sem método)"


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
            # 'reprodutor' na fonte é o touro/sêmen usado no serviço.
            "touro": s.get("reprodutor") or "(sem touro)",
            "inseminador": s.get("inseminador") or "(sem inseminador)",
            "metodo_ia": _metodo_ia(s.get("tipo_servico"), s.get("protocolo")),
            "ano": ano,
            "mes": mes,
            "data": ds.isoformat() if isinstance(ds, date) else None,
            "del_servico": _del_servico(ds, s.get("data_ult_parto")),
            "diagnostico": diag,
            "diagnosticado": diagnosticado,
            "positivo": diag == "POSITIVO",
            "perda": bool(s.get("data_perda_prenhez")),
        })
    return registros
