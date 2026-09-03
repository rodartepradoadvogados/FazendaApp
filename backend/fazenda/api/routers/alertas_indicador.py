"""
Router de Alertas de indicador — o usuário escolhe um indicador (dos já
mostrados em Indicadores), um operador e um valor-limite. Quando a condição
é atendida, aparece na central de notificações — ver o bloco correspondente
em fazenda/api/routers/notificacoes.py::montar_itens_notificacoes, que é
quem efetivamente dispara o alerta (este router só é o CRUD de configuração).

Catálogo de indicadores fixo no código (mudam raramente, dependem de campos
específicos de fazenda/rules/indicadores.py::calcular_indicadores) — mesmo
padrão de PASSOS_ONBOARDING/TIPOS_ASSUNTO em outros routers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.indicadores import calcular_indicadores_fazenda
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import AlertaIndicador, Usuario

router = APIRouter(prefix="/alertas-indicador", tags=["alertas-indicador"])

INDICADORES_CATALOGO = [
    # Rótulo "Fêmeas prenhas", não "Taxa de prenhez": este campo é inventário
    # (% do rebanho apto prenhe hoje), não a taxa formal do programa
    # reprodutivo (PREG ÷ PG ELIG) de /reproducao/ciclos-21-dias — mesmo nome
    # que passaria a colidir com este aqui. Mesmo rótulo usado na Capa.
    {"chave": "taxa_prenhez_pct", "label": "Fêmeas prenhas (%)", "caminho": ("reproducao", "taxa_prenhez_pct")},
    {"chave": "perc_vazias_pct", "label": "Percentual de vazias (%)", "caminho": ("reproducao", "perc_vazias_pct")},
    {"chave": "taxa_concepcao_pct", "label": "Taxa de concepção (%)", "caminho": ("reproducao", "taxa_concepcao_pct")},
    {"chave": "producao_media_kg", "label": "Produção média por vaca (kg/dia)", "caminho": ("producao", "producao_media_kg")},
    {"chave": "del_medio", "label": "DEL médio (dias)", "caminho": ("producao", "del_medio")},
    {"chave": "vacas_lactacao", "label": "Vacas em lactação (nº)", "caminho": ("rebanho", "vacas_lactacao")},
]
CATALOGO_POR_CHAVE = {c["chave"]: c for c in INDICADORES_CATALOGO}

OPERADORES_VALIDOS = {"<", "<=", ">", ">="}
OPERADOR_LABEL = {"<": "abaixo de", "<=": "no máximo", ">": "acima de", ">=": "no mínimo"}


def valor_indicador(resultado: dict, indicador_chave: str) -> float | None:
    """Busca o valor de um indicador no dict devolvido por
    calcular_indicadores_fazenda(), pelo caminho fixo em INDICADORES_CATALOGO."""
    catalogo = CATALOGO_POR_CHAVE.get(indicador_chave)
    if not catalogo:
        return None
    valor = resultado
    for parte in catalogo["caminho"]:
        if not isinstance(valor, dict):
            return None
        valor = valor.get(parte)
    return valor if isinstance(valor, (int, float)) else None


def condicao_atendida(valor: float, operador: str, limite: float) -> bool:
    if operador == "<":
        return valor < limite
    if operador == "<=":
        return valor <= limite
    if operador == ">":
        return valor > limite
    if operador == ">=":
        return valor >= limite
    return False


def descricao_alerta(alerta: AlertaIndicador, valor: float) -> str:
    label = CATALOGO_POR_CHAVE[alerta.indicador_chave]["label"]
    return f"{label} está em {round(valor, 1)} — alerta configurado para {OPERADOR_LABEL[alerta.operador]} {alerta.valor_limite}"


@router.get("/catalogo")
def listar_catalogo() -> list[dict]:
    return [{"chave": c["chave"], "label": c["label"]} for c in INDICADORES_CATALOGO]


def _serializar(alerta: AlertaIndicador, resultado: dict) -> dict:
    valor = valor_indicador(resultado, alerta.indicador_chave)
    return {
        "id": alerta.id,
        "indicador_chave": alerta.indicador_chave,
        "indicador_label": CATALOGO_POR_CHAVE.get(alerta.indicador_chave, {}).get("label", alerta.indicador_chave),
        "operador": alerta.operador,
        "valor_limite": alerta.valor_limite,
        "ativo": alerta.ativo,
        "valor_atual": valor,
        "disparado": valor is not None and condicao_atendida(valor, alerta.operador, alerta.valor_limite),
        "criado_em": alerta.criado_em.isoformat(),
    }


@router.get("")
def listar_alertas(
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    alertas = session.exec(select(AlertaIndicador).where(AlertaIndicador.usuario_id == user.id)).all()
    # Um cálculo de indicadores por fazenda distinta entre os alertas do
    # usuário (na prática, quase sempre uma só) — evita recalcular à toa.
    cache: dict[int | None, dict] = {}
    saida = []
    for a in alertas:
        if a.fazenda_id not in cache:
            cache[a.fazenda_id] = calcular_indicadores_fazenda(session, a.fazenda_id)
        saida.append(_serializar(a, cache[a.fazenda_id]))
    return saida


class AlertaIndicadorIn(BaseModel):
    indicador_chave: str
    operador: str
    valor_limite: float


@router.post("", status_code=201)
def criar_alerta(
    dados: AlertaIndicadorIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.indicador_chave not in CATALOGO_POR_CHAVE:
        raise HTTPException(400, f"Indicador inválido: {dados.indicador_chave}")
    if dados.operador not in OPERADORES_VALIDOS:
        raise HTTPException(400, f"Operador inválido: {dados.operador}")

    alerta = AlertaIndicador(
        usuario_id=user.id,
        fazenda_id=fazenda_id,
        indicador_chave=dados.indicador_chave,
        operador=dados.operador,
        valor_limite=dados.valor_limite,
    )
    session.add(alerta)
    session.commit()
    session.refresh(alerta)
    resultado = calcular_indicadores_fazenda(session, alerta.fazenda_id)
    return _serializar(alerta, resultado)


class AlertaIndicadorEdicaoIn(BaseModel):
    operador: str | None = None
    valor_limite: float | None = None
    ativo: bool | None = None


@router.put("/{alerta_id}")
def editar_alerta(
    alerta_id: int, dados: AlertaIndicadorEdicaoIn,
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
) -> dict:
    alerta = session.get(AlertaIndicador, alerta_id)
    if not alerta or alerta.usuario_id != user.id:
        raise HTTPException(404, "Alerta não encontrado")
    if dados.operador is not None:
        if dados.operador not in OPERADORES_VALIDOS:
            raise HTTPException(400, f"Operador inválido: {dados.operador}")
        alerta.operador = dados.operador
    if dados.valor_limite is not None:
        alerta.valor_limite = dados.valor_limite
    if dados.ativo is not None:
        alerta.ativo = dados.ativo
    session.add(alerta)
    session.commit()
    session.refresh(alerta)
    resultado = calcular_indicadores_fazenda(session, alerta.fazenda_id)
    return _serializar(alerta, resultado)


@router.delete("/{alerta_id}")
def excluir_alerta(
    alerta_id: int, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
) -> dict:
    alerta = session.get(AlertaIndicador, alerta_id)
    if not alerta or alerta.usuario_id != user.id:
        raise HTTPException(404, "Alerta não encontrado")
    session.delete(alerta)
    session.commit()
    return {"excluido": True}
