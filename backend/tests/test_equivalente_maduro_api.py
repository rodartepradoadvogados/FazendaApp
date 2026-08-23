"""
Integração de ponta a ponta do equivalente maduro: relatório, ficha do
animal e calculadora avulsa (`api/routers/producao.py`), em cima do banco de
verdade — as regras puras já são cobertas por `test_lactacao.py`,
`test_producao_305.py` e `test_equivalente_maduro.py`; aqui o que importa é
a MONTAGEM (derivar ordem de parto por data, separar lactação encerrada de
aberta, agregar por classe) a partir de Parto/Secagem/ControleLeiteiro reais.

Rebanho sintético: 25 vacas "de fundo" (EM0..EM24), cada uma com 4 partos
espaçados 400 dias (> 305, então a janela do TIM nunca é truncada pelo
parto seguinte) — a 1ª, 2ª e 3ª lactação de cada uma ficam ENCERRADAS (pelo
parto seguinte) e alimentam a amostra das classes 1, 2 e 3+; a 4ª fica em
andamento e é a lactação ATUAL dessas vacas (classe madura, ja_maduro).
Como os dois controles de cada janela (dia 30 e dia 250) têm o MESMO valor,
a integração trapezoidal colapsa para produção_diária × 305 exatamente —
o que torna os fatores esperados uma conta de cabeça: fator(classe) =
produção_madura / produção_da_classe.

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
from fazenda.rules.lactacao import backfill_lactacoes

PRODUCAO_CLASSE1 = 18.0
PRODUCAO_CLASSE2 = 24.0
PRODUCAO_MADURA = 32.0
DIAS_ENTRE_PARTOS = 400  # > 305: a janela do TIM nunca é truncada pelo parto seguinte
FATOR_CLASSE1_ESPERADO = PRODUCAO_MADURA / PRODUCAO_CLASSE1  # 1,7778
FATOR_CLASSE2_ESPERADO = PRODUCAO_MADURA / PRODUCAO_CLASSE2  # 1,3333


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
    c = _cliente(5)  # menos de 20 lactações encerradas por classe
    yield c
    import main
    main.app.dependency_overrides.clear()


class TestRelatorioComBaseSuficiente:
    def test_fatores_batem_com_a_razao_das_medias(self, client_com_base):
        r = client_com_base.get("/producao/equivalente-maduro")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["sem_base_geral"] is None
        assert corpo["fatores"]["1"]["fator"] == pytest.approx(FATOR_CLASSE1_ESPERADO, abs=1e-3)
        assert corpo["fatores"]["2"]["fator"] == pytest.approx(FATOR_CLASSE2_ESPERADO, abs=1e-3)
        assert corpo["fatores"]["3"]["fator"] == 1.0
        # 25 vacas de fundo + a 1ª lactação (já encerrada) da SUJ2, que pariu
        # de novo e por isso também vira amostra da classe 1.
        assert corpo["fatores"]["1"]["n_lactacoes"] == 26
        assert corpo["fatores"]["1"]["confianca"] == "baixa"  # entre 20 e 49
        # `amostras_por_classe` bate com `fatores[classe].n_lactacoes` quando a
        # classe tem fator publicado (aqui, todas as 3 têm).
        assert corpo["amostras_por_classe"]["1"] == 26
        assert corpo["amostras_por_classe"]["2"] == corpo["fatores"]["2"]["n_lactacoes"]
        assert corpo["amostras_por_classe"]["3"] == corpo["fatores"]["3"]["n_lactacoes"]

    def test_vaca_madura_de_fundo_ja_chegou_la(self, client_com_base):
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "EM0")
        assert linha["ja_maduro"] is True
        assert linha["diferenca_kg"] == 0.0
        assert linha["sem_base"] is False

    def test_primipara_recebe_projecao_de_maturidade(self, client_com_base):
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "SUJ1")
        assert linha["classe"] == 1
        assert linha["sem_base"] is False
        assert linha["producao_hoje_kg"] == pytest.approx(PRODUCAO_CLASSE1 * 305, abs=1.0)
        assert linha["producao_maturidade_kg"] > linha["producao_hoje_kg"]
        assert linha["diferenca_kg"] > 0

    def test_segundipara_recebe_projecao_sem_faixa(self, client_com_base):
        corpo = client_com_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "SUJ2")
        assert linha["classe"] == 2
        assert linha["sem_base"] is False
        assert linha["faixa_diferenca_kg"] is None  # faixa é só para 1ª cria

    def test_lista_vem_ordenada_pela_diferenca_decrescente(self, client_com_base):
        diferencas = [a["diferenca_kg"] for a in client_com_base.get("/producao/equivalente-maduro").json()["animais"]]
        nao_nulas = [d for d in diferencas if d is not None]
        assert nao_nulas == sorted(nao_nulas, reverse=True)

    def test_ficha_do_animal_bate_com_a_linha_do_relatorio(self, client_com_base):
        relatorio = client_com_base.get("/producao/equivalente-maduro").json()
        linha_relatorio = next(a for a in relatorio["animais"] if a["numero_matriz"] == "SUJ1")
        ficha = client_com_base.get("/producao/equivalente-maduro/SUJ1").json()
        assert ficha["producao_maturidade_kg"] == linha_relatorio["producao_maturidade_kg"]
        assert ficha["diferenca_kg"] == linha_relatorio["diferenca_kg"]

    def test_ficha_de_animal_sem_lactacao_da_404(self, client_com_base):
        r = client_com_base.get("/producao/equivalente-maduro/NAO-EXISTE")
        assert r.status_code == 404

    def test_calculadora_projeta_igual_ao_relatorio_para_o_mesmo_perfil(self, client_com_base):
        r = client_com_base.post("/producao/equivalente-maduro/calcular", json={
            "ordem_parto": 1,
            "pontos": [{"del_dias": 30, "producao_kg": PRODUCAO_CLASSE1}, {"del_dias": 250, "producao_kg": PRODUCAO_CLASSE1}],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["sem_base"] is False
        assert corpo["producao_hoje_kg"] == pytest.approx(PRODUCAO_CLASSE1 * 305, abs=1.0)
        assert corpo["producao_maturidade_kg"] == pytest.approx(PRODUCAO_CLASSE1 * 305 * FATOR_CLASSE1_ESPERADO, abs=1.0)

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


class TestRelatorioSemBaseSuficiente:
    def test_sem_20_lactacoes_na_madura_degrada_tudo(self, client_sem_base):
        corpo = client_sem_base.get("/producao/equivalente-maduro").json()
        assert corpo["fatores"] == {}
        assert corpo["sem_base_geral"] is not None
        primipara_ou_segundipara = [a for a in corpo["animais"] if a["classe"] in (1, 2)]
        assert primipara_ou_segundipara  # o cenário seedou SUJ1/SUJ2
        assert all(a["sem_base"] is True for a in primipara_ou_segundipara)

    def test_amostras_por_classe_mostra_a_contagem_mesmo_com_fatores_vazio(self, client_sem_base):
        """É exatamente o caso em que `fatores` fica {} (nenhuma classe
        publicada) — sem esta contagem, o usuário não teria como saber
        QUANTAS lactações faltam para cada classe, só que "está sem base"."""
        corpo = client_sem_base.get("/producao/equivalente-maduro").json()
        assert corpo["fatores"] == {}
        assert corpo["amostras_por_classe"]["3"] == 5  # client_sem_base = 5 vacas de fundo
        assert corpo["amostras_por_classe"]["3"] < 20

    def test_vaca_madura_ainda_assim_ja_chegou_la(self, client_sem_base):
        """Mesmo com o rebanho inteiro sem base para ajustar 1ª/2ª cria, uma
        vaca madura não precisa de fator nenhum — o dela é 1 por definição."""
        corpo = client_sem_base.get("/producao/equivalente-maduro").json()
        linha = next(a for a in corpo["animais"] if a["numero_matriz"] == "EM0")
        assert linha["ja_maduro"] is True
        assert linha["sem_base"] is False
