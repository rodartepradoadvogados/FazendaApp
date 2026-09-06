"""
Garante que a suíte de testes nunca rode acidentalmente contra o banco de
produção (Postgres/Neon apontado por DATABASE_URL no ambiente do shell).

Vários módulos (main.py, push.py, portal.py, rules/parametros.py, etc.)
fazem `from fazenda.database import engine` — um bind direto de nome, que
não é afetado por um `monkeypatch.setattr(database, "engine", ...)` feito
depois que o módulo já foi importado. O valor de DATABASE_URL só importa na
primeira vez que fazenda.database é importado no processo (é quando o
engine do módulo é criado); depois disso, mudar a env var não tem efeito.

Este conftest.py roda antes de qualquer teste ser coletado (garantia do
pytest para conftest.py na raiz do diretório de testes), então força
DATABASE_URL para um SQLite descartável antes que qualquer módulo de
fazenda.* seja importado pela primeira vez — independente da ordem de
coleta dos arquivos de teste e sem exigir que cada arquivo repita essa
mesma proteção individualmente.
"""
import glob
import os
import tempfile
import weakref

import sqlalchemy
import sqlmodel

# ── Faxina dos bancos temporários ────────────────────────────────────────────
#
# 47 arquivos de teste (mais este conftest) criam o banco da sessão com
# `tempfile.mktemp(suffix=".db")`, que devolve um caminho em /tmp e NUNCA
# apaga o arquivo. Cada execução da suíte deixava ~40 bancos para trás; em uma
# semana de desenvolvimento isso virou 8.020 arquivos e 27 GB, até encher o
# disco e derrubar a própria suíte com ENOSPC.
#
# Em vez de editar os 47 arquivos — e torcer para o 48º lembrar —, o wrapper
# abaixo anota todo caminho `.db` entregue por mktemp e `pytest_sessionfinish`
# apaga exatamente esses no fim. Só toca no que a própria suíte criou: nada de
# varrer /tmp por glob cego, que apagaria arquivo de outro processo.
#
# SEGUNDA REDE (set/2026), para o caso em que a primeira não roda: um processo
# MORTO A SIGKILL não executa `pytest_sessionfinish` nenhum, e leva a lista
# `_BANCOS_TEMPORARIOS` junto. Foi o que aconteceu com `-n auto` — o OOM killer
# derrubava workers no meio da suíte (ver a segunda seção deste arquivo) e
# cada worker morto deixava ~120 bancos órfãos: 618 arquivos e 1,9 GB em uma
# única execução. Como SIGKILL não dá para interceptar (nem por atexit), a
# única limpeza confiável é a do INÍCIO da execução seguinte: o nome do arquivo
# passa a carregar o PID de quem o criou, e a varredura abaixo apaga só os que
# pertencem a um processo que não existe mais. O lixo fica limitado ao de uma
# execução, em vez de acumular indefinidamente, e nenhum banco de um worker
# irmão VIVO é tocado.
_PREFIXO_BANCO = "fazenda-teste-"
_BANCOS_TEMPORARIOS: list[str] = []
_mktemp_original = tempfile.mktemp


def _mktemp_rastreado(suffix="", prefix=tempfile.template, dir=None):
    if suffix == ".db":
        # Carimba o dono no nome, para a varredura de órfãos saber de quem é.
        prefix = f"{_PREFIXO_BANCO}{os.getpid()}-"
    caminho = _mktemp_original(suffix=suffix, prefix=prefix, dir=dir)
    if str(caminho).endswith(".db"):
        _BANCOS_TEMPORARIOS.append(str(caminho))
    return caminho


tempfile.mktemp = _mktemp_rastreado


def _apagar_banco(caminho: str) -> None:
    """Apaga o banco e os `-wal`/`-shm`/`-journal` que o SQLite cria ao lado."""
    for alvo in (caminho, f"{caminho}-wal", f"{caminho}-shm", f"{caminho}-journal"):
        try:
            os.unlink(alvo)
        except OSError:
            pass  # já apagado, nunca criado, ou em uso — nada a fazer


def _pid_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # existe, só não é nosso para sinalizar — não encosta
    return True


def _varrer_bancos_orfaos() -> None:
    """Apaga os bancos deixados por execuções cujo processo já morreu (worker
    derrubado pelo OOM killer, Ctrl-C forçado, container reiniciado)."""
    for caminho in glob.glob(os.path.join(tempfile.gettempdir(), f"{_PREFIXO_BANCO}*.db")):
        resto = os.path.basename(caminho)[len(_PREFIXO_BANCO):]
        try:
            pid = int(resto.split("-", 1)[0])
        except ValueError:
            continue  # nome fora do padrão — não é nosso, não mexe
        if pid <= 0 or pid == os.getpid() or _pid_vivo(pid):
            continue
        _apagar_banco(caminho)


_varrer_bancos_orfaos()


def pytest_sessionfinish(session, exitstatus):
    """Apaga os bancos temporários desta sessão (caminho feliz — o processo
    chegou vivo até o fim). O que escapar daqui cai na varredura de órfãos da
    execução seguinte."""
    for caminho in _BANCOS_TEMPORARIOS:
        _apagar_banco(caminho)


# ── Vazamento de memória do cache de dependências do FastAPI ─────────────────
#
# `fastapi.dependencies.models` memoriza a classificação de cada callable
# ("é gerador?", "é async?", "é corrotina?") em três `@lru_cache(maxsize=4096)`
# chaveados por `_CallIdentity`, que guarda uma referência FORTE ao callable
# (hash por `id()`, ver o código do FastAPI 0.141).
#
# Quase todo arquivo desta suíte monta o cliente assim:
#
#     engine = create_engine(...); SQLModel.metadata.create_all(engine)
#     def _get_session_override():
#         with Session(engine) as session:
#             yield session
#     main.app.dependency_overrides[database.get_session] = _get_session_override
#
# `_get_session_override` é uma CLOSURE NOVA a cada teste, e a closure segura
# a engine, que segura a conexão SQLite aberta e todo o cache de SQL compilado
# daquele banco (~3 MB, o tamanho do schema). Como os três caches só descartam
# no 4.097º callable distinto, e um worker roda ~1.200 testes, NADA era
# descartado: `main.app.dependency_overrides.clear()` no teardown do teste não
# adianta nada, porque quem segura a closure é o cache do FastAPI, não o app.
#
# Medido em tests/test_cadastro.py (140 testes, um TestClient por teste):
#
#     sem limpar:  20 testes → 380 MB /  21 engines vivas
#                 140 testes → 969 MB / 132 engines vivas   (~4,5 MB por teste)
#     limpando:    20 testes → 352 MB /   2 engines vivas
#                 140 testes → 465 MB /   2 engines vivas   (~0,8 MB por teste)
#
# Extrapolando para os ~1.200 testes de um worker: ~5,9 GB contra ~1,2 GB. Era
# essa a causa do `pytest -n auto` derrubar workers com "node down: Not properly
# terminated" — o cgroup estourava e o OOM killer matava o processo. Cada worker
# morto vira uma linha "F" com `worker 'gwN' crashed while running '<teste>'`
# (xdist, dsession.py::handle_crashitem): um teste ÍNTEGRO reportado como falho,
# que passa sozinho e no `--lf` seguinte.
#
# A limpeza abaixo é só descartar memoização — o FastAPI recalcula na próxima
# requisição, e o custo é irrelevante perto de montar um TestClient por teste.
_CACHES_FASTAPI: list = []


def _caches_fastapi() -> list:
    if _CACHES_FASTAPI:
        return _CACHES_FASTAPI
    try:
        from fastapi.dependencies import models as _fastapi_models
    except Exception:  # pragma: no cover - FastAPI sempre presente na suíte
        return _CACHES_FASTAPI
    for nome in dir(_fastapi_models):
        alvo = getattr(_fastapi_models, nome, None)
        # Toda função decorada com functools.lru_cache expõe cache_clear.
        if callable(alvo) and hasattr(alvo, "cache_clear") and hasattr(alvo, "cache_info"):
            _CACHES_FASTAPI.append(alvo)
    return _CACHES_FASTAPI


def limpar_caches_dependencia_fastapi() -> None:
    """Solta as closures de override que os `lru_cache` do FastAPI seguram."""
    for cache in _caches_fastapi():
        cache.cache_clear()


def pytest_runtest_teardown(item, nextitem):
    limpar_caches_dependencia_fastapi()


# ── Faxina dos engines ───────────────────────────────────────────────────────
#
# A suíte inteira num processo só NÃO CABE na memória de um runner do GitHub
# (16 GB). Medido em 06/09/2026 numa máquina com a mesma RAM: pico de 13,6 GB
# e o processo morto pelo OOM killer (exit 137); no CI o job morre antes,
# sempre por volta de 30% dos testes, com exit 143 ("The runner has received a
# shutdown signal") — que parece teste quebrado e não é, porque não há um
# único F antes.
#
# A causa não é o volume de testes, é que ninguém fecha o engine: 277 arquivos
# chamam `create_engine` e apenas UM chamava `dispose()`. Cada engine mantém
# um connection pool vivo até o fim do PROCESSO — e, nos testes que usam
# `StaticPool` com "sqlite://", a conexão única segura o banco em memória
# inteiro. São ~276 pools (e bancos) acumulando enquanto a sessão do pytest
# durar.
#
# O wrapper abaixo anota cada engine criado e `pytest_runtest_teardown` o
# descarta ao fim do teste que o criou. É seguro descartar no teardown porque
# nenhuma fixture da suíte tem escopo maior que `function` e nenhum módulo
# cria engine fora de fixture (conferido: 0 e 0) — ou seja, nenhum engine é
# reusado entre testes.
#
# A lista guarda WEAKREF de propósito: uma referência forte manteria vivo
# justamente o objeto que se quer liberar, trocando um vazamento por outro.
_ENGINES_DO_TESTE: list = []


def _rastrear_engine(engine):
    _ENGINES_DO_TESTE.append(weakref.ref(engine))
    return engine


def _patch_create_engine(modulo) -> None:
    """Embrulha `create_engine` do módulo, se ele tiver um.

    Os dois pontos importam: os testes escrevem tanto `from sqlmodel import
    create_engine` quanto `from sqlalchemy import create_engine`, e o `from`
    copia a referência no import do módulo de teste. Este conftest.py roda
    antes da coleta (garantia do pytest para conftest.py na raiz), então os
    módulos de teste já importam a versão embrulhada.
    """
    original = getattr(modulo, "create_engine", None)
    if original is None or getattr(original, "_cowdata_rastreado", False):
        return

    def _wrapper(*args, **kwargs):
        return _rastrear_engine(original(*args, **kwargs))

    _wrapper._cowdata_rastreado = True  # evita embrulhar duas vezes
    modulo.create_engine = _wrapper


_patch_create_engine(sqlalchemy)
_patch_create_engine(sqlmodel)


def pytest_runtest_teardown(item, nextitem):
    """Fecha o pool de todo engine criado durante o teste que acabou.

    `dispose()` não invalida o engine — só devolve o pool e fecha as conexões
    —, mas num engine `StaticPool`/"sqlite://" ele descarta o banco em
    memória junto. É exatamente o que se quer AQUI, no teardown: o teste já
    terminou e ninguém mais vai ler aquele banco. Por isso este hook não pode
    virar `pytest_runtest_setup` nem rodar entre asserts.

    Erros são engolidos um a um: uma falha ao descartar um engine não pode
    derrubar o teste que acabou de passar.
    """
    for ref in _ENGINES_DO_TESTE:
        engine = ref()
        if engine is None:
            continue  # já coletado pelo GC — nada a fazer
        try:
            engine.dispose()
        except Exception:
            pass
    _ENGINES_DO_TESTE.clear()


os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
# Pula os ~50 seeds de bootstrap do lifespan (main.py) — cada TestClient(main.app)
# criado por um teste é um banco de produção vazio sendo semeado do zero; testes
# que constroem seu próprio engine isolado já semeiam só o que usam. Ver o
# comentário em main.py::lifespan para o que exatamente isso desliga.
os.environ["FAZENDA_TESTING"] = "1"
