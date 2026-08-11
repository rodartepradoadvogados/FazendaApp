"""
Router de Lida — lançar/listar ativos. O cadastro do molde vive em
fazenda/api/routers/cadastro/lida.py; aqui só o que acontece depois de o
molde existir: aplicar contra animais/lote/tarefa da fazenda, o que
materializa as aplicações que a Agenda lê (ver fazenda/rules/lida.py).
Confirmar (baixa), encerrar e cancelar um lançamento acontecem pela Central
de Protocolos (fazenda/api/routers/central_protocolos.py), que já tem esse
mecanismo genérico para IATF/indução/customizado — "lida" foi só mais uma
origem adicionada lá.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import Usuario, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import Lida, LidaAplicacao, LidaEtapa, LidaLancamento
from fazenda.ordenacao import chave_numero
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento

router = APIRouter(prefix="/lida", tags=["lida"])


@router.get("")
def listar_lidas_para_lancar(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lidas ativas disponíveis para lançamento (o cadastro/edição vive em
    Configurações > Cadastro > Lida)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Lida).where(Lida.ativo == True).order_by(Lida.nome)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(Lida.fazenda_id == fazenda_id)
    lidas = session.exec(query).all()
    out = []
    for l in lidas:
        etapas = session.exec(
            select(LidaEtapa).where(LidaEtapa.lida_id == l.id).order_by(LidaEtapa.dia_inicio, LidaEtapa.ordem)
        ).all()
        out.append({**l.model_dump(), "etapas": [e.model_dump() for e in etapas]})
    return out


class LancarLidaIn(BaseModel):
    lida_id: int
    animais: list[str] = []  # vazio = tarefa da fazenda, sem animal específico
    lote: str | None = None  # rótulo informativo
    data_inicio: date
    data_fim: date | None = None  # obrigatório no modo "frequencia"
    responsavel: str | None = None
    observacao: str | None = None


def _dias_periodo(etapas: list[LidaEtapa]) -> dict[int, LidaEtapa]:
    """Expande cada etapa (dia_inicio..dia_fim, ou só dia_inicio quando
    dia_fim é None) num mapa {dia: etapa} — uma aplicação por dia do
    intervalo, todas com a mesma descrição/insumo da etapa."""
    por_dia: dict[int, LidaEtapa] = {}
    for e in etapas:
        fim = e.dia_fim if e.dia_fim is not None else e.dia_inicio
        for dia in range(e.dia_inicio, fim + 1):
            por_dia[dia] = e  # etapas não se sobrepõem por construção do cadastro
    return por_dia


@router.post("/lancar", status_code=201)
def lancar_lida(
    dados: LancarLidaIn, response: Response, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    lida = session.get(Lida, dados.lida_id)
    if not lida or (fazenda_id is not None and lida.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lida não encontrada")
    if not lida.ativo:
        raise HTTPException(status_code=400, detail="Esta lida está inativa")

    animais = [n.strip() for n in dados.animais if n.strip()]
    alvo_tipo = "animal" if animais else ("lote" if dados.lote else "tarefa_fazenda")

    # (dia relativo, descrição, insumo, dose, unidade, foto_obrigatoria,
    # data_prevista) — o que muda entre os dois modos é só como esta lista é
    # montada.
    passos: list[tuple[int, str, str | None, float | None, str | None, bool, date]] = []
    if lida.modo == "frequencia":
        if not dados.data_fim:
            raise HTTPException(status_code=400, detail="Informe até quando esta lida se repete")
        if dados.data_fim < dados.data_inicio:
            raise HTTPException(status_code=400, detail="A data final não pode ser antes da data inicial")
        dia = 0
        data_atual = dados.data_inicio
        while data_atual <= dados.data_fim:
            passos.append((
                dia, lida.descricao_evento or "Executar lida", lida.insumo_padrao,
                lida.insumo_dose, lida.insumo_unidade, lida.foto_obrigatoria, data_atual,
            ))
            dia += lida.frequencia_dias
            data_atual = dados.data_inicio + timedelta(days=dia)
    else:
        etapas = session.exec(
            select(LidaEtapa).where(LidaEtapa.lida_id == lida.id).order_by(LidaEtapa.dia_inicio, LidaEtapa.ordem)
        ).all()
        if not etapas:
            raise HTTPException(status_code=400, detail="Esta lida não tem etapas cadastradas")
        for dia, etapa in sorted(_dias_periodo(etapas).items()):
            data_prevista = dados.data_inicio + timedelta(days=dia - lida.dia_inicial)
            passos.append((
                dia, etapa.descricao_evento, etapa.insumo_padrao,
                etapa.insumo_dose, etapa.insumo_unidade, etapa.foto_obrigatoria, data_prevista,
            ))

    if not passos:
        raise HTTPException(status_code=400, detail="Nenhuma ocorrência gerada neste intervalo")

    # Idempotência (mesmo padrão de producao.lancar_inducao_lactacao): duplo
    # clique ou retry da fila offline não pode criar um segundo lançamento
    # "Ativo" da mesma lida/data/alvo. `animais` pode ser [] (tarefa da
    # fazenda ou lote sem lista nominal — `numero_matriz` fica None em toda
    # aplicação); o set() vazio compara certo com outro vazio sem tratamento
    # especial. No modo "frequencia" `data_fim` não é uma coluna gravada em
    # LidaLancamento (só molda os passos), então dois lançamentos com o
    # mesmo início mas fins diferentes teriam o mesmo (lida_id, data_inicio,
    # animais) — para não confundi-los com um retry de verdade, a
    # equivalência compara também o CONJUNTO DE DIAS gerados (`dia` de cada
    # passo), que muda com data_fim/frequência/edição do molde; um retry
    # genuíno reenvia o mesmo payload e gera exatamente os mesmos dias.
    animais_set = set(animais)
    dias_set = {p[0] for p in passos}
    candidatos = session.exec(
        select(LidaLancamento)
        .where(LidaLancamento.lida_id == lida.id)
        .where(LidaLancamento.data_inicio == dados.data_inicio)
        .where(LidaLancamento.ativo == True)  # noqa: E712
        .where(LidaLancamento.encerrado_em.is_(None))
    ).all()
    for candidato in candidatos:
        if fazenda_id is not None and candidato.fazenda_id not in (fazenda_id, None):
            continue
        aplicacoes_candidato = session.exec(
            select(LidaAplicacao).where(LidaAplicacao.lancamento_id == candidato.id)
        ).all()
        animais_candidato = {a.numero_matriz for a in aplicacoes_candidato if a.numero_matriz is not None}
        dias_candidato = {a.dia for a in aplicacoes_candidato}
        if animais_candidato == animais_set and dias_candidato == dias_set:
            response.status_code = 200
            return {
                "criado": False, "lancamento_id": candidato.id, "eventos_criados": 0,
                "animais": len(animais_set),
                "aviso": (
                    "Já existe um lançamento ativo idêntico desta lida (mesma data, mesmo "
                    "período gerado e mesmo(s) animal(is), ou mesma tarefa/lote) — "
                    "reaproveitado em vez de criar um duplicado."
                ),
            }

    dia_final = max(p[0] for p in passos)
    nome_protocolo = gerar_nome_lancamento(lida.nome, dados.data_inicio, lida.dia_inicial if lida.modo == "periodo" else 0, dia_final)
    lancamento = LidaLancamento(
        lida_id=lida.id, nome_protocolo=nome_protocolo, modo=lida.modo,
        dia_inicial=lida.dia_inicial if lida.modo == "periodo" else 0, data_inicio=dados.data_inicio,
        alvo_tipo=alvo_tipo, lote=dados.lote, responsavel=dados.responsavel, observacao=dados.observacao,
        usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
    )
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)

    eventos_criados = 0
    alvos = animais or [None]
    for dia, descricao, insumo, insumo_dose, insumo_unidade, foto_obrigatoria, data_prevista in passos:
        for numero in alvos:
            session.add(LidaAplicacao(
                lancamento_id=lancamento.id, numero_matriz=numero, dia=dia,
                descricao=descricao, insumo=insumo, insumo_dose=insumo_dose, insumo_unidade=insumo_unidade,
                foto_obrigatoria=foto_obrigatoria, data_prevista=data_prevista, fazenda_id=fazenda_id,
            ))
            eventos_criados += 1

    session.commit()
    return {"criado": True, "lancamento_id": lancamento.id, "eventos_criados": eventos_criados, "animais": len(animais)}


@router.get("/ativos")
def listar_ativos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lançamentos ativos com pelo menos uma aplicação pendente."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(LidaLancamento).where(LidaLancamento.ativo == True).order_by(  # noqa: E712
        LidaLancamento.data_inicio.desc()
    )
    if fazenda_id is not None:
        query = query.where(LidaLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []

    aplicacoes = session.exec(
        select(LidaAplicacao).where(LidaAplicacao.lancamento_id.in_(tuple(l.id for l in lancamentos)))
    ).all()
    por_lancamento: dict[int, list[LidaAplicacao]] = {}
    for ap in aplicacoes:
        por_lancamento.setdefault(ap.lancamento_id, []).append(ap)

    ativos = []
    for lanc in lancamentos:
        aps = por_lancamento.get(lanc.id, [])
        pendentes = [a for a in aps if not a.realizada]
        if not pendentes:
            continue
        animais = sorted({a.numero_matriz for a in aps if a.numero_matriz}, key=chave_numero)
        proxima = min(pendentes, key=lambda a: a.dia)
        ativos.append({
            "lancamento_id": lanc.id,
            "nome_protocolo": lanc.nome_protocolo,
            "modo": lanc.modo,
            "data_inicio": lanc.data_inicio.isoformat(),
            "alvo_tipo": lanc.alvo_tipo,
            "lote": lanc.lote,
            "responsavel": lanc.responsavel,
            "total_etapas": len(aps),
            "pendentes": len(pendentes),
            "animais": animais,
            "proxima_etapa": f"D{proxima.dia - lanc.dia_inicial}",
            "proxima_data": proxima.data_prevista.isoformat(),
            "proxima_foto_obrigatoria": proxima.foto_obrigatoria,
        })
    return ativos
