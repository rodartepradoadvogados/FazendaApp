"""
Camada de dados — modelos SQLModel (tabelas SQLite/PostgreSQL + validação Pydantic).
Cada modelo representa uma entidade do domínio da fazenda.

NOTA: Relacionamentos usam strings forward-reference para compatibilidade
com SQLModel 0.0.39 + SQLAlchemy 2.x (sem Mapped[] em modelos com table=True).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel


# ---------------------------------------------------------------------------
# Animal
# ---------------------------------------------------------------------------
class Animal(SQLModel, table=True):
    """Foto atual de cada animal — alimentado pelo GERAL.csv."""

    __tablename__ = "animal"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero: str = Field(index=True, unique=True)
    data_nasc: Optional[date] = None
    idade_meses: Optional[float] = None
    grupo_primario: Optional[str] = None
    grupo_raw: Optional[str] = None
    categoria_completa: Optional[str] = None
    categoria_abrev: Optional[str] = None
    raca: Optional[str] = None
    sexo: Optional[str] = None          # "F", "M" ou None (sêmen/reprodutor)
    eh_semen: bool = False              # cadastro de sêmen/reprodutor, não é animal do rebanho
    sit_rep: Optional[str] = None
    del_dias: Optional[int] = None
    data_ult_leite: Optional[date] = None
    ult_cl_kg: Optional[float] = None
    data_ult_diag: Optional[date] = None
    diagnostico: Optional[str] = None
    ativo: bool = True
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    # True após uma movimentação manual de lote (ver MovimentoLote) — impede que
    # o próximo upload do GERAL.csv sobrescreva o lote atual com o valor do Ideagri.
    grupo_manual: bool = False

    # Ficha de cadastro (Configurações > Cadastro) — dados de identificação que
    # não vêm do GERAL.csv, preenchidos manualmente no cadastro do animal.
    nome: Optional[str] = None
    sisbov: Optional[str] = None
    mae_numero: Optional[str] = None
    mae_nome: Optional[str] = None
    proprietario: Optional[str] = None
    valor: Optional[float] = None
    data_entrada: Optional[date] = None
    motivo_baixa: Optional[str] = None
    data_baixa: Optional[date] = None
    observacoes: Optional[str] = None


# ---------------------------------------------------------------------------
# Lote (cadastro + parâmetros para sugestão de movimentação)
# ---------------------------------------------------------------------------
class Lote(SQLModel, table=True):
    """
    Cadastro de lotes de manejo. `codigo` é o código de 2 dígitos usado no
    Ideagri (ex.: "01"); `Animal.grupo_primario` é montado como
    "{codigo} - {nome}" para continuar compatível com os relatórios existentes.
    """

    __tablename__ = "lote"

    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(index=True, unique=True)
    nome: str
    del_min: Optional[int] = None
    del_max: Optional[int] = None  # também usado no critério "até X dias após o parto"
    producao_min: Optional[float] = None  # também usado no critério "produção de X a Y L"
    producao_max: Optional[float] = None
    ativo: bool = True
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)

    # ---- Critérios de seleção de animais (cumulativos/E lógico) — usados na
    # prévia de "quantos animais atendem" e, na sequência, nas sugestões
    # automáticas de movimentação entre lotes. Cada campo None = não filtra.
    status_lactacao: Optional[str] = None  # "lactacao" | "seca"
    categorias: Optional[str] = None  # "vaca,novilha,bezerra" (lista separada por vírgula)
    pre_parto: Optional[bool] = None
    peso_min: Optional[float] = None
    peso_max: Optional[float] = None
    dias_para_parto_min: Optional[int] = None
    dias_para_parto_max: Optional[int] = None
    em_tratamento: Optional[bool] = None
    idade_dias_min: Optional[int] = None
    idade_dias_max: Optional[int] = None
    novilhas_inseminadas: Optional[bool] = None
    novilhas_gestantes: Optional[bool] = None


# ---------------------------------------------------------------------------
# Movimento de lote (histórico de transferências de animais entre lotes)
# ---------------------------------------------------------------------------
class MovimentoLote(SQLModel, table=True):
    """Registro de cada transferência manual de animal entre lotes."""

    __tablename__ = "movimento_lote"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    lote_origem: Optional[str] = None
    lote_destino: str
    data_movimento: date
    hora_movimento: Optional[str] = None
    motivo: str = ""  # opcional no lançamento — "" quando o usuário não escolher nenhum
    observacao: Optional[str] = None
    responsavel: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Serviço (IA / IATF / Cobertura)
# ---------------------------------------------------------------------------
class Servico(SQLModel, table=True):
    """Uma linha da tabela REPRODUTIVO — um serviço por linha."""

    __tablename__ = "servico"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    raca_matriz: Optional[str] = None
    data_nasc_matriz: Optional[date] = None
    data_ult_parto: Optional[date] = None
    ordem_parto: Optional[int] = None
    data_servico: Optional[date] = None
    tipo_servico: Optional[str] = None
    protocolo: Optional[str] = None
    reprodutor: Optional[str] = None
    ordem_tentativa: Optional[int] = None
    intervalo_tentativas: Optional[int] = None
    data_diagnostico: Optional[date] = None
    diagnostico: Optional[str] = None
    data_perda_prenhez: Optional[date] = None
    pev_dias: Optional[int] = None
    del_servico: Optional[int] = None
    ult_ocorrencia: Optional[int] = None
    categoria: Optional[str] = None
    producao_lactacao_anterior: Optional[float] = None
    duracao_lactacao_anterior: Optional[int] = None
    periodo_seco_anterior: Optional[int] = None
    # Diagnóstico positivo marcado para reconfirmar (ainda não é prenhez definitiva)
    # — gera o lembrete de retoque na agenda, na data do próximo serviço.
    retoque: Optional[bool] = None
    # Segundo exame (reconfirmação, ~60 dias do serviço) — distinto do primeiro
    # toque (data_diagnostico/diagnostico) para a agenda do veterinário.
    data_reconfirmacao: Optional[date] = None
    diagnostico_reconfirmacao: Optional[str] = None


# ---------------------------------------------------------------------------
# Parto
# ---------------------------------------------------------------------------
class Parto(SQLModel, table=True):
    """Registro de parto extraído do campo REPRODUTIVO."""

    __tablename__ = "parto"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    data_parto: Optional[date] = None
    ordem_parto: Optional[int] = None
    tipo_parto: Optional[str] = None
    sexo_cria_1: Optional[str] = None
    sexo_cria_2: Optional[str] = None
    gemelar: Optional[bool] = None
    retencao_placenta: Optional[bool] = None


# ---------------------------------------------------------------------------
# Controle Leiteiro
# ---------------------------------------------------------------------------
class ControleLeiteiro(SQLModel, table=True):
    """Uma linha da lista de controles leiteiros por animal."""

    __tablename__ = "controle_leiteiro"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    raca: Optional[str] = None
    data_controle: Optional[date] = None
    producao_kg: Optional[float] = None
    del_no_controle: Optional[int] = None
    data_ult_parto: Optional[date] = None
    ordem_parto: Optional[int] = None
    # Ordenhas individuais do dia (1ª = manhã, 2ª = noite quando só há 2; a
    # 3ª só é preenchida em rotina de 3 ordenhas/dia). producao_kg continua
    # sendo a soma — estes campos existem só para permitir a média por ordenha.
    ordenha1_kg: Optional[float] = None
    ordenha2_kg: Optional[float] = None
    ordenha3_kg: Optional[float] = None


# ---------------------------------------------------------------------------
# Pesagem corporal (peso vivo — acompanhamento de crescimento)
# ---------------------------------------------------------------------------
class PesagemCorporal(SQLModel, table=True):
    """Uma pesagem corporal (peso vivo) de um animal — distinta da pesagem de leite."""

    __tablename__ = "pesagem_corporal"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    data_pesagem: date
    peso_kg: float
    del_dias: Optional[int] = None
    idade_meses: Optional[float] = None
    grupo_primario: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Conta Gerencial (Financeiro)
# ---------------------------------------------------------------------------
class ContaGerencial(SQLModel, table=True):
    """Uma movimentação financeira do CONTA_GERENCIAL.csv."""

    __tablename__ = "conta_gerencial"

    id: Optional[int] = Field(default=None, primary_key=True)
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
    responsavel: Optional[str] = None
    centro_custo: Optional[str] = None
    tipo: Optional[str] = None
    origem: Optional[str] = "csv"  # "csv" (upload) | "manual" (lançamento pela tela)
    # Desconto/acréscimo negociado NA NOTA (produtos → valor bruto → líquido pago/recebido).
    # Diferente de desconto_acrescimo acima, que é a diferença apurada só na baixa do pagamento.
    desconto_nota: Optional[float] = None
    acrescimo_nota: Optional[float] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Item de lançamento financeiro (produto/serviço) — uma nota pode ter vários
# ---------------------------------------------------------------------------
class LancamentoItem(SQLModel, table=True):
    """Um produto/serviço de um lançamento financeiro manual (várias linhas por nota)."""

    __tablename__ = "lancamento_item"

    id: Optional[int] = Field(default=None, primary_key=True)
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
# Plano de Contas Gerenciais
# ---------------------------------------------------------------------------
class PlanoContaGerencial(SQLModel, table=True):
    """Hierarquia do plano de contas gerenciais — LISTA_DE_PLANO_DE_CONTAS_GERENCIAIS.csv."""

    __tablename__ = "plano_conta_gerencial"

    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(index=True, unique=True)
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


# ---------------------------------------------------------------------------
# Conta corrente (Configurações > Parâmetros financeiros) — antes era uma
# lista fixa em Python (CONTAS_BANCARIAS); usada em lançamentos/baixas.
# ---------------------------------------------------------------------------
class ContaCorrente(SQLModel, table=True):
    __tablename__ = "conta_corrente"

    id: Optional[int] = Field(default=None, primary_key=True)
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

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Patrimônio
# ---------------------------------------------------------------------------
class Patrimonio(SQLModel, table=True):
    """Item de patrimônio/imobilizado — LISTA_DE_PATRIMONIO.csv."""

    __tablename__ = "patrimonio"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: Optional[str] = None
    nome: str
    numero: Optional[str] = None
    atividade_cultura: Optional[str] = None
    placa: Optional[str] = None
    data_imobilizacao: Optional[date] = None
    metodo_depreciacao: Optional[str] = None
    vida_util: Optional[str] = None  # texto livre (ex.: "7 Anos")
    valor_residual: Optional[float] = None
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    valor_total: Optional[float] = None
    data_baixa: Optional[date] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Estoque
# ---------------------------------------------------------------------------
class Estoque(SQLModel, table=True):
    """Item de estoque do ESTOQUE.csv."""

    __tablename__ = "estoque"

    id: Optional[int] = Field(default=None, primary_key=True)
    categoria: Optional[str] = None
    numero_produto: Optional[str] = None
    nome: str = Field(index=True)
    quantidade: Optional[float] = None
    estoque_minimo: Optional[float] = None
    unidade: Optional[str] = None
    valor_unitario: Optional[float] = None
    valor_total: Optional[float] = None
    abaixo_minimo: Optional[bool] = None
    local_armazenamento: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)

    # Metadados de cadastro (Configurações > Cadastro), usados pela Alimentação
    # para converter kg necessários em sacos quando o item é ensacado.
    ensacado: Optional[bool] = None
    kg_por_saco: Optional[float] = None
    fornecedor_id: Optional[int] = Field(default=None, foreign_key="fornecedor.id")

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
    exibir_necessidade_compra_agenda: Optional[bool] = None  # abaixo do mínimo -> lembrete na Agenda
    # None/True = estocável (item real de estoque, participa de baixa automática
    # por aplicação/consumo e pode ser doado/recebido de cortesia). False = item
    # cadastrado só para lançamento financeiro (produto de nota), sem controle de quantidade.
    estocavel: Optional[bool] = None


# ---------------------------------------------------------------------------
# Fornecedor / fabricante / cliente
# ---------------------------------------------------------------------------
class Fornecedor(SQLModel, table=True):
    """Cadastro de fornecedores, fabricantes e clientes (Configurações > Cadastro)."""

    __tablename__ = "fornecedor"

    id: Optional[int] = Field(default=None, primary_key=True)
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
# Pessoa (Configurações > Cadastro) — funcionário, veterinário, zootecnista,
# diarista, prestador de serviços. Distinto de Fornecedor: pessoa entra em
# folha de pagamento, não em nota de compra.
# ---------------------------------------------------------------------------
class Pessoa(SQLModel, table=True):
    """Cadastro de pessoas — funcionários e prestadores ligados à fazenda."""

    __tablename__ = "pessoa"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    tipo: str  # Funcionário | Veterinário | Zootecnista | Vet/Zootec. | Diarista | Prestador de serviços
    telefone: Optional[str] = None
    email: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)

    # Referência para o limite de 40% de desconto de vale (ver ValeFuncionario).
    salario_base: Optional[float] = None


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
    valor_liquido: float
    data_pagamento: Optional[date] = None
    status: str = "pendente"  # pendente | pago
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)

    # Recorrência mensal — marca este lançamento como o "modelo" a partir do
    # qual as competências seguintes são geradas automaticamente em Contas a
    # Pagar, sem precisar relançar a folha todo mês (dia_vencimento define o
    # dia do mês da conta a pagar gerada).
    recorrente: bool = False
    dia_vencimento: Optional[int] = None
    origem_recorrencia_id: Optional[int] = None  # id do lançamento-modelo, quando gerado automaticamente
    numero_lancamento_gerado: Optional[str] = None  # nº do lançamento (LC-...) criado em Contas a Pagar


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
    criado_em: datetime = Field(default_factory=datetime.utcnow)


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


# ---------------------------------------------------------------------------
# Movimento de estoque (histórico de entradas/saídas lançadas manualmente)
# ---------------------------------------------------------------------------
class MovimentoEstoque(SQLModel, table=True):
    """Uma entrada ou saída de estoque lançada em Lançamentos > Estoque."""

    __tablename__ = "movimento_estoque"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome_item: str = Field(index=True)
    movimento: str  # "Aplicação" | "Saída de ajuste" | "Entrada de ajuste" | "Entrada de cortesia" | "Doação"
    quantidade: float
    unidade: Optional[str] = None
    data_movimento: date
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


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
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Cadastros de apoio ao Calendário sanitário (Configurações > Cadastro).
# ---------------------------------------------------------------------------
class PrincipioAtivo(SQLModel, table=True):
    __tablename__ = "principio_ativo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Doenca(SQLModel, table=True):
    __tablename__ = "doenca"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class EventoSanitario(SQLModel, table=True):
    """Nome do evento/protocolo sanitário (ex.: Vermífugo, Brucelose B19, Leptospirose)."""

    __tablename__ = "evento_sanitario"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MotivoBaixa(SQLModel, table=True):
    """Causa específica de uma baixa de animal (Rebanho > Baixar animal), cadastrável em Configurações."""

    __tablename__ = "motivo_baixa"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ServicoCadastro(SQLModel, table=True):
    """
    Serviço cadastrável para lançamento financeiro (ex.: manutenção de trator,
    frete, quilometragem) — distinto do modelo `Servico` (serviço/IA reprodutivo).
    """

    __tablename__ = "servico_cadastro"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class CalendarioSanitario(SQLModel, table=True):
    """
    Uma regra do calendário sanitário da fazenda — sazonal/de rebanho (ex.:
    vermífugo a cada 4 meses para bezerras) ou por fase fisiológica (ex.:
    Brucelose B19 no nascimento). `data_evento` é a data de referência; a
    recorrência (frequencia_valor/unidade) projeta a próxima ocorrência.
    """

    __tablename__ = "calendario_sanitario"

    id: Optional[int] = Field(default=None, primary_key=True)
    evento_sanitario_id: int = Field(foreign_key="evento_sanitario.id")
    categoria_alvo: Optional[str] = None  # ex.: "Bezerras (até 4 a 8 meses)"
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")
    produto: Optional[str] = None  # nome do item de estoque (medicamento/vacina)
    principio_ativo_id: Optional[int] = Field(default=None, foreign_key="principio_ativo.id")
    dosagem: Optional[str] = None  # texto livre — ex.: "2 mL a 5 mL (conforme bula)"
    frequencia_valor: int
    frequencia_unidade: str  # "dias" | "meses" | "anos"
    data_evento: date  # data de referência do evento (base da recorrência)
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Protocolo sanitário — cadastro (Configurações > Cadastro > Sanitário) de um
# tratamento com múltiplas etapas (produto/dosagem/via por dia), a exemplo do
# tratamento de mastite. Etapas começam em D1 (protocolos sanitários não têm
# D0 — isso é exclusivo do protocolo hormonal IATF).
# ---------------------------------------------------------------------------
class ProtocoloSanitario(SQLModel, table=True):
    """Um protocolo sanitário cadastrado (ex.: Mastite clínica, Vermifugação padrão)."""

    __tablename__ = "protocolo_sanitario"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")
    eh_mastite: bool = False  # liga o fluxo diferenciado: CMT, teto afetado, classificação
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ProtocoloSanitarioEtapa(SQLModel, table=True):
    """Uma linha do protocolo — produto, dosagem, via e dia de aplicação (D1, D2...)."""

    __tablename__ = "protocolo_sanitario_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_sanitario.id")
    dia: int  # 1, 2, 3... nunca 0
    produto: str
    dosagem: float
    unidade: str
    via: Optional[str] = None


class ProtocoloSanitarioLancamento(SQLModel, table=True):
    """Aplicação de um protocolo a um animal — gera um evento na Agenda por etapa/dia."""

    __tablename__ = "protocolo_sanitario_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_sanitario.id")
    numero_matriz: str = Field(index=True)
    data_inicio: date
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    # Campos específicos de mastite — só usados quando o protocolo é de mastite.
    classificacao_mastite: Optional[str] = None  # "clinica" | "subclinica" | "ambiental"
    resultado_cmt: Optional[str] = None
    tetos_afetados: Optional[str] = None  # ex.: "AE,PD" — quadrantes: AE/AD/PD/PE
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ProtocoloSanitarioAplicacao(SQLModel, table=True):
    """
    Uma etapa (dia) de um lançamento de protocolo — vira evento na Agenda;
    ao marcar "realizado", dá baixa automática do produto no Estoque.
    """

    __tablename__ = "protocolo_sanitario_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_sanitario_lancamento.id")
    etapa_id: int = Field(foreign_key="protocolo_sanitario_etapa.id")
    data_prevista: date
    realizada: bool = False
    data_realizacao: Optional[date] = None


class Secagem(SQLModel, table=True):
    """Registro de secagem de uma vaca — produto(s) usado(s) entram como Sanidade (atividade='Secagem')."""

    __tablename__ = "secagem"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    data_secagem: date
    motivo: str  # doente | baixa_producao | comportamento | mastite | casco | rotina | outros
    escore_condicao_corporal: Optional[float] = None  # 1 a 5, passo 0,25
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Dieta (plano alimentar por lote)
# ---------------------------------------------------------------------------
class Dieta(SQLModel, table=True):
    """Uma linha por (lote, ingrediente) do DIETA.csv — quantidade por cabeça/dia."""

    __tablename__ = "dieta"

    id: Optional[int] = Field(default=None, primary_key=True)
    lote: Optional[int] = Field(default=None, index=True)
    categoria: Optional[str] = None
    ingrediente: str
    quantidade: Optional[float] = None
    unidade: Optional[str] = None  # kg ou L, por cabeça/dia
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Lançamento de dieta (Lançamentos > Alimentação) — histórico por lote, com
# data de abertura/encerramento previsto/efetivo, e a comparação programado
# (nutricionista) × real oferecido. Independente do `Dieta` acima (que segue
# vindo do DIETA.csv e alimentando o painel de Alimentação já existente).
# ---------------------------------------------------------------------------
class DietaLancamento(SQLModel, table=True):
    """Uma dieta lançada para um lote — só uma pode estar ativa por lote."""

    __tablename__ = "dieta_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    lote: int = Field(index=True)
    responsavel: Optional[str] = None  # nutricionista — ex. "Alexandre Scarpa"
    data_abertura: date
    data_prevista_encerramento: Optional[date] = None  # gera evento de análise na Agenda
    data_efetivo_encerramento: Optional[date] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class DietaItemProgramado(SQLModel, table=True):
    """Um alimento do plano formulado (programado) de uma DietaLancamento — quantidade TOTAL do lote/dia."""

    __tablename__ = "dieta_item_programado"

    id: Optional[int] = Field(default=None, primary_key=True)
    dieta_lancamento_id: int = Field(foreign_key="dieta_lancamento.id", index=True)
    alimento: str
    quantidade: float
    unidade: str


class DietaRegistroReal(SQLModel, table=True):
    """O que foi realmente oferecido, por data — comparado ao programado."""

    __tablename__ = "dieta_registro_real"

    id: Optional[int] = Field(default=None, primary_key=True)
    dieta_lancamento_id: int = Field(foreign_key="dieta_lancamento.id", index=True)
    data: date
    alimento: str
    quantidade: float
    unidade: str
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Estado da baixa automática de estoque da Alimentação (linha única, id=1)
# ---------------------------------------------------------------------------
class AlimentacaoEstado(SQLModel, table=True):
    """
    Controla a data da última baixa automática de estoque da Alimentação —
    o sistema recalcula quantos dias se passaram desde então e dá a baixa
    proporcional ao consumo do rebanho (kg/dia) de uma vez, na próxima vez
    que a tela de Alimentação é aberta. `ultima_data_deducao` funciona como
    trava otimista (compare-and-swap): duas requisições concorrentes nunca
    aplicam a mesma baixa duas vezes (ver fazenda/api/routers/alimentacao.py).
    """

    __tablename__ = "alimentacao_estado"

    id: Optional[int] = Field(default=None, primary_key=True)
    ultima_data_deducao: Optional[date] = None


# ---------------------------------------------------------------------------
# Agenda Manual
# ---------------------------------------------------------------------------
class AgendaManual(SQLModel, table=True):
    """Eventos adicionados manualmente — equivalente à aba AGENDA_MANUAL do Excel."""

    __tablename__ = "agenda_manual"

    id: Optional[int] = Field(default=None, primary_key=True)
    data_evento: date
    descricao: str
    categoria: str = "Gestão/Financeiro"
    numero_animal: Optional[str] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Curva ABC (análise de compras / Pareto)
# ---------------------------------------------------------------------------
class CurvaABC(SQLModel, table=True):
    """Linha da CURVA_ABC.csv — classificação A/B/C de produtos/serviços por valor."""

    __tablename__ = "curva_abc"

    id: Optional[int] = Field(default=None, primary_key=True)
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


# ---------------------------------------------------------------------------
# Evento realizado (workflow da agenda)
# ---------------------------------------------------------------------------
class EventoRealizado(SQLModel, table=True):
    """Marca um evento da agenda (identificado por hash estável) como concluído."""

    __tablename__ = "evento_realizado"

    id: Optional[int] = Field(default=None, primary_key=True)
    evento_id: str = Field(index=True, unique=True)
    marcado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Solicitação de exclusão (fluxo de aprovação p/ não-administradores)
# ---------------------------------------------------------------------------
class SolicitacaoExclusao(SQLModel, table=True):
    """
    Pedido de exclusão feito por um operador (não-admin) — fica pendente até
    um administrador aprovar (executa a exclusão de fato) ou rejeitar.
    """

    __tablename__ = "solicitacao_exclusao"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str
    id_alvo: str
    titulo: Optional[str] = None  # descrição do alvo no momento do pedido (snapshot p/ exibição)
    status: str = "pendente"       # pendente | aprovada | rejeitada
    solicitado_por: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    decidido_por: Optional[str] = None
    decidido_em: Optional[datetime] = None
    motivo_rejeicao: Optional[str] = None


# ---------------------------------------------------------------------------
# Usuário (login / controle de acesso)
# ---------------------------------------------------------------------------
class Usuario(SQLModel, table=True):
    """Usuário do sistema. Senha guardada apenas como hash (pbkdf2)."""

    __tablename__ = "usuario"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    nome: Optional[str] = None
    senha_hash: str
    papel: str = "admin"          # admin (tudo + gerencia usuários) | operador
    # Módulos liberados p/ operador, separados por vírgula. Admin ignora (tem tudo).
    permissoes: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Baixa de animal (Rebanho > Baixar animal) — morte/descarte, distinto da
# movimentação entre lotes. Ao registrar, o animal é marcado inativo.
# ---------------------------------------------------------------------------
class BaixaAnimal(SQLModel, table=True):
    """Registro de saída definitiva de um animal do rebanho (óbito/descarte)."""

    __tablename__ = "baixa_animal"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_animal: str = Field(index=True)
    tipo_baixa: str  # morte | descarte_voluntario | descarte_involuntario
    motivo: str      # venda | abate | acidente | doenca
    motivo_doenca: Optional[str] = None  # preenchido só quando motivo == "doenca"
    valor: Optional[float] = None        # preenchido só quando motivo == "venda" — sempre o valor POR ANIMAL já resolvido
    cliente: Optional[str] = None        # preenchido só quando motivo == "venda"
    tipo_valor: Optional[str] = None     # "por_animal" | "total" — como o valor foi originalmente digitado (metadado)
    numero_lancamento_gerado: Optional[str] = None  # LC-... do lançamento financeiro (ContaGerencial) gerado na venda
    data_baixa: date
    observacao: Optional[str] = None
    responsavel: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Compra de animal — entrada de animal no rebanho por aquisição (distinta do
# cadastro/ficha do Animal, que segue seu próprio fluxo de CSV/ficha). Gera
# lançamento financeiro (despesa) e, opcionalmente, comissão de corretagem.
# ---------------------------------------------------------------------------
class CompraAnimal(SQLModel, table=True):
    """Registro de compra de animal — apenas o efeito financeiro/histórico da aquisição."""

    __tablename__ = "compra_animal"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_animal: str = Field(index=True)
    vendedor: str
    valor: float  # valor por animal já resolvido (ver tipo_valor)
    tipo_valor: str  # "por_animal" | "total" — como o valor foi originalmente digitado (metadado)
    data_compra: date
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    numero_lancamento_gerado: Optional[str] = None  # LC-... do lançamento financeiro (ContaGerencial) gerado na compra
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Comissão de corretagem — gerada a partir de uma venda ou compra de animal,
# quando há corretor envolvido. Sempre resulta em uma despesa (ContaGerencial)
# separada e visível, seja "redirecionada" (já paga junto com a transação) ou
# "separada" (conta a pagar em aberto, liquidada depois como qualquer outra).
# ---------------------------------------------------------------------------
class ComissaoCorretagem(SQLModel, table=True):
    """Registro de comissão paga a corretor por uma venda/compra de animal."""

    __tablename__ = "comissao_corretagem"

    id: Optional[int] = Field(default=None, primary_key=True)
    origem_tipo: str  # "venda_animal" | "compra_animal"
    numero_lancamento: str  # LC-... do lançamento de venda/compra ao qual esta comissão se refere
    corretor_nome: str
    valor_comissao: float
    forma: str  # "redirecionado" (já paga junto da transação) | "separado" (conta a pagar em aberto)
    numero_lancamento_comissao: Optional[str] = None  # LC-... da despesa de comissão criada
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Motivo de movimentação de lote — lista editável (Configurações > Cadastro),
# substitui a constante Python fixa que existia antes.
# ---------------------------------------------------------------------------
class MotivoMovimentacao(SQLModel, table=True):
    """Motivo cadastrável de movimentação entre lotes."""

    __tablename__ = "motivo_movimentacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
