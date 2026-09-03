"""
Router do Banco de fotos do Milknews — pastas + fotos usadas para ilustrar
as matérias do blog News, geridas direto na aba de Aprovações (aprovar uma
matéria do robô /milknews deixa escolher a foto ali mesmo). Conteúdo vive no
Supabase Storage, bucket PÚBLICO settings.supabase_bucket_news_fotos (ver
fazenda/rules/supabase_storage.py) — diferente de fotos.py (fotos do campo,
bucket privado por fazenda), aqui é um banco global e público: a URL
devolvida por este router é a mesma guardada em NoticiaNews.imagem e
renderizada direto em <img src> na página pública do blog, sem login.

Toda escrita (criar pasta, enviar/excluir foto) exige a mesma permissão de
publicar matérias no blog (exigir_pode_publicar) — quem pode publicar
matéria também gerencia o banco de fotos que ilustra as matérias. Leitura
(listar pastas/fotos) também exige a permissão: a tela de gestão só existe
dentro da aba de Aprovações, que já é restrita.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.auth import exigir_pode_publicar
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import FotoNews, PastaFotoNews, Usuario
from fazenda.rules.supabase_storage import enviar_arquivo, excluir_arquivo, nome_seguro_storage, url_publica

router = APIRouter(prefix="/fotos-news", tags=["fotos-news"])

TAMANHO_MAXIMO_FOTO = 15 * 1024 * 1024  # 15 MB — igual às outras fotos do sistema


def _foto_dict(f: FotoNews) -> dict:
    return {
        "id": f.id, "pasta_id": f.pasta_id, "nome_arquivo": f.nome_arquivo,
        "mime_type": f.mime_type, "tamanho_bytes": f.tamanho_bytes, "tags": f.tags,
        "criado_em": f.criado_em.isoformat(),
        "url": url_publica(f.caminho_storage, bucket=settings.supabase_bucket_news_fotos),
    }


# ── Pastas ───────────────────────────────────────────────────────────────
@router.get("/pastas")
def listar_pastas(session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar)) -> list[dict]:
    pastas = session.exec(select(PastaFotoNews).order_by(PastaFotoNews.nome)).all()
    contagem: dict[int | None, int] = {}
    for pid in session.exec(select(FotoNews.pasta_id)).all():
        contagem[pid] = contagem.get(pid, 0) + 1
    return [{"id": p.id, "nome": p.nome, "criado_em": p.criado_em.isoformat(), "quantidade_fotos": contagem.get(p.id, 0)} for p in pastas]


@router.post("/pastas", status_code=201)
def criar_pasta(
    dados: dict, session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
) -> dict:
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome da pasta é obrigatório")
    if session.exec(select(PastaFotoNews).where(PastaFotoNews.nome == nome)).first():
        raise HTTPException(status_code=400, detail="Já existe uma pasta com este nome")
    pasta = PastaFotoNews(nome=nome, criado_por=user.id)
    session.add(pasta)
    session.commit()
    session.refresh(pasta)
    return {"id": pasta.id, "nome": pasta.nome, "criado_em": pasta.criado_em.isoformat(), "quantidade_fotos": 0}


@router.delete("/pastas/{pasta_id}")
def excluir_pasta(
    pasta_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
) -> dict:
    pasta = session.get(PastaFotoNews, pasta_id)
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    tem_fotos = session.exec(select(FotoNews).where(FotoNews.pasta_id == pasta_id)).first()
    if tem_fotos:
        raise HTTPException(status_code=400, detail="Pasta não está vazia — mova ou exclua as fotos antes")
    session.delete(pasta)
    session.commit()
    return {"excluido": True}


# ── Fotos ────────────────────────────────────────────────────────────────
@router.get("")
def listar_fotos(
    pasta_id: int | None = None, sem_pasta: bool = False,
    session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
) -> list[dict]:
    query = select(FotoNews)
    if sem_pasta:
        query = query.where(FotoNews.pasta_id.is_(None))
    elif pasta_id is not None:
        query = query.where(FotoNews.pasta_id == pasta_id)
    fotos = session.exec(query.order_by(FotoNews.criado_em.desc())).all()
    return [_foto_dict(f) for f in fotos]


@router.post("/upload", status_code=201)
async def enviar_foto(
    file: UploadFile, pasta_id: int | None = None, tags: str | None = None,
    session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
) -> dict:
    if pasta_id is not None and not session.get(PastaFotoNews, pasta_id):
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    conteudo = await file.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    if len(conteudo) > TAMANHO_MAXIMO_FOTO:
        raise HTTPException(status_code=400, detail="Foto maior que 15 MB — não é possível enviar")

    nome_original = file.filename or "foto.jpg"
    caminho = f"{uuid4().hex}_{nome_seguro_storage(nome_original)}"
    try:
        enviar_arquivo(caminho, conteudo, file.content_type or "image/jpeg", bucket=settings.supabase_bucket_news_fotos)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    foto = FotoNews(
        pasta_id=pasta_id, nome_arquivo=nome_original, caminho_storage=caminho,
        mime_type=file.content_type or "image/jpeg", tamanho_bytes=len(conteudo),
        tags=(tags or "").strip() or None, enviado_por=user.id,
    )
    session.add(foto)
    session.commit()
    session.refresh(foto)
    return _foto_dict(foto)


@router.delete("/{foto_id}")
def excluir_foto(
    foto_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
) -> dict:
    foto = session.get(FotoNews, foto_id)
    if not foto:
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    try:
        excluir_arquivo(foto.caminho_storage, bucket=settings.supabase_bucket_news_fotos)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.delete(foto)
    session.commit()
    return {"excluido": True}
