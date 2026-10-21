"""
Leituras agregadas do sanitário — SÓ LEITURA (nenhuma chama add/commit).
Contagens são sempre de animais DISTINTOS; nunca se soma entre caixas.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario.tipos import ESTADOS_NA_CAIXA


def _quando(row, hoje: date) -> Optional[date]:
    if row.estado == "marcada":
        return None  # o dia conta à parte
    if row.estado in ("janela", "atrasada"):
        return hoje
    if row.estado in ("aviso", "prevista"):
        return row.data_base or row.janela_inicio
    return None


def resumo_30d(session: Session, fazenda_id: int, hoje: Optional[date] = None, dias: int = 30) -> dict:
    """Card "Vacinas previstas" da Agenda: só números (animais distintos,
    caixas e dias marcados nos próximos `dias`)."""
    from fazenda.models import SanitarioCaixa, SanitarioDia, SanitarioSituacao

    hoje = hoje or hoje_local()
    ate = hoje + timedelta(days=dias)
    ativas = set(session.exec(select(SanitarioCaixa.id).where(
        SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.estado == "ativa")).all())
    animais, caixas = set(), set()
    for r in session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fazenda_id,
        SanitarioSituacao.estado.in_(("janela", "atrasada", "aviso", "prevista", "marcada")),
    )).all():
        if r.caixa_id not in ativas:
            continue
        q = _quando(r, hoje)
        if r.estado == "marcada" or (q is not None and q <= ate):
            animais.add(r.animal_id)
            caixas.add(r.caixa_id)
    n_dias = len(session.exec(select(SanitarioDia.id).where(
        SanitarioDia.fazenda_id == fazenda_id, SanitarioDia.estado.in_(("marcado", "em_execucao")),
        SanitarioDia.data >= hoje, SanitarioDia.data <= ate,
    )).all())
    return {"animais": len(animais), "caixas": len(caixas), "dias": n_dias, "periodo_dias": dias}


def membros(session: Session, fazenda_id: int, caixa_id: int, estados=ESTADOS_NA_CAIXA) -> list:
    """Linhas de situação da caixa nos estados pedidos (padrão: na caixa)."""
    from fazenda.models import SanitarioSituacao

    return list(session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fazenda_id, SanitarioSituacao.caixa_id == caixa_id,
        SanitarioSituacao.estado.in_(tuple(estados)),
    ).order_by(SanitarioSituacao.animal_id)).all())


def situacao_do_animal(session: Session, fazenda_id: int, animal_id: int, hoje: Optional[date] = None) -> list:
    """Situação ao vivo (motor puro) do animal em todas as caixas ativas —
    não lê nem grava `sanitario_situacao`."""
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
    from fazenda.rules.sanitario.motor import avaliar

    animais = carregar_animais(session, fazenda_id, animal_ids=[animal_id], hoje=hoje)
    a = animais.get(animal_id)
    if a is None:
        return []
    out = []
    for cx in carregar_caixas(session, fazenda_id, so_ativas=True):
        for s in avaliar(cx, a):
            out.append({
                "caixa_id": cx.caixa_id, "caixa": cx.rotulo, "estado": s.estado, "texto": s.texto,
                "ciclo": s.ciclo_chave, "dose": s.dose_num,
                "janela_inicio": s.ciclo.ini.isoformat() if s.ciclo and s.ciclo.chave != "C" else None,
                "janela_fim": s.ciclo.fim.isoformat() if s.ciclo and s.ciclo.chave != "C" else None,
                "motivos": [{"ok": m.ok, "texto": m.texto} for m in s.motivos],
            })
    return out


def registros_do_animal(session: Session, fazenda_id: Optional[int], animal_id: int, *, so_exames: bool = False,
                        incluir_estornados: bool = False) -> list[dict]:
    """Histórico sanitário preventivo do animal (registros), mais recente
    primeiro — a ficha do animal e o histórico leem daqui. SÓ LÊ."""
    from fazenda.models import SanitarioCaixa, SanitarioRegistro

    q = select(SanitarioRegistro).where(SanitarioRegistro.animal_id == animal_id)
    if fazenda_id is not None:
        q = q.where(SanitarioRegistro.fazenda_id == fazenda_id)
    if not incluir_estornados:
        q = q.where(SanitarioRegistro.estado == "valido")
    regs = session.exec(q.order_by(SanitarioRegistro.data.desc(), SanitarioRegistro.id.desc())).all()
    caixas = {c.id: c for c in session.exec(select(SanitarioCaixa).where(
        SanitarioCaixa.id.in_({r.caixa_id for r in regs if r.caixa_id} or {-1}))).all()}
    out = []
    for r in regs:
        cx = caixas.get(r.caixa_id) if r.caixa_id else None
        if so_exames and (cx is None or cx.tipo != "exame"):
            continue
        out.append(registro_dict(r, cx))
    return out


def registro_dict(r, cx=None) -> dict:
    return {
        "id": r.id, "data": r.data.isoformat() if r.data else None, "hora": r.hora,
        "animal_id": r.animal_id, "numero": r.numero_animal_texto,
        "caixa_id": r.caixa_id, "caixa": (cx.nome_curto or cx.nome) if cx else None,
        "tipo": cx.tipo if cx else "outro", "outro_texto": r.outro_texto, "ciclo_chave": r.ciclo_chave,
        "dose_num": r.dose_num, "dia_id": r.dia_id, "origem": r.origem, "canal": r.canal,
        "so_registro": r.so_registro, "decisao_curral": r.decisao_curral, "apos_fechamento": r.apos_fechamento,
        "retroativo": r.retroativo, "retroativo_motivo": r.retroativo_motivo, "fora_da_regra": r.fora_da_regra,
        "produto_modo": r.produto_modo, "estoque_id": r.estoque_id, "produto_texto": r.produto_texto,
        "dose_valor": r.dose_valor, "dose_unidade": r.dose_unidade, "quantidade_baixada": r.quantidade_baixada,
        "custo": r.custo, "peso_usado": r.peso_usado, "peso_estimado": r.peso_estimado,
        "partida_texto": r.partida_texto, "fabricante": r.fabricante,
        "validade": r.validade.isoformat() if r.validade else None, "lote_estoque_id": r.lote_estoque_id,
        "dia_item_id": r.dia_item_id, "carencia_aceite_id": r.carencia_aceite_id,
        "aplicador_pessoa_id": r.aplicador_pessoa_id, "aplicador_texto": r.aplicador_texto,
        "veterinario_pessoa_id": r.veterinario_pessoa_id, "veterinario_texto": r.veterinario_texto,
        "crmv_texto": r.crmv_texto,
        "resultado": r.resultado, "resultado_valor": r.resultado_valor, "resultado_detalhe": r.resultado_detalhe,
        "leitura_em": r.leitura_em.isoformat() if r.leitura_em else None,
        "carencia_leite_ate": r.carencia_leite_ate.isoformat() if r.carencia_leite_ate else None,
        "carencia_carne_ate": r.carencia_carne_ate.isoformat() if r.carencia_carne_ate else None,
        "carencia_modo": r.carencia_modo, "atestado_numero": r.atestado_numero,
        "atestado_destinatario": r.atestado_destinatario, "numero_lancamento_vinculado": r.numero_lancamento_vinculado,
        "estado": r.estado, "estornado_motivo": r.estornado_motivo,
        "criado_em": r.criado_em.isoformat() if r.criado_em else None,
    }
