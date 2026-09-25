"""
Painel CowData > Cotações — catálogo de produtos-padrão/preços-base
sugeridos, cotados com os fornecedores da PRÓPRIA CowData. Ver
fazenda/api/routers/painel_cowdata_cotacoes.py e
fazenda/models/catalogo_cowdata.py.

Cobre: gate de área/permissão (403 sem área; leitura livre com área, escrita
exige a permissão de edição também), o fluxo funcional completo (cadastro →
cotação → resposta → fechar → atribuir preço, com e sem média), e — o ponto
mais sensível — a muralha de privacidade: a leitura pública/farm-facing
(`GET /estoque/precos-referencia-cowdata`) nunca inclui NENHUM campo de
fornecedor, respeita `publicado` e o opt-out por fazenda.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fazenda.auth import EMAIL_DONO, get_current_user, get_fazenda_atual_id
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, PermissaoEquipeCowData, Usuario
from fazenda.models.planos import MODULOS_COMERCIAIS


class _FakeUser:
    def __init__(self, id=1, email=EMAIL_DONO, papel="admin"):
        self.id = id
        self.papel = papel
        self.ativo = True
        self.username = "teste"
        self.email = email
        self.permissoes = ""


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Cliente"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.add(Usuario(id=1, username="dono", nome="Jairo", senha_hash="x", papel="admin", email=EMAIL_DONO))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_usuario(fake_user: _FakeUser):
    import main
    main.app.dependency_overrides[get_current_user] = lambda: fake_user


def _como_fazenda(fazenda_id: int | None):
    import main
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestGateDeAreaEPermissao:
    def test_sem_area_bloqueia_leitura(self, client):
        c, _ = client
        _como_usuario(_FakeUser(email="comum@x.com"))
        r = c.get("/painel-cowdata/cotacoes/classificacoes")
        assert r.status_code == 403

    def test_com_area_sem_permissao_le_mas_nao_escreve(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Usuario(id=2, username="comercial", nome="Comercial", senha_hash="x", papel="admin", email="comercial@x.com"))
            s.add(PermissaoEquipeCowData(usuario_id=2, areas="cotacoes"))
            s.commit()
        _como_usuario(_FakeUser(id=2, email="comercial@x.com"))

        leitura = c.get("/painel-cowdata/cotacoes/classificacoes")
        assert leitura.status_code == 200

        escrita = c.post("/painel-cowdata/cotacoes/classificacoes", json={"nome": "Nova"})
        assert escrita.status_code == 403

    def test_com_area_e_permissao_escreve(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Usuario(id=2, username="comercial", nome="Comercial", senha_hash="x", papel="admin", email="comercial@x.com"))
            s.add(PermissaoEquipeCowData(usuario_id=2, areas="cotacoes", pode_editar_cotacoes=True))
            s.commit()
        _como_usuario(_FakeUser(id=2, email="comercial@x.com"))
        r = c.post("/painel-cowdata/cotacoes/classificacoes", json={"nome": "Nova classificação"})
        assert r.status_code == 201, r.text


class TestFluxoCompleto:
    def _setup_basico(self, c):
        classificacao = c.post("/painel-cowdata/cotacoes/classificacoes", json={"nome": "Ração e insumos"}).json()
        finalidade = c.post("/painel-cowdata/cotacoes/finalidades", json={"nome": "Energético"}).json()
        f1 = c.post("/painel-cowdata/cotacoes/fornecedores", json={
            "nome": "Fornecedor Um", "classificacao_ids": [classificacao["id"]], "finalidade_ids": [finalidade["id"]],
        }).json()
        f2 = c.post("/painel-cowdata/cotacoes/fornecedores", json={
            "nome": "Fornecedor Dois", "classificacao_ids": [classificacao["id"]], "finalidade_ids": [],
        }).json()
        produto = c.post("/painel-cowdata/cotacoes/produtos", json={
            "nome": "Silagem de milho", "unidade": "saca 50kg", "classificacao_id": classificacao["id"], "finalidade_ids": [finalidade["id"]],
        }).json()
        return classificacao, finalidade, f1, f2, produto

    def test_cadastro_fornecedor_com_classificacao_e_finalidade_multipla(self, client):
        c, _ = client
        classificacao, finalidade, f1, _, _ = self._setup_basico(c)
        assert len(f1["classificacoes"]) == 1
        assert len(f1["finalidades"]) == 1
        # nunca aparece cru "finalidade:"/"classificação:" no rótulo — o
        # objeto devolve id+nome estruturado, quem monta texto é o backend.
        assert f1["classificacoes"][0]["nome"] == "Ração e insumos"

    def test_produto_checar_duplicata_sugere_parecido(self, client):
        c, _ = client
        self._setup_basico(c)
        r = c.get("/painel-cowdata/cotacoes/produtos/checar-duplicata", params={"nome": "Silagem milho"})
        assert r.status_code == 200
        assert any("Silagem de milho" in s["nome"] for s in r.json())

    def test_cotacao_por_produto_resposta_fechar_atribuir_vencedor_e_publica(self, client):
        c, _ = client
        classificacao, finalidade, f1, f2, produto = self._setup_basico(c)

        cot = c.post("/painel-cowdata/cotacoes", json={"titulo": "Cotação teste"}).json()
        cid = cot["id"]
        assert cot["status"] == "rascunho"

        item = c.post(f"/painel-cowdata/cotacoes/{cid}/itens", json={
            "modo": "produto", "produto_padrao_id": produto["id"],
        }).json()
        item_id = item["itens"][0]["id"]
        assert item["itens"][0]["rotulo"] == "Silagem de milho"

        c.post(f"/painel-cowdata/cotacoes/{cid}/fornecedores", json={"fornecedor_ids": [f1["id"], f2["id"]]})

        r_resp = c.put(f"/painel-cowdata/cotacoes/{cid}/itens/{item_id}/respostas/{f1['id']}", json={
            "valor": 52.0, "condicao_pagamento": "30 dias", "prazo_entrega_dias": 5,
        })
        assert r_resp.status_code == 200
        assert r_resp.json()["status"] == "em_andamento"

        fechada = c.post(f"/painel-cowdata/cotacoes/{cid}/fechar")
        assert fechada.status_code == 200
        assert fechada.json()["status"] == "fechada"

        # não publicado por padrão — não deve aparecer na leitura da fazenda
        preco = c.post(f"/painel-cowdata/cotacoes/produtos/{produto['id']}/atribuir-preco", json={
            "valor": 52.0, "origem": "cotacao", "cotacao_cowdata_item_id": item_id,
            "fornecedor_escolhido_id": f1["id"], "eh_media": False, "publicar": False,
        })
        assert preco.status_code == 201, preco.text
        assert preco.json()["publicado"] is False
        assert preco.json()["fornecedor_escolhido_nome"] == "Fornecedor Um"

        _como_fazenda(1)
        leitura_fazenda_oculta = c.get("/estoque/precos-referencia-cowdata")
        assert leitura_fazenda_oculta.status_code == 200
        assert leitura_fazenda_oculta.json() == []

        # publica agora — passa a aparecer, sem NENHUM campo de fornecedor
        preco_id = preco.json()["id"]
        pub = c.put(f"/painel-cowdata/cotacoes/precos/{preco_id}/publicar", json={"publicado": True})
        assert pub.status_code == 200

        leitura_fazenda = c.get("/estoque/precos-referencia-cowdata")
        assert leitura_fazenda.status_code == 200
        corpo = leitura_fazenda.json()
        assert len(corpo) == 1
        assert corpo[0]["nome"] == "Silagem de milho"
        assert corpo[0]["valor"] == 52.0
        texto_bruto = str(corpo[0])
        assert "fornecedor" not in texto_bruto.lower()
        assert "Fornecedor Um" not in texto_bruto

    def test_atribuir_preco_por_media_exige_dois_participantes(self, client):
        c, _ = client
        _, _, f1, f2, produto = self._setup_basico(c)
        r = c.post(f"/painel-cowdata/cotacoes/produtos/{produto['id']}/atribuir-preco", json={
            "valor": 50.0, "origem": "manual", "eh_media": True,
            "participantes_media": [{"fornecedor_cowdata_id": f1["id"], "valor_informado": 48.0}],
            "publicar": False,
        })
        assert r.status_code == 400

        r2 = c.post(f"/painel-cowdata/cotacoes/produtos/{produto['id']}/atribuir-preco", json={
            "valor": 50.0, "origem": "manual", "eh_media": True,
            "participantes_media": [
                {"fornecedor_cowdata_id": f1["id"], "valor_informado": 48.0},
                {"fornecedor_cowdata_id": f2["id"], "valor_informado": 52.0},
            ],
            "publicar": True,
        })
        assert r2.status_code == 201, r2.text
        assert r2.json()["eh_media"] is True
        assert r2.json()["fornecedor_escolhido_id"] is None
        assert len(r2.json()["participantes_media"]) == 2

        _como_fazenda(1)
        leitura = c.get("/estoque/precos-referencia-cowdata").json()
        assert "media" not in str(leitura).lower() and "Fornecedor" not in str(leitura)

    def test_fazenda_pode_desligar_opt_out(self, client):
        c, _ = client
        _, _, f1, _, produto = self._setup_basico(c)
        c.post(f"/painel-cowdata/cotacoes/produtos/{produto['id']}/atribuir-preco", json={
            "valor": 40.0, "origem": "manual", "publicar": True,
        })
        _como_fazenda(1)
        assert len(c.get("/estoque/precos-referencia-cowdata").json()) == 1

        cfg = c.put("/estoque/precos-referencia-cowdata/config", json={"mostrar": False})
        assert cfg.status_code == 200
        assert c.get("/estoque/precos-referencia-cowdata").json() == []

        cfg2 = c.get("/estoque/precos-referencia-cowdata/config")
        assert cfg2.json()["mostrar_precos_referencia_cowdata"] is False
