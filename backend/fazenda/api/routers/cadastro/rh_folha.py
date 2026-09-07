"""
Cadastro > Folha de Pagamento — lançamento e acompanhamento de folha mensal
por pessoa/competência (com guias consolidadas de FGTS/DCTF), Férias, 13º
salário, Rescisão contratual (CLT) e Vale de funcionário. A visão unificada
de todos os lançamentos de RH (folha, empreita, contrato, diária) vive em
rh_contratos.py, que também cobre Empreitada/Contrato/Diária/Vale avulso.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    ContaCorrente, ContaGerencial, DecimoTerceiro, DocumentoArquivado, FeriasFuncionario, FolhaPagamento,
    FolhaRubrica, GuiaFolhaEncargo, LancamentoAnexo, Pessoa, RescisaoFuncionario, Usuario, ValeAvulso,
    ValeFuncionario, ValeParcela,
)
from fazenda.api.routers.financeiro import TAMANHO_MAXIMO_ANEXO, _proximo_numero_lancamento, rotulo_conta_corrente
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.vale_item import limpar_vinculo_de_itens, origens_lancamento_por_vale
from fazenda.rules import holerite, rubrica_folha, vale_alimentacao
from fazenda.rules.folha_rh import (
    PARCELAS_DECIMO_TERCEIRO,
    calcular_decimo_terceiro,
    calcular_ferias,
    calcular_rescisao,
    retencoes_permitidas_decimo_terceiro,
    valor_parcela_decimo_terceiro,
)
from fazenda.rules.parametros import (
    dias_ferias_padrao,
    percentual_estimado_fgts_mensal,
    percentual_terco_constitucional_ferias,
)
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage
from fazenda.config import settings

FORMAS_PAGAMENTO_VALE = ["dinheiro", "pix", "transferencia", "desconto_integral_folha"]

router = APIRouter()

logger = logging.getLogger(__name__)


def _resolver_conta_corrente(
    session: Session, conta_corrente_id: int | None, fazenda_id: int | None,
) -> ContaCorrente | None:
    """
    Resolve (com checagem de fazenda) a conta bancária OPCIONAL de um
    lançamento de RH (Folha/Férias/13º/Rescisão/Diária) — usada para
    preencher `ContaGerencial.conta_bancaria`, o campo que os relatórios
    gerenciais realmente filtram/agrupam (ver rotulo_conta_corrente).

    Ao contrário de `_validar_conta_vale` (só o Vale de funcionário, onde a
    conta é obrigatória quando a forma de pagamento implica saída de caixa
    AGORA), aqui a conta NUNCA é obrigatória: estes fluxos não têm o conceito
    de forma_pagamento do Vale — quando não informada, o lançamento segue
    funcionando normalmente, só sem `conta_bancaria` preenchida. Quando
    informada mas inválida (id inexistente ou de outra fazenda), rejeita —
    nunca falha silenciosamente.
    """
    if not conta_corrente_id:
        return None
    conta = session.get(ContaCorrente, conta_corrente_id)
    if not conta or (conta.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada")
    return conta


# ---------------------------------------------------------------------------
# Folha de pagamento — lançamento e acompanhamento por pessoa/competência.
# ---------------------------------------------------------------------------
class FolhaPagamentoIn(BaseModel):
    pessoa_id: int
    competencia: str  # "AAAA-MM"
    valor_bruto: float
    descontos: float = 0.0
    percentual_inss: float = 0.0
    percentual_ir: float = 0.0
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    # FGTS/DCTF — opcionais (ver `_calcular_encargo_projetado`): em branco, não
    # afetam o lançamento nem entram na soma de `gerar-guias`.
    percentual_fgts: float | None = None
    valor_fgts: float | None = None
    percentual_dctf: float | None = None
    valor_dctf: float | None = None
    data_pagamento: date | None = None
    status: str = "pendente"
    observacao: str | None = None
    recorrente: bool = False
    dia_vencimento: int | None = None  # obrigatório quando recorrente=True (1-28)
    centro_custo: str = "Pecuária Leiteira"
    # Conta bancária da fazenda de onde sai o pagamento — OPCIONAL (ver
    # _resolver_conta_corrente): quando informada, preenche
    # ContaGerencial.conta_bancaria (o que os relatórios gerenciais filtram).
    conta_corrente_id: int | None = None


def _competencia_seguinte(competencia: str) -> str:
    ano, mes = (int(x) for x in competencia.split("-"))
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return f"{ano:04d}-{mes:02d}"


def _calcular_encargo_projetado(valor_bruto: float, percentual: Optional[float], valor: Optional[float]) -> Optional[float]:
    """
    Regra comum a FGTS e DCTF na folha: quando `valor` vem preenchido, ele tem
    PRIORIDADE e é usado tal como informado (mutuamente exclusivo com o
    percentual); senão, se `percentual` vier preenchido, o valor é calculado
    como percentual×valor_bruto; se nenhum dos dois vier preenchido, retorna
    None — o lançamento de folha segue funcionando normalmente, apenas sem
    contribuir para a soma de `gerar-guias` daquela competência.
    NÃO reproduz a fórmula legal real de FGTS (8% s/ remuneração) nem da guia
    de DCTF — o percentual/valor é decidido pelo usuário/contador; aqui é só
    a base para projeção interna de fluxo de caixa.
    """
    if valor is not None:
        return round(valor, 2)
    if percentual is not None:
        return round(valor_bruto * percentual / 100, 2)
    return None


def _liquido_folha(
    valor_bruto: float, descontos: float, valor_inss: float, valor_ir: float, valor_vale: float,
    valor_rubricas: float = 0.0,
) -> float:
    """
    Fórmula ÚNICA do líquido da folha: bruto + rubricas − descontos de folha −
    INSS − IR − vale. Existe como função porque a fórmula estava escrita à mão
    em quatro lugares deste módulo e uma delas (a geração por recorrência)
    tinha esquecido as retenções — toda competência gerada automaticamente
    nascia com o líquido inflado no banco e na conta a pagar. Com um só lugar,
    essa divergência não volta a acontecer silenciosamente.

    `valor_rubricas` é o efeito LÍQUIDO das rubricas avulsas do holerite
    (vencimentos acrescentados − descontos acrescentados; ver
    `FolhaPagamento.valor_rubricas` e `rules/rubrica_folha.py`) e pode ser
    negativo. Entra com valor padrão 0.0 porque folha recém-criada não tem
    rubrica nenhuma — mas todo recálculo de folha JÁ EXISTENTE precisa passá-lo,
    senão o self-heal apaga em silêncio a bonificação que o dono lançou.
    """
    return round(valor_bruto + valor_rubricas - descontos - valor_inss - valor_ir - valor_vale, 2)


def _data_vencimento_folha(competencia: str, dia_vencimento: Optional[int]) -> date:
    """Vencimento da folha: dia 5 (ou o dia escolhido) do mês SEGUINTE ao mês
    trabalhado — a competência é sempre o mês trabalhado; o pagamento cai no
    mês seguinte (ex.: competência 07/2026 é paga em 05/08/2026)."""
    ano_pgto, mes_pgto = (int(x) for x in _competencia_seguinte(competencia).split("-"))
    dia = min(max(dia_vencimento or 5, 1), 28)
    return date(ano_pgto, mes_pgto, dia)


def _proporcional_admissao(pessoa: Pessoa, competencia: str) -> Optional[dict]:
    """
    Quando a competência lançada é o mês de admissão da pessoa, calcula a
    fração de dias efetivamente trabalhados no mês (da data de admissão até o
    último dia do mês) — usada para SUGERIR o valor proporcional da folha do
    1º mês (sempre editável no lançamento, nunca imposto).
    """
    if not pessoa.data_admissao or pessoa.data_admissao.strftime("%Y-%m") != competencia:
        return None
    dias_mes = calendar.monthrange(pessoa.data_admissao.year, pessoa.data_admissao.month)[1]
    dias_trabalhados = dias_mes - pessoa.data_admissao.day + 1
    return {
        "dias_trabalhados": dias_trabalhados,
        "dias_mes": dias_mes,
        "fracao": round(dias_trabalhados / dias_mes, 6),
    }


@router.get("/folha-pagamento/proporcional-admissao")
def proporcional_admissao(
    pessoa_id: int, competencia: str, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict | None:
    """
    Usado pelo lançamento de folha do funcionário para sugerir o valor
    proporcional quando a competência informada é o mês de admissão da
    pessoa — retorna None fora desse caso (folha integral normal).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    return _proporcional_admissao(pessoa, competencia)


def _valor_vale(session: Session, pessoa_id: int, competencia: str) -> float:
    """
    Soma o valor das parcelas de vale COBRÁVEIS da pessoa nesta competência —
    esse é o "desconto de vale" da folha (coluna separada dos "descontos de
    folha" manuais). Uma parcela pertence a exatamente uma competência e a
    pessoa tem no máximo uma folha por competência, então somar todas é
    correto e idempotente (não acumula em recomputações sucessivas).

    Parcela `assumida_pela_fazenda` fica DE FORA: é o mês que o dono mandou
    desconsiderar (ou o saldo de um vale cancelado). Ela continua existindo
    para o histórico — o holerite precisa poder dizer por que o desconto
    sumiu —, mas o funcionário não é descontado por ela; o valor virou
    despesa da fazenda no Financeiro (ver rh_vale_acoes.py). Este é o ÚNICO
    ponto que decide "quanto de vale entra na folha", e por isso a regra mora
    aqui e não espalhada nos chamadores.
    """
    parcelas = session.exec(
        select(ValeParcela).where(
            ValeParcela.pessoa_id == pessoa_id,
            ValeParcela.competencia == competencia,
            ValeParcela.assumida_pela_fazenda == False,  # noqa: E712
        )
    ).all()
    return round(sum(p.valor for p in parcelas), 2)


def _marcar_vale_aplicado(session: Session, pessoa_id: int, competencia: str) -> None:
    """Marca como aplicadas as parcelas de vale absorvidas por uma folha desta
    competência — só bookkeeping; o valor_vale vem sempre da SOMA, não daqui."""
    pendentes = session.exec(
        select(ValeParcela).where(
            ValeParcela.pessoa_id == pessoa_id,
            ValeParcela.competencia == competencia,
            ValeParcela.aplicada == False,  # noqa: E712
        )
    ).all()
    for p in pendentes:
        p.aplicada = True
        session.add(p)


def _recalcular_folha(session: Session, folha: FolhaPagamento) -> list[FolhaRubrica]:
    """
    Reprocessa a folha depois de qualquer mudança nas rubricas: as duas somas
    em cache, as retenções sobre a base corrigida, o líquido e a conta a pagar.

    Ordem importa e é a do holerite de papel: primeiro a base (bruto + as
    rubricas SALARIAIS), depois as retenções sobre ela, e só então o líquido —
    do qual saem os descontos, que nunca entraram em base nenhuma.

    MOROU EM `rh_folha_rubricas.py` ATÉ AQUI, e mudou de casa quando o
    vale-alimentação passou a gerar rubrica a partir do cadastro: a geração
    acontece neste módulo (na criação da folha, na recorrência e no self-heal
    da listagem) e `rh_folha_rubricas` já importa deste arquivo — importar de
    volta seria um ciclo. Continua sendo UMA função só: `rh_folha_rubricas` e
    `rh_folha_pagar` a importam daqui, para não existirem duas fórmulas de
    líquido no sistema (o defeito que `_liquido_folha` fechou).
    """
    rubricas = session.exec(select(FolhaRubrica).where(FolhaRubrica.folha_id == folha.id)).all()
    folha.valor_rubricas = rubrica_folha.valor_liquido_das_rubricas(rubricas)
    folha.valor_rubricas_tributaveis = rubrica_folha.base_tributavel_das_rubricas(rubricas)

    for campo, valor in rubrica_folha.retencoes_recalculadas(
        folha.valor_bruto, folha.percentual_inss, folha.percentual_ir, folha.percentual_fgts, rubricas,
    ).items():
        setattr(folha, campo, valor)

    # O vale vem sempre da SOMA das parcelas da competência: recalcular o
    # líquido a partir de um `valor_vale` desatualizado no registro é como a
    # folha já nascia inflada antes do self-heal da listagem.
    folha.valor_vale = _valor_vale(session, folha.pessoa_id, folha.competencia)
    folha.valor_liquido = _liquido_folha(
        folha.valor_bruto, folha.descontos, folha.valor_inss, folha.valor_ir, folha.valor_vale,
        folha.valor_rubricas,
    )
    session.add(folha)

    # A conta a pagar é o número que o dono efetivamente paga: sem isto, o
    # holerite mostraria a bonificação e o banco pagaria o valor antigo.
    # Conta já BAIXADA não é tocada (não se reescreve pagamento feito) — e ela
    # só existiria aqui numa folha paga, que os chamadores já barram.
    if folha.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado,
                ContaGerencial.fazenda_id == folha.fazenda_id,
            )
        ).first()
        if conta and conta.valor_pago is None:
            conta.valor_total = folha.valor_liquido
            session.add(conta)
    return list(rubricas)


# ---------------------------------------------------------------------------
# Vale-alimentação — a verba que a folha gera a partir do CADASTRO da pessoa
#
# O dono recusou a ideia de uma rubrica lançada mês a mês e pediu o oposto:
# "não precisa de uma rubrica para vale alimentação, só precisa de ter como
# cadastrar se vai ter ou não e o valor-base, se diário ou mensal, se pago
# antecipado ou vencido, para fins de competência, e o valor. O resto é
# padrão." As regras (quanto, de que competência, com que contagem de dias)
# são puras e moram em `rules/vale_alimentacao.py`; aqui fica só a gravação.
#
# POR QUE A LINHA É UMA `FolhaRubrica` COMUM, e não um campo novo na folha:
# porque assim ela já entra no líquido (`valor_rubricas`), no discriminado, no
# holerite impresso, no pop-up de pagamento e no congelamento do recibo, sem
# nenhum caminho paralelo que cada uma dessas telas teria de aprender. O que a
# distingue é a ORIGEM: quem manda no valor é o cadastro, e é por isso que os
# endpoints de rubrica recusam criar/editar/excluir esta linha na mão.
# ---------------------------------------------------------------------------
def _pessoa_da_folha(session: Session, folha: FolhaPagamento) -> Pessoa | None:
    """
    A pessoa da folha, com o filtro de fazenda DENTRO da consulta e
    INCONDICIONAL (`== folha.fazenda_id`, que em None vira `IS NULL`).

    Nunca `session.get(Pessoa, ...)` cru aqui: o que sai desta função vira
    dinheiro gravado no holerite de alguém, e o padrão tolerante
    ("se veio fazenda, filtra") é exatamente o que deixaria a configuração de
    vale-alimentação de um inquilino gerar verba na folha de outro.
    """
    return session.exec(
        select(Pessoa).where(Pessoa.id == folha.pessoa_id, Pessoa.fazenda_id == folha.fazenda_id)
    ).first()


def _sincronizar_vale_alimentacao(
    session: Session, folha: FolhaPagamento, pessoa: Pessoa | None = None,
    *, recem_criada: bool = False,
) -> bool:
    """
    Põe a linha de vale-alimentação desta folha igual ao que o CADASTRO diz —
    criando, corrigindo ou removendo. Devolve True quando mexeu em algo (o
    chamador então roda `_recalcular_folha`), False quando já estava certo.

    FOLHA PAGA NÃO É TOCADA, e a recusa é a primeira coisa que a função faz:
    a discriminação dela foi congelada no pagamento porque o holerite é PROVA.
    Ligar o vale-alimentação hoje acrescenta a verba nas competências ainda
    abertas e não reescreve um centavo de nenhum mês já pago; DESLIGAR também
    não apaga a verba de um recibo já emitido.

    `recem_criada` é a ÚNICA exceção, e ela não abre a porta que a regra
    fecha: o lançamento que já NASCE pago (`POST /folha-pagamento` com
    `status="pago"`) é gravado e congelado dentro da mesma requisição, e entre
    o INSERT e o congelamento ele ainda não é recibo de nada — não existe
    dinheiro anterior a preservar ali. Sem esta exceção, quem lança a folha já
    paga ficaria com um holerite sem a verba que o funcionário recebeu.
    Nenhum outro chamador passa a marca: a folha paga que veio do banco
    (listagem, recorrência) continua intocável, e a que já tem fotografia é
    recusada mesmo com a marca ligada.

    NÃO COMMITA: quem chama decide a transação, porque a linha, o líquido e a
    conta a pagar têm de cair juntos se algo falhar no meio (mesmo motivo do
    `flush` em `criar_rubrica_folha`).
    """
    if folha.discriminacao_congelada_em is not None:
        return False
    if folha.status == "pago" and not recem_criada:
        return False
    if pessoa is not None and pessoa.fazenda_id != folha.fazenda_id:
        # Objeto vindo de um mapa de outra consulta: só é aceito se for MESMO
        # da fazenda da folha. Divergiu, refaz a busca filtrada.
        pessoa = None
    if pessoa is None:
        pessoa = _pessoa_da_folha(session, folha)
    if pessoa is None:
        return False

    calculo = vale_alimentacao.calcular(pessoa, folha.competencia)
    existente = session.exec(
        select(FolhaRubrica).where(
            FolhaRubrica.folha_id == folha.id,
            FolhaRubrica.codigo == vale_alimentacao.CODIGO,
        )
    ).first()

    if calculo is None:
        # Benefício desligado (ou sem valor-base): a linha sai do holerite das
        # competências abertas. Só as pagas guardam o que foi pago.
        if existente is None:
            return False
        session.delete(existente)
        session.flush()
        return True

    verbete = rubrica_folha.CATALOGO_VENCIMENTOS[vale_alimentacao.CODIGO]
    descricao = vale_alimentacao.descricao(calculo)
    valor = calculo["valor"]

    if existente is not None:
        # `competencia`/`pessoa_id` são redundantes com a folha por desenho
        # (ver models/folha_rubrica.py) — e o PUT de folha permite trocar as
        # duas coisas num lançamento ainda aberto. Realinhar aqui é o que
        # impede a linha de continuar afirmando um mês ou um funcionário que a
        # folha já não tem.
        alinhada = (
            existente.competencia == folha.competencia and existente.pessoa_id == folha.pessoa_id
        )
        if (
            alinhada
            and abs(existente.valor - valor) <= 0.001
            and (existente.descricao or "") == descricao
        ):
            return False
        # O valor-base mudou no cadastro (ou o mês mudou de tamanho): a linha
        # da competência ABERTA acompanha. É o mesmo princípio do self-heal do
        # vale na listagem — o holerite não pago mostra o que será pago.
        existente.competencia = folha.competencia
        existente.pessoa_id = folha.pessoa_id
        existente.valor = valor
        existente.descricao = descricao
        session.add(existente)
        session.flush()
        return True

    session.add(FolhaRubrica(
        fazenda_id=folha.fazenda_id,
        folha_id=folha.id,
        pessoa_id=folha.pessoa_id,
        competencia=folha.competencia,
        especie=rubrica_folha.ESPECIE_VENCIMENTO,
        codigo=vale_alimentacao.CODIGO,
        descricao=descricao,
        valor=valor,
        # Enquadramento COPIADO do catálogo, igual à rubrica lançada à mão: o
        # recibo já emitido não muda de conteúdo se a lei mudar depois.
        natureza=verbete["natureza"],
        incide_inss=bool(verbete["incide_inss"]),
        incide_irrf=bool(verbete["incide_irrf"]),
        incide_fgts=bool(verbete["incide_fgts"]),
        incorpora_base=bool(verbete["incorpora_base"]),
        # `usuario_id` fica nulo: ninguém lançou esta linha — ela veio do
        # cadastro. Carimbar quem abriu a tela seria atribuir a uma pessoa um
        # lançamento que ela não fez.
    ))
    session.flush()
    return True


def _aplicar_vale_alimentacao(
    session: Session, folha: FolhaPagamento, pessoa: Pessoa | None = None,
    *, recem_criada: bool = False,
) -> bool:
    """Sincroniza a linha e, se ela mudou, refaz bases/retenções/líquido e a
    conta a pagar. É o par que todo chamador precisa — separado só para o
    self-heal da listagem poder saber se houve mudança a commitar."""
    if not _sincronizar_vale_alimentacao(session, folha, pessoa, recem_criada=recem_criada):
        return False
    _recalcular_folha(session, folha)
    return True


def _rescisao_fechada_encerra_competencia(
    session: Session, pessoa_id: int, competencia: str, fazenda_id: int | None
) -> bool:
    """
    True quando a pessoa já tem uma rescisão FECHADA (a simulação sozinha não
    conta — ver fluxo simulacao → fechada) que ENCERRA `competencia`: o
    desligamento caiu DENTRO do mês da competência ou antes dele. Usada para
    nunca gerar/aceitar folha de um mês que a rescisão já pagou ou que a
    pessoa não trabalhou.

    PAGAMENTO EM DUPLICIDADE CORRIGIDO AQUI (caso real de set/2026 — Jorbeson
    e Valéria, desligamento 05/08/2026, rescisão fechada e quitada, e mesmo
    assim uma folha PENDENTE de competência 2026-08 com salário CHEIO):
    a comparação era `data_desligamento < inicio_competencia` (o dia 1º do
    mês), então o PRÓPRIO mês do desligamento passava batido — 05/08 não é
    anterior a 01/08. Só setembro em diante era bloqueado.

    E o mês do desligamento não pode ser gerado, porque a rescisão já paga
    esses dias: `calcular_rescisao` (rules/folha_rh.py) inclui no total a
    verba `saldo_salario` = salario_base / 30 × dias trabalhados no mês do
    desligamento. Folha cheia do mesmo mês + saldo de salário da rescisão =
    o mês pago duas vezes. A decisão explícita é: o mês do desligamento NÃO
    gera folha, o saldo daqueles dias está na rescisão.

    Agora a comparação é contra o ÚLTIMO dia da competência
    (`data_desligamento <= fim_competencia`), que é o mesmo que dizer
    "desligou antes do início da competência SEGUINTE".

    READMISSÃO: uma rescisão fechada não pode calar a pessoa para sempre. Se
    o cadastro da pessoa passou a ter `data_admissao` POSTERIOR ao último
    desligamento (novo vínculo), a competência volta a ser válida a partir do
    mês dessa readmissão — os meses entre a saída e a volta continuam
    bloqueados. Sem `data_admissao` (ou com ela anterior ao desligamento) a
    resposta é a conservadora: bloqueia.

    `fazenda_id` é OBRIGATÓRIO e os filtros são INCONDICIONAIS (`==
    fazenda_id`, que em None vira `IS NULL`): esta função decide o que
    `_remover_folha_pos_rescisao` APAGA, e a versão antiga consultava
    `RescisaoFuncionario` sem filtro nenhum de fazenda — a rescisão de uma
    fazenda respondia pela folha de outra.
    """
    ano, mes = (int(x) for x in competencia.split("-"))
    fim_competencia = date(ano, mes, calendar.monthrange(ano, mes)[1])
    rescisoes = session.exec(
        select(RescisaoFuncionario).where(
            RescisaoFuncionario.pessoa_id == pessoa_id,
            RescisaoFuncionario.fazenda_id == fazenda_id,
            RescisaoFuncionario.status == "fechada",
            RescisaoFuncionario.data_desligamento <= fim_competencia,
        )
    ).all()
    if not rescisoes:
        return False

    # Vale o desligamento MAIS RECENTE: com mais de uma rescisão fechada na
    # ficha (readmitido e desligado de novo), é o último que diz se a pessoa
    # estava fora nesta competência.
    ultimo_desligamento = max(r.data_desligamento for r in rescisoes)
    # `select ... where fazenda_id == fazenda_id` em vez de `session.get`: a
    # data de admissão passa a decidir se uma folha é gerada, então a leitura
    # tem que ser tão isolada por fazenda quanto a da rescisão acima.
    pessoa = session.exec(
        select(Pessoa).where(Pessoa.id == pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    readmissao = pessoa.data_admissao if pessoa else None
    if readmissao and ultimo_desligamento < readmissao <= fim_competencia:
        return False
    return True


def _remover_folha_pos_rescisao(session: Session, fazenda_id: int | None) -> None:
    """
    Remove (com a conta a pagar vinculada, se ainda não paga) qualquer folha
    PENDENTE de uma competência que a rescisão fechada da pessoa já encerra —
    o mês do desligamento inclusive, cujo saldo de salário a rescisão paga
    (ver `_rescisao_fechada_encerra_competencia`). Cobre o caso de a folha já
    ter sido gerada (recorrência ou lançamento manual) ANTES de a rescisão ser
    lançada/fechada no sistema. Nunca mexe em folha já paga: aí o dinheiro
    saiu e apagar seria reescrever histórico financeiro.

    DUAS CORREÇÕES DE SEGURANÇA aqui, porque esta é a única rotina do módulo
    que DESTRÓI dado:

    1. O filtro de fazenda era o padrão tolerante `if fazenda_id is not None`
       — com um token legado (sem a claim `fid`, ex.: sessão "manter
       conectado" emitida antes do multi-fazenda) `fazenda_id` chegava None,
       a cláusula sumia e o loop varria e apagava a folha pendente de TODAS
       as fazendas. Agora o `where` é incondicional: com um id filtra por ele,
       com None vira `IS NULL` e alcança só o dado legado sem fazenda — nunca
       o das outras.
    2. Deixou de ser chamada de dentro do `GET /folha-pagamento`. Um GET não
       pode apagar nada; a rotina agora roda no POST que cria o fato novo
       (`/rescisoes/{id}/fechar`), que é onde a informação "esta pessoa saiu"
       nasce. A geração recorrente já parava sozinha na rescisão fechada
       (ver `_gerar_folha_recorrente`), então nada volta a sujar a base.
    """
    query = select(FolhaPagamento).where(
        FolhaPagamento.status != "pago",
        FolhaPagamento.fazenda_id == fazenda_id,
    )
    for registro in session.exec(query).all():
        if not _rescisao_fechada_encerra_competencia(session, registro.pessoa_id, registro.competencia, fazenda_id):
            continue
        if registro.numero_lancamento_gerado:
            conta = session.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
            ).first()
            if conta and conta.valor_pago is None:
                session.delete(conta)
        session.delete(registro)
    session.commit()


def _remover_folha_duplicada(session: Session, fazenda_id: int | None) -> None:
    """
    Self-heal: normaliza lançamentos duplicados de folha (mesma pessoa +
    competência) que a falta de idempotência em `criar_folha_pagamento`
    deixava acumular — mantém o pago (se houver) ou o mais recente, e remove
    o(s) outro(s) junto com a conta a pagar vinculada (se ainda não paga).
    Nunca exclui um lançamento já pago.

    Filtro de fazenda INCONDICIONAL pelo mesmo motivo de
    `_remover_folha_pos_rescisao`: é uma rotina que apaga, e o padrão
    tolerante `if fazenda_id is not None` deixava um token legado varrer as
    outras fazendas. (Esta continua rodando na listagem, ao contrário da
    outra: ela só desempata duplicatas DENTRO da própria pessoa/competência,
    o gatilho é a leitura da tela e não existe outro momento em que a
    duplicata legada apareça.)"""
    query = select(FolhaPagamento).where(FolhaPagamento.fazenda_id == fazenda_id)
    por_chave: dict[tuple[int, str], list[FolhaPagamento]] = {}
    for registro in session.exec(query).all():
        por_chave.setdefault((registro.pessoa_id, registro.competencia), []).append(registro)

    houve_remocao = False
    for registros in por_chave.values():
        if len(registros) <= 1:
            continue
        pagos = [r for r in registros if r.status == "pago"]
        manter_id = pagos[0].id if pagos else max(registros, key=lambda r: r.id).id
        for registro in registros:
            if registro.id == manter_id or registro.status == "pago":
                continue
            if registro.numero_lancamento_gerado:
                conta = session.exec(
                    select(ContaGerencial).where(
                        ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado
                    )
                ).first()
                if conta and conta.valor_pago is None:
                    session.delete(conta)
            session.delete(registro)
            houve_remocao = True
    if houve_remocao:
        session.commit()


def _rotulo_conta_do_modelo(session: Session, modelo: FolhaPagamento) -> str | None:
    """
    Rótulo da conta bancária do lançamento-modelo, para preencher
    `ContaGerencial.conta_bancaria` nas competências geradas pela recorrência.
    Ao contrário de `_resolver_conta_corrente` (usado nos endpoints), NUNCA
    levanta HTTPException: isto roda dentro de uma rotina "lazy pull" chamada
    pela listagem, e uma conta apagada depois do lançamento não pode derrubar a
    tela de folha inteira — nesse caso a conta a pagar só nasce sem o rótulo.
    """
    if not modelo.conta_corrente_id:
        return None
    conta = session.get(ContaCorrente, modelo.conta_corrente_id)
    if not conta or (conta.fazenda_id != modelo.fazenda_id):
        return None
    return rotulo_conta_corrente(conta)


def _gerar_folha_recorrente(session: Session, fazenda_id: int | None = None) -> None:
    """
    Para cada lançamento de folha marcado como recorrente (o "modelo"), gera
    automaticamente os lançamentos das competências seguintes até o mês atual
    — tanto o registro de acompanhamento (FolhaPagamento) quanto a conta a
    pagar correspondente (ContaGerencial) — sem exigir relançamento manual
    todo mês. Mesmo padrão "lazy pull" da baixa automática de Alimentação.
    Para de gerar na primeira competência encerrada por rescisão fechada —
    o MÊS DO DESLIGAMENTO inclusive, porque o saldo de salário daqueles dias
    já está dentro da rescisão (ver
    `_rescisao_fechada_encerra_competencia`).

    O `break` encerra ESTE modelo de recorrência de vez, e é de propósito:
    uma readmissão é contrato novo (salário novo, vencimento novo), e volta a
    gerar folha pelo lançamento recorrente novo que o usuário cria — não
    ressuscitando o modelo do vínculo antigo meses depois.
    """
    competencia_atual = date.today().strftime("%Y-%m")
    # Filtro de fazenda incondicional (`== fazenda_id`, que em None vira
    # `IS NULL`): esta rotina CRIA folha e conta a pagar, e o padrão tolerante
    # `if fazenda_id is not None` fazia um token legado gerar em cima do
    # dado das outras fazendas.
    query = select(FolhaPagamento).where(
        FolhaPagamento.recorrente == True,  # noqa: E712
        FolhaPagamento.fazenda_id == fazenda_id,
    )
    modelos = session.exec(query).all()
    for modelo in modelos:
        pessoa = session.get(Pessoa, modelo.pessoa_id)
        if not pessoa:
            continue
        competencia = _competencia_seguinte(modelo.competencia)
        while competencia <= competencia_atual:
            if _rescisao_fechada_encerra_competencia(session, modelo.pessoa_id, competencia, fazenda_id):
                break
            existe = session.exec(
                select(FolhaPagamento).where(
                    FolhaPagamento.pessoa_id == modelo.pessoa_id,
                    FolhaPagamento.competencia == competencia,
                )
            ).first()
            if not existe:
                ano, mes = (int(x) for x in competencia.split("-"))
                descontos = round(modelo.descontos, 2)
                valor_vale = _valor_vale(session, modelo.pessoa_id, competencia)
                _marcar_vale_aplicado(session, modelo.pessoa_id, competencia)
                # Retenções do modelo: a competência gerada é a MESMA folha do
                # mês seguinte, então INSS/IR seguem junto — sem eles, o líquido
                # (e a conta a pagar) nasciam inflados e a retenção sumia do
                # banco, não só da tela. Idem FGTS/DCTF (base da consolidação em
                # `gerar-guias`), conta bancária (o que os relatórios gerenciais
                # filtram) e dia de vencimento.
                valor_inss = round(modelo.valor_inss, 2)
                valor_ir = round(modelo.valor_ir, 2)
                valor_fgts = modelo.valor_fgts
                # AUMENTO NA FOLHA INCORPORADO (ver rules/rubrica_folha.py).
                # O modelo de recorrência é uma fotografia do salário do mês em
                # que ele foi criado — um aumento concedido depois ficava só na
                # competência em que foi lançado (como linha de vencimento) e o
                # mês seguinte voltava ao salário antigo, que é exatamente o que
                # o art. 468 da CLT não permite. A base do mês gerado é, então,
                # o bruto do modelo MAIS os aumentos concedidos daí até aqui.
                # É derivado das rubricas, nunca copiado: excluir o aumento
                # desfaz a incorporação sozinho, sem migração de dado.
                aumento = rubrica_folha.aumento_incorporado(
                    session, modelo.pessoa_id, modelo.competencia, competencia, fazenda_id,
                )
                valor_bruto = round(modelo.valor_bruto + aumento, 2)
                if aumento:
                    # Base maior, retenção maior: copiar o VALOR retido do
                    # modelo deixaria o INSS/IR/FGTS do mês novo calculado
                    # sobre o salário velho. Só recalcula o que tem percentual
                    # gravado — sem percentual não há base declarada, e deduzir
                    # uma seria inventar o número (mesma regra do holerite).
                    recalculadas = rubrica_folha.retencoes_recalculadas(
                        valor_bruto, modelo.percentual_inss, modelo.percentual_ir,
                        modelo.percentual_fgts, [],
                    )
                    valor_inss = recalculadas.get("valor_inss", valor_inss)
                    valor_ir = recalculadas.get("valor_ir", valor_ir)
                    valor_fgts = recalculadas.get("valor_fgts", valor_fgts)
                valor_liquido = _liquido_folha(
                    valor_bruto, descontos, valor_inss, valor_ir, valor_vale,
                )
                numero_lancamento = _proximo_numero_lancamento(session, ano)
                nova = FolhaPagamento(
                    pessoa_id=modelo.pessoa_id, competencia=competencia, valor_bruto=valor_bruto,
                    descontos=descontos,
                    percentual_inss=modelo.percentual_inss, valor_inss=valor_inss,
                    percentual_ir=modelo.percentual_ir, valor_ir=valor_ir,
                    valor_vale=valor_vale, valor_liquido=valor_liquido, status="pendente",
                    percentual_fgts=modelo.percentual_fgts, valor_fgts=valor_fgts,
                    percentual_dctf=modelo.percentual_dctf, valor_dctf=modelo.valor_dctf,
                    observacao=modelo.observacao, origem_recorrencia_id=modelo.id,
                    numero_lancamento_gerado=numero_lancamento,
                    centro_custo=modelo.centro_custo,
                    conta_corrente_id=modelo.conta_corrente_id,
                    dia_vencimento=modelo.dia_vencimento,
                    fazenda_id=fazenda_id,
                )
                session.add(nova)
                session.add(ContaGerencial(
                    numero_lancamento=numero_lancamento,
                    descricao=f"Folha de pagamento — {pessoa.nome} ({competencia})",
                    data_vencimento=_data_vencimento_folha(competencia, modelo.dia_vencimento),
                    data_competencia=date(ano, mes, 1),
                    fornecedor_cliente=pessoa.nome,
                    tipo_documento="Folha de pagamento",
                    centro_custo=modelo.centro_custo,
                    valor_total=valor_liquido,
                    parcela_num=1, parcela_total=1,
                    tipo="despesa", origem="auto",
                    conta_bancaria=_rotulo_conta_do_modelo(session, modelo),
                    fazenda_id=fazenda_id,
                ))
                session.commit()
                # Vale-alimentação do cadastro: a competência gerada nasce com
                # a verba, e não só a partir da primeira vez que alguém abrir a
                # listagem. Depois do commit, porque a rubrica precisa do id da
                # folha; e o recálculo daqui é o que deixa a CONTA A PAGAR já
                # nascer com o valor certo — é ela que o dono paga.
                session.refresh(nova)
                if _aplicar_vale_alimentacao(session, nova, pessoa):
                    session.commit()
            competencia = _competencia_seguinte(competencia)


def _corrigir_folha_gerada_sem_retencao(session: Session, fazenda_id: int | None = None) -> None:
    """
    Self-heal das competências que a recorrência JÁ gerou erradas (sem INSS/IR
    e com o líquido inflado), no mesmo espírito de `_remover_folha_duplicada` e
    `_remover_folha_pos_rescisao`.

    POR QUE reprocessar, e não só consertar a geração daqui pra frente: o erro
    está gravado no banco — no `valor_liquido` da folha e no `valor_total` da
    conta a pagar, que é o número que o dono efetivamente paga. Corrigir só a
    geração deixaria todas as competências já criadas mostrando (e cobrando) o
    valor errado para sempre, sem nenhum caminho de correção além de reeditar
    mês a mês na mão. Como a conta a pagar ainda está em aberto, ajustar agora
    corrige o futuro pagamento em vez de reescrever o passado.

    LIMITE DE SEGURANÇA — nunca toca em folha `status == "pago"` nem em conta a
    pagar com `valor_pago` preenchido: aí o dinheiro já saiu e mexer no líquido
    seria reescrever histórico financeiro. Uma folha paga com o líquido inflado
    fica exatamente como está (ver relato ao dono).

    Só age sobre a assinatura EXATA do bug, para não sobrescrever decisão de
    quem editou o lançamento à mão:
      1. a folha foi gerada pela recorrência (`origem_recorrencia_id`) e o
         modelo ainda existe;
      2. bruto e descontos continuam idênticos aos do modelo (linha intocada);
      3. as retenções da linha estão todas zeradas e o modelo tem retenção;
      4. o líquido gravado bate com a fórmula buggada (bruto − descontos − vale),
         isto é, nunca teve retenção descontada.
    Resta um caso ambíguo assumido: uma folha pendente em que o usuário zerou
    deliberadamente o INSS/IR de um mês, mantendo o modelo com retenção, é
    indistinguível de uma folha nascida do bug e volta a seguir o modelo. Não
    há como separar os dois no dado gravado, e a intenção registrada na
    recorrência é a melhor referência disponível.
    """
    # Filtro de fazenda incondicional — ver `_remover_folha_pos_rescisao`:
    # esta rotina REESCREVE valor de folha e de conta a pagar, então não pode
    # depender do padrão tolerante `if fazenda_id is not None`.
    query = select(FolhaPagamento).where(
        FolhaPagamento.status != "pago",
        FolhaPagamento.origem_recorrencia_id != None,  # noqa: E711
        FolhaPagamento.fazenda_id == fazenda_id,
    )

    houve_mudanca = False
    for registro in session.exec(query).all():
        modelo = session.get(FolhaPagamento, registro.origem_recorrencia_id)
        if not modelo or modelo.id == registro.id:
            continue
        # (2) linha ainda idêntica ao modelo no que o usuário poderia ter mexido.
        if abs(registro.valor_bruto - modelo.valor_bruto) > 0.001:
            continue
        if abs(registro.descontos - modelo.descontos) > 0.001:
            continue
        # A conta a pagar já quitada trava a correção mesmo com a folha ainda
        # "pendente" (baixa feita direto no Financeiro) — o dinheiro já saiu.
        conta = None
        if registro.numero_lancamento_gerado:
            conta = session.exec(
                select(ContaGerencial).where(
                    ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado
                )
            ).first()
            if conta and conta.valor_pago is not None:
                continue

        mudou = False
        # Campos que a geração simplesmente não copiava e que nascem vazios:
        # completa só quando ainda estão vazios (nunca sobrescreve escolha do
        # usuário) — não mexem no líquido, mas alimentam a consolidação de
        # guias (FGTS/DCTF) e o filtro por conta dos relatórios gerenciais.
        for campo in ("percentual_fgts", "valor_fgts", "percentual_dctf", "valor_dctf",
                      "conta_corrente_id", "dia_vencimento"):
            if getattr(registro, campo) is None and getattr(modelo, campo) is not None:
                setattr(registro, campo, getattr(modelo, campo))
                mudou = True
        if conta and conta.conta_bancaria is None:
            rotulo = _rotulo_conta_do_modelo(session, modelo)
            if rotulo:
                conta.conta_bancaria = rotulo
                session.add(conta)
                mudou = True

        # (3) e (4): a assinatura do líquido sem retenção nenhuma.
        sem_retencao_na_linha = not (
            registro.valor_inss or registro.valor_ir or registro.percentual_inss or registro.percentual_ir
        )
        modelo_tem_retencao = bool(modelo.valor_inss or modelo.valor_ir)
        liquido_buggado = _liquido_folha(
            registro.valor_bruto, registro.descontos, 0.0, 0.0, registro.valor_vale or 0.0,
            registro.valor_rubricas,
        )
        if (
            sem_retencao_na_linha
            and modelo_tem_retencao
            and abs(registro.valor_liquido - liquido_buggado) <= 0.001
        ):
            registro.percentual_inss = modelo.percentual_inss
            registro.valor_inss = round(modelo.valor_inss, 2)
            registro.percentual_ir = modelo.percentual_ir
            registro.valor_ir = round(modelo.valor_ir, 2)
            valor_vale = _valor_vale(session, registro.pessoa_id, registro.competencia)
            registro.valor_vale = valor_vale
            registro.valor_liquido = _liquido_folha(
                registro.valor_bruto, registro.descontos, registro.valor_inss, registro.valor_ir, valor_vale,
                registro.valor_rubricas,
            )
            if conta:
                conta.valor_total = registro.valor_liquido
                session.add(conta)
            mudou = True

        if mudou:
            session.add(registro)
            houve_mudanca = True

    if houve_mudanca:
        session.commit()


def _contexto_discriminacao(
    session: Session, registros: list[FolhaPagamento],
) -> dict:
    """
    Carrega DE UMA VEZ tudo o que a discriminação de várias folhas precisa —
    parcelas de vale, os vales de origem e a nota fiscal que gerou cada vale.

    Existe por dois motivos. O primeiro é desempenho: `_detalhe_folha` fazia
    uma consulta de parcelas por folha e, dentro dela, mais uma consulta de
    "parcelas irmãs" por parcela — N×M consultas só para numerar "3 de 13" numa
    listagem que já é chamada em toda abertura da tela.

    O segundo é isolamento entre fazendas, e é o que importa mais: o escopo
    aqui é o conjunto de `pessoa_id` das folhas recebidas, que já vieram
    filtradas por `fazenda_id` na listagem. Nenhuma parcela de vale de outra
    fazenda alcança este dicionário, porque nenhuma pessoa de outra fazenda
    entra na cláusula IN — e não existe caminho tolerante ("se veio fazenda,
    filtra") por onde um vazamento passe.
    """
    pessoa_ids = {r.pessoa_id for r in registros if r.pessoa_id}
    if not pessoa_ids:
        return {
            "parcelas_por_pessoa_competencia": {}, "assumidas_por_pessoa_competencia": {},
            "irmas_por_vale": {}, "vales": {}, "origens": {},
            "rubricas": {}, "compras_rubricas": {},
        }

    parcelas = session.exec(select(ValeParcela).where(ValeParcela.pessoa_id.in_(pessoa_ids))).all()
    irmas_por_vale: dict[int, list[ValeParcela]] = {}
    for p in parcelas:
        irmas_por_vale.setdefault(p.vale_id, []).append(p)
    for lista in irmas_por_vale.values():
        lista.sort(key=lambda x: (x.competencia, x.id or 0))

    # Só as parcelas das competências efetivamente lançadas entram no índice de
    # linhas — as demais servem apenas para numerar "k de n" na sequência
    # completa do vale.
    competencias = {(r.pessoa_id, r.competencia) for r in registros}
    por_pessoa_competencia: dict[tuple[int, str], list[ValeParcela]] = {}
    assumidas_por_pessoa_competencia: dict[tuple[int, str], list[ValeParcela]] = {}
    for p in parcelas:
        chave = (p.pessoa_id, p.competencia)
        if chave not in competencias:
            continue
        # Parcela assumida pela fazenda não vira linha de DESCONTO no
        # holerite — ela não foi descontada de ninguém (ver `_valor_vale`).
        # Continua em `irmas_por_vale` acima, porque a numeração "3 de 13"
        # é a posição na sequência do vale e não muda por causa disso.
        #
        # Ela vai para um índice SEPARADO (e não para `por_pessoa_competencia`
        # com uma marca) porque é `por_pessoa_competencia` que vira `detalhe`,
        # e `detalhe` é somado em vários lugares: qualquer somatório que
        # esquecesse de pular a marca voltaria a cobrar do funcionário o valor
        # que a fazenda assumiu. Este índice alimenta só a linha informativa
        # (ver `_vale_assumido_folha` e `holerite.linha_vale_assumido`).
        if p.assumida_pela_fazenda:
            assumidas_por_pessoa_competencia.setdefault(chave, []).append(p)
        else:
            por_pessoa_competencia.setdefault(chave, []).append(p)
    for lista in (*por_pessoa_competencia.values(), *assumidas_por_pessoa_competencia.values()):
        lista.sort(key=lambda x: (x.vale_id, x.id or 0))

    vale_ids = {p.vale_id for p in parcelas}
    vales = {
        v.id: v
        for v in (session.exec(select(ValeFuncionario).where(ValeFuncionario.id.in_(vale_ids))).all() if vale_ids else [])
    }
    origens = origens_lancamento_por_vale(session, vale_ids, "vale_funcionario_id") if vale_ids else {}
    # Rubricas avulsas do holerite (vencimentos/descontos acrescentados) e as
    # compras que os descontos de compra apontam — duas consultas para a
    # listagem inteira, pelo mesmo motivo das parcelas acima. Escopo: só as
    # folhas recebidas, que já vieram filtradas por fazenda.
    rubricas = rubrica_folha.rubricas_por_folha(session, registros)
    todas_rubricas = [r for lista in rubricas.values() for r in lista]
    return {
        "parcelas_por_pessoa_competencia": por_pessoa_competencia,
        "assumidas_por_pessoa_competencia": assumidas_por_pessoa_competencia,
        "irmas_por_vale": irmas_por_vale,
        "vales": vales,
        "origens": origens,
        "rubricas": rubricas,
        "compras_rubricas": rubrica_folha.compras_das_rubricas(session, todas_rubricas),
    }


# ---------------------------------------------------------------------------
# Congelamento da discriminação no pagamento (C7)
#
# O DEFEITO QUE ISTO FECHA. `_detalhe_folha` recalculava o recibo A CADA
# LEITURA, consultando `ValeParcela` ao vivo — inclusive para folha já paga.
# Só que o `valor_liquido` do pagamento ficou GRAVADO em `FolhaPagamento`, e o
# self-heal (`_corrigir_folha_gerada_sem_retencao`, e o de `valor_vale` na
# listagem) pula folha paga DE PROPÓSITO, para não reescrever dinheiro que já
# saiu. Os dois números chegavam então por caminhos diferentes e divergiam:
# editar um vale, quitá-lo, estorná-lo ou remanejar a parcela para outra
# competência DEPOIS de a folha ser paga fazia o holerite impresso hoje deixar
# de ser o recibo do que foi efetivamente pago. Num documento trabalhista isso
# é grave — o holerite é prova, não um relatório que se refaz.
#
# O DESENHO é o mesmo que a diária já usava (`encerrar_diaria`/`reabrir_diaria`
# em rh_contratos.py): no fechamento grava-se a FOTOGRAFIA, a leitura passa a
# ler a fotografia em vez de recalcular, e descongelar exige um ato explícito
# — aqui o estorno do pagamento (`estornar_pagamento_folha`), nunca em
# silêncio. Folha NÃO paga continua 100% ao vivo, com todos os self-heals.
# ---------------------------------------------------------------------------
def _discriminacao_congelada(registro: FolhaPagamento) -> list[dict] | None:
    """
    As linhas congeladas desta folha, ou None quando ela ainda é calculada ao
    vivo (folha não paga, paga antes desta feature — ver a migração
    b2f7c1a83d59 — ou pagamento estornado).

    JSON inválido cai em None de propósito: um caractere corrompido na coluna
    não pode derrubar a tela inteira de folha; a folha volta ao cálculo ao
    vivo, que é o comportamento que sempre existiu.
    """
    if not registro.discriminacao_congelada or registro.discriminacao_congelada_em is None:
        return None
    try:
        linhas = json.loads(registro.discriminacao_congelada)
    except (ValueError, TypeError):
        return None
    return linhas if isinstance(linhas, list) else None


def _congelar_discriminacao(session: Session, registro: FolhaPagamento) -> None:
    """
    Grava no pagamento a discriminação que gerou aquele líquido. Chamada no
    ÚNICO momento em que a folha passa a valer como recibo: quando ela vira
    `status == "pago"` (no POST que já nasce paga e no PUT que a marca paga).

    Nunca sobrescreve uma fotografia existente — congelar duas vezes a mesma
    folha pegaria o mundo de HOJE, que é exatamente o que não pode entrar num
    recibo já emitido.
    """
    if registro.discriminacao_congelada_em is not None:
        return
    registro.discriminacao_congelada = json.dumps(
        _detalhe_folha(session, registro), ensure_ascii=False,
    )
    registro.discriminacao_congelada_em = datetime.utcnow()
    session.add(registro)


def _descongelar_discriminacao(registro: FolhaPagamento) -> None:
    """Devolve a folha ao cálculo ao vivo. Só o estorno do pagamento chama —
    ver `estornar_pagamento_folha` (e `reabrir_diaria`, o mesmo padrão)."""
    registro.discriminacao_congelada = None
    registro.discriminacao_congelada_em = None


def _folha_resposta(registro: FolhaPagamento) -> dict:
    """
    O `model_dump()` da folha SEM o JSON da fotografia — a tela já recebe as
    mesmas linhas em `detalhe`, e mandar o blob junto dobraria o tamanho da
    listagem inteira sem acrescentar nada. No lugar dele vai só o fato que a
    tela precisa saber para rotular o documento: este recibo está congelado
    (e desde quando).
    """
    dados = registro.model_dump()
    dados.pop("discriminacao_congelada", None)
    congelado_em = dados.pop("discriminacao_congelada_em", None)
    dados["recibo_congelado"] = congelado_em is not None
    dados["recibo_congelado_em"] = congelado_em
    return dados


def _conta_do_numero(
    session: Session, numero_lancamento: str | None, fazenda_id: int | None,
) -> ContaGerencial | None:
    """
    A conta a pagar de um número de lançamento gerado pelo RH (folha, guia de
    FGTS/DCTF, férias, 13º), se existir. Ponto ÚNICO dessa busca no módulo:
    todo mundo que precisa decidir "esta conta já foi baixada?" antes de
    editar ou apagar passa por aqui, para a regra e o recorte de fazenda não
    voltarem a divergir de rotina para rotina.

    Filtro de fazenda INCONDICIONAL (`== fazenda_id`, que em None vira
    `IS NULL`) na PRÓPRIA consulta — nunca o padrão tolerante
    `if fazenda_id is not None: query = query.where(...)`, erradicado na Onda 1
    de segurança: quem chama isto reescreve ou apaga baixa de lançamento
    financeiro, e um token legado sem a claim de fazenda não pode alcançar a
    conta de outro tenant.
    """
    if not numero_lancamento:
        return None
    return session.exec(
        select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == numero_lancamento,
            ContaGerencial.fazenda_id == fazenda_id,
        )
    ).first()


def _conta_da_folha(
    session: Session, registro: FolhaPagamento, fazenda_id: int | None,
) -> ContaGerencial | None:
    """A conta a pagar emitida por esta folha, se existir (ver
    `_conta_do_numero` para o porquê do recorte de fazenda na consulta)."""
    return _conta_do_numero(session, registro.numero_lancamento_gerado, fazenda_id)


def _exigir_conta_nao_paga(conta: ContaGerencial | None, de_que: str, o_que: str) -> None:
    """
    Recusa a exclusão quando a conta a pagar vinculada JÁ FOI BAIXADA no
    Financeiro.

    O `status` do recibo (folha/férias/13º: "pendente" ou "pago") e a BAIXA da
    conta a pagar podem discordar: o recibo segue "pendente" no RH e alguém dá
    baixa no lançamento direto no Financeiro (Contas a pagar), que é um fluxo
    normal. Quem só olhava `registro.status` apagava a ContaGerencial sem ver
    `valor_pago` — e com ela sumia do extrato um pagamento que ACONTECEU:
    dinheiro que saiu do caixa desaparecendo do histórico. Mesma regra e mesmo
    tom de `excluir_guia_folha_encargo`, `_cancelar_conta_pendente` e
    `reabrir_periodo_diaria`: conta já paga fica onde está; quem quiser
    desfazer o pagamento faz isso em Lançamentos, onde a exclusão é explícita
    e auditada.
    """
    if conta is None or conta.valor_pago is None:
        return
    quando = f" em {conta.data_pagamento.strftime('%d/%m/%Y')}" if conta.data_pagamento else ""
    raise HTTPException(
        status_code=400,
        detail=(
            f"A conta a pagar {de_que} ({conta.numero_lancamento}) já foi baixada no Financeiro"
            f"{quando} — excluir {o_que} apagaria esse pagamento do extrato. Estorne o pagamento "
            f"(ou exclua o lançamento em Lançamentos > Excluir lançamento) antes de excluir {o_que}."
        ),
    )


def _detalhe_folha(
    session: Session, registro: FolhaPagamento, contexto: dict | None = None,
    pessoa: Pessoa | None = None,
) -> list[dict]:
    """
    Discriminação completa do lançamento nas QUATRO colunas do holerite de
    papel — Descrição · Referência · Vencimentos · Descontos — mais o líquido.

    A mudança que importa em relação à versão anterior: cada linha carrega
    agora a REFERÊNCIA (de onde o valor veio: "7,78% sobre R$ 2.000,00",
    "Parcela 3 de 13 · vale de 12/03/2026") e, quando é desconto de vale, a
    ORIGEM com o `vale_id` — data em que o dinheiro saiu, forma de pagamento,
    observação, nº do lançamento no extrato e a nota fiscal quando o vale
    nasceu de um item de nota. Antes disso tudo era jogado fora e sobravam N
    linhas escritas só "Vale", que a tela tentava reconhecer por regex no
    rótulo em português — sem nenhum jeito de desempatar dois vales com
    parcela de mesmo valor no mesmo mês.

    `label`/`valor` continuam exatamente como eram: são o contrato antigo
    (recibo em PDF, expansão da tela de Ações, testes de fechamento do
    líquido) e nada nele mudou de forma.

    FOLHA PAGA NÃO PASSA POR AQUI (C7): a discriminação dela foi congelada no
    pagamento e é lida de volta tal como estava. Recalcular ao vivo era o que
    fazia o recibo de uma folha paga deixar de bater com o líquido que foi
    pago quando o vale mudava depois — ver o bloco de congelamento acima.
    """
    congelada = _discriminacao_congelada(registro)
    if congelada is not None:
        return congelada

    ctx = contexto if contexto is not None else _contexto_discriminacao(session, [registro])
    parcelas_vale = ctx["parcelas_por_pessoa_competencia"].get((registro.pessoa_id, registro.competencia), [])
    rubricas = ctx.get("rubricas", {}).get(registro.id, [])
    # BASE das retenções ≠ salário bruto quando há rubrica SALARIAL lançada
    # (bonificação, guelta, aumento): o INSS foi calculado sobre bruto + elas.
    # Reembolso e indenização ficam fora, por serem indenizatórios — é
    # justamente esta distinção que faz a referência "9% sobre R$ 3.500,00"
    # bater com o valor retido em vez de acusar "valor ajustado à mão".
    base_retencao = round(registro.valor_bruto + (registro.valor_rubricas_tributaveis or 0.0), 2)

    if pessoa is None:
        pessoa = session.get(Pessoa, registro.pessoa_id)
    ano, mes = (int(x) for x in registro.competencia.split("-"))
    dias_mes = calendar.monthrange(ano, mes)[1]

    detalhe = [holerite.linha(
        "bruto", "Salário bruto", registro.valor_bruto,
        "Salário",
        holerite.referencia_bruto(pessoa.data_admissao if pessoa else None, registro.competencia, dias_mes),
        provento=round(registro.valor_bruto, 2),
    )]
    # A linha existe quando existe VALOR retido — nunca pelo percentual. O
    # percentual é só a referência de como o valor foi obtido, e o formulário
    # permite digitar o valor direto (campo `inssManual`), gravando
    # `valor_inss=300, percentual_inss=0`: testar o percentual fazia o líquido
    # cair sem nenhum desconto aparecer na discriminação — o recibo não fechava.
    # O caminho inverso (percentual preenchido e valor zero) não retém nada, e
    # por isso também não vira linha. Não se deduz percentual a partir do valor:
    # sem base declarada pelo usuário, qualquer percentual aqui seria inventado.
    for tipo, rotulo, valor, percentual in (
        ("inss", "INSS", registro.valor_inss, registro.percentual_inss),
        ("ir", "IR", registro.valor_ir, registro.percentual_ir),
    ):
        if not valor:
            continue
        sufixo = f" ({percentual:g}%)" if percentual else ""
        referencia, origem = holerite.referencia_retencao(valor, percentual, base_retencao)
        detalhe.append(holerite.linha(
            tipo, f"{rotulo}{sufixo}", -valor, rotulo, referencia,
            desconto=round(valor, 2), origem=origem,
        ))
    # Uma linha por parcela de vale, com o valor REAL da parcela (descontos de
    # vale). Numera a parcela na sequência do PRÓPRIO vale (k/n, ex.: 1/2, 2/2),
    # ordenando todas as parcelas do vale por competência — não só as deste mês.
    for p in parcelas_vale:
        irmas = ctx["irmas_por_vale"].get(p.vale_id, [p])
        n = len(irmas)
        k = next((i + 1 for i, x in enumerate(irmas) if x.id == p.id), 1)
        vale = ctx["vales"].get(p.vale_id)
        origem_lancamento = ctx["origens"].get(p.vale_id)
        detalhe.append(holerite.linha(
            "vale", f"Vale (parcela {k}/{n})", -p.valor,
            holerite.descricao_vale(vale.observacao if vale else None, origem_lancamento),
            holerite.referencia_vale(k, n, vale.data_pagamento if vale else None),
            desconto=round(p.valor, 2),
            origem=holerite.origem_vale(vale, p, k, n, origem_lancamento) if vale else None,
        ))
    # "Descontos de folha" manuais — vêm de registro.descontos, SEM misturar vale.
    if abs(registro.descontos) > 0.001:
        detalhe.append(holerite.linha(
            "outros", "Outros descontos", -registro.descontos,
            "Outros descontos",
            # C4: `FolhaPagamento.descontos` é um float solto — não existe
            # modelo filho, FK nem observação estruturada para itemizar. Dizer
            # isso é mais honesto que deixar a única célula vazia do documento.
            "Valor único, sem detalhamento gravado",
            desconto=round(registro.descontos, 2),
        ))
    # Rubricas avulsas do holerite (ver rh_folha_rubricas.py e
    # rules/rubrica_folha.py): vencimentos primeiro, descontos depois, cada um
    # com a referência que declara o regime tributário adotado ou a compra que
    # está sendo abatida. Entram DEPOIS das linhas fixas e ANTES do líquido —
    # o líquido continua sendo o rodapé, nunca uma linha do corpo.
    detalhe.extend(rubrica_folha.linhas_de_rubricas(rubricas, ctx.get("compras_rubricas", {})))
    detalhe.append(holerite.linha(
        "liquido", "Valor líquido", registro.valor_liquido, "Líquido", "",
    ))
    return detalhe


def _vale_assumido_folha(
    session: Session, registro: FolhaPagamento, contexto: dict | None = None,
) -> list[dict]:
    """
    As parcelas de vale desta competência que a FAZENDA assumiu — o mês que o
    dono mandou desconsiderar, ou o saldo varrido por um cancelamento.

    Campo à parte de `detalhe`, NUNCA dentro dele: essas parcelas não foram
    descontadas de ninguém (`_valor_vale` as ignora), e `detalhe` é a lista
    que vira total de descontos, líquido, holerite impresso e verbas do
    pop-up de pagamento. O motivo de elas voltarem a viajar até a tela é
    outro: enquanto sumiam por completo, sumia junto o painel "Descontos de
    vale" daquele mês — e com ele o botão "Ações", única porta para desfazer
    a desconsideração (`reverter_desconsideracao` em rh_vale_acoes.py). O
    dono errava o clique e ficava sem volta naquela competência.

    Calculado SEMPRE ao vivo, inclusive em folha paga: aqui não há recibo a
    congelar (nenhum valor destas linhas entra em conta nenhuma), e assumir/
    reverter já é recusado em folha paga na origem, pela trava de
    `_exigir_competencias_nao_pagas`.
    """
    ctx = contexto if contexto is not None else _contexto_discriminacao(session, [registro])
    linhas: list[dict] = []
    for p in ctx["assumidas_por_pessoa_competencia"].get((registro.pessoa_id, registro.competencia), []):
        vale = ctx["vales"].get(p.vale_id)
        if not vale:
            continue
        # "k de n" é a posição na sequência COMPLETA do vale (inclui as
        # assumidas), a mesma numeração das linhas de desconto — senão a
        # parcela assumida de agosto seria "2/12" no painel e "3/13" no vale.
        irmas = ctx["irmas_por_vale"].get(p.vale_id, [p])
        n = len(irmas)
        k = next((i + 1 for i, x in enumerate(irmas) if x.id == p.id), 1)
        linhas.append(holerite.linha_vale_assumido(vale, p, k, n, ctx["origens"].get(p.vale_id)))
    return linhas


@router.get("/folha-pagamento")
def listar_folha_pagamento(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    _remover_folha_duplicada(session, fazenda_id)
    # `_remover_folha_pos_rescisao` NÃO é chamada aqui de propósito: um GET
    # não pode apagar dado. Ela roda em `fechar_rescisao`, no momento em que
    # o desligamento passa a existir no sistema (ver a docstring dela).
    _gerar_folha_recorrente(session, fazenda_id)
    _corrigir_folha_gerada_sem_retencao(session, fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(FolhaPagamento)
    if fazenda_id is not None:
        query = query.where(FolhaPagamento.fazenda_id == fazenda_id)
    registros = session.exec(query.order_by(FolhaPagamento.competencia.desc())).all()

    # Self-heal: um vale lançado DEPOIS da folha (ainda não paga) não estava
    # sendo refletido. Recomputa o valor_vale a partir da SOMA das parcelas e,
    # se mudou, atualiza o líquido e a conta a pagar vinculada.
    houve_mudanca = False
    for registro in registros:
        if registro.status == "pago":
            continue
        vv = _valor_vale(session, registro.pessoa_id, registro.competencia)
        if abs(vv - (registro.valor_vale or 0)) > 0.001:
            registro.valor_vale = vv
            registro.valor_liquido = _liquido_folha(
                registro.valor_bruto, registro.descontos, registro.valor_inss, registro.valor_ir, vv,
                registro.valor_rubricas,
            )
            _marcar_vale_aplicado(session, registro.pessoa_id, registro.competencia)
            session.add(registro)
            if registro.numero_lancamento_gerado:
                conta = session.exec(
                    select(ContaGerencial).where(
                        ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado
                    )
                ).first()
                if conta and conta.valor_pago is None:
                    conta.valor_total = registro.valor_liquido
                    session.add(conta)
            houve_mudanca = True
        # Vale-alimentação: mesma ideia do self-heal acima, e pelo mesmo
        # motivo. Ligar o benefício (ou corrigir o valor-base) no cadastro tem
        # de aparecer nas competências AINDA ABERTAS sem o dono ter de reabrir
        # e salvar cada folha — e não pode aparecer nas pagas, que a própria
        # `_sincronizar_vale_alimentacao` recusa. Roda DEPOIS do bloco do vale
        # para não pular o `_marcar_vale_aplicado` dele.
        if _aplicar_vale_alimentacao(session, registro):
            houve_mudanca = True
    if houve_mudanca:
        session.commit()
        # O commit expira os objetos já carregados; recarrega para o model_dump.
        registros = session.exec(query.order_by(FolhaPagamento.competencia.desc())).all()

    # Data de vencimento da folha (mês de pagamento) — vem da conta a pagar
    # gerada. Mapeia numero_lancamento_gerado → data_vencimento.
    numeros = [r.numero_lancamento_gerado for r in registros if r.numero_lancamento_gerado]
    venc_por_numero: dict[str, object] = {}
    if numeros:
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all():
            if c.numero_lancamento and c.numero_lancamento not in venc_por_numero:
                venc_por_numero[c.numero_lancamento] = c.data_vencimento

    nomes_usuarios = mapa_usuarios(session, {r.usuario_id for r in registros})

    # Uma única carga de parcelas/vales/notas para TODAS as folhas da resposta
    # (ver `_contexto_discriminacao`) — antes era uma consulta por folha mais
    # uma por parcela só para numerar "3 de 13".
    contexto = _contexto_discriminacao(session, registros)
    pessoas_obj = {
        p.id: p
        for p in session.exec(select(Pessoa).where(Pessoa.id.in_({r.pessoa_id for r in registros}))).all()
    } if registros else {}

    saida = []
    for r in registros:
        detalhe = _detalhe_folha(session, r, contexto=contexto, pessoa=pessoas_obj.get(r.pessoa_id))
        saida.append({
            **_folha_resposta(r),
            "pessoa_nome": pessoas.get(r.pessoa_id, "—"),
            "data_vencimento": venc_por_numero.get(r.numero_lancamento_gerado),
            "detalhe": detalhe,
            # Parcelas assumidas pela fazenda — informativas, FORA de
            # `detalhe` e de `totais` de propósito (ver `_vale_assumido_folha`).
            "vale_assumido": _vale_assumido_folha(session, r, contexto=contexto),
            # Totais das duas colunas + líquido e a flag de recibo impossível
            # (descontos maiores que vencimentos), calculados no servidor para
            # as duas telas de folha lerem exatamente o mesmo número.
            "totais": holerite.totais_holerite(detalhe),
            "bases": holerite.bases_holerite(r),
            "usuario_nome": nomes_usuarios.get(r.usuario_id),
        })
    return saida


@router.post("/folha-pagamento")
def criar_folha_pagamento(
    dados: FolhaPagamentoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.recorrente and not (dados.dia_vencimento and 1 <= dados.dia_vencimento <= 28):
        raise HTTPException(status_code=400, detail="Informe o dia de vencimento (1 a 28) para lançamentos recorrentes")
    if _rescisao_fechada_encerra_competencia(session, dados.pessoa_id, dados.competencia, fazenda_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Esta pessoa tem rescisão fechada que já encerra esta competência "
                "— não é possível lançar folha. No mês do desligamento, o saldo de "
                "salário já é pago pela própria rescisão."
            ),
        )
    # Idempotência: nunca mais de uma folha por pessoa/competência (ver
    # comentário de _valor_vale) — sem esta checagem, a mesma pessoa acabava
    # com dois lançamentos para o mesmo mês (duplicado em Ações > Folha).
    ja_lancada = session.exec(
        select(FolhaPagamento).where(
            FolhaPagamento.pessoa_id == dados.pessoa_id,
            FolhaPagamento.competencia == dados.competencia,
            FolhaPagamento.fazenda_id == fazenda_id,
        )
    ).first()
    if ja_lancada:
        raise HTTPException(
            status_code=400,
            detail="Já existe um lançamento de folha para esta pessoa nesta competência — edite o lançamento existente.",
        )
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)
    descontos = round(dados.descontos, 2)  # "descontos de folha" manuais, sem vale
    valor_vale = _valor_vale(session, dados.pessoa_id, dados.competencia)
    _marcar_vale_aplicado(session, dados.pessoa_id, dados.competencia)
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    # O vale-alimentação do cadastro entra JÁ no líquido que vai ser gravado e
    # na conta a pagar que nasce logo abaixo. Não dá para deixar só para o
    # `_aplicar_vale_alimentacao` de depois do commit: numa folha que já nasce
    # PAGA a conta nasce com `valor_pago` preenchido, e conta baixada não é
    # reescrita por ninguém (nem deve ser) — ela ficaria pagando o líquido sem
    # a verba enquanto o holerite mostraria a verba.
    calculo_va = vale_alimentacao.calcular(pessoa, dados.competencia)
    valor_liquido = _liquido_folha(
        dados.valor_bruto, descontos, valor_inss, valor_ir, valor_vale,
        calculo_va["valor"] if calculo_va else 0.0,
    )
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")
    valor_fgts = _calcular_encargo_projetado(dados.valor_bruto, dados.percentual_fgts, dados.valor_fgts)
    valor_dctf = _calcular_encargo_projetado(dados.valor_bruto, dados.percentual_dctf, dados.valor_dctf)

    # Gera também a conta a pagar correspondente — sem isso, a folha nunca
    # aparecia em Contas a Pagar nem na Agenda (só as competências seguintes,
    # geradas por _gerar_folha_recorrente, tinham essa conta criada).
    ano, mes = (int(x) for x in dados.competencia.split("-"))
    numero_lancamento = _proximo_numero_lancamento(session, ano)

    registro = FolhaPagamento(
        pessoa_id=dados.pessoa_id, competencia=dados.competencia, valor_bruto=dados.valor_bruto,
        descontos=descontos, percentual_inss=dados.percentual_inss, percentual_ir=dados.percentual_ir,
        valor_inss=valor_inss, valor_ir=valor_ir, valor_vale=valor_vale, valor_liquido=valor_liquido,
        percentual_fgts=dados.percentual_fgts, valor_fgts=valor_fgts,
        percentual_dctf=dados.percentual_dctf, valor_dctf=valor_dctf,
        data_pagamento=dados.data_pagamento, status=dados.status, observacao=dados.observacao,
        recorrente=dados.recorrente, dia_vencimento=dados.dia_vencimento if dados.recorrente else None,
        numero_lancamento_gerado=numero_lancamento,
        centro_custo=dados.centro_custo,
        conta_corrente_id=conta_corrente.id if conta_corrente else None,
        usuario_id=user.id,
        fazenda_id=fazenda_id,
    )
    session.add(registro)
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Folha de pagamento — {pessoa.nome} ({dados.competencia})",
        data_vencimento=_data_vencimento_folha(dados.competencia, dados.dia_vencimento),
        data_competencia=date(ano, mes, 1),
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Folha de pagamento",
        centro_custo=dados.centro_custo,
        valor_total=valor_liquido,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        data_pagamento=dados.data_pagamento if dados.status == "pago" else None,
        valor_pago=valor_liquido if dados.status == "pago" else None,
        conta_bancaria=rotulo_conta_corrente(conta_corrente) if conta_corrente else None,
        fazenda_id=fazenda_id,
    ))
    session.commit()
    session.refresh(registro)
    # A LINHA do vale-alimentação (o valor dela já entrou no líquido acima).
    # Só é criada agora porque a rubrica precisa do id da folha — e entra
    # ANTES do congelamento abaixo, senão uma folha que já nasce paga viraria
    # um recibo sem a verba que o funcionário recebeu. `recem_criada` é o que
    # permite isso na folha já paga; ver `_sincronizar_vale_alimentacao`.
    if _aplicar_vale_alimentacao(session, registro, pessoa, recem_criada=True):
        session.commit()
        session.refresh(registro)
    # Folha que já NASCE paga é recibo desde o primeiro instante: congela a
    # discriminação agora (ver `_congelar_discriminacao`). Depois do commit,
    # porque a fotografia tem de ser a do lançamento efetivamente gravado.
    if registro.status == "pago":
        _congelar_discriminacao(session, registro)
        session.commit()
        session.refresh(registro)
    return _folha_resposta(registro)


@router.put("/folha-pagamento/{registro_id}")
def atualizar_folha_pagamento(
    registro_id: int, dados: FolhaPagamentoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(FolhaPagamento, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Registro de folha não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Lançamento de folha já pago não pode ser editado.")
    pessoa_nova = session.get(Pessoa, dados.pessoa_id)
    if not pessoa_nova or (pessoa_nova.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    descontos = round(dados.descontos, 2)  # "descontos de folha" manuais, sem vale
    valor_vale = _valor_vale(session, dados.pessoa_id, dados.competencia)
    _marcar_vale_aplicado(session, dados.pessoa_id, dados.competencia)
    # `registro.valor_rubricas` entra aqui porque esta folha JÁ EXISTE e pode
    # ter rubricas lançadas (ver rh_folha_rubricas.py): sem ele, salvar a
    # edição do bruto apagava do líquido — e da conta a pagar — a bonificação
    # ou o reembolso que o dono já tinha acrescentado ao holerite.
    valor_liquido = _liquido_folha(
        dados.valor_bruto, descontos, valor_inss, valor_ir, valor_vale, registro.valor_rubricas,
    )
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")
    if dados.recorrente and not (dados.dia_vencimento and 1 <= dados.dia_vencimento <= 28):
        raise HTTPException(status_code=400, detail="Informe o dia de vencimento (1 a 28) para lançamentos recorrentes")
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)
    valor_fgts = _calcular_encargo_projetado(dados.valor_bruto, dados.percentual_fgts, dados.valor_fgts)
    valor_dctf = _calcular_encargo_projetado(dados.valor_bruto, dados.percentual_dctf, dados.valor_dctf)
    registro.pessoa_id = dados.pessoa_id
    registro.competencia = dados.competencia
    registro.valor_bruto = dados.valor_bruto
    registro.descontos = descontos
    registro.percentual_inss = dados.percentual_inss
    registro.percentual_ir = dados.percentual_ir
    registro.valor_inss = valor_inss
    registro.valor_ir = valor_ir
    registro.valor_vale = valor_vale
    registro.valor_liquido = valor_liquido
    registro.percentual_fgts = dados.percentual_fgts
    registro.valor_fgts = valor_fgts
    registro.percentual_dctf = dados.percentual_dctf
    registro.valor_dctf = valor_dctf
    registro.data_pagamento = dados.data_pagamento
    registro.status = dados.status
    registro.observacao = dados.observacao
    registro.recorrente = dados.recorrente
    registro.dia_vencimento = dados.dia_vencimento if dados.recorrente else None
    registro.centro_custo = dados.centro_custo
    registro.conta_corrente_id = conta_corrente.id if conta_corrente else None
    session.add(registro)

    # Mantém a conta a pagar gerada automaticamente em sincronia com a edição.
    if registro.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        if conta and conta.valor_pago is None:
            pessoa = session.get(Pessoa, dados.pessoa_id)
            ano, mes = (int(x) for x in dados.competencia.split("-"))
            conta.descricao = f"Folha de pagamento — {pessoa.nome} ({dados.competencia})"
            conta.fornecedor_cliente = pessoa.nome
            conta.data_vencimento = _data_vencimento_folha(dados.competencia, dados.dia_vencimento)
            conta.data_competencia = date(ano, mes, 1)
            conta.centro_custo = dados.centro_custo
            conta.valor_total = valor_liquido
            conta.conta_bancaria = rotulo_conta_corrente(conta_corrente) if conta_corrente else None
            if dados.status == "pago":
                conta.data_pagamento = dados.data_pagamento
                conta.valor_pago = valor_liquido
            session.add(conta)

    # A folha acabou de virar recibo (o botão "Marcar como pago" cai aqui, e o
    # endpoint recusa editar folha já paga — então esta é sempre a transição
    # pendente → pago). Congela ANTES do commit, com os valores finais já
    # atribuídos ao registro: é esta discriminação que gerou o líquido pago.
    if registro.status == "pago":
        _congelar_discriminacao(session, registro)

    session.commit()
    session.refresh(registro)
    return _folha_resposta(registro)


@router.post("/folha-pagamento/{registro_id}/estornar")
def estornar_pagamento_folha(
    registro_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Estorna o pagamento da folha: desfaz a baixa da conta a pagar, devolve o
    lançamento a "pendente" e DESCONGELA a discriminação — a folha volta a ser
    calculada ao vivo, com todos os self-heals de vale valendo de novo.

    Por que este endpoint precisa existir: a partir do C7 a folha paga guarda a
    fotografia do recibo (ver `_congelar_discriminacao`). Sem uma porta de
    saída explícita, corrigir um pagamento errado exigiria mexer no banco à
    mão — e descongelar em silêncio, no meio de outra operação, recriaria
    exatamente a divergência que o congelamento existe para impedir. É o mesmo
    par de `encerrar_diaria`/`reabrir_diaria`: congela no fechamento,
    descongela só por um ato do usuário que diz "este pagamento não vale".

    Depois do estorno a folha volta a ser editável e excluível pelo fluxo
    normal (o PUT e o DELETE recusam folha paga), e um novo pagamento congela
    uma fotografia NOVA — a do mundo daquele momento.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(FolhaPagamento, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Registro de folha não encontrado")
    if registro.status != "pago":
        raise HTTPException(
            status_code=400,
            detail="Esta folha não está paga — não há pagamento a estornar.",
        )

    conta = _conta_da_folha(session, registro, fazenda_id)
    if conta is not None:
        conta.data_pagamento = None
        conta.valor_pago = None
        session.add(conta)

    registro.status = "pendente"
    registro.data_pagamento = None
    _descongelar_discriminacao(registro)
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return _folha_resposta(registro)


@router.delete("/folha-pagamento/{registro_id}")
def excluir_folha_pagamento(
    registro_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(FolhaPagamento, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Registro de folha não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Lançamento de folha já pago não pode ser excluído aqui — exclua em Lançamentos > Excluir lançamento.")
    conta = _conta_da_folha(session, registro, fazenda_id)
    # `registro.status` não basta: a folha pendente no RH pode ter a conta a
    # pagar já baixada no Financeiro (ver `_exigir_conta_nao_paga`).
    _exigir_conta_nao_paga(conta, "desta folha", "a folha")
    if conta is not None:
        session.delete(conta)
    session.delete(registro)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Guia de FGTS/DCTF — lançamento manual ou por leitura automática do PDF/foto
# da guia real (ver fazenda.rules.leitura_documento, tipo_documento
# 'guia_fgts'/'guia_dctf'). Substitui o antigo "Gerar guias de FGTS/DCTF"
# (soma automática projetada dos lançamentos de folha, sem vínculo com uma
# guia real, sem cálculo de fórmula legal — decisão do usuário: excluir essa
# projeção e lançar a guia de verdade, com seus campos estruturados
# (GuiaFolhaEncargo) para permitir relatório depois). A conta a pagar criada
# é um registro comum de ContaGerencial (mesmo padrão de Folha/Férias/13º) —
# editável pelo fluxo normal de Contas a Pagar/Lançamentos. Diferente de
# Folha/Férias/13º, aqui `codigo_conta` já sai preenchido (ver
# CODIGO_CONTA_GUIA_FGTS/CODIGO_CONTA_GUIA_DCTF): o destino no plano de
# contas é sempre o mesmo, sem ambiguidade a resolver depois.
# ---------------------------------------------------------------------------
TIPO_DOCUMENTO_GUIA_FGTS = "Guia FGTS"
TIPO_DOCUMENTO_GUIA_DCTF = "Guia DCTF"
# Conta gerencial do plano de contas (finalidade administrativa, categoria
# folha de pagamento) a que cada guia pertence — já cadastrada no plano de
# contas de cada fazenda e vinculada ao produto de estoque correspondente
# (dado de cada tenant — PlanoContaGerencial/Produto.conta_gerencial_despesa_padrao
# — carregado via CSV/tela própria, não seed deste repo). Fixo por tipo (não
# escolhido pelo usuário) porque, ao contrário da Folha/Férias/13º (que ficam
# sem codigo_conta e são classificadas depois em Financeiro), aqui o destino é
# sempre o mesmo — sem ambiguidade a resolver.
CODIGO_CONTA_GUIA_FGTS = "3.03.01.07"
CODIGO_CONTA_GUIA_DCTF = "3.03.01.06"


class GuiaFolhaEncargoIn(BaseModel):
    tipo: str  # "fgts" | "dctf"
    competencia: str  # "AAAA-MM"
    codigo_receita: str | None = None  # só DCTF
    valor_principal: float
    valor_multa: float = 0.0
    valor_juros: float = 0.0
    data_vencimento: date
    linha_digitavel: str | None = None
    # "manual" (usuário digitou) ou "leitura_automatica" (veio pré-preenchido
    # de POST /financeiro/ler-documento e o usuário só confirmou/ajustou).
    origem: str = "manual"
    centro_custo: str = "Pecuária Leiteira"


@router.post("/folha-pagamento/guias")
def lancar_guia_folha_encargo(
    dados: GuiaFolhaEncargoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Lança uma guia de FGTS ou DCTF: cria a conta a pagar (mesmo padrão de
    sempre) E grava os campos estruturados da guia numa tabela própria
    (GuiaFolhaEncargo), para dar pra montar relatório em cima disso depois —
    não fica só um PDF anexado sem dado nenhum extraído. O PDF/foto original,
    se o usuário anexar, é vinculado depois ao numero_lancamento devolvido
    aqui via POST /financeiro/lancamentos/{numero_lancamento}/anexos (mesmo
    mecanismo de qualquer outro anexo financeiro).
    """
    if dados.tipo not in ("fgts", "dctf"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'fgts' ou 'dctf'")
    valor_total = round(dados.valor_principal + dados.valor_multa + dados.valor_juros, 2)
    if valor_total <= 0:
        raise HTTPException(status_code=400, detail="O valor total da guia deve ser positivo")

    ano, mes = (int(x) for x in dados.competencia.split("-"))
    numero_lancamento = _proximo_numero_lancamento(session, ano)
    label = TIPO_DOCUMENTO_GUIA_FGTS if dados.tipo == "fgts" else TIPO_DOCUMENTO_GUIA_DCTF
    codigo_conta = CODIGO_CONTA_GUIA_FGTS if dados.tipo == "fgts" else CODIGO_CONTA_GUIA_DCTF
    conta = ContaGerencial(
        fazenda_id=fazenda_id,
        numero_lancamento=numero_lancamento,
        descricao=f"{label} — {dados.competencia}",
        data_vencimento=dados.data_vencimento,
        data_competencia=date(ano, mes, 1),
        tipo_documento=label,
        codigo_conta=codigo_conta,
        centro_custo=dados.centro_custo,
        valor_total=valor_total,
        parcela_num=1, parcela_total=1,
        numero_boleto=dados.linha_digitavel,
        tipo="despesa", origem="manual",
        usuario_id=user.id if isinstance(user, Usuario) else None,
    )
    session.add(conta)
    guia = GuiaFolhaEncargo(
        fazenda_id=fazenda_id,
        tipo=dados.tipo,
        competencia=dados.competencia,
        codigo_receita=dados.codigo_receita if dados.tipo == "dctf" else None,
        valor_principal=dados.valor_principal,
        valor_multa=dados.valor_multa,
        valor_juros=dados.valor_juros,
        valor_total=valor_total,
        data_vencimento=dados.data_vencimento,
        linha_digitavel=dados.linha_digitavel,
        numero_lancamento=numero_lancamento,
        origem=dados.origem if dados.origem in ("manual", "leitura_automatica") else "manual",
        usuario_id=user.id if isinstance(user, Usuario) else None,
    )
    session.add(guia)
    session.commit()
    session.refresh(conta)
    session.refresh(guia)
    return {**guia.model_dump(), "conta_id": conta.id}


@router.get("/folha-pagamento/guias")
def listar_guias_folha_encargo(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lista as guias de FGTS/DCTF já lançadas (mais recentes primeiro) — usada
    pelo relatório da Folha de Pagamento."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(GuiaFolhaEncargo).order_by(GuiaFolhaEncargo.competencia.desc(), GuiaFolhaEncargo.id.desc())
    if fazenda_id is not None:
        query = query.where(GuiaFolhaEncargo.fazenda_id == fazenda_id)
    return [g.model_dump() for g in session.exec(query).all()]


def _conta_da_guia(
    session: Session, guia: GuiaFolhaEncargo, fazenda_id: int | None,
) -> ContaGerencial | None:
    """A conta a pagar da guia de FGTS/DCTF, se existir.

    Passou a buscar pelo par (numero_lancamento, fazenda) e não só pelo
    número: quem chama isto EDITA ou APAGA lançamento financeiro, e busca sem
    recorte de fazenda é o mesmo tipo de furo já fechado em
    `_reconciliar_vale_competencias`. Ver `_conta_do_numero`."""
    return _conta_do_numero(session, guia.numero_lancamento, fazenda_id)


@router.put("/folha-pagamento/guias/{guia_id}")
def atualizar_guia_folha_encargo(
    guia_id: int, dados: GuiaFolhaEncargoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Corrige uma guia de FGTS/DCTF já lançada. Diferente de FolhaPagamento/
    FeriasFuncionario, GuiaFolhaEncargo não tem campo `status` próprio — "já
    paga" é decidido pela ContaGerencial vinculada (valor_pago preenchido).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    guia = session.get(GuiaFolhaEncargo, guia_id)
    if not guia or (guia.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Guia de FGTS/DCTF não encontrada")
    conta = _conta_da_guia(session, guia, fazenda_id)
    if conta and conta.valor_pago is not None:
        raise HTTPException(status_code=400, detail="Guia já paga não pode ser editada.")
    if dados.tipo not in ("fgts", "dctf"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'fgts' ou 'dctf'")
    valor_total = round(dados.valor_principal + dados.valor_multa + dados.valor_juros, 2)
    if valor_total <= 0:
        raise HTTPException(status_code=400, detail="O valor total da guia deve ser positivo")

    label = TIPO_DOCUMENTO_GUIA_FGTS if dados.tipo == "fgts" else TIPO_DOCUMENTO_GUIA_DCTF
    codigo_conta = CODIGO_CONTA_GUIA_FGTS if dados.tipo == "fgts" else CODIGO_CONTA_GUIA_DCTF
    ano, mes = (int(x) for x in dados.competencia.split("-"))

    guia.tipo = dados.tipo
    guia.competencia = dados.competencia
    guia.codigo_receita = dados.codigo_receita if dados.tipo == "dctf" else None
    guia.valor_principal = dados.valor_principal
    guia.valor_multa = dados.valor_multa
    guia.valor_juros = dados.valor_juros
    guia.valor_total = valor_total
    guia.data_vencimento = dados.data_vencimento
    guia.linha_digitavel = dados.linha_digitavel
    guia.origem = dados.origem if dados.origem in ("manual", "leitura_automatica") else "manual"
    session.add(guia)

    # Mantém a conta a pagar gerada junto em sincronia com a edição — sem
    # isso, a guia e o lançamento financeiro divergem depois de editar.
    if conta:
        conta.descricao = f"{label} — {dados.competencia}"
        conta.data_vencimento = dados.data_vencimento
        conta.data_competencia = date(ano, mes, 1)
        conta.tipo_documento = label
        conta.codigo_conta = codigo_conta
        conta.centro_custo = dados.centro_custo
        conta.valor_total = valor_total
        conta.numero_boleto = dados.linha_digitavel
        session.add(conta)

    session.commit()
    session.refresh(guia)
    return {**guia.model_dump(), "conta_id": conta.id if conta else None}


@router.delete("/folha-pagamento/guias/{guia_id}")
def excluir_guia_folha_encargo(
    guia_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    guia = session.get(GuiaFolhaEncargo, guia_id)
    if not guia or (guia.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Guia de FGTS/DCTF não encontrada")
    conta = _conta_da_guia(session, guia, fazenda_id)
    if conta and conta.valor_pago is not None:
        raise HTTPException(status_code=400, detail="Guia já paga não pode ser excluída aqui — exclua em Lançamentos > Excluir lançamento.")
    if conta:
        session.delete(conta)
    session.delete(guia)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Férias — cálculo (dias gozados + 1/3 constitucional + abono pecuniário
# opcional) e lançamento em Contas a Pagar. Sem envio ao eSocial (fora de
# escopo) — só o controle interno do que a fazenda já paga hoje.
# ---------------------------------------------------------------------------
# Status posto pelo SERVIDOR em férias/13º absorvidos por uma rescisão
# fechada (ver `_cancelar_ferias_decimo_da_rescisao`). Nunca aceito na
# entrada dos endpoints: `_validar_ferias`/`_validar_decimo_terceiro` só
# admitem "pendente" e "pago".
STATUS_CANCELADO_RESCISAO = "cancelado_rescisao"


class FeriasIn(BaseModel):
    pessoa_id: int
    periodo_aquisitivo_inicio: date
    periodo_aquisitivo_fim: date
    dias_direito: int = 30
    dias_gozados: int
    data_inicio_gozo: date
    data_fim_gozo: date
    abono_pecuniario_dias: int = 0
    data_pagamento: date | None = None
    status: str = "pendente"
    observacao: str | None = None
    centro_custo: str = "Pecuária Leiteira"
    # Conta bancária de onde sai o pagamento — OPCIONAL (ver _resolver_conta_corrente).
    conta_corrente_id: int | None = None


def _validar_ferias(dados: FeriasIn) -> None:
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.dias_gozados <= 0 or dados.dias_gozados > dados.dias_direito:
        raise HTTPException(status_code=400, detail="Dias gozados deve ser maior que zero e não pode exceder os dias de direito")
    if dados.data_fim_gozo < dados.data_inicio_gozo:
        raise HTTPException(status_code=400, detail="Data de fim do gozo não pode ser anterior à data de início")
    # Abono pecuniário (art. 143 CLT) — no máximo 1/3 dos dias de direito.
    if dados.abono_pecuniario_dias < 0 or dados.abono_pecuniario_dias > dados.dias_direito // 3:
        raise HTTPException(status_code=400, detail=f"Abono pecuniário não pode exceder {dados.dias_direito // 3} dias (1/3 dos dias de direito)")
    # A SOMA. As duas checagens acima eram feitas em separado e nunca somadas:
    # 30 dias gozados + 10 dias vendidos passava nas duas e pagava 40 dias de
    # férias sobre um direito de 30 (R$ 5.333,33 em vez de R$ 4.000 para um
    # salário de R$ 3.000). Os dias vendidos SAEM dos dias de direito — o
    # empregado goza 20 e vende 10, nunca goza 30 e vende mais 10 (art. 143
    # CLT: a conversão é "de 1/3 do período de férias a que tiver direito").
    if dados.dias_gozados + dados.abono_pecuniario_dias > dados.dias_direito:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Dias gozados ({dados.dias_gozados}) + abono pecuniário ({dados.abono_pecuniario_dias}) "
                f"somam {dados.dias_gozados + dados.abono_pecuniario_dias} dias e não podem exceder os "
                f"{dados.dias_direito} dias de direito — os dias vendidos saem do mesmo período (art. 143 CLT)."
            ),
        )


def _vencimento_ferias(data_inicio_gozo: date, data_pagamento: date | None) -> date:
    """
    Vencimento da conta a pagar das férias. O art. 145 da CLT manda pagar
    "até 2 (dois) dias antes do início do respectivo período" — a versão
    antiga usava `data_fim_gozo`, jogando o vencimento (e o alerta da Agenda)
    para ~30 dias DEPOIS do prazo legal: em férias de 01/07 a 30/07 o dinheiro
    aparecia como devido em 30/07, um mês depois de ter de sair.

    Não implementamos nenhuma dobra por atraso: a Súmula 450 do TST foi
    declarada inconstitucional pelo STF (ADPF 501) e cancelada pela Resolução
    TST nº 225/2025 — pagar fora do prazo do art. 145 hoje é só infração
    administrativa. (A dobra do art. 137, por gozo depois do período
    concessivo, é outra coisa e não é modelada aqui.)
    """
    return data_pagamento or (data_inicio_gozo - timedelta(days=2))


@router.get("/ferias")
def listar_ferias(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(FeriasFuncionario)
    if fazenda_id is not None:
        query = query.where(FeriasFuncionario.fazenda_id == fazenda_id)
    registros = session.exec(query.order_by(FeriasFuncionario.data_inicio_gozo.desc())).all()
    nomes_usuarios = mapa_usuarios(session, {r.usuario_id for r in registros})
    return [
        {**r.model_dump(), "pessoa_nome": pessoas.get(r.pessoa_id, "—"), "usuario_nome": nomes_usuarios.get(r.usuario_id)}
        for r in registros
    ]


@router.post("/ferias")
def criar_ferias(
    dados: FeriasIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_ferias(dados)
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)

    # Snapshot do salário no momento do lançamento — daqui pra frente é ELE
    # que manda no recálculo (ver o PUT), não o Pessoa.salario_base de hoje.
    salario_base = pessoa.salario_base
    calculo = calcular_ferias(
        salario_base, dados.dias_gozados, dados.abono_pecuniario_dias, percentual_terco_constitucional_ferias(),
    )
    numero_lancamento = _proximo_numero_lancamento(session, dados.data_fim_gozo.year)

    registro = FeriasFuncionario(
        pessoa_id=dados.pessoa_id,
        periodo_aquisitivo_inicio=dados.periodo_aquisitivo_inicio, periodo_aquisitivo_fim=dados.periodo_aquisitivo_fim,
        dias_direito=dados.dias_direito, dias_gozados=dados.dias_gozados,
        data_inicio_gozo=dados.data_inicio_gozo, data_fim_gozo=dados.data_fim_gozo,
        abono_pecuniario_dias=dados.abono_pecuniario_dias,
        salario_base=salario_base,
        valor_ferias=calculo["valor_ferias"], valor_terco_constitucional=calculo["valor_terco_constitucional"],
        valor_abono=calculo["valor_abono"],
        valor_total=calculo["valor_total"],
        data_pagamento=dados.data_pagamento, status=dados.status, observacao=dados.observacao,
        numero_lancamento_gerado=numero_lancamento, centro_custo=dados.centro_custo,
        conta_corrente_id=conta_corrente.id if conta_corrente else None, usuario_id=user.id,
        fazenda_id=fazenda_id,
    )
    session.add(registro)
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Férias — {pessoa.nome} ({dados.data_inicio_gozo.isoformat()} a {dados.data_fim_gozo.isoformat()})",
        # Vencimento e competência ancorados no INÍCIO do gozo (art. 145 CLT),
        # não no fim — ver `_vencimento_ferias`.
        data_vencimento=_vencimento_ferias(dados.data_inicio_gozo, dados.data_pagamento),
        data_competencia=dados.data_inicio_gozo,
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Férias",
        centro_custo=dados.centro_custo,
        valor_total=calculo["valor_total"],
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        data_pagamento=dados.data_pagamento if dados.status == "pago" else None,
        valor_pago=calculo["valor_total"] if dados.status == "pago" else None,
        conta_bancaria=rotulo_conta_corrente(conta_corrente) if conta_corrente else None,
        fazenda_id=fazenda_id,
    ))
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.put("/ferias/{registro_id}")
def atualizar_ferias(
    registro_id: int, dados: FeriasIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(FeriasFuncionario, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Registro de férias não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Férias já pagas não podem ser editadas.")
    if registro.status == STATUS_CANCELADO_RESCISAO:
        raise HTTPException(
            status_code=400,
            detail="Estas férias foram canceladas pela rescisão da pessoa — o valor já está nas verbas rescisórias.",
        )
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_ferias(dados)
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)

    # O RECÁLCULO USA O SNAPSHOT, não o salário de hoje. O botão "Marcar como
    # pago" da tela manda um PUT completo, e a versão antiga recalculava tudo
    # a partir de `pessoa.salario_base`: férias lançadas em janeiro por
    # R$ 2.666,67 (salário R$ 2.000) viravam R$ 4.000 em março se o salário
    # tivesse subido para R$ 3.000 no cadastro — e a conta a pagar era
    # sobrescrita sem aviso nenhum. O snapshot só é renovado quando o
    # lançamento passa a ser de OUTRA pessoa (aí o salário antigo não diz
    # respeito a ninguém) ou quando o registro é anterior à migração
    # e0b7c3a91d24 e não tem snapshot.
    salario_base = registro.salario_base
    if salario_base is None or dados.pessoa_id != registro.pessoa_id:
        salario_base = pessoa.salario_base
    calculo = calcular_ferias(
        salario_base, dados.dias_gozados, dados.abono_pecuniario_dias, percentual_terco_constitucional_ferias(),
    )
    registro.salario_base = salario_base
    registro.pessoa_id = dados.pessoa_id
    registro.periodo_aquisitivo_inicio = dados.periodo_aquisitivo_inicio
    registro.periodo_aquisitivo_fim = dados.periodo_aquisitivo_fim
    registro.dias_direito = dados.dias_direito
    registro.dias_gozados = dados.dias_gozados
    registro.data_inicio_gozo = dados.data_inicio_gozo
    registro.data_fim_gozo = dados.data_fim_gozo
    registro.abono_pecuniario_dias = dados.abono_pecuniario_dias
    registro.valor_ferias = calculo["valor_ferias"]
    registro.valor_terco_constitucional = calculo["valor_terco_constitucional"]
    registro.valor_abono = calculo["valor_abono"]
    registro.valor_total = calculo["valor_total"]
    registro.data_pagamento = dados.data_pagamento
    registro.status = dados.status
    registro.observacao = dados.observacao
    registro.centro_custo = dados.centro_custo
    registro.conta_corrente_id = conta_corrente.id if conta_corrente else None
    session.add(registro)

    if registro.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        if conta and conta.valor_pago is None:
            conta.descricao = f"Férias — {pessoa.nome} ({dados.data_inicio_gozo.isoformat()} a {dados.data_fim_gozo.isoformat()})"
            conta.fornecedor_cliente = pessoa.nome
            conta.data_vencimento = _vencimento_ferias(dados.data_inicio_gozo, dados.data_pagamento)
            conta.data_competencia = dados.data_inicio_gozo
            conta.centro_custo = dados.centro_custo
            conta.valor_total = calculo["valor_total"]
            conta.conta_bancaria = rotulo_conta_corrente(conta_corrente) if conta_corrente else None
            if dados.status == "pago":
                conta.data_pagamento = dados.data_pagamento
                conta.valor_pago = calculo["valor_total"]
            session.add(conta)

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.delete("/ferias/{registro_id}")
def excluir_ferias(
    registro_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(FeriasFuncionario, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Registro de férias não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Férias já pagas não podem ser excluídas aqui — exclua em Lançamentos > Excluir lançamento.")
    # O `status` do recibo de férias e a baixa da conta a pagar podem
    # discordar (recibo "pendente" + baixa feita direto no Financeiro):
    # apagar a conta nesse caso levava embora um pagamento real do extrato.
    # Mesma regra da folha e da guia de FGTS/DCTF — ver `_exigir_conta_nao_paga`.
    conta = _conta_do_numero(session, registro.numero_lancamento_gerado, fazenda_id)
    _exigir_conta_nao_paga(conta, "destas férias", "as férias")
    if conta is not None:
        session.delete(conta)
    session.delete(registro)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 13º salário — cálculo proporcional aos meses trabalhados no ano (única ou
# em duas parcelas) e lançamento em Contas a Pagar.
# ---------------------------------------------------------------------------
class DecimoTerceiroIn(BaseModel):
    pessoa_id: int
    ano: int
    parcela: str = "unica"  # unica | primeira | segunda
    meses_trabalhados: int
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    data_pagamento: date | None = None
    status: str = "pendente"
    observacao: str | None = None
    centro_custo: str = "Pecuária Leiteira"
    # Conta bancária de onde sai o pagamento — OPCIONAL (ver _resolver_conta_corrente).
    conta_corrente_id: int | None = None



def _validar_decimo_terceiro(dados: DecimoTerceiroIn) -> None:
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.parcela not in PARCELAS_DECIMO_TERCEIRO:
        raise HTTPException(status_code=400, detail="Parcela inválida")
    if dados.meses_trabalhados < 1 or dados.meses_trabalhados > 12:
        raise HTTPException(status_code=400, detail="Meses trabalhados deve estar entre 1 e 12")
    # INSS e IRRF incidem SÓ na 2ª parcela, sobre o 13º integral (Lei
    # 8.212/1991, art. 28, §7º; Dec. 3.048/1999, art. 214, §6º; Lei
    # 7.713/1988, art. 26). A 1ª é adiantamento pago CHEIO — descontar nela é
    # erro clássico de folha, e o formulário aceitava sem reclamar.
    if not retencoes_permitidas_decimo_terceiro(dados.parcela) and (dados.valor_inss or dados.valor_ir):
        raise HTTPException(
            status_code=400,
            detail=(
                "A 1ª parcela do 13º é adiantamento e é paga sem retenção: INSS e IRRF incidem só na "
                "2ª parcela, sobre o 13º integral (Lei 4.749/1965 e Lei 8.212/1991, art. 28, §7º)."
            ),
        )


ROTULO_PARCELA_DECIMO = {"unica": "parcela única", "primeira": "1ª parcela", "segunda": "2ª parcela"}


def _detalhe_decimo_terceiro_esgotado(parcela: str, ano: int, valor_integral: float, ja_lancado: float) -> str:
    """Mensagem do 400 quando não sobra nada a pagar nesta parcela — diz a
    conta inteira, para o usuário não ficar adivinhando por que o lançamento
    foi recusado."""
    if parcela == "primeira":
        limite = "50% do 13º (adiantamento, Lei 4.749/1965, art. 2º)"
    else:
        limite = "o 13º integral"
    return (
        f"Nada a lançar nesta {ROTULO_PARCELA_DECIMO.get(parcela, parcela)}: o 13º de {ano} é de "
        f"R$ {valor_integral:.2f} e já há R$ {ja_lancado:.2f} lançado(s) para esta pessoa no ano — "
        f"o limite desta parcela é {limite}. Exclua ou ajuste a parcela já lançada antes de lançar outra."
    )


def _decimo_terceiro_ja_lancado(
    session: Session, pessoa_id: int, ano: int, fazenda_id: int | None, ignorar_id: int | None = None
) -> float:
    """
    Soma do BRUTO das outras parcelas de 13º já lançadas para a mesma pessoa
    no mesmo ano — é o que impede a soma das parcelas de ultrapassar o 13º
    devido (ver `valor_parcela_decimo_terceiro`). Ignora o que foi cancelado
    por rescisão, que justamente deixou de ser devido por aqui.

    Filtro de fazenda incondicional (nunca `if fazenda_id is not None`): sem
    ele, a 1ª parcela lançada em outra fazenda entraria na conta desta.
    """
    query = select(DecimoTerceiro).where(
        DecimoTerceiro.pessoa_id == pessoa_id,
        DecimoTerceiro.ano == ano,
        DecimoTerceiro.fazenda_id == fazenda_id,
        DecimoTerceiro.status != STATUS_CANCELADO_RESCISAO,
    )
    return round(
        sum(r.valor_bruto for r in session.exec(query).all() if r.id != ignorar_id),
        2,
    )


@router.get("/decimo-terceiro")
def listar_decimo_terceiro(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(DecimoTerceiro)
    if fazenda_id is not None:
        query = query.where(DecimoTerceiro.fazenda_id == fazenda_id)
    registros = session.exec(query.order_by(DecimoTerceiro.ano.desc())).all()
    nomes_usuarios = mapa_usuarios(session, {r.usuario_id for r in registros})
    return [
        {**r.model_dump(), "pessoa_nome": pessoas.get(r.pessoa_id, "—"), "usuario_nome": nomes_usuarios.get(r.usuario_id)}
        for r in registros
    ]


@router.post("/decimo-terceiro")
def criar_decimo_terceiro(
    dados: DecimoTerceiroIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_decimo_terceiro(dados)
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)

    # Snapshot do salário (ver criar_ferias) + divisão em parcelas. ANTES:
    # `valor_bruto = calcular_decimo_terceiro(...)` — o 13º CHEIO — era
    # gravado igual para "unica", "primeira" e "segunda", e a parcela só
    # trocava o rótulo e o vencimento. Lançar 1ª + 2ª de um salário de
    # R$ 3.000 punha R$ 6.000 em Contas a Pagar.
    salario_base = pessoa.salario_base
    valor_integral = calcular_decimo_terceiro(salario_base, dados.meses_trabalhados)
    ja_lancado = _decimo_terceiro_ja_lancado(session, dados.pessoa_id, dados.ano, fazenda_id)
    valor_bruto = valor_parcela_decimo_terceiro(valor_integral, dados.parcela, ja_lancado)
    if valor_bruto <= 0:
        raise HTTPException(
            status_code=400,
            detail=_detalhe_decimo_terceiro_esgotado(dados.parcela, dados.ano, valor_integral, ja_lancado),
        )
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    valor_liquido = round(valor_bruto - valor_inss - valor_ir, 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")

    numero_lancamento = _proximo_numero_lancamento(session, dados.ano)
    vencimento_padrao = date(dados.ano, 12, 20) if dados.parcela in ("unica", "segunda") else date(dados.ano, 11, 30)

    registro = DecimoTerceiro(
        pessoa_id=dados.pessoa_id, ano=dados.ano, parcela=dados.parcela, meses_trabalhados=dados.meses_trabalhados,
        salario_base=salario_base, valor_integral=valor_integral,
        valor_bruto=valor_bruto, valor_inss=valor_inss, valor_ir=valor_ir, valor_liquido=valor_liquido,
        data_pagamento=dados.data_pagamento, status=dados.status, observacao=dados.observacao,
        numero_lancamento_gerado=numero_lancamento, centro_custo=dados.centro_custo,
        conta_corrente_id=conta_corrente.id if conta_corrente else None, usuario_id=user.id,
        fazenda_id=fazenda_id,
    )
    session.add(registro)
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"13º salário ({dados.parcela}) — {pessoa.nome} ({dados.ano})",
        data_vencimento=dados.data_pagamento or vencimento_padrao,
        data_competencia=date(dados.ano, 12, 1),
        fornecedor_cliente=pessoa.nome,
        tipo_documento="13º salário",
        centro_custo=dados.centro_custo,
        valor_total=valor_liquido,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        data_pagamento=dados.data_pagamento if dados.status == "pago" else None,
        valor_pago=valor_liquido if dados.status == "pago" else None,
        conta_bancaria=rotulo_conta_corrente(conta_corrente) if conta_corrente else None,
        fazenda_id=fazenda_id,
    ))
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.put("/decimo-terceiro/{registro_id}")
def atualizar_decimo_terceiro(
    registro_id: int, dados: DecimoTerceiroIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(DecimoTerceiro, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Registro de 13º salário não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="13º salário já pago não pode ser editado.")
    if registro.status == STATUS_CANCELADO_RESCISAO:
        raise HTTPException(
            status_code=400,
            detail="Este 13º foi cancelado pela rescisão da pessoa — o proporcional já está nas verbas rescisórias.",
        )
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_decimo_terceiro(dados)
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)

    # Recálculo pelo SNAPSHOT, não pelo salário de hoje (ver atualizar_ferias
    # — o botão "Marcar como pago" passa por aqui), e com a mesma divisão em
    # parcelas do POST, descontando o que as OUTRAS parcelas do ano já
    # levaram (`ignorar_id` tira este próprio registro da soma).
    salario_base = registro.salario_base
    if salario_base is None or dados.pessoa_id != registro.pessoa_id:
        salario_base = pessoa.salario_base
    valor_integral = calcular_decimo_terceiro(salario_base, dados.meses_trabalhados)
    ja_lancado = _decimo_terceiro_ja_lancado(
        session, dados.pessoa_id, dados.ano, fazenda_id, ignorar_id=registro.id,
    )
    valor_bruto = valor_parcela_decimo_terceiro(valor_integral, dados.parcela, ja_lancado)
    if valor_bruto <= 0:
        raise HTTPException(
            status_code=400,
            detail=_detalhe_decimo_terceiro_esgotado(dados.parcela, dados.ano, valor_integral, ja_lancado),
        )
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    valor_liquido = round(valor_bruto - valor_inss - valor_ir, 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")

    registro.pessoa_id = dados.pessoa_id
    registro.ano = dados.ano
    registro.parcela = dados.parcela
    registro.meses_trabalhados = dados.meses_trabalhados
    registro.salario_base = salario_base
    registro.valor_integral = valor_integral
    registro.valor_bruto = valor_bruto
    registro.valor_inss = valor_inss
    registro.valor_ir = valor_ir
    registro.valor_liquido = valor_liquido
    registro.data_pagamento = dados.data_pagamento
    registro.status = dados.status
    registro.observacao = dados.observacao
    registro.centro_custo = dados.centro_custo
    registro.conta_corrente_id = conta_corrente.id if conta_corrente else None
    session.add(registro)

    vencimento_padrao = date(dados.ano, 12, 20) if dados.parcela in ("unica", "segunda") else date(dados.ano, 11, 30)
    if registro.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        if conta and conta.valor_pago is None:
            conta.descricao = f"13º salário ({dados.parcela}) — {pessoa.nome} ({dados.ano})"
            conta.fornecedor_cliente = pessoa.nome
            conta.data_vencimento = dados.data_pagamento or vencimento_padrao
            conta.data_competencia = date(dados.ano, 12, 1)
            conta.centro_custo = dados.centro_custo
            conta.valor_total = valor_liquido
            conta.conta_bancaria = rotulo_conta_corrente(conta_corrente) if conta_corrente else None
            if dados.status == "pago":
                conta.data_pagamento = dados.data_pagamento
                conta.valor_pago = valor_liquido
            session.add(conta)

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.delete("/decimo-terceiro/{registro_id}")
def excluir_decimo_terceiro(
    registro_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(DecimoTerceiro, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Registro de 13º salário não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="13º salário já pago não pode ser excluído aqui — exclua em Lançamentos > Excluir lançamento.")
    # Mesmo furo das férias e da folha: o 13º pode estar "pendente" no RH com
    # a conta a pagar já baixada no Financeiro, e apagá-la sumiria com o
    # pagamento do extrato — ver `_exigir_conta_nao_paga`.
    conta = _conta_do_numero(session, registro.numero_lancamento_gerado, fazenda_id)
    _exigir_conta_nao_paga(conta, "deste 13º salário", "o 13º salário")
    if conta is not None:
        session.delete(conta)
    session.delete(registro)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Rescisão contratual (CLT) — cálculo das verbas rescisórias (saldo de
# salário, aviso prévio, férias vencidas/proporcionais, 13º proporcional,
# multa do FGTS estimada) para as 4 modalidades mais comuns. Sem eSocial/TRCT
# oficial (fora de escopo, mesma linha de férias/13º). Diferente do modelo
# antigo (que só gravava direto uma ContaGerencial, sem tabela própria), a
# rescisão agora É persistida e rastreada (`RescisaoFuncionario`), com um
# fluxo de duas etapas: nasce `simulacao` (`POST/PUT/DELETE /rescisoes`,
# livre para editar/recalcular, nada lançado em Financeiro) e só vira
# lançamento real ao FECHAR (`POST /rescisoes/{id}/fechar`, gera 1 conta a
# pagar — `forma_lancamento="unico"` — ou N, uma por verba —
# `forma_lancamento="detalhado"`). Não há endpoint de "reabrir" (v1): desfazer
# uma rescisão fechada é excluir o(s) lançamento(s) em Financeiro › Lançamentos,
# mesmo padrão já usado para Férias/13º pagos. Rescisões criadas pelo antigo
# `POST /cadastro/rescisao` (removido) continuam visíveis, só leitura, na
# listagem nova (ver `legado` em `GET /cadastro/rescisoes`).
# ---------------------------------------------------------------------------
LABELS_TIPO_RESCISAO = {
    "sem_justa_causa": "Dispensa sem justa causa",
    "pedido_demissao": "Pedido de demissão",
    "justa_causa": "Dispensa por justa causa",
    "acordo_mutuo": "Acordo mútuo (distrato)",
}


class RescisaoIn(BaseModel):
    pessoa_id: int
    tipo_rescisao: str  # sem_justa_causa | pedido_demissao | justa_causa | acordo_mutuo
    data_desligamento: date
    dias_ferias_vencidas: int = 0
    aviso_previo_trabalhado: bool = False
    data_pagamento: date | None = None
    status: str = "pendente"
    observacao: str | None = None
    centro_custo: str = "Pecuária Leiteira"


def _validar_rescisao(dados: RescisaoIn, pessoa: Pessoa) -> None:
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.tipo_rescisao not in LABELS_TIPO_RESCISAO:
        raise HTTPException(status_code=400, detail="Tipo de rescisão inválido")
    if dados.data_desligamento < pessoa.data_admissao:
        raise HTTPException(status_code=400, detail="Data de desligamento não pode ser anterior à data de admissão")
    limite_ferias_vencidas = dias_ferias_padrao()
    if dados.dias_ferias_vencidas < 0 or dados.dias_ferias_vencidas > limite_ferias_vencidas:
        raise HTTPException(status_code=400, detail=f"Dias de férias vencidas deve estar entre 0 e {limite_ferias_vencidas}")


# ── O SALDO DE VALE QUE A RESCISÃO PRECISA VER ──────────────────────────────
#
# O CASO QUE CUSTOU DINHEIRO (Jorbeson Nunes, pessoa 3, fazenda 1): a rescisão
# dele foi fechada com "Vale em aberto = R$ 0,00" e a fazenda pagou o líquido
# cheio, R$ 13.369,15. Ele continuou com SETE parcelas de vale abertas,
# somando R$ 6.485,00, em competências que nunca vão existir — não há mais
# folha para descontar. R$ 6.485,00 que a fazenda desembolsou e não tem mais
# como recuperar, sem que ninguém tenha sido avisado em momento nenhum: o
# campo `valor_vale_em_aberto` era digitado à mão, nascia em zero na tela e,
# mesmo preenchido, só reduzia o valor a pagar — não baixava parcela nenhuma.
#
# Esta função é a metade "mostrar": o número real, com as competências, para a
# tela pré-preencher o campo. A outra metade ("resolver o saldo no
# fechamento") está em `fechar_rescisao`.
def _saldo_vale_em_aberto(session: Session, pessoa_id: int, fazenda_id: int | None) -> dict:
    """
    Quanto de vale ainda é COBRÁVEL desta pessoa, e em que competências.

    Cobrável é a mesma definição que a folha usa para descontar, e por isso as
    três condições são as de `_valor_vale` + `_parcelas_pendentes`:
      - parcela NÃO `assumida_pela_fazenda` — o mês que o dono já mandou
        desconsiderar (ou o saldo de um vale cancelado) não é dívida de
        ninguém; já virou despesa da fazenda no Financeiro;
      - de vale que não está `cancelado` — mesma razão, para o vale inteiro;
      - em competência SEM folha paga — o que já caiu num holerite pago foi
        descontado de verdade e não se cobra de novo.

    MULTI-FAZENDA: o recorte é a `pessoa_id`, que quem chama SEMPRE resolveu
    com o filtro de fazenda dentro da consulta (`_pessoa_para_rescisao`,
    `_calcular_rescisao_pessoa`, `fechar_rescisao`) — uma rescisão de outra
    fazenda nunca chega aqui com o id de uma pessoa desta. Repetir
    `ValeParcela.fazenda_id == fazenda_id` seria pior, não melhor: a parcela
    órfã (fazenda_id nulo do backfill) da própria pessoa sairia da conta, e o
    saldo ficaria MENOR que o real — justamente o erro que custou os
    R$ 6.485,00. É o mesmo raciocínio, e pelo mesmo motivo, de `_valor_vale` e
    de `_parcela_da_folha` (rh_folha_pagar.py). `fazenda_id` continua sendo
    usado para o que ele de fato recorta: a folha paga.
    """
    parcelas = session.exec(
        select(ValeParcela).where(
            ValeParcela.pessoa_id == pessoa_id,
            ValeParcela.assumida_pela_fazenda == False,  # noqa: E712
        )
    ).all()
    if not parcelas:
        return {"total": 0.0, "competencias": [], "parcela_ids": []}

    vales = {
        v.id: v for v in session.exec(
            select(ValeFuncionario).where(ValeFuncionario.id.in_({p.vale_id for p in parcelas}))
        ).all()
    }
    cobraveis = [
        p for p in parcelas
        if (vales.get(p.vale_id) is not None and vales[p.vale_id].status != "cancelado")
        and not _vale_competencia_paga(session, pessoa_id, [p.competencia], fazenda_id)
    ]

    por_competencia: dict[str, float] = {}
    for p in cobraveis:
        por_competencia[p.competencia] = round(por_competencia.get(p.competencia, 0.0) + p.valor, 2)
    return {
        "total": round(sum(p.valor for p in cobraveis), 2),
        "competencias": [
            {"competencia": c, "valor": por_competencia[c]} for c in sorted(por_competencia)
        ],
        "parcela_ids": sorted(p.id for p in cobraveis if p.id is not None),
    }


def _calcular_rescisao_pessoa(dados: RescisaoIn, session: Session, fazenda_id: int | None = None) -> tuple[Pessoa, dict]:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    if not pessoa.data_admissao:
        raise HTTPException(status_code=400, detail="Pessoa não tem data de admissão cadastrada")
    _validar_rescisao(dados, pessoa)

    calculo = calcular_rescisao(
        pessoa.salario_base,
        pessoa.data_admissao,
        dados.data_desligamento,
        dados.tipo_rescisao,
        dados.dias_ferias_vencidas,
        dados.aviso_previo_trabalhado,
        percentual_terco_constitucional_ferias(),
        percentual_estimado_fgts_mensal(),
    )
    return pessoa, calculo


@router.post("/rescisao/calcular")
def simular_rescisao(
    dados: RescisaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Só calcula e devolve o detalhamento das verbas — não gera lançamento
    financeiro nem grava nada (usado pela tela para o usuário conferir os
    números antes de lançar a simulação persistida em
    `POST /cadastro/rescisoes`).

    `vale_em_aberto` vem junto porque é aqui que a tela monta a rescisão: sem
    o número real na mão do dono, o campo "Vale em aberto" nascia em zero e
    era assim que ficava — foi o que deixou R$ 6.485,00 de vale de pé numa
    rescisão fechada (ver `_saldo_vale_em_aberto`). A tela pré-preenche o
    campo com ele e mostra as competências; o valor continua EDITÁVEL, porque
    o dono pode ter acertado parte por fora."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa, calculo = _calcular_rescisao_pessoa(dados, session, fazenda_id)
    return {
        **calculo, "pessoa_id": pessoa.id, "pessoa_nome": pessoa.nome,
        "vale_em_aberto": _saldo_vale_em_aberto(session, pessoa.id, fazenda_id),
    }


# ---------------------------------------------------------------------------
# Rescisão — persistência (simulação editável → fechamento com lançamento).
# ---------------------------------------------------------------------------
class RescisaoSimulacaoIn(BaseModel):
    pessoa_id: int
    tipo_rescisao: str
    data_desligamento: date
    dias_ferias_vencidas: int = 0
    aviso_previo_trabalhado: bool = False
    observacao: str | None = None
    centro_custo: str = "Pecuária Leiteira"
    # Override manual de qualquer uma das 6 verbas calculadas — quando None,
    # usa o valor de `calcular_rescisao` (ver _aplicar_calculo_rescisao).
    valor_saldo_salario: float | None = None
    valor_aviso_previo: float | None = None
    valor_ferias_vencidas: float | None = None
    valor_ferias_proporcionais: float | None = None
    valor_decimo_terceiro_proporcional: float | None = None
    valor_multa_fgts: float | None = None
    # Deduções — sempre informadas pelo usuário, nunca calculadas sozinhas.
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    valor_vale_em_aberto: float = 0.0


class RescisaoFecharIn(BaseModel):
    forma_lancamento: str = "unico"  # unico | detalhado
    status_pagamento: str = "pendente"  # pendente | pago
    data_pagamento: date | None = None
    inativar_pessoa: bool = False
    centro_custo: str | None = None
    # Conta bancária de onde sai o pagamento — OPCIONAL (ver
    # _resolver_conta_corrente); aplicada a TODAS as ContaGerencial geradas,
    # mesmo no fechamento "detalhado" (uma por verba).
    conta_corrente_id: int | None = None


def _validar_simulacao_rescisao(dados: RescisaoSimulacaoIn, pessoa: Pessoa) -> None:
    if dados.tipo_rescisao not in LABELS_TIPO_RESCISAO:
        raise HTTPException(status_code=400, detail="Tipo de rescisão inválido")
    if dados.data_desligamento < pessoa.data_admissao:
        raise HTTPException(status_code=400, detail="Data de desligamento não pode ser anterior à data de admissão")
    limite_ferias_vencidas = dias_ferias_padrao()
    if dados.dias_ferias_vencidas < 0 or dados.dias_ferias_vencidas > limite_ferias_vencidas:
        raise HTTPException(status_code=400, detail=f"Dias de férias vencidas deve estar entre 0 e {limite_ferias_vencidas}")
    overrides = (
        ("saldo de salário", dados.valor_saldo_salario),
        ("aviso prévio", dados.valor_aviso_previo),
        ("férias vencidas", dados.valor_ferias_vencidas),
        ("férias proporcionais", dados.valor_ferias_proporcionais),
        ("13º proporcional", dados.valor_decimo_terceiro_proporcional),
        ("multa do FGTS", dados.valor_multa_fgts),
    )
    for campo, valor in overrides:
        if valor is not None and valor < 0:
            raise HTTPException(status_code=400, detail=f"Valor de {campo} não pode ser negativo")
    deducoes = (
        ("INSS", dados.valor_inss),
        ("IR", dados.valor_ir),
        ("vale em aberto", dados.valor_vale_em_aberto),
    )
    for campo, valor in deducoes:
        if valor < 0:
            raise HTTPException(status_code=400, detail=f"Valor de {campo} não pode ser negativo")


def _pessoa_para_rescisao(dados: RescisaoSimulacaoIn, session: Session, fazenda_id: int | None) -> Pessoa:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    if not pessoa.data_admissao:
        raise HTTPException(status_code=400, detail="Pessoa não tem data de admissão cadastrada")
    _validar_simulacao_rescisao(dados, pessoa)
    return pessoa


def _aplicar_calculo_rescisao(dados: RescisaoSimulacaoIn, pessoa: Pessoa, registro: RescisaoFuncionario) -> None:
    """Roda o cálculo puro `calcular_rescisao` (inalterado) e grava o
    resultado no `registro`: cada uma das 6 verbas usa o valor informado por
    `dados` quando presente (override manual), senão o valor calculado.
    `valor_bruto`/`valor_total` são SEMPRE recomputados aqui a partir das 6
    verbas já resolvidas e das deduções — nunca aceitos prontos do cliente."""
    calculo = calcular_rescisao(
        pessoa.salario_base,
        pessoa.data_admissao,
        dados.data_desligamento,
        dados.tipo_rescisao,
        dados.dias_ferias_vencidas,
        dados.aviso_previo_trabalhado,
        percentual_terco_constitucional_ferias(),
        percentual_estimado_fgts_mensal(),
    )

    def _resolver(override: float | None, calculado: float) -> float:
        return round(override, 2) if override is not None else round(calculado, 2)

    registro.pessoa_id = dados.pessoa_id
    registro.tipo_rescisao = dados.tipo_rescisao
    registro.data_desligamento = dados.data_desligamento
    registro.dias_ferias_vencidas = dados.dias_ferias_vencidas
    registro.aviso_previo_trabalhado = dados.aviso_previo_trabalhado
    registro.observacao = dados.observacao
    registro.centro_custo = dados.centro_custo
    registro.salario_base = pessoa.salario_base
    registro.data_admissao = pessoa.data_admissao

    registro.valor_saldo_salario = _resolver(dados.valor_saldo_salario, calculo["saldo_salario"]["valor"])
    registro.valor_aviso_previo = _resolver(dados.valor_aviso_previo, calculo["aviso_previo"]["valor"])
    registro.valor_ferias_vencidas = _resolver(dados.valor_ferias_vencidas, calculo["ferias_vencidas"]["valor_total"])
    registro.valor_ferias_proporcionais = _resolver(
        dados.valor_ferias_proporcionais, calculo["ferias_proporcionais"]["valor_total"]
    )
    registro.valor_decimo_terceiro_proporcional = _resolver(
        dados.valor_decimo_terceiro_proporcional, calculo["decimo_terceiro_proporcional"]["valor"]
    )
    registro.valor_multa_fgts = _resolver(dados.valor_multa_fgts, calculo["fgts"]["multa"])

    registro.valor_inss = round(dados.valor_inss, 2)
    registro.valor_ir = round(dados.valor_ir, 2)
    registro.valor_vale_em_aberto = round(dados.valor_vale_em_aberto, 2)

    registro.dias_saldo_salario = calculo["saldo_salario"]["dias_trabalhados_mes"]
    registro.dias_aviso_previo = calculo["aviso_previo"]["dias"]
    registro.dias_aviso_previo_indenizados = calculo["aviso_previo"]["dias_indenizados"]
    registro.meses_ferias_proporcionais = calculo["ferias_proporcionais"]["meses"]
    registro.meses_decimo_terceiro = calculo["decimo_terceiro_proporcional"]["meses"]
    registro.percentual_multa_fgts = calculo["fgts"]["percentual_multa"]

    registro.valor_bruto = round(
        registro.valor_saldo_salario
        + registro.valor_aviso_previo
        + registro.valor_ferias_vencidas
        + registro.valor_ferias_proporcionais
        + registro.valor_decimo_terceiro_proporcional
        + registro.valor_multa_fgts,
        2,
    )
    registro.valor_total = round(
        registro.valor_bruto - registro.valor_inss - registro.valor_ir - registro.valor_vale_em_aberto, 2
    )


def _linhas_verbas_rescisao(registro: RescisaoFuncionario) -> dict[str, tuple[str, float]]:
    """Label + valor de cada uma das 6 verbas, chaveado pelo nome interno —
    fonte única usada tanto por `_detalhe_rescisao` (ordem de exibição) quanto
    pela cascata de dedução do fechamento detalhado (ordem fixa definida no
    plano: saldo → 13º → férias proporcionais → férias vencidas → aviso
    prévio → multa do FGTS)."""
    return {
        "saldo_salario": (f"Saldo de salário ({registro.dias_saldo_salario} dia(s))", registro.valor_saldo_salario),
        "aviso_previo": (
            f"Aviso prévio indenizado ({registro.dias_aviso_previo_indenizados} dia(s))", registro.valor_aviso_previo,
        ),
        "ferias_vencidas": ("Férias vencidas + 1/3", registro.valor_ferias_vencidas),
        "ferias_proporcionais": (
            f"Férias proporcionais + 1/3 ({registro.meses_ferias_proporcionais} mês(es))",
            registro.valor_ferias_proporcionais,
        ),
        "decimo_terceiro_proporcional": (
            f"13º proporcional ({registro.meses_decimo_terceiro} mês(es))", registro.valor_decimo_terceiro_proporcional,
        ),
        "multa_fgts": (
            f"Multa do FGTS estimada ({registro.percentual_multa_fgts:.0%})", registro.valor_multa_fgts,
        ),
    }


# Ordem de EXIBIÇÃO em `_detalhe_rescisao` (mesma ordem em que `calcular_rescisao`
# devolve as verbas) — diferente da ordem de CASCATA abaixo (decisão do plano).
_ORDEM_EXIBICAO_VERBAS_RESCISAO = [
    "saldo_salario", "aviso_previo", "ferias_vencidas", "ferias_proporcionais", "decimo_terceiro_proporcional", "multa_fgts",
]
# Ordem em que INSS+IR+vale em aberto abatem as verbas no fechamento
# "detalhado" (decisão já aprovada do plano — não alterar).
_ORDEM_CASCATA_DEDUCAO_RESCISAO = [
    "saldo_salario", "decimo_terceiro_proporcional", "ferias_proporcionais", "ferias_vencidas", "aviso_previo", "multa_fgts",
]


def _detalhe_rescisao(registro: RescisaoFuncionario) -> list[dict]:
    """Discriminação completa da rescisão — mesma forma de `_detalhe_folha`
    ({"label", "valor"}). Saldo de salário sempre aparece (mesmo que zero);
    as demais verbas e as deduções só aparecem quando != 0. A última linha é
    SEMPRE `{"label": "Valor líquido", ...}` — string usada pelo frontend
    para negrito na última linha."""
    linhas = _linhas_verbas_rescisao(registro)
    label_saldo, valor_saldo = linhas["saldo_salario"]
    detalhe = [{"label": label_saldo, "valor": valor_saldo}]
    for chave in _ORDEM_EXIBICAO_VERBAS_RESCISAO[1:]:
        label, valor = linhas[chave]
        if valor:
            detalhe.append({"label": label, "valor": valor})
    if registro.valor_inss:
        detalhe.append({"label": "INSS", "valor": -registro.valor_inss})
    if registro.valor_ir:
        detalhe.append({"label": "IRRF", "valor": -registro.valor_ir})
    if registro.valor_vale_em_aberto:
        detalhe.append({"label": "Vale em aberto", "valor": -registro.valor_vale_em_aberto})
    detalhe.append({"label": "Valor líquido", "valor": registro.valor_total})
    return detalhe


def _parcelas_detalhado_rescisao(registro: RescisaoFuncionario) -> list[tuple[str, float, bool]]:
    """Cascata de dedução (INSS+IR+vale em aberto) sobre as verbas positivas,
    na ordem fixa `_ORDEM_CASCATA_DEDUCAO_RESCISAO`, cada uma flor no 0 e o
    restante da dedução carregado para a próxima. Devolve só as verbas que
    sobraram > 0 — (label, valor_final, foi_reduzida)."""
    linhas = _linhas_verbas_rescisao(registro)
    restante = round(registro.valor_inss + registro.valor_ir + registro.valor_vale_em_aberto, 2)
    parcelas: list[tuple[str, float, bool]] = []
    for chave in _ORDEM_CASCATA_DEDUCAO_RESCISAO:
        label, valor = linhas[chave]
        if valor <= 0:
            continue
        deduzido = min(valor, restante)
        valor_final = round(valor - deduzido, 2)
        restante = round(restante - deduzido, 2)
        if valor_final <= 0:
            continue
        parcelas.append((label, valor_final, deduzido > 0))
    return parcelas


@router.get("/rescisoes")
def listar_rescisoes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}

    query = select(RescisaoFuncionario)
    if fazenda_id is not None:
        query = query.where(RescisaoFuncionario.fazenda_id == fazenda_id)
    registros = session.exec(query).all()
    nomes_usuarios = mapa_usuarios(session, {r.usuario_id for r in registros})
    numeros_cobertos = {r.numero_lancamento_gerado for r in registros if r.numero_lancamento_gerado}

    itens = [
        {
            **r.model_dump(),
            "pessoa_nome": pessoas.get(r.pessoa_id, "—"),
            "usuario_nome": nomes_usuarios.get(r.usuario_id),
            "detalhe": _detalhe_rescisao(r),
            # Só nas SIMULAÇÕES: a tela abre um rascunho da listagem para
            # editar/fechar, e é aí que o saldo de vale precisa estar à vista.
            # Numa rescisão já fechada o saldo foi baixado no fechamento (e o
            # que sobrasse teria impedido o fechamento), então calcular de novo
            # só gastaria consulta para dizer zero.
            "vale_em_aberto": (
                _saldo_vale_em_aberto(session, r.pessoa_id, fazenda_id) if r.status == "simulacao" else None
            ),
            "legado": False,
        }
        for r in registros
    ]

    # Rescisões lançadas pelo antigo POST /cadastro/rescisao (removido nesta
    # migração) — sem RescisaoFuncionario correspondente. Continuam visíveis,
    # só leitura, para o histórico não sumir da listagem nova.
    query_legado = select(ContaGerencial).where(ContaGerencial.tipo_documento == "Rescisão")
    if fazenda_id is not None:
        query_legado = query_legado.where(ContaGerencial.fazenda_id == fazenda_id)
    for c in session.exec(query_legado).all():
        if c.numero_lancamento and c.numero_lancamento in numeros_cobertos:
            continue
        itens.append({
            "id": -(1_000_000 + (c.id or 0)),  # sintético — nunca colide com um id real de RescisaoFuncionario
            "legado_conta_id": c.id,
            "pessoa_id": None,
            "pessoa_nome": c.fornecedor_cliente or "—",
            "usuario_nome": None,
            "tipo_rescisao": None,
            "data_desligamento": c.data_competencia,
            "status": "fechada",
            "forma_lancamento": "unico",
            "valor_bruto": c.valor_total,
            "valor_total": c.valor_total,
            "numero_lancamento_gerado": c.numero_lancamento,
            "data_pagamento": c.data_pagamento,
            "data_fechamento": None,
            "centro_custo": c.centro_custo,
            "observacao": None,
            "descricao": c.descricao,
            "inativou_pessoa": False,
            "criado_em": None,
            "detalhe": [],
            "legado": True,
        })

    itens.sort(key=lambda i: (i.get("data_desligamento") or date.min, i.get("criado_em") or datetime.min), reverse=True)
    return itens


@router.post("/rescisoes")
def criar_rescisao_simulacao(
    dados: RescisaoSimulacaoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = _pessoa_para_rescisao(dados, session, fazenda_id)

    registro = RescisaoFuncionario(
        pessoa_id=dados.pessoa_id,
        tipo_rescisao=dados.tipo_rescisao,
        data_desligamento=dados.data_desligamento,
        salario_base=pessoa.salario_base,
        data_admissao=pessoa.data_admissao,
        status="simulacao",
        forma_lancamento=None,
        usuario_id=user.id,
        fazenda_id=fazenda_id,
    )
    _aplicar_calculo_rescisao(dados, pessoa, registro)
    if registro.valor_total < 0:
        raise HTTPException(status_code=400, detail="O valor líquido da rescisão não pode ser negativo")

    session.add(registro)
    session.commit()
    session.refresh(registro)
    return {
        **registro.model_dump(), "pessoa_nome": pessoa.nome, "detalhe": _detalhe_rescisao(registro),
        # O saldo real de vale acompanha o rascunho: é ele que o fechamento vai
        # exigir que esteja endereçado, então a tela precisa mostrá-lo desde já.
        "vale_em_aberto": _saldo_vale_em_aberto(session, registro.pessoa_id, fazenda_id),
    }


@router.put("/rescisoes/{registro_id}")
def atualizar_rescisao_simulacao(
    registro_id: int, dados: RescisaoSimulacaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(RescisaoFuncionario, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")
    if registro.status != "simulacao":
        raise HTTPException(status_code=400, detail="Esta rescisão já está fechada.")
    pessoa = _pessoa_para_rescisao(dados, session, fazenda_id)

    _aplicar_calculo_rescisao(dados, pessoa, registro)
    if registro.valor_total < 0:
        raise HTTPException(status_code=400, detail="O valor líquido da rescisão não pode ser negativo")

    session.add(registro)
    session.commit()
    session.refresh(registro)
    return {
        **registro.model_dump(), "pessoa_nome": pessoa.nome, "detalhe": _detalhe_rescisao(registro),
        "vale_em_aberto": _saldo_vale_em_aberto(session, registro.pessoa_id, fazenda_id),
    }


@router.delete("/rescisoes/{registro_id}")
def excluir_rescisao_simulacao(
    registro_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(RescisaoFuncionario, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")
    if registro.status != "simulacao":
        raise HTTPException(status_code=400, detail="Esta rescisão já está fechada.")
    # Simulação nunca gera ContaGerencial — só apagar o registro mesmo.
    session.delete(registro)
    session.commit()
    return {"ok": True}


def _cancelar_conta_pendente(session: Session, numero_lancamento: str | None, fazenda_id: int | None) -> None:
    """Remove a conta a pagar de um lançamento cancelado, desde que ainda não
    tenha sido paga — mesma regra e mesmo cuidado de `excluir_ferias`/
    `excluir_decimo_terceiro`. Conta já paga fica onde está: aí o dinheiro
    saiu e apagar seria reescrever histórico financeiro."""
    conta = _conta_do_numero(session, numero_lancamento, fazenda_id)
    if conta and conta.valor_pago is None:
        session.delete(conta)


def _cancelar_ferias_decimo_da_rescisao(
    session: Session, rescisao: RescisaoFuncionario, fazenda_id: int | None
) -> list[dict]:
    """
    Cancela os lançamentos de férias/13º PENDENTES que a rescisão absorve —
    era um pagamento em duplicidade real: o 13º de 2026 lançado em novembro
    (conta a pagar de R$ 3.000 vencendo 20/12, ainda pendente) continuava lá
    depois de a rescisão de 10/12 ser fechada JÁ INCLUINDO o 13º proporcional
    de 12 meses. Duas contas a pagar do mesmo 13º, e nada as relacionava.

    O que entra no cancelamento, e só isto:
    - 13º do ANO do desligamento — é exatamente o que a verba
      `decimo_terceiro_proporcional` da rescisão paga. 13º de anos anteriores
      ainda em aberto é dívida velha, que a rescisão não cobre e não some.
    - férias cujo gozo AINDA NÃO TERMINOU na data do desligamento
      (`data_fim_gozo > data_desligamento`) — férias que a pessoa não vai
      mais gozar. As férias vencidas/proporcionais da rescisão são verbas
      próprias (`dias_ferias_vencidas` + a proporcional calculada). Um
      período já gozado e não pago continua sendo dívida real e fica intacto.

    NADA É APAGADO: o registro fica no banco com `status`
    "cancelado_rescisao" e `rescisao_id` apontando para a rescisão que o
    cancelou — é o que torna o cancelamento explícito na tela, auditável e
    reversível (basta devolver o status e relançar a conta). Só a CONTA A
    PAGAR pendente some, porque é ela que geraria o pagamento em dobro; conta
    já paga nunca é tocada, e por isso um lançamento já pago também não é
    cancelado.
    """
    cancelados: list[dict] = []

    query_decimo = select(DecimoTerceiro).where(
        DecimoTerceiro.pessoa_id == rescisao.pessoa_id,
        DecimoTerceiro.fazenda_id == fazenda_id,
        DecimoTerceiro.ano == rescisao.data_desligamento.year,
        DecimoTerceiro.status == "pendente",
    )
    for d in session.exec(query_decimo).all():
        _cancelar_conta_pendente(session, d.numero_lancamento_gerado, fazenda_id)
        d.status = STATUS_CANCELADO_RESCISAO
        d.rescisao_id = rescisao.id
        session.add(d)
        cancelados.append({
            "tipo": "decimo_terceiro", "id": d.id, "valor": d.valor_liquido,
            "descricao": f"13º salário {d.ano} ({ROTULO_PARCELA_DECIMO.get(d.parcela, d.parcela)})",
        })

    query_ferias = select(FeriasFuncionario).where(
        FeriasFuncionario.pessoa_id == rescisao.pessoa_id,
        FeriasFuncionario.fazenda_id == fazenda_id,
        FeriasFuncionario.status == "pendente",
        FeriasFuncionario.data_fim_gozo > rescisao.data_desligamento,
    )
    for f in session.exec(query_ferias).all():
        _cancelar_conta_pendente(session, f.numero_lancamento_gerado, fazenda_id)
        f.status = STATUS_CANCELADO_RESCISAO
        f.rescisao_id = rescisao.id
        session.add(f)
        cancelados.append({
            "tipo": "ferias", "id": f.id, "valor": f.valor_total,
            "descricao": (
                f"Férias {f.data_inicio_gozo.strftime('%d/%m/%Y')} a {f.data_fim_gozo.strftime('%d/%m/%Y')}"
            ),
        })

    return cancelados


@router.post("/rescisoes/{registro_id}/fechar")
def fechar_rescisao(
    registro_id: int, dados: RescisaoFecharIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    registro = session.get(RescisaoFuncionario, registro_id)
    if not registro or (registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")
    if registro.status != "simulacao":
        raise HTTPException(status_code=400, detail="Esta rescisão já está fechada.")
    if dados.forma_lancamento not in ("unico", "detalhado"):
        raise HTTPException(status_code=400, detail="Forma de lançamento inválida")
    if dados.status_pagamento not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status de pagamento inválido")
    if registro.valor_total <= 0:
        raise HTTPException(status_code=400, detail="O valor líquido da rescisão deve ser positivo para fechar")

    # Defesa em profundidade — mesma checagem de fazenda feita na criação,
    # mesmo que a Pessoa não devesse ter mudado de fazenda nesse meio tempo.
    pessoa = session.get(Pessoa, registro.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    # ── O VALE TEM DE ESTAR ENDEREÇADO ANTES DE FECHAR ─────────────────────
    #
    # O caso: a rescisão do Jorbeson Nunes (pessoa 3, fazenda 1) foi fechada
    # com "Vale em aberto = R$ 0,00", a fazenda pagou o líquido cheio
    # (R$ 13.369,15), e ele ficou com 7 parcelas somando R$ 6.485,00 em
    # competências que nunca vão existir — não há mais folha para descontar.
    # Ninguém foi avisado. Este bloco é a trava que faltava, e ela é ANTES do
    # fechamento porque rescisão fechada NÃO REABRE (é regra desta casa, e não
    # muda aqui): depois não haveria conserto pela tela.
    #
    # POR QUE TRAVAR EM VEZ DE CANCELAR O VALE SOZINHO. Decidir por conta
    # própria o destino de R$ 6.485,00 de outra pessoa não é papel do sistema
    # — "a fazenda assume" é uma decisão de dono, com efeito no Financeiro
    # (o valor vira despesa dela) e sem volta automática em todos os casos.
    # Avisar e travar é. A saída está escrita na própria mensagem: descontar o
    # saldo na rescisão, ou resolvê-lo antes nas Ações do vale (abater,
    # desconsiderar o mês, cancelar o vale).
    saldo_vale = _saldo_vale_em_aberto(session, registro.pessoa_id, fazenda_id)
    vale_descontado = round(registro.valor_vale_em_aberto, 2)
    competencias_saldo = ", ".join(
        f"{c['competencia']} (R$ {c['valor']:.2f})" for c in saldo_vale["competencias"]
    )
    if vale_descontado > round(saldo_vale["total"] + 0.005, 2):
        raise HTTPException(
            status_code=400,
            detail=(
                f"O desconto de vale desta rescisão (R$ {vale_descontado:.2f}) é maior que o saldo de "
                f"vale ainda cobrável de {pessoa.nome} (R$ {saldo_vale['total']:.2f}). Descontar mais do "
                "que se tem a receber cobraria duas vezes o mesmo dinheiro — corrija o campo "
                "\"Vale em aberto\" na simulação."
            ),
        )
    sobra_vale = round(saldo_vale["total"] - vale_descontado, 2)
    if sobra_vale > 0.005:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{pessoa.nome} ainda tem R$ {sobra_vale:.2f} de vale em aberto que esta rescisão não "
                f"endereça (saldo cobrável de R$ {saldo_vale['total']:.2f} em {competencias_saldo}; "
                f"descontado na rescisão: R$ {vale_descontado:.2f}). Depois de fechada a rescisão não há "
                "mais folha para descontar e ela não reabre — então decida agora: aumente o campo "
                "\"Vale em aberto\" para descontar o saldo do que ele tem a receber, ou resolva o vale "
                "antes em Folha de Pagamento > vale > Ações (abater, desconsiderar o mês ou cancelar o "
                "vale, que faz a fazenda assumir o valor)."
            ),
        )
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)
    conta_bancaria = rotulo_conta_corrente(conta_corrente) if conta_corrente else None

    centro_custo = dados.centro_custo or registro.centro_custo
    numero_lancamento = _proximo_numero_lancamento(session, registro.data_desligamento.year)
    data_vencimento = dados.data_pagamento or registro.data_desligamento
    data_pagamento_conta = dados.data_pagamento if dados.status_pagamento == "pago" else None

    contas: list[ContaGerencial] = []
    if dados.forma_lancamento == "unico":
        contas.append(ContaGerencial(
            numero_lancamento=numero_lancamento,
            descricao=(
                f"Rescisão — {LABELS_TIPO_RESCISAO[registro.tipo_rescisao]} — "
                f"{pessoa.nome} ({registro.data_desligamento.isoformat()})"
            ),
            data_vencimento=data_vencimento,
            data_competencia=registro.data_desligamento,
            fornecedor_cliente=pessoa.nome,
            tipo_documento="Rescisão",
            centro_custo=centro_custo,
            valor_total=registro.valor_total,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            data_pagamento=data_pagamento_conta,
            valor_pago=registro.valor_total if dados.status_pagamento == "pago" else None,
            conta_bancaria=conta_bancaria,
            fazenda_id=fazenda_id,
        ))
    else:
        parcelas = _parcelas_detalhado_rescisao(registro)
        n = len(parcelas)
        for i, (label, valor, reduzido) in enumerate(parcelas, start=1):
            descricao_label = f"{label} (líquido de descontos)" if reduzido else label
            contas.append(ContaGerencial(
                numero_lancamento=numero_lancamento,
                descricao=(
                    f"Rescisão — {descricao_label} — {pessoa.nome} ({registro.data_desligamento.isoformat()})"
                ),
                data_vencimento=data_vencimento,
                data_competencia=registro.data_desligamento,
                fornecedor_cliente=pessoa.nome,
                tipo_documento="Rescisão",
                centro_custo=centro_custo,
                valor_total=valor,
                parcela_num=i, parcela_total=n,
                tipo="despesa", origem="auto",
                data_pagamento=data_pagamento_conta,
                valor_pago=valor if dados.status_pagamento == "pago" else None,
                conta_bancaria=conta_bancaria,
                fazenda_id=fazenda_id,
            ))
        # Garantia da cascata da decisão do plano: a soma das parcelas geradas
        # tem que bater exatamente com o líquido do registro.
        assert round(sum(c.valor_total for c in contas), 2) == registro.valor_total

    for conta in contas:
        session.add(conta)

    registro.status = "fechada"
    registro.forma_lancamento = dados.forma_lancamento
    registro.numero_lancamento_gerado = numero_lancamento
    registro.data_fechamento = date.today()
    registro.data_pagamento = dados.data_pagamento
    registro.centro_custo = centro_custo
    registro.conta_corrente_id = conta_corrente.id if conta_corrente else None
    if dados.inativar_pessoa:
        pessoa.ativo = False
        session.add(pessoa)
        registro.inativou_pessoa = True
    session.add(registro)
    session.flush()  # o registro precisa ter id antes de ser referenciado abaixo

    # O fechamento é o momento em que "esta pessoa saiu" passa a existir no
    # sistema — é aqui que os pagamentos futuros que a rescisão absorve são
    # encerrados, e não numa varredura dentro de um GET (ver
    # `_remover_folha_pos_rescisao`).
    cancelados = _cancelar_ferias_decimo_da_rescisao(session, registro, fazenda_id)

    # O que foi descontado em `valor_vale_em_aberto` BAIXA as parcelas
    # correspondentes. Sem isto o mesmo dinheiro é cobrado duas vezes: uma no
    # líquido reduzido da rescisão, outra nas parcelas que continuariam de pé
    # no relatório de vales. Import aqui dentro, e não no topo, porque
    # `rh_vale_acoes` importa deste módulo — no topo seria ciclo; o abatimento
    # é reusado de lá justamente para não existir um terceiro caminho.
    from .rh_vale_acoes import abater_saldo_na_rescisao
    vales_baixados = abater_saldo_na_rescisao(session, pessoa, vale_descontado, fazenda_id)

    session.commit()
    _remover_folha_pos_rescisao(session, fazenda_id)
    session.refresh(registro)
    return {
        **registro.model_dump(),
        "pessoa_nome": pessoa.nome,
        "detalhe": _detalhe_rescisao(registro),
        # Explícito na resposta para a tela poder dizer o que foi encerrado
        # junto, em vez de o lançamento sumir sem explicação.
        "lancamentos_cancelados": cancelados,
        # Idem para o vale: quanto foi baixado de cada um pelo desconto da
        # rescisão. O saldo que sobrasse não chegaria aqui — a trava acima
        # recusa o fechamento enquanto houver vale não endereçado.
        "vales_baixados": vales_baixados,
    }


# ---------------------------------------------------------------------------
# Vale de funcionário — adiantamento com desconto parcelado na folha. Se a
# soma das parcelas de vale de uma competência ultrapassar 40% do salário
# base da pessoa, é preciso confirmar explicitamente antes de lançar.
# ---------------------------------------------------------------------------
class ValeIn(BaseModel):
    pessoa_id: int
    valor_total: float
    forma_pagamento: str
    data_pagamento: date
    parcelas: int = 1
    competencia_inicio: str  # "AAAA-MM"
    observacao: str | None = None
    numero_documento_pagamento: str | None = None  # nº do documento do pagamento, p/ controle de extrato
    # Conta bancária da fazenda de onde sai o vale — obrigatória quando o
    # dinheiro realmente sai AGORA (forma_pagamento "dinheiro"/"pix"/
    # "transferencia"); irrelevante para "desconto_integral_folha" (nesse
    # caso não há saída de caixa nenhuma a registrar — ver criar_vale).
    conta_corrente_id: int | None = None
    confirmar: bool = False  # true para prosseguir mesmo ultrapassando 40% do salário


def _competencias_do_vale(competencia_inicio: str, parcelas: int) -> list[str]:
    competencias = [competencia_inicio]
    for _ in range(parcelas - 1):
        competencias.append(_competencia_seguinte(competencias[-1]))
    return competencias


def _reconciliar_vale_competencias(session: Session, pessoa_id: int, competencias: list[str]) -> None:
    """Recomputa valor_vale/valor_liquido da folha (não paga) e sincroniza a
    conta a pagar vinculada (não paga), para cada competência afetada por uma
    alteração (criação/edição/exclusão) de vale.

    O LÍQUIDO SAI DE `_liquido_folha`, NUNCA DA FÓRMULA COPIADA À MÃO. Esta
    função tinha a conta reescrita aqui dentro e ela ESQUECIA
    `valor_rubricas` — o efeito líquido das rubricas avulsas do holerite
    (bonificação, gueltas, reembolso, vale-alimentação, desconto avulso).
    Como TODA ação de vale passa por aqui (criar, editar, excluir, reparcelar,
    abater, desconsiderar, cancelar e as três voltas atrás), lançar um vale
    depois de uma bonificação apagava a bonificação do líquido gravado E da
    conta a pagar, em silêncio: o holerite continuava mostrando a linha, e o
    banco pagava o valor sem ela. É exatamente o defeito que `_liquido_folha`
    foi criada para não deixar voltar — e voltou, porque esta cópia ficou
    para trás."""
    for competencia in competencias:
        folha = session.exec(
            select(FolhaPagamento).where(
                FolhaPagamento.pessoa_id == pessoa_id,
                FolhaPagamento.competencia == competencia,
                FolhaPagamento.status != "pago",
            )
        ).first()
        if not folha:
            continue
        folha.valor_vale = _valor_vale(session, pessoa_id, competencia)
        folha.valor_liquido = _liquido_folha(
            folha.valor_bruto, folha.descontos, folha.valor_inss, folha.valor_ir, folha.valor_vale,
            folha.valor_rubricas,
        )
        _marcar_vale_aplicado(session, pessoa_id, competencia)
        session.add(folha)
        if folha.numero_lancamento_gerado:
            # Filtro de fazenda DENTRO da consulta, mesmo padrão de
            # `_recalcular_folha`: o número do lançamento é sequencial por ano
            # e não é chave global, então sem o recorte esta busca poderia
            # alcançar a conta a pagar de outro inquilino.
            conta = session.exec(
                select(ContaGerencial).where(
                    ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado,
                    ContaGerencial.fazenda_id == folha.fazenda_id,
                )
            ).first()
            if conta and conta.valor_pago is None:
                conta.valor_total = folha.valor_liquido
                session.add(conta)


def _vale_competencia_paga(
    session: Session, pessoa_id: int, competencias: list[str], fazenda_id: int | None,
) -> str | None:
    """Retorna a primeira competência, entre as informadas, cuja folha já
    esteja paga — a trava que impede um vale de mexer num holerite que já
    virou recibo (ver o bloco de congelamento da discriminação, acima).

    Filtro de fazenda INCONDICIONAL (`== fazenda_id`, que em None vira
    `IS NULL`) dentro da própria consulta, mesmo padrão de `_conta_da_folha`:
    fosse tolerante (`if fazenda_id is not None`), uma folha paga sem
    fazenda — as linhas órfãs que a migração de backfill assume existir —
    poderia travar ou liberar vale de qualquer tenant.

    Ordem das competências importa: quem chama passa a lista já ordenada e a
    mensagem de erro cita a PRIMEIRA competência paga encontrada, que é a que
    o dono precisa estornar primeiro."""
    for competencia in competencias:
        folha = session.exec(
            select(FolhaPagamento).where(
                FolhaPagamento.pessoa_id == pessoa_id,
                FolhaPagamento.competencia == competencia,
                FolhaPagamento.status == "pago",
                FolhaPagamento.fazenda_id == fazenda_id,
            )
        ).first()
        if folha:
            return competencia
    return None


def _exigir_competencias_nao_pagas(
    session: Session, pessoa_id: int, competencias: list[str], fazenda_id: int | None, verbo: str,
) -> None:
    """Recusa (400) quando alguma das competências de destino do vale já teve
    a folha PAGA.

    As duas portas que isto fecha, e que ficaram abertas desde que o vale
    existe: `criar_vale` nunca olhou a competência de destino (dava para
    lançar um vale novo em cima de um mês já pago), e `atualizar_vale` só
    olhava as competências ANTIGAS do vale (dava para mover um vale de um mês
    em aberto PARA um mês já pago). Nos dois casos a folha paga é imutável de
    propósito — a discriminação dela foi congelada no pagamento —, então a
    parcela nova entrava no banco, aparecia no relatório de vales, e o
    holerite daquele mês passava a mentir: cobrava um desconto que não foi
    descontado do dinheiro que saiu."""
    paga = _vale_competencia_paga(session, pessoa_id, competencias, fazenda_id)
    if paga:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A folha de {paga} desta pessoa já foi paga — não é possível {verbo} um vale nessa "
                f"competência. Estorne o pagamento da folha de {paga} ou escolha uma competência em aberto."
            ),
        )


# ── O TETO DE 40% DO SALÁRIO, EM UM LUGAR SÓ ────────────────────────────────
#
# O CASO QUE OBRIGOU A UNIFICAÇÃO (Jorbeson Nunes, pessoa 3, fazenda 1): a
# folha dele de 2026-08 fechava com líquido NEGATIVO (−R$ 866,50) — quase
# R$ 4.000 de vale numa competência só, contra R$ 3.393,00 de bruto, quando o
# teto de 40% do salário seria R$ 1.357,20. Ninguém foi avisado em nenhum
# momento, porque a conferência existia em DUAS das cinco portas que mexem no
# valor das parcelas (`criar_vale` e `atualizar_vale`) e em nenhuma das outras
# três (`editar_parcela_vale`, `_acao_reparcelar`, `_decisao_reparcelar`). Por
# elas dava para concentrar o saldo inteiro num mês, muito acima do teto, em
# silêncio absoluto.
#
# A REGRA CONTINUA SENDO UM AVISO CONFIRMÁVEL, não uma proibição: o dono pode
# ter motivo (um acerto combinado, um mês de saída). O que ele não pode é não
# ser avisado. Por isso as cinco portas devolvem o MESMO 409 com o mesmo
# `confirmar` — reenviar com `confirmar: true` passa.
#
# POR QUE UMA FUNÇÃO SÓ: a conta estava escrita à mão duas vezes (nas duas
# portas que conferiam), e uma terceira, quarta e quinta cópia seria a receita
# para as cinco divergirem no primeiro ajuste. Aqui mora a régua inteira: o
# limite, o que entra no total da competência e a forma da resposta.
TETO_VALE_SALARIO = 0.4


def _competencias_acima_do_teto_vale(
    session: Session, pessoa_id: int, salario_base: float,
    novos_valores: list[tuple[str, float]],
    *, parcela_ids_substituidas: frozenset[int] | set[int] = frozenset(),
) -> tuple[float, list[dict]]:
    """
    Quais competências ficariam acima do teto de 40% do salário, e o limite.

    `novos_valores` são os pares (competência, valor) que PASSARÃO a existir
    depois da operação — a criação de um vale parcelado, a reescrita de uma
    parcela, o novo cronograma de um reparcelamento. Valores da mesma
    competência são somados entre si, porque uma competência pode receber mais
    de uma parcela do mesmo vale (é o que `_decisao_desconsiderar` faz ao
    partir o mês em cobrado + assumido).

    `parcela_ids_substituidas` são as parcelas que a operação vai APAGAR ou
    REESCREVER — elas saem do "já lançado" para não serem contadas duas vezes
    (é o que `atualizar_vale` fazia com `ValeParcela.vale_id != vale_id`, só
    que por id, que também serve para quem mexe em parcelas avulsas).

    O total comparado com o limite é a soma de TODAS as parcelas de vale
    daquela pessoa naquela competência — não só as do vale que está sendo
    mexido: o teto é do funcionário, não do documento. Parcela
    `assumida_pela_fazenda` fica DE FORA, pela mesma razão de `_valor_vale`:
    ela não é descontada de ninguém, então não ocupa o teto de desconto dele.
    """
    limite = round(salario_base * TETO_VALE_SALARIO, 2)
    por_competencia: dict[str, float] = {}
    for competencia, valor in novos_valores:
        por_competencia[competencia] = round(por_competencia.get(competencia, 0.0) + round(valor, 2), 2)

    excedidas: list[dict] = []
    for competencia in sorted(por_competencia):
        ja_lancado = session.exec(
            select(ValeParcela).where(
                ValeParcela.pessoa_id == pessoa_id,
                ValeParcela.competencia == competencia,
                ValeParcela.assumida_pela_fazenda == False,  # noqa: E712
            )
        ).all()
        total_competencia = round(
            sum(p.valor for p in ja_lancado if p.id not in parcela_ids_substituidas)
            + por_competencia[competencia],
            2,
        )
        if total_competencia > limite:
            excedidas.append({"competencia": competencia, "total": total_competencia, "limite": limite})
    return limite, excedidas


def _exigir_teto_vale(
    session: Session, pessoa_id: int, salario_base: float | None,
    novos_valores: list[tuple[str, float]], *, confirmar: bool, verbo: str,
    parcela_ids_substituidas: frozenset[int] | set[int] = frozenset(),
) -> None:
    """
    Recusa com 409 + `confirmar` quando a operação deixaria alguma competência
    acima do teto de 40% — a MESMA porta de saída nas cinco portas do vale.

    A mensagem diz QUAL competência estourou, QUANTO ficaria e qual é o
    limite, porque "ultrapassa 40%" sem os números não diz ao dono o que ele
    precisa mudar; `competencias_excedidas` traz o mesmo, estruturado, para a
    tela montar a confirmação (é o payload que ValeItemModal/FolhaPagamentoView
    já leem).

    SALÁRIO BASE AUSENTE NÃO TRAVA a operação, e isso é deliberado: as duas
    portas de CRIAÇÃO (`criar_vale`/`atualizar_vale`) já exigem o salário
    cadastrado antes de chegar aqui — é lá que o cadastro incompleto tem de
    ser resolvido. Nas outras três (editar parcela, reparcelar, reparcelar no
    ato do pagamento) o vale JÁ existe, e recusar por causa de um campo do
    cadastro impediria o dono de consertar justamente o vale que ele quer
    ajustar. Sem salário não há teto calculável — segue sem aviso, como era.
    """
    if not salario_base:
        return
    limite, excedidas = _competencias_acima_do_teto_vale(
        session, pessoa_id, salario_base, novos_valores,
        parcela_ids_substituidas=parcela_ids_substituidas,
    )
    if not excedidas or confirmar:
        return
    detalhe = "; ".join(f"{c['competencia']}: R$ {c['total']:.2f}" for c in excedidas)
    raise HTTPException(status_code=409, detail={
        "mensagem": (
            f"O desconto de vale ultrapassa 40% do salário (limite de R$ {limite:.2f}) em "
            f"{len(excedidas)} competência(s) — {detalhe}. Confirme para {verbo} mesmo assim."
        ),
        "competencias_excedidas": excedidas,
        "limite": limite,
    })


def _validar_conta_vale(
    session: Session, forma_pagamento: str, conta_corrente_id: int | None, fazenda_id: int | None,
) -> ContaCorrente | None:
    """Resolve e valida a conta bancária de um vale de funcionário —
    obrigatória só quando o dinheiro sai AGORA (dinheiro/pix/transferência);
    "desconto_integral_folha" não movimenta banco nenhum na hora do vale (o
    efeito é só reduzir o líquido da folha futura), então não se aplica."""
    if forma_pagamento == "desconto_integral_folha":
        return None
    if not conta_corrente_id:
        raise HTTPException(status_code=400, detail="Selecione a conta bancária de onde sai o vale.")
    conta = session.get(ContaCorrente, conta_corrente_id)
    if not conta or (conta.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada")
    return conta


# Rótulo e descrição do lançamento espelho do vale, em constante/função porque
# há DOIS lados que precisam do mesmo texto: quem cria o lançamento (aqui) e
# quem o restaura depois de a fazenda ter assumido e o dono ter voltado atrás
# (`reverter_desconsideracao`, em rh_vale_acoes.py). Fossem duas literais
# soltas, a volta escreveria um rótulo parecido-mas-diferente e o lançamento
# deixaria de ser reconhecido como baixa espelhada de vale
# (TIPOS_DOCUMENTO_BAIXA_ESPELHADA, em financeiro.py) — o Financeiro voltaria
# a deixar estornar/editar à mão um lançamento que pertence ao RH.
TIPO_DOCUMENTO_VALE = "Vale de funcionário"


def descricao_conta_vale(pessoa_nome: str, competencia_inicio: str) -> str:
    return f"Vale — {pessoa_nome} ({competencia_inicio})"


def _sincronizar_conta_vale(
    session: Session, vale: ValeFuncionario, pessoa: Pessoa, conta: Optional[ContaCorrente],
    numero_documento_pagamento: Optional[str], fazenda_id: Optional[int],
) -> None:
    """
    Cria (ou, numa edição, atualiza) o lançamento (ContaGerencial) que
    representa a SAÍDA de caixa do vale — espelha `criar_folha_pagamento`,
    só que já nasce PAGO: o vale é entregue ao funcionário no ato, não é uma
    conta a pagar futura (mesmo padrão de `registrar_pagamento_diaria`, em
    rh_contratos.py).

    NÃO há duplicidade de valor no extrato, e isso é intencional: a folha de
    pagamento lança o valor LÍQUIDO (já com o vale descontado — ver
    `FolhaPagamento.valor_vale`/`valor_liquido`). Antes desta função existir,
    o dinheiro do vale saía do caixa/banco no ato e não aparecia em lugar
    nenhum do Financeiro — este lançamento é exatamente o que faltava para
    fechar esse furo. Quando a folha for paga depois, ela paga só o
    restante (líquido menor), então vale + líquido da folha = valor bruto —
    o vale nunca é contado duas vezes. NÃO remova este lançamento achando
    que é bug de duplicidade.

    Quando `conta` é None (forma_pagamento == "desconto_integral_folha"), não
    há saída de caixa nenhuma a registrar: nenhum ContaGerencial é criado, e,
    se o vale tinha um lançamento de uma edição anterior (mudou de forma de
    pagamento), ele é removido.
    """
    conta_existente = None
    if vale.numero_lancamento_gerado:
        conta_existente = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado)
        ).first()

    if conta is None:
        if conta_existente:
            session.delete(conta_existente)
        vale.numero_lancamento_gerado = None
        session.add(vale)
        return

    ano, mes = (int(x) for x in vale.competencia_inicio.split("-"))
    descricao = descricao_conta_vale(pessoa.nome, vale.competencia_inicio)
    if conta_existente:
        conta_existente.descricao = descricao
        conta_existente.fornecedor_cliente = pessoa.nome
        conta_existente.data_vencimento = vale.data_pagamento
        conta_existente.data_competencia = date(ano, mes, 1)
        conta_existente.valor_total = vale.valor_total
        conta_existente.data_pagamento = vale.data_pagamento
        conta_existente.valor_pago = vale.valor_total
        conta_existente.conta_bancaria = rotulo_conta_corrente(conta)
        conta_existente.forma_pagamento = vale.forma_pagamento
        conta_existente.numero_documento_pagamento = numero_documento_pagamento
        session.add(conta_existente)
    else:
        numero_lancamento = _proximo_numero_lancamento(session, vale.data_pagamento.year)
        vale.numero_lancamento_gerado = numero_lancamento
        session.add(vale)
        session.add(ContaGerencial(
            numero_lancamento=numero_lancamento,
            descricao=descricao,
            data_vencimento=vale.data_pagamento,
            data_competencia=date(ano, mes, 1),
            fornecedor_cliente=pessoa.nome,
            tipo_documento=TIPO_DOCUMENTO_VALE,
            centro_custo="Pecuária Leiteira",
            valor_total=vale.valor_total,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            data_pagamento=vale.data_pagamento,
            valor_pago=vale.valor_total,
            conta_bancaria=rotulo_conta_corrente(conta),
            forma_pagamento=vale.forma_pagamento,
            numero_documento_pagamento=numero_documento_pagamento,
            fazenda_id=fazenda_id,
        ))


# ---------------------------------------------------------------------------
# EXCLUIR ≠ CANCELAR — a distinção que este bloco escreve no código, porque
# confundir as duas foi o que originou esta correção.
#
# EXCLUIR (DELETE /vales, DELETE /vale-avulso) é para o lançamento que NUNCA
# DEVERIA TER EXISTIDO: valor errado, pessoa errada, vale digitado duas
# vezes. Apaga o vale, as parcelas e a saída de caixa que ele criou no
# Financeiro — porque aquele dinheiro não saiu daquele jeito. É a única porta
# para "lancei errado", e por isso ela CONTINUA ABERTA mesmo com a conta
# baixada: diferente da folha, das férias, do 13º e das guias de FGTS/DCTF
# (ver `_exigir_conta_nao_paga`), a conta do vale JÁ NASCE PAGA por desenho —
# o vale é entregue no ato (ver `_sincronizar_conta_vale`). Aplicar aqui a
# mesma trava daquelas quatro tornaria excluir um vale impossível PARA
# SEMPRE, e o dono ficaria preso com o erro de digitação no banco.
#
# CANCELAR (ação "cancelar", em rh_vale_acoes.py) é para o vale que
# ACONTECEU e só não vai mais ser cobrado do funcionário: o dinheiro saiu de
# verdade, a saída de caixa FICA no extrato, o saldo vira despesa da fazenda
# — e há desfazer ("reverter_cancelamento"). Quem quer perdoar um vale e
# clica na lixeira apaga do extrato uma saída de caixa que existiu.
#
# O ERRO DO CÓDIGO ANTERIOR NÃO ERA APAGAR A CONTA JUNTO — era apagar EM
# SILÊNCIO. Daqui em diante:
#   (1) a tela recebe, ANTES de perguntar, o que vai junto e por qual
#       lançamento (`_previa_exclusao_vale`), em vez de inventar um texto
#       genérico com dados que ela não tem; e
#   (2) a exclusão é RECUSADA (400) quando há trabalho humano investido
#       naquele lançamento (`_impedimento_excluir_vale`) — nesse caso a
#       mensagem manda cancelar o vale, ou acertar no Financeiro.
# ---------------------------------------------------------------------------
# Frase única do "não era isto que você queria" — a diferença entre as duas
# portas dita em UMA linha, no diálogo de exclusão e em toda recusa. Uma
# constante e não uma literal solta em cada lugar: era exatamente a lição do
# vale de funcionário; o vale avulso tem a sua (não existe "cancelar" lá).
ALTERNATIVA_CANCELAR_VALE = (
    'Se o vale ACONTECEU e só não vai mais ser cobrado, não exclua: use a ação "Cancelar o vale" '
    "— ela mantém a saída de caixa no extrato, avisa o Financeiro (o saldo vira despesa da "
    "fazenda) e pode ser desfeita depois."
)
ALTERNATIVA_VALE_AVULSO = (
    "Se o vale ACONTECEU e só o valor está errado, edite o vale em vez de excluir — excluir é "
    "para o vale que nunca deveria ter sido lançado."
)


def _saida_de_caixa_do_vale(conta: ContaGerencial | None) -> dict | None:
    """Os números da saída de caixa que a exclusão leva junto, para a TELA
    poder nomeá-la. `None` quando o vale não move caixa (desconto integral na
    folha / no próximo pagamento — ver `_sincronizar_conta_vale`)."""
    if conta is None:
        return None
    valor = conta.valor_pago if conta.valor_pago is not None else conta.valor_total
    return {
        "numero_lancamento": conta.numero_lancamento,
        "valor": round(valor, 2) if valor is not None else None,
        "data_pagamento": conta.data_pagamento.isoformat() if conta.data_pagamento else None,
        "conta_bancaria": conta.conta_bancaria,
        "descricao": conta.descricao,
    }


def _frase_saida_de_caixa(conta: ContaGerencial | None) -> str:
    """A mesma informação em uma frase pronta — o diálogo da tela é um
    `confirm` de texto, e montar a frase aqui é o que impede o front de
    descrever o lançamento com dados que ele não tem (o número, a data e a
    conta bancária da baixa vivem só no Financeiro)."""
    if conta is None:
        return (
            "Este vale não tem saída de caixa no Financeiro (é descontado integralmente do "
            "pagamento), então nada será apagado do extrato."
        )
    valor = conta.valor_pago if conta.valor_pago is not None else (conta.valor_total or 0)
    quando = f" em {conta.data_pagamento.strftime('%d/%m/%Y')}" if conta.data_pagamento else ""
    onde = f", {conta.conta_bancaria}" if conta.conta_bancaria else ""
    return (
        f"A saída de caixa {conta.numero_lancamento} (R$ {valor:.2f}{quando}{onde}) será APAGADA "
        "do extrato do Financeiro junto com o vale."
    )


def _comprovantes_do_vale(session: Session, coluna_comprovante, vale_id: int) -> list[LancamentoAnexo]:
    """Comprovantes anexados AO VALE (rotas /vales/{tipo}/{id}/comprovante).

    Sem filtro de fazenda na consulta — e isto NÃO é o padrão tolerante
    proibido: a âncora é `vale_id`, um id que quem chama já resolveu com
    `== fazenda_id`, e `coluna_comprovante` é FK para ele, então nenhuma
    linha de outro tenant alcança este resultado. Repetir o recorte aqui só
    criaria o risco inverso — NÃO enxergar um anexo antigo (fazenda_id nulo)
    e deixar o arquivo órfão ao apagar o vale."""
    return list(session.exec(select(LancamentoAnexo).where(coluna_comprovante == vale_id)).all())


def _impedimento_excluir_vale(
    session: Session, conta: ContaGerencial | None, valor_vale: float,
    coluna_comprovante, vale_id: int, alternativa: str,
) -> str | None:
    """
    O motivo, em palavras, para NÃO deixar excluir este vale — ou None.

    O CRITÉRIO: excluir é para o lançamento que nunca existiu de verdade.
    Quando alguém já INVESTIU TRABALHO naquele lançamento — conferiu,
    guardou o documento, acertou o valor contra o extrato do banco —, o
    lançamento existe de verdade e apagá-lo destruiria em silêncio o trabalho
    de quem fez. Aí a porta certa é outra (cancelar, ou acertar no
    Financeiro), e é isso que a mensagem diz.

    OS SINAIS, e por que são estes:

    1. COMPROVANTE ANEXADO AO VALE. É o mais claro dos três: alguém abriu o
       vale, conferiu o pagamento e guardou o PDF/foto do pix. Além do
       trabalho, o vínculo é FK (`LancamentoAnexo.vale_funcionario_id` /
       `vale_avulso_id`): apagar o vale deixava a linha do anexo apontando
       para um vale que não existe mais — e o arquivo, inalcançável no
       Storage.

    2. ANEXO OU DOCUMENTO ARQUIVADO NO LANÇAMENTO. Mesma natureza, do lado
       do Financeiro: anexo de lançamento (`LancamentoAnexo.numero_lancamento`)
       ou documento da Central de Documentos (`DocumentoArquivado.
       numero_lancamento`) preso a esta saída de caixa. Ambos ficariam
       órfãos, apontando para um LC- que sumiu do extrato.

    3. VALOR DIVERGENTE ENTRE A CONTA E O VALE. A sincronização reescreve
       `valor_total` E `valor_pago` com o valor do vale em toda criação e
       edição (ver `_sincronizar_conta_vale`), e nada mais no sistema mexe
       neles: divergência aqui é acerto manual em Lançamentos — alguém
       bateu o extrato do banco contra o sistema. Apagar apagaria o acerto.

    O QUE FICOU DE FORA, DE PROPÓSITO (e por quê):
    - `descricao` e `conta_bancaria` divergentes: os dois DERIVAM de dados
      que mudam sozinhos (o nome da pessoa, o rótulo da conta corrente
      renomeada em Parâmetros). Usá-los como sinal travaria a exclusão de
      vales em que ninguém tocou — falso positivo que fecharia a porta para
      sempre, que é justamente o que não pode acontecer aqui.
    - `codigo_conta` preenchido (classificação no plano de contas): é
      trabalho humano de verdade, mas é trabalho de LOTE — a conferência da
      DRE classifica tudo que está sem conta de uma vez. Bloquear por ele
      travaria, na prática, todo vale de uma fazenda que mantém a DRE em
      dia; o remédio seria pior que a doença.
    """
    comprovantes = _comprovantes_do_vale(session, coluna_comprovante, vale_id)
    if comprovantes:
        nomes = ", ".join(sorted(a.nome_arquivo for a in comprovantes)[:3])
        return (
            f"Este vale tem comprovante anexado ({nomes}) — alguém já conferiu este pagamento e "
            f"guardou o documento dele, então ele aconteceu de verdade. {alternativa} Se o "
            "comprovante foi anexado por engano, exclua o comprovante primeiro; aí o vale volta a "
            "poder ser excluído."
        )
    if conta is None:
        return None

    numero = conta.numero_lancamento
    anexos = session.exec(
        select(LancamentoAnexo).where(LancamentoAnexo.numero_lancamento == numero)
    ).all()
    documentos = session.exec(
        select(DocumentoArquivado).where(DocumentoArquivado.numero_lancamento == numero)
    ).all()
    if anexos or documentos:
        quantos = len(anexos) + len(documentos)
        return (
            f"A saída de caixa deste vale ({numero}) tem {quantos} documento(s) anexado(s) no "
            "Financeiro — excluir o vale apagaria o lançamento e deixaria esses documentos sem "
            f"lançamento nenhum por trás. {alternativa} Se os documentos não são deste vale, "
            "remova-os em Lançamentos antes de excluir."
        )

    divergentes = [
        v for v in (conta.valor_total, conta.valor_pago)
        if v is not None and round(v, 2) != round(valor_vale, 2)
    ]
    if divergentes:
        return (
            f"A saída de caixa deste vale ({numero}) foi ajustada à mão no Financeiro: o lançamento "
            f"está com R$ {round(divergentes[0], 2):.2f} e o vale, com R$ {round(valor_vale, 2):.2f}. "
            "Excluir o vale apagaria esse acerto sem deixar rastro — resolva a divergência em "
            f"Financeiro > Lançamentos antes. {alternativa}"
        )
    return None


def _previa_exclusao_vale(
    *, conta: ContaGerencial | None, impedimento: str | None, titulo: str, efeito: str,
    alternativa: str,
) -> dict:
    """O que a tela precisa para o diálogo de exclusão: se dá para excluir,
    por que não, e — quando dá — a frase que nomeia o que vai junto.

    `impedimento` vem pronto de quem chama (`_impedimento_excluir_vale_...`),
    que é a MESMA função usada pelo DELETE: a tela nunca oferece uma exclusão
    que o backend vai negar, nem nega uma que ele aceitaria. O DELETE confere
    tudo de novo na hora — esta prévia informa, nunca autoriza."""
    return {
        "pode_excluir": impedimento is None,
        "impedimento": impedimento,
        "lancamento": _saida_de_caixa_do_vale(conta),
        "confirmacao": f"{titulo} {_frase_saida_de_caixa(conta)} {efeito}",
        "alternativa": alternativa,
    }


@router.get("/vales")
def listar_vales(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(ValeFuncionario)
    if fazenda_id is not None:
        query = query.where(ValeFuncionario.fazenda_id == fazenda_id)
    vales = session.exec(query.order_by(ValeFuncionario.data_pagamento.desc())).all()
    nomes_usuarios = mapa_usuarios(session, {v.usuario_id for v in vales})
    origens = origens_lancamento_por_vale(session, {v.id for v in vales}, "vale_funcionario_id")
    saida = []
    for v in vales:
        parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == v.id)).all()
        saida.append({
            **v.model_dump(), "pessoa_nome": pessoas.get(v.pessoa_id, "—"),
            "usuario_nome": nomes_usuarios.get(v.usuario_id),
            "parcelas_detalhe": sorted(({**p.model_dump()} for p in parcelas), key=lambda p: p["competencia"]),
            "origem_lancamento": origens.get(v.id),
        })
    return saida


@router.post("/vales")
def criar_vale(
    dados: ValeIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.valor_total <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.parcelas < 1:
        raise HTTPException(status_code=400, detail="Informe ao menos 1 parcela")
    conta = _validar_conta_vale(session, dados.forma_pagamento, dados.conta_corrente_id, fazenda_id)

    competencias = _competencias_do_vale(dados.competencia_inicio, dados.parcelas)
    # Nenhuma das competências de destino pode ter folha já paga — ver
    # `_exigir_competencias_nao_pagas` para o holerite que passava a mentir.
    _exigir_competencias_nao_pagas(session, dados.pessoa_id, competencias, fazenda_id, "lançar")
    valor_parcela = round(dados.valor_total / dados.parcelas, 2)
    # a última parcela absorve o arredondamento, para a soma bater com valor_total
    valores_parcela = [valor_parcela] * (dados.parcelas - 1)
    valores_parcela.append(round(dados.valor_total - valor_parcela * (dados.parcelas - 1), 2))

    if not pessoa.salario_base:
        raise HTTPException(
            status_code=400,
            detail="Cadastre o salário base da pessoa (Configurações > Cadastro > Pessoas) antes de lançar um vale.",
        )

    # Teto de 40% do salário — a MESMA conferência das outras quatro portas
    # que mexem no valor das parcelas (ver `_exigir_teto_vale`).
    _exigir_teto_vale(
        session, dados.pessoa_id, pessoa.salario_base, list(zip(competencias, valores_parcela)),
        confirmar=dados.confirmar, verbo="lançar",
    )

    vale = ValeFuncionario(
        pessoa_id=dados.pessoa_id, valor_total=dados.valor_total, forma_pagamento=dados.forma_pagamento,
        data_pagamento=dados.data_pagamento, parcelas=dados.parcelas, competencia_inicio=dados.competencia_inicio,
        observacao=dados.observacao, numero_documento_pagamento=dados.numero_documento_pagamento,
        conta_corrente_id=conta.id if conta else None, usuario_id=user.id,
        fazenda_id=fazenda_id,
    )
    session.add(vale)
    session.commit()
    session.refresh(vale)
    for competencia, valor in zip(competencias, valores_parcela):
        session.add(ValeParcela(
            vale_id=vale.id, pessoa_id=dados.pessoa_id, competencia=competencia, valor=valor, fazenda_id=fazenda_id,
        ))
    session.commit()

    # Gera (quando aplicável) o lançamento que faltava no extrato para a
    # saída de caixa do vale — ver `_sincronizar_conta_vale`.
    _sincronizar_conta_vale(session, vale, pessoa, conta, dados.numero_documento_pagamento, fazenda_id)
    session.commit()

    # Efeito imediato: se já existir uma folha (não paga) para alguma das
    # competências afetadas, recomputa o valor_vale/líquido e sincroniza a
    # conta a pagar vinculada — sem depender do self-heal no próximo GET.
    _reconciliar_vale_competencias(session, dados.pessoa_id, competencias)
    session.commit()
    session.refresh(vale)

    return {**vale.model_dump(), "parcelas_detalhe": [
        {"competencia": c, "valor": v} for c, v in zip(competencias, valores_parcela)
    ]}


@router.put("/vales/{vale_id}")
def atualizar_vale(
    vale_id: int, dados: ValeIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    vale = session.get(ValeFuncionario, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.valor_total <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.parcelas < 1:
        raise HTTPException(status_code=400, detail="Informe ao menos 1 parcela")
    if not pessoa.salario_base:
        raise HTTPException(
            status_code=400,
            detail="Cadastre o salário base da pessoa (Configurações > Cadastro > Pessoas) antes de editar um vale.",
        )
    conta = _validar_conta_vale(session, dados.forma_pagamento, dados.conta_corrente_id, fazenda_id)

    pessoa_id_antigo = vale.pessoa_id
    parcelas_atuais = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    # PUT /vales apaga TODAS as parcelas e recria com split igual — o que
    # apagaria junto a marca de "mês desconsiderado"/"vale cancelado" e o
    # valor que a fazenda já assumiu no Financeiro por causa dela, sem
    # desfazer nada lá. Vale que passou por uma ação do dono só se mexe pelas
    # próprias ações (ver rh_vale_acoes.py).
    if vale.status == "cancelado":
        raise HTTPException(
            status_code=400,
            detail="Este vale foi cancelado — o saldo já virou despesa da fazenda e ele não pode mais ser editado.",
        )
    if any(p.assumida_pela_fazenda for p in parcelas_atuais):
        raise HTTPException(
            status_code=400,
            detail=(
                "Este vale tem mês desconsiderado (valor já assumido pela fazenda) — use as ações do vale "
                "(reparcelar/abater) em vez de reescrevê-lo por inteiro."
            ),
        )
    competencias_atuais = [p.competencia for p in parcelas_atuais]
    competencia_paga = _vale_competencia_paga(session, pessoa_id_antigo, competencias_atuais, fazenda_id)
    if competencia_paga:
        raise HTTPException(
            status_code=400,
            detail=f"Vale já aplicado na folha paga de {competencia_paga} não pode ser editado.",
        )

    competencias_novas = _competencias_do_vale(dados.competencia_inicio, dados.parcelas)
    # A checagem acima olha só o DESTINO ANTIGO do vale. Faltava esta: mudar
    # competencia_inicio/parcelas (ou a pessoa) para um mês cuja folha já foi
    # paga movia a parcela para dentro de um holerite fechado — que não podia
    # mais absorvê-la. Ver `_exigir_competencias_nao_pagas`.
    _exigir_competencias_nao_pagas(session, dados.pessoa_id, competencias_novas, fazenda_id, "mover")

    valor_parcela = round(dados.valor_total / dados.parcelas, 2)
    valores_parcela = [valor_parcela] * (dados.parcelas - 1)
    valores_parcela.append(round(dados.valor_total - valor_parcela * (dados.parcelas - 1), 2))

    # Teto de 40% do salário — mesma função das outras quatro portas. As
    # parcelas atuais do vale saem do "já lançado" (`parcela_ids_substituidas`)
    # porque este PUT as apaga e recria: contá-las somaria o vale a si mesmo.
    _exigir_teto_vale(
        session, dados.pessoa_id, pessoa.salario_base, list(zip(competencias_novas, valores_parcela)),
        confirmar=dados.confirmar, verbo="salvar",
        parcela_ids_substituidas={p.id for p in parcelas_atuais},
    )

    vale.pessoa_id = dados.pessoa_id
    vale.valor_total = dados.valor_total
    vale.forma_pagamento = dados.forma_pagamento
    vale.data_pagamento = dados.data_pagamento
    vale.parcelas = dados.parcelas
    vale.competencia_inicio = dados.competencia_inicio
    vale.observacao = dados.observacao
    vale.numero_documento_pagamento = dados.numero_documento_pagamento
    vale.conta_corrente_id = conta.id if conta else None
    session.add(vale)
    for p in parcelas_atuais:
        session.delete(p)
    session.commit()

    for competencia, valor in zip(competencias_novas, valores_parcela):
        session.add(ValeParcela(
            vale_id=vale.id, pessoa_id=dados.pessoa_id, competencia=competencia, valor=valor, fazenda_id=fazenda_id,
        ))
    session.commit()

    # Mantém o lançamento gerado (ContaGerencial) da saída de caixa do vale
    # em sincronia com a edição — cria/atualiza/remove conforme a mudança.
    _sincronizar_conta_vale(session, vale, pessoa, conta, dados.numero_documento_pagamento, fazenda_id)
    session.commit()

    if dados.pessoa_id == pessoa_id_antigo:
        _reconciliar_vale_competencias(session, pessoa_id_antigo, sorted(set(competencias_atuais) | set(competencias_novas)))
    else:
        _reconciliar_vale_competencias(session, pessoa_id_antigo, competencias_atuais)
        _reconciliar_vale_competencias(session, dados.pessoa_id, competencias_novas)
    session.commit()
    session.refresh(vale)

    return {**vale.model_dump(), "parcelas_detalhe": [
        {"competencia": c, "valor": v} for c, v in zip(competencias_novas, valores_parcela)
    ]}


class ValeParcelaEditIn(BaseModel):
    valor: float
    # Obrigatório só quando `valor` diverge do valor atual da parcela:
    # "conceder" (só essa parcela muda — a diferença fica como concessão
    # gratuita, o vale passa a ter soma de parcelas diferente do valor
    # efetivamente pago); "redistribuir_igual" (a diferença é dividida
    # igualmente entre as parcelas pendentes POSTERIORES a esta — nunca
    # mexe em parcela já vencida/anterior); "redistribuir_livre" (o
    # chamador informa o valor de cada parcela pendente posterior, sem
    # validação de soma — o front já cuida de auto-balancear as não-tocadas).
    acao: str | None = None
    valores_parcelas: dict[int, float] | None = None  # parcela_id -> novo valor, só p/ "redistribuir_livre"
    confirmar: bool = False
    # Só para "redistribuir_livre": confirma que o total final (parcela
    # editada + demais posteriores + já pagas) pode ficar diferente do
    # valor efetivamente pago no vale (vale.valor_total) — sem isso, a
    # divergência vira um 409 pedindo confirmação antes de salvar.
    confirmar_divergencia_total: bool = False
    # Confirma prosseguir mesmo concentrando, em alguma competência, mais de
    # 40% do salário em desconto de vale (ver `_exigir_teto_vale`). CAMPO
    # PRÓPRIO, e não o `confirmar` acima: aquele confirma que o valor digitado
    # diverge do calculado — reusá-lo faria quem confirma a divergência
    # confirmar junto, sem ver, o estouro do teto legal. São dois avisos
    # diferentes e cada um tem de ser respondido por quem o leu.
    confirmar_teto: bool = False


@router.put("/vales/{vale_id}/parcelas/{parcela_id}")
def editar_parcela_vale(
    vale_id: int, parcela_id: int, dados: ValeParcelaEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Edita o valor de UMA parcela de um vale de funcionário — diferente de
    PUT /vales/{id} (substitui o vale inteiro, recriando todas as parcelas
    com split igual). `ValeFuncionario.valor_total` nunca é tocado aqui: ele
    é o valor efetivamente pago/adiantado ao funcionário (histórico), e pode
    legitimamente divergir da soma atual das parcelas depois de uma
    concessão — é essa divergência que o front mostra no popup final."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeFuncionario, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    parcela = session.get(ValeParcela, parcela_id)
    if not parcela or parcela.vale_id != vale_id:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")
    if dados.valor < 0:
        raise HTTPException(status_code=400, detail="Valor da parcela não pode ser negativo")

    competencia_paga = _vale_competencia_paga(session, vale.pessoa_id, [parcela.competencia], fazenda_id)
    if competencia_paga:
        raise HTTPException(
            status_code=400,
            detail=f"Parcela já aplicada na folha paga de {competencia_paga} não pode ser editada.",
        )

    todas_parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    # Só as parcelas POSTERIORES (mesma ordem de competência) entram na
    # redistribuição — editar a parcela 3/10 nunca deve alterar 1 e 2, só
    # 4-10. "Pendente" continua significando "ainda não aplicada na folha paga".
    outras_pendentes = [
        p for p in todas_parcelas
        if p.id != parcela_id and p.competencia > parcela.competencia
        and not _vale_competencia_paga(session, vale.pessoa_id, [p.competencia], fazenda_id)
    ]
    diferenca = round(dados.valor - parcela.valor, 2)

    if diferenca != 0 and not dados.confirmar:
        raise HTTPException(status_code=409, detail={
            "mensagem": "O valor informado é diferente do valor calculado desta parcela.",
            "valor_calculado": parcela.valor,
            "valor_informado": dados.valor,
            "diferenca": diferenca,
            "parcelas_pendentes_restantes": len(outras_pendentes),
        })

    # Os valores que as parcelas PASSARÃO a ter (parcela_id -> valor), montados
    # antes de gravar qualquer coisa: é sobre eles que o teto de 40% é
    # conferido, e um 409 de teto tem de acontecer com o banco intacto.
    planejados: dict[int, float] = {parcela_id: round(dados.valor, 2)}

    if diferenca != 0:
        if dados.acao == "conceder":
            pass  # só essa parcela muda
        elif dados.acao == "redistribuir_igual":
            if not outras_pendentes:
                raise HTTPException(status_code=400, detail="Não há parcelas pendentes para redistribuir — escolha conceder.")
            total_a_redistribuir = round(sum(p.valor for p in outras_pendentes) - diferenca, 2)
            if total_a_redistribuir < 0:
                raise HTTPException(status_code=400, detail="A diferença é maior do que o total das demais parcelas pendentes.")
            valor_base = round(total_a_redistribuir / len(outras_pendentes), 2)
            restante = total_a_redistribuir
            for i, p in enumerate(outras_pendentes):
                novo = valor_base if i < len(outras_pendentes) - 1 else round(restante, 2)
                restante = round(restante - novo, 2)
                planejados[p.id] = novo
        elif dados.acao == "redistribuir_livre":
            if not outras_pendentes:
                raise HTTPException(status_code=400, detail="Não há parcelas pendentes para redistribuir — escolha conceder.")
            if not dados.valores_parcelas:
                raise HTTPException(status_code=400, detail="Informe o valor de cada parcela pendente.")
            ids_pendentes = {p.id for p in outras_pendentes}
            ids_informados = set(dados.valores_parcelas.keys())
            if ids_informados != ids_pendentes:
                raise HTTPException(status_code=400, detail="Informe o valor de todas as parcelas pendentes, e só delas.")
            for novo in dados.valores_parcelas.values():
                if novo < 0:
                    raise HTTPException(status_code=400, detail="Valor de parcela não pode ser negativo.")

            # Valores livres não são obrigados a somar o valor original —
            # antes de aplicar, confirma que o total final (parcela editada +
            # posteriores + já aplicadas, que não mudam) pode divergir do
            # valor efetivamente pago no vale (lança como concessão se
            # ficar menor, como acréscimo se ficar maior).
            ids_outras_pendentes = {p.id for p in outras_pendentes}
            parcelas_nao_tocadas = [p for p in todas_parcelas if p.id != parcela_id and p.id not in ids_outras_pendentes]
            soma_final = round(
                dados.valor + sum(dados.valores_parcelas.values()) + sum(p.valor for p in parcelas_nao_tocadas), 2
            )
            diferenca_total = round(soma_final - vale.valor_total, 2)
            if diferenca_total != 0 and not dados.confirmar_divergencia_total:
                raise HTTPException(status_code=409, detail={
                    "mensagem": "O valor total das parcelas ficará diferente do valor efetivamente pago no vale.",
                    "valor_vale": vale.valor_total,
                    "valor_lancado": soma_final,
                    "diferenca": diferenca_total,
                })

            for p in outras_pendentes:
                planejados[p.id] = round(dados.valores_parcelas[p.id], 2)
        else:
            raise HTTPException(status_code=400, detail="Informe a ação: redistribuir_igual, redistribuir_livre ou conceder.")

    # Teto de 40% do salário — a terceira das cinco portas. Era a mais fácil de
    # usar para concentrar o saldo inteiro num mês: bastava editar uma parcela
    # para o valor cheio e conceder. Confere o CRONOGRAMA INTEIRO que a edição
    # produz (a parcela editada mais as redistribuídas), não só a parcela
    # tocada, porque redistribuir empurra valor para os meses seguintes.
    competencia_por_id = {p.id: p.competencia for p in todas_parcelas}
    pessoa_do_vale = session.exec(
        select(Pessoa).where(Pessoa.id == vale.pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    _exigir_teto_vale(
        session, vale.pessoa_id, pessoa_do_vale.salario_base if pessoa_do_vale else None,
        [(competencia_por_id[pid], valor) for pid, valor in planejados.items()],
        confirmar=dados.confirmar_teto, verbo="salvar",
        parcela_ids_substituidas=set(planejados),
    )

    parcelas_por_id = {p.id: p for p in todas_parcelas}
    for pid, valor in planejados.items():
        parcelas_por_id[pid].valor = valor
        session.add(parcelas_por_id[pid])
    session.commit()

    todas_parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    competencias_afetadas = sorted({p.competencia for p in todas_parcelas})
    _reconciliar_vale_competencias(session, vale.pessoa_id, competencias_afetadas)
    session.commit()
    session.refresh(vale)

    soma_parcelas = round(sum(p.valor for p in todas_parcelas), 2)
    return {
        **vale.model_dump(),
        "parcelas_detalhe": sorted(({**p.model_dump()} for p in todas_parcelas), key=lambda p: p["competencia"]),
        "soma_parcelas_atual": soma_parcelas,
        "diverge_valor_pago": soma_parcelas != vale.valor_total,
        "diferenca_valor_pago": round(soma_parcelas - vale.valor_total, 2),
    }


@router.delete("/vales/{vale_id}/parcelas/{parcela_id}")
def excluir_parcela_vale(
    vale_id: int, parcela_id: int, acao: str = "conceder", confirmar: bool = False,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Exclui UMA parcela de um vale de funcionário — diferente de DELETE
    /vales/{id} (apaga o vale inteiro, incluindo o lançamento de caixa).
    Segue a mesma ordem de validação de `editar_parcela_vale` (ver ali para o
    porquê de cada regra), mas não é o motor genérico de `exclusoes.py`: é
    sub-registro com reconciliação própria via `_reconciliar_vale_competencias`.

    `acao`:
    - "conceder": apaga só a parcela; `ValeFuncionario.valor_total` NUNCA
      muda aqui (é o valor efetivamente pago/adiantado, histórico) — a soma
      das parcelas passa a divergir dele, e a resposta expõe
      `diverge_valor_pago`/`diferenca_valor_pago` para o front avisar.
    - "redistribuir_igual": distribui o valor da parcela apagada entre as
      parcelas PENDENTES POSTERIORES (mesma regra de "só posteriores" de
      `editar_parcela_vale` — nunca mexe em parcela já paga/anterior), com o
      resto (arredondamento) na última — a soma das parcelas se mantém.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeFuncionario, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    parcela = session.get(ValeParcela, parcela_id)
    if not parcela or parcela.vale_id != vale_id:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")

    competencia_paga = _vale_competencia_paga(session, vale.pessoa_id, [parcela.competencia], fazenda_id)
    if competencia_paga:
        raise HTTPException(
            status_code=400,
            detail=f"Parcela já aplicada na folha paga de {competencia_paga} não pode ser excluída.",
        )

    todas_parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    if len(todas_parcelas) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Este vale tem uma única parcela — exclua o vale inteiro (o lançamento de caixa também será removido).",
        )

    # Só as parcelas POSTERIORES (mesma ordem de competência) e ainda
    # pendentes entram na redistribuição — mesma regra de `editar_parcela_vale`.
    outras_pendentes = [
        p for p in todas_parcelas
        if p.id != parcela_id and p.competencia > parcela.competencia
        and not _vale_competencia_paga(session, vale.pessoa_id, [p.competencia], fazenda_id)
    ]

    if not confirmar:
        soma_atual = round(sum(p.valor for p in todas_parcelas), 2)
        raise HTTPException(status_code=409, detail={
            "mensagem": "Excluir esta parcela muda o valor total lançado do vale.",
            "valor_parcela": parcela.valor,
            "valor_vale": vale.valor_total,
            "soma_apos": round(soma_atual - parcela.valor, 2),
            "parcelas_pendentes_posteriores": len(outras_pendentes),
        })

    if acao == "redistribuir_igual":
        if not outras_pendentes:
            raise HTTPException(status_code=400, detail="Não há parcelas pendentes para redistribuir — escolha conceder.")
        valor_base = round(parcela.valor / len(outras_pendentes), 2)
        restante = parcela.valor
        for i, p in enumerate(outras_pendentes):
            acrescimo = valor_base if i < len(outras_pendentes) - 1 else round(restante, 2)
            restante = round(restante - acrescimo, 2)
            p.valor = round(p.valor + acrescimo, 2)
            session.add(p)
    elif acao != "conceder":
        raise HTTPException(status_code=400, detail="Informe a ação: conceder ou redistribuir_igual.")

    pessoa_id = vale.pessoa_id
    competencia_apagada = parcela.competencia
    session.delete(parcela)
    session.commit()

    # Inclui a competência apagada na reconciliação — senão a folha daquele
    # mês fica com o desconto fantasma (ela já não tem mais parcela nenhuma
    # apontando pra ela, mas o valor_vale/valor_liquido gravados na
    # FolhaPagamento ainda refletem o vale antes da exclusão).
    parcelas_restantes = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    competencias_afetadas = sorted({p.competencia for p in parcelas_restantes} | {competencia_apagada})
    _reconciliar_vale_competencias(session, pessoa_id, competencias_afetadas)
    session.commit()
    session.refresh(vale)

    soma_parcelas = round(sum(p.valor for p in parcelas_restantes), 2)
    return {
        **vale.model_dump(),
        "parcelas_detalhe": sorted(({**p.model_dump()} for p in parcelas_restantes), key=lambda p: p["competencia"]),
        "soma_parcelas_atual": soma_parcelas,
        "diverge_valor_pago": soma_parcelas != vale.valor_total,
        "diferenca_valor_pago": round(soma_parcelas - vale.valor_total, 2),
    }


def _impedimento_excluir_vale_funcionario(
    session: Session, vale: ValeFuncionario, parcelas: list[ValeParcela],
    conta: ContaGerencial | None, fazenda_id: int | None,
) -> str | None:
    """TODOS os motivos para recusar a exclusão de um vale de funcionário, em
    um lugar só — usado pela prévia da tela e pelo próprio DELETE, para os
    dois nunca discordarem (o dono não pode confirmar uma exclusão e só
    então descobrir que ela era proibida)."""
    # Vale que já sofreu "desconsiderar o mês"/"cancelar" não pode ser
    # apagado: o valor assumido já virou despesa da fazenda no Financeiro
    # (item de nota devolvido aos relatórios, ou lançamento reclassificado —
    # ver rh_vale_acoes.py::_assumir_no_financeiro), e apagar o vale aqui
    # apagaria junto o lançamento de caixa que sustenta aquela despesa,
    # sem desfazer nada do outro lado.
    if vale.status == "cancelado" or any(p.assumida_pela_fazenda for p in parcelas):
        return (
            "Este vale já teve valor assumido pela fazenda (mês desconsiderado ou vale cancelado) — "
            "a despesa correspondente já está no Financeiro e o vale não pode mais ser excluído."
        )
    # Parcela que já caiu em folha PAGA: o desconto foi feito de verdade e o
    # holerite daquele mês é recibo — apagar o vale faria o holerite mentir.
    competencia_paga = _vale_competencia_paga(
        session, vale.pessoa_id, [p.competencia for p in parcelas], fazenda_id,
    )
    if competencia_paga:
        return f"Vale já aplicado na folha paga de {competencia_paga} não pode ser excluído."
    # E, por último, o trabalho humano investido na saída de caixa — ver o
    # bloco EXCLUIR ≠ CANCELAR e `_impedimento_excluir_vale`.
    return _impedimento_excluir_vale(
        session, conta, vale.valor_total, LancamentoAnexo.vale_funcionario_id, vale.id,
        ALTERNATIVA_CANCELAR_VALE,
    )


@router.get("/vales/{vale_id}/exclusao")
def previa_exclusao_vale(
    vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """O que a tela mostra ANTES de perguntar "excluir?": o lançamento de
    caixa que vai junto (nomeado, com valor e data), o motivo de recusa
    quando há um, e a linha que ensina a porta certa quando a intenção era
    perdoar o vale, não apagá-lo. Ver o bloco EXCLUIR ≠ CANCELAR."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeFuncionario, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    pessoa = session.exec(
        select(Pessoa).where(Pessoa.id == vale.pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    conta = _conta_do_numero(session, vale.numero_lancamento_gerado, fazenda_id)
    return _previa_exclusao_vale(
        conta=conta,
        impedimento=_impedimento_excluir_vale_funcionario(session, vale, parcelas, conta, fazenda_id),
        titulo=f"Excluir o vale de {pessoa.nome if pessoa else 'funcionário'} de R$ {vale.valor_total:.2f}?",
        efeito="Os descontos já refletidos em folhas ainda não pagas serão revertidos.",
        alternativa=ALTERNATIVA_CANCELAR_VALE,
    )


@router.delete("/vales/{vale_id}")
def excluir_vale(
    vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Apaga o vale que NUNCA DEVERIA TER EXISTIDO (valor errado, pessoa
    errada, duplicado) e, com ele, a saída de caixa que ele criou. Apagar a
    conta JÁ PAGA é deliberado aqui — e só aqui: ver o bloco
    EXCLUIR ≠ CANCELAR sobre por que a trava de `_exigir_conta_nao_paga`
    (folha/férias/13º/guias) não vale para o vale, e por que a porta do vale
    que aconteceu mas não será mais cobrado é a ação "Cancelar o vale"."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeFuncionario, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    pessoa_id = vale.pessoa_id
    parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    # A conta agora vem por `_conta_do_numero`, que recorta a fazenda DENTRO
    # da consulta. Antes a busca era só por `numero_lancamento`: bastava um
    # número repetido entre tenants (ou um token legado sem a claim de
    # fazenda) para esta exclusão apagar lançamento de OUTRA fazenda.
    conta = _conta_do_numero(session, vale.numero_lancamento_gerado, fazenda_id)
    impedimento = _impedimento_excluir_vale_funcionario(session, vale, parcelas, conta, fazenda_id)
    if impedimento:
        raise HTTPException(status_code=400, detail=impedimento)
    competencias = [p.competencia for p in parcelas]
    # Remove também o lançamento (ContaGerencial) gerado para a saída de
    # caixa do vale — sem isso, excluir o vale deixaria um lançamento órfão
    # no extrato, sem vale nenhum por trás dele.
    if conta is not None:
        session.delete(conta)
    for p in parcelas:
        session.delete(p)
    # Zera o vínculo em qualquer LancamentoItem que apontava para este vale
    # (caminho inverso: usuário excluiu o vale direto no Relatório de vales,
    # não pelo checkbox do item) — sem isso ficaria FK pendurada e o item
    # sumido dos relatórios gerenciais para sempre (ver rules/vale_item.py).
    limpar_vinculo_de_itens(session, vale_funcionario_id=vale_id)
    session.delete(vale)
    session.commit()
    _reconciliar_vale_competencias(session, pessoa_id, competencias)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Comprovante de pagamento do vale (D7-D10 da Frente D, sessão de ajustes de
# tela) — reaproveita `LancamentoAnexo` (mesmo Storage/categoria "Comprovante"
# já usado no anexo de lançamento, ver financeiro.py) em vez de uma tabela
# nova: o mecanismo é idêntico, só o vínculo muda (`vale_funcionario_id`/
# `vale_avulso_id` em vez de `numero_lancamento` — ver o comentário no model,
# fazenda/models/financeiro.py). Cobre só `ValeFuncionario` e `ValeAvulso`; o
# terceiro "vale" do sistema (item de lançamento marcado como vale, ver
# rules/vale_item.py) já herda o anexo da própria nota financeira, então não
# precisa de rota nenhuma aqui.
#
# `tipo` ("funcionario" | "avulso") escolhe o modelo E a coluna de vínculo em
# LancamentoAnexo — resolvidos juntos por `_resolver_vale_comprovante` para
# as 4 rotas abaixo nunca divergirem sobre qual é qual.
# ---------------------------------------------------------------------------
_MODELOS_VALE_COMPROVANTE: dict[str, type] = {"funcionario": ValeFuncionario, "avulso": ValeAvulso}


def _resolver_vale_comprovante(session: Session, tipo: str, vale_id: int, fazenda_id: int | None):
    modelo = _MODELOS_VALE_COMPROVANTE.get(tipo)
    if modelo is None:
        raise HTTPException(status_code=400, detail="Tipo de vale inválido — use 'funcionario' ou 'avulso'")
    vale = session.get(modelo, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    coluna = LancamentoAnexo.vale_funcionario_id if tipo == "funcionario" else LancamentoAnexo.vale_avulso_id
    return vale, coluna


def _caminho_comprovante_vale(session: Session, fazenda_id: int | None, tipo: str, vale_id: int, coluna, nome_arquivo: str) -> str:
    """fazenda-X/vales/{tipo}/{vale_id}/0001_nome.ext — mesmo espírito
    sequencial de `_caminho_anexo_lancamento` (financeiro.py), sem depender
    de `numero_lancamento` (que aqui pode nem existir).

    BUG CORRIGIDO (mesmo defeito do anexo de Pessoa, relatado pelo dono em
    06/09/2026 e corrigido em `cadastro/pessoas.py::_caminho_anexo_pessoa`,
    depois em pedidos.py e financeiro.py; este módulo tinha a cópia): a
    sequência vinha de `1 + len(existentes)`, ou seja, da CONTAGEM de
    comprovantes vivos. Excluir um comprovante faz a contagem cair, então o
    próximo upload reaproveita um número que já está em uso; se o nome do
    arquivo também se repetir — que é a regra, não a exceção, no fluxo real
    "anexei o comprovante errado, apago e anexo o certo", em que o segundo
    envio traz o mesmo nome gerado pelo banco (comprovante.pdf, pix.pdf) — o
    caminho gerado é IDÊNTICO ao de um comprovante que ainda existe. O envio
    usa `x-upsert`, então o arquivo antigo é sobrescrito em silêncio e as
    DUAS linhas do banco passam a apontar para o mesmo objeto no Storage. A
    partir daí, excluir uma apaga o arquivo das duas, e a outra fica travada
    para sempre: o Storage responde 404 na exclusão, o endpoint devolvia 400
    e a linha nunca saía da tela.

    Agora a sequência sai do MAIOR número já usado nos caminhos do vale (não
    da contagem): número devolvido por uma exclusão nunca é reemitido
    enquanto sobrar qualquer comprovante, então dois comprovantes vivos
    jamais dividem o mesmo caminho.
    """
    pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}/vales/{tipo}/{vale_id}"
    existentes = session.exec(select(LancamentoAnexo).where(coluna == vale_id)).all()
    maior = 0
    for a in existentes:
        # "…/vales/funcionario/7/0003_pix.pdf" -> 3. Caminho antigo/fora do
        # padrão (ou nulo) simplesmente não entra na conta.
        prefixo = (a.caminho_storage or "").rsplit("/", 1)[-1].split("_", 1)[0]
        if prefixo.isdigit():
            maior = max(maior, int(prefixo))
    seq = 1 + max(maior, len(existentes))
    return f"{pasta}/{seq:04d}_{nome_seguro_storage(nome_arquivo)}"


@router.post("/vales/{tipo}/{vale_id}/comprovante", status_code=201)
async def anexar_comprovante_vale(
    tipo: str, vale_id: int, file: UploadFile,
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    _, coluna = _resolver_vale_comprovante(session, tipo, vale_id, fazenda_id)
    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_ANEXO:
        raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB — não é possível anexar")
    nome_arquivo = file.filename or "comprovante"
    caminho = _caminho_comprovante_vale(session, fazenda_id, tipo, vale_id, coluna, nome_arquivo)
    try:
        enviar_arquivo(caminho, conteudo, file.content_type or "application/octet-stream", bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    anexo = LancamentoAnexo(
        numero_lancamento=None,
        vale_funcionario_id=vale_id if tipo == "funcionario" else None,
        vale_avulso_id=vale_id if tipo == "avulso" else None,
        nome_arquivo=nome_arquivo,
        mime_type=file.content_type or "application/octet-stream",
        tamanho_bytes=len(conteudo),
        categoria="Comprovante",
        caminho_storage=caminho,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(anexo)
    session.commit()
    session.refresh(anexo)
    return {"id": anexo.id, "nome_arquivo": anexo.nome_arquivo}


@router.get("/vales/{tipo}/{vale_id}/comprovante")
def listar_comprovantes_vale(
    tipo: str, vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    _, coluna = _resolver_vale_comprovante(session, tipo, vale_id, fazenda_id)
    query = select(LancamentoAnexo).where(coluna == vale_id)
    if fazenda_id is not None:
        query = query.where(LancamentoAnexo.fazenda_id == fazenda_id)
    anexos = session.exec(query).all()
    return [
        {"id": a.id, "nome_arquivo": a.nome_arquivo, "mime_type": a.mime_type, "criado_em": a.criado_em.isoformat()}
        for a in sorted(anexos, key=lambda a: a.criado_em)
    ]


def _anexo_comprovante_vale(session: Session, anexo_id: int, fazenda_id: int | None) -> LancamentoAnexo:
    """Acha o anexo pelo id, exigindo que seja mesmo um comprovante DE VALE
    (um dos dois FKs preenchido) — sem essa checagem, `/vales/comprovante/{id}`
    poderia baixar/excluir qualquer anexo de lançamento da fazenda, coisa que
    não é dele: essa rota é só para o que foi anexado pelas duas rotas acima."""
    anexo = session.get(LancamentoAnexo, anexo_id)
    if (
        not anexo
        or (anexo.vale_funcionario_id is None and anexo.vale_avulso_id is None)
        or (anexo.fazenda_id != fazenda_id)
    ):
        raise HTTPException(status_code=404, detail="Comprovante não encontrado")
    return anexo


@router.get("/vales/comprovante/{anexo_id}")
def baixar_comprovante_vale(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = _anexo_comprovante_vale(session, anexo_id, fazenda_id)
    try:
        conteudo = baixar_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=conteudo, media_type=anexo.mime_type,
        headers={"Content-Disposition": f'inline; filename="{anexo.nome_arquivo}"'},
    )


@router.delete("/vales/comprovante/{anexo_id}")
def excluir_comprovante_vale(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Remove o comprovante anexado ao vale.

    BUG CORRIGIDO (mesmo defeito do anexo de Pessoa, relatado pelo dono em
    06/09/2026; este módulo tinha a cópia): qualquer falha do Supabase
    Storage ao apagar o arquivo virava 400 e ABORTAVA a exclusão da linha no
    banco. Arquivo que já não está lá (apagado à mão no painel do Supabase,
    caminho duplicado por causa do bug de sequência em
    `_caminho_comprovante_vale`, upload que falhou no meio) devolve 404 no
    delete — e o comprovante passava a ser IMPOSSÍVEL de tirar da tela: toda
    tentativa repetia o mesmo 400, para sempre, porque a causa era
    justamente o arquivo não existir mais.

    A linha do banco é o que o usuário enxerga e é ela que tem que sair. O
    arquivo no bucket é o subproduto: se a remoção dele falhar, no pior caso
    sobra um objeto órfão no Storage (invisível, sem nenhuma linha
    apontando), que é infinitamente melhor que um comprovante fantasma preso
    no vale.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = _anexo_comprovante_vale(session, anexo_id, fazenda_id)
    if anexo.caminho_storage:
        # Os comprovantes gravados ANTES da correção de
        # `_caminho_comprovante_vale` podem dividir o mesmo caminho com outro
        # anexo vivo. Apagar o objeto nesse caso derrubaria o download do
        # irmão que fica — só remove do bucket quando ninguém mais aponta
        # para lá. A busca é em LancamentoAnexo inteiro (não só nos
        # comprovantes de vale) porque o comprovante em lote do Financeiro
        # também referencia um arquivo só a partir de várias linhas.
        # O recorte por fazenda entra NA PRÓPRIA consulta (nunca num `if` em
        # volta dela): sem multi-fazenda provisionado vira `fazenda_id IS
        # NULL`, que é exatamente o conjunto de linhas desse ambiente. Anexo
        # de outra fazenda não é "irmão" de ninguém aqui.
        compartilhado = session.exec(
            select(LancamentoAnexo).where(
                LancamentoAnexo.fazenda_id == fazenda_id,
                LancamentoAnexo.caminho_storage == anexo.caminho_storage,
                LancamentoAnexo.id != anexo.id,
            )
        ).first()
        if not compartilhado:
            try:
                excluir_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
            except RuntimeError as exc:
                logger.warning(
                    "Comprovante %s do vale (funcionario=%s, avulso=%s): linha excluída mesmo com falha ao apagar o arquivo no Storage (%s): %s",
                    anexo.id, anexo.vale_funcionario_id, anexo.vale_avulso_id, anexo.caminho_storage, exc,
                )
    session.delete(anexo)
    session.commit()
    return {"excluido": True}



