"""
Centros de custo canônicos da fazenda. Os dados vindos do Ideagri usavam siglas
(PL, C|26, ARR); por decisão do usuário passam a ter um nome único e legível,
selecionável em todos os lugares. Este módulo centraliza o mapeamento para o
parser (import), o seed e a normalização única do banco.
"""
from __future__ import annotations

# Sigla antiga (sempre comparada em MAIÚSCULAS, sem espaços) → nome canônico.
MAPA_CENTRO_CUSTO: dict[str, str] = {
    "PL": "Pecuária Leiteira",
    "C|26": "Financiamento 2026",
    "ARR": "Arrendamento",
}

# Nomes canônicos que devem existir no cadastro (Configurações) e nos seletores.
CENTROS_CANONICOS: list[str] = list(dict.fromkeys(MAPA_CENTRO_CUSTO.values()))


def mapear_centro_custo(valor: str | None) -> str | None:
    """Converte a sigla antiga no nome canônico; devolve o valor original se
    não for uma das siglas conhecidas (comparação sem caixa/espaços)."""
    if not valor:
        return valor
    return MAPA_CENTRO_CUSTO.get(valor.strip().upper(), valor)
