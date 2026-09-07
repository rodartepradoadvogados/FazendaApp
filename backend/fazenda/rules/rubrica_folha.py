"""
Rubricas avulsas do holerite — o catálogo trabalhista, o regime tributário de
cada uma e as linhas que elas viram no recibo de quatro colunas.

POR QUE O REGIME TRIBUTÁRIO MORA AQUI, E POR RUBRICA. Tratar todas as verbas
igual é o erro que este módulo existe para impedir: um reembolso de R$ 400
somado ao salário bruto aumenta a base de INSS/IRRF/FGTS e faz o funcionário
pagar contribuição sobre dinheiro que é dele (só está sendo devolvido). O
oposto também é erro: uma bonificação por produtividade lançada como
indenizatória tira da base uma verba que a lei manda integrar.

ENQUADRAMENTO ADOTADO (conferido com a skill jurídica do escritório; o
fundamento vai escrito em cada linha do catálogo para o dono poder conferir
com a contabilidade dele):

- `bonificacao_produtividade` — SALARIAL. Gratificação ajustada paga pelo
  empregador em razão do trabalho (CLT, art. 457, §1º): integra a remuneração
  e as bases de INSS, IRRF e FGTS. RESSALVA CONSCIENTE: a Lei 13.467/2017
  criou no art. 457, §§2º e 4º, a figura do PRÊMIO — liberalidade eventual por
  desempenho superior ao ordinariamente esperado — que NÃO integra a
  remuneração. O sistema adota o enquadramento salarial porque é o
  conservador para o empregador (provisiona a mais, nunca a menos) e porque
  bonificação lançada mês a mês na folha é justamente o caso em que a
  habitualidade afasta o §4º. Quando a fazenda tiver parecer da contabilidade
  em sentido contrário, o caminho é acrescentar um código novo ao catálogo —
  nunca reinterpretar este.
- `aumento_folha` — SALARIAL, e é a única que muda o FUTURO: o valor entra
  como vencimento no mês em que é concedido e passa a integrar o salário-base
  a partir da competência seguinte (CLT, art. 468 — alteração benéfica ao
  empregado; salário não retrocede sozinho no mês seguinte).
- `gueltas` — SALARIAL. Valor pago por TERCEIRO (fornecedor/laboratório) ao
  empregado em razão do trabalho prestado ao empregador; a jurisprudência
  trabalhista as trata como parcela remuneratória, no mesmo raciocínio das
  gorjetas (CLT, art. 457, §3º, e Súmula 354 do TST): integram a remuneração
  para 13º, férias e FGTS. Entram nas bases porque são contraprestação do
  trabalho — a origem do dinheiro (terceiro) não muda a natureza.
- `indenizacao` — INDENIZATÓRIA. Repara dano/perda; não é contraprestação de
  trabalho, não integra salário (CLT, art. 457, §2º, e Lei 8.212/91, art. 28,
  §9º, que exclui do salário de contribuição as parcelas indenizatórias).
- `reembolso` — INDENIZATÓRIA. Devolução de despesa do EMPREGADOR adiantada
  pelo empregado (combustível, peça, compra de insumo): mera reposição
  patrimonial, sem acréscimo — não integra salário nem sofre incidência.
- `vale_transporte` — INDENIZATÓRIA, e é o enquadramento mais firme daqui: a
  própria lei do benefício diz que ele "não tem natureza salarial, nem se
  incorpora à remuneração para quaisquer efeitos" e "não constitui base de
  incidência de contribuição previdenciária ou de FGTS" (Lei 7.418/85,
  art. 2º, alíneas "a" e "d"). A cota-parte do empregado tem código PRÓPRIO
  no catálogo de descontos (`desconto_vale_transporte`), porque é desconto e
  não vencimento, e porque o fundamento dela é outro (art. 4º, parágrafo
  único, da mesma lei).

VALE-ALIMENTAÇÃO NÃO ENTRA, e a ausência é deliberada: a natureza dele depende
da FORMA de pagamento — pago em ticket/cartão dentro do PAT é indenizatório
(CLT, art. 457, §2º, e Lei 14.442/2022), pago em DINHEIRO é salarial e integra
as bases. O modelo não tem onde gravar a forma de pagamento de uma rubrica, e
escolher um dos dois enquadramentos por padrão poria a base de INSS/IRRF/FGTS
errada em metade dos casos — ver o relatório do PR.

O QUE ESTE MÓDULO NÃO FAZ: não calcula a tabela progressiva do IRRF nem as
faixas do INSS. O projeto inteiro trabalha com percentual informado pelo
usuário/contador (ver `_calcular_encargo_projetado` e o comentário de
`FolhaPagamento.percentual_fgts`); o que muda aqui é a BASE sobre a qual esse
percentual é aplicado — que é exatamente onde a natureza da rubrica pesa.

Funções puras onde dá; as que precisam de banco recebem `session` e carregam
em lote (ver `rubricas_por_folha`), pelo mesmo motivo de
`_contexto_discriminacao`: montar um holerite não pode custar N consultas.
"""
from __future__ import annotations

from sqlmodel import Session, select

from fazenda.models import ContaGerencial, FolhaRubrica
from fazenda.rules import holerite

NATUREZA_SALARIAL = "salarial"
NATUREZA_INDENIZATORIA = "indenizatoria"

ESPECIE_VENCIMENTO = "vencimento"
ESPECIE_DESCONTO = "desconto"

# ── Quem pode ser alterado NO ATO DO PAGAMENTO, e sob que condição ──
#
# POR QUE ESTE EIXO NÃO É `natureza`, e precisou de campo próprio. O dono
# pediu a coluna de edição do pop-up de pagamento com dois estados: "Editar"
# nos vales, bonificações e vale-transporte; CADEADO no salário, no INSS, no
# IR e "nas demais verbas salariais ou indenizatórias". Só que bonificação
# TEM natureza salarial (art. 457, §1º) e ganha "Editar", enquanto indenização
# e reembolso são indenizatórios e ganham cadeado — ou seja, o eixo que o dono
# enxerga NÃO é o regime tributário que `natureza` grava. É outro:
#
#   LIVRE       → o valor é MEDIDO no mês. Quanto de vale foi descontado,
#                 quanto se bonificou, quantos dias de vale-transporte. Não
#                 existe valor prometido a alterar: editar aqui é dizer o que
#                 aconteceu, não mudar o contrato.
#   CONTRATUAL  → o valor é DETERMINADO pela lei ou pelo contrato (salário,
#                 aumento incorporado, retenções, indenização ajustada,
#                 desconto amarrado a uma compra). Mexer nele vale como
#                 alteração daquele momento em diante (CLT, art. 468) — daí o
#                 cadeado, que não bloqueia: pergunta e deixa passar.
#
# O enquadramento de cada código vai escrito verbete a verbete, e não deduzido
# de outro campo, justamente porque os dois eixos não coincidem — e porque o
# dono precisa poder ler a lista e mudar UMA linha quando discordar.
ALTERACAO_LIVRE = "livre"
ALTERACAO_CONTRATUAL = "contratual"

# As rubricas de vencimento do catálogo, com o enquadramento discutido na
# docstring. `incide_*` é o que decide a BASE de cada tributo — por tributo, e
# não um "tributável: sim/não" único, porque nada garante que uma rubrica
# futura incida nos três (gorjeta, por exemplo, integra a remuneração para
# FGTS mas tem reflexo limitado pela Súmula 354 do TST). `alteracao` é o outro
# eixo, o da edição no ato do pagamento — ver o bloco de constantes acima.
CATALOGO_VENCIMENTOS: dict[str, dict] = {
    "bonificacao_produtividade": {
        "rotulo": "Bonificação por produtividade",
        "natureza": NATUREZA_SALARIAL,
        "incide_inss": True,
        "incide_irrf": True,
        "incide_fgts": True,
        "incorpora_base": False,
        # Quanto se bonifica é medido no mês (produção, colheita, resultado):
        # não há valor prometido cujo ajuste seja alteração contratual. O dono
        # nomeou "bonificações" entre as verbas de "Editar".
        "alteracao": ALTERACAO_LIVRE,
        "fundamento": "Gratificação ajustada — CLT, art. 457, §1º",
    },
    "aumento_folha": {
        "rotulo": "Aumento na folha",
        "natureza": NATUREZA_SALARIAL,
        "incide_inss": True,
        "incide_irrf": True,
        "incide_fgts": True,
        "incorpora_base": True,
        # É o próprio salário: `incorpora_base` faz esta linha virar
        # salário-base na competência seguinte (`_propagar_aumento`). Mexer
        # nela É a alteração contratual — cadeado, sempre.
        "alteracao": ALTERACAO_CONTRATUAL,
        "fundamento": "Aumento salarial incorporado — CLT, art. 468",
    },
    "gueltas": {
        "rotulo": "Gueltas",
        "natureza": NATUREZA_SALARIAL,
        "incide_inss": True,
        "incide_irrf": True,
        "incide_fgts": True,
        "incorpora_base": False,
        # Valor pago por terceiro, evento a evento: como a bonificação, o que
        # se lança é quanto veio no mês.
        "alteracao": ALTERACAO_LIVRE,
        "fundamento": "Parcela paga por terceiro em razão do trabalho — CLT, art. 457, §3º; Súmula 354 do TST",
    },
    "vale_transporte": {
        "rotulo": "Vale-transporte",
        # A lei do vale-transporte é EXPRESSA: não tem natureza salarial, não
        # se incorpora à remuneração "para quaisquer efeitos" e não é base de
        # contribuição previdenciária nem de FGTS. É o enquadramento menos
        # ambíguo do catálogo inteiro — por isso ele entra, e o
        # vale-alimentação não (ver o relatório do PR): a natureza do
        # auxílio-alimentação depende da FORMA de pagamento (ticket/cartão do
        # PAT × dinheiro, Lei 14.442/2022), e o modelo não tem onde gravar
        # essa forma. Adivinhar poria a base de INSS/IRRF/FGTS errada.
        "natureza": NATUREZA_INDENIZATORIA,
        "incide_inss": False,
        "incide_irrf": False,
        "incide_fgts": False,
        "incorpora_base": False,
        # Quantos dias de deslocamento houve no mês é medição, não promessa.
        "alteracao": ALTERACAO_LIVRE,
        "fundamento": "Vale-transporte, sem natureza salarial — Lei 7.418/85, art. 2º",
    },
    "indenizacao": {
        "rotulo": "Indenização",
        "natureza": NATUREZA_INDENIZATORIA,
        "incide_inss": False,
        "incide_irrf": False,
        "incide_fgts": False,
        "incorpora_base": False,
        # Verba indenizatória: o valor repara um dano JÁ apurado e ajustado
        # com o empregado. O dono pediu cadeado nas indenizatórias.
        "alteracao": ALTERACAO_CONTRATUAL,
        "fundamento": "Verba indenizatória — CLT, art. 457, §2º; Lei 8.212/91, art. 28, §9º",
    },
    "reembolso": {
        "rotulo": "Reembolso de despesa",
        "natureza": NATUREZA_INDENIZATORIA,
        "incide_inss": False,
        "incide_irrf": False,
        "incide_fgts": False,
        "incorpora_base": False,
        # O valor é o do comprovante que o empregado apresentou: alterá-lo é
        # reembolsar coisa diferente da que foi gasta.
        "alteracao": ALTERACAO_CONTRATUAL,
        "fundamento": "Reposição de despesa do empregador — CLT, art. 457, §2º; Lei 8.212/91, art. 28, §9º",
    },
}

# Desconto não tem "natureza tributária": ele não entra em base nenhuma — sai
# do LÍQUIDO, depois de as retenções já estarem calculadas. O que distingue os
# códigos é a ORIGEM que a linha do recibo consegue mostrar.
CATALOGO_DESCONTOS: dict[str, dict] = {
    "desconto_valor": {
        "rotulo": "Desconto em folha",
        "exige_compra": False,
        "alteracao": ALTERACAO_LIVRE,
        "fundamento": "Desconto autorizado pelo empregado — CLT, art. 462, caput",
    },
    "desconto_compra": {
        "rotulo": "Desconto de compra realizada",
        "exige_compra": True,
        # O valor está amarrado à parcela da compra (FK `conta_gerencial_id`):
        # editá-lo desfaz o casamento entre o que o recibo cobra e o que a
        # nota diz — cadeado.
        "alteracao": ALTERACAO_CONTRATUAL,
        "fundamento": "Ressarcimento de compra feita pela fazenda — CLT, art. 462, caput",
    },
    "desconto_vale_transporte": {
        "rotulo": "Vale-transporte — participação do empregado",
        "exige_compra": False,
        "alteracao": ALTERACAO_LIVRE,
        # Existe junto com o vencimento `vale_transporte`: sem ele a fazenda
        # concederia o VT e não teria onde registrar a cota-parte legal do
        # empregado. O TETO de 6% não é imposto aqui (o sistema não impõe
        # tetos que o usuário não pediu) — o fundamento fica escrito para ele
        # conferir com a contabilidade.
        "fundamento": (
            "Participação do empregado no vale-transporte, limitada a 6% do salário-base — "
            "Lei 7.418/85, art. 4º, parágrafo único"
        ),
    },
}


def catalogo_publico() -> dict:
    """O catálogo como a tela consome — a lista de escolhas do formulário, já
    com o enquadramento, para o usuário LER a consequência antes de lançar (e
    não descobrir depois, no valor retido)."""
    return {
        "vencimentos": [{"codigo": codigo, **dados} for codigo, dados in CATALOGO_VENCIMENTOS.items()],
        "descontos": [{"codigo": codigo, **dados} for codigo, dados in CATALOGO_DESCONTOS.items()],
    }


def competencia_seguinte(competencia: str) -> str:
    """"2026-07" → "2026-08". Duplicado de `_competencia_seguinte` do router de
    folha de propósito: este módulo é de regras puras e não importa router
    (o caminho inverso — router importa regra — é o que o projeto usa)."""
    ano, mes = (int(x) for x in competencia.split("-"))
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return f"{ano:04d}-{mes:02d}"


def _competencia_extenso(competencia: str) -> str:
    """"2026-08" → "08/2026" — formato de referência do documento, não ISO."""
    partes = (competencia or "").split("-")
    return f"{partes[1]}/{partes[0]}" if len(partes) == 2 else (competencia or "—")


def _tributos_da_rubrica(rubrica: FolhaRubrica) -> str:
    """"INSS, IRRF e FGTS" / "nenhuma incidência" — o texto que a coluna
    Referência usa para declarar o regime da linha."""
    siglas = [
        sigla for sigla, incide in (
            ("INSS", rubrica.incide_inss), ("IRRF", rubrica.incide_irrf), ("FGTS", rubrica.incide_fgts),
        ) if incide
    ]
    if not siglas:
        return "sem incidência de INSS, IRRF e FGTS"
    if len(siglas) == 1:
        return f"entra na base de {siglas[0]}"
    return f"entra nas bases de {', '.join(siglas[:-1])} e {siglas[-1]}"


def rotulo_rubrica(rubrica: FolhaRubrica) -> str:
    """Rótulo do código + o texto livre do usuário, quando houver. O texto do
    usuário nunca substitui o rótulo: "Reembolso de despesa — diesel" continua
    dizendo qual é a verba mesmo quando o dono escreve só "diesel"."""
    catalogo = CATALOGO_VENCIMENTOS if rubrica.especie == ESPECIE_VENCIMENTO else CATALOGO_DESCONTOS
    rotulo = catalogo.get(rubrica.codigo, {}).get("rotulo", rubrica.codigo)
    extra = (rubrica.descricao or "").strip()
    return f"{rotulo} — {extra}" if extra else rotulo


def referencia_rubrica(rubrica: FolhaRubrica, compra: dict | None = None) -> str:
    """
    A coluna Referência da linha: de onde o valor veio e o que ele provoca.

    A regra da tela vale aqui igual: NENHUM valor aparece sem dizer de onde
    veio. Para vencimento, o que explica o número é o regime — dizer que uma
    bonificação entra na base de INSS/IRRF/FGTS é o que deixa o dono conferir
    o valor retido logo acima na mesma folha. Para desconto de compra, é o
    lançamento financeiro que o originou (número, fornecedor e nota).
    """
    if rubrica.especie == ESPECIE_VENCIMENTO:
        natureza = "natureza salarial" if rubrica.natureza == NATUREZA_SALARIAL else "natureza indenizatória"
        texto = f"{natureza} · {_tributos_da_rubrica(rubrica)}"
        if rubrica.incorpora_base:
            # O aumento é a única rubrica cujo efeito não acaba no mês: dizer
            # em QUAL competência ele vira salário-base é o que evita o dono
            # achar que precisa relançá-lo todo mês.
            seguinte = _competencia_extenso(competencia_seguinte(rubrica.competencia))
            texto = f"{texto} · incorpora ao salário-base a partir de {seguinte}"
        return texto
    if compra:
        partes = [p for p in (
            compra.get("numero_lancamento"),
            compra.get("fornecedor_cliente"),
            f"nota {compra['numero_nota']}" if compra.get("numero_nota") else None,
        ) if p]
        return "Compra " + " · ".join(partes) if partes else "Compra vinculada"
    if rubrica.conta_gerencial_id:
        # Vínculo gravado mas a compra não veio (parcela excluída depois, ou
        # de outra fazenda): dizer isso é mais honesto que apagar a referência
        # e deixar a linha parecendo um desconto avulso.
        return "Compra vinculada — lançamento não localizado"
    return f"Desconto lançado na folha de {_competencia_extenso(rubrica.competencia)}"


def origem_rubrica(rubrica: FolhaRubrica, compra: dict | None = None) -> dict:
    """O cartão que o clique na linha abre — o enquadramento por extenso e,
    no desconto de compra, o caminho até o lançamento no extrato."""
    catalogo = CATALOGO_VENCIMENTOS if rubrica.especie == ESPECIE_VENCIMENTO else CATALOGO_DESCONTOS
    dados = catalogo.get(rubrica.codigo, {})
    return {
        "tipo": "rubrica",
        "rubrica_id": rubrica.id,
        "codigo": rubrica.codigo,
        "rotulo": dados.get("rotulo", rubrica.codigo),
        "especie": rubrica.especie,
        "descricao": rubrica.descricao,
        "natureza": rubrica.natureza,
        "incide_inss": rubrica.incide_inss,
        "incide_irrf": rubrica.incide_irrf,
        "incide_fgts": rubrica.incide_fgts,
        "incorpora_base": rubrica.incorpora_base,
        "competencia_incorporacao": (
            competencia_seguinte(rubrica.competencia) if rubrica.incorpora_base else None
        ),
        # A coluna de edição do pop-up de pagamento sai DAQUI, e não de uma
        # segunda lista escrita no frontend: a tela só desenha "Editar" ou o
        # cadeado conforme o que o servidor mandou. Repetir o catálogo em
        # TypeScript era garantir que um dia os dois discordassem — e o lado
        # que decide é o servidor, que é quem recusa a gravação.
        #
        # Vem do CATÁLOGO (`dados`), não de uma coluna gravada na linha, ao
        # contrário de `natureza`/`incide_*`: aquelas são congeladas porque o
        # recibo é PROVA e não pode mudar de conteúdo se a lei mudar. Esta não
        # descreve o recibo — descreve o que a TELA pode fazer hoje —, então
        # deve seguir o catálogo de hoje. Rubrica de código desconhecido (do
        # futuro, ou de um catálogo que encolheu) cai em "contratual": o lado
        # seguro é pedir confirmação, nunca liberar em silêncio.
        "alteracao": dados.get("alteracao", ALTERACAO_CONTRATUAL),
        "fundamento": dados.get("fundamento"),
        "compra": compra,
    }


def linha_de_rubrica(rubrica: FolhaRubrica, compra: dict | None = None) -> dict:
    """A rubrica virada linha do holerite de quatro colunas."""
    rotulo = rotulo_rubrica(rubrica)
    valor = round(rubrica.valor, 2)
    if rubrica.especie == ESPECIE_VENCIMENTO:
        return holerite.linha(
            "vencimento_extra", rotulo, valor, rotulo,
            referencia_rubrica(rubrica, compra), provento=valor,
            origem=origem_rubrica(rubrica, compra),
        )
    return holerite.linha(
        "desconto_extra", rotulo, -valor, rotulo,
        referencia_rubrica(rubrica, compra), desconto=valor,
        origem=origem_rubrica(rubrica, compra),
    )


def linhas_de_rubricas(rubricas: list[FolhaRubrica], compras: dict[int, dict] | None = None) -> list[dict]:
    """Vencimentos primeiro, descontos depois — a ordem das colunas do papel.
    Dentro de cada espécie, a ordem de lançamento (id), para dois meses
    seguidos continuarem comparáveis linha a linha."""
    compras = compras or {}
    ordenadas = sorted(
        rubricas,
        key=lambda r: (0 if r.especie == ESPECIE_VENCIMENTO else 1, r.id or 0),
    )
    return [linha_de_rubrica(r, compras.get(r.conta_gerencial_id) if r.conta_gerencial_id else None)
            for r in ordenadas]


# ---------------------------------------------------------------------------
# Somas — o que a folha precisa guardar para o líquido e para as bases
# ---------------------------------------------------------------------------
def valor_liquido_das_rubricas(rubricas: list[FolhaRubrica]) -> float:
    """Efeito LÍQUIDO das rubricas sobre o pagamento: vencimentos − descontos.
    É este número que `FolhaPagamento.valor_rubricas` guarda, para a fórmula
    do líquido continuar existindo em UM lugar só (`_liquido_folha`)."""
    total = 0.0
    for r in rubricas:
        total += r.valor if r.especie == ESPECIE_VENCIMENTO else -r.valor
    return round(total, 2)


def base_extra(rubricas: list[FolhaRubrica], tributo: str) -> float:
    """Quanto as rubricas ACRESCENTAM à base de um tributo ("inss", "irrf" ou
    "fgts"). Só vencimento entra: desconto sai do líquido depois das
    retenções, nunca da base delas."""
    campo = {"inss": "incide_inss", "irrf": "incide_irrf", "fgts": "incide_fgts"}[tributo]
    return round(sum(
        r.valor for r in rubricas
        if r.especie == ESPECIE_VENCIMENTO and getattr(r, campo)
    ), 2)


def base_tributavel_das_rubricas(rubricas: list[FolhaRubrica]) -> float:
    """
    O acréscimo de base que `FolhaPagamento.valor_rubricas_tributaveis` guarda
    para o holerite exibir a base certa sem reconsultar as rubricas.

    CUIDADO AO ACRESCENTAR RUBRICA AO CATÁLOGO: este cache assume que, nas
    rubricas de hoje, a base é a MESMA para os três tributos (salarial entra
    nos três; indenizatória em nenhum) — ver o teste
    `test_catalogo_mantem_bases_alinhadas`, que quebra de propósito no dia em
    que uma rubrica nova desalinhar isso. Quando esse dia chegar, o caminho é
    quebrar o cache em três colunas, não relaxar o teste.
    """
    return base_extra(rubricas, "inss")


def retencoes_recalculadas(
    valor_bruto: float, percentual_inss: float, percentual_ir: float,
    percentual_fgts: float | None, rubricas: list[FolhaRubrica],
) -> dict:
    """
    Recalcula INSS/IRRF/FGTS sobre a base CORRIGIDA pelas rubricas salariais.

    Só recalcula o que tem PERCENTUAL gravado, e essa é a regra do projeto
    inteiro, não uma escolha deste módulo: quando o usuário digita o valor
    retido direto (`valor_inss=300, percentual_inss=0`), não existe base
    declarada — deduzir um percentual a partir do valor para depois aplicá-lo
    a outra base seria inventar o número. Nesse caso o valor informado fica
    como está e a coluna Referência continua dizendo "Valor informado, sem
    percentual", como já dizia.
    """
    saida: dict[str, float] = {}
    for chave, percentual, tributo in (
        ("valor_inss", percentual_inss, "inss"),
        ("valor_ir", percentual_ir, "irrf"),
        ("valor_fgts", percentual_fgts, "fgts"),
    ):
        if not percentual:
            continue
        base = round(valor_bruto + base_extra(rubricas, tributo), 2)
        saida[chave] = round(base * percentual / 100, 2)
    return saida


# ---------------------------------------------------------------------------
# Carga em lote e incorporação do aumento
# ---------------------------------------------------------------------------
def rubricas_por_folha(session: Session, registros: list) -> dict[int, list[FolhaRubrica]]:
    """
    {folha_id: [rubricas]} para TODAS as folhas de uma listagem, numa consulta.

    Isolamento entre fazendas pelo mesmo desenho de `_contexto_discriminacao`:
    o escopo é o conjunto de `folha_id` das folhas recebidas, que já vieram
    filtradas por fazenda na listagem. Nenhuma rubrica de outra fazenda alcança
    este dicionário, porque nenhuma folha de outra fazenda entra no IN — e não
    existe caminho tolerante ("se veio fazenda, filtra") por onde vazar.
    """
    ids = [r.id for r in registros if getattr(r, "id", None)]
    if not ids:
        return {}
    saida: dict[int, list[FolhaRubrica]] = {}
    for rubrica in session.exec(select(FolhaRubrica).where(FolhaRubrica.folha_id.in_(ids))).all():
        saida.setdefault(rubrica.folha_id, []).append(rubrica)
    return saida


def compras_das_rubricas(session: Session, rubricas: list[FolhaRubrica]) -> dict[int, dict]:
    """
    {conta_gerencial_id: resumo da compra} das rubricas que apontam para uma
    compra — o que a linha do recibo mostra e o que o clique abre.

    A consulta é pelos ids QUE AS RUBRICAS JÁ GRAVARAM, e a gravação só aceita
    parcela da própria fazenda (ver o endpoint de criação): o vínculo é a
    fronteira, não este SELECT.
    """
    ids = {r.conta_gerencial_id for r in rubricas if r.conta_gerencial_id}
    if not ids:
        return {}
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.id.in_(ids))).all()
    return {c.id: resumo_compra(c) for c in contas}


def resumo_compra(conta: ContaGerencial) -> dict:
    """O cartão da compra dentro do holerite — os campos que identificam a nota
    para um humano, mais o número do lançamento que leva ao extrato."""
    return {
        "conta_id": conta.id,
        "numero_lancamento": conta.numero_lancamento,
        "descricao": conta.descricao,
        "fornecedor_cliente": conta.fornecedor_cliente,
        "numero_nota": conta.numero_nota,
        "tipo_documento": conta.tipo_documento,
        "centro_custo": conta.centro_custo,
        "data_emissao": conta.data_emissao.isoformat() if conta.data_emissao else None,
        "data_vencimento": conta.data_vencimento.isoformat() if conta.data_vencimento else None,
        "data_pagamento": conta.data_pagamento.isoformat() if conta.data_pagamento else None,
        "valor_total": round(conta.valor_total or 0.0, 2),
        "valor_pago": round(conta.valor_pago, 2) if conta.valor_pago is not None else None,
        "parcela_num": conta.parcela_num,
        "parcela_total": conta.parcela_total,
    }


def aumento_incorporado(
    session: Session, pessoa_id: int, desde: str, ate: str, fazenda_id: int | None,
) -> float:
    """
    Quanto de "aumento na folha" já foi concedido a esta pessoa entre as
    competências `desde` (inclusive) e `ate` (EXCLUSIVE) — o valor que a
    competência `ate`, ao ser gerada, precisa somar ao salário-base do modelo
    de recorrência.

    As duas pontas do intervalo são deliberadas:
    - `desde` = a competência do lançamento-modelo, INCLUSIVE, porque um
      aumento concedido no próprio mês do modelo não está dentro do
      `valor_bruto` dele (naquele mês ele foi uma LINHA de vencimento, não
      salário) — e precisa entrar na base dos meses seguintes;
    - `ate` EXCLUSIVE, porque o aumento concedido no próprio mês gerado já
      aparece nele como linha: somá-lo também à base pagaria duas vezes.

    Aumento anterior ao modelo não entra: ele já está dentro do `valor_bruto`
    que o usuário digitou quando criou o lançamento-modelo.
    """
    query = select(FolhaRubrica).where(
        FolhaRubrica.pessoa_id == pessoa_id,
        FolhaRubrica.incorpora_base == True,  # noqa: E712
        FolhaRubrica.competencia >= desde,
        FolhaRubrica.competencia < ate,
        # Filtro de fazenda INCONDICIONAL (`== fazenda_id`, que em None vira
        # `IS NULL`): esta soma vira salário gravado e conta a pagar emitida —
        # o padrão tolerante `if fazenda_id is not None` deixaria um token sem
        # a claim de fazenda pagar aumento de outro inquilino.
        FolhaRubrica.fazenda_id == fazenda_id,
    )
    return round(sum(r.valor for r in session.exec(query).all()), 2)
