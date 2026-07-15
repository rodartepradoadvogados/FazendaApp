"""
Relatório financeiro de compra/venda de animais (Lançamentos > Compra/Venda) —
consulta unificada das duas pontas (CompraAnimal + VendaAnimal), filtrável por
número do animal, período (de/até), número do documento ou GTA. Enriquece cada
linha com os dados do lançamento financeiro gerado (ContaGerencial), quando
ainda existir.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import CompraAnimal, ContaGerencial, VendaAnimal
from fazenda.rules.auditoria import mapa_usuarios

router = APIRouter(prefix="/relatorio-compra-venda-animais", tags=["relatorio-compra-venda-animais"])


@router.get("/")
def relatorio(
    numero: str | None = Query(None, description="Número do animal"),
    data_de: date | None = None,
    data_ate: date | None = None,
    numero_documento: str | None = None,
    gta: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    contas_por_lancamento = {
        c.numero_lancamento: c for c in session.exec(select(ContaGerencial)).all()
    }

    def _enriquecer(registros, tipo: str, campo_data: str, campo_contraparte: str) -> list[dict]:
        linhas = []
        for r in registros:
            d = r.model_dump()
            data_ref = d[campo_data]
            if data_de and data_ref < data_de:
                continue
            if data_ate and data_ref > data_ate:
                continue
            conta = contas_por_lancamento.get(d.get("numero_lancamento_gerado"))
            numero_doc = conta.numero_nota if conta else None
            if numero_documento and (numero_doc or "").strip().lower() != numero_documento.strip().lower():
                continue
            linhas.append({
                "tipo": tipo,
                "numero_animal": d["numero_animal"],
                "contraparte": d[campo_contraparte],
                "data": data_ref,
                "valor": d["valor"],
                "tipo_valor": d["tipo_valor"],
                "gta": d.get("gta"),
                "icms_incide": d.get("icms_incide"),
                "icms_tipo": d.get("icms_tipo"),
                "icms_valor": d.get("icms_valor"),
                "numero_lancamento": d.get("numero_lancamento_gerado"),
                "numero_documento": numero_doc,
                "centro_custo": conta.centro_custo if conta else None,
                "codigo_conta": conta.codigo_conta if conta else None,
                "categorias": d.get("categorias"),
                "motivo_venda": d.get("motivo_venda"),
                "usuario_id": d.get("usuario_id"),
            })
        return linhas

    compras_q = select(CompraAnimal)
    vendas_q = select(VendaAnimal)
    if numero:
        compras_q = compras_q.where(CompraAnimal.numero_animal == numero)
        vendas_q = vendas_q.where(VendaAnimal.numero_animal == numero)
    if gta:
        compras_q = compras_q.where(CompraAnimal.gta == gta)
        vendas_q = vendas_q.where(VendaAnimal.gta == gta)

    compras = session.exec(compras_q).all()
    vendas = session.exec(vendas_q).all()

    linhas = (
        _enriquecer(compras, "compra", "data_compra", "vendedor")
        + _enriquecer(vendas, "venda", "data_venda", "comprador")
    )
    linhas.sort(key=lambda l: (l["data"], l["numero_animal"]), reverse=True)

    nomes = mapa_usuarios(session, {l["usuario_id"] for l in linhas})
    for l in linhas:
        l["usuario_nome"] = nomes.get(l["usuario_id"])
    return linhas
