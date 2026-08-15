"""
Cartão de crédito (Controle Financeiro > Cartão de crédito) — cadastro,
resolução de competência da fatura, fechamento (manual e preguiçoso na
leitura) e pagamento reaproveitando `criar_lancamento` — ver
fazenda/api/routers/cartao_credito.py.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.rules.patrimonio import somar_meses

# As datas de compra/fechamento abaixo eram fixas em agosto de 2026
# (dia_fechamento=12, compras nos dias 3/5/20) — bomba-relógio real: a
# fatura só fica "aberta" (ver `_fechar_se_vencida` em
# fazenda/api/routers/cartao_credito.py) enquanto `date.today()` REAL da
# execução for igual ou anterior ao dia de fechamento apurado. Em
# 12/08/2026 — o próprio dia de fechamento cadastrado aqui — a fatura já
# nascia fechada e todo teste que dependia dela estar aberta quebrava (bug
# de produção de verdade, corrigido em `_fechar_se_vencida`; mas mesmo
# corrigido, a partir de 13/08/2026 essas datas fixas ficariam pra trás
# permanentemente). Uma nova data fixa só adiaria o problema pro mesmo dia
# do mês que vem — em vez disso, ancora tudo em `date.today()`.
#
# Dois grupos, porque `GET /extrato` SEM `competencia` resolve a fatura pela
# competência de "hoje" DE VERDADE (`date.today()` dentro do próprio
# endpoint) — não pelo mês em que o teste decidiu lançar a compra:
#
#   1) Testes que leem `GET /extrato` sem `competencia` (para pegar o
#      `fatura_id` da fatura "atual") PRECISAM lançar a compra no mês
#      corrente REAL, senão o extrato devolve uma fatura vazia diferente da
#      que acabou de receber o lançamento. `DIA_FECHAMENTO` fica sempre
#      alguns dias à frente do dia de hoje (nunca passa de 28, que existe em
#      todo mês) pra a fatura do mês corrente nunca fechar sozinha durante o
#      teste.
_HOJE = date.today()
DIA_FECHAMENTO = min(_HOJE.day + 5, 28)
DATA_COMPRA_1 = _HOJE
DATA_COMPRA_2 = _HOJE
DATA_COMPRA_3 = _HOJE

#   2) Testes que só conferem o campo `competencia` da resposta do POST (sem
#      depender do extrato "atual") não precisam bater com o mês corrente
#      real — usam um mês seguro e sempre no futuro (o mês que vem), com o
#      fechamento no meio do mês (20) pra nunca esbarrar em mês curto
#      (fevereiro).
_MES_REF = somar_meses(_HOJE, 1)
_MES_SEGUINTE = somar_meses(_MES_REF, 1)
DIA_FECHAMENTO_REF = 20
DATA_COMPRA_REF_ANTES = date(_MES_REF.year, _MES_REF.month, 5)
DATA_COMPRA_REF_DEPOIS = date(_MES_REF.year, _MES_REF.month, 25)
COMPETENCIA_REF = f"{_MES_REF.year:04d}-{_MES_REF.month:02d}"
COMPETENCIA_SEGUINTE = f"{_MES_SEGUINTE.year:04d}-{_MES_SEGUINTE.month:02d}"


@pytest.fixture
def client(monkeypatch):
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
        yield c

    main.app.dependency_overrides.clear()


class TestCadastroCartao:
    def test_cria_cartao(self, client):
        r = client.post("/financeiro/cartoes", json={
            "apelido": "Nubank PJ", "bandeira": "Visa", "dia_fechamento": 12, "dia_vencimento": 20,
        })
        assert r.status_code == 201
        d = r.json()
        assert d["apelido"] == "Nubank PJ"
        assert d["melhor_dia_compra"] == 13

    def test_sem_apelido_da_erro(self, client):
        r = client.post("/financeiro/cartoes", json={"apelido": "  ", "dia_fechamento": 10, "dia_vencimento": 20})
        assert r.status_code == 400

    def test_dia_invalido_da_erro(self, client):
        r = client.post("/financeiro/cartoes", json={"apelido": "Cartão X", "dia_fechamento": 35, "dia_vencimento": 20})
        assert r.status_code == 400

    def test_conta_bancaria_inexistente_da_404(self, client):
        r = client.post("/financeiro/cartoes", json={
            "apelido": "Cartão X", "dia_fechamento": 10, "dia_vencimento": 20, "conta_bancaria_id": 999,
        })
        assert r.status_code == 404

    def test_edita_cartao(self, client):
        cartao_id = client.post("/financeiro/cartoes", json={
            "apelido": "Cartão X", "dia_fechamento": 10, "dia_vencimento": 20,
        }).json()["id"]
        r = client.put(f"/financeiro/cartoes/{cartao_id}", json={
            "apelido": "Cartão Y", "dia_fechamento": 15, "dia_vencimento": 25,
        })
        assert r.status_code == 200
        assert r.json()["apelido"] == "Cartão Y"

    def test_lista_cartoes(self, client):
        client.post("/financeiro/cartoes", json={"apelido": "A", "dia_fechamento": 5, "dia_vencimento": 15})
        r = client.get("/financeiro/cartoes")
        assert r.status_code == 200
        assert len(r.json()) == 1


class TestLancamentoEExtrato:
    def _criar_cartao(self, client, **overrides) -> int:
        payload = {"apelido": "Nubank PJ", "dia_fechamento": DIA_FECHAMENTO, "dia_vencimento": 20, **overrides}
        return client.post("/financeiro/cartoes", json=payload).json()["id"]

    def test_lancamento_antes_do_fechamento_cai_no_mes_corrente(self, client):
        # Só confere o campo `competencia` da resposta — não lê `GET
        # /extrato` "atual", então pode usar o grupo de datas ancorado no mês
        # que vem (ver comentário no topo do arquivo) em vez do mês corrente
        # real.
        cartao_id = self._criar_cartao(client, dia_fechamento=DIA_FECHAMENTO_REF)
        r = client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_REF_ANTES.isoformat(), "descricao": "Posto BR-060", "valor": 480.0,
        })
        assert r.status_code == 201
        assert r.json()["competencia"] == COMPETENCIA_REF

    def test_lancamento_depois_do_fechamento_cai_no_mes_seguinte(self, client):
        cartao_id = self._criar_cartao(client, dia_fechamento=DIA_FECHAMENTO_REF)
        r = client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_REF_DEPOIS.isoformat(), "descricao": "Peças trator", "valor": 620.0,
        })
        assert r.status_code == 201
        assert r.json()["competencia"] == COMPETENCIA_SEGUINTE

    def test_valor_negativo_da_erro(self, client):
        # Nunca chega a olhar a fatura (o `valor <= 0` é rejeitado antes) —
        # qualquer data serve.
        cartao_id = self._criar_cartao(client, dia_fechamento=DIA_FECHAMENTO_REF)
        r = client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_REF_ANTES.isoformat(), "descricao": "X", "valor": 0,
        })
        assert r.status_code == 400

    def test_extrato_soma_lancamentos_ao_vivo(self, client):
        cartao_id = self._criar_cartao(client)
        client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_1.isoformat(), "descricao": "Sal mineral", "valor": 1240.0,
        })
        client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_2.isoformat(), "descricao": "Combustível", "valor": 480.0,
        })
        r = client.get(f"/financeiro/cartoes/{cartao_id}/extrato")
        assert r.status_code == 200
        d = r.json()
        assert d["fatura"]["status"] == "aberta"
        assert d["fatura"]["valor_total"] == 1720.0
        assert len(d["lancamentos"]) == 2

    def test_extrato_competencia_inexistente_404(self, client):
        cartao_id = self._criar_cartao(client)
        r = client.get(f"/financeiro/cartoes/{cartao_id}/extrato", params={"competencia": "2020-01"})
        assert r.status_code == 404


class TestFechamento:
    def _criar_cartao(self, client) -> int:
        return client.post("/financeiro/cartoes", json={
            "apelido": "Cartão milhas", "dia_fechamento": DIA_FECHAMENTO, "dia_vencimento": 20,
            "controla_milhas": True, "milhas_por_real": 2.0,
        }).json()["id"]

    def test_fecha_manualmente_e_congela_totais(self, client):
        cartao_id = self._criar_cartao(client)
        client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_1.isoformat(), "descricao": "Item", "valor": 1000.0,
        })
        fatura_id = client.get(f"/financeiro/cartoes/{cartao_id}/extrato").json()["fatura"]["id"]
        r = client.post(f"/financeiro/cartoes/faturas/{fatura_id}/fechar")
        assert r.status_code == 200
        assert r.json()["status"] == "fechada"
        assert r.json()["valor_total"] == 1000.0
        assert r.json()["milhas_acumuladas"] == 2000

    def test_nao_fecha_duas_vezes(self, client):
        cartao_id = self._criar_cartao(client)
        client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_1.isoformat(), "descricao": "Item", "valor": 100.0,
        })
        fatura_id = client.get(f"/financeiro/cartoes/{cartao_id}/extrato").json()["fatura"]["id"]
        client.post(f"/financeiro/cartoes/faturas/{fatura_id}/fechar")
        r = client.post(f"/financeiro/cartoes/faturas/{fatura_id}/fechar")
        assert r.status_code == 400

    def test_nao_lanca_em_fatura_ja_fechada(self, client):
        cartao_id = self._criar_cartao(client)
        client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_1.isoformat(), "descricao": "Item", "valor": 100.0,
        })
        fatura_id = client.get(f"/financeiro/cartoes/{cartao_id}/extrato").json()["fatura"]["id"]
        client.post(f"/financeiro/cartoes/faturas/{fatura_id}/fechar")
        r = client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_3.isoformat(), "descricao": "Outro item", "valor": 50.0,
        })
        assert r.status_code == 400


class TestPagamento:
    def _criar_fatura_fechada(self, client, valor=1000.0) -> int:
        cartao_id = client.post("/financeiro/cartoes", json={
            "apelido": "Cartão pgto", "dia_fechamento": DIA_FECHAMENTO, "dia_vencimento": 20,
        }).json()["id"]
        client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_1.isoformat(), "descricao": "Item", "valor": valor,
        })
        fatura_id = client.get(f"/financeiro/cartoes/{cartao_id}/extrato").json()["fatura"]["id"]
        client.post(f"/financeiro/cartoes/faturas/{fatura_id}/fechar")
        return fatura_id

    def test_pagar_fatura_gera_lancamento_financeiro(self, client):
        fatura_id = self._criar_fatura_fechada(client, valor=1234.5)
        r = client.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={})
        assert r.status_code == 201
        d = r.json()
        assert d["status"] == "paga"
        assert d["numero_lancamento"]
        assert d["lancamento"]["valor_liquido"] == 1234.5

        lancamentos = client.get("/financeiro/lancamentos").json()["lancamentos"]
        assert any(l["numero_lancamento"] == d["numero_lancamento"] for l in lancamentos)

    def test_nao_paga_fatura_aberta(self, client):
        cartao_id = client.post("/financeiro/cartoes", json={
            "apelido": "Cartão X", "dia_fechamento": DIA_FECHAMENTO, "dia_vencimento": 20,
        }).json()["id"]
        client.post(f"/financeiro/cartoes/{cartao_id}/lancamentos", json={
            "data_compra": DATA_COMPRA_1.isoformat(), "descricao": "Item", "valor": 100.0,
        })
        fatura_id = client.get(f"/financeiro/cartoes/{cartao_id}/extrato").json()["fatura"]["id"]
        r = client.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={})
        assert r.status_code == 400

    def test_nao_paga_duas_vezes(self, client):
        fatura_id = self._criar_fatura_fechada(client)
        client.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={})
        r = client.post(f"/financeiro/cartoes/faturas/{fatura_id}/pagar", json={})
        assert r.status_code == 400
