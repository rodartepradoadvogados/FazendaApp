"""Base de cálculo de secagem e pré-parto (Parâmetros > Gestação e parto).

Dois seletores: a base (mínimo/máximo/média) e se a raça cadastrada tem
prioridade. O "Parto provável" mostrado continua por raça (`dias_gestacao`)."""
from __future__ import annotations

import pytest

from fazenda.rules import gestation, parametros


@pytest.fixture
def config(monkeypatch):
    def _definir(base="minimo", raca="respeitar_raca", minimo=280, maximo=295):
        textos = {"gestacao_base_calculo": base, "gestacao_considerar_raca": raca}
        numeros = {"gestacao_dias_min": minimo, "gestacao_dias_max": maximo}
        monkeypatch.setattr(parametros, "get_param_texto", lambda chave, padrao="": textos.get(chave, padrao))
        monkeypatch.setattr(parametros, "get_param", lambda chave, padrao=None: numeros.get(chave, padrao))
    return _definir


@pytest.mark.parametrize("base,esperado", [("minimo", 280), ("maximo", 295), ("media", 288)])
def test_base_dias(config, base, esperado):
    config(base=base)
    assert parametros.gestacao_base_dias() == esperado


def test_padrao_sem_parametro_e_minimo(monkeypatch):
    monkeypatch.setattr(parametros, "get_param_texto", lambda chave, padrao="": padrao)
    monkeypatch.setattr(parametros, "get_param", lambda chave, padrao=None: padrao)
    assert parametros.gestacao_base_dias() == 280
    assert parametros.gestacao_raca_prevalece() is True


def test_respeitar_raca_cadastrada_usa_tabela_da_raca(config):
    config(base="minimo", raca="respeitar_raca")
    assert gestation.dias_gestacao_secagem_pre_parto("Girolando") == 287
    assert gestation.dias_gestacao_secagem_pre_parto("Gir") == 295
    assert gestation.dias_gestacao_secagem_pre_parto("Holandês") == 280


def test_respeitar_raca_sem_raca_ou_raca_fora_da_tabela_usa_base(config):
    config(base="media", raca="respeitar_raca")
    assert gestation.dias_gestacao_secagem_pre_parto(None) == 288
    assert gestation.dias_gestacao_secagem_pre_parto("") == 288
    assert gestation.dias_gestacao_secagem_pre_parto("Jersey") == 288


@pytest.mark.parametrize("base,esperado", [("minimo", 280), ("maximo", 295), ("media", 288)])
def test_ignorar_raca_usa_a_base_para_todos(config, base, esperado):
    config(base=base, raca="base_para_todos")
    for raca in (None, "Girolando", "Gir", "Holandês"):
        assert gestation.dias_gestacao_secagem_pre_parto(raca) == esperado


def test_parto_provavel_exibido_continua_por_raca(config):
    config(base="minimo", raca="base_para_todos")
    assert gestation.dias_gestacao("Girolando") == 287


def test_opcoes_do_select_cobrem_os_valores_padrao():
    for chave in ("gestacao_base_calculo", "gestacao_considerar_raca"):
        padrao = next(d for d in parametros.DEFINICOES if d["chave"] == chave)
        assert padrao["tipo"] == "select"
        assert padrao["valor"] in {v for v, _ in parametros.OPCOES_SELECT[chave]}
