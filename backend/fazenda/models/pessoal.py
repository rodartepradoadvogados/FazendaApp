"""
Pessoal/RH — cadastro de pessoas, folha de pagamento, férias/13º, vales, empreitadas, contratos e diárias.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Pessoa (Configurações > Cadastro) — funcionário, veterinário, zootecnista,
# diarista, prestador de serviços. Distinto de Fornecedor: pessoa entra em
# folha de pagamento, não em nota de compra.
# ---------------------------------------------------------------------------
class TipoPessoa(SQLModel, table=True):
    """
    Tipo de pessoa cadastrável (Funcionário, Veterinário, Empreiteiro...) —
    usado no seletor "Tipo(s)" do Cadastro de Pessoas. Substitui a lista fixa
    TIPOS_PESSOA por uma tabela editável em tempo de execução (botão "+" no
    Cadastro de Pessoas), para que novos tipos apareçam em todos os relatórios
    sem precisar de deploy.
    """

    __tablename__ = "tipo_pessoa"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Pessoa(SQLModel, table=True):
    """Cadastro de pessoas — funcionários e prestadores ligados à fazenda."""

    __tablename__ = "pessoa"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    tipo: str  # Funcionário | Veterinário | Zootecnista | Vet/Zootec. | Diarista | Prestador de serviços | ... (CSV de TipoPessoa.nome)
    telefone: Optional[str] = None  # legado — sempre o 1º item de `telefones`, mantido para quem lê Pessoa.email/telefone direto (ex.: destinatario_recibo)
    email: Optional[str] = None  # legado — sempre o 1º item de `emails`
    telefones: Optional[str] = None  # JSON: lista de strings — 0 a N telefones (mesmo padrão de NoticiaNews.fontes)
    emails: Optional[str] = None  # JSON: lista de strings — 0 a N e-mails
    cpf_cnpj: Optional[str] = None
    cep: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)

    # Referência para o limite de 40% de desconto de vale (ver ValeFuncionario).
    salario_base: Optional[float] = None

    # Data de admissão — usada para calcular a folha proporcional do 1º mês
    # (dias trabalhados / dias do mês) no lançamento de Folha de Pagamento.
    data_admissao: Optional[date] = None


# ---------------------------------------------------------------------------
# Folha de pagamento — lançamento e acompanhamento por pessoa/competência.
# ---------------------------------------------------------------------------
class FolhaPagamento(SQLModel, table=True):
    """Um lançamento de folha de pagamento (pessoa × mês/ano de competência)."""

    __tablename__ = "folha_pagamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    competencia: str = Field(index=True)  # "AAAA-MM"
    valor_bruto: float
    descontos: float = 0.0
    # Retenção de INSS/IR — o percentual guia o cálculo automático do valor
    # retido durante o lançamento, mas o valor final fica editável (para
    # particularidades de cada lançamento não seguirem a fórmula à risca).
    percentual_inss: float = 0.0
    percentual_ir: float = 0.0
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    # Descontos de vale (adiantamentos) — coluna SEPARADA de `descontos` (que
    # passa a ser só os "descontos de folha" manuais). Computado sempre a partir
    # da SOMA das ValeParcela da competência, para ser idempotente.
    valor_vale: float = 0.0
    valor_liquido: float
    data_pagamento: Optional[date] = None
    status: str = "pendente"  # pendente | pago
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)

    # FGTS/DCTF — projeção OPCIONAL por lançamento (mesmo par percentual/valor
    # do INSS/IR, mas os quatro nascem em branco: se nada for preenchido, o
    # lançamento de folha continua funcionando exatamente como antes, sem
    # nenhum efeito. Diferente de INSS/IR (calculados no frontend e só
    # armazenados aqui), o cálculo final destes — valor explícito tem
    # prioridade sobre percentual×bruto quando os dois vierem preenchidos —
    # é feito no backend (ver `_calcular_encargo_projetado` em
    # `routers/cadastro.py`), para servir de base confiável à soma consolidada
    # usada em `POST /folha-pagamento/gerar-guias`. NÃO é o cálculo legal real
    # de FGTS (8% s/ remuneração) nem da guia de DCTF — o percentual/valor é
    # decidido pelo usuário/contador; aqui só projetamos o fluxo de caixa,
    # sem qualquer envio a sistemas do governo.
    percentual_fgts: Optional[float] = None
    valor_fgts: Optional[float] = None
    percentual_dctf: Optional[float] = None
    valor_dctf: Optional[float] = None

    # Recorrência mensal — marca este lançamento como o "modelo" a partir do
    # qual as competências seguintes são geradas automaticamente em Contas a
    # Pagar, sem precisar relançar a folha todo mês (dia_vencimento define o
    # dia do mês da conta a pagar gerada).
    recorrente: bool = False
    dia_vencimento: Optional[int] = None
    origem_recorrencia_id: Optional[int] = None  # id do lançamento-modelo, quando gerado automaticamente
    numero_lancamento_gerado: Optional[str] = None  # nº do lançamento (LC-...) criado em Contas a Pagar
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Centro de custo de TODAS as contas a pagar geradas por esta folha —
    # nasce em "Pecuária Leiteira" (perfil típico da folha), mas é editável.
    centro_custo: str = "Pecuária Leiteira"


# ---------------------------------------------------------------------------
# Férias e 13º salário — controle DENTRO do app (cálculo, lançamento em Contas
# a Pagar e acompanhamento). Item de auditoria "RH ampliado (férias/13º/
# eSocial)" — a integração com o eSocial (envio ao governo) fica FORA de
# escopo: inviável sem certificado digital/infraestrutura própria; aqui só
# organizamos o que já é feito manualmente pela fazenda.
# ---------------------------------------------------------------------------
class FeriasFuncionario(SQLModel, table=True):
    """Um período de férias gozado (ou a gozar) por uma pessoa, com o valor
    calculado (dias gozados + 1/3 constitucional + abono pecuniário opcional)
    e o respectivo lançamento em Contas a Pagar."""

    __tablename__ = "ferias_funcionario"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    periodo_aquisitivo_inicio: date
    periodo_aquisitivo_fim: date
    dias_direito: int = 30  # dias de férias a que a pessoa tem direito no período aquisitivo
    dias_gozados: int
    data_inicio_gozo: date
    data_fim_gozo: date
    # Dias "vendidos" (abono pecuniário, art. 143 CLT — até 1/3 de dias_direito),
    # opcional — 0 quando a pessoa goza integralmente os dias.
    abono_pecuniario_dias: int = 0
    valor_ferias: float
    valor_terco_constitucional: float
    valor_total: float
    data_pagamento: Optional[date] = None
    status: str = "pendente"  # pendente | pago
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # nº do lançamento (LC-...) criado em Contas a Pagar — mesmo padrão de
    # sincronização usado por FolhaPagamento/EmpreitadaParcela/DiariaPagamento.
    numero_lancamento_gerado: Optional[str] = None
    # Centro de custo da conta a pagar gerada — nasce em "Pecuária Leiteira",
    # mas é editável (mesmo padrão de FolhaPagamento).
    centro_custo: str = "Pecuária Leiteira"


class DecimoTerceiro(SQLModel, table=True):
    """Um lançamento de 13º salário (parcela única, 1ª ou 2ª parcela) de uma
    pessoa, proporcional aos meses trabalhados no ano — com o respectivo
    lançamento em Contas a Pagar."""

    __tablename__ = "decimo_terceiro"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    ano: int
    parcela: str = "unica"  # unica | primeira | segunda
    meses_trabalhados: int  # 1 a 12 — proporcional ao ano de admissão/desligamento
    valor_bruto: float
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    valor_liquido: float
    data_pagamento: Optional[date] = None
    status: str = "pendente"  # pendente | pago
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    numero_lancamento_gerado: Optional[str] = None
    centro_custo: str = "Pecuária Leiteira"


# ---------------------------------------------------------------------------
# Vale de funcionário — adiantamento pago à parte, descontado da folha em uma
# ou mais competências futuras (ver ValeParcela).
# ---------------------------------------------------------------------------
class ValeFuncionario(SQLModel, table=True):
    """Um vale/adiantamento lançado para uma pessoa, com o desconto parcelado na folha."""

    __tablename__ = "vale_funcionario"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    valor_total: float
    forma_pagamento: str  # dinheiro | pix | transferencia | desconto_integral_folha
    data_pagamento: date
    parcelas: int = 1
    competencia_inicio: str = Field(index=True)  # "AAAA-MM" — primeira competência com desconto
    observacao: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None  # nº do documento do pagamento, p/ controle de extrato
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class ValeParcela(SQLModel, table=True):
    """Uma parcela do desconto de um vale — uma linha por competência afetada."""

    __tablename__ = "vale_parcela"

    id: Optional[int] = Field(default=None, primary_key=True)
    vale_id: int = Field(foreign_key="vale_funcionario.id")
    pessoa_id: int = Field(foreign_key="pessoa.id", index=True)
    competencia: str = Field(index=True)  # "AAAA-MM"
    valor: float
    aplicada: bool = False  # já foi somada aos descontos de algum lançamento de folha?
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ValeAvulso(SQLModel, table=True):
    """Vale (adiantamento) para Empreitada/Contrato/Diária — mesma ideia do
    Vale de funcionário, mas sem um documento mensal (`FolhaPagamento`) para
    descontar: aqui o valor é abatido diretamente da(s) próxima(s) parcela(s)/
    etapa(s) pendente(s) (Empreitada/Contrato) ou do saldo devedor acumulado
    (Diária). Ver `_aplicar_vale_avulso` em `routers/cadastro.py`."""

    __tablename__ = "vale_avulso"

    id: Optional[int] = Field(default=None, primary_key=True)
    origem_tipo: str = Field(index=True)  # empreitada | contrato | diaria
    origem_id: int = Field(index=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    valor: float
    forma_pagamento: str  # dinheiro | pix | transferencia | desconto_proximo_pagamento
    data_pagamento: date
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Empreitada — trabalho contratado com um empreiteiro (Pessoa do tipo
# "Empreiteiro"), pago por frequência fixa (mensal/semanal/quinzenal, parcelas
# editáveis como no lançamento financeiro) ou por etapa concluída (cada etapa
# gera uma conta a pagar — e portanto uma pendência de Agenda — no dia 1º do
# mês seguinte à conclusão).
# ---------------------------------------------------------------------------
class Empreitada(SQLModel, table=True):
    """Empreita lançada para um empreiteiro — valor total e forma de pagamento."""

    __tablename__ = "empreitada"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    descricao: str
    valor_total: float
    tipo_pagamento: str  # mensal | semanal | quinzenal | por_etapa
    status: str = "em_andamento"  # em_andamento | concluida
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Centro de custo de todas as contas a pagar geradas por esta empreitada
    # (parcelas ou etapas) — nasce em "Pecuária Leiteira", mas é editável.
    centro_custo: str = "Pecuária Leiteira"


class EmpreitadaParcela(SQLModel, table=True):
    """Parcela de pagamento de uma empreitada com frequência fixa — mesmo
    padrão de parcelamento editável do lançamento financeiro."""

    __tablename__ = "empreitada_parcela"

    id: Optional[int] = Field(default=None, primary_key=True)
    empreitada_id: int = Field(foreign_key="empreitada.id")
    data_vencimento: date
    valor: float
    numero_lancamento_gerado: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class EmpreitadaEtapa(SQLModel, table=True):
    """Etapa de uma empreitada paga por etapa — ao marcar concluída, lança a
    conta a pagar (e portanto a pendência de Agenda) no dia 1º do mês
    seguinte, para análise/pagamento."""

    __tablename__ = "empreitada_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    empreitada_id: int = Field(foreign_key="empreitada.id")
    nome: str
    valor: float
    ordem: int = 0
    concluida: bool = False
    data_conclusao: Optional[date] = None
    numero_lancamento_gerado: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Contrato — valor total pago por frequência fixa (parcelas editáveis, mesmo
# padrão do Financeiro) ou, sem frequência definida, com lembrete mensal na
# Agenda (todo dia 1º) para pagar ou definir uma nova data.
# ---------------------------------------------------------------------------
class Contrato(SQLModel, table=True):
    """Contrato de prestação de serviço/parceria lançado para uma pessoa."""

    __tablename__ = "contrato"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    descricao: str
    valor_total: float
    forma_pagamento: Optional[str] = None  # mensal | quinzenal | semanal | None (sem frequência definida)
    status: str = "ativo"  # ativo | encerrado
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    # Linha-modelo do lembrete mensal na Agenda, criada só quando forma_pagamento é None.
    origem_lembrete_agenda_id: Optional[int] = Field(default=None, foreign_key="agenda_manual.id")
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Centro de custo de todas as contas a pagar geradas por este contrato —
    # nasce em "Pecuária Leiteira", mas é editável.
    centro_custo: str = "Pecuária Leiteira"


class ContratoParcela(SQLModel, table=True):
    """Parcela de pagamento de um contrato com frequência fixa — mesmo padrão
    de parcelamento editável do lançamento financeiro."""

    __tablename__ = "contrato_parcela"

    id: Optional[int] = Field(default=None, primary_key=True)
    contrato_id: int = Field(foreign_key="contrato.id")
    data_vencimento: date
    valor: float
    numero_lancamento_gerado: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Diária — valor da diária + data de início; o sistema conta diariamente até
# hoje e mantém o saldo devedor a partir dos pagamentos registrados.
# ---------------------------------------------------------------------------
class Diaria(SQLModel, table=True):
    """Diarista lançada — valor da diária e data de início da contagem."""

    __tablename__ = "diaria"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    valor_diaria: float
    data_inicio: date
    status: str = "ativo"  # ativo | encerrado
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Centro de custo de todos os pagamentos gerados por esta diária — nasce
    # em "Pecuária Leiteira", mas é editável.
    centro_custo: str = "Pecuária Leiteira"


class DiariaPagamento(SQLModel, table=True):
    """Pagamento registrado para uma diarista — abate o saldo devedor acumulado."""

    __tablename__ = "diaria_pagamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    diaria_id: int = Field(foreign_key="diaria.id")
    data_pagamento: date
    valor: float
    observacao: Optional[str] = None
    numero_lancamento_gerado: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
