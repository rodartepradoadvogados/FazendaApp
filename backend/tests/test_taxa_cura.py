"""
Testes de `GET /sanidade/taxa-cura` e das rotas que marcam "curado? sim/não"
(`POST /sanidade/protocolos/lancamentos/{id}/cura`, o alias antigo
`POST /sanidade/mastite/cura` e `POST /sanidade/aplicacoes/{id}/cura`).

Cobre os 4 defeitos corrigidos:
  1. Vazamento entre fazendas no relatório (sem filtro de fazenda_id).
  2. IDOR ao marcar cura de um caso de outra fazenda.
  3. Viés que infla a taxa: casos nunca respondidos ficavam invisíveis —
     agora entram como "não avaliados" e não contam na taxa.
  4. Um protocolo em andamento (último dia ainda não todo aplicado) NUNCA é
     pendência de avaliação — só entra como "não avaliado" quando terminou.
  5. A rota antiga /mastite/cura continua funcionando (retrocompatibilidade).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Sanidade
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

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
        permissoes = "sanidade"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _etapa(dia, produto="Antibiótico X", dosagem=10.0, unidade="ml", via="Intramuscular"):
    return {"dia": dia, "produto": produto, "dosagem": dosagem, "unidade": unidade, "via": via}


def _lancar_protocolo_simples(c, fazenda_id, numero, data_inicio, nome_protocolo):
    """Cadastra um protocolo de UMA etapa (D1) e lança para um animal, como a
    fazenda `fazenda_id`. Devolve o lançamento serializado (com aplicações)."""
    _como_fazenda(fazenda_id)
    protocolo_id = c.post("/cadastro/protocolos-sanitarios", json={
        "nome": nome_protocolo, "etapas": [_etapa(1)],
    }).json()["id"]
    r = c.post("/sanidade/protocolos/lancamentos", json={
        "protocolo_id": protocolo_id, "numeros_matriz": [numero], "data_inicio": data_inicio,
    })
    assert r.status_code == 201, r.text
    return r.json()["lancamentos"][0]


def _concluir_protocolo(c, fazenda_id, data_referencia):
    """Marca REALIZADO(s) o(s) evento(s) de protocolo sanitário pendente(s) na
    Agenda até `data_referencia`, como a fazenda atual — deixa o protocolo
    "terminado" (todas as aplicações do último dia feitas), mesma regra que a
    Agenda usa para liberar a pergunta "curado?"."""
    _como_fazenda(fazenda_id)
    eventos = c.get("/agenda/", params={"data": data_referencia, "dias": 5}).json()["eventos"]
    marcados = 0
    for e in eventos:
        if e["id"].startswith("protocolo_sanitario_"):
            assert c.post("/agenda/realizados", json={"evento_id": e["id"]}).status_code == 200
            marcados += 1
    assert marcados > 0, "nenhum evento de protocolo sanitário encontrado para concluir"


class TestIsolamentoEntreFazendas:
    """Defeito 1: relatório vazava casos de cura entre fazendas."""

    def test_fazenda_nao_ve_caso_de_cura_de_outra(self, client):
        c, engine = client
        lanc1 = _lancar_protocolo_simples(c, 1, "700", "2026-03-01", "Protocolo F1")
        _concluir_protocolo(c, 1, "2026-03-01")
        r = c.post(f"/sanidade/protocolos/lancamentos/{lanc1['id']}/cura", json={"lancamento_id": lanc1["id"], "curada": True})
        assert r.status_code == 200, r.text

        lanc2 = _lancar_protocolo_simples(c, 2, "800", "2026-03-01", "Protocolo F2")
        _concluir_protocolo(c, 2, "2026-03-01")
        r = c.post(f"/sanidade/protocolos/lancamentos/{lanc2['id']}/cura", json={"lancamento_id": lanc2["id"], "curada": True})
        assert r.status_code == 200, r.text

        _como_fazenda(1)
        dados1 = c.get("/sanidade/taxa-cura").json()
        numeros1 = {caso["numero"] for caso in dados1["casos"]}
        assert "700" in numeros1
        assert "800" not in numeros1, "fazenda 1 viu o caso de cura da fazenda 2 — vazamento"

        _como_fazenda(2)
        dados2 = c.get("/sanidade/taxa-cura").json()
        numeros2 = {caso["numero"] for caso in dados2["casos"]}
        assert "800" in numeros2
        assert "700" not in numeros2, "fazenda 2 viu o caso de cura da fazenda 1 — vazamento"

    def test_aplicacao_avulsa_de_outra_fazenda_nao_aparece(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Sanidade(numero_matriz="900", produto="Ivermectina", data_aplicacao=date(2026, 3, 1), curada=True, fazenda_id=1))
            s.add(Sanidade(numero_matriz="901", produto="Ivermectina", data_aplicacao=date(2026, 3, 1), curada=True, fazenda_id=2))
            s.commit()

        _como_fazenda(1)
        casos1 = {c_["numero"] for c_ in c.get("/sanidade/taxa-cura").json()["casos"]}
        assert "900" in casos1 and "901" not in casos1

        _como_fazenda(2)
        casos2 = {c_["numero"] for c_ in c.get("/sanidade/taxa-cura").json()["casos"]}
        assert "901" in casos2 and "900" not in casos2


class TestIdorAoMarcarCura:
    """Defeito 2: marcar cura de um caso de outra fazenda deveria dar 404."""

    def test_marcar_cura_protocolo_de_outra_fazenda_da_404(self, client):
        c, engine = client
        lanc2 = _lancar_protocolo_simples(c, 2, "800", "2026-03-01", "Protocolo alheio")
        _concluir_protocolo(c, 2, "2026-03-01")

        _como_fazenda(1)
        r = c.post(f"/sanidade/protocolos/lancamentos/{lanc2['id']}/cura", json={"lancamento_id": lanc2["id"], "curada": True})
        assert r.status_code == 404

    def test_rota_antiga_mastite_cura_de_outra_fazenda_tambem_da_404(self, client):
        c, engine = client
        lanc2 = _lancar_protocolo_simples(c, 2, "800", "2026-03-01", "Protocolo alheio 2")
        _concluir_protocolo(c, 2, "2026-03-01")

        _como_fazenda(1)
        r = c.post("/sanidade/mastite/cura", json={"lancamento_id": lanc2["id"], "curada": True})
        assert r.status_code == 404

    def test_marcar_cura_aplicacao_avulsa_de_outra_fazenda_da_404(self, client):
        c, engine = client
        with Session(engine) as s:
            from sqlmodel import select
            s.add(Sanidade(numero_matriz="901", produto="Ivermectina", data_aplicacao=date(2026, 3, 1), fazenda_id=2))
            s.commit()
            aplicacao_id = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "901")).first().id

        _como_fazenda(1)
        r = c.post(f"/sanidade/aplicacoes/{aplicacao_id}/cura", json={"curada": True})
        assert r.status_code == 404


class TestCasosNaoAvaliados:
    """Defeito 3/4: protocolo terminado sem resposta vira 'não avaliado' e sai
    de fora do cálculo da taxa; protocolo em andamento não é pendência."""

    def _cenario(self, c):
        # A: terminado + respondido "curado" -> avaliado, curada=True
        lanc_a = _lancar_protocolo_simples(c, 1, "701", "2026-03-01", "Protocolo A")
        _concluir_protocolo(c, 1, "2026-03-01")
        c.post(f"/sanidade/protocolos/lancamentos/{lanc_a['id']}/cura", json={"lancamento_id": lanc_a["id"], "curada": True})

        # B: terminado + respondido "não curado" -> avaliado, curada=False
        lanc_b = _lancar_protocolo_simples(c, 1, "702", "2026-03-01", "Protocolo B")
        _concluir_protocolo(c, 1, "2026-03-01")
        c.post(f"/sanidade/protocolos/lancamentos/{lanc_b['id']}/cura", json={"lancamento_id": lanc_b["id"], "curada": False})

        # C: terminado, NUNCA respondido -> não avaliado
        lanc_c = _lancar_protocolo_simples(c, 1, "703", "2026-03-01", "Protocolo C")
        _concluir_protocolo(c, 1, "2026-03-01")

        # D: NÃO terminado (aplicação pendente) -> nem avaliado nem não avaliado
        lanc_d = _lancar_protocolo_simples(c, 1, "704", "2026-03-01", "Protocolo D")

        return lanc_a, lanc_b, lanc_c, lanc_d

    def test_protocolo_terminado_e_nao_respondido_aparece_como_nao_avaliado(self, client):
        c, engine = client
        _, _, lanc_c, _ = self._cenario(c)
        _como_fazenda(1)
        dados = c.get("/sanidade/taxa-cura").json()
        caso_c = next(caso for caso in dados["casos"] if caso["numero"] == "703")
        assert caso_c["avaliado"] is False
        assert caso_c["curada"] is None

    def test_protocolo_em_andamento_nao_entra_como_pendente(self, client):
        c, engine = client
        self._cenario(c)
        _como_fazenda(1)
        dados = c.get("/sanidade/taxa-cura").json()
        numeros = {caso["numero"] for caso in dados["casos"]}
        assert "704" not in numeros, "protocolo com o último dia ainda pendente não deveria aparecer no relatório"

    def test_taxa_calculada_so_sobre_avaliados(self, client):
        c, engine = client
        self._cenario(c)
        _como_fazenda(1)
        dados = c.get("/sanidade/taxa-cura").json()
        assert dados["total_avaliados"] == 2  # A e B
        assert dados["curados"] == 1  # A
        assert dados["nao_curados"] == 1  # B
        assert dados["taxa_cura_pct"] == 50.0
        assert dados["total_nao_avaliados"] == 1  # C

    def test_cobertura_de_avaliacao_reflete_o_nao_avaliado(self, client):
        c, engine = client
        self._cenario(c)
        _como_fazenda(1)
        dados = c.get("/sanidade/taxa-cura").json()
        # 2 avaliados de 3 casos "prontos para avaliação" (A, B, C) — D fica de fora da conta.
        assert dados["cobertura_avaliacao_pct"] == pytest.approx(66.7, abs=0.1)

    def test_responder_caso_nao_avaliado_fora_da_agenda_atualiza_o_relatorio(self, client):
        # Defeito 4: mesmo sem o evento na Agenda (>60 dias), dá pra responder
        # via relatório — usa o mesmo POST.
        c, engine = client
        _, _, lanc_c, _ = self._cenario(c)
        _como_fazenda(1)
        r = c.post(f"/sanidade/protocolos/lancamentos/{lanc_c['id']}/cura", json={"lancamento_id": lanc_c["id"], "curada": True})
        assert r.status_code == 200
        dados = c.get("/sanidade/taxa-cura").json()
        assert dados["total_avaliados"] == 3
        assert dados["total_nao_avaliados"] == 0
        caso_c = next(caso for caso in dados["casos"] if caso["numero"] == "703")
        assert caso_c["avaliado"] is True and caso_c["curada"] is True


class TestRotaAntigaRetrocompativel:
    """Defeito 5: /mastite/cura serve qualquer protocolo, não só mastite, e
    precisa continuar funcionando (app em produção ainda a chama)."""

    def test_mastite_cura_marca_protocolo_nao_mastite(self, client):
        c, engine = client
        lanc = _lancar_protocolo_simples(c, 1, "705", "2026-03-01", "Vermifugação (não é mastite)")
        _concluir_protocolo(c, 1, "2026-03-01")

        _como_fazenda(1)
        r = c.post("/sanidade/mastite/cura", json={"lancamento_id": lanc["id"], "curada": True})
        assert r.status_code == 200, r.text
        assert r.json()["curada"] is True

        dados = c.get("/sanidade/taxa-cura").json()
        caso = next(caso for caso in dados["casos"] if caso["numero"] == "705")
        assert caso["avaliado"] is True and caso["curada"] is True
