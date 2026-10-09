"""
Fechamento do mês e conciliação bancária (Fase C5 dos Relatórios do Financeiro —
ver docs/financeiro-fechamento-conciliacao.md).

- `FechamentoMesEvento`: TRILHA APPEND-ONLY do fechamento por fazenda e mês.
  Cada "Fechar" e cada "Reabrir com motivo" é uma linha nova — nunca se edita
  nem se apaga uma linha (mesmas duas camadas de `juridico.py`: ORM e gatilho
  no banco). O estado do mês é o do ÚLTIMO evento. O fechamento guarda o
  RETRATO dos totais (DRE de competência e de caixa, movimento de caixa e
  saldos por conta) em JSON e o SHA-256 desse JSON: quem reabre e fecha de
  novo vê se o número mudou.
- `ExtratoImportacao`: um arquivo de extrato importado (OFX ou CSV) numa conta
  corrente — período, saldo final informado pelo banco e contagem de linhas.
  O arquivo em si NÃO é guardado (LGPD: só o necessário para conciliar).
- `ExtratoLinha`: um movimento do extrato (data, valor com sinal, histórico
  curto do banco, nº do documento/FITID) e o pareamento com o sistema: um
  lançamento pago (`ContaGerencial`) ou uma transferência entre contas, ou a
  marca "sem lançamento" (tarifa, IOF... que ninguém lança).

Nenhuma destas tabelas muda número de relatório: o fechamento só TRAVA a
edição (com a flag `financeiro_regras_v2`), e a conciliação só lê.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import DDL, event
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Field, SQLModel, UniqueConstraint

from .juridico import RegistroImutavelError, ddl_gatilhos

LIMITE_HISTORICO_EXTRATO = 120
LIMITE_MOTIVO = 500


class FechamentoMesEvento(SQLModel, table=True):
    """Um evento da trilha do fechamento: "fechar" ou "reabrir" o mês `mes`
    ("AAAA-MM") da fazenda. APPEND-ONLY."""

    __tablename__ = "fechamento_mes_evento"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    mes: str = Field(index=True)  # "2026-09"
    acao: str  # "fechar" | "reabrir"
    motivo: Optional[str] = None  # obrigatório para reabrir e para fechar com pendências
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Nome de quem fez, copiado na hora: a trilha é prova e não pode mudar se o
    # cadastro do usuário mudar depois.
    usuario_nome: Optional[str] = None
    # Retrato dos totais no momento (JSON canônico) + SHA-256 dele. Só no "fechar".
    retrato_json: Optional[str] = None
    retrato_sha256: Optional[str] = None
    # Pendências do checklist que existiam quando o mês foi fechado assim mesmo.
    pendencias_no_fechamento: int = 0
    criado_em: datetime = Field(default_factory=datetime.utcnow)  # UTC


class ExtratoImportacao(SQLModel, table=True):
    __tablename__ = "extrato_importacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    conta_corrente_id: int = Field(foreign_key="conta_corrente.id", index=True)
    formato: str  # "ofx" | "csv"
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    # Saldo do extrato no fim do dia `data_saldo` (OFX: LEDGERBAL; CSV: coluna
    # ou linha de saldo). Sem ele, a tela compara pelo movimento do mês.
    saldo_final: Optional[float] = None
    data_saldo: Optional[date] = None
    linhas_novas: int = 0
    linhas_repetidas: int = 0
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ExtratoLinha(SQLModel, table=True):
    __tablename__ = "extrato_linha"
    __table_args__ = (
        UniqueConstraint("fazenda_id", "conta_corrente_id", "chave_dedup", name="uq_extrato_linha_dedup"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    conta_corrente_id: int = Field(foreign_key="conta_corrente.id", index=True)
    importacao_id: Optional[int] = Field(default=None, foreign_key="extrato_importacao.id", index=True)
    data: date = Field(index=True)
    valor: float  # com sinal: entrada > 0, saída < 0
    historico: Optional[str] = None  # texto do banco, cortado em LIMITE_HISTORICO_EXTRATO
    documento: Optional[str] = None  # nº do documento / cheque
    # FITID do OFX, ou hash de (data, valor, histórico, documento, ordem) no CSV:
    # importar o mesmo extrato duas vezes não duplica.
    chave_dedup: str
    status: str = Field(default="pendente", index=True)  # "pendente" | "pareado" | "sem_lancamento"
    lancamento_id: Optional[int] = Field(default=None, foreign_key="conta_gerencial.id", index=True)
    transferencia_id: Optional[int] = Field(default=None, foreign_key="transferencia_contas.id", index=True)
    observacao: Optional[str] = None  # motivo do "sem lançamento"
    conciliado_por: Optional[int] = Field(default=None, foreign_key="usuario.id")
    conciliado_em: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Append-only da trilha do fechamento (mesmo desenho de juridico.py)
# ---------------------------------------------------------------------------
@event.listens_for(OrmSession, "before_flush")
def _travar_trilha_fechamento(session, _flush_context, _instances) -> None:
    for obj in session.deleted:
        if isinstance(obj, FechamentoMesEvento):
            raise RegistroImutavelError("fechamento_mes_evento é append-only (trilha): DELETE proibido")
    for obj in session.dirty:
        if isinstance(obj, FechamentoMesEvento) and session.is_modified(obj, include_collections=False):
            raise RegistroImutavelError("fechamento_mes_evento é append-only (trilha): UPDATE proibido")


@event.listens_for(OrmSession, "do_orm_execute")
def _travar_dml_trilha_fechamento(state) -> None:
    if not (state.is_update or state.is_delete):
        return
    tabela = getattr(state.statement, "table", None)
    if getattr(tabela, "name", None) == FechamentoMesEvento.__tablename__:
        raise RegistroImutavelError("fechamento_mes_evento é append-only (trilha): UPDATE/DELETE proibido")


for _dialeto in ("postgresql", "sqlite"):
    for _cmd in ddl_gatilhos(_dialeto, FechamentoMesEvento.__tablename__):
        event.listen(FechamentoMesEvento.__table__, "after_create", DDL(_cmd).execute_if(dialect=_dialeto))
