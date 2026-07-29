"""
Alerta de indicador por limite — o usuário escolhe um indicador (dos já
mostrados em Indicadores), um operador e um valor-limite; quando a condição
é atendida, um item aparece na central de notificações (e, por consequência,
dispara push) — ver fazenda/api/routers/alertas_indicador.py e o bloco
correspondente em fazenda/api/routers/notificacoes.py.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AlertaIndicador(SQLModel, table=True):
    """`indicador_chave` referencia INDICADORES_CATALOGO (fixo no código, ver
    fazenda/api/routers/alertas_indicador.py). `operador` é um de
    "&gt;"/"&gt;="/"&lt;"/"&lt;=" — a condição de disparo é `valor_atual {operador}
    valor_limite`. `fazenda_id` é gravado na criação (fazenda selecionada
    naquele momento) e usado para calcular o indicador daquela fazenda
    especificamente, mesmo que o usuário troque de fazenda depois."""

    __tablename__ = "alerta_indicador"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    indicador_chave: str
    operador: str
    valor_limite: float
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
