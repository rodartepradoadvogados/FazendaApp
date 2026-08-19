"""
Regra IATF — Seleção de candidatas e cálculo de doses de hormônios.

Protocolo D0/D7/D9/D11:
  D0:  1 implante (Sincrogest ou CIDR) + 2ml Sincrodiol (Benzoato) + 2,5ml Sincroforte (Buserelina)
  D7:  2ml Estron (Cloprostenol)
  D9:  2ml Estron + 1ml SincroCP (Cipionato)
  D11: IA (Inseminação Artificial)

Candidatas:
  - estado reprodutivo AO VIVO ∈ {APTA, ATRASADA}, avaliado numa data.

    Antes o critério era `sit_rep IN ('Vaz. apt.', 'Vaz. atr.')` ou último
    diagnóstico NEGATIVO — texto congelado do GERAL.csv do Ideagri, que só muda
    no próximo upload. Uma vaca que engravidou pelo app continuava sendo
    oferecida para protocolo. Além da defasagem, aquele critério tinha quatro
    furos que a matriz de exclusão de `estado_reprodutivo` fecha de graça:

      - não testava PEV: vaca com diagnóstico negativo DENTRO do PEV entrava;
      - não testava protocolo em andamento: vaca com D0 implantado hoje
        continuava na lista;
      - não testava inseminação em aberto: vaca já inseminada com `sit_rep`
        velho continuava na lista;
      - não testava aptidão de novilha: nulípara sem idade/peso entrava se o
        CSV dissesse "Vaz.".

    O quinto furo — animal marcado a descartar — é fechado por quem chama, via
    `programa_reprodutivo.estado_no_dia` (regra R1). `classificar_animal`
    sozinho não consulta esse campo.

  - NÃO usar `EstadoDia.apta` para isto. `ESTADOS_APTOS` inclui INSEMINADA e
    EM_PROTOCOLO, que contam no denominador da taxa de serviço mas não podem
    virar candidata a protocolo. O teste é sobre o estado, não sobre `apta`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fazenda.ordenacao import chave_numero
from fazenda.rules.estado_reprodutivo import APTA, ATRASADA, ROTULOS


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

# NÃO decide mais candidata — o critério agora é o estado ao vivo. A constante
# sobrevive porque tem um segundo dono independente:
# `indicadores._classificar_situacao_reprodutiva`, o caminho legado do painel de
# Situação Reprodutiva da Capa, que ainda lê `sit_rep` quando não há registros
# carregados. Esvaziá-la quebraria aquele painel.
SIT_REP_CANDIDATAS = frozenset(["Vaz. apt.", "Vaz. atr."])

# Estado ao vivo → o motivo que o produtor lê na tela. Mantém o vocabulário que
# ele já conhece das listas antigas.
MOTIVO_POR_ESTADO = {APTA: "Vazia apta", ATRASADA: "Vazia em atraso"}
MOTIVO_DG_NEGATIVO = "Diagnóstico negativo"

# Os dois únicos estados que podem entrar num protocolo. Ver o docstring do
# módulo sobre por que `ESTADOS_APTOS` não serve aqui.
ESTADOS_CANDIDATA = frozenset({APTA, ATRASADA})


@dataclass
class CandidataIATF:
    numero_matriz: str
    sit_rep: str  # informativo: o texto do CSV, que já não decide nada
    del_dias: int | None
    motivo: str  # "Vazia apta", "Vazia em atraso", "Diagnóstico negativo"
    estado: str = ""  # estado reprodutivo ao vivo que a tornou candidata
    estado_rotulo: str = ""  # o mesmo, em português, para a tela


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
    estados: dict[str, dict],
) -> list[CandidataIATF]:
    """Seleciona candidatas ao protocolo IATF pelo estado reprodutivo ao vivo.

    Args:
        animais: dicts com `numero_matriz` e, opcionalmente, `sit_rep` (só
            informativo — vai para a saída, não decide nada).
        estados: {numero -> dict de `classificar_animal`}, já filtrado pela
            regra R1 por quem chamou (ver `estado_no_dia`). Animal ausente do
            mapa não é candidato: quem não tem estado calculado é porque saiu
            do programa ou não pôde ser classificado.

    O `del_dias` vem do estado calculado, não do `Animal.del_dias` congelado.

    Returns:
        Lista de CandidataIATF ordenada por número.
    """
    candidatas: list[CandidataIATF] = []

    for a in animais:
        numero = a.get("numero_matriz", "")
        info = estados.get(numero)
        if not info or info.get("estado") not in ESTADOS_CANDIDATA:
            continue

        estado = info["estado"]
        # "Diagnóstico negativo" deixou de ser um critério paralelo e virou um
        # refinamento do motivo: era daquele `elif` solto que vinha o furo de
        # listar vaca dentro do PEV. Quem tem DG negativo e já passou do PEV
        # cai em APTA/ATRASADA como qualquer outra.
        diag = (a.get("diagnostico_ultimo") or "").upper().strip()
        motivo = MOTIVO_DG_NEGATIVO if diag == "NEGATIVO" else MOTIVO_POR_ESTADO[estado]

        candidatas.append(
            CandidataIATF(
                numero_matriz=numero,
                sit_rep=(a.get("sit_rep") or "").strip(),
                del_dias=info.get("del_dias"),
                motivo=motivo,
                estado=estado,
                estado_rotulo=ROTULOS.get(estado, estado),
            )
        )

    return sorted(candidatas, key=lambda c: chave_numero(c.numero_matriz))


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
