"""
Ajuste da curva de Wood (`rules/curva_wood.py`) aos pontos reais (DEL, kg) de
um animal — usada pela ficha para desenhar a trajetória esperada da
lactação e projetar a cauda de uma lactação em aberto.
"""
from __future__ import annotations

import pytest

from fazenda.rules.curva_wood import (
    MARGEM_PROJECAO_DIAS,
    PONTOS_MINIMOS_AJUSTE,
    _wood,
    ajustar_curva_wood,
)


class TestPontosInsuficientes:
    def test_sem_pontos_e_none(self):
        assert ajustar_curva_wood([]) is None

    def test_abaixo_do_minimo_e_none(self):
        # PONTOS_MINIMOS_AJUSTE é 4 — 3 pontos válidos não bastam, mesmo que
        # descrevam uma trajetória plausível (curto demais para confiar).
        pontos = [(10, 20.0), (60, 30.0), (150, 22.0)]
        assert len(pontos) == PONTOS_MINIMOS_AJUSTE - 1
        assert ajustar_curva_wood(pontos) is None

    def test_pontos_invalidos_del_ou_kg_nao_positivos_sao_descartados(self):
        # DEL 0 e kg 0/negativo não entram na regressão (log exige > 0) — com
        # eles descartados, sobra menos que o mínimo.
        pontos = [(0, 20.0), (10, 0.0), (20, -5.0), (30, 25.0), (40, 24.0)]
        assert ajustar_curva_wood(pontos) is None

    def test_todos_no_mesmo_del_e_sistema_degenerado_none(self):
        # Sem variação em DEL não há como separar os 3 parâmetros.
        pontos = [(50, 20.0), (50, 21.0), (50, 19.0), (50, 22.0)]
        assert ajustar_curva_wood(pontos) is None


class TestAjustePlausivel:
    def _pontos_sinteticos(self, a=25.0, b=0.2, c=0.0025):
        """Amostra uma curva de Wood "real" em alguns DELs de controle
        mensal, com um ruído pequeno — como pontos de controle leiteiro de
        verdade, não perfeitamente sobre a curva."""
        dels = [5, 20, 40, 60, 90, 120, 150, 200, 250]
        ruido = [0.3, -0.4, 0.2, -0.1, 0.4, -0.3, 0.1, -0.2, 0.3]
        return [(t, round(_wood(a, b, c, t) + r, 2)) for t, r in zip(dels, ruido)]

    def test_recupera_parametros_proximos_dos_originais(self):
        pontos = self._pontos_sinteticos(a=25.0, b=0.2, c=0.0025)
        r = ajustar_curva_wood(pontos)
        assert r is not None
        assert r["a"] == pytest.approx(25.0, rel=0.25)
        assert r["b"] == pytest.approx(0.2, abs=0.15)
        assert r["c"] == pytest.approx(0.0025, abs=0.002)

    def test_curva_sobe_e_depois_desce_como_lactacao_real(self):
        pontos = self._pontos_sinteticos()
        r = ajustar_curva_wood(pontos)
        assert r is not None
        serie = r["pontos"]
        kgs = [p["kg"] for p in serie]
        pico_idx = max(range(len(kgs)), key=lambda i: kgs[i])
        # Sobe até o pico...
        assert all(kgs[i] <= kgs[i + 1] for i in range(pico_idx))
        # ...e desce depois dele.
        assert all(kgs[i] >= kgs[i + 1] for i in range(pico_idx, len(kgs) - 1))
        # Pico não é nem na borda inicial nem na final — tem forma de sino.
        assert 0 < pico_idx < len(kgs) - 1

    def test_serie_comeca_no_del_zero_e_cobre_ate_maior_del_mais_margem(self):
        pontos = self._pontos_sinteticos()
        maior_del = max(t for t, _ in pontos)
        r = ajustar_curva_wood(pontos)
        assert r is not None
        serie = r["pontos"]
        assert serie[0]["del"] == 0
        assert serie[0]["kg"] == 0.0
        assert serie[-1]["del"] == maior_del + MARGEM_PROJECAO_DIAS

    def test_projeta_cauda_alem_do_ultimo_ponto_real(self):
        """A lactação ainda em aberto (sem controle além do DEL 250) ganha
        pontos projetados de DEL 251 até 250+margem — é a cauda que a ficha
        usa para estimar onde a produção vai parar."""
        pontos = self._pontos_sinteticos()
        r = ajustar_curva_wood(pontos)
        assert r is not None
        dels_serie = {p["del"] for p in r["pontos"]}
        assert 251 in dels_serie
        assert 250 + MARGEM_PROJECAO_DIAS in dels_serie
