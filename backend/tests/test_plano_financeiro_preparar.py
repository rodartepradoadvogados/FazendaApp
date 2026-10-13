"""
Plano Financeiro §1.8 — POST /fazendas/{id}/financeiro/preparar (item G do
contrato de API): plano de contas padrão rural-leiteiro (RASCUNHO — validar
com o contador), contas do sistema e regras v2, idempotente e SÓ para fazenda
sem lançamentos no caso da flag.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, ParametroFazenda, PlanoContaGerencial,
)
from fazenda.rules import dre as dre_rules
from fazenda.rules import natureza as natureza_rules
from fazenda.rules.parametros import regras_v2_ativas
from fazenda.rules.plano_padrao import CODIGO_RETENCOES, CODIGO_VALES
from fazenda.rules.plano_padrao_rural import PLANO_PADRAO_RURAL

EMAIL_DONO = "jairodarte@gmail.com"
N_PADRAO = len(PLANO_PADRAO_RURAL)

# 10: financeiro novo, sem nada | 11: financeiro com lançamento | 12: financeiro com plano próprio
# 13: sem módulo financeiro     | 14: financeiro novo (para provar o isolamento entre fazendas)
MODULOS = {10: ["financeiro", "pedidos"], 11: ["financeiro", "pedidos"], 12: ["financeiro", "pedidos"],
           13: ["rebanho", "reprodutivo"], 14: ["financeiro", "pedidos"]}


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        for fid in MODULOS:
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid, modulos in MODULOS.items():
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for m in modulos:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=m, preco=0.0, ativo=True))
        s.add(ContaGerencial(
            fazenda_id=11, numero_lancamento="LC-11-1", descricao="Já lançada", tipo="despesa",
            data_vencimento=date(2026, 9, 1), valor_total=10.0, origem="manual",
        ))
        # Fazenda 12: plano "do Ideagri" (qualquer conta basta) + o grupo de Pessoal.
        s.add(PlanoContaGerencial(fazenda_id=12, codigo="3.03.01", nome="Pessoal", ativa=True))
        s.add(PlanoContaGerencial(fazenda_id=12, codigo="3.03.01.01", nome="Salários", ativa=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeDono:
        id = 1
        papel = "admin"
        ativo = True
        username = "dono"
        email = EMAIL_DONO
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeDono()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _contas(engine, fid: int) -> list[PlanoContaGerencial]:
    with Session(engine) as s:
        return list(s.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == fid)).all())


def _regras_v2(engine, fid: int) -> bool:
    with Session(engine) as s:
        return regras_v2_ativas(s, fid)


class TestPreparar:
    def test_fazenda_nova_recebe_plano_contas_do_sistema_e_regras_v2(self, client):
        c, engine = client
        r = c.post("/fazendas/10/financeiro/preparar")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["plano_contas_carregado"] is True
        assert corpo["contas_criadas"] == N_PADRAO + 2   # plano padrão + Retenções + Vales
        assert corpo["regras_v2_ligadas"] is True
        assert corpo["ja_preparado"] is False
        assert corpo["mensagens"] and all(isinstance(m, str) for m in corpo["mensagens"])
        assert any("rascunho" in m.lower() for m in corpo["mensagens"])

        por_codigo = {c.codigo: c for c in _contas(engine, 10)}
        assert len(por_codigo) == N_PADRAO + 2
        assert por_codigo[CODIGO_RETENCOES].linha_dre == "NAO_ENTRA_NA_DRE"
        assert por_codigo[CODIGO_VALES].natureza_fin == "ADIANTAMENTO"
        assert por_codigo["2.01.01.01"].rmca_receita_leite is True     # litros do leite no Resultado por litro
        assert _regras_v2(engine, 10) is True

    def test_idempotente_duas_chamadas_mesmo_estado(self, client):
        c, engine = client
        primeira = c.post("/fazendas/10/financeiro/preparar").json()
        antes = sorted(x.codigo for x in _contas(engine, 10))
        segunda = c.post("/fazendas/10/financeiro/preparar")
        assert segunda.status_code == 200, segunda.text
        s2 = segunda.json()
        assert s2["contas_criadas"] == 0
        assert s2["ja_preparado"] is True
        assert s2["plano_contas_carregado"] == primeira["plano_contas_carregado"] is True
        assert s2["regras_v2_ligadas"] == primeira["regras_v2_ligadas"] is True
        assert sorted(x.codigo for x in _contas(engine, 10)) == antes
        with Session(engine) as s:
            linhas = s.exec(select(ParametroFazenda).where(
                ParametroFazenda.chave == "financeiro_regras_v2", ParametroFazenda.fazenda_id == 10)).all()
            assert len(linhas) == 1

    def test_com_lancamentos_nao_liga_a_flag(self, client):
        c, engine = client
        r = c.post("/fazendas/11/financeiro/preparar")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["plano_contas_carregado"] is True          # tinha zero contas: carrega
        assert corpo["regras_v2_ligadas"] is False
        assert _regras_v2(engine, 11) is False
        assert any("lançamentos" in m for m in corpo["mensagens"])
        # E a segunda chamada continua sem ligar.
        c.post("/fazendas/11/financeiro/preparar")
        assert _regras_v2(engine, 11) is False

    def test_fazenda_com_plano_proprio_nao_e_tocada_so_ganha_contas_do_sistema(self, client):
        c, engine = client
        r = c.post("/fazendas/12/financeiro/preparar")
        assert r.status_code == 200, r.text
        codigos = sorted(x.codigo for x in _contas(engine, 12))
        assert codigos == ["3.03.01", "3.03.01.01", CODIGO_RETENCOES, CODIGO_VALES]
        assert r.json()["contas_criadas"] == 2
        assert r.json()["plano_contas_carregado"] is True

    def test_nao_vaza_para_outras_fazendas(self, client):
        c, engine = client
        c.post("/fazendas/10/financeiro/preparar")
        assert _contas(engine, 14) == []
        assert _regras_v2(engine, 14) is False

    def test_exige_modulo_financeiro_no_contrato(self, client):
        c, _ = client
        r = c.post("/fazendas/13/financeiro/preparar")
        assert r.status_code == 400
        assert "Financeiro" in r.json()["detail"]

    def test_fazenda_inexistente_404(self, client):
        c, _ = client
        assert c.post("/fazendas/999/financeiro/preparar").status_code == 404

    def test_so_o_dono_prepara(self, client):
        c, _ = client
        import main
        from fazenda.auth import get_current_user

        class _Admin:
            id = 2
            papel = "admin"
            ativo = True
            username = "admin"
            email = "admin_comum@example.com"
            permissoes = ""

        main.app.dependency_overrides[get_current_user] = lambda: _Admin()
        assert c.post("/fazendas/10/financeiro/preparar").status_code == 403


class TestPlanoPadraoRural:
    """Coerência do rascunho com rules/dre.py e rules/natureza.py."""

    def test_codigos_unicos_e_hierarquia_completa(self):
        codigos = [c.codigo for c in PLANO_PADRAO_RURAL]
        assert len(codigos) == len(set(codigos))
        existentes = set(codigos)
        for codigo in codigos:
            if "." in codigo:
                assert codigo.rsplit(".", 1)[0] in existentes, f"{codigo} sem pai"

    def test_linhas_dre_e_naturezas_validas(self):
        for c in PLANO_PADRAO_RURAL:
            assert c.linha_dre is None or c.linha_dre in dre_rules.LINHAS_DRE_VALIDAS, c.codigo
            assert c.natureza_fin is None or c.natureza_fin in natureza_rules.NATUREZAS, c.codigo

    def test_toda_folha_resolve_uma_linha_da_dre(self):
        """DRE sem 'não classificados' para as contas semeadas (herança por prefixo)."""
        mapa = {c.codigo: c.linha_dre for c in PLANO_PADRAO_RURAL if c.linha_dre}
        codigos = {c.codigo for c in PLANO_PADRAO_RURAL}
        folhas = [k for k in codigos if not any(o.startswith(k + ".") for o in codigos)]
        sem_linha = [k for k in folhas if dre_rules.resolver_linha_dre(k, mapa) is None]
        assert sem_linha == []

    def test_o_que_nao_e_resultado_fica_fora_da_dre(self):
        mapa = {c.codigo: c.linha_dre for c in PLANO_PADRAO_RURAL if c.linha_dre}
        for codigo in ("3.06.03", "3.07.01", "3.08.01", "2.03.01", "2.03.02"):
            assert dre_rules.resolver_linha_dre(codigo, mapa) == "NAO_ENTRA_NA_DRE", codigo
        assert dre_rules.resolver_linha_dre("3.06.01", mapa) == "OUTRAS_REC_DESP"      # só o juros é despesa
        assert dre_rules.resolver_linha_dre("2.01.01.01", mapa) == "RECEITA_VENDAS"
        assert dre_rules.resolver_linha_dre("3.01.01.01", mapa) == "CUSTO_VARIAVEL"
        assert dre_rules.resolver_linha_dre("3.03.01.01", mapa) == "GASTOS_PESSOAL"

    def test_so_a_receita_do_leite_e_a_alimentacao_marcam_rmca(self):
        assert [c.codigo for c in PLANO_PADRAO_RURAL if c.rmca_receita_leite] == ["2.01.01.01"]
        assert all(c.codigo.startswith("3.01.01") for c in PLANO_PADRAO_RURAL if c.rmca_custo_alimentacao)
