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
import os
import tempfile
import weakref

import sqlalchemy
import sqlmodel

# ── Faxina dos bancos temporários ────────────────────────────────────────────
#
# 20 arquivos de teste (mais este conftest) criam o banco da sessão com
# `tempfile.mktemp(suffix=".db")`, que devolve um caminho em /tmp e NUNCA
# apaga o arquivo. Cada execução da suíte deixava ~40 bancos para trás; em uma
# semana de desenvolvimento isso virou 8.020 arquivos e 27 GB, até encher o
# disco e derrubar a própria suíte com ENOSPC.
#
# Em vez de editar os 20 arquivos — e torcer para o 21º lembrar —, o wrapper
# abaixo anota todo caminho `.db` entregue por mktemp e `pytest_sessionfinish`
# apaga exatamente esses no fim. Só toca no que a própria suíte criou: nada de
# varrer /tmp por glob, que apagaria arquivo de outro processo.
_BANCOS_TEMPORARIOS: list[str] = []
_mktemp_original = tempfile.mktemp


def _mktemp_rastreado(*args, **kwargs):
    caminho = _mktemp_original(*args, **kwargs)
    if str(caminho).endswith(".db"):
        _BANCOS_TEMPORARIOS.append(str(caminho))
    return caminho


tempfile.mktemp = _mktemp_rastreado


def pytest_sessionfinish(session, exitstatus):
    """Apaga os bancos temporários da sessão — inclusive os `-wal`/`-shm` que
    o SQLite cria ao lado quando o journal está em modo WAL."""
    for caminho in _BANCOS_TEMPORARIOS:
        for alvo in (caminho, f"{caminho}-wal", f"{caminho}-shm", f"{caminho}-journal"):
            try:
                os.unlink(alvo)
            except OSError:
                pass  # já apagado, nunca criado, ou em uso — nada a fazer


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
