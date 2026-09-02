"""
Router de compra de animal (Lançamentos > Compra/Venda > Comprar animal) —
registra o efeito financeiro/histórico completo da aquisição: lançamento
(despesa) rico em ContaGerencial (conta gerencial restrita às contas de
compra de animal, centro de custo, documento, datas, parcelamento, pagamento),
GTA e ICMS quando houver, e comissão de corretagem opcional. Não cria nem
exige ficha de Animal: o cadastro do animal em si segue seu próprio fluxo
(CSV/ficha), este endpoint só documenta a compra e gera o(s) lançamento(s)
financeiro(s) correspondente(s).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import Animal, CompraAnimal, ContaGerencial, Usuario
from fazenda.api.routers.financeiro import ParcelaIn, _proximo_numero_lancamento
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios, usuario_id_seguro
from fazenda.rules.comissao import FORMAS_COMISSAO, criar_comissao

router = APIRouter(prefix="/compras-animais", tags=["compras-animais"])

TIPOS_VALOR = ("por_animal", "total")
# Ramos do plano de contas onde a compra de animal (reposição/crescimento de
# rebanho) deve ser lançada — o seletor do frontend só mostra folhas destes ramos.
PREFIXOS_CONTA_COMPRA_ANIMAL = ["3.10.06", "3.10.07"]
ICMS_TIPOS = ("intermunicipal", "interestadual")


class CompraIn(BaseModel):
    animais: list[str]
    vendedor: str
    valor: float
    tipo_valor: str  # "por_animal" | "total"
    data_compra: date
    observacao: str | None = None
    responsavel: str | None = None

    # Conta gerencial (restrita a PREFIXOS_CONTA_COMPRA_ANIMAL no frontend).
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

    gta: str | None = None
    icms_incide: bool = False
    icms_tipo: str | None = None
    icms_valor: float | None = None

    pagar_comissao: bool = False
    corretor_nome: str | None = None
    valor_comissao: float | None = None
    forma_comissao: str | None = None  # "redirecionado" | "separado"
    data_vencimento_comissao: date | None = None
    parcelas_comissao: list[ParcelaIn] = []


@router.get("/")
def listar_compras(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(CompraAnimal)
    if fazenda_id is not None:
        query = query.where(CompraAnimal.fazenda_id == fazenda_id)
    compras = session.exec(query.order_by(CompraAnimal.data_compra.desc(), CompraAnimal.id.desc())).all()
    registros = [c.model_dump() for c in compras]
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    for r in registros:
        r["usuario_nome"] = nomes.get(r["usuario_id"])
    return registros


@router.post("/")
def registrar_compra(
    dados: CompraIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Informe ao menos um animal")
    if not (dados.vendedor or "").strip():
        raise HTTPException(status_code=400, detail="Informe o vendedor")
    if dados.valor is None or dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Informe o valor da compra")
    if dados.tipo_valor not in TIPOS_VALOR:
        raise HTTPException(status_code=400, detail="Informe se o valor é por animal ou total")
    if not (dados.codigo_conta_gerencial or "").strip():
        raise HTTPException(status_code=400, detail="Selecione a conta gerencial da compra")
    if dados.icms_incide and dados.icms_tipo not in ICMS_TIPOS:
        raise HTTPException(status_code=400, detail="Informe se o ICMS é intermunicipal ou interestadual")
    if dados.pagar_comissao:
        if not (dados.corretor_nome or "").strip() or not dados.valor_comissao or dados.valor_comissao <= 0:
            raise HTTPException(status_code=400, detail="Informe corretor e valor da comissão")
        if dados.forma_comissao not in FORMAS_COMISSAO:
            raise HTTPException(status_code=400, detail="Informe a forma de pagamento da comissão")

    quantidade = len(dados.animais)
    if dados.tipo_valor == "por_animal":
        valor_unitario = round(dados.valor, 2)
        valor_total_bruto = round(valor_unitario * quantidade, 2)
    else:
        valor_total_bruto = round(dados.valor, 2)
        valor_unitario = round(valor_total_bruto / quantidade, 2)
    valor_liquido = round(valor_total_bruto - (dados.desconto or 0) + (dados.acrescimo or 0), 2)

    numero_lancamento = _proximo_numero_lancamento(session, dados.data_compra.year)
    descricao = dados.descricao or f"Compra de {quantidade} animal(is) — {dados.vendedor}"
    campos_comuns = dict(
        numero_lancamento=numero_lancamento,
        codigo_conta=dados.codigo_conta_gerencial,
        descricao=descricao,
        centro_custo=dados.centro_custo,
        fornecedor_cliente=dados.vendedor,
        responsavel=dados.responsavel,
        tipo_documento=dados.tipo_documento or "Compra de animal",
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
        fazenda_id=fazenda_id,
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

    if dados.pagar_comissao:
        criar_comissao(
            session,
            origem_tipo="compra_animal",
            numero_lancamento_origem=numero_lancamento,
            corretor_nome=dados.corretor_nome,
            valor_comissao=dados.valor_comissao,
            forma=dados.forma_comissao,
            data_transacao=dados.data_compra,
            descricao_origem=f"compra de {quantidade} animal(is) de {dados.vendedor}",
            centro_custo=dados.centro_custo,
            origem_paga=paga_agora,
            origem_data_pagamento=dados.data_pagamento,
            origem_conta_bancaria=dados.conta_bancaria,
            data_vencimento_comissao=dados.data_vencimento_comissao,
            parcelas_comissao=[(p.data_vencimento, p.valor) for p in dados.parcelas_comissao] or None,
            fazenda_id=fazenda_id,
        )

    comprados = []
    for numero in dados.animais:
        session.add(CompraAnimal(
            numero_animal=numero, vendedor=dados.vendedor, valor=valor_unitario,
            tipo_valor=dados.tipo_valor, data_compra=dados.data_compra,
            responsavel=dados.responsavel, observacao=dados.observacao,
            numero_lancamento_gerado=numero_lancamento,
            gta=dados.gta, icms_incide=dados.icms_incide, icms_tipo=dados.icms_tipo, icms_valor=dados.icms_valor,
            usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
        ))
        # Vincula o valor da compra à ficha do animal (para o relatório de
        # payback quando ele produzir). Preenche data de entrada e vendedor.
        query_animal = select(Animal).where(Animal.numero == numero)
        if fazenda_id is not None:
            query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        animal = session.exec(query_animal).first()
        if animal:
            animal.valor = valor_unitario
            if not animal.data_entrada:
                animal.data_entrada = dados.data_compra
            if not animal.proprietario:
                animal.proprietario = dados.vendedor
            session.add(animal)
        comprados.append(numero)

    session.commit()
    return {"comprados": len(comprados), "animais": comprados, "numero_lancamento": numero_lancamento}
