"""
Descarte previsto na Agenda (AgendaEngine, bloco "5e").

`Animal.descarte_previsto_em` é a data em que se PRETENDE tirar o animal do
rebanho — distinta de `a_descartar_em`, que é quando se DECIDIU. Sem entrar na
Agenda, a previsão ficava só guardada no cadastro: ninguém era lembrado quando
ela chegava, e o animal seguia comendo.

O caso que mais importa aqui é o VENCIDO. `AgendaItem.cor` é por CATEGORIA, não
por atraso — a Agenda não tem mecanismo de "vencido". Se o evento ficasse na
data original, ele sumiria da lista exatamente quando passa a importar, que é o
oposto de um lembrete. Por isso a previsão vencida é reancorada em HOJE e
continua aparecendo todo dia até a baixa ser lançada.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.agenda_engine import DIAS_HORIZONTE_DESCARTE, AgendaEngine

HOJE = date(2026, 8, 20)


def _animal(**kw) -> dict:
    base = {
        "numero": "900", "raca": "Holandês", "grupo_primario": "02 - Alta",
        "ativo": True, "sexo": "F", "eh_semen": False, "del_dias": 100,
        "a_descartar": True, "a_descartar_em": HOJE - timedelta(days=5),
        "descarte_previsto_em": None,
    }
    return {**base, **kw}


def _eventos_descarte(animais: list[dict]) -> list:
    r = AgendaEngine().calcular(
        data_referencia=HOJE, animais=animais, servicos=[], partos=[],
        estoque=[], contas=[], eventos_manuais=[],
    )
    return [e for e in r.eventos if "escarte" in e.descricao]


class TestDescartePrevistoNaAgenda:
    def test_previsao_futura_vira_evento_na_propria_data(self):
        prevista = HOJE + timedelta(days=10)
        eventos = _eventos_descarte([_animal(descarte_previsto_em=prevista)])
        assert len(eventos) == 1
        assert eventos[0].data == prevista
        assert eventos[0].numero_animal == "900"
        assert "VENCIDO" not in eventos[0].descricao

    def test_sem_previsao_nao_gera_evento(self):
        """Ficar em branco é estado legítimo, não pendência — não pode virar
        tarefa nem cobrança."""
        assert _eventos_descarte([_animal(descarte_previsto_em=None)]) == []

    def test_previsao_vencida_reancora_em_hoje_e_diz_desde_quando(self):
        """O teste central: a data passou e o animal continua no rebanho. O
        evento NÃO pode sumir — reaparece hoje, dizendo para quando estava
        previsto, até alguém lançar a baixa."""
        prevista = HOJE - timedelta(days=12)
        eventos = _eventos_descarte([_animal(descarte_previsto_em=prevista)])
        assert len(eventos) == 1
        assert eventos[0].data == HOJE, "evento vencido tem de reaparecer hoje, não ficar na data original"
        assert "VENCIDO" in eventos[0].descricao
        assert "08/08/2026" in eventos[0].descricao

    def test_animal_baixado_para_de_cobrar(self):
        """Quando a baixa é lançada o animal deixa de ser `ativo` e o evento
        some sozinho — sem estado extra para manter em dia."""
        prevista = HOJE - timedelta(days=12)
        eventos = _eventos_descarte([_animal(descarte_previsto_em=prevista, ativo=False)])
        assert eventos == []

    def test_previsao_sem_marcacao_de_descarte_nao_gera_evento(self):
        """Previsão órfã (marcação revertida sem limpar a data) não pode virar
        cobrança de um descarte que foi cancelado. O endpoint limpa as duas
        datas ao desmarcar; isto é a defesa em profundidade."""
        eventos = _eventos_descarte([
            _animal(a_descartar=False, a_descartar_em=None, descarte_previsto_em=HOJE + timedelta(days=5)),
        ])
        assert eventos == []

    def test_previsao_muito_distante_fica_fora_do_horizonte(self):
        """Descarte marcado para daqui a meio ano não polui a agenda de hoje.
        Entra quando chegar perto (ver DIAS_HORIZONTE_DESCARTE)."""
        longe = HOJE + timedelta(days=DIAS_HORIZONTE_DESCARTE + 1)
        assert _eventos_descarte([_animal(descarte_previsto_em=longe)]) == []

        perto = HOJE + timedelta(days=DIAS_HORIZONTE_DESCARTE)
        assert len(_eventos_descarte([_animal(descarte_previsto_em=perto)])) == 1

    def test_varios_animais_geram_um_evento_cada(self):
        eventos = _eventos_descarte([
            _animal(numero="900", descarte_previsto_em=HOJE + timedelta(days=3)),
            _animal(numero="901", descarte_previsto_em=HOJE - timedelta(days=3)),
            _animal(numero="902", descarte_previsto_em=None),
        ])
        assert {e.numero_animal for e in eventos} == {"900", "901"}
