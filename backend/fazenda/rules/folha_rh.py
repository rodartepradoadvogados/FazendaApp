"""
Cálculo de Férias, 13º salário e Rescisão — RH ampliado (item de auditoria
"RH ampliado (férias/13º/eSocial)" e, na parte 2, "regras específicas de
rescisão"). A integração com o eSocial (envio ao governo) está
EXPLICITAMENTE FORA de escopo aqui — inviável sem certificado digital e
infraestrutura própria; este módulo só cobre o cálculo interno usado pelo
lançamento em `fazenda.api.routers.cadastro` (endpoints `/cadastro/ferias`,
`/cadastro/decimo-terceiro` e `/cadastro/rescisao`).

Funções puras, sem I/O — fáceis de testar isoladamente (ver
`backend/tests/test_folha_rh.py`).

────────────────────────────────────────────────────────────────────────────
A MÉDIA DAS VERBAS VARIÁVEIS HABITUAIS — `media_variaveis`
────────────────────────────────────────────────────────────────────────────
Até esta versão, as três funções abaixo conheciam UM número: `salario_base`.
Nenhuma consultava rubrica nenhuma, e por isso nenhuma parcela salarial
variável — bonificação por produtividade, gueltas, vale-alimentação de
natureza salarial, insalubridade — entrava nas bases de 13º, férias e
rescisão. Era subdeclaração de todo funcionário com remuneração variável, e
estava registrada como `LIMITE CONHECIDO` na docstring de
`rules/vale_alimentacao.py`.

O que fecha o buraco é o parâmetro `media_variaveis` que cada função passou a
aceitar: a MÉDIA MENSAL das parcelas salariais variáveis habituais, somada ao
salário-base antes de dividir por 30 (férias) ou por 12 (13º). O fundamento da
integração é o art. 457, §1º, da CLT, com a habitualidade da Súmula 45 do TST.

O PADRÃO É `0.0`, E O PADRÃO É A GARANTIA. Com ele, cada uma das três funções
devolve exatamente os mesmos centavos que devolvia antes — é isso que faz o
parâmetro da fazenda (`parametros.calcula_media_verbas_variaveis`, desligado
por padrão) significar "nada muda". Há teste travando os três casos com
números concretos.

QUEM CALCULA A MÉDIA NÃO É ESTE MÓDULO. A apuração precisa de sessão e banco
(ela lê as `FolhaRubrica` já gravadas, com a natureza congelada no
lançamento), e este arquivo é de funções puras — ela mora em
`rules/media_verbas_habituais.py`, e quem junta as duas coisas é
`api/routers/cadastro/rh_folha.py`. A separação é o que mantém estas funções
testáveis sem banco e impede que a média vire recálculo de holerite antigo.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from dateutil.relativedelta import relativedelta

TERCO_CONSTITUCIONAL_PADRAO = 1 / 3

TIPOS_RESCISAO = ("sem_justa_causa", "pedido_demissao", "justa_causa", "acordo_mutuo")
TipoRescisao = Literal["sem_justa_causa", "pedido_demissao", "justa_causa", "acordo_mutuo"]


def calcular_ferias(
    salario_base: float,
    dias_gozados: int,
    abono_pecuniario_dias: int = 0,
    percentual_terco: float = TERCO_CONSTITUCIONAL_PADRAO,
    media_variaveis: float = 0.0,
) -> dict:
    """
    Calcula o valor de um período de férias:
    - `valor_ferias` = valor do dia (base/30) × dias efetivamente gozados;
    - `valor_terco_constitucional` = 1/3 constitucional sobre os dias gozados;
    - `valor_abono` = valor do abono pecuniário (dias "vendidos", art. 143
      CLT), incluindo o respectivo 1/3, quando `abono_pecuniario_dias > 0`;
    - `valor_total` = soma dos três.

    A BASE é `salario_base + media_variaveis`, e não o salário puro (CLT, art.
    142, §§ 1º a 6º: havendo remuneração variável, a média do PERÍODO
    AQUISITIVO integra o cálculo das férias). Com o padrão `media_variaveis=0.0`
    a base é o salário-base e o resultado é idêntico ao de sempre.

    O TERÇO CONSTITUCIONAL INCIDE SOBRE O TOTAL JÁ COM A MÉDIA sem nenhuma
    linha a mais: ele é percentual de `valor_ferias`, que já saiu da base
    somada. O mesmo vale para o abono pecuniário — o que se vende é dia de
    férias, e o dia de férias vale o mesmo com ou sem venda.

    `salario_base`, `media_variaveis` e `base_calculo` voltam no retorno para
    o recibo poder mostrar de onde veio o valor do dia. Média que ninguém
    consegue conferir é média que ninguém confia.
    """
    base_calculo = salario_base + media_variaveis
    valor_dia = base_calculo / 30
    valor_ferias = round(valor_dia * dias_gozados, 2)
    valor_terco_constitucional = round(valor_ferias * percentual_terco, 2)
    valor_abono = 0.0
    if abono_pecuniario_dias > 0:
        valor_abono = round(valor_dia * abono_pecuniario_dias * (1 + percentual_terco), 2)
    valor_total = round(valor_ferias + valor_terco_constitucional + valor_abono, 2)
    return {
        "valor_ferias": valor_ferias,
        "valor_terco_constitucional": valor_terco_constitucional,
        "valor_abono": valor_abono,
        "valor_total": valor_total,
        "salario_base": round(salario_base, 2),
        "media_variaveis": round(media_variaveis, 2),
        "base_calculo": round(base_calculo, 2),
    }


def calcular_decimo_terceiro(
    salario_base: float, meses_trabalhados: int, media_variaveis: float = 0.0,
) -> float:
    """Valor INTEGRAL do 13º salário do ano, proporcional aos meses
    trabalhados (1 a 12) — `(salario_base + media_variaveis) / 12 *
    meses_trabalhados`. É o total devido no ano, NÃO o valor de uma parcela:
    para dividir o 13º em 1ª/2ª parcela use `valor_parcela_decimo_terceiro`
    sobre este resultado.

    `media_variaveis` é a média mensal das parcelas salariais variáveis do ANO
    CIVIL da competência, dividida pelos meses de vigência do contrato no ano
    (Lei 4.090/62, art. 1º, §1º, e Decreto 57.155/65, art. 2º). Com o padrão
    `0.0` o resultado é `salario_base / 12 * meses`, idêntico ao de sempre.

    O DIVISOR DA MÉDIA E OS AVOS TÊM DE SER O MESMO NÚMERO. Quem apura a média
    recebe `divisor=meses_trabalhados` (ver
    `media_verbas_habituais.media_do_ano_civil`), de modo que o admitido em
    julho com R$ 3.600 de variável no semestre tenha média 600 (3.600/6) e 13º
    de (3.000+600)/12×6 = 1.800 — a conta que a contabilidade faz à mão."""
    return round((salario_base + media_variaveis) / 12 * meses_trabalhados, 2)


PARCELAS_DECIMO_TERCEIRO = ("unica", "primeira", "segunda")

# Lei 4.749/1965, art. 2º, caput: o adiantamento (1ª parcela) é "metade do
# salário recebido pelo respectivo empregado no mês anterior" — na prática,
# até 50% do 13º devido.
PERCENTUAL_ADIANTAMENTO_DECIMO_TERCEIRO = 0.5


def valor_parcela_decimo_terceiro(
    valor_integral: float,
    parcela: str,
    ja_lancado: float = 0.0,
    percentual_adiantamento: float = PERCENTUAL_ADIANTAMENTO_DECIMO_TERCEIRO,
) -> float:
    """
    Quanto ainda se deve pagar NESTA parcela do 13º, dado o 13º integral do
    ano e o quanto já foi lançado para a mesma pessoa no mesmo ano.

    ERA O BUG MAIS CARO DO MÓDULO: `calcular_decimo_terceiro` devolve o 13º
    CHEIO e era gravado igualzinho para `unica`, `primeira` e `segunda` — o
    campo `parcela` só mudava o rótulo e a data de vencimento. Lançar a 1ª e
    depois a 2ª parcela de um salário de R$ 3.000 punha R$ 6.000 em Contas a
    Pagar para um 13º de R$ 3.000.

    Regra legal aplicada (Lei 4.749/1965, arts. 1º e 2º):
    - `primeira` é ADIANTAMENTO de ATÉ 50% do 13º devido;
    - `segunda` (e `unica`) é o acerto: 13º integral MENOS o que já foi
      adiantado — as retenções (INSS/IRRF) entram só aqui, e por fora deste
      cálculo, que devolve sempre o BRUTO da parcela.

    `ja_lancado` é a soma do bruto das outras parcelas do mesmo ano da mesma
    pessoa. Com ele, a soma das parcelas NUNCA ultrapassa o 13º devido, seja
    qual for a ordem em que forem lançadas (inclusive "única" depois de uma
    1ª parcela, que vira o saldo). Devolve 0.0 quando o ano já foi
    integralmente lançado — quem chama deve recusar o lançamento.
    """
    if parcela not in PARCELAS_DECIMO_TERCEIRO:
        raise ValueError(f"parcela inválida: {parcela!r} (esperado uma de {PARCELAS_DECIMO_TERCEIRO})")
    teto = valor_integral * percentual_adiantamento if parcela == "primeira" else valor_integral
    return round(max(min(teto, valor_integral) - ja_lancado, 0.0), 2)


def retencoes_permitidas_decimo_terceiro(parcela: str) -> bool:
    """False para a 1ª parcela: o adiantamento é pago CHEIO — INSS e IRRF
    incidem só na 2ª parcela, sobre o 13º integral (Lei 8.212/1991, art. 28,
    §7º; Dec. 3.048/1999, art. 214, §6º; Lei 7.713/1988, art. 26). O FGTS
    incide nas duas, mas é encargo do empregador e não sai do valor pago ao
    empregado, então não entra aqui."""
    return parcela != "primeira"


# ---------------------------------------------------------------------------
# Rescisão contratual (CLT) — verbas rescisórias das 4 modalidades mais
# comuns. Cobre só o "core" comum a praticamente toda rescisão CLT (saldo de
# salário, aviso prévio, férias vencidas/proporcionais, 13º proporcional,
# multa do FGTS); NÃO cobre verbas específicas de convenção coletiva, multas
# contratuais, estabilidades (gestante, CIPA, acidentário...) nem o eSocial/
# TRCT oficial — tudo isso fica fora de escopo (mesma linha do aviso já
# registrado para férias/13º).
# ---------------------------------------------------------------------------
def meses_regra_15_dias(inicio: date, fim: date, limite: int | None = 12) -> int:
    """Meses completos entre duas datas aplicando a "regra dos 15 dias"
    (Súmula 45 do TST — usada tanto para 13º salário quanto para férias
    proporcionais): uma fração de mês igual ou superior a 15 dias trabalhados
    conta como mês integral; fração menor é desprezada. `limite` corta o
    resultado (12 para contagens dentro de um único ano/período aquisitivo;
    `None` para o tempo total de casa, usado na estimativa de FGTS)."""
    if fim <= inicio:
        return 0
    diferenca = relativedelta(fim, inicio)
    meses = diferenca.years * 12 + diferenca.months
    if diferenca.days >= 15:
        meses += 1
    meses = max(meses, 0)
    if limite is not None:
        meses = min(meses, limite)
    return meses


def _anos_completos(inicio: date, fim: date) -> int:
    """Anos completos de serviço, SEM arredondamento por fração (diferente de
    `meses_regra_15_dias`) — é o que a Lei 12.506/2011 usa para os 3 dias
    extras de aviso prévio por "ano completo de serviço"."""
    anos = fim.year - inicio.year
    if (fim.month, fim.day) < (inicio.month, inicio.day):
        anos -= 1
    return max(anos, 0)


def inicio_periodo_aquisitivo_atual(data_admissao: date, data_referencia: date) -> date:
    """Início do período aquisitivo de férias em curso na data de
    referência — o aniversário de admissão mais recente que seja anterior ou
    igual a ela (ou a própria admissão, se ainda não completou 1 ano)."""
    anos = _anos_completos(data_admissao, data_referencia)
    return data_admissao + relativedelta(years=anos)


def calcular_rescisao(
    salario_base: float,
    data_admissao: date,
    data_desligamento: date,
    tipo_rescisao: TipoRescisao,
    dias_ferias_vencidas: int = 0,
    aviso_previo_trabalhado: bool = False,
    percentual_terco: float = TERCO_CONSTITUCIONAL_PADRAO,
    percentual_estimado_fgts_mensal: float = 0.08,
    media_variaveis_decimo_terceiro: float = 0.0,
    media_variaveis_ferias: float = 0.0,
    media_variaveis_aviso_previo: float = 0.0,
) -> dict:
    """
    Verbas rescisórias da CLT para as 4 modalidades mais comuns de
    desligamento. Retorna um dict detalhado (cada verba separada + total),
    para o usuário auditar de onde veio cada valor — não só o número final.

    Modalidades (`tipo_rescisao`) e o que cada uma paga:
    - `sem_justa_causa` (iniciativa do empregador): todas as verbas abaixo,
      aviso prévio integral, multa de 40% do FGTS.
    - `pedido_demissao` (iniciativa do empregado): saldo de salário + férias
      vencidas/proporcionais + 13º proporcional. SEM aviso prévio (é o
      empregado quem deveria dar o aviso ao empregador — se não der, o
      empregador PODE descontar o equivalente do saldo, o que este cálculo
      não modela) e SEM multa/saque do FGTS.
    - `justa_causa` (falta grave do empregado, art. 482 CLT): só saldo de
      salário + férias vencidas (direito adquirido, não se perde mesmo na
      justa causa). SEM aviso prévio, SEM férias/13º proporcionais (art. 146,
      parágrafo único, CLT e Lei 4.090/62, art. 3º, respectivamente) e SEM
      multa/saque do FGTS.
    - `acordo_mutuo` (distrato — art. 484-A CLT, Lei 13.467/2017): como
      `sem_justa_causa`, mas com aviso prévio pago pela METADE, multa do
      FGTS de 20% (em vez de 40%) e saque limitado a 80% do saldo do FGTS
      (informativo — este módulo não controla saldo real de FGTS).

    Fórmulas de cada verba:
    - `saldo_salario`: dias corridos trabalhados no mês da rescisão (o dia do
      mês de `data_desligamento`) × (`salario_base` / 30).
    - `aviso_previo` (só sem_justa_causa/acordo_mutuo): 30 dias + 3 dias por
      ano completo de serviço, limitado a 90 dias (Lei 12.506/2011); metade
      disso no acordo mútuo. Se `aviso_previo_trabalhado=True`, só os dias
      ADICIONAIS (além dos 30 iniciais) são indenizados em dinheiro — os 30
      dias-base são considerados trabalhados (folha normal, fora deste
      cálculo). O aviso prévio indenizado PROJETA o fim do contrato (Súmula
      371 TST): os dias indenizados são somados a `data_desligamento` antes
      de calcular férias/13º proporcionais e o tempo total para o FGTS.
    - `ferias_vencidas`: reaproveita `calcular_ferias(salario_base,
      dias_ferias_vencidas)` — dias já adquiridos e não gozados, + 1/3.
    - `ferias_proporcionais`: meses completos do período aquisitivo em curso
      (regra dos 15 dias) convertidos em dias equivalentes (30/12 × meses) e
      passados por `calcular_ferias`, também com 1/3. Zerada na justa causa.
    - `decimo_terceiro_proporcional`: reaproveita `calcular_decimo_terceiro`
      com os meses completos (regra dos 15 dias) trabalhados no ano da
      rescisão. Zerada na justa causa.
    - `fgts` — **ESTIMATIVA**: o sistema não rastreia os depósitos mensais
      reais de FGTS, então o total depositado é aproximado por
      `salario_base × percentual_estimado_fgts_mensal (padrão 8%) × meses de
      casa`; a multa é esse total estimado × 40% (sem_justa_causa), 20%
      (acordo_mutuo) ou 0% (pedido_demissao/justa_causa). Use o valor real do
      extrato do FGTS sempre que disponível — este número é só uma
      referência.

    ── AS TRÊS MÉDIAS, E POR QUE SÃO TRÊS ─────────────────────────────────
    Na rescisão, cada verba segue a regra da SUA natureza — não existe "a
    média da rescisão". Por isso são três parâmetros e não um:

    - `media_variaveis_decimo_terceiro` → 13º proporcional. Janela: ANO CIVIL
      do desligamento (Lei 4.090/62, art. 1º, §1º; Decreto 57.155/65, art. 2º).
    - `media_variaveis_ferias` → férias VENCIDAS e PROPORCIONAIS. Janela:
      PERÍODO AQUISITIVO (CLT, art. 142, §§ 1º a 6º). As duas usam a mesma
      média porque as duas são férias; o terço sai certo sozinho, porque em
      `calcular_ferias` ele é percentual do valor já calculado sobre a base
      somada.
    - `media_variaveis_aviso_previo` → aviso prévio INDENIZADO. Janela: os
      ÚLTIMOS 12 MESES anteriores ao desligamento — o aviso indenizado paga o
      que a pessoa receberia, e a referência do que receberia é o que vinha
      recebendo.

    O SALDO DE SALÁRIO NÃO LEVA MÉDIA, e a ausência é a regra certa: ele é o
    salário dos dias efetivamente trabalhados no mês da rescisão, e a variável
    desse mês é lançada na folha desse mês, não numa média. Somar média ali
    pagaria a mesma parcela duas vezes.

    A MULTA DO FGTS TAMBÉM NÃO, e isso é limite consciente: o depósito é uma
    ESTIMATIVA declarada (o sistema não guarda o extrato do FGTS), e inflar um
    número que já não serve de documento só o tornaria mais difícil de
    conferir contra o extrato real. Quem tem o extrato usa o override do
    campo.

    Todos os três nascem em `0.0`, e com os três em zero o retorno é
    centavo a centavo o de antes desta feature.
    """
    if tipo_rescisao not in TIPOS_RESCISAO:
        raise ValueError(f"tipo_rescisao inválido: {tipo_rescisao!r} (esperado um de {TIPOS_RESCISAO})")

    # --- Saldo de salário ---------------------------------------------------
    dias_trabalhados_no_mes = data_desligamento.day
    saldo_salario = round(salario_base / 30 * dias_trabalhados_no_mes, 2)

    # --- Aviso prévio (Lei 12.506/2011) --------------------------------------
    devido_aviso_previo = tipo_rescisao in ("sem_justa_causa", "acordo_mutuo")
    dias_aviso_previo = min(30 + 3 * _anos_completos(data_admissao, data_desligamento), 90)
    if tipo_rescisao == "acordo_mutuo":
        dias_aviso_previo = dias_aviso_previo // 2  # art. 484-A CLT — pela metade
    dias_aviso_indenizados = 0
    valor_aviso_previo = 0.0
    # A base do aviso INDENIZADO leva a média dos últimos 12 meses (ver a
    # docstring); a dos 30 dias trabalhados não entra aqui — quando o aviso é
    # trabalhado, esses dias saem na folha normal do mês, com as variáveis
    # daquele mês.
    base_aviso_previo = salario_base + media_variaveis_aviso_previo
    if devido_aviso_previo:
        dias_aviso_indenizados = max(dias_aviso_previo - 30, 0) if aviso_previo_trabalhado else dias_aviso_previo
        valor_aviso_previo = round(base_aviso_previo / 30 * dias_aviso_indenizados, 2)

    # Projeção do aviso prévio indenizado (Súmula 371 TST) sobre o tempo de
    # serviço considerado nas verbas abaixo — só quando NÃO foi trabalhado
    # (se foi, `data_desligamento` já é o fim real do contrato).
    if dias_aviso_indenizados and not aviso_previo_trabalhado:
        data_referencia = data_desligamento + timedelta(days=dias_aviso_previo)
    else:
        data_referencia = data_desligamento

    # --- Férias vencidas (direito adquirido — devidas mesmo na justa causa) -
    ferias_vencidas = calcular_ferias(
        salario_base, dias_ferias_vencidas, 0, percentual_terco, media_variaveis_ferias,
    )

    # --- Férias proporcionais (perdidas na justa causa — art. 146, § único, CLT)
    meses_ferias_proporcionais = 0
    ferias_proporcionais = {
        "valor_ferias": 0.0, "valor_terco_constitucional": 0.0, "valor_abono": 0.0, "valor_total": 0.0,
        # Mesmas chaves de `calcular_ferias` mesmo no caso zerado (justa
        # causa): o consumidor do dict — recibo, tela, teste — não deveria
        # precisar saber que este ramo devolve um dicionário mais pobre.
        "salario_base": round(salario_base, 2), "media_variaveis": 0.0,
        "base_calculo": round(salario_base, 2),
    }
    if tipo_rescisao != "justa_causa":
        inicio_periodo_aquisitivo = inicio_periodo_aquisitivo_atual(data_admissao, data_referencia)
        meses_ferias_proporcionais = meses_regra_15_dias(inicio_periodo_aquisitivo, data_referencia, limite=12)
        dias_equivalentes = round(30 / 12 * meses_ferias_proporcionais, 4)
        ferias_proporcionais = calcular_ferias(
            salario_base, dias_equivalentes, 0, percentual_terco, media_variaveis_ferias,
        )

    # --- 13º proporcional (perdido na justa causa — Lei 4.090/62, art. 3º) ---
    meses_decimo_terceiro = 0
    valor_decimo_terceiro_proporcional = 0.0
    if tipo_rescisao != "justa_causa":
        inicio_ano = date(data_referencia.year, 1, 1)
        inicio_contagem_ano = max(data_admissao, inicio_ano)
        meses_decimo_terceiro = meses_regra_15_dias(inicio_contagem_ano, data_referencia, limite=12)
        valor_decimo_terceiro_proporcional = calcular_decimo_terceiro(
            salario_base, meses_decimo_terceiro, media_variaveis_decimo_terceiro,
        )

    # --- Multa do FGTS (ESTIMATIVA — ver docstring) --------------------------
    percentual_multa_fgts = {
        "sem_justa_causa": 0.40,
        "acordo_mutuo": 0.20,
        "pedido_demissao": 0.0,
        "justa_causa": 0.0,
    }[tipo_rescisao]
    percentual_saque_fgts_permitido = {
        "sem_justa_causa": 1.0,
        "acordo_mutuo": 0.80,
        "pedido_demissao": 0.0,
        "justa_causa": 0.0,
    }[tipo_rescisao]
    meses_de_casa_estimados = meses_regra_15_dias(data_admissao, data_referencia, limite=None)
    deposito_fgts_estimado = round(salario_base * percentual_estimado_fgts_mensal * meses_de_casa_estimados, 2)
    multa_fgts = round(deposito_fgts_estimado * percentual_multa_fgts, 2)

    valor_ferias_proporcionais_total = ferias_proporcionais["valor_total"]
    valor_total = round(
        saldo_salario
        + valor_aviso_previo
        + ferias_vencidas["valor_total"]
        + valor_ferias_proporcionais_total
        + valor_decimo_terceiro_proporcional
        + multa_fgts,
        2,
    )

    return {
        "tipo_rescisao": tipo_rescisao,
        "saldo_salario": {"dias_trabalhados_mes": dias_trabalhados_no_mes, "valor": saldo_salario},
        "aviso_previo": {
            "devido": devido_aviso_previo,
            "dias": dias_aviso_previo if devido_aviso_previo else 0,
            "dias_indenizados": dias_aviso_indenizados,
            "trabalhado": aviso_previo_trabalhado,
            "valor": valor_aviso_previo,
        },
        "ferias_vencidas": ferias_vencidas,
        "ferias_proporcionais": {**ferias_proporcionais, "meses": meses_ferias_proporcionais},
        # Sem `media_variaveis`/`base_calculo` aqui de propósito: quem quer
        # saber quanto de média entrou em cada verba lê `medias_variaveis`
        # abaixo, que é o lugar único das três. Repetir a informação dentro de
        # cada sub-dicionário só multiplicaria os pontos a manter em acordo.
        "decimo_terceiro_proporcional": {"meses": meses_decimo_terceiro, "valor": valor_decimo_terceiro_proporcional},
        "fgts": {
            "estimativa": True,
            "percentual_mensal_estimado": percentual_estimado_fgts_mensal,
            "meses_considerados": meses_de_casa_estimados,
            "deposito_total_estimado": deposito_fgts_estimado,
            "percentual_multa": percentual_multa_fgts,
            "multa": multa_fgts,
            "percentual_saque_permitido": percentual_saque_fgts_permitido,
        },
        # As três médias juntas, para a tela e o TRCT poderem mostrar num
        # lugar só o que entrou além do salário-base — e para o dono conferir
        # que a média do 13º NÃO é a das férias (janelas diferentes, arts.
        # diferentes; ver a docstring).
        "medias_variaveis": {
            "decimo_terceiro": round(media_variaveis_decimo_terceiro, 2),
            "ferias": round(media_variaveis_ferias, 2),
            "aviso_previo": round(media_variaveis_aviso_previo, 2),
            "alguma": bool(
                media_variaveis_decimo_terceiro or media_variaveis_ferias or media_variaveis_aviso_previo
            ),
        },
        "data_referencia_tempo_servico": data_referencia,
        "valor_total": valor_total,
    }
