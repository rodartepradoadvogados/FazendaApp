"""
Cadastro > Empreitada, Contrato, Diária e Vale avulso — trabalho contratado
pago por frequência/etapa (Empreitada), contrato com ou sem frequência fixa
(Contrato), diária com saldo devedor acumulado (Diária) e o adiantamento
avulso comum às três (Vale avulso). Também expõe
`GET /folha-pagamento-unificada`, o ledger consolidado de TODOS os
lançamentos de RH (funcionário, empreita, contrato, diária) — por isso
importa `listar_folha_pagamento`/`_competencia_seguinte` de rh_folha.py.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, exigir_admin, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, ContaCorrente, ContaGerencial, Contrato, ContratoParcela, DecimoTerceiro, Diaria, DiariaAuditoria,
    DiariaDia, DiariaPagamento, Empreitada, EmpreitadaEtapa, EmpreitadaParcela, FeriasFuncionario, LancamentoAnexo,
    ParametroDiariaPadrao, Pessoa, Usuario, ValeAvulso, ValeAvulsoAbatimento,
)
from fazenda.api.routers.financeiro import _proximo_numero_lancamento, rotulo_conta_corrente
from fazenda.rules import holerite
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.vale_item import limpar_vinculo_de_itens, origens_lancamento_por_vale

from .rh_folha import (
    ALTERNATIVA_VALE_AVULSO,
    STATUS_CANCELADO_RESCISAO,
    _competencia_seguinte,
    _conta_do_numero,
    _impedimento_excluir_vale,
    _previa_exclusao_vale,
    _resolver_conta_corrente,
    listar_folha_pagamento,
)

router = APIRouter()

PARCELA_DECIMO_ROTULO = {"unica": "parcela única", "primeira": "1ª parcela", "segunda": "2ª parcela"}


def _brl(valor: float) -> str:
    """R$ 1.234,56 — formatação usada só nas referências dos recibos daqui."""
    return "R$ " + f"{valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _detalhe_ferias(f: FeriasFuncionario) -> list[dict]:
    """
    Discriminação do recibo de férias nas mesmas quatro colunas do holerite.
    A REFERÊNCIA aqui não precisa ser inventada: dias gozados, dias de direito
    e período aquisitivo já estão gravados no modelo — é o mesmo padrão de
    `RescisaoFuncionario`, que guarda os metadados junto do valor e por isso é
    o único documento do sistema que já saía completo.
    """
    aquisitivo = (
        f"aquisitivo {f.periodo_aquisitivo_inicio.strftime('%d/%m/%Y')}"
        f" a {f.periodo_aquisitivo_fim.strftime('%d/%m/%Y')}"
    )
    linhas = [holerite.linha(
        "ferias", "Férias", f.valor_ferias, "Férias",
        f"{f.dias_gozados} de {f.dias_direito} dias · {aquisitivo}",
        provento=round(f.valor_ferias, 2),
    )]
    if f.valor_terco_constitucional:
        linhas.append(holerite.linha(
            "terco", "1/3 constitucional", f.valor_terco_constitucional,
            "1/3 constitucional", f"sobre {f.dias_gozados} dias de férias",
            provento=round(f.valor_terco_constitucional, 2),
        ))
    # O abono pecuniário (dias vendidos, art. 143 CLT) está embutido em
    # valor_total pelo cálculo; só vira linha quando de fato houve venda de
    # dias — senão seria um zero decorativo num documento. Desde a migração
    # e0b7c3a91d24 o valor é PERSISTIDO em `valor_abono` (antes era calculado
    # e jogado fora); a subtração fica só como fallback para registro antigo
    # cuja coluna não pôde ser reconstituída.
    abono = f.valor_abono if f.valor_abono else round(f.valor_total - f.valor_ferias - f.valor_terco_constitucional, 2)
    if f.abono_pecuniario_dias and abs(abono) > 0.001:
        linhas.append(holerite.linha(
            "abono", "Abono pecuniário", abono, "Abono pecuniário",
            f"{f.abono_pecuniario_dias} dias vendidos (art. 143 CLT), com 1/3",
            provento=abono,
        ))
    linhas.append(holerite.linha("liquido", "Valor total", f.valor_total, "Total", ""))
    return linhas


def _detalhe_decimo_terceiro(d: DecimoTerceiro) -> list[dict]:
    """
    Discriminação do recibo de 13º. Ressalva assumida: o modelo guarda
    `valor_inss`/`valor_ir` mas NÃO guarda os percentuais deles — então a
    referência da retenção diz "valor informado" em vez de inventar um
    percentual a partir do valor (mesma regra do INSS/IR da folha).
    """
    # A referência diz de onde saiu o valor DESTA parcela: quando ela é só
    # uma fatia do 13º do ano (1ª parcela = adiantamento de até 50%; 2ª = o
    # saldo), o integral e o já adiantado aparecem no texto — sem isso o
    # recibo mostrava uma metade sem dizer que era metade.
    referencia = f"{d.meses_trabalhados}/12 avos de {d.ano} · {PARCELA_DECIMO_ROTULO.get(d.parcela, d.parcela)}"
    integral = d.valor_integral or d.valor_bruto
    if abs(integral - d.valor_bruto) > 0.001:
        if d.parcela == "primeira":
            referencia += f" · adiantamento sobre 13º integral de {_brl(integral)}"
        else:
            referencia += (
                f" · 13º integral {_brl(integral)} − adiantamento {_brl(round(integral - d.valor_bruto, 2))}"
            )
    linhas = [holerite.linha(
        "bruto", "13º salário bruto", d.valor_bruto, "13º salário",
        referencia,
        provento=round(d.valor_bruto, 2),
    )]
    for tipo, rotulo, valor in (("inss", "INSS", d.valor_inss), ("ir", "IR", d.valor_ir)):
        if not valor:
            continue
        linhas.append(holerite.linha(
            tipo, rotulo, -valor, rotulo, "Valor informado, sem percentual",
            desconto=round(valor, 2),
        ))
    linhas.append(holerite.linha("liquido", "Valor líquido", d.valor_liquido, "Líquido", ""))
    return linhas


@router.get("/folha-pagamento-unificada")
def listar_folha_pagamento_unificada(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Visão consolidada de TODOS os lançamentos de folha — funcionário, empreita,
    contrato, diária e férias/13º salário — num único ledger ordenável/
    filtrável por vencimento, priorizando pendências (destacando as vencidas).
    `origem_tipo` (=`tipo`) + `origem_id` apontam para o registro de origem só
    para permitir excluir lançamentos ainda pendentes; a edição continua nas
    telas específicas.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    linhas: list[dict] = []

    for r in listar_folha_pagamento(session, fazenda_id=fazenda_id):
        linhas.append({
            "tipo": "funcionario", "origem_id": r["id"], "origem_subtipo": "folha",
            "pessoa_id": r["pessoa_id"], "pessoa_nome": r["pessoa_nome"],
            "descricao": f"Folha — {r['competencia']}",
            "valor": r["valor_liquido"],
            "data_vencimento": r["data_vencimento"],
            "data_pagamento": r["data_pagamento"],
            "status": r["status"],
            "pode_excluir": r["status"] == "pendente",
            # O discriminado JÁ era calculado aqui e descartado ao montar este
            # dict — por isso a tela de Contas nunca teve o que mostrar ao
            # clicar num nome e virou "a mesma tabela sem o clique". Passa a
            # viajar junto, com a competência e o nº do lançamento que ligam a
            # linha ao extrato.
            "competencia": r["competencia"],
            "detalhe": r["detalhe"],
            # As parcelas de vale que a FAZENDA assumiu naquele mês — campo
            # SEPARADO de `detalhe`, nunca dentro dele, exatamente como sai de
            # `GET /folha-pagamento` (ver `_vale_assumido_folha`). Sem elas,
            # quem abre o holerite aqui via o desconto de vale sumir do
            # documento sem explicação nenhuma: esta tela é só consulta e não
            # tem o painel de ações da tela de fechamento, onde a explicação
            # já aparecia.
            #
            # A trava é a mesma do #722, e vale igual aqui: a linha é INERTE
            # (provento/desconto nulos, `valor` zero) e não entra em soma
            # nenhuma — nem em `totais`, nem no líquido, nem no PDF/Excel do
            # holerite, que leem `detalhe`. Só explica.
            "vale_assumido": r["vale_assumido"],
            "totais": r["totais"],
            "bases": r["bases"],
            "numero_lancamento_gerado": r["numero_lancamento_gerado"],
            "observacao": r["observacao"],
        })

    query_empreitadas = select(Empreitada)
    query_parcelas_empreita = select(EmpreitadaParcela)
    query_etapas_empreita = select(EmpreitadaEtapa).where(EmpreitadaEtapa.concluida == True)  # noqa: E712
    if fazenda_id is not None:
        query_empreitadas = query_empreitadas.where(Empreitada.fazenda_id == fazenda_id)
        query_parcelas_empreita = query_parcelas_empreita.where(EmpreitadaParcela.fazenda_id == fazenda_id)
        query_etapas_empreita = query_etapas_empreita.where(EmpreitadaEtapa.fazenda_id == fazenda_id)
    empreitadas = {e.id: e for e in session.exec(query_empreitadas).all()}
    parcelas_empreita = session.exec(query_parcelas_empreita).all()
    etapas_empreita = session.exec(query_etapas_empreita).all()
    numeros_empreita = [p.numero_lancamento_gerado for p in parcelas_empreita if p.numero_lancamento_gerado] + [
        et.numero_lancamento_gerado for et in etapas_empreita if et.numero_lancamento_gerado
    ]
    contas_empreita = {
        c.numero_lancamento: c
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros_empreita))).all()
    } if numeros_empreita else {}
    for p in parcelas_empreita:
        e = empreitadas.get(p.empreitada_id)
        if not e:
            continue
        conta = contas_empreita.get(p.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "empreita", "origem_id": p.id, "origem_subtipo": "parcela",
            "pessoa_id": e.pessoa_id, "pessoa_nome": pessoas.get(e.pessoa_id, "—"),
            "descricao": f"Empreita — {e.descricao}",
            "valor": p.valor,
            "data_vencimento": p.data_vencimento,
            "data_pagamento": conta.data_pagamento if conta else None,
            "status": "pago" if pago else "pendente",
            "pode_excluir": not pago,
        })
    for et in etapas_empreita:
        e = empreitadas.get(et.empreitada_id)
        if not e:
            continue
        conta = contas_empreita.get(et.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "empreita", "origem_id": et.id, "origem_subtipo": "etapa",
            "pessoa_id": e.pessoa_id, "pessoa_nome": pessoas.get(e.pessoa_id, "—"),
            "descricao": f"Empreita — {e.descricao} — etapa: {et.nome}",
            "valor": et.valor,
            "data_vencimento": conta.data_vencimento if conta else None,
            "data_pagamento": conta.data_pagamento if conta else None,
            "status": "pago" if pago else "pendente",
            "pode_excluir": False,
        })

    query_contratos = select(Contrato)
    query_parcelas_contrato = select(ContratoParcela)
    if fazenda_id is not None:
        query_contratos = query_contratos.where(Contrato.fazenda_id == fazenda_id)
        query_parcelas_contrato = query_parcelas_contrato.where(ContratoParcela.fazenda_id == fazenda_id)
    contratos = {c.id: c for c in session.exec(query_contratos).all()}
    parcelas_contrato = session.exec(query_parcelas_contrato).all()
    numeros_contrato = [p.numero_lancamento_gerado for p in parcelas_contrato if p.numero_lancamento_gerado]
    contas_contrato = {
        c.numero_lancamento: c
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros_contrato))).all()
    } if numeros_contrato else {}
    for p in parcelas_contrato:
        c = contratos.get(p.contrato_id)
        if not c:
            continue
        conta = contas_contrato.get(p.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        linhas.append({
            "tipo": "contrato", "origem_id": p.id, "origem_subtipo": "parcela",
            "pessoa_id": c.pessoa_id, "pessoa_nome": pessoas.get(c.pessoa_id, "—"),
            "descricao": f"Contrato — {c.descricao}",
            "valor": p.valor,
            "data_vencimento": p.data_vencimento,
            "data_pagamento": conta.data_pagamento if conta else None,
            "status": "pago" if pago else "pendente",
            "pode_excluir": not pago,
        })

    query_diarias = select(Diaria)
    query_pagamentos_diaria = select(DiariaPagamento)
    if fazenda_id is not None:
        query_diarias = query_diarias.where(Diaria.fazenda_id == fazenda_id)
        query_pagamentos_diaria = query_pagamentos_diaria.where(DiariaPagamento.fazenda_id == fazenda_id)
    diarias = {d.id: d for d in session.exec(query_diarias).all()}

    # Conta a pagar emitida no encerramento do período de uma diarista (ver
    # `encerrar_diaria`) — é uma pendência de RH como qualquer outra e
    # precisava aparecer neste ledger; sem ela, o único lugar do módulo RH
    # que mostrava diária eram os pagamentos JÁ feitos, ou seja, exatamente o
    # que não corre risco de ser esquecido.
    numeros_encerramento = [d.numero_lancamento_gerado for d in diarias.values() if d.numero_lancamento_gerado]
    contas_encerramento = {
        c.numero_lancamento: c
        for c in session.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento.in_(numeros_encerramento),
                ContaGerencial.fazenda_id == fazenda_id,
            )
        ).all()
    } if numeros_encerramento else {}
    for d in diarias.values():
        conta = contas_encerramento.get(d.numero_lancamento_gerado)
        if conta is None:
            continue
        pago = conta.valor_pago is not None
        linhas.append({
            "tipo": "diaria", "origem_id": d.id, "origem_subtipo": "encerramento",
            "pessoa_id": d.pessoa_id, "pessoa_nome": pessoas.get(d.pessoa_id, "—"),
            "descricao": conta.descricao or "Diária — acerto do período",
            "valor": conta.valor_total,
            "data_vencimento": conta.data_vencimento,
            "data_pagamento": conta.data_pagamento,
            "status": "pago" if pago else "pendente",
            # Excluir por aqui removeria a conta e deixaria a diária
            # apontando para um lançamento que não existe mais — o caminho
            # é reabrir o período (que apaga a cobrança junto).
            "pode_excluir": False,
        })

    for pg in session.exec(query_pagamentos_diaria).all():
        d = diarias.get(pg.diaria_id)
        if not d:
            continue
        linhas.append({
            "tipo": "diaria", "origem_id": pg.id, "origem_subtipo": "pagamento",
            "pessoa_id": d.pessoa_id, "pessoa_nome": pessoas.get(d.pessoa_id, "—"),
            "descricao": "Diária",
            "valor": pg.valor,
            "data_vencimento": pg.data_pagamento,
            "data_pagamento": pg.data_pagamento,
            "status": "pago",
            "pode_excluir": False,
        })

    # Férias e 13º salário — mesmo padrão de Empreita/Contrato: o vencimento e
    # o status de pagamento vêm da ContaGerencial gerada junto (numero_
    # lancamento_gerado), já que os dois modelos não têm data_vencimento
    # própria. Faltavam neste ledger unificado (item aprovado da proposta de
    # Folha de Pagamento) — o filtro "Todos"/"Férias / 13º" agora inclui os dois.
    query_ferias = select(FeriasFuncionario)
    query_decimo = select(DecimoTerceiro)
    if fazenda_id is not None:
        query_ferias = query_ferias.where(FeriasFuncionario.fazenda_id == fazenda_id)
        query_decimo = query_decimo.where(DecimoTerceiro.fazenda_id == fazenda_id)
    ferias = session.exec(query_ferias).all()
    decimos = session.exec(query_decimo).all()
    numeros_ferias_decimo = [f.numero_lancamento_gerado for f in ferias if f.numero_lancamento_gerado] + [
        d.numero_lancamento_gerado for d in decimos if d.numero_lancamento_gerado
    ]
    contas_ferias_decimo = {
        c.numero_lancamento: c
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros_ferias_decimo))).all()
    } if numeros_ferias_decimo else {}
    for f in ferias:
        conta = contas_ferias_decimo.get(f.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        # Cancelado pela rescisão é um terceiro estado, não "pendente": o
        # registro fica visível (nada é apagado) mas não é mais uma conta a
        # pagar — o valor foi para dentro das verbas rescisórias.
        cancelado = f.status == STATUS_CANCELADO_RESCISAO
        detalhe = _detalhe_ferias(f)
        linhas.append({
            "tipo": "ferias_decimo", "origem_id": f.id, "origem_subtipo": "ferias",
            "pessoa_id": f.pessoa_id, "pessoa_nome": pessoas.get(f.pessoa_id, "—"),
            "descricao": f"Férias — {f.data_inicio_gozo.isoformat()} a {f.data_fim_gozo.isoformat()}",
            "valor": f.valor_total,
            "data_vencimento": conta.data_vencimento if conta else None,
            "data_pagamento": conta.data_pagamento if conta else f.data_pagamento,
            "status": "pago" if pago else (STATUS_CANCELADO_RESCISAO if cancelado else "pendente"),
            "pode_excluir": not pago,
            "detalhe": detalhe,
            "totais": holerite.totais_holerite(detalhe),
            "numero_lancamento_gerado": f.numero_lancamento_gerado,
            "observacao": f.observacao,
        })
    for d in decimos:
        conta = contas_ferias_decimo.get(d.numero_lancamento_gerado)
        pago = bool(conta and conta.valor_pago is not None)
        cancelado = d.status == STATUS_CANCELADO_RESCISAO  # ver comentário acima
        detalhe = _detalhe_decimo_terceiro(d)
        linhas.append({
            "tipo": "ferias_decimo", "origem_id": d.id, "origem_subtipo": "decimo_terceiro",
            "pessoa_id": d.pessoa_id, "pessoa_nome": pessoas.get(d.pessoa_id, "—"),
            "descricao": f"13º salário — {d.ano} ({d.parcela})",
            "valor": d.valor_liquido,
            "data_vencimento": conta.data_vencimento if conta else None,
            "data_pagamento": conta.data_pagamento if conta else d.data_pagamento,
            "status": "pago" if pago else (STATUS_CANCELADO_RESCISAO if cancelado else "pendente"),
            "pode_excluir": not pago,
            "detalhe": detalhe,
            "totais": holerite.totais_holerite(detalhe),
            "numero_lancamento_gerado": d.numero_lancamento_gerado,
            "observacao": d.observacao,
        })

    hoje = date.today()
    for linha in linhas:
        linha["vencido"] = bool(
            linha["status"] == "pendente" and linha["data_vencimento"] and linha["data_vencimento"] < hoje
        )

    # Prioriza pendente-vencido, depois pendente, depois pago; dentro de cada
    # grupo, o vencimento mais próximo primeiro.
    def _chave_prioridade(linha: dict):
        grupo = 0 if linha["vencido"] else (1 if linha["status"] == "pendente" else 2)
        return (grupo, linha["data_vencimento"] or date.max)

    linhas.sort(key=_chave_prioridade)
    return linhas




# ---------------------------------------------------------------------------
# Empreitada — trabalho contratado com um empreiteiro (Financeiro > Ações >
# Folha de Pagamento > Empreita). Paga por frequência fixa (parcelas editáveis,
# mesmo padrão do parcelamento do lançamento financeiro) ou por etapa
# concluída (cada etapa gera a conta a pagar no dia 1º do mês seguinte).
# ---------------------------------------------------------------------------
FORMAS_PAGAMENTO_FREQUENCIA = ["mensal", "semanal", "quinzenal"]
# Pagamento único numa data fixa (não recorrente) — "ao final da empreita" ou
# "no início da empreita". O frontend pede só a data e monta 1 parcela com o
# valor_total inteiro; entram no mesmo fluxo de `dados.parcelas` que mensal/
# semanal/quinzenal (ver FORMAS_PAGAMENTO_PARCELA abaixo).
FORMAS_PAGAMENTO_DATA_UNICA = ["inicio_empreita", "fim_empreita"]
FORMAS_PAGAMENTO_PARCELA = FORMAS_PAGAMENTO_FREQUENCIA + FORMAS_PAGAMENTO_DATA_UNICA
TIPOS_PAGAMENTO_EMPREITADA = FORMAS_PAGAMENTO_PARCELA + ["por_etapa"]


class EmpreitadaParcelaIn(BaseModel):
    data_vencimento: date
    valor: float


class EmpreitadaEtapaIn(BaseModel):
    nome: str
    valor: float


class EmpreitadaIn(BaseModel):
    pessoa_id: int
    descricao: str
    valor_total: float
    tipo_pagamento: str  # mensal | semanal | quinzenal | inicio_empreita | fim_empreita | por_etapa
    observacao: str | None = None
    # Preenchido quando tipo_pagamento é mensal/semanal/quinzenal (parcelamento
    # calculado e editável no frontend, mesmo padrão do Financeiro) ou
    # início/fim da empreita (1 única parcela, na data informada, valor cheio).
    parcelas: list[EmpreitadaParcelaIn] = []
    # Preenchido quando tipo_pagamento == "por_etapa" — nome + valor de cada
    # etapa (dividido proporcionalmente ou lançado específico, editável).
    etapas: list[EmpreitadaEtapaIn] = []
    centro_custo: str = "Pecuária Leiteira"


def _abatimentos_de_vale_por_item(
    session: Session, item_tipo: str, item_ids: list[int], fazenda_id: int | None,
) -> dict[int, float]:
    """Quanto de vale avulso já foi abatido de cada parcela/etapa
    (`ValeAvulsoAbatimento`), por item.

    Serve para a tela mostrar SEPARADAMENTE o bruto contratado e o desconto
    que virou o valor a pagar. Antes só existia o líquido: quando o
    empreiteiro dizia "mas a parcela era R$ 2.000", não havia nada na tela
    que explicasse o R$ 1.500 — a diferença tinha que ser deduzida abrindo o
    relatório de vales.

    Filtra por `fazenda_id` sem o `if fazenda_id is not None` tolerante que
    o resto deste arquivo ainda usa: consulta nova não repete furo antigo."""
    if not item_ids:
        return {}
    linhas = session.exec(
        select(ValeAvulsoAbatimento).where(
            ValeAvulsoAbatimento.item_tipo == item_tipo,
            ValeAvulsoAbatimento.item_id.in_(item_ids),
            ValeAvulsoAbatimento.fazenda_id == fazenda_id,
        )
    ).all()
    total: dict[int, float] = {}
    for ab in linhas:
        total[ab.item_id] = round(total.get(ab.item_id, 0.0) + ab.valor_abatido, 2)
    return total


def _serializar_empreitada(session: Session, e: Empreitada) -> dict:
    parcelas = session.exec(
        select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == e.id).order_by(EmpreitadaParcela.data_vencimento)
    ).all()
    etapas = session.exec(
        select(EmpreitadaEtapa).where(EmpreitadaEtapa.empreitada_id == e.id).order_by(EmpreitadaEtapa.ordem, EmpreitadaEtapa.id)
    ).all()
    numeros = [n for n in [p.numero_lancamento_gerado for p in parcelas] + [et.numero_lancamento_gerado for et in etapas] if n]
    pagos = set()
    if numeros:
        contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all()
        pagos = {c.numero_lancamento for c in contas if c.valor_pago is not None}
    abatido_parcela = _abatimentos_de_vale_por_item(session, "empreitada_parcela", [p.id for p in parcelas], e.fazenda_id)
    abatido_etapa = _abatimentos_de_vale_por_item(session, "empreitada_etapa", [et.id for et in etapas], e.fazenda_id)
    return {
        **e.model_dump(),
        # `valor_contratado` sai CRU (pode vir None em parcela anterior à
        # migração d4a1f6c2b9e7 criada fora da API): a tela mostra "—" em vez
        # de repetir o líquido no lugar do bruto — inventar um "contratado"
        # igual ao "a pagar" é exatamente o tipo de número que a pessoa
        # acredita e que não é verdade.
        "parcelas": [
            {
                **p.model_dump(),
                "status": "pago" if p.numero_lancamento_gerado in pagos else "pendente",
                "valor_abatido_vales": abatido_parcela.get(p.id, 0.0),
            }
            for p in parcelas
        ],
        "etapas": [
            {
                **et.model_dump(),
                "status_pagamento": "pago" if et.numero_lancamento_gerado in pagos else "pendente",
                "valor_abatido_vales": abatido_etapa.get(et.id, 0.0),
            }
            for et in etapas
        ],
        "vales": _listar_vales_avulsos(session, "empreitada", e.id),
    }


@router.get("/empreitadas")
def listar_empreitadas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(Empreitada)
    if fazenda_id is not None:
        query = query.where(Empreitada.fazenda_id == fazenda_id)
    empreitadas = session.exec(query.order_by(Empreitada.criado_em.desc())).all()
    return [{**_serializar_empreitada(session, e), "pessoa_nome": pessoas.get(e.pessoa_id, "—")} for e in empreitadas]


@router.post("/empreitadas")
def criar_empreitada(
    dados: EmpreitadaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.tipo_pagamento not in TIPOS_PAGAMENTO_EMPREITADA:
        raise HTTPException(status_code=400, detail="Tipo de pagamento inválido")
    if dados.tipo_pagamento in FORMAS_PAGAMENTO_PARCELA and not dados.parcelas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma parcela para o pagamento por frequência")
    if dados.tipo_pagamento == "por_etapa" and not dados.etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa")

    empreitada = Empreitada(
        pessoa_id=dados.pessoa_id, descricao=dados.descricao, valor_total=dados.valor_total,
        tipo_pagamento=dados.tipo_pagamento, observacao=dados.observacao, usuario_id=user.id,
        centro_custo=dados.centro_custo, fazenda_id=fazenda_id,
    )
    session.add(empreitada)
    session.commit()
    session.refresh(empreitada)

    if dados.tipo_pagamento in FORMAS_PAGAMENTO_PARCELA:
        # `numero`/`numero_total` nascem aqui e nunca mais mudam — nem quando
        # uma parcela é excluída (a numeração fica com buraco de propósito:
        # renumerar quebraria toda referência já impressa em recibo). E
        # `valor_contratado` guarda o bruto acordado agora, antes de qualquer
        # vale abater `valor`.
        total_parcelas = len(dados.parcelas)
        for i, parcela in enumerate(dados.parcelas, start=1):
            numero_lancamento = _proximo_numero_lancamento(session, parcela.data_vencimento.year)
            session.add(EmpreitadaParcela(
                empreitada_id=empreitada.id, data_vencimento=parcela.data_vencimento, valor=parcela.valor,
                numero=i, numero_total=total_parcelas, valor_contratado=parcela.valor,
                numero_lancamento_gerado=numero_lancamento, fazenda_id=fazenda_id,
            ))
            session.add(ContaGerencial(
                numero_lancamento=numero_lancamento,
                descricao=f"Empreita — {pessoa.nome} ({dados.descricao})",
                data_vencimento=parcela.data_vencimento,
                data_competencia=parcela.data_vencimento.replace(day=1),
                fornecedor_cliente=pessoa.nome,
                tipo_documento="Empreitada",
                centro_custo=dados.centro_custo,
                valor_total=parcela.valor,
                parcela_num=1, parcela_total=1,
                tipo="despesa", origem="auto",
                fazenda_id=fazenda_id,
            ))
    else:
        for i, etapa in enumerate(dados.etapas):
            session.add(EmpreitadaEtapa(
                empreitada_id=empreitada.id, nome=etapa.nome, valor=etapa.valor, ordem=i, fazenda_id=fazenda_id,
            ))
    session.commit()
    return _serializar_empreitada(session, empreitada)


@router.put("/empreitadas/{empreitada_id}/etapas/{etapa_id}/concluir")
def concluir_etapa_empreitada(
    empreitada_id: int, etapa_id: int, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Marca uma etapa como concluída e lança a conta a pagar correspondente no
    dia 1º do mês seguinte — cai automaticamente na Agenda (Gestão/Financeiro,
    a partir da própria data_vencimento da conta) e em Contas a Pagar, para
    análise/pagamento.
    """
    etapa = session.get(EmpreitadaEtapa, etapa_id)
    if not etapa or etapa.empreitada_id != empreitada_id or (etapa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Etapa não encontrada")
    if etapa.concluida:
        raise HTTPException(status_code=400, detail="Etapa já concluída")
    empreitada = session.get(Empreitada, empreitada_id)
    pessoa = session.get(Pessoa, empreitada.pessoa_id)

    hoje = date.today()
    proximo = _competencia_seguinte(hoje.strftime("%Y-%m"))
    ano, mes = (int(x) for x in proximo.split("-"))
    data_analise = date(ano, mes, 1)
    numero_lancamento = _proximo_numero_lancamento(session, ano)

    etapa.concluida = True
    etapa.data_conclusao = hoje
    etapa.numero_lancamento_gerado = numero_lancamento
    session.add(etapa)
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Empreita — {pessoa.nome} ({empreitada.descricao}) — etapa: {etapa.nome}",
        data_vencimento=data_analise,
        data_competencia=data_analise,
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Empreitada",
        centro_custo=empreitada.centro_custo,
        valor_total=etapa.valor,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        fazenda_id=fazenda_id,
    ))
    # Autoflush reflete etapa.concluida=True antes desta consulta — se não
    # sobrar nenhuma etapa pendente, a empreitada como um todo está concluída.
    etapas_pendentes = session.exec(
        select(EmpreitadaEtapa).where(EmpreitadaEtapa.empreitada_id == empreitada_id, EmpreitadaEtapa.concluida == False)  # noqa: E712
    ).all()
    if not etapas_pendentes:
        empreitada.status = "concluida"
        session.add(empreitada)
    session.commit()
    return _serializar_empreitada(session, empreitada)


@router.delete("/empreitadas/parcelas/{parcela_id}")
def excluir_parcela_empreitada(
    parcela_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(EmpreitadaParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Parcela de empreitada não encontrada")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado], fazenda_id):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser excluída aqui — exclua em Lançamentos > Excluir lançamento.")
    # `_conta_do_numero` (rh_folha.py) recorta a fazenda DENTRO da consulta:
    # o número do lançamento é sequencial por ano, não é chave global, e aqui
    # se APAGA o lançamento — sem o recorte, um número repetido numa base
    # importada levaria embora a conta a pagar de outro inquilino.
    conta = _conta_do_numero(session, parcela.numero_lancamento_gerado, fazenda_id)
    if conta:
        session.delete(conta)
    session.delete(parcela)
    session.commit()
    return {"ok": True}


class ParcelaEditIn(BaseModel):
    data_vencimento: date
    valor: float


def _sincronizar_conta_parcela(
    session: Session, numero_lancamento: str | None, data_vencimento: date, valor: float,
    fazenda_id: int | None,
) -> None:
    """Mantém o lançamento gerado (ContaGerencial) alinhado após editar/
    redistribuir uma parcela de Empreitada/Contrato — só toca contas ainda
    não pagas (parcela paga é bloqueada antes de chegar aqui).

    `fazenda_id` é obrigatório e vem do endpoint (`get_fazenda_atual_id` +
    `fazenda_id_seguro`), nunca deduzido aqui: a busca é por
    `_conta_do_numero`, que filtra a fazenda dentro do `select`. O número do
    lançamento não identifica o inquilino, e esta função REESCREVE vencimento
    e valor de conta a pagar — com dois números iguais em fazendas diferentes,
    editar a parcela de uma remarcaria a dívida da outra."""
    conta = _conta_do_numero(session, numero_lancamento, fazenda_id)
    if conta and conta.valor_pago is None:
        conta.data_vencimento = data_vencimento
        conta.data_competencia = data_vencimento.replace(day=1)
        conta.valor_total = valor
        session.add(conta)


def _reajustar_valor_contratado(session: Session, parcela, item_tipo: str) -> None:
    """Recoloca o bruto contratado no lugar depois de uma EDIÇÃO MANUAL da
    parcela (`PUT .../parcelas/{id}`): o que a tela edita é o valor A PAGAR,
    então o bruto vira esse valor mais o que já foi adiantado em vale.
    Renegociar a parcela para R$ 1.800 com R$ 500 de vale já abatido
    significa que o acordo passou a ser R$ 2.300 bruto — e é isso que a
    coluna "Contratado" precisa dizer.

    A REDISTRIBUIÇÃO não chama esta função de propósito (ver
    `_redistribuir_parcelas_pendentes` logo abaixo)."""
    abatido = _abatimentos_de_vale_por_item(session, item_tipo, [parcela.id], parcela.fazenda_id).get(parcela.id, 0.0)
    parcela.valor_contratado = round(parcela.valor + abatido, 2)


def _redistribuir_parcelas_pendentes(session: Session, pendentes: list, fazenda_id: int | None) -> None:
    """Redivide igualmente o total das parcelas pendentes informadas (mantendo
    as datas de vencimento de cada uma), ajustando o arredondamento na
    última para o somatório bater exatamente com o total original.

    NÃO toca em `valor_contratado`: redistribuir é remanejar entre parcelas o
    que já foi contratado, não renegociar o contrato. É por isso, aliás, que
    `valor_contratado` teve que virar coluna: quem tentasse reconstruir o
    bruto como `valor + Σ abatimentos` acertaria antes da redistribuição e
    erraria depois dela, porque ela reescreve `valor` sem tocar em nenhum
    `ValeAvulsoAbatimento`."""
    if len(pendentes) < 2:
        raise HTTPException(status_code=400, detail="É preciso ao menos 2 parcelas pendentes para redistribuir.")
    total = round(sum(p.valor for p in pendentes), 2)
    valor_base = round(total / len(pendentes), 2)
    restante = total
    for i, p in enumerate(pendentes):
        valor = valor_base if i < len(pendentes) - 1 else round(restante, 2)
        restante = round(restante - valor, 2)
        p.valor = valor
        session.add(p)
        _sincronizar_conta_parcela(session, p.numero_lancamento_gerado, p.data_vencimento, valor, fazenda_id)


@router.put("/empreitadas/parcelas/{parcela_id}")
def atualizar_parcela_empreitada(
    parcela_id: int, dados: ParcelaEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(EmpreitadaParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Parcela de empreitada não encontrada")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor da parcela deve ser positivo")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado], fazenda_id):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser editada aqui — edite em Lançamentos > Financeiro.")
    parcela.data_vencimento = dados.data_vencimento
    parcela.valor = dados.valor
    _reajustar_valor_contratado(session, parcela, "empreitada_parcela")
    session.add(parcela)
    _sincronizar_conta_parcela(session, parcela.numero_lancamento_gerado, dados.data_vencimento, dados.valor, fazenda_id)
    session.commit()
    empreitada = session.get(Empreitada, parcela.empreitada_id)
    return _serializar_empreitada(session, empreitada)


@router.post("/empreitadas/{empreitada_id}/parcelas/redistribuir")
def redistribuir_parcelas_empreitada(
    empreitada_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Redivide igualmente o valor total ainda pendente entre as parcelas
    pendentes da empreitada (ex.: após um vale abater desproporcionalmente
    uma única parcela, redistribui o saldo entre as próximas)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    empreitada = session.get(Empreitada, empreitada_id)
    if not empreitada or (empreitada.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Empreitada não encontrada")
    parcelas = session.exec(
        select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada_id).order_by(EmpreitadaParcela.data_vencimento)
    ).all()
    pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in parcelas if p.numero_lancamento_gerado], fazenda_id)
    pendentes = [p for p in parcelas if p.numero_lancamento_gerado not in pagos]
    _redistribuir_parcelas_pendentes(session, pendentes, fazenda_id)
    session.commit()
    return _serializar_empreitada(session, empreitada)


# ---------------------------------------------------------------------------
# Contrato — valor total pago por frequência fixa (parcelas editáveis, mesmo
# padrão do Financeiro) ou, sem frequência definida, com lembrete mensal na
# Agenda (todo dia 1º) para pagar ou definir uma nova data.
# ---------------------------------------------------------------------------
FORMAS_PAGAMENTO_CONTRATO = ["mensal", "quinzenal", "semanal"]


class ContratoParcelaIn(BaseModel):
    data_vencimento: date
    valor: float


class ContratoIn(BaseModel):
    pessoa_id: int
    descricao: str
    valor_total: float
    forma_pagamento: str | None = None  # None => sem frequência definida
    observacao: str | None = None
    # Preenchido quando forma_pagamento está definida — já calculado (a partir
    # de data de término estimada, número de parcelas ou lançamento livre) e
    # editável no frontend, mesmo padrão do parcelamento do Financeiro.
    parcelas: list[ContratoParcelaIn] = []
    centro_custo: str = "Pecuária Leiteira"


def _serializar_contrato(session: Session, c: Contrato) -> dict:
    parcelas = session.exec(
        select(ContratoParcela).where(ContratoParcela.contrato_id == c.id).order_by(ContratoParcela.data_vencimento)
    ).all()
    numeros = [p.numero_lancamento_gerado for p in parcelas if p.numero_lancamento_gerado]
    pagos = set()
    if numeros:
        contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all()
        pagos = {conta.numero_lancamento for conta in contas if conta.valor_pago is not None}
    abatido = _abatimentos_de_vale_por_item(session, "contrato_parcela", [p.id for p in parcelas], c.fazenda_id)
    return {
        **c.model_dump(),
        # Bruto contratado e desconto de vale separados — ver o comentário em
        # `_serializar_empreitada`.
        "parcelas": [
            {
                **p.model_dump(),
                "status": "pago" if p.numero_lancamento_gerado in pagos else "pendente",
                "valor_abatido_vales": abatido.get(p.id, 0.0),
            }
            for p in parcelas
        ],
        "vales": _listar_vales_avulsos(session, "contrato", c.id),
    }


@router.get("/contratos")
def listar_contratos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(Contrato)
    if fazenda_id is not None:
        query = query.where(Contrato.fazenda_id == fazenda_id)
    contratos = session.exec(query.order_by(Contrato.criado_em.desc())).all()
    return [{**_serializar_contrato(session, c), "pessoa_nome": pessoas.get(c.pessoa_id, "—")} for c in contratos]


@router.post("/contratos")
def criar_contrato(
    dados: ContratoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.forma_pagamento is not None and dados.forma_pagamento not in FORMAS_PAGAMENTO_CONTRATO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.forma_pagamento and not dados.parcelas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma parcela para a frequência escolhida")

    contrato = Contrato(
        pessoa_id=dados.pessoa_id, descricao=dados.descricao, valor_total=dados.valor_total,
        forma_pagamento=dados.forma_pagamento, observacao=dados.observacao, usuario_id=user.id,
        centro_custo=dados.centro_custo, fazenda_id=fazenda_id,
    )
    session.add(contrato)
    session.commit()
    session.refresh(contrato)

    if dados.forma_pagamento:
        # Mesma regra de `criar_empreitada`: k de n congelados na criação e
        # bruto contratado guardado antes de qualquer vale.
        total_parcelas = len(dados.parcelas)
        for i, parcela in enumerate(dados.parcelas, start=1):
            numero_lancamento = _proximo_numero_lancamento(session, parcela.data_vencimento.year)
            session.add(ContratoParcela(
                contrato_id=contrato.id, data_vencimento=parcela.data_vencimento, valor=parcela.valor,
                numero=i, numero_total=total_parcelas, valor_contratado=parcela.valor,
                numero_lancamento_gerado=numero_lancamento, fazenda_id=fazenda_id,
            ))
            session.add(ContaGerencial(
                numero_lancamento=numero_lancamento,
                descricao=f"Contrato — {pessoa.nome} ({dados.descricao})",
                data_vencimento=parcela.data_vencimento,
                data_competencia=parcela.data_vencimento.replace(day=1),
                fornecedor_cliente=pessoa.nome,
                tipo_documento="Contrato",
                centro_custo=dados.centro_custo,
                valor_total=parcela.valor,
                parcela_num=1, parcela_total=1,
                tipo="despesa", origem="auto",
                fazenda_id=fazenda_id,
            ))
    else:
        # Sem frequência definida: lembrete mensal na Agenda (todo dia 1º) para
        # pagar ou definir uma nova data — reaproveita o motor de recorrência
        # já existente da Agenda (_gerar_agenda_recorrente, chamado a cada GET
        # /agenda/), sem precisar de nenhuma lógica de recorrência nova aqui.
        proximo = _competencia_seguinte(date.today().strftime("%Y-%m"))
        ano, mes = (int(x) for x in proximo.split("-"))
        lembrete = AgendaManual(
            data_evento=date(ano, mes, 1),
            descricao=f"Contrato sem frequência definida — {pessoa.nome} ({dados.descricao}): pagar ou definir nova data",
            categoria="Gestão/Financeiro",
            tipo_evento="Outro",
            recorrente=True,
            intervalo_meses=1,
            usuario_id=user.id,
        )
        session.add(lembrete)
        session.commit()
        session.refresh(lembrete)
        contrato.origem_lembrete_agenda_id = lembrete.id
        session.add(contrato)
    session.commit()
    return _serializar_contrato(session, contrato)


@router.put("/contratos/{contrato_id}/encerrar")
def encerrar_contrato(
    contrato_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    contrato = session.get(Contrato, contrato_id)
    if not contrato or (contrato.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    contrato.status = "encerrado"
    session.add(contrato)
    if contrato.origem_lembrete_agenda_id:
        modelo = session.get(AgendaManual, contrato.origem_lembrete_agenda_id)
        if modelo:
            modelo.recorrente = False
            session.add(modelo)
    session.commit()
    return _serializar_contrato(session, contrato)


@router.delete("/contratos/parcelas/{parcela_id}")
def excluir_parcela_contrato(
    parcela_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(ContratoParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Parcela de contrato não encontrada")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado], fazenda_id):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser excluída aqui — exclua em Lançamentos > Excluir lançamento.")
    # `_conta_do_numero` (rh_folha.py) recorta a fazenda DENTRO da consulta:
    # o número do lançamento é sequencial por ano, não é chave global, e aqui
    # se APAGA o lançamento — sem o recorte, um número repetido numa base
    # importada levaria embora a conta a pagar de outro inquilino.
    conta = _conta_do_numero(session, parcela.numero_lancamento_gerado, fazenda_id)
    if conta:
        session.delete(conta)
    session.delete(parcela)
    session.commit()
    return {"ok": True}


@router.put("/contratos/parcelas/{parcela_id}")
def atualizar_parcela_contrato(
    parcela_id: int, dados: ParcelaEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    parcela = session.get(ContratoParcela, parcela_id)
    if not parcela or (parcela.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Parcela de contrato não encontrada")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor da parcela deve ser positivo")
    if parcela.numero_lancamento_gerado and _numeros_pagos(session, [parcela.numero_lancamento_gerado], fazenda_id):
        raise HTTPException(status_code=400, detail="Parcela já paga não pode ser editada aqui — edite em Lançamentos > Financeiro.")
    parcela.data_vencimento = dados.data_vencimento
    parcela.valor = dados.valor
    _reajustar_valor_contratado(session, parcela, "contrato_parcela")
    session.add(parcela)
    _sincronizar_conta_parcela(session, parcela.numero_lancamento_gerado, dados.data_vencimento, dados.valor, fazenda_id)
    session.commit()
    contrato = session.get(Contrato, parcela.contrato_id)
    return _serializar_contrato(session, contrato)


@router.post("/contratos/{contrato_id}/parcelas/redistribuir")
def redistribuir_parcelas_contrato(
    contrato_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    contrato = session.get(Contrato, contrato_id)
    if not contrato or (contrato.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    parcelas = session.exec(
        select(ContratoParcela).where(ContratoParcela.contrato_id == contrato_id).order_by(ContratoParcela.data_vencimento)
    ).all()
    pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in parcelas if p.numero_lancamento_gerado], fazenda_id)
    pendentes = [p for p in parcelas if p.numero_lancamento_gerado not in pagos]
    _redistribuir_parcelas_pendentes(session, pendentes, fazenda_id)
    session.commit()
    return _serializar_contrato(session, contrato)


# ---------------------------------------------------------------------------
# Diária — valor da diária + data de início; o sistema conta diariamente até
# hoje e mantém o saldo devedor a partir dos pagamentos registrados.
# ---------------------------------------------------------------------------
class DiariaIn(BaseModel):
    pessoa_id: int
    valor_diaria: float
    data_inicio: date
    data_fim: date | None = None
    observacao: str | None = None
    centro_custo: str = "Pecuária Leiteira"
    conta_dia_a_dia: bool = True
    # None = herda o padrão de ParametroDiariaPadrao no momento do cadastro.
    auditar_periodicamente: bool | None = None
    frequencia_auditoria: str | None = None
    dia_semana_auditoria: int | None = None
    intervalo_dias_auditoria: int | None = None


class DiariaEditIn(BaseModel):
    """Edição via botão no controle — sempre substitui os 3 campos por
    inteiro (envie null para limpar data_fim/ajuste_numero_diarias)."""
    data_inicio: date
    data_fim: date | None = None
    ajuste_numero_diarias: int | None = None


class DiariaPagamentoIn(BaseModel):
    data_pagamento: date
    valor: float
    observacao: str | None = None
    # Conta bancária de onde sai o pagamento — OPCIONAL (ver
    # _resolver_conta_corrente em rh_folha.py).
    conta_corrente_id: int | None = None
    # Confirmação de pagamento acima do saldo devedor (total apurado menos o
    # que já foi pago menos os vales já adiantados). Ver
    # `registrar_pagamento_diaria`.
    confirmar_excedente: bool = False


def _dias_confirmados_diaria(session: Session, diaria_id: int, ate: date | None = None) -> tuple[int, date | None]:
    """Soma os dias efetivamente confirmados nas auditorias JÁ RESPONDIDAS
    desta diária, e devolve também até que data essa contagem cobre
    (`periodo_fim` da última auditoria respondida — os dias corridos depois
    dela ainda não foram auditados, então continuam contados no "olho" pela
    regra antiga, dia a dia, até a próxima resposta).

    `ate` (opcional): descarta auditorias cujo `periodo_fim` passa de `ate` —
    usado por `_dias_legado_ate` para truncar a contagem legada num corte
    diferente de hoje. `ate=None` mantém o comportamento de sempre
    (considera todas as auditorias respondidas, sem limite)."""
    query = select(DiariaAuditoria).where(
        DiariaAuditoria.diaria_id == diaria_id, DiariaAuditoria.dias_trabalhados.is_not(None)
    )
    if ate is not None:
        query = query.where(DiariaAuditoria.periodo_fim <= ate)
    respondidas = session.exec(query.order_by(DiariaAuditoria.periodo_fim)).all()
    if not respondidas:
        return 0, None
    return sum(a.dias_trabalhados for a in respondidas), respondidas[-1].periodo_fim


def _dias_legado_ate(session: Session, d: Diaria, ate: date) -> int:
    """O mesmo cálculo do bloco legado abaixo (auditorias respondidas +
    ajuste manual + dias corridos), truncado em `ate` em vez de
    `hoje_ou_fim` — usado para somar a parte "antes do corte" de uma diária
    que passou a ser controlada por calendário (ver `controle_por_dia_desde`).
    """
    if ate < d.data_inicio:
        return 0
    dias_confirmados, cobertura_ate = _dias_confirmados_diaria(session, d.id, ate=ate)
    if d.ajuste_numero_diarias is not None and d.ajuste_numero_diarias_em is not None and (
        cobertura_ate is None or d.ajuste_numero_diarias_em >= cobertura_ate
    ):
        base, desde = d.ajuste_numero_diarias, d.ajuste_numero_diarias_em
    else:
        base, desde = dias_confirmados, cobertura_ate
    if desde is not None:
        return max(base + max((ate - desde).days, 0), 0)
    return max((ate - d.data_inicio).days + 1, 0)


def _fracao_dia(linha: DiariaDia) -> float:
    """Fração da diária cumprida num dia com linha de exceção — 1.0 = dia
    cheio (nunca gravado como linha; só chega aqui quem já tem exceção),
    0.5 = meia diária, 0.0 = folga. `fracao=None` (dado histórico, de antes
    desta feature) sempre significava folga, então cai em 0.0."""
    return linha.fracao if linha.fracao is not None else 0.0


def _dias_por_dia(session: Session, d: Diaria, desde: date, ate: date) -> tuple[float, int, int]:
    """(dias_efetivos, dias_folga, dias_meia_diaria) no intervalo [desde,
    ate], pelo modelo esparso de `DiariaDia`: todo dia corrido é trabalhado
    (fração 1.0) por padrão — só os dias com linha de exceção reduzem a
    contagem, por fração de dia perdida (1.0 = folga, 0.5 = meia diária)."""
    corridos = max((ate - desde).days + 1, 0)
    if corridos == 0:
        return 0.0, 0, 0
    excecoes = session.exec(
        select(DiariaDia).where(
            DiariaDia.diaria_id == d.id, DiariaDia.trabalhado == False,  # noqa: E712
            DiariaDia.data >= desde, DiariaDia.data <= ate,
        )
    ).all()
    dias_folga = sum(1 for e in excecoes if _fracao_dia(e) == 0.0)
    dias_meia = sum(1 for e in excecoes if _fracao_dia(e) == 0.5)
    perdido = sum(1 - _fracao_dia(e) for e in excecoes)
    dias_efetivos = max(round(corridos - perdido, 2), 0)
    return dias_efetivos, dias_folga, dias_meia


def _pago_ate_diaria(session: Session, diaria_id: int) -> date | None:
    """Data do pagamento mais recente registrado para esta diária, ou None
    se nunca houve pagamento — usado para travar a edição do calendário num
    período já quitado (ver `salvar_dias_diaria`) sem confirmação explícita."""
    ultimo = session.exec(
        select(DiariaPagamento)
        .where(DiariaPagamento.diaria_id == diaria_id)
        .order_by(DiariaPagamento.data_pagamento.desc())
    ).first()
    return ultimo.data_pagamento if ultimo else None


def _ultima_folga_diaria(session: Session, diaria_id: int, antes_de: date) -> date | None:
    """Data da folga (`DiariaDia.trabalhado=False`) mais recente ANTES de
    `antes_de` (estritamente — não inclui o próprio dia). Usado tanto no
    resumo (`ultima_folga`) quanto no modo `ultimo_periodo` do calendário: ao
    excluir o próprio dia de hoje, uma folga marcada hoje nunca colapsa a
    janela editável a vazio (senão o usuário ficaria travado sem conseguir
    desfazer o próprio toque)."""
    return session.exec(
        select(DiariaDia.data)
        .where(
            DiariaDia.diaria_id == diaria_id, DiariaDia.trabalhado == False,  # noqa: E712
            DiariaDia.data < antes_de,
        )
        .order_by(DiariaDia.data.desc())
    ).first()


def _diaria_ou_404(session: Session, diaria_id: int, fazenda_id: int | None) -> Diaria:
    diaria = session.get(Diaria, diaria_id)
    if not diaria or (diaria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    return diaria


def _periodo_congelado(d: Diaria) -> bool:
    """Este período já foi FECHADO pelo fluxo novo de encerramento?

    `status == "encerrado"` sozinho não basta: diária encerrada antes desta
    feature não tem fotografia nenhuma guardada (ver a migração
    d4a1f6c2b9e7), e para ela o comportamento continua sendo o de sempre —
    recalcular tudo. `data_encerramento` é o marco que separa os dois
    mundos."""
    return d.status == "encerrado" and d.data_encerramento is not None


def _conta_do_encerramento(session: Session, d: Diaria) -> ContaGerencial | None:
    """A conta a pagar emitida no encerramento desta diária, se existir.

    É por aqui que a RECONCILIAÇÃO acontece: quem baixa a conta é o
    Financeiro (`PUT /financeiro/lancamentos/{id}/pagar`), que não sabe nada
    de diária. Em vez de pendurar um gancho lá dentro, o resumo lê o estado
    do próprio lançamento — a conta É a fonte da verdade sobre ter sido paga
    ou não, e assim não existe cópia para ficar desatualizada. Sem isso,
    pagar a conta no Financeiro deixava a diária eternamente devendo."""
    if not d.numero_lancamento_gerado:
        return None
    return session.exec(
        select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == d.numero_lancamento_gerado,
            ContaGerencial.fazenda_id == d.fazenda_id,
        )
    ).first()


def _resumo_cobranca_diaria(session: Session, d: Diaria) -> dict | None:
    """Bloco `cobranca` do resumo — o que a tela precisa para dizer "cobrado,
    em aberto" ou "cobrado e pago", e para saber se ainda dá para reabrir."""
    conta = _conta_do_encerramento(session, d)
    if conta is None:
        return None
    pago = conta.valor_pago is not None
    return {
        "numero_lancamento": conta.numero_lancamento,
        "valor": conta.valor_total,
        "data_vencimento": conta.data_vencimento,
        "valor_pago": conta.valor_pago,
        "data_pagamento": conta.data_pagamento,
        "status": "pago" if pago else "em_aberto",
    }


def _exigir_periodo_aberto(session: Session, d: Diaria, acao: str) -> None:
    """Recusa qualquer escrita que mexeria no apurado de um período já
    congelado (dias trabalhados, datas/ajuste manual, pagamento avulso).

    Deixar passar seria pior do que recusar: a escrita seria aceita e não
    mudaria NADA no que a tela mostra (o resumo lê a fotografia) nem no valor
    já cobrado — trabalho silenciosamente perdido. Quem precisa corrigir de
    verdade reabre o período, o que apaga a cobrança e devolve o controle."""
    if not _periodo_congelado(d):
        return
    conta = _conta_do_encerramento(session, d)
    onde = f" A cobrança emitida é o lançamento {conta.numero_lancamento}." if conta is not None else ""
    raise HTTPException(
        status_code=400,
        detail=(
            f"O período desta diária foi encerrado em {d.data_encerramento.strftime('%d/%m/%Y')} e está congelado, "
            f"então {acao} não teria efeito nenhum no valor já apurado.{onde} "
            "Reabra o período (botão Reabrir) para poder alterá-lo."
        ),
    )


def _resumo_diaria(session: Session, d: Diaria, pessoa_nome: str) -> dict:
    # "Hoje" nunca passa da data de fim — depois que a diária encerra, o
    # contador para de correr (sem isso, teria que ser marcada como
    # "encerrado" manualmente no dia certo pra não seguir somando diárias).
    hoje = date.today()
    hoje_ou_fim = min(hoje, d.data_fim) if d.data_fim else hoje
    if d.controle_por_dia_desde is None:
        # bloco atual, byte-for-byte intocado — os 5 testes existentes de
        # TestDiaria dependem deste caminho continuar idêntico ao de sempre.
        dias_confirmados, cobertura_ate = _dias_confirmados_diaria(session, d.id)
        # O ajuste manual (botão de editar) e a cobertura de auditoria são dois
        # "checkpoints" concorrentes — o mais recente vence como base da
        # contagem, e os dias corridos desde ele são somados por cima.
        if d.ajuste_numero_diarias is not None and d.ajuste_numero_diarias_em is not None and (
            cobertura_ate is None or d.ajuste_numero_diarias_em >= cobertura_ate
        ):
            base, desde = d.ajuste_numero_diarias, d.ajuste_numero_diarias_em
        else:
            base, desde = dias_confirmados, cobertura_ate
        if desde is not None:
            numero_diarias = base + max((hoje_ou_fim - desde).days, 0)
        else:
            numero_diarias = max((hoje_ou_fim - d.data_inicio).days + 1, 0)
        dias_folga = 0
        dias_meia_diaria = 0
    else:
        # Calendário assumiu o controle a partir de `controle_por_dia_desde`
        # — tudo antes do corte continua pela regra legada (auditorias +
        # ajuste manual + dias corridos), tudo a partir dele vem do
        # calendário esparso de DiariaDia. As duas janelas são disjuntas por
        # construção (ver `salvar_dias_diaria`), então soma sem sobreposição.
        corte = d.controle_por_dia_desde
        legado = _dias_legado_ate(session, d, corte - timedelta(days=1))
        por_dia, dias_folga, dias_meia_diaria = _dias_por_dia(session, d, corte, hoje_ou_fim)
        numero_diarias = legado + por_dia
    total_ate_hoje = round(numero_diarias * d.valor_diaria, 2)
    pagamentos = sorted(
        session.exec(select(DiariaPagamento).where(DiariaPagamento.diaria_id == d.id)).all(),
        key=lambda p: p.data_pagamento,
    )
    valor_pago = round(sum(p.valor for p in pagamentos), 2)
    vales = _listar_vales_avulsos(session, "diaria", d.id)
    valor_vale = round(sum(v["valor"] for v in vales), 2)
    auditorias_pendentes = session.exec(
        select(DiariaAuditoria)
        .where(DiariaAuditoria.diaria_id == d.id, DiariaAuditoria.dias_trabalhados.is_(None))
        .order_by(DiariaAuditoria.periodo_fim)
    ).all()
    saldo_devedor = round(total_ate_hoje - valor_pago - valor_vale, 2)
    cobranca = _resumo_cobranca_diaria(session, d)

    # ── PERÍODO CONGELADO ────────────────────────────────────────────────
    # Tudo acima foi RECALCULADO como se o período ainda estivesse correndo.
    # Para uma diária já encerrada pelo fluxo novo isso é errado: a conta a
    # pagar emitida no fechamento guarda um valor que ninguém reescreve, e um
    # vale lançado depois, uma auditoria respondida atrasada ou um dia
    # corrigido no calendário faziam o resumo divergir dela sozinhos — a tela
    # dizia um número, o Contas a Pagar dizia outro. A partir daqui o resumo
    # LÊ a fotografia gravada no encerramento em vez de recalcular.
    #
    # A única coisa que continua viva é o pagamento da conta emitida
    # (reconciliação): baixar a conta no Financeiro abate o saldo aqui.
    if _periodo_congelado(d):
        numero_diarias = d.encerramento_numero_diarias if d.encerramento_numero_diarias is not None else numero_diarias
        total_ate_hoje = d.encerramento_total_apurado if d.encerramento_total_apurado is not None else total_ate_hoje
        valor_vale = d.encerramento_valor_vale if d.encerramento_valor_vale is not None else valor_vale
        valor_pago_congelado = d.encerramento_valor_pago if d.encerramento_valor_pago is not None else valor_pago
        saldo_congelado = (
            d.encerramento_saldo_devedor if d.encerramento_saldo_devedor is not None
            else round(total_ate_hoje - valor_pago_congelado - valor_vale, 2)
        )
        pago_na_cobranca = (cobranca or {}).get("valor_pago") or 0.0
        valor_pago = round(valor_pago_congelado + pago_na_cobranca, 2)
        saldo_devedor = round(saldo_congelado - pago_na_cobranca, 2)

    return {
        **d.model_dump(),
        "pessoa_nome": pessoa_nome,
        "numero_diarias": numero_diarias,
        "total_ate_hoje": total_ate_hoje,
        "valor_pago": valor_pago,
        "valor_vale": valor_vale,
        "saldo_devedor": saldo_devedor,
        "pagamentos": [p.model_dump() for p in pagamentos],
        "vales": vales,
        "auditorias_pendentes": [a.model_dump() for a in auditorias_pendentes],
        "dias_folga": dias_folga,
        "dias_meia_diaria": dias_meia_diaria,
        "ultima_folga": _ultima_folga_diaria(session, d.id, hoje_ou_fim),
        "pago_ate": pagamentos[-1].data_pagamento if pagamentos else None,
        # Conta a pagar emitida no encerramento (None enquanto o período está
        # aberto, ou quando ele fechou já quitado — ver `encerrar_diaria`).
        "cobranca": cobranca,
        "periodo_congelado": _periodo_congelado(d),
    }


@router.get("/diarias")
def listar_diarias(
    incluir_finalizadas: bool = False,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Por padrão só lista quem ainda está fazendo diárias (status "ativo") —
    ver `incluir_finalizadas` para trazer também as encerradas."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    query = select(Diaria)
    if fazenda_id is not None:
        query = query.where(Diaria.fazenda_id == fazenda_id)
    if not incluir_finalizadas:
        query = query.where(Diaria.status != "encerrado")
    diarias = session.exec(query.order_by(Diaria.criado_em.desc())).all()
    return [_resumo_diaria(session, d, pessoas.get(d.pessoa_id, "—")) for d in diarias]


def _parametro_diaria_padrao(session: Session, fazenda_id: int | None = None) -> ParametroDiariaPadrao:
    """Configuração-padrão da fazenda informada — get-or-create por
    `fazenda_id` (era um singleton id=1 global; agora uma linha por
    fazenda, ver fazenda/models/pessoal.py::ParametroDiariaPadrao)."""
    query = select(ParametroDiariaPadrao)
    query = query.where(ParametroDiariaPadrao.fazenda_id == fazenda_id) if fazenda_id is not None else query.where(
        ParametroDiariaPadrao.fazenda_id.is_(None)
    )
    padrao = session.exec(query).first()
    if not padrao:
        padrao = ParametroDiariaPadrao(fazenda_id=fazenda_id)
        session.add(padrao)
        session.commit()
        session.refresh(padrao)
    return padrao


@router.get("/diarias/parametro-padrao")
def obter_parametro_diaria_padrao(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    return _parametro_diaria_padrao(session, fazenda_id_seguro(fazenda_id)).model_dump()


class ParametroDiariaPadraoIn(BaseModel):
    auditar_periodicamente: bool
    frequencia_auditoria: str  # semanal | intervalo_dias | mensal
    dia_semana_auditoria: int = 0
    intervalo_dias_auditoria: int = 7


@router.put("/diarias/parametro-padrao")
def salvar_parametro_diaria_padrao(
    dados: ParametroDiariaPadraoIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.frequencia_auditoria not in ("semanal", "intervalo_dias", "mensal"):
        raise HTTPException(status_code=400, detail="Frequência inválida")
    padrao = _parametro_diaria_padrao(session, fazenda_id)
    padrao.auditar_periodicamente = dados.auditar_periodicamente
    padrao.frequencia_auditoria = dados.frequencia_auditoria
    padrao.dia_semana_auditoria = dados.dia_semana_auditoria
    padrao.intervalo_dias_auditoria = dados.intervalo_dias_auditoria
    padrao.atualizado_em = datetime.utcnow()
    session.add(padrao)
    session.commit()
    session.refresh(padrao)
    return padrao.model_dump()


@router.post("/diarias")
def criar_diaria(
    dados: DiariaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.valor_diaria <= 0:
        raise HTTPException(status_code=400, detail="Valor da diária deve ser positivo")
    # Campos de auditoria não informados herdam o padrão configurado em
    # Configurações > Parâmetros — cada diária pode depois editar a própria
    # cadência sem afetar as demais.
    padrao = _parametro_diaria_padrao(session, fazenda_id)
    auditar = dados.auditar_periodicamente if dados.auditar_periodicamente is not None else padrao.auditar_periodicamente
    frequencia = dados.frequencia_auditoria or padrao.frequencia_auditoria
    dia_semana = dados.dia_semana_auditoria if dados.dia_semana_auditoria is not None else padrao.dia_semana_auditoria
    intervalo = dados.intervalo_dias_auditoria if dados.intervalo_dias_auditoria is not None else padrao.intervalo_dias_auditoria
    diaria = Diaria(
        pessoa_id=dados.pessoa_id, valor_diaria=dados.valor_diaria, data_inicio=dados.data_inicio,
        data_fim=dados.data_fim,
        observacao=dados.observacao, usuario_id=user.id, centro_custo=dados.centro_custo,
        conta_dia_a_dia=dados.conta_dia_a_dia, auditar_periodicamente=auditar,
        frequencia_auditoria=frequencia, dia_semana_auditoria=dia_semana, intervalo_dias_auditoria=intervalo,
        fazenda_id=fazenda_id,
    )
    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    return _resumo_diaria(session, diaria, pessoa.nome)


@router.put("/diarias/{diaria_id}")
def editar_diaria(
    diaria_id: int, dados: DiariaEditIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = session.get(Diaria, diaria_id)
    if not diaria or (diaria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    _exigir_periodo_aberto(session, diaria, "mudar as datas ou o número de diárias")
    if dados.ajuste_numero_diarias is not None and dados.ajuste_numero_diarias < 0:
        raise HTTPException(status_code=400, detail="Número de diárias não pode ser negativo")
    diaria.data_inicio = dados.data_inicio
    diaria.data_fim = dados.data_fim
    if dados.ajuste_numero_diarias is not None:
        diaria.ajuste_numero_diarias = dados.ajuste_numero_diarias
        diaria.ajuste_numero_diarias_em = date.today()
    else:
        diaria.ajuste_numero_diarias = None
        diaria.ajuste_numero_diarias_em = None
    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    return _resumo_diaria(session, diaria, pessoa.nome)


class DiariaEncerrarIn(BaseModel):
    """Corpo OPCIONAL de `PUT /diarias/{id}/encerrar` — opcional porque a
    chamada sem corpo nenhum já existia e continua valendo (o frontend antigo
    e os testes de listagem passam por ela)."""
    # Último dia trabalhado. Sem ele o contador não parava: a diária ficava
    # "encerrada" e seguia somando uma diária por dia, invisível, porque a
    # linha sai da listagem padrão. Quando não vem, cai na melhor data
    # disponível (a `data_fim` já cadastrada, ou hoje).
    data_encerramento: date | None = None
    # Vencimento da conta a pagar emitida — padrão: dia 1º do mês seguinte,
    # exatamente como `concluir_etapa_empreitada` faz com a etapa concluída.
    data_vencimento: date | None = None
    # Escape para fechar o período SEM cobrar (acerto feito por fora, por
    # exemplo). O período congela do mesmo jeito; só não nasce lançamento.
    emitir_conta: bool = True


@router.put("/diarias/{diaria_id}/encerrar")
def encerrar_diaria(
    diaria_id: int, dados: DiariaEncerrarIn | None = None, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Encerra o período da diarista: para o contador, CONGELA o apurado e, se
    ainda houver saldo devedor, EMITE a conta a pagar correspondente.

    O buraco que isto fecha: encerrar um período devendo dinheiro não gerava
    lançamento nenhum. O trabalho ficava registrado aqui e sumia do radar
    financeiro — nem Agenda, nem Contas a Pagar — porque a linha ainda sai da
    listagem padrão de diárias (`incluir_finalizadas`). Ninguém via mais.

    A emissão segue a receita canônica do projeto, a mesma de
    `concluir_etapa_empreitada` logo acima: `_proximo_numero_lancamento`,
    número gravado na própria origem (`Diaria.numero_lancamento_gerado`) e uma
    `ContaGerencial` com tipo="despesa"/origem="auto". Agenda e Contas a Pagar
    não precisaram de UMA linha de mudança: os dois já pegam qualquer conta
    com `valor_pago < valor_total` (ver `AgendaEngine.calcular` e
    `financeiro.contas_a_pagar`). O que faltava era só emitir.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = _diaria_ou_404(session, diaria_id, fazenda_id)
    if _periodo_congelado(diaria):
        raise HTTPException(status_code=400, detail="Este período já foi encerrado. Reabra antes de encerrar de novo.")
    dados = dados or DiariaEncerrarIn()
    hoje = date.today()

    ultimo_dia = dados.data_encerramento or diaria.data_fim or hoje
    if ultimo_dia < diaria.data_inicio:
        raise HTTPException(
            status_code=400,
            detail="O último dia trabalhado não pode ser anterior ao início da diária.",
        )

    # `data_fim` é quem faz `_resumo_diaria` parar de contar; gravar as duas
    # mantém o comportamento de sempre para quem já usava data de fim, e faz
    # o encerramento sem data informada também parar o contador.
    diaria.data_fim = ultimo_dia
    diaria.data_encerramento = ultimo_dia

    pessoa = session.get(Pessoa, diaria.pessoa_id)
    nome_pessoa = pessoa.nome if pessoa else "—"
    # Resumo apurado com o contador JÁ parado no último dia trabalhado — é
    # esta fotografia que vira a conta a pagar e o congelamento.
    resumo = _resumo_diaria(session, diaria, nome_pessoa)
    saldo = resumo["saldo_devedor"]

    diaria.encerramento_numero_diarias = resumo["numero_diarias"]
    diaria.encerramento_total_apurado = resumo["total_ate_hoje"]
    diaria.encerramento_valor_pago = resumo["valor_pago"]
    diaria.encerramento_valor_vale = resumo["valor_vale"]
    diaria.encerramento_saldo_devedor = saldo
    diaria.status = "encerrado"

    # Saldo zerado (ou negativo, quando se pagou a mais) não vira conta
    # nenhuma: uma conta a pagar de R$ 0,00 é invisível na Agenda e em Contas
    # a Pagar (as duas exigem `valor_pago < valor_total`) e ficaria pendurada
    # para sempre sem ninguém conseguir baixá-la.
    if dados.emitir_conta and saldo > 0:
        if dados.data_vencimento:
            vencimento = dados.data_vencimento
        else:
            proximo = _competencia_seguinte(hoje.strftime("%Y-%m"))
            ano, mes = (int(x) for x in proximo.split("-"))
            vencimento = date(ano, mes, 1)
        numero_lancamento = _proximo_numero_lancamento(session, vencimento.year)
        diaria.numero_lancamento_gerado = numero_lancamento
        session.add(ContaGerencial(
            numero_lancamento=numero_lancamento,
            descricao=(
                f"Diária — {nome_pessoa} "
                f"({diaria.data_inicio.strftime('%d/%m/%Y')} a {ultimo_dia.strftime('%d/%m/%Y')})"
            ),
            data_vencimento=vencimento,
            data_competencia=vencimento.replace(day=1),
            fornecedor_cliente=nome_pessoa,
            # NÃO é "Diária": esse tipo_documento está em
            # `TIPOS_DOCUMENTO_BAIXA_ESPELHADA` (routers/financeiro.py), que
            # recusa estorno porque lá o lançamento nasce JÁ PAGO, espelhando
            # uma baixa feita no RH. Este aqui é o oposto — nasce EM ABERTO
            # para ser pago no Financeiro —, e precisa poder ser estornado:
            # é o próprio caminho que a reabertura do período manda seguir.
            tipo_documento="Acerto de diária",
            centro_custo=diaria.centro_custo,
            valor_total=saldo,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            fazenda_id=diaria.fazenda_id,
        ))

    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    return _resumo_diaria(session, diaria, nome_pessoa)


@router.put("/diarias/{diaria_id}/reabrir")
def reabrir_diaria(
    diaria_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Desfaz o encerramento: apaga a cobrança emitida (se ainda em aberto),
    descongela o apurado e devolve a diária ao estado anterior.

    A trava: se a conta já foi PAGA, reabrir é recusado. Descongelar por cima
    de dinheiro que já saiu do caixa recriaria a divergência que o
    congelamento existe para evitar — o apurado voltaria a correr e a conta
    paga continuaria valendo o que valia. Quem quiser reabrir mesmo assim
    estorna a baixa no Financeiro primeiro (por isso o lançamento nasce com
    `tipo_documento` estornável — ver `encerrar_diaria`).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = _diaria_ou_404(session, diaria_id, fazenda_id)
    if not _periodo_congelado(diaria):
        raise HTTPException(status_code=400, detail="Esta diária não está com o período encerrado.")

    conta = _conta_do_encerramento(session, diaria)
    if conta is not None and conta.valor_pago is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A conta a pagar deste encerramento ({conta.numero_lancamento}) já foi paga em "
                f"{conta.data_pagamento.strftime('%d/%m/%Y') if conta.data_pagamento else '—'}. "
                "Estorne a baixa em Financeiro › Lançamentos antes de reabrir o período."
            ),
        )
    if conta is not None:
        session.delete(conta)

    # `data_fim` volta a ficar vazia só quando foi este encerramento que a
    # preencheu — uma data de fim que já existia antes (cadastrada no
    # lançamento da diária) é do usuário, não nossa para apagar.
    if diaria.data_fim == diaria.data_encerramento:
        diaria.data_fim = None
    diaria.data_encerramento = None
    diaria.numero_lancamento_gerado = None
    diaria.encerramento_numero_diarias = None
    diaria.encerramento_total_apurado = None
    diaria.encerramento_valor_pago = None
    diaria.encerramento_valor_vale = None
    diaria.encerramento_saldo_devedor = None
    diaria.status = "ativo"
    session.add(diaria)
    session.commit()
    session.refresh(diaria)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    return _resumo_diaria(session, diaria, pessoa.nome if pessoa else "—")


class DiariaAuditoriaResponderIn(BaseModel):
    dias_trabalhados: int


@router.put("/diarias/auditorias/{auditoria_id}")
def responder_auditoria_diaria(
    auditoria_id: int, dados: DiariaAuditoriaResponderIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    auditoria = session.get(DiariaAuditoria, auditoria_id)
    if not auditoria or (auditoria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Auditoria não encontrada")
    dias_no_periodo = (auditoria.periodo_fim - auditoria.periodo_inicio).days + 1
    if not (0 <= dados.dias_trabalhados <= dias_no_periodo):
        raise HTTPException(status_code=400, detail=f"Dias trabalhados deve estar entre 0 e {dias_no_periodo}")
    auditoria.dias_trabalhados = dados.dias_trabalhados
    auditoria.confirmado_em = datetime.utcnow()
    auditoria.usuario_id = user.id
    session.add(auditoria)
    session.commit()
    diaria = session.get(Diaria, auditoria.diaria_id)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    return _resumo_diaria(session, diaria, pessoa.nome)


@router.post("/diarias/{diaria_id}/pagamentos")
def registrar_pagamento_diaria(
    diaria_id: int, dados: DiariaPagamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    diaria = session.get(Diaria, diaria_id)
    if not diaria or (diaria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do pagamento deve ser positivo")
    # Período encerrado tem a dívida em Contas a Pagar, não aqui: pagar por
    # este caminho criaria um segundo pagamento para a mesma dívida, e a
    # conta emitida continuaria em aberto cobrando de novo.
    _exigir_periodo_aberto(session, diaria, "registrar um pagamento por aqui")
    pessoa = session.get(Pessoa, diaria.pessoa_id)

    # Pagar mais do que se deve não pode acontecer em silêncio. O saldo
    # devedor (`_resumo_diaria`) já desconta os pagamentos anteriores E os
    # vales avulsos já adiantados — e era exatamente esse desconto que o
    # endpoint ignorava: quem digitava o total das diárias esquecendo o
    # adiantamento pagava a mesma diária duas vezes, sem um aviso.
    #
    # Continua sendo POSSÍVEL pagar a mais (adiantar o mês seguinte, acertar
    # uma diferença combinada), só que com confirmação explícita — mesmo
    # mecanismo de `confirmar_periodo_pago` em `salvar_dias_diaria` logo
    # abaixo: 409 com os números na mão para a tela poder perguntar.
    resumo_antes = _resumo_diaria(session, diaria, pessoa.nome if pessoa else "—")
    saldo_devedor = resumo_antes["saldo_devedor"]
    excedente = round(dados.valor - saldo_devedor, 2)
    if excedente > 0 and not dados.confirmar_excedente:
        raise HTTPException(status_code=409, detail={
            "mensagem": (
                f"O pagamento de R$ {dados.valor:.2f} é maior que o saldo devedor desta diária "
                f"(R$ {saldo_devedor:.2f} = R$ {resumo_antes['total_ate_hoje']:.2f} apurados "
                f"− R$ {resumo_antes['valor_pago']:.2f} já pagos "
                f"− R$ {resumo_antes['valor_vale']:.2f} de vale já adiantado). "
                f"Sobram R$ {excedente:.2f} pagos a mais. Confirme se quiser pagar assim mesmo."
            ),
            "saldo_devedor": saldo_devedor,
            "valor_informado": round(dados.valor, 2),
            "excedente": excedente,
            "total_ate_hoje": resumo_antes["total_ate_hoje"],
            "valor_pago": resumo_antes["valor_pago"],
            "valor_vale": resumo_antes["valor_vale"],
        })

    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)
    numero_lancamento = _proximo_numero_lancamento(session, dados.data_pagamento.year)
    session.add(DiariaPagamento(
        diaria_id=diaria_id, data_pagamento=dados.data_pagamento, valor=dados.valor,
        observacao=dados.observacao, numero_lancamento_gerado=numero_lancamento,
        conta_corrente_id=conta_corrente.id if conta_corrente else None, fazenda_id=fazenda_id,
    ))
    # Pagamento de diária já nasce quitado — reflete direto em Contas Pagas/relatórios.
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Diária — {pessoa.nome}",
        data_vencimento=dados.data_pagamento,
        data_competencia=dados.data_pagamento.replace(day=1),
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Diária",
        centro_custo=diaria.centro_custo,
        valor_total=dados.valor,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        data_pagamento=dados.data_pagamento,
        valor_pago=dados.valor,
        conta_bancaria=rotulo_conta_corrente(conta_corrente) if conta_corrente else None,
        fazenda_id=fazenda_id,
    ))
    session.commit()
    # `numero_lancamento_gerado` no topo (fora do resumo) — é o que a tela
    # usa pra anexar o comprovante logo em seguida via o mecanismo genérico
    # POST /financeiro/lancamentos/{numero_lancamento}/anexos, sem precisar
    # adivinhar qual dos pagamentos da lista é o que acabou de ser criado.
    return {**_resumo_diaria(session, diaria, pessoa.nome), "numero_lancamento_gerado": numero_lancamento}


# ---------------------------------------------------------------------------
# Calendário de dias trabalhados/folga da diária — modelo esparso (só existe
# linha de exceção pro dia que FOGE do padrão trabalhado). Convive com o
# modelo legado de contagem cega: `Diaria.controle_por_dia_desde` marca a
# partir de quando o calendário manda (None = diária nunca tocou o
# calendário, 100% regra antiga). Ver `_resumo_diaria` para o dispatch entre
# as duas regras.
# ---------------------------------------------------------------------------
class DiariaDiasPutIn(BaseModel):
    periodo_inicio: date
    periodo_fim: date
    dias_nao_trabalhados: list[date] = []
    # Meia diária — metade do valor de uma diária cheia (ver _fracao_dia).
    dias_meia_diaria: list[date] = []
    confirmar_periodo_pago: bool = False


@router.get("/diarias/{diaria_id}/dias")
def obter_dias_diaria(
    diaria_id: int, modo: str = "completo", desde: date | None = None, ate: date | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    diaria = _diaria_ou_404(session, diaria_id, fazenda_id)
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    hoje = date.today()
    hoje_ou_fim = min(hoje, diaria.data_fim) if diaria.data_fim else hoje
    ultima_folga = _ultima_folga_diaria(session, diaria.id, hoje_ou_fim)
    if modo == "ultimo_periodo":
        periodo_inicio = (ultima_folga + timedelta(days=1)) if ultima_folga else diaria.data_inicio
        periodo_fim = hoje_ou_fim
    else:
        modo = "completo"
        periodo_inicio = max(desde or diaria.data_inicio, diaria.data_inicio)
        periodo_fim = min(ate or hoje_ou_fim, hoje_ou_fim)
    pago_ate = _pago_ate_diaria(session, diaria.id)
    fracao_no_periodo = {
        e.data: _fracao_dia(e) for e in session.exec(
            select(DiariaDia).where(
                DiariaDia.diaria_id == diaria.id, DiariaDia.trabalhado == False,  # noqa: E712
                DiariaDia.data >= periodo_inicio, DiariaDia.data <= periodo_fim,
            )
        ).all()
    }
    dias = []
    cursor = periodo_inicio
    soma_fracao = 0.0
    while cursor <= periodo_fim:
        fracao = fracao_no_periodo.get(cursor, 1.0)
        soma_fracao += fracao
        dias.append({
            "data": cursor,
            "trabalhado": fracao == 1.0,
            "meia_diaria": fracao == 0.5,
            "pago": pago_ate is not None and cursor <= pago_ate,
        })
        cursor += timedelta(days=1)
    dias_trabalhados_periodo = sum(1 for x in dias if x["trabalhado"])
    dias_meia_periodo = sum(1 for x in dias if x["meia_diaria"])
    dias_folga_periodo = len(dias) - dias_trabalhados_periodo - dias_meia_periodo
    return {
        "diaria_id": diaria.id,
        "pessoa_nome": pessoa.nome if pessoa else "—",
        "valor_diaria": diaria.valor_diaria,
        "data_inicio": diaria.data_inicio,
        "data_fim": diaria.data_fim,
        "hoje": hoje,
        "modo": modo,
        "periodo_inicio": periodo_inicio,
        "periodo_fim": periodo_fim,
        "ultima_folga": ultima_folga,
        "controle_por_dia_desde": diaria.controle_por_dia_desde,
        "nunca_auditado": diaria.controle_por_dia_desde is None,
        "pago_ate": pago_ate,
        "dias": dias,
        "resumo_periodo": {
            "dias_no_periodo": len(dias),
            "dias_trabalhados": dias_trabalhados_periodo,
            "dias_folga": dias_folga_periodo,
            "dias_meia_diaria": dias_meia_periodo,
            "valor_periodo": round(soma_fracao * diaria.valor_diaria, 2),
        },
    }


@router.put("/diarias/{diaria_id}/dias")
def salvar_dias_diaria(
    diaria_id: int, dados: DiariaDiasPutIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Substitui (replace, não merge) o estado dos dias no período informado
    — o cliente sempre manda o estado corrigido inteiro da janela visível."""
    diaria = _diaria_ou_404(session, diaria_id, fazenda_id)
    _exigir_periodo_aberto(session, diaria, "corrigir os dias trabalhados")
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    if dados.periodo_inicio > dados.periodo_fim:
        raise HTTPException(status_code=400, detail="Período inválido: início não pode ser depois do fim")
    hoje = date.today()
    hoje_ou_fim = min(hoje, diaria.data_fim) if diaria.data_fim else hoje
    if dados.periodo_inicio < diaria.data_inicio:
        raise HTTPException(status_code=400, detail="Não dá para auditar dia antes do início da diária")
    if dados.periodo_fim > hoje_ou_fim:
        raise HTTPException(status_code=400, detail="Não dá para auditar dia que ainda não aconteceu")
    dias_informados: set[date] = set()
    for dia in dados.dias_nao_trabalhados:
        if dia < dados.periodo_inicio or dia > dados.periodo_fim:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} fora do período informado")
        if dia in dias_informados:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} duplicada em dias_nao_trabalhados")
        dias_informados.add(dia)
    dias_meia: set[date] = set()
    for dia in dados.dias_meia_diaria:
        if dia < dados.periodo_inicio or dia > dados.periodo_fim:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} fora do período informado")
        if dia in dias_informados or dia in dias_meia:
            raise HTTPException(status_code=400, detail=f"Data {dia.isoformat()} não pode ser folga e meia diária ao mesmo tempo")
        dias_meia.add(dia)
    pago_ate = _pago_ate_diaria(session, diaria_id)
    if pago_ate is not None and dados.periodo_inicio <= pago_ate and not dados.confirmar_periodo_pago:
        raise HTTPException(
            status_code=409,
            detail=f"Este período já tem pagamento registrado (até {pago_ate}). Alterar os dias trabalhados vai "
                   "mudar o total apurado e o saldo devedor de um período já quitado. Confirme se quiser prosseguir.",
        )

    # 1) Substitui as exceções do período (replace, não merge).
    existentes = session.exec(
        select(DiariaDia).where(
            DiariaDia.diaria_id == diaria_id,
            DiariaDia.data >= dados.periodo_inicio, DiariaDia.data <= dados.periodo_fim,
        )
    ).all()
    for e in existentes:
        session.delete(e)
    for dia in sorted(dias_informados):
        session.add(DiariaDia(
            diaria_id=diaria_id, data=dia, trabalhado=False, fracao=0.0, usuario_id=user.id, fazenda_id=fazenda_id,
        ))
    for dia in sorted(dias_meia):
        session.add(DiariaDia(
            diaria_id=diaria_id, data=dia, trabalhado=False, fracao=0.5, usuario_id=user.id, fazenda_id=fazenda_id,
        ))

    # 2) Marca/recua o marco do calendário — nunca avança, só recua, e nunca
    # invade um período de auditoria legada já RESPONDIDO (mantém as duas
    # janelas disjuntas).
    _, ultimo_respondido_fim = _dias_confirmados_diaria(session, diaria_id)
    corte_candidato = dados.periodo_inicio
    if ultimo_respondido_fim is not None and ultimo_respondido_fim >= corte_candidato:
        corte_candidato = ultimo_respondido_fim + timedelta(days=1)
    diaria.controle_por_dia_desde = (
        min(diaria.controle_por_dia_desde, corte_candidato) if diaria.controle_por_dia_desde else corte_candidato
    )
    session.add(diaria)

    # 3) Descarta auditorias pendentes (nunca respondidas) que ficaram
    # cobertas pelo calendário — nada se perde porque nunca foram respondidas.
    pendentes_superadas = session.exec(
        select(DiariaAuditoria).where(
            DiariaAuditoria.diaria_id == diaria_id, DiariaAuditoria.dias_trabalhados.is_(None),
            DiariaAuditoria.periodo_fim >= diaria.controle_por_dia_desde,
        )
    ).all()
    for a in pendentes_superadas:
        session.delete(a)

    session.commit()
    session.refresh(diaria)
    return _resumo_diaria(session, diaria, pessoa.nome if pessoa else "—")


# ---------------------------------------------------------------------------
# Vale (adiantamento) para Empreitada/Contrato/Diária — mesma ideia do Vale de
# funcionário, mas sem competência/folha mensal para descontar: o valor é
# abatido direto da(s) próxima(s) parcela(s)/etapa(s) pendente(s) (Empreitada/
# Contrato) ou do saldo devedor acumulado (Diária).
# ---------------------------------------------------------------------------
ORIGENS_VALE_AVULSO = ["empreitada", "contrato", "diaria"]
FORMAS_PAGAMENTO_VALE_AVULSO = ["dinheiro", "pix", "transferencia", "desconto_proximo_pagamento"]


class ValeAvulsoIn(BaseModel):
    origem_tipo: str  # empreitada | contrato | diaria
    origem_id: int
    valor: float
    forma_pagamento: str  # dinheiro | pix | transferencia | desconto_proximo_pagamento
    data_pagamento: date
    observacao: str | None = None
    # Conta bancária da fazenda de onde sai o vale — obrigatória quando o
    # dinheiro sai AGORA (dinheiro/pix/transferência); irrelevante para
    # "desconto_proximo_pagamento" (não há saída de caixa nenhuma agora — ver
    # `_validar_conta_vale_avulso`).
    conta_corrente_id: int | None = None
    # Só usados em PUT (edição) quando `valor` diverge do valor atual do vale
    # — mesma semântica de ValeParcelaEditIn.acao em rh_folha.py: "conceder"
    # (o vale muda de valor, o alvo absorve a diferença naturalmente ao
    # reaplicar o abatimento — comportamento padrão, sem redistribuir mais
    # nada); "redistribuir_igual" (depois de reaplicar, redivide igualmente
    # as parcelas/etapas do alvo ainda pendentes); "redistribuir_livre"
    # (idem, mas com o valor de cada parcela/etapa informado explicitamente).
    acao: str | None = None
    valores_itens: dict[int, float] | None = None
    confirmar: bool = False
    # Confirmação de um risco DIFERENTE de `confirmar` (que só trata "o valor
    # mudou"): o vale ser maior que o saldo pendente do alvo, ou seja, sair
    # dinheiro do caixa sem parcela/etapa para abater. Flag própria de
    # propósito — confirmar a mudança de valor não pode valer como
    # confirmação de um aviso que o usuário nunca viu. Ver
    # `_exigir_confirmacao_vale_acima_do_pendente`.
    confirmar_excedente: bool = False


def _info_parcelas_vale_avulso(session: Session, vale: ValeAvulso) -> dict:
    """Pra exibir no relatório de vales: quantas parcelas/etapas tem a
    origem do vale avulso, e a qual(is) delas ele se refere (via
    ValeAvulsoAbatimento) — só se aplica a empreitada/contrato; diária não
    tem parcela agendada, então volta sempre vazio."""
    if vale.origem_tipo == "diaria":
        # Diária não abate parcela nenhuma (o vale entra como `valor_vale` no
        # saldo devedor, ver `_resumo_diaria`) — "abatido x não abatido" não
        # se aplica, então vai None em vez de 0 para não parecer sobra.
        return {
            "total_parcelas_origem": None, "parcelas_referenciadas": [],
            "valor_abatido": None, "valor_nao_abatido": None,
        }
    if vale.origem_tipo == "empreitada":
        empreitada = session.get(Empreitada, vale.origem_id)
        if empreitada and empreitada.tipo_pagamento == "por_etapa":
            todos = session.exec(
                select(EmpreitadaEtapa).where(EmpreitadaEtapa.empreitada_id == vale.origem_id).order_by(EmpreitadaEtapa.ordem, EmpreitadaEtapa.id)
            ).all()
            item_tipo = "empreitada_etapa"
        else:
            todos = session.exec(
                select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == vale.origem_id).order_by(EmpreitadaParcela.data_vencimento)
            ).all()
            item_tipo = "empreitada_parcela"
    else:
        todos = session.exec(
            select(ContratoParcela).where(ContratoParcela.contrato_id == vale.origem_id).order_by(ContratoParcela.data_vencimento)
        ).all()
        item_tipo = "contrato_parcela"

    posicao = {item.id: i + 1 for i, item in enumerate(todos)}
    abatimentos = session.exec(select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale.id)).all()
    referenciadas = [
        {"numero_parcela": posicao.get(ab.item_id), "valor_abatido": ab.valor_abatido}
        for ab in abatimentos if ab.item_tipo == item_tipo
    ]
    # `valor_nao_abatido` é a sobra de um vale maior que o saldo pendente do
    # alvo (ver `_exigir_confirmacao_vale_acima_do_pendente`): dinheiro que
    # saiu do caixa e não reduziu parcela nenhuma. Antes ele simplesmente
    # sumia; expor aqui é o que faz a sobra confirmada continuar visível no
    # relatório de vales em vez de virar um furo silencioso.
    valor_abatido = round(sum(r["valor_abatido"] for r in referenciadas), 2)
    return {
        "total_parcelas_origem": len(todos), "parcelas_referenciadas": referenciadas,
        "valor_abatido": valor_abatido,
        "valor_nao_abatido": round(vale.valor - valor_abatido, 2),
    }


def _listar_vales_avulsos(session: Session, origem_tipo: str, origem_id: int) -> list[dict]:
    vales = session.exec(
        select(ValeAvulso)
        .where(ValeAvulso.origem_tipo == origem_tipo, ValeAvulso.origem_id == origem_id)
        .order_by(ValeAvulso.data_pagamento)
    ).all()
    return [{**v.model_dump(), **_info_parcelas_vale_avulso(session, v)} for v in vales]


def _numeros_pagos(session: Session, numeros: list[str], fazenda_id: int | None) -> set[str]:
    """Quais destes números de lançamento já foram BAIXADOS no Financeiro.

    É leitura, e é ela que decide o que ainda está em aberto: quais parcelas
    de empreitada/contrato aceitam abatimento de vale avulso, e se a exclusão
    da empreitada/contrato inteiro é liberada ou recusada com "estorne a baixa
    primeiro".

    O RECORTE DE FAZENDA É OBRIGATÓRIO (parâmetro sem valor padrão, para
    nenhum chamador novo esquecer dele) e vai DENTRO da consulta, junto do
    `IN`. O `numero_lancamento` é sequencial por ano, não é chave global: sem
    o recorte, a BAIXA de um lançamento homônimo de outra fazenda marcava como
    "paga" uma parcela que está em aberto aqui. O erro falha fechado — no pior
    caso esconde uma parcela aberta, nunca deixa pagar duas vezes — mas
    esconder parcela é esconder dinheiro devido, e a mensagem de recusa da
    exclusão passava a citar um lançamento que o usuário não consegue nem
    enxergar para estornar. Mesmo padrão e mesma justificativa de
    `_conta_do_numero` (rh_folha.py).

    `fazenda_id` None é legítimo aqui: significa instalação sem nenhuma
    fazenda cadastrada (ver `fazenda.auth.multifazenda_provisionado`), onde
    `fazenda_id == None` vira `IS NULL` e casa exatamente as linhas desse
    ambiente. Quem APAGA a partir deste resultado recusa o None antes de
    chegar aqui (ver `fazenda.rules.exclusao_tipos.pessoal`).
    """
    if not numeros:
        return set()
    contas = session.exec(
        select(ContaGerencial).where(
            ContaGerencial.numero_lancamento.in_(numeros),
            ContaGerencial.fazenda_id == fazenda_id,
        )
    ).all()
    return {c.numero_lancamento for c in contas if c.valor_pago is not None}


def _itens_pendentes_vale_avulso(
    session: Session, origem_tipo: str, origem_id: int, fazenda_id: int | None,
) -> tuple[str, list]:
    """Retorna (item_tipo, itens pendentes em ordem de vencimento) para o
    abatimento/reversão de um vale avulso de Empreitada/Contrato.

    `fazenda_id` só existe para repassar a `_numeros_pagos` — as consultas de
    parcela/etapa aqui filtram por `empreitada_id`/`contrato_id`, que são
    chaves globais de verdade (PK), e por isso já são naturalmente do
    inquilino certo."""
    if origem_tipo == "empreitada":
        empreitada = session.get(Empreitada, origem_id)
        if empreitada and empreitada.tipo_pagamento == "por_etapa":
            itens = session.exec(
                select(EmpreitadaEtapa)
                .where(EmpreitadaEtapa.empreitada_id == origem_id, EmpreitadaEtapa.concluida == False)  # noqa: E712
                .order_by(EmpreitadaEtapa.ordem, EmpreitadaEtapa.id)
            ).all()
            return "empreitada_etapa", list(itens)
        todas = session.exec(
            select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == origem_id).order_by(EmpreitadaParcela.data_vencimento)
        ).all()
        pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in todas if p.numero_lancamento_gerado], fazenda_id)
        return "empreitada_parcela", [p for p in todas if p.numero_lancamento_gerado not in pagos]
    if origem_tipo == "contrato":
        todas = session.exec(
            select(ContratoParcela).where(ContratoParcela.contrato_id == origem_id).order_by(ContratoParcela.data_vencimento)
        ).all()
        pagos = _numeros_pagos(session, [p.numero_lancamento_gerado for p in todas if p.numero_lancamento_gerado], fazenda_id)
        return "contrato_parcela", [p for p in todas if p.numero_lancamento_gerado not in pagos]
    return "", []


def _modelo_item_vale_avulso(item_tipo: str):
    return {"empreitada_parcela": EmpreitadaParcela, "empreitada_etapa": EmpreitadaEtapa, "contrato_parcela": ContratoParcela}[item_tipo]


def _sincronizar_conta_do_item(session: Session, item) -> None:
    """Alinha o lançamento (ContaGerencial) da parcela/etapa ao novo valor
    dela — só o que ainda não foi pago.

    O recorte de fazenda sai do PRÓPRIO item (`item.fazenda_id`), dentro da
    consulta, e não de um `fazenda_id` recebido: o lançamento é o espelho
    financeiro desta parcela/etapa, então ele é, por construção, do mesmo
    inquilino que ela. É o padrão já usado em `_recalcular_folha` e
    `_conta_do_encerramento` — a linha-pai já veio recortada do endpoint, e o
    espelho segue a linha. O que não pode existir é a busca SÓ pelo número:
    ele é sequencial por ano e se repete entre fazendas numa base importada,
    e daqui sai uma reescrita de valor de conta a pagar.

    Chega aqui por caminhos que não têm o `fazenda_id` do token à mão
    (`_reverter_vale_avulso` é chamado até de `rules/exclusao_tipos/pessoal.py`),
    e é por isso que a âncora é o item, e não um parâmetro propagado."""
    numero = getattr(item, "numero_lancamento_gerado", None)
    if numero:
        conta = session.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == numero,
                ContaGerencial.fazenda_id == item.fazenda_id,
            )
        ).first()
        if conta and conta.valor_pago is None:
            conta.valor_total = item.valor
            session.add(conta)


def _conta_paga_do_item(session: Session, item) -> ContaGerencial | None:
    """Lançamento (ContaGerencial) da parcela/etapa que JÁ foi baixado, ou
    None. É o espelho exato do ponto cego de `_sincronizar_conta_do_item`
    acima: conta com `valor_pago` preenchido é a única que ele se recusa a
    atualizar — logo, é exatamente onde mexer no valor da parcela quebra a
    igualdade entre o que o sistema diz que se deve e o que já foi pago."""
    numero = getattr(item, "numero_lancamento_gerado", None)
    if not numero:
        return None
    # Mesmo recorte por `item.fazenda_id` de `_sincronizar_conta_do_item` (ver
    # o porquê lá): sem ele, a conta PAGA de outra fazenda com o mesmo número
    # bloquearia — ou, pior, deixaria de bloquear — a reversão errada.
    conta = session.exec(
        select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == numero,
            ContaGerencial.fazenda_id == item.fazenda_id,
        )
    ).first()
    return conta if conta is not None and conta.valor_pago is not None else None


def _bloquear_reversao_de_abatimento_pago(session: Session, vale_avulso_id: int) -> None:
    """
    Recusa desfazer o abatimento de um vale que já caiu numa parcela/etapa
    PAGA.

    Por que travar em vez de "consertar por baixo": `_reverter_vale_avulso`
    devolve o valor abatido à parcela, mas `_sincronizar_conta_do_item` só
    atualiza contas ainda em aberto. Numa parcela já quitada o resultado é
    uma parcela de R$ 2.000 contra um lançamento pago de R$ 1.500 — uma
    dívida de R$ 500 que nasce no banco e que ninguém vai cobrar de
    ninguém. Ajustar a conta paga também não serve: o dinheiro JÁ SAIU do
    caixa; quem tem que decidir o que fazer com isso é a pessoa, não o
    endpoint.

    Mesmo tratamento (e mesmo motivo) do vale de funcionário, que bloqueia
    com 400 quando a competência do vale já está paga — ver
    `_vale_competencia_paga` em rh_folha.py. E mesma regra que a exclusão de
    Empreitada/Contrato já aplicava em `rules/exclusao_tipos/pessoal.py`
    ("parcela paga → 400 mandando estornar a baixa"): a regra já existia no
    sistema, só não valia para editar/excluir o vale em si. A diferença é que
    lá o bloqueio olha TODAS as parcelas do alvo, e aqui só as que ESTE vale
    abateu — pagar uma parcela que o vale não tocou não tem por que impedir
    o estorno dele.

    A mensagem aponta o lançamento exato a estornar (POST
    /financeiro/lancamentos/{id}/estornar, o botão "Estornar" em Contas a
    Pagar), para a operação ficar possível depois do estorno, e só depois dele.
    """
    abatimentos = session.exec(
        select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale_avulso_id)
    ).all()
    for ab in abatimentos:
        Modelo = _modelo_item_vale_avulso(ab.item_tipo)
        item = session.get(Modelo, ab.item_id)
        if item is None:
            continue
        conta = _conta_paga_do_item(session, item)
        if conta is not None:
            rotulo = "etapa" if ab.item_tipo == "empreitada_etapa" else "parcela"
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Este vale de R$ {round(ab.valor_abatido, 2):.2f} já foi abatido de uma {rotulo} "
                    f"que JÁ FOI PAGA (lançamento {conta.numero_lancamento}, "
                    f"baixado em {conta.data_pagamento} por R$ {conta.valor_pago:.2f}). "
                    f"Editar ou excluir o vale agora devolveria o valor à {rotulo} sem devolver o "
                    "dinheiro que já saiu do caixa, criando uma dívida que ninguém vai cobrar. "
                    f"Estorne o pagamento do lançamento {conta.numero_lancamento} em Contas a Pagar "
                    "e refaça a operação."
                ),
            )


def _saldo_pendente_do_alvo(
    session: Session, origem_tipo: str, origem_id: int, fazenda_id: int | None,
    vale_avulso_id: int | None = None,
) -> float | None:
    """
    Total ainda em aberto (soma das parcelas/etapas pendentes) do alvo de um
    vale avulso — quanto de fato existe para abater. `None` quando a pergunta
    não se aplica: diária não tem parcela agendada (o vale só soma ao saldo
    devedor, ver `_resumo_diaria`) e alvo sem nenhum item também não tem
    saldo a comparar.

    `vale_avulso_id` é para a EDIÇÃO: o PUT reverte o vale antes de reaplicar,
    então o pendente relevante é o de DEPOIS da reversão — o que está em
    aberto hoje mais o que este vale devolverá às parcelas/etapas que ainda
    estão pendentes. Calculado por aritmética justamente para a checagem
    poder acontecer ANTES de qualquer escrita (um 409 no meio do
    reverter/reaplicar deixaria o vale sem abatimento nenhum).

    `fazenda_id` desce até `_numeros_pagos`, que precisa dele para não contar
    como paga uma parcela cujo lançamento homônimo foi baixado em OUTRA
    fazenda — o pendente sairia menor do que é e o usuário levaria um 409 de
    "vale acima do pendente" que não existe.
    """
    if origem_tipo == "diaria":
        return None
    item_tipo, itens = _itens_pendentes_vale_avulso(session, origem_tipo, origem_id, fazenda_id)
    if not item_tipo or not itens:
        return None if not item_tipo else 0.0
    total = round(sum(i.valor for i in itens), 2)
    if vale_avulso_id is not None:
        ids_pendentes = {i.id for i in itens}
        devolvido = sum(
            ab.valor_abatido for ab in session.exec(
                select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale_avulso_id)
            ).all()
            if ab.item_tipo == item_tipo and ab.item_id in ids_pendentes
        )
        total = round(total + devolvido, 2)
    return total


def _exigir_confirmacao_vale_acima_do_pendente(
    session: Session, origem_tipo: str, origem_id: int, valor: float, confirmado: bool,
    fazenda_id: int | None, vale_avulso_id: int | None = None,
) -> None:
    """
    Vale maior que o saldo pendente do alvo: pede confirmação explícita (409)
    em vez de engolir a sobra.

    REGRA ESCOLHIDA e por quê: `_aplicar_vale_avulso` consome as parcelas
    pendentes até acabar o valor e simplesmente ABANDONA o `restante` — nem
    erro, nem aviso — enquanto `_sincronizar_conta_vale_avulso` lança a saída
    de caixa pelo valor CHEIO. Adiantar R$ 5.000 num contrato com R$ 3.000
    pendentes tirava R$ 5.000 do caixa e abatia R$ 3.000: R$ 2.000 sumiam do
    controle.

    Não recusamos de vez porque adiantar acima do pendente é legítimo com
    frequência (empreitada por etapa cujas próximas etapas ainda nem foram
    cadastradas, contrato que vai ser prorrogado, adiantamento de fim de ano).
    Também não registramos a sobra em silêncio: silêncio é exatamente o bug.
    Então seguimos o precedente do próprio módulo — 409 + flag de confirmação,
    como `confirmar_periodo_pago` em `salvar_dias_diaria` e o `confirmar` de
    `atualizar_vale_avulso` — dizendo QUANTO é o pendente e QUANTO vai sobrar.
    Confirmado, o vale passa e a sobra deixa de ser invisível: aparece como
    `valor_nao_abatido` no relatório de vales (ver
    `_info_parcelas_vale_avulso`).
    """
    if confirmado:
        return
    pendente = _saldo_pendente_do_alvo(session, origem_tipo, origem_id, fazenda_id, vale_avulso_id)
    if pendente is None:
        return
    excedente = round(round(valor, 2) - pendente, 2)
    if excedente <= 0:
        return
    alvo = "deste contrato" if origem_tipo == "contrato" else "desta empreitada"
    # Pendente zero é o caso do contrato sem frequência definida (nenhuma
    # parcela agendada) e o da empreitada com tudo já concluído/pago: aí o
    # vale inteiro é sobra, e dizer "maior que R$ 0,00" confundiria mais do
    # que explicaria.
    pendente_zerado = pendente <= 0
    raise HTTPException(status_code=409, detail={
        "mensagem": (
            (
                f"Não há parcela/etapa em aberto {alvo} para abater este vale de "
                f"R$ {round(valor, 2):.2f} — o valor inteiro sairá do caixa sem reduzir nada. "
                if pendente_zerado else
                f"O vale de R$ {round(valor, 2):.2f} é maior que o saldo pendente {alvo} "
                f"(R$ {pendente:.2f}). Só R$ {pendente:.2f} serão abatidos das parcelas/etapas "
                f"em aberto; os outros R$ {excedente:.2f} sairão do caixa sem nada para abater. "
            )
            + "Confirme se quiser lançar assim mesmo."
        ),
        "saldo_pendente": pendente,
        "valor_informado": round(valor, 2),
        "excedente": excedente,
    })


def _aplicar_vale_avulso(
    session: Session, vale_avulso_id: int, origem_tipo: str, origem_id: int, valor: float,
    fazenda_id: int | None = None,
) -> None:
    """
    Abate `valor` da(s) próxima(s) parcela(s)/etapa(s) PENDENTE(S), na ordem em
    que vencem — mesmo efeito do vale de funcionário (reduzir o valor líquido
    a receber), só que aqui não há um documento mensal (folha) para descontar,
    então o alvo é o próprio saldo em aberto de cada entidade:
    - Empreitada: reduz as próximas EmpreitadaParcela (ou EmpreitadaEtapa, se
      "por_etapa") ainda não pagas, e sincroniza a ContaGerencial vinculada
      (só quando ela já existe e ainda não foi paga).
    - Contrato: mesma lógica com ContratoParcela.
    - Diária: não há parcela agendada (o pagamento é sob demanda) — o valor só
      soma ao "saldo abatido", já calculado em `_resumo_diaria`.

    Cada abatimento é registrado em `ValeAvulsoAbatimento`, para permitir
    reverter exatamente ao editar/excluir o vale (ver `_reverter_vale_avulso`).
    """
    restante = round(valor, 2)
    if restante <= 0 or origem_tipo == "diaria":
        return

    item_tipo, itens = _itens_pendentes_vale_avulso(session, origem_tipo, origem_id, fazenda_id)
    if not item_tipo:
        return

    # Sobre o `restante` que pode sobrar deste laço (vale maior que o total
    # pendente): NÃO é tratado aqui de propósito. Quem decide é
    # `_exigir_confirmacao_vale_acima_do_pendente`, chamado pelos endpoints
    # ANTES de qualquer escrita — chegar até aqui já significa "usuário viu
    # quanto ia sobrar e confirmou". A sobra fica visível como
    # `valor_nao_abatido` no relatório de vales.
    #
    # CONHECIDO, fora do escopo desta correção: `min(item.valor, restante)`
    # pode zerar a parcela/etapa, e a ContaGerencial dela fica valendo
    # R$ 0,00 — viva em Contas a Pagar e na Agenda. Apagá-la aqui não serve:
    # a linha precisa sobreviver para `_reverter_vale_avulso` ter onde
    # devolver o valor. A correção certa é as listagens ignorarem conta
    # zerada (routers/financeiro.py e routers/agenda.py), fora deste arquivo.
    for item in itens:
        if restante <= 0:
            break
        abatido = min(item.valor, restante)
        if abatido <= 0:
            continue
        item.valor = round(item.valor - abatido, 2)
        restante = round(restante - abatido, 2)
        session.add(item)
        _sincronizar_conta_do_item(session, item)
        session.add(ValeAvulsoAbatimento(
            vale_avulso_id=vale_avulso_id, item_tipo=item_tipo, item_id=item.id, valor_abatido=abatido,
            fazenda_id=fazenda_id,
        ))


def _redistribuir_itens_pendentes_igual(session: Session, itens: list) -> None:
    """Como `_redistribuir_parcelas_pendentes` (empreitada/contrato), mas sem
    tocar `data_vencimento` — serve tanto para parcela quanto para etapa
    (EmpreitadaEtapa não tem data de vencimento própria). Também não mexe em
    `valor_contratado`, pelo mesmo motivo explicado lá."""
    if len(itens) < 2:
        raise HTTPException(status_code=400, detail="É preciso ao menos 2 parcelas/etapas pendentes para redistribuir.")
    total = round(sum(i.valor for i in itens), 2)
    valor_base = round(total / len(itens), 2)
    restante = total
    for i, item in enumerate(itens):
        valor = valor_base if i < len(itens) - 1 else round(restante, 2)
        restante = round(restante - valor, 2)
        item.valor = valor
        session.add(item)
        _sincronizar_conta_do_item(session, item)


def _redistribuir_itens_pendentes_livre(session: Session, itens: list, valores: dict[int, float]) -> None:
    ids_pendentes = {i.id for i in itens}
    if set(valores.keys()) != ids_pendentes:
        raise HTTPException(status_code=400, detail="Informe o valor de todas as parcelas/etapas pendentes, e só delas.")
    for item in itens:
        novo = valores[item.id]
        if novo < 0:
            raise HTTPException(status_code=400, detail="Valor de parcela/etapa não pode ser negativo.")
        item.valor = round(novo, 2)
        session.add(item)
        _sincronizar_conta_do_item(session, item)


def _reverter_vale_avulso(session: Session, vale_avulso_id: int) -> None:
    """Desfaz o efeito de `_aplicar_vale_avulso`: devolve a cada item exatamente
    o valor que foi abatido dele (registrado em ValeAvulsoAbatimento), na
    ordem inversa em que foi abatido, e sincroniza a ContaGerencial vinculada.

    Recusa-se a agir quando algum desses itens já foi PAGO — ver
    `_bloquear_reversao_de_abatimento_pago`. A trava mora aqui dentro (e não
    só nos endpoints) porque esta função é a única que mexe no valor da
    parcela sem passar pela tela: qualquer chamador novo herda a proteção sem
    precisar lembrar dela. Como ela levanta ANTES de qualquer escrita, o
    reverter continua sendo tudo-ou-nada."""
    _bloquear_reversao_de_abatimento_pago(session, vale_avulso_id)
    abatimentos = session.exec(
        select(ValeAvulsoAbatimento).where(ValeAvulsoAbatimento.vale_avulso_id == vale_avulso_id).order_by(ValeAvulsoAbatimento.id.desc())
    ).all()
    for ab in abatimentos:
        Modelo = _modelo_item_vale_avulso(ab.item_tipo)
        item = session.get(Modelo, ab.item_id)
        if item:
            item.valor = round(item.valor + ab.valor_abatido, 2)
            session.add(item)
            _sincronizar_conta_do_item(session, item)
        session.delete(ab)


@router.get("/vale-avulso")
def listar_vales_avulsos_endpoint(
    origem_tipo: str, origem_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    if origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is not None:
        _origem_vale_avulso(session, origem_tipo, origem_id, fazenda_id)
    return _listar_vales_avulsos(session, origem_tipo, origem_id)


def _origem_vale_avulso(session: Session, origem_tipo: str, origem_id: int, fazenda_id: int | None):
    """Busca a origem (Empreitada/Contrato/Diária) de um vale avulso já
    verificando que pertence à `fazenda_id` informada — 404 se não existir ou
    for de outra fazenda."""
    if origem_tipo == "empreitada":
        origem = session.get(Empreitada, origem_id)
    elif origem_tipo == "contrato":
        origem = session.get(Contrato, origem_id)
    else:
        origem = session.get(Diaria, origem_id)
    if not origem or (origem.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail=f"{origem_tipo.capitalize()} não encontrado(a)")
    return origem


def _validar_conta_vale_avulso(
    session: Session, forma_pagamento: str, conta_corrente_id: int | None, fazenda_id: int | None,
) -> ContaCorrente | None:
    """Análogo a `_validar_conta_vale` (rh_folha.py) para o vale avulso —
    obrigatória só quando o dinheiro sai AGORA (dinheiro/pix/transferência);
    "desconto_proximo_pagamento" não movimenta banco nenhum na hora do vale
    (o efeito é só reduzir a próxima parcela/etapa/saldo devedor)."""
    if forma_pagamento == "desconto_proximo_pagamento":
        return None
    if not conta_corrente_id:
        raise HTTPException(status_code=400, detail="Selecione a conta bancária de onde sai o vale.")
    conta = session.get(ContaCorrente, conta_corrente_id)
    if not conta or (conta.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada")
    return conta


def _sincronizar_conta_vale_avulso(
    session: Session, vale: ValeAvulso, pessoa_nome: str, conta: ContaCorrente | None, fazenda_id: int | None,
) -> None:
    """
    Cria (ou, numa edição, atualiza) o lançamento (ContaGerencial) que
    representa a SAÍDA de caixa do vale avulso — análogo a
    `_sincronizar_conta_vale` (rh_folha.py) e a `registrar_pagamento_diaria`
    acima: já nasce PAGO, porque o vale é entregue no ato.

    NÃO duplica valor no extrato: `_aplicar_vale_avulso` só reduz a
    PRÓXIMA parcela/etapa (ou o saldo da diária) que ainda vai ser paga —
    exatamente como a folha de funcionário lança o líquido já descontado do
    vale. Antes desta função existir, o dinheiro do vale avulso saía do
    caixa/banco no ato e não aparecia em lugar nenhum do Financeiro; este
    lançamento é o que fecha esse furo. NÃO remova achando que é bug de
    duplicidade.

    Quando `conta` é None (forma_pagamento == "desconto_proximo_pagamento"),
    não há saída de caixa nenhuma a registrar — nenhum ContaGerencial é
    criado/mantido (removendo um lançamento de edição anterior, se houver).
    """
    # `_conta_do_numero` (rh_folha.py) filtra a fazenda DENTRO da consulta —
    # daqui sai tanto uma reescrita quanto um `session.delete()`, e o número
    # do lançamento sozinho não diz de quem é a conta (ver a docstring do
    # helper). Mesmo tratamento de `_sincronizar_conta_vale`.
    conta_existente = _conta_do_numero(session, vale.numero_lancamento_gerado, fazenda_id)

    if conta is None:
        if conta_existente:
            session.delete(conta_existente)
        vale.numero_lancamento_gerado = None
        session.add(vale)
        return

    descricao = f"Vale — {pessoa_nome} ({vale.origem_tipo})"
    if conta_existente:
        conta_existente.descricao = descricao
        conta_existente.fornecedor_cliente = pessoa_nome
        conta_existente.data_vencimento = vale.data_pagamento
        conta_existente.data_competencia = vale.data_pagamento.replace(day=1)
        conta_existente.valor_total = vale.valor
        conta_existente.data_pagamento = vale.data_pagamento
        conta_existente.valor_pago = vale.valor
        conta_existente.conta_bancaria = rotulo_conta_corrente(conta)
        conta_existente.forma_pagamento = vale.forma_pagamento
        session.add(conta_existente)
    else:
        numero_lancamento = _proximo_numero_lancamento(session, vale.data_pagamento.year)
        vale.numero_lancamento_gerado = numero_lancamento
        session.add(vale)
        session.add(ContaGerencial(
            numero_lancamento=numero_lancamento,
            descricao=descricao,
            data_vencimento=vale.data_pagamento,
            data_competencia=vale.data_pagamento.replace(day=1),
            fornecedor_cliente=pessoa_nome,
            tipo_documento="Vale avulso",
            centro_custo="Pecuária Leiteira",
            valor_total=vale.valor,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            data_pagamento=vale.data_pagamento,
            valor_pago=vale.valor,
            conta_bancaria=rotulo_conta_corrente(conta),
            forma_pagamento=vale.forma_pagamento,
            fazenda_id=fazenda_id,
        ))


@router.post("/vale-avulso")
def criar_vale_avulso(
    dados: ValeAvulsoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Lança um vale (adiantamento) para Empreitada/Contrato/Diária — análogo ao
    Vale de funcionário, permitindo controlar o que já foi adiantado a
    empreiteiros/contratados/diaristas antes do pagamento final.
    """
    if dados.origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    origem = _origem_vale_avulso(session, dados.origem_tipo, dados.origem_id, fazenda_id)
    conta = _validar_conta_vale_avulso(session, dados.forma_pagamento, dados.conta_corrente_id, fazenda_id)
    # Antes de gravar qualquer coisa: vale maior que o pendente precisa de
    # confirmação (senão a sobra sai do caixa e some do controle). A checagem
    # vem ANTES do `session.add(vale)` de propósito — um 409 depois dele
    # deixaria um vale órfão gravado, sem abatimento e sem lançamento.
    _exigir_confirmacao_vale_acima_do_pendente(
        session, dados.origem_tipo, dados.origem_id, dados.valor, dados.confirmar_excedente,
        fazenda_id=fazenda_id,
    )
    pessoa = session.get(Pessoa, origem.pessoa_id)

    vale = ValeAvulso(
        origem_tipo=dados.origem_tipo, origem_id=dados.origem_id, pessoa_id=origem.pessoa_id,
        valor=dados.valor, forma_pagamento=dados.forma_pagamento, data_pagamento=dados.data_pagamento,
        observacao=dados.observacao, conta_corrente_id=conta.id if conta else None,
        usuario_id=user.id, fazenda_id=fazenda_id,
    )
    session.add(vale)
    session.commit()
    session.refresh(vale)

    _aplicar_vale_avulso(session, vale.id, dados.origem_tipo, dados.origem_id, dados.valor, fazenda_id=vale.fazenda_id)
    # Gera (quando aplicável) o lançamento que faltava no extrato para a
    # saída de caixa do vale — ver `_sincronizar_conta_vale_avulso`.
    _sincronizar_conta_vale_avulso(session, vale, pessoa.nome if pessoa else "—", conta, fazenda_id)
    session.commit()

    if dados.origem_tipo == "empreitada":
        resultado = _serializar_empreitada(session, origem)
    elif dados.origem_tipo == "contrato":
        resultado = _serializar_contrato(session, origem)
    else:
        resultado = _resumo_diaria(session, origem, pessoa.nome if pessoa else "—")
    return {"vale": vale.model_dump(), "origem": resultado}


@router.get("/vale-avulso/todos")
def listar_todos_vales_avulsos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Relatório unificado de vales avulsos (Empreitada/Contrato/Diária), para
    aparecer junto do Relatório de vales e descontos (vale de funcionário)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ValeAvulso)
    if fazenda_id is not None:
        query = query.where(ValeAvulso.fazenda_id == fazenda_id)
    vales = session.exec(query.order_by(ValeAvulso.data_pagamento.desc())).all()
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    empreitadas = {e.id: e.descricao for e in session.exec(select(Empreitada)).all()}
    contratos = {c.id: c.descricao for c in session.exec(select(Contrato)).all()}
    origens_lancamento = origens_lancamento_por_vale(session, {v.id for v in vales}, "vale_avulso_id")
    saida = []
    for v in vales:
        if v.origem_tipo == "empreitada":
            origem_descricao = f"Empreitada — {empreitadas.get(v.origem_id, '—')}"
        elif v.origem_tipo == "contrato":
            origem_descricao = f"Contrato — {contratos.get(v.origem_id, '—')}"
        else:
            origem_descricao = "Diária"
        saida.append({
            **v.model_dump(), "pessoa_nome": pessoas.get(v.pessoa_id, "—"), "origem_descricao": origem_descricao,
            **_info_parcelas_vale_avulso(session, v),
            "origem_lancamento": origens_lancamento.get(v.id),
        })
    return saida


@router.put("/vale-avulso/{vale_id}")
def atualizar_vale_avulso(
    vale_id: int, dados: ValeAvulsoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    vale = session.get(ValeAvulso, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    if dados.origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.origem_tipo != vale.origem_tipo or dados.origem_id != vale.origem_id:
        raise HTTPException(status_code=400, detail="Não é possível trocar a origem (Empreitada/Contrato/Diária) de um vale já lançado")
    conta = _validar_conta_vale_avulso(session, dados.forma_pagamento, dados.conta_corrente_id, fazenda_id)

    # Duas travas antes de QUALQUER escrita — este endpoint reverte e reaplica
    # o abatimento, então recusar no meio do caminho deixaria o vale sem
    # abatimento nenhum.
    # 1) parcela/etapa já paga: nem com confirmação (ver a função).
    _bloquear_reversao_de_abatimento_pago(session, vale_id)

    diferenca = round(dados.valor - vale.valor, 2)
    if diferenca != 0 and not dados.confirmar:
        raise HTTPException(status_code=409, detail={
            "mensagem": "O valor informado é diferente do valor atual deste vale.",
            "valor_calculado": vale.valor,
            "valor_informado": dados.valor,
            "diferenca": diferenca,
        })

    # 2) novo valor acima do pendente. O pendente considerado é o de DEPOIS da
    # reversão (o abatimento atual volta para as parcelas), por isso o
    # `vale_avulso_id` — ver `_saldo_pendente_do_alvo`.
    _exigir_confirmacao_vale_acima_do_pendente(
        session, dados.origem_tipo, dados.origem_id, dados.valor, dados.confirmar_excedente,
        fazenda_id=fazenda_id, vale_avulso_id=vale_id,
    )

    _reverter_vale_avulso(session, vale_id)
    session.commit()

    vale.valor = dados.valor
    vale.forma_pagamento = dados.forma_pagamento
    vale.data_pagamento = dados.data_pagamento
    vale.observacao = dados.observacao
    vale.conta_corrente_id = conta.id if conta else None
    session.add(vale)
    session.commit()

    _aplicar_vale_avulso(session, vale_id, dados.origem_tipo, dados.origem_id, dados.valor, fazenda_id=vale.fazenda_id)
    pessoa = session.get(Pessoa, vale.pessoa_id)
    # Mantém o lançamento gerado (ContaGerencial) da saída de caixa do vale
    # em sincronia com a edição — cria/atualiza/remove conforme a mudança.
    _sincronizar_conta_vale_avulso(session, vale, pessoa.nome if pessoa else "—", conta, fazenda_id)
    session.commit()

    # "conceder" (ou diferenca == 0) não precisa de mais nada: o alvo já
    # absorveu naturalmente a diferença ao reaplicar o abatimento acima.
    # "redistribuir_*" reequilibra as parcelas/etapas do alvo ainda
    # pendentes, para o efeito não ficar concentrado só na primeira delas.
    if diferenca != 0 and dados.acao in ("redistribuir_igual", "redistribuir_livre") and dados.origem_tipo in ("empreitada", "contrato"):
        _, itens_pendentes = _itens_pendentes_vale_avulso(session, dados.origem_tipo, dados.origem_id, fazenda_id)
        if dados.acao == "redistribuir_igual":
            _redistribuir_itens_pendentes_igual(session, itens_pendentes)
        else:
            if not dados.valores_itens:
                raise HTTPException(status_code=400, detail="Informe o valor de cada parcela/etapa pendente.")
            _redistribuir_itens_pendentes_livre(session, itens_pendentes, dados.valores_itens)
        session.commit()

    session.refresh(vale)
    if dados.origem_tipo == "empreitada":
        origem = session.get(Empreitada, dados.origem_id)
        resultado = _serializar_empreitada(session, origem)
    elif dados.origem_tipo == "contrato":
        origem = session.get(Contrato, dados.origem_id)
        resultado = _serializar_contrato(session, origem)
    else:
        origem = session.get(Diaria, dados.origem_id)
        pessoa = session.get(Pessoa, origem.pessoa_id)
        resultado = _resumo_diaria(session, origem, pessoa.nome if pessoa else "—")
    return {"vale": vale.model_dump(), "origem": resultado}


def _impedimento_excluir_vale_avulso(
    session: Session, vale: ValeAvulso, conta: ContaGerencial | None,
) -> str | None:
    """TODOS os motivos para recusar a exclusão de um vale avulso, em um
    lugar só — mesma função para a prévia da tela e para o DELETE, pelo mesmo
    motivo do vale de funcionário (ver `_impedimento_excluir_vale_funcionario`
    em rh_folha.py).

    A primeira trava não é escrita aqui: ela já mora dentro de
    `_bloquear_reversao_de_abatimento_pago` (parcela/etapa que este vale
    abateu e que JÁ FOI PAGA). Chamamos a mesma função e transformamos a
    recusa dela em texto, em vez de reescrever a regra — duas cópias
    divergiriam no primeiro ajuste."""
    try:
        _bloquear_reversao_de_abatimento_pago(session, vale.id)
    except HTTPException as exc:
        return exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _impedimento_excluir_vale(
        session, conta, vale.valor, LancamentoAnexo.vale_avulso_id, vale.id, ALTERNATIVA_VALE_AVULSO,
    )


@router.get("/vale-avulso/{vale_id}/exclusao")
def previa_exclusao_vale_avulso(
    vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Espelho de `previa_exclusao_vale` (rh_folha.py) para o vale avulso: o
    que a tela mostra antes de perguntar "excluir?". A alternativa aqui é
    outra de propósito — vale avulso não tem a ação "Cancelar o vale" (ela é
    do vale de funcionário, em rh_vale_acoes.py); o que existe é editar o
    valor do vale."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeAvulso, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    pessoa = session.exec(
        select(Pessoa).where(Pessoa.id == vale.pessoa_id, Pessoa.fazenda_id == fazenda_id)
    ).first()
    conta = _conta_do_numero(session, vale.numero_lancamento_gerado, fazenda_id)
    return _previa_exclusao_vale(
        conta=conta,
        impedimento=_impedimento_excluir_vale_avulso(session, vale, conta),
        titulo=f"Excluir o vale de {pessoa.nome if pessoa else 'contratado'} de R$ {vale.valor:.2f}?",
        efeito="O valor abatido da(s) parcela(s)/etapa(s) pendente(s) será revertido.",
        alternativa=ALTERNATIVA_VALE_AVULSO,
    )


@router.delete("/vale-avulso/{vale_id}")
def excluir_vale_avulso(
    vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Apaga o vale avulso que NUNCA DEVERIA TER EXISTIDO e, com ele, a saída
    de caixa que ele criou — ver o bloco EXCLUIR ≠ CANCELAR em rh_folha.py
    sobre por que a conta já paga do vale PODE ser apagada aqui (ela nasce
    paga por desenho) e quando a exclusão passa a ser recusada."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeAvulso, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    # A conta agora vem por `_conta_do_numero`, que recorta a fazenda DENTRO
    # da consulta — antes a busca era só por `numero_lancamento` e podia
    # alcançar lançamento de outra fazenda. E a recusa vem ANTES de
    # `_reverter_vale_avulso`, que já escreve nas parcelas/etapas: recusar
    # no meio deixaria o abatimento desfeito com o vale ainda de pé.
    conta = _conta_do_numero(session, vale.numero_lancamento_gerado, fazenda_id)
    impedimento = _impedimento_excluir_vale_avulso(session, vale, conta)
    if impedimento:
        raise HTTPException(status_code=400, detail=impedimento)
    _reverter_vale_avulso(session, vale_id)
    # Remove também o lançamento (ContaGerencial) gerado para a saída de
    # caixa do vale — sem isso, excluir o vale deixaria um lançamento órfão
    # no extrato, sem vale nenhum por trás dele.
    if conta is not None:
        session.delete(conta)
    # Zera o vínculo em qualquer LancamentoItem que apontava para este vale
    # (caminho inverso: usuário excluiu o vale direto no Relatório de vales,
    # não pelo checkbox do item) — sem isso ficaria FK pendurada e o item
    # sumido dos relatórios gerenciais para sempre (ver rules/vale_item.py).
    limpar_vinculo_de_itens(session, vale_avulso_id=vale_id)
    session.delete(vale)
    session.commit()
    return {"ok": True}




