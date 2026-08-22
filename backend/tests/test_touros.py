"""Testes do catálogo de touros NAAB: importador da planilha completa
(dezenas de colunas, ex. Alta Genetics) e cadastro manual."""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Touro
from fazenda.rules.touros import eh_planilha_rica, importar_touros_planilha_rica


def _xlsx_bytes(headers, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Réplica em miniatura do cabeçalho real da Alta Genetics: "Gordura"/"%
# Gordura" e "Proteína"/"Prot%" normalizam para o mesmo apelido genérico, e "D
# / H" aparece duas vezes — exatamente os casos que o importador por posição
# precisa acertar.
HEADERS_RICOS = (
    ["Código NAAB", "Nome", "Nome completo", "Raça"]
    + [f"Col{i}" for i in range(4, 6)]
    + ["TPI", "NM$"]
    + [f"Col{i}" for i in range(8, 11)]
    + ["Leite", "Proteína", "Prot%", "Gordura", "% Gordura"]
    + [f"Col{i}" for i in range(16, 27)]
    + ["SCS"]
    + [f"Col{i}" for i in range(28, 64)]
    + ["PTAT"]
    + [f"Col{i}" for i in range(65, 71)]
    + ["D / H"]
    + [f"Col{i}" for i in range(72, 100)]
)


def _linha_completa(**overrides):
    linha = [None] * len(HEADERS_RICOS)
    for campo, valor in overrides.items():
        linha[HEADERS_RICOS.index(campo)] = valor
    return linha


class TestDeteccaoFormato:
    def test_planilha_rica_detectada(self):
        assert eh_planilha_rica(list(HEADERS_RICOS)) is True

    def test_planilha_simples_nao_e_rica(self):
        assert eh_planilha_rica(["NAAB", "Nome", "TPI"]) is False


class TestImportarPlanilhaRica:
    @pytest.fixture
    def session(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            yield s

    def test_mapeia_campos_curados_sem_trocar_kg_por_pct(self, session):
        # "Proteína"/"Gordura" (kg) não podem cair em proteina_pct/gordura_pct
        # só porque normalizam parecido com "Prot%"/"% Gordura".
        conteudo = _xlsx_bytes(HEADERS_RICOS, [_linha_completa(**{
            "Código NAAB": "007HO99999", "Nome": "TouroTeste", "Nome completo": "TOURO TESTE-ET",
            "Raça": "HO", "TPI": 3000, "NM$": 700, "Leite": 2500, "Proteína": 80, "Prot%": -0.05,
            "Gordura": 90, "% Gordura": -0.1, "SCS": 2.9, "PTAT": 1.2, "D / H": "10/5",
        })])
        resultado = importar_touros_planilha_rica(session, conteudo, "Alta", "Teste")
        assert resultado == {"criados": 1, "atualizados": 0, "erros": []}

        from sqlmodel import select
        t = session.exec(select(Touro).where(Touro.naab == "007HO99999")).first()
        assert t.nome == "TouroTeste"
        assert t.nome_completo == "TOURO TESTE-ET"
        assert t.tpi == 3000
        assert t.nm_dolar == 700
        assert t.leite_kg == 2500
        assert t.proteina_kg == 80
        assert t.proteina_pct == -0.05
        assert t.gordura_kg == 90
        assert t.gordura_pct == -0.1
        assert t.ccs_score == 2.9
        assert t.tipo_composto == 1.2

    def test_preserva_todos_os_dados_em_dados_extra(self, session):
        conteudo = _xlsx_bytes(HEADERS_RICOS, [_linha_completa(**{
            "Código NAAB": "007HO11111", "Nome": "OutroTouro", "D / H": "1/2",
        })])
        importar_touros_planilha_rica(session, conteudo, "Alta", "Teste")
        from sqlmodel import select
        t = session.exec(select(Touro).where(Touro.naab == "007HO11111")).first()
        extra = json.loads(t.dados_extra)
        assert ["Código NAAB", "007HO11111"] in extra
        assert ["Nome", "OutroTouro"] in extra
        assert ["D / H", "1/2"] in extra

    def test_cabecalho_duplicado_preserva_os_dois_valores(self, session):
        # A planilha real tem "D / H" duas vezes (produção e conformação) —
        # dados_extra precisa manter as duas ocorrências, sem uma sobrescrever
        # a outra.
        headers = ["Código NAAB", "Nome", "D / H", "D / H"]
        conteudo = _xlsx_bytes(headers, [["007HO12121", "Duplo", "10/5", "20/8"]])
        importar_touros_planilha_rica(session, conteudo, "Alta", "Teste")
        from sqlmodel import select
        t = session.exec(select(Touro).where(Touro.naab == "007HO12121")).first()
        extra = json.loads(t.dados_extra)
        assert extra.count(["D / H", "10/5"]) == 1
        assert extra.count(["D / H", "20/8"]) == 1

    def test_upsert_por_naab_nao_duplica(self, session):
        conteudo = _xlsx_bytes(HEADERS_RICOS, [
            _linha_completa(**{"Código NAAB": "007HO22222", "Nome": "Primeiro", "TPI": 100}),
        ])
        importar_touros_planilha_rica(session, conteudo, "Alta", None)
        conteudo2 = _xlsx_bytes(HEADERS_RICOS, [
            _linha_completa(**{"Código NAAB": "007HO22222", "Nome": "Atualizado", "TPI": 200}),
        ])
        resultado = importar_touros_planilha_rica(session, conteudo2, "Alta", None)
        assert resultado["criados"] == 0
        assert resultado["atualizados"] == 1
        from sqlmodel import select
        todos = session.exec(select(Touro).where(Touro.naab == "007HO22222")).all()
        assert len(todos) == 1
        assert todos[0].nome == "Atualizado"
        assert todos[0].tpi == 200


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


class TestCadastroManual:
    def test_criar_touro_so_com_naab_e_nome(self, client):
        c, _engine = client
        resp = c.post("/cadastro/touros", json={"naab": "007HO33333", "nome": "Manual"})
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["naab"] == "007HO33333"
        assert corpo["nome"] == "Manual"
        assert corpo["tpi"] is None

    def test_criar_touro_sem_nome_falha(self, client):
        c, _engine = client
        resp = c.post("/cadastro/touros", json={"naab": "007HO44444", "nome": "  "})
        assert resp.status_code == 400

    def test_criar_touro_com_dados_extra(self, client):
        c, _engine = client
        resp = c.post("/cadastro/touros", json={
            "naab": "007HO55555", "nome": "ComExtra", "tpi": 3100,
            "dados_extra": [["Feed Saved", "24"], ["EFI", "12.3"]],
        })
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert json.loads(corpo["dados_extra"]) == [["Feed Saved", "24"], ["EFI", "12.3"]]

    def test_naab_duplicado_falha(self, client):
        c, _engine = client
        c.post("/cadastro/touros", json={"naab": "007HO66666", "nome": "A"})
        resp = c.post("/cadastro/touros", json={"naab": "007HO66666", "nome": "B"})
        assert resp.status_code == 400

    def test_atualizar_touro(self, client):
        c, _engine = client
        criado = c.post("/cadastro/touros", json={"naab": "007HO77777", "nome": "Original"}).json()
        resp = c.put(f"/cadastro/touros/{criado['id']}", json={"naab": "007HO77777", "nome": "Editado", "tpi": 2900})
        assert resp.status_code == 200, resp.text
        assert resp.json()["nome"] == "Editado"
        assert resp.json()["tpi"] == 2900

    def test_excluir_touro(self, client):
        c, _engine = client
        criado = c.post("/cadastro/touros", json={"naab": "007HO88888", "nome": "ParaExcluir"}).json()
        resp = c.delete(f"/cadastro/touros/{criado['id']}")
        assert resp.status_code == 200
        assert c.get("/cadastro/touros").status_code == 200
        naabs = [t["naab"] for t in c.get("/cadastro/touros").json()]
        assert "007HO88888" not in naabs

    def test_campos_planilha_lista_rotulos_conhecidos(self, client):
        c, _engine = client
        resp = c.get("/cadastro/touros/campos-planilha")
        assert resp.status_code == 200
        rotulos = resp.json()
        assert "TPI" in rotulos
        assert "NM$" in rotulos
        assert "naab" not in [r.lower() for r in rotulos]

    def test_recarregar_catalogo_chama_bootstrap_forcado(self, client, monkeypatch):
        c, _engine = client
        chamadas = []

        def _fake_bootstrap(session, forcar=False):
            chamadas.append(forcar)
            session.add(Touro(naab="000FAKE001", nome="Recarregado"))
            session.commit()

        monkeypatch.setattr("fazenda.rules.touros.bootstrap_touros_naab", _fake_bootstrap)
        resp = c.post("/cadastro/touros/recarregar-catalogo")
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["touros_depois"] == corpo["touros_antes"] + 1
        assert chamadas == [True]


class TestProvaMediaSemen:
    def test_simples_e_ponderada_entre_touros_com_dose_em_estoque(self, client):
        c, engine = client
        from fazenda.models import EstoqueSemen

        with Session(engine) as s:
            s.add(Touro(naab="1HO001", nome="TOURO A", tpi=2900, leite_kg=800))
            s.add(Touro(naab="1HO002", nome="TOURO B", tpi=2700, leite_kg=600))
            s.add(EstoqueSemen(touro_nome="TOURO A", naab="1HO001", tipo="convencional", doses=3))
            s.add(EstoqueSemen(touro_nome="TOURO B", naab="1HO002", tipo="convencional", doses=1))
            # Sêmen de touro de monta natural (tipo "fazenda") não entra em nenhum dos dois recortes.
            s.add(EstoqueSemen(touro_nome="TOURO FAZENDA", tipo="fazenda", doses=99))
            # Zero doses em estoque: fora dos dois recortes (não é "pelo menos 1 dose").
            s.add(Touro(naab="1HO099", nome="TOURO ZERADO", tpi=9999))
            s.add(EstoqueSemen(touro_nome="TOURO ZERADO", naab="1HO099", tipo="convencional", doses=0))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-media")
        assert resp.status_code == 200, resp.text
        corpo = resp.json()

        # Simples: cada touro pesa 1, tenha 1 dose ou 3 — (2900 + 2700) / 2 = 2800.
        assert corpo["simples"]["touros_considerados"] == 2
        assert corpo["simples"]["prova"]["tpi"] == 2800.0

        # Ponderada: 3 doses do touro A (TPI 2900) + 1 dose do touro B (TPI 2700).
        # Média ponderada = (2900*3 + 2700*1) / 4 = 2850.
        assert corpo["ponderada"]["total_doses"] == 4
        assert corpo["ponderada"]["touros_considerados"] == 2
        assert corpo["ponderada"]["prova"]["tpi"] == 2850.0

    def test_touro_sem_prova_naquele_indicador_nao_entra_no_calculo(self, client):
        c, engine = client
        from fazenda.models import EstoqueSemen

        with Session(engine) as s:
            s.add(Touro(naab="1HO004", nome="TOURO D", tpi=2500, nm_dolar=None))
            s.add(EstoqueSemen(touro_nome="TOURO D", naab="1HO004", tipo="convencional", doses=5))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-media")
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["ponderada"]["prova"]["tpi"] == 2500.0
        assert corpo["ponderada"]["prova"]["nm_dolar"] is None
        assert corpo["simples"]["prova"]["tpi"] == 2500.0
        assert corpo["simples"]["prova"]["nm_dolar"] is None

    def test_incluir_fazenda_traz_touro_de_monta_natural_cadastrado_no_naab(self, client):
        # Touro da fazenda (monta natural) que TAMBÉM está no catálogo NAAB
        # (ex.: foi comprado como sêmen antes de virar reprodutor natural) —
        # por padrão fica de fora; com a flag, entra como qualquer outro.
        c, engine = client
        from fazenda.models import EstoqueSemen

        with Session(engine) as s:
            s.add(Touro(naab="1HO005", nome="TOURO FAZENDA", tpi=2000))
            s.add(EstoqueSemen(touro_nome="TOURO FAZENDA", naab="1HO005", tipo="fazenda", doses=10))
            s.commit()

        resp_padrao = c.get("/cadastro/estoque-semen/prova-media")
        assert resp_padrao.json()["ponderada"]["touros_considerados"] == 0

        resp_incluindo = c.get("/cadastro/estoque-semen/prova-media", params={"incluir_fazenda": "true"})
        corpo = resp_incluindo.json()
        assert corpo["ponderada"]["touros_considerados"] == 1
        assert corpo["ponderada"]["prova"]["tpi"] == 2000.0


class TestProvaAoVivoSemen:
    """"Prova ao vivo" (Estoque de Sêmen > Prova média) — os MESMOS
    indicadores genéticos do catálogo (ver TestProvaMediaSemen), ponderados
    pelo uso real (nº de serviços) de cada touro na fazenda, não pela taxa de
    concepção/resultado reprodutivo do rebanho."""

    def _touro_e_estoque(self, session, *, naab, nome, tipo="convencional", **provas):
        from fazenda.models import EstoqueSemen

        session.add(Touro(naab=naab, nome=nome, **provas))
        session.add(EstoqueSemen(touro_nome=nome, naab=naab, tipo=tipo, doses=1))

    def test_pondera_indicador_genetico_pelo_numero_de_servicos(self, client):
        c, engine = client
        from datetime import date
        from fazenda.models import Servico

        d = date(2026, 1, 10)
        with Session(engine) as s:
            self._touro_e_estoque(s, naab="1HO101", nome="TOURO A", tpi=3000)
            self._touro_e_estoque(s, naab="1HO102", nome="TOURO B", tpi=2000)
            # TOURO A usado em 3 serviços, TOURO B em 1 — a ponderação é pelo
            # uso, não pelas doses em estoque (ambos têm 1 dose cadastrada).
            s.add(Servico(numero_matriz="1", reprodutor="TOURO A", data_servico=d))
            s.add(Servico(numero_matriz="2", reprodutor="TOURO A", data_servico=d))
            s.add(Servico(numero_matriz="3", reprodutor="TOURO A", data_servico=d))
            s.add(Servico(numero_matriz="4", reprodutor="TOURO B", data_servico=d))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-ao-vivo")
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        # (3000*3 + 2000*1) / 4 = 2750 — não é mais taxa de concepção/serviços
        # elegíveis/positivos, é o índice genético do catálogo.
        assert corpo["prova"]["tpi"] == 2750.0
        assert corpo["total_servicos"] == 4
        assert corpo["touros_considerados"] == 2
        touros = {t["touro"]: t["servicos"] for t in corpo["touros"]}
        assert touros == {"TOURO A": 3, "TOURO B": 1}
        assert "elegiveis" not in corpo
        assert "taxa_concepcao" not in corpo

    def test_servico_sem_touro_nao_entra(self, client):
        c, engine = client
        from datetime import date
        from fazenda.models import Servico

        with Session(engine) as s:
            s.add(Servico(numero_matriz="1", data_servico=date(2026, 1, 1)))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-ao-vivo")
        assert resp.status_code == 200
        assert resp.json()["touros"] == []
        assert resp.json()["touros_considerados"] == 0

    def test_touro_sem_casamento_no_catalogo_nao_entra(self, client):
        # Reprodutor usado nos serviços mas sem NAAB/catálogo cadastrado —
        # não tem nenhum indicador genético para ponderar.
        c, engine = client
        from datetime import date
        from fazenda.models import Servico

        with Session(engine) as s:
            s.add(Servico(numero_matriz="1", reprodutor="TOURO SEM CATALOGO", data_servico=date(2026, 1, 1)))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-ao-vivo")
        assert resp.status_code == 200
        assert resp.json()["touros"] == []
        assert resp.json()["touros_considerados"] == 0

    def test_touro_da_fazenda_fica_de_fora_por_padrao(self, client):
        c, engine = client
        from datetime import date
        from fazenda.models import Servico

        with Session(engine) as s:
            self._touro_e_estoque(s, naab="1HO201", nome="TOURO FAZENDA", tipo="fazenda", tpi=1000)
            # tipo_semen gravado no próprio serviço (monta natural).
            s.add(Servico(numero_matriz="1", reprodutor="TOURO FAZENDA", tipo_semen="fazenda", data_servico=date(2026, 1, 1)))
            s.commit()

        resp_padrao = c.get("/cadastro/estoque-semen/prova-ao-vivo")
        assert resp_padrao.json()["touros_considerados"] == 0
        assert resp_padrao.json()["prova"]["tpi"] is None

        resp_incluindo = c.get("/cadastro/estoque-semen/prova-ao-vivo", params={"incluir_fazenda": "true"})
        corpo = resp_incluindo.json()
        assert corpo["touros_considerados"] == 1
        assert corpo["prova"]["tpi"] == 1000.0

    def test_classifica_touro_da_fazenda_pelo_estoque_quando_servico_antigo_nao_tem_tipo_semen(self, client):
        # Serviço antigo sem `tipo_semen` gravado — classifica pelo tipo
        # cadastrado no Estoque de Sêmen com esse nome.
        c, engine = client
        from datetime import date
        from fazenda.models import Servico

        with Session(engine) as s:
            self._touro_e_estoque(s, naab="1HO202", nome="TOURO FAZENDA ANTIGO", tipo="fazenda", tpi=1500)
            s.add(Servico(numero_matriz="1", reprodutor="TOURO FAZENDA ANTIGO", data_servico=date(2026, 1, 1)))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-ao-vivo")
        assert resp.json()["touros_considerados"] == 0

    def test_filtro_categoria(self, client):
        c, engine = client
        from datetime import date
        from fazenda.models import Servico

        d = date(2026, 1, 1)
        with Session(engine) as s:
            self._touro_e_estoque(s, naab="1HO301", nome="TOURO A", tpi=2400)
            s.add(Servico(numero_matriz="1", categoria="Vaca", reprodutor="TOURO A", data_servico=d))
            s.add(Servico(numero_matriz="2", categoria="Novilha", reprodutor="TOURO A", data_servico=d))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-ao-vivo", params={"categoria": "vaca"})
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["total_servicos"] == 1
        touros = {t["touro"]: t["servicos"] for t in corpo["touros"]}
        assert touros == {"TOURO A": 1}

    def test_filtro_ano_nascimento_e_periodo(self, client):
        c, engine = client
        from datetime import date
        from fazenda.models import Servico

        with Session(engine) as s:
            self._touro_e_estoque(s, naab="1HO302", nome="TOURO A", tpi=2400)
            s.add(Servico(numero_matriz="1", reprodutor="TOURO A", data_nasc_matriz=date(2022, 3, 1),
                          data_servico=date(2026, 1, 10)))
            s.add(Servico(numero_matriz="2", reprodutor="TOURO A", data_nasc_matriz=date(2023, 3, 1),
                          data_servico=date(2026, 1, 10)))
            s.add(Servico(numero_matriz="1", reprodutor="TOURO A", data_nasc_matriz=date(2022, 3, 1),
                          data_servico=date(2026, 6, 1)))
            s.commit()

        resp = c.get("/cadastro/estoque-semen/prova-ao-vivo", params={"ano_nascimento": 2022})
        assert resp.status_code == 200
        assert resp.json()["total_servicos"] == 2

        resp2 = c.get("/cadastro/estoque-semen/prova-ao-vivo", params={"ano_nascimento": 2022, "de": "2026-01-01", "ate": "2026-03-01"})
        assert resp2.status_code == 200
        assert resp2.json()["total_servicos"] == 1
