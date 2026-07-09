"""
Router de sanidade — histórico de medicamentos aplicados nos animais e
lançamento de aplicação (um ou mais produtos, por animal ou por lote).
Endpoint: GET /sanidade/aplicacoes, POST /sanidade/aplicacoes
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    CalendarioSanitario, Doenca, Estoque, EventoSanitario, MovimentoEstoque, PrincipioAtivo, ProtocoloSanitario,
    ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa, ProtocoloSanitarioLancamento, Sanidade,
)
from fazenda.rules.calendario_sanitario import proxima_ocorrencia
from fazenda.rules.unidades import pode_dar_baixa_direta, unidades_compativeis

TETOS_VALIDOS = ["AE", "AD", "PD", "PE"]
CLASSIFICACOES_MASTITE = ["clinica", "subclinica", "ambiental"]

router = APIRouter(prefix="/sanidade", tags=["sanidade"])

FREQUENCIAS = ["dias", "meses", "anos"]


@router.get("/aplicacoes")
def listar_aplicacoes(session: Session = Depends(get_session)) -> dict:
    """Aplicações achatadas para o dashboard interativo (filtra no cliente)."""
    registros = []
    for s in session.exec(select(Sanidade)).all():
        d = s.data_aplicacao
        registros.append({
            "numero": s.numero_matriz,
            "raca": s.raca or "(sem raça)",
            "produto": s.produto,
            "categoria": s.categoria or "Outros",
            "dose": s.dose,
            "unidade": s.unidade,
            "atividade": s.atividade,
            "obs": s.obs,
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "mes": f"{d.year}-{d.month:02d}" if d else None,
        })
    return {"aplicacoes": registros, "total": len(registros)}


@router.get("/unidades-compativeis")
def obter_unidades_compativeis(produto: str, session: Session = Depends(get_session)) -> list[str]:
    """Unidades que fazem sentido escolher para este produto, dada sua unidade de estoque."""
    item = session.exec(select(Estoque).where(Estoque.nome == produto)).first()
    return unidades_compativeis(item.unidade if item else None)


class ItemAplicacaoIn(BaseModel):
    produto: str
    via: str | None = None
    quantidade: float
    unidade: str


class AplicacaoIn(BaseModel):
    data_aplicacao: date
    animais: list[str]
    itens: list[ItemAplicacaoIn]
    responsavel: str | None = None
    observacao: str | None = None


@router.post("/aplicacoes")
def registrar_aplicacao(dados: AplicacaoIn, session: Session = Depends(get_session)) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal ou lote")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Adicione ao menos um produto")

    criados = 0
    avisos: list[str] = []
    for item in dados.itens:
        estoque_item = session.exec(select(Estoque).where(Estoque.nome == item.produto)).first()
        compativeis = unidades_compativeis(estoque_item.unidade if estoque_item else None)
        if item.unidade not in compativeis:
            raise HTTPException(
                status_code=400,
                detail=f'Unidade "{item.unidade}" não é compatível com o produto "{item.produto}" (aceitas: {", ".join(compativeis)})',
            )

        for numero in dados.animais:
            session.add(Sanidade(
                numero_matriz=numero,
                data_aplicacao=dados.data_aplicacao,
                produto=item.produto,
                dose=item.quantidade,
                unidade=item.unidade,
                via=item.via,
                responsavel=dados.responsavel,
                obs=dados.observacao,
            ))
            criados += 1

        if estoque_item and estoque_item.estocavel is False:
            pass
        elif estoque_item and pode_dar_baixa_direta(item.unidade, estoque_item.unidade):
            total = item.quantidade * len(dados.animais)
            estoque_item.quantidade = (estoque_item.quantidade or 0) - total
            if estoque_item.estoque_minimo is not None:
                estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
            estoque_item.atualizado_em = datetime.utcnow()
            session.add(estoque_item)
            # Sem este registro, a baixa de sanidade ficava invisível no
            # histórico de /estoque/movimentos e no custo físico do RMCA.
            session.add(MovimentoEstoque(
                nome_item=estoque_item.nome, movimento="Aplicação", quantidade=total,
                unidade=estoque_item.unidade, data_movimento=dados.data_aplicacao,
                observacao=f"Aplicação em {len(dados.animais)} animal(is) — Sanidade",
            ))
        elif estoque_item and estoque_item.unidade and estoque_item.unidade != item.unidade:
            avisos.append(
                f'Baixa de estoque de "{item.produto}" não aplicada — cadastre a equivalência entre '
                f'"{item.unidade}" e "{estoque_item.unidade}" (unidade de estoque do produto).'
            )

    session.commit()
    return {"criados": criados, "avisos": avisos}


# ---------------------------------------------------------------------------
# Calendário sanitário — regras recorrentes (sazonal/de rebanho ou por fase
# fisiológica), cadastradas aqui e acompanhadas com filtro por período/evento.
# ---------------------------------------------------------------------------
def _nomes(session: Session) -> tuple[dict[int, str], dict[int, str], dict[int, str]]:
    eventos = {e.id: e.nome for e in session.exec(select(EventoSanitario)).all()}
    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    principios = {p.id: p.nome for p in session.exec(select(PrincipioAtivo)).all()}
    return eventos, doencas, principios


def _serializar(c: CalendarioSanitario, eventos: dict, doencas: dict, principios: dict) -> dict:
    return {
        **c.model_dump(),
        "evento_sanitario_nome": eventos.get(c.evento_sanitario_id, "—"),
        "doenca_nome": doencas.get(c.doenca_id) if c.doenca_id else None,
        "principio_ativo_nome": principios.get(c.principio_ativo_id) if c.principio_ativo_id else None,
        "proxima_ocorrencia": proxima_ocorrencia(c.data_evento, c.frequencia_valor, c.frequencia_unidade).isoformat(),
    }


@router.get("/calendario")
def listar_calendario(
    data_inicio: str = "", data_fim: str = "", evento_sanitario_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    """
    Lista as regras do calendário sanitário. O filtro de período compara com a
    PRÓXIMA ocorrência projetada (não a data de referência original), já que
    o objetivo é acompanhar o que está por vir — não o histórico já aplicado
    (esse fica em /sanidade/aplicacoes).
    """
    eventos, doencas, principios = _nomes(session)
    regras = session.exec(select(CalendarioSanitario).where(CalendarioSanitario.ativo == True)).all()  # noqa: E712
    saida = [_serializar(c, eventos, doencas, principios) for c in regras]
    if evento_sanitario_id is not None:
        saida = [s for s in saida if s["evento_sanitario_id"] == evento_sanitario_id]
    if data_inicio:
        saida = [s for s in saida if s["proxima_ocorrencia"] >= data_inicio]
    if data_fim:
        saida = [s for s in saida if s["proxima_ocorrencia"] <= data_fim]
    return sorted(saida, key=lambda s: s["proxima_ocorrencia"])


class CalendarioSanitarioIn(BaseModel):
    evento_sanitario_id: int
    categoria_alvo: str | None = None
    doenca_id: int | None = None
    produto: str | None = None
    principio_ativo_id: int | None = None
    dosagem: str | None = None
    frequencia_valor: int
    frequencia_unidade: str
    data_evento: date
    observacao: str | None = None
    ativo: bool = True


def _validar_calendario(dados: CalendarioSanitarioIn, session: Session) -> None:
    if not session.get(EventoSanitario, dados.evento_sanitario_id):
        raise HTTPException(status_code=400, detail="Evento sanitário não encontrado")
    if dados.doenca_id is not None and not session.get(Doenca, dados.doenca_id):
        raise HTTPException(status_code=400, detail="Doença não encontrada")
    if dados.principio_ativo_id is not None and not session.get(PrincipioAtivo, dados.principio_ativo_id):
        raise HTTPException(status_code=400, detail="Princípio ativo não encontrado")
    if dados.frequencia_unidade not in FREQUENCIAS:
        raise HTTPException(status_code=400, detail=f"Frequência inválida (use: {', '.join(FREQUENCIAS)})")
    if dados.frequencia_valor <= 0:
        raise HTTPException(status_code=400, detail="A frequência deve ser maior que zero")


@router.post("/calendario")
def criar_calendario(dados: CalendarioSanitarioIn, session: Session = Depends(get_session)) -> dict:
    _validar_calendario(dados, session)
    c = CalendarioSanitario(**dados.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    eventos, doencas, principios = _nomes(session)
    return _serializar(c, eventos, doencas, principios)


@router.put("/calendario/{calendario_id}")
def atualizar_calendario(calendario_id: int, dados: CalendarioSanitarioIn, session: Session = Depends(get_session)) -> dict:
    c = session.get(CalendarioSanitario, calendario_id)
    if not c:
        raise HTTPException(status_code=404, detail="Regra do calendário sanitário não encontrada")
    _validar_calendario(dados, session)
    for campo, valor in dados.model_dump().items():
        setattr(c, campo, valor)
    session.add(c)
    session.commit()
    session.refresh(c)
    eventos, doencas, principios = _nomes(session)
    return _serializar(c, eventos, doencas, principios)


# ---------------------------------------------------------------------------
# Protocolo sanitário — lançamento (aplicar um protocolo cadastrado a um
# animal). Gera uma aplicação (evento de Agenda) por etapa/dia do protocolo;
# a baixa de estoque só acontece quando o evento é marcado "realizado" na
# Agenda (ver POST /agenda/realizados).
# ---------------------------------------------------------------------------
class ProtocoloLancamentoIn(BaseModel):
    protocolo_id: int
    numero_matriz: str
    data_inicio: date
    responsavel: str | None = None
    observacao: str | None = None
    classificacao_mastite: str | None = None  # "clinica" | "subclinica" | "ambiental"
    resultado_cmt: str | None = None
    tetos_afetados: list[str] = []  # subconjunto de AE/AD/PD/PE


def _serializar_lancamento_protocolo(session: Session, lanc: ProtocoloSanitarioLancamento, protocolos: dict[int, str]) -> dict:
    aplicacoes = session.exec(
        select(ProtocoloSanitarioAplicacao)
        .where(ProtocoloSanitarioAplicacao.lancamento_id == lanc.id)
        .order_by(ProtocoloSanitarioAplicacao.data_prevista)
    ).all()
    etapas = {e.id: e for e in session.exec(select(ProtocoloSanitarioEtapa)).all()}
    return {
        **lanc.model_dump(),
        "protocolo_nome": protocolos.get(lanc.protocolo_id, "—"),
        "aplicacoes": [
            {**a.model_dump(), "etapa": etapas[a.etapa_id].model_dump() if a.etapa_id in etapas else None}
            for a in aplicacoes
        ],
    }


@router.get("/protocolos/lancamentos")
def listar_lancamentos_protocolo(session: Session = Depends(get_session)) -> list[dict]:
    protocolos = {p.id: p.nome for p in session.exec(select(ProtocoloSanitario)).all()}
    lancamentos = session.exec(select(ProtocoloSanitarioLancamento).order_by(ProtocoloSanitarioLancamento.data_inicio.desc())).all()
    return [_serializar_lancamento_protocolo(session, l, protocolos) for l in lancamentos]


@router.post("/protocolos/lancamentos", status_code=201)
def lancar_protocolo(dados: ProtocoloLancamentoIn, session: Session = Depends(get_session)) -> dict:
    protocolo = session.get(ProtocoloSanitario, dados.protocolo_id)
    if not protocolo:
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    etapas = session.exec(
        select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == dados.protocolo_id).order_by(ProtocoloSanitarioEtapa.dia)
    ).all()
    if not etapas:
        raise HTTPException(status_code=400, detail="Este protocolo não tem etapas cadastradas")
    if not dados.numero_matriz.strip():
        raise HTTPException(status_code=400, detail="Informe o animal")

    if protocolo.eh_mastite and not dados.classificacao_mastite:
        raise HTTPException(status_code=400, detail="Informe a classificação da mastite (clínica, subclínica ou ambiental)")
    if dados.classificacao_mastite and dados.classificacao_mastite not in CLASSIFICACOES_MASTITE:
        raise HTTPException(status_code=400, detail=f"Classificação de mastite inválida (aceitas: {', '.join(CLASSIFICACOES_MASTITE)})")
    for teto in dados.tetos_afetados:
        if teto not in TETOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Teto inválido: {teto} (aceitos: {', '.join(TETOS_VALIDOS)})")

    lancamento = ProtocoloSanitarioLancamento(
        protocolo_id=dados.protocolo_id, numero_matriz=dados.numero_matriz.strip(), data_inicio=dados.data_inicio,
        responsavel=dados.responsavel, observacao=dados.observacao,
        classificacao_mastite=dados.classificacao_mastite, resultado_cmt=dados.resultado_cmt,
        tetos_afetados=",".join(dados.tetos_afetados) if dados.tetos_afetados else None,
    )
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)

    for etapa in etapas:
        data_prevista = dados.data_inicio + timedelta(days=etapa.dia - 1)
        session.add(ProtocoloSanitarioAplicacao(lancamento_id=lancamento.id, etapa_id=etapa.id, data_prevista=data_prevista))
    session.commit()

    protocolos = {protocolo.id: protocolo.nome}
    return _serializar_lancamento_protocolo(session, lancamento, protocolos)
