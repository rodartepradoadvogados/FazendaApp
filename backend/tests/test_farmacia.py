"""
Farmácia — hierarquia por princípio ativo, unificação de volumes, mínimo por
apresentações, compatibilização sem perda e o gatilho de comunicação (baixa só
após estoque inicial/compra) + o menu "qual frasco?".
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, IndicacaoTerapeutica, MedicamentoComercial, MovimentoEstoque, PrincipioAtivo, Sanidade
from fazenda.rules.farmacia import compatibilizar_estoque, resumo_principios, seed_farmacia


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


class TestSeedCompatibilizacao:
    def test_seed_cria_principios_e_marcas(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            principios = s.exec(select(PrincipioAtivo)).all()
            marcas = s.exec(select(MedicamentoComercial)).all()
        nomes = {p.nome for p in principios}
        assert "Meloxicam" in nomes and "Ivermectina" in nomes
        assert any(p.eh_biologico and p.nome.startswith("Clostridioses") for p in principios)
        # Marcas viram tabela filha do princípio.
        assert any(m.nome_comercial == "Maxicam 2%" and m.laboratorio == "Ourofino" for m in marcas)

    def test_seed_idempotente_nao_duplica(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            n1 = len(s.exec(select(PrincipioAtivo)).all())
            m1 = len(s.exec(select(MedicamentoComercial)).all())
            seed_farmacia(s)
            assert len(s.exec(select(PrincipioAtivo)).all()) == n1
            assert len(s.exec(select(MedicamentoComercial)).all()) == m1

    def test_compatibiliza_por_marca_e_por_texto_sem_perda(self, client):
        c, engine = client
        with Session(engine) as s:
            # item vinculado pela MARCA no nome
            s.add(Estoque(nome="Maxicam 2% frasco", quantidade=50.0, unidade="ml"))
            # item vinculado pelo TEXTO do princípio
            s.add(Estoque(nome="Ivermectina genérica", principio_ativo="Ivermectina", quantidade=100.0, unidade="ml"))
            # item com princípio fora do catálogo → cria e vincula
            s.add(Estoque(nome="Remédio X", principio_ativo="Molécula Inédita", quantidade=10.0, unidade="ml"))
            s.commit()
            seed_farmacia(s)
            res = compatibilizar_estoque(s)
            assert res["vinculados"] == 3
            assert res["criados"] == 1
            maxicam = s.exec(select(Estoque).where(Estoque.nome == "Maxicam 2% frasco")).first()
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            assert maxicam.principio_ativo_id == melox.id
            assert maxicam.medicamento_comercial_id is not None  # casou a marca
            assert s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Molécula Inédita")).first() is not None


class TestUnificacaoMinimo:
    def test_soma_volumes_e_minimo_por_apresentacoes(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            # frasco de 50ml com 40ml (0,8) + frasco de 250ml com 125ml (0,5) = 1,3 apres
            s.add(Estoque(nome="Maxicam 50", principio_ativo_id=melox.id, quantidade=40.0, unidade="ml",
                          volume_por_apresentacao=50.0, volume_unidade="ml"))
            s.add(Estoque(nome="Aliv V 250", principio_ativo_id=melox.id, quantidade=125.0, unidade="ml",
                          volume_por_apresentacao=250.0, volume_unidade="ml"))
            s.commit()
        r = c.get("/farmacia/principios")
        assert r.status_code == 200
        melox_res = next(p for p in r.json() if p["nome"] == "Meloxicam")
        assert melox_res["total_base"] == 165.0  # 40 + 125 ml
        assert melox_res["total_apresentacoes"] == 1.3
        assert melox_res["abaixo_minimo"] is False  # 1,3 >= 1

    def test_abaixo_do_minimo_quando_menos_de_uma_apresentacao(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            s.add(Estoque(nome="Maxicam 50 quase vazio", principio_ativo_id=melox.id, quantidade=20.0, unidade="ml",
                          volume_por_apresentacao=50.0, volume_unidade="ml"))  # 0,4 apres
            s.commit()
        melox_res = next(p for p in c.get("/farmacia/principios").json() if p["nome"] == "Meloxicam")
        assert melox_res["abaixo_minimo"] is True

    def test_converte_litros_e_ml_no_mesmo_principio(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            amitraz = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Amitraz")).first()  # base L
            s.add(Estoque(nome="Triatox 1L", principio_ativo_id=amitraz.id, quantidade=1.0, unidade="L"))
            s.add(Estoque(nome="Amitraz 500ml", principio_ativo_id=amitraz.id, quantidade=500.0, unidade="ml"))
            s.commit()
        res = next(p for p in c.get("/farmacia/principios").json() if p["nome"] == "Amitraz")
        assert res["total_base"] == 1.5  # 1 L + 0,5 L


class TestGatilhoQualFrasco:
    def _principio_com_dois_frascos(self, engine):
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            a = Estoque(nome="Maxicam 50", principio_ativo_id=melox.id, quantidade=50.0, unidade="ml",
                        volume_por_apresentacao=50.0, volume_unidade="ml", estoque_inicializado=True)
            b = Estoque(nome="Aliv V 250", principio_ativo_id=melox.id, quantidade=250.0, unidade="ml",
                        volume_por_apresentacao=250.0, volume_unidade="ml", estoque_inicializado=True)
            s.add(a); s.add(b)
            s.commit()
            return melox.id, a.id, b.id

    def test_apresentacoes_lista_frascos_do_principio(self, client):
        c, engine = client
        pa_id, a_id, b_id = self._principio_com_dois_frascos(engine)
        r = c.get("/farmacia/apresentacoes", params={"principio_ativo_id": pa_id})
        assert r.status_code == 200
        nomes = {x["nome"] for x in r.json()}
        assert nomes == {"Maxicam 50", "Aliv V 250"}

    def test_qual_frasco_abate_do_recipiente_escolhido(self, client):
        c, engine = client
        pa_id, a_id, b_id = self._principio_com_dois_frascos(engine)
        # Aplica 10ml escolhendo o frasco B (Aliv V 250) em 1 animal.
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": date.today().isoformat(), "animais": ["1"],
            "itens": [{"produto": "Aliv V 250", "quantidade": 10.0, "unidade": "ml", "estoque_id": b_id}],
        })
        assert r.status_code == 200
        with Session(engine) as s:
            assert s.get(Estoque, a_id).quantidade == 50.0    # frasco A intacto
            assert s.get(Estoque, b_id).quantidade == 240.0   # abateu do B

    def test_gatilho_sem_estoque_inicial_nao_baixa(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            item = Estoque(nome="Maxicam novo", principio_ativo_id=melox.id, quantidade=0.0, unidade="ml",
                           estoque_inicializado=False)
            s.add(item); s.commit(); item_id = item.id
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": date.today().isoformat(), "animais": ["1"],
            "itens": [{"produto": "Maxicam novo", "quantidade": 5.0, "unidade": "ml", "estoque_id": item_id}],
        })
        assert r.status_code == 200
        assert any("sem baixa" in a for a in r.json()["avisos"])
        with Session(engine) as s:
            assert s.get(Estoque, item_id).quantidade == 0.0  # não baixou
            # a aplicação foi registrada mesmo assim
            assert s.exec(select(Sanidade).where(Sanidade.produto == "Maxicam novo")).first() is not None

    def test_inicializar_liga_gatilho_e_baixa_passa_a_valer(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            melox = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Meloxicam")).first()
            item = Estoque(nome="Maxicam novo", principio_ativo_id=melox.id, quantidade=0.0, unidade="ml",
                           estoque_inicializado=False)
            s.add(item); s.commit(); item_id = item.id
        # Registra estoque inicial → liga o gatilho.
        r = c.post(f"/farmacia/estoque/{item_id}/inicializar", json={"quantidade": 100.0})
        assert r.status_code == 200 and r.json()["estoque_inicializado"] is True
        # Agora a aplicação baixa.
        c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": date.today().isoformat(), "animais": ["1"],
            "itens": [{"produto": "Maxicam novo", "quantidade": 10.0, "unidade": "ml", "estoque_id": item_id}],
        })
        with Session(engine) as s:
            assert s.get(Estoque, item_id).quantidade == 90.0
            assert s.exec(select(MovimentoEstoque).where(MovimentoEstoque.movimento == "Estoque inicial")).first() is not None


def test_bootstrap_popula_catalogo_completo_idempotente():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select
    from fazenda.models import PrincipioAtivo, MedicamentoComercial
    from fazenda.rules.farmacia import bootstrap_farmacia
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        bootstrap_farmacia(s)
        bootstrap_farmacia(s)  # roda de novo: não pode duplicar
        pas = s.exec(select(PrincipioAtivo)).all()
        marcas = s.exec(select(MedicamentoComercial)).all()
        assert len(pas) == 51
        assert all(p.categoria_software for p in pas)   # todas com característica
        assert len(marcas) == 122
        mel = next(p for p in pas if p.nome == "Meloxicam")
        assert mel.categoria_software == "AINE" and mel.uso_principal


def test_backfill_finalidade_marca_medicamento_legado_sem_sobrescrever():
    """Item legado com sinal de medicamento (classificação/princípio) e sem
    `finalidade` ainda definida ganha "Medicamento" automaticamente — mas um
    valor já definido no cadastro (mesmo que "Outro") nunca é sobrescrito."""
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select
    from fazenda.rules.farmacia import bootstrap_farmacia

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Estoque(nome="Terramicina Legado", quantidade=10, unidade="ml", classificacao_medicamento="Antibiótico"))
        s.add(Estoque(nome="Ração Milho Legado", quantidade=500, unidade="kg"))
        s.add(Estoque(nome="Equipamento Já Classificado", quantidade=1, unidade="unidade", finalidade="Outro"))
        s.commit()
        bootstrap_farmacia(s)
        terramicina = s.exec(select(Estoque).where(Estoque.nome == "Terramicina Legado")).first()
        racao = s.exec(select(Estoque).where(Estoque.nome == "Ração Milho Legado")).first()
        equipamento = s.exec(select(Estoque).where(Estoque.nome == "Equipamento Já Classificado")).first()
        assert terramicina.finalidade == "Medicamento"
        assert racao.finalidade is None  # sem sinal de medicamento — fica sem classificar
        assert equipamento.finalidade == "Outro"  # já definido, não é sobrescrito


def test_normalizar_unidades_estoque_corrige_abreviacao_legada():
    """Item cadastrado/importado com unidade abreviada ("un") ficava fora do
    grupo de unidades compatíveis e escondia "ml" no seletor de dose — o
    backfill corrige para a forma canônica "unidade", sem mexer em itens já corretos."""
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select
    from fazenda.rules.farmacia import bootstrap_farmacia

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Estoque(nome="VACINA RB 51", quantidade=10, unidade="un"))
        s.add(Estoque(nome="Borgal 50ml", quantidade=10, unidade="ml"))
        s.commit()
        bootstrap_farmacia(s)
        vacina = s.exec(select(Estoque).where(Estoque.nome == "VACINA RB 51")).first()
        borgal = s.exec(select(Estoque).where(Estoque.nome == "Borgal 50ml")).first()
        assert vacina.unidade == "unidade"
        assert borgal.unidade == "ml"


class TestUnidadesCompativeis:
    def test_sinonimo_un_cai_no_grupo_de_unidade(self):
        from fazenda.rules.unidades import unidades_compativeis
        assert "ml" in unidades_compativeis("un")
        assert set(unidades_compativeis("un")) == set(unidades_compativeis("unidade"))


class TestIndicacoesTerapeuticas:
    """Substituto inteligente: vínculo N-para-N princípio ativo ↔ doença com
    prioridade, e o ranking com estoque ao vivo que alimenta a consulta
    "Remédios por doença" e o banner de substituto no lançamento."""

    def _cenario_mastite(self, engine):
        """Doença Mastite clínica com 3 opções: Ceftiofur (estoque ok),
        Cefquinoma (abaixo do mínimo) e Amoxicilina (sem estoque)."""
        from fazenda.models import Doenca

        with Session(engine) as s:
            doenca = Doenca(nome="Mastite clínica")
            s.add(doenca); s.commit(); s.refresh(doenca)

            ceftiofur = PrincipioAtivo(nome="Ceftiofur", categoria_software="Antibiótico sistêmico",
                                        unidade_base="ml", unidade_apresentacao="frasco", estoque_minimo_apresentacoes=1.0)
            cefquinoma = PrincipioAtivo(nome="Cefquinoma", categoria_software="Antibiótico sistêmico",
                                         unidade_base="ml", unidade_apresentacao="frasco", estoque_minimo_apresentacoes=2.0)
            amoxicilina = PrincipioAtivo(nome="Amoxicilina + Clavulanato", categoria_software="Antibiótico sistêmico",
                                          unidade_base="ml", unidade_apresentacao="frasco")
            s.add(ceftiofur); s.add(cefquinoma); s.add(amoxicilina); s.commit()
            s.refresh(ceftiofur); s.refresh(cefquinoma); s.refresh(amoxicilina)

            # Ceftiofur: 4 frascos de 100ml cheios → bem acima do mínimo.
            s.add(Estoque(nome="Excenel", laboratorio="Zoetis", principio_ativo_id=ceftiofur.id,
                          quantidade=400.0, unidade="ml", volume_por_apresentacao=100.0, volume_unidade="ml",
                          estoque_inicializado=True))
            # Cefquinoma: 1 frasco de 100ml, mínimo é 2 → abaixo do mínimo.
            s.add(Estoque(nome="Cobactan", laboratorio="MSD", principio_ativo_id=cefquinoma.id,
                          quantidade=100.0, unidade="ml", volume_por_apresentacao=100.0, volume_unidade="ml",
                          estoque_inicializado=True))
            # Amoxicilina: sem nenhum item de estoque vinculado → "out".
            s.commit()

            s.add(IndicacaoTerapeutica(principio_ativo_id=ceftiofur.id, doenca_id=doenca.id, prioridade=1))
            s.add(IndicacaoTerapeutica(principio_ativo_id=cefquinoma.id, doenca_id=doenca.id, prioridade=2))
            s.add(IndicacaoTerapeutica(principio_ativo_id=amoxicilina.id, doenca_id=doenca.id, prioridade=3))
            s.commit()
            return {"doenca_id": doenca.id, "ceftiofur_id": ceftiofur.id, "cefquinoma_id": cefquinoma.id,
                    "amoxicilina_id": amoxicilina.id}

    def test_ranking_por_doenca_traz_status_de_estoque_correto(self, client):
        c, engine = client
        ids = self._cenario_mastite(engine)
        r = c.get(f"/sanidade/indicacoes-doenca/{ids['doenca_id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["doenca"] == "Mastite clínica"
        opcoes = body["opcoes"]
        assert [o["principio_ativo_id"] for o in opcoes] == [ids["ceftiofur_id"], ids["cefquinoma_id"], ids["amoxicilina_id"]]
        assert opcoes[0]["status_estoque"] == "ok" and opcoes[0]["marcas"] == ["Zoetis"]
        assert opcoes[1]["status_estoque"] == "low"
        assert opcoes[2]["status_estoque"] == "out" and opcoes[2]["marcas"] == []

    def test_doenca_inexistente_da_404(self, client):
        c, engine = client
        r = c.get("/sanidade/indicacoes-doenca/999999")
        assert r.status_code == 404

    def test_doenca_sem_indicacao_traz_lista_vazia(self, client):
        from fazenda.models import Doenca
        c, engine = client
        with Session(engine) as s:
            s.add(Doenca(nome="Doença sem tratamento cadastrado")); s.commit()
            doenca_id = s.exec(select(Doenca).where(Doenca.nome == "Doença sem tratamento cadastrado")).first().id
        r = c.get(f"/sanidade/indicacoes-doenca/{doenca_id}")
        assert r.status_code == 200 and r.json()["opcoes"] == []

    def test_crud_indicacao(self, client):
        from fazenda.models import Doenca
        c, engine = client
        with Session(engine) as s:
            doenca = Doenca(nome="Pneumonia"); s.add(doenca)
            pa = PrincipioAtivo(nome="Tulatromicina"); s.add(pa)
            s.commit(); s.refresh(doenca); s.refresh(pa)
            doenca_id, pa_id = doenca.id, pa.id

        assert c.get("/farmacia/indicacoes", params={"principio_ativo_id": pa_id}).json() == []

        r = c.post("/farmacia/indicacoes", json={"principio_ativo_id": pa_id, "doenca_id": doenca_id, "prioridade": 1})
        assert r.status_code == 201
        criada = r.json()
        assert criada["doenca"] == "Pneumonia" and criada["prioridade"] == 1

        listada = c.get("/farmacia/indicacoes", params={"principio_ativo_id": pa_id}).json()
        assert len(listada) == 1 and listada[0]["id"] == criada["id"]

        # Duplicata (mesmo princípio + doença) é bloqueada.
        dup = c.post("/farmacia/indicacoes", json={"principio_ativo_id": pa_id, "doenca_id": doenca_id, "prioridade": 2})
        assert dup.status_code == 409

        excluir = c.delete(f"/farmacia/indicacoes/{criada['id']}")
        assert excluir.status_code == 200
        assert c.get("/farmacia/indicacoes", params={"principio_ativo_id": pa_id}).json() == []

    def test_criar_indicacao_com_principio_ou_doenca_inexistente_da_400(self, client):
        from fazenda.models import Doenca
        c, engine = client
        with Session(engine) as s:
            doenca = Doenca(nome="Verminose"); s.add(doenca)
            pa = PrincipioAtivo(nome="Ivermectina 1%"); s.add(pa)
            s.commit(); s.refresh(doenca); s.refresh(pa)
            doenca_id, pa_id = doenca.id, pa.id

        assert c.post("/farmacia/indicacoes", json={"principio_ativo_id": 999999, "doenca_id": doenca_id}).status_code == 400
        assert c.post("/farmacia/indicacoes", json={"principio_ativo_id": pa_id, "doenca_id": 999999}).status_code == 400

    def test_excluir_indicacao_inexistente_da_404(self, client):
        c, engine = client
        assert c.delete("/farmacia/indicacoes/999999").status_code == 404


class TestSomatotropinaBST:
    """bST (Lactotropin/Boostin) no catálogo da farmácia.

    Os dois itens de estoque nasceram antes de o princípio existir no
    catálogo, então ficaram com `principio_ativo_id` nulo — e quem faria o
    vínculo por nome de marca (`compatibilizar_estoque`) é guardada por
    SeedFlag e já rodou nos bancos em produção. Daí o backfill dirigido
    `vincular_bst_ao_principio`, que roda em todo start.
    """

    def test_seed_cria_o_principio_com_as_duas_marcas(self, client):
        from fazenda.rules.farmacia import NOME_PRINCIPIO_BST
        c, engine = client
        with Session(engine) as s:
            seed_farmacia(s)
            pa = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == NOME_PRINCIPIO_BST)).first()
            assert pa is not None, "princípio de bST não foi semeado"
            assert pa.categoria_software == "Hormônio Galactopoiético"
            assert pa.unidade_base == "dose"
            marcas = {m.nome_comercial for m in s.exec(
                select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == pa.id)
            ).all()}
            assert marcas == {"Lactotropin", "Boostin"}

    def test_vincula_item_de_estoque_legado_sem_principio(self, client):
        from fazenda.rules.farmacia import NOME_PRINCIPIO_BST, seed_boostin, vincular_bst_ao_principio
        c, engine = client
        with Session(engine) as s:
            # Estado do banco em produção: Lactotropin já cadastrado, sem princípio.
            s.add(Estoque(nome="Lactotropin", unidade="unidade", quantidade=5, principio_ativo_id=None))
            s.commit()
            seed_farmacia(s)
            seed_boostin(s)
            vincular_bst_ao_principio(s)

            pa = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == NOME_PRINCIPIO_BST)).one()
            for nome in ("Lactotropin", "Boostin"):
                item = s.exec(select(Estoque).where(Estoque.nome == nome)).one()
                assert item.principio_ativo_id == pa.id, f"{nome} continuou sem princípio"
                assert item.principio_ativo == NOME_PRINCIPIO_BST

    def test_nao_sobrescreve_vinculo_feito_pelo_usuario(self, client):
        from fazenda.rules.farmacia import vincular_bst_ao_principio
        c, engine = client
        with Session(engine) as s:
            outro = PrincipioAtivo(nome="Outro princípio escolhido à mão")
            s.add(outro); s.commit(); s.refresh(outro)
            s.add(Estoque(nome="Lactotropin", unidade="unidade", principio_ativo_id=outro.id))
            s.commit()
            seed_farmacia(s)
            vincular_bst_ao_principio(s)

            item = s.exec(select(Estoque).where(Estoque.nome == "Lactotropin")).one()
            assert item.principio_ativo_id == outro.id, "backfill não pode sobrescrever escolha do usuário"

    def test_e_idempotente(self, client):
        from fazenda.rules.farmacia import NOME_PRINCIPIO_BST, vincular_bst_ao_principio
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Lactotropin", unidade="unidade", principio_ativo_id=None))
            s.commit()
            for _ in range(3):
                seed_farmacia(s)
                vincular_bst_ao_principio(s)
            principios = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == NOME_PRINCIPIO_BST)).all()
            assert len(principios) == 1
            marcas = s.exec(select(MedicamentoComercial).where(
                MedicamentoComercial.principio_ativo_id == principios[0].id
            )).all()
            assert len(marcas) == 2

    def test_corrige_grafia_lactotropim_e_vincula(self, client):
        # "Lactotropim" (com M) é erro de digitação comum; o produto da Elanco
        # é Lactotropin. O item mal grafado tem que ser corrigido E vinculado,
        # senão fica fora do seletor de frasco por causa de uma letra.
        from fazenda.rules.farmacia import NOME_PRINCIPIO_BST, vincular_bst_ao_principio
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Lactotropim", unidade="unidade", quantidade=3, principio_ativo_id=None))
            s.commit()
            seed_farmacia(s)
            vincular_bst_ao_principio(s)

            pa = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == NOME_PRINCIPIO_BST)).one()
            assert s.exec(select(Estoque).where(Estoque.nome == "Lactotropim")).first() is None
            item = s.exec(select(Estoque).where(Estoque.nome == "Lactotropin")).one()
            assert item.principio_ativo_id == pa.id
            assert item.quantidade == 3, "corrigir a grafia não pode mexer no saldo"


class TestLinkBulaValidacao:
    """Achado P3 #3 da auditoria de segurança: link_bula vira <a href> no
    frontend — um esquema como javascript: executaria no clique."""

    def test_rejeita_esquema_nao_http(self, client):
        c, engine = client
        r = c.post("/farmacia/principios", json={"nome": "Princípio Link"})
        assert r.status_code == 201
        principio_id = r.json()["id"]

        r = c.post("/farmacia/medicamentos", json={
            "principio_ativo_id": principio_id, "nome_comercial": "Marca Link",
            "link_bula": "javascript:alert(document.cookie)",
        })
        assert r.status_code == 422

    def test_aceita_link_https(self, client):
        c, engine = client
        r = c.post("/farmacia/principios", json={"nome": "Princípio Link 2"})
        principio_id = r.json()["id"]

        r = c.post("/farmacia/medicamentos", json={
            "principio_ativo_id": principio_id, "nome_comercial": "Marca Link 2",
            "link_bula": "https://bula.exemplo.com.br/marca-link-2",
        })
        assert r.status_code == 201
        assert r.json()["link_bula"] == "https://bula.exemplo.com.br/marca-link-2"
