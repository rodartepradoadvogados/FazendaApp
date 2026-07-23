"""
Piloto conservador de multi-fazenda — cadastro de Fazenda e vínculo com
Usuario. Restrito ao proprietário (mesma trava de /auth/usuarios) enquanto
isto for só um piloto interno: criar uma fazenda ou vincular alguém a ela é
uma operação sensível (decide quem vê o quê), não um cadastro comum.

Ver fazenda/models/multitenant.py (Fazenda/UsuarioFazenda) e
fazenda/api/routers/auth.py (POST /auth/login, POST /auth/selecionar-fazenda).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import EMAIL_DONO, exigir_contratante_ou_dono, exigir_dono, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import CentroCusto, ContaCorrente, Fazenda, Usuario, UsuarioFazenda

router = APIRouter(prefix="/fazendas", tags=["fazendas"])


def _publico(f: Fazenda) -> dict:
    return {"id": f.id, "nome": f.nome, "cidade": f.cidade, "uf": f.uf, "ativa": f.ativa}


def provisionar_fazenda_nova(session: Session, fazenda_id: int) -> None:
    """Provisionamento padrão de uma fazenda recém-criada — só o que é
    seguro nascer em branco/genérico (não copia nada real da fazenda #1):
    - Contas correntes "Banco" e "Carteira", em branco, editáveis.
    - Centros de custo "Pecuária Leiteira" e "Agricultura".
    Pessoas e calendário sanitário nascem vazios de propósito (cada fazenda
    cadastra os seus funcionários e sua própria agenda sanitária) — ver
    fazenda/models/pessoal.py::Pessoa e fazenda/models/sanidade.py::CalendarioSanitario."""
    session.add_all([
        ContaCorrente(banco="Banco", agencia="", numero_conta="", fazenda_id=fazenda_id),
        ContaCorrente(banco="Carteira", agencia="", numero_conta="", fazenda_id=fazenda_id),
        CentroCusto(nome="Pecuária Leiteira", fazenda_id=fazenda_id),
        CentroCusto(nome="Agricultura", fazenda_id=fazenda_id),
    ])
    session.commit()


def _validar_escopo_contratante(user: Usuario, fazenda_id: int, fazenda_id_token: int | None) -> None:
    """Contratante só gerencia vínculos da PRÓPRIA fazenda selecionada (o
    dono passa sempre) — evita que um contratante da fazenda A manipule
    vínculos da fazenda B só porque exigir_contratante_ou_dono validou seu
    vínculo de contratante contra o token, sem saber qual fazenda a URL pede."""
    if (user.email or "").strip().lower() == EMAIL_DONO:
        return
    if fazenda_id_token != fazenda_id:
        raise HTTPException(status_code=403, detail="Requer ser contratante desta fazenda")


class FazendaIn(BaseModel):
    nome: str
    cidade: str | None = None
    uf: str | None = None


class VincularUsuarioIn(BaseModel):
    usuario_id: int
    contratante: bool = False


@router.get("/")
def listar_fazendas(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    return [_publico(f) for f in session.exec(select(Fazenda)).all()]


@router.get("/minhas")
def minhas_fazendas(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    """Fazendas vinculadas ao usuário logado — usado pela tela de "trocar de
    fazenda" (o login já devolve a mesma lista quando há mais de uma)."""
    vinculos = session.exec(select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id)).all()
    fazendas = [session.get(Fazenda, v.fazenda_id) for v in vinculos]
    return [_publico(f) for f in fazendas if f and f.ativa]


@router.post("/")
def criar_fazenda(dados: FazendaIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome da fazenda é obrigatório")
    fazenda = Fazenda(nome=nome, cidade=(dados.cidade or "").strip() or None, uf=(dados.uf or "").strip() or None)
    session.add(fazenda)
    session.commit()
    session.refresh(fazenda)
    provisionar_fazenda_nova(session, fazenda.id)
    return _publico(fazenda)


@router.post("/{fazenda_id}/vincular-usuario")
def vincular_usuario(
    fazenda_id: int, dados: VincularUsuarioIn,
    user: Usuario = Depends(exigir_contratante_ou_dono), fazenda_id_token: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    _validar_escopo_contratante(user, fazenda_id, fazenda_id_token)
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    usuario = session.get(Usuario, dados.usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    ja_vinculado = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario.id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if ja_vinculado:
        raise HTTPException(status_code=400, detail=f"{usuario.username} já está vinculado a esta fazenda")
    session.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=fazenda_id, contratante=dados.contratante))
    session.commit()
    return {"vinculado": True}


@router.delete("/{fazenda_id}/vincular-usuario/{usuario_id}")
def desvincular_usuario(
    fazenda_id: int, usuario_id: int,
    user: Usuario = Depends(exigir_contratante_ou_dono), fazenda_id_token: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    _validar_escopo_contratante(user, fazenda_id, fazenda_id_token)
    vinculo = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario_id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if not vinculo:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    session.delete(vinculo)
    session.commit()
    return {"desvinculado": True}
