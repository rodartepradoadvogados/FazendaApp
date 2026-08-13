"""
Router de compra de sêmen (Lançamentos > Compra/Venda > Comprar sêmen) —
registra o efeito financeiro/histórico da aquisição (lançamento em
ContaGerencial, restrito à conta gerencial de Sêmen) e soma as doses
compradas ao Estoque de Sêmen, seja de um touro já cadastrado na fazenda
(origem="estoque") ou de um touro do banco de dados NAAB (origem="naab" —
casa por NAAB com uma linha de EstoqueSemen existente, ou cria uma nova).
É essa soma em EstoqueSemen.doses que faz a compra "comunicar" com os
relatórios de estoque de sêmen e com a baixa por dose nas aplicações de
inseminação (ver fazenda.api.routers.reproducao). Também grava um
MovimentoEstoque "Entrada de compra" por item — sem isso a compra tinha
saldo certo, mas nenhum rastro no Mapa de entradas do Estoque.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import CompraSemen, ContaGerencial, Estoque, EstoqueSemen, MovimentoEstoque, Touro, Usuario
from fazenda.api.routers.financeiro import ParcelaIn, _proximo_numero_lancamento
from fazenda.api.routers.estoque import sincronizar_item_estoque_semen
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios, usuario_id_seguro

router = APIRouter(prefix="/compras-semen", tags=["compras-semen"])

TIPOS_VALOR = ("por_dose", "total")
ORIGENS = ("estoque", "naab")
# Sêmen sexado x convencional — modalidades realmente compráveis (o 3º valor
# de EstoqueSemen.tipo, "fazenda", é touro de monta natural, nunca comprado
# por nota fiscal de sêmen).
TIPOS_SEMEN_COMPRA = ("convencional", "sexado")
# Única conta gerencial onde a compra de sêmen deve ser lançada — o seletor
# do frontend só mostra esta folha (não é um ramo com sub-contas, como em
# compra_animal.py; é uma conta-folha específica).
PREFIXOS_CONTA_COMPRA_SEMEN = ["3.01.02.01"]


class ItemCompraSemenIn(BaseModel):
    origem: str  # "estoque" | "naab"
    estoque_semen_id: int | None = None  # obrigatório se origem == "estoque"
    naab: str | None = None              # obrigatório se origem == "naab"
    touro_nome: str | None = None        # obrigatório se origem == "naab" (nome a gravar/exibir)
    central: str | None = None           # opcional, só usado ao criar uma linha nova de EstoqueSemen
    # Sexado ou convencional — só relevante quando origem == "naab" (decide
    # com qual linha de EstoqueSemen casar/criar); ignorado quando origem ==
    # "estoque", já que a linha escolhida já tem seu próprio tipo definido.
    tipo: str = "convencional"

    valor: float
    tipo_valor: str  # "por_dose" | "total"
    doses: int


class CompraSemenIn(BaseModel):
    # Um ou mais sêmens/touros comprados na mesma nota fiscal — todos
    # compartilham vendedor, documento, parcelamento e pagamento abaixo.
    itens: list[ItemCompraSemenIn]

    vendedor: str
    data_compra: date
    observacao: str | None = None
    responsavel: str | None = None

    # Conta gerencial (restrita a PREFIXOS_CONTA_COMPRA_SEMEN no frontend).
    codigo_conta_gerencial: str
    descricao: str | None = None
    centro_custo: str = "Pecuária Leiteira"
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
def listar_compras(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(CompraSemen).order_by(CompraSemen.data_compra.desc(), CompraSemen.id.desc())
    if fazenda_id is not None:
        query = query.where(CompraSemen.fazenda_id == fazenda_id)
    compras = session.exec(query).all()
    registros = [c.model_dump() for c in compras]
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    for r in registros:
        r["usuario_nome"] = nomes.get(r["usuario_id"])
    return registros


@router.post("/")
def registrar_compra(
    dados: CompraSemenIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Adicione ao menos um sêmen/touro à compra")
    if not (dados.vendedor or "").strip():
        raise HTTPException(status_code=400, detail="Informe o vendedor")
    if not (dados.codigo_conta_gerencial or "").strip():
        raise HTTPException(status_code=400, detail="Selecione a conta gerencial da compra")
    if not any(dados.codigo_conta_gerencial.startswith(p) for p in PREFIXOS_CONTA_COMPRA_SEMEN):
        raise HTTPException(status_code=400, detail="A conta gerencial da compra de sêmen deve ser 3.01.02.01 — Sêmen")

    # Resolve, para cada item, o touro/linha de EstoqueSemen a incrementar —
    # de um touro já cadastrado na fazenda, ou casando/criando por NAAB — e
    # calcula o valor daquele item. Vários itens desta lista compartilham a
    # mesma nota fiscal/parcelamento, montados uma única vez abaixo.
    resolvidos: list[tuple[EstoqueSemen, ItemCompraSemenIn, float, float]] = []
    for item in dados.itens:
        if item.origem not in ORIGENS:
            raise HTTPException(status_code=400, detail="Informe a origem do sêmen (estoque ou NAAB)")
        if item.valor is None or item.valor <= 0:
            raise HTTPException(status_code=400, detail="Informe o valor da compra de cada sêmen/touro")
        if item.tipo_valor not in TIPOS_VALOR:
            raise HTTPException(status_code=400, detail="Informe se o valor é por dose ou total")
        if not item.doses or item.doses <= 0:
            raise HTTPException(status_code=400, detail="Informe o número de doses compradas de cada sêmen/touro")

        if item.origem == "estoque":
            if not item.estoque_semen_id:
                raise HTTPException(status_code=400, detail="Selecione o touro em estoque")
            estoque = session.get(EstoqueSemen, item.estoque_semen_id)
            if not estoque or (fazenda_id is not None and estoque.fazenda_id != fazenda_id):
                raise HTTPException(status_code=404, detail="Touro em estoque não encontrado")
        else:
            if not (item.naab or "").strip():
                raise HTTPException(status_code=400, detail="Selecione o touro do banco de dados NAAB")
            if item.tipo not in TIPOS_SEMEN_COMPRA:
                raise HTTPException(status_code=400, detail="Informe se o sêmen é sexado ou convencional")
            touro_naab = session.exec(select(Touro).where(Touro.naab == item.naab)).first()
            if not touro_naab:
                raise HTTPException(status_code=404, detail="Touro NAAB não encontrado")
            # Casa por NAAB *e* tipo — o mesmo touro pode ter uma linha de
            # estoque convencional e outra sexada; comprar um sêmen sexado de
            # um touro já em estoque como convencional não pode misturar as
            # doses na mesma linha (são produtos diferentes).
            estoque_query = select(EstoqueSemen).where(EstoqueSemen.naab == item.naab, EstoqueSemen.tipo == item.tipo)
            if fazenda_id is not None:
                estoque_query = estoque_query.where(EstoqueSemen.fazenda_id == fazenda_id)
            estoque = session.exec(estoque_query).first()
            if not estoque:
                estoque = EstoqueSemen(
                    touro_nome=item.touro_nome or touro_naab.nome or touro_naab.naab,
                    naab=touro_naab.naab, central=item.central or touro_naab.central,
                    tipo=item.tipo, doses=0, fazenda_id=fazenda_id,
                )
                session.add(estoque)
                session.flush()

        if item.tipo_valor == "por_dose":
            valor_unitario = round(item.valor, 2)
            valor_total_bruto = round(valor_unitario * item.doses, 2)
        else:
            valor_total_bruto = round(item.valor, 2)
            valor_unitario = round(valor_total_bruto / item.doses, 2)
        resolvidos.append((estoque, item, valor_unitario, valor_total_bruto))

    quantidade_total = sum(item.doses for item in dados.itens)
    valor_bruto = round(sum(vt for _, _, _, vt in resolvidos), 2)
    valor_liquido = round(valor_bruto - (dados.desconto or 0) + (dados.acrescimo or 0), 2)
    # Só faz sentido resumir um valor/dose único em ContaGerencial quando há
    # apenas um item — com vários touros de preços distintos, cada um já
    # guarda o próprio valor_unitario na sua linha de CompraSemen abaixo.
    valor_unitario_resumo = resolvidos[0][2] if len(resolvidos) == 1 else None

    numero_lancamento = _proximo_numero_lancamento(session, dados.data_compra.year)
    nomes_touros = ", ".join(dict.fromkeys(estoque.touro_nome for estoque, _, _, _ in resolvidos))
    descricao = dados.descricao or f"Compra de {quantidade_total} dose(s) de sêmen — {nomes_touros} ({dados.vendedor})"
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
        quantidade=quantidade_total,
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
                **campos_comuns, data_vencimento=p.data_vencimento, valor_unitario=valor_unitario_resumo,
                valor_total=p.valor, parcela_num=i, parcela_total=total_parcelas,
            ))
    else:
        registro = ContaGerencial(
            **campos_comuns,
            data_vencimento=dados.data_vencimento or dados.data_prevista_entrada or dados.data_compra,
            valor_unitario=valor_unitario_resumo, valor_total=valor_liquido,
            parcela_num=1, parcela_total=1,
        )
        if paga_agora:
            registro.data_pagamento = dados.data_pagamento
            registro.valor_pago = dados.valor_pago
            registro.conta_bancaria = dados.conta_bancaria
            registro.numero_documento_pagamento = dados.numero_documento_pagamento
        session.add(registro)

    usuario_id = usuario_id_seguro(user)
    estoque_semen_ids = []
    for estoque, item, valor_unitario, _ in resolvidos:
        estoque.doses = estoque.doses + item.doses
        estoque.valor_unitario = valor_unitario
        session.add(estoque)
        session.flush()
        sincronizar_item_estoque_semen(estoque, session)

        compra = CompraSemen(
            estoque_semen_id=estoque.id, touro_nome=estoque.touro_nome, naab=estoque.naab,
            origem=item.origem, tipo=estoque.tipo, doses=item.doses, valor_unitario=valor_unitario,
            vendedor=dados.vendedor, data_compra=dados.data_compra,
            responsavel=dados.responsavel, observacao=dados.observacao,
            numero_lancamento_gerado=numero_lancamento,
            usuario_id=usuario_id, fazenda_id=fazenda_id,
        )
        session.add(compra)
        session.flush()

        # Sem isto, a compra somava as doses certinho em EstoqueSemen (e a
        # aplicação/inseminação já baixava e registrava normalmente — ver
        # estoque_baixa.baixar_dose_semen), mas a ENTRADA em si nunca deixava
        # rastro em MovimentoEstoque — sumia do Mapa de entradas do Estoque e
        # de qualquer relatório de movimentação, mesmo com o saldo certo.
        item_espelho = session.exec(select(Estoque).where(Estoque.estoque_semen_id == estoque.id)).first()
        session.add(MovimentoEstoque(
            nome_item=estoque.touro_nome, movimento="Entrada de compra", quantidade=item.doses, unidade="dose",
            data_movimento=dados.data_compra, observacao=f"Compra de sêmen — {dados.vendedor} (lançamento {numero_lancamento})",
            usuario_id=usuario_id, fazenda_id=fazenda_id,
            estoque_id=item_espelho.id if item_espelho is not None else None,
            origem_tipo="compra_semen", origem_id=compra.id,
        ))
        estoque_semen_ids.append(estoque.id)

    session.commit()
    return {"doses_compradas": quantidade_total, "estoque_semen_ids": estoque_semen_ids, "numero_lancamento": numero_lancamento}
