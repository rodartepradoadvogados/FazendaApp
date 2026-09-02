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

from fazenda.api.routers.portal import usuarios_da_fazenda
from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import Animal, FotoCampo, PortalMensagem, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage

# BUG DE SEGURANÇA CORRIGIDO: content_type escolhido pelo cliente sem
# allow-list — mesma correção de documentos.py.
_CONTENT_TYPES_PERMITIDOS_FOTO = {"image/png", "image/jpeg", "image/webp", "image/gif"}

router = APIRouter(prefix="/fotos", tags=["fotos"])

TAMANHO_MAXIMO_FOTO = 15 * 1024 * 1024  # 15 MB — igual ao arquivo fiscal-contábil

TIPOS_ASSUNTO = {"animal", "lote", "outro"}
ASSUNTOS_FIXOS = {
    "reproducao": "Reprodução", "producao": "Produção", "sanidade": "Sanidade",
    "alimentacao": "Alimentação", "estoque": "Estoque", "outro": "Outro assunto",
}


def _ids_csv(valor: str | None) -> list[int]:
    """"3, 7" -> [3, 7]; ignora tokens que não são inteiros (cliente adulterado
    ou lixo de digitação — nunca vale a pena derrubar o upload da foto por isso)."""
    if not valor:
        return []
    resultado = []
    for token in valor.split(","):
        token = token.strip()
        if token.isdigit():
            resultado.append(int(token))
    return resultado


def _resumo_assunto(foto: FotoCampo) -> str:
    if foto.tipo_assunto == "animal" and foto.identificacao_animal:
        return f"Animal {foto.identificacao_animal}"
    if foto.tipo_assunto == "lote" and foto.lotes:
        return f"Lotes {foto.lotes.replace(',', ', ')}"
    if foto.tipo_assunto == "outro" and foto.assunto_fixo:
        return ASSUNTOS_FIXOS.get(foto.assunto_fixo, foto.assunto_fixo)
    return ""


def _corpo_aviso(foto: FotoCampo, descricao: str | None) -> str:
    # Hora obrigatória no corpo: push.py::_chave_item deduplica por
    # sha256(tipo|categoria|descricao) no dia — sem ela, duas fotos sem
    # descrição no mesmo dia colidiriam na mesma chave e a 2ª não notificaria.
    hora = foto.data_captura.strftime("%H:%M")
    resumo = _resumo_assunto(foto)
    base = f"{hora} — {resumo}" if resumo else f"{hora} — Foto do campo"
    return f"{base}: {descricao.strip()}" if descricao and descricao.strip() else base


def _criar_avisos_portal(
    session: Session, foto: FotoCampo, remetente_id: int,
    destinatarios_ids: list[int], descricao: str | None, fazenda_id: int | None,
) -> int:
    corpo = _corpo_aviso(foto, descricao)
    ids_validos = {u.id for u in usuarios_da_fazenda(session, fazenda_id)}
    alvo = [i for i in destinatarios_ids if i in ids_validos] if destinatarios_ids else list(ids_validos)
    alvo = [i for i in alvo if i != remetente_id]
    for dest_id in alvo:
        session.add(PortalMensagem(
            tipo="foto",
            remetente_usuario_id=remetente_id,
            destinatario_usuario_id=dest_id,
            corpo=corpo,
            foto_campo_id=foto.id,
            pede_retorno=False,
            fazenda_id=fazenda_id,
        ))
    return len(alvo)


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
    tipo_assunto: str | None = Form(None),
    lotes: str | None = Form(None),
    assunto_fixo: str | None = Form(None),
    destinatarios_usuario_id: str | None = Form(None),
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
    if tipo_assunto and tipo_assunto not in TIPOS_ASSUNTO:
        raise HTTPException(status_code=400, detail=f"Assunto inválido: {tipo_assunto}")
    if assunto_fixo and assunto_fixo not in ASSUNTOS_FIXOS:
        raise HTTPException(status_code=400, detail=f"Assunto inválido: {assunto_fixo}")

    nome_original = file.filename or "foto.jpg"
    # BUG DE SEGURANÇA CORRIGIDO: mesma correção de documentos.py — sanitiza
    # a extensão (remove "/" e afins) antes de montar a key do Storage.
    extensao = nome_seguro_storage(f".{nome_original.rsplit('.', 1)[-1].lower()}") if "." in nome_original else ".jpg"
    content_type = file.content_type if file.content_type in _CONTENT_TYPES_PERMITIDOS_FOTO else "image/jpeg"
    hoje = datetime.utcnow().date()
    caminho = _proximo_caminho(session, fazenda_id, hoje, extensao)

    try:
        enviar_arquivo(
            caminho, conteudo, content_type,
            bucket=settings.supabase_bucket_fotos,
        )
    except RuntimeError as exc:
        # 502 (não 400): isto é falha do Supabase Storage (fora do ar,
        # credencial ruim), não erro do cliente — a fila offline do app
        # (lib/offline.ts) trata >=500 como "tenta depois" e só marca erro
        # definitivo (exige "Descartar") em 4xx. Uma foto de verdade não
        # pode virar erro permanente por uma instabilidade de infra.
        raise HTTPException(status_code=502, detail=str(exc))

    animal_id = None
    if tipo_assunto == "animal" and identificacao_animal:
        query = select(Animal).where(Animal.numero == identificacao_animal)
        if fazenda_id is not None:
            query = query.where(Animal.fazenda_id == fazenda_id)
        animal = session.exec(query).first()
        animal_id = animal.id if animal else None

    foto = FotoCampo(
        fazenda_id=fazenda_id,
        caminho_storage=caminho,
        mime_type=content_type,
        tamanho_bytes=len(conteudo),
        descricao=descricao,
        identificacao_animal=identificacao_animal,
        enviado_por=user.id if isinstance(user, Usuario) else None,
        tipo_assunto=tipo_assunto if tipo_assunto in TIPOS_ASSUNTO else None,
        animal_id=animal_id,
        lotes=lotes if tipo_assunto == "lote" else None,
        assunto_fixo=assunto_fixo if tipo_assunto == "outro" else None,
    )
    session.add(foto)
    session.flush()  # garante foto.id antes de vincular os avisos do Portal

    notificados = _criar_avisos_portal(
        session, foto, user.id,
        _ids_csv(destinatarios_usuario_id), descricao, fazenda_id,
    )

    session.commit()
    session.refresh(foto)
    return {
        "id": foto.id, "tamanho_bytes": foto.tamanho_bytes,
        "descricao": foto.descricao, "identificacao_animal": foto.identificacao_animal,
        "tipo_assunto": foto.tipo_assunto, "animal_id": foto.animal_id,
        "lotes": foto.lotes, "assunto_fixo": foto.assunto_fixo,
        "data_captura": foto.data_captura.isoformat(),
        "notificados": notificados,
    }


@router.get("")
def listar_fotos(
    identificacao_animal: str | None = None,
    lote: str | None = None,
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
    if lote:
        query = query.where(FotoCampo.lotes.contains(lote))
    if data_de:
        query = query.where(FotoCampo.data_captura >= datetime.combine(data_de, datetime.min.time()))
    if data_ate:
        query = query.where(FotoCampo.data_captura <= datetime.combine(data_ate, datetime.max.time()))
    fotos = session.exec(query.order_by(FotoCampo.data_captura.desc())).all()
    return [
        {
            "id": f.id, "mime_type": f.mime_type, "tamanho_bytes": f.tamanho_bytes,
            "descricao": f.descricao, "identificacao_animal": f.identificacao_animal,
            "tipo_assunto": f.tipo_assunto, "animal_id": f.animal_id,
            "lotes": f.lotes, "assunto_fixo": f.assunto_fixo,
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
