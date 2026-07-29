"""
Uma cabeça só nas migrações.

Duas migrações irmãs (dois PRs paralelos partindo do mesmo `down_revision`)
passam individualmente e só quebram depois do segundo merge, quando
`alembic upgrade head` aborta e a API não sobe. Este teste transforma isso
em falha local/CI, antes do merge. Ver scripts/check_alembic_heads.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "scripts"))

from check_alembic_heads import heads  # noqa: E402


def test_migracoes_tem_uma_cabeca_so():
    atuais = heads()
    assert len(atuais) == 1, (
        f"{len(atuais)} cabecas de migracao: {atuais}. O deploy quebra com "
        f"'Multiple head revisions are present'. Corrija com: "
        f"cd backend && alembic merge -m \"merge heads\" {' '.join(atuais)}"
    )
