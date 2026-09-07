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
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import FolhaPagamento, Pessoa, ValeFuncionario, ValeParcela

from .rh_folha import (
    _competencia_seguinte,
    _competencias_do_vale,
    _conta_da_folha,
    _congelar_discriminacao,
    _exigir_competencias_nao_pagas,
    _folha_resposta,
    _liquido_folha,
    _marcar_vale_aplicado,
    _reconciliar_vale_competencias,
    _valor_vale,
)
from .rh_vale_acoes import (
    ValeAcaoIn,
    _acao_reparcelar,
    _assumir_no_financeiro,
    _fmt_brl,
    _lancar_devolucao_de_vale,
    _parcelas_do_vale,
    _parcelas_pendentes,
    _vale_da_fazenda,
)

router = APIRouter()

# Os três destinos da diferença, na ordem em que o dono os enunciou. São
# rótulos DESTE fluxo (o que fazer com a diferença de um pagamento), e por
# isso não repetem os nomes das ações do vale: "desconsiderar" aqui vale para
# a diferença de um mês, e não para o vale inteiro (que continua sendo
# "cancelar", no painel de ações do #708).
DECISOES = ("abater", "desconsiderar", "reparcelar")

# Tolerância de comparação de dinheiro: meio centavo. Abaixo disso os dois
# valores são o mesmo valor — e não existe diferença a decidir.
CENTAVO = 0.005


class VerbaPagaIn(BaseModel):
    """Uma verba do holerite com o valor efetivamente pago/descontado agora.

    Hoje só parcela de vale é editável (ver a docstring do endpoint): é a
    única verba que representa DÍVIDA DA PESSOA, e as três decisões da
    diferença só fazem sentido sobre uma dívida."""

    parcela_id: int
    valor_pago: float


class DecisaoDiferencaIn(BaseModel):
    tipo: str  # abater | desconsiderar | reparcelar
    # abater: conta que RECEBEU a devolução em dinheiro — opcional, do mesmo
    # jeito que em `_lancar_devolucao_de_vale` (abatimento que é perdão não
    # tem devolução a lançar).
    conta_corrente_id: int | None = None
    # reparcelar
    parcelas: int | None = None
    competencia_inicio: str | None = None  # "AAAA-MM"; padrão: a competência seguinte
    motivo: str | None = None


class PagarFolhaIn(BaseModel):
    data_pagamento: date
    verbas: list[VerbaPagaIn] = []
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
    else:
        parcela.valor = pago
        session.add(parcela)
        session.add(ValeParcela(
            vale_id=vale.id, pessoa_id=vale.pessoa_id, competencia=parcela.competencia,
            valor=diferenca, aplicada=True,
            assumida_pela_fazenda=True, motivo_assuncao=motivo,
            fazenda_id=vale.fazenda_id,
        ))
    vale.valor_assumido_fazenda = round(vale.valor_assumido_fazenda + diferenca, 2)
    session.add(vale)
    session.flush()

    total = all(p.assumida_pela_fazenda for p in _parcelas_do_vale(session, vale.id))
    financeiro = _assumir_no_financeiro(
        session, vale, pessoa, diferenca, total=total, motivo=motivo, fazenda_id=fazenda_id,
    )
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
    session: Session, vale: ValeFuncionario, parcela: ValeParcela, pago: float, diferenca: float,
    decisao: DecisaoDiferencaIn, fazenda_id: int | None,
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
    _exigir_competencias_nao_pagas(
        session, vale.pessoa_id, _competencias_do_vale(inicio, decisao.parcelas), fazenda_id, "reparcelar",
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
        session, vale, pendentes, saldo,
        ValeAcaoIn(acao="reparcelar", parcelas=decisao.parcelas, competencia_inicio=inicio),
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
    session: Session, vale: ValeFuncionario, parcela: ValeParcela, pago: float, excesso: float,
    decisao: DecisaoDiferencaIn, fazenda_id: int | None,
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
    resultado = _acao_reparcelar(
        session, vale, pendentes, saldo_novo,
        ValeAcaoIn(acao="reparcelar", parcelas=parcelas, competencia_inicio=inicio),
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


def _aplicar_decisao(
    session: Session, registro: FolhaPagamento, pessoa: Pessoa, parcela: ValeParcela,
    previsto: float, pago: float, decisao: DecisaoDiferencaIn, fazenda_id: int | None,
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
        if decisao.tipo != "reparcelar":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Foram descontados R$ {_fmt_brl(-diferenca)} a mais do que a parcela deste mês. Não há "
                    "valor deixado de cobrar para abater nem para a fazenda assumir — o que cabe decidir é "
                    "como fica o saldo restante do vale (reparcelar)."
                ),
            )
        return _decisao_antecipar(session, vale, parcela, pago, -diferenca, decisao, fazenda_id)

    if decisao.tipo == "abater":
        return _decisao_abater(session, vale, pessoa, parcela, pago, diferenca, decisao, fazenda_id)
    if decisao.tipo == "desconsiderar":
        return _decisao_desconsiderar(session, vale, pessoa, parcela, pago, diferenca, motivo, fazenda_id)
    return _decisao_reparcelar(session, vale, parcela, pago, diferenca, decisao, fazenda_id)


@router.post("/folha-pagamento/{registro_id}/pagar")
def pagar_folha_com_verbas(
    registro_id: int, dados: PagarFolhaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
) -> dict:
    """Paga a folha podendo lançar, no ato, valor distinto do previsto numa
    verba — e decidindo o destino da diferença.

    Só parcela de VALE é editável: é a única verba do holerite que representa
    dívida da pessoa, e "abater", "a fazenda assume" e "reparcelar" são as
    três coisas que se pode fazer com uma dívida não cobrada. Salário, INSS,
    IR e rubricas não são dívida de ninguém — mudá-los é corrigir o
    lançamento, o que já se faz em "Editar lançamento" antes de pagar (e que
    tem o próprio aviso de líquido diferente).

    Sem verba divergente, este endpoint é o "Marcar como pago" de sempre: data
    do pagamento, baixa da conta a pagar e congelamento da discriminação. Com
    diferença e SEM decisão, recusa — é o pedido do dono, e é também o único
    jeito de a fotografia congelada continuar batendo com o dinheiro que saiu.
    """
    registro = _folha_da_fazenda(session, registro_id, fazenda_id)
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Este lançamento de folha já está pago.")
    pessoa = session.exec(
        select(Pessoa).where(Pessoa.id == registro.pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    # (1) Mede a diferença de cada verba ANTES de mexer em qualquer coisa: a
    # recusa por falta de decisão tem de acontecer com o banco intacto.
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

    decisoes: list[dict] = []
    if ajustes:
        if dados.decisao is None or dados.decisao.tipo not in DECISOES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Há diferença entre o previsto e o pago. Escolha o que fazer com ela antes de "
                    "confirmar: lançar como desconto, desconsiderar (a fazenda assume) ou reparcelar o saldo."
                ),
            )
        for parcela, previsto, pago in ajustes:
            decisoes.append(
                _aplicar_decisao(session, registro, pessoa, parcela, previsto, pago, dados.decisao, fazenda_id)
            )
        session.flush()

    # (2) O pagamento. O líquido é recalculado com o vale JÁ ajustado — é este
    # número que vai para a conta a pagar e para a fotografia do recibo.
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
    return {**_folha_resposta(registro), "decisoes": decisoes}
