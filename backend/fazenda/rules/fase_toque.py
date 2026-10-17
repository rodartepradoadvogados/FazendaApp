"""
Fase do ciclo de diagnóstico — a tocar / a reconfirmar / reconfirmada — e o prazo "AINDA NÃO".

Uma regra só, lida por todas as telas que falam em toque e retoque (Agenda Reprodutiva, cards configuráveis, o
lançamento de diagnóstico e as exportações). Antes cada uma classificava por conta própria e elas divergiam: o card
"Gestantes" conta qualquer 1º toque positivo (`estado_reprodutivo`), enquanto a agenda do veterinário só considera
gestante a vaca já reconfirmada (`agenda_veterinario`).

Definição (vale para quem está INSEMINADA ou GESTANTE; qualquer outro estado não tem fase):

  a_tocar        INSEMINADA: serviço vigente sem diagnóstico, inclusive o de toque INDEFINIDO (volta para novo toque).
  a_reconfirmar  GESTANTE por 1º toque positivo ainda sem reconfirmação: marcado para retoque (`retoque=True`) ou, sem
                 marca nenhuma (dado importado do Ideagri), vaca — a novilha dispensa o 2º toque nesta fazenda.
  reconfirmada   reconfirmação positiva lançada, reconfirmada direto no lançamento (`retoque=False`) ou novilha com
                 toque positivo sem marca de retoque.

"AINDA NÃO" = o animal ainda está dentro do prazo de espera, calculado com os parâmetros da fazenda, nunca com o
intervalo entre visitas reprodutivas:
  a_tocar        faltam `dias_toque - dias_desde_o_servico` dias (Parâmetros › Dias para toque);
  a_reconfirmar  faltam `dias_toque + dias_reconfirmacao - dias_desde_o_servico` dias (mesma conta de
                 `relatorios_gerenciais`: a reconfirmação vence aos dias_toque + dias_reconfirmacao da inseminação).
Ele só informa: nunca impede o lançamento.
"""
from __future__ import annotations

from fazenda.rules.estado_reprodutivo import GESTANTE, INSEMINADA

A_TOCAR = "a_tocar"
A_RECONFIRMAR = "a_reconfirmar"
RECONFIRMADA = "reconfirmada"
FASES = (A_TOCAR, A_RECONFIRMAR, RECONFIRMADA)

ROTULOS = {A_TOCAR: "A tocar", A_RECONFIRMAR: "A reconfirmar", RECONFIRMADA: "Reconfirmada"}

_POSITIVO = "POSITIVO"


def _sem_fase() -> dict:
    return {"fase": None, "ainda_nao": False, "dias_para_prazo": None, "prazo_tipo": None}


def classificar_fase(
    estado: dict, *, eh_vaca: bool, dias_toque: int, dias_reconfirmacao: int,
) -> dict:
    """`estado` é o dict de `estado_reprodutivo.classificar_animal` (com os campos de diagnóstico do serviço vigente).

    Devolve `{fase, ainda_nao, dias_para_prazo, prazo_tipo}`; `dias_para_prazo` é o que falta (> 0) quando ainda_nao,
    senão None; `prazo_tipo` é "toque" ou "reconfirmacao"."""
    situacao = estado.get("estado")
    dias_ia = estado.get("dias_desde_servico")

    def _prazo(total: int, tipo: str) -> dict:
        faltam = total - dias_ia if dias_ia is not None else None
        ainda = faltam is not None and faltam > 0
        return {"ainda_nao": ainda, "dias_para_prazo": faltam if ainda else None, "prazo_tipo": tipo}

    if situacao == INSEMINADA:
        return {"fase": A_TOCAR, **_prazo(dias_toque, "toque")}

    if situacao == GESTANTE:
        reconf = (estado.get("diagnostico_reconfirmacao") or "").strip().upper()
        if reconf == _POSITIVO:
            return {"fase": RECONFIRMADA, "ainda_nao": False, "dias_para_prazo": None, "prazo_tipo": None}
        retoque = estado.get("retoque")
        if retoque is True or (retoque is None and eh_vaca):
            return {"fase": A_RECONFIRMAR, **_prazo(dias_toque + dias_reconfirmacao, "reconfirmacao")}
        return {"fase": RECONFIRMADA, "ainda_nao": False, "dias_para_prazo": None, "prazo_tipo": None}

    return _sem_fase()
