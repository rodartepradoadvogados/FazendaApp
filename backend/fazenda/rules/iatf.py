"""
Regra IATF — Seleção de candidatas e cálculo de doses de hormônios.

Protocolo D0/D7/D9/D11:
  D0:  1 implante (Sincrogest ou CIDR) + 2ml Sincrodiol (Benzoato) + 2,5ml Sincroforte (Buserelina)
  D7:  2ml Estron (Cloprostenol)
  D9:  2ml Estron + 1ml SincroCP (Cipionato)
  D11: IA (Inseminação Artificial)

Candidatas:
  - sit_rep IN ('Vaz. apt.', 'Vaz. atr.') OU último diagnóstico == 'NEGATIVO'
  - NÃO devem estar prenhes (Ges.) nem em PEV
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Protocolo IATF — doses por animal por fase
PROTOCOLO_IATF = {
    "D0": {
        "implante": 1,          # Sincrogest OU CIDR (unidade)
        "sincrodiol_ml": 2.0,   # Benzoato de Estradiol
        "sincroforte_ml": 2.5,  # Buserelina
    },
    "D7": {
        "estron_ml": 2.0,       # Cloprostenol
    },
    "D9": {
        "estron_ml": 2.0,       # Cloprostenol
        "sincrocp_ml": 1.0,     # Cipionato de Estradiol
    },
    # D11: IA (não requer produto de estoque)
}

# Conversão: ml/unidade → doses por frasco (para checagem de estoque)
EMBALAGEM = {
    "sincrodiol_ml": 50.0,   # frasco 50ml
    "sincroforte_ml": 20.0,  # frasco 20ml
    "estron_ml": 60.0,       # frasco 60ml
    "sincrocp_ml": 50.0,     # frasco 50ml
}

SIT_REP_CANDIDATAS = frozenset(["Vaz. apt.", "Vaz. atr."])


@dataclass
class CandidataIATF:
    numero_matriz: str
    sit_rep: str
    del_dias: int | None
    motivo: str  # "vazia apta", "vazia em atraso", "diagnóstico negativo"


@dataclass
class NecessidadeHormonios:
    n_candidatas: int
    implantes: int
    sincrodiol_ml: float
    sincrodiol_frascos: float
    sincroforte_ml: float
    sincroforte_frascos: float
    estron_ml: float   # D7 + D9
    estron_frascos: float
    sincrocp_ml: float
    sincrocp_frascos: float


@dataclass
class ResultadoIATF:
    candidatas: list[CandidataIATF] = field(default_factory=list)
    necessidade: NecessidadeIATF | None = None  # calculado ao finalizar


def selecionar_candidatas_iatf(
    animais: list[dict],
) -> list[CandidataIATF]:
    """
    Seleciona candidatas ao protocolo IATF.

    Args:
        animais: Lista de dicts com campos:
                   numero_matriz, sit_rep, del_dias, diagnostico_ultimo

    Returns:
        Lista de CandidataIATF ordenada por número.
    """
    candidatas: list[CandidataIATF] = []

    for a in animais:
        sit_rep = (a.get("sit_rep") or "").strip()
        diag = (a.get("diagnostico_ultimo") or "").upper().strip()
        numero = a.get("numero_matriz", "")

        if sit_rep in SIT_REP_CANDIDATAS:
            motivo = "Vazia apta" if sit_rep == "Vaz. apt." else "Vazia em atraso"
            candidatas.append(
                CandidataIATF(
                    numero_matriz=numero,
                    sit_rep=sit_rep,
                    del_dias=a.get("del_dias"),
                    motivo=motivo,
                )
            )
        elif diag == "NEGATIVO" and sit_rep not in ("Ges.",):
            candidatas.append(
                CandidataIATF(
                    numero_matriz=numero,
                    sit_rep=sit_rep,
                    del_dias=a.get("del_dias"),
                    motivo="Diagnóstico negativo",
                )
            )

    return sorted(candidatas, key=lambda c: c.numero_matriz)


def calcular_necessidade_hormonios(n_candidatas: int) -> NecessidadeHormonios:
    """
    Calcula a necessidade total de hormônios para N candidatas ao protocolo completo.

    Args:
        n_candidatas: Número de animais a entrar no protocolo.

    Returns:
        NecessidadeHormonios com ml totais e frascos necessários.
    """
    n = n_candidatas
    implantes = n  # 1 por animal
    sincrodiol = n * PROTOCOLO_IATF["D0"]["sincrodiol_ml"]
    sincroforte = n * PROTOCOLO_IATF["D0"]["sincroforte_ml"]
    estron = n * (PROTOCOLO_IATF["D7"]["estron_ml"] + PROTOCOLO_IATF["D9"]["estron_ml"])
    sincrocp = n * PROTOCOLO_IATF["D9"]["sincrocp_ml"]

    def frascos(ml: float, emb: float) -> float:
        import math
        return math.ceil(ml / emb) if emb else 0

    return NecessidadeHormonios(
        n_candidatas=n,
        implantes=implantes,
        sincrodiol_ml=sincrodiol,
        sincrodiol_frascos=frascos(sincrodiol, EMBALAGEM["sincrodiol_ml"]),
        sincroforte_ml=sincroforte,
        sincroforte_frascos=frascos(sincroforte, EMBALAGEM["sincroforte_ml"]),
        estron_ml=estron,
        estron_frascos=frascos(estron, EMBALAGEM["estron_ml"]),
        sincrocp_ml=sincrocp,
        sincrocp_frascos=frascos(sincrocp, EMBALAGEM["sincrocp_ml"]),
    )


# Alias para uso externo
NecessidadeIATF = NecessidadeHormonios
