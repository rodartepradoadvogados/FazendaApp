"""
Aceites registrados (parecer de 08/10/2026, item 6.1): clickwrap geral dos Termos,
cláusula em destaque e modal "Entendi" das réguas de referência.

Cada aceite aponta a versão e o SHA-256 do texto EXATO que a pessoa viu (ver
rules/textos_juridicos.py). O registro só é aceito se versão e hash forem os
VIGENTES — um front com texto velho em cache recebe 409 e precisa recarregar.
"Aceite pendente" = não existe aceite deste usuário, nesta fazenda, com o hash do
texto vigente: texto novo (nova versão, empresa preenchida, trecho do método que
passou a valer) pede aceite novo, como o parecer pede (6.1.3 e 6.1.9).

O clickwrap de cadastro (tipo "geral") e o da cláusula ("clausula") já têm a
infraestrutura (tabela, hash, endpoint), mas o texto está marcado `pendente` em
textos_juridicos.json: os Termos de Uso dependem da empresa constituída. Enquanto
isso, `registrar` recusa esses dois tipos com 409.

LGPD: IP e user-agent são lidos da requisição e gravados SÓ no registro do aceite
(não vão para log de aplicação); o user-agent é cortado em 512 caracteres.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlmodel import Session, select

from fazenda.models.juridico import LIMITE_USER_AGENT, AceiteTermos
from fazenda.rules import reguas_referencia, textos_juridicos
from fazenda.rules.agente_leitura import ip_do_cliente

TIPOS = tuple(textos_juridicos.TIPOS_ACEITE)


def texto_vigente(tipo: str, hoje: Optional[date] = None) -> dict[str, Any]:
    if tipo not in textos_juridicos.TIPOS_ACEITE:
        raise HTTPException(status_code=400, detail=f"Tipo de aceite inválido. Use um destes: {', '.join(TIPOS)}")
    if tipo == "reguas":
        return reguas_referencia.texto_modal_vigente(hoje=hoje)
    return textos_juridicos.descrever(textos_juridicos.TIPOS_ACEITE[tipo])


def origem_da_requisicao(request: Optional[Request]) -> tuple[Optional[str], Optional[str]]:
    if request is None:
        return None, None
    ip = ip_do_cliente(request.headers.get("x-forwarded-for"), request.client.host if request.client else None)
    ua = (request.headers.get("user-agent") or "")[:LIMITE_USER_AGENT] or None
    return ip, ua


def utc_iso(d: Optional[datetime]) -> Optional[str]:
    return d.replace(microsecond=0).isoformat() + "Z" if d else None


def ultimo_aceite(session: Session, usuario_id: int, fazenda_id: Optional[int], tipo: str,
                  sha256: Optional[str] = None) -> Optional[AceiteTermos]:
    if not isinstance(fazenda_id, int):
        return None
    q = select(AceiteTermos).where(
        AceiteTermos.usuario_id == usuario_id, AceiteTermos.fazenda_id == fazenda_id, AceiteTermos.tipo == tipo,
    )
    if sha256 is not None:
        q = q.where(AceiteTermos.sha256 == sha256)
    return session.exec(q.order_by(AceiteTermos.criado_em.desc(), AceiteTermos.id.desc())).first()


def aceite_pendente(session: Session, usuario_id: int, fazenda_id: Optional[int], tipo: str = "reguas",
                    hoje: Optional[date] = None) -> bool:
    vigente = texto_vigente(tipo, hoje)
    return ultimo_aceite(session, usuario_id, fazenda_id, tipo, vigente["sha256"]) is None


def registrar(session: Session, *, usuario_id: int, fazenda_id: Optional[int], tipo: str, versao: str,
              sha256: str, request: Optional[Request] = None, hoje: Optional[date] = None) -> AceiteTermos:
    if not isinstance(fazenda_id, int):
        raise HTTPException(status_code=409, detail="O aceite precisa de uma fazenda selecionada. Saia e entre novamente.")
    vigente = texto_vigente(tipo, hoje)
    if not vigente["disponivel_para_aceite"]:
        raise HTTPException(status_code=409, detail=vigente.get("pendente") or "Este texto ainda não está disponível para aceite.")
    if versao != vigente["versao"] or (sha256 or "").lower() != vigente["sha256"]:
        raise HTTPException(
            status_code=409,
            detail="O texto mudou desde que a tela foi aberta. Recarregue a página e leia a versão vigente antes de aceitar.",
        )
    ip, ua = origem_da_requisicao(request)
    aceite = AceiteTermos(
        usuario_id=usuario_id, fazenda_id=fazenda_id, tipo=tipo, texto_chave=vigente["chave"],
        versao=vigente["versao"], sha256=vigente["sha256"], ip=ip, user_agent=ua,
    )
    session.add(aceite)
    session.commit()
    session.refresh(aceite)
    return aceite


def como_dict(a: AceiteTermos) -> dict[str, Any]:
    return {
        "id": a.id, "tipo": a.tipo, "texto_chave": a.texto_chave, "versao": a.versao, "sha256": a.sha256,
        "fazenda_id": a.fazenda_id, "usuario_id": a.usuario_id, "ip": a.ip, "user_agent": a.user_agent,
        "criado_em_utc": utc_iso(a.criado_em),
    }


def comprovante(session: Session, usuario, fazenda_id: Optional[int]) -> dict[str, Any]:
    """Comprovante de aceite por usuário (parecer 6.1.6): todos os aceites dele
    NESTA fazenda, com o texto de cada versão aceita quando ainda é o vigente."""
    linhas = [] if not isinstance(fazenda_id, int) else session.exec(
        select(AceiteTermos).where(AceiteTermos.usuario_id == usuario.id, AceiteTermos.fazenda_id == fazenda_id)
        .order_by(AceiteTermos.criado_em, AceiteTermos.id)
    ).all()
    vigentes = {t: texto_vigente(t) for t in TIPOS}
    historico = textos_juridicos.dados_padrao().get("historico") or []
    registros = []
    for a in linhas:
        item = como_dict(a)
        v = vigentes.get(a.tipo) or {}
        if v.get("sha256") == a.sha256:
            item["texto_aceito"] = v.get("texto")
            item["e_a_versao_vigente"] = True
        else:
            antigo = next((h for h in historico if h.get("chave") == a.texto_chave and h.get("versao") == a.versao), None)
            item["texto_aceito"] = None
            item["modelo_da_versao"] = (antigo or {}).get("modelo")
            item["e_a_versao_vigente"] = False
        registros.append(item)
    return {
        "documento": "Comprovante de aceite — CowData",
        "gerado_em_utc": utc_iso(datetime.utcnow()),
        "usuario": {"id": usuario.id, "username": usuario.username, "nome": usuario.nome},
        "fazenda_id": fazenda_id,
        "aceites": registros,
        "observacao": "Registro append-only (parecer jurídico de 08/10/2026, item 6.1). Data e hora em UTC; "
                      "o SHA-256 identifica o texto exato exibido no momento do aceite.",
    }
