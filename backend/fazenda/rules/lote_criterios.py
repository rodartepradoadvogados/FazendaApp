"""
Critérios de seleção de animais por lote — cumulativos (E lógico). Usados na
prévia de "quantos animais atendem" no cadastro do lote e, na sequência, nas
sugestões automáticas de movimentação entre lotes.

Duas suposições documentadas (não há campo explícito no cadastro para isso):
  - "Em tratamento": animal com aplicação de sanidade nos últimos
    EM_TRATAMENTO_DIAS dias (janela de tratamento/observação ainda em curso).
  - Gestação: duração dada pela faixa editável gestacao_dias_min/max (ver
    `fazenda.rules.parametros`) — usa o ponto médio da faixa para estimar
    "dias para o parto" a partir da data do serviço com diagnóstico positivo.
  - "Pré-parto" (flag simples): gestante com pre_parto_max dias ou menos para
    o parto estimado (mesmo teto usado na janela de pré-parto da agenda do
    veterinário — ver `fazenda.rules.parametros.pre_parto_max`).
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.parametros import gestacao_dias_referencia, pre_parto_max

EM_TRATAMENTO_DIAS = 15


def _categoria_normalizada(animal: dict) -> str:
    texto = (animal.get("categoria_abrev") or animal.get("categoria_completa") or "").strip().lower()
    if "bezerr" in texto:
        return "bezerra"
    if "novilh" in texto:
        return "novilha"
    if "vaca" in texto:
        return "vaca"
    return ""


def _ultimo_servico_positivo(numero: str, servicos_por_animal: dict[str, list[dict]]) -> dict | None:
    servicos = servicos_por_animal.get(numero, [])
    positivos = [s for s in servicos if (s.get("diagnostico") or "").strip().upper() == "POSITIVO" and s.get("data_servico")]
    if not positivos:
        return None
    return max(positivos, key=lambda s: s["data_servico"])


def dias_para_parto(numero: str, servicos_por_animal: dict[str, list[dict]], hoje: date) -> int | None:
    servico = _ultimo_servico_positivo(numero, servicos_por_animal)
    if not servico:
        return None
    dias_gestacao = (hoje - servico["data_servico"]).days
    return round(gestacao_dias_referencia() - dias_gestacao)


def esta_em_tratamento(numero: str, sanidades_por_animal: dict[str, list[dict]], hoje: date) -> bool:
    limite = hoje - timedelta(days=EM_TRATAMENTO_DIAS)
    aplicacoes = sanidades_por_animal.get(numero, [])
    return any(a.get("data_aplicacao") and a["data_aplicacao"] >= limite for a in aplicacoes)


def foi_inseminada(numero: str, servicos_por_animal: dict[str, list[dict]]) -> bool:
    return bool(servicos_por_animal.get(numero))


def animal_atende_criterios(
    lote,
    animal: dict,
    hoje: date,
    peso_por_animal: dict[str, float],
    servicos_por_animal: dict[str, list[dict]],
    sanidades_por_animal: dict[str, list[dict]],
) -> bool:
    """Aplica, em E lógico, todos os critérios definidos no `lote` (campos None = não filtra)."""
    numero = animal["numero"]
    categoria = _categoria_normalizada(animal)

    if lote.status_lactacao:
        cat_completa = (animal.get("categoria_completa") or "").lower()
        if lote.status_lactacao == "lactacao" and "lact" not in cat_completa:
            return False
        if lote.status_lactacao == "seca" and "seca" not in cat_completa:
            return False

    if lote.categorias:
        alvo = {c.strip() for c in lote.categorias.split(",") if c.strip()}
        if categoria not in alvo:
            return False

    dpp = dias_para_parto(numero, servicos_por_animal, hoje)

    if lote.pre_parto:
        if dpp is None or dpp > pre_parto_max() or dpp < 0:
            return False

    peso = peso_por_animal.get(numero)
    if lote.peso_min is not None and (peso is None or peso < lote.peso_min):
        return False
    if lote.peso_max is not None and (peso is None or peso > lote.peso_max):
        return False

    producao = animal.get("ult_cl_kg")
    if lote.producao_min is not None and (producao is None or producao < lote.producao_min):
        return False
    if lote.producao_max is not None and (producao is None or producao > lote.producao_max):
        return False

    del_dias = animal.get("del_dias")
    if lote.del_min is not None and (del_dias is None or del_dias < lote.del_min):
        return False
    if lote.del_max is not None and (del_dias is None or del_dias > lote.del_max):
        return False

    if lote.dias_para_parto_min is not None and (dpp is None or dpp < lote.dias_para_parto_min):
        return False
    if lote.dias_para_parto_max is not None and (dpp is None or dpp > lote.dias_para_parto_max):
        return False

    if lote.em_tratamento and not esta_em_tratamento(numero, sanidades_por_animal, hoje):
        return False

    idade_dias = (hoje - animal["data_nasc"]).days if animal.get("data_nasc") else None
    if lote.idade_dias_min is not None and (idade_dias is None or idade_dias < lote.idade_dias_min):
        return False
    if lote.idade_dias_max is not None and (idade_dias is None or idade_dias > lote.idade_dias_max):
        return False

    gestante = (animal.get("sit_rep") or "") == "Ges." or (animal.get("diagnostico") or "").strip().upper() == "POSITIVO"

    if lote.novilhas_inseminadas:
        if categoria != "novilha" or not foi_inseminada(numero, servicos_por_animal) or gestante:
            return False

    if lote.novilhas_gestantes:
        if categoria != "novilha" or not gestante:
            return False

    return True


# Campos que definem um critério de fato — um lote sem NENHUM desses
# preenchido "atende" qualquer animal (não filtra nada), então não entra na
# sugestão automática de movimentação (evitaria sugerir o rebanho inteiro
# para um lote sem critério nenhum configurado).
_CAMPOS_CRITERIO = [
    "status_lactacao", "categorias", "pre_parto", "peso_min", "peso_max",
    "del_min", "del_max", "producao_min", "producao_max",
    "dias_para_parto_min", "dias_para_parto_max", "em_tratamento",
    "idade_dias_min", "idade_dias_max", "novilhas_inseminadas", "novilhas_gestantes",
]


def lote_tem_criterio(lote) -> bool:
    return any(getattr(lote, campo, None) for campo in _CAMPOS_CRITERIO)


def _motivos_atendimento(
    lote,
    animal: dict,
    hoje: date,
    peso_por_animal: dict[str, float],
    servicos_por_animal: dict[str, list[dict]],
    sanidades_por_animal: dict[str, list[dict]],
) -> list[str]:
    """Descreve, em texto, os critérios do `lote` que o animal atende — chamado só
    depois que `animal_atende_criterios` já confirmou o atendimento, então cada
    critério preenchido abaixo necessariamente já passou."""
    numero = animal["numero"]
    categoria = _categoria_normalizada(animal)
    dpp = dias_para_parto(numero, servicos_por_animal, hoje)
    motivos = []

    if lote.status_lactacao:
        motivos.append("Em lactação" if lote.status_lactacao == "lactacao" else "Seca")

    if lote.categorias and categoria:
        motivos.append(f"Categoria: {categoria}")

    if lote.pre_parto and dpp is not None:
        motivos.append(f"Pré-parto: faltam {dpp} dia(s) para o parto")

    peso = peso_por_animal.get(numero)
    if (lote.peso_min is not None or lote.peso_max is not None) and peso is not None:
        motivos.append(f"Peso: {peso:g} kg")

    producao = animal.get("ult_cl_kg")
    if (lote.producao_min is not None or lote.producao_max is not None) and producao is not None:
        motivos.append(f"Produção: {producao:g} kg/dia")

    del_dias = animal.get("del_dias")
    if (lote.del_min is not None or lote.del_max is not None) and del_dias is not None:
        motivos.append(f"DEL: {del_dias} dia(s)")

    if (lote.dias_para_parto_min is not None or lote.dias_para_parto_max is not None) and dpp is not None:
        motivos.append(f"Dias para o parto: {dpp}")

    if lote.em_tratamento:
        motivos.append("Em tratamento")

    idade_dias = (hoje - animal["data_nasc"]).days if animal.get("data_nasc") else None
    if (lote.idade_dias_min is not None or lote.idade_dias_max is not None) and idade_dias is not None:
        motivos.append(f"Idade: {idade_dias} dia(s)")

    gestante = (animal.get("sit_rep") or "") == "Ges." or (animal.get("diagnostico") or "").strip().upper() == "POSITIVO"
    if lote.novilhas_inseminadas:
        motivos.append("Novilha inseminada (não gestante)")
    if lote.novilhas_gestantes:
        motivos.append("Novilha gestante")

    return motivos


def sugerir_movimentacoes(
    lotes: list,
    animais: list[dict],
    hoje: date,
    peso_por_animal: dict[str, float],
    servicos_por_animal: dict[str, list[dict]],
    sanidades_por_animal: dict[str, list[dict]],
) -> list[dict]:
    """
    Para cada animal ativo, verifica a quais lotes (com critério configurado)
    ele atende. Se o lote atual dele não estiver entre os que ele atende,
    mas ele atender a algum outro, sugere a troca. Animal que não atende a
    nenhum lote com critério (dado insuficiente ou fora de toda faixa) não
    gera sugestão — não há para onde mandar.
    """
    lotes_com_criterio = [l for l in lotes if lote_tem_criterio(l)]
    sugestoes = []
    for animal in animais:
        numero = animal["numero"]
        grupo = animal.get("grupo_primario") or ""
        codigo_atual = grupo[:2] if len(grupo) >= 2 and grupo[:2].isdigit() else None

        atende = [
            l for l in lotes_com_criterio
            if animal_atende_criterios(l, animal, hoje, peso_por_animal, servicos_por_animal, sanidades_por_animal)
        ]
        if not atende:
            continue
        if codigo_atual in {l.codigo for l in atende}:
            continue

        lotes_sugeridos = []
        motivos_combinados: list[str] = []
        for l in atende:
            motivos_lote = _motivos_atendimento(l, animal, hoje, peso_por_animal, servicos_por_animal, sanidades_por_animal)
            lotes_sugeridos.append({
                "codigo": l.codigo, "nome": l.nome, "rotulo": f"{l.codigo} - {l.nome}",
                "motivo": "; ".join(motivos_lote) or None,
            })
            for m in motivos_lote:
                rotulado = f"{l.codigo} - {m}" if len(atende) > 1 else m
                if rotulado not in motivos_combinados:
                    motivos_combinados.append(rotulado)

        sugestoes.append({
            "numero_matriz": numero,
            "lote_atual": grupo or None,
            "lotes_sugeridos": lotes_sugeridos,
            "motivo": "; ".join(motivos_combinados) or None,
        })
    return sugestoes
