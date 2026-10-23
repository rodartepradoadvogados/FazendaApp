"""
Conta em aberto x conta baixada — regra ÚNICA.

A baixa (`data_pagamento` preenchida) é o que quita uma conta, seja qual for o valor: pagamento integral, com
desconto, parcial com a diferença virando outra parcela, ou desconto de 100% ("paga em R$ 0,00" — decisão do dono).
Comparar só `valor_pago < valor_total` NÃO serve: uma conta paga com desconto, ou com `valor_pago` nulo/zero, continuava
"em aberto" e ficava na Agenda como atrasada (LC-2026-00290, R$ 255 com 100% de desconto, vencida em 14/10/2026).

Registro antigo sem `data_pagamento` mas com o valor pago cobrindo o total continua quitado, como sempre foi: a regra só
ACRESCENTA a baixa, não reabre nada.

Estorno da baixa limpa `data_pagamento` (ver `estornar` em api/routers/financeiro.py): a conta volta a ser aberta.
"""
from __future__ import annotations

from datetime import date


def conta_em_aberto(data_pagamento: date | None, valor_pago: float | None, valor_total: float | None) -> bool:
    """True enquanto a conta NÃO foi baixada nem coberta pelo valor pago."""
    if data_pagamento is not None:
        return False
    return (valor_pago or 0) < (valor_total or 0)
