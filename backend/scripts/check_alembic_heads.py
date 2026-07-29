"""
Falha se as migrações do Alembic tiverem mais de uma cabeça (head).

Por que isto existe: dois PRs abertos em paralelo criam migrações irmãs com o
mesmo `down_revision`. Cada uma passa sozinha; depois do segundo merge o
histórico fica com duas cabeças, `alembic upgrade head` aborta com
"Multiple head revisions are present" e a API não sobe — derrubando o deploy.
Aconteceu 5+ vezes (PRs #311, #322+#324, #327+#328), sempre descoberto só em
produção. Este check roda no CI de cada PR, então o segundo PR do par quebra
ANTES do merge, e a correção é um `alembic merge` de uma linha.

Usa `ScriptDirectory`, que apenas lê os arquivos de versão: não executa
`env.py`, não importa a aplicação e não abre conexão com banco. Por isso o CI
só precisa do pacote `alembic` instalado, e o check roda em segundos.
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parent.parent


def heads() -> list[str]:
    cfg = Config(str(BACKEND / "alembic.ini"))
    # alembic.ini usa `%(here)s/alembic`, que o Config resolve a partir do
    # arquivo .ini — mas fixamos explicitamente para o check independer do cwd.
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return list(ScriptDirectory.from_config(cfg).get_heads())


def main() -> int:
    atuais = heads()
    if len(atuais) == 1:
        print(f"OK: uma cabeca so ({atuais[0]})")
        return 0
    if not atuais:
        print("ERRO: nenhuma cabeca encontrada em alembic/versions.")
        return 1
    print(f"ERRO: {len(atuais)} cabecas de migracao presentes:")
    for h in atuais:
        print(f"  - {h}")
    print("\nO deploy vai quebrar com 'Multiple head revisions are present'.")
    print("Corrija com:\n")
    print(f"  cd backend && alembic merge -m \"merge heads\" {' '.join(atuais)}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
