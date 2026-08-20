"""
Ordem de parto histórica do controle leiteiro (`rules/ordem_parto_historica.py`).

O teste central é `test_vaca_de_quinta_cria_nao_tem_tudo_marcado_como_quinta`:
é o bug de verdade, e ele é sistemático, não um caso de borda. Enquanto a ordem
exibida for a contagem TOTAL de partos, toda a produção baixa da primeira cria
entra na média das maduras — e o equivalente maduro passa a subestimar
exatamente o quanto uma novilha ainda tem a crescer, que é a única pergunta que
o indicador existe para responder.

Os testes de `None` importam quase tanto. Há três motivos reais para não saber a
ordem, e nenhum deles autoriza chutar: controle sem data, controle anterior ao
primeiro parto registrado (o histórico de partos é mais curto que o de
controles), e parto sem ordem gravada.
"""
from __future__ import annotations

from datetime import date

from fazenda.rules.ordem_parto_historica import (
    Divergencia,
    PartoRef,
    divergencias_do_animal,
    ordem_parto_na_data,
    ordem_parto_pelo_atalho_atual,
)

# Uma vaca de verdade: cinco partos, um por ano.
CINCO_PARTOS = [
    PartoRef(date(2021, 3, 10), 1),
    PartoRef(date(2022, 4, 2), 2),
    PartoRef(date(2023, 5, 20), 3),
    PartoRef(date(2024, 6, 15), 4),
    PartoRef(date(2025, 7, 1), 5),
]


class TestOrdemNaData:
    def test_vaca_de_quinta_cria_nao_tem_tudo_marcado_como_quinta(self):
        """O bug, em números. Um controle de 2021 é da PRIMEIRA cria, não da
        quinta — mesmo que a vaca esteja hoje na quinta."""
        assert ordem_parto_na_data(CINCO_PARTOS, date(2021, 8, 1)) == 1
        assert ordem_parto_na_data(CINCO_PARTOS, date(2022, 9, 1)) == 2
        assert ordem_parto_na_data(CINCO_PARTOS, date(2025, 12, 1)) == 5
        # E o atalho de hoje diria "5" para todos os três.
        assert ordem_parto_pelo_atalho_atual(CINCO_PARTOS) == 5

    def test_pega_o_parto_mais_recente_anterior_ao_controle(self):
        """Véspera do 3º parto ainda é 2ª cria."""
        assert ordem_parto_na_data(CINCO_PARTOS, date(2023, 5, 19)) == 2

    def test_empate_de_data_resolve_a_favor_do_parto(self):
        """Parto e controle no mesmo dia: a vaca já pariu, e o controle mede a
        lactação nova."""
        assert ordem_parto_na_data(CINCO_PARTOS, date(2023, 5, 20)) == 3

    def test_controle_anterior_ao_primeiro_parto_nao_chuta(self):
        """Acontece de verdade: o histórico de partos é mais curto que o de
        controles importados do sistema antigo."""
        assert ordem_parto_na_data(CINCO_PARTOS, date(2020, 1, 1)) is None

    def test_controle_sem_data_nao_chuta(self):
        assert ordem_parto_na_data(CINCO_PARTOS, None) is None

    def test_animal_sem_parto_nenhum_nao_chuta(self):
        assert ordem_parto_na_data([], date(2024, 1, 1)) is None

    def test_parto_sem_ordem_gravada_e_ignorado(self):
        """Não dá para derivar ordem de um parto que não tem ordem — e contar
        posição na lista seria inventar, porque a lista pode estar incompleta."""
        partos = [PartoRef(date(2023, 1, 1), None), PartoRef(date(2024, 1, 1), 2)]
        assert ordem_parto_na_data(partos, date(2023, 6, 1)) is None
        assert ordem_parto_na_data(partos, date(2024, 6, 1)) == 2

    def test_ordem_dos_partos_na_lista_nao_importa(self):
        """A regra é por data, não por posição — a consulta pode vir em
        qualquer ordem."""
        embaralhado = list(reversed(CINCO_PARTOS))
        assert ordem_parto_na_data(embaralhado, date(2022, 9, 1)) == 2

    def test_parto_sem_data_e_ignorado(self):
        partos = [*CINCO_PARTOS, PartoRef(None, 6)]
        assert ordem_parto_na_data(partos, date(2025, 12, 1)) == 5


class TestDivergencias:
    def test_lista_so_o_que_muda(self):
        """Controles depois do último parto já estão certos pelo atalho — não
        entram no relatório, senão o número assusta sem motivo."""
        datas = [date(2021, 8, 1), date(2023, 8, 1), date(2025, 12, 1)]
        d = divergencias_do_animal("3335", CINCO_PARTOS, datas)
        assert [x.data_controle for x in d] == [date(2021, 8, 1), date(2023, 8, 1)]
        assert d[0] == Divergencia("3335", date(2021, 8, 1), ordem_hoje=5, ordem_correta=1)
        assert d[1].ordem_correta == 3

    def test_primipara_nao_diverge(self):
        """Vaca de primeira cria: contagem total e ordem real são a mesma
        coisa. A reconstrução não deve tocá-la."""
        um_parto = [PartoRef(date(2024, 1, 1), 1)]
        assert divergencias_do_animal("900", um_parto, [date(2024, 6, 1)]) == []

    def test_controle_sem_ordem_derivavel_conta_como_divergencia(self):
        """Hoje a tela mostra um número; a verdade é que não se sabe. Trocar
        número por 'não sei' É uma mudança, e o relatório tem de contá-la."""
        d = divergencias_do_animal("901", CINCO_PARTOS, [date(2019, 1, 1)])
        assert len(d) == 1 and d[0].ordem_correta is None and d[0].ordem_hoje == 5

    def test_animal_sem_parto_e_sem_controle_nao_gera_nada(self):
        assert divergencias_do_animal("902", [], []) == []
