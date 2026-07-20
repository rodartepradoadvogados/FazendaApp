"""Acasalamento direcionado — sugestão de touro por vaca/fêmea a inseminar.
Combina 3 critérios (evitar consanguinidade, complementar características,
só sêmen em estoque) via `fazenda.rules.acasalamento.sugerir_touros`; este
router só resolve os dados do banco (genealogia materna por recursão,
touros com estoque disponível) e delega a regra pura."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, EstoqueSemen, Touro
from fazenda.rules.acasalamento import criterios_explicacao, sugerir_touros

router = APIRouter(prefix="/reproducao/acasalamento", tags=["reproducao"])

# Gerações maternas resolvidas por recursão via `mae_numero` (mãe, avó
# materna, bisavó materna) — além das 3 gerações paternas já prontas no
# cadastro do Animal (pai/avô/bisavô, com nome+NAAB).
PROFUNDIDADE_MATERNA = 3


def _ancestrais_maternos(session: Session, vaca: Animal) -> list[str]:
    """Sobe a linha materna via `Animal.mae_numero` até `PROFUNDIDADE_MATERNA`
    gerações, coletando o NAAB/nome do PAI de cada fêmea ascendente (o touro
    que a gerou) — é isso que precisa ser comparado contra o touro candidato
    para detectar ancestral comum do lado materno. Para de subir se a
    ascendente não estiver cadastrada como Animal, ou se detectar um `numero`
    repetido (dado circular/inconsistente)."""
    ancestrais: list[str] = []
    visitados = {vaca.numero}
    atual = vaca
    for _ in range(PROFUNDIDADE_MATERNA):
        mae_numero = atual.mae_numero
        if not mae_numero or mae_numero in visitados:
            break
        visitados.add(mae_numero)
        mae = session.exec(select(Animal).where(Animal.numero == mae_numero)).first()
        if not mae:
            break
        pai_da_mae = mae.pai_naab or mae.pai_nome
        if pai_da_mae:
            ancestrais.append(pai_da_mae)
        atual = mae
    return ancestrais


def _touros_com_estoque(session: Session) -> list[dict]:
    """Junta `EstoqueSemen` (doses > 0, ou tipo "fazenda") com o catálogo
    `Touro` via NAAB, trazendo as provas quando disponíveis — mesma lógica de
    `GET /cadastro/estoque-semen/disponivel`, mas devolvendo as provas do
    touro (TPI/NM$/produção) em vez de só nome/tipo/doses."""
    estoques = [e for e in session.exec(select(EstoqueSemen)).all() if e.ativo]
    touros_por_naab = {t.naab: t for t in session.exec(select(Touro)).all() if t.naab}

    disponiveis: list[dict] = []
    for e in estoques:
        if not (e.tipo == "fazenda" or (e.doses or 0) > 0):
            continue
        touro = touros_por_naab.get(e.naab) if e.naab else None
        item = touro.model_dump() if touro else {}
        item["naab"] = e.naab or item.get("naab")
        item["nome"] = (touro.nome if touro and touro.nome else None) or e.touro_nome
        item["doses"] = e.doses or 0
        item["tipo"] = e.tipo
        disponiveis.append(item)
    return disponiveis


@router.get("/sugestao")
def sugestao_acasalamento(numero_matriz: str, session: Session = Depends(get_session)) -> dict:
    """Sugestão de touro (acasalamento direcionado) para a vaca `numero_matriz`
    — evita consanguinidade, complementa características e só considera
    touros com sêmen em estoque. Retorna a lista ordenada de sugestões (cada
    uma com `motivo` explicando o porquê) mais a explicação fixa dos 3
    critérios usados."""
    vaca = session.exec(select(Animal).where(Animal.numero == numero_matriz)).first()
    if not vaca:
        raise HTTPException(status_code=404, detail=f"Animal {numero_matriz} não encontrado")

    ancestrais_maternos = _ancestrais_maternos(session, vaca)
    touros = _touros_com_estoque(session)
    sugestoes = sugerir_touros(vaca.model_dump(), touros, ancestrais_maternos=ancestrais_maternos)

    return {
        "numero_matriz": numero_matriz,
        "criterios": criterios_explicacao(),
        "sugestoes": sugestoes,
        "ancestrais_maternos_avaliados": len(ancestrais_maternos) > 0,
    }
