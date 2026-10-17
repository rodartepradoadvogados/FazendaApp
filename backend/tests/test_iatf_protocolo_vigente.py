"""
Matriz que já está em protocolo IATF vigente NÃO é lançada de novo — e o veredito
de aptidão que a tela mostra vem do mesmo código que o POST usa.

Cobre `fazenda/rules/iatf_vigente.py`, a trava nos três pontos de entrada
(POST /reproducao/protocolo-iatf, POST /reproducao/protocolo-iatf/{id}/animais,
POST /reproducao/servico-lote) e `GET /reproducao/aptidao-servico`.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, Parto, PesagemCorporal, ProtocoloIatfAplicacao, ProtocoloIatfLancamento, Servico,
)
from fazenda.rules.aptidao import avaliar_aptidao_em_massa, avaliar_aptidao_no_banco, parametros_aptidao
from fazenda.rules.iatf_vigente import protocolos_vigentes_por_animal

HOJE = date.today()


def _meses(n: float) -> int:
    return round(n * 30.44)


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

    with Session(engine) as s:
        for n in ["800", "801", "802", "803"]:
            s.add(Animal(numero=n, sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(40))))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _protocolo(c, animais, d0=None):
    r = c.post("/reproducao/protocolo-iatf", json={"animais": animais, "data_d0": (d0 or HOJE - timedelta(days=3)).isoformat()})
    assert r.status_code == 200, r.text
    return r.json()["lancamento_id"]


def _add(engine, *objs):
    with Session(engine) as s:
        for o in objs:
            s.add(o)
        s.commit()


# ---------------------------------------------------------------------------
# Protocolo novo
# ---------------------------------------------------------------------------
def test_protocolo_novo_recusa_matriz_ja_em_protocolo_vigente(client):
    c, engine = client
    _protocolo(c, ["800"])
    r = c.post("/reproducao/protocolo-iatf", json={"animais": ["800", "801"], "data_d0": HOJE.isoformat()})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["erro"] == "em_protocolo_vigente" and d["motivo"] == "em_protocolo"
    assert d["confirmavel"] is False and d["animais"] == ["800"]
    assert "800" in d["msg"] and "protocolo IATF vigente" in d["msg"]
    with Session(engine) as s:
        # nada foi gravado para 801 (tudo ou nada)
        assert s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "801")).first() is None
        assert len(s.exec(select(ProtocoloIatfLancamento)).all()) == 1


def test_forcar_nao_destrava_matriz_em_protocolo(client):
    c, _ = client
    _protocolo(c, ["800"])
    r = c.post("/reproducao/protocolo-iatf", json={"animais": ["800"], "data_d0": HOJE.isoformat(), "forcar": True})
    assert r.status_code == 409


def test_retry_identico_continua_idempotente(client):
    """Duplo clique / fila offline: o POST repetido devolve "já lançado", não 409."""
    c, _ = client
    d0 = (HOJE - timedelta(days=2)).isoformat()
    r1 = c.post("/reproducao/protocolo-iatf", json={"animais": ["800"], "data_d0": d0})
    r2 = c.post("/reproducao/protocolo-iatf", json={"animais": ["800"], "data_d0": d0})
    assert r1.status_code == 200 and r1.json()["criado"] is True
    assert r2.status_code == 200 and r2.json()["criado"] is False


def test_protocolo_abandonado_nao_bloqueia(client):
    c, engine = client
    _protocolo(c, ["800"], d0=HOJE - timedelta(days=40))
    with Session(engine) as s:
        assert protocolos_vigentes_por_animal(s, fazenda_id=None, numeros=["800"]) == {}
    assert c.post("/reproducao/protocolo-iatf", json={"animais": ["800"], "data_d0": HOJE.isoformat()}).status_code == 200


def test_protocolo_ja_inseminado_nao_bloqueia(client):
    c, engine = client
    _protocolo(c, ["800"], d0=HOJE - timedelta(days=11))
    _add(engine, Servico(numero_matriz="800", data_servico=HOJE, tipo_servico="IA", ult_ocorrencia=1))
    with Session(engine) as s:
        assert protocolos_vigentes_por_animal(s, fazenda_id=None, numeros=["800"]) == {}


def test_protocolo_cancelado_ou_encerrado_nao_bloqueia(client):
    c, engine = client
    l1 = _protocolo(c, ["800"])
    l2 = _protocolo(c, ["801"])
    with Session(engine) as s:
        s.get(ProtocoloIatfLancamento, l1).ativo = False
        s.get(ProtocoloIatfLancamento, l2).encerrado_em = HOJE
        s.commit()
        assert protocolos_vigentes_por_animal(s, fazenda_id=None, numeros=["800", "801"]) == {}


# ---------------------------------------------------------------------------
# Adicionar animais a um protocolo existente
# ---------------------------------------------------------------------------
def test_adicionar_recusa_quem_esta_em_outro_protocolo_vigente(client):
    c, _ = client
    l1 = _protocolo(c, ["800"])
    l2 = _protocolo(c, ["801"], d0=HOJE - timedelta(days=1))
    r = c.post(f"/reproducao/protocolo-iatf/{l2}/animais", json={"animais": ["800", "802"]})
    assert r.status_code == 409
    assert r.json()["detail"]["animais"] == ["800"]
    assert l1 != l2


def test_adicionar_ignora_quem_ja_esta_neste_protocolo(client):
    """Reenviar não pode virar erro: o animal já está aqui, nada a fazer."""
    c, _ = client
    l1 = _protocolo(c, ["800"])
    r = c.post(f"/reproducao/protocolo-iatf/{l1}/animais", json={"animais": ["800", "801"]})
    assert r.status_code == 200 and r.json()["adicionados"] == 1
    r2 = c.post(f"/reproducao/protocolo-iatf/{l1}/animais", json={"animais": ["800", "801"]})
    assert r2.status_code == 200 and r2.json()["adicionados"] == 0


def test_adicionar_aplica_a_mesma_aptidao_do_protocolo_novo(client):
    """Antes, este caminho não validava nada (porta dos fundos para pôr no
    hormônio uma bezerra ou uma vaca a descartar)."""
    c, engine = client
    _add(
        engine,
        Animal(numero="810", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(6))),
        Animal(numero="811", sexo="F", ativo=True, a_descartar=True, data_nasc=HOJE - timedelta(days=_meses(40))),
        Animal(numero="812", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(20))),
        PesagemCorporal(numero_matriz="812", data_pesagem=HOJE - timedelta(days=5), peso_kg=240),
    )
    l1 = _protocolo(c, ["800"])
    for numero, motivo in [("810", "idade"), ("811", "a_descartar")]:
        r = c.post(f"/reproducao/protocolo-iatf/{l1}/animais", json={"animais": [numero], "forcar": True})
        assert r.status_code == 409 and r.json()["detail"]["motivo"] == motivo  # duro: forcar não destrava
    # confirmável (peso lançado abaixo do mínimo): 409 e, com forcar, entra
    r = c.post(f"/reproducao/protocolo-iatf/{l1}/animais", json={"animais": ["812"]})
    assert r.status_code == 409 and r.json()["detail"]["confirmavel"] is True
    r = c.post(f"/reproducao/protocolo-iatf/{l1}/animais", json={"animais": ["812"], "forcar": True})
    assert r.status_code == 200 and r.json()["adicionados"] == 1


# ---------------------------------------------------------------------------
# Inseminação em lote
# ---------------------------------------------------------------------------
def test_cio_natural_e_monta_natural_recusam_matriz_em_protocolo_vigente(client):
    c, engine = client
    _protocolo(c, ["800"])
    for tipo in ("cio_natural", "monta_natural"):
        r = c.post("/reproducao/servico-lote", json={"animais": ["800", "801"], "data_servico": HOJE.isoformat(), "tipo": tipo})
        assert r.status_code == 409, tipo
        d = r.json()["detail"]
        assert d["motivo"] == "em_protocolo" and d["animais"] == ["800"] and d["confirmavel"] is False
    with Session(engine) as s:
        assert s.exec(select(Servico)).first() is None  # tudo ou nada


def test_iatf_da_matriz_em_protocolo_continua_permitida(client):
    """É o fluxo normal: a inseminação do protocolo vincula e fecha o ciclo."""
    c, engine = client
    lid = _protocolo(c, ["800"], d0=HOJE - timedelta(days=11))
    r = c.post("/reproducao/servico-lote", json={
        "animais": ["800"], "data_servico": HOJE.isoformat(), "tipo": "iatf", "protocolo_lancamento_id": lid,
    })
    assert r.status_code == 200 and r.json()["criados"] == 1
    with Session(engine) as s:
        assert protocolos_vigentes_por_animal(s, fazenda_id=None, numeros=["800"]) == {}


def test_servico_datado_antes_do_d0_nao_conflita_com_o_protocolo(client):
    c, _ = client
    _protocolo(c, ["800"], d0=HOJE - timedelta(days=3))
    r = c.post("/reproducao/servico-lote", json={
        "animais": ["800"], "data_servico": (HOJE - timedelta(days=10)).isoformat(), "tipo": "cio_natural",
    })
    assert r.status_code == 200


def test_iatf_com_d0_retroativo_nao_cria_segundo_protocolo_para_quem_ja_esta_em_um(client):
    """Protocolo vigente com TODAS as etapas já marcadas (sem serviço lançado):
    não há etapa pendente para vincular, e gerar um D0 retroativo seria pôr a
    matriz num segundo protocolo."""
    c, engine = client
    lid = _protocolo(c, ["800"])
    with Session(engine) as s:
        for ap in s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lid)).all():
            ap.realizada = True
            s.add(ap)
        s.commit()
    r = c.post("/reproducao/servico-lote", json={
        "animais": ["800"], "data_servico": HOJE.isoformat(), "tipo": "iatf", "auto_lancar_iatf": True,
    })
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "em_protocolo"
    with Session(engine) as s:
        assert len(s.exec(select(ProtocoloIatfLancamento)).all()) == 1
        assert s.exec(select(Servico)).first() is None


# ---------------------------------------------------------------------------
# GET /reproducao/aptidao-servico: a tela mostra o que o POST vai decidir
# ---------------------------------------------------------------------------
def _rebanho_misto(engine):
    _add(
        engine,
        Animal(numero="820", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(6))),            # idade (duro)
        Animal(numero="821", sexo="F", ativo=True, a_descartar=True, data_nasc=HOJE - timedelta(days=_meses(40))),  # a descartar (duro)
        Animal(numero="822", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(20))),            # peso (confirmável)
        PesagemCorporal(numero_matriz="822", data_pesagem=HOJE - timedelta(days=5), peso_kg=240),
        Animal(numero="823", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=_meses(40))),            # gestante (confirmável)
        Parto(numero_matriz="823", data_parto=HOJE - timedelta(days=300)),
        Servico(numero_matriz="823", data_servico=HOJE - timedelta(days=60), diagnostico="POSITIVO", ult_ocorrencia=1),
        Animal(numero="824", sexo="M", ativo=True),                                                         # macho: nem entra na lista
    )


def test_endpoint_de_aptidao_traz_so_quem_nao_e_apta_com_a_confirmabilidade_certa(client):
    c, engine = client
    _rebanho_misto(engine)
    r = c.get("/reproducao/aptidao-servico", params={"data": HOJE.isoformat()})
    assert r.status_code == 200
    animais = r.json()["animais"]
    assert set(animais) == {"820", "821", "822", "823"}
    assert animais["820"]["motivo"] == "idade" and animais["820"]["confirmavel"] is False
    assert animais["821"]["motivo"] == "a_descartar" and animais["821"]["confirmavel"] is False
    assert animais["822"]["motivo"] == "peso" and animais["822"]["confirmavel"] is True
    assert animais["823"]["motivo"] == "gestante" and animais["823"]["confirmavel"] is True
    assert all(a["mensagem"] for a in animais.values())


def test_endpoint_de_aptidao_concorda_com_o_post_de_servico_lote(client):
    """Para cada animal, o que a tela mostra (apta / confirmar / bloqueada) é o
    que o POST faz: sem divergência entre front e back."""
    c, engine = client
    _rebanho_misto(engine)
    veredito = c.get("/reproducao/aptidao-servico", params={"data": HOJE.isoformat()}).json()["animais"]
    corpo = {"data_servico": HOJE.isoformat(), "tipo": "cio_natural"}
    for numero in ["800", "820", "821", "822", "823"]:
        sem = c.post("/reproducao/servico-lote", json={**corpo, "animais": [numero]})
        com = c.post("/reproducao/servico-lote", json={**corpo, "animais": [numero], "forcar": True})
        v = veredito.get(numero)
        if v is None:
            assert sem.status_code == 200, numero
            continue
        assert sem.status_code == 409 and sem.json()["detail"]["motivo"] == v["motivo"], numero
        assert sem.json()["detail"]["confirmavel"] is v["confirmavel"], numero
        assert (com.status_code == 200) is v["confirmavel"], numero


def test_endpoint_de_aptidao_lista_quem_esta_em_protocolo_vigente(client):
    c, _ = client
    lid = _protocolo(c, ["800", "801"])
    dados = c.get("/reproducao/aptidao-servico").json()
    assert set(dados["em_protocolo"]) == {"800", "801"}
    assert dados["em_protocolo"]["800"]["lancamento_id"] == lid
    assert dados["em_protocolo"]["800"]["nome_protocolo"].startswith("PROTOCOLO IATF")
    assert "802" not in dados["em_protocolo"]


def test_veredito_em_massa_e_identico_ao_individual(client):
    _, engine = client
    _rebanho_misto(engine)
    with Session(engine) as s:
        animais = [a for a in s.exec(select(Animal)).all() if a.sexo != "M"]
        massa = avaliar_aptidao_em_massa(s, animais, data=HOJE)
        for a in animais:
            individual = avaliar_aptidao_no_banco(s, a, data=HOJE, params=parametros_aptidao())
            assert massa[a.numero] == individual, a.numero


def test_endpoint_de_aptidao_devolve_os_limites_da_fazenda(client):
    c, _ = client
    dados = c.get("/reproducao/aptidao-servico").json()
    assert dados["idade_min_meses"] > 0 and dados["peso_min_kg"] > 0 and dados["data"] == HOJE.isoformat()


# ---------------------------------------------------------------------------
# "Em andamento": o dado que a tela precisa para habilitar/desabilitar "Remover"
# ---------------------------------------------------------------------------
def test_ativos_informa_se_ha_etapa_confirmada_e_o_servidor_concorda_ao_remover(client):
    c, engine = client
    lid = _protocolo(c, ["800", "801"])
    with Session(engine) as s:
        d0_800 = s.exec(select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.lancamento_id == lid, ProtocoloIatfAplicacao.numero_matriz == "800", ProtocoloIatfAplicacao.dia == 0,
        )).first()
        d0_800.realizada = True
        s.add(d0_800)
        s.commit()
    animais = {a["numero_matriz"]: a for a in c.get("/reproducao/protocolo-iatf/ativos").json()[0]["animais"]}
    assert animais["800"]["tem_etapa_confirmada"] is True
    assert animais["801"]["tem_etapa_confirmada"] is False
    assert c.delete(f"/reproducao/protocolo-iatf/{lid}/animais/800").status_code == 409
    assert c.delete(f"/reproducao/protocolo-iatf/{lid}/animais/801").status_code == 200


def test_ativos_nao_lista_protocolo_cancelado_nem_encerrado(client):
    c, engine = client
    l1 = _protocolo(c, ["800"])
    l2 = _protocolo(c, ["801"], d0=HOJE - timedelta(days=1))
    _protocolo(c, ["802"], d0=HOJE - timedelta(days=2))
    with Session(engine) as s:
        s.get(ProtocoloIatfLancamento, l1).ativo = False
        s.get(ProtocoloIatfLancamento, l2).encerrado_em = HOJE
        s.commit()
    nomes = [a["numero_matriz"] for p in c.get("/reproducao/protocolo-iatf/ativos").json() for a in p["animais"]]
    assert nomes == ["802"]
