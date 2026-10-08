"""Réguas de referência: o arquivo versionado precisa obedecer às regras de validação."""
import copy
from datetime import date

from fazenda.rules import reguas_referencia as rr

HOJE = date(2026, 10, 8)


def _dados():
    return copy.deepcopy(rr.carregar())


def test_arquivo_versionado_e_valido():
    assert rr.validar(rr.carregar(), hoje=HOJE) == []


def test_validada_exige_fonte_nacional_e_internacional():
    d = _dados()
    r = next(x for x in d["reguas"] if x["codigo"] == "comida_receita")
    nacionais = {f["id"] for f in d["fontes"] if f["origem"] == "nacional"}
    r["fontes"] = [x for x in r["fontes"] if x in nacionais]
    assert any("exige ao menos uma fonte nacional e uma internacional" in e for e in rr.validar(d, hoje=HOJE))


def test_selo_alto_exige_duas_de_cada_lado():
    d = _dados()
    r = next(x for x in d["reguas"] if x["codigo"] == "comida_receita")
    intl = [f["id"] for f in d["fontes"] if f["origem"] == "internacional"]
    r["fontes"] = [x for x in r["fontes"] if x not in intl[1:]]
    assert any("selo alta" in e for e in rr.validar(d, hoje=HOJE))


def test_regua_nao_validada_nao_pode_exibir_faixa():
    d = _dados()
    r = next(x for x in d["reguas"] if x["codigo"] == "parcelas_receita")
    r["exibir_faixa"] = True
    r["faixa"] = {"max": 20}
    assert any("NAO_VALIDADA" in e for e in rr.validar(d, hoje=HOJE))


def test_fonte_com_licenca_vetada_e_recusada():
    d = _dados()
    d["fontes"].append({"id": "ahdb", "nome": "AHDB", "url": "https://ahdb.org.uk/dairy/x", "origem": "internacional", "ano": 2025, "licenca": "citar_com_link"})
    assert any("não permite uso comercial" in e for e in rr.validar(d, hoje=HOJE))


def test_datas_no_futuro_e_fonte_inexistente_sao_recusadas():
    d = _dados()
    d["conferida_em"] = "2026-12-01"
    d["reguas"][0]["fontes"].append("nao_existe")
    erros = rr.validar(d, hoje=HOJE)
    assert any("futuro" in e for e in erros)
    assert any("inexistentes" in e for e in erros)


def test_regua_com_condicao_pendente_nao_exibe_faixa():
    d = _dados()
    cob = next(x for x in d["reguas"] if x["codigo"] == "cobertura_divida")
    assert cob["exibir_faixa"] is False and cob["condicao_para_exibir"]
    cob["exibir_faixa"] = True
    assert any("condição pendente" in e for e in rr.validar(d, hoje=HOJE))


def test_publico_vigente_mostra_faixa_so_das_reguas_liberadas():
    p = rr.publico(hoje=HOJE)
    assert p["vencida"] is False
    por = {r["codigo"]: r for r in p["reguas"]}
    assert por["comida_receita"]["faixa"]["max"] == 55
    assert por["parcelas_receita"]["faixa"] is None
    assert por["cobertura_divida"]["faixa"] is None
    assert por["comida_receita"]["fontes"], "cada régua leva suas fontes para o pop-up"


def test_publico_vencida_esconde_todas_as_faixas():
    p = rr.publico(hoje=date(2027, 10, 9))
    assert p["vencida"] is True
    assert all(r["faixa"] is None and r["exibir_faixa"] is False for r in p["reguas"])


def test_endpoint_devolve_a_carga_publica():
    from fastapi.testclient import TestClient

    from fazenda.api.routers.reguas_referencia import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    r = TestClient(app).get("/financeiro/reguas-referencia")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["versao"] == "2026-10" and len(corpo["reguas"]) >= 7
