"""
Cotação de Preços com Fornecedores — pede preço a vários fornecedores por
categoria, compara as respostas e, ao decidir os vencedores, gera Pedidos de
verdade (reaproveita `Pedido`/`PedidoItem` já existentes, com
`origem_tipo="cotacao"` — mesmo precedente de "pedido nascido de outra tela"
que `origem_tipo="orcamento"`/`"planejamento_financeiro"` já usam).

Todas as tabelas carregam `fazenda_id` (mesmo quando derivável via FK pai) —
convenção já usada em `PedidoItem`/`MovimentoEstoque`: isolamento de tenant
por linha, não só por join.

`token_publico` segue o mesmo padrão do reset de senha
(`Usuario.reset_senha_token`): `secrets.token_urlsafe(32)`, opaco, sem
nenhuma outra forma de adivinhar/enumerar. Os endpoints públicos que resolvem
por este token NUNCA aceitam `fazenda_id` do cliente — toda a fazenda é
derivada da própria linha encontrada pelo token.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class Cotacao(SQLModel, table=True):
    __tablename__ = "cotacao"
    __table_args__ = (UniqueConstraint("numero_cotacao", "fazenda_id", name="uq_cotacao_numero_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_cotacao: str = Field(index=True)
    categoria: str  # ver CATEGORIAS_FORNECEDOR em fazenda.rules.categorias
    modo: str = "completo"  # "completo" | "expresso"
    prazo_resposta: datetime
    # rascunho -> enviada -> (parcialmente_respondida|respondida) -> comparada
    # -> pedidos_gerados, com "expirada"/"cancelada" como saídas alternativas.
    # Distinto de Pedido.status de propósito — uma cotação não é um pedido até
    # gerar_pedidos_da_cotacao() criar as linhas reais.
    status: str = "rascunho"
    observacao: Optional[str] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class CotacaoItem(SQLModel, table=True):
    __tablename__ = "cotacao_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    cotacao_id: int = Field(foreign_key="cotacao.id", index=True)
    # Opcional: item já cadastrado em Estoque (via EstoquePicker). `produto`
    # sempre carrega o nome no momento da cotação — se o item de Estoque for
    # renomeado ou excluído depois, a cotação não perde o registro do que foi
    # pedido (mesmo espírito de `PedidoItem.produto_servico`, que também é
    # sempre texto, nunca só a FK).
    estoque_id: Optional[int] = Field(default=None, foreign_key="estoque.id")
    produto: str
    quantidade: float
    unidade: Optional[str] = None


class CotacaoFornecedor(SQLModel, table=True):
    """Um convite de cotação a um fornecedor — o "envelope" que carrega o
    token público e o rastreio de envio/visualização/resposta."""

    __tablename__ = "cotacao_fornecedor"
    __table_args__ = (UniqueConstraint("token_publico", name="uq_cotacao_fornecedor_token"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    cotacao_id: int = Field(foreign_key="cotacao.id", index=True)
    fornecedor_id: int = Field(foreign_key="fornecedor.id")
    canal: str = "email"  # "email" | "whatsapp" | "ambos"
    token_publico: str = Field(index=True)
    # pendente (rascunho, ainda não disparado) -> enviado -> visualizado ->
    # respondido | recusado. "falha_envio" quando o disparo (e-mail/WhatsApp)
    # der erro — fica visível pro gestor tentar de novo, nunca falha silenciosa.
    status_envio: str = "pendente"
    enviado_em: Optional[datetime] = None
    visualizado_em: Optional[datetime] = None
    respondido_em: Optional[datetime] = None


class CotacaoResposta(SQLModel, table=True):
    """Resposta do fornecedor a UM item da cotação — uma linha por
    (fornecedor, item). Criada vazia (`recusado=False`, preço None) quando o
    fornecedor abre a página pela primeira vez, preenchida pelo POST de
    resposta; `vencedor` é marcado na tela de Comparação, nunca pelo
    fornecedor."""

    __tablename__ = "cotacao_resposta"
    __table_args__ = (UniqueConstraint("cotacao_fornecedor_id", "cotacao_item_id", name="uq_cotacao_resposta_item"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    cotacao_fornecedor_id: int = Field(foreign_key="cotacao_fornecedor.id", index=True)
    cotacao_item_id: int = Field(foreign_key="cotacao_item.id", index=True)
    recusado: bool = False
    preco_unitario: Optional[float] = None
    frete_incluso: Optional[bool] = None
    valor_frete: Optional[float] = None
    prazo_entrega_dias: Optional[int] = None
    condicao_pagamento: Optional[str] = None
    observacao: Optional[str] = None
    vencedor: bool = False
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class PedidoConfirmacao(SQLModel, table=True):
    """Disparo de "pedido formal" — pede ao fornecedor vencedor que confirme
    o pedido já fechado (preço não reabre, só previsão de entrega). Um Pedido
    pode ter mais de uma linha aqui só se for reenviado (a última é a
    válida)."""

    __tablename__ = "pedido_confirmacao"
    __table_args__ = (UniqueConstraint("token_publico", name="uq_pedido_confirmacao_token"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    pedido_id: int = Field(foreign_key="pedido.id", index=True)
    token_publico: str = Field(index=True)
    status: str = "enviado"  # "enviado" | "confirmado" | "recusado"
    previsao_entrega: Optional[str] = None
    observacao_fornecedor: Optional[str] = None
    enviado_em: datetime = Field(default_factory=datetime.utcnow)
    confirmado_em: Optional[datetime] = None


class FornecedorCategoria(SQLModel, table=True):
    """Categoria N:N de um Fornecedor — `Fornecedor.categoria` (texto único)
    continua existindo por compatibilidade com o cadastro atual; esta tabela
    é aditiva e é a fonte usada pela sugestão automática de fornecedores por
    categoria na Cotação. `fazenda_id` espelha `Fornecedor.fazenda_id`
    (redundante de propósito — mesma defesa em profundidade de
    `PedidoItem.fazenda_id`)."""

    __tablename__ = "fornecedor_categoria"
    __table_args__ = (UniqueConstraint("fornecedor_id", "categoria", name="uq_fornecedor_categoria"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    fornecedor_id: int = Field(foreign_key="fornecedor.id", index=True)
    categoria: str
