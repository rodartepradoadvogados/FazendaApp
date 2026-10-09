"""
Relatórios › Entrega ao contador (Fase C5 — docs/financeiro-fechamento-conciliacao.md):

- Fechamento do mês: `GET /financeiro/fechamento/meses`, `GET /financeiro/fechamento/{mes}`,
  `POST /financeiro/fechamento/{mes}/fechar` e `/reabrir` (administrador; trilha append-only).
- Conciliação bancária: `POST /financeiro/conciliacao/importar` (OFX/CSV),
  `GET /financeiro/conciliacao` (extrato × sistema de uma conta num mês), parear,
  desfazer, "sem lançamento", confirmar as sugestões exatas em lote.
- Pacote do contador: `GET /financeiro/pacote-contador` (o que vai no pacote),
  `/zip` e `/pdf` (download).

Montado em main.py com as MESMAS travas do router do Financeiro (módulo
financeiro, plano contratado, fazenda selecionada e `bloquear_escrita_contador`):
o vínculo `contador` lê tudo e baixa o pacote (GET), mas não escreve. Toda rota
de escrita usa `get_fazenda_id_escrita`; toda leitura filtra pela fazenda.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    ContaCorrente, ContaGerencial, ExportacaoRelatorioLog, ExtratoImportacao, ExtratoLinha, FechamentoMesEvento,
    TransferenciaContas, Usuario,
)
from fazenda.rules import conciliacao_banco, fechamento_mes, pacote_contador
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.datas import hoje_local
from fazenda.rules.extrato_bancario import ExtratoInvalido, ler_extrato
from fazenda.rules.parametros import regras_v2_ativas

router = APIRouter(prefix="/financeiro", tags=["financeiro-fechamento"])

LIMITE_ARQUIVO_EXTRATO = 5 * 1024 * 1024
MOTIVO_MINIMO = 5


def _fazenda(fazenda_id: int | None) -> int:
    fid = fazenda_id_seguro(fazenda_id)
    if not isinstance(fid, int):
        raise HTTPException(
            status_code=409, detail="Selecione a fazenda (saia e entre de novo) para usar o fechamento, a conciliação e o pacote.",
            headers={"X-Fazenda-Nao-Selecionada": "1"},
        )
    return fid


def _nome(user: Usuario) -> str:
    return (getattr(user, "nome", None) or getattr(user, "username", None) or "").strip() or "usuário"


def _conta(session: Session, fazenda_id: int, conta_id: int) -> ContaCorrente:
    c = session.get(ContaCorrente, conta_id)
    if not c or c.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Conta corrente não encontrada")
    return c


# ═════════════════════════════ Fechamento do mês ═════════════════════════════
@router.get("/fechamento/meses")
def fechamento_meses(
    ate: Optional[str] = Query(None, description="Último mês (AAAA-MM); padrão: o mês de hoje"),
    quantidade: int = Query(24, ge=1, le=60),
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Situação de cada mês (aberto/fechado/em curso) para a grade e o selo discreto do Resumo."""
    fid = _fazenda(fazenda_id)
    hoje = hoje_local()
    fim_mes = ate or fechamento_mes.mes_de(hoje)
    fechamento_mes.limites_do_mes(fim_mes)
    a, m = int(fim_mes[:4]), int(fim_mes[5:7])
    meses = []
    for _ in range(quantidade):
        meses.append(f"{a:04d}-{m:02d}")
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    ultimo = fechamento_mes.ultimo_evento_por_mes(session, fid)
    mes_hoje = fechamento_mes.mes_de(hoje)
    saida = []
    for mes in reversed(meses):
        ev = ultimo.get(mes)
        fechado = bool(ev and ev.acao == "fechar")
        saida.append({
            "mes": mes,
            "status": "fechado" if fechado else ("em_curso" if mes >= mes_hoje else "aberto"),
            "fechado_em": ev.criado_em.isoformat() if fechado else None,
            "fechado_por": ev.usuario_nome if fechado else None,
            "reaberto": bool(ev and ev.acao == "reabrir"),
        })
    trilha = sorted(fechamento_mes.eventos(session, fid), key=lambda e: e.id, reverse=True)[:30]
    return {
        "regras_v2": regras_v2_ativas(session, fid), "hoje": hoje.isoformat(), "meses": saida,
        "trilha": [fechamento_mes.dump_evento(e) for e in trilha],
    }


@router.get("/fechamento/{mes}")
def fechamento_do_mes(
    mes: str, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Checklist ao vivo, estado, trilha do mês e retrato atual × retrato do fechamento."""
    fid = _fazenda(fazenda_id)
    fechamento_mes.limites_do_mes(mes)
    return fechamento_mes.situacao_do_mes(session, fid, mes)


class FecharIn(BaseModel):
    motivo: Optional[str] = None
    forcar: bool = False  # fechar com pendências (exige motivo)


class ReabrirIn(BaseModel):
    motivo: str


def _exigir_flag(session: Session, fid: int) -> None:
    if not regras_v2_ativas(session, fid):
        raise HTTPException(status_code=409, detail={
            "codigo": "regras_v2_desligadas",
            "mensagem": "O fechamento do mês trava a edição pelas regras novas dos relatórios. Ligue as regras novas em "
                        "Configurações › Parâmetros financeiros para fechar meses.",
        })


@router.post("/fechamento/{mes}/fechar", status_code=201)
def fechar_mes(
    mes: str, dados: FecharIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita), user: Usuario = Depends(exigir_admin),
) -> dict:
    fid = _fazenda(fazenda_id)
    ini, fim = fechamento_mes.limites_do_mes(mes)
    _exigir_flag(session, fid)
    if fim >= hoje_local():
        raise HTTPException(status_code=409, detail={
            "codigo": "mes_em_curso", "mensagem": f"{fechamento_mes.nome_mes(mes).capitalize()} ainda não acabou: feche a partir de {date.fromordinal(fim.toordinal() + 1):%d/%m/%Y}.",
        })
    if fechamento_mes.esta_fechado(session, fid, mes):
        raise HTTPException(status_code=409, detail={"codigo": "ja_fechado", "mensagem": "Este mês já está fechado."})
    checklist = fechamento_mes.checklist(session, fid, mes)
    pendentes = [c for c in checklist if not c["ok"] and c["bloqueia"]]
    motivo = (dados.motivo or "").strip() or None
    if pendentes and not dados.forcar:
        raise HTTPException(status_code=409, detail={
            "codigo": "pendencias", "pendencias": len(pendentes), "itens": [c["nome"] for c in pendentes],
            "mensagem": f"Faltam {len(pendentes)} conferência(s): resolva antes de fechar ou feche assim mesmo informando o motivo.",
        })
    if pendentes and (not motivo or len(motivo) < MOTIVO_MINIMO):
        raise HTTPException(status_code=422, detail="Para fechar com pendências, escreva o motivo (fica na trilha).")
    retrato = fechamento_mes.retrato(session, fid, mes)
    ev = FechamentoMesEvento(
        fazenda_id=fid, mes=mes, acao="fechar", motivo=(motivo or "")[:500] or None, usuario_id=user.id, usuario_nome=_nome(user),
        retrato_json=fechamento_mes.json_canonico(retrato), retrato_sha256=fechamento_mes.sha256_retrato(retrato),
        pendencias_no_fechamento=len(pendentes),
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return {"evento": fechamento_mes.dump_evento(ev), "retrato": retrato}


@router.post("/fechamento/{mes}/reabrir", status_code=201)
def reabrir_mes(
    mes: str, dados: ReabrirIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita), user: Usuario = Depends(exigir_admin),
) -> dict:
    fid = _fazenda(fazenda_id)
    fechamento_mes.limites_do_mes(mes)
    motivo = (dados.motivo or "").strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise HTTPException(status_code=422, detail="Escreva o motivo da reabertura (fica na trilha).")
    if not fechamento_mes.esta_fechado(session, fid, mes):
        raise HTTPException(status_code=409, detail={"codigo": "nao_fechado", "mensagem": "Este mês não está fechado."})
    ev = FechamentoMesEvento(fazenda_id=fid, mes=mes, acao="reabrir", motivo=motivo[:500], usuario_id=user.id, usuario_nome=_nome(user))
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return {"evento": fechamento_mes.dump_evento(ev)}


# ═══════════════════════════ Conciliação bancária ════════════════════════════
@router.get("/conciliacao")
def conciliacao(
    mes: str = Query(..., description="AAAA-MM"), conta_corrente_id: Optional[int] = Query(None),
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Extrato × sistema de uma conta no mês, com as sugestões de pareamento,
    e o resumo de todas as contas (para o seletor e o checklist)."""
    fid = _fazenda(fazenda_id)
    ini, fim = fechamento_mes.limites_do_mes(mes)
    contas = conciliacao_banco.contas_da_fazenda(session, fid)
    resumo = conciliacao_banco.resumo_contas(session, fid, ini, fim)
    if not contas:
        return {"mes": mes, "contas": [], "resumo": [], "situacao": None}
    conta = _conta(session, fid, conta_corrente_id) if conta_corrente_id else contas[0]
    importacoes = session.exec(select(ExtratoImportacao).where(
        ExtratoImportacao.fazenda_id == fid, ExtratoImportacao.conta_corrente_id == conta.id,
    ).order_by(ExtratoImportacao.id.desc())).all()
    return {
        "mes": mes,
        "contas": [{"id": c.id, "rotulo": conciliacao_banco.rotulo_conta(c), "banco": c.banco} for c in contas],
        "resumo": resumo,
        "situacao": conciliacao_banco.situacao(session, fid, conta, ini, fim),
        "importacoes": [{
            "id": i.id, "formato": i.formato, "data_inicio": i.data_inicio.isoformat() if i.data_inicio else None,
            "data_fim": i.data_fim.isoformat() if i.data_fim else None, "saldo_final": i.saldo_final,
            "data_saldo": i.data_saldo.isoformat() if i.data_saldo else None, "linhas_novas": i.linhas_novas,
            "linhas_repetidas": i.linhas_repetidas, "criado_em": i.criado_em.isoformat(),
        } for i in importacoes[:10]],
    }


@router.post("/conciliacao/importar", status_code=201)
async def importar_extrato(
    conta_corrente_id: int = Form(...), arquivo: UploadFile = File(...),
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_id_escrita),
    user: Usuario = Depends(get_current_user),
) -> dict:
    """Importa um extrato OFX ou CSV na conta. Linhas já importadas (mesma
    chave) são ignoradas. O arquivo não é guardado."""
    fid = _fazenda(fazenda_id)
    conta = _conta(session, fid, conta_corrente_id)
    conteudo = await arquivo.read(LIMITE_ARQUIVO_EXTRATO + 1)
    if len(conteudo) > LIMITE_ARQUIVO_EXTRATO:
        raise HTTPException(status_code=413, detail="Extrato maior que 5 MB: exporte um período menor.")
    try:
        lido = ler_extrato(conteudo, arquivo.filename)
    except ExtratoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from None
    existentes = set(session.exec(select(ExtratoLinha.chave_dedup).where(
        ExtratoLinha.fazenda_id == fid, ExtratoLinha.conta_corrente_id == conta.id)).all())
    imp = ExtratoImportacao(
        fazenda_id=fid, conta_corrente_id=conta.id, formato=lido.formato, data_inicio=lido.data_inicio,
        data_fim=lido.data_fim, saldo_final=lido.saldo_final, data_saldo=lido.data_saldo, usuario_id=user.id,
    )
    session.add(imp)
    session.flush()
    novas = repetidas = 0
    for m in lido.movimentos:
        if m.chave in existentes:
            repetidas += 1
            continue
        existentes.add(m.chave)
        session.add(ExtratoLinha(
            fazenda_id=fid, conta_corrente_id=conta.id, importacao_id=imp.id, data=m.data, valor=m.valor,
            historico=m.historico or None, documento=(m.documento or None) and m.documento[:60], chave_dedup=m.chave,
        ))
        novas += 1
    imp.linhas_novas, imp.linhas_repetidas = novas, repetidas
    session.add(imp)
    session.commit()
    return {
        "importacao_id": imp.id, "formato": lido.formato, "linhas_novas": novas, "linhas_repetidas": repetidas,
        "data_inicio": lido.data_inicio.isoformat() if lido.data_inicio else None,
        "data_fim": lido.data_fim.isoformat() if lido.data_fim else None,
        "saldo_final": lido.saldo_final, "data_saldo": lido.data_saldo.isoformat() if lido.data_saldo else None,
        "avisos": lido.avisos,
    }


def _linha(session: Session, fid: int, linha_id: int) -> ExtratoLinha:
    l = session.get(ExtratoLinha, linha_id)
    if not l or l.fazenda_id != fid:
        raise HTTPException(status_code=404, detail="Linha do extrato não encontrada")
    return l


class ParearIn(BaseModel):
    lancamento_id: Optional[int] = None
    transferencia_id: Optional[int] = None


def _parear(session: Session, fid: int, l: ExtratoLinha, dados: ParearIn, user_id: int | None) -> None:
    if (dados.lancamento_id is None) == (dados.transferencia_id is None):
        raise HTTPException(status_code=422, detail="Informe o lançamento OU a transferência a parear.")
    if l.status != "pendente":
        raise HTTPException(status_code=409, detail="Esta linha já foi conciliada: desfaça antes de parear de novo.")
    conta = _conta(session, fid, l.conta_corrente_id)
    rotulo = conciliacao_banco.rotulo_conta(conta)
    if dados.lancamento_id is not None:
        c = session.get(ContaGerencial, dados.lancamento_id)
        if not c or c.fazenda_id != fid:
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")
        if c.data_pagamento is None:
            raise HTTPException(status_code=409, detail="Só lançamento pago (baixado) pareia com o extrato.")
        if not (c.conta_corrente_id == conta.id or (c.conta_corrente_id is None and c.conta_bancaria == rotulo)):
            raise HTTPException(status_code=409, detail="Este lançamento foi pago por outra conta corrente.")
        if (c.tipo == "receita") != (l.valor > 0):
            raise HTTPException(status_code=409, detail="Entrada no extrato só pareia com receita; saída, com despesa.")
        ja = session.exec(select(ExtratoLinha).where(
            ExtratoLinha.fazenda_id == fid, ExtratoLinha.lancamento_id == c.id, ExtratoLinha.status == "pareado")).first()
        if ja:
            raise HTTPException(status_code=409, detail="Este lançamento já está pareado com outra linha do extrato.")
        l.lancamento_id = c.id
    else:
        t = session.get(TransferenciaContas, dados.transferencia_id)
        if not t or t.fazenda_id != fid or conta.id not in (t.conta_origem_id, t.conta_destino_id):
            raise HTTPException(status_code=404, detail="Transferência não encontrada nesta conta")
        ja = session.exec(select(ExtratoLinha).where(
            ExtratoLinha.fazenda_id == fid, ExtratoLinha.conta_corrente_id == conta.id,
            ExtratoLinha.transferencia_id == t.id, ExtratoLinha.status == "pareado")).first()
        if ja:
            raise HTTPException(status_code=409, detail="Esta transferência já está pareada com outra linha do extrato.")
        l.transferencia_id = t.id
    l.status = "pareado"
    l.observacao = None
    l.conciliado_por, l.conciliado_em = user_id, datetime.utcnow()
    session.add(l)


@router.post("/conciliacao/linhas/{linha_id}/parear")
def parear_linha(
    linha_id: int, dados: ParearIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita), user: Usuario = Depends(get_current_user),
) -> dict:
    fid = _fazenda(fazenda_id)
    l = _linha(session, fid, linha_id)
    _parear(session, fid, l, dados, user.id)
    session.commit()
    return {"id": l.id, "status": l.status, "lancamento_id": l.lancamento_id, "transferencia_id": l.transferencia_id}


class SemLancamentoIn(BaseModel):
    observacao: Optional[str] = None


@router.post("/conciliacao/linhas/{linha_id}/sem-lancamento")
def marcar_sem_lancamento(
    linha_id: int, dados: SemLancamentoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita), user: Usuario = Depends(get_current_user),
) -> dict:
    """Linha que não terá lançamento (ex.: estorno do próprio banco no mesmo dia)."""
    fid = _fazenda(fazenda_id)
    l = _linha(session, fid, linha_id)
    if l.status != "pendente":
        raise HTTPException(status_code=409, detail="Esta linha já foi conciliada: desfaça antes.")
    l.status = "sem_lancamento"
    l.observacao = (dados.observacao or "").strip()[:200] or None
    l.conciliado_por, l.conciliado_em = user.id, datetime.utcnow()
    session.add(l)
    session.commit()
    return {"id": l.id, "status": l.status}


@router.post("/conciliacao/linhas/{linha_id}/desfazer")
def desfazer_linha(
    linha_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita), user: Usuario = Depends(get_current_user),  # noqa: ARG001
) -> dict:
    fid = _fazenda(fazenda_id)
    l = _linha(session, fid, linha_id)
    l.status, l.lancamento_id, l.transferencia_id, l.observacao = "pendente", None, None, None
    l.conciliado_por, l.conciliado_em = None, None
    session.add(l)
    session.commit()
    return {"id": l.id, "status": l.status}


class ConfirmarSugestoesIn(BaseModel):
    conta_corrente_id: int
    mes: str
    linha_ids: Optional[list[int]] = None  # None = todas as sugestões exatas do mês


@router.post("/conciliacao/confirmar-sugestoes")
def confirmar_sugestoes(
    dados: ConfirmarSugestoesIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita), user: Usuario = Depends(get_current_user),
) -> dict:
    """Confirma de uma vez as sugestões EXATAS (valor ao centavo) — a fila de pareamentos."""
    fid = _fazenda(fazenda_id)
    conta = _conta(session, fid, dados.conta_corrente_id)
    ini, fim = fechamento_mes.limites_do_mes(dados.mes)
    s = conciliacao_banco.situacao(session, fid, conta, ini, fim)
    alvo = set(dados.linha_ids) if dados.linha_ids is not None else None
    feitas = 0
    for l in s["linhas"]:
        sug = l.get("sugestao")
        if l["status"] != "pendente" or not sug or not sug.get("exata") or (alvo is not None and l["id"] not in alvo):
            continue
        linha = _linha(session, fid, l["id"])
        par = ParearIn(lancamento_id=sug["id"]) if sug["tipo"] == "lancamento" else ParearIn(transferencia_id=sug["id"])
        _parear(session, fid, linha, par, user.id)
        feitas += 1
    session.commit()
    return {"pareadas": feitas}


# ═══════════════════════════ Pacote do contador ═════════════════════════════
def _periodo(data_inicio: date, data_fim: date) -> None:
    if data_fim < data_inicio:
        raise HTTPException(status_code=422, detail="A data final é anterior à inicial.")
    if (data_fim - data_inicio).days > 400:
        raise HTTPException(status_code=422, detail="O pacote vai até 13 meses por vez (ano-calendário).")


def _registrar_exportacao(session: Session, fid: int, user: Usuario, formato: str) -> None:
    """Quem gerou o pacote, quando e em que formato (log append-only do parecer 6.2)."""
    try:
        if isinstance(getattr(user, "id", None), int):
            session.add(ExportacaoRelatorioLog(
                fazenda_id=fid, usuario_id=user.id, relatorio="pacote_contador", formato=formato,
                destinatario_tipo="contador", finalidade="Entrega ao contador (escrituração)",
            ))
            session.commit()
    except Exception:  # noqa: BLE001 - o log nunca impede o download
        session.rollback()


@router.get("/pacote-contador")
def pacote_contador_resumo(
    data_inicio: date = Query(...), data_fim: date = Query(...),
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    user: Usuario = Depends(get_current_user),
) -> dict:
    fid = _fazenda(fazenda_id)
    _periodo(data_inicio, data_fim)
    dados = pacote_contador.montar(session, fid, data_inicio, data_fim, _nome(user))
    return pacote_contador.resumo_para_tela(dados)


@router.get("/pacote-contador/zip")
def pacote_contador_zip(
    data_inicio: date = Query(...), data_fim: date = Query(...),
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    user: Usuario = Depends(get_current_user),
) -> Response:
    fid = _fazenda(fazenda_id)
    _periodo(data_inicio, data_fim)
    dados = pacote_contador.montar(session, fid, data_inicio, data_fim, _nome(user))
    conteudo = pacote_contador.gerar_zip(dados)
    _registrar_exportacao(session, fid, user, "zip")
    nome = pacote_contador.nome_base(dados) + ".zip"
    return Response(conteudo, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/pacote-contador/pdf")
def pacote_contador_pdf(
    data_inicio: date = Query(...), data_fim: date = Query(...),
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    user: Usuario = Depends(get_current_user),
) -> Response:
    fid = _fazenda(fazenda_id)
    _periodo(data_inicio, data_fim)
    dados = pacote_contador.montar(session, fid, data_inicio, data_fim, _nome(user))
    conteudo = pacote_contador.gerar_pdf(dados)
    _registrar_exportacao(session, fid, user, "pdf")
    nome = pacote_contador.nome_base(dados) + ".pdf"
    return Response(conteudo, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nome}"'})
