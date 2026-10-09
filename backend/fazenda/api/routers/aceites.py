"""Aceites (parecer jurídico de 08/10/2026, item 6.1) — registro append-only.

- `GET  /aceites/vigentes`: os textos que pedem aceite (geral, cláusula, réguas), com
  versão, SHA-256, se já estão disponíveis e se ESTE usuário ainda deve o aceite;
- `POST /aceites`: registra um aceite. Versão e hash precisam ser os vigentes (409 se
  o texto mudou); "geral" e "clausula" respondem 409 enquanto os Termos de Uso não
  existirem (dependem da empresa constituída);
- `GET  /aceites/comprovante`: comprovante por usuário, em JSON (`?baixar=true` manda
  como arquivo). Padrão: o próprio usuário. `usuario_id` de outra pessoa só para o
  administrador da fazenda, e só aceites DESTA fazenda.

Montado com login + fazenda selecionada, sem trava de contrato: o aceite geral é o
que vem antes de qualquer uso.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import Usuario, UsuarioFazenda
from fazenda.rules import aceites
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/aceites", tags=["aceites"])


@router.get("/vigentes")
def textos_vigentes(
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    saida = {}
    for tipo in aceites.TIPOS:
        t = aceites.texto_vigente(tipo)
        ultimo = aceites.ultimo_aceite(session, user.id, fazenda_id, tipo, t["sha256"])
        saida[tipo] = {**t, "pendente_para_mim": ultimo is None}
    return saida


class AceiteIn(BaseModel):
    tipo: Literal["geral", "clausula", "reguas"]
    versao: str = Field(min_length=1, max_length=40)
    sha256: str = Field(min_length=64, max_length=64)


@router.post("", status_code=201)
def registrar_aceite(
    dados: AceiteIn,
    request: Request,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
) -> dict:
    a = aceites.registrar(
        session, usuario_id=user.id, fazenda_id=fazenda_id, tipo=dados.tipo,
        versao=dados.versao, sha256=dados.sha256, request=request,
    )
    return aceites.como_dict(a)


@router.get("/comprovante")
def comprovante_de_aceite(
    usuario_id: Optional[int] = None,
    baixar: bool = False,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
):
    fazenda_id = fazenda_id_seguro(fazenda_id)
    alvo = user
    if usuario_id is not None and usuario_id != user.id:
        if user.papel != "admin":
            raise HTTPException(status_code=403, detail="Só o administrador da fazenda vê o comprovante de outra pessoa")
        vinculo = None if fazenda_id is None else session.exec(
            select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario_id, UsuarioFazenda.fazenda_id == fazenda_id)
        ).first()
        alvo = session.get(Usuario, usuario_id) if vinculo else None
        if alvo is None:
            raise HTTPException(status_code=404, detail="Usuário não encontrado nesta fazenda")
    corpo = aceites.comprovante(session, alvo, fazenda_id)
    if not baixar:
        return corpo
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", f"comprovante-aceite-{alvo.username}-fazenda-{fazenda_id}.json")
    return JSONResponse(corpo, headers={"Content-Disposition": f'attachment; filename="{nome}"'})
