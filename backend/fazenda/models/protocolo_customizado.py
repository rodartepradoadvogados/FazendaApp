"""
Protocolos personalizados — motor de protocolos configurável pelo próprio
produtor. Enquanto os protocolos IATF, sanitário e de indução de lactação são
específicos (hormônios, medicamentos, implante), este é GENÉRICO: o usuário
define nome, categoria e uma sequência de "dia + evento + insumo padrão", e a
Agenda passa a gerar as tarefas a partir disso (ver
fazenda/rules/protocolo_customizado.py).

Mesma arquitetura de 4 camadas dos outros três protocolos (catálogo → etapa →
lançamento → aplicação); as aplicações são MATERIALIZADAS no lançamento, para
que editar o catálogo depois não altere cronogramas já lançados — mesma
garantia que ProtocoloInducaoMedicamento já documenta.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class ProtocoloCustomizado(SQLModel, table=True):
    """O molde: nome + categoria da agenda + sequência de etapas."""

    __tablename__ = "protocolo_customizado"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_protocolo_customizado_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    # Categoria do evento na Agenda — define o módulo exigido para ver o
    # evento (ver MODULO_POR_CATEGORIA em api/routers/agenda.py). Validada
    # contra CATEGORIAS_PROTOCOLO_CUSTOM na API: uma categoria fora da
    # whitelist cairia no "nenhum módulo exigido" e vazaria o evento para
    # quem não tem permissão.
    categoria: str = Field(default="Atividades")
    dia_inicial: int = 0  # 0 (D0) ou 1 (D1) — primeiro dia do cronograma
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloCustomizadoEtapa(SQLModel, table=True):
    """Uma linha do molde: num dia do protocolo, um evento a executar e o
    insumo padrão sugerido (texto livre — não baixa estoque automaticamente;
    quem precisa de baixa com rastreio usa o Protocolo sanitário). Vários
    itens podem coexistir no mesmo dia (ordem)."""

    __tablename__ = "protocolo_customizado_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_customizado.id", index=True)
    dia: int  # bruto; o rótulo exibido é dia - dia_inicial
    descricao_evento: str  # ex.: "Aplicar vacina antirrábica"
    insumo_padrao: Optional[str] = None
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None
    observacao: Optional[str] = None  # nota livre para quem executa
    ordem: int = 0  # ordenação dentro do mesmo dia
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloCustomizadoLancamento(SQLModel, table=True):
    """Aplicação do molde a um grupo de animais (ou à fazenda, sem animal
    específico) numa data — o cabeçalho. Congela nome/categoria/dia_inicial
    do molde: editar o catálogo depois não altera lançamentos já feitos."""

    __tablename__ = "protocolo_customizado_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_customizado.id", index=True)
    nome_protocolo: str  # snapshot do nome
    categoria: str  # snapshot da categoria
    dia_inicial: int = 0  # snapshot — evita join só para calcular o rótulo D{n}
    data_inicio: date = Field(index=True)  # data do dia_inicial
    lote: Optional[str] = None  # rótulo informativo, quando lançado a partir de um lote
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    ativo: bool = Field(default=True, index=True)  # cancelar = False (histórico preservado)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloCustomizadoAplicacao(SQLModel, table=True):
    """Uma etapa (dia) de um animal dentro de um lançamento — vira evento na
    Agenda, confirmável ali (ver fazenda/rules/protocolo_customizado.py).
    `numero_matriz` nulo = tarefa da fazenda, sem animal específico (ex.:
    calendário de vacina do rebanho)."""

    __tablename__ = "protocolo_customizado_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_customizado_lancamento.id", index=True)
    numero_matriz: Optional[str] = Field(default=None, index=True)
    dia: int  # bruto (mesmo do molde)
    descricao: str  # texto congelado dos eventos do dia
    insumo: Optional[str] = None  # texto congelado dos insumos do dia
    observacao: Optional[str] = None  # notas congeladas do dia
    data_prevista: date = Field(index=True)
    realizada: bool = Field(default=False, index=True)
    data_realizacao: Optional[date] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
