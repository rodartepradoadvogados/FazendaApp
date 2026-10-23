"""
Tipos do motor sanitário (puros — nenhum acesso a banco).

`CaixaDef` é a versão vigente de uma caixa já "achatada" (com as categorias
por ID). `AnimalCtx` é tudo o que o motor precisa saber de um animal, lido de
uma vez por `contexto.carregar_animais`. Com os dois em mãos, `motor.avaliar`
decide a situação sem tocar no banco — é isso que permite simular outra data
e garantir que nenhuma tela grava ao abrir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

# Datas-sentinela do ciclo "contínuo" (sem começo nem fim).
INICIO_SEMPRE = date(1900, 1, 1)
FIM_NUNCA = date(9999, 12, 31)

# Ciclo por evento cuja janela fechou há mais que isto deixa de ser
# acompanhado (não vira "perdida"/"atrasada" para sempre).
HORIZONTE_EVENTO_DIAS = 365

# Pré-parto: a janela vai de N dias antes do parto PREVISTO até o parto REAL.
PRE_PARTO_PADRAO_DIAS = 30

ESTADOS_NA_CAIXA = ("janela", "aviso", "atrasada")


@dataclass(frozen=True)
class CaixaDef:
    caixa_id: int
    versao_id: Optional[int]
    nome: str
    nome_curto: str
    tipo: str = "vacina"
    ativada_em: Optional[date] = None
    # Produto/dose
    produto_modo: str = "vazio"
    estoque_id: Optional[int] = None
    dose_valor: Optional[float] = None
    dose_unidade: Optional[str] = None
    dose_x_kg: Optional[float] = None
    # Público
    pub_sexo: str = "ambos"
    pub_cat_modo: str = "incluir"
    categorias: frozenset = frozenset()
    pub_idade_min_dias: Optional[int] = None
    pub_idade_max_dias: Optional[int] = None
    pub_condicoes: tuple = ()
    pub_hist_tipo: Optional[str] = None
    pub_hist_caixa_id: Optional[int] = None
    pub_hist_nome: Optional[str] = None
    # Janela
    jan_usa_evento: bool = False
    evento_tipo: Optional[str] = None
    evento_de_dias: Optional[int] = None
    evento_ate_dias: Optional[int] = None
    jan_usa_periodo: bool = False
    periodo_modo: Optional[str] = None
    periodo_grupos: tuple = ()
    periodo_anos: Optional[int] = None
    periodo_ano_base: Optional[int] = None
    data_base_dia: int = 15
    comecar_em: Optional[date] = None
    ao_fechar: str = "manter"
    serie: tuple = ()          # ({"dose": 2, "apos_dias": 30, "janela_dias": 30}, ...)
    # Aviso
    aglo_min: int = 4
    aviso_antecedencia_dias: int = 30
    aviso_fim_janela_dias: Optional[int] = None

    @property
    def eh_exame(self) -> bool:
        return self.tipo == "exame"

    @property
    def eh_periodo(self) -> bool:
        """Período de calendário que gera ciclos (meses/frequência). O
        "contínuo" não gera ciclo próprio: é a janela por evento que manda."""
        return bool(self.jan_usa_periodo and self.periodo_modo in ("meses", "frequencia") and self.periodo_grupos)

    @property
    def rotulo(self) -> str:
        return self.nome_curto or self.nome


@dataclass(frozen=True)
class Gestacao:
    servico_id: int
    data_servico: date
    parto_previsto: date
    parto_real: Optional[date] = None
    perda: Optional[date] = None


@dataclass(frozen=True)
class RegistroCtx:
    id: int
    caixa_id: Optional[int]
    ciclo_chave: Optional[str]
    dose_num: int
    data: date
    so_registro: bool = False


@dataclass
class AnimalCtx:
    id: int
    numero: str
    hoje: date
    sexo: Optional[str] = None
    nasc: Optional[date] = None
    ativo: bool = True
    saida_txt: Optional[str] = None
    gestacoes: tuple = ()          # Gestacao, ordem cronológica
    entrada_ia: Optional[date] = None
    partos: tuple = ()             # datas
    secagens: tuple = ()           # datas
    compra: Optional[date] = None
    peso: Optional[float] = None
    idade_apta_dias: int = 396
    # registros válidos (inclui "só registro"), por caixa
    registros: dict = field(default_factory=dict)
    # (caixa_id, ciclo_chave, dose_num) dispensados
    dispensas: frozenset = frozenset()
    # caixa_id -> (dia_id, data) do dia aberto com o animal pendente
    dias: dict = field(default_factory=dict)
    # d -> (categoria_manejo_id, nome) — classificação projetada, pura
    classificador: Optional[Callable[[date], tuple]] = None
    _cache_cat: dict = field(default_factory=dict, repr=False)

    def categoria_em(self, d: date) -> tuple:
        if self.classificador is None:
            return (None, None)
        if d not in self._cache_cat:
            self._cache_cat[d] = self.classificador(d)
        return self._cache_cat[d]

    def gestacao_atual(self) -> Optional[Gestacao]:
        """A gestação mais recente sem perda (pode já ter terminado em parto)."""
        for g in reversed(self.gestacoes):
            if g.perda is None:
                return g
        return None

    def registros_da_caixa(self, caixa_id: int) -> list:
        return self.registros.get(caixa_id, [])

    def registro_valido(self, caixa_id: int, ciclo_chave: str, dose_num: int = 1) -> Optional[RegistroCtx]:
        """Registro que CONTA (não é "só registro") neste ciclo/dose."""
        for r in self.registros.get(caixa_id, []):
            if not r.so_registro and r.ciclo_chave == ciclo_chave and r.dose_num == dose_num:
                return r
        return None


@dataclass(frozen=True)
class Ciclo:
    chave: str
    ini: date
    fim: date
    base: date
    rotulo: str
    per: bool = False           # ciclo de período do calendário
    aberta: bool = False        # pré-parto ainda sem parto real
    fim_prev: Optional[date] = None
    atrasado: bool = False


@dataclass(frozen=True)
class Motivo:
    ok: bool
    texto: str
    chave: str = ""


@dataclass
class Situacao:
    caixa_id: int
    animal_id: int
    estado: str
    texto: str = ""
    ciclo: Optional[Ciclo] = None
    dose_num: int = 1
    motivos: list = field(default_factory=list)
    registro_id: Optional[int] = None
    dia_id: Optional[int] = None
    dia_data: Optional[date] = None
    elegivel: bool = False

    @property
    def ciclo_chave(self) -> Optional[str]:
        return self.ciclo.chave if self.ciclo else None

    @property
    def motivo_fora(self) -> Optional[str]:
        for m in self.motivos:
            if not m.ok:
                return m.texto
        return None


@dataclass(frozen=True)
class NaData:
    """Resposta de "o animal estará pronto na data d?" (simulação e curral)."""
    ok: bool
    texto: str = ""
    kind: str = ""              # saiu | aplicada | ciclo | parto | publico | idade | fecha | antes
    data: Optional[date] = None
