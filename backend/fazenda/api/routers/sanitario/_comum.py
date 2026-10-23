"""
Dependências e utilidades comuns do pacote /sanitario.

Isolamento por fazenda como o resto do sistema: o router é montado em
main.py com `exigir_fazenda_selecionada` (token sem "fid" não entra); as
rotas de LEITURA usam `get_fazenda_atual_id` e as de ESCRITA,
`get_fazenda_id_escrita` (sentinelas tests/test_sentinela_*). Toda consulta
filtra `fazenda_id`; id de outra fazenda responde 404, nunca 403.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session

from fazenda.rules.sanitario.dias import Conflito, PrecisaDecisao
from fazenda.rules.sanitario.permissoes import eh_admin_fazenda


def exigir_fazenda(fazenda_id: Optional[int]) -> int:
    if fazenda_id is None:
        raise HTTPException(status_code=409, detail="Selecione a fazenda antes de usar o sanitário.")
    return int(fazenda_id)


def exigir_admin_fazenda(session: Session, usuario, fazenda_id: int) -> None:
    if not eh_admin_fazenda(session, usuario, fazenda_id):
        raise HTTPException(status_code=403, detail="Só o administrador da fazenda pode fazer isto.")


def da_fazenda(session: Session, modelo, obj_id: int, fazenda_id: int, nome: str = "Registro"):
    obj = session.get(modelo, obj_id)
    if obj is None or getattr(obj, "fazenda_id", None) != fazenda_id:
        raise HTTPException(status_code=404, detail=f"{nome} não encontrado.")
    return obj


@contextmanager
def traduzir_erros(session: Session):
    """Exceções das regras -> HTTP. `PrecisaDecisao` vira 409 com o detalhe
    estruturado (o front abre o pop-up e reenvia com a decisão)."""
    try:
        yield
    except PrecisaDecisao as e:
        session.rollback()
        raise HTTPException(status_code=409, detail={"codigo": e.codigo, **e.detalhe})
    except Conflito as e:
        session.rollback()
        raise HTTPException(status_code=409, detail={"codigo": "versao_desatualizada", "mensagem": str(e)})
    except PermissionError as e:
        session.rollback()
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
