"""
CAUSA RAIZ DA AUDITORIA (F-A-01, F-B-01, F-B-02, F-A-03), fechada na porta.

O isolamento entre fazendas-clientes é feito, em centenas de consultas, pelo
padrão tolerante `if fazenda_id is not None: query = query.where(Modelo.
fazenda_id == fazenda_id)` — herdado do piloto de multi-fazenda. Um token SEM
a claim "fid" não restringe nada: ele DESLIGA esse `if` em toda rota de uma
vez, na leitura e na escrita. Três caminhos reais produzem um token assim
(usuário com 2+ fazendas que não escolheu, membro da Equipe CowData, token
legado) — ver fazenda/auth.py::exigir_fazenda_selecionada.

Este arquivo prova a trava com TOKEN DE VERDADE (nada de
`dependency_overrides` no `get_fazenda_atual_id`): é a claim do token que está
em julgamento, então falsificá-la invalidaria o teste.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.auth import criar_token, hash_senha
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario, UsuarioFazenda
from fazenda.models.planos import MODULOS_COMERCIAIS

# Uma amostra deliberadamente espalhada: cada uma destas rotas é montada por
# um caminho DIFERENTE em main.py (_protegido, exigir_modulo("financeiro"),
# exigir_modulo("rebanho"), exigir_modulo("parametros")), então a amostra
# cobre as quatro formas de montagem, não quatro rotas parecidas.
ROTAS_DE_FAZENDA = [
    "/animais/",
    "/financeiro/lancamentos",
    "/movimentacoes/",
    "/cadastro/fornecedores",
]


def _monta(monkeypatch, *, com_fazendas: bool):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        s.add(Usuario(id=1, username="operador", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        if com_fazendas:
            s.add(Fazenda(id=1, nome="Jairo Nasser"))
            s.add(Fazenda(id=2, nome="Fazenda Teste"))
            for fid in (1, 2):
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                s.add(UsuarioFazenda(usuario_id=1, fazenda_id=fid))
                for modulo in MODULOS_COMERCIAIS:
                    s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    return main


@pytest.fixture
def client(monkeypatch):
    main = _monta(monkeypatch, com_fazendas=True)
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


@pytest.fixture
def client_sem_multifazenda(monkeypatch):
    """Ambiente sem NENHUMA fazenda cadastrada — multi-fazenda não
    provisionado (instalação anterior à migração f1a2b3c4d5e6, e a maior
    parte da suíte). A trava tem que ficar de fora, senão quebra tudo que
    não monta cenário multi-fazenda."""
    main = _monta(monkeypatch, com_fazendas=False)
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _cabecalho(fazenda_id):
    return {"Authorization": f"Bearer {criar_token('operador', fazenda_id=fazenda_id)}"}


@pytest.mark.parametrize("rota", ROTAS_DE_FAZENDA)
def test_token_sem_fid_nao_entra_em_rota_de_fazenda(client, rota):
    r = client.get(rota, headers=_cabecalho(None))
    assert r.status_code == 409, (
        f"{rota} aceitou um token sem 'fid'. Nesse estado o filtro por fazenda de TODA consulta "
        f"lá dentro vira no-op e a rota devolve/edita dado de todas as fazendas-clientes. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )


@pytest.mark.parametrize("rota", ROTAS_DE_FAZENDA)
def test_token_com_fid_entra_normalmente(client, rota):
    r = client.get(rota, headers=_cabecalho(1))
    assert r.status_code != 409, f"{rota} recusou um token legítimo, com fazenda escolhida: {r.text[:200]}"


@pytest.mark.parametrize("rota", ROTAS_DE_FAZENDA)
def test_sem_multifazenda_provisionado_a_trava_nao_atrapalha(client_sem_multifazenda, rota):
    r = client_sem_multifazenda.get(rota, headers=_cabecalho(None))
    assert r.status_code != 409, (
        f"{rota} recusou por falta de fazenda selecionada num banco SEM nenhuma fazenda cadastrada — "
        f"aí não há tenant a isolar, e a trava tem que sair da frente (mesma escape hatch de "
        f"resolver_fazenda_id_escrita). Resposta: {r.status_code} {r.text[:200]}"
    )
