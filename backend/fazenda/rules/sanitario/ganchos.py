"""
Ganchos: toda escrita que muda a vida do animal avisa o sanitário NA HORA
(entra/sai das caixas), dentro da transação de quem escreveu, antes do commit.

Pontos plugados (o teste de contrato tests/test_sanitario_ganchos.py
percorre esta lista nos fontes):
  reproducao.py (parto, diagnóstico, serviço, serviço em lote, perda de
  prenhez), producao.py (secagem), baixas.py (baixa),
  venda_animal.py, compra_animal.py, cadastro/animais.py (criar, editar,
  renumerar). Mudança de categoria por idade é absorvida pelo job diário.

Falha aqui NUNCA derruba a escrita de quem chamou: o erro vai para o log e o
job diário corrige na próxima volta.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

from sqlmodel import Session, select

logger = logging.getLogger(__name__)

PONTOS_PLUGADOS = {
    "fazenda/api/routers/reproducao.py": ("parto", "diagnostico", "servico", "servico_lote", "perda_prenhez"),
    "fazenda/api/routers/producao.py": ("secagem",),
    "fazenda/api/routers/baixas.py": ("baixa",),
    "fazenda/api/routers/venda_animal.py": ("venda",),
    "fazenda/api/routers/compra_animal.py": ("compra",),
    "fazenda/api/routers/cadastro/animais.py": ("cadastro", "edicao", "renumeracao"),
}


def _tem_caixa_ativa(session: Session, fazenda_id: int) -> bool:
    from fazenda.models import SanitarioCaixa

    return session.exec(select(SanitarioCaixa.id).where(
        SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.estado == "ativa",
    ).limit(1)).first() is not None


def _ids_por_numero(session: Session, fazenda_id: int, numeros: Iterable[str]) -> set[int]:
    from fazenda.models import Animal

    nums = {str(n) for n in numeros if n}
    if not nums:
        return set()
    return set(session.exec(select(Animal.id).where(Animal.fazenda_id == fazenda_id, Animal.numero.in_(nums))).all())


def animal_mudou(
    session: Session, fazenda_id: Optional[int], *, animal_ids: Optional[Iterable[int]] = None,
    numeros: Optional[Iterable[str]] = None, evento: str = "", hoje: Optional[date] = None,
) -> dict:
    """Recalcula a situação dos animais afetados e avisa quando um animal
    marcado para um dia deixou de cumprir a regra. Não dá commit."""
    if not fazenda_id:
        return {}
    try:
        ids = {int(i) for i in (animal_ids or ()) if i}
        if numeros:
            ids |= _ids_por_numero(session, fazenda_id, numeros)
        if not ids or not _tem_caixa_ativa(session, fazenda_id):
            return {}
        from fazenda.rules.sanitario.job import verificar_dias_abertos
        from fazenda.rules.sanitario.motor import recalcular

        def _rodar() -> dict:
            cont = recalcular(session, fazenda_id, animal_ids=ids, motivo=evento, hoje=hoje)
            cont["saiu_janela"] = verificar_dias_abertos(session, fazenda_id, animal_ids=ids, hoje=hoje)
            return cont

        if session.get_bind().dialect.name == "postgresql":
            with session.begin_nested():
                return _rodar()
        return _rodar()
    except Exception:
        logger.exception("sanitario.animal_mudou falhou (fazenda=%s, evento=%s) — o job diário corrige", fazenda_id, evento)
        return {"erro": True}
