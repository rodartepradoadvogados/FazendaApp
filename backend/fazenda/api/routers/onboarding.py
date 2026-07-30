"""
Router de Onboarding — checklist guiado de primeiro acesso, mostrado na Capa
até o usuário concluir ou dispensar. Ver fazenda/models/onboarding.py.

Passos fixos no código (mudam raramente, não fazem sentido editáveis pelo
usuário) — mesmo padrão de ABAS_PORTAL/TIPOS_ASSUNTO em outros routers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import OnboardingUsuario, Usuario

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

PASSOS_ONBOARDING = [
    {"chave": "primeiro_lote", "label": "Cadastre seu primeiro lote", "rota": "/rebanho"},
    {"chave": "primeiro_lancamento", "label": "Lance seu primeiro evento", "rota": "/lancamentos"},
    {"chave": "conferir_agenda", "label": "Confira a Agenda", "rota": "/agenda"},
    {"chave": "instalar_app", "label": "Instale o app no celular", "rota": "/app"},
]
CHAVES_VALIDAS = {p["chave"] for p in PASSOS_ONBOARDING}


def _linha(session: Session, usuario_id: int) -> OnboardingUsuario:
    linha = session.get(OnboardingUsuario, usuario_id)
    if not linha:
        linha = OnboardingUsuario(usuario_id=usuario_id)
        session.add(linha)
        session.commit()
        session.refresh(linha)
    return linha


def _serializar(linha: OnboardingUsuario) -> dict:
    concluidos = {c for c in linha.passos_concluidos.split(",") if c}
    return {
        "passos": [{**p, "concluido": p["chave"] in concluidos} for p in PASSOS_ONBOARDING],
        "dispensado": linha.dispensado,
        "tudo_concluido": concluidos.issuperset(CHAVES_VALIDAS),
    }


@router.get("")
def obter_onboarding(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return _serializar(_linha(session, user.id))


@router.post("/passos/{chave}/concluir")
def concluir_passo(chave: str, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    if chave not in CHAVES_VALIDAS:
        raise HTTPException(400, f"Passo inválido: {chave}")
    linha = _linha(session, user.id)
    concluidos = {c for c in linha.passos_concluidos.split(",") if c}
    concluidos.add(chave)
    linha.passos_concluidos = ",".join(sorted(concluidos))
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return _serializar(linha)


@router.post("/dispensar")
def dispensar_onboarding(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    linha = _linha(session, user.id)
    linha.dispensado = True
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return _serializar(linha)
