"""
Cadastro > Sanitário — Princípio ativo, Doença (com seed), Agendamento de
pesagem e o template do checklist do protocolo curativo. Protocolos
sanitários (curativos e indução de lactação) ficam em protocolos_sanitarios.py
— módulo maior e com sua própria importação de planilha.

O antigo calendário sanitário preventivo (eventos sanitários, exames,
checklist e calendário padrão) foi arquivado em 2026 (schema
arquivo_sanitario_2026); o módulo novo de vacinas e exames vive nas tabelas
sanitario_*.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import AgendamentoPesagem, Doenca, PrincipioAtivo
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.checklist_curativo import TIPO_CURATIVO, template_curativo

from ._comum import _crud_nome_ativo

router = APIRouter()

# ---------------------------------------------------------------------------
# Doença — cadastro de apoio da farmácia/curativo. Seed inicial idempotente.
# ---------------------------------------------------------------------------
SEED_DOENCAS = [
    "Brucelose", "Clostridiose", "Diarreia Neonatal", "Botulismo", "Pasteurelose", "Verminose",
    "Leptospirose", "Tuberculose", "Febre Aftosa", "Raiva",
]


def seed_cadastro_sanitario(session: Session) -> None:
    """Cria as doenças padrão se a tabela ainda estiver vazia (idempotente).
    Princípios ativos não entram aqui: o catálogo completo (documento base) é
    responsabilidade de bootstrap_farmacia, que roda em todo start."""
    if not session.exec(select(Doenca)).first():
        for nome in SEED_DOENCAS:
            session.add(Doenca(nome=nome))
    session.commit()


# ---------------------------------------------------------------------------
# Princípio ativo / Doença — cadastros simples nome+ativo (catálogo global +
# os da fazenda).
# ---------------------------------------------------------------------------
_listar_principios, _criar_principio, _atualizar_principio, _ = _crud_nome_ativo(
    PrincipioAtivo, com_fazenda=True, global_compartilhado=True,
)
router.get("/principios-ativos")(_listar_principios)
router.post("/principios-ativos")(_criar_principio)
router.put("/principios-ativos/{item_id}")(_atualizar_principio)


# BUG DE SEGURANÇA CORRIGIDO (achado 35): aqui existia
# `POST /principios-ativos/restaurar-catalogo`, SEM dependência de fazenda e
# SEM gate de papel — qualquer usuário com o módulo sanitário disparava uma
# reescrita (add-missing) do catálogo GLOBAL de princípios ativos, que é
# compartilhado por todas as fazendas-cliente.
#
# Não bastava acrescentar um `exigir_admin` aqui: o catálogo global não é
# dado da fazenda, é dado da CowData, e escrever nele a partir de um router
# do TENANT é o mesmo erro estrutural que o catálogo de touros NAAB já teve
# (escrita removida do lado da fazenda no PR #702). A rota foi movida para
# `painel_cowdata_farmacia.py`, junto das outras escritas do catálogo global,
# com o gate que elas já usam (área "farmacia" + `pode_editar_farmacia`).
#
# Ninguém do lado da fazenda perdeu função: o botão que a chamava só é
# renderizado no Painel CowData (Farmacia.tsx só o mostra quando
# `!somenteLeitura`, e a tela do tenant monta o componente com
# `somenteLeitura`).

_listar_doencas, _criar_doenca, _atualizar_doenca, _ = _crud_nome_ativo(
    Doenca, com_fazenda=True, global_compartilhado=True,
)
router.get("/doencas")(_listar_doencas)
router.post("/doencas")(_criar_doenca)
router.put("/doencas/{item_id}")(_atualizar_doenca)


# ---------------------------------------------------------------------------
# Agendamento de pesagem do rebanho (acompanhamento da evolução de peso) —
# periodicidade por fase + dia da semana, que alimenta a Agenda.
# ---------------------------------------------------------------------------
class AgendamentoPesagemIn(BaseModel):
    nome: str
    ativo: bool = True
    idade_min_dias: int | None = None
    idade_max_dias: int | None = None
    categoria_alvo: str | None = None
    frequencia_valor: int = 15
    frequencia_unidade: str = "dias"  # "dias" | "meses"
    dia_semana: int = 1  # 0=segunda … 6=domingo
    data_referencia: date


@router.get("/agendamentos-pesagem")
def listar_agendamentos_pesagem(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(AgendamentoPesagem).order_by(AgendamentoPesagem.nome)
    if fazenda_id is not None:
        query = query.where(AgendamentoPesagem.fazenda_id == fazenda_id)
    return [a.model_dump() for a in session.exec(query).all()]


def _valida_pesagem(dados: AgendamentoPesagemIn) -> None:
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome da fase (ex.: Bezerras até desmama)")
    if dados.frequencia_unidade not in ("dias", "meses"):
        raise HTTPException(status_code=400, detail="Frequência inválida (dias ou meses)")
    if dados.frequencia_valor <= 0:
        raise HTTPException(status_code=400, detail="A periodicidade deve ser maior que zero")
    if not (0 <= dados.dia_semana <= 6):
        raise HTTPException(status_code=400, detail="Dia da semana inválido")


@router.post("/agendamentos-pesagem", status_code=201)
def criar_agendamento_pesagem(
    dados: AgendamentoPesagemIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    _valida_pesagem(dados)
    obj = AgendamentoPesagem(**{**dados.model_dump(), "nome": dados.nome.strip()}, fazenda_id=fazenda_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.put("/agendamentos-pesagem/{item_id}")
def atualizar_agendamento_pesagem(
    item_id: int, dados: AgendamentoPesagemIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    obj = session.get(AgendamentoPesagem, item_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    _valida_pesagem(dados)
    for k, v in {**dados.model_dump(), "nome": dados.nome.strip()}.items():
        setattr(obj, k, v)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.delete("/agendamentos-pesagem/{item_id}")
def excluir_agendamento_pesagem(
    item_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    obj = session.get(AgendamentoPesagem, item_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    session.delete(obj)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Template do checklist do protocolo CURATIVO — só leitura. Os tipos
# "vacina"/"exame" eram do sanitário preventivo antigo (saíram em 2026).
# ---------------------------------------------------------------------------
@router.get("/checklist-template")
def listar_checklist_template(
    tipo: str = TIPO_CURATIVO, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    if tipo != TIPO_CURATIVO:
        raise HTTPException(status_code=400, detail=f"Tipo inválido (use: {TIPO_CURATIVO})")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    return [{"chave": i.chave, "nome": i.nome, "ordem": i.ordem} for i in template_curativo(session, fazenda_id)]
