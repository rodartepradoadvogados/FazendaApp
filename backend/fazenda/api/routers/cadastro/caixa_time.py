"""
Caixa do time (participação nos lucros) e rateio — Fase 3 do Caixa dos funcionários.

- O caixa do time é dinheiro do COLETIVO (PL). A entrada da fazenda vira despesa de
  pessoal baixada no Financeiro (como no caixa individual).
- O rateio reparte o saldo em partes proporcionais aos dias de cada membro no
  período; a penalidade (art. 482 CLT) retira % da parte da pessoa e reparte entre
  os demais — e só confirma com o DOCUMENTO de ciência anexado.
- Confirmar: cada parte vira crédito no caixa individual (ou pagamento direto =
  crédito + retirada imediata com recibo). O crédito NÃO gera despesa nova: o gasto
  foi reconhecido quando o dinheiro entrou no caixa do time.
- Desfazer: só enquanto nenhuma parte foi sacada, e só se não houve pagamento direto.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    CaixaMovimento, CaixaRateio, CaixaRateioLinha, CaixaTime, CaixaTimeMembro, CaixaTimeMovimento,
    ContaGerencial, Pessoa, PessoaAnexo,
)
from fazenda.rules import caixa_funcionario as regras_caixa
from fazenda.rules import caixa_time as regras
from fazenda.rules import parametros
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro

router = APIRouter(prefix="/caixa-time", tags=["Caixa do time"])

TIPOS_ENTRADA = {
    "deposito": "Depósito da fazenda", "bonificacao": "Bonificação por produtividade",
    "comissao": "Comissão", "outro": "Outro tipo",
}
GRUPOS = {"clt", "empreita", "contrato", "diaria"}
FORMAS = ["pix", "dinheiro", "transferencia", "debito", "credito", "boleto"]
TIPO_DOC_ENTRADA = "Caixa do time"
TIPO_DOC_ESTORNO = "Estorno caixa do time"


def _brl(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _time_ou_404(session: Session, time_id: int, fazenda_id: int | None) -> CaixaTime:
    t = session.get(CaixaTime, time_id)
    if not t or (fazenda_id is not None and t.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Caixa do time não encontrado")
    return t


def _rateio_ou_404(session: Session, rateio_id: int, fazenda_id: int | None) -> CaixaRateio:
    r = session.get(CaixaRateio, rateio_id)
    if not r or (fazenda_id is not None and r.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Rateio não encontrado")
    return r


def _movimentos(session: Session, time_id: int) -> list[CaixaTimeMovimento]:
    return list(session.exec(
        select(CaixaTimeMovimento).where(CaixaTimeMovimento.time_id == time_id)
        .order_by(CaixaTimeMovimento.data, CaixaTimeMovimento.id)
    ).all())


def _serializar_time(session: Session, t: CaixaTime) -> dict:
    hoje = date.today()
    datas = parametros.caixa_time_datas_entrega()
    inicio, fim, entrega = regras.periodo_em_apuracao(hoje, datas)
    return {
        "id": t.id, "nome": t.nome, "auto_tipos": [x for x in (t.auto_tipos or "").split(",") if x], "ativo": t.ativo,
        "saldo": regras.saldo_do_time(session, t.id),
        "membros": sum(1 for m in regras.membros_do_periodo(session, t, inicio, fim) if m["dias"] > 0),
        "periodo_inicio": inicio, "periodo_fim": fim, "proxima_entrega": entrega,
    }


def _normalizar_tipos(tipos: list[str]) -> str:
    invalidos = [t for t in tipos if t not in GRUPOS]
    if invalidos:
        raise HTTPException(status_code=400, detail=f"Tipo de membro inválido: {', '.join(invalidos)}")
    return ",".join(dict.fromkeys(tipos))


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------
class TimeIn(BaseModel):
    nome: str
    auto_tipos: list[str] = []
    ativo: bool = True


@router.get("/sugestao-resultado")
def sugestao_do_resultado(
    mes: str | None = None, percentual: float | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    """"X% do resultado do mês = R$ Y": a base é o RESULTADO LÍQUIDO da DRE Gerencial do mês (competência).
    Só sugere — quem lança a entrada aceita, ajusta ou ignora. `mes` AAAA-MM (padrão: o mês anterior);
    `percentual` (padrão: o parâmetro financeiro do caixa do time)."""
    import calendar

    from fazenda.api.routers.financeiro import dre as dre_gerencial
    from fazenda.rules.dre import RESULTADO_LIQUIDO

    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = date.today()
    if mes:
        try:
            ano, m = (int(x) for x in mes.split("-"))
            date(ano, m, 1)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Mês inválido. Use AAAA-MM.") from None
    else:
        ano, m = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    pct = parametros.caixa_time_pct_resultado() if percentual is None else percentual
    if not (0 <= pct <= 100):
        raise HTTPException(status_code=400, detail="O percentual deve estar entre 0 e 100.")
    d = dre_gerencial(
        data_inicio=date(ano, m, 1), data_fim=date(ano, m, calendar.monthrange(ano, m)[1]), centro_custo=None,
        regime="competencia", session=session, fazenda_id=fazenda_id,
    )
    linha = next((l for l in d["cascata"] if l["chave"] == RESULTADO_LIQUIDO), None)
    resultado = float(linha["valor"]) if linha else 0.0
    return {
        "mes": f"{ano}-{m:02d}", "regime": "competencia", "percentual": pct,
        "resultado_liquido": round(resultado, 2),
        # Resultado negativo ou zero não gera sugestão: o time não participa de prejuízo.
        "valor_sugerido": round(max(resultado, 0.0) * pct / 100, 2),
        "nao_classificado": d["nao_classificado"]["total"],
    }


@router.get("")
def listar_times(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(CaixaTime).where(CaixaTime.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(CaixaTime.fazenda_id == fazenda_id)
    times = [_serializar_time(session, t) for t in session.exec(query.order_by(CaixaTime.nome)).all()]
    return {"times": times, "total_pl": round(sum(t["saldo"] for t in times), 2)}


@router.post("")
def criar_time(
    dados: TimeIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    nome = (dados.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Dê um nome ao caixa do time")
    t = CaixaTime(fazenda_id=fazenda_id, nome=nome, auto_tipos=_normalizar_tipos(dados.auto_tipos), ativo=True)
    session.add(t)
    session.commit()
    session.refresh(t)
    return _serializar_time(session, t)


@router.put("/{time_id}")
def editar_time(
    time_id: int, dados: TimeIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    t = _time_ou_404(session, time_id, fazenda_id)
    nome = (dados.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Dê um nome ao caixa do time")
    if not dados.ativo and regras.saldo_do_time(session, t.id) != 0:
        raise HTTPException(status_code=409, detail="O caixa ainda tem saldo: faça o rateio antes de desativá-lo.")
    t.nome, t.auto_tipos, t.ativo = nome, _normalizar_tipos(dados.auto_tipos), dados.ativo
    session.add(t)
    session.commit()
    return _serializar_time(session, t)


@router.get("/{time_id}")
def obter_time(
    time_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    t = _time_ou_404(session, time_id, fazenda_id)
    base = _serializar_time(session, t)
    membros = regras.membros_do_periodo(session, t, base["periodo_inicio"], base["periodo_fim"])
    movs = _movimentos(session, t.id)
    estornados = {m.estorna_id for m in movs if m.estorna_id}
    acumulado = 0.0
    saldo_depois: dict[int, float] = {}
    for m in movs:
        acumulado = round(acumulado + m.valor, 2)
        saldo_depois[m.id] = acumulado
    rateios = session.exec(select(CaixaRateio).where(CaixaRateio.time_id == t.id).order_by(CaixaRateio.id.desc())).all()
    return {
        **base, "membros_lista": membros,
        "movimentos": [
            {**m.model_dump(), "saldo_depois": saldo_depois[m.id], "estornado": m.id in estornados,
             "pode_estornar": m.tipo not in ("estorno", "rateio") and not m.folha_id and m.id not in estornados}
            for m in sorted(movs, key=lambda x: (x.data, x.id), reverse=True)
        ],
        "rateios": [r.model_dump() for r in rateios],
        "tipos_entrada": TIPOS_ENTRADA,
    }


# ---------------------------------------------------------------------------
# Membros por nome
# ---------------------------------------------------------------------------
class MembrosIn(BaseModel):
    pessoa_ids: list[int]
    entrada: date | None = None


@router.post("/{time_id}/membros")
def adicionar_membros(
    time_id: int, dados: MembrosIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    t = _time_ou_404(session, time_id, fazenda_id)
    if not dados.pessoa_ids:
        raise HTTPException(status_code=400, detail="Escolha ao menos uma pessoa")
    entrada = dados.entrada or date.today()
    for pid in dict.fromkeys(dados.pessoa_ids):
        p = session.get(Pessoa, pid)
        if not p or p.fazenda_id != fazenda_id or not regras_caixa.grupos_da_pessoa(p):
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        atual = session.exec(select(CaixaTimeMembro).where(
            CaixaTimeMembro.time_id == t.id, CaixaTimeMembro.pessoa_id == pid)).first()
        if atual is None:
            session.add(CaixaTimeMembro(fazenda_id=fazenda_id, time_id=t.id, pessoa_id=pid, entrada=entrada))
        else:  # voltou ao time
            atual.entrada, atual.saida = entrada, None
            session.add(atual)
    session.commit()
    return _serializar_time(session, t)


@router.delete("/{time_id}/membros/{pessoa_id}")
def remover_membro(
    time_id: int, pessoa_id: int, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Dá saída HOJE (a pessoa continua contando os dias em que esteve). Quem entra por
    tipo e quer ficar de fora: entra por nome com saída — aqui, vira um membro por nome
    já encerrado."""
    t = _time_ou_404(session, time_id, fazenda_id)
    p = session.get(Pessoa, pessoa_id)
    if not p or p.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    m = session.exec(select(CaixaTimeMembro).where(
        CaixaTimeMembro.time_id == t.id, CaixaTimeMembro.pessoa_id == pessoa_id)).first()
    if m is None:
        m = CaixaTimeMembro(fazenda_id=fazenda_id, time_id=t.id, pessoa_id=pessoa_id, entrada=p.data_admissao or date.today())
    m.saida = date.today()
    session.add(m)
    session.commit()
    return _serializar_time(session, t)


# ---------------------------------------------------------------------------
# Entradas do time
# ---------------------------------------------------------------------------
class EntradaTimeIn(BaseModel):
    tipo: str
    data: date
    motivo: str
    valor: float | None = None
    base_valor: float | None = None
    percentual: float | None = None
    conta_bancaria: str | None = None


@router.post("/{time_id}/entradas")
def lancar_entrada_time(
    time_id: int, dados: EntradaTimeIn, session: Session = Depends(get_session), user=Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    t = _time_ou_404(session, time_id, fazenda_id)
    if not t.ativo:
        raise HTTPException(status_code=409, detail="Este caixa do time está desativado")
    if dados.tipo not in TIPOS_ENTRADA:
        raise HTTPException(status_code=400, detail="Tipo de entrada inválido")
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo da entrada")
    valor = dados.valor
    if dados.tipo == "comissao" and dados.base_valor is not None and dados.percentual is not None:
        valor = round(dados.base_valor * dados.percentual / 100, 2)
        motivo = f"{motivo} · base R$ {_brl(dados.base_valor)} × {dados.percentual:g}%"
    if valor is None or valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor maior que zero")
    valor = round(valor, 2)
    numero = _proximo_numero_lancamento(session, dados.data.year)
    conta = ContaGerencial(
        numero_lancamento=numero,
        descricao=f"{TIPOS_ENTRADA[dados.tipo]} · caixa do time {t.nome} · {motivo}"[:500],
        data_vencimento=dados.data, data_competencia=dados.data.replace(day=1),
        fornecedor_cliente=t.nome, tipo_documento=TIPO_DOC_ENTRADA, centro_custo="Pecuária Leiteira",
        valor_total=valor, parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
        data_pagamento=dados.data, valor_pago=valor, conta_bancaria=dados.conta_bancaria or None,
        forma_pagamento="caixa_funcionario", fazenda_id=fazenda_id,
    )
    session.add(conta)
    session.flush()
    mov = CaixaTimeMovimento(
        fazenda_id=fazenda_id, time_id=t.id, tipo=dados.tipo, valor=valor, data=dados.data, motivo=motivo,
        lancamento_id=conta.id, numero_lancamento=numero, usuario_id=usuario_id_seguro(user),
    )
    session.add(mov)
    session.commit()
    session.refresh(mov)
    return {"movimento": mov.model_dump(), "saldo": regras.saldo_do_time(session, t.id)}


class EstornoTimeIn(BaseModel):
    motivo: str


@router.post("/{time_id}/movimentos/{movimento_id}/estornar")
def estornar_entrada_time(
    time_id: int, movimento_id: int, dados: EstornoTimeIn, session: Session = Depends(get_session),
    user=Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    t = _time_ou_404(session, time_id, fazenda_id)
    original = session.get(CaixaTimeMovimento, movimento_id)
    if not original or original.time_id != t.id or original.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Movimento não encontrado")
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo do estorno")
    if original.folha_id:
        raise HTTPException(
            status_code=409,
            detail="Esta retenção veio de uma folha paga. Para desfazê-la, estorne o pagamento da folha.",
        )
    if original.tipo in ("estorno", "rateio"):
        raise HTTPException(status_code=409, detail="Este movimento não se estorna aqui (rateio: use 'Desfazer rateio')")
    if session.exec(select(CaixaTimeMovimento).where(CaixaTimeMovimento.estorna_id == original.id)).first():
        raise HTTPException(status_code=409, detail="Este movimento já foi estornado")
    if regras.saldo_do_time(session, t.id) - original.valor < 0:
        raise HTTPException(status_code=409, detail="O saldo desta entrada já foi repartido em rateio.")
    hoje = date.today()
    novo = CaixaTimeMovimento(
        fazenda_id=fazenda_id, time_id=t.id, tipo="estorno", valor=-original.valor, data=hoje,
        motivo=f"Estorno de {original.numero_lancamento or f'#{original.id}'}: {motivo}",
        estorna_id=original.id, usuario_id=usuario_id_seguro(user),
    )
    conta_original = session.get(ContaGerencial, original.lancamento_id) if original.lancamento_id else None
    if conta_original is not None:
        numero = _proximo_numero_lancamento(session, hoje.year)
        contra = ContaGerencial(
            numero_lancamento=numero,
            descricao=f"Estorno de {conta_original.numero_lancamento} · caixa do time {t.nome} · {motivo}"[:500],
            data_vencimento=hoje, data_competencia=hoje.replace(day=1), fornecedor_cliente=t.nome,
            tipo_documento=TIPO_DOC_ESTORNO, centro_custo=conta_original.centro_custo,
            valor_total=conta_original.valor_total, parcela_num=1, parcela_total=1, tipo="receita", origem="auto",
            data_pagamento=hoje, valor_pago=conta_original.valor_total, conta_bancaria=conta_original.conta_bancaria,
            forma_pagamento="caixa_funcionario", fazenda_id=fazenda_id,
        )
        session.add(contra)
        session.flush()
        novo.lancamento_id, novo.numero_lancamento = contra.id, numero
    session.add(novo)
    session.commit()
    return {"estorno": novo.model_dump()}


# ---------------------------------------------------------------------------
# Rateio
# ---------------------------------------------------------------------------
def _serializar_rateio(session: Session, r: CaixaRateio) -> dict:
    t = session.get(CaixaTime, r.time_id)
    linhas = list(session.exec(select(CaixaRateioLinha).where(CaixaRateioLinha.rateio_id == r.id)).all())
    saida = []
    for l in linhas:
        p = session.get(Pessoa, l.pessoa_id)
        saida.append({
            **l.model_dump(), "nome": p.nome if p else "—", "tipo": p.tipo if p else "",
            "grupos": regras_caixa.grupos_da_pessoa(p) if p else [],
        })
    saida.sort(key=lambda x: x["nome"])
    pend = [x["nome"] for x in saida if x["penalidade_pct"] > 0 and not x["documento_anexo_id"]]
    retirado = round(sum(round(x["parte_calculada"] * x["penalidade_pct"] / 100, 2) for x in saida), 2)
    return {
        **r.model_dump(), "time_nome": t.nome if t else "—", "linhas": saida,
        "documentos_pendentes": pend, "retirado_por_penalidade": retirado,
        "saldo_atual_do_time": regras.saldo_do_time(session, r.time_id),
        "pode_confirmar": r.situacao == "rascunho" and not pend,
    }


def _recalcular(session: Session, r: CaixaRateio) -> None:
    linhas = list(session.exec(select(CaixaRateioLinha).where(CaixaRateioLinha.rateio_id == r.id)).all())
    try:
        calc = regras.calcular_partes(
            r.total, [{"pessoa_id": l.pessoa_id, "dias": l.dias, "penalidade_pct": l.penalidade_pct} for l in linhas])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    for l, c in zip(linhas, calc):
        l.parte_calculada, l.parte_final = c["parte_calculada"], c["parte_final"]
        session.add(l)


class RateioIn(BaseModel):
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    data_entrega: date | None = None


@router.post("/{time_id}/rateios")
def criar_rateio(
    time_id: int, dados: RateioIn, session: Session = Depends(get_session), user=Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Cria o RASCUNHO: saldo do caixa repartido pelos dias de cada membro no período."""
    t = _time_ou_404(session, time_id, fazenda_id)
    if session.exec(select(CaixaRateio).where(CaixaRateio.time_id == t.id, CaixaRateio.situacao == "rascunho")).first():
        raise HTTPException(status_code=409, detail="Já existe um rateio em rascunho para este caixa. Confirme ou exclua.")
    ini, fim, entrega = regras.periodo_em_apuracao(date.today(), parametros.caixa_time_datas_entrega())
    inicio, fim, entrega = dados.periodo_inicio or ini, dados.periodo_fim or fim, dados.data_entrega or entrega
    if fim < inicio:
        raise HTTPException(status_code=400, detail="O fim do período não pode ser antes do início")
    saldo = regras.saldo_do_time(session, t.id)
    if saldo <= 0:
        raise HTTPException(status_code=409, detail="O caixa do time não tem saldo para ratear.")
    membros = [m for m in regras.membros_do_periodo(session, t, inicio, fim) if m["dias"] > 0]
    if not membros:
        raise HTTPException(status_code=409, detail="Nenhum membro participou do período. Adicione membros ao caixa do time.")
    r = CaixaRateio(fazenda_id=fazenda_id, time_id=t.id, periodo_inicio=inicio, periodo_fim=fim, data_entrega=entrega,
                    total=saldo, usuario_id=usuario_id_seguro(user))
    session.add(r)
    session.flush()
    for m in membros:
        session.add(CaixaRateioLinha(fazenda_id=fazenda_id, rateio_id=r.id, pessoa_id=m["pessoa_id"], dias=m["dias"]))
    session.flush()
    _recalcular(session, r)
    session.commit()
    return _serializar_rateio(session, r)


@router.get("/rateios/{rateio_id}")
def obter_rateio(
    rateio_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    return _serializar_rateio(session, _rateio_ou_404(session, rateio_id, fazenda_id))


class LinhaIn(BaseModel):
    penalidade_pct: float = 0.0
    penalidade_motivo: str | None = None
    documento_anexo_id: int | None = None
    destino: str = "individual"
    forma_pagamento: str | None = None
    # Pagamento direto: nº e arquivo do comprovante (opcionais; também dá para anexar depois de confirmado).
    numero_documento_pagamento: str | None = None
    comprovante_anexo_id: int | None = None


@router.put("/rateios/{rateio_id}/linhas/{pessoa_id}")
def ajustar_linha(
    rateio_id: int, pessoa_id: int, dados: LinhaIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    r = _rateio_ou_404(session, rateio_id, fazenda_id)
    if r.situacao != "rascunho":
        raise HTTPException(status_code=409, detail="Só o rascunho pode ser editado")
    l = session.exec(select(CaixaRateioLinha).where(
        CaixaRateioLinha.rateio_id == r.id, CaixaRateioLinha.pessoa_id == pessoa_id)).first()
    if l is None:
        raise HTTPException(status_code=404, detail="Pessoa não está neste rateio")
    if not 0 <= dados.penalidade_pct <= 100:
        raise HTTPException(status_code=400, detail="A penalidade vai de 0 a 100%")
    if dados.destino not in ("individual", "direto"):
        raise HTTPException(status_code=400, detail="Destino inválido")
    if dados.destino == "direto" and (dados.forma_pagamento or "pix") not in FORMAS:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.penalidade_pct > 0 and not (dados.penalidade_motivo or "").strip():
        raise HTTPException(status_code=400, detail="Informe o motivo da penalidade (ex.: art. 482 da CLT)")
    anexo_id = dados.documento_anexo_id if dados.penalidade_pct > 0 else None
    if anexo_id is not None:
        a = session.get(PessoaAnexo, anexo_id)
        if not a or a.pessoa_id != pessoa_id or a.fazenda_id != fazenda_id:
            raise HTTPException(status_code=404, detail="Documento não encontrado nesta pessoa")
    comprovante_id = dados.comprovante_anexo_id if dados.destino == "direto" else None
    if comprovante_id is not None:
        c = session.get(PessoaAnexo, comprovante_id)
        if not c or c.pessoa_id != pessoa_id or c.fazenda_id != fazenda_id:
            raise HTTPException(status_code=404, detail="Comprovante não encontrado nesta pessoa")
    l.numero_documento_pagamento = (dados.numero_documento_pagamento or "").strip() or None if dados.destino == "direto" else None
    l.comprovante_anexo_id = comprovante_id
    l.penalidade_pct = dados.penalidade_pct
    l.penalidade_motivo = (dados.penalidade_motivo or "").strip() or None if dados.penalidade_pct > 0 else None
    l.documento_anexo_id = anexo_id
    l.destino = dados.destino
    l.forma_pagamento = (dados.forma_pagamento or "pix") if dados.destino == "direto" else None
    session.add(l)
    session.flush()
    _recalcular(session, r)
    session.commit()
    return _serializar_rateio(session, r)


@router.delete("/rateios/{rateio_id}")
def excluir_rascunho(
    rateio_id: int, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    r = _rateio_ou_404(session, rateio_id, fazenda_id)
    if r.situacao != "rascunho":
        raise HTTPException(status_code=409, detail="Só o rascunho pode ser excluído. Rateio confirmado se desfaz.")
    for l in session.exec(select(CaixaRateioLinha).where(CaixaRateioLinha.rateio_id == r.id)).all():
        session.delete(l)
    session.delete(r)
    session.commit()
    return {"excluido": True}


@router.post("/rateios/{rateio_id}/confirmar")
def confirmar_rateio(
    rateio_id: int, session: Session = Depends(get_session), user=Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    r = _rateio_ou_404(session, rateio_id, fazenda_id)
    if r.situacao != "rascunho":
        raise HTTPException(status_code=409, detail="Este rateio já foi confirmado ou desfeito")
    linhas = list(session.exec(select(CaixaRateioLinha).where(CaixaRateioLinha.rateio_id == r.id)).all())
    sem_doc = [l for l in linhas if l.penalidade_pct > 0 and not l.documento_anexo_id]
    if sem_doc:
        nomes = ", ".join(session.get(Pessoa, l.pessoa_id).nome for l in sem_doc)
        raise HTTPException(
            status_code=409,
            detail=f"Falta o documento de ciência da penalidade de: {nomes}. O rateio só confirma com o documento anexado.",
        )
    if abs(regras.saldo_do_time(session, r.time_id) - r.total) > 0.005:
        raise HTTPException(
            status_code=409,
            detail="O saldo do caixa do time mudou depois que este rascunho foi criado. Exclua o rascunho e crie outro.",
        )
    if abs(round(sum(l.parte_final for l in linhas), 2) - r.total) > 0.005:
        raise HTTPException(status_code=409, detail="As partes não somam o total do caixa. Recalcule o rascunho.")
    t = session.get(CaixaTime, r.time_id)
    usuario_id = usuario_id_seguro(user)
    for l in linhas:
        if l.parte_final <= 0:
            continue
        cred = CaixaMovimento(
            fazenda_id=fazenda_id, pessoa_id=l.pessoa_id, tipo="rateio", valor=l.parte_final, data=r.data_entrega,
            motivo=f"Rateio do PL · {t.nome} · {r.periodo_inicio:%d/%m/%Y} a {r.periodo_fim:%d/%m/%Y}"
                   + (f" · penalidade {l.penalidade_pct:g}%" if l.penalidade_pct else ""),
            rateio_id=r.id, usuario_id=usuario_id,
        )
        session.add(cred)
        session.flush()
        l.movimento_id = cred.id
        if l.destino == "direto":
            ret = CaixaMovimento(
                fazenda_id=fazenda_id, pessoa_id=l.pessoa_id, tipo="retirada", valor=-l.parte_final, data=r.data_entrega,
                motivo=f"Pagamento direto do rateio do PL · {t.nome}", forma_pagamento=l.forma_pagamento or "pix",
                numero_documento_pagamento=l.numero_documento_pagamento, comprovante_anexo_id=l.comprovante_anexo_id,
                rateio_id=r.id, usuario_id=usuario_id,
            )
            session.add(ret)
            session.flush()
            ret.numero_recibo = f"CX-{r.data_entrega.year}-{ret.id:05d}"
            l.retirada_id = ret.id
        session.add(l)
    session.add(CaixaTimeMovimento(
        fazenda_id=fazenda_id, time_id=r.time_id, tipo="rateio", valor=-r.total, data=r.data_entrega,
        motivo=f"Rateio do PL · {r.periodo_inicio:%d/%m/%Y} a {r.periodo_fim:%d/%m/%Y}", rateio_id=r.id,
        usuario_id=usuario_id,
    ))
    r.situacao, r.confirmado_em = "confirmado", datetime.utcnow()
    session.add(r)
    session.commit()
    return _serializar_rateio(session, r)


@router.post("/rateios/{rateio_id}/desfazer")
def desfazer_rateio(
    rateio_id: int, session: Session = Depends(get_session), user=Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Estorna os créditos e devolve o total ao caixa do time. Recusa se alguma parte já
    foi sacada (saldo individual menor que a parte) ou se houve pagamento direto."""
    r = _rateio_ou_404(session, rateio_id, fazenda_id)
    if r.situacao != "confirmado":
        raise HTTPException(status_code=409, detail="Só um rateio confirmado se desfaz")
    linhas = list(session.exec(select(CaixaRateioLinha).where(CaixaRateioLinha.rateio_id == r.id)).all())
    if any(l.retirada_id for l in linhas):
        raise HTTPException(
            status_code=409,
            detail="Este rateio teve pagamento direto (dinheiro que já saiu). Não dá para desfazê-lo por aqui.",
        )
    usuario_id = usuario_id_seguro(user)
    for l in linhas:
        if not l.movimento_id:
            continue
        cred = session.get(CaixaMovimento, l.movimento_id)
        if cred is None:
            continue
        try:
            regras_caixa.estornar_movimento(session, cred, "rateio do PL desfeito", usuario_id, fazenda_id)
        except HTTPException as exc:
            session.rollback()
            if exc.status_code == 409 and "retirada" in str(exc.detail):
                nome = (session.get(Pessoa, l.pessoa_id) or Pessoa(nome="—")).nome
                raise HTTPException(
                    status_code=409,
                    detail=f"A parte de {nome} já foi retirada do caixa individual. Estorne a retirada antes de desfazer o rateio.",
                ) from None
            raise
    session.add(CaixaTimeMovimento(
        fazenda_id=fazenda_id, time_id=r.time_id, tipo="estorno", valor=r.total, data=date.today(),
        motivo=f"Rateio do PL de {r.data_entrega:%d/%m/%Y} desfeito", rateio_id=r.id, usuario_id=usuario_id,
    ))
    r.situacao = "desfeito"
    session.add(r)
    session.commit()
    return _serializar_rateio(session, r)
