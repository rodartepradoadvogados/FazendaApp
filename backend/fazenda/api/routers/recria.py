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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    Animal, BenchmarkRecria, FaseRecria, JanelaPontoCritico, MetaRecria, OcorrenciaClinica,
    Parto, PesagemCorporal, PesoAlvoIdade, RegistroCocho, Servico,
)
from fazenda.rules.coorte import (
    FASES_PADRAO, curva_casos_por_idade, idade_em_dias, incidencia_por_fase, ponto_critico,
)
from fazenda.rules.reproducao_dossie import (
    DIAS_MES, custo_recria_excedente, distribuicao_idade_parto, estatisticas_idade_parto, taxa_prenhez_ciclos,
)

router = APIRouter(prefix="/recria", tags=["recria"])


# --- Helpers ---------------------------------------------------------------
def _nascimentos(session: Session) -> dict[str, date]:
    """numero -> data de nascimento (só animais com data)."""
    return {
        a.numero: a.data_nasc
        for a in session.exec(select(Animal)).all()
        if a.data_nasc and not a.eh_semen
    }


def _idade_atual(session: Session, hoje: date) -> dict[str, int]:
    """numero -> idade em dias hoje (ou na data de baixa, se já saiu)."""
    out: dict[str, int] = {}
    for a in session.exec(select(Animal)).all():
        if not a.data_nasc or a.eh_semen:
            continue
        ref = a.data_baixa if (a.data_baixa and not a.ativo) else hoje
        out[a.numero] = (ref - a.data_nasc).days
    return out


def _fases(session: Session) -> list[dict]:
    linhas = session.exec(select(FaseRecria).where(FaseRecria.ativo == True)).all()  # noqa: E712
    if not linhas:
        return FASES_PADRAO
    return [{"nome": f.nome, "dia_min": f.dia_min, "dia_max": f.dia_max}
            for f in sorted(linhas, key=lambda x: (x.ordem, x.dia_min))]


# --- Pilar Saúde -----------------------------------------------------------
@router.get("/doencas")
def listar_doencas_com_casos(session: Session = Depends(get_session)) -> list[dict]:
    """Doenças que já têm ocorrências lançadas (para o seletor do Dossiê)."""
    cont: dict[str, int] = {}
    for o in session.exec(select(OcorrenciaClinica)).all():
        cont[o.doenca] = cont.get(o.doenca, 0) + 1
    return [{"doenca": d, "casos": cont[d]} for d in sorted(cont)]


@router.get("/saude/curva")
def curva_saude(
    doenca: str, ini: date | None = None, fim: date | None = None,
    limite_dias: int = 300, session: Session = Depends(get_session),
) -> dict:
    """Curva casos×idade (dias) + ponto crítico + incidência por fase."""
    nasc = _nascimentos(session)
    ocorrencias = [
        o for o in session.exec(select(OcorrenciaClinica).where(OcorrenciaClinica.doenca == doenca)).all()
        if (not ini or o.data_ocorrencia >= ini) and (not fim or o.data_ocorrencia <= fim)
    ]
    pares = []  # (numero, idade_dias)
    for o in ocorrencias:
        idade = idade_em_dias(nasc.get(o.numero_matriz), o.data_ocorrencia)
        if idade is not None:
            pares.append((o.numero_matriz, idade))

    curva = curva_casos_por_idade([p[1] for p in pares], limite_dias=limite_dias)
    pc = ponto_critico(curva)
    fases = _fases(session)
    incid = incidencia_por_fase(pares, _idade_atual(session, date.today()), fases)
    return {
        "doenca": doenca,
        "total_casos": len(pares),
        "curva": curva,
        "ponto_critico": pc,
        "incidencia_por_fase": incid,
    }


# --- Pilar Crescimento -----------------------------------------------------
@router.get("/crescimento/peso-alvo")
def crescimento_peso_alvo(session: Session = Depends(get_session)) -> dict:
    """Peso real médio por mês de idade × faixa de peso-alvo cadastrada."""
    nasc = _nascimentos(session)
    # Peso real: média das pesagens agrupadas por mês de idade na data da pesagem.
    por_mes: dict[int, list[float]] = {}
    for p in session.exec(select(PesagemCorporal)).all():
        if not p.peso_kg or not p.data_pesagem:
            continue
        d = idade_em_dias(nasc.get(p.numero_matriz), p.data_pesagem)
        if d is None:
            continue
        mes = max(1, round(d / 30.44))
        por_mes.setdefault(mes, []).append(p.peso_kg)

    alvo = {a.mes: (a.peso_min_kg, a.peso_max_kg) for a in session.exec(select(PesoAlvoIdade)).all()}
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


# --- Pilar Reprodução ------------------------------------------------------
@router.get("/reproducao/idade-parto")
def reproducao_idade_parto(session: Session = Depends(get_session)) -> dict:
    """Relatório Wisconsin: estatística da idade ao 1º parto + distribuição +
    custo de recria excedente (usa a meta e o custo diário cadastrados)."""
    nasc = _nascimentos(session)
    # 1º parto de cada animal = parto de ordem 1, ou o mais antigo se não houver ordem.
    primeiro: dict[str, date] = {}
    for p in session.exec(select(Parto)).all():
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

    meta = session.get(MetaRecria, 1) or MetaRecria(id=1)
    return {
        "meta_idade_parto": meta.idade_parto_meses,
        "estatisticas": estatisticas_idade_parto(idades),
        "distribuicao": distribuicao_idade_parto(idades),
        "custo_excedente": custo_recria_excedente(idades, meta.idade_parto_meses, meta.custo_diario_recria),
    }


@router.get("/reproducao/taxa-prenhez")
def reproducao_taxa_prenhez(
    ini: date, fim: date, vwp_dias: int = 0, session: Session = Depends(get_session),
) -> dict:
    """Taxa de Prenhez em ciclos de 21 dias (Taxa de Serviço × Concepção)."""
    servicos = []
    for s in session.exec(select(Servico)).all():
        if not s.data_servico:
            continue
        servicos.append({
            "numero": s.numero_matriz,
            "data_servico": s.data_servico,
            "prenhe": (s.diagnostico or "").strip().upper() == "POSITIVO",
            "elegivel_desde": s.data_ult_parto,
        })
    ciclos = taxa_prenhez_ciclos(servicos, ini, fim, vwp_dias)
    # Resumo do período: PR média ponderada pelos elegíveis.
    tot_el = sum(c["elegiveis"] for c in ciclos)
    tot_pr = sum((c["taxa_prenhez"] or 0) * c["elegiveis"] for c in ciclos)
    return {
        "ciclos": ciclos,
        "taxa_prenhez_media": round(tot_pr / tot_el, 1) if tot_el else None,
        "total_servicos": len(servicos),
    }


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
) -> dict:
    linhas = session.exec(select(RegistroCocho).order_by(RegistroCocho.data.desc())).all()
    saida = []
    for r in linhas:
        if lote and r.lote != lote:
            continue
        if ini and r.data < ini:
            continue
        if fim and r.data > fim:
            continue
        saida.append(_serializa_cocho(r))
    lotes = sorted({r.lote for r in linhas})
    return {"registros": saida, "lotes": lotes}


@router.post("/cocho", status_code=201)
def criar_cocho(dados: CochoIn, session: Session = Depends(get_session)) -> dict:
    if not dados.lote.strip():
        raise HTTPException(status_code=400, detail="Informe o lote.")
    if dados.kg_sobra > dados.kg_ofertado:
        raise HTTPException(status_code=400, detail="A sobra não pode ser maior que o ofertado.")
    r = RegistroCocho(**dados.model_dump())
    r.lote = dados.lote.strip()
    session.add(r)
    session.commit()
    session.refresh(r)
    return _serializa_cocho(r)


@router.delete("/cocho/{cocho_id}")
def excluir_cocho(cocho_id: int, session: Session = Depends(get_session)) -> dict:
    r = session.get(RegistroCocho, cocho_id)
    if r:
        session.delete(r)
        session.commit()
    return {"ok": True}


# --- Ocorrências clínicas (lançamento) -------------------------------------
class OcorrenciaIn(BaseModel):
    numero_matriz: str
    doenca: str
    data_ocorrencia: date
    observacao: str | None = None


@router.get("/ocorrencias")
def listar_ocorrencias(
    doenca: str = "", numero_matriz: str = "", session: Session = Depends(get_session),
) -> list[dict]:
    q = session.exec(select(OcorrenciaClinica).order_by(OcorrenciaClinica.data_ocorrencia.desc())).all()
    saida = []
    for o in q:
        if doenca and o.doenca != doenca:
            continue
        if numero_matriz and o.numero_matriz != numero_matriz:
            continue
        saida.append(o.model_dump())
    return saida


@router.post("/ocorrencias", status_code=201)
def criar_ocorrencia(dados: OcorrenciaIn, session: Session = Depends(get_session)) -> dict:
    if not dados.numero_matriz.strip() or not dados.doenca.strip():
        raise HTTPException(status_code=400, detail="Informe o animal e a doença.")
    o = OcorrenciaClinica(
        numero_matriz=dados.numero_matriz.strip(), doenca=dados.doenca.strip(),
        data_ocorrencia=dados.data_ocorrencia, observacao=(dados.observacao or None), origem="manual",
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o.model_dump()


@router.delete("/ocorrencias/{ocorrencia_id}")
def excluir_ocorrencia(ocorrencia_id: int, session: Session = Depends(get_session)) -> dict:
    o = session.get(OcorrenciaClinica, ocorrencia_id)
    if not o:
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
def obter_metas(session: Session = Depends(get_session)) -> dict:
    m = session.get(MetaRecria, 1)
    if not m:
        m = MetaRecria(id=1)
        session.add(m)
        session.commit()
        session.refresh(m)
    return m.model_dump()


@router.put("/metas")
def salvar_metas(dados: MetaIn, session: Session = Depends(get_session)) -> dict:
    m = session.get(MetaRecria, 1) or MetaRecria(id=1)
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
def listar_peso_alvo(session: Session = Depends(get_session)) -> list[dict]:
    linhas = session.exec(select(PesoAlvoIdade).order_by(PesoAlvoIdade.mes)).all()
    return [l.model_dump() for l in linhas]


@router.post("/peso-alvo", status_code=201)
def salvar_peso_alvo(dados: PesoAlvoIn, session: Session = Depends(get_session)) -> dict:
    """Cria ou atualiza a faixa daquele mês (upsert por mês)."""
    if dados.peso_min_kg > dados.peso_max_kg:
        raise HTTPException(status_code=400, detail="Peso mínimo não pode ser maior que o máximo.")
    linha = session.exec(select(PesoAlvoIdade).where(PesoAlvoIdade.mes == dados.mes)).first()
    if linha:
        linha.peso_min_kg = dados.peso_min_kg
        linha.peso_max_kg = dados.peso_max_kg
    else:
        linha = PesoAlvoIdade(mes=dados.mes, peso_min_kg=dados.peso_min_kg, peso_max_kg=dados.peso_max_kg)
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return linha.model_dump()


@router.delete("/peso-alvo/{mes}")
def excluir_peso_alvo(mes: int, session: Session = Depends(get_session)) -> dict:
    linha = session.exec(select(PesoAlvoIdade).where(PesoAlvoIdade.mes == mes)).first()
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
def listar_fases(session: Session = Depends(get_session)) -> list[dict]:
    linhas = session.exec(select(FaseRecria).order_by(FaseRecria.ordem, FaseRecria.dia_min)).all()
    return [l.model_dump() for l in linhas]


@router.post("/fases", status_code=201)
def criar_fase(dados: FaseIn, session: Session = Depends(get_session)) -> dict:
    if dados.dia_min > dados.dia_max:
        raise HTTPException(status_code=400, detail="Dia inicial não pode ser maior que o final.")
    f = FaseRecria(**dados.model_dump())
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()


@router.delete("/fases/{fase_id}")
def excluir_fase(fase_id: int, session: Session = Depends(get_session)) -> dict:
    f = session.get(FaseRecria, fase_id)
    if f:
        session.delete(f)
        session.commit()
    return {"ok": True}


# --- Cadastros: Janelas de ponto crítico -----------------------------------
class JanelaIn(BaseModel):
    doenca: str
    dia_min: int
    dia_max: int
    dias_antecedencia: int = 3
    ativo: bool = True


@router.get("/janelas")
def listar_janelas(session: Session = Depends(get_session)) -> list[dict]:
    linhas = session.exec(select(JanelaPontoCritico).order_by(JanelaPontoCritico.doenca)).all()
    return [l.model_dump() for l in linhas]


@router.post("/janelas", status_code=201)
def criar_janela(dados: JanelaIn, session: Session = Depends(get_session)) -> dict:
    if dados.dia_min > dados.dia_max:
        raise HTTPException(status_code=400, detail="Dia inicial não pode ser maior que o final.")
    j = JanelaPontoCritico(**dados.model_dump())
    session.add(j)
    session.commit()
    session.refresh(j)
    return j.model_dump()


@router.delete("/janelas/{janela_id}")
def excluir_janela(janela_id: int, session: Session = Depends(get_session)) -> dict:
    j = session.get(JanelaPontoCritico, janela_id)
    if j:
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
def listar_benchmark(session: Session = Depends(get_session)) -> list[dict]:
    linhas = session.exec(select(BenchmarkRecria).order_by(BenchmarkRecria.ordem, BenchmarkRecria.indicador)).all()
    return [{**b.model_dump(), "faixa_fazenda": _faixa_benchmark(b)} for b in linhas]


@router.post("/benchmark", status_code=201)
def salvar_benchmark(dados: BenchmarkIn, session: Session = Depends(get_session)) -> dict:
    """Upsert por indicador."""
    b = session.exec(select(BenchmarkRecria).where(BenchmarkRecria.indicador == dados.indicador)).first()
    if b:
        for campo, valor in dados.model_dump().items():
            setattr(b, campo, valor)
        b.atualizado_em = datetime.utcnow()
    else:
        b = BenchmarkRecria(**dados.model_dump())
    session.add(b)
    session.commit()
    session.refresh(b)
    return {**b.model_dump(), "faixa_fazenda": _faixa_benchmark(b)}


@router.delete("/benchmark/{benchmark_id}")
def excluir_benchmark(benchmark_id: int, session: Session = Depends(get_session)) -> dict:
    b = session.get(BenchmarkRecria, benchmark_id)
    if b:
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


def seed_recria(session: Session) -> None:
    """Cria metas (linha única), curva de peso-alvo e janelas padrão se vazio."""
    if not session.get(MetaRecria, 1):
        session.add(MetaRecria(id=1))
    if not session.exec(select(BenchmarkRecria)).first():
        for i, (ind, un, maior, t5, t10, t25, t50, t75, faz) in enumerate(_BENCHMARK_PADRAO):
            session.add(BenchmarkRecria(
                indicador=ind, unidade=un, melhor_e_maior=maior,
                top5=t5, top10=t10, top25=t25, top50=t50, top75=t75, valor_fazenda=faz, ordem=i,
            ))
    if not session.exec(select(PesoAlvoIdade)).first():
        for mes, mn, mx in _PESO_ALVO_PADRAO:
            # Garante mín<=máx (a Foto 7 tem casos de faixa estreita/invertida).
            session.add(PesoAlvoIdade(mes=mes, peso_min_kg=float(min(mn, mx)), peso_max_kg=float(max(mn, mx))))
    if not session.exec(select(JanelaPontoCritico)).first():
        for doenca, dmin, dmax, ant in _JANELAS_PADRAO:
            session.add(JanelaPontoCritico(doenca=doenca, dia_min=dmin, dia_max=dmax, dias_antecedencia=ant))
    session.commit()
