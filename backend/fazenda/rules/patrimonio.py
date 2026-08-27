"""
Depreciação e manutenção preventiva do patrimônio.

Depreciação: linha reta (linear), a partir da vida útil cadastrada (texto
livre, ex. "7 Anos" ou "60 Meses"), da data de imobilização e do valor
residual. Quando a vida útil não pode ser interpretada (ou falta a data de
imobilização), o item entra na resposta sem depreciação e com um aviso — não
trava o cálculo dos demais itens.

IMPORTANTE — não confundir com financiamento: depreciação é despesa
CONTÁBIL (desgaste do bem ao longo da vida útil), nunca saída de caixa. O
principal de um financiamento é o oposto: saída de caixa, nunca despesa
contábil. As duas coisas não se misturam em lugar nenhum deste módulo.

Manutenção preventiva: plano OPCIONAL por item, só por periodicidade de DATA
(ex.: "a cada 6 meses"). Avaliamos cadastrar também por horas/uso, mas o
sistema não rastreia horímetro nem horas de uso de nenhum equipamento hoje —
não há de onde puxar esse dado sem inventar um cadastro novo inteiro (sensor,
lançamento manual de horas etc.), o que é escopo maior do que "manutenção
preventiva" pede agora. Por isso o plano por data cobre o caso de uso
imediato (troca de óleo semestral, revisão anual...) e fica mais simples e
viável; manutenção por uso pode ser adicionada depois como um campo a mais
sem quebrar o que já existe.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date


def _normalizar(texto: str) -> str:
    """Sem acento e minúsculo — o CSV do Ideagri vem em windows-1252 e a
    grafia do tipo varia entre uploads/usuários (ex.: "Terra", "TERRA",
    "Térreo"); comparar bruto perderia casos."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


# Tipos que NUNCA depreciam — só valorizam (ver Patrimonio.depreciavel).
# Terra não sofre desgaste físico com o uso/tempo, então não há "vida útil"
# a consumir: é o consenso contábil (CPC 27 — Ativo Imobilizado) e a própria
# IN RFB 1700/2017, que lista uma taxa de depreciação anual para cada tipo
# de bem, não atribui NENHUMA taxa a terrenos/terras — exatamente porque a
# Receita também não reconhece depreciação para eles. "Fazenda" e "Terreno"
# são grafias comuns do mesmo conceito no cadastro do cliente.
TIPOS_NAO_DEPRECIAVEIS = {"terra", "fazenda", "terreno"}


def eh_tipo_nao_depreciavel(tipo: str | None) -> bool:
    """True quando o TIPO do item (ex.: "Terra") indica um bem que não
    deprecia — usado pelo parser do CSV para inferir `Patrimonio.depreciavel`
    (o CSV não traz essa coluna) e por qualquer outro ponto que precise da
    mesma regra, em vez de cada um duplicar a comparação de texto."""
    if not tipo:
        return False
    return _normalizar(tipo) in TIPOS_NAO_DEPRECIAVEIS


# Vida útil "solta" (só um número, sem unidade) acima disso é claramente erro
# de digitação/cadastro (ex.: ano de fabricação digitado no campo errado) —
# rejeitamos como inconsistência em vez de aceitar um número absurdo em
# silêncio.
VIDA_UTIL_MAX_ANOS = 100

_RE_ANOS_E_MESES = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*anos?(?:\s*e\s*(\d+(?:[.,]\d+)?)\s*m[eê]s(?:es)?)?", re.IGNORECASE
)
_RE_SO_MESES = re.compile(r"(\d+(?:[.,]\d+)?)\s*m[eê]s(?:es)?", re.IGNORECASE)
_RE_NUMERO = re.compile(r"(\d+(?:[.,]\d+)?)")


def _vida_util_em_anos(texto: str | None) -> float | None:
    """Interpreta o texto livre da vida útil (ex.: "7 Anos", "60 Meses",
    "10 anos e 6 meses") e devolve o total em anos. None quando o texto não
    tem padrão reconhecível OU quando o valor interpretado é implausível
    (<=0 ou > 100 anos) — nos dois casos o chamador (calcular_depreciacao)
    gera uma inconsistência explícita em vez de aceitar um número claramente
    errado em silêncio (a versão antiga desta função pegava só o primeiro
    número do texto e dividia por 12 se a palavra "mês" aparecesse EM
    QUALQUER LUGAR do texto — "10 anos e 6 meses" virava 10/12 = 0,83 ano em
    vez de 10,5).

    Sem NENHUMA unidade no texto (só um número, ex.: "60"), assume-se ANOS —
    é a unidade que o próprio formulário anuncia (placeholder "ex.: 10
    Anos"). Quem cadastrou pensando em meses (ex.: "60" querendo dizer 60
    meses) cai nessa mesma ambiguidade e precisa corrigir manualmente; não há
    como diferenciar só pelo texto. A correção definitiva é a da Onda 2, que
    troca este texto livre por um stepper numérico já em anos — até lá,
    porém, este parser continua necessário para reler o que já foi
    importado (dado legado)."""
    if not texto or not texto.strip():
        return None
    t = texto.strip()

    m = _RE_ANOS_E_MESES.search(t)
    if m:
        anos = float(m.group(1).replace(",", "."))
        meses = float(m.group(2).replace(",", ".")) if m.group(2) else 0.0
        valor = anos + meses / 12
    else:
        m_meses = _RE_SO_MESES.search(t)
        if m_meses:
            valor = float(m_meses.group(1).replace(",", ".")) / 12
        else:
            m_num = _RE_NUMERO.search(t)
            if not m_num:
                return None
            valor = float(m_num.group(1).replace(",", "."))

    if valor <= 0 or valor > VIDA_UTIL_MAX_ANOS:
        return None
    return valor


def valor_base_aquisicao(item: dict) -> float:
    """Base de valor do item para QUALQUER cálculo (depreciação, valor de
    mercado inicial, KPIs de listagem) — nenhum lugar deve ler `valor_total`
    cru fora daqui, senão a regra abaixo fica duplicada (e sujeita a
    divergir) em cada ponto que usa o valor do item.

    `valor_por_unidade=False` (padrão — é o comportamento histórico, de
    antes deste campo existir): `valor_total` JÁ é o valor do lote inteiro.
    `valor_por_unidade=True`: `valor_total` é o valor de UMA unidade, e a
    base é `valor_total * quantidade` (ex.: 50 vacas a R$ 3.000 cada = base
    de R$ 150.000) — sem quantidade cadastrada, não há como multiplicar, e a
    base cai para o próprio valor_total (fazer diferente travaria o cálculo
    por causa de um campo opcional não preenchido)."""
    valor_total = item.get("valor_total") or 0.0
    if item.get("valor_por_unidade") and item.get("quantidade"):
        return valor_total * item["quantidade"]
    return valor_total


def meses_cheios(inicio: date, referencia: date) -> int:
    """Quantidade de meses CHEIOS entre `inicio` e `referencia`, na convenção
    contábil brasileira de depreciação: o mês de entrada em operação conta
    inteiro (não é rateado pelo dia do mês — comprar no dia 20 já conta o
    mês inteiro), e o mês corrente só é somado quando ele FECHA (chega ao
    último dia). Substitui a conta antiga em dias corridos / 365,25 (ver ADR
    na Onda 1), que não seguia essa convenção."""
    if referencia < inicio:
        return 0
    diferenca = (referencia.year - inicio.year) * 12 + (referencia.month - inicio.month)
    if diferenca == 0:
        # Mesmo mês da imobilização: conta como o 1º mês cheio, mesmo que o
        # mês ainda não tenha fechado — é a exceção "entrada conta inteira".
        return 1
    ultimo_dia_mes_referencia = calendar.monthrange(referencia.year, referencia.month)[1]
    fechou = referencia.day >= ultimo_dia_mes_referencia
    return diferenca + (1 if fechou else 0)


def _depreciacao_ate(
    valor_base: float, valor_residual: float, vida_util_anos: float, data_imob: date, referencia: date
) -> float:
    """Depreciação acumulada linear até `referencia` (hoje, para um item em
    operação, ou a data_baixa, para um já baixado) — meses cheios (ver
    `meses_cheios`) x depreciação mensal, com teto no valor depreciável (não
    deprecia abaixo do residual)."""
    depreciavel = max(valor_base - valor_residual, 0.0)
    vida_util_meses = vida_util_anos * 12
    dep_mensal = depreciavel / vida_util_meses if vida_util_meses else 0.0
    meses = meses_cheios(data_imob, referencia)
    return min(dep_mensal * meses, depreciavel)


def calcular_depreciacao(item: dict, hoje: date | None = None) -> dict:
    """Recebe um dict com os campos do Patrimonio (model_dump()) e devolve
    depreciacao_acumulada, valor_atual, vida_util_anos e uma eventual
    inconsistência (vida útil não reconhecida ou sem data de imobilização)."""
    hoje = hoje or date.today()
    valor_base = valor_base_aquisicao(item)
    valor_residual = item.get("valor_residual") or 0.0
    data_imob = item.get("data_imobilizacao")
    vida_util_anos = _vida_util_em_anos(item.get("vida_util"))

    if item.get("depreciavel") is False:
        # Só valoriza (ex.: terra/fazenda) — nunca deprecia; o "valor atual" é
        # o valor de mercado mais recente informado, ou o valor de aquisição
        # enquanto nenhuma atualização foi feita ainda. Nunca gera inconsistência
        # por falta de vida útil/data de imobilização — não se aplica aqui.
        valor_mercado = item.get("valor_mercado_atual")
        return {
            "depreciacao_acumulada": None,
            "valor_atual": round(valor_mercado if valor_mercado is not None else valor_base, 2),
            "vida_util_anos": None,
            "inconsistencia": None,
        }
    data_baixa = item.get("data_baixa")
    # Bem já baixado com cadastro incompleto: NÃO cobra correção. Ele está
    # fora do ativo (não entra em nenhum total — ver listar_patrimonio) e
    # exigir vida útil de um trator já vendido só produziria ruído na tela de
    # inconsistências, que existe para apontar o que ainda dá para consertar.
    # Bem baixado COM cadastro completo continua sendo calculado normalmente
    # (proporcional até a data da baixa, mais abaixo) — o histórico correto
    # importa para o resultado do exercício em que a baixa aconteceu.
    cadastro_incompleto = not data_imob or not vida_util_anos or vida_util_anos <= 0 or valor_residual > valor_base
    if data_baixa and cadastro_incompleto:
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_base, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": None,
        }
    if not data_imob:
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_base, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": "Sem data de imobilização — não é possível calcular a depreciação.",
        }
    if valor_residual > valor_base:
        # Cadastro incoerente (ex.: valor residual maior que o valor do bem)
        # — sem esta checagem a base depreciável vira 0 e o item passava
        # 100% silencioso como "sem depreciação", sem nenhum aviso na tela.
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_base, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": (
                f"Valor residual (R$ {valor_residual:,.2f}) maior que o valor do bem "
                f"(R$ {valor_base:,.2f}) — corrija um dos dois."
            ),
        }
    if not vida_util_anos or vida_util_anos <= 0:
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_base, 2),
            "vida_util_anos": None,
            "inconsistencia": f'Vida útil "{item.get("vida_util") or "—"}" não reconhecida — cadastre um número (ex.: "7 anos").',
        }

    if data_baixa:
        # Já baixado — parou de depreciar na data da baixa. Deprecia
        # proporcionalmente até lá (mesma fórmula do método normal, só
        # trocando "hoje" por `data_baixa`) — depreciar o valor inteiro de
        # uma vez (comportamento antigo) ignorava quando a baixa ocorreu e
        # inflava a despesa de quem baixou o bem ainda no início da vida útil.
        acumulada = _depreciacao_ate(valor_base, valor_residual, vida_util_anos, data_imob, data_baixa)
        return {
            "depreciacao_acumulada": round(acumulada, 2),
            "valor_atual": round(valor_base - acumulada, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": None,
        }

    acumulada = _depreciacao_ate(valor_base, valor_residual, vida_util_anos, data_imob, hoje)
    return {
        "depreciacao_acumulada": round(acumulada, 2),
        "valor_atual": round(valor_base - acumulada, 2),
        "vida_util_anos": vida_util_anos,
        "inconsistencia": None,
    }


DIAS_ALERTA_MANUTENCAO_PROXIMA = 15  # "perto de vencer" — mesma janela usada no front para destacar


def somar_meses(base: date, meses: int) -> date:
    """Soma `meses` a `base`, ajustando o dia quando o mês de destino é mais
    curto (ex.: 31/01 + 1 mês = 28 ou 29/02) — mesma lógica de
    `agenda._proxima_ocorrencia`, duplicada aqui para manter esta regra sem
    depender do router de agenda."""
    mes_total = base.month - 1 + meses
    ano = base.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def status_manutencao(item: dict, hoje: date | None = None) -> dict:
    """Recebe um dict com os campos de manutenção do Patrimonio (model_dump())
    e devolve a situação do plano preventivo: None quando não há plano
    cadastrado (sem data_proxima_manutencao), ou "vencida"/"proxima"/"ok" a
    partir de quantos dias faltam para a próxima manutenção. Item já baixado
    nunca alerta — não faz sentido agendar manutenção de bem baixado."""
    hoje = hoje or date.today()
    prox = item.get("data_proxima_manutencao")
    if not prox or item.get("data_baixa"):
        return {"situacao_manutencao": None, "dias_para_manutencao": None}
    dias = (prox - hoje).days
    if dias < 0:
        situacao = "vencida"
    elif dias <= DIAS_ALERTA_MANUTENCAO_PROXIMA:
        situacao = "proxima"
    else:
        situacao = "ok"
    return {"situacao_manutencao": situacao, "dias_para_manutencao": dias}


def proxima_atualizacao_valor_mercado(item: dict, frequencia_padrao_meses: int) -> date | None:
    """Data da próxima pendência de "atualizar valor de mercado" (Agenda) —
    só para patrimônio não depreciável (ver Patrimonio.depreciavel). None =
    nunca gera pendência: item deprecia normalmente, já foi baixado, ou a
    frequência (própria do item ou o padrão do sistema) é 0 ("nunca").

    frequencia_meses do PRÓPRIO item, quando preenchida, vence a do sistema
    (override por item) — 0 é "nunca" mesmo que o padrão do sistema não seja."""
    if item.get("depreciavel") is not False or item.get("data_baixa"):
        return None
    frequencia = item.get("atualizacao_valor_mercado_frequencia_meses")
    if frequencia is None:
        frequencia = frequencia_padrao_meses
    if not frequencia:
        return None
    base = item.get("data_ultima_atualizacao_valor_mercado") or item.get("data_imobilizacao")
    if not base:
        return None
    return somar_meses(base, frequencia)
