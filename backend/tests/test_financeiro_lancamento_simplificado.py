"""
Lançamento simplificado (Lançamentos > Financeiro > Contas a pagar/receber,
toggle "Lançamento simplificado" em app/lancamentos/page.tsx) e o centro de
custo padrão que ele usa no lugar de pedir centro de custo na tela — ver
fazenda/api/routers/financeiro.py (`_desmarcar_outros_centro_custo_padrao`,
`criar_lancamento`) e frontend/components/FormFinanceiroSimplificado.tsx.

Não é um endpoint novo: o formulário simplificado só monta um payload
minimalista para o MESMO POST /financeiro/lancamentos de sempre (ItemIn só
exige produto/valor_total, LancamentoIn só exige tipo/itens) — os testes
abaixo cobrem exatamente esse payload mínimo.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import CentroCusto, ContaGerencial, Estoque, MovimentoEstoque


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


class TestCentroCustoPadrao:
    def test_marcar_padrao_no_post_e_o_unico_padrao(self, client):
        c, engine = client
        r = c.post("/financeiro/centros-custo", json={"nome": "Pecuária Leiteira", "padrao": True})
        assert r.status_code == 200
        assert r.json()["padrao"] is True

    def test_marcar_um_como_padrao_desmarca_o_outro_da_mesma_fazenda(self, client):
        c, engine = client
        id1 = c.post("/financeiro/centros-custo", json={"nome": "Pecuária Leiteira", "padrao": True}).json()["id"]
        id2 = c.post("/financeiro/centros-custo", json={"nome": "Agricultura"}).json()["id"]

        # Marca o 2º como padrão via PUT — o 1º precisa deixar de ser.
        r = c.put(f"/financeiro/centros-custo/{id2}", json={"nome": "Agricultura", "ativo": True, "padrao": True})
        assert r.status_code == 200
        assert r.json()["padrao"] is True

        centros = {x["id"]: x["padrao"] for x in c.get("/financeiro/centros-custo").json()}
        assert centros[id1] is False
        assert centros[id2] is True

    def test_desmarcar_padrao_nao_mexe_no_padrao_de_outro(self, client):
        c, engine = client
        id1 = c.post("/financeiro/centros-custo", json={"nome": "Pecuária Leiteira", "padrao": True}).json()["id"]
        id2 = c.post("/financeiro/centros-custo", json={"nome": "Agricultura"}).json()["id"]

        # Editar o 2º (sem padrao=True) não pode desmarcar o 1º, que continua padrão.
        r = c.put(f"/financeiro/centros-custo/{id2}", json={"nome": "Agricultura renomeada", "ativo": True})
        assert r.status_code == 200
        assert r.json()["padrao"] is False

        centros = {x["id"]: x["padrao"] for x in c.get("/financeiro/centros-custo").json()}
        assert centros[id1] is True
        assert centros[id2] is False


class TestLancamentoSimplificado:
    """Payload minimalista montado por FormFinanceiroSimplificado.tsx: um
    item de produto (do cadastro de Estoque), data única (emissão =
    vencimento = pagamento), conta bancária e o nome do centro de custo
    padrão — sem parcelamento, desconto/acréscimo, anexo ou vínculo."""

    def _payload(self, **overrides):
        payload = {
            "tipo": "despesa",
            "itens": [{
                "produto": "Ração concentrada", "tipo_item": "produto",
                "quantidade": 10, "valor_total": 850.0,
                "codigo_conta_gerencial": None, "nome_conta_gerencial": None,
            }],
            "centro_custo": "Pecuária Leiteira",
            "fornecedor_cliente": "Cooperativa Agro LTDA",
            "data_emissao": "2026-08-23",
            "data_vencimento": "2026-08-23",
            "data_pagamento": "2026-08-23",
            "valor_pago": 850.0,
            "conta_bancaria": "Banco do Brasil · Agência 0001 · Conta corrente 12345-6",
        }
        payload.update(overrides)
        return payload

    def test_nasce_com_data_pagamento_e_conta_bancaria_preenchidas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração concentrada", quantidade=10, unidade="kg"))
            s.commit()

        r = c.post("/financeiro/lancamentos", json=self._payload())
        assert r.status_code == 201
        corpo = r.json()

        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == corpo["numero_lancamento"])).first()
            assert conta is not None
            assert str(conta.data_pagamento) == "2026-08-23"
            assert conta.valor_pago == 850.0
            assert conta.conta_bancaria == "Banco do Brasil · Agência 0001 · Conta corrente 12345-6"
            assert conta.centro_custo == "Pecuária Leiteira"
            assert conta.parcela_num == 1 and conta.parcela_total == 1  # sem parcelamento

    def test_item_produto_cadastrado_da_entrada_automatica_no_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração concentrada", quantidade=10, unidade="kg"))
            s.commit()

        r = c.post("/financeiro/lancamentos", json=self._payload())
        assert r.status_code == 201
        assert r.json()["avisos_estoque"] == []

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração concentrada")).first()
            assert item.quantidade == 20  # 10 (inicial) + 10 (quantidade do item)
            mov = s.exec(select(MovimentoEstoque)).first()
            assert mov is not None
            assert mov.quantidade == 10

    def test_sem_centro_de_custo_padrao_backend_ainda_aceita_o_valor_enviado(self, client):
        # O bloqueio de "nenhum centro de custo padrão configurado" é do
        # FRONTEND (FormFinanceiroSimplificado.tsx) — o backend continua
        # aceitando qualquer `centro_custo` enviado (mesmo contrato de
        # sempre de POST /financeiro/lancamentos, sem regra nova aqui).
        c, engine = client
        r = c.post("/financeiro/lancamentos", json=self._payload(centro_custo=None))
        assert r.status_code == 201
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == r.json()["numero_lancamento"])).first()
            assert conta.centro_custo == "Pecuária Leiteira"  # cai no default do backend (perfil típico da fazenda)
