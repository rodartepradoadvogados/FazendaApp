"""Repro: Agenda vs Rebanho > Secagens previstas devem concordar sobre a
data de secagem prevista de uma vaca.

Chama as camadas de regra diretamente (`AgendaEngine.calcular` e
`relatorios_manejo`), sem passar pelos routers HTTP — é exatamente o motor
que a Agenda e a tela Rebanho > Secagens previstas usam por baixo
(`agenda.py::calcular_agenda` e `relatorios.py::relatorios_manejo` só
buscam os dados do banco e repassam pra cá).
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules import relatorios_gerenciais as rg
from fazenda.rules.agenda_engine import AgendaEngine
from fazenda.rules.dry_off import calcular_secagem
from fazenda.rules.gestation import calcular_parto_provavel


def _cenario(raca: str):
    """Vaca prenhe (já pariu antes, em lactação) com serviço positivo há 200
    dias. Retorna (animais, servicos, partos, hoje, data_servico)."""
    hoje = date.today()
    data_servico = hoje - timedelta(days=200)
    animal = {
        "numero": "900", "raca": raca, "del_dias": 200, "grupo_primario": "02 - Alta",
        "ativo": True, "sexo": "F", "eh_semen": False, "sit_rep": "Ges.",
    }
    servico = {
        "numero_matriz": "900", "data_servico": data_servico, "diagnostico": "POSITIVO",
        "ordem_parto": 2, "ult_ocorrencia": 1,
    }
    parto = {"numero_matriz": "900", "data_parto": hoje - timedelta(days=400), "ordem_parto": 1}
    return [animal], [servico], [parto], hoje, data_servico


def test_agenda_e_rebanho_concordam_sobre_secagem_prevista_girolando():
    """Reproduz o bug: para raças != Holandês, `relatorios_manejo` (Rebanho >
    Secagens previstas) usava GESTACAO_DIAS=280 fixo, enquanto a Agenda
    (AgendaEngine, via `dry_off.calcular_secagem` + `gestation.
    calcular_parto_provavel`) usa a gestação ESPECÍFICA da raça (Girolando =
    287 dias) — uma divergência de 7 dias na secagem prevista da MESMA vaca
    entre as duas telas."""
    animais, servicos, partos, hoje, data_servico = _cenario("Girolando")

    resultado_agenda = AgendaEngine().calcular(
        data_referencia=hoje, animais=animais, servicos=servicos, partos=partos,
        estoque=[], contas=[], eventos_manuais=[],
    )
    eventos_secagem = [e for e in resultado_agenda.eventos if e.numero_animal == "900" and "Secagem" in e.descricao]
    assert len(eventos_secagem) == 1, "Agenda deveria gerar 1 evento de Secagem para o animal 900"
    data_agenda = eventos_secagem[0].data

    manejo = rg.relatorios_manejo(animais, servicos, partos, semen=[], hoje=hoje)
    lista_secagem = [i for i in manejo["secagem"] if i["numero"] == "900"]
    assert len(lista_secagem) == 1, "Rebanho > Secagens previstas deveria listar o animal 900"
    data_rebanho = lista_secagem[0]["previsao_secagem"]

    # Regra oficial (dry_off + gestation, raça-específica — a mesma que a
    # Agenda usa):
    res_gest = calcular_parto_provavel(data_servico, "Girolando")
    res_sec = calcular_secagem("900", res_gest.data_parto_provavel, ordem_parto=2, em_lactacao=True)
    assert res_sec.data_secagem == data_servico + timedelta(days=287 - 60)

    assert data_agenda == res_sec.data_secagem, f"Agenda deveria bater com a regra oficial: {data_agenda} != {res_sec.data_secagem}"
    assert data_rebanho == res_sec.data_secagem, (
        f"Rebanho > Secagens previstas diverge da Agenda para Girolando: "
        f"Rebanho={data_rebanho} Agenda/regra-oficial={res_sec.data_secagem} "
        f"(antes do fix, Rebanho usava 280 dias fixos e dava {data_servico + timedelta(days=280 - 60)})"
    )
    assert data_rebanho == data_agenda


def test_agenda_e_rebanho_concordam_sobre_secagem_prevista_gir_zebu():
    """Mesmo teste para raça Gir/Zebu/Nelore (295 dias) — divergência de 15
    dias no bug original, a maior de todas as raças mapeadas."""
    animais, servicos, partos, hoje, data_servico = _cenario("Nelore")

    resultado_agenda = AgendaEngine().calcular(
        data_referencia=hoje, animais=animais, servicos=servicos, partos=partos,
        estoque=[], contas=[], eventos_manuais=[],
    )
    data_agenda = next(e.data for e in resultado_agenda.eventos if e.numero_animal == "900" and "Secagem" in e.descricao)

    manejo = rg.relatorios_manejo(animais, servicos, partos, semen=[], hoje=hoje)
    data_rebanho = next(i["previsao_secagem"] for i in manejo["secagem"] if i["numero"] == "900")

    esperado = data_servico + timedelta(days=295 - 60)
    assert data_agenda == esperado
    assert data_rebanho == esperado
