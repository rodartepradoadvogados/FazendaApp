"""
A produção do painel sai dos CONTROLES LEITEIROS, não de um campo congelado.

`Animal.ult_cl_kg` tinha um único ponto de escrita em todo o backend: o parser
do GERAL.csv do Ideagri. Quem lançava controle pelo app via o card
"Produção/dia (últ. controle)" parado na data do último CSV importado, ao lado
de um gráfico que já mostrava os números novos — duas verdades na mesma tela.
Com a importação do Ideagri aposentada, o campo nunca mais seria escrito.

`ult_cl_kg` continua como fallback POR ANIMAL, para o histórico de quem só tem
o valor importado.
"""
from __future__ import annotations

from datetime import date

from fazenda.rules.indicadores import calcular_indicadores


def _animal(numero: str, **extra) -> dict:
    base = {"numero": numero, "grupo_primario": "02 - VACAS ALTA", "raca": "Girolando"}
    base.update(extra)
    return base


class TestProducaoVemDoControle:
    def test_usa_o_controle_lancado_e_ignora_o_campo_congelado(self):
        animais = [_animal("100", ult_cl_kg=10.0)]
        controles = [{"numero_matriz": "100", "producao_kg": 30.0, "data": date(2026, 8, 10)}]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 30.0

    def test_pega_o_controle_mais_recente_do_animal(self):
        animais = [_animal("100", ult_cl_kg=10.0)]
        controles = [
            {"numero_matriz": "100", "producao_kg": 22.0, "data": date(2026, 8, 1)},
            {"numero_matriz": "100", "producao_kg": 28.0, "data": date(2026, 8, 12)},
            {"numero_matriz": "100", "producao_kg": 25.0, "data": date(2026, 8, 5)},
        ]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 28.0

    def test_soma_o_rebanho_todo(self):
        animais = [_animal("100"), _animal("200"), _animal("300")]
        controles = [
            {"numero_matriz": "100", "producao_kg": 30.0, "data": date(2026, 8, 10)},
            {"numero_matriz": "200", "producao_kg": 25.0, "data": date(2026, 8, 10)},
            {"numero_matriz": "300", "producao_kg": 20.0, "data": date(2026, 8, 10)},
        ]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 75.0
        assert ind["producao"]["producao_media_kg"] == 25.0


class TestFallbackParaOHistoricoImportado:
    def test_animal_sem_controle_usa_o_campo_importado(self):
        animais = [_animal("100", ult_cl_kg=18.0)]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=[])
        assert ind["producao"]["producao_total_dia_kg"] == 18.0

    def test_sem_controles_nenhum_mantem_o_comportamento_antigo(self):
        # Chamadas que não passam `controles` (manual da fazenda, assistente)
        # continuam funcionando exatamente como antes.
        animais = [_animal("100", ult_cl_kg=18.0), _animal("200", ult_cl_kg=22.0)]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13))
        assert ind["producao"]["producao_total_dia_kg"] == 40.0

    def test_mistura_controle_novo_com_historico_importado(self):
        # 100 já lança pelo app; 200 só tem o valor que veio do CSV antigo.
        animais = [_animal("100", ult_cl_kg=10.0), _animal("200", ult_cl_kg=22.0)]
        controles = [{"numero_matriz": "100", "producao_kg": 30.0, "data": date(2026, 8, 10)}]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 52.0


class TestBordas:
    def test_controle_zerado_nao_conta(self):
        animais = [_animal("100", ult_cl_kg=15.0)]
        controles = [{"numero_matriz": "100", "producao_kg": 0.0, "data": date(2026, 8, 10)}]
        # Produção zero no controle não derruba o animal para zero: cai no
        # fallback, igual a um animal sem controle nenhum.
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 15.0

    def test_controle_de_animal_que_nao_esta_na_lista_e_ignorado(self):
        animais = [_animal("100", ult_cl_kg=15.0)]
        controles = [{"numero_matriz": "999", "producao_kg": 99.0, "data": date(2026, 8, 10)}]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 15.0
