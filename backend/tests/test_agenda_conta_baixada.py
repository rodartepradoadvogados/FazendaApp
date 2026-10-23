"""
LC-2026-00290: conta de R$ 255 paga com 100% de desconto (R$ 0,00), vencida em 14/10/2026, seguia na Agenda como atrasada.
Regra do dono: a BAIXA (`data_pagamento`) quita a conta, seja qual for o valor — inclusive R$ 0. O critério antigo
(`valor_pago < valor_total`) mantinha em aberto a conta paga com desconto, com `valor_pago` nulo ou zero.
"""
from __future__ import annotations

from datetime import date

import pytest

from fazenda.rules.agenda_engine import AgendaEngine
from fazenda.rules.conta_baixa import conta_em_aberto

HOJE = date(2026, 10, 23)
VENC = date(2026, 10, 14)
BAIXA = date(2026, 10, 14)


def _conta(**extra):
    return {"descricao": "teste", "data_vencimento": VENC, "tipo": "despesa", "valor_total": 255.0, "numero_lancamento": "LC-2026-00290", **extra}


@pytest.mark.parametrize("nome,extra", [
    ("paga integral", dict(valor_pago=255.0, data_pagamento=BAIXA, desconto_acrescimo=0.0)),
    ("desconto de 100% (paga em R$ 0,00)", dict(valor_pago=0.0, data_pagamento=BAIXA, desconto_acrescimo=-255.0)),
    ("desconto parcial", dict(valor_pago=200.0, data_pagamento=BAIXA, desconto_acrescimo=-55.0)),
    ("valor_pago nulo", dict(valor_pago=None, data_pagamento=BAIXA, desconto_acrescimo=-255.0)),
    ("baixa parcial, diferença virou outra parcela", dict(valor_pago=100.0, data_pagamento=BAIXA, desconto_acrescimo=0.0)),
])
def test_conta_baixada_some_da_agenda_qualquer_que_seja_o_valor(nome, extra):
    r = AgendaEngine().calcular(HOJE, [], [], [], [], [_conta(**extra)], [])
    assert r.contas_a_pagar == [], nome


def test_conta_sem_baixa_continua_na_agenda_como_atrasada():
    r = AgendaEngine().calcular(HOJE, [], [], [], [], [_conta(valor_pago=None, data_pagamento=None)], [])
    assert [c["numero_lancamento"] for c in r.contas_a_pagar] == ["LC-2026-00290"]


def test_regra_unica_conta_em_aberto():
    assert conta_em_aberto(None, None, 255.0) is True            # sem baixa
    assert conta_em_aberto(None, 200.0, 700.0) is True           # recebimento parcial sem baixa registrada
    assert conta_em_aberto(BAIXA, 0.0, 255.0) is False           # baixa em R$ 0,00 (desconto de 100%)
    assert conta_em_aberto(BAIXA, None, 255.0) is False
    assert conta_em_aberto(None, 300.0, 300.0) is False          # registro antigo: valor pago cobre o total
    assert conta_em_aberto(None, None, 0.0) is False             # conta de valor zero nunca foi "a pagar"
