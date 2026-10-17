"""Fixação manual TEMPORÁRIA da classificação (matriz 11153) — ver CLASSIFICACAO_FIXADA em estado_reprodutivo."""
from datetime import date, timedelta
from types import SimpleNamespace

from fazenda.rules import estado_reprodutivo as er

HOJE = date(2026, 10, 17)


def _calcular(numero: str) -> dict:
    # Pariu há 300 dias; serviço positivo reconfirmado ANTES de uma lactação reaberta (âncora posterior) -> a regra
    # descarta o serviço e devolve atrasada. É exatamente o cenário que a Auditoria chama de «lactacao_sem_parto».
    parto = SimpleNamespace(data_parto=HOJE - timedelta(days=300))
    servico = SimpleNamespace(
        data_servico=HOJE - timedelta(days=120), diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=90),
        diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=HOJE - timedelta(days=60), data_perda_prenhez=None,
        tipo_servico="IA", protocolo=None, retoque=None,
    )
    return er.classificar_animal(
        numero, hoje=HOJE, partos=[parto], servicos=[servico], aplicacoes_iatf=[], pev_dias=50,
        del_max_1o_servico=60, eh_vaca=True, data_inicio_lactacao=HOJE - timedelta(days=100),
    )


def test_matriz_fixada_vira_gestante_e_guarda_o_estado_calculado():
    r = _calcular("11153")
    assert r["estado"] == er.GESTANTE
    assert r["classificacao_fixada"] is True
    assert r["estado_calculado"] == er.ATRASADA


def test_outra_matriz_nao_e_afetada():
    r = _calcular("11154")
    assert r["estado"] == er.ATRASADA
    assert "classificacao_fixada" not in r
