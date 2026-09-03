"""
Central de Protocolos — abas Acompanhamento e Histórico: junta IATF, Indução
de Lactação, Sanitário e Customizado num único painel, com o mesmo formato de
linha (nome do lançamento já com a data — ver
fazenda.rules.nomenclatura_protocolo — tipo, progresso), filtrável por nome,
período e tipo (produtivo/reprodutivo/sanitario).

Isto é ADICIONAL — não substitui os relatórios específicos de cada domínio
(Histórico de Ciclos IATF em Reprodução, Protocolos Sanitários em Sanidade,
Relatório de Rastreabilidade Sanitária), que continuam nos mesmos lugares.

As 5 famílias têm cabeçalho de lote e ação completa (marcar, desfazer,
cancelar, encerrar) pela Central. Sanitário é a única com uma camada extra
entre o cabeçalho (ProtocoloSanitarioLote) e a aplicação: um
ProtocoloSanitarioLancamento POR ANIMAL (as outras 4 já têm `numero_matriz`
direto na aplicação) — por isso alguns pontos (`_linhas_sanitario`,
`_aplicacoes_do_lancamento`, `desfazer_aplicacao`, `cancelar`) têm um passo a
mais para essa família específica, em vez de reaproveitar o dict genérico
`{origem: modelo}` das outras.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Estoque, MovimentoEstoque,
    LidaAplicacao, LidaLancamento,
    ProtocoloCustomizado, ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento,
    ProtocoloIatfAplicacao, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLactacao, ProtocoloInducaoLancamento, ProtocoloInducaoMedicamento,
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento, ProtocoloSanitarioLote,
    Usuario,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules import estoque_baixa
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento, nome_curto
# A baixa reaproveita, sem duplicar uma linha, exatamente o que a Agenda já
# faz: gerar a Sanidade da aplicação e abater o estoque com rastreio de origem.
from fazenda.api.routers.agenda import (
    MedicamentoIatfIn,
    _marcar_protocolo_iatf_realizado,
    _marcar_protocolo_inducao_realizado,
    _marcar_protocolo_custom_realizado,
    _marcar_lida_realizado,
    _baixar_protocolo_sanitario,
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


def _filtro_fazenda(query, coluna, fazenda_id: int | None):
    """Restringe `query` à fazenda atual.

    Filtro ESTRITO desde o PR claude/fazenda-id-raiz — até lá tolerava
    `coluna IS NULL` (lançamento feito antes de a rota correspondente
    carimbar fazenda_id, ou movimento de estoque gerado por um desses
    lançamentos legados): um `==` estrito fazia essas linhas antigas
    sumirem da listagem OU — pior, quando a mesma tolerância faltava no
    detalhe/nas ações — aparecerem na lista e dar 404 ao abrir (era
    exatamente esta assimetria que causava "Lançamento de protocolo não
    encontrado" ao clicar num protocolo legado que a Central mostrava).
    Voltou a estrito só depois de dois reforços: (1) toda rota de escrita
    passou a recusar gravar fazenda_id nulo (fazenda.auth::
    get_fazenda_id_escrita) e (2) a migração 029227481e9e preencheu o
    histórico que já tinha ficado nulo — sem isso, este filtro faria o
    dado legado desaparecer de novo.
    """
    if fazenda_id is None:
        return query
    return query.where(coluna == fazenda_id)


def _linhas_iatf(session: Session, fazenda_id: int | None) -> list[dict]:
    query = _filtro_fazenda(select(ProtocoloIatfLancamento), ProtocoloIatfLancamento.fazenda_id, fazenda_id)
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
    query = _filtro_fazenda(select(ProtocoloInducaoLancamento), ProtocoloInducaoLancamento.fazenda_id, fazenda_id)
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
    query = _filtro_fazenda(select(ProtocoloCustomizadoLancamento), ProtocoloCustomizadoLancamento.fazenda_id, fazenda_id)
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


def _linhas_lida(session: Session, fazenda_id: int | None) -> list[dict]:
    query = _filtro_fazenda(select(LidaLancamento), LidaLancamento.fazenda_id, fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(LidaAplicacao).where(LidaAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[LidaAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)
    linhas = []
    for l in lancamentos:
        aps = por_lanc.get(l.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            # "lida" não é produtivo/reprodutivo/sanitário — tipo próprio, de
            # propósito fora dos 3 filtros existentes (é sempre trabalho geral
            # da fazenda, nunca protocolo de animal).
            tipo="lida", origem="lida", origem_id=l.id, nome=l.nome_protocolo,
            data_inicio=l.data_inicio, data_fim=max(datas) if datas else l.data_inicio,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len({a.numero_matriz for a in aps if a.numero_matriz}),
            ativo=l.ativo,
            encerrado_em=l.encerrado_em, encerrado_motivo=l.encerrado_motivo,
        ))
    return linhas


def _linhas_sanitario(session: Session, fazenda_id: int | None) -> list[dict]:
    """Mesmo formato de `_linhas_iatf`/`_linhas_inducao` — só precisa de um
    passo extra porque o Sanitário tem uma camada a mais entre o cabeçalho
    (ProtocoloSanitarioLote) e a aplicação: um ProtocoloSanitarioLancamento
    POR ANIMAL, que as outras 3 famílias não têm (a aplicação delas já
    carrega `numero_matriz` direto)."""
    query = _filtro_fazenda(select(ProtocoloSanitarioLote), ProtocoloSanitarioLote.fazenda_id, fazenda_id)
    lotes = session.exec(query).all()
    if not lotes:
        return []
    lote_ids = [lo.id for lo in lotes]
    lancamentos = session.exec(
        select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.lote_id.in_(lote_ids))
    ).all()
    lancamento_ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloSanitarioAplicacao).where(ProtocoloSanitarioAplicacao.lancamento_id.in_(lancamento_ids))
    ).all()

    animais_por_lote: dict[int, set[str]] = defaultdict(set)
    for l in lancamentos:
        if l.lote_id is not None:
            animais_por_lote[l.lote_id].add(l.numero_matriz)
    lancamento_para_lote = {l.id: l.lote_id for l in lancamentos}
    aps_por_lote: dict[int, list[ProtocoloSanitarioAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        lote_id = lancamento_para_lote.get(a.lancamento_id)
        if lote_id is not None:
            aps_por_lote[lote_id].append(a)

    linhas = []
    for lo in lotes:
        aps = aps_por_lote.get(lo.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            tipo="sanitario", origem="sanitario", origem_id=lo.id, nome=lo.nome_protocolo,
            data_inicio=lo.data_inicio, data_fim=max(datas) if datas else lo.data_inicio,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len(animais_por_lote.get(lo.id, set())),
            ativo=lo.ativo,
            encerrado_em=lo.encerrado_em, encerrado_motivo=lo.encerrado_motivo,
        ))
    return linhas


def _todas_as_linhas(session: Session, fazenda_id: int | None) -> list[dict]:
    return (
        _linhas_iatf(session, fazenda_id)
        + _linhas_inducao(session, fazenda_id)
        + _linhas_sanitario(session, fazenda_id)
        + _linhas_customizado(session, fazenda_id)
        + _linhas_lida(session, fazenda_id)
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

# Origens com cabeçalho de lote próprio — todas as 5 famílias, desde que
# Sanitário ganhou o seu (ProtocoloSanitarioLote). Cada uma tem baixa/desfazer/
# cancelar pela Central; Sanitário precisa de um passo extra em alguns pontos
# (`_aplicacoes_do_lancamento`, `desfazer_aplicacao`, `cancelar`) por causa da
# camada extra ProtocoloSanitarioLancamento (um por animal) que as outras não
# têm — ver comentário em `_linhas_sanitario`.
_ORIGENS_COM_ACAO = ("iatf", "inducao", "customizado", "lida", "sanitario")


class BaixaProtocoloIn(BaseModel):
    dia: int
    # Sem `animais`, dá baixa no dia inteiro; com, só nesse subconjunto.
    animais: list[str] | None = None
    # Dia em que a aplicação REALMENTE aconteceu. Sem ele, hoje.
    data_realizacao: date | None = None
    medicamentos: list[MedicamentoIatfIn] | None = None


class EncerrarProtocoloIn(BaseModel):
    motivo: str | None = None


class RenomearProtocoloIn(BaseModel):
    nome: str


class EditarLancamentoProtocoloIn(BaseModel):
    """G16 — edição do cabeçalho do lançamento. Todos os campos são opcionais
    (só o que veio na requisição é alterado — `exclude_unset`)."""
    data_inicio: date | None = None
    responsavel: str | None = None
    observacao: str | None = None
    nome: str | None = None


class DesfazerAplicacaoIn(BaseModel):
    dia: int
    numero_matriz: str


def _frasco_da_ultima_baixa_protocolo(session: Session, origem_tipo: str, origem_id: int) -> tuple[int | None, int | None]:
    """(`estoque_id`, `lote_id`) que a baixa mais recente desta origem/id de
    fato usou — lido do próprio rastro em MovimentoEstoque (mesmo padrão de
    `sanidade.py::_frasco_da_ultima_aplicacao`), pra devolver o estorno no
    MESMO frasco/lote que a baixa consumiu, nunca em outro escolhido por
    acaso pelo FIFO/nome na hora de desfazer."""
    mov = session.exec(
        select(MovimentoEstoque).where(
            MovimentoEstoque.origem_tipo == origem_tipo, MovimentoEstoque.origem_id == origem_id,
            MovimentoEstoque.movimento == "Aplicação",
        ).order_by(MovimentoEstoque.id.desc())
    ).first()
    return (mov.estoque_id, mov.lote_id) if mov else (None, None)


def _lancamento_ou_404(session: Session, origem: str, origem_id: int, fazenda_id: int | None):
    if origem not in _ORIGENS_COM_ACAO:
        raise HTTPException(
            status_code=400,
            detail="Só protocolos de IATF, indução, customizado, lida e sanitário têm baixa pela Central.",
        )
    modelo = {
        "iatf": ProtocoloIatfLancamento,
        "inducao": ProtocoloInducaoLancamento,
        "customizado": ProtocoloCustomizadoLancamento,
        "lida": LidaLancamento,
        "sanitario": ProtocoloSanitarioLote,
    }[origem]
    lancamento = session.get(modelo, origem_id)
    # Estrito desde o PR claude/fazenda-id-raiz (ver `_filtro_fazenda` acima)
    # — `fazenda_id is not None` continua cobrindo o caso de leitura sem
    # fazenda resolvida (token legado/sem contexto multi-fazenda), que não
    # filtra nada, igual ao resto do sistema.
    if not lancamento or (fazenda_id is not None and lancamento.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento de protocolo não encontrado")
    return lancamento


def _aplicacoes_do_lancamento(session: Session, origem: str, origem_id: int) -> list:
    if origem == "sanitario":
        # `origem_id` aqui é o ProtocoloSanitarioLote.id, não o
        # ProtocoloSanitarioLancamento.id — precisa resolver os lançamentos
        # (um por animal) do lote antes de buscar as aplicações deles. Como
        # ProtocoloSanitarioAplicacao já carrega `.dia`/`.numero_matriz`
        # (denormalizados, ver o modelo), o resto do código genérico abaixo
        # (detalhe, dar_baixa, desfazer_aplicacao, cancelar) não precisa saber
        # dessa camada extra.
        lancamento_ids = session.exec(
            select(ProtocoloSanitarioLancamento.id).where(ProtocoloSanitarioLancamento.lote_id == origem_id)
        ).all()
        return list(session.exec(
            select(ProtocoloSanitarioAplicacao).where(ProtocoloSanitarioAplicacao.lancamento_id.in_(lancamento_ids))
        ).all())
    modelo = {
        "iatf": ProtocoloIatfAplicacao,
        "inducao": ProtocoloInducaoAplicacao,
        "customizado": ProtocoloCustomizadoAplicacao,
        "lida": LidaAplicacao,
    }[origem]
    return list(session.exec(
        select(modelo).where(modelo.lancamento_id == origem_id)
    ).all())


@router.get("/{origem}/{origem_id}")
def detalhe(
    origem: str, origem_id: int, incluir_sem_estoque: bool = False,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """A grade animal × dia de um lançamento: uma linha por animal, uma coluna
    por dia do cronograma, cada célula com o estado daquela aplicação."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)
    aps = _aplicacoes_do_lancamento(session, origem, origem_id)
    hoje = date.today()

    # `dia` do customizado e da lida é absoluto (pode começar em D1); os
    # outros já são relativos ao D0. O rótulo sempre sai relativo ao início
    # do cronograma. Sanitário também é absoluto (D0 ou D1 conforme o molde
    # ProtocoloSanitario cadastrado), mas o `dia_inicial` mora no MOLDE, não
    # no lote (ProtocoloSanitarioLote não repete esse campo, igual à Indução
    # — ver `_dia_inicial_lancamento`).
    if origem in ("customizado", "lida"):
        base = getattr(lancamento, "dia_inicial", 0)
    elif origem == "sanitario":
        molde = session.get(ProtocoloSanitario, lancamento.protocolo_id)
        base = molde.dia_inicial if molde else 0
    else:
        base = 0

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

    # IATF e Indução: os hormônios/medicamentos cadastrados por dia + as
    # opções de frasco em estoque do mesmo princípio ativo — mesmo campo
    # "qual medicamento/frasco?" que a Agenda já mostra (ver
    # fazenda.rules.estoque_baixa.opcoes_medicamento). `incluir_sem_estoque`
    # expande as opções para toda marca comercial do princípio ativo, mesmo
    # sem frasco em Estoque — liberdade de flagar o que realmente foi usado.
    if origem == "iatf":
        hormonios_por_dia: dict[int, list] = defaultdict(list)
        for h in session.exec(
            select(ProtocoloIatfHormonio).where(ProtocoloIatfHormonio.lancamento_id == origem_id)
        ).all():
            hormonios_por_dia[h.dia].append(h)
        for d in dias.values():
            d["hormonios"] = [
                {
                    "produto": h.produto, "dose": h.dose, "unidade": h.unidade, "via": h.via,
                    "opcoes": estoque_baixa.opcoes_medicamento(
                        session, fazenda_id=fazenda_id, produto=h.produto,
                        incluir_sem_estoque=incluir_sem_estoque,
                    )[1],
                }
                for h in hormonios_por_dia.get(d["dia"], [])
            ]
    elif origem == "inducao":
        medicamentos_por_dia: dict[int, list] = defaultdict(list)
        for m in session.exec(
            select(ProtocoloInducaoMedicamento).where(ProtocoloInducaoMedicamento.lancamento_id == origem_id)
        ).all():
            medicamentos_por_dia[m.dia].append(m)
        for d in dias.values():
            d["hormonios"] = [
                {
                    "produto": m.produto, "dose": m.dose, "unidade": m.unidade, "via": m.via,
                    "opcoes": estoque_baixa.opcoes_medicamento(
                        session, fazenda_id=fazenda_id, produto=m.produto,
                        incluir_sem_estoque=incluir_sem_estoque,
                    )[1],
                }
                for m in medicamentos_por_dia.get(d["dia"], [])
            ]
    elif origem == "sanitario":
        # Sanitário: um único produto por dia (a etapa do molde cadastrado) —
        # diferente de IATF/Indução, que podem ter vários hormônios no mesmo
        # dia. `ProtocoloSanitarioAplicacao.produto` pode ter fixado o
        # medicamento no lançamento (etapa por princípio ativo/classificação,
        # ver ProtocoloLancamentoIn.escolhas_medicamento); senão usa o produto
        # já cadastrado na própria etapa. Como o produto vale pro dia inteiro
        # (todo animal daquele dia usa a mesma etapa), uma aplicação
        # qualquer do dia já basta pra descobrir etapa/produto.
        etapa_por_dia: dict[int, ProtocoloSanitarioEtapa] = {}
        produto_por_dia: dict[int, str] = {}
        for a in aps:
            if a.dia in etapa_por_dia:
                continue
            etapa = session.get(ProtocoloSanitarioEtapa, a.etapa_id)
            if etapa:
                etapa_por_dia[a.dia] = etapa
                produto_por_dia[a.dia] = a.produto or etapa.produto
        for d in dias.values():
            etapa = etapa_por_dia.get(d["dia"])
            if not etapa:
                d["hormonios"] = []
                continue
            produto = produto_por_dia[d["dia"]]
            opcoes = estoque_baixa.opcoes_medicamento(
                session, fazenda_id=fazenda_id, produto=produto, incluir_sem_estoque=incluir_sem_estoque,
            )[1]
            # "de qual lote/frasco de COMPRA?" (Fase G) — um nível abaixo do
            # frasco (estoque_id), mesmo seletor de 2 níveis que a aplicação
            # avulsa de Sanidade já tem (ver FormSanidade.tsx). Só listado
            # quando o frasco tem lote aberto — item sem lote nenhum não
            # ganha essa chave, e o frontend trata como "sem escolha de lote".
            for op in opcoes:
                if op.get("estoque_id"):
                    op["lotes"] = [
                        {
                            "id": l.id, "numero_lote": l.numero_lote,
                            "data_compra": l.data_compra, "quantidade_restante": l.quantidade_restante,
                        }
                        for l in estoque_baixa.lotes_disponiveis(session, estoque_id=op["estoque_id"])
                    ]
            d["hormonios"] = [{"produto": produto, "dose": etapa.dosagem, "unidade": etapa.unidade, "via": etapa.via, "opcoes": opcoes}]

    total = len(aps)
    feitas = sum(1 for a in aps if a.realizada)
    return {
        "origem": origem, "origem_id": origem_id,
        "nome": lancamento.nome_protocolo,
        "data_inicio": getattr(lancamento, "data_d0", None) or getattr(lancamento, "data_inicio", None),
        "responsavel": lancamento.responsavel,
        # G16 — a Central só editava o nome antes; agora responsavel/observacao/
        # data_inicio também. `observacao` não estava no dict aqui até então —
        # sem ela, o bloco "Editar" (frontend) não teria como pré-preencher o
        # campo.
        "observacao": lancamento.observacao,
        "encerrado_em": lancamento.encerrado_em, "encerrado_motivo": lancamento.encerrado_motivo,
        "ativo": getattr(lancamento, "ativo", True),
        "etapas_total": total, "etapas_realizadas": feitas,
        "etapas_atrasadas": sum(
            1 for a in aps if not a.realizada and a.data_prevista < hoje
        ),
        "dias": sorted(dias.values(), key=lambda d: d["dia"]),
        "animais": sorted(animais.values(), key=lambda l: chave_numero(l["numero_matriz"])),
    }


@router.patch("/{origem}/{origem_id}/renomear")
def renomear(
    origem: str, origem_id: int, dados: RenomearProtocoloIn,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Renomeia o `nome_protocolo` do lançamento — o título mostrado no
    detalhe e nas listas de Acompanhamento/Histórico."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)
    nome = (dados.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Informe um nome para o protocolo.")
    lancamento.nome_protocolo = nome
    session.add(lancamento)
    session.commit()
    return {"ok": True, "nome": lancamento.nome_protocolo}


def _dia_inicial_lancamento(session: Session, origem: str, lancamento) -> int:
    """O `dia_inicial` que `gerar_nome_lancamento` usa para montar o nome
    automático — depende de onde ele mora em cada origem (ver comentário no
    topo de `detalhe()`): sempre 0 no IATF; vem do MOLDE cadastrado na
    indução (não é campo do lançamento); é um campo próprio do lançamento no
    customizado e na lida."""
    if origem == "iatf":
        return 0
    if origem == "inducao":
        molde = session.get(ProtocoloInducaoLactacao, lancamento.protocolo_id)
        return molde.dia_inicial if molde else 0
    if origem == "sanitario":
        molde = session.get(ProtocoloSanitario, lancamento.protocolo_id)
        return molde.dia_inicial if molde else 0
    return lancamento.dia_inicial


@router.put("/{origem}/{origem_id}")
def editar_lancamento(
    origem: str, origem_id: int, dados: EditarLancamentoProtocoloIn,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """G16 — edita data de início/responsável/observação/nome de um
    lançamento (as 4 origens com ação: iatf, inducao, customizado, lida).

    Mudar `data_inicio` é a parte delicada: bloqueia se alguma etapa já foi
    aplicada (mudar a data desalinharia o que já foi feito de verdade) e,
    quando permitido, desloca TODAS as `data_prevista` das aplicações pelo
    mesmo delta — a Agenda lê `data_prevista`, então o evento também muda de
    dia lá. `ProtocoloIatfHormonio`/`ProtocoloInducaoMedicamento` guardam
    `dia` relativo (não data), então não precisam de ajuste; no
    customizado/lida o `dia` também é relativo ao `dia_inicial` gravado no
    lançamento — só a `data_prevista` (absoluta) se desloca.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)

    if lancamento.encerrado_em is not None or getattr(lancamento, "ativo", True) is False:
        raise HTTPException(
            status_code=400,
            detail="Protocolo encerrado/cancelado — reabra antes de editar.",
        )

    dados_definidos = dados.model_dump(exclude_unset=True)
    avisos: list[str] = []

    if "responsavel" in dados_definidos:
        lancamento.responsavel = dados.responsavel
    if "observacao" in dados_definidos:
        lancamento.observacao = dados.observacao
    if "nome" in dados_definidos:
        nome = (dados.nome or "").strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Informe um nome para o protocolo.")
        lancamento.nome_protocolo = nome

    if "data_inicio" in dados_definidos and dados.data_inicio is not None:
        campo_data = "data_d0" if origem in ("iatf", "inducao") else "data_inicio"
        data_atual = getattr(lancamento, campo_data)
        nova_data = dados.data_inicio
        if nova_data != data_atual:
            aps = _aplicacoes_do_lancamento(session, origem, origem_id)
            if any(a.realizada for a in aps):
                raise HTTPException(
                    status_code=400,
                    detail="Este protocolo já tem etapa(s) aplicada(s) — mudar a data de início desalinharia "
                           "as datas do que já foi feito. Desfaça as aplicações antes ou cancele o lançamento.",
                )
            delta = nova_data - data_atual
            for ap in aps:
                ap.data_prevista = ap.data_prevista + delta
                session.add(ap)
            if origem == "sanitario":
                # Camada extra que só o Sanitário tem: cada animal do lote
                # também guarda seu próprio `data_inicio`
                # (ProtocoloSanitarioLancamento) — sem este ajuste, ficaria
                # dessincronizado do `data_inicio` do lote recém-atualizado.
                for l in session.exec(
                    select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.lote_id == origem_id)
                ).all():
                    l.data_inicio = l.data_inicio + delta
                    session.add(l)
            setattr(lancamento, campo_data, nova_data)

            # Regrava nome_protocolo com gerar_nome_lancamento SOMENTE se o
            # nome atual ainda for exatamente o auto-gerado para a data
            # ANTIGA (nome_curto tira o sufixo de datas, se houver, e
            # comparamos o resultado reconstruído contra o nome gravado) — se
            # o usuário renomeou à mão, ou o nome nunca teve o sufixo (nome
            # legado, anterior a esta nomenclatura), preserva como está. Não
            # regrava se `nome` também veio nesta mesma requisição — quem
            # editou os dois de propósito quer o nome que mandou, não um
            # recalculado por cima.
            if "nome" not in dados_definidos:
                nome_atual = lancamento.nome_protocolo
                dia_inicial = _dia_inicial_lancamento(session, origem, lancamento)
                dia_final = max((a.dia for a in aps), default=dia_inicial)
                nome_base = nome_curto(nome_atual)
                nome_autogerado_antigo = gerar_nome_lancamento(nome_base, data_atual, dia_inicial, dia_final)
                if nome_atual == nome_autogerado_antigo:
                    lancamento.nome_protocolo = gerar_nome_lancamento(nome_base, nova_data, dia_inicial, dia_final)

            if nova_data > date.today():
                avisos.append("A nova data de início é no futuro.")

    session.add(lancamento)
    session.commit()
    resposta = detalhe(origem, origem_id, False, session, fazenda_id)
    resposta["avisos"] = avisos
    return resposta


@router.post("/{origem}/{origem_id}/baixa")
def dar_baixa(
    origem: str, origem_id: int, dados: BaixaProtocoloIn,
    session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
    user: Usuario = Depends(get_current_user),
) -> dict:
    """Dá baixa num dia do protocolo — o dia inteiro ou só alguns animais —
    com a data REAL da aplicação. Reaproveita exatamente as mesmas funções que
    a Agenda usa (Sanidade gerada, baixa de estoque com rastreio); a diferença
    é que aqui a data não é obrigatoriamente hoje e o dia pode já ter passado.
    """
    usuario_id = usuario_id_seguro(user)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)
    if lancamento.encerrado_em:
        raise HTTPException(status_code=400, detail="Protocolo encerrado — reabra antes de dar baixa.")
    if dados.data_realizacao and dados.data_realizacao > date.today():
        raise HTTPException(status_code=400, detail="A data da aplicação não pode ser no futuro.")

    # O dia precisa existir NESTE lançamento. Sem esta checagem, as origens
    # `inducao`/`customizado`/`lida` caíam direto em `_marcar_*_realizado`,
    # que filtra as aplicações por `dia`, não encontrava nenhuma e devolvia
    # {"ok": True, "avisos": []} com HTTP 200 — como se a baixa tivesse
    # funcionado, sem gravar nada. Antes só o ramo `iatf` checava (ele já
    # precisava da aplicação em mãos para montar a chave do evento, que é
    # por data prevista); agora vale para as quatro.
    alvo = next(
        (a for a in _aplicacoes_do_lancamento(session, origem, origem_id) if a.dia == dados.dia),
        None,
    )
    if alvo is None:
        raise HTTPException(status_code=404, detail="Este dia não existe neste lançamento.")

    if origem == "iatf":
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
    elif origem == "lida":
        avisos = _marcar_lida_realizado(
            session, f"lida_{origem_id}_{dados.dia}",
            dados.animais, data_realizacao=dados.data_realizacao, fazenda_id=fazenda_id, usuario_id=usuario_id,
        )
    elif origem == "sanitario":
        # Sem `_marcar_protocolo_sanitario_realizado` próprio: cada aplicação
        # sanitária já é confirmável uma a uma pela Agenda
        # (`_baixar_protocolo_sanitario`, chaveada por `protocolo_sanitario_{id}`)
        # — aqui só filtra as do dia/lote pedido (e do subconjunto de animais,
        # se veio) e chama a mesma função uma vez por aplicação pendente,
        # repassando a data retroativa.
        # "De qual frasco/lote?" (Fase G, 01/09/2026): um só par
        # estoque_id/lote_id pro dia inteiro — a etapa sanitária tem um único
        # produto por dia, então não há por que pedir a escolha por animal
        # (mesmo espírito de `medicamentos[0]` valendo pro grupo inteiro no
        # IATF). Sem escolha, cai no comportamento de sempre: resolve pelo
        # nome do produto e baixa em FIFO.
        escolha = dados.medicamentos[0] if dados.medicamentos else None
        avisos = []
        pendentes = [
            a for a in _aplicacoes_do_lancamento(session, origem, origem_id)
            if a.dia == dados.dia and not a.realizada and (not dados.animais or a.numero_matriz in dados.animais)
        ]
        for ap in pendentes:
            avisos.extend(_baixar_protocolo_sanitario(
                session, f"protocolo_sanitario_{ap.id}", fazenda_id=fazenda_id, usuario_id=usuario_id,
                data_realizacao=dados.data_realizacao,
                estoque_id=escolha.estoque_id if escolha else None,
                lote_id=escolha.lote_id if escolha else None,
            ))
    else:
        _marcar_protocolo_custom_realizado(
            session, f"{PREFIXO_PROTOCOLO_CUSTOM}{origem_id}_{dados.dia}",
            dados.animais, data_realizacao=dados.data_realizacao, fazenda_id=fazenda_id,
        )
        avisos = []
    return {"ok": True, "avisos": avisos}


@router.delete("/{origem}/{origem_id}/baixa")
def desfazer_aplicacao(
    origem: str, origem_id: int, dados: DesfazerAplicacaoIn,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    user: Usuario = Depends(get_current_user),
) -> dict:
    """Desfaz a aplicação de UM animal em UM dia — diferente de cancelar (que
    desfaz o lançamento inteiro). Volta `realizada=False`/`data_realizacao=None`
    só naquela célula da grade.

    Estoque: só estorna para origem=="iatf" — é o único caso relatado (o
    usuário quer desfazer uma aplicação IATF puxada errado, sem cancelar o
    lote inteiro). Indução/customizado/lida ficam de fora por ora: não é
    esquecimento, é escopo — cada um tem uma forma diferente de registrar o
    medicamento aplicado (indução por lançamento/dia, customizado e lida às
    vezes sem medicamento nenhum) e estornar direito exigiria replicar a
    mesma lógica de "uma dose, não a batelada" três vezes sem um pedido
    concreto ainda para isso.

    A Sanidade gerada permanece — mesma filosofia de `cancelar()`: é o
    registro clínico de que o produto entrou no animal, e desfazer a baixa
    do protocolo não reescreve a ficha.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    usuario_id = usuario_id_seguro(user)
    lancamento = _lancamento_ou_404(session, origem, origem_id, fazenda_id)

    if origem == "sanitario":
        # `_aplicacoes_do_lancamento` já resolve a camada extra (lote ->
        # lançamentos por animal -> aplicações) e devolve objetos com
        # `.dia`/`.numero_matriz` reais — dá pra filtrar em Python em vez de
        # repetir a query de 2 passos aqui.
        aplicacao = next(
            (a for a in _aplicacoes_do_lancamento(session, origem, origem_id)
             if a.dia == dados.dia and a.numero_matriz == dados.numero_matriz),
            None,
        )
    else:
        modelo = {
            "iatf": ProtocoloIatfAplicacao,
            "inducao": ProtocoloInducaoAplicacao,
            "customizado": ProtocoloCustomizadoAplicacao,
            "lida": LidaAplicacao,
        }[origem]
        aplicacao = session.exec(
            select(modelo).where(
                modelo.lancamento_id == origem_id,
                modelo.dia == dados.dia,
                modelo.numero_matriz == dados.numero_matriz,
            )
        ).first()
    if aplicacao is None:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada para este animal/dia.")
    if not aplicacao.realizada:
        raise HTTPException(status_code=400, detail="Esta aplicação já está pendente — nada a desfazer.")

    aplicacao.realizada = False
    aplicacao.data_realizacao = None
    session.add(aplicacao)

    avisos: list[str] = []
    if origem == "sanitario":
        etapa = session.get(ProtocoloSanitarioEtapa, aplicacao.etapa_id)
        if etapa and etapa.dosagem:
            produto = aplicacao.produto or etapa.produto
            # Devolve no MESMO frasco/lote que a baixa original consumiu —
            # lido de volta do rastro em MovimentoEstoque (ver
            # `_frasco_da_ultima_baixa_protocolo`), nunca resolvido de novo
            # só pelo nome (que cairia no frasco "errado" se houver mais de
            # um do mesmo produto, mesmo bug que A-13 já corrigiu em Sanidade).
            estoque_id_usado, lote_id_usado = _frasco_da_ultima_baixa_protocolo(
                session, "protocolo_sanitario", aplicacao.id,
            )
            item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=produto, estoque_id=estoque_id_usado)
            avisos.extend(estoque_baixa.devolver(
                session, item=item, quantidade=etapa.dosagem, unidade=etapa.unidade, data=date.today(),
                fazenda_id=fazenda_id, usuario_id=usuario_id, produto=produto,
                observacao=f"Estorno — aplicação desfeita: {dados.numero_matriz}, D{dados.dia}",
                # Mesma convenção de origem_tipo/origem_id que
                # `_baixar_protocolo_sanitario` usa ao dar a baixa original —
                # rastreada por APLICAÇÃO, não pelo lote (ver
                # ProtocoloSanitarioAplicacao no modelo e exclusoes.py).
                origem_tipo="protocolo_sanitario", origem_id=aplicacao.id, lote_id=lote_id_usado,
            ))
    elif origem == "iatf":
        hoje = date.today()
        for h in session.exec(
            select(ProtocoloIatfHormonio).where(
                ProtocoloIatfHormonio.lancamento_id == origem_id,
                ProtocoloIatfHormonio.dia == dados.dia,
            )
        ).all():
            if not h.dose:
                continue
            item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=h.produto)
            avisos.extend(estoque_baixa.devolver(
                session, item=item, quantidade=h.dose, unidade=h.unidade, data=hoje,
                fazenda_id=fazenda_id, usuario_id=usuario_id, produto=h.produto,
                observacao=f"Estorno — aplicação desfeita: {dados.numero_matriz}, D{dados.dia}",
                origem_tipo="iatf", origem_id=origem_id,
            ))

    session.commit()
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

    # Cancelar é IRREPETÍVEL. O estorno abaixo procura os MovimentoEstoque de
    # movimento "Aplicação" desta origem e devolve a quantidade de cada um —
    # mas o estorno grava uma linha NOVA ("Entrada de ajuste"), sem marcar a
    # "Aplicação" original como já estornada. Sem esta guarda, cancelar duas
    # vezes reencontrava as MESMAS aplicações e devolvia o estoque de novo,
    # inflando o saldo (reproduzido: 20 L -> baixa 19,5 L -> cancelar 20 L
    # (certo) -> cancelar de novo 20,5 L). Mesmo espírito da guarda que
    # `desfazer_aplicacao` já tinha.
    if not getattr(lancamento, "ativo", True):
        raise HTTPException(status_code=400, detail="Este protocolo já está cancelado.")

    # Desfaz as aplicações — o lançamento inteiro passa a valer como não feito.
    for ap in _aplicacoes_do_lancamento(session, origem, origem_id):
        if ap.realizada:
            ap.realizada = False
            ap.data_realizacao = None
            session.add(ap)

    # Estorna cada saída de estoque desta origem. Só as SAÍDAS: uma devolução
    # anterior (entrada) não pode ser estornada de novo, ou o saldo inflaria.
    #
    # Sanitário é o único caso em que o rastro em MovimentoEstoque não usa
    # (origem_tipo=origem, origem_id=origem_id) — `_baixar_protocolo_sanitario`
    # grava origem_tipo="protocolo_sanitario" com origem_id = APLICAÇÃO (não o
    # lote), mesma convenção que exclusoes.py já usa para essa família. Por
    # isso o filtro é por uma LISTA de origem_id (uma aplicação por
    # animal/dia), não um valor só.
    avisos: list[str] = []
    hoje = date.today()
    if origem == "sanitario":
        aplicacao_ids = [a.id for a in _aplicacoes_do_lancamento(session, origem, origem_id)]
        query_mov = select(MovimentoEstoque).where(
            MovimentoEstoque.origem_tipo == "protocolo_sanitario",
            MovimentoEstoque.origem_id.in_(aplicacao_ids),
            MovimentoEstoque.movimento == "Aplicação",
        )
    else:
        query_mov = select(MovimentoEstoque).where(
            MovimentoEstoque.origem_tipo == origem,
            MovimentoEstoque.origem_id == origem_id,
            MovimentoEstoque.movimento == "Aplicação",
        )
    query_mov = _filtro_fazenda(query_mov, MovimentoEstoque.fazenda_id, fazenda_id)
    for mov in session.exec(query_mov).all():
        item = session.get(Estoque, mov.estoque_id) if mov.estoque_id else None
        if item is None:
            item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=mov.nome_item)
        avisos.extend(estoque_baixa.devolver(
            session, item=item, quantidade=mov.quantidade, unidade=mov.unidade, data=hoje,
            fazenda_id=fazenda_id, usuario_id=usuario_id, produto=mov.nome_item,
            observacao=f"Estorno — protocolo cancelado ({lancamento.nome_protocolo})",
            origem_tipo=mov.origem_tipo, origem_id=mov.origem_id, lote_id=mov.lote_id,
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
