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

    # Tipo de vínculo (ago/2026) — hoje só coletado/usado pelo cadastro de
    # Equipe CowData (ver painel_cowdata.py), mas mora aqui (não num modelo
    # à parte) pelo mesmo motivo dos campos civis acima: Pessoa já é o
    # cadastro reaproveitado por Equipe CowData, e nada impede uma
    # fazenda-cliente usar os mesmos campos no futuro. "funcionario" usa
    # salario_base (acima); "pj" usa pagamento_mensal + subtipo_pj.
    tipo_vinculo: Optional[str] = None  # "funcionario" | "pj"
    subtipo_pj: Optional[str] = None  # "MEI" | "ME" | "EPP" | "Outros" — só quando tipo_vinculo="pj"
    pagamento_mensal: Optional[float] = None


# ---------------------------------------------------------------------------
# Documentos anexados à Pessoa — RG, CPF, carteira de trabalho, contratos,
# holerite, comprovantes. Mesmo padrão de PedidoAnexo (fazenda/models/
# financeiro.py): lista fixa de categorias (não uma tabela cadastrável — o
# conjunto é fechado, específico de RH), conteúdo no Supabase Storage (bucket
# `settings.supabase_bucket_financeiro`, mesmo de PedidoAnexo/LancamentoAnexo
# — documento de pessoa é financeiramente adjacente, sem precisar de bucket
# próprio), `data_validade` opcional é dela que a Agenda tira o alerta de
# vencimento (ver fazenda/rules/agenda_engine.py) — só faz sentido para
# "Contrato de trabalho por prazo determinado" na prática, mas o campo fica
# livre para qualquer categoria em que o usuário queira acompanhar validade.
# "Contrato de trabalho por prazo indeterminado" é o funcionário com carteira
# assinada — não pede validade nem documento adicional além do que já existe
# aqui (Carteira de trabalho, Ficha de registro).
CATEGORIAS_PESSOA_ANEXO = [
    "RG", "CPF", "Carteira de trabalho", "Ficha de registro",
    "Contrato de trabalho por prazo indeterminado", "Contrato de trabalho por prazo determinado",
    "Contrato de empreita", "Holerite", "Comprovante de pagamento", "Comprovante de vale",
]


class PessoaAnexo(SQLModel, table=True):
    """Documento anexado a uma Pessoa — ver CATEGORIAS_PESSOA_ANEXO."""

    __tablename__ = "pessoa_anexo"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    pessoa_id: int = Field(foreign_key="pessoa.id", index=True)
    nome_arquivo: str
    mime_type: str
    tamanho_bytes: int
    categoria: str  # um de CATEGORIAS_PESSOA_ANEXO
    data_validade: Optional[date] = None
    caminho_storage: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    # Rubricas avulsas do holerite — vencimentos e descontos que o dono
    # acrescenta linha a linha (ver models/folha_rubrica.py). As DUAS colunas
    # são cache do que as linhas de `FolhaRubrica` somam, mantidas na mesma
    # transação que grava a rubrica, e existem por um motivo cada:
    # - `valor_rubricas` (vencimentos − descontos, pode ser negativo) é o que
    #   permite a fórmula do líquido continuar num lugar só (`_liquido_folha`),
    #   que é função PURA e não tem sessão para reconsultar as rubricas. Sem
    #   ela, todo self-heal que recalcula o líquido (o do vale na listagem, o
    #   de `_corrigir_folha_gerada_sem_retencao`) apagaria em silêncio o
    #   acréscimo que o dono lançou.
    # - `valor_rubricas_tributaveis` é quanto as rubricas SALARIAIS somam à
    #   base das retenções — reembolso e indenização não entram (natureza
    #   indenizatória). É o que faz o rodapé do holerite mostrar a base sobre
    #   a qual o INSS foi de fato calculado, em vez do salário puro.
    valor_rubricas: float = 0.0
    valor_rubricas_tributaveis: float = 0.0
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
    # Conta corrente da fazenda de onde sai o pagamento — vínculo RELACIONAL
    # (não string), mesmo padrão de ValeFuncionario.conta_corrente_id: OPCIONAL
    # (ao contrário do vale, aqui nunca é obrigatória), preenche
    # ContaGerencial.conta_bancaria (o que os relatórios gerenciais filtram) e
    # permite a um formulário de edição pré-selecionar a conta já escolhida.
    conta_corrente_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")

    # ── Discriminação congelada no pagamento (ver `_congelar_discriminacao` e
    #    `estornar_pagamento_folha` em routers/cadastro/rh_folha.py) ──
    # O RECIBO da folha era montado de novo A CADA LEITURA (`_detalhe_folha`
    # consultava `ValeParcela` ao vivo), inclusive para folha JÁ PAGA — mas o
    # `valor_liquido` acima ficou GRAVADO no pagamento e o self-heal
    # (`_corrigir_folha_gerada_sem_retencao`) não toca em folha paga, de
    # propósito. Os dois números chegavam por caminhos diferentes: bastava
    # editar/quitar/estornar um vale, ou remanejar a parcela para outra
    # competência, DEPOIS do pagamento, para o holerite impresso hoje deixar
    # de ser o recibo do que foi efetivamente pago. Num documento trabalhista
    # isso é grave — o holerite é prova.
    # A partir do pagamento, a discriminação que gerou aquele líquido é
    # gravada aqui (JSON com as linhas no formato de `holerite.linha`, mesmo
    # padrão de `Pessoa.telefones`) e passa a ser a FONTE DA VERDADE do recibo
    # daquela folha. Folha não paga continua sendo calculada ao vivo.
    # Mesmo desenho da fotografia de `Diaria.encerramento_*`: congelar no
    # fechamento e só descongelar por um ato explícito — aqui, o estorno do
    # pagamento (`POST /folha-pagamento/{id}/estornar`), nunca em silêncio.
    discriminacao_congelada: Optional[str] = None
    # Marco que separa os dois mundos (o papel de `Diaria.data_encerramento`):
    # NULL numa folha "paga" = pagamento anterior a esta feature ou já
    # estornado, e aí o recibo volta a ser calculado ao vivo, como sempre foi.
    discriminacao_congelada_em: Optional[datetime] = None
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
    # Snapshot do salário usado no cálculo — MESMO motivo de
    # `RescisaoFuncionario.salario_base`, que já fazia certo. Sem ele, o PUT
    # (usado pelo botão "Marcar como pago") recalculava tudo a partir do
    # `Pessoa.salario_base` de HOJE: férias lançadas a R$ 2.666,67 em janeiro
    # viravam R$ 4.000 em março só porque o salário subiu no meio, e a conta
    # a pagar era sobrescrita em silêncio. Nulo só em registro anterior à
    # migração e0b7c3a91d24 que não pôde ser reconstituído.
    salario_base: Optional[float] = None
    valor_ferias: float
    valor_terco_constitucional: float
    # Abono pecuniário (dias vendidos + o respectivo 1/3). ERA CALCULADO E
    # JOGADO FORA: entrava em `valor_total` mas não era gravado, então com
    # abono `valor_ferias + valor_terco_constitucional != valor_total` no
    # banco e o valor não era reconstituível a partir das colunas.
    valor_abono: float = 0.0
    valor_total: float
    data_pagamento: Optional[date] = None
    # pendente | pago | cancelado_rescisao — o último é posto pelo servidor
    # ao FECHAR uma rescisão que absorve estas férias (ver `rescisao_id`);
    # nunca aceito na entrada dos endpoints.
    status: str = "pendente"
    # Rescisão que cancelou este lançamento — o registro NUNCA é apagado,
    # para o cancelamento ser rastreável e reversível.
    rescisao_id: Optional[int] = Field(default=None, foreign_key="rescisao_funcionario.id")
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # nº do lançamento (LC-...) criado em Contas a Pagar — mesmo padrão de
    # sincronização usado por FolhaPagamento/EmpreitadaParcela/DiariaPagamento.
    numero_lancamento_gerado: Optional[str] = None
    # Centro de custo da conta a pagar gerada — nasce em "Pecuária Leiteira",
    # mas é editável (mesmo padrão de FolhaPagamento).
    centro_custo: str = "Pecuária Leiteira"
    # Conta corrente de onde sai o pagamento — ver FolhaPagamento.conta_corrente_id.
    conta_corrente_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")
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
    # Snapshot do salário usado no cálculo — ver FeriasFuncionario.salario_base.
    salario_base: Optional[float] = None
    # 13º INTEGRAL do ano (salario_base / 12 × meses). `valor_bruto` é o que
    # se paga NESTA parcela: até 50% do integral na 1ª (adiantamento, Lei
    # 4.749/1965, art. 2º) e o SALDO na 2ª/única. Antes as duas colunas eram
    # a mesma coisa — `valor_bruto` guardava sempre o integral, e lançar 1ª +
    # 2ª parcela pagava o 13º duas vezes.
    valor_integral: Optional[float] = None
    valor_bruto: float
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    valor_liquido: float
    data_pagamento: Optional[date] = None
    # pendente | pago | cancelado_rescisao — ver FeriasFuncionario.status.
    status: str = "pendente"
    # Rescisão que cancelou este lançamento (o 13º proporcional já está
    # dentro das verbas rescisórias) — ver FeriasFuncionario.rescisao_id.
    rescisao_id: Optional[int] = Field(default=None, foreign_key="rescisao_funcionario.id")
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    numero_lancamento_gerado: Optional[str] = None
    centro_custo: str = "Pecuária Leiteira"
    # Conta corrente de onde sai o pagamento — ver FolhaPagamento.conta_corrente_id.
    conta_corrente_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Rescisão contratual (CLT) — mesma família de férias/13º acima, mas com um
# passo a mais: nasce como `simulacao` (livre para editar/recalcular, nada
# lançado em Financeiro) e só vira lançamento real ao `fechar` (status muda
# para `fechada`, gera 1 ou N ContaGerencial conforme `forma_lancamento`).
# ---------------------------------------------------------------------------
class RescisaoFuncionario(SQLModel, table=True):
    """Uma rescisão contratual (CLT) de uma pessoa — verbas calculadas
    (saldo de salário, aviso prévio, férias vencidas/proporcionais, 13º
    proporcional, multa do FGTS estimada), com deduções (INSS/IR/vale em
    aberto) e o fluxo `simulacao` → `fechada`. Diferente de férias/13º, o
    lançamento em Contas a Pagar só é criado ao FECHAR (a simulação é livre
    para editar/excluir sem gerar nada em Financeiro) — ver
    `_aplicar_calculo_rescisao`/`POST /cadastro/rescisoes/{id}/fechar` em
    `routers/cadastro/rh_folha.py`. Substitui o antigo par
    `GET/POST /cadastro/rescisao` (removido), que só gravava a conta a pagar,
    sem tabela de acompanhamento própria — rescisões criadas por aquele
    endpoint legado continuam visíveis, como registro somente-leitura, na
    listagem nova (ver `legado` no retorno de `GET /cadastro/rescisoes`)."""

    __tablename__ = "rescisao_funcionario"

    id: Optional[int] = Field(default=None, primary_key=True)
    pessoa_id: int = Field(foreign_key="pessoa.id")
    tipo_rescisao: str  # sem_justa_causa | pedido_demissao | justa_causa | acordo_mutuo
    data_desligamento: date
    dias_ferias_vencidas: int = 0
    aviso_previo_trabalhado: bool = False
    # Snapshot do salário/admissão da Pessoa no momento do cálculo — para a
    # simulação/registro fechado não mudar de valor se a Pessoa for editada
    # depois (mesmo motivo de qualquer outro snapshot deste arquivo).
    salario_base: float
    data_admissao: date
    # Seis verbas — cada uma é `override do usuário if informado else valor
    # calculado por calcular_rescisao()` (ver _aplicar_calculo_rescisao).
    valor_saldo_salario: float = 0.0
    valor_aviso_previo: float = 0.0
    valor_ferias_vencidas: float = 0.0
    valor_ferias_proporcionais: float = 0.0
    valor_decimo_terceiro_proporcional: float = 0.0
    valor_multa_fgts: float = 0.0
    # Deduções — sempre informadas pelo usuário (nunca calculadas automaticamente).
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    valor_vale_em_aberto: float = 0.0
    # valor_bruto = soma das 6 verbas; valor_total = bruto - deduções — ambos
    # SEMPRE recomputados pelo servidor (nunca aceitos do cliente).
    valor_bruto: float = 0.0
    valor_total: float = 0.0
    # Metadados de exibição (dias/meses/percentual por trás de cada verba,
    # devolvidos por calcular_rescisao) — guardados para não recalcular ao
    # montar `_detalhe_rescisao`.
    dias_saldo_salario: int = 0
    dias_aviso_previo: int = 0
    dias_aviso_previo_indenizados: int = 0
    meses_ferias_proporcionais: int = 0
    meses_decimo_terceiro: int = 0
    percentual_multa_fgts: float = 0.0
    status: str = "simulacao"  # simulacao | fechada
    forma_lancamento: Optional[str] = None  # unico | detalhado — só definido ao fechar
    data_fechamento: Optional[date] = None
    data_pagamento: Optional[date] = None
    inativou_pessoa: bool = False
    observacao: Optional[str] = None
    # nº do lançamento (LC-...) criado em Contas a Pagar ao fechar — mesmo
    # padrão de FeriasFuncionario/DecimoTerceiro.numero_lancamento_gerado.
    numero_lancamento_gerado: Optional[str] = None
    centro_custo: str = "Pecuária Leiteira"
    # Conta corrente de onde sai o pagamento — ver FolhaPagamento.conta_corrente_id.
    conta_corrente_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
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
    # ── Ações do dono sobre um vale JÁ lançado (Folha de Pagamento > vale >
    # Ações — ver fazenda/api/routers/cadastro/rh_vale_acoes.py) ────────────
    # "ativo" | "cancelado". Cancelar NÃO apaga o vale (diferente de
    # DELETE /vales, que é "isto nunca deveria ter existido"): o dinheiro
    # saiu de verdade e o histórico continua valendo — o que muda é que o
    # saldo pendente deixa de ser cobrança do funcionário e passa a ser
    # despesa assumida pela fazenda. Por isso é coluna de estado, não
    # exclusão.
    status: str = Field(default="ativo", index=True)
    # Acumuladores das ações, PARA O HISTÓRICO — `valor_total` nunca muda
    # (é o valor efetivamente adiantado à pessoa, mesma regra que
    # `editar_parcela_vale` já seguia): `valor_abatido` é o que o
    # funcionário devolveu/o dono perdoou, `valor_assumido_fazenda` é o que
    # deixou de ser cobrado dele porque a fazenda assumiu (desconsiderar o
    # mês / cancelar o vale). Sem eles, a soma das parcelas divergiria do
    # valor pago sem dizer POR QUE divergiu.
    valor_abatido: float = 0.0
    valor_assumido_fazenda: float = 0.0
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
    # Parcela que o dono mandou DESCONSIDERAR neste mês (ou que foi varrida
    # junto com o cancelamento do vale): continua existindo — a competência,
    # o valor e o motivo são o registro de que aquele mês foi perdoado —, mas
    # NÃO é descontada do funcionário: `_valor_vale` (rh_folha.py) ignora
    # estas parcelas, e o valor correspondente vira despesa da fazenda no
    # Financeiro. Apagar a parcela seria mais simples e é justamente o que
    # não serve: sem ela o holerite do mês não teria como explicar por que o
    # desconto sumiu.
    assumida_pela_fazenda: bool = False
    motivo_assuncao: Optional[str] = None
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
    uma mutação direta no valor da parcela/etapa/conta gerencial.

    `fazenda_id`: espelha `ValeAvulso.fazenda_id` do pai (backfill por join)
    — sem ela, o motor de replicação Fazenda -> Fazenda (que descobre o que
    copiar por `fazenda_id` presente na tabela) não enxergava este registro
    e a Fazenda Teste ficava com o vale copiado mas sem o abatimento já
    aplicado nele."""

    __tablename__ = "vale_avulso_abatimento"

    id: Optional[int] = Field(default=None, primary_key=True)
    vale_avulso_id: int = Field(foreign_key="vale_avulso.id", index=True)
    item_tipo: str  # empreitada_parcela | empreitada_etapa | contrato_parcela
    item_id: int
    valor_abatido: float
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    padrão de parcelamento editável do lançamento financeiro.

    `numero`/`numero_total` = "parcela k de n", CONGELADOS na criação. Antes
    não existiam: a tela numerava pela posição na lista ordenada por
    vencimento, então excluir a parcela 3 de 5 fazia a 4 virar "3" e todo
    recibo já impresso ("vale referente à parcela 3 de 5") passava a apontar
    para outra parcela. Com o número gravado, a exclusão deixa o buraco
    honesto (1, 2, 4, 5 de 5) e nada é renumerado.

    `valor_contratado` = o BRUTO acordado nesta parcela; `valor` = o que
    sobra a pagar depois dos vales adiantados (ver `_aplicar_vale_avulso`).
    Precisa ser um campo PERSISTIDO, não reconstruído: a tentação é dizer
    que `bruto = valor + Σ ValeAvulsoAbatimento`, e isso QUEBRA — a
    redistribuição (`_redistribuir_parcelas_pendentes` /
    `_redistribuir_itens_pendentes_*`) reescreve `valor` sem tocar em
    nenhum `ValeAvulsoAbatimento`, então depois dela a soma não fecha mais.
    Por isso a redistribuição nunca reescreve este campo."""

    __tablename__ = "empreitada_parcela"

    id: Optional[int] = Field(default=None, primary_key=True)
    empreitada_id: int = Field(foreign_key="empreitada.id")
    data_vencimento: date
    valor: float
    numero: Optional[int] = None
    numero_total: Optional[int] = None
    valor_contratado: Optional[float] = None
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
    de parcelamento editável do lançamento financeiro.

    `numero`/`numero_total`/`valor_contratado`: mesma semântica (e mesmo
    motivo) de EmpreitadaParcela acima — ver o docstring de lá."""

    __tablename__ = "contrato_parcela"

    id: Optional[int] = Field(default=None, primary_key=True)
    contrato_id: int = Field(foreign_key="contrato.id")
    data_vencimento: date
    valor: float
    numero: Optional[int] = None
    numero_total: Optional[int] = None
    valor_contratado: Optional[float] = None
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
    # ── Encerramento do período (ver `encerrar_diaria`/`reabrir_diaria`) ──
    # `data_encerramento` é o ÚLTIMO DIA TRABALHADO informado no fechamento
    # (e copiado para `data_fim`, que é quem faz o contador parar). Ele
    # também é o marco que diz se este encerramento é dos novos: NULL numa
    # diária com status "encerrado" = fechamento antigo, de antes desta
    # feature, que continua 100% na regra de sempre (`_resumo_diaria`
    # recalcula tudo) — sem retroatividade.
    data_encerramento: Optional[date] = None
    # Conta a pagar emitida no encerramento (receita canônica do projeto:
    # `_proximo_numero_lancamento` + ContaGerencial tipo="despesa"/
    # origem="auto" — o mesmo que `concluir_etapa_empreitada` faz). É o elo
    # que faltava: sem ele o saldo devedor de um período encerrado ficava
    # registrado só aqui e NUNCA aparecia na Agenda nem em Contas a Pagar.
    numero_lancamento_gerado: Optional[str] = None
    # Fotografia congelada no fechamento. Existe porque o resumo era todo
    # recalculado a cada leitura: uma auditoria respondida depois, um dia
    # corrigido no calendário ou um vale novo mudavam sozinhos o valor de um
    # período já FECHADO — e portanto divergiam da conta a pagar já emitida,
    # que ninguém reescreve. A partir do encerramento, `_resumo_diaria` LÊ
    # estes números em vez de recalcular.
    encerramento_numero_diarias: Optional[float] = None
    encerramento_total_apurado: Optional[float] = None
    encerramento_valor_pago: Optional[float] = None
    encerramento_valor_vale: Optional[float] = None
    encerramento_saldo_devedor: Optional[float] = None
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
    # Marco do controle por calendário: NULL = esta diária nunca passou pelo
    # calendário de dias trabalhados e continua 100% na regra antiga
    # (auditorias agregadas + ajuste manual + contagem cega). Quando o usuário
    # salva o calendário pela primeira vez, vira a data mais antiga já coberta
    # por um envio — a partir dela quem manda é DiariaDia; antes dela, o
    # histórico legado permanece intacto. Só anda para trás, nunca para frente.
    controle_por_dia_desde: Optional[date] = None


class DiariaPagamento(SQLModel, table=True):
    """Pagamento registrado para uma diarista — abate o saldo devedor acumulado."""

    __tablename__ = "diaria_pagamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    diaria_id: int = Field(foreign_key="diaria.id")
    data_pagamento: date
    valor: float
    observacao: Optional[str] = None
    numero_lancamento_gerado: Optional[str] = None
    # Conta corrente de onde sai o pagamento — ver FolhaPagamento.conta_corrente_id.
    conta_corrente_id: Optional[int] = Field(default=None, foreign_key="conta_corrente.id")
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


class DiariaDia(SQLModel, table=True):
    """Exceção do dia a dia de uma diária — só existe linha para o dia que
    FOGE do padrão. Sem linha = dia trabalhado (o calendário nasce todo
    marcado, e o usuário só toca no dia em que o diarista não veio)."""
    __tablename__ = "diaria_dia"
    __table_args__ = (UniqueConstraint("diaria_id", "data", name="uq_diaria_dia_diaria_data"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    diaria_id: int = Field(foreign_key="diaria.id", index=True)
    data: date = Field(index=True)
    trabalhado: bool = False
    # Fração da diária cumprida neste dia (0 a 1) — None em linhas antigas
    # (só existiam folgas antes desta feature) equivale a 0.0, o mesmo que
    # `trabalhado=False` já significava. 0.5 = meia diária (metade do valor);
    # ver `_fracao_dia` em routers/cadastro/rh_contratos.py. Uma linha de dia
    # CHEIO nunca é gravada (o calendário é esparso — ausência de linha já
    # significa dia cheio), então `trabalhado` continua sempre False em toda
    # linha existente; ele fica só por compatibilidade com dado histórico.
    fracao: Optional[float] = None
    observacao: Optional[str] = None
    registrado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
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
