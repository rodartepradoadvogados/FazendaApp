"""
Ciclo de vida ponta a ponta das 5 famílias de protocolo — IATF, Indução de
Lactação, Sanitário, Customizado e Lida — todas seguindo o mesmo padrão de 4
camadas (molde -> etapa -> lançamento -> aplicação), agregadas pela Central de
Protocolos (fazenda/api/routers/central_protocolos.py) e visíveis na Agenda
enquanto pendentes (fazenda/api/routers/agenda.py + fazenda/rules/lida.py,
protocolo_customizado.py, protocolo_iatf.py).

Eixos cobertos (ver auditoria):
  1. Contagem de etapas (N moldes x M animais, baixa parcial).
  2. Derivação de status (ativo/concluido/encerrado/cancelado) — sempre
     calculada, nunca gravada (ver `_linha` em central_protocolos.py).
  3. Concordância Agenda <-> Central (mesma pendência dos dois lados; baixa
     por um lado reflete no outro; janela de 30 dias).
  4. Lançamento retroativo (D0 no passado).
  5. Cronogramas não clássicos: IATF de dias livres, Lida periodo/frequencia,
     Customizado com dia_inicial=1.
  6. Bordas: sem animal, molde sem etapa, dia inexistente, dupla baixa,
     encerrar/reabrir/cancelar repetidos, data de realização futura.

Bugs CONFIRMADOS em arquivos fora do meu escopo de correção (ver
`_ORIGENS_COM_ACAO`/`cancelar`/`dar_baixa` em central_protocolos.py, e
`/producao/inducao-lactacao/ativos` em producao.py) ficam cobertos por testes
`xfail` — eles documentam o comportamento CORRETO esperado, hoje falhando,
sem derrubar a suíte (ver resumo da tarefa para os detalhes).

Segue o padrão de fixture de test_central_protocolos.py: sem overridar
`get_fazenda_atual_id`, fazenda_id fica None em toda a fixture (token
legado) — nenhuma linha de ContratoFazenda é necessária (o middleware de
contrato só gateia quando fazenda_id resolve para um int real).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.models  # noqa: F401 — força o registro de todas as tabelas antes do create_all() do fixture
from fazenda.models import (
    Estoque,
    LidaAplicacao, LidaLancamento,
    ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento,
    ProtocoloIatfAplicacao, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
)
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento, nome_curto
from fazenda.rules.protocolo_iatf import DIA_INSEMINACAO_PADRAO, dia_inseminacao


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


HOJE = date.today()


# ─────────────────────────────── Helpers de lançamento ───────────────────────

def _d(dias_atras: int = 0) -> str:
    return (HOJE - timedelta(days=dias_atras)).isoformat()


def cadastrar_molde_iatf(c, nome, dias, produto="Sincrodiol"):
    etapas = [{"dia": d, "produto": produto, "dose": 2.0, "unidade": "ml", "via": "Intramuscular"} for d in dias]
    r = c.post("/cadastro/protocolos-iatf", json={"nome": nome, "etapas": etapas})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def lancar_iatf(c, animais, data_d0, protocolo_id=None, hormonios=None):
    payload = {"animais": animais, "data_d0": data_d0}
    if protocolo_id is not None:
        payload["protocolo_id"] = protocolo_id
    if hormonios is not None:
        payload["hormonios"] = hormonios
    r = c.post("/reproducao/protocolo-iatf", json=payload)
    return r


def cadastrar_molde_inducao(c, nome, etapas):
    r = c.post("/cadastro/protocolos-inducao-lactacao", json={"nome": nome, "etapas": etapas})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def lancar_inducao(c, protocolo_id, animais, data_d0):
    r = c.post("/producao/inducao-lactacao", json={
        "protocolo_id": protocolo_id, "animais": animais, "data_d0": data_d0,
    })
    return r


def cadastrar_molde_customizado(c, nome, etapas, tipo="sanitario", categoria="Rebanho", dia_inicial=0):
    r = c.post("/cadastro/protocolos-customizados", json={
        "nome": nome, "categoria": categoria, "tipo": tipo, "dia_inicial": dia_inicial, "etapas": etapas,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def lancar_customizado(c, protocolo_id, animais, data_inicio):
    r = c.post("/protocolos-customizados/lancar", json={
        "protocolo_id": protocolo_id, "animais": animais, "data_inicio": data_inicio,
    })
    return r


def cadastrar_lida_frequencia(c, nome, frequencia_dias, dar_baixa=False, **kw):
    payload = {
        "nome": nome, "modo": "frequencia", "frequencia_dias": frequencia_dias,
        "descricao_evento": kw.get("descricao_evento", "Executar lida"),
        "dar_baixa_estoque": dar_baixa,
    }
    if dar_baixa:
        payload["insumo_padrao"] = kw.get("insumo_padrao")
        payload["insumo_dose"] = kw.get("insumo_dose")
        payload["insumo_unidade"] = kw.get("insumo_unidade")
    r = c.post("/cadastro/lidas", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def cadastrar_lida_periodo(c, nome, etapas, dia_inicial=0):
    r = c.post("/cadastro/lidas", json={"nome": nome, "modo": "periodo", "dia_inicial": dia_inicial, "etapas": etapas})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def lancar_lida(c, lida_id, data_inicio, data_fim=None, animais=None):
    payload = {"lida_id": lida_id, "data_inicio": data_inicio}
    if data_fim is not None:
        payload["data_fim"] = data_fim
    if animais is not None:
        payload["animais"] = animais
    r = c.post("/lida/lancar", json=payload)
    return r


def marcar_tudo_realizado(engine, modelo, lancamento_id):
    """Atalho para simular "todas as etapas confirmadas" sem passar pelo fluxo
    de confirmação da Agenda/Central (que já tem cobertura própria) — mesmo
    artifício de test_central_protocolos.py::test_iatf_concluido_..."""
    with Session(engine) as s:
        aps = s.exec(select(modelo).where(modelo.lancamento_id == lancamento_id)).all()
        for a in aps:
            a.realizada = True
            a.data_realizacao = a.data_prevista
            s.add(a)
        s.commit()


def linha_de(c, origem, origem_id, aba="acompanhamento"):
    linhas = c.get(f"/central-protocolos/{aba}").json()
    return next((l for l in linhas if l["origem"] == origem and l["origem_id"] == origem_id), None)


# ═══════════════════════════ 1. Contagem de etapas ═══════════════════════════

class TestContagemEtapas:
    def test_iatf_classico_n_etapas_x_m_animais(self, client):
        c, engine = client
        # Ad-hoc (sem molde) usa o cronograma clássico D0/D7/D9/D11 — 4 etapas.
        r = lancar_iatf(c, ["101", "102", "103"], _d(0))
        assert r.status_code == 200, r.text
        lancamento_id = r.json()["lancamento_id"]
        linha = linha_de(c, "iatf", lancamento_id)
        assert linha["etapas_total"] == 4 * 3
        assert linha["etapas_realizadas"] == 0
        assert linha["animais"] == 3

    def test_iatf_baixa_parcial_atualiza_contagem(self, client):
        c, engine = client
        r = lancar_iatf(c, ["101", "102", "103"], _d(0))
        lancamento_id = r.json()["lancamento_id"]

        # Baixa só 1 dos 3 animais no D0.
        rb = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0, "animais": ["101"]})
        assert rb.status_code == 200, rb.text
        linha = linha_de(c, "iatf", lancamento_id)
        assert linha["etapas_realizadas"] == 1
        assert linha["etapas_faltam"] == 11

        # Completa o D0 com os outros 2.
        c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0})
        linha = linha_de(c, "iatf", lancamento_id)
        assert linha["etapas_realizadas"] == 3

    def test_customizado_n_etapas_x_m_animais(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Cura de casco N", [
            {"dia": 0, "descricao_evento": "Aplicar"},
            {"dia": 3, "descricao_evento": "Reaplicar"},
            {"dia": 6, "descricao_evento": "Conferir cura"},
        ])
        r = lancar_customizado(c, pid, ["201", "202", "203", "204"], _d(0))
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]
        linha = linha_de(c, "customizado", lancamento_id)
        assert linha["etapas_total"] == 3 * 4
        assert linha["animais"] == 4

    def test_customizado_baixa_parcial_no_dia(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Cura de casco P", [
            {"dia": 0, "descricao_evento": "Aplicar"}, {"dia": 3, "descricao_evento": "Reaplicar"},
        ])
        r = lancar_customizado(c, pid, ["301", "302", "303", "304"], _d(0))
        lancamento_id = r.json()["lancamento_id"]

        c.post(f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 3, "animais": ["301", "302"]})
        linha = linha_de(c, "customizado", lancamento_id)
        assert linha["etapas_realizadas"] == 2
        assert linha["etapas_faltam"] == 6

        c.post(f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 3})
        linha = linha_de(c, "customizado", lancamento_id)
        assert linha["etapas_realizadas"] == 4

    def test_lida_frequencia_n_ocorrencias_x_m_animais(self, client):
        c, engine = client
        lid = cadastrar_lida_frequencia(c, "Verificar cerca", 10)
        r = lancar_lida(c, lid, _d(0), data_fim=(HOJE + timedelta(days=30)).isoformat(), animais=["401", "402"])
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]
        # dias 0/10/20/30 -> 4 ocorrências x 2 animais = 8.
        linha = linha_de(c, "lida", lancamento_id)
        assert linha["etapas_total"] == 8
        assert linha["animais"] == 2

    def test_lida_periodo_dia_fim_conta_n_dias_x_m_animais(self, client):
        c, engine = client
        lid = cadastrar_lida_periodo(c, "Obra da cerca N", [
            {"dia_inicio": 0, "dia_fim": 4, "descricao_evento": "Enviar foto"},
        ])
        r = lancar_lida(c, lid, _d(0), animais=["501", "502", "503"])
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]
        # D0..D4 (5 dias) x 3 animais = 15.
        linha = linha_de(c, "lida", lancamento_id)
        assert linha["etapas_total"] == 15
        assert linha["animais"] == 3

    def test_inducao_n_etapas_x_m_animais(self, client):
        c, engine = client
        pid = cadastrar_molde_inducao(c, "Indução N", [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
            {"dia": 10, "tipo": "manejo", "produto": "Adaptar ordenha"},
        ])
        r = lancar_inducao(c, pid, ["601", "602"], _d(0))
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]
        linha = linha_de(c, "inducao", lancamento_id)
        assert linha["etapas_total"] == 2 * 2
        assert linha["animais"] == 2


# ══════════════════════════ 2. Derivação de status ═══════════════════════════

class TestDerivacaoStatus:
    def test_iatf_concluido_sai_do_acompanhamento_entra_no_historico(self, client):
        c, engine = client
        r = lancar_iatf(c, ["701"], _d(60))  # bem no passado — nada de janela aqui, ação é direta no banco
        lancamento_id = r.json()["lancamento_id"]
        marcar_tudo_realizado(engine, ProtocoloIatfAplicacao, lancamento_id)

        assert linha_de(c, "iatf", lancamento_id, "acompanhamento") is None
        historico = linha_de(c, "iatf", lancamento_id, "historico")
        assert historico is not None and historico["status"] == "concluido"

    def test_encerrar_no_meio_nao_maquia_o_progresso(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo longo", [
            {"dia": d, "descricao_evento": "Etapa"} for d in range(0, 12, 3)  # 4 dias x 3 animais = 12 etapas
        ])
        r = lancar_customizado(c, pid, ["801", "802", "803"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 0, "animais": ["801", "802"]})

        linha_antes = linha_de(c, "customizado", lancamento_id)
        assert linha_antes["etapas_realizadas"] == 2
        assert linha_antes["etapas_total"] == 12
        assert linha_antes["status"] == "ativo"

        re = c.post(f"/central-protocolos/customizado/{lancamento_id}/encerrar", json={"motivo": "Fim do lote"})
        assert re.status_code == 200, re.text

        assert linha_de(c, "customizado", lancamento_id, "acompanhamento") is None
        linha_depois = linha_de(c, "customizado", lancamento_id, "historico")
        assert linha_depois["status"] == "encerrado"
        # 2 de 12 continua 2 de 12 — encerrar não é dar por feito o que não foi.
        assert linha_depois["etapas_realizadas"] == 2
        assert linha_depois["etapas_total"] == 12
        assert linha_depois["etapas_faltam"] == 10

    def test_cancelado_desfaz_aplicacoes_realizadas(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo a cancelar", [
            {"dia": 0, "descricao_evento": "Etapa 1"}, {"dia": 3, "descricao_evento": "Etapa 2"},
        ])
        r = lancar_customizado(c, pid, ["901", "902"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 0})

        rc = c.post(f"/central-protocolos/customizado/{lancamento_id}/cancelar", json={"motivo": "Erro de lançamento"})
        assert rc.status_code == 200, rc.text

        linha = linha_de(c, "customizado", lancamento_id, "historico")
        assert linha["status"] == "cancelado"
        with Session(engine) as s:
            aps = s.exec(
                select(ProtocoloCustomizadoAplicacao).where(ProtocoloCustomizadoAplicacao.lancamento_id == lancamento_id)
            ).all()
            assert all(not a.realizada and a.data_realizacao is None for a in aps)

    def test_reabrir_desfaz_encerramento_volta_a_cobrar_pendencia(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo a reabrir", [{"dia": 0, "descricao_evento": "Etapa"}])
        r = lancar_customizado(c, pid, ["950"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/customizado/{lancamento_id}/encerrar", json={})
        assert linha_de(c, "customizado", lancamento_id, "acompanhamento") is None

        rr = c.request("DELETE", f"/central-protocolos/customizado/{lancamento_id}/encerrar")
        assert rr.status_code == 200, rr.text

        linha = linha_de(c, "customizado", lancamento_id, "acompanhamento")
        assert linha is not None and linha["status"] == "ativo"
        det = c.get(f"/central-protocolos/customizado/{lancamento_id}").json()
        assert det["encerrado_em"] is None

    def test_reabrir_apos_cancelar_nao_reativa_o_lancamento(self, client):
        # Comportamento documentado, não um bug: `cancelar` marca `ativo=False`,
        # e `reabrir` só desfaz `encerrado_em`/`encerrado_motivo` — não existe
        # endpoint de "descancelar". Um lançamento cancelado continua
        # "cancelado" mesmo depois de DELETE .../encerrar.
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo cancelado e reaberto", [{"dia": 0, "descricao_evento": "Etapa"}])
        r = lancar_customizado(c, pid, ["960"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/customizado/{lancamento_id}/cancelar", json={"motivo": "x"})

        rr = c.request("DELETE", f"/central-protocolos/customizado/{lancamento_id}/encerrar")
        assert rr.status_code == 200, rr.text

        assert linha_de(c, "customizado", lancamento_id, "acompanhamento") is None
        linha = linha_de(c, "customizado", lancamento_id, "historico")
        assert linha["status"] == "cancelado"

    def test_lida_ciclo_completo_de_status(self, client):
        c, engine = client
        lid = cadastrar_lida_frequencia(c, "Lida ciclo completo", 5)
        r = lancar_lida(c, lid, _d(0), data_fim=(HOJE + timedelta(days=10)).isoformat())
        lancamento_id = r.json()["lancamento_id"]
        assert linha_de(c, "lida", lancamento_id)["status"] == "ativo"

        marcar_tudo_realizado(engine, LidaAplicacao, lancamento_id)
        assert linha_de(c, "lida", lancamento_id, "acompanhamento") is None
        assert linha_de(c, "lida", lancamento_id, "historico")["status"] == "concluido"

    def test_inducao_ciclo_completo_de_status(self, client):
        c, engine = client
        pid = cadastrar_molde_inducao(c, "Indução ciclo completo", [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato", "dose": 1, "unidade": "ml"},
        ])
        r = lancar_inducao(c, pid, ["970"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        assert linha_de(c, "inducao", lancamento_id)["status"] == "ativo"

        re = c.post(f"/central-protocolos/inducao/{lancamento_id}/encerrar", json={"motivo": "Descartada"})
        assert re.status_code == 200, re.text
        assert linha_de(c, "inducao", lancamento_id, "historico")["status"] == "encerrado"


# ═════════════════════ 3. Agenda <-> Central concordam ═══════════════════════

class TestAgendaCentralConcordam:
    def _tem_evento(self, c, tipo, data=None):
        ag = c.get("/agenda/", params={"data": data or HOJE.isoformat()}).json()
        return [e for e in ag["eventos"] if e.get("tipo") == tipo]

    def test_customizado_pendente_aparece_na_agenda_e_no_acompanhamento(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Vacina do rebanho", [{"dia": 0, "descricao_evento": "Aplicar vacina"}])
        r = lancar_customizado(c, pid, ["111"], _d(0))
        lancamento_id = r.json()["lancamento_id"]

        eventos = self._tem_evento(c, "protocolo_customizado")
        assert any(e["protocolo"] == "VACINA DO REBANHO" or "VACINA DO REBANHO" in e["protocolo"] for e in eventos)
        assert linha_de(c, "customizado", lancamento_id)["status"] == "ativo"

    def test_baixa_pela_central_some_da_agenda(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Cura de casco central", [{"dia": 0, "descricao_evento": "Aplicar"}])
        r = lancar_customizado(c, pid, ["112"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        assert len(self._tem_evento(c, "protocolo_customizado")) == 1

        rb = c.post(f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 0})
        assert rb.status_code == 200, rb.text

        assert self._tem_evento(c, "protocolo_customizado") == []

    def test_baixa_pela_agenda_reflete_no_progresso_da_central(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Cura de casco agenda", [{"dia": 0, "descricao_evento": "Aplicar"}])
        r = lancar_customizado(c, pid, ["113"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        eventos = self._tem_evento(c, "protocolo_customizado")
        evento_id = eventos[0]["id"]

        rm = c.post("/agenda/realizados", json={"evento_id": evento_id})
        assert rm.status_code == 200, rm.text

        linha = linha_de(c, "customizado", lancamento_id, "historico")
        assert linha["status"] == "concluido"
        assert linha["etapas_realizadas"] == 1

    def test_baixa_pela_agenda_iatf_reflete_no_progresso_da_central(self, client):
        c, engine = client
        r = lancar_iatf(c, ["114"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        eventos = self._tem_evento(c, "protocolo_iatf")
        evento_d0 = next(e for e in eventos if e["dia"] == 0)

        c.post("/agenda/realizados", json={"evento_id": evento_d0["id"]})
        linha = linha_de(c, "iatf", lancamento_id)
        assert linha["etapas_realizadas"] == 1

    def test_etapa_fora_da_janela_some_da_agenda_mas_continua_baixavel_pela_central(self, client):
        # Documentado em protocolo_customizado.JANELA_ATRASO_DIAS (30): passada
        # a janela a etapa some da Agenda, mas a Central continua fechando o
        # ciclo (senão o lançamento fica travado para sempre).
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo esquecido", [{"dia": 0, "descricao_evento": "Aplicar"}])
        r = lancar_customizado(c, pid, ["115"], _d(45))
        lancamento_id = r.json()["lancamento_id"]

        assert self._tem_evento(c, "protocolo_customizado") == []
        linha = linha_de(c, "customizado", lancamento_id)
        assert linha is not None and linha["status"] == "ativo" and linha["etapas_realizadas"] == 0

        rb = c.post(f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 0})
        assert rb.status_code == 200, rb.text
        assert linha_de(c, "customizado", lancamento_id, "historico")["status"] == "concluido"

    def test_etapa_fora_da_janela_iatf_some_da_agenda_mas_continua_baixavel(self, client):
        c, engine = client
        r = lancar_iatf(c, ["116"], _d(45))  # D0/D7/D9/D11 — tudo além de 30 dias
        lancamento_id = r.json()["lancamento_id"]

        assert self._tem_evento(c, "protocolo_iatf") == []
        linha = linha_de(c, "iatf", lancamento_id)
        assert linha["status"] == "ativo" and linha["etapas_realizadas"] == 0

        rb = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0})
        assert rb.status_code == 200, rb.text
        assert linha_de(c, "iatf", lancamento_id)["etapas_realizadas"] == 1

    def test_etapa_fora_da_janela_lida(self, client):
        c, engine = client
        lid = cadastrar_lida_frequencia(c, "Lida esquecida", 10)
        r = lancar_lida(c, lid, _d(45), data_fim=_d(45))
        lancamento_id = r.json()["lancamento_id"]

        assert self._tem_evento(c, "lida") == []
        assert linha_de(c, "lida", lancamento_id)["status"] == "ativo"
        rb = c.post(f"/central-protocolos/lida/{lancamento_id}/baixa", json={"dia": 0})
        assert rb.status_code == 200, rb.text


# ═══════════════════════════ 4. Lançamento retroativo ═════════════════════════

class TestLancamentoRetroativo:
    def test_customizado_retroativo_pendencia_aparece_como_pendencia(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo retroativo", [
            {"dia": 0, "descricao_evento": "Etapa 1"}, {"dia": 5, "descricao_evento": "Etapa 2"},
        ])
        # D0 há 10 dias — D0 e D5 já venceram, ambos dentro da janela de 30 dias.
        r = lancar_customizado(c, pid, ["120"], _d(10))
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]

        ag = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        eventos = [e for e in ag["eventos"] if e.get("tipo") == "protocolo_customizado"]
        # As DUAS etapas vencidas aparecem como pendência — não ficam escondidas
        # só porque a data já passou (ver docstring de eventos_agenda).
        assert len(eventos) == 2

        linha = linha_de(c, "customizado", lancamento_id)
        assert linha["status"] == "ativo" and linha["etapas_realizadas"] == 0

    def test_iatf_retroativo_pendencias_aparecem_e_status_inicial_e_ativo(self, client):
        c, engine = client
        r = lancar_iatf(c, ["121"], _d(15))  # D0/D7/D9 já venceram, D11 também
        lancamento_id = r.json()["lancamento_id"]

        ag = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        eventos = [e for e in ag["eventos"] if e.get("tipo") == "protocolo_iatf"]
        assert len(eventos) == 4  # D0/D7/D9/D11 — todas as 4 etapas vencidas, nenhuma escondida

        assert linha_de(c, "iatf", lancamento_id)["status"] == "ativo"

    @pytest.mark.xfail(
        reason=(
            "BUG confirmado fora do meu escopo de correção: "
            "GET /producao/inducao-lactacao/ativos (fazenda/api/routers/producao.py, "
            "listar_inducao_lactacao_ativos ~L1350-1398) lista QUALQUER lançamento com "
            "aplicação pendente, sem nenhuma janela de tempo nem mecanismo de "
            "'abandonado -> concluído' (diferente do equivalente de IATF, "
            "GRACA_D11_ATRASADO_DIAS em reproducao.py ~L1039/1120-1130, que eventualmente "
            "para de listar um protocolo esquecido). Já a Agenda "
            "(fazenda/api/routers/agenda.py ~L531-543) aplica JANELA_ATRASO_PROTOCOLO_DIAS "
            "(30 dias) à indução — sem a exceção 'retroativo' que o IATF tem (ver comentário "
            "em ProtocoloIatfLancamento.retroativo, fazenda/models/reprodutivo.py ~L177-180). "
            "Resultado: uma indução lançada retroativamente (D0 > 30 dias atrás) some da "
            "Agenda mas continua aparecendo para sempre em /producao/inducao-lactacao/ativos "
            "— a tela de 'Pendências' e a Agenda divergem sobre se o protocolo ainda está "
            "pendente. Reproduzido isolado em probe manual antes deste teste "
            "(agenda: nenhum evento 'protocolo_inducao'; ativos: lançamento presente). "
            "Bate com o relato do usuário de indução retroativa inconsistente entre Agenda "
            "e Pendências. Fix natural: aplicar a mesma janela (ou um teto de 'abandonado') "
            "em listar_inducao_lactacao_ativos."
        ),
        strict=False,
    )
    def test_inducao_retroativa_pendencias_agenda_e_ativos_devem_concordar(self, client):
        c, engine = client
        pid = cadastrar_molde_inducao(c, "Indução retroativa", [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
        ])
        r = lancar_inducao(c, pid, ["122"], _d(40))
        assert r.status_code == 201, r.text

        ag = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        na_agenda = any(e.get("tipo") == "protocolo_inducao" for e in ag["eventos"])
        ativos = c.get("/producao/inducao-lactacao/ativos").json()
        nos_ativos = any(a["nome_protocolo"].startswith("INDUÇÃO RETROATIVA") for a in ativos)

        # Comportamento esperado (consistente): as duas telas concordam sobre
        # se o lançamento ainda está pendente. Hoje `na_agenda` é False e
        # `nos_ativos` é True — a asserção abaixo é o que DEVERIA valer.
        assert na_agenda == nos_ativos


# ═══════════════════════ 5. Cronogramas não-clássicos ═════════════════════════

class TestCronogramasNaoClassicos:
    def test_dia_inseminacao_e_sempre_maior_dia_mais_dois(self):
        assert dia_inseminacao([0, 7, 9]) == 11  # clássico
        assert dia_inseminacao([0, 8, 10, 12]) == 14  # dias livres
        assert dia_inseminacao([5]) == 7
        assert dia_inseminacao([]) == DIA_INSEMINACAO_PADRAO == 11  # defensivo — não deveria acontecer na prática

    def test_iatf_molde_dias_livres_gera_aplicacoes_nos_dias_certos(self, client):
        c, engine = client
        pid = cadastrar_molde_iatf(c, "Molde D0 D8 D10 D12", [0, 8, 10, 12])
        r = lancar_iatf(c, ["201"], _d(0), protocolo_id=pid)
        assert r.status_code == 200, r.text
        lancamento_id = r.json()["lancamento_id"]
        with Session(engine) as s:
            dias = sorted(
                a.dia for a in s.exec(
                    select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lancamento_id)
                ).all()
            )
        assert dias == [0, 8, 10, 12, 14]  # inseminação = maior dia (12) + 2

    def test_iatf_molde_dias_livres_rotulos_no_detalhe_central(self, client):
        c, engine = client
        pid = cadastrar_molde_iatf(c, "Molde rotulos livres", [0, 8, 10, 12])
        r = lancar_iatf(c, ["202"], _d(0), protocolo_id=pid)
        lancamento_id = r.json()["lancamento_id"]
        det = c.get(f"/central-protocolos/iatf/{lancamento_id}").json()
        rotulos = sorted((d["dia"], d["rotulo"]) for d in det["dias"])
        assert rotulos == [(0, "D0"), (8, "D8"), (10, "D10"), (12, "D12"), (14, "D14")]

    def test_lida_periodo_dia_fim_repete_diariamente_com_rotulos_corretos(self, client):
        c, engine = client
        lid = cadastrar_lida_periodo(c, "Obra da cerca rotulos", [
            {"dia_inicio": 0, "dia_fim": 3, "descricao_evento": "Enviar foto", "foto_obrigatoria": True},
        ])
        r = lancar_lida(c, lid, _d(0), animais=["301"])
        lancamento_id = r.json()["lancamento_id"]
        det = c.get(f"/central-protocolos/lida/{lancamento_id}").json()
        rotulos = sorted((d["dia"], d["rotulo"]) for d in det["dias"])
        assert rotulos == [(0, "D0"), (1, "D1"), (2, "D2"), (3, "D3")]

    def test_lida_frequencia_a_cada_n_dias_entre_inicio_e_fim(self, client):
        c, engine = client
        lid = cadastrar_lida_frequencia(c, "Verificar cerca N dias", 7)
        r = lancar_lida(c, lid, _d(0), data_fim=(HOJE + timedelta(days=20)).isoformat())
        lancamento_id = r.json()["lancamento_id"]
        with Session(engine) as s:
            dias = sorted(
                a.dia for a in s.exec(select(LidaAplicacao).where(LidaAplicacao.lancamento_id == lancamento_id)).all()
            )
        assert dias == [0, 7, 14]  # a cada 7 dias, sem passar de +20

    def test_customizado_dia_inicial_1_rotulo_relativo_ao_inicio(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo D1", [
            {"dia": 1, "descricao_evento": "Etapa 1"}, {"dia": 4, "descricao_evento": "Etapa 2"},
        ], dia_inicial=1)
        r = lancar_customizado(c, pid, ["401"], _d(0))
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]
        det = c.get(f"/central-protocolos/customizado/{lancamento_id}").json()
        rotulos = sorted((d["dia"], d["rotulo"]) for d in det["dias"])
        # dia bruto 1 e 4, mas o rótulo é relativo ao dia_inicial=1 -> D0 e D3.
        assert rotulos == [(1, "D0"), (4, "D3")]

    def test_customizado_dia_inicial_1_no_evento_da_agenda(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Protocolo D1 agenda", [
            {"dia": 1, "descricao_evento": "Etapa 1"},
        ], dia_inicial=1)
        r = lancar_customizado(c, pid, ["402"], _d(0))
        assert r.status_code == 201, r.text
        ag = c.get("/agenda/", params={"data": HOJE.isoformat()}).json()
        eventos = [e for e in ag["eventos"] if e.get("tipo") == "protocolo_customizado"]
        assert any(e["dia"] == 0 for e in eventos)  # dia bruto 1 - dia_inicial 1 = rótulo 0


# ══════════════════════════════════ 6. Bordas ═════════════════════════════════

class TestBordas:
    def test_iatf_lancar_sem_animal_da_400(self, client):
        c, engine = client
        r = lancar_iatf(c, [], _d(0))
        assert r.status_code == 400

    def test_inducao_lancar_sem_animal_da_400(self, client):
        c, engine = client
        pid = cadastrar_molde_inducao(c, "Indução sem animal", [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato", "dose": 1, "unidade": "ml"},
        ])
        r = lancar_inducao(c, pid, [], _d(0))
        assert r.status_code == 400

    def test_customizado_sem_animal_vira_tarefa_da_fazenda(self, client):
        # Diferente de IATF/Indução: customizado e lida aceitam lançamento sem
        # nenhum animal — vira uma tarefa geral da fazenda (comportamento
        # documentado, não um bug).
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Tarefa da fazenda", [{"dia": 0, "descricao_evento": "Vistoriar cerca"}])
        r = lancar_customizado(c, pid, [], _d(0))
        assert r.status_code == 201, r.text
        assert r.json()["animais"] == 0
        with Session(engine) as s:
            aps = s.exec(
                select(ProtocoloCustomizadoAplicacao).where(
                    ProtocoloCustomizadoAplicacao.lancamento_id == r.json()["lancamento_id"]
                )
            ).all()
            assert aps[0].numero_matriz is None

    @pytest.mark.parametrize("endpoint,payload", [
        ("/cadastro/protocolos-iatf", {"nome": "IATF sem etapa"}),
        ("/cadastro/protocolos-inducao-lactacao", {"nome": "Indução sem etapa"}),
        ("/cadastro/protocolos-customizados", {"nome": "Customizado sem etapa", "categoria": "Rebanho"}),
        ("/cadastro/lidas", {"nome": "Lida sem etapa", "modo": "periodo"}),
    ])
    def test_molde_sem_etapa_e_rejeitado(self, client, endpoint, payload):
        c, engine = client
        r = c.post(endpoint, json={**payload, "etapas": []})
        assert r.status_code == 400, r.text

    def test_iatf_baixa_em_dia_inexistente_da_404(self, client):
        c, engine = client
        r = lancar_iatf(c, ["501"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        rb = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 999})
        assert rb.status_code == 404

    # Regressão: só o ramo `iatf` checava se o dia existe. As outras 3 origens
    # caíam direto em `_marcar_*_realizado`, não achavam nenhuma aplicação
    # naquele dia e devolviam 200 {"ok": True} sem gravar nada — baixa
    # fantasma. A checagem foi elevada para valer nas quatro.
    @pytest.mark.parametrize("origem,setup", [
        ("customizado", "customizado"), ("lida", "lida"), ("inducao", "inducao"),
    ])
    def test_baixa_em_dia_inexistente_deveria_dar_404_em_todas_as_origens(self, client, origem, setup):
        c, engine = client
        if setup == "customizado":
            pid = cadastrar_molde_customizado(c, f"Molde 404 {origem}", [{"dia": 0, "descricao_evento": "Aplicar"}])
            r = lancar_customizado(c, pid, ["601"], _d(0))
        elif setup == "lida":
            lid = cadastrar_lida_frequencia(c, f"Molde 404 {origem}", 5)
            r = lancar_lida(c, lid, _d(0), data_fim=_d(0))
        else:
            pid = cadastrar_molde_inducao(c, f"Molde 404 {origem}", [
                {"dia": 0, "tipo": "medicamento", "produto": "Benzoato", "dose": 1, "unidade": "ml"},
            ])
            r = lancar_inducao(c, pid, ["601"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        rb = c.post(f"/central-protocolos/{origem}/{lancamento_id}/baixa", json={"dia": 999})
        assert rb.status_code == 404

    def test_iatf_baixa_duas_vezes_no_mesmo_dia_e_idempotente(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Sincrocp", quantidade=50, unidade="ml"))
            s.commit()
        r = lancar_iatf(c, ["701"], _d(0), hormonios=[
            {"dia": 0, "produto": "Sincrocp", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ])
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0})
        r2 = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0})
        assert r2.status_code == 200, r2.text
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Sincrocp")).first()
        assert item.quantidade == 50 - 2  # a segunda baixa não desconta de novo

    def test_desfazer_aplicacao_ja_desfeita_da_400_customizado(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Desfazer 400", [{"dia": 0, "descricao_evento": "Aplicar"}])
        r = lancar_customizado(c, pid, ["702"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 0})
        primeira = c.request("DELETE", f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 0, "numero_matriz": "702"})
        assert primeira.status_code == 200, primeira.text
        segunda = c.request("DELETE", f"/central-protocolos/customizado/{lancamento_id}/baixa", json={"dia": 0, "numero_matriz": "702"})
        assert segunda.status_code == 400

    def test_encerrar_ja_encerrado_e_idempotente(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Encerrar 2x", [{"dia": 0, "descricao_evento": "Aplicar"}])
        r = lancar_customizado(c, pid, ["703"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        r1 = c.post(f"/central-protocolos/customizado/{lancamento_id}/encerrar", json={"motivo": "a"})
        r2 = c.post(f"/central-protocolos/customizado/{lancamento_id}/encerrar", json={"motivo": "b"})
        assert r1.status_code == 200 and r2.status_code == 200
        assert linha_de(c, "customizado", lancamento_id, "historico")["status"] == "encerrado"

    def test_reabrir_nao_encerrado_e_idempotente(self, client):
        c, engine = client
        pid = cadastrar_molde_customizado(c, "Reabrir sem encerrar", [{"dia": 0, "descricao_evento": "Aplicar"}])
        r = lancar_customizado(c, pid, ["704"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        rr = c.request("DELETE", f"/central-protocolos/customizado/{lancamento_id}/encerrar")
        assert rr.status_code == 200, rr.text
        assert linha_de(c, "customizado", lancamento_id)["status"] == "ativo"

    def test_cancelar_ja_cancelado_nao_deveria_dobrar_o_estorno_de_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Detergente para cochos", quantidade=20, unidade="L"))
            s.commit()
        lid = cadastrar_lida_frequencia(
            c, "Lida cancelar 2x", 15, dar_baixa=True,
            insumo_padrao="Detergente para cochos", insumo_dose=0.5, insumo_unidade="L",
        )
        r = lancar_lida(c, lid, _d(0), data_fim=_d(0), animais=["705", "706"])
        lancamento_id = r.json()["lancamento_id"]
        c.post(f"/central-protocolos/lida/{lancamento_id}/baixa", json={"dia": 0})
        with Session(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "Detergente para cochos")).first().quantidade == 19.0

        r1 = c.post(f"/central-protocolos/lida/{lancamento_id}/cancelar", json={"motivo": "x"})
        assert r1.status_code == 200, r1.text
        with Session(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "Detergente para cochos")).first().quantidade == 20.0

        r2 = c.post(f"/central-protocolos/lida/{lancamento_id}/cancelar", json={"motivo": "x de novo"})
        # Comportamento esperado: cancelar de novo não deveria fazer nada (o
        # lançamento já não está ativo) — o estoque tem que continuar em 20.
        assert r2.status_code == 400
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Detergente para cochos")).first()
        assert item.quantidade == 20.0

    def test_data_realizacao_no_futuro_da_400(self, client):
        c, engine = client
        r = lancar_iatf(c, ["707"], _d(0))
        lancamento_id = r.json()["lancamento_id"]
        futuro = (HOJE + timedelta(days=5)).isoformat()
        rb = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0, "data_realizacao": futuro})
        assert rb.status_code == 400

    def test_data_realizacao_no_futuro_da_400_lida(self, client):
        c, engine = client
        lid = cadastrar_lida_frequencia(c, "Lida data futura", 5)
        r = lancar_lida(c, lid, _d(0), data_fim=_d(0))
        lancamento_id = r.json()["lancamento_id"]
        futuro = (HOJE + timedelta(days=5)).isoformat()
        rb = c.post(f"/central-protocolos/lida/{lancamento_id}/baixa", json={"dia": 0, "data_realizacao": futuro})
        assert rb.status_code == 400


# ═══════════════════════ Unidade: nomenclatura_protocolo.py ══════════════════

class TestNomenclaturaProtocolo:
    def test_gerar_nome_lancamento_com_dia_inicial_nao_zero(self):
        nome = gerar_nome_lancamento("Protocolo X", date(2026, 8, 5), dia_inicial=1, dia_final=4)
        assert nome == "PROTOCOLO X - 05/08/26 A 08/08/26 (D1 A D4 - 4 DIAS)"

    def test_nome_curto_remove_sufixo_gerado(self):
        nome = gerar_nome_lancamento("Vacina", date(2026, 8, 5), 0, 3)
        assert nome_curto(nome) == "VACINA"

    def test_nome_curto_mantem_nome_legado_sem_sufixo(self):
        assert nome_curto("Nome digitado à mão, sem sufixo") == "Nome digitado à mão, sem sufixo"
