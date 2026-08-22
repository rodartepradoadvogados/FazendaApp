"""
Quadro "por parto" da Ficha do Animal — o resumo que se quer ver "se fosse
comprar este animal": para cada parto (lactação), produção total, dias em
lactação, média diária, uma projeção de 305 dias, tentativas de emprenhar e
o DEL em que engravidou de novo.

Cálculo de produção — hoje só existem controles leiteiros pontuais (lançados
manualmente, poucos por lactação), não a ordenha dia a dia (que só chega
quando a importação diária via API de ordenha — DeLaval/GEA/GMZ — estiver no
ar). Enquanto isso:
  - `producao_media_dia_kg` = SOMA dos controles DAQUELA lactação ÷ QUANTIDADE
    de controles daquela lactação (não é dividido pelos dias em lactação —
    isso subestimaria a média sempre que há menos controles do que dias).
  - `producao_total_kg` = média/dia × dias em lactação (DEL atual, se a
    lactação ainda está aberta; ou o DEL final da lactação, se já encerrou).
    É uma ESTIMATIVA a partir da média real — não a soma bruta dos controles
    lançados — porque poucos controles pontuais não representam a produção
    real de todos os dias.
  - `producao_305_dias_kg` = média/dia × 305 (projeção para uma lactação
    padrão), sempre — não uma soma real mesmo quando a lactação já passou de
    305 dias, pelo mesmo motivo acima.

Fora daqui de propósito: "produção do equivalente maduro" (item 6 do pedido
original) fica de fora por ora — depende da reconstrução de
`ControleLeiteiro.ordem_parto`, uma iniciativa em andamento à parte (ver
`scripts/reconstruir_ordem_parto.py` e o card de Curva de lactação/EM), e
implementar um segundo cálculo em paralelo aqui criaria duas fontes de
verdade divergentes assim que aquela iniciativa for concluída.
"""
from __future__ import annotations

from datetime import date

DIAS_LACTACAO_PADRAO = 305


def resumo_por_parto(
    partos: list[dict], controles: list[dict], secagens: list[dict], servicos: list[dict],
    *, hoje: date | None = None,
) -> list[dict]:
    """Um dict por parto do animal (mais antigo primeiro — mesma ordem de
    `partos`). Cada `dict` de entrada precisa ter as datas já como `date`
    (não string) — `partos`: `data_parto`; `controles`: `data_controle`,
    `producao_kg`; `secagens`: `data_secagem`; `servicos`: `data_servico`,
    `diagnostico`, `ordem_tentativa`.
    """
    hoje = hoje or date.today()
    n = len(partos)
    datas_secagem = sorted(s["data_secagem"] for s in secagens if s.get("data_secagem"))

    saida: list[dict] = []
    for i, p in enumerate(partos):
        inicio = p.get("data_parto")
        if not isinstance(inicio, date):
            continue

        # Fim da lactação: o próximo parto encerra de vez; sem próximo parto,
        # uma secagem registrada depois do início encerra também; sem nenhum
        # dos dois, a lactação ainda está em andamento (fim = hoje).
        fim = partos[i + 1]["data_parto"] if i + 1 < n and isinstance(partos[i + 1].get("data_parto"), date) else None
        encerrada = fim is not None
        if fim is None:
            secagem_da_janela = next((d for d in datas_secagem if d >= inicio), None)
            if secagem_da_janela:
                fim = secagem_da_janela
                encerrada = True
        fim_efetivo = fim or hoje
        dias_em_lactacao = (fim_efetivo - inicio).days

        controles_janela = [
            c for c in controles
            if isinstance(c.get("data_controle"), date) and inicio <= c["data_controle"] < fim_efetivo
            and c.get("producao_kg") is not None
        ]
        # Média/dia = média dos controles leiteiros DAQUELA lactação (soma dos
        # controles ÷ quantidade de controles) — NÃO soma dos controles ÷ dias
        # em lactação, que subestimaria a média sempre que há menos controles
        # pontuais do que dias corridos (ver docstring do módulo).
        producao_media_dia_kg = (
            round(sum(c["producao_kg"] for c in controles_janela) / len(controles_janela), 2)
            if controles_janela else None
        )
        # Produção total = média/dia × DEL (atual, se em aberto; final da
        # lactação, se encerrada) — uma estimativa a partir da média real, não
        # a soma bruta dos poucos controles lançados (ver docstring do módulo).
        producao_total_kg = (
            round(producao_media_dia_kg * dias_em_lactacao, 1) if producao_media_dia_kg is not None else None
        )
        # 305 dias = média/dia × 305 — sempre uma projeção, mesmo quando a
        # lactação já passou de 305 dias corridos (ver docstring do módulo).
        producao_305_dias_kg = (
            round(producao_media_dia_kg * DIAS_LACTACAO_PADRAO, 1) if producao_media_dia_kg is not None else None
        )
        producao_305_dias_estimada = True

        servicos_janela = sorted(
            (s for s in servicos if isinstance(s.get("data_servico"), date) and inicio <= s["data_servico"] < fim_efetivo),
            key=lambda s: s["data_servico"],
        )
        if servicos_janela:
            maior_ordem = max((s.get("ordem_tentativa") or 0) for s in servicos_janela)
            tentativas_emprenhar = maior_ordem if maior_ordem > 0 else len(servicos_janela)
        else:
            tentativas_emprenhar = None
        concepcao = next((s for s in servicos_janela if (s.get("diagnostico") or "").strip().upper() == "POSITIVO"), None)
        del_concepcao = (concepcao["data_servico"] - inicio).days if concepcao else None

        saida.append({
            "ordem_parto": i + 1,
            "data_parto": inicio,
            "lactacao_encerrada": encerrada,
            "dias_em_lactacao": dias_em_lactacao,
            "producao_total_kg": producao_total_kg,
            "producao_media_dia_kg": producao_media_dia_kg,
            "producao_305_dias_kg": producao_305_dias_kg,
            "producao_305_dias_estimada": producao_305_dias_estimada,
            "tentativas_emprenhar": tentativas_emprenhar,
            "del_concepcao": del_concepcao,
        })
    return saida
