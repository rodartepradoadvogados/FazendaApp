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
from fazenda.auth import exigir_admin, get_current_user
from fazenda.database import get_session
from fazenda.models import Animal, Lote, MotivoMovimentacao, MovimentoLote, ParametroSugestaoMovimentacao, Usuario
from fazenda.rules.auditoria import mapa_usuarios, usuario_id_seguro
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


def seed_motivos_movimentacao(session: Session) -> None:
    """Cria os motivos padrão se a tabela ainda estiver vazia (idempotente)."""
    if session.exec(select(MotivoMovimentacao)).first():
        return
    for nome in SEED_MOTIVOS:
        session.add(MotivoMovimentacao(nome=nome))
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
def listar_motivos(session: Session = Depends(get_session)) -> list[str]:
    """Nomes dos motivos ativos, na ordem cadastrada — usado pelos selects do front."""
    motivos = session.exec(
        select(MotivoMovimentacao).where(MotivoMovimentacao.ativo == True).order_by(MotivoMovimentacao.id)  # noqa: E712
    ).all()
    return [m.nome for m in motivos]


@router.get("/motivos/cadastro")
def listar_motivos_cadastro(session: Session = Depends(get_session)) -> list[dict]:
    """Todos os motivos (inclusive inativos), para a tela de cadastro em Configurações."""
    motivos = session.exec(select(MotivoMovimentacao).order_by(MotivoMovimentacao.id)).all()
    return [m.model_dump() for m in motivos]


@router.post("/motivos")
def criar_motivo(dados: MotivoIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(MotivoMovimentacao).where(MotivoMovimentacao.nome == nome)).first():
        raise HTTPException(status_code=409, detail="Já existe um motivo com esse nome")
    motivo = MotivoMovimentacao(nome=nome, ativo=dados.ativo)
    session.add(motivo)
    session.commit()
    session.refresh(motivo)
    return motivo.model_dump()


@router.put("/motivos/{motivo_id}")
def atualizar_motivo(motivo_id: int, dados: MotivoIn, session: Session = Depends(get_session)) -> dict:
    motivo = session.get(MotivoMovimentacao, motivo_id)
    if not motivo:
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
def sugestoes_movimentacao(session: Session = Depends(get_session)) -> dict:
    """
    Sugestão automática de movimentação entre lotes: usa os critérios já
    cadastrados em cada lote (Configurações > Cadastro > Lotes) — não pede
    nenhum parâmetro novo. Só considera lotes com pelo menos um critério
    definido; um lote sem nenhum critério "atenderia" o rebanho inteiro, então
    fica de fora da comparação.
    """
    hoje = date.today()
    lotes = session.exec(select(Lote)).all()
    animais, servicos_por_animal, sanidades_por_animal, peso_por_animal = coletar_dados_criterios(session)

    sugestoes = sugerir_movimentacoes(lotes, animais, hoje, peso_por_animal, servicos_por_animal, sanidades_por_animal)
    return {
        "sugestoes": sugestoes,
        "total": len(sugestoes),
        "lotes_com_criterio": sum(1 for l in lotes if lote_tem_criterio(l)),
    }


def _parametro_sugestao_movimentacao(session: Session) -> ParametroSugestaoMovimentacao:
    """Linha única (id=1, mesmo padrão de `ParametroDiariaPadrao`) com a
    configuração de quando as sugestões de troca de lote aparecem na Agenda."""
    parametro = session.get(ParametroSugestaoMovimentacao, 1)
    if not parametro:
        parametro = ParametroSugestaoMovimentacao(id=1)
        session.add(parametro)
        session.commit()
        session.refresh(parametro)
    return parametro


@router.get("/parametro-agendamento")
def obter_parametro_agendamento(session: Session = Depends(get_session)) -> dict:
    return _parametro_sugestao_movimentacao(session).model_dump()


class ParametroAgendamentoIn(BaseModel):
    modo: str  # "na_data_parametro" | "dia_fixo_semana"
    dia_semana: int = 4


@router.put("/parametro-agendamento")
def salvar_parametro_agendamento(
    dados: ParametroAgendamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)
) -> dict:
    if dados.modo not in ("na_data_parametro", "dia_fixo_semana"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    if not 0 <= dados.dia_semana <= 6:
        raise HTTPException(status_code=400, detail="Dia da semana inválido")
    parametro = _parametro_sugestao_movimentacao(session)
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
) -> list[dict]:
    query = select(MovimentoLote)
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
def mover_animais(dados: MoverIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    destino = session.exec(select(Lote).where(Lote.codigo == dados.lote_destino_codigo)).first()
    if not destino:
        raise HTTPException(status_code=404, detail="Lote de destino não encontrado")
    rotulo_destino = _rotulo(destino.codigo, destino.nome)

    movidos = 0
    nao_encontrados = []
    for numero in dados.animais:
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
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
        ))
        movidos += 1

    session.commit()
    return {"movidos": movidos, "nao_encontrados": nao_encontrados}
