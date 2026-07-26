"""
Piloto conservador de multi-fazenda — cadastro de Fazenda e vínculo com
Usuario. Restrito ao proprietário (mesma trava de /auth/usuarios) enquanto
isto for só um piloto interno: criar uma fazenda ou vincular alguém a ela é
uma operação sensível (decide quem vê o quê), não um cadastro comum.

Ver fazenda/models/multitenant.py (Fazenda/UsuarioFazenda) e
fazenda/api/routers/auth.py (POST /auth/login, POST /auth/selecionar-fazenda).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import EMAIL_DONO, exigir_contratante_ou_dono, exigir_dono, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    CentroCusto, ContaCorrente, ContratoAnexo, ContratoFazenda, ContratoFazendaModulo, Fazenda, PrecoModulo,
    Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULO_REBANHO, MODULOS_COMERCIAIS, PLANOS_CATALOGO
from fazenda.api.routers.cadastro.servicos import seed_tipos_metodos_servico

router = APIRouter(prefix="/fazendas", tags=["fazendas"])

# Anexo do contrato assinado — mesmo limite/padrão de LancamentoAnexo (ver
# fazenda/api/routers/financeiro.py) — conteúdo em bytes no próprio banco.
TAMANHO_MAXIMO_ANEXO_CONTRATO = 15 * 1024 * 1024  # 15 MB


def _publico(f: Fazenda) -> dict:
    return {"id": f.id, "nome": f.nome, "cidade": f.cidade, "uf": f.uf, "ativa": f.ativa}


def provisionar_fazenda_nova(session: Session, fazenda_id: int) -> None:
    """Provisionamento padrão de uma fazenda recém-criada — só o que é
    seguro nascer em branco/genérico (não copia nada real da fazenda #1):
    - Contas correntes "Banco" e "Carteira", em branco, editáveis.
    - Centros de custo "Pecuária Leiteira" e "Agricultura".
    - Contrato aguardando aprovação, SEM nenhum módulo ativo — nada funciona
      (nem Rebanho, que é obrigatório em todo plano) até você escolher o
      plano/módulos e aprovar/fechar o contrato (ver endpoints abaixo).
    Pessoas e calendário sanitário nascem vazios de propósito (cada fazenda
    cadastra os seus funcionários e sua própria agenda sanitária) — ver
    fazenda/models/pessoal.py::Pessoa e fazenda/models/sanidade.py::CalendarioSanitario."""
    session.add_all([
        ContaCorrente(banco="Banco", agencia="", numero_conta="", fazenda_id=fazenda_id),
        ContaCorrente(banco="Carteira", agencia="", numero_conta="", fazenda_id=fazenda_id),
        CentroCusto(nome="Pecuária Leiteira", fazenda_id=fazenda_id),
        CentroCusto(nome="Agricultura", fazenda_id=fazenda_id),
        ContratoFazenda(fazenda_id=fazenda_id, status="aguardando_aprovacao"),
    ])
    session.commit()
    # Vocabulário mínimo de Serviço/Inseminação (Cobertura/IA + Monta
    # Natural/IA em cio natural/IATF) — sem isso a fazenda nasce sem nenhum
    # tipo/método e o lançamento de Serviço/Inseminação fica vazio.
    seed_tipos_metodos_servico(session, fazenda_id=fazenda_id)


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
    usuario_id: int | None = None
    username: str | None = None  # alternativa a usuario_id — resolvido pelo backend
    contratante: bool = False
    # Vínculo de consultor externo (veterinário, contador, agrônomo) — só
    # aceito se a fazenda tiver o módulo comercial "consultor" contratado e
    # ativo (plano Diamond). Nunca junto de contratante=True.
    consultor: bool = False


def _tem_modulo_consultor_ativo(session: Session, fazenda_id: int) -> bool:
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    if not contrato or contrato.status != "ativo":
        return False
    return session.exec(
        select(ContratoFazendaModulo).where(
            ContratoFazendaModulo.fazenda_id == fazenda_id,
            ContratoFazendaModulo.modulo == "consultor",
            ContratoFazendaModulo.ativo == True,  # noqa: E712
        )
    ).first() is not None


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
    if dados.contratante and dados.consultor:
        raise HTTPException(status_code=400, detail="Um vínculo não pode ser contratante e consultor ao mesmo tempo")
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    usuario = None
    if dados.usuario_id is not None:
        usuario = session.get(Usuario, dados.usuario_id)
    elif dados.username:
        usuario = session.exec(select(Usuario).where(Usuario.username == dados.username)).first()
    else:
        raise HTTPException(status_code=400, detail="Informe usuario_id ou username")
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if dados.consultor and not _tem_modulo_consultor_ativo(session, fazenda_id):
        raise HTTPException(
            status_code=403,
            detail="Esta fazenda não tem o módulo Consultor contratado (disponível no plano Diamond)",
        )
    ja_vinculado = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario.id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if ja_vinculado:
        raise HTTPException(status_code=400, detail=f"{usuario.username} já está vinculado a esta fazenda")
    session.add(UsuarioFazenda(
        usuario_id=usuario.id, fazenda_id=fazenda_id, contratante=dados.contratante, consultor=dados.consultor,
    ))
    session.commit()
    return {"vinculado": True, "usuario_id": usuario.id, "username": usuario.username}


@router.get("/{fazenda_id}/usuarios")
def listar_usuarios_vinculados(
    fazenda_id: int, user: Usuario = Depends(exigir_contratante_ou_dono),
    fazenda_id_token: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    _validar_escopo_contratante(user, fazenda_id, fazenda_id_token)
    vinculos = session.exec(select(UsuarioFazenda).where(UsuarioFazenda.fazenda_id == fazenda_id)).all()
    resultado = []
    for v in vinculos:
        usuario = session.get(Usuario, v.usuario_id)
        if not usuario:
            continue
        resultado.append({
            "usuario_id": usuario.id, "username": usuario.username, "nome": usuario.nome,
            "contratante": v.contratante, "consultor": v.consultor,
        })
    return resultado


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


# ---------------------------------------------------------------------------
# Planos e contrato por fazenda — quem contrata o quê, com atenção de que
# nada (nem Rebanho) libera antes da aprovação/fechamento (ver
# provisionar_fazenda_nova acima e exigir_modulo_contratado/exigir_contrato_ativo
# em fazenda/auth.py, usados nos include_router de main.py).
# ---------------------------------------------------------------------------
class ModuloContratoIn(BaseModel):
    modulo: str
    preco: float


class ContratoIn(BaseModel):
    plano: str | None = None  # chave de PLANOS_CATALOGO, ou None para "sob medida"
    modulos: list[ModuloContratoIn] = []  # só usado quando plano é None


def _publico_contrato(session: Session, fazenda_id: int) -> dict:
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    modulos = session.exec(
        select(ContratoFazendaModulo).where(ContratoFazendaModulo.fazenda_id == fazenda_id)
    ).all()
    if not contrato:
        return {"fazenda_id": fazenda_id, "status": None, "plano": None, "modulos": []}
    return {
        "fazenda_id": fazenda_id,
        "status": contrato.status,
        "plano": contrato.plano,
        "aprovado_por_usuario_id": contrato.aprovado_por_usuario_id,
        "data_fechamento": contrato.data_fechamento.isoformat() if contrato.data_fechamento else None,
        "modulos": [{"modulo": m.modulo, "preco": m.preco, "ativo": m.ativo} for m in modulos],
    }


@router.get("/{fazenda_id}/contrato")
def obter_contrato(fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    if not session.get(Fazenda, fazenda_id):
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    return _publico_contrato(session, fazenda_id)


@router.put("/{fazenda_id}/contrato")
def definir_contrato(
    fazenda_id: int, dados: ContratoIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    """Monta o "rascunho" do contrato — plano fechado (Standard/Silver/Gold/
    Diamond, preço do pacote) ou módulos avulsos sob medida (preço livre por
    módulo). Não muda o status: uma fazenda nova continua aguardando
    aprovação até POST /{fazenda_id}/contrato/aprovar; editar os módulos de
    uma fazenda já ativa aplica na hora (é você mesmo, dono, editando)."""
    if not session.get(Fazenda, fazenda_id):
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    if dados.plano is not None and dados.plano not in PLANOS_CATALOGO:
        raise HTTPException(status_code=400, detail=f"Plano inválido: {dados.plano}")

    if dados.plano is not None:
        pacote = PLANOS_CATALOGO[dados.plano]
        novos = [{"modulo": m, "preco": pacote["preco"] if m == MODULO_REBANHO else 0.0} for m in pacote["modulos"]]
        # Preço do pacote fica só na 1ª linha (rebanho) pra não somar errado
        # num relatório futuro — os demais módulos do mesmo pacote entram
        # com preço 0 (o valor cobrado é o do plano, não a soma dos módulos).
    else:
        nomes_invalidos = [m.modulo for m in dados.modulos if m.modulo not in MODULOS_COMERCIAIS]
        if nomes_invalidos:
            raise HTTPException(status_code=400, detail=f"Módulo(s) inválido(s): {', '.join(nomes_invalidos)}")
        if not any(m.modulo == MODULO_REBANHO for m in dados.modulos):
            raise HTTPException(status_code=400, detail="Rebanho é obrigatório em todo contrato")
        novos = [{"modulo": m.modulo, "preco": m.preco} for m in dados.modulos]

    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    if not contrato:
        contrato = ContratoFazenda(fazenda_id=fazenda_id)
        session.add(contrato)
    contrato.plano = dados.plano
    contrato.atualizado_em = datetime.utcnow()
    session.add(contrato)

    existentes = {
        m.modulo: m for m in session.exec(
            select(ContratoFazendaModulo).where(ContratoFazendaModulo.fazenda_id == fazenda_id)
        ).all()
    }
    modulos_novos = {n["modulo"] for n in novos}
    for nome, linha in existentes.items():
        linha.ativo = nome in modulos_novos
        if linha.ativo:
            linha.preco = next(n["preco"] for n in novos if n["modulo"] == nome)
        session.add(linha)
    for n in novos:
        if n["modulo"] not in existentes:
            session.add(ContratoFazendaModulo(fazenda_id=fazenda_id, modulo=n["modulo"], preco=n["preco"], ativo=True))
    session.commit()
    return _publico_contrato(session, fazenda_id)


@router.post("/{fazenda_id}/contrato/aprovar")
def aprovar_contrato(
    fazenda_id: int, user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    """Aprova/fecha o contrato — a partir daqui os módulos definidos em PUT
    .../contrato liberam de verdade para a fazenda. Idempotente: também serve
    para reativar uma fazenda suspensa."""
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    if not contrato:
        raise HTTPException(status_code=404, detail="Fazenda não tem contrato — defina os módulos antes (PUT)")
    tem_modulo_ativo = session.exec(
        select(ContratoFazendaModulo).where(
            ContratoFazendaModulo.fazenda_id == fazenda_id, ContratoFazendaModulo.ativo == True,  # noqa: E712
        )
    ).first()
    if not tem_modulo_ativo:
        raise HTTPException(status_code=400, detail="Defina ao menos um módulo (PUT .../contrato) antes de aprovar")
    contrato.status = "ativo"
    contrato.aprovado_por_usuario_id = user.id
    contrato.data_fechamento = datetime.utcnow()
    contrato.atualizado_em = datetime.utcnow()
    session.add(contrato)
    session.commit()
    return _publico_contrato(session, fazenda_id)


@router.post("/{fazenda_id}/contrato/suspender")
def suspender_contrato(
    fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    if not contrato:
        raise HTTPException(status_code=404, detail="Fazenda não tem contrato")
    contrato.status = "suspenso"
    contrato.atualizado_em = datetime.utcnow()
    session.add(contrato)
    session.commit()
    return _publico_contrato(session, fazenda_id)


@router.get("/catalogo/planos")
def listar_planos_catalogo(_: Usuario = Depends(exigir_dono)) -> dict:
    return PLANOS_CATALOGO


@router.get("/catalogo/precos-modulo")
def listar_precos_modulo(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    existentes = {p.modulo: p for p in session.exec(select(PrecoModulo)).all()}
    return [
        {"modulo": m, "preco": existentes[m].preco if m in existentes else 0.0}
        for m in MODULOS_COMERCIAIS
    ]


@router.put("/catalogo/precos-modulo/{modulo}")
def atualizar_preco_modulo(
    modulo: str, dados: ModuloContratoIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    if modulo not in MODULOS_COMERCIAIS:
        raise HTTPException(status_code=400, detail=f"Módulo inválido: {modulo}")
    preco = session.exec(select(PrecoModulo).where(PrecoModulo.modulo == modulo)).first()
    if not preco:
        preco = PrecoModulo(modulo=modulo)
    preco.preco = dados.preco
    preco.atualizado_em = datetime.utcnow()
    session.add(preco)
    session.commit()
    return {"modulo": preco.modulo, "preco": preco.preco}


# ---------------------------------------------------------------------------
# Anexo do contrato assinado — consulta e segurança jurídica (bytes no banco,
# mesmo padrão de LancamentoAnexo — sobrevive a redeploy).
# ---------------------------------------------------------------------------
@router.post("/{fazenda_id}/contrato/anexos", status_code=201)
async def anexar_contrato(
    fazenda_id: int, file: UploadFile,
    user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    if not session.get(Fazenda, fazenda_id):
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_ANEXO_CONTRATO:
        raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB — não é possível anexar")
    anexo = ContratoAnexo(
        fazenda_id=fazenda_id,
        nome_arquivo=file.filename or "contrato",
        mime_type=file.content_type or "application/octet-stream",
        tamanho_bytes=len(conteudo),
        conteudo=conteudo,
        usuario_id=user.id,
    )
    session.add(anexo)
    session.commit()
    session.refresh(anexo)
    return {"id": anexo.id, "nome_arquivo": anexo.nome_arquivo, "mime_type": anexo.mime_type, "tamanho_bytes": anexo.tamanho_bytes}


@router.get("/{fazenda_id}/contrato/anexos")
def listar_anexos_contrato(
    fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> list[dict]:
    anexos = session.exec(select(ContratoAnexo).where(ContratoAnexo.fazenda_id == fazenda_id)).all()
    return [
        {"id": a.id, "nome_arquivo": a.nome_arquivo, "mime_type": a.mime_type, "tamanho_bytes": a.tamanho_bytes,
         "criado_em": a.criado_em.isoformat()}
        for a in anexos
    ]


@router.get("/contrato/anexos/{anexo_id}")
def baixar_anexo_contrato(
    anexo_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> Response:
    anexo = session.get(ContratoAnexo, anexo_id)
    if not anexo:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    return Response(
        content=anexo.conteudo, media_type=anexo.mime_type,
        headers={"Content-Disposition": f'inline; filename="{anexo.nome_arquivo}"'},
    )


@router.delete("/contrato/anexos/{anexo_id}")
def excluir_anexo_contrato(
    anexo_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    anexo = session.get(ContratoAnexo, anexo_id)
    if not anexo:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    session.delete(anexo)
    session.commit()
    return {"excluido": True}
