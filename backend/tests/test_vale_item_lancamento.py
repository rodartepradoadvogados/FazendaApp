"""
Vale de funcionário/empreiteiro a partir de item de lançamento financeiro —
os 21 cenários do plano técnico (ver rules/vale_item.py e
api/routers/cadastro/rh_vale_item.py).

Padrão de `tests/test_vale_folha.py` (fixture `client` com SQLite em memória
+ StaticPool, `dependency_overrides` de `get_session`/`get_current_user`);
o cenário 16 (isolamento entre fazendas) usa o padrão de
`tests/test_financeiro_fazenda_isolamento.py`.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaGerencial, Contrato, Diaria, Empreitada, EmpreitadaParcela, LancamentoItem, PlanoContaGerencial, Pessoa,
    Safra, ValeAvulso, ValeAvulsoAbatimento, ValeFuncionario, ValeParcela,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _criar_pessoa(engine, salario_base: float | None = None, tipo: str = "Funcionário") -> int:
    with Session(engine) as s:
        p = Pessoa(nome="Fulano de Tal", tipo=tipo, salario_base=salario_base)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _criar_lancamento(c, itens: list[dict], tipo: str = "despesa", data_emissao: str = "2026-06-10",
                       centro_custo: str | None = None, parcelas: list[dict] | None = None) -> dict:
    payload = {
        "tipo": tipo,
        "itens": itens,
        "data_emissao": data_emissao,
        "centro_custo": centro_custo,
    }
    if parcelas is not None:
        payload["parcelas"] = parcelas
    r = c.post("/financeiro/lancamentos", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _item_unico(engine, numero_lancamento: str) -> LancamentoItem:
    with Session(engine) as s:
        return s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero_lancamento)).first()


def _itens_do_lancamento(engine, numero_lancamento: str) -> list[LancamentoItem]:
    with Session(engine) as s:
        return s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero_lancamento)).all()


def _criar_empreitada(c, pessoa_id: int, valor_parcela1: float = 1000.0, valor_parcela2: float | None = None,
                       vencimento1: str = "2026-07-05", vencimento2: str = "2026-08-05") -> dict:
    parcelas = [{"data_vencimento": vencimento1, "valor": valor_parcela1}]
    if valor_parcela2 is not None:
        parcelas.append({"data_vencimento": vencimento2, "valor": valor_parcela2})
    r = c.post("/cadastro/empreitadas", json={
        "pessoa_id": pessoa_id, "descricao": "Curral novo", "valor_total": sum(p["valor"] for p in parcelas),
        "tipo_pagamento": "mensal", "parcelas": parcelas,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _criar_diaria(c, pessoa_id: int, valor_diaria: float = 100.0, data_inicio: str = "2026-06-01") -> dict:
    r = c.post("/cadastro/diarias", json={"pessoa_id": pessoa_id, "valor_diaria": valor_diaria, "data_inicio": data_inicio})
    assert r.status_code == 200, r.text
    return r.json()


def _criar_contrato(c, pessoa_id: int, valor_total: float = 2000.0) -> dict:
    r = c.post("/cadastro/contratos", json={
        "pessoa_id": pessoa_id, "descricao": "Prestação de serviço", "valor_total": valor_total,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _marcar_conta_rmca(engine, codigo: str = "3.01.01.001", nome: str = "Ração") -> None:
    with Session(engine) as s:
        s.add(PlanoContaGerencial(codigo=codigo, nome=nome, ativa=True, rmca_custo_alimentacao=True))
        s.commit()


# ---------------------------------------------------------------------------
# 1 — Criação junto com a nota — funcionário
# ---------------------------------------------------------------------------
def test_01_criacao_junto_com_nota_funcionario(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)

    resultado = _criar_lancamento(c, [
        {"produto": "Ração para o gado", "valor_total": 900.0},
        {"produto": "Ração para cães 15kg", "valor_total": 100.0, "vale": {"pessoa_id": pessoa_id, "modo": "folha"}},
    ])
    assert resultado["vales_criados"] and resultado["vales_criados"][0]["vale_tipo"] == "funcionario"
    assert resultado["vales_criados"][0]["valor"] == 100.0

    with Session(engine) as s:
        vales = s.exec(select(ValeFuncionario)).all()
        assert len(vales) == 1
        assert vales[0].valor_total == 100.0
        parcelas = s.exec(select(ValeParcela).where(ValeParcela.vale_id == vales[0].id)).all()
        assert len(parcelas) == 1

        itens = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == resultado["numero_lancamento"])).all()
        item_vale = next(it for it in itens if it.valor_total == 100.0)
        assert item_vale.vale_funcionario_id == vales[0].id

        # Nenhum ContaGerencial extra: só a(s) parcela(s) da própria nota.
        contas = s.exec(select(ContaGerencial)).all()
        assert len(contas) == len(resultado["ids"])


# ---------------------------------------------------------------------------
# 2 — Criação junto com a nota — avulso (empreitada)
# ---------------------------------------------------------------------------
def test_02_criacao_junto_com_nota_avulso(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)  # sem salario_base
    empreitada = _criar_empreitada(c, pessoa_id, valor_parcela1=1000.0, valor_parcela2=1000.0)

    with Session(engine) as s:
        total_contas_antes = len(s.exec(select(ContaGerencial)).all())

    resultado = _criar_lancamento(c, [
        {"produto": "Ração para cães 15kg", "valor_total": 300.0, "vale": {
            "pessoa_id": pessoa_id, "modo": "avulso", "origem_tipo": "empreitada", "origem_id": empreitada["id"],
        }},
    ])
    assert resultado["vales_criados"][0]["vale_tipo"] == "avulso"

    with Session(engine) as s:
        vales = s.exec(select(ValeAvulso)).all()
        assert len(vales) == 1
        assert vales[0].valor == 300.0
        abatimentos = s.exec(select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vales[0].id)).all()
        assert len(abatimentos) == 1

        parcelas = sorted(
            s.exec(select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada["id"])).all(),
            key=lambda p: p.data_vencimento,
        )
        assert parcelas[0].valor == 700.0  # 1000 - 300
        assert parcelas[1].valor == 1000.0  # intocada

        item = _item_unico(engine, resultado["numero_lancamento"])
        assert item.vale_avulso_id == vales[0].id

        total_contas_depois = len(s.exec(select(ContaGerencial)).all())
        # só a conta da própria nota entrou — nada extra para o vale.
        assert total_contas_depois == total_contas_antes + len(resultado["ids"])


# ---------------------------------------------------------------------------
# 3 — Filtro central — Camada A
# ---------------------------------------------------------------------------
def test_03_filtro_camada_a(client):
    c, engine = client
    _marcar_conta_rmca(engine)
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)

    resultado = _criar_lancamento(c, [
        {"produto": "Ração do gado", "valor_total": 900.0, "codigo_conta_gerencial": "3.01.01.001"},
        {"produto": "Ração para cães 15kg", "valor_total": 100.0, "codigo_conta_gerencial": "3.01.01.001",
         "vale": {"pessoa_id": pessoa_id, "modo": "folha"}},
    ], data_emissao="2026-06-10")

    r = c.get("/financeiro/rmca", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["gerencial"]["custo_alimentacao"] == 900.0

    r = c.get("/financeiro/custo-litro-leite", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["custo_total"] == 900.0

    r = c.get("/financeiro/itens-por-conta", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    itens = [it for it in r.json() if it["numero_lancamento"] == resultado["numero_lancamento"]]
    assert len(itens) == 1
    assert itens[0]["valor_total"] == 900.0

    r = c.get("/planejamento/orcamento/comparativo", params={"ano": 2026, "mes_inicio": 6, "mes_fim": 6})
    assert r.status_code == 200, r.text
    assert r.json()["total_realizado"] == 900.0


# ---------------------------------------------------------------------------
# 4 — Filtro central — Camada B
# ---------------------------------------------------------------------------
def test_04_filtro_camada_b(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)

    resultado = _criar_lancamento(c, [
        {"produto": "Insumo agrícola", "valor_total": 900.0},
        {"produto": "Ração para cães 15kg", "valor_total": 100.0, "vale": {"pessoa_id": pessoa_id, "modo": "folha"}},
    ], data_emissao="2026-06-10", centro_custo="Pecuária Leiteira")

    r = c.get("/financeiro/dre", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["despesas_total"] == 900.0

    r = c.get("/financeiro/custo-hectare", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["despesas_total"] == 900.0

    r = c.get("/financeiro/custo-vaca-lote", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["despesas_total"] == 900.0

    with Session(engine) as s:
        s.add(Safra(
            nome="Safra teste", centro_custo="Pecuária Leiteira", data_inicio=date(2026, 6, 1),
            data_fim=date(2026, 6, 30), hectares=10.0, toneladas_produzidas=50.0,
        ))
        s.commit()
        safra_id = s.exec(select(Safra)).first().id
    r = c.get("/financeiro/custo-safra", params={"safra_id": safra_id})
    assert r.status_code == 200, r.text
    assert r.json()["despesas_total"] == 900.0

    # O caixa continua batendo: a nota inteira (R$ 1000) e o item marcado
    # continuam aparecendo no extrato.
    r = c.get("/financeiro/lancamentos")
    assert r.status_code == 200, r.text
    registro = next(l for l in r.json()["lancamentos"] if l["numero_lancamento"] == resultado["numero_lancamento"])
    assert registro["valor"] == 1000.0
    item_vale = next(it for it in registro["itens"] if it["valor_total"] == 100.0)
    assert item_vale["eh_vale"] is True
    assert item_vale["vale_tipo"] == "funcionario"
    assert item_vale["vale_pessoa_id"] == pessoa_id


# ---------------------------------------------------------------------------
# 5 — Rateio em nota parcelada
# ---------------------------------------------------------------------------
def test_05_rateio_em_nota_parcelada(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)

    resultado = _criar_lancamento(c, [
        {"produto": "Insumo agrícola", "valor_total": 820.0},
        {"produto": "Ração para cães 15kg", "valor_total": 180.0, "vale": {"pessoa_id": pessoa_id, "modo": "folha"}},
    ], data_emissao="2026-06-10", parcelas=[
        {"data_vencimento": "2026-07-10", "valor": 500.0},
        {"data_vencimento": "2026-08-10", "valor": 500.0},
    ])
    assert len(resultado["ids"]) == 2

    r = c.get("/financeiro/dre", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["despesas_total"] == 820.0  # 1000 - 180, nem 500 nem 1000

    from fazenda.rules.vale_item import ajuste_vale_por_conta, valor_gerencial
    with Session(engine) as s:
        contas = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == resultado["numero_lancamento"])).all()
        ajustes = ajuste_vale_por_conta(s, contas, None)
        for conta in contas:
            assert ajustes[conta.id] == 90.0
            assert valor_gerencial(conta, ajustes) == 410.0


# ---------------------------------------------------------------------------
# 6 — Marcar item já salvo
# ---------------------------------------------------------------------------
def test_06_marcar_item_ja_salvo(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 400.0}], data_emissao="2026-06-15")
    item = _item_unico(engine, resultado["numero_lancamento"])

    r = c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha", "parcelas": 1})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["valor"] == 400.0  # vem do item, não do body (body não manda valor)
    assert corpo["data_pagamento"] == "2026-06-15"  # vem da nota

    with Session(engine) as s:
        vale = s.get(ValeFuncionario, corpo["vale_id"])
        assert vale.valor_total == 400.0
        assert vale.data_pagamento == date(2026, 6, 15)


# ---------------------------------------------------------------------------
# 7 — Idempotência do marcar
# ---------------------------------------------------------------------------
def test_07_idempotencia_marcar(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 200.0}])
    item = _item_unico(engine, resultado["numero_lancamento"])

    r1 = c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha"})
    assert r1.status_code == 201, r1.text

    r2 = c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha"})
    assert r2.status_code == 409, r2.text

    with Session(engine) as s:
        assert len(s.exec(select(ValeFuncionario)).all()) == 1


# ---------------------------------------------------------------------------
# 8 — Desmarcar excluindo
# ---------------------------------------------------------------------------
def test_08_desmarcar_excluindo(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 500.0}], data_emissao="2026-06-01")
    item = _item_unico(engine, resultado["numero_lancamento"])
    c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha"})

    r = c.delete(f"/cadastro/vale-item/{item.id}", params={"excluir_vale": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["vale_excluido"] is True

    with Session(engine) as s:
        assert s.exec(select(ValeFuncionario)).all() == []
        assert s.exec(select(ValeParcela)).all() == []

    r = c.get("/financeiro/dre", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.json()["despesas_total"] == 500.0


# ---------------------------------------------------------------------------
# 9 — Desmarcar sem excluir
# ---------------------------------------------------------------------------
def test_09_desmarcar_sem_excluir(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 300.0}], data_emissao="2026-06-01")
    item = _item_unico(engine, resultado["numero_lancamento"])
    r = c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha"})
    vale_id = r.json()["vale_id"]

    r = c.delete(f"/cadastro/vale-item/{item.id}", params={"excluir_vale": "false"})
    assert r.status_code == 200, r.text
    assert r.json()["vale_excluido"] is False

    with Session(engine) as s:
        assert s.get(ValeFuncionario, vale_id) is not None  # o vale sobrevive
        item_db = s.get(LancamentoItem, item.id)
        assert item_db.vale_funcionario_id is None  # item voltou a contar

    r = c.get("/cadastro/vales")
    vale_no_relatorio = next(v for v in r.json() if v["id"] == vale_id)
    assert vale_no_relatorio["origem_lancamento"] is None


# ---------------------------------------------------------------------------
# 10 — Desmarcar avulso reverte o abatimento
# ---------------------------------------------------------------------------
def test_10_desmarcar_avulso_reverte_abatimento(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)
    empreitada = _criar_empreitada(c, pessoa_id, valor_parcela1=1000.0)
    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 250.0}], data_emissao="2026-06-01")
    item = _item_unico(engine, resultado["numero_lancamento"])
    c.post(f"/cadastro/vale-item/{item.id}", json={
        "pessoa_id": pessoa_id, "modo": "avulso", "origem_tipo": "empreitada", "origem_id": empreitada["id"],
    })

    with Session(engine) as s:
        parcela = s.exec(select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada["id"])).first()
        assert parcela.valor == 750.0

    r = c.delete(f"/cadastro/vale-item/{item.id}", params={"excluir_vale": "true"})
    assert r.status_code == 200, r.text

    with Session(engine) as s:
        parcela = s.exec(select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada["id"])).first()
        assert parcela.valor == 1000.0
        assert s.exec(select(ValeAvulsoAbatimento)).all() == []


# ---------------------------------------------------------------------------
# 11 — Idempotência do desmarcar
# ---------------------------------------------------------------------------
def test_11_idempotencia_desmarcar(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 150.0}])
    item = _item_unico(engine, resultado["numero_lancamento"])
    c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha"})

    r1 = c.delete(f"/cadastro/vale-item/{item.id}", params={"excluir_vale": "true"})
    assert r1.status_code == 200, r1.text
    r2 = c.delete(f"/cadastro/vale-item/{item.id}", params={"excluir_vale": "true"})
    assert r2.status_code == 404, r2.text


# ---------------------------------------------------------------------------
# 12 — Bloqueio: pessoa avulsa sem origem ativa
# ---------------------------------------------------------------------------
def test_12_bloqueio_sem_origem_ativa(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)  # sem salario_base
    empreitada = _criar_empreitada(c, pessoa_id, valor_parcela1=1000.0)
    with Session(engine) as s:
        e = s.get(Empreitada, empreitada["id"])
        e.status = "concluida"
        s.add(e)
        s.commit()

    r = c.get("/cadastro/vale-item/opcoes", params={"pessoa_id": pessoa_id})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["bloqueio"] is not None
    assert corpo["origens"] == []
    assert corpo["sugestao"] is None

    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 100.0}])
    item = _item_unico(engine, resultado["numero_lancamento"])
    r = c.post(f"/cadastro/vale-item/{item.id}", json={
        "pessoa_id": pessoa_id, "modo": "avulso", "origem_tipo": "empreitada", "origem_id": empreitada["id"],
    })
    assert r.status_code in (400, 404), r.text


# ---------------------------------------------------------------------------
# 13 — Auto-seleção de origem única
# ---------------------------------------------------------------------------
def test_13_auto_selecao_origem_unica(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)  # sem salario_base
    diaria = _criar_diaria(c, pessoa_id)

    r = c.get("/cadastro/vale-item/opcoes", params={"pessoa_id": pessoa_id})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["sugestao"] == {"modo": "avulso", "origem_tipo": "diaria", "origem_id": diaria["id"]}


# ---------------------------------------------------------------------------
# 14 — Duas origens ativas
# ---------------------------------------------------------------------------
def test_14_duas_origens_ativas(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)  # sem salario_base
    _criar_empreitada(c, pessoa_id, valor_parcela1=1000.0)
    _criar_contrato(c, pessoa_id, valor_total=2000.0)

    r = c.get("/cadastro/vale-item/opcoes", params={"pessoa_id": pessoa_id})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["origens"]) == 2
    assert corpo["sugestao"]["origem_id"] is None


# ---------------------------------------------------------------------------
# 15 — Limite de 40% repassado
# ---------------------------------------------------------------------------
def test_15_limite_40_por_cento_repassado(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=1000.0)  # limite = 400
    resultado = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 500.0}])
    item = _item_unico(engine, resultado["numero_lancamento"])

    r = c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha"})
    assert r.status_code == 409, r.text
    assert "competencias_excedidas" in r.json()["detail"]

    r = c.post(f"/cadastro/vale-item/{item.id}", json={"pessoa_id": pessoa_id, "modo": "folha", "confirmar": True})
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# 16 — Isolamento entre fazendas
# ---------------------------------------------------------------------------
@pytest.fixture
def client_multi_fazenda(monkeypatch):
    import tempfile

    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
    from fazenda.models.planos import MODULOS_COMERCIAIS

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "admin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def test_16_isolamento_entre_fazendas(client_multi_fazenda):
    c, engine = client_multi_fazenda

    _como_fazenda(1)
    pessoa_f1_id = _criar_pessoa(engine, salario_base=5000.0)
    with Session(engine) as s:
        p = s.get(Pessoa, pessoa_f1_id)
        p.fazenda_id = 1
        s.add(p)
        s.commit()

    _como_fazenda(2)
    pessoa_f2_id = _criar_pessoa(engine, salario_base=5000.0)
    with Session(engine) as s:
        p = s.get(Pessoa, pessoa_f2_id)
        p.fazenda_id = 2
        s.add(p)
        s.commit()
    empreitada_f2 = _criar_empreitada(c, pessoa_f2_id, valor_parcela1=1000.0)
    resultado_f2 = _criar_lancamento(c, [
        {"produto": "Ração para cães 15kg", "valor_total": 300.0, "vale": {"pessoa_id": pessoa_f2_id, "modo": "folha"}},
    ], data_emissao="2026-06-10")
    item_f2 = _item_unico(engine, resultado_f2["numero_lancamento"])

    # (a) opções de pessoa de outra fazenda -> 404
    _como_fazenda(1)
    r = c.get("/cadastro/vale-item/opcoes", params={"pessoa_id": pessoa_f2_id})
    assert r.status_code == 404, r.text

    # (b) POST em item de outra fazenda -> 404
    r = c.post(f"/cadastro/vale-item/{item_f2.id}", json={"pessoa_id": pessoa_f1_id, "modo": "folha"})
    assert r.status_code == 404, r.text

    # (c) origem de outra fazenda -> 404
    resultado_f1 = _criar_lancamento(c, [{"produto": "Ração para cães 15kg", "valor_total": 200.0}], data_emissao="2026-06-10")
    item_f1 = _item_unico(engine, resultado_f1["numero_lancamento"])
    r = c.post(f"/cadastro/vale-item/{item_f1.id}", json={
        "pessoa_id": pessoa_f1_id, "modo": "avulso", "origem_tipo": "empreitada", "origem_id": empreitada_f2["id"],
    })
    assert r.status_code == 404, r.text

    # (d) DRE da fazenda 1 não é afetado pelo vale da fazenda 2 (300 já saiu como vale lá)
    r = c.get("/financeiro/dre", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["despesas_total"] == 200.0  # só a nota da fazenda 1, sem desconto nenhum


# ---------------------------------------------------------------------------
# 17 — Exclusão da nota
# ---------------------------------------------------------------------------
def test_17_exclusao_da_nota(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)  # sem salario_base
    empreitada = _criar_empreitada(c, pessoa_id, valor_parcela1=1000.0)
    resultado = _criar_lancamento(c, [
        {"produto": "Ração para cães 15kg", "valor_total": 300.0, "vale": {
            "pessoa_id": pessoa_id, "modo": "avulso", "origem_tipo": "empreitada", "origem_id": empreitada["id"],
        }},
    ], data_emissao="2026-06-10")
    conta_id = resultado["ids"][0]

    with Session(engine) as s:
        parcela = s.exec(select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada["id"])).first()
        assert parcela.valor == 700.0

    r = c.post("/exclusoes/confirmar", json={"tipo": "financeiro", "id": str(conta_id)})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "excluido"

    with Session(engine) as s:
        parcela = s.exec(select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada["id"])).first()
        assert parcela.valor == 1000.0  # abatimento revertido
        assert s.exec(select(ValeAvulsoAbatimento)).all() == []
        assert s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == resultado["numero_lancamento"])).all() == []


# ---------------------------------------------------------------------------
# 18 — Excluir o vale pelo relatório de vales
# ---------------------------------------------------------------------------
def test_18_excluir_vale_pelo_relatorio(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    resultado = _criar_lancamento(c, [
        {"produto": "Ração para cães 15kg", "valor_total": 350.0, "vale": {"pessoa_id": pessoa_id, "modo": "folha"}},
    ])
    item = _item_unico(engine, resultado["numero_lancamento"])
    vale_id = item.vale_funcionario_id
    assert vale_id is not None

    r = c.delete(f"/cadastro/vales/{vale_id}")
    assert r.status_code == 200, r.text

    with Session(engine) as s:
        item_db = s.get(LancamentoItem, item.id)
        assert item_db.vale_funcionario_id is None

    r = c.get("/financeiro/dre", params={"data_inicio": "2026-06-01", "data_fim": "2026-06-30"})
    # item voltou aos relatórios (não há mais vale vinculado que o exclua)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 19 — Bloqueio de edição de valor
# ---------------------------------------------------------------------------
def test_19_bloqueio_edicao_valor(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=5000.0)
    resultado = _criar_lancamento(c, [
        {"produto": "Ração para cães 15kg", "valor_total": 220.0, "vale": {"pessoa_id": pessoa_id, "modo": "folha"}},
    ])
    conta_id = resultado["ids"][0]

    r = c.put(f"/financeiro/lancamentos/{conta_id}", json={"valor_total": 500.0})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# 20 — Receita não vira vale
# ---------------------------------------------------------------------------
def test_20_receita_nao_vira_vale(client):
    c, _engine = client
    pessoa_id = _criar_pessoa(_engine, salario_base=5000.0)
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "receita",
        "itens": [{"produto": "Venda de leite", "valor_total": 500.0, "vale": {"pessoa_id": pessoa_id, "modo": "folha"}}],
        "data_emissao": "2026-06-10",
    })
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# 21 — Auto-heal e migração (cabeça única)
# ---------------------------------------------------------------------------
def test_21_migracao_cabeca_unica():
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend / "scripts"))
    from check_alembic_heads import heads

    atuais = heads()
    assert len(atuais) == 1, f"{len(atuais)} cabecas de migracao: {atuais}"
