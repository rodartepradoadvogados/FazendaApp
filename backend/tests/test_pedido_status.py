"""Status de Pedido derivado de entrega física — fazenda.rules.pedido_status."""
from __future__ import annotations

from fazenda.rules.pedido_status import (
    STATUS_ABERTO,
    STATUS_ATENDIDO,
    STATUS_CANCELADO,
    STATUS_PARCIALMENTE_ATENDIDO,
    calcular_status_pedido,
)


def _item(quantidade: float | None, quantidade_entregue: float = 0) -> dict:
    return {"quantidade": quantidade, "quantidade_entregue": quantidade_entregue}


class TestCancelado:
    def test_cancelado_permanece_cancelado_mesmo_sem_entrega(self):
        itens = [_item(10, 0)]
        assert calcular_status_pedido(itens, STATUS_CANCELADO) == STATUS_CANCELADO

    def test_cancelado_permanece_cancelado_mesmo_com_itens_100_por_cento_entregues(self):
        # Intencional: cancelamento é terminal e nunca é recalculado a
        # partir de entrega, mesmo que a entrega tenha sido marcada depois.
        itens = [_item(10, 10), _item(5, 5)]
        assert calcular_status_pedido(itens, STATUS_CANCELADO) == STATUS_CANCELADO


class TestSemItens:
    def test_lista_vazia_fica_aberto(self):
        assert calcular_status_pedido([], STATUS_ABERTO) == STATUS_ABERTO

    def test_nenhum_item_com_quantidade_valida_fica_aberto(self):
        itens = [_item(None, 0), _item(0, 0)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_ABERTO


class TestAberto:
    def test_um_item_sem_nenhuma_entrega_fica_aberto(self):
        itens = [_item(10, 0)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_ABERTO

    def test_varios_itens_sem_nenhuma_entrega_fica_aberto(self):
        itens = [_item(10, 0), _item(5, 0), _item(3, 0)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_ABERTO


class TestAtendido:
    def test_um_item_completo_fica_atendido(self):
        itens = [_item(10, 10)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_ATENDIDO

    def test_varios_itens_todos_completos_fica_atendido(self):
        itens = [_item(10, 10), _item(5, 5), _item(3, 3)]
        assert calcular_status_pedido(itens, STATUS_PARCIALMENTE_ATENDIDO) == STATUS_ATENDIDO

    def test_entrega_maior_que_quantidade_ainda_conta_como_completo(self):
        # Devolução/ajuste pode deixar quantidade_entregue > quantidade;
        # continua sendo "completo", não deve virar erro nem travar status.
        itens = [_item(10, 12)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_ATENDIDO

    def test_tolerancia_de_ponto_flutuante_conta_como_completo(self):
        itens = [_item(3.0, 2.9999999999)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_ATENDIDO

    def test_item_com_quantidade_none_nao_trava_pedido_em_atendido(self):
        # Item mal cadastrado (sem quantidade) conta como "sempre
        # satisfeito" — não deve impedir o pedido de virar atendido quando
        # todo o resto já foi entregue.
        itens = [_item(10, 10), _item(None, 0)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_ATENDIDO


class TestParcialmenteAtendido:
    def test_um_item_parcialmente_entregue_fica_parcial(self):
        itens = [_item(10, 4)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_PARCIALMENTE_ATENDIDO

    def test_um_item_completo_e_outro_pendente_fica_parcial(self):
        itens = [_item(10, 10), _item(5, 0)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_PARCIALMENTE_ATENDIDO

    def test_um_item_com_quantidade_none_nao_impede_status_parcial(self):
        itens = [_item(10, 4), _item(None, 0)]
        assert calcular_status_pedido(itens, STATUS_ABERTO) == STATUS_PARCIALMENTE_ATENDIDO
