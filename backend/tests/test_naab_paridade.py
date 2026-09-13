"""
Paridade entre fazenda/rules/naab.py::NAAB_STUDS e frontend/lib/constants.ts::
NAAB_STUDS — as duas tabelas de códigos de central NAAB são mantidas
manualmente em dois lugares (o próprio docstring de naab.py já avisa
"Espelha frontend/lib/constants.ts"), sem nenhum mecanismo automático que
impeça as duas cópias de divergirem quando alguém adicionar uma central nova
em só um dos dois lados. Este teste lê o arquivo TS de verdade (não duplica a
lista aqui) e compara com o dict Python.
"""
from __future__ import annotations

import re
from pathlib import Path

from fazenda.rules.naab import NAAB_STUDS

# backend/tests/test_naab_paridade.py -> backend/ -> raiz do repo -> frontend/lib/constants.ts
_CONSTANTS_TS = Path(__file__).resolve().parent.parent.parent / "frontend" / "lib" / "constants.ts"


def _ler_naab_studs_do_frontend() -> dict[str, str]:
    texto = _CONSTANTS_TS.read_text(encoding="utf-8")
    bloco = re.search(r"export const NAAB_STUDS.*?=\s*\[(.*?)\];", texto, re.DOTALL)
    assert bloco, "Não encontrei NAAB_STUDS em frontend/lib/constants.ts — arquivo mudou de formato?"
    pares = re.findall(r'\{\s*codigo:\s*"(\d+)",\s*nome:\s*"([^"]+)"\s*\}', bloco.group(1))
    assert pares, "NAAB_STUDS do frontend está vazio ou o regex não bateu com o formato atual"
    return dict(pares)


def test_tabela_python_e_typescript_tem_os_mesmos_codigos_e_nomes():
    assert _CONSTANTS_TS.exists(), f"Não achei {_CONSTANTS_TS} — layout do repo mudou?"
    do_frontend = _ler_naab_studs_do_frontend()
    assert NAAB_STUDS == do_frontend, (
        "fazenda/rules/naab.py::NAAB_STUDS divergiu de frontend/lib/constants.ts::NAAB_STUDS — "
        "atualize os dois juntos.\n"
        f"Só no Python: {set(NAAB_STUDS.items()) - set(do_frontend.items())}\n"
        f"Só no TypeScript: {set(do_frontend.items()) - set(NAAB_STUDS.items())}"
    )
