"""
Router do Assistente Claude (protótipo) — POST /assistente/perguntar + CRUD
de "ensinamentos" (base de conhecimento em texto que um admin cadastra para
o Assistente, ver fazenda.rules.assistente._system_prompt).

Piloto de multi-fazenda (ver fazenda/models/multitenant.py): por decisão do
dono, o assistente NÃO entra no pacote padrão de uma fazenda nova por
enquanto — fica restrito à fazenda já existente. `fazenda_id` só é None para
token emitido antes do piloto (comportamento idêntico ao de hoje).

Modelo de acesso (decisão do dono, 2026-07-30): a CONVERSA (/perguntar) fica
aberta a qualquer usuário logado da fazenda piloto — as ferramentas que ele
vê já são filtradas pelas permissões normais de módulo (ver
fazenda.rules.assistente._ferramentas_do_usuario). Só o TREINO (CRUD de
ensinamentos, que muda o que o Assistente responde para TODO MUNDO) fica
restrito a administradores (Usuario.papel == "admin") — nunca ficou restrito
ao dono via UsuarioFazenda.contratante porque essa tabela nunca teve uma
linha pra fazenda-piloto de instalação única, e o gate antigo (que exigia
esse vínculo) deixava o dono original sem acesso nenhum, chat incluído.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import AssistenteEnsinamento, Usuario
from fazenda.rules.assistente import responder
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/assistente", tags=["assistente"])

FAZENDA_ID_PILOTO = 1


def _fazenda_piloto(fazenda_id: int | None) -> bool:
    return fazenda_id is None or fazenda_id == FAZENDA_ID_PILOTO


def _exigir_fazenda_piloto(
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Usuario:
    """Único gate da conversa: qualquer usuário logado da fazenda piloto.
    As ferramentas oferecidas já são filtradas pelas permissões de módulo
    de cada um (ver rules/assistente.py::_ferramentas_do_usuario)."""
    if not _fazenda_piloto(fazenda_id):
        raise HTTPException(status_code=403, detail="Assistente ainda não disponível para esta fazenda")
    return usuario


def _exigir_admin(
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Usuario:
    """Gate dos endpoints de treino: só administrador — o que é cadastrado
    aqui muda o que o Assistente responde para todo mundo da fazenda."""
    if not _fazenda_piloto(fazenda_id):
        raise HTTPException(status_code=403, detail="Assistente ainda não disponível para esta fazenda")
    if usuario.papel != "admin":
        raise HTTPException(status_code=403, detail="Treinar o Assistente é restrito a administradores")
    return usuario


class PerguntaIn(BaseModel):
    mensagem: str
    historico: list[dict] = []


@router.post("/perguntar")
def perguntar(
    dados: PerguntaIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(_exigir_fazenda_piloto),
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
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Nunca dá 403 — só devolve o que o front (site/app) precisa saber pra
    decidir o que mostrar: `liberado` (pode conversar) e `pode_treinar`
    (é admin — mostra a aba/tela de Ensinamentos)."""
    liberado = _fazenda_piloto(fazenda_id)
    return {"liberado": liberado, "pode_treinar": liberado and usuario.papel == "admin"}


# ---------------------------------------------------------------------------
# Ensinamentos — base de conhecimento em texto (não é fine-tuning) que um
# admin cadastra e que entra no SYSTEM_PROMPT a cada pergunta (ver
# fazenda.rules.assistente._system_prompt). Restrito a admin — ver
# _exigir_admin acima.
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
    usuario: Usuario = Depends(_exigir_admin),
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
    usuario: Usuario = Depends(_exigir_admin),
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
    usuario: Usuario = Depends(_exigir_admin),
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
    usuario: Usuario = Depends(_exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    e = _buscar_da_fazenda(session, ensinamento_id, fazenda_id)
    session.delete(e)
    session.commit()
    return {"ok": True}
