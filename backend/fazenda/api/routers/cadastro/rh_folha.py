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
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    ContaGerencial, DecimoTerceiro, FeriasFuncionario, FolhaPagamento, Pessoa, Usuario, ValeFuncionario, ValeParcela,
)
from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.folha_rh import calcular_decimo_terceiro, calcular_ferias, calcular_rescisao
from fazenda.rules.parametros import (
    dias_ferias_padrao,
    percentual_estimado_fgts_mensal,
    percentual_terco_constitucional_ferias,
)

FORMAS_PAGAMENTO_VALE = ["dinheiro", "pix", "transferencia", "desconto_integral_folha"]

router = APIRouter()

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
def proporcional_admissao(pessoa_id: int, competencia: str, session: Session = Depends(get_session)) -> dict | None:
    """
    Usado pelo lançamento de folha do funcionário para sugerir o valor
    proporcional quando a competência informada é o mês de admissão da
    pessoa — retorna None fora desse caso (folha integral normal).
    """
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa:
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


def _gerar_folha_recorrente(session: Session, fazenda_id: int | None = None) -> None:
    """
    Para cada lançamento de folha marcado como recorrente (o "modelo"), gera
    automaticamente os lançamentos das competências seguintes até o mês atual
    — tanto o registro de acompanhamento (FolhaPagamento) quanto a conta a
    pagar correspondente (ContaGerencial) — sem exigir relançamento manual
    todo mês. Mesmo padrão "lazy pull" da baixa automática de Alimentação.
    """
    competencia_atual = date.today().strftime("%Y-%m")
    modelos = session.exec(select(FolhaPagamento).where(FolhaPagamento.recorrente == True)).all()  # noqa: E712
    for modelo in modelos:
        pessoa = session.get(Pessoa, modelo.pessoa_id)
        if not pessoa:
            continue
        competencia = _competencia_seguinte(modelo.competencia)
        while competencia <= competencia_atual:
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
    _gerar_folha_recorrente(session, fazenda_id)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    registros = session.exec(select(FolhaPagamento).order_by(FolhaPagamento.competencia.desc())).all()

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
        registros = session.exec(select(FolhaPagamento).order_by(FolhaPagamento.competencia.desc())).all()

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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.recorrente and not (dados.dia_vencimento and 1 <= dados.dia_vencimento <= 28):
        raise HTTPException(status_code=400, detail="Informe o dia de vencimento (1 a 28) para lançamentos recorrentes")
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
        usuario_id=user.id,
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
        fazenda_id=fazenda_id,
    ))
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.put("/folha-pagamento/{registro_id}")
def atualizar_folha_pagamento(registro_id: int, dados: FolhaPagamentoIn, session: Session = Depends(get_session)) -> dict:
    registro = session.get(FolhaPagamento, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de folha não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Lançamento de folha já pago não pode ser editado.")
    if not session.get(Pessoa, dados.pessoa_id):
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
            if dados.status == "pago":
                conta.data_pagamento = dados.data_pagamento
                conta.valor_pago = valor_liquido
            session.add(conta)

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.delete("/folha-pagamento/{registro_id}")
def excluir_folha_pagamento(registro_id: int, session: Session = Depends(get_session)) -> dict:
    registro = session.get(FolhaPagamento, registro_id)
    if not registro:
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
# Guias consolidadas de FGTS/DCTF — projeção de contas a pagar somando o
# `valor_fgts`/`valor_dctf` de TODOS os lançamentos de folha de uma
# competência (todos os funcionários), fora de escopo qualquer fórmula legal
# real ou integração com sistemas do governo: é só uma soma decidida pelo
# usuário/contador, para antecipar o fluxo de caixa. As contas a pagar
# geradas são registros comuns de ContaGerencial (mesmo padrão de Folha/
# Férias/13º) — por isso já são editáveis (valor e vencimento) pelo fluxo
# normal de "Contas a Pagar" / "Lançamentos", sem precisar de endpoint
# especial de edição.
# ---------------------------------------------------------------------------
TIPO_DOCUMENTO_GUIA_FGTS = "Guia FGTS"
TIPO_DOCUMENTO_GUIA_DCTF = "Guia DCTF"


class GerarGuiasFgtsDctfIn(BaseModel):
    competencia: str  # "AAAA-MM" — mesma competência dos lançamentos de folha somados
    # Ajuste opcional do valor projetado (preview) antes de confirmar a
    # geração — se omitido, usa a soma calculada dos lançamentos da folha.
    valor_fgts: float | None = None
    valor_dctf: float | None = None
    # Vencimento das guias — se omitido, usa o dia 20 do mês SEGUINTE à
    # competência (editável antes ou depois de gerar, nas duas contas).
    data_vencimento: date | None = None
    centro_custo: str = "Pecuária Leiteira"


def _lancamentos_folha_competencia(session: Session, competencia: str) -> list[FolhaPagamento]:
    """TODOS os lançamentos de folha (de qualquer funcionário) de uma
    competência — usado para somar valor_fgts/valor_dctf; registros sem o
    campo preenchido simplesmente não contribuem (ver
    `_calcular_encargo_projetado`)."""
    return session.exec(select(FolhaPagamento).where(FolhaPagamento.competencia == competencia)).all()


def _guias_ja_geradas(session: Session, competencia: str) -> bool:
    """
    Proteção simples contra geração duplicada: as guias já existem para essa
    competência se houver alguma ContaGerencial com tipo_documento "Guia FGTS"
    ou "Guia DCTF" cuja data_competencia seja o 1º dia do mês da competência
    informada — o mesmo campo/convenção já usado para vincular a folha
    individual à sua competência (`data_competencia=date(ano, mes, 1)`).
    """
    ano, mes = (int(x) for x in competencia.split("-"))
    primeiro_dia = date(ano, mes, 1)
    existente = session.exec(
        select(ContaGerencial).where(
            ContaGerencial.tipo_documento.in_([TIPO_DOCUMENTO_GUIA_FGTS, TIPO_DOCUMENTO_GUIA_DCTF]),
            ContaGerencial.data_competencia == primeiro_dia,
        )
    ).first()
    return existente is not None


@router.get("/folha-pagamento/guias-preview")
def preview_guias_fgts_dctf(competencia: str, session: Session = Depends(get_session)) -> dict:
    """
    Pré-visualização da soma projetada de FGTS/DCTF de uma competência (todos
    os funcionários) — usada pelo frontend para MOSTRAR os valores antes do
    usuário confirmar a geração das guias (que ele ainda pode ajustar).
    """
    registros = _lancamentos_folha_competencia(session, competencia)
    valor_fgts = round(sum(r.valor_fgts or 0.0 for r in registros), 2)
    valor_dctf = round(sum(r.valor_dctf or 0.0 for r in registros), 2)
    ano_venc, mes_venc = (int(x) for x in _competencia_seguinte(competencia).split("-"))
    return {
        "competencia": competencia,
        "quantidade_lancamentos": len(registros),
        "valor_fgts": valor_fgts,
        "valor_dctf": valor_dctf,
        "data_vencimento_sugerida": date(ano_venc, mes_venc, 20),
        "ja_gerado": _guias_ja_geradas(session, competencia),
    }


@router.post("/folha-pagamento/gerar-guias")
def gerar_guias_fgts_dctf(
    dados: GerarGuiasFgtsDctfIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Cria as DUAS contas a pagar consolidadas (Guia FGTS e Guia DCTF) de uma
    competência, somando o valor_fgts/valor_dctf de todos os lançamentos de
    folha daquela competência (a soma pode ser sobrescrita em `dados` — é só
    o valor inicial sugerido). Vencimento padrão: dia 20 do mês seguinte à
    competência, também sobrescrevível. Bloqueia geração duplicada — se as
    guias já existirem para a competência, aponta para editá-las em Contas a
    Pagar em vez de gerar de novo.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if _guias_ja_geradas(session, dados.competencia):
        raise HTTPException(
            status_code=400,
            detail=(
                f"As guias de FGTS/DCTF da competência {dados.competencia} já foram geradas. "
                "Edite os lançamentos existentes em Contas a Pagar em vez de gerar novamente."
            ),
        )
    registros = _lancamentos_folha_competencia(session, dados.competencia)
    if not registros:
        raise HTTPException(status_code=404, detail=f"Nenhum lançamento de folha encontrado para a competência {dados.competencia}")

    valor_fgts = round(dados.valor_fgts, 2) if dados.valor_fgts is not None else round(sum(r.valor_fgts or 0.0 for r in registros), 2)
    valor_dctf = round(dados.valor_dctf, 2) if dados.valor_dctf is not None else round(sum(r.valor_dctf or 0.0 for r in registros), 2)
    if valor_fgts <= 0 and valor_dctf <= 0:
        raise HTTPException(
            status_code=400,
            detail="Nenhum valor de FGTS/DCTF foi lançado nos funcionários dessa competência — informe percentual ou valor no lançamento de folha, ou preencha manualmente aqui.",
        )

    ano, mes = (int(x) for x in dados.competencia.split("-"))
    ano_venc, mes_venc = (int(x) for x in _competencia_seguinte(dados.competencia).split("-"))
    data_vencimento = dados.data_vencimento or date(ano_venc, mes_venc, 20)

    contas_criadas: list[ContaGerencial] = []
    if valor_fgts > 0:
        numero_fgts = _proximo_numero_lancamento(session, ano)
        conta_fgts = ContaGerencial(
            numero_lancamento=numero_fgts,
            descricao=f"Guia FGTS — {dados.competencia}",
            data_vencimento=data_vencimento,
            data_competencia=date(ano, mes, 1),
            tipo_documento=TIPO_DOCUMENTO_GUIA_FGTS,
            centro_custo=dados.centro_custo,
            valor_total=valor_fgts,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            usuario_id=user.id,
            fazenda_id=fazenda_id,
        )
        session.add(conta_fgts)
        contas_criadas.append(conta_fgts)
    if valor_dctf > 0:
        numero_dctf = _proximo_numero_lancamento(session, ano)
        conta_dctf = ContaGerencial(
            numero_lancamento=numero_dctf,
            descricao=f"Guia DCTF — {dados.competencia}",
            data_vencimento=data_vencimento,
            data_competencia=date(ano, mes, 1),
            tipo_documento=TIPO_DOCUMENTO_GUIA_DCTF,
            centro_custo=dados.centro_custo,
            valor_total=valor_dctf,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            usuario_id=user.id,
            fazenda_id=fazenda_id,
        )
        session.add(conta_dctf)
        contas_criadas.append(conta_dctf)

    session.commit()
    for conta in contas_criadas:
        session.refresh(conta)
    return {
        "competencia": dados.competencia,
        "data_vencimento": data_vencimento,
        "contas": [c.model_dump() for c in contas_criadas],
    }




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
def listar_ferias(session: Session = Depends(get_session)) -> list[dict]:
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    registros = session.exec(select(FeriasFuncionario).order_by(FeriasFuncionario.data_inicio_gozo.desc())).all()
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_ferias(dados)

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
        numero_lancamento_gerado=numero_lancamento, centro_custo=dados.centro_custo, usuario_id=user.id,
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
        fazenda_id=fazenda_id,
    ))
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.put("/ferias/{registro_id}")
def atualizar_ferias(registro_id: int, dados: FeriasIn, session: Session = Depends(get_session)) -> dict:
    registro = session.get(FeriasFuncionario, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de férias não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Férias já pagas não podem ser editadas.")
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_ferias(dados)

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
            if dados.status == "pago":
                conta.data_pagamento = dados.data_pagamento
                conta.valor_pago = calculo["valor_total"]
            session.add(conta)

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.delete("/ferias/{registro_id}")
def excluir_ferias(registro_id: int, session: Session = Depends(get_session)) -> dict:
    registro = session.get(FeriasFuncionario, registro_id)
    if not registro:
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


PARCELAS_DECIMO_TERCEIRO = ("unica", "primeira", "segunda")


def _validar_decimo_terceiro(dados: DecimoTerceiroIn) -> None:
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.parcela not in PARCELAS_DECIMO_TERCEIRO:
        raise HTTPException(status_code=400, detail="Parcela inválida")
    if dados.meses_trabalhados < 1 or dados.meses_trabalhados > 12:
        raise HTTPException(status_code=400, detail="Meses trabalhados deve estar entre 1 e 12")


@router.get("/decimo-terceiro")
def listar_decimo_terceiro(session: Session = Depends(get_session)) -> list[dict]:
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    registros = session.exec(select(DecimoTerceiro).order_by(DecimoTerceiro.ano.desc())).all()
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_decimo_terceiro(dados)

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
        numero_lancamento_gerado=numero_lancamento, centro_custo=dados.centro_custo, usuario_id=user.id,
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
        fazenda_id=fazenda_id,
    ))
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.put("/decimo-terceiro/{registro_id}")
def atualizar_decimo_terceiro(registro_id: int, dados: DecimoTerceiroIn, session: Session = Depends(get_session)) -> dict:
    registro = session.get(DecimoTerceiro, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de 13º salário não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="13º salário já pago não pode ser editado.")
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa.salario_base:
        raise HTTPException(status_code=400, detail="Pessoa não tem salário base cadastrado")
    _validar_decimo_terceiro(dados)

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
            if dados.status == "pago":
                conta.data_pagamento = dados.data_pagamento
                conta.valor_pago = valor_liquido
            session.add(conta)

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.delete("/decimo-terceiro/{registro_id}")
def excluir_decimo_terceiro(registro_id: int, session: Session = Depends(get_session)) -> dict:
    registro = session.get(DecimoTerceiro, registro_id)
    if not registro:
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
# oficial (fora de escopo, mesma linha de férias/13º). Diferente de férias/
# 13º, não existe uma tabela de acompanhamento dedicada — o registro fica só
# no lançamento em Contas a Pagar (`tipo_documento == "Rescisão"`), reusado
# pela listagem abaixo.
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


def _calcular_rescisao_pessoa(dados: RescisaoIn, session: Session) -> tuple[Pessoa, dict]:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
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
def simular_rescisao(dados: RescisaoIn, session: Session = Depends(get_session)) -> dict:
    """Só calcula e devolve o detalhamento das verbas — não gera lançamento
    financeiro nenhum (usado pela tela para o usuário conferir antes de
    lançar em `POST /cadastro/rescisao`)."""
    pessoa, calculo = _calcular_rescisao_pessoa(dados, session)
    return {**calculo, "pessoa_id": pessoa.id, "pessoa_nome": pessoa.nome}


@router.get("/rescisao")
def listar_rescisoes(session: Session = Depends(get_session)) -> list[dict]:
    contas = session.exec(
        select(ContaGerencial)
        .where(ContaGerencial.tipo_documento == "Rescisão")
        .order_by(ContaGerencial.data_competencia.desc())
    ).all()
    return [c.model_dump() for c in contas]


@router.post("/rescisao")
def criar_rescisao(
    dados: RescisaoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa, calculo = _calcular_rescisao_pessoa(dados, session)

    numero_lancamento = _proximo_numero_lancamento(session, dados.data_desligamento.year)
    conta = ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Rescisão — {LABELS_TIPO_RESCISAO[dados.tipo_rescisao]} — {pessoa.nome} ({dados.data_desligamento.isoformat()})",
        data_vencimento=dados.data_pagamento or dados.data_desligamento,
        data_competencia=dados.data_desligamento,
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Rescisão",
        centro_custo=dados.centro_custo,
        valor_total=calculo["valor_total"],
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        data_pagamento=dados.data_pagamento if dados.status == "pago" else None,
        valor_pago=calculo["valor_total"] if dados.status == "pago" else None,
        fazenda_id=fazenda_id,
    )
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return {
        **calculo,
        "pessoa_id": pessoa.id,
        "pessoa_nome": pessoa.nome,
        "observacao": dados.observacao,
        "status": dados.status,
        "numero_lancamento_gerado": numero_lancamento,
        **conta.model_dump(),
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


@router.get("/vales")
def listar_vales(session: Session = Depends(get_session)) -> list[dict]:
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    vales = session.exec(select(ValeFuncionario).order_by(ValeFuncionario.data_pagamento.desc())).all()
    nomes_usuarios = mapa_usuarios(session, {v.usuario_id for v in vales})
    saida = []
    for v in vales:
        parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == v.id)).all()
        saida.append({
            **v.model_dump(), "pessoa_nome": pessoas.get(v.pessoa_id, "—"),
            "usuario_nome": nomes_usuarios.get(v.usuario_id),
            "parcelas_detalhe": sorted(({**p.model_dump()} for p in parcelas), key=lambda p: p["competencia"]),
        })
    return saida


@router.post("/vales")
def criar_vale(dados: ValeIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.valor_total <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.parcelas < 1:
        raise HTTPException(status_code=400, detail="Informe ao menos 1 parcela")

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
        observacao=dados.observacao, numero_documento_pagamento=dados.numero_documento_pagamento, usuario_id=user.id,
    )
    session.add(vale)
    session.commit()
    session.refresh(vale)
    for competencia, valor in zip(competencias, valores_parcela):
        session.add(ValeParcela(vale_id=vale.id, pessoa_id=dados.pessoa_id, competencia=competencia, valor=valor))
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
def atualizar_vale(vale_id: int, dados: ValeIn, session: Session = Depends(get_session)) -> dict:
    vale = session.get(ValeFuncionario, vale_id)
    if not vale:
        raise HTTPException(status_code=404, detail="Vale não encontrado")
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
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
    session.add(vale)
    for p in parcelas_atuais:
        session.delete(p)
    session.commit()

    for competencia, valor in zip(competencias_novas, valores_parcela):
        session.add(ValeParcela(vale_id=vale.id, pessoa_id=dados.pessoa_id, competencia=competencia, valor=valor))
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


@router.delete("/vales/{vale_id}")
def excluir_vale(vale_id: int, session: Session = Depends(get_session)) -> dict:
    vale = session.get(ValeFuncionario, vale_id)
    if not vale:
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
    for p in parcelas:
        session.delete(p)
    session.delete(vale)
    session.commit()
    _reconciliar_vale_competencias(session, pessoa_id, competencias)
    session.commit()
    return {"ok": True}



