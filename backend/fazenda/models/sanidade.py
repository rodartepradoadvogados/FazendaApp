"""
Sanidade — aplicações, farmácia (princípio ativo/medicamento), calendário e protocolos sanitários, catálogo de touros.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

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
    # Vínculo (soft-join pelo número, igual a *.numero_lancamento_gerado em
    # ManutencaoPatrimonio/FolhaPagamento) com o lançamento financeiro em
    # ContaGerencial que paga esta aplicação — ver popup de vínculo
    # sanitário/reprodutivo, disparado ao salvar uma vacina/exame preventivo.
    numero_lancamento_vinculado: Optional[str] = Field(default=None, index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Cadastros de apoio ao Calendário sanitário (Configurações > Cadastro).
# ---------------------------------------------------------------------------
class PrincipioAtivo(SQLModel, table=True):
    """Espinha dorsal da farmácia: o princípio ativo (ou, para biológicos, o
    antígeno/doença combatida). Marcas comerciais e itens de estoque penduram
    aqui. O somatório de estoque e o alerta de mínimo são calculados no nível do
    princípio (ver rules/farmacia)."""

    __tablename__ = "principio_ativo"
    # nome era único globalmente — passa a ser único por fazenda (mesmo padrão
    # de CentroCusto/ColostragemBezerra), senão a 2ª fazenda nunca conseguiria
    # cadastrar um princípio ativo com o mesmo nome já usado pela 1ª.
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_principio_ativo_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class Doenca(SQLModel, table=True):
    __tablename__ = "doenca"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_doenca_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class IndicacaoTerapeutica(SQLModel, table=True):
    """Vínculo N-para-N entre princípio ativo e doença, com prioridade clínica
    (1 = 1ª escolha, 2 = 2ª opção, ...). Generaliza `PrincipioAtivo.doenca_id`
    (1-para-1, usado só por biológicos) para o caso geral — mesmo antibiótico
    tratando mais de uma doença, mesma doença com várias opções ranqueadas.
    Base do "substituto inteligente": ao faltar o 1º colocado, a 2ª/3ª opção
    aparecem automaticamente no lançamento."""

    __tablename__ = "indicacao_terapeutica"
    __table_args__ = (UniqueConstraint("principio_ativo_id", "doenca_id", name="uq_indicacao_principio_doenca"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    principio_ativo_id: int = Field(foreign_key="principio_ativo.id", index=True)
    doenca_id: int = Field(foreign_key="doenca.id", index=True)
    prioridade: int = 2  # 1 = 1ª escolha, 2 = 2ª opção, 3 = 3ª opção...
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_exame_definicao_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    # Vínculo (soft-join pelo número) com o lançamento financeiro em
    # ContaGerencial que paga este exame — ver popup de vínculo
    # sanitário/reprodutivo, disparado ao salvar um exame preventivo.
    numero_lancamento_vinculado: Optional[str] = Field(default=None, index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class EventoSanitario(SQLModel, table=True):
    """
    Evento/protocolo sanitário (ex.: Vermífugo, Brucelose B19, Leptospirose).
    Além do nome, guarda o AGENDAMENTO — por época (recorrência fixa) ou por
    evento de vida (gatilho: nascimento, entrada em lote, aptidão de novilha…) —
    e o MEDICAMENTO PADRÃO, editável no momento do lançamento. Isso alimenta o
    calendário sanitário e a Agenda.
    """

    __tablename__ = "evento_sanitario"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_evento_sanitario_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class CalendarioSanitario(SQLModel, table=True):
    """
    Uma regra do calendário sanitário da fazenda — sazonal/de rebanho (ex.:
    vermífugo a cada 4 meses para bezerras) ou por fase fisiológica (ex.:
    Brucelose B19 no nascimento). `data_evento` é a data de referência; a
    recorrência (frequencia_valor/unidade) projeta a próxima ocorrência.
    """

    __tablename__ = "calendario_sanitario"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda: nulo para toda regra já cadastrada
    # antes da migração de backfill (ver fazenda/models/multitenant.py) — a
    # regra já É o "lançamento" real e editável (não um valor fixo em
    # Python); fazenda nova nasce sem nenhuma, fazenda #1 mantém as suas.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    # Liga esta regra ao workflow de Cronograma (ver CronogramaSanitario
    # abaixo): em vez de virar pendência de "aplicar agora" direto, o animal
    # que bate o critério entra numa lista de espera, e a aplicação em si só
    # acontece quando um veterinário for agendado (ou a equipe própria
    # confirmar que vai aplicar) — decisão pedida na Agenda a cada ocorrência.
    # False (padrão) preserva 100% o comportamento antigo — nenhuma regra já
    # cadastrada muda de comportamento sozinha.
    usa_cronograma: bool = False
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Cronograma sanitário — workflow dinâmico de acompanhamento de UMA ocorrência
# de uma regra do calendário sanitário marcada `usa_cronograma=True` (ver
# CalendarioSanitario acima). Existe no máximo 1 cronograma "em aberto" (não
# concluído/cancelado) por regra a qualquer momento — cada evento sanitário
# "toca" nesse cronograma aberto por duas trilhas independentes:
#   (1) trilha do animal — CronogramaSanitarioAnimal, alimentada todo dia
#       conforme animais batem o critério do EventoSanitario (idade/gatilho);
#   (2) trilha do agendamento — os campos abaixo, decidindo COM QUEM e
#       QUANDO a aplicação de fato acontece (veterinário/própria/em branco,
#       com lembrete obrigatório N dias antes se ninguém decidiu nada).
# Ver fazenda.rules.cronograma_sanitario para o motor de estado completo.
# ---------------------------------------------------------------------------
class CronogramaSanitario(SQLModel, table=True):
    __tablename__ = "cronograma_sanitario"

    id: Optional[int] = Field(default=None, primary_key=True)
    calendario_sanitario_id: int = Field(foreign_key="calendario_sanitario.id", index=True)
    # Data prevista desta ocorrência — nasce igual à próxima ocorrência
    # projetada da regra (ver rules.calendario_sanitario.proxima_ocorrencia),
    # mas pode ser adiada (ver "adiar" abaixo) sem alterar a regra em si.
    data_evento: date
    data_original: Optional[date] = None  # 1ª data prevista, preenchida só se já foi adiado 1x
    # None = "em branco" (ainda não decidido) | "veterinario" | "propria".
    modo_execucao: Optional[str] = None
    veterinario_pessoa_id: Optional[int] = Field(default=None, foreign_key="pessoa.id")
    # "aberto" (recém-criado, aceitando inclusão de animais e aguardando
    #   decisão de modo) | "agendado" (modo definido, aguardando a data) |
    #   "aguardando_confirmacao" (passou o aviso de N dias antes sem decisão,
    #   Agenda cobrando confirmar/adiar) | "concluido" (aplicado) |
    #   "cancelado".
    status: str = Field(default="aberto", index=True)
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    concluido_em: Optional[datetime] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class CronogramaSanitarioAnimal(SQLModel, table=True):
    """Um animal dentro de um CronogramaSanitario — trilha (1) acima. Nasce
    "sugerido" assim que o animal bate o critério do evento sanitário
    (idade/gatilho); o funcionário aprova ("incluido") ou recusa ("excluido")
    pela Agenda. "aplicado" é marcado quando o cronograma é executado."""

    __tablename__ = "cronograma_sanitario_animal"
    __table_args__ = (UniqueConstraint("cronograma_id", "numero_matriz", name="uq_cronograma_animal"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    cronograma_id: int = Field(foreign_key="cronograma_sanitario.id", index=True)
    numero_matriz: str = Field(index=True)
    status: str = Field(default="sugerido", index=True)  # sugerido | incluido | excluido | aplicado
    data_sugestao: date
    data_decisao: Optional[date] = None
    data_aplicacao: Optional[date] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class ServicoCadastro(SQLModel, table=True):
    """
    Serviço cadastrável para lançamento financeiro (ex.: manutenção de trator,
    frete, quilometragem) — distinto do modelo `Servico` (serviço/IA reprodutivo).
    """

    __tablename__ = "servico_cadastro"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_servico_cadastro_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


# ---------------------------------------------------------------------------
# Protocolo sanitário — cadastro (Configurações > Cadastro > Sanitário) de um
# tratamento com múltiplas etapas (produto/dosagem/via por dia), a exemplo do
# tratamento de mastite. Dias podem começar em D0 ou D1 conforme o protocolo
# cadastrado (mesmo padrão de dia_inicial usado em ProtocoloInducaoLactacao).
# ---------------------------------------------------------------------------
class ProtocoloSanitario(SQLModel, table=True):
    """Um protocolo sanitário cadastrado (ex.: Mastite clínica, Vermifugação padrão)."""

    __tablename__ = "protocolo_sanitario"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_protocolo_sanitario_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    doenca_id: Optional[int] = Field(default=None, foreign_key="doenca.id")
    eh_mastite: bool = False  # liga o fluxo diferenciado: CMT, teto afetado, classificação
    dia_inicial: int = 0  # 0 (D0) ou 1 (D1) — primeiro dia do cronograma (etapas já existentes usam 1)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_protocolo_inducao_lactacao_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    dia_inicial: int = 0  # 0 (D0) ou 1 (D1) — primeiro dia do cronograma
    observacao: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


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
