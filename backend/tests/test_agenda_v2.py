"""
Agenda v2 (fatia 10, item A): GET /agenda/dia, /agenda/painel, /agenda/projecao.

Contrato: leitura pura (nenhum INSERT/UPDATE/DELETE), isolamento por fazenda,
animal em lista de espera NUNCA vira tarefa nem aparece na projecao (R1), e a
projecao devolve so numeros por semana (nenhum brinco).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    AgendaManual, Animal, CalendarioSanitario, ContratoFazenda, ContratoFazendaModulo, CronogramaSanitario,
    CronogramaSanitarioAnimal, Estoque, EventoSanitario, Fazenda, Pedido, RepasseConfig, Servico,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.parametros import fazenda_atual

HOJE = date.today()


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""

    estado = {"fazenda": 1}
    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fazenda"]
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: estado["fazenda"]
    with TestClient(main.app) as c:
        c.estado = estado
        yield c, engine
    main.app.dependency_overrides.clear()
    fazenda_atual.set(None)


def _animal(s: Session, numero: str, fazenda_id: int = 1, **kw) -> None:
    s.add(Animal(numero=numero, sexo="F", ativo=True, fazenda_id=fazenda_id, grupo_primario="03 Lote 03", **kw))


def _servico(s: Session, numero: str, dias_atras: int, fazenda_id: int = 1, **kw) -> None:
    s.add(Servico(
        numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), ult_ocorrencia=1,
        tipo_servico=kw.pop("tipo_servico", "IA"), fazenda_id=fazenda_id, **kw,
    ))


def _manual(s: Session, descricao: str, dia: date, fazenda_id: int = 1) -> None:
    s.add(AgendaManual(data_evento=dia, descricao=descricao, categoria="Atividades", fazenda_id=fazenda_id))


def _atrasada(s: Session, numero_pedido: str, dias_atras: int, fazenda_id: int = 1) -> None:
    """Pedido com entrega prevista no passado: o motor nao poe piso de data nele, entao vira 'atrasada'."""
    s.add(Pedido(numero_pedido=numero_pedido, tipo="compra", data_pedido=HOJE - timedelta(days=30),
                 data_prevista=HOJE - timedelta(days=dias_atras), status="aberto", fazenda_id=fazenda_id))


def _lista_espera(s: Session, brincos: list[str]) -> None:
    ev = EventoSanitario(nome="Vacina Aftosa", tipo_agendamento="epoca", fazenda_id=1)
    s.add(ev)
    s.commit()
    s.refresh(ev)
    cal = CalendarioSanitario(
        evento_sanitario_id=ev.id, categoria_alvo="Novilha", produto="Aftosa", frequencia_valor=6,
        frequencia_unidade="meses", data_evento=HOJE + timedelta(days=5), usa_cronograma=True, fazenda_id=1,
    )
    s.add(cal)
    s.commit()
    s.refresh(cal)
    cron = CronogramaSanitario(calendario_sanitario_id=cal.id, data_evento=HOJE + timedelta(days=5), status="aberto", fazenda_id=1)
    s.add(cron)
    s.commit()
    s.refresh(cron)
    for b in brincos:
        s.add(CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=b, status="sugerido", data_sugestao=HOJE, fazenda_id=1))
    s.commit()


def _sem_escrita(engine):
    """Devolve a lista onde cada INSERT/UPDATE/DELETE executado fica registrado."""
    escritas: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE"):
            escritas.append(statement[:90])

    return escritas


# ───────────────────────────── /agenda/dia ──────────────────────────────────
class TestDia:
    def test_atrasadas_hoje_e_proximos_com_resumo(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _atrasada(s, "PED-1", 3)
            _manual(s, "Tarefa de hoje", HOJE)
            _manual(s, "Tarefa amanha", HOJE + timedelta(days=1))
            _manual(s, "Tarefa longe", HOJE + timedelta(days=30))
            s.commit()
        r = c.get("/agenda/dia", params={"data": HOJE.isoformat()})
        assert r.status_code == 200, r.text
        corpo = r.json()
        descricoes = {e["descricao"] for e in corpo["eventos"]}
        assert {"Tarefa de hoje", "Tarefa amanha"} <= descricoes
        assert any("PED-1" in d for d in descricoes)
        assert "Tarefa longe" not in descricoes          # fora da janela padrao (+10 dias)
        assert corpo["resumo"]["atrasadas"] == 1
        # o resumo bate com a propria lista (o motor pode somar outros eventos de hoje)
        hoje_iso = HOJE.isoformat()
        assert corpo["resumo"]["hoje_total"] == sum(1 for e in corpo["eventos"] if e["data"] == hoje_iso)
        assert corpo["resumo"]["hoje_total"] >= 1
        assert corpo["resumo"]["proximos_7d"] >= 1
        # sem os blocos pesados/de painel
        for chave in ("candidatas_iatf", "bst_elegiveis", "lista_espera_sanitaria", "estoque_negativo"):
            assert chave not in corpo

    def test_ate_amplia_a_janela_e_valida(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _manual(s, "Tarefa longe", HOJE + timedelta(days=30))
            s.commit()
        r = c.get("/agenda/dia", params={"data": HOJE.isoformat(), "ate": (HOJE + timedelta(days=40)).isoformat()})
        assert "Tarefa longe" in {e["descricao"] for e in r.json()["eventos"]}
        ruim = c.get("/agenda/dia", params={"data": HOJE.isoformat(), "ate": (HOJE - timedelta(days=1)).isoformat()})
        assert ruim.status_code == 422

    def test_lista_de_espera_nunca_vira_tarefa(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _lista_espera(s, ["7771", "7772"])
        r = c.get("/agenda/dia", params={"data": HOJE.isoformat(), "ate": (HOJE + timedelta(days=30)).isoformat()})
        assert r.status_code == 200
        bruto = json.dumps(r.json())
        assert "7771" not in bruto and "7772" not in bruto

    def test_isolamento_por_fazenda(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _manual(s, "So da fazenda 1", HOJE, fazenda_id=1)
            _manual(s, "So da fazenda 2", HOJE, fazenda_id=2)
            s.commit()
        d1 = {e["descricao"] for e in c.get("/agenda/dia", params={"data": HOJE.isoformat()}).json()["eventos"]}
        c.estado["fazenda"] = 2
        d2 = {e["descricao"] for e in c.get("/agenda/dia", params={"data": HOJE.isoformat()}).json()["eventos"]}
        assert "So da fazenda 1" in d1 and "So da fazenda 2" not in d1
        assert "So da fazenda 2" in d2 and "So da fazenda 1" not in d2

    def test_nao_escreve_no_banco(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _manual(s, "Tarefa", HOJE)
            _animal(s, "101")
            _servico(s, "101", 10)
            s.commit()
        escritas = _sem_escrita(engine)
        for _ in range(2):
            assert c.get("/agenda/dia", params={"data": HOJE.isoformat()}).status_code == 200
        assert escritas == [], escritas


# ───────────────────────────── /agenda/painel ───────────────────────────────
class TestPainel:
    def test_estrutura_e_atalho_da_lista_de_espera(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _lista_espera(s, ["8801", "8802", "8803"])
            _atrasada(s, "PED-2", 4)
            s.commit()
        r = c.get("/agenda/painel", params={"data": HOJE.isoformat()})
        assert r.status_code == 200, r.text
        p = r.json()
        for chave in ("candidatas_iatf", "bst_elegiveis", "bst_excluidos", "bst_nunca_aplicados", "estoque_negativo",
                      "estoque_abaixo_minimo", "comunicados", "pendencias", "lista_espera_total", "repasse"):
            assert chave in p, chave
        assert p["lista_espera_total"] == 3
        assert "eventos" not in p                      # tarefas sao do Dia a dia
        assert p["pendencias"]["n"] == 1 and p["pendencias"]["mais_antiga_dias"] == 4
        assert "8801" not in json.dumps(p)             # so a contagem, nunca o brinco (R1)

    def test_estoque_abaixo_do_minimo(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            s.add(Estoque(nome="Sincroforte", quantidade=1, estoque_minimo=3, unidade="frasco", fazenda_id=1))
            s.add(Estoque(nome="De outra fazenda", quantidade=1, estoque_minimo=3, unidade="frasco", fazenda_id=2))
            s.commit()
        p = c.get("/agenda/painel", params={"data": HOJE.isoformat()}).json()
        assert [i["nome"] for i in p["estoque_abaixo_minimo"]] == ["Sincroforte"]

    def test_nao_escreve_e_isola(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _lista_espera(s, ["8801"])
        escritas = _sem_escrita(engine)
        assert c.get("/agenda/painel", params={"data": HOJE.isoformat()}).status_code == 200
        assert escritas == [], escritas
        c.estado["fazenda"] = 2
        assert c.get("/agenda/painel", params={"data": HOJE.isoformat()}).json()["lista_espera_total"] == 0


# ───────────────────────────── /agenda/projecao ─────────────────────────────
class TestProjecao:
    def test_horizonte_invalido(self, ctx):
        c, _ = ctx
        assert c.get("/agenda/projecao", params={"dias": 45}).status_code == 422

    def test_semanas_e_por_semana_tem_o_mesmo_tamanho(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "101")
            _servico(s, "101", 5)                      # repasse em HOJE+9
            s.commit()
        for dias in (30, 60, 90):
            p = c.get("/agenda/projecao", params={"dias": dias, "data": HOJE.isoformat()}).json()
            assert p["dias"] == dias and len(p["semanas"]) >= dias // 7
            for nome, card in p["cards"].items():
                if "por_semana" in card:
                    assert len(card["por_semana"]) == len(p["semanas"]), nome

    def test_repasse_conta_checagens_e_respeita_a_regra(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            for n in ("101", "102", "103"):
                _animal(s, n)
            _servico(s, "101", 5)                                            # +9 dias
            _servico(s, "102", 8, tipo_servico="Monta natural")              # +6 dias
            _servico(s, "103", 5, diagnostico="NEGATIVO")                    # cancela
            s.commit()
        rep = c.get("/agenda/projecao", params={"dias": 30, "data": HOJE.isoformat()}).json()["cards"]["repasse"]
        assert rep["checagens"] == 2 and rep["vacas"] == 2
        assert sum(rep["por_semana"]) == 2
        assert rep["proxima"] == (HOJE + timedelta(days=6)).isoformat()
        # so IATF: a monta natural sai (e a vaca 101 nao tem protocolo -> nao e IATF)
        with Session(engine) as s:
            s.add(RepasseConfig(fazenda_id=1, quem_entra="iatf"))
            s.commit()
        rep = c.get("/agenda/projecao", params={"dias": 30, "data": HOJE.isoformat()}).json()["cards"]["repasse"]
        assert rep["checagens"] == 0

    def test_repasse_desligado_nao_projeta(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "101")
            _servico(s, "101", 5)
            s.add(RepasseConfig(fazenda_id=1, usar=False))
            s.commit()
        rep = c.get("/agenda/projecao", params={"dias": 30, "data": HOJE.isoformat()}).json()["cards"]["repasse"]
        assert rep["usar"] is False and rep["checagens"] == 0

    def test_repasse_falta_de_produto_vira_ruptura_no_estoque(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            for i in range(3):
                _animal(s, f"20{i}")
                _servico(s, f"20{i}", 5)
            item = Estoque(nome="Adesivo detector", categoria="Detecção de cio de repasse", quantidade=1, unidade="un", fazenda_id=1)
            s.add(item)
            s.commit()
            s.refresh(item)
            s.add(RepasseConfig(fazenda_id=1, estoque_id=item.id))
            s.commit()
        cards = c.get("/agenda/projecao", params={"dias": 30, "data": HOJE.isoformat()}).json()["cards"]
        assert cards["repasse"]["produto"]["falta"] == 2
        assert cards["estoque"]["rupturas"][0]["item"] == "Adesivo detector"

    def test_vacinas_agendadas_contam_e_lista_de_espera_so_numero(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _lista_espera(s, ["9901", "9902"])
            ev = EventoSanitario(nome="Vermifugacao", tipo_agendamento="epoca", fazenda_id=1, categoria_preventiva="vacina")
            s.add(ev)
            s.commit()
            s.refresh(ev)
            cal = CalendarioSanitario(evento_sanitario_id=ev.id, categoria_alvo="Novilha", produto="Ivermectina",
                                      frequencia_valor=6, frequencia_unidade="meses", data_evento=HOJE + timedelta(days=3),
                                      usa_cronograma=True, fazenda_id=1)
            s.add(cal)
            s.commit()
            s.refresh(cal)
            cron = CronogramaSanitario(calendario_sanitario_id=cal.id, data_evento=HOJE + timedelta(days=3), status="agendado",
                                       modo_execucao="propria", fazenda_id=1, hora="15:30")
            s.add(cron)
            s.commit()
            s.refresh(cron)
            for b in ("5001", "5002", "5003"):
                s.add(CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=b, status="incluido", data_sugestao=HOJE, fazenda_id=1))
            s.commit()
        p = c.get("/agenda/projecao", params={"dias": 30, "data": HOJE.isoformat()}).json()
        v = p["cards"]["vacinas"]
        assert v["agendadas"] == 1 and v["n_animais"] == 3 and sum(v["por_semana"]) == 1
        assert v["proximas"][0]["nome"] == "Vermifugacao"
        assert p["cards"]["lista_espera"]["n"] == 2
        bruto = json.dumps(p)
        for brinco in ("9901", "9902", "5001", "5002", "5003"):
            assert brinco not in bruto

    def test_nao_escreve_e_isola_por_fazenda(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animal(s, "101")
            _servico(s, "101", 5)
            _animal(s, "901", fazenda_id=2)
            _servico(s, "901", 5, fazenda_id=2)
            s.commit()
        escritas = _sem_escrita(engine)
        f1 = c.get("/agenda/projecao", params={"dias": 30, "data": HOJE.isoformat()}).json()["cards"]["repasse"]["checagens"]
        c.estado["fazenda"] = 2
        f2 = c.get("/agenda/projecao", params={"dias": 30, "data": HOJE.isoformat()}).json()["cards"]["repasse"]["checagens"]
        assert escritas == [], escritas
        assert f1 == 1 and f2 == 1
