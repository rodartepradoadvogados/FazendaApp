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


os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
# Pula os ~50 seeds de bootstrap do lifespan (main.py) — cada TestClient(main.app)
# criado por um teste é um banco de produção vazio sendo semeado do zero; testes
# que constroem seu próprio engine isolado já semeiam só o que usam. Ver o
# comentário em main.py::lifespan para o que exatamente isso desliga.
os.environ["FAZENDA_TESTING"] = "1"
