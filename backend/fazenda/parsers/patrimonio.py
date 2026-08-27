"""
Parser da LISTA_DE_PATRIMONIO.csv — registro de bens/imobilizado da fazenda.
Colunas: Tipo patr.; Nome Patr.; Nº patr.; Ativ. cul.; Placa; Dt. imob.;
Mét. depr.; Vd. útil; Vlr. res.; Quant.; Uni.; Vlr. tot.; Dt. baixa pat.
"""
from __future__ import annotations

from fazenda.models import Patrimonio
from fazenda.parsers.utils import iter_csv_rows, parse_date, parse_float
from fazenda.rules.patrimonio import eh_tipo_nao_depreciavel


def _get(row: dict, *chaves: str) -> str:
    for c in chaves:
        for k, v in row.items():
            if k.strip().lower().startswith(c.lower()):
                return v
    return ""


def parse_patrimonio(content: bytes) -> list[Patrimonio]:
    itens: list[Patrimonio] = []
    for row in iter_csv_rows(content):
        nome = _get(row, "Nome Patr", "Nome").strip()
        if not nome:
            continue
        tipo = _get(row, "Tipo patr", "Tipo").strip() or None
        itens.append(Patrimonio(
            tipo=tipo,
            nome=nome,
            numero=(_get(row, "N° patr", "Nº patr", "N. patr").strip() or None),
            atividade_cultura=(_get(row, "Ativ. cul", "Ativ cul").strip() or None),
            data_imobilizacao=parse_date(_get(row, "Dt. imob", "Dt imob")),
            metodo_depreciacao=(_get(row, "Mét. depr", "Met. depr", "Metodo depr").strip() or None),
            vida_util=(_get(row, "Vd. útil", "Vd util", "Vida util").strip() or None),
            valor_residual=parse_float(_get(row, "Vlr. res", "Vlr res")),
            quantidade=parse_float(_get(row, "Quant")),
            unidade=(_get(row, "Uni.", "Unidade").strip() or None),
            valor_total=parse_float(_get(row, "Vlr. tot", "Vlr tot")),
            data_baixa=parse_date(_get(row, "Dt. baixa", "Dt baixa")),
            # O CSV não traz uma coluna de depreciabilidade — sem isto, TODO
            # item (inclusive Terra) nascia com o default True do model e
            # entrava no cálculo de depreciação normal, disparando a
            # inconsistência de "vida útil não reconhecida" pra terra (que
            # nunca tem vida útil cadastrada, porque não deprecia). Ver
            # `eh_tipo_nao_depreciavel` para o porquê contábil.
            depreciavel=not eh_tipo_nao_depreciavel(tipo),
        ))
    return itens
