"""
Isolamento entre fazendas do item de Estoque espelhado de sêmen
(`sincronizar_item_estoque_semen`, em fazenda/api/routers/estoque.py) —
esse item nascia SEM `fazenda_id` (ficava NULL), vazando entre fazendas nas
listagens sem filtro e sumindo das listagens que já filtram por
`Estoque.fazenda_id` (ex.: `GET /estoque/`). Cobre também o backfill que
corrige o histórico (`backfill_estoque_semen_fazenda_id`) e a autocura feita
por `sincronizar_item_estoque_semen` quando o item já existe.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, EstoqueSemen, Fazenda, SeedFlag
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client_engine():
    """Expõe o `engine` (além do TestClient) — os testes abaixo chamam
    `sincronizar_item_estoque_semen`/`backfill_estoque_semen_fazenda_id`
    diretamente contra uma sessão, fora do ciclo de requisição HTTP, e também
    fazem chamadas HTTP reais sob duas fazendas (1 e 2) já com contrato ativo
    e módulo "rebanho" contratado — sem isso, `exigir_modulo_contratado`
    devolveria 403 assim que a fazenda selecionada deixasse de ser None."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda A"))
        s.add(Fazenda(id=2, nome="Fazenda B"))
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


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestSincronizacaoGravaFazendaId:
    """Prova do vínculo correto: o item de Estoque espelhado nasce com o
    mesmo fazenda_id do touro (EstoqueSemen) que ele espelha."""

    def test_item_novo_herda_fazenda_id_do_touro(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import sincronizar_item_estoque_semen

        with Session(engine) as s:
            touro = EstoqueSemen(touro_nome="Coors", tipo="convencional", doses=10, fazenda_id=7)
            s.add(touro)
            s.commit()
            s.refresh(touro)
            touro_id = touro.id
            sincronizar_item_estoque_semen(touro, s)
            s.commit()

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.estoque_semen_id == touro_id)).first()
            assert item is not None
            assert item.fazenda_id == 7

    def test_compra_de_semen_pelo_endpoint_grava_fazenda_id_no_item_espelhado(self, client_engine):
        """Fim a fim, via HTTP: POST /compras-semen/ (que chama
        sincronizar_item_estoque_semen internamente) deve deixar o item de
        Estoque espelhado já com o fazenda_id correto — não NULL."""
        c, engine = client_engine
        _como_fazenda(1)
        r = c.post("/compras-semen/", json={
            "itens": [{"origem": "naab", "naab": "7HO12345", "touro_nome": "Supersire", "valor": 50.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        # Precisa existir o Touro no catálogo NAAB para casar — cria antes se preciso.
        if r.status_code == 404:
            with Session(engine) as s:
                from fazenda.models import Touro
                s.add(Touro(naab="7HO12345", nome="Supersire", central="ABS"))
                s.commit()
            r = c.post("/compras-semen/", json={
                "itens": [{"origem": "naab", "naab": "7HO12345", "touro_nome": "Supersire", "valor": 50.0, "tipo_valor": "por_dose", "doses": 10}],
                "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
            })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.categoria == "Sêmen e genética")).first()
            assert item is not None
            assert item.fazenda_id == 1


class TestIsolamentoEntreFazendas:
    """Prova do isolamento: um item de Estoque espelhado de sêmen da fazenda
    A não pode aparecer na listagem de Estoque da fazenda B."""

    def test_fazenda_b_nao_ve_item_de_semen_da_fazenda_a(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import sincronizar_item_estoque_semen

        with Session(engine) as s:
            touro_a = EstoqueSemen(touro_nome="Touro Fazenda A", tipo="convencional", doses=10, fazenda_id=1)
            s.add(touro_a)
            s.commit()
            s.refresh(touro_a)
            sincronizar_item_estoque_semen(touro_a, s)
            s.commit()

        _como_fazenda(2)
        r = c.get("/estoque/")
        assert r.status_code == 200
        nomes = {i["nome"] for i in r.json()["itens"]}
        assert "Sêmen — Touro Fazenda A" not in nomes

        _como_fazenda(1)
        r = c.get("/estoque/")
        assert r.status_code == 200
        nomes = {i["nome"] for i in r.json()["itens"]}
        assert "Sêmen — Touro Fazenda A" in nomes


class TestBackfillFazendaId:
    """Corrige o histórico: itens de Estoque de sêmen legados que ficaram
    com fazenda_id NULL (criados antes desta correção)."""

    def _limpar_marca(self, session):
        flag = session.get(SeedFlag, "estoque_semen_backfill_fazenda_id_202608")
        if flag:
            session.delete(flag)
            session.commit()

    def test_preenche_fazenda_id_a_partir_do_touro_vinculado(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import backfill_estoque_semen_fazenda_id

        with Session(engine) as s:
            self._limpar_marca(s)
            touro = EstoqueSemen(touro_nome="Legado", tipo="convencional", doses=5, fazenda_id=3)
            s.add(touro)
            s.commit()
            s.refresh(touro)
            # Simula o estado quebrado histórico: item espelhado sem fazenda_id.
            s.add(Estoque(
                nome="Sêmen — Legado", categoria="Sêmen e genética", unidade="dose",
                quantidade=5, estocavel=True, ativo=True, estoque_semen_id=touro.id, fazenda_id=None,
            ))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_id(s)

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sêmen — Legado")).first()
            assert item.fazenda_id == 3

    def test_roda_uma_unica_vez(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import backfill_estoque_semen_fazenda_id

        with Session(engine) as s:
            self._limpar_marca(s)
            touro = EstoqueSemen(touro_nome="Legado2", tipo="convencional", doses=5, fazenda_id=9)
            s.add(touro)
            s.commit()
            s.refresh(touro)
            s.add(Estoque(
                nome="Sêmen — Legado2", categoria="Sêmen e genética", unidade="dose",
                quantidade=5, estocavel=True, ativo=True, estoque_semen_id=touro.id, fazenda_id=None,
            ))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_id(s)
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sêmen — Legado2")).first()
            item.fazenda_id = None  # simula desfazer manualmente, pra provar que não roda de novo
            s.add(item)
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_id(s)  # já rodou uma vez — não deve rodar de novo

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sêmen — Legado2")).first()
            assert item.fazenda_id is None

    def test_nunca_sobrescreve_fazenda_id_ja_preenchido(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import backfill_estoque_semen_fazenda_id

        with Session(engine) as s:
            self._limpar_marca(s)
            touro = EstoqueSemen(touro_nome="Legado3", tipo="convencional", doses=5, fazenda_id=9)
            s.add(touro)
            s.commit()
            s.refresh(touro)
            # Item já tem fazenda_id preenchido (com um valor diferente do touro,
            # de propósito) — o backfill não deve mexer nele.
            s.add(Estoque(
                nome="Sêmen — Legado3", categoria="Sêmen e genética", unidade="dose",
                quantidade=5, estocavel=True, ativo=True, estoque_semen_id=touro.id, fazenda_id=42,
            ))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_id(s)

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sêmen — Legado3")).first()
            assert item.fazenda_id == 42


class TestAutocuraNaSincronizacao:
    """`sincronizar_item_estoque_semen` também autocura o item já existente
    (não só cria certo daqui pra frente) — assim, uma compra/baixa nova num
    item legado já corrige o fazenda_id, sem esperar o backfill único."""

    def test_atualizacao_de_item_existente_preenche_fazenda_id_ausente(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import sincronizar_item_estoque_semen

        with Session(engine) as s:
            touro = EstoqueSemen(touro_nome="Autocura", tipo="convencional", doses=5, fazenda_id=5)
            s.add(touro)
            s.commit()
            s.refresh(touro)
            touro_id = touro.id
            s.add(Estoque(
                nome="Sêmen — Autocura", categoria="Sêmen e genética", unidade="dose",
                quantidade=5, estocavel=True, ativo=True, estoque_semen_id=touro_id, fazenda_id=None,
            ))
            s.commit()

        with Session(engine) as s:
            touro = s.get(EstoqueSemen, touro_id)
            touro.doses = 8
            s.add(touro)
            sincronizar_item_estoque_semen(touro, s)
            s.commit()

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.estoque_semen_id == touro_id)).first()
            assert item.quantidade == 8
            assert item.fazenda_id == 5
