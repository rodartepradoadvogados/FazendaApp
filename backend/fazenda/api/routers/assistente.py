"""
Router do Assistente Claude (protótipo) — POST /assistente/perguntar + CRUD
de "ensinamentos" (base de conhecimento em texto que o dono cadastra para o
Assistente, ver fazenda.rules.assistente._system_prompt).

Piloto de multi-fazenda (ver fazenda/models/multitenant.py): por decisão do
dono, o assistente NÃO entra no pacote padrão de uma fazenda nova por
enquanto — fica restrito à fazenda já existente. `fazenda_id` só é None para
token emitido antes do piloto (comportamento idêntico ao de hoje).

Restrito a UM usuário por fazenda (ver `_exigir_acesso` abaixo): o dono da
fazenda (UsuarioFazenda.contratante) mais quem ele liberar explicitamente via
parâmetro `assistente_usuarios_liberados` (Configurações > Parâmetros — ver
fazenda.rules.parametros). Antes disso, o gate era só por fazenda; agora as
duas camadas se somam.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import AssistenteEnsinamento, Usuario, UsuarioFazenda
from fazenda.rules.assistente import responder
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.parametros import get_param_texto

router = APIRouter(prefix="/assistente", tags=["assistente"])

FAZENDA_ID_PILOTO = 1


def _fazenda_do_gate(fazenda_id: int | None) -> int:
    """fazenda_id None = token legado (piloto conservador, ver módulo) — usa
    a mesma fazenda-âncora do resto deste router (FAZENDA_ID_PILOTO) para
    resolver quem é "o dono" nesse caso."""
    return fazenda_id if fazenda_id is not None else FAZENDA_ID_PILOTO


def _usuario_liberado(session: Session, usuario: Usuario, fazenda_id: int | None) -> bool:
    """O assistente é restrito ao dono da fazenda (UsuarioFazenda.contratante)
    mais quem ele liberar explicitamente via parâmetro
    'assistente_usuarios_liberados' (ids separados por vírgula) — vazio = só
    o dono mesmo, que é o comportamento de hoje."""
    fid = _fazenda_do_gate(fazenda_id)
    vinculo = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario.id, UsuarioFazenda.fazenda_id == fid)
    ).first()
    if vinculo is not None and vinculo.contratante:
        return True
    liberados = {s.strip() for s in get_param_texto("assistente_usuarios_liberados", "").split(",") if s.strip()}
    return str(usuario.id) in liberados


def _exigir_acesso(
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Usuario:
    """Dependência única para TODOS os endpoints deste router: mantém o gate
    de fazenda já existente e soma o gate por usuário (ver `_usuario_liberado`)."""
    if fazenda_id is not None and fazenda_id != FAZENDA_ID_PILOTO:
        raise HTTPException(status_code=403, detail="Assistente ainda não disponível para esta fazenda")
    if not _usuario_liberado(session, usuario, fazenda_id):
        raise HTTPException(
            status_code=403,
            detail="Assistente restrito ao proprietário da fazenda (ou usuário liberado por ele)",
        )
    return usuario


class PerguntaIn(BaseModel):
    mensagem: str
    historico: list[dict] = []


@router.post("/perguntar")
def perguntar(
    dados: PerguntaIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(_exigir_acesso),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if not dados.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    try:
        return responder(dados.mensagem.strip(), dados.historico, session, usuario, fazenda_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/acesso")
def acesso(
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Nunca dá 403 — só devolve se o usuário logado tem acesso ao Assistente,
    para o front (app/site) decidir se mostra o item de menu sem precisar
    tentar e tomar erro."""
    liberado = (fazenda_id is None or fazenda_id == FAZENDA_ID_PILOTO) and _usuario_liberado(session, usuario, fazenda_id)
    return {"liberado": liberado}


# ---------------------------------------------------------------------------
# Ensinamentos — base de conhecimento em texto (não é fine-tuning) que o dono
# cadastra e que entra no SYSTEM_PROMPT a cada pergunta (ver
# fazenda.rules.assistente._system_prompt).
# ---------------------------------------------------------------------------
class EnsinamentoIn(BaseModel):
    titulo: str
    texto: str


class EnsinamentoEditIn(BaseModel):
    titulo: str
    texto: str
    ativo: bool = True


def _serializar_ensinamento(e: AssistenteEnsinamento) -> dict:
    return {
        "id": e.id, "titulo": e.titulo, "texto": e.texto, "ativo": e.ativo,
        "criado_em": e.criado_em.isoformat(), "atualizado_em": e.atualizado_em.isoformat(),
    }


@router.get("/ensinamentos")
def listar_ensinamentos(
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(_exigir_acesso),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fid = fazenda_id_seguro(fazenda_id)
    query = select(AssistenteEnsinamento)
    if fid is not None:
        query = query.where(AssistenteEnsinamento.fazenda_id == fid)
    linhas = session.exec(query.order_by(AssistenteEnsinamento.criado_em.desc())).all()
    return [_serializar_ensinamento(e) for e in linhas]


@router.post("/ensinamentos")
def criar_ensinamento(
    dados: EnsinamentoIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(_exigir_acesso),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if not dados.titulo.strip() or not dados.texto.strip():
        raise HTTPException(status_code=400, detail="Título e texto são obrigatórios")
    e = AssistenteEnsinamento(
        fazenda_id=fazenda_id_seguro(fazenda_id),
        usuario_id=usuario.id,
        titulo=dados.titulo.strip(),
        texto=dados.texto.strip(),
    )
    session.add(e)
    session.commit()
    session.refresh(e)
    return _serializar_ensinamento(e)


def _buscar_da_fazenda(session: Session, ensinamento_id: int, fazenda_id: int | None) -> AssistenteEnsinamento:
    """Isolamento: um ensinamento de outra fazenda nunca é encontrado (404,
    igual ao padrão do resto do sistema — ver test_isolamento_sanidade.py)."""
    fid = fazenda_id_seguro(fazenda_id)
    e = session.get(AssistenteEnsinamento, ensinamento_id)
    if not e or e.fazenda_id != fid:
        raise HTTPException(status_code=404, detail="Ensinamento não encontrado")
    return e


@router.put("/ensinamentos/{ensinamento_id}")
def atualizar_ensinamento(
    ensinamento_id: int,
    dados: EnsinamentoEditIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(_exigir_acesso),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    e = _buscar_da_fazenda(session, ensinamento_id, fazenda_id)
    if not dados.titulo.strip() or not dados.texto.strip():
        raise HTTPException(status_code=400, detail="Título e texto são obrigatórios")
    e.titulo = dados.titulo.strip()
    e.texto = dados.texto.strip()
    e.ativo = dados.ativo
    e.atualizado_em = datetime.utcnow()
    session.add(e)
    session.commit()
    session.refresh(e)
    return _serializar_ensinamento(e)


@router.delete("/ensinamentos/{ensinamento_id}")
def excluir_ensinamento(
    ensinamento_id: int,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(_exigir_acesso),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    e = _buscar_da_fazenda(session, ensinamento_id, fazenda_id)
    session.delete(e)
    session.commit()
    return {"ok": True}
