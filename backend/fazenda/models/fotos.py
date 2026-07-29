"""
Fotos do campo — capturadas pela câmera no app móvel (Android/Capacitor) e
enviadas ao Supabase Storage (bucket separado do arquivo fiscal-contábil, ver
fazenda/rules/supabase_storage.py e fazenda/api/routers/fotos.py).

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class FotoCampo(SQLModel, table=True):
    __tablename__ = "foto_campo"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    caminho_storage: str
    mime_type: str
    tamanho_bytes: int
    descricao: Optional[str] = None
    # Vínculo opcional com um animal (ex.: foto de um machucado, de uma
    # cria recém-nascida) — sem FK dura: o número da brinco/identificação
    # é digitado, não precisa existir cadastrado.
    identificacao_animal: Optional[str] = None
    data_captura: datetime = Field(default_factory=datetime.utcnow)
    enviado_por: Optional[int] = Field(default=None, foreign_key="usuario.id")
