"""
Formulação de Dietas — biblioteca nutricional por fazenda e simulações de
dieta (motor NASEM/NRC Dairy 2021, ver fazenda/rules/nutricao/).

`DietaSimulacao` e `DietaSimulacaoItem` têm `fazenda_id` OBRIGATÓRIO (int,
não Optional): diferente do resto do repo (que aceita fazenda_id nulo por
retrocompatibilidade com token legado anterior ao piloto de multi-fazenda),
este módulo nasceu depois do piloto — não existe dado legado para acomodar,
então cada router exige fazenda_id resolvido antes de gravar (ver
fazenda/api/routers/formulacao_dietas.py).

`AlimentoNutricional.fazenda_id` é a ÚNICA exceção nesta tabela nova: é
Optional de propósito (não por retrocompatibilidade) — `fazenda_id=None`
marca as linhas da BIBLIOTECA MESTRE CowData (semeada uma vez, global,
igual para todas as fazendas — ver `fazenda.rules.biblioteca_alimentos`).
Por isso toda consulta a esta tabela que filtra por fazenda precisa ser
TOLERANTE a nulo (`fazenda_id == X OR fazenda_id IS NULL`), nunca um
`== fazenda_id` seco — do contrário a biblioteca mestre some da fazenda
inteira (== NULL nunca casa em SQL).

`AlimentoNutricional` (cadastro editável, colunas tipadas) e
`DietaSimulacaoItem` (snapshot imutável da grade no momento do cálculo, em
`valores_json`) guardam composição nutricional de formas deliberadamente
diferentes: a primeira é consultada/validada por campo, o segundo só precisa
sobreviver íntegro para o motor reprocessar — ver docstring de cada classe.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class AlimentoNutricional(SQLModel, table=True):
    """Biblioteca nutricional — um perfil de composição (NASEM) por
    `Alimento` cadastrado, ou uma entrada só-biblioteca sem cadastro
    correspondente (`alimento_id=None`). Alimenta a Etapa 1 do wizard de
    Formulação de Dietas: ao importar um alimento já cadastrado, o backend
    resolve em cascata biblioteca → análise bromatológica mais recente →
    template por `categoria_nasem` (ver GET /formulacao/alimentos/{id}/resolver).

    Biblioteca MESTRE CowData + cópia por fazenda (copy-on-write), ver
    `fazenda.rules.biblioteca_alimentos`: `fazenda_id=None` marca uma linha
    da biblioteca mestre (global, semeada uma vez, igual para todas as
    fazendas). Quando uma fazenda edita/exclui um item da mestre, o backend
    NUNCA grava na linha mestre — cria uma cópia com `fazenda_id` da fazenda
    e `origem_mestre_id` apontando pra linha mestre original. A tela de
    biblioteca de cada fazenda enxerga: suas próprias linhas (`fazenda_id`
    dela, `origem_mestre_id` nulo = item 100% próprio, ou preenchido = cópia
    editada de um item mestre) + as linhas mestre que ela NÃO tem cópia
    (`ativo=True`) e que não foram ocultadas (cópia com `ativo=False` =
    "removi este item padrão da minha biblioteca", sem apagar a mestre nem
    afetar as outras fazendas). "Restaurar ao padrão CowData" é simplesmente
    apagar a cópia da fazenda — a linha mestre, nunca tocada, volta a aparecer.

    Os ~38 campos numéricos abaixo cobrem só o que a Fase 1 usa; aminoácidos,
    microminerais, vitaminas e perfil de ácidos graxos (Fase 2) ficam em
    `extras_json` até serem promovidos a colunas reais — mantém a migração
    pequena sem impedir que o dado já seja digitado e guardado hoje.

    Exceção deliberada: o fracionamento CNCPS de carboidrato/proteína
    (`cncps_*` abaixo) JÁ nasce como coluna tipada, à frente do resto da
    Fase 2 — é o dado de entrada que as Etapas 8 (Modelo ruminal) e 9
    (Aminoácidos) do wizard vão precisar quando forem implementadas (ainda
    NÃO estão; esta classe só guarda o dado, não há leitor dele hoje). Ver
    `fazenda.rules.biblioteca_alimentos.avisos_fechamento_fracoes` para a
    checagem (não bloqueante) de que as frações somam 100%."""

    __tablename__ = "alimento_nutricional"
    __table_args__ = (
        UniqueConstraint(
            "alimento_id", "estoque_id", "fazenda_id", name="uq_alimento_nutricional_alimento_estoque_fazenda"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    # Optional DE PROPÓSITO (não retrocompatibilidade) — None = biblioteca
    # mestre CowData, global. Ver docstring da classe.
    fazenda_id: Optional[int] = Field(default=None, foreign_key="fazenda.id", index=True)
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id", index=True)
    # Preenchido quando esta linha de composição é específica de um produto
    # comercial de Estoque (ex.: "Concentrado X" da marca Y), não da família
    # Alimento inteira — nulo = entrada em nível de família (comportamento
    # histórico, antes da Fase 2 de importação por produto).
    estoque_id: Optional[int] = Field(default=None, foreign_key="estoque.id", index=True)
    # Preenchido só quando esta linha é a cópia-por-fazenda de um item da
    # biblioteca mestre (edição ou ocultação) — nulo tanto na própria linha
    # mestre quanto num item 100% próprio da fazenda (nunca existiu na mestre).
    origem_mestre_id: Optional[int] = Field(default=None, foreign_key="alimento_nutricional.id", index=True)
    nome: str = Field(index=True)
    # Vocabulário fechado — ver fazenda.rules.nutricao.tipos.CATEGORIAS_NASEM.
    # Controla as exceções de energia digestível base por categoria.
    categoria_nasem: str
    # % de concentrado na matéria seca do PRÓPRIO ingrediente (0 = volumoso
    # puro, 100 = concentrado puro) — dirige a fração de volumoso e as
    # constantes de passagem ruminal usadas no fracionamento proteico.
    conc_pct: float = 0.0
    fonte: Optional[str] = None
    observacao: Optional[str] = None
    # Numa linha mestre: sempre True (a mestre nunca é "excluída"). Numa
    # cópia-por-fazenda: True = cópia editada normal; False = "tombstone" —
    # a fazenda ocultou o item mestre correspondente (origem_mestre_id) sem
    # nunca ter editado seus valores. Ver fazenda.rules.biblioteca_alimentos.
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    # Faixa típica de inclusão na dieta, % da matéria seca TOTAL da dieta
    # (não da MS do próprio ingrediente) — referência de bom senso zootécnico
    # para o nutricionista, puxada automaticamente na Etapa 1 da grade junto
    # com o teor de MS; não entra no motor de cálculo (só orientação visual).
    inclusao_min_pct: Optional[float] = None
    inclusao_max_pct: Optional[float] = None

    # ---- Base (% da MS, salvo indicado) --------------------------------
    ms_pct: Optional[float] = None  # % da matéria NATURAL (não da MS)
    pb_pct: Optional[float] = None
    fdn_pct: Optional[float] = None
    fda_pct: Optional[float] = None
    lignina_pct: Optional[float] = None
    amido_pct: Optional[float] = None
    acucares_pct: Optional[float] = None
    ee_pct: Optional[float] = None
    ag_pct: Optional[float] = None
    cinzas_pct: Optional[float] = None
    # % da FDN digerida in vitro em 48h — usada no cálculo do CMS de vacas em
    # lactação por dieta (eq_cms=9) mesmo na Fase 1; só a digestibilidade
    # ajustada por DNDF48 (Fase 3) fica de fora.
    dndf48_fdn_pct: Optional[float] = None

    # ---- Fracionamento proteico (frações A/B/C, % da PB) ---------------
    pb_a_pct: Optional[float] = None
    pb_b_pct: Optional[float] = None
    pb_c_pct: Optional[float] = None
    kd_pb_b_pct_h: Optional[float] = None  # taxa de degradação da fração B, %/h
    nnp_pb_pct: Optional[float] = None  # nitrogênio não-proteico, % da PB
    pidn_pct: Optional[float] = None  # proteína insolúvel em detergente neutro, % da MS
    pida_pct: Optional[float] = None  # proteína insolúvel em detergente ácido, % da MS

    # ---- Digestibilidades de referência do próprio ingrediente ---------
    dig_amido_pct: Optional[float] = None
    dig_pndr_pct: Optional[float] = None
    dig_ag_pct: Optional[float] = None

    # ---- Macrominerais (% da MS) ----------------------------------------
    ca_pct: Optional[float] = None
    p_pct: Optional[float] = None
    p_inorg_p_pct: Optional[float] = None  # % do P total que é inorgânico
    p_org_p_pct: Optional[float] = None
    mg_pct: Optional[float] = None
    k_pct: Optional[float] = None
    na_pct: Optional[float] = None
    cl_pct: Optional[float] = None
    s_pct: Optional[float] = None

    # ---- Coeficientes de absorção (fração 0-1) --------------------------
    abs_ca: Optional[float] = None
    abs_p_total: Optional[float] = None
    abs_mg: Optional[float] = None
    abs_na: Optional[float] = None
    abs_cl: Optional[float] = None
    abs_k: Optional[float] = None

    # ---- Custo -----------------------------------------------------------
    custo_kg_mn: Optional[float] = None  # R$/kg de matéria natural

    # ---- Fracionamento CNCPS de carboidrato (v6.5), % da MATÉRIA SECA ---
    # Nomenclatura A (solúvel) / B (insolúvel potencialmente digestível) /
    # C (indigestível) do CNCPS original (Sniffen et al., 1992, J. Anim.
    # Sci. 70:3562-3577), com o detalhamento em subfrações da revisão v6.5
    # (Van Amburgh et al., 2015, J. Dairy Sci. 98:6361-6380; Higgs et al.,
    # 2015, J. Dairy Sci. 98:6340-6360 — tabela de kd por alimento). Junto
    # com PB/EE/Cinzas dá o "fechamento": CA1+CA2+CA3+CA4+CB1+CB2+CB3+CC
    # deve somar (100 − PB − EE − Cinzas), isto é, 100% do carboidrato do
    # alimento — ver `avisos_fechamento_fracoes`.
    #
    # kd (taxa de degradação ruminal, %/h) só vira COLUNA para a fração que
    # de fato tem uma taxa própria, medida/estimada por alimento (varia de
    # ingrediente pra ingrediente). Duas frações ficam de fora de propósito:
    #   - CA1 (ácidos orgânicos — acético/propiônico/butírico, típico de
    #     silagem): já é produto final de fermentação, não fermenta mais no
    #     rúmen — kd=0 por definição do sistema, não é dado do alimento.
    #   - CC (FDN indigestível/uNDF): indigestível É o oposto de "ter uma
    #     taxa" — kd=0 sempre, por definição, também não é dado do alimento.
    # As outras seis (CA2, CA3, CA4, CB1, CB2, CB3) ganham campo de kd.
    cncps_ca1_pct: Optional[float] = None  # ácidos orgânicos (acético/propiônico/butírico) — sem kd, ver acima
    cncps_ca2_pct: Optional[float] = None  # ácido lático
    cncps_kd_ca2_pct_h: Optional[float] = None
    cncps_ca3_pct: Optional[float] = None  # outros ácidos orgânicos/solúveis
    cncps_kd_ca3_pct_h: Optional[float] = None
    cncps_ca4_pct: Optional[float] = None  # açúcares (WSC — carboidrato solúvel em água)
    cncps_kd_ca4_pct_h: Optional[float] = None
    cncps_cb1_pct: Optional[float] = None  # amido
    cncps_kd_cb1_pct_h: Optional[float] = None
    cncps_cb2_pct: Optional[float] = None  # fibra solúvel (pectina e afins — calculada por diferença no laudo)
    cncps_kd_cb2_pct_h: Optional[float] = None
    cncps_cb3_pct: Optional[float] = None  # FDN potencialmente digestível
    cncps_kd_cb3_pct_h: Optional[float] = None
    cncps_cc_pct: Optional[float] = None  # FDN indigestível (uNDF/uNDF240) — sem kd, ver acima

    # ---- Fracionamento CNCPS de proteína (v6.5), % da PROTEÍNA BRUTA ----
    # PA1+PA2+PB1+PB2+PC deve somar 100% da PB do alimento — ver
    # `avisos_fechamento_fracoes`. Mesma fonte da seção de carboidrato acima.
    #
    # kd só vira coluna pra quem tem taxa própria e variável por alimento:
    #   - PA1 (amônia): já é N mineral, não "degrada" — é absorvida direto.
    #     O próprio CNCPS trata isso como praticamente instantâneo (kd
    #     nominal de 200%/h, um valor de sistema, não medido por alimento —
    #     Van Amburgh et al., 2015), então não é dado do alimento.
    #   - PC (proteína indisponível, ligada a ADF/lignina): por definição
    #     praticamente indigestível — sem taxa própria de degradação.
    # PA2, PB1 e PB2 ganham campo de kd (variam de verdade por alimento —
    # PB2, em especial, acompanha a taxa de digestão da fibra, CB3).
    cncps_pa1_pct: Optional[float] = None  # amônia
    cncps_pa2_pct: Optional[float] = None  # peptídeos solúveis/proteína verdadeira solúvel
    cncps_kd_pa2_pct_h: Optional[float] = None
    cncps_pb1_pct: Optional[float] = None  # proteína rapidamente degradável
    cncps_kd_pb1_pct_h: Optional[float] = None
    cncps_pb2_pct: Optional[float] = None  # proteína lentamente degradável (ligada à FDN)
    cncps_kd_pb2_pct_h: Optional[float] = None
    cncps_pc_pct: Optional[float] = None  # proteína indisponível (ligada a ADF/lignina) — sem kd, ver acima

    # Quais dos campos acima (e dos ~38 campos "Base"/"Custo" desta classe)
    # foram digitados à mão pelo usuário desta fazenda, em oposição a
    # puxados automaticamente da linha mestre CowData — mesma convenção
    # (nomes de coluna como string num array-JSON) de
    # `DietaSimulacaoItem.campos_editados_json`, reaproveitada aqui de
    # propósito (não é um mecanismo novo). Cinza na tela = ainda é o valor
    # da mestre; preto e negrito = este item já foi verificado/editado pela
    # fazenda para este campo específico. Nunca populado na própria linha
    # mestre (ela é sempre 100% CowData, por definição).
    campos_editados_json: Optional[str] = None

    # ---- Fase 2/3 (aminoácidos, microminerais, vitaminas, perfil de AG) -
    extras_json: Optional[str] = None


# Todos os campos do fracionamento CNCPS acima — usado para o copy-on-write
# (`_clonar_para_fazenda`, em fazenda.rules.biblioteca_alimentos) e para a
# extração/gravação genérica no router (criar/atualizar item da biblioteca),
# igual em espírito a `CAMPOS_NUTRICIONAIS` (fazenda.rules.nutricao.tipos)
# mas DELIBERADAMENTE um conjunto separado: estes campos NÃO entram no
# contrato do motor (`IngredienteEntrada`) nem na grade/snapshot do wizard
# (`DietaSimulacaoItem.valores_json`) — a Fase 1 (Etapas 1-7, já
# implementada) não lê nenhum deles; só a biblioteca cadastra/importa/valida
# o fechamento, para quando as Etapas 8/9 existirem.
CAMPOS_CNCPS_CARBOIDRATO: tuple[str, ...] = (
    "cncps_ca1_pct", "cncps_ca2_pct", "cncps_ca3_pct", "cncps_ca4_pct",
    "cncps_cb1_pct", "cncps_cb2_pct", "cncps_cb3_pct", "cncps_cc_pct",
)
CAMPOS_CNCPS_PROTEINA: tuple[str, ...] = (
    "cncps_pa1_pct", "cncps_pa2_pct", "cncps_pb1_pct", "cncps_pb2_pct", "cncps_pc_pct",
)
CAMPOS_CNCPS_KD: tuple[str, ...] = (
    "cncps_kd_ca2_pct_h", "cncps_kd_ca3_pct_h", "cncps_kd_ca4_pct_h",
    "cncps_kd_cb1_pct_h", "cncps_kd_cb2_pct_h", "cncps_kd_cb3_pct_h",
    "cncps_kd_pa2_pct_h", "cncps_kd_pb1_pct_h", "cncps_kd_pb2_pct_h",
)
CAMPOS_CNCPS_FRACIONAMENTO: tuple[str, ...] = CAMPOS_CNCPS_CARBOIDRATO + CAMPOS_CNCPS_PROTEINA + CAMPOS_CNCPS_KD


class DietaSimulacao(SQLModel, table=True):
    """Cabeçalho de uma simulação de Formulação de Dietas — os dados do
    animal/lote (Etapa 2), as chaves de equação escolhidas, e o resultado do
    último cálculo (`resultado_json`, texto-como-JSON — mesmo padrão de
    `Usuario.permissoes` no resto do repo). Uma simulação
    pode ser salva em rascunho, recalculada quantas vezes o usuário quiser, e
    opcionalmente aplicada como uma `DietaLancamento` real do lote."""

    __tablename__ = "dieta_simulacao"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    nome: str = Field(index=True)
    lote: Optional[int] = Field(default=None, index=True)
    # "rascunho" | "concluida" | "aplicada" | "arquivada"
    status: str = Field(default="rascunho", index=True)
    etapa_atual: int = 1

    # ---- Animal/lote (Etapa 2) ------------------------------------------
    # "vaca_lactante" | "vaca_seca" | "novilha" | "bezerra"
    estado_fisiologico: str = "vaca_lactante"
    # "Holandes" | "Jersey" | "Outra"
    raca: str = "Holandes"
    peso_vivo_kg: float = 0.0
    peso_maturo_kg: float = 680.0
    ecc: float = 3.0  # escore de condição corporal, 1 a 5, passo 0,25
    paridade: float = 1.0  # 0 = novilha; 1-2 real (média do lote)
    idade_dias: Optional[int] = None
    del_dias: Optional[int] = None
    dias_gestacao: Optional[int] = None
    duracao_gestacao_dias: int = 283
    peso_bezerro_nascer_kg: float = 44.1
    del_concepcao: Optional[int] = None
    idade_concepcao_1a_dias: Optional[int] = None
    ganho_estrutura_kg_dia: float = 0.0
    ganho_reserva_kg_dia: float = 0.0
    producao_leite_kg_dia: Optional[float] = None
    gordura_leite_pct: Optional[float] = None
    proteina_leite_pct: Optional[float] = None
    lactose_leite_pct: float = 4.78
    potencial_genetico_pl_305: float = 280.0

    # ---- Ambiente e manejo ------------------------------------------------
    temperatura_c: float = 24.0
    distancia_sala_m: float = 0.0
    viagens_sala_dia: int = 4
    desnivel_diario_m: float = 0.0

    # ---- Chaves de equação (ver fazenda.rules.nutricao) -------------------
    # 0=informado pelo usuário · 2/3=novilha · 8/9=vaca lactante · 10/11=vaca seca
    eq_cms: int = 8
    cms_informado_kg_dia: Optional[float] = None  # usado quando eq_cms=0
    usa_monensina: bool = False
    # Como descontar o efeito da monensina sobre o CMS (ago/2026): "kg" =
    # -0,30 kg MS/dia (Duffield et al., 2008) | "pct" = -2% do CMS |
    # "manual" = monensina_reducao_manual. Só vale com usa_monensina=True.
    monensina_modo: str = "kg"
    monensina_reducao_manual: Optional[float] = None
    eq_microbiana: int = 1  # só 1 (NASEM 2021) na Fase 1
    usa_dndf48: int = 0  # travado em 0 na Fase 1 (ajuste de digestibilidade por DNDF48; Fase 3)

    # ---- Resultado do último cálculo --------------------------------------
    motor_versao: Optional[str] = None
    calculado_em: Optional[datetime] = None
    resultado_json: Optional[str] = None
    avisos_json: Optional[str] = None
    # Overrides manuais da coluna "Exigência" da Etapa 4 (balanço ao vivo),
    # {nutriente: valor} — o motor sempre recalcula a exigência a partir do
    # animal (Etapa 3), mas o nutricionista pode sobrepor um valor pontual
    # (ex.: exigência de uma tabela própria da fazenda); o balanço/situação
    # daquela linha passa a usar o valor sobreposto (ver `_calcular` em
    # formulacao_dietas.py). Convenção de cor cinza/preto igual à de
    # `campos_editados_json` em DietaSimulacaoItem — ver PainelBalanco.tsx.
    exigencias_editadas_json: Optional[str] = None

    # ---- Aplicação na dieta real -------------------------------------------
    dieta_lancamento_id: Optional[int] = Field(default=None, foreign_key="dieta_lancamento.id")
    aplicada_em: Optional[datetime] = None
    aplicada_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")

    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class DietaSimulacaoItem(SQLModel, table=True):
    """Uma linha (ingrediente) da grade de uma `DietaSimulacao` — snapshot
    imutável dos valores nutricionais usados no cálculo (`valores_json`),
    para a simulação nunca mudar de resultado se o cadastro de origem
    (`AlimentoNutricional`/`AnaliseBromatologica`) for editado depois. Salvar
    a simulação de novo (PUT) substitui a grade inteira e gera um snapshot
    novo — não há edição parcial de item isolado no banco."""

    __tablename__ = "dieta_simulacao_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    simulacao_id: int = Field(foreign_key="dieta_simulacao.id", index=True)
    ordem: int = 0
    # None = linha manual (sem cadastro de Alimento); preenchido = importada.
    alimento_id: Optional[int] = Field(default=None, foreign_key="alimento.id")
    alimento_nutricional_id: Optional[int] = Field(default=None, foreign_key="alimento_nutricional.id")
    analise_bromatologica_id: Optional[int] = Field(default=None, foreign_key="analise_bromatologica.id")
    # Produto de Estoque específico escolhido na importação (ex.: "Concentrado
    # X" dentro da família Concentrado Protéico) — None = item importado no
    # nível de família, ou linha manual. Denormalizado (produto_nome) para o
    # snapshot da simulação sobreviver à exclusão/renomeação do item de Estoque.
    estoque_id: Optional[int] = Field(default=None, foreign_key="estoque.id")
    produto_nome: Optional[str] = None
    nome: str
    # "biblioteca" | "bromatologica" | "template" | "manual"
    origem: str = "manual"
    proporcao_ms_pct: float = 0.0
    categoria_nasem: str = "Outros"
    # Duplicados como coluna (também vêm em valores_json) — usados fora do
    # motor: listagem/resumo volumoso×concentrado, conversão MS↔MN ao
    # aplicar na dieta, e custo total sem precisar reabrir o JSON.
    conc_pct: float = 0.0
    ms_pct: Optional[float] = None
    custo_kg_mn: Optional[float] = None
    valores_json: str = "{}"
    campos_editados_json: Optional[str] = None
