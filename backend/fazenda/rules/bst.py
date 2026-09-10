"""
Regra BST (Lactotropin / Boostin) — hormônio de suporte à lactação.

Critérios para receber BST (limites editáveis em Configurações > Parâmetros):
  1. Animal em lactação — grupos 01, 02 ou 03
  2. DEL ≥ del_minimo_bst (padrão 60 dias)
  3. Dias até a secagem > dias_antes_secagem_bst (padrão 15 dias — não seca em breve)
  4. Aplicação a cada intervalo_bst dias (padrão 12 — ver `agenda_engine.py`)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fazenda.rules.parametros import del_minimo_bst, dias_antes_secagem_bst

GRUPOS_LACTACAO = frozenset(["01", "02", "03"])


def _extrair_numero_grupo(grupo: str) -> str:
    """Extrai o número (2 dígitos) de um nome de grupo como '01 - NOV. ALTA'."""
    return grupo.strip().split(" ")[0] if grupo else ""


@dataclass
class ResultadoBST:
    numero_matriz: str
    elegivel: bool
    del_dias: int | None
    grupo: str | None
    dias_para_secar: int | None
    motivo_exclusao: str | None = None
    proxima_dose: date | None = None
    # DEL de exibição — independentes do `del_dias` acima (que em alguns
    # chamadores já vem projetado, pois é o valor usado no CRITÉRIO de
    # elegibilidade). `del_atual` é sempre o DEL de hoje; `del_projetado` é o
    # DEL que o animal terá na data da PRÓXIMA aplicação de BST agendada
    # (`proxima_visita_bst`). Ambos None quando não há como calcular (sem
    # último parto ou sem próxima aplicação agendada) — ver `agenda_engine.py`.
    del_atual: int | None = None
    del_projetado: int | None = None


def avaliar_bst(
    numero_matriz: str,
    grupo_primario: str | None,
    del_dias: int | None,
    data_secagem: date | None,
    data_referencia: date | None = None,
    del_atual: int | None = None,
    del_projetado: int | None = None,
    codigos_lactacao: frozenset[str] | set[str] | None = None,
) -> ResultadoBST:
    """
    Avalia se um animal é elegível para receber BST.

    Args:
        numero_matriz: Identificador do animal.
        grupo_primario: Grupo atual do animal (ex. '01 - NOV. ALTA').
        del_dias: Dias em lactação (DEL) usado no critério de elegibilidade —
            pode já vir projetado para a próxima aplicação, conforme o chamador.
        data_secagem: Data calculada de secagem (ou None se não aplica).
        data_referencia: Data de referência (default: hoje).
        del_atual: DEL de hoje, só para exibição (não entra no critério).
        del_projetado: DEL projetado para a data da próxima aplicação de BST
            agendada, só para exibição (não entra no critério).
        codigos_lactacao: Códigos de lote (2 dígitos) que contam como
            lactação — por padrão GRUPOS_LACTACAO (01/02/03), mas o chamador
            pode passar o conjunto derivado do cadastro real de Lote
            (status_lactacao == "lactacao"), pro caso de a fazenda ter
            renumerado/adicionado lotes de lactação além dos 3 históricos
            (ver mesma correção em `fazenda.rules.indicadores`).

    Returns:
        ResultadoBST com flag elegivel e motivo de exclusão se inelegível.
    """
    hoje = data_referencia or date.today()
    num_grupo = _extrair_numero_grupo(grupo_primario or "")
    del_minimo = del_minimo_bst()
    dias_antes_secagem_min = dias_antes_secagem_bst()
    grupos_lactacao = codigos_lactacao if codigos_lactacao else GRUPOS_LACTACAO

    # Critério 1: grupo de lactação
    if num_grupo not in grupos_lactacao:
        return ResultadoBST(
            numero_matriz=numero_matriz,
            elegivel=False,
            del_dias=del_dias,
            grupo=grupo_primario,
            dias_para_secar=None,
            motivo_exclusao=f"Grupo {grupo_primario!r} não é de lactação ({'/'.join(sorted(grupos_lactacao))})",
            del_atual=del_atual,
            del_projetado=del_projetado,
        )

    # Critério 2: DEL ≥ del_minimo_bst
    if del_dias is None or del_dias < del_minimo:
        return ResultadoBST(
            numero_matriz=numero_matriz,
            elegivel=False,
            del_dias=del_dias,
            grupo=grupo_primario,
            dias_para_secar=None,
            motivo_exclusao=f"DEL {del_dias} < {del_minimo} dias",
            del_atual=del_atual,
            del_projetado=del_projetado,
        )

    # Critério 3: dias até secar > dias_antes_secagem_bst
    dias_para_secar: int | None = None
    if data_secagem is not None:
        dias_para_secar = (data_secagem - hoje).days
        if dias_para_secar <= dias_antes_secagem_min:
            return ResultadoBST(
                numero_matriz=numero_matriz,
                elegivel=False,
                del_dias=del_dias,
                grupo=grupo_primario,
                dias_para_secar=dias_para_secar,
                motivo_exclusao=f"Faltam apenas {dias_para_secar} dias para secar (mínimo {dias_antes_secagem_min})",
                del_atual=del_atual,
                del_projetado=del_projetado,
            )

    return ResultadoBST(
        numero_matriz=numero_matriz,
        elegivel=True,
        del_dias=del_dias,
        grupo=grupo_primario,
        dias_para_secar=dias_para_secar,
        motivo_exclusao=None,
        del_atual=del_atual,
        del_projetado=del_projetado,
    )
