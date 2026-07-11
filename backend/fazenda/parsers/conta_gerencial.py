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

        conta = ContaGerencial(
            codigo_conta=codigo or None,
            descricao=row.get("Descrição", row.get("Descricao", "")) or None,
            data_vencimento=parse_date(row.get("Data venc.", "")),
            data_pagamento=parse_date(row.get("Data pag. / receb.", "")),
            data_competencia=parse_date(row.get("Data comp.", "")),
            data_emissao=parse_date(row.get("DATAEMISSAO", "")),
            fornecedor_cliente=row.get("Fornecedor / cliente", "") or None,
            numero_nota=row.get("Nº da nota", row.get("No da nota", "")) or None,
            valor_total=parse_float(row.get("Valor total da parcela", "")),
            valor_pago=parse_float(row.get("Valor pago receb.", "")),
            centro_custo=mapear_centro_custo(row.get("Centro de custo", "") or None),
            tipo=tipo,
        )
        contas.append(conta)

    return contas
