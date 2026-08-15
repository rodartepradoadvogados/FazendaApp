"""Repro dos bugs relatados pelo usuário (ago/2026): previsão de secagem e
projeção de DEL do BST usavam `Animal.del_dias`, congelado no valor do
último GERAL.csv — nunca atualizado por um Parto/Secagem lançado no app.

Chama `AgendaEngine.calcular` diretamente, sem passar pelo router HTTP —
mesmo padrão de `test_repro_secagem_divergencia.py`.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.agenda_engine import AgendaEngine
from fazenda.rules.gestation import calcular_parto_provavel
from fazenda.rules.parametros import periodo_seco_dias


def _eventos_secagem(resultado, numero="900"):
    return [e for e in resultado.eventos if e.numero_animal == numero and "Secagem" in e.descricao]


def _eventos_pre_parto(resultado, numero="900"):
    return [e for e in resultado.eventos if e.numero_animal == numero and e.descricao == "Pré-parto"]


class TestSecagemDelAoVivo:
    def test_vaca_parida_pelo_app_sem_reimport_de_csv_entra_para_secar(self):
        """`Animal.del_dias` é zerado no instante do parto (registrar_parto) e
        fica congelado dali em diante — só volta a bater com a realidade no
        próximo GERAL.csv. Uma fazenda que não reimporta o CSV toda semana
        tem `del_dias=0` congelado meses depois de um parto real lançado no
        app; sem o DEL ao vivo, `em_lactacao` batia False pra sempre e a
        secagem prevista da PRÓXIMA prenhez nunca era gerada."""
        hoje = date.today()
        data_parto = hoje - timedelta(days=220)  # pariu há 220 dias — del_dias real seria 220, não 0
        data_servico = data_parto + timedelta(days=30)  # nova IA 30 dias pós-parto, diagnosticada prenhe
        animal = {
            "numero": "900", "raca": "Holandês", "del_dias": 0, "grupo_primario": "02 - Alta",
            "ativo": True, "sexo": "F", "eh_semen": False, "sit_rep": "Ges.",
        }
        servico = {"numero_matriz": "900", "data_servico": data_servico, "diagnostico": "POSITIVO", "ordem_parto": 2, "ult_ocorrencia": 1}
        parto = {"numero_matriz": "900", "data_parto": data_parto, "ordem_parto": 1}

        resultado = AgendaEngine().calcular(
            data_referencia=hoje, animais=[animal], servicos=[servico], partos=[parto],
            estoque=[], contas=[], eventos_manuais=[],
        )
        assert len(_eventos_secagem(resultado)) == 1, "Vaca em lactação (parto lançado no app) deveria entrar para secar"

    def test_vaca_ja_secada_pelo_app_nao_continua_pedindo_secagem(self):
        """Uma Secagem lançada no app depois do último parto marca o animal
        como seco AO VIVO — sem isso, `del_dias` congelado continuava > 0 e a
        vaca nunca saía da lista de secagem, mesmo já seca de verdade."""
        hoje = date.today()
        data_servico = hoje - timedelta(days=200)
        animal = {
            "numero": "900", "raca": "Holandês", "del_dias": 220, "grupo_primario": "02 - Alta",
            "ativo": True, "sexo": "F", "eh_semen": False, "sit_rep": "Ges.",
        }
        servico = {"numero_matriz": "900", "data_servico": data_servico, "diagnostico": "POSITIVO", "ordem_parto": 2, "ult_ocorrencia": 1}
        data_parto = hoje - timedelta(days=250)
        parto = {"numero_matriz": "900", "data_parto": data_parto, "ordem_parto": 1}
        secagem = {"numero_matriz": "900", "data_secagem": hoje - timedelta(days=2)}  # secada ontem/anteontem

        resultado = AgendaEngine().calcular(
            data_referencia=hoje, animais=[animal], servicos=[servico], partos=[parto],
            estoque=[], contas=[], eventos_manuais=[], secagens=[secagem],
        )
        assert not _eventos_secagem(resultado), "Vaca já secada pelo app não deveria continuar pedindo secagem"

    def test_secagem_atrasada_continua_aparecendo_na_agenda(self):
        """Antes, uma secagem cuja data já passou (`data_secagem < data_referencia`)
        simplesmente sumia da Agenda — sem indicação nenhuma de que alguém
        precisa agir. Agora continua aparecendo (cai em "Atrasados" no front,
        que filtra por `data < hoje`)."""
        hoje = date.today()
        raca = "Holandês"
        # Serviço datado para a secagem prevista cair 10 dias no passado.
        seco = periodo_seco_dias()
        res_gest_alvo = calcular_parto_provavel(hoje - timedelta(days=1), raca)  # só pra achar dias_gestacao
        dias_gestacao_total = res_gest_alvo.dias_gestacao
        data_secagem_alvo = hoje - timedelta(days=10)
        data_parto_provavel_alvo = data_secagem_alvo + timedelta(days=seco)
        data_servico = data_parto_provavel_alvo - timedelta(days=dias_gestacao_total)

        animal = {
            "numero": "900", "raca": raca, "del_dias": 0, "grupo_primario": "02 - Alta",
            "ativo": True, "sexo": "F", "eh_semen": False, "sit_rep": "Ges.",
        }
        servico = {"numero_matriz": "900", "data_servico": data_servico, "diagnostico": "POSITIVO", "ordem_parto": 2, "ult_ocorrencia": 1}
        parto = {"numero_matriz": "900", "data_parto": data_servico - timedelta(days=30), "ordem_parto": 1}

        resultado = AgendaEngine().calcular(
            data_referencia=hoje, animais=[animal], servicos=[servico], partos=[parto],
            estoque=[], contas=[], eventos_manuais=[],
        )
        eventos = _eventos_secagem(resultado)
        assert len(eventos) == 1, "Secagem vencida deveria continuar aparecendo na Agenda"
        assert eventos[0].data < hoje

    def test_pre_parto_atrasado_continua_aparecendo_na_agenda(self):
        """Mesmo bug do teste acima, mas para o card 'Pré-parto'."""
        hoje = date.today()
        raca = "Holandês"
        from fazenda.rules.parametros import pre_parto_max
        pmax = pre_parto_max()
        data_pre_parto_alvo = hoje - timedelta(days=5)  # já vencido
        data_parto_provavel_alvo = data_pre_parto_alvo + timedelta(days=pmax)
        res_gest_alvo = calcular_parto_provavel(hoje, raca)
        data_servico = data_parto_provavel_alvo - timedelta(days=res_gest_alvo.dias_gestacao)

        animal = {
            "numero": "900", "raca": raca, "del_dias": 0, "grupo_primario": "01 - Sem lote",
            "ativo": True, "sexo": "F", "eh_semen": False, "sit_rep": "Ges.",
        }
        servico = {"numero_matriz": "900", "data_servico": data_servico, "diagnostico": "POSITIVO", "ordem_parto": 1, "ult_ocorrencia": 1}

        resultado = AgendaEngine().calcular(
            data_referencia=hoje, animais=[animal], servicos=[servico], partos=[],
            estoque=[], contas=[], eventos_manuais=[],
        )
        eventos = _eventos_pre_parto(resultado)
        assert len(eventos) == 1, "Pré-parto vencido deveria continuar aparecendo na Agenda"
        assert eventos[0].data < hoje


class TestBstDelAoVivo:
    def test_del_atual_bst_usa_parto_lancado_no_app_nao_del_dias_congelado(self):
        """`Animal.del_dias` congelado em 0 (valor de antes do parto, só
        atualizado no próximo GERAL.csv) não deveria continuar valendo depois
        de um parto real lançado no app — o DEL atual do BST precisa refletir
        os dias reais desde esse parto."""
        hoje = date.today()
        animal = {
            "numero": "900", "raca": "Holandês", "del_dias": 0, "grupo_primario": "01 - Alta",
            "ativo": True, "sexo": "F", "eh_semen": False, "sit_rep": "",
            "excluir_bst": False, "aguardando_nova_aplicacao_bst": False,
        }
        parto = {"numero_matriz": "900", "data_parto": hoje - timedelta(days=65), "ordem_parto": 2}

        resultado = AgendaEngine().calcular(
            data_referencia=hoje, animais=[animal], servicos=[], partos=[parto],
            estoque=[], contas=[], eventos_manuais=[],
        )
        todos_bst = resultado.bst_elegiveis + resultado.bst_excluidos
        alvo = next((b for b in todos_bst if b.numero_matriz == "900"), None)
        assert alvo is not None, "Animal 900 deveria aparecer em bst_elegiveis ou bst_excluidos"
        assert alvo.del_atual == 65, f"DEL atual deveria ser 65 (dias reais desde o parto), veio {alvo.del_atual}"
