"""
Indicadores zootécnicos, reprodutivos e produtivos do rebanho.

Funções puras: recebem listas de dicts (Animal, Servico, Parto — já em model_dump)
e devolvem um dicionário de indicadores. Sem acesso a banco, testáveis isoladamente.

Referências de negócio (Seção 5 do CONTEXTO_PROJETO_FAZENDA.md):
  - Lactação = grupos 01/02/03; Pré-parto = 04; Secas = 05.
  - Sit. rep.: Ges. (prenhe), Vaz.* (vazia), Ins. (inseminada).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fazenda.rules.gestation import calcular_parto_provavel
from fazenda.rules.iatf import SIT_REP_CANDIDATAS
from fazenda.rules.parametros import (
    BENCHMARK_METAS,
    data_corte_taxa_concepcao,
    gestacao_dias_min,
    gestacao_dias_referencia,
    peso_apta_min,
    pev_dias,
)

# Códigos de grupo (2 primeiros dígitos do grupo_primario).
GRUPOS_LACTACAO = {"01", "02", "03"}
GRUPO_PRE_PARTO = "04"
GRUPO_SECAS = "05"

def _concepcao_desde() -> date:
    """Taxa de concepção considerada sempre a partir desta data — editável em
    Configurações > Parâmetros (data_corte_taxa_concepcao). Função (não
    constante de módulo) para ler o valor atual do banco a cada chamada, sem
    depender da ordem de import x criação de tabelas no startup."""
    return data_corte_taxa_concepcao()


def _iep_minimo_dias() -> int:
    """Piso biológico do intervalo entre partos (IEP).
    Uma nova cria exige, no mínimo, a gestação (~9 meses) somada ao período de
    espera voluntária (PEV) até a matriz emprenhar de novo. Dois registros de
    parto mais próximos que isso são o mesmo evento (duplicidade na fonte) e
    não representam um intervalo real — são descartados para não distorcer a
    média. Ambos editáveis em Configurações > Parâmetros
    (gestacao_dias_min/pev_dias) — ~325 dias (~10,7 meses) por padrão."""
    return gestacao_dias_min() + pev_dias()


def _classificar_situacao_reprodutiva(sit_rep: Optional[str]) -> str:
    """Classifica o `Sit. rep.` bruto em um dos 4 grupos padrão do painel de
    Situação Reprodutiva (Capa): prenhes / inseminadas / pev / a_inseminar.
    Qualquer valor fora desse padrão (em branco, ou qualquer outro texto)
    cai em 'vazias' — mesmo balde usado para animais sem situação reprodutiva
    definida (ex.: machos, bezerras). 'A inseminar' reaproveita o mesmo
    critério de candidatas do IATF (SIT_REP_CANDIDATAS = Vaz. apt./Vaz. atr.)
    para não divergir a mesma regra de negócio em dois lugares."""
    sit = (sit_rep or "").strip()
    if sit == "Ges.":
        return "prenhes"
    if sit == "Ins.":
        return "inseminadas"
    if sit == "Vaz. pev":
        return "pev"
    if sit in SIT_REP_CANDIDATAS:
        return "a_inseminar"
    return "vazias"


def _codigo_grupo(grupo: Optional[str]) -> Optional[str]:
    """Extrai o código de 2 dígitos do início do grupo (ex.: '01 - NOV. ALTA' -> '01')."""
    if not grupo:
        return None
    g = grupo.strip()
    if len(g) >= 2 and g[:2].isdigit():
        return g[:2]
    return None


def _media(valores: list[float]) -> Optional[float]:
    vals = [v for v in valores if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _diag_upper(s: str | None) -> str:
    return (s or "").strip().upper()


def _no_periodo(s: dict, desde: date) -> bool:
    ds = s.get("data_servico")
    return isinstance(ds, date) and ds >= desde


def _del_serv(s: dict) -> Optional[float]:
    d = s.get("del_servico")
    if isinstance(d, (int, float)) and d >= 0:
        return float(d)
    ds, dp = s.get("data_servico"), s.get("data_ult_parto")
    if isinstance(ds, date) and isinstance(dp, date) and ds >= dp:
        return float((ds - dp).days)
    return None


def _iep_dias(partos: list[dict]) -> Optional[int]:
    iep_minimo = _iep_minimo_dias()
    por_matriz: dict[str, list[date]] = {}
    for p in partos:
        d = p.get("data_parto")
        m = p.get("numero_matriz")
        if d and m:
            por_matriz.setdefault(m, []).append(d)
    intervalos: list[int] = []
    for datas in por_matriz.values():
        distintos: list[date] = []
        for d in sorted(set(datas)):
            if not distintos or (d - distintos[-1]).days >= iep_minimo:
                distintos.append(d)
        for ant, atu in zip(distintos, distintos[1:]):
            intervalos.append((atu - ant).days)
    return round(sum(intervalos) / len(intervalos)) if intervalos else None


# Rótulo/unidade de cada indicador do benchmark reprodutivo.
_BENCH_LABELS: dict[str, tuple[str, str]] = {
    "taxa_servico": ("Taxa de serviço", "%"),
    "taxa_concepcao": ("Taxa de concepção", "%"),
    "taxa_prenhez_ciclo": ("Taxa de prenhez", "%"),
    "del_medio": ("DEL médio", "dias"),
    "taxa_perda_prenhez": ("Taxa de perda de prenhez", "%"),
    "perc_vacas_prenhas": ("% de fêmeas prenhas", "%"),
    "servicos_por_prenhez": ("Serviços por prenhez", ""),
    "del_1a_ia": ("DEL médio à 1ª IA", "dias"),
    "dias_abertos": ("Dias abertos", "dias"),
    "iep_meses": ("Intervalo entre partos (IEP)", "meses"),
}


def _repro_benchmark(animais: list[dict], servicos: list[dict], partos: list[dict], desde: date) -> list[dict]:
    """Painel de benchmark reprodutivo (Prenhez = Serviço × Concepção) para um
    subconjunto do rebanho — usado para 'todas', 'vaca' e 'novilha'."""
    prenhes = vazias = inseminadas = 0
    for a in animais:
        sit = (a.get("sit_rep") or "").strip()
        if sit == "Ges.":
            prenhes += 1
        elif sit.startswith("Vaz."):
            vazias += 1
        elif sit == "Ins.":
            inseminadas += 1
    aptas = prenhes + vazias + inseminadas
    total = len(animais)

    serv_periodo = [s for s in servicos if _no_periodo(s, desde)]
    pos = sum(1 for s in serv_periodo if _diag_upper(s.get("diagnostico")) == "POSITIVO")
    neg = sum(1 for s in serv_periodo if _diag_upper(s.get("diagnostico")) == "NEGATIVO")
    diag = pos + neg
    taxa_concepcao = round(100 * pos / diag, 1) if diag else None
    servidas = {s.get("numero_matriz") for s in serv_periodo if s.get("numero_matriz")}
    taxa_servico = round(100 * len(servidas) / aptas, 1) if aptas else None
    taxa_prenhez_ciclo = (
        round(taxa_servico * taxa_concepcao / 100, 1)
        if taxa_servico is not None and taxa_concepcao is not None else None
    )
    servicos_por_prenhez = round(len(serv_periodo) / pos, 1) if pos else None
    perdas = sum(1 for s in serv_periodo if s.get("data_perda_prenhez"))
    taxa_perda = round(100 * perdas / pos, 1) if pos else None
    perc_prenhas = round(100 * prenhes / total, 1) if total else None
    dias_abertos = _media([
        v for s in serv_periodo if _diag_upper(s.get("diagnostico")) == "POSITIVO"
        for v in [_del_serv(s)] if v is not None
    ])
    del_1a = _media([
        v for s in serv_periodo if s.get("ordem_tentativa") == 1
        for v in [_del_serv(s)] if v is not None
    ])
    del_medio = _media([
        float(a["del_dias"]) for a in animais
        if _codigo_grupo(a.get("grupo_primario")) in GRUPOS_LACTACAO and a.get("del_dias")
    ])
    iep_dias = _iep_dias(partos)
    iep_meses = round(iep_dias / 30.44, 1) if iep_dias else None

    valores = {
        "taxa_servico": taxa_servico, "taxa_concepcao": taxa_concepcao,
        "taxa_prenhez_ciclo": taxa_prenhez_ciclo, "del_medio": del_medio,
        "taxa_perda_prenhez": taxa_perda, "perc_vacas_prenhas": perc_prenhas,
        "servicos_por_prenhez": servicos_por_prenhez, "del_1a_ia": del_1a,
        "dias_abertos": dias_abertos, "iep_meses": iep_meses,
    }
    lista = []
    for chave, (label, unidade) in _BENCH_LABELS.items():
        m = BENCHMARK_METAS.get(chave, {})
        lista.append({
            "chave": chave, "label": label, "unidade": unidade,
            "valor": valores.get(chave), "meta": m.get("meta"),
            "media_pais": m.get("media_pais"), "maior_melhor": m.get("maior_melhor", True),
        })
    return lista


def _benchmark_categorias(
    animais: list[dict], servicos: list[dict], partos: list[dict], vacas_nums: set, desde: date,
) -> dict:
    """Benchmark separado por categoria: todas / vaca (já pariu) / novilha."""
    animais_vaca = [a for a in animais if a.get("numero") in vacas_nums]
    animais_novilha = [a for a in animais if a.get("numero") not in vacas_nums]
    serv_vaca = [s for s in servicos if (s.get("ordem_parto") or 0) >= 1]
    serv_novilha = [s for s in servicos if (s.get("ordem_parto") or 0) < 1]
    return {
        "todas": _repro_benchmark(animais, servicos, partos, desde),
        "vaca": _repro_benchmark(animais_vaca, serv_vaca, partos, desde),
        "novilha": _repro_benchmark(animais_novilha, serv_novilha, [], desde),
    }


DEL_APTA_MIN = 45  # vaca apta a novo serviço: dias mínimos após o último parto


def _reproducao_categorias(
    animais: list[dict],
    numeros_com_servico: set,
    peso_por_animal: dict[str, float],
    vacas_nums: set,
) -> dict:
    """Situação reprodutiva (prenhes/vazias/inseminadas/aptas) por categoria:
    todas / vaca (já pariu) / novilha.

    'Aptas' usa dois critérios diferentes conforme a categoria, porque
    "apta" tem sentido distinto para quem já pariu e para quem nunca pariu:
    - Vaca: DEL (dias desde o último parto) >= DEL_APTA_MIN e não está
      inseminada nem prenhe (sit_rep diferente de "Ins."/"Ges.") — apta a
      novo serviço.
    - Novilha: nulípara (nunca teve nenhum Serviço) que já atingiu o peso
      mínimo de 1ª cobertura (peso_apta_min(), mesmo parâmetro usado em
      agenda_veterinario.py para "novilhas_aptas_vazias" — reaproveitado
      aqui para não divergir o número em dois lugares); novilha não tem
      parto, então o critério de DEL não se aplica a ela.
    "Todas" soma os dois grupos.
    """
    peso_apta = peso_apta_min()
    resultado: dict[str, dict] = {}
    for chave, filtro in (
        ("todas", lambda a: True),
        ("vaca", lambda a: a.get("numero") in vacas_nums),
        ("novilha", lambda a: a.get("numero") not in vacas_nums),
    ):
        subset = [a for a in animais if filtro(a)]
        prenhes = vazias = inseminadas = 0
        # Detalhamento usado pelo gráfico de Situação Reprodutiva da Capa —
        # Prenhas/Inseminadas/PEV/A inseminar são o padrão; qualquer sit_rep
        # fora desse padrão (em branco ou não reconhecido) cai em
        # "nao_classificadas". Contadores independentes de `vazias` acima
        # (que soma TODO "Vaz.*") para não alterar o que já é consumido em
        # Indicadores > Gerais e no Menu do app.
        pev = a_inseminar = nao_classificadas = 0
        for a in subset:
            sit = (a.get("sit_rep") or "").strip()
            if sit == "Ges.":
                prenhes += 1
            elif sit.startswith("Vaz."):
                vazias += 1
            elif sit == "Ins.":
                inseminadas += 1
            categoria = _classificar_situacao_reprodutiva(sit)
            if categoria == "pev":
                pev += 1
            elif categoria == "a_inseminar":
                a_inseminar += 1
            elif categoria == "vazias":
                nao_classificadas += 1

        aptas_nums: list[str] = []
        for a in subset:
            numero = a.get("numero")
            sit = (a.get("sit_rep") or "").strip()
            if sit in ("Ins.", "Ges."):
                continue  # já inseminada ou prenhe — não é "apta" a novo serviço
            if numero in vacas_nums:
                del_dias = a.get("del_dias")
                if del_dias is not None and del_dias >= DEL_APTA_MIN:
                    aptas_nums.append(numero)
                continue
            if numero in numeros_com_servico:
                continue  # já tem QUALQUER histórico de serviço — não é nulípara
            peso = peso_por_animal.get(numero)
            if peso is not None and peso >= peso_apta:
                aptas_nums.append(numero)

        resultado[chave] = {
            "aptas": len(aptas_nums), "prenhes": prenhes, "vazias": vazias, "inseminadas": inseminadas,
            "aptas_nums": aptas_nums,
            "pev": pev, "a_inseminar": a_inseminar, "nao_classificadas": nao_classificadas,
        }
    return resultado


def calcular_indicadores(
    animais: list[dict],
    servicos: list[dict],
    partos: list[dict],
    data_ref: date | None = None,
    peso_por_animal: dict[str, float] | None = None,
    lotes: list[dict] | None = None,
) -> dict:
    """Calcula o painel de indicadores a partir dos dados carregados.

    `peso_por_animal` (numero_matriz -> peso_kg da pesagem corporal mais
    recente) é opcional — sem ele, "aptas" (novilhas nulíparas com peso
    mínimo de 1ª cobertura) sempre dá zero, já que peso é indispensável para
    essa aptidão. Ver `fazenda.api.routers.indicadores` para como é montado
    (mesmo padrão de `coletar_dados_criterios` em `routers/lotes.py`).

    `lotes` (dicts do cadastro de Lote — `codigo`, `status_lactacao`,
    `pre_parto`) identifica QUAL lote é "Secas"/"Pré-parto" pelo cadastro real,
    não por um número fixo — o cadastro pode renomear/renumerar os lotes a
    qualquer momento (ex.: o usuário já trocou qual código é Secas ×
    Pré-parto). Sem `lotes` (chamada isolada, ex. testes), cai no número
    histórico 04/05 só para não quebrar quem não passa o cadastro."""
    hoje = data_ref or date.today()
    peso_por_animal = peso_por_animal or {}
    concepcao_desde = _concepcao_desde()
    if lotes:
        codigos_secas = {l.get("codigo") for l in lotes if l.get("status_lactacao") == "seca"}
        codigos_pre_parto = {l.get("codigo") for l in lotes if l.get("pre_parto")}
    else:
        codigos_secas = {GRUPO_SECAS}
        codigos_pre_parto = {GRUPO_PRE_PARTO}

    # ---------------------------------------------------------------
    # Composição do rebanho
    # ---------------------------------------------------------------
    total = len(animais)
    distribuicao: dict[str, int] = {}
    for a in animais:
        g = a.get("grupo_primario") or "(sem grupo)"
        distribuicao[g] = distribuicao.get(g, 0) + 1

    codigos = [_codigo_grupo(a.get("grupo_primario")) for a in animais]
    vacas_lactacao = sum(1 for c in codigos if c in GRUPOS_LACTACAO)
    vacas_secas = sum(1 for c in codigos if c in codigos_secas)
    pre_parto = sum(1 for c in codigos if c in codigos_pre_parto)

    # ---------------------------------------------------------------
    # Situação reprodutiva do rebanho — herd-wide e por categoria (todas /
    # vaca / novilha). `vacas_nums` (matrizes com pelo menos um parto) é o
    # mesmo critério usado por `_benchmark_categorias` mais abaixo — calculado
    # uma única vez aqui e reaproveitado nos dois lugares.
    # ---------------------------------------------------------------
    vacas_nums = {p.get("numero_matriz") for p in partos if p.get("numero_matriz")}
    numeros_com_servico = {s.get("numero_matriz") for s in servicos if s.get("numero_matriz")}

    prenhes = vazias = inseminadas = 0
    for a in animais:
        sit = (a.get("sit_rep") or "").strip()
        if sit == "Ges.":
            prenhes += 1
        elif sit.startswith("Vaz."):
            vazias += 1
        elif sit == "Ins.":
            inseminadas += 1
    # Denominador de taxa_prenhez_pct/perc_vazias_pct: mantém o cálculo
    # histórico desses dois indicadores (soma dos 3 estados com situação
    # reprodutiva definida) — não é o mesmo "aptas" do painel abaixo.
    _rebanho_com_situacao = prenhes + vazias + inseminadas

    taxa_prenhez = round(100 * prenhes / _rebanho_com_situacao, 1) if _rebanho_com_situacao else None
    perc_vazias = round(100 * vazias / _rebanho_com_situacao, 1) if _rebanho_com_situacao else None

    # "Aptas" (elegibilidade de 1ª cobertura): só novilha nulípara (nunca
    # inseminada) com peso mínimo — ver `_reproducao_categorias`. Corrige o
    # bug relatado: antes "aptas" somava prenhes+vazias+inseminadas (ou seja,
    # "qualquer fêmea com situação reprodutiva definida"), o oposto de "apta
    # pela 1ª vez".
    reproducao_categorias = _reproducao_categorias(animais, numeros_com_servico, peso_por_animal, vacas_nums)
    aptas = reproducao_categorias["todas"]["aptas"]

    # ---------------------------------------------------------------
    # Concepção — serviços diagnosticados (POSITIVO / NEGATIVO) desde 01/01/2026
    # ---------------------------------------------------------------
    pos = sum(1 for s in servicos if _no_periodo(s, concepcao_desde) and _diag_upper(s.get("diagnostico")) == "POSITIVO")
    neg = sum(1 for s in servicos if _no_periodo(s, concepcao_desde) and _diag_upper(s.get("diagnostico")) == "NEGATIVO")
    diagnosticados = pos + neg
    taxa_concepcao = round(100 * pos / diagnosticados, 1) if diagnosticados else None

    # ---------------------------------------------------------------
    # DEL e produção das lactantes
    # ---------------------------------------------------------------
    del_lactacao = [
        a.get("del_dias")
        for a in animais
        if _codigo_grupo(a.get("grupo_primario")) in GRUPOS_LACTACAO and a.get("del_dias")
    ]
    del_medio = _media([float(d) for d in del_lactacao])

    producoes = [
        a.get("ult_cl_kg")
        for a in animais
        if a.get("ult_cl_kg") and a.get("ult_cl_kg") > 0
    ]
    producao_media = _media([float(p) for p in producoes])
    producao_total_dia = round(sum(float(p) for p in producoes), 1) if producoes else 0.0

    # ---------------------------------------------------------------
    # IEP — intervalo entre partos (média, em dias e meses)
    # ---------------------------------------------------------------
    partos_por_matriz: dict[str, list[date]] = {}
    for p in partos:
        d = p.get("data_parto")
        m = p.get("numero_matriz")
        if d and m:
            partos_por_matriz.setdefault(m, []).append(d)

    intervalos: list[int] = []
    for datas in partos_por_matriz.values():
        # Colapsa registros do mesmo parto (mais próximos que o piso biológico),
        # ancorando sempre no parto distinto mais antigo, e mede o intervalo
        # apenas entre partos efetivamente distintos.
        distintos: list[date] = []
        for d in sorted(set(datas)):
            if not distintos or (d - distintos[-1]).days >= _iep_minimo_dias():
                distintos.append(d)
        for anterior, atual in zip(distintos, distintos[1:]):
            intervalos.append((atual - anterior).days)

    iep_dias = round(sum(intervalos) / len(intervalos)) if intervalos else None
    iep_meses = round(iep_dias / 30.44, 1) if iep_dias else None

    # ---------------------------------------------------------------
    # Partos previstos — só matrizes ATUALMENTE prenhes (sit_rep = "Ges.").
    # Parto provável = data do último serviço POSITIVO + gestacao_dias_referencia()
    # (ponto médio da faixa editável gestacao_dias_min/max).
    # Uma matriz por linha (não conta serviços antigos nem vazias/PEV).
    # ---------------------------------------------------------------
    gestacao_prevista_dias = gestacao_dias_referencia()
    ult_pos: dict[str, date] = {}
    for s in servicos:
        d = s.get("data_servico")
        if isinstance(d, date) and _diag_upper(s.get("diagnostico")) == "POSITIVO":
            n = s.get("numero_matriz")
            if n and (n not in ult_pos or d > ult_pos[n]):
                ult_pos[n] = d

    previstos = {"em_30_dias": 0, "em_60_dias": 0, "em_90_dias": 0}
    previstos_nums: dict[str, list[str]] = {"em_30_dias": [], "em_60_dias": [], "em_90_dias": []}
    previstos_datas: dict[str, str] = {}  # numero -> data provável de parto (ISO)
    for a in animais:
        if (a.get("sit_rep") or "").strip() != "Ges.":
            continue
        num = a.get("numero")
        data_serv = ult_pos.get(num)
        if not data_serv:
            continue
        parto = data_serv + timedelta(days=gestacao_prevista_dias)
        dias = (parto - hoje).days
        if 0 <= dias <= 90:
            previstos_datas[num] = parto.isoformat()
            previstos["em_90_dias"] += 1
            previstos_nums["em_90_dias"].append(num)
            if dias <= 60:
                previstos["em_60_dias"] += 1
                previstos_nums["em_60_dias"].append(num)
            if dias <= 30:
                previstos["em_30_dias"] += 1
                previstos_nums["em_30_dias"].append(num)

    # ---------------------------------------------------------------
    # Benchmark reprodutivo (eficiência) — desde a data de corte (_concepcao_desde()).
    # Modelo dos "medidores": Prenhez = Serviço × Concepção.
    # Calculado para todas / vaca (já pariu) / novilha.
    # ---------------------------------------------------------------
    benchmark_categorias = _benchmark_categorias(animais, servicos, partos, vacas_nums, concepcao_desde)
    benchmark = benchmark_categorias["todas"]
    _bt = {b["chave"]: b["valor"] for b in benchmark}

    return {
        "data_referencia": hoje.isoformat(),
        "rebanho": {
            "total": total,
            "vacas_lactacao": vacas_lactacao,
            "vacas_secas": vacas_secas,
            "pre_parto": pre_parto,
            "distribuicao_grupos": dict(sorted(distribuicao.items())),
        },
        "reproducao": {
            "aptas": aptas,
            "aptas_nums": reproducao_categorias["todas"]["aptas_nums"],
            "prenhes": prenhes,
            "vazias": vazias,
            "inseminadas": inseminadas,
            "taxa_prenhez_pct": taxa_prenhez,
            "perc_vazias_pct": perc_vazias,
            "taxa_concepcao_pct": taxa_concepcao,
            "servicos_positivos": pos,
            "servicos_negativos": neg,
            "iep_dias": iep_dias,
            "iep_meses": iep_meses,
            "partos_previstos": previstos,
            "partos_previstos_nums": previstos_nums,
            "partos_previstos_datas": previstos_datas,
            "concepcao_desde": concepcao_desde.isoformat(),
            "taxa_servico_pct": _bt.get("taxa_servico"),
            "taxa_prenhez_ciclo_pct": _bt.get("taxa_prenhez_ciclo"),
            "servicos_por_prenhez": _bt.get("servicos_por_prenhez"),
            "taxa_perda_prenhez_pct": _bt.get("taxa_perda_prenhez"),
            "perc_vacas_prenhas_pct": _bt.get("perc_vacas_prenhas"),
            "dias_abertos": _bt.get("dias_abertos"),
            "del_1a_ia": _bt.get("del_1a_ia"),
        },
        "benchmark": benchmark,
        "benchmark_categorias": benchmark_categorias,
        "reproducao_categorias": reproducao_categorias,
        "producao": {
            "vacas_com_producao": len(producoes),
            "producao_media_kg": producao_media,
            "producao_total_dia_kg": producao_total_dia,
            "del_medio": del_medio,
        },
    }
