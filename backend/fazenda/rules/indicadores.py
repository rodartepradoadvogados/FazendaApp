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

from fazenda.rules.gestation import calcular_parto_provavel, dias_gestacao_da_raca
from fazenda.rules.iatf import SIT_REP_CANDIDATAS
from fazenda.rules.parametros import (
    BENCHMARK_METAS,
    data_corte_taxa_concepcao,
    gestacao_dias_min,
    gestacao_dias_referencia,
    get_param,
    idade_apta_min_meses,
    meta_concepcao_novilha,
    meta_taxa_concepcao,
    meta_taxa_prenhez,
    meta_taxa_servico,
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


def _data_servico(s: dict) -> Optional[date]:
    ds = s.get("data_servico")
    return ds if isinstance(ds, date) else None


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


def _iep_por_matriz(partos: list[dict]) -> list[dict]:
    """Detalhamento por matriz do IEP (drill-down do card 'IEP médio'): o
    intervalo entre os dois partos distintos mais recentes de cada matriz.
    Matrizes com um único parto (ainda sem intervalo) não entram na lista."""
    iep_minimo = _iep_minimo_dias()
    por_matriz: dict[str, list[date]] = {}
    for p in partos:
        d = p.get("data_parto")
        m = p.get("numero_matriz")
        if d and m:
            por_matriz.setdefault(m, []).append(d)
    resultado: list[dict] = []
    for numero, datas in por_matriz.items():
        distintos: list[date] = []
        for d in sorted(set(datas)):
            if not distintos or (d - distintos[-1]).days >= iep_minimo:
                distintos.append(d)
        if len(distintos) >= 2:
            resultado.append({
                "numero": numero,
                "iep_dias": (distintos[-1] - distintos[-2]).days,
                "data_parto_anterior": distintos[-2].isoformat(),
                "data_ultimo_parto": distintos[-1].isoformat(),
            })
    return resultado


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


def _metas_benchmark(categoria: str) -> dict[str, dict]:
    """Metas do benchmark reprodutivo por categoria. taxa_servico/
    taxa_concepcao/taxa_prenhez_ciclo vêm de Configurações > Parâmetros
    (editáveis, ver `parametros.meta_taxa_servico/meta_taxa_prenhez/
    meta_taxa_concepcao/meta_concepcao_novilha`) — as demais ainda usam a
    referência fixa de `BENCHMARK_METAS` (sem parâmetro equivalente hoje).
    Novilha usa sua própria meta de concepção, distinta da meta de vacas."""
    metas = {chave: dict(valor) for chave, valor in BENCHMARK_METAS.items()}
    metas["taxa_servico"]["meta"] = meta_taxa_servico()
    metas["taxa_prenhez_ciclo"]["meta"] = meta_taxa_prenhez()
    metas["taxa_concepcao"]["meta"] = meta_concepcao_novilha() if categoria == "novilha" else meta_taxa_concepcao()
    return metas


def _repro_benchmark(
    animais: list[dict], servicos: list[dict], partos: list[dict], desde: date, categoria: str = "todas",
    estados: dict[str, str] | None = None, hoje: date | None = None,
    descartar_nums: set[str] | None = None,
) -> list[dict]:
    """Painel de benchmark reprodutivo de um subconjunto do rebanho — usado
    para 'todas', 'vaca' e 'novilha'.

    Três correções em relação ao que este painel fazia antes (ver o modelo
    lógico em `fazenda.rules.programa_reprodutivo`):

    1. **Gestante saiu do denominador.** O denominador era
       `prenhes + vazias + inseminadas`, ou seja, incluía as prenhes. Vaca
       prenhe não pode ser inseminada — não pode entrar no denominador de uma
       taxa de serviço. Agora o denominador são as APTAS (regra R4).
    2. **Estado ao vivo em vez de `sit_rep`.** O corte era feito pelo texto
       congelado do GERAL.csv do Ideagri, que só muda no próximo upload. Agora
       usa o estado recalculado dos registros (`_estados_ao_vivo`), o mesmo que
       as listas de Rebanho — os dois lados passam a bater. Sem estados (ex.:
       chamador legado que passa só a lista de animais), cai no `sit_rep` de
       antes, preservando o comportamento desses consumidores.
    3. **Taxa de prenhez deixou de ser serviço × concepção** (regra R9). Passa
       a ser prenhes do período ÷ aptas, com os mesmos serviços avaliáveis.
    4. **`a_descartar` saiu do programa** (regra R1). O animal marcado para
       descarte não estava sendo cortado: ficava no denominador cobrando uma
       inseminação que ninguém pretende fazer. E se chegou a ser inseminado
       antes da marcação, ficava no numerador também — o que podia levar a
       taxa de serviço acima de 100%.

    E aplica a regra dos 28 dias (R7): serviço dos últimos 27 dias não entra em
    taxa nenhuma enquanto o desfecho não for conhecido.

    `descartar_nums` deve vir do rebanho INTEIRO, não do recorte desta
    categoria: os animais são separados em vaca/novilha por `vacas_nums` e os
    serviços por `ordem_parto`, dois cortes independentes — derivar o conjunto
    aqui dentro deixaria escapar o serviço de uma novilha descartada que caísse
    no painel de vacas. Sem o argumento, cai no recorte local, que é o que os
    chamadores diretos e os testes precisam.
    """
    from fazenda.rules.programa_reprodutivo import ESTADOS_APTOS, conta_em_taxa
    from fazenda.rules.estado_reprodutivo import GESTANTE as _GESTANTE

    hoje = hoje or date.today()
    estados = estados or {}
    if descartar_nums is None:
        descartar_nums = {
            a.get("numero") for a in animais if a.get("a_descartar") and a.get("numero")
        }
    # R1 — quem está marcado a descartar não está mais no programa reprodutivo.
    no_programa = [a for a in animais if a.get("numero") not in descartar_nums]

    if estados:
        aptas = sum(1 for a in no_programa if estados.get(a.get("numero")) in ESTADOS_APTOS)
        prenhes = sum(1 for a in animais if estados.get(a.get("numero")) == _GESTANTE)
    else:
        # Fallback legado: sem registros carregados não há o que recalcular.
        prenhes = vazias = inseminadas = 0
        for a in animais:
            sit = (a.get("sit_rep") or "").strip()
            if sit == "Ges.":
                prenhes += 1  # inventário — ver `total` abaixo
            elif a.get("numero") in descartar_nums:
                continue
            elif sit.startswith("Vaz."):
                vazias += 1
            elif sit == "Ins.":
                inseminadas += 1
        aptas = vazias + inseminadas  # sem as prenhes, ao contrário de antes
    # `prenhes` e `total` são INVENTÁRIO, não taxa do programa: respondem
    # "quantas das fêmeas estão prenhes hoje". A vaca marcada para descarte que
    # está prenhe continua prenhe e continua comendo — por isso os dois ficam
    # sobre o rebanho inteiro, ao contrário de `aptas`.
    total = len(animais)

    serv_periodo = [
        s for s in servicos
        if _no_periodo(s, desde) and s.get("numero_matriz") not in descartar_nums
    ]
    # R7 — o serviço só entra na conta quando dá para saber se pegou. Sem isto,
    # as IAs dos últimos dias entram no denominador da concepção sem nenhuma
    # chance de já terem virado prenhez, e a taxa despenca artificialmente.
    ultimas_datas: dict[str, date] = {}
    for s in servicos:
        n, d = s.get("numero_matriz"), _data_servico(s)
        if n and d and (n not in ultimas_datas or d > ultimas_datas[n]):
            ultimas_datas[n] = d
    avaliaveis = []
    for s in serv_periodo:
        d = _data_servico(s)
        posterior = bool(
            d and (ultima := ultimas_datas.get(s.get("numero_matriz"))) and ultima > d
        )
        if conta_em_taxa(s, hoje, servico_posterior=posterior):
            avaliaveis.append(s)

    pos = sum(1 for s in avaliaveis if _diag_upper(s.get("diagnostico")) == "POSITIVO")
    neg = sum(1 for s in avaliaveis if _diag_upper(s.get("diagnostico")) == "NEGATIVO")
    diag = pos + neg
    taxa_concepcao = round(100 * pos / diag, 1) if diag else None
    servidas = {s.get("numero_matriz") for s in avaliaveis if s.get("numero_matriz")}
    taxa_servico = round(100 * len(servidas) / aptas, 1) if aptas else None
    # R9 — prenhes ÷ aptas, NÃO serviço × concepção.
    concebidas = {
        s.get("numero_matriz") for s in avaliaveis
        if _diag_upper(s.get("diagnostico")) == "POSITIVO" and s.get("numero_matriz")
    }
    taxa_prenhez_ciclo = round(100 * len(concebidas) / aptas, 1) if aptas else None
    servicos_por_prenhez = round(len(avaliaveis) / pos, 1) if pos else None
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
    metas = _metas_benchmark(categoria)
    lista = []
    for chave, (label, unidade) in _BENCH_LABELS.items():
        m = metas.get(chave, {})
        lista.append({
            "chave": chave, "label": label, "unidade": unidade,
            "valor": valores.get(chave), "meta": m.get("meta"),
            "media_pais": m.get("media_pais"), "maior_melhor": m.get("maior_melhor", True),
        })
    return lista


def _benchmark_categorias(
    animais: list[dict], servicos: list[dict], partos: list[dict], vacas_nums: set, desde: date,
    estados: dict[str, str] | None = None, hoje: date | None = None,
) -> dict:
    """Benchmark separado por categoria: todas / vaca (já pariu) / novilha.

    `estados` são os estados reprodutivos AO VIVO (ver `_estados_ao_vivo`) —
    é o que faz o denominador deixar de sair do `sit_rep` congelado do CSV.
    """
    animais_vaca = [a for a in animais if a.get("numero") in vacas_nums]
    animais_novilha = [a for a in animais if a.get("numero") not in vacas_nums]
    serv_vaca = [s for s in servicos if (s.get("ordem_parto") or 0) >= 1]
    serv_novilha = [s for s in servicos if (s.get("ordem_parto") or 0) < 1]
    # Do rebanho inteiro, antes de qualquer recorte de categoria — ver a nota
    # sobre `descartar_nums` no docstring de `_repro_benchmark`.
    descartar_nums = {
        a.get("numero") for a in animais if a.get("a_descartar") and a.get("numero")
    }
    comum = {"estados": estados, "hoje": hoje, "descartar_nums": descartar_nums}
    return {
        "todas": _repro_benchmark(animais, servicos, partos, desde, categoria="todas", **comum),
        "vaca": _repro_benchmark(animais_vaca, serv_vaca, partos, desde, categoria="vaca", **comum),
        "novilha": _repro_benchmark(animais_novilha, serv_novilha, [], desde, categoria="novilha", **comum),
    }


DEL_APTA_MIN = 45  # vaca apta a novo serviço: dias mínimos após o último parto


def _estados_ao_vivo(
    animais: list[dict],
    servicos: list[dict],
    partos: list[dict],
    aplicacoes_iatf: list[dict],
    peso_por_animal: dict[str, float],
    vacas_nums: set,
    hoje: date,
) -> dict[str, str]:
    """Estado reprodutivo de cada animal, recalculado dos registros.

    Devolve {} quando não há NENHUM parto nem serviço carregado — nesse caso
    não há o que recalcular, e quem chamar cai no `sit_rep` de antes (é o que
    mantém chamadores legados, como o relatório personalizado e os testes que
    passam só uma lista de animais, funcionando exatamente como funcionavam).
    """
    if not partos and not servicos:
        return {}

    from fazenda.rules.estado_reprodutivo import classificar_animal
    from fazenda.rules.parametros import idade_apta_min_meses, peso_apta_min

    servicos_por: dict[str, list] = {}
    for s in servicos:
        servicos_por.setdefault(s.get("numero_matriz"), []).append(s)
    partos_por: dict[str, list] = {}
    for p in partos:
        partos_por.setdefault(p.get("numero_matriz"), []).append(p)
    iatf_por: dict[str, list] = {}
    for ap in aplicacoes_iatf:
        iatf_por.setdefault(ap.get("numero_matriz"), []).append(ap)

    pev = pev_dias()
    del_max = int(get_param("meta_del_max_1o_servico", 100) or 100)
    idade_apta = int(idade_apta_min_meses() * 30.44)
    peso_apta = peso_apta_min()

    estados: dict[str, str] = {}
    for a in animais:
        numero = a.get("numero")
        if not numero:
            continue
        nasc = a.get("data_nasc")
        if isinstance(nasc, str):
            try:
                nasc = date.fromisoformat(nasc[:10])
            except ValueError:
                nasc = None
        estados[numero] = classificar_animal(
            numero,
            hoje=hoje,
            partos=partos_por.get(numero, []),
            servicos=servicos_por.get(numero, []),
            aplicacoes_iatf=iatf_por.get(numero, []),
            pev_dias=pev,
            del_max_1o_servico=del_max,
            eh_vaca=numero in vacas_nums,
            idade_dias=(hoje - nasc).days if nasc else None,
            peso_kg=peso_por_animal.get(numero),
            idade_apta_dias=idade_apta,
            peso_apta_kg=peso_apta,
        )["estado"]
    return estados


def _reproducao_categorias(
    animais: list[dict],
    numeros_com_servico: set,
    peso_por_animal: dict[str, float],
    vacas_nums: set,
    estados: dict[str, str] | None = None,
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

    `estados` (numero -> estado ao vivo, ver fazenda.rules.estado_reprodutivo)
    é o caminho CORRETO e preferido: quando vem preenchido, a classificação
    sai dos registros reais (Parto/Servico/ProtocoloIatf) e a Capa/Menu passam
    a bater com as listas de Rebanho. Sem ele, cai no `sit_rep` congelado do
    CSV — mantido só para chamadores legados (ex.: relatório personalizado),
    que continuam funcionando como antes.
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
            estado = (estados or {}).get(a.get("numero"))
            if estado is not None:
                # Caminho ao vivo: "vazias" agrega tudo que não está prenhe
                # nem inseminada nem em protocolo — mesmo conjunto que o
                # "Vaz.*" do CSV representava, para o número do card não
                # mudar de significado.
                if estado == "gestante":
                    prenhes += 1
                elif estado == "inseminada":
                    inseminadas += 1
                elif estado in ("vazia", "apta", "atrasada", "pev", "nao_apta"):
                    vazias += 1
                if estado == "pev":
                    pev += 1
                elif estado in ("apta", "atrasada"):
                    a_inseminar += 1
                elif estado in ("vazia", "nao_apta"):
                    nao_classificadas += 1
                continue
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
            estado = (estados or {}).get(numero)
            if estado is not None:
                # Ao vivo, "apta" já é uma categoria exclusiva: quem está
                # prenhe, inseminada ou em protocolo nunca cai aqui.
                if estado == "apta":
                    aptas_nums.append(numero)
                continue
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
    aplicacoes_iatf: list[dict] | None = None,
    controles: list[dict] | None = None,
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

    # Estado reprodutivo AO VIVO por animal (ver fazenda.rules.estado_reprodutivo).
    # É o que faz a Capa/Menu baterem com as listas de Rebanho: os dois lados
    # passam a ler os mesmos registros, em vez de a Capa ler o sit_rep
    # congelado do CSV e o Rebanho ler os lançamentos.
    estados_por_animal = _estados_ao_vivo(
        animais, servicos, partos, aplicacoes_iatf or [], peso_por_animal, vacas_nums, hoje,
    )

    # Números das gestantes pelo MESMO critério ao vivo usado para contar
    # `prenhes` logo abaixo — reaproveitado no drill-down (`gestantes_detalhe`/
    # `partos_previstos`) mais adiante para o card e a lista baterem sempre.
    # Antes o card usava este critério (estado ao vivo, com fallback pro
    # sit_rep congelado do CSV) e o drill-down usava só o sit_rep cru — uma
    # matriz cujo estado ao vivo virou "gestante" antes do próximo import do
    # CSV entrava no card mas sumia da lista que abre ao clicar nele.
    numeros_gestantes_vivo: set[str] = set()
    prenhes = vazias = inseminadas = 0
    for a in animais:
        estado = estados_por_animal.get(a.get("numero"))
        if estado is not None:
            if estado == "gestante":
                prenhes += 1
                numeros_gestantes_vivo.add(a.get("numero"))
            elif estado == "inseminada":
                inseminadas += 1
            else:
                vazias += 1
            continue
        sit = (a.get("sit_rep") or "").strip()
        if sit == "Ges.":
            prenhes += 1
            numeros_gestantes_vivo.add(a.get("numero"))
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
    reproducao_categorias = _reproducao_categorias(
        animais, numeros_com_servico, peso_por_animal, vacas_nums, estados_por_animal,
    )
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

    # Produção do ÚLTIMO CONTROLE de cada animal, lida dos controles leiteiros
    # de verdade. `Animal.ult_cl_kg` (o campo que isto usava sozinho) só era
    # escrito pelo parser do GERAL.csv do Ideagri — quem lança pelo app via
    # este número congelado na data do último CSV importado, enquanto o
    # gráfico de produção ao lado já mostrava os valores novos. Com a
    # importação do Ideagri aposentada, `ult_cl_kg` nunca mais seria escrito.
    # Ele segue como fallback por animal, para as fazendas cujo histórico só
    # existe no campo importado.
    ultimo_controle_kg: dict[str, float] = {}
    data_do_ultimo: dict[str, date] = {}
    for c in controles or []:
        numero = c.get("numero_matriz") or c.get("numero")
        producao = c.get("producao_kg")
        data_c = c.get("data")
        if not numero or not producao or producao <= 0:
            continue
        anterior = data_do_ultimo.get(numero)
        if anterior is None or (isinstance(data_c, date) and data_c >= anterior):
            ultimo_controle_kg[numero] = float(producao)
            if isinstance(data_c, date):
                data_do_ultimo[numero] = data_c

    producoes = []
    for a in animais:
        numero = a.get("numero")
        valor = ultimo_controle_kg.get(numero) if numero else None
        if valor is None:
            valor = a.get("ult_cl_kg")
        if valor and valor > 0:
            producoes.append(valor)
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
    # Partos previstos — só matrizes ATUALMENTE prenhes, pelo mesmo critério
    # ao vivo de `numeros_gestantes_vivo` (não o sit_rep cru — ver comentário
    # acima de onde o set é montado, é o que faz o card "Gestantes" bater com
    # esta lista).
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
    # Detalhe de TODAS as gestantes (drill-down do card "Gestantes") — ao
    # contrário de `previstos_datas` acima (só as com parto em até 90 dias),
    # aqui entra qualquer matriz prenhe com um serviço positivo conhecido,
    # não importa o quão distante esteja do parto.
    gestantes_detalhe: list[dict] = []
    for a in animais:
        num = a.get("numero")
        if num not in numeros_gestantes_vivo:
            continue
        data_serv = ult_pos.get(num)
        if not data_serv:
            continue
        # Gestação da RAÇA do animal (Holandês 280, Girolando 287, Gir/Zebu
        # 295); só cai no ponto médio da faixa configurável quando a raça não
        # é conhecida. Fixar um valor único adiantava em 7-15 dias o parto
        # previsto de Girolando e Gir — e com ele a secagem e o pré-parto.
        dias_ate_parto = dias_gestacao_da_raca(a.get("raca"), gestacao_prevista_dias)
        parto = data_serv + timedelta(days=dias_ate_parto)
        dias = (parto - hoje).days
        gestantes_detalhe.append({
            "numero": num,
            "dias_gestacao": (hoje - data_serv).days,
            "parto_previsto": parto.isoformat(),
        })
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
    # Prenhez = prenhes ÷ aptas (R9) — NÃO é serviço × concepção.
    # Calculado para todas / vaca (já pariu) / novilha.
    # ---------------------------------------------------------------
    benchmark_categorias = _benchmark_categorias(
        animais, servicos, partos, vacas_nums, concepcao_desde,
        estados=estados_por_animal, hoje=hoje,
    )
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
            "gestantes_detalhe": gestantes_detalhe,
            "iep_por_matriz": _iep_por_matriz(partos),
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
