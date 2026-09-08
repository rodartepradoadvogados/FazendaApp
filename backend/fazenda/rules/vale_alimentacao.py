"""
Vale-alimentação — a verba que a folha GERA a partir do cadastro da pessoa.

O PEDIDO DO DONO, literal: "não precisa de uma rubrica para vale alimentação,
só precisa de ter como cadastrar se vai ter ou não e o valor-base, se diário
ou mensal, se pago antecipado ou vencido, para fins de competência, e o valor.
O resto é padrão."

Ou seja: NÃO é uma rubrica avulsa que alguém lança mês a mês (esse era o
desenho recusado, e a recusa continua valendo para o lançamento manual — ver
`rubrica_folha.CATALOGO_VENCIMENTOS["vale_alimentacao"]`). É uma CONDIÇÃO DO
VÍNCULO, gravada em quatro campos de `Pessoa`, que a folha lê e transforma
numa linha do holerite sozinha, todo mês, sem ninguém digitar nada.

────────────────────────────────────────────────────────────────────────────
"ANTECIPADO OU VENCIDO, PARA FINS DE COMPETÊNCIA" — o ponto delicado
────────────────────────────────────────────────────────────────────────────
O sistema já tem UM conceito de competência, e ele não é ambíguo:
`FolhaPagamento.competencia` é o MÊS TRABALHADO, e o pagamento dela cai no mês
seguinte (`_data_vencimento_folha`: dia 5 do mês seguinte). Este módulo NÃO
cria um segundo conceito de competência — ele não inventa campo novo, não
grava data nenhuma e não mexe em `data_vencimento`. Ele só decide, para a
folha de uma competência C, **de qual competência é o vale-alimentação que
sai nela**:

    vencido    → o VA da competência C sai na folha de C  (benefício = C)
    antecipado → o VA de uma competência é pago junto com a folha da
                 competência ANTERIOR, logo a folha de C carrega o VA de C+1
                 (benefício = C+1)

A diferença NÃO é cosmética, e é por isso que ela precisa existir no cálculo e
não só no texto: no regime diário, C e C+1 podem ter número de dias diferente
(fevereiro com 28 e março com 31 é a diferença de três diárias de benefício no
mesmo holerite), e a proporcionalidade do mês de admissão também muda de mês.
A competência do benefício viaja escrita na Referência da linha, para o dono
poder conferir no papel qual mês está sendo pago ali.

────────────────────────────────────────────────────────────────────────────
DIÁRIO OU MENSAL — e qual contagem de dias
────────────────────────────────────────────────────────────────────────────
`mensal` é o valor cheio, sem proporcionalidade — inclusive no mês de
admissão, porque foi o que o dono descreveu ("se mensal, é o valor cheio").

`diario` multiplica o valor-base pelos dias da competência do BENEFÍCIO. A
contagem é `dias_do_beneficio`, e ela tem TRÊS bases porque não existe norma
legal dizendo qual usar: quem manda é a convenção coletiva rural da base,
depois o contrato, depois a política da fazenda. Por isso é parâmetro
(`vale_alimentacao_base_dias`), com padrão `trabalhados` — o auxílio custeia
a refeição DURANTE a jornada, então o defensável é pagar pelos dias em que
houve jornada. Ver a docstring de `dias_do_beneficio` para o que cada base
conta e para o limite que continua consciente (não há registro de ponto nem
de faltas para quem está na folha — `DiariaDia` é do diarista, que não entra
em folha —, então as faltas entram por parâmetro do chamador, não por
adivinhação).

────────────────────────────────────────────────────────────────────────────
ENQUADRAMENTO — a pergunta que decide o dinheiro
────────────────────────────────────────────────────────────────────────────
A ressalva que este módulo registrava ("VA pago em dinheiro seria salarial, e
o sistema assume o PAT") DEIXOU DE SER RESSALVA e virou regra executável, em
`natureza_do_vale_alimentacao`. O que importa não é o valor nem a
periodicidade: é COMO o benefício é pago, e se a fazenda está no PAT. A
árvore inteira, com o fundamento de cada linha, está na docstring daquela
função — é o ÚNICO ponto de verdade do sistema sobre isso, e nada aqui nem
em `rh_folha.py` reimplementa a regra.

────────────────────────────────────────────────────────────────────────────
LIMITE CONHECIDO — 13º E FÉRIAS
────────────────────────────────────────────────────────────────────────────
Quando a natureza é salarial, o benefício ENTRA nas bases de INSS, IRRF e FGTS
da folha mensal: a linha nasce com `incide_inss`/`incide_irrf`/`incide_fgts`
verdadeiros e `rubrica_folha.base_extra` a soma à base sobre a qual o
percentual é aplicado. Esse caminho existe e está coberto por teste.

O 13º e as FÉRIAS deste sistema, porém, são calculados só sobre
`Pessoa.salario_base` (`rules/folha_rh.py::calcular_ferias`,
`calcular_decimo_terceiro`, `calcular_rescisao`) — eles não consultam rubrica
NENHUMA. Não é uma lacuna do vale-alimentação: bonificação por produtividade,
gueltas e todas as demais verbas salariais do catálogo têm hoje exatamente o
mesmo tratamento, porque o sistema não tem o conceito de "média das parcelas
salariais habituais" (art. 457, §1º, da CLT; Súmulas 45 e 253 do TST) de que
essa integração dependeria. Fazer o VA salarial integrar 13º/férias sem esse
conceito seria escolher uma média por conta própria — quantos meses, quais
competências — e aplicá-la de imediato a TODAS as verbas salariais de TODAS as
fazendas. Fica registrado como decisão consciente e como o próximo passo:
quando houver a média habitual, ela entra em `folha_rh.py` para o catálogo
inteiro de uma vez, e não por um atalho só para esta verba.

Funções puras, sem I/O: quem chama carrega a `Pessoa`, lê os parâmetros da
fazenda (`rules/parametros.py`) e passa tudo. A gravação da linha (e a recusa
em folha paga) mora em `rh_folha.py`.
"""
from __future__ import annotations

import calendar
from datetime import date

from fazenda.rules import holerite
from fazenda.rules.rubrica_folha import (
    NATUREZA_INDENIZATORIA as _NATUREZA_INDENIZATORIA,
    NATUREZA_SALARIAL as _NATUREZA_SALARIAL,
    competencia_seguinte,
)

# A mesma formatação pt-BR do recibo ("R$ 1.234,50"), reusada em vez de
# recriada: dois formatadores de dinheiro no mesmo documento é como um deles
# passa a imprimir "25.0" no dia em que alguém mexer só num.
_brl = holerite._brl

# O código do verbete no catálogo de vencimentos — a linha do holerite é uma
# `FolhaRubrica` comum, e é isso que faz o vale-alimentação aparecer no recibo,
# no líquido, no PDF e no pop-up de pagamento sem nenhum caminho paralelo.
CODIGO = "vale_alimentacao"

PERIODICIDADE_DIARIA = "diario"
PERIODICIDADE_MENSAL = "mensal"
PERIODICIDADES = (PERIODICIDADE_DIARIA, PERIODICIDADE_MENSAL)

REGIME_ANTECIPADO = "antecipado"
REGIME_VENCIDO = "vencido"
REGIMES = (REGIME_ANTECIPADO, REGIME_VENCIDO)

# Os padrões de quem ligou o benefício sem escolher os dois eixos. São os
# conservadores: `mensal` não multiplica nada por dias, e `vencido` mantém o
# benefício na competência da própria folha — ou seja, nenhum dos dois desloca
# dinheiro para um mês que o usuário não pediu.
PERIODICIDADE_PADRAO = PERIODICIDADE_MENSAL
REGIME_PADRAO = REGIME_VENCIDO


# ---------------------------------------------------------------------------
# FORMA DE PAGAMENTO — o eixo que decide a NATUREZA da verba
#
# Não tem padrão, e a ausência de padrão é a decisão: o cadastro EXIGE a
# escolha quando o benefício está ligado (ver `pessoas.py::
# _validar_vale_alimentacao`). Chutar "cartão" em silêncio seria tirar da base
# do INSS/FGTS uma verba que, paga em dinheiro, tem de entrar — erro que só
# aparece anos depois, com juros, numa autuação ou numa reclamatória.
# ---------------------------------------------------------------------------
FORMA_DINHEIRO = "dinheiro"
FORMA_CARTAO = "cartao"
FORMA_IN_NATURA = "in_natura"
FORMAS = (FORMA_DINHEIRO, FORMA_CARTAO, FORMA_IN_NATURA)

# As duas naturezas que o sistema conhece, reusadas de `rubrica_folha` em vez
# de redigitadas: é a mesma coluna `FolhaRubrica.natureza` que vai receber o
# resultado, e duas listas de literais é como uma delas ganha um "indenizatória"
# com acento no dia em que alguém mexer só num lado.
NATUREZA_SALARIAL = _NATUREZA_SALARIAL
NATUREZA_INDENIZATORIA = _NATUREZA_INDENIZATORIA

# ---------------------------------------------------------------------------
# CONTAGEM DE DIAS — três bases, porque não há norma legal que escolha uma
# ---------------------------------------------------------------------------
BASE_DIAS_CORRIDOS = "corridos"
BASE_DIAS_UTEIS = "uteis"
BASE_DIAS_TRABALHADOS = "trabalhados"
BASES_DIAS = (BASE_DIAS_CORRIDOS, BASE_DIAS_UTEIS, BASE_DIAS_TRABALHADOS)
# `trabalhados` é o padrão porque o auxílio-alimentação custeia a refeição
# DURANTE a jornada: pagar por domingo é pagar refeição de dia em que não se
# trabalha. Quem tiver CCT dizendo outra coisa troca o parâmetro.
BASE_DIAS_PADRAO = BASE_DIAS_TRABALHADOS

# Quantos dias da semana cada base conta. `weekday()`: 0=segunda … 6=domingo.
#  - corridos    → todos, inclusive domingo (é a contagem que a folha já usa
#                  para o salário, ver `holerite.dias_da_competencia`);
#  - uteis       → segunda a sexta;
#  - trabalhados → segunda a SÁBADO, a jornada rural típica (44h semanais com
#                  sábado trabalhado). É aproximação declarada, não medição: o
#                  sistema não tem registro de ponto para quem está na folha, e
#                  as faltas entram por fora (ver `dias_do_beneficio`).
_DIAS_DA_SEMANA_POR_BASE = {
    BASE_DIAS_CORRIDOS: (0, 1, 2, 3, 4, 5, 6),
    BASE_DIAS_UTEIS: (0, 1, 2, 3, 4),
    BASE_DIAS_TRABALHADOS: (0, 1, 2, 3, 4, 5),
}

# (singular, plural) — "× 1 dia trabalhado" e "× 24 dias trabalhados". O
# holerite é lido por gente, e concordância errada num documento oficial faz o
# leitor desconfiar do número que vem antes dela.
_ROTULO_BASE_DIAS = {
    BASE_DIAS_CORRIDOS: ("dia corrido", "dias corridos"),
    BASE_DIAS_UTEIS: ("dia útil", "dias úteis"),
    BASE_DIAS_TRABALHADOS: ("dia trabalhado", "dias trabalhados"),
}


def forma_valida(valor: str | None) -> str | None:
    """
    A forma gravada, ou None quando não há forma escolhida.

    DE PROPÓSITO SEM PADRÃO, ao contrário de `periodicidade_valida` e
    `regime_valido`: aqueles dois normalizam o desconhecido para o valor que
    não desloca dinheiro nenhum, e por isso podem ter padrão. Aqui não existe
    escolha neutra — toda forma decide se a verba entra ou não na base do
    INSS, do FGTS, do 13º e das férias. Devolver None é dizer "não sei", e é o
    "não sei" que faz `enquadramento_do_vale_alimentacao` cair no lado
    conservador (salarial) em vez de inventar um PAT que ninguém declarou.
    """
    return valor if valor in FORMAS else None


def base_dias_valida(valor: str | None) -> str:
    """Normaliza a base de contagem gravada no parâmetro da fazenda. Aqui o
    padrão existe (`trabalhados`) porque é escolha de POLÍTICA, não de
    natureza: errar a base muda quantos dias se paga, não se a verba integra o
    salário."""
    return valor if valor in BASES_DIAS else BASE_DIAS_PADRAO


def natureza_do_vale_alimentacao(
    forma: str | None, fazenda_no_pat: bool = False, travada_salarial: bool = False,
) -> str:
    """
    A NATUREZA do vale-alimentação: "salarial" ou "indenizatoria". Ponto de
    verdade único do sistema — todo o resto (a folha, o holerite, as bases de
    incidência, a tela) consulta esta função e ninguém reimplementa a árvore.

    A pergunta que ela responde é a que decide dinheiro de verdade: **o
    vale-alimentação entra ou não na base de INSS, FGTS, 13º e férias?** A
    resposta NÃO depende do valor nem da periodicidade — depende de COMO é
    pago, e de a fazenda estar ou não no PAT.

    ┌──────────────────────────┬──────────────────┬─────────┬───────────────────────────────────┐
    │ Como é pago              │ Natureza         │ Integra │ Fundamento                        │
    ├──────────────────────────┼──────────────────┼─────────┼───────────────────────────────────┤
    │ DINHEIRO (na folha,      │ SALARIAL         │ SIM     │ CLT, art. 457, §2º — a exclusão   │
    │ junto do salário)        │                  │         │ vale "vedado seu pagamento em     │
    │                          │                  │         │ dinheiro"; pago em dinheiro, não  │
    │                          │                  │         │ entra na exclusão                 │
    ├──────────────────────────┼──────────────────┼─────────┼───────────────────────────────────┤
    │ CARTÃO/TICKET, fazenda   │ indenizatória    │ não     │ OJ 133 da SDI-1 do TST;           │
    │ NO PAT                   │                  │         │ Lei 8.212/91, art. 28, §9º, "c"   │
    ├──────────────────────────┼──────────────────┼─────────┼───────────────────────────────────┤
    │ CARTÃO/TICKET, fazenda   │ indenizatória    │ não     │ CLT, art. 457, §2º + Solução de   │
    │ FORA do PAT              │                  │         │ Consulta COSIT nº 35/2019 (RFB):  │
    │                          │                  │         │ desde 11/11/2017 o PAT deixou de  │
    │                          │                  │         │ ser necessário por esta via       │
    ├──────────────────────────┼──────────────────┼─────────┼───────────────────────────────────┤
    │ REFEIÇÃO SERVIDA na      │ SALÁRIO-UTILIDADE│ SIM     │ CLT, art. 458, caput              │
    │ fazenda (in natura),     │ (= salarial)     │         │                                   │
    │ fazenda FORA do PAT      │                  │         │                                   │
    ├──────────────────────────┼──────────────────┼─────────┼───────────────────────────────────┤
    │ REFEIÇÃO SERVIDA, fazenda│ indenizatória    │ não     │ OJ 133 da SDI-1 do TST            │
    │ NO PAT                   │                  │         │                                   │
    └──────────────────────────┴──────────────────┴─────────┴───────────────────────────────────┘

    A TRAVA — OJ 413 da SDI-1 do TST, e é ela que `travada_salarial` executa:

        "A pactuação em norma coletiva conferindo caráter indenizatório à
        verba 'auxílio-alimentação' ou a adesão posterior do empregador ao PAT
        não altera a natureza salarial da parcela, instituída anteriormente,
        para aqueles empregados que, habitualmente, já percebiam o benefício,
        a teor das Súmulas 51, I, e 241 do TST."

    Ou seja: quem JÁ VINHA recebendo o VA com natureza salarial não perde essa
    natureza porque a fazenda mudou a forma de pagamento depois, nem porque
    entrou no PAT depois — seria alteração contratual lesiva (CLT, art. 468).
    Vale só para quem for contratado dali em diante. Na prática a fazenda pode
    ter DUAS populações com regras diferentes, e é por isso que a trava é
    marcador POR FUNCIONÁRIO, e não parâmetro da fazenda. Quando ligada, ela
    vence a forma e vence o PAT — é a primeira coisa que esta função olha.

    FORMA NÃO INFORMADA cai em SALARIAL, e a escolha é deliberada. Assumir
    "cartão" tiraria da base do INSS/FGTS uma verba que talvez tivesse de
    entrar — subdeclaração, que aparece anos depois com juros e multa. Assumir
    salarial recolhe a mais sobre uma verba que talvez não precisasse: caro,
    visível no holerite do mês seguinte, e reversível assim que alguém abrir o
    cadastro e escolher a forma. Entre errar para dentro da base e errar para
    fora dela, o sistema erra para dentro.
    """
    if travada_salarial:
        return NATUREZA_SALARIAL
    forma = forma_valida(forma)
    if forma is None:
        return NATUREZA_SALARIAL
    if forma == FORMA_DINHEIRO:
        return NATUREZA_SALARIAL
    if forma == FORMA_CARTAO:
        return NATUREZA_INDENIZATORIA
    # in natura: salário-utilidade (art. 458, caput), SALVO no PAT (OJ 133).
    return NATUREZA_INDENIZATORIA if fazenda_no_pat else NATUREZA_SALARIAL


def enquadramento_do_vale_alimentacao(
    forma: str | None, fazenda_no_pat: bool = False, travada_salarial: bool = False,
) -> dict:
    """
    A natureza MAIS o que o papel precisa dizer sobre ela: o fundamento da
    linha da árvore que se aplicou, o rótulo da forma e as três incidências.

    Existe separada de `natureza_do_vale_alimentacao` porque a folha precisa
    das duas coisas em momentos diferentes (a natureza decide a base; o
    fundamento e o rótulo vão escritos na Referência do holerite), mas a
    ÁRVORE é a de lá — esta função não decide nada por conta própria, só
    veste o resultado.

    `integra_bases` é a mesma resposta que `natureza`, dita como booleano:
    salarial entra em INSS, IRRF e FGTS; indenizatória não entra em nenhum. É
    o alinhamento que `FolhaPagamento.valor_rubricas_tributaveis` (um número
    só para os três) depende — ver `rubrica_folha.base_tributavel_das_rubricas`.

    `aviso_lei_14442` é CONFORMIDADE SEPARADA, e não muda natureza nenhuma: a
    Lei 14.442/2022 (art. 2º, §§ 4º e 5º) proíbe o pagamento do auxílio em
    dinheiro e a conversão/saque do saldo, com multa de R$ 5.000 a R$ 50.000,
    dobrada na reincidência. Pagar em dinheiro não é só "vira salarial" — é
    infração autônoma. O sistema AVISA e não bloqueia: a decisão é do
    empregador, e travar o cadastro esconderia do holerite um pagamento que
    está acontecendo de qualquer jeito.
    """
    natureza = natureza_do_vale_alimentacao(forma, fazenda_no_pat, travada_salarial)
    forma_norm = forma_valida(forma)
    no_pat = " (fazenda no PAT)" if fazenda_no_pat else " (fazenda fora do PAT)"

    if forma_norm == FORMA_DINHEIRO:
        rotulo = "pago em dinheiro"
        fundamento = (
            "Auxílio-alimentação pago em dinheiro — natureza salarial: a exclusão do "
            "art. 457, §2º, da CLT vale \"vedado seu pagamento em dinheiro\""
        )
    elif forma_norm == FORMA_CARTAO:
        rotulo = "pago em cartão/ticket" + no_pat
        fundamento = (
            "Auxílio-alimentação em cartão/ticket do PAT, sem natureza salarial — "
            "OJ 133 da SDI-1 do TST; Lei 8.212/91, art. 28, §9º, \"c\""
            if fazenda_no_pat else
            "Auxílio-alimentação em cartão/ticket, sem natureza salarial mesmo fora do PAT — "
            "CLT, art. 457, §2º; Solução de Consulta COSIT nº 35/2019 da Receita Federal"
        )
    elif forma_norm == FORMA_IN_NATURA:
        rotulo = "refeição servida na fazenda" + no_pat
        fundamento = (
            "Refeição fornecida por fazenda inscrita no PAT, sem natureza salarial — "
            "OJ 133 da SDI-1 do TST"
            if fazenda_no_pat else
            "Refeição fornecida in natura — salário-utilidade, CLT, art. 458, caput"
        )
    else:
        rotulo = "forma de pagamento não informada"
        fundamento = (
            "Forma de pagamento não informada no cadastro — enquadrado como salarial, "
            "o lado que não subdeclara base (CLT, art. 457, §2º)"
        )

    if travada_salarial:
        rotulo = f"{rotulo} · natureza salarial travada"
        fundamento = (
            "Natureza salarial preservada para quem já percebia o benefício — "
            "OJ 413 da SDI-1 do TST; CLT, art. 468"
        )

    integra = natureza == NATUREZA_SALARIAL
    return {
        "natureza": natureza,
        "forma": forma_norm,
        "rotulo": rotulo,
        "fundamento": fundamento,
        "integra_bases": integra,
        "incide_inss": integra,
        "incide_irrf": integra,
        "incide_fgts": integra,
        "travada_salarial": bool(travada_salarial),
        "fazenda_no_pat": bool(fazenda_no_pat),
        "aviso_lei_14442": forma_norm == FORMA_DINHEIRO,
    }


def dias_do_beneficio(
    competencia: str,
    data_admissao=None,
    data_desligamento=None,
    *,
    base_dias: str = BASE_DIAS_PADRAO,
    mes_admissao_integral: bool = False,
    faltas_injustificadas: int = 0,
    faltas_justificadas: int = 0,
    falta_justificada_desconta: bool = False,
) -> tuple[int, int]:
    """
    (dias a pagar, dias do mês cheio na MESMA base) do vale-alimentação diário.

    POR QUE NÃO É `holerite.dias_da_competencia`. Aquela é a contagem do
    SALÁRIO, e ela é de dias corridos por um motivo bom: salário mensal não se
    divide por dia útil. O auxílio-alimentação não é salário — ele custeia a
    refeição durante a jornada —, e não existe norma legal que fixe a
    contagem: quem manda é a convenção coletiva rural da base, depois o
    contrato, depois a política da fazenda. Daí as três bases, e daí a
    contagem própria. Com `base_dias="corridos"`, sem faltas e sem
    desligamento, esta função devolve EXATAMENTE o mesmo par que
    `holerite.dias_da_competencia` — há teste travando isso, para as duas não
    divergirem em silêncio.

    PROPORCIONALIDADE. O mês de ADMISSÃO conta só a partir do dia da admissão,
    e o mês de RESCISÃO só até o dia do desligamento: o benefício custeia a
    refeição dos dias em que houve vínculo, e pagar o mês cheio nos dois casos
    é pagar refeição de quem não estava lá. `mes_admissao_integral` desliga
    isso APENAS na admissão (é o que algumas CCTs preveem, "no mês de admissão
    paga-se o mês cheio") — não há interruptor equivalente para a rescisão,
    porque nenhuma norma manda pagar adiante do desligamento.

    FALTAS. Falta INJUSTIFICADA autoriza suprimir o dia (não houve jornada, não
    houve refeição a custear). Falta JUSTIFICADA, férias, afastamento pelo INSS
    e feriado normalmente NÃO autorizam — mas a CCT decide, e por isso
    `falta_justificada_desconta` é parâmetro da fazenda. Os números de faltas
    chegam por argumento e o padrão é zero: este sistema não tem registro de
    ponto para quem está na folha (`DiariaDia` é do diarista, que não entra em
    folha), e inventar faltas seria inventar desconto no benefício de alguém.
    O dia em que houver registro de ponto, é aqui que ele entra — sem que a
    regra precise mudar.
    """
    base_dias = base_dias_valida(base_dias)
    dias_validos = _DIAS_DA_SEMANA_POR_BASE[base_dias]
    ano, mes = (int(x) for x in competencia.split("-"))
    ultimo = calendar.monthrange(ano, mes)[1]

    primeiro_dia, ultimo_dia = 1, ultimo
    if data_admissao is not None and data_admissao.strftime("%Y-%m") == competencia:
        if not mes_admissao_integral:
            primeiro_dia = data_admissao.day
    elif data_admissao is not None and data_admissao > date(ano, mes, ultimo):
        # Admissão depois do fim da competência do benefício — alcançável no
        # regime antecipado, em que a folha olha para o mês seguinte.
        primeiro_dia, ultimo_dia = 1, 0
    if data_desligamento is not None:
        if data_desligamento < date(ano, mes, 1):
            primeiro_dia, ultimo_dia = 1, 0
        elif data_desligamento.strftime("%Y-%m") == competencia:
            ultimo_dia = min(ultimo_dia, data_desligamento.day)

    def _contar(inicio: int, fim: int) -> int:
        return sum(
            1 for dia in range(inicio, fim + 1)
            if date(ano, mes, dia).weekday() in dias_validos
        )

    dias_mes = _contar(1, ultimo)
    dias = _contar(primeiro_dia, ultimo_dia) if ultimo_dia >= primeiro_dia else 0

    descontar = max(int(faltas_injustificadas or 0), 0)
    if falta_justificada_desconta:
        descontar += max(int(faltas_justificadas or 0), 0)
    return max(dias - descontar, 0), dias_mes


def _competencia_extenso(competencia: str) -> str:
    """"2026-08" → "08/2026" — formato de referência do documento, não ISO."""
    partes = (competencia or "").split("-")
    return f"{partes[1]}/{partes[0]}" if len(partes) == 2 else (competencia or "—")


def periodicidade_valida(valor: str | None) -> str:
    """Normaliza o que está gravado (ou o que o formulário mandou). Valor
    desconhecido cai no padrão em vez de explodir: o cadastro é editado por
    humanos e um typo não pode derrubar a geração da folha inteira."""
    return valor if valor in PERIODICIDADES else PERIODICIDADE_PADRAO


def regime_valido(valor: str | None) -> str:
    """Idem para antecipado/vencido — ver `periodicidade_valida`."""
    return valor if valor in REGIMES else REGIME_PADRAO


def competencia_do_beneficio(competencia_folha: str, regime: str | None) -> str:
    """
    De qual competência é o vale-alimentação que sai NESTA folha.

    É a tradução literal do "antecipado ou vencido, para fins de competência"
    — e o único lugar do sistema onde essa escolha vira uma conta. Reusa
    `rubrica_folha.competencia_seguinte`, a mesma função que a folha já usa
    para saber em que mês um aumento incorpora e em que mês a recorrência
    gera a próxima competência: não há um segundo calendário aqui.
    """
    if regime_valido(regime) == REGIME_ANTECIPADO:
        return competencia_seguinte(competencia_folha)
    return competencia_folha


def calcular(
    pessoa,
    competencia_folha: str,
    *,
    fazenda_no_pat: bool = False,
    base_dias: str = BASE_DIAS_PADRAO,
    mes_admissao_integral: bool = False,
    falta_justificada_desconta: bool = False,
    faltas_injustificadas: int = 0,
    faltas_justificadas: int = 0,
    data_desligamento=None,
) -> dict | None:
    """
    O vale-alimentação desta pessoa NESTA folha, ou None quando não há linha
    a gerar (benefício desligado, ou ligado sem valor-base).

    Devolve tudo o que a linha precisa dizer no papel — o valor, a competência
    do benefício, a periodicidade, a conta que produziu o valor no diário
    (valor-base × dias) e, agora, o ENQUADRAMENTO: natureza, as três
    incidências e o fundamento da linha da árvore que se aplicou. Nada disso é
    deduzido depois pela tela: o recibo é prova e cada número dele tem de vir
    com a explicação junto.

    OS ARGUMENTOS NOMEADOS SÃO PARÂMETROS DA FAZENDA, e chegam prontos porque
    este módulo é de regras puras, sem I/O: quem os lê do banco é o chamador
    (`rh_folha.py::_politica_vale_alimentacao`, que consulta
    `rules/parametros.py`). Os padrões aqui são os mesmos padrões dos
    parâmetros — uma fazenda que nunca abriu a tela de Parâmetros e um teste
    que chama esta função direto veem exatamente o mesmo comportamento.

    `pessoa.data_admissao` e `data_desligamento` entram na conta do DIÁRIO: o
    benefício custeia a refeição dos dias em que houve vínculo, então os dois
    extremos são proporcionais (ver `dias_do_beneficio`). O mensal ignora isso
    de propósito: o dono disse "se mensal, é o valor cheio".
    """
    if not getattr(pessoa, "vale_alimentacao", False):
        return None
    valor_base = round(getattr(pessoa, "vale_alimentacao_valor", None) or 0.0, 2)
    if valor_base <= 0:
        # Benefício ligado sem valor cadastrado não vira linha de R$ 0,00 no
        # holerite: linha de zero num documento oficial lê como "não recebeu",
        # que é uma afirmação diferente de "ainda não foi configurado".
        return None

    periodicidade = periodicidade_valida(getattr(pessoa, "vale_alimentacao_periodicidade", None))
    regime = regime_valido(getattr(pessoa, "vale_alimentacao_regime", None))
    competencia = competencia_do_beneficio(competencia_folha, regime)

    # O enquadramento é do FUNCIONÁRIO (forma e trava da OJ 413) cruzado com o
    # fato da FAZENDA (PAT) — e sai do ponto de verdade único, nunca de uma
    # cópia da árvore escrita aqui.
    enquadramento = enquadramento_do_vale_alimentacao(
        getattr(pessoa, "vale_alimentacao_forma", None),
        fazenda_no_pat=fazenda_no_pat,
        travada_salarial=bool(getattr(pessoa, "vale_alimentacao_natureza_travada_salarial", False)),
    )

    dias: int | None = None
    dias_mes: int | None = None
    base = base_dias_valida(base_dias)
    if periodicidade == PERIODICIDADE_DIARIA:
        dias, dias_mes = dias_do_beneficio(
            competencia,
            getattr(pessoa, "data_admissao", None),
            data_desligamento,
            base_dias=base,
            mes_admissao_integral=mes_admissao_integral,
            faltas_injustificadas=faltas_injustificadas,
            faltas_justificadas=faltas_justificadas,
            falta_justificada_desconta=falta_justificada_desconta,
        )
        # Sem dia nenhum na competência do benefício (admissão posterior no
        # regime antecipado, desligamento anterior, mês inteiro de faltas): não
        # há benefício a pagar, e linha de R$ 0,00 no holerite mente.
        if dias <= 0:
            return None
        valor = round(valor_base * dias, 2)
    else:
        valor = valor_base

    return {
        "valor": valor,
        "valor_base": valor_base,
        "periodicidade": periodicidade,
        "regime": regime,
        "competencia_beneficio": competencia,
        "dias": dias,
        "dias_mes": dias_mes,
        "base_dias": base,
        **{
            chave: enquadramento[chave] for chave in (
                "natureza", "forma", "fundamento", "integra_bases",
                "incide_inss", "incide_irrf", "incide_fgts",
                "travada_salarial", "fazenda_no_pat", "aviso_lei_14442",
            )
        },
        "rotulo_enquadramento": enquadramento["rotulo"],
    }


def descricao(calculo: dict) -> str:
    """
    A composição da linha em uma frase — de onde o valor veio, de que mês ele
    é e SOB QUE ENQUADRAMENTO ele está sendo pago. Vai gravada em
    `FolhaRubrica.descricao` e o holerite a mostra na coluna REFERÊNCIA (ver
    `rubrica_folha.referencia_rubrica`), não colada no rótulo: numa rubrica
    gerada pelo cadastro, o "texto livre do usuário" é justamente a explicação
    do número, e o lugar da explicação é a Referência.

    O enquadramento entra aqui porque a mesma verba, com o mesmo valor, pode
    ser salarial num funcionário e indenizatória no outro na MESMA folha (a
    trava da OJ 413 é por pessoa). Sem a forma escrita na linha, o dono veria
    dois holerites idênticos com retenções diferentes e nenhuma explicação. A
    natureza e as incidências continuam sendo escritas logo depois por
    `referencia_rubrica`, a partir do que ficou congelado na linha.

    Exemplos:
      "Mensal · competência 07/2026 (vencido) · pago em cartão/ticket (fazenda no PAT)"
      "Diário · R$ 25,00 × 24 dias trabalhados · competência 08/2026 (antecipado) · pago em dinheiro"
    """
    if calculo["periodicidade"] == PERIODICIDADE_DIARIA:
        base = (
            f"Diário · {_brl(calculo['valor_base'])} × {calculo['dias']} "
            f"{_ROTULO_BASE_DIAS[base_dias_valida(calculo.get('base_dias'))][0 if calculo['dias'] == 1 else 1]}"
        )
    else:
        base = "Mensal"
    competencia = _competencia_extenso(calculo["competencia_beneficio"])
    partes = [base, f"competência {competencia} ({calculo['regime']})"]
    rotulo = calculo.get("rotulo_enquadramento")
    if rotulo:
        partes.append(rotulo)
    return " · ".join(partes)
