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

from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.rules import estoque_baixa
from fazenda.rules import lactacao as regras_lactacao
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.exclusao_tipos import REGISTRO
from fazenda.rules.exclusao_tipos._base import _br, _contem, _dentro_periodo
from fazenda.rules.vale_item import eh_item_de_vale
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
    Lactacao,
    LancamentoItem,
    Lote,
    MotivoMovimentacao,
    MovimentoEstoque,
    Parto,
    PesagemCorporal,
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
    Secagem,
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

# Tipos "de cadastro" (sem data intrínseca) entre os hardcoded em TIPOS —
# espelha o que era a constante TIPOS_SEM_DATA em FormExclusao.tsx antes de
# GET /tipos virar a fonte da verdade (ver `tipos()` abaixo). Tipo novo
# registrado via `rules/exclusao_tipos` declara isso no próprio
# `TipoExclusao.sem_filtro_data` — não precisa entrar aqui.
_TIPOS_SEM_DATA_LEGADO = {
    "animal", "estoque", "lote", "fornecedor", "motivo_movimentacao", "pessoa",
    "principio_ativo", "doenca", "evento_sanitario", "protocolo_sanitario",
}


@router.get("/tipos")
def tipos() -> list[dict]:
    legados = [{**t, "sem_filtro_data": t["id"] in _TIPOS_SEM_DATA_LEGADO} for t in TIPOS]
    novos = [{"id": t.id, "label": t.label, "sem_filtro_data": t.sem_filtro_data} for t in REGISTRO.values()]
    return sorted(legados + novos, key=lambda t: t["label"])


def _buscar_um(
    tipo: str, termo: str, data_inicio: str, data_fim: str, session: Session,
    fazenda_id: int | None = None,
) -> list[dict]:
    """Lista candidatos a exclusão de um único tipo (sem o catch-all "todos_lancamentos"),
    filtrados por um termo de busca e, opcionalmente, por período. Cada item carrega um
    campo interno "_data" (para ordenação cronológica) que a rota pública remove antes
    de responder."""
    if tipo in REGISTRO:
        return REGISTRO[tipo].buscar(
            termo=termo, data_inicio=data_inicio, data_fim=data_fim, session=session, fazenda_id=fazenda_id,
        )

    if tipo == "animal":
        query = select(Animal)
        if fazenda_id is not None:
            query = query.where(Animal.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [
            {"id": a.numero, "titulo": a.numero, "subtitulo": f"{a.categoria_abrev or a.categoria_completa or '—'} · {a.grupo_primario or '—'}"}
            for a in rows if _contem(termo, a.numero, a.grupo_primario, a.categoria_completa)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "servico":
        query = select(Servico)
        if fazenda_id is not None:
            query = query.where(Servico.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(Parto)
        if fazenda_id is not None:
            query = query.where(Parto.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(ControleLeiteiro)
        if fazenda_id is not None:
            query = query.where(ControleLeiteiro.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(Sanidade)
        if fazenda_id is not None:
            query = query.where(Sanidade.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(ProtocoloSanitarioLancamento)
        if fazenda_id is not None:
            query = query.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(ProtocoloIatfLancamento)
        if fazenda_id is not None:
            query = query.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(ContaGerencial)
        if fazenda_id is not None:
            query = query.where(ContaGerencial.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(CompraAnimal)
        if fazenda_id is not None:
            query = query.where(CompraAnimal.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(VendaAnimal)
        if fazenda_id is not None:
            query = query.where(VendaAnimal.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(CompraSemen)
        if fazenda_id is not None:
            query = query.where(CompraSemen.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
        query = select(Estoque)
        if fazenda_id is not None:
            query = query.where(Estoque.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [
            {"id": e.id, "titulo": e.nome, "subtitulo": f"{e.quantidade or 0} {e.unidade or ''}"}
            for e in rows if _contem(termo, e.nome)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "evento_manual":
        query = select(AgendaManual)
        if fazenda_id is not None:
            query = query.where(AgendaManual.fazenda_id.in_((fazenda_id, None)))
        rows = session.exec(query).all()
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
        query = select(Lote)
        if fazenda_id is not None:
            query = query.where(Lote.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [
            {"id": l.id, "titulo": f"{l.codigo} — {l.nome}", "subtitulo": l.status_lactacao or "—"}
            for l in rows if _contem(termo, l.codigo, l.nome)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "fornecedor":
        query = select(Fornecedor)
        if fazenda_id is not None:
            query = query.where(Fornecedor.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [
            {"id": f.id, "titulo": f.nome, "subtitulo": f"{f.tipo} · {f.categoria or '—'}"}
            for f in rows if _contem(termo, f.nome, f.tipo, f.categoria)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "motivo_movimentacao":
        query = select(MotivoMovimentacao)
        if fazenda_id is not None:
            query = query.where(MotivoMovimentacao.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [{"id": m.id, "titulo": m.nome, "subtitulo": "Ativo" if m.ativo else "Inativo"} for m in rows if _contem(termo, m.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "pessoa":
        query = select(Pessoa)
        if fazenda_id is not None:
            query = query.where(Pessoa.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [{"id": p.id, "titulo": p.nome, "subtitulo": (p.tipo or "").replace(",", ", ")} for p in rows if _contem(termo, p.nome, p.tipo)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "principio_ativo":
        query = select(PrincipioAtivo)
        if fazenda_id is not None:
            query = query.where(PrincipioAtivo.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [{"id": p.id, "titulo": p.nome, "subtitulo": "Ativo" if p.ativo else "Inativo"} for p in rows if _contem(termo, p.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "doenca":
        query = select(Doenca)
        if fazenda_id is not None:
            query = query.where(Doenca.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [{"id": d.id, "titulo": d.nome, "subtitulo": "Ativo" if d.ativo else "Inativo"} for d in rows if _contem(termo, d.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "evento_sanitario":
        query = select(EventoSanitario)
        if fazenda_id is not None:
            query = query.where(EventoSanitario.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [{"id": e.id, "titulo": e.nome, "subtitulo": "Ativo" if e.ativo else "Inativo"} for e in rows if _contem(termo, e.nome)]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "protocolo_sanitario":
        query = select(ProtocoloSanitario)
        if fazenda_id is not None:
            query = query.where(ProtocoloSanitario.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
        out = [
            {"id": p.id, "titulo": p.nome, "subtitulo": "Mastite" if p.eh_mastite else "—"}
            for p in rows if _contem(termo, p.nome)
        ]
        return sorted(out, key=lambda x: x["titulo"])[:200]

    if tipo == "calendario_sanitario":
        eventos = {e.id: e.nome for e in session.exec(select(EventoSanitario)).all()}
        doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
        query = select(CalendarioSanitario)
        if fazenda_id is not None:
            query = query.where(CalendarioSanitario.fazenda_id == fazenda_id)
        rows = session.exec(query).all()
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lista candidatos a exclusão. O tipo especial "todos_lancamentos" combina todos os
    tipos de lançamento com data (serviço, parto, controle, sanidade, protocolos, evento
    manual, financeiro) numa única lista em ordem decrescente — para achar um registro que
    não constou em nenhuma das opções específicas. Cada item carrega "tipo_real" para que
    a exclusão seja roteada ao tipo de origem de fato."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if tipo != "todos_lancamentos":
        out = _buscar_um(tipo, termo, data_inicio, data_fim, session, fazenda_id=fazenda_id)
        for item in out:
            item.pop("_data", None)
        return out

    combinados: list[dict] = []
    for subtipo in SUBTIPOS_TODOS:
        for item in _buscar_um(subtipo, termo, data_inicio, data_fim, session, fazenda_id=fazenda_id):
            item["tipo_real"] = subtipo
            combinados.append(item)

    combinados.sort(key=lambda x: x.get("_data") or date.min, reverse=True)
    for item in combinados:
        item.pop("_data", None)
    return combinados[:300]


def _alvos(tipo: str, id_: str, session: Session, fazenda_id: int | None = None) -> tuple[list[str], list]:
    """Retorna (descrições do impacto, objetos que serão apagados)."""
    if tipo in REGISTRO:
        return REGISTRO[tipo].alvos(id_=id_, session=session, fazenda_id=fazenda_id)

    if tipo == "animal":
        query_animal = select(Animal).where(Animal.numero == id_)
        if fazenda_id is not None:
            query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        animal = session.exec(query_animal).first()
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
        if not s or (fazenda_id is not None and s.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Serviço não encontrado")
        return [f"Serviço de {s.numero_matriz} em {_br(s.data_servico)}"], [s]

    if tipo == "parto":
        p = session.get(Parto, int(id_))
        if not p or (fazenda_id is not None and p.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Parto não encontrado")
        impacto = [f"Parto de {p.numero_matriz} em {_br(p.data_parto)}"]
        alvos: list = [p]

        # Retenção de placenta gera um item na Agenda no dia do parto (ver
        # registrar_parto) sem guardar o parto_id — mesma heurística por
        # matriz/data/prefixo do texto já usada acima para o mirror de
        # Sanidade dos protocolos.
        agendas = session.exec(
            select(AgendaManual).where(
                AgendaManual.numero_animal == p.numero_matriz, AgendaManual.data_evento == p.data_parto,
                AgendaManual.descricao.startswith(f"Retenção de placenta — vaca {p.numero_matriz}"),
            )
        ).all()
        if agendas:
            impacto.append(f"{len(agendas)} pendência(s) de retenção de placenta na Agenda")
            alvos.extend(agendas)

        # Crias cadastradas por ESTE parto (ver registrar_parto) — só entram
        # na exclusão se ainda não ganharam vida própria no sistema (nenhum
        # outro registro as referencia). Uma cria que já tem pesagem, IA,
        # sanidade etc. lançada fica: apagar a ficha destruiria histórico
        # real só porque o parto que a originou foi corrigido/apagado.
        numeros_crias = [n for n in (p.numero_cria_1, p.numero_cria_2) if n]
        crias_orfas = []
        for numero_cria in numeros_crias:
            query_cria = select(Animal).where(Animal.numero == numero_cria)
            if fazenda_id is not None:
                query_cria = query_cria.where(Animal.fazenda_id == fazenda_id)
            cria = session.exec(query_cria).first()
            if cria is None:
                continue
            tem_outros_registros = any([
                session.exec(select(Servico).where(Servico.numero_matriz == numero_cria)).first(),
                session.exec(select(Parto).where(Parto.numero_matriz == numero_cria)).first(),
                session.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == numero_cria)).first(),
                session.exec(select(Sanidade).where(Sanidade.numero_matriz == numero_cria)).first(),
                session.exec(select(PesagemCorporal).where(PesagemCorporal.numero_matriz == numero_cria)).first(),
            ])
            if not tem_outros_registros:
                crias_orfas.append(cria)
        if crias_orfas:
            impacto.append(f"{len(crias_orfas)} ficha(s) de cria sem nenhum outro registro (nascida só por este parto)")
            alvos.extend(crias_orfas)

        return impacto, alvos

    if tipo == "controle":
        c = session.get(ControleLeiteiro, int(id_))
        if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return [f"Controle leiteiro de {c.numero_matriz} em {_br(c.data_controle)}"], [c]

    if tipo == "sanidade":
        s = session.get(Sanidade, int(id_))
        if not s or (fazenda_id is not None and s.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return [f"Aplicação de {s.produto} em {s.numero_matriz}"], [s]

    if tipo == "protocolo_sanitario_lancamento":
        lancamento = session.get(ProtocoloSanitarioLancamento, int(id_))
        if not lancamento or (fazenda_id is not None and lancamento.fazenda_id != fazenda_id):
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
        if not lancamento or (fazenda_id is not None and lancamento.fazenda_id != fazenda_id):
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
        if not e or (fazenda_id is not None and e.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Item não encontrado")
        return [f'Item de estoque "{e.nome}"'], [e]

    if tipo == "evento_manual":
        ev = session.get(AgendaManual, int(id_))
        if not ev or (fazenda_id is not None and ev.fazenda_id not in (fazenda_id, None)):
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        return [f'Evento manual "{ev.descricao}" em {_br(ev.data_evento)}'], [ev]

    if tipo == "financeiro":
        c = session.get(ContaGerencial, int(id_))
        if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")
        itens = (
            session.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == c.numero_lancamento)).all()
            if c.numero_lancamento else []
        )
        n_itens_vale = sum(1 for it in itens if eh_item_de_vale(it))
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
            if n_itens_vale:
                impacto.append(f"{n_itens_vale} item(ns) desta nota geraram vale — o(s) vale(s) também será(ão) excluído(s)")
            return impacto, [*irmaos, *itens]
        impacto = [f"Lançamento {c.numero_lancamento or ''} — {c.descricao or '—'} (R$ {c.valor_total or 0:,.2f})"]
        if itens:
            impacto.append(f"{len(itens)} produto(s)/serviço(s) lançados nesta nota")
        if n_itens_vale:
            impacto.append(f"{n_itens_vale} item(ns) desta nota geraram vale — o(s) vale(s) também será(ão) excluído(s)")
        return impacto, [c, *itens]

    if tipo == "compra_animal":
        c = session.get(CompraAnimal, int(id_))
        if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
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
        if not v or (fazenda_id is not None and v.fazenda_id != fazenda_id):
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
        if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Compra de sêmen não encontrada")
        impacto = [f"Compra de {c.doses} dose(s) de sêmen — {c.touro_nome} — {c.vendedor} — {_br(c.data_compra)} (R$ {c.valor_unitario or 0:,.2f}/dose)"]
        objetos: list = [c]
        estoque = session.get(EstoqueSemen, c.estoque_semen_id)
        if estoque:
            impacto.append(f"{c.doses} dose(s) serão subtraídas do estoque de sêmen de {estoque.touro_nome} (saldo atual: {estoque.doses})")
            # Mesmo motor de todo o resto (`estoque_baixa`), não um ajuste
            # direto no campo: sem isso, esta baixa não deixava rastro em
            # MovimentoEstoque — nem no histórico, nem no custo físico do
            # RMCA. A compra original foi uma ENTRADA; o estorno é uma SAÍDA
            # (sinal=-1), não uma "Aplicação" (que seria consumo real).
            estoque_baixa.movimentar_dose_semen(
                session, touro=estoque, doses=c.doses, data=date.today(), fazenda_id=fazenda_id,
                usuario_id=None, movimento="Saída de ajuste", sinal=-1,
                observacao=f"Estorno por exclusão da compra de sêmen #{c.id} ({c.touro_nome})",
                origem_tipo="estorno_compra_semen", origem_id=c.id,
            )
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
        if not lote or (fazenda_id is not None and lote.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Lote não encontrado")
        rotulo = f"{lote.codigo} - {lote.nome}"
        n_animais = len(session.exec(select(Animal).where(Animal.grupo_primario == rotulo)).all())
        impacto = [f"Lote {rotulo}"]
        if n_animais:
            impacto.append(f"{n_animais} animal(is) atualmente com esse lote no cadastro (não serão apagados, só ficam com um lote que não existe mais)")
        return impacto, [lote]

    if tipo == "fornecedor":
        fornecedor = session.get(Fornecedor, int(id_))
        if not fornecedor or (fazenda_id is not None and fornecedor.fazenda_id != fazenda_id):
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
        if not motivo or (fazenda_id is not None and motivo.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Motivo não encontrado")
        return [f"Motivo de movimentação {motivo.nome}"], [motivo]

    if tipo == "pessoa":
        pessoa = session.get(Pessoa, int(id_))
        if not pessoa or (fazenda_id is not None and pessoa.fazenda_id != fazenda_id):
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
        if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
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
        if not doenca or (fazenda_id is not None and doenca.fazenda_id != fazenda_id):
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
        if not evento or (fazenda_id is not None and evento.fazenda_id != fazenda_id):
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
        if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
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
        if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Regra do calendário sanitário não encontrada")
        evento = session.get(EventoSanitario, c.evento_sanitario_id)
        nome = evento.nome if evento else "evento"
        return [f"Evento do calendário sanitário: {nome} — {_br(c.data_evento)}"], [c]

    raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo}")


# Mapeia a classe de um objeto que será apagado para o(s) `origem_tipo` que
# ELE PRÓPRIO pode ter gravado em MovimentoEstoque (origem_id == obj.id) — ver
# rules/estoque_baixa.py e os pontos de baixa em agenda.py/sanidade.py/
# reproducao.py. Só entram aqui classes cujo MovimentoEstoque referencia o
# próprio id do objeto; ex.: ProtocoloIatfAplicacao NÃO entra porque a baixa
# do protocolo IATF é gravada com origem_id=lancamento_id (ver
# agenda.py::_marcar_protocolo_iatf_realizado), não o id de cada aplicação —
# por isso é ProtocoloIatfLancamento quem entra no mapa. Isso também evita
# duplo estorno "de graça": ao excluir protocolo_sanitario_lancamento, os
# registros de Sanidade espelhados (mirror) vêm junto na lista de alvos, mas
# a baixa real está presa ao id da ProtocoloSanitarioAplicacao (origem_tipo=
# "protocolo_sanitario") — o mirror de Sanidade nunca tem MovimentoEstoque
# com origem_id igual ao seu próprio id, então a busca abaixo não acha nada
# pra ele e não reverte a mesma baixa duas vezes.
_ORIGENS_POR_CLASSE: dict[type, list[str]] = {
    # Aplicação avulsa em Sanidade + os três fluxos que também geram uma
    # Sanidade 1-para-1 com a baixa (vacina pré-parto, BST, secagem) — todos
    # gravam origem_id=sanidade.id. (Exceção conhecida: quando a mesma
    # Sanidade "avulsa" nasce de POST /sanidade/aplicacoes para VÁRIOS
    # animais de uma vez, só a última linha do lote carrega o origem_id —
    # limitação preexistente do registro em lote, não introduzida aqui.)
    Sanidade: ["sanidade", "vacina_pre_parto", "bst", "secagem"],
    ProtocoloSanitarioAplicacao: ["protocolo_sanitario"],
    ProtocoloIatfLancamento: ["iatf"],
    Servico: ["ia_semen"],
    # Compra de produto estocável lançada em Financeiro dá ENTRADA automática
    # no estoque (sinal=+1, ver financeiro.py::criar_lancamento) — diferente
    # dos demais casos acima (que são baixas/consumo, sinal=-1). Por isso o
    # estorno abaixo trata "Entrada de compra" à parte: precisa SUBTRAIR a
    # quantidade de volta, não devolver.
    LancamentoItem: ["compra_financeiro"],
}


def _devolver_dose_semen_do_movimento(
    session: Session, mov: MovimentoEstoque, fazenda_id: int | None, observacao: str,
) -> list[str]:
    """Localiza o EstoqueSemen que a baixa de `mov` (origem_tipo="ia_semen")
    descontou e devolve a dose — MovimentoEstoque não guarda o id do touro
    diretamente, só o nome (`nome_item`) e, quando existe um item de Estoque
    espelhado, o `estoque_id` dele (ver estoque_baixa.baixar_dose_semen)."""
    touro = None
    if mov.estoque_id is not None:
        item_espelho = session.get(Estoque, mov.estoque_id)
        if item_espelho is not None and item_espelho.estoque_semen_id is not None:
            touro = session.get(EstoqueSemen, item_espelho.estoque_semen_id)
    if touro is None:
        query = select(EstoqueSemen).where(EstoqueSemen.touro_nome == mov.nome_item)
        if fazenda_id is not None:
            query = query.where(EstoqueSemen.fazenda_id == fazenda_id)
        touro = session.exec(query).first()
    if touro is None:
        return [f'Não foi possível localizar o estoque de sêmen de "{mov.nome_item}" para devolver {mov.quantidade:g} dose(s).']
    return estoque_baixa.devolver_dose_semen(
        session, touro=touro, doses=mov.quantidade, data=date.today(), fazenda_id=fazenda_id,
        observacao=observacao, origem_tipo=f"estorno_{mov.origem_tipo}", origem_id=mov.origem_id,
    )


def _desvincular_vales_dos_alvos(session: Session, alvos: list, fazenda_id: int | None) -> None:
    """Antes de excluir, reverte o(s) vale(s) de qualquer LancamentoItem em
    `alvos` que tenha virado vale (checkbox "É vale de funcionário?", ver
    fazenda/api/routers/cadastro/rh_vale_item.py) — sem isso, excluir a nota
    deixaria ValeParcela/ValeAvulsoAbatimento órfãos e a parcela da
    empreitada/contrato abatida para sempre. Import local: exclusoes.py não
    precisa (nem deve) importar cadastro no topo do módulo."""
    from fazenda.api.routers.cadastro.rh_vale_item import desvincular_vale_do_item

    for obj in alvos:
        if isinstance(obj, LancamentoItem) and eh_item_de_vale(obj):
            desvincular_vale_do_item(session, obj, excluir_vale=True, fazenda_id=fazenda_id)


def _restaurar_ult_ocorrencia_dos_alvos(session: Session, alvos: list, fazenda_id: int | None) -> None:
    """Antes de excluir, se algum Servico em `alvos` é o "vigente" do animal
    (ult_ocorrencia=1 — ver reproducao.py::registrar_servico/registrar_servico_lote,
    que zera o flag de todo serviço anterior ao criar um novo), promove o
    serviço anterior mais recente que sobrar a vigente. Sem isso, excluir a
    IA/cobertura mais recente de um animal deixa NENHUM serviço marcado como
    vigente — quebra o diagnóstico "atual" usado pela Agenda Reprodutiva e
    pela sugestão de candidatas a IATF (ver diag_por_animal em reproducao.py)."""
    excluidos = {obj.id for obj in alvos if isinstance(obj, Servico)}
    matrizes = {obj.numero_matriz for obj in alvos if isinstance(obj, Servico) and obj.ult_ocorrencia == 1}
    for matriz in matrizes:
        query = select(Servico).where(Servico.numero_matriz == matriz)
        if fazenda_id is not None:
            query = query.where(Servico.fazenda_id == fazenda_id)
        restantes = [s for s in session.exec(query).all() if s.id not in excluidos]
        if not restantes:
            continue
        mais_recente = max(restantes, key=lambda s: (s.data_servico or date.min, s.id))
        mais_recente.ult_ocorrencia = 1
        session.add(mais_recente)


def _reverter_perda_prenhez_causada_pelos_alvos(session: Session, alvos: list, fazenda_id: int | None) -> None:
    """Um Servico excluído pode ter sido a NOVA inseminação que disparou a
    detecção automática de perda de prenhez no serviço anterior (ver
    `Servico.perda_causada_por_servico_id` e
    `fazenda.rules.perda_prenhez.detectar_e_registrar_perda_por_reinseminacao`)
    — sem isso, excluir essa inseminação (ex.: lançamento em duplicidade)
    deixava a perda gravada no anterior sem nenhum jeito de desfazer. Reverte
    a perda quando ainda está pendente de motivo (ninguém confirmou); se o
    motivo já foi preenchido, o usuário confirmou a perda como fato — só
    desvincula a referência ao serviço que não existe mais."""
    excluidos = {obj.id for obj in alvos if isinstance(obj, Servico)}
    if not excluidos:
        return
    query = select(Servico).where(Servico.perda_causada_por_servico_id.in_(excluidos))
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    for anterior in session.exec(query).all():
        if anterior.motivo_perda_prenhez is None:
            anterior.data_perda_prenhez = None
            anterior.origem_perda_prenhez = None
        anterior.perda_causada_por_servico_id = None
        session.add(anterior)


def _remover_lactacao_dos_partos_excluidos(session: Session, alvos: list, fazenda_id: int | None) -> None:
    """Todo parto (inclusive o aborto) abre uma `Lactacao` — excluir o parto
    tem que fechar esse ciclo também, senão a matriz fica "em lactação" para
    sempre por causa de um evento que não existe mais, e o controle leiteiro
    dela continuaria sendo aceito (ver POST /producao/controles).

    Casa pelo `parto_id` e, para as lactações do backfill que possam não tê-lo,
    também por (matriz, data de início == data do parto).

    REABRE a lactação anterior quando foi ESTE parto que a fechou: `abrir_
    lactacao` encerra a anterior na data do novo parto quando não houve
    secagem no meio (ver rules/lactacao.py). Desfazer o parto tem que desfazer
    esse fechamento — mas só ele: uma lactação fechada por uma `Secagem` real
    (`secagem_id` preenchido) continua fechada, porque aquele evento aconteceu
    de verdade e não depende deste parto."""
    partos_excluidos = [obj for obj in alvos if isinstance(obj, Parto)]
    if not partos_excluidos:
        return
    for p in partos_excluidos:
        query = select(Lactacao).where(Lactacao.numero_matriz == p.numero_matriz)
        if fazenda_id is not None:
            query = query.where(Lactacao.fazenda_id == fazenda_id)
        lactacoes = sorted(session.exec(query).all(), key=lambda l: l.data_inicio)
        for lact in lactacoes:
            if lact.parto_id != p.id and not (p.data_parto and lact.data_inicio == p.data_parto):
                continue
            for anterior in lactacoes:
                if (
                    anterior is not lact
                    and anterior.data_fim == lact.data_inicio
                    and anterior.secagem_id is None
                ):
                    anterior.data_fim = None
                    session.add(anterior)
            session.delete(lact)


def _reabrir_lactacao_das_secagens_excluidas(session: Session, alvos: list, fazenda_id: int | None) -> None:
    """A secagem é o evento que FECHA a lactação (ver rules/lactacao.py) —
    excluir a secagem tem que desfazer esse fechamento também, senão a
    lactação continua "fechada" para sempre por um evento que não existe
    mais, e todo controle leiteiro lançado depois passa a ser recusado (ou,
    pior, o relatório de correção de DEL passa a reportá-lo como "sem
    lactação" — caso relatado: secagem lançada em lote por engano em
    04/07/2026, fechando a lactação de vacas que na verdade só secaram
    semanas depois).

    Mesmo espírito de `_remover_lactacao_dos_partos_excluidos`, mas para
    `Secagem`: usa `reabrir_lactacao_fechada_por_secagem`, que já sabe achar
    a lactação certa pelo `secagem_id` e não faz nada quando esta secagem
    não tinha fechado nenhuma (lançada para quem já constava seco)."""
    secagens_excluidas = [obj for obj in alvos if isinstance(obj, Secagem)]
    for s in secagens_excluidas:
        if s.id is not None:
            regras_lactacao.reabrir_lactacao_fechada_por_secagem(session, secagem_id=s.id, fazenda_id=fazenda_id)


def _reajustar_del_dias_apos_excluir_parto(session: Session, alvos: list, fazenda_id: int | None) -> None:
    """`registrar_parto` zera `Animal.del_dias` da mãe no instante do parto
    (congelado dali em diante, só voltando a bater com a realidade no próximo
    upload do GERAL.csv — ver `_del_dias_ao_vivo` em api/routers/animais.py).
    Excluir esse Parto deixava o 0 congelado pra sempre, mesmo quando a vaca
    na verdade está há dias em lactação (ou já foi seca) por outro parto
    remanescente. Recalcula com o MESMO critério "ao vivo": parto
    remanescente mais recente da matriz, e None quando não há nenhum (não dá
    pra reconstruir o valor pré-parto sem o próximo import do CSV)."""
    partos_excluidos = [obj for obj in alvos if isinstance(obj, Parto)]
    if not partos_excluidos:
        return
    ids_excluidos = {p.id for p in partos_excluidos}
    hoje = date.today()
    for p in partos_excluidos:
        query_animal = select(Animal).where(Animal.numero == p.numero_matriz)
        if fazenda_id is not None:
            query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        mae = session.exec(query_animal).first()
        if mae is None:
            continue
        query_partos = select(Parto).where(Parto.numero_matriz == p.numero_matriz)
        if fazenda_id is not None:
            query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
        ult_parto = max(
            (x.data_parto for x in session.exec(query_partos).all() if x.data_parto and x.id not in ids_excluidos),
            default=None,
        )
        query_secagens = select(Secagem).where(Secagem.numero_matriz == p.numero_matriz)
        if fazenda_id is not None:
            query_secagens = query_secagens.where(Secagem.fazenda_id == fazenda_id)
        ult_secagem = max((x.data_secagem for x in session.exec(query_secagens).all() if x.data_secagem), default=None)
        if ult_parto is None or (ult_secagem and ult_secagem >= ult_parto):
            mae.del_dias = None
        else:
            mae.del_dias = (hoje - ult_parto).days
        session.add(mae)


def _estornar_estoque_dos_alvos(session: Session, alvos: list, fazenda_id: int | None, tipo_exclusao: str) -> list[str]:
    """Antes de excluir, devolve ao estoque tudo que os objetos em `alvos`
    consumiram — resolvido pelos MovimentoEstoque que apontam pra eles via
    origem_tipo/origem_id (ver rules/estoque_baixa.py e o mapa
    `_ORIGENS_POR_CLASSE` acima). Genérico: funciona pra qualquer tipo de
    exclusão que tenha causado baixa, sem reimplementar a lógica de devolução
    tipo a tipo. Nunca bloqueia a exclusão — só avisa quando algo não pôde
    ser revertido."""
    avisos: list[str] = []
    for obj in alvos:
        origens = _ORIGENS_POR_CLASSE.get(type(obj))
        if not origens or getattr(obj, "id", None) is None:
            continue
        # Lançamento já cancelado (POST .../cancelar, ver central_protocolos.py)
        # — o cancelamento já devolveu ao estoque tudo que ele consumiu, mas
        # não apaga o MovimentoEstoque de "Aplicação" original (só grava um
        # estorno ao lado). Sem esta guarda, excluir um lançamento já
        # cancelado encontrava de novo a MESMA "Aplicação" e devolvia o
        # estoque uma segunda vez — hormônio em dobro.
        if getattr(obj, "ativo", True) is False:
            continue
        query = select(MovimentoEstoque).where(
            MovimentoEstoque.origem_tipo.in_(origens),
            MovimentoEstoque.origem_id == obj.id,
            MovimentoEstoque.movimento.in_(["Aplicação", "Entrada de compra"]),
        )
        if fazenda_id is not None:
            query = query.where(MovimentoEstoque.fazenda_id == fazenda_id)
        for mov in session.exec(query).all():
            observacao = f"Estorno por exclusão ({tipo_exclusao}) — mov #{mov.id}"
            if mov.origem_tipo == "ia_semen":
                avisos.extend(_devolver_dose_semen_do_movimento(session, mov, fazenda_id, observacao))
                continue
            item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=mov.nome_item, estoque_id=mov.estoque_id)
            if mov.movimento == "Entrada de compra":
                # A baixa original SOMOU ao estoque (compra financeira) — o
                # estorno precisa SUBTRAIR a mesma quantidade, não devolver.
                avisos.extend(estoque_baixa.movimentar(
                    session, item=item, quantidade=mov.quantidade, unidade=mov.unidade, data=date.today(),
                    fazenda_id=fazenda_id, movimento="Saída de ajuste", observacao=observacao, sinal=-1,
                    origem_tipo=f"estorno_{tipo_exclusao}", origem_id=obj.id, produto=mov.nome_item,
                ))
            else:
                avisos.extend(estoque_baixa.devolver(
                    session, item=item, quantidade=mov.quantidade, unidade=mov.unidade, data=date.today(),
                    fazenda_id=fazenda_id, observacao=observacao,
                    origem_tipo=f"estorno_{tipo_exclusao}", origem_id=obj.id, produto=mov.nome_item,
                ))
    return avisos


class ExclusaoIn(BaseModel):
    tipo: str
    id: str


@router.post("/impacto")
def impacto(
    dados: ExclusaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    itens, _ = _alvos(dados.tipo, dados.id, session, fazenda_id=fazenda_id_seguro(fazenda_id))
    return {"impacto": itens}


@router.post("/confirmar")
def confirmar(
    dados: ExclusaoIn,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Admin exclui na hora. Operador só registra uma solicitação pendente."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    itens, alvos = _alvos(dados.tipo, dados.id, session, fazenda_id=fazenda_id)

    if user.papel == "admin":
        _desvincular_vales_dos_alvos(session, alvos, fazenda_id)
        _restaurar_ult_ocorrencia_dos_alvos(session, alvos, fazenda_id)
        _reverter_perda_prenhez_causada_pelos_alvos(session, alvos, fazenda_id)
        _remover_lactacao_dos_partos_excluidos(session, alvos, fazenda_id)
        _reabrir_lactacao_das_secagens_excluidas(session, alvos, fazenda_id)
        _reajustar_del_dias_apos_excluir_parto(session, alvos, fazenda_id)
        avisos = _estornar_estoque_dos_alvos(session, alvos, fazenda_id, dados.tipo)
        for obj in alvos:
            session.delete(obj)
        session.commit()
        return {"status": "excluido", "itens": itens, "avisos": avisos}

    solicitacao = SolicitacaoExclusao(
        tipo=dados.tipo,
        id_alvo=dados.id,
        titulo=itens[0] if itens else f"{dados.tipo} #{dados.id}",
        solicitado_por=user.username,
        fazenda_id=fazenda_id,
    )
    session.add(solicitacao)
    session.commit()
    return {"status": "solicitado", "itens": itens}


@router.get("/pendentes", dependencies=[Depends(exigir_admin)])
def listar_pendentes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(SolicitacaoExclusao).where(SolicitacaoExclusao.status == "pendente")
    if fazenda_id is not None:
        query = query.where(SolicitacaoExclusao.fazenda_id.in_((fazenda_id, None)))
    sols = session.exec(query.order_by(SolicitacaoExclusao.criado_em.desc())).all()
    return [s.model_dump() for s in sols]


@router.post("/pendentes/{sol_id}/aprovar", dependencies=[Depends(exigir_admin)])
def aprovar_pendente(
    sol_id: int,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    sol = session.get(SolicitacaoExclusao, sol_id)
    if not sol or sol.status != "pendente":
        raise HTTPException(status_code=404, detail="Solicitação não encontrada ou já decidida")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is not None and sol.fazenda_id not in (None, fazenda_id):
        raise HTTPException(status_code=404, detail="Solicitação não encontrada ou já decidida")

    _, alvos = _alvos(sol.tipo, sol.id_alvo, session, fazenda_id=fazenda_id)
    _desvincular_vales_dos_alvos(session, alvos, fazenda_id)
    _restaurar_ult_ocorrencia_dos_alvos(session, alvos, fazenda_id)
    _reverter_perda_prenhez_causada_pelos_alvos(session, alvos, fazenda_id)
    _remover_lactacao_dos_partos_excluidos(session, alvos, fazenda_id)
    _reabrir_lactacao_das_secagens_excluidas(session, alvos, fazenda_id)
    _reajustar_del_dias_apos_excluir_parto(session, alvos, fazenda_id)
    avisos = _estornar_estoque_dos_alvos(session, alvos, fazenda_id, sol.tipo)
    for obj in alvos:
        session.delete(obj)
    sol.status = "aprovada"
    sol.decidido_por = user.username
    sol.decidido_em = datetime.utcnow()
    session.add(sol)
    session.commit()
    return {"aprovado": True, "avisos": avisos}


class RejeitarIn(BaseModel):
    motivo: str | None = None


@router.post("/pendentes/{sol_id}/rejeitar", dependencies=[Depends(exigir_admin)])
def rejeitar_pendente(
    sol_id: int,
    dados: RejeitarIn,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    sol = session.get(SolicitacaoExclusao, sol_id)
    if not sol or sol.status != "pendente":
        raise HTTPException(status_code=404, detail="Solicitação não encontrada ou já decidida")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is not None and sol.fazenda_id not in (None, fazenda_id):
        raise HTTPException(status_code=404, detail="Solicitação não encontrada ou já decidida")

    sol.status = "rejeitada"
    sol.decidido_por = user.username
    sol.decidido_em = datetime.utcnow()
    sol.motivo_rejeicao = dados.motivo
    session.add(sol)
    session.commit()
    return {"rejeitado": True}
