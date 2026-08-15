"""
Duas mudanças que sustentam a Central de Protocolos no app de campo:

1. `nome_curto()` — a Agenda passa a mostrar só o nome cadastrado, sem o
   intervalo de datas. O nome COMPLETO continua gravado e é o que aparece na
   Central, na ficha do animal e nos relatórios; e nome antigo (anterior à
   nomenclatura automática) não pode ser tocado.
2. Ficha do animal ganha as seções de Indução de Lactação e de Protocolo
   Customizado, que existiam no sistema mas nunca apareciam na ficha.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Animal, Pessoa
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento, nome_curto


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


class TestNomeCurto:
    def test_remove_o_intervalo_de_datas(self):
        completo = gerar_nome_lancamento("Protocolo de Mastite 1", date(2026, 8, 5), 0, 4)
        assert completo == "PROTOCOLO DE MASTITE 1 - 05/08/26 A 09/08/26 (D0 A D4 - 5 DIAS)"
        assert nome_curto(completo) == "PROTOCOLO DE MASTITE 1"

    def test_nome_antigo_fica_intacto(self):
        """Lançamento anterior à nomenclatura automática não tem o sufixo — a
        função não pode 'limpar' nada nele."""
        for antigo in ("IATF 12/06 a 23/06", "Protocolo padrão", "Mastite - Protocolo 1"):
            assert nome_curto(antigo) == antigo

    def test_protocolo_de_um_dia_so(self):
        completo = gerar_nome_lancamento("Vacinação", date(2026, 8, 5), 0, 0)
        assert nome_curto(completo) == "VACINAÇÃO"

    def test_nao_corta_parenteses_que_facam_parte_do_nome(self):
        completo = gerar_nome_lancamento("Pós-Parto (Vaca Grande)", date(2026, 8, 5), 0, 3)
        assert nome_curto(completo) == "PÓS-PARTO (VACA GRANDE)"

    def test_vazio_nao_quebra(self):
        assert nome_curto("") == ""


class TestAgendaUsaNomeCurto:
    def test_cartao_da_agenda_nao_repete_o_intervalo(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-08-05"})
        assert r.status_code == 200, r.text

        eventos = c.get("/agenda/", params={"data": "2026-08-05", "dias": 30}).json()["eventos"]
        d7 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 7)
        assert d7["descricao"] == "PROTOCOLO IATF — D7"
        assert "A 16/08/26" not in d7["descricao"], "intervalo de datas ainda está no cartão da Agenda"

    def test_o_nome_completo_continua_gravado(self, client):
        """Encurtar é só de exibição na Agenda — a Central e o registro seguem
        com o nome inteiro."""
        c, engine = client
        criado = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-08-05"}).json()
        lancs = c.get("/reproducao/protocolo-iatf/lancamentos").json()
        nome = next(l["nome_protocolo"] for l in lancs if l["lancamento_id"] == criado["lancamento_id"])
        assert nome == "PROTOCOLO IATF - 05/08/26 A 16/08/26 (D0 A D11 - 12 DIAS)"

        linha = next(
            l for l in c.get("/central-protocolos/acompanhamento").json()
            if l["origem"] == "iatf" and l["origem_id"] == criado["lancamento_id"]
        )
        assert linha["nome"] == nome


class TestFichaDoAnimalNovasSecoes:
    def _animal(self, engine, numero="700"):
        with Session(engine) as s:
            s.add(Animal(numero=numero, ativo=True))
            s.commit()

    def test_inducao_de_lactacao_aparece_na_ficha(self, client):
        c, engine = client
        self._animal(engine)
        pid = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução padrão", "dia_inicial": 0,
            "etapas": [
                {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
                {"dia": 7, "tipo": "manejo", "produto": "Adaptação na ordenha"},
            ],
        }).json()["id"]
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid, "animais": ["700"], "data_d0": "2026-08-05",
        })
        assert r.status_code == 201, r.text

        ficha = c.get("/animais/700/ficha").json()
        assert "inducao_lactacao" in ficha, "seção nova não foi exposta pela ficha"
        linhas = ficha["inducao_lactacao"]
        assert len(linhas) == 2, f"esperava 2 etapas, veio {len(linhas)}"
        assert linhas[0]["nome_protocolo"].startswith("INDUÇÃO PADRÃO - 05/08/26")
        assert linhas[0]["realizada"] == "Não"
        assert linhas[0]["data_prevista"] == "2026-08-05"

    def test_protocolo_customizado_aparece_na_ficha(self, client):
        c, engine = client
        self._animal(engine)
        criado = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Cura de casco", "categoria": "Rebanho", "dia_inicial": 0,
            "etapas": [
                {"dia": 0, "descricao_evento": "Aplicar produto", "insumo_padrao": "Sulfato de cobre"},
                {"dia": 3, "descricao_evento": "Reavaliar casco"},
            ],
        }).json()
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["700"], "data_inicio": "2026-08-05",
        })
        assert r.status_code == 201, r.text

        ficha = c.get("/animais/700/ficha").json()
        assert "protocolos_customizados" in ficha, "seção nova não foi exposta pela ficha"
        linhas = ficha["protocolos_customizados"]
        assert len(linhas) == 2
        assert linhas[0]["dia"] == 0 and linhas[1]["dia"] == 3
        assert linhas[0]["insumo"] == "Sulfato de cobre"
        assert linhas[0]["nome_protocolo"].startswith("CURA DE CASCO - 05/08/26")

    def test_animal_sem_protocolo_traz_secoes_vazias(self, client):
        """A ficha não pode quebrar nem omitir a chave para quem nunca entrou
        nesses protocolos — o front espera a lista, mesmo vazia."""
        c, engine = client
        self._animal(engine, "701")
        ficha = c.get("/animais/701/ficha").json()
        assert ficha["inducao_lactacao"] == []
        assert ficha["protocolos_customizados"] == []

    def test_secoes_antigas_da_ficha_continuam(self, client):
        """Nada do que já existia na ficha pode ter sumido com a inclusão."""
        c, engine = client
        self._animal(engine)
        ficha = c.get("/animais/700/ficha").json()
        for chave in ("protocolos_iatf", "protocolos_sanitarios", "aplicacoes_sanitarias", "partos", "servicos"):
            assert chave in ficha, f"seção '{chave}' sumiu da ficha do animal"

    def test_tarefa_da_fazenda_nao_polui_a_ficha_de_animal(self, client):
        """Protocolo customizado lançado sem animal (tarefa da fazenda) não
        pode aparecer na ficha de ninguém."""
        c, engine = client
        self._animal(engine)
        criado = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Manutenção do curral", "categoria": "Atividades", "dia_inicial": 0,
            "etapas": [{"dia": 0, "descricao_evento": "Revisar contenção"}],
        }).json()
        c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": [], "data_inicio": "2026-08-05",
        })
        ficha = c.get("/animais/700/ficha").json()
        assert ficha["protocolos_customizados"] == []
