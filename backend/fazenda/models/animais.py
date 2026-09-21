"""
Rebanho — cadastro de animais, lotes, baixa/compra/venda e motivos cadastrados.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

# ---------------------------------------------------------------------------
# Animal
# ---------------------------------------------------------------------------
class Animal(SQLModel, table=True):
    """Foto atual de cada animal — alimentado pelo GERAL.csv."""

    __tablename__ = "animal"
    # Unicidade de `numero` é POR FAZENDA, não global (ver migração
    # animal_numero_unico_por_fazenda) — duas fazendas diferentes têm cada
    # uma, legitimamente, uma vaca "100". `numero` sozinho continua indexado
    # (não único) logo abaixo, porque boa parte do código ainda busca só por
    # ele, sem filtrar fazenda (ver relatório da "fundação" multi-tenant,
    # PR desta migração — auditoria completa dos pontos que assumem `numero`
    # como identificador global; não corrigidos aqui, fora de escopo desta
    # frente).
    __table_args__ = (UniqueConstraint("numero", "fazenda_id", name="uq_animal_numero_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    # Piloto conservador de multi-fazenda (ver fazenda/models/multitenant.py):
    # nulo para todo animal de instalações que nunca passaram pela migração de
    # backfill, e preenchido a partir daí — ainda não filtra nada sozinho, só
    # o endpoint de listagem (GET /animais) e o de cadastro (POST .../animais)
    # o consideram por enquanto.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero: str = Field(index=True)
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
    # Data em que a marcação acima passou a valer — ausente em `a_descartar`
    # (que é só o booleano "sim/não", sem quando). Sem esta data o motor do
    # programa reprodutivo (fazenda/rules/programa_reprodutivo.py) não
    # conseguia reconstruir o passado: um animal marcado hoje sumia de TODOS
    # os ciclos históricos, inclusive dos em que estava ativo. NULL cobre dois
    # casos que não dá pra distinguir: nunca foi marcado, OU foi marcado antes
    # de esta coluna existir (ver migração c576e514aa3e — a coluna nasceu sem
    # backfill retroativo de propósito). Sempre gravada/limpa junto com
    # `a_descartar` (ver marcar_a_descartar em api/routers/baixas.py).
    a_descartar_em: Optional[date] = None
    # QUANDO SE PRETENDE tirar o animal do rebanho — o plano físico da saída
    # (a boiada, o caminhão, a próxima venda). NÃO confundir com as duas linhas
    # acima, e a confusão é o risco real deste trio:
    #
    #   a_descartar          -> a decisão vale hoje? (booleano)
    #   a_descartar_em       -> QUANDO SE DECIDIU. É esta que o motor do
    #                           programa reprodutivo lê (`descartada_em`), e a
    #                           partir dela o animal sai do denominador.
    #   descarte_previsto_em -> QUANDO SE PRETENDE FAZER. Opcional, e não
    #                           influencia cálculo reprodutivo nenhum.
    #
    # Opcional de propósito: nem toda decisão de descarte nasce com data
    # marcada, e ficar em branco é um estado legítimo — não uma pendência.
    # Quando preenchida, vira evento na Agenda (ver agenda_engine.py) para a
    # data não ficar só na cabeça de quem decidiu. Limpa junto com as outras
    # duas ao desmarcar.
    descarte_previsto_em: Optional[date] = None
    # Marca manual: nunca entra nas listas de candidatas/excluídos do BST
    # (ex.: vaca com contraindicação), independente dos critérios automáticos.
    excluir_bst: bool = False
    # "Reverter (voltar a apta)": revertida de excluir_bst, mas ainda não conta
    # como apta de novo — só volta a aparecer em bst_elegiveis depois que uma
    # NOVA aplicação de BST é lançada para o animal (ver aplicar_bst_lote).
    # Até lá fica na lista "Incluir no próximo BST" (bst_reanalise).
    aguardando_nova_aplicacao_bst: bool = False
    # Marcado ao confirmar "Entrou em lactação?" de um protocolo de indução
    # de lactação (POST /producao/inducao-lactacao/.../confirmar, campo
    # incluir_bst) — o protocolo de indução já aplica BST nele mesmo, então
    # o animal entra direto em "Incluir no próximo BST" (junto com
    # aguardando_nova_aplicacao_bst=True) sem esperar o DEL mínimo normal.
    # Só existe para o front distinguir esse caso com a notinha "(ind.lact.)"
    # (ver agenda_engine.py); limpa junto com aguardando_nova_aplicacao_bst
    # assim que uma aplicação real de BST é lançada, ou se marcada como
    # inapta manualmente.
    bst_pendente_inducao_lactacao: bool = False


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
    __table_args__ = (UniqueConstraint("codigo", "fazenda_id", name="uq_lote_codigo_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    nome: str
    del_min: Optional[int] = None
    del_max: Optional[int] = None  # também usado no critério "até X dias após o parto"
    producao_min: Optional[float] = None  # também usado no critério "produção de X a Y L"
    producao_max: Optional[float] = None
    ativo: bool = True
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)

    # ---- Permissões do lançamento de consumo de alimento (Lançamentos >
    # Alimentação). Ambas nascem FALSE de propósito: o padrão restritivo é o
    # seguro, porque cada uma desliga uma checagem que existe para pegar erro
    # de digitação no curral. Quem precisa da exceção liga por lote, que é onde
    # a exceção de fato acontece — o lote de transição que recebe um alimento
    # fora da dieta, o silo que acabou e será reposto hoje.
    permitir_fora_da_dieta: bool = False
    permitir_sem_estoque: bool = False

    # ---- Como a dieta deste lote afeta o Estoque (proposta aceita pelo
    # proprietário: "automática pela dieta" / "pelo consumo real" / "sem
    # baixa"). Valores válidos: "automatica" (baixa dia a dia pelo PLANO —
    # `_dar_baixa_automatica`), "consumo_real" (só baixa quando alguém lança
    # o consumo de verdade em "Consumo diário e sobra" — `lancar_consumo`) ou
    # "sem_baixa" (a dieta é só plano/receita, nunca mexe em estoque).
    # "consumo_real" nasce padrão porque é o ÚNICO mecanismo que já funciona
    # hoje de ponta a ponta — todo lote existente antes desta coluna continua
    # se comportando exatamente como antes.
    modo_baixa_estoque: str = "consumo_real"

    # ---- Critérios de seleção de animais (cumulativos/E lógico) — usados na
    # prévia de "quantos animais atendem" e, na sequência, nas sugestões
    # automáticas de movimentação entre lotes. Cada campo None = não filtra.
    # `status_lactacao` (rótulo na tela: "Situação produtiva") e `del_min`/
    # `del_max` (rótulo: "Dias pós-parto") são comparados AO VIVO — calculados
    # a partir do Secagem/Parto mais recente do animal (mesma lógica de
    # fazenda.api.routers.recria._contexto_categoria), não do texto congelado
    # de Animal.categoria_completa/del_dias (que só atualiza no próximo
    # GERAL.csv) — ver fazenda.rules.lote_criterios.
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
    # Situação reprodutiva ("vazia"|"vazia_atrasada"|"inseminada"|"prenha") —
    # mesmos valores e mesma derivação AO VIVO que
    # CategoriaManejo.situacao_reprodutiva (ver
    # fazenda.api.routers.recria._situacao_reprodutiva_3); "vazia" também casa
    # com a atrasada, por retrocompatibilidade.
    situacao_reprodutiva: Optional[str] = None
    dias_gestacao_min: Optional[int] = None
    dias_gestacao_max: Optional[int] = None
    dias_desde_servico_min: Optional[int] = None
    dias_desde_servico_max: Optional[int] = None
    # Vínculo com uma ou mais categorias de manejo cadastradas em
    # Configurações > Cadastro > Categorias (CategoriaManejo.id, lista
    # separada por vírgula — mesmo padrão simples de `categorias` acima).
    # Quando preenchido, só entra no critério do lote o animal cuja
    # classificação atual (classificar_categoria) bater com o NOME de uma
    # dessas categorias — refinamento adicional aos critérios diretos acima,
    # não uma substituição deles (ambos valem em E lógico).
    categoria_manejo_ids: Optional[str] = None
    # Lote existe (ex.: enfermaria, quarentena, venda) mas não deve nunca ser
    # sugerido automaticamente por bater nos critérios acima — a movimentação
    # pra ele continua manual. Ver fazenda.rules.lote_criterios::sugerir_lote.
    excluir_da_sugestao: bool = False


# ---------------------------------------------------------------------------
# Movimento de lote (histórico de transferências de animais entre lotes)
# ---------------------------------------------------------------------------
class MovimentoLote(SQLModel, table=True):
    """Registro de cada transferência manual de animal entre lotes."""

    __tablename__ = "movimento_lote"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    # De ONDE veio a movimentação — não confundir com `motivo` (texto livre/
    # cadastrável, ex.: "Secagem", "Parto"), que pode ter o MESMO valor tanto
    # numa troca automática confirmada quanto numa digitada à mão. `origem` é
    # quem determina isso de fato, atribuído pelo próprio código que chama
    # POST /movimentacoes/mover (ver fazenda.api.routers.movimentacoes),
    # nunca inferido do texto do motivo. Valores possíveis:
    #   "manual"               — Rebanho > Movimentar animais (tela avulsa),
    #                            e a inativação de lote (CadastroLotes; humano
    #                            escolhe o destino explicitamente nos dois casos).
    #   "sugestao_confirmada"  — pop-up de sugestão pós-evento (parto/secagem/
    #                            pré-parto) que o usuário viu e confirmou.
    #   "sugestao_automatica"  — mesma sugestão do motor de critérios de um
    #                            evento, mas aplicada sem pop-up de confirmação
    #                            (hoje só a alocação da cria no lançamento de
    #                            parto em lote/categoria — ver alocarSemConfirmar
    #                            em FormParto.tsx; é uma decisão do código, não
    #                            um clique do usuário, por isso não entra em
    #                            "sugestao_confirmada").
    #   "sugestao_passiva"     — card de sugestão da Agenda ou tela dedicada
    #                            Rebanho > Sugestões de movimentação (sugestão
    #                            periódica, não amarrada a um evento específico).
    #   "importacao"           — reservado para o dia em que o upload do
    #                            GERAL.csv passar a gerar histórico de
    #                            movimentação; HOJE o upload só atualiza
    #                            Animal.grupo_primario direto, sem criar
    #                            MovimentoLote (ver test_lotes_movimentacoes.py
    #                            ::test_upload_geral_nao_sobrescreve_lote_movido_manualmente)
    #                            — não usado ainda.
    #   None ("desconhecida" no /movimentacoes/ listado, ver rótulo no front)
    #                          — histórico gravado antes deste campo existir;
    #                            não dá pra inferir retroativamente, então fica
    #                            em branco em vez de forçar uma origem falsa.
    origem: Optional[str] = None


class MotivoBaixa(SQLModel, table=True):
    """Causa específica de uma baixa de animal (Rebanho > Baixar animal), cadastrável em Configurações."""

    __tablename__ = "motivo_baixa"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_motivo_baixa_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class MotivoVenda(SQLModel, table=True):
    """Motivo da venda de um animal (Lançamentos > Compra/Venda > Vender animal), cadastrável em Configurações."""

    __tablename__ = "motivo_venda"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_motivo_venda_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Raca(SQLModel, table=True):
    """Raça de animal (Girolando, Holandês, Gir...), cadastrável em Configurações — substitui o select fixo do cadastro de animal."""

    __tablename__ = "raca"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_raca_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    # Nota didática curta (ex.: "Zebuína indiana, referência mundial em
    # leite entre as raças zebuínas — a base leiteira do Girolando.") — mostrada
    # como subtítulo no seletor da ficha do animal, para quem não conhece a
    # raça de cor não precisar sair da tela para pesquisar.
    nota: Optional[str] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_grau_sangue_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    # Nota didática curta explicando a sigla/fração (ex.: "PO = Puro de
    # Origem — animal registrado, sem cruzamento.") — mesma finalidade da
    # nota de Raça, acima.
    nota: Optional[str] = None
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    fracao_holandes: Optional[float] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Motivo de movimentação de lote — lista editável (Configurações > Cadastro),
# substitui a constante Python fixa que existia antes.
# ---------------------------------------------------------------------------
class MotivoMovimentacao(SQLModel, table=True):
    """Motivo cadastrável de movimentação entre lotes."""

    __tablename__ = "motivo_movimentacao"
    __table_args__ = (UniqueConstraint("nome", "fazenda_id", name="uq_motivo_movimentacao_nome_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Parâmetro de agendamento das sugestões de movimentação entre lotes
# (Configurações > Parâmetros) — uma linha por fazenda (mesmo padrão de
# `ParametroDiariaPadrao`). Define quando uma sugestão (animal que atende a
# outro lote, calculada em `sugerir_movimentacoes`) aparece na Agenda: no
# próprio dia em que o parâmetro do lote passa a ser atendido, ou só no
# próximo dia fixo da semana (ex.: toda sexta), agrupando as sugestões da
# semana.
# ---------------------------------------------------------------------------
class ParametroSugestaoMovimentacao(SQLModel, table=True):
    __tablename__ = "parametro_sugestao_movimentacao"
    __table_args__ = (UniqueConstraint("fazenda_id", name="uq_parametro_sugestao_movimentacao_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    modo: str = "na_data_parametro"  # "na_data_parametro" | "dia_fixo_semana"
    dia_semana: int = 4  # 0=segunda ... 6=domingo (padrão: sexta)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Baixa de animal (Rebanho > Baixar animal) — morte/descarte, distinto da
# movimentação entre lotes. Ao registrar, o animal é marcado inativo.
# ---------------------------------------------------------------------------
class BaixaAnimal(SQLModel, table=True):
    """Registro de saída definitiva de um animal do rebanho (óbito/descarte)."""

    __tablename__ = "baixa_animal"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    numero_animal: str = Field(index=True)
    tipo_baixa: str  # morte | descarte_voluntario | descarte_involuntario
    motivo: str      # venda | abate | acidente | doenca | macho | outros
    motivo_doenca: Optional[str] = None  # causa específica cadastrada — motivo == "doenca" (obrigatório) ou "acidente" (opcional)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
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
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    origem_tipo: str  # "venda_animal" | "compra_animal"
    numero_lancamento: str  # LC-... do lançamento de venda/compra ao qual esta comissão se refere
    corretor_nome: str
    valor_comissao: float
    forma: str  # "redirecionado" (segue o pagamento da transação) | "separado" (conta a pagar própria)
    numero_lancamento_comissao: Optional[str] = None  # LC-... da despesa de comissão criada
    observacao: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
