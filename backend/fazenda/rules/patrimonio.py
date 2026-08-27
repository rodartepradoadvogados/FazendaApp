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


# ---------------------------------------------------------------------------
# Onda 2 — LISTAS FECHADAS do cadastro.
#
# Até aqui `tipo`, `metodo_depreciacao` e `unidade` eram texto livre vindo do
# CSV do Ideagri, e cada upload trazia uma grafia diferente da mesma coisa
# ("Trator"/"TRATOR"/"trator "). Texto livre em campo que ALIMENTA CÁLCULO é
# a origem da classe de bug da Onda 1 (a vida útil "10 anos e 6 meses" lida
# como 0,83 ano): o sistema tem que adivinhar o que o usuário quis dizer.
# Fechar a lista elimina a adivinhação na origem.
#
# O dado legado NÃO é rejeitado: o que já está no banco continua sendo lido e
# exibido tal como está; a lista fechada vale para o que entra a partir de
# agora (formulário) e para o casamento por normalização na importação.
# ---------------------------------------------------------------------------

# Tipos de bem. Os três primeiros são os não-depreciáveis (TIPOS_NAO_DEPRECIAVEIS
# acima) — mantidos aqui na mesma ordem em que aparecem no formulário.
TIPOS_PATRIMONIO: tuple[str, ...] = (
    "Terra",
    "Fazenda",
    "Terreno",
    "Benfeitoria",
    "Construção",
    "Máquina",
    "Trator",
    "Implemento",
    "Veículo",
    "Equipamento",
    "Instalação",
    "Móveis e utensílios",
    "Informática",
    "Animal de trabalho",
    "Animal reprodutor",
    "Cultura permanente",
    "Outro",
)

# Unidades de medida do item. "un" cobre o caso mais comum (1 trator);
# as demais existem para lotes (50 matrizes, 12 ha de lavoura).
UNIDADES_PATRIMONIO: tuple[str, ...] = ("un", "cab", "ha", "m²", "m", "km", "conjunto", "lote")

# ---------------------------------------------------------------------------
# Os 4 métodos de depreciação.
#
# Chave (guardada em Patrimonio.metodo_depreciacao) -> rótulo exibido.
# LINEAR é o default e o comportamento histórico: item sem método cadastrado
# (todo o legado) deprecia linear, exatamente como antes desta onda.
# ---------------------------------------------------------------------------
LINEAR = "LINEAR"
SALDO_DECRESCENTE = "SALDO_DECRESCENTE"
SOMA_DIGITOS = "SOMA_DIGITOS"
UNIDADES_PRODUZIDAS = "UNIDADES_PRODUZIDAS"

METODOS_DEPRECIACAO: tuple[tuple[str, str, str], ...] = (
    (
        LINEAR,
        "Linear (quotas constantes)",
        "Mesma parcela todo mês. É o método da Receita Federal (IN 1700/2017) e "
        "o padrão para quase todo bem de fazenda.",
    ),
    (
        SALDO_DECRESCENTE,
        "Saldo decrescente (acelerada)",
        "Deprecia mais no começo e menos no fim, aplicando uma taxa fixa sobre o "
        "saldo que ainda resta. Para bem que perde valor rápido nos primeiros anos "
        "(veículo, informática).",
    ),
    (
        SOMA_DIGITOS,
        "Soma dos dígitos (acelerada)",
        "Também deprecia mais no começo, mas em parcelas que caem em linha reta e "
        "zeram exatamente no fim da vida útil.",
    ),
    (
        UNIDADES_PRODUZIDAS,
        "Unidades produzidas (por uso)",
        "Deprecia pelo USO, não pelo tempo: você informa o total que o bem produz "
        "na vida inteira (horas, km, fardos) e quanto já foi consumido. Um trator "
        "parado não deprecia neste método.",
    ),
)

METODOS_VALIDOS: tuple[str, ...] = tuple(chave for chave, _r, _d in METODOS_DEPRECIACAO)

# Multiplicador padrão do saldo decrescente. 2 = "saldo decrescente em
# dobro" (double declining balance), a convenção mais usada; o usuário pode
# sobrescrever por item (Patrimonio.fator_saldo_decrescente).
FATOR_SALDO_DECRESCENTE_PADRAO = 2.0


def metodo_normalizado(metodo: str | None) -> str:
    """Método do item, sempre um dos METODOS_VALIDOS. Vazio/desconhecido cai
    em LINEAR — é o comportamento histórico (o campo era texto livre e nunca
    foi lido pelo cálculo; todo item existente deprecia linear hoje), então
    o default preserva o número que o usuário já vê na tela.

    Aceita também o rótulo por extenso que o CSV legado possa trazer
    ("Linear", "linha reta") — normalizando, não adivinhando: só casa com
    grafia que corresponda de fato a um método conhecido."""
    if not metodo:
        return LINEAR
    bruto = _normalizar(metodo)
    if bruto in {_normalizar(chave) for chave in METODOS_VALIDOS}:
        return next(c for c in METODOS_VALIDOS if _normalizar(c) == bruto)
    apelidos = {
        "linear": LINEAR, "linha reta": LINEAR, "quotas constantes": LINEAR, "constante": LINEAR,
        "saldo decrescente": SALDO_DECRESCENTE, "acelerada": SALDO_DECRESCENTE,
        "decrescente": SALDO_DECRESCENTE, "saldo decrescente em dobro": SALDO_DECRESCENTE,
        "soma dos digitos": SOMA_DIGITOS, "soma de digitos": SOMA_DIGITOS, "digitos": SOMA_DIGITOS,
        "unidades produzidas": UNIDADES_PRODUZIDAS, "unidades": UNIDADES_PRODUZIDAS,
        "por uso": UNIDADES_PRODUZIDAS, "horas": UNIDADES_PRODUZIDAS,
    }
    return apelidos.get(bruto, LINEAR)


# ---------------------------------------------------------------------------
# Motivos de baixa (Onda 2).
#
# `data_baixa` sozinha dizia QUANDO o bem saiu, nunca POR QUÊ nem POR QUANTO —
# e sem o valor de venda não há como apurar ganho/perda de capital, que é
# resultado do exercício e precisa chegar na DRE (linha OUTRAS_REC_DESP).
#
# (chave, rótulo, tem_valor_de_venda)
# ---------------------------------------------------------------------------
MOTIVOS_BAIXA: tuple[tuple[str, str, bool], ...] = (
    ("VENDA", "Venda", True),
    ("PERDA", "Perda ou sinistro", False),
    ("SUCATEAMENTO", "Sucateamento / fim de vida útil", False),
    ("DOACAO", "Doação", False),
    ("TRANSFERENCIA", "Transferência para outra fazenda", False),
)

MOTIVOS_BAIXA_VALIDOS: tuple[str, ...] = tuple(chave for chave, _r, _v in MOTIVOS_BAIXA)
MOTIVOS_BAIXA_COM_VENDA: frozenset[str] = frozenset(
    chave for chave, _r, tem_valor in MOTIVOS_BAIXA if tem_valor
)


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



def vida_util_em_anos(item: dict) -> float | None:
    """Vida útil TOTAL do item em anos, na ordem de precedência da Onda 2:

    1. Campos ESTRUTURADOS (`vida_util_anos` + `vida_util_meses`), preenchidos
       pelos steppers do formulário novo. Não há o que interpretar — 10 anos
       e 6 meses são 10,5 anos, ponto.
    2. Texto livre (`vida_util`), o campo legado — todo item importado do CSV
       antes desta onda só tem isso. Cai no parser tolerante
       `_vida_util_em_anos`, que continua existindo exatamente para reler
       esse dado histórico.

    A precedência é essa e não a inversa: quando o usuário abre um item
    legado e salva pelo formulário novo, os campos estruturados passam a
    existir e viram a verdade; o texto antigo fica no registro como
    procedência, mas não manda mais no cálculo."""
    anos = item.get("vida_util_anos")
    meses = item.get("vida_util_meses")
    if anos is not None or meses is not None:
        total = (anos or 0) + (meses or 0) / 12
        if total <= 0 or total > VIDA_UTIL_MAX_ANOS:
            return None
        return total
    return _vida_util_em_anos(item.get("vida_util"))


def _acumulada_linear(depreciavel: float, vida_util_meses: float, meses: int) -> float:
    """Quotas constantes: mesma parcela todo mês."""
    if vida_util_meses <= 0:
        return 0.0
    return min(depreciavel / vida_util_meses * meses, depreciavel)


def _acumulada_saldo_decrescente(
    valor_base: float, valor_residual: float, vida_util_meses: float, meses: int, fator: float
) -> float:
    """Saldo decrescente: taxa fixa aplicada sobre o SALDO CONTÁBIL que ainda
    resta, não sobre a base — por isso a parcela encolhe todo mês e o método
    concentra depreciação no início.

    Forma fechada de aplicar a taxa mensal `t` por `m` meses:
        saldo = base * (1 - t)^m
    A depreciação acumulada é a diferença entre a base e esse saldo, com piso
    no valor residual: o método por natureza NUNCA zera sozinho (a curva é
    assintótica), então sem esse piso ele depreciaria abaixo do residual e,
    no limite, até abaixo de zero."""
    if vida_util_meses <= 0:
        return 0.0
    taxa_mensal = fator / vida_util_meses
    if taxa_mensal >= 1:
        # Vida útil curta demais para o fator (ex.: 6 meses com fator 2 dá
        # taxa >= 1): o bem iria a zero no primeiro mês e o expoente abaixo
        # ficaria negativo. Deprecia tudo de uma vez, com o mesmo teto.
        return max(valor_base - valor_residual, 0.0) if meses >= 1 else 0.0
    saldo = valor_base * ((1 - taxa_mensal) ** meses)
    saldo_minimo = valor_residual
    return max(valor_base - max(saldo, saldo_minimo), 0.0)


def _acumulada_soma_digitos(depreciavel: float, vida_util_meses: int, meses: int) -> float:
    """Soma dos dígitos: no mês k de uma vida útil de n meses, a parcela é
    (n - k + 1) / (1+2+...+n) da base depreciável — cai em linha reta e zera
    exatamente no fim da vida útil (diferente do saldo decrescente, que nunca
    zera sozinho).

    Acumulada até o mês m, somando as parcelas de k=1 até m e simplificando:
        [n(n+1) - (n-m)(n-m+1)] / [n(n+1)]
    """
    n = int(vida_util_meses)
    if n <= 0:
        return 0.0
    m = min(int(meses), n)
    if m <= 0:
        return 0.0
    restante = n - m
    fracao = (n * (n + 1) - restante * (restante + 1)) / (n * (n + 1))
    return min(depreciavel * fracao, depreciavel)


def _acumulada_unidades(depreciavel: float, total_unidades: float | None, consumidas: float | None) -> float:
    """Unidades produzidas: deprecia por USO, não por tempo. Um trator parado
    o ano inteiro não deprecia neste método — é a diferença essencial em
    relação aos outros três, e a razão de ele não olhar data nenhuma."""
    if not total_unidades or total_unidades <= 0:
        return 0.0
    usadas = max(consumidas or 0.0, 0.0)
    return min(depreciavel * (usadas / total_unidades), depreciavel)


def _acumulada_por_metodo(
    metodo: str, valor_base: float, valor_residual: float, vida_util_anos: float,
    data_imob: date, referencia: date, item: dict,
) -> float:
    """Despacho único dos 4 métodos — todo cálculo de depreciação acumulada
    do sistema passa por aqui, para que nenhum ponto reimplemente a fórmula
    de um método (foi assim que a Onda 1 acumulou 10 divergências)."""
    depreciavel = max(valor_base - valor_residual, 0.0)
    vida_util_meses = vida_util_anos * 12

    if metodo == UNIDADES_PRODUZIDAS:
        return _acumulada_unidades(
            depreciavel, item.get("unidades_vida_util_total"), item.get("unidades_consumidas")
        )

    meses = meses_cheios(data_imob, referencia)
    if metodo == SALDO_DECRESCENTE:
        fator = item.get("fator_saldo_decrescente") or FATOR_SALDO_DECRESCENTE_PADRAO
        return _acumulada_saldo_decrescente(valor_base, valor_residual, vida_util_meses, meses, fator)
    if metodo == SOMA_DIGITOS:
        return _acumulada_soma_digitos(depreciavel, round(vida_util_meses), meses)
    return _acumulada_linear(depreciavel, vida_util_meses, meses)


def resultado_baixa(item: dict, hoje: date | None = None) -> dict | None:
    """Ganho ou perda de capital da baixa de um bem — None para item que não
    foi baixado.

        resultado = valor recebido na venda - valor contábil na data da baixa

    Positivo = ganho de capital (vendeu por mais do que valia nos livros);
    negativo = perda. Nos motivos SEM venda (perda, sucateamento, doação,
    transferência) o valor recebido é zero e o resultado é a perda do valor
    contábil que ainda restava.

    Este número é resultado do exercício e pertence à linha OUTRAS RECEITAS E
    DESPESAS da DRE (ver rules/dre.py) — não é receita de vendas (não é a
    atividade-fim da fazenda) nem depreciação (que é o desgaste ao longo do
    uso, não o acerto de contas do momento da saída)."""
    data_baixa = item.get("data_baixa")
    if not data_baixa:
        return None

    calculo = calcular_depreciacao(item, hoje=hoje)
    valor_base = valor_base_aquisicao(item)
    acumulada = calculo.get("depreciacao_acumulada")
    # Cadastro incompleto (sem vida útil/data): não dá para dizer quanto o bem
    # já havia depreciado, então o valor contábil é a própria base. O
    # resultado sai mesmo assim — é melhor do que esconder a baixa do
    # usuário —, sinalizado por `estimado` para a tela poder avisar.
    estimado = acumulada is None
    valor_contabil = valor_base - (acumulada or 0.0)

    motivo = (item.get("motivo_baixa") or "").upper()
    tem_venda = motivo in MOTIVOS_BAIXA_COM_VENDA
    valor_recebido = (item.get("valor_baixa") or 0.0) if tem_venda else 0.0

    return {
        "motivo": motivo or None,
        "data_baixa": data_baixa,
        "valor_recebido": round(valor_recebido, 2),
        "valor_contabil": round(valor_contabil, 2),
        "resultado": round(valor_recebido - valor_contabil, 2),
        "estimado": estimado,
    }

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
    valor_base: float, valor_residual: float, vida_util_anos: float, data_imob: date,
    referencia: date, item: dict | None = None,
) -> float:
    """Depreciação acumulada até `referencia` (hoje, para um item em operação,
    ou a data_baixa, para um já baixado), pelo MÉTODO cadastrado no item —
    ver `_acumulada_por_metodo` para os 4. Sempre com teto no valor
    depreciável (nenhum método deprecia abaixo do residual).

    `item` opcional só para não quebrar chamador antigo que passava apenas os
    números soltos: sem ele, LINEAR — que é o comportamento histórico."""
    return _acumulada_por_metodo(
        metodo_normalizado((item or {}).get("metodo_depreciacao")),
        valor_base, valor_residual, vida_util_anos, data_imob, referencia, item or {},
    )


def calcular_depreciacao(item: dict, hoje: date | None = None) -> dict:
    """Recebe um dict com os campos do Patrimonio (model_dump()) e devolve
    depreciacao_acumulada, valor_atual, vida_util_anos e uma eventual
    inconsistência (vida útil não reconhecida ou sem data de imobilização)."""
    hoje = hoje or date.today()
    valor_base = valor_base_aquisicao(item)
    valor_residual = item.get("valor_residual") or 0.0
    data_imob = item.get("data_imobilizacao")
    vida_util_anos = vida_util_em_anos(item)

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
        acumulada = _depreciacao_ate(valor_base, valor_residual, vida_util_anos, data_imob, data_baixa, item)
        return {
            "depreciacao_acumulada": round(acumulada, 2),
            "valor_atual": round(valor_base - acumulada, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": None,
        }

    acumulada = _depreciacao_ate(valor_base, valor_residual, vida_util_anos, data_imob, hoje, item)
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
