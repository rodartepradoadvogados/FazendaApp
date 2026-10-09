"""
Gera tests/dados/caixa_cartao_golden_pre_pr56.json: saldo das contas, Caixa
Real, fundo de reserva, Contas a pagar e o fluxo do cartão (compra → fechar →
pagar) do cenário da auditoria, calculados pelo código de ANTES dos PRs 5 e 6
(commit 62880163, já com o `hoje_local` do PR 0). É a prova de que, com a flag
`financeiro_regras_v2` desligada, nada disso mudou.

O relógio fica PARADO em `HOJE_GOLDEN_CAIXA` (o L9 vence em hoje+22 e a compra
aberta do cartão é de hoje), substituindo `fazenda.rules.datas.agora_local`.

Uso (de backend/):

    git archive -o /tmp/base.tar 62880163 backend && mkdir /tmp/base && tar -xf /tmp/base.tar -C /tmp/base
    DATABASE_URL=sqlite:////tmp/golden_caixa.db FAZENDA_TESTING=1 \\
        python tests/dados/gerar_golden_caixa_cartao.py /tmp/base/backend \\
        tests/dados/caixa_cartao_golden_pre_pr56.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TESTS = AQUI.parent


def main() -> int:
    backend_codigo, saida = sys.argv[1], sys.argv[2]
    sys.path.insert(0, str(TESTS))
    sys.path.insert(0, backend_codigo)
    db = os.environ["DATABASE_URL"].removeprefix("sqlite:///")
    if os.path.exists(db):
        os.remove(db)

    from fastapi.testclient import TestClient
    from sqlmodel import Session, SQLModel, create_engine

    import fazenda.database as database
    import fazenda.models  # noqa: F401
    import fazenda.rules.datas as datas
    import main as app_main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    from cenario_auditoria_financeiro import HOJE_GOLDEN_CAIXA, ler_caixa_e_cartao, montar_cenario, preparar_fazendas

    meio_dia = datetime(HOJE_GOLDEN_CAIXA.year, HOJE_GOLDEN_CAIXA.month, HOJE_GOLDEN_CAIXA.day, 12, 0)
    datas.agora_local = lambda agora=None: meio_dia  # relógio parado

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
        ids = montar_cenario(c, engine, 1, hoje=HOJE_GOLDEN_CAIXA)
        dados = ler_caixa_e_cartao(c, ids, HOJE_GOLDEN_CAIXA)
    Path(saida).write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"golden gravado em {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
