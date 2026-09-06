"""
Rubrica avulsa do holerite — o vencimento ou o desconto que o dono acrescenta
à folha de uma competência, linha a linha.

POR QUE ESTA TABELA EXISTE. `FolhaPagamento` só tinha DOIS campos livres de
dinheiro: `valor_bruto` (o salário) e `descontos` (um float solto, sem
itemização — o próprio `_detalhe_folha` escreve "Valor único, sem detalhamento
gravado" na coluna Referência porque não há o que dizer). Não havia onde
lançar uma bonificação por produtividade, uma guelta, um reembolso ou um
desconto de uma compra que a fazenda pagou pelo funcionário: ou o valor era
somado à mão no salário bruto — e aí virava salário para todos os efeitos,
inclusive para as bases de INSS/IRRF/FGTS, o que está errado para reembolso e
indenização — ou ficava fora do documento.

A COLUNA `natureza` É O CORAÇÃO DISTO. Rubrica trabalhista não é toda igual:
reembolso e indenização têm natureza INDENIZATÓRIA (repõem patrimônio, não
remuneram trabalho) e não integram salário nem as bases de contribuição;
bonificação por produtividade e gueltas têm natureza SALARIAL e integram.
Sem um campo dizendo isso, o holerite calcularia as retenções sobre uma base
inflada por reembolso — erro que aparece em dinheiro no bolso do funcionário
e na guia do empregador. O enquadramento de cada código está em
`fazenda/rules/rubrica_folha.py::CATALOGO_VENCIMENTOS`, com o fundamento
legal de cada um.

POR QUE O ENQUADRAMENTO É COPIADO PARA A LINHA (e não só consultado no
catálogo na hora de ler): mesmo motivo de `RescisaoFuncionario.salario_base` e
de `FolhaPagamento.discriminacao_congelada` — o holerite é PROVA. Se amanhã o
catálogo mudar (a lei muda, o entendimento muda), o recibo já emitido não pode
mudar de conteúdo retroativamente por causa disso.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class FolhaRubrica(SQLModel, table=True):
    """Um vencimento ou desconto acrescentado ao holerite de uma competência."""

    __tablename__ = "folha_rubrica"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    folha_id: int = Field(foreign_key="folha_pagamento.id", index=True)
    # `pessoa_id`/`competencia` são redundantes com a folha DE PROPÓSITO: a
    # incorporação do "aumento na folha" precisa varrer os aumentos de uma
    # pessoa por faixa de competência (ver `aumento_incorporado`) sem ter de
    # carregar todas as folhas dela antes — e a competência de uma folha nunca
    # muda depois de criada, então não há como as duas divergirem.
    pessoa_id: int = Field(foreign_key="pessoa.id", index=True)
    competencia: str = Field(index=True)  # "AAAA-MM", a mesma da folha
    especie: str  # vencimento | desconto
    codigo: str  # ver CATALOGO_VENCIMENTOS / CATALOGO_DESCONTOS
    # Texto livre do usuário ("colheita de setembro", "quebra de vidro do
    # trator"). Complementa o rótulo do código, nunca o substitui.
    descricao: Optional[str] = None
    valor: float  # sempre POSITIVO; quem diz se soma ou subtrai é `especie`

    # ── Enquadramento congelado no lançamento (ver docstring do módulo) ──
    natureza: str  # salarial | indenizatoria
    incide_inss: bool = False
    incide_irrf: bool = False
    incide_fgts: bool = False
    # Só o "aumento na folha": o valor não é avulso do mês, ele passa a fazer
    # parte do salário-base a partir da competência SEGUINTE (art. 468 da CLT
    # — alteração benéfica ao empregado, que não se desfaz sozinha no mês
    # seguinte). Ver `aumento_incorporado`.
    incorpora_base: bool = False

    # ── Desconto associado a uma compra já realizada ──
    # FK de verdade para a parcela do lançamento financeiro, e não o número do
    # lançamento em texto: é o que permite o clique na linha do holerite chegar
    # à compra sem casar por string (o mesmo erro que o desconto de vale já
    # tinha cometido com `/vale/i.test(label)`). `numero_lancamento` viaja
    # junto só como rótulo estável para o documento impresso.
    conta_gerencial_id: Optional[int] = Field(default=None, foreign_key="conta_gerencial.id", index=True)
    numero_lancamento: Optional[str] = None

    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
