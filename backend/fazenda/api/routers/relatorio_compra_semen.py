"""
Relatório financeiro de compra de sêmen (Lançamentos > Compra/Venda > espelho
de relatorio_compra_venda_animal.py, só que para CompraSemen) — consulta as
compras de sêmen já registradas, filtrável por período, número do
documento/nota, touro e vendedor. Enriquece cada linha com os dados do
lançamento financeiro gerado (ContaGerencial), quando ainda existir — mesmo
padrão do relatório de compra/venda de animais: `CompraSemen.numero_lancamento_gerado`
aponta para `ContaGerencial.numero_lancamento`, de onde vem o nº da nota
(`numero_nota`), o centro de custo e a conta gerencial usada na compra.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import CompraSemen, ContaGerencial
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios

router = APIRouter(prefix="/relatorio-compra-semen", tags=["relatorio-compra-semen"])


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
    # Mesmo cuidado do relatório de animais (já corrigido lá por vazamento):
    # este relatório nasce filtrando por fazenda_id desde o primeiro commit —
    # tanto a leitura de CompraSemen quanto o mapa de contas gerenciais usado
    # para casar `numero_lancamento_gerado`, para nunca misturar compras de
    # sêmen entre fazendas diferentes.
    fazenda_id = fazenda_id_seguro(fazenda_id)

    query_contas = select(ContaGerencial)
    if fazenda_id is not None:
        query_contas = query_contas.where(ContaGerencial.fazenda_id == fazenda_id)
    contas_por_lancamento = {c.numero_lancamento: c for c in session.exec(query_contas).all()}

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
        })
    linhas.sort(key=lambda l: (l["data_compra"], l["touro_nome"]), reverse=True)

    nomes = mapa_usuarios(session, {l["usuario_id"] for l in linhas})
    for l in linhas:
        l["usuario_nome"] = nomes.get(l["usuario_id"])
    return linhas
