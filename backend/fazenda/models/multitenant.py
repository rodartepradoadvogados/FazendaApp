"""
Multi-fazenda (piloto conservador) — Fazenda e vínculo Usuario↔Fazenda.

Aditivo e isolado: nenhuma tabela existente foi alterada por causa disto.
Enquanto um usuário tiver só uma fazenda vinculada (o caso de todo mundo hoje,
via backfill da migração a3f7c9d1e246→<esta>), o comportamento do sistema
continua idêntico a antes — login auto-seleciona a única fazenda, sem tela de
escolha, e as consultas que já sabem filtrar por fazenda_id enxergam os mesmos
dados de sempre. A tela de seleção só aparece quando há de fato mais de uma
fazenda vinculada ao mesmo usuário (ex.: um consultor, ou um teste interno).

Ver fazenda/auth.py (token passa a carregar "fid") e
fazenda/api/routers/fazendas.py (cadastro de fazenda + vínculo).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class Fazenda(SQLModel, table=True):
    """Uma propriedade/cliente do sistema. Hoje só existe uma fazenda "real"
    (a que já está em uso diário) — esta tabela nasce com ela mais qualquer
    fazenda de teste criada depois."""

    __tablename__ = "fazenda"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    cidade: Optional[str] = None
    uf: Optional[str] = None
    ativa: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class UsuarioFazenda(SQLModel, table=True):
    """Vínculo N:N entre Usuario e Fazenda. Um usuário com mais de um vínculo
    vê a tela de seleção de fazenda ao logar (ver POST /auth/login e
    POST /auth/selecionar-fazenda)."""

    __tablename__ = "usuario_fazenda"
    __table_args__ = (UniqueConstraint("usuario_id", "fazenda_id", name="uq_usuario_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
