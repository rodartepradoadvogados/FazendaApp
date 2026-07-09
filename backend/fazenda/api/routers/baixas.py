"""
Router de baixa de animal (Rebanho > Baixar animal) — óbito/descarte
definitivo do rebanho, distinto de movimentação entre lotes. Ao registrar,
o(s) animal(is) selecionado(s) ficam inativos (Animal.ativo = False).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, BaixaAnimal, ContaGerencial, MotivoBaixa
from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.rules.comissao import FORMAS_COMISSAO, criar_comissao

router = APIRouter(prefix="/baixas", tags=["baixas"])

TIPOS_BAIXA = ["morte", "descarte_voluntario", "descarte_involuntario"]
MOTIVOS = ["venda", "abate", "acidente", "doenca"]
TIPOS_VALOR = ("por_animal", "total")


class BaixaIn(BaseModel):
    animais: list[str]
    tipo_baixa: str
    motivo: str
    motivo_doenca: str | None = None
    valor: float | None = None
    cliente: str | None = None
    tipo_valor: str | None = None  # "por_animal" | "total" — exigido quando motivo == "venda"
    data_baixa: date
    observacao: str | None = None
    responsavel: str | None = None
    pagar_comissao: bool = False
    corretor_nome: str | None = None
    valor_comissao: float | None = None
    forma_comissao: str | None = None  # "redirecionado" | "separado"


@router.get("/motivos")
def listar_opcoes(session: Session = Depends(get_session)) -> dict:
    motivos_doenca = [
        m.nome for m in session.exec(
            select(MotivoBaixa).where(MotivoBaixa.ativo == True).order_by(MotivoBaixa.nome)  # noqa: E712
        ).all()
    ]
    return {"tipos_baixa": TIPOS_BAIXA, "motivos": MOTIVOS, "motivos_doenca": motivos_doenca}


@router.get("/")
def listar_baixas(session: Session = Depends(get_session)) -> list[dict]:
    baixas = session.exec(select(BaixaAnimal).order_by(BaixaAnimal.data_baixa.desc(), BaixaAnimal.id.desc())).all()
    return [b.model_dump() for b in baixas]


@router.post("/")
def registrar_baixa(dados: BaixaIn, session: Session = Depends(get_session)) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")
    if dados.tipo_baixa not in TIPOS_BAIXA:
        raise HTTPException(status_code=400, detail="Tipo de baixa inválido")
    if dados.motivo not in MOTIVOS:
        raise HTTPException(status_code=400, detail="Motivo inválido")
    if dados.motivo == "doenca" and not (dados.motivo_doenca or "").strip():
        raise HTTPException(status_code=400, detail="Informe a doença/causa")
    if dados.motivo == "venda":
        if dados.valor is None or not (dados.cliente or "").strip():
            raise HTTPException(status_code=400, detail="Venda exige valor e cliente")
        if dados.tipo_valor not in TIPOS_VALOR:
            raise HTTPException(status_code=400, detail="Informe se o valor é por animal ou total")
    if dados.pagar_comissao:
        if dados.motivo != "venda":
            raise HTTPException(status_code=400, detail="Comissão de corretagem só se aplica à venda")
        if not (dados.corretor_nome or "").strip() or not dados.valor_comissao or dados.valor_comissao <= 0:
            raise HTTPException(status_code=400, detail="Informe corretor e valor da comissão")
        if dados.forma_comissao not in FORMAS_COMISSAO:
            raise HTTPException(status_code=400, detail="Informe a forma de pagamento da comissão")

    encontrados = []
    nao_encontrados = []
    for numero in dados.animais:
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if not animal:
            nao_encontrados.append(numero)
            continue
        encontrados.append((numero, animal))

    numero_lancamento = None
    valor_unitario = None
    if dados.motivo == "venda" and encontrados:
        quantidade = len(encontrados)
        if dados.tipo_valor == "por_animal":
            valor_unitario = round(dados.valor, 2)
            valor_total = round(valor_unitario * quantidade, 2)
        else:
            valor_total = round(dados.valor, 2)
            valor_unitario = round(valor_total / quantidade, 2)

        numero_lancamento = _proximo_numero_lancamento(session, dados.data_baixa.year)
        session.add(ContaGerencial(
            numero_lancamento=numero_lancamento,
            descricao=f"Venda de {quantidade} animal(is) — {dados.cliente}",
            data_vencimento=dados.data_baixa,
            data_competencia=dados.data_baixa,
            fornecedor_cliente=dados.cliente,
            tipo_documento="Venda de animal",
            quantidade=quantidade,
            valor_unitario=valor_unitario,
            valor_total=valor_total,
            parcela_num=1, parcela_total=1,
            tipo="receita", origem="auto",
        ))

        if dados.pagar_comissao:
            criar_comissao(
                session,
                origem_tipo="venda_animal",
                numero_lancamento_origem=numero_lancamento,
                corretor_nome=dados.corretor_nome,
                valor_comissao=dados.valor_comissao,
                forma=dados.forma_comissao,
                data_transacao=dados.data_baixa,
                descricao_origem=f"venda de {quantidade} animal(is) para {dados.cliente}",
            )

    baixados = []
    for numero, animal in encontrados:
        session.add(BaixaAnimal(
            numero_animal=numero, tipo_baixa=dados.tipo_baixa, motivo=dados.motivo,
            motivo_doenca=dados.motivo_doenca if dados.motivo == "doenca" else None,
            valor=valor_unitario if dados.motivo == "venda" else None,
            cliente=dados.cliente if dados.motivo == "venda" else None,
            tipo_valor=dados.tipo_valor if dados.motivo == "venda" else None,
            numero_lancamento_gerado=numero_lancamento,
            data_baixa=dados.data_baixa, observacao=dados.observacao, responsavel=dados.responsavel,
        ))

        animal.ativo = False
        animal.data_baixa = dados.data_baixa
        animal.motivo_baixa = dados.motivo_doenca if dados.motivo == "doenca" else dados.motivo
        animal.atualizado_em = datetime.utcnow()
        session.add(animal)
        baixados.append(numero)

    session.commit()
    return {"baixados": len(baixados), "animais": baixados, "nao_encontrados": nao_encontrados}
