"""
Cobrança da assinatura CowData via Banco do Brasil (boleto + PIX) — ver
fazenda/rules/banco_brasil.py e fazenda/models/cobranca.py. Emissão exige
BB_CLIENT_ID/BB_CLIENT_SECRET/BB_DEVELOPER_APPLICATION_KEY configurados (ver
fazenda/config.py); sem isso, erro 400 explicando o que falta — mesmo padrão
do ZapSign em fazenda/api/routers/fazendas.py.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_dono
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import CobrancaBoleto, CobrancaPix, ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario
from fazenda.models.planos import PLANOS_CATALOGO
from fazenda.rules import banco_brasil

router = APIRouter(prefix="/cobranca", tags=["cobranca"])


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


class EmitirBoletoIn(BaseModel):
    pagador_nome: str
    pagador_documento: str  # CPF/CNPJ — Fazenda ainda não cadastra isso (ver Cláusula do contrato-modelo)
    data_vencimento: date


@router.post("/{fazenda_id}/boleto")
def emitir_boleto(fazenda_id: int, dados: EmitirBoletoIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    valor = _valor_mensal(session, fazenda_id)
    try:
        resposta = banco_brasil.emitir_boleto(f"fazenda-{fazenda_id}", valor, dados.data_vencimento, dados.pagador_nome, dados.pagador_documento)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o Banco do Brasil: {e}")

    boleto = CobrancaBoleto(
        fazenda_id=fazenda_id, numero_convenio=f"fazenda-{fazenda_id}",
        nosso_numero=resposta.get("nossoNumero"), linha_digitavel=resposta.get("linhaDigitavel"),
        codigo_barras=resposta.get("codigoBarraNumerico"), valor=valor, data_vencimento=dados.data_vencimento,
    )
    session.add(boleto)
    session.commit()
    session.refresh(boleto)
    return {"id": boleto.id, "linha_digitavel": boleto.linha_digitavel, "codigo_barras": boleto.codigo_barras, "valor": boleto.valor, "status": boleto.status}


@router.post("/{fazenda_id}/pix")
def emitir_pix(fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    valor = _valor_mensal(session, fazenda_id)
    txid = f"cowdata{fazenda_id}{int(datetime.utcnow().timestamp())}"
    try:
        resposta = banco_brasil.emitir_cobranca_pix(txid, valor)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o Banco do Brasil: {e}")

    cobranca = CobrancaPix(
        fazenda_id=fazenda_id, txid=txid, pix_copia_cola=resposta.get("pixCopiaECola"),
        qrcode_base64=resposta.get("qrcode"), valor=valor,
    )
    session.add(cobranca)
    session.commit()
    session.refresh(cobranca)
    return {"id": cobranca.id, "txid": cobranca.txid, "pix_copia_cola": cobranca.pix_copia_cola, "valor": cobranca.valor, "status": cobranca.status}


@router.get("/{fazenda_id}")
def listar_cobrancas(fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    boletos = session.exec(select(CobrancaBoleto).where(CobrancaBoleto.fazenda_id == fazenda_id)).all()
    pix = session.exec(select(CobrancaPix).where(CobrancaPix.fazenda_id == fazenda_id)).all()
    return {
        "boletos": [{"id": b.id, "valor": b.valor, "status": b.status, "data_vencimento": b.data_vencimento.isoformat(), "linha_digitavel": b.linha_digitavel} for b in boletos],
        "pix": [{"id": p.id, "txid": p.txid, "valor": p.valor, "status": p.status, "pix_copia_cola": p.pix_copia_cola} for p in pix],
    }


@router.post("/webhook/bb/{secret}")
async def cobranca_webhook_bb(secret: str, request: Request, session: Session = Depends(get_session)) -> dict:
    """Baixa automática — configurar esta URL no Portal Developers BB
    (Cobranças: webhook por convênio; PIX: PUT /pix/v2/webhook/{chave}).
    Payload varia por API (boleto x PIX); aqui aceitamos os dois formatos
    pelo campo presente (nossoNumero para boleto, txid para PIX)."""
    if not settings.bb_client_id:  # reaproveita a checagem de "BB configurado" — não há segredo de webhook próprio documentado
        raise HTTPException(status_code=403, detail="Banco do Brasil não configurado")
    payload = await request.json()

    if "txid" in payload:
        pix = session.exec(select(CobrancaPix).where(CobrancaPix.txid == payload["txid"])).first()
        if pix and payload.get("status") in ("CONCLUIDA", "paga"):
            pix.status = "paga"
            pix.pago_em = datetime.utcnow()
            session.add(pix)
            session.commit()
        return {"ok": True}

    nosso_numero = payload.get("nossoNumero") or payload.get("numero")
    if nosso_numero:
        boleto = session.exec(select(CobrancaBoleto).where(CobrancaBoleto.nosso_numero == nosso_numero)).first()
        if boleto and payload.get("codigoEstadoTituloCobranca") in ("06", "PAGO", "LIQUIDADO"):
            boleto.status = "paga"
            boleto.pago_em = datetime.utcnow()
            session.add(boleto)
            session.commit()
        return {"ok": True}

    return {"ignorado": True}
