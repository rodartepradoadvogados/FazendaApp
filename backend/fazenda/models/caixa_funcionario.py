"""
Caixa dos funcionários — saldo a favor de cada colaborador (CLT, empreita,
contrato, diária), movimentado só por lançamentos (nada é editado nem apagado
sem rastro: erro se corrige por estorno).

O saldo NÃO é uma coluna: é a soma de `CaixaMovimento.valor` da pessoa. Entrada
tem valor positivo; retirada e estorno de entrada, negativo.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class CaixaMovimento(SQLModel, table=True):
    __tablename__ = "caixa_movimento"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    pessoa_id: int = Field(foreign_key="pessoa.id", index=True)
    # deposito | bonificacao | comissao | outro | retirada | estorno
    tipo: str = Field(index=True)
    valor: float  # com sinal: + entrada, − retirada/estorno de entrada
    data: date
    motivo: str
    # Só em comissão: base e percentual informados (o valor é calculado deles).
    base_valor: Optional[float] = None
    percentual: Optional[float] = None
    # Financeiro: entrada da fazenda gera uma despesa de pessoal (ContaGerencial);
    # estorno dela gera o lançamento contrário.
    lancamento_id: Optional[int] = Field(default=None, foreign_key="conta_gerencial.id")
    numero_lancamento: Optional[str] = None
    # Retirada: dados do pagamento e número do recibo (CX-AAAA-nnnnn).
    forma_pagamento: Optional[str] = None
    conta_bancaria: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    numero_recibo: Optional[str] = None
    # Retenção em folha: a folha (FolhaPagamento.id) cujo pagamento gerou este movimento.
    folha_id: Optional[int] = Field(default=None, index=True)
    # Estorno: aponta o movimento estornado.
    estorna_id: Optional[int] = Field(default=None, foreign_key="caixa_movimento.id", index=True)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class CaixaRetencao(SQLModel, table=True):
    """Combinado de retenção em folha de UMA pessoa (um por pessoa; edita-se o mesmo).

    Só roda com `autorizada` marcada (marcação interna). O termo em papel é anexado
    depois, como anexo da pessoa (categoria "Termo de retenção do caixa"); enquanto
    não houver anexo, a retenção continua rodando e fica PENDENTE na Agenda e no
    Fechamento da folha. Revogar encerra a vigência no fim do mês corrente (vale a
    partir do mês seguinte)."""

    __tablename__ = "caixa_retencao"
    __table_args__ = (UniqueConstraint("fazenda_id", "pessoa_id", name="uq_caixa_retencao_fazenda_pessoa"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    pessoa_id: int = Field(foreign_key="pessoa.id", index=True)
    forma: str = "fixo"  # fixo (R$ por mês) | percentual (% do salário-base)
    valor: float = 0.0
    teto: Optional[float] = None  # saldo retido máximo; a retenção para ao alcançá-lo
    destino: str = "individual"  # individual (o caixa do time entra na Fase 3)
    inicio: date
    fim: Optional[date] = None  # None = sem fim de vigência
    pausada: bool = False
    autorizada: bool = False
    autorizada_em: Optional[date] = None
    revogada_em: Optional[date] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
