"""
Router de exclusões — apaga registros de qualquer tipo de lançamento com uma
prévia de impacto antes de confirmar.

Administradores excluem direto. Operadores só podem SOLICITAR a exclusão —
o pedido fica pendente até um administrador aprovar (executa a exclusão de
fato) ou rejeitar.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual,
    Animal,
    CalendarioSanitario,
    ComissaoCorretagem,
    CompraAnimal,
    CompraSemen,
    ContaGerencial,
    ControleLeiteiro,
    Doenca,
    Estoque,
    EstoqueSemen,
    EventoSanitario,
    FolhaPagamento,
    Fornecedor,
    LancamentoItem,
    Lote,
    MotivoMovimentacao,
    Parto,
    Pessoa,
    PrincipioAtivo,
    ProtocoloIatfAplicacao,
    ProtocoloIatfHormonio,
    ProtocoloIatfLancamento,
    ProtocoloSanitario,
    ProtocoloSanitarioAplicacao,
    ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento,
    Sanidade,
    Servico,
    SolicitacaoExclusao,
    Usuario,
    ValeFuncionario,
    VendaAnimal,
)

router = APIRouter(prefix="/exclusoes", tags=["exclusoes"])

TIPOS = [
    {"id": "animal", "label": "Animal (ficha)"},
    {"id": "servico", "label": "Serviço / IA (inclui diagnóstico)"},
    {"id": "parto", "label": "Parto / nascimento"},
    {"id": "controle", "label": "Controle leiteiro"},
    {"id": "sanidade", "label": "Sanidade"},
    {"id": "protocolo_sanitario_lancamento", "label": "Aplicação de protocolo sanitário (curativo/vacina)"},
    {"id": "protocolo_iatf_lancamento", "label": "Aplicação de protocolo hormonal (IATF)"},
    {"id": "financeiro", "label": "Financeiro"},
    {"id": "compra_animal", "label": "Compra de animal"},
    {"id": "compra_semen", "label": "Compra de sêmen"},
    {"id": "venda_animal", "label": "Venda de animal"},
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
    {"id": "calendario_sanitario", "label": "Evento do calendário sanitário"},
    {"id": "todos_lancamentos", "label": "Todos os lançamentos (mais recentes primeiro)"},
]

# Tipos "de lançamento" (têm data) reunidos na busca combinada "todos_lancamentos" —
# serve para achar algo que não constou em nenhuma das opções específicas acima.
SUBTIPOS_TODOS = [
    "servico", "parto", "controle", "sanidade",
    "protocolo_sanitario_lancamento", "protocolo_iatf_lancamento",
    "evento_manual", "financeiro", "compra_animal", "compra_semen", "venda_animal",
]


@router.get("/tipos")
def tipos() -> list[dict]:
    return sorted(TIPOS, key=lambda t: t["label"])


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


def _buscar_um(tipo: str, termo: str, data_inicio: str, data_fim: str, session: Session) -> list[dict]:
    """Lista candidatos a exclusão de um único tipo (sem o catch-all "todos_lancamentos"),
    filtrados por um termo de busca e, opcionalmente, por período. Cada item carrega um
    campo interno "_data" (para ordenação cronológica) que a rota pública remove antes
    de responder."""
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
                "_data": s.data_servico,
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
                "_data": p.data_parto,
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
                "_data": c.data_controle,
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
                "_data": s.data_aplicacao,
            }
            for s in rows
            if _contem(termo, s.numero_matriz, s.produto) and _dentro_periodo(s.data_aplicacao, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "protocolo_sanitario_lancamento":
        protocolos = {p.id: p.nome for p in session.exec(select(ProtocoloSanitario)).all()}
        rows = session.exec(select(ProtocoloSanitarioLancamento)).all()
        aplicacoes_por_lancamento: dict[int, list] = {}
        for ap in session.exec(select(ProtocoloSanitarioAplicacao)).all():
            aplicacoes_por_lancamento.setdefault(ap.lancamento_id, []).append(ap)
        out = []
        for l in rows:
            nome_protocolo = protocolos.get(l.protocolo_id, "—")
            aps = aplicacoes_por_lancamento.get(l.id, [])
            realizadas = sum(1 for a in aps if a.realizada)
            if not _contem(termo, l.numero_matriz, nome_protocolo, l.observacao):
                continue
            if not _dentro_periodo(l.data_inicio, data_inicio, data_fim):
                continue
            out.append({
                "id": l.id,
                "titulo": f"{l.numero_matriz} — {nome_protocolo} — {_br(l.data_inicio)}",
                "subtitulo": f"{realizadas}/{len(aps)} etapa(s) realizada(s)" + (f" · {l.observacao}" if l.observacao else ""),
                "_data": l.data_inicio,
            })
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "protocolo_iatf_lancamento":
        rows = session.exec(select(ProtocoloIatfLancamento)).all()
        aplicacoes_por_lancamento: dict[int, list] = {}
        for ap in session.exec(select(ProtocoloIatfAplicacao)).all():
            aplicacoes_por_lancamento.setdefault(ap.lancamento_id, []).append(ap)
        out = []
        for l in rows:
            aps = aplicacoes_por_lancamento.get(l.id, [])
            realizadas = sum(1 for a in aps if a.realizada)
            matrizes = sorted({a.numero_matriz for a in aps})
            if not _contem(termo, l.nome_protocolo, l.observacao, *matrizes):
                continue
            if not _dentro_periodo(l.data_d0, data_inicio, data_fim):
                continue
            out.append({
                "id": l.id,
                "titulo": f"{l.nome_protocolo or 'Protocolo IATF'} — D0 {_br(l.data_d0)}",
                "subtitulo": f"{len(matrizes)} animal(is) · {realizadas}/{len(aps)} etapa(s) realizada(s)",
                "_data": l.data_d0,
            })
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "financeiro":
        rows = session.exec(select(ContaGerencial)).all()
        out = [
            {
                "id": c.id,
                "titulo": f"{c.numero_lancamento or '(csv)'} — {c.descricao or '—'}",
                "subtitulo": f"R$ {c.valor_total or 0:,.2f} · {c.fornecedor_cliente or '—'}"
                + (f" · parcela {c.parcela_num}/{c.parcela_total}" if (c.parcela_total or 1) > 1 else ""),
                "_data": c.data_vencimento or c.data_competencia or c.data_emissao,
            }
            for c in rows
            if _contem(termo, c.numero_lancamento, c.descricao, c.fornecedor_cliente, c.numero_nota)
            and _dentro_periodo(
                c.data_vencimento or c.data_competencia or c.data_emissao, data_inicio, data_fim
            )
        ]
        return out[:200]

    if tipo == "compra_animal":
        rows = session.exec(select(CompraAnimal)).all()
        out = [
            {
                "id": c.id,
                "titulo": f"{c.numero_animal} — {c.vendedor} — {_br(c.data_compra)}",
                "subtitulo": f"R$ {c.valor or 0:,.2f} · lanç. {c.numero_lancamento_gerado or '—'}"
                + (f" · GTA {c.gta}" if c.gta else ""),
                "_data": c.data_compra,
            }
            for c in rows
            if _contem(termo, c.numero_animal, c.vendedor, c.numero_lancamento_gerado, c.gta)
            and _dentro_periodo(c.data_compra, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "venda_animal":
        rows = session.exec(select(VendaAnimal)).all()
        out = [
            {
                "id": v.id,
                "titulo": f"{v.numero_animal} — {v.comprador} — {_br(v.data_venda)}",
                "subtitulo": f"R$ {v.valor or 0:,.2f} · lanç. {v.numero_lancamento_gerado or '—'}"
                + (f" · GTA {v.gta}" if v.gta else ""),
                "_data": v.data_venda,
            }
            for v in rows
            if _contem(termo, v.numero_animal, v.comprador, v.numero_lancamento_gerado, v.gta)
            and _dentro_periodo(v.data_venda, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

    if tipo == "compra_semen":
        rows = session.exec(select(CompraSemen)).all()
        out = [
            {
                "id": c.id,
                "titulo": f"{c.touro_nome} — {c.vendedor} — {_br(c.data_compra)}",
                "subtitulo": f"{c.doses} dose(s) · R$ {c.valor_unitario or 0:,.2f}/dose · lanç. {c.numero_lancamento_gerado or '—'}",
                "_data": c.data_compra,
            }
            for c in rows
            if _contem(termo, c.touro_nome, c.naab, c.vendedor, c.numero_lancamento_gerado)
            and _dentro_periodo(c.data_compra, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]

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
                "_data": ev.data_evento,
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
        out = [{"id": p.id, "titulo": p.nome, "subtitulo": (p.tipo or "").replace(",", ", ")} for p in rows if _contem(termo, p.nome, p.tipo)]
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

    if tipo == "calendario_sanitario":
        eventos = {e.id: e.nome for e in session.exec(select(EventoSanitario)).all()}
        doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
        rows = session.exec(select(CalendarioSanitario)).all()
        out = [
            {"id": c.id,
             "titulo": f"{eventos.get(c.evento_sanitario_id, '—')} — {_br(c.data_evento)}",
             "subtitulo": f"{c.categoria_alvo or 'rebanho'} · a cada {c.frequencia_valor} {c.frequencia_unidade}"}
            for c in rows
            if _contem(termo, eventos.get(c.evento_sanitario_id), c.categoria_alvo, c.produto, doencas.get(c.doenca_id))
            and _dentro_periodo(c.data_evento, data_inicio, data_fim)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo}")


@router.get("/buscar")
def buscar(
    tipo: str = Query(...),
    termo: str = Query(""),
    data_inicio: str = Query(""),
    data_fim: str = Query(""),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Lista candidatos a exclusão. O tipo especial "todos_lancamentos" combina todos os
    tipos de lançamento com data (serviço, parto, controle, sanidade, protocolos, evento
    manual, financeiro) numa única lista em ordem decrescente — para achar um registro que
    não constou em nenhuma das opções específicas. Cada item carrega "tipo_real" para que
    a exclusão seja roteada ao tipo de origem de fato."""
    if tipo != "todos_lancamentos":
        out = _buscar_um(tipo, termo, data_inicio, data_fim, session)
        for item in out:
            item.pop("_data", None)
        return out

    combinados: list[dict] = []
    for subtipo in SUBTIPOS_TODOS:
        for item in _buscar_um(subtipo, termo, data_inicio, data_fim, session):
            item["tipo_real"] = subtipo
            combinados.append(item)

    combinados.sort(key=lambda x: x.get("_data") or date.min, reverse=True)
    for item in combinados:
        item.pop("_data", None)
    return combinados[:300]


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

    if tipo == "protocolo_sanitario_lancamento":
        lancamento = session.get(ProtocoloSanitarioLancamento, int(id_))
        if not lancamento:
            raise HTTPException(status_code=404, detail="Lançamento de protocolo não encontrado")
        aplicacoes = session.exec(
            select(ProtocoloSanitarioAplicacao).where(ProtocoloSanitarioAplicacao.lancamento_id == lancamento.id)
        ).all()
        # Registros de Sanidade gerados ao confirmar cada etapa — vinculados pela FK
        # (lançamentos criados após esta correção) ou, em lançamentos mais antigos sem
        # o vínculo, localizados heuristicamente por matriz + prefixo do texto de
        # observação que a confirmação grava ("Protocolo sanitário — D...").
        sanidades = session.exec(
            select(Sanidade).where(Sanidade.protocolo_sanitario_lancamento_id == lancamento.id)
        ).all()
        if not sanidades:
            candidatas = session.exec(
                select(Sanidade).where(
                    Sanidade.numero_matriz == lancamento.numero_matriz,
                    Sanidade.data_aplicacao >= lancamento.data_inicio,
                )
            ).all()
            sanidades = [s for s in candidatas if (s.obs or "").startswith("Protocolo sanitário — D")]
        protocolo = session.get(ProtocoloSanitario, lancamento.protocolo_id)
        impacto = [f"Lançamento do protocolo {protocolo.nome if protocolo else '—'} em {lancamento.numero_matriz} ({_br(lancamento.data_inicio)})"]
        if aplicacoes:
            impacto.append(f"{len(aplicacoes)} etapa(s) do protocolo (agenda)")
        if sanidades:
            impacto.append(f"{len(sanidades)} aplicação(ões) já registrada(s) em Sanidade")
        return impacto, [lancamento, *aplicacoes, *sanidades]

    if tipo == "protocolo_iatf_lancamento":
        lancamento = session.get(ProtocoloIatfLancamento, int(id_))
        if not lancamento:
            raise HTTPException(status_code=404, detail="Lançamento de protocolo IATF não encontrado")
        aplicacoes = session.exec(
            select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lancamento.id)
        ).all()
        hormonios = session.exec(
            select(ProtocoloIatfHormonio).where(ProtocoloIatfHormonio.lancamento_id == lancamento.id)
        ).all()
        sanidades = session.exec(
            select(Sanidade).where(Sanidade.protocolo_iatf_lancamento_id == lancamento.id)
        ).all()
        if not sanidades:
            matrizes = {a.numero_matriz for a in aplicacoes}
            candidatas = session.exec(
                select(Sanidade).where(
                    Sanidade.data_aplicacao >= lancamento.data_d0,
                )
            ).all()
            sanidades = [
                s for s in candidatas
                if s.numero_matriz in matrizes and (s.obs or "").startswith("Protocolo IATF — D")
            ]
        impacto = [f"Lançamento do protocolo IATF {lancamento.nome_protocolo or ''} — D0 {_br(lancamento.data_d0)}"]
        if aplicacoes:
            impacto.append(f"{len(aplicacoes)} aplicação(ões) programada(s) (agenda), {len({a.numero_matriz for a in aplicacoes})} animal(is)")
        if sanidades:
            impacto.append(f"{len(sanidades)} aplicação(ões) já registrada(s) em Sanidade")
        return impacto, [lancamento, *aplicacoes, *hormonios, *sanidades]

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

    if tipo == "compra_animal":
        c = session.get(CompraAnimal, int(id_))
        if not c:
            raise HTTPException(status_code=404, detail="Compra de animal não encontrada")
        impacto = [f"Compra do animal {c.numero_animal} — {c.vendedor} — {_br(c.data_compra)} (R$ {c.valor or 0:,.2f})"]
        objetos: list = [c]
        irmaos = (
            session.exec(select(CompraAnimal).where(CompraAnimal.numero_lancamento_gerado == c.numero_lancamento_gerado)).all()
            if c.numero_lancamento_gerado else [c]
        )
        if len(irmaos) > 1:
            impacto.append(
                f"Faz parte de uma compra em lote com mais {len(irmaos) - 1} animal(is) — o lançamento "
                "financeiro e a comissão (se houver) continuam intactos, pois ainda valem para os demais animais."
            )
        else:
            contas = (
                session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == c.numero_lancamento_gerado)).all()
                if c.numero_lancamento_gerado else []
            )
            comissoes = (
                session.exec(select(ComissaoCorretagem).where(ComissaoCorretagem.numero_lancamento == c.numero_lancamento_gerado)).all()
                if c.numero_lancamento_gerado else []
            )
            contas_comissao = []
            for co in comissoes:
                contas_comissao += session.exec(
                    select(ContaGerencial).where(ContaGerencial.numero_lancamento == co.numero_lancamento_comissao)
                ).all()
            if contas:
                impacto.append(f"Lançamento financeiro {c.numero_lancamento_gerado} (R$ {sum(x.valor_total or 0 for x in contas):,.2f})")
            if comissoes:
                impacto.append(f"{len(comissoes)} comissão(ões) de corretagem vinculada(s)")
            objetos += [*contas, *comissoes, *contas_comissao]
        return impacto, objetos

    if tipo == "venda_animal":
        v = session.get(VendaAnimal, int(id_))
        if not v:
            raise HTTPException(status_code=404, detail="Venda de animal não encontrada")
        impacto = [f"Venda do animal {v.numero_animal} — {v.comprador} — {_br(v.data_venda)} (R$ {v.valor or 0:,.2f})"]
        objetos: list = [v]
        irmaos = (
            session.exec(select(VendaAnimal).where(VendaAnimal.numero_lancamento_gerado == v.numero_lancamento_gerado)).all()
            if v.numero_lancamento_gerado else [v]
        )
        if len(irmaos) > 1:
            impacto.append(
                f"Faz parte de uma venda em lote com mais {len(irmaos) - 1} animal(is) — o lançamento "
                "financeiro e a comissão (se houver) continuam intactos, pois ainda valem para os demais animais."
            )
        else:
            contas = (
                session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == v.numero_lancamento_gerado)).all()
                if v.numero_lancamento_gerado else []
            )
            comissoes = (
                session.exec(select(ComissaoCorretagem).where(ComissaoCorretagem.numero_lancamento == v.numero_lancamento_gerado)).all()
                if v.numero_lancamento_gerado else []
            )
            contas_comissao = []
            for co in comissoes:
                contas_comissao += session.exec(
                    select(ContaGerencial).where(ContaGerencial.numero_lancamento == co.numero_lancamento_comissao)
                ).all()
            if contas:
                impacto.append(f"Lançamento financeiro {v.numero_lancamento_gerado} (R$ {sum(x.valor_total or 0 for x in contas):,.2f})")
            if comissoes:
                impacto.append(f"{len(comissoes)} comissão(ões) de corretagem vinculada(s)")
            objetos += [*contas, *comissoes, *contas_comissao]
        return impacto, objetos

    if tipo == "compra_semen":
        c = session.get(CompraSemen, int(id_))
        if not c:
            raise HTTPException(status_code=404, detail="Compra de sêmen não encontrada")
        impacto = [f"Compra de {c.doses} dose(s) de sêmen — {c.touro_nome} — {c.vendedor} — {_br(c.data_compra)} (R$ {c.valor_unitario or 0:,.2f}/dose)"]
        objetos: list = [c]
        estoque = session.get(EstoqueSemen, c.estoque_semen_id)
        if estoque:
            impacto.append(f"{c.doses} dose(s) serão subtraídas do estoque de sêmen de {estoque.touro_nome} (saldo atual: {estoque.doses})")
            estoque.doses = estoque.doses - c.doses
            session.add(estoque)
        # Uma compra pode ter vários touros/sêmens lançados na mesma nota
        # (mesmo numero_lancamento_gerado) — o lançamento financeiro só é
        # apagado junto quando este é o ÚLTIMO item daquela nota; do
        # contrário, ele continua valendo para os itens irmãos restantes.
        irmaos = (
            session.exec(select(CompraSemen).where(CompraSemen.numero_lancamento_gerado == c.numero_lancamento_gerado)).all()
            if c.numero_lancamento_gerado else [c]
        )
        if len(irmaos) > 1:
            impacto.append(
                f"Faz parte de uma compra com mais {len(irmaos) - 1} sêmen/touro(s) na mesma nota — o "
                "lançamento financeiro continua intacto, pois ainda vale para os demais itens."
            )
        else:
            contas = (
                session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == c.numero_lancamento_gerado)).all()
                if c.numero_lancamento_gerado else []
            )
            if contas:
                impacto.append(f"Lançamento financeiro {c.numero_lancamento_gerado} (R$ {sum(x.valor_total or 0 for x in contas):,.2f})")
            objetos += contas
        return impacto, objetos

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

    if tipo == "calendario_sanitario":
        c = session.get(CalendarioSanitario, int(id_))
        if not c:
            raise HTTPException(status_code=404, detail="Regra do calendário sanitário não encontrada")
        evento = session.get(EventoSanitario, c.evento_sanitario_id)
        nome = evento.nome if evento else "evento"
        return [f"Evento do calendário sanitário: {nome} — {_br(c.data_evento)}"], [c]

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
