"""
Chave de idempotência — cache de respostas por header `Idempotency-Key`, usado
pelo middleware de idempotência (ver main.py::_idempotencia) para o app de
campo não duplicar um lançamento quando a resposta de um POST se perde por
queda de conexão (o cliente reenvia da fila offline achando que nunca chegou
ao servidor — ver frontend/lib/offline.ts).

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel
from sqlalchemy import Index


class IdempotenciaChave(SQLModel, table=True):
    """Uma linha por (chave, método, caminho) processado com sucesso (2xx).
    Reenviar a mesma chave para o mesmo endpoint+verbo devolve `resposta_json`
    /`status_code` salvos aqui, sem rodar a rota de novo — ver o middleware
    para o fluxo completo (inclusive por que erro de validação NÃO é salvo).

    ponytail: sem expiração automática — a fila offline do app de campo é de
    curto prazo (minutos a poucas horas até reconectar), então a tabela não
    deve crescer muito. Se um dia isso incomodar, uma limpeza periódica (ex.:
    apagar linhas com `criado_em` > 7 dias, no mesmo estilo dos loops de
    background em main.py) resolveria — não implementado agora."""

    __tablename__ = "idempotencia_chave"
    __table_args__ = (
        Index("uq_idempotencia_chave_metodo_caminho", "chave", "metodo", "caminho", unique=True),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    chave: str = Field(index=True)
    metodo: str
    caminho: str
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    status_code: int
    resposta_json: str
    criado_em: datetime = Field(default_factory=datetime.utcnow)
