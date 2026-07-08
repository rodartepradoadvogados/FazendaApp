"""
Agenda/roteiro do veterinário do serviço — classifica o rebanho fêmea em 10
listas para orientar a visita reprodutiva. Machos, bezerras e novilhas com
peso confirmado abaixo de 260 kg nunca entram em nenhuma lista.

Parâmetros de análise (documentados aqui para aparecerem também na tela):
  - Inseminada de 1 a 29 dias: aguardar 30 dias para o toque.
  - Inseminada de 30 a 59 dias: dar o toque; se não tiver toque nessa fase,
    fica marcada como "toque atrasado".
  - Inseminada com 60 dias ou mais: reconfirmar; se não tiver reconfirmação
    nessa fase, fica marcada como "atrasada para reconfirmação".
  - Vazias por diagnóstico (10ª lista): diagnóstico negativo no toque OU
    perda de prenhez confirmada na reconfirmação — precisam de novo serviço.
    Fica separada de "pendentes de classificação", que é só para dado
    faltante (peso não registrado, sem histórico de serviço).
"""
from __future__ import annotations

from datetime import date

from fazenda.rules.lote_criterios import GESTACAO_DIAS

PESO_APTA_MIN = 300.0
PESO_VERIFICAR_APTIDAO_MIN = 260.0
PRE_PARTO_MIN = 31
PRE_PARTO_MAX = 60


def _categoria(animal: dict) -> str:
    texto = (animal.get("categoria_abrev") or animal.get("categoria_completa") or "").strip().lower()
    if "bezerr" in texto:
        return "bezerra"
    if "novilh" in texto:
        return "novilha"
    if "vaca" in texto:
        return "vaca"
    return ""


def classificar_rebanho(
    animais: list[dict],
    servico_por_animal: dict[str, dict],
    peso_por_animal: dict[str, float],
    hoje: date,
) -> dict:
    listas: dict[str, list[dict]] = {
        "inseminadas_1_29": [], "inseminadas_30_59": [], "inseminadas_60_mais": [],
        "novilhas_aptas_vazias": [], "novilhas_gestantes": [], "verificar_aptidao": [],
        "verificar_pre_parto": [], "vacas_gestantes": [],
        "vazias_por_diagnostico": [], "pendentes_classificacao": [],
    }

    for animal in animais:
        if animal.get("eh_semen") or animal.get("sexo") == "M":
            continue
        categoria = _categoria(animal)
        if categoria == "bezerra":
            continue

        numero = animal["numero"]
        peso = peso_por_animal.get(numero)
        if categoria == "novilha" and peso is not None and peso < PESO_VERIFICAR_APTIDAO_MIN:
            continue  # abaixo de 260kg: nunca entra em nenhuma lista

        servico = servico_por_animal.get(numero)
        data_servico = servico.get("data_servico") if servico else None
        dias_insem = (hoje - data_servico).days if data_servico else None
        tocada = bool(servico and servico.get("data_diagnostico"))
        reconfirmada = bool(servico and servico.get("data_reconfirmacao"))
        diag1 = (servico or {}).get("diagnostico")
        diag2 = (servico or {}).get("diagnostico_reconfirmacao")
        negativo_toque = tocada and diag1 == "NEGATIVO"
        gestante_confirmada = tocada and diag1 == "POSITIVO" and reconfirmada and diag2 == "POSITIVO"
        perda_prenhez = reconfirmada and diag2 == "NEGATIVO"

        dpp = None
        if gestante_confirmada and data_servico:
            dpp = GESTACAO_DIAS - (hoje - data_servico).days

        classificado = False
        base = {
            "numero_matriz": numero, "categoria": categoria, "peso": peso,
            "dias_inseminada": dias_insem, "data_servico": data_servico.isoformat() if data_servico else None,
            "tocada": tocada, "reconfirmada": reconfirmada,
            "diagnostico": diag1, "diagnostico_reconfirmacao": diag2,
        }

        em_aberto = servico is not None and dias_insem is not None and not gestante_confirmada and not negativo_toque and not perda_prenhez
        if em_aberto:
            if 1 <= dias_insem <= 29:
                listas["inseminadas_1_29"].append(base)
                classificado = True
            elif 30 <= dias_insem <= 59:
                listas["inseminadas_30_59"].append({**base, "atrasada": not tocada})
                classificado = True
            elif dias_insem >= 60:
                listas["inseminadas_60_mais"].append({**base, "atrasada": not reconfirmada})
                classificado = True

        if categoria == "novilha":
            vazia = not gestante_confirmada and not em_aberto
            if vazia and peso is not None and peso >= PESO_APTA_MIN:
                listas["novilhas_aptas_vazias"].append(base)
                classificado = True
            if gestante_confirmada:
                listas["novilhas_gestantes"].append({**base, "dias_para_parto": dpp})
                classificado = True
            if vazia and peso is not None and PESO_VERIFICAR_APTIDAO_MIN <= peso < PESO_APTA_MIN:
                listas["verificar_aptidao"].append(base)
                classificado = True

        if gestante_confirmada and dpp is not None and PRE_PARTO_MIN <= dpp <= PRE_PARTO_MAX:
            listas["verificar_pre_parto"].append({**base, "dias_para_parto": dpp})
            classificado = True

        if categoria == "vaca" and gestante_confirmada:
            listas["vacas_gestantes"].append({**base, "dias_para_parto": dpp})
            classificado = True

        if not classificado:
            if negativo_toque:
                motivo = f"{categoria.capitalize()} com diagnóstico negativo no toque, aguardando novo serviço."
                listas["vazias_por_diagnostico"].append({**base, "motivo": motivo})
            elif perda_prenhez:
                motivo = "Perda de prenhez confirmada na reconfirmação, aguardando novo serviço."
                listas["vazias_por_diagnostico"].append({**base, "motivo": motivo})
            elif categoria == "novilha" and peso is None:
                motivo = "Novilha sem peso registrado — não é possível confirmar aptidão."
                listas["pendentes_classificacao"].append({**base, "motivo": motivo})
            elif not servico:
                motivo = f"{categoria.capitalize()} sem histórico de serviço nem diagnóstico de gestação registrado."
                listas["pendentes_classificacao"].append({**base, "motivo": motivo})
            else:
                motivo = "Dados insuficientes para classificar."
                listas["pendentes_classificacao"].append({**base, "motivo": motivo})

    return listas
