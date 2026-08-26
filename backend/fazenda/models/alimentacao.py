"""
Alimentação — cadastro de alimentos, dietas por lote, matéria seca, tabela nutricional e análises bromatológicas.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

# ---------------------------------------------------------------------------
# Dieta (plano alimentar por lote)
# ---------------------------------------------------------------------------
class CategoriaAlimento(SQLModel, table=True):
    """Categoria de alimento (Volumoso, Concentrado, Mineral...), editável em
    Configurações > Cadastro > Alimentação > Categorias. Agrupa os Alimentos
    cadastrados — puramente organizacional, sem regra de cálculo própria.

    `categoria_pai_id` permite UM nível de subdivisão (ex.: "Proteico" sob
    "Concentrado") — NULL é raiz. Só dois níveis são permitidos: o router
    recusa uma categoria que já tem pai virar pai de outra (ver
    `criar_categoria_alimento`/`atualizar_categoria_alimento`). A FK aponta
    para a própria tabela, então não pode ser NOT NULL nem ter default
    diferente de None (senão a primeira raiz nunca cadastrada travaria)."""

    __tablename__ = "categoria_alimento"
    __table_args__ = (
        UniqueConstraint(
            "nome", "categoria_pai_id", "fazenda_id", name="uq_categoria_alimento_nome_pai_fazenda"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    # Auto-FK opcional — raiz quando None. Indexada porque toda listagem
    # (GET /alimentacao/categorias) e toda checagem de "tem filha" (exclusão)
    # filtram por ela.
    categoria_pai_id: Optional[int] = Field(default=None, foreign_key="categoria_alimento.id", index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Alimento(SQLModel, table=True):
    """Cadastro de alimento (Configurações > Cadastro > Alimentação >
    Alimentos) — distinto do item de Estoque: um Alimento é o conceito
    nutricional (ex.: "Silagem de milho"), que pode estar vinculado a um ou
    mais itens de Estoque (ver `Estoque.alimento_id`) de onde vem a baixa
    física quando a dieta é lançada. Um Alimento sem nenhum Estoque vinculado
    ainda é válido (ex.: acabou de ser cadastrado), mas fica marcado como
    pendente de vínculo nas telas onde aparece."""

    __tablename__ = "alimento"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_alimento_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    categoria_alimento_id: Optional[int] = Field(default=None, foreign_key="categoria_alimento.id")
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    # Fase P1 do refactor Alimento/Estoque — quando este Alimento tem 2+
    # itens de Estoque vinculados (`Estoque.alimento_id`), toda resolução por
    # nome (`_estoque_por_alimento`, usada pela baixa automática diária, pelo
    # lançamento manual de consumo e pela necessidade mensal) hoje pega o
    # primeiro candidato que a query devolve, em ordem arbitrária — ver
    # TestEscolhaArbitrariaDeCandidato (T11) em tests/test_migracao_alimento.py.
    # Este campo deixa a fazenda ESCOLHER deliberadamente qual item recebe a
    # baixa (ver PUT /alimentacao/alimentos/{alimento_id}/estoque-preferido);
    # NULL preserva a ordem arbitrária de hoje exatamente como está — nenhum
    # comportamento muda pra quem não usar o mecanismo novo.
    estoque_preferido_id: Optional[int] = Field(default=None, foreign_key="estoque.id")


class Dieta(SQLModel, table=True):
    """Uma linha por (lote, ingrediente) do DIETA.csv — quantidade por cabeça/dia."""

    __tablename__ = "dieta"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    lote: Optional[int] = Field(default=None, index=True)
    categoria: Optional[str] = None
    ingrediente: str
    quantidade: Optional[float] = None
    unidade: Optional[str] = None  # kg ou L, por cabeça/dia
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Lançamento de dieta (Lançamentos > Alimentação) — histórico por lote, com
# data de abertura/encerramento previsto/efetivo, e a comparação programado
# (nutricionista) × real oferecido. Independente do `Dieta` acima (que segue
# vindo do DIETA.csv e alimentando o painel de Alimentação já existente).
# ---------------------------------------------------------------------------
class DietaLancamento(SQLModel, table=True):
    """Uma dieta lançada para um lote — só uma pode estar ativa por lote."""

    __tablename__ = "dieta_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    lote: int = Field(index=True)
    responsavel: Optional[str] = None  # nutricionista — ex. "Alexandre Scarpa"
    data_abertura: date
    data_prevista_encerramento: Optional[date] = None  # gera evento de análise na Agenda
    data_efetivo_encerramento: Optional[date] = None
    observacao: Optional[str] = None
    # Como as quantidades dos itens foram informadas: "total" do lote/dia (padrão)
    # ou "animal" (por cabeça/dia — o total é multiplicado pelo nº de animais).
    # Serve de PADRÃO da dieta — cada item pode sobrescrever isso individualmente
    # em `DietaItemProgramado.base_quantidade` (ver lá).
    base_quantidade: Optional[str] = None
    # Leite destinado aos bezerros nesta dieta (kg/dia do lote) — alimenta o
    # relatório Controle × Entregue (consumo de bezerros). Preenchido pelo
    # veterinário/nutricionista ao lançar a dieta de um lote de bezerras.
    leite_bezerros_kg_dia: Optional[float] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Rastro "esta dieta veio de uma simulação" — preenchido só quando o
    # lançamento nasce de Formulação de Dietas > Aplicar na dieta atual
    # (ver fazenda/api/routers/formulacao_dietas.py). None para lançamentos
    # feitos direto em Alimentação, como sempre.
    dieta_simulacao_id: Optional[int] = Field(default=None, foreign_key="dieta_simulacao.id", index=True)


class DietaItemProgramado(SQLModel, table=True):
    """Um alimento do plano formulado (programado) de uma DietaLancamento — quantidade TOTAL do lote/dia."""

    __tablename__ = "dieta_item_programado"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    dieta_lancamento_id: int = Field(foreign_key="dieta_lancamento.id", index=True)
    alimento: str
    # Vínculo com o cadastro de Alimento, quando escolhido via o seletor (em
    # vez de texto livre) — permite resolver o(s) item(ns) de Estoque vinculados
    # sem depender de casar `alimento` (nome) com `Estoque.nome`. Fica None para
    # lançamentos antigos ou alimentos ainda sem cadastro correspondente.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")
    quantidade: float
    unidade: str
    # Base da quantidade do ingrediente: "MN" (matéria natural, padrão) ou "MS"
    # (matéria seca). ms_pct = % de matéria seca do alimento, para converter
    # entre as duas bases quando informado.
    base: Optional[str] = None
    ms_pct: Optional[float] = None
    # Sobrescreve, só para este item, o `DietaLancamento.base_quantidade` da
    # dieta ("total" ou "animal") — permite misturar bases no mesmo lançamento
    # (ex.: silagem em total do lote e concentrado em por-cabeça). `None`
    # (padrão) significa "usa o valor da dieta" — retrocompatível com todo
    # item lançado antes desta coluna existir.
    base_quantidade: Optional[str] = None


class IngredienteMS(SQLModel, table=True):
    """% de matéria seca (MS) de cada ingrediente padrão — editável na aba
    Matéria seca da Alimentação. Alimenta a conversão MN↔MS das dietas."""

    __tablename__ = "ingrediente_ms"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_ingrediente_ms_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    ms_pct: Optional[float] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class TabelaNutricionalProduto(SQLModel, table=True):
    """Um produto/alimento cadastrado na tabela nutricional (uma coluna da
    matriz nutriente × produto) — editável em Alimentação > Tabela nutricional."""

    __tablename__ = "tabela_nutricional_produto"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_tabela_nutricional_produto_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    ordem: int = 0
    # Vínculo opcional com o cadastro de Alimento — quando presente, a tela de
    # cadastro do Alimento pode oferecer "cadastrar tabela nutricional" direto.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")


class TabelaNutricionalValor(SQLModel, table=True):
    """Um valor (nutriente × produto) da tabela nutricional. Texto livre —
    a planilha de referência mistura unidades diferentes na mesma célula
    (ex.: "5.500,00 mg", "740,00 g (Mín)")."""

    __tablename__ = "tabela_nutricional_valor"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    produto_id: int = Field(foreign_key="tabela_nutricional_produto.id", index=True)
    nutriente: str = Field(index=True)
    valor: str = ""


class AnaliseBromatologica(SQLModel, table=True):
    """Laudo de análise bromatológica de um lote/silo de alimento — resultado
    de laboratório (não confundir com a Tabela Nutricional, que é referência
    padrão, ou Matéria seca, que é só o %MS por ingrediente genérico). Cada
    registro é um laudo pontual de um alimento específico da fazenda."""

    __tablename__ = "analise_bromatologica"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    data: date
    alimento: str = Field(index=True)
    # Vínculo opcional com o cadastro de Alimento (ver `Alimento`) — permite
    # oferecer "fazer análise bromatológica" direto do cadastro do alimento.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")
    ms_pct: Optional[float] = None  # matéria seca (%)
    pb_pct: Optional[float] = None  # proteína bruta (%)
    fdn_pct: Optional[float] = None  # fibra em detergente neutro (%)
    fda_pct: Optional[float] = None  # fibra em detergente ácido (%)
    ndt_pct: Optional[float] = None  # nutrientes digestíveis totais (%)
    ee_pct: Optional[float] = None  # extrato etéreo / gordura (%)
    cinzas_pct: Optional[float] = None
    ca_pct: Optional[float] = None  # cálcio (%)
    p_pct: Optional[float] = None  # fósforo (%)
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class DietaRegistroReal(SQLModel, table=True):
    """O que foi realmente oferecido, por data — comparado ao programado."""

    __tablename__ = "dieta_registro_real"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    dieta_lancamento_id: int = Field(foreign_key="dieta_lancamento.id", index=True)
    data: date
    alimento: str
    quantidade: float
    unidade: str
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Estado da baixa automática de estoque da Alimentação (uma linha por fazenda)
# ---------------------------------------------------------------------------
class AlimentacaoEstado(SQLModel, table=True):
    """
    Controla a data da última baixa automática de estoque da Alimentação —
    o sistema recalcula quantos dias se passaram desde então e dá a baixa
    proporcional ao consumo do rebanho (kg/dia) de uma vez, na próxima vez
    que a tela de Alimentação é aberta. `ultima_data_deducao` funciona como
    trava otimista (compare-and-swap): duas requisições concorrentes nunca
    aplicam a mesma baixa duas vezes (ver fazenda/api/routers/alimentacao.py).

    Era uma linha única (id=1) — passa a ser uma linha por fazenda (lookup
    por `fazenda_id`, não mais por id fixo), já que cada fazenda tem seu
    próprio ritmo de consumo e sua própria baixa automática independente.
    """

    __tablename__ = "alimentacao_estado"
    __table_args__ = (UniqueConstraint("fazenda_id", name="uq_alimentacao_estado_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    ultima_data_deducao: Optional[date] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Consumo diário e sobra (Lançamentos > Alimentação)
# ---------------------------------------------------------------------------
class ConsumoAlimento(SQLModel, table=True):
    """O que foi REALMENTE FORNECIDO de um alimento a um lote, num dia.

    Distinto de `DietaItemProgramado` (o plano) e de `DietaRegistroReal` (que
    registra o real por dieta mas NÃO dá baixa em estoque). Este é o único
    lançamento de alimentação que debita estoque pelo motor
    `rules/estoque_baixa.movimentar()`, com `origem_tipo="consumo_alimento"`,
    para a baixa ser rastreável e reversível.

    `lote` é `int`, a MESMA representação de `DietaLancamento.lote` — e essa
    escolha é deliberada: o lançamento de consumo só existe ancorado numa dieta
    ativa, então tem de falar a língua dela. O sistema tem quatro
    representações de lote convivendo (`Lote.codigo` str de 2 dígitos,
    `Animal.grupo_primario` "01 - Nome", este `int`, e str livre em
    Recria/Sanidade); a ponte para o cadastro é `f"{lote:02d}"`, como já faz
    `apresentacao_dieta`.

    Lançamentos do mesmo dia SOMAM (decisão do produto): o trato é fracionado
    ao longo do dia e cada passada do vagão é um lançamento.
    """

    __tablename__ = "consumo_alimento"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    data: date = Field(index=True)
    lote: int = Field(index=True)
    alimento: str
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")
    quantidade: float
    unidade: str
    # Quantos animais o lançamento considerou, quando veio pelo modo "por
    # cabeça". Guardado mesmo no modo kg direto porque é o que permite auditar
    # depois por que o número era aquele — o lote muda de tamanho todo dia.
    num_animais: Optional[int] = None
    # "animais" = derivado do nº de cabeças × quantidade por cabeça da dieta;
    # "kg" = digitado direto pelo funcionário.
    origem: str = "kg"
    # Alimento que não está na dieta ativa do lote, aceito porque o lote tem a
    # flag `permitir_fora_da_dieta`. Marcado para o relatório poder separar o
    # que foi exceção do que foi plano.
    fora_da_dieta: bool = False
    # Se ESTE registro de fato debitou o Estoque (`estoque_baixa.baixar`) ao
    # ser criado — depende do `Lote.modo_baixa_estoque` NO MOMENTO do
    # lançamento ("consumo_real" debita, "automatica"/"sem_baixa" não, pra não
    # dobrar a baixa que a Alimentação já faz sozinha por dia decorrido).
    # Nasce True porque toda linha existente ANTES deste campo debitou estoque
    # incondicionalmente (era o único comportamento que existia). Guardado no
    # registro, não recalculado do modo ATUAL do lote, porque o modo pode
    # mudar depois — a exclusão (`excluir_consumo`) tem de saber se estorna
    # olhando pro que aconteceu quando o lançamento foi feito, não pro que o
    # lote é hoje.
    baixou_estoque: bool = True
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ConsumoSobra(SQLModel, table=True):
    """A sobra do cocho de um lote num dia, em QUILOS TOTAIS.

    Não é por alimento, e isso é decisão do produto: ninguém separa o que
    sobrou no cocho por ingrediente. O rateio por alimento é CALCULADO a partir
    da proporção da dieta (ver `rules/unidades.kg_equivalente`) e nunca
    gravado — gravar um rateio o congelaria, e ele muda se a dieta mudar.

    Ao contrário do consumo, relançar a sobra no mesmo dia SUBSTITUI em vez de
    somar: sobra é uma medição única do dia, não um acúmulo de eventos. A
    unicidade por (fazenda, lote, data) trava isso no banco, para não depender
    de a aplicação lembrar.
    """

    __tablename__ = "consumo_sobra"
    __table_args__ = (UniqueConstraint("fazenda_id", "lote", "data", name="uq_consumo_sobra_fazenda_lote_data"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    data: date = Field(index=True)
    lote: int = Field(index=True)
    kg_sobra: float = 0.0
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
