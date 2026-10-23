"""
Sanidade — aplicações, farmácia (princípio ativo/medicamento), protocolos sanitários curativos, catálogo de touros.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar, Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

# ---------------------------------------------------------------------------
# Sanidade (medicamentos aplicados nos animais)
# ---------------------------------------------------------------------------
class Sanidade(SQLModel, table=True):
    """Uma aplicação de medicamento/vacina por linha — do SANIDADE.csv (Ideagri)."""

    __tablename__ = "sanidade"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    nome: Optional[str] = None
    data_nasc: Optional[date] = None
    sexo: Optional[str] = None
    raca: Optional[str] = None
    data_aplicacao: Optional[date] = Field(default=None, index=True)
    produto: str
    categoria: Optional[str] = None  # derivada (Vacina, Antiparasitário, ...)
    dose: Optional[float] = None
    unidade: Optional[str] = None  # unidade da dose (ml, L, unidade, dose) — lançamento manual
    via: Optional[str] = None
    responsavel: Optional[str] = None
    lote: Optional[str] = None
    atividade: Optional[str] = None
    obs: Optional[str] = None
    # "curativo" | "preventivo" — distingue o lançamento avulso (Curativa) das
    # aplicações de manejo (BST e Indução de cio gravam "preventivo"). O módulo
    # antigo de vacinas/exames preventivos foi arquivado em 2026 (schema
    # arquivo_sanitario_2026); o novo vive nas tabelas sanitario_*.
    # None (dado legado/importado do CSV) é tratado como "curativo" na leitura.
    natureza: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Origem da aplicação quando veio da confirmação de um protocolo agrupado —
    # permite excluir o lançamento inteiro (protocolo + agenda + Sanidade) de uma vez.
    protocolo_sanitario_lancamento_id: Optional[int] = Field(default=None, foreign_key="protocolo_sanitario_lancamento.id")
    protocolo_iatf_lancamento_id: Optional[int] = Field(default=None, foreign_key="protocolo_iatf_lancamento.id")
    # Espelha protocolo_iatf_lancamento_id acima, mas para a indução de
    # lactação — vínculo relacional com o ProtocoloInducaoLancamento que
    # originou esta Sanidade (antes só existia como texto livre em `obs`).
    protocolo_inducao_lancamento_id: Optional[int] = Field(
        default=None, foreign_key="protocolo_inducao_lancamento.id", index=True
    )
    # Avaliação de cura, pedida na Agenda no dia seguinte a uma aplicação
    # curativa (None = ainda não respondida). Alimenta o relatório Taxa de cura.
    curada: Optional[bool] = None
    # Vínculo (soft-join pelo número, igual a *.numero_lancamento_gerado em
    # ManutencaoPatrimonio/FolhaPagamento) com o lançamento financeiro em
    # ContaGerencial que paga esta aplicação — ver popup de vínculo
    # sanitário/reprodutivo, disparado ao salvar uma vacina/exame preventivo.
    numero_lancamento_vinculado: Optional[str] = Field(default=None, index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class AplicacaoAgendada(SQLModel, table=True):
    """
    Aplicação de medicamento lançada mas ainda NÃO aplicada (programada para o
    futuro ou marcada "aplicado? não"). Fica pendente na Agenda — nada é baixado
    do estoque até ser confirmada ("dar baixa"), quando vira um registro de
    Sanidade de verdade e dá a saída de estoque. Espelha "contas a pagar".
    """

    __tablename__ = "aplicacao_agendada"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    data: date = Field(index=True)  # data prevista da aplicação
    produto: str
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    aplicado: bool = Field(default=False, index=True)
    data_aplicacao: Optional[date] = None
    # "curativo" | "preventivo" — propagado para o Sanidade.natureza quando a
    # pendência é confirmada (ver _baixar_aplicacao_agendada).
    natureza: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Cadastros de apoio da farmácia e do sanitário (Configurações > Cadastro).
# ---------------------------------------------------------------------------
class PrincipioAtivo(SQLModel, table=True):
    """Espinha dorsal da farmácia: o princípio ativo (ou, para biológicos, o
    antígeno/doença combatida). Marcas comerciais e itens de estoque penduram
    aqui. O somatório de estoque e o alerta de mínimo são calculados no nível do
    princípio (ver rules/farmacia)."""

    __tablename__ = "principio_ativo"
    # nome era único globalmente — passa a ser único por fazenda (mesmo padrão
    # de CentroCusto/ColostragemBezerra), senão a 2ª fazenda nunca conseguiria
    # cadastrar um princípio ativo com o mesmo nome já usado pela 1ª.
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_principio_ativo_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ativo: bool = True
    # Enriquecimento (documento base de princípios ativos).
    categoria: Optional[str] = None  # grupo amplo do documento base, ex.: "Antimicrobianos e Antibióticos", "Biológicos (Vacinas e Diagnósticos)"
    categoria_software: Optional[str] = None  # ex.: "Antimicrobiano Sistêmico Injetável", "AINE", "Biológico (Vacina)"
    uso_principal: Optional[str] = None
    justificativa: Optional[str] = None
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")  # p/ biológicos: doença combatida
    eh_biologico: bool = False  # antígeno/vacina/diagnóstico (agrupado por doença, não por molécula)
    # Unificação de volumes: unidade canônica em que o saldo das apresentações é
    # somado (ml, L, dose, unidade, g). O mínimo é medido em "apresentações
    # primárias" (frascos/potes/seringas): padrão 1.
    unidade_base: Optional[str] = None            # ml | L | dose | unidade | g
    unidade_apresentacao: Optional[str] = None    # frasco | seringa | dose | dispositivo | pote | galão | caixa
    estoque_minimo_apresentacoes: float = 1.0
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ParametroMinimoFarmacia(SQLModel, table=True):
    """Estoque mínimo de um princípio ativo, em `unidade_base` (ml/L/g/
    unidade) — NUNCA por contagem de frascos/pacotes. Pedido do usuário
    (31/08/2026): "estoque mínimo... tem que ser em unidade de medida. Ex.:
    Sincrogest — 3 pacotes de 10 + 2 pacotes de 5 — mínimo: 12 unidades, e
    não pacotes."

    Vive numa tabela À PARTE de `PrincipioAtivo` — nunca escreve no próprio
    princípio — por dois motivos: (1) `PrincipioAtivo` pode ser um registro
    GLOBAL (`fazenda_id=None`, catálogo padrão CowData, ver
    painel_cowdata_farmacia.py) compartilhado por várias fazendas-cliente, e
    um valor de mínimo é sempre uma decisão de UMA fazenda (o consumo de
    Meloxicam da fazenda A não tem nada a ver com o mínimo ideal da fazenda
    B); (2) `PrincipioAtivo` documentadamente NUNCA é clonado por fazenda
    (ao contrário de Doença/MedicamentoComercial) — é a âncora fixa de
    `Estoque.principio_ativo_id`, então esta tabela evita precisar quebrar
    essa invariante só para guardar um número.

    Sem uma linha aqui para um princípio, `rules.farmacia.resumo_principios`
    continua usando a regra ANTIGA (mínimo em número de apresentações,
    `PrincipioAtivo.estoque_minimo_apresentacoes`) — nenhuma conversão
    automática acontece; cada fazenda concilia o próprio mínimo, um
    princípio de cada vez, pelo Painel de Conciliação (Configurações >
    Cadastro > Farmácia > Estoque mínimo)."""

    __tablename__ = "parametro_minimo_farmacia"
    __table_args__ = (UniqueConstraint("fazenda_id", "principio_ativo_id", name="uq_minimo_fazenda_principio"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    principio_ativo_id: int = Field(foreign_key="principio_ativo.id", index=True)
    estoque_minimo_base: float
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class MedicamentoComercial(SQLModel, table=True):
    """Marca comercial + laboratório de um princípio ativo (tabela filha). Ex.:
    Maxicam 2%/Ourofino → Meloxicam. Catálogo relacional; um item de estoque
    físico referencia uma marca (ou pelo menos o princípio).

    É AQUI que moram dose, via e carência — não no princípio ativo: duas marcas
    da mesma molécula têm concentrações diferentes (ivermectina 1% e 3,15% são
    volumes completamente diferentes) e carências diferentes. Herdar carência
    de "marca irmã" do mesmo princípio é justamente o erro que contamina tanque.
    """

    __tablename__ = "medicamento_comercial"

    id: Optional[int] = Field(default=None, primary_key=True)
    principio_ativo_id: int = Field(foreign_key="principio_ativo.id", index=True)
    nome_comercial: str = Field(index=True)
    laboratorio: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)

    # ── Bula (o "norte" do catálogo padrão, editável por fazenda) ──
    uso_principal: Optional[str] = None
    concentracao: Optional[str] = None            # ex.: "50 mg/mL", "1%"
    dose_padrao: Optional[float] = None
    unidade_dose: Optional[str] = None            # ml | dose | seringa | unidade
    dose_base: Optional[str] = None               # por_kg_pv | por_animal | por_teto | por_litro_agua
    dose_referencia_kg: Optional[float] = None    # ex.: 1 mL/50 kg → 50
    dose_texto: Optional[str] = None              # texto pronto ("1 mL/50 kg SC")
    via_padrao: Optional[str] = None
    link_bula: Optional[str] = None

    # ── Carência: guardada SEPARADA (leite × carne), exibida num campo único
    #    (ver rules/carencia.formatar_carencia). Nulo = NÃO INFORMADA, nunca
    #    zero: a UI precisa dizer "não informada" em vez de induzir a "liberado".
    carencia_leite_dias: Optional[int] = None
    carencia_carne_dias: Optional[int] = None
    proibido_lactacao: Optional[bool] = None      # não usar em vaca em ordenha
    alerta_gestacao: Optional[bool] = None        # risco de aborto (corticoide, PGF2α)
    alerta: Optional[str] = None                  # texto livre de alerta clínico

    # "Categoria" do medicamento (antimicrobiano, anti-inflamatório,
    # antibiótico... — ver lib/api.ts::CLASSIFICACOES_MEDICAMENTO) — hoje só
    # existia no cadastro de item de estoque do tenant; pedido do usuário
    # (01/09/2026) de trazer o mesmo campo pro cadastro central do Painel
    # CowData, compatibilizando os dois. Espelhado em `Estoque.
    # classificacao_medicamento` pelo fan-out.
    classificacao_medicamento: Optional[str] = None

    # Linha global que esta é cópia de — preenchido só quando a fazenda
    # personaliza o padrão (ver POST /farmacia/indicacoes/{id}/personalizar).
    origem_id: Optional[int] = Field(default=None, foreign_key="medicamento_comercial.id", index=True)


class Doenca(SQLModel, table=True):
    """INDICAÇÃO: o motivo pelo qual se aplica alguma coisa.

    Nasceu como "doença" (mastite, pneumonia) e continua sendo isso por padrão,
    mas `tipo` generaliza para MANEJO — sincronização/IATF, indução de lactação,
    secagem. É o que permite um seletor único de "por que estou aplicando":
    protocolo de indução de lactação mistura hormônio e medicamento, e o
    operador não pode ser obrigado a escolher a categoria antes de achar o que
    usou. O nome da tabela continua `doenca` de propósito — renomear quebraria
    `PrincipioAtivo.doenca_id`, `ProtocoloSanitarioEtapa` gravada por critério
    e o casamento por nome de vacina pré-parto em routers/estoque.py.
    """

    __tablename__ = "doenca"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_doenca_nome_fazenda"),)

    TIPOS: ClassVar[tuple[str, ...]] = ("doenca", "reprodutivo", "produtivo", "preventivo", "suporte")

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    tipo: Optional[str] = Field(default="doenca", index=True)  # ver TIPOS
    descricao: Optional[str] = None
    origem_id: Optional[int] = Field(default=None, foreign_key="doenca.id", index=True)


class IndicacaoTerapeutica(SQLModel, table=True):
    """Vínculo N-para-N entre princípio ativo e doença, com prioridade clínica
    (1 = 1ª escolha, 2 = 2ª opção, ...). Generaliza `PrincipioAtivo.doenca_id`
    (1-para-1, usado só por biológicos) para o caso geral — mesmo antibiótico
    tratando mais de uma doença, mesma doença com várias opções ranqueadas.
    Base do "substituto inteligente": ao faltar o 1º colocado, a 2ª/3ª opção
    aparecem automaticamente no lançamento."""

    __tablename__ = "indicacao_terapeutica"
    # `fazenda_id` entra na unique: sem ele, a 2ª fazenda que personalizasse a
    # mesma indicação batia em IntegrityError (500) na hora de clonar o padrão.
    __table_args__ = (
        UniqueConstraint("principio_ativo_id", "doenca_id", "fazenda_id", name="uq_indicacao_principio_doenca"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    principio_ativo_id: int = Field(foreign_key="principio_ativo.id", index=True)
    doenca_id: int = Field(foreign_key="doenca.id", index=True)
    prioridade: int = 2  # 1 = 1ª escolha, 2 = 2ª opção, 3 = 3ª opção...
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nota: Optional[str] = None  # ressalva clínica ("só com corpo lúteo", etc.)
    origem_id: Optional[int] = Field(default=None, foreign_key="indicacao_terapeutica.id", index=True)


class MedicamentoPrincipioAtivo(SQLModel, table=True):
    """Vínculo N-para-N entre marca comercial e princípio ativo — generaliza
    `MedicamentoComercial.principio_ativo_id` (escalar, obrigatório, mantido
    como o "princípio principal" por compatibilidade com todo o código que já
    lê só ele) para o caso de medicamento combinado (mais de uma molécula na
    mesma bula — ex.: associação antibiótico + anti-inflamatório). Mesmo
    padrão de `IndicacaoTerapeutica` (fazenda_id entra na unique pelo mesmo
    motivo: clonagem por fazenda ao personalizar um medicamento do catálogo)."""

    __tablename__ = "medicamento_principio_ativo"
    __table_args__ = (
        UniqueConstraint("medicamento_comercial_id", "principio_ativo_id", "fazenda_id", name="uq_medicamento_principio_fazenda"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    medicamento_comercial_id: int = Field(foreign_key="medicamento_comercial.id", index=True)
    principio_ativo_id: int = Field(foreign_key="principio_ativo.id", index=True)
    # Espelha (e mantém sincronizado com) MedicamentoComercial.principio_ativo_id
    # — exatamente 1 linha por medicamento tem principal=True.
    principal: bool = False
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    origem_id: Optional[int] = Field(default=None, foreign_key="medicamento_principio_ativo.id", index=True)


class Laboratorio(SQLModel, table=True):
    """Catálogo de laboratórios/fabricantes de medicamento — Configurações
    (Painel CowData) > Farmácia > Cadastrar > Laboratórios. Mesmo padrão
    "nome + ativo" global/por-fazenda de CategoriaEstoque (models/estoque.py).
    `MedicamentoComercial.laboratorio`/`Estoque.laboratorio` continuam texto
    livre (pedido do usuário, 01/09/2026: "puxe o padrão do que já há
    cadastrado no painel CowData") — este catálogo só alimenta o seletor,
    não substitui o dado já gravado."""

    __tablename__ = "laboratorio"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_laboratorio_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class CategoriaMedicamento(SQLModel, table=True):
    """"Categoria (medicamento)" — antimicrobiano, anti-inflamatório,
    antibiótico... (a classificação médica que o usuário chama de
    "categoria", para não confundir com `CategoriaEstoque`, a lista geral de
    Administrativo/Alim. Animal/Sêmen/etc. — ver Estoque.categoria). Nasce
    semeada com os 7 valores hoje fixos em lib/api.ts::CLASSIFICACOES_MEDICAMENTO
    (seed em rules/farmacia.py::seed_farmacia), mas o Painel CowData pode
    cadastrar mais. Cumulativo (um medicamento pode ter mais de uma) — ver
    `MedicamentoCategoria`/`EstoqueCategoriaMedicamento`."""

    __tablename__ = "categoria_medicamento"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_categoria_medicamento_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ClassificacaoMedicamento(SQLModel, table=True):
    """"Classificação do medicamento" — eixo novo e independente de
    Categoria (medicamento), pedido do usuário (01/09/2026) como item 2.4 da
    hierarquia da Farmácia. Nasce vazio: o Painel CowData cadastra os valores
    que quiser (ex.: controlado, genérico, uso interno/externo). Cumulativo,
    mesmo padrão de CategoriaMedicamento."""

    __tablename__ = "classificacao_medicamento_cad"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_classificacao_medicamento_cad_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MedicamentoCategoria(SQLModel, table=True):
    """Vínculo N-para-N entre marca comercial e CategoriaMedicamento —
    cumulativo (sem "principal": ao contrário de princípio ativo, não há
    hierarquia entre categorias, só a lista completa). O primeiro valor
    escolhido é espelhado em `MedicamentoComercial.classificacao_medicamento`
    (mantido por compatibilidade com quem já lê só o escalar).

    `fazenda_id`: espelha `MedicamentoComercial.fazenda_id` do pai (backfill
    por join, nunca dado independente) — inclusive quando NULO: um vínculo de
    medicamento GLOBAL (catálogo do dono do SaaS, ver
    fazenda/rules/visibilidade.py) tem que continuar global, senão ele
    passaria a "pertencer" à primeira fazenda que o backfill encontrasse e
    sumiria do catálogo global de todas as outras. Sem esta coluna, o motor
    de replicação (que descobre o que copiar por `fazenda_id` presente na
    tabela) não via este vínculo e a Fazenda Teste ficava com o medicamento
    copiado mas sem categoria(s)."""

    __tablename__ = "medicamento_categoria"
    __table_args__ = (UniqueConstraint("medicamento_comercial_id", "categoria_medicamento_id", name="uq_medicamento_categoria"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    medicamento_comercial_id: int = Field(foreign_key="medicamento_comercial.id", index=True)
    categoria_medicamento_id: int = Field(foreign_key="categoria_medicamento.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class MedicamentoClassificacao(SQLModel, table=True):
    """Vínculo N-para-N entre marca comercial e ClassificacaoMedicamento —
    mesmo espírito de MedicamentoCategoria, sem espelho escalar (eixo novo,
    sem leitor pré-existente). `fazenda_id`: mesma regra de espelhar o pai
    (`MedicamentoComercial.fazenda_id`), inclusive nulo para medicamento
    GLOBAL — ver docstring de `MedicamentoCategoria` acima."""

    __tablename__ = "medicamento_classificacao"
    __table_args__ = (UniqueConstraint("medicamento_comercial_id", "classificacao_medicamento_id", name="uq_medicamento_classificacao"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    medicamento_comercial_id: int = Field(foreign_key="medicamento_comercial.id", index=True)
    classificacao_medicamento_id: int = Field(foreign_key="classificacao_medicamento_cad.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class EstoqueCategoriaMedicamento(SQLModel, table=True):
    """Espelho de MedicamentoCategoria no lado do item de Estoque do
    tenant — propagado pelo fan-out, editável depois pelo tenant.

    `fazenda_id`: ao contrário do espelho em MedicamentoCategoria, aqui o pai
    (`Estoque`) é sempre dado do tenant (nunca catálogo global) — espelha
    `Estoque.fazenda_id` no backfill. Mesma razão de existir: sem ela, a
    replicação Fazenda -> Fazenda não enxergava este vínculo."""

    __tablename__ = "estoque_categoria_medicamento"
    __table_args__ = (UniqueConstraint("estoque_id", "categoria_medicamento_id", name="uq_estoque_categoria_medicamento"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    estoque_id: int = Field(foreign_key="estoque.id", index=True)
    categoria_medicamento_id: int = Field(foreign_key="categoria_medicamento.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class EstoqueClassificacaoMedicamento(SQLModel, table=True):
    """Espelho de MedicamentoClassificacao no lado do item de Estoque do
    tenant. `fazenda_id`: mesma regra de EstoqueCategoriaMedicamento acima
    (espelha `Estoque.fazenda_id`, sempre de tenant, nunca nulo por origem
    global)."""

    __tablename__ = "estoque_classificacao_medicamento"
    __table_args__ = (UniqueConstraint("estoque_id", "classificacao_medicamento_id", name="uq_estoque_classificacao_medicamento"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    estoque_id: int = Field(foreign_key="estoque.id", index=True)
    classificacao_medicamento_id: int = Field(foreign_key="classificacao_medicamento_cad.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ChecklistTemplateItem(SQLModel, table=True):
    """Item padrão do checklist do protocolo CURATIVO (tipo "curativo"),
    global (`fazenda_id` nulo) ou personalizado pela fazenda. Sem linha
    nenhuma, vale o padrão em código (rules/checklist_curativo.py).

    As linhas "vacina"/"exame" eram do sanitário preventivo antigo e foram
    arquivadas em 2026 (migração s0a1r2q3v4o5, schema arquivo_sanitario_2026)."""

    __tablename__ = "checklist_template_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str = Field(index=True)  # "curativo"
    nome: str
    # Item adicionado pelo usuário nasce "custom", sem comportamento especial;
    # renomear um item canônico não muda a chave.
    chave: str = "custom"
    ordem: int = 0
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ServicoCadastro(SQLModel, table=True):
    """
    Serviço cadastrável para lançamento financeiro (ex.: manutenção de trator,
    frete, quilometragem) — distinto do modelo `Servico` (serviço/IA reprodutivo).
    """

    __tablename__ = "servico_cadastro"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_servico_cadastro_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Protocolo sanitário — cadastro (Configurações > Cadastro > Sanitário) de um
# tratamento com múltiplas etapas (produto/dosagem/via por dia), a exemplo do
# tratamento de mastite. Dias podem começar em D0 ou D1 conforme o protocolo
# cadastrado (mesmo padrão de dia_inicial usado em ProtocoloInducaoLactacao).
# ---------------------------------------------------------------------------
class ProtocoloSanitario(SQLModel, table=True):
    """Um protocolo sanitário cadastrado (ex.: Mastite clínica, Vermifugação padrão)."""

    __tablename__ = "protocolo_sanitario"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_protocolo_sanitario_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")
    eh_mastite: bool = False  # liga o fluxo diferenciado: CMT, teto afetado, classificação
    dia_inicial: int = 0  # 0 (D0) ou 1 (D1) — primeiro dia do cronograma (etapas já existentes usam 1)
    # Curativo (trata um animal já doente — mastite, diarreia, pneumonia…).
    # None = curativo. A opção "preventivo" saiu em 2026: os protocolos que a
    # tinham viraram "curativo" na migração s0a1r2q3v4o5 (nada apagado);
    # vacinas e exames recorrentes moram no módulo novo (sanitario_*).
    finalidade: Optional[str] = None  # "curativo" (o "preventivo" saiu em 2026; vacinas/exames moram em sanitario_*)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloSanitarioEtapa(SQLModel, table=True):
    """Uma linha do protocolo — produto, dosagem, via e dia de aplicação (dia bruto; o
    rótulo exibido é dia - dia_inicial do protocolo)."""

    __tablename__ = "protocolo_sanitario_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_sanitario.id")
    dia: int  # 0, 1, 2... conforme dia_inicial do protocolo
    # Como o medicamento é definido: "medicamento" (produto = item de estoque,
    # aplicação já definida), "principio_ativo" ou "classificacao" (produto
    # guarda o critério; o medicamento real é escolhido no lançamento).
    criterio_tipo: str = Field(default="medicamento")
    produto: str  # nome do medicamento OU o valor do critério (princípio/classificação)
    # Onda "Protocolo à Mostra" — dose FIXA (padrão, é o legado inteiro) ou
    # POR PESO VIVO, ver fazenda.rules.dose_protocolo. Nos dois modos
    # `dosagem` é o número e `unidade` é só a unidade de medida ("mL", "UI")
    # — o que muda é a LEITURA: "fixa" usa `dosagem` pronta; "por_peso" lê
    # `dosagem` como a dose A CADA `dose_referencia_kg` de peso vivo do
    # animal (ex.: dosagem=2, dose_referencia_kg=15 → "2 mL a cada 15 kg"),
    # calculada em rules.dose_protocolo.calcular_dose. Mesmo par de campos
    # (dose_padrao/dose_referencia_kg) já usado em MedicamentoComercial —
    # nome igual, mesmo conceito, para não duplicar vocabulário.
    #
    # Todo registro pré-existente nasceu "fixa" com a referência de peso
    # embutida como TEXTO dentro do próprio `unidade` (ex.: "ml / 15kg PV")
    # — nunca calculada. Ver ADR em rules/dose_protocolo.py e o backfill em
    # POST /cadastro/protocolos-sanitarios/dose-migrar (report-first).
    modo_dose: str = Field(default="fixa")  # "fixa" | "por_peso"
    dosagem: float
    unidade: str
    dose_referencia_kg: Optional[float] = None  # só quando modo_dose == "por_peso"
    via: Optional[str] = None
    observacao: Optional[str] = None  # nota livre (ex.: "Se necessário", "10ml por orelha")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloSanitarioLote(SQLModel, table=True):
    """O "cabeçalho" de um lançamento de protocolo sanitário em lote — junta os
    ProtocoloSanitarioLancamento (um por animal) criados na MESMA chamada de
    POST /sanidade/protocolos/lancamentos, no mesmo formato/campos que
    ProtocoloIatfLancamento/ProtocoloInducaoLancamento/etc. usam (nome_protocolo
    já com data, responsavel/observacao, ativo/encerrado_em/encerrado_motivo)
    — é o que permite ao Sanitário entrar em `_ORIGENS_COM_ACAO`
    (central_protocolos.py) e ganhar a mesma grade dia×animal, com
    marcar/desfazer/cancelar/encerrar, que IATF/Indução/Customizado/Lida já
    tinham. Antes deste modelo, cada ProtocoloSanitarioLancamento era uma
    linha solta sem cabeçalho — a Central AGRUPAVA por (protocolo_id,
    data_inicio) só para exibir, sem estado próprio (ver histórico de
    `_linhas_sanitario`); esse agrupamento por coincidência de data confundia
    lançamentos de fato distintos que caíssem no mesmo dia. `lote_id` agora é
    a fonte de verdade do agrupamento, carimbada no momento do lançamento.

    Migração e3ad0b2a1c47 cria esta tabela e faz o backfill do histórico: cada
    ProtocoloSanitarioLancamento existente (não tinha cabeçalho) vira um
    "lote de 1" — decisão deliberadamente conservadora, sem tentar adivinhar
    quais lançamentos antigos "deveriam" ter sido um lote só por coincidirem
    na mesma data (ver docstring da migração)."""

    __tablename__ = "protocolo_sanitario_lote"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_sanitario.id")
    nome_protocolo: str
    data_inicio: date
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    # Ver ProtocoloIatfLancamento.encerrado_em / .ativo — mesma semântica.
    encerrado_em: Optional[date] = Field(default=None)
    encerrado_motivo: Optional[str] = None
    ativo: bool = Field(default=True, index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloSanitarioLancamento(SQLModel, table=True):
    """Aplicação de um protocolo a um animal — gera um evento na Agenda por etapa/dia."""

    __tablename__ = "protocolo_sanitario_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_sanitario.id")
    numero_matriz: str = Field(index=True)
    data_inicio: date
    # Cabeçalho do lote (ver ProtocoloSanitarioLote) — nullable só porque o
    # histórico pré-existente à migração e3ad0b2a1c47 é preenchido em lotes
    # de 1 pela própria migração; todo lançamento novo sempre grava este
    # campo (ver sanidade.lancar_protocolo).
    lote_id: Optional[int] = Field(default=None, foreign_key="protocolo_sanitario_lote.id", index=True)
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    # Campos específicos de mastite — só usados quando o protocolo é de mastite.
    classificacao_mastite: Optional[str] = None  # "clinica" | "subclinica" | "ambiental"
    grau_mastite: Optional[int] = None   # 1, 2 ou 3
    agente: Optional[str] = None         # patógeno identificado (ver AGENTES_MASTITE)
    resultado_cmt: Optional[str] = None  # "-", "+", "++" ou "+++"
    tetos_afetados: Optional[str] = None  # ex.: "AE,PD" — quadrantes: AE/AD/PD/PE
    # Snapshots do animal no momento do caso (preenchidos automaticamente).
    del_no_caso: Optional[int] = None
    ccs_ultima: Optional[float] = None
    # Recidiva: True quando há caso anterior no mesmo teto com intervalo < 20 dias.
    recidiva: Optional[bool] = None
    # Avaliação de cura no último dia do protocolo (marcada pela Agenda).
    curada: Optional[bool] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloSanitarioAplicacao(SQLModel, table=True):
    """
    Uma etapa (dia) de um lançamento de protocolo — vira evento na Agenda;
    ao marcar "realizado", dá baixa automática do produto no Estoque.
    """

    __tablename__ = "protocolo_sanitario_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_sanitario_lancamento.id")
    etapa_id: int = Field(foreign_key="protocolo_sanitario_etapa.id")
    # `dia` e `numero_matriz` são DENORMALIZADOS de ProtocoloSanitarioEtapa.dia
    # e ProtocoloSanitarioLancamento.numero_matriz, gravados uma vez no
    # lançamento (ver sanidade.lancar_protocolo). Só existem para dar a esta
    # tabela o MESMO formato de ProtocoloIatfAplicacao/ProtocoloInducaoAplicacao/
    # ProtocoloCustomizadoAplicacao/LidaAplicacao — todo o código genérico da
    # Central de Protocolos (central_protocolos.py: detalhe, dar_baixa,
    # desfazer_aplicacao, cancelar) lê `.dia` e `.numero_matriz` direto da
    # aplicação, sem saber que Sanitário tem uma camada extra por animal
    # (ProtocoloSanitarioLancamento) que os outros não têm. Nullable só pelo
    # histórico pré-migração e3ad0b2a1c47 (que faz o backfill); lançamento
    # novo sempre preenche os dois.
    dia: Optional[int] = Field(default=None, index=True)
    numero_matriz: Optional[str] = Field(default=None, index=True)
    data_prevista: date
    # Medicamento escolhido no lançamento quando a etapa foi cadastrada por
    # princípio ativo/classificação (None = usa o produto da própria etapa).
    produto: Optional[str] = None
    realizada: bool = False
    data_realizacao: Optional[date] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Protocolo de indução de lactação — cronograma multi-dia (hormônios +
# implante de progesterona + manejo de adaptação à ordenha) para induzir
# lactação em vacas que não vão parir (ex.: doadoras, vacas de descarte com
# valor de produção). Estrutura em 3 camadas, no mesmo espírito do protocolo
# IATF e do protocolo sanitário genérico:
#   catálogo (editável em Configurações > Cadastro) → lançamento (aplica o
#   catálogo a um grupo de animais numa data) → aplicação (uma linha por
#   animal/dia, confirmável na Agenda, com baixa de estoque automática).
# Dias podem começar em D0 ou D1 conforme o protocolo cadastrado.
# ---------------------------------------------------------------------------
class ProtocoloInducaoLactacao(SQLModel, table=True):
    """Um protocolo de indução de lactação cadastrado (o "molde" do cronograma)."""

    __tablename__ = "protocolo_inducao_lactacao"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_protocolo_inducao_lactacao_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    dia_inicial: int = 0  # 0 (D0) ou 1 (D1) — primeiro dia do cronograma
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloInducaoLactacaoEtapa(SQLModel, table=True):
    """
    Uma linha do cronograma-molde: um medicamento, o implante de progesterona
    (colocar/retirar) ou uma ação de manejo (ex.: "Adaptação na ordenha") num
    dia do protocolo. Vários itens podem coexistir no mesmo dia.
    """

    __tablename__ = "protocolo_inducao_lactacao_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_inducao_lactacao.id", index=True)
    dia: int  # 0, 1, 2... conforme dia_inicial do protocolo
    tipo: str = Field(default="medicamento")  # "medicamento" | "dispositivo" | "manejo"
    principio_ativo_id: Optional[int] = Field(default=None, foreign_key="principio_ativo.id")
    produto: str  # nome do princípio (medicamento) OU "Implante de Progesterona" OU a ação de manejo
    acao_dispositivo: Optional[str] = None  # "colocar" | "retirar" — só para tipo="dispositivo"
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloInducaoLancamento(SQLModel, table=True):
    """Um lançamento do protocolo em lote — o "cabeçalho" (protocolo + data do 1º dia)."""

    __tablename__ = "protocolo_inducao_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_inducao_lactacao.id")
    nome_protocolo: str
    data_d0: date  # data do dia_inicial do protocolo (D0 ou D1)
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    # Ver ProtocoloIatfLancamento.encerrado_em / .ativo — mesma semântica.
    encerrado_em: Optional[date] = Field(default=None)
    encerrado_motivo: Optional[str] = None
    ativo: bool = Field(default=True, index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloInducaoMedicamento(SQLModel, table=True):
    """
    Medicamento(s) do dia, congelados no momento do lançamento (a partir da
    etapa-molde) — igual ao hormônio do protocolo IATF. Editar o catálogo
    depois não altera lançamentos já feitos.
    """

    __tablename__ = "protocolo_inducao_medicamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_inducao_lancamento.id", index=True)
    dia: int
    produto: str
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ProtocoloInducaoAplicacao(SQLModel, table=True):
    """
    Uma etapa (dia) de um animal dentro de um lançamento — vira evento na
    Agenda; ao marcar "realizado", dá baixa automática do(s) produto(s) do
    dia. `observacao_manejo` é o texto que o funcionário vê na Agenda para as
    ações sem medicamento (colocar/retirar implante, adaptação na ordenha,
    iniciar a ordenha).
    """

    __tablename__ = "protocolo_inducao_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_inducao_lancamento.id")
    numero_matriz: str = Field(index=True)
    dia: int
    descricao: str  # medicamentos do dia (auto), ex.: "20 ml Benzoato de Estradiol"
    observacao_manejo: Optional[str] = None
    data_prevista: date
    realizada: bool = False
    data_realizacao: Optional[date] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class TouroAtivadoFazenda(SQLModel, table=True):
    """Touro INATIVO no catálogo NAAB que uma fazenda decidiu usar mesmo
    assim (comprar, aplicar, selecionar). Não altera o catálogo global."""

    __tablename__ = "touro_ativado_fazenda"
    __table_args__ = (UniqueConstraint("fazenda_id", "touro_id", name="uq_touro_ativado_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    touro_id: int = Field(foreign_key="touro.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Touro(SQLModel, table=True):
    """Catálogo genético de touros (provas do fornecedor / NAAB-CDCB). Guarda o
    código NAAB, nome e as provas (produção, índices econômicos, tipo/saúde) —
    importado do catálogo Excel/CSV do fornecedor a cada rodada de prova. Usado
    para mostrar o pai com nome + provas na ficha do animal."""

    __tablename__ = "touro"

    id: Optional[int] = Field(default=None, primary_key=True)
    naab: str = Field(index=True, unique=True)  # código NAAB (ex.: 7HO12345)
    nome: Optional[str] = None
    nome_completo: Optional[str] = None
    raca: Optional[str] = None
    central: Optional[str] = None
    # Produção (PTAs)
    leite_kg: Optional[float] = None
    gordura_kg: Optional[float] = None
    gordura_pct: Optional[float] = None
    proteina_kg: Optional[float] = None
    proteina_pct: Optional[float] = None
    # Índices econômicos
    tpi: Optional[float] = None
    nm_dolar: Optional[float] = None  # Net Merit $ (ou índice econômico equivalente)
    # Tipo e saúde
    tipo_composto: Optional[float] = None      # PTAT / composto de conformação
    ubere_composto: Optional[float] = None     # UDC — composto de úbere
    pernas_composto: Optional[float] = None    # FLC — pernas e pés
    ccs_score: Optional[float] = None          # SCS — células somáticas
    fertilidade_filhas: Optional[float] = None # DPR / fertilidade
    facilidade_parto: Optional[float] = None   # SCE/DCE — facilidade de parto
    # Metadados
    fonte: Optional[str] = None       # ABS, Alta, Select Sires, CRV, manual...
    rodada_prova: Optional[str] = None  # ex.: "Abr/2026"
    observacao: Optional[str] = None
    # Catálogo global: False = touro que saiu da lista de comercializados da
    # NAAB (arquivo AISS), mas cujo sêmen ainda pode circular no mercado.
    # Cada fazenda pode ativá-lo para uso próprio (`TouroAtivadoFazenda`).
    ativo: bool = Field(default=True, sa_column_kwargs={"server_default": "1"})
    # Dados brutos da planilha do fornecedor além dos campos curados acima —
    # JSON com lista [[rótulo original, valor], ...], na ordem da planilha.
    # Garante que nenhuma coluna do catálogo se perca mesmo quando o fornecedor
    # usa nomes de campo que não têm um equivalente curado no modelo.
    dados_extra: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
