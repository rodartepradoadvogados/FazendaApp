"""
Router de Onboarding — checklist guiado de primeiro acesso, mostrado na Capa
até o usuário concluir ou dispensar. Ver fazenda/models/onboarding.py.

Passos fixos no código (mudam raramente, não fazem sentido editáveis pelo
usuário) — mesmo padrão de ABAS_PORTAL/TIPOS_ASSUNTO em outros routers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from fazenda.auth import fazenda_tem_modulo_contratado, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import OnboardingUsuario, Usuario

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Checklist de uma fazenda COM rebanho — o de sempre (inalterado).
PASSOS_ONBOARDING = [
    {"chave": "primeiro_lote", "label": "Cadastre seu primeiro lote", "rota": "/rebanho"},
    {"chave": "primeiro_lancamento", "label": "Lance seu primeiro evento", "rota": "/lancamentos"},
    {"chave": "conferir_agenda", "label": "Confira a Agenda", "rota": "/agenda"},
    {"chave": "instalar_app", "label": "Instale o app no celular", "rota": "/app"},
]

# Checklist de uma fazenda SÓ-Financeiro (plano Financeiro, sem rebanho): nada
# de lote/rebanho/app de campo. Plano Financeiro §1.9.
PASSOS_ONBOARDING_FINANCEIRO = [
    {"chave": "contas_bancarias", "label": "Cadastre suas contas bancárias", "rota": "/financeiro"},
    {"chave": "plano_de_contas", "label": "Carregue o plano de contas", "rota": "/financeiro"},
    {"chave": "primeira_conta_a_pagar", "label": "Lance a primeira conta a pagar", "rota": "/financeiro"},
    {"chave": "convidar_contador", "label": "Convide seu contador", "rota": "/usuarios"},
    {"chave": "conferir_agenda", "label": "Confira a Agenda", "rota": "/agenda"},
]

# Fazenda sem rebanho e sem financeiro (não deve existir: o contrato exige um
# módulo base): só o que sobra de universal.
PASSOS_ONBOARDING_MINIMO = [
    {"chave": "conferir_agenda", "label": "Confira a Agenda", "rota": "/agenda"},
]

# Toda chave que algum checklist pode ter — validar a conclusão de um passo
# contra isto (e não contra o checklist da fazenda atual) deixa a marcação
# funcionar mesmo se o contrato mudar entre o GET e o POST.
CHAVES_VALIDAS = {p["chave"] for lista in (PASSOS_ONBOARDING, PASSOS_ONBOARDING_FINANCEIRO, PASSOS_ONBOARDING_MINIMO) for p in lista}


def passos_da_fazenda(session: Session, fazenda_id: int | None) -> list[dict]:
    """Checklist em função dos módulos CONTRATADOS (Plano Financeiro §1.9).
    Com rebanho (ou sem fazenda selecionada, legado) = o de hoje; só-Financeiro
    = os 5 passos do financeiro."""
    if fazenda_id is None or fazenda_tem_modulo_contratado(session, fazenda_id, "rebanho"):
        return PASSOS_ONBOARDING
    if fazenda_tem_modulo_contratado(session, fazenda_id, "financeiro"):
        return PASSOS_ONBOARDING_FINANCEIRO
    return PASSOS_ONBOARDING_MINIMO


def _linha(session: Session, usuario_id: int) -> OnboardingUsuario:
    linha = session.get(OnboardingUsuario, usuario_id)
    if not linha:
        linha = OnboardingUsuario(usuario_id=usuario_id)
        session.add(linha)
        session.commit()
        session.refresh(linha)
    return linha


def _serializar(linha: OnboardingUsuario, passos: list[dict]) -> dict:
    concluidos = {c for c in linha.passos_concluidos.split(",") if c}
    return {
        "passos": [{**p, "concluido": p["chave"] in concluidos} for p in passos],
        "dispensado": linha.dispensado,
        "tudo_concluido": concluidos.issuperset({p["chave"] for p in passos}),
    }


@router.get("")
def obter_onboarding(
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return _serializar(_linha(session, user.id), passos_da_fazenda(session, fazenda_id))


@router.post("/passos/{chave}/concluir")
def concluir_passo(
    chave: str, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if chave not in CHAVES_VALIDAS:
        raise HTTPException(400, f"Passo inválido: {chave}")
    linha = _linha(session, user.id)
    concluidos = {c for c in linha.passos_concluidos.split(",") if c}
    concluidos.add(chave)
    linha.passos_concluidos = ",".join(sorted(concluidos))
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return _serializar(linha, passos_da_fazenda(session, fazenda_id))


@router.post("/dispensar")
def dispensar_onboarding(
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    linha = _linha(session, user.id)
    linha.dispensado = True
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return _serializar(linha, passos_da_fazenda(session, fazenda_id))
