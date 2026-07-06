"""
Camada de dados — modelos SQLModel (tabelas SQLite/PostgreSQL + validação Pydantic).
Cada modelo representa uma entidade do domínio da fazenda.

NOTA: Relacionamentos usam strings forward-reference para compatibilidade
com SQLModel 0.0.39 + SQLAlchemy 2.x (sem Mapped[] em modelos com table=True).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel


# ---------------------------------------------------------------------------
# Animal
# ---------------------------------------------------------------------------
class Animal(SQLModel, table=True):
    """Foto atual de cada animal — alimentado pelo GERAL.csv."""

    __tablename__ = "animal"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero: str = Field(index=True, unique=True)
    data_nasc: Optional[date] = None
    idade_meses: Optional[float] = None
    grupo_primario: Optional[str] = None
    grupo_raw: Optional[str] = None
    categoria_completa: Optional[str] = None
    categoria_abrev: Optional[str] = None
    raca: Optional[str] = None
    sit_rep: Optional[str] = None
    del_dias: Optional[int] = None
    data_ult_leite: Optional[date] = None
    ult_cl_kg: Optional[float] = None
    data_ult_diag: Optional[date] = None
    diagnostico: Optional[str] = None
    ativo: bool = True
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Serviço (IA / IATF / Cobertura)
# ---------------------------------------------------------------------------
class Servico(SQLModel, table=True):
    """Uma linha da tabela REPRODUTIVO — um serviço por linha."""

    __tablename__ = "servico"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    raca_matriz: Optional[str] = None
    data_nasc_matriz: Optional[date] = None
    data_ult_parto: Optional[date] = None
    ordem_parto: Optional[int] = None
    data_servico: Optional[date] = None
    tipo_servico: Optional[str] = None
    protocolo: Optional[str] = None
    reprodutor: Optional[str] = None
    ordem_tentativa: Optional[int] = None
    intervalo_tentativas: Optional[int] = None
    data_diagnostico: Optional[date] = None
    diagnostico: Optional[str] = None
    data_perda_prenhez: Optional[date] = None
    pev_dias: Optional[int] = None
    del_servico: Optional[int] = None
    ult_ocorrencia: Optional[int] = None
    categoria: Optional[str] = None
    producao_lactacao_anterior: Optional[float] = None
    duracao_lactacao_anterior: Optional[int] = None
    periodo_seco_anterior: Optional[int] = None


# ---------------------------------------------------------------------------
# Parto
# ---------------------------------------------------------------------------
class Parto(SQLModel, table=True):
    """Registro de parto extraído do campo REPRODUTIVO."""

    __tablename__ = "parto"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    data_parto: Optional[date] = None
    ordem_parto: Optional[int] = None
    tipo_parto: Optional[str] = None
    sexo_cria_1: Optional[str] = None
    sexo_cria_2: Optional[str] = None
    gemelar: Optional[bool] = None
    retencao_placenta: Optional[bool] = None


# ---------------------------------------------------------------------------
# Controle Leiteiro
# ---------------------------------------------------------------------------
class ControleLeiteiro(SQLModel, table=True):
    """Uma linha da lista de controles leiteiros por animal."""

    __tablename__ = "controle_leiteiro"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    raca: Optional[str] = None
    data_controle: Optional[date] = None
    producao_kg: Optional[float] = None
    del_no_controle: Optional[int] = None
    data_ult_parto: Optional[date] = None
    ordem_parto: Optional[int] = None


# ---------------------------------------------------------------------------
# Conta Gerencial (Financeiro)
# ---------------------------------------------------------------------------
class ContaGerencial(SQLModel, table=True):
    """Uma movimentação financeira do CONTA_GERENCIAL.csv."""

    __tablename__ = "conta_gerencial"

    id: Optional[int] = Field(default=None, primary_key=True)
    codigo_conta: Optional[str] = None
    descricao: Optional[str] = None
    data_vencimento: Optional[date] = None
    data_pagamento: Optional[date] = None
    data_competencia: Optional[date] = None
    data_emissao: Optional[date] = None
    fornecedor_cliente: Optional[str] = None
    numero_nota: Optional[str] = None
    valor_total: Optional[float] = None
    valor_pago: Optional[float] = None
    centro_custo: Optional[str] = None
    tipo: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Estoque
# ---------------------------------------------------------------------------
class Estoque(SQLModel, table=True):
    """Item de estoque do ESTOQUE.csv."""

    __tablename__ = "estoque"

    id: Optional[int] = Field(default=None, primary_key=True)
    categoria: Optional[str] = None
    numero_produto: Optional[str] = None
    nome: str = Field(index=True)
    quantidade: Optional[float] = None
    estoque_minimo: Optional[float] = None
    unidade: Optional[str] = None
    valor_unitario: Optional[float] = None
    valor_total: Optional[float] = None
    abaixo_minimo: Optional[bool] = None
    local_armazenamento: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Sanidade (medicamentos aplicados nos animais)
# ---------------------------------------------------------------------------
class Sanidade(SQLModel, table=True):
    """Uma aplicação de medicamento/vacina por linha — do SANIDADE.csv (Ideagri)."""

    __tablename__ = "sanidade"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    nome: Optional[str] = None
    data_nasc: Optional[date] = None
    sexo: Optional[str] = None
    raca: Optional[str] = None
    data_aplicacao: Optional[date] = Field(default=None, index=True)
    produto: str
    categoria: Optional[str] = None  # derivada (Vacina, Antiparasitário, ...)
    dose: Optional[float] = None
    lote: Optional[str] = None
    atividade: Optional[str] = None
    obs: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Dieta (plano alimentar por lote)
# ---------------------------------------------------------------------------
class Dieta(SQLModel, table=True):
    """Uma linha por (lote, ingrediente) do DIETA.csv — quantidade por cabeça/dia."""

    __tablename__ = "dieta"

    id: Optional[int] = Field(default=None, primary_key=True)
    lote: Optional[int] = Field(default=None, index=True)
    categoria: Optional[str] = None
    ingrediente: str
    quantidade: Optional[float] = None
    unidade: Optional[str] = None  # kg ou L, por cabeça/dia
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Agenda Manual
# ---------------------------------------------------------------------------
class AgendaManual(SQLModel, table=True):
    """Eventos adicionados manualmente — equivalente à aba AGENDA_MANUAL do Excel."""

    __tablename__ = "agenda_manual"

    id: Optional[int] = Field(default=None, primary_key=True)
    data_evento: date
    descricao: str
    categoria: str = "Gestão/Financeiro"
    numero_animal: Optional[str] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
