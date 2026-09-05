"""
Testes de regressão de um subconjunto dos achados P2 da auditoria de
segurança de 02/09/2026 (docs/security-audit/achados.json) — cobre o item
mais arriscado de mudar (a checagem de posse que tolerava fazenda_id=None) e
alguns dos vazamentos/gaps pontuais mais fáceis de verificar isoladamente.
Os demais itens de e-mail/autoescape já são cobertos pelas suítes existentes
(test_financeiro.py, test_agenda_veterinario.py, test_esqueci_senha.py) e por
verificação manual (contrato_render.py); o item do cofre_acesso já ganhou
teste dedicado em test_cowdata_modo_suporte.py.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaCorrente, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, Touro
from fazenda.models.estoque import EstoqueSemen
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.models.sanidade import Sanidade


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda A"))
        s.add(Fazenda(id=2, nome="Fazenda B"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        s.add(Pessoa(id=1, nome="Funcionário da Fazenda A", tipo="Funcionário", fazenda_id=1))
        s.add(EstoqueSemen(touro_nome="Touro Sigiloso", tipo="convencional", doses=10, fazenda_id=1))
        s.add(Sanidade(numero_matriz="A1", data_aplicacao=date(2026, 5, 1), produto="X", fazenda_id=1))
        s.add(ContaCorrente(banco="Banco A", agencia="0001", numero_conta="12345-6", fazenda_id=1))
        s.add(ContaGerencial(
            tipo="despesa", valor_total=100.0, data_competencia=date(2026, 1, 15),
            data_emissao=date(2026, 1, 15), numero_lancamento="LC-2026-00001",
            fornecedor_cliente="Fornecedor A", fazenda_id=1,
        ))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "admin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestOwnershipNaoToleraFazendaIdNulo:
    """Item 2: a checagem `fazenda_id is not None and obj.fazenda_id !=
    fazenda_id` liberava qualquer objeto de qualquer fazenda quando o
    CHAMADOR não tinha fazenda selecionada (fazenda_id=None) — cenário real
    de um token sem "fid" (Painel CowData, sessão legada). Corrigido para
    `obj.fazenda_id != fazenda_id`, que nega sempre que os dois lados não
    batem (inclusive um dos lados None e o outro não)."""

    def test_chamador_sem_fazenda_nao_edita_pessoa_de_fazenda_especifica(self, client):
        # A recusa continua sendo o ponto do teste, mas agora vem ANTES da
        # checagem de posse: a trava de tenant (fazenda/auth.py::
        # exigir_fazenda_selecionada) barra na porta do router, com 409, toda
        # requisição sem fazenda no token quando existe fazenda cadastrada —
        # este chamador nem chega mais ao `PUT` que o achado 2 endurecia.
        # Recusa mais cedo e mais forte, não mais fraca: o 404 de posse virou
        # inalcançável por este caminho, então o que se afirma aqui é o 409 —
        # e, abaixo, que a pessoa da Fazenda A segue intocada.
        c, engine = client
        _como_fazenda(None)
        r = c.put("/cadastro/pessoas/1", json={"nome": "Nome Trocado", "tipos": ["Funcionário"]})
        assert r.status_code == 409
        with Session(engine) as s:
            assert s.get(Pessoa, 1).nome == "Funcionário da Fazenda A"

    def test_chamador_de_outra_fazenda_nao_edita_pessoa_da_fazenda_a(self, client):
        """A comparação de posse em si (achado 2) — como a trava de tenant
        tornou o caso "chamador sem fazenda" inalcançável na rota, é este
        cenário (chamador COM fazenda, dado de OUTRA) que continua exercitando
        `obj.fazenda_id != fazenda_id` de verdade."""
        c, engine = client
        _como_fazenda(2)
        r = c.put("/cadastro/pessoas/1", json={"nome": "Nome Trocado", "tipos": ["Funcionário"]})
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(Pessoa, 1).nome == "Funcionário da Fazenda A"

    def test_dono_da_fazenda_continua_editando_sua_propria_pessoa(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.put("/cadastro/pessoas/1", json={"nome": "Nome Corrigido", "tipos": ["Funcionário"]})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(Pessoa, 1).nome == "Nome Corrigido"


class TestEstoqueSemenNaoVazaEntreFazendas:
    """Item 3: relatorios.py e nao_conformidades.py devolviam o estoque de
    sêmen (touro/NAAB/doses) de TODAS as fazendas no relatório de manejo."""

    def test_relatorio_manejo_nao_mostra_semen_de_outra_fazenda(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.get("/relatorios/manejo")
        assert r.status_code == 200
        nomes = [s["touro_nome"] for s in r.json().get("semen_touros", r.json().get("semen", []))] if isinstance(r.json(), dict) else []
        assert "Touro Sigiloso" not in str(r.json())


class TestCatalogoTouroExigeAdmin:
    """Item 4: o catálogo global de Touro (sem fazenda_id, compartilhado por
    todas as fazendas) só era protegido pelo módulo genérico "parametros" —
    qualquer operador podia alterar o catálogo visto por todo mundo."""

    def test_operador_nao_cria_touro_no_catalogo_global(self, client):
        c, engine = client
        import main
        from fazenda.auth import get_current_user

        class _Operador:
            id = 2
            papel = "operador"
            ativo = True
            username = "operador"
            email = "operador@example.com"
            permissoes = "parametros"

        main.app.dependency_overrides[get_current_user] = lambda: _Operador()
        # Fazenda selecionada de propósito: o que este teste garante é a
        # trava de PAPEL no catálogo global, e sem "fid" a trava de tenant
        # (exigir_fazenda_selecionada) recusaria antes com 409 — o operador
        # seria barrado por ser uma sessão sem fazenda, não por ser operador.
        _como_fazenda(1)
        r = c.post("/cadastro/touros", json={"naab": "007HO99999", "nome": "Touro Invasor"})
        assert r.status_code == 403
        with Session(engine) as s:
            assert s.exec(select(Touro).where(Touro.naab == "007HO99999")).first() is None


class TestCartaoCreditoNaoVinculaContaDeOutraFazenda:
    """Item 7: criar/editar cartão de crédito aceitava conta_bancaria_id de
    QUALQUER fazenda, sem checar se a ContaCorrente pertence a quem está
    chamando."""

    def test_nao_cria_cartao_apontando_para_conta_de_outra_fazenda(self, client):
        c, engine = client
        with Session(engine) as s:
            conta_a = s.exec(select(ContaCorrente).where(ContaCorrente.fazenda_id == 1)).first()
            conta_a_id = conta_a.id
        _como_fazenda(2)
        r = c.post("/financeiro/cartoes", json={
            "apelido": "Cartão B", "conta_bancaria_id": conta_a_id, "dia_fechamento": 10, "dia_vencimento": 17,
        })
        assert r.status_code == 404


class TestChamadoExigeAdmin:
    """Item 8: qualquer usuário autenticado (inclusive operador) podia mudar
    status/resposta de um chamado de suporte."""

    def test_operador_nao_atualiza_status_de_chamado(self, client):
        c, engine = client
        import main
        from fazenda.auth import get_current_user

        _como_fazenda(1)
        r_abrir = c.post("/chamados", json={"assunto": "Dúvida", "descricao": "Preciso de ajuda"})
        assert r_abrir.status_code == 201
        chamado_id = r_abrir.json()["id"]

        class _Operador:
            id = 2
            papel = "operador"
            ativo = True
            username = "operador"
            email = "operador@example.com"
            permissoes = ""

        main.app.dependency_overrides[get_current_user] = lambda: _Operador()
        r = c.put(f"/chamados/{chamado_id}", json={"status": "resolvido"})
        assert r.status_code == 403
