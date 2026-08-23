"""
Card "Visita reprodutiva" na Agenda (AgendaEngine).

Antes desta entrega, `proxima_visita_iatf` só existia como dado de referência
(texto discreto no rodapé da Agenda) — não havia nenhum item na lista de
eventos para o funcionário se organizar. Ver `fazenda.rules.parametros.
intervalo_visita_reprodutiva` (grupo "manejo", padrão 21 dias).
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.agenda_engine import AgendaEngine

HOJE = date(2026, 8, 20)


def _eventos_visita(resultado):
    return [e for e in resultado.eventos if "Visita reprodutiva" in e.descricao]


class TestVisitaReprodutivaNaAgenda:
    def test_gera_card_na_data_da_proxima_visita(self):
        ultimo_servico = HOJE - timedelta(days=5)
        servico = {"numero_matriz": "900", "data_servico": ultimo_servico, "ult_ocorrencia": 1}
        resultado = AgendaEngine().calcular(
            data_referencia=HOJE, animais=[], servicos=[servico], partos=[],
            estoque=[], contas=[], eventos_manuais=[],
        )
        eventos = _eventos_visita(resultado)
        assert len(eventos) == 1
        assert eventos[0].data == resultado.proxima_visita_iatf
        assert eventos[0].categoria == "Reprodutivo"
        assert eventos[0].numero_animal is None, "evento é do rebanho, não de um animal específico"

    def test_visita_vencida_continua_aparecendo(self):
        """Mesmo racional do Pré-parto/Secagem: sem novo serviço lançado, a
        data prevista fica no passado e o card precisa continuar visível
        (cai em 'Atrasados' no front) até a visita realmente acontecer."""
        ultimo_servico = HOJE - timedelta(days=40)  # bem além dos 21 dias padrão
        servico = {"numero_matriz": "900", "data_servico": ultimo_servico, "ult_ocorrencia": 1}
        resultado = AgendaEngine().calcular(
            data_referencia=HOJE, animais=[], servicos=[servico], partos=[],
            estoque=[], contas=[], eventos_manuais=[],
        )
        eventos = _eventos_visita(resultado)
        assert len(eventos) == 1
        assert eventos[0].data < HOJE

    def test_sem_servico_nenhum_nao_gera_card(self):
        resultado = AgendaEngine().calcular(
            data_referencia=HOJE, animais=[], servicos=[], partos=[],
            estoque=[], contas=[], eventos_manuais=[],
        )
        assert resultado.proxima_visita_iatf is None
        assert _eventos_visita(resultado) == []
