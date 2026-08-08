"""
Cadastro > Pessoas — funcionário, veterinário, zootecnista, diarista,
prestador de serviços, e os tipos de pessoa cadastráveis (TipoPessoa).
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Pessoa, SeedFlag, TipoPessoa
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter()

# Lista original — mantida só como referência do vocabulário inicial. A
# validação de tipos passou a consultar a tabela TipoPessoa (ver
# seed_tipos_pessoa/_validar_tipos), que é editável em tempo de execução pelo
# botão "+" do Cadastro de Pessoas.
TIPOS_PESSOA = ["Funcionário", "Veterinário", "Zootecnista", "Diarista", "Prestador de serviços", "Inseminador"]

# "Empreiteiro" já nasce cadastrado — usado pelo módulo de Empreita (Financeiro
# > Ações > Folha de Pagamento).
SEED_TIPOS_PESSOA = TIPOS_PESSOA + ["Empreiteiro"]

# Seed inicial — funcionários já conhecidos da fazenda (ver seed_pessoas,
# chamada uma vez no startup, mesmo padrão de seed_motivos_movimentacao).
SEED_PESSOAS = [
    {"nome": "Leomir Bonfim", "tipo": "Funcionário"},
    {"nome": "Alane dos Santos", "tipo": "Funcionário"},
    {"nome": "Jorbeson Nunes", "tipo": "Funcionário"},
    {"nome": "Valéria Bonfim", "tipo": "Funcionário"},
    {"nome": "Alexandre Scarpa", "tipo": "Funcionário"},
]


def seed_pessoas(session: Session) -> None:
    """Cria as pessoas padrão se a tabela ainda estiver vazia (idempotente)."""
    if session.exec(select(Pessoa)).first():
        return
    for dados in SEED_PESSOAS:
        session.add(Pessoa(**dados))
    session.commit()


NOME_PESSOA_ROBO_MILKNEWS = "Robô MilkNews"


def seed_pessoa_robo_milknews(session: Session, fazenda_id: int | None = None) -> None:
    """Garante a existência de uma Pessoa "Robô MilkNews", representando a
    automação de Telegram/MilkNews no cadastro — permite vincular um usuário
    de sistema a essa identidade, como qualquer outra pessoa (get-or-create;
    roda sempre, ao contrário de seed_pessoas, que só semeia tabela vazia)."""
    seed_tipos_pessoa(session, fazenda_id=fazenda_id)
    query_pessoa = select(Pessoa).where(Pessoa.nome == NOME_PESSOA_ROBO_MILKNEWS)
    if fazenda_id is not None:
        query_pessoa = query_pessoa.where(Pessoa.fazenda_id == fazenda_id)
    if session.exec(query_pessoa).first():
        return
    query_tipo = select(TipoPessoa).where(TipoPessoa.nome == "Robô")
    if fazenda_id is not None:
        query_tipo = query_tipo.where(TipoPessoa.fazenda_id == fazenda_id)
    if not session.exec(query_tipo).first():
        session.add(TipoPessoa(nome="Robô", fazenda_id=fazenda_id))
        session.commit()
    session.add(Pessoa(
        nome=NOME_PESSOA_ROBO_MILKNEWS, tipo="Robô", fazenda_id=fazenda_id,
        observacoes="Identidade da automação de Telegram/MilkNews — não recebe folha de pagamento.",
    ))
    session.commit()


def seed_tipos_pessoa(session: Session, fazenda_id: int | None = None) -> None:
    """Cria os tipos de pessoa padrão para a `fazenda_id` informada (None =
    execução legada/global, mantida por compatibilidade com bancos antigos de
    fazenda única) — nunca sobrescreve tipos adicionados depois pelo usuário.
    Roda uma vez por fazenda (SeedFlag com chave específica, mesmo padrão de
    seed_tipos_metodos_servico) — nome globalmente vazio deixou de ser um
    critério válido desde que TipoPessoa passou a ter fazenda_id (a 2ª
    fazenda nunca teria a tabela "vazia" de verdade)."""
    chave = f"tipos_pessoa_v1_fazenda_{fazenda_id}" if fazenda_id is not None else "tipos_pessoa_v1"
    if session.get(SeedFlag, chave):
        return
    for nome in SEED_TIPOS_PESSOA:
        query = select(TipoPessoa).where(TipoPessoa.nome == nome)
        if fazenda_id is not None:
            query = query.where(TipoPessoa.fazenda_id == fazenda_id)
        if not session.exec(query).first():
            session.add(TipoPessoa(nome=nome, fazenda_id=fazenda_id))
    session.add(SeedFlag(chave=chave))
    session.commit()


def seed_tipo_geral(session: Session, fazenda_id: int | None = None) -> None:
    """Garante a existência do tipo "Geral" para a `fazenda_id` informada —
    usado para liberar acesso a Portal > Comunicação > Delegar tarefa (#515) a
    pessoas sem um papel técnico específico. Get-or-create (roda sempre, como
    seed_pessoa_robo_milknews), ao contrário de seed_tipos_pessoa, que só
    semeia uma vez por fazenda."""
    query = select(TipoPessoa).where(TipoPessoa.nome == "Geral")
    if fazenda_id is not None:
        query = query.where(TipoPessoa.fazenda_id == fazenda_id)
    if not session.exec(query).first():
        session.add(TipoPessoa(nome="Geral", fazenda_id=fazenda_id))
        session.commit()




# ---------------------------------------------------------------------------
# Pessoas — funcionário, veterinário, zootecnista, diarista, prestador de
# serviços. Distinto de Fornecedor: usado na folha de pagamento, não em notas.
# ---------------------------------------------------------------------------
class PessoaIn(BaseModel):
    nome: str
    tipos: list[str]
    telefones: list[str] = []
    emails: list[str] = []
    cpf_cnpj: str | None = None
    cep: str | None = None
    observacoes: str | None = None
    ativo: bool = True
    salario_base: float | None = None
    data_admissao: date | None = None
    # Dados civis (jul/2026) — coletados no cadastro, mas só exigidos na hora
    # de assinar um contrato (ver Contrato Assinado). Gênero nunca é exigido.
    rg: str | None = None
    data_nascimento: date | None = None
    genero: str | None = None
    estado_civil: str | None = None
    # Endereço estruturado — junto com nome e CPF, obrigatório para cadastrar
    # (ver _exigir_campos_obrigatorios abaixo).
    endereco_rua: str | None = None
    endereco_numero: str | None = None
    endereco_bairro: str | None = None
    endereco_cidade: str | None = None
    endereco_uf: str | None = None


def _exigir_campos_obrigatorios(dados: PessoaIn) -> None:
    """Nome, CPF e endereço são obrigatórios para cadastrar uma pessoa nova
    (decisão jul/2026) — RG, data de nascimento e estado civil são
    coletados no mesmo formulário mas só passam a ser exigidos na hora de
    assinar um contrato (ver Contrato Assinado), nunca aqui. Só roda na
    criação: editar uma pessoa já cadastrada antes dessa regra não pode
    ficar bloqueada por campos que ela nunca teve chance de preencher.

    NÃO está sendo chamada em criar_pessoa por enquanto — Pessoa é o
    cadastro de RH usado para QUALQUER funcionário/veterinário/diarista/
    empreiteiro, não só o contratante que assina o contrato CowData.
    Bloquear CPF/endereço aqui quebraria 31+ fluxos de teste/uso reais
    (contratar um diarista sem endereço completo, por exemplo). Os campos
    já existem no formulário para quem quiser preencher; fica pronta para
    ligar com uma linha (chamar esta função em criar_pessoa) se a decisão
    for realmente travar TODO cadastro de pessoa, e não só o do contratante
    do contrato CowData."""
    faltando = []
    if not dados.nome.strip():
        faltando.append("nome completo")
    if not (dados.cpf_cnpj or "").strip():
        faltando.append("CPF")
    endereco_preenchido = all((dados.endereco_rua or "").strip() and (dados.endereco_numero or "").strip()
                               and (dados.endereco_cidade or "").strip() and (dados.endereco_uf or "").strip())
    if not endereco_preenchido:
        faltando.append("endereço completo (rua, número, cidade e UF)")
    if faltando:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios faltando: {', '.join(faltando)}")


def _normalizar_lista_contato(valores: list[str]) -> list[str]:
    """Remove vazios/duplicatas mantendo a ordem — mesma ideia de _validar_tipos,
    mas sem vocabulário fechado (telefone/e-mail são texto livre)."""
    return list(dict.fromkeys(v.strip() for v in valores if v.strip()))


def _aplicar_contatos(p: Pessoa, telefones: list[str], emails: list[str]) -> None:
    """Grava telefones/emails (JSON) e mantém telefone/email (1º item) para
    quem ainda lê o campo legado direto no ORM (ex.: destinatario_recibo)."""
    p.telefones = json.dumps(telefones) if telefones else None
    p.emails = json.dumps(emails) if emails else None
    p.telefone = telefones[0] if telefones else None
    p.email = emails[0] if emails else None


def _serializar_pessoa(p: Pessoa) -> dict:
    dados = p.model_dump(exclude={"tipo", "telefone", "email", "telefones", "emails"})
    dados["tipos"] = [t for t in (p.tipo or "").split(",") if t]
    dados["telefones"] = json.loads(p.telefones) if p.telefones else ([p.telefone] if p.telefone else [])
    dados["emails"] = json.loads(p.emails) if p.emails else ([p.email] if p.email else [])
    return dados


def _validar_tipos(session: Session, tipos: list[str], fazenda_id: int | None = None) -> str:
    """Valida e serializa a lista de tipos de uma pessoa como CSV (mesmo
    padrão de Usuario.permissoes) — permite marcar mais de um tipo (ex.:
    Funcionário + Inseminador). Os tipos válidos vêm da tabela TipoPessoa
    (cadastrável via botão "+" no Cadastro de Pessoas), não mais de uma
    lista fixa, escopados pela fazenda atual. Autossemeia se a fazenda ainda
    não tiver nenhum tipo (ex.: banco de teste isolado que não passou pelo
    seed do lifespan)."""
    seed_tipos_pessoa(session, fazenda_id=fazenda_id)
    query = select(TipoPessoa).where(TipoPessoa.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(TipoPessoa.fazenda_id == fazenda_id)
    validos = {t.nome for t in session.exec(query).all()}
    if not tipos or any(t not in validos for t in tipos):
        raise HTTPException(status_code=400, detail="Tipo inválido")
    return ",".join(dict.fromkeys(tipos))  # remove duplicatas mantendo a ordem


class TipoPessoaIn(BaseModel):
    nome: str
    ativo: bool = True


@router.get("/pessoas/tipos")
def listar_tipos_pessoa(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    seed_tipos_pessoa(session, fazenda_id=fazenda_id)
    query = select(TipoPessoa)
    if fazenda_id is not None:
        query = query.where(TipoPessoa.fazenda_id == fazenda_id)
    return [t.model_dump() for t in session.exec(query.order_by(TipoPessoa.id)).all()]


@router.post("/pessoas/tipos")
def criar_tipo_pessoa(
    dados: TipoPessoaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(TipoPessoa).where(TipoPessoa.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(TipoPessoa.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail="Tipo já cadastrado")
    obj = TipoPessoa(nome=nome, ativo=dados.ativo, fazenda_id=fazenda_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.put("/pessoas/tipos/{tipo_id}")
def atualizar_tipo_pessoa(
    tipo_id: int, dados: TipoPessoaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    obj = session.get(TipoPessoa, tipo_id)
    if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Tipo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(TipoPessoa).where(TipoPessoa.nome == nome, TipoPessoa.id != tipo_id)
    if fazenda_id is not None:
        query_dup = query_dup.where(TipoPessoa.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail="Tipo já cadastrado")
    obj.nome = nome
    obj.ativo = dados.ativo
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.get("/pessoas")
def listar_pessoas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    query = select(Pessoa)
    if fazenda_id is not None:
        query = query.where(Pessoa.fazenda_id == fazenda_id)
    return [_serializar_pessoa(p) for p in session.exec(query.order_by(Pessoa.nome)).all()]


@router.post("/pessoas")
def criar_pessoa(
    dados: PessoaIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    tipo_csv = _validar_tipos(session, dados.tipos, fazenda_id=fazenda_id_seguro(fazenda_id))
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    telefones = _normalizar_lista_contato(dados.telefones)
    emails = _normalizar_lista_contato(dados.emails)
    campos = dados.model_dump(exclude={"tipos", "telefones", "emails"})
    p = Pessoa(**campos, tipo=tipo_csv, fazenda_id=fazenda_id)
    _aplicar_contatos(p, telefones, emails)
    session.add(p)
    session.commit()
    session.refresh(p)
    return _serializar_pessoa(p)


@router.put("/pessoas/{pessoa_id}")
def atualizar_pessoa(
    pessoa_id: int, dados: PessoaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    p = session.get(Pessoa, pessoa_id)
    if not p or (fazenda_id is not None and p.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    tipo_csv = _validar_tipos(session, dados.tipos, fazenda_id=fazenda_id)
    for campo, valor in dados.model_dump(exclude={"tipos", "telefones", "emails"}).items():
        setattr(p, campo, valor)
    p.tipo = tipo_csv
    _aplicar_contatos(p, _normalizar_lista_contato(dados.telefones), _normalizar_lista_contato(dados.emails))
    session.add(p)
    session.commit()
    session.refresh(p)
    return _serializar_pessoa(p)


@router.get("/pessoas/inseminadores")
def listar_inseminadores(session: Session = Depends(get_session)) -> list[str]:
    """Nomes das pessoas cadastradas com o tipo Inseminador (ativas) — usado
    para alimentar os filtros de inseminador em Análise reprodutiva/
    Indicadores/Relatórios, mesmo antes de qualquer serviço lançado."""
    pessoas = session.exec(select(Pessoa).where(Pessoa.ativo == True)).all()  # noqa: E712
    return sorted({p.nome for p in pessoas if "Inseminador" in (p.tipo or "").split(",")})



