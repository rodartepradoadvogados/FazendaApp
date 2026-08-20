"""
Router do módulo RECRIA — Dossiê de Desempenho Zootécnico (bezerras/novilhas).

Entrega, sobre os dados que a fazenda já lança:
 - Pilar Saúde: curva 'casos de doença por idade (dias)' + ponto crítico +
   incidência por fase (motor de coorte).
 - Pilar Crescimento: peso real médio por mês × faixa de peso-alvo cadastrada.
 - Lançamento de ocorrências clínicas (casos) e os cadastros do módulo
   (metas, curva de peso-alvo, fases de idade, janelas de ponto crítico).

Tudo pensado para uso simples: seletor de doença, botões, tabelas claras.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Animal, BenchmarkRecria, CategoriaManejo, Doenca, FaseRecria, JanelaPontoCritico, MetaRecria, OcorrenciaClinica,
    Parto, PesagemCorporal, PesoAlvoIdade, RegistroCocho, Secagem, Servico, Usuario,
)
from fazenda.parsers.utils import iter_planilha_rows, normalizar_cabecalho, parse_date, parse_float, valor_por_apelido
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.estado_reprodutivo import APTA, ATRASADA, GESTANTE, INSEMINADA, classificar_animal
from fazenda.rules.gestation import dias_gestacao_da_raca
from fazenda.rules.parametros import (
    get_param, idade_apta_min_meses, idade_max_1a_cobertura_meses, peso_apta_min,
    pev_dias as pev_dias_param,
)
from fazenda.rules.planilha_modelo import gerar_modelo_xlsx
from fazenda.rules.coorte import (
    FASES_PADRAO, curva_casos_por_idade, idade_em_dias, incidencia_por_fase, ponto_critico,
)
from fazenda.rules.visibilidade import visivel
from fazenda.rules.reproducao_dossie import (
    DIAS_MES, custo_recria_excedente, distribuicao_idade_parto, estatisticas_idade_parto,
)
from fazenda.rules.programa_reprodutivo import calcular_series, ciclos_21_dias

router = APIRouter(prefix="/recria", tags=["recria"])


# --- Helpers ---------------------------------------------------------------
def _nascimentos(session: Session, fazenda_id: int | None = None) -> dict[str, date]:
    """numero -> data de nascimento (só animais com data)."""
    query = select(Animal)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    return {
        a.numero: a.data_nasc
        for a in session.exec(query).all()
        if a.data_nasc and not a.eh_semen
    }


def _idade_atual(session: Session, hoje: date, fazenda_id: int | None = None) -> dict[str, int]:
    """numero -> idade em dias hoje (ou na data de baixa, se já saiu)."""
    query = select(Animal)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    out: dict[str, int] = {}
    for a in session.exec(query).all():
        if not a.data_nasc or a.eh_semen:
            continue
        ref = a.data_baixa if (a.data_baixa and not a.ativo) else hoje
        out[a.numero] = (ref - a.data_nasc).days
    return out


def _fases(session: Session, fazenda_id: int | None = None) -> list[dict]:
    query = select(FaseRecria).where(FaseRecria.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(FaseRecria.fazenda_id == fazenda_id)
    linhas = session.exec(query).all()
    if not linhas:
        return FASES_PADRAO
    return [{"nome": f.nome, "dia_min": f.dia_min, "dia_max": f.dia_max}
            for f in sorted(linhas, key=lambda x: (x.ordem, x.dia_min))]


def _texto_doenca_do_catalogo(session: Session, doenca_id: int | None, fazenda_id: int | None) -> str | None:
    """Nome da Doenca do catálogo (visível pela fazenda: global + a própria) —
    usado para denormalizar o texto (`doenca`) a partir do vínculo
    (`doenca_id`) escolhido no seletor, em vez de confiar no texto digitado.
    None se o id não vier, não existir ou não for visível por esta fazenda."""
    if doenca_id is None:
        return None
    d = session.exec(visivel(select(Doenca).where(Doenca.id == doenca_id), Doenca, fazenda_id)).first()
    return d.nome if d else None


# --- Pilar Saúde -----------------------------------------------------------
@router.get("/doencas")
def listar_doencas_com_casos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Doenças que já têm ocorrências lançadas (para o seletor do Dossiê)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(OcorrenciaClinica)
    if fazenda_id is not None:
        query = query.where(OcorrenciaClinica.fazenda_id == fazenda_id)
    cont: dict[str, int] = {}
    for o in session.exec(query).all():
        cont[o.doenca] = cont.get(o.doenca, 0) + 1
    return [{"doenca": d, "casos": cont[d]} for d in sorted(cont)]


@router.get("/saude/curva")
def curva_saude(
    doenca: str, ini: date | None = None, fim: date | None = None,
    limite_dias: int = 300, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Curva casos×idade (dias) + ponto crítico + incidência por fase."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nasc = _nascimentos(session, fazenda_id)
    query = select(OcorrenciaClinica).where(OcorrenciaClinica.doenca == doenca)
    if fazenda_id is not None:
        query = query.where(OcorrenciaClinica.fazenda_id == fazenda_id)
    ocorrencias = [
        o for o in session.exec(query).all()
        if (not ini or o.data_ocorrencia >= ini) and (not fim or o.data_ocorrencia <= fim)
    ]
    pares = []  # (numero, idade_dias)
    for o in ocorrencias:
        idade = idade_em_dias(nasc.get(o.numero_matriz), o.data_ocorrencia)
        if idade is not None:
            pares.append((o.numero_matriz, idade))

    curva = curva_casos_por_idade([p[1] for p in pares], limite_dias=limite_dias)
    pc = ponto_critico(curva)
    fases = _fases(session, fazenda_id)
    incid = incidencia_por_fase(pares, _idade_atual(session, date.today(), fazenda_id), fases)
    return {
        "doenca": doenca,
        "total_casos": len(pares),
        "curva": curva,
        "ponto_critico": pc,
        "incidencia_por_fase": incid,
    }


# --- Pilar Crescimento -----------------------------------------------------
@router.get("/crescimento/peso-alvo")
def crescimento_peso_alvo(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Peso real médio por mês de idade × faixa de peso-alvo cadastrada."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nasc = _nascimentos(session, fazenda_id)
    # Peso real: média das pesagens agrupadas por mês de idade na data da pesagem.
    pesagens_query = select(PesagemCorporal)
    if fazenda_id is not None:
        pesagens_query = pesagens_query.where(PesagemCorporal.fazenda_id == fazenda_id)
    por_mes: dict[int, list[float]] = {}
    for p in session.exec(pesagens_query).all():
        if not p.peso_kg or not p.data_pesagem:
            continue
        d = idade_em_dias(nasc.get(p.numero_matriz), p.data_pesagem)
        if d is None:
            continue
        mes = max(1, round(d / 30.44))
        por_mes.setdefault(mes, []).append(p.peso_kg)

    alvo_query = select(PesoAlvoIdade)
    if fazenda_id is not None:
        alvo_query = alvo_query.where(PesoAlvoIdade.fazenda_id == fazenda_id)
    alvo = {a.mes: (a.peso_min_kg, a.peso_max_kg) for a in session.exec(alvo_query).all()}
    meses = sorted(set(por_mes) | set(alvo))
    linhas = []
    for m in meses:
        reais = por_mes.get(m, [])
        faixa = alvo.get(m)
        media = round(sum(reais) / len(reais), 1) if reais else None
        dentro = None
        if media is not None and faixa:
            dentro = faixa[0] <= media <= faixa[1]
        linhas.append({
            "mes": m, "peso_medio_real": media, "n_pesagens": len(reais),
            "peso_min_alvo": faixa[0] if faixa else None,
            "peso_max_alvo": faixa[1] if faixa else None,
            "dentro_do_alvo": dentro,
        })
    return {"linhas": linhas}


def _meta_recria(session: Session, fazenda_id: int | None) -> MetaRecria:
    """Metas da fazenda informada — get-or-create por `fazenda_id` (era um
    singleton id=1 global; agora uma linha por fazenda, mesmo padrão de
    `ParametroDiariaPadrao`, ver fazenda/models/recria.py::MetaRecria)."""
    query = select(MetaRecria)
    query = query.where(MetaRecria.fazenda_id == fazenda_id) if fazenda_id is not None else query.where(
        MetaRecria.fazenda_id.is_(None)
    )
    meta = session.exec(query).first()
    if not meta:
        meta = MetaRecria(fazenda_id=fazenda_id)
        session.add(meta)
        session.commit()
        session.refresh(meta)
    return meta


# --- Pilar Reprodução ------------------------------------------------------
@router.get("/reproducao/idade-parto")
def reproducao_idade_parto(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Relatório Wisconsin: estatística da idade ao 1º parto + distribuição +
    custo de recria excedente (usa a meta e o custo diário cadastrados)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nasc = _nascimentos(session, fazenda_id)
    # 1º parto de cada animal = parto de ordem 1, ou o mais antigo se não houver ordem.
    partos_query = select(Parto)
    if fazenda_id is not None:
        partos_query = partos_query.where(Parto.fazenda_id == fazenda_id)
    primeiro: dict[str, date] = {}
    for p in session.exec(partos_query).all():
        if not p.data_parto or not p.numero_matriz:
            continue
        num = p.numero_matriz
        if p.ordem_parto == 1:
            primeiro[num] = p.data_parto
        elif num not in primeiro or p.data_parto < primeiro[num]:
            primeiro.setdefault(num, p.data_parto)
            if p.data_parto < primeiro[num]:
                primeiro[num] = p.data_parto

    idades = []
    for num, dparto in primeiro.items():
        dn = nasc.get(num)
        if dn:
            idades.append((dparto - dn).days / DIAS_MES)

    meta = _meta_recria(session, fazenda_id)
    return {
        "meta_idade_parto": meta.idade_parto_meses,
        "meta_desvio_padrao": meta.desvio_padrao_meta,
        "estatisticas": estatisticas_idade_parto(idades),
        "distribuicao": distribuicao_idade_parto(idades),
        "custo_excedente": custo_recria_excedente(idades, meta.idade_parto_meses, meta.custo_diario_recria),
    }


@router.get("/reproducao/taxa-prenhez")
def reproducao_taxa_prenhez(
    ini: date, fim: date, vwp_dias: int = 0, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Risco de prenhez das NOVILHAS em ciclos de 21 dias (BREDSUM\\E).

    Passou a usar `fazenda.rules.programa_reprodutivo` — o mesmo motor da tela
    de Reprodução, aqui filtrado em novilhas. O cálculo anterior
    (`reproducao_dossie.taxa_prenhez_ciclos`, removido) usava "os próprios
    serviços como universo de animais avaliáveis": a novilha elegível que
    atravessou o ciclo sem ser inseminada não tinha linha de `Servico` e sumia
    do denominador, inflando a taxa de serviço. Também derivava a taxa de
    prenhez de serviço × concepção, atalho que o DairyComp não faz.

    Os números desta tela mudam em relação ao que era exibido antes — é a
    correção, não um efeito colateral.
    """
    from fazenda.api.routers.reproducao import carregar_perfis_reprodutivos
    from fazenda.rules.parametros import (
        dias_minimos_no_ciclo, dias_resultado_conhecido, get_param,
        idade_apta_min_meses, pev_dias, peso_apta_min,
    )

    fazenda_id = fazenda_id_seguro(fazenda_id)
    perfis = carregar_perfis_reprodutivos(session, fazenda_id, categoria="novilha")

    # A janela pedida vira uma série de ciclos de 21 dias a partir de `ini`.
    dias_periodo = max((fim - ini).days + 1, 1)
    n_ciclos = max((dias_periodo + 20) // 21, 1)
    ciclos = ciclos_21_dias(ini, modo="inicio", n_ciclos=n_ciclos)

    resultados = calcular_series(
        perfis, ciclos, date.today(),
        # `vwp_dias` continua sendo o override de PEV desta tela (novilha
        # nulípara não tem parto, então o PEV do rebanho não se aplica a ela).
        pev_dias=vwp_dias or pev_dias(),
        dias_minimos=dias_minimos_no_ciclo(),
        dias_resultado=dias_resultado_conhecido(),
        # Janela mínima de cio de repasse — a mesma que a tela de Reprodução
        # já usa. Sem passar aqui, o motor cairia no piso embutido e o campo
        # editável em Configurações não faria efeito nenhum (foi por ser um
        # campo assim, editável e inerte, que `idade_maturidade_novilha` foi
        # aposentado).
        dias_minimos_repasse=dias_reinseminacao_min(),
        del_max_1o_servico=int(get_param("meta_del_max_1o_servico", 100) or 100),
        idade_apta_dias=int(idade_apta_min_meses() * 30.44),
        idade_atraso_dias=int(idade_max_1a_cobertura_meses() * 30.44),
        peso_apta_kg=peso_apta_min(),
    )

    linhas = []
    for r in resultados:
        d = r.para_dict()
        linhas.append({
            **d,
            # Nomes que a tela de Recria já consome (RecriaCiclo no front) —
            # mantidos para não quebrar o contrato, agora com o valor correto.
            "elegiveis": d["br_elig"],
            "servidos": d["bred"],
            "prenhes": d["preg"],
        })

    # Resumo do período: prenhez média ponderada pelo denominador de cada ciclo.
    tot_pg = sum(l["pg_elig"] for l in linhas)
    tot_pr = sum((l["taxa_prenhez"] or 0) * l["pg_elig"] for l in linhas)
    meta = _meta_recria(session, fazenda_id)
    return {
        "ciclos": linhas,
        "taxa_prenhez_media": round(tot_pr / tot_pg, 1) if tot_pg else None,
        "total_servicos": sum(l["bred"] for l in linhas),
        "meta_taxa_prenhez": meta.taxa_prenhez_meta,
        "animais_avaliados": len(perfis),
    }


# --- Dossiê Zootécnico (montador do PDF) -----------------------------------
@router.get("/dossie")
def montar_dossie(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Reúne, num único pacote, tudo que compõe o Dossiê Zootécnico da recria —
    saúde (incidência por fase), crescimento (peso real × alvo), reprodução
    (idade ao 1º parto/Wisconsin + custo excedente) e composição por categoria.
    Devolve KPIs de capa e uma lista de seções (título + colunas + linhas) já no
    formato que o front usa para montar o PDF de várias páginas.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = date.today()
    nasc = _nascimentos(session, fazenda_id)

    # Crescimento: peso real × alvo por mês de idade (reusa a mesma lógica).
    crescimento = crescimento_peso_alvo(session, fazenda_id)["linhas"]

    # Reprodução: idade ao 1º parto (Wisconsin) + custo excedente.
    repro = reproducao_idade_parto(session, fazenda_id)
    est = repro.get("estatisticas") or {}
    custo = repro.get("custo_excedente") or {}

    # Composição por categoria de manejo.
    comp = composicao_categorias(session, fazenda_id)["composicao"]

    # Saúde: incidência por fase, somada sobre todas as doenças lançadas.
    fases = _fases(session, fazenda_id)
    ocorrencias_query = select(OcorrenciaClinica)
    if fazenda_id is not None:
        ocorrencias_query = ocorrencias_query.where(OcorrenciaClinica.fazenda_id == fazenda_id)
    casos_por_animal_idade = []
    for o in session.exec(ocorrencias_query).all():
        if not o.data_ocorrencia:
            continue
        d = idade_em_dias(nasc.get(o.numero_matriz), o.data_ocorrencia)
        if d is not None:
            casos_por_animal_idade.append((o.numero_matriz, d))
    idade_atual = _idade_atual(session, hoje, fazenda_id)
    incidencia = incidencia_por_fase(casos_por_animal_idade, idade_atual, fases)

    secoes = [
        {
            "titulo": "Composição atual do rebanho por categoria de manejo",
            "colunas": [{"header": "Categoria", "key": "categoria"}, {"header": "Animais", "key": "n"}],
            "linhas": comp,
        },
        {
            "titulo": "Crescimento — peso real médio × peso-alvo por idade",
            "colunas": [
                {"header": "Idade (meses)", "key": "mes"}, {"header": "Peso real (kg)", "key": "peso_medio_real"},
                {"header": "Alvo mín (kg)", "key": "peso_min_alvo"}, {"header": "Alvo máx (kg)", "key": "peso_max_alvo"},
                {"header": "Pesagens", "key": "n_pesagens"}, {"header": "Dentro do alvo", "key": "dentro_txt"},
            ],
            "linhas": [
                {**l, "dentro_txt": ("—" if l["dentro_do_alvo"] is None else "Sim" if l["dentro_do_alvo"] else "Não")}
                for l in crescimento
            ],
        },
        {
            "titulo": "Saúde — incidência de doenças por fase de vida",
            "colunas": [
                {"header": "Fase", "key": "fase"}, {"header": "Casos", "key": "casos"},
                {"header": "Animais em risco", "key": "animais_em_risco"}, {"header": "Incidência (%)", "key": "incidencia_pct"},
            ],
            "linhas": incidencia,
        },
        {
            "titulo": "Reprodução — distribuição da idade ao 1º parto",
            "colunas": [
                {"header": "Idade (meses)", "key": "mes"}, {"header": "Animais", "key": "n"}, {"header": "%", "key": "pct"},
            ],
            "linhas": [l for l in (repro.get("distribuicao") or []) if l.get("n")],
        },
    ]

    return {
        "gerado_em": hoje.isoformat(),
        "kpis": {
            "meta_idade_parto": repro.get("meta_idade_parto"),
            "idade_media_1o_parto": est.get("media"),
            "desvio_idade_parto": est.get("desvio_padrao"),
            "n_animais_1o_parto": est.get("n"),
            "custo_excedente_total": custo.get("custo_total"),
            "dias_excedentes_medios": custo.get("dias_por_novilha"),
            "total_recria": sum(c["n"] for c in comp) if comp else 0,
        },
        "secoes": [s for s in secoes if s["linhas"]],
    }


# --- Parâmetros de categoria de manejo -------------------------------------
GESTACAO_DIAS_CATEGORIA = 280  # gestação média — mesma referência de fazenda.rules.relatorios_gerenciais


def _parametros_estado_vivo() -> tuple[int, int, int, float, int]:
    """(pev_dias, del_max_1o_servico, idade_apta_dias, peso_apta_kg,
    idade_atraso_dias) lidos uma
    vez só — cada chamador desta função (composicao_categorias, ficha do
    animal, critérios de lote) roda `classificar_animal` em loop por animal,
    e cada parâmetro lido por `get_param`/os acessores de parametros.py abre
    uma sessão de banco própria (ver mesmo cuidado em eventos_sanitarios.py e
    agenda.py::calcular_agenda) — ler dentro do loop multiplicaria a mesma
    consulta uma vez por animal."""
    del_max = int(get_param("meta_del_max_1o_servico", 100) or 100)
    idade_apta_dias = round(idade_apta_min_meses() * 30.44)
    idade_atraso_dias = round(idade_max_1a_cobertura_meses() * 30.44)
    return pev_dias_param(), del_max, idade_apta_dias, peso_apta_min(), idade_atraso_dias


def _status_reprodutivo(estado_vivo: str | None) -> str:
    """Refina a categoria de aptidão legada (usa_status_reprodutivo) pelo
    estado reprodutivo AO VIVO (estado_reprodutivo.classificar_animal, motor
    canônico das regras R1-R9 do programa reprodutivo) — não mais pelo
    `sit_rep`, texto congelado do último GERAL.csv importado. Antes, uma
    novilha que engravidava pelo app continuava "Apta" (por eliminação sobre
    o texto velho) até o próximo upload de planilha."""
    if estado_vivo == GESTANTE:
        return "Gestante"
    if estado_vivo == INSEMINADA:
        return "Inseminada"
    return "Apta"


def _situacao_reprodutiva_3(estado_vivo: str | None) -> str | None:
    """Situação reprodutiva em 4 categorias (inseminada/vazia/vazia_atrasada/
    prenha — as 3 antigas mais o refinamento "vazia em atraso"), usada
    para casar com CategoriaManejo.situacao_reprodutiva — a partir do ESTADO
    AO VIVO (estado_reprodutivo.classificar_animal: GESTANTE/INSEMINADA/APTA/
    ATRASADA/PEV/EM_PROTOCOLO/NAO_APTA), não mais do `sit_rep` congelado do
    GERAL.csv (só mudava no próximo upload — uma vaca que engravidava pelo
    app continuava "vazia" pra sempre, até o próximo CSV, e alimentava a
    sugestão de movimentação de lote errada — ver rules.lote_criterios).

    "Vazia" = APTA ou ATRASADA (mesma convenção de relatorios_gerenciais.py e
    agenda_engine.py: livre para receber serviço) — a ATRASADA devolve o valor
    mais específico "vazia_atrasada", que continua sendo aceito por quem
    cadastrou "vazia" (ver `situacao_reprodutiva_casa`). PEV, EM_PROTOCOLO e
    NAO_APTA são estados reais, mas nenhum dos três é "vazia" (PEV é
    descanso obrigatório; EM_PROTOCOLO já está sendo trabalhada; NAO_APTA é
    novilha que ainda não deu a idade/peso) — por isso caem em None, igual a
    um estado desconhecido: não casam com NENHUM dos critérios cadastráveis
    (prenha/inseminada/vazia/vazia_atrasada), então não filtram nem devem
    "inventar" um bucket que não corresponde à realidade do animal."""
    if estado_vivo == GESTANTE:
        return "prenha"
    if estado_vivo == INSEMINADA:
        return "inseminada"
    if estado_vivo == ATRASADA:
        # "vazia_atrasada" é um REFINAMENTO de "vazia", não um bucket novo e
        # paralelo: quem casa por "vazia" continua casando com ela (ver
        # `situacao_reprodutiva_casa` logo abaixo). Sem esta distinção não
        # havia como cadastrar uma categoria/lote só para a novilha em atraso
        # — a única categoria "Vazia atrasada" semeada usa dias_pos_parto_min,
        # que nunca casa com nulípara (ela não tem parto, então não tem DEL).
        return "vazia_atrasada"
    if estado_vivo == APTA:
        return "vazia"
    return None


# Critério cadastrado -> situações vivas que ele aceita. "vazia" aceita também
# "vazia_atrasada" por RETROCOMPATIBILIDADE: toda categoria/lote já cadastrado
# com "vazia" (inclusive as sementes "Vazia atrasada" e "Liberada/apta")
# continua casando exatamente com os mesmos animais de antes, quando ATRASADA
# ainda era mapeada para "vazia". Só quem escolher explicitamente
# "vazia_atrasada" fica restrito às atrasadas.
_SITUACOES_REPRODUTIVAS_ACEITAS = {"vazia": ("vazia", "vazia_atrasada")}


def situacao_reprodutiva_casa(criterio: str | None, situacao_viva: str | None) -> bool:
    """O critério `situacao_reprodutiva` cadastrado (em CategoriaManejo ou em
    Lote) casa com a situação AO VIVO do animal (`_situacao_reprodutiva_3`)?
    Critério vazio = não filtra (sempre casa)."""
    if not criterio:
        return True
    return situacao_viva in _SITUACOES_REPRODUTIVAS_ACEITAS.get(criterio, (criterio,))


def _dentro_faixa(valor: int | float | None, minimo, maximo) -> bool:
    """Sem mínimo nem máximo cadastrados = critério não se aplica (sempre bate).
    Com algum limite cadastrado, exige que o animal tenha o valor calculado
    (ex.: só entra em 'dias de gestação' quem está prenhe) e que caiba na faixa."""
    if minimo is None and maximo is None:
        return True
    if valor is None:
        return False
    if minimo is not None and valor < minimo:
        return False
    if maximo is not None and valor > maximo:
        return False
    return True


def classificar_categoria(ctx: dict, categorias: list[CategoriaManejo]) -> str:
    """Categoria de manejo de um animal, cruzando idade/peso (sempre) com os
    critérios adicionais cadastrados (situação reprodutiva/produtiva, dias de
    gestação, dias desde o último serviço, dias para o parto provável, dias
    pós-parto) — um critério só filtra quando cadastrado (min/max ambos None
    = não filtra).
    Na categoria de aptidão legada (usa_status_reprodutivo), o status
    reprodutivo textual (Apta/Inseminada/Gestante) assume o nome da categoria."""
    dias = ctx.get("dias")
    if dias is None:
        return "Sem data de nascimento"
    peso = ctx.get("peso")
    sit_rep_3 = ctx.get("situacao_reprodutiva_viva")
    peso_faltou: CategoriaManejo | None = None
    for cat in sorted(categorias, key=lambda c: (c.ordem, c.dia_min)):
        if dias < cat.dia_min:
            continue
        if cat.dia_max is not None and dias > cat.dia_max:
            continue
        peso_baixo = cat.peso_min_kg is not None and (peso is None or peso < cat.peso_min_kg)
        peso_alto = cat.peso_max_kg is not None and peso is not None and peso > cat.peso_max_kg
        if peso_baixo or peso_alto:
            peso_faltou = peso_faltou or cat
            continue
        if not situacao_reprodutiva_casa(cat.situacao_reprodutiva, sit_rep_3):
            continue
        if cat.situacao_produtiva and cat.situacao_produtiva != ctx.get("situacao_produtiva"):
            continue
        if not _dentro_faixa(ctx.get("dias_gestacao"), cat.dias_gestacao_min, cat.dias_gestacao_max):
            continue
        if not _dentro_faixa(ctx.get("dias_desde_servico"), cat.dias_desde_servico_min, cat.dias_desde_servico_max):
            continue
        if not _dentro_faixa(ctx.get("dias_para_parto"), cat.dias_para_parto_min, cat.dias_para_parto_max):
            continue
        if not _dentro_faixa(ctx.get("dias_pos_parto"), cat.dias_pos_parto_min, cat.dias_pos_parto_max):
            continue
        if cat.usa_status_reprodutivo:
            return _status_reprodutivo(ctx.get("estado_vivo"))
        return cat.nome
    # Idade compatível com uma categoria, mas o peso ainda não alcançou o alvo.
    if peso_faltou is not None:
        return f"{peso_faltou.nome} (abaixo do peso)"
    return "Fora das faixas"


def _contexto_categoria(
    dias: int | None, peso: float | None, sit_rep: str | None, hoje: date,
    servicos: list[Servico], partos: list[Parto], secagens: list[Secagem],
    raca: str | None = None, numero: str | None = None,
    pev_dias: int | None = None, del_max_1o_servico: int | None = None,
    idade_apta_dias: int | None = None, peso_apta_kg: float | None = None,
    idade_atraso_dias: int | None = None,
) -> dict:
    """Monta o contexto de classificação de um animal a partir dos lançamentos
    já feitos (serviço/IA, parto, secagem) — mesma referência de cálculo de
    fazenda.rules.relatorios_gerenciais (concepção = data do serviço com
    diagnóstico positivo e sem perda de prenhez).

    `pev_dias`/`del_max_1o_servico`/`idade_apta_dias`/`peso_apta_kg`: os 4
    parâmetros que `estado_reprodutivo.classificar_animal` (chamado abaixo)
    precisa — opcionais aqui porque o chamador que roda em loop por animal
    (composicao_categorias, lote_criterios) já leu tudo uma vez via
    `_parametros_estado_vivo()` e passa pronto; só quando ausentes (ex.:
    chamada avulsa de um único animal) é que lemos aqui, na hora."""
    if pev_dias is None or del_max_1o_servico is None or idade_apta_dias is None or peso_apta_kg is None:
        _pev, _del_max, _idade_apta, _peso_apta, _idade_atraso = _parametros_estado_vivo()
        pev_dias = pev_dias if pev_dias is not None else _pev
        del_max_1o_servico = del_max_1o_servico if del_max_1o_servico is not None else _del_max
        idade_apta_dias = idade_apta_dias if idade_apta_dias is not None else _idade_apta
        idade_atraso_dias = idade_atraso_dias if idade_atraso_dias is not None else _idade_atraso
        peso_apta_kg = peso_apta_kg if peso_apta_kg is not None else _peso_apta
    servs = sorted((s for s in servicos if s.data_servico), key=lambda s: s.data_servico)
    ult_serv = servs[-1] if servs else None
    dias_desde_servico = (hoje - ult_serv.data_servico).days if ult_serv else None

    concep = None
    for s in reversed(servs):
        if (s.diagnostico or "").strip().upper() == "POSITIVO" and not s.data_perda_prenhez:
            concep = s.data_servico
            break
    dias_gestacao = (hoje - concep).days if concep else None
    # Dias de gestação variam por raça (Holandês 280, Girolando 287, Gir/
    # Zebu/Nelore 295 — ver fazenda.rules.gestation) — usar sempre 280 fixo
    # adiantava a classificação de pré-parto/seca em até 15 dias para raças
    # zebuínas. Mesma correção já aplicada em estado_reprodutivo.py,
    # relatorios_gerenciais.py e animais.py.
    dias_para_parto = (
        (dias_gestacao_da_raca(raca, GESTACAO_DIAS_CATEGORIA) - dias_gestacao) if dias_gestacao is not None else None
    )

    ult_parto = max((p.data_parto for p in partos if p.data_parto), default=None)
    ult_secagem = max((s.data_secagem for s in secagens if s.data_secagem), default=None)
    if ult_secagem and (not ult_parto or ult_secagem > ult_parto):
        situacao_produtiva = "seca"
    elif ult_parto:
        situacao_produtiva = "lactacao"
    else:
        situacao_produtiva = None  # novilha — nunca pariu, não se aplica
    dias_pos_parto = (hoje - ult_parto).days if ult_parto else None

    # Estado reprodutivo AO VIVO — mesmo motor canônico das regras R1-R9 do
    # programa reprodutivo (estado_reprodutivo.classificar_animal), em vez do
    # texto congelado de sit_rep (que só muda no próximo GERAL.csv — uma
    # vaca que engravidava pelo app continuava "vazia"/"apta" até o próximo
    # upload de planilha). `eh_vaca` = tem Parto registrado (mesma convenção
    # de relatorios_gerenciais._eh_vaca); sem categoria de texto disponível
    # aqui pra reforçar isso como o `estados_ao_vivo` em lote faz.
    #
    # `aplicacoes_iatf=[]`: este contexto não carrega o histórico de IATF (os
    # 3 chamadores — composição de categorias, ficha do animal e critérios de
    # lote — não pedem essa tabela) — o estado EM_PROTOCOLO nunca sai daqui;
    # um animal em protocolo aparece como PEV/APTA/ATRASADA, conforme o resto
    # dos dados. Consequência aceita: as categorias/lotes que dependem deste
    # contexto não distinguem "em protocolo" das demais novilhas/vacas aptas.
    estado_vivo = classificar_animal(
        numero or "", hoje=hoje, partos=partos, servicos=servicos, aplicacoes_iatf=[],
        pev_dias=pev_dias, del_max_1o_servico=del_max_1o_servico,
        eh_vaca=bool(ult_parto), idade_dias=dias, peso_kg=peso,
        idade_apta_dias=idade_apta_dias, peso_apta_kg=peso_apta_kg,
        idade_atraso_dias=idade_atraso_dias, raca=raca,
    )["estado"]

    return {
        "dias": dias, "peso": peso, "sit_rep": sit_rep,
        "estado_vivo": estado_vivo,
        "situacao_reprodutiva_viva": _situacao_reprodutiva_3(estado_vivo),
        "dias_gestacao": dias_gestacao, "dias_desde_servico": dias_desde_servico,
        "dias_para_parto": dias_para_parto, "dias_pos_parto": dias_pos_parto,
        "situacao_produtiva": situacao_produtiva,
    }


@router.get("/categorias/composicao")
def composicao_categorias(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Conta os animais ativos em cada categoria de manejo (idade/peso/status/
    situação reprodutiva-produtiva/dias de gestação/serviço/parto provável)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    categorias_query = select(CategoriaManejo).where(CategoriaManejo.ativo == True)  # noqa: E712
    pesagens_query = select(PesagemCorporal).order_by(PesagemCorporal.data_pesagem)
    servicos_query = select(Servico)
    partos_query = select(Parto)
    secagens_query = select(Secagem)
    animais_query = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        categorias_query = categorias_query.where(CategoriaManejo.fazenda_id == fazenda_id)
        pesagens_query = pesagens_query.where(PesagemCorporal.fazenda_id == fazenda_id)
        servicos_query = servicos_query.where(Servico.fazenda_id == fazenda_id)
        partos_query = partos_query.where(Parto.fazenda_id == fazenda_id)
        secagens_query = secagens_query.where(Secagem.fazenda_id == fazenda_id)
        animais_query = animais_query.where(Animal.fazenda_id == fazenda_id)

    categorias = session.exec(categorias_query).all()
    ult_peso: dict[str, float] = {}
    for p in session.exec(pesagens_query).all():
        if p.peso_kg:
            ult_peso[p.numero_matriz] = p.peso_kg  # a última pesagem (ordenada asc) prevalece
    servicos_idx: dict[str, list[Servico]] = {}
    for s in session.exec(servicos_query).all():
        if s.numero_matriz:
            servicos_idx.setdefault(s.numero_matriz, []).append(s)
    partos_idx: dict[str, list[Parto]] = {}
    for p in session.exec(partos_query).all():
        if p.numero_matriz:
            partos_idx.setdefault(p.numero_matriz, []).append(p)
    secagens_idx: dict[str, list[Secagem]] = {}
    for s in session.exec(secagens_query).all():
        if s.numero_matriz:
            secagens_idx.setdefault(s.numero_matriz, []).append(s)
    hoje = date.today()
    pev, del_max, idade_apta_dias, peso_apta_kg, idade_atraso_dias = _parametros_estado_vivo()
    cont: dict[str, int] = {}
    for a in session.exec(animais_query).all():
        if a.eh_semen or a.sexo == "M":
            continue
        dias = (hoje - a.data_nasc).days if a.data_nasc else None
        ctx = _contexto_categoria(
            dias, ult_peso.get(a.numero), a.sit_rep, hoje,
            servicos_idx.get(a.numero, []), partos_idx.get(a.numero, []), secagens_idx.get(a.numero, []),
            raca=a.raca, numero=a.numero,
            pev_dias=pev, del_max_1o_servico=del_max, idade_apta_dias=idade_apta_dias,
            peso_apta_kg=peso_apta_kg, idade_atraso_dias=idade_atraso_dias,
        )
        cat = classificar_categoria(ctx, categorias)
        cont[cat] = cont.get(cat, 0) + 1
    return {"composicao": [{"categoria": k, "n": cont[k]} for k in sorted(cont)], "total": sum(cont.values())}


@router.get("/categorias/animal/{numero}")
def categoria_sugerida_animal(
    numero: str, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Categoria de manejo sugerida para UM animal — usada para pré-preencher
    a categoria na ficha (Rebanho > editar), já que o animal segue os
    parâmetros cadastrados em Configurações > Cadastro > Categorias."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    animal_query = select(Animal).where(Animal.numero == numero)
    if fazenda_id is not None:
        animal_query = animal_query.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(animal_query).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    if animal.eh_semen or animal.sexo == "M":
        return {"categoria": None}
    categorias_query = select(CategoriaManejo).where(CategoriaManejo.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        categorias_query = categorias_query.where(CategoriaManejo.fazenda_id == fazenda_id)
    categorias = session.exec(categorias_query).all()
    hoje = date.today()
    dias = (hoje - animal.data_nasc).days if animal.data_nasc else None
    peso_query = select(PesagemCorporal).where(PesagemCorporal.numero_matriz == numero).order_by(PesagemCorporal.data_pesagem)
    secagens_query = select(Secagem).where(Secagem.numero_matriz == numero)
    if fazenda_id is not None:
        peso_query = peso_query.where(PesagemCorporal.fazenda_id == fazenda_id)
        secagens_query = secagens_query.where(Secagem.fazenda_id == fazenda_id)
    ult = session.exec(peso_query).all()
    peso = ult[-1].peso_kg if ult else None
    servicos_query = select(Servico).where(Servico.numero_matriz == numero)
    partos_query = select(Parto).where(Parto.numero_matriz == numero)
    if fazenda_id is not None:
        servicos_query = servicos_query.where(Servico.fazenda_id == fazenda_id)
        partos_query = partos_query.where(Parto.fazenda_id == fazenda_id)
    servicos = session.exec(servicos_query).all()
    partos = session.exec(partos_query).all()
    secagens = session.exec(secagens_query).all()
    ctx = _contexto_categoria(dias, peso, animal.sit_rep, hoje, servicos, partos, secagens, raca=animal.raca, numero=numero)
    return {"categoria": classificar_categoria(ctx, categorias)}


class CategoriaManejoIn(BaseModel):
    nome: str
    dia_min: int = 0
    dia_max: int | None = None
    peso_min_kg: float | None = None
    peso_max_kg: float | None = None
    usa_status_reprodutivo: bool = False
    situacao_reprodutiva: str | None = None
    situacao_produtiva: str | None = None
    dias_gestacao_min: int | None = None
    dias_gestacao_max: int | None = None
    dias_desde_servico_min: int | None = None
    dias_desde_servico_max: int | None = None
    dias_para_parto_min: int | None = None
    dias_para_parto_max: int | None = None
    dias_pos_parto_min: int | None = None
    dias_pos_parto_max: int | None = None
    ordem: int = 0
    ativo: bool = True


@router.get("/categorias")
def listar_categorias(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(CategoriaManejo).order_by(CategoriaManejo.ordem, CategoriaManejo.dia_min)
    if fazenda_id is not None:
        query = query.where(CategoriaManejo.fazenda_id == fazenda_id)
    linhas = session.exec(query).all()
    return [l.model_dump() for l in linhas]


@router.post("/categorias", status_code=201)
def criar_categoria(
    dados: CategoriaManejoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome da categoria.")
    c = CategoriaManejo(**dados.model_dump(), fazenda_id=fazenda_id)
    c.nome = dados.nome.strip()
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


@router.put("/categorias/{categoria_id}")
def atualizar_categoria(
    categoria_id: int, dados: CategoriaManejoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    c = session.get(CategoriaManejo, categoria_id)
    if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(c, campo, valor)
    c.nome = dados.nome.strip()
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


@router.delete("/categorias/{categoria_id}")
def excluir_categoria(
    categoria_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    c = session.get(CategoriaManejo, categoria_id)
    if c and (fazenda_id is None or c.fazenda_id == fazenda_id):
        session.delete(c)
        session.commit()
    return {"ok": True}


# --- Pilar Nutrição (gestão de cocho + IMS) --------------------------------
class CochoIn(BaseModel):
    data: date
    lote: str
    num_animais: int = 1
    kg_ofertado: float = 0.0
    kg_sobra: float = 0.0
    kg_formulado: float | None = None
    observacao: str | None = None


def _serializa_cocho(r: RegistroCocho) -> dict:
    consumido = max(0.0, (r.kg_ofertado or 0) - (r.kg_sobra or 0))
    n = r.num_animais or 1
    return {
        **r.model_dump(),
        "kg_consumido": round(consumido, 1),
        "pct_sobra": round(100 * (r.kg_sobra or 0) / r.kg_ofertado, 1) if r.kg_ofertado else None,
        "ims_consumida_animal": round(consumido / n, 2),
        "ims_formulada_animal": round((r.kg_formulado or 0) / n, 2) if r.kg_formulado else None,
    }


@router.get("/cocho")
def listar_cocho(
    lote: str = "", ini: date | None = None, fim: date | None = None, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(RegistroCocho).order_by(RegistroCocho.data.desc())
    if fazenda_id is not None:
        query = query.where(RegistroCocho.fazenda_id == fazenda_id)
    linhas = session.exec(query).all()
    nomes = mapa_usuarios(session, {r.usuario_id for r in linhas})
    saida = []
    for r in linhas:
        if lote and r.lote != lote:
            continue
        if ini and r.data < ini:
            continue
        if fim and r.data > fim:
            continue
        saida.append({**_serializa_cocho(r), "usuario_nome": nomes.get(r.usuario_id)})
    lotes = sorted({r.lote for r in linhas})
    return {"registros": saida, "lotes": lotes}


@router.post("/cocho", status_code=201)
def criar_cocho(
    dados: CochoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.lote.strip():
        raise HTTPException(status_code=400, detail="Informe o lote.")
    if dados.kg_sobra > dados.kg_ofertado:
        raise HTTPException(status_code=400, detail="A sobra não pode ser maior que o ofertado.")
    r = RegistroCocho(**dados.model_dump(), usuario_id=user.id, fazenda_id=fazenda_id)
    r.lote = dados.lote.strip()
    session.add(r)
    session.commit()
    session.refresh(r)
    return _serializa_cocho(r)


# ---------------------------------------------------------------------------
# Importação de planilha (Excel ou CSV) da leitura de campo do cocho — a
# ficha de papel que o técnico preenche no curral (data/lote/nº de
# animais/ofertado/sobra), evitando redigitar registro a registro na tela.
# ---------------------------------------------------------------------------
COCHO_APELIDOS = {
    "data": ["data", "data leitura", "data da leitura"],
    "lote": ["lote", "lote/grupo", "grupo"],
    "num_animais": ["numero de animais", "num animais", "n animais", "qtd animais", "animais"],
    "kg_ofertado": ["kg ofertado", "ofertado", "ofertado kg", "kg ofertados"],
    "kg_sobra": ["kg sobra", "sobra", "sobra kg"],
    "kg_formulado": ["kg formulado", "formulado", "meta", "kg meta", "kg formulado meta opcional"],
}
MODELO_COCHO = {
    "colunas": ["Data", "Lote", "Número de animais", "Kg ofertado", "Kg sobra", "Kg formulado (meta, opcional)"],
    "exemplo": ["05/07/2026", "01 - Lactação Alta", "45", "900,0", "60,0", "850,0"],
}


@router.get("/cocho/modelo-excel")
def modelo_excel_cocho() -> Response:
    conteudo = gerar_modelo_xlsx(MODELO_COCHO["colunas"], MODELO_COCHO["exemplo"], aba="Leitura de cocho")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo_leitura_cocho.xlsx"'},
    )


@router.post("/cocho/importar")
async def importar_cocho_planilha(
    file: UploadFile, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    content = await file.read()
    linhas = list(iter_planilha_rows(file.filename or "", content))
    if not linhas:
        return {"criados": 0, "erros": ["Planilha vazia ou em formato não reconhecido."]}

    erros: list[str] = []
    criados = 0
    for i, row in enumerate(linhas, start=2):
        row_norm = {normalizar_cabecalho(k): v for k, v in row.items()}
        data_linha = parse_date(valor_por_apelido(row_norm, COCHO_APELIDOS["data"]))
        lote = valor_por_apelido(row_norm, COCHO_APELIDOS["lote"]).strip()
        num_animais = parse_float(valor_por_apelido(row_norm, COCHO_APELIDOS["num_animais"]))
        kg_ofertado = parse_float(valor_por_apelido(row_norm, COCHO_APELIDOS["kg_ofertado"]))
        kg_sobra = parse_float(valor_por_apelido(row_norm, COCHO_APELIDOS["kg_sobra"]))
        kg_formulado = parse_float(valor_por_apelido(row_norm, COCHO_APELIDOS["kg_formulado"]))
        if not data_linha or not lote or not kg_ofertado:
            erros.append(f"Linha {i}: data, lote e kg ofertado são obrigatórios.")
            continue
        if kg_sobra and kg_sobra > kg_ofertado:
            erros.append(f"Linha {i}: a sobra não pode ser maior que o ofertado.")
            continue
        r = RegistroCocho(
            data=data_linha, lote=lote, num_animais=int(num_animais) if num_animais else 1,
            kg_ofertado=kg_ofertado, kg_sobra=kg_sobra or 0.0, kg_formulado=kg_formulado, usuario_id=user.id,
            fazenda_id=fazenda_id,
        )
        session.add(r)
        criados += 1
    session.commit()
    return {"criados": criados, "erros": erros}


@router.delete("/cocho/{cocho_id}")
def excluir_cocho(
    cocho_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    r = session.get(RegistroCocho, cocho_id)
    if r and (fazenda_id is None or r.fazenda_id == fazenda_id):
        session.delete(r)
        session.commit()
    return {"ok": True}


# --- Ocorrências clínicas (lançamento) -------------------------------------
class OcorrenciaIn(BaseModel):
    numero_matriz: str
    doenca: str
    doenca_id: int | None = None  # vínculo com o catálogo — opcional, ver _texto_doenca_do_catalogo
    data_ocorrencia: date
    observacao: str | None = None


@router.get("/ocorrencias")
def listar_ocorrencias(
    doenca: str = "", numero_matriz: str = "", session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(OcorrenciaClinica).order_by(OcorrenciaClinica.data_ocorrencia.desc())
    if fazenda_id is not None:
        query = query.where(OcorrenciaClinica.fazenda_id == fazenda_id)
    q = session.exec(query).all()
    nomes = mapa_usuarios(session, {o.usuario_id for o in q})
    saida = []
    for o in q:
        if doenca and o.doenca != doenca:
            continue
        if numero_matriz and o.numero_matriz != numero_matriz:
            continue
        saida.append({**o.model_dump(), "usuario_nome": nomes.get(o.usuario_id)})
    return saida


@router.post("/ocorrencias", status_code=201)
def criar_ocorrencia(
    dados: OcorrenciaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.numero_matriz.strip() or not dados.doenca.strip():
        raise HTTPException(status_code=400, detail="Informe o animal e a doença.")
    # Quando vem doenca_id (seletor do catálogo), o texto é denormalizado a
    # partir do nome cadastrado — mantém o texto digitado como fallback se o
    # vínculo não resolver (id de outra fazenda, catálogo removido etc.).
    texto_catalogo = _texto_doenca_do_catalogo(session, dados.doenca_id, fazenda_id)
    o = OcorrenciaClinica(
        numero_matriz=dados.numero_matriz.strip(), doenca=texto_catalogo or dados.doenca.strip(),
        doenca_id=dados.doenca_id,
        data_ocorrencia=dados.data_ocorrencia, observacao=(dados.observacao or None), origem="manual",
        usuario_id=user.id, fazenda_id=fazenda_id,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o.model_dump()


@router.delete("/ocorrencias/{ocorrencia_id}")
def excluir_ocorrencia(
    ocorrencia_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    o = session.get(OcorrenciaClinica, ocorrencia_id)
    if not o or (fazenda_id is not None and o.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada")
    session.delete(o)
    session.commit()
    return {"ok": True}


# --- Cadastros: Metas ------------------------------------------------------
class MetaIn(BaseModel):
    idade_parto_meses: float = 24.0
    idade_prenhez_meses: float = 14.5
    idade_1a_cobertura_meses: float = 13.5
    taxa_prenhez_meta: float = 42.5
    desvio_padrao_meta: float = 1.7
    custo_diario_recria: float = 12.0


@router.get("/metas")
def obter_metas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return _meta_recria(session, fazenda_id_seguro(fazenda_id)).model_dump()


@router.put("/metas")
def salvar_metas(
    dados: MetaIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    m = _meta_recria(session, fazenda_id)
    for campo, valor in dados.model_dump().items():
        setattr(m, campo, valor)
    m.atualizado_em = datetime.utcnow()
    session.add(m)
    session.commit()
    session.refresh(m)
    return m.model_dump()


# --- Cadastros: Curva de peso-alvo -----------------------------------------
class PesoAlvoIn(BaseModel):
    mes: int
    peso_min_kg: float
    peso_max_kg: float


@router.get("/peso-alvo")
def listar_peso_alvo(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(PesoAlvoIdade).order_by(PesoAlvoIdade.mes)
    if fazenda_id is not None:
        query = query.where(PesoAlvoIdade.fazenda_id == fazenda_id)
    linhas = session.exec(query).all()
    return [l.model_dump() for l in linhas]


@router.post("/peso-alvo", status_code=201)
def salvar_peso_alvo(
    dados: PesoAlvoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Cria ou atualiza a faixa daquele mês (upsert por mês, escopado por fazenda)."""
    if dados.peso_min_kg > dados.peso_max_kg:
        raise HTTPException(status_code=400, detail="Peso mínimo não pode ser maior que o máximo.")
    query = select(PesoAlvoIdade).where(PesoAlvoIdade.mes == dados.mes)
    if fazenda_id is not None:
        query = query.where(PesoAlvoIdade.fazenda_id == fazenda_id)
    linha = session.exec(query).first()
    if linha:
        linha.peso_min_kg = dados.peso_min_kg
        linha.peso_max_kg = dados.peso_max_kg
    else:
        linha = PesoAlvoIdade(mes=dados.mes, peso_min_kg=dados.peso_min_kg, peso_max_kg=dados.peso_max_kg, fazenda_id=fazenda_id)
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha.model_dump()


@router.delete("/peso-alvo/{mes}")
def excluir_peso_alvo(
    mes: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(PesoAlvoIdade).where(PesoAlvoIdade.mes == mes)
    if fazenda_id is not None:
        query = query.where(PesoAlvoIdade.fazenda_id == fazenda_id)
    linha = session.exec(query).first()
    if linha:
        session.delete(linha)
        session.commit()
    return {"ok": True}


# --- Cadastros: Fases de idade ---------------------------------------------
class FaseIn(BaseModel):
    nome: str
    dia_min: int
    dia_max: int
    ordem: int = 0
    ativo: bool = True


@router.get("/fases")
def listar_fases(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(FaseRecria).order_by(FaseRecria.ordem, FaseRecria.dia_min)
    if fazenda_id is not None:
        query = query.where(FaseRecria.fazenda_id == fazenda_id)
    linhas = session.exec(query).all()
    return [l.model_dump() for l in linhas]


@router.post("/fases", status_code=201)
def criar_fase(
    dados: FaseIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.dia_min > dados.dia_max:
        raise HTTPException(status_code=400, detail="Dia inicial não pode ser maior que o final.")
    f = FaseRecria(**dados.model_dump(), fazenda_id=fazenda_id)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()


@router.delete("/fases/{fase_id}")
def excluir_fase(
    fase_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    f = session.get(FaseRecria, fase_id)
    if f and (fazenda_id is None or f.fazenda_id == fazenda_id):
        session.delete(f)
        session.commit()
    return {"ok": True}


# --- Cadastros: Janelas de ponto crítico -----------------------------------
class JanelaIn(BaseModel):
    doenca: str
    doenca_id: int | None = None  # vínculo com o catálogo — opcional, ver _texto_doenca_do_catalogo
    dia_min: int
    dia_max: int
    dias_antecedencia: int = 3
    ativo: bool = True


@router.get("/janelas")
def listar_janelas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(JanelaPontoCritico).order_by(JanelaPontoCritico.doenca)
    if fazenda_id is not None:
        query = query.where(JanelaPontoCritico.fazenda_id == fazenda_id)
    linhas = session.exec(query).all()
    return [l.model_dump() for l in linhas]


@router.post("/janelas", status_code=201)
def criar_janela(
    dados: JanelaIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.dia_min > dados.dia_max:
        raise HTTPException(status_code=400, detail="Dia inicial não pode ser maior que o final.")
    # Quando vem doenca_id (seletor do catálogo), o texto é denormalizado a
    # partir do nome cadastrado — mesma regra de criar_ocorrencia acima.
    texto_catalogo = _texto_doenca_do_catalogo(session, dados.doenca_id, fazenda_id)
    dados_dict = dados.model_dump()
    if texto_catalogo:
        dados_dict["doenca"] = texto_catalogo
    j = JanelaPontoCritico(**dados_dict, fazenda_id=fazenda_id)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j.model_dump()


@router.delete("/janelas/{janela_id}")
def excluir_janela(
    janela_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    j = session.get(JanelaPontoCritico, janela_id)
    if j and (fazenda_id is None or j.fazenda_id == fazenda_id):
        session.delete(j)
        session.commit()
    return {"ok": True}


# --- Cadastros: Benchmark externo (Alta CRIA) ------------------------------
class BenchmarkIn(BaseModel):
    indicador: str
    unidade: str | None = None
    melhor_e_maior: bool = True
    top5: float | None = None
    top10: float | None = None
    top25: float | None = None
    top50: float | None = None
    top75: float | None = None
    valor_fazenda: float | None = None
    ordem: int = 0
    fonte: str = "Alta CRIA 2026"


def _faixa_benchmark(b: BenchmarkRecria) -> str | None:
    """Classifica o valor da fazenda na escala de percentis (TOP 5..75%)."""
    v = b.valor_fazenda
    if v is None:
        return None
    # Ordena os cortes do melhor para o pior conforme o sentido do indicador.
    cortes = [("TOP 5%", b.top5), ("TOP 10%", b.top10), ("TOP 25%", b.top25), ("TOP 50%", b.top50), ("TOP 75%", b.top75)]
    cortes = [(nome, c) for nome, c in cortes if c is not None]
    if not cortes:
        return None
    for nome, c in cortes:
        if (b.melhor_e_maior and v >= c) or ((not b.melhor_e_maior) and v <= c):
            return nome
    return "Abaixo do TOP 75%"


@router.get("/benchmark")
def listar_benchmark(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(BenchmarkRecria).order_by(BenchmarkRecria.ordem, BenchmarkRecria.indicador)
    if fazenda_id is not None:
        query = query.where(BenchmarkRecria.fazenda_id == fazenda_id)
    linhas = session.exec(query).all()
    return [{**b.model_dump(), "faixa_fazenda": _faixa_benchmark(b)} for b in linhas]


@router.post("/benchmark", status_code=201)
def salvar_benchmark(
    dados: BenchmarkIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Upsert por indicador (escopado por fazenda)."""
    query = select(BenchmarkRecria).where(BenchmarkRecria.indicador == dados.indicador)
    if fazenda_id is not None:
        query = query.where(BenchmarkRecria.fazenda_id == fazenda_id)
    b = session.exec(query).first()
    if b:
        for campo, valor in dados.model_dump().items():
            setattr(b, campo, valor)
        b.atualizado_em = datetime.utcnow()
    else:
        b = BenchmarkRecria(**dados.model_dump(), fazenda_id=fazenda_id)
    session.add(b)
    session.commit()
    session.refresh(b)
    return {**b.model_dump(), "faixa_fazenda": _faixa_benchmark(b)}


@router.delete("/benchmark/{benchmark_id}")
def excluir_benchmark(
    benchmark_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    b = session.get(BenchmarkRecria, benchmark_id)
    if b and (fazenda_id is None or b.fazenda_id == fazenda_id):
        session.delete(b)
        session.commit()
    return {"ok": True}


# --- Seed idempotente ------------------------------------------------------
# Curva de peso-alvo padrão (Foto 7 do dossiê): mês -> (mín, máx) em kg.
_PESO_ALVO_PADRAO = [
    (1, 25, 35), (2, 55, 65), (3, 75, 105), (4, 105, 135), (5, 135, 195),
    (6, 165, 225), (7, 195, 225), (9, 255, 225), (10, 285, 315), (11, 285, 315),
    (12, 345, 345), (13, 375, 405), (14, 405, 435), (15, 435, 465), (16, 465, 495),
    (17, 495, 525), (18, 495, 555), (19, 525, 555), (20, 585, 615), (21, 615, 645),
    (22, 645, 675),
]
_JANELAS_PADRAO = [
    ("Diarreia", 7, 15, 3),
    ("Pneumonia", 7, 14, 3),
    ("Pneumonia", 90, 150, 7),
    ("TPB", 90, 100, 7),  # profilaxia ANTES do salto (100–170); alerta antes do 100º dia
]


# Benchmark Alta CRIA 2026 (Vacaria Tijuca — "Benchmarking Total"):
# (indicador, unidade, maior_melhor, top5, top10, top25, top50, top75, fazenda).
_BENCHMARK_PADRAO = [
    ("Eficiência de colostragem (excelente)", "%", True, 94, 86, 74, 59, 41, 57),
    ("GMD nascimento–30 dias", "g/dia", True, 981, 928, 796, 661, 547, None),
    ("GMD 30–60 dias", "g/dia", True, 1068, 985, 910, 830, 773, None),
    ("GMD nascimento–desmama", "g/dia", True, 1015, 991, 897, 822, 756, 626),
    ("Ocorrência de diarreia", "%", False, 3.6, 7.7, 25.0, 39.7, 68.4, 16),
    ("Ocorrência de doenças respiratórias", "%", False, 1.6, 3.4, 7.7, 15.9, 27.2, 9),
    ("Taxa de mortalidade", "%", False, 2.2, 2.6, 4.4, 7.6, 13.5, 2.2),
]


# Categorias reprodutivas/produtivas mais finas pedidas pelo usuário — ordem
# negativa para serem tentadas ANTES da "Recria apta" legada (ordem=3), que
# do contrário classificaria todo adulto fértil (idade/peso ok) sem chegar a
# olhar estes critérios mais ricos.
def _categorias_novas_padrao() -> list[dict]:
    """Lista-modelo lida por `seed_categorias_novas` — função (não constante)
    porque "Vazia atrasada" e "Liberada/apta" derivam `dias_pos_parto_min` de
    `pev_dias()` na hora da semeadura (e "Novilha vazia em atraso" deriva
    `dia_min` de `idade_max_1a_cobertura_meses()`), em vez de números fixos
    (45/46) paralelos e independentes do parâmetro. As três têm de sair do MESMO
    valor, senão mudar o parâmetro abre um buraco: "Pós-parto - PEV" cobre
    os dias 0..pev e "liberada/atrasada" começa em pev+1, o dia seguinte ao
    fim do descanso — com o padrão de 45, 0-45 e 46. Isto é só a SEMENTE
    inicial — depois
    de criada, a categoria fica editável normalmente em Configurações >
    Cadastro > Recria, sem vínculo nenhum com o parâmetro daí em diante."""
    pev = pev_dias_param()
    liberada_desde = pev + 1
    return [
        dict(nome="Pós-parto - PEV", dias_pos_parto_max=pev, ordem=-8),
        dict(nome="Pré-parto", dias_para_parto_max=30, ordem=-7),
        dict(nome="Seca", dias_para_parto_min=30, dias_para_parto_max=60, ordem=-6),
        # "Atrasada" = já passou 30 dias desde a última tentativa de serviço
        # sem nova IA/monta; senão (nunca servida ou servida há pouco) cai
        # em "apta".
        dict(nome="Vazia atrasada", situacao_reprodutiva="vazia", dias_pos_parto_min=liberada_desde, dias_desde_servico_min=30, ordem=-5),
        # Novilha nulípara em atraso — o análogo de "Vazia atrasada" para quem
        # nunca pariu. "Vazia atrasada" acima depende de `dias_pos_parto_min`,
        # que NUNCA casa com nulípara (sem parto não há DEL), então até aqui a
        # novilha em atraso caía em "Liberada/apta" junto com a que acabou de
        # ficar apta. Casa por `situacao_reprodutiva="vazia_atrasada"` (ver
        # `_situacao_reprodutiva_3`).
        #
        # `ordem=-5` empata de propósito com "Vazia atrasada", e o desempate é
        # por `dia_min` (ver a ordenação em `classificar_categoria`): a vaca
        # atrasada continua caindo na categoria antiga, que é tentada primeiro.
        # `dia_min` é a própria idade-teto da 1ª cobertura — abaixo dela o
        # motor nunca devolve ATRASADA para nulípara, então o limite não
        # exclui ninguém que a categoria deveria pegar.
        dict(nome="Novilha vazia em atraso", situacao_reprodutiva="vazia_atrasada",
             dia_min=round(idade_max_1a_cobertura_meses() * 30.44), ordem=-5),
        dict(nome="Liberada/apta", situacao_reprodutiva="vazia", dias_pos_parto_min=liberada_desde, ordem=-4),
        dict(nome="Inseminada", situacao_reprodutiva="inseminada", ordem=-3),
        dict(nome="Prenha", situacao_reprodutiva="prenha", ordem=-2),
        dict(nome="Em lactação", situacao_produtiva="lactacao", ordem=-1),
        # Mesma faixa de idade da "Recria apta" legada (dia_min=391), mas
        # abaixo do peso mínimo — ordem menor para ser tentada antes dela.
        dict(nome="Recria atrasada", dia_min=391, peso_max_kg=369.99, ordem=2),
    ]


def seed_categorias_novas(session: Session, fazenda_id: int | None = None) -> None:
    """Acrescenta (por nome, idempotente, escopado por fazenda) as categorias
    de manejo mais ricas acima — roda mesmo em bancos que já têm as 4
    categorias legadas (Aleitamento/Recria 1/Recria 2/Recria apta)
    cadastradas."""
    query = select(CategoriaManejo)
    if fazenda_id is not None:
        query = query.where(CategoriaManejo.fazenda_id == fazenda_id)
    existentes = {c.nome for c in session.exec(query).all()}
    for dados in _categorias_novas_padrao():
        if dados["nome"] not in existentes:
            session.add(CategoriaManejo(**dados, fazenda_id=fazenda_id))
    session.commit()


def seed_recria(session: Session, fazenda_id: int | None = None) -> None:
    """Cria metas, curva de peso-alvo, janelas e benchmark padrão para a
    fazenda informada, se ainda vazio (idempotente, escopado por fazenda —
    ver nota em fazenda/models/recria.py::MetaRecria sobre o singleton por
    fazenda). `fazenda_id=None` preserva o comportamento legado de instalação
    única (pré-multi-tenant)."""
    _meta_recria(session, fazenda_id)
    benchmark_query = select(BenchmarkRecria)
    peso_alvo_query = select(PesoAlvoIdade)
    janela_query = select(JanelaPontoCritico)
    categoria_query = select(CategoriaManejo)
    if fazenda_id is not None:
        benchmark_query = benchmark_query.where(BenchmarkRecria.fazenda_id == fazenda_id)
        peso_alvo_query = peso_alvo_query.where(PesoAlvoIdade.fazenda_id == fazenda_id)
        janela_query = janela_query.where(JanelaPontoCritico.fazenda_id == fazenda_id)
        categoria_query = categoria_query.where(CategoriaManejo.fazenda_id == fazenda_id)

    if not session.exec(benchmark_query).first():
        for i, (ind, un, maior, t5, t10, t25, t50, t75, faz) in enumerate(_BENCHMARK_PADRAO):
            session.add(BenchmarkRecria(
                indicador=ind, unidade=un, melhor_e_maior=maior,
                top5=t5, top10=t10, top25=t25, top50=t50, top75=t75, valor_fazenda=faz, ordem=i,
                fazenda_id=fazenda_id,
            ))
    if not session.exec(peso_alvo_query).first():
        for mes, mn, mx in _PESO_ALVO_PADRAO:
            # Garante mín<=máx (a Foto 7 tem casos de faixa estreita/invertida).
            session.add(PesoAlvoIdade(
                mes=mes, peso_min_kg=float(min(mn, mx)), peso_max_kg=float(max(mn, mx)), fazenda_id=fazenda_id,
            ))
    if not session.exec(janela_query).first():
        for doenca, dmin, dmax, ant in _JANELAS_PADRAO:
            session.add(JanelaPontoCritico(
                doenca=doenca, dia_min=dmin, dia_max=dmax, dias_antecedencia=ant, fazenda_id=fazenda_id,
            ))
    if not session.exec(categoria_query).first():
        # Parâmetros de categoria (idade em dias / peso em kg).
        session.add(CategoriaManejo(nome="Aleitamento", dia_min=0, dia_max=90, peso_max_kg=100, ordem=0, fazenda_id=fazenda_id))
        session.add(CategoriaManejo(nome="Recria 1", dia_min=91, dia_max=210, ordem=1, fazenda_id=fazenda_id))
        session.add(CategoriaManejo(nome="Recria 2", dia_min=211, dia_max=390, ordem=2, fazenda_id=fazenda_id))
        session.add(CategoriaManejo(
            nome="Recria apta", dia_min=391, dia_max=None, peso_min_kg=370, usa_status_reprodutivo=True, ordem=3,
            fazenda_id=fazenda_id,
        ))
    session.commit()
    seed_categorias_novas(session, fazenda_id)
