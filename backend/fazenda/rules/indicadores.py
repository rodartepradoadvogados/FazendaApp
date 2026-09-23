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
from math import ceil
from typing import Optional

from fazenda.ordenacao import chave_numero
from fazenda.rules.gestation import calcular_parto_provavel, dias_gestacao_da_raca
from fazenda.rules.iatf import SIT_REP_CANDIDATAS
from fazenda.rules.producao_leiteira import del_dias_ao_vivo
from fazenda.rules.parametros import (
    dias_reinseminacao_min,
    BENCHMARK_METAS,
    data_corte_taxa_concepcao,
    dias_minimos_no_ciclo,
    dias_resultado_conhecido,
    gestacao_dias_min,
    gestacao_dias_referencia,
    get_param,
    idade_apta_min_meses,
    idade_max_1a_cobertura_meses,
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


def _baixada_em(a: dict, hoje: date) -> bool:
    """R1 do programa reprodutivo (ver `programa_reprodutivo.baixada_em`),
    reescrita sobre dict em vez de `PerfilAnimal` — é o formato que circula
    aqui. Usada pelos indicadores de INVENTÁRIO (quantas fêmeas do rebanho
    ATUAL estão prenhas/vazias hoje) para tirar do denominador quem já saiu
    da fazenda. `data_baixa` é datada, então a baixa é reconstruída na data
    certa; `ativo=False` sem data de baixa é tratado como baixa já vigente."""
    data_baixa = a.get("data_baixa")
    if isinstance(data_baixa, str):
        try:
            data_baixa = date.fromisoformat(data_baixa[:10])
        except ValueError:
            data_baixa = None
    if data_baixa is not None:
        return hoje >= data_baixa
    return a.get("ativo") is False


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


def _parametros_ciclos() -> dict:
    """Os mesmos parâmetros que `GET /reproducao/ciclos-21-dias` passa para
    `calcular_series` — lidos de uma vez só.

    Cada acessor de `fazenda.rules.parametros` abre a sua própria sessão de
    banco, e `_benchmark_categorias` chama o benchmark 3x (todas/vaca/novilha):
    ler aqui e repassar o dicionário troca 18 idas ao banco por 6.
    """
    return {
        "pev_dias": pev_dias(),
        "dias_minimos": dias_minimos_no_ciclo(),
        "dias_resultado": dias_resultado_conhecido(),
        # Janela mínima de cio de repasse: sem passar, o motor usa o piso
        # embutido e o parâmetro editável da fazenda não faria efeito nenhum.
        "dias_minimos_repasse": dias_reinseminacao_min(),
        "del_max_1o_servico": int(get_param("meta_del_max_1o_servico", 100) or 100),
        "idade_apta_dias": int(idade_apta_min_meses() * 30.44),
        "idade_atraso_dias": int(idade_max_1a_cobertura_meses() * 30.44),
        "peso_apta_kg": peso_apta_min(),
    }


def _montar_perfis(
    animais: list[dict],
    servicos: list[dict],
    partos: list[dict],
    aplicacoes_iatf: list[dict],
    peso_por_animal: dict[str, float],
) -> list:
    """`PerfilAnimal` (ver `programa_reprodutivo.montar_perfil`) de cada animal,
    com os registros DELE indexados por `numero_matriz`.

    O peso não viaja no dict do animal (vem de outra tabela, a pesagem
    corporal), então é injetado aqui — sem ele a novilha nulípara nunca atinge
    a puberdade e cai fora de todo denominador.

    Monte SEMPRE a partir do rebanho inteiro e dos registros completos: o
    recorte por categoria é feito depois, pelo próprio perfil (`eh_vaca`).
    """
    from fazenda.rules.programa_reprodutivo import montar_perfil

    servicos_por: dict[str, list] = {}
    for s in servicos:
        servicos_por.setdefault(s.get("numero_matriz"), []).append(s)
    partos_por: dict[str, list] = {}
    for p in partos:
        partos_por.setdefault(p.get("numero_matriz"), []).append(p)
    iatf_por: dict[str, list] = {}
    for ap in aplicacoes_iatf:
        iatf_por.setdefault(ap.get("numero_matriz"), []).append(ap)

    perfis = []
    for a in animais:
        numero = a.get("numero")
        perfis.append(montar_perfil(
            {**a, "peso_kg": peso_por_animal.get(numero)},
            partos=partos_por.get(numero, []),
            servicos=servicos_por.get(numero, []),
            aplicacoes_iatf=iatf_por.get(numero, []),
        ))
    return perfis


CONTADORES_ZERO = {"bred": 0, "br_elig": 0, "preg": 0, "pg_elig": 0, "com_resultado": 0}


def _taxas_por_ciclos(
    perfis: list, categoria: str, desde: date, hoje: date, params: dict,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Taxas de serviço, prenhez e concepção do painel, saídas do motor de
    ciclos de 21 dias (`programa_reprodutivo`, regras R1–R9) — o MESMO cálculo
    de `GET /reproducao/ciclos-21-dias`.

    Por que isto substituiu a conta anterior: ela dividia um conjunto ACUMULADO
    desde `desde` (~7,6 meses em produção) por uma contagem INSTANTÂNEA de
    aptas de hoje. Toda fêmea que emprenhava saía do denominador e ficava no
    numerador, então o resultado estourava 100% POR CONSTRUÇÃO — a Capa exibia
    241,9% de taxa de serviço e 487,5% de prenhez em novilhas. E as metas
    (50% de serviço, 18% de prenhez) são metas POR CICLO DE 21 DIAS, padrão
    DairyComp: comparar um acumulado de 7,6 meses com elas não faria sentido
    nem com o denominador certo.

    A agregação dos N ciclos soma NUMERADORES e DENOMINADORES (média ponderada
    pelo tamanho de cada ciclo); a média simples das porcentagens daria o mesmo
    peso a um ciclo de 3 vacas e a um de 300.

    Só os ciclos com `janela_dg_completa` entram em prenhez e concepção: com a
    janela de diagnóstico ainda aberta o denominador já está cheio e o
    numerador não, e a taxa sai subestimada por construção (ver R7). Se nenhum
    ciclo fechou a janela, as duas voltam None em vez de um número inventado.
    """
    from fazenda.rules.programa_reprodutivo import calcular_series, ciclos_21_dias

    # Fallback legado: sem NENHUM registro no rebanho (chamador que passa só a
    # lista de animais — o relatório personalizado e os testes que fazem isso)
    # não há ciclo para calcular. O teste é sobre o rebanho INTEIRO, não sobre
    # a categoria: uma categoria sem serviço nenhum tem taxa 0%, que é um fato
    # do manejo, e não a ausência de dados que este fallback trata.
    if not any(p.partos or p.servicos for p in perfis):
        return None, None, None

    if categoria == "vaca":
        selecionados = [p for p in perfis if p.eh_vaca]
    elif categoria == "novilha":
        selecionados = [p for p in perfis if not p.eh_vaca]
    else:
        selecionados = list(perfis)

    return taxas_de_contadores(contadores_ciclos(selecionados, desde, hoje, params))


def contadores_ciclos(perfis: list, desde: date, hoje: date, params: dict) -> dict:
    """Numeradores e denominadores BRUTOS do motor de ciclos, somados sobre a
    série — antes de virarem porcentagem.

    Existem separados das taxas por uma razão de custo: `_benchmark_categorias`
    precisa dos mesmos números para "todas", "vaca" e "novilha", e a partição
    por `perfil.eh_vaca` é DISJUNTA e cobre o rebanho. Como todos estes campos
    são aditivos — `bred`/`br_elig`/`preg`/`pg_elig` contam animais, e
    `com_resultado` conta serviços de animais da partição —, "todas" é a soma
    de "vaca" e "novilha", e não precisa de uma terceira passada pelo motor.
    Cada passada percorre 21 dias por ciclo por animal, então derivar em vez de
    recalcular corta um terço do custo da Capa. `test_todas_e_a_soma_das_duas
    _categorias` prova que o derivado é idêntico ao calculado direto.
    """
    from fazenda.rules.programa_reprodutivo import calcular_series, ciclos_21_dias

    if not perfis:
        return dict(CONTADORES_ZERO)

    n_ciclos = max(1, min(26, ceil(((hoje - desde).days + 1) / 21)))
    ciclos = ciclos_21_dias(hoje, modo="fim", n_ciclos=n_ciclos)
    serie = calcular_series(perfis, ciclos, hoje, **params)

    # Só ciclos com a janela de DG fechada entram em prenhez e concepção — ver
    # a nota em `_taxas_por_ciclos`. A taxa de serviço usa a série inteira: o
    # serviço é fato consumado no ciclo em que aconteceu (R7 trava o
    # RESULTADO, não o serviço).
    fechados = [r for r in serie if r.janela_dg_completa]
    return {
        "bred": sum(len(r.bred) for r in serie),
        "br_elig": sum(len(r.br_elig) for r in serie),
        "preg": sum(len(r.preg) for r in fechados),
        "pg_elig": sum(len(r.pg_elig) for r in fechados),
        "com_resultado": sum(r.servicos_com_resultado for r in fechados),
    }


def somar_contadores(a: dict, b: dict) -> dict:
    """Soma campo a campo — válido porque a partição vaca/novilha é disjunta."""
    return {chave: a[chave] + b[chave] for chave in CONTADORES_ZERO}


def taxas_de_contadores(c: dict) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """(serviço, prenhez, concepção) a partir dos contadores brutos. Denominador
    zero devolve None — não 0%, que afirmaria um fato que não se mediu."""
    return (
        round(100 * c["bred"] / c["br_elig"], 1) if c["br_elig"] else None,
        round(100 * c["preg"] / c["pg_elig"], 1) if c["pg_elig"] else None,
        round(100 * c["preg"] / c["com_resultado"], 1) if c["com_resultado"] else None,
    )


def _repro_benchmark(
    animais: list[dict], servicos: list[dict], partos: list[dict], desde: date, categoria: str = "todas",
    estados: dict[str, str] | None = None, hoje: date | None = None,
    descartar_nums: set[str] | None = None,
    aplicacoes_iatf: list[dict] | None = None,
    peso_por_animal: dict[str, float] | None = None,
    perfis: list | None = None,
    params_ciclos: dict | None = None,
    contadores_prontos: dict | None = None,
    del_por_matriz: dict[str, float] | None = None,
) -> list[dict]:
    """Painel de benchmark reprodutivo de um subconjunto do rebanho — usado
    para 'todas', 'vaca' e 'novilha'.

    As TRÊS TAXAS (serviço, concepção e prenhez) saem do motor de ciclos de 21
    dias — ver `_taxas_por_ciclos`, e o modelo lógico (R1–R9) no topo de
    `fazenda.rules.programa_reprodutivo`. É o mesmo cálculo que a tela de
    Ciclos de 21 Dias mostra, então os dois lados do sistema passam a dar o
    mesmo número. Antes, cada uma dessas taxas dividia um acumulado do período
    inteiro pela contagem instantânea de aptas de HOJE, e estourava 100% por
    construção (241,9% de serviço em produção).

    Os demais indicadores da lista continuam como estavam, sobre os serviços do
    período: `servicos_por_prenhez`, `taxa_perda_prenhez`, `dias_abertos`,
    `del_1a_ia`, `del_medio`, `iep_meses` e `perc_vacas_prenhas` (este último é
    INVENTÁRIO — quantas fêmeas estão prenhes hoje —, não taxa do programa).

    Parâmetros do motor de ciclos:
      - `aplicacoes_iatf`/`peso_por_animal` alimentam `montar_perfil` (o peso
        não está no dict do animal); ambos opcionais, porque há chamadores
        legados que passam só animais/serviços/partos.
      - `perfis`/`params_ciclos`, quando vêm preenchidos, são reaproveitados de
        `_benchmark_categorias`: os perfis precisam ser montados do rebanho
        INTEIRO com os registros COMPLETOS de cada animal (o recorte de
        categoria é feito pelo próprio perfil, ver `_taxas_por_ciclos`), e os
        parâmetros vêm do banco, uma leitura por acessor. Sem eles, cada um é
        montado/lido aqui — o caminho dos chamadores diretos e dos testes.

    `descartar_nums` deve vir do rebanho INTEIRO, não do recorte desta
    categoria: os animais são separados em vaca/novilha por `vacas_nums` e os
    serviços por `ordem_parto`, dois cortes independentes — derivar o conjunto
    aqui dentro deixaria escapar o serviço de uma novilha descartada que caísse
    no painel de vacas. Sem o argumento, cai no recorte local, que é o que os
    chamadores diretos e os testes precisam.
    """
    from fazenda.rules.programa_reprodutivo import conta_em_taxa
    from fazenda.rules.estado_reprodutivo import GESTANTE as _GESTANTE, NAO_APTA as _NAO_APTA

    hoje = hoje or date.today()
    estados = estados or {}
    if descartar_nums is None:
        descartar_nums = {
            a.get("numero") for a in animais if a.get("a_descartar") and a.get("numero")
        }

    # `prenhes` é o numerador de `perc_vacas_prenhas` (INVENTÁRIO). Baixada É
    # porta de saída sem exceção (diferente de a_descartar): sem o corte, uma
    # gestante baixada ficaria no numerador mesmo já fora de `total` (abaixo),
    # podendo passar de 100%.
    if estados:
        prenhes = sum(
            1 for a in animais
            if estados.get(a.get("numero")) == _GESTANTE and not _baixada_em(a, hoje)
        )
    else:
        # Fallback legado: sem registros carregados não há o que recalcular,
        # e o único corte possível é o `sit_rep` congelado do CSV.
        prenhes = sum(
            1 for a in animais
            if (a.get("sit_rep") or "").strip() == "Ges." and not _baixada_em(a, hoje)
        )
    # `prenhes` é INVENTÁRIO, não taxa do programa: responde "quantas das
    # fêmeas estão prenhes hoje". A vaca marcada para descarte que está
    # prenhe continua prenhe e continua comendo — por isso ela fica no
    # numerador, embora a R1 a tenha tirado do programa reprodutivo.
    #
    # `total` (denominador de perc_vacas_prenhas) ERA `len(animais)` — o
    # rebanho fêmeo INTEIRO, bezerra incluída: uma bezerra de seis meses não
    # pode estar prenhe, e incluí-la no denominador de "% de fêmeas prenhas"
    # dilui o número sem significado nenhum. Agora é o rebanho no PROGRAMA
    # reprodutivo (R1: puberdade ∧ ¬a_descartar ∧ ¬baixada) — MAIS a exceção
    # da gestante marcada a_descartar, que R1 sozinha excluiria mas que aqui
    # precisa continuar (mesmo motivo do numerador: ela está prenhe e vai
    # parir, isto é inventário, não a taxa do programa).
    if estados:
        total = sum(
            1 for a in animais
            if estados.get(a.get("numero")) != _NAO_APTA  # impúbere nunca entrou no programa
            and not _baixada_em(a, hoje)
            and (a.get("numero") not in descartar_nums or estados.get(a.get("numero")) == _GESTANTE)
        )
    else:
        # Fallback sem estado ao vivo: o sit_rep congelado não diz puberdade,
        # então o corte aqui é parcial (só descarte/baixa) — menos preciso
        # que o caminho ao vivo, mas evita voltar ao antigo denominador
        # (rebanho inteiro) quando não há registros carregados.
        total = sum(
            1 for a in animais
            if not _baixada_em(a, hoje)
            and (a.get("numero") not in descartar_nums or (a.get("sit_rep") or "").strip() == "Ges.")
        )

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
    # As três taxas do painel vêm do motor de ciclos de 21 dias (R1–R9), não
    # mais de um acumulado do período dividido pelas aptas de hoje — ver
    # `_taxas_por_ciclos` para o porquê. A chave de saída continua
    # `taxa_prenhez_ciclo`: é dela que o frontend depende.
    if perfis is None:
        perfis = _montar_perfis(
            animais, servicos, partos, aplicacoes_iatf or [], peso_por_animal or {},
        )
    if contadores_prontos is not None:
        # Vindos de `_benchmark_categorias`, que já rodou o motor uma vez por
        # categoria e derivou "todas" da soma — ver `contadores_ciclos`.
        taxa_servico, taxa_prenhez_ciclo, taxa_concepcao = taxas_de_contadores(contadores_prontos)
    else:
        taxa_servico, taxa_prenhez_ciclo, taxa_concepcao = _taxas_por_ciclos(
            perfis, categoria, desde, hoje, params_ciclos or _parametros_ciclos(),
        )
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
    # DEL das lactantes: o ao vivo quando o chamador o entrega (o mesmo mapa
    # que alimenta `producao.del_medio` — os dois campos são rotulados "DEL
    # médio" e não podem discordar dentro do mesmo payload). Sem o mapa
    # (chamada isolada, testes), cai no `del_dias` congelado como antes.
    if del_por_matriz is not None:
        del_medio = _media([
            v for a in animais
            for v in [del_por_matriz.get(a.get("numero"))] if v is not None
        ])
    else:
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
    aplicacoes_iatf: list[dict] | None = None,
    peso_por_animal: dict[str, float] | None = None,
    del_por_matriz: dict[str, float] | None = None,
) -> dict:
    """Benchmark separado por categoria: todas / vaca (já pariu) / novilha.

    `estados` são os estados reprodutivos AO VIVO (ver `_estados_ao_vivo`) —
    é o que faz o denominador deixar de sair do `sit_rep` congelado do CSV.

    Os PERFIS do motor de ciclos são montados UMA VEZ, aqui, do rebanho inteiro
    e com os registros completos de cada animal, e o recorte de categoria é
    feito lá dentro pelo próprio perfil (`eh_vaca`). É o que corrige o
    double-count da novilha que PARIU no meio do período: `animais_vaca`/
    `animais_novilha` a separam pelo parto, mas `serv_vaca`/`serv_novilha`
    fatiam os SERVIÇOS por `ordem_parto` — as inseminações dela de antes do
    parto caíam no recorte de novilha e as de depois no de vaca, e ela era
    contada nos dois painéis. (Os dois recortes seguem valendo para os
    indicadores que não são as três taxas — DEL, IEP, dias abertos etc.)
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
    perfis = _montar_perfis(
        animais, servicos, partos, aplicacoes_iatf or [], peso_por_animal or {},
    )
    params_ciclos = _parametros_ciclos()
    comum = {
        "estados": estados, "hoje": hoje, "descartar_nums": descartar_nums,
        "perfis": perfis, "params_ciclos": params_ciclos,
        "del_por_matriz": del_por_matriz,
    }
    # O motor de ciclos roda DUAS vezes, não três: a partição por
    # `perfil.eh_vaca` é disjunta e cobre o rebanho, e todos os contadores são
    # aditivos, então "todas" é a soma das outras duas. Cada passada percorre
    # 21 dias por ciclo por animal — derivar corta um terço do custo da Capa.
    # Sem NENHUM registro carregado não há ciclo a calcular e cada
    # `_repro_benchmark` cai sozinho no fallback legado (taxas None).
    contadores: dict[str, dict | None] = {"todas": None, "vaca": None, "novilha": None}
    if any(p.partos or p.servicos for p in perfis):
        hoje_ = hoje or date.today()
        c_vaca = contadores_ciclos([p for p in perfis if p.eh_vaca], desde, hoje_, params_ciclos)
        c_novilha = contadores_ciclos([p for p in perfis if not p.eh_vaca], desde, hoje_, params_ciclos)
        contadores = {
            "vaca": c_vaca, "novilha": c_novilha,
            "todas": somar_contadores(c_vaca, c_novilha),
        }
    return {
        "todas": _repro_benchmark(animais, servicos, partos, desde, categoria="todas",
                                  contadores_prontos=contadores["todas"], **comum),
        "vaca": _repro_benchmark(animais_vaca, serv_vaca, partos, desde, categoria="vaca",
                                 contadores_prontos=contadores["vaca"], **comum),
        "novilha": _repro_benchmark(animais_novilha, serv_novilha, [], desde, categoria="novilha",
                                    contadores_prontos=contadores["novilha"], **comum),
    }


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
    idade_atraso = int(idade_max_1a_cobertura_meses() * 30.44)
    peso_apta = peso_apta_min()

    estados: dict[str, str] = {}
    for a in animais:
        numero = a.get("numero")
        if not numero:
            continue
        estados[numero] = classificar_animal(
            numero,
            hoje=hoje,
            partos=partos_por.get(numero, []),
            servicos=servicos_por.get(numero, []),
            aplicacoes_iatf=iatf_por.get(numero, []),
            pev_dias=pev,
            del_max_1o_servico=del_max,
            eh_vaca=numero in vacas_nums,
            idade_dias=_idade_dias(a.get("data_nasc"), hoje),
            peso_kg=peso_por_animal.get(numero),
            idade_apta_dias=idade_apta,
            idade_atraso_dias=idade_atraso,
            peso_apta_kg=peso_apta,
        )["estado"]
    return estados


def _idade_dias(data_nasc, hoje: date) -> int | None:
    """`data_nasc` de um dict de animal (model_dump) pode chegar como `date`
    ou como string ISO — mesma tolerância dos dois lugares que precisam da
    idade em dias a partir daí (estado ao vivo e o fallback de aptidão de
    novilha logo abaixo)."""
    nasc = data_nasc
    if isinstance(nasc, str):
        try:
            nasc = date.fromisoformat(nasc[:10])
        except ValueError:
            nasc = None
    return (hoje - nasc).days if nasc else None


def _reproducao_categorias(
    animais: list[dict],
    numeros_com_servico: set,
    peso_por_animal: dict[str, float],
    vacas_nums: set,
    estados: dict[str, str] | None = None,
    hoje: date | None = None,
) -> dict:
    """Situação reprodutiva (prenhes/vazias/inseminadas/aptas) por categoria:
    todas / vaca (já pariu) / novilha.

    'Aptas' usa dois critérios diferentes conforme a categoria, porque
    "apta" tem sentido distinto para quem já pariu e para quem nunca pariu:
    - Vaca: DEL (dias desde o último parto) >= pev_dias() e não está
      inseminada nem prenhe (sit_rep diferente de "Ins."/"Ges.") — apta a
      novo serviço.
    - Novilha: nulípara (nunca teve nenhum Serviço) que já atingiu IDADE
      (idade_apta_min_meses()) E peso (peso_apta_min()) mínimos de 1ª
      cobertura — a mesma dupla condição da matriz canônica (ver
      estado_reprodutivo.classificar_animal, regra 7): peso sozinho não
      basta, senão uma bezerra pesada mas ainda nova contava como apta.
    "Todas" soma os dois grupos.

    `estados` (numero -> estado ao vivo, ver fazenda.rules.estado_reprodutivo)
    é o caminho CORRETO e preferido: quando vem preenchido, a classificação
    sai dos registros reais (Parto/Servico/ProtocoloIatf) e a Capa/Menu passam
    a bater com as listas de Rebanho. Sem ele, cai no `sit_rep` congelado do
    CSV — mantido só para chamadores legados (ex.: relatório personalizado),
    que continuam funcionando como antes. `hoje` só é usado neste caminho de
    FALLBACK, para calcular a idade da novilha a partir de `data_nasc` —
    sem `estados` nem `hoje`, a idade não entra no critério (retrocompatível
    com quem chamava esta função sem essa data)."""
    peso_apta = peso_apta_min()
    idade_apta_dias = round(idade_apta_min_meses() * 30.44)
    resultado: dict[str, dict] = {}
    for chave, filtro in (
        ("todas", lambda a: True),
        ("vaca", lambda a: a.get("numero") in vacas_nums),
        ("novilha", lambda a: a.get("numero") not in vacas_nums),
    ):
        subset = [a for a in animais if filtro(a)]
        prenhes = vazias = inseminadas = 0
        # Números por trás de CADA contador — o drill-down da Capa/Indicadores
        # abre exatamente a lista que gerou o número, em vez de refiltrar o
        # `sit_rep` congelado do CSV no cliente (o mesmo padrão já provado por
        # `aptas_nums`/`partos_previstos_nums`, os dois que nunca divergiram).
        prenhes_nums: list[str] = []
        vazias_nums: list[str] = []
        inseminadas_nums: list[str] = []
        pev_nums: list[str] = []
        a_inseminar_nums: list[str] = []
        nao_classificadas_nums: list[str] = []
        em_protocolo_nums: list[str] = []
        nao_aptas_nums: list[str] = []
        # Detalhamento usado pelo gráfico de Situação Reprodutiva da Capa —
        # Prenhas/Inseminadas/PEV/A inseminar são o padrão; qualquer sit_rep
        # fora desse padrão (em branco ou não reconhecido) cai em
        # "nao_classificadas". Contadores independentes de `vazias` acima
        # (que soma TODO "Vaz.*") para não alterar o que já é consumido em
        # Indicadores > Gerais e no Menu do app.
        # `em_protocolo` é balde próprio (estado ao vivo homônimo): antes ele
        # não entrava em fatia nenhuma do donut da Capa — nem em `vazias` (que
        # o exclui de propósito), nem em pev/a_inseminar/nao_classificadas — e
        # por isso as fatias não fechavam o rebanho da categoria. Com ele,
        # prenhes+inseminadas+em_protocolo+pev+a_inseminar+nao_classificadas+
        # nao_aptas é uma partição exata do subset.
        #
        # `nao_aptas` — balde PRÓPRIO, separado de `nao_classificadas` (pedido
        # do produtor, 23/09/2026): a novilha nao_apta (ainda não bateu
        # idade/peso mínimos de 1ª cobertura) não tem "situação reprodutiva"
        # nenhuma pra falar a verdade — ela nem é candidata a serviço ainda.
        # Jogá-la dentro de "Vazias"/"nao_classificadas" inflava o donut da
        # Capa (novilha imatura contada junto de quem já está apta e vazia).
        # Balde à parte preserva a partição exata (nada desaparece do total)
        # e dá ao frontend uma fatia própria ("Não aptas") em vez de escondê-la
        # dentro de "Vazias". Só ocorre em novilha nulípara (nunca em vaca —
        # ver estado_reprodutivo.classificar_animal), então nunca aparece na
        # categoria "vaca".
        pev = a_inseminar = nao_classificadas = em_protocolo = nao_aptas = 0
        for a in subset:
            numero = a.get("numero")
            estado = (estados or {}).get(numero)
            if estado is not None:
                # Caminho ao vivo: "vazias" agrega tudo que não está prenhe
                # nem inseminada nem em protocolo — mesmo conjunto que o
                # "Vaz.*" do CSV representava, para o número do card não
                # mudar de significado.
                #
                # NAO_APTA fica de fora de propósito (pedido do produtor,
                # 23/09/2026): "vazia" é uma leitura reprodutiva — só faz
                # sentido para quem já está em condições de ser avaliada
                # (apta/atrasada/pev). Uma novilha nao_apta (ainda não bateu
                # idade/peso mínimos) não é "vazia", é "ainda não apta" — a
                # métrica é de aptidão, não de reprodução, e contá-la em
                # "Vazias" inflava o card (ex.: 20 novilhas vazias na Capa
                # quando boa parte só ainda não tinha idade/peso pra ser
                # avaliada). NAO_APTA só ocorre em novilha nulípara (nunca em
                # vaca — ver estado_reprodutivo.classificar_animal), então
                # esta mudança nunca afeta a contagem de vacas.
                if estado == "gestante":
                    prenhes += 1
                    prenhes_nums.append(numero)
                elif estado == "inseminada":
                    inseminadas += 1
                    inseminadas_nums.append(numero)
                elif estado in ("vazia", "apta", "atrasada", "pev"):
                    vazias += 1
                    vazias_nums.append(numero)
                if estado == "pev":
                    pev += 1
                    pev_nums.append(numero)
                elif estado in ("apta", "atrasada"):
                    a_inseminar += 1
                    a_inseminar_nums.append(numero)
                elif estado == "vazia":
                    nao_classificadas += 1
                    nao_classificadas_nums.append(numero)
                elif estado == "nao_apta":
                    nao_aptas += 1
                    nao_aptas_nums.append(numero)
                elif estado == "em_protocolo":
                    em_protocolo += 1
                    em_protocolo_nums.append(numero)
                continue
            sit = (a.get("sit_rep") or "").strip()
            if sit == "Ges.":
                prenhes += 1
                prenhes_nums.append(numero)
            elif sit.startswith("Vaz."):
                vazias += 1
                vazias_nums.append(numero)
            elif sit == "Ins.":
                inseminadas += 1
                inseminadas_nums.append(numero)
            categoria = _classificar_situacao_reprodutiva(sit)
            if categoria == "pev":
                pev += 1
                pev_nums.append(numero)
            elif categoria == "a_inseminar":
                a_inseminar += 1
                a_inseminar_nums.append(numero)
            elif categoria == "vazias":
                nao_classificadas += 1
                nao_classificadas_nums.append(numero)
            # Sem estado ao vivo não há como saber que o animal está em
            # protocolo (o `sit_rep` do CSV não tem esse valor): `em_protocolo`
            # fica em 0 neste caminho, e a partição das 6 fatias continua
            # exata porque `_classificar_situacao_reprodutiva` já cobre
            # prenhes/inseminadas/pev/a_inseminar e joga o resto em vazias.

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
                if del_dias is not None and del_dias >= pev_dias():
                    aptas_nums.append(numero)
                continue
            if numero in numeros_com_servico:
                continue  # já tem QUALQUER histórico de serviço — não é nulípara
            peso = peso_por_animal.get(numero)
            if peso is None or peso < peso_apta:
                continue
            # Idade E peso, a mesma dupla condição da matriz canônica (ver
            # docstring da função) — sem `hoje` (chamador legado que não a
            # informou), a idade não dá pra calcular e o critério cai só no
            # peso, como sempre foi.
            if hoje is not None:
                idade_dias = _idade_dias(a.get("data_nasc"), hoje)
                if idade_dias is None or idade_dias < idade_apta_dias:
                    continue
            aptas_nums.append(numero)

        resultado[chave] = {
            "aptas": len(aptas_nums), "prenhes": prenhes, "vazias": vazias, "inseminadas": inseminadas,
            "aptas_nums": aptas_nums,
            "pev": pev, "a_inseminar": a_inseminar, "nao_classificadas": nao_classificadas,
            "em_protocolo": em_protocolo, "nao_aptas": nao_aptas,
            "prenhes_nums": prenhes_nums, "vazias_nums": vazias_nums,
            "inseminadas_nums": inseminadas_nums, "pev_nums": pev_nums,
            "a_inseminar_nums": a_inseminar_nums,
            "nao_classificadas_nums": nao_classificadas_nums,
            "em_protocolo_nums": em_protocolo_nums,
            "nao_aptas_nums": nao_aptas_nums,
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
    secagens: list[dict] | None = None,
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
    histórico 04/05 só para não quebrar quem não passa o cadastro.

    `secagens` (dicts de `Secagem` — `numero_matriz`, `data_secagem`)
    alimenta o DEL ao vivo de `producao.del_medio` (ver `del_dias_ao_vivo`,
    em `rules.producao_leiteira`): sem ele, o DEL ao vivo de cada lactante
    ainda é recalculado a partir do último PARTO (sempre disponível, via
    `partos`), só sem o corte de quem já secou — equivalente a chamar com
    `secagens=[]`. É o parâmetro que os dois caminhos puros que não carregam
    Secagem (`rules.manual_fazenda`/`rules.assistente`, antes desta correção)
    seguem podendo omitir sem quebrar."""
    hoje = data_ref or date.today()
    peso_por_animal = peso_por_animal or {}
    concepcao_desde = _concepcao_desde()
    if lotes:
        codigos_secas = {l.get("codigo") for l in lotes if l.get("status_lactacao") == "seca"}
        codigos_pre_parto = {l.get("codigo") for l in lotes if l.get("pre_parto")}
        # Mesma lógica de codigos_secas/codigos_pre_parto acima, faltando até
        # agora: sem isto, "vacas em lactação" ficava presa ao número fixo
        # 01/02/03 mesmo quando o cadastro real de Lote (status_lactacao)
        # dizia outra coisa — um lote novo (ex. "04 — pós-parto imediato",
        # criado numa reorganização de números) ficava invisível a esta
        # contagem mesmo com Parto/Lactação reais abertos, porque a conta
        # nunca olha Parto/Lactação: só compara o código do lote atual do
        # animal contra este conjunto. Bug real reportado pelo usuário
        # 2026-09-10 (37 = soma de 01+02+03, lote 4 ausente).
        codigos_lactacao = {l.get("codigo") for l in lotes if l.get("status_lactacao") == "lactacao"}
        if not codigos_lactacao:
            # Cadastro de Lote existe mas nenhum está marcado "Situação
            # produtiva = Lactação" — não apaga a contagem, cai no padrão
            # histórico (mesma rede de segurança de codigos_secas/pre_parto).
            codigos_lactacao = set(GRUPOS_LACTACAO)
    else:
        codigos_secas = {GRUPO_SECAS}
        codigos_pre_parto = {GRUPO_PRE_PARTO}
        codigos_lactacao = set(GRUPOS_LACTACAO)

    # ---------------------------------------------------------------
    # Composição do rebanho
    # ---------------------------------------------------------------
    total = len(animais)
    distribuicao: dict[str, int] = {}
    for a in animais:
        g = a.get("grupo_primario") or "(sem grupo)"
        distribuicao[g] = distribuicao.get(g, 0) + 1

    codigos = [_codigo_grupo(a.get("grupo_primario")) for a in animais]
    vacas_lactacao = sum(1 for c in codigos if c in codigos_lactacao)
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
    # Numerador/denominador do PROGRAMA reprodutivo (R1), usados só por
    # taxa_prenhez_pct/perc_vazias_pct logo abaixo. `prenhes`/`vazias`/
    # `inseminadas` acima são o rebanho INTEIRO e alimentam outros
    # consumidores (ex.: card "Vazias" do app mobile) — não são o escopo
    # desta correção, e continuam de pé.
    #
    # `prenhes_programa` (não só `vazias_programa`) também precisou de corte
    # próprio: `prenhes` conta toda gestante, mesmo baixada — a baixa é
    # porta de saída SEM exceção (ao contrário da a_descartar), então uma
    # gestante baixada some do denominador mas ficaria no numerador cru,
    # o que poderia passar de 100%. `prenhes_programa` é sempre <=
    # `rebanho_programa` por construção (é contado dentro do mesmo `if`).
    rebanho_programa = vazias_programa = prenhes_programa = 0
    # Números por trás de `prenhes_programa`/`vazias_programa` — o drill-down
    # dos cards "Fêmeas prenhas"/"Vazias" de Indicadores abre exatamente a
    # lista que gerou o percentual, em vez de refiltrar o sit_rep congelado
    # do CSV no cliente (mesmo padrão de `aptas_nums`/`partos_previstos_nums`).
    prenhes_programa_nums: list[str] = []
    vazias_programa_nums: list[str] = []
    for a in animais:
        numero = a.get("numero")
        estado = estados_por_animal.get(numero)
        descartar = bool(a.get("a_descartar"))
        baixada = _baixada_em(a, hoje)
        if estado is not None:
            if estado == "gestante":
                prenhes += 1
                numeros_gestantes_vivo.add(numero)
            elif estado == "inseminada":
                inseminadas += 1
            else:
                # Era aqui o defeito: este `else` é um catch-all que absorve
                # TUDO que não é gestante nem inseminada — inclusive a
                # bezerra impúbere (estado 'nao_apta'), que nunca poderia
                # estar prenhe. `vazias` (linha acima) mantém esse sentido
                # antigo para não mudar os outros consumidores; o corte de
                # verdade é feito abaixo, só para o denominador dos 2%.
                vazias += 1
            # R1 (puberdade ∧ ¬a_descartar ∧ ¬baixada), com a exceção da
            # gestante marcada a_descartar: ela já saiu do programa por R1,
            # mas aqui é INVENTÁRIO — está prenhe e ainda vai parir, então
            # continua no numerador e no denominador. Baixada NÃO tem essa
            # exceção — já saiu da fazenda de verdade, nem gestante escapa.
            if estado != "nao_apta" and not baixada and (not descartar or estado == "gestante"):
                rebanho_programa += 1
                if estado == "gestante":
                    prenhes_programa += 1
                    prenhes_programa_nums.append(numero)
                elif estado != "inseminada":
                    # `perc_vazias_pct` alimenta o card rotulado "Vazias", cujo
                    # drill-down abre a lista filtrada por sit_rep "Vaz." — sem
                    # as inseminadas. Jogar a inseminada aqui faria o número do
                    # card divergir da lista que abre ao clicar nele, o mesmo
                    # defeito que `numeros_gestantes_vivo` já corrigiu acima.
                    # Por isso os três baldes não somam `rebanho_programa`: a
                    # diferença são justamente as inseminadas.
                    vazias_programa += 1
                    vazias_programa_nums.append(numero)
            continue
        sit = (a.get("sit_rep") or "").strip()
        eh_gestante = sit == "Ges."
        if eh_gestante:
            prenhes += 1
            numeros_gestantes_vivo.add(numero)
        elif sit.startswith("Vaz."):
            vazias += 1
        elif sit == "Ins.":
            inseminadas += 1
        # Fallback sem estado ao vivo (sit_rep congelado): o texto do CSV não
        # diz puberdade, então o corte de impúbere não é possível aqui — só
        # descarte/baixa. Menos preciso que o caminho ao vivo, mas evita
        # regredir ao denominador antigo (rebanho inteiro) quando não há
        # registros carregados.
        if not baixada and (not descartar or eh_gestante):
            rebanho_programa += 1
            if eh_gestante:
                prenhes_programa += 1
                prenhes_programa_nums.append(numero)
            elif sit.startswith("Vaz."):
                vazias_programa += 1
                vazias_programa_nums.append(numero)

    taxa_prenhez = round(100 * prenhes_programa / rebanho_programa, 1) if rebanho_programa else None
    perc_vazias = round(100 * vazias_programa / rebanho_programa, 1) if rebanho_programa else None

    # "Aptas" (elegibilidade de 1ª cobertura): só novilha nulípara (nunca
    # inseminada) com peso mínimo — ver `_reproducao_categorias`. Corrige o
    # bug relatado: antes "aptas" somava prenhes+vazias+inseminadas (ou seja,
    # "qualquer fêmea com situação reprodutiva definida"), o oposto de "apta
    # pela 1ª vez".
    reproducao_categorias = _reproducao_categorias(
        animais, numeros_com_servico, peso_por_animal, vacas_nums, estados_por_animal, hoje,
    )
    aptas = reproducao_categorias["todas"]["aptas"]

    # ---------------------------------------------------------------
    # Serviços diagnosticados (POSITIVO / NEGATIVO) desde a data de corte —
    # contagens BRUTAS do período, informativas.
    #
    # ATENÇÃO: `pos`/`neg` NÃO são mais os termos da taxa de concepção. A
    # taxa passou a ser a única do sistema, a do motor de ciclos de 21 dias
    # (`_bt["taxa_concepcao"]`, ver `_taxas_por_ciclos`): média ponderada dos
    # ciclos fechados, com a regra dos 28 dias para a janela de diagnóstico.
    # A conta antiga (pos ÷ (pos+neg)) somava serviços de ciclos diferentes
    # num acumulado só, e por isso a Capa mostrava dois números distintos
    # com o mesmo nome ("Concepção / serviço" e o medidor "Taxa de
    # Concepção"). Estes dois contadores ficam porque respondem a outra
    # pergunta, honesta e sem ponderação: quantos diagnósticos deram
    # positivo e quantos deram negativo no período.
    # ---------------------------------------------------------------
    pos = sum(1 for s in servicos if _no_periodo(s, concepcao_desde) and _diag_upper(s.get("diagnostico")) == "POSITIVO")
    neg = sum(1 for s in servicos if _no_periodo(s, concepcao_desde) and _diag_upper(s.get("diagnostico")) == "NEGATIVO")

    # ---------------------------------------------------------------
    # DEL AO VIVO das lactantes — card "DEL médio" da Produção.
    #
    # Era `a.get("del_dias")` direto: o campo congelado do CSV do Ideagri,
    # que só volta a bater com a realidade no próximo upload. A lista de
    # animais (GET /animais/) já mostra DEL AO VIVO (parto mais recente
    # lançado no app, zerado por uma Secagem posterior) — usar o congelado
    # aqui fazia o card discordar da lista logo ao lado dele, e DEL alimenta
    # tanto a dieta quanto a decisão de secagem. `del_dias_ao_vivo` é a MESMA
    # função usada por `routers/animais.py::listar_animais` (extraída para
    # `rules.producao_leiteira` para não duplicar a regra em dois lugares).
    # MUDANÇA DE SEMÂNTICA (deliberada — ver decisão do dono do produto):
    # `producao.del_medio` deixa de ser a média do DEL CONGELADO e passa a
    # ser a média do DEL AO VIVO. `alertas_indicador.py` resolve este mesmo
    # campo por `("producao", "del_medio")` — um alerta configurado sobre ele
    # passa a comparar contra o número ao vivo, não mais o do último CSV.
    # ---------------------------------------------------------------
    ultimo_parto_por_matriz: dict[str, date] = {}
    for p in partos:
        d, m = p.get("data_parto"), p.get("numero_matriz")
        if d and m and (m not in ultimo_parto_por_matriz or d > ultimo_parto_por_matriz[m]):
            ultimo_parto_por_matriz[m] = d
    ultima_secagem_por_matriz: dict[str, date] = {}
    for s in secagens or []:
        d, m = s.get("data_secagem"), s.get("numero_matriz")
        if d and m and (m not in ultima_secagem_por_matriz or d > ultima_secagem_por_matriz[m]):
            ultima_secagem_por_matriz[m] = d

    # Mapa (e não só a lista da média) porque o MESMO DEL ao vivo alimenta o
    # "DEL médio" do benchmark reprodutivo — ver `_repro_benchmark`. Os dois
    # campos se chamam `del_medio` e são rotulados "DEL médio" na tela; se um
    # fosse ao vivo e o outro continuasse no `del_dias` congelado do CSV, o
    # mesmo painel mostraria dois números diferentes com o mesmo nome — que é
    # exatamente o defeito que esta correção veio remover, não introduzir.
    del_vivo_por_matriz: dict[str, float] = {}
    del_vivo_lactacao: list[float] = []
    for a in animais:
        if _codigo_grupo(a.get("grupo_primario")) not in codigos_lactacao:
            continue
        numero = a.get("numero")
        del_vivo = del_dias_ao_vivo(
            a.get("del_dias"),
            ultimo_parto_por_matriz.get(numero),
            ultima_secagem_por_matriz.get(numero),
            hoje,
        )
        if del_vivo is None:
            continue
        del_vivo_lactacao.append(float(del_vivo))
        # O mapa é só o índice para o benchmark. A MÉDIA não depende dele:
        # um dict de animal sem `numero` (chamada isolada/teste do motor puro)
        # continua entrando na média, como sempre entrou — indexar não pode
        # virar critério de inclusão.
        if numero:
            del_vivo_por_matriz[numero] = float(del_vivo)
    del_medio = _media(del_vivo_lactacao)
    del_medio_animais = len(del_vivo_lactacao)

    # ---------------------------------------------------------------
    # O CONTROLE DO DIA — card "Produção do dia". Decisão do dono do produto:
    # antes o card somava o ÚLTIMO controle de CADA animal, em QUALQUER data
    # (uma vaca controlada em março entrava no mesmo total de uma controlada
    # ontem), enquanto o drill-down ao lado listava só as linhas do dia mais
    # recente — card e lista eram dois números diferentes com o mesmo nome,
    # por construção. Agora os dois são a mesma coisa: o card É a soma exata
    # de `controle_nums`, o dia do controle leiteiro mais recente com
    # produção > 0.
    #
    # Duas passadas de propósito (não uma só): a primeira só descobre QUAL é
    # o dia mais recente; a segunda soma as linhas DAQUELE dia. Assim
    # `producao_total_dia_kg` é, por construção, a soma de `controle_do_dia`
    # nos números de `controle_nums` — não uma segunda conta que possa
    # divergir da lista.
    # ---------------------------------------------------------------
    data_controle: date | None = None
    for c in controles or []:
        producao = c.get("producao_kg")
        data_c = c.get("data_controle") or c.get("data")  # "data" = alias legado, ver histórico abaixo
        if not producao or producao <= 0 or not isinstance(data_c, date):
            continue
        if data_controle is None or data_c > data_controle:
            data_controle = data_c

    controle_do_dia: dict[str, float] = {}  # numero_matriz -> produção somada no dia
    if data_controle is not None:
        for c in controles or []:
            numero = c.get("numero_matriz") or c.get("numero")
            producao = c.get("producao_kg")
            data_c = c.get("data_controle") or c.get("data")
            if not numero or not producao or producao <= 0 or data_c != data_controle:
                continue
            controle_do_dia[numero] = controle_do_dia.get(numero, 0.0) + float(producao)

    # Ordem crescente do número do brinco — mesma convenção usada nas listas
    # de rebanho (chave_numero já resolve string numérica x alfanumérica).
    controle_nums = sorted(controle_do_dia.keys(), key=chave_numero)
    vacas_no_controle = len(controle_nums)
    # A GARANTIA estrutural desta etapa: o total É a soma das linhas dos
    # números que estão em `controle_nums`, não uma segunda passagem por
    # `controles` que poderia, por um bug futuro, divergir da lista.
    producao_total_dia = round(sum(controle_do_dia[n] for n in controle_nums), 1) if controle_nums else 0.0
    producao_media_dia = round(producao_total_dia / vacas_no_controle, 1) if vacas_no_controle else None
    cobertura_controle_pct = (
        round(100 * vacas_no_controle / vacas_lactacao, 1) if vacas_lactacao else None
    )

    # ---------------------------------------------------------------
    # ULTIMO POR ANIMAL — o acumulado antigo (último controle de CADA animal,
    # em qualquer data, com fallback para o campo congelado do CSV do
    # Ideagri). Não é mais o card, mas continua disponível com um nome que
    # diz o que ele é — outras telas (ex. a ficha do animal) ainda fazem
    # sentido com "a última produção conhecida desta vaca", mesmo que não
    # seja hoje.
    #
    # `Animal.ult_cl_kg` tinha um único ponto de escrita em todo o backend: o
    # parser do GERAL.csv do Ideagri (aposentado). Quem lançava controle pelo
    # app via esse número congelado na data do último CSV importado, ao lado
    # de um gráfico que já mostrava os valores novos. Segue como fallback por
    # animal — para o histórico de quem só tem o valor importado — mas agora
    # contado à parte (`congelado`/`congelado_nums`) para a origem do dado
    # ficar visível, não misturada ao que já vem de ControleLeiteiro
    # (`de_controle`).
    # ---------------------------------------------------------------
    ultimo_controle_kg: dict[str, float] = {}
    data_do_ultimo: dict[str, date] = {}
    for c in controles or []:
        numero = c.get("numero_matriz") or c.get("numero")
        producao = c.get("producao_kg")
        data_c = c.get("data_controle") or c.get("data")
        if not numero or not producao or producao <= 0:
            continue
        anterior = data_do_ultimo.get(numero)
        if anterior is None or (isinstance(data_c, date) and data_c >= anterior):
            ultimo_controle_kg[numero] = float(producao)
            if isinstance(data_c, date):
                data_do_ultimo[numero] = data_c

    producoes: list[float] = []
    de_controle = 0
    congelado = 0
    congelado_nums: list[str] = []
    for a in animais:
        numero = a.get("numero")
        valor = ultimo_controle_kg.get(numero) if numero else None
        if valor is not None:
            producoes.append(valor)
            de_controle += 1
            continue
        valor = a.get("ult_cl_kg")
        if valor and valor > 0:
            producoes.append(valor)
            congelado += 1
            if numero:
                congelado_nums.append(numero)
    producao_media = _media([float(p) for p in producoes])
    producao_total_antiga = round(sum(float(p) for p in producoes), 1) if producoes else 0.0
    congelado_nums.sort(key=chave_numero)

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
    # Serviço/concepção/prenhez saem do motor de ciclos de 21 dias (R1–R9), a
    # mesma conta da tela de Ciclos de 21 Dias: média ponderada dos ciclos que
    # cabem no período, e NÃO um acumulado dividido pelas aptas de hoje.
    # Calculado para todas / vaca (já pariu) / novilha.
    # ---------------------------------------------------------------
    benchmark_categorias = _benchmark_categorias(
        animais, servicos, partos, vacas_nums, concepcao_desde,
        estados=estados_por_animal, hoje=hoje,
        aplicacoes_iatf=aplicacoes_iatf or [], peso_por_animal=peso_por_animal,
        del_por_matriz=del_vivo_por_matriz,
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
            # Códigos de lote (2 dígitos) que compõem "vacas_lactacao" acima —
            # o frontend usa esta lista (em vez de um ["01","02","03"] fixo)
            # pra filtrar a mesma lista de animais no drill-down do card,
            # senão o clique no card mostra um conjunto diferente do número
            # exibido assim que o cadastro de Lote tiver mais de 3 lotes de
            # lactação.
            "codigos_lactacao": sorted(c for c in codigos_lactacao if c),
        },
        "reproducao": {
            "aptas": aptas,
            "aptas_nums": reproducao_categorias["todas"]["aptas_nums"],
            "prenhes": prenhes,
            "vazias": vazias,
            "inseminadas": inseminadas,
            "taxa_prenhez_pct": taxa_prenhez,
            "prenhes_programa_nums": prenhes_programa_nums,
            "perc_vazias_pct": perc_vazias,
            "vazias_programa_nums": vazias_programa_nums,
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
            # Alias do benchmark, como os demais desta lista: UMA definição de
            # taxa de concepção no sistema inteiro — a do motor de ciclos de
            # 21 dias, a mesma da tela Ciclos de 21 Dias e do medidor "Taxa de
            # Concepção" da Capa.
            "taxa_concepcao_pct": _bt.get("taxa_concepcao"),
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
            # O CONTROLE DO DIA — o card é a soma exata desta lista (ver bloco
            # acima). `producao_media_kg`/`del_medio` MUDARAM DE SEMÂNTICA
            # (média do dia / DEL ao vivo) — `alertas_indicador.py` resolve os
            # dois por `("producao","producao_media_kg")` e
            # `("producao","del_medio")`, e passam a comparar contra os novos
            # números; é deliberado, ver decisão do dono do produto.
            "data_controle": data_controle.isoformat() if data_controle else None,
            "producao_total_dia_kg": producao_total_dia,
            "producao_media_kg": producao_media_dia,
            "vacas_no_controle": vacas_no_controle,
            "controle_nums": controle_nums,
            "vacas_lactacao": vacas_lactacao,
            "cobertura_controle_pct": cobertura_controle_pct,
            "del_medio": del_medio,
            "del_medio_animais": del_medio_animais,
            # O acumulado antigo (último controle de CADA animal, em qualquer
            # data) — deixou de ser o card, mas segue disponível com um nome
            # honesto sobre o que é.
            "ultimo_por_animal": {
                "producao_total_kg": producao_total_antiga,
                "producao_media_kg": producao_media,
                "vacas_com_producao": len(producoes),
                "de_controle": de_controle,
                "congelado": congelado,
                "congelado_nums": congelado_nums,
            },
            # Compat: mesmas telas que hoje leem "vacas_com_producao" no nível
            # de cima esperando "quantas entraram no card" — agora o card É o
            # controle do dia, então este alias passa a valer o mesmo que
            # `vacas_no_controle`.
            "vacas_com_producao": vacas_no_controle,
        },
    }
