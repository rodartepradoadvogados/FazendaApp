"""Risco e exigências de confirmação (Fase 1 do "Excluir lançamentos") — funções
puras, sem banco. Valida o contrato que o servidor usa para recusar com 422."""
from __future__ import annotations

from fazenda.rules.exclusao_impacto import Impacto, Linha
from fazenda.rules import exclusao_risco


def _imp(apagar=(), reverter=(), risco=None, porque=()) -> Impacto:
    return Impacto(
        item={"tipo": "x", "id": "1", "titulo": "x"},
        apagar=list(apagar),
        reverter=list(reverter),
        risco=risco,
        porque=list(porque),
    )


def test_baixo_um_registro_sem_reversao():
    assert exclusao_risco.calcular(_imp(apagar=[Linha("A", "some")])) == "baixo"


def test_medio_por_reversao():
    assert exclusao_risco.calcular(_imp(apagar=[Linha("A", "some")], reverter=[Linha("Estoque", "volta")])) == "medio"


def test_medio_por_dinheiro_em_aberto():
    assert exclusao_risco.calcular(_imp(apagar=[Linha("Conta", "some", valor=100.0)])) == "medio"


def test_medio_por_dois_ou_mais_registros():
    assert exclusao_risco.calcular(_imp(apagar=[Linha("A", "some"), Linha("B", "some")])) == "medio"


def test_alto_por_dez_ou_mais():
    assert exclusao_risco.calcular(_imp(apagar=[Linha("A", "some", qtd=10)])) == "alto"


def test_alto_forcado_pelo_tipo():
    # ficha de animal força alto (e a razão vem pronta)
    assert exclusao_risco.calcular(_imp(risco="alto", porque=["apaga a ficha e todo o histórico"])) == "alto"


def test_porque_elenca_razoes():
    p = exclusao_risco.porque(_imp(apagar=[Linha("Conta", "some", valor=100.0)], reverter=[Linha("E", "volta")]))
    assert "tem dinheiro em aberto" in p
    assert any("mexe em outros dados" in r for r in p)


def test_admin_exige_motivo_so_no_medio_alto():
    assert exclusao_risco.exige_motivo("baixo", eh_admin=True) is False
    assert exclusao_risco.exige_motivo("medio", eh_admin=True) is True
    assert exclusao_risco.exige_motivo("alto", eh_admin=True) is True


def test_nao_admin_sempre_exige_motivo():
    assert exclusao_risco.exige_motivo("baixo", eh_admin=False) is True


def test_confirmacao_so_no_alto():
    assert exclusao_risco.exige_confirmacao("baixo") is False
    assert exclusao_risco.exige_confirmacao("medio") is False
    assert exclusao_risco.exige_confirmacao("alto") is True