"""
Financeiro — contas gerenciais, plano de contas, orçamento/planejamento, pedidos e patrimônio.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

# ---------------------------------------------------------------------------
# Conta Gerencial (Financeiro)
# ---------------------------------------------------------------------------
class ContaGerencial(SQLModel, table=True):
    """Uma movimentação financeira do CONTA_GERENCIAL.csv."""

    __tablename__ = "conta_gerencial"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (ver fazenda/models/multitenant.py):
    # nulo para todo lançamento já existente antes da migração de backfill —
    # ainda não filtra nada sozinho, só os endpoints que já sabem considerar
    # fazenda_id (ver fazenda/api/routers/financeiro.py e os demais routers
    # que também criam ContaGerencial — compra/venda de animal e sêmen, RH).
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_lancamento: Optional[str] = Field(default=None, index=True)  # referência do lançamento (ex.: LC-2026-00001), igual em todas as parcelas
    codigo_conta: Optional[str] = None
    descricao: Optional[str] = None
    data_vencimento: Optional[date] = None
    data_pagamento: Optional[date] = None
    data_competencia: Optional[date] = None
    data_emissao: Optional[date] = None
    data_prevista_entrada: Optional[date] = None
    data_pedido: Optional[date] = None
    entregue: Optional[bool] = None
    fornecedor_cliente: Optional[str] = None
    numero_nota: Optional[str] = None  # número do documento (nota fiscal, recibo, fatura...)
    tipo_documento: Optional[str] = None  # nota fiscal | recibo | folha de pagamento | fatura | contrato
    # Item de consulta À PARTE do número do documento — nº da ordem de serviço
    # (OS) ou do orçamento que originou a compra, quando houver.
    numero_os_orcamento: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    conta_bancaria: Optional[str] = None
    forma_pagamento: Optional[str] = None  # pix | transferencia | boleto | credito
    data_vencimento_cartao: Optional[date] = None  # só quando forma_pagamento == "credito"
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: Optional[float] = None
    valor_pago: Optional[float] = None
    desconto_acrescimo: Optional[float] = None
    parcela_num: Optional[int] = None
    parcela_total: Optional[int] = None
    # Linha digitável/número do boleto DESTA parcela — opcional para o usuário
    # preencher, mas o sistema tenta extrair sozinho ao importar um boleto
    # (ver rules/leitura_documento.py); nunca bloqueia o lançamento se faltar.
    numero_boleto: Optional[str] = None
    responsavel: Optional[str] = None
    centro_custo: Optional[str] = None
    tipo: Optional[str] = None
    origem: Optional[str] = "csv"  # "csv" (upload) | "manual" (lançamento pela tela)
    # Desconto/acréscimo negociado NA NOTA (produtos → valor bruto → líquido pago/recebido).
    # Diferente de desconto_acrescimo acima, que é a diferença apurada só na baixa do pagamento.
    desconto_nota: Optional[float] = None
    acrescimo_nota: Optional[float] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Vínculo opcional ao Pedido que esta nota fiscal/recibo está atendendo —
    # é só quando esse vínculo existe que o Pedido passa a refletir em Financeiro.
    pedido_id: Optional[int] = Field(default=None, foreign_key="pedido.id")


# ---------------------------------------------------------------------------
# Item de lançamento financeiro (produto/serviço) — uma nota pode ter vários
# ---------------------------------------------------------------------------
class LancamentoItem(SQLModel, table=True):
    """Um produto/serviço de um lançamento financeiro manual (várias linhas por nota)."""

    __tablename__ = "lancamento_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda — ver ContaGerencial.fazenda_id
    # acima. Precisa da própria coluna porque o vínculo com ContaGerencial é
    # por numero_lancamento (string), não por id.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_lancamento: str = Field(index=True)
    tipo: Optional[str] = None  # herdado do lançamento (despesa/receita), útil p/ consultas
    data_competencia: Optional[date] = None  # herdado, p/ DRE por conta
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    produto: str
    tipo_item: Optional[str] = None  # "produto" | "servico" — escolha exclusiva no lançamento
    descricao: Optional[str] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: float
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Anexo de lançamento financeiro (ex.: boleto de um parcelamento) — o conteúdo
# fica no próprio banco (bytes), sem depender de disco persistente no deploy.
# ---------------------------------------------------------------------------
class LancamentoAnexo(SQLModel, table=True):
    __tablename__ = "lancamento_anexo"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda — ver ContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_lancamento: str = Field(index=True)
    nome_arquivo: str
    mime_type: str
    tamanho_bytes: int
    conteudo: bytes
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Plano de Contas Gerenciais
# ---------------------------------------------------------------------------
class PlanoContaGerencial(SQLModel, table=True):
    """Hierarquia do plano de contas gerenciais — LISTA_DE_PLANO_DE_CONTAS_GERENCIAIS.csv."""

    __tablename__ = "plano_conta_gerencial"
    __table_args__ = (UniqueConstraint("codigo", "fazenda_id", name="uq_plano_conta_gerencial_codigo_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3B — ver fazenda/models/multitenant.py):
    # nulo para todo item já cadastrado antes da migração de backfill. Trocou
    # o unique(codigo) global por unique(codigo, fazenda_id) — dois tenants
    # podem, cada um, ter sua própria conta "3.01.01", mesmo padrão de
    # centro_custo/sanidade.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    codigo: str = Field(index=True)
    nome: str
    ativa: bool = True
    participa_atividade: Optional[bool] = None
    fluxo: Optional[bool] = None
    tipo_fixo_variavel: Optional[str] = None  # "Fixa" | "Variável"
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)

    # Marcação para o indicador RMCA (Receita Menos Custo com Alimentação) —
    # versão "gerencial", ver Configurações > Parâmetros financeiros.
    rmca_receita_leite: Optional[bool] = None
    rmca_custo_alimentacao: Optional[bool] = None

    # Natureza do lançamento aceito por esta conta — "servico" | "produto" | "ambos".
    # Restringe, em Financeiro > Contas a pagar/a receber, se o item do lançamento
    # pode ser um serviço, um produto, ou os dois (ver FormFinanceiro/SeletorContaGerencial).
    natureza: Optional[str] = None

    # Quando marcado, um lançamento de despesa nesta conta (ex.: 3.03.02.11 —
    # Veterinário/zootecnista) pergunta, ao salvar, se o pagamento deve ser
    # vinculado a uma aplicação de vacina, exame ou visita reprodutiva — ver
    # popup de vínculo sanitário/reprodutivo em FormFinanceiro.
    pede_vinculo_sanitario_reprodutivo: Optional[bool] = None


# ---------------------------------------------------------------------------
# Conta corrente (Configurações > Parâmetros financeiros) — antes era uma
# lista fixa em Python (CONTAS_BANCARIAS); usada em lançamentos/baixas.
# ---------------------------------------------------------------------------
class ContaCorrente(SQLModel, table=True):
    __tablename__ = "conta_corrente"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (ver fazenda/models/multitenant.py):
    # nulo para toda conta cadastrada antes da migração de backfill — ainda
    # não filtra nada sozinho, só os endpoints que já sabem considerar
    # fazenda_id (ver fazenda/api/routers/financeiro.py).
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    banco: str
    agencia: str
    numero_conta: str
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Centro de custo (Configurações > Parâmetros financeiros) — antes era só
# sugestão (distinct dos valores já usados em ContaGerencial.centro_custo).
# ---------------------------------------------------------------------------
class CentroCusto(SQLModel, table=True):
    __tablename__ = "centro_custo"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_centro_custo_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda: nulo para todo centro de custo já
    # cadastrado antes da migração de backfill (ver fazenda/models/multitenant.py).
    # Trocou o unique(nome) global por unique(nome, fazenda_id) — dois
    # tenants podem, cada um, ter seu próprio "Pecuária Leiteira".
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Tipo de documento e forma de pagamento (Configurações > Parâmetros
# financeiros) — antes eram listas fixas em Python (TIPOS_DOCUMENTO,
# FORMAS_PAGAMENTO em fazenda.api.routers.financeiro); agora cadastráveis,
# no mesmo padrão de CentroCusto/ContaCorrente.
# ---------------------------------------------------------------------------
class TipoDocumento(SQLModel, table=True):
    __tablename__ = "tipo_documento"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_tipo_documento_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3B) — ver PlanoContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FormaPagamentoCadastro(SQLModel, table=True):
    __tablename__ = "forma_pagamento_cadastro"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_forma_pagamento_cadastro_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3B) — ver PlanoContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Orçamento (Financeiro > Planejamento > Orçamento) — uma linha por
# ano/mês/conta gerencial/centro de custo. Comparado contra o realizado
# (ContaGerencial/LancamentoItem já existentes) para o relatório orçado x
# realizado; não tem efeito nenhum sobre Estoque nem sobre lançamentos.
# ---------------------------------------------------------------------------
class OrcamentoItem(SQLModel, table=True):
    __tablename__ = "orcamento_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3C) — ver PlanoContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    ano: int = Field(index=True)
    mes: int  # 1-12
    codigo_conta_gerencial: str
    centro_custo: Optional[str] = None
    tipo: str  # "receita" | "despesa"
    valor_orcado: float
    observacao: Optional[str] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Planejamento financeiro (Financeiro > Planejamento > Planejamento
# financeiro) — cenários de simulação (otimista/realista/pessimista ou
# personalizado) com linhas de receita/despesa projetadas mês a mês, para
# montar uma projeção de fluxo de caixa "e se". Também sem efeito sobre
# Estoque/lançamentos — é só simulação.
# ---------------------------------------------------------------------------
class PlanejamentoCenario(SQLModel, table=True):
    __tablename__ = "planejamento_cenario"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3C) — ver PlanoContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str
    tipo: str = "personalizado"  # "otimista" | "realista" | "pessimista" | "personalizado"
    observacao: Optional[str] = None
    ativo: bool = True
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class PlanejamentoItem(SQLModel, table=True):
    __tablename__ = "planejamento_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3C) — ver PlanoContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    cenario_id: int = Field(foreign_key="planejamento_cenario.id", index=True)
    mes_competencia: str  # "YYYY-MM"
    codigo_conta_gerencial: str
    centro_custo: Optional[str] = None
    tipo: str  # "receita" | "despesa"
    valor_previsto: float
    observacao: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Pedidos — intenção de compra/venda que NÃO mexe em Estoque nem gera
# lançamento financeiro sozinha; só quando uma nota fiscal/recibo é lançada
# em Financeiro (ou uma entrada/saída em Estoque) e vinculada a este pedido é
# que ele passa a refletir nesses dois módulos (ver `pedido_id` em
# ContaGerencial e MovimentoEstoque, mais abaixo).
# ---------------------------------------------------------------------------
class Pedido(SQLModel, table=True):
    __tablename__ = "pedido"
    __table_args__ = (UniqueConstraint("numero_pedido", "fazenda_id", name="uq_pedido_numero_pedido_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3C) — ver PlanoContaGerencial.fazenda_id
    # acima. numero_pedido é só um rótulo de exibição (o vínculo real com
    # PedidoItem é por pedido_id, FK), então pode virar unique(numero_pedido,
    # fazenda_id) sem o mesmo risco de colisão do numero_lancamento do
    # Financeiro (esse fica global de propósito — ver ContaGerencial).
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_pedido: str = Field(index=True)
    tipo: str  # "compra" | "venda"
    fornecedor_cliente: Optional[str] = None
    centro_custo: Optional[str] = None
    data_pedido: date
    data_prevista: Optional[date] = None
    status: str = "aberto"  # "aberto" | "parcialmente_atendido" | "atendido" | "cancelado"
    observacao: Optional[str] = None
    responsavel: Optional[str] = None
    # Rastro de onde este pedido nasceu, se veio de "Importar para Pedidos"
    # em Orçamento/Planejamento financeiro (ver planejamento.py).
    origem_tipo: Optional[str] = None  # "orcamento" | "planejamento_financeiro"
    origem_item_id: Optional[int] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class PedidoItem(SQLModel, table=True):
    __tablename__ = "pedido_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3C) — ver PlanoContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    pedido_id: int = Field(foreign_key="pedido.id", index=True)
    tipo_item: str  # "produto" | "servico"
    produto_servico: str
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    quantidade: Optional[float] = None
    valor_unitario_estimado: Optional[float] = None
    valor_total_estimado: float
    # Quanto desse item já foi coberto por lançamentos/movimentos vinculados.
    quantidade_atendida: float = 0
    valor_atendido: float = 0


# ---------------------------------------------------------------------------
# Patrimônio
# ---------------------------------------------------------------------------
class Patrimonio(SQLModel, table=True):
    """Item de patrimônio/imobilizado — LISTA_DE_PATRIMONIO.csv."""

    __tablename__ = "patrimonio"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (Fase 3D) — ver PlanoContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    tipo: Optional[str] = None
    nome: str
    numero: Optional[str] = None
    atividade_cultura: Optional[str] = None
    data_imobilizacao: Optional[date] = None
    metodo_depreciacao: Optional[str] = None
    vida_util: Optional[str] = None  # texto livre (ex.: "7 Anos")
    valor_residual: Optional[float] = None
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    valor_total: Optional[float] = None
    data_baixa: Optional[date] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)

    # Plano de manutenção preventiva (opcional) — periodicidade só por DATA
    # (ex.: "a cada 6 meses"). O sistema hoje não rastreia horímetro/horas de
    # uso de nenhum equipamento, então manutenção por uso fica fora de escopo
    # por ora (ver ADR em rules/patrimonio.py). Sem plano cadastrado, os três
    # campos ficam None e o item nunca gera alerta.
    frequencia_manutencao_meses: Optional[int] = None
    data_ultima_manutencao: Optional[date] = None
    # Calculada (última + frequência) quando a manutenção é registrada, mas
    # também editável manualmente — cobre o caso de plano novo sem histórico
    # ainda, ou de o usuário querer antecipar/adiar a próxima data.
    data_proxima_manutencao: Optional[date] = None
    observacao_manutencao: Optional[str] = None


# ---------------------------------------------------------------------------
# Manutenção de patrimônio (histórico de execuções do plano preventivo)
# ---------------------------------------------------------------------------
class ManutencaoPatrimonio(SQLModel, table=True):
    """Um registro de manutenção preventiva realizada (ou agendada) em um item
    de Patrimônio — histórico + link opcional para o lançamento em Contas a
    Pagar (ContaGerencial) gerado automaticamente, mesmo padrão de
    FeriasFuncionario/DecimoTerceiro (RH ampliado)."""

    __tablename__ = "manutencao_patrimonio"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    patrimonio_id: int = Field(foreign_key="patrimonio.id", index=True)
    data_realizacao: date
    descricao: Optional[str] = None
    fornecedor: Optional[str] = None
    valor: Optional[float] = None
    centro_custo: str = "Pecuária Leiteira"
    # pendente = a conta a pagar segue em aberto; pago = já baixada na hora
    # do registro (mesmo vocabulário de FeriasFuncionario/DecimoTerceiro).
    status: str = "pago"
    data_pagamento: Optional[date] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # nº do lançamento (LC-...) criado em Contas a Pagar quando
    # `gerar_conta_a_pagar=True` foi pedido ao registrar — None quando o
    # usuário optou por não lançar nada financeiro para esta manutenção.
    numero_lancamento_gerado: Optional[str] = None


# ---------------------------------------------------------------------------
# Lançamento recorrente (Financeiro > Ações > Lançamentos recorrentes) —
# "modelo" com os dados FIXOS de uma conta que se repete todo período (ex.:
# energia, internet, telefone, assinatura, aluguel): fornecedor, conta
# gerencial, centro de custo, forma de pagamento e conta bancária padrão, dia
# de vencimento típico. Todo período, o usuário só entra com os dados
# VARIÁVEIS (valor da fatura, data de emissão real, boleto daquele mês) em
# POST /financeiro/recorrentes/{id}/gerar — que gera um ContaGerencial/
# LancamentoItem de verdade reaproveitando `criar_lancamento`, nunca uma
# tabela paralela. Sem geração automática por cron nem lembrete — isso é
# trabalho de outra sessão (ver ADR no router).
# ---------------------------------------------------------------------------
class LancamentoRecorrente(SQLModel, table=True):
    __tablename__ = "lancamento_recorrente"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    descricao: str  # nome do modelo, ex.: "Energia CPFL"
    tipo: str  # "receita" | "despesa"
    fornecedor_cliente: Optional[str] = None
    centro_custo: Optional[str] = None
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    tipo_item: Optional[str] = None  # "produto" | "servico" — do item gerado
    responsavel_padrao: Optional[str] = None
    tipo_documento_padrao: Optional[str] = None
    forma_pagamento_padrao: Optional[str] = None
    conta_bancaria_padrao: Optional[str] = None
    # Dia do mês em que esta conta costuma vencer (1-31); usado para calcular
    # o vencimento do período ao gerar, se o usuário não informar um diferente
    # (dias além do fim do mês são ajustados para o último dia, ex.: 31 em
    # fevereiro vira 28/29).
    dia_vencimento: Optional[int] = None
    # Nomeado de forma genérica (não "mensal" fixo no código) para não fechar
    # a porta a outras periodicidades no futuro — hoje só "mensal" é aceito
    # (ver PERIODICIDADES_ACEITAS no router), que é o único caso de uso pedido.
    periodicidade: str = "mensal"
    observacao: Optional[str] = None
    ativo: bool = True
    # Rastro só informativo do último lançamento gerado a partir deste modelo
    # (mostrado na lista, não usado por nenhuma regra) — ajuda o usuário a ver
    # se já gerou a conta deste mês antes de gerar de novo.
    ultimo_numero_lancamento: Optional[str] = None
    ultima_geracao_em: Optional[date] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Curva ABC (análise de compras / Pareto)
# ---------------------------------------------------------------------------
class CurvaABC(SQLModel, table=True):
    """Linha da CURVA_ABC.csv — classificação A/B/C de produtos/serviços por valor."""

    __tablename__ = "curva_abc"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    item: Optional[int] = None
    classificacao: Optional[str] = None          # A, B ou C
    produto: Optional[str] = None
    unidade: Optional[str] = None
    preco_unitario: Optional[float] = None
    quantidade: Optional[float] = None
    valor_compra: Optional[float] = None
    valor_acumulado: Optional[float] = None
    perc_acumulado: Optional[float] = None
    perc_total: Optional[float] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
