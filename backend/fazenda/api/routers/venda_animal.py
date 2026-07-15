"""
Router de venda de animal (Lançamentos > Compra/Venda > Vender animal) —
espelha compra_animal.py: lançamento (receita) rico em ContaGerencial (conta
gerencial restrita às contas de venda de animal, centro de custo, documento,
datas, parcelamento, recebimento), GTA e ICMS quando houver, motivo(s) e
categoria(s) da venda, e comissão de corretagem opcional.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import Animal, ContaGerencial, Usuario, VendaAnimal
from fazenda.api.routers.financeiro import ParcelaIn, _proximo_numero_lancamento
from fazenda.rules.auditoria import mapa_usuarios, usuario_id_seguro
from fazenda.rules.comissao import FORMAS_COMISSAO, criar_comissao

router = APIRouter(prefix="/vendas-animais", tags=["vendas-animais"])

TIPOS_VALOR = ("por_animal", "total")
# Ramo do plano de contas onde a receita de venda de animal deve ser lançada.
PREFIXOS_CONTA_VENDA_ANIMAL = ["2.01.02"]
ICMS_TIPOS = ("intermunicipal", "interestadual")


class VendaIn(BaseModel):
    animais: list[str]
    comprador: str
    valor: float
    tipo_valor: str  # "por_animal" | "total"
    data_venda: date
    observacao: str | None = None
    responsavel: str | None = None
    categorias: list[str] = []  # ex.: ["Vaca", "Novilha"] — pode misturar categorias na mesma nota
    motivo_venda: str | None = None

    codigo_conta_gerencial: str
    descricao: str | None = None
    centro_custo: str | None = None
    tipo_documento: str | None = None
    numero_documento: str | None = None
    data_emissao: date | None = None
    data_vencimento: date | None = None
    data_prevista_saida: date | None = None
    data_pedido: date | None = None
    entregue: bool | None = None  # "já foi entregue/recebido" (aqui: entregue ao comprador)
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
    forma_comissao: str | None = None
    data_vencimento_comissao: date | None = None
    parcelas_comissao: list[ParcelaIn] = []


@router.get("/")
def listar_vendas(session: Session = Depends(get_session)) -> list[dict]:
    vendas = session.exec(select(VendaAnimal).order_by(VendaAnimal.data_venda.desc(), VendaAnimal.id.desc())).all()
    registros = [v.model_dump() for v in vendas]
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    for r in registros:
        r["usuario_nome"] = nomes.get(r["usuario_id"])
    return registros


@router.post("/")
def registrar_venda(dados: VendaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Informe ao menos um animal")
    if not (dados.comprador or "").strip():
        raise HTTPException(status_code=400, detail="Informe o comprador")
    if dados.valor is None or dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Informe o valor da venda")
    if dados.tipo_valor not in TIPOS_VALOR:
        raise HTTPException(status_code=400, detail="Informe se o valor é por animal ou total")
    if not (dados.codigo_conta_gerencial or "").strip():
        raise HTTPException(status_code=400, detail="Selecione a conta gerencial da venda")
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

    categorias_txt = ",".join(dados.categorias) if dados.categorias else None
    numero_lancamento = _proximo_numero_lancamento(session, dados.data_venda.year)
    descricao = dados.descricao or f"Venda de {quantidade} animal(is) — {dados.comprador}"
    campos_comuns = dict(
        numero_lancamento=numero_lancamento,
        codigo_conta=dados.codigo_conta_gerencial,
        descricao=descricao,
        centro_custo=dados.centro_custo,
        fornecedor_cliente=dados.comprador,
        responsavel=dados.responsavel,
        tipo_documento=dados.tipo_documento or "Venda de animal",
        numero_nota=dados.numero_documento,
        data_emissao=dados.data_emissao,
        data_competencia=dados.data_venda,
        data_prevista_entrada=dados.data_prevista_saida,  # mesma coluna serve p/ "data prevista" (entrada OU saída, a depender do fluxo)
        data_pedido=dados.data_pedido,
        entregue=dados.entregue,
        quantidade=quantidade,
        desconto_nota=dados.desconto or None,
        acrescimo_nota=dados.acrescimo or None,
        tipo="receita", origem="manual",
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
            data_vencimento=dados.data_vencimento or dados.data_prevista_saida or dados.data_venda,
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
            origem_tipo="venda_animal",
            numero_lancamento_origem=numero_lancamento,
            corretor_nome=dados.corretor_nome,
            valor_comissao=dados.valor_comissao,
            forma=dados.forma_comissao,
            data_transacao=dados.data_venda,
            descricao_origem=f"venda de {quantidade} animal(is) para {dados.comprador}",
            centro_custo=dados.centro_custo,
            origem_paga=paga_agora,
            origem_data_pagamento=dados.data_pagamento,
            origem_conta_bancaria=dados.conta_bancaria,
            data_vencimento_comissao=dados.data_vencimento_comissao,
            parcelas_comissao=[(p.data_vencimento, p.valor) for p in dados.parcelas_comissao] or None,
        )

    vendidos = []
    for numero in dados.animais:
        session.add(VendaAnimal(
            numero_animal=numero, comprador=dados.comprador, valor=valor_unitario,
            tipo_valor=dados.tipo_valor, data_venda=dados.data_venda,
            responsavel=dados.responsavel, observacao=dados.observacao,
            categorias=categorias_txt, motivo_venda=dados.motivo_venda,
            numero_lancamento_gerado=numero_lancamento,
            gta=dados.gta, icms_incide=dados.icms_incide, icms_tipo=dados.icms_tipo, icms_valor=dados.icms_valor,
            usuario_id=usuario_id_seguro(user),
        ))
        # A venda tira o animal do rebanho ativo — mesmo efeito de Rebanho >
        # Baixar animal > motivo "venda" (Animal.ativo/data_baixa/motivo_baixa),
        # para que relatórios e listas de rebanho ativo fiquem consistentes
        # não importa por qual tela a venda foi lançada.
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if animal:
            animal.ativo = False
            animal.data_baixa = dados.data_venda
            animal.motivo_baixa = "venda"
            animal.atualizado_em = datetime.utcnow()
            session.add(animal)
        vendidos.append(numero)

    session.commit()
    return {"vendidos": len(vendidos), "animais": vendidos, "numero_lancamento": numero_lancamento}
