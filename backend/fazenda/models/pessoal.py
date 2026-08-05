"""
Pessoal/RH — cadastro de pessoas, folha de pagamento, férias/13º, vales, empreitadas, contratos e diárias.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

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
    # nome era único globalmente — passa a ser único por fazenda (mesmo padrão
    # de TipoServicoReprodutivo), senão a 2ª fazenda nunca conseguiria
    # cadastrar um tipo com o mesmo nome já usado (ex.: "Empreiteiro").
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_tipo_pessoa_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class Pessoa(SQLModel, table=True):
    """Cadastro de pessoas — funcionários e prestadores ligados à fazenda."""

    __tablename__ = "pessoa"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda: nulo para toda pessoa cadastrada
    # antes da migração de backfill (ver fazenda/models/multitenant.py) — só
    # a listagem/cadastro principal (GET/POST /pessoas) considera este campo
    # por enquanto; seletores em outros módulos (veterinário, responsável
    # etc.) ainda enxergam todas as pessoas, independente da fazenda.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    tipo: str  # Funcionário | Veterinário | Zootecnista | Diarista | Prestador de serviços | ... (CSV de TipoPessoa.nome)
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

    # Dados civis + endereço estruturado (decisão jul/2026) — coletados no
    # cadastro de toda pessoa nova a partir de agora, para alimentar o
    # Contrato Assinado (Configurações > Fazendas) sem precisar redigitar.
    # Nome/CPF/endereço já eram (e continuam) obrigatórios para cadastrar
    # (ver criar_pessoa em routers/cadastro/pessoas.py); os demais — RG, data
    # de nascimento, estado civil — são coletados aqui mas só passam a ser
    # exigidos na hora de assinar um contrato, nunca bloqueiam o cadastro.
    # Gênero nunca é obrigatório, em cadastro nem em contrato. Colunas nascem
    # nullable para não quebrar nenhuma Pessoa já cadastrada.
    rg: Optional[str] = None
    data_nascimento: Optional[date] = None
    genero: Optional[str] = None  # texto livre; "" ou None = não informado
    estado_civil: Optional[str] = None
    endereco_rua: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_cidade: Optional[str] = None
    endereco_uf: Optional[str] = None


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    # Conta corrente da fazenda de onde saiu o dinheiro do vale — vínculo
    # RELACIONAL (não string), para sobreviver a renomear/editar a conta
    # depois. Nullable só para não quebrar vales lançados antes desta coluna
    # existir; todo vale novo passa a exigi-lo (ver POST/PUT /vales).
    conta_corrente_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")
    # Número do lançamento (ContaGerencial) gerado automaticamente para este
    # vale — mesmo padrão de FolhaPagamento.numero_lancamento_gerado — para
    # o extrato mostrar a saída de caixa que hoje falta (ver criar_vale).
    numero_lancamento_gerado: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    # Mesmo furo do vale de funcionário, e mesma correção: o dinheiro sai na
    # hora (adiantamento ao empreiteiro/contratado/diarista), mas isso nunca
    # aparecia no extrato — só o abatimento futuro na parcela/etapa final. Ver
    # `conta_corrente_id`/`numero_lancamento_gerado` em ValeFuncionario acima.
    conta_corrente_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")
    numero_lancamento_gerado: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ValeAvulsoAbatimento(SQLModel, table=True):
    """Registro de quanto um `ValeAvulso` abateu de cada parcela/etapa
    pendente, para permitir reverter o efeito exatamente (editar/excluir o
    vale) sem depender de recalcular a partir do zero — ao contrário do vale
    de funcionário (que tem `ValeParcela` recomputável), aqui o abatimento é
    uma mutação direta no valor da parcela/etapa/conta gerencial."""

    __tablename__ = "vale_avulso_abatimento"

    id: Optional[int] = Field(default=None, primary_key=True)
    vale_avulso_id: int = Field(foreign_key="vale_avulso.id", index=True)
    item_tipo: str  # empreitada_parcela | empreitada_etapa | contrato_parcela
    item_id: int
    valor_abatido: float
    criado_em: datetime = Field(default_factory=datetime.utcnow)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Diária — valor da diária + data de início; o sistema conta diariamente até
# hoje e mantém o saldo devedor a partir dos pagamentos registrados.
# ---------------------------------------------------------------------------
class Diaria(SQLModel, table=True):
    """Diarista lançada — valor da diária e data de início da contagem.

    `conta_dia_a_dia` preserva o comportamento histórico (soma automática de
    todos os dias corridos desde `data_inicio`) — sempre True por padrão, para
    não alterar diárias já cadastradas. Quando `auditar_periodicamente` está
    ligado, a Agenda passa a perguntar, na cadência escolhida (ver
    `frequencia_auditoria`), se o diarista realmente trabalhou todos os dias
    do período fechado — a resposta vira uma `DiariaAuditoria` e corrige a
    contagem daquele período (ver `_dias_confirmados_diaria` em
    `routers/cadastro.py`), em vez de presumir cegamente que todo dia corrido
    foi um dia trabalhado."""

    __tablename__ = "diaria"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    valor_diaria: float
    data_inicio: date
    # Data prevista de encerramento (opcional) — quando informada, a Agenda
    # avisa no próprio dia (ver eventos_diaria_fim em routers/agenda.py) e o
    # relatório de estimativa (frontend) usa esta data para projetar
    # quantidade/valor totais mesmo antes de ela chegar.
    data_fim: Optional[date] = None
    status: str = "ativo"  # ativo | encerrado
    # Correção manual do contador de diárias (botão de editar no controle) —
    # substitui, a partir de `ajuste_numero_diarias_em`, a contagem dia a dia
    # que viria de `data_inicio`/auditorias. Ver _resumo_diaria.
    ajuste_numero_diarias: Optional[int] = None
    ajuste_numero_diarias_em: Optional[date] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Centro de custo de todos os pagamentos gerados por esta diária — nasce
    # em "Pecuária Leiteira", mas é editável.
    centro_custo: str = "Pecuária Leiteira"
    # Contagem automática dia a dia (comportamento histórico) — desligar exige
    # lançar manualmente os dias trabalhados (fora do escopo desta 1ª versão;
    # hoje só controla se a auditoria periódica abaixo tem o que corrigir).
    conta_dia_a_dia: bool = True
    # Pergunta periódica na Agenda ("o diarista trabalhou os N dias do
    # período?") — desligada por padrão (não muda nada pra quem já usa o
    # sistema sem configurar nada). Os 3 campos abaixo só importam quando esta
    # flag está ligada; nascem com o valor padrão de `ParametroDiariaPadrao` no
    # cadastro, mas são editáveis por diária.
    auditar_periodicamente: bool = False
    frequencia_auditoria: Optional[str] = None  # semanal | intervalo_dias | mensal
    dia_semana_auditoria: Optional[int] = None  # 0=segunda ... 6=domingo (frequencia == semanal)
    intervalo_dias_auditoria: Optional[int] = None  # frequencia == intervalo_dias
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class DiariaAuditoria(SQLModel, table=True):
    """Uma pendência (e depois, resposta) da auditoria periódica de uma
    diária — um período fechado (ex.: a semana passada) para o qual a Agenda
    perguntou quantos dias o diarista realmente trabalhou. `dias_trabalhados`
    nasce None (pendente); ao responder, vira o número informado (0 a
    `dias_no_periodo`) e a contagem da diária nesse período passa a usar esse
    valor em vez de presumir todos os dias corridos."""

    __tablename__ = "diaria_auditoria"

    id: Optional[int] = Field(default=None, primary_key=True)
    diaria_id: int = Field(foreign_key="diaria.id", index=True)
    periodo_inicio: date
    periodo_fim: date
    dias_trabalhados: Optional[int] = None
    confirmado_em: Optional[datetime] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ParametroDiariaPadrao(SQLModel, table=True):
    """Configuração-padrão da auditoria periódica de diárias, definida em
    Configurações > Parâmetros > Folha de pagamento/RH. Copiada para os campos
    de mesmo nome de `Diaria` no momento do cadastro (ver `criar_diaria` em
    `routers/cadastro.py`) — cada diária pode depois editar a própria
    cadência sem afetar esta configuração global nem as demais diárias.

    Era uma linha única (id=1, mesmo padrão de `AlimentacaoEstado`) — passa a
    ser uma linha por fazenda (lookup por `fazenda_id`, não mais por id fixo),
    já que cada fazenda tem sua própria cadência de auditoria padrão."""

    __tablename__ = "parametro_diaria_padrao"
    __table_args__ = (UniqueConstraint("fazenda_id", name="uq_parametro_diaria_padrao_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    auditar_periodicamente: bool = False
    frequencia_auditoria: str = "semanal"  # semanal | intervalo_dias | mensal
    dia_semana_auditoria: int = 0  # 0=segunda ... 6=domingo
    intervalo_dias_auditoria: int = 7
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class GuiaFolhaEncargo(SQLModel, table=True):
    """Guia de FGTS ou DCTF lançada em Folha de Pagamento > Ações > "Lançar
    guia de FGTS/DCTF" — manual ou pré-preenchida por leitura automática do
    PDF/foto da guia (ver fazenda.rules.leitura_documento, tipo_documento
    'guia_fgts'/'guia_dctf'). Guarda os campos estruturados da guia (não só
    o PDF anexado), para dar pra montar relatório em cima disso depois — o
    PDF original, se enviado, fica vinculado ao mesmo numero_lancamento via
    LancamentoAnexo (mesmo mecanismo de qualquer outro anexo financeiro).
    Substitui o antigo "Gerar guias de FGTS/DCTF" (soma automática projetada
    dos lançamentos de folha, sem vínculo com uma guia real)."""

    __tablename__ = "guia_folha_encargo"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    tipo: str  # "fgts" | "dctf"
    competencia: str  # "AAAA-MM"
    codigo_receita: Optional[str] = None  # só DCTF (código da receita do DARF)
    valor_principal: float
    valor_multa: float = 0.0
    valor_juros: float = 0.0
    valor_total: float
    data_vencimento: date
    linha_digitavel: Optional[str] = None
    # Vínculo com a conta a pagar criada junto (mesmo padrão de LancamentoAnexo)
    # e, por tabela, com qualquer anexo do PDF/foto da guia original.
    numero_lancamento: Optional[str] = Field(default=None, index=True)
    origem: str = "manual"  # "manual" | "leitura_automatica"
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
