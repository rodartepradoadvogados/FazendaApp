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

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
