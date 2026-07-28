"""
Router de reprodução — dados achatados para o dashboard interativo de análise
e lançamento de diagnóstico de gestação.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    Animal, ControleLeiteiro, EstoqueSemen, Parto, PesagemCorporal, ProtocoloIatfAplicacao, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    SeedFlag, Secagem, Servico, Usuario,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.agenda_veterinario import classificar_rebanho
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios, usuario_id_seguro
from fazenda.rules.email import enviar_email
from fazenda.rules.genetica import calcular_grau_sangue_cria
from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos

router = APIRouter(prefix="/reproducao", tags=["reproducao"])


def deduplicar_partos(session: Session) -> None:
    """Remove partos duplicados que sobraram de reimportações antigas do CSV
    reprodutivo (o import só inseria e nunca limpava — uma vaca com N uploads
    ficava com N partos iguais). Roda UMA vez (guardada por SeedFlag): para
    cada (matriz, data), mantém só o registro mais antigo. Uma vaca não pode
    parir duas vezes no mesmo dia, então colapsar por (matriz, data) é seguro.
    """
    chave = "partos_dedup_v1"
    if session.get(SeedFlag, chave):
        return
    vistos: set[tuple[str, object]] = set()
    for p in session.exec(select(Parto).order_by(Parto.id)).all():
        k = (p.numero_matriz, p.data_parto)
        if k in vistos:
            session.delete(p)
        else:
            vistos.add(k)
    session.add(SeedFlag(chave=chave))
    session.commit()


def backfill_categoria_crias(session: Session) -> None:
    """Corrige crias já cadastradas via /parto que ficaram sem categoria (o
    registro só define categoria a partir de agora — ver registrar_parto).
    Roda UMA vez (guardada por SeedFlag): qualquer Animal com mãe registrada
    (mae_numero preenchido, ou seja, veio de um parto) e sem categoria
    completa ainda entra em "Bezerra/o Mamando"; o próximo upload do
    GERAL.csv (Ideagri) segue tendo prioridade e substitui esse valor."""
    chave = "backfill_categoria_crias_v1"
    if session.get(SeedFlag, chave):
        return
    crias = session.exec(
        select(Animal).where(Animal.mae_numero.is_not(None), Animal.categoria_completa.is_(None))
    ).all()
    for a in crias:
        a.categoria_completa = "Bezerra Mamando" if a.sexo == "F" else "Bezerro Mamando"
        a.categoria_abrev = "Bezerra" if a.sexo == "F" else "Bezerro"
        session.add(a)
    session.add(SeedFlag(chave=chave))
    session.commit()


def backfill_numero_cria_partos(session: Session) -> None:
    """Associa retroativamente numero_cria_1/2 (e gemelar_sexo) aos partos que
    vieram do upload do CSV reprodutivo — esse CSV não traz o número da cria
    nem o sexo do gemelar, só quem é registrado via /reproducao/parto tem
    isso hoje. Casa pela mãe (Animal.mae_numero == Parto.numero_matriz) e
    pela data de nascimento próxima da data do parto (± 2 dias, cobre
    diferenças de fuso/lançamento tardio). Roda UMA vez (SeedFlag); só
    preenche quando a combinação é inequívoca — deixa de fora (para revisão
    manual) qualquer parto com mais candidatos do que o esperado."""
    chave = "backfill_numero_cria_partos_v1"
    if session.get(SeedFlag, chave):
        return
    por_mae: dict[str, list[Animal]] = {}
    for a in session.exec(select(Animal).where(Animal.mae_numero.is_not(None))).all():
        por_mae.setdefault(a.mae_numero, []).append(a)

    partos = session.exec(
        select(Parto).where(Parto.numero_cria_1.is_(None), Parto.numero_cria_2.is_(None))
    ).all()
    for p in partos:
        if not p.data_parto:
            continue
        candidatos = [
            a for a in por_mae.get(p.numero_matriz, [])
            if a.data_nasc and abs((a.data_nasc - p.data_parto).days) <= 2
        ]
        if not candidatos:
            continue
        esperado = 2 if p.gemelar else 1
        if len(candidatos) > esperado:
            continue  # ambíguo — mais crias batendo do que o parto indica, não arrisca
        # Prioriza o candidato cujo sexo bate com sexo_cria_1 (já vindo do CSV),
        # depois ordena por número para ficar determinístico.
        candidatos.sort(key=lambda a: (0 if (p.sexo_cria_1 and a.sexo == p.sexo_cria_1) else 1, a.numero))
        p.numero_cria_1 = candidatos[0].numero
        if len(candidatos) > 1:
            p.numero_cria_2 = candidatos[1].numero
            if not p.gemelar_sexo and candidatos[0].sexo and candidatos[1].sexo:
                combo = "".join(sorted(candidatos[0].sexo + candidatos[1].sexo))
                p.gemelar_sexo = {"FF": "FF", "FM": "FM", "MM": "MM"}.get(combo)
        session.add(p)
    session.add(SeedFlag(chave=chave))
    session.commit()

# Passos do protocolo IATF — mesmo cronograma já usado no rascunho do front
# (D0/D7/D9/D11); aqui viram eventos reais na Agenda em vez de só um desenho.
PASSOS_PROTOCOLO_IATF = [
    (0, "Implante de progesterona + Benzoato de estradiol + Acetato de buserelina (D0)"),
    (7, "Cloprostenol (D7)"),
    (9, "Retirar implante + Cipionato de estradiol + Cloprostenol (D9)"),
    (11, "Inseminação (IATF) — D11"),
]


@router.get("/agenda-veterinario")
def agenda_veterinario(
    data: date | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Roteiro do veterinário do serviço: classifica o rebanho fêmea em 9 listas
    (ver fazenda.rules.agenda_veterinario para os critérios de cada uma).

    Aceita uma data de referência opcional (`?data=AAAA-MM-DD`, #490) para um
    cenário projetado: quando a visita do veterinário será numa data futura
    (o "próximo serviço"), os dias inseminada/dias para parto são recalculados
    como se aquela fosse "hoje" — com os dados já lançados, sem prever novos
    lançamentos que ainda vão acontecer até lá.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje_real = date.today()
    hoje = data or hoje_real
    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais = [a.model_dump() for a in session.exec(query_animais).all()]

    query_servicos = select(Servico)
    if fazenda_id is not None:
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
    servico_por_animal: dict[str, dict] = {}
    for s in session.exec(query_servicos).all():
        atual = servico_por_animal.get(s.numero_matriz)
        if not atual or (s.data_servico and (not atual.get("data_servico") or s.data_servico > atual["data_servico"])):
            servico_por_animal[s.numero_matriz] = s.model_dump()

    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    for p in session.exec(select(PesagemCorporal)).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg

    listas = classificar_rebanho(animais, servico_por_animal, peso_por_animal, hoje)

    # Próxima visita reprodutiva sugerida (#571): último serviço do rebanho +
    # intervalo configurado em Parâmetros. Intervalo 0/vazio => nenhuma data
    # é sugerida (agendamento automático "desligado") — o front então oferece
    # a janela suspensa para o usuário configurar o intervalo.
    from fazenda.rules.parametros import intervalo_visita_reprodutiva as _intervalo_visita_reprodutiva

    datas_servico = [s["data_servico"] for s in servico_por_animal.values() if s.get("data_servico")]
    ultimo_servico = max(datas_servico) if datas_servico else None
    intervalo = _intervalo_visita_reprodutiva()
    proxima_visita_reprodutiva = (
        ultimo_servico + timedelta(days=intervalo) if (ultimo_servico and intervalo > 0) else None
    )

    return {
        "data_referencia": hoje.isoformat(),
        "projetado": hoje != hoje_real,
        "listas": listas,
        "totais": {k: len(v) for k, v in listas.items()},
        "ultimo_servico": ultimo_servico.isoformat() if ultimo_servico else None,
        "proxima_visita_reprodutiva": proxima_visita_reprodutiva.isoformat() if proxima_visita_reprodutiva else None,
        "intervalo_visita_reprodutiva": intervalo,
    }


def _ultimo_servico(session: Session, numero_matriz: str, fazenda_id: int | None = None) -> Servico | None:
    query = select(Servico).where(Servico.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    return session.exec(query.order_by(Servico.data_servico.desc())).first()


@router.get("/animais/{numero_matriz}/ultimo-diagnostico")
def ultimo_diagnostico(
    numero_matriz: str,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict | None:
    """Último serviço/IA da matriz (com diagnóstico, se já lançado) — usado
    tanto na Agenda do veterinário quanto na ficha do animal para montar o
    e-mail de "enviar último DG" (ver enviar_ultimo_diagnostico abaixo)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    servico = _ultimo_servico(session, numero_matriz, fazenda_id=fazenda_id)
    return servico.model_dump() if servico else None


class EnviarDiagnosticoIn(BaseModel):
    destinatario: str


@router.post("/animais/{numero_matriz}/diagnostico/enviar")
def enviar_ultimo_diagnostico(
    numero_matriz: str,
    dados: EnviarDiagnosticoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Envia por e-mail um resumo do último diagnóstico de gestação da
    matriz — mesmo mecanismo de e-mail do recibo financeiro (#505), mas sem
    PDF anexado (o corpo do e-mail já traz os dados do diagnóstico)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not (dados.destinatario or "").strip():
        raise HTTPException(status_code=400, detail="Informe o e-mail do destinatário")
    servico = _ultimo_servico(session, numero_matriz, fazenda_id=fazenda_id)
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {numero_matriz}")
    if not servico.data_diagnostico:
        raise HTTPException(status_code=400, detail=f"A matriz {numero_matriz} ainda não tem diagnóstico de gestação registrado")

    fmt = lambda d: d.strftime("%d/%m/%Y") if d else "—"  # noqa: E731
    linhas = [
        f"<p><b>Matriz:</b> {numero_matriz}</p>",
        f"<p><b>Data do serviço:</b> {fmt(servico.data_servico)}</p>",
        f"<p><b>Data do diagnóstico:</b> {fmt(servico.data_diagnostico)}</p>",
        f"<p><b>Resultado:</b> {servico.diagnostico or '—'}</p>",
    ]
    if servico.metodo_diagnostico:
        linhas.append(f"<p><b>Método:</b> {servico.metodo_diagnostico}</p>")
    if servico.data_reconfirmacao:
        linhas.append(f"<p><b>Reconfirmação ({fmt(servico.data_reconfirmacao)}):</b> {servico.diagnostico_reconfirmacao or '—'}</p>")
    corpo_html = "".join(linhas) + "<p>Fazenda Estreito Ponte de Pedra</p>"

    try:
        enviar_email(dados.destinatario.strip(), f"Diagnóstico de gestação — matriz {numero_matriz}", corpo_html)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"enviado": True}


@router.get("/servicos")
def listar_servicos_analise(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Todos os serviços achatados com as dimensões da análise reprodutiva
    (concepção/perda por categoria, raça, ordem de parto/tentativa, condição
    de IA, inseminador, mês, DEL). O front filtra/agrega no cliente.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Servico)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    servicos = [s.model_dump() for s in session.exec(query).all()]
    registros = analisar_servicos(servicos)
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    tipo_por_touro = _mapa_tipo_semen_por_touro(session)
    data_d0_por_servico = _mapa_data_d0_por_servico(session, fazenda_id)
    for r in registros:
        r["usuario_nome"] = nomes.get(r.pop("usuario_id"))
        # Serviços antigos (lançados antes de o tipo ser perguntado) não têm
        # tipo_semen gravado — completa casando o nome do touro com o Estoque
        # de Sêmen atual, mesma regra usada na baixa de dose.
        if not r.get("tipo_semen") and r.get("touro") and r["touro"] != "(sem touro)":
            r["tipo_semen"] = tipo_por_touro.get(r["touro"].strip().lower())
        # D0 real do protocolo IATF (se o serviço veio de um) — usado pela tela
        # para agrupar por "ciclo" de verdade, em vez de uma janela de calendário
        # ancorada na data do serviço mais recente do filtro (ver data_d0_por_servico).
        # analisar_servicos já renomeou/serializou os campos: "numero" (não
        # numero_matriz) e "data" como string ISO (não data_servico/date).
        r["data_d0"] = data_d0_por_servico.get((r["numero"], r["data"]))
    return {"servicos": registros, "total": len(registros)}


def _mapa_data_d0_por_servico(session: Session, fazenda_id: int | None) -> dict[tuple[str, str], str]:
    """(numero_matriz, data_servico ISO) -> data_d0 (ISO) do protocolo IATF que
    originou aquele serviço — mesma chave que registrar_servico usa para
    resolver a ProtocoloIatfAplicacao (dia 11) na hora de registrar
    (numero_matriz + data_realizacao == data_servico), então funciona igual
    para qualquer serviço já lançado, não só os novos. Sem isso a tela
    agrupava "ciclo" numa janela de calendário arbitrária, sem nenhuma relação
    com o D0 real de cada protocolo (bug relatado — datas de ciclo não
    batiam com os D0 verdadeiros)."""
    query = (
        select(ProtocoloIatfAplicacao.numero_matriz, ProtocoloIatfAplicacao.data_realizacao, ProtocoloIatfLancamento.data_d0)
        .join(ProtocoloIatfLancamento, ProtocoloIatfAplicacao.lancamento_id == ProtocoloIatfLancamento.id)
        .where(ProtocoloIatfAplicacao.dia == 11, ProtocoloIatfAplicacao.realizada == True)  # noqa: E712
    )
    if fazenda_id is not None:
        query = query.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    return {
        (numero, realizacao.isoformat()): d0.isoformat()
        for numero, realizacao, d0 in session.exec(query).all() if realizacao is not None
    }


class ServicoEditIn(BaseModel):
    """Edição de um serviço/IA já lançado — todos os campos são opcionais,
    só o que for enviado é alterado (usado pelas sub-abas Serviços, IAs,
    Diagnósticos e Perda de prenhez do histórico de Reprodução, que editam
    o mesmo registro Servico com recortes de campos diferentes)."""
    data_servico: date | None = None
    tipo_servico: str | None = None
    reprodutor: str | None = None
    tipo_semen: str | None = None
    inseminador: str | None = None
    data_diagnostico: date | None = None
    diagnostico: str | None = None
    metodo_diagnostico: str | None = None
    data_perda_prenhez: date | None = None
    motivo_perda_prenhez: str | None = None


@router.put("/servicos/{servico_id}")
def atualizar_servico(
    servico_id: int,
    dados: ServicoEditIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    servico = session.get(Servico, servico_id)
    if not servico or (fazenda_id is not None and servico.fazenda_id not in (None, fazenda_id)):
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(servico, campo, valor)
    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


@router.get("/indicadores-mensais")
def indicadores_mensais_analise(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    ini: str | None = None,
    fim: str | None = None,
    tipo_servico: list[str] | None = Query(None),
    metodo_ia: list[str] | None = Query(None),
    touro: list[str] | None = Query(None),
    inseminador: list[str] | None = Query(None),
    ordem_parto: list[str] | None = Query(None),
    ordem_tentativa: list[str] | None = Query(None),
) -> dict:
    """
    Série mensal cruzando métricas reprodutivas (serviços, métodos, concepção,
    perdas) e produtivas (secagens, produção de leite, DEL) — alimenta o
    gráfico interativo configurável de Análise reprodutiva (escolha de
    métricas e eixo ano/mês).

    Aceita os mesmos filtros (período e dimensões) usados na tela de Análise
    reprodutiva, para que o gráfico reflita exatamente o recorte que o
    usuário escolheu — em vez de sempre olhar o histórico inteiro.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Servico)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    servicos = [s.model_dump() for s in session.exec(query).all()]
    registros = analisar_servicos(servicos)

    filtros_dimensao = {
        "tipo_servico": tipo_servico,
        "metodo_ia": metodo_ia,
        "touro": touro,
        "inseminador": inseminador,
        "ordem_parto": ordem_parto,
        "ordem_tentativa": ordem_tentativa,
    }

    def passa(r: dict) -> bool:
        if ini and (not r["data"] or r["data"] < ini):
            return False
        if fim and (not r["data"] or r["data"] > fim):
            return False
        for chave, valores in filtros_dimensao.items():
            if valores and str(r.get(chave)) not in valores:
                return False
        return True

    registros = [r for r in registros if passa(r)]

    secagens = [s.model_dump() for s in session.exec(select(Secagem)).all()]
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]

    if ini or fim:
        def no_periodo(d: object) -> bool:
            if not isinstance(d, date):
                return False
            iso = d.isoformat()
            if ini and iso < ini:
                return False
            if fim and iso > fim:
                return False
            return True

        secagens = [s for s in secagens if no_periodo(s.get("data_secagem"))]
        controles = [c for c in controles if no_periodo(c.get("data_controle"))]

    return agregar_mensal(registros, secagens, controles)


class DiagnosticoIn(BaseModel):
    numero_matriz: str
    data_diagnostico: date
    resultado: str  # "retoque" | "reconfirmada" | "negativo" | "indefinido"
    metodo: str | None = None  # Palpação | Ultrassom | Cio de repasse


@router.post("/diagnostico")
def registrar_diagnostico(
    dados: DiagnosticoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Registra o resultado do diagnóstico de gestação no serviço mais recente da
    matriz. Se marcado "retoque", o lembrete de reconfirmação entra na agenda
    na data do próximo serviço (agenda_engine.py). "Indefinido" (inconclusivo)
    é distinto de "negativo" — a matriz não vira vazia, segue para reavaliar.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.resultado not in ("retoque", "reconfirmada", "negativo", "indefinido"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    # Prioriza o serviço ainda em aberto (sem diagnóstico) — evita gravar por
    # engano num serviço antigo já diagnosticado quando a matriz tem mais de
    # um serviço na tabela. Sem serviço em aberto, cai no mais recente (mantém
    # o fluxo de reeditar o diagnóstico já lançado, ex.: retoque -> reconfirmada).
    query_aberto = select(Servico).where(Servico.numero_matriz == dados.numero_matriz, Servico.diagnostico.is_(None))
    query_recente = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query_aberto = query_aberto.where(Servico.fazenda_id == fazenda_id)
        query_recente = query_recente.where(Servico.fazenda_id == fazenda_id)
    servico = session.exec(query_aberto.order_by(Servico.data_servico.desc())).first() or session.exec(
        query_recente.order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_diagnostico = dados.data_diagnostico
    servico.metodo_diagnostico = dados.metodo
    if dados.resultado == "retoque":
        servico.diagnostico = "POSITIVO"
        servico.retoque = True
    elif dados.resultado == "reconfirmada":
        servico.diagnostico = "POSITIVO"
        servico.retoque = False
    elif dados.resultado == "indefinido":
        servico.diagnostico = "INDEFINIDO"
        servico.retoque = False
    else:
        servico.diagnostico = "NEGATIVO"
        servico.retoque = False

    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


class ReconfirmacaoIn(BaseModel):
    numero_matriz: str
    data_reconfirmacao: date
    resultado: str  # "positivo" | "negativo"


@router.post("/reconfirmacao")
def registrar_reconfirmacao(
    dados: ReconfirmacaoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Segundo exame (reconfirmação, ~60 dias do serviço) — distinto do primeiro
    toque. Usado pela agenda do veterinário para tirar o animal de "atrasada
    para reconfirmação" e classificá-lo como gestante confirmada.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.resultado not in ("positivo", "negativo"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    # Mesma lógica de preferência do diagnóstico acima: prioriza o serviço
    # positivo ainda sem reconfirmação; sem um assim, cai no mais recente
    # (mantém o fluxo legado de reconfirmar direto um serviço sem 1º toque).
    query_aberto = select(Servico).where(
        Servico.numero_matriz == dados.numero_matriz,
        Servico.diagnostico == "POSITIVO",
        Servico.data_reconfirmacao.is_(None),
    )
    query_recente = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query_aberto = query_aberto.where(Servico.fazenda_id == fazenda_id)
        query_recente = query_recente.where(Servico.fazenda_id == fazenda_id)
    servico = session.exec(query_aberto.order_by(Servico.data_servico.desc())).first() or session.exec(
        query_recente.order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_reconfirmacao = dados.data_reconfirmacao
    servico.diagnostico_reconfirmacao = "POSITIVO" if dados.resultado == "positivo" else "NEGATIVO"
    servico.retoque = False

    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


MOTIVOS_PERDA_PRENHEZ = ["aborto", "natimorto", "outros"]


class PerdaPrenhezIn(BaseModel):
    numero_matriz: str
    data_perda_prenhez: date
    motivo: str  # aborto | natimorto | outros


@router.post("/perda-prenhez")
def registrar_perda_prenhez(
    dados: PerdaPrenhezIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Registra a perda de prenhez (com motivo) no serviço mais recente da
    matriz — sem isso, `data_perda_prenhez` só era populado pela importação de
    CSV, sem nenhuma classificação nem forma manual de lançar. Alimenta o
    histórico de perda de prenhezes (filtro aborto/natimorto/outros).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.motivo not in MOTIVOS_PERDA_PRENHEZ:
        raise HTTPException(status_code=400, detail="Motivo inválido")

    query = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    servico = session.exec(query.order_by(Servico.data_servico.desc())).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_perda_prenhez = dados.data_perda_prenhez
    servico.motivo_perda_prenhez = dados.motivo
    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


@router.get("/partos")
def listar_partos_historico(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Todos os partos, achatados — histórico de partos (Reprodução), com os
    mesmos filtros de animal/data/ciclo/ordem de parto da sub-aba Reprodução."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Parto).order_by(Parto.data_parto.desc())
    if fazenda_id is not None:
        query = query.where(Parto.fazenda_id == fazenda_id)
    partos = session.exec(query).all()
    nomes = mapa_usuarios(session, {p.usuario_id for p in partos})
    registros = []
    for p in partos:
        d = p.model_dump()
        d["numero"] = d.pop("numero_matriz")
        ds = d.get("data_parto")
        d["ano"] = ds.year if isinstance(ds, date) else None
        d["mes"] = f"{ds.year}-{ds.month:02d}" if isinstance(ds, date) else None
        d["data"] = ds.isoformat() if isinstance(ds, date) else None
        d["usuario_nome"] = nomes.get(d.pop("usuario_id"))
        registros.append(d)
    return {"partos": registros, "total": len(registros)}


class PartoEditIn(BaseModel):
    data_parto: date | None = None
    tipo_parto: str | None = None
    retencao_placenta: bool | None = None


@router.put("/partos/{parto_id}")
def atualizar_parto(
    parto_id: int,
    dados: PartoEditIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Edita os campos do parto em si (data, tipo, retenção de placenta) — não
    mexe nas crias já cadastradas, que seguem editáveis pela ficha do animal."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parto = session.get(Parto, parto_id)
    if not parto or (fazenda_id is not None and parto.fazenda_id not in (None, fazenda_id)):
        raise HTTPException(status_code=404, detail="Parto não encontrado")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(parto, campo, valor)
    session.add(parto)
    session.commit()
    session.refresh(parto)
    return parto.model_dump()


@router.get("/secagens")
def listar_secagens_historico(session: Session = Depends(get_session)) -> dict:
    """Todas as secagens, achatadas — histórico de secagens (Reprodução), com
    os mesmos filtros de animal/data/ciclo da sub-aba Reprodução."""
    secagens = session.exec(select(Secagem).order_by(Secagem.data_secagem.desc())).all()
    registros = []
    for s in secagens:
        d = s.model_dump()
        d["numero"] = d.pop("numero_matriz")
        ds = d.get("data_secagem")
        d["ano"] = ds.year if isinstance(ds, date) else None
        d["mes"] = f"{ds.year}-{ds.month:02d}" if isinstance(ds, date) else None
        d["data"] = ds.isoformat() if isinstance(ds, date) else None
        registros.append(d)
    return {"secagens": registros, "total": len(registros)}


class SecagemEditIn(BaseModel):
    data_secagem: date | None = None
    motivo: str | None = None
    escore_condicao_corporal: float | None = None
    observacao: str | None = None


@router.put("/secagens/{secagem_id}")
def atualizar_secagem(secagem_id: int, dados: SecagemEditIn, session: Session = Depends(get_session)) -> dict:
    secagem = session.get(Secagem, secagem_id)
    if not secagem:
        raise HTTPException(status_code=404, detail="Secagem não encontrada")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(secagem, campo, valor)
    session.add(secagem)
    session.commit()
    session.refresh(secagem)
    return secagem.model_dump()


class CriaIn(BaseModel):
    numero: str = ""      # vazio = cria sem número → baixa automática (natimorto/não entra no rebanho)
    sexo: str  # "F" | "M"
    nasceu_viva: bool = True


class PartoIn(BaseModel):
    numero_matriz: str
    data_parto: date
    tipo_parto: str | None = None
    crias: list[CriaIn] = []
    retencao_placenta: bool | None = None
    gemelar: bool | None = None
    gemelar_sexo: str | None = None  # "FF" | "FM" | "MM" (informado ou derivado dos sexos das crias)
    observacao: str | None = None


@router.post("/parto")
def registrar_parto(
    dados: PartoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Registra o parto e cria a ficha de cada cria nascida viva ainda não
    cadastrada. Não move ninguém de lote sozinho — o front sugere o lote via
    /producao/sugestao-lote-evento e só move (POST /movimentacoes/mover) com
    confirmação explícita do usuário.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_mae = select(Animal).where(Animal.numero == dados.numero_matriz)
    if fazenda_id is not None:
        query_mae = query_mae.where(Animal.fazenda_id == fazenda_id)
    mae = session.exec(query_mae).first()
    if not mae:
        raise HTTPException(status_code=404, detail="Matriz não encontrada")

    query_ultimo_parto = select(Parto).where(Parto.numero_matriz == dados.numero_matriz).order_by(Parto.ordem_parto.desc())
    if fazenda_id is not None:
        query_ultimo_parto = query_ultimo_parto.where(Parto.fazenda_id == fazenda_id)
    ultimo_parto = session.exec(query_ultimo_parto).first()
    ordem_parto = (ultimo_parto.ordem_parto or 0) + 1 if ultimo_parto else 1

    # Sexo do parto gemelar: usa o informado ou deriva dos sexos das crias.
    gemelar_sexo = dados.gemelar_sexo
    if not gemelar_sexo and len(dados.crias) >= 2:
        combo = "".join(sorted((dados.crias[0].sexo or "").upper() + (dados.crias[1].sexo or "").upper()))
        gemelar_sexo = {"FF": "FF", "FM": "FM", "MM": "MM"}.get(combo)

    parto = Parto(
        animal_id=mae.id,
        numero_matriz=dados.numero_matriz,
        data_parto=dados.data_parto,
        ordem_parto=ordem_parto,
        tipo_parto=dados.tipo_parto,
        sexo_cria_1=dados.crias[0].sexo if len(dados.crias) > 0 else None,
        sexo_cria_2=dados.crias[1].sexo if len(dados.crias) > 1 else None,
        numero_cria_1=(dados.crias[0].numero or None) if len(dados.crias) > 0 else None,
        numero_cria_2=(dados.crias[1].numero or None) if len(dados.crias) > 1 else None,
        gemelar=dados.gemelar if dados.gemelar is not None else len(dados.crias) > 1,
        gemelar_sexo=gemelar_sexo,
        retencao_placenta=dados.retencao_placenta,
        usuario_id=usuario_id_seguro(user),
        fazenda_id=fazenda_id,
    )
    session.add(parto)

    crias_criadas = []
    crias_baixadas = []
    for cria in dados.crias:
        # Sem número OU marcada como não-viva → baixa automática (natimorto/não
        # entra no rebanho). Fica registrada no parto (sexo), mas sem ficha.
        if not (cria.numero or "").strip() or not cria.nasceu_viva:
            crias_baixadas.append(cria.sexo or "?")
            continue
        query_cria_existente = select(Animal).where(Animal.numero == cria.numero)
        if fazenda_id is not None:
            query_cria_existente = query_cria_existente.where(Animal.fazenda_id == fazenda_id)
        if session.exec(query_cria_existente).first():
            continue  # já cadastrada — não sobrescreve
        raca_cria, grau_sangue_cria = calcular_grau_sangue_cria(session, mae, dados.data_parto)
        # Todo animal que nasce entra automaticamente na categoria "bezerra/o
        # mamando" — o próximo upload do GERAL.csv (Ideagri) pode atualizar
        # depois, mas a cria não deve ficar sem categoria até lá.
        categoria_completa_cria = "Bezerra Mamando" if cria.sexo == "F" else "Bezerro Mamando"
        categoria_abrev_cria = "Bezerra" if cria.sexo == "F" else "Bezerro"
        session.add(Animal(
            numero=cria.numero, sexo=cria.sexo, raca=raca_cria, grau_sangue=grau_sangue_cria, data_nasc=dados.data_parto,
            mae_numero=mae.numero, mae_nome=mae.nome, ativo=True,
            categoria_completa=categoria_completa_cria, categoria_abrev=categoria_abrev_cria,
            fazenda_id=fazenda_id,
        ))
        crias_criadas.append(cria.numero)

    # Retenção de placenta → gera um item na Agenda (avaliação/tratamento) no
    # dia do parto, para não passar despercebido.
    if dados.retencao_placenta:
        from fazenda.models import AgendaManual
        session.add(AgendaManual(
            data_evento=dados.data_parto,
            descricao=f"Retenção de placenta — vaca {mae.numero}: avaliar/tratar",
            categoria="Sanidade",
            numero_animal=mae.numero,
            tipo_evento="Outro",
            observacao="Gerado automaticamente pelo lançamento de parto com retenção de placenta.",
            usuario_id=usuario_id_seguro(user),
        ))

    # DEL reseta ao parir — o resto da ficha (categoria, produção etc.) só é
    # atualizado de fato no próximo upload do GERAL.csv.
    mae.del_dias = 0
    mae.atualizado_em = datetime.utcnow()
    session.add(mae)

    session.commit()
    return {"criado": True, "ordem_parto": ordem_parto, "crias_criadas": crias_criadas, "crias_baixadas": crias_baixadas}


class HormonioIatfIn(BaseModel):
    dia: int  # 0, 7 ou 9 (D11 é inseminação, sem hormônio)
    produto: str
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None


class ProtocoloIatfIn(BaseModel):
    animais: list[str]
    data_d0: date
    # Vazio/ausente -> nome automático "IATF <D0> A <D11>" (ver _nome_auto_iatf).
    protocolo: str | None = None
    # Medicamentos por dia (ex.: D0 = 1ml SincroCP + 2ml Estron). Opcional —
    # sem eles, o protocolo funciona como antes (sem baixa de estoque).
    hormonios: list[HormonioIatfIn] = []


@router.post("/protocolo-iatf")
def lancar_protocolo_iatf(
    dados: ProtocoloIatfIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Agenda só o PROTOCOLO hormonal (D0/D7/D9/D11) — não cria o serviço em si.
    A inseminação de fato (D11) é lançada à parte em POST /reproducao/servico,
    para separar "marcar o protocolo" de "a vaca foi inseminada". Cada etapa de
    cada animal vira uma ProtocoloIatfAplicacao rastreável — a Agenda agrupa
    por (lançamento, dia) em vez de mostrar uma linha por animal.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    nome_protocolo = (dados.protocolo or "").strip() or _nome_auto_iatf(dados.data_d0)
    lancamento = ProtocoloIatfLancamento(
        nome_protocolo=nome_protocolo, data_d0=dados.data_d0, usuario_id=usuario_id_seguro(user),
        fazenda_id=fazenda_id,
    )
    session.add(lancamento)
    session.flush()  # garante lancamento.id antes de criar as aplicações

    # Medicamentos por dia (aplicados a todas as vacas do passo). Se o usuário
    # informou hormônios, a descrição de cada dia passa a listá-los.
    hormonios_por_dia: dict[int, list[HormonioIatfIn]] = {}
    for h in dados.hormonios:
        if (h.produto or "").strip():
            hormonios_por_dia.setdefault(h.dia, []).append(h)
            session.add(ProtocoloIatfHormonio(
                lancamento_id=lancamento.id, dia=h.dia, produto=h.produto.strip(),
                dose=h.dose, unidade=h.unidade, via=h.via, fazenda_id=fazenda_id,
            ))

    def _descricao_dia(dias: int, padrao: str) -> str:
        hs = hormonios_por_dia.get(dias)
        if not hs:
            return padrao
        return " + ".join(f"{h.dose or ''}{(' ' + h.unidade) if h.unidade else ''} {h.produto}".strip() for h in hs)

    eventos_criados = 0
    for numero in dados.animais:
        for dias, descricao in PASSOS_PROTOCOLO_IATF:
            session.add(ProtocoloIatfAplicacao(
                lancamento_id=lancamento.id,
                numero_matriz=numero,
                dia=dias,
                descricao=_descricao_dia(dias, descricao),
                data_prevista=dados.data_d0 + timedelta(days=dias),
                fazenda_id=fazenda_id,
            ))
            eventos_criados += 1

    session.commit()
    return {"criado": True, "lancamento_id": lancamento.id, "eventos_criados": eventos_criados, "animais": len(dados.animais)}


@router.get("/protocolo-iatf/ativos")
def listar_protocolos_iatf_ativos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Protocolos IATF com pelo menos uma etapa ainda não realizada — para ver de
    relance em qual dia (D0/D7/D9/D11) está cada animal em andamento.

    Um protocolo com TODAS as etapas concluídas (D11/inseminação já com
    baixa) some da lista principal, mas continua aparecendo por mais um
    ciclo (intervalo_visita_reprodutiva dias, editável em Configurações >
    Parâmetros) como "concluido": True, mostrando a data do próximo serviço
    (D11 + intervalo) e as candidatas herd-wide ao próximo repasse (mesmo
    critério de `selecionar_candidatas_iatf`, usado na Agenda) — ver #369.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    from fazenda.rules.iatf import selecionar_candidatas_iatf
    from fazenda.rules.parametros import intervalo_visita_reprodutiva

    hoje = date.today()
    intervalo = intervalo_visita_reprodutiva()
    query_lancamentos = select(ProtocoloIatfLancamento).order_by(ProtocoloIatfLancamento.data_d0.desc())
    if fazenda_id is not None:
        query_lancamentos = query_lancamentos.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query_lancamentos).all()
    query_aplicacoes = select(ProtocoloIatfAplicacao)
    if fazenda_id is not None:
        query_aplicacoes = query_aplicacoes.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    aplicacoes = session.exec(query_aplicacoes).all()
    por_lancamento: dict[int, list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes:
        por_lancamento.setdefault(ap.lancamento_id, []).append(ap)

    _candidatas_cache: list | None = None

    def candidatas_herd() -> list[dict]:
        nonlocal _candidatas_cache
        if _candidatas_cache is None:
            query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
            if fazenda_id is not None:
                query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
            animais = session.exec(query_animais).all()
            query_servicos = select(Servico).where(Servico.ult_ocorrencia == 1)
            if fazenda_id is not None:
                query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
            servicos = session.exec(query_servicos).all()
            diag_por_animal = {s.numero_matriz: s.diagnostico for s in servicos}
            iatf_input = [
                {
                    "numero_matriz": a.numero, "sit_rep": a.sit_rep, "del_dias": a.del_dias,
                    "diagnostico_ultimo": diag_por_animal.get(a.numero),
                }
                for a in animais
            ]
            candidatas = selecionar_candidatas_iatf(iatf_input)
            _candidatas_cache = [
                {"numero_matriz": c.numero_matriz, "sit_rep": c.sit_rep, "del_dias": c.del_dias, "motivo": c.motivo}
                for c in candidatas
            ]
        return _candidatas_cache

    ativos = []
    for lanc in lancamentos:
        aps = por_lancamento.get(lanc.id, [])
        pendentes = [a for a in aps if not a.realizada]
        d11s = [a for a in aps if a.dia == 11]

        # Concluído se todas as etapas já foram marcadas realizada OU se o
        # próprio calendário já passou do D11 previsto — este segundo caso
        # cobre o protocolo abandonado (ninguém marcou "realizada" em cada
        # etapa, mas D0/D7/D9/D11 já ficaram todos no passado); sem isto, o
        # card "IATF atual" da Agenda ficava mostrando para sempre "D0" de um
        # protocolo que já devia ter virado "última IATF" há muito tempo. Só
        # se aplica quando o D11 já está cadastrado — sem ele não há data
        # prevista pra comparar (protocolo ainda em criação/incompleto).
        data_d11_prevista = max((a.data_prevista for a in d11s), default=None)
        concluido = not pendentes or (data_d11_prevista is not None and hoje > data_d11_prevista)
        if concluido:
            if not d11s:
                continue  # protocolo sem etapa D11 cadastrada — nada a projetar
            data_d11 = max((a.data_realizacao or a.data_prevista) for a in d11s)
            proxima_visita = data_d11 + timedelta(days=intervalo)
            if hoje > proxima_visita + timedelta(days=7):
                continue  # já passou da janela útil — não mostra mais
            animais_concluidos = sorted({ap.numero_matriz for ap in aps}, key=chave_numero)
            ativos.append({
                "lancamento_id": lanc.id,
                "nome_protocolo": lanc.nome_protocolo,
                "data_d0": lanc.data_d0.isoformat(),
                "animais": [{"numero_matriz": n, "etapa_atual": "Concluído", "data_etapa_atual": None} for n in animais_concluidos],
                "concluido": True,
                "data_d11": data_d11.isoformat(),
                "proxima_visita": proxima_visita.isoformat(),
                "candidatas_proxima_visita": candidatas_herd(),
            })
            continue

        por_animal: dict[str, list[ProtocoloIatfAplicacao]] = {}
        for ap in aps:
            por_animal.setdefault(ap.numero_matriz, []).append(ap)
        animais_status = []
        for numero, aps_animal in sorted(por_animal.items(), key=lambda item: chave_numero(item[0])):
            pendentes_animal = [a for a in aps_animal if not a.realizada]
            if not pendentes_animal:
                animais_status.append({"numero_matriz": numero, "etapa_atual": "Concluído", "data_etapa_atual": None})
                continue
            # Próxima etapa é sempre calculada pela DATA, não por qual etapa
            # foi marcada "realizada" — do contrário, uma etapa nunca
            # confirmada manualmente trava a exibição em "D0"/"D7" para
            # sempre, mesmo com o calendário já bem à frente (ver #reformular
            # relatório gerencial de IATF atual). Chega em D11 e fica lá até
            # ultrapassar data_d11_prevista, quando o grupo inteiro entra no
            # ramo "concluído" acima.
            by_dia = {a.dia: a for a in aps_animal}
            d0, d7, d9, d11 = by_dia.get(0), by_dia.get(7), by_dia.get(9), by_dia.get(11)
            if d0 and hoje <= d0.data_prevista:
                proxima = d0
            elif d7 and hoje <= d7.data_prevista:
                proxima = d7
            elif d9 and hoje <= d9.data_prevista:
                proxima = d9
            else:
                proxima = d11 or min(pendentes_animal, key=lambda a: a.dia)
            animais_status.append({
                "numero_matriz": numero,
                "etapa_atual": f"D{proxima.dia}",
                "data_etapa_atual": proxima.data_prevista.isoformat(),
            })
        ativos.append({
            "lancamento_id": lanc.id,
            "nome_protocolo": lanc.nome_protocolo,
            "data_d0": lanc.data_d0.isoformat(),
            "animais": animais_status,
            "concluido": False,
        })
    return ativos


@router.get("/protocolo-iatf/candidatas")
def candidatas_iatf_projetadas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Candidatas à próxima IATF (mesmo critério de `selecionar_candidatas_iatf`
    usado na Agenda), com projeção de aptidão na data do próximo serviço —
    último serviço do rebanho + `intervalo_visita_reprodutiva` dias (Configurações
    > Parâmetros). Usado em Histórico > Reprodução > Ciclos de IATF."""
    from fazenda.rules.iatf import selecionar_candidatas_iatf
    from fazenda.rules.parametros import get_param, intervalo_visita_reprodutiva

    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = date.today()
    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais = session.exec(query_animais).all()
    query_servicos = select(Servico)
    if fazenda_id is not None:
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
    todos_servicos = session.exec(query_servicos).all()
    diag_por_animal = {s.numero_matriz: s.diagnostico for s in todos_servicos if s.ult_ocorrencia == 1}
    iatf_input = [
        {"numero_matriz": a.numero, "sit_rep": a.sit_rep, "del_dias": a.del_dias,
         "diagnostico_ultimo": diag_por_animal.get(a.numero)}
        for a in animais
    ]
    candidatas = selecionar_candidatas_iatf(iatf_input)

    datas_servico = [s.data_servico for s in todos_servicos if s.data_servico]
    intervalo = intervalo_visita_reprodutiva()
    proxima_visita = (max(datas_servico) + timedelta(days=intervalo)) if (datas_servico and intervalo > 0) else None
    dias_ate_visita = (proxima_visita - hoje).days if proxima_visita else None
    pev_dias = int(get_param("pev_dias", 45) or 45)

    resultado = []
    for c in candidatas:
        del_projetado = (c.del_dias + dias_ate_visita) if (c.del_dias is not None and dias_ate_visita is not None) else c.del_dias
        # "Diagnóstico negativo" não depende de DEL/PEV — já é candidata apta
        # independente da data; as demais (vazia apta/em atraso) só se
        # confirmam se o DEL projetado ainda cobrir o PEV na data da visita.
        apta_projetada = True if c.motivo == "Diagnóstico negativo" else (del_projetado is not None and del_projetado >= pev_dias)
        resultado.append({
            "numero_matriz": c.numero_matriz, "sit_rep": c.sit_rep, "del_dias": c.del_dias, "motivo": c.motivo,
            "del_dias_projetado": del_projetado, "apta_na_proxima_visita": apta_projetada,
        })
    return {"candidatas": resultado, "proxima_visita_iatf": proxima_visita.isoformat() if proxima_visita else None}


@router.get("/protocolo-iatf/lancamentos")
def listar_lancamentos_iatf(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Todos os lançamentos de protocolo IATF (para adicionar animais a um
    protocolo já existente — mesmo D0 e mesmo nome). Mais recentes primeiro.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_lancamentos = select(ProtocoloIatfLancamento).order_by(
        ProtocoloIatfLancamento.data_d0.desc(), ProtocoloIatfLancamento.id.desc()
    )
    if fazenda_id is not None:
        query_lancamentos = query_lancamentos.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query_lancamentos).all()
    query_aplicacoes = select(ProtocoloIatfAplicacao)
    if fazenda_id is not None:
        query_aplicacoes = query_aplicacoes.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    aplicacoes = session.exec(query_aplicacoes).all()
    animais_por_lanc: dict[int, set[str]] = {}
    for ap in aplicacoes:
        animais_por_lanc.setdefault(ap.lancamento_id, set()).add(ap.numero_matriz)
    return [
        {
            "lancamento_id": l.id,
            "nome_protocolo": l.nome_protocolo,
            "data_d0": l.data_d0.isoformat(),
            "qtd_animais": len(animais_por_lanc.get(l.id, set())),
        }
        for l in lancamentos
    ]


class AdicionarAnimaisIatfIn(BaseModel):
    animais: list[str]


@router.post("/protocolo-iatf/{lancamento_id}/animais")
def adicionar_animais_iatf(
    lancamento_id: int,
    dados: AdicionarAnimaisIatfIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Adiciona animais a um protocolo IATF já lançado (esqueci de incluí-los na
    hora). Reaproveita a MESMA data de D0 e os mesmos hormônios por dia; ignora
    animais que já estão no protocolo.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = session.get(ProtocoloIatfLancamento, lancamento_id)
    if not lancamento or (fazenda_id is not None and lancamento.fazenda_id not in (None, fazenda_id)):
        raise HTTPException(status_code=404, detail="Protocolo IATF não encontrado")
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    ja_no_protocolo = {
        a.numero_matriz for a in session.exec(
            select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lancamento_id)
        ).all()
    }
    # Hormônios por dia deste lançamento → mesma descrição das etapas.
    hormonios = session.exec(
        select(ProtocoloIatfHormonio).where(ProtocoloIatfHormonio.lancamento_id == lancamento_id)
    ).all()
    hormonios_por_dia: dict[int, list[ProtocoloIatfHormonio]] = {}
    for h in hormonios:
        hormonios_por_dia.setdefault(h.dia, []).append(h)

    def _descricao_dia(dias: int, padrao: str) -> str:
        hs = hormonios_por_dia.get(dias)
        if not hs:
            return padrao
        return " + ".join(f"{h.dose or ''}{(' ' + h.unidade) if h.unidade else ''} {h.produto}".strip() for h in hs)

    novos = 0
    for numero in dados.animais:
        if numero in ja_no_protocolo:
            continue
        for dias, descricao in PASSOS_PROTOCOLO_IATF:
            session.add(ProtocoloIatfAplicacao(
                lancamento_id=lancamento_id,
                numero_matriz=numero,
                dia=dias,
                descricao=_descricao_dia(dias, descricao),
                data_prevista=lancamento.data_d0 + timedelta(days=dias),
            ))
        novos += 1

    session.commit()
    return {"adicionados": novos, "lancamento_id": lancamento_id, "nome_protocolo": lancamento.nome_protocolo}


def _mapa_tipo_semen_por_touro(session: Session) -> dict[str, str]:
    """touro_nome (minúsculo) -> tipo (convencional/sexado/fazenda) do Estoque
    de Sêmen — usado para completar o tipo_semen de serviços antigos que não
    gravaram a modalidade no momento da inseminação."""
    mapa: dict[str, str] = {}
    for e in session.exec(select(EstoqueSemen)).all():
        if e.touro_nome:
            mapa.setdefault(e.touro_nome.strip().lower(), e.tipo or "convencional")
    return mapa


def _baixar_dose_semen(session: Session, reprodutor: str | None, tipo_semen: str | None, quantidade: int) -> None:
    """Desconta `quantidade` doses do Estoque de Sêmen do touro usado, casando
    por nome, NAAB ou código. Quando o tipo (sexado/convencional/fazenda) é
    conhecido, restringe o casamento a esse tipo primeiro — o mesmo touro pode
    ter linhas de estoque separadas por modalidade, e usar a errada bagunçaria
    o saldo de quem realmente tem doses. Sem casamento por tipo (ou tipo
    desconhecido), cai no casamento antigo por nome/NAAB/código, para não
    quebrar compras/lançamentos que ainda não informam o tipo."""
    if not reprodutor:
        return
    alvo = reprodutor.strip().lower()
    candidatos = [
        t for t in session.exec(select(EstoqueSemen)).all()
        if (t.touro_nome or "").strip().lower() == alvo
        or (t.naab or "").strip().lower() == alvo
        or (t.codigo or "").strip().lower() == alvo
    ]
    if tipo_semen:
        por_tipo = [t for t in candidatos if t.tipo == tipo_semen]
        if por_tipo:
            candidatos = por_tipo
    touro = candidatos[0] if candidatos else None
    if touro:
        touro.doses = touro.doses - quantidade
        touro.atualizado_em = datetime.utcnow()
        session.add(touro)


class ServicoIn(BaseModel):
    numero_matriz: str
    data_servico: date
    tipo_servico: str = "IA"  # "IA" | "Monta natural"
    protocolo: str | None = None  # preenchido = veio de um protocolo IATF; vazio = cio natural
    reprodutor: str | None = None
    responsavel: str | None = None
    tipo_semen: str | None = None  # convencional | sexado | fazenda


@router.post("/servico")
def registrar_servico(
    dados: ServicoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Registra a inseminação/cobertura em si — cio natural (sem protocolo) ou a
    inseminação de um protocolo IATF já agendado (protocolo preenchido).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_animal = select(Animal).where(Animal.numero == dados.numero_matriz)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Matriz não encontrada")

    query_anteriores = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query_anteriores = query_anteriores.where(Servico.fazenda_id == fazenda_id)
    anteriores = session.exec(query_anteriores).all()
    for s in anteriores:
        if s.ult_ocorrencia == 1:
            s.ult_ocorrencia = 0
            session.add(s)

    ultimo = max(anteriores, key=lambda s: s.data_servico or date.min, default=None)
    ordem_tentativa = (ultimo.ordem_tentativa or 0) + 1 if ultimo else 1
    intervalo = (dados.data_servico - ultimo.data_servico).days if ultimo and ultimo.data_servico else None

    servico = Servico(
        animal_id=animal.id,
        numero_matriz=dados.numero_matriz,
        raca_matriz=animal.raca,
        data_nasc_matriz=animal.data_nasc,
        data_servico=dados.data_servico,
        tipo_servico=dados.tipo_servico,
        protocolo=dados.protocolo,
        reprodutor=dados.reprodutor,
        tipo_semen=dados.tipo_semen,
        inseminador=dados.responsavel,
        ordem_tentativa=ordem_tentativa,
        intervalo_tentativas=intervalo,
        del_servico=animal.del_dias,
        ult_ocorrencia=1,
        usuario_id=usuario_id_seguro(user),
        fazenda_id=fazenda_id,
    )
    session.add(servico)
    # Desconta 1 dose do Estoque de Sêmen (mesma regra do lançamento em lote,
    # ver registrar_servico_lote) — não se aplica a monta natural, que não usa
    # sêmen estocado.
    if dados.tipo_servico != "Monta natural":
        _baixar_dose_semen(session, dados.reprodutor, dados.tipo_semen, 1)

    # Veio de um protocolo IATF: resolve automaticamente a aplicação D11 em
    # aberto correspondente — a Agenda para de lembrar essa etapa sozinha,
    # sem exigir um segundo clique de "marcar realizado" separado.
    if dados.protocolo:
        query_ap_d11 = (
            select(ProtocoloIatfAplicacao)
            .join(ProtocoloIatfLancamento, ProtocoloIatfAplicacao.lancamento_id == ProtocoloIatfLancamento.id)
            .where(
                ProtocoloIatfAplicacao.numero_matriz == dados.numero_matriz,
                ProtocoloIatfAplicacao.dia == 11,
                ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
                ProtocoloIatfLancamento.nome_protocolo == dados.protocolo,
            )
        )
        if fazenda_id is not None:
            query_ap_d11 = query_ap_d11.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
        aplicacao_d11 = session.exec(query_ap_d11).first()
        if aplicacao_d11:
            aplicacao_d11.realizada = True
            aplicacao_d11.data_realizacao = dados.data_servico
            session.add(aplicacao_d11)

    session.commit()
    session.refresh(servico)
    return servico.model_dump()


def _nome_auto_iatf(d0: date) -> str:
    """Nome padrão do protocolo IATF: 'IATF <D0> A <D11>' (datas dd/mm/aa)."""
    d11 = d0 + timedelta(days=11)
    return f"IATF {d0.strftime('%d/%m/%y')} A {d11.strftime('%d/%m/%y')}"


def _registrar_um_servico(session: Session, numero_matriz: str, data_servico: date,
                          tipo_servico: str, protocolo: str | None, reprodutor: str | None,
                          inseminador: str | None = None, usuario_id: int | None = None,
                          tipo_semen: str | None = None, fazenda_id: int | None = None) -> Servico | None:
    """Cria um Servico para uma matriz (mesma lógica de registrar_servico, sem
    commit) — resolve o D11 do protocolo IATF vinculado, se houver."""
    query_animal = select(Animal).where(Animal.numero == numero_matriz)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        return None
    query_anteriores = select(Servico).where(Servico.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        query_anteriores = query_anteriores.where(Servico.fazenda_id == fazenda_id)
    anteriores = session.exec(query_anteriores).all()
    for s in anteriores:
        if s.ult_ocorrencia == 1:
            s.ult_ocorrencia = 0
            session.add(s)
    ultimo = max(anteriores, key=lambda s: s.data_servico or date.min, default=None)
    ordem_tentativa = (ultimo.ordem_tentativa or 0) + 1 if ultimo else 1
    intervalo = (data_servico - ultimo.data_servico).days if ultimo and ultimo.data_servico else None
    servico = Servico(
        animal_id=animal.id, numero_matriz=numero_matriz, raca_matriz=animal.raca,
        data_nasc_matriz=animal.data_nasc, data_servico=data_servico, tipo_servico=tipo_servico,
        protocolo=protocolo, reprodutor=reprodutor, tipo_semen=tipo_semen, inseminador=inseminador,
        ordem_tentativa=ordem_tentativa,
        intervalo_tentativas=intervalo, del_servico=animal.del_dias, ult_ocorrencia=1, usuario_id=usuario_id,
        fazenda_id=fazenda_id,
    )
    session.add(servico)
    if protocolo:
        query_ap_d11 = (
            select(ProtocoloIatfAplicacao)
            .join(ProtocoloIatfLancamento, ProtocoloIatfAplicacao.lancamento_id == ProtocoloIatfLancamento.id)
            .where(
                ProtocoloIatfAplicacao.numero_matriz == numero_matriz,
                ProtocoloIatfAplicacao.dia == 11,
                ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
                ProtocoloIatfLancamento.nome_protocolo == protocolo,
            )
        )
        if fazenda_id is not None:
            query_ap_d11 = query_ap_d11.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
        ap_d11 = session.exec(query_ap_d11).first()
        if ap_d11:
            ap_d11.realizada = True
            ap_d11.data_realizacao = data_servico
            session.add(ap_d11)
    return servico


def _animal_tem_protocolo_pendente(
    session: Session, numero_matriz: str, fazenda_id: int | None = None
) -> ProtocoloIatfLancamento | None:
    """Retorna o lançamento IATF com etapa pendente do animal (o mais recente)."""
    query_ap = select(ProtocoloIatfAplicacao).where(
        ProtocoloIatfAplicacao.numero_matriz == numero_matriz, ProtocoloIatfAplicacao.realizada == False  # noqa: E712
    )
    if fazenda_id is not None:
        query_ap = query_ap.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    ap = session.exec(query_ap).all()
    if not ap:
        return None
    lanc_ids = {a.lancamento_id for a in ap}
    lancs = [l for l in (session.get(ProtocoloIatfLancamento, lid) for lid in lanc_ids) if l]
    return max(lancs, key=lambda l: l.data_d0, default=None) if lancs else None


class ServicoLoteIn(BaseModel):
    animais: list[str]
    data_servico: date
    tipo: str  # "cio_natural" | "iatf" | "monta_natural"
    reprodutor: str | None = None
    responsavel: str | None = None
    protocolo_lancamento_id: int | None = None  # IATF: vincular a este lançamento
    auto_lancar_iatf: bool = False  # IATF: se não há protocolo, cria um retroativo (D0 = serviço − 11)
    tipo_semen: str | None = None  # convencional | sexado | fazenda


@router.post("/servico-lote")
def registrar_servico_lote(
    dados: ServicoLoteIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Inseminação de vários animais de uma vez. `tipo` = cio_natural (IA sem
    protocolo), iatf (IA vinculada a protocolo) ou monta_natural. No IATF, se o
    animal não estiver em protocolo e `auto_lancar_iatf`, cria um protocolo
    retroativo (D0 = data do serviço − 11) só para registrar/vincular — sem
    hormônio. Animais IATF sem protocolo e sem auto-lançar entram em
    `incompativeis` (a UI pergunta o que fazer).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")
    if dados.tipo not in ("cio_natural", "iatf", "monta_natural"):
        raise HTTPException(status_code=400, detail="Tipo inválido")

    tipo_servico = "Monta natural" if dados.tipo == "monta_natural" else "IA"
    lanc_escolhido = session.get(ProtocoloIatfLancamento, dados.protocolo_lancamento_id) if dados.protocolo_lancamento_id else None
    if lanc_escolhido and fazenda_id is not None and lanc_escolhido.fazenda_id not in (None, fazenda_id):
        lanc_escolhido = None

    criados, incompativeis = 0, []
    for numero in dados.animais:
        protocolo_name: str | None = None
        if dados.tipo == "iatf":
            alvo = lanc_escolhido or _animal_tem_protocolo_pendente(session, numero, fazenda_id=fazenda_id)
            if alvo is None and dados.auto_lancar_iatf:
                d0 = dados.data_servico - timedelta(days=11)
                alvo = ProtocoloIatfLancamento(
                    nome_protocolo=_nome_auto_iatf(d0), data_d0=d0, retroativo=True,
                    usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
                )
                session.add(alvo)
                session.flush()
                for dias, descricao in PASSOS_PROTOCOLO_IATF:
                    session.add(ProtocoloIatfAplicacao(
                        lancamento_id=alvo.id, numero_matriz=numero, dia=dias,
                        descricao=descricao, data_prevista=d0 + timedelta(days=dias),
                        fazenda_id=fazenda_id,
                    ))
            elif alvo is not None:
                ja = session.exec(
                    select(ProtocoloIatfAplicacao).where(
                        ProtocoloIatfAplicacao.lancamento_id == alvo.id,
                        ProtocoloIatfAplicacao.numero_matriz == numero,
                    )
                ).first()
                if not ja:
                    for dias, descricao in PASSOS_PROTOCOLO_IATF:
                        session.add(ProtocoloIatfAplicacao(
                            lancamento_id=alvo.id, numero_matriz=numero, dia=dias,
                            descricao=descricao, data_prevista=alvo.data_d0 + timedelta(days=dias),
                            fazenda_id=fazenda_id,
                        ))
            if alvo is None:
                incompativeis.append(numero)
                continue
            session.flush()
            protocolo_name = alvo.nome_protocolo

        s = _registrar_um_servico(
            session, numero, dados.data_servico, tipo_servico, protocolo_name, dados.reprodutor, dados.responsavel,
            usuario_id=usuario_id_seguro(user), tipo_semen=dados.tipo_semen, fazenda_id=fazenda_id,
        )
        if s is None:
            incompativeis.append(numero)
        else:
            criados += 1

    # Desconta 1 dose por inseminação realizada (IA — cio natural ou IATF; não
    # se aplica à monta natural, que não usa sêmen estocado) do touro
    # informado — mantém o Estoque de Sêmen em dia com o uso real sem exigir
    # baixa manual a cada inseminação.
    if criados and dados.tipo != "monta_natural" and dados.reprodutor:
        _baixar_dose_semen(session, dados.reprodutor, dados.tipo_semen, criados)

    session.commit()
    return {"criados": criados, "incompativeis": incompativeis, "tipo": dados.tipo}
