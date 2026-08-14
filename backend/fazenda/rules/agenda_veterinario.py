"""
Agenda/roteiro do veterinário do serviço — classifica o rebanho fêmea em 11
listas para orientar a visita reprodutiva. Machos e bezerras nunca entram em
nenhuma lista.

Parâmetros de análise (todos editáveis em Configurações > Parâmetros — ver
`fazenda.rules.parametros`; documentados aqui para aparecerem também na tela):
  - Gate de aptidão (idade_apta_min_meses/peso_apta_min, padrão 15 meses e
    300 kg): só entram na lista "novilhas aptas vazias" (protocolos de
    novilha apta) — NÃO é mais um filtro geral que esconde a novilha das
    demais listas (toque, reconfirmação, pré-parto etc.); ver #364.
  - Verificar aptidão (idade_verificar_aptidao_meses/peso_verificar_aptidao_min,
    padrão 14 meses e 280 kg — limiar mais baixo, de "olho nela em breve"):
    novilha que nunca tenha sido inseminada nem coberta (nenhum registro de
    serviço).
  - Inseminada de 1 a 29 dias: aguardar 30 dias para o toque.
  - Inseminada de 30 a 59 dias: dar o toque; se não tiver toque nessa fase,
    fica marcada como "toque atrasado".
  - Inseminada com 60 dias ou mais: reconfirmar; se não tiver reconfirmação
    nessa fase, fica marcada como "atrasada para reconfirmação". A cobrança
    por reconfirmação para de valer assim que QUALQUER evento mais definitivo
    já tiver resolvido a gestação sozinho: a matriz pariu, foi seca de
    rotina (preparo pro parto) ou já entrou na janela de pré-parto — ver
    `fazenda.rules.perda_prenhez.retoque_esta_resolvido`. Pariu excluiu a
    matriz de "gestante" (ela não está mais prenha, precisa de novo
    serviço); os outros dois casos a mantêm como gestante confirmada, sem
    depender do 2º toque formal (#pedido do produtor, ago/2026).
  - Observação de cio (11ª lista, só quando usa_adesivo_deteccao_cio=true):
    inseminadas entre 15 e 28 dias — subconjunto de "inseminadas 1-29" — para
    acompanhar o adesivo de detecção de cio de repasse.
  - Vazias por diagnóstico (10ª lista): diagnóstico negativo no toque OU
    perda de prenhez confirmada na reconfirmação — precisam de novo serviço.
    Fica separada de "pendentes de classificação", que é só para dado
    faltante (peso não registrado, sem histórico de serviço).
"""
from __future__ import annotations

from datetime import date

from fazenda.rules.parametros import (
    dias_adesivo_cio_max,
    dias_adesivo_cio_min,
    gestacao_dias_referencia,
    idade_apta_min_meses,
    idade_verificar_aptidao_meses,
    peso_apta_min,
    peso_verificar_aptidao_min,
    pre_parto_max,
    pre_parto_min,
    usa_adesivo_deteccao_cio,
)
from fazenda.rules.perda_prenhez import (
    dentro_da_janela_pre_parto,
    pariu_depois_do_servico,
    secou_de_rotina_depois_do_servico,
)


def _categoria(animal: dict) -> str:
    texto = (animal.get("categoria_abrev") or animal.get("categoria_completa") or "").strip().lower()
    if "bezerr" in texto:
        return "bezerra"
    if "novilh" in texto:
        return "novilha"
    if "vaca" in texto:
        return "vaca"
    return ""


def _idade_meses(animal: dict, hoje: date) -> float | None:
    idade = animal.get("idade_meses")
    if idade is not None:
        return idade
    nasc = animal.get("data_nasc")
    if not nasc:
        return None
    if isinstance(nasc, str):
        nasc = date.fromisoformat(nasc)
    return round((hoje - nasc).days / 30.44, 1)


def classificar_rebanho(
    animais: list[dict],
    servico_por_animal: dict[str, dict],
    peso_por_animal: dict[str, float],
    hoje: date,
    ultimo_parto_por_animal: dict[str, date] | None = None,
    ultima_secagem_rotina_por_animal: dict[str, date] | None = None,
    grupos_pre_parto: set[str] | None = None,
) -> dict:
    listas: dict[str, list[dict]] = {
        "inseminadas_1_29": [], "inseminadas_30_59": [], "inseminadas_60_mais": [],
        "novilhas_aptas_vazias": [], "novilhas_gestantes": [], "verificar_aptidao": [],
        "verificar_pre_parto": [], "vacas_gestantes": [],
        "vazias_por_diagnostico": [], "pendentes_classificacao": [],
        "observacao_cio": [],
    }
    grupos_pre_parto = grupos_pre_parto or set()
    gestacao_dias = gestacao_dias_referencia()
    peso_apta = peso_apta_min()
    idade_apta = idade_apta_min_meses()
    peso_verificar = peso_verificar_aptidao_min()
    idade_verificar = idade_verificar_aptidao_meses()
    pre_parto_de = pre_parto_min()
    pre_parto_ate = pre_parto_max()
    usa_adesivo = usa_adesivo_deteccao_cio()
    adesivo_min = dias_adesivo_cio_min()
    adesivo_max = dias_adesivo_cio_max()

    for animal in animais:
        if animal.get("eh_semen") or animal.get("sexo") == "M":
            continue
        if animal.get("a_descartar"):
            continue  # marcada "A descartar" — fora de todas as ações reprodutivas
        categoria = _categoria(animal)
        if categoria == "bezerra":
            continue

        numero = animal["numero"]
        peso = peso_por_animal.get(numero)
        idade = _idade_meses(animal, hoje)
        servico = servico_por_animal.get(numero)

        if (
            categoria == "novilha"
            and peso is not None and peso >= peso_verificar
            and idade is not None and idade >= idade_verificar
            and servico is None
        ):
            listas["verificar_aptidao"].append({
                "numero_matriz": numero, "categoria": categoria, "peso": peso,
                "dias_inseminada": None, "data_servico": None,
                "tocada": False, "reconfirmada": False,
                "diagnostico": None, "diagnostico_reconfirmacao": None,
            })

        # Nota #364: o gate de idade/peso (idade_apta_min_meses/peso_apta_min)
        # NÃO é mais um filtro geral aqui — ele só passa a valer dentro do
        # bloco "novilha" abaixo, restrito à lista "novilhas_aptas_vazias".
        # As demais listas (toque, reconfirmação, pré-parto, vazias por
        # diagnóstico etc.) seguem valendo para qualquer novilha/vaca com
        # histórico de serviço, independente de idade/peso.

        data_servico = servico.get("data_servico") if servico else None
        dias_insem = (hoje - data_servico).days if data_servico else None
        tocada = bool(servico and servico.get("data_diagnostico"))
        reconfirmada = bool(servico and servico.get("data_reconfirmacao"))
        diag1 = (servico or {}).get("diagnostico")
        diag2 = (servico or {}).get("diagnostico_reconfirmacao")
        negativo_toque = tocada and diag1 == "NEGATIVO"
        # Novilha (nunca pariu) dispensa o 2º toque/reconfirmação nesta
        # fazenda — uma vez tocada positiva já é considerada confirmada; só
        # vaca passa pelo 2º exame aos 60+ dias (ver relatorios_gerenciais.py).
        eh_novilha = categoria == "novilha"
        # Perda de prenhez registrada neste serviço (manual ou automática por
        # reinseminação, ver fazenda.rules.perda_prenhez) — mesmo com o
        # diagnóstico ainda POSITIVO no registro, a gestação não é mais
        # vigente. Sem este filtro, uma vaca com a perda já registrada (mas
        # sem uma nova IA lançada ainda, então `servico` continua sendo este
        # mesmo POSITIVO) continuava "gestante confirmada" no roteiro do
        # veterinário.
        perda_registrada = bool((servico or {}).get("data_perda_prenhez"))
        diag_positivo_vigente = tocada and diag1 == "POSITIVO" and not perda_registrada

        # Eventos mais definitivos que o 2º toque — ver
        # fazenda.rules.perda_prenhez.retoque_esta_resolvido. Pariu resolve a
        # gestação SEM deixar a matriz "gestante" (ela precisa de novo
        # serviço agora); secar de rotina ou entrar na janela de pré-parto a
        # mantêm gestante, sem exigir reconfirmação formal.
        ultimo_parto = (ultimo_parto_por_animal or {}).get(numero)
        ultima_secagem_rotina = (ultima_secagem_rotina_por_animal or {}).get(numero)
        pariu_depois = diag_positivo_vigente and pariu_depois_do_servico(
            data_servico=data_servico, ultimo_parto=ultimo_parto,
        )
        secou_rotina_depois = diag_positivo_vigente and secou_de_rotina_depois_do_servico(
            data_servico=data_servico, ultima_secagem_rotina=ultima_secagem_rotina,
        )
        # Janela calculada (média configurável) OU já fisicamente no lote de
        # pré-parto (critério race-aware, ver lote_criterios.dias_para_parto)
        # — as duas podem divergir alguns dias para raças fora do Holandês,
        # então valem como alternativas, não como E lógico.
        entrou_pre_parto = diag_positivo_vigente and (
            dentro_da_janela_pre_parto(
                data_servico=data_servico, hoje=hoje,
                dias_gestacao_referencia=gestacao_dias, pre_parto_max_dias=pre_parto_ate,
            )
            or (animal.get("grupo_primario") or "") in grupos_pre_parto
        )

        gestante_confirmada = diag_positivo_vigente and not pariu_depois and (
            eh_novilha or (reconfirmada and diag2 == "POSITIVO") or entrou_pre_parto or secou_rotina_depois
        )
        perda_prenhez = perda_registrada or (reconfirmada and diag2 == "NEGATIVO")

        dpp = None
        if diag_positivo_vigente and not pariu_depois and data_servico:
            dpp = round(gestacao_dias - (hoje - data_servico).days)

        classificado = False
        base = {
            "numero_matriz": numero, "categoria": categoria, "peso": peso,
            "dias_inseminada": dias_insem, "data_servico": data_servico.isoformat() if data_servico else None,
            "tocada": tocada, "reconfirmada": reconfirmada,
            "diagnostico": diag1, "diagnostico_reconfirmacao": diag2,
        }

        em_aberto = (
            servico is not None and dias_insem is not None
            and not gestante_confirmada and not negativo_toque and not perda_prenhez and not pariu_depois
        )
        if em_aberto:
            if 1 <= dias_insem <= 29:
                listas["inseminadas_1_29"].append(base)
                classificado = True
                # Observação de cio (repasse): subconjunto de "1-29 dias", só
                # quando a fazenda usa adesivo de detecção de cio (parâmetro
                # usa_adesivo_deteccao_cio) — ver #365.
                if usa_adesivo and adesivo_min <= dias_insem <= adesivo_max:
                    listas["observacao_cio"].append(base)
            elif 30 <= dias_insem <= 59:
                listas["inseminadas_30_59"].append({**base, "atrasada": not tocada})
                classificado = True
            elif dias_insem >= 60:
                listas["inseminadas_60_mais"].append({**base, "atrasada": not reconfirmada})
                classificado = True

        if categoria == "novilha":
            vazia = not gestante_confirmada and not em_aberto
            # Gate de aptidão (#364): restrito a esta lista — idade/peso
            # mínimos NÃO afetam nenhuma outra lista acima/abaixo.
            apta = idade is not None and idade >= idade_apta and peso is not None and peso >= peso_apta
            if vazia and apta:
                listas["novilhas_aptas_vazias"].append(base)
                classificado = True
            if gestante_confirmada:
                listas["novilhas_gestantes"].append({**base, "dias_para_parto": dpp})
                classificado = True

        if gestante_confirmada and dpp is not None and pre_parto_de <= dpp <= pre_parto_ate:
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
            elif pariu_depois:
                motivo = f"{categoria.capitalize()} pariu — a gestação deste serviço já se resolveu, aguardando nova inseminação."
                listas["vazias_por_diagnostico"].append({**base, "motivo": motivo})
            elif not servico:
                motivo = f"{categoria.capitalize()} sem histórico de serviço nem diagnóstico de gestação registrado."
                listas["pendentes_classificacao"].append({**base, "motivo": motivo})
            else:
                motivo = "Dados insuficientes para classificar."
                listas["pendentes_classificacao"].append({**base, "motivo": motivo})

    return listas
