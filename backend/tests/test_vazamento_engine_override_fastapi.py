"""
CONTROLE POSITIVO da faxina de `tests/conftest.py::limpar_caches_dependencia_fastapi`.

O `pytest -n auto` derrubava workers com "node down: Not properly terminated"
(OOM killer) e o xdist reportava o teste em voo como falho — um teste íntegro,
que passa sozinho e no `--lf` seguinte. A causa não era teste nenhum: era
memória. `fastapi.dependencies.models` memoriza a classificação de cada
callable em três `@lru_cache(maxsize=4096)` chaveados por `_CallIdentity`, que
guarda referência FORTE ao callable. Como cada teste da suíte registra uma
CLOSURE NOVA em `app.dependency_overrides[get_session]`, e a closure segura a
engine (e a conexão SQLite aberta, e o cache de SQL compilado — ~3 MB), o cache
do FastAPI ia acumulando uma engine por teste. `dependency_overrides.clear()`
no teardown não solta nada: quem segura a closure é o cache, não o app.

Este arquivo trava os dois lados:

  1. sem a faxina, a engine CONTINUA viva depois de todo mundo largar dela —
     é a doença; se um dia o FastAPI parar de segurar a closure, este teste
     falha avisando que a faxina do conftest virou desnecessária;
  2. com a faxina, a engine é coletada.

Sem o item 2, uma faxina que não limpasse nada passaria despercebida — é
exatamente o furo que este arquivo existe para fechar.
"""
from __future__ import annotations

import gc
import weakref

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from tests.conftest import limpar_caches_dependencia_fastapi


# App montada UMA vez para o arquivo inteiro — é o ponto que importa: na suíte
# real todo teste sobrescreve `get_session` na MESMA `main.app`, e é a app que
# sobrevive de um teste para o outro. Uma app nova por rodada esconderia o
# vazamento (morreria junto com os caches que ela mesma carrega).
_APP = FastAPI()


@_APP.get("/eco")
def _eco(session: Session = Depends(database.get_session)) -> dict:
    return {"ok": session is not None}


def _uma_rodada_de_teste() -> weakref.ref:
    """Reproduz o que ~200 arquivos desta suíte fazem: engine própria +
    override de `get_session` por closure + uma requisição que de fato USA a
    sessão injetada (numa rota protegida o 401 estoura antes, e a dependência
    sobrescrita nem chegaria a ser resolvida). Devolve um weakref para a
    engine, já tendo largado toda referência forte local."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    _APP.dependency_overrides[database.get_session] = _get_session_override
    try:
        with TestClient(_APP) as c:
            assert c.get("/eco").json() == {"ok": True}
    finally:
        _APP.dependency_overrides.clear()

    # Sem `del engine` aqui de propósito: `del` de uma variável CAPTURADA por
    # closure esvazia a própria cell, e aí o teste provaria o contrário do que
    # quer provar. Ao retornar, o frame morre sozinho — a cell, não: ela vive
    # dentro da closure, e é justamente essa closure que o cache do FastAPI
    # segura. É o mesmo que acontece na fixture `client` de cada arquivo.
    return weakref.ref(engine)


def test_sem_a_faxina_o_cache_do_fastapi_segura_a_engine():
    """CONTROLE POSITIVO — prova que o vazamento existe de verdade. Se este
    teste falhar, o FastAPI parou de segurar a closure e a faxina do conftest
    pode ser removida (com esta suíte inteira de volta ao verde)."""
    ref = _uma_rodada_de_teste()
    gc.collect()
    assert ref() is not None, (
        "o cache lru de fastapi.dependencies.models não segura mais a closure de "
        "override — a faxina em tests/conftest.py virou desnecessária, pode sair"
    )
    limpar_caches_dependencia_fastapi()  # não deixa lixo para o próximo teste


def test_com_a_faxina_a_engine_e_coletada():
    """O que a faxina do conftest garante: nenhuma engine sobrevive ao teste."""
    ref = _uma_rodada_de_teste()
    limpar_caches_dependencia_fastapi()
    gc.collect()
    assert ref() is None, (
        "a engine do teste continuou viva mesmo depois da faxina — o vazamento de "
        "~3 MB por teste voltou, e com ele o OOM dos workers do pytest -n auto"
    )
