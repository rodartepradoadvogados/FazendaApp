"""
Reprodução — serviços (IA/IATF/cobertura), protocolos IATF, partos e colostragem.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

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
    # Vínculo (soft-join pelo número) com o lançamento financeiro em
    # ContaGerencial que paga a visita reprodutiva (diagnóstico de gestação) —
    # ver popup de vínculo sanitário/reprodutivo, disparado ao salvar o
    # diagnóstico (data_diagnostico == data_servico == D0 do protocolo IATF).
    numero_lancamento_vinculado: Optional[str] = Field(default=None, index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    # nome era único globalmente — passa a ser único por fazenda (mesmo
    # padrão de CentroCusto/PrincipioAtivo), senão a 2ª fazenda nunca
    # conseguiria cadastrar um tipo de serviço com o mesmo nome já usado.
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_tipo_servico_reprodutivo_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class MetodoServicoReprodutivo(SQLModel, table=True):
    """Método de um tipo de serviço (ex.: Monta Natural, IA em cio natural, IATF)."""

    __tablename__ = "metodo_servico_reprodutivo"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_metodo_servico_reprodutivo_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    tipo_servico_id: int = Field(foreign_key="tipo_servico_reprodutivo.id")
    codigo_interno: Optional[str] = None  # "monta_natural" | "cio_natural" | "iatf" | None (customizado)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Protocolo IATF cadastrado (o "molde" do cronograma hormonal — mesmo padrão
# do protocolo de indução de lactação e do protocolo sanitário: catálogo
# editável em Configurações/Central de Protocolos → lançamento aplica o
# catálogo a um grupo de animais → aplicação por animal/dia). Os dias em si
# (D0/D7/D9/D11) continuam fixos (ver PASSOS_PROTOCOLO_IATF) — o molde só
# define QUAL hormônio/dose/via é usado em D0/D7/D9 (D11 é sempre a
# inseminação, sem hormônio). Lançar sem escolher um molde continua possível
# — os hormônios são digitados na hora, como sempre foi.
# ---------------------------------------------------------------------------
class ProtocoloIatf(SQLModel, table=True):
    """Um protocolo IATF cadastrado (o "molde" dos hormônios de D0/D7/D9)."""

    __tablename__ = "protocolo_iatf"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_protocolo_iatf_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloIatfEtapa(SQLModel, table=True):
    """
    Um hormônio do molde num dia (0, 7 ou 9 — D11 nunca entra aqui, é sempre
    inseminação). `criterio_tipo` segue o mesmo seletor de insumo usado no
    protocolo sanitário: por medicamento específico, por princípio ativo
    (lista fechada dos itens de estoque daquele princípio) ou por
    classificação/doença.
    """

    __tablename__ = "protocolo_iatf_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_iatf.id", index=True)
    dia: int  # 0, 7 ou 9
    criterio_tipo: str = Field(default="medicamento")  # "medicamento" | "principio_ativo" | "classificacao"
    principio_ativo_id: Optional[int] = Field(default=None, foreign_key="principio_ativo.id")
    produto: str  # medicamento OU o valor do critério (princípio ativo / classificação)
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    # Molde (ProtocoloIatf) usado para pré-preencher os hormônios, se algum
    # foi escolhido no lançamento — None quando lançado ad-hoc (hormônios
    # digitados na hora, como sempre foi possível).
    protocolo_id: Optional[int] = Field(default=None, foreign_key="protocolo_iatf.id")
    # Lançado retroativamente (D0 no passado, a partir de uma inseminação IATF
    # sem protocolo). As etapas vencidas destes aparecem como PENDÊNCIA na
    # agenda; nos protocolos normais, etapas já passadas ficam escondidas.
    retroativo: bool = Field(default=False)
    # Encerrado manualmente pela Central de Protocolos: o lote acabou antes do
    # fim do cronograma. As etapas que sobraram continuam gravadas como NÃO
    # realizadas — encerrar não é o mesmo que dar por feito o que não foi —,
    # mas param de cobrar pendência na Agenda.
    encerrado_em: Optional[date] = Field(default=None)
    encerrado_motivo: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Colostragem e teste de sangue (IgG) da cria — histórico sanitário usado no
# relatório de bezerras (Sanidade). Uma linha por animal, atualizável conforme
# os dados vão sendo colhidos (colostro no nascimento, teste de sangue 24-48h
# depois).
# ---------------------------------------------------------------------------
class ColostragemBezerra(SQLModel, table=True):
    """Registro de colostragem e teste de sangue (IgG) de uma cria."""

    __tablename__ = "colostragem_bezerra"
    # numero_animal era único globalmente (uq antigo, dropado na migração de
    # fazenda_id) — passa a ser único por fazenda, senão a 2ª fazenda nunca
    # conseguiria cadastrar colostragem de uma cria com o mesmo número da 1ª.
    __table_args__ = (UniqueConstraint("numero_animal", "fazenda_id", name="uq_colostragem_bezerra_numero_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_animal: str = Field(index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
