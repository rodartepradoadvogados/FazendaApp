"""
Faturas de fornecedor — Entrega 1: Lançamento em lote.

O lote cria VÁRIAS notas de uma vez (cada uma é um lançamento completo, como o Lançamento normal:
itens, conta gerencial, estoque, DRE) e as agrupa numa FaturaFornecedor já FECHADA (ou paga). É
TUDO OU NADA: valida tudo antes e grava numa única transação — qualquer falha desfaz o lote inteiro
e aponta a nota com erro.

Cada nota é gravada pela MESMA função do Lançamento normal (`criar_lancamento`); para ela não
comitar no meio do caminho, recebe uma sessão cujo `commit()` só faz `flush()`.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.financeiro import FORMAS_PAGAMENTO, ItemIn, LancamentoIn, ParcelaIn, criar_lancamento
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import ContaGerencial, FaturaFornecedor, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro

router = APIRouter(prefix="/financeiro/faturas", tags=["Faturas de fornecedor"])

MAX_PARCELAS = 24
TIPOS_DOCUMENTO_SEM_NUMERO_OK = None  # o marcador "sem número" vale para qualquer tipo


class NotaLoteIn(BaseModel):
    tipo_documento: str
    numero_documento: str | None = None
    sem_numero: bool = False
    data_emissao: date
    itens: list[ItemIn]
    desconto: float = 0
    acrescimo: float = 0


class ParcelamentoLoteIn(BaseModel):
    n: int
    primeiro_vencimento: date
    intervalo: str = "mensal"  # mensal | 30dias


class PagamentoLoteIn(BaseModel):
    data_pagamento: date
    forma_pagamento: str
    conta_bancaria: str | None = None
    numero_documento_pagamento: str | None = None


class LoteIn(BaseModel):
    fornecedor: str
    conta_bancaria: str | None = None
    centro_custo: str | None = None
    notas: list[NotaLoteIn]
    modo: str = "venc"  # venc | parc | pago
    data_vencimento: date | None = None
    parcelamento: ParcelamentoLoteIn | None = None
    pagamento: PagamentoLoteIn | None = None
    total_fornecedor: float | None = None
    rotulo: str | None = None
    # O usuário já viu e aceitou o aviso correspondente (a tela reenvia com a marca).
    confirmar_divergencia: bool = False
    confirmar_duplicados: bool = False


class _SessaoSemCommit:
    """Sessão que repassa tudo à real, menos o commit: `commit()` vira `flush()`. Assim, funções que
    comitam por conta própria (criar_lancamento, entrada de estoque) participam de UMA transação só,
    que o chamador comita no fim — ou desfaz inteira."""

    def __init__(self, sessao: Session):
        self._s = sessao

    def commit(self) -> None:
        self._s.flush()

    def __getattr__(self, nome: str):
        return getattr(self._s, nome)


def _liquido(nota: NotaLoteIn) -> float:
    return round(sum(i.valor_total for i in nota.itens) - (nota.desconto or 0) + (nota.acrescimo or 0), 2)


def _dividir(valor: float, n: int) -> list[float]:
    """Divide em n partes iguais; os centavos que sobram vão para a última (soma exata)."""
    base = int(valor * 100) // n / 100
    partes = [base] * n
    partes[-1] = round(valor - base * (n - 1), 2)
    return partes


def _vencimentos(par: ParcelamentoLoteIn) -> list[date]:
    saida = []
    for i in range(par.n):
        if par.intervalo == "30dias":
            saida.append(date.fromordinal(par.primeiro_vencimento.toordinal() + 30 * i))
        else:
            mes = par.primeiro_vencimento.month - 1 + i
            ano = par.primeiro_vencimento.year + mes // 12
            mes = mes % 12 + 1
            ultimo = [31, 29 if ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
            saida.append(date(ano, mes, min(par.primeiro_vencimento.day, ultimo)))
    return saida


def _validar(dados: LoteIn) -> None:
    if not (dados.fornecedor or "").strip():
        raise HTTPException(status_code=400, detail="Escolha o fornecedor do lote.")
    if not dados.notas:
        raise HTTPException(status_code=400, detail="Acrescente ao menos uma nota ao lote.")
    if dados.modo not in ("venc", "parc", "pago"):
        raise HTTPException(status_code=400, detail="Modo de pagamento inválido.")
    vistos: dict[tuple[str, str], int] = {}
    for i, nota in enumerate(dados.notas, start=1):
        if not (nota.tipo_documento or "").strip():
            raise HTTPException(status_code=400, detail=f"Nota {i}: escolha o tipo de documento.")
        numero = (nota.numero_documento or "").strip()
        if not numero and not nota.sem_numero:
            raise HTTPException(status_code=400, detail=f"Nota {i}: informe o número do documento ou marque \"sem número\".")
        if not nota.itens:
            raise HTTPException(status_code=400, detail=f"Nota {i}: acrescente ao menos um produto ou serviço.")
        for item in nota.itens:
            if item.tipo_item is not None and item.tipo_item not in ("produto", "servico"):
                raise HTTPException(status_code=400, detail=f"Nota {i}: tipo de item inválido.")
            if not (item.produto or "").strip() or item.valor_total <= 0:
                raise HTTPException(status_code=400, detail=f"Nota {i}: todo item precisa de produto/serviço e valor maior que zero.")
        if _liquido(nota) <= 0:
            raise HTTPException(status_code=400, detail=f"Nota {i}: o valor líquido deve ser positivo.")
        if numero:
            chave = (nota.tipo_documento.strip().lower(), numero.lower())
            if chave in vistos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Nota {i} repete a nota {vistos[chave]} deste lote (mesmo tipo e número {numero}). Corrija antes de lançar.",
                )
            vistos[chave] = i
    if dados.modo == "venc" and not dados.data_vencimento:
        raise HTTPException(status_code=400, detail="Informe o vencimento do lote.")
    if dados.modo == "parc":
        p = dados.parcelamento
        if not p or not 2 <= p.n <= MAX_PARCELAS:
            raise HTTPException(status_code=400, detail=f"Parcelamento: informe de 2 a {MAX_PARCELAS} parcelas.")
        if p.intervalo not in ("mensal", "30dias"):
            raise HTTPException(status_code=400, detail="Intervalo de parcelas inválido.")
    if dados.modo == "pago":
        p = dados.pagamento
        if not p:
            raise HTTPException(status_code=400, detail="Informe a data e a forma do pagamento.")
        if p.forma_pagamento not in FORMAS_PAGAMENTO:
            raise HTTPException(status_code=400, detail="Forma de pagamento inválida.")


def _duplicadas_existentes(session: Session, dados: LoteIn, fazenda_id: int) -> list[dict]:
    """Notas do lote que já existem no Financeiro: mesmo fornecedor + tipo + número (exato).
    Nota sem número não entra: não há o que comparar com exatidão."""
    achados: list[dict] = []
    for i, nota in enumerate(dados.notas, start=1):
        numero = (nota.numero_documento or "").strip()
        if not numero:
            continue
        candidatos = session.exec(
            select(ContaGerencial).where(
                ContaGerencial.fazenda_id == fazenda_id, ContaGerencial.tipo == "despesa",
                ContaGerencial.numero_nota == numero,
            )
        ).all()
        for c in candidatos:
            if (c.fornecedor_cliente or "").strip().lower() != dados.fornecedor.strip().lower():
                continue
            if (c.tipo_documento or "").strip().lower() != nota.tipo_documento.strip().lower():
                continue
            achados.append({
                "nota": i, "numero_documento": numero, "numero_lancamento": c.numero_lancamento,
                "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None, "valor_total": c.valor_total,
            })
            break
    return achados


@router.post("/lote", status_code=201)
def criar_lote(
    dados: LoteIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Lança várias notas de um fornecedor de uma vez, agrupadas numa fatura já fechada (ou paga)."""
    _validar(dados)
    soma = round(sum(_liquido(n) for n in dados.notas), 2)

    if dados.total_fornecedor is not None and abs(round(dados.total_fornecedor - soma, 2)) > 0.005 and not dados.confirmar_divergencia:
        raise HTTPException(status_code=409, detail={
            "codigo": "divergencia_total",
            "mensagem": f"O total das notas (R$ {soma:.2f}) difere do total informado pelo fornecedor "
                        f"(R$ {dados.total_fornecedor:.2f}) em R$ {abs(round(dados.total_fornecedor - soma, 2)):.2f}.",
            "soma_notas": soma, "total_fornecedor": dados.total_fornecedor,
        })
    existentes = _duplicadas_existentes(session, dados, fazenda_id)
    if existentes and not dados.confirmar_duplicados:
        raise HTTPException(status_code=409, detail={
            "codigo": "duplicadas",
            "mensagem": "Algumas notas parecem já lançadas (mesmo fornecedor, tipo e número).",
            "duplicadas": existentes,
        })

    responsavel = (getattr(user, "nome", None) or getattr(user, "username", None) or "").strip() or None
    vencs = _vencimentos(dados.parcelamento) if dados.modo == "parc" else []
    sessao = _SessaoSemCommit(session)
    criadas: list[dict] = []
    todas_contas: list[int] = []
    try:
        for i, nota in enumerate(dados.notas, start=1):
            liquido = _liquido(nota)
            kwargs: dict = {}
            if dados.modo == "venc":
                kwargs["data_vencimento"] = dados.data_vencimento
            elif dados.modo == "parc":
                kwargs["parcelas"] = [
                    ParcelaIn(data_vencimento=v, valor=valor) for v, valor in zip(vencs, _dividir(liquido, dados.parcelamento.n))
                ]
            else:
                p = dados.pagamento
                kwargs.update(
                    data_vencimento=p.data_pagamento, data_pagamento=p.data_pagamento, valor_pago=liquido,
                    conta_bancaria=p.conta_bancaria or dados.conta_bancaria, forma_pagamento=p.forma_pagamento,
                    numero_documento_pagamento=p.numero_documento_pagamento,
                )
            lancamento = LancamentoIn(
                tipo="despesa", itens=nota.itens, centro_custo=dados.centro_custo,
                fornecedor_cliente=dados.fornecedor.strip(), responsavel=responsavel,
                tipo_documento=nota.tipo_documento.strip(),
                numero_documento=(nota.numero_documento or "").strip() or None,
                data_emissao=nota.data_emissao, desconto=nota.desconto or 0, acrescimo=nota.acrescimo or 0, **kwargs,
            )
            try:
                r = criar_lancamento(lancamento, sessao, user, fazenda_id)
            except HTTPException as exc:
                detalhe = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                rotulo_nota = (nota.numero_documento or "sem número").strip() or "sem número"
                raise HTTPException(status_code=exc.status_code, detail=f"Nota {i} ({rotulo_nota}): {detalhe}") from None
            todas_contas += r["ids"]
            criadas.append({
                "nota": i, "numero_lancamento": r["numero_lancamento"], "valor_liquido": r["valor_liquido"],
                "ids": r["ids"], "avisos_estoque": r.get("avisos_estoque", []),
            })

        emissoes = [n.data_emissao for n in dados.notas]
        primeiro_venc = dados.data_vencimento or (vencs[0] if vencs else None) or (dados.pagamento.data_pagamento if dados.pagamento else None)
        mes_ref = min(emissoes)
        rotulo = (dados.rotulo or "").strip() or f"{dados.fornecedor.strip()} — {mes_ref.month:02d}/{mes_ref.year}"
        pago = dados.modo == "pago"
        fatura = FaturaFornecedor(
            fazenda_id=fazenda_id, fornecedor=dados.fornecedor.strip(), rotulo=rotulo,
            data_abertura=min(emissoes), data_fechamento_prevista=max(emissoes), data_vencimento=primeiro_venc,
            conta_bancaria=dados.conta_bancaria, centro_custo=dados.centro_custo,
            parcelas_n=dados.parcelamento.n if dados.modo == "parc" else None,
            total_fornecedor=dados.total_fornecedor, valor_total=soma,
            status="paga" if pago else "fechada", origem="lote", fechada_em=datetime.utcnow(),
            paga_em=dados.pagamento.data_pagamento if pago else None, usuario_id=usuario_id_seguro(user),
        )
        session.add(fatura)
        session.flush()
        for conta in session.exec(select(ContaGerencial).where(ContaGerencial.id.in_(todas_contas))).all():
            conta.fatura_id = fatura.id
            session.add(conta)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {
        "fatura_id": fatura.id, "rotulo": fatura.rotulo, "status": fatura.status, "valor_total": soma,
        "notas": criadas, "ids_contas": todas_contas,
    }


def _resumo(session: Session, f: FaturaFornecedor) -> dict:
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.fatura_id == f.id)).all()
    notas = {c.numero_lancamento for c in contas if c.numero_lancamento}
    return {
        "id": f.id, "fornecedor": f.fornecedor, "rotulo": f.rotulo, "status": f.status, "origem": f.origem,
        "data_abertura": f.data_abertura, "data_fechamento_prevista": f.data_fechamento_prevista,
        "data_vencimento": f.data_vencimento, "parcelas_n": f.parcelas_n, "total_fornecedor": f.total_fornecedor,
        "valor_total": f.valor_total if f.valor_total is not None else round(sum(c.valor_total or 0 for c in contas), 2),
        "notas": len(notas), "paga_em": f.paga_em,
    }


@router.get("")
def listar_faturas(
    status: str | None = None, fornecedor: str | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    consulta = select(FaturaFornecedor).where(FaturaFornecedor.fazenda_id == fazenda_id)
    if status:
        consulta = consulta.where(FaturaFornecedor.status == status)
    if fornecedor:
        consulta = consulta.where(FaturaFornecedor.fornecedor == fornecedor)
    return [_resumo(session, f) for f in session.exec(consulta.order_by(FaturaFornecedor.id.desc())).all()]


@router.get("/{fatura_id}")
def detalhe_fatura(
    fatura_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    f = session.exec(select(FaturaFornecedor).where(
        FaturaFornecedor.id == fatura_id, FaturaFornecedor.fazenda_id == fazenda_id)).first()
    if f is None:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    contas = session.exec(select(ContaGerencial).where(
        ContaGerencial.fatura_id == f.id, ContaGerencial.fazenda_id == fazenda_id
    ).order_by(ContaGerencial.numero_lancamento, ContaGerencial.parcela_num)).all()
    notas: dict[str, dict] = {}
    for c in contas:
        n = notas.setdefault(c.numero_lancamento or str(c.id), {
            "numero_lancamento": c.numero_lancamento, "tipo_documento": c.tipo_documento,
            "numero_documento": c.numero_nota, "data_emissao": c.data_emissao, "valor": 0.0, "parcelas": [],
        })
        n["valor"] = round(n["valor"] + (c.valor_total or 0), 2)
        n["parcelas"].append({"parcela": c.parcela_num, "vencimento": c.data_vencimento, "valor": c.valor_total, "pago": c.data_pagamento is not None})
    return {**_resumo(session, f), "lista_notas": list(notas.values())}
