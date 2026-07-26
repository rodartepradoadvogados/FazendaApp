"""
Cobrança da assinatura CowData via Asaas — assinatura mensal (Pix), cobrança
avulsa Pix (desconto semestral) e boleto. Ver fazenda/rules/asaas.py e
fazenda/models/cobranca.py::CobrancaAsaas.

Segurança do webhook (o pedido explícito era "ninguém consiga enviar sinal de
pago pro nosso backend"): (1) token fixo no header `asaas-access-token`,
comparado a ASAAS_WEBHOOK_TOKEN; (2) mesmo com o token batendo, o webhook
NUNCA confia no `status` do corpo recebido — ele só usa o payload pra saber
QUAL cobrança consultar, e então chama a API do Asaas (`consultar_cobranca`,
GET direto, autenticado com nossa própria API key) pra confirmar o status de
verdade antes de marcar como paga ou liberar qualquer acesso; (3)
idempotência: se a cobrança já está "paga" no nosso banco, o webhook não
repete a liberação de acesso.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_dono
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import CobrancaAsaas, ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario
from fazenda.models.planos import DESCONTO_CICLO_PAGAMENTO, MESES_POR_CICLO, PLANOS_CATALOGO
from fazenda.rules import asaas

router = APIRouter(prefix="/asaas", tags=["asaas"])


def _valor_mensal(session: Session, fazenda_id: int) -> float:
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    if not contrato:
        raise HTTPException(status_code=400, detail="Fazenda ainda não tem contrato definido")
    if contrato.plano and contrato.plano in PLANOS_CATALOGO:
        return PLANOS_CATALOGO[contrato.plano]["preco"]
    modulos = session.exec(
        select(ContratoFazendaModulo).where(ContratoFazendaModulo.fazenda_id == fazenda_id, ContratoFazendaModulo.ativo == True)  # noqa: E712
    ).all()
    return sum(m.preco for m in modulos)


def _obter_ou_criar_customer_id(session: Session, fazenda_id: int, nome: str, documento: str, email: str | None) -> str:
    existente = session.exec(
        select(CobrancaAsaas).where(CobrancaAsaas.fazenda_id == fazenda_id).order_by(CobrancaAsaas.criado_em.desc())
    ).first()
    if existente:
        return existente.asaas_customer_id
    cliente = asaas.criar_cliente(nome, documento, email)
    return cliente["id"]


class CobrancaAsaasIn(BaseModel):
    pagador_nome: str
    pagador_documento: str  # CPF/CNPJ — mesmo gap do contrato-modelo (Fazenda ainda não cadastra isso)
    pagador_email: str | None = None


def _erro_asaas(e: Exception) -> HTTPException:
    if isinstance(e, RuntimeError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=502, detail=f"Falha ao comunicar com o Asaas: {e}")


@router.post("/{fazenda_id}/assinatura")
def criar_assinatura_mensal(fazenda_id: int, dados: CobrancaAsaasIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    """Assinatura mensal recorrente via Pix (cobrada automaticamente a cada vencimento)."""
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    valor = _valor_mensal(session, fazenda_id)
    try:
        customer_id = _obter_ou_criar_customer_id(session, fazenda_id, dados.pagador_nome, dados.pagador_documento, dados.pagador_email)
        resposta = asaas.criar_assinatura_pix(
            customer_id, valor, (date.today() + timedelta(days=1)).isoformat(), f"CowData — assinatura mensal ({fazenda.nome})",
        )
    except Exception as e:
        raise _erro_asaas(e)

    cobranca = CobrancaAsaas(fazenda_id=fazenda_id, tipo="assinatura_mensal", referencia_asaas=resposta["id"], asaas_customer_id=customer_id, valor=valor)
    session.add(cobranca)
    session.commit()
    session.refresh(cobranca)
    return {"id": cobranca.id, "referencia_asaas": cobranca.referencia_asaas, "status": cobranca.status}


@router.post("/{fazenda_id}/pix-semestral")
def criar_cobranca_pix_semestral(fazenda_id: int, dados: CobrancaAsaasIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    """QR Code Pix dinâmico avulso, valor do ciclo semestral já com 20% de desconto."""
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    preco_mensal = _valor_mensal(session, fazenda_id)
    desconto = DESCONTO_CICLO_PAGAMENTO["semestral"]
    meses = MESES_POR_CICLO["semestral"]
    valor_total = round(preco_mensal * meses * (1 - desconto), 2)
    try:
        customer_id = _obter_ou_criar_customer_id(session, fazenda_id, dados.pagador_nome, dados.pagador_documento, dados.pagador_email)
        resposta = asaas.criar_cobranca_pix(
            customer_id, valor_total, (date.today() + timedelta(days=2)).isoformat(),
            f"CowData — assinatura semestral com 20% off ({fazenda.nome})",
        )
    except Exception as e:
        raise _erro_asaas(e)

    cobranca = CobrancaAsaas(fazenda_id=fazenda_id, tipo="pix_semestral", referencia_asaas=resposta["id"], asaas_customer_id=customer_id, valor=valor_total)
    session.add(cobranca)
    session.commit()
    session.refresh(cobranca)
    return {"id": cobranca.id, "referencia_asaas": cobranca.referencia_asaas, "valor": valor_total, "pix_qr_code": resposta.get("pixQrCode"), "invoice_url": resposta.get("invoiceUrl"), "status": cobranca.status}


@router.post("/{fazenda_id}/boleto")
def criar_cobranca_boleto(fazenda_id: int, dados: CobrancaAsaasIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    valor = _valor_mensal(session, fazenda_id)
    try:
        customer_id = _obter_ou_criar_customer_id(session, fazenda_id, dados.pagador_nome, dados.pagador_documento, dados.pagador_email)
        resposta = asaas.criar_cobranca_boleto(
            customer_id, valor, (date.today() + timedelta(days=5)).isoformat(), f"CowData — mensalidade ({fazenda.nome})",
        )
    except Exception as e:
        raise _erro_asaas(e)

    cobranca = CobrancaAsaas(fazenda_id=fazenda_id, tipo="boleto", referencia_asaas=resposta["id"], asaas_customer_id=customer_id, valor=valor)
    session.add(cobranca)
    session.commit()
    session.refresh(cobranca)
    return {"id": cobranca.id, "referencia_asaas": cobranca.referencia_asaas, "invoice_url": resposta.get("invoiceUrl"), "status": cobranca.status}


@router.get("/{fazenda_id}")
def listar_cobrancas_asaas(fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    cobrancas = session.exec(select(CobrancaAsaas).where(CobrancaAsaas.fazenda_id == fazenda_id).order_by(CobrancaAsaas.criado_em.desc())).all()
    return [{"id": c.id, "tipo": c.tipo, "valor": c.valor, "status": c.status, "criado_em": c.criado_em.isoformat(), "pago_em": c.pago_em.isoformat() if c.pago_em else None} for c in cobrancas]


@router.post("/webhook")
async def asaas_webhook(
    request: Request, session: Session = Depends(get_session),
    asaas_access_token: str | None = Header(default=None, alias="asaas-access-token"),
) -> dict:
    if not settings.asaas_webhook_token or asaas_access_token != settings.asaas_webhook_token:
        raise HTTPException(status_code=403, detail="Token inválido")

    payload = await request.json()
    payment_id = (payload.get("payment") or {}).get("id")
    if not payment_id:
        return {"ignorado": True}

    cobranca = session.exec(select(CobrancaAsaas).where(CobrancaAsaas.referencia_asaas == payment_id)).first()
    if not cobranca:
        return {"ignorado": True, "motivo": "referência desconhecida"}
    if cobranca.status == "paga":
        return {"ok": True, "ja_processado": True}  # idempotência — webhook pode repetir a mesma notificação

    # Nunca confia no "status" do corpo do webhook — reconfirma direto na API
    # do Asaas, autenticado com nossa própria chave, antes de liberar acesso.
    try:
        confirmado = asaas.consultar_cobranca(payment_id)
    except Exception as e:
        raise _erro_asaas(e)
    if confirmado.get("status") not in ("RECEIVED", "CONFIRMED"):
        return {"ok": True, "status_atual": confirmado.get("status")}

    cobranca.status = "paga"
    cobranca.pago_em = datetime.utcnow()
    session.add(cobranca)

    # Liberação automática de acesso — mesma transição que o dono faria à mão
    # em Fazendas > Contrato > Aprovar/Fechar contrato (ver fazendas.py).
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == cobranca.fazenda_id)).first()
    if contrato and contrato.status != "ativo":
        contrato.status = "ativo"
        contrato.data_fechamento = datetime.utcnow()
        contrato.atualizado_em = datetime.utcnow()
        session.add(contrato)

    session.commit()
    return {"ok": True}
