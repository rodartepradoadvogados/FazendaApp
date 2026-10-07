"""Caixa dos funcionários — Fase 2: retenção na folha.

Trava: a rubrica de desconto identificada nasce do combinado (fixo/percentual,
teto, vigência, pausa, revogação); o pagamento da folha vira entrada no caixa +
despesa baixada; o estorno do pagamento desfaz (e é recusado se o dinheiro já
foi sacado); a pendência do termo aparece; e há isolamento entre fazendas."""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    CaixaMovimento, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, PessoaAnexo,
    Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import caixa_funcionario as regras

COMPETENCIA = "2026-02"
INICIO = "2026-01-01"


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    ids: dict[str, int] = {}
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
        s.commit()
        for fid in (1, 2):
            p = Pessoa(nome="Leomir Bonfim", tipo="Funcionário", salario_base=3000.0,
                       data_admissao=date(2024, 1, 10), fazenda_id=fid)
            s.add(p)
            s.commit()
            s.refresh(p)
            ids[f"pessoa{fid}"] = p.id

    def _sess():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fid: int = 1):
    return {"Authorization": f"Bearer {criar_token(f'admin{fid}', fazenda_id=fid)}"}


def _cfg(c, pessoa_id, fid=1, **extra):
    corpo = {"forma": "fixo", "valor": 100.0, "inicio": INICIO, "autorizada": True}
    corpo.update(extra)
    return c.put(f"/cadastro/caixa-funcionarios/{pessoa_id}/retencao", json=corpo, headers=_cab(fid))


def _folha(c, pessoa_id, fid=1, competencia=COMPETENCIA) -> int:
    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": 3000.0,
        "percentual_inss": 9.0, "valor_inss": 270.0,
    }, headers=_cab(fid))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _ver(c, folha_id, fid=1) -> dict:
    r = c.get("/cadastro/folha-pagamento", headers=_cab(fid))
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["id"] == folha_id)


def _linha(folha: dict):
    return next((d for d in folha["detalhe"] if (d.get("origem") or {}).get("codigo") == regras.CODIGO_RUBRICA), None)


def _pagar(c, folha_id, fid=1):
    return c.post(f"/cadastro/folha-pagamento/{folha_id}/pagar", json={"data_pagamento": "2026-03-05"}, headers=_cab(fid))


def _saldo(c, pessoa_id, fid=1) -> float:
    return c.get(f"/cadastro/caixa-funcionarios/{pessoa_id}", headers=_cab(fid)).json()["saldo"]


class TestConfiguracao:
    def test_validacoes(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        assert _cfg(c, p, valor=0).status_code == 400
        assert _cfg(c, p, forma="percentual", valor=150).status_code == 400
        assert _cfg(c, p, forma="xx").status_code == 400
        assert _cfg(c, p, teto=-1).status_code == 400
        assert _cfg(c, p, fim="2025-01-01").status_code == 400
        assert _cfg(c, p).status_code == 200

    def test_um_combinado_por_pessoa_atualiza(self, ambiente):
        c, engine, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p, valor=100)
        _cfg(c, p, valor=150)
        from fazenda.models import CaixaRetencao
        with Session(engine) as s:
            rows = s.exec(select(CaixaRetencao).where(CaixaRetencao.pessoa_id == p)).all()
        assert len(rows) == 1 and rows[0].valor == 150


class TestRubricaNaFolha:
    def test_rubrica_identificada_e_liquido_reduzido(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        sem = _ver(c, _folha(c, p, competencia="2025-12"))["valor_liquido"]
        _cfg(c, p, valor=100)
        f = _ver(c, _folha(c, p))
        linha = _linha(f)
        assert linha is not None and round(abs(linha["valor"]), 2) == 100.0
        assert round(sem - f["valor_liquido"], 2) == 100.0

    def test_sem_autorizacao_nao_retem(self, ambiente):
        c, _, ids = ambiente
        _cfg(c, ids["pessoa1"], autorizada=False)
        assert _linha(_ver(c, _folha(c, ids["pessoa1"]))) is None

    def test_pausada_nao_retem_e_retomar_volta(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p)
        c.post(f"/cadastro/caixa-funcionarios/{p}/retencao/pausar", json={"pausada": True}, headers=_cab())
        fid_folha = _folha(c, p)
        assert _linha(_ver(c, fid_folha)) is None
        c.post(f"/cadastro/caixa-funcionarios/{p}/retencao/pausar", json={"pausada": False}, headers=_cab())
        assert _linha(_ver(c, fid_folha)) is not None  # autocura na listagem

    def test_vigencia_fora_da_janela(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p, inicio="2026-03-01")
        assert _linha(_ver(c, _folha(c, p))) is None  # competência 2026-02 anterior ao início

    def test_percentual_sobre_salario_base(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p, forma="percentual", valor=5)
        assert round(abs(_linha(_ver(c, _folha(c, p)))["valor"]), 2) == 150.0

    def test_teto_limita_ao_que_falta(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p, valor=100, teto=130)
        f1 = _folha(c, p, competencia="2026-01")
        assert round(abs(_linha(_ver(c, f1))["valor"]), 2) == 100.0
        assert _pagar(c, f1).status_code == 200
        f2 = _folha(c, p, competencia="2026-02")
        assert round(abs(_linha(_ver(c, f2))["valor"]), 2) == 30.0


class TestPagamentoEEstorno:
    def test_pagar_cria_movimento_e_despesa_baixada(self, ambiente):
        c, engine, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p, valor=100)
        fo = _folha(c, p)
        assert _pagar(c, fo).status_code == 200
        assert _saldo(c, p) == 100.0
        with Session(engine) as s:
            movs = s.exec(select(CaixaMovimento).where(CaixaMovimento.pessoa_id == p)).all()
            assert len(movs) == 1 and movs[0].tipo == "retencao" and movs[0].folha_id == fo
            conta = s.get(ContaGerencial, movs[0].lancamento_id)
            assert conta.valor_pago is not None and conta.tipo == "despesa"

    def test_idempotente_nao_duplica(self, ambiente):
        c, engine, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p)
        fo = _folha(c, p)
        _pagar(c, fo)
        with Session(engine) as s:
            folha = s.get(__import__("fazenda.models", fromlist=["FolhaPagamento"]).FolhaPagamento, fo)
            regras.lancar_retencao_da_folha(s, folha)
            s.commit()
        assert _saldo(c, p) == 100.0

    def test_estornar_pagamento_reverte_retencao(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p)
        fo = _folha(c, p)
        _pagar(c, fo)
        r = c.post(f"/cadastro/folha-pagamento/{fo}/estornar", json={}, headers=_cab())
        assert r.status_code == 200, r.text
        assert _saldo(c, p) == 0.0

    def test_estorno_bloqueado_se_ja_sacou(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p)
        fo = _folha(c, p)
        _pagar(c, fo)
        r = c.post(f"/cadastro/caixa-funcionarios/{p}/retiradas", json={
            "valor": 100.0, "data": date.today().isoformat(), "forma_pagamento": "pix"}, headers=_cab())
        assert r.status_code == 200, r.text
        r = c.post(f"/cadastro/folha-pagamento/{fo}/estornar", json={}, headers=_cab())
        assert r.status_code == 409, r.text
        assert _saldo(c, p) == 0.0

    def test_movimento_de_folha_nao_estorna_nem_exclui_pelo_caixa(self, ambiente):
        c, engine, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p)
        _pagar(c, _folha(c, p))
        with Session(engine) as s:
            mid = s.exec(select(CaixaMovimento).where(CaixaMovimento.pessoa_id == p)).first().id
        assert c.post(f"/cadastro/caixa-funcionarios/{p}/movimentos/{mid}/estornar", json={"motivo": "x"}, headers=_cab()).status_code == 409
        assert c.delete(f"/cadastro/caixa-funcionarios/{p}/movimentos/{mid}", headers=_cab()).status_code in (400, 409)


class TestTermoPendente:
    def test_pendencia_some_ao_anexar(self, ambiente):
        c, engine, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p)
        r = c.get("/cadastro/caixa-funcionarios/pendencias", headers=_cab())
        assert [x["pessoa_id"] for x in r.json()["termos_pendentes"]] == [p]
        with Session(engine) as s:
            s.add(PessoaAnexo(pessoa_id=p, fazenda_id=1, categoria=regras.CATEGORIA_TERMO,
                              nome_arquivo="t.pdf", tamanho_bytes=10, mime_type="application/pdf"))
            s.commit()
        r = c.get("/cadastro/caixa-funcionarios/pendencias", headers=_cab())
        assert r.json()["termos_pendentes"] == []

    def test_nao_autorizada_ou_revogada_nao_gera_pendencia(self, ambiente):
        c, _, ids = ambiente
        p = ids["pessoa1"]
        _cfg(c, p, autorizada=False)
        assert c.get("/cadastro/caixa-funcionarios/pendencias", headers=_cab()).json()["termos_pendentes"] == []


class TestIsolamento:
    def test_fazenda_2_nao_ve_nem_mexe_na_retencao_da_1(self, ambiente):
        c, _, ids = ambiente
        _cfg(c, ids["pessoa1"])
        assert c.get(f"/cadastro/caixa-funcionarios/{ids['pessoa1']}/retencao", headers=_cab(2)).status_code == 404
        assert _cfg(c, ids["pessoa1"], fid=2).status_code == 404
        assert c.get("/cadastro/caixa-funcionarios/pendencias", headers=_cab(2)).json()["termos_pendentes"] == []
        assert _linha(_ver(c, _folha(c, ids["pessoa2"], fid=2), fid=2)) is None
