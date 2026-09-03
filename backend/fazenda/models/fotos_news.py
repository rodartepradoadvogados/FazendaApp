"""
Banco de fotos do Milknews — imagens usadas para ilustrar as matérias do
blog News (campo NoticiaNews.imagem, ver fazenda/models/sistema.py), enviadas
e organizadas em pastas pela aba de Aprovações. Guardadas no Supabase
Storage, bucket público settings.supabase_bucket_news_fotos (ver
fazenda/rules/supabase_storage.py e fazenda/api/routers/fotos_news.py) —
diferente de FotoCampo (fazenda/models/fotos.py), que é privado e por
fazenda, este banco é global (compartilhado por todas as fazendas) e
público, porque a página do blog é lida sem login.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PastaFotoNews(SQLModel, table=True):
    __tablename__ = "pasta_foto_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    criado_por: Optional[int] = Field(default=None, foreign_key="usuario.id")


class FotoNews(SQLModel, table=True):
    __tablename__ = "foto_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    # None = foto solta na raiz do banco, fora de qualquer pasta.
    pasta_id: Optional[int] = Field(default=None, foreign_key="pasta_foto_news.id", index=True)
    nome_arquivo: str
    caminho_storage: str
    mime_type: str
    tamanho_bytes: int
    # Tags livres em PT-BR, separadas por vírgula (mesmo padrão do manifest.json
    # do banco estático em frontend/public/news-images/) — ajuda a casar foto
    # com assunto ao escolher a ilustração de uma matéria.
    tags: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    enviado_por: Optional[int] = Field(default=None, foreign_key="usuario.id")
