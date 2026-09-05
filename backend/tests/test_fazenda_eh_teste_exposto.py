"""
`Fazenda.eh_teste` (ver fazenda/models/multitenant.py) precisa aparecer no
payload público da fazenda pro frontend desenhar a tarja de teste — cobre os
dois serializadores tocados: `_fazenda_publica` (fazenda/api/routers/auth.py,
usado por login/selecionar-fazenda) e `_publico` (fazenda/api/routers/
fazendas.py, usado pelo admin/painel de Fazendas).
"""
from __future__ import annotations

from fazenda.api.routers.auth import _fazenda_publica
from fazenda.api.routers.fazendas import _publico
from fazenda.models import Fazenda


class TestFazendaPublicaAuth:
    def test_expoe_eh_teste_true(self):
        f = Fazenda(id=1, nome="Fazenda Teste", eh_teste=True)
        assert _fazenda_publica(f)["eh_teste"] is True

    def test_expoe_eh_teste_false_por_padrao(self):
        f = Fazenda(id=2, nome="Jairo Nasser")
        assert _fazenda_publica(f)["eh_teste"] is False


class TestFazendaPublicaAdmin:
    def test_expoe_eh_teste_true(self):
        f = Fazenda(id=1, nome="Fazenda Teste", eh_teste=True)
        assert _publico(f)["eh_teste"] is True

    def test_expoe_eh_teste_false_por_padrao(self):
        f = Fazenda(id=2, nome="Jairo Nasser")
        assert _publico(f)["eh_teste"] is False
