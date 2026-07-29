"""
Filtro salvo — conjunto de filtros nomeado pelo usuário, para reaplicar com um
clique numa tela de relatório (ex.: Financeiro > Extrato completo). Ver
fazenda/api/routers/filtros_salvos.py.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel
from sqlalchemy import Index


class FiltroSalvo(SQLModel, table=True):
    """`tela` identifica a tela/aba onde o filtro se aplica (ex.:
    "financeiro_extrato") — cada tela tem seu próprio conjunto de filtros
    salvos, nunca compartilhado com outra. `filtros` é o estado dos campos de
    filtro daquela tela, JSON-codificado (mesmo padrão de texto-como-JSON já
    usado em TelegramSessao.dados/LancamentoPendente.payload)."""

    __tablename__ = "filtro_salvo"
    # Mesmo nome duas vezes na mesma tela, para o mesmo usuário, sobrescreve
    # em vez de duplicar (ver POST /filtros-salvos).
    __table_args__ = (Index("uq_filtro_salvo_usuario_tela_nome", "usuario_id", "tela", "nome", unique=True),)

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    tela: str = Field(index=True)
    nome: str
    filtros: str
    criado_em: datetime = Field(default_factory=datetime.utcnow)
