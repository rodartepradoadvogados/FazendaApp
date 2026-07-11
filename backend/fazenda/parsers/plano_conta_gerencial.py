"""
Parser da LISTA_DE_PLANO_DE_CONTAS_GERENCIAIS.csv — hierarquia do plano de
contas usado para classificar os lançamentos financeiros.
Colunas: Nº ct. ger.; Nome ct. ger.; Ativa; Part. ativ.; Fluxo; Tipo F/V.
"""
from __future__ import annotations

from fazenda.models import PlanoContaGerencial
from fazenda.parsers.utils import iter_csv_rows, parse_bool


def _get(row: dict, *chaves: str) -> str:
    for c in chaves:
        for k, v in row.items():
            if k.strip().lower().startswith(c.lower()):
                return v
    return ""


def parse_plano_conta_gerencial(content: bytes) -> list[PlanoContaGerencial]:
    contas: list[PlanoContaGerencial] = []
    for row in iter_csv_rows(content):
        codigo = _get(row, "N° ct", "N. ct", "Nº ct", "Codigo", "Código").strip()
        nome = _get(row, "Nome ct", "Nome").strip()
        if not codigo or not nome:
            continue
        contas.append(PlanoContaGerencial(
            codigo=codigo,
            nome=nome,
            # Por decisão do usuário, toda conta gerencial nasce ATIVA — a
            # seleção do lançamento é feita apenas nas contas-folha (nível mais
            # baixo), então "ativa" passou a ser só um liga/desliga de exibição
            # ajustável em Configurações, não mais o que define o que aparece.
            ativa=True,
            participa_atividade=parse_bool(_get(row, "Part. ativ", "Part ativ")),
            fluxo=parse_bool(_get(row, "Fluxo")),
            tipo_fixo_variavel=(_get(row, "Tipo F/V", "Tipo F V").strip() or None),
            # Todo item de "3.01.01 - Alimentação do rebanho" já entra marcado
            # como custo de alimentação para o indicador RMCA.
            rmca_custo_alimentacao=True if codigo.startswith("3.01.01") else None,
        ))
    return contas
