"""
Lida — tarefas gerais da fazenda que não são protocolo de animal (limpar
cocho, acompanhar obra, manutenção...). Diferente do Protocolo Customizado
(que pede Tipo produtivo/reprodutivo/sanitário porque nasceu para rotina de
animal), a Lida nunca pede Tipo — é sempre "trabalho da fazenda".

Duas formas de agendar (`Lida.modo`):
  - "periodo": uma ou mais etapas em dias fixos (D0, D1...), cada uma podendo
    se repetir todo dia num intervalo (LidaEtapa.dia_fim) — ex.: "enviar foto
    da cerca, D0 a D30".
  - "frequencia": uma única tarefa que se repete a cada N dias entre um
    início e um fim — ex.: "limpar o cocho, a cada 15 dias, de 01/08 a
    01/10". Os campos da tarefa ficam direto no molde (Lida), sem LidaEtapa.

Mesma arquitetura de 4 camadas dos demais protocolos (catálogo → etapa →
lançamento → aplicação) — ver fazenda/models/protocolo_customizado.py.
`LidaAplicacao.numero_matriz` nulo = tarefa da fazenda, sem animal específico
(mesmo padrão de ProtocoloCustomizadoAplicacao).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class Lida(SQLModel, table=True):
    """O molde: nome + modo de agendamento + (para "frequencia") a própria
    tarefa; para "periodo" as tarefas ficam em LidaEtapa."""

    __tablename__ = "lida"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_lida_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    modo: str = Field(default="periodo")  # "periodo" | "frequencia"
    dia_inicial: int = 0  # modo "periodo" — 0 (D0) ou 1 (D1)

    # Campos usados só quando modo == "frequencia" — uma única tarefa que se
    # repete; sem etapas, para não obrigar a cadastrar uma grade pra uma
    # coisa que é sempre a mesma linha repetida.
    frequencia_dias: Optional[int] = None
    descricao_evento: Optional[str] = None
    insumo_padrao: Optional[str] = None
    # Quantidade consumida A CADA confirmação — só faz sentido junto de
    # dar_baixa_estoque=True (sem baixa, insumo_padrao já é informativo por
    # si só, como no Protocolo Customizado).
    insumo_dose: Optional[float] = None
    insumo_unidade: Optional[str] = None
    foto_obrigatoria: bool = False

    # Comportamento na confirmação (Agenda/Central) — vale para as duas
    # formas de agendar.
    dar_baixa_estoque: bool = False
    # Guardado para a tela mostrar a intenção — a geração automática do
    # lançamento financeiro ainda não está implementada (ver TODO no router).
    vincular_financeiro: bool = False

    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class LidaEtapa(SQLModel, table=True):
    """Uma linha do molde no modo "periodo": um evento num dia (ou faixa de
    dias, quando `dia_fim` é preenchido — a mesma tarefa repete todo dia até
    lá, ex.: D0 a D30 pedindo foto todo dia)."""

    __tablename__ = "lida_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    lida_id: int = Field(foreign_key="lida.id", index=True)
    dia_inicio: int
    dia_fim: Optional[int] = None  # None = etapa de um dia só (== dia_inicio)
    descricao_evento: str
    insumo_padrao: Optional[str] = None
    insumo_dose: Optional[float] = None
    insumo_unidade: Optional[str] = None
    foto_obrigatoria: bool = False
    ordem: int = 0
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class LidaLancamento(SQLModel, table=True):
    """Aplicação do molde contra um alvo (tarefa da fazenda, lote ou
    animal(is)) numa data — o cabeçalho. Congela nome/modo do molde."""

    __tablename__ = "lida_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    lida_id: int = Field(foreign_key="lida.id", index=True)
    nome_protocolo: str  # snapshot do nome (+ intervalo de datas, ver gerar_nome_lancamento)
    modo: str  # snapshot
    dia_inicial: int = 0  # snapshot — mesmo motivo de ProtocoloCustomizadoLancamento
    data_inicio: date = Field(index=True)
    # "tarefa_fazenda" | "lote" | "animal" — só informativo (a lista real de
    # animais, quando houver, está nas LidaAplicacao.numero_matriz).
    alvo_tipo: str = "tarefa_fazenda"
    lote: Optional[str] = None  # rótulo informativo, quando alvo_tipo == "lote"
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    ativo: bool = Field(default=True, index=True)  # cancelar = False
    encerrado_em: Optional[date] = Field(default=None)
    encerrado_motivo: Optional[str] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class LidaAplicacao(SQLModel, table=True):
    """Uma ocorrência (dia) dentro de um lançamento — vira evento na Agenda,
    confirmável ali ou pela Central de Protocolos. `foto_url` é o caminho no
    Supabase Storage da evidência anexada (quando a etapa exige foto)."""

    __tablename__ = "lida_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="lida_lancamento.id", index=True)
    numero_matriz: Optional[str] = Field(default=None, index=True)  # None = tarefa da fazenda
    dia: int  # bruto (mesmo do molde, relativo a data_inicio via dia_inicial)
    descricao: str  # texto congelado do evento
    insumo: Optional[str] = None  # texto congelado do insumo
    insumo_dose: Optional[float] = None
    insumo_unidade: Optional[str] = None
    foto_obrigatoria: bool = False
    foto_url: Optional[str] = None  # caminho no Supabase Storage, preenchido ao anexar
    data_prevista: date = Field(index=True)
    realizada: bool = Field(default=False, index=True)
    data_realizacao: Optional[date] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
