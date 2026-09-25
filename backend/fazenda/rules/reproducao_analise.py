"""
Análise reprodutiva — transforma os serviços em registros achatados com as
dimensões usadas nos dashboards (concepção/perda por categoria, raça, ordem
de parto/tentativa, condição de IA, inseminador, mês, DEL no serviço).

O front consome esses registros e fatia/agrega conforme os filtros escolhidos.
Métrica central: TAXA DE CONCEPÇÃO = positivos / serviços com resultado
conhecido (regra R7 — ver `fazenda.rules.programa_reprodutivo`), não mais
"positivos / diagnosticados": serviço antigo que ninguém diagnosticou conta
como fracasso, não some da conta.
"""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta

from fazenda.rules.programa_reprodutivo import DIAS_RESULTADO_CONHECIDO_PADRAO, conta_em_taxa


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
        dpp = s.get("data_perda_prenhez")
        mes_perda = f"{dpp.year}-{dpp.month:02d}" if isinstance(dpp, date) else None
        dn = s.get("data_nasc_matriz")

        registros.append({
            "id": s.get("id"),
            "numero": s.get("numero_matriz"),
            "raca": s.get("raca_matriz") or "(sem raça)",
            "categoria": s.get("categoria") or "(sem categoria)",
            # Ano de nascimento da MATRIZ (não do serviço) — usado como filtro
            # da "prova ao vivo" (Estoque de Sêmen > Prova média), ver
            # `prova_ao_vivo_por_touro` abaixo.
            "ano_nascimento": dn.year if isinstance(dn, date) else None,
            "ordem_parto": s.get("ordem_parto"),
            "ordem_tentativa": s.get("ordem_tentativa"),
            "tipo_servico": s.get("tipo_servico") or "(sem tipo)",
            "protocolo": s.get("protocolo") or "(sem protocolo)",
            # 'reprodutor' na fonte é o touro/sêmen usado no serviço.
            "touro": s.get("reprodutor") or "(sem touro)",
            # Sexado/convencional/fazenda — gravado no serviço desde que essa
            # distinção passou a ser perguntada; None em registros antigos (o
            # chamador pode completar por nome via Estoque de Sêmen).
            "tipo_semen": s.get("tipo_semen"),
            "inseminador": s.get("inseminador") or "(sem inseminador)",
            "metodo_ia": _metodo_ia(s.get("tipo_servico"), s.get("protocolo")),
            "ano": ano,
            "mes": mes,
            "data": ds.isoformat() if isinstance(ds, date) else None,
            # Cru (não string), ao contrário de "data" acima — é o nome de
            # campo que `programa_reprodutivo.conta_em_taxa` espera (R7);
            # `agregar_mensal` reusa a regra em vez de reimplementar a janela
            # dos 28 dias.
            "data_servico": ds if isinstance(ds, date) else None,
            "del_servico": _del_servico(ds, s.get("data_ult_parto")),
            "diagnostico": diag,
            # Data do 1º toque (exame de gestação) — distinta de "data"/
            # "data_servico" (a IA/cobertura em si) e de "data_reconfirmacao"
            # (2º exame, abaixo). Faltava aqui: o Histórico > Reprodução >
            # Diagnósticos só mostrava a data do SERVIÇO, nunca a data em que o
            # diagnóstico foi de fato lançado (pedido do produtor, set/2026).
            "data_diagnostico": s["data_diagnostico"].isoformat() if isinstance(s.get("data_diagnostico"), date) else None,
            # "reinseminacao" = o sistema concluiu que não pegou porque veio
            # uma nova tentativa, não porque alguém tocou a vaca. A tela marca
            # essa diferença para o veterinário não achar que houve exame.
            "origem_diagnostico": s.get("origem_diagnostico"),
            # 2º exame (reconfirmação) — distinto do 1º toque acima. `retoque`
            # true e sem `diagnostico_reconfirmacao` = ainda aguardando o 2º
            # exame; com `diagnostico_reconfirmacao` = já reconfirmado
            # (positivo ou negativo). Sem isso, o Histórico nunca mostrava se
            # (e quando) a reconfirmação aconteceu.
            "retoque": bool(s.get("retoque")),
            "data_reconfirmacao": s["data_reconfirmacao"].isoformat() if isinstance(s.get("data_reconfirmacao"), date) else None,
            "diagnostico_reconfirmacao": s.get("diagnostico_reconfirmacao"),
            "diagnosticado": diagnosticado,
            "positivo": diag == "POSITIVO",
            "perda": bool(s.get("data_perda_prenhez")),
            "data_perda": dpp.isoformat() if isinstance(dpp, date) else None,
            "motivo_perda": s.get("motivo_perda_prenhez"),
            "mes_perda": mes_perda,
            "usuario_id": s.get("usuario_id"),
        })
    return registros


# ---------------------------------------------------------------------------
# Agregação mensal — alimenta o gráfico interativo configurável de Análise
# reprodutiva (cruzamento de métricas por mês/ano). Cada série é uma lista
# alinhada 1:1 com a lista de meses retornada.
# ---------------------------------------------------------------------------
def agregar_mensal(
    registros: list[dict], secagens: list[dict], controles: list[dict], *,
    hoje: date | None = None, dias_resultado: int = DIAS_RESULTADO_CONHECIDO_PADRAO,
) -> dict:
    hoje = hoje or date.today()
    meses: set[str] = set()
    por_mes_servico: dict[str, list[dict]] = defaultdict(list)
    for r in registros:
        if r["mes"]:
            por_mes_servico[r["mes"]].append(r)
            meses.add(r["mes"])
        if r["mes_perda"]:
            meses.add(r["mes_perda"])

    por_mes_secagem: dict[str, int] = defaultdict(int)
    for s in secagens:
        d = s.get("data_secagem")
        if isinstance(d, date):
            m = f"{d.year}-{d.month:02d}"
            por_mes_secagem[m] += 1
            meses.add(m)

    por_mes_producao: dict[str, list[float]] = defaultdict(list)
    for c in controles:
        d, kg = c.get("data_controle"), c.get("producao_kg")
        if isinstance(d, date) and kg is not None:
            m = f"{d.year}-{d.month:02d}"
            por_mes_producao[m].append(kg)
            meses.add(m)

    por_mes_perda: dict[str, int] = defaultdict(int)
    for r in registros:
        if r["mes_perda"]:
            por_mes_perda[r["mes_perda"]] += 1

    meses_ordenados = sorted(meses)

    def _por_mes(fn):
        return [fn(por_mes_servico.get(m, [])) for m in meses_ordenados]

    def _conta(pred):
        return _por_mes(lambda regs: sum(1 for r in regs if pred(r)))

    def _media(campo):
        def f(regs):
            vals = [r[campo] for r in regs if r.get(campo) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
        return _por_mes(f)

    # "Há IA posterior para este animal?" — mesma aproximação já usada em
    # `indicadores._repro_benchmark`: a existência de QUALQUER serviço mais
    # recente do mesmo animal, sem recortar por lactação. Esta camada só
    # enxerga serviços achatados (sem Parto), então não tem como reproduzir
    # `programa_reprodutivo.tem_reinseminacao_posterior` inteira — que exige o
    # perfil completo do animal para não confundir uma IA de lactação
    # seguinte com uma reinseminação da mesma tentativa. Na prática o efeito
    # de não recortar é pequeno: só adia por alguns dias, quando muito, a
    # entrada de um serviço já fadado ao fracasso — não muda a taxa final.
    ultimas_datas: dict[str, date] = {}
    for r in registros:
        n, d = r.get("numero"), r.get("data_servico")
        if n and d and (n not in ultimas_datas or d > ultimas_datas[n]):
            ultimas_datas[n] = d

    def _taxa_concepcao(regs):
        """R7 — só entra no denominador o serviço cujo desfecho já pode ser
        conhecido: 28 dias corridos (`dias_resultado`), DG lançado, perda de
        prenhez registrada, ou reinseminação posterior que prova a falha.
        Usa `conta_em_taxa`, a mesma porta de `_repro_benchmark` e dos ciclos
        de 21 dias — antes o denominador era só "diagnosticado", e o serviço
        antigo que ninguém diagnosticou simplesmente sumia da conta em vez de
        contar como fracasso.
        """
        contam = []
        for r in regs:
            d = r["data_servico"]
            if d is None:
                continue
            posterior = bool((ultima := ultimas_datas.get(r["numero"])) and ultima > d)
            servico = {"data_servico": d, "diagnostico": r["diagnostico"], "data_perda_prenhez": r["data_perda"]}
            if conta_em_taxa(servico, hoje, servico_posterior=posterior, dias=dias_resultado):
                contam.append(r)
        if not contam:
            return None
        pos = sum(1 for r in contam if r["positivo"])
        return round(100 * pos / len(contam), 1)

    def _delta(serie):
        if not serie:
            return []
        out = [None]
        for i in range(1, len(serie)):
            a, b = serie[i - 1], serie[i]
            out.append(round(b - a, 1) if a is not None and b is not None else None)
        return out

    del_medio = _media("del_servico")
    producao_leite = [
        round(sum(por_mes_producao[m]) / len(por_mes_producao[m]), 1) if por_mes_producao.get(m) else None
        for m in meses_ordenados
    ]

    series = {
        "num_servicos": _por_mes(len),
        "animais_inseminados": _conta(lambda r: r["tipo_servico"] != "Monta natural"),
        "num_ias": _conta(lambda r: r["metodo_ia"] in ("IA em cio natural", "IATF")),
        "num_montas_naturais": _conta(lambda r: r["metodo_ia"] == "Monta natural"),
        "num_coberturas": _conta(lambda r: any(p in r["tipo_servico"].lower() for p in ("cobertura", "monta"))),
        "num_ia_cio": _conta(lambda r: r["metodo_ia"] == "IA em cio natural"),
        "num_iatf": _conta(lambda r: r["metodo_ia"] == "IATF"),
        "qtd_positivos": _conta(lambda r: r["positivo"]),
        "qtd_negativos": _conta(lambda r: r["diagnosticado"] and not r["positivo"]),
        "animais_prenhes": _conta(lambda r: r["positivo"]),
        "taxa_concepcao": _por_mes(_taxa_concepcao),
        "perdas_prenhez": [por_mes_perda.get(m, 0) for m in meses_ordenados],
        "num_secagens": [por_mes_secagem.get(m, 0) for m in meses_ordenados],
        "del_medio": del_medio,
        "producao_leite": producao_leite,
    }
    series["variacao_del"] = _delta(del_medio)
    series["variacao_producao_leite"] = _delta(producao_leite)

    # Mesmo padrão de `ResultadoCiclo.janela_dg_completa`: um mês só está
    # "fechado" quando TODOS os seus serviços já passaram os `dias_resultado`
    # dias — na prática, quando o fim do mês + a janela já ficou no passado.
    # Sem isto, o mês corrente (quase sem diagnóstico ainda, por definição)
    # entra na série de concepção como se fosse um mês maduro, e quem compara
    # a série (`manual_fazenda._insights`) enxerga uma "queda" que é só falta
    # de tempo — não piora de manejo.
    def _mes_completo(m: str) -> bool:
        ano, mes = (int(x) for x in m.split("-"))
        fim_do_mes = date(ano, mes, monthrange(ano, mes)[1])
        return fim_do_mes + timedelta(days=dias_resultado) <= hoje

    janela_dg_completa = [_mes_completo(m) for m in meses_ordenados]

    return {"meses": meses_ordenados, "series": series, "janela_dg_completa": janela_dg_completa}
