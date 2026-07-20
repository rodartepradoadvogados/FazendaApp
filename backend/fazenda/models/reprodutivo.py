"""
Reprodução — serviços (IA/IATF/cobertura), protocolos IATF, partos e colostragem.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Serviço (IA / IATF / Cobertura)
# ---------------------------------------------------------------------------
class Servico(SQLModel, table=True):
    """Uma linha da tabela REPRODUTIVO — um serviço por linha."""

    __tablename__ = "servico"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    raca_matriz: Optional[str] = None
    data_nasc_matriz: Optional[date] = None
    data_ult_parto: Optional[date] = None
    ordem_parto: Optional[int] = None
    data_servico: Optional[date] = None
    tipo_servico: Optional[str] = None
    protocolo: Optional[str] = None
    reprodutor: Optional[str] = None
    # Sêmen sexado x convencional (ou monta natural, tipo "fazenda") — gravado no
    # momento da inseminação para o histórico não depender de recasar o nome do
    # touro com o Estoque de Sêmen depois (que pode mudar de tipo com o tempo).
    tipo_semen: Optional[str] = None  # convencional | sexado | fazenda
    inseminador: Optional[str] = None  # quem fez a IA/cobertura (responsável)
    ordem_tentativa: Optional[int] = None
    intervalo_tentativas: Optional[int] = None
    data_diagnostico: Optional[date] = None
    diagnostico: Optional[str] = None  # POSITIVO | NEGATIVO | INDEFINIDO
    metodo_diagnostico: Optional[str] = None  # Palpação | Ultrassom | Cio de repasse
    data_perda_prenhez: Optional[date] = None
    motivo_perda_prenhez: Optional[str] = None  # aborto | natimorto | outros
    pev_dias: Optional[int] = None
    del_servico: Optional[int] = None
    ult_ocorrencia: Optional[int] = None
    categoria: Optional[str] = None
    producao_lactacao_anterior: Optional[float] = None
    duracao_lactacao_anterior: Optional[int] = None
    periodo_seco_anterior: Optional[int] = None
    # Diagnóstico positivo marcado para reconfirmar (ainda não é prenhez definitiva)
    # — gera o lembrete de retoque na agenda, na data do próximo serviço.
    retoque: Optional[bool] = None
    # Segundo exame (reconfirmação, ~60 dias do serviço) — distinto do primeiro
    # toque (data_diagnostico/diagnostico) para a agenda do veterinário.
    data_reconfirmacao: Optional[date] = None
    diagnostico_reconfirmacao: Optional[str] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Tipo de serviço / Método reprodutivo — cadastro (Configurações > Cadastro)
# do vocabulário usado no lançamento de Serviço/Inseminação. Um Método sempre
# pertence a um Tipo de serviço (ex.: "Monta Natural" → Cobertura; "IA em cio
# natural" e "IATF" → IA). `codigo_interno` identifica os 3 métodos que o
# motor de lançamento/análise reprodutiva já sabe tratar de forma especial
# (nenhum novo método customizado tem código — fica só informativo/rótulo).
# ---------------------------------------------------------------------------
class TipoServicoReprodutivo(SQLModel, table=True):
    """Tipo de serviço reprodutivo cadastrado (ex.: Cobertura, IA)."""

    __tablename__ = "tipo_servico_reprodutivo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MetodoServicoReprodutivo(SQLModel, table=True):
    """Método de um tipo de serviço (ex.: Monta Natural, IA em cio natural, IATF)."""

    __tablename__ = "metodo_servico_reprodutivo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    tipo_servico_id: int = Field(foreign_key="tipo_servico_reprodutivo.id")
    codigo_interno: Optional[str] = None  # "monta_natural" | "cio_natural" | "iatf" | None (customizado)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Protocolo IATF — lançamento do protocolo hormonal (D0/D7/D9/D11) em um ou
# vários animais de uma vez. Cada etapa de cada animal vira uma "aplicação"
# rastreável (aparece agrupada na Agenda, marcada como realizada individualmente).
# A inseminação em si (D11) continua sendo lançada à parte em Servico — ver
# fazenda.api.routers.reproducao.registrar_servico, que resolve a aplicação
# de D11 correspondente automaticamente quando o protocolo é informado.
# ---------------------------------------------------------------------------
class ProtocoloIatfLancamento(SQLModel, table=True):
    """Um lançamento de protocolo IATF em lote — o "cabeçalho" (nome + data do D0)."""

    __tablename__ = "protocolo_iatf_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome_protocolo: str
    data_d0: date
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    # Lançado retroativamente (D0 no passado, a partir de uma inseminação IATF
    # sem protocolo). As etapas vencidas destes aparecem como PENDÊNCIA na
    # agenda; nos protocolos normais, etapas já passadas ficam escondidas.
    retroativo: bool = Field(default=False)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class ProtocoloIatfAplicacao(SQLModel, table=True):
    """Uma etapa (D0/D7/D9/D11) de um animal dentro de um lançamento de protocolo IATF."""

    __tablename__ = "protocolo_iatf_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_iatf_lancamento.id")
    numero_matriz: str = Field(index=True)
    dia: int  # 0, 7, 9 ou 11
    descricao: str  # hormônio/ação do dia (D11 = "Inseminação (IATF)")
    data_prevista: date
    realizada: bool = False
    data_realizacao: Optional[date] = None


class ProtocoloIatfHormonio(SQLModel, table=True):
    """
    Medicamento(s) aplicado(s) num dia do protocolo IATF (ex.: D0 = 1ml SincroCP
    + 2ml Estron). Definido uma vez por lançamento/dia e aplicado a todas as
    vacas daquele passo. Ao confirmar o dia, dá baixa de estoque e registra a
    aplicação em Sanidade para cada vaca.
    """

    __tablename__ = "protocolo_iatf_hormonio"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_iatf_lancamento.id", index=True)
    dia: int
    produto: str
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None


# ---------------------------------------------------------------------------
# Parto
# ---------------------------------------------------------------------------
class Parto(SQLModel, table=True):
    """Registro de parto extraído do campo REPRODUTIVO."""

    __tablename__ = "parto"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    data_parto: Optional[date] = None
    ordem_parto: Optional[int] = None
    tipo_parto: Optional[str] = None
    sexo_cria_1: Optional[str] = None
    sexo_cria_2: Optional[str] = None
    # Números das crias nascidas (para abrir a ficha da cria a partir do parto).
    numero_cria_1: Optional[str] = None
    numero_cria_2: Optional[str] = None
    gemelar: Optional[bool] = None
    # Combinação de sexos de um parto gemelar: "FF" | "FM" | "MM". Em FM, a fêmea
    # costuma ser freemartin (infértil) — informação útil no descarte precoce.
    gemelar_sexo: Optional[str] = None
    retencao_placenta: Optional[bool] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Colostragem e teste de sangue (IgG) da cria — histórico sanitário usado no
# relatório de bezerras (Sanidade). Uma linha por animal, atualizável conforme
# os dados vão sendo colhidos (colostro no nascimento, teste de sangue 24-48h
# depois).
# ---------------------------------------------------------------------------
class ColostragemBezerra(SQLModel, table=True):
    """Registro de colostragem e teste de sangue (IgG) de uma cria."""

    __tablename__ = "colostragem_bezerra"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_animal: str = Field(index=True, unique=True)
    tomou_colostro: Optional[bool] = None
    litros_colostro: Optional[float] = None
    brix_colostro: Optional[float] = None  # Ouro >25% · Prata 18-25% · Bronze <18%
    data_colostro: Optional[date] = None
    hora_parto: Optional[str] = None       # "HH:MM" — hora do parto
    hora_colostro: Optional[str] = None    # "HH:MM" — hora do 1º oferecimento de colostro
    peso_nascer_kg: Optional[float] = None # peso do animal ao nascer
    brix_soro: Optional[float] = None  # teste de sangue: Brix sérico (refratômetro)
    proteina_serica: Optional[float] = None  # teste de sangue: proteína sérica total (g/dL)
    # True = bezerra que recebeu somente colostro em pó (sem colostro materno);
    # entra em grupo próprio no relatório de eficiência de colostragem.
    apenas_colostro_po: Optional[bool] = None
    data_teste_sangue: Optional[date] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
