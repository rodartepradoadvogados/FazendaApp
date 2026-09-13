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

E, porque ERRAR DE AÇÃO é o que acontece de verdade (o dono quis
"desconsiderar o mês — a fazenda assume" e clicou em "lançar abatimento"),
três voltas atrás — as únicas ações deste módulo que DESFAZEM:

 5. estornar_abatimento    — devolve ao saldo a descontar o que (2) tirou:
                             inverso exato de `abater`, mesmo rateio
                             proporcional, para abater(X) + estornar(X)
                             devolver as parcelas ao centavo original.
 6. reverter_desconsideracao — o mês volta a ser descontado do funcionário.
 7. reverter_cancelamento  — o vale volta a `ativo` e o saldo que (4) varreu
                             para a fazenda volta a ser cobrança da pessoa.

POR QUE ESTAS TRÊS EXISTEM. Sem elas o dono ficava preso: editar o vale
inteiro (`PUT /vales`) é recusado quando qualquer competência do vale já está
em folha paga, e abatimento negativo é recusado por desenho (aumentaria a
dívida do funcionário sem registro nenhum de POR QUE aumentou). Não havia
terceira porta — o erro ficava no banco para sempre. O cancelamento era o
caso extremo: a ação mais destrutiva das seis, e a única que nem as voltas
atrás alcançavam, porque a trava do topo de `executar_acao_vale` recusa tudo
para vale cancelado (ela continua recusando tudo — a exceção é NOMEADA, uma
só).

O QUE ELAS NÃO DESFAZEM, de propósito: nada no Financeiro que possa ter sido
mexido por fora desde então. `estornar_abatimento` não apaga a entrada de
caixa da devolução (não há vínculo persistido entre o vale e aquele
lançamento — adivinhar qual é apagaria dinheiro certo de outra pessoa), e as
duas reversões de assunção RECUSAM quando ela mexeu num item de nota (ver
`_desfazer_assuncao_no_financeiro`). Todas dizem em palavras o que sobra para
a mão do dono, em vez de fingir que fizeram.

A NATUREZA DA ASSUNÇÃO É GRAVADA, NÃO DEDUZIDA (`ValeParcela.
natureza_assuncao`/`assuncao_detalhe`, migração b7d21f9c4a30). Antes disso, um
vale sem item vinculado hoje e sem lançamento próprio podia ser "sem lastro"
(nada a desfazer) ou "item de nota cujo vínculo foi solto" — indistinguíveis
depois, e chutar contaria a mesma despesa duas vezes —, então a reversão
recusava os dois. Agora o que a assunção fez fica escrito na parcela no ato
(`_registrar_assuncao`), e só continua sendo recusado o que é genuinamente
irreversível: item de nota (que pode ter sido editado desde então) e parcela
antiga, sem natureza gravada, que segue caindo na recusa por ambiguidade.

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

import json
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
    TIPO_DOCUMENTO_VALE,
    _competencias_do_vale,
    _exigir_competencias_nao_pagas,
    _exigir_teto_vale,
    _reconciliar_vale_competencias,
    _vale_competencia_paga,
    descricao_conta_vale,
)

router = APIRouter()

ACOES_VALE = (
    "reparcelar", "abater", "desconsiderar_mes", "cancelar",
    # As TRÊS voltas atrás — ver o cabeçalho do módulo.
    "estornar_abatimento", "reverter_desconsideracao", "reverter_cancelamento",
)

# ── Natureza da assunção, GRAVADA no ato (ValeParcela.natureza_assuncao) ────
# São os mesmos três valores que `_assumir_no_financeiro` devolve. Existem
# como constante porque três lugares os escrevem (as duas ações daqui e o
# pop-up de pagar a folha) e a reversão os lê para decidir o que tem inverso
# seguro — um literal solto divergindo faria a reversão ler natureza nenhuma
# e cair na recusa por ambiguidade sem motivo.
NATUREZA_ITEM_DE_NOTA = "item_de_nota"
NATUREZA_LANCAMENTO_PROPRIO = "lancamento_proprio"
NATUREZA_SEM_LASTRO = "sem_lastro"

# Qual AÇÃO assumiu a parcela (vai dentro de `assuncao_detalhe`). É o que
# permite a `reverter_cancelamento` devolver só o que o CANCELAMENTO varreu,
# deixando de pé o mês que o dono já havia desconsiderado antes por decisão
# própria — desfazer o cancelamento não pode voltar a cobrar aquele mês.
ACAO_DESCONSIDERAR = "desconsiderar_mes"
ACAO_CANCELAR = "cancelar"
ACAO_PAGAMENTO_FOLHA = "pagamento_folha"

# Rótulo do lançamento de vale no extrato depois que a fazenda assume a conta
# — deixa de ser "Vale de funcionário" (tipo de baixa espelhada, ver
# TIPOS_DOCUMENTO_BAIXA_ESPELHADA em financeiro.py) e passa a ser um
# documento comum, estornável/editável como qualquer despesa da fazenda.
TIPO_DOCUMENTO_ASSUMIDO = "Recibo"

# Forma de pagamento em que NADA sai do caixa quando o vale é lançado (o
# efeito é só a folha futura descontar): é a forma fixada no servidor para o
# vale que nasce de um item de nota (`rh_vale_item.py`) E a de um vale
# lançado à mão sem lastro nenhum. Ela é justamente a fronteira da AMBIGUIDADE
# que faz `reverter_desconsideracao` recusar — ver
# `_desfazer_assuncao_no_financeiro`.
FORMA_SEM_SAIDA_DE_CAIXA = "desconto_integral_folha"


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


def _reescalar_parcelas(pendentes: list[ValeParcela], saldo: float, saldo_novo: float) -> list[float]:
    """Redistribui `saldo_novo` entre as parcelas pendentes PROPORCIONALMENTE
    ao peso que cada uma tem hoje, com a ÚLTIMA absorvendo o arredondamento.

    Uma função só, usada pelo abatimento e pelo estorno dele, porque é a
    mesma conta nos dois sentidos — e é essa identidade que faz abater(X)
    seguido de estornar(X) devolver as parcelas ao valor original, ao
    centavo: o estorno reescala pelos pesos que o abatimento acabou de
    escrever, então a ida e a volta multiplicam pela mesma razão invertida.
    Duas cópias da conta divergiriam no primeiro arredondamento.

    Distribui o saldo NOVO (em vez de ratear a diferença) para a soma das
    parcelas fechar exatamente com o saldo, sem sobra a acertar depois."""
    novos: list[float] = []
    acumulado = 0.0
    for i, p in enumerate(pendentes):
        if i < len(pendentes) - 1:
            valor_novo = round(saldo_novo * p.valor / saldo, 2)
        else:
            valor_novo = round(saldo_novo - acumulado, 2)
        acumulado = round(acumulado + valor_novo, 2)
        novos.append(max(valor_novo, 0.0))
    return novos


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
            "natureza": NATUREZA_ITEM_DE_NOTA,
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
                "natureza": NATUREZA_LANCAMENTO_PROPRIO,
                "numero_lancamento": conta.numero_lancamento,
                "reclassificado": True,
            }
        return {
            "natureza": NATUREZA_LANCAMENTO_PROPRIO,
            "numero_lancamento": vale.numero_lancamento_gerado,
            "reclassificado": False,
        }

    return {"natureza": NATUREZA_SEM_LASTRO, "numero_lancamento": None}


def _registrar_assuncao(
    session: Session, parcelas: list[ValeParcela], financeiro: dict, acao: str,
) -> None:
    """Grava NA PARCELA o que a assunção acabou de fazer no Financeiro.

    Por que não basta deduzir depois: `_assumir_no_financeiro` tem três
    naturezas e duas delas ficam INDISTINGUÍVEIS pelo estado posterior do
    vale. Um vale que nasceu de item de nota e teve o vínculo solto na
    assunção (`limpar_vinculo_de_itens`) fica exatamente igual a um vale que
    nunca teve lastro nenhum — e reverter no escuro contaria a mesma despesa
    duas vezes. Escrever no ato é a única fonte confiável.

    `natureza_assuncao` guarda o enum; `assuncao_detalhe` guarda o resto em
    JSON (a ação que assumiu, o nº do lançamento, se ele foi reclassificado e
    quais itens foram divididos). Chamada pelas duas ações daqui e pelo
    pop-up de pagar a folha (rh_folha_pagar.py) — os três caminhos que
    assumem parcela."""
    detalhe = {"acao": acao, **{k: v for k, v in financeiro.items() if k != "natureza"}}
    for p in parcelas:
        p.natureza_assuncao = financeiro.get("natureza")
        p.assuncao_detalhe = json.dumps(detalhe, ensure_ascii=False)
        session.add(p)


def _detalhe_assuncao(parcela: ValeParcela) -> dict:
    """O `assuncao_detalhe` da parcela como dicionário — {} quando não há
    nada gravado ou quando o JSON está corrompido.

    JSON inválido vira {} de propósito, mesmo raciocínio de
    `_discriminacao_congelada` (rh_folha.py): um caractere estragado numa
    coluna de texto não pode derrubar a tela de ações; sem detalhe a parcela
    volta a ser tratada como de natureza desconhecida, que é a recusa
    conservadora."""
    if not parcela.assuncao_detalhe:
        return {}
    try:
        dados = json.loads(parcela.assuncao_detalhe)
    except (ValueError, TypeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _acao_que_assumiu(parcela: ValeParcela) -> str | None:
    """Qual ação marcou esta parcela como assumida — None para parcela
    assumida antes de a coluna existir."""
    acao = _detalhe_assuncao(parcela).get("acao")
    return acao if isinstance(acao, str) else None


def _limpar_assuncao(parcela: ValeParcela) -> None:
    """Apaga a marca da assunção INTEIRA quando a parcela volta a ser
    cobrança do funcionário. A natureza descreve um estado que deixou de
    existir; deixá-la para trás faria a próxima reversão decidir com base numa
    assunção antiga, já desfeita."""
    parcela.assumida_pela_fazenda = False
    parcela.motivo_assuncao = None
    parcela.natureza_assuncao = None
    parcela.assuncao_detalhe = None


def _onde_acertar_a_mao(parcelas: list[ValeParcela]) -> str:
    """"lançamento LC-2026-0007" a partir do que ficou gravado na assunção —
    para a recusa dizer QUAL documento o dono precisa acertar à mão."""
    numeros = sorted({
        n for n in (_detalhe_assuncao(p).get("numero_lancamento") for p in parcelas) if n
    })
    return f"lançamento {'/'.join(numeros)}" if numeros else "nota de origem"


def _motivo_reversao_impossivel(
    session: Session, vale: ValeFuncionario, fazenda_id: int | None,
    parcelas_alvo: list[ValeParcela] | None = None,
) -> str | None:
    """Por que a assunção deste vale NÃO pode ser desfeita no Financeiro — ou
    None, quando pode. Não escreve nada: serve tanto para a recusa (400) da
    ação quanto para a tela nem oferecer a ação.

    `_assumir_no_financeiro` tem três naturezas e só uma delas NÃO tem
    inverso seguro:

    a) item de nota: a assunção partiu o item em dois
       (`dividir_item_de_lancamento`) ou soltou o vínculo, e o gêmeo pode ter
       sido editado desde então — juntar os dois de volta às cegas
       corromperia a nota, que é o documento fiscal. Recusa, dizendo qual
       lançamento acertar à mão. CONTINUA recusando mesmo com a natureza
       gravada: a coluna resolve a ambiguidade, não torna tudo reversível.
    b) lançamento próprio (`numero_lancamento_gerado`): reversível — é só
       devolver o tipo de documento e a descrição de vale.
    c) sem lastro: nada foi tocado no Financeiro, nada a desfazer.

    COMO A NATUREZA É DESCOBERTA, em duas camadas.

    1) `ValeParcela.natureza_assuncao`, gravada NO ATO da assunção
       (`_registrar_assuncao`) — a fonte confiável, e a que responde por
       `parcelas_alvo` (as parcelas que a reversão vai mexer). Quando todas
       elas têm natureza gravada, a decisão é exata: (a) recusa, (b) e (c)
       passam.
    2) Parcela SEM natureza gravada (assumida antes da coluna existir, ver a
       migração b7d21f9c4a30): cai na dedução pelo estado atual do vale, que
       é o que sempre existiu — e onde o estado atual não distingue, recusa.

    A AMBIGUIDADE que a camada 2 não resolve, e por isso recusa: um vale sem
    item vinculado HOJE e sem lançamento próprio pode ser (c) — vale lançado à
    mão, sem saída de caixa — ou (a) já consumado, o vale que nasceu de item
    de nota e teve o vínculo SOLTO na assunção (`limpar_vinculo_de_itens`),
    que não deixa marca nenhuma. Os dois têm exatamente a mesma cara. Chutar
    (c) no caso (a) contaria a despesa duas vezes: o item voltaria a ser gasto
    da fazenda no gerencial E o funcionário voltaria a ser descontado pelo
    mesmo dinheiro. Como as duas origens compartilham a forma de pagamento sem
    saída de caixa, é ela que marca a fronteira da recusa. NULL continua
    caindo aqui de propósito: não se inventa natureza para o passado."""
    itens = itens_do_vale(session, vale.id)
    if itens:
        numeros = sorted({it.numero_lancamento for it in itens if it.numero_lancamento})
        ids = ", ".join(str(it.id) for it in itens)
        onde = f"lançamento {'/'.join(numeros)}" if numeros else "nota de origem"
        return (
            f"Este vale nasceu de um item de nota ({onde}, item {ids}), e assumir o valor mexeu nesse "
            "item — ele foi partido em dois (a parte da fazenda virou uma linha separada) ou teve o "
            "vínculo com o vale solto. Desfazer isso automaticamente corromperia a nota se a linha já "
            f"tiver sido editada desde então, então a volta é à mão: no Financeiro, acerte o {onde} "
            "(junte as duas linhas de volta numa só) e depois lance o vale novamente para o mês."
        )
    # Camada 1 — a natureza gravada no ato, quando TODAS as parcelas alvo a
    # têm. Basta uma sem natureza para a decisão inteira voltar à dedução
    # conservadora da camada 2: metade sabida não autoriza reverter o resto.
    if parcelas_alvo and all(p.natureza_assuncao for p in parcelas_alvo):
        de_nota = [p for p in parcelas_alvo if p.natureza_assuncao == NATUREZA_ITEM_DE_NOTA]
        if de_nota:
            onde = _onde_acertar_a_mao(de_nota)
            return (
                f"Este vale nasceu de um item de nota ({onde}) e a assunção mexeu nesse item — ele foi "
                "partido em dois (a parte da fazenda virou uma linha separada) ou teve o vínculo com o "
                "vale solto. Desfazer isso automaticamente corromperia a nota se a linha já tiver sido "
                f"editada desde então, então a volta é à mão: no Financeiro, acerte o {onde} (junte as "
                "duas linhas de volta numa só) e depois lance o vale novamente para o mês."
            )
        return None
    if vale.numero_lancamento_gerado:
        return None
    if vale.forma_pagamento == FORMA_SEM_SAIDA_DE_CAIXA:
        return (
            "Não dá para saber com segurança o que a assunção fez no Financeiro deste vale: ele não tem "
            "lançamento próprio, e um vale assim ou nunca teve lastro nenhum (nada a desfazer) ou nasceu "
            "de um item de nota cujo vínculo foi solto na assunção — os dois ficam idênticos depois. "
            "Reverter no escuro poderia contar a mesma despesa duas vezes (o item como gasto da fazenda "
            "e o desconto do funcionário). Confira a origem do vale no relatório de vales: se ele veio de "
            "uma nota, acerte o item lá e lance o vale de novo; se não veio, o desconto pode ser "
            "recriado lançando um vale novo para o mês."
        )
    return None


def _desfazer_assuncao_no_financeiro(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, fazenda_id: int | None,
    parcelas_alvo: list[ValeParcela] | None = None,
) -> dict:
    """Inverso de `_assumir_no_financeiro` para o único caso em que existe
    inverso seguro: o lançamento próprio reclassificado volta a ser o espelho
    do vale (tipo de documento e descrição vindos de `_sincronizar_conta_vale`,
    via as constantes de rh_folha.py — nunca texto reescrito aqui, senão o
    Financeiro deixaria de reconhecer a baixa espelhada).

    Recusa antes de escrever qualquer coisa nos casos que não têm volta
    segura (ver `_motivo_reversao_impossivel`), e é por `parcelas_alvo` que
    ele lê a natureza gravada no ato da assunção — sem elas a decisão volta a
    ser a dedução conservadora pelo estado atual do vale."""
    impedimento = _motivo_reversao_impossivel(session, vale, fazenda_id, parcelas_alvo)
    if impedimento:
        raise HTTPException(status_code=400, detail=impedimento)

    if not vale.numero_lancamento_gerado:
        # Natureza "sem lastro" confirmada: nada foi tocado no Financeiro na
        # ida, então não há nada a desfazer na volta. Antes da coluna
        # `natureza_assuncao` este caminho só era alcançado por um vale com
        # saída de caixa própria; agora ele também é o do vale sem lastro
        # cuja natureza foi GRAVADA — o caso que a ambiguidade recusava.
        return {"natureza": NATUREZA_SEM_LASTRO, "numero_lancamento": None, "reclassificado": False}

    conta = session.exec(
        select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado,
            ContaGerencial.fazenda_id == fazenda_id,
        )
    ).first()
    # Só volta atrás o que foi reclassificado pela assunção. Numa assunção
    # PARCIAL o rótulo nunca chegou a mudar (o vale seguia vivo), e mexer nele
    # aqui inventaria uma alteração que ninguém pediu.
    if conta is not None and conta.tipo_documento == TIPO_DOCUMENTO_ASSUMIDO:
        conta.tipo_documento = TIPO_DOCUMENTO_VALE
        conta.descricao = descricao_conta_vale(pessoa.nome, vale.competencia_inicio)
        session.add(conta)
        return {
            "natureza": NATUREZA_LANCAMENTO_PROPRIO,
            "numero_lancamento": conta.numero_lancamento,
            "reclassificado": True,
        }
    return {
        "natureza": NATUREZA_LANCAMENTO_PROPRIO,
        "numero_lancamento": vale.numero_lancamento_gerado,
        "reclassificado": False,
    }


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
    # reparcelar | abater | desconsiderar_mes | cancelar |
    # estornar_abatimento | reverter_desconsideracao
    acao: str
    # reparcelar
    parcelas: int | None = None
    competencia_inicio: str | None = None  # "AAAA-MM"; None => a 1ª competência ainda pendente
    # abater; e estornar_abatimento, em que `valor` é OPCIONAL — sem ele, o
    # estorno é do abatimento inteiro (o caso do dono, que quer desfazer o
    # clique errado por completo, não fazer conta de cabeça).
    valor: float | None = None
    # Conta bancária que RECEBEU a devolução, quando o funcionário devolveu em
    # dinheiro — opcional (ver `_lancar_devolucao_de_vale`).
    conta_corrente_id: int | None = None
    # desconsiderar_mes; e reverter_desconsideracao, em que é OBRIGATÓRIA (não
    # há padrão razoável: o vale pode ter vários meses assumidos, e escolher
    # um por conta própria mexeria no mês errado).
    competencia: str | None = None  # "AAAA-MM"
    motivo: str | None = None
    # reparcelar: confirma prosseguir mesmo deixando alguma competência com
    # mais de 40% do salário em desconto de vale. Reparcelar era uma das três
    # portas que não conferiam o teto — dava para jogar o saldo inteiro num
    # mês só, em silêncio (ver `_exigir_teto_vale`, em rh_folha.py).
    confirmar: bool = False


def _competencias_revertiveis(
    session: Session, vale: ValeFuncionario, parcelas: list[ValeParcela], fazenda_id: int | None,
) -> list[str]:
    """As competências assumidas pela fazenda que ainda dá para voltar a
    descontar: assumidas E com a folha em aberto. Folha paga não entra —
    reverter ali reescreveria um recibo já congelado.

    MÊS SEM FOLHA LANÇADA ENTRA, e isso é o que importa aqui: a lista é
    montada a partir das PARCELAS do vale, não das folhas do mês, e
    `_vale_competencia_paga` só encontra folha com `status == "pago"` — não
    haver folha nenhuma naquela competência devolve None e a competência
    fica na lista. Sem isso, desconsiderar um mês que ainda não tem folha
    lançada seria uma via de mão única: o painel "Descontos de vale" (a outra
    porta do desfazer) só existe onde há folha, e o mês sumiria do seletor
    justamente por não ter folha."""
    return sorted({
        p.competencia for p in parcelas
        if p.assumida_pela_fazenda
        and not _vale_competencia_paga(session, vale.pessoa_id, [p.competencia], fazenda_id)
    })


def _parcelas_do_cancelamento(parcelas: list[ValeParcela]) -> list[ValeParcela]:
    """As parcelas que o CANCELAMENTO assumiu — as que `reverter_cancelamento`
    devolve à cobrança do funcionário.

    Um mês desconsiderado ANTES do cancelamento (decisão própria do dono, com
    seu próprio motivo) não entra: desfazer o cancelamento não pode voltar a
    cobrar um mês que o dono já havia perdoado por outra razão. É para isso
    que a ação que assumiu fica gravada em `assuncao_detalhe`.

    Parcela assumida antes de a coluna existir (`acao` = None) entra: num vale
    CANCELADO ela é, na esmagadora maioria dos casos, o próprio saldo varrido
    pelo cancelamento, e deixá-la de fora tornaria a volta inútil justamente
    nos vales que já estão cancelados hoje — que são os que motivaram a ação.
    A escolha é visível e barata de corrigir: a resposta lista competência por
    competência o que voltou a ser descontado, e cada uma pode ser
    desconsiderada de novo num clique."""
    return [
        p for p in parcelas
        if p.assumida_pela_fazenda and _acao_que_assumiu(p) in (None, ACAO_CANCELAR)
    ]


def _impedimento_reverter_cancelamento(
    session: Session, vale: ValeFuncionario, parcelas: list[ValeParcela], fazenda_id: int | None,
) -> str | None:
    """Por que o cancelamento deste vale NÃO pode ser desfeito — ou None,
    quando pode. Não escreve nada: a tela usa para explicar, a ação usa para
    recusar (400) antes de qualquer escrita.

    São dois impedimentos, e nenhum deles é adivinhável depois:

    a) alguma competência varrida pelo cancelamento já virou FOLHA PAGA. O
       recibo daquele mês foi congelado sem o desconto (a parcela estava
       assumida pela fazenda quando ele foi emitido); voltar a cobrá-la agora
       cobraria do funcionário um desconto que o recibo não tem.
    b) o lado do Financeiro não tem inverso seguro — o mesmo
       `_motivo_reversao_impossivel` da reversão de desconsideração, olhando
       as parcelas que o cancelamento assumiu."""
    if vale.status != "cancelado":
        return "Este vale não está cancelado."
    alvo = _parcelas_do_cancelamento(parcelas)
    if not alvo:
        # O cancelamento não chegou a assumir parcela nenhuma (o vale já
        # estava todo descontado ou todo desconsiderado antes). Não há o que
        # devolver nem no vale nem no Financeiro — só o `status` volta.
        return None
    paga = _vale_competencia_paga(
        session, vale.pessoa_id, sorted({p.competencia for p in alvo}), fazenda_id,
    )
    if paga:
        return (
            f"A folha de {paga} desta pessoa foi paga depois do cancelamento, e o recibo dela foi "
            "emitido sem este desconto — reverter o cancelamento voltaria a cobrar um valor que aquele "
            f"holerite não tem. Estorne o pagamento da folha de {paga} antes de desfazer o cancelamento."
        )
    return _motivo_reversao_impossivel(session, vale, fazenda_id, alvo)


def _acoes_disponiveis(
    session: Session, vale: ValeFuncionario, parcelas: list[ValeParcela],
    pendentes: list[ValeParcela], fazenda_id: int | None,
) -> list[str]:
    """O que a TELA pode oferecer para este vale, agora.

    As ações de desfazer entram condicionadas porque oferecer uma delas
    quando ela vai dar 400 é pior que não oferecer: o dono clica achando que
    tem saída, leva o erro e continua sem saber o que fazer. As quatro
    originais continuam sempre disponíveis (cada uma explica sua própria
    recusa com o motivo concreto — saldo zerado, competência paga).

    VALE CANCELADO só oferece a volta do próprio cancelamento — e só quando
    ela é possível. Nenhuma das outras cinco o alcança: o saldo dele já virou
    despesa da fazenda, e mexer nisso sem antes desfazer o cancelamento
    deixaria o vale meio de cada lado."""
    if vale.status == "cancelado":
        if _impedimento_reverter_cancelamento(session, vale, parcelas, fazenda_id):
            return []
        return ["reverter_cancelamento"]
    acoes = ["reparcelar", "abater", "desconsiderar_mes", "cancelar"]
    # Estornar exige o que devolver E onde devolver: sem parcela pendente não
    # há parcela para o valor voltar (o estorno não inventa parcela nova).
    if round(vale.valor_abatido, 2) > 0 and pendentes:
        acoes.append("estornar_abatimento")
    # A reversão é oferecida quando EXISTE ao menos um mês assumido que ela
    # aceita: o impedimento do Financeiro passou a ser lido nas parcelas
    # daquela competência (a natureza é gravada por parcela, e um vale pode
    # ter meses assumidos de naturezas diferentes), em vez de uma resposta
    # única para o vale inteiro.
    if any(
        not _motivo_reversao_impossivel(
            session, vale, fazenda_id,
            [p for p in parcelas if p.competencia == comp and p.assumida_pela_fazenda],
        )
        for comp in _competencias_revertiveis(session, vale, parcelas, fazenda_id)
    ):
        acoes.append("reverter_desconsideracao")
    return acoes


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
        "acoes_disponiveis": _acoes_disponiveis(session, vale, parcelas, pendentes, fazenda_id),
        # As competências que `reverter_desconsideracao` aceita — a tela
        # monta o seletor com esta lista em vez de deduzir das parcelas, para
        # não discordar da recusa que o POST daria. Inclui mês SEM folha
        # lançada (ver `_competencias_revertiveis`): é a única porta do
        # desfazer nesse caso, já que sem folha não há painel de descontos.
        "competencias_revertiveis": _competencias_revertiveis(session, vale, parcelas, fazenda_id),
        # Por que a volta do cancelamento não está disponível, em palavras —
        # `acoes_disponiveis` diz que ela não pode, e num vale cancelado isso
        # deixaria a tela muda sobre a ação mais destrutiva das seis.
        "impedimento_reverter_cancelamento": (
            _impedimento_reverter_cancelamento(session, vale, parcelas, fazenda_id)
            if vale.status == "cancelado" else None
        ),
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
    """As ações do dono sobre um vale já lançado — as quatro decisões e as
    três voltas atrás (ver o cabeçalho do módulo). Todas reconciliam a folha
    das competências afetadas pelo mesmo caminho já usado por
    criar/editar/excluir vale (`_reconciliar_vale_competencias`) — nunca
    reescrevendo folha paga."""
    if dados.acao not in ACOES_VALE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Ação inválida. Use: reparcelar, abater, desconsiderar_mes, cancelar, "
                "estornar_abatimento, reverter_desconsideracao ou reverter_cancelamento."
            ),
        )
    vale = _vale_da_fazenda(session, vale_id, fazenda_id)
    pessoa = session.exec(
        select(Pessoa).where(Pessoa.id == vale.pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    # A trava do vale cancelado continua recusando TUDO — a exceção é NOMEADA,
    # uma só, e não um afrouxamento da condição: `reverter_cancelamento` é a
    # única ação cujo trabalho é justamente sair desse estado. Qualquer outra
    # (reparcelar, abater, desconsiderar, cancelar de novo, estornar,
    # reverter desconsideração) mexeria num saldo que já virou despesa da
    # fazenda e deixaria o vale meio de cada lado.
    if vale.status == "cancelado" and dados.acao != "reverter_cancelamento":
        raise HTTPException(
            status_code=400,
            detail=(
                "Este vale já foi cancelado — o saldo pendente já virou despesa da fazenda. Para voltar "
                "a cobrá-lo, use antes \"Reverter o cancelamento do vale\"."
            ),
        )
    if dados.acao == "reverter_cancelamento" and vale.status != "cancelado":
        raise HTTPException(
            status_code=400,
            detail="Este vale não está cancelado — não há cancelamento a reverter.",
        )

    parcelas = _parcelas_do_vale(session, vale.id)
    pendentes = _parcelas_pendentes(session, vale, parcelas, fazenda_id)
    saldo = round(sum(p.valor for p in pendentes), 2)
    motivo = (dados.motivo or "").strip()

    if dados.acao == "reparcelar":
        resultado = _acao_reparcelar(session, vale, pessoa, pendentes, saldo, dados, fazenda_id)
    elif dados.acao == "abater":
        resultado = _acao_abater(session, vale, pessoa, pendentes, saldo, dados, fazenda_id)
    elif dados.acao == "desconsiderar_mes":
        resultado = _acao_desconsiderar_mes(session, vale, pessoa, parcelas, dados, motivo, fazenda_id)
    elif dados.acao == "estornar_abatimento":
        resultado = _acao_estornar_abatimento(session, vale, pendentes, saldo, dados, fazenda_id)
    elif dados.acao == "reverter_desconsideracao":
        resultado = _acao_reverter_desconsideracao(session, vale, pessoa, parcelas, dados, fazenda_id)
    elif dados.acao == "reverter_cancelamento":
        resultado = _acao_reverter_cancelamento(session, vale, pessoa, parcelas, fazenda_id)
    else:
        resultado = _acao_cancelar(session, vale, pessoa, parcelas, pendentes, saldo, motivo, fazenda_id)

    session.commit()
    session.refresh(vale)
    return {**resultado, "vale": _contexto_vale(session, vale, fazenda_id)}


def _acao_reparcelar(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, pendentes: list[ValeParcela], saldo: float,
    dados: ValeAcaoIn, fazenda_id: int | None,
) -> dict:
    """Redistribui o SALDO (o que ainda não foi descontado) em N parcelas a
    partir de uma competência. Só o saldo, nunca `valor_total`: o que já caiu
    numa folha paga foi descontado de verdade e não volta atrás.

    `pessoa` entra só para o teto de 40% do salário (`_exigir_teto_vale`):
    reparcelar em 1x é exatamente o caminho de concentrar num mês um saldo que
    o funcionário não tem como absorver, e era uma das três portas que não
    avisavam nada."""
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

    valores = _split_valores(saldo, dados.parcelas)
    # Teto de 40% do salário — ANTES de apagar as pendentes, para a recusa
    # acontecer com o banco intacto. As parcelas que vão sumir saem do "já
    # lançado": elas serão substituídas pelo novo cronograma, e contá-las
    # somaria o saldo a si mesmo.
    _exigir_teto_vale(
        session, vale.pessoa_id, pessoa.salario_base, list(zip(competencias_novas, valores)),
        confirmar=dados.confirmar, verbo="reparcelar",
        parcela_ids_substituidas={p.id for p in pendentes},
    )

    competencias_antigas = [p.competencia for p in pendentes]
    for p in pendentes:
        session.delete(p)
    session.flush()

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

    # Proporcional ao peso de cada parcela, não igualitário: parcela que já
    # era menor continua menor (ver `_reescalar_parcelas`).
    saldo_novo = round(saldo - valor, 2)
    novos = _reescalar_parcelas(pendentes, saldo, saldo_novo)

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


def abater_saldo_na_rescisao(
    session: Session, pessoa: Pessoa, valor: float, fazenda_id: int | None,
) -> list[dict]:
    """
    Baixa `valor` do saldo de vale cobrável da pessoa porque a RESCISÃO já o
    descontou do que ela tem a receber — a metade "resolver" do defeito que
    deixou R$ 6.485,00 de vale de pé numa rescisão fechada (Jorbeson Nunes,
    pessoa 3, fazenda 1; ver `_saldo_vale_em_aberto`, em rh_folha.py).

    NÃO É UM TERCEIRO CAMINHO DE ABATIMENTO: cada vale é baixado por
    `_acao_abater`, o mesmo desta casa, com o mesmo rateio proporcional de
    `_reescalar_parcelas`. O que existe aqui é só a REPARTIÇÃO entre vales,
    que o abatimento (que sempre falou de um vale só) não tinha: os vales são
    quitados do mais antigo para o mais novo (pela primeira competência ainda
    pendente, e o id como desempate), até o valor acabar. Quitar do mais
    antigo é o que uma pessoa faria com a folha na mão, e deixa a sobra — se
    houver — no vale mais recente, que é o mais fácil de reconhecer depois.

    SEM LANÇAMENTO NOVO NO FINANCEIRO, e isto é deliberado: `conta_corrente_id`
    fica de fora da chamada de `_acao_abater` porque não houve devolução em
    dinheiro. O caixa já fecha sozinho — a saída do vale continua lançada como
    sempre esteve, e a rescisão paga um líquido MENOR exatamente nesse valor.
    Lançar uma "devolução" aqui contaria a recuperação duas vezes.
    """
    restante = round(valor, 2)
    if restante <= 0:
        return []

    parcelas_por_vale: dict[int, list[ValeParcela]] = {}
    for p in session.exec(
        select(ValeParcela).where(
            ValeParcela.pessoa_id == pessoa.id,
            ValeParcela.assumida_pela_fazenda == False,  # noqa: E712
        )
    ).all():
        parcelas_por_vale.setdefault(p.vale_id, []).append(p)

    if not parcelas_por_vale:
        return []

    def _pendentes(vale: ValeFuncionario) -> list[ValeParcela]:
        return _parcelas_pendentes(
            session, vale,
            sorted(parcelas_por_vale[vale.id], key=lambda x: (x.competencia, x.id or 0)),
            fazenda_id,
        )

    vales = sorted(
        (
            v for v in session.exec(
                select(ValeFuncionario).where(ValeFuncionario.id.in_(list(parcelas_por_vale)))
            ).all()
            if v.status != "cancelado"
        ),
        # "9999-99" para vale sem parcela pendente nenhuma: ele vai para o fim
        # da fila e o laço abaixo o pula (saldo zero) — nunca para o começo,
        # onde bloquearia a vez de um vale que de fato tem o que baixar.
        key=lambda v: (min((p.competencia for p in _pendentes(v)), default="9999-99"), v.id or 0),
    )

    baixados: list[dict] = []
    for vale in vales:
        if restante <= 0:
            break
        pendentes = _pendentes(vale)
        saldo = round(sum(p.valor for p in pendentes), 2)
        if saldo <= 0:
            continue
        valor_neste = min(restante, saldo)
        resultado = _acao_abater(
            session, vale, pessoa, pendentes, saldo,
            ValeAcaoIn(acao="abater", valor=valor_neste), fazenda_id,
        )
        restante = round(restante - valor_neste, 2)
        baixados.append({
            "vale_id": vale.id,
            "valor_abatido": valor_neste,
            "saldo_apos": resultado["saldo_apos"],
        })
    return baixados


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
    # O que a assunção fez fica GRAVADO na parcela, não deduzido depois — é
    # isso que permite à reversão distinguir "sem lastro" (nada a desfazer) de
    # "item de nota cujo vínculo foi solto", que ficam idênticos no estado
    # posterior do vale. Ver `_registrar_assuncao`.
    _registrar_assuncao(session, alvo, financeiro, ACAO_DESCONSIDERAR)
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
    # Marca nas parcelas que o CANCELAMENTO varreu (só nelas): é por esta
    # marca que `reverter_cancelamento` sabe o que devolver à cobrança sem
    # ressuscitar um mês que o dono já havia desconsiderado antes, por decisão
    # própria e por outro motivo.
    _registrar_assuncao(session, pendentes, financeiro, ACAO_CANCELAR)
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


def _acao_estornar_abatimento(
    session: Session, vale: ValeFuncionario, pendentes: list[ValeParcela], saldo: float,
    dados: ValeAcaoIn, fazenda_id: int | None,
) -> dict:
    """Desfaz um abatimento: o valor volta a ser dívida do funcionário.

    O caso real que fez esta ação existir: o dono queria "desconsiderar o vale
    do mês — a fazenda assume" e clicou em "lançar desconto/abatimento". As
    duas fazem o valor sumir da cobrança, mas por caminhos opostos (uma vira
    despesa da fazenda no Financeiro, a outra é perdão/devolução), e não havia
    volta: `PUT /vales` é recusado quando alguma competência do vale já está em
    folha paga, e abatimento negativo é recusado por desenho.

    É o INVERSO EXATO de `_acao_abater` — mesmo rateio proporcional, mesma
    última parcela absorvendo o arredondamento (`_reescalar_parcelas`), para
    abater(X) seguido de estornar(X) devolver as parcelas ao centavo original.
    A exceção é a parcela que o abatimento tiver ZERADO: ela foi apagada (era
    ruído no holerite) e o estorno não a ressuscita — o valor volta rateado
    entre as que sobraram."""
    if round(vale.valor_abatido, 2) <= 0:
        raise HTTPException(status_code=400, detail="Este vale não tem abatimento a estornar.")
    disponivel = round(vale.valor_abatido, 2)
    # Sem valor informado, estorna o abatimento inteiro: é o que desfaz o
    # clique errado por completo, sem o dono ter de refazer a conta.
    valor = round(dados.valor if dados.valor is not None else disponivel, 2)
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor do estorno deve ser positivo.")
    if valor > disponivel:
        raise HTTPException(
            status_code=400,
            detail=(
                f"O estorno de R$ {_fmt_brl(valor)} é maior que o abatimento já lançado neste vale — "
                f"há R$ {_fmt_brl(disponivel)} disponíveis para estorno."
            ),
        )
    if not pendentes or saldo <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este vale não tem parcela pendente onde devolver o valor estornado — todas já foram "
                "descontadas em folha paga ou assumidas pela fazenda. Reparcele o vale para o valor "
                "voltar a ter uma competência em aberto (se ainda houver saldo) ou lance um vale novo "
                "pelo valor a recobrar: o estorno não cria parcela por conta própria, porque escolher "
                "sozinho em que mês cobrar seria decidir no lugar do dono."
            ),
        )

    saldo_novo = round(saldo + valor, 2)
    novos = _reescalar_parcelas(pendentes, saldo, saldo_novo)
    competencias = [p.competencia for p in pendentes]
    for p, novo in zip(pendentes, novos):
        p.valor = novo
        session.add(p)
    vale.valor_abatido = round(disponivel - valor, 2)
    session.add(vale)
    session.flush()

    _reconciliar_vale_competencias(session, vale.pessoa_id, sorted(set(competencias)))
    return {
        "acao": "estornar_abatimento",
        "valor_estornado": valor,
        "saldo_apos": saldo_novo,
        "abatimento_restante": vale.valor_abatido,
        "resumo": (
            f"Estorno de R$ {_fmt_brl(valor)} — o saldo do vale voltou para R$ {_fmt_brl(saldo_novo)}. "
            "Se aquele abatimento foi lançado com devolução em conta bancária, o recebimento continua "
            "no Financeiro e precisa ser excluído à mão: o vale não guarda qual lançamento é o dele, e "
            "apagar um chutado tiraria dinheiro certo do extrato."
        ),
    }


def _acao_reverter_desconsideracao(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcelas: list[ValeParcela],
    dados: ValeAcaoIn, fazenda_id: int | None,
) -> dict:
    """Desfaz um "desconsiderar o vale em AAAA-MM": o funcionário volta a ser
    descontado naquele mês e o valor deixa de ser despesa da fazenda.

    A parcela não é recriada — ela nunca foi apagada, só marcada (ver
    `ValeParcela.assumida_pela_fazenda`), então reverter é tirar a marca. O
    lado do Financeiro é o difícil e está em `_desfazer_assuncao_no_financeiro`:
    ele recusa (400) tudo o que não tem inverso seguro, ANTES de qualquer
    escrita aqui, porque metade da volta seria pior que nenhuma."""
    competencia = (dados.competencia or "").strip()
    if not competencia:
        raise HTTPException(
            status_code=400, detail="Informe a competência (AAAA-MM) que volta a ser descontada.",
        )
    alvo = [p for p in parcelas if p.competencia == competencia and p.assumida_pela_fazenda]
    if not alvo:
        raise HTTPException(
            status_code=400,
            detail=f"Este vale não tem parcela assumida pela fazenda em {competencia} para reverter.",
        )
    # Mesma trava de `_acao_desconsiderar_mes`, pelo mesmo motivo e em sentido
    # contrário: voltar a descontar num mês já pago cobraria do funcionário um
    # desconto que o recibo daquele mês não tem.
    _exigir_competencias_nao_pagas(session, vale.pessoa_id, [competencia], fazenda_id, "voltar a descontar")

    financeiro = _desfazer_assuncao_no_financeiro(session, vale, pessoa, fazenda_id, alvo)

    valor = round(sum(p.valor for p in alvo), 2)
    for p in alvo:
        _limpar_assuncao(p)
        session.add(p)
    # `max(..., 0)`: o acumulador é histórico e não pode ficar negativo se o
    # mesmo mês tiver sido assumido por caminhos diferentes (o pop-up de pagar
    # a folha também assume parcelas — ver rh_folha_pagar.py).
    vale.valor_assumido_fazenda = round(max(vale.valor_assumido_fazenda - valor, 0.0), 2)
    session.add(vale)
    session.flush()

    _reconciliar_vale_competencias(session, vale.pessoa_id, [competencia])
    volta_do_lancamento = (
        f" O lançamento {financeiro['numero_lancamento']} voltou a ser vale no Financeiro."
        if financeiro.get("reclassificado") else ""
    )
    return {
        "acao": "reverter_desconsideracao",
        "competencia": competencia,
        "valor_revertido": valor,
        "financeiro": financeiro,
        "resumo": (
            f"{pessoa.nome} volta a ser descontado em {competencia}: R$ {_fmt_brl(valor)} deixaram de "
            f"ser despesa assumida pela fazenda e voltaram a ser cobrança do vale.{volta_do_lancamento}"
        ),
    }


def _acao_reverter_cancelamento(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, parcelas: list[ValeParcela],
    fazenda_id: int | None,
) -> dict:
    """Desfaz um "cancelar o vale inteiro": o vale volta a ser `ativo` e o
    saldo que o cancelamento varreu para a fazenda volta a ser cobrança do
    funcionário.

    POR QUE ESTA AÇÃO EXISTE. Cancelar era a mais destrutiva das seis e a
    única sem volta: `executar_acao_vale` recusa qualquer ação sobre vale
    cancelado logo no topo, então nem as voltas atrás do #720 o alcançavam. Um
    clique errado em "Cancelar o vale inteiro" tirava para sempre a cobrança
    de um adiantamento que o funcionário de fato recebeu.

    O QUE ELA DESFAZ, exatamente o que `_acao_cancelar` fez e nada além:
      1. a marca das parcelas que o CANCELAMENTO assumiu (as que ele mesmo
         varreu — ver `_parcelas_do_cancelamento`); um mês desconsiderado
         antes, por decisão própria do dono, continua desconsiderado;
      2. o valor correspondente em `valor_assumido_fazenda`;
      3. o `status`, que volta a "ativo";
      4. no Financeiro, a reclassificação do lançamento próprio do vale
         (`_desfazer_assuncao_no_financeiro`), que volta a ser a baixa
         espelhada do RH.

    O QUE ELA RECUSA, sem escrever nada (ver `_impedimento_reverter_
    cancelamento`): competência que virou folha PAGA depois do cancelamento —
    o recibo daquele mês foi emitido sem o desconto e não se reescreve —, e
    assunção que mexeu em item de nota, que não tem inverso seguro: o item
    pode ter sido editado desde então e juntar as linhas às cegas corromperia
    a nota fiscal. Nesses casos a resposta diz, em palavras, o que precisa ser
    acertado à mão — nunca adivinha."""
    impedimento = _impedimento_reverter_cancelamento(session, vale, parcelas, fazenda_id)
    if impedimento:
        raise HTTPException(status_code=400, detail=impedimento)

    alvo = _parcelas_do_cancelamento(parcelas)
    # Recusa ANTES de qualquer escrita, como na reversão da desconsideração:
    # metade da volta (parcela devolvida à cobrança, Financeiro ainda com a
    # despesa da fazenda) seria pior que nenhuma. Sem parcela a devolver, o
    # Financeiro não é tocado: o que estiver lá foi posto por outra assunção
    # (uma desconsideração anterior), que continua de pé e tem sua própria
    # volta.
    financeiro = (
        _desfazer_assuncao_no_financeiro(session, vale, pessoa, fazenda_id, alvo) if alvo
        else {"natureza": None, "numero_lancamento": None, "reclassificado": False}
    )

    valor = round(sum(p.valor for p in alvo), 2)
    competencias = sorted({p.competencia for p in alvo})
    for p in alvo:
        _limpar_assuncao(p)
        session.add(p)
    vale.status = "ativo"
    # `max(..., 0)`: o acumulador é histórico e não pode ficar negativo se o
    # mesmo vale tiver sido assumido por caminhos diferentes (o pop-up de
    # pagar a folha também assume parcelas — ver rh_folha_pagar.py).
    vale.valor_assumido_fazenda = round(max(vale.valor_assumido_fazenda - valor, 0.0), 2)
    session.add(vale)
    session.flush()

    _reconciliar_vale_competencias(session, vale.pessoa_id, competencias)
    # As que continuam assumidas: meses desconsiderados por decisão própria do
    # dono, antes do cancelamento. Vão na resposta para ele não achar que a
    # volta devolveu o vale inteiro — cada um se desfaz pela sua própria ação
    # (`reverter_desconsideracao`), agora que o vale voltou a ser "ativo".
    ainda_assumidas = sorted({
        p.competencia for p in parcelas
        if p.assumida_pela_fazenda and p.id not in {x.id for x in alvo}
    })
    volta_do_lancamento = (
        f" O lançamento {financeiro['numero_lancamento']} voltou a ser vale no Financeiro."
        if financeiro.get("reclassificado") else ""
    )
    sobra = (
        f" Continuam assumidos pela fazenda os meses desconsiderados antes do cancelamento: "
        f"{', '.join(ainda_assumidas)}."
        if ainda_assumidas else ""
    )
    return {
        "acao": "reverter_cancelamento",
        "valor_revertido": valor,
        "competencias": competencias,
        "competencias_ainda_assumidas": ainda_assumidas,
        "financeiro": financeiro,
        "resumo": (
            f"Cancelamento desfeito — R$ {_fmt_brl(valor)} voltam a ser cobrados de {pessoa.nome} nas "
            f"competências {', '.join(competencias) if competencias else '—'}."
            f"{volta_do_lancamento}{sobra}"
        ),
    }
