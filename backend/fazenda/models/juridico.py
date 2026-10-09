"""
Registros jurídicos das réguas de referência e dos Termos (parecer de 08/10/2026,
itens 6.1, 6.2 e 6.3):

- `AceiteTermos`: log APPEND-ONLY de cada aceite (geral dos Termos, cláusula em
  destaque, modal "Entendi" das réguas) — versão e SHA-256 do texto aceito, data/hora
  UTC, IP e user-agent. É prova: nunca é editado nem apagado.
- `ExportacaoRelatorioLog`: log APPEND-ONLY de cada exportação/compartilhamento de
  relatório (quem, quando, para quem, para quê, versão das réguas, com ou sem réguas).
- `ReguaErroReportado`: botão "Reportar erro na faixa" (política 7.4). Este NÃO é
  append-only: o operador CowData registra o andamento (status/resposta).

Imutabilidade em duas camadas:
1. ORM (vale para todo código do sistema): `before_flush` recusa UPDATE/DELETE de
   instâncias append-only, e `do_orm_execute` recusa `update()`/`delete()` em massa
   dessas tabelas;
2. banco: gatilhos BEFORE UPDATE/DELETE criados junto com a tabela (create_all e a
   migração), que barram até SQL cru. Em PostgreSQL, a função
   `cowdata_bloquear_append_only()`; em SQLite, RAISE(ABORT).

LGPD: guarda-se só o necessário para a prova (usuário, fazenda, IP, user-agent).
O e-mail/nome do usuário não é copiado: vem do cadastro na hora do comprovante.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DDL, event
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Field, SQLModel

LIMITE_USER_AGENT = 512
LIMITE_TEXTO_ERRO = 1000


class RegistroImutavelError(Exception):
    """Tentativa de alterar ou apagar um registro append-only."""


class AceiteTermos(SQLModel, table=True):
    __tablename__ = "aceite_termos"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    tipo: str = Field(index=True)  # "geral" | "clausula" | "reguas"
    texto_chave: str  # chave em seed_data/textos_juridicos.json
    versao: str
    sha256: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)  # UTC


class ExportacaoRelatorioLog(SQLModel, table=True):
    __tablename__ = "exportacao_relatorio_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    relatorio: str
    formato: Optional[str] = None  # "pdf" | "xlsx" | "csv" | "link"
    com_reguas: bool = False
    destinatario: Optional[str] = None
    destinatario_tipo: Optional[str] = None  # "banco" | "contador" | "comprador" | "outro"
    finalidade: Optional[str] = None
    autorizacao_confirmada: bool = False
    versao_reguas: Optional[str] = None
    rodape_versao: Optional[str] = None
    rodape_sha256: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)  # UTC


class ReguaErroReportado(SQLModel, table=True):
    __tablename__ = "regua_erro_reportado"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    regua_codigo: str = Field(index=True)
    texto: str
    versao_reguas: str
    status: str = Field(default="aberto", index=True)  # aberto | em_analise | resolvido | descartado
    resposta: Optional[str] = None
    tratado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    tratado_em: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)  # UTC


# ---------------------------------------------------------------------------
# Append-only
# ---------------------------------------------------------------------------
MODELOS_APPEND_ONLY = (AceiteTermos, ExportacaoRelatorioLog)
TABELAS_APPEND_ONLY = tuple(m.__tablename__ for m in MODELOS_APPEND_ONLY)


def _recusar(nome: str, acao: str) -> None:
    raise RegistroImutavelError(f"{nome} é append-only (registro de prova): {acao} proibido")


@event.listens_for(OrmSession, "before_flush")
def _travar_alteracao_append_only(session, _flush_context, _instances) -> None:
    for obj in session.deleted:
        if isinstance(obj, MODELOS_APPEND_ONLY):
            _recusar(obj.__tablename__, "DELETE")
    for obj in session.dirty:
        if isinstance(obj, MODELOS_APPEND_ONLY) and session.is_modified(obj, include_collections=False):
            _recusar(obj.__tablename__, "UPDATE")


@event.listens_for(OrmSession, "do_orm_execute")
def _travar_dml_em_massa(state) -> None:
    if not (state.is_update or state.is_delete):
        return
    tabela = getattr(state.statement, "table", None)
    nome = getattr(tabela, "name", None)
    if nome in TABELAS_APPEND_ONLY:
        _recusar(nome, "UPDATE" if state.is_update else "DELETE")


FUNCAO_PG = "cowdata_bloquear_append_only"


def ddl_gatilhos(dialeto: str, tabela: str) -> list[str]:
    """Comandos que criam (idempotente) os gatilhos de uma tabela append-only.
    Usados aqui (create_all) e na migração."""
    if dialeto == "postgresql":
        return [
            f"CREATE OR REPLACE FUNCTION {FUNCAO_PG}() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN RAISE EXCEPTION USING MESSAGE = TG_TABLE_NAME || ' é append-only: UPDATE/DELETE proibido'; END; $$",
            f"DROP TRIGGER IF EXISTS trg_{tabela}_append_only ON {tabela}",
            f"CREATE TRIGGER trg_{tabela}_append_only BEFORE UPDATE OR DELETE ON {tabela} "
            f"FOR EACH ROW EXECUTE PROCEDURE {FUNCAO_PG}()",
        ]
    if dialeto == "sqlite":
        return [
            f"CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_update BEFORE UPDATE ON {tabela} "
            f"BEGIN SELECT RAISE(ABORT, '{tabela} é append-only: UPDATE proibido'); END",
            f"CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_delete BEFORE DELETE ON {tabela} "
            f"BEGIN SELECT RAISE(ABORT, '{tabela} é append-only: DELETE proibido'); END",
        ]
    return []


for _modelo in MODELOS_APPEND_ONLY:
    _tabela = _modelo.__table__
    for _dialeto in ("postgresql", "sqlite"):
        for _cmd in ddl_gatilhos(_dialeto, _tabela.name):
            event.listen(_tabela, "after_create", DDL(_cmd).execute_if(dialect=_dialeto))
