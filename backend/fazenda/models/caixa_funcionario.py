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
    # Retenção no pagamento de quem não é CLT (parcela de contrato/empreita, diária): a conta paga que a gerou.
    origem_conta_id: Optional[int] = Field(default=None, index=True)
    # Rateio do PL: o rateio (CaixaRateio.id) cujo crédito gerou este movimento.
    rateio_id: Optional[int] = Field(default=None, index=True)
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
    # individual | time | dividir (parte para o caixa do time, o resto no individual)
    destino: str = "individual"
    time_id: Optional[int] = None
    pct_time: float = 50.0  # só em "dividir": % do retido que vai para o caixa do time
    inicio: date
    fim: Optional[date] = None  # None = sem fim de vigência
    pausada: bool = False
    autorizada: bool = False
    autorizada_em: Optional[date] = None
    revogada_em: Optional[date] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Fase 3 — Caixa do time (participação nos lucros) e rateio
# ---------------------------------------------------------------------------
class CaixaTime(SQLModel, table=True):
    """Um caixa coletivo (ex.: "Turma da ordenha"). O dinheiro é do time e é
    repartido em datas fixas (rateio do PL). Os membros entram por nome
    (`CaixaTimeMembro`) e/ou por tipo (`auto_tipos`, CSV de clt|empreita|contrato|diaria:
    todos os ativos daquele tipo, que se atualiza sozinho)."""

    __tablename__ = "caixa_time"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str
    auto_tipos: str = ""
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class CaixaTimeMembro(SQLModel, table=True):
    __tablename__ = "caixa_time_membro"
    __table_args__ = (UniqueConstraint("time_id", "pessoa_id", name="uq_caixa_time_membro"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    time_id: int = Field(foreign_key="caixa_time.id", index=True)
    pessoa_id: int = Field(foreign_key="pessoa.id", index=True)
    entrada: date
    saida: Optional[date] = None


class CaixaTimeMovimento(SQLModel, table=True):
    """Movimento do caixa do time. O saldo é a soma de `valor` (entrada +, rateio e
    estorno de entrada −). Entrada da fazenda gera despesa de pessoal baixada."""

    __tablename__ = "caixa_time_movimento"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    time_id: int = Field(foreign_key="caixa_time.id", index=True)
    tipo: str = Field(index=True)  # deposito | bonificacao | comissao | outro | rateio | estorno
    valor: float
    data: date
    motivo: str
    lancamento_id: Optional[int] = Field(default=None, foreign_key="conta_gerencial.id")
    numero_lancamento: Optional[str] = None
    rateio_id: Optional[int] = Field(default=None, index=True)
    folha_id: Optional[int] = Field(default=None, index=True)  # retenção de folha com destino time
    origem_conta_id: Optional[int] = Field(default=None, index=True)  # retenção de pagamento (não-CLT) com destino time
    estorna_id: Optional[int] = Field(default=None, foreign_key="caixa_time_movimento.id", index=True)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class CaixaRateio(SQLModel, table=True):
    __tablename__ = "caixa_rateio"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    time_id: int = Field(foreign_key="caixa_time.id", index=True)
    periodo_inicio: date
    periodo_fim: date
    data_entrega: date
    total: float = 0.0  # saldo do caixa do time na criação do rascunho
    situacao: str = "rascunho"  # rascunho | confirmado | desfeito
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    confirmado_em: Optional[datetime] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class CaixaRateioLinha(SQLModel, table=True):
    __tablename__ = "caixa_rateio_linha"
    __table_args__ = (UniqueConstraint("rateio_id", "pessoa_id", name="uq_caixa_rateio_linha"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    rateio_id: int = Field(foreign_key="caixa_rateio.id", index=True)
    pessoa_id: int = Field(foreign_key="pessoa.id", index=True)
    dias: int = 0
    parte_calculada: float = 0.0  # proporcional aos dias
    penalidade_pct: float = 0.0  # 0–100; a parte retirada vai para os demais
    penalidade_motivo: Optional[str] = None
    documento_anexo_id: Optional[int] = None  # PessoaAnexo (ciência da penalidade), obrigatório se penalidade > 0
    parte_final: float = 0.0
    destino: str = "individual"  # individual (crédito no caixa) | direto (crédito + retirada imediata)
    forma_pagamento: Optional[str] = None  # só no pagamento direto
    movimento_id: Optional[int] = None  # CaixaMovimento do crédito
    retirada_id: Optional[int] = None  # CaixaMovimento da retirada (pagamento direto)
