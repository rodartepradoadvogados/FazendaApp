"""
Sanitário Preventivo v2 — vacinas, exames e vermífugos ("caixas").

Modelo aprovado em 21/10/2026 (modelo_v1.md §12/§13 e plano de implementação,
seção C). Substitui o módulo antigo (calendário/regras, eventos sanitários,
cronogramas, lista de espera), arquivado pela migração s0a1r2q3v4o5.

Vocabulário:
  - CAIXA: o cadastro de uma vacina/exame/vermífugo/outro. Cada animal entra
    na caixa quando cumpre a regra e sai quando recebe, deixa de cumprir,
    sai do rebanho, é dispensado ou a janela fecha. Editar a caixa cria uma
    VERSÃO nova (vale dali para frente; o histórico fica como foi).
  - CICLO: a "rodada" de uma caixa para um animal, deduzida do tipo de janela
    (`ciclo_chave`): U (dose única), G:{servico_id} (gestação/pré-parto),
    IA:{AAAA-MM-DD} (entrada em IA), P:/S:/CP:{AAAA-MM-DD} (parto, secagem,
    compra), M:AAAA-MM ou M:AAAA-MM..MM (mês/grupo de meses), F:AAAA
    (frequência em anos), C (contínuo sem evento).
  - DIA: o dia marcado da aplicação/coleta ("Vacina · B19 · 25/12" ou
    "Exame · ..."). Termo interno: aplicação.
  - REGISTRO: a aplicação/resultado por animal — o histórico ÚNICO (dia,
    lançamento simples, ficha de campo, importação de planilha).

Regras duras (ver fazenda/rules/sanitario/):
  - Só o motor (`recalcular`) escreve `sanitario_situacao`; nenhuma leitura grava.
  - Chave única animal × caixa × ciclo × dose em `sanitario_situacao` e (para
    registro válido que conta) em `sanitario_registro`.
  - Aplicar nunca cria caixa; só o cadastro (wizard/catálogo) cria.
  - `fazenda_id` NOT NULL em tudo, menos o catálogo central (cockpit CowData)
    e as normas — tabelas GLOBAIS por definição.
  - Categorias e produtos por ID, nunca por texto.

As FKs para tabelas de fazenda são simples aqui no model (como no resto do
projeto); no Postgres a migração s1n2o3v4o5m6 as compõe com `fazenda_id`
(padrão de 472f92e0860b).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# JSON portátil: JSONB no Postgres (indexável/comparável), JSON no SQLite.
JSON_T = JSON().with_variant(JSONB(), "postgresql")


def _json(nullable: bool = True) -> Column:
    return Column(JSON_T, nullable=nullable)


# ── Vocabulário fechado (validado nos schemas da API, F5) ───────────────────
TIPOS_CAIXA = ("vacina", "exame", "vermifugo", "outro")
ESTADOS_CAIXA = ("ativa", "inativa", "arquivada")
PRODUTO_MODOS = ("estoque", "sem_estoque", "vazio", "nao_se_aplica")
DOSE_UNIDADES = ("mL", "dose", "g", "comprimido", "mL_por_kg", "mL_por_x_kg")
EVENTO_TIPOS = ("idade", "pre_parto", "entrada_ia", "parto", "secagem", "compra")
PERIODO_MODOS = ("meses", "frequencia", "continuo")
AO_FECHAR = ("perder", "manter", "descartar")
CONDICOES = ("prenhe", "pre_parto", "lactacao", "seca", "apta_ia")
ESTADOS_SITUACAO = (
    "prevista", "aviso", "janela", "marcada", "aplicada", "atrasada",
    "perdida", "descartada", "dispensada", "saiu", "fora",
)
ESTADOS_DIA = ("marcado", "em_execucao", "fechado", "cancelado")
CARENCIA_MODOS_LEITE = ("bloqueio", "descarte", "tanque")


# ════════════════════════════════════════════════════════════════════════════
# Catálogo central (GLOBAL — cockpit CowData)
# ════════════════════════════════════════════════════════════════════════════
class SanitarioCatalogo(SQLModel, table=True):
    """Item do catálogo central de vacinas/exames, mantido no cockpit CowData.
    Cada fazenda ATIVA (copia) o que quiser para uma caixa própria; mudança
    no catálogo vira aviso para a fazenda, nunca sobrescreve a caixa dela."""

    __tablename__ = "sanitario_catalogo"

    id: Optional[int] = Field(default=None, primary_key=True)
    chave: str = Field(index=True, unique=True)
    nome: str
    tipo: str = "vacina"
    versao_atual: int = 1
    padrao_fabrica: bool = False   # vem criado (inativo) em toda fazenda
    ativo: bool = True
    uf_sugerida: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class SanitarioCatalogoVersao(SQLModel, table=True):
    """Versão imutável de um item do catálogo central. `definicao` tem o mesmo
    formato do payload da caixa (ver rules/sanitario/definicao.py), com as
    categorias por REFERÊNCIA de nome (`categorias_ref`), resolvidas para os
    IDs da fazenda na ativação."""

    __tablename__ = "sanitario_catalogo_versao"
    __table_args__ = (UniqueConstraint("catalogo_id", "versao", name="uq_sanitario_catalogo_versao"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    catalogo_id: int = Field(foreign_key="sanitario_catalogo.id", index=True)
    versao: int = 1
    definicao: dict = Field(default_factory=dict, sa_column=_json(nullable=False))
    nota_mudanca: Optional[str] = None
    base_legal: Optional[str] = None
    publicado_em: datetime = Field(default_factory=datetime.utcnow)
    publicado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class SanitarioNorma(SQLModel, table=True):
    """Norma legal por UF (GLOBAL). Toda mudança vira sugestão para a fazenda,
    nunca sobrescreve. Preenchida no cockpit (F8)."""

    __tablename__ = "sanitario_norma"
    __table_args__ = (UniqueConstraint("uf", "chave", "versao", name="uq_sanitario_norma_uf_chave_versao"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    uf: str = Field(index=True)
    chave: str
    texto: str
    base_legal: Optional[str] = None
    valores_sugeridos: Optional[dict] = Field(default=None, sa_column=_json())
    vigente_desde: Optional[date] = None
    versao: int = 1
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ════════════════════════════════════════════════════════════════════════════
# Caixa e versões (por fazenda)
# ════════════════════════════════════════════════════════════════════════════
class SanitarioCaixa(SQLModel, table=True):
    """O cadastro de uma vacina/exame/vermífugo/outro da fazenda. As regras
    vivem na versão vigente (`versao_atual_id`)."""

    __tablename__ = "sanitario_caixa"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_caixa_id_fazenda_id"),
        # Nome único por fazenda entre as não arquivadas (arquivar libera o nome).
        Index(
            "uq_sanitario_caixa_nome_vivo", "fazenda_id", "nome_normalizado", unique=True,
            sqlite_where=text("estado <> 'arquivada'"), postgresql_where=text("estado <> 'arquivada'"),
        ),
        Index("ix_sanitario_caixa_fazenda_estado", "fazenda_id", "estado"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    nome: str
    nome_normalizado: str              # lower/trim de `nome` — chave do UNIQUE parcial
    nome_curto: Optional[str] = None
    tipo: str = "vacina"               # TIPOS_CAIXA
    estado: str = "inativa"            # ESTADOS_CAIXA
    obrigatoria: bool = False          # entra na cobertura obrigatória (dono único)
    padrao_fabrica: bool = False
    versao_atual_id: Optional[int] = Field(default=None, index=True)  # sem FK (ciclo caixa<->versão)
    catalogo_id: Optional[int] = Field(default=None, foreign_key="sanitario_catalogo.id")
    catalogo_versao: Optional[int] = None
    ativada_em: Optional[date] = None  # 1ª ativação: ciclos anteriores não viram "atrasada"
    mesclada_em_caixa_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa.id")
    arquivada_em: Optional[datetime] = None
    arquivada_motivo: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    criado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class SanitarioCaixaVersao(SQLModel, table=True):
    """Regras de uma caixa a partir de `vigente_desde`. Imutável depois de
    criada: editar a caixa grava uma versão nova."""

    __tablename__ = "sanitario_caixa_versao"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_caixa_versao_id_fazenda_id"),
        UniqueConstraint("caixa_id", "numero", name="uq_sanitario_caixa_versao_numero"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    caixa_id: int = Field(foreign_key="sanitario_caixa.id", index=True)
    numero: int = 1
    vigente_desde: date
    vigente_ate: Optional[date] = None

    # Produto e dose
    produto_modo: str = "vazio"        # PRODUTO_MODOS
    estoque_id: Optional[int] = Field(default=None, foreign_key="estoque.id")
    produto_texto: Optional[str] = None
    dose_valor: Optional[float] = None
    dose_unidade: Optional[str] = None  # DOSE_UNIDADES
    dose_x_kg: Optional[float] = None   # "mL por X kg"
    peso_ausente: str = "estimado"      # exigir | estimado

    # Público
    pub_sexo: str = "ambos"             # F | M | ambos
    pub_cat_modo: str = "incluir"       # incluir | excluir (categorias por ID na tabela filha)
    pub_idade_min_dias: Optional[int] = None
    pub_idade_max_dias: Optional[int] = None
    pub_condicoes: list = Field(default_factory=list, sa_column=_json(nullable=False))
    pub_hist_tipo: Optional[str] = None  # ja | nunca
    pub_hist_caixa_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa.id")

    # Janela
    jan_usa_evento: bool = False
    evento_tipo: Optional[str] = None   # EVENTO_TIPOS
    evento_de_dias: Optional[int] = None
    evento_ate_dias: Optional[int] = None
    jan_usa_periodo: bool = False
    periodo_modo: Optional[str] = None  # PERIODO_MODOS
    periodo_grupos: list = Field(default_factory=list, sa_column=_json(nullable=False))  # [[0],[5,6],[11]] (mês 0-11)
    periodo_anos: Optional[int] = None
    periodo_ano_base: Optional[int] = None
    data_base_dia: int = 15
    comecar_em: Optional[date] = None
    ao_fechar: str = "manter"           # AO_FECHAR
    serie: list = Field(default_factory=list, sa_column=_json(nullable=False))  # [{"dose":2,"apos_dias":30,"janela_dias":30}]

    # Aglomeração e aviso
    aglo_min: int = 4
    aviso_antecedencia_dias: int = 30
    aviso_fim_janela_dias: Optional[int] = None
    push_admin: bool = True

    # Veterinário e etapas legais (cada uma liga/desliga)
    legal_crmv_pedir: bool = False
    legal_atestado: Optional[dict] = Field(default=None, sa_column=_json())
    legal_comprovacao: Optional[dict] = Field(default=None, sa_column=_json())
    legal_leitura: Optional[dict] = Field(default=None, sa_column=_json())
    legal_reagente_aviso: bool = False
    legal_marca_texto: Optional[str] = None

    # Carência (NULL = não informada, nunca zero)
    car_leite_dias: Optional[int] = None
    car_carne_dias: Optional[int] = None
    car_modo_leite: Optional[str] = None  # CARENCIA_MODOS_LEITE

    # Outros
    ficha_colunas: list = Field(default_factory=list, sa_column=_json(nullable=False))
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    criado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class SanitarioCaixaVersaoCategoria(SQLModel, table=True):
    """Categorias de manejo do público de uma versão — por ID, nunca por texto."""

    __tablename__ = "sanitario_caixa_versao_categoria"
    __table_args__ = (UniqueConstraint("versao_id", "categoria_manejo_id", name="uq_sanitario_versao_categoria"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    versao_id: int = Field(foreign_key="sanitario_caixa_versao.id", index=True)
    categoria_manejo_id: int = Field(foreign_key="categoria_manejo.id")


# ════════════════════════════════════════════════════════════════════════════
# Situação (só o motor escreve)
# ════════════════════════════════════════════════════════════════════════════
class SanitarioSituacao(SQLModel, table=True):
    """Situação de um animal numa caixa num ciclo (e dose). Gravada SÓ por
    `rules.sanitario.motor.recalcular` (job diário e ganchos de escrita).

    Exceção deliberada: `dispensada_*` é uma DECISÃO de gente (dispensar o
    animal neste ciclo) — o motor lê e preserva, nunca apaga."""

    __tablename__ = "sanitario_situacao"
    __table_args__ = (
        UniqueConstraint(
            "fazenda_id", "caixa_id", "animal_id", "ciclo_chave", "dose_num", name="uq_sanitario_situacao_chave",
        ),
        Index("ix_sanitario_situacao_fazenda_estado", "fazenda_id", "estado"),
        Index("ix_sanitario_situacao_fazenda_caixa_estado", "fazenda_id", "caixa_id", "estado"),
        Index("ix_sanitario_situacao_fazenda_janela_inicio", "fazenda_id", "janela_inicio"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    caixa_id: int = Field(foreign_key="sanitario_caixa.id")
    caixa_versao_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa_versao.id")
    animal_id: int = Field(foreign_key="animal.id", index=True)
    ciclo_chave: str
    dose_num: int = 1
    estado: str                        # ESTADOS_SITUACAO
    janela_inicio: Optional[date] = None
    janela_fim: Optional[date] = None
    data_base: Optional[date] = None
    motivo: Optional[str] = None       # texto do "fora"/da janela
    dia_id: Optional[int] = Field(default=None, foreign_key="sanitario_dia.id")
    registro_id: Optional[int] = Field(default=None, foreign_key="sanitario_registro.id")
    dispensada_em: Optional[datetime] = None
    dispensada_motivo: Optional[str] = None
    dispensada_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    calculado_em: datetime = Field(default_factory=datetime.utcnow)


# ════════════════════════════════════════════════════════════════════════════
# Dia marcado ("Vacina"/"Exame")
# ════════════════════════════════════════════════════════════════════════════
class SanitarioDia(SQLModel, table=True):
    __tablename__ = "sanitario_dia"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_dia_id_fazenda_id"),
        Index("ix_sanitario_dia_fazenda_data_estado", "fazenda_id", "data", "estado"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    tipo: str = "vacina"               # vacina | exame (derivado das caixas e gravado)
    data: date
    hora: Optional[str] = None         # "HH:MM"
    data_prevista: Optional[date] = None
    estado: str = "marcado"            # ESTADOS_DIA
    veterinario_pessoa_id: Optional[int] = Field(default=None, foreign_key="pessoa.id")
    veterinario_texto: Optional[str] = None
    crmv_texto: Optional[str] = None
    observacao: Optional[str] = None
    decisao_riscos: Optional[dict] = Field(default=None, sa_column=_json())
    fechado_em: Optional[datetime] = None
    fechado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fechamento_auto: bool = False
    motivo_cancelamento: Optional[str] = None
    versao_lock: int = 1
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    criado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class SanitarioDiaCaixa(SQLModel, table=True):
    """Uma caixa dentro de um dia, com o produto/dose daquele dia."""

    __tablename__ = "sanitario_dia_caixa"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_dia_caixa_id_fazenda_id"),
        UniqueConstraint("dia_id", "caixa_id", name="uq_sanitario_dia_caixa"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    dia_id: int = Field(foreign_key="sanitario_dia.id", index=True)
    caixa_id: int = Field(foreign_key="sanitario_caixa.id")
    caixa_versao_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa_versao.id")
    produto_modo: str = "vazio"
    estoque_id: Optional[int] = Field(default=None, foreign_key="estoque.id")
    produto_texto: Optional[str] = None
    dose_valor: Optional[float] = None
    dose_unidade: Optional[str] = None
    dose_x_kg: Optional[float] = None
    carencia_decisao_id: Optional[int] = Field(default=None, foreign_key="sanitario_carencia_aceite.id")


class SanitarioDiaItem(SQLModel, table=True):
    """Um animal × caixa num dia. `origem`: janela (veio pela caixa), manual
    (incluído na marcação) ou curral (incluído na hora)."""

    __tablename__ = "sanitario_dia_item"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_dia_item_id_fazenda_id"),
        UniqueConstraint("dia_id", "animal_id", "caixa_id", name="uq_sanitario_dia_item"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    dia_id: int = Field(foreign_key="sanitario_dia.id", index=True)
    animal_id: int = Field(foreign_key="animal.id", index=True)
    caixa_id: int = Field(foreign_key="sanitario_caixa.id")
    origem: str = "janela"             # janela | manual | curral
    estado: str = "pendente"           # pendente | feito | faltou | dispensado | removido
    consentimento_log_id: Optional[int] = Field(default=None, foreign_key="sanitario_log.id")
    situacao_id: Optional[int] = None  # referência fraca (a situação é recalculada)
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ════════════════════════════════════════════════════════════════════════════
# Registro por animal — o histórico único
# ════════════════════════════════════════════════════════════════════════════
class SanitarioRegistro(SQLModel, table=True):
    __tablename__ = "sanitario_registro"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_registro_id_fazenda_id"),
        UniqueConstraint("fazenda_id", "chave_idempotencia", name="uq_sanitario_registro_idempotencia"),
        # Um registro VÁLIDO que conta por animal × caixa × ciclo × dose. "Só
        # registro" (planilha importada, "outro") e estornado não entram.
        Index(
            "uq_sanitario_registro_chave_valida",
            "fazenda_id", "animal_id", "caixa_id", "ciclo_chave", "dose_num", unique=True,
            sqlite_where=text("estado = 'valido' AND so_registro = 0 AND caixa_id IS NOT NULL"),
            postgresql_where=text("estado = 'valido' AND so_registro = false AND caixa_id IS NOT NULL"),
        ),
        Index("ix_sanitario_registro_fazenda_data", "fazenda_id", "data"),
        Index("ix_sanitario_registro_fazenda_animal", "fazenda_id", "animal_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)

    # Identificação
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id")  # NULL = brinco sem cadastro
    numero_animal_texto: Optional[str] = None
    caixa_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa.id")  # NULL = "outro"
    caixa_versao_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa_versao.id")
    outro_texto: Optional[str] = None
    ciclo_chave: Optional[str] = None
    dose_num: int = 1
    dia_id: Optional[int] = Field(default=None, foreign_key="sanitario_dia.id")
    dia_item_id: Optional[int] = Field(default=None, foreign_key="sanitario_dia_item.id")
    data: date
    hora: Optional[str] = None

    # Origem
    origem: str = "dia"                # dia | lancamento_simples | ficha | importado
    canal: str = "site"                # site | app | curral | importacao
    so_registro: bool = False          # aparece no histórico; não conta nem tira da caixa
    decisao_curral: bool = False
    apos_fechamento: bool = False
    retroativo: bool = False
    retroativo_motivo: Optional[str] = None
    fora_da_regra: bool = False

    # Produto
    produto_modo: Optional[str] = None
    estoque_id: Optional[int] = Field(default=None, foreign_key="estoque.id")
    lote_estoque_id: Optional[int] = Field(default=None, foreign_key="lote_estoque.id")
    partida_texto: Optional[str] = None
    fabricante: Optional[str] = None
    validade: Optional[date] = None
    produto_texto: Optional[str] = None
    dose_valor: Optional[float] = None
    dose_unidade: Optional[str] = None
    quantidade_baixada: Optional[float] = None
    movimento_estoque_id: Optional[int] = Field(default=None, foreign_key="movimento_estoque.id")
    custo: Optional[float] = None
    peso_usado: Optional[float] = None
    peso_estimado: bool = False

    # Pessoas
    aplicador_pessoa_id: Optional[int] = Field(default=None, foreign_key="pessoa.id")
    aplicador_texto: Optional[str] = None
    veterinario_pessoa_id: Optional[int] = Field(default=None, foreign_key="pessoa.id")
    veterinario_texto: Optional[str] = None
    crmv_texto: Optional[str] = None

    # Exame
    resultado: Optional[str] = None    # positivo | negativo | inconclusivo | nao_lido
    resultado_valor: Optional[float] = None
    resultado_detalhe: Optional[dict] = Field(default=None, sa_column=_json())
    leitura_em: Optional[datetime] = None

    # Carência e atestado
    carencia_leite_ate: Optional[date] = None
    carencia_carne_ate: Optional[date] = None
    carencia_modo: Optional[str] = None
    carencia_aceite_id: Optional[int] = Field(default=None, foreign_key="sanitario_carencia_aceite.id")
    atestado_numero: Optional[str] = None
    atestado_destinatario: Optional[str] = None
    numero_lancamento_vinculado: Optional[str] = None

    # Estado
    estado: str = "valido"             # valido | estornado
    estornado_em: Optional[datetime] = None
    estornado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    estornado_motivo: Optional[str] = None
    chave_idempotencia: Optional[str] = None
    dispositivo_id: Optional[int] = Field(default=None, foreign_key="sanitario_dispositivo.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    criado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ════════════════════════════════════════════════════════════════════════════
# Log de decisões, carência, prazos, notas, dispositivos, parâmetros, job
# ════════════════════════════════════════════════════════════════════════════
class SanitarioLog(SQLModel, table=True):
    """Decisões e consentimentos (o produtor decide; o sistema registra).
    Tipos: consentimento.fora_janela|inelegivel|legal, carencia.decisao|aceite,
    dia.data_diferente|fechado|fechado_auto, registro.retroativo|estorno,
    caixa.versao|arquivada|mesclada, catalogo.atualizado, escrita.duplicada,
    offline.conflito."""

    __tablename__ = "sanitario_log"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_log_id_fazenda_id"),
        Index("ix_sanitario_log_fazenda_em", "fazenda_id", "em"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    tipo: str
    dia_id: Optional[int] = Field(default=None, foreign_key="sanitario_dia.id")
    caixa_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa.id")
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id")
    registro_id: Optional[int] = None  # referência fraca (o log sobrevive ao registro)
    motivo_exibido: Optional[str] = None
    decisao: Optional[str] = None
    texto_livre: Optional[str] = None
    payload: Optional[dict] = Field(default=None, sa_column=_json())
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    dispositivo_id: Optional[int] = None
    em: datetime = Field(default_factory=datetime.utcnow)


class SanitarioCarenciaAceite(SQLModel, table=True):
    """Aceite (1 clique, só administrador) da carência de uma versão de caixa,
    ou decisão do pop-up para um produto num dia."""

    __tablename__ = "sanitario_carencia_aceite"
    __table_args__ = (UniqueConstraint("id", "fazenda_id", name="uq_sanitario_carencia_aceite_id_fazenda_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    escopo: str = "caixa_versao"       # caixa_versao | dia_caixa
    caixa_versao_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa_versao.id")
    dia_caixa_id: Optional[int] = None  # sem FK (ciclo dia_caixa<->aceite)
    modo_leite: Optional[str] = None
    leite_dias: Optional[int] = None
    carne_dias: Optional[int] = None
    origem: str = "wizard"             # wizard | popup
    aceito_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    aceito_em: datetime = Field(default_factory=datetime.utcnow)


class SanitarioPrazoLegal(SQLModel, table=True):
    """Atestado (ex.: SIDAGO, o que vencer primeiro entre aplicação e NF-e) e
    comprovação periódica (ex.: 180 dias)."""

    __tablename__ = "sanitario_prazo_legal"
    __table_args__ = (
        UniqueConstraint("fazenda_id", "tipo", "caixa_id", "referencia_chave", name="uq_sanitario_prazo_legal"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    tipo: str                          # atestado | comprovacao
    caixa_id: int = Field(foreign_key="sanitario_caixa.id")
    referencia_chave: str              # "dia:12" | "data:2026-10-21"
    registro_ids: list = Field(default_factory=list, sa_column=_json(nullable=False))
    vence_em: date
    destinatario: Optional[str] = None
    estado: str = "aberto"             # aberto | cumprido | dispensado
    cumprido_em: Optional[date] = None
    documento_numero: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class SanitarioNotaAgenda(SQLModel, table=True):
    """Nota do sanitário na Agenda (aglomerou, fim de janela, véspera, animal
    saiu da janela, carência pendente, prazo legal, celular offline,
    fechamento automático, catálogo mudou). `chave_dedupe` impede duplicata —
    a de "aglomerou" é `aglo:{caixa}:{ciclo}`, sem o N."""

    __tablename__ = "sanitario_nota_agenda"
    __table_args__ = (UniqueConstraint("fazenda_id", "chave_dedupe", name="uq_sanitario_nota_dedupe"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    tipo: str
    caixa_id: Optional[int] = Field(default=None, foreign_key="sanitario_caixa.id")
    ciclo_chave: Optional[str] = None
    dia_id: Optional[int] = Field(default=None, foreign_key="sanitario_dia.id")
    chave_dedupe: str
    titulo: str
    texto: Optional[str] = None
    dados: Optional[dict] = Field(default=None, sa_column=_json())
    so_admin: bool = True
    data_ref: Optional[date] = None
    resolvida_em: Optional[datetime] = None
    push_enviado_em: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class SanitarioDispositivo(SQLModel, table=True):
    """Celular do app de campo (heartbeat offline: fila pendente e último contato)."""

    __tablename__ = "sanitario_dispositivo"
    __table_args__ = (
        UniqueConstraint("id", "fazenda_id", name="uq_sanitario_dispositivo_id_fazenda_id"),
        UniqueConstraint("fazenda_id", "usuario_id", "dispositivo_uid", name="uq_sanitario_dispositivo"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    dispositivo_uid: str
    nome: Optional[str] = None
    ultimo_contato_em: Optional[datetime] = None
    fila_pendentes: int = 0
    fila_mais_antigo_em: Optional[datetime] = None
    aviso_admin_em: Optional[datetime] = None


class SanitarioParametros(SQLModel, table=True):
    """Parâmetros › Sanitário (1 linha por fazenda). Os protocolos obrigatórios
    NÃO ficam aqui: são `sanitario_caixa.obrigatoria` (dono único)."""

    __tablename__ = "sanitario_parametros"
    __table_args__ = (UniqueConstraint("fazenda_id", name="uq_sanitario_parametros_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    uf: Optional[str] = None
    prazos_legais_ativo: bool = False
    antecedencia_padrao_dias: int = 30
    corrigir_ate: str = "fechar_dia"
    dose_externa_sem_data: str = "contar"     # contar | nao_contar
    peso_estimado: str = "aceitar"            # aceitar | exigir
    modo_tuberculina: str = "so_resultado"    # so_resultado | diferenca | medidas
    aviso_offline_horas: int = 24
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class SanitarioJobEstado(SQLModel, table=True):
    """Estado da rotina diária do sanitário por fazenda (lock + 1×/dia local)."""

    __tablename__ = "sanitario_job_estado"
    __table_args__ = (UniqueConstraint("fazenda_id", name="uq_sanitario_job_estado_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    ultima_diaria_em: Optional[date] = None   # dia LOCAL (America/Sao_Paulo)
    em_execucao_ate: Optional[datetime] = None  # lock (UTC ingênuo)
    status: Optional[str] = None
    erro: Optional[str] = None
    contagens: Optional[dict[str, Any]] = Field(default=None, sa_column=_json())
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


TABELAS_SANITARIO_V2 = (
    "sanitario_catalogo", "sanitario_catalogo_versao", "sanitario_norma",
    "sanitario_caixa", "sanitario_caixa_versao", "sanitario_caixa_versao_categoria",
    "sanitario_dispositivo", "sanitario_dia", "sanitario_log", "sanitario_carencia_aceite",
    "sanitario_dia_caixa", "sanitario_dia_item", "sanitario_registro", "sanitario_situacao",
    "sanitario_prazo_legal", "sanitario_nota_agenda", "sanitario_parametros", "sanitario_job_estado",
)
TABELAS_SANITARIO_GLOBAIS = ("sanitario_catalogo", "sanitario_catalogo_versao", "sanitario_norma")
