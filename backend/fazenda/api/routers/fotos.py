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

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from fazenda.api.routers.portal import usuarios_da_fazenda
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import Animal, FotoCampo, PortalMensagem, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage

# BUG DE SEGURANÇA CORRIGIDO: content_type escolhido pelo cliente sem
# allow-list — mesma correção de documentos.py.
_CONTENT_TYPES_PERMITIDOS_FOTO = {"image/png", "image/jpeg", "image/webp", "image/gif"}

router = APIRouter(prefix="/fotos", tags=["fotos"])

logger = logging.getLogger(__name__)

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
    """fazenda-X/2026-09-06_0001.jpg — sequencial por dia.

    BUG CORRIGIDO (mesmo defeito do anexo de Pessoa, relatado pelo dono em
    06/09/2026 e corrigido em `cadastro/pessoas.py::_caminho_anexo_pessoa`,
    depois em pedidos.py e financeiro.py) — só que AQUI ele é GARANTIDO, não
    eventual, como no Arquivo fiscal (documentos.py::_proximo_caminho): a
    sequência vinha da CONTAGEM de fotos vivas do dia, e o nome no Storage é
    DETERMINÍSTICO (data + sequência, sem o nome do arquivo enviado). Nos
    outros módulos a colisão dependia de o usuário repetir o nome do arquivo;
    aqui basta ter 0001 e 0002 no mesmo dia: excluir a 0001 derruba a
    contagem para 1 e a próxima foto nasce 0002 — exatamente o caminho da que
    continua na galeria. O envio usa `x-upsert`, então o arquivo da 0002 é
    sobrescrito em silêncio e as DUAS linhas do banco passam a apontar para o
    mesmo objeto: a foto antiga passa a exibir a imagem nova, excluir uma
    apaga o arquivo das duas, e a outra fica travada para sempre (o Storage
    responde 404 na exclusão, o endpoint devolvia 400 e a linha nunca saía da
    galeria). No app móvel, em que o peão manda várias fotos do mesmo assunto
    no mesmo dia, isso acontece na PRIMEIRA exclusão.

    Agora a sequência sai do MAIOR número já usado nos caminhos daquele dia
    (não da contagem): número devolvido por uma exclusão nunca é reemitido
    enquanto sobrar qualquer foto, então duas fotos vivas jamais dividem o
    mesmo caminho.
    """
    prefixo_pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}"
    prefixo_nome = f"{hoje.isoformat()}_"
    existentes = session.exec(
        select(FotoCampo).where(FotoCampo.fazenda_id == fazenda_id)
    ).all()
    maior = 0
    vivas_do_dia = 0
    for f in existentes:
        nome = (f.caminho_storage or "").split("/")[-1]
        if not nome.startswith(prefixo_nome):
            continue
        vivas_do_dia += 1
        # "2026-09-06_0003.jpg" -> 3. Caminho antigo/fora do padrão não entra
        # na conta (o `vivas_do_dia` cobre esse caso, como antes).
        numero = nome[len(prefixo_nome):].split(".", 1)[0]
        if numero.isdigit():
            maior = max(maior, int(numero))
    seq = 1 + max(maior, vivas_do_dia)
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
    # Escrita usa o resolvedor ESTRITO, não o tolerante: com
    # `get_fazenda_atual_id`, um token sem "fid" gravava a foto com
    # `fazenda_id` nulo — órfã, e órfã passa por qualquer fazenda no padrão
    # `if fazenda_id is not None` espalhado pelo sistema. Mesmo defeito que o
    # PR #703 fechou em cartao_credito.py::criar_cartao.
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
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
        # O recorte entra NA CONSULTA, sem `if` em volta: `animal.numero`
        # deixou de ser único globalmente na migração c24befa94c1b, então
        # "0042" existe em várias fazendas ao mesmo tempo e sem a cláusula a
        # foto era vinculada ao animal de OUTRA fazenda com o mesmo número.
        animal = session.exec(
            select(Animal).where(
                Animal.numero == identificacao_animal,
                Animal.fazenda_id == fazenda_id,
            )
        ).first()
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


def _foto_da_fazenda(session: Session, foto_id: int, fazenda_id: int | None) -> FotoCampo | None:
    """Carrega UMA foto por id JÁ FILTRANDO por fazenda na própria consulta,
    em vez de `session.get()` seguido de um `if` sobre o objeto carregado
    (mesmo padrão de agenda.py::_buscar_da_fazenda).

    A checagem anterior era `if fazenda_id is not None and foto.fazenda_id !=
    fazenda_id`: com `fazenda_id` nulo — token sem "fid" — ela não comparava
    nada e QUALQUER foto de QUALQUER fazenda era baixada ou excluída pelo id.
    Hoje a trava de porta (auth.py::exigir_fazenda_selecionada, montada no
    router em main.py) recusa esse token antes de chegar aqui, então o furo
    não está aberto em produção; mas a guarda da rota não pode depender
    disso — é a mesma defesa em profundidade aplicada no PR #703.

    Filtrando na consulta, "de outra fazenda" e "sem fazenda" caem os dois no
    mesmo lugar: não encontrado. E `fazenda_id is None` só acontece onde o
    multi-fazenda não está provisionado (tabela `fazenda` vazia — suíte de
    testes e instalação anterior à f1a2b3c4d5e6), onde vira
    `fazenda_id IS NULL`, que é exatamente o conjunto de linhas daquele
    ambiente."""
    return session.exec(
        select(FotoCampo).where(FotoCampo.id == foto_id, FotoCampo.fazenda_id == fazenda_id)
    ).first()


@router.get("/{foto_id}/arquivo")
def baixar_foto(
    foto_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    """Proxy: busca no Supabase Storage e transmite os bytes de volta — o
    navegador nunca vê a URL do Supabase, só este endpoint (mesmo padrão de
    fazenda/api/routers/documentos.py::baixar_documento)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # 404, nunca 403: 403 confirmaria ao atacante que a foto existe.
    foto = _foto_da_fazenda(session, foto_id, fazenda_id)
    if not foto:
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    try:
        conteudo = baixar_arquivo(foto.caminho_storage, bucket=settings.supabase_bucket_fotos)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=conteudo, media_type=foto.mime_type)


@router.delete("/{foto_id}")
def excluir_foto(
    foto_id: int, session: Session = Depends(get_session),
    # Exclusão é escrita: resolvedor estrito, como no upload acima.
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    foto = _foto_da_fazenda(session, foto_id, fazenda_id)
    if not foto:
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    # As fotos enviadas ANTES da correção de `_proximo_caminho` podem dividir
    # o mesmo caminho com outra foto viva. Apagar o objeto nesse caso
    # derrubaria o download da irmã que fica — só remove do bucket quando
    # ninguém mais aponta para lá.
    # O recorte por fazenda entra NA PRÓPRIA consulta (nunca num `if` em
    # volta dela): sem multi-fazenda provisionado vira `fazenda_id IS NULL`,
    # que é exatamente o conjunto de linhas desse ambiente. Foto de outra
    # fazenda não é "irmã" de ninguém aqui.
    compartilhado = session.exec(
        select(FotoCampo).where(
            FotoCampo.fazenda_id == fazenda_id,
            FotoCampo.caminho_storage == foto.caminho_storage,
            FotoCampo.id != foto.id,
        )
    ).first()
    if not compartilhado:
        try:
            excluir_arquivo(foto.caminho_storage, bucket=settings.supabase_bucket_fotos)
        except RuntimeError as exc:
            # BUG CORRIGIDO (mesmo defeito do anexo de Pessoa, relatado pelo
            # dono em 06/09/2026): a falha do Storage virava 400 e ABORTAVA a
            # exclusão da linha. Arquivo que já não está lá (apagado à mão no
            # painel do Supabase, caminho sobrescrito pelo bug de sequência
            # acima, upload interrompido pela fila offline do app) devolve
            # 404 no delete — e a foto passava a ser IMPOSSÍVEL de tirar da
            # galeria: toda tentativa repetia o mesmo 400, para sempre,
            # porque a causa era justamente o arquivo não existir mais. A
            # linha do banco é o que o usuário enxerga e é ela que tem que
            # sair; no pior caso sobra um objeto órfão no bucket (invisível,
            # sem nenhuma linha apontando), muito melhor que uma foto
            # fantasma presa na galeria.
            logger.warning(
                "Foto %s: linha excluída mesmo com falha ao apagar o arquivo no Storage (%s): %s",
                foto.id, foto.caminho_storage, exc,
            )
    session.delete(foto)
    session.commit()
    return {"excluido": True}
