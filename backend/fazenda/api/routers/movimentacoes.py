"""
Router de movimentação de animais entre lotes — transferência manual
(individual ou em lote) com data, hora e motivo, e histórico/relatório.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.lotes import coletar_dados_criterios
from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Animal, Lote, MotivoMovimentacao, MovimentoLote, ParametroSugestaoMovimentacao, SeedFlag, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios, usuario_id_seguro
from fazenda.rules.lote_criterios import lote_tem_criterio, sugerir_movimentacoes

router = APIRouter(prefix="/movimentacoes", tags=["movimentacoes"])

# Seed inicial — usado só na primeira subida do banco (ver seed_motivos_movimentacao).
# "Outro motivo" é tratado à parte pelo front: ao ser escolhido, abre um campo de
# texto livre e o que for digitado ali vira o próprio valor de `motivo`.
SEED_MOTIVOS = [
    "Crescimento",
    "Desmama",
    "Aptidão",
    "Inseminação",
    "Pré-parto",
    "Pós-parto",
    "Aumento de DEL e/ou produção",
    "Final de DEL ou queda de produção",
    "Tratamento/doença",
    "Secagem",
    "Nascimento",
    "Outro motivo",
]


def seed_motivos_movimentacao(session: Session, fazenda_id: int | None = None) -> None:
    """Cria os motivos padrão uma única vez por fazenda (idempotente via SeedFlag)."""
    chave = f"motivos_movimentacao_v1_fazenda_{fazenda_id}" if fazenda_id is not None else "motivos_movimentacao_v1"
    if session.get(SeedFlag, chave):
        return
    for nome in SEED_MOTIVOS:
        query = select(MotivoMovimentacao).where(MotivoMovimentacao.nome == nome)
        if fazenda_id is not None:
            query = query.where(MotivoMovimentacao.fazenda_id == fazenda_id)
        if not session.exec(query).first():
            session.add(MotivoMovimentacao(nome=nome, fazenda_id=fazenda_id))
    session.add(SeedFlag(chave=chave))
    session.commit()


def _rotulo(codigo: str, nome: str) -> str:
    return f"{codigo} - {nome}"


class MoverIn(BaseModel):
    data_movimento: date
    hora_movimento: str | None = None
    motivo: str | None = None
    observacao: str | None = None
    responsavel: str | None = None
    lote_destino_codigo: str
    animais: list[str]


class MotivoIn(BaseModel):
    nome: str
    ativo: bool = True


@router.get("/motivos")
def listar_motivos(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[str]:
    """Nomes dos motivos ativos, na ordem cadastrada — usado pelos selects do front."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(MotivoMovimentacao).where(MotivoMovimentacao.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(MotivoMovimentacao.fazenda_id == fazenda_id)
    motivos = session.exec(query.order_by(MotivoMovimentacao.id)).all()
    return [m.nome for m in motivos]


@router.get("/motivos/cadastro")
def listar_motivos_cadastro(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    """Todos os motivos (inclusive inativos), para a tela de cadastro em Configurações."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(MotivoMovimentacao)
    if fazenda_id is not None:
        query = query.where(MotivoMovimentacao.fazenda_id == fazenda_id)
    motivos = session.exec(query.order_by(MotivoMovimentacao.id)).all()
    return [m.model_dump() for m in motivos]


@router.post("/motivos")
def criar_motivo(
    dados: MotivoIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_existente = select(MotivoMovimentacao).where(MotivoMovimentacao.nome == nome)
    if fazenda_id is not None:
        query_existente = query_existente.where(MotivoMovimentacao.fazenda_id == fazenda_id)
    if session.exec(query_existente).first():
        raise HTTPException(status_code=409, detail="Já existe um motivo com esse nome")
    motivo = MotivoMovimentacao(nome=nome, ativo=dados.ativo, fazenda_id=fazenda_id)
    session.add(motivo)
    session.commit()
    session.refresh(motivo)
    return motivo.model_dump()


@router.put("/motivos/{motivo_id}")
def atualizar_motivo(
    motivo_id: int,
    dados: MotivoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    motivo = session.get(MotivoMovimentacao, motivo_id)
    if not motivo or (fazenda_id is not None and motivo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Motivo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    motivo.nome = nome
    motivo.ativo = dados.ativo
    session.add(motivo)
    session.commit()
    session.refresh(motivo)
    return motivo.model_dump()


@router.get("/sugestoes")
def sugestoes_movimentacao(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """
    Sugestão automática de movimentação entre lotes: usa os critérios já
    cadastrados em cada lote (Configurações > Cadastro > Lotes) — não pede
    nenhum parâmetro novo. Só considera lotes com pelo menos um critério
    definido; um lote sem nenhum critério "atenderia" o rebanho inteiro, então
    fica de fora da comparação.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = date.today()
    query_lotes = select(Lote).where(Lote.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_lotes = query_lotes.where(Lote.fazenda_id == fazenda_id)
    lotes = session.exec(query_lotes).all()
    dados_criterios = coletar_dados_criterios(session, fazenda_id)

    sugestoes = sugerir_movimentacoes(lotes, dados_criterios["animais"], hoje, dados_criterios)
    return {
        "sugestoes": sugestoes,
        "total": len(sugestoes),
        "lotes_com_criterio": sum(1 for l in lotes if lote_tem_criterio(l)),
    }


def _parametro_sugestao_movimentacao(session: Session, fazenda_id: int | None = None) -> ParametroSugestaoMovimentacao:
    """Uma linha por fazenda (mesmo padrão de `ParametroDiariaPadrao`) com a
    configuração de quando as sugestões de troca de lote aparecem na Agenda."""
    query = select(ParametroSugestaoMovimentacao)
    query = query.where(ParametroSugestaoMovimentacao.fazenda_id == fazenda_id) if fazenda_id is not None else query.where(
        ParametroSugestaoMovimentacao.fazenda_id.is_(None)
    )
    parametro = session.exec(query).first()
    if not parametro:
        parametro = ParametroSugestaoMovimentacao(fazenda_id=fazenda_id)
        session.add(parametro)
        session.commit()
        session.refresh(parametro)
    return parametro


@router.get("/parametro-agendamento")
def obter_parametro_agendamento(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return _parametro_sugestao_movimentacao(session, fazenda_id=fazenda_id_seguro(fazenda_id)).model_dump()


class ParametroAgendamentoIn(BaseModel):
    modo: str  # "na_data_parametro" | "dia_fixo_semana"
    dia_semana: int = 4


@router.put("/parametro-agendamento")
def salvar_parametro_agendamento(
    dados: ParametroAgendamentoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if dados.modo not in ("na_data_parametro", "dia_fixo_semana"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    if not 0 <= dados.dia_semana <= 6:
        raise HTTPException(status_code=400, detail="Dia da semana inválido")
    parametro = _parametro_sugestao_movimentacao(session, fazenda_id=fazenda_id_seguro(fazenda_id))
    parametro.modo = dados.modo
    parametro.dia_semana = dados.dia_semana
    parametro.atualizado_em = datetime.utcnow()
    session.add(parametro)
    session.commit()
    session.refresh(parametro)
    return parametro.model_dump()


@router.get("/")
def listar_movimentacoes(
    numero_matriz: str | None = Query(None),
    data_inicio: date | None = Query(None),
    data_fim: date | None = Query(None),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(MovimentoLote)
    if fazenda_id is not None:
        query = query.where(MovimentoLote.fazenda_id == fazenda_id)
    if numero_matriz:
        query = query.where(MovimentoLote.numero_matriz.contains(numero_matriz))
    if data_inicio:
        query = query.where(MovimentoLote.data_movimento >= data_inicio)
    if data_fim:
        query = query.where(MovimentoLote.data_movimento <= data_fim)
    movs = session.exec(query.order_by(MovimentoLote.data_movimento.desc(), MovimentoLote.id.desc())).all()
    registros = [m.model_dump() for m in movs]
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    for r in registros:
        r["usuario_nome"] = nomes.get(r["usuario_id"])
    return registros


@router.post("/mover")
def mover_animais(
    dados: MoverIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    query_destino = select(Lote).where(Lote.codigo == dados.lote_destino_codigo)
    if fazenda_id is not None:
        query_destino = query_destino.where(Lote.fazenda_id == fazenda_id)
    destino = session.exec(query_destino).first()
    if not destino:
        raise HTTPException(status_code=404, detail="Lote de destino não encontrado")
    if not destino.ativo:
        raise HTTPException(
            status_code=400,
            detail=f"Lote {_rotulo(destino.codigo, destino.nome)} está inativo — reative-o ou escolha outro destino",
        )
    rotulo_destino = _rotulo(destino.codigo, destino.nome)

    movidos = 0
    nao_encontrados = []
    for numero in dados.animais:
        query_animal = select(Animal).where(Animal.numero == numero)
        if fazenda_id is not None:
            query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        animal = session.exec(query_animal).first()
        if not animal:
            nao_encontrados.append(numero)
            continue

        origem = animal.grupo_primario
        animal.grupo_primario = rotulo_destino
        animal.grupo_raw = rotulo_destino
        animal.grupo_manual = True
        animal.atualizado_em = datetime.utcnow()
        session.add(animal)

        session.add(MovimentoLote(
            numero_matriz=numero,
            lote_origem=origem,
            lote_destino=rotulo_destino,
            data_movimento=dados.data_movimento,
            hora_movimento=dados.hora_movimento,
            motivo=dados.motivo or "",
            observacao=dados.observacao,
            responsavel=dados.responsavel,
            usuario_id=usuario_id_seguro(user),
            fazenda_id=fazenda_id,
        ))
        movidos += 1

    session.commit()
    return {"movidos": movidos, "nao_encontrados": nao_encontrados}
