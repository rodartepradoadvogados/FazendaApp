"""
Testes de cadastro de item de estoque — POST /estoque/ (criação) e
PUT /estoque/{id} (edição completa, usada pelo botão "editar" da tabela
filtrada de Estoque no site), incluindo o campo tipo_semen (sexado/convencional).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import CategoriaMedicamento, Estoque, EstoqueCategoriaMedicamento, MovimentoEstoque


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


class TestCriarItemEstoque:
    def test_cria_item_com_tipo_semen(self, client):
        c, _ = client
        r = c.post("/estoque/", json={
            "nome": "Sêmen 7HO12345", "categoria": "Sêmen e genética",
            "unidade": "dose", "quantidade": 10, "tipo_semen": "sexado",
        })
        assert r.status_code == 201, r.text
        assert r.json()["tipo_semen"] == "sexado"

    def test_nao_duplica_nome(self, client):
        c, _ = client
        c.post("/estoque/", json={"nome": "Ração X", "unidade": "kg"})
        r = c.post("/estoque/", json={"nome": "Ração X", "unidade": "kg"})
        assert r.status_code == 409

    def test_flag_gera_patrimonio(self, client):
        c, _ = client
        r = c.post("/estoque/", json={"nome": "Trator Massey", "gera_patrimonio": True})
        assert r.status_code == 201, r.text
        assert r.json()["gera_patrimonio"] is True

    def test_gera_patrimonio_padrao_false(self, client):
        c, _ = client
        r = c.post("/estoque/", json={"nome": "Ração Y", "unidade": "kg"})
        assert r.json()["gera_patrimonio"] is False

    def test_carencia_leite_carne_lactacao_e_laboratorio_sao_salvos(self, client):
        """Achado (01/09/2026): o modelo/migração/tela ganharam carência
        leite/carne, "proibido em lactação" e laboratório, mas o endpoint de
        cadastro (`EstoqueIn`) nunca declarou esses campos — o valor digitado
        no formulário era silenciosamente descartado. Cobre o cadastro via
        API de verdade (não direto no banco)."""
        c, engine = client
        r = c.post("/estoque/", json={
            "nome": "Draxxin KP", "finalidade": "Medicamento", "unidade": "ml",
            "carencia_leite_dias": 0, "carencia_carne_dias": 18, "proibido_lactacao": True,
            "laboratorio": "Zoetis",
        })
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["carencia_carne_dias"] == 18
        assert corpo["proibido_lactacao"] is True
        assert corpo["laboratorio"] == "Zoetis"
        with Session(engine) as s:
            item = s.get(Estoque, corpo["id"])
            assert item.carencia_carne_dias == 18
            assert item.proibido_lactacao is True
            assert item.laboratorio == "Zoetis"

    def test_categoria_medicamento_cumulativa_via_api(self, client):
        """Pedido do usuário (01/09/2026): categoria (medicamento) cumulativa
        no cadastro de item de estoque do tenant, via API de verdade."""
        c, engine = client
        with Session(engine) as s:
            cat1 = CategoriaMedicamento(nome="Antibiótico", fazenda_id=None)
            cat2 = CategoriaMedicamento(nome="Anti-inflamatório", fazenda_id=None)
            s.add(cat1); s.add(cat2)
            s.commit(); s.refresh(cat1); s.refresh(cat2)
            cat1_id, cat2_id = cat1.id, cat2.id

        r = c.post("/estoque/", json={
            "nome": "Maxicam 2%", "finalidade": "Medicamento", "unidade": "ml",
            "categoria_medicamento_ids": [cat1_id, cat2_id],
        })
        assert r.status_code == 201, r.text
        item_id = r.json()["id"]

        with Session(engine) as s:
            vinculos = {
                v.categoria_medicamento_id
                for v in s.exec(select(EstoqueCategoriaMedicamento).where(EstoqueCategoriaMedicamento.estoque_id == item_id)).all()
            }
            assert vinculos == {cat1_id, cat2_id}
            item = s.get(Estoque, item_id)
            assert item.classificacao_medicamento == "Antibiótico"  # espelho da 1ª categoria

        r_listar = c.get("/estoque/")
        linha = next(i for i in r_listar.json()["itens"] if i["id"] == item_id)
        assert set(linha["categoria_medicamento_ids"]) == {cat1_id, cat2_id}


class TestSaldoInicialGeraEntrada:
    """Saldo inicial informado no cadastro é uma entrada de verdade — precisa
    aparecer no Mapa de entradas (Sanidade > Insumos e Sanidade), não só em
    Estoque.quantidade (ver criar_item_estoque, fazenda/api/routers/estoque.py)."""

    def test_saldo_inicial_positivo_cria_movimento_de_entrada(self, client):
        c, engine = client
        criado = c.post("/estoque/", json={
            "nome": "Vacina Y", "unidade": "ml", "quantidade": 24, "estocavel": True,
            "data_inicio_controle": "2026-08-16",
        }).json()

        with Session(engine) as s:
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "cadastro_estoque", MovimentoEstoque.origem_id == criado["id"])).first()
            assert mov is not None
            assert mov.movimento == "Saldo inicial"
            assert mov.quantidade == 24
            assert str(mov.data_movimento) == "2026-08-16"
            assert mov.estoque_id == criado["id"]

    def test_sem_saldo_inicial_nao_cria_movimento(self, client):
        c, engine = client
        criado = c.post("/estoque/", json={"nome": "Ração Z", "unidade": "kg"}).json()

        with Session(engine) as s:
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "cadastro_estoque", MovimentoEstoque.origem_id == criado["id"])).first()
            assert mov is None

    def test_item_nao_estocavel_com_quantidade_nao_cria_movimento(self, client):
        c, engine = client
        criado = c.post("/estoque/", json={"nome": "Serviço financeiro", "quantidade": 5, "estocavel": False}).json()

        with Session(engine) as s:
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "cadastro_estoque", MovimentoEstoque.origem_id == criado["id"])).first()
            assert mov is None


class TestAtualizarItemEstoque:
    def test_edita_todos_os_campos(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={
            "nome": "Antibiótico A", "categoria": "Medicamentos e produtos veterinários",
            "unidade": "ml", "quantidade": 100, "estoque_minimo": 10, "valor_unitario": 2.5,
        }).json()

        r = c.put(f"/estoque/{criado['id']}", json={
            "nome": "Antibiótico A (novo nome)", "categoria": "Medicamentos e produtos veterinários",
            "finalidade": "Medicamento", "unidade": "ml", "quantidade": 200, "estoque_minimo": 20,
            "valor_unitario": 3.0, "principio_ativo": "Oxitetraciclina",
        })
        assert r.status_code == 200, r.text
        atualizado = r.json()
        assert atualizado["nome"] == "Antibiótico A (novo nome)"
        assert atualizado["quantidade"] == 200
        assert atualizado["estoque_minimo"] == 20
        assert atualizado["valor_total"] == 600
        assert atualizado["abaixo_minimo"] is False
        assert atualizado["principio_ativo"] == "Oxitetraciclina"

    def test_edita_tipo_semen(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={
            "nome": "Sêmen ABS 1", "categoria": "Sêmen e genética", "unidade": "dose",
            "quantidade": 5, "tipo_semen": "convencional",
        }).json()

        r = c.put(f"/estoque/{criado['id']}", json={
            "nome": "Sêmen ABS 1", "categoria": "Sêmen e genética", "unidade": "dose",
            "quantidade": 5, "tipo_semen": "sexado",
        })
        assert r.status_code == 200
        assert r.json()["tipo_semen"] == "sexado"

    def test_editar_quantidade_grava_movimento_de_ajuste(self, client):
        """Gauntlet A-14: editar a quantidade direto no cadastro do item
        (PUT /estoque/{id}) mudava `Estoque.quantidade` sem gerar nenhum
        MovimentoEstoque — invisível no Mapa de Entradas/Saídas e no custo
        físico do RMCA, diferente de toda outra baixa/ajuste do sistema."""
        c, engine = client
        criado = c.post("/estoque/", json={
            "nome": "Sal mineral", "categoria": "Nutrição animal", "unidade": "kg",
            "quantidade": 100, "estoque_minimo": 10, "valor_unitario": 2.0,
        }).json()

        r = c.put(f"/estoque/{criado['id']}", json={
            "nome": "Sal mineral", "categoria": "Nutrição animal", "unidade": "kg",
            "quantidade": 130, "estoque_minimo": 10, "valor_unitario": 2.0,
        })
        assert r.status_code == 200, r.text
        assert r.json()["quantidade"] == 130

        with Session(engine) as s:
            ajustes = s.exec(
                select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "cadastro_estoque")
            ).all()
        ajustes_de_edicao = [m for m in ajustes if m.movimento == "Entrada de ajuste" and m.quantidade == 30]
        assert len(ajustes_de_edicao) == 1, "aumentar a quantidade editada tem que gravar uma Entrada de ajuste"

    def test_editar_quantidade_para_baixo_grava_saida_de_ajuste(self, client):
        c, engine = client
        criado = c.post("/estoque/", json={
            "nome": "Ureia", "categoria": "Nutrição animal", "unidade": "kg", "quantidade": 100,
        }).json()

        r = c.put(f"/estoque/{criado['id']}", json={
            "nome": "Ureia", "categoria": "Nutrição animal", "unidade": "kg", "quantidade": 60,
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            ajustes = s.exec(
                select(MovimentoEstoque).where(
                    MovimentoEstoque.origem_tipo == "cadastro_estoque", MovimentoEstoque.movimento == "Saída de ajuste",
                )
            ).all()
        assert len(ajustes) == 1
        assert ajustes[0].quantidade == 40

    def test_editar_sem_mudar_quantidade_nao_gera_movimento_extra(self, client):
        c, engine = client
        criado = c.post("/estoque/", json={
            "nome": "Fosfato bicálcico", "categoria": "Nutrição animal", "unidade": "kg", "quantidade": 50,
        }).json()
        with Session(engine) as s:
            antes = len(s.exec(select(MovimentoEstoque)).all())

        r = c.put(f"/estoque/{criado['id']}", json={
            "nome": "Fosfato bicálcico (renomeado)", "categoria": "Nutrição animal", "unidade": "kg", "quantidade": 50,
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            depois = len(s.exec(select(MovimentoEstoque)).all())
        assert depois == antes, "quantidade igual não pode gerar movimento de ajuste"

    def test_404_para_item_inexistente(self, client):
        c, _ = client
        r = c.put("/estoque/999", json={"nome": "Não existe", "unidade": "un"})
        assert r.status_code == 404

    def test_409_ao_renomear_para_nome_ja_usado(self, client):
        c, _ = client
        c.post("/estoque/", json={"nome": "Item 1", "unidade": "un"})
        item2 = c.post("/estoque/", json={"nome": "Item 2", "unidade": "un"}).json()

        r = c.put(f"/estoque/{item2['id']}", json={"nome": "Item 1", "unidade": "un"})
        assert r.status_code == 409


class TestExcluirItemEstoque:
    def test_exclui_item_sem_movimento(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={"nome": "Item novo, nunca usado", "unidade": "un"}).json()

        r = c.delete(f"/estoque/{criado['id']}")
        assert r.status_code == 200, r.text
        assert r.json() == {"excluido": True}

        itens = c.get("/estoque/").json()["itens"]
        assert not any(i["id"] == criado["id"] for i in itens)

    def test_404_para_item_inexistente(self, client):
        c, _ = client
        r = c.delete("/estoque/9999")
        assert r.status_code == 404

    def test_409_com_movimento_vinculado_e_item_continua_existindo(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={"nome": "Ração com movimento", "unidade": "kg", "quantidade": 0}).json()
        mov = c.post("/estoque/movimentar", json={
            "nome": "Ração com movimento", "movimento": "Entrada de ajuste", "quantidade": 10,
            "unidade": "kg", "data_movimento": "2026-08-01",
        })
        assert mov.status_code == 200, mov.text

        r = c.delete(f"/estoque/{criado['id']}")
        assert r.status_code == 409, r.text
        assert "Ração com movimento" in r.json()["detail"]

        itens = c.get("/estoque/").json()["itens"]
        assert any(i["id"] == criado["id"] for i in itens)
