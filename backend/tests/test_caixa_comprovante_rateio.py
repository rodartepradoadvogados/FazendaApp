"""Comprovante (nº e arquivo) no pagamento direto do rateio e nas retiradas do caixa."""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, select

from fazenda.models import CaixaMovimento, PessoaAnexo
from tests.test_caixa_time import _entrada, _h, _rateio, _saldo, _time, ambiente  # noqa: F401


def _anexo(c, monkeypatch, pessoa_id, fid=1, categoria="Comprovante de pagamento"):
    from fazenda.api.routers.cadastro import pessoas as rota_pessoas
    monkeypatch.setattr(rota_pessoas, "enviar_arquivo", lambda *a, **k: None)  # sem Supabase nos testes
    r = c.post(f"/cadastro/pessoas/{pessoa_id}/anexos", headers=_h(fid), data={"categoria": categoria},
               files={"file": ("pix.pdf", b"%PDF-1.4 comprovante", "application/pdf")})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _retirada_de(engine, pessoa_id) -> CaixaMovimento:
    with Session(engine) as s:
        return s.exec(select(CaixaMovimento).where(CaixaMovimento.pessoa_id == pessoa_id, CaixaMovimento.tipo == "retirada")).first()


def test_pagamento_direto_leva_numero_e_arquivo_para_a_retirada(ambiente, monkeypatch):
    c, engine, ids = ambiente
    tid = _time(c); _entrada(c, tid)
    rid = _rateio(c, tid).json()["id"]
    aid = _anexo(c, monkeypatch, ids["a"])
    r = c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", headers=_h(), json={
        "destino": "direto", "forma_pagamento": "pix", "numero_documento_pagamento": "E123PIX", "comprovante_anexo_id": aid})
    assert r.status_code == 200, r.text
    linha = next(l for l in r.json()["linhas"] if l["pessoa_id"] == ids["a"])
    assert linha["numero_documento_pagamento"] == "E123PIX" and linha["comprovante_anexo_id"] == aid
    assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 200
    ret = _retirada_de(engine, ids["a"])
    assert ret.numero_documento_pagamento == "E123PIX" and ret.comprovante_anexo_id == aid


def test_comprovante_e_opcional_e_so_vale_no_pagamento_direto(ambiente, monkeypatch):
    c, engine, ids = ambiente
    tid = _time(c); _entrada(c, tid)
    rid = _rateio(c, tid).json()["id"]
    aid = _anexo(c, monkeypatch, ids["a"])
    # crédito no caixa (não é pagamento direto): o comprovante é descartado
    r = c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", headers=_h(), json={
        "destino": "individual", "numero_documento_pagamento": "X", "comprovante_anexo_id": aid})
    linha = next(l for l in r.json()["linhas"] if l["pessoa_id"] == ids["a"])
    assert linha["comprovante_anexo_id"] is None and linha["numero_documento_pagamento"] is None
    # direto sem comprovante confirma normalmente
    c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['b']}", headers=_h(), json={"destino": "direto", "forma_pagamento": "pix"})
    assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 200
    assert _retirada_de(engine, ids["b"]).comprovante_anexo_id is None


def test_arquivo_de_outra_pessoa_ou_fazenda_e_recusado(ambiente, monkeypatch):
    c, engine, ids = ambiente
    tid = _time(c); _entrada(c, tid)
    rid = _rateio(c, tid).json()["id"]
    de_outra_pessoa = _anexo(c, monkeypatch, ids["b"])
    r = c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", headers=_h(), json={
        "destino": "direto", "forma_pagamento": "pix", "comprovante_anexo_id": de_outra_pessoa})
    assert r.status_code == 404


def test_anexar_comprovante_depois_de_confirmado(ambiente, monkeypatch):
    c, engine, ids = ambiente
    tid = _time(c); _entrada(c, tid)
    rid = _rateio(c, tid).json()["id"]
    c.put(f"/cadastro/caixa-time/rateios/{rid}/linhas/{ids['a']}", headers=_h(), json={"destino": "direto", "forma_pagamento": "pix"})
    assert c.post(f"/cadastro/caixa-time/rateios/{rid}/confirmar", headers=_h()).status_code == 200
    ret = _retirada_de(engine, ids["a"])
    assert ret.comprovante_anexo_id is None
    aid = _anexo(c, monkeypatch, ids["a"])
    r = c.put(f"/cadastro/caixa-funcionarios/{ids['a']}/movimentos/{ret.id}/comprovante", headers=_h(),
              json={"numero_documento_pagamento": "  E999  ", "anexo_id": aid})
    assert r.status_code == 200, r.text
    m = r.json()["movimento"]
    assert m["comprovante_anexo_id"] == aid and m["numero_documento_pagamento"] == "E999"
    # a linha do rateio confirmado mostra o mesmo comprovante
    linha = next(l for l in c.get(f"/cadastro/caixa-time/rateios/{rid}", headers=_h()).json()["linhas"] if l["pessoa_id"] == ids["a"])
    assert linha["comprovante_anexo_id"] == aid and linha["numero_documento_pagamento"] == "E999"
    # aparece no extrato do caixa
    ext = c.get(f"/cadastro/caixa-funcionarios/{ids['a']}", headers=_h()).json()
    mov = next(x for x in ext["movimentos"] if x["id"] == ret.id)
    assert mov["comprovante_anexo_id"] == aid


def test_comprovante_so_em_retirada_e_isolado_por_fazenda(ambiente, monkeypatch):
    c, engine, ids = ambiente
    r = c.post("/cadastro/caixa-funcionarios/entradas", headers=_h(), json={
        "pessoa_ids": [ids["a"]], "tipo": "deposito", "valor": 100.0, "data": date.today().isoformat(), "motivo": "teste"})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        dep = s.exec(select(CaixaMovimento).where(CaixaMovimento.pessoa_id == ids["a"])).first()
    assert dep is not None and dep.tipo == "deposito"
    aid = _anexo(c, monkeypatch, ids["a"])
    assert c.put(f"/cadastro/caixa-funcionarios/{ids['a']}/movimentos/{dep.id}/comprovante", headers=_h(),
                 json={"anexo_id": aid}).status_code == 400  # entrada não tem comprovante
    # outra fazenda não enxerga a pessoa
    assert c.put(f"/cadastro/caixa-funcionarios/{ids['a']}/movimentos/{dep.id}/comprovante", headers=_h(2),
                 json={"numero_documento_pagamento": "x"}).status_code == 404
