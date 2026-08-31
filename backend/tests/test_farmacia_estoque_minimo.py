"""
Estoque mínimo em unidade de medida (não em frascos/pacotes), por fazenda —
pedido do usuário (31/08/2026): "estoque mínimo... tem que ser em unidade de
medida. Ex.: Sincrogest — 3 pacotes de 10 + 2 pacotes de 5 — mínimo: 12
unidades, e não pacotes." Ver ParametroMinimoFarmacia e
PUT /farmacia/principios/{id}/estoque-minimo.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, ParametroMinimoFarmacia, PrincipioAtivo


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Fazenda A", ativa=True)
        fb = Fazenda(nome="Fazenda B", ativa=True)
        s.add_all([fa, fb])
        s.commit()
        s.refresh(fa)
        s.refresh(fb)
        fa_id, fb_id = fa.id, fb.id
        for fid in (fa_id, fb_id):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="sanitario", ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fa_id
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fa_id

    with TestClient(main.app) as c:
        yield c, engine, fa_id, fb_id
    main.app.dependency_overrides.clear()


def test_sem_override_mantem_regra_antiga_por_apresentacoes(client):
    c, engine, fa_id, fb_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Sincrogest", unidade_base="unidade", unidade_apresentacao="pacote")
        s.add(pa)
        s.commit()
        s.refresh(pa)
        pa_id = pa.id
        s.add(Estoque(nome="Sincrogest pct10", principio_ativo_id=pa_id, quantidade=30.0, unidade="unidade"))
        s.commit()

    r = c.get("/farmacia/principios")
    item = next(p for p in r.json() if p["id"] == pa_id)
    assert item["minimo_modo"] == "apresentacoes"
    assert item["precisa_reconciliar_minimo"] is True
    assert item["estoque_minimo_base"] is None


def test_define_minimo_em_unidade_e_passa_a_valer(client):
    c, engine, fa_id, fb_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Sincrogest", unidade_base="unidade", unidade_apresentacao="pacote")
        s.add(pa)
        s.commit()
        s.refresh(pa)
        pa_id = pa.id
        # 3 pacotes de 10 + 2 pacotes de 5 = 40 unidades no total
        s.add(Estoque(nome="Sincrogest pct10", principio_ativo_id=pa_id, quantidade=30.0, unidade="unidade"))
        s.add(Estoque(nome="Sincrogest pct5", principio_ativo_id=pa_id, quantidade=10.0, unidade="unidade"))
        s.commit()

    r = c.put(f"/farmacia/principios/{pa_id}/estoque-minimo", json={"estoque_minimo_base": 12})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["minimo_modo"] == "base"
    assert corpo["estoque_minimo_base"] == 12
    assert corpo["total_base"] == 40.0
    assert corpo["abaixo_minimo"] is False  # 40 >= 12
    assert corpo["precisa_reconciliar_minimo"] is False

    with Session(engine) as s:
        override = s.exec(select(ParametroMinimoFarmacia).where(ParametroMinimoFarmacia.principio_ativo_id == pa_id)).first()
        assert override is not None
        assert override.fazenda_id == fa_id
        assert override.estoque_minimo_base == 12


def test_abaixo_do_minimo_em_unidade_mesmo_com_varios_pacotes(client):
    c, engine, fa_id, fb_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Sincrogest", unidade_base="unidade")
        s.add(pa)
        s.commit()
        s.refresh(pa)
        pa_id = pa.id
        s.add(Estoque(nome="Sincrogest pct5 (1)", principio_ativo_id=pa_id, quantidade=5.0, unidade="unidade"))
        s.add(Estoque(nome="Sincrogest pct5 (2)", principio_ativo_id=pa_id, quantidade=5.0, unidade="unidade"))
        s.commit()

    c.put(f"/farmacia/principios/{pa_id}/estoque-minimo", json={"estoque_minimo_base": 12})
    item = next(p for p in c.get("/farmacia/principios").json() if p["id"] == pa_id)
    # 2 itens com saldo (2 "apresentações" na regra antiga) mas só 10 unidades reais — abaixo dos 12 pedidos
    assert item["total_base"] == 10.0
    assert item["abaixo_minimo"] is True


def test_atualizar_minimo_ja_existente_sobrescreve_um_a_um(client):
    c, engine, fa_id, fb_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Meloxicam", unidade_base="ml")
        s.add(pa)
        s.commit()
        s.refresh(pa)
        pa_id = pa.id

    c.put(f"/farmacia/principios/{pa_id}/estoque-minimo", json={"estoque_minimo_base": 100})
    r = c.put(f"/farmacia/principios/{pa_id}/estoque-minimo", json={"estoque_minimo_base": 150})
    assert r.status_code == 200
    with Session(engine) as s:
        overrides = s.exec(select(ParametroMinimoFarmacia).where(ParametroMinimoFarmacia.principio_ativo_id == pa_id)).all()
        assert len(overrides) == 1  # upsert, não duplica
        assert overrides[0].estoque_minimo_base == 150


def test_minimo_negativo_e_rejeitado(client):
    c, engine, fa_id, fb_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Meloxicam", unidade_base="ml")
        s.add(pa)
        s.commit()
        s.refresh(pa)
        pa_id = pa.id
    r = c.put(f"/farmacia/principios/{pa_id}/estoque-minimo", json={"estoque_minimo_base": -1})
    assert r.status_code == 400


def test_principio_sem_unidade_base_e_rejeitado(client):
    c, engine, fa_id, fb_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Sem unidade")  # unidade_base=None
        s.add(pa)
        s.commit()
        s.refresh(pa)
        pa_id = pa.id
    r = c.put(f"/farmacia/principios/{pa_id}/estoque-minimo", json={"estoque_minimo_base": 5})
    assert r.status_code == 400


def test_minimo_de_uma_fazenda_nao_vaza_para_outra(client):
    """Princípio GLOBAL (fazenda_id=None) — cada fazenda concilia o próprio
    mínimo sem afetar a outra, mesmo usando o mesmo princípio do catálogo."""
    c, engine, fa_id, fb_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Meloxicam", unidade_base="ml", fazenda_id=None)
        s.add(pa)
        s.commit()
        s.refresh(pa)
        pa_id = pa.id
        s.add(Estoque(nome="Maxicam", fazenda_id=fa_id, principio_ativo_id=pa_id, quantidade=50.0, unidade="ml"))
        s.add(Estoque(nome="Maxicam", fazenda_id=fb_id, principio_ativo_id=pa_id, quantidade=50.0, unidade="ml"))
        s.commit()

    r = c.put(f"/farmacia/principios/{pa_id}/estoque-minimo", json={"estoque_minimo_base": 100})
    assert r.status_code == 200
    assert r.json()["abaixo_minimo"] is True  # fazenda A: 50 < 100

    with Session(engine) as s:
        overrides = s.exec(select(ParametroMinimoFarmacia)).all()
        assert len(overrides) == 1
        assert overrides[0].fazenda_id == fa_id  # nunca gravou pra fazenda B
