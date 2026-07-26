"""
Webhook do ZapSign — recebe o aviso de assinatura do contrato e atualiza
ContratoAssinaturaZapSign (ver fazenda/rules/zapsign.py e o botão "Assinar
contrato" em fazenda/api/routers/fazendas.py). O ZapSign não documenta um
cabeçalho de assinatura HMAC própria, então o segredo vai na própria URL
(mesmo princípio do webhook do Telegram, que usa um header — aqui não temos
como exigir header customizado do lado do ZapSign): configure em
Configurações > Webhooks do painel ZapSign a URL
"{PUBLIC_BASE_URL}/zapsign/webhook/{ZAPSIGN_WEBHOOK_SECRET}".
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import ContratoAssinaturaZapSign

router = APIRouter(prefix="/zapsign", tags=["zapsign"])


@router.post("/webhook/{secret}")
async def zapsign_webhook(secret: str, request: Request, session: Session = Depends(get_session)) -> dict:
    if not settings.zapsign_webhook_secret or secret != settings.zapsign_webhook_secret:
        raise HTTPException(status_code=403, detail="Segredo inválido")

    payload = await request.json()
    document_token = payload.get("token")
    status = payload.get("status")
    if not document_token or not status:
        return {"ignorado": True}

    tentativa = session.exec(
        select(ContratoAssinaturaZapSign).where(ContratoAssinaturaZapSign.document_token == document_token)
    ).first()
    if not tentativa:
        return {"ignorado": True, "motivo": "document_token desconhecido"}
    tentativa.status = status
    if status == "signed" and not tentativa.assinado_em:
        tentativa.assinado_em = datetime.utcnow()
    session.add(tentativa)
    session.commit()
    return {"ok": True}
