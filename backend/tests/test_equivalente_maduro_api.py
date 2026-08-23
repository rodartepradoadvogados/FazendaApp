"""
Integração de ponta a ponta do equivalente maduro: relatório, ficha do
animal e calculadora avulsa (`api/routers/producao.py`), em cima do banco de
verdade — as regras puras já são cobertas por `test_lactacao.py`,
`test_producao_305.py` e `test_equivalente_maduro.py`; aqui o que importa é
a MONTAGEM (derivar ordem de parto por data, separar lactação encerrada de
aberta, agregar por classe para o painel de aferição) a partir de
Parto/Secagem/ControleLeiteiro reais.

Redesign "padronização por vaca": o trio principal usa fatores FIXOS de
tabela (Holandês) — não depende mais de nenhum mínimo de lactações
encerradas do rebanho. `client_sem_base` (5 vacas de fundo, bem abaixo do
mínimo de 20 do painel de aferição) ainda assim produz o trio completo para
1ª/2ª cria — é exatamente o comportamento que a remoção do mínimo garante.

Rebanho sintético: N vacas "de fundo" (EM0..EMn-1), cada uma com 4 partos
espaçados 400 dias (> 305, então a janela do TIM nunca é truncada pelo
parto seguinte) — a 1ª, 2ª e 3ª lactação de cada uma ficam ENCERRADAS (pelo
parto seguinte) e alimentam a amostra do painel de aferição das classes 1, 2
e 3+; a 4ª fica em andamento e é a lactação ATUAL dessas vacas (classe
madura, ja_maduro). Como os dois controles de cada janela (dia 30 e dia 250)
têm o MESMO valor, a integração trapezoidal do trecho MEDIDO colapsa para
produção_diária × 220 exatamente.

Duas vacas "sujeito" (SUJ1: só 1 parto; SUJ2: só 2 partos) têm a lactação
ATUAL ainda aberta na classe 1 e 2 — são elas que testam o trio de
apresentação de uma novilha/segundipara de verdade, em vez de só madura.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ControleLeiteiro, Parto
from fazenda.rules.equivalente_maduro import FATOR_HOLANDES
from fazenda.rules.lactacao import backfill_lactacoes

PRODUCAO_CLASSE1 = 18.0
PRODUCAO_CLASSE2 = 24.0
PRODUCAO_MADURA = 32.0
DIAS_ENTRE_PARTOS = 400  # > 305: a janela do TIM nunca é truncada pelo parto seguinte


def _lanca_lactacao(session: Session, numero: str, ordem: int, inicio: date, producao_dia: float) -> None:
    session.add(Parto(numero_matriz=numero, data_parto=inicio, ordem_parto=ordem))
    for offset in (30, 250):
        session.add(ControleLeiteiro(numero_matriz=numero, data_controle=inicio + timedelta(days=offset), producao_kg=producao_dia))


def _semear_rebanho(session: Session, n_vacas_de_fundo: int) -> None:
    base = date(2018, 1, 1)
    for i in range(n_vacas_de_fundo):
        numero = f"EM{i}"
        session.add(Animal(numero=numero, ativo=True))
        for ordem, producao in ((1, PRODUCAO_CLASSE1), (2, PRODUCAO_CLASSE2), (3, PRODUCAO_MADURA), (4, PRODUCAO_MADURA)):
            inicio = base + timedelta(days=(ordem - 1) * DIAS_ENTRE_PARTOS)
            _lanca_lactacao(session, numero, ordem, inicio, producao)

    # Sujeitos com lactação ATUAL aberta — o caso de verdade do trio.
    session.add(Animal(numero="SUJ1", ativo=True))
    _lanca_lactacao(session, "SUJ1", 1, date(2025, 6, 1), PRODUCAO_CLASSE1)
    session.add(Animal(numero="SUJ2", ativo=True))
    _lanca_lactacao(session, "SUJ2", 1, date(2022, 1, 1), PRODUCAO_CLASSE1)
    _lanca_lactacao(session, "SUJ2", 2, date(2025, 6, 1), PRODUCAO_CLASSE2)
    # A entidade Lactacao (rules/lactacao.py) é a fonte real que os endpoints
    # de EM leem — sem backfill aqui, o cenário teria Parto/ControleLeiteiro
    # mas nenhuma Lactacao, e o relatório veria o rebanho inteiro vazio.
    backfill_lactacoes(session, fazenda_id=None)
    session.commit()


def _cliente(n_vacas_de_fundo: int):
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

    with Session(engine) as s:
        _semear_rebanho(s, n_vacas_de_fundo)

    client = TestClient(main.app)
    return client


@pytest.fixture
def client_com_base():
    c = _cliente(25)
    yield c
    import main
    main.app.dependency_overrides.clear()


@pytest.fixture
def client_sem_base():
    c = _cliente(5)  # bem abaixo do mínimo de 20 do painel de aferição
    yield c
    import main
    main.app.dependency_overrides.clear()


class TestPainelDeAfericao:
    def test_painel_traz_fator_observado_e_fator_de_tabela_por_classe(self, client_com_base):
        r = client_com_base.get("/producao/equivalente-maduro")
        assert r.status_code == 200
        corpo = r.json()
        painel = {l["classe"]: l for l in corpo["painel_afericao"]}
        assert set(painel) == {1, 2, 3}
        # Fator de tabela é sempre o fixo, independente do que o rebanho mostra.
        assert painel[1]["fator_tabela"] == FATOR_HOLANDES[1]
        assert painel[2]["fator_tabela"] == FATOR_HOLANDES[2]
        assert painel[3]["fator_tabela"] == FATOR_HOLANDES[3]
        # Com 25 vacas de fundo (+ a 1ª lactação encerrada da SUJ2), todas as
        # classes batem o mínimo de 20 do painel — fator observado presente.
        assert painel[1]["fator_observado"] == pytest.approx(PRODUCAO_MADURA / PRODUCAO_CLASSE1, abs=1e-3)
        assert painel[1]["n_lactacoes"] == 26
        assert painel[1]["divergencia_pct"] is not None

    def test_painel_nao_afeta_o_trio_principal(self, client_com_base):
        """O fator observado da classe 1 (32/18 ≈ 1,78) é bem diferente do
        fixo de tabela (1,22) — o trio usa SEMPRE o de tabela."""
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "SUJ1")
        assert linha["producao_maturidade_kg"] == pytest.approx(linha["producao_hoje_kg"] * FATOR_HOLANDES[1], abs=0.1)

    def test_sem_base_no_rebanho_ainda_assim_mostra_contagem_no_painel(self, client_sem_base):
        corpo = client_sem_base.get("/producao/equivalente-maduro").json()
        painel = {l["classe"]: l for l in corpo["painel_afericao"]}
        assert painel[3]["n_lactacoes"] == 5  # 5 vacas de fundo, bem abaixo do mínimo de 20
        assert painel[3]["fator_observado"] is None  # sem base madura confiável para o OBSERVADO
        assert painel[3]["fator_tabela"] == FATOR_HOLANDES[3]  # a tabela fixa não se importa com isso


class TestRelatorioSemMinimoDeLactacoesDoRebanho:
    """O núcleo do redesign: nenhuma classe fica "sem base" por falta de
    histórico do rebanho — só por falta de dados DA PRÓPRIA vaca (produção
    não calculável, ordem de parto desconhecida)."""

    def test_vaca_madura_de_fundo_ja_chegou_la(self, client_com_base):
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "EM0")
        assert linha["ja_maduro"] is True
        assert linha["diferenca_kg"] == 0.0
        assert linha["sem_base"] is False

    def test_primipara_recebe_projecao_de_maturidade_com_fator_fixo(self, client_com_base):
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "SUJ1")
        assert linha["classe"] == 1
        assert linha["sem_base"] is False
        assert linha["producao_maturidade_kg"] == pytest.approx(linha["producao_hoje_kg"] * FATOR_HOLANDES[1], abs=0.1)
        assert linha["diferenca_kg"] > 0
        assert linha["confianca_nivel"] is not None

    def test_segundipara_recebe_fator_1_08(self, client_com_base):
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "SUJ2")
        assert linha["classe"] == 2
        assert linha["sem_base"] is False
        assert linha["producao_maturidade_kg"] == pytest.approx(linha["producao_hoje_kg"] * FATOR_HOLANDES[2], abs=0.1)

    def test_primipara_recebe_numero_mesmo_no_rebanho_sem_base_nenhuma(self, client_sem_base):
        """A mudança central: um rebanho com só 5 lactações encerradas por
        classe (bem abaixo do antigo mínimo de 20) NÃO impede mais o
        cálculo — a novilha ainda recebe o trio inteiro."""
        corpo = client_sem_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "SUJ1")
        assert linha["sem_base"] is False
        assert linha["producao_maturidade_kg"] is not None
        assert linha["diferenca_kg"] is not None

    def test_lista_vem_ordenada_pela_diferenca_decrescente(self, client_com_base):
        diferencas = [a["diferenca_kg"] for a in client_com_base.get("/producao/equivalente-maduro").json()["animais"]]
        nao_nulas = [d for d in diferencas if d is not None]
        assert nao_nulas == sorted(nao_nulas, reverse=True)

    def test_linha_traz_del_atual_e_faltam_partos_maturidade(self, client_com_base):
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "SUJ1")
        assert linha["del_atual"] > 0
        assert linha["faltam_partos_maturidade"] == 2  # 1ª cria: faltam a 2ª e a 3ª

        madura = next(a for a in corpo["animais"] if a["numero_matriz"] == "EM0")
        assert madura["faltam_partos_maturidade"] == 0

    def test_ficha_do_animal_bate_com_a_linha_do_relatorio(self, client_com_base):
        relatorio = client_com_base.get("/producao/equivalente-maduro").json()
        linha_relatorio = next(a for a in relatorio["animais"] if a["numero_matriz"] == "SUJ1")
        ficha = client_com_base.get("/producao/equivalente-maduro/SUJ1").json()
        assert ficha["producao_maturidade_kg"] == linha_relatorio["producao_maturidade_kg"]
        assert ficha["diferenca_kg"] == linha_relatorio["diferenca_kg"]

    def test_ficha_de_animal_sem_lactacao_da_404(self, client_com_base):
        r = client_com_base.get("/producao/equivalente-maduro/NAO-EXISTE")
        assert r.status_code == 404

    def test_calculadora_usa_o_mesmo_fator_fixo_do_relatorio(self, client_com_base):
        r = client_com_base.post("/producao/equivalente-maduro/calcular", json={
            "ordem_parto": 1,
            "pontos": [{"del_dias": 30, "producao_kg": PRODUCAO_CLASSE1}, {"del_dias": 250, "producao_kg": PRODUCAO_CLASSE1}],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["sem_base"] is False
        assert corpo["producao_maturidade_kg"] == pytest.approx(corpo["producao_hoje_kg"] * FATOR_HOLANDES[1], abs=0.1)

    def test_calculadora_nao_depende_de_nenhum_historico_do_rebanho(self, client_sem_base):
        """Mesmo dado exatamente o mesmo perfil, a calculadora não olha para
        o rebanho — é a mesma conta independente de `client_sem_base` ou
        `client_com_base`."""
        r = client_sem_base.post("/producao/equivalente-maduro/calcular", json={
            "ordem_parto": 1,
            "pontos": [{"del_dias": 30, "producao_kg": PRODUCAO_CLASSE1}, {"del_dias": 250, "producao_kg": PRODUCAO_CLASSE1}],
        })
        assert r.status_code == 200
        assert r.json()["sem_base"] is False

    def test_calculadora_com_um_ponto_so_fica_sem_base(self, client_com_base):
        r = client_com_base.post("/producao/equivalente-maduro/calcular", json={
            "ordem_parto": 1,
            "pontos": [{"del_dias": 30, "producao_kg": 20.0}],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["sem_base"] is True
        assert "dois controles" in corpo["motivo"]

    def test_calculadora_nao_grava_nada(self, client_com_base):
        antes = client_com_base.get("/producao/controles").json()["total"]
        client_com_base.post("/producao/equivalente-maduro/calcular", json={
            "ordem_parto": 1,
            "pontos": [{"del_dias": 30, "producao_kg": 20.0}, {"del_dias": 250, "producao_kg": 22.0}],
        })
        depois = client_com_base.get("/producao/controles").json()["total"]
        assert antes == depois
