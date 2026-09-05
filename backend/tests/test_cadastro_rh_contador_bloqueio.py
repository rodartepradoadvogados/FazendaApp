"""
Contador (UsuarioFazenda.contador=True) é somente-leitura/exportação em
Financeiro — o mesmo vínculo precisa valer para RH/Folha, montado sob
/cadastro (ver fazenda/api/routers/cadastro/__init__.py e docstring de
UsuarioFazenda em fazenda/models/multitenant.py).

BUG DE SEGURANÇA CORRIGIDO (F-B-07): o include_router de rh_folha/
rh_contratos/rh_vale_item em cadastro/__init__.py só aplicava
exigir_modulo("financeiro")/exigir_modulo_contratado("financeiro") — nunca
`Depends(bloquear_escrita_contador())`, diferente do include_router de
financeiro/cartao_credito/etc. em main.py. Como o Painel do Contador só
funciona com os módulos "parametros"+"financeiro" (a mesma combinação exigida
para acessar RH/Folha), todo contador tinha escrita liberada em férias, 13º,
folha de pagamento, vale e diária — apesar do produto vender esse vínculo como
"só leitura/exportação". Este arquivo prova que o cadeado agora vale aqui:
mesmo padrão de tests/test_arquivo_contador_desbloqueio.py (Cadeado de
Financeiro), adaptado para uma rota de RH/Folha.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

SENHA_CONTADOR = "senha-do-contador-rh-456"


class _FakeUser:
    id = 77
    papel = "operador"
    ativo = True
    username = "contador.rh.teste"
    email = "contador.rh@example.com"
    # Mesma combinação exigida pelo próprio Painel do Contador para enxergar
    # RH/Folha: "parametros" (exigido no include_router de cadastro.router
    # inteiro, main.py) + "financeiro" (exigido no _exige_financeiro de
    # cadastro/__init__.py) — ver justificativa "melhor_ataque" do achado.
    permissoes = "parametros,financeiro"
    senha_hash = hash_senha(SENHA_CONTADOR)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    # `parametros.get_param` (percentual_terco_constitucional_ferias) lê direto
    # de `fazenda.database.engine`, não da sessão injetada — mesmo padrão de
    # tests/test_folha_rh.py.
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(Usuario(
            id=77, username=_FakeUser.username, senha_hash=_FakeUser.senha_hash, papel="operador",
            ativo=True, permissoes=_FakeUser.permissoes,
        ))
        # O vínculo que o achado explora: contador=True nesta fazenda.
        s.add(UsuarioFazenda(usuario_id=77, fazenda_id=1, contador=True))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.add(Pessoa(id=1, nome="Fulano de Tal", tipo="Funcionário", salario_base=3000.0,
                     data_admissao=date(2020, 1, 10), fazenda_id=1))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


def _payload_ferias(**overrides) -> dict:
    base = {
        "pessoa_id": 1,
        "periodo_aquisitivo_inicio": "2025-01-10",
        "periodo_aquisitivo_fim": "2026-01-10",
        "dias_direito": 30,
        "dias_gozados": 30,
        "data_inicio_gozo": "2026-02-01",
        "data_fim_gozo": "2026-03-02",
        "abono_pecuniario_dias": 0,
    }
    base.update(overrides)
    return base


class TestContadorRhFolhaSomenteLeitura:
    def test_leitura_de_ferias_funciona_para_contador(self, client):
        """GET nunca é bloqueado — é a base do Painel do Contador (relatórios)."""
        r = client.get("/cadastro/ferias")
        assert r.status_code == 200

    def test_leitura_de_folha_pagamento_unificada_funciona_para_contador(self, client):
        r = client.get("/cadastro/folha-pagamento-unificada")
        assert r.status_code == 200

    def test_escrita_de_ferias_e_bloqueada_sem_desbloqueio(self, client):
        """O PoC do achado: POST /cadastro/ferias sem cadeado destravado —
        antes da correção isto voltava 200 e criava ContaGerencial de
        verdade; agora tem que ser 403, igual ao que já acontece em
        POST /financeiro/lancamentos/{id}/pagar."""
        r = client.post("/cadastro/ferias", json=_payload_ferias())
        assert r.status_code == 403
        assert "leitura" in r.json()["detail"].lower()

    def test_escrita_de_ferias_e_liberada_com_desbloqueio(self, client):
        """Mesmo cadeado por senha que já protege Financeiro (X-Desbloqueio,
        POST /auth/desbloquear) — RH/Folha usa exatamente o mesmo mecanismo,
        não um novo."""
        token = client.post("/auth/desbloquear", json={"senha": SENHA_CONTADOR}).json()["token_desbloqueio"]
        r = client.post(
            "/cadastro/ferias", json=_payload_ferias(), headers={"X-Desbloqueio": token},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pendente"

    def test_delete_tambem_e_bloqueado_sem_desbloqueio(self, client):
        """Cria a férias já destravado (setup) e confirma que EXCLUIR de
        novo sem token volta a ser bloqueado — o cadeado vale para qualquer
        método de escrita, não só POST."""
        token = client.post("/auth/desbloquear", json={"senha": SENHA_CONTADOR}).json()["token_desbloqueio"]
        criado = client.post(
            "/cadastro/ferias", json=_payload_ferias(), headers={"X-Desbloqueio": token},
        ).json()
        r = client.delete(f"/cadastro/ferias/{criado['id']}")
        assert r.status_code == 403
