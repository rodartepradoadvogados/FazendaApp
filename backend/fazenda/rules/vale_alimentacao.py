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

`diario` multiplica o valor-base pelos dias da competência do BENEFÍCIO, e a
contagem é a que a folha JÁ usa (`holerite.dias_da_competencia`, extraída de
`_proporcional_admissao`): dias corridos do mês, reduzidos no mês de admissão
para os dias a partir da admissão. Não há contagem nova aqui — de propósito.
O sistema não tem registro de faltas nem de jornada para quem está na folha
(`DiariaDia` é do diarista, que não entra em folha), então um "por dia útil"
ou "por dia efetivamente trabalhado" seria um número inventado. Fica
registrado como limite consciente: se o dono quiser VA por dia útil, o
caminho é passar a registrar os dias, não chutar 22.

────────────────────────────────────────────────────────────────────────────
ENQUADRAMENTO — "o resto é padrão"
────────────────────────────────────────────────────────────────────────────
Padrão do PAT: INDENIZATÓRIO, fora das bases de INSS, IRRF e FGTS (CLT, art.
457, §2º; Lei 14.442/2022). Não existe campo de forma de pagamento porque o
dono decidiu que não precisa. A ressalva fica escrita, aqui e em
`models/pessoal.py`, para o próximo leitor não achar que foi descuido: vale-
alimentação pago EM DINHEIRO tem natureza SALARIAL e integraria as três
bases — quem pagar em dinheiro estará com a base subdeclarada por este
sistema.

Funções puras, sem I/O: quem chama carrega a `Pessoa` e passa. A gravação da
linha (e a recusa em folha paga) mora em `rh_folha.py`.
"""
from __future__ import annotations

from fazenda.rules import holerite
from fazenda.rules.rubrica_folha import competencia_seguinte

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


def calcular(pessoa, competencia_folha: str) -> dict | None:
    """
    O vale-alimentação desta pessoa NESTA folha, ou None quando não há linha
    a gerar (benefício desligado, ou ligado sem valor-base).

    Devolve tudo o que a linha precisa dizer no papel — o valor, a competência
    do benefício, a periodicidade e, no diário, a conta que produziu o valor
    (valor-base × dias). Nada disso é deduzido depois pela tela: o recibo é
    prova e cada número dele tem de vir com a explicação junto.

    `pessoa.data_admissao` entra na conta do DIÁRIO porque a contagem de dias
    reusada é a mesma da folha (`holerite.dias_da_competencia`) — e ela é
    proporcional no mês de admissão. O mensal ignora isso de propósito: o dono
    disse "se mensal, é o valor cheio".
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

    dias: int | None = None
    dias_mes: int | None = None
    if periodicidade == PERIODICIDADE_DIARIA:
        dias, dias_mes = holerite.dias_da_competencia(
            competencia, getattr(pessoa, "data_admissao", None),
        )
        # Admissão depois do fim da competência do benefício (só alcançável no
        # regime antecipado, em que a folha olha para o mês seguinte): sem dia
        # nenhum, não há benefício a pagar.
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
    }


def descricao(calculo: dict) -> str:
    """
    A composição da linha em uma frase — de onde o valor veio e de que mês ele
    é. Vai gravada em `FolhaRubrica.descricao` e o holerite a mostra na coluna
    REFERÊNCIA (ver `rubrica_folha.referencia_rubrica`), não colada no rótulo:
    numa rubrica gerada pelo cadastro, o "texto livre do usuário" é justamente
    a explicação do número, e o lugar da explicação é a Referência.

    Exemplos:
      "Mensal · competência 07/2026 (vencido)"
      "Diário · R$ 25,00 × 31 dias · competência 08/2026 (antecipado)"
    """
    if calculo["periodicidade"] == PERIODICIDADE_DIARIA:
        base = (
            f"Diário · {_brl(calculo['valor_base'])} × {calculo['dias']} "
            f"{'dia' if calculo['dias'] == 1 else 'dias'}"
        )
    else:
        base = "Mensal"
    return f"{base} · competência {_competencia_extenso(calculo['competencia_beneficio'])} ({calculo['regime']})"
