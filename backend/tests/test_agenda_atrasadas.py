"""
Alerta proativo de "atrasada" na Agenda (AgendaEngine) — vaca que passou do
DEL máximo para o 1º serviço, ou novilha que passou do teto de idade para a
1ª cobertura, sem novo serviço. Antes desta entrega não existia nenhum alerta
para isso na Agenda do dia a dia — só era visível como lista consultável
(Rebanho, Agenda Reprodutiva). Mesmo estado ATRASADA do motor canônico
(`fazenda.rules.estado_reprodutivo`), não uma regra própria.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.agenda_engine import AgendaEngine

HOJE = date(2026, 8, 20)
DEL_MAX_PADRAO = 100          # meta_del_max_1o_servico, default
IDADE_ATRASO_DIAS_PADRAO = 487  # 16 meses, default de idade_max_1a_cobertura_meses


def _vaca(numero="900", dias_pos_parto=150, **kw):
    base = {
        "numero": numero, "categoria_abrev": "Vaca", "raca": "Holandês",
        "grupo_primario": "02 - Alta", "ativo": True, "sexo": "F", "eh_semen": False,
        "del_dias": dias_pos_parto, "a_descartar": False, "descarte_previsto_em": None,
    }
    partos = kw.pop("partos", [{"numero_matriz": numero, "data_parto": HOJE - timedelta(days=dias_pos_parto)}])
    return {**base, **kw}, partos


def _novilha(numero="901", idade_dias=500, **kw):
    base = {
        "numero": numero, "categoria_abrev": "Novilha", "raca": "Holandês",
        "grupo_primario": "03 - Recria", "ativo": True, "sexo": "F", "eh_semen": False,
        "data_nasc": HOJE - timedelta(days=idade_dias),
        "a_descartar": False, "descarte_previsto_em": None,
    }
    return {**base, **kw}


def _eventos_atrasada(animais, partos=None, servicos=None, peso_por_animal=None):
    r = AgendaEngine().calcular(
        data_referencia=HOJE, animais=animais, servicos=servicos or [], partos=partos or [],
        estoque=[], contas=[], eventos_manuais=[], peso_por_animal=peso_por_animal or {},
    )
    return [e for e in r.eventos if "atrasad" in e.descricao.lower()]


class TestVacaAtrasadaNaAgenda:
    def test_vaca_alem_do_del_maximo_sem_servico_gera_alerta(self):
        vaca, partos = _vaca(dias_pos_parto=DEL_MAX_PADRAO + 20)
        eventos = _eventos_atrasada([vaca], partos=partos)
        assert len(eventos) == 1
        assert eventos[0].numero_animal == "900"
        assert eventos[0].data == HOJE, "alerta persistente reancora em hoje, não numa data fixa passada"
        assert "150" not in eventos[0].descricao  # sanity: não é o del_dias do outro teste
        assert str(DEL_MAX_PADRAO + 20) in eventos[0].descricao

    def test_vaca_dentro_do_del_maximo_nao_gera_alerta(self):
        vaca, partos = _vaca(dias_pos_parto=DEL_MAX_PADRAO - 10)
        assert _eventos_atrasada([vaca], partos=partos) == []

    def test_vaca_com_servico_novo_nao_e_atrasada(self):
        """Servida recentemente: vira INSEMINADA, não ATRASADA — mesmo com o
        DEL alto na hora do último parto."""
        vaca, partos = _vaca(dias_pos_parto=DEL_MAX_PADRAO + 30)
        servicos = [{"numero_matriz": "900", "data_servico": HOJE - timedelta(days=5)}]
        assert _eventos_atrasada([vaca], partos=partos, servicos=servicos) == []

    def test_vaca_marcada_a_descartar_nao_gera_alerta(self):
        vaca, partos = _vaca(dias_pos_parto=DEL_MAX_PADRAO + 20, a_descartar=True)
        assert _eventos_atrasada([vaca], partos=partos) == []


class TestNovilhaAtrasadaNaAgenda:
    def test_novilha_alem_do_teto_de_idade_e_apta_vazia_gera_alerta(self):
        novilha = _novilha(idade_dias=IDADE_ATRASO_DIAS_PADRAO + 5)
        eventos = _eventos_atrasada([novilha], peso_por_animal={"901": 320.0})
        assert len(eventos) == 1
        assert eventos[0].numero_animal == "901"
        assert eventos[0].data == HOJE

    def test_novilha_dentro_da_janela_apta_nao_gera_alerta(self):
        novilha = _novilha(idade_dias=IDADE_ATRASO_DIAS_PADRAO - 5)
        assert _eventos_atrasada([novilha], peso_por_animal={"901": 320.0}) == []

    def test_novilha_ainda_nao_apta_nao_gera_alerta(self):
        """Idade baixa (impúbere): NAO_APTA, não ATRASADA — não é a mesma
        pendência e não deve poluir a agenda com ela."""
        novilha = _novilha(idade_dias=200)
        assert _eventos_atrasada([novilha], peso_por_animal={"901": 320.0}) == []
