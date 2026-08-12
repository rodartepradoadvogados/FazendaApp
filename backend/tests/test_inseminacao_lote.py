"""
Inseminação em lote: vários animais de uma vez, tipo cio natural / IATF /
monta natural, touro por categoria de sêmen e estoque mínimo por categoria.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, EstoqueSemen, MovimentoEstoque, ProtocoloIatfAplicacao, ProtocoloIatfLancamento, Servico


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for n in ["700", "701", "702"]:
            s.add(Animal(numero=n, sit_rep="Vaz. apt.", ativo=True))
        s.add(EstoqueSemen(touro_nome="Hagen", tipo="sexado", doses=3))
        s.add(EstoqueSemen(touro_nome="Coors", tipo="convencional", doses=30))
        s.add(EstoqueSemen(touro_nome="Frederico", tipo="fazenda", doses=0))
        s.commit()

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
        permissoes = "reproducao,financeiro,sanidade"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestServicoLote:
    def test_cio_natural_varios_animais(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700", "701"], "data_servico": "2026-07-08", "tipo": "cio_natural", "reprodutor": "Coors",
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 2
        with Session(engine) as s:
            servs = s.exec(select(Servico)).all()
            assert len(servs) == 2
            assert all(sv.tipo_servico == "IA" and sv.protocolo is None for sv in servs)

    def test_monta_natural(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-08", "tipo": "monta_natural", "reprodutor": "Frederico",
        })
        assert r.status_code == 200
        with Session(engine) as s:
            sv = s.exec(select(Servico)).first()
            assert sv.tipo_servico == "Monta natural"

    def test_iatf_sem_protocolo_vai_para_incompativeis(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-08", "tipo": "iatf", "reprodutor": "Coors",
        })
        assert r.status_code == 200
        assert r.json()["incompativeis"] == ["700"]
        assert r.json()["criados"] == 0

    def test_iatf_auto_lanca_protocolo_retroativo(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-12", "tipo": "iatf",
            "reprodutor": "Coors", "auto_lancar_iatf": True,
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 1 and r.json()["incompativeis"] == []
        with Session(engine) as s:
            lanc = s.exec(select(ProtocoloIatfLancamento)).first()
            # D0 = serviço − 11 dias, marcado como retroativo.
            assert lanc.data_d0 == date(2026, 7, 12) - timedelta(days=11)
            assert lanc.retroativo is True
            # D11 resolvido pela inseminação (data = serviço).
            d11 = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 11)).first()
            assert d11.realizada is True

    def test_etapas_retroativas_aparecem_como_pendencia_na_agenda(self, client):
        c, engine = client
        c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-12", "tipo": "iatf",
            "reprodutor": "Coors", "auto_lancar_iatf": True,
        })
        # Consulta a agenda numa data DEPOIS de todas as etapas retroativas —
        # num protocolo normal elas ficariam escondidas; retroativo mostra.
        eventos = c.get("/agenda/", params={"data": "2026-07-13", "dias": 30}).json()["eventos"]
        iatf = [e for e in eventos if e.get("tipo") == "protocolo_iatf"]
        dias = sorted(e["dia"] for e in iatf)
        assert dias == [0, 7, 9]  # D0/D7/D9 vencidos aparecem; D11 já foi resolvido


class TestIatfNaoAbsorveAnimalDeOutroLancamento:
    """Reproduz o diagnóstico "lista de IATF com mais animais do que o
    implantado": confirmar uma inseminação com tipo=iatf vinculada a um
    lançamento (protocolo_lancamento_id) para um animal que NUNCA passou pelo
    D0 daquele lançamento não pode fabricar um histórico D0-D11 retroativo
    para ela — tem que cair em incompatíveis, como quando não há protocolo
    algum."""

    def test_animal_fora_do_lancamento_vai_para_incompativeis_nao_e_absorvido(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-07-03"})
        assert r.status_code == 200
        lancamento_id = r.json()["lancamento_id"]

        # 701 nunca entrou nesse lançamento — confirmar a inseminação dela
        # vinculada a ele não pode criar D0-D11 fantasma.
        r2 = c.post("/reproducao/servico-lote", json={
            "animais": ["700", "701"], "data_servico": "2026-07-14", "tipo": "iatf",
            "reprodutor": "Coors", "protocolo_lancamento_id": lancamento_id,
        })
        assert r2.status_code == 200
        assert r2.json()["incompativeis"] == ["701"]
        assert r2.json()["criados"] == 1

        with Session(engine) as s:
            aps_701 = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "701")).all()
            assert aps_701 == []  # nenhuma etapa fabricada para ela
            servicos_701 = s.exec(select(Servico).where(Servico.numero_matriz == "701")).all()
            assert servicos_701 == []  # nem o próprio serviço, já que ficou incompatível

    def test_animal_de_fato_no_lancamento_confirma_normalmente(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700", "701"], "data_d0": "2026-07-03"})
        lancamento_id = r.json()["lancamento_id"]

        r2 = c.post("/reproducao/servico-lote", json={
            "animais": ["700", "701"], "data_servico": "2026-07-14", "tipo": "iatf",
            "reprodutor": "Coors", "protocolo_lancamento_id": lancamento_id,
        })
        assert r2.json()["criados"] == 2 and r2.json()["incompativeis"] == []
        with Session(engine) as s:
            d11s = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 11)).all()
            assert all(d.realizada for d in d11s)


class TestD0ConfirmadoNaListaAtivos:
    def test_d0_confirmado_falso_ate_marcar_realizado_na_agenda(self, client):
        # D0 fixo em "2026-07-03" era uma bomba-relógio: `GET
        # /protocolo-iatf/ativos` (fazenda/api/routers/reproducao.py) só
        # lista um protocolo com D0 tão velho enquanto `date.today()` REAL
        # ainda estiver dentro da janela de graça — GRACA_D11_ATRASADO_DIAS
        # (7 dias após o D11 previsto) some soma outros +7 dias após
        # `proxima_visita` antes de sumir de vez da lista (ver comentário
        # acima de `listar_protocolos_iatf_ativos`). Passados esses dias —
        # o caso de "2026-07-03" a partir de meados de agosto/2026 — o
        # protocolo simplesmente não aparece mais em `ativos`, e o
        # `next(...)` do teste estoura `StopIteration`. O comportamento de
        # produção está certo (protocolo abandonado há muito tempo
        # realmente deve sumir da lista); o teste é quem fixou uma data que
        # teria que ser eternamente "recente". Usa D0 = hoje (protocolo
        # recém-lançado, ainda dentro de toda janela por dezenas de dias),
        # que é também o cenário que o nome do teste descreve.
        c, engine = client
        hoje = date.today()
        c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": hoje.isoformat()})

        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        animal = next(a for g in ativos for a in g["animais"] if a["numero_matriz"] == "700")
        assert animal["d0_confirmado"] is False

        # evento_id da Agenda é chaveado por (data prevista, dia), não mais
        # por lancamento_id — ver comentário em calcular_agenda.
        c.post("/agenda/realizados", json={"evento_id": f"protocolo_iatf_{hoje.isoformat()}_0"})
        ativos2 = c.get("/reproducao/protocolo-iatf/ativos").json()
        animal2 = next(a for g in ativos2 for a in g["animais"] if a["numero_matriz"] == "700")
        assert animal2["d0_confirmado"] is True


class TestRemoverAnimalIatf:
    def test_remove_animal_ainda_nao_confirmado(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700", "701"], "data_d0": "2026-07-03"})
        lancamento_id = r.json()["lancamento_id"]

        rd = c.delete(f"/reproducao/protocolo-iatf/{lancamento_id}/animais/701")
        assert rd.status_code == 200
        with Session(engine) as s:
            restantes = {a.numero_matriz for a in s.exec(select(ProtocoloIatfAplicacao)).all()}
            assert restantes == {"700"}

    def test_bloqueia_remocao_se_ja_confirmado(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-07-03"})
        lancamento_id = r.json()["lancamento_id"]
        # evento_id da Agenda é chaveado por (data prevista, dia), não mais
        # por lancamento_id — ver comentário em calcular_agenda.
        c.post("/agenda/realizados", json={"evento_id": "protocolo_iatf_2026-07-03_0"})

        rd = c.delete(f"/reproducao/protocolo-iatf/{lancamento_id}/animais/700")
        assert rd.status_code == 409
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "700")).all()) == 4

    def test_404_animal_fora_do_lancamento(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-07-03"})
        lancamento_id = r.json()["lancamento_id"]
        rd = c.delete(f"/reproducao/protocolo-iatf/{lancamento_id}/animais/999")
        assert rd.status_code == 404

    def test_404_lancamento_inexistente(self, client):
        c, engine = client
        rd = c.delete("/reproducao/protocolo-iatf/99999/animais/700")
        assert rd.status_code == 404


class TestDescontoDoseSemen:
    def test_ia_cio_natural_desconta_uma_dose_por_animal(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700", "701"], "data_servico": "2026-07-08", "tipo": "cio_natural", "reprodutor": "Coors",
        })
        assert r.json()["criados"] == 2
        with Session(engine) as s:
            coors = s.exec(select(EstoqueSemen).where(EstoqueSemen.touro_nome == "Coors")).first()
            assert coors.doses == 28  # 30 - 2

    def test_monta_natural_nao_desconta_dose(self, client):
        c, engine = client
        c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-08", "tipo": "monta_natural", "reprodutor": "Frederico",
        })
        with Session(engine) as s:
            frederico = s.exec(select(EstoqueSemen).where(EstoqueSemen.touro_nome == "Frederico")).first()
            assert frederico.doses == 0

    def test_reprodutor_sem_touro_cadastrado_nao_quebra(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-08", "tipo": "cio_natural", "reprodutor": "Touro Fantasma",
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 1

    def test_desconto_grava_movimento_de_estoque(self, client):
        # Antes, _baixar_dose_semen descontava EstoqueSemen.doses sem gravar
        # MovimentoEstoque nenhum — a baixa não deixava rastro (ver auditoria).
        c, engine = client
        r = c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": "2026-07-08", "tipo_servico": "IA", "reprodutor": "Coors",
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.nome_item == "Coors")).first()
            assert mov is not None
            assert mov.quantidade == 1
            assert mov.origem_tipo == "ia_semen"


class TestProtocoloVigenteParaInseminacao:
    """"Protocolo de IATF atual" (sub-aba Inseminação) tem que mostrar a
    matriz enquanto o protocolo estiver vigente — nenhum Serviço lançado
    depois do D0 — não importa em qual etapa do hormônio ela está hoje. A
    inseminação pode ser lançada bem depois de o hormônio ter sido aplicado
    (a posteriori)."""

    def _animal(self, ativos, numero):
        return next(a for g in ativos for a in g["animais"] if a["numero_matriz"] == numero)

    def test_pronta_para_inseminar_mesmo_ainda_no_d0_sem_servico(self, client):
        c, engine = client
        hoje = date.today().isoformat()
        c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": hoje})

        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        animal = self._animal(ativos, "700")
        # Ainda em D0 (não é a etapa de inseminação) — mas sem serviço nenhum
        # lançado, o protocolo continua vigente e a matriz tem que aparecer.
        assert animal["etapa_atual"] == "D0"
        assert animal["pronta_para_inseminar"] is True

    def test_deixa_de_estar_pronta_apos_lancar_servico_no_ciclo(self, client):
        c, engine = client
        hoje = date.today()
        c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": hoje.isoformat()})
        c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": (hoje + timedelta(days=11)).isoformat(),
            "tipo_servico": "IA", "reprodutor": "Coors",
        })

        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        animal = self._animal(ativos, "700")
        assert animal["pronta_para_inseminar"] is False

    def test_protocolo_concluido_pronta_para_inseminar_ate_ter_servico(self, client):
        c, engine = client
        c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-07-03"})
        for evento_id in [
            "protocolo_iatf_2026-07-03_0", "protocolo_iatf_2026-07-10_7",
            "protocolo_iatf_2026-07-12_9", "protocolo_iatf_2026-07-14_11",
        ]:
            r = c.post("/agenda/realizados", json={"evento_id": evento_id})
            assert r.status_code == 200, r.text

        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        grupo = next(g for g in ativos if any(a["numero_matriz"] == "700" for a in g["animais"]))
        assert grupo["concluido"] is True
        animal = self._animal(ativos, "700")
        assert animal["etapa_atual"] == "Concluído"
        # Hormônio todo aplicado, mas ninguém lançou a inseminação ainda —
        # continua "pronta", que é justamente o caso que a Central de
        # Protocolos confirmar sozinha (sem passar pela tela de Inseminação)
        # deixava invisível antes desta correção.
        assert animal["pronta_para_inseminar"] is True

        c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": "2026-07-15", "tipo_servico": "IA", "reprodutor": "Coors",
        })
        ativos2 = c.get("/reproducao/protocolo-iatf/ativos").json()
        animal2 = self._animal(ativos2, "700")
        assert animal2["pronta_para_inseminar"] is False


class TestSemenDisponivel:
    def test_categorias_e_minimo(self, client):
        c, engine = client
        d = c.get("/cadastro/estoque-semen/disponivel").json()
        nomes = {t["nome"]: t for t in d["touros"]}
        # Frederico (fazenda) sempre aparece mesmo com 0 dose; Coors/Hagen têm dose.
        assert "Frederico" in nomes and nomes["Frederico"]["tipo"] == "fazenda"
        assert "Coors" in nomes and "Hagen" in nomes
        # Sexado: 3 doses < mínimo 5 → abaixo. Convencional: 30 ≥ 20 → ok.
        assert d["abaixo_minimo"]["sexado"] is True
        assert d["abaixo_minimo"]["convencional"] is False

    def test_alerta_semen_na_agenda(self, client):
        c, engine = client
        eventos = c.get("/agenda/", params={"data": "2026-07-12", "dias": 30}).json()["eventos"]
        semen_baixo = [e for e in eventos if e.get("tipo") == "semen_minimo"]
        assert any("sexado" in e["descricao"] for e in semen_baixo)
