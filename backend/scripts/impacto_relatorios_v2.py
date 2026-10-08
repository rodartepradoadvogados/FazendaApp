"""
Relatório de impacto das regras novas do Financeiro (Fase A) — SOMENTE LEITURA.

PARA QUÊ
--------
Antes de ligar a flag `financeiro_regras_v2` numa fazenda, medir quanto cada
número muda. Roda o motor ANTIGO e o NOVO sobre os mesmos dados, mês a mês, e
grava um CSV com antes / depois / Δ:

  - `depois`: regras novas com os dados como estão hoje;
  - `depois_com_backfill`: regras novas SIMULANDO o backfill de natureza
    (scripts/backfill_natureza_fin.py) — sem gravá-lo.

Métricas desta versão (PR 1, 7 e 4): as 15 linhas da DRE (competência e
caixa), o total fora da DRE (e por natureza), o não classificado, os
numeradores dos custos por hectare, por vaca/lote e por safra (mais a
depreciação e o COT) e, na seção `leite`, custo por litro (litros, custo,
R$/L) e RMCA (receita bruta, custo, RMCA, receita líquida). Juros/descontos da
baixa e deduções da nota de venda aparecem no CSV de lançamentos.
Saldo e Caixa Real entram quando as regras deles existirem (PR 6) — o
registro de métricas fica em `METRICAS` para os PRs seguintes estenderem.

O CSV de lançamentos (`--csv-lancamentos`) lista cada lançamento que muda de
lugar, com o motivo (compra de bem, conta de financiamento, etc.).

GARANTIA DE LEITURA
-------------------
A conexão é aberta em modo só leitura (`PRAGMA query_only` no SQLite,
`SET TRANSACTION READ ONLY` no Postgres) e a sessão termina com `rollback()`.
Mesmo assim: rode num DUMP RESTAURADO em banco descartável, nunca na produção.

COMO USAR
---------
    DATABASE_URL=sqlite:////caminho/dump.db \\
      python -m scripts.impacto_relatorios_v2 --fazenda 3 --de 2026-01 --ate 2026-09 \\
        --csv impacto.csv --csv-lancamentos lancamentos.csv
"""
from __future__ import annotations

import argparse
import calendar
import csv
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402
from sqlmodel import Session  # noqa: E402

COLUNAS = ["secao", "periodo", "metrica", "antes", "depois", "delta", "depois_com_backfill", "delta_com_backfill"]
COLUNAS_LANC = [
    "periodo", "regime", "numero_lancamento", "conta_id", "item_id", "codigo_conta", "descricao", "valor",
    "linha_antes", "destino_depois", "motivo",
]


# Registros que só existem nas regras novas: (linha antes, destino depois, motivo).
ORIGENS_NOVAS = {
    "diferenca_baixa": (
        "(fora da DRE: a conta ficava no valor contratado)", "OUTRAS_REC_DESP",
        "juro/multa ou desconto apurado na baixa (PR 7)",
    ),
    "deducao_nota": (
        "(rateado na receita: entrava líquida)", "DEDUCAO_IMPOSTOS",
        "Funrural/Senar ou desconto da nota de venda (PR 4)",
    ),
}


def _meses(de: str, ate: str) -> list[tuple[date, date]]:
    ano, mes = (int(x) for x in de.split("-"))
    ano_f, mes_f = (int(x) for x in ate.split("-"))
    saida = []
    while (ano, mes) <= (ano_f, mes_f):
        saida.append((date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return saida


def _abrir_somente_leitura(conn) -> None:
    dialeto = conn.dialect.name
    if dialeto == "sqlite":
        conn.exec_driver_sql("PRAGMA query_only = ON")
    elif dialeto == "postgresql":
        conn.execute(text("SET TRANSACTION READ ONLY"))


def _linhas_dre(resposta: dict) -> dict[str, float]:
    valores = {f"dre.{linha['chave']}": linha["valor"] for linha in resposta["cascata"]}
    valores["dre.fora_da_dre"] = resposta["fora_da_dre"]["total"]
    valores["dre.nao_classificado"] = resposta["nao_classificado"]["total"]
    for natureza, total in (resposta["fora_da_dre"].get("por_natureza") or {}).items():
        valores[f"dre.fora_da_dre.{natureza}"] = total
    return valores


def _destino_antes(registro: dict, mapa_linha: dict[str, str]) -> str:
    from fazenda.rules.dre import NAO_ENTRA_NA_DRE, resolver_linha_dre

    linha = resolver_linha_dre(registro.get("codigo_conta"), mapa_linha)
    if linha == NAO_ENTRA_NA_DRE:
        return "fora_da_dre"
    return linha or "nao_classificado"


def _motivo(registro: dict, contexto, plano_backfill, contas_por_id: dict, itens_por_id: dict) -> str:
    from fazenda.rules.natureza import resolver_natureza_plano

    conta = contas_por_id.get(registro.get("conta_id"))
    item = itens_por_id.get(registro.get("item_id"))
    if item is not None and item.natureza_fin:
        return "natureza informada no item"
    if conta is not None and conta.natureza_fin:
        return "natureza informada no lançamento"
    if plano_backfill is not None:
        for m in plano_backfill.mudancas:
            if m["tabela"] == "conta_gerencial" and m["id"] == registro.get("conta_id"):
                return f"backfill: {m['motivo']}"
        codigo = registro.get("codigo_conta") or ""
        for m in plano_backfill.mudancas:
            if m["tabela"] == "plano_conta_gerencial" and (codigo == m["codigo"] or codigo.startswith(m["codigo"] + ".")):
                return f"backfill (conta {m['codigo']} do plano): {m['motivo']}"
    if conta is not None and conta.patrimonio_id in contexto.patrimonios_vendidos and conta.tipo == "receita":
        return "receita de bem baixado com venda (o ganho/perda entra em Outras)"
    if resolver_natureza_plano(registro.get("codigo_conta"), contexto.mapa_natureza_plano):
        return "natureza da conta do plano"
    return "conta fora da DRE (NAO_ENTRA_NA_DRE) sem natureza informada"


def gerar(session: Session, fazenda_id: int, de: str, ate: str, *, centro_custo_vaca: str | None = "Pecuária Leiteira") -> dict:
    """Calcula tudo e devolve {"linhas": [...], "lancamentos": [...]}. Não grava."""
    from fazenda.api.routers.financeiro import (
        _contexto_natureza, _mapa_linha_por_codigo, _periodo_filtradas_dre, calcular_custo_litro_leite, calcular_dre,
        custos_operacionais_periodo, rmca_gerencial,
    )
    from fazenda.api.routers.relatorio_custo_producao import _despesas_periodo
    from fazenda.models import ContaGerencial, LancamentoItem, PlanoContaGerencial, Safra
    from fazenda.rules import backfill_natureza
    from fazenda.rules import parametros
    from fazenda.rules.natureza import OPERACIONAL
    from sqlmodel import select

    parametros.fazenda_atual.set(fazenda_id)
    session.info["fazenda_id"] = fazenda_id
    plano_bf = backfill_natureza.planejar(session, fazenda_id)
    sim = {"sobrepor_conta": plano_bf.sobrepor_conta(), "sobrepor_plano": plano_bf.sobrepor_plano()}
    mapa_linha = _mapa_linha_por_codigo(session, fazenda_id)
    contexto_sim = _contexto_natureza(session, fazenda_id, sim["sobrepor_conta"], None, sim["sobrepor_plano"])
    contas_por_id = {c.id: c for c in session.exec(select(ContaGerencial).where(ContaGerencial.fazenda_id == fazenda_id)).all()}
    itens_por_id = {i.id: i for i in session.exec(select(LancamentoItem).where(LancamentoItem.fazenda_id == fazenda_id)).all()}
    plano = session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == fazenda_id)).all()
    cod_receita = {p.codigo for p in plano if p.rmca_receita_leite}
    cod_custo = {p.codigo for p in plano if p.rmca_custo_alimentacao}

    linhas: list[dict] = []
    lancamentos: list[dict] = []

    def _linha(secao, periodo, metrica, antes, depois, depois_bf):
        linhas.append({
            "secao": secao, "periodo": periodo, "metrica": metrica,
            "antes": round(antes or 0.0, 2), "depois": round(depois or 0.0, 2),
            "delta": round((depois or 0.0) - (antes or 0.0), 2),
            "depois_com_backfill": round(depois_bf or 0.0, 2),
            "delta_com_backfill": round((depois_bf or 0.0) - (antes or 0.0), 2),
        })

    for inicio, fim in _meses(de, ate):
        periodo = f"{inicio:%Y-%m}"
        for regime in ("competencia", "caixa"):
            antes = calcular_dre(session, fazenda_id, inicio, fim, None, regime, regras_v2=False)
            depois = calcular_dre(session, fazenda_id, inicio, fim, None, regime, regras_v2=True)
            depois_bf = calcular_dre(session, fazenda_id, inicio, fim, None, regime, regras_v2=True, **sim)
            va, vd, vb = _linhas_dre(antes), _linhas_dre(depois), _linhas_dre(depois_bf)
            for chave in sorted(set(va) | set(vd) | set(vb)):
                _linha(f"dre_{regime}", periodo, chave, va.get(chave), vd.get(chave), vb.get(chave))
            for registro in depois_bf["_registros"]:
                origem_nova = ORIGENS_NOVAS.get(registro.get("origem"))
                if origem_nova is not None:
                    # PR 7 / PR 4: registros que só existem nas regras novas.
                    linha_antes, destino, motivo = origem_nova
                    lancamentos.append({
                        "periodo": periodo, "regime": regime,
                        "numero_lancamento": registro.get("numero_lancamento"), "conta_id": registro.get("conta_id"),
                        "item_id": registro.get("item_id"), "codigo_conta": registro.get("codigo_conta"),
                        "descricao": registro.get("descricao"), "valor": registro.get("valor"),
                        "linha_antes": linha_antes, "destino_depois": destino, "motivo": motivo,
                    })
                    continue
                natureza = registro.get("natureza") or OPERACIONAL
                if natureza == OPERACIONAL:
                    continue
                destino_antes = _destino_antes(registro, mapa_linha)
                lancamentos.append({
                    "periodo": periodo, "regime": regime,
                    "numero_lancamento": registro.get("numero_lancamento"), "conta_id": registro.get("conta_id"),
                    "item_id": registro.get("item_id"), "codigo_conta": registro.get("codigo_conta"),
                    "descricao": registro.get("descricao"), "valor": registro.get("valor"),
                    "linha_antes": destino_antes, "destino_depois": f"fora_da_dre.{natureza}",
                    "motivo": _motivo(registro, contexto_sim, plano_bf, contas_por_id, itens_por_id),
                })

        # Custos (competência). "antes" = o numerador de hoje das telas (a mesma
        # soma de relatorio_custo_hectare com a flag desligada; sem COT).
        filtradas, valores = _periodo_filtradas_dre(session, inicio, fim, None, "competencia", fazenda_id)
        ha_antes = round(sum(valores.get(c.id, 0.0) for c in filtradas if c.tipo == "despesa"), 2)
        ha_dep = custos_operacionais_periodo(session, fazenda_id, inicio, fim, None)
        ha_bf = custos_operacionais_periodo(session, fazenda_id, inicio, fim, None, **sim)
        _linha("custos", periodo, "custo_hectare.numerador", ha_antes, ha_dep["despesas_total"], ha_bf["despesas_total"])
        _linha("custos", periodo, "custo_hectare.cot", ha_antes, ha_dep["cot"], ha_bf["cot"])
        vaca_antes = _despesas_periodo(session, inicio, fim, centro_custo_vaca, fazenda_id=fazenda_id)
        vaca_dep = custos_operacionais_periodo(session, fazenda_id, inicio, fim, centro_custo_vaca)
        vaca_bf = custos_operacionais_periodo(session, fazenda_id, inicio, fim, centro_custo_vaca, **sim)
        _linha("custos", periodo, f"custo_vaca.numerador[{centro_custo_vaca or 'todos'}]",
               vaca_antes, vaca_dep["despesas_total"], vaca_bf["despesas_total"])
        _linha("custos", periodo, "depreciacao_periodo", 0.0, ha_dep["depreciacao_periodo"], ha_bf["depreciacao_periodo"])

        # Leite (PR 4 + PR 7): custo por litro (kg→L, desconto da nota rateado)
        # e RMCA (receita bruta; a líquida ao lado). Mês fechado nos dois.
        cl_antes = calcular_custo_litro_leite(session, fazenda_id, inicio, fim, regras_v2=False)
        cl_dep = calcular_custo_litro_leite(session, fazenda_id, inicio, fim, regras_v2=True)
        for chave in ("litros", "custo_total", "custo_por_litro"):
            _linha("leite", periodo, f"custo_litro.{chave}", cl_antes[chave], cl_dep[chave], cl_dep[chave])
        rm_antes = rmca_gerencial(session, fazenda_id, inicio, fim, cod_receita, cod_custo, regras_v2=False)
        rm_dep = rmca_gerencial(session, fazenda_id, inicio, fim, cod_receita, cod_custo, regras_v2=True)
        for chave in ("receita_leite", "custo_alimentacao", "rmca"):
            _linha("leite", periodo, f"rmca.{chave}", rm_antes[chave], rm_dep[chave], rm_dep[chave])
        _linha("leite", periodo, "rmca.receita_leite_liquida", rm_antes["receita_leite"],
               rm_dep["receita_leite_liquida"], rm_dep["receita_leite_liquida"])

    # Safras que tocam o intervalo (uma linha por safra, período da própria safra).
    inicio_total, fim_total = _meses(de, ate)[0][0], _meses(de, ate)[-1][1]
    for safra in session.exec(select(Safra).where(Safra.fazenda_id == fazenda_id)).all():
        if not safra.data_inicio or not safra.data_fim or safra.data_fim < inicio_total or safra.data_inicio > fim_total:
            continue
        filtradas, valores = _periodo_filtradas_dre(session, safra.data_inicio, safra.data_fim, safra.centro_custo, "competencia", fazenda_id)
        s_antes = round(sum(valores.get(c.id, 0.0) for c in filtradas if c.tipo == "despesa"), 2)
        s_dep = custos_operacionais_periodo(session, fazenda_id, safra.data_inicio, safra.data_fim, safra.centro_custo)
        s_bf = custos_operacionais_periodo(session, fazenda_id, safra.data_inicio, safra.data_fim, safra.centro_custo, **sim)
        _linha("custos", f"{safra.data_inicio:%Y-%m}..{safra.data_fim:%Y-%m}", f"custo_safra[{safra.nome}].numerador",
               s_antes, s_dep["despesas_total"], s_bf["despesas_total"])

    return {"linhas": linhas, "lancamentos": lancamentos, "plano_backfill": plano_bf}


def executar(engine, fazenda_id: int, de: str, ate: str, csv_saida: str, csv_lancamentos: str | None = None) -> dict:
    with engine.connect() as conn:
        _abrir_somente_leitura(conn)
        with Session(bind=conn) as session:
            try:
                resultado = gerar(session, fazenda_id, de, ate)
            finally:
                session.rollback()
    with open(csv_saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, delimiter=";")
        w.writeheader()
        w.writerows(resultado["linhas"])
    if csv_lancamentos:
        with open(csv_lancamentos, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=COLUNAS_LANC, delimiter=";")
            w.writeheader()
            w.writerows(resultado["lancamentos"])
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fazenda", type=int, required=True)
    parser.add_argument("--de", required=True, help="AAAA-MM")
    parser.add_argument("--ate", required=True, help="AAAA-MM")
    parser.add_argument("--csv", required=True, help="CSV das métricas (antes/depois/Δ)")
    parser.add_argument("--csv-lancamentos", help="CSV dos lançamentos que mudam de lugar, com o motivo")
    args = parser.parse_args(argv)

    from fazenda.database import engine

    print(f"Banco (somente leitura): {engine.url.render_as_string(hide_password=True)}")
    resultado = executar(engine, args.fazenda, args.de, args.ate, args.csv, args.csv_lancamentos)
    mudam = [m for m in resultado["linhas"] if m["delta"] or m["delta_com_backfill"]]
    print(f"{len(resultado['linhas'])} métrica(s), {len(mudam)} com diferença. CSV: {args.csv}")
    if args.csv_lancamentos:
        print(f"{len(resultado['lancamentos'])} registro(s) mudam de lugar. CSV: {args.csv_lancamentos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
