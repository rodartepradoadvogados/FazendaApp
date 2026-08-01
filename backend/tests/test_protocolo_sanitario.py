"""
Testes do Protocolo sanitário: cadastro (com etapas D1/D2/D3...), lançamento
em um animal, geração de eventos na Agenda e baixa automática de estoque
quando o evento é marcado "realizado".
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, MovimentoEstoque, Sanidade


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


def _etapa(dia, produto="Mastite Injetável", dosagem=10.0, unidade="ml", via="Intramamária"):
    return {"dia": dia, "produto": produto, "dosagem": dosagem, "unidade": unidade, "via": via}


class TestCadastroProtocolo:
    def test_cria_protocolo_com_etapas(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite clínica padrão", "eh_mastite": True,
            "etapas": [_etapa(1), _etapa(2), _etapa(3)],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["eh_mastite"] is True
        assert [e["dia"] for e in corpo["etapas"]] == [1, 2, 3]

    def test_aceita_etapa_com_dia_zero(self, client):
        # Padronização em D0 (jul/2026): protocolos sanitários agora aceitam D0,
        # assim como o protocolo hormonal IATF e a indução de lactação.
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Protocolo D0", "etapas": [_etapa(0), _etapa(1)],
        })
        assert r.status_code == 200, r.json()
        corpo = r.json()
        assert [e["dia"] for e in corpo["etapas"]] == [0, 1]
        # Novo protocolo (sem dia_inicial explícito) nasce com dia_inicial=0.
        assert corpo["dia_inicial"] == 0

    def test_rejeita_etapa_com_dia_negativo(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Protocolo inválido", "etapas": [_etapa(-1), _etapa(1)],
        })
        assert r.status_code == 400

    def test_rejeita_protocolo_sem_etapas(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={"nome": "Vazio", "etapas": []})
        assert r.status_code == 400

    def test_rejeita_via_fora_da_lista_fixa(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Via inválida", "etapas": [_etapa(1, via="Retal")],
        })
        assert r.status_code == 400
        assert "Via inválida" in r.json()["detail"]

    def test_aceita_cada_via_da_lista_fixa(self, client):
        c, engine = client
        # Mesma lista usada em todo o site (frontend/lib/constants.ts) — as duas
        # devem ficar sempre em sincronia.
        for i, via in enumerate(["Intramuscular", "Subcutânea", "Intravenosa", "Intramamária", "Oral", "Tópica", "Subdérmica", "Intrauterina"]):
            r = c.post("/cadastro/protocolos-sanitarios", json={
                "nome": f"Via {via}", "etapas": [_etapa(1, via=via)],
            })
            assert r.status_code == 200, r.json()

    def test_rejeita_nome_duplicado(self, client):
        c, engine = client
        c.post("/cadastro/protocolos-sanitarios", json={"nome": "Duplicado", "etapas": [_etapa(1)]})
        r = c.post("/cadastro/protocolos-sanitarios", json={"nome": "Duplicado", "etapas": [_etapa(1)]})
        assert r.status_code == 409

    def test_atualiza_protocolo_substitui_etapas(self, client):
        c, engine = client
        pid = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Editável", "etapas": [_etapa(1), _etapa(2)],
        }).json()["id"]
        r = c.put(f"/cadastro/protocolos-sanitarios/{pid}", json={
            "nome": "Editável", "etapas": [_etapa(1, produto="Novo produto")],
        })
        assert r.status_code == 200
        assert len(r.json()["etapas"]) == 1
        assert r.json()["etapas"][0]["produto"] == "Novo produto"


class TestExcluirProtocolo:
    def test_exclui_protocolo_nunca_usado(self, client):
        c, engine = client
        pid = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Nunca usado", "etapas": [_etapa(1)],
        }).json()["id"]
        r = c.delete(f"/cadastro/protocolos-sanitarios/{pid}")
        assert r.status_code == 200
        assert r.json() == {"excluido": True}
        nomes = [p["nome"] for p in c.get("/cadastro/protocolos-sanitarios").json()]
        assert "Nunca usado" not in nomes

    def test_nao_exclui_protocolo_ja_lancado(self, client):
        c, engine = client
        pid = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Já lançado", "etapas": [_etapa(1, produto="Ivermectina")],
        }).json()["id"]
        r_lanc = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
        })
        assert r_lanc.status_code == 201

        r = c.delete(f"/cadastro/protocolos-sanitarios/{pid}")
        assert r.status_code == 409
        assert "desative" in r.json()["detail"].lower()
        # Continua existindo — a exclusão não pode ter apagado nada por engano.
        nomes = [p["nome"] for p in c.get("/cadastro/protocolos-sanitarios").json()]
        assert "Já lançado" in nomes

    def test_exclui_protocolo_inexistente_da_404(self, client):
        c, engine = client
        r = c.delete("/cadastro/protocolos-sanitarios/999999")
        assert r.status_code == 404


class TestImportarProtocolo:
    def test_importa_csv_agrupando_por_nome(self, client):
        c, engine = client
        csv = (
            "Nome do protocolo,Dia da aplicação,Definido por,Medicamento,Dosagem,Unidade,Via\n"
            "Mastite - Protocolo 1,1,Medicamento,Borgal,40,ml,Intramuscular\n"
            "Mastite - Protocolo 1,1,Medicamento,Spectramast,2,unidade,Intramamária\n"
            "Mastite - Protocolo 1,2,Medicamento,Spectramast,2,unidade,Intramamária\n"
            "Retenção de Placenta,5,Medicamento,Excede (10ml por orelha),20,ml,Subcutânea\n"
            "Retenção de Placenta,30,Medicamento,Lutalyse (Se necessário),5,ml,Intramuscular\n"
        ).encode("utf-8")
        r = c.post("/cadastro/protocolos-sanitarios/importar", files={"file": ("protocolos.csv", csv, "text/csv")})
        assert r.status_code == 200, r.json()
        corpo = r.json()
        assert set(corpo["criados"]) == {"Mastite - Protocolo 1", "Retenção de Placenta"}
        assert not corpo["atualizados"]
        assert not corpo["erros"]

        protocolos = {p["nome"]: p for p in c.get("/cadastro/protocolos-sanitarios").json()}
        mastite = protocolos["Mastite - Protocolo 1"]
        assert mastite["eh_mastite"] is True
        assert [e["dia"] for e in mastite["etapas"]] == [1, 1, 2]

        reten = protocolos["Retenção de Placenta"]
        assert reten["eh_mastite"] is False
        por_dia = {e["dia"]: e for e in reten["etapas"]}
        assert por_dia[5]["produto"] == "Excede"
        assert por_dia[5]["observacao"] == "10ml por orelha"
        assert por_dia[30]["produto"] == "Lutalyse"
        assert por_dia[30]["observacao"] == "Se necessário"

    def test_reimportar_atualiza_em_vez_de_duplicar(self, client):
        c, engine = client
        csv_v1 = (
            "Nome do protocolo,Dia da aplicação,Definido por,Medicamento,Dosagem,Unidade,Via\n"
            "Diarreia - Protocolo 1,1,Medicamento,Biobac,4,g,Oral\n"
        ).encode("utf-8")
        r1 = c.post("/cadastro/protocolos-sanitarios/importar", files={"file": ("v1.csv", csv_v1, "text/csv")})
        assert r1.json()["criados"] == ["Diarreia - Protocolo 1"]

        csv_v2 = (
            "Nome do protocolo,Dia da aplicação,Definido por,Medicamento,Dosagem,Unidade,Via\n"
            "Diarreia - Protocolo 1,1,Medicamento,Biobac,4,g,Oral\n"
            "Diarreia - Protocolo 1,2,Medicamento,Biobac,4,g,Oral\n"
        ).encode("utf-8")
        r2 = c.post("/cadastro/protocolos-sanitarios/importar", files={"file": ("v2.csv", csv_v2, "text/csv")})
        assert r2.json()["atualizados"] == ["Diarreia - Protocolo 1"]
        assert not r2.json()["criados"]

        protocolos = c.get("/cadastro/protocolos-sanitarios").json()
        assert sum(1 for p in protocolos if p["nome"] == "Diarreia - Protocolo 1") == 1
        etapas = next(p for p in protocolos if p["nome"] == "Diarreia - Protocolo 1")["etapas"]
        assert len(etapas) == 2

    def test_importa_xlsx_multiplas_abas(self, client):
        c, engine = client
        import io
        import openpyxl

        wb = openpyxl.Workbook()
        cabecalho = ["Nome do protocolo", "Dia da aplicação", "Definido por", "Medicamento", "Dosagem", "Unidade", "Via"]
        ws1 = wb.active
        ws1.title = "Protocolo A"
        ws1.append(cabecalho)
        ws1.append(["Pneumonia - Protocolo A", 1, "Medicamento", "Resflor", 2, "ml / 15kg PV", "Subcutânea"])
        ws2 = wb.create_sheet("Protocolo B")
        ws2.append(cabecalho)
        ws2.append(["Pneumonia - Protocolo B", 1, "Medicamento", "Advocin", 1, "ml / 30kg PV", "Intramuscular"])
        buf = io.BytesIO()
        wb.save(buf)

        r = c.post(
            "/cadastro/protocolos-sanitarios/importar",
            files={"file": ("protocolos.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert r.status_code == 200, r.json()
        assert set(r.json()["criados"]) == {"Pneumonia - Protocolo A", "Pneumonia - Protocolo B"}

    def test_importar_planilha_sem_colunas_reconheciveis(self, client):
        c, engine = client
        csv = "Coluna qualquer,Outra coluna\nx,y\n".encode("utf-8")
        r = c.post("/cadastro/protocolos-sanitarios/importar", files={"file": ("ruim.csv", csv, "text/csv")})
        assert r.status_code == 400


class TestLancamentoProtocolo:
    def _protocolo_mastite(self, c):
        # dia_inicial=1 explícito: simula um protocolo já existente antes da
        # padronização em D0 — usado por test_datas_das_etapas_seguem_d1_d2_d3_sem_d0
        # para provar que as datas continuam idênticas às de sempre.
        return c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite subclínica", "eh_mastite": True, "dia_inicial": 1,
            "etapas": [_etapa(1), _etapa(2), _etapa(3)],
        }).json()["id"]

    def _protocolo_simples(self, c):
        return c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Vermifugação", "etapas": [_etapa(1, produto="Ivermectina", unidade="ml")],
        }).json()["id"]

    def test_lanca_protocolo_gera_uma_aplicacao_por_etapa_com_datas_corretas(self, client):
        c, engine = client
        protocolo_id = self._protocolo_simples(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 201

    def test_datas_das_etapas_seguem_d1_d2_d3_sem_d0(self, client):
        # Protocolo pré-existente à padronização em D0 (dia_inicial=1, etapas
        # armazenadas como D1/D2/D3) continua gerando as MESMAS datas de sempre —
        # a fórmula dia - dia_inicial com dia_inicial=1 é idêntica ao antigo `dia - 1`.
        c, engine = client
        protocolo_id = self._protocolo_mastite(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica", "tetos_afetados": ["AE", "PD"],
        })
        assert r.status_code == 201
        aplicacoes = sorted(r.json()["lancamentos"][0]["aplicacoes"], key=lambda a: a["data_prevista"])
        datas = [a["data_prevista"] for a in aplicacoes]
        assert datas == ["2026-03-01", "2026-03-02", "2026-03-03"]  # D1=início, D2=+1, D3=+2

    def test_datas_das_etapas_com_dia_inicial_0_batem_com_dia_inicial_1(self, client):
        # Um protocolo NOVO (dia_inicial=0, etapas D0/D1/D2) deve gerar
        # exatamente as mesmas datas que o protocolo D1-based acima, provando
        # que o rótulo exibido (D0, D1, D2...) é só uma questão de exibição —
        # o offset de datas (dia - dia_inicial) é o mesmo nos dois casos.
        c, engine = client
        r_proto = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite subclínica D0", "eh_mastite": True, "dia_inicial": 0,
            "etapas": [_etapa(0), _etapa(1), _etapa(2)],
        })
        assert r_proto.status_code == 200, r_proto.json()
        assert r_proto.json()["dia_inicial"] == 0
        protocolo_id = r_proto.json()["id"]

        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica", "tetos_afetados": ["AE", "PD"],
        })
        assert r.status_code == 201
        aplicacoes = sorted(r.json()["lancamentos"][0]["aplicacoes"], key=lambda a: a["data_prevista"])
        datas = [a["data_prevista"] for a in aplicacoes]
        assert datas == ["2026-03-01", "2026-03-02", "2026-03-03"]  # D0=início, D1=+1, D2=+2

    def test_exige_classificacao_de_mastite_quando_protocolo_e_mastite(self, client):
        c, engine = client
        protocolo_id = self._protocolo_mastite(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 400

    def test_rejeita_teto_invalido(self, client):
        c, engine = client
        protocolo_id = self._protocolo_mastite(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica", "tetos_afetados": ["XX"],
        })
        assert r.status_code == 400

    def test_rejeita_protocolo_sem_etapas_cadastradas(self, client):
        c, engine = client
        # protocolo criado direto no banco sem passar pela validação de cadastro (não deve ocorrer via API, mas defende o endpoint de lançamento)
        pid = c.post("/cadastro/protocolos-sanitarios", json={"nome": "X", "etapas": [_etapa(1)]}).json()["id"]
        with Session(engine) as s:
            from fazenda.models import ProtocoloSanitarioEtapa
            etapa = s.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == pid)).first()
            s.delete(etapa)
            s.commit()
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 400

    def test_rejeita_mastite_com_mais_de_um_animal(self, client):
        c, engine = client
        protocolo_id = self._protocolo_mastite(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700", "701"], "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica",
        })
        assert r.status_code == 400

    def test_lanca_protocolo_simples_para_varios_animais(self, client):
        c, engine = client
        protocolo_id = self._protocolo_simples(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700", "701", "702"], "data_inicio": "2026-03-01",
        })
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["criados"] == 3
        assert {l["numero_matriz"] for l in corpo["lancamentos"]} == {"700", "701", "702"}


class TestAgendaEBaixaAutomatica:
    def _lancar(self, c, produto="Mastite Injetável", unidade="ml", dosagem=10.0):
        protocolo_id = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite ambiental", "eh_mastite": True,
            "etapas": [_etapa(1, produto=produto, unidade=unidade, dosagem=dosagem), _etapa(2, produto=produto, unidade=unidade, dosagem=dosagem)],
        }).json()["id"]
        lanc = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700"], "data_inicio": "2026-01-01",
            "classificacao_mastite": "ambiental", "tetos_afetados": ["AD"],
        }).json()
        return lanc

    def test_aplicacao_pendente_aparece_na_agenda(self, client):
        c, engine = client
        self._lancar(c)
        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        assert any(e["id"].startswith("protocolo_sanitario_") and e["numero_animal"] == "700" for e in eventos)

    def test_marcar_realizado_da_baixa_e_registra_sanidade(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Mastite Injetável", quantidade=100.0, unidade="ml"))
            s.commit()

        self._lancar(c, produto="Mastite Injetável", unidade="ml", dosagem=10.0)
        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("protocolo_sanitario_"))

        r = c.post("/agenda/realizados", json={"evento_id": alvo["id"]})
        assert r.status_code == 200

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Mastite Injetável")).first()
            assert item.quantidade == 90.0
            movimento = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.nome_item == "Mastite Injetável")).first()
            assert movimento is not None
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "700")).first()
            assert sanidade is not None
            assert sanidade.produto == "Mastite Injetável"

        eventos2 = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        assert alvo["id"] not in [e["id"] for e in eventos2]

    def test_nao_da_baixa_quando_unidade_incompativel(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Produto Litro", quantidade=50.0, unidade="L"))
            s.commit()

        self._lancar(c, produto="Produto Litro", unidade="unidade", dosagem=2.0)
        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("protocolo_sanitario_"))
        c.post("/agenda/realizados", json={"evento_id": alvo["id"]})

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Produto Litro")).first()
            assert item.quantidade == 50.0  # sem baixa — unidade incompatível
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "700")).first()
            assert sanidade is not None  # aplicação ainda é registrada em Sanidade


class TestAgrupamentoLote:
    """Aplicações do mesmo protocolo/dia/data compartilham `grupo` para o app
    oferecer 'lote ou individual' — cada animal continua confirmável por si."""

    def _protocolo_simples(self, c):
        return c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Vermifugação", "etapas": [_etapa(1, produto="Ivermectina", unidade="ml")],
        }).json()["id"]

    def test_animais_do_lote_compartilham_grupo(self, client):
        c, engine = client
        pid = self._protocolo_simples(c)
        c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700", "701", "702"], "data_inicio": "2026-03-01",
        })
        eventos = c.get("/agenda/", params={"data": "2026-02-01", "dias": 60}).json()["eventos"]
        san = [e for e in eventos if e.get("tipo") == "protocolo_sanitario"]
        assert len(san) == 3
        grupos = {e["grupo"] for e in san}
        assert len(grupos) == 1  # mesmo protocolo/dia/data → um só grupo
        assert {e["numero_animal"] for e in san} == {"700", "701", "702"}
        # Cada um tem id próprio (confirmável individualmente).
        assert len({e["id"] for e in san}) == 3


class TestConfirmacaoCura:
    """#400 — "confirmar cura" só pode aparecer quando (1) a aplicação veio de
    um PROTOCOLO SANITÁRIO pré-cadastrado em Sanidade Curativa (nunca para
    lançamento avulso nem preventivo) e (2) TODOS os medicamentos do ÚLTIMO
    DIA do protocolo já foram lançados — não basta a data ter passado."""

    def _protocolo_2_dias(self, c):
        # dia_inicial=1 explícito: simula um protocolo já existente antes da
        # padronização em D0 — as datas abaixo (2026-03-01, 2026-03-03) só
        # batem com a fórmula antiga (dia - 1) quando dia_inicial=1.
        return c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite 2 dias", "eh_mastite": True, "dia_inicial": 1,
            "etapas": [_etapa(1), _etapa(2)],
        }).json()["id"]

    def test_nao_pergunta_cura_com_ultimo_dia_incompleto(self, client):
        c, engine = client
        pid = self._protocolo_2_dias(c)
        c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica", "tetos_afetados": ["AE"],
        })
        eventos = c.get("/agenda/", params={"data": "2026-03-01", "dias": 60}).json()["eventos"]
        dia1 = next(e for e in eventos if e.get("tipo") == "protocolo_sanitario" and e["data"] == "2026-03-01")
        r = c.post("/agenda/realizados", json={"evento_id": dia1["id"]})
        assert r.status_code == 200

        # Só o D1 foi lançado — o D2 (último dia) ainda está pendente → sem "confirmar cura".
        eventos2 = c.get("/agenda/", params={"data": "2026-03-03", "dias": 60}).json()["eventos"]
        assert not any(e.get("tipo") == "confirmar_cura" for e in eventos2)

    def test_pergunta_cura_no_dia_seguinte_ao_ultimo_dia_totalmente_lancado(self, client):
        c, engine = client
        pid = self._protocolo_2_dias(c)
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-03-01",
            "classificacao_mastite": "clinica", "tetos_afetados": ["AE"],
        })
        lancamento_id = r.json()["lancamentos"][0]["id"]

        eventos = c.get("/agenda/", params={"data": "2026-03-01", "dias": 60}).json()["eventos"]
        for e in [x for x in eventos if x.get("tipo") == "protocolo_sanitario"]:
            assert c.post("/agenda/realizados", json={"evento_id": e["id"]}).status_code == 200

        # D1 e D2 (último dia) completos → confirma cura no dia seguinte ao D2 (2026-03-03).
        eventos2 = c.get("/agenda/", params={"data": "2026-03-03", "dias": 60}).json()["eventos"]
        cura = next(e for e in eventos2 if e.get("tipo") == "confirmar_cura")
        assert cura["cura_origem"] == "protocolo"
        assert cura["cura_id"] == lancamento_id
        assert cura["numero_animal"] == "700"

    def test_aplicacao_avulsa_nunca_pergunta_cura(self, client):
        c, engine = client
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-03-01", "animais": ["700"],
            "itens": [{"produto": "Antibiótico avulso", "quantidade": 10.0, "unidade": "ml"}],
            "natureza": "curativo",
        })
        assert r.status_code == 200, r.text
        eventos = c.get("/agenda/", params={"data": "2026-03-05", "dias": 60}).json()["eventos"]
        assert not any(e.get("tipo") == "confirmar_cura" for e in eventos)

    def test_aplicacao_preventiva_nunca_pergunta_cura(self, client):
        c, engine = client
        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-03-01", "animais": ["700"],
            "itens": [{"produto": "Vacina X", "quantidade": 2.0, "unidade": "ml"}],
            "natureza": "preventivo",
        })
        assert r.status_code == 200, r.text
        eventos = c.get("/agenda/", params={"data": "2026-03-05", "dias": 60}).json()["eventos"]
        assert not any(e.get("tipo") == "confirmar_cura" for e in eventos)


class TestCadastroPorCriterio:
    """Cadastro por princípio ativo/classificação → escolher o medicamento no
    lançamento → baixa usa o medicamento escolhido."""

    def test_medicamentos_filtra_por_classificacao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Terramicina", quantidade=100, unidade="ml", classificacao_medicamento="Antibiótico"))
            s.add(Estoque(nome="Banamine", quantidade=100, unidade="ml", classificacao_medicamento="Anti-inflamatório"))
            s.commit()
        r = c.get("/estoque/medicamentos", params={"classificacao": "Antibiótico"})
        assert r.status_code == 200
        nomes = [m["nome"] for m in r.json()]
        assert nomes == ["Terramicina"]

    def test_lancar_por_classificacao_exige_escolha_e_baixa_o_escolhido(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Terramicina", quantidade=100, unidade="ml", classificacao_medicamento="Antibiótico"))
            s.commit()
        # Protocolo cuja etapa é definida por classificação (não um medicamento fixo).
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Antibioticoterapia", "etapas": [
                {"dia": 1, "criterio_tipo": "classificacao", "produto": "Antibiótico", "dosagem": 5.0, "unidade": "ml", "via": "Intramuscular"},
            ],
        })
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        etapa_id = r.json()["etapas"][0]["id"]

        # Sem escolher o medicamento → 400.
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2025-12-01",
        })
        assert r.status_code == 400

        # Escolhendo o medicamento da classificação → ok.
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2025-12-01",
            "escolhas_medicamento": {str(etapa_id): "Terramicina"},
        })
        assert r.status_code == 201, r.text

        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("protocolo_sanitario_"))
        assert "Terramicina" in alvo["descricao"]
        c.post("/agenda/realizados", json={"evento_id": alvo["id"]})

    def test_medicamentos_sem_criterio_exclui_itens_nao_medicamento(self, client):
        """Sem nenhum critério (principio_ativo/classificacao/doenca/finalidade),
        vira o catálogo geral — ração/material não devem aparecer, só itens
        marcados como finalidade "Medicamento" (ou com sinal de que são)."""
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Terramicina", quantidade=10, unidade="ml", classificacao_medicamento="Antibiótico"))
            s.add(Estoque(nome="Ração Milho", quantidade=500, unidade="kg", finalidade="Ração/Alimento"))
            s.commit()
        r = c.get("/estoque/medicamentos")
        assert r.status_code == 200
        nomes = [m["nome"] for m in r.json()]
        assert "Terramicina" in nomes
        assert "Ração Milho" not in nomes

    def test_medicamentos_esconde_sem_estoque_por_padrao_e_inclui_com_flag(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Terramicina", quantidade=0, unidade="ml", classificacao_medicamento="Antibiótico"))
            s.commit()
        r = c.get("/estoque/medicamentos", params={"classificacao": "Antibiótico"})
        assert [m["nome"] for m in r.json()] == []
        r2 = c.get("/estoque/medicamentos", params={"classificacao": "Antibiótico", "incluir_sem_estoque": "true"})
        assert [m["nome"] for m in r2.json()] == ["Terramicina"]

    def test_lancar_com_medicamento_fixo_zerado_aceita_substituto(self, client):
        """Etapa com produto FIXO (criterio_tipo="medicamento") cujo item está
        zerado: o front pode mandar um substituto em escolhas_medicamento mesmo
        essa etapa não sendo "por critério" — a baixa usa o substituto."""
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Mastite Injetável", quantidade=0, unidade="ml", classificacao_medicamento="Antibiótico"))
            s.add(Estoque(nome="Mastite Injetável 2", quantidade=50, unidade="ml", classificacao_medicamento="Antibiótico"))
            s.commit()
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite substituível", "etapas": [_etapa(1, produto="Mastite Injetável", unidade="ml", dosagem=10.0)],
        })
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        etapa_id = r.json()["etapas"][0]["id"]

        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2025-12-01",
            "escolhas_medicamento": {str(etapa_id): "Mastite Injetável 2"},
        })
        assert r.status_code == 201, r.text

        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("protocolo_sanitario_"))
        assert "Mastite Injetável 2" in alvo["descricao"]

        r = c.post("/agenda/realizados", json={"evento_id": alvo["id"]})
        assert r.status_code == 200
        with Session(engine) as s:
            substituto = s.exec(select(Estoque).where(Estoque.nome == "Mastite Injetável 2")).first()
            assert substituto.quantidade == 40.0
            original = s.exec(select(Estoque).where(Estoque.nome == "Mastite Injetável")).first()
            assert original.quantidade == 0  # não mexeu no item zerado
