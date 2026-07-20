"""
Camada de dados — modelos SQLModel (tabelas SQLite/PostgreSQL + validação Pydantic).
Cada modelo representa uma entidade do domínio da fazenda.

NOTA: Relacionamentos usam strings forward-reference para compatibilidade
com SQLModel 0.0.39 + SQLAlchemy 2.x (sem Mapped[] em modelos com table=True).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger
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
    # Grau de sangue / composição racial (ex.: "1/2 Holandês x Gir", "3/4 Holandês",
    # "PO Holandês"). Livre, com opções padrão sugeridas no cadastro.
    grau_sangue: Optional[str] = None
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
    # Pai cadastrado manualmente (touro da fazenda, sêmen em estoque ou catálogo
    # NAAB) — usado quando não é possível derivar o pai automaticamente a partir
    # do serviço/parto da mãe (animal comprado, ou anterior ao uso do sistema).
    # Tem prioridade sobre a derivação automática em ficha_animal().
    pai_nome: Optional[str] = None
    pai_naab: Optional[str] = None
    # Genealogia paterna — preenchida automaticamente quando o pai (ou o avô)
    # também está cadastrado como Animal com sua própria genealogia; senão fica
    # disponível para seleção manual no cadastro.
    avo_paterno_nome: Optional[str] = None
    avo_paterno_naab: Optional[str] = None
    bisavo_paterno_nome: Optional[str] = None
    bisavo_paterno_naab: Optional[str] = None
    proprietario: Optional[str] = None
    valor: Optional[float] = None
    data_entrada: Optional[date] = None
    motivo_baixa: Optional[str] = None
    data_baixa: Optional[date] = None
    observacoes: Optional[str] = None
    # "A descartar": a vaca segue ativa no rebanho (ordenha, sanidade), mas sai
    # de todas as ações reprodutivas (IATF, inseminação, candidatas) — marcada
    # para descarte futuro sem dar baixa definitiva.
    a_descartar: bool = False
    # Marca manual: nunca entra nas listas de candidatas/excluídos do BST
    # (ex.: vaca com contraindicação), independente dos critérios automáticos.
    excluir_bst: bool = False


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
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    # Sêmen sexado x convencional (ou monta natural, tipo "fazenda") — gravado no
    # momento da inseminação para o histórico não depender de recasar o nome do
    # touro com o Estoque de Sêmen depois (que pode mudar de tipo com o tempo).
    tipo_semen: Optional[str] = None  # convencional | sexado | fazenda
    inseminador: Optional[str] = None  # quem fez a IA/cobertura (responsável)
    ordem_tentativa: Optional[int] = None
    intervalo_tentativas: Optional[int] = None
    data_diagnostico: Optional[date] = None
    diagnostico: Optional[str] = None  # POSITIVO | NEGATIVO | INDEFINIDO
    metodo_diagnostico: Optional[str] = None  # Palpação | Ultrassom | Cio de repasse
    data_perda_prenhez: Optional[date] = None
    motivo_perda_prenhez: Optional[str] = None  # aborto | natimorto | outros
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
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Tipo de serviço / Método reprodutivo — cadastro (Configurações > Cadastro)
# do vocabulário usado no lançamento de Serviço/Inseminação. Um Método sempre
# pertence a um Tipo de serviço (ex.: "Monta Natural" → Cobertura; "IA em cio
# natural" e "IATF" → IA). `codigo_interno` identifica os 3 métodos que o
# motor de lançamento/análise reprodutiva já sabe tratar de forma especial
# (nenhum novo método customizado tem código — fica só informativo/rótulo).
# ---------------------------------------------------------------------------
class TipoServicoReprodutivo(SQLModel, table=True):
    """Tipo de serviço reprodutivo cadastrado (ex.: Cobertura, IA)."""

    __tablename__ = "tipo_servico_reprodutivo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MetodoServicoReprodutivo(SQLModel, table=True):
    """Método de um tipo de serviço (ex.: Monta Natural, IA em cio natural, IATF)."""

    __tablename__ = "metodo_servico_reprodutivo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    tipo_servico_id: int = Field(foreign_key="tipo_servico_reprodutivo.id")
    codigo_interno: Optional[str] = None  # "monta_natural" | "cio_natural" | "iatf" | None (customizado)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Protocolo IATF — lançamento do protocolo hormonal (D0/D7/D9/D11) em um ou
# vários animais de uma vez. Cada etapa de cada animal vira uma "aplicação"
# rastreável (aparece agrupada na Agenda, marcada como realizada individualmente).
# A inseminação em si (D11) continua sendo lançada à parte em Servico — ver
# fazenda.api.routers.reproducao.registrar_servico, que resolve a aplicação
# de D11 correspondente automaticamente quando o protocolo é informado.
# ---------------------------------------------------------------------------
class ProtocoloIatfLancamento(SQLModel, table=True):
    """Um lançamento de protocolo IATF em lote — o "cabeçalho" (nome + data do D0)."""

    __tablename__ = "protocolo_iatf_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome_protocolo: str
    data_d0: date
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    # Lançado retroativamente (D0 no passado, a partir de uma inseminação IATF
    # sem protocolo). As etapas vencidas destes aparecem como PENDÊNCIA na
    # agenda; nos protocolos normais, etapas já passadas ficam escondidas.
    retroativo: bool = Field(default=False)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class ProtocoloIatfAplicacao(SQLModel, table=True):
    """Uma etapa (D0/D7/D9/D11) de um animal dentro de um lançamento de protocolo IATF."""

    __tablename__ = "protocolo_iatf_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_iatf_lancamento.id")
    numero_matriz: str = Field(index=True)
    dia: int  # 0, 7, 9 ou 11
    descricao: str  # hormônio/ação do dia (D11 = "Inseminação (IATF)")
    data_prevista: date
    realizada: bool = False
    data_realizacao: Optional[date] = None


class ProtocoloIatfHormonio(SQLModel, table=True):
    """
    Medicamento(s) aplicado(s) num dia do protocolo IATF (ex.: D0 = 1ml SincroCP
    + 2ml Estron). Definido uma vez por lançamento/dia e aplicado a todas as
    vacas daquele passo. Ao confirmar o dia, dá baixa de estoque e registra a
    aplicação em Sanidade para cada vaca.
    """

    __tablename__ = "protocolo_iatf_hormonio"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_iatf_lancamento.id", index=True)
    dia: int
    produto: str
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None


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
    # Números das crias nascidas (para abrir a ficha da cria a partir do parto).
    numero_cria_1: Optional[str] = None
    numero_cria_2: Optional[str] = None
    gemelar: Optional[bool] = None
    # Combinação de sexos de um parto gemelar: "FF" | "FM" | "MM". Em FM, a fêmea
    # costuma ser freemartin (infértil) — informação útil no descarte precoce.
    gemelar_sexo: Optional[str] = None
    retencao_placenta: Optional[bool] = None
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Colostragem e teste de sangue (IgG) da cria — histórico sanitário usado no
# relatório de bezerras (Sanidade). Uma linha por animal, atualizável conforme
# os dados vão sendo colhidos (colostro no nascimento, teste de sangue 24-48h
# depois).
# ---------------------------------------------------------------------------
class ColostragemBezerra(SQLModel, table=True):
    """Registro de colostragem e teste de sangue (IgG) de uma cria."""

    __tablename__ = "colostragem_bezerra"

    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_animal: str = Field(index=True, unique=True)
    tomou_colostro: Optional[bool] = None
    litros_colostro: Optional[float] = None
    brix_colostro: Optional[float] = None  # Ouro >25% · Prata 18-25% · Bronze <18%
    data_colostro: Optional[date] = None
    hora_parto: Optional[str] = None       # "HH:MM" — hora do parto
    hora_colostro: Optional[str] = None    # "HH:MM" — hora do 1º oferecimento de colostro
    peso_nascer_kg: Optional[float] = None # peso do animal ao nascer
    brix_soro: Optional[float] = None  # teste de sangue: Brix sérico (refratômetro)
    proteina_serica: Optional[float] = None  # teste de sangue: proteína sérica total (g/dL)
    # True = bezerra que recebeu somente colostro em pó (sem colostro materno);
    # entra em grupo próprio no relatório de eficiência de colostragem.
    apenas_colostro_po: Optional[bool] = None
    data_teste_sangue: Optional[date] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    # Fase da vaca na data da pesagem, para pesos de transição:
    # "pre_parto" (<=30 dias do parto previsto), "vaca_seca" (31-60 dias antes),
    # "pos_parto" (recém-parida) ou None (fora de transição / recria).
    fase: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class AgendamentoPesagem(SQLModel, table=True):
    """
    Acompanhamento da evolução de peso do rebanho: define a periodicidade de
    pesagem de uma fase (ex.: bezerras até desmama, de 15 em 15 dias, às terças).
    Alimenta a Agenda dos funcionários com o lembrete de pesagem no dia certo.
    """

    __tablename__ = "agendamento_pesagem"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)  # ex.: "Bezerras até desmama"
    ativo: bool = True
    # Alvo por idade (dias) — animais dentro da faixa entram na pesagem.
    idade_min_dias: Optional[int] = None
    idade_max_dias: Optional[int] = None
    categoria_alvo: Optional[str] = None  # opcional: casa também pela categoria_abrev
    # Periodicidade + dia da semana fixo (0=segunda … 6=domingo; terça=1).
    frequencia_valor: int = 15
    frequencia_unidade: str = "dias"  # "dias" | "meses"
    dia_semana: int = 1
    data_referencia: date  # 1ª pesagem (âncora da cadência)
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class QualidadeLeite(SQLModel, table=True):
    """
    Uma coleta de qualidade do leite — do tanque (todo o rebanho em lactação,
    numero_matriz vazio) ou de uma vaca específica (ex.: investigação de mastite).
    """

    __tablename__ = "qualidade_leite"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: Optional[str] = Field(default=None, index=True)
    data_coleta: date
    ccs: Optional[float] = None  # células somáticas (mil/mL)
    cbt: Optional[float] = None  # contagem bacteriana total (mil UFC/mL)
    gordura_pct: Optional[float] = None
    proteina_pct: Optional[float] = None
    solidos_totais_pct: Optional[float] = None
    esd_pct: Optional[float] = None  # extrato seco desengordurado
    lactose_pct: Optional[float] = None
    nul: Optional[float] = None  # Nitrogênio Ureico no Leite / MUN (mg/dL)
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class EntregaLeiteMensal(SQLModel, table=True):
    """Volume de leite entregue ao laticínio em um mês (competência), para
    comparar com o controle leiteiro projetado e a receita informada pelo laticínio."""

    __tablename__ = "entrega_leite_mensal"

    id: Optional[int] = Field(default=None, primary_key=True)
    competencia: str = Field(index=True)  # "YYYY-MM"
    quantidade_litros: float
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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

    # Natureza do lançamento aceito por esta conta — "servico" | "produto" | "ambos".
    # Restringe, em Financeiro > Contas a pagar/a receber, se o item do lançamento
    # pode ser um serviço, um produto, ou os dois (ver FormFinanceiro/SeletorContaGerencial).
    natureza: Optional[str] = None


class SeedFlag(SQLModel, table=True):
    """Marcador de migração/seed de dados executado uma única vez.

    Usado por normalizações que devem rodar só na primeira inicialização
    (ex.: ativar todas as contas gerenciais) e nunca sobrescrever ajustes
    manuais feitos depois pelo usuário.
    """

    __tablename__ = "seed_flag"

    chave: str = Field(primary_key=True)
    aplicado_em: datetime = Field(default_factory=datetime.utcnow)


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
# Tipo de documento e forma de pagamento (Configurações > Parâmetros
# financeiros) — antes eram listas fixas em Python (TIPOS_DOCUMENTO,
# FORMAS_PAGAMENTO em fazenda.api.routers.financeiro); agora cadastráveis,
# no mesmo padrão de CentroCusto/ContaCorrente.
# ---------------------------------------------------------------------------
class TipoDocumento(SQLModel, table=True):
    __tablename__ = "tipo_documento"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FormaPagamentoCadastro(SQLModel, table=True):
    __tablename__ = "forma_pagamento_cadastro"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
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
    nome: str
    tipo: str = "personalizado"  # "otimista" | "realista" | "pessimista" | "personalizado"
    observacao: Optional[str] = None
    ativo: bool = True
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class PlanejamentoItem(SQLModel, table=True):
    __tablename__ = "planejamento_item"

    id: Optional[int] = Field(default=None, primary_key=True)
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

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_pedido: str = Field(index=True, unique=True)
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
# Estoque
# ---------------------------------------------------------------------------
class Estoque(SQLModel, table=True):
    """Item de estoque do ESTOQUE.csv."""

    __tablename__ = "estoque"

    id: Optional[int] = Field(default=None, primary_key=True)
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


class TelegramPendente(SQLModel, table=True):
    """Documento recebido pelo robô do Telegram, aguardando o usuário responder
    se é receita ou despesa antes de virar um lançamento financeiro. Depois de
    lido (`tipo`/`dados_lidos` preenchidos), continua vivo até o usuário
    confirmar/corrigir/cancelar — só aí vira (ou não) um LancamentoPendente."""

    __tablename__ = "telegram_pendente"

    id: Optional[int] = Field(default=None, primary_key=True)
    # BigInteger: ids de chat do Telegram passam de 2,1 bi (não cabem em INTEGER).
    chat_id: int = Field(sa_type=BigInteger, index=True)  # de quem recebeu (para responder)
    file_id: str                         # id do arquivo no Telegram (para baixar)
    file_name: Optional[str] = None
    mime: Optional[str] = None
    kind: str                            # "xml" | "documento"
    tipo: Optional[str] = None           # "receita" | "despesa" — preenchido após a escolha
    dados_lidos: Optional[str] = None    # JSON já extraído do documento, aguardando confirmação
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class TelegramSessao(SQLModel, table=True):
    """Estado da conversa de um chat no robô: qual lançamento está sendo
    preenchido, em que etapa e os dados já coletados (JSON)."""

    __tablename__ = "telegram_sessao"

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(sa_type=BigInteger, index=True, unique=True)
    fluxo: Optional[str] = None          # tipo de lançamento em andamento
    etapa: int = 0                       # índice da pergunta atual
    dados: str = "{}"                    # JSON acumulado dos campos respondidos
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class LancamentoPendente(SQLModel, table=True):
    """Lançamento operacional (pesagem, parto, secagem, troca de lote…) enviado
    pelo Telegram e aguardando aprovação da conta principal antes de virar um
    registro real no sistema."""

    __tablename__ = "lancamento_pendente"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str = Field(index=True)        # controle_leiteiro | parto | secagem | ...
    payload: str = "{}"                  # JSON dos campos coletados
    resumo: str = ""                     # texto legível para a tela de aprovação
    solicitante_chat_id: Optional[int] = Field(default=None, sa_type=BigInteger)
    solicitante_nome: Optional[str] = None
    status: str = Field(default="pendente", index=True)  # pendente | aprovado | rejeitado
    erro: Optional[str] = None           # mensagem se a materialização falhar
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    decidido_em: Optional[datetime] = None
    decidido_por: Optional[str] = None   # username de quem aprovou/rejeitou


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
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Vínculo opcional ao Pedido de compra que esta entrada física está
    # atendendo — é só quando esse vínculo existe que o Pedido passa a
    # refletir em Estoque (ver Pedido/PedidoItem).
    pedido_id: Optional[int] = Field(default=None, foreign_key="pedido.id")
    pedido_item_id: Optional[int] = Field(default=None, foreign_key="pedido_item.id")


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
    # "curativo" | "preventivo" — distingue o lançamento avulso (Curativa) da
    # aplicação que veio de uma regra do calendário sanitário (Preventiva).
    # None (dado legado/importado do CSV) é tratado como "curativo" na leitura.
    natureza: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Origem da aplicação quando veio da confirmação de um protocolo agrupado —
    # permite excluir o lançamento inteiro (protocolo + agenda + Sanidade) de uma vez.
    protocolo_sanitario_lancamento_id: Optional[int] = Field(default=None, foreign_key="protocolo_sanitario_lancamento.id")
    protocolo_iatf_lancamento_id: Optional[int] = Field(default=None, foreign_key="protocolo_iatf_lancamento.id")
    # Avaliação de cura, pedida na Agenda no dia seguinte a uma aplicação
    # curativa (None = ainda não respondida). Alimenta o relatório Taxa de cura.
    curada: Optional[bool] = None


class AplicacaoAgendada(SQLModel, table=True):
    """
    Aplicação de medicamento lançada mas ainda NÃO aplicada (programada para o
    futuro ou marcada "aplicado? não"). Fica pendente na Agenda — nada é baixado
    do estoque até ser confirmada ("dar baixa"), quando vira um registro de
    Sanidade de verdade e dá a saída de estoque. Espelha "contas a pagar".
    """

    __tablename__ = "aplicacao_agendada"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    data: date = Field(index=True)  # data prevista da aplicação
    produto: str
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    aplicado: bool = Field(default=False, index=True)
    data_aplicacao: Optional[date] = None
    # "curativo" | "preventivo" — propagado para o Sanidade.natureza quando a
    # pendência é confirmada (ver _baixar_aplicacao_agendada).
    natureza: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Cadastros de apoio ao Calendário sanitário (Configurações > Cadastro).
# ---------------------------------------------------------------------------
class PrincipioAtivo(SQLModel, table=True):
    """Espinha dorsal da farmácia: o princípio ativo (ou, para biológicos, o
    antígeno/doença combatida). Marcas comerciais e itens de estoque penduram
    aqui. O somatório de estoque e o alerta de mínimo são calculados no nível do
    princípio (ver rules/farmacia)."""

    __tablename__ = "principio_ativo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    # Enriquecimento (documento base de princípios ativos).
    categoria: Optional[str] = None  # grupo amplo do documento base, ex.: "Antimicrobianos e Antibióticos", "Biológicos (Vacinas e Diagnósticos)"
    categoria_software: Optional[str] = None  # ex.: "Antimicrobiano Sistêmico Injetável", "AINE", "Biológico (Vacina)"
    uso_principal: Optional[str] = None
    justificativa: Optional[str] = None
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")  # p/ biológicos: doença combatida
    eh_biologico: bool = False  # antígeno/vacina/diagnóstico (agrupado por doença, não por molécula)
    # Unificação de volumes: unidade canônica em que o saldo das apresentações é
    # somado (ml, L, dose, unidade, g). O mínimo é medido em "apresentações
    # primárias" (frascos/potes/seringas): padrão 1.
    unidade_base: Optional[str] = None            # ml | L | dose | unidade | g
    unidade_apresentacao: Optional[str] = None    # frasco | seringa | dose | dispositivo | pote | galão | caixa
    estoque_minimo_apresentacoes: float = 1.0
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MedicamentoComercial(SQLModel, table=True):
    """Marca comercial + laboratório de um princípio ativo (tabela filha). Ex.:
    Maxicam 2%/Ourofino → Meloxicam. Catálogo relacional; um item de estoque
    físico referencia uma marca (ou pelo menos o princípio)."""

    __tablename__ = "medicamento_comercial"

    id: Optional[int] = Field(default=None, primary_key=True)
    principio_ativo_id: int = Field(foreign_key="principio_ativo.id", index=True)
    nome_comercial: str = Field(index=True)
    laboratorio: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Doenca(SQLModel, table=True):
    __tablename__ = "doenca"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ExameDefinicao(SQLModel, table=True):
    """
    Cadastro de um exame (ex.: Tuberculose, Brucelose) para o calendário
    sanitário preventivo — define como o RESULTADO é lançado: por
    diagnóstico (positivo/negativo/indefinido) ou numérico (faixa de x até
    y, com o que fazer abaixo/dentro/acima dela). Vinculado ao princípio
    ativo do exame. Consumido em Lançamentos > Sanitário > Preventivo — o
    lançamento de exame nunca gera aplicação de medicamento nem baixa de
    estoque (ver EventoSanitario.categoria_preventiva == "exame").
    """

    __tablename__ = "exame_definicao"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    principio_ativo_id: Optional[int] = Field(default=None, foreign_key="principio_ativo.id")
    tipo_resultado: str = "diagnostico"  # "diagnostico" | "numerico"
    # tipo_resultado == "numerico": faixa [faixa_min, faixa_max] e o que fazer
    # abaixo/dentro/acima dela — texto livre (orientação, não muda o rebanho).
    faixa_min: Optional[float] = None
    faixa_max: Optional[float] = None
    acao_abaixo: Optional[str] = None
    acao_dentro: Optional[str] = None
    acao_acima: Optional[str] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ExameResultado(SQLModel, table=True):
    """
    Resultado de um exame preventivo por animal (ex.: tuberculose,
    brucelose), lançado junto com o calendário sanitário preventivo (ver
    cadastrar_preventivo). Diagnóstico: positivo marca Animal.a_descartar
    automaticamente; negativo é informativo ("liberada"); indefinido marca
    para repetir o exame — ambos só para fins de relatório. Numérico: valor
    + banda (abaixo/dentro/acima da faixa do ExameDefinicao vinculado).
    Nunca gera aplicação de medicamento nem baixa de estoque.
    """

    __tablename__ = "exame_resultado"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    evento_sanitario_id: int = Field(foreign_key="evento_sanitario.id")
    exame_definicao_id: Optional[int] = Field(default=None, foreign_key="exame_definicao.id")
    data_exame: date
    resultado: Optional[str] = None  # diagnóstico: "positivo" | "negativo" | "indefinido"
    valor_numerico: Optional[float] = None  # numérico: valor lançado
    banda: Optional[str] = None  # numérico: "abaixo" | "dentro" | "acima" da faixa
    veterinario: Optional[str] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class EventoSanitario(SQLModel, table=True):
    """
    Evento/protocolo sanitário (ex.: Vermífugo, Brucelose B19, Leptospirose).
    Além do nome, guarda o AGENDAMENTO — por época (recorrência fixa) ou por
    evento de vida (gatilho: nascimento, entrada em lote, aptidão de novilha…) —
    e o MEDICAMENTO PADRÃO, editável no momento do lançamento. Isso alimenta o
    calendário sanitário e a Agenda.
    """

    __tablename__ = "evento_sanitario"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True

    # Agendamento: "nenhum" (só o nome, retrocompatível) | "epoca" | "evento".
    tipo_agendamento: str = Field(default="nenhum")
    categoria_alvo: Optional[str] = None  # ex.: "Bezerras (3 a 8 meses)"
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")
    # Tipo do manejo preventivo: "vacina" | "exame" | "tratamento".
    categoria_preventiva: Optional[str] = None
    # Só para exame: qual ExameDefinicao (Configurações > Cadastro > Sanitário
    # > Exames) decide o tipo de resultado (diagnóstico/numérico) mostrado no
    # lançamento. Sem vínculo, o lançamento usa o modo diagnóstico padrão.
    exame_definicao_id: Optional[int] = Field(default=None, foreign_key="exame_definicao.id")

    # Por época — recorrência fixa a partir de uma data de referência.
    data_primeiro: Optional[date] = None
    frequencia_valor: Optional[int] = None
    frequencia_unidade: Optional[str] = None  # "dias" | "meses" | "anos"

    # Por evento de vida — gatilho + parâmetros do gatilho.
    gatilho: Optional[str] = None  # "nascimento" | "entrada_lote" | "novilha_apta" | "secagem" | "parto"
    gatilho_lote: Optional[str] = None       # código do lote (para entrada_lote)
    gatilho_idade_meses: Optional[int] = None  # idade-alvo (para novilha_apta)
    offset_dias: Optional[int] = None        # dias após o gatilho para agendar (default 0)

    # Medicamento padrão — sugerido no lançamento, editável na hora.
    produto_padrao: Optional[str] = None
    dose_padrao: Optional[float] = None
    unidade_padrao: Optional[str] = None
    via_padrao: Optional[str] = None

    # Só para exame: avisa na Agenda N dias antes da data prevista, para
    # confirmar o exame com o veterinário (pendência distinta da do próprio dia).
    agenda_dias_antes: Optional[int] = None

    # Condição de exclusão mútua — ex.: alternativas de vacina para a mesma
    # doença (Brucelose B19 × Brucelose RB51): só agenda ESTE evento se o
    # animal NUNCA tiver recebido o evento apontado aqui (ver
    # rules/eventos_sanitarios.eventos_agenda).
    condicao_evento_id: Optional[int] = Field(default=None, foreign_key="evento_sanitario.id")

    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MotivoBaixa(SQLModel, table=True):
    """Causa específica de uma baixa de animal (Rebanho > Baixar animal), cadastrável em Configurações."""

    __tablename__ = "motivo_baixa"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MotivoVenda(SQLModel, table=True):
    """Motivo da venda de um animal (Lançamentos > Compra/Venda > Vender animal), cadastrável em Configurações."""

    __tablename__ = "motivo_venda"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Raca(SQLModel, table=True):
    """Raça de animal (Girolando, Holandês, Gir...), cadastrável em Configurações — substitui o select fixo do cadastro de animal."""

    __tablename__ = "raca"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class GrauSangue(SQLModel, table=True):
    """
    Grau de sangue / composição racial cadastrável (ex.: "1/2 Holandês x Gir",
    "3/4 Holandês", "PO Holandês"). `fracao_holandes` (0 a 1) é a fração de
    sangue Holandês na escala de absorção Holandês x Gir usada na pecuária
    leiteira brasileira — permite calcular automaticamente o grau de sangue
    da cria no parto (média entre mãe e pai). Graus fora dessa escala (ex.:
    "PCOD Holandês") ficam com `fracao_holandes=None` — só rótulo, sem cálculo.
    """

    __tablename__ = "grau_sangue_cadastro"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    fracao_holandes: Optional[float] = None
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
    unidade: Optional[str] = None  # ml | L | unidade | dose | kg | saca 30kg | saca 60kg
    # Responsável pela regra (pessoa cadastrada) — vacina e exame.
    responsavel: Optional[str] = None
    # Veterinário (só exame) — pessoa cadastrada com tipo Veterinário/Zootecnista.
    veterinario: Optional[str] = None
    frequencia_valor: int
    frequencia_unidade: str  # "dias" | "meses" | "anos"
    data_evento: date  # data de referência do evento (base da recorrência)
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Protocolo sanitário — cadastro (Configurações > Cadastro > Sanitário) de um
# tratamento com múltiplas etapas (produto/dosagem/via por dia), a exemplo do
# tratamento de mastite. Dias podem começar em D0 ou D1 conforme o protocolo
# cadastrado (mesmo padrão de dia_inicial usado em ProtocoloInducaoLactacao).
# ---------------------------------------------------------------------------
class ProtocoloSanitario(SQLModel, table=True):
    """Um protocolo sanitário cadastrado (ex.: Mastite clínica, Vermifugação padrão)."""

    __tablename__ = "protocolo_sanitario"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")
    eh_mastite: bool = False  # liga o fluxo diferenciado: CMT, teto afetado, classificação
    dia_inicial: int = 0  # 0 (D0) ou 1 (D1) — primeiro dia do cronograma (etapas já existentes usam 1)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ProtocoloSanitarioEtapa(SQLModel, table=True):
    """Uma linha do protocolo — produto, dosagem, via e dia de aplicação (dia bruto; o
    rótulo exibido é dia - dia_inicial do protocolo)."""

    __tablename__ = "protocolo_sanitario_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_sanitario.id")
    dia: int  # 0, 1, 2... conforme dia_inicial do protocolo
    # Como o medicamento é definido: "medicamento" (produto = item de estoque,
    # aplicação já definida), "principio_ativo" ou "classificacao" (produto
    # guarda o critério; o medicamento real é escolhido no lançamento).
    criterio_tipo: str = Field(default="medicamento")
    produto: str  # nome do medicamento OU o valor do critério (princípio/classificação)
    dosagem: float
    unidade: str
    via: Optional[str] = None
    observacao: Optional[str] = None  # nota livre (ex.: "Se necessário", "10ml por orelha")


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
    grau_mastite: Optional[int] = None   # 1, 2 ou 3
    agente: Optional[str] = None         # patógeno identificado (ver AGENTES_MASTITE)
    resultado_cmt: Optional[str] = None  # "-", "+", "++" ou "+++"
    tetos_afetados: Optional[str] = None  # ex.: "AE,PD" — quadrantes: AE/AD/PD/PE
    # Snapshots do animal no momento do caso (preenchidos automaticamente).
    del_no_caso: Optional[int] = None
    ccs_ultima: Optional[float] = None
    # Recidiva: True quando há caso anterior no mesmo teto com intervalo < 20 dias.
    recidiva: Optional[bool] = None
    # Avaliação de cura no último dia do protocolo (marcada pela Agenda).
    curada: Optional[bool] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    # Medicamento escolhido no lançamento quando a etapa foi cadastrada por
    # princípio ativo/classificação (None = usa o produto da própria etapa).
    produto: Optional[str] = None
    realizada: bool = False
    data_realizacao: Optional[date] = None


# ---------------------------------------------------------------------------
# Protocolo de indução de lactação — cronograma multi-dia (hormônios +
# implante de progesterona + manejo de adaptação à ordenha) para induzir
# lactação em vacas que não vão parir (ex.: doadoras, vacas de descarte com
# valor de produção). Estrutura em 3 camadas, no mesmo espírito do protocolo
# IATF e do protocolo sanitário genérico:
#   catálogo (editável em Configurações > Cadastro) → lançamento (aplica o
#   catálogo a um grupo de animais numa data) → aplicação (uma linha por
#   animal/dia, confirmável na Agenda, com baixa de estoque automática).
# Dias podem começar em D0 ou D1 conforme o protocolo cadastrado.
# ---------------------------------------------------------------------------
class ProtocoloInducaoLactacao(SQLModel, table=True):
    """Um protocolo de indução de lactação cadastrado (o "molde" do cronograma)."""

    __tablename__ = "protocolo_inducao_lactacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    dia_inicial: int = 0  # 0 (D0) ou 1 (D1) — primeiro dia do cronograma
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ProtocoloInducaoLactacaoEtapa(SQLModel, table=True):
    """
    Uma linha do cronograma-molde: um medicamento, o implante de progesterona
    (colocar/retirar) ou uma ação de manejo (ex.: "Adaptação na ordenha") num
    dia do protocolo. Vários itens podem coexistir no mesmo dia.
    """

    __tablename__ = "protocolo_inducao_lactacao_etapa"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_inducao_lactacao.id", index=True)
    dia: int  # 0, 1, 2... conforme dia_inicial do protocolo
    tipo: str = Field(default="medicamento")  # "medicamento" | "dispositivo" | "manejo"
    principio_ativo_id: Optional[int] = Field(default=None, foreign_key="principio_ativo.id")
    produto: str  # nome do princípio (medicamento) OU "Implante de Progesterona" OU a ação de manejo
    acao_dispositivo: Optional[str] = None  # "colocar" | "retirar" — só para tipo="dispositivo"
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None


class ProtocoloInducaoLancamento(SQLModel, table=True):
    """Um lançamento do protocolo em lote — o "cabeçalho" (protocolo + data do 1º dia)."""

    __tablename__ = "protocolo_inducao_lancamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    protocolo_id: int = Field(foreign_key="protocolo_inducao_lactacao.id")
    nome_protocolo: str
    data_d0: date  # data do dia_inicial do protocolo (D0 ou D1)
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class ProtocoloInducaoMedicamento(SQLModel, table=True):
    """
    Medicamento(s) do dia, congelados no momento do lançamento (a partir da
    etapa-molde) — igual ao hormônio do protocolo IATF. Editar o catálogo
    depois não altera lançamentos já feitos.
    """

    __tablename__ = "protocolo_inducao_medicamento"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_inducao_lancamento.id", index=True)
    dia: int
    produto: str
    dose: Optional[float] = None
    unidade: Optional[str] = None
    via: Optional[str] = None


class ProtocoloInducaoAplicacao(SQLModel, table=True):
    """
    Uma etapa (dia) de um animal dentro de um lançamento — vira evento na
    Agenda; ao marcar "realizado", dá baixa automática do(s) produto(s) do
    dia. `observacao_manejo` é o texto que o funcionário vê na Agenda para as
    ações sem medicamento (colocar/retirar implante, adaptação na ordenha,
    iniciar a ordenha).
    """

    __tablename__ = "protocolo_inducao_aplicacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    lancamento_id: int = Field(foreign_key="protocolo_inducao_lancamento.id")
    numero_matriz: str = Field(index=True)
    dia: int
    descricao: str  # medicamentos do dia (auto), ex.: "20 ml Benzoato de Estradiol"
    observacao_manejo: Optional[str] = None
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


class Touro(SQLModel, table=True):
    """Catálogo genético de touros (provas do fornecedor / NAAB-CDCB). Guarda o
    código NAAB, nome e as provas (produção, índices econômicos, tipo/saúde) —
    importado do catálogo Excel/CSV do fornecedor a cada rodada de prova. Usado
    para mostrar o pai com nome + provas na ficha do animal."""

    __tablename__ = "touro"

    id: Optional[int] = Field(default=None, primary_key=True)
    naab: str = Field(index=True, unique=True)  # código NAAB (ex.: 7HO12345)
    nome: Optional[str] = None
    nome_completo: Optional[str] = None
    raca: Optional[str] = None
    central: Optional[str] = None
    # Produção (PTAs)
    leite_kg: Optional[float] = None
    gordura_kg: Optional[float] = None
    gordura_pct: Optional[float] = None
    proteina_kg: Optional[float] = None
    proteina_pct: Optional[float] = None
    # Índices econômicos
    tpi: Optional[float] = None
    nm_dolar: Optional[float] = None  # Net Merit $ (ou índice econômico equivalente)
    # Tipo e saúde
    tipo_composto: Optional[float] = None      # PTAT / composto de conformação
    ubere_composto: Optional[float] = None     # UDC — composto de úbere
    pernas_composto: Optional[float] = None    # FLC — pernas e pés
    ccs_score: Optional[float] = None          # SCS — células somáticas
    fertilidade_filhas: Optional[float] = None # DPR / fertilidade
    facilidade_parto: Optional[float] = None   # SCE/DCE — facilidade de parto
    # Metadados
    fonte: Optional[str] = None       # ABS, Alta, Select Sires, CRV, manual...
    rodada_prova: Optional[str] = None  # ex.: "Abr/2026"
    observacao: Optional[str] = None
    # Dados brutos da planilha do fornecedor além dos campos curados acima —
    # JSON com lista [[rótulo original, valor], ...], na ordem da planilha.
    # Garante que nenhuma coluna do catálogo se perca mesmo quando o fornecedor
    # usa nomes de campo que não têm um equivalente curado no modelo.
    dados_extra: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class EstoqueSemen(SQLModel, table=True):
    """Estoque de doses de sêmen por touro — usado no relatório de manejo
    'Estoque de sêmen'. Distinto de Estoque (insumos) e de Animal(eh_semen),
    que é só o catálogo do touro sem contagem de doses."""

    __tablename__ = "estoque_semen"

    id: Optional[int] = Field(default=None, primary_key=True)
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


# ---------------------------------------------------------------------------
# Dieta (plano alimentar por lote)
# ---------------------------------------------------------------------------
class CategoriaAlimento(SQLModel, table=True):
    """Categoria de alimento (Volumoso, Concentrado, Mineral...), editável em
    Configurações > Cadastro > Alimentação > Categorias. Agrupa os Alimentos
    cadastrados — puramente organizacional, sem regra de cálculo própria."""

    __tablename__ = "categoria_alimento"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Alimento(SQLModel, table=True):
    """Cadastro de alimento (Configurações > Cadastro > Alimentação >
    Alimentos) — distinto do item de Estoque: um Alimento é o conceito
    nutricional (ex.: "Silagem de milho"), que pode estar vinculado a um ou
    mais itens de Estoque (ver `Estoque.alimento_id`) de onde vem a baixa
    física quando a dieta é lançada. Um Alimento sem nenhum Estoque vinculado
    ainda é válido (ex.: acabou de ser cadastrado), mas fica marcado como
    pendente de vínculo nas telas onde aparece."""

    __tablename__ = "alimento"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    categoria_alimento_id: Optional[int] = Field(default=None, foreign_key="categoria_alimento.id")
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


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
    # Como as quantidades dos itens foram informadas: "total" do lote/dia (padrão)
    # ou "animal" (por cabeça/dia — o total é multiplicado pelo nº de animais).
    base_quantidade: Optional[str] = None
    # Leite destinado aos bezerros nesta dieta (kg/dia do lote) — alimenta o
    # relatório Controle × Entregue (consumo de bezerros). Preenchido pelo
    # veterinário/nutricionista ao lançar a dieta de um lote de bezerras.
    leite_bezerros_kg_dia: Optional[float] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class DietaItemProgramado(SQLModel, table=True):
    """Um alimento do plano formulado (programado) de uma DietaLancamento — quantidade TOTAL do lote/dia."""

    __tablename__ = "dieta_item_programado"

    id: Optional[int] = Field(default=None, primary_key=True)
    dieta_lancamento_id: int = Field(foreign_key="dieta_lancamento.id", index=True)
    alimento: str
    # Vínculo com o cadastro de Alimento, quando escolhido via o seletor (em
    # vez de texto livre) — permite resolver o(s) item(ns) de Estoque vinculados
    # sem depender de casar `alimento` (nome) com `Estoque.nome`. Fica None para
    # lançamentos antigos ou alimentos ainda sem cadastro correspondente.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")
    quantidade: float
    unidade: str
    # Base da quantidade do ingrediente: "MN" (matéria natural, padrão) ou "MS"
    # (matéria seca). ms_pct = % de matéria seca do alimento, para converter
    # entre as duas bases quando informado.
    base: Optional[str] = None
    ms_pct: Optional[float] = None


class IngredienteMS(SQLModel, table=True):
    """% de matéria seca (MS) de cada ingrediente padrão — editável na aba
    Matéria seca da Alimentação. Alimenta a conversão MN↔MS das dietas."""

    __tablename__ = "ingrediente_ms"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ms_pct: Optional[float] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class TabelaNutricionalProduto(SQLModel, table=True):
    """Um produto/alimento cadastrado na tabela nutricional (uma coluna da
    matriz nutriente × produto) — editável em Alimentação > Tabela nutricional."""

    __tablename__ = "tabela_nutricional_produto"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ordem: int = 0
    # Vínculo opcional com o cadastro de Alimento — quando presente, a tela de
    # cadastro do Alimento pode oferecer "cadastrar tabela nutricional" direto.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")


class TabelaNutricionalValor(SQLModel, table=True):
    """Um valor (nutriente × produto) da tabela nutricional. Texto livre —
    a planilha de referência mistura unidades diferentes na mesma célula
    (ex.: "5.500,00 mg", "740,00 g (Mín)")."""

    __tablename__ = "tabela_nutricional_valor"

    id: Optional[int] = Field(default=None, primary_key=True)
    produto_id: int = Field(foreign_key="tabela_nutricional_produto.id", index=True)
    nutriente: str = Field(index=True)
    valor: str = ""


class AnaliseBromatologica(SQLModel, table=True):
    """Laudo de análise bromatológica de um lote/silo de alimento — resultado
    de laboratório (não confundir com a Tabela Nutricional, que é referência
    padrão, ou Matéria seca, que é só o %MS por ingrediente genérico). Cada
    registro é um laudo pontual de um alimento específico da fazenda."""

    __tablename__ = "analise_bromatologica"

    id: Optional[int] = Field(default=None, primary_key=True)
    data: date
    alimento: str = Field(index=True)
    # Vínculo opcional com o cadastro de Alimento (ver `Alimento`) — permite
    # oferecer "fazer análise bromatológica" direto do cadastro do alimento.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")
    ms_pct: Optional[float] = None  # matéria seca (%)
    pb_pct: Optional[float] = None  # proteína bruta (%)
    fdn_pct: Optional[float] = None  # fibra em detergente neutro (%)
    fda_pct: Optional[float] = None  # fibra em detergente ácido (%)
    ndt_pct: Optional[float] = None  # nutrientes digestíveis totais (%)
    ee_pct: Optional[float] = None  # extrato etéreo / gordura (%)
    cinzas_pct: Optional[float] = None
    ca_pct: Optional[float] = None  # cálcio (%)
    p_pct: Optional[float] = None  # fósforo (%)
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class ParametroFazenda(SQLModel, table=True):
    """Parâmetro editável de manejo/metas/financeiro — substitui o antigo dict
    fixo em `rules/parametros.py` por um valor persistido e de fato editável
    pela UI de Configurações > Parâmetros. `valor` fica como texto para caber
    qualquer `tipo` (int/float/bool/date) num único campo; `get_param()` (ver
    `rules/parametros.py`) faz a conversão na leitura."""

    __tablename__ = "parametro_fazenda"

    id: Optional[int] = Field(default=None, primary_key=True)
    chave: str = Field(index=True, unique=True)
    grupo: str
    label: str
    valor: str
    tipo: str = "int"  # "int" | "float" | "bool" | "date"
    unidade: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


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
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    numero_animal: Optional[str] = None  # CSV de números, quando vinculado a um ou mais animais
    lotes: Optional[str] = None  # CSV de códigos de lote, quando vinculado a um ou mais lotes
    tipo_evento: Optional[str] = None  # Compra, Venda, Serviço, Outro
    observacao: Optional[str] = None
    recorrente: bool = False  # linha-modelo que gera as próximas ocorrências automaticamente
    intervalo_dias: Optional[int] = None
    intervalo_meses: Optional[int] = None
    origem_recorrencia_id: Optional[int] = None  # id da linha-modelo que gerou esta ocorrência
    apenas_admin: bool = False  # evento visível somente para o administrador
    link: Optional[str] = None  # rota interna de instruções/ação (ex.: "/configuracoes?aba=importar")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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
    # Preferência pessoal de paleta de cores — "vinho" (padrão) ou "verde".
    paleta: Optional[str] = None
    # E-mail pessoal (opcional) — usado hoje só para identificar o dono da
    # fazenda e liberar o relatório de acessos (ver fazenda.auth.exigir_dono).
    email: Optional[str] = None
    ultimo_login: Optional[datetime] = None
    # Permissão específica para publicar matérias no blog (News) — independente
    # de papel/admin (ver fazenda.auth.exigir_pode_publicar). Todo usuário
    # nasce sem essa permissão; o proprietário recebe uma única vez via seed
    # (ver fazenda.auth.seed_permissao_publicar_dono).
    pode_publicar_materias_blog: bool = False
    # Vínculo com o cadastro de Pessoas — todo usuário novo exige uma pessoa já
    # cadastrada (ver criar_usuario em fazenda.api.routers.auth); contas
    # antigas podem não ter esse vínculo até serem editadas retroativamente.
    pessoa_id: Optional[int] = Field(default=None, foreign_key="pessoa.id")


class LoginAcesso(SQLModel, table=True):
    """Um login bem-sucedido — histórico completo (Usuario.ultimo_login guarda
    só o mais recente). Alimenta o relatório de últimos acessos, restrito ao
    proprietário (ver fazenda.auth.exigir_dono)."""

    __tablename__ = "login_acesso"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class BackupAutomatico(SQLModel, table=True):
    """Registro de cada rodada do backup automático semanal (ver
    fazenda.rules.backup) — guarda quando rodou e se deu certo, para decidir
    se já é hora da próxima rodada e para o erro não se perder caso o envio
    do e-mail falhe (ex.: RESEND_API_KEY não configurada)."""

    __tablename__ = "backup_automatico"

    id: Optional[int] = Field(default=None, primary_key=True)
    executado_em: datetime = Field(default_factory=datetime.utcnow)
    sucesso: bool = True
    erro: Optional[str] = None


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
    motivo: str      # venda | abate | acidente | doenca | macho | outros
    motivo_doenca: Optional[str] = None  # preenchido só quando motivo == "doenca"
    motivo_outro: Optional[str] = None   # texto livre opcional quando motivo == "outros"
    valor: Optional[float] = None        # preenchido só quando motivo == "venda" — sempre o valor POR ANIMAL já resolvido
    cliente: Optional[str] = None        # preenchido só quando motivo == "venda"
    tipo_valor: Optional[str] = None     # "por_animal" | "total" — como o valor foi originalmente digitado (metadado)
    venda_recria: Optional[bool] = None  # True quando é venda de animal de recria (para simular receita vs custo de recria)
    numero_lancamento_gerado: Optional[str] = None  # LC-... do lançamento financeiro (ContaGerencial) gerado na venda
    data_baixa: date
    observacao: Optional[str] = None
    responsavel: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Compra de animal — entrada de animal no rebanho por aquisição (distinta do
# cadastro/ficha do Animal, que segue seu próprio fluxo de CSV/ficha). Gera
# lançamento financeiro (despesa) e, opcionalmente, comissão de corretagem.
# ---------------------------------------------------------------------------
class CompraAnimal(SQLModel, table=True):
    """Registro de compra de animal — apenas o efeito financeiro/histórico da aquisição.
    Os campos financeiros "ricos" (centro de custo, tipo/nº de documento, datas,
    parcelamento, pagamento etc.) vivem na(s) ContaGerencial geradas — aqui só
    o que é específico da transação de compra do animal em si."""

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
    # Guia de Trânsito Animal — vincula a compra ao documento sanitário de
    # transporte (consultável no relatório de compra/venda de animais).
    gta: Optional[str] = None
    icms_incide: bool = False
    icms_tipo: Optional[str] = None  # "intermunicipal" | "interestadual"
    icms_valor: Optional[float] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class VendaAnimal(SQLModel, table=True):
    """Registro de venda de animal — espelha CompraAnimal, com comprador no
    lugar de vendedor e categoria(s)/motivo da venda, específicos de venda."""

    __tablename__ = "venda_animal"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_animal: str = Field(index=True)
    comprador: str
    valor: float
    tipo_valor: str  # "por_animal" | "total"
    data_venda: date
    responsavel: Optional[str] = None
    observacao: Optional[str] = None
    # Categoria(s) do(s) animal(is) vendido(s) nesta nota — lista separada por
    # vírgula (ex.: "Vaca,Novilha") já que uma mesma nota pode misturar categorias.
    categorias: Optional[str] = None
    motivo_venda: Optional[str] = None
    numero_lancamento_gerado: Optional[str] = None
    gta: Optional[str] = None
    icms_incide: bool = False
    icms_tipo: Optional[str] = None  # "intermunicipal" | "interestadual"
    icms_valor: Optional[float] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


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


# ---------------------------------------------------------------------------
# Comissão de corretagem — gerada a partir de uma venda ou compra de animal,
# quando há corretor envolvido. Sempre resulta em uma despesa (ContaGerencial)
# separada e visível, seja "redirecionada" (liquidada junto com a transação,
# copiando o estado de pagamento dela) ou "separada" (conta a pagar/vencimento
# própria, independente da transação de origem).
# ---------------------------------------------------------------------------
class ComissaoCorretagem(SQLModel, table=True):
    """Registro de comissão paga a corretor por uma venda/compra de animal."""

    __tablename__ = "comissao_corretagem"

    id: Optional[int] = Field(default=None, primary_key=True)
    origem_tipo: str  # "venda_animal" | "compra_animal"
    numero_lancamento: str  # LC-... do lançamento de venda/compra ao qual esta comissão se refere
    corretor_nome: str
    valor_comissao: float
    forma: str  # "redirecionado" (segue o pagamento da transação) | "separado" (conta a pagar própria)
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


# ===========================================================================
# MÓDULO RECRIA — Dossiê de Desempenho Zootécnico
# Novas tabelas que sustentam o acompanhamento de bezerras/novilhas:
# ocorrências clínicas (fonte das curvas doença×idade), metas, curva de
# peso-alvo por idade, fases de idade (coorte) e janelas de ponto crítico.
# ===========================================================================
class OcorrenciaClinica(SQLModel, table=True):
    """Caso clínico de doença num animal, numa data. É a matéria-prima das
    curvas 'casos por idade' e da incidência por fase do Dossiê de Recria."""

    __tablename__ = "ocorrencia_clinica"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_matriz: str = Field(index=True)
    doenca: str = Field(index=True)          # nome da doença (ex.: Diarreia, Pneumonia, TPB)
    data_ocorrencia: date = Field(index=True)
    observacao: Optional[str] = None
    origem: str = "manual"                    # "manual" | "importacao" | "sanidade"
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class MetaRecria(SQLModel, table=True):
    """Metas gerenciais da recria (linha única, id=1). Espelha a aba
    PARÂMETROS da planilha do consultor."""

    __tablename__ = "meta_recria"

    id: Optional[int] = Field(default=None, primary_key=True)
    idade_parto_meses: float = 24.0
    idade_prenhez_meses: float = 14.5
    idade_1a_cobertura_meses: float = 13.5
    taxa_prenhez_meta: float = 42.5
    desvio_padrao_meta: float = 1.7
    custo_diario_recria: float = 12.0
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class PesoAlvoIdade(SQLModel, table=True):
    """Curva de peso-alvo: faixa mín/máx de peso (kg) esperada por mês de vida."""

    __tablename__ = "peso_alvo_idade"

    id: Optional[int] = Field(default=None, primary_key=True)
    mes: int = Field(index=True, unique=True)   # idade em meses (1..24)
    peso_min_kg: float
    peso_max_kg: float
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FaseRecria(SQLModel, table=True):
    """Faixa de idade (em dias) usada para agrupar casos/incidência. Editável
    pelo consultor. Ex.: '30–60 dias'."""

    __tablename__ = "fase_recria"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    dia_min: int = Field(index=True)
    dia_max: int
    ordem: int = 0
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class JanelaPontoCritico(SQLModel, table=True):
    """Janela crítica de uma doença: faixa de idade (dias) de maior incidência
    e a antecedência (dias) com que o alerta preventivo entra na Agenda."""

    __tablename__ = "janela_ponto_critico"

    id: Optional[int] = Field(default=None, primary_key=True)
    doenca: str = Field(index=True)
    dia_min: int
    dia_max: int
    dias_antecedencia: int = 3
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class BenchmarkRecria(SQLModel, table=True):
    """Referência externa de benchmarking (ex.: Alta CRIA): percentis do setor
    (TOP 5/10/25/50/75%) por indicador, e o valor atual da fazenda."""

    __tablename__ = "benchmark_recria"

    id: Optional[int] = Field(default=None, primary_key=True)
    indicador: str = Field(index=True)
    unidade: Optional[str] = None            # "%", "g/dia", etc.
    melhor_e_maior: bool = True              # True: quanto MAIOR melhor (GMD); False: quanto menor (mortalidade)
    top5: Optional[float] = None
    top10: Optional[float] = None
    top25: Optional[float] = None
    top50: Optional[float] = None
    top75: Optional[float] = None
    valor_fazenda: Optional[float] = None
    ordem: int = 0
    fonte: str = "Alta CRIA 2026"
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class RegistroCocho(SQLModel, table=True):
    """Gestão de cocho: leitura diária por lote — quanto foi ofertado, quanto
    sobrou e quantos animais comeram. Fecha o consumo e a IMS (ingestão de
    matéria seca) para o Dossiê de Recria."""

    __tablename__ = "registro_cocho"

    id: Optional[int] = Field(default=None, primary_key=True)
    data: date = Field(index=True)
    lote: str = Field(index=True)
    num_animais: int = 1
    kg_ofertado: float = 0.0
    kg_sobra: float = 0.0
    kg_formulado: Optional[float] = None   # meta formulada (kg total do lote), opcional
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class CategoriaManejo(SQLModel, table=True):
    """Parâmetro de categoria de manejo por idade/peso (aleitamento, recria 1,
    recria 2, apta). Cadastrável; classifica cada animal automaticamente. Na
    categoria de aptidão, o status reprodutivo (apta/inseminada/gestante) assume."""

    __tablename__ = "categoria_manejo"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    dia_min: int = 0
    dia_max: Optional[int] = None          # None = sem limite superior
    peso_min_kg: Optional[float] = None
    peso_max_kg: Optional[float] = None
    usa_status_reprodutivo: bool = False   # True: a partir daqui, o status reprodutivo assume
    # Critérios adicionais — todos opcionais; None = não filtra por aquele
    # critério. Permitem compor categorias como "Prenha", "Em lactação",
    # "Seca", "Vazia atrasada" etc. além de idade/peso.
    situacao_reprodutiva: Optional[str] = None   # "vazia" | "inseminada" | "prenha"
    situacao_produtiva: Optional[str] = None     # "lactacao" | "seca"
    dias_gestacao_min: Optional[int] = None
    dias_gestacao_max: Optional[int] = None
    dias_desde_servico_min: Optional[int] = None
    dias_desde_servico_max: Optional[int] = None
    dias_para_parto_min: Optional[int] = None
    dias_para_parto_max: Optional[int] = None
    dias_pos_parto_min: Optional[int] = None
    dias_pos_parto_max: Optional[int] = None
    ordem: int = 0
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# News — blog de importação de notícias de pecuária leiteira (botão "News").
# ---------------------------------------------------------------------------
class FonteNews(SQLModel, table=True):
    """Um site cadastrado para o agregador de notícias (Configurações > News,
    só administrador). Guarda o último erro de busca — quando um site muda de
    layout ou sai do ar, aparece aqui para o admin substituir/corrigir a URL,
    em vez de quebrar a página de notícias para todo mundo."""

    __tablename__ = "fonte_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    url: str  # home do site ou feed RSS/Atom direto
    ativo: bool = True
    ultimo_erro: Optional[str] = None
    ultima_busca_em: Optional[datetime] = None
    ultima_busca_ok_em: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    # Fonte alimentada via POST /news/manual (ex.: robô agendado) em vez de
    # RSS — nunca busca sozinha, então nunca aparece com erro de fetch.
    manual: bool = False


class NoticiaNews(SQLModel, table=True):
    """Uma matéria já importada de uma fonte (manchete + resumo + link) — cache
    local para não depender de buscar no site a cada carregamento da página."""

    __tablename__ = "noticia_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    fonte_id: int = Field(foreign_key="fonte_news.id", index=True)
    manchete: str
    resumo: Optional[str] = None
    link: str = Field(unique=True)
    data_publicacao: Optional[datetime] = None  # data/hora informada pelo site (quando disponível)
    capturado_em: datetime = Field(default_factory=datetime.utcnow, index=True)
    # Matéria escrita por nós (admin ou robô) via Configurações > News > Adicionar
    # matéria ao blog — corpo completo do texto, distinto do `resumo` (que é o
    # recorte curto vindo de fontes RSS externas). Nula para matérias antigas
    # importadas de RSS.
    materia: Optional[str] = None
    # Fontes/URLs de referência informadas ao publicar a matéria (JSON: lista de
    # strings) — 0 a N links, diferente do `link` único usado no fluxo antigo de
    # importação RSS.
    fontes: Optional[str] = None
    # Revisão de publicação definitiva (aba própria em Configurações > News) —
    # etapa humana que o robô nunca faz, independente de quem/o que publicou a
    # matéria (robô /milknews, "Adicionar matéria ao blog" ou aprovação de
    # pendente). Toda matéria nasce não revisada.
    revisado_final: bool = False
    revisado_final_em: Optional[datetime] = None
    revisado_final_por: Optional[str] = None
    # Ilustração da matéria (#news-redesign) — caminho público dentro de
    # frontend/public/news-images/ (ex.: "/news-images/compost-barn-01.jpg"),
    # escolhido a partir do banco de fotos + manifesto de tags (ver
    # frontend/public/news-images/manifest.json). Nula para matérias antigas
    # ou sem foto correspondente no banco — a tela cai no fundo temático
    # rotativo já existente (newsVisual.ts) nesse caso.
    imagem: Optional[str] = None
    # Rótulo curto (pílula na tela, ex.: "Instalações", "Genética", "Qualidade
    # do Leite") — livre, sem lista fixa; nulo não mostra pílula.
    categoria: Optional[str] = None


# ---------------------------------------------------------------------------
# Notificações push (Web Push API) — canal adicional de entrega para os
# MESMOS alertas do sininho (/notificacoes), funcionando com o app fechado.
# Ver fazenda/api/routers/push.py.
# ---------------------------------------------------------------------------
class PushSubscription(SQLModel, table=True):
    """Uma inscrição de push do navegador (PushSubscription da Web Push API)
    vinculada ao usuário logado que a criou. Um usuário pode ter mais de uma
    (um por navegador/dispositivo em que clicou "Ativar notificações")."""

    __tablename__ = "push_subscription"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    endpoint: str = Field(index=True)  # URL única do serviço de push do navegador
    p256dh: str
    auth: str
    user_agent: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class PushNotificacaoEnviada(SQLModel, table=True):
    """Registro de deduplicação: evita reenviar o mesmo alerta (mesma
    `chave`) via push para o mesmo usuário mais de uma vez por dia — a
    lógica de "quando gerar o alerta" continua 100% em calcular_agenda()/
    notificacoes.py; isto só impede reenvio no canal de entrega novo, já
    que o sininho é reconsultado a cada poll do app aberto."""

    __tablename__ = "push_notificacao_enviada"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    chave: str = Field(index=True)
    data_referencia: date = Field(index=True)
    enviado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Administração > Portal > Comunicação — mensagens internas e tarefas
# delegadas entre usuários, com sinalização na central de alertas (#513-515).
# ---------------------------------------------------------------------------
class PortalMensagem(SQLModel, table=True):
    """Uma mensagem, e-mail-log ou tarefa delegada do Portal de comunicação.

    Regras de permanência na central de alertas (ver /notificacoes):
      - tipo "tarefa": some ao ser lida (não tem fluxo de resposta).
      - tipo "mensagem" sem pede_retorno: some ao ser lida.
      - tipo "mensagem" com pede_retorno: só some quando resolvida (marcada
        "resolvido" OU respondida — responder já marca resolvida=True)."""

    __tablename__ = "portal_mensagem"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str = "mensagem"  # "mensagem" | "tarefa"
    remetente_usuario_id: int = Field(foreign_key="usuario.id")
    destinatario_usuario_id: int = Field(foreign_key="usuario.id", index=True)
    aba: Optional[str] = None  # sanidade|alimentacao|estoque|indicadores|financeiro|pedidos|listas|lancamentos|agenda
    corpo: str
    pede_retorno: bool = False
    lida: bool = False
    resolvida: bool = False
    # Quando esta linha é a resposta a outra, aponta para a mensagem original.
    resposta_de_id: Optional[int] = Field(default=None, foreign_key="portal_mensagem.id")
    # Quando tipo="tarefa", aponta para o evento correspondente na Agenda.
    agenda_manual_id: Optional[int] = Field(default=None, foreign_key="agenda_manual.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class FaixaBonificacaoQualidade(SQLModel, table=True):
    """Faixa de bonificação/penalização por qualidade do leite, cadastrável em
    Configurações > Parâmetros (#548). Cada laticínio tem sua própria tabela de
    faixas para CCS/CBT/gordura/proteína — não existe padrão nacional único —
    por isso aqui fica só a estrutura configurável (sem valores fixos no
    código): um ajuste em R$/litro por faixa de um indicador, comparado contra
    os lançamentos de Qualidade do leite (ver fazenda/rules/bonificacao_qualidade.py)."""

    __tablename__ = "faixa_bonificacao_qualidade"

    id: Optional[int] = Field(default=None, primary_key=True)
    indicador: str = Field(index=True)  # "ccs" | "cbt" | "gordura_pct" | "proteina_pct"
    valor_min: Optional[float] = None  # None = sem limite inferior
    valor_max: Optional[float] = None  # None = sem limite superior
    ajuste_por_litro: float  # R$/litro — positivo = bônus, negativo = desconto/penalização
    ativo: bool = True
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
