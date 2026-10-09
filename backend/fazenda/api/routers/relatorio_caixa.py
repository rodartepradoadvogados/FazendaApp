"""
Relatórios do grupo CAIXA (Fase C1 do redesenho dos Relatórios) — só LEITURA,
arquivo próprio no prefixo `/financeiro` (como relatorio_resultado_litro.py):

- `GET /financeiro/caixa-real/folego`: saldo de hoje ÷ saída média diária dos
  últimos 90 dias (o resto do Caixa real continua em GET /financeiro/caixa-real
  e /caixa-real/fundo-reserva-sugerido, sem mudança);
- `GET /financeiro/fluxo-caixa-mensal`: entradas e saídas que passaram no banco,
  mês a mês (e dia a dia), com o que ainda está previsto (em aberto pelo
  vencimento, agendado);
- `GET /financeiro/livro-caixa-rural`: o livro caixa da atividade rural no
  formato do contador (data, histórico, documento, receita, despesa, saldo).

Valores com as MESMAS funções do Caixa Real e da DRE: com a flag
`financeiro_regras_v2` desligada, o realizado é o de antes (data de pagamento,
`valor_pago` ou o valor da parcela — o mesmo do Fluxo e do Livro caixa antigos,
que somavam isso no navegador); ligada, a data de caixa e o valor que de fato
passou no banco (rules/saldo_conta.py) e, no livro, a separação fiscal pela
natureza dos registros da DRE de caixa.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import ContaCorrente, ContaGerencial, LancamentoItem, PlanoContaGerencial, Usuario
from fazenda.rules import saldo_conta
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.centro_custo import valor_gerencial_por_centro_custo
from fazenda.rules.datas import hoje_local
from fazenda.rules.natureza import ROTULOS as ROTULOS_NATUREZA
from fazenda.rules.parametros import regras_v2_ativas
from fazenda.rules.relatorio_caixa import (
    SEM_CONTA, classificar_registro_livro, fluxo_de_caixa, folego, montar_livro, r2, repartir_por_itens,
)
from fazenda.rules.vale_item import ajuste_vale_por_conta, valor_caixa_parcela

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

SEM_CENTRO = "Sem centro de custo"
JANELA_FOLEGO = 90


def _contas_da_fazenda(session: Session, fazenda_id: int | None) -> list[ContaGerencial]:
    query = select(ContaGerencial)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    return list(session.exec(query).all())


def _nomes_plano(session: Session, fazenda_id: int | None) -> dict[str, str]:
    query = select(PlanoContaGerencial.codigo, PlanoContaGerencial.nome)
    if fazenda_id is not None:
        query = query.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    return {codigo: nome for codigo, nome in session.exec(query).all()}


def _valor_realizado_antigo(c: ContaGerencial) -> float:
    """O valor do Fluxo e do Livro caixa ANTIGOS (frontend `valorRealizado`):
    `valor_pago`, ou o valor da parcela quando o pago não foi informado."""
    return float(c.valor_pago if c.valor_pago is not None else (c.valor_total or 0.0))


def _periodo_valido(data_inicio: date, data_fim: date) -> None:
    if data_fim < data_inicio:
        raise HTTPException(status_code=422, detail="A data final é anterior à inicial.")
    if (data_fim - data_inicio).days > 3 * 366:
        raise HTTPException(status_code=422, detail="Escolha um período de até 3 anos.")


# ── Fôlego do Caixa real ─────────────────────────────────────────────────
@router.get("/caixa-real/folego")
def caixa_real_folego(
    hoje: Optional[date] = Query(None, description="'Hoje' do front (hojeLocal); só com as regras v2"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: Usuario = Depends(exigir_admin),
) -> dict:
    """Fôlego de caixa em dias = saldo de hoje ÷ saída média diária dos últimos
    90 dias (PLANO §5, indicador 9). O saldo de hoje é o MESMO do Caixa real
    (`saldo_inicial` de GET /financeiro/caixa-real); as saídas são o que de
    fato saiu do banco na janela — com as regras v2 pela data de caixa e o
    valor pago (sem descontar vale, como o fundo de reserva sugerido); sem
    elas, pela data de pagamento e o valor gerencial (vale descontado), a
    mesma base do fundo de reserva sugerido antigo."""
    from fazenda.api.routers.financeiro import calcular_saldos_contas_correntes, saldos_contas_v2

    fazenda_id = fazenda_id_seguro(fazenda_id)
    v2 = regras_v2_ativas(session, fazenda_id)
    hoje = (hoje or hoje_local()) if v2 else hoje_local()
    query_contas = select(ContaCorrente)
    if fazenda_id is not None:
        query_contas = query_contas.where(ContaCorrente.fazenda_id == fazenda_id)
    contas_cc = list(session.exec(query_contas).all())
    if v2:
        saldo = sum(s.saldo for s in saldos_contas_v2(session, contas_cc, fazenda_id, hoje).values())
    else:
        saldo = sum(calcular_saldos_contas_correntes(session, contas_cc, fazenda_id).values())

    ini = hoje - timedelta(days=JANELA_FOLEGO - 1)
    query = select(ContaGerencial).where(ContaGerencial.tipo == "despesa", ContaGerencial.data_pagamento.is_not(None))
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    saidas = 0.0
    if v2:
        for c in session.exec(query).all():
            dc = saldo_conta.data_caixa(c)
            if saldo_conta.conta_entra_no_caixa(c) and dc is not None and ini <= dc <= hoje:
                saidas += abs(valor_caixa_parcela(c))
    else:
        candidatas = [c for c in session.exec(query).all() if ini <= c.data_pagamento <= hoje]
        valores = valor_gerencial_por_centro_custo(session, candidatas, None, ajuste_vale_por_conta(session, candidatas, fazenda_id))
        saidas = sum(abs(valores.get(c.id, 0.0)) for c in candidatas)
    return {**folego(saldo, saidas, JANELA_FOLEGO), "hoje": hoje.isoformat(), "inicio_janela": ini.isoformat(), "regras_v2": v2}


# ── Fluxo de caixa ───────────────────────────────────────────────────────
def _itens_por_numero(session: Session, fazenda_id: int | None, numeros: set[str]) -> dict[str, list[LancamentoItem]]:
    out: dict[str, list[LancamentoItem]] = {}
    if not numeros:
        return out
    query = select(LancamentoItem).where(LancamentoItem.numero_lancamento.in_(sorted(numeros)))
    if fazenda_id is not None:
        query = query.where(LancamentoItem.fazenda_id == fazenda_id)
    for it in session.exec(query).all():
        out.setdefault(it.numero_lancamento, []).append(it)
    return out


@router.get("/fluxo-caixa-mensal")
def fluxo_caixa_mensal(
    data_inicio: date = Query(..., description="Data inicial"),
    data_fim: date = Query(..., description="Data final"),
    centro_custo: Optional[str] = Query(None, description="Centro de custo da nota (vazio = todos)"),
    hoje: Optional[date] = Query(None, description="'Hoje' do front (hojeLocal): separa realizado de previsto"),
    por_dia: bool = Query(False, description="Devolve também os dias do período"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Fluxo de caixa: o dinheiro que passou no banco no período, por mês, por
    conta gerencial e (com `por_dia`) por dia — sempre pelo dia do pagamento.

    Realizado: notas pagas no período (regras antigas: data de pagamento e
    `valor_pago` ou o valor da parcela — os números do Fluxo de caixa antigo;
    regras v2: data de caixa, valor pago, sem a nota de classificação do
    cartão). Previsto: notas em aberto pelo vencimento (vencida e não paga
    entra hoje, marcada), com o valor do Caixa real; com as regras v2, também o
    pagamento já baixado com data de caixa depois de hoje (agendado).
    Transferências entre contas próprias não entram (não mudam o total)."""
    _periodo_valido(data_inicio, data_fim)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    v2 = regras_v2_ativas(session, fazenda_id)
    hoje = hoje or hoje_local()
    centro = (centro_custo or "").strip() or None
    nomes = _nomes_plano(session, fazenda_id)

    contas = [c for c in _contas_da_fazenda(session, fazenda_id) if centro is None or (c.centro_custo or SEM_CENTRO) == centro]
    em_aberto = [c for c in contas if c.data_pagamento is None]
    valores_aberto: dict[int, float] = {}
    if not v2 and em_aberto:
        # O valor do Caixa real antigo (vale descontado) — ver financeiro.caixa_real.
        valores_aberto = valor_gerencial_por_centro_custo(session, em_aberto, None, ajuste_vale_por_conta(session, em_aberto, fazenda_id))

    movimentos: list[dict] = []
    pagos: list[tuple[ContaGerencial, date, float]] = []
    sem_vencimento = 0
    for c in contas:
        if c.data_pagamento is None:
            valor = valor_caixa_parcela(c) if v2 else valores_aberto.get(c.id, 0.0)
            if not valor:
                continue
            if c.data_vencimento is None:
                sem_vencimento += 1
                continue
            d = max(c.data_vencimento, hoje)
            movimentos.append({"data": d, "tipo": c.tipo, "valor": valor, "previsto": True, "vencido": c.data_vencimento < hoje})
            continue
        if v2:
            if not saldo_conta.conta_entra_no_caixa(c):
                continue
            d, valor = saldo_conta.data_caixa(c), saldo_conta.valor_pago_efetivo(c)
            if d is not None and d > hoje:
                movimentos.append({"data": d, "tipo": c.tipo, "valor": valor, "previsto": True, "agendado": True})
                continue
        else:
            d, valor = c.data_pagamento, _valor_realizado_antigo(c)
        if d is None or not valor or not (data_inicio <= d <= data_fim):
            continue
        pagos.append((c, d, valor))

    # Realizado por conta gerencial: a da nota; nota de vários itens, repartida pelo peso dos itens.
    itens = _itens_por_numero(session, fazenda_id, {c.numero_lancamento for c, _d, _v in pagos if not c.codigo_conta and c.numero_lancamento})
    for c, d, valor in pagos:
        partes: list[tuple[str | None, str | None, float]] = []
        if c.codigo_conta:
            partes = [(c.codigo_conta, nomes.get(c.codigo_conta), valor)]
        else:
            partes = repartir_por_itens(valor, [
                (it.codigo_conta_gerencial, nomes.get(it.codigo_conta_gerencial or "") or it.nome_conta_gerencial, it.valor_total or 0.0)
                for it in itens.get(c.numero_lancamento or "", [])
            ]) or [(None, None, valor)]
        for codigo, nome, fatia in partes:
            movimentos.append({"data": d, "tipo": c.tipo, "valor": fatia, "previsto": False,
                               "codigo": codigo, "conta": f"{codigo} {nome}".strip() if codigo and nome else (codigo or nome or SEM_CONTA)})

    resposta = fluxo_de_caixa(movimentos, data_inicio, data_fim, hoje, por_dia=por_dia)
    agendado = r2(sum(m["valor"] for m in movimentos if m.get("agendado") and data_inicio <= m["data"] <= data_fim))
    resposta.update({
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "centro_custo": centro, "hoje": hoje.isoformat(), "regras_v2": v2,
        "compromissos_sem_vencimento": sem_vencimento, "agendado_no_periodo": agendado,
        "avisos": ([f"{sem_vencimento} conta(s) em aberto sem vencimento ficaram fora do previsto."] if sem_vencimento else []),
    })
    return resposta


# ── Livro caixa da atividade rural ───────────────────────────────────────
def _texto_nota(c: ContaGerencial) -> dict:
    return {
        "id": c.id, "numero_lancamento": c.numero_lancamento, "documento": c.numero_nota or None,
        "historico": c.descricao or "", "fornecedor": c.fornecedor_cliente or "",
    }


@router.get("/livro-caixa-rural")
def livro_caixa_rural(
    data_inicio: date = Query(..., description="Data inicial"),
    data_fim: date = Query(..., description="Data final"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Livro caixa da atividade rural: cronológico pelo dia do pagamento, todos
    os centros, com o saldo acumulado do período e os totais por mês.

    Regras v2: os registros da DRE de CAIXA (os mesmos números, por item) com a
    regra fiscal do produtor pessoa física — receita pela BRUTA (Funrural/
    Senar não é despesa paga), despesa de custeio (inclui juros; desconto
    obtido abate) e investimento pago como despesa no mês do pagamento, sem
    depreciação; financiamento, aporte/retirada, transferência, adiantamento,
    obrigação já reconhecida e conta sem classificação ficam fora (agrupados
    em `fora_do_livro`). Devolve a ponte com a DRE de caixa, que fecha no
    centavo.

    Regras antigas: o Livro caixa de antes — todo pagamento e recebimento do
    período, pelo valor pago — sem a separação fiscal (a natureza só existe
    nas regras novas: `separacao_fiscal` = False)."""
    _periodo_valido(data_inicio, data_fim)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    v2 = regras_v2_ativas(session, fazenda_id)
    nomes = _nomes_plano(session, fazenda_id)
    base = {"periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()}, "regras_v2": v2,
            "separacao_fiscal": v2}

    if not v2:
        lancs = []
        for c in _contas_da_fazenda(session, fazenda_id):
            d = c.data_pagamento
            if d is None or not (data_inicio <= d <= data_fim):
                continue
            valor = _valor_realizado_antigo(c)
            lancs.append({**_texto_nota(c), "data": d, "conta": nomes.get(c.codigo_conta or "") if c.codigo_conta else None,
                          "receita": valor if c.tipo == "receita" else 0.0,
                          "custeio": 0.0 if c.tipo == "receita" else valor, "categoria": None})
        livro = montar_livro(lancs, data_inicio, data_fim)
        return {**base, **livro, "presumido_20": None, "fora_do_livro": None, "ponte_dre": None, "avisos": []}

    from fazenda.api.routers.financeiro import _mapa_linha_por_codigo, calcular_dre
    from fazenda.rules.dre import NAO_ENTRA_NA_DRE, resolver_linha_dre
    from fazenda.rules.natureza import NAO_INFORMADA

    dre = calcular_dre(session, fazenda_id, data_inicio, data_fim, None, "caixa", regras_v2=True)
    mapa_linha = _mapa_linha_por_codigo(session, fazenda_id)
    por_conta: dict[int, dict] = {}
    fora: dict[str, dict] = {}
    deducoes = venda_bem = 0.0
    for reg in dre.get("_registros") or []:
        linha = reg.get("linha_forcada") or resolver_linha_dre(reg.get("codigo_conta"), mapa_linha)
        if linha == NAO_ENTRA_NA_DRE and (reg.get("natureza") or "OPERACIONAL") == "OPERACIONAL":
            reg = {**reg, "natureza": NAO_INFORMADA}
        destino, valor = classificar_registro_livro(reg, classificado=linha is not None)
        if destino == "deducao":
            deducoes = r2(deducoes - valor)
            continue
        cid = reg.get("conta_id")
        if destino in ("receita", "custeio", "investimento"):
            b = por_conta.setdefault(cid, {"receita": 0.0, "custeio": 0.0, "investimento": 0.0, "codigos": {}})
            # receita soma (+); custeio/investimento chegam negativos (saída) e viram magnitude.
            b[destino] = r2(b[destino] + (valor if destino == "receita" else -valor))
            codigo = reg.get("codigo_conta")
            if codigo:
                b["codigos"][codigo] = b["codigos"].get(codigo, 0.0) + abs(valor)
            if destino == "receita" and (reg.get("natureza") == "INVESTIMENTO"):
                venda_bem = r2(venda_bem + valor)
            continue
        g = fora.setdefault(destino, {"natureza": destino, "entradas": 0.0, "saidas": 0.0, "ids": set()})
        g["entradas" if valor > 0 else "saidas"] = r2(g["entradas" if valor > 0 else "saidas"] + abs(valor))
        if cid is not None:
            g["ids"].add(cid)

    notas = {}
    if por_conta:
        query = select(ContaGerencial).where(ContaGerencial.id.in_([i for i in por_conta if i is not None]))
        if fazenda_id is not None:
            query = query.where(ContaGerencial.fazenda_id == fazenda_id)
        notas = {c.id: c for c in session.exec(query).all()}
    lancs = []
    for cid, b in por_conta.items():
        c = notas.get(cid)
        if c is None:
            continue
        d = saldo_conta.data_caixa(c) or c.data_pagamento
        if d is not None and not (data_inicio <= d <= data_fim) and c.data_pagamento and data_inicio <= c.data_pagamento <= data_fim:
            d = c.data_pagamento  # juros/desconto da baixa de um cartão avulso: o fato é a baixa
        codigo = max(b["codigos"], key=b["codigos"].get) if b["codigos"] else c.codigo_conta
        partes = [k for k in ("custeio", "investimento") if abs(b[k]) >= 0.005]
        categoria = "receita" if c.tipo == "receita" else ("misto" if len(partes) > 1 else (partes[0] if partes else "custeio"))
        if c.tipo == "receita":
            rec, cus, inv = r2(b["receita"] - b["custeio"] - b["investimento"]), 0.0, 0.0
        else:
            rec, cus, inv = 0.0, r2(b["custeio"] - b["receita"]), b["investimento"]
        lancs.append({**_texto_nota(c), "data": d, "conta": f"{codigo} {nomes.get(codigo, '')}".strip() if codigo else None,
                      "receita": rec, "custeio": cus, "investimento": inv, "categoria": categoria})
    livro = montar_livro(lancs, data_inicio, data_fim)
    t = livro["totais"]

    resumo = dre.get("resumo") or {}
    resultado_dre = r2(resumo.get("resultado_liquido", 0.0))
    depreciacao = r2((dre.get("depreciacao_periodo") or {}).get("total", 0.0))
    baixas = r2(((dre.get("resultado_baixas_periodo") or {}).get("total")) or 0.0)
    investimentos_liquidos = r2(t["investimentos"] - venda_bem)
    reconstruido = r2(resultado_dre + depreciacao - baixas + deducoes - investimentos_liquidos)
    grupos_fora = sorted(
        ({"natureza": g["natureza"], "rotulo": "Sem classificação na DRE" if g["natureza"] == "sem_conta" else ROTULOS_NATUREZA.get(g["natureza"], g["natureza"]),
          "entradas": g["entradas"], "saidas": g["saidas"], "quantidade": len(g["ids"])} for g in fora.values()),
        key=lambda g: -(g["entradas"] + g["saidas"]),
    )
    return {
        **base, **livro,
        "presumido_20": r2(t["receitas"] * 0.2),
        "fora_do_livro": {"entradas": r2(sum(g["entradas"] for g in grupos_fora)), "saidas": r2(sum(g["saidas"] for g in grupos_fora)),
                          "grupos": grupos_fora},
        "ponte_dre": {
            "resultado_dre": resultado_dre, "depreciacao": depreciacao, "resultado_baixas": baixas,
            "deducoes": deducoes, "investimentos_liquidos": investimentos_liquidos, "venda_de_bens": venda_bem,
            "resultado_livro": t["resultado"], "reconstruido": reconstruido, "fecha": abs(reconstruido - t["resultado"]) < 0.02,
        },
        "avisos": [],
    }
