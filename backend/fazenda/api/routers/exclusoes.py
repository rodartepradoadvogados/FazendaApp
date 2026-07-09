"""
Router de exclusões — apaga registros de qualquer tipo de lançamento com uma
prévia de impacto antes de confirmar.

Administradores excluem direto. Operadores só podem SOLICITAR a exclusão —
o pedido fica pendente até um administrador aprovar (executa a exclusão de
fato) ou rejeitar.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual,
    Animal,
    CalendarioSanitario,
    ContaGerencial,
    ControleLeiteiro,
    Doenca,
    Estoque,
    EventoSanitario,
    FolhaPagamento,
    Fornecedor,
    LancamentoItem,
    Lote,
    MotivoMovimentacao,
    Parto,
    Pessoa,
    PrincipioAtivo,
    ProtocoloSanitario,
    ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento,
    Sanidade,
    Servico,
    SolicitacaoExclusao,
    Usuario,
    ValeFuncionario,
)

router = APIRouter(prefix="/exclusoes", tags=["exclusoes"])

TIPOS = [
    {"id": "animal", "label": "Animal (ficha)"},
    {"id": "servico", "label": "Serviço / IA (inclui diagnóstico)"},
    {"id": "parto", "label": "Parto / nascimento"},
    {"id": "controle", "label": "Controle leiteiro"},
    {"id": "sanidade", "label": "Sanidade"},
    {"id": "financeiro", "label": "Financeiro"},
    {"id": "estoque", "label": "Estoque"},
    {"id": "evento_manual", "label": "Evento manual da agenda"},
    {"id": "lote", "label": "Lote (cadastro)"},
    {"id": "fornecedor", "label": "Fornecedor/fabricante/cliente/corretor"},
    {"id": "motivo_movimentacao", "label": "Motivo de movimentação"},
    {"id": "pessoa", "label": "Pessoa"},
    {"id": "principio_ativo", "label": "Princípio ativo"},
    {"id": "doenca", "label": "Doença"},
    {"id": "evento_sanitario", "label": "Evento sanitário"},
    {"id": "protocolo_sanitario", "label": "Protocolo sanitário (cadastro)"},
]


@router.get("/tipos")
def tipos() -> list[dict]:
    return TIPOS


def _br(data) -> str:
    """Formata uma data como dd/mm/aaaa (padrão brasileiro) para exibição no título."""
    return data.strftime("%d/%m/%Y") if data else "—"


def _contem(termo: str, *valores) -> bool:
    if not termo:
        return True
    termo = termo.strip().lower()
    return any(termo in str(v).lower() for v in valores if v is not None)


def _dentro_periodo(data_ref, data_inicio: str, data_fim: str) -> bool:
    """Filtro de data opcional — sem data de referência no registro, ou sem filtro definido, não exclui nada."""
    if not data_inicio and not data_fim:
        return True
    if data_ref is None:
        return False
    ref = data_ref.isoformat()
    if data_inicio and ref < data_inicio:
        return False
    if data_fim and ref > data_fim:
        return False
    return True


@router.get("/buscar")
def buscar(
    tipo: str = Query(...),
    termo: str = Query(""),
    data_inicio: str = Query(""),
    data_fim: str = Query(""),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Lista candidatos a exclusão de um tipo, filtrados por um termo de busca e, opcionalmente, por período."""
    if tipo == "animal":
        rows = session.exec(select(Animal)).all()
        out = [
            {"id": a.numero, "titulo": a.numero, "subtitulo": f"{a.categoria_abrev or a.categoria_completa or '—'} · {a.grupo_primario or '—'}"}
            for a in rows if _contem(termo, a.numero, a.grupo_primario, a.categoria_completa)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "servico":
        rows = session.exec(select(Servico)).all()
        out = [
            {
                "id": s.id,
                "titulo": f"{s.numero_matriz} — {_br(s.data_servico)}",
                "subtitulo": f"{s.tipo_servico or '—'} · {s.reprodutor or '—'} · diag: {s.diagnostico or '—'}",
            }
            for s in rows
            if _contem(termo, s.numero_matriz, s.reprodutor, s.diagnostico, s.tipo_servico)
            and _dentro_periodo(s.data_servico, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "parto":
        rows = session.exec(select(Parto)).all()
        out = [
            {
                "id": p.id,
                "titulo": f"{p.numero_matriz} — {_br(p.data_parto)}",
                "subtitulo": f"Parto nº{p.ordem_parto or '?'} · {p.tipo_parto or '—'}",
            }
            for p in rows
            if _contem(termo, p.numero_matriz, p.tipo_parto) and _dentro_periodo(p.data_parto, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "controle":
        rows = session.exec(select(ControleLeiteiro)).all()
        out = [
            {
                "id": c.id,
                "titulo": f"{c.numero_matriz} — {_br(c.data_controle)}",
                "subtitulo": f"{c.producao_kg or 0} kg",
            }
            for c in rows
            if _contem(termo, c.numero_matriz) and _dentro_periodo(c.data_controle, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "sanidade":
        rows = session.exec(select(Sanidade)).all()
        out = [
            {
                "id": s.id,
                "titulo": f"{s.numero_matriz} — {_br(s.data_aplicacao)}",
                "subtitulo": s.produto,
            }
            for s in rows
            if _contem(termo, s.numero_matriz, s.produto) and _dentro_periodo(s.data_aplicacao, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "financeiro":
        rows = session.exec(select(ContaGerencial)).all()
        out = [
            {
                "id": c.id,
                "titulo": f"{c.numero_lancamento or '(csv)'} — {c.descricao or '—'}",
                "subtitulo": f"R$ {c.valor_total or 0:,.2f} · {c.fornecedor_cliente or '—'}"
                + (f" · parcela {c.parcela_num}/{c.parcela_total}" if (c.parcela_total or 1) > 1 else ""),
            }
            for c in rows
            if _contem(termo, c.numero_lancamento, c.descricao, c.fornecedor_cliente, c.numero_nota)
            and _dentro_periodo(
                c.data_vencimento or c.data_competencia or c.data_emissao, data_inicio, data_fim
            )
        ]
        return out[:200]

    if tipo == "estoque":
        rows = session.exec(select(Estoque)).all()
        out = [
            {"id": e.id, "titulo": e.nome, "subtitulo": f"{e.quantidade or 0} {e.unidade or ''}"}
            for e in rows if _contem(termo, e.nome)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "evento_manual":
        rows = session.exec(select(AgendaManual)).all()
        out = [
            {
                "id": ev.id,
                "titulo": f"{_br(ev.data_evento)} — {ev.descricao}",
                "subtitulo": ev.categoria,
            }
            for ev in rows
            if _contem(termo, ev.descricao, ev.numero_animal) and _dentro_periodo(ev.data_evento, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "lote":
        rows = session.exec(select(Lote)).all()
        out = [
            {"id": l.id, "titulo": f"{l.codigo} — {l.nome}", "subtitulo": l.status_lactacao or "—"}
            for l in rows if _contem(termo, l.codigo, l.nome)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "fornecedor":
        rows = session.exec(select(Fornecedor)).all()
        out = [
            {"id": f.id, "titulo": f.nome, "subtitulo": f"{f.tipo} · {f.categoria or '—'}"}
            for f in rows if _contem(termo, f.nome, f.tipo, f.categoria)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "motivo_movimentacao":
        rows = session.exec(select(MotivoMovimentacao)).all()
        out = [{"id": m.id, "titulo": m.nome, "subtitulo": "Ativo" if m.ativo else "Inativo"} for m in rows if _contem(termo, m.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "pessoa":
        rows = session.exec(select(Pessoa)).all()
        out = [{"id": p.id, "titulo": p.nome, "subtitulo": p.tipo} for p in rows if _contem(termo, p.nome, p.tipo)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "principio_ativo":
        rows = session.exec(select(PrincipioAtivo)).all()
        out = [{"id": p.id, "titulo": p.nome, "subtitulo": "Ativo" if p.ativo else "Inativo"} for p in rows if _contem(termo, p.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "doenca":
        rows = session.exec(select(Doenca)).all()
        out = [{"id": d.id, "titulo": d.nome, "subtitulo": "Ativo" if d.ativo else "Inativo"} for d in rows if _contem(termo, d.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "evento_sanitario":
        rows = session.exec(select(EventoSanitario)).all()
        out = [{"id": e.id, "titulo": e.nome, "subtitulo": "Ativo" if e.ativo else "Inativo"} for e in rows if _contem(termo, e.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "protocolo_sanitario":
        rows = session.exec(select(ProtocoloSanitario)).all()
        out = [
            {"id": p.id, "titulo": p.nome, "subtitulo": "Mastite" if p.eh_mastite else "—"}
            for p in rows if _contem(termo, p.nome)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo}")


def _alvos(tipo: str, id_: str, session: Session) -> tuple[list[str], list]:
    """Retorna (descrições do impacto, objetos que serão apagados)."""
    if tipo == "animal":
        animal = session.exec(select(Animal).where(Animal.numero == id_)).first()
        if not animal:
            raise HTTPException(status_code=404, detail="Animal não encontrado")
        servicos = session.exec(select(Servico).where(Servico.numero_matriz == id_)).all()
        partos = session.exec(select(Parto).where(Parto.numero_matriz == id_)).all()
        controles = session.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == id_)).all()
        sanidades = session.exec(select(Sanidade).where(Sanidade.numero_matriz == id_)).all()
        impacto = [f"Ficha do animal {id_}"]
        if servicos:
            impacto.append(f"{len(servicos)} serviço(s) de IA/cobertura")
        if partos:
            impacto.append(f"{len(partos)} parto(s)")
        if controles:
            impacto.append(f"{len(controles)} registro(s) de controle leiteiro")
        if sanidades:
            impacto.append(f"{len(sanidades)} aplicação(ões) de sanidade")
        return impacto, [animal, *servicos, *partos, *controles, *sanidades]

    if tipo == "servico":
        s = session.get(Servico, int(id_))
        if not s:
            raise HTTPException(status_code=404, detail="Serviço não encontrado")
        return [f"Serviço de {s.numero_matriz} em {_br(s.data_servico)}"], [s]

    if tipo == "parto":
        p = session.get(Parto, int(id_))
        if not p:
            raise HTTPException(status_code=404, detail="Parto não encontrado")
        return [f"Parto de {p.numero_matriz} em {_br(p.data_parto)}"], [p]

    if tipo == "controle":
        c = session.get(ControleLeiteiro, int(id_))
        if not c:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return [f"Controle leiteiro de {c.numero_matriz} em {_br(c.data_controle)}"], [c]

    if tipo == "sanidade":
        s = session.get(Sanidade, int(id_))
        if not s:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return [f"Aplicação de {s.produto} em {s.numero_matriz}"], [s]

    if tipo == "estoque":
        e = session.get(Estoque, int(id_))
        if not e:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        return [f'Item de estoque "{e.nome}"'], [e]

    if tipo == "evento_manual":
        ev = session.get(AgendaManual, int(id_))
        if not ev:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        return [f'Evento manual "{ev.descricao}" em {_br(ev.data_evento)}'], [ev]

    if tipo == "financeiro":
        c = session.get(ContaGerencial, int(id_))
        if not c:
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")
        itens = (
            session.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == c.numero_lancamento)).all()
            if c.numero_lancamento else []
        )
        if c.numero_lancamento and (c.parcela_total or 1) > 1:
            irmaos = session.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == c.numero_lancamento)
            ).all()
            impacto = [
                f"Lançamento {c.numero_lancamento} — {c.descricao or '—'}",
                f"{len(irmaos)} parcela(s) no total — todas serão excluídas",
            ]
            if itens:
                impacto.append(f"{len(itens)} produto(s)/serviço(s) lançados nesta nota")
            return impacto, [*irmaos, *itens]
        impacto = [f"Lançamento {c.numero_lancamento or ''} — {c.descricao or '—'} (R$ {c.valor_total or 0:,.2f})"]
        if itens:
            impacto.append(f"{len(itens)} produto(s)/serviço(s) lançados nesta nota")
        return impacto, [c, *itens]

    if tipo == "lote":
        lote = session.get(Lote, int(id_))
        if not lote:
            raise HTTPException(status_code=404, detail="Lote não encontrado")
        rotulo = f"{lote.codigo} - {lote.nome}"
        n_animais = len(session.exec(select(Animal).where(Animal.grupo_primario == rotulo)).all())
        impacto = [f"Lote {rotulo}"]
        if n_animais:
            impacto.append(f"{n_animais} animal(is) atualmente com esse lote no cadastro (não serão apagados, só ficam com um lote que não existe mais)")
        return impacto, [lote]

    if tipo == "fornecedor":
        fornecedor = session.get(Fornecedor, int(id_))
        if not fornecedor:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
        vinculados = session.exec(select(Estoque).where(Estoque.fornecedor_id == fornecedor.id)).all()
        impacto = [f"Fornecedor {fornecedor.nome}"]
        if vinculados:
            impacto.append(f"{len(vinculados)} item(ns) de estoque perderão o vínculo com este fornecedor")
            for item in vinculados:
                item.fornecedor_id = None
                session.add(item)
        return impacto, [fornecedor]

    if tipo == "motivo_movimentacao":
        motivo = session.get(MotivoMovimentacao, int(id_))
        if not motivo:
            raise HTTPException(status_code=404, detail="Motivo não encontrado")
        return [f"Motivo de movimentação {motivo.nome}"], [motivo]

    if tipo == "pessoa":
        pessoa = session.get(Pessoa, int(id_))
        if not pessoa:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        n_folha = len(session.exec(select(FolhaPagamento).where(FolhaPagamento.pessoa_id == pessoa.id)).all())
        n_vale = len(session.exec(select(ValeFuncionario).where(ValeFuncionario.pessoa_id == pessoa.id)).all())
        if n_folha or n_vale:
            raise HTTPException(
                status_code=400,
                detail=f"Não é possível excluir {pessoa.nome}: há {n_folha} lançamento(s) de folha e "
                       f"{n_vale} vale(s) registrados para essa pessoa. Exclua-os primeiro (aba Financeiro).",
            )
        return [f"Pessoa {pessoa.nome}"], [pessoa]

    if tipo == "principio_ativo":
        pa = session.get(PrincipioAtivo, int(id_))
        if not pa:
            raise HTTPException(status_code=404, detail="Princípio ativo não encontrado")
        vinculados = session.exec(select(CalendarioSanitario).where(CalendarioSanitario.principio_ativo_id == pa.id)).all()
        impacto = [f"Princípio ativo {pa.nome}"]
        if vinculados:
            impacto.append(f"{len(vinculados)} regra(s) do calendário sanitário perderão esse vínculo")
            for regra in vinculados:
                regra.principio_ativo_id = None
                session.add(regra)
        return impacto, [pa]

    if tipo == "doenca":
        doenca = session.get(Doenca, int(id_))
        if not doenca:
            raise HTTPException(status_code=404, detail="Doença não encontrada")
        n_calendario = session.exec(select(CalendarioSanitario).where(CalendarioSanitario.doenca_id == doenca.id)).all()
        n_protocolo = session.exec(select(ProtocoloSanitario).where(ProtocoloSanitario.doenca_id == doenca.id)).all()
        impacto = [f"Doença {doenca.nome}"]
        if n_calendario or n_protocolo:
            impacto.append(f"{len(n_calendario)} regra(s) do calendário e {len(n_protocolo)} protocolo(s) perderão esse vínculo")
            for regra in n_calendario:
                regra.doenca_id = None
                session.add(regra)
            for prot in n_protocolo:
                prot.doenca_id = None
                session.add(prot)
        return impacto, [doenca]

    if tipo == "evento_sanitario":
        evento = session.get(EventoSanitario, int(id_))
        if not evento:
            raise HTTPException(status_code=404, detail="Evento sanitário não encontrado")
        n_calendario = len(session.exec(select(CalendarioSanitario).where(CalendarioSanitario.evento_sanitario_id == evento.id)).all())
        if n_calendario:
            raise HTTPException(
                status_code=400,
                detail=f'Não é possível excluir "{evento.nome}": há {n_calendario} regra(s) do calendário '
                       "sanitário usando esse evento. Exclua-as primeiro.",
            )
        return [f"Evento sanitário {evento.nome}"], [evento]

    if tipo == "protocolo_sanitario":
        protocolo = session.get(ProtocoloSanitario, int(id_))
        if not protocolo:
            raise HTTPException(status_code=404, detail="Protocolo sanitário não encontrado")
        n_lancamentos = len(session.exec(
            select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.protocolo_id == protocolo.id)
        ).all())
        if n_lancamentos:
            raise HTTPException(
                status_code=400,
                detail=f'Não é possível excluir "{protocolo.nome}": há {n_lancamentos} lançamento(s) já feito(s) '
                       "com esse protocolo (histórico em Sanidade/Agenda).",
            )
        etapas = session.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == protocolo.id)).all()
        impacto = [f"Protocolo sanitário {protocolo.nome}"]
        if etapas:
            impacto.append(f"{len(etapas)} etapa(s) do protocolo")
        return impacto, [protocolo, *etapas]

    raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo}")


class ExclusaoIn(BaseModel):
    tipo: str
    id: str


@router.post("/impacto")
def impacto(dados: ExclusaoIn, session: Session = Depends(get_session)) -> dict:
    itens, _ = _alvos(dados.tipo, dados.id, session)
    return {"impacto": itens}


@router.post("/confirmar")
def confirmar(
    dados: ExclusaoIn,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Admin exclui na hora. Operador só registra uma solicitação pendente."""
    itens, alvos = _alvos(dados.tipo, dados.id, session)

    if user.papel == "admin":
        for obj in alvos:
            session.delete(obj)
        session.commit()
        return {"status": "excluido", "itens": itens}

    solicitacao = SolicitacaoExclusao(
        tipo=dados.tipo,
        id_alvo=dados.id,
        titulo=itens[0] if itens else f"{dados.tipo} #{dados.id}",
        solicitado_por=user.username,
    )
    session.add(solicitacao)
    session.commit()
    return {"status": "solicitado", "itens": itens}


@router.get("/pendentes", dependencies=[Depends(exigir_admin)])
def listar_pendentes(session: Session = Depends(get_session)) -> list[dict]:
    sols = session.exec(
        select(SolicitacaoExclusao)
        .where(SolicitacaoExclusao.status == "pendente")
        .order_by(SolicitacaoExclusao.criado_em.desc())
    ).all()
    return [s.model_dump() for s in sols]


@router.post("/pendentes/{sol_id}/aprovar", dependencies=[Depends(exigir_admin)])
def aprovar_pendente(
    sol_id: int,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    sol = session.get(SolicitacaoExclusao, sol_id)
    if not sol or sol.status != "pendente":
        raise HTTPException(status_code=404, detail="Solicitação não encontrada ou já decidida")

    _, alvos = _alvos(sol.tipo, sol.id_alvo, session)
    for obj in alvos:
        session.delete(obj)
    sol.status = "aprovada"
    sol.decidido_por = user.username
    sol.decidido_em = datetime.utcnow()
    session.add(sol)
    session.commit()
    return {"aprovado": True}


class RejeitarIn(BaseModel):
    motivo: str | None = None


@router.post("/pendentes/{sol_id}/rejeitar", dependencies=[Depends(exigir_admin)])
def rejeitar_pendente(
    sol_id: int,
    dados: RejeitarIn,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    sol = session.get(SolicitacaoExclusao, sol_id)
    if not sol or sol.status != "pendente":
        raise HTTPException(status_code=404, detail="Solicitação não encontrada ou já decidida")

    sol.status = "rejeitada"
    sol.decidido_por = user.username
    sol.decidido_em = datetime.utcnow()
    sol.motivo_rejeicao = dados.motivo
    session.add(sol)
    session.commit()
    return {"rejeitado": True}
