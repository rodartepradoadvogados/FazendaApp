"""
Encerrar o período de um diarista devendo dinheiro não gerava conta a pagar
nenhuma: o trabalho ficava registrado em `diaria` e sumia do radar
financeiro — nem Agenda, nem Contas a Pagar —, ainda por cima porque a linha
também some da listagem padrão de diárias. Ninguém mais via a dívida.

Os quatro comportamentos que a correção precisa garantir, e que este arquivo
cobre:

1. EMITIR — encerrar com saldo devedor cria a ContaGerencial de verdade
   (mesma receita de `concluir_etapa_empreitada`) e ela aparece em
   `/financeiro/contas-a-pagar` sem que nada tenha mudado lá.
2. CONGELAR — depois do fechamento o apurado para de correr sozinho: o
   resumo lê a fotografia gravada, não recalcula.
3. REABRIR — apaga a cobrança em aberto, mas é RECUSADO quando ela já foi
   paga.
4. RECONCILIAR — baixar a conta no Financeiro zera o saldo aqui.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, Diaria


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


def _diaria(c, valor_diaria=100.0, dias=4):
    """Diarista com `dias + 1` diárias corridas apuradas e nada pago."""
    pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista Encerramento", "tipos": ["Diarista"]}).json()["id"]
    inicio = date.today() - timedelta(days=dias)
    return c.post("/cadastro/diarias", json={
        "pessoa_id": pessoa_id, "valor_diaria": valor_diaria, "data_inicio": inicio.isoformat(),
    }).json()


def _conta_do_encerramento(engine, diaria_id: int) -> ContaGerencial | None:
    with Session(engine) as s:
        diaria = s.get(Diaria, diaria_id)
        if not diaria.numero_lancamento_gerado:
            return None
        return s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == diaria.numero_lancamento_gerado)
        ).first()


class TestEmissaoDaContaAoEncerrar:
    def test_encerrar_devendo_emite_conta_a_pagar(self, client):
        c, engine = client
        d = _diaria(c)  # 5 diárias × R$ 100 = R$ 500 em aberto
        assert d["saldo_devedor"] == 500.0

        r = c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={
            "data_encerramento": date.today().isoformat(),
            "data_vencimento": (date.today() + timedelta(days=20)).isoformat(),
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["status"] == "encerrado"
        assert corpo["cobranca"]["valor"] == 500.0
        assert corpo["cobranca"]["status"] == "em_aberto"

        conta = _conta_do_encerramento(engine, d["id"])
        assert conta is not None
        assert conta.tipo == "despesa"
        assert conta.origem == "auto"
        assert conta.valor_total == 500.0
        assert conta.valor_pago is None
        assert conta.numero_lancamento.startswith("LC-")

    def test_conta_emitida_cai_em_contas_a_pagar(self, client):
        """A Agenda e o Contas a Pagar não precisaram de mudança nenhuma —
        os dois já pegam qualquer conta com `valor_pago < valor_total`. O que
        faltava era só existir a conta."""
        c, engine = client
        d = _diaria(c)
        vencimento = date.today() + timedelta(days=5)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={
            "data_encerramento": date.today().isoformat(), "data_vencimento": vencimento.isoformat(),
        })

        contas = c.get("/financeiro/contas-a-pagar", params={"dias": 30}).json()
        numeros = {conta["numero_lancamento"] for conta in contas}
        with Session(engine) as s:
            esperado = s.get(Diaria, d["id"]).numero_lancamento_gerado
        assert esperado in numeros

    def test_encerrar_quitado_nao_emite_conta_nenhuma(self, client):
        """Conta de R$ 0,00 seria invisível na Agenda e em Contas a Pagar
        (as duas exigem valor_pago < valor_total) e ficaria pendurada para
        sempre."""
        c, engine = client
        d = _diaria(c)
        assert c.post(f"/cadastro/diarias/{d['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 500.0,
        }).status_code == 200

        r = c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        assert r.status_code == 200, r.text
        assert r.json()["cobranca"] is None
        assert r.json()["saldo_devedor"] == 0.0
        assert _conta_do_encerramento(engine, d["id"]) is None

    def test_encerrar_sem_corpo_continua_funcionando(self, client):
        """A chamada sem corpo já existia (frontend antigo) — continua
        valendo, e o último dia trabalhado cai em hoje."""
        c, engine = client
        d = _diaria(c)
        r = c.put(f"/cadastro/diarias/{d['id']}/encerrar")
        assert r.status_code == 200, r.text
        assert r.json()["data_encerramento"] == date.today().isoformat()
        assert r.json()["cobranca"]["valor"] == 500.0

    def test_ultimo_dia_antes_do_inicio_e_recusado(self, client):
        c, engine = client
        d = _diaria(c)
        r = c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={
            "data_encerramento": (date.today() - timedelta(days=30)).isoformat(),
        })
        assert r.status_code == 400
        assert "anterior ao início" in r.json()["detail"]


class TestCongelamento:
    def test_apurado_para_de_correr_e_vem_da_fotografia(self, client):
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})

        with Session(engine) as s:
            diaria = s.get(Diaria, d["id"])
            assert diaria.encerramento_numero_diarias == 5
            assert diaria.encerramento_total_apurado == 500.0
            assert diaria.encerramento_saldo_devedor == 500.0
            # A data de fim é quem faz o contador parar — sem ela, o período
            # "encerrado" seguia somando uma diária por dia, invisível.
            assert diaria.data_fim == date.today()

            # Mexer no valor da diária no banco (o equivalente a qualquer
            # recálculo posterior) não pode mudar o que já foi cobrado.
            diaria.valor_diaria = 999.0
            s.add(diaria)
            s.commit()

        resumo = next(x for x in c.get("/cadastro/diarias", params={"incluir_finalizadas": True}).json() if x["id"] == d["id"])
        assert resumo["periodo_congelado"] is True
        assert resumo["total_ate_hoje"] == 500.0
        assert resumo["saldo_devedor"] == 500.0

    def test_corrigir_dias_de_periodo_congelado_e_recusado(self, client):
        """Aceitar em silêncio seria pior: a escrita passaria e não mudaria
        nada no valor já cobrado — trabalho perdido sem aviso."""
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})

        r = c.put(f"/cadastro/diarias/{d['id']}/dias", json={
            "periodo_inicio": (date.today() - timedelta(days=4)).isoformat(),
            "periodo_fim": date.today().isoformat(),
            "dias_nao_trabalhados": [(date.today() - timedelta(days=1)).isoformat()],
        })
        assert r.status_code == 400
        assert "congelado" in r.json()["detail"]

    def test_pagamento_avulso_em_periodo_congelado_e_recusado(self, client):
        """A dívida está em Contas a Pagar — pagar por aqui criaria um
        segundo pagamento para a mesma dívida, com a conta emitida
        continuando a cobrar."""
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})

        r = c.post(f"/cadastro/diarias/{d['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 500.0,
        })
        assert r.status_code == 400
        assert "congelado" in r.json()["detail"]

    def test_encerrar_duas_vezes_e_recusado(self, client):
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        r = c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        assert r.status_code == 400
        assert "já foi encerrado" in r.json()["detail"]


class TestReabertura:
    def test_reabrir_apaga_a_cobranca_em_aberto_e_descongela(self, client):
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        assert _conta_do_encerramento(engine, d["id"]) is not None

        r = c.put(f"/cadastro/diarias/{d['id']}/reabrir")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["status"] == "ativo"
        assert corpo["data_encerramento"] is None
        assert corpo["cobranca"] is None
        assert corpo["periodo_congelado"] is False

        with Session(engine) as s:
            diaria = s.get(Diaria, d["id"])
            assert diaria.numero_lancamento_gerado is None
            assert diaria.encerramento_saldo_devedor is None
            # A data de fim tinha sido posta pelo encerramento — volta a vazia.
            assert diaria.data_fim is None
            assert s.exec(select(ContaGerencial)).all() == []

    def test_reabrir_com_conta_ja_paga_e_recusado(self, client):
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        conta = _conta_do_encerramento(engine, d["id"])

        assert c.put(f"/financeiro/lancamentos/{conta.id}/pagar", json={
            "data_pagamento": date.today().isoformat(), "valor_pago": 500.0,
        }).status_code == 200

        r = c.put(f"/cadastro/diarias/{d['id']}/reabrir")
        assert r.status_code == 400
        assert "Estorne a baixa" in r.json()["detail"]
        # E a conta continua lá, paga — a recusa não pode ter apagado nada.
        assert _conta_do_encerramento(engine, d["id"]).valor_pago == 500.0

    def test_reabrir_diaria_aberta_e_recusado(self, client):
        c, engine = client
        d = _diaria(c)
        r = c.put(f"/cadastro/diarias/{d['id']}/reabrir")
        assert r.status_code == 400


class TestReconciliacao:
    def test_baixar_a_conta_no_financeiro_zera_o_saldo_da_diaria(self, client):
        """O buraco que a autocrítica da proposta apontou: pagar a conta no
        Financeiro não voltava para a diária, que seguia devendo para
        sempre."""
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        conta = _conta_do_encerramento(engine, d["id"])

        assert c.put(f"/financeiro/lancamentos/{conta.id}/pagar", json={
            "data_pagamento": date.today().isoformat(), "valor_pago": 500.0,
        }).status_code == 200

        resumo = next(x for x in c.get("/cadastro/diarias", params={"incluir_finalizadas": True}).json() if x["id"] == d["id"])
        assert resumo["saldo_devedor"] == 0.0
        assert resumo["valor_pago"] == 500.0
        assert resumo["cobranca"]["status"] == "pago"

    def test_baixa_parcial_abate_so_o_que_foi_pago(self, client):
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        conta = _conta_do_encerramento(engine, d["id"])

        assert c.put(f"/financeiro/lancamentos/{conta.id}/pagar", json={
            "data_pagamento": date.today().isoformat(), "valor_pago": 300.0,
        }).status_code == 200

        resumo = next(x for x in c.get("/cadastro/diarias", params={"incluir_finalizadas": True}).json() if x["id"] == d["id"])
        assert resumo["valor_pago"] == 300.0
        assert resumo["saldo_devedor"] == 200.0

    def test_cobranca_aparece_na_folha_unificada(self, client):
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})

        linhas = c.get("/cadastro/folha-pagamento-unificada").json()
        encerramentos = [l for l in linhas if l["origem_subtipo"] == "encerramento"]
        assert len(encerramentos) == 1
        assert encerramentos[0]["valor"] == 500.0
        assert encerramentos[0]["status"] == "pendente"


class TestExclusaoDaDiariaEncerrada:
    def test_excluir_diaria_leva_a_cobranca_em_aberto_junto(self, client):
        """Cobrança órfã em Contas a Pagar, sem nada que explique de onde
        veio, é pior do que não ter cobrança nenhuma."""
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})

        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria", "id": str(d["id"])})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.exec(select(ContaGerencial)).all() == []

    def test_excluir_diaria_com_cobranca_paga_e_recusado(self, client):
        c, engine = client
        d = _diaria(c)
        c.put(f"/cadastro/diarias/{d['id']}/encerrar", json={"data_encerramento": date.today().isoformat()})
        conta = _conta_do_encerramento(engine, d["id"])
        c.put(f"/financeiro/lancamentos/{conta.id}/pagar", json={
            "data_pagamento": date.today().isoformat(), "valor_pago": 500.0,
        })

        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria", "id": str(d["id"])})
        assert r.status_code == 400
        assert "já foi paga" in r.json()["detail"]
