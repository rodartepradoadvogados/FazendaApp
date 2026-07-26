"""
Estoque — itens de estoque, fornecedores, movimentos e estoque/compra de sêmen.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Estoque
# ---------------------------------------------------------------------------
class Estoque(SQLModel, table=True):
    """Item de estoque do ESTOQUE.csv."""

    __tablename__ = "estoque"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    categoria: Optional[str] = None
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
    carencia_dias: Optional[int] = None  # período de carência (leite/carne) após uso, em dias
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
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Vínculo opcional ao Pedido de compra que esta entrada física está
    # atendendo — é só quando esse vínculo existe que o Pedido passa a
    # refletir em Estoque (ver Pedido/PedidoItem).
    pedido_id: Optional[int] = Field(default=None, foreign_key="pedido.id")
    pedido_item_id: Optional[int] = Field(default=None, foreign_key="pedido_item.id")


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
