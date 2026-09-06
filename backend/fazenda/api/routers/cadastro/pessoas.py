"""
Cadastro > Pessoas — funcionário, veterinário, zootecnista, diarista,
prestador de serviços, e os tipos de pessoa cadastráveis (TipoPessoa).
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import (
    CATEGORIAS_PESSOA_ANEXO,
    Contrato,
    CronogramaSanitario,
    DecimoTerceiro,
    Diaria,
    Empreitada,
    FeriasFuncionario,
    FolhaPagamento,
    Pessoa,
    PessoaAnexo,
    RescisaoFuncionario,
    SeedFlag,
    TipoPessoa,
    Usuario,
    ValeAvulso,
    ValeFuncionario,
    ValeParcela,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage

logger = logging.getLogger(__name__)

router = APIRouter()

# Lista original — mantida só como referência do vocabulário inicial. A
# validação de tipos passou a consultar a tabela TipoPessoa (ver
# seed_tipos_pessoa/_validar_tipos), que é editável em tempo de execução pelo
# botão "+" do Cadastro de Pessoas.
TIPOS_PESSOA = [
    "Funcionário", "Veterinário", "Zootecnista", "Diarista", "Prestador de serviços", "Inseminador",
    # Administrador/Contador (ago/2026): não são cargo de RH no sentido usual,
    # mas entram no mesmo vocabulário de TipoPessoa para poder marcar quem
    # exerce esse papel na fazenda — usePessoasAtivas (frontend) usa isso para
    # decidir quem aparece nas listas de "Responsável" de um lançamento
    # (só entra quem tiver ao menos um papel funcional: Funcionário,
    # Veterinário, Zootecnista, Administrador ou Contador).
    "Administrador", "Contador",
]

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
    seed_tipos_papel_administrativo(session, fazenda_id=fazenda_id)
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


def _seed_tipos_get_or_create(session: Session, nomes: list[str], fazenda_id: int | None = None) -> None:
    """Get-or-create para uma lista de nomes de TipoPessoa — roda SEMPRE,
    nunca gated por SeedFlag (ao contrário de seed_tipos_pessoa). Base comum
    de seed_tipo_geral e seed_tipos_papel_administrativo: qualquer tipo que
    precise existir em toda fazenda, inclusive nas que já passaram pelo seed
    original antes desse tipo ser criado, usa este helper em vez de entrar
    em SEED_TIPOS_PESSOA (que só é aplicada uma vez por fazenda)."""
    algum_criado = False
    for nome in nomes:
        query = select(TipoPessoa).where(TipoPessoa.nome == nome)
        if fazenda_id is not None:
            query = query.where(TipoPessoa.fazenda_id == fazenda_id)
        if not session.exec(query).first():
            session.add(TipoPessoa(nome=nome, fazenda_id=fazenda_id))
            algum_criado = True
    if algum_criado:
        session.commit()


def seed_tipo_geral(session: Session, fazenda_id: int | None = None) -> None:
    """Garante a existência do tipo "Geral" para a `fazenda_id` informada —
    usado para liberar acesso a Portal > Comunicação > Delegar tarefa (#515) a
    pessoas sem um papel técnico específico. Get-or-create (roda sempre, como
    seed_pessoa_robo_milknews), ao contrário de seed_tipos_pessoa, que só
    semeia uma vez por fazenda."""
    _seed_tipos_get_or_create(session, ["Geral"], fazenda_id=fazenda_id)


# Administrador/Contador entraram em TIPOS_PESSOA em ago/2026 (ver comentário
# acima) — mas seed_tipos_pessoa só semeia os tipos padrão de uma fazenda UMA
# VEZ (SeedFlag). Toda fazenda cujo seed já tinha rodado antes dessa data
# nunca ganhou essas duas linhas em TipoPessoa e passou a receber "Tipo
# inválido" ao tentar marcar alguém como Administrador/Contador — mesmo
# problema que seed_tipo_geral já resolve para "Geral" (#515).
TIPOS_PAPEL_ADMINISTRATIVO_BACKFILL = ["Administrador", "Contador"]


def seed_tipos_papel_administrativo(session: Session, fazenda_id: int | None = None) -> None:
    """Garante a existência de "Administrador"/"Contador" para a `fazenda_id`
    informada — get-or-create, roda SEMPRE (mesmo padrão de seed_tipo_geral),
    ao contrário de seed_tipos_pessoa. Backfill transparente para fazendas
    antigas que nunca receberam esses dois tipos (ver comentário acima de
    TIPOS_PAPEL_ADMINISTRATIVO_BACKFILL) — sem precisar de migração de dados
    nem script manual: a primeira chamada a qualquer rota que já semeava tipo
    de pessoa (_validar_tipos, listar_tipos_pessoa, provisionamento de
    fazenda nova) resolve sozinha."""
    _seed_tipos_get_or_create(session, TIPOS_PAPEL_ADMINISTRATIVO_BACKFILL, fazenda_id=fazenda_id)


def backfill_tipos_orfaos(session: Session, fazenda_id: int | None = None) -> None:
    """Get-or-create de qualquer valor de `Pessoa.tipo` (CSV) que já existe
    em produção para esta fazenda mas nunca virou uma linha `TipoPessoa`
    correspondente — dado legado de antes da validação estrita (import, SQL
    manual, ou um tipo que existia e foi removido/renomeado depois de já
    gravado em alguém). Caso real: "Sócio" gravado em Pessoa.tipo sem NUNCA
    ter sido um TipoPessoa desta fazenda — qualquer tentativa de salvar essa
    pessoa de novo (mesmo editando um campo sem relação nenhuma com tipo)
    falhava com "Tipo inválido", porque o formulário reenvia os tipos atuais
    dela junto, e um deles já não validava mais. Diferente do backfill de
    Administrador/Contador acima (que cria um tipo NOVO que ninguém ainda
    usa, para o checkbox existir) — este cura o inverso: um tipo que já está
    em uso mas nunca foi cadastrado como válido."""
    query = select(Pessoa)
    if fazenda_id is not None:
        query = query.where(Pessoa.fazenda_id == fazenda_id)
    nomes_em_uso = {
        nome.strip()
        for p in session.exec(query).all()
        for nome in (p.tipo or "").split(",")
        if nome.strip()
    }
    if nomes_em_uso:
        _seed_tipos_get_or_create(session, sorted(nomes_em_uso), fazenda_id=fazenda_id)




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
    seed do lifespan). Também backfilla Administrador/Contador (ver
    seed_tipos_papel_administrativo) — sem isso, uma fazenda cujo
    seed_tipos_pessoa já rodou antes de ago/2026 (SeedFlag já marcada) nunca
    ganharia esses dois tipos e ficaria travada em "Tipo inválido" para
    sempre, mesmo autossemeando. E cura tipos órfãos já em uso (ver
    backfill_tipos_orfaos) — ex.: "Sócio", gravado em produção sem nunca ter
    sido um TipoPessoa válido, travava até reeditar a própria pessoa que já
    tinha esse tipo."""
    seed_tipos_pessoa(session, fazenda_id=fazenda_id)
    seed_tipos_papel_administrativo(session, fazenda_id=fazenda_id)
    backfill_tipos_orfaos(session, fazenda_id=fazenda_id)
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
    seed_tipos_papel_administrativo(session, fazenda_id=fazenda_id)
    backfill_tipos_orfaos(session, fazenda_id=fazenda_id)
    query = select(TipoPessoa)
    if fazenda_id is not None:
        query = query.where(TipoPessoa.fazenda_id == fazenda_id)
    return [t.model_dump() for t in session.exec(query.order_by(TipoPessoa.id)).all()]


@router.post("/pessoas/tipos")
def criar_tipo_pessoa(
    dados: TipoPessoaIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
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
    if not obj or (obj.fazenda_id != fazenda_id):
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
    dados: PessoaIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    tipo_csv = _validar_tipos(session, dados.tipos, fazenda_id=fazenda_id)
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
    if not p or (p.fazenda_id != fazenda_id):
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


# Toda tabela com FK real para pessoa.id (ver grep de "pessoa_id" em
# fazenda/models/) — bloqueia a exclusão de fato se qualquer uma tiver
# registro vinculado, mesma lógica de excluir_item_estoque (estoque.py).
# Usuario.pessoa_id e CronogramaSanitario.veterinario_pessoa_id também são
# FK para pessoa.id, então entram na mesma varredura (o 2º é checado à
# parte abaixo por ter nome de coluna diferente de "pessoa_id").
#
# Cada linha é (modelo, singular, plural, status_que_NÃO_bloqueiam).
#
# 1. SINGULAR/PLURAL EXPLÍCITOS — antes a mensagem montava o plural sozinha
#    grudando um "s" no rótulo, e com isso o motivo da recusa chegava na tela
#    como "2 fériass" / "3 folha de pagamentos". A mensagem é a única coisa
#    que o usuário tem para decidir entre desativar a pessoa ou desfazer o
#    vínculo — ela precisa estar legível.
#
# 2. STATUS QUE NÃO BLOQUEIAM — férias e 13º NUNCA são apagados quando uma
#    rescisão os absorve: o servidor só carimba status="cancelado_rescisao"
#    (ver FeriasFuncionario.status/rescisao_id em models/pessoal.py), de
#    propósito, para o cancelamento ser rastreável e reversível. A varredura
#    aqui contava esses registros como vínculo vivo, então bastava a pessoa
#    ter tido férias ou 13º cancelados por uma rescisão para ela virar
#    não-excluível para sempre — por causa de um lançamento que já não vale
#    mais nada. Registro cancelado não é vínculo.
_TABELAS_COM_PESSOA_ID = [
    (Usuario, "login de usuário", "logins de usuário", ()),
    (FolhaPagamento, "folha de pagamento", "folhas de pagamento", ()),
    (FeriasFuncionario, "férias", "períodos de férias", ("cancelado_rescisao",)),
    (DecimoTerceiro, "lançamento de 13º salário", "lançamentos de 13º salário", ("cancelado_rescisao",)),
    (RescisaoFuncionario, "rescisão", "rescisões", ()),
    (ValeFuncionario, "vale", "vales", ()),
    (ValeAvulso, "vale avulso", "vales avulsos", ()),
    (Empreitada, "empreitada", "empreitadas", ()),
    (Contrato, "contrato", "contratos", ()),
    (Diaria, "diária", "diárias", ()),
    # ValeParcela.pessoa_id é FK para pessoa.id e tinha ficado de fora desta
    # lista. No SQLite da suíte isso passa batido (FK não é verificada por
    # padrão), mas no Postgres de produção o `session.delete(p)` estoura
    # ForeignKeyViolation e a tela recebe um 500 com texto de banco — o
    # oposto de "diga ao usuário o que está vinculado". Na prática a parcela
    # sempre vem junto do ValeFuncionario (que já bloqueia acima), então isto
    # só aparece sozinho no caso órfão — e é justamente esse que dava 500.
    (ValeParcela, "parcela de vale", "parcelas de vale", ()),
]


@router.delete("/pessoas/{pessoa_id}")
def excluir_pessoa(
    pessoa_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Exclui uma pessoa de fato — só permitido quando não há nenhum registro
    vinculado (login de usuário, folha/férias/13º/rescisão/vale, empreitada,
    contrato, diária ou cronograma sanitário como veterinário agendado), 409
    caso contrário, orientando a desativar em vez de excluir (mesmo padrão de
    excluir_item_estoque em estoque.py).

    Férias e 13º com status "cancelado_rescisao" NÃO contam como vínculo —
    ver o comentário de _TABELAS_COM_PESSOA_ID. E o 409 nomeia cada vínculo
    (quantidade + o que é), porque é a única informação que o usuário tem
    para escolher entre desativar a pessoa e desfazer o vínculo."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    p = session.get(Pessoa, pessoa_id)
    if not p or (p.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    vinculos = []
    for modelo, singular, plural, status_ignorados in _TABELAS_COM_PESSOA_ID:
        registros = session.exec(select(modelo).where(modelo.pessoa_id == pessoa_id)).all()
        if status_ignorados:
            registros = [r for r in registros if getattr(r, "status", None) not in status_ignorados]
        total = len(registros)
        if total:
            vinculos.append(f"{total} {singular if total == 1 else plural}")
    cronogramas_vet = session.exec(
        select(CronogramaSanitario).where(CronogramaSanitario.veterinario_pessoa_id == pessoa_id)
    ).all()
    if cronogramas_vet:
        total = len(cronogramas_vet)
        vinculos.append(
            f"{total} {'cronograma sanitário' if total == 1 else 'cronogramas sanitários'} como veterinário agendado"
        )
    if vinculos:
        raise HTTPException(
            status_code=409,
            detail=(
                f'"{p.nome}" não pode ser excluída porque ainda tem lançamento vinculado: '
                f'{", ".join(vinculos)}. Excluir a pessoa apagaria a referência desses lançamentos. '
                'Ou desative a pessoa (desmarque "Ativo" ao editar) — ela some das listas e o histórico '
                'fica de pé —, ou exclua antes os lançamentos acima.'
            ),
        )
    # Documento anexado não bloqueia a exclusão (diferente dos vínculos acima)
    # — é só um arquivo preso à pessoa, não um registro de negócio; cascade
    # simples, mesmo padrão de excluir_pedido em pedidos.py.
    for a in session.exec(select(PessoaAnexo).where(PessoaAnexo.pessoa_id == pessoa_id)).all():
        if a.caminho_storage:
            try:
                excluir_arquivo(a.caminho_storage, bucket=settings.supabase_bucket_financeiro)
            except RuntimeError:
                pass
        session.delete(a)
    session.delete(p)
    session.commit()
    return {"excluido": True}


# ---------------------------------------------------------------------------
# Documentos anexados à Pessoa — ver CATEGORIAS_PESSOA_ANEXO em fazenda/models/
# pessoal.py. Mesmo padrão de anexo de Pedido (fazenda/api/routers/pedidos.py):
# lista fixa de categorias, conteúdo no Supabase Storage, `data_validade`
# opcional alimenta o alerta de vencimento na Agenda.
# ---------------------------------------------------------------------------
TAMANHO_MAXIMO_ANEXO_PESSOA = 15 * 1024 * 1024  # 15 MB — mesmo limite de Pedido/Lançamento.

# FURO CORRIGIDO (varredura set/2026): o `mime_type` gravado era o
# `file.content_type` que o CLIENTE manda, sem nenhuma allow-list, e
# baixar_anexo_pessoa devolve o arquivo com esse mesmo tipo e
# `Content-Disposition: inline` — o navegador RENDERIZA. Bastava anexar um
# "rg.html"/"cpf.svg" declarado como text/html ou image/svg+xml a uma pessoa
# para ter script executando na origem autenticada do próprio sistema, com o
# token de quem abrisse o anexo (XSS armazenado). É o mesmo achado 55 da
# auditoria, já fechado em documentos.py e fotos.py com esta mesma
# allow-list — só não tinha sido replicado no anexo de PESSOA, que é
# justamente onde ficam RG, CPF, carteira de trabalho e holerite.
# Tipo fora da lista não é recusado (quebraria anexo legítimo de formato
# exótico): vira application/octet-stream, que o navegador baixa em vez de
# renderizar.
_CONTENT_TYPES_PERMITIDOS_ANEXO_PESSOA = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/octet-stream",
}


def _content_type_seguro_anexo(content_type: str | None) -> str:
    return content_type if content_type in _CONTENT_TYPES_PERMITIDOS_ANEXO_PESSOA else "application/octet-stream"


def _caminho_anexo_pessoa(session: Session, fazenda_id: int | None, pessoa_id: int, nome_arquivo: str) -> str:
    """fazenda-X/pessoas/{pessoa_id}/0001_nome.ext — sequencial dentro da pessoa.

    BUG CORRIGIDO (relato do dono, 06/09/2026 — "não consigo excluir
    documento"): a sequência vinha de `1 + len(existentes)`, ou seja, da
    CONTAGEM de anexos vivos. Excluir um documento faz a contagem cair, então
    o próximo upload reaproveita um número que já está em uso; se o nome do
    arquivo também se repetir — que é a regra, não a exceção, no fluxo real
    "anexei o RG errado, apago e anexo o certo" — o caminho gerado é
    IDÊNTICO ao de um anexo que ainda existe. O envio usa `x-upsert`, então o
    arquivo antigo é sobrescrito em silêncio e as DUAS linhas do banco passam
    a apontar para o mesmo objeto no Storage. A partir daí, excluir uma
    apaga o arquivo das duas, e a outra fica travada para sempre: o Storage
    responde 404 na exclusão, o endpoint devolvia 400 e a linha nunca saía
    da tela.

    Agora a sequência sai do MAIOR número já usado nos caminhos da pessoa
    (não da contagem): número devolvido por uma exclusão nunca é reemitido
    enquanto sobrar qualquer anexo, então dois anexos vivos jamais dividem o
    mesmo caminho.
    """
    pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}/pessoas/{pessoa_id}"
    existentes = session.exec(select(PessoaAnexo).where(PessoaAnexo.pessoa_id == pessoa_id)).all()
    maior = 0
    for a in existentes:
        # "…/pessoas/7/0003_rg.pdf" -> 3. Caminho antigo/fora do padrão (ou
        # nulo) simplesmente não entra na conta.
        prefixo = (a.caminho_storage or "").rsplit("/", 1)[-1].split("_", 1)[0]
        if prefixo.isdigit():
            maior = max(maior, int(prefixo))
    seq = 1 + max(maior, len(existentes))
    return f"{pasta}/{seq:04d}_{nome_seguro_storage(nome_arquivo)}"


@router.post("/pessoas/{pessoa_id}/anexos", status_code=201)
async def anexar_arquivo_pessoa(
    pessoa_id: int, file: UploadFile, categoria: str = Form(...),
    data_validade: Optional[date] = Form(None),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Anexa um documento (RG, CPF, contrato, holerite, comprovante...) a uma
    pessoa já cadastrada. Se `data_validade` for informada, a Agenda passa a
    alertar antes do vencimento — hoje só para "Contrato de trabalho por
    prazo determinado" (ver fazenda/rules/agenda_engine.py)."""
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if categoria not in CATEGORIAS_PESSOA_ANEXO:
        raise HTTPException(status_code=400, detail=f"categoria deve ser uma de: {', '.join(CATEGORIAS_PESSOA_ANEXO)}")
    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_ANEXO_PESSOA:
        raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB — não é possível anexar")
    nome_arquivo = file.filename or "arquivo"
    caminho = _caminho_anexo_pessoa(session, fazenda_id, pessoa_id, nome_arquivo)
    content_type = _content_type_seguro_anexo(file.content_type)
    try:
        enviar_arquivo(caminho, conteudo, content_type, bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    anexo = PessoaAnexo(
        pessoa_id=pessoa_id,
        nome_arquivo=nome_arquivo,
        mime_type=content_type,
        tamanho_bytes=len(conteudo),
        categoria=categoria,
        data_validade=data_validade,
        caminho_storage=caminho,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(anexo)
    session.commit()
    session.refresh(anexo)
    return {
        "id": anexo.id, "nome_arquivo": anexo.nome_arquivo, "mime_type": anexo.mime_type,
        "tamanho_bytes": anexo.tamanho_bytes, "categoria": anexo.categoria,
        "data_validade": anexo.data_validade.isoformat() if anexo.data_validade else None,
    }


@router.get("/pessoas/{pessoa_id}/anexos")
def listar_anexos_pessoa(
    pessoa_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    anexos = session.exec(select(PessoaAnexo).where(PessoaAnexo.pessoa_id == pessoa_id)).all()
    return [
        {"id": a.id, "nome_arquivo": a.nome_arquivo, "mime_type": a.mime_type, "tamanho_bytes": a.tamanho_bytes,
         "categoria": a.categoria, "data_validade": a.data_validade.isoformat() if a.data_validade else None,
         "criado_em": a.criado_em.isoformat()}
        for a in anexos
    ]


@router.get("/pessoas/anexos/{anexo_id}")
def baixar_anexo_pessoa(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = session.get(PessoaAnexo, anexo_id)
    if not anexo or (anexo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    try:
        conteudo = baixar_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # A allow-list é aplicada TAMBÉM na saída, não só no upload: os anexos
    # gravados ANTES da correção continuam no banco com o mime_type que o
    # cliente escolheu — um "text/html" já armazenado voltaria a ser
    # renderizado inline se aqui confiássemos na coluna.
    return Response(
        content=conteudo, media_type=_content_type_seguro_anexo(anexo.mime_type),
        headers={"Content-Disposition": f'inline; filename="{anexo.nome_arquivo}"'},
    )


@router.delete("/pessoas/anexos/{anexo_id}")
def excluir_anexo_pessoa(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Remove o documento anexado à pessoa.

    BUG CORRIGIDO (relato do dono, 06/09/2026): qualquer falha do Supabase
    Storage ao apagar o arquivo virava 400 e ABORTAVA a exclusão da linha no
    banco. Arquivo que já não está lá (apagado à mão no painel do Supabase,
    caminho duplicado por causa do bug de sequência em
    `_caminho_anexo_pessoa`, upload que falhou no meio) devolve 404 no
    delete — e o documento passava a ser IMPOSSÍVEL de tirar da tela: toda
    tentativa repetia o mesmo 400, para sempre, porque a causa era
    justamente o arquivo não existir mais.

    A linha do banco é o que o usuário enxerga e é ela que tem que sair. O
    arquivo no bucket é o subproduto: se a remoção dele falhar, no pior caso
    sobra um objeto órfão no Storage (invisível, sem nenhuma linha
    apontando), que é infinitamente melhor que um documento fantasma preso
    no cadastro. É exatamente o que a cascata de `excluir_pessoa` logo acima
    já fazia (`except RuntimeError: pass`) — a incoerência entre as duas era
    o bug.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = session.get(PessoaAnexo, anexo_id)
    if not anexo or (anexo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    if anexo.caminho_storage:
        # Anexos gravados ANTES da correção de `_caminho_anexo_pessoa` podem
        # dividir o mesmo caminho com outro anexo vivo. Apagar o objeto
        # nesse caso derrubaria o download do irmão que fica — só remove do
        # bucket quando ninguém mais aponta para lá.
        # O recorte por fazenda entra NA PRÓPRIA consulta (nunca num `if`
        # em volta dela): sem multi-fazenda provisionado vira
        # `fazenda_id IS NULL`, que é exatamente o conjunto de linhas desse
        # ambiente. Anexo de outra fazenda não é "irmão" de ninguém aqui.
        compartilhado = session.exec(
            select(PessoaAnexo).where(
                PessoaAnexo.fazenda_id == fazenda_id,
                PessoaAnexo.caminho_storage == anexo.caminho_storage,
                PessoaAnexo.id != anexo.id,
            )
        ).first()
        if not compartilhado:
            try:
                excluir_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
            except RuntimeError as exc:
                logger.warning(
                    "Anexo %s da pessoa %s: linha excluída mesmo com falha ao apagar o arquivo no Storage (%s): %s",
                    anexo.id, anexo.pessoa_id, anexo.caminho_storage, exc,
                )
    session.delete(anexo)
    session.commit()
    return {"excluido": True}


@router.get("/pessoas/inseminadores")
def listar_inseminadores(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[str]:
    """Nomes das pessoas cadastradas com o tipo Inseminador (ativas) — usado
    para alimentar os filtros de inseminador em Análise reprodutiva/
    Indicadores/Relatórios, mesmo antes de qualquer serviço lançado.

    FURO CORRIGIDO (varredura set/2026): esta consulta era a ÚNICA de
    `pessoas.py` sem nenhum recorte por fazenda — varria a tabela Pessoa
    inteira. Qualquer usuário autenticado de qualquer fazenda-cliente abria
    o filtro de inseminador de Análise reprodutiva e via, numa lista, o nome
    dos inseminadores de TODAS as outras fazendas da plataforma (dado
    pessoal de funcionário de concorrente, e mapa de quem trabalha onde).
    O filtro agora é parte da consulta: pessoa de outra fazenda e pessoa
    órfã (`fazenda_id` NULL, resíduo real do backfill 029227481e9e) caem as
    duas fora — órfã não é "de todo mundo".

    `fazenda_id is None` só acontece onde o multi-fazenda não está
    provisionado (tabela `fazenda` vazia: suíte de testes e instalação
    anterior à migração f1a2b3c4d5e6); havendo qualquer fazenda cadastrada,
    a trava de porta (exigir_fazenda_selecionada, montada no router de
    cadastro em main.py) recusa antes de chegar aqui. Tratado
    explicitamente, não por omissão."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Pessoa).where(Pessoa.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(Pessoa.fazenda_id == fazenda_id)
    pessoas = session.exec(query).all()
    return sorted({p.nome for p in pessoas if "Inseminador" in (p.tipo or "").split(",")})



