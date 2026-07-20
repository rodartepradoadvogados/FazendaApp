"""
Módulo Recria — Dossiê de Desempenho Zootécnico (ocorrências clínicas, metas, curva de peso, fases e benchmarking).

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# ===========================================================================
# MÓDULO RECRIA — Dossiê de Desempenho Zootécnico
# Novas tabelas que sustentam o acompanhamento de bezerras/novilhas:
# ocorrências clínicas (fonte das curvas doença×idade), metas, curva de
# peso-alvo por idade, fases de idade (coorte) e janelas de ponto crítico.
# ===========================================================================
class OcorrenciaClinica(SQLModel, table=True):
    """Caso clínico de doença num animal, numa data. É a matéria-prima das
    curvas 'casos por idade' e da incidência por fase do Dossiê de Recria."""

    __tablename__ = "ocorrencia_clinica"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    doenca: str = Field(index=True)          # nome da doença (ex.: Diarreia, Pneumonia, TPB)
    data_ocorrencia: date = Field(index=True)
    observacao: Optional[str] = None
    origem: str = "manual"                    # "manual" | "importacao" | "sanidade"
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class MetaRecria(SQLModel, table=True):
    """Metas gerenciais da recria (linha única, id=1). Espelha a aba
    PARÂMETROS da planilha do consultor."""

    __tablename__ = "meta_recria"

    id: Optional[int] = Field(default=None, primary_key=True)
    idade_parto_meses: float = 24.0
    idade_prenhez_meses: float = 14.5
    idade_1a_cobertura_meses: float = 13.5
    taxa_prenhez_meta: float = 42.5
    desvio_padrao_meta: float = 1.7
    custo_diario_recria: float = 12.0
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class PesoAlvoIdade(SQLModel, table=True):
    """Curva de peso-alvo: faixa mín/máx de peso (kg) esperada por mês de vida."""

    __tablename__ = "peso_alvo_idade"

    id: Optional[int] = Field(default=None, primary_key=True)
    mes: int = Field(index=True, unique=True)   # idade em meses (1..24)
    peso_min_kg: float
    peso_max_kg: float
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FaseRecria(SQLModel, table=True):
    """Faixa de idade (em dias) usada para agrupar casos/incidência. Editável
    pelo consultor. Ex.: '30–60 dias'."""

    __tablename__ = "fase_recria"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    dia_min: int = Field(index=True)
    dia_max: int
    ordem: int = 0
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class JanelaPontoCritico(SQLModel, table=True):
    """Janela crítica de uma doença: faixa de idade (dias) de maior incidência
    e a antecedência (dias) com que o alerta preventivo entra na Agenda."""

    __tablename__ = "janela_ponto_critico"

    id: Optional[int] = Field(default=None, primary_key=True)
    doenca: str = Field(index=True)
    dia_min: int
    dia_max: int
    dias_antecedencia: int = 3
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class BenchmarkRecria(SQLModel, table=True):
    """Referência externa de benchmarking (ex.: Alta CRIA): percentis do setor
    (TOP 5/10/25/50/75%) por indicador, e o valor atual da fazenda."""

    __tablename__ = "benchmark_recria"

    id: Optional[int] = Field(default=None, primary_key=True)
    indicador: str = Field(index=True)
    unidade: Optional[str] = None            # "%", "g/dia", etc.
    melhor_e_maior: bool = True              # True: quanto MAIOR melhor (GMD); False: quanto menor (mortalidade)
    top5: Optional[float] = None
    top10: Optional[float] = None
    top25: Optional[float] = None
    top50: Optional[float] = None
    top75: Optional[float] = None
    valor_fazenda: Optional[float] = None
    ordem: int = 0
    fonte: str = "Alta CRIA 2026"
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class RegistroCocho(SQLModel, table=True):
    """Gestão de cocho: leitura diária por lote — quanto foi ofertado, quanto
    sobrou e quantos animais comeram. Fecha o consumo e a IMS (ingestão de
    matéria seca) para o Dossiê de Recria."""

    __tablename__ = "registro_cocho"

    id: Optional[int] = Field(default=None, primary_key=True)
    data: date = Field(index=True)
    lote: str = Field(index=True)
    num_animais: int = 1
    kg_ofertado: float = 0.0
    kg_sobra: float = 0.0
    kg_formulado: Optional[float] = None   # meta formulada (kg total do lote), opcional
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class CategoriaManejo(SQLModel, table=True):
    """Parâmetro de categoria de manejo por idade/peso (aleitamento, recria 1,
    recria 2, apta). Cadastrável; classifica cada animal automaticamente. Na
    categoria de aptidão, o status reprodutivo (apta/inseminada/gestante) assume."""

    __tablename__ = "categoria_manejo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    dia_min: int = 0
    dia_max: Optional[int] = None          # None = sem limite superior
    peso_min_kg: Optional[float] = None
    peso_max_kg: Optional[float] = None
    usa_status_reprodutivo: bool = False   # True: a partir daqui, o status reprodutivo assume
    # Critérios adicionais — todos opcionais; None = não filtra por aquele
    # critério. Permitem compor categorias como "Prenha", "Em lactação",
    # "Seca", "Vazia atrasada" etc. além de idade/peso.
    situacao_reprodutiva: Optional[str] = None   # "vazia" | "inseminada" | "prenha"
    situacao_produtiva: Optional[str] = None     # "lactacao" | "seca"
    dias_gestacao_min: Optional[int] = None
    dias_gestacao_max: Optional[int] = None
    dias_desde_servico_min: Optional[int] = None
    dias_desde_servico_max: Optional[int] = None
    dias_para_parto_min: Optional[int] = None
    dias_para_parto_max: Optional[int] = None
    dias_pos_parto_min: Optional[int] = None
    dias_pos_parto_max: Optional[int] = None
    ordem: int = 0
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
