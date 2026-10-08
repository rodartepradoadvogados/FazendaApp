"""DRE/custos não contam duas vezes o restante reparcelado numa baixa parcial."""
from types import SimpleNamespace

from fazenda.rules.vale_item import valor_gerencial


def _conta(id_, valor_total, valor_pago=None, desconto=None):
    return SimpleNamespace(id=id_, valor_total=valor_total, valor_pago=valor_pago, desconto_acrescimo=desconto)


def test_baixa_parcial_vale_o_que_foi_pago_e_a_soma_com_a_parcela_nova_fecha_na_nota():
    paga = _conta(1, 1000.0, 600.0, 0.0)
    resto = _conta(2, 400.0)
    assert valor_gerencial(paga, {}) == 600.0
    assert valor_gerencial(paga, {}) + valor_gerencial(resto, {}) == 1000.0


def test_desconto_e_acrescimo_continuam_como_antes():
    assert valor_gerencial(_conta(1, 1000.0, 900.0, -100.0), {}) == 1000.0
    assert valor_gerencial(_conta(2, 1000.0, 1100.0, 100.0), {}) == 1000.0


def test_em_aberto_e_pago_cheio_nao_mudam_e_ajuste_de_vale_ainda_abate():
    assert valor_gerencial(_conta(1, 500.0), {}) == 500.0
    assert valor_gerencial(_conta(2, 500.0, 500.0, 0.0), {}) == 500.0
    assert valor_gerencial(_conta(3, 1000.0, 600.0, 0.0), {3: 100.0}) == 500.0
