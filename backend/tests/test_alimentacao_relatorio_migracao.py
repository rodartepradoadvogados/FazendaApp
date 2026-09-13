"""
Testes do relatório de conferência da Fase P0-B (GET /alimentacao/migracao/relatorio)
— SOMENTE LEITURA: mostra fantasmas deixados pela importação antiga, "pontes"
nunca usadas, alimentos sem categoria, agrupamentos a desmembrar, divergência
de nome entre Alimento e Estoque, ingredientes de dieta não resolvíveis e o
impacto da futura regra de elegibilidade ao RMCA. Cada seção tem um caso
positivo e um vazio; mais isolamento por fazenda_id e a garantia de que o
endpoint não escreve nada no banco.
"""
from __future__ import annotations

import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Alimento, AlimentoNutricional, AnaliseBromatologica, CategoriaAlimento, CurvaABC, Dieta, Estoque,
    LancamentoItem, MovimentoEstoque, Sanidade,
)

TABELAS_RELEVANTES = [
    Alimento, AlimentoNutricional, AnaliseBromatologica, CategoriaAlimento, CurvaABC, Dieta, Estoque,
    LancamentoItem, MovimentoEstoque, Sanidade,
]


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    lock_conexao = threading.Lock()

    def _get_session_override():
        with lock_conexao, Session(engine) as session:
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


@pytest.fixture
def client_multi_fazenda():
    from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="alimentacao", ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    def _client(fazenda_id: int) -> TestClient:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id
        return TestClient(main.app)

    yield engine, _client

    main.app.dependency_overrides.clear()


def _contagens(engine) -> dict[str, int]:
    with Session(engine) as s:
        return {t.__tablename__: len(s.exec(select(t)).all()) for t in TABELAS_RELEVANTES}


class TestFantasmasImportacao:
    def test_item_com_assinatura_de_importacao_aparece_com_fontes_e_movimentos(self, client):
        c, engine = client
        with Session(engine) as s:
            e = Estoque(nome="Silagem de milho", quantidade=0, finalidade=None, alimento_id=None)
            s.add(e)
            s.commit()
            s.refresh(e)
            s.add(Dieta(lote=1, ingrediente="Silagem de milho", quantidade=20.0, unidade="kg"))
            s.add(Dieta(lote=2, ingrediente="Silagem de milho", quantidade=15.0, unidade="kg"))
            s.add(CurvaABC(produto="Silagem de milho"))
            s.add(Sanidade(numero_matriz="1", produto="Silagem de milho"))
            s.add(MovimentoEstoque(
                nome_item="Silagem de milho", estoque_id=e.id, movimento="Entrada de ajuste",
                quantidade=10.0, data_movimento=date(2026, 1, 5),
            ))
            s.commit()

        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = r.json()["fantasmas_importacao"]
        assert len(linhas) == 1
        linha = linhas[0]
        assert linha["nome"] == "Silagem de milho"
        assert linha["fontes"] == {"dieta": 2, "curva_abc": 1, "lancamento_item": 0, "sanidade": 1}
        assert linha["quantidade_movimentos"] == 1
        assert linha["primeiro_movimento"] == "2026-01-05"
        assert linha["ultimo_movimento"] == "2026-01-05"

    def test_item_normal_nao_entra_no_relatorio(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração comprada", quantidade=100.0, finalidade="Ração/Alimento"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        assert r.json()["fantasmas_importacao"] == []

    def test_candidatos_de_mesclagem_por_nome_normalizado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Sal mineral", quantidade=0, finalidade=None, alimento_id=None))
            s.add(Estoque(nome="Sal Mineral", quantidade=50.0, unidade="kg"))
            s.add(Estoque(nome="Sal-mineral premium", quantidade=30.0, unidade="kg"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        linha = r.json()["fantasmas_importacao"][0]
        nomes_candidatos = {cand["nome"] for cand in linha["candidatos_mesclagem"]}
        assert nomes_candidatos == {"Sal Mineral", "Sal-mineral premium"}


class TestFantasmasPonte:
    def test_ponte_sem_nenhum_movimento_aparece(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Milho moído")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="Milho moído", quantidade=200.0, unidade="kg", finalidade="Ração/Alimento", alimento_id=a.id))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = r.json()["fantasmas_ponte"]
        assert len(linhas) == 1
        assert linhas[0]["nome"] == "Milho moído"
        assert linhas[0]["quantidade_movimentos"] == 0

    def test_ponte_com_movimento_nao_aparece(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Farelo")
            s.add(a)
            s.commit()
            s.refresh(a)
            e = Estoque(nome="Farelo", quantidade=200.0, unidade="kg", finalidade="Ração/Alimento", alimento_id=a.id)
            s.add(e)
            s.commit()
            s.refresh(e)
            s.add(MovimentoEstoque(
                nome_item="Farelo", estoque_id=e.id, movimento="Saída de ajuste",
                quantidade=5.0, data_movimento=date(2026, 2, 1),
            ))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        assert r.json()["fantasmas_ponte"] == []


class TestProdutosSemCategoria:
    def test_alimento_vinculado_sem_categoria_e_finalidade_sem_vinculo(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Núcleo mineral", categoria_alimento_id=None)
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="Núcleo mineral", quantidade=10.0, finalidade="Ração/Alimento", alimento_id=a.id))
            s.add(Estoque(nome="Ração avulsa", quantidade=5.0, finalidade="Nutrição animal", alimento_id=None))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = r.json()["produtos_sem_categoria"]
        nomes = {l["nome"] for l in linhas}
        assert nomes == {"Núcleo mineral", "Ração avulsa"}
        for l in linhas:
            assert l["motivo"]

    def test_alimento_com_categoria_nao_entra(self, client):
        c, engine = client
        with Session(engine) as s:
            cat = CategoriaAlimento(nome="Volumoso")
            s.add(cat)
            s.commit()
            s.refresh(cat)
            a = Alimento(nome="Silagem", categoria_alimento_id=cat.id)
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="Silagem", quantidade=10.0, finalidade="Ração/Alimento", alimento_id=a.id))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        assert r.json()["produtos_sem_categoria"] == []

    def test_categoria_direta_no_estoque_tambem_exclui_da_lista(self, client):
        """Fase P1, Gap 2 — `Estoque.categoria_alimento_id` satisfaz "tem
        categoria" por si só, mesmo sem NENHUM vínculo de Alimento (o
        caminho que até aqui era obrigatório)."""
        c, engine = client
        with Session(engine) as s:
            cat = CategoriaAlimento(nome="Concentrado")
            s.add(cat)
            s.commit()
            s.refresh(cat)
            s.add(Estoque(
                nome="Ração avulsa categorizada", quantidade=5.0, finalidade="Nutrição animal",
                alimento_id=None, categoria_alimento_id=cat.id,
            ))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        assert r.json()["produtos_sem_categoria"] == []


class TestDesmembramentos:
    def test_alimento_com_dois_produtos_aparece_com_flag_nutricional(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Silagem de milho")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="Silagem de milho - Fornecedor A", quantidade=100.0, alimento_id=a.id))
            s.add(Estoque(nome="Silagem de milho - Fornecedor B", quantidade=200.0, alimento_id=a.id))
            s.add(AlimentoNutricional(alimento_id=a.id, nome="Silagem de milho", categoria_nasem="Volumoso"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = r.json()["desmembramentos"]
        assert len(linhas) == 1
        assert linhas[0]["alimento_nome"] == "Silagem de milho"
        assert len(linhas[0]["produtos"]) == 2
        assert linhas[0]["tem_alimento_nutricional"] is True
        assert linhas[0]["estoque_preferido_id"] is None  # ninguém escolheu ainda (Fase P1)

    def test_mostra_o_estoque_preferido_quando_ja_escolhido(self, client):
        """Fase P1, Gap 3 — a escolha feita via PUT
        /alimentacao/alimentos/{id}/estoque-preferido aparece no relatório."""
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Núcleo proteico")
            s.add(a)
            s.commit()
            s.refresh(a)
            e_a = Estoque(nome="Núcleo proteico - Fornecedor A", quantidade=100.0, alimento_id=a.id)
            e_b = Estoque(nome="Núcleo proteico - Fornecedor B", quantidade=200.0, alimento_id=a.id)
            s.add(e_a)
            s.add(e_b)
            s.commit()
            s.refresh(e_b)
            estoque_preferido_id = e_b.id
            a.estoque_preferido_id = estoque_preferido_id
            s.add(a)
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = r.json()["desmembramentos"]
        assert len(linhas) == 1
        assert linhas[0]["estoque_preferido_id"] == estoque_preferido_id

    def test_alimento_com_um_unico_produto_nao_entra(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Ureia")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="Ureia", quantidade=50.0, alimento_id=a.id))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        assert r.json()["desmembramentos"] == []


class TestDivergenciaNome:
    def test_nomes_diferentes_conta_laudos_pelo_nome_atual(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Silagem de Milho")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="SILAGEM MILHO SILO 2", quantidade=100.0, alimento_id=a.id))
            s.add(AnaliseBromatologica(data=date(2026, 1, 1), alimento="Silagem de Milho"))
            s.add(AnaliseBromatologica(data=date(2026, 2, 1), alimento="Silagem de Milho"))
            s.add(AnaliseBromatologica(data=date(2026, 3, 1), alimento="Nome antigo qualquer"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = r.json()["divergencia_nome"]
        assert len(linhas) == 1
        assert linhas[0]["alimento_nome"] == "Silagem de Milho"
        assert linhas[0]["estoque_nome"] == "SILAGEM MILHO SILO 2"
        assert linhas[0]["quantidade_laudos_pelo_nome_atual"] == 2
        assert linhas[0]["quantidade_laudos_pelo_id"] == 0  # Fase P1 — nenhum laudo ligado por id ainda

    def test_quantidade_laudos_pelo_id_reflete_o_vinculo_da_fase_p1(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Silagem de Milho")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="SILAGEM MILHO SILO 2", quantidade=100.0, alimento_id=a.id))
            # Um laudo ligado por id (imune a rename) e outro só por nome.
            s.add(AnaliseBromatologica(data=date(2026, 1, 1), alimento="Silagem de Milho", alimento_id=a.id))
            s.add(AnaliseBromatologica(data=date(2026, 2, 1), alimento="Silagem de Milho"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = r.json()["divergencia_nome"]
        assert len(linhas) == 1
        assert linhas[0]["quantidade_laudos_pelo_nome_atual"] == 2
        assert linhas[0]["quantidade_laudos_pelo_id"] == 1

    def test_nomes_iguais_nao_entra(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Sal mineral")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="Sal mineral", quantidade=20.0, alimento_id=a.id))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        assert r.json()["divergencia_nome"] == []


class TestIngredientesNaoResolviveis:
    def test_sem_candidato_algum_e_ambiguo_aparecem_resolve_um_nao(self, client):
        c, engine = client
        with Session(engine) as s:
            # Resolve por nome exato — não deve aparecer no relatório.
            s.add(Estoque(nome="Silagem de milho", quantidade=100.0))
            s.add(Dieta(lote=1, ingrediente="Silagem de milho", quantidade=10.0, unidade="kg"))
            # Sem nenhum candidato.
            s.add(Dieta(lote=1, ingrediente="Ingrediente fantasma", quantidade=5.0, unidade="kg"))
            # Ambíguo: dois itens de Estoque vinculados ao mesmo Alimento.
            a = Alimento(nome="Núcleo proteico")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Dieta(lote=1, ingrediente="Núcleo proteico", quantidade=3.0, unidade="kg"))
            s.add(Estoque(nome="Núcleo proteico A", quantidade=10.0, alimento_id=a.id))
            s.add(Estoque(nome="Núcleo proteico B", quantidade=20.0, alimento_id=a.id))
            s.commit()

        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        linhas = {l["ingrediente"]: l for l in r.json()["ingredientes_nao_resolviveis"]}
        assert "Silagem de milho" not in linhas
        assert linhas["Ingrediente fantasma"]["classificacao"] == "resolve_0"
        assert linhas["Ingrediente fantasma"]["candidatos"] == []
        assert linhas["Núcleo proteico"]["classificacao"] == "ambiguo"
        assert len(linhas["Núcleo proteico"]["candidatos"]) == 2

    def test_todos_ingredientes_resolvem_relatorio_vazio(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Silagem de milho", quantidade=100.0))
            s.add(Dieta(lote=1, ingrediente="Silagem de milho", quantidade=10.0, unidade="kg"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        assert r.json()["ingredientes_nao_resolviveis"] == []


class TestRmca:
    def test_tres_listas_por_criterio(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Só conta", quantidade=1.0, conta_gerencial_despesa_padrao="3.01.01.02"))
            s.add(Estoque(nome="Só finalidade", quantidade=1.0, finalidade="Ração/Alimento"))
            s.add(Estoque(
                nome="Ambas", quantidade=1.0, finalidade="Ração/Alimento",
                conta_gerencial_despesa_padrao="3.01.01.03",
            ))
            s.add(Estoque(nome="Nenhuma", quantidade=1.0, conta_gerencial_despesa_padrao="3.02.01.01"))
            # O caso que motivou o refactor: "Nutrição" NÃO está em
            # FINALIDADES_ESTOQUE, foi criada à mão no cadastro livre de
            # finalidade. Se a elegibilidade for testada pelo literal
            # "Ração/Alimento", este item — que é o "Caroço de Algodão" da vida
            # real — some da seção de RMCA sem nenhum aviso.
            s.add(Estoque(nome="Finalidade criada à mão", quantidade=1.0, finalidade="Nutrição"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        rmca = r.json()["rmca"]
        assert {i["nome"] for i in rmca["so_pela_conta"]} == {"Só conta"}
        assert {i["nome"] for i in rmca["so_pela_finalidade"]} == {"Só finalidade", "Finalidade criada à mão"}
        assert {i["nome"] for i in rmca["por_ambas"]} == {"Ambas"}

    def test_sem_itens_elegiveis_listas_vazias(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Material qualquer", quantidade=1.0, conta_gerencial_despesa_padrao="5.01.01"))
            s.commit()
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        rmca = r.json()["rmca"]
        assert rmca == {"so_pela_conta": [], "so_pela_finalidade": [], "por_ambas": []}


class TestIsolamentoFazenda:
    def test_relatorio_so_mostra_dados_da_propria_fazenda(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        with Session(engine) as s:
            s.add(Estoque(nome="Fantasma fazenda 1", quantidade=0, fazenda_id=1))
            s.add(Estoque(nome="Fantasma fazenda 2", quantidade=0, fazenda_id=2))
            s.commit()

        r1 = _client(1).get("/alimentacao/migracao/relatorio")
        r2 = _client(2).get("/alimentacao/migracao/relatorio")
        assert r1.status_code == 200 and r2.status_code == 200
        nomes1 = {l["nome"] for l in r1.json()["fantasmas_importacao"]}
        nomes2 = {l["nome"] for l in r2.json()["fantasmas_importacao"]}
        assert nomes1 == {"Fantasma fazenda 1"}
        assert nomes2 == {"Fantasma fazenda 2"}


class TestSomenteLeitura:
    def test_endpoint_nao_altera_nenhuma_tabela(self, client):
        c, engine = client
        with Session(engine) as s:
            a = Alimento(nome="Silagem de Milho")
            s.add(a)
            s.commit()
            s.refresh(a)
            s.add(Estoque(nome="Fantasma", quantidade=0, finalidade=None, alimento_id=None))
            s.add(Estoque(nome="Silagem diferente", quantidade=50.0, alimento_id=a.id))
            s.add(Estoque(nome="Ponte parada", quantidade=10.0, finalidade="Ração/Alimento", alimento_id=a.id))
            s.add(Dieta(lote=1, ingrediente="Ingrediente qualquer", quantidade=1.0, unidade="kg"))
            s.add(CurvaABC(produto="Fantasma"))
            s.add(Sanidade(numero_matriz="1", produto="Fantasma"))
            s.add(LancamentoItem(numero_lancamento="LC-1", produto="Fantasma", valor_total=10.0))
            s.add(AnaliseBromatologica(data=date(2026, 1, 1), alimento="Silagem de Milho"))
            s.commit()

        antes = _contagens(engine)
        r = c.get("/alimentacao/migracao/relatorio")
        assert r.status_code == 200
        # O relatório precisa ter algo em pelo menos uma seção (senão o teste
        # não estaria exercitando nenhum caminho de leitura de verdade).
        corpo = r.json()
        assert any(corpo[secao] for secao in (
            "fantasmas_importacao", "fantasmas_ponte", "desmembramentos", "divergencia_nome",
            "ingredientes_nao_resolviveis",
        ))
        depois = _contagens(engine)
        assert antes == depois
