"""
Usuário sem fazenda nenhuma: a mensagem deixa de mandá-lo a um lugar que não
existe.

Regra do dono, e é regra de negócio, não detalhe de tela: o vínculo entre
usuário e fazenda é criado pela CowData, e só por ela — cria a fazenda,
cadastra a pessoa nela, e liga o usuário a essa pessoa. Quem não tem vínculo
não resolve sozinho, então tem que ser mandado ao suporte.

O QUE ACONTECIA. A trava de porta (`auth.py::exigir_fazenda_selecionada`)
tratava duas situações como uma só e respondia às duas com:

    "Sua sessão não tem uma fazenda selecionada. Saia e entre novamente para
     escolher em qual fazenda deseja trabalhar."

Para quem tem duas fazendas e ainda não escolheu, a frase está certa. Para
quem não tem nenhuma, ela é um laço: a pessoa sai, entra, e a tela de escolha
vem vazia — sem nada que indique que é preciso falar com alguém.

TRÊS CAMINHOS, e o teste separa os três porque a diferença entre eles é o
ponto:

  1. sem fazenda nenhuma      → mensagem do suporte, SEM o cabeçalho que
                                redireciona para /escolher-conta;
  2. com fazendas, sem escolher → mensagem de sempre, COM o cabeçalho;
  3. Equipe CowData sem fazenda → mensagem de sempre. Ela legitimamente não
                                tem vínculo e entra pelo Cofre de acesso;
                                mandá-la ao suporte seria mandá-la a si mesma.

O cabeçalho importa tanto quanto o texto: é ele que o `authFetch`
(frontend/lib/api.ts) usa para decidir o redirecionamento. Mandar a mensagem
certa com o cabeçalho errado devolveria a pessoa ao mesmo laço, agora com
outra frase.
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
    ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

# Rota qualquer que passe pela trava de porta — o que se mede é a recusa, não
# o que a rota faria depois dela.
ROTA = "/animais/"


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
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        # (1) o caso desta correção: conta criada, nenhum vínculo
        s.add(Usuario(
            id=10, username="sem_fazenda", senha_hash=hash_senha("x"), papel="admin", ativo=True,
        ))

        # (2) tem duas fazendas e não escolheu: quem a tela de escolha atende
        s.add(Usuario(
            id=11, username="com_duas", senha_hash=hash_senha("x"), papel="admin", ativo=True,
        ))
        s.add(UsuarioFazenda(usuario_id=11, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=11, fazenda_id=2))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _cab(username: str):
    """Token real, sem `fid` — que é o estado dos três casos testados."""
    return {"Authorization": f"Bearer {criar_token(username)}"}


def test_sem_fazenda_nenhuma_manda_ao_suporte(ambiente):
    c, _ = ambiente
    r = c.get(ROTA, headers=_cab("sem_fazenda"))

    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"
    detalhe = r.json()["detail"]
    assert "suporte da CowData" in detalhe, detalhe
    assert "Saia e entre novamente" not in detalhe, (
        "esta pessoa não tem o que escolher — mandá-la sair e entrar é um laço"
    )


def test_sem_fazenda_nenhuma_nao_e_mandado_para_a_tela_de_escolha(ambiente):
    """O cabeçalho decide o redirecionamento no frontend (authFetch, em
    lib/api.ts). Com ele, a pessoa cairia na tela de escolha — vazia."""
    c, _ = ambiente
    r = c.get(ROTA, headers=_cab("sem_fazenda"))

    assert r.headers.get("X-Fazenda-Nao-Selecionada") is None, (
        "com este cabeçalho o frontend redireciona para /escolher-conta"
    )
    assert r.headers.get("X-Conta-Sem-Fazenda") == "1"


def test_quem_tem_fazenda_e_so_nao_escolheu_continua_indo_escolher(ambiente):
    """A correção não pode ter estragado o caso que já funcionava — e é o
    caso comum."""
    c, _ = ambiente
    r = c.get(ROTA, headers=_cab("com_duas"))

    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"
    detalhe = r.json()["detail"]
    assert "Saia e entre novamente" in detalhe, detalhe
    assert "suporte" not in detalhe.lower(), (
        "esta pessoa resolve sozinha: ela tem fazendas para escolher"
    )
    assert r.headers.get("X-Fazenda-Nao-Selecionada") == "1"


def test_equipe_cowdata_sem_vinculo_nao_e_mandada_ao_suporte(ambiente, monkeypatch):
    """Ela não tem fazenda vinculada por desenho, e entra pelo Cofre de
    acesso. Mandá-la ao suporte da CowData seria mandá-la a si mesma."""
    import fazenda.auth as auth

    monkeypatch.setattr(auth, "eh_membro_equipe_cowdata", lambda session, user: True)

    c, _ = ambiente
    r = c.get(ROTA, headers=_cab("sem_fazenda"))

    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"
    assert "suporte" not in r.json()["detail"].lower()
