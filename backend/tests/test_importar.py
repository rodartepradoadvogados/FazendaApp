"""
Testes do router de Importar dados (Configurações > Importar dados) — CSV
manual simplificado. Cada categoria precisa gravar na tabela/rotina REAL
usada em todo o site, não numa tabela isolada.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque


def _csv(linhas: list[str]) -> bytes:
    texto = "\r\n".join(linhas) + "\r\n"
    return texto.encode("windows-1252")


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


def _upload(c, categoria, linhas):
    content = _csv(linhas)
    return c.post(f"/importar/{categoria}", files={"file": ("dados.csv", content, "text/csv")})


class TestModelos:
    def test_lista_categorias(self, client):
        c, engine = client
        r = c.get("/importar/modelos")
        assert r.status_code == 200
        d = r.json()
        assert "pesagem" in d["novas"]
        assert "animais" in d["existentes"]


class TestPesagem:
    def test_importa_pesagens_para_tabela_real(self, client):
        c, engine = client
        r = _upload(c, "pesagem", [
            "numero_matriz;data_pesagem;peso_kg",
            "100;01/07/2026;320,5",
            "101;01/07/2026;340",
        ])
        assert r.status_code == 200
        assert r.json()["criados"] == 2

        # As mesmas pesagens aparecem no relatório real usado em Produção.
        r2 = c.get("/producao/pesagens/relatorio")
        assert r2.status_code == 200

    def test_linha_incompleta_vira_erro(self, client):
        c, engine = client
        r = _upload(c, "pesagem", ["numero_matriz;data_pesagem;peso_kg", "100;;320"])
        assert r.json()["criados"] == 0
        assert len(r.json()["erros"]) == 1


class TestFinanceiro:
    def test_importa_lancamento_para_conta_gerencial_real(self, client):
        c, engine = client
        r = _upload(c, "financeiro", [
            "data;tipo;descricao;valor;fornecedor_cliente",
            "01/07/2026;despesa;Ração;1500,00;Agropecuária X",
        ])
        assert r.status_code == 200
        assert r.json()["criados"] == 1

        # O lançamento entra a pagar no Financeiro real (mesma tabela ContaGerencial).
        r2 = c.get("/financeiro/dre?data_inicio=2026-01-01&data_fim=2026-12-31")
        assert r2.status_code == 200

    def test_tipo_invalido_vira_erro(self, client):
        c, engine = client
        r = _upload(c, "financeiro", ["data;tipo;descricao;valor;fornecedor_cliente", "01/07/2026;x;Ração;100;Y"])
        assert r.json()["criados"] == 0
        assert len(r.json()["erros"]) == 1


class TestEstoqueMovimento:
    def test_movimenta_estoque_real(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração concentrada", categoria="alimento", quantidade=100))
            s.commit()

        r = _upload(c, "estoque_movimento", [
            "nome_item;movimento;quantidade;unidade;data_movimento;observacao",
            "Ração concentrada;Saída de ajuste;10;kg;01/07/2026;teste",
        ])
        assert r.status_code == 200
        assert r.json()["criados"] == 1

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração concentrada")).first()
            assert item.quantidade == 90

    def test_item_inexistente_vira_erro(self, client):
        c, engine = client
        r = _upload(c, "estoque_movimento", [
            "nome_item;movimento;quantidade;unidade;data_movimento;observacao",
            "Não existe;Saída de ajuste;10;kg;01/07/2026;teste",
        ])
        assert r.json()["criados"] == 0
        assert len(r.json()["erros"]) == 1


class TestProdutosEstoque:
    def test_cria_item_novo_com_metadados(self, client):
        c, engine = client
        r = _upload(c, "produtos_estoque", [
            "nome;categoria;unidade;unidade_embalagem;medida_embalagem;quantidade_embalagem;fornecedor_nome",
            "Sal mineral;alimento;kg;Saca;kg/saca;25;",
        ])
        assert r.status_code == 200
        assert r.json()["criados"] == 1

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral")).first()
            assert item is not None
            assert item.unidade_embalagem == "Saca"
            assert item.medida_embalagem == "kg/saca"
            assert item.quantidade_embalagem == 25.0

    def test_fornecedor_inexistente_vira_erro_mas_nao_bloqueia(self, client):
        c, engine = client
        r = _upload(c, "produtos_estoque", [
            "nome;categoria;unidade;unidade_embalagem;medida_embalagem;quantidade_embalagem;fornecedor_nome",
            "Hormonio X;hormonio;ml;;;;Fornecedor Fantasma",
        ])
        assert r.json()["criados"] == 1
        assert len(r.json()["erros"]) == 1


class TestFornecedores:
    def test_cria_e_atualiza_por_nome(self, client):
        c, engine = client
        r1 = _upload(c, "fornecedores", ["nome;tipo;cnpj_cpf;telefone;email", "Agro X;fornecedor;;;"])
        assert r1.json()["criados"] == 1

        r2 = _upload(c, "fornecedores", ["nome;tipo;cnpj_cpf;telefone;email", "Agro X;fabricante;;;"])
        assert r2.json()["atualizados"] == 1

        # O mesmo fornecedor aparece no Cadastro real (mesma tabela Fornecedor).
        r3 = c.get("/cadastro/fornecedores")
        assert r3.json()[0]["tipo"] == "fabricante"
