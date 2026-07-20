"""
Router de sanidade — histórico de medicamentos aplicados nos animais e
lançamento de aplicação (um ou mais produtos, por animal ou por lote).
Endpoint: GET /sanidade/aplicacoes, POST /sanidade/aplicacoes
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import (
    Animal, AplicacaoAgendada, CalendarioSanitario, ColostragemBezerra, Doenca, Estoque, EventoRealizado,
    EventoSanitario, ExameDefinicao, ExameResultado, MovimentoEstoque,
    Parto, PrincipioAtivo, ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento, QualidadeLeite, Sanidade, Usuario,
)
from fazenda.api.routers.baixas import ADescartarIn, marcar_a_descartar
from fazenda.api.routers.cadastro import GATILHOS_EVENTO
from fazenda.rules.auditoria import mapa_usuarios, usuario_id_seguro
from fazenda.rules.calendario_sanitario import proxima_ocorrencia
from fazenda.rules.eventos_sanitarios import ROTULOS_GATILHO, _datas_gatilho
from fazenda.rules.farmacia import pode_baixar_estoque
from fazenda.rules.unidades import pode_dar_baixa_direta, unidades_compativeis

RESULTADOS_EXAME = ["positivo", "negativo", "indefinido"]

TETOS_VALIDOS = ["AE", "AD", "PD", "PE"]
CLASSIFICACOES_MASTITE = ["clinica", "subclinica", "ambiental"]
GRAUS_MASTITE = [1, 2, 3]
RESULTADOS_CMT = ["-", "+", "++", "+++"]
# Agentes (patógenos) de mastite mais comuns — lista padrão sugerida; o usuário
# pode informar outro no lançamento.
AGENTES_MASTITE = [
    "Staphylococcus aureus", "Streptococcus agalactiae", "Mycoplasma bovis", "Negativo",
    "Coliformes", "Streptococcus uberis", "Streptococcus dysgalactiae", "Escherichia coli",
    "Klebsiella pneumoniae", "Enterobacter aerogenes", "Serratia spp.", "Pseudomonas spp.",
    "Proteus spp.", "Arcanobacterium pyogenes", "Nocardia spp.", "Bacillus spp.",
    "Fungos", "Leveduras", "Algas",
]
# Intervalo abaixo do qual um novo caso no mesmo teto é considerado recidiva
# (indica trocar para o próximo tratamento).
DIAS_RECIDIVA_MASTITE = 20

router = APIRouter(prefix="/sanidade", tags=["sanidade"])

FREQUENCIAS = ["dias", "meses", "anos"]


@router.get("/aplicacoes")
def listar_aplicacoes(session: Session = Depends(get_session)) -> dict:
    """Aplicações achatadas para o dashboard interativo (filtra no cliente)."""
    partos_por_numero: dict[str, int] = {}
    for p in session.exec(select(Parto)).all():
        partos_por_numero[p.numero_matriz] = partos_por_numero.get(p.numero_matriz, 0) + 1
    # Lote/categoria ATUAIS do animal (a Sanidade não guarda o lote histórico de
    # quando o produto foi aplicado — mesma limitação já aceita para ordem_parto
    # acima, que também reflete o estado de hoje, não o de quando aconteceu).
    animais_por_numero = {a.numero: a for a in session.exec(select(Animal)).all()}
    sanidades = session.exec(select(Sanidade)).all()
    nomes = mapa_usuarios(session, {s.usuario_id for s in sanidades})
    registros = []
    for s in sanidades:
        d = s.data_aplicacao
        animal = animais_por_numero.get(s.numero_matriz)
        registros.append({
            "id": s.id,
            "numero": s.numero_matriz,
            "raca": s.raca or "(sem raça)",
            "produto": s.produto,
            "categoria": s.categoria or "Outros",
            "dose": s.dose,
            "unidade": s.unidade,
            "via": s.via,
            "responsavel": s.responsavel,
            "atividade": s.atividade,
            "obs": s.obs,
            "ordem_parto": partos_por_numero.get(s.numero_matriz) or None,
            "lote": s.lote or (animal.grupo_primario if animal else None),
            "categoria_animal": animal.categoria_abrev or animal.categoria_completa if animal else None,
            "natureza": s.natureza or "curativo",
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "mes": f"{d.year}-{d.month:02d}" if d else None,
            "usuario_nome": nomes.get(s.usuario_id),
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
    # "Qual frasco/apresentação você está usando?" — quando há mais de uma
    # apresentação (marca/tamanho) do mesmo princípio no estoque, o front manda
    # o id do item escolhido para abater do recipiente certo.
    estoque_id: int | None = None


class AplicacaoIn(BaseModel):
    data_aplicacao: date
    animais: list[str]
    itens: list[ItemAplicacaoIn]
    responsavel: str | None = None
    observacao: str | None = None
    # "Já foi aplicado?" — quando False (ou a data é futura) NADA é baixado do
    # estoque: a aplicação fica programada na Agenda até ser confirmada.
    aplicado: bool = True
    # "curativo" | "preventivo" — ver Sanidade.natureza.
    natureza: str = "curativo"


@router.post("/aplicacoes")
def registrar_aplicacao(
    dados: AplicacaoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal ou lote")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Adicione ao menos um produto")

    # Regra de data: aplicação no futuro NUNCA baixa estoque (não aconteceu
    # ainda). Só materializa quando marcada como aplicada E a data não é futura.
    materializar = dados.aplicado and dados.data_aplicacao <= date.today()

    if not materializar:
        agendadas = 0
        for item in dados.itens:
            for numero in dados.animais:
                session.add(AplicacaoAgendada(
                    numero_matriz=numero, data=dados.data_aplicacao, produto=item.produto,
                    dose=item.quantidade, unidade=item.unidade, via=item.via,
                    responsavel=dados.responsavel, observacao=dados.observacao,
                    usuario_id=usuario_id_seguro(user), natureza=dados.natureza,
                ))
                agendadas += 1
        session.commit()
        return {"criados": 0, "agendadas": agendadas, "avisos": [], "programado": True}

    criados = 0
    avisos: list[str] = []
    for item in dados.itens:
        # Se o usuário escolheu o frasco/apresentação específico ("qual frasco?"),
        # abate dele; senão, cai no item pelo nome do produto (comportamento antigo).
        estoque_item = None
        if item.estoque_id is not None:
            estoque_item = session.get(Estoque, item.estoque_id)
        if estoque_item is None:
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
                usuario_id=usuario_id_seguro(user),
                natureza=dados.natureza,
            ))
            criados += 1

        if estoque_item and estoque_item.estocavel is False:
            pass
        elif estoque_item and not pode_baixar_estoque(estoque_item):
            # Gatilho de comunicação: sem estoque inicial/primeira compra, a
            # aplicação é registrada mas NÃO baixa (o item pede inicialização).
            avisos.append(
                f'Aplicação de "{item.produto}" registrada, mas sem baixa: registre o estoque inicial '
                f'ou a primeira compra do item para começar o controle de baixas.'
            )
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
    return {"criados": criados, "agendadas": 0, "avisos": avisos, "programado": False}


class EditarAplicacaoIn(BaseModel):
    """Edição de UMA aplicação já lançada, direto na lista de Sanidade.
    Todos os campos são opcionais — só o que vier é alterado."""
    data_aplicacao: date | None = None
    produto: str | None = None
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None
    responsavel: str | None = None
    obs: str | None = None


@router.put("/aplicacoes/{aplicacao_id}")
def editar_aplicacao(aplicacao_id: int, dados: EditarAplicacaoIn, session: Session = Depends(get_session)) -> dict:
    """Corrige uma aplicação diretamente na lista (produto, dose, unidade, via,
    responsável, data, observação). Não mexe no estoque — é só ajuste do registro."""
    s = session.get(Sanidade, aplicacao_id)
    if not s:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")

    campos = dados.model_dump(exclude_unset=True)
    if "unidade" in campos and campos["unidade"]:
        produto = campos.get("produto", s.produto)
        estoque_item = session.exec(select(Estoque).where(Estoque.nome == produto)).first()
        compativeis = unidades_compativeis(estoque_item.unidade if estoque_item else None)
        if campos["unidade"] not in compativeis:
            raise HTTPException(
                status_code=400,
                detail=f'Unidade "{campos["unidade"]}" não é compatível com o produto "{produto}" (aceitas: {", ".join(compativeis)})',
            )

    for campo, valor in campos.items():
        setattr(s, campo, valor)
    s.atualizado_em = datetime.utcnow()
    session.add(s)
    session.commit()
    session.refresh(s)
    return {"id": s.id, "numero": s.numero_matriz, "produto": s.produto, "dose": s.dose, "unidade": s.unidade}


@router.delete("/aplicacoes/{aplicacao_id}")
def excluir_aplicacao(aplicacao_id: int, session: Session = Depends(get_session)) -> dict:
    """Exclui uma aplicação da lista de Sanidade. O estoque não é reposto
    automaticamente — se precisar, ajuste o estoque manualmente."""
    s = session.get(Sanidade, aplicacao_id)
    if not s:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")
    session.delete(s)
    session.commit()
    return {"excluido": True, "id": aplicacao_id}


class MarcarCuraAplicacaoIn(BaseModel):
    curada: bool


@router.post("/aplicacoes/{aplicacao_id}/cura")
def marcar_cura_aplicacao(aplicacao_id: int, dados: MarcarCuraAplicacaoIn, session: Session = Depends(get_session)) -> dict:
    """Marca, no dia seguinte a uma aplicação curativa avulsa, se o animal foi
    curado ou não — mesma ideia do /mastite/cura, mas para aplicação avulsa
    (não um protocolo multi-dia). Alimenta o relatório Taxa de cura."""
    s = session.get(Sanidade, aplicacao_id)
    if not s:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")
    s.curada = dados.curada
    session.add(s)
    session.commit()
    return {"id": s.id, "curada": s.curada}


# Categoria simplificada do animal (mesmo padrão usado em lote_criterios.py e
# agenda_veterinario.py — sem helper compartilhado hoje, ver dívida técnica
# anotada nesses arquivos) — usada só para os filtros do relatório abaixo.
def _categoria_animal(animal: Animal | None) -> str:
    if not animal:
        return ""
    texto = (animal.categoria_abrev or animal.categoria_completa or "").strip().lower()
    if "bezerr" in texto:
        return "bezerra"
    if "novilh" in texto:
        return "novilha"
    if "vaca" in texto:
        return "vaca"
    return ""


def _status_lactacao(animal: Animal | None) -> str:
    if not animal:
        return ""
    texto = (animal.categoria_completa or "").strip().lower()
    if "seca" in texto:
        return "seca"
    if "lact" in texto:
        return "lactacao"
    return ""


@router.get("/taxa-cura")
def relatorio_taxa_cura(session: Session = Depends(get_session)) -> dict:
    """
    Casos de cura já avaliados (aplicação avulsa curativa + protocolo
    sanitário), achatados para o dashboard interativo — filtra no cliente por
    período, lote, lactação/seca e categoria, e permite comparar o mesmo
    animal ao longo da vida (vários casos por número).
    """
    animais_por_numero = {a.numero: a for a in session.exec(select(Animal)).all()}
    protocolos_nomes = {p.id: p.nome for p in session.exec(select(ProtocoloSanitario)).all()}

    casos = []
    for s in session.exec(select(Sanidade).where(Sanidade.curada != None)).all():  # noqa: E711
        animal = animais_por_numero.get(s.numero_matriz)
        casos.append({
            "origem": "aplicacao",
            "id": s.id,
            "numero": s.numero_matriz,
            "tratamento": s.produto,
            "data": s.data_aplicacao.isoformat() if s.data_aplicacao else None,
            "curada": s.curada,
            "lote": s.lote or (animal.grupo_primario if animal else None),
            "categoria": _categoria_animal(animal),
            "status_lactacao": _status_lactacao(animal),
        })
    for lanc in session.exec(select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.curada != None)).all():  # noqa: E711
        animal = animais_por_numero.get(lanc.numero_matriz)
        casos.append({
            "origem": "protocolo",
            "id": lanc.id,
            "numero": lanc.numero_matriz,
            "tratamento": protocolos_nomes.get(lanc.protocolo_id, "—"),
            "data": lanc.data_inicio.isoformat() if lanc.data_inicio else None,
            "curada": lanc.curada,
            "lote": animal.grupo_primario if animal else None,
            "categoria": _categoria_animal(animal),
            "status_lactacao": _status_lactacao(animal),
        })

    casos.sort(key=lambda c: (c["numero"], c["data"] or ""))
    total = len(casos)
    curados = sum(1 for c in casos if c["curada"])
    return {
        "casos": casos,
        "total": total,
        "curados": curados,
        "taxa_cura_pct": round(100 * curados / total, 1) if total else None,
    }


# ---------------------------------------------------------------------------
# Calendário sanitário — regras recorrentes (sazonal/de rebanho ou por fase
# fisiológica), cadastradas aqui e acompanhadas com filtro por período/evento.
# ---------------------------------------------------------------------------
def _nomes(session: Session) -> tuple[dict[int, str], dict[int, str], dict[int, str], dict[int, str | None]]:
    evs = session.exec(select(EventoSanitario)).all()
    eventos = {e.id: e.nome for e in evs}
    categorias = {e.id: e.categoria_preventiva for e in evs}
    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    principios = {p.id: p.nome for p in session.exec(select(PrincipioAtivo)).all()}
    return eventos, doencas, principios, categorias


def _ultimo_evento_por_produto(session: Session) -> dict[str, dict]:
    """Data (isoformat) e id da aplicação Sanidade (natureza=preventivo) mais
    recente por produto (chave em minúsculo) — usado para achar "o último
    evento já lançado" de uma regra do calendário sanitário, no popup de
    Aplicações (ver GET /sanidade/calendario, campos ultimo_evento_data/id)."""
    mapa: dict[str, dict] = {}
    registros = session.exec(
        select(Sanidade).where(Sanidade.natureza == "preventivo", Sanidade.data_aplicacao.is_not(None))
    ).all()
    for r in registros:
        chave = (r.produto or "").strip().lower()
        if not chave:
            continue
        atual = mapa.get(chave)
        novo = r.data_aplicacao.isoformat()
        if not atual or novo > atual["data"]:
            mapa[chave] = {"data": novo, "id": r.id}
    return mapa


def _serializar(
    c: CalendarioSanitario, eventos: dict, doencas: dict, principios: dict,
    categorias: dict | None = None, ultimos_por_produto: dict[str, dict] | None = None,
) -> dict:
    categorias = categorias or {}
    ultimos_por_produto = ultimos_por_produto or {}
    ultimo = ultimos_por_produto.get((c.produto or "").strip().lower()) if c.produto else None
    return {
        **c.model_dump(),
        "evento_sanitario_nome": eventos.get(c.evento_sanitario_id, "—"),
        "categoria_preventiva": categorias.get(c.evento_sanitario_id),
        "doenca_nome": doencas.get(c.doenca_id) if c.doenca_id else None,
        "principio_ativo_nome": principios.get(c.principio_ativo_id) if c.principio_ativo_id else None,
        "proxima_ocorrencia": proxima_ocorrencia(c.data_evento, c.frequencia_valor, c.frequencia_unidade).isoformat(),
        "ultimo_evento_data": ultimo["data"] if ultimo else None,
        "ultimo_evento_id": ultimo["id"] if ultimo else None,
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
    eventos, doencas, principios, categorias = _nomes(session)
    ultimos = _ultimo_evento_por_produto(session)
    regras = session.exec(select(CalendarioSanitario).where(CalendarioSanitario.ativo == True)).all()  # noqa: E712
    saida = [_serializar(c, eventos, doencas, principios, categorias, ultimos) for c in regras]
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
    unidade: str | None = None
    responsavel: str | None = None  # pessoa responsável pela regra (vacina e exame)
    veterinario: str | None = None  # p/ exames: quem realizou/vai realizar
    frequencia_valor: int
    frequencia_unidade: str
    data_evento: date
    observacao: str | None = None
    ativo: bool = True
    # "Já foi realizado?" — quando a 1ª ocorrência é hoje/passada e já aconteceu,
    # marca o evento como realizado (some da Agenda). Não é campo do modelo.
    realizado: bool = False


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
    # Só se marca como realizado evento do dia corrente ou retroativo — nunca
    # um evento com data futura (ainda não aconteceu).
    if dados.realizado and dados.data_evento > date.today():
        raise HTTPException(
            status_code=400,
            detail="Só é possível marcar como realizado um evento de hoje ou retroativo — a data informada é futura.",
        )


def _marcar_calendario_realizado(session: Session, c: CalendarioSanitario) -> None:
    eid = f"calendario_sanitario_{c.id}__{c.data_evento.isoformat()}"
    if not session.exec(select(EventoRealizado).where(EventoRealizado.evento_id == eid)).first():
        session.add(EventoRealizado(evento_id=eid))
        session.commit()


@router.post("/calendario")
def criar_calendario(dados: CalendarioSanitarioIn, session: Session = Depends(get_session)) -> dict:
    _validar_calendario(dados, session)
    c = CalendarioSanitario(**dados.model_dump(exclude={"realizado"}))
    session.add(c)
    session.commit()
    session.refresh(c)
    # "Já foi realizado?" — marca a ocorrência de referência como realizada para
    # não aparecer como pendência na Agenda (útil p/ exames já feitos hoje).
    # Considera realizada somente essa primeira ocorrência — cada ocorrência
    # projetada tem seu próprio evento_id (ver _eventos_calendario_agenda), as
    # seguintes continuam pendentes normalmente.
    if dados.realizado:
        _marcar_calendario_realizado(session, c)
    eventos, doencas, principios, categorias = _nomes(session)
    ultimos = _ultimo_evento_por_produto(session)
    return _serializar(c, eventos, doencas, principios, categorias, ultimos)


@router.put("/calendario/{calendario_id}")
def atualizar_calendario(calendario_id: int, dados: CalendarioSanitarioIn, session: Session = Depends(get_session)) -> dict:
    c = session.get(CalendarioSanitario, calendario_id)
    if not c:
        raise HTTPException(status_code=404, detail="Regra do calendário sanitário não encontrada")
    _validar_calendario(dados, session)
    for campo, valor in dados.model_dump(exclude={"realizado"}).items():
        setattr(c, campo, valor)
    session.add(c)
    session.commit()
    session.refresh(c)
    if dados.realizado:
        _marcar_calendario_realizado(session, c)
    eventos, doencas, principios, categorias = _nomes(session)
    ultimos = _ultimo_evento_por_produto(session)
    return _serializar(c, eventos, doencas, principios, categorias, ultimos)


@router.delete("/calendario/{calendario_id}")
def excluir_calendario(calendario_id: int, session: Session = Depends(get_session)) -> dict:
    """Exclui uma regra do calendário sanitário (e suas ocorrências somem da Agenda)."""
    c = session.get(CalendarioSanitario, calendario_id)
    if not c:
        raise HTTPException(status_code=404, detail="Regra do calendário sanitário não encontrada")
    session.delete(c)
    session.commit()
    return {"excluido": True, "id": calendario_id}


@router.get("/calendario/eventos-vida")
def listar_eventos_vida(session: Session = Depends(get_session)) -> list[dict]:
    """Vocabulário de eventos de vida (gatilhos) disponíveis para o relatório
    abaixo e para o cadastro de evento sanitário por evento — rótulo em
    português de cada `gatilho` (ver GATILHOS_EVENTO)."""
    return [{"gatilho": g, "rotulo": ROTULOS_GATILHO.get(g, g)} for g in GATILHOS_EVENTO]


@router.get("/calendario/relatorio-eventos-vida")
def relatorio_eventos_vida(
    gatilho: str | None = None,
    evento_sanitario_id: int | None = None,
    gatilho_lote: str | None = None,
    gatilho_idade_meses: int | None = None,
    data_inicio: str = "",
    data_fim: str = "",
    session: Session = Depends(get_session),
) -> dict:
    """
    Relatório "quais animais entrarão em determinado calendário sanitário" —
    dado um evento de vida (gatilho), lista os animais e a data em que cada um
    atinge (ou atingiu) esse evento, para identificar quem entrará na próxima
    aplicação de um calendário sanitário por evento.

    Aceita ou um `evento_sanitario_id` já cadastrado (herda gatilho/lote/idade
    do cadastro) ou um `gatilho` avulso (exploração livre, sem precisar
    cadastrar o evento sanitário antes).
    """
    nome_evento = None
    if evento_sanitario_id is not None:
        ev = session.get(EventoSanitario, evento_sanitario_id)
        if not ev:
            raise HTTPException(status_code=400, detail="Evento sanitário não encontrado")
        if ev.tipo_agendamento != "evento" or not ev.gatilho:
            raise HTTPException(status_code=400, detail="Este evento sanitário não está agendado por evento de vida")
        gatilho, gatilho_lote, gatilho_idade_meses = ev.gatilho, ev.gatilho_lote, ev.gatilho_idade_meses
        nome_evento = ev.nome
    if not gatilho or gatilho not in GATILHOS_EVENTO:
        raise HTTPException(status_code=400, detail=f"Gatilho inválido (use: {', '.join(GATILHOS_EVENTO)})")

    animais = {a.numero: a for a in session.exec(select(Animal)).all()}
    hoje = date.today()
    linhas = []
    for numero, quando in _datas_gatilho(session, gatilho, gatilho_lote, gatilho_idade_meses):
        if data_inicio and quando.isoformat() < data_inicio:
            continue
        if data_fim and quando.isoformat() > data_fim:
            continue
        a = animais.get(numero)
        linhas.append({
            "numero_matriz": numero,
            "nome": a.nome if a else None,
            "grupo_primario": a.grupo_primario if a else None,
            "categoria": (a.categoria_abrev or a.categoria_completa) if a else None,
            "data_evento": quando.isoformat(),
            "dias_restantes": (quando - hoje).days,
        })
    linhas.sort(key=lambda x: x["data_evento"])
    return {"gatilho": gatilho, "rotulo": ROTULOS_GATILHO.get(gatilho, gatilho), "evento_sanitario_nome": nome_evento, "animais": linhas}


class CadastrarPreventivoIn(BaseModel):
    """
    Cadastro de um preventivo do calendário sanitário mirando um lote/categoria
    e os animais marcados. Cria a regra recorrente do calendário (para as
    próximas ocorrências) e — se `aplicar` — registra a aplicação do produto
    padrão do evento nos animais marcados (individual ou todos os filtrados),
    reaproveitando a baixa de estoque de /sanidade/aplicacoes.
    """
    evento_sanitario_id: int
    categoria_alvo: str | None = None       # lote ou categoria alvo
    data_evento: date
    frequencia_valor: int = 1               # 0 = não repetir (só esta aplicação, sem gerar agendamento futuro)
    frequencia_unidade: str = "meses"
    animais: list[str] = []                  # animais marcados (individual ou todos)
    aplicar: bool = False                    # também registrar a aplicação do produto padrão
    # "Já foi aplicado?" — só importa quando `aplicar` é True (vacina/tratamento;
    # exame não passa por aqui). Quando False, a aplicação vira AplicacaoAgendada
    # (pendência na Agenda) em vez de Sanidade — idêntico ao toggle de /sanidade/aplicacoes.
    aplicado: bool = True
    veterinario: str | None = None           # p/ exames
    responsavel: str | None = None
    observacao: str | None = None
    # Overrides opcionais do produto/dose/via padrão do evento — usados pela
    # confirmação inline da Agenda ("dar baixa" sem abrir a tela de lançamento),
    # onde o usuário pode ajustar o que veio do cadastro antes de confirmar.
    # Quando omitidos, o comportamento é idêntico ao de sempre (usa o padrão).
    produto: str | None = None
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None
    principio_ativo_id: int | None = None
    # Resultado do exame (só quando o evento é categoria_preventiva == "exame") —
    # diagnóstico: positivo/negativo/indefinido; numérico: valor lançado (a
    # banda é calculada a partir do ExameDefinicao vinculado ao evento).
    # Nunca gera aplicação de medicamento — só grava ExameResultado p/ relatório.
    resultado_exame: str | None = None
    resultado_numerico: float | None = None


def _banda_numerica(exame_def: ExameDefinicao | None, valor: float) -> str | None:
    if not exame_def or exame_def.faixa_min is None or exame_def.faixa_max is None:
        return None
    if valor < exame_def.faixa_min:
        return "abaixo"
    if valor > exame_def.faixa_max:
        return "acima"
    return "dentro"


@router.post("/calendario/cadastrar-preventivo")
def cadastrar_preventivo(dados: CadastrarPreventivoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    ev = session.get(EventoSanitario, dados.evento_sanitario_id)
    if not ev:
        raise HTTPException(status_code=400, detail="Evento sanitário não encontrado")
    if dados.frequencia_unidade not in FREQUENCIAS:
        raise HTTPException(status_code=400, detail=f"Frequência inválida (use: {', '.join(FREQUENCIAS)})")
    if dados.frequencia_valor < 0:
        raise HTTPException(status_code=400, detail="A frequência não pode ser negativa")

    produto = dados.produto or ev.produto_padrao
    dose = dados.dose if dados.dose is not None else ev.dose_padrao
    unidade = dados.unidade or ev.unidade_padrao
    via = dados.via if dados.via is not None else ev.via_padrao

    # 1) Regra recorrente do calendário — herda produto/dose/doença do evento
    # (ou o que foi confirmado/ajustado na hora de dar baixa). "Repetir a cada"
    # = 0 significa que o usuário não quer gerar agendamento futuro: só a
    # aplicação de agora é registrada (passo 2), sem criar a regra recorrente.
    regra = None
    if dados.frequencia_valor > 0:
        dosagem = None
        if dose is not None:
            dosagem = f"{dose:g} {unidade}".strip() if unidade else f"{dose:g}"
        regra = CalendarioSanitario(
            evento_sanitario_id=ev.id, categoria_alvo=dados.categoria_alvo, doenca_id=ev.doenca_id,
            produto=produto, principio_ativo_id=dados.principio_ativo_id, dosagem=dosagem, unidade=unidade,
            veterinario=dados.veterinario,
            frequencia_valor=dados.frequencia_valor, frequencia_unidade=dados.frequencia_unidade,
            data_evento=dados.data_evento, observacao=dados.observacao,
        )
        session.add(regra)
        session.commit()
        session.refresh(regra)

    # 2) Aplicação do produto (padrão ou confirmado/ajustado) nos animais marcados (opcional).
    aplicacao = None
    if dados.aplicar and dados.animais and produto and dose is not None and unidade:
        aplicacao = registrar_aplicacao(
            AplicacaoIn(
                data_aplicacao=dados.data_evento, animais=dados.animais,
                itens=[ItemAplicacaoIn(produto=produto, via=via, quantidade=dose, unidade=unidade)],
                responsavel=dados.responsavel, observacao=dados.observacao or f"Preventivo: {ev.nome}",
                aplicado=dados.aplicado, natureza="preventivo",
            ),
            session,
            user,
        )

    # 3) Diagnóstico/resultado do exame (só evento categoria_preventiva ==
    # "exame") — grava um ExameResultado por animal, para fins de relatório, e
    # aplica a ação automática do diagnóstico: positivo marca "A descartar";
    # negativo é informativo ("liberada"); indefinido marca para repetir o
    # exame (ambos só leitura no relatório). Nunca baixa estoque.
    resultado_exame = None
    if (dados.resultado_exame or dados.resultado_numerico is not None) and dados.animais:
        if ev.categoria_preventiva != "exame":
            raise HTTPException(status_code=400, detail="Diagnóstico só se aplica a eventos do tipo exame")
        exame_def = session.get(ExameDefinicao, ev.exame_definicao_id) if ev.exame_definicao_id else None
        if dados.resultado_exame and dados.resultado_exame not in RESULTADOS_EXAME:
            raise HTTPException(status_code=400, detail=f"Resultado inválido (use: {', '.join(RESULTADOS_EXAME)})")
        banda = _banda_numerica(exame_def, dados.resultado_numerico) if dados.resultado_numerico is not None else None
        for numero in dados.animais:
            session.add(ExameResultado(
                numero_matriz=numero, evento_sanitario_id=ev.id, exame_definicao_id=ev.exame_definicao_id,
                data_exame=dados.data_evento, resultado=dados.resultado_exame,
                valor_numerico=dados.resultado_numerico, banda=banda,
                veterinario=dados.veterinario, observacao=dados.observacao,
            ))
        session.commit()
        if dados.resultado_exame == "positivo":
            marcar_a_descartar(
                ADescartarIn(animais=dados.animais, descartar=True, observacao=f"Exame {ev.nome}: positivo"),
                session,
            )
        resultado_exame = {"resultado": dados.resultado_exame, "banda": banda, "animais": len(dados.animais)}

    eventos, doencas, principios, categorias = _nomes(session)
    return {
        "regra": _serializar(regra, eventos, doencas, principios, categorias) if regra else None,
        "aplicacao": aplicacao,
        "resultado_exame": resultado_exame,
    }


@router.get("/exames/resultados")
def listar_resultados_exame(
    evento_sanitario_id: int | None = None, resultado: str | None = None,
    data_de: date | None = None, data_ate: date | None = None, session: Session = Depends(get_session),
) -> list[dict]:
    """Relatório de resultados de exames (positivo/negativo/indefinido ou
    numérico) lançados via calendário sanitário preventivo — ver
    cadastrar_preventivo. Só leitura, para acompanhamento."""
    query = select(ExameResultado).order_by(ExameResultado.data_exame.desc(), ExameResultado.id.desc())
    if evento_sanitario_id is not None:
        query = query.where(ExameResultado.evento_sanitario_id == evento_sanitario_id)
    if resultado is not None:
        query = query.where(ExameResultado.resultado == resultado)
    if data_de is not None:
        query = query.where(ExameResultado.data_exame >= data_de)
    if data_ate is not None:
        query = query.where(ExameResultado.data_exame <= data_ate)
    eventos = {e.id: e.nome for e in session.exec(select(EventoSanitario)).all()}
    saida = []
    for r in session.exec(query).all():
        d = r.model_dump()
        d["evento_sanitario_nome"] = eventos.get(r.evento_sanitario_id)
        saida.append(d)
    return saida


# ---------------------------------------------------------------------------
# Protocolo sanitário — lançamento (aplicar um protocolo cadastrado a um
# animal). Gera uma aplicação (evento de Agenda) por etapa/dia do protocolo;
# a baixa de estoque só acontece quando o evento é marcado "realizado" na
# Agenda (ver POST /agenda/realizados).
# ---------------------------------------------------------------------------
class ProtocoloLancamentoIn(BaseModel):
    protocolo_id: int
    numeros_matriz: list[str]  # um ou mais animais (protocolo de mastite aceita só um)
    data_inicio: date
    responsavel: str | None = None
    observacao: str | None = None
    classificacao_mastite: str | None = None  # "clinica" | "subclinica" | "ambiental"
    grau_mastite: int | None = None  # 1, 2 ou 3
    agente: str | None = None
    resultado_cmt: str | None = None  # "-", "+", "++" ou "+++"
    tetos_afetados: list[str] = []  # subconjunto de AE/AD/PD/PE
    # Medicamento escolhido por etapa (etapa_id -> nome do medicamento), quando
    # a etapa foi cadastrada por princípio ativo/classificação.
    escolhas_medicamento: dict[str, str] = {}


def _serializar_lancamento_protocolo(
    session: Session, lanc: ProtocoloSanitarioLancamento, protocolos: dict[int, ProtocoloSanitario], nomes: dict[int, str] | None = None,
) -> dict:
    aplicacoes = session.exec(
        select(ProtocoloSanitarioAplicacao)
        .where(ProtocoloSanitarioAplicacao.lancamento_id == lanc.id)
        .order_by(ProtocoloSanitarioAplicacao.data_prevista)
    ).all()
    etapas = {e.id: e for e in session.exec(select(ProtocoloSanitarioEtapa)).all()}
    nomes = nomes if nomes is not None else mapa_usuarios(session, {lanc.usuario_id})
    protocolo = protocolos.get(lanc.protocolo_id)
    return {
        **lanc.model_dump(),
        "protocolo_nome": protocolo.nome if protocolo else "—",
        # Rótulo D exibido = etapa.dia - protocolo_dia_inicial (mesma convenção
        # de CadastroSanitario.tsx) — sem isso, a listagem de lançamentos
        # sempre mostraria o dia bruto (D1, D2...) mesmo para protocolos já
        # cadastrados em base D0.
        "protocolo_dia_inicial": protocolo.dia_inicial if protocolo else 1,
        "usuario_nome": nomes.get(lanc.usuario_id),
        "aplicacoes": [
            {**a.model_dump(), "etapa": etapas[a.etapa_id].model_dump() if a.etapa_id in etapas else None}
            for a in aplicacoes
        ],
    }


@router.get("/protocolos/lancamentos")
def listar_lancamentos_protocolo(session: Session = Depends(get_session)) -> list[dict]:
    protocolos = {p.id: p for p in session.exec(select(ProtocoloSanitario)).all()}
    lancamentos = session.exec(select(ProtocoloSanitarioLancamento).order_by(ProtocoloSanitarioLancamento.data_inicio.desc())).all()
    nomes = mapa_usuarios(session, {l.usuario_id for l in lancamentos})
    return [_serializar_lancamento_protocolo(session, l, protocolos, nomes) for l in lancamentos]


@router.post("/protocolos/lancamentos", status_code=201)
def lancar_protocolo(dados: ProtocoloLancamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    protocolo = session.get(ProtocoloSanitario, dados.protocolo_id)
    if not protocolo:
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    etapas = session.exec(
        select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == dados.protocolo_id).order_by(ProtocoloSanitarioEtapa.dia)
    ).all()
    if not etapas:
        raise HTTPException(status_code=400, detail="Este protocolo não tem etapas cadastradas")
    numeros = [n.strip() for n in dados.numeros_matriz if n.strip()]
    if not numeros:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal, lote ou categoria")

    if protocolo.eh_mastite and not dados.classificacao_mastite:
        raise HTTPException(status_code=400, detail="Informe a classificação da mastite (clínica, subclínica ou ambiental)")
    if protocolo.eh_mastite and len(numeros) > 1:
        raise HTTPException(status_code=400, detail="Protocolo de mastite: lance um animal por vez (classificação/CMT/tetos são específicos de cada caso)")
    if dados.classificacao_mastite and dados.classificacao_mastite not in CLASSIFICACOES_MASTITE:
        raise HTTPException(status_code=400, detail=f"Classificação de mastite inválida (aceitas: {', '.join(CLASSIFICACOES_MASTITE)})")
    for teto in dados.tetos_afetados:
        if teto not in TETOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Teto inválido: {teto} (aceitos: {', '.join(TETOS_VALIDOS)})")

    # Etapas cadastradas por princípio ativo/classificação exigem escolher o
    # medicamento real no lançamento (guardado por etapa em cada aplicação).
    # Etapas de produto FIXO também podem vir com uma escolha — é o medicamento
    # SUBSTITUTO que o front oferece quando o item cadastrado no protocolo está
    # zerado/negativo/no mínimo; nesse caso, o substituto vale por cima do fixo.
    produto_por_etapa: dict[int, str | None] = {}
    for etapa in etapas:
        escolhido = (dados.escolhas_medicamento.get(str(etapa.id)) or "").strip()
        if getattr(etapa, "criterio_tipo", "medicamento") != "medicamento":
            if not escolhido:
                raise HTTPException(status_code=400, detail=f"Escolha o medicamento da etapa D{etapa.dia - protocolo.dia_inicial} ({etapa.produto}).")
            produto_por_etapa[etapa.id] = escolhido
        else:
            produto_por_etapa[etapa.id] = escolhido or None

    if dados.grau_mastite is not None and dados.grau_mastite not in GRAUS_MASTITE:
        raise HTTPException(status_code=400, detail="Grau de mastite inválido (aceitos: 1, 2 ou 3)")

    protocolos = {protocolo.id: protocolo}
    lancamentos_criados = []
    avisos: list[str] = []
    for numero in numeros:
        del_no_caso = None
        ccs_ultima = None
        recidiva = None
        if protocolo.eh_mastite:
            animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
            del_no_caso = animal.del_dias if animal else None
            # Última CCS do animal (ou do tanque, na falta) — snapshot do caso.
            ult_ccs = session.exec(
                select(QualidadeLeite).where(QualidadeLeite.numero_matriz == numero, QualidadeLeite.ccs != None)  # noqa: E711
                .order_by(QualidadeLeite.data_coleta.desc())
            ).first()
            ccs_ultima = ult_ccs.ccs if ult_ccs else None
            # Recidiva: caso de mastite anterior no MESMO teto com intervalo < 20 dias.
            tetos_novos = set(dados.tetos_afetados)
            if tetos_novos:
                limite = dados.data_inicio - timedelta(days=DIAS_RECIDIVA_MASTITE)
                anteriores = session.exec(
                    select(ProtocoloSanitarioLancamento).where(
                        ProtocoloSanitarioLancamento.numero_matriz == numero,
                        ProtocoloSanitarioLancamento.data_inicio >= limite,
                        ProtocoloSanitarioLancamento.data_inicio < dados.data_inicio,
                    )
                ).all()
                for ant in anteriores:
                    tetos_ant = set((ant.tetos_afetados or "").split(",")) if ant.tetos_afetados else set()
                    if tetos_novos & tetos_ant:
                        recidiva = True
                        avisos.append(
                            f"Recidiva no(s) teto(s) {', '.join(sorted(tetos_novos & tetos_ant))} do animal {numero} "
                            f"(caso em {ant.data_inicio.strftime('%d/%m/%Y')}, menos de {DIAS_RECIDIVA_MASTITE} dias) — "
                            f"troque para o próximo tratamento."
                        )
                        break
        lancamento = ProtocoloSanitarioLancamento(
            protocolo_id=dados.protocolo_id, numero_matriz=numero, data_inicio=dados.data_inicio,
            responsavel=dados.responsavel, observacao=dados.observacao,
            classificacao_mastite=dados.classificacao_mastite,
            grau_mastite=dados.grau_mastite, agente=dados.agente,
            resultado_cmt=dados.resultado_cmt,
            tetos_afetados=",".join(dados.tetos_afetados) if dados.tetos_afetados else None,
            del_no_caso=del_no_caso, ccs_ultima=ccs_ultima, recidiva=recidiva,
            usuario_id=usuario_id_seguro(user),
        )
        session.add(lancamento)
        session.commit()
        session.refresh(lancamento)

        for etapa in etapas:
            data_prevista = dados.data_inicio + timedelta(days=etapa.dia - protocolo.dia_inicial)
            session.add(ProtocoloSanitarioAplicacao(
                lancamento_id=lancamento.id, etapa_id=etapa.id, data_prevista=data_prevista,
                produto=produto_por_etapa.get(etapa.id),
            ))
        session.commit()
        lancamentos_criados.append(_serializar_lancamento_protocolo(session, lancamento, protocolos))

    return {"criados": len(lancamentos_criados), "lancamentos": lancamentos_criados, "avisos": avisos}


@router.get("/mastite/opcoes")
def opcoes_mastite() -> dict:
    """Listas padrão do lançamento de mastite (agentes, graus, tetos, CMT)."""
    return {
        "agentes": AGENTES_MASTITE, "graus": GRAUS_MASTITE, "tetos": TETOS_VALIDOS,
        "resultados_cmt": RESULTADOS_CMT, "classificacoes": CLASSIFICACOES_MASTITE,
    }


@router.get("/mastite/contexto")
def contexto_mastite(numero: str, session: Session = Depends(get_session)) -> dict:
    """DEL atual, última CCS e último CMT do animal — preenchidos automaticamente
    ao abrir um caso de mastite."""
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    ult_ccs = session.exec(
        select(QualidadeLeite).where(QualidadeLeite.numero_matriz == numero, QualidadeLeite.ccs != None)  # noqa: E711
        .order_by(QualidadeLeite.data_coleta.desc())
    ).first()
    ult_caso = session.exec(
        select(ProtocoloSanitarioLancamento).where(
            ProtocoloSanitarioLancamento.numero_matriz == numero, ProtocoloSanitarioLancamento.resultado_cmt != None  # noqa: E711
        ).order_by(ProtocoloSanitarioLancamento.data_inicio.desc())
    ).first()
    return {
        "numero": numero,
        "del_atual": animal.del_dias if animal else None,
        "ccs_ultima": ult_ccs.ccs if ult_ccs else None,
        "data_ccs": ult_ccs.data_coleta.isoformat() if ult_ccs else None,
        "cmt_ultimo": ult_caso.resultado_cmt if ult_caso else None,
    }


class MarcarCuraIn(BaseModel):
    lancamento_id: int
    curada: bool


@router.post("/mastite/cura")
def marcar_cura_mastite(dados: MarcarCuraIn, session: Session = Depends(get_session)) -> dict:
    """Marca, no último dia do protocolo, se o caso de mastite foi curado ou não.
    Se não curado, sinaliza a necessidade do próximo tratamento."""
    lanc = session.get(ProtocoloSanitarioLancamento, dados.lancamento_id)
    if not lanc:
        raise HTTPException(status_code=404, detail="Lançamento de mastite não encontrado")
    lanc.curada = dados.curada
    session.add(lanc)
    session.commit()
    proximo = None if dados.curada else "Caso não curado — inicie o próximo tratamento (protocolo seguinte)."
    return {"lancamento_id": lanc.id, "curada": lanc.curada, "proximo_tratamento": proximo}


# ---------------------------------------------------------------------------
# Colostragem e teste de sangue (IgG) — gravado a partir da calculadora em
# Lançamentos > Parto/nascimento, consumido pelo relatório sanitário de
# bezerras abaixo.
# ---------------------------------------------------------------------------
def _classe_colostro(brix: float | None) -> str | None:
    if brix is None:
        return None
    if brix > 25:
        return "ouro"
    if brix >= 18:
        return "prata"
    return "bronze"


def _classe_soro(brix: float | None) -> str | None:
    if brix is None:
        return None
    if brix >= 8.4:
        return "sucesso"
    if brix >= 8.1:
        return "alerta"
    return "falha"


def _classe_colostragem(brix: float | None, proteina: float | None) -> str | None:
    """Eficiência de transferência de imunidade passiva, em 4 níveis, por Brix
    sérico (%) OU proteína sérica total (g/dL) — o que estiver disponível
    (Brix tem prioridade). Faixas (Lombard et al.):
      excelente  Brix >9,4  · proteína >6,2   (meta: >50% das bezerras)
      boa        Brix 8,9-9,3 · proteína 5,8-6,1 (meta: 30%)
      aceitavel  Brix 8,1-8,8 · proteína 5,1-5,7 (meta: 15%)
      ruim       Brix <8,1  · proteína <5,1    (meta: <5%)
    """
    if brix is not None:
        if brix > 9.4:
            return "excelente"
        if brix >= 8.9:
            return "boa"
        if brix >= 8.1:
            return "aceitavel"
        return "ruim"
    if proteina is not None:
        if proteina > 6.2:
            return "excelente"
        if proteina >= 5.8:
            return "boa"
        if proteina >= 5.1:
            return "aceitavel"
        return "ruim"
    return None


class ColostragemIn(BaseModel):
    numero_animal: str
    tomou_colostro: bool | None = None
    litros_colostro: float | None = None
    brix_colostro: float | None = None
    data_colostro: date | None = None
    hora_parto: str | None = None
    hora_colostro: str | None = None
    peso_nascer_kg: float | None = None
    brix_soro: float | None = None
    proteina_serica: float | None = None
    apenas_colostro_po: bool | None = None
    data_teste_sangue: date | None = None
    observacao: str | None = None


@router.post("/colostragem")
def registrar_colostragem(
    dados: ColostragemIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    """Grava (ou atualiza) o registro de colostragem/teste de sangue de uma
    cria — uma linha por animal, chamada pela calculadora de Parto/nascimento."""
    animal = session.exec(select(Animal).where(Animal.numero == dados.numero_animal)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    registro = session.exec(
        select(ColostragemBezerra).where(ColostragemBezerra.numero_animal == dados.numero_animal)
    ).first()
    if not registro:
        registro = ColostragemBezerra(animal_id=animal.id, numero_animal=dados.numero_animal, usuario_id=usuario_id_seguro(user))
    for campo, valor in dados.model_dump(exclude={"numero_animal"}).items():
        setattr(registro, campo, valor)
    registro.atualizado_em = datetime.utcnow()
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.get("/relatorio-bezerras")
def relatorio_sanitario_bezerras(
    faixa_etaria: str | None = Query(None, description="ate_12 | acima_12"),
    numero: str | None = None,
    lote: str | None = None,
    numeros: list[str] | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict]:
    """
    Indicadores de colostragem e teste de sangue por animal, para identificar
    na fase adulta problemas que vieram de má colostragem. Filtra por faixa
    etária (bezerra <=12 meses / animal >12 meses, calculada por data_nasc),
    por animal, por lote atual (grupo_primario) ou por seleção de vários animais.
    """
    animais = session.exec(select(Animal).where(Animal.eh_semen == False)).all()  # noqa: E712
    todos_registros = session.exec(select(ColostragemBezerra)).all()
    registros = {r.numero_animal: r for r in todos_registros}
    nomes = mapa_usuarios(session, {r.usuario_id for r in todos_registros})
    hoje = date.today()

    numeros_selecionados = {n.strip() for n in numeros} if numeros else None
    saida = []
    for a in animais:
        if numero and a.numero != numero:
            continue
        if lote and (a.grupo_primario or "") != lote:
            continue
        if numeros_selecionados and a.numero not in numeros_selecionados:
            continue

        idade_meses = round((hoje - a.data_nasc).days / 30.44, 1) if a.data_nasc else a.idade_meses
        if faixa_etaria == "ate_12" and (idade_meses is None or idade_meses > 12):
            continue
        if faixa_etaria == "acima_12" and (idade_meses is None or idade_meses <= 12):
            continue

        r = registros.get(a.numero)
        saida.append({
            "numero": a.numero, "nome": a.nome, "sexo": a.sexo, "categoria_abrev": a.categoria_abrev,
            "grupo_primario": a.grupo_primario, "data_nasc": a.data_nasc, "idade_meses": idade_meses,
            "ativo": a.ativo,
            "tomou_colostro": r.tomou_colostro if r else None,
            "litros_colostro": r.litros_colostro if r else None,
            "brix_colostro": r.brix_colostro if r else None,
            "classe_colostro": _classe_colostro(r.brix_colostro if r else None),
            "data_colostro": r.data_colostro if r else None,
            "hora_parto": r.hora_parto if r else None,
            "hora_colostro": r.hora_colostro if r else None,
            "peso_nascer_kg": r.peso_nascer_kg if r else None,
            "brix_soro": r.brix_soro if r else None,
            "proteina_serica": r.proteina_serica if r else None,
            "classe_soro": _classe_soro(r.brix_soro if r else None),
            "classe_colostragem": _classe_colostragem(r.brix_soro if r else None, r.proteina_serica if r else None),
            "apenas_colostro_po": (r.apenas_colostro_po if r else None) or False,
            # Sem mensuração = tem registro mas nenhum Brix/proteína sérica medido.
            "sem_mensuracao": bool(r) and (r.brix_soro is None and r.proteina_serica is None),
            "data_teste_sangue": r.data_teste_sangue if r else None,
            "usuario_nome": nomes.get(r.usuario_id) if r else None,
        })
    saida.sort(key=lambda x: x["numero"])
    return saida
