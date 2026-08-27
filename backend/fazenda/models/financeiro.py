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
    classificacao: Optional[str] = None  # nome de uma ClassificacaoLancamento cadastrada (ex.: Medicamentos)
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
    # Vínculo opcional a um item de Patrimônio (ver Patrimonio, mais abaixo
    # neste arquivo) — esta compra/venda representa uma entrada/saída de
    # patrimônio. FK de verdade (não string), editável dos dois lados: aqui
    # (POST/PUT /financeiro/lancamentos) e do lado do Patrimônio (POST
    # /financeiro/patrimonio, campo `criar_patrimonio` na criação do
    # lançamento, ou vínculo posterior via PUT /financeiro/patrimonio/{id}).
    patrimonio_id: Optional[int] = Field(default=None, foreign_key="patrimonio.id", index=True)


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
    # Override do centro de custo da nota (ContaGerencial.centro_custo) SÓ
    # para este item — permite que uma nota com vários itens (um boleto,
    # uma compra) distribua cada item para um centro de custo diferente.
    # None (a maioria dos itens) = usa o centro de custo da nota inteira.
    centro_custo: Optional[str] = None
    produto: str
    tipo_item: Optional[str] = None  # "produto" | "servico" — escolha exclusiva no lançamento
    descricao: Optional[str] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: float
    # ── Item que na verdade é gasto pessoal de um funcionário/empreiteiro/
    # diarista (checkbox "É vale de funcionário?" na linha do item, ver
    # FormFinanceiro.tsx). O dinheiro saiu de verdade na compra — o caixa da
    # fazenda continua batendo —, mas gerencialmente isso não é despesa da
    # fazenda e sim adiantamento A RECEBER da pessoa: por isso o item passa a
    # ser ignorado por todo relatório gerencial (ver rules/vale_item.py).
    # Exatamente UM dos dois é preenchido, nunca os dois: o vale gerado é um
    # ValeFuncionario (desconto na folha) OU um ValeAvulso (abatimento de
    # empreitada/contrato/diária) de verdade — não há sistema paralelo de vale.
    # Ambos nullable: item sem vale (a esmagadora maioria) tem os dois nulos.
    vale_funcionario_id: Optional[int] = Field(default=None, foreign_key="vale_funcionario.id", index=True)
    vale_avulso_id: Optional[int] = Field(default=None, foreign_key="vale_avulso.id", index=True)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Anexo de lançamento financeiro (ex.: boleto, nota fiscal, comprovante de um
# parcelamento) — o conteúdo vive no Supabase Storage (ver
# fazenda/rules/supabase_storage.py), igual ao Arquivo fiscal-contábil
# (DocumentoArquivado, ver fazenda/models/documentos.py); aqui só ficam os
# metadados e o caminho. `conteudo` (bytes direto no Postgres) é o formato
# ANTIGO, mantido só para ler anexos já existentes — todo anexo novo usa
# `caminho_storage`, nunca os dois ao mesmo tempo.
#
# Também é o anexo do COMPROVANTE DE PAGAMENTO de `ValeFuncionario` e
# `ValeAvulso` (ver fazenda/api/routers/cadastro/rh_folha.py, rotas
# /vales/{tipo}/{id}/comprovante) — reaproveitado em vez de uma tabela nova
# porque o mecanismo (Storage + categoria "Comprovante" + metadados) é
# idêntico; só a chave de vínculo muda. `numero_lancamento` continua sendo
# o vínculo de todo anexo "de lançamento" de verdade, mas um vale nem
# sempre tem um `ContaGerencial` por trás (forma_pagamento
# "desconto_integral_folha"/"desconto_proximo_pagamento" não move caixa —
# ver `_sincronizar_conta_vale`): por isso `numero_lancamento` virou
# opcional e ganhou os dois FKs abaixo, mutuamente exclusivos com ele e
# entre si (exatamente um dos três vínculos preenchido, nunca mais de um).
# ---------------------------------------------------------------------------
class LancamentoAnexo(SQLModel, table=True):
    __tablename__ = "lancamento_anexo"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda — ver ContaGerencial.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_lancamento: Optional[str] = Field(default=None, index=True)
    # Comprovante de vale — exatamente um preenchido quando o anexo é de
    # vale (o outro fica None), e os dois None quando o anexo é de um
    # lançamento normal (`numero_lancamento` preenchido nesse caso).
    vale_funcionario_id: Optional[int] = Field(default=None, foreign_key="vale_funcionario.id", index=True)
    vale_avulso_id: Optional[int] = Field(default=None, foreign_key="vale_avulso.id", index=True)
    nome_arquivo: str
    mime_type: str
    tamanho_bytes: int
    conteudo: Optional[bytes] = None  # formato antigo (legado) — ver docstring acima
    categoria: Optional[str] = None  # nome de um tipo de documento cadastrado (TIPOS_DOCUMENTO)
    # Número impresso no próprio documento (nº da nota fiscal, do boleto, da
    # OS, do orçamento/pedido...) e a data dele — diferentes de `criado_em`
    # (quando o arquivo foi enviado). É por aqui que a Central de Documentos
    # (fazenda.api.routers.central_documentos) permite achar, por exemplo,
    # "o boleto número X" ou "tudo com data de documento em julho", mesmo
    # sabendo só um dos vários documentos que um lançamento reúne (orçamento,
    # pedido, nota fiscal, boleto, comprovante — cada um com seu próprio número).
    numero_documento: Optional[str] = Field(default=None, index=True)
    data_documento: Optional[date] = None
    caminho_storage: Optional[str] = None  # Supabase Storage — formato atual
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
# Transferência entre contas correntes (Configurações > Parâmetros
# financeiros > Conta corrente, botão "Transferir entre contas") — move
# dinheiro de uma conta cadastrada para outra, refletindo no saldo calculado
# das duas (ver calcular_saldos_contas_correntes em
# fazenda/api/routers/financeiro.py).
#
# Tabela dedicada em vez de reaproveitar ContaGerencial com um novo tipo
# "transferencia": ContaGerencial carrega dezenas de campos que não fazem
# sentido aqui (parcela, boleto, patrimônio, pedido...) e o `tipo` do
# lançamento é assumido "receita"/"despesa" em vários pontos do sistema (DRE
# — agrupamento por_conta trata qualquer tipo != "receita" como despesa —,
# validação de POST/PUT /financeiro/lancamentos etc.); um tipo novo ali
# arriscaria vazar a transferência pros relatórios de despesa/receita sem
# cada ponto do sistema saber filtrar. Uma linha por transferência já liga
# as duas pontas (origem e destino) sozinha, sem precisar de um par de
# registros linkados por um `transferencia_par_id`.
# ---------------------------------------------------------------------------
class TransferenciaContas(SQLModel, table=True):
    __tablename__ = "transferencia_contas"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda — ver ContaCorrente.fazenda_id acima.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    conta_origem_id: int = Field(foreign_key="conta_corrente.id", index=True)
    conta_destino_id: int = Field(foreign_key="conta_corrente.id", index=True)
    valor: float
    data: date
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    # Centro de custo usado automaticamente no Lançamento simplificado
    # (Lançamentos > Financeiro > Contas a pagar/receber) — no máximo 1
    # marcado por fazenda; ao marcar um, os demais da mesma fazenda são
    # desmarcados na mesma transação (ver `_desmarcar_outros_centro_custo_
    # padrao` em fazenda/api/routers/financeiro.py). Sem nenhum marcado, o
    # formulário simplificado bloqueia o salvamento em vez de adivinhar.
    padrao: bool = Field(default=False)
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


class ClassificacaoLancamento(SQLModel, table=True):
    """Classificação livre de uma conta a pagar/receber (ex.: Medicamentos,
    Ração, Manutenção) — Configurações > Parâmetros financeiros, mesmo padrão
    de TipoDocumento/FormaPagamentoCadastro, cadastrável na hora do lançamento."""

    __tablename__ = "classificacao_lancamento"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_classificacao_lancamento_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
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
    # Rastreio — preenchido quando o status vira "parcialmente_atendido" e o
    # usuário confirma que o pedido já foi enviado (ver PUT /pedidos/{id}/rastreio).
    enviado: Optional[bool] = None
    codigo_rastreio: Optional[str] = None
    link_rastreio: Optional[str] = None
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
    # Dirige o status ATUAL do Pedido (ver pedidos.py::atualizar_status_por_*)
    # — dinheiro lançado ou estoque baixado, não entrega física.
    quantidade_atendida: float = 0
    valor_atendido: float = 0
    # Quanto desse item já foi CONFIRMADO como fisicamente entregue — só
    # escrito por uma ação explícita de "marcar entrega" (ainda não
    # implementada), nunca por lançamento financeiro nem movimento de
    # estoque. Paralelo e independente de quantidade_atendida/valor_atendido
    # de propósito: é a base do novo cálculo de status em
    # fazenda.rules.pedido_status.calcular_status_pedido, que nenhum router
    # ainda chama (ver comentário da migração f1a2b3c4d5e6).
    quantidade_entregue: float = 0


CATEGORIAS_PEDIDO_ANEXO = ["Orçamento", "Ordem de serviço", "Outro documento"]


class PedidoAnexo(SQLModel, table=True):
    """Documento anexado a um Pedido — orçamento, ordem de serviço ou outro
    documento (ver CATEGORIAS_PEDIDO_ANEXO). Mesmo padrão de armazenamento
    de LancamentoAnexo (conteúdo no Supabase Storage, só metadados aqui),
    mas com `data_validade` própria: é dela que a Agenda tira o alerta de
    vencimento (2 dias antes, ver fazenda/rules/agenda_engine.py) enquanto
    o pedido segue "aberto" ou "parcialmente_atendido"."""

    __tablename__ = "pedido_anexo"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    pedido_id: int = Field(foreign_key="pedido.id", index=True)
    nome_arquivo: str
    mime_type: str
    tamanho_bytes: int
    categoria: str  # um de CATEGORIAS_PEDIDO_ANEXO
    data_validade: Optional[date] = None
    caminho_storage: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    # False (padrão) preserva o comportamento histórico: valor_total JÁ é o
    # valor do lote inteiro. True = valor_total é o valor de UMA unidade, e a
    # base de qualquer cálculo (depreciação, valor de mercado inicial, KPIs)
    # passa a ser valor_total * quantidade — ver rules.patrimonio.
    # valor_base_aquisicao, a ÚNICA função que deve ler estes dois campos
    # juntos (nenhum outro ponto deve ler valor_total cru).
    valor_por_unidade: bool = False
    data_baixa: Optional[date] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)

    # True (padrão) = deprecia normalmente (calcular_depreciacao). False =
    # patrimônio que só valoriza (ex.: terra/fazenda) — não deprecia, e em vez
    # disso acompanha `valor_mercado_atual`, atualizado periodicamente (ver
    # campos abaixo e o card "Atualizar valor de mercado" na Agenda).
    depreciavel: bool = True
    valor_mercado_atual: Optional[float] = None
    data_ultima_atualizacao_valor_mercado: Optional[date] = None
    # Frequência de atualização do valor de mercado, só para depreciavel=False:
    # None = usa o padrão do sistema (Configurações > Parâmetros, ver
    # fazenda.rules.parametros.patrimonio_atualizacao_valor_mercado_meses); 0 =
    # nunca (não gera pendência); N = a cada N meses (override deste item).
    atualizacao_valor_mercado_frequencia_meses: Optional[int] = None

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
# Cartão de crédito (Financeiro > Controle Financeiro > Cartão de crédito) —
# extrato próprio por fatura, fechamento por competência e pagamento
# reaproveitando o mesmo fluxo de baixa do Financeiro (ver
# fazenda/api/routers/cartao_credito.py). Não substitui o campo solto
# `ContaGerencial.data_vencimento_cartao` (forma_pagamento="credito") já
# existente — aquele continua servindo pagamentos avulsos no cartão sem
# cadastro; este módulo é para quem quer extrato/fatura/milhas de verdade.
# ---------------------------------------------------------------------------
class CartaoCredito(SQLModel, table=True):
    __tablename__ = "cartao_credito"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    apelido: str
    bandeira: Optional[str] = None
    banco_emissor: Optional[str] = None
    conta_bancaria_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")
    dia_fechamento: int  # 1-31
    dia_vencimento: int  # 1-31
    limite: Optional[float] = None
    controla_milhas: bool = False
    milhas_por_real: Optional[float] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FaturaCartao(SQLModel, table=True):
    """Uma competência (mês) do cartão — nasce "aberta" na hora do 1º
    lançamento daquele mês (mesmo padrão de `cronograma_aberto()`, ver
    fazenda/rules/cronograma_sanitario.py: lida sempre cria se faltar).
    `valor_total`/`milhas_acumuladas` só são gravados (congelados) no
    fechamento — enquanto aberta, o extrato soma os LancamentoCartao ao vivo."""

    __tablename__ = "fatura_cartao"
    __table_args__ = (UniqueConstraint("cartao_id", "competencia", name="uq_fatura_cartao_competencia"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    cartao_id: int = Field(foreign_key="cartao_credito.id", index=True)
    competencia: str = Field(index=True)  # "2026-08"
    data_fechamento: date
    data_vencimento: date
    valor_total: Optional[float] = None  # só preenchido no fechamento
    milhas_acumuladas: Optional[int] = None
    status: str = "aberta"  # "aberta" | "fechada" | "paga"
    numero_lancamento: Optional[str] = None  # → ContaGerencial, só quando paga
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class LancamentoCartao(SQLModel, table=True):
    """Uma compra no cartão. `fatura_id` é atribuído na hora da criação,
    resolvendo a competência pela data da compra x dia de fechamento do
    cartão (ver `_resolver_fatura` no router)."""

    __tablename__ = "lancamento_cartao"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    cartao_id: int = Field(foreign_key="cartao_credito.id", index=True)
    fatura_id: int = Field(foreign_key="fatura_cartao.id", index=True)
    data_compra: date
    descricao: str
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    centro_custo: Optional[str] = None
    valor: float
    parcela_num: Optional[int] = None
    parcela_total: Optional[int] = None
    observacao: Optional[str] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


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
