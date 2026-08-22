"""
Trava de aptidão para serviço reprodutivo (`fazenda/rules/aptidao.py`) e sua
aplicação nos três pontos de entrada: POST /reproducao/servico,
POST /reproducao/servico-lote e POST /reproducao/protocolo-iatf.

O buraco que estes testes fecham: nenhum desses caminhos validava nada além
de "o animal existe". Dava para inseminar bezerra, macho, animal baixado ou
vaca já prenhe — e neste último caso o sistema INVENTAVA sozinho uma perda de
prenhez no serviço anterior (ver rules/perda_prenhez.py). A trava que existia
morava só no frontend, com `13` cravado no código, divergente do parâmetro
real da fazenda (15) e invisível para o app de campo e o bot do Telegram, que
chamam a API direto.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, PesagemCorporal, Servico
from fazenda.rules.aptidao import (
    APTA, AptidaoResultado, ContextoAptidao, ParametrosAptidao, MOTIVO_GESTANTE, MOTIVO_IDADE,
    MOTIVO_PESO, MOTIVO_SEM_PESAGEM, MOTIVO_SEXO, avaliar_aptidao_servico,
)

HOJE = date.today()
PARAMS = ParametrosAptidao(idade_apta_min_meses=15, peso_apta_min_kg=300)


def _meses(n: float) -> int:
    return round(n * 30.44)


# ---------------------------------------------------------------------------
# A função pura
# ---------------------------------------------------------------------------
def test_novilha_apta_passa():
    animal = {"numero": "10", "sexo": "F", "ativo": True}
    ctx = ContextoAptidao(idade_dias=_meses(18), peso_kg=340, tem_pesagem=True)
    assert avaliar_aptidao_servico(animal, ctx, PARAMS) == APTA


def test_idade_abaixo_do_minimo_e_bloqueio_duro():
    """14 meses passava na trava antiga do frontend (13) e é reprovada pelo
    parâmetro real da fazenda (15). Duro: `forcar` não destrava."""
    animal = {"numero": "10", "sexo": "F", "ativo": True}
    ctx = ContextoAptidao(idade_dias=_meses(14), peso_kg=340, tem_pesagem=True)
    r = avaliar_aptidao_servico(animal, ctx, PARAMS)
    assert r.motivo == MOTIVO_IDADE
    assert r.bloqueia(forcar=False) and r.bloqueia(forcar=True)
    assert "15 meses" in r.mensagem


def test_macho_e_animal_baixado_sao_bloqueios_duros():
    macho = avaliar_aptidao_servico({"numero": "M1", "sexo": "M", "ativo": True}, ContextoAptidao(), PARAMS)
    assert macho.motivo == MOTIVO_SEXO and macho.bloqueia(forcar=True)

    baixado = avaliar_aptidao_servico(
        {"numero": "20", "sexo": "F", "ativo": False}, ContextoAptidao(idade_dias=_meses(30), ja_pariu=True), PARAMS,
    )
    assert baixado.bloqueia(forcar=True)


def test_sem_pesagem_nao_inventa_peso_mas_pede_confirmacao():
    """Novilha sem NENHUMA pesagem: não se afirma que está leve (o dado não
    existe), mas também não passa em silêncio — exige confirmação explícita."""
    animal = {"numero": "10", "sexo": "F", "ativo": True}
    ctx = ContextoAptidao(idade_dias=_meses(20), peso_kg=None, tem_pesagem=False)
    r = avaliar_aptidao_servico(animal, ctx, PARAMS)
    assert r.motivo == MOTIVO_SEM_PESAGEM
    assert r.bloqueia(forcar=False)
    assert not r.bloqueia(forcar=True)


def test_peso_abaixo_do_minimo_e_confirmavel():
    animal = {"numero": "10", "sexo": "F", "ativo": True}
    ctx = ContextoAptidao(idade_dias=_meses(20), peso_kg=250, tem_pesagem=True)
    r = avaliar_aptidao_servico(animal, ctx, PARAMS)
    assert r.motivo == MOTIVO_PESO
    assert r.bloqueia(forcar=False) and not r.bloqueia(forcar=True)


def test_vaca_que_ja_pariu_nao_e_cobrada_por_peso():
    """Peso de aptidão é critério de NOVILHA. Cobrar pesagem de uma vaca de
    terceira cria seria ruído puro."""
    animal = {"numero": "10", "sexo": "F", "ativo": True}
    ctx = ContextoAptidao(idade_dias=_meses(60), peso_kg=None, tem_pesagem=False, ja_pariu=True)
    assert avaliar_aptidao_servico(animal, ctx, PARAMS).apta


def test_gestante_vigente_exige_confirmacao():
    """Reinseminar quem consta como prenhe faz o sistema gravar uma perda de
    prenhez no serviço anterior — decisão que agora precisa de gente."""
    animal = {"numero": "14", "sexo": "F", "ativo": True}
    servico = {"diagnostico": "POSITIVO", "data_perda_prenhez": None, "data_servico": HOJE - timedelta(days=40)}
    ctx = ContextoAptidao(idade_dias=_meses(30), ja_pariu=True, servico_vigente=servico)
    r = avaliar_aptidao_servico(animal, ctx, PARAMS)
    assert r.motivo == MOTIVO_GESTANTE
    assert r.bloqueia(forcar=False) and not r.bloqueia(forcar=True)


def test_gestante_com_perda_ja_registrada_nao_bloqueia():
    """Usa `servico_esta_positivo_vigente`, que NÃO esquece
    `data_perda_prenhez` — o erro que mantinha gestante quem já tinha a perda
    lançada."""
    animal = {"numero": "14", "sexo": "F", "ativo": True}
    servico = {"diagnostico": "POSITIVO", "data_perda_prenhez": HOJE - timedelta(days=3)}
    ctx = ContextoAptidao(idade_dias=_meses(30), ja_pariu=True, servico_vigente=servico)
    assert avaliar_aptidao_servico(animal, ctx, PARAMS).apta


def test_sem_idade_cadastrada_nao_reprova_por_idade():
    """Lacuna assumida: não dá para afirmar que está abaixo do mínimo sem
    saber a idade."""
    animal = {"numero": "10", "sexo": "F", "ativo": True}
    ctx = ContextoAptidao(idade_dias=None, peso_kg=340, tem_pesagem=True, ja_pariu=True)
    assert avaliar_aptidao_servico(animal, ctx, PARAMS).apta


# ---------------------------------------------------------------------------
# Os endpoints
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    lock = threading.Lock()

    def _get_session_override():
        with lock, Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_id_escrita

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: None

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _add(engine, *objs):
    with Session(engine) as s:
        for o in objs:
            s.add(o)
        s.commit()


def test_post_servico_recusa_bezerra_com_409(client):
    c, engine = client
    _add(engine, Animal(numero="900", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(6))))
    r = c.post("/reproducao/servico", json={"numero_matriz": "900", "data_servico": HOJE.isoformat()})
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["motivo"] == MOTIVO_IDADE
    assert detalhe["confirmavel"] is False
    with Session(engine) as s:
        assert s.exec(select(Servico)).first() is None


def test_post_servico_bezerra_nao_passa_nem_com_forcar(client):
    """Bloqueio DURO: `forcar` é para o limítrofe, não para o absurdo."""
    c, engine = client
    _add(engine, Animal(numero="901", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(6))))
    r = c.post("/reproducao/servico", json={
        "numero_matriz": "901", "data_servico": HOJE.isoformat(), "forcar": True,
    })
    assert r.status_code == 409


def test_post_servico_novilha_sem_pesagem_bloqueia_e_forcar_destrava(client):
    c, engine = client
    _add(engine, Animal(numero="902", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(20))))

    bloqueado = c.post("/reproducao/servico", json={"numero_matriz": "902", "data_servico": HOJE.isoformat()})
    assert bloqueado.status_code == 409
    assert bloqueado.json()["detail"]["motivo"] == MOTIVO_SEM_PESAGEM
    assert bloqueado.json()["detail"]["confirmavel"] is True

    ok = c.post("/reproducao/servico", json={
        "numero_matriz": "902", "data_servico": HOJE.isoformat(), "forcar": True,
    })
    assert ok.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Servico)).first() is not None


def test_post_servico_com_pesagem_suficiente_passa_direto(client):
    c, engine = client
    _add(
        engine,
        Animal(numero="903", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(20))),
        PesagemCorporal(numero_matriz="903", data_pesagem=HOJE - timedelta(days=10), peso_kg=350),
    )
    r = c.post("/reproducao/servico", json={"numero_matriz": "903", "data_servico": HOJE.isoformat()})
    assert r.status_code == 200


def test_post_servico_matriz_gestante_exige_forcar(client):
    """O caso perigoso: sem `forcar`, o sistema não escreve mais uma perda de
    prenhez que ninguém afirmou."""
    c, engine = client
    _add(
        engine,
        Animal(numero="904", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(40))),
        Servico(numero_matriz="904", data_servico=HOJE - timedelta(days=40), diagnostico="POSITIVO", ult_ocorrencia=1),
    )
    bloqueado = c.post("/reproducao/servico", json={"numero_matriz": "904", "data_servico": HOJE.isoformat()})
    assert bloqueado.status_code == 409
    assert bloqueado.json()["detail"]["motivo"] == MOTIVO_GESTANTE
    with Session(engine) as s:
        anterior = s.exec(select(Servico)).first()
        assert anterior.data_perda_prenhez is None  # nada foi inventado

    ok = c.post("/reproducao/servico", json={
        "numero_matriz": "904", "data_servico": HOJE.isoformat(), "forcar": True,
    })
    assert ok.status_code == 200


def test_servico_lote_recusa_o_lote_inteiro_e_nao_grava_nada(client):
    """Tudo ou nada: abortar no meio deixaria metade do lote gravada."""
    c, engine = client
    _add(
        engine,
        Animal(numero="910", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(30))),
        PesagemCorporal(numero_matriz="910", data_pesagem=HOJE - timedelta(days=5), peso_kg=520),
        Animal(numero="911", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(5))),
    )
    r = c.post("/reproducao/servico-lote", json={
        "animais": ["910", "911"], "data_servico": HOJE.isoformat(), "tipo": "cio_natural",
    })
    assert r.status_code == 409
    assert "911" in r.json()["detail"]["animais"]
    with Session(engine) as s:
        assert s.exec(select(Servico)).first() is None


def test_protocolo_iatf_recusa_animal_inapto(client):
    """A trava vale AQUI PRIMEIRO: entre o D0 e a IA passam ~11 dias de
    hormônio aplicado num bicho que nunca deveria ter entrado."""
    c, engine = client
    _add(engine, Animal(numero="920", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(8))))
    r = c.post("/reproducao/protocolo-iatf", json={"animais": ["920"], "data_d0": HOJE.isoformat()})
    assert r.status_code == 409
    assert r.json()["detail"]["motivo"] == MOTIVO_IDADE
