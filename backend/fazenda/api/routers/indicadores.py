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
from fazenda.models import Animal, Lote, Parto, PesagemCorporal, Servico
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
]
CATALOGO_POR_ID = {c["id"]: c for c in CATALOGO_RELATORIO_PERSONALIZADO}
MAX_PARAMETROS = 10
MAX_PARAMETROS_GRAFICO = 5


@router.get("/relatorio-personalizado/catalogo")
def catalogo_relatorio_personalizado() -> list[dict]:
    return CATALOGO_RELATORIO_PERSONALIZADO


class RelatorioPersonalizadoIn(BaseModel):
    parametros: list[str]
    data_de: date | None = None
    data_ate: date | None = None


@router.post("/relatorio-personalizado")
def relatorio_personalizado(dados: RelatorioPersonalizadoIn, session: Session = Depends(get_session)) -> dict:
    parametros = list(dict.fromkeys(dados.parametros))  # remove duplicatas, preserva ordem
    if not parametros:
        raise HTTPException(status_code=400, detail="Selecione ao menos 1 parâmetro.")
    if len(parametros) > MAX_PARAMETROS:
        raise HTTPException(status_code=400, detail=f"Selecione no máximo {MAX_PARAMETROS} parâmetros.")
    invalidos = [p for p in parametros if p not in CATALOGO_POR_ID]
    if invalidos:
        raise HTTPException(status_code=400, detail=f"Parâmetro(s) inválido(s): {', '.join(invalidos)}")

    colunas_data = [p for p in parametros if CATALOGO_POR_ID[p]["tipo"] == "data"]
    animais = session.exec(select(Animal).where(Animal.eh_semen == False)).all()  # noqa: E712

    linhas = []
    for a in animais:
        d = a.model_dump()
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
