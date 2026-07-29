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
    # Assunto opcional marcado no momento da captura — "animal" | "lote" | "outro".
    # None = foto sem assunto marcado (comportamento de antes desta coluna existir).
    tipo_assunto: Optional[str] = None
    # tipo_assunto == "animal": FK resolvida a partir do número escolhido na lista
    # fechada de animais. identificacao_animal continua gravado com o mesmo
    # número (compatibilidade com o filtro de GET /fotos e o rótulo da galeria).
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    # tipo_assunto == "lote": CSV de códigos de lote ("01,03") — mesmo formato de
    # AgendaManual.lotes e Lote.categorias; a foto nunca é consultada "por lote"
    # em JOIN, só exibida, então não há tabela de junção.
    lotes: Optional[str] = None
    # tipo_assunto == "outro": reproducao|producao|sanidade|alimentacao|estoque|outro
    assunto_fixo: Optional[str] = None
