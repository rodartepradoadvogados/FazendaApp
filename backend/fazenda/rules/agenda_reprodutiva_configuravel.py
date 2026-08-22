"""
Motor de filtro dos cards configuráveis da Agenda Reprodutiva.

Troca os cards fixos de `agenda_veterinario.classificar_rebanho` (exceto
"Vazias por diagnóstico" e "Pendentes de classificação", que continuam à
parte — não são situação reprodutiva, ver o módulo citado) por cards que o
usuário monta ao vivo, com 4 eixos:

  1. categoria       — "vaca" | "novilha" | "todas"
  2. lotes           — lista de códigos/nomes de lote; vazia = todos
  3. situacao        — "pev" | "inseminada" | "gestante" | "vazia" |
                        "vazia_atrasada" | "a_descartar"
  4. sub-filtro       — depende da situação:
       pev/inseminada/gestante: `periodos` (lista de (de, ate) em dias —
         OR entre eles; vazia = sem restrição de período, mostra todos da
         situação). O eixo do dia varia: PEV e vazia usam dias desde o
         parto (`del_dias`), inseminada usa dias desde o serviço
         (`dias_desde_servico`), gestante usa dias de gestação
         (`dias_gestacao`).
       vazia: `somente_atrasadas`/`exceto_atrasadas` (no máximo um marcado;
         nenhum = todas as vazias, atrasadas ou não).
       vazia_atrasada: atalho == vazia + somente_atrasadas (sem sub-filtro
         próprio).
       a_descartar: sem sub-filtro — puxa só `Animal.a_descartar`.

Função pura: recebe os animais já achatados em dict e o estado ao vivo já
calculado (`estado_reprodutivo.estados_ao_vivo`) — não abre Session. Quem
monta os dois dicts é o endpoint (`routers/reproducao.py`), do mesmo jeito
que `agenda_veterinario.classificar_rebanho` já faz.
"""
from __future__ import annotations

from typing import Any

from fazenda.rules.estado_reprodutivo import APTA, ATRASADA, GESTANTE, INSEMINADA, PEV

SITUACOES = ("pev", "inseminada", "gestante", "vazia", "vazia_atrasada", "a_descartar")

# Situações que casam com o estado ao vivo "vazia" (livre para novo serviço) —
# mesma convenção de recria._situacao_reprodutiva_3: APTA e ATRASADA são as
# duas faces de "vazia", a atrasada é o refinamento mais específico.
_ESTADOS_VAZIA = (APTA, ATRASADA)


def _categoria(animal: dict) -> str:
    """Mesma lógica de `agenda_veterinario._categoria`/
    `lote_criterios._categoria_normalizada` (já duplicada duas vezes no
    repo, sempre sobre o texto congelado de categoria) — replicada aqui em
    vez de importar um símbolo privado de outro módulo de regra."""
    texto = (animal.get("categoria_abrev") or animal.get("categoria_completa") or "").strip().lower()
    if "bezerr" in texto:
        return "bezerra"
    if "novilh" in texto:
        return "novilha"
    if "vaca" in texto:
        return "vaca"
    return ""


def dentro_de_algum_periodo(dias: int | None, periodos: list[tuple[int, int]]) -> bool:
    """OR entre os períodos do mesmo eixo. Lista vazia = sem restrição
    (sempre casa) — é o que permite "situação = PEV" sozinha, sem nenhum
    período manual, continuar mostrando todo mundo em PEV."""
    if not periodos:
        return True
    if dias is None:
        return False
    return any(de <= dias <= ate for de, ate in periodos)


def _casa_situacao(
    situacao: str, estado: dict,
    periodos: list[tuple[int, int]], somente_atrasadas: bool, exceto_atrasadas: bool,
) -> bool:
    estado_vivo = estado.get("estado")
    if situacao == "pev":
        return estado_vivo == PEV and dentro_de_algum_periodo(estado.get("del_dias"), periodos)
    if situacao == "inseminada":
        return estado_vivo == INSEMINADA and dentro_de_algum_periodo(estado.get("dias_desde_servico"), periodos)
    if situacao == "gestante":
        return estado_vivo == GESTANTE and dentro_de_algum_periodo(estado.get("dias_gestacao"), periodos)
    if situacao == "vazia":
        if estado_vivo not in _ESTADOS_VAZIA:
            return False
        if somente_atrasadas and estado_vivo != ATRASADA:
            return False
        if exceto_atrasadas and estado_vivo == ATRASADA:
            return False
        return True
    if situacao == "vazia_atrasada":
        return estado_vivo == ATRASADA
    return False  # "a_descartar" é tratado à parte em avaliar_card (não usa estado ao vivo)


def avaliar_card(
    *,
    categoria: str,
    lotes: list[str],
    situacao: str,
    periodos: list[tuple[int, int]],
    somente_atrasadas: bool,
    exceto_atrasadas: bool,
    animais: list[dict],
    estados: dict[str, dict],
) -> list[dict]:
    """Devolve os animais (dict original + o estado ao vivo anexado) que
    atendem à combinação dos 4 eixos. `animais` traz pelo menos `numero`,
    `categoria_abrev`/`categoria_completa`, `grupo_primario` (lote atual) e
    `a_descartar`. `estados` é `estado_reprodutivo.estados_ao_vivo(...)`."""
    lotes_normalizados = {loc.strip().lower() for loc in lotes if loc and loc.strip()}
    resultado: list[dict] = []
    for animal in animais:
        numero = animal.get("numero")
        if not numero:
            continue
        cat = _categoria(animal)
        if cat == "bezerra":
            continue
        if categoria != "todas" and cat != categoria:
            continue
        if lotes_normalizados:
            lote_atual = (animal.get("grupo_primario") or "").strip().lower()
            if lote_atual not in lotes_normalizados:
                continue

        if situacao == "a_descartar":
            if not animal.get("a_descartar"):
                continue
            resultado.append({**animal, "estado": None, "categoria_normalizada": cat})
            continue

        # Fora de "a_descartar", a própria marcação exclui o animal de
        # qualquer situação reprodutiva — mesma regra de
        # `agenda_veterinario.classificar_rebanho` (linha "marcada 'A
        # descartar' — fora de todas as ações reprodutivas").
        if animal.get("a_descartar"):
            continue

        estado = estados.get(numero)
        if not estado:
            continue
        if not _casa_situacao(
            situacao, estado, periodos, somente_atrasadas, exceto_atrasadas,
        ):
            continue
        resultado.append({**animal, **estado, "categoria_normalizada": cat})
    return resultado
