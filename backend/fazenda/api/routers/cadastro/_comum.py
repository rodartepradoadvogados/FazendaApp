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

from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.visibilidade import visivel


class NomeAtivoIn(BaseModel):
    nome: str
    ativo: bool = True


def _crud_nome_ativo(model, com_fazenda: bool = False, global_compartilhado: bool = False):
    """Fábrica de CRUD idêntico para os cadastros simples (nome + ativo).

    `com_fazenda=True` para os modelos que já têm fazenda_id (unique(nome,
    fazenda_id) em vez de unique(nome) global) — filtra a listagem e a
    checagem de duplicata pela fazenda atual, e carimba fazenda_id no
    registro criado. Os demais (sem fazenda_id na tabela) ignoram o parâmetro.

    `global_compartilhado=True` (só faz sentido junto de `com_fazenda=True`)
    é para os cadastros que são também CATÁLOGO do Painel CowData (Princípio
    ativo, Doença — ver `rules/visibilidade.py`): a listagem troca o filtro
    estrito por `visivel()` (fazenda atual OU `fazenda_id` nulo), senão um
    princípio/doença cadastrado no Painel CowData nunca aparece no seletor do
    tenant. `criar`/`atualizar`/`excluir` continuam estritos por fazenda — o
    tenant só cria/edita/apaga as PRÓPRIAS linhas; a linha global nunca é
    tocada por aqui (isso é papel do Painel CowData).

    `criar` (o único caminho de ESCRITA que grava fazenda_id — `atualizar`/
    `excluir` só leem um registro já existente) usa o resolvedor único
    `get_fazenda_id_escrita` quando `com_fazenda=True`, em vez do
    `get_fazenda_atual_id` tolerante — nunca grava fazenda_id nulo em
    silêncio (ver fazenda.auth::resolver_fazenda_id_escrita). Isso vale pra
    TODO cadastro "nome + ativo" que usa esta fábrica com `com_fazenda=True`
    (Local de Armazenamento, Categoria/Finalidade/Unidade de Estoque, Raça,
    Motivo de baixa/venda, Princípio ativo, Doença, Serviço de cadastro...).
    """

    def listar(session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)) -> list[dict]:
        query = select(model).order_by(model.nome)
        if com_fazenda:
            fazenda_id = fazenda_id_seguro(fazenda_id)
            if global_compartilhado:
                query = visivel(query, model, fazenda_id)
            elif fazenda_id is not None:
                query = query.where(model.fazenda_id == fazenda_id)
        return [m.model_dump() for m in session.exec(query).all()]

    def _criar_com_fazenda(dados: NomeAtivoIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        query_dup = select(model).where(model.nome == nome)
        if fazenda_id is not None:
            query_dup = query_dup.where(model.fazenda_id == fazenda_id)
        if session.exec(query_dup).first():
            raise HTTPException(status_code=409, detail=f"Já existe um registro com o nome '{nome}'")
        obj = model(nome=nome, ativo=dados.ativo, fazenda_id=fazenda_id)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    def _criar_sem_fazenda(dados: NomeAtivoIn, session: Session = Depends(get_session)) -> dict:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        query_dup = select(model).where(model.nome == nome)
        if session.exec(query_dup).first():
            raise HTTPException(status_code=409, detail=f"Já existe um registro com o nome '{nome}'")
        obj = model(nome=nome, ativo=dados.ativo)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    criar = _criar_com_fazenda if com_fazenda else _criar_sem_fazenda

    def atualizar(
        item_id: int, dados: NomeAtivoIn, session: Session = Depends(get_session),
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
    ) -> dict:
        obj = session.get(model, item_id)
        if com_fazenda:
            fazenda_id = fazenda_id_seguro(fazenda_id)
            if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
                raise HTTPException(status_code=404, detail="Registro não encontrado")
        elif not obj:
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

    def excluir(
        item_id: int, session: Session = Depends(get_session),
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
    ) -> dict:
        obj = session.get(model, item_id)
        if com_fazenda:
            fazenda_id = fazenda_id_seguro(fazenda_id)
            if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
                raise HTTPException(status_code=404, detail="Registro não encontrado")
        elif not obj:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        session.delete(obj)
        session.commit()
        return {"excluido": True}

    return listar, criar, atualizar, excluir
