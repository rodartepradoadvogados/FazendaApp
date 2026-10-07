"""
Faturas de fornecedor — Entrega 1 (Lançamento em lote) e Entrega 2 (modo Faturas).

Fatura: reúne notas de UM fornecedor e é ela que se vence, se parcela e se paga. Situação:
aberta (vai recebendo notas) → fechada (total congelado, com ou sem parcelamento) → paga (todas as
parcelas baixadas). Reabrir volta a "aberta" enquanto nenhuma parcela foi paga.

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
from fazenda.models import ContaGerencial, FaturaFornecedor, FaturaFornecedorEvento, Usuario
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
    if dados.modo not in ("venc", "parc", "pago"):
        raise HTTPException(status_code=400, detail="Modo de pagamento inválido.")
    _validar_notas(dados.notas)
    if dados.modo == "venc" and not dados.data_vencimento:
        raise HTTPException(status_code=400, detail="Informe o vencimento do lote.")
    if dados.modo == "parc":
        _validar_cronograma_cadastro(dados.parcelamento)
        if dados.parcelamento is None:
            raise HTTPException(status_code=400, detail=f"Parcelamento: informe de 2 a {MAX_PARCELAS} parcelas.")
    if dados.modo == "pago":
        p = dados.pagamento
        if not p:
            raise HTTPException(status_code=400, detail="Informe a data e a forma do pagamento.")
        if p.forma_pagamento not in FORMAS_PAGAMENTO:
            raise HTTPException(status_code=400, detail="Forma de pagamento inválida.")


# ---------------------------------------------------------------------------
# Núcleo compartilhado: validar notas, gravar notas (tudo ou nada), cronograma da fatura
# ---------------------------------------------------------------------------
def _validar_notas(notas: list[NotaLoteIn]) -> None:
    if not notas:
        raise HTTPException(status_code=400, detail="Acrescente ao menos uma nota.")
    vistos: dict[tuple[str, str], int] = {}
    for i, nota in enumerate(notas, start=1):
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


def _duplicadas_notas(session: Session, fornecedor: str, notas: list[NotaLoteIn], fazenda_id: int) -> list[dict]:
    """Notas que já existem no Financeiro: mesmo fornecedor + tipo + número (exato).
    Nota sem número não entra: não há o que comparar com exatidão."""
    achados: list[dict] = []
    for i, nota in enumerate(notas, start=1):
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
            if (c.fornecedor_cliente or "").strip().lower() != fornecedor.strip().lower():
                continue
            if (c.tipo_documento or "").strip().lower() != nota.tipo_documento.strip().lower():
                continue
            achados.append({
                "nota": i, "numero_documento": numero, "numero_lancamento": c.numero_lancamento,
                "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None, "valor_total": c.valor_total,
            })
            break
    return achados


def _exigir_confirmacao_duplicadas(session: Session, fornecedor: str, notas: list[NotaLoteIn], fazenda_id: int, confirmou: bool) -> None:
    existentes = _duplicadas_notas(session, fornecedor, notas, fazenda_id)
    if existentes and not confirmou:
        raise HTTPException(status_code=409, detail={
            "codigo": "duplicadas",
            "mensagem": "Algumas notas parecem já lançadas (mesmo fornecedor, tipo e número).",
            "duplicadas": existentes,
        })


def _gravar_notas(
    session: Session, user: Usuario, fazenda_id: int, *, fornecedor: str, centro_custo: str | None,
    conta_bancaria: str | None, notas: list[NotaLoteIn], modo: str, data_vencimento: date | None = None,
    vencimentos: list[date] | None = None, pagamento: PagamentoLoteIn | None = None,
) -> tuple[list[dict], list[int]]:
    """Grava as notas pela MESMA função do Lançamento normal, sem comitar (quem chama comita ou
    desfaz tudo). `modo`: venc (um vencimento), parc (N parcelas em `vencimentos`) ou pago."""
    responsavel = (getattr(user, "nome", None) or getattr(user, "username", None) or "").strip() or None
    sessao = _SessaoSemCommit(session)
    criadas: list[dict] = []
    ids: list[int] = []
    for i, nota in enumerate(notas, start=1):
        liquido = _liquido(nota)
        kwargs: dict = {}
        if modo == "venc":
            kwargs["data_vencimento"] = data_vencimento
        elif modo == "parc":
            kwargs["parcelas"] = [ParcelaIn(data_vencimento=v, valor=valor) for v, valor in zip(vencimentos or [], _dividir(liquido, len(vencimentos or [])))]
        else:
            kwargs.update(
                data_vencimento=pagamento.data_pagamento, data_pagamento=pagamento.data_pagamento, valor_pago=liquido,
                conta_bancaria=pagamento.conta_bancaria or conta_bancaria, forma_pagamento=pagamento.forma_pagamento,
                numero_documento_pagamento=pagamento.numero_documento_pagamento,
            )
        lancamento = LancamentoIn(
            tipo="despesa", itens=nota.itens, centro_custo=centro_custo, fornecedor_cliente=fornecedor.strip(),
            responsavel=responsavel, tipo_documento=nota.tipo_documento.strip(),
            numero_documento=(nota.numero_documento or "").strip() or None, data_emissao=nota.data_emissao,
            desconto=nota.desconto or 0, acrescimo=nota.acrescimo or 0, **kwargs,
        )
        try:
            r = criar_lancamento(lancamento, sessao, user, fazenda_id)
        except HTTPException as exc:
            detalhe = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            rotulo_nota = (nota.numero_documento or "sem número").strip() or "sem número"
            raise HTTPException(status_code=exc.status_code, detail=f"Nota {i} ({rotulo_nota}): {detalhe}") from None
        ids += r["ids"]
        criadas.append({
            "nota": i, "numero_lancamento": r["numero_lancamento"], "valor_liquido": r["valor_liquido"],
            "ids": r["ids"], "avisos_estoque": r.get("avisos_estoque", []),
        })
    return criadas, ids


def _evento(session: Session, f: FaturaFornecedor, user: Usuario, acao: str, detalhe: str | None = None) -> None:
    session.add(FaturaFornecedorEvento(
        fazenda_id=f.fazenda_id, fatura_id=f.id, acao=acao, detalhe=detalhe, usuario_id=usuario_id_seguro(user),
    ))


def _fatura_ou_404(session: Session, fatura_id: int, fazenda_id: int | None) -> FaturaFornecedor:
    f = session.exec(select(FaturaFornecedor).where(
        FaturaFornecedor.id == fatura_id, FaturaFornecedor.fazenda_id == fazenda_id)).first()
    if f is None:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    return f


def _contas_da_fatura(session: Session, f: FaturaFornecedor) -> list[ContaGerencial]:
    return list(session.exec(select(ContaGerencial).where(
        ContaGerencial.fatura_id == f.id, ContaGerencial.fazenda_id == f.fazenda_id
    ).order_by(ContaGerencial.numero_lancamento, ContaGerencial.parcela_num, ContaGerencial.id)).all())


def _agrupar(contas: list[ContaGerencial]) -> dict[str, list[ContaGerencial]]:
    grupos: dict[str, list[ContaGerencial]] = {}
    for c in contas:
        grupos.setdefault(c.numero_lancamento or f"id-{c.id}", []).append(c)
    return grupos


def _cronograma(f: FaturaFornecedor) -> list[date | None]:
    """Os vencimentos de CADA parcela da fatura (1 = à vista)."""
    if f.parcelas_n and f.parcelas_n >= 2 and f.parcelas_primeiro:
        return list(_vencimentos(ParcelamentoLoteIn(n=f.parcelas_n, primeiro_vencimento=f.parcelas_primeiro, intervalo=f.parcelas_intervalo or "mensal")))
    return [f.data_vencimento]


def _aplicar_cronograma(session: Session, linhas: list[ContaGerencial], vencs: list[date | None]) -> list[ContaGerencial]:
    """Refaz as parcelas de UMA nota (todas em aberto) para `len(vencs)` partes iguais, centavos na
    última, reaproveitando as linhas existentes e criando/removendo o que faltar ou sobrar."""
    if any(c.data_pagamento is not None for c in linhas):
        raise HTTPException(status_code=409, detail="A nota %s já tem parcela paga e não pode ter o vencimento refeito." % (linhas[0].numero_nota or linhas[0].numero_lancamento))
    linhas = sorted(linhas, key=lambda c: (c.parcela_num or 0, c.id or 0))
    total = round(sum(c.valor_total or 0 for c in linhas), 2)
    n = len(vencs)
    partes = _dividir(total, n) if n > 1 else [total]
    vivas: list[ContaGerencial] = []
    for k in range(n):
        if k < len(linhas):
            c = linhas[k]
        else:
            base = {k2: v for k2, v in linhas[0].model_dump().items() if k2 != "id"}
            c = ContaGerencial(**base)
        c.parcela_num, c.parcela_total, c.valor_total, c.data_vencimento = k + 1, n, partes[k], vencs[k]
        c.atualizado_em = datetime.utcnow()
        session.add(c)
        vivas.append(c)
    for extra in linhas[n:]:
        session.delete(extra)
    # Devolve só as linhas que continuam existindo: re-adicionar à sessão uma linha apagada a "ressuscita".
    return vivas


def _reaplicar_cronograma_da_fatura(session: Session, f: FaturaFornecedor) -> None:
    vencs = _cronograma(f)
    for linhas in _agrupar(_contas_da_fatura(session, f)).values():
        _aplicar_cronograma(session, linhas, vencs)


def _validar_cronograma_cadastro(par: ParcelamentoLoteIn | None) -> None:
    if par is None:
        return
    if not 2 <= par.n <= MAX_PARCELAS:
        raise HTTPException(status_code=400, detail=f"Parcelamento: informe de 2 a {MAX_PARCELAS} parcelas.")
    if par.intervalo not in ("mensal", "30dias"):
        raise HTTPException(status_code=400, detail="Intervalo de parcelas inválido.")


# ---------------------------------------------------------------------------
# Entrega 1 — Lançamento em lote (a fatura já nasce fechada ou paga)
# ---------------------------------------------------------------------------
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
    _exigir_confirmacao_duplicadas(session, dados.fornecedor, dados.notas, fazenda_id, dados.confirmar_duplicados)

    vencs = _vencimentos(dados.parcelamento) if dados.modo == "parc" else []
    try:
        criadas, todas_contas = _gravar_notas(
            session, user, fazenda_id, fornecedor=dados.fornecedor, centro_custo=dados.centro_custo,
            conta_bancaria=dados.conta_bancaria, notas=dados.notas, modo=dados.modo,
            data_vencimento=dados.data_vencimento, vencimentos=vencs, pagamento=dados.pagamento,
        )
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
            parcelas_primeiro=dados.parcelamento.primeiro_vencimento if dados.modo == "parc" else None,
            parcelas_intervalo=dados.parcelamento.intervalo if dados.modo == "parc" else None,
            parcelamento_origem="lote" if dados.modo == "parc" else None,
            total_fornecedor=dados.total_fornecedor, valor_total=soma,
            status="paga" if pago else "fechada", origem="lote", fechada_em=datetime.utcnow(),
            paga_em=dados.pagamento.data_pagamento if pago else None, usuario_id=usuario_id_seguro(user),
        )
        session.add(fatura)
        session.flush()
        for conta in session.exec(select(ContaGerencial).where(ContaGerencial.id.in_(todas_contas))).all():
            conta.fatura_id = fatura.id
            session.add(conta)
        _evento(session, fatura, user, "lote_lancado", f"{len(criadas)} nota(s), R$ {soma:.2f}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {
        "fatura_id": fatura.id, "rotulo": fatura.rotulo, "status": fatura.status, "valor_total": soma,
        "notas": criadas, "ids_contas": todas_contas,
    }


# ---------------------------------------------------------------------------
# Entrega 2 — modo Faturas
# ---------------------------------------------------------------------------
class FaturaIn(BaseModel):
    fornecedor: str
    rotulo: str | None = None
    data_abertura: date
    data_fechamento_prevista: date | None = None
    data_vencimento: date | None = None
    conta_bancaria: str | None = None
    centro_custo: str | None = None
    parcelamento: ParcelamentoLoteIn | None = None  # em branco = decide no fechamento


def _aplicar_cadastro(f: FaturaFornecedor, d: FaturaIn) -> None:
    if not (d.fornecedor or "").strip():
        raise HTTPException(status_code=400, detail="Escolha o fornecedor da fatura.")
    if d.data_fechamento_prevista and d.data_fechamento_prevista < d.data_abertura:
        raise HTTPException(status_code=400, detail="O fechamento previsto não pode ser antes da abertura.")
    _validar_cronograma_cadastro(d.parcelamento)
    venc = d.parcelamento.primeiro_vencimento if d.parcelamento else d.data_vencimento
    if venc is None:
        raise HTTPException(status_code=400, detail="Informe o vencimento da fatura.")
    f.fornecedor = d.fornecedor.strip()
    f.rotulo = (d.rotulo or "").strip() or f"{f.fornecedor} — {d.data_abertura.month:02d}/{d.data_abertura.year}"
    f.data_abertura, f.data_fechamento_prevista, f.data_vencimento = d.data_abertura, d.data_fechamento_prevista, venc
    f.conta_bancaria, f.centro_custo = d.conta_bancaria or None, d.centro_custo or None
    if d.parcelamento:
        f.parcelas_n, f.parcelas_primeiro, f.parcelas_intervalo = d.parcelamento.n, d.parcelamento.primeiro_vencimento, d.parcelamento.intervalo
        f.parcelamento_origem = "cadastro"
    elif f.parcelamento_origem == "cadastro":
        f.parcelas_n = f.parcelas_primeiro = f.parcelas_intervalo = f.parcelamento_origem = None
    f.atualizado_em = datetime.utcnow()


@router.post("", status_code=201)
def abrir_fatura(
    dados: FaturaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    f = FaturaFornecedor(fazenda_id=fazenda_id, fornecedor="", rotulo="", data_abertura=dados.data_abertura,
                         status="aberta", origem="fatura", usuario_id=usuario_id_seguro(user))
    _aplicar_cadastro(f, dados)
    session.add(f)
    session.flush()
    _evento(session, f, user, "aberta", f.rotulo)
    session.commit()
    return _detalhe(session, f)


@router.put("/{fatura_id}")
def editar_fatura(
    fatura_id: int, dados: FaturaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    if f.status != "aberta":
        raise HTTPException(status_code=409, detail="Só fatura aberta pode ter o cadastro editado. Reabra a fatura antes.")
    if dados.fornecedor.strip().lower() != f.fornecedor.lower() and _contas_da_fatura(session, f):
        raise HTTPException(status_code=409, detail="A fatura já tem notas: não dá para trocar o fornecedor.")
    try:
        _aplicar_cadastro(f, dados)
        _reaplicar_cronograma_da_fatura(session, f)
        _evento(session, f, user, "editada", f.rotulo)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _detalhe(session, f)


class NotasNaFaturaIn(BaseModel):
    notas: list[NotaLoteIn]
    confirmar_duplicados: bool = False
    confirmar_fora_periodo: bool = False


def _fora_do_periodo(f: FaturaFornecedor, notas: list[NotaLoteIn]) -> list[dict]:
    fora = []
    for i, n in enumerate(notas, start=1):
        if n.data_emissao < f.data_abertura:
            fora.append({"nota": i, "data_emissao": n.data_emissao.isoformat(), "motivo": "anterior à abertura da fatura"})
        elif f.data_fechamento_prevista and n.data_emissao > f.data_fechamento_prevista:
            fora.append({"nota": i, "data_emissao": n.data_emissao.isoformat(), "motivo": "posterior ao fechamento previsto da fatura"})
    return fora


@router.post("/{fatura_id}/notas", status_code=201)
def lancar_notas_na_fatura(
    fatura_id: int, dados: NotasNaFaturaIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Lança uma ou mais notas DENTRO de uma fatura aberta (tudo ou nada). A nota nasce com o
    cronograma da fatura (vencimento previsto ou as N parcelas definidas no cadastro)."""
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    if f.status != "aberta":
        raise HTTPException(status_code=409, detail="A fatura não está aberta. Reabra-a para lançar mais notas.")
    _validar_notas(dados.notas)
    fora = _fora_do_periodo(f, dados.notas)
    if fora and not dados.confirmar_fora_periodo:
        raise HTTPException(status_code=409, detail={
            "codigo": "fora_do_periodo",
            "mensagem": "Há nota fora do período desta fatura.", "fora": fora,
            "abertura": f.data_abertura.isoformat(),
            "fechamento_previsto": f.data_fechamento_prevista.isoformat() if f.data_fechamento_prevista else None,
        })
    _exigir_confirmacao_duplicadas(session, f.fornecedor, dados.notas, fazenda_id, dados.confirmar_duplicados)
    vencs = _cronograma(f)
    try:
        criadas, ids = _gravar_notas(
            session, user, fazenda_id, fornecedor=f.fornecedor, centro_custo=f.centro_custo, conta_bancaria=f.conta_bancaria,
            notas=dados.notas, modo="parc" if len(vencs) > 1 else "venc", data_vencimento=vencs[0], vencimentos=vencs,
        )
        for conta in session.exec(select(ContaGerencial).where(ContaGerencial.id.in_(ids))).all():
            conta.fatura_id = f.id
            session.add(conta)
        soma = round(sum(c["valor_liquido"] for c in criadas), 2)
        _evento(session, f, user, "notas_lancadas", f"{len(criadas)} nota(s), R$ {soma:.2f}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"fatura_id": f.id, "notas": criadas, "ids_contas": ids, "valor": soma}


class NotasAvulsasIn(BaseModel):
    fornecedor: str
    conta_bancaria: str | None = None
    centro_custo: str | None = None
    notas: list[NotaLoteIn]
    data_vencimento: date
    confirmar_duplicados: bool = False


@router.post("/notas-avulsas", status_code=201)
def lancar_notas_avulsas(
    dados: NotasAvulsasIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Notas SEM fatura (a opção "lançar sem fatura" do aviso de nota fora do período): tudo ou nada."""
    if not (dados.fornecedor or "").strip():
        raise HTTPException(status_code=400, detail="Escolha o fornecedor.")
    _validar_notas(dados.notas)
    _exigir_confirmacao_duplicadas(session, dados.fornecedor, dados.notas, fazenda_id, dados.confirmar_duplicados)
    try:
        criadas, ids = _gravar_notas(
            session, user, fazenda_id, fornecedor=dados.fornecedor, centro_custo=dados.centro_custo,
            conta_bancaria=dados.conta_bancaria, notas=dados.notas, modo="venc", data_vencimento=dados.data_vencimento,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"notas": criadas, "ids_contas": ids}


class FecharIn(BaseModel):
    total_fornecedor: float | None = None
    confirmar_divergencia: bool = False
    modo: str = "vista"  # vista | parcelar (ignorado se o parcelamento veio do cadastro)
    parcelamento: ParcelamentoLoteIn | None = None
    data_vencimento: date | None = None  # ajuste do vencimento à vista no fechamento


@router.post("/{fatura_id}/fechar")
def fechar_fatura(
    fatura_id: int, dados: FecharIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    if f.status != "aberta":
        raise HTTPException(status_code=409, detail="Só fatura aberta pode ser fechada.")
    contas = _contas_da_fatura(session, f)
    if not contas:
        raise HTTPException(status_code=409, detail="A fatura não tem notas. Lance ao menos uma antes de fechar.")
    soma = round(sum(c.valor_total or 0 for c in contas), 2)
    if dados.total_fornecedor is not None and abs(round(dados.total_fornecedor - soma, 2)) > 0.005 and not dados.confirmar_divergencia:
        raise HTTPException(status_code=409, detail={
            "codigo": "divergencia_total",
            "mensagem": f"O total das notas (R$ {soma:.2f}) difere do total informado pelo fornecedor (R$ {dados.total_fornecedor:.2f}).",
            "soma_notas": soma, "total_fornecedor": dados.total_fornecedor,
        })
    try:
        if f.parcelamento_origem != "cadastro":
            if dados.modo == "parcelar":
                if dados.parcelamento is None:
                    raise HTTPException(status_code=400, detail="Informe as parcelas, o primeiro vencimento e o intervalo.")
                _validar_cronograma_cadastro(dados.parcelamento)
                f.parcelas_n, f.parcelas_primeiro, f.parcelas_intervalo = dados.parcelamento.n, dados.parcelamento.primeiro_vencimento, dados.parcelamento.intervalo
                f.parcelamento_origem = "fechamento"
                f.data_vencimento = dados.parcelamento.primeiro_vencimento
            else:
                f.parcelas_n = f.parcelas_primeiro = f.parcelas_intervalo = f.parcelamento_origem = None
                if dados.data_vencimento:
                    f.data_vencimento = dados.data_vencimento
        _reaplicar_cronograma_da_fatura(session, f)
        f.status, f.valor_total, f.fechada_em = "fechada", soma, datetime.utcnow()
        if dados.total_fornecedor is not None:
            f.total_fornecedor = dados.total_fornecedor
        f.atualizado_em = datetime.utcnow()
        session.add(f)
        _evento(session, f, user, "fechada", f"R$ {soma:.2f}" + (f" em {f.parcelas_n}x" if f.parcelas_n else " à vista"))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _detalhe(session, f)


class ReabrirIn(BaseModel):
    motivo: str


@router.post("/{fatura_id}/reabrir")
def reabrir_fatura(
    fatura_id: int, dados: ReabrirIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo da reabertura.")
    if f.status != "fechada":
        raise HTTPException(
            status_code=409,
            detail="Fatura paga não se reabre: estorne o pagamento antes." if f.status == "paga" else "Só fatura fechada pode ser reaberta.",
        )
    contas = _contas_da_fatura(session, f)
    if any(c.data_pagamento is not None for c in contas):
        raise HTTPException(status_code=409, detail="Há parcela paga. Estorne o pagamento antes de reabrir.")
    try:
        if f.parcelamento_origem in ("fechamento", "lote"):
            f.parcelas_n = f.parcelas_primeiro = f.parcelas_intervalo = f.parcelamento_origem = None
        _reaplicar_cronograma_da_fatura(session, f)
        f.status, f.valor_total, f.fechada_em = "aberta", None, None
        f.atualizado_em = datetime.utcnow()
        session.add(f)
        _evento(session, f, user, "reaberta", motivo)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _detalhe(session, f)


class PagarParcelaIn(BaseModel):
    parcela: int = 1
    data_pagamento: date
    forma_pagamento: str
    conta_bancaria: str | None = None
    numero_documento_pagamento: str | None = None
    valor_pago: float | None = None
    data_vencimento_cartao: date | None = None


@router.post("/{fatura_id}/pagar")
def pagar_parcela(
    fatura_id: int, dados: PagarParcelaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Paga UMA parcela da fatura: baixa a parcela de todas as notas de uma vez, mesma data, conta,
    forma e comprovante. Valor pago diferente da soma: a diferença é rateada proporcionalmente nas
    notas (desconto/acréscimo de cada uma)."""
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    if f.status == "aberta":
        raise HTTPException(status_code=409, detail="Feche a fatura antes de pagar.")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida.")
    if dados.forma_pagamento == "credito" and not dados.data_vencimento_cartao:
        raise HTTPException(status_code=400, detail="Informe a data de vencimento do cartão.")
    alvo = [c for c in _contas_da_fatura(session, f) if (c.parcela_num or 1) == dados.parcela]
    if not alvo:
        raise HTTPException(status_code=404, detail=f"A fatura não tem a parcela {dados.parcela}.")
    if any(c.data_pagamento is not None for c in alvo):
        raise HTTPException(status_code=409, detail=f"A parcela {dados.parcela} já está paga.")
    soma = round(sum(c.valor_total or 0 for c in alvo), 2)
    pago = round(dados.valor_pago if dados.valor_pago is not None else soma, 2)
    if pago <= 0:
        raise HTTPException(status_code=400, detail="O valor pago deve ser maior que zero.")
    # Rateio da diferença em centavos, proporcional ao valor de cada nota (sobra na última).
    dif_c = round((pago - soma) * 100)
    cents = [round((c.valor_total or 0) * 100) for c in alvo]
    cotas = [dif_c * v // sum(cents) if dif_c >= 0 else -((-dif_c) * v // sum(cents)) for v in cents]
    cotas[-1] += dif_c - sum(cotas)
    try:
        for c, cota in zip(alvo, cotas):
            c.data_pagamento = dados.data_pagamento
            c.valor_pago = round((c.valor_total or 0) + cota / 100, 2)
            c.desconto_acrescimo = round(cota / 100, 2)
            c.conta_bancaria = dados.conta_bancaria or f.conta_bancaria
            c.forma_pagamento = dados.forma_pagamento
            c.numero_documento_pagamento = dados.numero_documento_pagamento
            c.data_vencimento_cartao = dados.data_vencimento_cartao if dados.forma_pagamento == "credito" else None
            c.atualizado_em = datetime.utcnow()
            session.add(c)
        session.flush()
        todas = _contas_da_fatura(session, f)
        if all(c.data_pagamento is not None for c in todas):
            f.status, f.paga_em = "paga", dados.data_pagamento
        f.atualizado_em = datetime.utcnow()
        session.add(f)
        _evento(session, f, user, "parcela_paga", f"parcela {dados.parcela}: R$ {pago:.2f}" + (f" (previsto R$ {soma:.2f})" if pago != soma else ""))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {**_detalhe(session, f), "ids_contas_pagas": [c.id for c in alvo], "diferenca": round(dif_c / 100, 2)}


class EstornarParcelaIn(BaseModel):
    motivo: str


@router.post("/{fatura_id}/parcelas/{parcela}/estornar")
def estornar_parcela(
    fatura_id: int, parcela: int, dados: EstornarParcelaIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo do estorno.")
    alvo = [c for c in _contas_da_fatura(session, f) if (c.parcela_num or 1) == parcela]
    if not alvo or any(c.data_pagamento is None for c in alvo):
        raise HTTPException(status_code=409, detail=f"A parcela {parcela} não está paga.")
    try:
        for c in alvo:
            c.data_pagamento = c.valor_pago = c.conta_bancaria = c.numero_documento_pagamento = None
            c.forma_pagamento = c.data_vencimento_cartao = c.desconto_acrescimo = None
            c.atualizado_em = datetime.utcnow()
            session.add(c)
        if f.status == "paga":
            f.status, f.paga_em = "fechada", None
        f.atualizado_em = datetime.utcnow()
        session.add(f)
        _evento(session, f, user, "pagamento_estornado", f"parcela {parcela}: {motivo}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _detalhe(session, f)


class InserirNotasIn(BaseModel):
    numeros_lancamento: list[str]


def _notas_para_inserir(session: Session, f: FaturaFornecedor, numeros: list[str]) -> dict[str, list[ContaGerencial]]:
    if not numeros:
        raise HTTPException(status_code=400, detail="Escolha ao menos uma nota.")
    saida: dict[str, list[ContaGerencial]] = {}
    for numero in dict.fromkeys(numeros):
        linhas = list(session.exec(select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == numero, ContaGerencial.fazenda_id == f.fazenda_id)).all())
        if not linhas:
            raise HTTPException(status_code=404, detail=f"Nota {numero} não encontrada.")
        c0 = linhas[0]
        if c0.tipo != "despesa":
            raise HTTPException(status_code=409, detail=f"A nota {numero} não é uma despesa.")
        if (c0.fornecedor_cliente or "").strip().lower() != f.fornecedor.lower():
            raise HTTPException(status_code=409, detail=f"A nota {numero} é de outro fornecedor ({c0.fornecedor_cliente}).")
        if any(c.fatura_id for c in linhas):
            raise HTTPException(status_code=409, detail=f"A nota {numero} já pertence a uma fatura. Tire-a de lá antes.")
        if any(c.data_pagamento is not None for c in linhas):
            raise HTTPException(status_code=409, detail=f"A nota {numero} já tem parcela paga e não entra em fatura.")
        saida[numero] = linhas
    return saida


@router.post("/{fatura_id}/notas/inserir/previa")
def previa_inserir_notas(
    fatura_id: int, dados: InserirNotasIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    if f.status != "aberta":
        raise HTTPException(status_code=409, detail="Só fatura aberta recebe notas.")
    grupos = _notas_para_inserir(session, f, dados.numeros_lancamento)
    vencs = _cronograma(f)
    return {"fatura": f.rotulo, "vencimentos_da_fatura": vencs, "notas": [{
        "numero_lancamento": n, "numero_documento": ls[0].numero_nota, "valor": round(sum(c.valor_total or 0 for c in ls), 2),
        "parcelas_atuais": [{"parcela": c.parcela_num, "vencimento": c.data_vencimento, "valor": c.valor_total} for c in sorted(ls, key=lambda c: c.parcela_num or 0)],
    } for n, ls in grupos.items()]}


@router.post("/{fatura_id}/notas/inserir")
def inserir_notas(
    fatura_id: int, dados: InserirNotasIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Insere notas JÁ lançadas (em aberto, do mesmo fornecedor) numa fatura aberta: o vencimento e
    as parcelas próprios da nota são substituídos pelo cronograma da fatura."""
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    if f.status != "aberta":
        raise HTTPException(status_code=409, detail="Só fatura aberta recebe notas.")
    try:
        grupos = _notas_para_inserir(session, f, dados.numeros_lancamento)
        vencs = _cronograma(f)
        for linhas in grupos.values():
            for c in _aplicar_cronograma(session, linhas, vencs):
                c.fatura_id = f.id
                session.add(c)
        _evento(session, f, user, "notas_inseridas", ", ".join(grupos))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _detalhe(session, f)


@router.post("/{fatura_id}/notas/{numero_lancamento}/tirar")
def tirar_nota(
    fatura_id: int, numero_lancamento: str, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Tira uma nota da fatura aberta: volta a ser avulsa, com vencimento único igual ao da fatura."""
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    if f.status != "aberta":
        raise HTTPException(status_code=409, detail="Só dá para tirar nota de fatura aberta. Reabra a fatura antes.")
    linhas = [c for c in _contas_da_fatura(session, f) if c.numero_lancamento == numero_lancamento]
    if not linhas:
        raise HTTPException(status_code=404, detail="Nota não encontrada nesta fatura.")
    try:
        for c in _aplicar_cronograma(session, linhas, [f.data_vencimento]):
            c.fatura_id = None
            session.add(c)
        _evento(session, f, user, "nota_retirada", numero_lancamento)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _detalhe(session, f)


@router.delete("/{fatura_id}")
def excluir_fatura(
    fatura_id: int, soltar_notas: bool = False, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Exclui a fatura se estiver vazia. Fatura aberta com notas só com `soltar_notas=true`: as notas
    ficam avulsas, com vencimento único igual ao da fatura."""
    f = _fatura_ou_404(session, fatura_id, fazenda_id)
    contas = _contas_da_fatura(session, f)
    if f.status == "paga" or any(c.data_pagamento is not None for c in contas):
        raise HTTPException(status_code=409, detail="Fatura com pagamento não se exclui. Estorne os pagamentos primeiro.")
    if contas and not soltar_notas:
        raise HTTPException(status_code=409, detail="A fatura tem notas. Esvazie-a ou exclua soltando as notas (elas ficam avulsas).")
    if contas and f.status != "aberta":
        raise HTTPException(status_code=409, detail="Reabra a fatura antes de soltar as notas.")
    try:
        for linhas in _agrupar(contas).values():
            for c in _aplicar_cronograma(session, linhas, [f.data_vencimento]):
                c.fatura_id = None
                session.add(c)
        for e in session.exec(select(FaturaFornecedorEvento).where(FaturaFornecedorEvento.fatura_id == f.id)).all():
            session.delete(e)
        session.delete(f)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"excluida": True, "notas_soltas": len(_agrupar(contas))}


def _resumo(session: Session, f: FaturaFornecedor, contas: list[ContaGerencial] | None = None) -> dict:
    contas = contas if contas is not None else _contas_da_fatura(session, f)
    notas = {c.numero_lancamento or f"id-{c.id}" for c in contas}
    return {
        "id": f.id, "fornecedor": f.fornecedor, "rotulo": f.rotulo, "status": f.status, "origem": f.origem,
        "data_abertura": f.data_abertura, "data_fechamento_prevista": f.data_fechamento_prevista,
        "data_vencimento": f.data_vencimento, "parcelas_n": f.parcelas_n, "parcelas_primeiro": f.parcelas_primeiro,
        "parcelas_intervalo": f.parcelas_intervalo, "parcelamento_origem": f.parcelamento_origem,
        "conta_bancaria": f.conta_bancaria, "centro_custo": f.centro_custo, "total_fornecedor": f.total_fornecedor,
        "valor_total": f.valor_total if f.valor_total is not None else round(sum(c.valor_total or 0 for c in contas), 2),
        "notas": len(notas), "paga_em": f.paga_em,
    }


def _detalhe(session: Session, f: FaturaFornecedor) -> dict:
    contas = _contas_da_fatura(session, f)
    notas: dict[str, dict] = {}
    for chave, linhas in _agrupar(contas).items():
        c0 = linhas[0]
        notas[chave] = {
            "numero_lancamento": c0.numero_lancamento, "tipo_documento": c0.tipo_documento, "numero_documento": c0.numero_nota,
            "data_emissao": c0.data_emissao, "descricao": c0.descricao, "valor": round(sum(c.valor_total or 0 for c in linhas), 2),
            "desconto": c0.desconto_nota, "acrescimo": c0.acrescimo_nota,
            "parcelas": [{"parcela": c.parcela_num, "vencimento": c.data_vencimento, "valor": c.valor_total, "pago": c.data_pagamento is not None} for c in linhas],
        }
    por_parcela: dict[int, dict] = {}
    for c in contas:
        k = c.parcela_num or 1
        x = por_parcela.setdefault(k, {"parcela": k, "vencimento": c.data_vencimento, "valor": 0.0, "pago": True, "valor_pago": 0.0, "data_pagamento": None, "forma_pagamento": None})
        x["valor"] = round(x["valor"] + (c.valor_total or 0), 2)
        if c.data_pagamento is None:
            x["pago"] = False
        else:
            x["valor_pago"] = round(x["valor_pago"] + (c.valor_pago or 0), 2)
            x["data_pagamento"], x["forma_pagamento"] = c.data_pagamento, c.forma_pagamento
    eventos = session.exec(select(FaturaFornecedorEvento).where(
        FaturaFornecedorEvento.fatura_id == f.id).order_by(FaturaFornecedorEvento.id.desc())).all()
    nomes = {}
    for e in eventos:
        if e.usuario_id and e.usuario_id not in nomes:
            u = session.get(Usuario, e.usuario_id)
            nomes[e.usuario_id] = (getattr(u, "nome", None) or getattr(u, "username", None)) if u else None
    return {
        **_resumo(session, f, contas), "lista_notas": list(notas.values()),
        "parcelas": [por_parcela[k] for k in sorted(por_parcela)],
        "eventos": [{"acao": e.acao, "detalhe": e.detalhe, "em": e.criado_em, "usuario": nomes.get(e.usuario_id)} for e in eventos],
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
    return _detalhe(session, _fatura_ou_404(session, fatura_id, fazenda_id_seguro(fazenda_id)))
