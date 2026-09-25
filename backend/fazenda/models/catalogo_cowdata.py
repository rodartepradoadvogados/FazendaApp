"""
Catálogo de preços de referência do Painel CowData — a CowData cotiza com os
próprios fornecedores (não os de cada fazenda) e atribui um preço-base
sugerido a um produto-padrão, que toda fazenda-cliente pode ver como
referência ao lançar seu próprio item de Estoque. Nunca escreve em
`Estoque.valor_unitario` — é só um número de apoio, a fazenda decide o
próprio preço sempre.

SEM `fazenda_id` em nenhuma tabela deste módulo, de propósito — diferente do
catálogo de farmácia (`PrincipioAtivo`/`Doenca`, `fazenda_id` nulo = "linha
global", com `rules.visibilidade.visivel()` unindo global+própria), aqui não
existe personalização por fazenda: é um catálogo único, mantido só pela
CowData. Mesmo padrão de `Touro` (NAAB) em `sanidade.py`, que também não
carrega `fazenda_id`. Nunca colidir de nome com o `fazenda.models.cotacao`
(cotação de UMA fazenda com OS FORNECEDORES DELA) — este módulo é sobre a
CowData e os fornecedores DELA, por isso todo nome novo leva o sufixo
"CowData"/"_cowdata".

Muralha de privacidade: fornecedor_cowdata NUNCA aparece em nada que uma
fazenda possa ler. A fazenda só vê "preço veio de cotação realizada em
<data>" — nunca qual fornecedor, nem se foi só um ou uma média entre vários.
Essa muralha é estrutural (o schema de resposta pública nem carrega o campo),
não um filtro de UI — ver `api/routers/estoque.py::precos_referencia_cowdata`
(schema de leitura sem nenhum campo de fornecedor) e
`api/routers/painel_cowdata_cotacoes.py` (onde o fornecedor de fato aparece,
só dentro do Painel CowData).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


# ---------------------------------------------------------------------------
# Classificação / Finalidade — vocabulário livre que a CowData cadastra e
# mantém (não um enum fixo) para marcar fornecedores e produtos-padrão, e
# para servir de "modo" de cotação (por produto específico, por classificação
# inteira ou por finalidade inteira — ver CotacaoCowDataItem.modo). Nunca
# aparece por extenso no texto que sai para o fornecedor ("Cotação de:
# Medicamentos", nunca "finalidade: Medicamentos") — ver
# rules/cotacao_cowdata.py::montar_mensagem_cotacao_cowdata.
# ---------------------------------------------------------------------------
class ClassificacaoCowData(SQLModel, table=True):
    """Categoria ampla (ex.: "Ração e insumos alimentares", "Medicamentos e
    produtos veterinários") — mesmo vocabulário inicial de
    rules.categorias.CATEGORIAS_FORNECEDOR (a lista semeia a tabela na
    migração), mas editável depois pela CowData, como Laboratorio/
    CategoriaMedicamento já são."""

    __tablename__ = "classificacao_cowdata"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FinalidadeCowData(SQLModel, table=True):
    """Rótulo mais fino, transversal à classificação (ex.: "Energético",
    "Proteico", "Antibiótico") — permite cotar/consultar por um recorte mais
    específico do que a classificação sozinha permitiria (pedido do usuário:
    "posso querer cotar concentrados energéticos, destrinchar isso no corpo
    do texto")."""

    __tablename__ = "finalidade_cowdata"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Fornecedor da própria CowData (nunca o Fornecedor de uma fazenda,
# fazenda.models.estoque.Fornecedor) — quem a CowData de fato cotiza.
# ---------------------------------------------------------------------------
class FornecedorCowData(SQLModel, table=True):
    __tablename__ = "fornecedor_cowdata"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    cnpj_cpf: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FornecedorCowDataClassificacao(SQLModel, table=True):
    """N:N — um fornecedor pode atender mais de uma classificação (pedido do
    usuário: "um ou mais de um")."""

    __tablename__ = "fornecedor_cowdata_classificacao"
    __table_args__ = (UniqueConstraint("fornecedor_cowdata_id", "classificacao_id", name="uq_forncd_classificacao"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fornecedor_cowdata_id: int = Field(foreign_key="fornecedor_cowdata.id", index=True)
    classificacao_id: int = Field(foreign_key="classificacao_cowdata.id", index=True)


class FornecedorCowDataFinalidade(SQLModel, table=True):
    """N:N — mesmo espírito de FornecedorCowDataClassificacao, para
    finalidade."""

    __tablename__ = "fornecedor_cowdata_finalidade"
    __table_args__ = (UniqueConstraint("fornecedor_cowdata_id", "finalidade_id", name="uq_forncd_finalidade"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fornecedor_cowdata_id: int = Field(foreign_key="fornecedor_cowdata.id", index=True)
    finalidade_id: int = Field(foreign_key="finalidade_cowdata.id", index=True)


# ---------------------------------------------------------------------------
# Produto-padrão — o item do catálogo compartilhado que recebe o
# preço-base sugerido. Granularidade sem regra fixa imposta (não há um jeito
# automático de garantir que "Silagem de milho" e "Silagem de milho picada"
# não virem dois produtos-padrão diferentes) — mitigado por um aviso ativo de
# possível duplicata no cadastro (rules/cotacao_cowdata.py::
# sugestoes_duplicata), nunca por uma trava — depende de curadoria humana
# contínua da própria CowData, decisão explícita (o usuário delegou este
# ponto).
# ---------------------------------------------------------------------------
class ProdutoPadrao(SQLModel, table=True):
    __tablename__ = "produto_padrao"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    unidade: Optional[str] = None  # texto livre, mesmo espírito de Estoque.unidade
    classificacao_id: Optional[int] = Field(default=None, foreign_key="classificacao_cowdata.id", index=True)
    # Vínculo opcional ao catálogo de farmácia já existente (sanidade.py) —
    # só quando o produto-padrão É um medicamento comercial; None para
    # ração/insumo/equipamento/etc. MedicamentoComercial.principio_ativo_id é
    # NOT NULL, então vincular aqui automaticamente já traz o princípio ativo
    # junto.
    medicamento_comercial_id: Optional[int] = Field(default=None, foreign_key="medicamento_comercial.id", index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ProdutoPadraoFinalidade(SQLModel, table=True):
    """N:N — um produto-padrão pode servir mais de uma finalidade (ex.:
    "Farelo de soja" é energético E proteico)."""

    __tablename__ = "produto_padrao_finalidade"
    __table_args__ = (UniqueConstraint("produto_padrao_id", "finalidade_id", name="uq_produtopadrao_finalidade"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    produto_padrao_id: int = Field(foreign_key="produto_padrao.id", index=True)
    finalidade_id: int = Field(foreign_key="finalidade_cowdata.id", index=True)


# ---------------------------------------------------------------------------
# Cotação CowData — a CowData liga para os próprios fornecedores e REGISTRA
# manualmente cada resposta (diferente da Cotação de uma fazenda em
# fazenda.models.cotacao, que dispara e-mail/WhatsApp com link público sem
# login: aqui os fornecedores já são conhecidos e contatados diretamente pela
# CowData, então não há necessidade de link/token — só um formulário de
# registro).
# ---------------------------------------------------------------------------
STATUS_COTACAO_COWDATA = ("rascunho", "em_andamento", "fechada", "cancelada")


class CotacaoCowData(SQLModel, table=True):
    __tablename__ = "cotacao_cowdata"

    id: Optional[int] = Field(default=None, primary_key=True)
    titulo: str
    status: str = "rascunho"  # ver STATUS_COTACAO_COWDATA
    usuario_id: int = Field(foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    fechada_em: Optional[datetime] = None


class CotacaoCowDataFornecedor(SQLModel, table=True):
    """Fornecedores convidados/considerados nesta cotação — o universo de
    quem pode ter uma CotacaoCowDataResposta registrada."""

    __tablename__ = "cotacao_cowdata_fornecedor"
    __table_args__ = (UniqueConstraint("cotacao_cowdata_id", "fornecedor_cowdata_id", name="uq_cotcd_fornecedor"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    cotacao_cowdata_id: int = Field(foreign_key="cotacao_cowdata.id", index=True)
    fornecedor_cowdata_id: int = Field(foreign_key="fornecedor_cowdata.id", index=True)


class CotacaoCowDataItem(SQLModel, table=True):
    """Uma linha da cotação — decide, por linha, se o alvo é um produto
    específico, uma classificação inteira ou uma finalidade inteira (pedido
    do usuário: "para cada produto, se vai ser por produto, por
    classificação ou por finalidade"). Exatamente um dos três alvos é
    preenchido, conforme `modo`."""

    __tablename__ = "cotacao_cowdata_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    cotacao_cowdata_id: int = Field(foreign_key="cotacao_cowdata.id", index=True)
    modo: str  # "produto" | "classificacao" | "finalidade"
    produto_padrao_id: Optional[int] = Field(default=None, foreign_key="produto_padrao.id", index=True)
    classificacao_id: Optional[int] = Field(default=None, foreign_key="classificacao_cowdata.id", index=True)
    finalidade_id: Optional[int] = Field(default=None, foreign_key="finalidade_cowdata.id", index=True)
    # Elaboração livre, só para uso INTERNO (nunca sai por extenso rotulado
    # como "finalidade:"/"classificação:" — a mensagem some com um rótulo
    # neutro, ver montar_mensagem_cotacao_cowdata) — ex.: "concentrados
    # energéticos: milho moído, farelo de soja, casquinha de soja".
    descricao_livre: Optional[str] = None


class CotacaoCowDataResposta(SQLModel, table=True):
    """A resposta de UM fornecedor a UM item da cotação — digitada
    manualmente pela equipe CowData depois do contato (telefone/e-mail/
    WhatsApp feito por fora do sistema), não recebida por link público."""

    __tablename__ = "cotacao_cowdata_resposta"
    __table_args__ = (UniqueConstraint("cotacao_cowdata_item_id", "fornecedor_cowdata_id", name="uq_cotcd_resposta"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    cotacao_cowdata_item_id: int = Field(foreign_key="cotacao_cowdata_item.id", index=True)
    fornecedor_cowdata_id: int = Field(foreign_key="fornecedor_cowdata.id", index=True)
    valor: Optional[float] = None
    condicao_pagamento: Optional[str] = None
    prazo_entrega_dias: Optional[int] = None
    observacao: Optional[str] = None
    recusado: bool = False
    registrado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Preço-base sugerido — o que de fato chega à fazenda (via leitura pública
# filtrada, nunca write). Cada atribuição de preço (venha de uma cotação
# fechada ou de pesquisa simples/manual) passa pelo "popup" de publicar ou
# não (pedido do usuário) — `publicado` decide se aparece para as fazendas,
# e essa escolha é feita de novo a cada nova atribuição, nunca herdada.
# ---------------------------------------------------------------------------
class PrecoBaseSugerido(SQLModel, table=True):
    __tablename__ = "preco_base_sugerido"

    id: Optional[int] = Field(default=None, primary_key=True)
    produto_padrao_id: int = Field(foreign_key="produto_padrao.id", index=True)
    valor: float
    unidade: Optional[str] = None
    regiao: Optional[str] = None
    origem: str = "manual"  # "cotacao" | "manual" — de onde veio o número
    cotacao_cowdata_item_id: Optional[int] = Field(default=None, foreign_key="cotacao_cowdata_item.id", index=True)
    # Fornecedor vencedor (origem="cotacao", eh_media=False) OU informado à
    # mão numa atribuição manual — NUNCA serializado para fora do Painel
    # CowData (ver docstring do módulo).
    fornecedor_escolhido_id: Optional[int] = Field(default=None, foreign_key="fornecedor_cowdata.id")
    eh_media: bool = False
    observacao: Optional[str] = None
    publicado: bool = False
    publicado_em: Optional[datetime] = None
    usuario_id: int = Field(foreign_key="usuario.id")
    atribuido_em: datetime = Field(default_factory=datetime.utcnow)


class PrecoBaseSugeridoParticipanteMedia(SQLModel, table=True):
    """Quando `PrecoBaseSugerido.eh_media` é True, cada fornecedor que
    participou da média — com o valor que ELE informou, para o Painel
    CowData sempre poder mostrar "quem entrou na média e com que preço"
    (pedido do usuário). Nunca visível à fazenda."""

    __tablename__ = "preco_base_sugerido_participante_media"

    id: Optional[int] = Field(default=None, primary_key=True)
    preco_base_sugerido_id: int = Field(foreign_key="preco_base_sugerido.id", index=True)
    fornecedor_cowdata_id: int = Field(foreign_key="fornecedor_cowdata.id", index=True)
    valor_informado: Optional[float] = None
