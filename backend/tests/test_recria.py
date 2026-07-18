"""
Módulo Recria — Dossiê Zootécnico.

Cobre o motor de coorte (curva por idade, ponto crítico, incidência por fase)
e os endpoints do router: curva de saúde, peso-alvo, ocorrências e cadastros.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, PesagemCorporal, PesoAlvoIdade
from fazenda.rules.coorte import curva_casos_por_idade, incidencia_por_fase, ponto_critico


# --- Unidade: motor de coorte ----------------------------------------------
class TestCoorte:
    def test_ponto_critico_encontra_janela_do_pico(self):
        idades = [2, 7, 8, 9, 9, 9, 10, 10, 11, 25, 40]
        pc = ponto_critico(curva_casos_por_idade(idades))
        assert pc["dia_pico"] == 9
        assert pc["dia_min"] <= 9 <= pc["dia_max"]
        assert pc["pct_na_janela"] >= 50

    def test_curva_ignora_fora_do_limite(self):
        curva = curva_casos_por_idade([5, 5, 400, -3], limite_dias=300)
        assert curva == [{"dia": 5, "casos": 2}]

    def test_incidencia_denominador_por_fase(self):
        pares = [("1", 9), ("2", 9), ("3", 200)]
        idade_atual = {"1": 300, "2": 300, "3": 300, "4": 300, "5": 20}
        fases = [{"nome": "0–30", "dia_min": 0, "dia_max": 30}]
        r = incidencia_por_fase(pares, idade_atual, fases)[0]
        # 2 animais afetados (1 e 2), denominador = 4 (todos com idade>=0 exceto... todos>=0);
        # aqui todos têm idade>=0, então 5 em risco; 2 afetados → 40%.
        assert r["animais_afetados"] == 2
        assert r["animais_em_risco"] == 5
        assert r["incidencia_pct"] == 40.0


# --- Integração: endpoints -------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1; papel = "admin"; ativo = True; username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    from fazenda.api.routers.recria import seed_recria

    with TestClient(main.app) as c:
        with Session(engine) as s:
            seed_recria(s)  # metas, curva de peso-alvo e janelas padrão no engine de teste
            # Bezerras nascidas em datas diferentes.
            s.add(Animal(numero="101", data_nasc=date(2026, 1, 1), ativo=True))
            s.add(Animal(numero="102", data_nasc=date(2026, 1, 1), ativo=True))
            s.add(Animal(numero="103", data_nasc=date(2026, 1, 1), ativo=True))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


class TestOcorrenciasECurva:
    def test_lanca_ocorrencia_e_curva(self, client):
        c, _ = client
        # 101 e 102 com diarreia aos ~9 dias; 103 aos 40.
        for num, dia in [("101", 9), ("102", 9), ("103", 40)]:
            r = c.post("/recria/ocorrencias", json={
                "numero_matriz": num, "doenca": "Diarreia",
                "data_ocorrencia": (date(2026, 1, 1) + timedelta(days=dia)).isoformat(),
            })
            assert r.status_code == 201
        # Doenças com casos
        assert any(d["doenca"] == "Diarreia" and d["casos"] == 3 for d in c.get("/recria/doencas").json())
        # Curva + ponto crítico
        r = c.get("/recria/saude/curva", params={"doenca": "Diarreia"})
        j = r.json()
        assert j["total_casos"] == 3
        assert j["ponto_critico"]["dia_pico"] == 9
        assert any(p["dia"] == 9 and p["casos"] == 2 for p in j["curva"])
        # incidência por fase existe
        assert any(f["casos"] > 0 for f in j["incidencia_por_fase"])

    def test_excluir_ocorrencia(self, client):
        c, _ = client
        rid = c.post("/recria/ocorrencias", json={"numero_matriz": "101", "doenca": "Pneumonia", "data_ocorrencia": "2026-02-01"}).json()["id"]
        assert c.delete(f"/recria/ocorrencias/{rid}").json()["ok"] is True
        assert c.get("/recria/ocorrencias", params={"doenca": "Pneumonia"}).json() == []


class TestPesoAlvo:
    def test_peso_alvo_semeado_e_comparacao(self, client):
        c, engine = client
        # Seed padrão existe (lifespan rodou). Adiciona pesagem real no mês 2.
        with Session(engine) as s:
            s.add(PesagemCorporal(numero_matriz="101", data_pesagem=date(2026, 3, 1), peso_kg=60.0))  # ~59 dias → mês 2
            s.commit()
        linhas = c.get("/recria/crescimento/peso-alvo").json()["linhas"]
        m2 = next((l for l in linhas if l["mes"] == 2), None)
        assert m2 is not None
        assert m2["peso_medio_real"] == 60.0
        assert m2["peso_min_alvo"] is not None  # veio do seed

    def test_upsert_peso_alvo(self, client):
        c, _ = client
        c.post("/recria/peso-alvo", json={"mes": 3, "peso_min_kg": 80, "peso_max_kg": 110})
        c.post("/recria/peso-alvo", json={"mes": 3, "peso_min_kg": 85, "peso_max_kg": 115})
        linhas = [l for l in c.get("/recria/peso-alvo").json() if l["mes"] == 3]
        assert len(linhas) == 1 and linhas[0]["peso_min_kg"] == 85


class TestCadastros:
    def test_metas_padrao_e_edicao(self, client):
        c, _ = client
        m = c.get("/recria/metas").json()
        assert m["idade_parto_meses"] == 24.0
        c.put("/recria/metas", json={**{k: v for k, v in m.items() if k in (
            "idade_parto_meses", "idade_prenhez_meses", "idade_1a_cobertura_meses",
            "taxa_prenhez_meta", "desvio_padrao_meta", "custo_diario_recria")}, "custo_diario_recria": 15.0})
        assert c.get("/recria/metas").json()["custo_diario_recria"] == 15.0

    def test_janelas_semeadas(self, client):
        c, _ = client
        janelas = c.get("/recria/janelas").json()
        assert any(j["doenca"] == "Diarreia" for j in janelas)

    def test_fase_crud(self, client):
        c, _ = client
        fid = c.post("/recria/fases", json={"nome": "Teste", "dia_min": 0, "dia_max": 30, "ordem": 1}).json()["id"]
        assert any(f["nome"] == "Teste" for f in c.get("/recria/fases").json())
        c.delete(f"/recria/fases/{fid}")
        assert not any(f["nome"] == "Teste" for f in c.get("/recria/fases").json())


class TestBenchmark:
    def test_benchmark_semeado_e_faixa(self, client):
        c, _ = client
        linhas = c.get("/recria/benchmark").json()
        colostro = next((b for b in linhas if "colostragem" in b["indicador"].lower()), None)
        assert colostro is not None
        assert colostro["valor_fazenda"] == 57
        assert colostro["faixa_fazenda"] is not None  # classificado
        mort = next((b for b in linhas if "mortalidade" in b["indicador"].lower()), None)
        assert mort["faixa_fazenda"] == "TOP 5%"  # 2,2 é o melhor corte

    def test_benchmark_upsert(self, client):
        c, _ = client
        c.post("/recria/benchmark", json={"indicador": "Ocorrência de diarreia", "unidade": "%", "melhor_e_maior": False,
                                          "top5": 3.6, "top25": 25, "top75": 68.4, "valor_fazenda": 10, "ordem": 4})
        linhas = [b for b in c.get("/recria/benchmark").json() if b["indicador"] == "Ocorrência de diarreia"]
        assert len(linhas) == 1 and linhas[0]["valor_fazenda"] == 10


class TestReproducao:
    def test_idade_ao_primeiro_parto(self, client):
        from fazenda.models import Animal, Parto
        c, engine = client
        with Session(engine) as s:
            # 3 novilhas nascidas 2024-01-01, 1º parto em idades ~23,24,31 meses.
            for num, meses in [("201", 23), ("202", 24), ("203", 31)]:
                s.add(Animal(numero=num, data_nasc=date(2024, 1, 1), ativo=True))
                s.add(Parto(numero_matriz=num, data_parto=date(2024, 1, 1) + timedelta(days=round(meses * 30.44)), ordem_parto=1))
            s.commit()
        j = c.get("/recria/reproducao/idade-parto").json()
        assert j["estatisticas"]["n"] == 3
        assert 25.5 <= j["estatisticas"]["media"] <= 26.5
        assert j["custo_excedente"]["custo_total"] > 0  # há novilha acima de 24 meses
        assert any(d["mes"] == 24 for d in j["distribuicao"])

    def test_dossie_reune_secoes_e_kpis(self, client):
        from fazenda.models import Animal, Parto
        c, engine = client
        with Session(engine) as s:
            for num, meses in [("401", 23), ("402", 30)]:
                s.add(Animal(numero=num, data_nasc=date(2024, 1, 1), ativo=True))
                s.add(Parto(numero_matriz=num, data_parto=date(2024, 1, 1) + timedelta(days=round(meses * 30.44)), ordem_parto=1))
            s.commit()
        j = c.get("/recria/dossie").json()
        assert j["kpis"]["n_animais_1o_parto"] == 2
        assert j["kpis"]["idade_media_1o_parto"] is not None
        titulos = [sec["titulo"] for sec in j["secoes"]]
        assert any("idade ao 1º parto" in t for t in titulos)
        # Cada seção tem colunas e linhas prontas para o PDF.
        for sec in j["secoes"]:
            assert sec["colunas"] and sec["linhas"]

    def test_importar_dairycomp_cria_nascimento_e_parto(self, client):
        from fazenda.models import Animal, Parto
        c, engine = client
        csv = "numero_matriz,data_nascimento,data_parto,ordem_parto\n501,10/03/2022,05/06/2024,1\n"
        r = c.post("/importar/dairycomp", files={"file": ("dairycomp.csv", csv, "text/csv")})
        assert r.status_code == 200
        assert r.json()["criados"] == 1
        with Session(engine) as s:
            a = s.exec(select(Animal).where(Animal.numero == "501")).first()
            assert a is not None and a.data_nasc == date(2022, 3, 10)
            p = s.exec(select(Parto).where(Parto.numero_matriz == "501")).first()
            assert p is not None and p.data_parto == date(2024, 6, 5)
        # Reimportar não duplica o parto (dedup por animal + data).
        r2 = c.post("/importar/dairycomp", files={"file": ("dairycomp.csv", csv, "text/csv")})
        assert r2.json()["criados"] == 0

    def test_taxa_prenhez_ciclos(self, client):
        from fazenda.models import Servico
        c, engine = client
        with Session(engine) as s:
            # 2 serviços no 1º ciclo: um prenhe, um vazio.
            s.add(Servico(numero_matriz="301", data_servico=date(2026, 3, 1), diagnostico="POSITIVO"))
            s.add(Servico(numero_matriz="302", data_servico=date(2026, 3, 5), diagnostico="NEGATIVO"))
            s.commit()
        j = c.get("/recria/reproducao/taxa-prenhez", params={"ini": "2026-03-01", "fim": "2026-03-21"}).json()
        assert len(j["ciclos"]) >= 1
        c1 = j["ciclos"][0]
        assert c1["servidos"] == 2 and c1["prenhes"] == 1
        assert c1["taxa_concepcao"] == 50.0


class TestCocho:
    def test_registro_e_ims(self, client):
        c, _ = client
        r = c.post("/recria/cocho", json={"data": "2026-03-01", "lote": "Bezerras", "num_animais": 10,
                                          "kg_ofertado": 250, "kg_sobra": 25, "kg_formulado": 225})
        assert r.status_code == 201
        j = r.json()
        assert j["kg_consumido"] == 225.0
        assert j["pct_sobra"] == 10.0
        assert j["ims_consumida_animal"] == 22.5
        lst = c.get("/recria/cocho", params={"lote": "Bezerras"}).json()
        assert lst["registros"][0]["ims_consumida_animal"] == 22.5
        assert "Bezerras" in lst["lotes"]

    def test_sobra_maior_que_ofertado_erro(self, client):
        c, _ = client
        r = c.post("/recria/cocho", json={"data": "2026-03-01", "lote": "X", "num_animais": 5, "kg_ofertado": 10, "kg_sobra": 20})
        assert r.status_code == 400


class TestCategoriaManejo:
    def test_composicao_e_classificacao(self, client):
        from fazenda.models import Animal, PesagemCorporal
        from datetime import date, timedelta
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="C1", data_nasc=hoje - timedelta(days=30), ativo=True, sexo="F"))    # aleitamento
            s.add(Animal(numero="C2", data_nasc=hoje - timedelta(days=150), ativo=True, sexo="F"))   # recria 1
            s.add(Animal(numero="C3", data_nasc=hoje - timedelta(days=300), ativo=True, sexo="F"))   # recria 2
            s.add(Animal(numero="C4", data_nasc=hoje - timedelta(days=420), ativo=True, sexo="F", sit_rep="Ges."))
            s.add(PesagemCorporal(numero_matriz="C4", data_pesagem=hoje, peso_kg=400))               # apta → prenha
            s.commit()
        j = c.get("/recria/categorias/composicao").json()
        comp = {x["categoria"]: x["n"] for x in j["composicao"]}
        assert comp.get("Aleitamento") == 1
        assert comp.get("Recria 1", 0) >= 1  # C2 + os animais do fixture (~192 dias)
        assert comp.get("Recria 2") == 1
        # "Prenha" (situação reprodutiva) tem prioridade sobre a "Recria apta"
        # legada (usa_status_reprodutivo) — ver _CATEGORIAS_NOVAS_PADRAO.
        assert comp.get("Prenha") == 1

    def test_categorias_semeadas_crud(self, client):
        c, _ = client
        cats = c.get("/recria/categorias").json()
        assert any(x["nome"] == "Aleitamento" for x in cats)
        cid = c.post("/recria/categorias", json={"nome": "Teste", "dia_min": 0, "dia_max": 10, "ordem": 9}).json()["id"]
        c.put(f"/recria/categorias/{cid}", json={"nome": "Teste2", "dia_min": 0, "dia_max": 20, "ordem": 9})
        assert any(x["nome"] == "Teste2" for x in c.get("/recria/categorias").json())
        c.delete(f"/recria/categorias/{cid}")
        assert not any(x["nome"] == "Teste2" for x in c.get("/recria/categorias").json())
