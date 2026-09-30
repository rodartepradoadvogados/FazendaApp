"""Item de estoque INATIVO nunca gera alerta/tarefa de compra (relato do dono:
"COMPRAR BANAMINE 100ML — estoque abaixo do mínimo" continuava na Agenda com o
item inativado)."""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Estoque, PrincipioAtivo


def _calcular(estoque):
    from fazenda.rules.agenda_engine import AgendaEngine
    return AgendaEngine().calcular(date(2026, 7, 7), [], [], [], estoque, [], [])


def _item(**kw):
    base = {"nome": "Banamine 100ml", "quantidade": 1, "estoque_minimo": 10, "unidade": "ml",
            "exibir_necessidade_compra_agenda": True}
    base.update(kw)
    return base


def test_engine_nao_gera_comprar_para_item_inativo():
    res = _calcular([_item(ativo=False)])
    assert not [e for e in res.eventos if e.descricao.startswith("Comprar")]


def test_engine_continua_gerando_para_ativo_e_para_ativo_nulo():
    assert len([e for e in _calcular([_item(ativo=True)]).eventos if e.descricao.startswith("Comprar")]) == 1
    assert len([e for e in _calcular([_item(ativo=None)]).eventos if e.descricao.startswith("Comprar")]) == 1


def test_manual_da_fazenda_ignora_item_inativo():
    from fazenda.rules.manual_fazenda import _rotina_compras
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Estoque(nome="Banamine 100ml", quantidade=1.0, estoque_minimo=10.0, unidade="ml", ativo=False, estocavel=True))
        s.add(Estoque(nome="Ivermectina", quantidade=1.0, estoque_minimo=10.0, unidade="ml", ativo=True, estocavel=True))
        s.commit()
        assert [c["nome"] for c in _rotina_compras(s, None)] == ["Ivermectina"]


def test_assistente_ignora_item_inativo():
    from fazenda.rules.assistente import _tool_consultar_estoque
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Estoque(nome="Banamine 100ml", quantidade=1.0, estoque_minimo=10.0, unidade="ml", ativo=False, abaixo_minimo=True))
        s.add(Estoque(nome="Ivermectina", quantidade=1.0, estoque_minimo=10.0, unidade="ml", ativo=True, abaixo_minimo=True))
        s.commit()
        r = _tool_consultar_estoque(s)
        assert [i["nome"] for i in r["abaixo_do_minimo"]] == ["Ivermectina"]


def test_baixa_de_item_inativo_nao_avisa_abaixo_do_minimo():
    from fazenda.rules import estoque_baixa
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        it = Estoque(nome="Banamine 100ml", quantidade=5.0, estoque_minimo=10.0, unidade="ml", ativo=False)
        s.add(it); s.commit(); s.refresh(it)
        avisos = estoque_baixa.baixar(s, item=it, quantidade=1, unidade="ml", data=date(2026, 7, 7), fazenda_id=None, observacao="t")
        assert not any("abaixo do mínimo" in a for a in avisos)
