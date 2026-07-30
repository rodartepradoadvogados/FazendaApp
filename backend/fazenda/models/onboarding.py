"""
Onboarding — checklist guiado de primeiro acesso (Configurações > nada, é
automático: aparece na Capa até o usuário concluir ou dispensar). Ver
fazenda/api/routers/onboarding.py.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class OnboardingUsuario(SQLModel, table=True):
    """Uma linha por usuário (get-or-create, mesmo padrão de
    ParametroManualFazenda). `passos_concluidos` é CSV de chaves de passo
    (ver PASSOS_ONBOARDING em fazenda/api/routers/onboarding.py) — os passos
    em si são fixos no código, não em banco, porque mudam raramente e não
    fazem sentido editáveis pelo usuário."""

    __tablename__ = "onboarding_usuario"

    usuario_id: int = Field(foreign_key="usuario.id", primary_key=True)
    passos_concluidos: str = ""
    dispensado: bool = False
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
