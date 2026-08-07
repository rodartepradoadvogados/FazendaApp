"""
Regra compartilhada: quando um lançamento de protocolo sanitário "terminou"
— ou seja, todas as aplicações do ÚLTIMO DIA do cronograma já foram
efetivamente realizadas — e portanto está pronto para a pergunta
"curado? sim/não".

Usada em dois lugares que precisam concordar exatamente sobre o mesmo
critério:
  - `agenda.py`, para decidir quando o evento "Confirmar cura" aparece;
  - `sanidade.py` (`GET /taxa-cura`), para decidir quando um caso sem
    resposta entra no relatório como "não avaliado" (protocolo em
    andamento não é pendência — ainda não chegou a hora de perguntar).
"""
from __future__ import annotations

from datetime import date


def protocolo_terminado(aplicacoes: list) -> tuple[bool, date | None]:
    """Recebe as `ProtocoloSanitarioAplicacao` de UM lançamento e devolve
    `(terminou, ultimo_dia)`. `terminou` é True só quando existe pelo menos
    uma aplicação e TODAS as do último dia (`data_prevista` máxima) estão
    `realizada=True`."""
    if not aplicacoes:
        return False, None
    ultimo_dia = max(a.data_prevista for a in aplicacoes)
    aps_ultimo_dia = [a for a in aplicacoes if a.data_prevista == ultimo_dia]
    return all(a.realizada for a in aps_ultimo_dia), ultimo_dia
