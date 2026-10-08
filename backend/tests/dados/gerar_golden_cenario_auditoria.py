"""
Gera tests/dados/cenario_auditoria_golden_main.json: os números do cenário da
auditoria calculados pelo código ORIGINAL (antes da Fase A). É a prova de que,
com a flag `financeiro_regras_v2` desligada, nada mudou.

Uso (uma vez, ou quando o cenário mudar) — de backend/:

    git worktree add /tmp/base-main 460d9712
    DATABASE_URL=sqlite:////tmp/golden.db FAZENDA_TESTING=1 \\
        python tests/dados/gerar_golden_cenario_auditoria.py /tmp/base-main/backend \\
        tests/dados/cenario_auditoria_golden_main.json

O 1º argumento é o backend cujo código vai calcular (o da main antiga); o
cenário (tests/cenario_auditoria_financeiro.py) é sempre o desta árvore.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TESTS = AQUI.parent


def main() -> int:
    backend_codigo, saida = sys.argv[1], sys.argv[2]
    sys.path.insert(0, str(TESTS))          # cenario_auditoria_financeiro
    sys.path.insert(0, backend_codigo)      # fazenda/main do código a medir
    db = os.environ["DATABASE_URL"].removeprefix("sqlite:///")
    if os.path.exists(db):
        os.remove(db)

    from fastapi.testclient import TestClient
    from sqlmodel import Session, SQLModel, create_engine

    import fazenda.database as database
    import fazenda.models  # noqa: F401
    import main as app_main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    from cenario_auditoria_financeiro import ler_relatorios_estaveis, montar_cenario, preparar_fazendas

    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    preparar_fazendas(engine)

    def _sessao():
        with Session(engine) as s:
            yield s

    class _U:
        id = 1
        papel = "admin"
        ativo = True
        username = "golden"

    app_main.app.dependency_overrides[database.get_session] = _sessao
    app_main.app.dependency_overrides[get_current_user] = lambda: _U()
    app_main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    with TestClient(app_main.app) as c:
        montar_cenario(c, engine, 1)
        dados = ler_relatorios_estaveis(c)
    Path(saida).write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"golden gravado em {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
