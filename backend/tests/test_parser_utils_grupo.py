"""
Testes de fazenda.parsers.utils: clean_grupo (escolhe o grupo de menor
código quando há vários) e normalizar_grupos_por_codigo (uniformiza a
grafia do mesmo lote entre linhas, evitando duplicidade por maiúsculas).
"""
from __future__ import annotations

from fazenda.parsers.utils import clean_grupo, normalizar_grupos_por_codigo


class TestCleanGrupo:
    def test_grupo_unico(self):
        assert clean_grupo("01 - NOV. ALTA") == "01 - NOV. ALTA"

    def test_escolhe_o_menor_codigo_independente_da_ordem(self):
        assert clean_grupo("03 - Média,01 - NOV. ALTA") == "01 - NOV. ALTA"
        assert clean_grupo("01 - NOV. ALTA,03 - Média") == "01 - NOV. ALTA"

    def test_tres_grupos(self):
        assert clean_grupo("08 - BEZ 3,02 - Baixa,05 - Secas") == "02 - Baixa"

    def test_vazio(self):
        assert clean_grupo("") == ""
        assert clean_grupo(None) == ""  # type: ignore[arg-type]


class _Animal:
    def __init__(self, grupo_primario):
        self.grupo_primario = grupo_primario


class TestNormalizarGruposPorCodigo:
    def test_unifica_grafias_diferentes_do_mesmo_codigo(self):
        animais = [_Animal("03 - Média"), _Animal("03 - MÉDIA"), _Animal("03 - Média")]
        normalizar_grupos_por_codigo(animais)
        grafias = {a.grupo_primario for a in animais}
        assert len(grafias) == 1

    def test_prefere_a_grafia_toda_maiuscula(self):
        animais = [_Animal("03 - Média"), _Animal("03 - MÉDIA")]
        normalizar_grupos_por_codigo(animais)
        assert all(a.grupo_primario == "03 - MÉDIA" for a in animais)

    def test_sem_variante_maiuscula_mantem_a_primeira(self):
        animais = [_Animal("01 - Nov. Alta"), _Animal("01 - Nov. alta")]
        normalizar_grupos_por_codigo(animais)
        assert all(a.grupo_primario == "01 - Nov. Alta" for a in animais)

    def test_nao_mistura_codigos_diferentes(self):
        animais = [_Animal("01 - Alta"), _Animal("02 - Baixa")]
        normalizar_grupos_por_codigo(animais)
        assert animais[0].grupo_primario == "01 - Alta"
        assert animais[1].grupo_primario == "02 - Baixa"

    def test_ignora_grupo_vazio(self):
        animais = [_Animal(""), _Animal(None), _Animal("01 - Alta")]
        normalizar_grupos_por_codigo(animais)
        assert animais[0].grupo_primario == ""
        assert animais[1].grupo_primario is None
        assert animais[2].grupo_primario == "01 - Alta"
