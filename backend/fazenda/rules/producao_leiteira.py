"""
Último controle leiteiro por animal — ponto único de "qual foi a produção e a
data do controle mais recente de cada vaca", lido dos ControleLeiteiro de
verdade. Antes, mais de um lugar (Alimentação > Nova dieta, Formulação de
Dietas > contexto do lote) lia só o campo congelado
`Animal.ult_cl_kg`/`Animal.data_ult_leite` — escrito uma única vez pelo
parser do GERAL.csv do Ideagri (aposentado) e nunca mais atualizado por um
controle leiteiro lançado pelo próprio app. Resultado: lançar um controle
novo não refletia nessas telas, que continuavam mostrando a data/produção do
último CSV importado (ver o mesmo bug já corrigido, com este histórico
documentado, em `rules/indicadores.py::calcular_indicadores`).
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from fazenda.models import Animal, ControleLeiteiro


def ultimo_controle_por_animal(
    session: Session, numeros: set[str] | list[str], fazenda_id: int | None = None,
) -> dict[str, tuple[float, date]]:
    """{numero_matriz: (producao_kg, data_controle)} do controle MAIS
    RECENTE de cada animal em `numeros`, considerando só produção > 0. Sem
    fallback para o campo congelado — ver `com_fallback_animal` abaixo."""
    if not numeros:
        return {}
    query = select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz.in_(numeros))
    if fazenda_id is not None:
        query = query.where(ControleLeiteiro.fazenda_id == fazenda_id)
    resultado: dict[str, tuple[float, date]] = {}
    for c in session.exec(query).all():
        if not c.producao_kg or c.producao_kg <= 0 or not c.data_controle:
            continue
        atual = resultado.get(c.numero_matriz)
        if atual is None or c.data_controle >= atual[1]:
            resultado[c.numero_matriz] = (float(c.producao_kg), c.data_controle)
    return resultado


def com_fallback_animal(
    numero: str, ao_vivo: dict[str, tuple[float, date]], animal: Animal,
) -> tuple[float | None, date | None]:
    """(producao_kg, data_controle) para `numero` — do controle leiteiro AO
    VIVO quando existe; senão cai para o campo congelado do animal (só serve
    quem nunca teve um ControleLeiteiro lançado pelo app)."""
    if numero in ao_vivo:
        return ao_vivo[numero]
    return animal.ult_cl_kg, animal.data_ult_leite
