"""
Média das parcelas SALARIAIS VARIÁVEIS habituais — o que faltava para 13º,
férias e rescisão pararem de sair só sobre o salário-base.

────────────────────────────────────────────────────────────────────────────
O BURACO QUE ESTE MÓDULO FECHA
────────────────────────────────────────────────────────────────────────────
`rules/folha_rh.py` calculava 13º, férias e rescisão a partir de UM número:
`Pessoa.salario_base`. Nenhuma rubrica era consultada. Consequência: quem
recebe bonificação por produtividade, guelta, insalubridade ou
vale-alimentação de natureza salarial tinha essas parcelas fora das bases de
13º, férias e rescisão — subdeclaração de todo funcionário com remuneração
variável. Não era defeito do vale-alimentação; era do sistema inteiro, e
estava registrado como `LIMITE CONHECIDO` na docstring de
`rules/vale_alimentacao.py`.

A base normativa da integração é o art. 457, §1º, da CLT (integram o salário
as gratificações ajustadas e demais parcelas pagas em razão do trabalho) e a
Súmula 45 do TST (a gratificação HABITUAL integra o cálculo). Este módulo não
decide o que é salarial — ele só SOMA o que a folha já enquadrou.

────────────────────────────────────────────────────────────────────────────
DE ONDE SAI O NÚMERO: FATO CONGELADO, NUNCA RECÁLCULO
────────────────────────────────────────────────────────────────────────────
A fonte é `FolhaRubrica` — a linha do holerite já gravada, com a `natureza` e
as três incidências COPIADAS para ela no momento do lançamento (ver
`models/folha_rubrica.py`: "o holerite é PROVA"). Entram na média as linhas
com `especie == "vencimento"` e `natureza == "salarial"`.

Isso resolve três coisas de uma vez, e é por isso que a fonte é esta e não
outra:

1. **Não reimplementa a classificação.** Quem diz que bonificação e guelta são
   salariais e que reembolso e vale-transporte não são é o catálogo
   (`rules/rubrica_folha.py`), e ele já escreveu essa resposta na linha. Uma
   segunda tabela de naturezas aqui seria a segunda a divergir.

2. **Respeita o enquadramento POR FUNCIONÁRIO do vale-alimentação.** A
   natureza do VA não é do código: é da forma de pagamento × PAT × trava da
   OJ 413 (ver `rules/vale_alimentacao.py::natureza_do_vale_alimentacao`).
   `_sincronizar_vale_alimentacao` grava o resultado dessa árvore na linha —
   então o VA salarial entra na média e o indenizatório não, sem que este
   módulo saiba uma vírgula da árvore.

3. **Não muda o passado.** Se o catálogo ou a lei mudarem amanhã, a média de
   um período antigo continua a mesma: ela lê o que estava escrito na linha,
   não o que o catálogo diz hoje.

O salário-base NÃO entra (ele já está na conta de quem chama, somado por
fora), verba indenizatória não entra, e desconto não entra.

────────────────────────────────────────────────────────────────────────────
AS TRÊS JANELAS — cada verba tem a sua, e não é detalhe
────────────────────────────────────────────────────────────────────────────
- **13º salário — ANO CIVIL.** Lei 4.090/62, art. 1º, §1º ("a gratificação
  corresponderá a 1/12 da remuneração devida em dezembro, por mês de
  serviço") e Decreto 57.155/65, art. 2º: quando há remuneração variável, o
  13º se apura pela MÉDIA dessas parcelas no ano civil da competência,
  dividida pelo número de meses de vigência do contrato naquele ano.

- **Férias — PERÍODO AQUISITIVO.** CLT, art. 142, §§ 1º a 6º. O §3º fala de
  comissão/percentagem e o §5º de horas extras, mas a técnica é a mesma para
  toda variável habitual: a média se apura sobre o PERÍODO AQUISITIVO (os 12
  meses do período), e não sobre o ano civil. O terço constitucional incide
  sobre o total JÁ com a média — o que sai de graça em `calcular_ferias`,
  porque lá o terço é percentual do valor das férias.

- **Aviso prévio indenizado — ÚLTIMOS 12 MESES.** O aviso prévio indenizado
  paga a remuneração que o empregado receberia no período do aviso; a
  referência do que ele "receberia" é o que vinha recebendo, e a janela usual
  é a dos 12 meses anteriores ao desligamento.

A **Súmula 253 do TST** é de GRATIFICAÇÃO SEMESTRAL — ela diz que essa verba
específica não repercute em férias nem em aviso prévio, e repercute pelo
duodécimo no 13º. NÃO é regra geral das variáveis e por isso não está
implementada como tal: o sistema não tem hoje uma rubrica de gratificação
semestral no catálogo, e o dia em que tiver, o tratamento dela é este —
código próprio, com exclusão das janelas de férias/aviso.

────────────────────────────────────────────────────────────────────────────
O DIVISOR — e por que mês sem folha lançada CONTA
────────────────────────────────────────────────────────────────────────────
O divisor é o número de meses de **vigência do contrato dentro da janela**,
apurado pela MESMA regra dos 15 dias que o resto do módulo de RH já usa
(`folha_rh.meses_regra_15_dias`, Súmula 45 do TST) — não há uma segunda
contagem de avos neste projeto.

Isso significa que um mês em que o contrato estava em vigor mas NÃO existe
folha lançada entra no divisor valendo ZERO. A escolha é deliberada e muda
dinheiro, então vai justificada:

- é o que a norma manda dividir — "o número de meses de vigência do contrato
  naquele ano" (Decreto 57.155/65, art. 2º), não o número de meses com
  movimento;
- dividir só pelos meses COM folha transformaria uma bonificação isolada de
  R$ 5.000 num ano com uma folha lançada numa média mensal de R$ 5.000, que
  entraria nas três bases. O erro para cima aqui é tão caro quanto o erro
  para baixo, e este é o lado que a lei escolhe;
- o mês sem folha é INDISTINGUÍVEL, para o sistema, do mês em que a pessoa
  não recebeu variável nenhuma. Fingir que ele não existe é escolher a
  interpretação mais cara sem nenhum fato que a sustente.

Para não deixar isso escondido, a composição devolvida MARCA cada competência
sem folha lançada (`sem_folha`) e traz a contagem delas (`competencias_sem_folha`).
A tela e o recibo mostram esse número: se a fazenda lança folha só de vez em
quando, o dono VÊ o divisor que produziu a média e decide.

────────────────────────────────────────────────────────────────────────────
DESLIGADO POR PADRÃO
────────────────────────────────────────────────────────────────────────────
Nada aqui roda sem o parâmetro `calcula_media_verbas_variaveis` da fazenda
(grupo `folha_rh`, padrão FALSO — ver `rules/parametros.py`). Desligado,
quem chama passa `media_variaveis=0.0` às funções puras de `folha_rh.py` e o
resultado é byte a byte o de sempre. O requisito é do dono, textual: "tem que
ser de modo que possa ser configurável, para usar ou não, pois a fazenda pode
não querer controlar os detalhes e deixar só com a contabilidade externa".

────────────────────────────────────────────────────────────────────────────
ONDE ESTE MÓDULO NÃO ENTRA
────────────────────────────────────────────────────────────────────────────
- **Folha, férias, 13º ou rescisão já fechada/paga não é recalculada.** A
  guarda não é aqui: é nos endpoints, que já recusam editar registro pago
  (`atualizar_ferias`, `atualizar_decimo_terceiro`) ou rescisão fechada
  (`atualizar_rescisao_simulacao`) — a mesma família de recusa que
  `_sincronizar_vale_alimentacao` aplica à folha com
  `discriminacao_congelada_em`. Ligar o parâmetro hoje não reescreve um
  centavo de nada que já foi pago; vale do próximo lançamento em diante.
- **Multa do FGTS.** `calcular_rescisao` estima o depósito de FGTS por
  `salario_base × 8% × meses` e já declara, na própria docstring, que é
  ESTIMATIVA (o sistema não guarda o extrato). Somar a média ali mudaria um
  número que ninguém deveria usar como oficial, e o requisito não pediu.
  Fica registrado como limite consciente.

Este módulo precisa de sessão e banco — por isso NÃO mora em `folha_rh.py`,
que é de funções puras. Quem junta as duas coisas é o router
(`api/routers/cadastro/rh_folha.py`).
"""
from __future__ import annotations

import calendar
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlmodel import Session, select

from fazenda.models import FolhaPagamento, FolhaRubrica
from fazenda.rules.folha_rh import meses_regra_15_dias
from fazenda.rules.rubrica_folha import ESPECIE_VENCIMENTO, NATUREZA_SALARIAL, CATALOGO_VENCIMENTOS

# As três janelas, com o rótulo que vai para a tela e o recibo. O rótulo é
# parte do produto: média que o dono não consegue conferir é média que ele não
# usa, e "média de quê, de quando?" é a primeira pergunta que ele faz.
JANELA_ANO_CIVIL = "ano_civil"
JANELA_PERIODO_AQUISITIVO = "periodo_aquisitivo"
JANELA_ULTIMOS_12_MESES = "ultimos_12_meses"

FUNDAMENTOS = {
    JANELA_ANO_CIVIL: (
        "Média das parcelas salariais variáveis do ano civil, dividida pelos meses de vigência "
        "do contrato no ano — Lei 4.090/62, art. 1º, §1º, e Decreto 57.155/65, art. 2º; "
        "a habitualidade que faz integrar é a da Súmula 45 do TST"
    ),
    JANELA_PERIODO_AQUISITIVO: (
        "Média das parcelas salariais variáveis do período aquisitivo das férias — "
        "CLT, art. 142, §§ 1º a 6º; o terço constitucional incide sobre o total já com a média"
    ),
    JANELA_ULTIMOS_12_MESES: (
        "Média das parcelas salariais variáveis dos 12 meses anteriores ao desligamento — "
        "o aviso prévio indenizado paga a remuneração que o empregado receberia no período do aviso"
    ),
}


def _competencia(dia: date) -> str:
    """`date(2026, 7, 9)` → "2026-07" — o formato de `FolhaPagamento.competencia`."""
    return f"{dia.year:04d}-{dia.month:02d}"


def _competencias_entre(inicio: date, fim: date) -> list[str]:
    """Todas as competências ("AAAA-MM") tocadas pelo intervalo [inicio, fim],
    em ordem. Intervalo invertido devolve lista vazia — quem chama trata."""
    if fim < inicio:
        return []
    competencias: list[str] = []
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        competencias.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return competencias


def _primeiro_dia(competencia: str) -> date:
    ano, mes = (int(x) for x in competencia.split("-"))
    return date(ano, mes, 1)


def _ultimo_dia(competencia: str) -> date:
    ano, mes = (int(x) for x in competencia.split("-"))
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _rotulo_competencia(competencia: str) -> str:
    """"2026-07" → "07/2026" — o formato do documento impresso, não o ISO."""
    partes = competencia.split("-")
    return f"{partes[1]}/{partes[0]}" if len(partes) == 2 else competencia


def _rotulo_rubrica(codigo: str) -> str:
    """Rótulo do catálogo para o código da linha; o próprio código quando for
    um verbete que o catálogo não conhece (linha antiga, código removido) —
    melhor mostrar "insalubridade" do que esconder a parcela da composição."""
    return CATALOGO_VENCIMENTOS.get(codigo, {}).get("rotulo", codigo)


def apurar(
    session: Session,
    pessoa_id: int,
    fazenda_id: int | None,
    *,
    janela: str,
    inicio: date,
    fim: date,
    data_admissao: date | None = None,
    data_desligamento: date | None = None,
    divisor: int | None = None,
) -> dict:
    """
    A média das parcelas salariais variáveis habituais de uma pessoa numa
    janela, MAIS a composição que permite conferi-la linha a linha.

    `inicio`/`fim` delimitam a janela (o mês de `inicio` e o mês de `fim`
    entram inteiros — a unidade da folha é a competência, não o dia).
    `janela` é uma das três constantes do módulo e serve só para rotular e
    fundamentar o resultado; quem escolhe as datas é o chamador, porque é ele
    que sabe se está calculando 13º, férias ou aviso prévio.

    `divisor` permite ao chamador IMPOR o número de meses — é o que o 13º faz,
    passando os `meses_trabalhados` que o próprio lançamento já usa como avos,
    para a média e a proporcionalidade do 13º não saírem de duas contagens
    diferentes. Sem ele, o divisor é calculado aqui pelos meses de vigência do
    contrato dentro da janela (regra dos 15 dias — ver a docstring do módulo).

    RECORTE DE FAZENDA INCONDICIONAL. O filtro por `fazenda_id` vai dentro da
    consulta, sempre, inclusive quando ele é None (nesse caso o que se procura
    são as linhas sem fazenda — não "todas as linhas"). Média é dinheiro
    gravado no recibo de alguém: o padrão tolerante "se veio fazenda, filtra"
    é exatamente o que faria a bonificação de um inquilino inflar as férias de
    outro.

    Devolve SEMPRE um dicionário completo (JSON-serializável), mesmo quando
    não há nada a somar — a tela precisa poder dizer "a média foi apurada e
    deu zero", que é informação diferente de "não foi apurada".
    """
    competencias = _competencias_entre(inicio, fim)
    if not competencias:
        # Janela invertida (dado inconsistente do chamador). Devolve a forma
        # completa com média zero em vez de estourar: o lançamento de férias
        # não pode falhar por causa de um período aquisitivo digitado ao
        # contrário — a validação disso é do endpoint, não da média.
        vazia = nao_apurada(janela)
        return {**vazia, "aplicada": True, "motivo": "Janela sem nenhuma competência."}

    # ── Meses de vigência do contrato DENTRO da janela ──────────────────────
    # O contrato pode ter começado depois do início da janela (admissão no
    # meio do ano) ou terminado antes do fim dela (desligamento). O divisor é
    # o da interseção, e a contagem é a regra dos 15 dias já usada pelo resto
    # do RH — importada de `folha_rh`, nunca reescrita aqui.
    inicio_vigencia = max(inicio, data_admissao) if data_admissao else inicio
    fim_vigencia = min(fim, data_desligamento) if data_desligamento else fim
    meses_vigencia = meses_regra_15_dias(inicio_vigencia, fim_vigencia, limite=len(competencias))

    # ── As linhas salariais de vencimento das folhas da janela ─────────────
    # Uma consulta só para a janela inteira (o mesmo cuidado de
    # `rubrica_folha.rubricas_por_folha`: montar um cálculo de RH não pode
    # custar N consultas). `natureza` e `especie` são lidas da LINHA — o
    # enquadramento congelado no lançamento —, nunca do catálogo de hoje.
    linhas = session.exec(
        select(FolhaRubrica).where(
            FolhaRubrica.pessoa_id == pessoa_id,
            FolhaRubrica.fazenda_id == fazenda_id,
            FolhaRubrica.especie == ESPECIE_VENCIMENTO,
            FolhaRubrica.natureza == NATUREZA_SALARIAL,
            FolhaRubrica.competencia.in_(competencias),
        )
    ).all()

    # Quais competências têm folha LANÇADA — é o que separa "mês sem variável"
    # de "mês sem folha nenhuma". As duas valem zero na soma; só uma delas é
    # um buraco de dado, e a composição precisa dizer qual é qual.
    folhas = session.exec(
        select(FolhaPagamento).where(
            FolhaPagamento.pessoa_id == pessoa_id,
            FolhaPagamento.fazenda_id == fazenda_id,
            FolhaPagamento.competencia.in_(competencias),
        )
    ).all()
    competencias_com_folha = {f.competencia for f in folhas}

    por_competencia: dict[str, list[FolhaRubrica]] = {}
    for linha in linhas:
        por_competencia.setdefault(linha.competencia, []).append(linha)

    detalhe: list[dict] = []
    total = 0.0
    for competencia in competencias:
        # Competência fora da vigência do contrato não é "mês sem folha": é
        # mês em que a pessoa não era empregada. Não aparece na composição e
        # não pesa no divisor (ele já foi apurado pela interseção acima).
        if data_admissao and _ultimo_dia(competencia) < data_admissao:
            continue
        if data_desligamento and _primeiro_dia(competencia) > data_desligamento:
            continue
        rubricas = por_competencia.get(competencia, [])
        valor = round(sum(r.valor for r in rubricas), 2)
        total = round(total + valor, 2)
        detalhe.append({
            "competencia": competencia,
            "rotulo": _rotulo_competencia(competencia),
            "valor": valor,
            "sem_folha": competencia not in competencias_com_folha,
            "rubricas": [
                {"codigo": r.codigo, "rotulo": _rotulo_rubrica(r.codigo), "valor": round(r.valor, 2)}
                for r in sorted(rubricas, key=lambda r: (r.codigo, r.id or 0))
            ],
        })

    divisor_final = divisor if divisor is not None else meses_vigencia
    # Divisor zero acontece de verdade: janela inteira fora do contrato, ou
    # contrato de menos de 15 dias. Média zero é a resposta honesta — dividir
    # por len(detalhe) para "salvar" o número seria inventar um divisor que
    # nenhuma norma prevê.
    media = round(total / divisor_final, 2) if divisor_final > 0 else 0.0

    return {
        "aplicada": True,
        "janela": janela,
        "fundamento": FUNDAMENTOS.get(janela, ""),
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "rotulo_janela": (
            f"{_rotulo_competencia(competencias[0])} a {_rotulo_competencia(competencias[-1])}"
            if competencias else "—"
        ),
        "competencias": detalhe,
        "competencias_sem_folha": sum(1 for d in detalhe if d["sem_folha"]),
        "total": total,
        "divisor": divisor_final,
        "divisor_imposto": divisor is not None,
        "criterio_divisor": (
            "meses trabalhados informados no lançamento (mesmos avos do 13º)"
            if divisor is not None else
            "meses de vigência do contrato na janela, pela regra dos 15 dias (Súmula 45 do TST)"
        ),
        "media": media,
    }


def nao_apurada(janela: str) -> dict:
    """
    A composição do caso DESLIGADO — média zero, com o motivo escrito.

    Existe para a tela e o recibo terem sempre a mesma forma de dado a
    renderizar, e para o dono ver "o sistema não calcula médias de variáveis
    (parâmetro desligado)" em vez de não ver nada e ficar sem saber se a média
    deu zero ou nem foi tentada. `aplicada: False` é o que distingue os dois.
    """
    return {
        "aplicada": False,
        "janela": janela,
        "fundamento": FUNDAMENTOS.get(janela, ""),
        "motivo": (
            "O parâmetro \"O sistema calcula as médias de verbas variáveis no 13º, férias e rescisão\" "
            "está desligado nesta fazenda (Configurações > Parâmetros > Folha de pagamento / RH). "
            "O cálculo saiu apenas sobre o salário-base."
        ),
        "inicio": None,
        "fim": None,
        "rotulo_janela": "—",
        "competencias": [],
        "competencias_sem_folha": 0,
        "total": 0.0,
        "divisor": 0,
        "divisor_imposto": False,
        "criterio_divisor": "—",
        "media": 0.0,
    }


# ---------------------------------------------------------------------------
# As três janelas, uma função cada. São finas de propósito: o que elas
# carregam é a ESCOLHA da janela (que é jurídica e tem de estar num lugar só),
# não a aritmética — essa mora em `apurar`.
# ---------------------------------------------------------------------------
def media_do_ano_civil(
    session: Session, pessoa_id: int, fazenda_id: int | None, ano: int,
    *, data_admissao: date | None = None, data_desligamento: date | None = None,
    divisor: int | None = None,
) -> dict:
    """Média para o 13º SALÁRIO — ano civil da competência, dividida pelos
    meses de vigência do contrato no ano (Lei 4.090/62, art. 1º, §1º, e
    Decreto 57.155/65, art. 2º).

    O chamador do 13º passa `divisor=meses_trabalhados`: é o mesmo número de
    avos que o lançamento já usa para proporcionalizar o 13º, e usar dois
    números diferentes para a mesma coisa é como eles passam a divergir."""
    return apurar(
        session, pessoa_id, fazenda_id,
        janela=JANELA_ANO_CIVIL,
        inicio=date(ano, 1, 1), fim=date(ano, 12, 31),
        data_admissao=data_admissao, data_desligamento=data_desligamento,
        divisor=divisor,
    )


def media_do_periodo_aquisitivo(
    session: Session, pessoa_id: int, fazenda_id: int | None,
    periodo_inicio: date, periodo_fim: date,
    *, data_admissao: date | None = None, data_desligamento: date | None = None,
) -> dict:
    """Média para as FÉRIAS — período aquisitivo, não ano civil (CLT, art.
    142, §§ 1º a 6º).

    O sistema CONHECE o período aquisitivo: `FeriasFuncionario` grava
    `periodo_aquisitivo_inicio`/`periodo_aquisitivo_fim` desde a primeira
    versão da tela, e a rescisão calcula o período em curso em
    `folha_rh.inicio_periodo_aquisitivo_atual`. Nenhuma aproximação por "12
    competências anteriores ao gozo" foi necessária — o dado real existe."""
    return apurar(
        session, pessoa_id, fazenda_id,
        janela=JANELA_PERIODO_AQUISITIVO,
        inicio=periodo_inicio, fim=periodo_fim,
        data_admissao=data_admissao, data_desligamento=data_desligamento,
    )


def media_dos_ultimos_12_meses(
    session: Session, pessoa_id: int, fazenda_id: int | None, referencia: date,
    *, data_admissao: date | None = None, data_desligamento: date | None = None,
) -> dict:
    """Média para o AVISO PRÉVIO INDENIZADO — os 12 meses anteriores à
    `referencia` (o desligamento), inclusive o mês dela.

    A janela é a do que a pessoa VINHA recebendo. Ela não acompanha a projeção
    do aviso prévio (Súmula 371 do TST): o contrato se projeta para efeito de
    avos, mas nenhuma verba variável é recebida no período projetado, e somar
    meses vazios ao divisor diluiria a média sem nenhum fato por trás."""
    # 12 competências FECHANDO no mês da referência (e não `referencia` menos
    # um ano civil, que daria 13 competências e um divisor de 13 meses).
    inicio = referencia.replace(day=1) - relativedelta(months=11)
    return apurar(
        session, pessoa_id, fazenda_id,
        janela=JANELA_ULTIMOS_12_MESES,
        inicio=inicio, fim=referencia,
        data_admissao=data_admissao, data_desligamento=data_desligamento,
    )
