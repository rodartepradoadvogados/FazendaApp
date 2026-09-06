"""
Dois bugs reais reportados em produção no módulo de Folha de Pagamento:

1. Rescisão de contrato não impedia a folha de gerar pagamento de competência
   POSTERIOR à data de desligamento (tanto na geração recorrente "lazy pull"
   quanto numa folha futura já gerada antes de a rescisão ser fechada).
2. Lançamento de folha não era idempotente: nada impedia criar duas linhas
   para a mesma pessoa/competência (duplicado em Ações > Folha de Pagamento),
   e a listagem não se recuperava de duplicatas já existentes no banco.

Mesmo padrão de fixture de test_vale_folha.py/test_rescisao_fluxo.py.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.api.routers.cadastro.rh_folha as rh_folha
from fazenda.models import ContaGerencial, FolhaPagamento, Pessoa, RescisaoFuncionario


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


def _criar_pessoa(engine, nome: str = "Valéria Bonfim", salario_base: float = 3000.0) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=salario_base, data_admissao=date(2024, 1, 1))
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _fechar_rescisao(c, pessoa_id: int, data_desligamento: date) -> None:
    """Fluxo real de 2 etapas (simulação -> fechar), igual ao usuário faria."""
    r = c.post("/cadastro/rescisoes", json={
        "pessoa_id": pessoa_id, "tipo_rescisao": "pedido_demissao",
        "data_desligamento": data_desligamento.isoformat(),
    })
    assert r.status_code == 200, r.text
    registro_id = r.json()["id"]
    r = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})
    assert r.status_code == 200, r.text


class _FakeDate(date):
    """Congela `date.today()` em rh_folha para simular meses futuros sem
    depender da data real do sistema (mesmo truque de sempre: subclasse que
    só sobrescreve `today`, mantendo o construtor original)."""
    _hoje = date(2026, 8, 27)

    @classmethod
    def today(cls):
        return cls._hoje


# ---------------------------------------------------------------------------
# Bug 1 — rescisão não encerra pagamentos futuros
# ---------------------------------------------------------------------------
def test_rescisao_impede_geracao_de_folha_recorrente_apos_desligamento(client, monkeypatch):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    # Folha recorrente lançada em julho — sem a correção, o "lazy pull" geraria
    # agosto e (mais adiante no tempo) setembro sem olhar pra rescisão.
    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
        "recorrente": True, "dia_vencimento": 5,
    })
    assert r.status_code == 200, r.text

    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    # Avança o "hoje" do módulo para outubro, simulando o tempo passando bem
    # depois da rescisão — a geração recorrente teria toda a chance de criar
    # agosto/setembro/outubro se não checasse a rescisão.
    monkeypatch.setattr(rh_folha, "date", _FakeDate)
    monkeypatch.setattr(_FakeDate, "_hoje", date(2026, 10, 15))

    r = c.get("/cadastro/folha-pagamento")
    assert r.status_code == 200, r.text
    competencias = {f["competencia"] for f in r.json() if f["pessoa_id"] == pessoa_id}
    # Setembro/outubro (competência de início POSTERIOR ao desligamento de
    # 05/08) nunca deveriam ser geradas.
    assert "2026-09" not in competencias
    assert "2026-10" not in competencias


def test_rescisao_remove_folha_futura_ja_gerada_antes_do_fechamento(client):
    """Ordem cronológica real do bug: a folha de setembro já existia (gerada
    ou lançada manualmente) ANTES de a rescisão de agosto ser fechada — a
    correção precisa também limpar essa linha já suja, não só bloquear
    geração nova."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-09", "valor_bruto": 3000.0,
    })
    assert r.status_code == 200, r.text
    numero_lancamento = r.json()["numero_lancamento_gerado"]

    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    r = c.get("/cadastro/folha-pagamento")
    assert r.status_code == 200, r.text
    competencias = {f["competencia"] for f in r.json() if f["pessoa_id"] == pessoa_id}
    assert "2026-09" not in competencias

    # A conta a pagar vinculada (nunca paga) some junto — não fica órfã.
    with Session(engine) as s:
        assert s.exec(select(FolhaPagamento).where(FolhaPagamento.competencia == "2026-09")).first() is None
        assert s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)
        ).first() is None


def test_rescisao_nao_remove_folha_ja_paga(client):
    """Mesmo depois de rescindida, uma folha já PAGA (histórico real) nunca é
    apagada — só a pendente/futura indevida."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-09", "valor_bruto": 3000.0,
        "status": "pago", "data_pagamento": "2026-10-05",
    })
    assert r.status_code == 200, r.text

    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    r = c.get("/cadastro/folha-pagamento")
    competencias = {f["competencia"] for f in r.json() if f["pessoa_id"] == pessoa_id}
    assert "2026-09" in competencias


def test_lancar_folha_bloqueada_apos_rescisao_fechada(client):
    """Defesa em profundidade: o lançamento MANUAL também é bloqueado para
    uma competência posterior ao desligamento, não só a geração automática."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine)
    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-09", "valor_bruto": 3000.0,
    })
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Bug 2 — pagamentos duplicados na folha
# ---------------------------------------------------------------------------
def test_lancar_folha_duas_vezes_mesma_competencia_e_rejeitado(client):
    """Reproduz o duplicado: sem a correção, este segundo POST criava uma
    SEGUNDA linha de folha para a mesma pessoa/competência (200 OK)."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, nome="Alane dos Santos")

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-08", "valor_bruto": 2500.0,
    })
    assert r.status_code == 200, r.text

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-08", "valor_bruto": 2500.0,
    })
    assert r.status_code == 400, r.text

    with Session(engine) as s:
        registros = s.exec(
            select(FolhaPagamento).where(
                FolhaPagamento.pessoa_id == pessoa_id, FolhaPagamento.competencia == "2026-08",
            )
        ).all()
        assert len(registros) == 1


def test_listagem_normaliza_duplicata_ja_existente_no_banco(client):
    """Simula o dado histórico já duplicado (duas linhas gravadas direto no
    banco, como teria acontecido em produção antes da correção) e confirma
    que a listagem se autocorrige — mantém uma linha só e remove a conta a
    pagar órfã da outra, em vez de só escondê-la."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, nome="Jorbeson Nunes")

    with Session(engine) as s:
        s.add(FolhaPagamento(
            pessoa_id=pessoa_id, competencia="2026-08", valor_bruto=2200.0, valor_liquido=2200.0,
            status="pendente", numero_lancamento_gerado="LC-0001",
        ))
        s.add(ContaGerencial(
            numero_lancamento="LC-0001", descricao="Folha de pagamento — Jorbeson Nunes (2026-08)",
            data_vencimento=date(2026, 9, 5), data_competencia=date(2026, 8, 1),
            fornecedor_cliente="Jorbeson Nunes", tipo_documento="Folha de pagamento",
            centro_custo="Pecuária Leiteira", valor_total=2200.0, parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
        ))
        s.add(FolhaPagamento(
            pessoa_id=pessoa_id, competencia="2026-08", valor_bruto=2200.0, valor_liquido=2200.0,
            status="pendente", numero_lancamento_gerado="LC-0002",
        ))
        s.add(ContaGerencial(
            numero_lancamento="LC-0002", descricao="Folha de pagamento — Jorbeson Nunes (2026-08)",
            data_vencimento=date(2026, 9, 5), data_competencia=date(2026, 8, 1),
            fornecedor_cliente="Jorbeson Nunes", tipo_documento="Folha de pagamento",
            centro_custo="Pecuária Leiteira", valor_total=2200.0, parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
        ))
        s.commit()

    # Confirma o duplicado ANTES de ler a listagem corrigida.
    with Session(engine) as s:
        assert len(s.exec(
            select(FolhaPagamento).where(FolhaPagamento.pessoa_id == pessoa_id)
        ).all()) == 2

    r = c.get("/cadastro/folha-pagamento")
    assert r.status_code == 200, r.text
    linhas = [f for f in r.json() if f["pessoa_id"] == pessoa_id]
    assert len(linhas) == 1
    assert linhas[0]["numero_lancamento_gerado"] == "LC-0002"  # mantém a mais recente

    with Session(engine) as s:
        assert len(s.exec(
            select(FolhaPagamento).where(FolhaPagamento.pessoa_id == pessoa_id)
        ).all()) == 1
        assert s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-0001")
        ).first() is None
        assert s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-0002")
        ).first() is not None


# ---------------------------------------------------------------------------
# Bug 3 — folha do MÊS DO DESLIGAMENTO gerada por cima da rescisão
#
# Caso real reportado em set/2026 (Jorbeson Nunes e Valéria Bonfim): rescisão
# "Dispensa sem justa causa" com desligamento em 05/08/2026, status FECHADA e
# já quitada — e mesmo assim a aba Folha de Pagamento mostrava uma folha
# PENDENTE de competência 2026-08, salário CHEIO, vencendo 05/09/2026.
#
# A rescisão já paga `saldo_salario` (ver rules/folha_rh.py::calcular_rescisao)
# = salario_base / 30 × dias trabalhados no mês do desligamento. Gerar também a
# folha desse mesmo mês é pagar o mês duas vezes.
# ---------------------------------------------------------------------------
def test_folha_do_mes_do_desligamento_nao_e_gerada(client, monkeypatch):
    """A competência do PRÓPRIO mês do desligamento não pode ser gerada: o
    saldo de salário daqueles dias já está dentro da rescisão."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, nome="Jorbeson Nunes", salario_base=3393.0)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3393.0,
        "recorrente": True, "dia_vencimento": 5,
    })
    assert r.status_code == 200, r.text

    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    monkeypatch.setattr(rh_folha, "date", _FakeDate)
    monkeypatch.setattr(_FakeDate, "_hoje", date(2026, 9, 6))

    r = c.get("/cadastro/folha-pagamento")
    assert r.status_code == 200, r.text
    competencias = {f["competencia"] for f in r.json() if f["pessoa_id"] == pessoa_id}
    assert "2026-07" in competencias  # o mês inteiro trabalhado continua devido
    assert "2026-08" not in competencias, "folha do mês do desligamento duplica o saldo de salário da rescisão"
    assert "2026-09" not in competencias


def test_folha_do_mes_do_desligamento_ja_gerada_e_removida_no_fechamento(client):
    """Ordem cronológica do caso de produção: a folha de agosto já existia
    quando a rescisão de 05/08 foi fechada. O fechamento tem que limpá-la
    (junto com a conta a pagar não paga)."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, nome="Valéria Bonfim", salario_base=3393.0)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-08", "valor_bruto": 3393.0,
    })
    assert r.status_code == 200, r.text
    numero_lancamento = r.json()["numero_lancamento_gerado"]

    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    with Session(engine) as s:
        assert s.exec(select(FolhaPagamento).where(FolhaPagamento.competencia == "2026-08")).first() is None
        assert s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)
        ).first() is None


def test_lancar_folha_do_mes_do_desligamento_e_bloqueado(client):
    """Defesa em profundidade: o lançamento MANUAL do mês do desligamento
    também é recusado."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine)
    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-08", "valor_bruto": 3000.0,
    })
    assert r.status_code == 400, r.text


def test_folha_paga_do_mes_do_desligamento_nunca_e_apagada(client):
    """Se a folha do mês do desligamento JÁ FOI PAGA, o dinheiro saiu — o
    fechamento não reescreve histórico financeiro, só deixa de gerar o que
    ainda não existe."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-08", "valor_bruto": 3000.0,
        "status": "pago", "data_pagamento": "2026-09-05",
    })
    assert r.status_code == 200, r.text

    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    r = c.get("/cadastro/folha-pagamento")
    competencias = {f["competencia"] for f in r.json() if f["pessoa_id"] == pessoa_id}
    assert "2026-08" in competencias


# ---------------------------------------------------------------------------
# O que NÃO pode quebrar: readmissão
# ---------------------------------------------------------------------------
def test_readmissao_depois_da_rescisao_volta_a_gerar_folha(client, monkeypatch):
    """Pessoa desligada em 05/08 e READMITIDA em 01/11 (nova `data_admissao`,
    posterior ao desligamento) volta a receber folha a partir do mês da
    readmissão — a rescisão antiga não pode calar a pessoa para sempre. Os
    meses entre o desligamento e a readmissão continuam bloqueados."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
        "recorrente": True, "dia_vencimento": 5,
    })
    assert r.status_code == 200, r.text
    _fechar_rescisao(c, pessoa_id, date(2026, 8, 5))

    # Readmissão: o cadastro da pessoa passa a ter admissão posterior à saída.
    with Session(engine) as s:
        pessoa = s.get(Pessoa, pessoa_id)
        pessoa.data_admissao = date(2026, 11, 1)
        pessoa.ativo = True
        s.add(pessoa)
        s.commit()

    # Lançamento manual da folha do mês da readmissão é aceito de novo...
    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-11", "valor_bruto": 3000.0,
        "recorrente": True, "dia_vencimento": 5,
    })
    assert r.status_code == 200, r.text

    # ...e os meses em que a pessoa estava fora continuam recusados.
    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-09", "valor_bruto": 3000.0,
    })
    assert r.status_code == 400, r.text

    # A recorrência do novo vínculo volta a rodar normalmente.
    monkeypatch.setattr(rh_folha, "date", _FakeDate)
    monkeypatch.setattr(_FakeDate, "_hoje", date(2026, 12, 20))
    r = c.get("/cadastro/folha-pagamento")
    assert r.status_code == 200, r.text
    competencias = {f["competencia"] for f in r.json() if f["pessoa_id"] == pessoa_id}
    assert "2026-12" in competencias
    assert "2026-09" not in competencias
    assert "2026-10" not in competencias
