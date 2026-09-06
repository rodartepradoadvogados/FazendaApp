"""
Duas coisas que a parcela de empreitada/contrato não sabia dizer.

1. QUAL parcela ela é. A tela numerava pela posição na lista ordenada por
   vencimento, então excluir a parcela 3 de 5 fazia a 4 virar "3" — e todo
   recibo já impresso ("vale referente à parcela 3 de 5") passava a apontar
   para outra parcela. `numero`/`numero_total` congelam isso na criação: a
   exclusão deixa o buraco honesto (1, 2, 4, 5 de 5).

2. Quanto foi CONTRATADO. Só existia o líquido a pagar; quando o empreiteiro
   dizia "mas a parcela era R$ 2.000", nada na tela explicava o R$ 1.500.

   `valor_contratado` precisou virar coluna persistida em vez de conta feita
   na hora. A reconstrução tentadora — `bruto = valor + Σ abatimentos` —
   QUEBRA, e o teste
   `test_redistribuir_nao_reescreve_o_contratado_e_a_reconstrucao_quebraria`
   abaixo é a prova: a redistribuição reescreve `valor` sem tocar em nenhum
   `ValeAvulsoAbatimento`.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaCorrente, EmpreitadaParcela, ValeAvulsoAbatimento


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


def _empreitada(c, parcelas=5, valor_parcela=2000.0):
    """Empreita de R$ 10.000 em 5 parcelas mensais de R$ 2.000."""
    pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Sebastião Empreiteiro", "tipos": ["Empreiteiro"]}).json()["id"]
    return c.post("/cadastro/empreitadas", json={
        "pessoa_id": pessoa_id, "descricao": "Roçagem geral do pasto",
        "valor_total": valor_parcela * parcelas, "tipo_pagamento": "mensal",
        "parcelas": [
            {"data_vencimento": date(2026, 8 + i, 4).isoformat(), "valor": valor_parcela}
            for i in range(parcelas)
        ],
    }).json()


class TestNumeracaoDaParcela:
    def test_parcelas_nascem_numeradas_k_de_n(self, client):
        c, engine = client
        empreitada = _empreitada(c)
        numeros = [(p["numero"], p["numero_total"]) for p in empreitada["parcelas"]]
        assert numeros == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]

    def test_excluir_parcela_deixa_o_buraco_e_nao_renumera(self, client):
        """Renumerar quebraria toda referência já impressa em recibo: um vale
        que dizia "parcela 3 de 5" passaria a apontar para outra parcela."""
        c, engine = client
        empreitada = _empreitada(c)
        terceira = next(p for p in empreitada["parcelas"] if p["numero"] == 3)

        assert c.delete(f"/cadastro/empreitadas/parcelas/{terceira['id']}").status_code == 200

        atual = next(e for e in c.get("/cadastro/empreitadas").json() if e["id"] == empreitada["id"])
        assert [(p["numero"], p["numero_total"]) for p in atual["parcelas"]] == [(1, 5), (2, 5), (4, 5), (5, 5)]

    def test_parcelas_de_contrato_tambem_nascem_numeradas(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Consultor", "tipos": ["Prestador de serviços"]}).json()["id"]
        contrato = c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "Consultoria", "valor_total": 3000.0,
            "forma_pagamento": "mensal",
            "parcelas": [
                {"data_vencimento": "2026-09-10", "valor": 1500.0},
                {"data_vencimento": "2026-10-10", "valor": 1500.0},
            ],
        }).json()
        assert [(p["numero"], p["numero_total"]) for p in contrato["parcelas"]] == [(1, 2), (2, 2)]


class TestValorContratado:
    def test_parcela_nasce_com_o_bruto_contratado(self, client):
        c, engine = client
        empreitada = _empreitada(c)
        assert all(p["valor_contratado"] == 2000.0 for p in empreitada["parcelas"])
        assert all(p["valor_abatido_vales"] == 0.0 for p in empreitada["parcelas"])

    def test_vale_abate_o_a_pagar_e_o_serializer_mostra_de_onde_veio(self, client):
        """Contratado R$ 2.000, vale de R$ 500 adiantado, a pagar R$ 1.500 —
        os três números na mesma linha, sem precisar deduzir nada."""
        c, engine = client
        empreitada = _empreitada(c)
        conta_id = _conta_corrente(engine)

        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-18",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200, r.text

        atual = next(e for e in c.get("/cadastro/empreitadas").json() if e["id"] == empreitada["id"])
        primeira = atual["parcelas"][0]
        assert primeira["valor_contratado"] == 2000.0
        assert primeira["valor_abatido_vales"] == 500.0
        assert primeira["valor"] == 1500.0
        # A soma das parcelas cai R$ 500 e o contratado continua R$ 10.000 —
        # a diferença é exatamente o vale.
        assert round(sum(p["valor"] for p in atual["parcelas"]), 2) == 9500.0
        assert round(sum(p["valor_contratado"] for p in atual["parcelas"]), 2) == 10000.0

    def test_redistribuir_nao_reescreve_o_contratado_e_a_reconstrucao_quebraria(self, client):
        """A prova de que `bruto = valor + Σ abatimentos` não serve.

        Depois de redistribuir, o abatimento do vale continua registrado na
        parcela 1 (`ValeAvulsoAbatimento` não é tocado), mas o `valor` dela
        subiu de volta — somar os dois devolve um bruto que ninguém
        contratou. Só um campo persistido sobrevive a isso."""
        c, engine = client
        empreitada = _empreitada(c)
        conta_id = _conta_corrente(engine)
        c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-18",
            "conta_corrente_id": conta_id,
        })

        r = c.post(f"/cadastro/empreitadas/{empreitada['id']}/parcelas/redistribuir")
        assert r.status_code == 200, r.text
        primeira = r.json()["parcelas"][0]

        # R$ 9.500 divididos por 5 = R$ 1.900 em cada parcela.
        assert primeira["valor"] == 1900.0
        # O contratado NÃO foi reescrito.
        assert primeira["valor_contratado"] == 2000.0
        # E o abatimento continua pendurado na parcela 1, intocado — é daqui
        # que sairia o bruto errado de R$ 2.400.
        with Session(engine) as s:
            abatimentos = s.exec(
                select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.item_tipo == "empreitada_parcela")
            ).all()
            parcela = s.get(EmpreitadaParcela, primeira["id"])
            reconstruido = round(parcela.valor + sum(a.valor_abatido for a in abatimentos if a.item_id == parcela.id), 2)
        assert reconstruido == 2400.0
        assert reconstruido != parcela.valor_contratado

    def test_editar_parcela_a_mao_reajusta_o_contratado(self, client):
        """Editar é renegociar: o que a tela edita é o valor A PAGAR, então o
        bruto vira esse valor mais o que já foi adiantado em vale."""
        c, engine = client
        empreitada = _empreitada(c)
        conta_id = _conta_corrente(engine)
        c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-18",
            "conta_corrente_id": conta_id,
        })
        primeira = empreitada["parcelas"][0]

        r = c.put(f"/cadastro/empreitadas/parcelas/{primeira['id']}", json={
            "data_vencimento": primeira["data_vencimento"], "valor": 1800.0,
        })
        assert r.status_code == 200, r.text
        atualizada = next(p for p in r.json()["parcelas"] if p["id"] == primeira["id"])
        assert atualizada["valor"] == 1800.0
        assert atualizada["valor_contratado"] == 2300.0
