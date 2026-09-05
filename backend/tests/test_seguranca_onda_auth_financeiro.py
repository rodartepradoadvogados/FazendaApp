"""
Onda de segurança em auth.py, financeiro.py e no upload — as 3 ALTAS que
sobraram fora da trava de tenant (fazenda/auth.py::exigir_fazenda_selecionada,
coberta por test_trava_fazenda_selecionada.py).

  F-B-03  GET /financeiro/opcoes devolvia fornecedores/clientes e produtos de
          TODAS as fazendas — e com token NORMAL, não legado: eram os dois
          únicos `select` sem filtro num endpoint em que todos os outros
          filtravam.
  F-A-02  GET /auth/usuarios/acessos (e /auth/usuarios) devolviam o banco
          inteiro quando o token não trazia fazenda.
  F-A-05  POST /upload/{tipo} não exigia o módulo "upload", enquanto o router
          irmão (importar) sempre exigiu — e cada _upsert_* apaga o conjunto
          inteiro antes de inserir.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, LancamentoItem, Pessoa, Usuario,
    UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Vizinha"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # Uma pessoa/usuário em cada fazenda — o vazamento do F-A-02 é
        # justamente a lista de usuários da fazenda vizinha.
        s.add(Pessoa(id=1, nome="Gerente 1", tipo="funcionario", fazenda_id=1))
        s.add(Pessoa(id=2, nome="Gerente 2", tipo="funcionario", fazenda_id=2))
        s.add(Usuario(id=1, username="admin1", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=1))
        s.add(Usuario(id=2, username="admin2", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=2))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=2))
        # Operador da fazenda 1 SEM o módulo "upload" (só a Capa) — F-A-05.
        s.add(Usuario(id=3, username="peao", senha_hash=hash_senha("x"), papel="operador",
                      ativo=True, pessoa_id=1, permissoes="capa"))
        s.add(UsuarioFazenda(usuario_id=3, fazenda_id=1))

        # Dado financeiro de cada fazenda, com fornecedor e produto que só
        # existem lá — é o que o /opcoes vazava.
        s.add(ContaGerencial(id=1, descricao="Ração", valor_total=10.0, fazenda_id=1,
                             fornecedor_cliente="Fornecedor Da Casa", centro_custo="Pecuária Leiteira"))
        s.add(ContaGerencial(id=2, descricao="Ração", valor_total=10.0, fazenda_id=2,
                             fornecedor_cliente="Fornecedor Do Vizinho", centro_custo="Centro Do Vizinho"))
        s.add(LancamentoItem(numero_lancamento="LC-1", produto="Produto Da Casa", quantidade=1.0,
                             valor_unitario=1.0, valor_total=1.0, fazenda_id=1))
        s.add(LancamentoItem(numero_lancamento="LC-2", produto="Produto Do Vizinho", quantidade=1.0,
                             valor_unitario=1.0, valor_total=1.0, fazenda_id=2))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _cab(username, fazenda_id):
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


# --- F-B-03 --------------------------------------------------------------
def test_opcoes_do_financeiro_nao_vaza_carteira_do_vizinho(ambiente):
    r = ambiente.get("/financeiro/opcoes", headers=_cab("admin1", 1))
    assert r.status_code == 200, r.text
    dados = r.json()
    assert "Fornecedor Da Casa" in dados["fornecedores"]
    assert "Fornecedor Do Vizinho" not in dados["fornecedores"], (
        "a carteira de fornecedores/clientes da fazenda vizinha apareceu no autocomplete — "
        "é inteligência comercial de outro cliente do SaaS"
    )
    assert "Produto Da Casa" in dados["produtos"]
    assert "Produto Do Vizinho" not in dados["produtos"], "o catálogo de compras do vizinho vazou"
    assert "Centro Do Vizinho" not in dados["centros_custo"], "os centros de custo do vizinho vazaram"


# --- F-A-02 --------------------------------------------------------------
def test_acessos_recusa_token_sem_fazenda(ambiente):
    r = ambiente.get("/auth/usuarios/acessos", headers=_cab("admin1", None))
    assert r.status_code == 400, (
        "sem fazenda no token a rota devolvia o banco inteiro: username (o identificador de login), "
        f"papel e telemetria de acesso de todos os clientes. Resposta: {r.status_code} {r.text[:200]}"
    )


def test_acessos_com_fazenda_so_mostra_a_propria(ambiente):
    r = ambiente.get("/auth/usuarios/acessos", headers=_cab("admin1", 1))
    assert r.status_code == 200, r.text
    usernames = {u["username"] for u in r.json()}
    assert "admin1" in usernames
    assert "admin2" not in usernames, "o administrador da fazenda 1 enxergou o login da fazenda 2"


# --- F-A-05 --------------------------------------------------------------
def test_upload_exige_o_modulo_upload(ambiente):
    r = ambiente.post(
        "/upload/plano_conta_gerencial",
        headers=_cab("peao", 1),
        files={"file": ("plano.csv", b"codigo,nome\n1,Teste\n", "text/csv")},
    )
    assert r.status_code == 403, (
        "um operador com permissoes='capa' conseguiu subir CSV: os _upsert_* de upload.py APAGAM "
        f"todo o conjunto do escopo antes de inserir. Resposta: {r.status_code} {r.text[:200]}"
    )


def test_upload_continua_liberado_para_quem_tem_o_modulo(ambiente):
    r = ambiente.post(
        "/upload/plano_conta_gerencial",
        headers=_cab("admin1", 1),
        files={"file": ("plano.csv", b"codigo,nome\n1,Teste\n", "text/csv")},
    )
    assert r.status_code != 403, f"a correção barrou quem tem direito de subir: {r.text[:200]}"
