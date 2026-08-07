"""
Tipos de exclusão do domínio de Rebanho/Reprodução — preenchido pelo Agente
C1 (Rebanho & Reprodução): G4 (`movimento_lote`), G5 (`secagem`). G12 é só UI
(tipos `servico`/`parto` já existem no motor) — não mexe neste arquivo.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from fazenda.models import Animal, AplicacaoAgendada, MovimentoLote, Sanidade, Secagem
from fazenda.rules.exclusao_tipos._base import TipoExclusao, _br, _contem, _dentro_periodo

# Espelha ORIGEM_MOVIMENTO_LOTE_LABEL de frontend/lib/constants.ts — mantido
# aqui em vez de importado (backend não pode importar do frontend) só para
# compor o subtítulo da busca do motor de exclusões; a UI de Movimentações em
# si continua usando a constante do frontend.
_ORIGEM_LABEL = {
    "manual": "Manual",
    "sugestao_confirmada": "Sugestão confirmada",
    "sugestao_automatica": "Sugestão automática",
    "sugestao_passiva": "Sugestão passiva",
    "importacao": "Importação",
}


def _rotulo_origem(origem: Optional[str]) -> str:
    return _ORIGEM_LABEL.get(origem or "", "Desconhecida")


def _buscar_movimento_lote(
    termo: str, data_inicio: str, data_fim: str, session: Session, fazenda_id: int | None = None,
) -> list[dict]:
    query = select(MovimentoLote)
    if fazenda_id is not None:
        query = query.where(MovimentoLote.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    out = [
        {
            "id": m.id,
            "titulo": f"{m.numero_matriz} — {m.lote_origem or '—'} → {m.lote_destino} — {_br(m.data_movimento)}",
            "subtitulo": f"{m.motivo or '—'} · {_rotulo_origem(m.origem)}",
            "_data": m.data_movimento,
        }
        for m in rows
        if _contem(termo, m.numero_matriz, m.lote_origem, m.lote_destino, m.motivo, m.responsavel)
        and _dentro_periodo(m.data_movimento, data_inicio, data_fim)
    ]
    return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]


def _alvos_movimento_lote(id_: str, session: Session, fazenda_id: int | None = None) -> tuple[list[str], list]:
    """G4 — excluir um MovimentoLote só desfaz a troca de lote do ANIMAL
    (Animal.grupo_primario/grupo_raw) quando este é o movimento MAIS RECENTE
    daquele animal (por data_movimento, id desc). Havendo movimentação
    posterior, o lote atual do animal já reflete essa transferência mais
    nova — sobrescrevê-lo com o `lote_origem` deste registro mais antigo
    corromperia o estado atual; nesse caso só o histórico (o próprio
    MovimentoLote) é apagado."""
    mov = session.get(MovimentoLote, int(id_))
    if not mov or (fazenda_id is not None and mov.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")

    impacto = [f"Movimentação de {mov.numero_matriz}: {mov.lote_origem or '—'} → {mov.lote_destino} em {_br(mov.data_movimento)}"]

    query_irmaos = select(MovimentoLote).where(MovimentoLote.numero_matriz == mov.numero_matriz)
    if fazenda_id is not None:
        query_irmaos = query_irmaos.where(MovimentoLote.fazenda_id == fazenda_id)
    irmaos = session.exec(query_irmaos).all()
    mais_recente = max(irmaos, key=lambda m: (m.data_movimento, m.id)) if irmaos else None

    query_animal = select(Animal).where(Animal.numero == mov.numero_matriz)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()

    if mais_recente is not None and mais_recente.id == mov.id:
        if not mov.lote_origem:
            impacto.append(f"O animal {mov.numero_matriz} não tinha lote registrado antes desta movimentação — o lote atual não será alterado")
        elif animal is not None:
            animal.grupo_primario = mov.lote_origem
            animal.grupo_raw = mov.lote_origem
            animal.grupo_manual = True
            animal.atualizado_em = datetime.utcnow()
            session.add(animal)
            impacto.append(f"O animal {mov.numero_matriz} volta para o lote {mov.lote_origem}")
    else:
        lote_atual = animal.grupo_primario if animal is not None else "—"
        impacto.append(
            f"Existe(m) movimentação(ões) posterior(es) deste animal — o lote atual "
            f"({lote_atual or '—'}) NÃO será alterado, só o histórico."
        )

    return impacto, [mov]


def _buscar_secagem(
    termo: str, data_inicio: str, data_fim: str, session: Session, fazenda_id: int | None = None,
) -> list[dict]:
    query = select(Secagem)
    if fazenda_id is not None:
        query = query.where(Secagem.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    out = [
        {
            "id": s.id,
            "titulo": f"{s.numero_matriz} — {_br(s.data_secagem)}",
            "subtitulo": f"{s.motivo}" + (f" · escore {s.escore_condicao_corporal:g}" if s.escore_condicao_corporal else ""),
            "_data": s.data_secagem,
        }
        for s in rows
        if _contem(termo, s.numero_matriz, s.motivo, s.observacao) and _dentro_periodo(s.data_secagem, data_inicio, data_fim)
    ]
    return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]


def _alvos_secagem(id_: str, session: Session, fazenda_id: int | None = None) -> tuple[list[str], list]:
    """G5 — `registrar_secagem` (api/routers/producao.py) cria até quatro
    coisas sem NENHUMA FK de volta para `Secagem`: Sanidade(atividade=
    "Secagem"/"Vacina pré-parto") quando já aplicado na hora, ou
    AplicacaoAgendada(observacao="Secagem"/"Vacina pré-parto") quando
    programado. Localizamos por heurística (matriz + data + atividade/
    observação) — a vacina pré-parto programada nasce para o DIA SEGUINTE à
    secagem (ver producao.py), por isso a janela de datas da AplicacaoAgendada
    inclui data_secagem E data_secagem+1.
    O estorno de estoque das Sanidade encontradas sai de graça: `Sanidade` já
    está em `_ORIGENS_POR_CLASSE` (exclusoes.py) com origem_tipo "secagem" e
    "vacina_pre_parto" — basta devolvê-las na lista de objetos.
    """
    s = session.get(Secagem, int(id_))
    # Tolerância a NULL: `Secagem.fazenda_id` pode ser None em registros
    # anteriores ao multi-fazenda — não bloquear a exclusão desses legados só
    # porque o usuário está com uma fazenda selecionada no token.
    if not s or (fazenda_id is not None and s.fazenda_id not in (None, fazenda_id)):
        raise HTTPException(status_code=404, detail="Secagem não encontrada")

    sanidades = session.exec(
        select(Sanidade).where(
            Sanidade.numero_matriz == s.numero_matriz,
            Sanidade.data_aplicacao == s.data_secagem,
            Sanidade.atividade.in_(("Secagem", "Vacina pré-parto")),
            Sanidade.fazenda_id == s.fazenda_id,
        )
    ).all()
    agendadas = session.exec(
        select(AplicacaoAgendada).where(
            AplicacaoAgendada.numero_matriz == s.numero_matriz,
            AplicacaoAgendada.data.in_((s.data_secagem, s.data_secagem + timedelta(days=1))),
            AplicacaoAgendada.observacao.in_(("Secagem", "Vacina pré-parto")),
            AplicacaoAgendada.aplicado == False,  # noqa: E712
            AplicacaoAgendada.fazenda_id == s.fazenda_id,
        )
    ).all()

    impacto = [f"Secagem de {s.numero_matriz} em {_br(s.data_secagem)} ({s.motivo})"]
    if sanidades:
        produtos = ", ".join(sorted({sa.produto for sa in sanidades}))
        impacto.append(
            f"{len(sanidades)} aplicação(ões) em Sanidade (produto de secagem/vacina pré-parto) — "
            f"o estoque será devolvido: {produtos}"
        )
    if agendadas:
        produtos_ag = ", ".join(sorted({a.produto for a in agendadas}))
        impacto.append(f"{len(agendadas)} aplicação(ões) ainda programada(s) na Agenda: {produtos_ag}")

    return impacto, [s, *sanidades, *agendadas]


TIPOS_EXCLUSAO: list = [
    TipoExclusao(
        id="movimento_lote",
        label="Movimentação entre lotes",
        buscar=_buscar_movimento_lote,
        alvos=_alvos_movimento_lote,
        sem_filtro_data=False,
    ),
    TipoExclusao(
        id="secagem",
        label="Secagem",
        buscar=_buscar_secagem,
        alvos=_alvos_secagem,
        sem_filtro_data=False,
    ),
]
