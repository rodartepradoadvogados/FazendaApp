"""
Cadastro > Folha de Pagamento > pagar lançando valor DISTINTO numa verba.

O PEDIDO, literal e repetido duas vezes pelo dono: "no ato do pagamento, deve
ser possível clicar no vale ou outra verba, lançar valor distinto e a
diferença, em pop up, decidir se é desconto, desconsiderar, re-parcelar".

O QUE FALTAVA. "Marcar como pago" (PUT /folha-pagamento/{id}) só perguntava a
DATA: o valor pago era, obrigatoriamente, o líquido calculado. Quem quisesse
descontar do funcionário menos vale do que a parcela do mês tinha de sair da
tela de pagamento, abrir as ações do vale, decidir lá, voltar e só então pagar
— e nesse meio-tempo a folha já podia ter sido paga, congelando um recibo com
o desconto que não foi feito.

O QUE ESTE MÓDULO ACRESCENTA É O GATILHO, NÃO AS REGRAS. As três decisões da
diferença são as MESMAS do PR #708 (`rh_vale_acoes.py`), e são chamadas de lá,
não reescritas aqui:

  desconto/abatimento → o valor não descontado deixa de ser cobrado; com conta
                        corrente informada, `_lancar_devolucao_de_vale` lança a
                        receita "Devolução de vale".
  desconsiderar       → a fazenda assume: `_assumir_no_financeiro` faz o valor
                        mudar de dono ("desconsiderar o vale faz a conta passar
                        a ser da fazenda... e comunicar com o financeiro
                        completo" — palavras do dono).
  reparcelar          → `_acao_reparcelar` redistribui o saldo (a diferença
                        incluída) nas competências seguintes.

O ÚNICO CÁLCULO QUE NASCE AQUI é o que o gatilho exige: a parcela DAQUELE MÊS
passa a valer o que foi efetivamente descontado, e a diferença é o que sobra
para decidir. Por isso as ações são chamadas com a lista de parcelas pendentes
JÁ SEM a parcela do mês que está sendo pago — ela não é mais "pendente", é o
desconto que acabou de acontecer.

ORDEM, QUE AQUI É TUDO. A decisão roda ANTES do pagamento: primeiro o vale
muda, depois o líquido é recalculado com o vale já ajustado, e só então a
folha vira "pago" e a discriminação é congelada (`_congelar_discriminacao`).
Folha paga é fotografia — nada nela pode ser reescrito depois, e é justamente
por isso que o pop-up age no ATO do pagamento e não em seguida.

MULTI-FAZENDA. Folha, pessoa e parcela são carregadas com o filtro de fazenda
DENTRO da própria consulta e caem em 404 (nunca 403, que confirmaria a
existência do id); a escrita usa `get_fazenda_id_escrita`. O vale é carregado
por `_vale_da_fazenda`, o mesmo do #708.

────────────────────────────────────────────────────────────────────────────
A COLUNA DE EDIÇÃO (pedido do dono, segunda rodada)
────────────────────────────────────────────────────────────────────────────
Até aqui SÓ a parcela de vale era editável no ato do pagamento, e as demais
verbas apareciam em leitura com a frase "para mudá-las, use 'Editar
lançamento' antes de pagar". O dono pediu que TODA verba passe a ter uma
coluna de edição com dois estados: "Editar" nas que são medidas no mês (vale,
bonificação, gueltas, vale-transporte, desconto em folha) e um CADEADO nas
demais. O cadeado não bloqueia — avisa que a alteração "será tido[a] como
alteração daquele momento em diante" e, confirmada, deixa passar.

QUEM É QUEM está em `rules/verba_pagamento.py`, módulo puro, e é a MESMA régua
que a tela usa (`frontend/lib/pagamentoFolhaRegras.ts`). Aqui só se confere.

O QUE CADA ALTERAÇÃO GRAVA, e por que não há um caminho novo para nenhuma:

  rubrica     → o valor da própria `FolhaRubrica`, e `_recalcular_folha` (de
                rh_folha.py) refaz bases, retenções e líquido. É o
                mesmo caminho do PUT /rubricas/{id}; quando a rubrica é o
                "aumento na folha", `_propagar_aumento` corre igual.
  salário     → NÃO reescreve `FolhaPagamento.valor_bruto`. O aumento vira uma
                rubrica `aumento_folha` da DIFERENÇA nesta competência, que é
                o mecanismo que o sistema já tem para "novo salário daquele
                momento em diante" (CLT, art. 468): entra como vencimento
                deste mês, `_propagar_aumento` soma a diferença a
                `Pessoa.salario_base` e às competências seguintes AINDA NÃO
                PAGAS, e nenhuma competência passada nem folha paga é tocada.
                Para MENOR é recusado com 400 — art. 468 da CLT: alteração
                contratual lesiva ao empregado é nula.
  INSS / IR   → `valor_inss`/`valor_ir` com o `percentual_*` zerado, que é
                exatamente como o formulário de folha já grava uma retenção
                digitada à mão (ver `referencia_retencao`: a linha passa a
                dizer "Valor informado, sem percentual", em vez de mentir um
                percentual que não produz aquele valor).
  outros      → `FolhaPagamento.descontos`, o float solto sem itemização.

FOLHA PAGA CONTINUA RECUSANDO TUDO, sem exceção: a primeira coisa que o
endpoint faz é recusar folha paga ou já congelada. A discriminação congelada
não é reescrita por nenhum destes caminhos.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    FolhaPagamento, FolhaRubrica, Pessoa, Usuario, ValeFuncionario, ValeParcela,
)
from fazenda.rules import rubrica_folha, verba_pagamento

from .rh_folha import (
    _competencia_seguinte,
    _competencias_do_vale,
    _conta_da_folha,
    _congelar_discriminacao,
    _exigir_competencias_nao_pagas,
    _exigir_teto_vale,
    _folha_resposta,
    _liquido_folha,
    _marcar_vale_aplicado,
    _reconciliar_vale_competencias,
    _valor_vale,
)
from .rh_folha import _recalcular_folha
from .rh_folha_rubricas import _propagar_aumento
from .rh_vale_acoes import (
    ACAO_PAGAMENTO_FOLHA,
    ValeAcaoIn,
    _acao_reparcelar,
    _assumir_no_financeiro,
    _fmt_brl,
    _lancar_devolucao_de_vale,
    _parcelas_do_vale,
    _parcelas_pendentes,
    _registrar_assuncao,
    _split_valores,
    _vale_da_fazenda,
)

router = APIRouter()

# Os destinos da diferença de uma parcela de VALE, na ordem em que o dono os
# enunciou. São rótulos DESTE fluxo (o que fazer com a diferença de um
# pagamento), e por isso não repetem os nomes das ações do vale:
# "desconsiderar" aqui vale para a diferença de um mês, e não para o vale
# inteiro (que continua sendo "cancelar", no painel de ações do #708).
#
# `acrescimo_avulso` é o quarto, e só existe para quem lançou a MAIS: o dono
# pediu que descontar mais do que a parcela previa passasse a oferecer
# "exatamente duas" saídas — reparcelar (o excedente antecipa o saldo do vale)
# e lançar o excedente como acréscimo avulso (o vale fica intacto e a
# diferença vira uma linha própria do holerite). Ver `_decisao_acrescimo`.
DECISOES = ("abater", "desconsiderar", "reparcelar", "acrescimo_avulso")

# As duas — e só estas duas — cabem quando se desconta MAIS do que o previsto.
# Escrito como constante porque é a lista que o teste tranca: "oferece as duas
# opções e só elas".
DECISOES_DESCONTOU_A_MAIS = ("reparcelar", "acrescimo_avulso")

# Tolerância de comparação de dinheiro: meio centavo. Abaixo disso os dois
# valores são o mesmo valor — e não existe diferença a decidir.
CENTAVO = 0.005


class VerbaPagaIn(BaseModel):
    """Uma parcela de VALE com o valor efetivamente descontado agora.

    Continua sendo a única verba cuja diferença abre as três/duas decisões:
    é a única que representa DÍVIDA DA PESSOA, e "abater", "a fazenda assume"
    e "reparcelar" só significam alguma coisa sobre uma dívida. As demais
    verbas agora também são editáveis, mas por outro caminho (ver
    `AlteracaoVerbaIn` e a docstring do módulo): nelas não há dívida, e o
    valor novo é simplesmente o valor novo."""

    parcela_id: int
    valor_pago: float


class RubricaPagaIn(BaseModel):
    """Uma rubrica avulsa do holerite com valor alterado no ato do pagamento.

    `confirmado` é a marca do CADEADO: nas rubricas contratuais (aumento na
    folha, indenização, reembolso, desconto de compra) o servidor recusa a
    alteração que chega sem ele. Não é enfeite de tela — é a diferença entre
    uma alteração contratual assumida e um número trocado sem querer."""

    rubrica_id: int
    valor_pago: float
    confirmado: bool = False


class SalarioPagoIn(BaseModel):
    """O salário lançado no ato do pagamento.

    Para MAIOR vira aumento incorporado; para MENOR é recusado com a mensagem
    do art. 468 da CLT. Ver `_conferir_salario`."""

    valor_pago: float
    confirmado: bool = False


class RetencaoPagaIn(BaseModel):
    """INSS ou IR com valor retido alterado no ato do pagamento."""

    tipo: str  # inss | ir
    valor_pago: float
    confirmado: bool = False


class OutrosDescontosIn(BaseModel):
    """`FolhaPagamento.descontos` — o desconto manual sem itemização. Verba
    LIVRE (o valor é o do mês, não uma promessa), por isso sem `confirmado`."""

    valor_pago: float


class DecisaoDiferencaIn(BaseModel):
    tipo: str  # abater | desconsiderar | reparcelar | acrescimo_avulso
    # abater: conta que RECEBEU a devolução em dinheiro — opcional, do mesmo
    # jeito que em `_lancar_devolucao_de_vale` (abatimento que é perdão não
    # tem devolução a lançar).
    conta_corrente_id: int | None = None
    # reparcelar
    parcelas: int | None = None
    competencia_inicio: str | None = None  # "AAAA-MM"; padrão: a competência seguinte
    motivo: str | None = None
    # Confirma prosseguir mesmo deixando alguma competência acima de 40% do
    # salário em desconto de vale (ver `_exigir_teto_vale`, em rh_folha.py).
    # Reparcelar no ato do pagamento era a terceira porta sem conferência
    # nenhuma: "reparcelar em 1x" no mês seguinte empilhava ali o saldo
    # inteiro, sem aviso.
    confirmar: bool = False


class PagarFolhaIn(BaseModel):
    data_pagamento: date
    verbas: list[VerbaPagaIn] = []
    # ── As verbas que a coluna de edição abriu (ver docstring do módulo) ──
    rubricas: list[RubricaPagaIn] = []
    retencoes: list[RetencaoPagaIn] = []
    salario: SalarioPagoIn | None = None
    outros_descontos: OutrosDescontosIn | None = None
    decisao: DecisaoDiferencaIn | None = None


def _folha_da_fazenda(session: Session, registro_id: int, fazenda_id: int | None) -> FolhaPagamento:
    """Carrega a folha JÁ FILTRANDO por fazenda na própria consulta — nunca
    `session.get()` seguido de `if registro.fazenda_id != fazenda_id`, que
    deixa passar a linha órfã (fazenda_id nulo do backfill). "De outra
    fazenda" e "sem fazenda" caem os dois em 404."""
    registro = session.exec(
        select(FolhaPagamento).where(
            FolhaPagamento.id == registro_id,
            FolhaPagamento.fazenda_id == fazenda_id,
        )
    ).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de folha não encontrado")
    return registro


def _parcela_da_folha(
    session: Session, registro: FolhaPagamento, parcela_id: int,
) -> ValeParcela:
    """A parcela de vale que é uma VERBA DESTA folha: mesma pessoa, mesma
    competência.

    O escopo de fazenda aqui é a própria folha, que já veio filtrada — mesmo
    raciocínio de `_contexto_discriminacao` em rh_folha.py: nenhuma parcela de
    outra fazenda alcança uma pessoa desta. Repetir
    `ValeParcela.fazenda_id == fazenda_id` aqui só serviria para dar 404 numa
    parcela órfã legítima da própria fazenda (o vale, esse sim, é carregado
    por `_vale_da_fazenda`, que aplica o filtro)."""
    parcela = session.exec(
        select(ValeParcela).where(
            ValeParcela.id == parcela_id,
            ValeParcela.pessoa_id == registro.pessoa_id,
            ValeParcela.competencia == registro.competencia,
        )
    ).first()
    if not parcela:
        raise HTTPException(
            status_code=404,
            detail="Esta verba não pertence ao lançamento de folha que está sendo pago.",
        )
    return parcela


def _pendentes_fora_do_mes(
    session: Session, vale: ValeFuncionario, competencia_paga: str, fazenda_id: int | None,
) -> list[ValeParcela]:
    """As parcelas em que a decisão ainda pode mexer: as pendentes do vale
    MENOS as da competência que está sendo paga agora.

    A exclusão é o ponto do módulo. `_parcelas_pendentes` (do #708) considera
    pendente tudo que não caiu em folha paga — e a folha deste mês ainda não
    está paga no instante em que a decisão roda. Deixá-la na lista faria, por
    exemplo, o rateio de um abatimento diminuir de novo a parcela que o dono
    acabou de fixar no valor que pagou."""
    parcelas = _parcelas_do_vale(session, vale.id)
    return [
        p for p in _parcelas_pendentes(session, vale, parcelas, fazenda_id)
        if p.competencia != competencia_paga
    ]


def _fixar_parcela_do_mes(session: Session, parcela: ValeParcela, pago: float) -> None:
    """A parcela passa a valer o que foi efetivamente descontado. Descontou
    zero: a parcela sai — parcela de R$ 0,00 é ruído no holerite ("Vale
    (parcela 2/3) — R$ 0,00"), mesma regra que `_acao_abater` já aplica."""
    if pago <= CENTAVO:
        session.delete(parcela)
        return
    parcela.valor = pago
    session.add(parcela)


def _decisao_abater(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcela: ValeParcela,
    pago: float, diferenca: float, decisao: DecisaoDiferencaIn, fazenda_id: int | None,
) -> dict:
    """Desconto/abatimento: o que não foi descontado deixa de ser cobrado.

    Não há rateio entre as parcelas pendentes (o que `_acao_abater` faz) e não
    poderia haver: aqui o abatimento já saiu de uma parcela concreta, a deste
    mês, que acabou de ser fixada no valor pago. As parcelas seguintes
    continuam como estavam — o prazo combinado não muda, exatamente a
    distinção que o #708 faz entre abater e reparcelar. O que é reusado é o
    outro lado, o do caixa: `_lancar_devolucao_de_vale`, para o dinheiro
    devolvido em mãos não sumir do extrato."""
    _fixar_parcela_do_mes(session, parcela, pago)
    vale.valor_abatido = round(vale.valor_abatido + diferenca, 2)
    session.add(vale)
    session.flush()

    numero_devolucao = None
    if decisao.conta_corrente_id:
        numero_devolucao = _lancar_devolucao_de_vale(
            session, vale, pessoa, diferenca, decisao.conta_corrente_id, fazenda_id,
        )
    saldo = round(sum(p.valor for p in _pendentes_fora_do_mes(session, vale, parcela.competencia, fazenda_id)), 2)
    return {
        "decisao": "abater",
        "valor": diferenca,
        "numero_lancamento_devolucao": numero_devolucao,
        "resumo": (
            f"R$ {_fmt_brl(diferenca)} abatidos do vale de {pessoa.nome} — deixam de ser cobrados e o "
            f"saldo a descontar ficou em R$ {_fmt_brl(saldo)}."
        ),
    }


def _decisao_desconsiderar(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcela: ValeParcela,
    pago: float, diferenca: float, motivo: str, fazenda_id: int | None,
) -> dict:
    """Desconsiderar — a fazenda assume: o valor deixa de ser cobrança da
    pessoa e vira despesa normal da fazenda, comunicada ao Financeiro.

    A parcela do mês se PARTE em duas: a cobrada (o que foi descontado) e a
    assumida, marcada com o motivo. Partir em vez de só marcar é o que
    permite desconsiderar um PEDAÇO do mês — `_acao_desconsiderar_mes`
    assume a competência inteira, que é a decisão de quem está olhando o vale,
    não a de quem está pagando um valor distinto.

    O efeito no Financeiro é o do #708, chamado e não recopiado:
    `_assumir_no_financeiro` divide o item da nota (ou reclassifica o
    lançamento próprio, quando nada mais será cobrado) e devolve o valor aos
    relatórios gerenciais como despesa comum da fazenda."""
    if pago <= CENTAVO:
        # Nada foi descontado: a própria parcela do mês é o que a fazenda
        # assume. Ela CONTINUA existindo, marcada — é o registro de que aquele
        # mês foi perdoado (ver o comentário de `ValeParcela`).
        parcela.assumida_pela_fazenda = True
        parcela.motivo_assuncao = motivo
        session.add(parcela)
        assumidas = [parcela]
    else:
        parcela.valor = pago
        session.add(parcela)
        assumida = ValeParcela(
            vale_id=vale.id, pessoa_id=vale.pessoa_id, competencia=parcela.competencia,
            valor=diferenca, aplicada=True,
            assumida_pela_fazenda=True, motivo_assuncao=motivo,
            fazenda_id=vale.fazenda_id,
        )
        session.add(assumida)
        assumidas = [assumida]
    vale.valor_assumido_fazenda = round(vale.valor_assumido_fazenda + diferenca, 2)
    session.add(vale)
    session.flush()

    total = all(p.assumida_pela_fazenda for p in _parcelas_do_vale(session, vale.id))
    financeiro = _assumir_no_financeiro(
        session, vale, pessoa, diferenca, total=total, motivo=motivo, fazenda_id=fazenda_id,
    )
    # O que a assunção fez no Financeiro fica gravado NA PARCELA, aqui pelo
    # mesmo motivo do #708: sem isso, desfazer depois seria adivinhar entre
    # "sem lastro" e "item de nota com o vínculo já solto" — e o palpite
    # errado conta a mesma despesa duas vezes. A ação registrada é
    # `pagamento_folha`, não `cancelar`: assim `reverter_cancelamento` nunca
    # devolve à cobrança uma diferença que foi decidida no ato do pagamento.
    _registrar_assuncao(session, assumidas, financeiro, ACAO_PAGAMENTO_FOLHA)
    return {
        "decisao": "desconsiderar",
        "valor": diferenca,
        "financeiro": financeiro,
        "resumo": (
            f"R$ {_fmt_brl(diferenca)} não serão cobrados de {pessoa.nome} — a fazenda assumiu o valor, "
            "que virou despesa dela no Financeiro."
        ),
    }


def _decisao_reparcelar(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcela: ValeParcela, pago: float,
    diferenca: float, decisao: DecisaoDiferencaIn, fazenda_id: int | None,
) -> dict:
    """Reparcelar o saldo: a diferença continua sendo dívida e é redistribuída
    nas competências seguintes, junto com o que ainda restava do vale.

    A diferença volta ao cronograma como uma parcela da primeira competência
    de destino, e daí em diante quem manda é `_acao_reparcelar` (do #708):
    ele apaga as parcelas pendentes, recria N com `_split_valores`, recusa
    competência de folha já paga (`_exigir_competencias_nao_pagas`) e
    reconcilia as folhas afetadas. Nada disso é reescrito aqui."""
    if not decisao.parcelas or decisao.parcelas < 1:
        raise HTTPException(status_code=400, detail="Informe em quantas parcelas a diferença será dividida.")
    inicio = (decisao.competencia_inicio or "").strip() or _competencia_seguinte(parcela.competencia)
    if inicio <= parcela.competencia:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A diferença só pode ser reparcelada a partir de {_competencia_seguinte(parcela.competencia)} — "
                f"a competência {parcela.competencia} é a que está sendo paga agora."
            ),
        )
    # Antes de gravar qualquer coisa: as competências de destino não podem ter
    # folha paga. `_acao_reparcelar` confere de novo (é a trava dele), mas
    # conferir aqui evita criar a parcela da diferença para depois abortar.
    competencias_destino = _competencias_do_vale(inicio, decisao.parcelas)
    _exigir_competencias_nao_pagas(
        session, vale.pessoa_id, competencias_destino, fazenda_id, "reparcelar",
    )
    # Teto de 40% do salário, também ANTES de gravar. `_acao_reparcelar`
    # confere de novo (é a trava dele, e é a que vale), mas o cronograma final
    # é previsível daqui: o saldo que sobra do vale MAIS a diferença que não
    # foi descontada agora, dividido em N a partir de `inicio`. Conferir aqui
    # evita criar a parcela da diferença para só então abortar — e é o mesmo
    # cuidado que a linha acima já tinha com a folha paga.
    pendentes_previstas = _pendentes_fora_do_mes(session, vale, parcela.competencia, fazenda_id)
    saldo_previsto = round(sum(p.valor for p in pendentes_previstas) + diferenca, 2)
    _exigir_teto_vale(
        session, vale.pessoa_id, pessoa.salario_base,
        list(zip(competencias_destino, _split_valores(saldo_previsto, decisao.parcelas))),
        confirmar=decisao.confirmar, verbo="reparcelar",
        parcela_ids_substituidas={p.id for p in pendentes_previstas},
    )

    _fixar_parcela_do_mes(session, parcela, pago)
    session.add(ValeParcela(
        vale_id=vale.id, pessoa_id=vale.pessoa_id, competencia=inicio,
        valor=diferenca, fazenda_id=vale.fazenda_id,
    ))
    session.flush()

    pendentes = _pendentes_fora_do_mes(session, vale, parcela.competencia, fazenda_id)
    saldo = round(sum(p.valor for p in pendentes), 2)
    resultado = _acao_reparcelar(
        session, vale, pessoa, pendentes, saldo,
        ValeAcaoIn(
            acao="reparcelar", parcelas=decisao.parcelas, competencia_inicio=inicio,
            confirmar=decisao.confirmar,
        ),
        fazenda_id,
    )
    return {
        "decisao": "reparcelar",
        "valor": diferenca,
        "competencias": resultado["competencias"],
        "resumo": (
            f"R$ {_fmt_brl(diferenca)} não descontados agora voltam para o saldo: "
            f"R$ {_fmt_brl(saldo)} em {decisao.parcelas}x a partir de {inicio}."
        ),
    }


def _decisao_antecipar(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcela: ValeParcela, pago: float,
    excesso: float, decisao: DecisaoDiferencaIn, fazenda_id: int | None,
) -> dict:
    """Descontou MAIS do que a parcela previa — o excedente é antecipação do
    saldo, e o que resta do vale precisa caber no que ainda é devido.

    É o único destino possível quando se paga a mais: não há valor não
    cobrado para abater nem para a fazenda assumir (o dinheiro foi descontado
    de verdade); o que muda é só o cronograma do que sobrou. Descontar mais do
    que o vale inteiro é recusado — viraria crédito do funcionário, que não é
    o que um desconto de vale representa."""
    pendentes = _pendentes_fora_do_mes(session, vale, parcela.competencia, fazenda_id)
    saldo_futuro = round(sum(p.valor for p in pendentes), 2)
    if excesso > saldo_futuro + CENTAVO:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não é possível descontar R$ {_fmt_brl(excesso)} a mais neste mês: o saldo restante do "
                f"vale é de R$ {_fmt_brl(saldo_futuro)}."
            ),
        )
    _fixar_parcela_do_mes(session, parcela, pago)
    saldo_novo = round(saldo_futuro - excesso, 2)

    if saldo_novo <= CENTAVO:
        competencias = sorted({p.competencia for p in pendentes})
        for p in pendentes:
            session.delete(p)
        session.flush()
        _reconciliar_vale_competencias(session, vale.pessoa_id, competencias)
        return {
            "decisao": "reparcelar",
            "valor": -excesso,
            "competencias": [],
            "resumo": (
                f"R$ {_fmt_brl(excesso)} descontados a mais quitaram o vale — não resta parcela nenhuma."
            ),
        }

    parcelas = decisao.parcelas or len(pendentes)
    inicio = (decisao.competencia_inicio or "").strip() or pendentes[0].competencia
    # `pessoa`/`confirmar` são repassados porque `_acao_reparcelar` confere o
    # teto de 40%: descontar a mais reduz o saldo, mas o novo cronograma ainda
    # pode concentrá-lo num mês só — e o dono precisa poder confirmar.
    resultado = _acao_reparcelar(
        session, vale, pessoa, pendentes, saldo_novo,
        ValeAcaoIn(
            acao="reparcelar", parcelas=parcelas, competencia_inicio=inicio, confirmar=decisao.confirmar,
        ),
        fazenda_id,
    )
    return {
        "decisao": "reparcelar",
        "valor": -excesso,
        "competencias": resultado["competencias"],
        "resumo": (
            f"R$ {_fmt_brl(excesso)} descontados a mais neste mês — o saldo caiu para "
            f"R$ {_fmt_brl(saldo_novo)}, em {parcelas}x a partir de {inicio}."
        ),
    }


def _nova_rubrica(
    registro: FolhaPagamento, especie: str, codigo: str, valor: float,
    descricao: str | None, fazenda_id: int | None, usuario_id: int | None,
) -> FolhaRubrica:
    """
    Monta uma linha avulsa do holerite a partir do CÓDIGO do catálogo — o
    mesmo enquadramento e a mesma cópia congelada que `criar_rubrica_folha`
    faz no POST /rubricas.

    Existe para os dois acréscimos que este módulo lança sozinho (o excedente
    de "acréscimo avulso" e o "aumento na folha" do salário para maior). O
    enquadramento nunca é escrito à mão aqui: sai do catálogo, senão um
    aumento lançado por este caminho ficaria fora das bases em que o mesmo
    aumento lançado pela tela de rubricas entra.
    """
    catalogo = (
        rubrica_folha.CATALOGO_VENCIMENTOS if especie == rubrica_folha.ESPECIE_VENCIMENTO
        else rubrica_folha.CATALOGO_DESCONTOS
    )
    verbete = catalogo[codigo]
    return FolhaRubrica(
        fazenda_id=fazenda_id,
        folha_id=registro.id,
        pessoa_id=registro.pessoa_id,
        competencia=registro.competencia,
        especie=especie,
        codigo=codigo,
        descricao=(descricao or "").strip() or None,
        valor=round(valor, 2),
        natureza=verbete.get("natureza", rubrica_folha.NATUREZA_SALARIAL),
        incide_inss=bool(verbete.get("incide_inss")),
        incide_irrf=bool(verbete.get("incide_irrf")),
        incide_fgts=bool(verbete.get("incide_fgts")),
        incorpora_base=bool(verbete.get("incorpora_base")),
        usuario_id=usuario_id,
    )


def _decisao_acrescimo(
    session: Session, registro: FolhaPagamento, excesso: float, motivo: str,
    fazenda_id: int | None, usuario_id: int | None,
) -> dict:
    """
    Acréscimo avulso: o que foi descontado a mais NÃO é vale — é uma cobrança
    própria deste mês, e o cronograma do vale fica exatamente como estava.

    A DIFERENÇA PARA REPARCELAR, que é o que o dono pediu para poder escolher:
    reparcelar trata o excedente como antecipação (o saldo do vale cai e as
    parcelas seguintes são refeitas); o acréscimo avulso não toca no vale
    nenhum — a parcela do mês continua valendo o que valia e o excedente vira
    uma linha separada do holerite, com fundamento próprio (CLT, art. 462:
    desconto autorizado pelo empregado). É a saída para quando o valor a mais
    não tem nada a ver com o vale: uma quebra, uma compra, um acerto do mês.

    REUSA A RUBRICA AVULSA QUE JÁ EXISTE (`FolhaRubrica` + `desconto_valor`),
    e não um segundo conceito de acréscimo: a linha aparece no recibo, entra
    no líquido por `_recalcular_folha` e pode ser conferida depois no painel
    de vencimentos e descontos do holerite, como qualquer outra.
    """
    session.add(_nova_rubrica(
        registro, rubrica_folha.ESPECIE_DESCONTO, "desconto_valor", excesso,
        motivo, fazenda_id, usuario_id,
    ))
    session.flush()
    return {
        "decisao": "acrescimo_avulso",
        "valor": -excesso,
        "resumo": (
            f"R$ {_fmt_brl(excesso)} descontados a mais neste mês entraram como desconto avulso no "
            f"holerite — o vale de {registro.competencia} continua com o mesmo saldo e o mesmo prazo."
        ),
    }


def _aplicar_decisao(
    session: Session, registro: FolhaPagamento, pessoa: Pessoa, parcela: ValeParcela,
    previsto: float, pago: float, decisao: DecisaoDiferencaIn, fazenda_id: int | None,
    usuario_id: int | None = None,
) -> dict:
    vale = _vale_da_fazenda(session, parcela.vale_id, fazenda_id)
    if vale.status == "cancelado":
        raise HTTPException(
            status_code=400,
            detail="Este vale já foi cancelado — o saldo dele já virou despesa da fazenda.",
        )
    diferenca = round(previsto - pago, 2)
    motivo = (decisao.motivo or "").strip() or f"diferença no pagamento da folha de {registro.competencia}"

    if diferenca < 0:
        if decisao.tipo not in DECISOES_DESCONTOU_A_MAIS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Foram descontados R$ {_fmt_brl(-diferenca)} a mais do que a parcela deste mês. Não há "
                    "valor deixado de cobrar para abater nem para a fazenda assumir — o que cabe decidir é "
                    "se o excedente antecipa o saldo do vale (reparcelar) ou se é uma cobrança própria "
                    "deste mês (lançar acréscimo avulso)."
                ),
            )
        if decisao.tipo == "acrescimo_avulso":
            # Nem o vale nem a parcela entram: é justamente o ponto desta
            # decisão — o excedente não toca no vale.
            return _decisao_acrescimo(session, registro, -diferenca, motivo, fazenda_id, usuario_id)
        return _decisao_antecipar(session, vale, pessoa, parcela, pago, -diferenca, decisao, fazenda_id)

    if decisao.tipo == "acrescimo_avulso":
        raise HTTPException(
            status_code=400,
            detail=(
                "Lançar acréscimo avulso só cabe quando se desconta MAIS do que a parcela previa. "
                "Descontando menos, o que se decide é o destino do valor que deixou de ser cobrado."
            ),
        )

    if decisao.tipo == "abater":
        return _decisao_abater(session, vale, pessoa, parcela, pago, diferenca, decisao, fazenda_id)
    if decisao.tipo == "desconsiderar":
        return _decisao_desconsiderar(session, vale, pessoa, parcela, pago, diferenca, motivo, fazenda_id)
    return _decisao_reparcelar(session, vale, pessoa, parcela, pago, diferenca, decisao, fazenda_id)


# ---------------------------------------------------------------------------
# A coluna de edição: alterar as DEMAIS verbas no ato do pagamento
#
# Tudo aqui é conferido ANTES de gravar (`_conferir_*`) e só depois aplicado
# (`_aplicar_alteracoes`). A ordem não é estilo: a recusa do salário para
# menor tem de acontecer com o banco intacto, senão uma folha teria começado a
# ser alterada por causa de um pedido que a lei não permite atender.
# ---------------------------------------------------------------------------
def _exigir_confirmacao(classe: str, confirmado: bool) -> None:
    """A trava do CADEADO, do lado do servidor.

    Ela existe aqui — e não só na tela — pelo mesmo motivo de todas as outras
    deste módulo: a tela é um cliente, e um POST feito por fora dela chegaria
    com a mesma autorização. Uma alteração contratual que a fazenda não
    assumiu não pode entrar por essa porta."""
    if verba_pagamento.exige_confirmacao(classe) and not confirmado:
        raise HTTPException(status_code=400, detail=verba_pagamento.MENSAGEM_SEM_CONFIRMACAO)


def _rubrica_da_folha(
    session: Session, registro: FolhaPagamento, rubrica_id: int, fazenda_id: int | None,
) -> FolhaRubrica:
    """A rubrica que é linha DESTA folha — com o filtro de fazenda e o de
    folha DENTRO da consulta.

    "De outra fazenda", "de outra folha" e "sem fazenda" caem os três em 404:
    responder 403 confirmaria que o id existe em algum lugar, e responder 200
    deixaria o pagamento de uma folha reescrever a rubrica de outra."""
    rubrica = session.exec(
        select(FolhaRubrica).where(
            FolhaRubrica.id == rubrica_id,
            FolhaRubrica.folha_id == registro.id,
            FolhaRubrica.fazenda_id == fazenda_id,
        )
    ).first()
    if not rubrica:
        raise HTTPException(
            status_code=404,
            detail="Esta verba não pertence ao lançamento de folha que está sendo pago.",
        )
    return rubrica


def _conferir_rubricas(
    session: Session, registro: FolhaPagamento, dados: PagarFolhaIn, fazenda_id: int | None,
) -> list[tuple[FolhaRubrica, float]]:
    """Confere as rubricas alteradas e devolve os pares (rubrica, valor novo)
    que realmente mudaram."""
    planos: list[tuple[FolhaRubrica, float]] = []
    for pedido in dados.rubricas:
        rubrica = _rubrica_da_folha(session, registro, pedido.rubrica_id, fazenda_id)
        novo = round(pedido.valor_pago, 2)
        if abs(round(rubrica.valor, 2) - novo) <= CENTAVO:
            continue
        # Valor sempre POSITIVO, a mesma regra de `_validar_valor` no router
        # de rubricas: quem diz se soma ou subtrai é a espécie, não o sinal.
        # Zerar não é "editar para zero" — é excluir a linha, e isso se faz
        # em "Editar lançamento", com a linha sumindo do recibo.
        if novo <= 0:
            # A saída indicada depende de QUEM manda no valor: a verba gerada
            # pelo cadastro (vale-alimentação) não tem linha para excluir — a
            # exclusão dela é desmarcar o benefício no cadastro do funcionário.
            saida = (
                "Para tirar a verba do holerite, desmarque o benefício no cadastro do funcionário."
                if rubrica_folha.gerado_por_cadastro(rubrica.codigo, rubrica.especie)
                else "Para tirar a verba do holerite, exclua a linha antes de pagar."
            )
            raise HTTPException(
                status_code=400,
                detail=f"Informe um valor maior que zero para “{rubrica_folha.rotulo_rubrica(rubrica)}”. {saida}",
            )
        _exigir_confirmacao(
            verba_pagamento.classe_da_rubrica(rubrica.codigo, rubrica.especie), pedido.confirmado,
        )
        planos.append((rubrica, novo))
    return planos


def _conferir_retencoes(dados: PagarFolhaIn, registro: FolhaPagamento) -> list[tuple[str, float]]:
    """Confere INSS/IR e devolve os pares ("inss"|"ir", valor novo)."""
    planos: list[tuple[str, float]] = []
    for pedido in dados.retencoes:
        if pedido.tipo not in ("inss", "ir"):
            raise HTTPException(status_code=400, detail="Retenção desconhecida (inss ou ir).")
        atual = round(getattr(registro, f"valor_{pedido.tipo}") or 0.0, 2)
        novo = round(pedido.valor_pago, 2)
        if abs(atual - novo) <= CENTAVO:
            continue
        if novo < 0:
            raise HTTPException(status_code=400, detail="O valor retido não pode ser negativo.")
        _exigir_confirmacao(verba_pagamento.classe_da_linha(pedido.tipo), pedido.confirmado)
        planos.append((pedido.tipo, novo))
    return planos


def _conferir_salario(registro: FolhaPagamento, pessoa: Pessoa, dados: PagarFolhaIn) -> float:
    """
    O salário lançado no ato do pagamento — devolve a DIFERENÇA a incorporar
    (0.0 quando não há alteração).

    AS TRÊS SAÍDAS, na ordem em que a lei as impõe:

    1. Para MENOR: 400, e só — inclusive ANTES de conferir o cadeado, porque
       a alteração contratual lesiva ao empregado é NULA (CLT, art. 468) e não
       existe "confirmar mesmo assim". O caminho de reduzir salário, quando
       ele é legítimo, é o cadastro da pessoa, e a mensagem diz isso.
    2. Para MAIOR, mas com o bruto do mês diferente do salário-base do
       cadastro: também 400, por outro motivo. Ver
       `verba_pagamento.pode_virar_novo_salario` — sem os dois pontos de
       partida coincidindo, a diferença digitada não é um aumento de salário,
       e gravá-la como se fosse inventaria um contrato.
    3. Para MAIOR com os dois batendo: a diferença é o aumento.
    """
    if dados.salario is None:
        return 0.0
    previsto = round(registro.valor_bruto, 2)
    informado = round(dados.salario.valor_pago, 2)
    direcao = verba_pagamento.direcao_do_salario(previsto, informado)
    if direcao == "igual":
        return 0.0
    if direcao == "menor":
        # ANTES da conferência do cadeado, de propósito: a redução é nula
        # confirmada ou não, e mandar o usuário "confirmar o aviso" antes de
        # dizer que a alteração é proibida seria oferecer um caminho que não
        # existe. A frase é a MESMA da tela, palavra por palavra (ver
        # `verba_pagamento.MENSAGEM_SALARIO_MENOR`): a recusa que o usuário lê
        # no pop-up e a que o servidor devolve não podem ser duas recusas
        # diferentes para o mesmo fato.
        raise HTTPException(status_code=400, detail=verba_pagamento.MENSAGEM_SALARIO_MENOR)
    _exigir_confirmacao(verba_pagamento.CLASSE_SALARIO, dados.salario.confirmado)
    if not verba_pagamento.pode_virar_novo_salario(previsto, pessoa.salario_base):
        raise HTTPException(
            status_code=400,
            detail=verba_pagamento.MENSAGEM_SALARIO_SEM_REFERENCIA.format(
                bruto=f"R$ {_fmt_brl(previsto)}",
                base=f"R$ {_fmt_brl(round(pessoa.salario_base or 0.0, 2))}",
            ),
        )
    return round(informado - previsto, 2)


def _conferir_outros_descontos(registro: FolhaPagamento, dados: PagarFolhaIn) -> float | None:
    """`FolhaPagamento.descontos` — None quando não há alteração."""
    if dados.outros_descontos is None:
        return None
    novo = round(dados.outros_descontos.valor_pago, 2)
    if abs(round(registro.descontos, 2) - novo) <= CENTAVO:
        return None
    if novo < 0:
        raise HTTPException(status_code=400, detail="O valor do desconto não pode ser negativo.")
    return novo


def _aplicar_alteracoes(
    session: Session, registro: FolhaPagamento, rubricas: list[tuple[FolhaRubrica, float]],
    aumento_salario: float, fazenda_id: int | None, usuario_id: int | None,
) -> list[dict]:
    """
    Grava as alterações já conferidas — as que mexem em RUBRICA e no SALÁRIO.

    Retenções e "outros descontos" ficam de fora de propósito: elas têm de ser
    escritas DEPOIS de `_recalcular_folha`, senão o recálculo das retenções a
    partir do percentual apagaria o valor que o usuário acabou de digitar.
    Ver a ordem no endpoint.
    """
    aplicadas: list[dict] = []
    for rubrica, novo in rubricas:
        rotulo = rubrica_folha.rotulo_rubrica(rubrica)
        anterior = round(rubrica.valor, 2)
        # A DIFERENÇA é o que se propaga quando a rubrica é o aumento — mesma
        # razão do PUT /rubricas/{id}: propagar o valor inteiro somaria uma
        # segunda vez um aumento que a base já tinha.
        diferenca = round(novo - anterior, 2)
        rubrica.valor = novo
        session.add(rubrica)
        session.flush()
        incorporacao = (
            _propagar_aumento(session, registro, diferenca, fazenda_id)
            if rubrica.incorpora_base else None
        )
        aplicadas.append({
            "verba": "rubrica",
            "rubrica_id": rubrica.id,
            "de": anterior,
            "para": novo,
            "incorporacao": incorporacao,
            "resumo": f"{rotulo}: R$ {_fmt_brl(anterior)} → R$ {_fmt_brl(novo)}.",
        })

    if aumento_salario:
        # O AUMENTO NÃO REESCREVE `valor_bruto`. Ele entra como a rubrica
        # `aumento_folha` da diferença — a verba que o sistema já tem para
        # "novo salário daquele momento em diante" (CLT, art. 468) — e
        # `_propagar_aumento` faz o resto: soma a diferença a
        # `Pessoa.salario_base`, corrige as competências seguintes que ainda
        # não foram pagas e NÃO toca em nenhuma folha paga nem em competência
        # passada. Reescrever `valor_bruto` deste mês teria o efeito contrário
        # do pedido: mudaria só o mês, e o salário do cadastro continuaria o
        # antigo no mês seguinte.
        rubrica = _nova_rubrica(
            registro, rubrica_folha.ESPECIE_VENCIMENTO, "aumento_folha", aumento_salario,
            f"aumento lançado no pagamento da folha de {registro.competencia}",
            fazenda_id, usuario_id,
        )
        session.add(rubrica)
        session.flush()
        incorporacao = _propagar_aumento(session, registro, aumento_salario, fazenda_id)
        aplicadas.append({
            "verba": "salario",
            "rubrica_id": rubrica.id,
            "de": round(registro.valor_bruto, 2),
            "para": round(registro.valor_bruto + aumento_salario, 2),
            "incorporacao": incorporacao,
            "resumo": (
                f"Aumento de R$ {_fmt_brl(aumento_salario)} lançado nesta competência — o salário-base "
                f"passou a R$ {_fmt_brl(round(incorporacao.get('salario_base') or 0.0, 2))} a partir daqui."
            ),
        })
    return aplicadas


@router.post("/folha-pagamento/{registro_id}/pagar")
def pagar_folha_com_verbas(
    registro_id: int, dados: PagarFolhaIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
) -> dict:
    """Paga a folha podendo lançar, no ato, valor distinto do previsto nas
    verbas — e decidindo o destino da diferença de vale.

    QUEM PODE SER ALTERADO, e sob que condição, está em
    `rules/verba_pagamento.py` e resumido na docstring do módulo: as verbas
    LIVRES (parcela de vale, bonificação, gueltas, vale-transporte, desconto
    em folha, "outros descontos") mudam direto; as CONTRATUAIS (salário,
    aumento incorporado, INSS, IR, indenização, reembolso, desconto de
    compra) exigem a confirmação do cadeado; e o salário para MENOR é recusado
    sempre, com a mensagem do art. 468 da CLT.

    Só a parcela de VALE abre as decisões de diferença: é a única verba que
    representa dívida da pessoa, e "abater", "a fazenda assume", "reparcelar"
    e "lançar acréscimo avulso" só significam alguma coisa sobre uma dívida.
    Nas demais, o valor novo é simplesmente o valor novo.

    Sem nada alterado, este endpoint é o "Marcar como pago" de sempre: data
    do pagamento, baixa da conta a pagar e congelamento da discriminação. Com
    diferença de vale e SEM decisão, recusa — é o pedido do dono, e é também o
    único jeito de a fotografia congelada continuar batendo com o dinheiro que
    saiu.
    """
    registro = _folha_da_fazenda(session, registro_id, fazenda_id)
    # Folha paga recusa TUDO, sem exceção — e a conferência é dupla de
    # propósito: `status` é o que a tela mostra, mas quem manda no recibo é o
    # congelamento (`_congelar_discriminacao`). Uma folha congelada que
    # tivesse perdido o status continuaria com a fotografia gravada, e
    # deixá-la ser paga de novo reescreveria o líquido por baixo dela.
    if registro.status == "pago" or registro.discriminacao_congelada_em is not None:
        raise HTTPException(status_code=400, detail="Este lançamento de folha já está pago.")
    pessoa = session.exec(
        select(Pessoa).where(Pessoa.id == registro.pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    # (1) Mede a diferença de cada verba ANTES de mexer em qualquer coisa: a
    # recusa por falta de decisão — e, mais ainda, a recusa do salário para
    # menor — tem de acontecer com o banco intacto.
    ajustes: list[tuple[ValeParcela, float, float]] = []
    for verba in dados.verbas:
        parcela = _parcela_da_folha(session, registro, verba.parcela_id)
        if parcela.assumida_pela_fazenda:
            raise HTTPException(
                status_code=400,
                detail="Esta parcela já foi assumida pela fazenda neste mês — ela não é descontada de ninguém.",
            )
        if verba.valor_pago < 0:
            raise HTTPException(status_code=400, detail="O valor pago de uma verba não pode ser negativo.")
        previsto = round(parcela.valor, 2)
        pago = round(verba.valor_pago, 2)
        if abs(previsto - pago) <= CENTAVO:
            continue
        ajustes.append((parcela, previsto, pago))

    planos_rubricas = _conferir_rubricas(session, registro, dados, fazenda_id)
    planos_retencoes = _conferir_retencoes(dados, registro)
    aumento_salario = _conferir_salario(registro, pessoa, dados)
    novos_outros = _conferir_outros_descontos(registro, dados)

    decisoes: list[dict] = []
    if ajustes:
        if dados.decisao is None or dados.decisao.tipo not in DECISOES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Há diferença entre o previsto e o pago. Escolha o que fazer com ela antes de "
                    "confirmar: lançar como desconto, desconsiderar (a fazenda assume), reparcelar o "
                    "saldo ou lançar acréscimo avulso."
                ),
            )
        for parcela, previsto, pago in ajustes:
            decisoes.append(_aplicar_decisao(
                session, registro, pessoa, parcela, previsto, pago, dados.decisao, fazenda_id, user.id,
            ))
        session.flush()

    # (1b) As alterações da coluna de edição. Rubrica e salário PRIMEIRO,
    # porque as duas mexem nas rubricas da folha e o recálculo precisa vê-las.
    alteracoes = _aplicar_alteracoes(
        session, registro, planos_rubricas, aumento_salario, fazenda_id, user.id,
    )
    # O recálculo roda SÓ quando alguma FolhaRubrica mudou — as alterações de
    # rubrica/salário, ou a decisão de acréscimo avulso, que cria uma linha.
    # A condição é estreita de propósito: `_recalcular_folha` também refaz as
    # retenções a partir do percentual gravado, e chamá-la num pagamento que
    # só mexeu no vale apagaria um INSS que o contador tivesse digitado à mão
    # em "Editar lançamento" — um valor que ninguém pediu para mudar.
    if alteracoes or any(d.get("decisao") == "acrescimo_avulso" for d in decisoes):
        # Refaz somas de rubrica, bases e retenções por percentual, o líquido
        # e a conta a pagar — a MESMA função do router de rubricas, não uma
        # segunda conta escrita aqui.
        _recalcular_folha(session, registro)

    # (1c) Retenção digitada à mão e "outros descontos" vêm DEPOIS do
    # recálculo, e o percentual é zerado junto: enquanto houver percentual
    # gravado, `retencoes_recalculadas` recalcula o valor a partir dele e
    # apagaria o número que o usuário acabou de digitar. Zerar o percentual é
    # o que o próprio formulário de folha já faz quando o valor é informado
    # direto — e é o que faz a linha do recibo dizer "Valor informado, sem
    # percentual" em vez de exibir um percentual que não produz aquele valor.
    for tipo, novo in planos_retencoes:
        anterior = round(getattr(registro, f"valor_{tipo}") or 0.0, 2)
        setattr(registro, f"valor_{tipo}", novo)
        setattr(registro, f"percentual_{tipo}", 0.0)
        alteracoes.append({
            "verba": tipo, "de": anterior, "para": novo,
            "resumo": (
                f"{'INSS' if tipo == 'inss' else 'IR'}: R$ {_fmt_brl(anterior)} → R$ {_fmt_brl(novo)} "
                "(valor informado, sem percentual)."
            ),
        })
    if novos_outros is not None:
        anterior = round(registro.descontos, 2)
        registro.descontos = novos_outros
        alteracoes.append({
            "verba": "outros", "de": anterior, "para": novos_outros,
            "resumo": f"Outros descontos: R$ {_fmt_brl(anterior)} → R$ {_fmt_brl(novos_outros)}.",
        })

    # (2) O pagamento. O líquido é recalculado com o vale e as verbas JÁ
    # ajustados — é este número que vai para a conta a pagar e para a
    # fotografia do recibo.
    valor_vale = _valor_vale(session, registro.pessoa_id, registro.competencia)
    valor_liquido = _liquido_folha(
        registro.valor_bruto, registro.descontos, registro.valor_inss, registro.valor_ir, valor_vale,
        registro.valor_rubricas,
    )
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")
    registro.valor_vale = valor_vale
    registro.valor_liquido = valor_liquido
    registro.data_pagamento = dados.data_pagamento
    registro.status = "pago"
    _marcar_vale_aplicado(session, registro.pessoa_id, registro.competencia)
    session.add(registro)

    conta = _conta_da_folha(session, registro, fazenda_id)
    if conta is not None and conta.valor_pago is None:
        conta.valor_total = valor_liquido
        conta.data_pagamento = dados.data_pagamento
        conta.valor_pago = valor_liquido
        session.add(conta)

    # Congela DEPOIS do flush: a fotografia precisa enxergar as parcelas já
    # ajustadas pela decisão, senão o recibo diria o desconto que não houve.
    session.flush()
    _congelar_discriminacao(session, registro)
    session.commit()
    session.refresh(registro)
    return {**_folha_resposta(registro), "decisoes": decisoes, "alteracoes": alteracoes}
