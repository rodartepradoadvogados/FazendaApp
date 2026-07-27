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
    CentroCusto, ContaCorrente, ContratoAnexo, ContratoAssinaturaZapSign, ContratoFazenda, ContratoFazendaModulo,
    EmpresaOperadora, Fazenda, PrecoModulo, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import (
    DESCONTO_CICLO_PAGAMENTO, MESES_POR_CICLO, MODULO_REBANHO, MODULOS_COMERCIAIS, PLANOS_CATALOGO,
)
from fazenda.rules.contrato_render import render_contrato
from fazenda.rules import zapsign
from fazenda.api.routers.cadastro.servicos import seed_tipos_metodos_servico
from fazenda.api.routers.cadastro.pessoas import seed_tipo_geral, seed_tipos_pessoa

router = APIRouter(prefix="/fazendas", tags=["fazendas"])

# Anexo do contrato assinado — mesmo limite/padrão de LancamentoAnexo (ver
# fazenda/api/routers/financeiro.py) — conteúdo em bytes no próprio banco.
TAMANHO_MAXIMO_ANEXO_CONTRATO = 15 * 1024 * 1024  # 15 MB


def _publico(f: Fazenda) -> dict:
    return {
        "id": f.id, "nome": f.nome, "cidade": f.cidade, "uf": f.uf, "ativa": f.ativa,
        "tipo_documento": f.tipo_documento, "documento": f.documento, "endereco": f.endereco, "cep": f.cep,
        "representante_nome": f.representante_nome, "representante_cpf": f.representante_cpf,
    }


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
    # Tipos de pessoa padrão (Funcionário/Veterinário/.../Empreiteiro) + "Geral"
    # — sem isso o Cadastro de Pessoas nasce sem nenhum tipo válido e toda
    # tentativa de cadastrar uma pessoa falha com "Tipo inválido".
    seed_tipos_pessoa(session, fazenda_id=fazenda_id)
    seed_tipo_geral(session, fazenda_id=fazenda_id)


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


class FazendaEditarIn(BaseModel):
    nome: str | None = None
    cidade: str | None = None
    uf: str | None = None
    tipo_documento: str | None = None  # "cpf" | "cnpj" — obrigatório junto com `documento`
    documento: str | None = None
    endereco: str | None = None
    cep: str | None = None
    representante_nome: str | None = None
    representante_cpf: str | None = None


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


@router.put("/{fazenda_id}")
def editar_fazenda(
    fazenda_id: int, dados: FazendaEditarIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    """Edita nome/cidade/uf e os dados jurídicos (tipo_documento+documento,
    endereço, cep, representante) usados como padrão no contrato-modelo e na
    cobrança — ver _publico/render_contrato. Todo campo é opcional: só
    atualiza o que veio preenchido. `documento` exige `tipo_documento`
    definido antes (ou no mesmo PUT) — sem isso, 400."""
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    if dados.nome is not None:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome da fazenda é obrigatório")
        fazenda.nome = nome
    if dados.cidade is not None:
        fazenda.cidade = dados.cidade.strip() or None
    if dados.uf is not None:
        fazenda.uf = dados.uf.strip() or None
    if dados.tipo_documento is not None:
        if dados.tipo_documento not in ("cpf", "cnpj", ""):
            raise HTTPException(status_code=400, detail="tipo_documento deve ser \"cpf\" ou \"cnpj\"")
        fazenda.tipo_documento = dados.tipo_documento or None
    if dados.documento is not None:
        if dados.documento.strip() and not fazenda.tipo_documento:
            raise HTTPException(status_code=400, detail="Escolha se o documento é CPF ou CNPJ antes de preencher o número")
        fazenda.documento = dados.documento.strip() or None
    if dados.endereco is not None:
        fazenda.endereco = dados.endereco.strip() or None
    if dados.cep is not None:
        fazenda.cep = dados.cep.strip() or None
    if dados.representante_nome is not None:
        fazenda.representante_nome = dados.representante_nome.strip() or None
    if dados.representante_cpf is not None:
        fazenda.representante_cpf = dados.representante_cpf.strip() or None
    session.add(fazenda)
    session.commit()
    session.refresh(fazenda)
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
    ciclo_pagamento: str = "mensal"  # "mensal"/"trimestral"/"semestral" — ver DESCONTO_CICLO_PAGAMENTO


def _preco_mensal_contrato(contrato: ContratoFazenda, modulos: list[ContratoFazendaModulo]) -> float:
    if contrato.plano and contrato.plano in PLANOS_CATALOGO:
        return PLANOS_CATALOGO[contrato.plano]["preco"]
    return sum(m.preco for m in modulos if m.ativo)


def _publico_contrato(session: Session, fazenda_id: int) -> dict:
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    modulos = session.exec(
        select(ContratoFazendaModulo).where(ContratoFazendaModulo.fazenda_id == fazenda_id)
    ).all()
    if not contrato:
        return {"fazenda_id": fazenda_id, "status": None, "plano": None, "modulos": [], "ciclo_pagamento": "mensal"}
    preco_mensal = _preco_mensal_contrato(contrato, modulos)
    desconto = DESCONTO_CICLO_PAGAMENTO.get(contrato.ciclo_pagamento, 0.0)
    meses = MESES_POR_CICLO.get(contrato.ciclo_pagamento, 1)
    return {
        "fazenda_id": fazenda_id,
        "status": contrato.status,
        "plano": contrato.plano,
        "aprovado_por_usuario_id": contrato.aprovado_por_usuario_id,
        "data_fechamento": contrato.data_fechamento.isoformat() if contrato.data_fechamento else None,
        "modulos": [{"modulo": m.modulo, "preco": m.preco, "ativo": m.ativo} for m in modulos],
        "ciclo_pagamento": contrato.ciclo_pagamento,
        "desconto_pct": desconto * 100,
        "preco_mensal": preco_mensal,
        "valor_total_ciclo": round(preco_mensal * meses * (1 - desconto), 2),
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
    if dados.ciclo_pagamento not in DESCONTO_CICLO_PAGAMENTO:
        raise HTTPException(status_code=400, detail=f"Ciclo de pagamento inválido: {dados.ciclo_pagamento}")

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
    contrato.ciclo_pagamento = dados.ciclo_pagamento
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


@router.get("/catalogo/resumo-cowdata")
def resumo_cowdata(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    """Números agregados pra o Cockpit do Painel CowData (ver frontend
    app/painel-cowdata/) — MRR real (soma do preço mensal só dos contratos
    "ativo"), nunca um valor fixo/mockado."""
    fazendas = session.exec(select(Fazenda)).all()
    contratos = {c.fazenda_id: c for c in session.exec(select(ContratoFazenda)).all()}
    modulos_por_fazenda: dict[int, list[ContratoFazendaModulo]] = {}
    for m in session.exec(select(ContratoFazendaModulo).where(ContratoFazendaModulo.ativo == True)).all():  # noqa: E712
        modulos_por_fazenda.setdefault(m.fazenda_id, []).append(m)

    mrr = 0.0
    contagem = {"ativo": 0, "aguardando_aprovacao": 0, "suspenso": 0, "sem_contrato": 0}
    for f in fazendas:
        c = contratos.get(f.id)
        if not c:
            contagem["sem_contrato"] += 1
            continue
        contagem[c.status] = contagem.get(c.status, 0) + 1
        if c.status == "ativo":
            mrr += _preco_mensal_contrato(c, modulos_por_fazenda.get(f.id, []))

    return {"total_fazendas": len(fazendas), "mrr": round(mrr, 2), **contagem}


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


# ---------------------------------------------------------------------------
# Contrato-modelo (minuta CowData) — "Baixar contrato" gera o HTML pronto pra
# imprimir/assinar a partir do plano real da fazenda (ver
# fazenda/rules/contrato_render.py); "Assinar contrato" manda a mesma minuta
# (em markdown) pro ZapSign e devolve o link de assinatura (ver
# fazenda/rules/zapsign.py). Nenhum dos dois documentos é gravado aqui — o
# que fica registrado é só a tentativa de assinatura (ContratoAssinaturaZapSign)
# e, quando o cliente devolve assinado, o anexo (endpoints acima).
# ---------------------------------------------------------------------------
def _dados_para_minuta(session: Session, fazenda: Fazenda) -> tuple[str | None, list[str], float, str]:
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda.id)).first()
    if not contrato:
        raise HTTPException(status_code=400, detail="Fazenda ainda não tem contrato definido — defina o plano antes (PUT .../contrato)")
    modulos = session.exec(
        select(ContratoFazendaModulo).where(ContratoFazendaModulo.fazenda_id == fazenda.id, ContratoFazendaModulo.ativo == True)  # noqa: E712
    ).all()
    preco_mensal = _preco_mensal_contrato(contrato, modulos)
    return contrato.plano, [m.modulo for m in modulos], preco_mensal, contrato.ciclo_pagamento


@router.get("/{fazenda_id}/contrato/modelo")
def baixar_modelo_contrato(
    fazenda_id: int, documento: str | None = None, endereco: str | None = None,
    representante_nome: str | None = None, representante_cpf: str | None = None,
    cidade_foro: str | None = None, estado_foro: str | None = None,
    _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> Response:
    """Minuta do contrato pronta pra ler/imprimir/assinar à mão — os campos de
    query (documento/endereço/representante/foro) são opcionais e servem só
    pra sobrescrever pontualmente; o padrão vem do cadastro da fazenda
    (Fazendas > editar) — sem nenhum dos dois, o modelo sai com "[PREENCHER]"."""
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    empresa = session.exec(select(EmpresaOperadora)).first()
    plano, modulos, preco_mensal, ciclo = _dados_para_minuta(session, fazenda)
    html = render_contrato(
        "html", fazenda, empresa, plano, modulos, preco_mensal, ciclo,
        documento or fazenda.documento, endereco or fazenda.endereco,
        representante_nome or fazenda.representante_nome, representante_cpf or fazenda.representante_cpf,
        cidade_foro, estado_foro,
    )
    return Response(
        content=html, media_type="text/html",
        headers={"Content-Disposition": f'inline; filename="contrato-cowdata-{fazenda.nome}.html"'},
    )


@router.post("/{fazenda_id}/contrato/assinar-zapsign")
def assinar_contrato_zapsign(
    fazenda_id: int, user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    """Cria a solicitação de assinatura eletrônica no ZapSign para o contrato
    desta fazenda e devolve o link de assinatura. Requer ZAPSIGN_API_TOKEN
    configurado (ver fazenda/config.py) — sem isso, erro 400 explicando o que falta."""
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    if not user.email:
        raise HTTPException(status_code=400, detail="Seu usuário precisa de um e-mail cadastrado para assinar via ZapSign")
    empresa = session.exec(select(EmpresaOperadora)).first()
    plano, modulos, preco_mensal, ciclo = _dados_para_minuta(session, fazenda)
    markdown = render_contrato(
        "md", fazenda, empresa, plano, modulos, preco_mensal, ciclo,
        fazenda.documento, fazenda.endereco, fazenda.representante_nome, fazenda.representante_cpf,
    )
    try:
        resposta = zapsign.criar_documento_para_assinatura(
            f"Contrato CowData — {fazenda.nome}", markdown, user.nome or user.username, user.email,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # erro de rede/API do ZapSign — não é bug nosso, mas o usuário precisa saber
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com o ZapSign: {e}")

    signer = (resposta.get("signers") or [{}])[0]
    tentativa = ContratoAssinaturaZapSign(
        fazenda_id=fazenda_id,
        document_token=resposta["token"],
        signer_token=signer.get("token"),
        sign_url=signer.get("sign_url"),
        status=resposta.get("status", "pending"),
        solicitado_por_usuario_id=user.id,
    )
    session.add(tentativa)
    session.commit()
    session.refresh(tentativa)
    return {"id": tentativa.id, "document_token": tentativa.document_token, "sign_url": tentativa.sign_url, "status": tentativa.status}


@router.get("/{fazenda_id}/contrato/assinatura-zapsign")
def status_assinatura_zapsign(
    fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict | None:
    """Última tentativa de assinatura via ZapSign desta fazenda (o status é
    atualizado pelo webhook — ver fazenda/api/routers/zapsign.py — não faz
    polling na API do ZapSign aqui)."""
    tentativa = session.exec(
        select(ContratoAssinaturaZapSign)
        .where(ContratoAssinaturaZapSign.fazenda_id == fazenda_id)
        .order_by(ContratoAssinaturaZapSign.criado_em.desc())
    ).first()
    if not tentativa:
        return None
    return {
        "id": tentativa.id, "document_token": tentativa.document_token, "sign_url": tentativa.sign_url,
        "status": tentativa.status, "criado_em": tentativa.criado_em.isoformat(),
        "assinado_em": tentativa.assinado_em.isoformat() if tentativa.assinado_em else None,
    }
