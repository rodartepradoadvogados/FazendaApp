"""
Parâmetros da fazenda — metas e configurações zootécnicas/financeiras
editáveis pelo usuário (Configurações > Parâmetros).

Persistidos na tabela `parametro_fazenda` (ver `fazenda.models.ParametroFazenda`).
`DEFINICOES` abaixo é só a lista de sementes (chave/grupo/label/valor/tipo/
unidade) usada por `seed_parametros()` para popular o banco na primeira vez —
depois de seedado, o valor que vale é sempre o do banco (editável via
`PUT /parametros/{chave}`), nunca mais esta lista.

`get_param()` preserva a assinatura antiga (chave, padrao) -> float|int|None
para não quebrar nenhum dos ~15 call sites espalhados pelas regras/relatórios;
`get_param_bool()`/`get_param_date()` cobrem os novos parâmetros booleanos e
de data (ex.: uso de adesivo de detecção de cio, data de corte da concepção).
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

# Rótulo de cada grupo, na ordem em que aparecem na tela de Parâmetros.
GRUPO_TITULOS: dict[str, str] = {
    "manejo": "Manejo reprodutivo",
    "aptidao_novilha": "Aptidão de novilhas",
    "gestacao_parto": "Gestação e parto",
    "bst": "BST",
    "reinseminacao_cio": "Reinseminação e observação de cio",
    "agenda_sistema": "Agenda e sistema",
    "metas_reproducao": "Metas reprodutivas",
    "producao_descarte": "Produção e descarte",
    "estoque_semen": "Estoque de sêmen",
    "folha_rh": "Folha de pagamento / RH",
    "estrutura_fazenda": "Estrutura da fazenda",
}

# Sementes iniciais — só usadas por `seed_parametros()` na primeira vez que
# cada chave aparece (nunca sobrescreve um valor já editado no banco).
DEFINICOES: list[dict] = [
    # ---- Manejo reprodutivo ------------------------------------------------
    {"chave": "periodo_seco_dias", "grupo": "manejo", "label": "Período seco", "valor": 60, "unidade": "dias"},
    {"chave": "pev_dias", "grupo": "manejo", "label": "Período de espera voluntária (PEV)", "valor": 45, "unidade": "dias"},
    {"chave": "dias_toque", "grupo": "manejo", "label": "Dias para toque (diagnóstico)", "valor": 30, "unidade": "dias"},
    {"chave": "dias_reconfirmacao", "grupo": "manejo", "label": "Dias para reconfirmação", "valor": 30, "unidade": "dias"},
    {"chave": "intervalo_visita_reprodutiva", "grupo": "manejo", "label": "Intervalo da visita reprodutiva", "valor": 21, "unidade": "dias"},
    {"chave": "intervalo_bst", "grupo": "manejo", "label": "Intervalo de aplicação de BST", "valor": 12, "unidade": "dias"},
    {"chave": "intervalo_visita_vet", "grupo": "manejo", "label": "Intervalo de visitas do veterinário", "valor": 30, "unidade": "dias"},
    {"chave": "idade_maturidade_novilha", "grupo": "manejo", "label": "Idade de maturidade da novilha", "valor": 16, "unidade": "meses"},

    # ---- Aptidão de novilhas (gate de entrada em listas de análise/
    # relatório/vacinação/protocolos de novilhas aptas) ----------------------
    {"chave": "peso_apta_min", "grupo": "aptidao_novilha", "label": "Peso mínimo de aptidão", "valor": 300, "unidade": "kg"},
    {"chave": "peso_verificar_aptidao_min", "grupo": "aptidao_novilha", "label": "Peso mínimo p/ verificar aptidão", "valor": 280, "unidade": "kg"},
    {"chave": "idade_apta_min_meses", "grupo": "aptidao_novilha", "label": "Idade mínima de aptidão", "valor": 15, "unidade": "meses"},
    {"chave": "idade_verificar_aptidao_meses", "grupo": "aptidao_novilha", "label": "Idade mínima p/ verificar aptidão", "valor": 14, "unidade": "meses"},

    # ---- Gestação e parto ---------------------------------------------------
    {"chave": "gestacao_dias_min", "grupo": "gestacao_parto", "label": "Gestação — dias mínimo", "valor": 280, "unidade": "dias"},
    {"chave": "gestacao_dias_max", "grupo": "gestacao_parto", "label": "Gestação — dias máximo", "valor": 295, "unidade": "dias"},
    {"chave": "pre_parto_min", "grupo": "gestacao_parto", "label": "Janela de pré-parto — dias mínimo", "valor": 31, "unidade": "dias"},
    {"chave": "pre_parto_max", "grupo": "gestacao_parto", "label": "Janela de pré-parto — dias máximo", "valor": 60, "unidade": "dias"},

    # ---- BST -----------------------------------------------------------------
    {"chave": "del_minimo_bst", "grupo": "bst", "label": "DEL mínimo para BST", "valor": 60, "unidade": "dias"},
    {"chave": "dias_antes_secagem_bst", "grupo": "bst", "label": "Dias antes da secagem para sair do BST", "valor": 15, "unidade": "dias"},
    # Ajuste manual da "próxima aplicação BST" (Produção > Relatórios de BST e
    # Lançamentos > Produção > BST) quando o usuário escolhe a opção "considerar
    # essa nova data a referência para a contagem de x dias" — guarda a data
    # equivalente de "última aplicação" para que o cálculo padrão (âncora +
    # intervalo_bst) reproduza a data escolhida. Vazio = sem ajuste manual
    # pendente (o cálculo usa só as aplicações reais lançadas em Sanidade).
    {"chave": "bst_ajuste_ancora_data", "grupo": "bst", "label": "Ajuste manual da próxima aplicação de BST", "valor": "", "tipo": "date"},

    # ---- Reinseminação e observação de cio ------------------------------------
    {"chave": "dias_reinseminacao_min", "grupo": "reinseminacao_cio", "label": "Dias para reinseminação — mínimo", "valor": 18, "unidade": "dias"},
    {"chave": "dias_reinseminacao_max", "grupo": "reinseminacao_cio", "label": "Dias para reinseminação — máximo", "valor": 25, "unidade": "dias"},
    {"chave": "usa_adesivo_deteccao_cio", "grupo": "reinseminacao_cio", "label": "Utiliza adesivos para detecção de cio de repasse?", "valor": "false", "tipo": "bool"},
    {"chave": "dias_adesivo_cio_min", "grupo": "reinseminacao_cio", "label": "Observação de cio (adesivo) — dias mínimo", "valor": 15, "unidade": "dias"},
    {"chave": "dias_adesivo_cio_max", "grupo": "reinseminacao_cio", "label": "Observação de cio (adesivo) — dias máximo", "valor": 28, "unidade": "dias"},

    # ---- Agenda e sistema ------------------------------------------------------
    {"chave": "janela_eventos_sanitarios_passado", "grupo": "agenda_sistema", "label": "Janela de eventos sanitários — dias no passado", "valor": 120, "unidade": "dias"},
    {"chave": "janela_eventos_sanitarios_futuro", "grupo": "agenda_sistema", "label": "Janela de eventos sanitários — dias no futuro", "valor": 180, "unidade": "dias"},
    {"chave": "dias_contas_a_pagar_agenda", "grupo": "agenda_sistema", "label": "Contas a pagar na agenda — próximos dias", "valor": 10, "unidade": "dias"},
    {"chave": "data_corte_taxa_concepcao", "grupo": "agenda_sistema", "label": "Data de corte para taxa de concepção", "valor": "2026-01-01", "tipo": "date"},
    # Ids de usuário (separados por vírgula) liberados a usar o Assistente
    # Virtual além do dono da fazenda (contratante) — ver
    # fazenda.rules.assistente e fazenda.api.routers.assistente. Vazio = só o
    # dono mesmo (comportamento de hoje).
    {"chave": "assistente_usuarios_liberados", "grupo": "agenda_sistema", "label": "Assistente — usuários liberados além do dono (ids separados por vírgula)", "valor": "", "tipo": "texto"},

    # ---- Metas reprodutivas ----------------------------------------------------
    {"chave": "meta_del_max_1o_servico", "grupo": "metas_reproducao", "label": "DEL máximo para 1º serviço", "valor": 100, "unidade": "dias"},
    {"chave": "meta_del_medio_1o_servico", "grupo": "metas_reproducao", "label": "DEL médio ao 1º serviço", "valor": 70, "unidade": "dias"},
    {"chave": "meta_del_medio", "grupo": "metas_reproducao", "label": "DEL médio do rebanho", "valor": 200, "unidade": "dias"},
    {"chave": "meta_taxa_servico", "grupo": "metas_reproducao", "label": "Taxa de serviço em vacas", "valor": 50, "unidade": "%"},
    {"chave": "meta_taxa_concepcao", "grupo": "metas_reproducao", "label": "Taxa de concepção em vacas", "valor": 35, "unidade": "%"},
    {"chave": "meta_taxa_prenhez", "grupo": "metas_reproducao", "label": "Taxa de prenhez em vacas", "valor": 18, "unidade": "%"},
    {"chave": "meta_concepcao_novilha", "grupo": "metas_reproducao", "label": "Taxa de concepção da novilha", "valor": 60, "unidade": "%"},
    {"chave": "meta_iep_meses", "grupo": "metas_reproducao", "label": "Intervalo entre partos (IEP)", "valor": 14, "unidade": "meses"},
    {"chave": "meta_taxa_perda_prenhez", "grupo": "metas_reproducao", "label": "Taxa de perda de prenhez", "valor": 15, "unidade": "%"},

    # ---- Produção e descarte -----------------------------------------------
    {"chave": "taxa_reposicao", "grupo": "producao_descarte", "label": "Taxa de reposição", "valor": 25, "unidade": "%"},
    {"chave": "producao_minima_secagem", "grupo": "producao_descarte", "label": "Produção mínima de leite para secagem", "valor": 15, "unidade": "kg/dia"},
    {"chave": "meses_queda_reprodutiva", "grupo": "producao_descarte", "label": "Meses de queda reprodutiva (ex.: estresse calórico)", "valor": 4, "unidade": "meses"},
    {"chave": "concepcao_meses_queda", "grupo": "producao_descarte", "label": "Taxa de concepção nos meses de queda", "valor": 25, "unidade": "%"},

    # ---- Estoque de sêmen — mínimo agregado por TIPO (convencional/sexado),
    # não por touro individual. Editável em Configurações > Cadastro >
    # Central de Sêmen > Estoque mínimo. Consumido por `semen_disponivel`
    # (cadastro.py) e pelo alerta de sêmen abaixo do mínimo na Agenda.
    {"chave": "estoque_minimo_semen_convencional", "grupo": "estoque_semen", "label": "Estoque mínimo — sêmen convencional", "valor": 20, "unidade": "doses"},
    {"chave": "estoque_minimo_semen_sexado", "grupo": "estoque_semen", "label": "Estoque mínimo — sêmen sexado", "valor": 5, "unidade": "doses"},

    # ---- Folha de pagamento / RH — Férias e 13º salário (cálculo interno,
    # sem envio ao eSocial) ----------------------------------------------------
    {"chave": "percentual_terco_constitucional_ferias", "grupo": "folha_rh", "label": "1/3 constitucional de férias", "valor": 0.3333, "tipo": "float", "unidade": "fração"},
    {"chave": "dias_ferias_padrao", "grupo": "folha_rh", "label": "Dias de férias padrão", "valor": 30, "unidade": "dias"},
    # Estimativa de depósito mensal de FGTS (8% do salário) — usada só para
    # estimar a multa rescisória de 40%/20% quando não há extrato real do
    # FGTS cadastrado (ver `fazenda.rules.folha_rh.calcular_rescisao`).
    {"chave": "percentual_estimado_fgts_mensal", "grupo": "folha_rh", "label": "Estimativa de depósito mensal de FGTS", "valor": 0.08, "tipo": "float", "unidade": "fração"},

    # ---- Estrutura da fazenda — usado pelo indicador "Custo por hectare"
    # (Financeiro > Relatórios), que divide as despesas do período por este
    # valor. Sem cadastro de área em nenhum outro lugar do sistema hoje
    # (nem em Lote, nem em models já existentes), então entra aqui como um
    # parâmetro simples, editável em Configurações > Parâmetros.
    {"chave": "area_total_hectares", "grupo": "estrutura_fazenda", "label": "Área total da fazenda", "valor": 0, "tipo": "float", "unidade": "ha"},
]


def seed_parametros(session: Session) -> None:
    """Popula o banco com as definições acima — só cria o que ainda não
    existe (nunca sobrescreve um valor já editado). Idempotente, chamado no
    startup como os demais `seed_*`."""
    from fazenda.models import ParametroFazenda

    existentes = {p.chave for p in session.exec(select(ParametroFazenda)).all()}
    for item in DEFINICOES:
        if item["chave"] in existentes:
            continue
        session.add(ParametroFazenda(
            chave=item["chave"],
            grupo=item["grupo"],
            label=item["label"],
            valor=str(item["valor"]),
            tipo=item.get("tipo", "int"),
            unidade=item.get("unidade"),
        ))
    session.commit()


import contextvars

# Fazenda do request em curso, para `get_param` saber de quem é o parâmetro
# sem precisar receber fazenda_id em TODA função de regra (get_param é chamada
# de dezenas de funções puras, sem contexto de request). O middleware em
# main.py carimba isso no início de cada request; fora de request (testes de
# regra puros, loops de fundo) fica None e vale o padrão global.
fazenda_atual: contextvars.ContextVar[int | None] = contextvars.ContextVar("fazenda_atual", default=None)


def _linha(chave: str):
    """Busca a linha do parâmetro no banco, preferindo a personalização da
    fazenda atual e caindo no padrão global (fazenda_id NULL) quando ela não
    personalizou aquele parâmetro. Cai em None (o chamador usa o `padrao`) se
    a tabela ainda não existir — ex.: testes de regra "puros" que chamam
    `avaliar_bst`/`dias_gestacao`/`calcular_indicadores` direto, sem passar
    pelo startup da API (`create_db_and_tables`/`seed_parametros`) — mantém
    essas funções utilizáveis sem depender de banco."""
    from sqlalchemy.exc import OperationalError, ProgrammingError

    from fazenda.database import engine
    from fazenda.models import ParametroFazenda
    fid = fazenda_atual.get()
    try:
        with Session(engine) as session:
            if fid is not None:
                especifica = session.exec(
                    select(ParametroFazenda).where(
                        ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == fid,
                    )
                ).first()
                if especifica is not None:
                    return especifica
            # Padrão global: o seed continua criando as linhas com
            # fazenda_id NULL, então uma fazenda que nunca personalizou nada
            # enxerga exatamente os mesmos valores de antes.
            return session.exec(
                select(ParametroFazenda).where(
                    ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == None,  # noqa: E711
                )
            ).first()
    except (OperationalError, ProgrammingError):
        return None


def get_param(chave: str, padrao: float | int | None = None) -> float | int | None:
    """Retorna o valor numérico (int/float) de um parâmetro por chave (ex.:
    'pev_dias', 'meta_del_max_1o_servico', 'periodo_seco_dias'). Usado pelos
    relatórios gerenciais e pelas regras de negócio para semaforizar
    (verde/amarelo/vermelho) e calcular datas com base nas metas/parâmetros."""
    row = _linha(chave)
    if row is None:
        return padrao
    try:
        if row.tipo == "float":
            return float(row.valor)
        return int(float(row.valor))
    except (TypeError, ValueError):
        return padrao


def get_param_bool(chave: str, padrao: bool = False) -> bool:
    """Retorna o valor booleano de um parâmetro (ex.: 'usa_adesivo_deteccao_cio')."""
    row = _linha(chave)
    if row is None:
        return padrao
    return (row.valor or "").strip().lower() in ("1", "true", "sim", "yes")


def get_param_date(chave: str, padrao: date | None = None) -> date | None:
    """Retorna o valor de data de um parâmetro (ex.: 'data_corte_taxa_concepcao')."""
    row = _linha(chave)
    if row is None or not row.valor:
        return padrao
    try:
        return date.fromisoformat(row.valor)
    except ValueError:
        return padrao


def get_param_texto(chave: str, padrao: str = "") -> str:
    """Retorna o valor de texto livre de um parâmetro (ex.:
    'assistente_usuarios_liberados') — get_param() não serve aqui porque só
    sabe converter para int/float."""
    row = _linha(chave)
    if row is None or row.valor is None:
        return padrao
    return row.valor


# ---------------------------------------------------------------------------
# Acessores nomeados — usados pelas regras espalhadas (agenda_veterinario,
# lote_criterios, relatorios_gerenciais, gestation, indicadores, bst,
# scratch_pev, dry_off, eventos_sanitarios, agenda_engine) no lugar dos
# antigos módulo-constantes fixos, para que a edição em Configurações >
# Parâmetros passe a valer de fato em todo lugar (ver tarefa #363).
# ---------------------------------------------------------------------------
def peso_apta_min() -> float:
    return float(get_param("peso_apta_min", 300) or 300)


def peso_verificar_aptidao_min() -> float:
    return float(get_param("peso_verificar_aptidao_min", 280) or 280)


def idade_apta_min_meses() -> float:
    return float(get_param("idade_apta_min_meses", 15) or 15)


def idade_verificar_aptidao_meses() -> float:
    return float(get_param("idade_verificar_aptidao_meses", 14) or 14)


def gestacao_dias_min() -> int:
    return int(get_param("gestacao_dias_min", 280) or 280)


def gestacao_dias_max() -> int:
    return int(get_param("gestacao_dias_max", 295) or 295)


def gestacao_dias_referencia() -> int:
    """Ponto médio (arredondado) da faixa de gestação — usado onde é preciso
    um único valor escalar para estimar a data provável de parto (não uma
    faixa min/max). Consolida os antigos valores fragmentados (283 em
    lote_criterios, 280 em relatorios_gerenciais/indicadores, dict por raça
    em gestation.py)."""
    return round((gestacao_dias_min() + gestacao_dias_max()) / 2)


def pre_parto_min() -> int:
    return int(get_param("pre_parto_min", 31) or 31)


def pre_parto_max() -> int:
    return int(get_param("pre_parto_max", 60) or 60)


def pev_dias() -> int:
    return int(get_param("pev_dias", 45) or 45)


def periodo_seco_dias() -> int:
    return int(get_param("periodo_seco_dias", 60) or 60)


def intervalo_bst() -> int:
    return int(get_param("intervalo_bst", 12) or 12)


def intervalo_visita_reprodutiva() -> int:
    return int(get_param("intervalo_visita_reprodutiva", 21) or 21)


def dias_reinseminacao_min() -> int:
    return int(get_param("dias_reinseminacao_min", 18) or 18)


def dias_reinseminacao_max() -> int:
    return int(get_param("dias_reinseminacao_max", 25) or 25)


def dias_reinseminacao_referencia() -> int:
    """Ponto médio (arredondado) da faixa de dias para reinseminação — usado
    onde é preciso uma única data-alvo (ex.: item "Retoque" da Agenda), não
    uma faixa min/max."""
    return round((dias_reinseminacao_min() + dias_reinseminacao_max()) / 2)


def usa_adesivo_deteccao_cio() -> bool:
    return get_param_bool("usa_adesivo_deteccao_cio", False)


def dias_adesivo_cio_min() -> int:
    return int(get_param("dias_adesivo_cio_min", 15) or 15)


def dias_adesivo_cio_max() -> int:
    return int(get_param("dias_adesivo_cio_max", 28) or 28)


def del_minimo_bst() -> int:
    return int(get_param("del_minimo_bst", 60) or 60)


def dias_antes_secagem_bst() -> int:
    return int(get_param("dias_antes_secagem_bst", 15) or 15)


def bst_ajuste_ancora_data() -> date | None:
    return get_param_date("bst_ajuste_ancora_data", None)


def janela_eventos_sanitarios_passado() -> int:
    return int(get_param("janela_eventos_sanitarios_passado", 120) or 120)


def janela_eventos_sanitarios_futuro() -> int:
    return int(get_param("janela_eventos_sanitarios_futuro", 180) or 180)


def dias_contas_a_pagar_agenda() -> int:
    return int(get_param("dias_contas_a_pagar_agenda", 10) or 10)


def data_corte_taxa_concepcao() -> date:
    from datetime import date as _date
    return get_param_date("data_corte_taxa_concepcao", _date(2026, 1, 1)) or _date(2026, 1, 1)


def estoque_minimo_semen_convencional() -> int:
    return int(get_param("estoque_minimo_semen_convencional", 20) or 20)


def estoque_minimo_semen_sexado() -> int:
    return int(get_param("estoque_minimo_semen_sexado", 5) or 5)


def percentual_terco_constitucional_ferias() -> float:
    """1/3 constitucional aplicado sobre o valor das férias gozadas (padrão
    0.3333) — usado por `fazenda.rules.folha_rh.calcular_ferias`."""
    return float(get_param("percentual_terco_constitucional_ferias", 0.3333) or 0.3333)


def dias_ferias_padrao() -> int:
    """Dias de férias padrão (direito integral por período aquisitivo) —
    sugestão inicial no lançamento de férias, sempre editável."""
    return int(get_param("dias_ferias_padrao", 30) or 30)


def percentual_estimado_fgts_mensal() -> float:
    """Estimativa de depósito mensal de FGTS (padrão 8% do salário) — usada
    só por `fazenda.rules.folha_rh.calcular_rescisao` para estimar a multa
    rescisória, já que o sistema não guarda o extrato real do FGTS."""
    return float(get_param("percentual_estimado_fgts_mensal", 0.08) or 0.08)


def area_total_hectares() -> float:
    """Área total da fazenda em hectares (Configurações > Parâmetros >
    Estrutura da fazenda). Denominador do indicador "Custo por hectare"
    (`fazenda.rules.custo_hectare`); 0 até o usuário cadastrar."""
    return float(get_param("area_total_hectares", 0) or 0)


def minimos_semen_por_tipo() -> dict[str, int]:
    """Único ponto de leitura do estoque mínimo de sêmen, agregado por tipo —
    usado em `cadastro.semen_disponivel` e no alerta de sêmen abaixo do
    mínimo na Agenda (antes, cada um tinha sua própria constante hardcoded
    e desincronizada, `MINIMO_SEMEN`)."""
    return {"convencional": estoque_minimo_semen_convencional(), "sexado": estoque_minimo_semen_sexado()}


# Metas do benchmark (nosso valor será comparado a estes) — usadas na capa.
# meta = alvo da fazenda; media_pais = referência de mercado. Ainda não
# exposto na UI de Parâmetros (candidato a exposição futura — ver CSV
# entregue ao usuário em 2026-07-16).
BENCHMARK_METAS: dict[str, dict] = {
    "taxa_servico":        {"meta": 50.0, "media_pais": 55.0, "maior_melhor": True},
    "taxa_concepcao":      {"meta": 35.0, "media_pais": 40.0, "maior_melhor": True},
    "taxa_prenhez_ciclo":  {"meta": 18.0, "media_pais": 21.0, "maior_melhor": True},
    "del_medio":           {"meta": 200.0, "media_pais": 209.0, "maior_melhor": False},
    "taxa_perda_prenhez":  {"meta": 15.0, "media_pais": 11.0, "maior_melhor": False},
    "perc_vacas_prenhas":  {"meta": 50.0, "media_pais": 46.0, "maior_melhor": True},
    "servicos_por_prenhez": {"meta": 2.9, "media_pais": 2.5, "maior_melhor": False},
    "del_1a_ia":           {"meta": 70.0, "media_pais": 78.0, "maior_melhor": False},
    "dias_abertos":        {"meta": 145.6, "media_pais": 164.0, "maior_melhor": False},
    "iep_meses":           {"meta": 14.0, "media_pais": 14.0, "maior_melhor": False},
}
