"""
Agricultura — cadastro de Safra (silagem, grãos etc.), usado pelo relatório de
custo agrícola (ver fazenda.api.routers.relatorio_custo_safra) para apurar
R$/hectare e R$/tonelada a partir dos lançamentos do Financeiro. "Opção A" do
plano de custo da silagem: sem módulo de Lavoura/Safra completo (orçamento
pré-plantio, projeção "e se" etc.) — só o cadastro mínimo para dividir o total
gasto no centro de custo pelo hectare/tonelada da safra.

Submódulo de fazenda.models — parte da camada de dados SQLModel. Ver
fazenda/models/__init__.py para o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Safra(SQLModel, table=True):
    __tablename__ = "safra"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    # Nome do centro de custo (Financeiro) cujos lançamentos, no período
    # abaixo, formam o total apurado desta safra — ver CentroCusto/opções em
    # Configurações > Parâmetros financeiros. Padrão "Agricultura" (decisão do
    # usuário: já serve qualquer fazenda que planta para a produção do leite).
    centro_custo: str = "Agricultura"
    data_inicio: date
    data_fim: date
    hectares: float
    toneladas_produzidas: float
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
