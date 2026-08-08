"""
Registro dos tipos de exclusão "plugáveis" (ver `_base.py::TipoExclusao`) —
descoberta automática por `pkgutil`, para que cada domínio (estoque, pessoal,
rebanho, produção, agricultura) crie/edite só o próprio módulo em vez de
mexer num arquivo compartilhado (Parte 2 do plano de fechamento dos 17 gaps
de editar/excluir — evita 4+ agentes concorrentes colidindo no mesmo commit).

Qualquer módulo deste pacote (exceto os que começam com "_") que exportar
`TIPOS_EXCLUSAO: list[TipoExclusao]` no nível do módulo tem seus tipos
somados a `REGISTRO` automaticamente na primeira importação deste pacote —
não é preciso editar este arquivo para registrar um tipo novo.
"""
from __future__ import annotations

import importlib
import pkgutil

from fazenda.rules.exclusao_tipos._base import TipoExclusao

REGISTRO: dict[str, TipoExclusao] = {}
for _, nome, _ in pkgutil.iter_modules(__path__):
    if nome.startswith("_"):
        continue
    modulo = importlib.import_module(f"{__name__}.{nome}")
    for t in getattr(modulo, "TIPOS_EXCLUSAO", []):
        REGISTRO[t.id] = t

__all__ = ["REGISTRO", "TipoExclusao"]
