"""
Produção leiteira — controle leiteiro, pesagens, qualidade do leite e secagem.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Controle Leiteiro
# ---------------------------------------------------------------------------
class ControleLeiteiro(SQLModel, table=True):
    """Uma linha da lista de controles leiteiros por animal."""

    __tablename__ = "controle_leiteiro"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)


class QualidadeLeite(SQLModel, table=True):
    """
    Uma coleta de qualidade do leite — do tanque (todo o rebanho em lactação,
    numero_matriz vazio) ou de uma vaca específica (ex.: investigação de mastite).
    """

    __tablename__ = "qualidade_leite"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    competencia: str = Field(index=True)  # "YYYY-MM"
    # Volume entregue, NA UNIDADE indicada em `unidade` (o nome do campo é
    # histórico — nasceu quando só havia litro). O laticínio paga por um dos
    # dois conforme o contrato, então o produtor escolhe como lança.
    quantidade_litros: float
    # "kg" (padrão) | "L". O controle leiteiro é sempre em kg, então a
    # comparação Controle × Entregue converte a entrega para kg antes de
    # subtrair (ver DENSIDADE_LEITE_KG_POR_L em rules/unidades.py). Sem isso o
    # litro entrava como se fosse kg e o "não entregue" (bezerros + equipe)
    # saía inflado em ~2,9% do volume entregue.
    unidade: str = Field(default="kg")
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class Secagem(SQLModel, table=True):
    """Registro de secagem de uma vaca — produto(s) usado(s) entram como Sanidade (atividade='Secagem')."""

    __tablename__ = "secagem"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_matriz: str = Field(index=True)
    data_secagem: date
    motivo: str  # doente | baixa_producao | comportamento | mastite | casco | rotina | outros
    escore_condicao_corporal: Optional[float] = None  # 1 a 5, passo 0,25
    observacao: Optional[str] = None
    # Resposta explícita de "aplicar vacina pré-parto?" no momento da secagem
    # (ver POST /producao/secagem) — None é dado legado/sem resposta; True/
    # False fica gravado no histórico da vaca mesmo quando a resposta é "não"
    # (nesse caso não gera pendência nenhuma na Agenda, só o registro aqui).
    vacina_pre_parto: Optional[bool] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Lactacao(SQLModel, table=True):
    """
    Uma lactação da matriz — o período entre o evento que a abriu (parto,
    aborto ou indução) e a secagem que a fechou.

    ## A entidade que faltava

    Até aqui o sistema NÃO TINHA lactação: cada tela inferia "está em
    lactação" do seu próprio jeito — existir um `Parto`, `Animal.del_dias >
    0` (campo congelado, zerado no instante do parto e nunca mais
    atualizado), ou o código do lote começar com 01/02/03. O resultado foi o
    bug que originou esta tabela: uma matriz com aborto lançado, lactação
    aberta pelo popup, já no lote de lactação e com controle leiteiro
    lançado continuava aparecendo como "novilha gestante, sem parto" —
    porque nenhuma dessas inferências concordava com as outras.

    Com a lactação materializada, "esta vaca está em lactação em D?" e "qual
    o DEL dela em D?" viram uma consulta só, com resposta única (ver
    `fazenda.rules.lactacao`).

    ## Campos que merecem explicação

    * `data_inicio` — a data REAL do evento, aceita retroativa. É daqui que
      sai o DEL ao vivo (`hoje - data_inicio`), e é por isso que o
      endpoint de encerramento de gestação exige a data do evento: o
      caminho antigo (`POST /reproducao/animais/{n}/abrir-lactacao`) nem
      recebia data, gravava `del_dias = 0` e contaminava a curva de
      lactação do rebanho com DEL 0 em toda vaca que pariu pelo app.
    * `origem` — "parto" | "aborto" | "inducao" | "importacao". Distingue o
      que abriu a lactação; "importacao" é o backfill a partir dos partos
      que já existiam no banco antes desta tabela.
    * `parto_id` — o `Parto` correspondente, quando existe. A partir do
      endpoint único, TODO fim de gestação cria um `Parto` (inclusive o
      aborto, com `ordem_parto` NULL — ver `fazenda.rules.parto`), então na
      prática só as lactações por indução ficam sem ele.
    * `numero_lactacao` — ordem da lactação NA MATRIZ (1ª, 2ª, …). Não é a
      mesma coisa que `Parto.ordem_parto`: um aborto abre lactação sem
      avançar a ordem de parto, e uma indução abre lactação sem parto
      nenhum.
    * `data_fim`/`secagem_id` — NULL enquanto a lactação está ABERTA. É
      esse NULL que o controle leiteiro exige (ver POST /producao/controles).
    """

    __tablename__ = "lactacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    numero_matriz: str = Field(index=True)
    data_inicio: date = Field(index=True)
    origem: str = Field(default="parto")  # parto | aborto | inducao | importacao
    parto_id: Optional[int] = Field(default=None, foreign_key="parto.id", index=True)
    numero_lactacao: int = Field(default=1)
    data_fim: Optional[date] = Field(default=None, index=True)
    secagem_id: Optional[int] = Field(default=None, foreign_key="secagem.id", index=True)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    observacao: Optional[str] = None


class FaixaBonificacaoQualidade(SQLModel, table=True):
    """Faixa de bonificação/penalização por qualidade do leite, cadastrável em
    Configurações > Parâmetros (#548). Cada laticínio tem sua própria tabela de
    faixas para CCS/CBT/gordura/proteína — não existe padrão nacional único —
    por isso aqui fica só a estrutura configurável (sem valores fixos no
    código): um ajuste em R$/litro por faixa de um indicador, comparado contra
    os lançamentos de Qualidade do leite (ver fazenda/rules/bonificacao_qualidade.py)."""

    __tablename__ = "faixa_bonificacao_qualidade"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    indicador: str = Field(index=True)  # "ccs" | "cbt" | "gordura_pct" | "proteina_pct"
    valor_min: Optional[float] = None  # None = sem limite inferior
    valor_max: Optional[float] = None  # None = sem limite superior
    ajuste_por_litro: float  # R$/litro — positivo = bônus, negativo = desconto/penalização
    ativo: bool = True
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
