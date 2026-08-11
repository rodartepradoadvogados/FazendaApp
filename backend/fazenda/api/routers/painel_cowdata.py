"""
Painel Mestre CowData — Equipe própria da CowData (Sócio/Comercial/T.I./
Financeiro/Marketing/Suporte) e Financeiro CowData (livro-caixa independente
de qualquer fazenda-cliente). Ver fazenda/models/multitenant.py::
Fazenda.eh_empresa_cowdata e fazenda/models/cowdata_interno.py::LancamentoCowData.

Tudo aqui exige a área "equipe" ou "financeiro" do Painel CowData conforme a
seção (dono sempre passa; membro da Equipe CowData só com a área liberada —
ver exigir_area_painel_cowdata em fazenda/auth.py), exceto a criação/edição
do PRÓPRIO login de um membro (POST/PUT .../usuario), que fica restrita ao
proprietário (`exigir_dono`). Opera sempre sobre a ÚNICA fazenda marcada
`eh_empresa_cowdata=True` — nunca sobre a fazenda selecionada no token
(get_fazenda_atual_id), que é irrelevante aqui.
Reaproveita os modelos Pessoa/FolhaPagamento (mesmo formato da folha de
pagamento de qualquer fazenda-cliente), mas por endpoints NOVOS e isolados —
nenhuma alteração nos routers tenant-facing já testados.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_area_painel_cowdata, exigir_dono, hash_senha
from fazenda.database import get_session
from fazenda.models import CobrancaAsaas, Fazenda, FolhaPagamento, Pessoa, SeedFlag, TipoPessoa, Usuario
from fazenda.models.cowdata_interno import LancamentoCowData
from fazenda.models.equipe_cowdata_acesso import AREAS_PAINEL_COWDATA, PermissaoEquipeCowData
from fazenda.models.multitenant import EmpresaOperadora
from fazenda.rules.contrato_equipe_render import nome_arquivo_contrato, render_contrato_equipe

router = APIRouter(prefix="/painel-cowdata", tags=["painel-cowdata"])

NOME_FAZENDA_COWDATA = "CowData (empresa)"

CARGOS_COWDATA = ["Sócio", "Comercial", "T.I.", "Financeiro", "Marketing", "Suporte", "Consultor"]

TIPOS_VINCULO = ["funcionario", "pj"]
SUBTIPOS_PJ = ["MEI", "ME", "EPP", "Outros"]


def seed_cowdata_empresa(session: Session) -> Fazenda:
    """Garante a existência da fazenda "lógica" que ancora Equipe/Financeiro
    CowData (get-or-create — idempotente) e semeia os cargos padrão (uma vez,
    via SeedFlag, mesmo padrão de seed_tipos_pessoa) sem nunca sobrescrever
    cargos adicionados depois pelo usuário."""
    fazenda = session.exec(select(Fazenda).where(Fazenda.eh_empresa_cowdata == True)).first()  # noqa: E712
    if not fazenda:
        fazenda = Fazenda(nome=NOME_FAZENDA_COWDATA, eh_empresa_cowdata=True)
        session.add(fazenda)
        session.commit()
        session.refresh(fazenda)

    chave = "cowdata_cargos_v1"
    if not session.get(SeedFlag, chave):
        for nome in CARGOS_COWDATA:
            existe = session.exec(
                select(TipoPessoa).where(TipoPessoa.nome == nome, TipoPessoa.fazenda_id == fazenda.id)
            ).first()
            if not existe:
                session.add(TipoPessoa(nome=nome, fazenda_id=fazenda.id))
        session.add(SeedFlag(chave=chave))
        session.commit()
    # "Consultor" (ago/2026) chegou depois do SeedFlag original já ter
    # rodado em produção — garante a existência dele à parte, sem depender
    # de um SeedFlag novo (idempotente por natureza: só cria se não existir,
    # nunca reseta cargos que o usuário já editou/removeu de propósito).
    if not session.exec(select(TipoPessoa).where(TipoPessoa.nome == "Consultor", TipoPessoa.fazenda_id == fazenda.id)).first():
        session.add(TipoPessoa(nome="Consultor", fazenda_id=fazenda.id))
        session.commit()
    return fazenda


def _fazenda_cowdata_id(session: Session) -> int:
    fazenda = session.exec(select(Fazenda).where(Fazenda.eh_empresa_cowdata == True)).first()  # noqa: E712
    if not fazenda:
        raise HTTPException(status_code=500, detail="Fazenda interna da CowData não provisionada")
    return fazenda.id


# ---------------------------------------------------------------------------
# Equipe CowData
# ---------------------------------------------------------------------------
class PessoaCowDataIn(BaseModel):
    nome: str
    cargo: str  # um de CARGOS_COWDATA (ou outro já cadastrado)
    telefones: list[str] = []
    emails: list[str] = []
    cpf_cnpj: Optional[str] = None
    cep: Optional[str] = None
    salario_base: Optional[float] = None
    data_admissao: Optional[date] = None
    observacoes: Optional[str] = None
    ativo: bool = True
    # Campos acrescentados a pedido do usuário (ago/2026) — RG/gênero/estado
    # civil/endereço já existiam em Pessoa (colunas jul/2026, reaproveitadas
    # aqui pela primeira vez neste formulário específico); tipo_vinculo/
    # subtipo_pj/pagamento_mensal são novos (ver models/pessoal.py).
    rg: Optional[str] = None
    genero: Optional[str] = None
    estado_civil: Optional[str] = None
    endereco_rua: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_cidade: Optional[str] = None
    endereco_uf: Optional[str] = None
    tipo_vinculo: Optional[str] = None  # "funcionario" | "pj"
    subtipo_pj: Optional[str] = None  # obrigatório (validado abaixo) quando tipo_vinculo == "pj"
    pagamento_mensal: Optional[float] = None


def _validar_vinculo(dados: "PessoaCowDataIn") -> None:
    if dados.tipo_vinculo is not None and dados.tipo_vinculo not in TIPOS_VINCULO:
        raise HTTPException(status_code=400, detail="Tipo de vínculo inválido")
    if dados.tipo_vinculo == "pj" and dados.subtipo_pj and dados.subtipo_pj not in SUBTIPOS_PJ:
        raise HTTPException(status_code=400, detail="Subtipo de PJ inválido — escolha MEI, ME, EPP ou Outros")


def _pessoa_publica(p: Pessoa) -> dict:
    return {
        "id": p.id,
        "nome": p.nome,
        "cargo": p.tipo,
        "telefones": json.loads(p.telefones) if p.telefones else [],
        "emails": json.loads(p.emails) if p.emails else [],
        "cpf_cnpj": p.cpf_cnpj,
        "cep": p.cep,
        "salario_base": p.salario_base,
        "data_admissao": p.data_admissao,
        "observacoes": p.observacoes,
        "ativo": p.ativo,
        "rg": p.rg,
        "genero": p.genero,
        "estado_civil": p.estado_civil,
        "endereco_rua": p.endereco_rua,
        "endereco_numero": p.endereco_numero,
        "endereco_bairro": p.endereco_bairro,
        "endereco_cidade": p.endereco_cidade,
        "endereco_uf": p.endereco_uf,
        "tipo_vinculo": p.tipo_vinculo,
        "subtipo_pj": p.subtipo_pj,
        "pagamento_mensal": p.pagamento_mensal,
    }


@router.get("/equipe/tipos-vinculo")
def listar_tipos_vinculo(_: Usuario = Depends(exigir_area_painel_cowdata("equipe"))) -> dict:
    return {"tipos_vinculo": TIPOS_VINCULO, "subtipos_pj": SUBTIPOS_PJ}


@router.get("/equipe/cargos")
def listar_cargos(_: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)) -> list[str]:
    fazenda_id = _fazenda_cowdata_id(session)
    tipos = session.exec(
        select(TipoPessoa).where(TipoPessoa.fazenda_id == fazenda_id, TipoPessoa.ativo == True)  # noqa: E712
    ).all()
    return [t.nome for t in tipos]


@router.get("/equipe/pessoas")
def listar_equipe(_: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)) -> list[dict]:
    fazenda_id = _fazenda_cowdata_id(session)
    pessoas = session.exec(select(Pessoa).where(Pessoa.fazenda_id == fazenda_id)).all()
    return [_pessoa_publica(p) for p in sorted(pessoas, key=lambda p: p.nome)]


@router.get("/equipe/consultores")
def listar_consultores_cowdata(
    _: Usuario = Depends(exigir_area_painel_cowdata("fazendas")), session: Session = Depends(get_session)
) -> list[dict]:
    """Membros ATIVOS da Equipe CowData com cargo Consultor que já têm login
    próprio ATIVO — é a lista do seletor "Consultor CowData" ao definir o
    plano de uma fazenda-cliente (ver FazendasAdmin.tsx). Fica na área
    `fazendas` (não `equipe`) de propósito: quem administra contrato de
    cliente precisa desta lista, mesmo sem acesso ao cadastro da Equipe."""
    fazenda_id = _fazenda_cowdata_id(session)
    pessoas = session.exec(
        select(Pessoa).where(
            Pessoa.fazenda_id == fazenda_id, Pessoa.tipo == "Consultor", Pessoa.ativo == True,  # noqa: E712
        )
    ).all()
    if not pessoas:
        return []
    por_pessoa_id = {p.id: p for p in pessoas}
    usuarios = session.exec(
        select(Usuario).where(
            Usuario.pessoa_id.in_(list(por_pessoa_id)), Usuario.ativo == True,  # noqa: E712
        )
    ).all()
    saida = [
        {
            "pessoa_id": u.pessoa_id,
            "usuario_id": u.id,
            "nome": por_pessoa_id[u.pessoa_id].nome,
            "username": u.username,
            "email": u.email,
        }
        for u in usuarios
        if u.pessoa_id in por_pessoa_id
    ]
    return sorted(saida, key=lambda c: c["nome"])


@router.post("/equipe/pessoas")
def criar_membro_equipe(
    dados: PessoaCowDataIn, _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)
) -> dict:
    fazenda_id = _fazenda_cowdata_id(session)
    cargo_existe = session.exec(
        select(TipoPessoa).where(TipoPessoa.nome == dados.cargo, TipoPessoa.fazenda_id == fazenda_id)
    ).first()
    if not cargo_existe:
        raise HTTPException(status_code=400, detail="Cargo inválido")
    _validar_vinculo(dados)
    pessoa = Pessoa(
        fazenda_id=fazenda_id,
        nome=dados.nome,
        tipo=dados.cargo,
        telefones=json.dumps(dados.telefones) if dados.telefones else None,
        emails=json.dumps(dados.emails) if dados.emails else None,
        telefone=dados.telefones[0] if dados.telefones else None,
        email=dados.emails[0] if dados.emails else None,
        cpf_cnpj=dados.cpf_cnpj,
        cep=dados.cep,
        salario_base=dados.salario_base,
        data_admissao=dados.data_admissao,
        observacoes=dados.observacoes,
        ativo=dados.ativo,
        rg=dados.rg,
        genero=dados.genero,
        estado_civil=dados.estado_civil,
        endereco_rua=dados.endereco_rua,
        endereco_numero=dados.endereco_numero,
        endereco_bairro=dados.endereco_bairro,
        endereco_cidade=dados.endereco_cidade,
        endereco_uf=dados.endereco_uf,
        tipo_vinculo=dados.tipo_vinculo,
        subtipo_pj=dados.subtipo_pj if dados.tipo_vinculo == "pj" else None,
        pagamento_mensal=dados.pagamento_mensal,
    )
    session.add(pessoa)
    session.commit()
    session.refresh(pessoa)
    return _pessoa_publica(pessoa)


def _pessoa_equipe_ou_404(session: Session, pessoa_id: int) -> Pessoa:
    fazenda_id = _fazenda_cowdata_id(session)
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa or pessoa.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Membro da equipe não encontrado")
    return pessoa


@router.put("/equipe/pessoas/{pessoa_id}")
def editar_membro_equipe(
    pessoa_id: int, dados: PessoaCowDataIn, _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)
) -> dict:
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    _validar_vinculo(dados)
    pessoa.nome = dados.nome
    pessoa.tipo = dados.cargo
    pessoa.telefones = json.dumps(dados.telefones) if dados.telefones else None
    pessoa.emails = json.dumps(dados.emails) if dados.emails else None
    pessoa.telefone = dados.telefones[0] if dados.telefones else None
    pessoa.email = dados.emails[0] if dados.emails else None
    pessoa.cpf_cnpj = dados.cpf_cnpj
    pessoa.cep = dados.cep
    pessoa.salario_base = dados.salario_base
    pessoa.data_admissao = dados.data_admissao
    pessoa.observacoes = dados.observacoes
    pessoa.ativo = dados.ativo
    pessoa.rg = dados.rg
    pessoa.genero = dados.genero
    pessoa.estado_civil = dados.estado_civil
    pessoa.endereco_rua = dados.endereco_rua
    pessoa.endereco_numero = dados.endereco_numero
    pessoa.endereco_bairro = dados.endereco_bairro
    pessoa.endereco_cidade = dados.endereco_cidade
    pessoa.endereco_uf = dados.endereco_uf
    pessoa.tipo_vinculo = dados.tipo_vinculo
    pessoa.subtipo_pj = dados.subtipo_pj if dados.tipo_vinculo == "pj" else None
    pessoa.pagamento_mensal = dados.pagamento_mensal
    session.add(pessoa)
    session.commit()
    session.refresh(pessoa)
    return _pessoa_publica(pessoa)


@router.get("/equipe/pessoas/{pessoa_id}/contrato")
def baixar_contrato_membro(
    pessoa_id: int,
    funcao: str | None = None, local_prestacao: str | None = None,
    jornada_semanal: int | None = None, experiencia_dias: int | None = None,
    objeto_servico: str | None = None, dia_pagamento: int | None = None, vigencia: str | None = None,
    representante_nome: str | None = None, representante_cpf: str | None = None,
    cidade_foro: str | None = None, estado_foro: str | None = None,
    _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session),
) -> Response:
    """Minuta do contrato do membro — CLT quando `tipo_vinculo="funcionario"`,
    prestação de serviços quando `"pj"`. O corpo vem do cadastro (nome, RG,
    CPF/CNPJ, endereço, estado civil, salário/pagamento, admissão, cargo); os
    parâmetros de query são sobrescritas pontuais para o que o cadastro não
    tem (função no contrato, local de prestação, jornada, objeto do serviço,
    foro), mesmo padrão de /fazendas/{id}/contrato/modelo. O que faltar sai
    como "[PREENCHER]" destacado — a minuta nunca deixa de ser gerada."""
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    empresa = session.exec(select(EmpresaOperadora)).first()
    try:
        html = render_contrato_equipe(
            pessoa, empresa,
            funcao=funcao, local_prestacao=local_prestacao,
            jornada_semanal=jornada_semanal, experiencia_dias=experiencia_dias,
            objeto_servico=objeto_servico, dia_pagamento=dia_pagamento, vigencia=vigencia,
            representante_nome=representante_nome, representante_cpf=representante_cpf,
            cidade_foro=cidade_foro, estado_foro=estado_foro,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=html, media_type="text/html",
        headers={"Content-Disposition": f'inline; filename="{nome_arquivo_contrato(pessoa)}"'},
    )


@router.delete("/equipe/pessoas/{pessoa_id}")
def excluir_membro_equipe(
    pessoa_id: int, _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)
) -> dict:
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    session.delete(pessoa)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Login + permissões de um membro da Equipe CowData no próprio Painel
# CowData — pedido explícito do usuário. Gated por `exigir_dono` (não pela
# área "equipe"): conceder/alterar um login e suas permissões é uma ação
# de mais confiança do que só editar nome/cargo/salário, então fica
# restrita ao proprietário mesmo — ver docstring de
# fazenda/models/equipe_cowdata_acesso.py.
# ---------------------------------------------------------------------------
class UsuarioEquipeCowDataIn(BaseModel):
    username: str
    email: str
    senha: Optional[str] = None  # obrigatório ao criar; opcional ao editar (None = mantém a senha atual)
    ativo: bool = True
    areas: list[str] = []
    pode_suspender_assinatura: bool = False
    pode_acessar_fazendas: bool = False
    pode_alterar_cadastro: bool = False
    pode_modificar_suspender_plano: bool = False
    pode_emitir_auditar_contratos: bool = False
    pode_emitir_cobrancas: bool = False
    pode_vincular_usuarios: bool = False
    pode_cadastrar_usuarios: bool = False


def _validar_areas(areas: list[str]) -> None:
    invalidas = [a for a in areas if a not in AREAS_PAINEL_COWDATA]
    if invalidas:
        raise HTTPException(status_code=400, detail=f"Área inválida: {', '.join(invalidas)}")


def _usuario_equipe_publico(usuario: Usuario, perm: PermissaoEquipeCowData) -> dict:
    return {
        "usuario_id": usuario.id, "username": usuario.username, "email": usuario.email, "ativo": usuario.ativo,
        "areas": [a for a in (perm.areas or "").split(",") if a],
        "pode_suspender_assinatura": perm.pode_suspender_assinatura,
        "pode_acessar_fazendas": perm.pode_acessar_fazendas,
        "pode_alterar_cadastro": perm.pode_alterar_cadastro,
        "pode_modificar_suspender_plano": perm.pode_modificar_suspender_plano,
        "pode_emitir_auditar_contratos": perm.pode_emitir_auditar_contratos,
        "pode_emitir_cobrancas": perm.pode_emitir_cobrancas,
        "pode_vincular_usuarios": perm.pode_vincular_usuarios,
        "pode_cadastrar_usuarios": perm.pode_cadastrar_usuarios,
    }


def _aplicar_subpermissoes(perm: PermissaoEquipeCowData, dados: UsuarioEquipeCowDataIn) -> None:
    perm.pode_suspender_assinatura = dados.pode_suspender_assinatura
    perm.pode_acessar_fazendas = dados.pode_acessar_fazendas
    # As 6 sub-permissões só fazem sentido com pode_acessar_fazendas=True —
    # reforçado aqui (não só no formulário) pra nunca gravar uma combinação
    # que o próprio desenho do usuário não previu.
    if dados.pode_acessar_fazendas:
        perm.pode_alterar_cadastro = dados.pode_alterar_cadastro
        perm.pode_modificar_suspender_plano = dados.pode_modificar_suspender_plano
        perm.pode_emitir_auditar_contratos = dados.pode_emitir_auditar_contratos
        perm.pode_emitir_cobrancas = dados.pode_emitir_cobrancas
        perm.pode_vincular_usuarios = dados.pode_vincular_usuarios
        perm.pode_cadastrar_usuarios = dados.pode_cadastrar_usuarios
    else:
        perm.pode_alterar_cadastro = False
        perm.pode_modificar_suspender_plano = False
        perm.pode_emitir_auditar_contratos = False
        perm.pode_emitir_cobrancas = False
        perm.pode_vincular_usuarios = False
        perm.pode_cadastrar_usuarios = False


@router.get("/equipe/pessoas/{pessoa_id}/usuario")
def obter_usuario_equipe(
    pessoa_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> Optional[dict]:
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    usuario = session.exec(select(Usuario).where(Usuario.pessoa_id == pessoa.id)).first()
    if not usuario:
        return None
    perm = _permissao_equipe_cowdata_ou_vazia(session, usuario.id)
    return _usuario_equipe_publico(usuario, perm)


def _permissao_equipe_cowdata_ou_vazia(session: Session, usuario_id: int) -> PermissaoEquipeCowData:
    perm = session.exec(select(PermissaoEquipeCowData).where(PermissaoEquipeCowData.usuario_id == usuario_id)).first()
    return perm or PermissaoEquipeCowData(usuario_id=usuario_id)


@router.post("/equipe/pessoas/{pessoa_id}/usuario")
def criar_usuario_equipe(
    pessoa_id: int, dados: UsuarioEquipeCowDataIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    if session.exec(select(Usuario).where(Usuario.pessoa_id == pessoa.id)).first():
        raise HTTPException(status_code=400, detail="Este membro já tem um usuário de login — edite as permissões em vez de criar outro.")
    if not dados.senha or not dados.senha.strip():
        raise HTTPException(status_code=400, detail="Senha é obrigatória para criar o usuário")
    if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
        raise HTTPException(status_code=400, detail="Nome de usuário já em uso")
    _validar_areas(dados.areas)

    usuario = Usuario(
        username=dados.username, nome=pessoa.nome, email=dados.email,
        senha_hash=hash_senha(dados.senha), papel="operador", pessoa_id=pessoa.id, ativo=dados.ativo,
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)

    perm = PermissaoEquipeCowData(usuario_id=usuario.id, areas=",".join(dados.areas))
    _aplicar_subpermissoes(perm, dados)
    session.add(perm)
    session.commit()
    session.refresh(perm)
    return _usuario_equipe_publico(usuario, perm)


@router.put("/equipe/pessoas/{pessoa_id}/usuario")
def editar_usuario_equipe(
    pessoa_id: int, dados: UsuarioEquipeCowDataIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    usuario = session.exec(select(Usuario).where(Usuario.pessoa_id == pessoa.id)).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Este membro ainda não tem usuário de login")
    outro = session.exec(select(Usuario).where(Usuario.username == dados.username, Usuario.id != usuario.id)).first()
    if outro:
        raise HTTPException(status_code=400, detail="Nome de usuário já em uso")
    _validar_areas(dados.areas)

    usuario.username = dados.username
    usuario.email = dados.email
    usuario.ativo = dados.ativo
    if dados.senha and dados.senha.strip():
        usuario.senha_hash = hash_senha(dados.senha)
    session.add(usuario)

    perm = _permissao_equipe_cowdata_ou_vazia(session, usuario.id)
    perm.areas = ",".join(dados.areas)
    _aplicar_subpermissoes(perm, dados)
    perm.atualizado_em = datetime.utcnow()
    session.add(perm)
    session.commit()
    session.refresh(usuario)
    session.refresh(perm)
    return _usuario_equipe_publico(usuario, perm)


# ---------------------------------------------------------------------------
# Folha de pagamento da Equipe CowData — mesmo formato de FolhaPagamento
# usado pela folha de pagamento de qualquer fazenda-cliente, sem recorrência
# automática nem geração de Contas a Pagar (não existe "Contas a Pagar" aqui
# — ver LancamentoCowData/livro-caixa abaixo, onde a folha paga entra como
# despesa "Folha").
# ---------------------------------------------------------------------------
class FolhaCowDataIn(BaseModel):
    competencia: str  # "AAAA-MM"
    valor_bruto: float
    descontos: float = 0.0
    valor_liquido: float
    status: str = "pendente"  # pendente | pago
    data_pagamento: Optional[date] = None
    observacao: Optional[str] = None


def _folha_publica(f: FolhaPagamento) -> dict:
    return {
        "id": f.id,
        "pessoa_id": f.pessoa_id,
        "competencia": f.competencia,
        "valor_bruto": f.valor_bruto,
        "descontos": f.descontos,
        "valor_liquido": f.valor_liquido,
        "status": f.status,
        "data_pagamento": f.data_pagamento,
        "observacao": f.observacao,
    }


@router.get("/equipe/pessoas/{pessoa_id}/folha")
def listar_folha_membro(
    pessoa_id: int, _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)
) -> list[dict]:
    _pessoa_equipe_ou_404(session, pessoa_id)
    lancamentos = session.exec(select(FolhaPagamento).where(FolhaPagamento.pessoa_id == pessoa_id)).all()
    return [_folha_publica(f) for f in sorted(lancamentos, key=lambda f: f.competencia, reverse=True)]


@router.post("/equipe/pessoas/{pessoa_id}/folha")
def lancar_folha_membro(
    pessoa_id: int, dados: FolhaCowDataIn, _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)
) -> dict:
    fazenda_id = _fazenda_cowdata_id(session)
    _pessoa_equipe_ou_404(session, pessoa_id)
    folha = FolhaPagamento(
        fazenda_id=fazenda_id,
        pessoa_id=pessoa_id,
        competencia=dados.competencia,
        valor_bruto=dados.valor_bruto,
        descontos=dados.descontos,
        valor_liquido=dados.valor_liquido,
        status=dados.status,
        data_pagamento=dados.data_pagamento,
        observacao=dados.observacao,
    )
    session.add(folha)
    session.commit()
    session.refresh(folha)
    return _folha_publica(folha)


def _folha_equipe_ou_404(session: Session, folha_id: int) -> FolhaPagamento:
    fazenda_id = _fazenda_cowdata_id(session)
    folha = session.get(FolhaPagamento, folha_id)
    if not folha or folha.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Lançamento de folha não encontrado")
    return folha


@router.put("/equipe/folha/{folha_id}")
def editar_folha_membro(
    folha_id: int, dados: FolhaCowDataIn, _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)
) -> dict:
    folha = _folha_equipe_ou_404(session, folha_id)
    folha.competencia = dados.competencia
    folha.valor_bruto = dados.valor_bruto
    folha.descontos = dados.descontos
    folha.valor_liquido = dados.valor_liquido
    folha.status = dados.status
    folha.data_pagamento = dados.data_pagamento
    folha.observacao = dados.observacao
    session.add(folha)
    session.commit()
    session.refresh(folha)
    return _folha_publica(folha)


@router.delete("/equipe/folha/{folha_id}")
def excluir_folha_membro(folha_id: int, _: Usuario = Depends(exigir_area_painel_cowdata("equipe")), session: Session = Depends(get_session)) -> dict:
    folha = _folha_equipe_ou_404(session, folha_id)
    session.delete(folha)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Financeiro CowData — livro-caixa independente (receita/despesa manual +
# receita de assinatura real das fazendas-clientes + folha paga da equipe).
# ---------------------------------------------------------------------------
CATEGORIAS_RECEITA = ["assinatura_avulsa", "servico_avulso", "outra_receita"]
CATEGORIAS_DESPESA = ["folha_equipe", "servidor_infra", "ferramentas_software", "marketing", "juridico_contabil", "outra_despesa"]


class LancamentoCowDataIn(BaseModel):
    tipo: str  # receita | despesa
    categoria: str
    descricao: str
    contraparte: Optional[str] = None
    valor: float
    data: date


def _lancamento_publico(l: LancamentoCowData) -> dict:  # noqa: E741
    return {
        "id": l.id,
        "tipo": l.tipo,
        "categoria": l.categoria,
        "descricao": l.descricao,
        "contraparte": l.contraparte,
        "valor": l.valor,
        "data": l.data,
        "origem": "manual",
    }


@router.get("/financeiro/categorias")
def listar_categorias(_: Usuario = Depends(exigir_area_painel_cowdata("financeiro"))) -> dict:
    return {"receita": CATEGORIAS_RECEITA, "despesa": CATEGORIAS_DESPESA}


@router.get("/financeiro/lancamentos")
def listar_lancamentos(
    de: Optional[date] = None,
    ate: Optional[date] = None,
    _: Usuario = Depends(exigir_area_painel_cowdata("financeiro")),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(LancamentoCowData)
    if de:
        query = query.where(LancamentoCowData.data >= de)
    if ate:
        query = query.where(LancamentoCowData.data <= ate)
    lancamentos = session.exec(query).all()
    return [_lancamento_publico(l) for l in sorted(lancamentos, key=lambda l: l.data, reverse=True)]


@router.post("/financeiro/lancamentos")
def criar_lancamento(
    dados: LancamentoCowDataIn, user: Usuario = Depends(exigir_area_painel_cowdata("financeiro")), session: Session = Depends(get_session)
) -> dict:
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="Tipo deve ser receita ou despesa")
    lancamento = LancamentoCowData(
        tipo=dados.tipo,
        categoria=dados.categoria,
        descricao=dados.descricao,
        contraparte=dados.contraparte,
        valor=dados.valor,
        data=dados.data,
        usuario_id=user.id,
    )
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)
    return _lancamento_publico(lancamento)


@router.put("/financeiro/lancamentos/{lancamento_id}")
def editar_lancamento(
    lancamento_id: int, dados: LancamentoCowDataIn, _: Usuario = Depends(exigir_area_painel_cowdata("financeiro")), session: Session = Depends(get_session)
) -> dict:
    lancamento = session.get(LancamentoCowData, lancamento_id)
    if not lancamento:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    lancamento.tipo = dados.tipo
    lancamento.categoria = dados.categoria
    lancamento.descricao = dados.descricao
    lancamento.contraparte = dados.contraparte
    lancamento.valor = dados.valor
    lancamento.data = dados.data
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)
    return _lancamento_publico(lancamento)


@router.delete("/financeiro/lancamentos/{lancamento_id}")
def excluir_lancamento(lancamento_id: int, _: Usuario = Depends(exigir_area_painel_cowdata("financeiro")), session: Session = Depends(get_session)) -> dict:
    lancamento = session.get(LancamentoCowData, lancamento_id)
    if not lancamento:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    session.delete(lancamento)
    session.commit()
    return {"ok": True}


def _movimentos_periodo(session: Session, de: date, ate: date) -> list[dict]:
    """Livro-caixa consolidado do período: lançamentos manuais (receita/
    despesa) + folha da equipe CowData paga no período (despesa) + assinaturas
    de fazendas-clientes pagas no período (receita real, via Asaas) — nunca
    duplica: a folha e a assinatura não passam por LancamentoCowData."""
    movimentos: list[dict] = []

    for l in session.exec(  # noqa: E741
        select(LancamentoCowData).where(LancamentoCowData.data >= de, LancamentoCowData.data <= ate)
    ).all():
        movimentos.append({
            "data": l.data, "tipo": l.tipo, "categoria": l.categoria, "descricao": l.descricao, "valor": l.valor,
        })

    fazenda_id_cowdata = _fazenda_cowdata_id(session)
    for cobranca in session.exec(
        select(CobrancaAsaas).where(
            CobrancaAsaas.status == "paga",
            CobrancaAsaas.pago_em >= de,
            CobrancaAsaas.pago_em <= ate,
            CobrancaAsaas.fazenda_id != fazenda_id_cowdata,
        )
    ).all():
        fazenda = session.get(Fazenda, cobranca.fazenda_id)
        movimentos.append({
            "data": cobranca.pago_em.date(), "tipo": "receita", "categoria": "assinatura",
            "descricao": f"Assinatura — {fazenda.nome if fazenda else cobranca.fazenda_id}", "valor": cobranca.valor,
        })

    for folha in session.exec(
        select(FolhaPagamento).where(
            FolhaPagamento.fazenda_id == fazenda_id_cowdata,
            FolhaPagamento.status == "pago",
            FolhaPagamento.data_pagamento >= de,
            FolhaPagamento.data_pagamento <= ate,
        )
    ).all():
        pessoa = session.get(Pessoa, folha.pessoa_id)
        movimentos.append({
            "data": folha.data_pagamento, "tipo": "despesa", "categoria": "folha_equipe",
            "descricao": f"Folha — {pessoa.nome if pessoa else folha.pessoa_id} ({folha.competencia})",
            "valor": folha.valor_liquido,
        })

    return sorted(movimentos, key=lambda m: m["data"])


@router.get("/financeiro/resumo")
def resumo_financeiro(
    de: date, ate: date, _: Usuario = Depends(exigir_area_painel_cowdata("financeiro")), session: Session = Depends(get_session)
) -> dict:
    movimentos = _movimentos_periodo(session, de, ate)
    receita = sum(m["valor"] for m in movimentos if m["tipo"] == "receita")
    despesa = sum(m["valor"] for m in movimentos if m["tipo"] == "despesa")
    return {"receita": round(receita, 2), "despesa": round(despesa, 2), "resultado": round(receita - despesa, 2)}


@router.get("/financeiro/livro-caixa")
def livro_caixa(
    de: date, ate: date, _: Usuario = Depends(exigir_area_painel_cowdata("financeiro")), session: Session = Depends(get_session)
) -> list[dict]:
    movimentos = _movimentos_periodo(session, de, ate)
    saldo = 0.0
    linhas = []
    for m in movimentos:
        saldo += m["valor"] if m["tipo"] == "receita" else -m["valor"]
        linhas.append({**m, "saldo_acumulado": round(saldo, 2)})
    return linhas


@router.get("/financeiro/fluxo-caixa")
def fluxo_caixa(
    de: date, ate: date, _: Usuario = Depends(exigir_area_painel_cowdata("financeiro")), session: Session = Depends(get_session)
) -> list[dict]:
    """Agrupado por mês (entradas/saídas/saldo do mês/saldo acumulado) —
    distinto do livro-caixa (lançamento a lançamento)."""
    movimentos = _movimentos_periodo(session, de, ate)
    por_mes: dict[str, dict] = {}
    for m in movimentos:
        chave = f"{m['data'].year:04d}-{m['data'].month:02d}"
        bucket = por_mes.setdefault(chave, {"competencia": chave, "entradas": 0.0, "saidas": 0.0})
        if m["tipo"] == "receita":
            bucket["entradas"] += m["valor"]
        else:
            bucket["saidas"] += m["valor"]
    saldo_acumulado = 0.0
    linhas = []
    for chave in sorted(por_mes.keys()):
        bucket = por_mes[chave]
        saldo_mes = bucket["entradas"] - bucket["saidas"]
        saldo_acumulado += saldo_mes
        linhas.append({
            "competencia": chave, "entradas": round(bucket["entradas"], 2), "saidas": round(bucket["saidas"], 2),
            "saldo_mes": round(saldo_mes, 2), "saldo_acumulado": round(saldo_acumulado, 2),
        })
    return linhas


@router.get("/financeiro/dre")
def dre(ano: int, _: Usuario = Depends(exigir_area_painel_cowdata("financeiro")), session: Session = Depends(get_session)) -> dict:
    """DRE simplificado do ano: receita total, despesas por categoria e
    resultado — mesma base de dados do livro-caixa/fluxo-caixa, só reagrupada."""
    de, ate = date(ano, 1, 1), date(ano, 12, 31)
    movimentos = _movimentos_periodo(session, de, ate)
    receita_total = sum(m["valor"] for m in movimentos if m["tipo"] == "receita")
    despesas_por_categoria: dict[str, float] = {}
    for m in movimentos:
        if m["tipo"] == "despesa":
            despesas_por_categoria[m["categoria"]] = despesas_por_categoria.get(m["categoria"], 0.0) + m["valor"]
    despesa_total = sum(despesas_por_categoria.values())
    return {
        "ano": ano,
        "receita_total": round(receita_total, 2),
        "despesas_por_categoria": {k: round(v, 2) for k, v in despesas_por_categoria.items()},
        "despesa_total": round(despesa_total, 2),
        "resultado": round(receita_total - despesa_total, 2),
    }
