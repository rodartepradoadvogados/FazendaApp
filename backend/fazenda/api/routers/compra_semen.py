"""
Router de compra de sêmen (Lançamentos > Compra/Venda > Comprar sêmen) —
registra o efeito financeiro/histórico da aquisição (lançamento em
ContaGerencial, restrito à conta gerencial de Sêmen) e soma as doses
compradas ao Estoque de Sêmen, seja de um touro já cadastrado na fazenda
(origem="estoque") ou de um touro do banco de dados NAAB (origem="naab" —
casa por NAAB com uma linha de EstoqueSemen existente, ou cria uma nova).
É essa soma em EstoqueSemen.doses que faz a compra "comunicar" com os
relatórios de estoque de sêmen e com a baixa por dose nas aplicações de
inseminação (ver fazenda.api.routers.reproducao).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import CompraSemen, ContaGerencial, EstoqueSemen, Touro, Usuario
from fazenda.api.routers.financeiro import ParcelaIn, _proximo_numero_lancamento
from fazenda.rules.auditoria import mapa_usuarios, usuario_id_seguro

router = APIRouter(prefix="/compras-semen", tags=["compras-semen"])

TIPOS_VALOR = ("por_dose", "total")
ORIGENS = ("estoque", "naab")
# Única conta gerencial onde a compra de sêmen deve ser lançada — o seletor
# do frontend só mostra esta folha (não é um ramo com sub-contas, como em
# compra_animal.py; é uma conta-folha específica).
PREFIXOS_CONTA_COMPRA_SEMEN = ["3.01.02.01"]


class CompraSemenIn(BaseModel):
    origem: str  # "estoque" | "naab"
    estoque_semen_id: int | None = None  # obrigatório se origem == "estoque"
    naab: str | None = None              # obrigatório se origem == "naab"
    touro_nome: str | None = None        # obrigatório se origem == "naab" (nome a gravar/exibir)
    central: str | None = None           # opcional, só usado ao criar uma linha nova de EstoqueSemen

    vendedor: str
    valor: float
    tipo_valor: str  # "por_dose" | "total"
    doses: int
    data_compra: date
    observacao: str | None = None
    responsavel: str | None = None

    # Conta gerencial (restrita a PREFIXOS_CONTA_COMPRA_SEMEN no frontend).
    codigo_conta_gerencial: str
    descricao: str | None = None
    centro_custo: str | None = None
    tipo_documento: str | None = None
    numero_documento: str | None = None
    data_emissao: date | None = None
    data_vencimento: date | None = None
    data_prevista_entrada: date | None = None
    data_pedido: date | None = None
    entregue: bool | None = None
    desconto: float = 0
    acrescimo: float = 0
    parcelas: list[ParcelaIn] = []
    data_pagamento: date | None = None
    valor_pago: float | None = None
    conta_bancaria: str | None = None
    numero_documento_pagamento: str | None = None


@router.get("/")
def listar_compras(session: Session = Depends(get_session)) -> list[dict]:
    compras = session.exec(select(CompraSemen).order_by(CompraSemen.data_compra.desc(), CompraSemen.id.desc())).all()
    registros = [c.model_dump() for c in compras]
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    for r in registros:
        r["usuario_nome"] = nomes.get(r["usuario_id"])
    return registros


@router.post("/")
def registrar_compra(dados: CompraSemenIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    if dados.origem not in ORIGENS:
        raise HTTPException(status_code=400, detail="Informe a origem do sêmen (estoque ou NAAB)")
    if not (dados.vendedor or "").strip():
        raise HTTPException(status_code=400, detail="Informe o vendedor")
    if dados.valor is None or dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Informe o valor da compra")
    if dados.tipo_valor not in TIPOS_VALOR:
        raise HTTPException(status_code=400, detail="Informe se o valor é por dose ou total")
    if not dados.doses or dados.doses <= 0:
        raise HTTPException(status_code=400, detail="Informe o número de doses compradas")
    if not (dados.codigo_conta_gerencial or "").strip():
        raise HTTPException(status_code=400, detail="Selecione a conta gerencial da compra")
    if not any(dados.codigo_conta_gerencial.startswith(p) for p in PREFIXOS_CONTA_COMPRA_SEMEN):
        raise HTTPException(status_code=400, detail="A conta gerencial da compra de sêmen deve ser 3.01.02.01 — Sêmen")

    # Resolve o touro/linha de EstoqueSemen a incrementar — de um touro já
    # cadastrado na fazenda, ou casando/criando por NAAB.
    if dados.origem == "estoque":
        if not dados.estoque_semen_id:
            raise HTTPException(status_code=400, detail="Selecione o touro em estoque")
        estoque = session.get(EstoqueSemen, dados.estoque_semen_id)
        if not estoque:
            raise HTTPException(status_code=404, detail="Touro em estoque não encontrado")
    else:
        if not (dados.naab or "").strip():
            raise HTTPException(status_code=400, detail="Selecione o touro do banco de dados NAAB")
        touro_naab = session.exec(select(Touro).where(Touro.naab == dados.naab)).first()
        if not touro_naab:
            raise HTTPException(status_code=404, detail="Touro NAAB não encontrado")
        estoque = session.exec(select(EstoqueSemen).where(EstoqueSemen.naab == dados.naab)).first()
        if not estoque:
            estoque = EstoqueSemen(
                touro_nome=dados.touro_nome or touro_naab.nome or touro_naab.naab,
                naab=touro_naab.naab, central=dados.central or touro_naab.central,
                tipo="convencional", doses=0,
            )
            session.add(estoque)
            session.flush()

    quantidade = dados.doses
    if dados.tipo_valor == "por_dose":
        valor_unitario = round(dados.valor, 2)
        valor_total_bruto = round(valor_unitario * quantidade, 2)
    else:
        valor_total_bruto = round(dados.valor, 2)
        valor_unitario = round(valor_total_bruto / quantidade, 2)
    valor_liquido = round(valor_total_bruto - (dados.desconto or 0) + (dados.acrescimo or 0), 2)

    numero_lancamento = _proximo_numero_lancamento(session, dados.data_compra.year)
    descricao = dados.descricao or f"Compra de {quantidade} dose(s) de sêmen — {estoque.touro_nome} ({dados.vendedor})"
    campos_comuns = dict(
        numero_lancamento=numero_lancamento,
        codigo_conta=dados.codigo_conta_gerencial,
        descricao=descricao,
        centro_custo=dados.centro_custo,
        fornecedor_cliente=dados.vendedor,
        responsavel=dados.responsavel,
        tipo_documento=dados.tipo_documento or "Compra de sêmen",
        numero_nota=dados.numero_documento,
        data_emissao=dados.data_emissao,
        data_competencia=dados.data_compra,
        data_prevista_entrada=dados.data_prevista_entrada,
        data_pedido=dados.data_pedido,
        entregue=dados.entregue,
        quantidade=quantidade,
        desconto_nota=dados.desconto or None,
        acrescimo_nota=dados.acrescimo or None,
        tipo="despesa", origem="manual",
        usuario_id=usuario_id_seguro(user),
    )

    paga_agora = bool(dados.data_pagamento) and not dados.parcelas
    if dados.parcelas:
        total_parcelas = len(dados.parcelas)
        for i, p in enumerate(dados.parcelas, start=1):
            session.add(ContaGerencial(
                **campos_comuns, data_vencimento=p.data_vencimento, valor_unitario=valor_unitario,
                valor_total=p.valor, parcela_num=i, parcela_total=total_parcelas,
            ))
    else:
        registro = ContaGerencial(
            **campos_comuns,
            data_vencimento=dados.data_vencimento or dados.data_prevista_entrada or dados.data_compra,
            valor_unitario=valor_unitario, valor_total=valor_liquido,
            parcela_num=1, parcela_total=1,
        )
        if paga_agora:
            registro.data_pagamento = dados.data_pagamento
            registro.valor_pago = dados.valor_pago
            registro.conta_bancaria = dados.conta_bancaria
            registro.numero_documento_pagamento = dados.numero_documento_pagamento
        session.add(registro)

    estoque.doses = estoque.doses + quantidade
    estoque.valor_unitario = valor_unitario
    session.add(estoque)

    session.add(CompraSemen(
        estoque_semen_id=estoque.id, touro_nome=estoque.touro_nome, naab=estoque.naab,
        origem=dados.origem, doses=quantidade, valor_unitario=valor_unitario,
        vendedor=dados.vendedor, data_compra=dados.data_compra,
        responsavel=dados.responsavel, observacao=dados.observacao,
        numero_lancamento_gerado=numero_lancamento,
        usuario_id=usuario_id_seguro(user),
    ))

    session.commit()
    return {"doses_compradas": quantidade, "estoque_semen_id": estoque.id, "numero_lancamento": numero_lancamento}
