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
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    ContaCorrente, ContaGerencial, DecimoTerceiro, FeriasFuncionario, FolhaPagamento, GuiaFolhaEncargo,
    LancamentoAnexo, Pessoa, RescisaoFuncionario, Usuario, ValeAvulso, ValeFuncionario, ValeParcela,
)
from fazenda.api.routers.financeiro import TAMANHO_MAXIMO_ANEXO, _proximo_numero_lancamento, rotulo_conta_corrente
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.vale_item import limpar_vinculo_de_itens, origens_lancamento_por_vale
from fazenda.rules.folha_rh import calcular_decimo_terceiro, calcular_ferias, calcular_rescisao
from fazenda.rules.parametros import (
    dias_ferias_padrao,
    percentual_estimado_fgts_mensal,
    percentual_terco_constitucional_ferias,
)
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage
from fazenda.config import settings

FORMAS_PAGAMENTO_VALE = ["dinheiro", "pix", "transferencia", "desconto_integral_folha"]

router = APIRouter()


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
    Soma o valor de TODAS as parcelas de vale da pessoa nesta competência —
    esse é o "desconto de vale" da folha (coluna separada dos "descontos de
    folha" manuais). Uma parcela pertence a exatamente uma competência e a
    pessoa tem no máximo uma folha por competência, então somar todas é
    correto e idempotente (não acumula em recomputações sucessivas).
    """
    parcelas = session.exec(
        select(ValeParcela).where(
            ValeParcela.pessoa_id == pessoa_id,
            ValeParcela.competencia == competencia,
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


def _rescisao_fechada_antes_de(session: Session, pessoa_id: int, competencia: str) -> bool:
    """
    True quando a pessoa já tem uma rescisão FECHADA (a simulação sozinha não
    conta — ver fluxo simulacao → fechada) com `data_desligamento` anterior ao
    início de `competencia`. Usada para nunca gerar/aceitar folha de um mês em
    que a pessoa já não trabalhava mais (bug: rescisão lançada em agosto não
    impedia a folha de setembro em diante).
    """
    ano, mes = (int(x) for x in competencia.split("-"))
    inicio_competencia = date(ano, mes, 1)
    rescisao = session.exec(
        select(RescisaoFuncionario).where(
            RescisaoFuncionario.pessoa_id == pessoa_id,
            RescisaoFuncionario.status == "fechada",
            RescisaoFuncionario.data_desligamento < inicio_competencia,
        )
    ).first()
    return rescisao is not None


def _remover_folha_pos_rescisao(session: Session, fazenda_id: int | None) -> None:
    """
    Self-heal: remove (com a conta a pagar vinculada, se ainda não paga)
    qualquer folha PENDENTE de uma competência posterior à rescisão fechada da
    pessoa — cobre o caso de a folha já ter sido gerada (recorrência ou
    lançamento manual) ANTES de a rescisão ser lançada/fechada no sistema.
    Nunca mexe em folha já paga."""
    query = select(FolhaPagamento).where(FolhaPagamento.status != "pago")
    if fazenda_id is not None:
        query = query.where(FolhaPagamento.fazenda_id == fazenda_id)
    for registro in session.exec(query).all():
        if not _rescisao_fechada_antes_de(session, registro.pessoa_id, registro.competencia):
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
    Nunca exclui um lançamento já pago."""
    query = select(FolhaPagamento)
    if fazenda_id is not None:
        query = query.where(FolhaPagamento.fazenda_id == fazenda_id)
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


def _gerar_folha_recorrente(session: Session, fazenda_id: int | None = None) -> None:
    """
    Para cada lançamento de folha marcado como recorrente (o "modelo"), gera
    automaticamente os lançamentos das competências seguintes até o mês atual
    — tanto o registro de acompanhamento (FolhaPagamento) quanto a conta a
    pagar correspondente (ContaGerencial) — sem exigir relançamento manual
    todo mês. Mesmo padrão "lazy pull" da baixa automática de Alimentação.
    Para de gerar a partir da competência em que a pessoa já tem rescisão
    fechada (ver _rescisao_fechada_antes_de) — todas as competências seguintes
    também estariam bloqueadas, então a geração deste modelo pode parar aí.
    """
    competencia_atual = date.today().strftime("%Y-%m")
    query = select(FolhaPagamento).where(FolhaPagamento.recorrente == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(FolhaPagamento.fazenda_id == fazenda_id)
    modelos = session.exec(query).all()
    for modelo in modelos:
        pessoa = session.get(Pessoa, modelo.pessoa_id)
        if not pessoa:
            continue
        competencia = _competencia_seguinte(modelo.competencia)
        while competencia <= competencia_atual:
            if _rescisao_fechada_antes_de(session, modelo.pessoa_id, competencia):
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
                valor_liquido = round(modelo.valor_bruto - descontos - valor_vale, 2)
                numero_lancamento = _proximo_numero_lancamento(session, ano)
                nova = FolhaPagamento(
                    pessoa_id=modelo.pessoa_id, competencia=competencia, valor_bruto=modelo.valor_bruto,
                    descontos=descontos, valor_vale=valor_vale, valor_liquido=valor_liquido, status="pendente",
                    observacao=modelo.observacao, origem_recorrencia_id=modelo.id,
                    numero_lancamento_gerado=numero_lancamento,
                    centro_custo=modelo.centro_custo,
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
                    fazenda_id=fazenda_id,
                ))
                session.commit()
            competencia = _competencia_seguinte(competencia)


def _detalhe_folha(session: Session, registro: FolhaPagamento) -> list[dict]:
    """
    Discriminação completa do lançamento — bruto, INSS, IR, cada parcela de
    vale aplicada nesta competência e o líquido. É essa lista que vira a
    expansão da linha da folha no frontend (em vez da antiga lista de vales
    solta abaixo do lançamento de vale).
    """
    parcelas_vale = sorted(
        session.exec(
            select(ValeParcela).where(
                ValeParcela.pessoa_id == registro.pessoa_id, ValeParcela.competencia == registro.competencia
            )
        ).all(),
        key=lambda p: (p.vale_id, p.id or 0),
    )
    detalhe = [{"label": "Salário bruto", "valor": registro.valor_bruto}]
    if registro.percentual_inss:
        detalhe.append({"label": f"INSS ({registro.percentual_inss:g}%)", "valor": -registro.valor_inss})
    if registro.percentual_ir:
        detalhe.append({"label": f"IR ({registro.percentual_ir:g}%)", "valor": -registro.valor_ir})
    # Uma linha por parcela de vale, com o valor REAL da parcela (descontos de
    # vale). Numera a parcela na sequência do PRÓPRIO vale (k/n, ex.: 1/2, 2/2),
    # ordenando todas as parcelas do vale por competência — não só as deste mês.
    for p in parcelas_vale:
        irmas = sorted(
            session.exec(select(ValeParcela).where(ValeParcela.vale_id == p.vale_id)).all(),
            key=lambda x: (x.competencia, x.id or 0),
        )
        n = len(irmas)
        k = next((i + 1 for i, x in enumerate(irmas) if x.id == p.id), 1)
        detalhe.append({"label": f"Vale (parcela {k}/{n})", "valor": -p.valor})
    # "Descontos de folha" manuais — vêm de registro.descontos, SEM misturar vale.
    if abs(registro.descontos) > 0.001:
        detalhe.append({"label": "Outros descontos", "valor": -registro.descontos})
    detalhe.append({"label": "Valor líquido", "valor": registro.valor_liquido})
    return detalhe


@router.get("/folha-pagamento")
def listar_folha_pagamento(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    _remover_folha_duplicada(session, fazenda_id)
    _remover_folha_pos_rescisao(session, fazenda_id)
    _gerar_folha_recorrente(session, fazenda_id)
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
            registro.valor_liquido = round(
                registro.valor_bruto - registro.descontos - registro.valor_inss - registro.valor_ir - vv, 2
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

    return [
        {
            **r.model_dump(),
            "pessoa_nome": pessoas.get(r.pessoa_id, "—"),
            "data_vencimento": venc_por_numero.get(r.numero_lancamento_gerado),
            "detalhe": _detalhe_folha(session, r),
            "usuario_nome": nomes_usuarios.get(r.usuario_id),
        }
        for r in registros
    ]


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
    if _rescisao_fechada_antes_de(session, dados.pessoa_id, dados.competencia):
        raise HTTPException(
            status_code=400,
            detail="Esta pessoa tem rescisão fechada anterior a esta competência — não é possível lançar folha.",
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
    valor_liquido = round(dados.valor_bruto - descontos - valor_inss - valor_ir - valor_vale, 2)
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
    return registro.model_dump()


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
    valor_liquido = round(dados.valor_bruto - descontos - valor_inss - valor_ir - valor_vale, 2)
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

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


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
    if registro.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        if conta:
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


def _conta_da_guia(session: Session, guia: GuiaFolhaEncargo) -> ContaGerencial | None:
    if not guia.numero_lancamento:
        return None
    return session.exec(
        select(ContaGerencial).where(ContaGerencial.numero_lancamento == guia.numero_lancamento)
    ).first()


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
    conta = _conta_da_guia(session, guia)
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
    conta = _conta_da_guia(session, guia)
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

    calculo = calcular_ferias(
        pessoa.salario_base, dados.dias_gozados, dados.abono_pecuniario_dias, percentual_terco_constitucional_ferias(),
    )
    numero_lancamento = _proximo_numero_lancamento(session, dados.data_fim_gozo.year)

    registro = FeriasFuncionario(
        pessoa_id=dados.pessoa_id,
        periodo_aquisitivo_inicio=dados.periodo_aquisitivo_inicio, periodo_aquisitivo_fim=dados.periodo_aquisitivo_fim,
        dias_direito=dados.dias_direito, dias_gozados=dados.dias_gozados,
        data_inicio_gozo=dados.data_inicio_gozo, data_fim_gozo=dados.data_fim_gozo,
        abono_pecuniario_dias=dados.abono_pecuniario_dias,
        valor_ferias=calculo["valor_ferias"], valor_terco_constitucional=calculo["valor_terco_constitucional"],
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
        data_vencimento=dados.data_pagamento or dados.data_fim_gozo,
        data_competencia=dados.data_fim_gozo,
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
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_ferias(dados)
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)

    calculo = calcular_ferias(
        pessoa.salario_base, dados.dias_gozados, dados.abono_pecuniario_dias, percentual_terco_constitucional_ferias(),
    )
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
            conta.data_vencimento = dados.data_pagamento or dados.data_fim_gozo
            conta.data_competencia = dados.data_fim_gozo
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
    if registro.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        if conta:
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


PARCELAS_DECIMO_TERCEIRO = ("unica", "primeira", "segunda")


def _validar_decimo_terceiro(dados: DecimoTerceiroIn) -> None:
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.parcela not in PARCELAS_DECIMO_TERCEIRO:
        raise HTTPException(status_code=400, detail="Parcela inválida")
    if dados.meses_trabalhados < 1 or dados.meses_trabalhados > 12:
        raise HTTPException(status_code=400, detail="Meses trabalhados deve estar entre 1 e 12")


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

    valor_bruto = calcular_decimo_terceiro(pessoa.salario_base, dados.meses_trabalhados)
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    valor_liquido = round(valor_bruto - valor_inss - valor_ir, 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")

    numero_lancamento = _proximo_numero_lancamento(session, dados.ano)
    vencimento_padrao = date(dados.ano, 12, 20) if dados.parcela in ("unica", "segunda") else date(dados.ano, 11, 30)

    registro = DecimoTerceiro(
        pessoa_id=dados.pessoa_id, ano=dados.ano, parcela=dados.parcela, meses_trabalhados=dados.meses_trabalhados,
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
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_decimo_terceiro(dados)
    conta_corrente = _resolver_conta_corrente(session, dados.conta_corrente_id, fazenda_id)

    valor_bruto = calcular_decimo_terceiro(pessoa.salario_base, dados.meses_trabalhados)
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    valor_liquido = round(valor_bruto - valor_inss - valor_ir, 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")

    registro.pessoa_id = dados.pessoa_id
    registro.ano = dados.ano
    registro.parcela = dados.parcela
    registro.meses_trabalhados = dados.meses_trabalhados
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
    if registro.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        if conta:
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
    `POST /cadastro/rescisoes`)."""
    pessoa, calculo = _calcular_rescisao_pessoa(dados, session, fazenda_id_seguro(fazenda_id))
    return {**calculo, "pessoa_id": pessoa.id, "pessoa_nome": pessoa.nome}


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
    return {**registro.model_dump(), "pessoa_nome": pessoa.nome, "detalhe": _detalhe_rescisao(registro)}


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
    return {**registro.model_dump(), "pessoa_nome": pessoa.nome, "detalhe": _detalhe_rescisao(registro)}


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
    session.commit()
    session.refresh(registro)
    return {**registro.model_dump(), "pessoa_nome": pessoa.nome, "detalhe": _detalhe_rescisao(registro)}


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
    alteração (criação/edição/exclusão) de vale."""
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
        folha.valor_liquido = round(
            folha.valor_bruto - folha.descontos - folha.valor_inss - folha.valor_ir - folha.valor_vale, 2
        )
        _marcar_vale_aplicado(session, pessoa_id, competencia)
        session.add(folha)
        if folha.numero_lancamento_gerado:
            conta = session.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado)
            ).first()
            if conta and conta.valor_pago is None:
                conta.valor_total = folha.valor_liquido
                session.add(conta)


def _vale_competencia_paga(session: Session, pessoa_id: int, competencias: list[str]) -> str | None:
    """Retorna a primeira competência, entre as informadas, cuja folha já
    esteja paga — usado para bloquear edição/exclusão de um vale já
    absorvido por um pagamento que já saiu."""
    for competencia in competencias:
        folha = session.exec(
            select(FolhaPagamento).where(
                FolhaPagamento.pessoa_id == pessoa_id,
                FolhaPagamento.competencia == competencia,
                FolhaPagamento.status == "pago",
            )
        ).first()
        if folha:
            return competencia
    return None


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
    descricao = f"Vale — {pessoa.nome} ({vale.competencia_inicio})"
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
            tipo_documento="Vale de funcionário",
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
    valor_parcela = round(dados.valor_total / dados.parcelas, 2)
    # a última parcela absorve o arredondamento, para a soma bater com valor_total
    valores_parcela = [valor_parcela] * (dados.parcelas - 1)
    valores_parcela.append(round(dados.valor_total - valor_parcela * (dados.parcelas - 1), 2))

    if not pessoa.salario_base:
        raise HTTPException(
            status_code=400,
            detail="Cadastre o salário base da pessoa (Configurações > Cadastro > Pessoas) antes de lançar um vale.",
        )

    limite = round(pessoa.salario_base * 0.4, 2)
    competencias_excedidas = []
    for competencia, valor in zip(competencias, valores_parcela):
        ja_lancado = session.exec(
            select(ValeParcela).where(ValeParcela.pessoa_id == dados.pessoa_id, ValeParcela.competencia == competencia)
        ).all()
        total_competencia = round(sum(p.valor for p in ja_lancado) + valor, 2)
        if total_competencia > limite:
            competencias_excedidas.append({"competencia": competencia, "total": total_competencia, "limite": limite})

    if competencias_excedidas and not dados.confirmar:
        raise HTTPException(status_code=409, detail={
            "mensagem": (
                f"O desconto de vale ultrapassa 40% do salário (limite de R$ {limite:.2f}) em "
                f"{len(competencias_excedidas)} competência(s). Confirme para lançar mesmo assim."
            ),
            "competencias_excedidas": competencias_excedidas,
        })

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
    competencias_atuais = [p.competencia for p in parcelas_atuais]
    competencia_paga = _vale_competencia_paga(session, pessoa_id_antigo, competencias_atuais)
    if competencia_paga:
        raise HTTPException(
            status_code=400,
            detail=f"Vale já aplicado na folha paga de {competencia_paga} não pode ser editado.",
        )

    competencias_novas = _competencias_do_vale(dados.competencia_inicio, dados.parcelas)
    valor_parcela = round(dados.valor_total / dados.parcelas, 2)
    valores_parcela = [valor_parcela] * (dados.parcelas - 1)
    valores_parcela.append(round(dados.valor_total - valor_parcela * (dados.parcelas - 1), 2))

    limite = round(pessoa.salario_base * 0.4, 2)
    competencias_excedidas = []
    for competencia, valor in zip(competencias_novas, valores_parcela):
        # exclui as parcelas do próprio vale (serão substituídas) do total já lançado nessa competência
        ja_lancado = session.exec(
            select(ValeParcela).where(
                ValeParcela.pessoa_id == dados.pessoa_id,
                ValeParcela.competencia == competencia,
                ValeParcela.vale_id != vale_id,
            )
        ).all()
        total_competencia = round(sum(p.valor for p in ja_lancado) + valor, 2)
        if total_competencia > limite:
            competencias_excedidas.append({"competencia": competencia, "total": total_competencia, "limite": limite})

    if competencias_excedidas and not dados.confirmar:
        raise HTTPException(status_code=409, detail={
            "mensagem": (
                f"O desconto de vale ultrapassa 40% do salário (limite de R$ {limite:.2f}) em "
                f"{len(competencias_excedidas)} competência(s). Confirme para salvar mesmo assim."
            ),
            "competencias_excedidas": competencias_excedidas,
        })

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

    competencia_paga = _vale_competencia_paga(session, vale.pessoa_id, [parcela.competencia])
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
        and not _vale_competencia_paga(session, vale.pessoa_id, [p.competencia])
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
                p.valor = novo
                session.add(p)
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
                p.valor = round(dados.valores_parcelas[p.id], 2)
                session.add(p)
        else:
            raise HTTPException(status_code=400, detail="Informe a ação: redistribuir_igual, redistribuir_livre ou conceder.")

    parcela.valor = dados.valor
    session.add(parcela)
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

    competencia_paga = _vale_competencia_paga(session, vale.pessoa_id, [parcela.competencia])
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
        and not _vale_competencia_paga(session, vale.pessoa_id, [p.competencia])
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


@router.delete("/vales/{vale_id}")
def excluir_vale(
    vale_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    vale = session.get(ValeFuncionario, vale_id)
    if not vale or (vale.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    pessoa_id = vale.pessoa_id
    parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
    competencias = [p.competencia for p in parcelas]
    competencia_paga = _vale_competencia_paga(session, pessoa_id, competencias)
    if competencia_paga:
        raise HTTPException(
            status_code=400,
            detail=f"Vale já aplicado na folha paga de {competencia_paga} não pode ser excluído.",
        )
    # Remove também o lançamento (ContaGerencial) gerado para a saída de
    # caixa do vale — sem isso, excluir o vale deixaria um lançamento órfão
    # no extrato, sem vale nenhum por trás dele.
    if vale.numero_lancamento_gerado:
        conta_gerada = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado)
        ).first()
        if conta_gerada:
            session.delete(conta_gerada)
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
    de `numero_lancamento` (que aqui pode nem existir)."""
    pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}/vales/{tipo}/{vale_id}"
    existentes = session.exec(select(LancamentoAnexo).where(coluna == vale_id)).all()
    seq = 1 + len(existentes)
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
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = _anexo_comprovante_vale(session, anexo_id, fazenda_id)
    if anexo.caminho_storage:
        try:
            excluir_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    session.delete(anexo)
    session.commit()
    return {"excluido": True}



