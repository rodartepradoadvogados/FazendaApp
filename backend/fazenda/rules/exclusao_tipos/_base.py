"""
Peças compartilhadas do registro extensível de tipos de exclusão
(`rules/exclusao_tipos/`, ver `__init__.py` para a descoberta automática).

`_br`, `_contem` e `_dentro_periodo` moraram em
`api/routers/exclusoes.py` até a Fase 0 do plano de fechamento dos 17 gaps de
editar/excluir — foram movidas para cá porque os módulos de domínio
(`estoque.py`, `pessoal.py`, `rebanho.py`, `producao.py`, `agricultura.py`)
precisam delas para implementar `buscar`/`alvos`, e um módulo de domínio não
pode importar de `api/routers/exclusoes.py` sem criar um ciclo
(`exclusoes -> rules.exclusao_tipos.<dominio> -> exclusoes`). `exclusoes.py`
agora importa as três funções DAQUI, em vez de defini-las.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def _br(data) -> str:
    """Formata uma data como dd/mm/aaaa (padrão brasileiro) para exibição no título."""
    return data.strftime("%d/%m/%Y") if data else "—"


def _contem(termo: str, *valores) -> bool:
    if not termo:
        return True
    termo = termo.strip().lower()
    return any(termo in str(v).lower() for v in valores if v is not None)


def _dentro_periodo(data_ref, data_inicio: str, data_fim: str) -> bool:
    """Filtro de data opcional — sem data de referência no registro, ou sem filtro definido, não exclui nada."""
    if not data_inicio and not data_fim:
        return True
    if data_ref is None:
        return False
    ref = data_ref.isoformat()
    if data_inicio and ref < data_inicio:
        return False
    if data_fim and ref > data_fim:
        return False
    return True


@dataclass
class TipoExclusao:
    """Um tipo de exclusão "plugável" no motor genérico de
    `api/routers/exclusoes.py`. Cada domínio exporta uma lista de nível de
    módulo `TIPOS_EXCLUSAO: list[TipoExclusao]` no seu próprio arquivo
    (`estoque.py`, `pessoal.py`, `rebanho.py`, `producao.py`,
    `agricultura.py`) — `__init__.py` descobre e registra sozinho, sem que
    ninguém precise editar um arquivo compartilhado.

    `buscar` e `alvos` seguem exatamente o contrato de `_buscar_um`/`_alvos`
    em `exclusoes.py`: `buscar` filtra por `_contem`/`_dentro_periodo` e corta
    em `[:200]`; `alvos` pode ter efeitos colaterais (reversão de saldo/
    estado) e pode bloquear com `HTTPException(400, ...)` — a reversão SEMPRE
    vai dentro de `alvos`, nunca numa rota separada (ver comentário no topo de
    `exclusoes.py` sobre `get_session` não commitar no teardown).
    """

    id: str
    label: str
    # (termo, data_inicio, data_fim, session, fazenda_id) -> list[dict com "id"/"titulo"/"subtitulo"/"_data"?]
    buscar: Callable[..., list[dict]]
    # (id_, session, fazenda_id) -> (impacto: list[str], objetos: list)
    alvos: Callable[..., tuple[list[str], list]]
    sem_filtro_data: bool = False  # espelha TIPOS_SEM_DATA do FormExclusao.tsx
