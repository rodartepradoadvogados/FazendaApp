"""Testes de compra de sêmen (Lançamentos > Compra/Venda > Comprar sêmen) —
efeito financeiro + soma de doses ao estoque de sêmen (existente ou novo, via
NAAB), incluindo compras com múltiplos touros/sêmens na mesma nota fiscal."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import CompraSemen, ContaGerencial, Estoque, EstoqueSemen, MovimentoEstoque, Touro


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, exigir_admin

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


def _criar_estoque_semen(engine, **kwargs) -> int:
    with Session(engine) as s:
        campos = dict(touro_nome="Touro da Fazenda", doses=10, tipo="convencional")
        campos.update(kwargs)
        item = EstoqueSemen(**campos)
        s.add(item)
        s.commit()
        s.refresh(item)
        return item.id


def _criar_touro_naab(engine, naab="7HO12345", nome="Supersire") -> None:
    with Session(engine) as s:
        s.add(Touro(naab=naab, nome=nome, central="ABS"))
        s.commit()


class TestRegistrarCompraSemen:
    def test_compra_de_touro_ja_em_estoque_soma_doses(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 50.0, "tipo_valor": "por_dose", "doses": 20}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["doses_compradas"] == 20
        assert corpo["estoque_semen_ids"] == [estoque_id]

        with Session(client.engine) as s:
            estoque = s.get(EstoqueSemen, estoque_id)
            assert estoque.doses == 30  # 10 iniciais + 20 compradas
            assert estoque.valor_unitario == 50.0

            conta = s.exec(select(ContaGerencial).where(ContaGerencial.codigo_conta == "3.01.02.01")).first()
            assert conta is not None
            assert conta.tipo == "despesa"
            assert conta.valor_total == 1000.0  # 20 x 50
            assert conta.valor_unitario == 50.0  # único item — resumo preenchido

            registro = s.exec(select(CompraSemen)).first()
            assert registro.origem == "estoque"
            assert registro.doses == 20
            assert registro.estoque_semen_id == estoque_id

    def test_compra_grava_movimento_de_estoque_entrada_de_compra(self, client):
        # Regressão: a compra somava doses certinho em EstoqueSemen (e a
        # aplicação na inseminação já baixava e registrava normalmente), mas
        # a ENTRADA em si nunca deixava rastro em MovimentoEstoque — sumia do
        # Mapa de entradas do Estoque mesmo com o saldo correto.
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 50.0, "tipo_valor": "por_dose", "doses": 20}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200

        with Session(client.engine) as s:
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "compra_semen")).first()
            assert mov is not None
            assert mov.movimento == "Entrada de compra"
            assert mov.quantidade == 20
            assert mov.unidade == "dose"
            assert mov.nome_item == "Touro da Fazenda"

            item_espelho = s.exec(select(Estoque).where(Estoque.estoque_semen_id == estoque_id)).first()
            assert item_espelho is not None
            assert mov.estoque_id == item_espelho.id

    def test_compra_valor_total_calcula_valor_por_dose(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        client.post("/compras-semen/", json={
            "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 900.0, "tipo_valor": "total", "doses": 18}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        with Session(client.engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.codigo_conta == "3.01.02.01")).first()
            assert conta.valor_unitario == 50.0
            assert conta.valor_total == 900.0

    def test_compra_de_touro_naab_novo_cria_linha_de_estoque(self, client):
        _criar_touro_naab(client.engine)
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "naab", "naab": "7HO12345", "touro_nome": "Supersire", "valor": 80.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "ABS Brasil", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200
        with Session(client.engine) as s:
            estoque = s.exec(select(EstoqueSemen).where(EstoqueSemen.naab == "7HO12345")).first()
            assert estoque is not None
            assert estoque.doses == 10
            assert estoque.touro_nome == "Supersire"
            assert estoque.central == "ABS"

    def test_compra_de_touro_naab_ja_no_estoque_soma_doses_sem_duplicar(self, client):
        _criar_touro_naab(client.engine)
        estoque_id = _criar_estoque_semen(client.engine, naab="7HO12345")
        client.post("/compras-semen/", json={
            "itens": [{"origem": "naab", "naab": "7HO12345", "touro_nome": "Supersire", "valor": 80.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "ABS Brasil", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        with Session(client.engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.naab == "7HO12345")).all()
            assert len(linhas) == 1
            assert linhas[0].id == estoque_id
            assert linhas[0].doses == 20

    def test_compra_naab_de_touro_ja_cadastrado_so_pelo_nome_sem_duplicar(self, client):
        """Regressão (Henessy/Heineken/Halle, relato do produtor ago/2026):
        touro já cadastrado no Estoque de Sêmen, mas SEM o NAAB preenchido
        (cadastro manual/CSV antigo) — comprar pelo catálogo NAAB precisa
        casar pelo NOME em vez de criar uma 2ª linha duplicada."""
        _criar_touro_naab(client.engine)
        estoque_id = _criar_estoque_semen(client.engine, touro_nome="Supersire", naab=None)
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "naab", "naab": "7HO12345", "touro_nome": "Supersire", "valor": 80.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "ABS Brasil", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200
        with Session(client.engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.touro_nome == "Supersire")).all()
            assert len(linhas) == 1  # não duplicou
            assert linhas[0].id == estoque_id
            assert linhas[0].doses == 20  # 10 iniciais + 10 compradas
            assert linhas[0].naab == "7HO12345"  # NAAB completado, sem sobrescrever a linha

    def test_compra_exige_conta_gerencial_de_semen(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 50.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.10.06",
        })
        assert r.status_code == 400

    def test_compra_naab_inexistente_da_404(self, client):
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "naab", "naab": "NAOEXISTE", "touro_nome": "Fantasma", "valor": 80.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "ABS Brasil", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 404

    def test_compra_exige_doses_positivas(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 50.0, "tipo_valor": "por_dose", "doses": 0}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 400

    def test_compra_exige_ao_menos_um_item(self, client):
        r = client.post("/compras-semen/", json={
            "itens": [], "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 400

    def test_lista_compras_registradas(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        client.post("/compras-semen/", json={
            "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 50.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        r = client.get("/compras-semen/")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["doses"] == 10


class TestCompraSemenMultiItem:
    """Vários touros/sêmens na mesma compra — mesma nota fiscal/parcelamento
    (o pedido do usuário: "vincular à mesma nota fiscal, mesmos boletos")."""

    def test_dois_touros_compartilham_numero_lancamento_e_valor_somado(self, client):
        estoque_id_1 = _criar_estoque_semen(client.engine)
        _criar_touro_naab(client.engine, naab="7HO99999", nome="Outro Touro")
        r = client.post("/compras-semen/", json={
            "itens": [
                {"origem": "estoque", "estoque_semen_id": estoque_id_1, "valor": 50.0, "tipo_valor": "por_dose", "doses": 10},
                {"origem": "naab", "naab": "7HO99999", "touro_nome": "Outro Touro", "valor": 700.0, "tipo_valor": "total", "doses": 14},
            ],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["doses_compradas"] == 24
        assert len(corpo["estoque_semen_ids"]) == 2

        with Session(client.engine) as s:
            estoque_1 = s.get(EstoqueSemen, estoque_id_1)
            assert estoque_1.doses == 20  # 10 + 10

            estoque_2 = s.exec(select(EstoqueSemen).where(EstoqueSemen.naab == "7HO99999")).first()
            assert estoque_2.doses == 14
            assert estoque_2.valor_unitario == 50.0  # 700 / 14

            compras = s.exec(select(CompraSemen)).all()
            assert len(compras) == 2
            numeros = {c.numero_lancamento_gerado for c in compras}
            assert len(numeros) == 1  # mesma nota fiscal para os dois itens

            contas = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numeros.pop())).all()
            assert len(contas) == 1  # não parcelado → 1 linha só, valor somado dos 2 itens
            assert contas[0].valor_total == 500.0 + 700.0
            assert contas[0].valor_unitario is None  # 2 itens com valores/dose distintos — sem resumo único
            assert contas[0].quantidade == 24

    def test_multi_item_parcelado_gera_uma_parcela_por_entrada_compartilhada(self, client):
        estoque_id_1 = _criar_estoque_semen(client.engine)
        estoque_id_2 = _criar_estoque_semen(client.engine, touro_nome="Segundo Touro")
        r = client.post("/compras-semen/", json={
            "itens": [
                {"origem": "estoque", "estoque_semen_id": estoque_id_1, "valor": 40.0, "tipo_valor": "por_dose", "doses": 10},
                {"origem": "estoque", "estoque_semen_id": estoque_id_2, "valor": 60.0, "tipo_valor": "por_dose", "doses": 10},
            ],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
            "parcelas": [
                {"data_vencimento": "2026-08-10", "valor": 500.0},
                {"data_vencimento": "2026-09-10", "valor": 500.0},
            ],
        })
        assert r.status_code == 200
        numero_lancamento = r.json()["numero_lancamento"]
        with Session(client.engine) as s:
            contas = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).all()
            assert len(contas) == 2  # 2 parcelas, compartilhadas pelos 2 itens
            assert sum(c.valor_total for c in contas) == 1000.0

    def test_exclusao_de_um_item_nao_apaga_lancamento_compartilhado_com_irmao(self, client):
        estoque_id_1 = _criar_estoque_semen(client.engine)
        estoque_id_2 = _criar_estoque_semen(client.engine, touro_nome="Segundo Touro")
        r = client.post("/compras-semen/", json={
            "itens": [
                {"origem": "estoque", "estoque_semen_id": estoque_id_1, "valor": 40.0, "tipo_valor": "por_dose", "doses": 10},
                {"origem": "estoque", "estoque_semen_id": estoque_id_2, "valor": 60.0, "tipo_valor": "por_dose", "doses": 5},
            ],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        assert r.status_code == 200
        numero_lancamento = r.json()["numero_lancamento"]

        with Session(client.engine) as s:
            compras = s.exec(select(CompraSemen).where(CompraSemen.numero_lancamento_gerado == numero_lancamento)).all()
            compra_do_item_2 = next(c for c in compras if c.estoque_semen_id == estoque_id_2)

        # Prévia de impacto deve avisar que é parte de uma compra com mais itens.
        r_impacto = client.post("/exclusoes/impacto", json={"tipo": "compra_semen", "id": str(compra_do_item_2.id)})
        assert r_impacto.status_code == 200
        assert any("mais 1 sêmen/touro" in linha for linha in r_impacto.json()["impacto"])

        r_confirma = client.post("/exclusoes/confirmar", json={"tipo": "compra_semen", "id": str(compra_do_item_2.id)})
        assert r_confirma.status_code == 200

        with Session(client.engine) as s:
            # O item excluído sumiu e teve suas doses revertidas...
            assert s.get(CompraSemen, compra_do_item_2.id) is None
            estoque_2 = s.get(EstoqueSemen, estoque_id_2)
            assert estoque_2.doses == 10  # 10 iniciais + 5 compradas - 5 revertidas

            # ...mas o item irmão e o lançamento financeiro compartilhado continuam intactos.
            compras_restantes = s.exec(select(CompraSemen).where(CompraSemen.numero_lancamento_gerado == numero_lancamento)).all()
            assert len(compras_restantes) == 1
            assert compras_restantes[0].estoque_semen_id == estoque_id_1

            contas = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).all()
            assert len(contas) == 1

    def test_exclusao_do_ultimo_item_apaga_lancamento_financeiro(self, client):
        estoque_id = _criar_estoque_semen(client.engine)
        r = client.post("/compras-semen/", json={
            "itens": [{"origem": "estoque", "estoque_semen_id": estoque_id, "valor": 50.0, "tipo_valor": "por_dose", "doses": 10}],
            "vendedor": "Central Genética", "data_compra": "2026-07-10", "codigo_conta_gerencial": "3.01.02.01",
        })
        numero_lancamento = r.json()["numero_lancamento"]
        with Session(client.engine) as s:
            compra = s.exec(select(CompraSemen).where(CompraSemen.numero_lancamento_gerado == numero_lancamento)).first()

        r_confirma = client.post("/exclusoes/confirmar", json={"tipo": "compra_semen", "id": str(compra.id)})
        assert r_confirma.status_code == 200
        with Session(client.engine) as s:
            assert s.get(CompraSemen, compra.id) is None
            contas = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).all()
            assert len(contas) == 0
