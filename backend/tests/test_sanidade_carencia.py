"""
Fase 4 — a carência tem que APARECER onde o operador precisa: no picker de
medicamento (Agenda/Central de Protocolos/protocolo sanitário/indução), na
listagem "/estoque/medicamentos" (FormSanidade/FormProtocoloSanitario/
EditorHormoniosIatf), na listagem e no lançamento de aplicação avulsa
(Sanidade) e no relatório de rastreabilidade sanitária.

Cobre também o casamento item de Estoque -> marca comercial (por
`medicamento_comercial_id` ou por nome dentro do mesmo princípio ativo) e o
fallback do campo legado `Estoque.carencia_dias` (dado morto do formulário
antigo) — que só pode virar carência de CARNE, nunca de leite.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, MedicamentoComercial, PrincipioAtivo,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.estoque_baixa import carencia_para_item, opcoes_medicamento, resolver_marca_comercial


# ---------------------------------------------------------------------------
# Fixture de app (mesma convenção de test_farmacia_visibilidade.py)
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        permissoes = "sanidade,estoque"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _seed_basico(engine) -> dict:
    """Princípio ativo + duas marcas comerciais (uma com carência normal, uma
    proibida em lactação) + itens de estoque vinculados/casados por nome, mais
    um item legado (sem marca, com `carencia_dias` antigo preenchido)."""
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Meloxicam", unidade_base="ml", fazenda_id=1)
        s.add(pa)
        s.commit()
        s.refresh(pa)

        marca_normal = MedicamentoComercial(
            principio_ativo_id=pa.id, nome_comercial="Maxicam 2%", laboratorio="Ourofino",
            carencia_leite_dias=3, carencia_carne_dias=8, fazenda_id=1,
        )
        marca_proibida = MedicamentoComercial(
            principio_ativo_id=pa.id, nome_comercial="Flunixin Proibido", laboratorio="LabX",
            carencia_carne_dias=35, proibido_lactacao=True, fazenda_id=1,
        )
        s.add(marca_normal)
        s.add(marca_proibida)
        s.commit()
        s.refresh(marca_normal)
        s.refresh(marca_proibida)

        # Item vinculado explicitamente por medicamento_comercial_id.
        item_vinculado = Estoque(
            nome="Maxicam 2% 50ml", quantidade=10, unidade="ml", fazenda_id=1,
            principio_ativo_id=pa.id, medicamento_comercial_id=marca_normal.id,
        )
        # Item que casa por NOME (mesmo texto da marca, sem vínculo explícito).
        item_por_nome = Estoque(
            nome="Flunixin Proibido", quantidade=5, unidade="ml", fazenda_id=1,
            principio_ativo_id=pa.id,
        )
        # Item legado: nenhuma marca casa com o nome, mas tem `carencia_dias`
        # preenchido pelo formulário antigo.
        item_legado = Estoque(
            nome="Produto Sem Marca Cadastrada", quantidade=20, unidade="ml", fazenda_id=1,
            principio_ativo_id=pa.id, carencia_dias=15,
        )
        # Item totalmente sem informação de carência (nem marca, nem legado).
        item_sem_info = Estoque(
            nome="Produto Sem Info Nenhuma", quantidade=8, unidade="ml", fazenda_id=1,
            principio_ativo_id=pa.id,
        )
        # Item auto-cadastrado pelo tenant (sem medicamento_comercial_id, sem
        # marca casando por nome) mas com carência/lactação próprias — pedido
        # do usuário (01/09/2026): "colocar, junto com a carência para o
        # leite, opção de marcar se pode aplicar em vacas em lactação".
        item_proprio_proibido = Estoque(
            nome="Produto Cadastrado Direto Proibido", quantidade=6, unidade="ml", fazenda_id=1,
            principio_ativo_id=pa.id, carencia_carne_dias=21, proibido_lactacao=True,
        )
        s.add(item_vinculado)
        s.add(item_por_nome)
        s.add(item_legado)
        s.add(item_sem_info)
        s.add(item_proprio_proibido)
        s.commit()
        s.refresh(item_vinculado)
        s.refresh(item_por_nome)
        s.refresh(item_legado)
        s.refresh(item_sem_info)
        s.refresh(item_proprio_proibido)

        return {
            "pa_id": pa.id,
            "marca_normal_id": marca_normal.id,
            "marca_proibida_id": marca_proibida.id,
            "item_vinculado_id": item_vinculado.id,
            "item_por_nome_id": item_por_nome.id,
            "item_legado_id": item_legado.id,
            "item_sem_info_id": item_sem_info.id,
            "item_proprio_proibido_id": item_proprio_proibido.id,
        }


# ---------------------------------------------------------------------------
# 4C — opcoes_medicamento (rules/estoque_baixa.py)
# ---------------------------------------------------------------------------
class TestOpcoesMedicamento:
    def test_opcao_vinculada_traz_carencia_com_texto_e_proibido_lactacao(self, client):
        c, engine = client
        ids = _seed_basico(engine)
        with Session(engine) as s:
            _, opcoes = opcoes_medicamento(s, fazenda_id=1, produto="Maxicam 2% 50ml")
        assert len(opcoes) >= 1
        opcao = next(o for o in opcoes if o["estoque_id"] == ids["item_vinculado_id"])
        assert opcao["carencia"]["texto"] == "Carência: leite — 3 dias / carne — 8 dias"
        assert opcao["carencia"]["leite_dias"] == 3
        assert opcao["carencia"]["carne_dias"] == 8
        assert opcao["proibido_lactacao"] is False
        assert opcao["carencia"]["carencia_origem"] == "marca"

    def test_opcao_proibida_em_lactacao_vem_marcada_e_com_texto_explicito(self, client):
        c, engine = client
        ids = _seed_basico(engine)
        with Session(engine) as s:
            _, opcoes = opcoes_medicamento(s, fazenda_id=1, produto="Flunixin Proibido")
        opcao = next(o for o in opcoes if o["estoque_id"] == ids["item_por_nome_id"])
        assert opcao["proibido_lactacao"] is True
        assert "NÃO USAR" in opcao["carencia"]["texto"]
        assert "lactação" in opcao["carencia"]["texto"]
        assert opcao["carencia"]["liberacao_leite"] is None  # nunca projeta liberação de leite p/ produto proibido

    def test_fallback_legado_vira_carne_nunca_leite(self, client):
        c, engine = client
        ids = _seed_basico(engine)
        with Session(engine) as s:
            _, opcoes = opcoes_medicamento(s, fazenda_id=1, produto="Produto Sem Marca Cadastrada")
        opcao = next(o for o in opcoes if o["estoque_id"] == ids["item_legado_id"])
        assert opcao["carencia"]["carne_dias"] == 15
        assert opcao["carencia"]["leite_dias"] is None
        assert opcao["carencia"]["carencia_origem"] == "fazenda"

    def test_sem_marca_e_sem_legado_nao_informa_nada(self, client):
        c, engine = client
        ids = _seed_basico(engine)
        with Session(engine) as s:
            _, opcoes = opcoes_medicamento(s, fazenda_id=1, produto="Produto Sem Info Nenhuma")
        opcao = next(o for o in opcoes if o["estoque_id"] == ids["item_sem_info_id"])
        assert opcao["carencia"]["leite_dias"] is None
        assert opcao["carencia"]["carne_dias"] is None
        assert opcao["carencia"]["texto"] == "Carência: não informada"

    def test_carencia_e_lactacao_do_proprio_item_de_estoque_sem_marca(self, client):
        """Item de estoque auto-cadastrado pelo tenant (sem marca comercial
        vinculada) tem sua PRÓPRIA carência/lactação lidas — não fica mais
        preso ao fallback legado de `carencia_dias` (carne-only)."""
        c, engine = client
        ids = _seed_basico(engine)
        with Session(engine) as s:
            _, opcoes = opcoes_medicamento(s, fazenda_id=1, produto="Produto Cadastrado Direto Proibido")
        opcao = next(o for o in opcoes if o["estoque_id"] == ids["item_proprio_proibido_id"])
        assert opcao["proibido_lactacao"] is True
        assert opcao["carencia"]["carne_dias"] == 21
        assert "NÃO USAR" in opcao["carencia"]["texto"]
        assert opcao["carencia"]["carencia_origem"] == "fazenda"


class TestResolverMarcaComercial:
    def test_prioriza_vinculo_explicito_sobre_nome(self, client):
        c, engine = client
        ids = _seed_basico(engine)
        with Session(engine) as s:
            item = s.get(Estoque, ids["item_vinculado_id"])
            marca = resolver_marca_comercial(s, item=item, principio_ativo_id=item.principio_ativo_id)
            assert marca is not None
            assert marca.id == ids["marca_normal_id"]

    def test_casa_por_nome_quando_sem_vinculo(self, client):
        c, engine = client
        ids = _seed_basico(engine)
        with Session(engine) as s:
            item = s.get(Estoque, ids["item_por_nome_id"])
            marca = resolver_marca_comercial(s, item=item, principio_ativo_id=item.principio_ativo_id)
            assert marca is not None
            assert marca.id == ids["marca_proibida_id"]


# ---------------------------------------------------------------------------
# 4C' — GET /estoque/medicamentos
# ---------------------------------------------------------------------------
class TestEstoqueMedicamentos:
    def test_lista_traz_carencia_proibido_lactacao_e_alerta(self, client):
        c, engine = client
        _seed_basico(engine)
        r = c.get("/estoque/medicamentos", params={"principio_ativo": "Meloxicam", "incluir_sem_estoque": True})
        assert r.status_code == 200, r.text
        itens = r.json()
        por_nome = {i["nome"]: i for i in itens}

        vinculado = por_nome["Maxicam 2% 50ml"]
        assert vinculado["carencia"]["texto"] == "Carência: leite — 3 dias / carne — 8 dias"
        assert vinculado["proibido_lactacao"] is False

        proibido = por_nome["Flunixin Proibido"]
        assert proibido["proibido_lactacao"] is True
        assert "NÃO USAR" in proibido["carencia"]["texto"]

        legado = por_nome["Produto Sem Marca Cadastrada"]
        assert legado["carencia"]["carne_dias"] == 15
        assert legado["carencia"]["leite_dias"] is None


# ---------------------------------------------------------------------------
# 4A — /sanidade/aplicacoes
# ---------------------------------------------------------------------------
class TestSanidadeAplicacoes:
    def test_post_avulso_devolve_aviso_com_data_de_liberacao_do_leite(self, client):
        c, engine = client
        _seed_basico(engine)
        payload = {
            "data_aplicacao": "2026-08-07",
            "animais": ["1001"],
            "itens": [{"produto": "Maxicam 2% 50ml", "quantidade": 2, "unidade": "ml"}],
            "aplicado": True,
        }
        r = c.post("/sanidade/aplicacoes", json=payload)
        assert r.status_code == 200, r.text
        corpo = r.json()
        avisos_texto = " | ".join(corpo["avisos"])
        # Carência leite=3 dias a partir de 2026-08-07 -> libera 2026-08-10.
        assert "10/08/2026" in avisos_texto
        assert "Carência" in avisos_texto

    def test_post_avulso_de_produto_proibido_avisa_explicitamente(self, client):
        c, engine = client
        _seed_basico(engine)
        payload = {
            "data_aplicacao": "2026-08-07",
            "animais": ["1002"],
            "itens": [{"produto": "Flunixin Proibido", "quantidade": 1, "unidade": "ml"}],
            "aplicado": True,
        }
        r = c.post("/sanidade/aplicacoes", json=payload)
        assert r.status_code == 200, r.text
        avisos_texto = " | ".join(r.json()["avisos"])
        assert "lactação" in avisos_texto
        assert "NÃO" in avisos_texto.upper() or "não pode" in avisos_texto.lower()

    def test_post_avulso_sem_carencia_nenhuma_nao_gera_aviso_enganoso(self, client):
        c, engine = client
        _seed_basico(engine)
        payload = {
            "data_aplicacao": "2026-08-07",
            "animais": ["1003"],
            "itens": [{"produto": "Produto Sem Info Nenhuma", "quantidade": 1, "unidade": "ml"}],
            "aplicado": True,
        }
        r = c.post("/sanidade/aplicacoes", json=payload)
        assert r.status_code == 200, r.text
        avisos_texto = " | ".join(r.json()["avisos"])
        # Nem "sem carência" (mentira), nem número de dias inventado.
        assert "sem carência" not in avisos_texto.lower()
        assert "Carência" not in avisos_texto

    def test_listar_aplicacoes_traz_carencia_por_linha(self, client):
        c, engine = client
        _seed_basico(engine)
        c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-08-07",
            "animais": ["2001"],
            "itens": [{"produto": "Maxicam 2% 50ml", "quantidade": 2, "unidade": "ml"}],
            "aplicado": True,
        })
        r = c.get("/sanidade/aplicacoes")
        assert r.status_code == 200, r.text
        linhas = r.json()["aplicacoes"]
        linha = next(l for l in linhas if l["numero"] == "2001")
        assert linha["carencia"]["leite_dias"] == 3
        assert linha["carencia"]["liberacao_leite"] == "2026-08-10"


# ---------------------------------------------------------------------------
# 4B — relatório de rastreabilidade sanitária
# ---------------------------------------------------------------------------
class TestRelatorioRastreabilidade:
    def test_linha_de_aplicacao_traz_carencia(self, client):
        c, engine = client
        _seed_basico(engine)
        c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-08-07",
            "animais": ["3001"],
            "itens": [{"produto": "Maxicam 2% 50ml", "quantidade": 2, "unidade": "ml"}],
            "aplicado": True,
        })
        r = c.get("/relatorio-rastreabilidade-sanitaria/", params={"numero": "3001"})
        assert r.status_code == 200, r.text
        linhas = r.json()
        aplicacao = next(l for l in linhas if l["tipo_evento"] == "Aplicação sanitária")
        assert aplicacao["carencia"]["carne_dias"] == 8
        assert aplicacao["carencia"]["liberacao_carne"] == "2026-08-15"

    def test_linhas_sem_produto_nao_quebram_com_carencia_none(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Placeholder", quantidade=1, unidade="ml", fazenda_id=1))
            s.commit()
        r = c.get("/relatorio-rastreabilidade-sanitaria/", params={"numero": "9999-inexistente"})
        assert r.status_code == 200, r.text
        assert r.json() == []
