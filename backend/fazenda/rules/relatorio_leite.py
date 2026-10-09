"""
Contas PURAS da Fase C dos Relatórios (grupos Leite e Registros): custo do
leite pela metodologia CNA/Embrapa (COE → COT → CT), a sobra da comida por
vaca/dia (RMCA) e o custo do sêmen por prenhez. Nenhuma consulta ao banco
aqui — os routers (relatorio_leite.py, relatorio_compra_semen.py) montam as
listas e chamam estas funções; os testes as exercitam direto.

Metodologia (PLANO.md §5, CNA/Embrapa):
  COE = desembolso de custeio (as linhas de custo da DRE: variável, pessoal,
        operacionais) — o MESMO número do Resultado por litro;
  COT = COE + depreciação + remuneração da família (pró-labore, parâmetro);
  CT  = COT + retorno do capital (taxa ao ano × capital empatado, parâmetros).
Sem a família informada, o COT é exatamente o "custo total" do Resultado por
litro (COE + depreciação). Sem capital informado, o CT não existe (None) — a
tela diz o que falta em vez de mostrar um número inventado.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Iterable, Optional


def _r(v: Optional[float], casas: int = 2) -> Optional[float]:
    return None if v is None else round(v + 0.0, casas)


# ---------------------------------------------------------------------------
# Custo do leite: COE → COT → CT (estimativas com parâmetros)
# ---------------------------------------------------------------------------
def estimativas_custo_leite(
    *, coe: float, depreciacao: float, litros: float, meses: float,
    familia_mes: float, taxa_capital_aa: float, capital_rebanho: float, capital_maquinas: float, capital_terra: float,
) -> dict:
    """COT e CT do período (R$ e R$/L). `taxa_capital_aa` em % ao ano.
    `meses`: fração de meses do período (ver resultado_litro.meses_no_periodo)."""
    familia_mes = max(0.0, familia_mes or 0.0)
    taxa = max(0.0, taxa_capital_aa or 0.0)
    capital = {
        "rebanho": max(0.0, capital_rebanho or 0.0),
        "maquinas": max(0.0, capital_maquinas or 0.0),
        "terra": max(0.0, capital_terra or 0.0),
    }
    capital_total = sum(capital.values())
    familia_informada = familia_mes > 0
    capital_informado = capital_total > 0 and taxa > 0

    familia = familia_mes * meses
    retorno_capital = capital_total * (taxa / 100.0) * (meses / 12.0) if capital_informado else 0.0
    cot = coe + depreciacao + familia
    ct = cot + retorno_capital if capital_informado else None

    tem_litros = litros > 0
    por_l = (lambda v: None if v is None else v / litros) if tem_litros else (lambda v: None)
    return {
        "familia_informada": familia_informada,
        "capital_informado": capital_informado,
        "familia_mes": _r(familia_mes),
        "taxa_capital_aa": _r(taxa, 4),
        "capital": {k: _r(v) for k, v in capital.items()},
        "capital_total": _r(capital_total),
        "familia_periodo": _r(familia),
        "retorno_capital_periodo": _r(retorno_capital) if capital_informado else None,
        "cot": _r(cot),
        "ct": _r(ct),
        "familia_l": _r(por_l(familia), 4),
        "retorno_capital_l": _r(por_l(retorno_capital), 4) if capital_informado else None,
        "cot_l": _r(por_l(cot), 4),
        "ct_l": _r(por_l(ct), 4) if ct is not None else None,
    }


def media_ponderada_por_litro(meses: Iterable[dict], chave: str) -> Optional[float]:
    """Média de N meses de um custo por litro, ponderada pelos litros (Σ R$ ÷
    Σ litros) — só os meses com litros. `chave` é o total em R$ (ex.: "coe")."""
    soma = litros = 0.0
    for m in meses:
        lt = m.get("litros") or 0.0
        if lt > 0:
            soma += m.get(chave) or 0.0
            litros += lt
    return _r(soma / litros, 4) if litros > 0 else None


# ---------------------------------------------------------------------------
# Sobra da comida por vaca/dia (RMCA)
# ---------------------------------------------------------------------------
def _meses_do_periodo(ini: date, fim: date) -> list[tuple[int, int, int]]:
    """[(ano, mês, dias do mês dentro do período)]."""
    out: list[tuple[int, int, int]] = []
    d = ini
    while d <= fim:
        ultimo = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        ate = min(ultimo, fim)
        out.append((d.year, d.month, (ate - d).days + 1))
        d = ate + timedelta(days=1)
    return out


def vaca_dias(controles: Iterable[tuple[str, date]], ini: date, fim: date) -> dict:
    """Vacas em lactação × dias do período. Vaca em lactação no mês = teve ao
    menos um Controle leiteiro naquele mês (o mesmo critério do custo por
    vaca). Mês parcial conta só os dias dentro do período — assim um período
    de um ano não soma a vaca que saiu em março nos doze meses.

    Devolve vaca_dias, dias, vacas (distintas no período todo) e a média de
    vacas por dia (vaca_dias ÷ dias)."""
    por_mes: dict[tuple[int, int], set[str]] = {}
    distintas: set[str] = set()
    for numero, quando in controles:
        if not numero or quando is None:
            continue
        por_mes.setdefault((quando.year, quando.month), set()).add(numero)
    total = 0.0
    dias = 0
    for ano, mes, dias_no_periodo in _meses_do_periodo(ini, fim):
        dias += dias_no_periodo
        vacas_mes = por_mes.get((ano, mes), set())
        total += len(vacas_mes) * dias_no_periodo
        distintas |= vacas_mes
    return {
        "vaca_dias": round(total, 2),
        "dias": dias,
        "vacas": len(distintas),
        "vacas_media": _r(total / dias, 1) if dias else None,
    }


def rmca_por_vaca_dia(*, receita_bruta: float, receita_liquida: Optional[float], comida: float,
                     vaca_dias_total: float, litros: float) -> dict:
    """RMCA total e por vaca/dia. Convenção (decisão Q7): sobre a receita
    BRUTA do leite; a líquida (Funrural/Senar e descontos) ao lado quando
    existe (regras v2)."""
    rmca = receita_bruta - comida
    por_vd = (lambda v: None if v is None else v / vaca_dias_total) if vaca_dias_total > 0 else (lambda v: None)
    rmca_liq = None if receita_liquida is None else receita_liquida - comida
    return {
        "receita_bruta": _r(receita_bruta),
        "receita_liquida": _r(receita_liquida),
        "comida": _r(comida),
        "rmca": _r(rmca),
        "rmca_liquida": _r(rmca_liq),
        "comida_receita_pct": _r(100 * comida / receita_bruta, 2) if receita_bruta > 0 else None,
        "comida_receita_liquida_pct": _r(100 * comida / receita_liquida, 2) if receita_liquida and receita_liquida > 0 else None,
        "receita_vaca_dia": _r(por_vd(receita_bruta), 4),
        "comida_vaca_dia": _r(por_vd(comida), 4),
        "rmca_vaca_dia": _r(por_vd(rmca), 4),
        "rmca_liquida_vaca_dia": _r(por_vd(rmca_liq), 4),
        "litros": _r(litros, 1),
        "litros_vaca_dia": _r(por_vd(litros), 2),
    }


# ---------------------------------------------------------------------------
# Custo do sêmen por prenhez
# ---------------------------------------------------------------------------
TIPOS_SEMEN_IA = {"convencional", "sexado"}


def eh_inseminacao(tipo_servico: Optional[str], tipo_semen: Optional[str]) -> bool:
    """Serviço que gasta uma dose de sêmen: IA/IATF (tipo de sêmen convencional
    ou sexado). Monta natural (tipo "fazenda", ou serviço de monta/cobertura)
    não gasta dose."""
    semen = (tipo_semen or "").strip().lower()
    if semen:
        return semen in TIPOS_SEMEN_IA
    servico = (tipo_servico or "").strip().upper()
    if any(p in servico for p in ("MONTA", "COBERTURA", "REPASSE")):
        return False
    palavras = servico.replace("-", " ").replace("/", " ").split()
    return any(p in ("IA", "IATF") for p in palavras) or "INSEMIN" in servico


def preco_medio_dose(compras: Iterable[dict], ate: date, janela_dias: int = 365) -> dict:
    """Preço médio da dose comprada nos `janela_dias` antes de `ate` (o botijão
    mistura compras). Sem compra na janela, a média de TODAS as compras até
    `ate`, com `base` dizendo qual foi usada."""
    todas = [c for c in compras if c.get("data") and c["data"] <= ate and (c.get("doses") or 0) > 0]
    janela = [c for c in todas if c["data"] > ate - timedelta(days=janela_dias)]
    base = "12_meses" if janela else ("historico" if todas else None)
    usar = janela or todas
    doses = sum(c["doses"] for c in usar)
    valor = sum(c["doses"] * (c.get("valor_unitario") or 0.0) for c in usar)
    return {"preco": _r(valor / doses, 4) if doses else None, "doses": doses, "valor": _r(valor), "base": base}


def semen_por_prenhez(servicos: Iterable[dict], preco_dose: Optional[float], ini: date, fim: date) -> dict:
    """Inseminações do período (pela data do serviço), as já diagnosticadas,
    as prenhezes (diagnóstico POSITIVO) e o custo do sêmen por prenhez =
    doses das inseminações diagnosticadas × preço médio da dose ÷ prenhezes.
    Inseminação ainda sem diagnóstico fica de fora da conta (senão o custo por
    prenhez sobe só porque o toque ainda não aconteceu)."""
    ia = diag = pos = 0
    for s in servicos:
        quando = s.get("data_servico")
        if quando is None or not (ini <= quando <= fim):
            continue
        if not eh_inseminacao(s.get("tipo_servico"), s.get("tipo_semen")):
            continue
        ia += 1
        resultado = (s.get("diagnostico") or "").strip().upper()
        if resultado in ("POSITIVO", "NEGATIVO"):
            diag += 1
            if resultado == "POSITIVO":
                pos += 1
    custo_diag = diag * preco_dose if preco_dose is not None else None
    return {
        "inseminacoes": ia,
        "diagnosticadas": diag,
        "aguardando_diagnostico": ia - diag,
        "prenhezes": pos,
        "taxa_concepcao_pct": _r(100 * pos / diag, 1) if diag else None,
        "custo_semen_usado": _r(ia * preco_dose) if preco_dose is not None else None,
        "custo_semen_diagnosticadas": _r(custo_diag),
        "custo_por_prenhez": _r(custo_diag / pos) if (custo_diag is not None and pos) else None,
    }
