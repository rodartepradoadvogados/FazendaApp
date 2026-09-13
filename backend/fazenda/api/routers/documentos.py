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

import logging
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

logger = logging.getLogger(__name__)

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


def _buscar_documento_da_fazenda(session: Session, documento_id: int, fazenda_id: int | None) -> DocumentoArquivado | None:
    """Carrega UM documento por id JÁ FILTRANDO por fazenda na consulta, em
    vez de `session.get()` + `if` sobre o objeto carregado (mesmo helper e
    mesmo motivo de agenda.py::_buscar_da_fazenda).

    O `if` de antes era `fazenda_id is not None and documento.fazenda_id !=
    fazenda_id` — o padrão tolerante da auditoria: um token sem "fid"
    desligava o recorte e devolvia/apagava documento fiscal (IRPF, matrícula,
    contrato) de QUALQUER fazenda só chutando um id sequencial. Hoje a trava
    de porta (exigir_fazenda_selecionada, montada neste router em main.py)
    recusa esse token antes, mas o `if` continuava sendo a segunda linha de
    defesa apontando para o lado errado. Filtrando na consulta, "de outra
    fazenda" e "sem fazenda" (órfão do backfill 029227481e9e) caem os dois
    no mesmo lugar: não encontrado — 404, nunca 403, porque um 403 já
    confirmaria ao atacante que aquele id existe.

    `fazenda_id is None` só acontece onde o multi-fazenda não está
    provisionado (tabela `fazenda` vazia — suíte de testes e instalação
    anterior à f1a2b3c4d5e6): sem tenant cadastrado não há tenant a isolar,
    e o comportamento é o de sempre. Tratado explicitamente, não por
    omissão."""
    query = select(DocumentoArquivado).where(DocumentoArquivado.id == documento_id)
    if fazenda_id is not None:
        query = query.where(DocumentoArquivado.fazenda_id == fazenda_id)
    return session.exec(query).first()


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
    """fazenda-X/nota_fiscal/2026-09-06_NF_0001.pdf — sequencial por dia e
    categoria.

    BUG CORRIGIDO (mesmo defeito do anexo de Pessoa, relatado pelo dono em
    06/09/2026 e corrigido em `cadastro/pessoas.py::_caminho_anexo_pessoa`,
    depois em pedidos.py e financeiro.py) — só que AQUI ele é GARANTIDO, não
    eventual: a sequência vinha da CONTAGEM de documentos vivos do dia, e o
    nome no Storage é DETERMINÍSTICO (data + abreviação da categoria +
    sequência, sem o nome do arquivo enviado). Nos outros módulos a colisão
    dependia de o usuário repetir o nome do arquivo; nesta tela basta ter
    0001 e 0002 arquivados no mesmo dia e categoria: excluir o 0001 derruba a
    contagem para 1 e o upload seguinte nasce 0002 — exatamente o caminho do
    documento que continua na tela. O envio usa `x-upsert`, então o arquivo
    do 0002 é sobrescrito em silêncio e as DUAS linhas do banco passam a
    apontar para o mesmo objeto: o download do documento antigo devolve o
    arquivo novo, excluir um apaga o arquivo dos dois, e o outro fica travado
    para sempre (o Storage responde 404 na exclusão, o endpoint devolvia 400
    e a linha nunca saía da tela).

    Agora a sequência sai do MAIOR número já usado nos caminhos daquele dia e
    categoria (não da contagem): número devolvido por uma exclusão nunca é
    reemitido enquanto sobrar qualquer documento, então dois documentos vivos
    jamais dividem o mesmo caminho.
    """
    prefixo_pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}/{_slug(categoria)}"
    abrev = _abreviar_categoria(categoria)
    prefixo_nome = f"{hoje.isoformat()}_{abrev}_"
    existentes = session.exec(
        select(DocumentoArquivado).where(
            DocumentoArquivado.fazenda_id == fazenda_id,
            DocumentoArquivado.categoria == categoria,
        )
    ).all()
    maior = 0
    vivos_do_dia = 0
    for d in existentes:
        nome = (d.caminho_storage or "").split("/")[-1]
        if not nome.startswith(prefixo_nome):
            continue
        vivos_do_dia += 1
        # "2026-09-06_NF_0003.pdf" -> 3. Caminho antigo/fora do padrão não
        # entra na conta (o `vivos_do_dia` cobre esse caso, como antes).
        numero = nome[len(prefixo_nome):].split(".", 1)[0]
        if numero.isdigit():
            maior = max(maior, int(numero))
    seq = 1 + max(maior, vivos_do_dia)
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
    documento = _buscar_documento_da_fazenda(session, documento_id, fazenda_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    try:
        conteudo = baixar_arquivo(documento.caminho_storage)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # A allow-list de content_type vale TAMBÉM na saída: os documentos
    # enviados antes da correção continuam gravados com o mime_type que o
    # cliente escolheu, e um "text/html" já armazenado voltaria a ser
    # renderizado inline se aqui confiássemos na coluna.
    media_type = documento.mime_type if documento.mime_type in _CONTENT_TYPES_PERMITIDOS else "application/octet-stream"
    return Response(
        content=conteudo, media_type=media_type,
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
    documento = _buscar_documento_da_fazenda(session, documento_id, fazenda_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    # Os documentos arquivados ANTES da correção de `_proximo_caminho` podem
    # dividir o mesmo caminho com outro documento vivo. Apagar o objeto nesse
    # caso derrubaria o download do irmão que fica — só remove do bucket
    # quando ninguém mais aponta para lá.
    # O recorte por fazenda entra NA PRÓPRIA consulta (nunca num `if` em
    # volta dela): sem multi-fazenda provisionado vira `fazenda_id IS NULL`,
    # que é exatamente o conjunto de linhas desse ambiente. Documento de
    # outra fazenda não é "irmão" de ninguém aqui.
    compartilhado = session.exec(
        select(DocumentoArquivado).where(
            DocumentoArquivado.fazenda_id == fazenda_id,
            DocumentoArquivado.caminho_storage == documento.caminho_storage,
            DocumentoArquivado.id != documento.id,
        )
    ).first()
    if not compartilhado:
        try:
            excluir_arquivo(documento.caminho_storage)
        except RuntimeError as exc:
            # BUG CORRIGIDO (mesmo defeito do anexo de Pessoa, relatado pelo
            # dono em 06/09/2026): a falha do Storage virava 400 e ABORTAVA a
            # exclusão da linha. Arquivo que já não está lá (apagado à mão no
            # painel do Supabase, caminho sobrescrito pelo bug de sequência
            # acima, upload que falhou no meio) devolve 404 no delete — e o
            # documento passava a ser IMPOSSÍVEL de tirar da tela: toda
            # tentativa repetia o mesmo 400, para sempre, porque a causa era
            # justamente o arquivo não existir mais. A linha do banco é o que
            # o dono enxerga e é ela que tem que sair; no pior caso sobra um
            # objeto órfão no bucket (invisível, sem nenhuma linha
            # apontando), muito melhor que um documento fantasma preso no
            # Arquivo.
            logger.warning(
                "Documento %s (%s): linha excluída mesmo com falha ao apagar o arquivo no Storage (%s): %s",
                documento.id, documento.categoria, documento.caminho_storage, exc,
            )
    session.delete(documento)
    session.commit()
    return {"excluido": True}
