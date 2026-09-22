"""
Cobre o bug relatado: animais com protocolo de IATF "concluído" (D0/D7/D9/D11
todos `realizada=True`) apareciam como "Atrasados" na Agenda. Causa raiz — a
Central de Protocolos deixava dar baixa (POST /central-protocolos/iatf/
{id}/baixa) no dia de inseminação (o maior `dia` do lançamento, nem sempre
11 — ver fazenda.rules.protocolo_iatf.dia_inseminacao) exatamente como
qualquer dia de hormônio: marca `realizada=True` + Sanidade + baixa de
estoque, mas NUNCA cria o `Servico` (touro/sêmen). Sem o Servico,
`estado_reprodutivo.classificar_animal` nunca reconhece a matriz como
"Inseminada" depois que a janela D0–D11 fecha — ela cai em "Atrasada" mesmo
com o protocolo 100% concluído na Central.

O único caminho correto para o dia de inseminação é "Ir para Inseminação"
(POST /reproducao/servicos, que cria o Servico e fecha a etapa sozinho) — a
Agenda já faz essa distinção; a Central não fazia. Este teste cobre o
bloqueio novo: dar baixa no dia de inseminação pela Central agora falha com
400, orientando a registrar o serviço em Reprodução.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ProtocoloIatfAplicacao, Servico


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
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _lancar_iatf(c, animais, data_d0="2026-08-05"):
    r = c.post("/reproducao/protocolo-iatf", json={"animais": animais, "data_d0": data_d0})
    assert r.status_code == 200, r.text
    return r.json()["lancamento_id"]


class TestBloqueiaBaixaNoDiaDeInseminacao:
    def test_dar_baixa_no_dia_11_e_recusado(self, client):
        c, engine = client
        lancamento_id = _lancar_iatf(c, ["700"])

        r = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 11})
        assert r.status_code == 400, r.text
        assert "inseminação" in r.json()["detail"].lower()

        # Nada foi gravado: a aplicação de D11 continua pendente e nenhum
        # Servico foi criado.
        with Session(engine) as s:
            ap_d11 = s.exec(
                select(ProtocoloIatfAplicacao)
                .where(ProtocoloIatfAplicacao.lancamento_id == lancamento_id, ProtocoloIatfAplicacao.dia == 11)
            ).first()
            assert ap_d11 is not None and ap_d11.realizada is False
            assert s.exec(select(Servico).where(Servico.numero_matriz == "700")).first() is None

    def test_dar_baixa_nos_outros_dias_continua_funcionando(self, client):
        c, engine = client
        lancamento_id = _lancar_iatf(c, ["700"])

        for dia in (0, 7, 9):
            r = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": dia})
            assert r.status_code == 200, r.text

        with Session(engine) as s:
            aps = s.exec(
                select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lancamento_id)
            ).all()
            realizados = {a.dia: a.realizada for a in aps}
            assert realizados[0] is True and realizados[7] is True and realizados[9] is True
            assert realizados[11] is False

    def test_dia_de_inseminacao_nao_literal_11_tambem_e_bloqueado(self, client):
        """Molde D0/D8/D10 -> inseminação em D12 (maior dia hormônio + 2),
        não 11 — o bloqueio tem que ser dinâmico, não hardcoded. Os dias do
        lançamento vêm do MOLDE cadastrado (protocolo_id), não da lista
        `hormonios` ad-hoc — ver `_passos_do_lancamento` em reproducao.py."""
        c, engine = client
        r = c.post("/cadastro/protocolos-iatf", json={
            "nome": "Molde D0/D8/D10",
            "etapas": [
                {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
                {"dia": 8, "produto": "Cloprostenol", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
                {"dia": 10, "produto": "Cipionato", "dose": 1, "unidade": "ml", "via": "Intramuscular"},
            ],
        })
        assert r.status_code == 200, r.text
        molde_id = r.json()["id"]

        r = c.post("/reproducao/protocolo-iatf", json={
            "animais": ["701"], "data_d0": "2026-08-05", "protocolo_id": molde_id,
        })
        assert r.status_code == 200, r.text
        lancamento_id = r.json()["lancamento_id"]

        with Session(engine) as s:
            dias = sorted(
                a.dia for a in s.exec(
                    select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lancamento_id)
                ).all()
            )
        assert dias == [0, 8, 10, 12], dias

        r = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 12})
        assert r.status_code == 400, r.text

        r = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 10})
        assert r.status_code == 200, r.text
