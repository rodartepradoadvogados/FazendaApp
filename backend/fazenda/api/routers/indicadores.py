"""
Router de indicadores — painel zootécnico/reprodutivo/produtivo do rebanho.
Endpoint: GET /indicadores/
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Parto, PesagemCorporal, Servico
from fazenda.rules.indicadores import calcular_indicadores

router = APIRouter(prefix="/indicadores", tags=["indicadores"])


@router.get("/")
def obter_indicadores(
    data: date = date.today(),
    session: Session = Depends(get_session),
) -> dict:
    """
    Indicadores consolidados do rebanho: composição, situação reprodutiva
    (taxa de prenhez, concepção, IEP, partos previstos) e produção (DEL médio,
    litros/dia). Calculado sobre os dados já carregados via upload.
    """
    todos = session.exec(select(Animal).where(Animal.ativo == True)).all()
    animais = [a.model_dump() for a in todos if not a.eh_semen and a.sexo != "M"]  # só fêmeas
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    partos = [p.model_dump() for p in session.exec(select(Parto)).all()]

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

    return calcular_indicadores(animais, servicos, partos, data_ref=data, peso_por_animal=peso_por_animal)
