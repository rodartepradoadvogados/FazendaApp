"""
Protocolos personalizados — motor de protocolos configurável pelo usuário
(catálogo + etapas + lançamento + aplicações que viram eventos na Agenda).
Ver fazenda/models/protocolo_customizado.py,
fazenda/api/routers/cadastro/protocolos_customizados.py,
fazenda/api/routers/protocolos_customizados.py e
fazenda/rules/protocolo_customizado.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Sanidade
from fazenda.models.planos import MODULOS_COMERCIAIS


class _FakeUser:
    id = 1
    papel = "admin"
    ativo = True
    username = "teste"
    permissoes = None


class _FakeFuncionario:
    id = 2
    papel = "funcionario"
    ativo = True
    username = "funcionario_teste"
    permissoes = "rebanho"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _etapa(dia, evento="Conferir escore corporal", insumo=None, **kw):
    d = {"dia": dia, "descricao_evento": evento, "insumo_padrao": insumo}
    d.update(kw)
    return d


def _criar_protocolo(c, nome="Protocolo teste", categoria="Atividades", dia_inicial=0, etapas=None):
    etapas = etapas if etapas is not None else [_etapa(0), _etapa(1), _etapa(2)]
    return c.post("/cadastro/protocolos-customizados", json={
        "nome": nome, "categoria": categoria, "dia_inicial": dia_inicial, "etapas": etapas,
    })


class TestCadastroProtocoloCustomizado:
    def test_cria_com_3_etapas(self, client):
        c, _ = client
        r = _criar_protocolo(c)
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["dia_inicial"] == 0
        assert [e["dia"] for e in corpo["etapas"]] == [0, 1, 2]
        assert corpo["duracao_dias"] == 2

    def test_nome_duplicado_409(self, client):
        c, _ = client
        _criar_protocolo(c, nome="Repetido")
        r = _criar_protocolo(c, nome="Repetido")
        assert r.status_code == 409

    def test_sem_etapas_400(self, client):
        c, _ = client
        r = _criar_protocolo(c, etapas=[])
        assert r.status_code == 400

    def test_categoria_fora_da_whitelist_400(self, client):
        c, _ = client
        r = _criar_protocolo(c, categoria="Financeiro Secreto")
        assert r.status_code == 400

    def test_categoria_alimentacao_400(self, client):
        c, _ = client
        r = _criar_protocolo(c, categoria="alimentacao")
        assert r.status_code == 400

    def test_put_substitui_etapas_por_completo(self, client):
        c, _ = client
        criado = _criar_protocolo(c, etapas=[_etapa(0), _etapa(1), _etapa(2)]).json()
        r = c.put(f"/cadastro/protocolos-customizados/{criado['id']}", json={
            "nome": criado["nome"], "categoria": "Atividades", "dia_inicial": 0,
            "etapas": [_etapa(0), _etapa(1)],
        })
        assert r.status_code == 200
        assert len(r.json()["etapas"]) == 2

    def test_put_inexistente_404(self, client):
        c, _ = client
        r = c.put("/cadastro/protocolos-customizados/9999", json={
            "nome": "X", "categoria": "Atividades", "dia_inicial": 0, "etapas": [_etapa(0)],
        })
        assert r.status_code == 404

    def test_excluir_com_lancamento_409(self, client):
        c, _ = client
        criado = _criar_protocolo(c).json()
        c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["800"], "data_inicio": "2026-03-01",
        })
        r = c.delete(f"/cadastro/protocolos-customizados/{criado['id']}")
        assert r.status_code == 409
        assert c.get("/cadastro/protocolos-customizados").json()

    def test_excluir_sem_lancamento_ok(self, client):
        c, _ = client
        criado = _criar_protocolo(c).json()
        r = c.delete(f"/cadastro/protocolos-customizados/{criado['id']}")
        assert r.status_code == 200
        assert c.get("/cadastro/protocolos-customizados").json() == []


class TestLancamento:
    def test_datas_previstas_dia_inicial_0(self, client):
        c, _ = client
        criado = _criar_protocolo(c, dia_inicial=0, etapas=[_etapa(0), _etapa(1), _etapa(2)]).json()
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["800"], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 201, r.text
        assert r.json()["eventos_criados"] == 3

    def test_offset_dia_inicial_1_mesmas_datas(self, client, monkeypatch):
        c, engine = client
        criado0 = _criar_protocolo(c, nome="D0", dia_inicial=0, etapas=[_etapa(0), _etapa(1), _etapa(2)]).json()
        c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado0["id"], "animais": ["800"], "data_inicio": "2026-03-01",
        })
        criado1 = _criar_protocolo(c, nome="D1", dia_inicial=1, etapas=[_etapa(1), _etapa(2), _etapa(3)]).json()
        c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado1["id"], "animais": ["801"], "data_inicio": "2026-03-01",
        })
        from fazenda.models import ProtocoloCustomizadoAplicacao
        with Session(engine) as s:
            datas0 = sorted(a.data_prevista.isoformat() for a in s.exec(
                select(ProtocoloCustomizadoAplicacao).where(ProtocoloCustomizadoAplicacao.numero_matriz == "800")
            ).all())
            datas1 = sorted(a.data_prevista.isoformat() for a in s.exec(
                select(ProtocoloCustomizadoAplicacao).where(ProtocoloCustomizadoAplicacao.numero_matriz == "801")
            ).all())
        assert datas0 == datas1 == ["2026-03-01", "2026-03-02", "2026-03-03"]

    def test_multiplos_animais_um_unico_lancamento(self, client):
        c, engine = client
        criado = _criar_protocolo(c, etapas=[_etapa(0), _etapa(1), _etapa(2)]).json()
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["800", "801", "802"], "data_inicio": "2026-03-01",
        })
        assert r.json()["eventos_criados"] == 9
        assert r.json()["animais"] == 3
        from fazenda.models import ProtocoloCustomizadoLancamento
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloCustomizadoLancamento)).all()) == 1

    def test_sem_animais_cria_tarefa_da_fazenda(self, client, monkeypatch):
        c, engine = client
        criado = _criar_protocolo(c, etapas=[_etapa(0), _etapa(1), _etapa(2)]).json()
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": [], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 201
        from fazenda.models import ProtocoloCustomizadoAplicacao
        with Session(engine) as s:
            aps = s.exec(select(ProtocoloCustomizadoAplicacao)).all()
        assert len(aps) == 3
        assert all(a.numero_matriz is None for a in aps)

    def test_protocolo_inexistente_404(self, client):
        c, _ = client
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": 9999, "animais": ["800"], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 404

    def test_protocolo_inativo_400(self, client):
        c, _ = client
        criado = _criar_protocolo(c).json()
        c.put(f"/cadastro/protocolos-customizados/{criado['id']}", json={
            "nome": criado["nome"], "categoria": "Atividades", "dia_inicial": 0, "ativo": False,
            "etapas": [_etapa(0)],
        })
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["800"], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 400

    def test_editar_template_nao_altera_lancamento_ja_feito(self, client):
        c, engine = client
        criado = _criar_protocolo(c, nome="Original", etapas=[_etapa(0, "Evento original")]).json()
        c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["800"], "data_inicio": "2026-03-01",
        })
        c.put(f"/cadastro/protocolos-customizados/{criado['id']}", json={
            "nome": "Renomeado", "categoria": "Atividades", "dia_inicial": 0,
            "etapas": [_etapa(0, "Evento novo")],
        })
        from fazenda.models import ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento
        with Session(engine) as s:
            lanc = s.exec(select(ProtocoloCustomizadoLancamento)).first()
            ap = s.exec(select(ProtocoloCustomizadoAplicacao)).first()
        assert lanc.nome_protocolo == "ORIGINAL - 01/03/26 A 01/03/26 (D0 A D0 - 1 DIAS)"
        assert ap.descricao == "Evento original"


class TestAgenda:
    def _lancar(self, c, animais=None, data_inicio="2026-03-01", categoria="Atividades", dia_inicial=0):
        criado = _criar_protocolo(c, categoria=categoria, dia_inicial=dia_inicial, etapas=[
            _etapa(dia_inicial, "Aplicar vacina", insumo="Vacina X"),
            _etapa(dia_inicial + 1, "Reforço", insumo="Vacina X"),
        ]).json()
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": animais or [], "data_inicio": data_inicio,
        })
        return criado, r.json()

    def test_um_evento_por_dia_agrupando_animais(self, client):
        c, _ = client
        self._lancar(c, animais=["800", "801", "802"])
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        assert r.status_code == 200
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert len(eventos) == 2  # um por dia (D0 e D1), não um por animal
        for e in eventos:
            assert set(e["animais"]) == {"800", "801", "802"}
            assert e["numero_animal"] is None

    def test_um_animal_numero_animal_preenchido(self, client):
        c, _ = client
        self._lancar(c, animais=["800"])
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert eventos[0]["numero_animal"] == "800"

    def test_descricao_traz_nome_e_dia_e_observacao_traz_insumo(self, client):
        c, _ = client
        criado, _ = self._lancar(c, animais=["800"])
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        ev_d0 = next(e for e in eventos if e["dia"] == 0)
        # Nome vira automático (nome cadastrado + data D0 + último dia) — não
        # digitado mais na hora do lançamento.
        assert criado["nome"].upper() in ev_d0["descricao"]
        assert "D0" in ev_d0["descricao"]
        assert "Vacina X" in (ev_d0["observacao"] or "")
        assert ev_d0["cor"] == "var(--dourado)"
        assert ev_d0["ref"] is None

    def test_categoria_do_lancamento_aparece_no_evento(self, client):
        c, _ = client
        self._lancar(c, animais=["800"], categoria="Rebanho")
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert all(e["categoria"] == "Rebanho" for e in eventos)

    def test_permissao_por_categoria(self, client):
        c, _ = client
        self._lancar(c, animais=["800"], categoria="Reprodutivo")
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _FakeFuncionario()
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert eventos == []  # funcionário só tem "rebanho", não "reproducao"

    def test_permissao_categoria_liberada_aparece(self, client):
        c, _ = client
        self._lancar(c, animais=["800"], categoria="Rebanho")
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _FakeFuncionario()
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert len(eventos) == 2  # D0 e D1, ambos visíveis (categoria "Rebanho" liberada)

    def test_marcar_realizado_grupo_inteiro(self, client):
        c, _ = client
        self._lancar(c, animais=["800", "801"])
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        evento_id = next(e["id"] for e in eventos if e["dia"] == 0)
        r2 = c.post("/agenda/realizados", json={"evento_id": evento_id})
        assert r2.status_code == 200
        r3 = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos3 = [e for e in r3.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert all(e["id"] != evento_id for e in eventos3)

    def test_marcar_realizado_subconjunto(self, client):
        c, _ = client
        self._lancar(c, animais=["800", "801"])
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        ev = next(e for e in eventos if e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": ev["id"], "animais": ["800"]})
        r2 = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos2 = [e for e in r2.json()["eventos"] if e.get("tipo") == "protocolo_customizado" and e["dia"] == 0]
        assert len(eventos2) == 1
        assert eventos2[0]["animais"] == ["801"]

    def test_desmarcar_realizado_volta_a_aparecer(self, client):
        c, _ = client
        self._lancar(c, animais=["800"])
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        ev = next(e for e in eventos if e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": ev["id"]})
        c.delete(f"/agenda/realizados/{ev['id']}")
        r2 = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos2 = [e for e in r2.json()["eventos"] if e.get("tipo") == "protocolo_customizado" and e["id"] == ev["id"]]
        assert len(eventos2) == 1

    def test_janela_de_atraso(self, client):
        c, _ = client
        # 10 dias atrás — dentro da janela de 30 dias, deve aparecer
        self._lancar(c, animais=["800"], data_inicio="2026-02-19")
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 0})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert len(eventos) >= 1

    def test_janela_de_atraso_expira_apos_30_dias(self, client):
        c, _ = client
        self._lancar(c, animais=["800"], data_inicio="2025-12-01")  # bem mais de 30 dias antes de 2026-03-01
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 0})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert eventos == []

    def test_cancelar_lancamento_some_da_agenda(self, client):
        c, _ = client
        criado, resultado = self._lancar(c, animais=["800"])
        c.post(f"/protocolos-customizados/{resultado['lancamento_id']}/cancelar")
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert eventos == []

    def test_nao_gera_sanidade_nem_baixa_estoque(self, client):
        c, engine = client
        self._lancar(c, animais=["800"])
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        ev = next(e for e in eventos if e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": ev["id"]})
        with Session(engine) as s:
            assert s.exec(select(Sanidade)).all() == []


class TestIsolamentoFazenda:
    def _liberar_contrato(self, engine, fazenda_ids=(1, 2)):
        with Session(engine) as s:
            for fid in fazenda_ids:
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                for modulo in MODULOS_COMERCIAIS:
                    s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.commit()

    def test_lancamento_de_outra_fazenda_nao_aparece_na_agenda(self, client, monkeypatch):
        c, engine = client
        self._liberar_contrato(engine)
        import main
        from fazenda.auth import get_fazenda_atual_id

        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        criado = _criar_protocolo(c, etapas=[_etapa(0)]).json()
        c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["800"], "data_inicio": "2026-03-01",
        })

        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 2
        r = c.get("/agenda/", params={"data": "2026-03-01", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert eventos == []

    def test_editar_protocolo_de_outra_fazenda_404(self, client):
        c, engine = client
        self._liberar_contrato(engine)
        import main
        from fazenda.auth import get_fazenda_atual_id

        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        criado = _criar_protocolo(c, etapas=[_etapa(0)]).json()

        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 2
        r = c.put(f"/cadastro/protocolos-customizados/{criado['id']}", json={
            "nome": "X", "categoria": "Atividades", "dia_inicial": 0, "etapas": [_etapa(0)],
        })
        assert r.status_code == 404
