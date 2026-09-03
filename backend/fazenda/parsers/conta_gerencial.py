"""
Parser do CONTA_GERENCIAL.csv — movimentações financeiras.
15 colunas:
  1  Conta gerencial (código hierárquico, ex. 3.01.03.01)
  2  Descrição
  3  Data venc.
  4  Data pag. / receb.
  5  Data comp.
  6  Fornecedor / cliente
  7  Nº da nota
  8  Parcela
  9  Valor total da parcela
  10 Valor parcela aprop. ct. gerencial
  11 Valor aprop. centros de custos
  12 Valor pago receb.
  13 TIPO  (1=receita, 2=despesa)
  14 Centro de custo  (PL / C|26 / ARR / …)
  15 DATAEMISSAO
"""
from __future__ import annotations

from fazenda.models import ContaGerencial
from fazenda.parsers.utils import iter_csv_rows, parse_date, parse_float
from fazenda.rules.centro_custo import mapear_centro_custo


def _parse_parcela(valor: str) -> tuple[int, int]:
    """Converte a coluna "Parcela" do Ideagri — formato "N de M" (ex.: "1 de
    3") — em (parcela_num, parcela_total).

    Sem essa conversão a linha nascia com os dois campos em None (o modelo
    ContaGerencial não tem default nenhum para eles) e o Financeiro mostrava
    "(null/1)"/"(null/2)"/... no lugar do número da parcela — ver
    `frontend/app/financeiro/page.tsx`, coluna "Nº lanç." da tabela de
    Lançamentos, que faz `(${r.parcela_num}/${r.parcela_total})` sem checar
    se parcela_num veio preenchido.

    Qualquer valor vazio ou fora do formato esperado vira (1, 1) — mesmo
    padrão usado em todo o resto do código para "lançamento sem
    parcelamento" (ver criar_lancamento, compra/venda de animal e sêmen,
    RH, comissão, etc.), nunca None."""
    partes = (valor or "").strip().lower().split(" de ")
    if len(partes) == 2:
        try:
            num, total = int(partes[0].strip()), int(partes[1].strip())
            if num >= 1 and total >= 1:
                return num, total
        except ValueError:
            pass
    return 1, 1


def parse_conta_gerencial(content: bytes) -> list[ContaGerencial]:
    contas: list[ContaGerencial] = []

    for row in iter_csv_rows(content):
        codigo = (
            row.get("Conta gerencial", "")
            or row.get("Conta Gerencial", "")
            or ""
        ).strip()

        # Ideagri exporta TIPO=1 para tudo neste relatório.
        # Determinamos receita/despesa pelo prefixo do código de conta:
        #   2.x.x.x → receita (ex. 2.01.01.01 = Leite indústria)
        #   3.x.x.x → despesa (ex. 3.01.03.01 = Alimentação)
        nivel1 = codigo.split(".")[0] if "." in codigo else ""
        if nivel1 == "2":
            tipo = "receita"
        elif nivel1 == "3":
            tipo = "despesa"
        else:
            tipo_raw = (row.get("TIPO", "") or "").strip()
            tipo = "receita" if tipo_raw == "1" else ("despesa" if tipo_raw == "2" else None)

        parcela_num, parcela_total = _parse_parcela(row.get("Parcela", ""))

        conta = ContaGerencial(
            codigo_conta=codigo or None,
            descricao=row.get("Descrição", row.get("Descricao", "")) or None,
            data_vencimento=parse_date(row.get("Data venc.", "")),
            data_pagamento=parse_date(row.get("Data pag. / receb.", "")),
            data_competencia=parse_date(row.get("Data comp.", "")),
            data_emissao=parse_date(row.get("DATAEMISSAO", "")),
            fornecedor_cliente=row.get("Fornecedor / cliente", "") or None,
            numero_nota=row.get("Nº da nota", row.get("No da nota", "")) or None,
            parcela_num=parcela_num,
            parcela_total=parcela_total,
            valor_total=parse_float(row.get("Valor total da parcela", "")),
            valor_pago=parse_float(row.get("Valor pago receb.", "")),
            centro_custo=mapear_centro_custo(row.get("Centro de custo", "") or None),
            tipo=tipo,
        )
        contas.append(conta)

    return contas
