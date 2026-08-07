"""
FASE 3 — endpoints da aba Farmácia: catálogo de indicações (GET
/farmacia/indicacoes-catalogo) e a trava de personalização (POST/DELETE
.../personalizar), que clona o padrão global para a fazenda poder editar bula
de marca e prioridade/nota do vínculo sem afetar as outras fazendas.

Cobre também a mesma trava de 404 em PUT /medicamentos e PUT /indicacoes para
linha global (não personalizada) e o formato de carência (`carencia_dict`)
devolvido pelo catálogo.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Doenca, Fazenda, IndicacaoTerapeutica, MedicamentoComercial,
    PrincipioAtivo,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

        # Catálogo global (como o seed cria: sem fazenda_id).
        pa = PrincipioAtivo(nome="Ceftiofur", categoria_software="Antimicrobiano", unidade_base="ml")
        s.add(pa)
        s.commit()
        s.refresh(pa)

        doenca = Doenca(nome="Mastite Clínica", tipo="doenca", descricao="Inflamação da glândula mamária")
        s.add(doenca)
        s.commit()
        s.refresh(doenca)

        ind = IndicacaoTerapeutica(principio_ativo_id=pa.id, doenca_id=doenca.id, prioridade=1, nota="1ª escolha")
        s.add(ind)

        marca = MedicamentoComercial(
            principio_ativo_id=pa.id, nome_comercial="Excenel", laboratorio="Zoetis",
            dose_texto="1 mL/50 kg SC", carencia_leite_dias=0, carencia_carne_dias=4,
            proibido_lactacao=False,
        )
        s.add(marca)
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
        permissoes = "sanidade,estoque"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _ids_globais(engine):
    with Session(engine) as s:
        doenca_id = s.exec(select(Doenca).where(Doenca.nome == "Mastite Clínica")).one().id
        pa_id = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Ceftiofur")).one().id
        marca_id = s.exec(select(MedicamentoComercial).where(MedicamentoComercial.nome_comercial == "Excenel")).one().id
    return doenca_id, pa_id, marca_id


class TestCatalogoListaGlobalParaFazenda:
    def test_catalogo_lista_indicacao_global_com_principios_e_marcas(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.get("/farmacia/indicacoes-catalogo")
        assert r.status_code == 200, r.text
        itens = r.json()
        alvo = next(i for i in itens if i["nome"] == "Mastite Clínica")
        assert alvo["personalizada"] is False
        assert alvo["origem_id"] is None
        assert len(alvo["principios"]) == 1
        principio = alvo["principios"][0]
        assert principio["nome"] == "Ceftiofur"
        assert principio["prioridade"] == 1
        assert len(principio["marcas"]) == 1
        marca = principio["marcas"][0]
        assert marca["nome_comercial"] == "Excenel"
        assert marca["editavel"] is False  # linha global é só leitura

    def test_carencia_vem_no_formato_de_carencia_dict(self, client):
        c, engine = client
        _como_fazenda(1)
        itens = c.get("/farmacia/indicacoes-catalogo").json()
        marca = next(i for i in itens if i["nome"] == "Mastite Clínica")["principios"][0]["marcas"][0]
        carencia = marca["carencia"]
        assert "texto" in carencia
        assert carencia["carne_dias"] == 4
        assert carencia["leite_dias"] == 0
        assert carencia["texto"].startswith("Carência:")

    def test_filtro_por_tipo(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.get("/farmacia/indicacoes-catalogo", params={"tipo": "reprodutivo"})
        assert r.json() == []
        r = c.get("/farmacia/indicacoes-catalogo", params={"tipo": "doenca"})
        assert any(i["nome"] == "Mastite Clínica" for i in r.json())

    def test_busca_por_nome_de_marca_sem_acento_e_caixa(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.get("/farmacia/indicacoes-catalogo", params={"busca": "excenel"})
        assert any(i["nome"] == "Mastite Clínica" for i in r.json())
        r2 = c.get("/farmacia/indicacoes-catalogo", params={"busca": "produto-inexistente"})
        assert r2.json() == []


class TestPersonalizarClona:
    def test_personalizar_cria_clone_com_fazenda_id_e_origem_id(self, client):
        c, engine = client
        doenca_id, pa_id, marca_id = _ids_globais(engine)
        _como_fazenda(1)
        r = c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar")
        assert r.status_code == 201, r.text
        clone = r.json()
        assert clone["origem_id"] == doenca_id
        assert clone["personalizada"] is True
        assert clone["id"] != doenca_id

        with Session(engine) as s:
            doenca_clonada = s.get(Doenca, clone["id"])
            assert doenca_clonada.fazenda_id == 1
            assert doenca_clonada.origem_id == doenca_id

            inds = s.exec(
                select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.doenca_id == clone["id"])
            ).all()
            assert len(inds) == 1
            assert inds[0].fazenda_id == 1
            assert inds[0].principio_ativo_id == pa_id  # princípio NUNCA é clonado

            marcas_fazenda = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == pa_id, MedicamentoComercial.fazenda_id == 1,
                )
            ).all()
            assert len(marcas_fazenda) == 1
            assert marcas_fazenda[0].origem_id == marca_id
            assert marcas_fazenda[0].nome_comercial == "Excenel"

            # PrincipioAtivo nunca é duplicado — continua existindo só o global.
            principios = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Ceftiofur")).all()
            assert len(principios) == 1

    def test_personalizar_duas_vezes_e_idempotente(self, client):
        c, engine = client
        doenca_id, pa_id, marca_id = _ids_globais(engine)
        _como_fazenda(1)
        r1 = c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar")
        r2 = c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar")
        assert r1.json()["id"] == r2.json()["id"]

        with Session(engine) as s:
            clones = s.exec(select(Doenca).where(Doenca.origem_id == doenca_id, Doenca.fazenda_id == 1)).all()
            assert len(clones) == 1
            marcas_fazenda = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == pa_id, MedicamentoComercial.fazenda_id == 1,
                )
            ).all()
            assert len(marcas_fazenda) == 1  # não duplicou a marca na 2ª chamada

    def test_personalizar_esconde_a_global_correspondente_sem_duplicar(self, client):
        c, engine = client
        doenca_id, _, _ = _ids_globais(engine)
        _como_fazenda(1)
        c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar")

        itens = c.get("/farmacia/indicacoes-catalogo").json()
        mastites = [i for i in itens if i["nome"] == "Mastite Clínica"]
        assert len(mastites) == 1, "catálogo mostrou padrão E personalização — duplicado"
        assert mastites[0]["personalizada"] is True

    def test_personalizar_doenca_inexistente_da_404(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.post("/farmacia/indicacoes/99999/personalizar")
        assert r.status_code == 404

    def test_personalizar_a_propria_doenca_da_400(self, client):
        c, engine = client
        doenca_id, _, _ = _ids_globais(engine)
        _como_fazenda(1)
        c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar")
        with Session(engine) as s:
            clone = s.exec(select(Doenca).where(Doenca.origem_id == doenca_id, Doenca.fazenda_id == 1)).one()
        r = c.post(f"/farmacia/indicacoes/{clone.id}/personalizar")
        assert r.status_code == 400

    def test_outra_fazenda_nao_ve_a_personalizacao_da_primeira(self, client):
        c, engine = client
        doenca_id, _, _ = _ids_globais(engine)
        _como_fazenda(1)
        c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar")

        _como_fazenda(2)
        itens = c.get("/farmacia/indicacoes-catalogo").json()
        mastites = [i for i in itens if i["nome"] == "Mastite Clínica"]
        assert len(mastites) == 1
        assert mastites[0]["personalizada"] is False  # continua vendo o global, não o clone da fazenda 1


class TestDespersonalizar:
    def test_despersonalizar_remove_so_o_que_tem_origem_id(self, client):
        c, engine = client
        doenca_id, pa_id, marca_id = _ids_globais(engine)
        _como_fazenda(1)
        clone = c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar").json()
        clone_id = clone["id"]

        # Produtor adiciona, à mão, uma indicação própria a mais na doença personalizada
        # (SEM origem_id — não pode ser apagada pela despersonalização).
        with Session(engine) as s:
            outro_pa = PrincipioAtivo(nome="Outro Princípio Próprio", fazenda_id=1)
            s.add(outro_pa)
            s.commit()
            s.refresh(outro_pa)
            s.add(IndicacaoTerapeutica(principio_ativo_id=outro_pa.id, doenca_id=clone_id, prioridade=2, fazenda_id=1))
            s.commit()
            outro_pa_id = outro_pa.id

        r = c.delete(f"/farmacia/indicacoes/{clone_id}/personalizar")
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            assert s.get(Doenca, clone_id) is None
            # indicação clonada (com origem_id) sumiu
            clonada = s.exec(
                select(IndicacaoTerapeutica).where(
                    IndicacaoTerapeutica.doenca_id == clone_id, IndicacaoTerapeutica.origem_id.is_not(None),
                )
            ).first()
            assert clonada is None
            # marca clonada (com origem_id) sumiu — nenhuma outra indicação da fazenda usa o princípio
            marca_clonada = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == pa_id, MedicamentoComercial.fazenda_id == 1,
                )
            ).first()
            assert marca_clonada is None
            # a indicação própria (sem origem_id) do produtor, ligada à doença que acabou de sumir,
            # continua intacta — nunca apagamos o que ele criou do zero.
            propria = s.exec(
                select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.principio_ativo_id == outro_pa_id)
            ).first()
            assert propria is not None
            assert s.get(PrincipioAtivo, outro_pa_id) is not None

    def test_despersonalizar_doenca_que_nao_e_clone_da_fazenda_da_404(self, client):
        c, engine = client
        doenca_id, _, _ = _ids_globais(engine)
        _como_fazenda(1)
        # doença global (não personalizada) não é um clone — 404.
        r = c.delete(f"/farmacia/indicacoes/{doenca_id}/personalizar")
        assert r.status_code == 404

    def test_fazenda_2_nao_consegue_despersonalizar_clone_da_fazenda_1(self, client):
        c, engine = client
        doenca_id, _, _ = _ids_globais(engine)
        _como_fazenda(1)
        clone_id = c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar").json()["id"]

        _como_fazenda(2)
        r = c.delete(f"/farmacia/indicacoes/{clone_id}/personalizar")
        assert r.status_code == 404


class TestPutMarcaTravaGlobal:
    def test_put_em_marca_global_da_404(self, client):
        c, engine = client
        _, _, marca_id = _ids_globais(engine)
        _como_fazenda(1)
        r = c.put(f"/farmacia/medicamentos/{marca_id}", json={
            "principio_ativo_id": _ids_globais(engine)[1], "nome_comercial": "Excenel", "dose_texto": "novo",
        })
        assert r.status_code == 404

    def test_put_em_marca_personalizada_funciona(self, client):
        c, engine = client
        doenca_id, pa_id, marca_id = _ids_globais(engine)
        _como_fazenda(1)
        c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar")
        with Session(engine) as s:
            marca_fazenda = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == pa_id, MedicamentoComercial.fazenda_id == 1,
                )
            ).one()
            marca_fazenda_id = marca_fazenda.id

        r = c.put(f"/farmacia/medicamentos/{marca_fazenda_id}", json={
            "principio_ativo_id": pa_id, "nome_comercial": "Excenel", "dose_texto": "1 mL/40 kg SC",
            "carencia_leite_dias": 2, "carencia_carne_dias": 5,
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["dose_texto"] == "1 mL/40 kg SC"
        assert corpo["carencia"]["leite_dias"] == 2
        assert corpo["carencia"]["carne_dias"] == 5


class TestPutIndicacaoTravaGlobal:
    def test_put_em_vinculo_global_da_404(self, client):
        c, engine = client
        doenca_id, pa_id, _ = _ids_globais(engine)
        _como_fazenda(1)
        with Session(engine) as s:
            vinculo_global = s.exec(
                select(IndicacaoTerapeutica).where(
                    IndicacaoTerapeutica.doenca_id == doenca_id, IndicacaoTerapeutica.principio_ativo_id == pa_id,
                )
            ).one()
        r = c.put(f"/farmacia/indicacoes/{vinculo_global.id}", json={"prioridade": 3, "nota": "tentativa"})
        assert r.status_code == 404

    def test_put_em_vinculo_personalizado_funciona(self, client):
        c, engine = client
        doenca_id, pa_id, _ = _ids_globais(engine)
        _como_fazenda(1)
        clone = c.post(f"/farmacia/indicacoes/{doenca_id}/personalizar").json()
        vinculo_id = clone["principios"][0]["indicacao_id"]

        r = c.put(f"/farmacia/indicacoes/{vinculo_id}", json={"prioridade": 3, "nota": "só com corpo lúteo"})
        assert r.status_code == 200, r.text
        assert r.json()["prioridade"] == 3
        assert r.json()["nota"] == "só com corpo lúteo"
