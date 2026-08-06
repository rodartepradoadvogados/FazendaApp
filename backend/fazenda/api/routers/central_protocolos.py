"""
Central de Protocolos — abas Acompanhamento e Histórico: junta IATF, Indução
de Lactação, Sanitário e Customizado num único painel, com o mesmo formato de
linha (nome do lançamento já com a data — ver
fazenda.rules.nomenclatura_protocolo — tipo, progresso), filtrável por nome,
período e tipo (produtivo/reprodutivo/sanitario).

Isto é ADICIONAL — não substitui os relatórios específicos de cada domínio
(Histórico de Ciclos IATF em Reprodução, Protocolos Sanitários em Sanidade,
Relatório de Rastreabilidade Sanitária), que continuam nos mesmos lugares.

Sanitário é o único dos quatro sem um "cabeçalho de lote" (cada
ProtocoloSanitarioLancamento é por animal) — aqui ele é agrupado por
(protocolo_id, data_inicio) só para efeito de exibição, sem alterar o
modelo de dados.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, or_, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    Estoque, MovimentoEstoque,
    ProtocoloCustomizado, ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento,
    ProtocoloIatfAplicacao, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioLancamento,
    Usuario,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules import estoque_baixa
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento
# A baixa reaproveita, sem duplicar uma linha, exatamente o que a Agenda já
# faz: gerar a Sanidade da aplicação e abater o estoque com rastreio de origem.
from fazenda.api.routers.agenda import (
    MedicamentoIatfIn,
    _marcar_protocolo_iatf_realizado,
    _marcar_protocolo_inducao_realizado,
    _marcar_protocolo_custom_realizado,
    PREFIXO_PROTOCOLO_CUSTOM,
)

router = APIRouter(prefix="/central-protocolos", tags=["central-protocolos"])


def _linha(*, tipo: str, origem: str, origem_id: int, nome: str, data_inicio: date, data_fim: date,
           etapas_total: int, etapas_realizadas: int, animais: int, ativo: bool = True,
           encerrado_em: date | None = None, encerrado_motivo: str | None = None) -> dict:
    """Uma linha do painel. `status` é derivado, nunca gravado:

    - `cancelado`  — o lançamento não deveria ter existido (ativo=False).
    - `encerrado`  — existiu, acabou antes do fim do cronograma. As etapas que
                     sobraram continuam contadas como NÃO realizadas: encerrar
                     não maquia o progresso, só para de cobrar pendência.
    - `concluido`  — todas as etapas aplicadas.
    - `ativo`      — em andamento.
    """
    if not ativo:
        status = "cancelado"
    elif encerrado_em is not None:
        status = "encerrado"
    elif etapas_total and etapas_realizadas == etapas_total:
        status = "concluido"
    else:
        status = "ativo"
    return {
        "tipo": tipo, "origem": origem, "origem_id": origem_id, "nome": nome,
        "data_inicio": data_inicio, "data_fim": data_fim,
        "etapas_total": etapas_total, "etapas_realizadas": etapas_realizadas,
        "etapas_faltam": max(etapas_total - etapas_realizadas, 0),
        "animais": animais, "status": status,
        "encerrado_em": encerrado_em, "encerrado_motivo": encerrado_motivo,
    }


def _linhas_iatf(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloIatfLancamento)
    if fazenda_id is not None:
        query = query.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloIatfAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)
    linhas = []
    for l in lancamentos:
        aps = por_lanc.get(l.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            tipo="reprodutivo", origem="iatf", origem_id=l.id, nome=l.nome_protocolo,
            data_inicio=l.data_d0, data_fim=max(datas) if datas else l.data_d0,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len({a.numero_matriz for a in aps}),
            ativo=l.ativo,
            encerrado_em=l.encerrado_em, encerrado_motivo=l.encerrado_motivo,
        ))
    return linhas


def _linhas_inducao(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloInducaoLancamento)
    if fazenda_id is not None:
        # fazenda_id IS NULL = lançamento feito antes da rota de lançar
        # indução carimbar fazenda_id (corrigido em lancar_inducao_lactacao)
        # — sem isto, esses lançamentos antigos somem para sempre desta aba
        # (relato: "Acompanhamento não mostra nenhum protocolo ativo" mesmo
        # com o lançamento existindo e aparecendo em outras telas que não
        # filtram por fazenda).
        query = query.where(or_(ProtocoloInducaoLancamento.fazenda_id == fazenda_id, ProtocoloInducaoLancamento.fazenda_id.is_(None)))
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloInducaoAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)
    linhas = []
    for l in lancamentos:
        aps = por_lanc.get(l.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            tipo="produtivo", origem="inducao", origem_id=l.id, nome=l.nome_protocolo,
            data_inicio=l.data_d0, data_fim=max(datas) if datas else l.data_d0,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len({a.numero_matriz for a in aps}),
            ativo=l.ativo,
            encerrado_em=l.encerrado_em, encerrado_motivo=l.encerrado_motivo,
        ))
    return linhas


def _linhas_customizado(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloCustomizadoLancamento)
    if fazenda_id is not None:
        query = query.where(ProtocoloCustomizadoLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    protocolos = {p.id: p for p in session.exec(select(ProtocoloCustomizado)).all()}
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloCustomizadoAplicacao).where(ProtocoloCustomizadoAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloCustomizadoAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)
    linhas = []
    for l in lancamentos:
        molde = protocolos.get(l.protocolo_id)
        tipo = molde.tipo if molde else None
        if not tipo:
            continue  # sem Tipo cadastrado -> continua na Agenda, fora destes filtros
        aps = por_lanc.get(l.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            tipo=tipo, origem="customizado", origem_id=l.id, nome=l.nome_protocolo,
            data_inicio=l.data_inicio, data_fim=max(datas) if datas else l.data_inicio,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len({a.numero_matriz for a in aps if a.numero_matriz}),
            ativo=l.ativo,
            encerrado_em=l.encerrado_em, encerrado_motivo=l.encerrado_motivo,
        ))
    return linhas


def _linhas_sanitario(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloSanitarioLancamento)
    if fazenda_id is not None:
        query = query.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    protocolos = {p.id: p for p in session.exec(select(ProtocoloSanitario)).all()}
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloSanitarioAplicacao).where(ProtocoloSanitarioAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloSanitarioAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)

    # Agrupa por (protocolo_id, data_inicio) — cada ProtocoloSanitarioLancamento
    # é por animal; aqui vira uma única linha "lote", só para exibição.
    grupos: dict[tuple[int, date], list[ProtocoloSanitarioLancamento]] = defaultdict(list)
    for l in lancamentos:
        grupos[(l.protocolo_id, l.data_inicio)].append(l)

    linhas = []
    for (protocolo_id, data_inicio), grupo in grupos.items():
        molde = protocolos.get(protocolo_id)
        nome_base = molde.nome if molde else "Protocolo Sanitário"
        aps_grupo: list[ProtocoloSanitarioAplicacao] = []
        for l in grupo:
            aps_grupo.extend(por_lanc.get(l.id, []))
        datas = [a.data_prevista for a in aps_grupo]
        dia_inicial = molde.dia_inicial if molde else 0
        dias_previstos = [(d - data_inicio).days + dia_inicial for d in datas] if datas else [dia_inicial]
        dia_final = max(dias_previstos) if dias_previstos else dia_inicial
        nome = gerar_nome_lancamento(nome_base, data_inicio, dia_inicial, dia_final)
        linhas.append(_linha(
            tipo="sanitario", origem="sanitario", origem_id=grupo[0].id, nome=nome,
            data_inicio=data_inicio, data_fim=max(datas) if datas else data_inicio,
            etapas_total=len(aps_grupo), etapas_realizadas=sum(1 for a in aps_grupo if a.realizada),
            animais=len({l.numero_matriz for l in grupo}),
        ))
    return linhas


def _todas_as_linhas(session: Session, fazenda_id: int | None) -> list[dict]:
    return (
        _linhas_iatf(session, fazenda_id)
        + _linhas_inducao(session, fazenda_id)
        + _linhas_sanitario(session, fazenda_id)
        + _linhas_customizado(session, fazenda_id)
    )


def _filtrar(linhas: list[dict], *, nome: str | None, tipo: str | None,
             data_de: date | None, data_ate: date | None) -> list[dict]:
    if nome:
        alvo = nome.strip().lower()
        linhas = [l for l in linhas if alvo in l["nome"].lower()]
    if tipo:
        linhas = [l for l in linhas if l["tipo"] == tipo]
    if data_de:
        linhas = [l for l in linhas if l["data_fim"] >= data_de]
    if data_ate:
        linhas = [l for l in linhas if l["data_inicio"] <= data_ate]
    return sorted(linhas, key=lambda l: l["data_inicio"], reverse=True)


@router.get("/acompanhamento")
def acompanhamento(
    nome: str | None = None, tipo: str | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Protocolos EM ANDAMENTO (ao menos uma etapa pendente) dos 4 tipos, juntos."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linhas = _todas_as_linhas(session, fazenda_id)
    linhas = [l for l in linhas if l["status"] == "ativo"]
    return _filtrar(linhas, nome=nome, tipo=tipo, data_de=None, data_ate=None)


@router.get("/historico")
def historico(
    nome: str | None = None, tipo: str | None = None,
    data_de: date | None = None, data_ate: date | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Concluídos, encerrados e cancelados dos 4 tipos — consulta/exportação."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linhas = _todas_as_linhas(session, fazenda_id)
    linhas = [l for l in linhas if l["status"] in ("concluido", "encerrado", "cancelado")]
    return _filtrar(linhas, nome=nome, tipo=tipo, data_de=data_de, data_ate=data_ate)


# ─────────────────────── Detalhe e ações de um lançamento ───────────────────
#
# Até aqui a Central era só leitura, e a Agenda era o ÚNICO lugar do sistema
# capaz de gravar `realizada = True`. Como a Agenda esconde a etapa cujo dia
# passou, um protocolo que perdeu o dia ficava travado em "em andamento" para
# sempre. Estes três endpoints fecham o ciclo: ver a grade animal × dia, dar
# baixa (inclusive retroativa, com a data REAL da aplicação) e encerrar o que
# acabou antes do fim.

# Origens com cabeçalho de lote próprio. Sanitário fica de fora de propósito:
# cada ProtocoloSanitarioLancamento é POR ANIMAL, e na Central ele já aparece
# agrupado só para exibição — dar baixa nele exigiria decidir o que fazer com
# o grupo inteiro, o que é outra discussão. Segue pela Agenda, como sempre.
_ORIGENS_COM_ACAO = ("iatf", "inducao", "customizado")


class BaixaProtocoloIn(BaseModel):
    dia: int
    # Sem `animais`, dá baixa no dia inteiro; com, só nesse subconjunto.
    animais: list[str] | None = None
    # Dia em que a aplicação REALMENTE aconteceu. Sem ele, hoje.
    data_realizacao: date | None = None
    medicamentos: list[MedicamentoIatfIn] | None = None


class EncerrarProtocoloIn(BaseModel):
    motivo: str | None = None


def _lancamento_ou_404(session: Session, origem: str, origem_id: int, fazenda_id: int | None):
    if origem not in _ORIGENS_COM_ACAO:
        raise HTTPException(
            status_code=400,
            detail="Só protocolos de IATF, indução e customizado têm baixa pela Central — "
                   "o sanitário é lançado por animal e se resolve pela Agenda.",
        )
    modelo = {
        "iatf": ProtocoloIatfLancamento,
        "inducao": ProtocoloInducaoLancamento,
        "customizado": ProtocoloCustomizadoLancamento,
    }[origem]
    lancamento = session.get(modelo, origem_id)
    if not lancamento or (fazenda_id is not None and lancamento.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento de protocolo não encontrado")
    return lancamento


def _aplicacoes_do_lancamento(session: Session, origem: str, origem_id: int) -> list:
    modelo = {
        "iatf": ProtocoloIatfAplicacao,
        "inducao": ProtocoloInducaoAplicacao,
        "customizado": ProtocoloCustomizadoAplicacao,
    }[origem]
    return list(session.exec(
        select(modelo).where(modelo.lancamento_id == origem_id)
    ).all())


@router.get("/{origem}/{origem_id}")
def detalhe(
    origem: str, origem_id: int,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """A grade animal × dia de um lançamento: uma linha por animal, uma coluna
    por dia do cronograma, cada célula com o estado daquela aplicação."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)
    aps = _aplicacoes_do_lancamento(session, origem, origem_id)
    hoje = date.today()

    # `dia` do customizado é absoluto (pode começar em D1); os outros já são
    # relativos ao D0. O rótulo sempre sai relativo ao início do cronograma.
    base = getattr(lancamento, "dia_inicial", 0) if origem == "customizado" else 0

    dias: dict[int, dict] = {}
    for a in aps:
        d = dias.setdefault(a.dia, {
            "dia": a.dia, "rotulo": f"D{a.dia - base}", "data_prevista": a.data_prevista,
            "descricao": getattr(a, "descricao", None), "total": 0, "realizadas": 0,
        })
        d["total"] += 1
        if a.realizada:
            d["realizadas"] += 1

    animais: dict[str, dict] = {}
    for a in aps:
        numero = a.numero_matriz or "—"  # customizado aceita tarefa sem animal
        linha = animais.setdefault(numero, {"numero_matriz": numero, "celulas": []})
        atrasada = (not a.realizada) and a.data_prevista < hoje
        linha["celulas"].append({
            "dia": a.dia, "rotulo": f"D{a.dia - base}",
            "data_prevista": a.data_prevista, "data_realizacao": a.data_realizacao,
            "realizada": a.realizada,
            "estado": "realizada" if a.realizada else ("atrasada" if atrasada else "pendente"),
        })
    for linha in animais.values():
        linha["celulas"].sort(key=lambda c: c["dia"])

    total = len(aps)
    feitas = sum(1 for a in aps if a.realizada)
    return {
        "origem": origem, "origem_id": origem_id,
        "nome": lancamento.nome_protocolo,
        "data_inicio": getattr(lancamento, "data_d0", None) or getattr(lancamento, "data_inicio", None),
        "responsavel": lancamento.responsavel,
        "encerrado_em": lancamento.encerrado_em, "encerrado_motivo": lancamento.encerrado_motivo,
        "ativo": getattr(lancamento, "ativo", True),
        "etapas_total": total, "etapas_realizadas": feitas,
        "etapas_atrasadas": sum(
            1 for a in aps if not a.realizada and a.data_prevista < hoje
        ),
        "dias": sorted(dias.values(), key=lambda d: d["dia"]),
        "animais": sorted(animais.values(), key=lambda l: chave_numero(l["numero_matriz"])),
    }


@router.post("/{origem}/{origem_id}/baixa")
def dar_baixa(
    origem: str, origem_id: int, dados: BaixaProtocoloIn,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    user: Usuario = Depends(get_current_user),
) -> dict:
    """Dá baixa num dia do protocolo — o dia inteiro ou só alguns animais —
    com a data REAL da aplicação. Reaproveita exatamente as mesmas funções que
    a Agenda usa (Sanidade gerada, baixa de estoque com rastreio); a diferença
    é que aqui a data não é obrigatoriamente hoje e o dia pode já ter passado.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    usuario_id = usuario_id_seguro(user)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)
    if lancamento.encerrado_em:
        raise HTTPException(status_code=400, detail="Protocolo encerrado — reabra antes de dar baixa.")
    if dados.data_realizacao and dados.data_realizacao > date.today():
        raise HTTPException(status_code=400, detail="A data da aplicação não pode ser no futuro.")

    if origem == "iatf":
        alvo = next(
            (a for a in _aplicacoes_do_lancamento(session, origem, origem_id) if a.dia == dados.dia),
            None,
        )
        if alvo is None:
            raise HTTPException(status_code=404, detail="Este dia não existe neste lançamento.")
        # O evento IATF é chaveado por (data prevista, dia); `lancamento_id`
        # impede que a baixa atinja outro lote com o mesmo D0.
        avisos = _marcar_protocolo_iatf_realizado(
            session, f"protocolo_iatf_{alvo.data_prevista.isoformat()}_{dados.dia}",
            dados.animais, dados.medicamentos, fazenda_id=fazenda_id, usuario_id=usuario_id,
            data_realizacao=dados.data_realizacao, lancamento_id=origem_id,
        )
    elif origem == "inducao":
        avisos = _marcar_protocolo_inducao_realizado(
            session, f"protocolo_inducao_{origem_id}_{dados.dia}",
            dados.animais, dados.medicamentos, fazenda_id=fazenda_id, usuario_id=usuario_id,
            data_realizacao=dados.data_realizacao,
        )
    else:
        _marcar_protocolo_custom_realizado(
            session, f"{PREFIXO_PROTOCOLO_CUSTOM}{origem_id}_{dados.dia}",
            dados.animais, data_realizacao=dados.data_realizacao,
        )
        avisos = []
    return {"ok": True, "avisos": avisos}


@router.post("/{origem}/{origem_id}/encerrar")
def encerrar(
    origem: str, origem_id: int, dados: EncerrarProtocoloIn,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Encerra o lançamento: ele para de cobrar pendência na Agenda e sai do
    Acompanhamento para o Histórico. As etapas que sobraram continuam gravadas
    como NÃO realizadas — encerrar não é dar por feito o que não foi feito, e
    o progresso mostrado segue sendo o verdadeiro (ex.: 18 de 36)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)
    lancamento.encerrado_em = date.today()
    lancamento.encerrado_motivo = (dados.motivo or "").strip() or None
    session.add(lancamento)
    session.commit()
    return {"ok": True, "encerrado_em": lancamento.encerrado_em}


@router.delete("/{origem}/{origem_id}/encerrar")
def reabrir(
    origem: str, origem_id: int,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Desfaz o encerramento — o protocolo volta a cobrar as etapas que faltam."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)
    lancamento.encerrado_em = None
    lancamento.encerrado_motivo = None
    session.add(lancamento)
    session.commit()
    return {"ok": True}


@router.post("/{origem}/{origem_id}/cancelar")
def cancelar(
    origem: str, origem_id: int, dados: EncerrarProtocoloIn,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    user: Usuario = Depends(get_current_user),
) -> dict:
    """Cancela o lançamento e ESTORNA o estoque que ele consumiu.

    Cancelar ≠ encerrar. Encerrar diz "aconteceu, rendeu o que rendeu e acabou
    antes do fim" — o consumo foi real e fica. Cancelar diz "este lançamento
    não deveria ter existido": as aplicações voltam a NÃO realizadas e cada
    baixa de estoque que ele gerou é devolvida, pelo rastro
    (origem_tipo, origem_id) que `estoque_baixa` grava em MovimentoEstoque.

    A Sanidade gerada por essas aplicações NÃO é apagada: ela é o registro de
    que o produto entrou no animal, e apagá-la reescreveria a ficha. O
    cancelamento é do lançamento, não da história clínica.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    usuario_id = usuario_id_seguro(user)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)

    # Desfaz as aplicações — o lançamento inteiro passa a valer como não feito.
    for ap in _aplicacoes_do_lancamento(session, origem, origem_id):
        if ap.realizada:
            ap.realizada = False
            ap.data_realizacao = None
            session.add(ap)

    # Estorna cada saída de estoque desta origem. Só as SAÍDAS: uma devolução
    # anterior (entrada) não pode ser estornada de novo, ou o saldo inflaria.
    avisos: list[str] = []
    hoje = date.today()
    query_mov = select(MovimentoEstoque).where(
        MovimentoEstoque.origem_tipo == origem,
        MovimentoEstoque.origem_id == origem_id,
        MovimentoEstoque.movimento == "Aplicação",
    )
    if fazenda_id is not None:
        query_mov = query_mov.where(MovimentoEstoque.fazenda_id == fazenda_id)
    for mov in session.exec(query_mov).all():
        item = session.get(Estoque, mov.estoque_id) if mov.estoque_id else None
        if item is None:
            item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=mov.nome_item)
        avisos.extend(estoque_baixa.devolver(
            session, item=item, quantidade=mov.quantidade, unidade=mov.unidade, data=hoje,
            fazenda_id=fazenda_id, usuario_id=usuario_id, produto=mov.nome_item,
            observacao=f"Estorno — protocolo cancelado ({lancamento.nome_protocolo})",
            origem_tipo=origem, origem_id=origem_id,
        ))

    # `ativo=False` é o que marca "cancelado" nas três famílias — `_linha` já
    # dá precedência a ele sobre encerrado/concluído. `encerrado_em` também é
    # preenchido porque é ele que a Agenda consulta para parar de cobrar
    # pendência de IATF e indução; o motivo fica em `encerrado_motivo`, que
    # aqui vale como "por que este lançamento saiu".
    lancamento.ativo = False
    lancamento.encerrado_em = hoje
    lancamento.encerrado_motivo = (dados.motivo or "").strip() or None
    session.add(lancamento)
    session.commit()
    return {"ok": True, "avisos": avisos}
