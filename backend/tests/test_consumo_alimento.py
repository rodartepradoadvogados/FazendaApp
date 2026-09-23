"""
Testes de Lançamentos > Alimentação > Consumo diário e sobra de cocho
(Sessão 3 — Frente B): POST/GET/DELETE de ConsumoAlimento, POST/GET de
ConsumoSobra e o relatório de sobra por alimento.

Cobre, no mínimo (B15): soma no mesmo dia; substituição da sobra; baixa e
devolução em estoque; 409 nas duas flags do lote e o caminho liberado por
elas; rateio com unidades mistas; rateio impossível; isolamento por fazenda.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ConsumoAlimento, ConsumoSobra, ContratoFazenda, ContratoFazendaModulo, DietaItemProgramado,
    DietaLancamento, Estoque, Fazenda, Lote, MovimentoEstoque,
)

HOJE = date(2026, 8, 20)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    # `exigir_modulo_contratado("alimentacao")` (main.py, na inclusão do
    # router) só deixa passar `fazenda_id` != None com contrato ATIVO e o
    # módulo "alimentacao" contratado — sem isto, TODA chamada com a fazenda
    # explícita (ver `fazenda_atual` abaixo) cai em 403, mesmo antes de
    # chegar no endpoint. Duas fazendas, para os testes de isolamento (B15).
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
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""

    # Mutável para os testes de isolamento (B15) poderem trocar de fazenda no
    # meio do teste, sem precisar de uma segunda fixture inteira.
    fazenda_atual = {"id": 1}

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_atual["id"]

    with TestClient(main.app) as c:
        yield c, engine, fazenda_atual

    main.app.dependency_overrides.clear()


def _seed_lote_1(engine, fazenda_id: int = 1, permitir_fora_da_dieta: bool = False, permitir_sem_estoque: bool = False):
    """Lote 01, 2 animais, dieta ATIVA "total/dia" com um item (Silagem,
    40kg/dia para o lote = 20kg/cabeça) — o cenário-base da maioria dos testes."""
    with Session(engine) as s:
        s.add(Lote(
            codigo="01", fazenda_id=fazenda_id, nome="Alta",
            permitir_fora_da_dieta=permitir_fora_da_dieta, permitir_sem_estoque=permitir_sem_estoque,
        ))
        s.add(Animal(numero=f"{fazenda_id}-1-A", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True, fazenda_id=fazenda_id))
        s.add(Animal(numero=f"{fazenda_id}-1-B", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True, fazenda_id=fazenda_id))
        dieta = DietaLancamento(lote=1, fazenda_id=fazenda_id, data_abertura=HOJE, base_quantidade="total")
        s.add(dieta)
        s.commit()
        s.refresh(dieta)
        s.add(DietaItemProgramado(fazenda_id=fazenda_id, dieta_lancamento_id=dieta.id, alimento="Silagem", quantidade=40.0, unidade="kg"))
        s.add(Estoque(nome="Silagem", fazenda_id=fazenda_id, quantidade=1000.0, unidade="kg"))
        s.commit()
        return dieta.id


def _set_flags(engine, fazenda_id: int, *, permitir_fora_da_dieta: bool | None = None, permitir_sem_estoque: bool | None = None):
    with Session(engine) as s:
        lote = s.exec(select(Lote).where(Lote.codigo == "01", Lote.fazenda_id == fazenda_id)).first()
        if permitir_fora_da_dieta is not None:
            lote.permitir_fora_da_dieta = permitir_fora_da_dieta
        if permitir_sem_estoque is not None:
            lote.permitir_sem_estoque = permitir_sem_estoque
        s.add(lote)
        s.commit()


class TestDietaDoLote:
    """B3 — só os alimentos da dieta ativa, com a quantidade por cabeça já
    resolvida pelo backend (a checagem do B4 acontece aqui em miniatura)."""

    def test_lista_itens_da_dieta_ativa_com_por_cabeca_resolvido(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        r = c.get("/alimentacao/consumo/dieta-do-lote?lote=1")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["base_quantidade"] == "total"
        assert corpo["kg_total_dieta"] == 40.0
        assert corpo["itens"] == [{
            "alimento": "Silagem", "alimento_id": None, "quantidade": 40.0, "unidade": "kg",
            "por_cabeca": 20.0, "converte_para_kg": True,
            "quantidade_total_lote": 40.0, "kg_total": 40.0, "percentual_dieta": 100.0,
        }]

    def test_404_quando_lote_nao_tem_dieta_ativa(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        r = c.get("/alimentacao/consumo/dieta-do-lote?lote=99")
        assert r.status_code == 404

    def test_item_com_override_por_cabeca_ignora_a_base_da_dieta(self, client):
        """Dieta "total/dia" (padrão), mas um item específico foi lançado com
        override "animal" — o `por_cabeca` desse item usa a SUA base, não a
        da dieta (2 animais, item com 5kg/cabeça/dia → por_cabeca = 5, não
        5/2 = 2.5)."""
        c, engine, _ = client
        dieta_id = _seed_lote_1(engine)
        with Session(engine) as s:
            s.add(DietaItemProgramado(
                fazenda_id=1, dieta_lancamento_id=dieta_id, alimento="Concentrado",
                quantidade=5.0, unidade="kg", base_quantidade="animal",
            ))
            s.commit()

        corpo = c.get("/alimentacao/consumo/dieta-do-lote?lote=1").json()
        por_alimento = {it["alimento"]: it for it in corpo["itens"]}
        assert por_alimento["Silagem"]["por_cabeca"] == 20.0  # herda "total": 40/2
        assert por_alimento["Concentrado"]["por_cabeca"] == 5.0  # override "animal": já é por cabeça


class TestLancamentoConsumo:
    """B1/B2/B4/B7/B8 — lançar consumo, ver o acumulado do dia, dar baixa e
    propagar avisos."""

    def test_lancamento_por_animais_nao_dobra_a_conta_base_total(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        # Dieta é "total/dia" (40kg p/ 2 animais = 20kg/cabeça). O bug mais
        # provável (spec) é multiplicar 40 (total) por 2 animais de novo — o
        # valor certo é 40, não 80. O `quantidade` enviado pelo cliente é lixo
        # de propósito: o servidor tem que recalcular, não confiar nele.
        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "num_animais": 2, "origem": "animais",
            "itens": [{"alimento": "Silagem", "quantidade": 999, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text
        assert r.json() == {"ok": True, "avisos": []}

        r2 = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}")
        assert r2.status_code == 200, r2.text
        corpo = r2.json()
        assert corpo["itens"] == [{"alimento": "Silagem", "quantidade": 40.0, "unidade": "kg", "kg_equivalente": 40.0}]
        assert corpo["kg_fornecido_total"] == 40.0
        assert corpo["num_animais"] == 2

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Silagem")).first()
            assert estoque.quantidade == 960.0  # 1000 - 40

    def test_lancamento_por_animais_nao_dobra_a_conta_base_animal(self, client):
        """Mesmo cuidado do teste acima, mas para o outro lado do enum
        (`base_quantidade == "animal"`) — dieta com 5kg/cabeça/dia, lote com
        3 animais informados (nº diferente do cadastro, de propósito: o
        usuário pode digitar o efetivo do trato, não o do cadastro)."""
        c, engine, _ = client
        with Session(engine) as s:
            s.add(Lote(codigo="02", fazenda_id=1, nome="Baixa"))
            dieta = DietaLancamento(lote=2, fazenda_id=1, data_abertura=HOJE, base_quantidade="animal")
            s.add(dieta)
            s.commit()
            s.refresh(dieta)
            s.add(DietaItemProgramado(fazenda_id=1, dieta_lancamento_id=dieta.id, alimento="Concentrado", quantidade=5.0, unidade="kg"))
            s.add(Estoque(nome="Concentrado", fazenda_id=1, quantidade=1000.0, unidade="kg"))
            s.commit()

        r = c.post("/alimentacao/consumo", json={
            "lote": 2, "data": HOJE.isoformat(), "num_animais": 3, "origem": "animais",
            "itens": [{"alimento": "Concentrado", "quantidade": 1, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Concentrado")).first()
            assert estoque.quantidade == 985.0  # 1000 - (5/cabeça * 3 animais = 15)

    def test_lancamento_por_animais_respeita_override_do_item_dentro_de_dieta_total(self, client):
        """Mesma dieta "total/dia" de `_seed_lote_1`, mas o item lançado com
        consumo "por animal" tem override próprio "animal" (3kg/cabeça) — a
        baixa de estoque tem que usar a base do ITEM (3 * num_animais), não a
        da dieta (que dividiria de novo e dobraria o erro do outro lado)."""
        c, engine, _ = client
        dieta_id = _seed_lote_1(engine)
        with Session(engine) as s:
            s.add(DietaItemProgramado(
                fazenda_id=1, dieta_lancamento_id=dieta_id, alimento="Concentrado",
                quantidade=3.0, unidade="kg", base_quantidade="animal",
            ))
            s.add(Estoque(nome="Concentrado", fazenda_id=1, quantidade=500.0, unidade="kg"))
            s.commit()

        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "num_animais": 2, "origem": "animais",
            "itens": [{"alimento": "Concentrado", "quantidade": 1, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Concentrado")).first()
            assert estoque.quantidade == 494.0  # 500 - (3/cabeça * 2 animais = 6)

    def test_lancamentos_do_mesmo_dia_somam(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        for quantidade in (40.0, 10.0):
            r = c.post("/alimentacao/consumo", json={
                "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
                "itens": [{"alimento": "Silagem", "quantidade": quantidade, "unidade": "kg"}],
            })
            assert r.status_code == 201, r.text

        corpo = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        assert corpo["itens"][0]["quantidade"] == 50.0
        assert corpo["kg_fornecido_total"] == 50.0

    def test_avisos_da_baixa_sao_propagados(self, client):
        """B8 — hoje esses avisos são jogados fora pelos outros chamadores
        (`obter_alimentacao`/`necessidade_mensal`); aqui têm de aparecer."""
        c, engine, _ = client
        _seed_lote_1(engine, permitir_sem_estoque=True)
        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Silagem")).first()
            estoque.quantidade = 5.0
            s.add(estoque)
            s.commit()

        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Silagem", "quantidade": 40.0, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text
        avisos = r.json()["avisos"]
        assert len(avisos) == 1
        assert "negativo" in avisos[0]

    def test_baixa_gravada_com_origem_rastreavel(self, client):
        """B7 — `origem_tipo="consumo_alimento"` e `origem_id` do registro."""
        c, engine, _ = client
        _seed_lote_1(engine)
        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Silagem", "quantidade": 40.0, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text

        with Session(engine) as s:
            registro = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.lote == 1)).first()
            movimento = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "consumo_alimento")).first()
            assert movimento is not None
            assert movimento.origem_id == registro.id
            assert movimento.quantidade == 40.0


class TestLancamentoConsumoVagao:
    """Lançamento "Quantidade direta" via kg total do vagão (item novo,
    23/09/2026): o funcionário informa só o kg TOTAL ofertado, e a
    quantidade de CADA alimento que converte para kg é derivada da % dele na
    dieta — calculada no SERVIDOR (origem "vagao"), nunca confiando no valor
    que o cliente já mostrou na tabela gerencial."""

    def _seed_dieta_mista(self, engine, fazenda_id: int = 1):
        """Lote 01, 2 animais, dieta "total/dia" com 3 itens: Silagem 40kg
        (40% da dieta em kg), Concentrado 2 sacas de 30kg = 60kg (60% da
        dieta), e um Aditivo em "dose" (não converte p/ kg, fica de fora do
        rateio — só entra lançado à mão)."""
        with Session(engine) as s:
            s.add(Lote(codigo="01", fazenda_id=fazenda_id, nome="Alta"))
            s.add(Animal(numero=f"{fazenda_id}-1-A", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True, fazenda_id=fazenda_id))
            s.add(Animal(numero=f"{fazenda_id}-1-B", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True, fazenda_id=fazenda_id))
            dieta = DietaLancamento(lote=1, fazenda_id=fazenda_id, data_abertura=HOJE, base_quantidade="total")
            s.add(dieta)
            s.commit()
            s.refresh(dieta)
            s.add(DietaItemProgramado(fazenda_id=fazenda_id, dieta_lancamento_id=dieta.id, alimento="Silagem", quantidade=40.0, unidade="kg"))
            s.add(DietaItemProgramado(fazenda_id=fazenda_id, dieta_lancamento_id=dieta.id, alimento="Concentrado", quantidade=2.0, unidade="saca 30kg"))
            s.add(DietaItemProgramado(fazenda_id=fazenda_id, dieta_lancamento_id=dieta.id, alimento="Aditivo", quantidade=4.0, unidade="dose"))
            s.add(Estoque(nome="Silagem", fazenda_id=fazenda_id, quantidade=1000.0, unidade="kg"))
            s.add(Estoque(nome="Concentrado", fazenda_id=fazenda_id, quantidade=100.0, unidade="saca 30kg"))
            s.add(Estoque(nome="Aditivo", fazenda_id=fazenda_id, quantidade=50.0, unidade="dose"))
            s.commit()

    def test_dieta_do_lote_devolve_percentual_e_kg_total(self, client):
        c, engine, _ = client
        self._seed_dieta_mista(engine)
        corpo = c.get("/alimentacao/consumo/dieta-do-lote?lote=1").json()
        assert corpo["kg_total_dieta"] == 100.0  # 40 (silagem) + 60 (2 sacas de 30kg)
        por_alimento = {it["alimento"]: it for it in corpo["itens"]}
        assert por_alimento["Silagem"]["kg_total"] == 40.0
        assert por_alimento["Silagem"]["percentual_dieta"] == 40.0
        assert por_alimento["Concentrado"]["quantidade_total_lote"] == 2.0  # 2 sacas, não kg
        assert por_alimento["Concentrado"]["kg_total"] == 60.0
        assert por_alimento["Concentrado"]["percentual_dieta"] == 60.0
        assert por_alimento["Aditivo"]["kg_total"] is None
        assert por_alimento["Aditivo"]["percentual_dieta"] is None

    def test_vagao_rateia_por_kg_e_converte_de_volta_pra_unidade_do_item(self, client):
        c, engine, _ = client
        self._seed_dieta_mista(engine)
        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "vagao", "kg_vagao": 50,
            "itens": [{"alimento": "Aditivo", "quantidade": 2, "unidade": "dose"}],
        })
        assert r.status_code == 201, r.text

        corpo = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        por_alimento = {it["alimento"]: it for it in corpo["itens"]}
        # 50kg no vagão, 40%/60% da dieta: 20kg de silagem, 30kg de
        # concentrado — convertido de volta pra "saca 30kg" (30/30 = 1 saca).
        assert por_alimento["Silagem"]["quantidade"] == 20.0
        assert por_alimento["Silagem"]["unidade"] == "kg"
        assert por_alimento["Concentrado"]["quantidade"] == 1.0
        assert por_alimento["Concentrado"]["unidade"] == "saca 30kg"
        # Aditivo não converte p/ kg — veio do valor manual enviado, intacto.
        assert por_alimento["Aditivo"]["quantidade"] == 2.0
        assert por_alimento["Aditivo"]["unidade"] == "dose"

        with Session(engine) as s:
            silagem = s.exec(select(Estoque).where(Estoque.nome == "Silagem")).first()
            concentrado = s.exec(select(Estoque).where(Estoque.nome == "Concentrado")).first()
            aditivo = s.exec(select(Estoque).where(Estoque.nome == "Aditivo")).first()
            assert silagem.quantidade == 980.0     # 1000 - 20
            assert concentrado.quantidade == 99.0   # 100 - 1
            assert aditivo.quantidade == 48.0        # 50 - 2

    def test_vagao_ignora_conta_do_cliente_e_recalcula_no_servidor(self, client):
        """O front pode mandar `itens` com valores absurdos para os alimentos
        que a dieta já cobre — o servidor tem que ignorá-los e recalcular do
        `kg_vagao`, a mesma postura de "animais" (nunca confiar no cliente)."""
        c, engine, _ = client
        self._seed_dieta_mista(engine)
        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "vagao", "kg_vagao": 50,
            "itens": [
                {"alimento": "Silagem", "quantidade": 9999, "unidade": "kg"},  # deve ser ignorado
                {"alimento": "Aditivo", "quantidade": 2, "unidade": "dose"},
            ],
        })
        assert r.status_code == 201, r.text
        corpo = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        por_alimento = {it["alimento"]: it for it in corpo["itens"]}
        assert por_alimento["Silagem"]["quantidade"] == 20.0  # não 9999 nem a soma com 9999

    def test_kg_vagao_obrigatorio_e_positivo(self, client):
        c, engine, _ = client
        self._seed_dieta_mista(engine)
        for kg_vagao in (None, 0, -5):
            r = c.post("/alimentacao/consumo", json={
                "lote": 1, "data": HOJE.isoformat(), "origem": "vagao", "kg_vagao": kg_vagao, "itens": [],
            })
            assert r.status_code == 400, r.text

    def test_vagao_sem_itens_manuais_ainda_lanca_os_proporcionais(self, client):
        c, engine, _ = client
        self._seed_dieta_mista(engine)
        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "vagao", "kg_vagao": 10, "itens": [],
        })
        assert r.status_code == 201, r.text
        corpo = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        alimentos = {it["alimento"] for it in corpo["itens"]}
        assert alimentos == {"Silagem", "Concentrado"}  # Aditivo não veio manual — fica de fora


class TestFlagsDoLote:
    """B5/B6 — 409 quando a flag do lote está desligada, liberado quando ligada."""

    def test_fora_da_dieta_bloqueado_sem_flag(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        with Session(engine) as s:
            s.add(Estoque(nome="Ração Nova", fazenda_id=1, quantidade=100.0, unidade="kg"))
            s.commit()

        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Ração Nova", "quantidade": 5.0, "unidade": "kg"}],
        })
        assert r.status_code == 409, r.text

    def test_fora_da_dieta_liberado_com_flag(self, client):
        c, engine, _ = client
        _seed_lote_1(engine, permitir_fora_da_dieta=True)
        with Session(engine) as s:
            s.add(Estoque(nome="Ração Nova", fazenda_id=1, quantidade=100.0, unidade="kg"))
            s.commit()

        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Ração Nova", "quantidade": 5.0, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text
        with Session(engine) as s:
            registro = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.alimento == "Ração Nova")).first()
            assert registro.fora_da_dieta is True

    def test_sem_saldo_bloqueado_sem_flag(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Silagem")).first()
            estoque.quantidade = 0.0
            s.add(estoque)
            s.commit()

        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Silagem", "quantidade": 5.0, "unidade": "kg"}],
        })
        assert r.status_code == 409, r.text

    def test_sem_saldo_liberado_com_flag(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Silagem")).first()
            estoque.quantidade = 0.0
            s.add(estoque)
            s.commit()
        _set_flags(engine, 1, permitir_sem_estoque=True)

        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Silagem", "quantidade": 5.0, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text


class TestExclusaoConsumo:
    """B9 — excluir devolve ao estoque pelo mesmo motor."""

    def test_excluir_devolve_ao_estoque(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Silagem", "quantidade": 40.0, "unidade": "kg"}],
        })
        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Silagem")).first()
            assert estoque.quantidade == 960.0
            registro_id = s.exec(select(ConsumoAlimento).where(ConsumoAlimento.lote == 1)).first().id

        r = c.delete(f"/alimentacao/consumo/{registro_id}")
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Silagem")).first()
            assert estoque.quantidade == 1000.0
            assert s.get(ConsumoAlimento, registro_id) is None

        corpo = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        assert corpo["itens"] == []


class TestSobra:
    """B10 — sobra substitui no mesmo dia, ao contrário do consumo (que soma)."""

    def test_relancar_no_mesmo_dia_substitui(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        r1 = c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 5.0})
        assert r1.status_code == 201, r1.text
        r2 = c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 8.0})
        assert r2.status_code == 201, r2.text

        with Session(engine) as s:
            registros = s.exec(select(ConsumoSobra).where(ConsumoSobra.lote == 1)).all()
            assert len(registros) == 1
            assert registros[0].kg_sobra == 8.0

    def test_sobra_aparece_no_get_consumo_com_percentual(self, client):
        c, engine, _ = client
        _seed_lote_1(engine)
        c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Silagem", "quantidade": 40.0, "unidade": "kg"}],
        })
        c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 2.0})

        corpo = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        assert corpo["sobra_kg"] == 2.0
        assert corpo["sobra_pct"] == 5.0  # 2 / 40 * 100 — bem no alvo (5%)
        assert corpo["dentro_da_faixa"] is True


class TestRelatorioSobra:
    """B11/B12/B13/B14 — sobra por alimento e total no período, rateio pela
    proporção da dieta em kg, unidades sem conversão fora da conta e listadas."""

    def _seed_lote_10(self, engine):
        with Session(engine) as s:
            s.add(Lote(codigo="10", fazenda_id=1, nome="Rateio"))
            dieta = DietaLancamento(lote=10, fazenda_id=1, data_abertura=HOJE, base_quantidade="total")
            s.add(dieta)
            s.commit()
            s.refresh(dieta)
            s.add(DietaItemProgramado(fazenda_id=1, dieta_lancamento_id=dieta.id, alimento="Silagem", quantidade=30.0, unidade="kg"))
            s.add(DietaItemProgramado(fazenda_id=1, dieta_lancamento_id=dieta.id, alimento="Concentrado", quantidade=10.0, unidade="kg"))
            # Item que não converte para kg (dose) — tem de ficar FORA do
            # rateio e aparecer em `itens_sem_conversao`, nunca virar 0
            # silencioso (ver docstring de rules/unidades).
            s.add(DietaItemProgramado(fazenda_id=1, dieta_lancamento_id=dieta.id, alimento="Aditivo", quantidade=2.0, unidade="dose"))
            s.add(Estoque(nome="Silagem", fazenda_id=1, quantidade=1000.0, unidade="kg"))
            s.add(Estoque(nome="Concentrado", fazenda_id=1, quantidade=1000.0, unidade="kg"))
            s.commit()

    def test_rateio_com_unidades_mistas(self, client):
        c, engine, _ = client
        self._seed_lote_10(engine)
        c.post("/alimentacao/consumo", json={
            "lote": 10, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [
                {"alimento": "Silagem", "quantidade": 30.0, "unidade": "kg"},
                {"alimento": "Concentrado", "quantidade": 10.0, "unidade": "kg"},
            ],
        })
        c.post("/alimentacao/sobra", json={"lote": 10, "data": HOJE.isoformat(), "kg_sobra": 4.0})

        r = c.get(f"/alimentacao/sobra/relatorio?de={HOJE.isoformat()}&ate={HOJE.isoformat()}&lote=10")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["total_kg_sobra"] == 4.0
        assert corpo["total_kg_fornecido"] == 40.0
        assert corpo["pct_medio"] == 10.0
        # Proporção na dieta: Silagem 30/40=75%, Concentrado 10/40=25% —
        # aplicada aos 4kg de sobra.
        assert corpo["por_alimento"] == [
            {"alimento": "Concentrado", "kg_sobra": 1.0, "pct_do_total": 25.0},
            {"alimento": "Silagem", "kg_sobra": 3.0, "pct_do_total": 75.0},
        ]
        assert corpo["itens_sem_conversao"] == ["Aditivo"]

    def test_rateio_impossivel_quando_nada_converte(self, client):
        """B13 — dieta cujo ÚNICO item não converte para kg: devolve o total
        (a sobra existiu, foi medida) e a lista de excluídos, sem inventar
        uma distribuição por alimento."""
        c, engine, _ = client
        with Session(engine) as s:
            s.add(Lote(codigo="11", fazenda_id=1, nome="SóDose"))
            dieta = DietaLancamento(lote=11, fazenda_id=1, data_abertura=HOJE, base_quantidade="total")
            s.add(dieta)
            s.commit()
            s.refresh(dieta)
            s.add(DietaItemProgramado(fazenda_id=1, dieta_lancamento_id=dieta.id, alimento="Suplemento", quantidade=5.0, unidade="dose"))
            s.commit()

        c.post("/alimentacao/sobra", json={"lote": 11, "data": HOJE.isoformat(), "kg_sobra": 2.0})

        r = c.get(f"/alimentacao/sobra/relatorio?de={HOJE.isoformat()}&ate={HOJE.isoformat()}&lote=11")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["total_kg_sobra"] == 2.0
        assert corpo["total_kg_fornecido"] == 0.0
        assert corpo["pct_medio"] is None
        assert corpo["por_alimento"] == []
        assert corpo["itens_sem_conversao"] == ["Suplemento"]


class TestIsolamentoPorFazenda:
    """B15 — nada de uma fazenda vaza para a listagem/relatório de outra."""

    def test_consumo_e_sobra_nao_vazam_entre_fazendas(self, client):
        c, engine, fazenda_atual = client
        _seed_lote_1(engine, fazenda_id=1)
        _seed_lote_1(engine, fazenda_id=2)

        fazenda_atual["id"] = 1
        c.post("/alimentacao/consumo", json={
            "lote": 1, "data": HOJE.isoformat(), "origem": "kg",
            "itens": [{"alimento": "Silagem", "quantidade": 40.0, "unidade": "kg"}],
        })
        c.post("/alimentacao/sobra", json={"lote": 1, "data": HOJE.isoformat(), "kg_sobra": 2.0})

        fazenda_atual["id"] = 2
        corpo = c.get(f"/alimentacao/consumo?lote=1&data={HOJE.isoformat()}").json()
        assert corpo["itens"] == []
        assert corpo["kg_fornecido_total"] == 0.0
        assert corpo["sobra_kg"] is None

        relatorio = c.get(f"/alimentacao/sobra/relatorio?de={HOJE.isoformat()}&ate={HOJE.isoformat()}&lote=1").json()
        assert relatorio["total_kg_sobra"] == 0.0
        assert relatorio["total_kg_fornecido"] == 0.0

        # E o estoque da fazenda 2 (nunca lançou nada) continua intacto.
        with Session(engine) as s:
            estoque_f2 = s.exec(select(Estoque).where(Estoque.nome == "Silagem", Estoque.fazenda_id == 2)).first()
            assert estoque_f2.quantidade == 1000.0
