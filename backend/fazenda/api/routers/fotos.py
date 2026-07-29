"""
Router de Fotos do campo — upload/lista/download/exclusão de fotos tiradas
pela câmera no app móvel. O conteúdo vive no Supabase Storage, bucket
`settings.supabase_bucket_fotos` (separado do arquivo fiscal-contábil — ver
fazenda/rules/supabase_storage.py); aqui só ficam os metadados (ver
fazenda/models/fotos.py::FotoCampo).

Registrado em main.py com _protegido + _contrato_ativo, sem exigir módulo
contratado específico — qualquer fazenda com contrato ativo pode usar.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import FotoCampo, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo

router = APIRouter(prefix="/fotos", tags=["fotos"])

TAMANHO_MAXIMO_FOTO = 15 * 1024 * 1024  # 15 MB — igual ao arquivo fiscal-contábil


def _proximo_caminho(session: Session, fazenda_id: int | None, hoje: date, extensao: str) -> str:
    prefixo_pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}"
    prefixo_nome = f"{hoje.isoformat()}_"
    existentes = session.exec(
        select(FotoCampo).where(FotoCampo.fazenda_id == fazenda_id)
    ).all()
    seq = 1 + sum(1 for f in existentes if f.caminho_storage.split("/")[-1].startswith(prefixo_nome))
    return f"{prefixo_pasta}/{prefixo_nome}{seq:04d}{extensao}"


@router.post("/upload", status_code=201)
async def enviar_foto(
    file: UploadFile,
    descricao: str | None = Form(None),
    identificacao_animal: str | None = Form(None),
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_FOTO:
        raise HTTPException(status_code=400, detail="Foto maior que 15 MB — não é possível enviar")
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    nome_original = file.filename or "foto.jpg"
    extensao = f".{nome_original.rsplit('.', 1)[-1].lower()}" if "." in nome_original else ".jpg"
    hoje = datetime.utcnow().date()
    caminho = _proximo_caminho(session, fazenda_id, hoje, extensao)

    try:
        enviar_arquivo(
            caminho, conteudo, file.content_type or "image/jpeg",
            bucket=settings.supabase_bucket_fotos,
        )
    except RuntimeError as exc:
        # 502 (não 400): isto é falha do Supabase Storage (fora do ar,
        # credencial ruim), não erro do cliente — a fila offline do app
        # (lib/offline.ts) trata >=500 como "tenta depois" e só marca erro
        # definitivo (exige "Descartar") em 4xx. Uma foto de verdade não
        # pode virar erro permanente por uma instabilidade de infra.
        raise HTTPException(status_code=502, detail=str(exc))

    foto = FotoCampo(
        fazenda_id=fazenda_id,
        caminho_storage=caminho,
        mime_type=file.content_type or "image/jpeg",
        tamanho_bytes=len(conteudo),
        descricao=descricao,
        identificacao_animal=identificacao_animal,
        enviado_por=user.id if isinstance(user, Usuario) else None,
    )
    session.add(foto)
    session.commit()
    session.refresh(foto)
    return {
        "id": foto.id, "tamanho_bytes": foto.tamanho_bytes,
        "descricao": foto.descricao, "identificacao_animal": foto.identificacao_animal,
        "data_captura": foto.data_captura.isoformat(),
    }


@router.get("")
def listar_fotos(
    identificacao_animal: str | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(FotoCampo)
    if fazenda_id is not None:
        query = query.where(FotoCampo.fazenda_id == fazenda_id)
    if identificacao_animal:
        query = query.where(FotoCampo.identificacao_animal == identificacao_animal)
    if data_de:
        query = query.where(FotoCampo.data_captura >= datetime.combine(data_de, datetime.min.time()))
    if data_ate:
        query = query.where(FotoCampo.data_captura <= datetime.combine(data_ate, datetime.max.time()))
    fotos = session.exec(query.order_by(FotoCampo.data_captura.desc())).all()
    return [
        {
            "id": f.id, "mime_type": f.mime_type, "tamanho_bytes": f.tamanho_bytes,
            "descricao": f.descricao, "identificacao_animal": f.identificacao_animal,
            "data_captura": f.data_captura.isoformat(),
        }
        for f in fotos
    ]


@router.get("/{foto_id}/arquivo")
def baixar_foto(
    foto_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    """Proxy: busca no Supabase Storage e transmite os bytes de volta — o
    navegador nunca vê a URL do Supabase, só este endpoint (mesmo padrão de
    fazenda/api/routers/documentos.py::baixar_documento)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    foto = session.get(FotoCampo, foto_id)
    if not foto or (fazenda_id is not None and foto.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    try:
        conteudo = baixar_arquivo(foto.caminho_storage, bucket=settings.supabase_bucket_fotos)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=conteudo, media_type=foto.mime_type)


@router.delete("/{foto_id}")
def excluir_foto(
    foto_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    foto = session.get(FotoCampo, foto_id)
    if not foto or (fazenda_id is not None and foto.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    try:
        excluir_arquivo(foto.caminho_storage, bucket=settings.supabase_bucket_fotos)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.delete(foto)
    session.commit()
    return {"excluido": True}
