"""
Relatório financeiro de compra de sêmen (Lançamentos > Compra/Venda > espelho
de relatorio_compra_venda_animal.py, só que para CompraSemen) — consulta as
compras de sêmen já registradas, filtrável por período, número do
documento/nota, touro e vendedor. Enriquece cada linha com os dados do
lançamento financeiro gerado (ContaGerencial), quando ainda existir — mesmo
padrão do relatório de compra/venda de animais: `CompraSemen.numero_lancamento_gerado`
aponta para `ContaGerencial.numero_lancamento`, de onde vem o nº da nota
(`numero_nota`), o centro de custo e a conta gerencial usada na compra.

Fase C dos Relatórios (Registros): cada linha diz a natureza do lançamento
(Fase A, PR 1) e `GET /resumo` acrescenta o custo do sêmen por prenhez —
inseminações do período (Reprodutivo) × preço médio da dose comprada nos 12
meses ÷ prenhezes confirmadas (ver rules/relatorio_leite.py).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import CompraSemen, ContaGerencial, Servico
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.natureza import ROTULOS as ROTULOS_NATUREZA
from fazenda.rules.parametros import regras_v2_ativas
from fazenda.rules.relatorio_leite import preco_medio_dose, semen_por_prenhez
from fazenda.rules.resultado_litro import meses_da_serie

router = APIRouter(prefix="/relatorio-compra-semen", tags=["relatorio-compra-semen"])


def linhas_compra_semen(
    session: Session, fazenda_id: int | None, *, touro: str | None = None, naab: str | None = None,
    vendedor: str | None = None, data_de: date | None = None, data_ate: date | None = None,
    numero_documento: str | None = None, centro_custo: str | None = None,
) -> list[dict]:
    # Mesmo cuidado do relatório de animais (já corrigido lá por vazamento):
    # este relatório nasce filtrando por fazenda_id desde o primeiro commit —
    # tanto a leitura de CompraSemen quanto o mapa de contas gerenciais usado
    # para casar `numero_lancamento_gerado`, para nunca misturar compras de
    # sêmen entre fazendas diferentes.
    query_contas = select(ContaGerencial)
    if fazenda_id is not None:
        query_contas = query_contas.where(ContaGerencial.fazenda_id == fazenda_id)
    contas_por_lancamento = {c.numero_lancamento: c for c in session.exec(query_contas).all()}
    from fazenda.api.routers.financeiro import _contexto_natureza

    ctx_natureza = _contexto_natureza(session, fazenda_id)

    query = select(CompraSemen)
    if fazenda_id is not None:
        query = query.where(CompraSemen.fazenda_id == fazenda_id)
    if touro:
        alvo = touro.strip().lower()
        query = query.where(CompraSemen.touro_nome.ilike(f"%{alvo}%"))
    if naab:
        query = query.where(CompraSemen.naab == naab)
    if vendedor:
        alvo_v = vendedor.strip().lower()
        query = query.where(CompraSemen.vendedor.ilike(f"%{alvo_v}%"))
    if data_de:
        query = query.where(CompraSemen.data_compra >= data_de)
    if data_ate:
        query = query.where(CompraSemen.data_compra <= data_ate)

    compras = session.exec(query).all()

    linhas = []
    for c in compras:
        conta = contas_por_lancamento.get(c.numero_lancamento_gerado)
        numero_doc = conta.numero_nota if conta else None
        if numero_documento and (numero_doc or "").strip().lower() != numero_documento.strip().lower():
            continue
        if centro_custo and (conta is None or (conta.centro_custo or "") != centro_custo):
            continue
        natureza = ctx_natureza.natureza(conta=conta, codigo_conta=conta.codigo_conta) if conta else None
        linhas.append({
            "touro_nome": c.touro_nome,
            "naab": c.naab,
            "origem": c.origem,
            "tipo": c.tipo,
            "doses": c.doses,
            "valor_unitario": c.valor_unitario,
            "valor_total": round(c.doses * c.valor_unitario, 2),
            "vendedor": c.vendedor,
            "data_compra": c.data_compra,
            "responsavel": c.responsavel,
            "observacao": c.observacao,
            "numero_lancamento": c.numero_lancamento_gerado,
            "numero_documento": numero_doc,
            "centro_custo": conta.centro_custo if conta else None,
            "codigo_conta": conta.codigo_conta if conta else None,
            "usuario_id": c.usuario_id,
            "natureza": natureza,
            "natureza_rotulo": ROTULOS_NATUREZA.get(natureza, "Sem lançamento financeiro") if natureza else "Sem lançamento financeiro",
        })
    linhas.sort(key=lambda l: (l["data_compra"], l["touro_nome"]), reverse=True)

    nomes = mapa_usuarios(session, {l["usuario_id"] for l in linhas})
    for l in linhas:
        l["usuario_nome"] = nomes.get(l["usuario_id"])
    return linhas


@router.get("/")
def relatorio(
    touro: str | None = Query(None, description="Nome do touro (contém, sem diferenciar maiúsculas)"),
    naab: str | None = None,
    vendedor: str | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
    numero_documento: str | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    return linhas_compra_semen(
        session, fazenda_id, touro=touro, naab=naab, vendedor=vendedor, data_de=data_de, data_ate=data_ate,
        numero_documento=numero_documento,
    )


@router.get("/resumo")
def relatorio_resumo(
    data_de: date = Query(...),
    data_ate: date = Query(...),
    touro: str | None = None,
    vendedor: str | None = None,
    numero_documento: str | None = None,
    centro_custo: str | None = None,
    serie_meses: int = Query(12, ge=0, le=24),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Relatórios › Registros › Compra de sêmen (Fase C): as compras do
    período (com natureza), os totais e o custo do sêmen por prenhez do
    período e dos `serie_meses` meses que terminam em `data_ate`."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linhas = linhas_compra_semen(
        session, fazenda_id, touro=touro, vendedor=vendedor, data_de=data_de, data_ate=data_ate,
        numero_documento=numero_documento, centro_custo=centro_custo or None,
    )
    # Preço médio da dose: TODAS as compras da fazenda (o botijão mistura
    # compras de qualquer touro/vendedor), não só as filtradas na tela.
    query_compras = select(CompraSemen)
    query_servicos = select(Servico)
    if fazenda_id is not None:
        query_compras = query_compras.where(CompraSemen.fazenda_id == fazenda_id)
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
    compras = [{"data": c.data_compra, "doses": c.doses, "valor_unitario": c.valor_unitario} for c in session.exec(query_compras).all()]
    servicos = [
        {"data_servico": s.data_servico, "tipo_servico": s.tipo_servico, "tipo_semen": s.tipo_semen, "diagnostico": s.diagnostico}
        for s in session.exec(query_servicos).all()
    ]

    def calc(ini: date, fim: date) -> dict:
        preco = preco_medio_dose(compras, fim)
        return {"preco_dose": preco, **semen_por_prenhez(servicos, preco["preco"], ini, fim)}

    doses = sum(l["doses"] for l in linhas)
    gasto = round(sum(l["valor_total"] for l in linhas), 2)
    return {
        "periodo": {"inicio": data_de.isoformat(), "fim": data_ate.isoformat()},
        "centro_custo": centro_custo or None,
        "regras_v2": regras_v2_ativas(session, fazenda_id),
        "linhas": linhas,
        "totais": {
            "gasto": gasto, "doses": doses, "compras": len(linhas),
            "preco_medio_dose": round(gasto / doses, 2) if doses else None,
            "sem_lancamento": sum(1 for l in linhas if l["natureza"] is None),
        },
        "prenhez": calc(data_de, data_ate),
        "serie": [{"competencia": f"{ini:%Y-%m}", **calc(ini, fim)} for ini, fim in meses_da_serie(data_ate, serie_meses)],
    }
