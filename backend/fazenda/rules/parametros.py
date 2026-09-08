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
    "financeiro": "Financeiro",
    "alimentacao": "Alimentação",
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

    # ---- Aptidão de novilhas (gate de entrada em listas de análise/
    # relatório/vacinação/protocolos de novilhas aptas) ----------------------
    {"chave": "peso_apta_min", "grupo": "aptidao_novilha", "label": "Peso mínimo de aptidão", "valor": 300, "unidade": "kg"},
    {"chave": "idade_apta_min_meses", "grupo": "aptidao_novilha", "label": "Idade mínima de aptidão", "valor": 15, "unidade": "meses"},
    # Teto: passada esta idade, a novilha VAZIA deixa de ser "apta" e passa a
    # "em atraso" — o análogo de `meta_del_max_1o_servico` para quem nunca
    # pariu. O padrão de 16 meses reproduz a classificação do Ideagri: no
    # GERAL.csv desta fazenda as 11 "Novilha vazia em atraso" começam em
    # exatamente 16,0 meses, e NÃO existe uma única "Novilha vazia apta" —
    # ou seja, lá o teto coincide com o piso de aptidão.
    {"chave": "idade_max_1a_cobertura_meses", "grupo": "aptidao_novilha", "label": "Idade máxima para a 1ª cobertura (novilha em atraso)", "valor": 16, "unidade": "meses"},

    # ---- Gestação e parto ---------------------------------------------------
    {"chave": "gestacao_dias_min", "grupo": "gestacao_parto", "label": "Gestação — dias mínimo", "valor": 280, "unidade": "dias"},
    {"chave": "gestacao_dias_max", "grupo": "gestacao_parto", "label": "Gestação — dias máximo", "valor": 295, "unidade": "dias"},
    # Pré-parto: últimos pre_parto_max dias antes do parto (padrão 30, até o
    # parto). Vem DEPOIS do período seco/Secagem (periodo_seco_dias, acima —
    # 60 dias antes do parto até o início do pré-parto) — não confundir as
    # duas janelas (ver fazenda.rules.dry_off e agenda_engine.py).
    {"chave": "pre_parto_min", "grupo": "gestacao_parto", "label": "Janela de pré-parto — dias mínimo", "valor": 0, "unidade": "dias"},
    {"chave": "pre_parto_max", "grupo": "gestacao_parto", "label": "Janela de pré-parto — dias máximo", "valor": 30, "unidade": "dias"},

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
    {"chave": "cronograma_sanitario_dias_aviso", "grupo": "agenda_sistema", "label": "Cronograma sanitário — aviso obrigatório antes do evento sem veterinário definido", "valor": 5, "unidade": "dias"},
    {"chave": "cronograma_sanitario_min_animais_agrupamento", "grupo": "agenda_sistema", "label": "Calendário sanitário — mínimo de animais para sugerir chamada do veterinário", "valor": 15, "unidade": "animais"},
    {"chave": "cronograma_sanitario_janela_agrupamento_dias", "grupo": "agenda_sistema", "label": "Calendário sanitário — janela de agrupamento entre eventos próximos", "valor": 7, "unidade": "dias"},
    {"chave": "dias_contas_a_pagar_agenda", "grupo": "agenda_sistema", "label": "Contas a pagar na agenda — próximos dias", "valor": 10, "unidade": "dias"},
    # Secagem/Parto sugerem mover o animal para o lote de secas/lote 03 — por
    # padrão, sempre PERGUNTA (janela de confirmação, ver FormSecagem.tsx/
    # FormParto.tsx); marcando este parâmetro, a movimentação acontece sozinha,
    # sem perguntar.
    {"chave": "transferencia_lote_automatica", "grupo": "agenda_sistema", "label": "Secagem/Parto — transferir para o lote sugerido automaticamente (sem perguntar)?", "valor": "false", "tipo": "bool"},
    {"chave": "patrimonio_atualizacao_valor_mercado_meses", "grupo": "agenda_sistema", "label": "Patrimônio não depreciável — frequência padrão de atualização do valor de mercado (0 = nunca)", "valor": 12, "unidade": "meses"},
    {"chave": "data_corte_taxa_concepcao", "grupo": "agenda_sistema", "label": "Data de corte para taxa de concepção", "valor": "2026-01-01", "tipo": "date"},

    # ---- Caixa Real (Onda 4) ---------------------------------------------------
    # Fundo de reserva: quanto a fazenda quer manter em caixa como colchão.
    # 0 = sem fundo definido (a tela então só alerta sobre saldo negativo, e
    # oferece a sugestão calculada pelo histórico — ver
    # rules.caixa_real.sugerir_fundo_reserva).
    {"chave": "caixa_fundo_reserva", "grupo": "agenda_sistema", "label": "Caixa Real — fundo de reserva (colchão mínimo desejado em caixa; 0 = não definido)", "valor": 0, "tipo": "float", "unidade": "R$"},
    {"chave": "caixa_meses_folga_sugestao", "grupo": "agenda_sistema", "label": "Caixa Real — meses de custo que o fundo de reserva sugerido deve cobrir", "valor": 3, "tipo": "float", "unidade": "meses"},
    {"chave": "caixa_dias_projecao", "grupo": "agenda_sistema", "label": "Caixa Real — horizonte padrão da projeção de caixa", "valor": 90, "unidade": "dias"},

    # ---- Metas reprodutivas ----------------------------------------------------
    {"chave": "meta_del_max_1o_servico", "grupo": "metas_reproducao", "label": "DEL máximo para 1º serviço", "valor": 100, "unidade": "dias"},
    # Análogo do parâmetro acima, para quem nunca pariu: em vez de contar a
    # partir de um teto fixo de IDADE desde o nascimento (idade_max_1a_
    # cobertura_meses, que penaliza no mesmo dia a novilha que amadurece
    # devagar), conta a partir do dia em que ELA ficou apta (idade E peso —
    # ver estado_reprodutivo.data_em_que_ficou_apta). As duas regras valem
    # em paralelo: o que vier primeiro marca ATRASADA (decisão do usuário —
    # manter o teto de idade como rede de segurança).
    {"chave": "dias_atraso_apos_aptidao_novilha", "grupo": "metas_reproducao", "label": "Dias após aptidão (novilha)", "valor": 30, "unidade": "dias"},
    {"chave": "meta_del_medio_1o_servico", "grupo": "metas_reproducao", "label": "DEL médio ao 1º serviço", "valor": 70, "unidade": "dias"},
    {"chave": "meta_del_medio", "grupo": "metas_reproducao", "label": "DEL médio do rebanho", "valor": 200, "unidade": "dias"},
    {"chave": "meta_taxa_servico", "grupo": "metas_reproducao", "label": "Taxa de serviço em vacas", "valor": 50, "unidade": "%"},
    {"chave": "meta_taxa_concepcao", "grupo": "metas_reproducao", "label": "Taxa de concepção em vacas", "valor": 35, "unidade": "%"},
    {"chave": "meta_taxa_prenhez", "grupo": "metas_reproducao", "label": "Taxa de prenhez em vacas", "valor": 18, "unidade": "%"},
    {"chave": "meta_concepcao_novilha", "grupo": "metas_reproducao", "label": "Taxa de concepção da novilha", "valor": 60, "unidade": "%"},
    {"chave": "meta_iep_meses", "grupo": "metas_reproducao", "label": "Intervalo entre partos (IEP)", "valor": 14, "unidade": "meses"},
    {"chave": "meta_taxa_perda_prenhez", "grupo": "metas_reproducao", "label": "Taxa de perda de prenhez", "valor": 15, "unidade": "%"},
    # Regra dos 28 dias (ver fazenda.rules.programa_reprodutivo, R7): uma
    # inseminação dos últimos 27 dias ainda não deu tempo de virar prenhez
    # confirmada. Deixá-la no denominador da concepção faz a taxa despencar
    # artificialmente nos dias recentes. Só entra antes disso quando o desfecho
    # já é conhecido (DG negativo, perda, ou nova IA em cio de repasse).
    {"chave": "dias_resultado_conhecido", "grupo": "metas_reproducao", "label": "Dias até o resultado da inseminação ser considerado conhecido", "valor": 28, "unidade": "dias"},
    # Regra dos 11 de 21 (R5): o animal não precisa estar apto o ciclo inteiro
    # para entrar no denominador — precisa ter participado de pelo menos
    # metade dele. Mesmo critério do BREDSUM\E do DairyComp.
    {"chave": "dias_minimos_no_ciclo", "grupo": "metas_reproducao", "label": "Dias mínimos de participação no ciclo de 21 dias", "valor": 11, "unidade": "dias"},

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

    # ---- Folha de pagamento / RH — média das verbas variáveis habituais ----
    # LIGA a integração das parcelas SALARIAIS VARIÁVEIS (bonificação por
    # produtividade, gueltas, vale-alimentação de natureza salarial e o que
    # mais o catálogo enquadrar como salarial) nas bases de 13º, férias e
    # rescisão — CLT, art. 457, §1º, e Súmula 45 do TST; as janelas de cada
    # verba estão em `rules/media_verbas_habituais.py`.
    #
    # PADRÃO FALSO, e o padrão é o requisito, textual, do dono: "tem que ser
    # de modo que possa ser configurável, para usar ou não, pois a fazenda
    # pode não querer controlar os detalhes e deixar só com a contabilidade
    # externa". Desligado, o 13º, as férias e a rescisão saem exatamente como
    # sempre saíram (só sobre o salário-base) — nenhuma fazenda existente muda
    # de comportamento sem alguém escolher. Ligado, a média entra a partir do
    # PRÓXIMO lançamento: nada já pago ou fechado é recalculado.
    {"chave": "calcula_media_verbas_variaveis", "grupo": "folha_rh",
     "label": "O sistema calcula as médias de verbas variáveis no 13º, férias e rescisão",
     "valor": "false", "tipo": "bool"},

    # ---- Folha de pagamento / RH — vale-alimentação -------------------------
    # O PAT é fato da FAZENDA, não do funcionário, e por isso mora aqui e não
    # em `Pessoa`. Ele muda a NATUREZA da verba em duas das quatro linhas da
    # árvore (refeição servida in natura: salário-utilidade fora do PAT, art.
    # 458, caput, da CLT; indenizatória dentro dele, OJ 133 da SDI-1 do TST) —
    # e é ele também que abre a dedução de IRPJ do programa. Padrão FALSO: a
    # maioria das fazendas rurais não é inscrita, e inscrever ninguém por
    # omissão é o lado que não subdeclara base. Ver
    # `rules/vale_alimentacao.py::natureza_do_vale_alimentacao`.
    {"chave": "inscrita_no_pat", "grupo": "folha_rh",
     "label": "Fazenda inscrita no PAT (Programa de Alimentação do Trabalhador)",
     "valor": "false", "tipo": "bool"},
    # Contagem de dias do vale-alimentação DIÁRIO. Não há norma legal que fixe
    # uma: quem manda é a convenção coletiva rural da base, depois o contrato,
    # depois a política da fazenda. Padrão `trabalhados` porque o auxílio
    # custeia a refeição DURANTE a jornada. Fica como texto pelo mesmo motivo
    # de `modo_lancamento_alimentacao`: a tela de Parâmetros só renderiza int,
    # bool, date, float e texto — os valores aceitos vão no rótulo, e a
    # validação mora em `vale_alimentacao.base_dias_valida`.
    {"chave": "vale_alimentacao_base_dias", "grupo": "folha_rh",
     "label": "Vale-alimentação diário — contagem de dias (corridos | uteis | trabalhados)",
     "valor": "trabalhados", "tipo": "texto"},
    # Falta INJUSTIFICADA autoriza suprimir o dia do benefício (não houve
    # jornada, não houve refeição a custear) e isso é fixo. Falta JUSTIFICADA,
    # férias, afastamento pelo INSS e feriado normalmente NÃO autorizam — mas a
    # CCT decide, e por isso este é o interruptor. Padrão FALSO: não descontar
    # é o que a maioria das convenções prevê, e o padrão que não tira dinheiro
    # de ninguém sem alguém ter pedido.
    {"chave": "vale_alimentacao_falta_justificada_desconta", "grupo": "folha_rh",
     "label": "Vale-alimentação — falta justificada desconta o dia", "valor": "false", "tipo": "bool"},
    # No mês de ADMISSÃO o padrão é proporcional (conta a partir do dia da
    # admissão), porque o benefício custeia a refeição dos dias em que houve
    # vínculo. Algumas CCTs mandam pagar o mês cheio — é o que este
    # interruptor liga. Não existe equivalente para o mês de RESCISÃO: nenhuma
    # norma manda pagar refeição depois do desligamento.
    {"chave": "vale_alimentacao_mes_admissao_integral", "grupo": "folha_rh",
     "label": "Vale-alimentação — mês de admissão integral (não proporcional)",
     "valor": "false", "tipo": "bool"},

    # ---- Estrutura da fazenda — usado pelo indicador "Custo por hectare"
    # (Financeiro > Relatórios), que divide as despesas do período por este
    # valor. Sem cadastro de área em nenhum outro lugar do sistema hoje
    # (nem em Lote, nem em models já existentes), então entra aqui como um
    # parâmetro simples, editável em Configurações > Parâmetros.
    {"chave": "area_total_hectares", "grupo": "estrutura_fazenda", "label": "Área total da fazenda", "valor": 0, "tipo": "float", "unidade": "ha"},

    # ---- Financeiro — RMCA (Receita Menos Custo com Alimentação, Financeiro
    # > RMCA). Padrão 0 (ponto de equilíbrio) preserva o comportamento atual
    # (verde se RMCA >= 0) até o usuário definir uma meta de margem própria.
    {"chave": "meta_rmca", "grupo": "financeiro", "label": "RMCA mínimo aceitável", "valor": 0, "tipo": "float", "unidade": "R$"},
    # Nome (ou trecho do nome) do comprador do leite usado para reconhecer a
    # receita de leite em "Fornecedor/Cliente" — antes era "italac" fixo no
    # código (rules/producao.py), então qualquer fazenda com outro laticínio
    # nunca tinha a receita reconhecida no RMCA/custo por litro.
    {"chave": "laticinio_nome", "grupo": "financeiro", "label": "Nome do laticínio (reconhece a receita de leite no RMCA)", "valor": "italac", "tipo": "texto"},
    # ---- Alimentação: sobra de cocho ---------------------------------------
    # A sobra é o termômetro do trato. Sobra de menos significa cocho vazio
    # antes da hora — vaca que comeu menos do que a dieta previa, e produção
    # perdida sem ninguém ver. Sobra de mais é comida virando esterco e custo.
    # Por isso a faixa, e não um alvo único: perseguir 5% exatos todo dia faria
    # o sistema reclamar todo dia.
    {"chave": "sobra_alvo_pct", "grupo": "alimentacao", "label": "Sobra de cocho — alvo", "valor": 5, "unidade": "%"},
    {"chave": "sobra_min_pct", "grupo": "alimentacao", "label": "Sobra de cocho — mínimo aceitável", "valor": 3, "unidade": "%"},
    {"chave": "sobra_max_pct", "grupo": "alimentacao", "label": "Sobra de cocho — máximo aceitável", "valor": 7, "unidade": "%"},
    # Três modos, porque nem toda fazenda pesa sobra: quem pesa lança fornecido
    # e sobra; quem não pesa deixa o sistema baixar o estoque pela dieta; e quem
    # controla alimentação por fora desliga tudo.
    # Fica como texto porque a tela de Parâmetros só sabe renderizar int, bool,
    # date, float e texto — não há tipo de seleção (ver o router de parâmetros).
    # Os valores aceitos vão no rótulo, para quem edita não ter de adivinhar, e
    # a validação é feita no endpoint que consome o parâmetro. Um campo de
    # seleção de verdade é melhoria posterior, e mexe na tela de Parâmetros.
    {"chave": "modo_lancamento_alimentacao", "grupo": "alimentacao",
     "label": "Como lançar a alimentação (fornecido_sobra | baixa_automatica | nao_lancar)",
     "valor": "fornecido_sobra", "tipo": "texto"},

]


def seed_parametros(session: Session) -> None:
    """Popula o banco com as definições acima — só cria o que ainda não
    existe (nunca sobrescreve um valor já editado). Idempotente, chamado no
    startup como os demais `seed_*`."""
    from fazenda.models import ParametroFazenda

    # `idade_maturidade_novilha` era um parâmetro editável na tela de
    # Parâmetros que NENHUM código lia — a única ocorrência no backend era a
    # própria linha de seed. Apagar é seguro justamente por isso: como nada o
    # consultava, nenhum comportamento muda, e quem por acaso o editou nunca
    # teve efeito algum. O conceito que ele parecia prometer agora existe de
    # verdade em `idade_max_1a_cobertura_meses`.
    for orfao in session.exec(
        select(ParametroFazenda).where(ParametroFazenda.chave == "idade_maturidade_novilha")
    ).all():
        session.delete(orfao)

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
    """Retorna o valor de texto livre de um parâmetro — get_param() não serve
    aqui porque só sabe converter para int/float."""
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


def idade_apta_min_meses() -> float:
    return float(get_param("idade_apta_min_meses", 15) or 15)


def idade_max_1a_cobertura_meses() -> float:
    return float(get_param("idade_max_1a_cobertura_meses", 16) or 16)


def dias_atraso_apos_aptidao_novilha() -> int:
    return int(get_param("dias_atraso_apos_aptidao_novilha", 30) or 30)


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
    return int(get_param("pre_parto_min", 0) or 0)


def pre_parto_max() -> int:
    return int(get_param("pre_parto_max", 30) or 30)


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


def cronograma_sanitario_dias_aviso() -> int:
    return int(get_param("cronograma_sanitario_dias_aviso", 5) or 5)


def cronograma_sanitario_min_animais_agrupamento() -> int:
    return int(get_param("cronograma_sanitario_min_animais_agrupamento", 15) or 15)


def cronograma_sanitario_janela_agrupamento_dias() -> int:
    return int(get_param("cronograma_sanitario_janela_agrupamento_dias", 7) or 7)


def patrimonio_atualizacao_valor_mercado_meses() -> int:
    """Frequência padrão (em meses) de "atualizar valor de mercado" pra
    patrimônio não depreciável (ex.: terra) sem override próprio — ver
    Patrimonio.atualizacao_valor_mercado_frequencia_meses. 0 = nunca.

    NÃO use `get_param(...) or 12` aqui — 0 é um valor válido e "or" o
    trocaria por 12, tornando "0 = nunca" (o próprio label do parâmetro na
    tela) impossível de configurar."""
    valor = get_param("patrimonio_atualizacao_valor_mercado_meses", 12)
    return int(valor) if valor is not None else 12


def caixa_fundo_reserva() -> float:
    """Colchão mínimo desejado em caixa (Onda 4). 0 = não definido — a tela
    então alerta só sobre saldo negativo e oferece a sugestão calculada.

    Como em patrimonio_atualizacao_valor_mercado_meses, NÃO usar `or`: 0 é
    um valor legítimo ("ainda não defini meu fundo"), e `or` o trocaria pelo
    padrão, tornando impossível voltar ao estado não definido."""
    valor = get_param("caixa_fundo_reserva", 0)
    return float(valor) if valor is not None else 0.0


def caixa_meses_folga_sugestao() -> float:
    valor = get_param("caixa_meses_folga_sugestao", 3)
    return float(valor) if valor is not None else 3.0


def caixa_dias_projecao() -> int:
    return int(get_param("caixa_dias_projecao", 90) or 90)


def dias_contas_a_pagar_agenda() -> int:
    return int(get_param("dias_contas_a_pagar_agenda", 10) or 10)


def transferencia_lote_automatica() -> bool:
    """Secagem/Parto: mover para o lote sugerido sem perguntar (True) ou
    sempre abrir a janela de confirmação (False, padrão) — ver
    FormSecagem.tsx/FormParto.tsx."""
    return get_param_bool("transferencia_lote_automatica", False)


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


def calcula_media_verbas_variaveis() -> bool:
    """A fazenda quer que o sistema apure a média das parcelas salariais
    VARIÁVEIS habituais (bonificação, gueltas, vale-alimentação salarial…) e a
    some às bases de 13º, férias e rescisão? Padrão FALSO — desligado, as três
    contas saem só sobre o salário-base, exatamente como antes desta feature.

    Ver `rules/media_verbas_habituais.py` para as janelas de cada verba (ano
    civil no 13º, período aquisitivo nas férias, últimos 12 meses no aviso
    prévio indenizado) e para o fundamento de cada uma."""
    return get_param_bool("calcula_media_verbas_variaveis", False)


def fazenda_inscrita_no_pat() -> bool:
    """A fazenda é inscrita no PAT? Fato da FAZENDA (não do funcionário) que
    decide duas das quatro linhas da árvore de natureza do vale-alimentação —
    ver `rules/vale_alimentacao.py::natureza_do_vale_alimentacao`."""
    return get_param_bool("inscrita_no_pat", False)


def vale_alimentacao_base_dias() -> str:
    """"corridos" | "uteis" | "trabalhados" — a contagem do VA diário. Quem
    normaliza valor desconhecido é `vale_alimentacao.base_dias_valida`, que é
    também quem conhece o padrão: um segundo padrão escrito aqui é como os
    dois passam a discordar."""
    return get_param_texto("vale_alimentacao_base_dias", "trabalhados")


def vale_alimentacao_falta_justificada_desconta() -> bool:
    """A CCT da base manda suprimir o dia de benefício na falta JUSTIFICADA?
    Padrão False — a injustificada desconta sempre, e não é configurável."""
    return get_param_bool("vale_alimentacao_falta_justificada_desconta", False)


def vale_alimentacao_mes_admissao_integral() -> bool:
    """No mês de admissão, paga-se o benefício cheio em vez de proporcional?
    Padrão False (proporcional)."""
    return get_param_bool("vale_alimentacao_mes_admissao_integral", False)


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


def meta_rmca() -> float:
    """Valor mínimo aceitável de RMCA (Receita Menos Custo com Alimentação)
    no período (Configurações > Parâmetros > Financeiro) — usado para
    colorir o indicador em Financeiro > RMCA (site e app). Padrão 0 (ponto
    de equilíbrio), preservando o comportamento anterior (RMCA >= 0 = verde)
    até o usuário definir uma meta de margem própria."""
    return float(get_param("meta_rmca", 0) or 0)


def minimos_semen_por_tipo() -> dict[str, int]:
    """Único ponto de leitura do estoque mínimo de sêmen, agregado por tipo —
    usado em `cadastro.semen_disponivel` e no alerta de sêmen abaixo do
    mínimo na Agenda (antes, cada um tinha sua própria constante hardcoded
    e desincronizada, `MINIMO_SEMEN`)."""
    return {"convencional": estoque_minimo_semen_convencional(), "sexado": estoque_minimo_semen_sexado()}


def meta_taxa_servico() -> float:
    """Meta de taxa de serviço do rebanho (Configurações > Parâmetros >
    Metas reprodutivas) — usada em `relatorios_gerenciais.taxa_servico_prenhez`
    e no benchmark reprodutivo da Capa (`indicadores._metas_benchmark`)."""
    return float(get_param("meta_taxa_servico", 50) or 50)


def meta_taxa_prenhez() -> float:
    """Meta de taxa de prenhez do rebanho — usada no benchmark reprodutivo da
    Capa (`indicadores._metas_benchmark`, chave "taxa_prenhez_ciclo")."""
    return float(get_param("meta_taxa_prenhez", 18) or 18)


def meta_taxa_concepcao() -> float:
    """Meta de taxa de concepção em vacas — usada no benchmark reprodutivo da
    Capa (`indicadores._metas_benchmark`, categorias "todas"/"vaca")."""
    return float(get_param("meta_taxa_concepcao", 35) or 35)


def dias_resultado_conhecido() -> int:
    """Janela após a qual o desfecho de uma inseminação é dado como conhecido
    (padrão 28 dias) — ver `fazenda.rules.programa_reprodutivo`, regra R7.
    Serviço mais recente que isso só entra numa taxa se já tiver DG, perda ou
    reinseminação em cio de repasse."""
    return int(get_param("dias_resultado_conhecido", 28) or 28)


def dias_minimos_no_ciclo() -> int:
    """Dias mínimos de participação num ciclo de 21 dias para o animal entrar
    no denominador (padrão 11) — regra R5, mesmo critério do BREDSUM\\E."""
    return int(get_param("dias_minimos_no_ciclo", 11) or 11)


def meta_concepcao_novilha() -> float:
    """Meta de taxa de concepção em novilhas — usada no benchmark reprodutivo
    da Capa (`indicadores._metas_benchmark`, categoria "novilha"), separada
    da meta de vacas acima (`meta_taxa_concepcao`)."""
    return float(get_param("meta_concepcao_novilha", 60) or 60)


# Metas do benchmark (nosso valor será comparado a estes) — usadas na capa.
# meta = alvo da fazenda; media_pais = referência de mercado. As 3 primeiras
# chaves (taxa_servico/taxa_concepcao/taxa_prenhez_ciclo) têm parâmetro
# editável próprio (accessors acima) — o "meta" delas aqui só serve de
# fallback (nunca lido diretamente, ver `indicadores._metas_benchmark`). As
# demais ainda não têm parâmetro equivalente, continuam fixas (candidato a
# exposição futura — ver CSV entregue ao usuário em 2026-07-16).
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
