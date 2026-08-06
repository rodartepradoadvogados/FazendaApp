"""
Fechamento do ciclo de um protocolo — o que estava quebrado até 08/2026.

A Agenda era o ÚNICO lugar do sistema capaz de gravar `realizada = True`, e
escondia a etapa cujo dia já tinha passado. Resultado: protocolo que perdeu o
dia ficava travado em "em andamento" para sempre, sem nenhuma tela capaz de
fechá-lo (relato: três protocolos IATF parados em 18/36, 15/20 e 8/16).

Aqui se cobre:
1. etapa vencida volta a aparecer na Agenda, dentro da janela de 30 dias;
2. a Central dá baixa mesmo FORA da janela, com a data REAL da aplicação;
3. a baixa por lançamento não vaza para outro lote com o mesmo D0;
4. encerrar tira da Agenda e do Acompanhamento SEM fingir que as etapas que
   sobraram foram feitas.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Animal, ProtocoloIatfAplicacao, ProtocoloIatfLancamento
from fazenda.rules.protocolo_customizado import JANELA_ATRASO_DIAS


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


def _animais(engine, numeros):
    with Session(engine) as s:
        for n in numeros:
            s.add(Animal(numero=n, ativo=True))
        s.commit()


def _lancar_iatf(c, animais, data_d0: date) -> int:
    r = c.post("/reproducao/protocolo-iatf", json={
        "animais": animais, "data_d0": data_d0.isoformat(),
    })
    assert r.status_code == 200, r.text
    return r.json()["lancamento_id"]


def _eventos_iatf(c):
    """Pendências IATF como o usuário as vê: a Agenda aberta em HOJE.

    A janela de atraso é contada a partir da data PEDIDA à agenda, não de
    hoje — pedir a agenda de 120 dias atrás traria etapas de 150 dias atrás e
    não testaria nada. O endpoint não recorta a saída por período (quem faz
    isso é o front), então basta ler todos os eventos do tipo."""
    eventos = c.get("/agenda/", params={"data": date.today().isoformat(), "dias": 400}).json()["eventos"]
    return [e for e in eventos if e.get("tipo") == "protocolo_iatf"]


class TestAgendaVoltaACobrarEtapaVencida:
    def test_etapa_vencida_dentro_da_janela_aparece(self, client):
        """Era ESTE o bug: D0/D7 de um protocolo lançado há 20 dias sumiam."""
        c, engine = client
        _animais(engine, ["700", "701"])
        _lancar_iatf(c, ["700", "701"], date.today() - timedelta(days=20))

        dias = {e["dia"] for e in _eventos_iatf(c)}
        assert 0 in dias, "D0 vencido sumiu da Agenda — o protocolo fica sem como fechar"
        assert 7 in dias, "D7 vencido sumiu da Agenda"

    def test_etapa_muito_antiga_nao_polui_a_agenda_para_sempre(self, client):
        c, engine = client
        _animais(engine, ["700"])
        _lancar_iatf(c, ["700"], date.today() - timedelta(days=JANELA_ATRASO_DIAS + 60))
        assert not _eventos_iatf(c), "lançamento abandonado não pode cobrar pendência eternamente"

    def test_etapa_futura_continua_aparecendo(self, client):
        c, engine = client
        _animais(engine, ["700"])
        _lancar_iatf(c, ["700"], date.today())
        assert {e["dia"] for e in _eventos_iatf(c)} == {0, 7, 9, 11}


class TestBaixaPelaCentral:
    def test_da_baixa_fora_da_janela_da_agenda(self, client):
        """O caso do usuário: protocolo velho, sem nada na Agenda, e ainda
        assim precisa ser possível fechá-lo."""
        c, engine = client
        _animais(engine, ["700", "701"])
        d0 = date.today() - timedelta(days=JANELA_ATRASO_DIAS + 40)
        lid = _lancar_iatf(c, ["700", "701"], d0)
        assert not _eventos_iatf(c), "pré-condição: nada na Agenda"

        r = c.post(f"/central-protocolos/iatf/{lid}/baixa", json={
            "dia": 0, "data_realizacao": (d0).isoformat(),
        })
        assert r.status_code == 200, r.text

        det = c.get(f"/central-protocolos/iatf/{lid}").json()
        assert det["etapas_realizadas"] == 2
        d0_linha = next(d for d in det["dias"] if d["dia"] == 0)
        assert d0_linha["realizadas"] == 2

    def test_grava_a_data_real_e_nao_hoje(self, client):
        """Aplicou no dia certo, registrou três semanas depois — o histórico
        tem que dizer o dia da aplicação, não o dia da digitação."""
        c, engine = client
        _animais(engine, ["700"])
        d0 = date.today() - timedelta(days=21)
        lid = _lancar_iatf(c, ["700"], d0)

        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={
            "dia": 0, "data_realizacao": d0.isoformat(),
        })
        with Session(engine) as s:
            ap = s.exec(select(ProtocoloIatfAplicacao).where(
                ProtocoloIatfAplicacao.lancamento_id == lid, ProtocoloIatfAplicacao.dia == 0,
            )).first()
            assert ap.data_realizacao == d0, f"carimbou {ap.data_realizacao} em vez de {d0}"

    def test_sem_data_assume_hoje(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = _lancar_iatf(c, ["700"], date.today())
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})
        with Session(engine) as s:
            ap = s.exec(select(ProtocoloIatfAplicacao).where(
                ProtocoloIatfAplicacao.lancamento_id == lid, ProtocoloIatfAplicacao.dia == 0,
            )).first()
            assert ap.data_realizacao == date.today()

    def test_baixa_so_de_alguns_animais(self, client):
        c, engine = client
        _animais(engine, ["700", "701", "702"])
        lid = _lancar_iatf(c, ["700", "701", "702"], date.today())
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0, "animais": ["700"]})

        det = c.get(f"/central-protocolos/iatf/{lid}").json()
        d0 = next(d for d in det["dias"] if d["dia"] == 0)
        assert (d0["realizadas"], d0["total"]) == (1, 3)

    def test_nao_vaza_para_outro_lote_com_o_mesmo_d0(self, client):
        """O evento IATF da Agenda é chaveado por (data, dia) — de propósito,
        para juntar lotes do mesmo dia. Pela Central, olhando UM lançamento,
        confirmar não pode arrastar o lote do vizinho."""
        c, engine = client
        _animais(engine, ["700", "800"])
        d0 = date.today()
        lid_a = _lancar_iatf(c, ["700"], d0)
        lid_b = _lancar_iatf(c, ["800"], d0)

        c.post(f"/central-protocolos/iatf/{lid_a}/baixa", json={"dia": 0})

        assert c.get(f"/central-protocolos/iatf/{lid_a}").json()["etapas_realizadas"] == 1
        assert c.get(f"/central-protocolos/iatf/{lid_b}").json()["etapas_realizadas"] == 0

    def test_data_no_futuro_e_recusada(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = _lancar_iatf(c, ["700"], date.today())
        r = c.post(f"/central-protocolos/iatf/{lid}/baixa", json={
            "dia": 0, "data_realizacao": (date.today() + timedelta(days=1)).isoformat(),
        })
        assert r.status_code == 400

    def test_sanitario_nao_aceita_baixa_pela_central(self, client):
        c, _ = client
        r = c.post("/central-protocolos/sanitario/1/baixa", json={"dia": 0})
        assert r.status_code == 400
        assert "sanitário" in r.json()["detail"].lower()

    def test_lancamento_inexistente_da_404(self, client):
        c, _ = client
        assert c.get("/central-protocolos/iatf/999999").status_code == 404
        assert c.post("/central-protocolos/iatf/999999/baixa", json={"dia": 0}).status_code == 404


class TestDetalheGradeAnimalPorDia:
    def test_grade_traz_uma_linha_por_animal_e_uma_celula_por_dia(self, client):
        c, engine = client
        _animais(engine, ["700", "701"])
        lid = _lancar_iatf(c, ["700", "701"], date.today())

        det = c.get(f"/central-protocolos/iatf/{lid}").json()
        assert [l["numero_matriz"] for l in det["animais"]] == ["700", "701"]
        assert [c_["rotulo"] for c_ in det["animais"][0]["celulas"]] == ["D0", "D7", "D9", "D11"]
        assert det["etapas_total"] == 8

    def test_estado_da_celula_distingue_atrasada_de_pendente(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = _lancar_iatf(c, ["700"], date.today() - timedelta(days=8))

        det = c.get(f"/central-protocolos/iatf/{lid}").json()
        estados = {c_["rotulo"]: c_["estado"] for c_ in det["animais"][0]["celulas"]}
        assert estados["D0"] == "atrasada"  # venceu há 8 dias
        assert estados["D7"] == "atrasada"  # venceu ontem
        assert estados["D11"] == "pendente"  # ainda vai vencer
        assert det["etapas_atrasadas"] == 2

    def test_celula_realizada_mostra_a_data_da_aplicacao(self, client):
        c, engine = client
        _animais(engine, ["700"])
        d0 = date.today() - timedelta(days=5)
        lid = _lancar_iatf(c, ["700"], d0)
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0, "data_realizacao": d0.isoformat()})

        det = c.get(f"/central-protocolos/iatf/{lid}").json()
        celula = next(c_ for c_ in det["animais"][0]["celulas"] if c_["rotulo"] == "D0")
        assert celula["estado"] == "realizada"
        assert celula["data_realizacao"] == d0.isoformat()


class TestEncerrar:
    def test_encerrar_nao_finge_que_as_etapas_foram_feitas(self, client):
        """A decisão explícita do produto: encerrar ≠ dar por feito."""
        c, engine = client
        _animais(engine, ["700", "701"])
        lid = _lancar_iatf(c, ["700", "701"], date.today())
        c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0})

        r = c.post(f"/central-protocolos/iatf/{lid}/encerrar", json={"motivo": "Lote vendido"})
        assert r.status_code == 200, r.text

        det = c.get(f"/central-protocolos/iatf/{lid}").json()
        assert (det["etapas_realizadas"], det["etapas_total"]) == (2, 8), "encerrar maquiou o progresso"
        assert det["encerrado_motivo"] == "Lote vendido"

    def test_encerrado_sai_do_acompanhamento_e_entra_no_historico(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = _lancar_iatf(c, ["700"], date.today())

        assert any(l["origem_id"] == lid for l in c.get("/central-protocolos/acompanhamento").json())
        c.post(f"/central-protocolos/iatf/{lid}/encerrar", json={"motivo": "Vaca morreu"})

        assert not any(l["origem_id"] == lid for l in c.get("/central-protocolos/acompanhamento").json())
        linha = next(l for l in c.get("/central-protocolos/historico").json() if l["origem_id"] == lid)
        assert linha["status"] == "encerrado"
        # 1 animal × 4 dias, nenhuma baixa: as 4 continuam contadas como
        # faltando. Encerrar não maquia o progresso.
        assert (linha["etapas_realizadas"], linha["etapas_faltam"]) == (0, 4)

    def test_encerrado_para_de_cobrar_pendencia_na_agenda(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = _lancar_iatf(c, ["700"], date.today())
        assert _eventos_iatf(c), "pré-condição: cobrando na Agenda"

        c.post(f"/central-protocolos/iatf/{lid}/encerrar", json={})
        assert not _eventos_iatf(c), "protocolo encerrado continua cobrando na Agenda"

    def test_encerrado_recusa_baixa_ate_ser_reaberto(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = _lancar_iatf(c, ["700"], date.today())
        c.post(f"/central-protocolos/iatf/{lid}/encerrar", json={})

        assert c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0}).status_code == 400

        assert c.delete(f"/central-protocolos/iatf/{lid}/encerrar").status_code == 200
        assert c.post(f"/central-protocolos/iatf/{lid}/baixa", json={"dia": 0}).status_code == 200
        with Session(engine) as s:
            assert s.get(ProtocoloIatfLancamento, lid).encerrado_em is None

    def test_motivo_em_branco_vira_nulo(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = _lancar_iatf(c, ["700"], date.today())
        c.post(f"/central-protocolos/iatf/{lid}/encerrar", json={"motivo": "   "})
        assert c.get(f"/central-protocolos/iatf/{lid}").json()["encerrado_motivo"] is None


class TestAsOutrasDuasFamilias:
    """A baixa pela Central vale para as três famílias com cabeçalho de lote,
    não só IATF — indução e customizado passam pelas mesmas rotas."""

    def _inducao(self, c, engine, d0: date) -> int:
        _animais(engine, ["700"])
        pid = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução padrão", "dia_inicial": 0,
            "etapas": [
                {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
                {"dia": 7, "tipo": "manejo", "produto": "Adaptação na ordenha"},
            ],
        }).json()["id"]
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid, "animais": ["700"], "data_d0": d0.isoformat(),
        })
        assert r.status_code == 201, r.text
        return next(
            l["origem_id"] for l in c.get("/central-protocolos/acompanhamento").json()
            if l["origem"] == "inducao"
        )

    def _customizado(self, c, engine, d0: date, animais: list[str]) -> int:
        criado = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Cura de casco", "categoria": "Rebanho", "dia_inicial": 0, "tipo": "sanitario",
            "etapas": [
                {"dia": 0, "descricao_evento": "Aplicar produto", "insumo_padrao": "Sulfato de cobre"},
                {"dia": 3, "descricao_evento": "Reavaliar casco"},
            ],
        }).json()
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": animais, "data_inicio": d0.isoformat(),
        })
        assert r.status_code == 201, r.text
        return next(
            l["origem_id"] for l in c.get("/central-protocolos/acompanhamento").json()
            if l["origem"] == "customizado"
        )

    def test_inducao_da_baixa_com_data_real(self, client):
        c, engine = client
        d0 = date.today() - timedelta(days=15)
        lid = self._inducao(c, engine, d0)

        r = c.post(f"/central-protocolos/inducao/{lid}/baixa", json={
            "dia": 0, "data_realizacao": d0.isoformat(),
        })
        assert r.status_code == 200, r.text
        det = c.get(f"/central-protocolos/inducao/{lid}").json()
        celula = next(x for x in det["animais"][0]["celulas"] if x["dia"] == 0)
        assert celula["realizada"] and celula["data_realizacao"] == d0.isoformat()

    def test_customizado_da_baixa_e_encerra(self, client):
        c, engine = client
        _animais(engine, ["700", "701"])
        d0 = date.today() - timedelta(days=10)
        lid = self._customizado(c, engine, d0, ["700", "701"])

        assert c.post(f"/central-protocolos/customizado/{lid}/baixa", json={
            "dia": 0, "animais": ["700"], "data_realizacao": d0.isoformat(),
        }).status_code == 200

        det = c.get(f"/central-protocolos/customizado/{lid}").json()
        assert (det["etapas_realizadas"], det["etapas_total"]) == (1, 4)

        assert c.post(f"/central-protocolos/customizado/{lid}/encerrar", json={"motivo": "Casco curou"}).status_code == 200
        linha = next(l for l in c.get("/central-protocolos/historico").json() if l["origem"] == "customizado")
        assert linha["status"] == "encerrado" and linha["etapas_faltam"] == 3

    def test_customizado_encerrado_sai_da_agenda(self, client):
        c, engine = client
        _animais(engine, ["700"])
        lid = self._customizado(c, engine, date.today(), ["700"])

        def _eventos():
            ev = c.get("/agenda/", params={"data": date.today().isoformat(), "dias": 400}).json()["eventos"]
            return [e for e in ev if e.get("tipo") == "protocolo_customizado"]

        assert _eventos(), "pré-condição: cobrando na Agenda"
        c.post(f"/central-protocolos/customizado/{lid}/encerrar", json={})
        assert not _eventos()

    def test_tarefa_da_fazenda_sem_animal_nao_quebra_a_grade(self, client):
        """Customizado aceita lançamento sem animal (tarefa da fazenda) — a
        grade não pode explodir por causa do numero_matriz nulo."""
        c, engine = client
        lid = self._customizado(c, engine, date.today(), [])
        det = c.get(f"/central-protocolos/customizado/{lid}").json()
        assert [a["numero_matriz"] for a in det["animais"]] == ["—"]
        assert c.post(f"/central-protocolos/customizado/{lid}/baixa", json={"dia": 0}).status_code == 200


class TestNadaQuebrouNoCaminhoAntigo:
    def test_baixa_pela_agenda_continua_funcionando(self, client):
        c, engine = client
        _animais(engine, ["700", "701"])
        lid = _lancar_iatf(c, ["700", "701"], date.today())
        evento = next(e for e in _eventos_iatf(c) if e["dia"] == 0)

        assert c.post("/agenda/realizados", json={"evento_id": evento["id"]}).status_code == 200
        assert c.get(f"/central-protocolos/iatf/{lid}").json()["etapas_realizadas"] == 2

    def test_agenda_ainda_junta_lotes_do_mesmo_d0_num_evento_so(self, client):
        """O agrupamento por (data, dia) é proposital e não pode ter sido
        desfeito pelo filtro novo de lançamento."""
        c, engine = client
        _animais(engine, ["700", "800"])
        _lancar_iatf(c, ["700"], date.today())
        _lancar_iatf(c, ["800"], date.today())

        d0 = [e for e in _eventos_iatf(c) if e["dia"] == 0]
        assert len(d0) == 1, "um card por dia, com os dois lotes juntos"
        assert sorted(d0[0]["animais"]) == ["700", "800"]
