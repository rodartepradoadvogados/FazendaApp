"""Regras puras de fazenda.rules.cotacao — sem banco, sem HTTP."""
from fazenda.rules.cotacao import (
    STATUS_CANCELADA,
    STATUS_COMPARADA,
    STATUS_ENVIADA,
    STATUS_PARCIALMENTE_RESPONDIDA,
    STATUS_RASCUNHO,
    STATUS_RESPONDIDA,
    calcular_status_resposta,
    montar_mensagem_cotacao,
    montar_mensagem_pedido_formal,
)


def _f(status_envio):
    return {"status_envio": status_envio}


class TestCalcularStatusResposta:
    def test_sem_fornecedores_fica_rascunho(self):
        assert calcular_status_resposta(STATUS_RASCUNHO, []) == STATUS_RASCUNHO

    def test_nenhum_respondeu_fica_enviada(self):
        fornecedores = [_f("enviado"), _f("visualizado")]
        assert calcular_status_resposta(STATUS_ENVIADA, fornecedores) == STATUS_ENVIADA

    def test_alguns_responderam_fica_parcialmente_respondida(self):
        fornecedores = [_f("respondido"), _f("enviado"), _f("visualizado")]
        assert calcular_status_resposta(STATUS_ENVIADA, fornecedores) == STATUS_PARCIALMENTE_RESPONDIDA

    def test_recusado_conta_como_respondido(self):
        fornecedores = [_f("respondido"), _f("recusado")]
        assert calcular_status_resposta(STATUS_ENVIADA, fornecedores) == STATUS_RESPONDIDA

    def test_todos_responderam_fica_respondida(self):
        fornecedores = [_f("respondido"), _f("respondido")]
        assert calcular_status_resposta(STATUS_ENVIADA, fornecedores) == STATUS_RESPONDIDA

    def test_status_terminal_nunca_recalcula(self):
        # Uma resposta atrasada chegando não deve tirar a cotação de
        # "comparada"/"pedidos_gerados"/"cancelada"/"expirada".
        fornecedores = [_f("enviado")]
        for terminal in (STATUS_COMPARADA, "pedidos_gerados", "expirada", STATUS_CANCELADA):
            assert calcular_status_resposta(terminal, fornecedores) == terminal


class TestMensagensPadrao:
    def test_mensagem_cotacao_carrega_fazenda_e_link(self):
        msg = montar_mensagem_cotacao("Fazenda Estreito Ponte de Pedra", "https://x/y")
        assert "Fazenda Estreito Ponte de Pedra" in msg
        assert "https://x/y" in msg

    def test_mensagem_pedido_formal_carrega_numero_do_pedido(self):
        msg = montar_mensagem_pedido_formal("Fazenda Estreito Ponte de Pedra", "PED-2026-00001", "https://x/y")
        assert "PED-2026-00001" in msg
        assert "https://x/y" in msg
