"""
Estoque — itens de estoque, fornecedores, movimentos e estoque/compra de sêmen.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

# ---------------------------------------------------------------------------
# Estoque
# ---------------------------------------------------------------------------
class Estoque(SQLModel, table=True):
    """Item de estoque do ESTOQUE.csv."""

    __tablename__ = "estoque"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    categoria: Optional[str] = None
    # Vínculo direto com CategoriaAlimento (Configurações > Cadastro >
    # Alimentação > Categorias) — Fase P1 do refactor Alimento/Estoque.
    # Distinto de `categoria` acima (texto livre, sem FK) e de
    # `Alimento.categoria_alimento_id` (categoria do CONCEITO nutricional):
    # este campo deixa um item de Estoque ser categorizado sem precisar
    # primeiro passar pelo cadastro de Alimento — ver PUT
    # /alimentacao/estoque/{estoque_id}/categoria. Puramente aditivo: a
    # categorização indireta via Alimento continua funcionando do mesmo
    # jeito (ver seção `produtos_sem_categoria` do relatório de conferência).
    categoria_alimento_id: Optional[int] = Field(default=None, foreign_key="categoria_alimento.id")
    # Finalidade de uso do item — distinta de `categoria` (texto livre): um
    # enum fechado (ver rules.categorias.FINALIDADES_ESTOQUE) que decide se o
    # item pode aparecer nos seletores de "aplicação de medicamento"/hormônio
    # (Medicamento) ou fica de fora deles (Ração/Alimento, Material/Insumo,
    # Equipamento, Outro). Sêmen não usa este campo — vive em EstoqueSemen.
    finalidade: Optional[str] = None
    numero_produto: Optional[str] = None
    nome: str = Field(index=True)
    # Metadados de medicamento — permitem cadastrar/protocolar por princípio
    # ativo ou por classificação (antimicrobiano, anti-inflamatório, antibiótico…)
    # e, na hora de aplicar, listar os medicamentos que cumprem o requisito.
    principio_ativo: Optional[str] = None
    classificacao_medicamento: Optional[str] = None
    # Vínculo relacional com a farmácia (hierarquia = princípio ativo). O texto
    # `principio_ativo` acima é mantido para histórico/compatibilização.
    principio_ativo_id: Optional[int] = Field(default=None, foreign_key="principio_ativo.id")
    medicamento_comercial_id: Optional[int] = Field(default=None, foreign_key="medicamento_comercial.id")
    laboratorio: Optional[str] = None
    # Unificação de volumes: tamanho de UMA apresentação (frasco/pote/seringa) e
    # sua unidade. Ex.: frasco de 250 → volume_por_apresentacao=250, volume_unidade="ml".
    # O nº de apresentações em estoque = quantidade / volume_por_apresentacao.
    volume_por_apresentacao: Optional[float] = None
    volume_unidade: Optional[str] = None
    # Gatilho de comunicação: enquanto False, aplicações/dietas NÃO baixam este
    # item (só registram o manejo) e um alerta pede o estoque inicial. None =
    # item legado (já em uso) — tratado como inicializado para não quebrar baixas.
    estoque_inicializado: Optional[bool] = None
    quantidade: Optional[float] = None
    estoque_minimo: Optional[float] = None
    unidade: Optional[str] = None
    valor_unitario: Optional[float] = None
    valor_total: Optional[float] = None
    abaixo_minimo: Optional[bool] = None
    local_armazenamento: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)

    # Metadados de cadastro (Configurações > Cadastro), usados pela Alimentação
    # para converter kg necessários em sacos/potes/fardos quando o item é
    # embalado (ex.: "saca" de 30kg -> unidade_embalagem="saca",
    # medida_embalagem="kg/saca", quantidade_embalagem=30). Distinto do campo
    # `unidade` acima, que é a unidade de estoque usada em toda baixa/consumo.
    unidade_embalagem: Optional[str] = None  # saca, pote, frasco, pacote, bag, fardo, garrafa, unidade
    medida_embalagem: Optional[str] = None  # kg/saca, litros/garrafa, mililitros/frasco, unidades/fardo, potes/caixa, unidades
    quantidade_embalagem: Optional[float] = None
    fornecedor_id: Optional[int] = Field(default=None, foreign_key="fornecedor.id")  # fornecedor principal

    # Cadastro completo de item (Configurações > Cadastro > Itens de estoque).
    # Booleanos ficam Optional (None = valor não definido ainda, ex.: itens
    # antigos vindos do ESTOQUE.csv antes deste cadastro existir) — None é
    # tratado como "não desativado"/"não pediu lembrete", nunca como erro.
    ativo: Optional[bool] = None
    observacao: Optional[str] = None
    carencia_dias: Optional[int] = None  # período de carência (leite/carne) após uso, em dias — legado, ver split abaixo
    # Split leite/carne (compatibiliza com MedicamentoComercial.carencia_leite_dias/
    # carencia_carne_dias — ver rules/carencia.py) + flag "não usar em vaca em
    # lactação", pedido do usuário (01/09/2026) junto da carência do leite.
    # `carencia_dias` acima continua existindo por compatibilidade com quem já lê
    # esse campo; estes dois passam a ser a fonte de verdade a partir de agora.
    carencia_leite_dias: Optional[int] = None
    carencia_carne_dias: Optional[int] = None
    proibido_lactacao: Optional[bool] = None
    centro_custo_padrao: Optional[str] = None
    conta_gerencial_despesa_padrao: Optional[str] = None  # código do plano de contas (ex.: "3.01.01.01")
    conta_gerencial_receita_padrao: Optional[str] = None
    # True = produto que gera receita (venda: leite, animal, esterco...). Classifica
    # o item para relatórios de receita e para a conta gerencial de receita padrão.
    gera_receita: Optional[bool] = None
    exibir_necessidade_compra_agenda: Optional[bool] = None  # abaixo do mínimo -> lembrete na Agenda
    # None/True = estocável (item real de estoque, participa de baixa automática
    # por aplicação/consumo e pode ser doado/recebido de cortesia). False = item
    # cadastrado só para lançamento financeiro (produto de nota), sem controle de quantidade.
    estocavel: Optional[bool] = None
    # True = item de patrimônio (ex.: trator, benfeitoria) — uma compra desse
    # item no lançamento financeiro sugere vincular/criar um registro em
    # Controle Financeiro > Patrimônio (ver ContaGerencial.patrimonio_id e
    # fazenda/api/routers/financeiro.py). Nada a ver com estocável/gera_receita.
    gera_patrimonio: Optional[bool] = None
    # Campo legado — a elegibilidade do custo físico do RMCA (ver GET
    # /financeiro/rmca) hoje é decidida por `conta_gerencial_despesa_padrao`
    # (conta "3.01.01" — Alimentação do rebanho — ou qualquer conta dentro
    # dela), não mais por esta flag. Mantido só para não perder dados antigos;
    # não é mais lido nem editável via Configurações > Cadastro > Itens de estoque.
    considerar_rmca: Optional[bool] = None
    # A partir desta data o item passa a ter controle de estoque; movimentos e
    # lançamentos ANTERIORES a ela não repercutem no saldo/custo (só faz sentido
    # para itens estocáveis). None = sem recorte (considera tudo).
    data_inicio_controle: Optional[date] = None
    # Vínculo com o cadastro de Alimento (Configurações > Cadastro > Alimentação
    # > Alimentos) — um item de estoque só pode estar linkado a UM alimento
    # (campo escalar), mas um alimento pode ter vários itens de estoque
    # apontando para ele (ex.: "Silagem de milho" comprada de fornecedores
    # diferentes, cada um seu próprio item de estoque). Usado para resolver
    # a "necessidade mensal" por vínculo real em vez de casar nomes.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")
    # Vínculo com o Estoque de Sêmen (Configurações > Cadastro > Central de
    # Sêmen) — quando um item de estoque genérico representa doses de um touro
    # (comprado por nota fiscal e cadastrado aqui, e não direto em
    # EstoqueSemen), ligar os dois faz toda entrada/saída deste item também
    # atualizar `EstoqueSemen.doses` (ver `_criar_movimento_estoque`), casado
    # automaticamente por nome do touro/NAAB quando possível.
    estoque_semen_id: Optional[int] = Field(default=None, foreign_key="estoque_semen.id")
    # Sexado/convencional do item de estoque quando ele representa doses de
    # sêmen (categoria "Sêmen e genética") — mesmo vocabulário de
    # EstoqueSemen.tipo/CompraSemen.tipo, mas cadastrável aqui direto (antes só
    # existia na compra de sêmen). None = não é sêmen ou ainda não informado.
    tipo_semen: Optional[str] = None


class EstoquePrincipioAtivo(SQLModel, table=True):
    """Vínculo N-para-N entre item de Estoque (do tenant) e princípio ativo —
    generaliza `Estoque.principio_ativo_id` (escalar, mantido como o
    "princípio principal" por compatibilidade) para medicamento combinado.
    Sem `fazenda_id` próprio: sempre herda a fazenda do `Estoque` referenciado
    (que já é dado por-tenant, ao contrário do catálogo global de Farmácia)."""

    __tablename__ = "estoque_principio_ativo"
    __table_args__ = (UniqueConstraint("estoque_id", "principio_ativo_id", name="uq_estoque_principio"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    estoque_id: int = Field(foreign_key="estoque.id", index=True)
    principio_ativo_id: int = Field(foreign_key="principio_ativo.id", index=True)
    # Espelha (e mantém sincronizado com) Estoque.principio_ativo_id — exatamente
    # 1 linha por item tem principal=True.
    principal: bool = False
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class EstoqueAliasMesclado(SQLModel, table=True):
    """Registro de mesclagem de itens de Estoque (ver POST
    /estoque/{sobrevivente_id}/mesclar): o item "perdedor" NÃO é excluído nem
    seu nome é reescrito por cima do histórico (Sanidade.produto, protocolos,
    financeiro...) — isso apagaria a carência que valia para aquele
    lançamento no passado (duas marcas do mesmo princípio podem ter carências
    diferentes; ver docstring de MedicamentoComercial em models/sanidade.py).
    Em vez disso, o nome antigo vira um ALIAS que aponta pro item
    sobrevivente, com a carência do perdedor CONGELADA no momento da
    mesclagem — quem hoje resolve item/carência por nome (ver
    rules/estoque_baixa.py) passa a também consultar esta tabela antes de
    concluir que o item "sumiu"."""

    __tablename__ = "estoque_alias_mesclado"
    __table_args__ = (UniqueConstraint("fazenda_id", "nome_perdedor", name="uq_alias_mesclado_fazenda_nome"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome_perdedor: str = Field(index=True)
    estoque_perdedor_id: int = Field(foreign_key="estoque.id", index=True)
    estoque_sobrevivente_id: int = Field(foreign_key="estoque.id", index=True)
    carencia_leite_dias_congelada: Optional[int] = None
    carencia_carne_dias_congelada: Optional[int] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Cadastros de apoio ao item de estoque — Local de Armazenamento, Categoria,
# Finalidade, Unidade, Unidade (embalagem) e Unidade de Medida (Configurações
# > Cadastro > Estoque). Antes eram listas fixas em Python/TypeScript
# (CATEGORIAS_ESTOQUE, FINALIDADES_ESTOQUE, UNIDADES, UNIDADES_EMBALAGEM,
# MEDIDAS_EMBALAGEM) ou texto livre sem sugestão (local_armazenamento) — agora
# cadastráveis, mesmo padrão "nome + ativo" de Raça/MotivoBaixa (ver
# fazenda.api.routers.cadastro._comum._crud_nome_ativo). `Estoque.categoria`
# etc. continuam guardando o NOME como texto (igual a `centro_custo_padrao`),
# não uma FK — o cadastro só alimenta o seletor de preenchimento, sem exigir
# migração de dado já existente.
# ---------------------------------------------------------------------------
class LocalArmazenamento(SQLModel, table=True):
    __tablename__ = "local_armazenamento"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_local_armazenamento_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class CategoriaEstoque(SQLModel, table=True):
    __tablename__ = "categoria_estoque"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_categoria_estoque_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FinalidadeEstoque(SQLModel, table=True):
    __tablename__ = "finalidade_estoque"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_finalidade_estoque_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class UnidadeEstoque(SQLModel, table=True):
    __tablename__ = "unidade_estoque"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_unidade_estoque_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class UnidadeEmbalagemEstoque(SQLModel, table=True):
    __tablename__ = "unidade_embalagem_estoque"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_unidade_embalagem_estoque_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class UnidadeMedidaEmbalagemEstoque(SQLModel, table=True):
    __tablename__ = "unidade_medida_embalagem_estoque"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_unidade_medida_embalagem_estoque_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Fornecedor / fabricante / cliente
# ---------------------------------------------------------------------------
class Fornecedor(SQLModel, table=True):
    """Cadastro de fornecedores, fabricantes e clientes (Configurações > Cadastro)."""

    __tablename__ = "fornecedor"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    tipo: str  # "fornecedor" | "fabricante" | "cliente"
    categoria: Optional[str] = None  # ver CATEGORIAS_FORNECEDOR em fazenda.rules.categorias
    cnpj_cpf: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FornecedorClienteApelido(SQLModel, table=True):
    """Apelido aprendido: o nome de fornecedor/cliente como aparece BRUTO num
    documento (razão social completa da NF-e, texto lido por OCR) nem sempre
    bate com o nome do cadastro (ex.: nota vem com "COOP.AGRO.PROD.R.S.
    GOIANO - COMIGO", cadastro tem só "COMIGO"). Quando a leitura automática
    de documento não encontra correspondência exata no cadastro (ver
    fazenda.rules.casamento_cadastro), o usuário pode ensinar o sistema a
    reconhecer aquele nome bruto — da próxima vez, resolve direto para
    `nome_canonico`, sem precisar corrigir de novo.

    Por fazenda — o apelido de um tenant nunca pode resolver o nome de outro
    (mesmo texto bruto pode significar fornecedores diferentes em fazendas
    diferentes)."""

    __tablename__ = "fornecedor_cliente_apelido"
    __table_args__ = (UniqueConstraint("nome_bruto", "fazenda_id", name="uq_apelido_nome_bruto_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    # Normalizado (mesma função de fazenda.rules.casamento_cadastro) antes de
    # gravar e antes de comparar — evita duplicar apelido por causa de
    # diferença de maiúscula/acento/espaço.
    nome_bruto: str = Field(index=True)
    nome_canonico: str
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Movimento de estoque (histórico de entradas/saídas lançadas manualmente)
# ---------------------------------------------------------------------------
class MovimentoEstoque(SQLModel, table=True):
    """Uma entrada ou saída de estoque lançada em Lançamentos > Estoque."""

    __tablename__ = "movimento_estoque"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome_item: str = Field(index=True)
    movimento: str  # "Aplicação" | "Saída de ajuste" | "Entrada de ajuste" | "Entrada de cortesia" | "Doação"
    quantidade: float
    unidade: Optional[str] = None
    data_movimento: date
    observacao: Optional[str] = None
    # Preço do item NO MOMENTO deste movimento (snapshot de Estoque.valor_unitario
    # ao gravar) — sem isso, o custo físico do RMCA (rules/rmca.py) multiplicava
    # todo o histórico pelo preço ATUAL do item, reescrevendo retroativamente o
    # custo de meses cujo preço já mudou. None em movimentos antigos (de antes
    # desta coluna existir) — quem lê cai no preço atual como aproximação.
    valor_unitario: Optional[float] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Vínculo opcional ao Pedido de compra que esta entrada física está
    # atendendo — é só quando esse vínculo existe que o Pedido passa a
    # refletir em Estoque (ver Pedido/PedidoItem).
    pedido_id: Optional[int] = Field(default=None, foreign_key="pedido.id")
    pedido_item_id: Optional[int] = Field(default=None, foreign_key="pedido_item.id")
    # Vínculo relacional com o item de estoque (ver fazenda.rules.estoque_baixa)
    # — até aqui o único vínculo era o TEXTO `nome_item`, que quebra se o item
    # for renomeado. None em movimentos antigos (backfill best-effort por nome
    # dentro da mesma fazenda, ver migração) ou quando o item não foi
    # encontrado no momento do lançamento.
    estoque_id: Optional[int] = Field(default=None, foreign_key="estoque.id", index=True)
    # De onde veio esta baixa/devolução — ex.: "sanidade", "protocolo_sanitario",
    # "iatf", "inducao", "secagem", "vacina_pre_parto", "bst", "ia_semen",
    # "alimentacao". None = lançamento manual (POST /estoque/movimentar) ou
    # importação de CSV.
    origem_tipo: Optional[str] = None
    # Id do lançamento (Sanidade, ProtocoloSanitarioAplicacao, Servico...) que
    # gerou este movimento — junto de `origem_tipo`, dá o rastro completo.
    origem_id: Optional[int] = None


class EstoqueSemen(SQLModel, table=True):
    """Estoque de doses de sêmen por touro — usado no relatório de manejo
    'Estoque de sêmen'. Distinto de Estoque (insumos) e de Animal(eh_semen),
    que é só o catálogo do touro sem contagem de doses."""

    __tablename__ = "estoque_semen"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    touro_nome: str = Field(index=True)
    codigo: Optional[str] = None
    naab: Optional[str] = None  # código NAAB do touro (ex.: 7HO12345)
    central: Optional[str] = None  # central de genética (ex.: ABS, Alta, Semex)
    tipo: str = "convencional"  # convencional | sexado | fazenda
    doses: int = 0
    valor_unitario: Optional[float] = None  # R$ por dose (para relatório de payback)
    local_armazenamento: Optional[str] = None  # ex.: "Caneca 1"
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class CompraSemen(SQLModel, table=True):
    """Registro de compra de sêmen — igual em espírito a CompraAnimal: o
    efeito financeiro/histórico da aquisição (a conta gerencial rica vive na
    ContaGerencial gerada). Sempre resulta em doses somadas a um EstoqueSemen
    (existente, se `origem="estoque"`, ou criado/casado por NAAB se
    `origem="naab"`) — é o que faz a compra "comunicar com o estoque de
    sêmen" e, por consequência, com os relatórios e a baixa nas aplicações
    de IA (que descontam de EstoqueSemen.doses)."""

    __tablename__ = "compra_semen"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    estoque_semen_id: int = Field(foreign_key="estoque_semen.id", index=True)
    touro_nome: str
    naab: Optional[str] = None
    origem: str  # "estoque" (touro já cadastrado na fazenda) | "naab" (banco de dados NAAB)
    tipo: str = "convencional"  # convencional | sexado — mesma modalidade do EstoqueSemen resultante
    doses: int
    valor_unitario: float  # R$ por dose
    vendedor: str
    data_compra: date
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    numero_lancamento_gerado: Optional[str] = None  # LC-... do lançamento financeiro (ContaGerencial) gerado na compra
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
