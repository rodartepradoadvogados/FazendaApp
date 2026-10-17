"""
Telas gerenciais de Lançamentos › Produção (Qualidade do leite, Indução de lactação, Venda mensal do leite, BST).

O front manda campos novos/antigos e o Pydantic descarta em silêncio o que não conhece — por isso cada tela tem um teste de
IDA-E-VOLTA (front envia → back grava → back devolve), mais as regras que o servidor passou a impor à Venda mensal.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Estoque, Sanidade


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


class TestQualidadeLeiteIdaEVolta:
    def test_os_oito_indices_a_observacao_e_a_vaca_voltam_na_listagem(self, client):
        c, _ = client
        corpo = {
            "numero_matriz": "11153", "data_coleta": "2026-10-17",
            "ccs": 312.0, "cbt": 78.0, "gordura_pct": 3.82, "proteina_pct": 3.28,
            "solidos_totais_pct": 12.41, "esd_pct": 8.62, "lactose_pct": 4.58, "nul": 11.8,
            "observacao": "laudo do laticínio",
        }
        assert c.post("/producao/qualidade-leite", json=corpo).status_code == 201
        # Tanque: sem vaca e só alguns índices — o que a tela não preenche tem de voltar nulo, nunca 0.
        assert c.post("/producao/qualidade-leite", json={"data_coleta": "2026-10-10", "ccs": 182.0, "cbt": None}).status_code == 201
        regs = c.get("/producao/qualidade-leite").json()["registros"]
        vaca = next(r for r in regs if r["numero_matriz"] == "11153")
        for campo, valor in corpo.items():
            if campo != "data_coleta":
                assert vaca[campo] == valor, campo
        tanque = next(r for r in regs if r["numero_matriz"] is None)
        assert tanque["ccs"] == 182.0
        assert tanque["cbt"] is None and tanque["gordura_pct"] is None and tanque["nul"] is None


class TestVendaMensalIdaEVolta:
    def test_litro_observacao_e_autor_voltam_e_o_put_corrige(self, client):
        c, _ = client
        r = c.post("/producao/entrega-leite", json={"competencia": "2026-09", "quantidade_litros": 12130.5, "unidade": "L", "observacao": "app do laticínio"})
        assert r.status_code == 201, r.text
        reg = c.get("/producao/entrega-leite").json()["registros"][0]
        assert (reg["competencia"], reg["quantidade_litros"], reg["unidade"], reg["observacao"]) == ("2026-09", 12130.5, "L", "app do laticínio")
        assert "usuario_nome" in reg  # a tela mostra a coluna "Lançado por"

        r = c.put(f"/producao/entrega-leite/{reg['id']}", json={"competencia": "2026-08", "quantidade_litros": 13054, "unidade": "kg", "observacao": None})
        assert r.status_code == 200, r.text
        reg = c.get("/producao/entrega-leite").json()["registros"][0]
        assert (reg["competencia"], reg["quantidade_litros"], reg["unidade"], reg["observacao"]) == ("2026-08", 13054, "kg", None)

    def test_salvar_o_mesmo_mes_substitui_o_valor_e_nao_duplica(self, client):
        # É o motivo do botão "Substituir entrega de MM/AAAA" na tela.
        c, _ = client
        c.post("/producao/entrega-leite", json={"competencia": "2026-06", "quantidade_litros": 12000})
        c.post("/producao/entrega-leite", json={"competencia": "2026-06", "quantidade_litros": 12500, "unidade": "L"})
        regs = c.get("/producao/entrega-leite").json()["registros"]
        assert len(regs) == 1
        assert (regs[0]["quantidade_litros"], regs[0]["unidade"]) == (12500, "L")

    @pytest.mark.parametrize("corpo", [
        {"competencia": "2026-13", "quantidade_litros": 100},
        {"competencia": "09/2026", "quantidade_litros": 100},
        {"competencia": "", "quantidade_litros": 100},
        {"competencia": "2026-09", "quantidade_litros": 0},
        {"competencia": "2026-09", "quantidade_litros": -5},
    ])
    def test_servidor_recusa_mes_invalido_e_quantidade_nao_positiva(self, client, corpo):
        c, _ = client
        r = c.post("/producao/entrega-leite", json=corpo)
        assert r.status_code == 400, r.text
        assert c.get("/producao/entrega-leite").json()["total"] == 0


class TestInducaoLactacaoEmAndamento:
    def test_ativos_devolve_o_protocolo_para_a_tela_casar_com_o_molde(self, client):
        c, _ = client
        proto = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução D0", "dia_inicial": 0,
            "etapas": [
                {"dia": 0, "tipo": "manejo", "produto": "Adaptação na ordenha"},
                {"dia": 2, "tipo": "manejo", "produto": "COMEÇAR A ORDENHA"},
            ],
        }).json()
        hoje = date.today()
        r = c.post("/producao/inducao-lactacao", json={"protocolo_id": proto["id"], "animais": ["4802", "4811"], "data_d0": hoje.isoformat()})
        assert r.status_code == 201, r.text
        assert r.json()["eventos_criados"] == 4  # 2 dias distintos x 2 animais: é a conta que a tela mostra antes de salvar

        ativos = c.get("/producao/inducao-lactacao/ativos").json()
        assert len(ativos) == 1
        a = ativos[0]
        assert a["protocolo_id"] == proto["id"]
        assert a["data_d0"] == hoje.isoformat()
        assert [x["numero_matriz"] for x in a["animais"]] == ["4802", "4811"]
        assert a["animais"][0]["etapa_atual"] == "D0"

        # O molde que a tela cruza traz dia_inicial, duração e as etapas (para achar o dia da ordenha).
        molde = next(p for p in c.get("/producao/protocolos-inducao-lactacao").json() if p["id"] == proto["id"])
        assert molde["dia_inicial"] == 0 and molde["duracao_dias"] == 2
        assert [e["produto"] for e in molde["etapas"]] == ["Adaptação na ordenha", "COMEÇAR A ORDENHA"]

    def test_lancar_duas_vezes_nao_duplica(self, client):
        c, _ = client
        proto = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução D0", "dia_inicial": 0, "etapas": [{"dia": 0, "tipo": "manejo", "produto": "Adaptação"}],
        }).json()
        corpo = {"protocolo_id": proto["id"], "animais": ["4802"], "data_d0": date.today().isoformat()}
        assert c.post("/producao/inducao-lactacao", json=corpo).json()["criado"] is True
        segundo = c.post("/producao/inducao-lactacao", json=corpo)
        assert segundo.json()["criado"] is False and segundo.json()["aviso"]


class TestBstRetornoQueATelaMostra:
    def _semear(self, engine):
        with Session(engine) as s:
            s.add(Animal(numero="301", grupo_primario="02 - Vacas Alta", del_dias=70, sexo="F", ativo=True))
            s.add(Animal(numero="302", grupo_primario="02 - Vacas Alta", del_dias=75, sexo="F", ativo=True))
            s.add(Estoque(nome="Lactotropin", categoria="medicamento", quantidade=50.0, unidade="unidade", estocavel=True))
            s.commit()

    def test_aplicar_hoje_devolve_contagem_proxima_data_e_baixa_o_estoque(self, client):
        c, engine = client
        self._semear(engine)
        hoje = date.today()
        r = c.post("/agenda/bst/aplicar", json={
            "numeros_matriz": ["301", "302"], "data_aplicacao": hoje.isoformat(), "aplicado": True,
            "produto": "Lactotropin", "dose": 1.0, "unidade": "unidade", "dose_por_animal": True,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["aplicados"] == 2 and d["agendados"] == 0 and d["programado"] is False
        assert d["proxima_aplicacao_calculada"] == (hoje + timedelta(days=d["intervalo_dias"])).isoformat()
        assert isinstance(d["avisos"], list)
        with Session(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "Lactotropin")).first().quantidade == 48.0
            assert len(s.exec(select(Sanidade)).all()) == 2

    def test_data_futura_agenda_e_nao_baixa_estoque(self, client):
        c, engine = client
        self._semear(engine)
        futura = (date.today() + timedelta(days=3)).isoformat()
        r = c.post("/agenda/bst/aplicar", json={
            "numeros_matriz": ["301"], "data_aplicacao": futura, "aplicado": True, "produto": "Lactotropin", "dose": 1.0, "unidade": "unidade",
        })
        d = r.json()
        assert d["aplicados"] == 0 and d["agendados"] == 1 and d["programado"] is True
        with Session(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "Lactotropin")).first().quantidade == 50.0

    def test_marcar_inapta_e_reverter_respondem_com_a_contagem(self, client):
        c, engine = client
        self._semear(engine)
        r = c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["301", "302", "999"], "inapta": True})
        assert r.json() == {"atualizados": 2, "inapta": True}
        r = c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["301"], "inapta": False})
        assert r.json() == {"atualizados": 1, "inapta": False}
        with Session(engine) as s:
            a = s.exec(select(Animal).where(Animal.numero == "301")).first()
            assert a.excluir_bst is False and a.aguardando_nova_aplicacao_bst is True  # reverter NÃO torna apta na hora
