"""
Testes de fazenda/rules/reproducao_dossie.py::taxa_prenhez_ciclos — módulo
sem teste dedicado até aqui (152 linhas de estatística usadas no Dossiê de
Recria). Cobre o caso normal e documenta (caracterização, não endosso) o
comportamento do fallback quando a interseção servidos∩elegíveis é vazia —
achado da auditoria de 18/08: nesse caso a taxa usa `len(servidos)` inteiro
sobre `len(elegiveis)`, podendo passar de 100%.
"""
from __future__ import annotations

from datetime import date

from fazenda.rules.reproducao_dossie import taxa_prenhez_ciclos


def _servico(numero, data_servico, elegivel_desde=None, prenhe=False):
    return {"numero": numero, "data_servico": data_servico, "prenhe": prenhe, "elegivel_desde": elegivel_desde}


class TestCicloNormal:
    def test_animal_elegivel_e_servido_no_mesmo_ciclo(self):
        servicos = [_servico("101", date(2026, 1, 5), elegivel_desde=date(2026, 1, 1))]
        ciclos = taxa_prenhez_ciclos(servicos, date(2026, 1, 1), date(2026, 1, 21))
        assert len(ciclos) == 1
        c = ciclos[0]
        assert c["elegiveis"] == 1
        assert c["servidos"] == 1
        assert c["taxa_servico"] == 100.0

    def test_servido_e_prenhe_conta_nas_tres_taxas(self):
        servicos = [_servico("101", date(2026, 1, 5), elegivel_desde=date(2026, 1, 1), prenhe=True)]
        c = taxa_prenhez_ciclos(servicos, date(2026, 1, 1), date(2026, 1, 21))[0]
        assert c["taxa_servico"] == 100.0
        assert c["taxa_concepcao"] == 100.0
        assert c["taxa_prenhez"] == 100.0

    def test_sem_elegiveis_no_ciclo_taxas_ficam_none(self):
        # elegivel_desde muito depois do fim do ciclo -> ninguém apto.
        servicos = [_servico("101", date(2026, 1, 5), elegivel_desde=date(2026, 2, 1))]
        c = taxa_prenhez_ciclos(servicos, date(2026, 1, 1), date(2026, 1, 21))[0]
        assert c["elegiveis"] == 0
        assert c["taxa_servico"] is None
        assert c["taxa_prenhez"] is None

    def test_multiplos_ciclos_de_21_dias_no_periodo(self):
        # 45 dias -> 3 ciclos (21 + 21 + 3).
        servicos = [_servico("101", date(2026, 1, 5), elegivel_desde=date(2026, 1, 1))]
        ciclos = taxa_prenhez_ciclos(servicos, date(2026, 1, 1), date(2026, 2, 14))
        assert len(ciclos) == 3
        assert ciclos[0]["inicio"] == "2026-01-01"
        assert ciclos[1]["inicio"] == "2026-01-22"
        assert ciclos[2]["fim"] == "2026-02-14"

    def test_animal_ja_prenhe_antes_do_ciclo_nao_conta_como_elegivel(self):
        # Concebeu em 05/01 (ciclo 1) -> no ciclo 2 (22/01 em diante) não é mais elegível.
        servicos = [_servico("101", date(2026, 1, 5), elegivel_desde=date(2026, 1, 1), prenhe=True)]
        ciclos = taxa_prenhez_ciclos(servicos, date(2026, 1, 1), date(2026, 2, 11))
        assert ciclos[0]["elegiveis"] == 1
        assert ciclos[1]["elegiveis"] == 0


class TestFallbackInterseccaoVazia:
    """Achado da auditoria (18/08): quando servidos∩elegiveis é vazio, o
    fallback usa `len(servidos)` cru em vez de 0 — se houver mais "servidos
    fora do universo elegível" do que elegíveis, a taxa passa de 100%.
    Documentando o comportamento atual como está, não como deveria ser."""

    def test_servidos_fora_do_universo_elegivel_empurra_taxa_acima_de_100(self):
        servicos = [
            # C: elegível neste ciclo, mas NÃO foi servida.
            _servico("C", date(2025, 12, 1), elegivel_desde=date(2026, 1, 1)),
            # B e D: servidas DENTRO do ciclo, mas só ficam elegíveis depois dele.
            _servico("B", date(2026, 1, 10), elegivel_desde=date(2026, 1, 25)),
            _servico("D", date(2026, 1, 12), elegivel_desde=date(2026, 1, 25)),
        ]
        c = taxa_prenhez_ciclos(servicos, date(2026, 1, 1), date(2026, 1, 21))[0]
        assert c["elegiveis"] == 1  # só C
        assert c["servidos"] == 2  # B e D
        # servidos ∩ elegiveis = {} (vazio) -> fallback usa os 2 servidos crus
        # sobre 1 elegível = 200%, mesmo nenhum dos servidos sendo elegível.
        assert c["taxa_servico"] == 200.0
