"""
Helpers compartilhados entre os submódulos de Cadastro — extraídos do antigo
`cadastro.py` monolítico. Hoje só a fábrica de CRUD "nome + ativo", reusada
por animais.py (Raça, Motivo de baixa, Motivo de venda), sanitario.py
(Princípio ativo, Doença) e servicos.py (Serviço de cadastro, Tipo de
serviço reprodutivo).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.rules.auditoria import fazenda_id_seguro


class NomeAtivoIn(BaseModel):
    nome: str
    ativo: bool = True


def _crud_nome_ativo(model, com_fazenda: bool = False):
    """Fábrica de CRUD idêntico para os cadastros simples (nome + ativo).

    `com_fazenda=True` para os modelos que já têm fazenda_id (unique(nome,
    fazenda_id) em vez de unique(nome) global) — filtra a listagem e a
    checagem de duplicata pela fazenda atual, e carimba fazenda_id no
    registro criado. Os demais (sem fazenda_id na tabela) ignoram o parâmetro.
    """

    def listar(session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)) -> list[dict]:
        query = select(model).order_by(model.nome)
        if com_fazenda:
            fazenda_id = fazenda_id_seguro(fazenda_id)
            if fazenda_id is not None:
                query = query.where(model.fazenda_id == fazenda_id)
        return [m.model_dump() for m in session.exec(query).all()]

    def criar(dados: NomeAtivoIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)) -> dict:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        query_dup = select(model).where(model.nome == nome)
        if com_fazenda:
            fazenda_id = fazenda_id_seguro(fazenda_id)
            if fazenda_id is not None:
                query_dup = query_dup.where(model.fazenda_id == fazenda_id)
        if session.exec(query_dup).first():
            raise HTTPException(status_code=409, detail=f"Já existe um registro com o nome '{nome}'")
        obj = model(nome=nome, ativo=dados.ativo, **({"fazenda_id": fazenda_id} if com_fazenda else {}))
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    def atualizar(item_id: int, dados: NomeAtivoIn, session: Session = Depends(get_session)) -> dict:
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        obj.nome = nome
        obj.ativo = dados.ativo
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    return listar, criar, atualizar
