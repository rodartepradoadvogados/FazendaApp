"""
Router de animais — listagem e consulta de animais.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    Animal, AgendaManual, BaixaAnimal, ColostragemBezerra, CompraAnimal, ControleLeiteiro, MovimentoLote, Parto,
    PesagemCorporal, ProtocoloIatfAplicacao, ProtocoloSanitario, ProtocoloSanitarioLancamento, QualidadeLeite,
    Sanidade, Secagem, Servico,
)
from fazenda.ordenacao import chave_numero

router = APIRouter(prefix="/animais", tags=["animais"])


@router.get("/")
def listar_animais(
    grupo: str | None = Query(None, description="Filtrar por grupo primário"),
    sit_rep: str | None = Query(None, description="Filtrar por situação reprodutiva"),
    ativo: bool = Query(True),
    incluir_machos: bool = Query(False, description="Incluir machos e sêmen (padrão: só fêmeas)"),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(Animal).where(Animal.ativo == ativo)
    if grupo:
        query = query.where(Animal.grupo_primario.contains(grupo))
    if sit_rep:
        query = query.where(Animal.sit_rep == sit_rep)

    animais = session.exec(query).all()
    if not incluir_machos:
        # Rebanho = só fêmeas. Exclui sêmen/reprodutores e machos. Registros
        # antigos (sem o campo) permanecem até o próximo upload do GERAL.
        animais = [a for a in animais if not a.eh_semen and a.sexo != "M"]

    # Datas reprodutivas por matriz: último serviço POSITIVO (concepção) e último
    # parto. Usadas no front para dias de gestação, dias para o parto e PEV.
    ult_pos: dict[str, object] = {}
    for s in session.exec(select(Servico)).all():
        d = s.data_servico
        if d and (s.diagnostico or "").strip().upper() == "POSITIVO":
            if s.numero_matriz not in ult_pos or d > ult_pos[s.numero_matriz]:
                ult_pos[s.numero_matriz] = d
    ult_parto: dict[str, object] = {}
    for p in session.exec(select(Parto)).all():
        d = p.data_parto
        if d and (p.numero_matriz not in ult_parto or d > ult_parto[p.numero_matriz]):
            ult_parto[p.numero_matriz] = d

    saida = []
    for a in animais:
        d = a.model_dump()
        sp = ult_pos.get(a.numero)
        pp = ult_parto.get(a.numero)
        d["data_ult_servico_pos"] = sp.isoformat() if sp else None
        d["data_ult_parto"] = pp.isoformat() if pp else None
        saida.append(d)
    saida.sort(key=lambda d: chave_numero(d["numero"]))
    return saida


@router.get("/{numero}")
def buscar_animal(numero: str, session: Session = Depends(get_session)) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")
    return animal.model_dump()


@router.get("/{numero}/ficha")
def ficha_animal(numero: str, session: Session = Depends(get_session)) -> dict:
    """
    Ficha única do animal: absolutamente todos os lançamentos já registrados
    para ele, reunidos em uma resposta — reprodução, parto, colostragem/IgG,
    produção, sanidade, movimentação de lote, compra/baixa e agenda. Serve
    tanto a tela de consulta quanto a exportação em PDF (por maior que fique).
    """
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")

    def _dump(rows) -> list[dict]:
        return [r.model_dump() for r in rows]

    partos = session.exec(select(Parto).where(Parto.numero_matriz == numero).order_by(Parto.data_parto)).all()
    servicos = session.exec(select(Servico).where(Servico.numero_matriz == numero).order_by(Servico.data_servico)).all()

    protocolos_iatf = session.exec(
        select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == numero).order_by(ProtocoloIatfAplicacao.data_prevista)
    ).all()

    movimentos_lote = session.exec(
        select(MovimentoLote).where(MovimentoLote.numero_matriz == numero).order_by(MovimentoLote.data_movimento)
    ).all()

    colostragem = session.exec(select(ColostragemBezerra).where(ColostragemBezerra.numero_animal == numero)).first()

    controles_leiteiros = session.exec(
        select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == numero).order_by(ControleLeiteiro.data_controle)
    ).all()

    pesagens_corporais = session.exec(
        select(PesagemCorporal).where(PesagemCorporal.numero_matriz == numero).order_by(PesagemCorporal.data_pesagem)
    ).all()

    qualidade_leite = session.exec(
        select(QualidadeLeite).where(QualidadeLeite.numero_matriz == numero).order_by(QualidadeLeite.data_coleta)
    ).all()

    aplicacoes_sanitarias = session.exec(
        select(Sanidade).where(Sanidade.numero_matriz == numero).order_by(Sanidade.data_aplicacao)
    ).all()

    protocolos_nomes = {p.id: p.nome for p in session.exec(select(ProtocoloSanitario)).all()}
    protocolos_sanitarios_rows = session.exec(
        select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.numero_matriz == numero).order_by(ProtocoloSanitarioLancamento.data_inicio)
    ).all()
    protocolos_sanitarios = [
        {**p.model_dump(), "protocolo_nome": protocolos_nomes.get(p.protocolo_id, "—")} for p in protocolos_sanitarios_rows
    ]

    secagens = session.exec(select(Secagem).where(Secagem.numero_matriz == numero).order_by(Secagem.data_secagem)).all()

    eventos_agenda = [
        e for e in session.exec(select(AgendaManual).order_by(AgendaManual.data_evento)).all()
        if e.numero_animal and numero in [n.strip() for n in e.numero_animal.split(",")]
    ]

    baixa = session.exec(select(BaixaAnimal).where(BaixaAnimal.numero_animal == numero)).first()
    compra = session.exec(select(CompraAnimal).where(CompraAnimal.numero_animal == numero)).first()

    return {
        "animal": animal.model_dump(),
        "partos": _dump(partos),
        "servicos": _dump(servicos),
        "protocolos_iatf": _dump(protocolos_iatf),
        "movimentos_lote": _dump(movimentos_lote),
        "colostragem": colostragem.model_dump() if colostragem else None,
        "controles_leiteiros": _dump(controles_leiteiros),
        "pesagens_corporais": _dump(pesagens_corporais),
        "qualidade_leite": _dump(qualidade_leite),
        "aplicacoes_sanitarias": _dump(aplicacoes_sanitarias),
        "protocolos_sanitarios": protocolos_sanitarios,
        "secagens": _dump(secagens),
        "eventos_agenda": _dump(eventos_agenda),
        "baixa": baixa.model_dump() if baixa else None,
        "compra": compra.model_dump() if compra else None,
    }
