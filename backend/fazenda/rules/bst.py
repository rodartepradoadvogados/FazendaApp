"""
Regra BST (Lactotropin / Boostin) — hormônio de suporte à lactação.

Critérios para receber BST:
  1. Animal em lactação — grupos 01, 02 ou 03
  2. DEL ≥ 60 dias
  3. Dias até a secagem > 15 dias (não seca em breve)
  4. Aplicação a cada 12 dias

Produz duas listas:
  - elegíveis: recebem BST
  - excluídos: não recebem (com motivo)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


GRUPOS_LACTACAO = frozenset(["01", "02", "03"])
DEL_MINIMO = 60
DIAS_ANTES_SECAGEM_MINIMO = 15
INTERVALO_BST = 12  # dias entre aplicações


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


def avaliar_bst(
    numero_matriz: str,
    grupo_primario: str | None,
    del_dias: int | None,
    data_secagem: date | None,
    data_referencia: date | None = None,
) -> ResultadoBST:
    """
    Avalia se um animal é elegível para receber BST.

    Args:
        numero_matriz: Identificador do animal.
        grupo_primario: Grupo atual do animal (ex. '01 - NOV. ALTA').
        del_dias: Dias em lactação (DEL).
        data_secagem: Data calculada de secagem (ou None se não aplica).
        data_referencia: Data de referência (default: hoje).

    Returns:
        ResultadoBST com flag elegivel e motivo de exclusão se inelegível.
    """
    hoje = data_referencia or date.today()
    num_grupo = _extrair_numero_grupo(grupo_primario or "")

    # Critério 1: grupo de lactação
    if num_grupo not in GRUPOS_LACTACAO:
        return ResultadoBST(
            numero_matriz=numero_matriz,
            elegivel=False,
            del_dias=del_dias,
            grupo=grupo_primario,
            dias_para_secar=None,
            motivo_exclusao=f"Grupo {grupo_primario!r} não é de lactação (01/02/03)",
        )

    # Critério 2: DEL ≥ 60
    if del_dias is None or del_dias < DEL_MINIMO:
        return ResultadoBST(
            numero_matriz=numero_matriz,
            elegivel=False,
            del_dias=del_dias,
            grupo=grupo_primario,
            dias_para_secar=None,
            motivo_exclusao=f"DEL {del_dias} < {DEL_MINIMO} dias",
        )

    # Critério 3: dias até secar > 15
    dias_para_secar: int | None = None
    if data_secagem is not None:
        dias_para_secar = (data_secagem - hoje).days
        if dias_para_secar <= DIAS_ANTES_SECAGEM_MINIMO:
            return ResultadoBST(
                numero_matriz=numero_matriz,
                elegivel=False,
                del_dias=del_dias,
                grupo=grupo_primario,
                dias_para_secar=dias_para_secar,
                motivo_exclusao=f"Faltam apenas {dias_para_secar} dias para secar (mínimo {DIAS_ANTES_SECAGEM_MINIMO})",
            )

    return ResultadoBST(
        numero_matriz=numero_matriz,
        elegivel=True,
        del_dias=del_dias,
        grupo=grupo_primario,
        dias_para_secar=dias_para_secar,
        motivo_exclusao=None,
    )
