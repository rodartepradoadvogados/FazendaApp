"""
Isolamento por fazenda — achados F-C-01, F-C-04, F-C-06, F-C-08 e F-C-10 do
dossiê `onda-sanidade-producao-exclusoes` (auditoria de 3 rodadas, 05/09/2026).

Cada classe abaixo reproduz UM achado: duas fazendas com dados próprios,
e a operação de uma não pode alcançar a da outra. F-C-03 (exclusão em
cascata de animal vazando colostragem/lactação/foto de campo) já estava
corrigido antes desta onda — coberto por `test_isolamento_exclusoes.py`,
não repetido aqui.

Mesmo fixture/convenção de `test_isolamento_sanidade.py`.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    Animal, CalendarioSanitario, ContratoFazenda, ContratoFazendaModulo, EventoSanitario, Fazenda,
    Parto, ProtocoloInducaoLactacao, ProtocoloInducaoLactacaoEtapa, ProtocoloSanitario, ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento, ProtocoloSanitarioLote, Servico,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

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
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


# ---------------------------------------------------------------------------
# F-C-01 — GET /sanidade/calendario/relatorio-eventos-vida
# ---------------------------------------------------------------------------
class TestRelatorioEventosVidaIsolado:
    def test_relatorio_por_gatilho_nao_lista_animal_de_outra_fazenda(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="9001", fazenda_id=1, nome="Vaca sigilosa F1", data_nasc=date(2026, 1, 1)))
            s.add(Animal(numero="9002", fazenda_id=2, nome="Vaca F2", data_nasc=date(2026, 1, 1)))
            s.commit()

        _como_fazenda(1)
        r = c.get("/sanidade/calendario/relatorio-eventos-vida", params={"gatilho": "nascimento"})
        assert r.status_code == 200, r.text
        numeros = {linha["numero_matriz"] for linha in r.json()["animais"]}
        assert "9001" in numeros
        assert "9002" not in numeros, "animal de OUTRA fazenda vazou no relatório de eventos de vida"

    def test_relatorio_por_evento_sanitario_de_outra_fazenda_da_400(self, client):
        c, engine = client
        with Session(engine) as s:
            ev = EventoSanitario(
                nome="Brucelose B19 sigilosa", fazenda_id=1, tipo_agendamento="evento",
                gatilho="novilha_apta", gatilho_idade_meses=13,
            )
            s.add(ev)
            s.commit()
            s.refresh(ev)
            ev_id = ev.id

        _como_fazenda(2)
        r = c.get("/sanidade/calendario/relatorio-eventos-vida", params={"evento_sanitario_id": ev_id})
        assert r.status_code == 400, "evento_sanitario_id de outra fazenda não pode ser aceito"
        assert "sigilosa" not in r.text.lower()


# ---------------------------------------------------------------------------
# F-C-04 — GET /producao/secagem-info
# ---------------------------------------------------------------------------
class TestSecagemInfoIsolado:
    def test_secagem_info_nao_devolve_animal_de_outra_fazenda(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="100", fazenda_id=1, nome="Vaca F1", grupo_primario="Lote sigiloso F1"))
            s.add(Servico(numero_matriz="100", fazenda_id=1, data_servico=date(2026, 1, 1), diagnostico="POSITIVO"))
            s.commit()

        # Fazenda 2 não tem NENHUM animal "100" — antes do fix, a rota
        # devolvia o animal da fazenda 1 mesmo assim (zero filtro de tenant).
        _como_fazenda(2)
        r = c.get("/producao/secagem-info", params={"numero_matriz": "100"})
        assert r.status_code == 404, r.text

        _como_fazenda(1)
        r = c.get("/producao/secagem-info", params={"numero_matriz": "100"})
        assert r.status_code == 200, r.text
        assert r.json()["lote_atual"] == "Lote sigiloso F1"

    def test_secagem_info_colisao_de_numero_nao_mistura_servicos_entre_fazendas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="200", fazenda_id=1, nome="Vaca F1", grupo_primario="Lote F1"))
            s.add(Animal(numero="200", fazenda_id=2, nome="Vaca F2", grupo_primario="Lote F2"))
            # Parto exclusivo da fazenda 1 — não pode influenciar o DEL da fazenda 2.
            s.add(Parto(numero_matriz="200", fazenda_id=1, data_parto=date(2026, 1, 1)))
            s.commit()

        _como_fazenda(2)
        r = c.get("/producao/secagem-info", params={"numero_matriz": "200"})
        assert r.status_code == 200, r.text
        assert r.json()["lote_atual"] == "Lote F2"
        # DEL não pode vir do parto da fazenda 1 (que daria um DEL calculado);
        # sem parto próprio, del_atual cai para animal.del_dias (None aqui).
        assert r.json()["del_atual"] is None


# ---------------------------------------------------------------------------
# F-C-06 — GET /producao/protocolos-inducao-lactacao e POST /producao/inducao-lactacao
# ---------------------------------------------------------------------------
class TestProtocoloInducaoLactacaoIsolado:
    def _criar_protocolo(self, engine, fazenda_id: int, nome: str) -> int:
        with Session(engine) as s:
            p = ProtocoloInducaoLactacao(nome=nome, fazenda_id=fazenda_id, dia_inicial=0)
            s.add(p)
            s.commit()
            s.refresh(p)
            s.add(ProtocoloInducaoLactacaoEtapa(
                protocolo_id=p.id, dia=0, tipo="medicamento", produto="Estradiol", fazenda_id=fazenda_id,
            ))
            s.commit()
            return p.id

    def test_listagem_nao_traz_protocolo_de_outra_fazenda(self, client):
        c, engine = client
        self._criar_protocolo(engine, 1, "Protocolo sigiloso F1")
        self._criar_protocolo(engine, 2, "Protocolo F2")

        _como_fazenda(2)
        r = c.get("/producao/protocolos-inducao-lactacao")
        assert r.status_code == 200, r.text
        nomes = {p["nome"] for p in r.json()}
        assert "Protocolo F2" in nomes
        assert "Protocolo sigiloso F1" not in nomes

    def test_lancar_com_protocolo_de_outra_fazenda_da_404(self, client):
        c, engine = client
        protocolo_id_f1 = self._criar_protocolo(engine, 1, "Protocolo sigiloso F1")

        _como_fazenda(2)
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": protocolo_id_f1, "animais": ["1"], "data_d0": "2026-09-05",
        })
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# F-C-08 — POST /sanidade/calendario/cadastrar-preventivo
# ---------------------------------------------------------------------------
class TestCadastrarPreventivoIsolado:
    def test_evento_sanitario_de_outra_fazenda_nao_pode_ser_usado(self, client):
        c, engine = client
        with Session(engine) as s:
            ev = EventoSanitario(nome="Vacina sigilosa F1", fazenda_id=1, produto_padrao="Segredo Comercial")
            s.add(ev)
            s.commit()
            s.refresh(ev)
            ev_id = ev.id

        _como_fazenda(2)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": "2026-09-05", "frequencia_valor": 0,
        })
        assert r.status_code == 400, r.text
        assert "Segredo Comercial" not in r.text

    def test_calendario_id_de_outra_fazenda_nao_pode_ser_reaproveitado(self, client):
        """A checagem antiga só comparava `regra.evento_sanitario_id ==
        ev.id` — nunca o tenant da própria regra. Reproduz isolando essa
        checagem: uma CalendarioSanitario da FAZENDA 1 que referencia o
        evento_sanitario_id da FAZENDA 2 (a mesma anomalia que o comentário
        do achado descreve como possível antes do fix em `calendario_id is
        None`) — o atacante (fazenda 2) usa o PRÓPRIO evento_sanitario_id
        (passa na 1ª checagem) e o calendario_id da fazenda 1 (deveria falhar
        na 2ª)."""
        c, engine = client
        with Session(engine) as s:
            ev2 = EventoSanitario(nome="Vacina F2", fazenda_id=2)
            s.add(ev2)
            s.commit()
            s.refresh(ev2)
            # Regra é da FAZENDA 1, mas aponta pro evento_sanitario_id que
            # pertence à fazenda 2 (atacante) — únicos ids que o antigo check
            # comparava.
            cal_f1 = CalendarioSanitario(
                evento_sanitario_id=ev2.id, fazenda_id=1, frequencia_valor=4, frequencia_unidade="meses",
                data_evento=date(2026, 1, 1), produto="Segredo Regra F1",
            )
            s.add(cal_f1)
            s.commit()
            s.refresh(cal_f1)
            ids = {"ev2_id": ev2.id, "cal_f1_id": cal_f1.id}

        _como_fazenda(2)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ids["ev2_id"], "calendario_id": ids["cal_f1_id"],
            "data_evento": "2026-09-05", "frequencia_valor": 0,
        })
        assert r.status_code == 404, r.text
        assert "Segredo Regra F1" not in r.text


# ---------------------------------------------------------------------------
# F-C-10 — POST /sanidade/protocolos/lancamentos
# ---------------------------------------------------------------------------
class TestLancarProtocoloSanitarioIsolado:
    def _criar_protocolo(self, engine, fazenda_id: int, nome: str, eh_mastite: bool = False) -> int:
        with Session(engine) as s:
            p = ProtocoloSanitario(nome=nome, fazenda_id=fazenda_id, eh_mastite=eh_mastite)
            s.add(p)
            s.commit()
            s.refresh(p)
            s.add(ProtocoloSanitarioEtapa(
                protocolo_id=p.id, dia=0, produto="Borgal", dosagem=40, unidade="ml",
                via="Intramuscular", fazenda_id=fazenda_id,
            ))
            s.commit()
            return p.id

    def test_lancar_com_protocolo_de_outra_fazenda_da_404(self, client):
        c, engine = client
        protocolo_id_f1 = self._criar_protocolo(engine, 1, "Protocolo sigiloso F1")

        _como_fazenda(2)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id_f1, "numeros_matriz": ["1"], "data_inicio": "2026-09-05",
        })
        assert r.status_code == 404, r.text

    def test_recidiva_de_mastite_nao_cruza_fazenda(self, client):
        """Achado F-C-10 (extra): a checagem de recidiva (mesmo teto, < 20
        dias) rodava sem filtro de fazenda_id — um caso de mastite de OUTRA
        fazenda no mesmo número de animal acionava (incorretamente) o aviso
        de recidiva."""
        c, engine = client
        protocolo_f1 = self._criar_protocolo(engine, 1, "Mastite F1", eh_mastite=True)
        protocolo_f2 = self._criar_protocolo(engine, 2, "Mastite F2", eh_mastite=True)

        with Session(engine) as s:
            lote = ProtocoloSanitarioLote(protocolo_id=protocolo_f1, nome_protocolo="Mastite F1 05/09", data_inicio=date(2026, 8, 20), fazenda_id=1)
            s.add(lote)
            s.commit()
            s.refresh(lote)
            # Caso de mastite recente da FAZENDA 1, mesmo número "300", mesmo teto.
            s.add(ProtocoloSanitarioLancamento(
                protocolo_id=protocolo_f1, numero_matriz="300", data_inicio=date(2026, 8, 20),
                lote_id=lote.id, tetos_afetados="AE", fazenda_id=1,
            ))
            s.commit()

        _como_fazenda(2)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_f2, "numeros_matriz": ["300"], "data_inicio": "2026-09-05",
            "classificacao_mastite": "clinica", "tetos_afetados": ["AE"],
        })
        assert r.status_code == 201, r.text
        lancamentos = r.json()["lancamentos"]
        assert len(lancamentos) == 1
        assert not lancamentos[0]["recidiva"], "recidiva não pode ser calculada a partir de caso de OUTRA fazenda"
        assert not r.json()["avisos"], "aviso de recidiva não pode citar caso de OUTRA fazenda"
