"""
Auditoria de estoque/Sanidade dos protocolos (IATF, indução de lactação,
Lida) — fazenda/rules/estoque_baixa.py é o ponto ÚNICO de baixa/devolução
(ver o módulo para o porquê). Quem chama:

  - agenda.py: _marcar_protocolo_iatf_realizado / _marcar_protocolo_inducao_realizado
    (POST /agenda/realizados e POST /central-protocolos/{origem}/{id}/baixa);
  - lida.py (meu escopo): marcar_realizado (mesmas rotas, origem="lida");
  - central_protocolos.py: cancelar() estorna toda saída ("Aplicação") da
    origem; desfazer_aplicacao() (DELETE .../baixa) estorna uma dose, só p/ iatf.

Este arquivo cobre, nesta ordem:
  A. Primitivas de estoque_baixa.py isoladas (resolver_item, movimentar,
     baixar/devolver, portões, rastro) — sem HTTP, engine descartável.
  B. Quantidade exata via HTTP (IATF/indução/lida): N x dose, baixa parcial,
     baixa duas vezes não dobra.
  C. Escolha de frasco explícito e isolamento entre fazendas.
  D. Estorno exato: cancelar, desfazer, cancelar duas vezes.
  E. Sanidade: geração, data real, preservação no cancelamento.
  F. Bugs confirmados fora do meu escopo de correção — xfail com o motivo.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra todas as tabelas antes do create_all()
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Estoque, MovimentoEstoque, Sanidade,
)
from fazenda.rules import estoque_baixa


# ─────────────────────────────── Fixtures ──────────────────────────────────

@pytest.fixture
def bare_session():
    """Engine descartável, SEM HTTP — para as primitivas de estoque_baixa.py
    isoladas do resto da pilha (Agenda/Central)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def client():
    """Fazenda 1 com contrato ativo e os módulos produtivo/reprodutivo — para
    os testes via HTTP (Agenda, Central de Protocolos, Reprodução, Produção)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="produtivo", ativo=True))
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="reprodutivo", ativo=True))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _animais(engine, numeros):
    with Session(engine) as s:
        for n in numeros:
            s.add(Animal(numero=n, ativo=True))
        s.commit()


def _estoque(engine, fazenda_id=1, **kwargs) -> int:
    kwargs.setdefault("quantidade", 100)
    kwargs.setdefault("unidade", "ml")
    with Session(engine) as s:
        item = Estoque(fazenda_id=fazenda_id, **kwargs)
        s.add(item)
        s.commit()
        s.refresh(item)
        return item.id


def _lancar_iatf(c, animais, data_d0: date, hormonios: list[dict] | None = None) -> int:
    payload = {"animais": animais, "data_d0": data_d0.isoformat()}
    if hormonios:
        payload["hormonios"] = hormonios
    r = c.post("/reproducao/protocolo-iatf", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()["lancamento_id"]


def _cadastrar_inducao(c, etapas, nome="Indução teste"):
    r = c.post("/cadastro/protocolos-inducao-lactacao", json={
        "nome": nome, "dia_inicial": 0, "etapas": etapas,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _lancar_inducao(c, protocolo_id, animais, data_d0: date) -> int:
    r = c.post("/producao/inducao-lactacao", json={
        "protocolo_id": protocolo_id, "animais": animais, "data_d0": data_d0.isoformat(),
    })
    assert r.status_code == 201, r.text
    return next(
        l["origem_id"] for l in c.get("/central-protocolos/acompanhamento").json()
        if l["origem"] == "inducao"
    )


def _cadastrar_lida_frequencia(c, dose, unidade, insumo, dar_baixa=True, nome="Limpar cocho"):
    r = c.post("/cadastro/lidas", json={
        "nome": nome, "modo": "frequencia", "frequencia_dias": 15,
        "descricao_evento": "Limpar cocho de água", "insumo_padrao": insumo,
        "insumo_dose": dose, "insumo_unidade": unidade, "dar_baixa_estoque": dar_baixa,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _lancar_lida(c, lida_id, data: str, animais: list[str] | None = None) -> int:
    payload = {"lida_id": lida_id, "data_inicio": data, "data_fim": data}
    if animais is not None:
        payload["animais"] = animais
    r = c.post("/lida/lancar", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["lancamento_id"]


def _saldo(engine, nome: str) -> float:
    with Session(engine) as s:
        return s.exec(select(Estoque).where(Estoque.nome == nome)).one().quantidade


# ═══════════════════ A. Primitivas de estoque_baixa.py ═════════════════════

class TestResolverItem:
    def test_por_estoque_id_na_mesma_fazenda(self, bare_session):
        s = bare_session
        item = Estoque(fazenda_id=1, nome="Sincrocp", quantidade=50, unidade="ml")
        s.add(item); s.commit(); s.refresh(item)
        achado = estoque_baixa.resolver_item(s, fazenda_id=1, estoque_id=item.id)
        assert achado is not None and achado.id == item.id

    def test_estoque_id_de_outra_fazenda_cai_no_fallback_por_nome(self, bare_session):
        """Garantia central de isolamento: um estoque_id de outra fazenda
        NUNCA é usado diretamente — cai para a busca por nome dentro da
        própria fazenda."""
        s = bare_session
        alheio = Estoque(fazenda_id=2, nome="Sincrocp", quantidade=999, unidade="ml")
        proprio = Estoque(fazenda_id=1, nome="Sincrocp", quantidade=50, unidade="ml")
        s.add(alheio); s.add(proprio); s.commit(); s.refresh(alheio); s.refresh(proprio)

        achado = estoque_baixa.resolver_item(s, fazenda_id=1, produto="Sincrocp", estoque_id=alheio.id)
        assert achado is not None and achado.id == proprio.id

    def test_estoque_id_de_outra_fazenda_sem_nome_correspondente_nao_acha_nada(self, bare_session):
        """Sem item na própria fazenda com o mesmo nome, o id alheio não vira
        um jeito indireto de acessar o estoque de outra fazenda — resolve None."""
        s = bare_session
        alheio = Estoque(fazenda_id=2, nome="Sincrocp", quantidade=999, unidade="ml")
        s.add(alheio); s.commit(); s.refresh(alheio)

        achado = estoque_baixa.resolver_item(s, fazenda_id=1, produto="Sincrocp", estoque_id=alheio.id)
        assert achado is None

    def test_por_nome_filtra_pela_fazenda(self, bare_session):
        s = bare_session
        de_outra = Estoque(fazenda_id=2, nome="Detergente", quantidade=10, unidade="L")
        da_minha = Estoque(fazenda_id=1, nome="Detergente", quantidade=20, unidade="L")
        s.add(de_outra); s.add(da_minha); s.commit(); s.refresh(da_minha)
        achado = estoque_baixa.resolver_item(s, fazenda_id=1, produto="Detergente")
        assert achado is not None and achado.id == da_minha.id


class TestOpcoesMedicamentoRespeitaFazenda:
    def test_so_lista_frascos_da_propria_fazenda(self, bare_session):
        s = bare_session
        from fazenda.models import PrincipioAtivo
        pa1 = PrincipioAtivo(nome="Cloprostenol", fazenda_id=1)
        s.add(pa1); s.commit(); s.refresh(pa1)
        s.add(Estoque(fazenda_id=1, nome="Sincrocp", quantidade=50, unidade="ml", principio_ativo_id=pa1.id))
        s.add(Estoque(fazenda_id=2, nome="Croniben", quantidade=50, unidade="ml", principio_ativo_id=pa1.id))
        s.commit()

        _, opcoes = estoque_baixa.opcoes_medicamento(s, fazenda_id=1, produto="Sincrocp")
        assert {o["nome"] for o in opcoes} == {"Sincrocp"}, "não pode listar frasco de outra fazenda"


class TestMovimentarQuantidadeExata:
    def test_abate_exatamente_sinal_vezes_quantidade(self, bare_session):
        s = bare_session
        item = Estoque(fazenda_id=1, nome="X", quantidade=50, unidade="ml")
        s.add(item); s.commit(); s.refresh(item)
        avisos = estoque_baixa.baixar(
            s, item=item, quantidade=6, unidade="ml", data=date.today(), fazenda_id=1,
            observacao="teste", origem_tipo="iatf", origem_id=1,
        )
        s.commit()
        assert avisos == []
        assert item.quantidade == 44

    def test_baixar_e_devolver_a_mesma_quantidade_volta_ao_original(self, bare_session):
        s = bare_session
        item = Estoque(fazenda_id=1, nome="X", quantidade=50, unidade="ml")
        s.add(item); s.commit(); s.refresh(item)
        estoque_baixa.baixar(
            s, item=item, quantidade=10, unidade="ml", data=date.today(), fazenda_id=1,
            observacao="baixa", origem_tipo="iatf", origem_id=1,
        )
        s.commit()
        estoque_baixa.devolver(
            s, item=item, quantidade=10, unidade="ml", data=date.today(), fazenda_id=1,
            observacao="estorno", origem_tipo="iatf", origem_id=1,
        )
        s.commit()
        assert item.quantidade == 50


class TestPortoesDeMovimentar:
    """Portões de movimentar(), na ordem em que o código os aplica — todos
    retornam ANTES de criar qualquer MovimentoEstoque (verificado em cada
    caso)."""

    def test_item_none_avisa_e_nao_quebra(self, bare_session):
        s = bare_session
        avisos = estoque_baixa.baixar(
            s, item=None, quantidade=5, unidade="ml", data=date.today(), fazenda_id=1,
            observacao="x", produto="Fantasma",
        )
        assert avisos and "não está no estoque" in avisos[0]
        assert s.exec(select(MovimentoEstoque)).all() == []

    def test_item_nao_estocavel_nao_mexe_sem_aviso(self, bare_session):
        s = bare_session
        item = Estoque(fazenda_id=1, nome="Serviço", quantidade=100, unidade="unidade", estocavel=False)
        s.add(item); s.commit(); s.refresh(item)
        avisos = estoque_baixa.baixar(
            s, item=item, quantidade=3, unidade="unidade", data=date.today(), fazenda_id=1, observacao="x",
        )
        s.commit()
        assert avisos == []
        assert item.quantidade == 100
        assert s.exec(select(MovimentoEstoque)).all() == []

    def test_estoque_nao_inicializado_avisa_e_nao_abate(self, bare_session):
        s = bare_session
        item = Estoque(fazenda_id=1, nome="Novo", quantidade=0, unidade="ml", estoque_inicializado=False)
        s.add(item); s.commit(); s.refresh(item)
        avisos = estoque_baixa.baixar(
            s, item=item, quantidade=3, unidade="ml", data=date.today(), fazenda_id=1, observacao="x",
        )
        s.commit()
        assert avisos
        assert item.quantidade == 0
        assert s.exec(select(MovimentoEstoque)).all() == []

    def test_unidade_incompativel_avisa_e_nao_abate(self, bare_session):
        s = bare_session
        item = Estoque(fazenda_id=1, nome="Ração", quantidade=200, unidade="kg")
        s.add(item); s.commit(); s.refresh(item)
        avisos = estoque_baixa.baixar(
            s, item=item, quantidade=3, unidade="ml", data=date.today(), fazenda_id=1, observacao="x",
        )
        s.commit()
        assert avisos
        assert item.quantidade == 200
        assert s.exec(select(MovimentoEstoque)).all() == []

    def test_saldo_insuficiente_abate_mesmo_assim_e_so_avisa(self, bare_session):
        """Decisão de produto: negativo só avisa, nunca bloqueia."""
        s = bare_session
        item = Estoque(fazenda_id=1, nome="Escasso", quantidade=1, unidade="ml")
        s.add(item); s.commit(); s.refresh(item)
        avisos = estoque_baixa.baixar(
            s, item=item, quantidade=5, unidade="ml", data=date.today(), fazenda_id=1, observacao="x",
        )
        s.commit()
        assert item.quantidade == -4
        assert avisos and "negativo" in avisos[0]
        # A baixa aconteceu de verdade — não é só o aviso sem efeito.
        assert s.exec(select(MovimentoEstoque)).one().quantidade == 5


class TestRastroDoMovimento:
    def test_grava_origem_estoque_id_e_fazenda_id(self, bare_session):
        s = bare_session
        item = Estoque(fazenda_id=1, nome="X", quantidade=50, unidade="ml")
        s.add(item); s.commit(); s.refresh(item)
        estoque_baixa.baixar(
            s, item=item, quantidade=6, unidade="ml", data=date.today(), fazenda_id=1,
            observacao="teste", origem_tipo="iatf", origem_id=42,
        )
        s.commit()
        mov = s.exec(select(MovimentoEstoque)).one()
        assert mov.origem_tipo == "iatf"
        assert mov.origem_id == 42
        assert mov.estoque_id == item.id
        assert mov.fazenda_id == 1


# ═════════════════ B. Quantidade exata via HTTP (IATF/indução) ═════════════

class TestIatfQuantidadeExata:
    def test_abate_dose_vezes_n_vacas_confirmadas(self, client):
        c, engine = client
        _animais(engine, ["700", "701", "702"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        lid = _lancar_iatf(c, ["700", "701", "702"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        r = c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Sincrocp") == 50 - 2 * 3

    def test_baixa_parcial_abate_so_a_fracao_do_subconjunto(self, client):
        c, engine = client
        _animais(engine, ["700", "701", "702"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        lid = _lancar_iatf(c, ["700", "701", "702"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        r = c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0, "animais": ["700", "701"]})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Sincrocp") == 50 - 2 * 2

    def test_dar_baixa_duas_vezes_no_mesmo_dia_nao_abate_duas_vezes(self, client):
        c, engine = client
        _animais(engine, ["700"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        lid = _lancar_iatf(c, ["700"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        r2 = c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        assert r2.status_code == 200, r2.text
        assert _saldo(engine, "Sincrocp") == 48
        with Session(engine) as s:
            assert len(s.exec(select(MovimentoEstoque).where(MovimentoEstoque.nome_item == "Sincrocp")).all()) == 1

    def test_dois_hormonios_no_mesmo_dia_cada_um_abate_o_seu(self, client):
        """Dois medicamentos cadastrados no mesmo D0 não podem se multiplicar
        um pelo outro (nº de vacas x nº de medicamentos por engano)."""
        c, engine = client
        _animais(engine, ["700", "701"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        _estoque(engine, nome="Folltropin", quantidade=30, unidade="ml")
        lid = _lancar_iatf(c, ["700", "701"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
            {"dia": 0, "produto": "Folltropin", "dose": 1, "unidade": "ml", "via": "Intramuscular"},
        ])
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        assert _saldo(engine, "Sincrocp") == 50 - 2 * 2
        assert _saldo(engine, "Folltropin") == 30 - 1 * 2


class TestInducaoQuantidadeExata:
    def _protocolo(self, c, dose=1.0, unidade="ml"):
        return _cadastrar_inducao(c, etapas=[
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": dose, "unidade": unidade},
        ])

    def test_abate_dose_vezes_n_vacas_confirmadas(self, client):
        c, engine = client
        pid = self._protocolo(c, dose=1.5)
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        lid = _lancar_inducao(c, pid, ["700", "701", "702"], date.today())
        r = c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Benzoato de estradiol") == 50 - 1.5 * 3

    def test_baixa_duas_vezes_nao_abate_duas_vezes(self, client):
        c, engine = client
        pid = self._protocolo(c)
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        lid = _lancar_inducao(c, pid, ["700"], date.today())
        c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0})
        c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0})
        assert _saldo(engine, "Benzoato de estradiol") == 49


# ═══════════════════ C. Frasco explícito e isolamento ═══════════════════════

class TestFrascoExplicitoAbateOEscolhido:
    def test_medicamentos_explicito_abate_o_frasco_e_nao_o_hormonio_cadastrado(self, client):
        c, engine = client
        _animais(engine, ["700"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        croniben_id = _estoque(engine, nome="Croniben", quantidade=30, unidade="ml")
        lid = _lancar_iatf(c, ["700"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        r = c.post(f"/central-protocolos/iatf/{lid}/baixa", json={
            "dia": 0,
            "medicamentos": [{"produto": "Croniben", "estoque_id": croniben_id, "dose": 2, "unidade": "ml", "via": "IM"}],
        })
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Croniben") == 28
        assert _saldo(engine, "Sincrocp") == 50, "o hormônio cadastrado no lançamento não pode ser tocado"


class TestIsolamentoEntreFazendas:
    def test_baixa_com_estoque_id_de_outra_fazenda_nao_abate_o_alheio(self, client):
        """`estoque_id` explícito de outro tenant nunca pode virar baixa
        cross-fazenda — nem quando vem digitado à mão num payload de baixa."""
        c, engine = client
        _animais(engine, ["700"])
        alheio_id = _estoque(engine, fazenda_id=2, nome="Sincrocp", quantidade=999, unidade="ml")
        lid = _lancar_iatf(c, ["700"], date.today())  # sem hormônio cadastrado (ad-hoc)
        r = c.post(f"/central-protocolos/iatf/{lid}/baixa", json={
            "dia": 0,
            "medicamentos": [{"produto": "Sincrocp", "estoque_id": alheio_id, "dose": 2, "unidade": "ml", "via": "IM"}],
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(Estoque, alheio_id).quantidade == 999


# ══════════════════════════ D. Estorno exato ════════════════════════════════

class TestDesfazerAplicacaoIatf:
    def test_desfazer_todas_uma_a_uma_devolve_ao_saldo_inicial(self, client):
        c, engine = client
        _animais(engine, ["700", "701", "702"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        lid = _lancar_iatf(c, ["700", "701", "702"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        assert _saldo(engine, "Sincrocp") == 50 - 2 * 3

        for numero in ("700", "701", "702"):
            r = c.request("DELETE", f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0, "numero_matriz": numero})
            assert r.status_code == 200, r.text
        assert _saldo(engine, "Sincrocp") == 50


class TestCancelarEstornoExato:
    def test_iatf_estorna_exatamente_o_consumido(self, client):
        c, engine = client
        _animais(engine, ["700", "701"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        lid = _lancar_iatf(c, ["700", "701"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        assert _saldo(engine, "Sincrocp") == 46

        r = c.post(f"/central-protocolos/iatf/{lid}/cancelar", json={"motivo": "teste"})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Sincrocp") == 50

    def test_inducao_estorna_exatamente_o_consumido(self, client):
        c, engine = client
        pid = _cadastrar_inducao(c, etapas=[
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
        ])
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        lid = _lancar_inducao(c, pid, ["700", "701"], date.today())
        c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0})
        assert _saldo(engine, "Benzoato de estradiol") == 48

        r = c.post(f"/central-protocolos/inducao/{lid}/cancelar", json={"motivo": "teste"})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Benzoato de estradiol") == 50


class TestLidaBaixaEEstorno:
    def test_baixa_abate_dose_vezes_aplicacoes_confirmadas(self, client):
        c, engine = client
        _estoque(engine, nome="Detergente para cochos", quantidade=20, unidade="L")
        molde = _cadastrar_lida_frequencia(c, dose=0.5, unidade="L", insumo="Detergente para cochos")
        lanc = _lancar_lida(c, molde, "2026-08-01", animais=["700", "701"])
        r = c.post(f"/central-protocolos/lida/{lanc}/baixa", json={"dia": 0})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Detergente para cochos") == 19

    def test_baixa_duas_vezes_nao_abate_duas_vezes(self, client):
        c, engine = client
        _estoque(engine, nome="Detergente para cochos", quantidade=20, unidade="L")
        molde = _cadastrar_lida_frequencia(c, dose=0.5, unidade="L", insumo="Detergente para cochos")
        lanc = _lancar_lida(c, molde, "2026-08-01")
        c.post(f"/central-protocolos/lida/{lanc}/baixa", json={"dia": 0})
        c.post(f"/central-protocolos/lida/{lanc}/baixa", json={"dia": 0})
        assert _saldo(engine, "Detergente para cochos") == 19.5

    def test_dar_baixa_estoque_false_nao_abate_nada(self, client):
        c, engine = client
        _estoque(engine, nome="Detergente para cochos", quantidade=20, unidade="L")
        molde = _cadastrar_lida_frequencia(c, dose=0.5, unidade="L", insumo="Detergente para cochos", dar_baixa=False)
        lanc = _lancar_lida(c, molde, "2026-08-01")
        r = c.post(f"/central-protocolos/lida/{lanc}/baixa", json={"dia": 0})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Detergente para cochos") == 20
        with Session(engine) as s:
            assert s.exec(select(MovimentoEstoque)).all() == []

    def test_confirmacoes_parciais_e_cancelar_devolve_ao_saldo_inicial(self, client):
        """Duas confirmações parciais (subconjuntos de animais) do mesmo dia
        somam certo, e cancelar o lançamento devolve tudo — não só a última
        fração."""
        c, engine = client
        _estoque(engine, nome="Detergente para cochos", quantidade=20, unidade="L")
        molde = _cadastrar_lida_frequencia(c, dose=0.5, unidade="L", insumo="Detergente para cochos")
        lanc = _lancar_lida(c, molde, "2026-08-01", animais=["700", "701"])
        c.post(f"/central-protocolos/lida/{lanc}/baixa", json={"dia": 0, "animais": ["700"]})
        c.post(f"/central-protocolos/lida/{lanc}/baixa", json={"dia": 0, "animais": ["701"]})
        assert _saldo(engine, "Detergente para cochos") == 19

        r = c.post(f"/central-protocolos/lida/{lanc}/cancelar", json={"motivo": "teste"})
        assert r.status_code == 200, r.text
        assert _saldo(engine, "Detergente para cochos") == 20


# ══════════════════════════════ E. Sanidade ═════════════════════════════════

class TestSanidadeIatf:
    def test_uma_sanidade_por_animal_vezes_medicamento(self, client):
        c, engine = client
        _animais(engine, ["700", "701"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        _estoque(engine, nome="Folltropin", quantidade=50, unidade="ml")
        lid = _lancar_iatf(c, ["700", "701"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
            {"dia": 0, "produto": "Folltropin", "dose": 1, "unidade": "ml", "via": "Intramuscular"},
        ])
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        with Session(engine) as s:
            sans = s.exec(select(Sanidade)).all()
            # 2 animais x 2 medicamentos = 4 linhas.
            assert len(sans) == 4
            assert all(sa.protocolo_iatf_lancamento_id == lid for sa in sans)

    def test_data_aplicacao_e_a_data_real_nao_hoje(self, client):
        c, engine = client
        _animais(engine, ["700"])
        _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        d0 = date.today() - timedelta(days=21)
        lid = _lancar_iatf(c, ["700"], d0, hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0, "data_realizacao": d0.isoformat()})
        with Session(engine) as s:
            san = s.exec(select(Sanidade)).one()
            assert san.data_aplicacao == d0


class TestSanidadeInducao:
    def _protocolo(self, c):
        return _cadastrar_inducao(c, etapas=[
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
        ])

    def test_gera_uma_sanidade_por_animal(self, client):
        c, engine = client
        pid = self._protocolo(c)
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        lid = _lancar_inducao(c, pid, ["700", "701"], date.today())
        c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0})
        with Session(engine) as s:
            sans = s.exec(select(Sanidade)).all()
            assert len(sans) == 2
            # Vínculo relacional com o lançamento que gerou a aplicação — não
            # só o texto livre em obs (ver protocolo_inducao_lancamento_id).
            assert all(sa.protocolo_inducao_lancamento_id == lid for sa in sans)

    def test_data_aplicacao_e_a_data_real_nao_hoje(self, client):
        c, engine = client
        pid = self._protocolo(c)
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        d0 = date.today() - timedelta(days=10)
        lid = _lancar_inducao(c, pid, ["700"], d0)
        c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0, "data_realizacao": d0.isoformat()})
        with Session(engine) as s:
            san = s.exec(select(Sanidade)).one()
            # Baixa retroativa: data REAL da aplicação (não "hoje") e o
            # vínculo relacional gravados juntos, na mesma linha.
            assert san.data_aplicacao == d0
            assert san.protocolo_inducao_lancamento_id == lid

    def test_etapa_de_manejo_sem_medicamento_nao_gera_sanidade(self, client):
        """Etapa de manejo/dispositivo (ex.: colocar implante, adaptação na
        ordenha) não tem medicamento — não pode gerar Sanidade nenhuma.
        Comportamento pré-existente, preservado pela adição do vínculo."""
        c, engine = client
        pid = _cadastrar_inducao(c, etapas=[
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
            {"dia": 1, "tipo": "manejo", "produto": "Adaptação na ordenha"},
        ])
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        lid = _lancar_inducao(c, pid, ["700"], date.today())

        r = c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 1})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            sans = s.exec(select(Sanidade)).all()
            assert sans == [], "etapa de manejo sem medicamento não pode gerar Sanidade"

    def test_cancelar_nao_apaga_sanidade(self, client):
        c, engine = client
        pid = self._protocolo(c)
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        lid = _lancar_inducao(c, pid, ["700"], date.today())
        c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0})
        with Session(engine) as s:
            sans_antes = s.exec(select(Sanidade)).all()
            antes = len(sans_antes)
            assert all(sa.protocolo_inducao_lancamento_id == lid for sa in sans_antes)
        assert antes == 1

        c.post(f"/central-protocolos/inducao/{lid}/cancelar", json={"motivo": "teste"})
        with Session(engine) as s:
            sans_depois = s.exec(select(Sanidade)).all()
            depois = len(sans_depois)
        assert depois == antes, "a Sanidade da aplicação não pode sumir da ficha ao cancelar"
        # Cancelar é o estorno do estoque/agenda — não apaga o registro
        # clínico nem desfaz o vínculo relacional dele com o lançamento.
        assert all(sa.protocolo_inducao_lancamento_id == lid for sa in sans_depois), (
            "cancelar não pode zerar o vínculo relacional da Sanidade — é o registro clínico"
        )


class TestSanidadeInducaoComVinculoAoLancamento:
    """IATF grava `Sanidade.protocolo_iatf_lancamento_id` (agenda.py ~1367).
    Indução gera a mesma Sanidade por animal x medicamento (agenda.py
    ~1481) e agora grava o equivalente `protocolo_inducao_lancamento_id` —
    vínculo relacional com o `ProtocoloInducaoLancamento` que originou a
    aplicação, além do texto livre em `obs` ("Indução de lactação — D{dia}"),
    que continua existindo (é lido em outras telas). Era um bug confirmado
    por auditoria, coberto por um xfail (test_protocolos_estoque.py — este
    teste) até a correção do modelo/agenda.py nesta mudança."""

    def test_sanidade_da_inducao_tem_vinculo_relacional_ao_lancamento(self, client):
        c, engine = client
        pid = _cadastrar_inducao(c, etapas=[
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
        ])
        _estoque(engine, nome="Benzoato de estradiol", quantidade=50, unidade="ml")
        lid = _lancar_inducao(c, pid, ["700"], date.today())
        c.post(f"/central-protocolos/inducao/{lid}/baixa", json={"dia": 0})
        with Session(engine) as s:
            san = s.exec(select(Sanidade)).one()
            vinculo = getattr(san, "protocolo_inducao_lancamento_id", None)
            assert vinculo == lid


# ════════════════════════ F. Bugs confirmados (fora do escopo) ═════════════

class TestBugCancelarDuasVezesInflaSaldo:
    """`cancelar()` (fazenda/api/routers/central_protocolos.py, linhas
    ~677-689) estorna toda linha de MovimentoEstoque(origem_tipo=origem,
    origem_id=origem_id, movimento=="Aplicação") — mas NÃO marca essa linha
    como "já estornada" nem verifica `lancamento.ativo`/`encerrado_em` antes
    de rodar. Uma segunda chamada a POST .../cancelar no MESMO lançamento
    encontra a MESMA linha "Aplicação" (ela nunca é apagada nem sinalizada)
    e devolve o estoque de novo — infla o saldo a cada clique repetido.

    Reproduzido e CONFIRMADO nesta auditoria (rodando a sequência baixa →
    cancelar → cancelar num engine isolado): saldo inicial 100, após baixa de
    2ml vai a 98, primeiro cancelar volta a 100 (correto), segundo cancelar
    vai a 102 (bug — deveria permanecer 100).

    O teste equivalente na suíte já existente
    (tests/test_protocolos_baixa_retroativa.py::TestCancelar::
    test_cancelar_duas_vezes_nao_infla_o_estoque) não pega o bug porque o
    lançamento usado ali (`_com_estoque`) não cadastra hormônio nenhum
    (`_lancar_iatf(c, animais, data_d0)` sem `hormonios=`) — a baixa nunca
    sai do zero, e a asserção fica dentro de um
    `if saldo_apos_baixa < saldo_inicial:` que nunca é satisfeito. Ou seja: a
    suíte atual tem uma falsa cobertura desse ponto — passa sem exercitar o
    caminho que importa.

    Fora do meu escopo de correção: central_protocolos.py é propriedade
    exclusiva de outro agente desta auditoria."""

    def test_cancelar_duas_vezes_infla_o_saldo_iatf(self, client):
        c, engine = client
        _animais(engine, ["700"])
        _estoque(engine, nome="Sincrocp", quantidade=100, unidade="ml")
        lid = _lancar_iatf(c, ["700"], date.today(), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        assert _saldo(engine, "Sincrocp") == 98

        c.post(f"/central-protocolos/iatf/{lid}/cancelar", json={"motivo": "1a"})
        assert _saldo(engine, "Sincrocp") == 100, "primeiro cancelar deve devolver ao saldo original"

        c.post(f"/central-protocolos/iatf/{lid}/cancelar", json={"motivo": "2a"})
        assert _saldo(engine, "Sincrocp") == 100, "cancelar de novo NÃO pode inflar o saldo — mas infla (bug)"

    def test_cancelar_duas_vezes_infla_o_saldo_lida(self, client):
        c, engine = client
        _estoque(engine, nome="Detergente para cochos", quantidade=20, unidade="L")
        molde = _cadastrar_lida_frequencia(c, dose=0.5, unidade="L", insumo="Detergente para cochos")
        lanc = _lancar_lida(c, molde, "2026-08-01")
        c.post(f"/central-protocolos/lida/{lanc}/baixa", json={"dia": 0})
        assert _saldo(engine, "Detergente para cochos") == 19.5

        c.post(f"/central-protocolos/lida/{lanc}/cancelar", json={"motivo": "1a"})
        assert _saldo(engine, "Detergente para cochos") == 20

        c.post(f"/central-protocolos/lida/{lanc}/cancelar", json={"motivo": "2a"})
        assert _saldo(engine, "Detergente para cochos") == 20, "cancelar de novo não pode inflar (bug)"


class TestGrupoMultiLancamentoRateiaBaixaPorLancamento:
    """O evento agrupado da Agenda (mesma data_prevista, mesmo dia) pode
    reunir animais de MAIS DE UM ProtocoloIatfLancamento (dois lotes com o
    mesmo D0 — ver docstring de `_marcar_protocolo_iatf_realizado`,
    agenda.py ~1283). Quando o usuário escolhe o frasco explicitamente
    (`medicamentos`) ao confirmar esse grupo, agenda.py agora emite UMA
    baixa POR LANÇAMENTO (origem_id = lancamento_id, quantidade = dose × nº
    de vacas daquele lançamento) em vez de um bloco único com origem_id=None
    — que deixava `cancelar()` (central_protocolos.py) incapaz de achar o
    que estornar, já que ele filtra por origem_id do lançamento específico."""

    def test_cancelar_um_lote_do_grupo_estorna_a_fracao_dele(self, client):
        c, engine = client
        _animais(engine, ["700", "800"])
        item_id = _estoque(engine, nome="Sincrocp", quantidade=50, unidade="ml")
        d0 = date.today()
        lid_a = _lancar_iatf(c, ["700"], d0)
        lid_b = _lancar_iatf(c, ["800"], d0)

        evento_id = f"protocolo_iatf_{d0.isoformat()}_0"
        r = c.post("/agenda/realizados", json={
            "evento_id": evento_id,
            "medicamentos": [{"produto": "Sincrocp", "estoque_id": item_id, "dose": 2, "unidade": "ml", "via": "IM"}],
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            saldo_apos_baixa = s.get(Estoque, item_id).quantidade
        assert saldo_apos_baixa == 50 - 2 * 2  # 2 vacas, total do grupo continua o mesmo

        movs = None
        with Session(engine) as s:
            movs = s.exec(
                select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "iatf")
            ).all()
        assert len(movs) == 2, "uma baixa por lançamento, não uma só pro grupo"
        assert {m.origem_id for m in movs} == {lid_a, lid_b}
        assert all(m.quantidade == 2 for m in movs)  # 1 vaca cada, dose 2 ml

        c.post(f"/central-protocolos/iatf/{lid_a}/cancelar", json={"motivo": "teste"})
        with Session(engine) as s:
            saldo_apos_cancelar_a = s.get(Estoque, item_id).quantidade
        assert saldo_apos_cancelar_a == saldo_apos_baixa + 2, "cancelar A devolve só a fração dele (2 ml)"

        c.post(f"/central-protocolos/iatf/{lid_b}/cancelar", json={"motivo": "teste"})
        with Session(engine) as s:
            saldo_final = s.get(Estoque, item_id).quantidade
        assert saldo_final == 50, "cancelar B depois fecha no saldo original"

    def test_rateio_proporcional_com_lotes_de_tamanhos_diferentes(self, client):
        c, engine = client
        _animais(engine, ["1", "2", "3", "4"])
        item_id = _estoque(engine, nome="Sincrocp", quantidade=100, unidade="ml")
        d0 = date.today()
        lid_a = _lancar_iatf(c, ["1", "2", "3"], d0)  # 3 vacas
        lid_b = _lancar_iatf(c, ["4"], d0)  # 1 vaca

        evento_id = f"protocolo_iatf_{d0.isoformat()}_0"
        r = c.post("/agenda/realizados", json={
            "evento_id": evento_id,
            "medicamentos": [{"produto": "Sincrocp", "estoque_id": item_id, "dose": 2, "unidade": "ml", "via": "IM"}],
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            saldo_apos_baixa = s.get(Estoque, item_id).quantidade
        assert saldo_apos_baixa == 100 - 2 * 4  # dose 2 ml x 4 vacas no total, igual a antes

        with Session(engine) as s:
            movs = {
                m.origem_id: m.quantidade
                for m in s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "iatf")).all()
            }
        assert movs == {lid_a: 6, lid_b: 2}  # 3 vacas x 2ml = 6; 1 vaca x 2ml = 2 — rateio exato, sem dízima

        c.post(f"/central-protocolos/iatf/{lid_a}/cancelar", json={"motivo": "teste"})
        with Session(engine) as s:
            assert s.get(Estoque, item_id).quantidade == saldo_apos_baixa + 6

        c.post(f"/central-protocolos/iatf/{lid_b}/cancelar", json={"motivo": "teste"})
        with Session(engine) as s:
            assert s.get(Estoque, item_id).quantidade == 100

    def test_avisos_nao_duplicam_por_lancamento(self, client):
        c, engine = client
        _animais(engine, ["700", "800"])
        # Nenhum item "Sincrocp" cadastrado no estoque -> resolver_item devolve
        # None -> o mesmo aviso de "não está no estoque" seria emitido uma vez
        # por lançamento do grupo se não houvesse dedup.
        d0 = date.today()
        _lancar_iatf(c, ["700"], d0)
        _lancar_iatf(c, ["800"], d0)

        evento_id = f"protocolo_iatf_{d0.isoformat()}_0"
        r = c.post("/agenda/realizados", json={
            "evento_id": evento_id,
            "medicamentos": [{"produto": "Sincrocp", "estoque_id": None, "dose": 2, "unidade": "ml", "via": "IM"}],
        })
        assert r.status_code == 200, r.text
        avisos = r.json()["avisos"]
        assert len(avisos) == len(set(avisos)), f"avisos duplicados: {avisos}"
        assert any("não está no estoque" in a for a in avisos)
        assert sum("não está no estoque" in a for a in avisos) == 1
