"""
Cenário comum dos testes do Sanitário Preventivo v2 (motor, job, ganchos).

Banco SQLite em memória com `create_all`, duas fazendas, categorias de manejo
por idade e helpers para animais, serviços, partos e caixas (criadas pela
única porta de criação, `definicao.criar_caixa`).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Animal, CategoriaManejo, Fazenda, Parto, Servico
from fazenda.rules.sanitario.definicao import criar_caixa

HOJE = date(2026, 10, 21)
F1, F2 = 1, 2


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=F1, nome="Estreito", uf="GO"))
        s.add(Fazenda(id=F2, nome="Outra", uf="MG"))
        s.commit()
        for fid in (F1, F2):
            for nome, dmin, dmax, ordem in (
                ("Aleitamento", 0, 90, 0), ("Recria 1", 91, 210, 1), ("Recria 2", 211, 390, 2),
                ("Novilha", 391, None, 3),
            ):
                s.add(CategoriaManejo(fazenda_id=fid, nome=nome, dia_min=dmin, dia_max=dmax, ordem=ordem))
        s.commit()
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def categoria_id(session: Session, fazenda_id: int, nome: str) -> int:
    from sqlmodel import select
    return session.exec(select(CategoriaManejo.id).where(
        CategoriaManejo.fazenda_id == fazenda_id, CategoriaManejo.nome == nome)).one()


def animal(session: Session, numero: str, *, fazenda_id: int = F1, sexo: str = "F", idade_dias: int | None = None,
           nasc: date | None = None, ativo: bool = True, motivo_baixa: str | None = None) -> Animal:
    if nasc is None and idade_dias is not None:
        nasc = HOJE - timedelta(days=idade_dias)
    a = Animal(fazenda_id=fazenda_id, numero=numero, sexo=sexo, data_nasc=nasc, ativo=ativo,
               motivo_baixa=motivo_baixa, raca="Holandês")
    session.add(a)
    session.flush()
    return a


def servico(session: Session, a: Animal, data: date, *, positivo: bool = True) -> Servico:
    s = Servico(fazenda_id=a.fazenda_id, animal_id=a.id, numero_matriz=a.numero, data_servico=data,
                diagnostico="POSITIVO" if positivo else None, raca_matriz=a.raca)
    session.add(s)
    session.flush()
    return s


def parto(session: Session, a: Animal, data: date) -> Parto:
    p = Parto(fazenda_id=a.fazenda_id, animal_id=a.id, numero_matriz=a.numero, data_parto=data)
    session.add(p)
    session.flush()
    return p


# ── definições prontas ──────────────────────────────────────────────────────
def def_b19(**kw) -> dict:
    d = dict(nome="Brucelose B19", nome_curto="B19", tipo="vacina", pub_sexo="F", jan_usa_evento=True,
             evento_tipo="idade", evento_de_dias=120, evento_ate_dias=240, jan_usa_periodo=True,
             periodo_modo="continuo", ao_fechar="perder", aglo_min=4, dose_valor=2, dose_unidade="mL")
    d.update(kw)
    return d


def def_meses(nome: str, grupos, **kw) -> dict:
    d = dict(nome=nome, nome_curto=nome, tipo="vacina", jan_usa_periodo=True, periodo_modo="meses",
             periodo_grupos=grupos, ao_fechar="manter", aglo_min=2)
    d.update(kw)
    return d


def def_pre_parto(nome: str = "Clostridiose · pré-parto", **kw) -> dict:
    d = dict(nome=nome, nome_curto="Clostridiose", tipo="vacina", pub_sexo="F", pub_condicoes=["prenhe"],
             jan_usa_evento=True, evento_tipo="pre_parto", evento_de_dias=-30, evento_ate_dias=0,
             ao_fechar="perder", aglo_min=1)
    d.update(kw)
    return d


def caixa(session: Session, definicao: dict, *, fazenda_id: int = F1, estado: str = "ativa", ativada_em: date | None = None):
    cx = criar_caixa(session, fazenda_id, definicao, estado=estado, hoje=HOJE)
    if ativada_em is not None:
        cx.ativada_em = ativada_em
        session.add(cx)
        session.flush()
    return cx
