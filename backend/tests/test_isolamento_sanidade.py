"""
Isolamento por fazenda — Sanidade (Fase 4D) — garante que aplicações,
calendário sanitário, exames (cadastro e resultado), protocolos sanitários e
agendamento de pesagem de uma fazenda nunca aparecem nem são editáveis por
outra.

`test_multi_fazenda_isolamento.py` já cobre a listagem de
GET /sanidade/calendario e GET /farmacia/principios — este arquivo fecha o
resto do domínio Sanidade: aplicações (GET/PUT/DELETE), mutação do
calendário (POST/PUT/DELETE), cadastro de exames, protocolos sanitários,
agendamento de pesagem e os relatórios de resultado de exame/lançamento de
protocolo.

Self-contained: fixture `client` própria (mesmo padrão do arquivo de
referência), não compartilha nada com os demais arquivos de teste.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

# Precisa ser setado ANTES de qualquer import de fazenda.* — ver mesma nota em
# test_multi_fazenda_isolamento.py.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    AgendamentoPesagem, CalendarioSanitario, ContratoFazenda, ContratoFazendaModulo, Doenca, Estoque, EventoSanitario,
    ExameDefinicao, ExameResultado, Fazenda, MovimentoEstoque, ProtocoloSanitario, ProtocoloSanitarioEtapa, Sanidade,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    # Banco isolado por teste — mesmo motivo do arquivo de referência: todos os
    # módulos compartilham o MESMO objeto `engine` depois de importados.
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))

        # Contrato ativo + todos os módulos comerciais para as duas fazendas —
        # o router de sanidade exige módulo "sanitario" contratado
        # (main.py: exigir_modulo_contratado("sanitario")) e o de cadastro
        # exige contrato ativo (exigir_contrato_ativo); ortogonal ao que este
        # arquivo testa (isolamento de dados), então libera os dois lados.
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        # --- Dados reais da fazenda #1 — nunca devem aparecer para a #2. ---
        ev = EventoSanitario(nome="Vermífugo", fazenda_id=1)
        s.add(ev)
        s.commit()
        s.refresh(ev)

        cal = CalendarioSanitario(
            evento_sanitario_id=ev.id, fazenda_id=1, frequencia_valor=4, frequencia_unidade="meses",
            data_evento=date(2026, 1, 1), categoria_alvo="Bezerras",
        )
        s.add(cal)

        sanidade = Sanidade(
            numero_matriz="9001", produto="Ivomec", data_aplicacao=date(2026, 1, 10),
            natureza="curativo", fazenda_id=1,
        )
        s.add(sanidade)

        doenca = Doenca(nome="Brucelose", fazenda_id=1)
        s.add(doenca)

        exame_def = ExameDefinicao(nome="Tuberculose", fazenda_id=1)
        s.add(exame_def)

        protocolo = ProtocoloSanitario(nome="Mastite - Protocolo Fazenda 1", fazenda_id=1)
        s.add(protocolo)
        s.commit()
        s.refresh(protocolo)

        etapa = ProtocoloSanitarioEtapa(
            protocolo_id=protocolo.id, dia=1, produto="Borgal", dosagem=40, unidade="ml",
            via="Intramuscular", fazenda_id=1,
        )
        s.add(etapa)

        agendamento = AgendamentoPesagem(
            nome="Bezerras até desmama", data_referencia=date(2026, 1, 1), fazenda_id=1,
        )
        s.add(agendamento)

        exame_resultado = ExameResultado(
            numero_matriz="9001", evento_sanitario_id=ev.id, data_exame=date(2026, 1, 15),
            resultado="negativo", fazenda_id=1,
        )
        s.add(exame_resultado)

        # Item de estoque exclusivo da fazenda #2 — usado por
        # TestEstoqueBaixaIsolada para garantir que a fazenda #1 nunca consegue
        # baixar (nem pelo nome, nem pelo estoque_id) o item alheio.
        estoque_f2 = Estoque(
            nome="Item Exclusivo F2", fazenda_id=2, quantidade=100.0, unidade="ml", estoque_inicializado=True,
        )
        s.add(estoque_f2)

        # Evento sanitário PRÓPRIO da fazenda #2 — o cadastro é por fazenda
        # (a listagem em cadastro/sanitario.py filtra por `fazenda_id ==`), e
        # desde a correção do furo em `_validar_calendario` uma regra de
        # calendário só pode apontar para um evento da própria fazenda.
        # Antes, o teste de "criar regra fica na fazenda do criador" usava o
        # evento da fazenda #1 por conveniência — o que é exatamente o
        # ataque (a resposta do POST devolve nome/categoria/serviço
        # financeiro do evento apontado, ver `_serializar`).
        ev_f2 = EventoSanitario(nome="Vermífugo", fazenda_id=2)
        s.add(ev_f2)

        s.commit()
        s.refresh(cal)
        s.refresh(sanidade)
        s.refresh(doenca)
        s.refresh(exame_def)
        s.refresh(etapa)
        s.refresh(agendamento)
        s.refresh(exame_resultado)
        s.refresh(estoque_f2)
        s.refresh(ev_f2)

        ids = {
            "evento_sanitario_id": ev.id,
            "evento_sanitario_f2_id": ev_f2.id,
            "calendario_id": cal.id,
            "sanidade_id": sanidade.id,
            "doenca_id": doenca.id,
            "exame_definicao_id": exame_def.id,
            "protocolo_id": protocolo.id,
            "etapa_id": etapa.id,
            "agendamento_id": agendamento.id,
            "exame_resultado_id": exame_resultado.id,
            "estoque_f2_id": estoque_f2.id,
        }

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


# ---------------------------------------------------------------------------
# Aplicações (Sanidade) — GET /sanidade/aplicacoes, PUT/DELETE por id.
# ---------------------------------------------------------------------------
class TestAplicacoesIsoladas:
    def test_listar_aplicacoes_nao_vaza_entre_fazendas(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/sanidade/aplicacoes")
        assert r.status_code == 200
        produtos = {item["produto"] for item in r.json()["aplicacoes"]}
        assert "Ivomec" not in produtos

        _como_fazenda(1)
        r = c.get("/sanidade/aplicacoes")
        produtos = {item["produto"] for item in r.json()["aplicacoes"]}
        assert "Ivomec" in produtos

    def test_editar_aplicacao_de_outra_fazenda_da_404(self, client):
        """Bug real corrigido: PUT /sanidade/aplicacoes/{id} não checava
        fazenda_id nenhum — qualquer fazenda logada conseguia editar a
        aplicação de outra só sabendo o id (fazenda/api/routers/sanidade.py,
        editar_aplicacao)."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.put(f"/sanidade/aplicacoes/{ids['sanidade_id']}", json={"produto": "Sequestrado"})
        assert r.status_code == 404

        _como_fazenda(1)
        r = c.put(f"/sanidade/aplicacoes/{ids['sanidade_id']}", json={"produto": "Ivomec Gold"})
        assert r.status_code == 200
        assert r.json()["produto"] == "Ivomec Gold"

    def test_excluir_aplicacao_de_outra_fazenda_da_404(self, client):
        """Bug real corrigido: DELETE /sanidade/aplicacoes/{id} idem — sem
        checagem de posse nenhuma."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.delete(f"/sanidade/aplicacoes/{ids['sanidade_id']}")
        assert r.status_code == 404

        with Session(engine) as s:
            assert s.get(Sanidade, ids["sanidade_id"]) is not None

        _como_fazenda(1)
        r = c.delete(f"/sanidade/aplicacoes/{ids['sanidade_id']}")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Calendário sanitário — POST/PUT/DELETE (GET já coberto em
# test_multi_fazenda_isolamento.py, mas mutação nunca foi testada).
# ---------------------------------------------------------------------------
class TestCalendarioMutacaoIsolada:
    def test_criar_regra_calendario_fica_na_fazenda_do_criador(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        body = {
            # Evento da PRÓPRIA fazenda 2 — ver o comentário no fixture.
            "evento_sanitario_id": ids["evento_sanitario_f2_id"],
            "frequencia_valor": 6,
            "frequencia_unidade": "meses",
            "data_evento": "2026-02-01",
        }
        r = c.post("/sanidade/calendario", json=body)
        assert r.status_code == 200, r.text
        nova_id = r.json()["id"]
        assert r.json()["fazenda_id"] == 2

        with Session(engine) as s:
            regra = s.get(CalendarioSanitario, nova_id)
            assert regra.fazenda_id == 2

        # Fazenda 1 não vê a regra da fazenda 2, e vice-versa.
        r = c.get("/sanidade/calendario")
        assert nova_id in {item["id"] for item in r.json()}
        _como_fazenda(1)
        r = c.get("/sanidade/calendario")
        assert nova_id not in {item["id"] for item in r.json()}
        assert ids["calendario_id"] in {item["id"] for item in r.json()}

    def test_atualizar_regra_calendario_de_outra_fazenda_da_404(self, client):
        """Bug real corrigido: PUT /sanidade/calendario/{id} não checava
        fazenda_id — fazenda_id_seguro(fazenda_id) do ownership check estava
        ausente (fazenda/api/routers/sanidade.py, atualizar_calendario)."""
        c, engine, ids = client
        body = {
            "evento_sanitario_id": ids["evento_sanitario_id"],
            "frequencia_valor": 12,
            "frequencia_unidade": "meses",
            "data_evento": "2026-03-01",
        }
        _como_fazenda(2)
        r = c.put(f"/sanidade/calendario/{ids['calendario_id']}", json=body)
        assert r.status_code == 404

        _como_fazenda(1)
        r = c.put(f"/sanidade/calendario/{ids['calendario_id']}", json=body)
        assert r.status_code == 200

    def test_excluir_regra_calendario_de_outra_fazenda_da_404(self, client):
        """Bug real corrigido: DELETE /sanidade/calendario/{id} idem."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.delete(f"/sanidade/calendario/{ids['calendario_id']}")
        assert r.status_code == 404

        with Session(engine) as s:
            assert s.get(CalendarioSanitario, ids["calendario_id"]) is not None

        _como_fazenda(1)
        r = c.delete(f"/sanidade/calendario/{ids['calendario_id']}")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Cadastro > Sanitário > Exames — GET/POST/PUT/DELETE /cadastro/exames.
# ---------------------------------------------------------------------------
class TestExamesCadastroIsolados:
    def test_listar_exames_isolado(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/cadastro/exames")
        assert r.status_code == 200
        assert "Tuberculose" not in {e["nome"] for e in r.json()}
        _como_fazenda(1)
        r = c.get("/cadastro/exames")
        assert "Tuberculose" in {e["nome"] for e in r.json()}

    def test_criar_exame_fica_na_fazenda_do_criador(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.post("/cadastro/exames", json={"nome": "Brucelose"})
        assert r.status_code == 200, r.text
        nova_id = r.json()["id"]
        with Session(engine) as s:
            assert s.get(ExameDefinicao, nova_id).fazenda_id == 2
        # Mesmo nome já usado pela fazenda #1 — não conflita (unique por fazenda).
        assert r.json()["nome"] == "Brucelose"

    def test_editar_exame_de_outra_fazenda_da_404(self, client):
        """Bug real corrigido: PUT /cadastro/exames/{id} não checava
        fazenda_id (fazenda/api/routers/cadastro/sanitario.py, atualizar_exame)."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.put(f"/cadastro/exames/{ids['exame_definicao_id']}", json={"nome": "Sequestrado"})
        assert r.status_code == 404

        _como_fazenda(1)
        r = c.put(f"/cadastro/exames/{ids['exame_definicao_id']}", json={"nome": "Tuberculose Bovina"})
        assert r.status_code == 200
        assert r.json()["nome"] == "Tuberculose Bovina"

    def test_excluir_exame_de_outra_fazenda_da_404(self, client):
        """Bug real corrigido: DELETE /cadastro/exames/{id} idem."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.delete(f"/cadastro/exames/{ids['exame_definicao_id']}")
        assert r.status_code == 404

        with Session(engine) as s:
            assert s.get(ExameDefinicao, ids["exame_definicao_id"]) is not None

        _como_fazenda(1)
        r = c.delete(f"/cadastro/exames/{ids['exame_definicao_id']}")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Cadastro > Protocolos Sanitários — GET/POST/PUT /cadastro/protocolos-sanitarios.
# ---------------------------------------------------------------------------
class TestProtocolosSanitariosIsolados:
    def test_listar_protocolos_isolado(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/cadastro/protocolos-sanitarios")
        assert r.status_code == 200
        assert "Mastite - Protocolo Fazenda 1" not in {p["nome"] for p in r.json()}
        _como_fazenda(1)
        r = c.get("/cadastro/protocolos-sanitarios")
        assert "Mastite - Protocolo Fazenda 1" in {p["nome"] for p in r.json()}

    def test_criar_protocolo_fica_na_fazenda_do_criador(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        body = {
            "nome": "Mastite - Protocolo Fazenda 1",  # mesmo nome da fazenda #1 — permitido (unique por fazenda)
            "etapas": [{"dia": 1, "produto": "Agemoxi", "dosagem": 50, "unidade": "ml", "via": "Intramuscular"}],
        }
        r = c.post("/cadastro/protocolos-sanitarios", json=body)
        assert r.status_code == 200, r.text
        nova_id = r.json()["id"]
        with Session(engine) as s:
            assert s.get(ProtocoloSanitario, nova_id).fazenda_id == 2

    def test_atualizar_protocolo_de_outra_fazenda_da_404(self, client):
        """Bug real corrigido: PUT /cadastro/protocolos-sanitarios/{id} não
        checava fazenda_id (fazenda/api/routers/cadastro/protocolos_sanitarios.py,
        atualizar_protocolo_sanitario)."""
        c, engine, ids = client
        body = {
            "nome": "Sequestrado",
            "etapas": [{"dia": 1, "produto": "X", "dosagem": 1, "unidade": "ml"}],
        }
        _como_fazenda(2)
        r = c.put(f"/cadastro/protocolos-sanitarios/{ids['protocolo_id']}", json=body)
        assert r.status_code == 404

        _como_fazenda(1)
        body["nome"] = "Mastite - Protocolo Fazenda 1 (revisado)"
        r = c.put(f"/cadastro/protocolos-sanitarios/{ids['protocolo_id']}", json=body)
        assert r.status_code == 200
        assert r.json()["nome"] == "Mastite - Protocolo Fazenda 1 (revisado)"


# ---------------------------------------------------------------------------
# Cadastro > Sanitário > Agendamento de pesagem —
# GET/POST/PUT/DELETE /cadastro/agendamentos-pesagem.
# ---------------------------------------------------------------------------
class TestAgendamentosPesagemIsolados:
    """Bug real corrigido: AgendamentoPesagem nunca tinha ganhado fazenda_id
    no retrofit multi-tenant da Sanidade (esquecido na migração
    c9d1e2f3a4b5) — o cadastro vazava 100% entre fazendas (listagem sem
    filtro, criação sem carimbo, update/delete sem checagem de posse). Ver
    fazenda/models/producao.py::AgendamentoPesagem, migração
    f7a8b9c0d1e2_agendamento_pesagem_fazenda_id.py e
    fazenda/api/routers/cadastro/sanitario.py."""

    def test_listar_isolado(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/cadastro/agendamentos-pesagem")
        assert r.status_code == 200
        assert "Bezerras até desmama" not in {a["nome"] for a in r.json()}
        _como_fazenda(1)
        r = c.get("/cadastro/agendamentos-pesagem")
        assert "Bezerras até desmama" in {a["nome"] for a in r.json()}

    def test_criar_fica_na_fazenda_do_criador(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        body = {"nome": "Novilhas", "data_referencia": "2026-02-01"}
        r = c.post("/cadastro/agendamentos-pesagem", json=body)
        assert r.status_code == 201, r.text
        nova_id = r.json()["id"]
        with Session(engine) as s:
            assert s.get(AgendamentoPesagem, nova_id).fazenda_id == 2

    def test_atualizar_de_outra_fazenda_da_404(self, client):
        c, engine, ids = client
        body = {"nome": "Sequestrado", "data_referencia": "2026-01-01"}
        _como_fazenda(2)
        r = c.put(f"/cadastro/agendamentos-pesagem/{ids['agendamento_id']}", json=body)
        assert r.status_code == 404

        _como_fazenda(1)
        body["nome"] = "Bezerras até desmama (revisado)"
        r = c.put(f"/cadastro/agendamentos-pesagem/{ids['agendamento_id']}", json=body)
        assert r.status_code == 200
        assert r.json()["nome"] == "Bezerras até desmama (revisado)"

    def test_excluir_de_outra_fazenda_da_404(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.delete(f"/cadastro/agendamentos-pesagem/{ids['agendamento_id']}")
        assert r.status_code == 404

        with Session(engine) as s:
            assert s.get(AgendamentoPesagem, ids["agendamento_id"]) is not None

        _como_fazenda(1)
        r = c.delete(f"/cadastro/agendamentos-pesagem/{ids['agendamento_id']}")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Relatório de resultados de exame — GET /sanidade/exames/resultados.
# ---------------------------------------------------------------------------
class TestResultadosExameIsolado:
    def test_listar_resultados_exame_isolado(self, client):
        """Bug real corrigido: GET /sanidade/exames/resultados não recebia
        fazenda_id nenhum (nem via Depends) e listava TODOS os resultados de
        TODAS as fazendas (fazenda/api/routers/sanidade.py, listar_resultados_exame)."""
        c, engine, ids = client
        _como_fazenda(2)
        r = c.get("/sanidade/exames/resultados")
        assert r.status_code == 200
        assert r.json() == []

        _como_fazenda(1)
        r = c.get("/sanidade/exames/resultados")
        assert len(r.json()) == 1
        assert r.json()[0]["numero_matriz"] == "9001"


# ---------------------------------------------------------------------------
# Protocolos sanitários — lançamentos (GET/POST /sanidade/protocolos/lancamentos).
# ---------------------------------------------------------------------------
class TestLancamentosProtocoloIsolados:
    def test_lancar_protocolo_fica_na_fazenda_do_lancador_e_nao_vaza(self, client):
        c, engine, ids = client
        _como_fazenda(1)
        body = {
            "protocolo_id": ids["protocolo_id"],
            "numeros_matriz": ["9001"],
            "data_inicio": "2026-01-20",
        }
        r = c.post("/sanidade/protocolos/lancamentos", json=body)
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamentos"][0]["id"]

        r = c.get("/sanidade/protocolos/lancamentos")
        assert lancamento_id in {l["id"] for l in r.json()}

        _como_fazenda(2)
        r = c.get("/sanidade/protocolos/lancamentos")
        assert r.status_code == 200
        assert lancamento_id not in {l["id"] for l in r.json()}


# ---------------------------------------------------------------------------
# Baixa de estoque (fazenda.rules.estoque_baixa) — item de outra fazenda nunca
# é baixado, nem pelo nome nem pelo estoque_id do frasco.
# ---------------------------------------------------------------------------
class TestEstoqueBaixaIsolada:
    def test_baixa_por_nome_nao_atinge_item_de_outra_fazenda(self, client):
        c, engine, ids = client
        _como_fazenda(1)
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-01-10", "animais": ["9001"],
            "itens": [{"produto": "Item Exclusivo F2", "quantidade": 10.0, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        # Não achou o item (é de outra fazenda) — registra a aplicação mas avisa,
        # não baixa nada.
        assert any("não está no estoque" in a for a in r.json()["avisos"])
        with Session(engine) as s:
            assert s.get(Estoque, ids["estoque_f2_id"]).quantidade == 100.0

    def test_baixa_por_estoque_id_de_outra_fazenda_e_ignorada(self, client):
        """Um `estoque_id` de outro tenant não pode ser usado para baixar
        estoque alheio — resolver_item ignora o id e cai na busca por nome
        (que também falha, pois o nome só existe na fazenda #2)."""
        c, engine, ids = client
        _como_fazenda(1)
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-01-10", "animais": ["9001"],
            "itens": [{
                "produto": "Item Exclusivo F2", "quantidade": 10.0, "unidade": "ml",
                "estoque_id": ids["estoque_f2_id"],
            }],
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(Estoque, ids["estoque_f2_id"]).quantidade == 100.0
            # Nenhum MovimentoEstoque foi gravado contra o item da fazenda #2.
            movs = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == ids["estoque_f2_id"])).all()
            assert movs == []

    def test_mesma_fazenda_consegue_baixar_pelo_estoque_id(self, client):
        c, engine, ids = client
        _como_fazenda(2)
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-01-10", "animais": ["9002"],
            "itens": [{
                "produto": "Item Exclusivo F2", "quantidade": 10.0, "unidade": "ml",
                "estoque_id": ids["estoque_f2_id"],
            }],
        })
        assert r.status_code == 200, r.text
        assert r.json()["avisos"] == []
        with Session(engine) as s:
            item = s.get(Estoque, ids["estoque_f2_id"])
            assert item.quantidade == 90.0
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == ids["estoque_f2_id"])).first()
            assert mov is not None
            assert mov.fazenda_id == 2
            assert mov.origem_tipo == "sanidade"
