"""
Vale avulso — travas de dinheiro que faltavam em `rh_contratos.py`:

BUG 1 — reverter/editar um vale cujo abatimento já caiu numa parcela/etapa
        PAGA devolvia o valor à parcela sem tocar na ContaGerencial já
        baixada (`_sincronizar_conta_do_item` só mexe em conta com
        `valor_pago is None`). Resultado: parcela volta a valer o cheio, o
        lançamento pago continua pelo valor abatido, e nasce uma dívida
        fantasma que ninguém cobra.

BUG 2 — vale maior que o total pendente do alvo abatia só o que cabia e
        DESCARTAVA a sobra em silêncio, enquanto a saída de caixa
        (`_sincronizar_conta_vale_avulso`) saía pelo valor cheio.

Os dois casos seguem o precedente que já existe no módulo: recusar com
mensagem acionável (400 do vale de funcionário em `_vale_competencia_paga`)
ou pedir confirmação explícita (409 + flag booleana, como
`confirmar_periodo_pago` em `salvar_dias_diaria`).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaCorrente, ContaGerencial, ValeAvulso, ValeAvulsoAbatimento


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


def _conta_corrente(engine) -> int:
    with Session(engine) as s:
        conta = ContaCorrente(banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6")
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


def _empreitada(c, valores=(1500.0, 1500.0)):
    pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro Trava", "tipos": ["Empreiteiro"]}).json()["id"]
    return c.post("/cadastro/empreitadas", json={
        "pessoa_id": pessoa_id, "descricao": "Roçagem", "valor_total": sum(valores), "tipo_pagamento": "mensal",
        "parcelas": [
            {"data_vencimento": f"2026-0{8 + i}-05", "valor": v} for i, v in enumerate(valores)
        ],
    }).json()


def _contrato(c, valores=(1500.0, 1500.0)):
    pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Prestador Trava", "tipos": ["Prestador de serviços"]}).json()["id"]
    return c.post("/cadastro/contratos", json={
        "pessoa_id": pessoa_id, "descricao": "Consultoria", "valor_total": sum(valores), "forma_pagamento": "mensal",
        "parcelas": [
            {"data_vencimento": f"2026-0{8 + i}-10", "valor": v} for i, v in enumerate(valores)
        ],
    }).json()


def _pagar(c, engine, numero_lancamento, valor):
    with Session(engine) as s:
        conta_id = s.exec(
            select(ContaGerencial.id).where(ContaGerencial.numero_lancamento == numero_lancamento)
        ).first()
    r = c.put(f"/financeiro/lancamentos/{conta_id}/pagar", json={
        "data_pagamento": "2026-08-01", "valor_pago": valor, "forma_pagamento": "pix",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _parcelas(c, empreitada_id):
    empreitada = next(e for e in c.get("/cadastro/empreitadas").json() if e["id"] == empreitada_id)
    return sorted(empreitada["parcelas"], key=lambda p: p["data_vencimento"])


def _conta_por_numero(engine, numero):
    with Session(engine) as s:
        return s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()


# ---------------------------------------------------------------------------
# BUG 1 — parcela já paga não pode ser "descabatida" pelas costas
# ---------------------------------------------------------------------------
class TestReverterValeSobreParcelaPaga:
    def _cenario_parcela_paga(self, c, engine):
        """Vale de 500 abate a 1ª parcela (1500 -> 1000); a conta a pagar
        dessa parcela é então QUITADA por 1000. A partir daqui, mexer no vale
        significaria mexer num dinheiro que já saiu."""
        empreitada = _empreitada(c)
        conta_id = _conta_corrente(engine)
        vale = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_id,
        }).json()["vale"]
        parcelas = _parcelas(c, empreitada["id"])
        assert parcelas[0]["valor"] == 1000.0
        _pagar(c, engine, parcelas[0]["numero_lancamento_gerado"], 1000.0)
        return empreitada, vale, parcelas, conta_id

    def test_excluir_vale_com_parcela_paga_e_recusado(self, client):
        c, engine = client
        empreitada, vale, parcelas, _ = self._cenario_parcela_paga(c, engine)

        r = c.delete(f"/cadastro/vale-avulso/{vale['id']}")
        assert r.status_code == 400, r.text
        detalhe = r.json()["detail"]
        texto = detalhe if isinstance(detalhe, str) else str(detalhe)
        # Mensagem acionável: aponta o lançamento a estornar (precedente do
        # vale de funcionário, que nomeia a competência paga).
        assert parcelas[0]["numero_lancamento_gerado"] in texto
        assert "estorn" in texto.lower()

        # Nada foi tocado: parcela continua abatida, conta continua paga,
        # vale e abatimento continuam de pé.
        assert _parcelas(c, empreitada["id"])[0]["valor"] == 1000.0
        conta = _conta_por_numero(engine, parcelas[0]["numero_lancamento_gerado"])
        assert conta.valor_total == 1000.0 and conta.valor_pago == 1000.0
        with Session(engine) as s:
            assert s.get(ValeAvulso, vale["id"]) is not None
            assert s.exec(
                select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale["id"])
            ).all()

    def test_editar_vale_com_parcela_paga_e_recusado(self, client):
        c, engine = client
        empreitada, vale, parcelas, conta_id = self._cenario_parcela_paga(c, engine)

        r = c.put(f"/cadastro/vale-avulso/{vale['id']}", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 200.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_id,
            "confirmar": True,
        })
        assert r.status_code == 400, r.text

        # O vale segue valendo 500 e a parcela paga segue coerente com a conta.
        with Session(engine) as s:
            assert s.get(ValeAvulso, vale["id"]).valor == 500.0
        assert _parcelas(c, empreitada["id"])[0]["valor"] == 1000.0
        conta = _conta_por_numero(engine, parcelas[0]["numero_lancamento_gerado"])
        assert conta.valor_pago == 1000.0

    def test_parcela_paga_que_o_vale_nao_abateu_nao_bloqueia(self, client):
        """Trava tem que ser cirúrgica: só as parcelas que ESTE vale abateu
        contam. Pagar a 2ª parcela (intocada pelo vale) não pode impedir o
        estorno do vale que só mexeu na 1ª."""
        c, engine = client
        empreitada = _empreitada(c)
        conta_corrente_id = _conta_corrente(engine)
        vale = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
        }).json()["vale"]
        parcelas = _parcelas(c, empreitada["id"])
        _pagar(c, engine, parcelas[1]["numero_lancamento_gerado"], 1500.0)

        r = c.delete(f"/cadastro/vale-avulso/{vale['id']}")
        assert r.status_code == 200, r.text
        assert _parcelas(c, empreitada["id"])[0]["valor"] == 1500.0

    def test_contrato_com_parcela_paga_tambem_e_recusado(self, client):
        c, engine = client
        contrato = _contrato(c)
        conta_corrente_id = _conta_corrente(engine)
        vale = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 500.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
        }).json()["vale"]
        parcelas = sorted(
            next(x for x in c.get("/cadastro/contratos").json() if x["id"] == contrato["id"])["parcelas"],
            key=lambda p: p["data_vencimento"],
        )
        assert parcelas[0]["valor"] == 1000.0
        _pagar(c, engine, parcelas[0]["numero_lancamento_gerado"], 1000.0)

        assert c.delete(f"/cadastro/vale-avulso/{vale['id']}").status_code == 400


# ---------------------------------------------------------------------------
# BUG 2 — vale maior que o pendente não pode sumir com a sobra
# ---------------------------------------------------------------------------
class TestValeMaiorQueOPendente:
    def test_criar_vale_acima_do_pendente_pede_confirmacao(self, client):
        c, engine = client
        contrato = _contrato(c)  # 3000 pendentes
        conta_corrente_id = _conta_corrente(engine)

        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 5000.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 409, r.text
        detalhe = r.json()["detail"]
        assert detalhe["saldo_pendente"] == 3000.0
        assert detalhe["valor_informado"] == 5000.0
        assert detalhe["excedente"] == 2000.0

        # 409 tem que ser atômico: nenhum vale, nenhum abatimento, nenhuma
        # saída de caixa, parcelas intactas.
        with Session(engine) as s:
            assert s.exec(select(ValeAvulso)).all() == []
            assert s.exec(select(ValeAvulsoAbatimento)).all() == []
        parcelas = sorted(
            next(x for x in c.get("/cadastro/contratos").json() if x["id"] == contrato["id"])["parcelas"],
            key=lambda p: p["data_vencimento"],
        )
        assert [p["valor"] for p in parcelas] == [1500.0, 1500.0]

    def test_criar_vale_acima_do_pendente_com_confirmacao_registra_a_sobra(self, client):
        c, engine = client
        contrato = _contrato(c)
        conta_corrente_id = _conta_corrente(engine)

        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 5000.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
            "confirmar_excedente": True,
        })
        assert r.status_code == 200, r.text
        vale = r.json()["vale"]

        # A saída de caixa continua pelo valor cheio (o dinheiro saiu mesmo)...
        conta_vale = _conta_por_numero(engine, vale["numero_lancamento_gerado"])
        assert conta_vale.valor_pago == 5000.0
        # ...mas a sobra deixa de ser invisível: aparece no relatório de vales.
        linha = next(v for v in c.get("/cadastro/vale-avulso/todos").json() if v["id"] == vale["id"])
        assert linha["valor_abatido"] == 3000.0
        assert linha["valor_nao_abatido"] == 2000.0

    def test_vale_igual_ao_pendente_nao_pede_confirmacao(self, client):
        c, engine = client
        contrato = _contrato(c)
        conta_corrente_id = _conta_corrente(engine)
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 3000.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 200, r.text
        linha = next(v for v in c.get("/cadastro/vale-avulso/todos").json() if v["id"] == r.json()["vale"]["id"])
        assert linha["valor_nao_abatido"] == 0.0

    def test_vale_de_diaria_nunca_pede_confirmacao(self, client):
        """Diária não tem parcela agendada — o vale só soma ao saldo abatido
        (`_resumo_diaria`), então "exceder o pendente" não faz sentido aqui."""
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista Trava", "tipos": ["Diarista"]}).json()["id"]
        diaria = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": date.today().isoformat(),
        }).json()
        conta_corrente_id = _conta_corrente(engine)
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "diaria", "origem_id": diaria["id"], "valor": 9999.0,
            "forma_pagamento": "dinheiro", "data_pagamento": date.today().isoformat(),
            "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 200, r.text

    def test_editar_vale_para_acima_do_pendente_pede_confirmacao_sem_corromper(self, client):
        """O PUT reverte e reaplica o abatimento; se o 409 fosse dado no meio,
        o vale ficaria sem abatimento nenhum. A checagem tem que acontecer
        ANTES de qualquer escrita."""
        c, engine = client
        contrato = _contrato(c)
        conta_corrente_id = _conta_corrente(engine)
        vale = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 500.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
        }).json()["vale"]

        r = c.put(f"/cadastro/vale-avulso/{vale['id']}", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 5000.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
            "confirmar": True,
        })
        assert r.status_code == 409, r.text
        # Pendente pós-reversão = 2500 (em aberto) + 500 (devolvido) = 3000.
        assert r.json()["detail"]["saldo_pendente"] == 3000.0

        with Session(engine) as s:
            assert s.get(ValeAvulso, vale["id"]).valor == 500.0
            abatimentos = s.exec(
                select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale["id"])
            ).all()
            assert round(sum(a.valor_abatido for a in abatimentos), 2) == 500.0
        parcelas = sorted(
            next(x for x in c.get("/cadastro/contratos").json() if x["id"] == contrato["id"])["parcelas"],
            key=lambda p: p["data_vencimento"],
        )
        assert [p["valor"] for p in parcelas] == [1000.0, 1500.0]

    def test_editar_vale_para_acima_do_pendente_com_confirmacao_passa(self, client):
        c, engine = client
        contrato = _contrato(c)
        conta_corrente_id = _conta_corrente(engine)
        vale = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 500.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
        }).json()["vale"]

        r = c.put(f"/cadastro/vale-avulso/{vale['id']}", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 5000.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
            "confirmar": True, "confirmar_excedente": True,
        })
        assert r.status_code == 200, r.text
        linha = next(v for v in c.get("/cadastro/vale-avulso/todos").json() if v["id"] == vale["id"])
        assert linha["valor_abatido"] == 3000.0
        assert linha["valor_nao_abatido"] == 2000.0

    def test_contrato_sem_parcela_agendada_pede_confirmacao(self, client):
        """Contrato sem frequência definida não tem parcela nenhuma — o vale
        inteiro é sobra. A mensagem diz isso em vez de "maior que R$ 0,00"."""
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={
            "nome": "Prestador Sem Parcela", "tipos": ["Prestador de serviços"],
        }).json()["id"]
        contrato = c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "Assessoria sob demanda", "valor_total": 1000.0,
        }).json()
        conta_corrente_id = _conta_corrente(engine)

        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 400.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["saldo_pendente"] == 0.0
        assert r.json()["detail"]["excedente"] == 400.0
        assert "Não há parcela/etapa em aberto" in r.json()["detail"]["mensagem"]

        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 400.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
            "confirmar_excedente": True,
        })
        assert r.status_code == 200, r.text
        linha = next(v for v in c.get("/cadastro/vale-avulso/todos").json() if v["id"] == r.json()["vale"]["id"])
        assert linha["valor_abatido"] == 0.0 and linha["valor_nao_abatido"] == 400.0
