"""
GET /producao/del-controle/divergencias e POST /producao/del-controle/reconstruir
— backfill de `ControleLeiteiro.del_no_controle`, mesmo padrão report-first do
ordem_parto (ver test_ordem_parto_reconstrucao_endpoint.py e a seção
"Reconstrução de ControleLeiteiro.del_no_controle" em
fazenda/api/routers/producao.py).

Cenário espelha um caso real reportado: vaca "131" pariu 19/06/2026, e dois
controles lançados em datas diferentes (31/07 e 13/08) tinham o MESMO
del_no_controle gravado (21) — sintoma do bug antigo, em que o campo era
copiado de `Animal.del_dias` (congelado) em vez de calculado a partir da
`data_controle` de cada registro contra a `Lactacao` aberta naquele dia.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, ControleLeiteiro, Fazenda, Lactacao


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        with Session(engine) as s:
            for fid in (1, 2):
                s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="produtivo", preco=0.0, ativo=True))

            # Fazenda 1 — vaca "131", cenário real reportado: pariu 19/06,
            # três controles — o primeiro já certo (19), os dois seguintes
            # com o mesmo DEL congelado (21), e um quarto ANTES do parto
            # (sem lactação aberta naquela data — correta vira None).
            s.add(Animal(numero="131", grupo_primario="01 - Alta", raca="Holandês", ativo=True, fazenda_id=1))
            s.add(Lactacao(numero_matriz="131", data_inicio=date(2026, 6, 19), origem="parto", numero_lactacao=1, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="131", data_controle=date(2026, 7, 8), producao_kg=15.0, del_no_controle=19, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="131", data_controle=date(2026, 7, 31), producao_kg=13.0, del_no_controle=21, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="131", data_controle=date(2026, 8, 13), producao_kg=10.0, del_no_controle=21, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="131", data_controle=date(2026, 5, 1), producao_kg=12.0, del_no_controle=21, fazenda_id=1))

            # Fazenda 2 — outro animal, cenário próprio — nunca deve aparecer
            # nem ser gravado atuando como fazenda 1, e vice-versa.
            s.add(Animal(numero="231", grupo_primario="01 - Alta", raca="Holandês", ativo=True, fazenda_id=2))
            s.add(Lactacao(numero_matriz="231", data_inicio=date(2026, 5, 1), origem="parto", numero_lactacao=1, fazenda_id=2))
            s.add(ControleLeiteiro(numero_matriz="231", data_controle=date(2026, 6, 1), producao_kg=22.0, del_no_controle=99, fazenda_id=2))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


def _atuar_como_fazenda(fazenda_id: int) -> None:
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestDivergenciasDelControle:
    def test_relatorio_reflete_divergencias_reais_da_fazenda(self, client):
        c, _ = client
        r = c.get("/producao/del-controle/divergencias")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["controles"] == 4
        # 08/07 (19) já está certo; 31/07 e 13/08 (ambos 21) estão errados;
        # 01/05 (antes do parto) não tem lactação aberta — vira "sem lactação".
        assert corpo["muda"] == 3
        assert corpo["sem_lactacao"] == 1
        amostra = {a["data_controle"]: a for a in corpo["amostra"]}
        assert amostra["2026-07-31"]["del_hoje"] == 21
        assert amostra["2026-07-31"]["del_correto"] == 42
        assert amostra["2026-08-13"]["del_hoje"] == 21
        assert amostra["2026-08-13"]["del_correto"] == 55
        assert amostra["2026-05-01"]["del_correto"] is None
        assert "2026-07-08" not in amostra  # já estava certo, não é divergência

    def test_relatorio_nao_grava_nada(self, client):
        c, engine = client
        c.get("/producao/del-controle/divergencias")
        with Session(engine) as s:
            por_data = {
                ctrl.data_controle: ctrl.del_no_controle
                for ctrl in s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 1)).all()
            }
            assert por_data[date(2026, 7, 31)] == 21
            assert por_data[date(2026, 8, 13)] == 21

    def test_divergencia_da_outra_fazenda_nunca_aparece(self, client):
        c, _ = client
        r = c.get("/producao/del-controle/divergencias")
        assert r.json()["controles"] == 4  # só os da fazenda 1

        _atuar_como_fazenda(2)
        r2 = c.get("/producao/del-controle/divergencias")
        assert r2.json()["controles"] == 1  # só o da fazenda 2
        assert r2.json()["muda"] == 1


class TestPermissaoReconstruirDelControle:
    def test_usuario_comum_sem_papel_admin_e_403(self, client):
        c, _ = client
        import main
        from fazenda.auth import get_current_user

        class _FakeOperador:
            id = 3
            papel = "operador"
            ativo = True
            username = "operador"
            email = "operador@exemplo.com"

        main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()
        r = c.post("/producao/del-controle/reconstruir", json={"confirmar": True})
        assert r.status_code == 403


class TestReconstruirDelControle:
    def test_sem_confirmar_e_400_e_nao_grava_nada(self, client):
        c, engine = client
        r = c.post("/producao/del-controle/reconstruir", json={})
        assert r.status_code == 400
        with Session(engine) as s:
            controle = s.exec(
                select(ControleLeiteiro).where(ControleLeiteiro.data_controle == date(2026, 7, 31))
            ).first()
            assert controle.del_no_controle == 21

    def test_confirmar_true_grava_exatamente_os_valores_corretos(self, client):
        c, engine = client
        r = c.post("/producao/del-controle/reconstruir", json={"confirmar": True})
        assert r.status_code == 200
        # 3 divergem (07/31, 08/13, e o "sem lactação" 05/01), mas só os 2
        # com resposta conhecida são de fato GRAVADOS — o "sem lactação" fica
        # intocado (ver test_controle_sem_lactacao_aberta_fica_intocado).
        assert r.json()["gravados"] == 2

        with Session(engine) as s:
            por_data = {
                ctrl.data_controle: ctrl.del_no_controle
                for ctrl in s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 1)).all()
            }
            assert por_data[date(2026, 7, 8)] == 19  # já estava certo, continua
            assert por_data[date(2026, 7, 31)] == 42
            assert por_data[date(2026, 8, 13)] == 55

    def test_controle_sem_lactacao_aberta_fica_intocado(self, client):
        """Sem lactação aberta na data, a resposta correta é genuinamente
        desconhecida — não pode virar um palpite, e o valor antigo (mesmo
        errado) não pode ser apagado silenciosamente."""
        c, engine = client
        c.post("/producao/del-controle/reconstruir", json={"confirmar": True})
        with Session(engine) as s:
            controle = s.exec(
                select(ControleLeiteiro).where(
                    ControleLeiteiro.fazenda_id == 1, ControleLeiteiro.data_controle == date(2026, 5, 1),
                )
            ).first()
            assert controle.del_no_controle == 21  # continua o que já estava, não vira None

    def test_rodar_de_novo_nao_regrava_o_que_ja_esta_certo(self, client):
        c, _ = client
        r1 = c.post("/producao/del-controle/reconstruir", json={"confirmar": True})
        assert r1.json()["gravados"] == 2
        r2 = c.post("/producao/del-controle/reconstruir", json={"confirmar": True})
        assert r2.json()["gravados"] == 0

    def test_isolamento_por_fazenda_na_gravacao(self, client):
        c, engine = client
        c.post("/producao/del-controle/reconstruir", json={"confirmar": True})
        with Session(engine) as s:
            controle_f2 = s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 2)).first()
            assert controle_f2.del_no_controle == 99  # nunca tocado atuando como fazenda 1

        _atuar_como_fazenda(2)
        r = c.post("/producao/del-controle/reconstruir", json={"confirmar": True})
        assert r.json()["gravados"] == 1
        with Session(engine) as s:
            controle_f2 = s.exec(select(ControleLeiteiro).where(ControleLeiteiro.fazenda_id == 2)).first()
            assert controle_f2.del_no_controle == 31  # 01/05 a 01/06
