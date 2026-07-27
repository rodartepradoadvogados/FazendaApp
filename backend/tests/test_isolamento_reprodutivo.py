"""
Fase 4D — isolamento por fazenda do domínio Reprodutivo (Servico,
TipoServicoReprodutivo/MetodoServicoReprodutivo, ProtocoloIatf*, Parto).

Todos os modelos deste domínio (fazenda/models/reprodutivo.py) já tinham
`fazenda_id` desde fases anteriores; este arquivo cobre os testes de
isolamento específicos que nunca tinham sido escritos: listagem, ownership em
edição (PUT) e criação (POST) nos routers fazenda/api/routers/reproducao.py e
fazenda/api/routers/cadastro/servicos.py.

Segue o mesmo padrão de tests/test_multi_fazenda_isolamento.py (fixture
`client` própria, banco SQLite isolado por teste, `_como_fazenda(fazenda_id)`
para trocar o "caller" no meio do teste) — arquivo self-contained, não reusa
nem edita o arquivo de referência.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

# Precisa ser setado ANTES de qualquer import de fazenda.* — ver comentário
# equivalente em test_multi_fazenda_isolamento.py.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, MetodoServicoReprodutivo, Parto,
    ProtocoloIatfAplicacao, ProtocoloIatfLancamento, Servico, TipoServicoReprodutivo,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    ids: dict[str, int] = {}

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        s.add(Animal(numero="9001", sexo="F", ativo=True, fazenda_id=1))
        s.commit()

        # Vocabulário de Serviço/Inseminação (Fase 4A) da fazenda #1.
        tipo = TipoServicoReprodutivo(nome="Cobertura", fazenda_id=1)
        s.add(tipo)
        s.commit()
        s.refresh(tipo)
        metodo = MetodoServicoReprodutivo(nome="Monta Natural", tipo_servico_id=tipo.id, fazenda_id=1)
        s.add(metodo)

        # Serviço/IA da fazenda #1 — data_servico distinta e verificável em
        # agenda-veterinario (ultimo_servico) e reproducao/servicos.
        servico = Servico(
            numero_matriz="9001", data_servico=date(2026, 1, 10), tipo_servico="IA",
            reprodutor="Touro X", fazenda_id=1,
        )
        s.add(servico)

        # Parto da fazenda #1.
        parto = Parto(numero_matriz="9001", data_parto=date(2025, 6, 1), ordem_parto=1, fazenda_id=1)
        s.add(parto)

        # Protocolo IATF (lançamento + 1 aplicação) da fazenda #1.
        lancamento = ProtocoloIatfLancamento(nome_protocolo="IATF Lote 1", data_d0=date(2026, 1, 1), fazenda_id=1)
        s.add(lancamento)
        s.commit()
        s.refresh(lancamento)
        aplicacao = ProtocoloIatfAplicacao(
            lancamento_id=lancamento.id, numero_matriz="9001", dia=0,
            descricao="Implante D0", data_prevista=date(2026, 1, 1), fazenda_id=1,
        )
        s.add(aplicacao)
        s.commit()

        s.refresh(tipo)
        s.refresh(metodo)
        s.refresh(servico)
        s.refresh(parto)
        ids["tipo_id"] = tipo.id
        ids["metodo_id"] = metodo.id
        ids["servico_id"] = servico.id
        ids["parto_id"] = parto.id
        ids["lancamento_id"] = lancamento.id

        # Contrato ativo + todos os módulos comerciais para as duas fazendas —
        # ortogonal ao isolamento testado aqui (ver mesmo bloco em
        # test_multi_fazenda_isolamento.py); sem isso os routers de reprodução
        # e cadastro barram por módulo não contratado antes mesmo de chegar
        # no filtro de fazenda_id.
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
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine, ids

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestIsolamentoReprodutivo:
    def test_servicos_isolados(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/reproducao/servicos")
        assert r.status_code == 200
        numeros = {reg["numero"] for reg in r.json()["servicos"]}
        assert "9001" not in numeros

        _como_fazenda(1)
        r = c.get("/reproducao/servicos")
        numeros = {reg["numero"] for reg in r.json()["servicos"]}
        assert "9001" in numeros

    def test_atualizar_servico_ownership(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.put(f"/reproducao/servicos/{ids['servico_id']}", json={"tipo_servico": "Monta natural"})
        assert r.status_code == 404

        _como_fazenda(1)
        r = c.put(f"/reproducao/servicos/{ids['servico_id']}", json={"tipo_servico": "Monta natural"})
        assert r.status_code == 200
        assert r.json()["tipo_servico"] == "Monta natural"

    def test_partos_isolados(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/reproducao/partos")
        assert r.status_code == 200
        assert r.json()["partos"] == []

        _como_fazenda(1)
        r = c.get("/reproducao/partos")
        numeros = {reg["numero"] for reg in r.json()["partos"]}
        assert "9001" in numeros

    def test_atualizar_parto_ownership(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.put(f"/reproducao/partos/{ids['parto_id']}", json={"tipo_parto": "Distócico"})
        assert r.status_code == 404

        _como_fazenda(1)
        r = c.put(f"/reproducao/partos/{ids['parto_id']}", json={"tipo_parto": "Distócico"})
        assert r.status_code == 200
        assert r.json()["tipo_parto"] == "Distócico"

    def test_protocolo_iatf_lancamentos_isolado(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/reproducao/protocolo-iatf/lancamentos")
        assert r.status_code == 200
        assert r.json() == []

        _como_fazenda(1)
        r = c.get("/reproducao/protocolo-iatf/lancamentos")
        nomes = {l["nome_protocolo"] for l in r.json()}
        assert "IATF Lote 1" in nomes

    def test_protocolo_iatf_ativos_isolado(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/reproducao/protocolo-iatf/ativos")
        assert r.status_code == 200
        assert r.json() == []

        _como_fazenda(1)
        r = c.get("/reproducao/protocolo-iatf/ativos")
        nomes = {p["nome_protocolo"] for p in r.json()}
        assert "IATF Lote 1" in nomes

    def test_agenda_veterinario_isolada(self, client):
        """GET /reproducao/agenda-veterinario cruza Animal + Servico filtrados
        por fazenda — ultimo_servico não pode vazar a data do serviço lançado
        pela fazenda #1 para quem consulta como fazenda #2."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/reproducao/agenda-veterinario")
        assert r.status_code == 200
        assert r.json()["ultimo_servico"] is None

        _como_fazenda(1)
        r = c.get("/reproducao/agenda-veterinario")
        assert r.json()["ultimo_servico"] == "2026-01-10"

    def test_tipos_servico_post_e_put_ownership(self, client):
        """POST/PUT /cadastro/tipos-servico — só GET tinha cobertura de
        isolamento até então; POST precisa carimbar fazenda_id no criado e PUT
        precisa recusar editar o tipo de outra fazenda."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.post("/cadastro/tipos-servico", json={"nome": "Cobertura", "ativo": True})
        assert r.status_code == 200, r.text
        novo_id = r.json()["id"]
        assert r.json()["fazenda_id"] == 2

        # Fazenda #1 não vê o tipo criado pela #2 (mesmo nome, fazendas
        # diferentes — unique(nome, fazenda_id) permite ambas existirem).
        _como_fazenda(1)
        nomes_1 = {t["nome"] for t in c.get("/cadastro/tipos-servico").json()}
        assert "Cobertura" in nomes_1  # o próprio da fazenda #1, seedado no fixture

        # Fazenda #2 não pode editar o tipo "Cobertura" da fazenda #1.
        _como_fazenda(2)
        r = c.put(f"/cadastro/tipos-servico/{ids['tipo_id']}", json={"nome": "Cobertura Renomeada", "ativo": True})
        assert r.status_code == 404

        # Fazenda #2 pode editar o próprio tipo criado.
        r = c.put(f"/cadastro/tipos-servico/{novo_id}", json={"nome": "Cobertura F2", "ativo": True})
        assert r.status_code == 200
        assert r.json()["nome"] == "Cobertura F2"

        # Fazenda #1 continua enxergando o seu tipo intacto.
        _como_fazenda(1)
        r = c.get(f"/cadastro/tipos-servico")
        assert {"Cobertura"} <= {t["nome"] for t in r.json()}

    def test_metodos_servico_post_e_put_ownership(self, client):
        """POST/PUT /cadastro/metodos-servico — criar um método referenciando
        o tipo_servico_id de OUTRA fazenda deve falhar (400), e editar um
        método de outra fazenda deve falhar (404)."""
        c, engine, ids = client

        # Fazenda #2 tenta criar um método usando o tipo_servico_id da #1 —
        # tipo.fazenda_id (1) != fazenda_id do caller (2) => 400.
        _como_fazenda(2)
        r = c.post(
            "/cadastro/metodos-servico",
            json={"nome": "Monta Natural F2", "tipo_servico_id": ids["tipo_id"], "ativo": True},
        )
        assert r.status_code == 400

        # Cria o próprio tipo de serviço da fazenda #2 e um método válido nele.
        r = c.post("/cadastro/tipos-servico", json={"nome": "Cobertura F2", "ativo": True})
        assert r.status_code == 200, r.text
        tipo_f2_id = r.json()["id"]
        r = c.post(
            "/cadastro/metodos-servico",
            json={"nome": "Monta Natural F2", "tipo_servico_id": tipo_f2_id, "ativo": True},
        )
        assert r.status_code == 200, r.text
        metodo_f2_id = r.json()["id"]
        assert r.json()["fazenda_id"] == 2

        # Fazenda #2 não vê o método "Monta Natural" da fazenda #1.
        nomes_f2 = {m["nome"] for m in c.get("/cadastro/metodos-servico").json()}
        assert "Monta Natural" not in nomes_f2
        assert "Monta Natural F2" in nomes_f2

        # Fazenda #2 não pode editar o método da fazenda #1.
        r = c.put(
            f"/cadastro/metodos-servico/{ids['metodo_id']}",
            json={"nome": "Renomeado", "tipo_servico_id": tipo_f2_id, "ativo": True},
        )
        assert r.status_code == 404

        # Fazenda #2 pode editar o próprio método.
        r = c.put(
            f"/cadastro/metodos-servico/{metodo_f2_id}",
            json={"nome": "Monta Natural F2 Renomeado", "tipo_servico_id": tipo_f2_id, "ativo": True},
        )
        assert r.status_code == 200
        assert r.json()["nome"] == "Monta Natural F2 Renomeado"

        # Fazenda #1 continua vendo o método original intacto.
        _como_fazenda(1)
        nomes_f1 = {m["nome"] for m in c.get("/cadastro/metodos-servico").json()}
        assert "Monta Natural" in nomes_f1

    def test_criar_servico_carimba_fazenda_e_nao_vaza(self, client):
        """POST /reproducao/servico (registrar_servico) — o serviço criado
        pela fazenda #2 (com sua própria matriz) precisa ser carimbado com
        fazenda_id=2 e não pode aparecer na listagem da fazenda #1."""
        c, engine, ids = client
        with Session(engine) as s:
            s.add(Animal(numero="7002", sexo="F", ativo=True, fazenda_id=2))
            s.commit()

        _como_fazenda(2)
        r = c.post(
            "/reproducao/servico",
            json={
                "numero_matriz": "7002", "data_servico": "2026-02-01", "tipo_servico": "Monta natural",
                "reprodutor": None,
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["fazenda_id"] == 2

        r = c.get("/reproducao/servicos")
        numeros = {reg["numero"] for reg in r.json()["servicos"]}
        assert "7002" in numeros
        assert "9001" not in numeros  # da fazenda #1, não deve vazar

        _como_fazenda(1)
        r = c.get("/reproducao/servicos")
        numeros = {reg["numero"] for reg in r.json()["servicos"]}
        assert "9001" in numeros
        assert "7002" not in numeros  # da fazenda #2, não deve vazar
