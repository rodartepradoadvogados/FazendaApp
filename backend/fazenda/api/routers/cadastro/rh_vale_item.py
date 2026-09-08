"""
Cadastro > Vale a partir de item de lançamento financeiro — quando uma linha
de uma nota (ex.: "Ração para cães 15kg" numa compra de insumos da
cooperativa) é, na verdade, gasto pessoal de um funcionário/empreiteiro/
diarista. O dinheiro já saiu de verdade na compra (o caixa da fazenda
continua batendo), mas gerencialmente isso não é despesa da fazenda e sim
adiantamento A RECEBER da pessoa — então o item vira um vale de VERDADE
(ValeFuncionario ou ValeAvulso, ver rh_folha.py/rh_contratos.py) e passa a
ser ignorado por todo relatório gerencial (ver rules/vale_item.py).

Arquivo próprio (não em rh_folha.py/rh_contratos.py, que já são grandes) —
mas o pacote `cadastro` PODE importar `financeiro` (o contrário não: ver
fazenda/api/routers/financeiro.py, que só importa este módulo localmente
dentro de função, para não formar ciclo de import).

NÃO reimplementa parcelamento, limite de 40% do salário, nem abatimento de
empreitada/contrato/diária — tudo isso é decidido por `criar_vale`
(rh_folha.py) e `criar_vale_avulso` (rh_contratos.py), chamados aqui como
função Python (mesmo padrão de `gerar_lancamento_recorrente`, que chama
`criar_lancamento` diretamente).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    ContaGerencial, Contrato, Diaria, Empreitada, LancamentoItem, Pessoa, Usuario, ValeParcela,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.vale_item import dividir_item_de_lancamento, eh_item_de_vale

from .rh_contratos import (
    ORIGENS_VALE_AVULSO,
    ValeAvulsoIn,
    _itens_pendentes_vale_avulso,
    _origem_vale_avulso,
    _resumo_diaria,
    criar_vale_avulso,
    excluir_vale_avulso,
)
from .rh_folha import (
    ValeIn,
    _competencias_do_vale,
    _exigir_competencias_nao_pagas,
    criar_vale,
    excluir_vale as excluir_vale_funcionario,
)

router = APIRouter()

# Fixados no servidor (ver §0.2 do plano) — o dinheiro já saiu na compra
# original, então o vale gerado a partir de um item NUNCA pode movimentar
# caixa de novo. `criar_vale`/`criar_vale_avulso` já sabem NÃO criar
# ContaGerencial nenhuma para essas duas formas de pagamento.
FORMA_PAGAMENTO_VALE_ITEM_FOLHA = "desconto_integral_folha"
FORMA_PAGAMENTO_VALE_ITEM_AVULSO = "desconto_proximo_pagamento"

STATUS_ENCERRADO_POR_ORIGEM = {"empreitada": "concluida", "contrato": "encerrado", "diaria": "encerrado"}


def _fmt_brl(valor: float | None) -> str:
    return f"{float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _rotulo_origem(origem_tipo: str, origem) -> str:
    if origem_tipo == "empreitada":
        return f"Empreitada — {origem.descricao}"
    if origem_tipo == "contrato":
        return f"Contrato — {origem.descricao}"
    return f"Diária — R$ {_fmt_brl(origem.valor_diaria)}/dia (desde {origem.data_inicio.strftime('%d/%m/%Y')})"


# ---------------------------------------------------------------------------
# Serviço compartilhado — request do POST/opções e as duas funções que fazem
# o trabalho de verdade (chamadas pelos endpoints deste arquivo E por
# `criar_lancamento`, em financeiro.py, via import local).
# ---------------------------------------------------------------------------
class ValeItemIn(BaseModel):
    pessoa_id: int
    modo: str  # "folha" | "avulso" — obrigatório
    # Quanto DO ITEM é vale. O caso que criou este campo, na palavra do dono:
    # "Tenho cachorros e o funcionário também, daí 2/3 do preço da ração de
    # cachorro que eu marco como vale de funcionário é do funcionário, vale,
    # e 1/3 eu que pago." Até aqui o checkbox era tudo-ou-nada e a única
    # saída era digitar duas linhas de item na nota, na mão, com a conta
    # gerencial e o centro de custo repetidos.
    # "integral" (padrão, comportamento de sempre) | "parcial".
    abrangencia: str = "integral"
    # Sendo parcial, EXATAMENTE UM dos dois: percentual do item (0 < x < 100)
    # ou valor em reais (0 < x < valor do item). Os dois juntos, ou nenhum,
    # são erro — não há regra de desempate que não fosse chute.
    percentual: float | None = None
    valor: float | None = None
    # modo == "folha"
    parcelas: int = 1
    competencia_inicio: str | None = None  # "AAAA-MM"; None => mês da data do vale
    # modo == "avulso"
    origem_tipo: str | None = None  # empreitada | contrato | diaria
    origem_id: int | None = None
    observacao: str | None = None
    confirmar: bool = False  # repassa o "confirmar" do 409 de 40% do salário


def valor_vale_do_item(valor_item: float, dados: ValeItemIn) -> float:
    """Quanto do item é vale do funcionário — o item inteiro (padrão) ou a
    fatia informada em percentual/valor. Sempre arredondado a 2 casas, e
    sempre menor que o item quando é parcial: o RESTO é o que vira despesa
    normal da fazenda (decisão textual do dono), e um resto zero não seria
    "parcial" coisa nenhuma, seria integral com passos a mais.

    Função pura (sem I/O) para o mesmo número ser calculado no validar (antes
    de gravar qualquer coisa) e no aplicar — se cada um fizesse sua conta, o
    limite de 40% do salário seria checado sobre um valor e o vale nasceria
    com outro."""
    valor_item = round(valor_item, 2)
    if dados.abrangencia == "integral":
        return valor_item
    if dados.abrangencia != "parcial":
        raise HTTPException(status_code=400, detail="Abrangência do vale inválida: use 'integral' ou 'parcial'.")

    informados = [x for x in (dados.percentual, dados.valor) if x is not None]
    if len(informados) != 1:
        raise HTTPException(
            status_code=400,
            detail="Vale parcial: informe o percentual OU o valor da parte do funcionário — um dos dois, não os dois.",
        )
    if dados.percentual is not None:
        if not (0 < dados.percentual < 100):
            raise HTTPException(
                status_code=400,
                detail="O percentual do vale precisa ficar entre 0 e 100 (100% é vale integral).",
            )
        valor_vale = round(valor_item * dados.percentual / 100, 2)
    else:
        valor_vale = round(dados.valor, 2)

    if valor_vale <= 0:
        raise HTTPException(status_code=400, detail="A parte do funcionário precisa ser maior que zero.")
    if valor_vale >= valor_item:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A parte do funcionário (R$ {_fmt_brl(valor_vale)}) precisa ser menor que o valor do item "
                f"(R$ {_fmt_brl(valor_item)}) — para o item inteiro, use vale integral."
            ),
        )
    return valor_vale


def _resolver_data_pagamento_vale(item: LancamentoItem, session: Session, fazenda_id: int | None) -> date:
    """data_pagamento do vale = data da compra: ContaGerencial.data_emissao
    or .data_competencia or .data_vencimento da primeira parcela do mesmo
    numero_lancamento; fallback LancamentoItem.data_competencia; fallback hoje.

    `fazenda_id` vem do endpoint (`get_fazenda_id_escrita`) e entra
    INCONDICIONALMENTE no `where`, apesar de isto ser só leitura: o número do
    lançamento é sequencial por ano e se repete entre fazendas numa base
    importada, e a data que sai daqui vira `data_pagamento` do vale — ou seja,
    a compra de OUTRO inquilino datando um vale que não é dele, e ainda por
    cima escolhendo em silêncio (o `.first()` não tem como saber que pegou a
    nota errada). O item já foi validado contra este mesmo `fazenda_id` pelos
    chamadores, então o recorte aqui nunca esconde a nota certa."""
    primeira = session.exec(
        select(ContaGerencial)
        .where(
            ContaGerencial.numero_lancamento == item.numero_lancamento,
            ContaGerencial.fazenda_id == fazenda_id,
        )
        .order_by(ContaGerencial.parcela_num)
    ).first()
    if primeira:
        data = primeira.data_emissao or primeira.data_competencia or primeira.data_vencimento
        if data:
            return data
    if item.data_competencia:
        return item.data_competencia
    return date.today()


def validar_vale_item(
    session: Session, item_valor: float, item_data: date, dados: ValeItemIn, fazenda_id: int | None,
) -> dict:
    """Valida SEM gravar nada. Levanta HTTPException(400/404/409) exatamente
    com as mensagens dos endpoints existentes. Devolve o contexto resolvido
    (pessoa, origem, competências) para `aplicar_vale_item` não refazer."""
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if item_valor <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.modo not in ("folha", "avulso"):
        raise HTTPException(status_code=400, detail="Modo de vale inválido")
    # Vale parcial: daqui para baixo tudo (limite de 40%, parcelas, valor do
    # vale gerado) é sobre a FATIA DO FUNCIONÁRIO, nunca sobre o item inteiro
    # — o resto é despesa da fazenda e nunca foi dele.
    valor_vale = valor_vale_do_item(item_valor, dados)

    if dados.modo == "folha":
        if dados.parcelas < 1:
            raise HTTPException(status_code=400, detail="Informe ao menos 1 parcela")
        if not pessoa.salario_base:
            raise HTTPException(
                status_code=400,
                detail="Cadastre o salário base da pessoa (Configurações > Cadastro > Pessoas) antes de lançar um vale.",
            )
        competencia_inicio = dados.competencia_inicio or item_data.strftime("%Y-%m")
        competencias = _competencias_do_vale(competencia_inicio, dados.parcelas)
        # Mesma trava de `criar_vale`, aplicada aqui porque este caminho
        # valida ANTES de gravar a nota inteira: um vale de item lançado numa
        # competência com folha já paga entraria num holerite fechado.
        _exigir_competencias_nao_pagas(session, dados.pessoa_id, competencias, fazenda_id, "lançar")
        valor_parcela = round(valor_vale / dados.parcelas, 2)
        valores_parcela = [valor_parcela] * (dados.parcelas - 1)
        valores_parcela.append(round(valor_vale - valor_parcela * (dados.parcelas - 1), 2))

        limite = round(pessoa.salario_base * 0.4, 2)
        competencias_excedidas = []
        for competencia, valor in zip(competencias, valores_parcela):
            ja_lancado = session.exec(
                select(ValeParcela).where(
                    ValeParcela.pessoa_id == dados.pessoa_id,
                    ValeParcela.competencia == competencia,
                    ValeParcela.assumida_pela_fazenda == False,  # noqa: E712
                )
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
        return {
            "pessoa": pessoa, "modo": "folha", "competencia_inicio": competencia_inicio,
            "valor_vale": valor_vale,
        }

    # modo == "avulso"
    if not dados.origem_tipo or not dados.origem_id:
        raise HTTPException(
            status_code=400,
            detail="Selecione a empreitada, contrato ou diária de onde o vale será abatido.",
        )
    if dados.origem_tipo not in ORIGENS_VALE_AVULSO:
        raise HTTPException(status_code=400, detail="Tipo de origem inválido")
    origem = _origem_vale_avulso(session, dados.origem_tipo, dados.origem_id, fazenda_id)
    if origem.pessoa_id != dados.pessoa_id:
        raise HTTPException(status_code=400, detail="A origem escolhida não é desta pessoa.")
    status_encerrado = STATUS_ENCERRADO_POR_ORIGEM.get(dados.origem_tipo)
    if status_encerrado and origem.status == status_encerrado:
        raise HTTPException(
            status_code=400,
            detail="Esta empreitada/contrato/diária já foi encerrada — escolha outra origem.",
        )
    return {
        "pessoa": pessoa, "modo": "avulso", "origem": origem, "valor_vale": valor_vale,
        "origem_label": _rotulo_origem(dados.origem_tipo, origem),
    }


def aplicar_vale_item(
    session: Session, item: LancamentoItem, dados: ValeItemIn, user: Usuario, fazenda_id: int | None,
) -> dict:
    """Cria o vale REAPROVEITANDO `criar_vale` (rh_folha.py) ou
    `criar_vale_avulso` (rh_contratos.py) — mesmo padrão de
    `gerar_lancamento_recorrente` (financeiro.py), que chama `criar_lancamento`
    diretamente. NÃO reimplementa parcelamento, limite de 40%,
    `_aplicar_vale_avulso` nem `ValeAvulsoAbatimento`. Grava o vínculo no
    item (vale_funcionario_id ou vale_avulso_id) e commita."""
    data_pagamento = _resolver_data_pagamento_vale(item, session, fazenda_id)
    observacao = dados.observacao or f"Vale gerado do item '{item.produto}' da nota {item.numero_lancamento}"

    # Vale PARCIAL: o item se divide antes de qualquer outra coisa (decisão
    # textual do dono sobre o resto — "Vira despesa normal da fazenda"). A
    # linha original encolhe para a fatia do funcionário e é ELA que recebe o
    # vínculo do vale; o gêmeo com o resto fica sem vínculo nenhum e volta a
    # ser despesa comum, com a mesma conta gerencial e o mesmo centro de
    # custo que a nota já tinha. Divide-se a linha, e não uma coluna "quanto
    # deste item é vale", porque toda soma gerencial do sistema filtra o item
    # inteiro — ver `dividir_item_de_lancamento` em rules/vale_item.py.
    valor_vale = valor_vale_do_item(item.valor_total, dados)
    item_fazenda = None
    if valor_vale < round(item.valor_total, 2):
        item_fazenda = dividir_item_de_lancamento(
            session, item, valor_vale, sufixo_descricao="parte da fazenda",
        )
        session.commit()
        session.refresh(item)
        session.refresh(item_fazenda)
    parte_fazenda = {
        "item_id": item_fazenda.id, "valor": item_fazenda.valor_total, "quantidade": item_fazenda.quantidade,
    } if item_fazenda is not None else None

    if dados.modo == "folha":
        competencia_inicio = dados.competencia_inicio or data_pagamento.strftime("%Y-%m")
        vale_in = ValeIn(
            pessoa_id=dados.pessoa_id,
            valor_total=item.valor_total,
            forma_pagamento=FORMA_PAGAMENTO_VALE_ITEM_FOLHA,
            data_pagamento=data_pagamento,
            parcelas=dados.parcelas,
            competencia_inicio=competencia_inicio,
            observacao=observacao,
            numero_documento_pagamento=None,
            conta_corrente_id=None,
            confirmar=dados.confirmar,
        )
        resultado = criar_vale(dados=vale_in, session=session, user=user, fazenda_id=fazenda_id)
        vale_id = resultado["id"]
        item.vale_funcionario_id = vale_id
        session.add(item)
        session.commit()
        session.refresh(item)
        return {
            "vale_tipo": "funcionario", "vale_id": vale_id, "competencia_inicio": competencia_inicio,
            "valor_vale": item.valor_total, "parte_fazenda": parte_fazenda, "resultado": resultado,
        }

    origem = session.get(
        {"empreitada": Empreitada, "contrato": Contrato, "diaria": Diaria}[dados.origem_tipo], dados.origem_id,
    )
    vale_avulso_in = ValeAvulsoIn(
        origem_tipo=dados.origem_tipo,
        origem_id=dados.origem_id,
        valor=item.valor_total,
        forma_pagamento=FORMA_PAGAMENTO_VALE_ITEM_AVULSO,
        data_pagamento=data_pagamento,
        observacao=observacao,
        conta_corrente_id=None,
    )
    resultado = criar_vale_avulso(dados=vale_avulso_in, session=session, user=user, fazenda_id=fazenda_id)
    vale_id = resultado["vale"]["id"]
    item.vale_avulso_id = vale_id
    session.add(item)
    session.commit()
    session.refresh(item)
    return {
        "vale_tipo": "avulso", "vale_id": vale_id,
        "valor_vale": item.valor_total, "parte_fazenda": parte_fazenda,
        "origem_label": _rotulo_origem(dados.origem_tipo, origem) if origem else None,
        "resultado": resultado,
    }


def desvincular_vale_do_item(
    session: Session, item: LancamentoItem, excluir_vale: bool, fazenda_id: int | None,
) -> dict:
    """excluir_vale=True  -> chama `excluir_vale` (rh_folha.py) ou
                             `excluir_vale_avulso` (rh_contratos.py), que já
                             removem ValeParcela / revertem
                             ValeAvulsoAbatimento e reconciliam a folha (e,
                             por sua vez, já zeram o vínculo do item — ver
                             §3.7 — mas conferimos aqui de novo por segurança).
       excluir_vale=False -> só zera o vínculo no item (o vale sobrevive
                             sozinho no relatório de vales).
       Em ambos os casos o item volta a contar nos relatórios."""
    if item.vale_funcionario_id is not None:
        vale_tipo, vale_id = "funcionario", item.vale_funcionario_id
    else:
        vale_tipo, vale_id = "avulso", item.vale_avulso_id

    if excluir_vale:
        if vale_tipo == "funcionario":
            excluir_vale_funcionario(vale_id=vale_id, session=session, fazenda_id=fazenda_id)
        else:
            excluir_vale_avulso(vale_id=vale_id, session=session, fazenda_id=fazenda_id)

    item.vale_funcionario_id = None
    item.vale_avulso_id = None
    session.add(item)
    session.commit()
    session.refresh(item)
    return {"vale_excluido": excluir_vale, "vale_tipo": vale_tipo, "vale_id": vale_id}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/vale-item/opcoes")
def opcoes_vale_item(
    pessoa_id: int = Query(...), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa or (pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    tipos = [t for t in (pessoa.tipo or "").split(",") if t]

    folha_disponivel = bool(pessoa.salario_base)
    folha = {
        "disponivel": folha_disponivel,
        "motivo": None if folha_disponivel else (
            "Cadastre o salário base da pessoa (Configurações > Cadastro > Pessoas) antes de lançar um vale."
        ),
        "salario_base": pessoa.salario_base,
        "limite_por_competencia": round(pessoa.salario_base * 0.4, 2) if pessoa.salario_base else None,
    }

    origens: list[dict] = []

    query_empreitadas = select(Empreitada).where(Empreitada.pessoa_id == pessoa_id, Empreitada.status != "concluida")
    if fazenda_id is not None:
        query_empreitadas = query_empreitadas.where(Empreitada.fazenda_id == fazenda_id)
    for e in session.exec(query_empreitadas.order_by(Empreitada.criado_em.desc())).all():
        _, itens_pendentes = _itens_pendentes_vale_avulso(session, "empreitada", e.id)
        origens.append({
            "origem_tipo": "empreitada", "origem_id": e.id, "label": _rotulo_origem("empreitada", e),
            "saldo_pendente": round(sum(i.valor for i in itens_pendentes), 2),
            "itens_pendentes": len(itens_pendentes),
        })

    query_contratos = select(Contrato).where(Contrato.pessoa_id == pessoa_id, Contrato.status != "encerrado")
    if fazenda_id is not None:
        query_contratos = query_contratos.where(Contrato.fazenda_id == fazenda_id)
    for c in session.exec(query_contratos.order_by(Contrato.criado_em.desc())).all():
        _, itens_pendentes = _itens_pendentes_vale_avulso(session, "contrato", c.id)
        origens.append({
            "origem_tipo": "contrato", "origem_id": c.id, "label": _rotulo_origem("contrato", c),
            "saldo_pendente": round(sum(i.valor for i in itens_pendentes), 2),
            "itens_pendentes": len(itens_pendentes),
        })

    query_diarias = select(Diaria).where(Diaria.pessoa_id == pessoa_id, Diaria.status != "encerrado")
    if fazenda_id is not None:
        query_diarias = query_diarias.where(Diaria.fazenda_id == fazenda_id)
    for d in session.exec(query_diarias.order_by(Diaria.criado_em.desc())).all():
        resumo = _resumo_diaria(session, d, pessoa.nome)
        origens.append({
            "origem_tipo": "diaria", "origem_id": d.id, "label": _rotulo_origem("diaria", d),
            "saldo_pendente": resumo["saldo_devedor"], "itens_pendentes": None,
        })

    if folha_disponivel:
        sugestao = {"modo": "folha", "origem_tipo": None, "origem_id": None}
    elif len(origens) == 1:
        sugestao = {"modo": "avulso", "origem_tipo": origens[0]["origem_tipo"], "origem_id": origens[0]["origem_id"]}
    elif len(origens) > 1:
        sugestao = {"modo": "avulso", "origem_tipo": None, "origem_id": None}
    else:
        sugestao = None

    bloqueio = None
    if not folha_disponivel and not origens:
        bloqueio = (
            f"{pessoa.nome} não tem salário base cadastrado (necessário para descontar o vale da folha) e não "
            "tem nenhuma empreitada, contrato ou diária ativa para abater o vale. Cadastre o salário base em "
            "Configurações ▸ Cadastro ▸ Pessoas, ou lance a empreitada/contrato/diária desta pessoa, antes de "
            "marcar este item como vale."
        )

    return {
        "pessoa_id": pessoa.id, "pessoa_nome": pessoa.nome, "tipos": tipos,
        "folha": folha, "origens": origens, "sugestao": sugestao, "bloqueio": bloqueio,
    }


@router.post("/vale-item/{item_id}", status_code=201)
def marcar_item_como_vale(
    item_id: int, dados: ValeItemIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    item = session.get(LancamentoItem, item_id)
    if not item or (item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de lançamento não encontrado")
    if eh_item_de_vale(item):
        vale_tipo = "funcionario" if item.vale_funcionario_id is not None else "avulso"
        vale_id = item.vale_funcionario_id if item.vale_funcionario_id is not None else item.vale_avulso_id
        raise HTTPException(status_code=409, detail={
            "mensagem": "Este item já gerou um vale.", "vale_tipo": vale_tipo, "vale_id": vale_id,
        })
    if item.tipo == "receita":
        raise HTTPException(status_code=400, detail="Só item de despesa pode virar vale.")

    data_pagamento = _resolver_data_pagamento_vale(item, session, fazenda_id)
    contexto = validar_vale_item(session, item.valor_total, data_pagamento, dados, fazenda_id)
    resultado = aplicar_vale_item(session, item, dados, user, fazenda_id)

    pessoa = contexto["pessoa"]
    # `item.valor_total` já é a FATIA DO FUNCIONÁRIO aqui: num vale parcial o
    # item foi encolhido por `aplicar_vale_item` e o resto virou item próprio.
    parte_fazenda = resultado.get("parte_fazenda")
    if dados.modo == "folha":
        parcela_txt = "parcela" if dados.parcelas == 1 else "parcelas"
        resumo = (
            f"Vale de R$ {_fmt_brl(item.valor_total)} para {pessoa.nome} — desconto em {dados.parcelas} "
            f"{parcela_txt} na folha de {resultado['competencia_inicio']}"
        )
    else:
        resumo = f"Vale de R$ {_fmt_brl(item.valor_total)} para {pessoa.nome} — abatido de {contexto['origem_label']}"
    if parte_fazenda:
        resumo += f" · R$ {_fmt_brl(parte_fazenda['valor'])} ficaram como despesa da fazenda"

    return {
        "item_id": item.id,
        "numero_lancamento": item.numero_lancamento,
        "vale_tipo": resultado["vale_tipo"],
        "vale_id": resultado["vale_id"],
        "valor": item.valor_total,
        "parte_fazenda": parte_fazenda,
        "data_pagamento": data_pagamento.isoformat(),
        "pessoa_id": pessoa.id,
        "pessoa_nome": pessoa.nome,
        "resumo": resumo,
    }


@router.delete("/vale-item/{item_id}")
def desmarcar_item_como_vale(
    item_id: int,
    excluir_vale: bool = Query(..., description="true = exclui o vale vinculado; false = só desfaz o vínculo"),
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(LancamentoItem, item_id)
    if not item or (item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de lançamento não encontrado")
    if not eh_item_de_vale(item):
        raise HTTPException(status_code=404, detail="Este item não tem vale vinculado.")

    resultado = desvincular_vale_do_item(session, item, excluir_vale, fazenda_id)
    return {"item_id": item.id, "desvinculado": True, **resultado}
