"""
Router de indicadores — painel zootécnico/reprodutivo/produtivo do rebanho.
Endpoint: GET /indicadores/
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Animal, Lote, OcorrenciaClinica, Parto, PesagemCorporal, Sanidade, Servico
from fazenda.rules.indicadores import calcular_indicadores

router = APIRouter(prefix="/indicadores", tags=["indicadores"])

# ---------------------------------------------------------------------------
# Relatório personalizado (Análise > Relatório personalizado) — v1 livre, para
# lapidar depois: catálogo de parâmetros (todos vindos da ficha do animal, um
# valor por animal) que o usuário escolhe livremente (até 10) para montar uma
# tabela e, opcionalmente, um gráfico (até 5 dos parâmetros escolhidos).
# ---------------------------------------------------------------------------
CATALOGO_RELATORIO_PERSONALIZADO = [
    {"id": "numero", "label": "Número do animal", "categoria": "Identificação", "tipo": "texto"},
    {"id": "nome", "label": "Nome", "categoria": "Identificação", "tipo": "texto"},
    {"id": "categoria_completa", "label": "Categoria", "categoria": "Identificação", "tipo": "texto"},
    {"id": "categoria_abrev", "label": "Categoria (abreviada)", "categoria": "Identificação", "tipo": "texto"},
    {"id": "raca", "label": "Raça", "categoria": "Identificação", "tipo": "texto"},
    {"id": "grau_sangue", "label": "Grau de sangue", "categoria": "Identificação", "tipo": "texto"},
    {"id": "sexo", "label": "Sexo", "categoria": "Identificação", "tipo": "texto"},
    {"id": "data_nasc", "label": "Data de nascimento", "categoria": "Identificação", "tipo": "data"},
    {"id": "idade_meses", "label": "Idade (meses)", "categoria": "Identificação", "tipo": "numero"},
    {"id": "mae_numero", "label": "Número da mãe", "categoria": "Identificação", "tipo": "texto"},
    {"id": "proprietario", "label": "Proprietário", "categoria": "Identificação", "tipo": "texto"},
    {"id": "grupo_primario", "label": "Lote atual", "categoria": "Manejo", "tipo": "texto"},
    {"id": "ativo", "label": "Ativo no rebanho?", "categoria": "Manejo", "tipo": "booleano"},
    {"id": "motivo_baixa", "label": "Motivo da baixa", "categoria": "Manejo", "tipo": "texto"},
    {"id": "data_baixa", "label": "Data da baixa", "categoria": "Manejo", "tipo": "data"},
    {"id": "sit_rep", "label": "Situação reprodutiva", "categoria": "Reprodução", "tipo": "texto"},
    {"id": "diagnostico", "label": "Último diagnóstico", "categoria": "Reprodução", "tipo": "texto"},
    {"id": "data_ult_diag", "label": "Data do último diagnóstico", "categoria": "Reprodução", "tipo": "data"},
    {"id": "del_dias", "label": "DEL (dias em lactação)", "categoria": "Produção", "tipo": "numero"},
    {"id": "ult_cl_kg", "label": "Última produção (kg)", "categoria": "Produção", "tipo": "numero"},
    {"id": "data_ult_leite", "label": "Data da última pesagem de leite", "categoria": "Produção", "tipo": "data"},
    {"id": "valor", "label": "Valor de compra (R$)", "categoria": "Financeiro", "tipo": "numero"},
    {"id": "data_entrada", "label": "Data de entrada na fazenda", "categoria": "Financeiro", "tipo": "data"},
    # Colunas computadas (não vêm direto de Animal.model_dump() — calculadas
    # por animal em relatorio_personalizado() a partir de Servico/OcorrenciaClinica).
    {"id": "idade_dias", "label": "Idade (dias)", "categoria": "Identificação", "tipo": "numero"},
    {"id": "numero_servicos", "label": "Número de serviços", "categoria": "Reprodução", "tipo": "numero"},
    {"id": "numero_prenhezes", "label": "Número de prenhezes", "categoria": "Reprodução", "tipo": "numero"},
    {"id": "dias_gestacao_atual", "label": "Tempo de gestação atual (dias)", "categoria": "Reprodução", "tipo": "numero"},
    {"id": "numero_mastites", "label": "Número de mastites", "categoria": "Sanidade", "tipo": "numero"},
]
CATALOGO_POR_ID = {c["id"]: c for c in CATALOGO_RELATORIO_PERSONALIZADO}
COLUNAS_COMPUTADAS = {"idade_dias", "numero_servicos", "numero_prenhezes", "dias_gestacao_atual", "numero_mastites"}
MAX_PARAMETROS_GRAFICO = 8


@router.get("/relatorio-personalizado/catalogo")
def catalogo_relatorio_personalizado() -> list[dict]:
    return CATALOGO_RELATORIO_PERSONALIZADO


class RelatorioPersonalizadoIn(BaseModel):
    parametros: list[str]
    data_de: date | None = None
    data_ate: date | None = None
    # Cutoff (em meses) de "novilha apta" só para o Resumo do período — ver
    # `novilhas_aptas_ate_meses` na resposta. Independente do critério por
    # peso já usado em Indicadores > Gerais (não substitui, só um recorte
    # extra pedido especificamente para este relatório).
    novilhas_aptas_meses: int = 15


@router.post("/relatorio-personalizado")
def relatorio_personalizado(
    dados: RelatorioPersonalizadoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    parametros = list(dict.fromkeys(dados.parametros))  # remove duplicatas, preserva ordem
    if not parametros:
        raise HTTPException(status_code=400, detail="Selecione ao menos 1 parâmetro.")
    invalidos = [p for p in parametros if p not in CATALOGO_POR_ID]
    if invalidos:
        raise HTTPException(status_code=400, detail=f"Parâmetro(s) inválido(s): {', '.join(invalidos)}")

    colunas_data = [p for p in parametros if CATALOGO_POR_ID[p]["tipo"] == "data"]
    query_animais = select(Animal).where(Animal.eh_semen == False)  # noqa: E712
    query_servicos = select(Servico)
    query_partos = select(Parto)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
    animais_rows = session.exec(query_animais).all()
    servicos_rows = session.exec(query_servicos).all()
    partos_rows = session.exec(query_partos).all()
    hoje = date.today()

    precisa_computadas = COLUNAS_COMPUTADAS & set(parametros)
    servicos_por_animal: dict[str, list[Servico]] = {}
    for s in servicos_rows:
        servicos_por_animal.setdefault(s.numero_matriz, []).append(s)
    mastites_por_animal: dict[str, int] = {}
    if "numero_mastites" in precisa_computadas:
        query_ocorrencias = select(OcorrenciaClinica).where(OcorrenciaClinica.doenca.ilike("%mastite%"))
        if fazenda_id is not None:
            query_ocorrencias = query_ocorrencias.where(OcorrenciaClinica.fazenda_id == fazenda_id)
        for o in session.exec(query_ocorrencias).all():
            mastites_por_animal[o.numero_matriz] = mastites_por_animal.get(o.numero_matriz, 0) + 1

    def _computar(numero: str, data_nasc: date | None) -> dict:
        servs = sorted(servicos_por_animal.get(numero, []), key=lambda s: s.data_servico or date.min)
        valores: dict[str, object] = {}
        if "idade_dias" in precisa_computadas:
            valores["idade_dias"] = (hoje - data_nasc).days if data_nasc else None
        if "numero_servicos" in precisa_computadas:
            valores["numero_servicos"] = len(servs)
        if "numero_prenhezes" in precisa_computadas:
            valores["numero_prenhezes"] = sum(1 for s in servs if (s.diagnostico or "").strip().upper() == "POSITIVO")
        if "dias_gestacao_atual" in precisa_computadas:
            positivos = [s for s in servs if (s.diagnostico or "").strip().upper() == "POSITIVO" and not s.data_perda_prenhez]
            valores["dias_gestacao_atual"] = (hoje - positivos[-1].data_servico).days if positivos and positivos[-1].data_servico else None
        if "numero_mastites" in precisa_computadas:
            valores["numero_mastites"] = mastites_por_animal.get(numero, 0)
        return valores

    linhas = []
    for a in animais_rows:
        d = a.model_dump()
        d.update(_computar(a.numero, a.data_nasc))
        if colunas_data and (dados.data_de or dados.data_ate):
            dentro = True
            for col in colunas_data:
                v = d.get(col)
                if not v:
                    dentro = False
                    break
                if dados.data_de and v < dados.data_de:
                    dentro = False
                    break
                if dados.data_ate and v > dados.data_ate:
                    dentro = False
                    break
            if not dentro:
                continue
        linha = {"numero": a.numero}
        for p in parametros:
            linha[p] = d.get(p)
        linhas.append(linha)

    linhas.sort(key=lambda l: l["numero"])

    return {
        "colunas": [CATALOGO_POR_ID[p] for p in parametros],
        "linhas": linhas,
        "resumo": _resumo_relatorio_personalizado(
            animais_rows, servicos_rows, partos_rows, session, fazenda_id,
            dados.novilhas_aptas_meses, dados.data_de, dados.data_ate, len(linhas),
        ),
    }


def _resumo_relatorio_personalizado(
    animais_rows: list[Animal], servicos_rows: list[Servico], partos_rows: list[Parto],
    session: Session, fazenda_id: int | None, novilhas_aptas_meses: int,
    data_de: date | None, data_ate: date | None, quantidade_animais: int,
) -> dict:
    """Métricas agregadas do rebanho (não por animal) — painel "Resumo do
    período" do Relatório personalizado. Taxas de serviço/concepção/prenhez/
    perda reaproveitam `calcular_indicadores` (mesmo cálculo de Indicadores >
    Gerais); o resto é específico deste relatório."""
    hoje = date.today()
    animais_dump = [a.model_dump() for a in animais_rows]
    servicos_dump = [s.model_dump() for s in servicos_rows]
    partos_dump = [p.model_dump() for p in partos_rows]
    ind = calcular_indicadores(animais_dump, servicos_dump, partos_dump, data_ref=hoje)
    rep = ind.get("reproducao", {})

    vacas_nums = {p.get("numero_matriz") for p in partos_dump if p.get("numero_matriz")}
    novilhas_aptas = sum(
        1 for a in animais_rows
        if a.sexo != "M" and a.ativo and a.numero not in vacas_nums and a.data_nasc
        and (hoje - a.data_nasc).days <= novilhas_aptas_meses * 30
    )

    perdas = [s for s in servicos_rows if s.data_perda_prenhez]
    if data_de or data_ate:
        perdas = [s for s in perdas if (not data_de or s.data_perda_prenhez >= data_de) and (not data_ate or s.data_perda_prenhez <= data_ate)]
    diagnosticados = sum(1 for s in servicos_rows if (s.diagnostico or "").strip())

    partos_filtrados = partos_rows
    if data_de or data_ate:
        partos_filtrados = [p for p in partos_rows if p.data_parto and (not data_de or p.data_parto >= data_de) and (not data_ate or p.data_parto <= data_ate)]
    sexos_crias = [s for p in partos_filtrados for s in (p.sexo_cria_1, p.sexo_cria_2) if s]
    machos = sum(1 for s in sexos_crias if s.strip().upper().startswith("M"))
    femeas = sum(1 for s in sexos_crias if s.strip().upper().startswith("F"))
    total_crias = machos + femeas

    query_sanidade = select(Sanidade).where(Sanidade.curada.is_not(None))
    if fazenda_id is not None:
        query_sanidade = query_sanidade.where(Sanidade.fazenda_id == fazenda_id)
    if data_de:
        query_sanidade = query_sanidade.where(Sanidade.data_aplicacao >= data_de)
    if data_ate:
        query_sanidade = query_sanidade.where(Sanidade.data_aplicacao <= data_ate)
    avaliadas = session.exec(query_sanidade).all()
    curadas = sum(1 for s in avaliadas if s.curada)

    return {
        "quantidade_animais": quantidade_animais,
        "taxa_servico_pct": rep.get("taxa_servico_pct"),
        "taxa_concepcao_pct": rep.get("taxa_concepcao_pct"),
        "taxa_prenhez_pct": rep.get("taxa_prenhez_pct"),
        "novilhas_aptas_ate_meses": novilhas_aptas,
        "novilhas_aptas_meses_criterio": novilhas_aptas_meses,
        "quantidade_perda_prenhez": len(perdas),
        "percentual_perda_prenhez_pct": round(100 * len(perdas) / diagnosticados, 1) if diagnosticados else None,
        "percentual_nascimento_macho_pct": round(100 * machos / total_crias, 1) if total_crias else None,
        "percentual_nascimento_femea_pct": round(100 * femeas / total_crias, 1) if total_crias else None,
        "taxa_cura_pct": round(100 * curadas / len(avaliadas), 1) if avaliadas else None,
    }


@router.get("/")
def obter_indicadores(
    data: date = date.today(),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    """
    Indicadores consolidados do rebanho: composição, situação reprodutiva
    (taxa de prenhez, concepção, IEP, partos previstos) e produção (DEL médio,
    litros/dia). Calculado sobre os dados já carregados via upload.
    """
    query_animais = select(Animal).where(Animal.ativo == True)
    query_servicos = select(Servico)
    query_partos = select(Parto)
    # Piloto conservador de multi-fazenda (ver animais.py:listar_animais): só
    # filtra quando o token carrega uma fazenda selecionada.
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)

    todos = session.exec(query_animais).all()
    animais = [a.model_dump() for a in todos if not a.eh_semen and a.sexo != "M"]  # só fêmeas
    servicos = [s.model_dump() for s in session.exec(query_servicos).all()]
    partos = [p.model_dump() for p in session.exec(query_partos).all()]

    # Peso vivo mais recente por matriz (mesmo padrão de
    # routers/reproducao.py e routers/lotes.py:coletar_dados_criterios) — só
    # usado aqui para a elegibilidade de 1ª cobertura ("aptas").
    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    for p in session.exec(select(PesagemCorporal)).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg

    lotes = [l.model_dump() for l in session.exec(select(Lote)).all()]
    return calcular_indicadores(animais, servicos, partos, data_ref=data, peso_por_animal=peso_por_animal, lotes=lotes)
