"""
Router de produção — indicadores do histórico de controle leiteiro e
lançamento de pesagens (por vaca ou por lote inteiro, de uma vez).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.lotes import coletar_dados_criterios
from fazenda.database import get_session
from fazenda.models import (
    Animal, AplicacaoAgendada, ContaGerencial, ControleLeiteiro, Dieta, EntregaLeiteMensal, Estoque, LancamentoItem, Lote,
    Parto, PesagemCorporal, QualidadeLeite, Sanidade, Secagem, Servico,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.alimentacao import calcular_consumo
from fazenda.rules.dry_off import calcular_secagem
from fazenda.rules.gestation import calcular_parto_provavel
from fazenda.rules.lote_criterios import animal_atende_criterios, lote_tem_criterio
from fazenda.rules.producao import calcular_producao
from fazenda.rules.unidades import pode_dar_baixa_direta, unidades_compativeis

router = APIRouter(prefix="/producao", tags=["producao"])

MOTIVOS_SECAGEM = ["doente", "baixa_producao", "comportamento", "mastite", "casco", "rotina", "outros"]


class OrdenhaIn(BaseModel):
    numero_matriz: str
    ordenhas: list[float]


class ControlesIn(BaseModel):
    data_controle: date
    entradas: list[OrdenhaIn]


@router.get("/")
def obter_producao(session: Session = Depends(get_session)) -> dict:
    """Série temporal, curva de lactação e ranking por vaca do controle leiteiro."""
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]
    return calcular_producao(controles)


@router.get("/controles")
def listar_controles(session: Session = Depends(get_session)) -> dict:
    """Registros de controle leiteiro achatados para o dashboard interativo."""
    grupo_por_numero = {a.numero: a.grupo_primario for a in session.exec(select(Animal)).all()}
    # Ordem de parto por animal derivada do nº de partos, para preencher os
    # controles cuja ordem veio vazia (o primeiro parto é sempre "1").
    partos_por_numero: dict[str, int] = {}
    for p in session.exec(select(Parto)).all():
        partos_por_numero[p.numero_matriz] = partos_por_numero.get(p.numero_matriz, 0) + 1
    registros = []
    for c in session.exec(select(ControleLeiteiro)).all():
        d = c.data_controle
        ordem = c.ordem_parto or partos_por_numero.get(c.numero_matriz) or None
        registros.append({
            "numero": c.numero_matriz,
            "raca": c.raca or "(sem raça)",
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "producao_kg": c.producao_kg,
            "del": c.del_no_controle,
            "ordem_parto": ordem,
            "data_ult_parto": c.data_ult_parto.isoformat() if c.data_ult_parto else None,
            "ordenha1_kg": c.ordenha1_kg,
            "ordenha2_kg": c.ordenha2_kg,
            "ordenha3_kg": c.ordenha3_kg,
            "grupo_primario": grupo_por_numero.get(c.numero_matriz),  # lote atual do animal (não histórico)
        })
    return {"controles": registros, "total": len(registros)}


@router.post("/controles")
def criar_controles(dados: ControlesIn, session: Session = Depends(get_session)) -> dict:
    """
    Registra a pesagem do dia para uma ou várias vacas de uma vez (lançamento
    individual ou em lote — o front manda uma entrada por vaca do lote).
    """
    criados = []
    for entrada in dados.entradas:
        if not entrada.ordenhas or not any(entrada.ordenhas):
            continue
        animal = session.exec(select(Animal).where(Animal.numero == entrada.numero_matriz)).first()
        ordenhas = entrada.ordenhas
        registro = ControleLeiteiro(
            animal_id=animal.id if animal else None,
            numero_matriz=entrada.numero_matriz,
            raca=animal.raca if animal else None,
            data_controle=dados.data_controle,
            producao_kg=round(sum(ordenhas), 2),
            del_no_controle=animal.del_dias if animal else None,
            ordenha1_kg=ordenhas[0] if len(ordenhas) > 0 else None,
            ordenha2_kg=ordenhas[1] if len(ordenhas) > 1 else None,
            ordenha3_kg=ordenhas[2] if len(ordenhas) > 2 else None,
        )
        session.add(registro)
        criados.append(registro)
    session.commit()
    return {"criados": len(criados)}


class PesoIn(BaseModel):
    numero_matriz: str
    peso_kg: float


class PesagensIn(BaseModel):
    data_pesagem: date
    entradas: list[PesoIn]


@router.post("/pesagens")
def criar_pesagens(dados: PesagensIn, session: Session = Depends(get_session)) -> dict:
    """Registra a pesagem corporal do dia para uma ou várias vacas de uma vez."""
    criados = []
    for entrada in dados.entradas:
        if not entrada.peso_kg:
            continue
        animal = session.exec(select(Animal).where(Animal.numero == entrada.numero_matriz)).first()
        registro = PesagemCorporal(
            numero_matriz=entrada.numero_matriz,
            data_pesagem=dados.data_pesagem,
            peso_kg=entrada.peso_kg,
            del_dias=animal.del_dias if animal else None,
            idade_meses=animal.idade_meses if animal else None,
            grupo_primario=animal.grupo_primario if animal else None,
        )
        session.add(registro)
        criados.append(registro)
    session.commit()
    return {"criados": len(criados)}


@router.get("/pesagens/relatorio")
def relatorio_pesagens(
    numero_matriz: str | None = None,
    grupo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """
    Primeira/última pesagem, GMD (ganho médio diário — peso final vs inicial no
    período) e GPD (ganho de peso diário entre pesagens — média dos ganhos
    diários de cada intervalo consecutivo) por animal, lote ou todo o rebanho.
    """
    query = select(PesagemCorporal)
    if numero_matriz:
        query = query.where(PesagemCorporal.numero_matriz == numero_matriz)
    if data_inicio:
        query = query.where(PesagemCorporal.data_pesagem >= data_inicio)
    if data_fim:
        query = query.where(PesagemCorporal.data_pesagem <= data_fim)
    pesagens = session.exec(query).all()
    if grupo:
        pesagens = [p for p in pesagens if p.grupo_primario == grupo]

    por_animal: dict[str, list[PesagemCorporal]] = {}
    for p in pesagens:
        por_animal.setdefault(p.numero_matriz, []).append(p)

    linhas = []
    for numero, lista in por_animal.items():
        lista.sort(key=lambda p: p.data_pesagem)
        primeira, ultima = lista[0], lista[-1]
        dias_totais = (ultima.data_pesagem - primeira.data_pesagem).days
        gmd = round((ultima.peso_kg - primeira.peso_kg) / dias_totais, 3) if dias_totais > 0 else None

        taxas = []
        for anterior, atual in zip(lista, lista[1:]):
            dias = (atual.data_pesagem - anterior.data_pesagem).days
            if dias > 0:
                taxas.append((atual.peso_kg - anterior.peso_kg) / dias)
        gpd = round(sum(taxas) / len(taxas), 3) if taxas else None

        linhas.append({
            "numero_matriz": numero,
            "grupo_primario": ultima.grupo_primario,
            "primeira_data": primeira.data_pesagem.isoformat(),
            "primeira_peso": primeira.peso_kg,
            "ultima_data": ultima.data_pesagem.isoformat(),
            "ultima_peso": ultima.peso_kg,
            "gmd_kg_dia": gmd,
            "gpd_kg_dia": gpd,
            "num_pesagens": len(lista),
        })

    linhas.sort(key=lambda l: chave_numero(l["numero_matriz"]))
    return {"linhas": linhas, "total": len(linhas)}


class QualidadeLeiteIn(BaseModel):
    numero_matriz: str | None = None  # vazio = leitura do tanque (todas as vacas em lactação)
    data_coleta: date
    ccs: float | None = None
    cbt: float | None = None
    gordura_pct: float | None = None
    proteina_pct: float | None = None
    solidos_totais_pct: float | None = None
    esd_pct: float | None = None
    lactose_pct: float | None = None
    observacao: str | None = None


@router.get("/qualidade-leite")
def listar_qualidade_leite(session: Session = Depends(get_session)) -> dict:
    registros = session.exec(select(QualidadeLeite).order_by(QualidadeLeite.data_coleta)).all()
    return {"registros": [r.model_dump() for r in registros], "total": len(registros)}


@router.post("/qualidade-leite", status_code=201)
def criar_qualidade_leite(dados: QualidadeLeiteIn, session: Session = Depends(get_session)) -> dict:
    registro = QualidadeLeite(**dados.model_dump())
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


class EntregaLeiteMensalIn(BaseModel):
    competencia: str  # "YYYY-MM"
    quantidade_litros: float
    observacao: str | None = None


@router.get("/entrega-leite")
def listar_entrega_leite(session: Session = Depends(get_session)) -> dict:
    registros = session.exec(select(EntregaLeiteMensal).order_by(EntregaLeiteMensal.competencia)).all()
    return {"registros": [r.model_dump() for r in registros], "total": len(registros)}


@router.post("/entrega-leite", status_code=201)
def criar_entrega_leite(dados: EntregaLeiteMensalIn, session: Session = Depends(get_session)) -> dict:
    existente = session.exec(select(EntregaLeiteMensal).where(EntregaLeiteMensal.competencia == dados.competencia)).first()
    if existente:
        existente.quantidade_litros = dados.quantidade_litros
        existente.observacao = dados.observacao
        session.add(existente)
        session.commit()
        session.refresh(existente)
        return existente.model_dump()
    registro = EntregaLeiteMensal(**dados.model_dump())
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


def _competencia(d: date | None) -> str | None:
    return f"{d.year:04d}-{d.month:02d}" if d else None


@router.get("/relatorio-leite-italac")
def relatorio_leite_italac(session: Session = Depends(get_session)) -> dict:
    """Compara, por competência (mês), o controle leiteiro pesado, a entrega mensal
    lançada e a receita/volume faturado pela ITALAC (contas gerenciais com
    fornecedor/cliente contendo "italac"). Projeta também o consumo de leite pelas
    bezerras/bezerros com base na dieta atual, para estimar o que sobra do "não
    entregue" como consumo da fazenda/equipe."""
    controles = session.exec(select(ControleLeiteiro)).all()
    entregas = session.exec(select(EntregaLeiteMensal)).all()
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.tipo == "receita")).all()
    qualidades = session.exec(select(QualidadeLeite)).all()

    controle_por_mes: dict[str, dict] = {}
    for c in controles:
        comp = _competencia(c.data_controle)
        if not comp or c.producao_kg is None:
            continue
        acc = controle_por_mes.setdefault(comp, {"kg": 0.0, "n": 0})
        acc["kg"] += c.producao_kg
        acc["n"] += 1

    entrega_por_mes = {e.competencia: e.quantidade_litros for e in entregas}

    contas_italac = [c for c in contas if "italac" in (c.fornecedor_cliente or "").lower()]
    # CSV importado costuma preencher quantidade direto na conta; lançamento manual
    # guarda a quantidade no(s) item(ns) da nota — cai para a soma dos itens nesse caso.
    numeros_sem_quantidade = {c.numero_lancamento for c in contas_italac if not c.quantidade and c.numero_lancamento}
    quantidade_por_numero: dict[str, float] = {}
    if numeros_sem_quantidade:
        itens = session.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento.in_(numeros_sem_quantidade))).all()
        for item in itens:
            quantidade_por_numero[item.numero_lancamento] = quantidade_por_numero.get(item.numero_lancamento, 0.0) + (item.quantidade or 0.0)

    italac_por_mes: dict[str, dict] = {}
    for c in contas_italac:
        comp = _competencia(c.data_competencia)
        if not comp:
            continue
        litros = c.quantidade or quantidade_por_numero.get(c.numero_lancamento or "", 0.0)
        acc = italac_por_mes.setdefault(comp, {"litros": 0.0, "receita": 0.0})
        acc["litros"] += litros
        acc["receita"] += c.valor_total or 0.0

    qualidade_por_mes: dict[str, list[QualidadeLeite]] = {}
    for q in qualidades:
        comp = _competencia(q.data_coleta)
        if comp:
            qualidade_por_mes.setdefault(comp, []).append(q)

    # Consumo de leite pelas bezerras/bezerros — projeção a partir da dieta atual
    # (mesma lógica do painel de Alimentação), incluindo machos e fêmeas.
    dietas = [d.model_dump() for d in session.exec(select(Dieta)).all()]
    animais = [
        a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
        if not a.eh_semen
    ]
    consumo = calcular_consumo(dietas, animais)
    litros_dia_bezerros = 0.0
    efetivo_bezerros = 0
    for lote_info in consumo["por_lote"]:
        if "bezerr" not in (lote_info.get("categoria") or "").lower():
            continue
        efetivo_bezerros += lote_info["efetivo"]
        for item in lote_info["itens"]:
            if "leite" in (item["ingrediente"] or "").lower():
                litros_dia_bezerros += item["consumo_dia"]
    litros_mes_bezerros = round(litros_dia_bezerros * 30, 1)

    competencias = sorted(set(controle_por_mes) | set(entrega_por_mes) | set(italac_por_mes))
    linhas = []
    for comp in competencias:
        kg_controle = round(controle_por_mes[comp]["kg"], 1) if comp in controle_por_mes else None
        litros_entrega = entrega_por_mes.get(comp)
        italac = italac_por_mes.get(comp)
        litros_italac = round(italac["litros"], 1) if italac else None
        receita_italac = round(italac["receita"], 2) if italac else None
        preco_medio = round(receita_italac / litros_italac, 4) if litros_italac else None

        qs = qualidade_por_mes.get(comp, [])
        ccs_vals = [q.ccs for q in qs if q.ccs is not None]
        gordura_vals = [q.gordura_pct for q in qs if q.gordura_pct is not None]

        nao_entregue = round(kg_controle - litros_entrega, 1) if (kg_controle is not None and litros_entrega is not None) else None
        consumo_outros = round(nao_entregue - litros_mes_bezerros, 1) if nao_entregue is not None else None

        linhas.append({
            "competencia": comp,
            "controle_leiteiro_kg": kg_controle,
            "controles_no_mes": controle_por_mes.get(comp, {}).get("n", 0),
            "entrega_litros": litros_entrega,
            "italac_litros": litros_italac,
            "italac_receita": receita_italac,
            "preco_medio_litro": preco_medio,
            "ccs_medio": round(sum(ccs_vals) / len(ccs_vals), 1) if ccs_vals else None,
            "gordura_media_pct": round(sum(gordura_vals) / len(gordura_vals), 2) if gordura_vals else None,
            "nao_entregue_kg": nao_entregue,
            "consumo_bezerros_estimado_litros": litros_mes_bezerros if nao_entregue is not None else None,
            "consumo_outros_estimado_litros": consumo_outros,
        })

    return {
        "linhas": linhas,
        "efetivo_bezerros": efetivo_bezerros,
        "consumo_bezerros_dia_litros": round(litros_dia_bezerros, 1),
        "consumo_bezerros_mes_litros": litros_mes_bezerros,
    }


def _rotulo_lote(codigo: str, nome: str) -> str:
    return f"{codigo} - {nome}"


def _lote_das_secas(session: Session) -> dict | None:
    """
    O lote de vacas secas é o único configurado com status_lactacao="seca" —
    não dá pra usar o motor geral de critérios aqui porque a categoria/status
    do animal na ficha só é atualizada no próximo upload do GERAL.csv, não na
    hora do lançamento manual de secagem.
    """
    lote = session.exec(select(Lote).where(Lote.status_lactacao == "seca")).first()
    if not lote:
        return None
    return {"codigo": lote.codigo, "nome": lote.nome, "rotulo": _rotulo_lote(lote.codigo, lote.nome)}


@router.get("/secagem-info")
def info_secagem(numero_matriz: str, session: Session = Depends(get_session)) -> dict:
    """DEL atual, data prevista de secagem e o lote sugerido para a vaca secar."""
    animal = session.exec(select(Animal).where(Animal.numero == numero_matriz)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    ultimo_servico = session.exec(
        select(Servico)
        .where(Servico.numero_matriz == numero_matriz, Servico.diagnostico == "POSITIVO")
        .order_by(Servico.data_servico.desc())
    ).first()

    data_prevista = None
    deve_secar = None
    motivo_exclusao = None
    if ultimo_servico and ultimo_servico.data_servico:
        res_gest = calcular_parto_provavel(ultimo_servico.data_servico, animal.raca)
        em_lactacao = bool(animal.del_dias and animal.del_dias > 0)
        res_sec = calcular_secagem(numero_matriz, res_gest.data_parto_provavel, ultimo_servico.ordem_parto, em_lactacao)
        data_prevista = res_sec.data_secagem.isoformat()
        deve_secar = res_sec.deve_secar
        motivo_exclusao = res_sec.motivo_exclusao

    return {
        "numero_matriz": numero_matriz,
        "del_atual": animal.del_dias,
        "lote_atual": animal.grupo_primario,
        "data_prevista_secagem": data_prevista,
        "deve_secar": deve_secar,
        "motivo_exclusao": motivo_exclusao,
        "lote_sugerido": _lote_das_secas(session),
    }


class ItemSecagemIn(BaseModel):
    produto: str
    via: str | None = None
    quantidade: float
    unidade: str


class SecagemIn(BaseModel):
    numero_matriz: str
    data_secagem: date
    motivo: str
    escore_condicao_corporal: float | None = None
    observacao: str | None = None
    responsavel: str | None = None
    produtos: list[ItemSecagemIn] = []
    # Igual à Aplicação de Sanidade: se o produto de secagem ainda não foi
    # aplicado (ou a data é futura), não baixa estoque agora — vira uma
    # aplicação programada na Agenda, que baixa ao confirmar.
    aplicado: bool = True


@router.post("/secagem")
def registrar_secagem(dados: SecagemIn, session: Session = Depends(get_session)) -> dict:
    if dados.motivo not in MOTIVOS_SECAGEM:
        raise HTTPException(status_code=400, detail=f"Motivo inválido (aceitos: {', '.join(MOTIVOS_SECAGEM)})")
    if dados.escore_condicao_corporal is not None and not (1 <= dados.escore_condicao_corporal <= 5):
        raise HTTPException(status_code=400, detail="Escore de condição corporal deve ser entre 1 e 5")

    session.add(Secagem(
        numero_matriz=dados.numero_matriz,
        data_secagem=dados.data_secagem,
        motivo=dados.motivo,
        escore_condicao_corporal=dados.escore_condicao_corporal,
        observacao=dados.observacao,
    ))

    # Data futura ou "ainda não apliquei" → os produtos de secagem não baixam
    # estoque agora; viram aplicações programadas (Agenda/pendências).
    materializar = dados.aplicado and dados.data_secagem <= date.today()

    avisos: list[str] = []
    for item in dados.produtos:
        estoque_item = session.exec(select(Estoque).where(Estoque.nome == item.produto)).first()
        compativeis = unidades_compativeis(estoque_item.unidade if estoque_item else None)
        if item.unidade not in compativeis:
            raise HTTPException(
                status_code=400,
                detail=f'Unidade "{item.unidade}" não é compatível com o produto "{item.produto}" (aceitas: {", ".join(compativeis)})',
            )
        if not materializar:
            session.add(AplicacaoAgendada(
                numero_matriz=dados.numero_matriz, data=dados.data_secagem, produto=item.produto,
                dose=item.quantidade, unidade=item.unidade, via=item.via, responsavel=dados.responsavel,
                observacao="Secagem", aplicado=False,
            ))
            continue
        session.add(Sanidade(
            numero_matriz=dados.numero_matriz,
            data_aplicacao=dados.data_secagem,
            produto=item.produto,
            dose=item.quantidade,
            unidade=item.unidade,
            via=item.via,
            responsavel=dados.responsavel,
            atividade="Secagem",
        ))
        if estoque_item and estoque_item.estocavel is not False and pode_dar_baixa_direta(item.unidade, estoque_item.unidade):
            estoque_item.quantidade = (estoque_item.quantidade or 0) - item.quantidade
            if estoque_item.estoque_minimo is not None:
                estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
            estoque_item.atualizado_em = datetime.utcnow()
            session.add(estoque_item)
        elif estoque_item and estoque_item.unidade and estoque_item.unidade != item.unidade:
            avisos.append(
                f'Baixa de estoque de "{item.produto}" não aplicada — cadastre a equivalência entre '
                f'"{item.unidade}" e "{estoque_item.unidade}" (unidade de estoque do produto).'
            )

    if dados.produtos and not materializar:
        avisos.append("Produto(s) de secagem programado(s) na Agenda — o estoque baixa quando você confirmar a aplicação.")

    session.commit()
    return {"criado": True, "avisos": avisos, "programado": not materializar, "lote_sugerido": _lote_das_secas(session)}


class SugestaoLoteEventoIn(BaseModel):
    numero_matriz: str
    categoria_abrev: str  # "Vaca" | "Novilha" | "Bezerra" | "Bezerro"
    del_dias: int | None = None
    data_nasc: date | None = None


@router.post("/sugestao-lote-evento")
def sugestao_lote_evento(dados: SugestaoLoteEventoIn, session: Session = Depends(get_session)) -> dict:
    """
    Sugere um lote para um animal num evento de vida (nascimento ou parto),
    aplicando os critérios já cadastrados (Configurações > Cadastro > Lotes)
    ao estado REAL do animal nesse momento (idade 0 ao nascer, DEL 0 ao parir),
    mesmo que a ficha ainda não tenha sido atualizada pelo próximo GERAL.csv.
    """
    lotes = [l for l in session.exec(select(Lote)).all() if lote_tem_criterio(l)]
    _, servicos_por_animal, sanidades_por_animal, peso_por_animal = coletar_dados_criterios(session)

    hoje = date.today()
    animal_dict = {
        "numero": dados.numero_matriz,
        "categoria_abrev": dados.categoria_abrev,
        "categoria_completa": dados.categoria_abrev,
        "del_dias": dados.del_dias,
        "data_nasc": dados.data_nasc or hoje,
        "sit_rep": None,
        "diagnostico": None,
        "ult_cl_kg": None,
    }
    for lote in lotes:
        if animal_atende_criterios(lote, animal_dict, hoje, peso_por_animal, servicos_por_animal, sanidades_por_animal):
            return {"lote_sugerido": {"codigo": lote.codigo, "nome": lote.nome, "rotulo": _rotulo_lote(lote.codigo, lote.nome)}}
    return {"lote_sugerido": None}
