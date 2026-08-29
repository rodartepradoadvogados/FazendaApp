"""
Dose por peso vivo do Protocolo Sanitário (onda "Protocolo à Mostra").

===========================================================================
ADR — por que isto não existia antes, e por que agora é campo estruturado

Até esta onda, "2 ml / 15kg PV" era só TEXTO dentro de
`ProtocoloSanitarioEtapa.unidade` — o "2" ficava em `dosagem` (um float
solto) e "/ 15kg PV" ficava colado no texto da unidade. Nenhuma tela ou
regra jamais separou os dois números, e por isso nenhuma jamais multiplicou
a dose pelo peso do animal: a fórmula era só decoração. A prova concreta é
que os dois cadastros do mesmo princípio ativo divergiam sem ninguém notar
— o catálogo de bula (`MedicamentoComercial`) tem Banamine a 45 kg, o
protocolo sanitário "Pneumonia — Protocolo A" tem o mesmo Banamine a 40 kg.

Este módulo separa os dois números em campos próprios
(`ProtocoloSanitarioEtapa.modo_dose` + `dose_referencia_kg`, mesmo par de
nomes de `MedicamentoComercial.dose_base`/`dose_referencia_kg` — mesmo
conceito, mesmo vocabulário) e fornece o cálculo que nunca existiu:
dose = dosagem_por_referencia × (peso_do_animal / peso_de_referencia).
===========================================================================
"""
from __future__ import annotations

import re

MODO_FIXA = "fixa"
MODO_POR_PESO = "por_peso"
MODOS_DOSE_VALIDOS: tuple[str, ...] = (MODO_FIXA, MODO_POR_PESO)

# Casa "ml / 15kg pv", "ML/15 KG PV", "ml/15kg", "mL / 45 Kg P.V." — a grafia
# do CSV/cadastro legado nunca foi consistente. Grupo 1 = unidade (o que
# sobra antes da barra); grupo 2 = o número de kg de referência.
_RE_POR_PESO = re.compile(
    r"^\s*([a-zA-ZµμΜ%]+)\s*/\s*([\d]+(?:[.,]\d+)?)\s*kg\b.*$", re.IGNORECASE
)


def interpretar_unidade_legada(unidade: str | None) -> tuple[str, str | None, float | None]:
    """Lê o texto livre de `unidade` como ele existe no cadastro legado e
    devolve `(modo_dose, unidade_limpa, dose_referencia_kg)`.

    "ml / 15kg PV" -> ("por_peso", "ml", 15.0) — a dose (o "2" de "2 ml/15kg")
    já está correta em `dosagem`, não precisa mudar; só a referência de peso
    é que estava escondida no texto.

    "ml" (sem "/ NNkg") -> ("fixa", "ml", None) — não há o que separar,
    o texto já era só a unidade de medida.

    Nunca adivinha: texto que não casa o padrão volta como está, em modo
    "fixa" — errar para "não calculado" é sempre mais seguro que inventar
    uma referência de peso que não estava escrita."""
    if not unidade:
        return (MODO_FIXA, unidade, None)
    m = _RE_POR_PESO.match(unidade.strip())
    if not m:
        return (MODO_FIXA, unidade.strip(), None)
    unidade_limpa = m.group(1).strip()
    referencia = float(m.group(2).replace(",", "."))
    if referencia <= 0:
        return (MODO_FIXA, unidade.strip(), None)
    return (MODO_POR_PESO, unidade_limpa, referencia)


def calcular_dose(dosagem: float, dose_referencia_kg: float, peso_animal_kg: float) -> float:
    """dose = dosagem × (peso do animal / peso de referência).

    Ex.: Resflor é "2 mL a cada 15 kg" (dosagem=2, dose_referencia_kg=15);
    um animal de 640 kg recebe 2 × (640/15) = 85,33 mL. Arredondado a 1 casa
    — dose de medicamento injetável não se mede com mais precisão que isso
    numa seringa de campo."""
    if dose_referencia_kg <= 0:
        raise ValueError("dose_referencia_kg precisa ser positivo — não há como dividir por ele")
    return round(dosagem * (peso_animal_kg / dose_referencia_kg), 1)


def formula_legivel(dosagem: float, unidade: str, dose_referencia_kg: float) -> str:
    """"2 mL a cada 15 kg PV" — a fórmula sempre exibida ao lado do número
    calculado, nunca escondida atrás dele (ver o card "Usar último peso" no
    plano de UI): quem está aplicando o medicamento tem que conseguir
    conferir a conta, não só confiar nela."""
    dosagem_fmt = f"{dosagem:g}"
    referencia_fmt = f"{dose_referencia_kg:g}"
    return f"{dosagem_fmt} {unidade} a cada {referencia_fmt} kg PV"
