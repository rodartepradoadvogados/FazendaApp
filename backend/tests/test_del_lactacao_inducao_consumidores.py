"""
Matriz 422 — indução de lactação concluída e confirmada, mas "sem DEL".

A `Lactacao` aberta por indução (`origem="inducao"`, sem `Parto` por trás) é a
fonte única do DEL ("conta como um parto"). A listagem GET /animais/ já a lia,
mas três consumidores calculavam o DEL só com `ultimo parto produtivo` +
`ultima secagem` e devolviam None para a vaca que tem parto antigo (2025),
secagem depois dele e uma indução mais nova:

  * Ficha do animal (GET /animais/{numero}/ficha) — "sem DEL" e sem previsão;
  * motor da Agenda — DEL atual/projetado do BST e decisão de secar;
  * card "DEL médio" dos Indicadores.

Cobre a função pura `del_dias_ao_vivo` e cada consumidor, partindo do estado
real da 422: parto em 2025 -> secagem -> indução (D0..D6) -> confirmação.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Lactacao, Parto, ProtocoloInducaoAplicacao, Secagem
from fazenda.rules.indicadores import calcular_indicadores
from fazenda.rules.producao_leiteira import del_dias_ao_vivo

HOJE = date(2026, 10, 18)


class TestFuncaoPura:
    def test_inducao_mais_nova_que_a_secagem_conta_del_da_inducao(self):
        # parto 2025 -> secagem -> indução em 08/10: DEL = 10, não None.
        assert del_dias_ao_vivo(None, date(2025, 3, 1), date(2026, 1, 10), HOJE, inicio_lactacao=date(2026, 10, 8)) == 10

    def test_sem_lactacao_aberta_mantem_o_comportamento_antigo(self):
        assert del_dias_ao_vivo(None, date(2025, 3, 1), date(2026, 1, 10), HOJE) is None
        assert del_dias_ao_vivo(None, date(2026, 9, 28), None, HOJE) == 20

    def test_parto_real_mais_novo_vence_a_lactacao_mais_velha(self):
        # Mesma âncora de estado_reprodutivo: max(parto, início da lactação).
        assert del_dias_ao_vivo(None, date(2026, 10, 1), None, HOJE, inicio_lactacao=date(2026, 8, 1)) == 17

    def test_aborto_ou_inducao_sem_nenhum_parto_tambem_tem_del(self):
        assert del_dias_ao_vivo(None, None, None, HOJE, inicio_lactacao=date(2026, 10, 3)) == 15

    def test_secagem_depois_da_lactacao_zera(self):
        assert del_dias_ao_vivo(None, date(2025, 3, 1), date(2026, 10, 12), HOJE, inicio_lactacao=date(2026, 10, 8)) is None


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


def _cenario_422(c, engine, *, confirmar: bool = True) -> date:
    """Parto em 2025 -> secagem -> indução de lactação concluída (D0 há 10 dias).
    Devolve a data de início da lactação por indução."""
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(
            numero="422", sexo="F", ativo=True, del_dias=0, grupo_primario="02 - Vacas Alta",
            categoria_completa="Vaca seca", categoria_abrev="Vaca seca",
        ))
        s.add(Parto(numero_matriz="422", data_parto=hoje - timedelta(days=420), ordem_parto=2, tipo_parto="Normal"))
        s.add(Secagem(numero_matriz="422", data_secagem=hoje - timedelta(days=60), motivo="rotina"))
        s.commit()

    pid = c.post("/cadastro/protocolos-inducao-lactacao", json={
        "nome": "Indução padrão", "dia_inicial": 0,
        "etapas": [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 5, "unidade": "ml"},
            {"dia": 6, "tipo": "manejo", "produto": "Iniciar ordenha"},
        ],
    }).json()["id"]
    d0 = hoje - timedelta(days=10)
    lancamento_id = c.post("/producao/inducao-lactacao", json={
        "protocolo_id": pid, "animais": ["422"], "data_d0": d0.isoformat(),
    }).json()["lancamento_id"]
    with Session(engine) as s:
        for a in s.exec(select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.lancamento_id == lancamento_id)).all():
            a.realizada = True
            a.data_realizacao = a.data_prevista
            s.add(a)
        s.commit()
    inicio = d0 + timedelta(days=6)  # data_sugerida = última etapa
    if confirmar:
        r = c.post(f"/producao/inducao-lactacao/{lancamento_id}/422/confirmar", json={"entrou_em_lactacao": True})
        assert r.status_code == 200, r.text
        assert r.json()["entrou_em_lactacao"] is True
    return inicio


class TestMatriz422:
    def test_listagem_ja_mostrava_o_del_da_inducao(self, client):
        c, engine = client
        inicio = _cenario_422(c, engine)
        animal = next(a for a in c.get("/animais/", params={"ativo": True}).json() if a["numero"] == "422")
        assert animal["del_dias"] == (date.today() - inicio).days
        assert animal["em_lactacao"] is True

    def test_ficha_mostra_del_e_lactacao_por_inducao(self, client):
        c, engine = client
        inicio = _cenario_422(c, engine)
        ficha = c.get("/animais/422/ficha").json()
        assert ficha["animal"]["del_dias"] == (date.today() - inicio).days
        # Categoria "Vaca seca" do CSV não pode contradizer a lactação aberta.
        assert ficha["lactacao_atual"]["origem"] == "inducao"
        assert ficha["lactacao_atual"]["data_inicio"] == inicio.isoformat()
        assert ficha["lactacao_atual"]["del_dias"] == (date.today() - inicio).days
        assert [(l["origem"], l["data_fim"]) for l in ficha["lactacoes"]][-1] == ("inducao", None)

    def test_ficha_sem_confirmar_a_inducao_continua_sem_del(self, client):
        # Indução concluída mas o card da Agenda ainda não foi respondido: não
        # inventa lactação — o DEL só nasce da confirmação.
        c, engine = client
        _cenario_422(c, engine, confirmar=False)
        ficha = c.get("/animais/422/ficha").json()
        assert ficha["animal"]["del_dias"] is None
        assert ficha["lactacao_atual"] is None

    def test_agenda_bst_usa_o_del_da_inducao(self, client):
        c, engine = client
        inicio = _cenario_422(c, engine)
        agenda = c.get("/agenda/", params={"data": date.today().isoformat(), "dias": 5}).json()
        linhas = [b for lista in ("bst_elegiveis", "bst_nunca_aplicados", "bst_excluidos") for b in agenda.get(lista, []) if b["numero_matriz"] == "422"]
        assert linhas, "422 deveria constar em alguma lista de BST"
        assert linhas[0]["del_atual"] == (date.today() - inicio).days


    def test_tela_secagem_usa_o_del_da_inducao_e_nao_o_do_parto_antigo(self, client):
        c, engine = client
        inicio = _cenario_422(c, engine)
        r = c.get("/producao/secagem-info", params={"numero_matriz": "422"})
        assert r.status_code == 200, r.text
        assert r.json()["del_atual"] == (date.today() - inicio).days


class TestCardDelMedio:
    def test_del_medio_conta_a_vaca_em_inducao(self):
        animais = [{"numero": "422", "sexo": "F", "ativo": True, "grupo_primario": "02 - Vacas Alta", "del_dias": 0}]
        partos = [{"numero_matriz": "422", "data_parto": date(2025, 3, 1), "tipo_parto": "Normal"}]
        secagens = [{"numero_matriz": "422", "data_secagem": date(2026, 1, 10)}]
        sem = calcular_indicadores(animais, [], partos, data_ref=HOJE, secagens=secagens)
        com = calcular_indicadores(
            animais, [], partos, data_ref=HOJE, secagens=secagens,
            inicio_lactacao_por_animal={"422": date(2026, 10, 8)},
        )
        assert sem["producao"]["del_medio_animais"] == 0
        assert com["producao"]["del_medio_animais"] == 1
        assert com["producao"]["del_medio"] == 10
