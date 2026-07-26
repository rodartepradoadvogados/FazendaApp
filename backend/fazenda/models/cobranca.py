"""
Cobrança da assinatura CowData — Asaas (ativo, ver fazenda/rules/asaas.py) e
Banco do Brasil (scaffold inicial, ver fazenda/rules/banco_brasil.py).
Distinto do módulo Financeiro de cada fazenda (que já tem seu próprio
boleto/PIX para os CLIENTES da fazenda) — aqui é a CONTRATADA
(CowData/EmpresaOperadora) cobrando a mensalidade da fazenda-cliente pelo
plano contratado (ver fazenda/models/planos.py).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

STATUS_COBRANCA = ["emitida", "paga", "vencida", "cancelada"]

TIPO_COBRANCA_ASAAS = ["assinatura_mensal", "pix_semestral", "boleto"]


class CobrancaBoleto(SQLModel, table=True):
    """Um boleto emitido pela API "Cobranças" do BB para uma fazenda-cliente.
    `status` começa "emitida" e é atualizado pelo webhook de baixa automática
    (fazenda/api/routers/cobranca.py::cobranca_webhook_bb) quando o BB avisa
    o pagamento — nunca por polling do frontend."""

    __tablename__ = "cobranca_boleto"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    numero_convenio: str
    nosso_numero: Optional[str] = None
    linha_digitavel: Optional[str] = None
    codigo_barras: Optional[str] = None
    valor: float
    data_vencimento: date
    status: str = "emitida"
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    pago_em: Optional[datetime] = None


class CobrancaPix(SQLModel, table=True):
    """Uma cobrança PIX imediata (`txid`) emitida pela API PIX do BB — devolve
    o payload BR Code pronto pro QR e a string "copia e cola" (`pix_copia_cola`).
    Baixa automática pelo mesmo webhook de boleto (evento diferente, mesmo secret)."""

    __tablename__ = "cobranca_pix"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    txid: str = Field(index=True, unique=True)
    pix_copia_cola: Optional[str] = None
    qrcode_base64: Optional[str] = None
    valor: float
    status: str = "emitida"
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    pago_em: Optional[datetime] = None


class CobrancaAsaas(SQLModel, table=True):
    """Uma cobrança ou assinatura criada no Asaas para uma fazenda-cliente —
    `referencia_asaas` é o id do payment ("pay_...") ou da subscription
    ("sub_...") retornado pela API (ver fazenda/rules/asaas.py). `status`
    começa "emitida" e só muda para "paga" depois que o webhook (ver
    fazenda/api/routers/asaas.py::asaas_webhook) RE-CONFIRMA o pagamento
    direto na API do Asaas — nunca confia só no corpo do webhook recebido."""

    __tablename__ = "cobranca_asaas"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    tipo: str  # ver TIPO_COBRANCA_ASAAS
    referencia_asaas: str = Field(index=True, unique=True)
    asaas_customer_id: str
    valor: float
    status: str = "emitida"
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    pago_em: Optional[datetime] = None
