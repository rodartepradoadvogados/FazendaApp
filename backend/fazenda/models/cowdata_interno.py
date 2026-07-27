"""
Financeiro interno da própria CowData (empresa operadora) — INDEPENDENTE do
Financeiro de qualquer Fazenda-cliente. Ver fazenda/models/multitenant.py::
Fazenda.eh_empresa_cowdata (a fazenda "lógica" que ancora Pessoa/FolhaPagamento
e este lançamento, sem nunca aparecer nas listagens de fazendas-clientes).

Deliberadamente um livro-caixa simples (não reaproveita o motor de Conta
Gerencial/LancamentoItem do Financeiro de fazenda) — é exatamente esse
isolamento que torna o controle "independente": nenhuma consulta daqui cruza
com dados de nenhuma fazenda-cliente, e nenhum módulo comercial trava o
lançamento (é sempre a própria CowData usando o próprio sistema).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

TIPOS_LANCAMENTO_COWDATA = ["receita", "despesa"]


class LancamentoCowData(SQLModel, table=True):
    """Uma receita ou despesa da própria empresa CowData (aluguel de servidor,
    ferramentas, marketing, serviço avulso etc.) — ver DRE/Fluxo de
    Caixa/Livro Caixa em fazenda/api/routers/painel_cowdata.py, que também
    somam a receita de assinatura (CobrancaAsaas paga) como receita real,
    sem duplicar lançamento manual para o que já é cobrado automaticamente."""

    __tablename__ = "lancamento_cowdata"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str  # receita | despesa
    categoria: str
    descricao: str
    contraparte: Optional[str] = None  # fornecedor (despesa) ou cliente (receita avulsa)
    valor: float
    data: date
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
