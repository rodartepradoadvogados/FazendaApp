"""
Arquivo fiscal-contábil integral e chamados de suporte do Painel do Contador.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Documento arquivado — nota fiscal, CCIR, IRPF/IRPJ, inscrição estadual,
# matrícula, contrato de trabalho/prestação de serviço, entre outros.
# Independente de lançamento (ao contrário de LancamentoAnexo, ver
# fazenda/models/financeiro.py) — o conteúdo do arquivo vive no Supabase
# Storage, aqui só ficam os metadados e o caminho (ver
# fazenda/rules/supabase_storage.py e fazenda/api/routers/documentos.py).
# ---------------------------------------------------------------------------
class DocumentoArquivado(SQLModel, table=True):
    __tablename__ = "documento_arquivado"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    categoria: str = Field(index=True)  # nome de um TipoDocumento cadastrado
    nome_original: str
    caminho_storage: str
    mime_type: str
    tamanho_bytes: int
    data_documento: Optional[date] = None
    data_upload: datetime = Field(default_factory=datetime.utcnow)
    enviado_por: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Resposta à pergunta "inserir no balanço?" feita no momento do upload —
    # quando True, numero_lancamento aponta para o lançamento financeiro
    # gerado a partir deste documento (ver ContaGerencial.numero_lancamento).
    inserir_no_balanco: bool = False
    numero_lancamento: Optional[str] = None
    descricao: Optional[str] = None


# ---------------------------------------------------------------------------
# Chamado — suporte aberto pelo contador (ou pela fazenda) ao administrador/
# CowData. Escrita bloqueada para o vínculo `contador` como qualquer outra
# escrita em Financeiro, a não ser com o cadeado destravado (ver
# fazenda/auth.py::bloquear_escrita_contador).
# ---------------------------------------------------------------------------
class Chamado(SQLModel, table=True):
    __tablename__ = "chamado"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    assunto: str
    descricao: str
    status: str = "aberto"  # aberto | em_andamento | resolvido
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    resposta: Optional[str] = None
