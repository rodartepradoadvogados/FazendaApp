"""
Testes dos gaps de exclusão de Pessoal/RH via motor genérico de exclusões:
G3 (`diaria_pagamento`), G9 (`empreitada`), G10 (`contrato`), G14 (`diaria`).

Cada tipo é exercitado nos três eixos transversais do plano (Parte 5):
funciona, reverte o estado exatamente, isolamento entre fazendas — mais o
fluxo de aprovação (operador solicita, admin aprova e a exclusão de fato só
acontece na aprovação) para ao menos um dos tipos com efeito colateral
(`_alvos` roda de novo no aprovar_pendente).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    AgendaManual,
    ContaCorrente,
    ContaGerencial,
    Contrato,
    ContratoFazenda,
    ContratoParcela,
    Diaria,
    DiariaAuditoria,
    DiariaPagamento,
    Empreitada,
    EmpreitadaEtapa,
    EmpreitadaParcela,
    Pessoa,
    SolicitacaoExclusao,
    ValeAvulso,
    ValeAvulsoAbatimento,
)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    # Os testes de isolamento trocam get_fazenda_atual_id para 1 — /exclusoes
    # exige contrato ativo quando a fazenda não é None (ver _contrato_ativo
    # em main.py), então a fazenda 1 precisa de um ContratoFazenda ativo.
    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.commit()

    import main
    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"

    class _FakeOperador:
        id = 2
        papel = "operador"
        ativo = True
        username = "operador-teste"
        permissoes = "parametros"

    admin = _FakeAdmin()
    estado = {"user": admin, "admin": admin}
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: estado["user"]
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine, estado, _FakeOperador()

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


def _criar_pessoa(engine, nome: str = "Fulano", fazenda_id: int | None = None) -> int:
    with _sessao(engine) as s:
        p = Pessoa(nome=nome, tipo="Diarista", fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _marcar_pago(engine, numero_lancamento: str) -> None:
    with _sessao(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
        conta.valor_pago = conta.valor_total
        conta.data_pagamento = date.today()
        s.add(conta)
        s.commit()


def _criar_diaria(c, pessoa_id: int, valor_diaria: float = 100.0, data_inicio: date | None = None) -> dict:
    r = c.post("/cadastro/diarias", json={
        "pessoa_id": pessoa_id, "valor_diaria": valor_diaria,
        "data_inicio": (data_inicio or date.today()).isoformat(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _registrar_pagamento_diaria(c, diaria_id: int, valor: float, data_pagamento: date | None = None) -> dict:
    r = c.post(f"/cadastro/diarias/{diaria_id}/pagamentos", json={
        "data_pagamento": (data_pagamento or date.today()).isoformat(), "valor": valor,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _criar_empreitada_mensal(c, pessoa_id: int, valores: list[float]) -> dict:
    parcelas = [{"data_vencimento": date(2026, i + 1, 5).isoformat(), "valor": v} for i, v in enumerate(valores)]
    r = c.post("/cadastro/empreitadas", json={
        "pessoa_id": pessoa_id, "descricao": "Reforma do curral", "valor_total": sum(valores),
        "tipo_pagamento": "mensal", "parcelas": parcelas,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _criar_empreitada_por_etapa(c, pessoa_id: int, etapas: list[dict]) -> dict:
    r = c.post("/cadastro/empreitadas", json={
        "pessoa_id": pessoa_id, "descricao": "Construção do galpão", "valor_total": sum(e["valor"] for e in etapas),
        "tipo_pagamento": "por_etapa", "etapas": etapas,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _criar_contrato(c, pessoa_id: int, forma_pagamento: str | None, valores: list[float] | None = None) -> dict:
    payload = {
        "pessoa_id": pessoa_id, "descricao": "Arrendamento de pasto", "valor_total": sum(valores) if valores else 1000.0,
        "forma_pagamento": forma_pagamento,
    }
    if forma_pagamento and valores:
        payload["parcelas"] = [{"data_vencimento": date(2026, i + 1, 5).isoformat(), "valor": v} for i, v in enumerate(valores)]
    r = c.post("/cadastro/contratos", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _criar_conta_corrente(engine) -> int:
    with _sessao(engine) as s:
        conta = ContaCorrente(banco="Banco Teste", agencia="0001", numero_conta="1-1")
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


def _criar_vale_avulso(c, origem_tipo: str, origem_id: int, valor: float, forma_pagamento: str = "desconto_proximo_pagamento", conta_corrente_id: int | None = None) -> dict:
    r = c.post("/cadastro/vale-avulso", json={
        "origem_tipo": origem_tipo, "origem_id": origem_id, "valor": valor,
        "forma_pagamento": forma_pagamento, "data_pagamento": date.today().isoformat(),
        "conta_corrente_id": conta_corrente_id,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# G3 — diaria_pagamento
# ---------------------------------------------------------------------------
class TestExclusaoDiariaPagamento:
    def test_impacto_lista_lancamento_e_saldo(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine, "Zé Diarista")
        diaria = _criar_diaria(c, pessoa_id, valor_diaria=100.0)
        pagamento = _registrar_pagamento_diaria(c, diaria["id"], valor=40.0)
        pagamento_id = pagamento["pagamentos"][0]["id"]
        assert pagamento["saldo_devedor"] == 60.0

        r = c.post("/exclusoes/impacto", json={"tipo": "diaria_pagamento", "id": str(pagamento_id)})
        assert r.status_code == 200, r.text
        impacto = r.json()["impacto"]
        assert any("R$ 40.00" in i and "Zé Diarista" in i for i in impacto)
        assert any("Lançamento financeiro" in i for i in impacto)
        assert any("60.00" in i and "100.00" in i for i in impacto)

    def test_excluir_sobe_saldo_e_remove_lancamento(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        diaria = _criar_diaria(c, pessoa_id, valor_diaria=100.0)
        pagamento = _registrar_pagamento_diaria(c, diaria["id"], valor=40.0)
        pagamento_id = pagamento["pagamentos"][0]["id"]
        numero_lancamento = pagamento["pagamentos"][0]["numero_lancamento_gerado"]
        assert numero_lancamento

        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria_pagamento", "id": str(pagamento_id)})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            assert s.get(DiariaPagamento, pagamento_id) is None
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
            assert conta is None

        r = c.get("/cadastro/diarias")
        assert r.status_code == 200
        resumo = next(d for d in r.json() if d["id"] == diaria["id"])
        assert resumo["saldo_devedor"] == 100.0
        assert resumo["valor_pago"] == 0.0

    def test_isolamento_entre_fazendas(self, client):
        c, engine, estado, _ = client
        pessoa_id = _criar_pessoa(engine, fazenda_id=2)
        with _sessao(engine) as s:
            diaria = Diaria(pessoa_id=pessoa_id, valor_diaria=50.0, data_inicio=date.today(), fazenda_id=2)
            s.add(diaria)
            s.commit()
            s.refresh(diaria)
            pagamento = DiariaPagamento(diaria_id=diaria.id, data_pagamento=date.today(), valor=10.0, fazenda_id=2)
            s.add(pagamento)
            s.commit()
            s.refresh(pagamento)
            pagamento_id = pagamento.id

        from fazenda.auth import get_fazenda_atual_id
        import main
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        try:
            r = c.get("/exclusoes/buscar", params={"tipo": "diaria_pagamento"})
            assert r.status_code == 200
            assert all(item["id"] != pagamento_id for item in r.json())

            r = c.post("/exclusoes/impacto", json={"tipo": "diaria_pagamento", "id": str(pagamento_id)})
            assert r.status_code == 404
        finally:
            del main.app.dependency_overrides[get_fazenda_atual_id]

    def test_operador_solicita_e_aprovacao_executa(self, client):
        c, engine, estado, operador = client
        pessoa_id = _criar_pessoa(engine)
        diaria = _criar_diaria(c, pessoa_id, valor_diaria=100.0)
        pagamento = _registrar_pagamento_diaria(c, diaria["id"], valor=40.0)
        pagamento_id = pagamento["pagamentos"][0]["id"]

        estado["user"] = operador
        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria_pagamento", "id": str(pagamento_id)})
        assert r.status_code == 200
        assert r.json()["status"] == "solicitado"

        with _sessao(engine) as s:
            # A solicitação existe, mas o pagamento em si ainda está lá.
            assert s.get(DiariaPagamento, pagamento_id) is not None
            sol = s.exec(select(SolicitacaoExclusao).where(SolicitacaoExclusao.status == "pendente")).first()
            assert sol is not None
            sol_id = sol.id

        estado["user"] = estado["admin"]
        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200, r.text

        with _sessao(engine) as s:
            assert s.get(DiariaPagamento, pagamento_id) is None


# ---------------------------------------------------------------------------
# G9 — empreitada
# ---------------------------------------------------------------------------
class TestExclusaoEmpreitada:
    def test_excluir_sem_pagamento_remove_parcelas_e_contas(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        empreitada = _criar_empreitada_mensal(c, pessoa_id, [1000.0, 1000.0])
        numeros = [p["numero_lancamento_gerado"] for p in empreitada["parcelas"]]

        r = c.post("/exclusoes/confirmar", json={"tipo": "empreitada", "id": str(empreitada["id"])})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            assert s.get(Empreitada, empreitada["id"]) is None
            assert s.exec(select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada["id"])).all() == []
            for n in numeros:
                assert s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == n)).first() is None

    def test_com_parcela_paga_bloqueia(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        empreitada = _criar_empreitada_mensal(c, pessoa_id, [1000.0, 1000.0])
        _marcar_pago(engine, empreitada["parcelas"][0]["numero_lancamento_gerado"])

        r = c.post("/exclusoes/impacto", json={"tipo": "empreitada", "id": str(empreitada["id"])})
        assert r.status_code == 400
        assert "paga" in r.json()["detail"].lower()
        assert "Estorne a baixa" in r.json()["detail"]

        # A empreitada continua intacta — nada foi mutado pela prévia bloqueada.
        with _sessao(engine) as s:
            assert s.get(Empreitada, empreitada["id"]) is not None

    def test_reverte_vale_avulso_sem_deixar_abatimento_orfao(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        empreitada = _criar_empreitada_mensal(c, pessoa_id, [1000.0, 1000.0])
        vale = _criar_vale_avulso(c, "empreitada", empreitada["id"], valor=300.0)
        vale_id = vale["vale"]["id"]

        with _sessao(engine) as s:
            abatimentos = s.exec(select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale_id)).all()
            assert len(abatimentos) == 1
            parcela1 = s.get(EmpreitadaParcela, empreitada["parcelas"][0]["id"])
            assert parcela1.valor == 700.0  # 1000 - 300 abatido pelo vale

        r = c.post("/exclusoes/confirmar", json={"tipo": "empreitada", "id": str(empreitada["id"])})
        assert r.status_code == 200, r.text

        with _sessao(engine) as s:
            assert s.get(ValeAvulso, vale_id) is None
            assert s.exec(select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale_id)).all() == []

    def test_por_etapa_com_etapa_concluida_nao_paga_e_excluivel(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        empreitada = _criar_empreitada_por_etapa(c, pessoa_id, [{"nome": "Fundação", "valor": 2000.0}])
        etapa_id = empreitada["etapas"][0]["id"]

        r = c.put(f"/cadastro/empreitadas/{empreitada['id']}/etapas/{etapa_id}/concluir")
        assert r.status_code == 200, r.text

        r = c.post("/exclusoes/confirmar", json={"tipo": "empreitada", "id": str(empreitada["id"])})
        assert r.status_code == 200, r.text

        with _sessao(engine) as s:
            assert s.get(Empreitada, empreitada["id"]) is None
            assert s.get(EmpreitadaEtapa, etapa_id) is None

    def test_isolamento_entre_fazendas(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine, fazenda_id=2)
        with _sessao(engine) as s:
            e = Empreitada(pessoa_id=pessoa_id, descricao="Outra fazenda", valor_total=500.0, tipo_pagamento="mensal", fazenda_id=2)
            s.add(e)
            s.commit()
            s.refresh(e)
            empreitada_id = e.id

        from fazenda.auth import get_fazenda_atual_id
        import main
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        try:
            r = c.get("/exclusoes/buscar", params={"tipo": "empreitada"})
            assert r.status_code == 200
            assert all(item["id"] != empreitada_id for item in r.json())

            r = c.post("/exclusoes/impacto", json={"tipo": "empreitada", "id": str(empreitada_id)})
            assert r.status_code == 404
        finally:
            del main.app.dependency_overrides[get_fazenda_atual_id]


# ---------------------------------------------------------------------------
# G10 — contrato
# ---------------------------------------------------------------------------
class TestExclusaoContrato:
    def test_excluir_remove_parcelas_contas_e_lembrete_agenda(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        contrato = _criar_contrato(c, pessoa_id, forma_pagamento="mensal", valores=[500.0, 500.0])
        numeros = [p["numero_lancamento_gerado"] for p in contrato["parcelas"]]

        r = c.post("/exclusoes/confirmar", json={"tipo": "contrato", "id": str(contrato["id"])})
        assert r.status_code == 200, r.text

        with _sessao(engine) as s:
            assert s.get(Contrato, contrato["id"]) is None
            assert s.exec(select(ContratoParcela).where(ContratoParcela.contrato_id == contrato["id"])).all() == []
            for n in numeros:
                assert s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == n)).first() is None

    def test_com_parcela_paga_bloqueia(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        contrato = _criar_contrato(c, pessoa_id, forma_pagamento="mensal", valores=[500.0, 500.0])
        _marcar_pago(engine, contrato["parcelas"][0]["numero_lancamento_gerado"])

        r = c.post("/exclusoes/impacto", json={"tipo": "contrato", "id": str(contrato["id"])})
        assert r.status_code == 400
        assert "paga" in r.json()["detail"].lower()

    def test_sem_frequencia_excluivel_remove_lembrete_agenda(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        contrato = _criar_contrato(c, pessoa_id, forma_pagamento=None)
        assert contrato["origem_lembrete_agenda_id"]
        lembrete_id = contrato["origem_lembrete_agenda_id"]

        r = c.post("/exclusoes/impacto", json={"tipo": "contrato", "id": str(contrato["id"])})
        assert r.status_code == 200
        assert any("lembrete" in i.lower() for i in r.json()["impacto"])

        r = c.post("/exclusoes/confirmar", json={"tipo": "contrato", "id": str(contrato["id"])})
        assert r.status_code == 200, r.text

        with _sessao(engine) as s:
            assert s.get(Contrato, contrato["id"]) is None
            assert s.get(AgendaManual, lembrete_id) is None

    def test_isolamento_entre_fazendas(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine, fazenda_id=2)
        with _sessao(engine) as s:
            contrato = Contrato(pessoa_id=pessoa_id, descricao="Outra fazenda", valor_total=500.0, fazenda_id=2)
            s.add(contrato)
            s.commit()
            s.refresh(contrato)
            contrato_id = contrato.id

        from fazenda.auth import get_fazenda_atual_id
        import main
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        try:
            r = c.post("/exclusoes/impacto", json={"tipo": "contrato", "id": str(contrato_id)})
            assert r.status_code == 404
        finally:
            del main.app.dependency_overrides[get_fazenda_atual_id]


# ---------------------------------------------------------------------------
# G14 — diaria
# ---------------------------------------------------------------------------
class TestExclusaoDiaria:
    def test_sem_pagamento_remove_auditorias_e_vale_desconto(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        diaria = _criar_diaria(c, pessoa_id, valor_diaria=100.0)
        with _sessao(engine) as s:
            aud = DiariaAuditoria(diaria_id=diaria["id"], periodo_inicio=date(2026, 1, 1), periodo_fim=date(2026, 1, 7), dias_trabalhados=7)
            s.add(aud)
            s.commit()
            s.refresh(aud)
            auditoria_id = aud.id

        vale = _criar_vale_avulso(c, "diaria", diaria["id"], valor=20.0, forma_pagamento="desconto_proximo_pagamento")
        vale_id = vale["vale"]["id"]

        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria", "id": str(diaria["id"])})
        assert r.status_code == 200, r.text

        with _sessao(engine) as s:
            assert s.get(Diaria, diaria["id"]) is None
            assert s.get(DiariaAuditoria, auditoria_id) is None
            assert s.get(ValeAvulso, vale_id) is None

    def test_com_pagamento_bloqueia(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        diaria = _criar_diaria(c, pessoa_id, valor_diaria=100.0)
        _registrar_pagamento_diaria(c, diaria["id"], valor=40.0)

        r = c.post("/exclusoes/impacto", json={"tipo": "diaria", "id": str(diaria["id"])})
        assert r.status_code == 400
        assert "pagamento" in r.json()["detail"].lower()

    def test_com_vale_saida_de_caixa_bloqueia(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        diaria = _criar_diaria(c, pessoa_id, valor_diaria=100.0)
        conta_id = _criar_conta_corrente(engine)
        _criar_vale_avulso(c, "diaria", diaria["id"], valor=50.0, forma_pagamento="pix", conta_corrente_id=conta_id)

        r = c.post("/exclusoes/impacto", json={"tipo": "diaria", "id": str(diaria["id"])})
        assert r.status_code == 400
        assert "vale" in r.json()["detail"].lower()

    def test_apos_excluir_pagamentos_diaria_fica_excluivel(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine)
        diaria = _criar_diaria(c, pessoa_id, valor_diaria=100.0)
        pagamento = _registrar_pagamento_diaria(c, diaria["id"], valor=40.0)
        pagamento_id = pagamento["pagamentos"][0]["id"]

        r = c.post("/exclusoes/impacto", json={"tipo": "diaria", "id": str(diaria["id"])})
        assert r.status_code == 400

        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria_pagamento", "id": str(pagamento_id)})
        assert r.status_code == 200, r.text

        r = c.post("/exclusoes/confirmar", json={"tipo": "diaria", "id": str(diaria["id"])})
        assert r.status_code == 200, r.text
        with _sessao(engine) as s:
            assert s.get(Diaria, diaria["id"]) is None

    def test_isolamento_entre_fazendas(self, client):
        c, engine, _, _ = client
        pessoa_id = _criar_pessoa(engine, fazenda_id=2)
        with _sessao(engine) as s:
            diaria = Diaria(pessoa_id=pessoa_id, valor_diaria=50.0, data_inicio=date.today(), fazenda_id=2)
            s.add(diaria)
            s.commit()
            s.refresh(diaria)
            diaria_id = diaria.id

        from fazenda.auth import get_fazenda_atual_id
        import main
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        try:
            r = c.get("/exclusoes/buscar", params={"tipo": "diaria"})
            assert r.status_code == 200
            assert all(item["id"] != diaria_id for item in r.json())

            r = c.post("/exclusoes/impacto", json={"tipo": "diaria", "id": str(diaria_id)})
            assert r.status_code == 404
        finally:
            del main.app.dependency_overrides[get_fazenda_atual_id]
