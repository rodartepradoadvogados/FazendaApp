"""
Relatório financeiro de compra/venda de animais (Lançamentos > Compra/Venda) —
consulta unificada das duas pontas (CompraAnimal + VendaAnimal), filtrável por
número do animal, período (de/até), número do documento ou GTA. Enriquece cada
linha com os dados do lançamento financeiro gerado (ContaGerencial), quando
ainda existir.

Fase C dos Relatórios (Registros): cada linha também diz a NATUREZA do
lançamento (Fase A, PR 1 — matriz/reprodutor comprado é INVESTIMENTO, fora da
DRE e dos custos com as regras novas; recria/venda é OPERACIONAL) e a
categoria do animal; `GET /resumo` devolve as mesmas linhas com os totais por
cabeça, por categoria e por natureza (a tela só apresenta).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Animal, CompraAnimal, ContaGerencial, VendaAnimal
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.natureza import OPERACIONAL, ROTULOS as ROTULOS_NATUREZA
from fazenda.rules.parametros import regras_v2_ativas

router = APIRouter(prefix="/relatorio-compra-venda-animais", tags=["relatorio-compra-venda-animais"])

SEM_CATEGORIA = "Sem categoria"


def _categoria(texto: str | None) -> str | None:
    """"vaca,novilha" → "Vaca" (a primeira categoria da nota, com maiúscula)."""
    primeira = (texto or "").split(",")[0].strip()
    return primeira[:1].upper() + primeira[1:] if primeira else None


def linhas_compra_venda(
    session: Session, fazenda_id: int | None, *, numero: str | None = None, data_de: date | None = None,
    data_ate: date | None = None, numero_documento: str | None = None, gta: str | None = None,
    centro_custo: str | None = None,
) -> list[dict]:
    """As linhas do relatório (uma por animal), já com natureza e categoria.
    `centro_custo`: só as linhas cujo lançamento é daquele centro (linha sem
    lançamento financeiro não tem centro — só aparece sem o filtro)."""
    # As três leituras aqui rodavam sem NENHUM filtro de fazenda: o relatório
    # de uma fazenda listava compras/vendas de todas as outras, e o mapa de
    # contas casava `numero_lancamento` entre fazendas diferentes.
    query_contas = select(ContaGerencial)
    if fazenda_id is not None:
        query_contas = query_contas.where(ContaGerencial.fazenda_id == fazenda_id)
    contas_por_lancamento = {
        c.numero_lancamento: c for c in session.exec(query_contas).all()
    }
    query_animais = select(Animal)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    categoria_atual = {
        a.numero: (a.categoria_completa or a.categoria_abrev) for a in session.exec(query_animais).all()
    }
    # Import tardio: o resolvedor de natureza (contexto do plano de contas) mora em financeiro.py.
    from fazenda.api.routers.financeiro import _contexto_natureza

    ctx_natureza = _contexto_natureza(session, fazenda_id)

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
            if centro_custo and (conta is None or (conta.centro_custo or "") != centro_custo):
                continue
            natureza = ctx_natureza.natureza(conta=conta, codigo_conta=conta.codigo_conta) if conta else None
            if tipo == "venda":
                categoria = _categoria(d.get("categorias")) or _categoria(categoria_atual.get(d["numero_animal"]))
                origem_categoria = "nota" if _categoria(d.get("categorias")) else ("animal" if categoria else None)
            else:
                categoria = _categoria(categoria_atual.get(d["numero_animal"]))
                origem_categoria = "animal" if categoria else None
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
                # Fase C: natureza (Fase A, PR 1) e categoria (da nota de venda,
                # ou a categoria ATUAL do animal no cadastro).
                "natureza": natureza,
                "natureza_rotulo": ROTULOS_NATUREZA.get(natureza, "Sem lançamento financeiro") if natureza else "Sem lançamento financeiro",
                "categoria": categoria or SEM_CATEGORIA,
                "origem_categoria": origem_categoria,
            })
        return linhas

    compras_q = select(CompraAnimal)
    vendas_q = select(VendaAnimal)
    if fazenda_id is not None:
        compras_q = compras_q.where(CompraAnimal.fazenda_id == fazenda_id)
        vendas_q = vendas_q.where(VendaAnimal.fazenda_id == fazenda_id)
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


def resumo_compra_venda(linhas: list[dict]) -> dict:
    """Totais, R$ por cabeça e quebra por categoria e por natureza. Cada linha
    é UM animal (CompraAnimal/VendaAnimal guardam o valor por animal)."""
    def _por(itens: list[dict]) -> tuple[int, float]:
        return len(itens), round(sum(i["valor"] or 0.0 for i in itens), 2)

    vendas = [l for l in linhas if l["tipo"] == "venda"]
    compras = [l for l in linhas if l["tipo"] == "compra"]
    cab_v, v = _por(vendas)
    cab_c, c = _por(compras)
    por_categoria = []
    for cat in sorted({l["categoria"] for l in linhas}, key=lambda x: (x == SEM_CATEGORIA, x)):
        cv, vv = _por([l for l in vendas if l["categoria"] == cat])
        cc, vc = _por([l for l in compras if l["categoria"] == cat])
        por_categoria.append({
            "categoria": cat, "cab_vendidas": cv, "vendas": vv, "venda_por_cabeca": round(vv / cv, 2) if cv else None,
            "cab_compradas": cc, "compras": vc, "compra_por_cabeca": round(vc / cc, 2) if cc else None,
        })
    por_natureza = []
    for nat in sorted({l["natureza"] or "" for l in linhas}, key=lambda x: (x != OPERACIONAL, x)):
        do_grupo = [l for l in linhas if (l["natureza"] or "") == nat]
        cv, vv = _por([l for l in do_grupo if l["tipo"] == "venda"])
        cc, vc = _por([l for l in do_grupo if l["tipo"] == "compra"])
        por_natureza.append({
            "natureza": nat or None, "rotulo": do_grupo[0]["natureza_rotulo"],
            "cab_vendidas": cv, "vendas": vv, "cab_compradas": cc, "compras": vc,
        })
    return {
        "totais": {
            "vendas": v, "compras": c, "saldo": round(v - c, 2), "cab_vendidas": cab_v, "cab_compradas": cab_c,
            "venda_por_cabeca": round(v / cab_v, 2) if cab_v else None,
            "compra_por_cabeca": round(c / cab_c, 2) if cab_c else None,
            # Compra de matriz/reprodutor (INVESTIMENTO) não é custo do período
            # com as regras novas: fica à parte para a tela não somar errado.
            "compras_operacionais": round(sum(l["valor"] or 0.0 for l in compras if l["natureza"] in (None, OPERACIONAL)), 2),
            "compras_investimento": round(sum(l["valor"] or 0.0 for l in compras if l["natureza"] not in (None, OPERACIONAL)), 2),
            "sem_lancamento": sum(1 for l in linhas if not l["numero_lancamento"] or l["natureza"] is None),
        },
        "por_categoria": por_categoria,
        "por_natureza": por_natureza,
    }


@router.get("/")
def relatorio(
    numero: str | None = Query(None, description="Número do animal"),
    data_de: date | None = None,
    data_ate: date | None = None,
    numero_documento: str | None = None,
    gta: str | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    return linhas_compra_venda(
        session, fazenda_id, numero=numero, data_de=data_de, data_ate=data_ate, numero_documento=numero_documento, gta=gta,
    )


@router.get("/resumo")
def relatorio_resumo(
    numero: str | None = Query(None, description="Número do animal"),
    data_de: date | None = None,
    data_ate: date | None = None,
    numero_documento: str | None = None,
    gta: str | None = None,
    centro_custo: str | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Relatórios › Registros › Compra e venda de animais (Fase C): as linhas
    do relatório + totais por cabeça, por categoria e por natureza."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linhas = linhas_compra_venda(
        session, fazenda_id, numero=numero, data_de=data_de, data_ate=data_ate, numero_documento=numero_documento,
        gta=gta, centro_custo=centro_custo or None,
    )
    return {
        "periodo": {"inicio": data_de.isoformat() if data_de else None, "fim": data_ate.isoformat() if data_ate else None},
        "centro_custo": centro_custo or None,
        "regras_v2": regras_v2_ativas(session, fazenda_id),
        "linhas": linhas,
        **resumo_compra_venda(linhas),
    }
