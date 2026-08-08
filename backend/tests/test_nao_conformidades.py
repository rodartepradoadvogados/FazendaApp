"""
Testes do Relatório de Não Conformidades — agregador único que reúne o que
está fora da meta em reprodução, recria, financeiro e manejo.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, EstoqueSemen, LancamentoItem, Parto, PlanoContaGerencial, Servico


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _hoje():
    return date.today()


class TestNaoConformidades:
    def test_fazenda_vazia_so_traz_listas_de_manejo_zeradas(self, client):
        c, engine = client
        r = c.get("/nao-conformidades/")
        assert r.status_code == 200
        corpo = r.json()
        # Sem animais/serviços/contas: benchmark reprodutivo, recria e
        # financeiro não têm dado suficiente para avaliar — só sobram as 6
        # listas de manejo, todas em dia (zero fora do padrão).
        assert corpo["itens"], "manejo deve sempre aparecer, mesmo zerado"
        assert all(i["dominio"] == "manejo" for i in corpo["itens"])
        assert all(i["status"] == "ok" for i in corpo["itens"])
        assert corpo["resumo"]["critico"] == 0
        assert corpo["resumo"]["atencao"] == 0
        assert corpo["sem_meta"] == []

    def test_toque_atrasado_alem_do_limite_entra_como_critico(self, client):
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="900", sexo="F", ativo=True, del_dias=300, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="900", data_parto=hoje - timedelta(days=300), ordem_parto=1))
            # 70 dias inseminada sem diagnóstico: dias_toque(30) + visita_vet(30)
            # = 60 já passado -> cor "vermelho" em a_tocar.
            s.add(Servico(numero_matriz="900", data_servico=hoje - timedelta(days=70),
                          ordem_tentativa=1, reprodutor="Touro X"))
            s.commit()
        r = c.get("/nao-conformidades/")
        corpo = r.json()
        item = next(i for i in corpo["itens"] if i["chave"] == "manejo_a_tocar")
        assert item["valor"] == 1
        assert item["status"] == "atencao"  # 1 animal -> faixa "atenção" (1-2)
        assert item["rota"] == "/relatorios"

        # 3 animais no mesmo estado -> vira "crítico" (>= 3).
        with Session(engine) as s:
            for num in ("901", "902"):
                s.add(Animal(numero=num, sexo="F", ativo=True, del_dias=300, sit_rep="Vaz. apt."))
                s.add(Parto(numero_matriz=num, data_parto=hoje - timedelta(days=300), ordem_parto=1))
                s.add(Servico(numero_matriz=num, data_servico=hoje - timedelta(days=70),
                              ordem_tentativa=1, reprodutor="Touro X"))
            s.commit()
        r2 = c.get("/nao-conformidades/")
        item2 = next(i for i in r2.json()["itens"] if i["chave"] == "manejo_a_tocar")
        assert item2["valor"] == 3
        assert item2["status"] == "critico"

    def test_rmca_so_aparece_quando_configurado(self, client):
        c, engine = client
        r = c.get("/nao-conformidades/")
        assert not any(i["chave"].startswith("rmca_") for i in r.json()["itens"])

        with Session(engine) as s:
            s.add(PlanoContaGerencial(codigo="2.01.01.01", nome="Leite", ativa=True, rmca_receita_leite=True))
            s.add(PlanoContaGerencial(codigo="3.01.01.01", nome="Ração", ativa=True, rmca_custo_alimentacao=True))
            s.commit()
        c.post("/financeiro/lancamentos", json={
            "tipo": "receita",
            "itens": [{"produto": "Leite", "codigo_conta_gerencial": "2.01.01.01", "valor_total": 1000.0}],
            "data_competencia": _hoje().isoformat(),
        })
        c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração", "codigo_conta_gerencial": "3.01.01.01", "valor_total": 5000.0}],
            "data_competencia": _hoje().isoformat(),
        })
        r2 = c.get("/nao-conformidades/")
        item = next(i for i in r2.json()["itens"] if i["chave"] == "rmca_gerencial")
        assert item["valor"] == -4000.0
        assert item["meta"] == 0  # padrão de meta_rmca
        assert item["status"] == "critico"  # bem abaixo da meta

    def test_resumo_bate_com_contagem_dos_itens(self, client):
        c, engine = client
        r = c.get("/nao-conformidades/")
        corpo = r.json()
        criticos = sum(1 for i in corpo["itens"] if i["status"] == "critico")
        atencoes = sum(1 for i in corpo["itens"] if i["status"] == "atencao")
        oks = sum(1 for i in corpo["itens"] if i["status"] == "ok")
        assert corpo["resumo"] == {
            "critico": criticos, "atencao": atencoes, "ok": oks, "total": len(corpo["itens"]),
        }
