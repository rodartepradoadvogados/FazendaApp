"""
Cadastro > Folha de Pagamento > ações sobre um vale JÁ lançado.

O QUE ISTO FECHA. O vale aparecia na folha e era imutável na prática: as
únicas saídas eram `PUT /vales` (que apaga todas as parcelas e recria com
split igual — perde qualquer ajuste fino) e `DELETE /vales` (que apaga o
vale inteiro, incluindo a saída de caixa que ACONTECEU). Nenhuma das duas
serve para o que o dono faz no dia a dia, que são quatro decisões distintas:

 1. reparcelar       — o SALDO que resta é redistribuído em N parcelas nos
                       meses seguintes (renegociação de prazo).
 2. abater           — um valor é abatido do vale (o funcionário devolveu
                       parte em dinheiro, o dono perdoou um pedaço).
 3. desconsiderar_mes— o vale NÃO é descontado do funcionário naquele mês;
                       aquele valor passa a ser assumido pela fazenda.
 4. cancelar         — o vale inteiro deixa de ser cobrança do funcionário;
                       mesmo destino de (3) quanto ao Financeiro.

A DECISÃO DO DONO, LITERAL, sobre (3) e (4): "Desconsiderar o vale faz a
conta passar a ser da fazenda, apenas fazendo aquele valor ser assumido pela
fazenda e comunicar com o financeiro completo." É isso que
`_assumir_no_financeiro` implementa — o valor não some, ele MUDA DE DONO: sai
de "adiantamento a receber da pessoa" e vira despesa comum da fazenda, no
mesmo centro de custo/conta gerencial que o gasto já tinha.

POR QUE NENHUMA DAS QUATRO APAGA O VALE. O dinheiro do vale saiu de verdade
(ou a compra foi feita de verdade). Apagar o registro faria o extrato perder
uma saída de caixa que existiu; por isso `cancelar` é um `status`, e
`desconsiderar_mes` é uma marca na parcela — a parcela continua lá para o
holerite daquele mês poder explicar por que o desconto sumiu.

MULTI-FAZENDA. Todo carregamento por id filtra a fazenda DENTRO da consulta
(`_vale_da_fazenda`), com `== fazenda_id` incondicional: "de outra fazenda" e
"sem fazenda" caem os dois em 404, e nunca 403 (403 confirmaria que o id
existe). Escrita usa `get_fazenda_id_escrita`, não o par tolerante
`get_fazenda_atual_id` + `fazenda_id_seguro`.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import ContaCorrente, ContaGerencial, Pessoa, ValeFuncionario, ValeParcela
from fazenda.api.routers.financeiro import _proximo_numero_lancamento, rotulo_conta_corrente
from fazenda.rules.vale_item import dividir_item_de_lancamento, itens_do_vale, limpar_vinculo_de_itens

from .rh_folha import (
    _competencias_do_vale,
    _exigir_competencias_nao_pagas,
    _reconciliar_vale_competencias,
    _vale_competencia_paga,
)

router = APIRouter()

ACOES_VALE = ("reparcelar", "abater", "desconsiderar_mes", "cancelar")

# Rótulo do lançamento de vale no extrato depois que a fazenda assume a conta
# — deixa de ser "Vale de funcionário" (tipo de baixa espelhada, ver
# TIPOS_DOCUMENTO_BAIXA_ESPELHADA em financeiro.py) e passa a ser um
# documento comum, estornável/editável como qualquer despesa da fazenda.
TIPO_DOCUMENTO_ASSUMIDO = "Recibo"


def _fmt_brl(valor: float | None) -> str:
    return f"{float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _vale_da_fazenda(session: Session, vale_id: int, fazenda_id: int | None) -> ValeFuncionario:
    """Carrega o vale JÁ FILTRANDO por fazenda na própria consulta.

    Não é `session.get()` + `if vale.fazenda_id not in (None, fazenda_id)`:
    esse `if` (espalhado pelo projeto) deixa passar o registro ÓRFÃO — o que
    ficou com `fazenda_id` nulo na migração de backfill —, que assim seria
    editável por qualquer tenant. Filtrando na consulta, "de outra fazenda" e
    "sem fazenda" caem os dois no mesmo lugar: 404. Nunca 403, que
    confirmaria a existência do id para quem não pode vê-lo."""
    vale = session.exec(
        select(ValeFuncionario).where(
            ValeFuncionario.id == vale_id,
            ValeFuncionario.fazenda_id == fazenda_id,
        )
    ).first()
    if not vale:
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    return vale


def _parcelas_do_vale(session: Session, vale_id: int) -> list[ValeParcela]:
    parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    return sorted(parcelas, key=lambda p: (p.competencia, p.id or 0))


def _parcelas_pendentes(
    session: Session, vale: ValeFuncionario, parcelas: list[ValeParcela], fazenda_id: int | None,
) -> list[ValeParcela]:
    """As parcelas em que ainda dá para mexer: nem assumidas pela fazenda,
    nem já absorvidas por uma folha PAGA. Folha paga é imutável (a
    discriminação dela foi congelada no pagamento — ver rh_folha.py), então
    reparcelar/abater só pode alcançar o que ainda não foi descontado."""
    return [
        p for p in parcelas
        if not p.assumida_pela_fazenda
        and not _vale_competencia_paga(session, vale.pessoa_id, [p.competencia], fazenda_id)
    ]


def _split_valores(total: float, partes: int) -> list[float]:
    """Divide `total` em `partes` iguais com a ÚLTIMA absorvendo o
    arredondamento — mesma regra de `criar_vale`, para a soma fechar."""
    base = round(total / partes, 2)
    valores = [base] * (partes - 1)
    valores.append(round(total - base * (partes - 1), 2))
    return valores


def _assumir_no_financeiro(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, valor: float, *,
    total: bool, motivo: str, fazenda_id: int | None,
) -> dict:
    """Faz o valor que a fazenda assumiu virar DESPESA DA FAZENDA no
    Financeiro — a parte "comunicar com o financeiro completo" do pedido.

    São dois lastros possíveis, e eles são mutuamente exclusivos por desenho:

    a) O vale nasceu de um item de nota (o checkbox "é vale de funcionário?"
       — ver rules/vale_item.py). Esse item está HOJE fora de todo relatório
       gerencial, justamente por ser vale. Assumir o valor é devolvê-lo aos
       relatórios: se a fazenda assumiu o item inteiro, basta soltar o
       vínculo; se assumiu só um pedaço (vale parcelado com parte já
       descontada, ou um único mês desconsiderado), o item se DIVIDE — o
       resto vira um item normal, com a mesma conta gerencial e o mesmo
       centro de custo do original, porque é a mesma compra.

    b) O vale saiu do caixa por conta própria (dinheiro/pix/transferência) e
       tem um `ContaGerencial` só dele. Esse lançamento JÁ é uma despesa da
       fazenda no extrato — o que ele não é ainda é uma despesa COMUM: está
       marcado como "Vale de funcionário", tipo de baixa espelhada que o
       Financeiro se recusa a estornar/editar porque pertence ao RH. Quando
       nada mais será cobrado do funcionário, o rótulo passa a ser o de uma
       despesa qualquer. Numa assunção PARCIAL o rótulo não muda: o vale
       continua vivo e o lançamento continua sendo o espelho dele.

    c) Vale sem nenhum dos dois (forma "desconto_integral_folha" lançado à
       mão, sem item): não há nada no Financeiro para reclassificar — o
       dinheiro nunca saiu; o efeito é só o funcionário receber o salário
       cheio. Devolve `natureza: "sem_lastro"` para a tela poder dizer isso
       em vez de deixar o dono achando que faltou alguma coisa.
    """
    itens = itens_do_vale(session, vale.id)
    if itens:
        reclassificados = []
        for item in itens:
            if total or valor >= round(item.valor_total or 0, 2):
                limpar_vinculo_de_itens(session, vale_funcionario_id=vale.id)
                reclassificados.append({"item_id": item.id, "valor": round(item.valor_total or 0, 2), "dividido": False})
            else:
                gemeo = dividir_item_de_lancamento(
                    session, item, round((item.valor_total or 0) - valor, 2),
                    sufixo_descricao=f"parte assumida pela fazenda ({motivo})",
                )
                session.flush()
                reclassificados.append({"item_id": gemeo.id, "valor": valor, "dividido": True})
        return {
            "natureza": "item_de_nota",
            "numero_lancamento": itens[0].numero_lancamento,
            "itens": reclassificados,
        }

    if vale.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado,
                ContaGerencial.fazenda_id == fazenda_id,
            )
        ).first()
        if conta is not None and total:
            conta.tipo_documento = TIPO_DOCUMENTO_ASSUMIDO
            conta.descricao = f"Despesa assumida pela fazenda — vale de {pessoa.nome} ({vale.competencia_inicio})"
            session.add(conta)
            return {
                "natureza": "lancamento_proprio",
                "numero_lancamento": conta.numero_lancamento,
                "reclassificado": True,
            }
        return {
            "natureza": "lancamento_proprio",
            "numero_lancamento": vale.numero_lancamento_gerado,
            "reclassificado": False,
        }

    return {"natureza": "sem_lastro", "numero_lancamento": None}


def _lancar_devolucao_de_vale(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, valor: float,
    conta_corrente_id: int, fazenda_id: int | None,
) -> str:
    """Registra a ENTRADA de caixa de um abatimento pago em dinheiro/pix.

    Existe porque abater sem registrar a devolução desequilibra o caixa: a
    fazenda desembolsou o vale inteiro, deixa de recuperar parte dele na
    folha, e o dinheiro que voltou pela mão do funcionário não apareceria em
    lugar nenhum. Nasce já recebido (o dinheiro está na conta agora), mesmo
    padrão de `_sincronizar_conta_vale`. É OPCIONAL de propósito: abatimento
    que é perdão/concessão não tem devolução nenhuma a lançar, e forçar uma
    conta bancária ali inventaria uma entrada que não houve."""
    conta_corrente = session.exec(
        select(ContaCorrente).where(ContaCorrente.id == conta_corrente_id, ContaCorrente.fazenda_id == fazenda_id)
    ).first()
    if not conta_corrente:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada")

    hoje = date.today()
    numero = _proximo_numero_lancamento(session, hoje.year)
    session.add(ContaGerencial(
        numero_lancamento=numero,
        descricao=f"Devolução de vale — {pessoa.nome}",
        data_vencimento=hoje,
        data_competencia=hoje.replace(day=1),
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Recibo",
        centro_custo="Pecuária Leiteira",
        valor_total=valor,
        parcela_num=1, parcela_total=1,
        tipo="receita", origem="auto",
        data_pagamento=hoje,
        valor_pago=valor,
        conta_bancaria=rotulo_conta_corrente(conta_corrente),
        fazenda_id=fazenda_id,
    ))
    return numero


class ValeAcaoIn(BaseModel):
    acao: str  # reparcelar | abater | desconsiderar_mes | cancelar
    # reparcelar
    parcelas: int | None = None
    competencia_inicio: str | None = None  # "AAAA-MM"; None => a 1ª competência ainda pendente
    # abater
    valor: float | None = None
    # Conta bancária que RECEBEU a devolução, quando o funcionário devolveu em
    # dinheiro — opcional (ver `_lancar_devolucao_de_vale`).
    conta_corrente_id: int | None = None
    # desconsiderar_mes
    competencia: str | None = None  # "AAAA-MM"
    motivo: str | None = None


def _contexto_vale(session: Session, vale: ValeFuncionario, fazenda_id: int | None) -> dict:
    parcelas = _parcelas_do_vale(session, vale.id)
    pendentes = _parcelas_pendentes(session, vale, parcelas, fazenda_id)
    return {
        "vale_id": vale.id,
        "status": vale.status,
        "valor_total": round(vale.valor_total, 2),
        "valor_abatido": round(vale.valor_abatido, 2),
        "valor_assumido_fazenda": round(vale.valor_assumido_fazenda, 2),
        "saldo_pendente": round(sum(p.valor for p in pendentes), 2),
        "parcelas": [
            {
                **p.model_dump(),
                "pendente": p.id in {x.id for x in pendentes},
                "competencia_paga": bool(
                    _vale_competencia_paga(session, vale.pessoa_id, [p.competencia], fazenda_id)
                ),
            }
            for p in parcelas
        ],
        "acoes_disponiveis": [] if vale.status == "cancelado" else list(ACOES_VALE),
    }


@router.get("/vales/{vale_id}/acoes")
def opcoes_acoes_vale(
    vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
) -> dict:
    """O que a tela precisa para montar o painel de ações: saldo que resta,
    quais parcelas ainda dá para mexer e quais já estão travadas por folha
    paga (para explicar a trava em vez de só recusar depois)."""
    vale = _vale_da_fazenda(session, vale_id, fazenda_id)
    return _contexto_vale(session, vale, fazenda_id)


@router.post("/vales/{vale_id}/acoes")
def executar_acao_vale(
    vale_id: int, dados: ValeAcaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
) -> dict:
    """As quatro ações do dono sobre um vale já lançado (ver o cabeçalho do
    módulo). Todas reconciliam a folha das competências afetadas pelo mesmo
    caminho já usado por criar/editar/excluir vale
    (`_reconciliar_vale_competencias`) — nunca reescrevendo folha paga."""
    if dados.acao not in ACOES_VALE:
        raise HTTPException(
            status_code=400,
            detail="Ação inválida. Use: reparcelar, abater, desconsiderar_mes ou cancelar.",
        )
    vale = _vale_da_fazenda(session, vale_id, fazenda_id)
    pessoa = session.exec(
        select(Pessoa).where(Pessoa.id == vale.pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if vale.status == "cancelado":
        raise HTTPException(
            status_code=400,
            detail="Este vale já foi cancelado — o saldo pendente já virou despesa da fazenda.",
        )

    parcelas = _parcelas_do_vale(session, vale.id)
    pendentes = _parcelas_pendentes(session, vale, parcelas, fazenda_id)
    saldo = round(sum(p.valor for p in pendentes), 2)
    motivo = (dados.motivo or "").strip()

    if dados.acao == "reparcelar":
        resultado = _acao_reparcelar(session, vale, pendentes, saldo, dados, fazenda_id)
    elif dados.acao == "abater":
        resultado = _acao_abater(session, vale, pessoa, pendentes, saldo, dados, fazenda_id)
    elif dados.acao == "desconsiderar_mes":
        resultado = _acao_desconsiderar_mes(session, vale, pessoa, parcelas, dados, motivo, fazenda_id)
    else:
        resultado = _acao_cancelar(session, vale, pessoa, parcelas, pendentes, saldo, motivo, fazenda_id)

    session.commit()
    session.refresh(vale)
    return {**resultado, "vale": _contexto_vale(session, vale, fazenda_id)}


def _acao_reparcelar(
    session: Session, vale: ValeFuncionario, pendentes: list[ValeParcela], saldo: float,
    dados: ValeAcaoIn, fazenda_id: int | None,
) -> dict:
    """Redistribui o SALDO (o que ainda não foi descontado) em N parcelas a
    partir de uma competência. Só o saldo, nunca `valor_total`: o que já caiu
    numa folha paga foi descontado de verdade e não volta atrás."""
    if not dados.parcelas or dados.parcelas < 1:
        raise HTTPException(status_code=400, detail="Informe em quantas parcelas o saldo será dividido.")
    if not pendentes or saldo <= 0:
        raise HTTPException(
            status_code=400,
            detail="Este vale não tem saldo pendente para reparcelar — todas as parcelas já foram descontadas ou assumidas pela fazenda.",
        )

    competencia_inicio = dados.competencia_inicio or pendentes[0].competencia
    competencias_novas = _competencias_do_vale(competencia_inicio, dados.parcelas)
    _exigir_competencias_nao_pagas(session, vale.pessoa_id, competencias_novas, fazenda_id, "reparcelar")

    competencias_antigas = [p.competencia for p in pendentes]
    for p in pendentes:
        session.delete(p)
    session.flush()

    valores = _split_valores(saldo, dados.parcelas)
    for competencia, valor in zip(competencias_novas, valores):
        session.add(ValeParcela(
            vale_id=vale.id, pessoa_id=vale.pessoa_id, competencia=competencia,
            valor=valor, fazenda_id=vale.fazenda_id,
        ))
    session.flush()

    _reconciliar_vale_competencias(
        session, vale.pessoa_id, sorted(set(competencias_antigas) | set(competencias_novas)),
    )
    return {
        "acao": "reparcelar",
        "saldo_reparcelado": saldo,
        "competencias": competencias_novas,
        "resumo": (
            f"Saldo de R$ {_fmt_brl(saldo)} reparcelado em {dados.parcelas}x a partir de {competencia_inicio}."
        ),
    }


def _acao_abater(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, pendentes: list[ValeParcela], saldo: float,
    dados: ValeAcaoIn, fazenda_id: int | None,
) -> dict:
    """Abate um valor do vale — o funcionário devolveu parte em dinheiro, ou
    o dono perdoou um pedaço.

    O abatimento é rateado PROPORCIONALMENTE entre as parcelas pendentes (a
    última absorve o arredondamento), e não "das últimas para trás": o que
    diminuiu foi a dívida, então cada desconto futuro diminui na mesma
    medida, sem mudar o prazo combinado. Quem quiser mudar o prazo tem a ação
    de reparcelar, que é justamente a outra escolha do dono."""
    valor = round(dados.valor or 0, 2)
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor do abatimento deve ser positivo.")
    if not pendentes or saldo <= 0:
        raise HTTPException(
            status_code=400,
            detail="Este vale não tem saldo pendente para abater — todas as parcelas já foram descontadas ou assumidas pela fazenda.",
        )
    if valor > saldo:
        raise HTTPException(
            status_code=400,
            detail=(
                f"O abatimento de R$ {_fmt_brl(valor)} é maior que o saldo pendente do vale "
                f"(R$ {_fmt_brl(saldo)})."
            ),
        )

    # Distribui o saldo NOVO (em vez de distribuir o abatimento) — assim a
    # soma das parcelas fecha exatamente com o saldo restante, sem sobra de
    # arredondamento a acertar depois.
    saldo_novo = round(saldo - valor, 2)
    # Proporcional ao peso de cada parcela, não igualitário: parcela que já
    # era menor continua menor. A última absorve o arredondamento.
    novos: list[float] = []
    acumulado = 0.0
    for i, p in enumerate(pendentes):
        if i < len(pendentes) - 1:
            valor_novo = round(saldo_novo * p.valor / saldo, 2)
        else:
            valor_novo = round(saldo_novo - acumulado, 2)
        acumulado = round(acumulado + valor_novo, 2)
        novos.append(max(valor_novo, 0.0))

    competencias = [p.competencia for p in pendentes]
    for p, novo in zip(pendentes, novos):
        if novo <= 0:
            # Parcela zerada pelo abatimento vira ruído no holerite ("Vale
            # (parcela 2/3) — R$ 0,00"), então sai.
            session.delete(p)
        else:
            p.valor = novo
            session.add(p)
    vale.valor_abatido = round(vale.valor_abatido + valor, 2)
    session.add(vale)
    session.flush()

    numero_devolucao = None
    if dados.conta_corrente_id:
        numero_devolucao = _lancar_devolucao_de_vale(
            session, vale, pessoa, valor, dados.conta_corrente_id, fazenda_id,
        )

    _reconciliar_vale_competencias(session, vale.pessoa_id, sorted(set(competencias)))
    return {
        "acao": "abater",
        "valor_abatido": valor,
        "saldo_apos": saldo_novo,
        "numero_lancamento_devolucao": numero_devolucao,
        "resumo": (
            f"Abatimento de R$ {_fmt_brl(valor)} — o saldo do vale caiu para R$ {_fmt_brl(saldo_novo)}."
        ),
    }


def _acao_desconsiderar_mes(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcelas: list[ValeParcela],
    dados: ValeAcaoIn, motivo: str, fazenda_id: int | None,
) -> dict:
    """"Desconsiderar o vale neste mês": o funcionário não é descontado na
    competência informada e aquele valor passa a ser despesa da fazenda —
    decisão textual do dono. A parcela NÃO é apagada: fica marcada, para o
    holerite do mês poder explicar por que o desconto sumiu."""
    competencia = (dados.competencia or "").strip()
    if not competencia:
        raise HTTPException(status_code=400, detail="Informe a competência (AAAA-MM) a desconsiderar.")
    alvo = [p for p in parcelas if p.competencia == competencia and not p.assumida_pela_fazenda]
    if not alvo:
        raise HTTPException(
            status_code=400,
            detail=f"Este vale não tem parcela a descontar em {competencia}.",
        )
    _exigir_competencias_nao_pagas(session, vale.pessoa_id, [competencia], fazenda_id, "desconsiderar")

    valor = round(sum(p.valor for p in alvo), 2)
    rotulo_motivo = motivo or f"vale desconsiderado em {competencia}"
    for p in alvo:
        p.assumida_pela_fazenda = True
        p.motivo_assuncao = rotulo_motivo
        session.add(p)
    vale.valor_assumido_fazenda = round(vale.valor_assumido_fazenda + valor, 2)
    session.add(vale)
    session.flush()

    total = all(p.assumida_pela_fazenda for p in parcelas)
    financeiro = _assumir_no_financeiro(
        session, vale, pessoa, valor, total=total, motivo=rotulo_motivo, fazenda_id=fazenda_id,
    )
    _reconciliar_vale_competencias(session, vale.pessoa_id, [competencia])
    return {
        "acao": "desconsiderar_mes",
        "competencia": competencia,
        "valor_assumido": valor,
        "financeiro": financeiro,
        "resumo": (
            f"R$ {_fmt_brl(valor)} do vale de {competencia} não serão descontados de {pessoa.nome} — "
            "o valor passou a ser despesa da fazenda."
        ),
    }


def _acao_cancelar(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcelas: list[ValeParcela],
    pendentes: list[ValeParcela], saldo: float, motivo: str, fazenda_id: int | None,
) -> dict:
    """Cancela o vale inteiro como cobrança do funcionário — mesmo destino do
    "desconsiderar" quanto ao Financeiro, só que para todo o saldo.

    O que já caiu numa folha PAGA fica como está (foi descontado de verdade,
    e o holerite daquele mês é recibo), e a resposta diz quais competências
    são essas — sem isso o dono acharia que o cancelamento devolveu tudo."""
    # Comparação por id, não por objeto: `p in pendentes` usaria a igualdade
    # de campos do SQLModel e duas parcelas de mesmo valor/competência
    # passariam uma pela outra.
    ids_pendentes = {p.id for p in pendentes}
    ja_descontadas = [
        p for p in parcelas
        if not p.assumida_pela_fazenda and p.id not in ids_pendentes
    ]
    rotulo_motivo = motivo or "vale cancelado"
    for p in pendentes:
        p.assumida_pela_fazenda = True
        p.motivo_assuncao = rotulo_motivo
        session.add(p)
    vale.status = "cancelado"
    vale.valor_assumido_fazenda = round(vale.valor_assumido_fazenda + saldo, 2)
    session.add(vale)
    session.flush()

    total = not ja_descontadas
    financeiro = _assumir_no_financeiro(
        session, vale, pessoa, saldo, total=total, motivo=rotulo_motivo, fazenda_id=fazenda_id,
    )
    _reconciliar_vale_competencias(session, vale.pessoa_id, sorted({p.competencia for p in parcelas}))
    return {
        "acao": "cancelar",
        "valor_assumido": saldo,
        "competencias_ja_descontadas": sorted({p.competencia for p in ja_descontadas}),
        "financeiro": financeiro,
        "resumo": (
            f"Vale cancelado — R$ {_fmt_brl(saldo)} deixam de ser cobrados de {pessoa.nome} e viraram "
            "despesa da fazenda."
        ),
    }
