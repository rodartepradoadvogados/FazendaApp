"""
Router do Arquivo fiscal-contábil — upload/lista/download/exclusão de notas
fiscais, CCIR, IRPF/IRPJ, inscrição estadual, matrículas, contratos de
trabalho/prestação de serviço, entre outros. O conteúdo vive no Supabase
Storage (ver fazenda/rules/supabase_storage.py); aqui só ficam os metadados
(ver fazenda/models/documentos.py::DocumentoArquivado).

Registrado em main.py SEM bloquear_escrita_contador — o contador pode
arquivar documentos livremente, sem precisar destravar o cadeado (essa
trava é só para escrita em Financeiro/Planejamento/Chamados, ver
fazenda/auth.py::bloquear_escrita_contador).
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import DocumentoArquivado, TipoDocumento, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage

router = APIRouter(prefix="/documentos", tags=["documentos"])

TAMANHO_MAXIMO_DOCUMENTO = 15 * 1024 * 1024  # 15 MB — igual ao anexo de lançamento

# BUG DE SEGURANÇA CORRIGIDO: content_type é escolhido pelo cliente e, sem
# uma allow-list, um valor como "text/html"/"image/svg+xml" servido depois
# com Content-Disposition: inline (ver baixar_documento) seria um risco de
# XSS armazenado se este endpoint for aberto na mesma origem autenticada.
_CONTENT_TYPES_PERMITIDOS = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/octet-stream",
}

_ABREV_CATEGORIA = {
    "nota fiscal": "NF", "recibo": "REC", "folha de pagamento": "FOLHA", "fatura": "FAT",
    "contrato": "CONT", "boleto": "BOL", "ordem de serviço": "OS", "ccir": "CCIR",
    "irpf": "IRPF", "irpj": "IRPJ", "inscrição estadual": "IE", "matrícula": "MAT",
    "contrato de trabalho": "CTRAB", "contrato de prestação de serviço": "CSERV", "outros": "DOC",
}


def _slug(texto: str) -> str:
    """'Inscrição estadual' -> 'inscricao_estadual' — usado no caminho de pastas."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "_".join(sem_acento.lower().split())


def _abreviar_categoria(categoria: str) -> str:
    achado = _ABREV_CATEGORIA.get(categoria.strip().lower())
    if achado:
        return achado
    letras = "".join(c for c in categoria.upper() if c.isalpha())
    return letras[:4] or "DOC"


def _proximo_caminho(session: Session, fazenda_id: int | None, categoria: str, hoje: date, extensao: str) -> str:
    prefixo_pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}/{_slug(categoria)}"
    abrev = _abreviar_categoria(categoria)
    prefixo_nome = f"{hoje.isoformat()}_{abrev}_"
    existentes = session.exec(
        select(DocumentoArquivado).where(
            DocumentoArquivado.fazenda_id == fazenda_id,
            DocumentoArquivado.categoria == categoria,
        )
    ).all()
    seq = 1 + sum(1 for d in existentes if d.caminho_storage.split("/")[-1].startswith(prefixo_nome))
    return f"{prefixo_pasta}/{prefixo_nome}{seq:04d}{extensao}"


@router.post("/upload", status_code=201)
async def enviar_documento(
    file: UploadFile,
    categoria: str = Form(...),
    inserir_no_balanco: bool = Form(False),
    numero_lancamento: str | None = Form(None),
    data_documento: date | None = Form(None),
    descricao: str | None = Form(None),
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_tipo = select(TipoDocumento).where(TipoDocumento.nome == categoria, TipoDocumento.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_tipo = query_tipo.where(TipoDocumento.fazenda_id == fazenda_id)
    if not session.exec(query_tipo).first():
        raise HTTPException(status_code=400, detail=f"Categoria de documento inválida: '{categoria}'")

    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_DOCUMENTO:
        raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB — não é possível arquivar")

    nome_original = file.filename or "arquivo"
    # BUG DE SEGURANÇA CORRIGIDO: sem nome_seguro_storage, um nome de arquivo
    # como "evil.png/../../outra-fazenda/arquivo.pdf" produzia uma extensão
    # contendo "/", que ia direto pra URL do Supabase Storage sem sanitização
    # — risco de escrever fora do prefixo fazenda-{id}/ pretendido.
    extensao = nome_seguro_storage(f".{nome_original.rsplit('.', 1)[-1].lower()}") if "." in nome_original else ""
    content_type = file.content_type if file.content_type in _CONTENT_TYPES_PERMITIDOS else "application/octet-stream"
    hoje = datetime.utcnow().date()
    caminho = _proximo_caminho(session, fazenda_id, categoria, hoje, extensao)

    try:
        enviar_arquivo(caminho, conteudo, content_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    documento = DocumentoArquivado(
        fazenda_id=fazenda_id,
        categoria=categoria,
        nome_original=nome_original,
        caminho_storage=caminho,
        mime_type=content_type,
        tamanho_bytes=len(conteudo),
        data_documento=data_documento,
        enviado_por=user.id if isinstance(user, Usuario) else None,
        inserir_no_balanco=inserir_no_balanco,
        numero_lancamento=numero_lancamento if inserir_no_balanco else None,
        descricao=descricao,
    )
    session.add(documento)
    session.commit()
    session.refresh(documento)
    return {
        "id": documento.id, "categoria": documento.categoria, "nome_original": documento.nome_original,
        "caminho_storage": documento.caminho_storage, "tamanho_bytes": documento.tamanho_bytes,
        "inserir_no_balanco": documento.inserir_no_balanco, "numero_lancamento": documento.numero_lancamento,
    }


@router.get("")
def listar_documentos(
    categoria: str | None = None,
    inserir_no_balanco: bool | None = None,
    numero_lancamento: str | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(DocumentoArquivado)
    if fazenda_id is not None:
        query = query.where(DocumentoArquivado.fazenda_id == fazenda_id)
    if categoria:
        query = query.where(DocumentoArquivado.categoria == categoria)
    if inserir_no_balanco is not None:
        query = query.where(DocumentoArquivado.inserir_no_balanco == inserir_no_balanco)
    if numero_lancamento:
        query = query.where(DocumentoArquivado.numero_lancamento == numero_lancamento)
    if data_de:
        query = query.where(DocumentoArquivado.data_upload >= datetime.combine(data_de, datetime.min.time()))
    if data_ate:
        query = query.where(DocumentoArquivado.data_upload <= datetime.combine(data_ate, datetime.max.time()))
    documentos = session.exec(query.order_by(DocumentoArquivado.data_upload.desc())).all()
    return [
        {
            "id": d.id, "categoria": d.categoria, "nome_original": d.nome_original,
            "mime_type": d.mime_type, "tamanho_bytes": d.tamanho_bytes,
            "data_documento": d.data_documento.isoformat() if d.data_documento else None,
            "data_upload": d.data_upload.isoformat(), "inserir_no_balanco": d.inserir_no_balanco,
            "numero_lancamento": d.numero_lancamento, "descricao": d.descricao,
        }
        for d in documentos
    ]


@router.get("/categorias")
def listar_categorias_documento(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[str]:
    """Categorias cadastradas (TipoDocumento ativo) — alimenta o seletor do upload."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(TipoDocumento).where(TipoDocumento.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(TipoDocumento.fazenda_id == fazenda_id)
    return sorted({t.nome for t in session.exec(query).all()})


@router.get("/{documento_id}/download")
def baixar_documento(
    documento_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    """Proxy: busca no Supabase Storage e transmite os bytes de volta — o
    navegador nunca vê a URL do Supabase, só este endpoint (sensação de que
    o arquivo está dentro do próprio site)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    documento = session.get(DocumentoArquivado, documento_id)
    if not documento or (fazenda_id is not None and documento.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    try:
        conteudo = baixar_arquivo(documento.caminho_storage)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=conteudo, media_type=documento.mime_type,
        headers={"Content-Disposition": f'inline; filename="{documento.nome_original}"'},
    )


@router.delete("/{documento_id}")
def excluir_documento(
    documento_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _admin: Usuario = Depends(exigir_admin),
) -> dict:
    # Exclusão é irreversível e o arquivo aqui é fiscal/pessoal do dono (IRPF,
    # matrícula, contrato...) — mais sensível que o upload/consulta (que o
    # contador precisa fazer livremente, ver comentário em main.py). Por isso
    # só a exclusão fica restrita a admin, sem travar o resto do router.
    fazenda_id = fazenda_id_seguro(fazenda_id)
    documento = session.get(DocumentoArquivado, documento_id)
    if not documento or (fazenda_id is not None and documento.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    try:
        excluir_arquivo(documento.caminho_storage)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.delete(documento)
    session.commit()
    return {"excluido": True}
