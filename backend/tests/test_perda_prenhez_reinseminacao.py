"""
Perda de prenhez por reinseminação — pedido do produtor:

  "Se uma vaca é diagnosticada positiva, uma nova inseminação faz considerar
  o dia anterior à nova inseminação como perda de prenhez, o que deve fazer
  gerar uma lista na agenda para cadastrar o motivo da perda de prenhez [...]
  Consequentemente [...] essa vaca tem que, obrigatoriamente, sair de todos
  os tipos de manejo e sugestões e listas que competem às vacas ou novilhas
  prenhas, para passar a ser considerada apenas inseminada."

Cobre:
  (a) vaca POSITIVO + nova IA -> perda gravada em D-1, motivo pendente.
  (b) a vaca some de pré-parto/secagem/parto provável na Agenda.
  (c) "Descartar" tira a pendência da lista sem desfazer a perda.
  (d) vaca que pariu entre o positivo e a nova IA NÃO gera perda falsa.
  (e) idempotência — relançar/reprocessar não duplica nem sobrescreve.

Testa tanto a função de regra pura (fazenda.rules.perda_prenhez) quanto a
integração via API (POST /reproducao/servico + GET /agenda/).

NOTA sobre `"forcar": True` nos lançamentos de integração: reinseminar uma
matriz que consta como GESTANTE deixou de ser silencioso. A trava de aptidão
(fazenda/rules/aptidao.py) agora recusa esse lançamento com 409 até alguém
confirmar explicitamente — justamente porque o efeito dele é o sistema gravar
uma perda de prenhez que ninguém afirmou. A detecção automática em si não
mudou: continua acontecendo exatamente como estes testes verificam, só que
depois de uma decisão humana em vez de por conta própria.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Parto, Servico
from fazenda.rules.perda_prenhez import (
    MOTIVO_NAO_INFORMADO,
    ORIGEM_REINSEMINACAO,
    detectar_e_registrar_perda_por_reinseminacao,
    servico_esta_positivo_vigente,
    servicos_positivos_vigentes,
)

HOJE = date(2026, 8, 11)


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _add_animal(engine, numero: str, raca: str | None = "Holandês"):
    with Session(engine) as s:
        s.add(Animal(numero=numero, raca=raca, sexo="F", ativo=True, sit_rep="Ges."))
        s.commit()


def _add_servico(engine, numero: str, data_servico: date, **kwargs) -> int:
    with Session(engine) as s:
        servico = Servico(numero_matriz=numero, data_servico=data_servico, ult_ocorrencia=1, **kwargs)
        s.add(servico)
        s.commit()
        s.refresh(servico)
        return servico.id


# ---------------------------------------------------------------------------
# Unidade — fazenda.rules.perda_prenhez
# ---------------------------------------------------------------------------
class TestServicoEstaPositivoVigente:
    def test_positivo_sem_perda(self):
        assert servico_esta_positivo_vigente({"diagnostico": "POSITIVO", "data_perda_prenhez": None}) is True

    def test_positivo_com_perda_nao_vale_mais(self):
        assert servico_esta_positivo_vigente({"diagnostico": "POSITIVO", "data_perda_prenhez": date(2026, 1, 1)}) is False

    def test_negativo(self):
        assert servico_esta_positivo_vigente({"diagnostico": "NEGATIVO", "data_perda_prenhez": None}) is False

    def test_aceita_objeto_sqlmodel(self):
        s = Servico(numero_matriz="1", diagnostico="POSITIVO")
        assert servico_esta_positivo_vigente(s) is True


class TestServicosPositivosVigentes:
    def test_pega_o_mais_recente_positivo(self):
        servicos = [
            {"numero_matriz": "1", "data_servico": date(2026, 1, 1), "diagnostico": "POSITIVO"},
            {"numero_matriz": "1", "data_servico": date(2026, 3, 1), "diagnostico": "POSITIVO"},
        ]
        vigentes = servicos_positivos_vigentes(servicos)
        assert vigentes["1"]["data_servico"] == date(2026, 3, 1)

    def test_reinseminacao_sem_diagnostico_tira_a_vaca_da_lista(self):
        """O ponto central do bug: um serviço mais novo (ainda sem diagnóstico)
        já invalida o positivo anterior, mesmo que ninguém tenha marcado
        `data_perda_prenhez` nele."""
        servicos = [
            {"numero_matriz": "1", "data_servico": date(2026, 1, 1), "diagnostico": "POSITIVO"},
            {"numero_matriz": "1", "data_servico": date(2026, 6, 1), "diagnostico": None},
        ]
        assert "1" not in servicos_positivos_vigentes(servicos)

    def test_perda_registrada_tira_a_vaca_da_lista(self):
        servicos = [
            {"numero_matriz": "1", "data_servico": date(2026, 1, 1), "diagnostico": "POSITIVO",
             "data_perda_prenhez": date(2026, 6, 1)},
        ]
        assert "1" not in servicos_positivos_vigentes(servicos)

    def test_parto_depois_do_servico_tira_a_vaca_da_lista(self):
        servicos = [{"numero_matriz": "1", "data_servico": date(2026, 1, 1), "diagnostico": "POSITIVO"}]
        partos = [{"numero_matriz": "1", "data_parto": date(2026, 10, 1)}]
        assert "1" not in servicos_positivos_vigentes(servicos, partos)

    def test_servico_apos_o_parto_conta_normalmente(self):
        servicos = [
            {"numero_matriz": "1", "data_servico": date(2026, 1, 1), "diagnostico": "POSITIVO"},  # ciclo anterior
            {"numero_matriz": "1", "data_servico": date(2026, 11, 1), "diagnostico": "POSITIVO"},  # ciclo novo
        ]
        partos = [{"numero_matriz": "1", "data_parto": date(2026, 10, 1)}]
        vigentes = servicos_positivos_vigentes(servicos, partos)
        assert vigentes["1"]["data_servico"] == date(2026, 11, 1)


class TestDetectarERegistrarPerdaPorReinseminacao:
    def test_grava_perda_no_dia_anterior(self, client):
        c, engine = client
        _add_animal(engine, "100")
        _add_servico(engine, "100", date(2026, 3, 1), diagnostico="POSITIVO")
        with Session(engine) as s:
            resultado = detectar_e_registrar_perda_por_reinseminacao(
                s, numero_matriz="100", nova_data_servico=date(2026, 8, 1), fazenda_id=None,
            )
            s.commit()
            assert resultado is not None
            assert resultado.data_perda_prenhez == date(2026, 7, 31)
            assert resultado.motivo_perda_prenhez is None
            assert resultado.origem_perda_prenhez == ORIGEM_REINSEMINACAO

    def test_sem_positivo_anterior_nao_faz_nada(self, client):
        c, engine = client
        _add_animal(engine, "101")
        _add_servico(engine, "101", date(2026, 3, 1), diagnostico="NEGATIVO")
        with Session(engine) as s:
            resultado = detectar_e_registrar_perda_por_reinseminacao(
                s, numero_matriz="101", nova_data_servico=date(2026, 8, 1), fazenda_id=None,
            )
            assert resultado is None

    def test_parto_entre_os_dois_servicos_nao_gera_perda_falsa(self, client):
        c, engine = client
        _add_animal(engine, "102")
        _add_servico(engine, "102", date(2026, 1, 1), diagnostico="POSITIVO")
        with Session(engine) as s:
            s.add(Parto(numero_matriz="102", data_parto=date(2026, 10, 1)))
            s.commit()
        with Session(engine) as s:
            resultado = detectar_e_registrar_perda_por_reinseminacao(
                s, numero_matriz="102", nova_data_servico=date(2026, 11, 1), fazenda_id=None,
            )
            assert resultado is None
        with Session(engine) as s:
            servico = s.exec(select(Servico).where(Servico.numero_matriz == "102")).first()
            assert servico.data_perda_prenhez is None

    def test_idempotente_nao_sobrescreve_perda_ja_registrada(self, client):
        c, engine = client
        _add_animal(engine, "103")
        servico_id = _add_servico(
            engine, "103", date(2026, 3, 1), diagnostico="POSITIVO",
            data_perda_prenhez=date(2026, 5, 1), motivo_perda_prenhez="aborto",
        )
        with Session(engine) as s:
            resultado = detectar_e_registrar_perda_por_reinseminacao(
                s, numero_matriz="103", nova_data_servico=date(2026, 8, 1), fazenda_id=None,
            )
            assert resultado is None
        with Session(engine) as s:
            servico = s.get(Servico, servico_id)
            assert servico.data_perda_prenhez == date(2026, 5, 1)
            assert servico.motivo_perda_prenhez == "aborto"


# ---------------------------------------------------------------------------
# Integração — POST /reproducao/servico + GET /agenda/
# ---------------------------------------------------------------------------
class TestIntegracaoReinseminacao:
    def test_nova_ia_sobre_positivo_grava_perda_e_gera_pendencia_na_agenda(self, client):
        c, engine = client
        _add_animal(engine, "200")
        _add_servico(engine, "200", date(2026, 3, 1), diagnostico="POSITIVO")

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "200", "data_servico": "2026-08-01", "tipo_servico": "IA", "forcar": True,
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            servicos = s.exec(select(Servico).where(Servico.numero_matriz == "200")).all()
        anterior = next(sv for sv in servicos if sv.data_servico == date(2026, 3, 1))
        assert anterior.data_perda_prenhez == date(2026, 7, 31)
        assert anterior.motivo_perda_prenhez is None
        assert anterior.origem_perda_prenhez == "reinseminacao"

        r = c.get("/agenda/", params={"data": "2026-08-01"})
        assert r.status_code == 200
        pendencias = [e for e in r.json()["eventos"] if e.get("tipo") == "perda_prenhez_motivo"]
        assert len(pendencias) == 1
        assert pendencias[0]["numero_animal"] == "200"
        assert pendencias[0]["servico_id"] == anterior.id

    def test_vaca_reinseminada_some_de_pre_parto_secagem_parto_provavel(self, client):
        """Consequência obrigatória do pedido: depois da perda automática, a
        Agenda não pode mais sugerir Parto provável/Pré-parto/Secagem para
        essa vaca a partir do diagnóstico antigo."""
        c, engine = client
        _add_animal(engine, "201")
        _add_servico(engine, "201", date(2026, 3, 1), diagnostico="POSITIVO")

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "201", "data_servico": "2026-08-01", "tipo_servico": "IA", "forcar": True,
        })
        assert r.status_code == 200, r.text

        r = c.get("/agenda/", params={"data": "2026-08-01"})
        eventos_201 = [e for e in r.json()["eventos"] if e.get("numero_animal") == "201"]
        descricoes = " | ".join(e["descricao"] for e in eventos_201)
        assert "Parto provável" not in descricoes
        assert "Pré-parto" not in descricoes
        assert "Secagem" not in descricoes

    def test_vaca_que_pariu_entre_positivo_e_nova_ia_nao_gera_perda_falsa(self, client):
        c, engine = client
        _add_animal(engine, "202")
        _add_servico(engine, "202", date(2026, 1, 1), diagnostico="POSITIVO")
        with Session(engine) as s:
            s.add(Parto(numero_matriz="202", data_parto=date(2026, 10, 1)))
            s.commit()

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "202", "data_servico": "2026-11-05", "tipo_servico": "IA",
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            servico_antigo = s.exec(
                select(Servico).where(Servico.numero_matriz == "202", Servico.data_servico == date(2026, 1, 1))
            ).first()
        assert servico_antigo.data_perda_prenhez is None

    def test_idempotencia_via_api_nao_duplica_pendencia_nem_sobrescreve(self, client):
        c, engine = client
        _add_animal(engine, "203")
        _add_servico(engine, "203", date(2026, 3, 1), diagnostico="POSITIVO")

        r1 = c.post("/reproducao/servico", json={
            "numero_matriz": "203", "data_servico": "2026-08-01", "tipo_servico": "IA", "forcar": True,
        })
        assert r1.status_code == 200, r1.text

        # Reinseminar de novo (3ª IA) não deve mexer na perda já registrada na
        # 1ª (o serviço imediatamente anterior a esta 3ª é a 2ª IA, sem
        # diagnóstico — não há prenhez vigente para "perder" de novo).
        r2 = c.post("/reproducao/servico", json={
            "numero_matriz": "203", "data_servico": "2026-09-15", "tipo_servico": "IA", "forcar": True,
        })
        assert r2.status_code == 200, r2.text

        with Session(engine) as s:
            servicos = s.exec(select(Servico).where(Servico.numero_matriz == "203")).all()
        com_perda = [sv for sv in servicos if sv.data_perda_prenhez is not None]
        assert len(com_perda) == 1
        assert com_perda[0].data_servico == date(2026, 3, 1)
        assert com_perda[0].data_perda_prenhez == date(2026, 7, 31)

        r = c.get("/agenda/", params={"data": "2026-09-15"})
        pendencias = [e for e in r.json()["eventos"] if e.get("tipo") == "perda_prenhez_motivo"]
        assert len(pendencias) == 1

    def test_cadastrar_motivo_remove_pendencia_da_agenda(self, client):
        c, engine = client
        _add_animal(engine, "204")
        _add_servico(engine, "204", date(2026, 3, 1), diagnostico="POSITIVO")
        c.post("/reproducao/servico", json={
            "numero_matriz": "204", "data_servico": "2026-08-01", "tipo_servico": "IA", "forcar": True,
        })
        with Session(engine) as s:
            anterior = s.exec(
                select(Servico).where(Servico.numero_matriz == "204", Servico.data_servico == date(2026, 3, 1))
            ).first()
            servico_id = anterior.id

        r = c.put(f"/reproducao/servicos/{servico_id}", json={"motivo_perda_prenhez": "aborto"})
        assert r.status_code == 200, r.text
        assert r.json()["motivo_perda_prenhez"] == "aborto"

        r = c.get("/agenda/", params={"data": "2026-08-01"})
        pendencias = [e for e in r.json()["eventos"] if e.get("tipo") == "perda_prenhez_motivo"]
        assert not any(p["servico_id"] == servico_id for p in pendencias)

    def test_descartar_remove_pendencia_mas_mantem_a_perda(self, client):
        c, engine = client
        _add_animal(engine, "205")
        _add_servico(engine, "205", date(2026, 3, 1), diagnostico="POSITIVO")
        c.post("/reproducao/servico", json={
            "numero_matriz": "205", "data_servico": "2026-08-01", "tipo_servico": "IA", "forcar": True,
        })
        with Session(engine) as s:
            anterior = s.exec(
                select(Servico).where(Servico.numero_matriz == "205", Servico.data_servico == date(2026, 3, 1))
            ).first()
            servico_id = anterior.id
            data_perda_antes = anterior.data_perda_prenhez

        r = c.put(f"/reproducao/servicos/{servico_id}", json={"motivo_perda_prenhez": MOTIVO_NAO_INFORMADO})
        assert r.status_code == 200, r.text
        assert r.json()["motivo_perda_prenhez"] == "nao_informado"
        assert r.json()["data_perda_prenhez"] == data_perda_antes.isoformat()

        r = c.get("/agenda/", params={"data": "2026-08-01"})
        pendencias = [e for e in r.json()["eventos"] if e.get("tipo") == "perda_prenhez_motivo"]
        assert not any(p["servico_id"] == servico_id for p in pendencias)

        with Session(engine) as s:
            servico = s.get(Servico, servico_id)
            assert servico.data_perda_prenhez == data_perda_antes  # a perda continua registrada

    def test_motivo_invalido_rejeitado(self, client):
        c, engine = client
        _add_animal(engine, "206")
        servico_id = _add_servico(
            engine, "206", date(2026, 3, 1), diagnostico="POSITIVO",
            data_perda_prenhez=date(2026, 6, 1),
        )
        r = c.put(f"/reproducao/servicos/{servico_id}", json={"motivo_perda_prenhez": "motivo_inventado"})
        assert r.status_code == 400

    def test_servico_lote_tambem_detecta_perda_por_reinseminacao(self, client):
        """Segundo caminho de criação de Servico (lançamento em lote/cio
        natural) usa a mesma regra."""
        c, engine = client
        _add_animal(engine, "207")
        _add_servico(engine, "207", date(2026, 3, 1), diagnostico="POSITIVO")

        r = c.post("/reproducao/servico-lote", json={
            "animais": ["207"], "data_servico": "2026-08-01", "tipo": "cio_natural", "forcar": True,
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            anterior = s.exec(
                select(Servico).where(Servico.numero_matriz == "207", Servico.data_servico == date(2026, 3, 1))
            ).first()
        assert anterior.data_perda_prenhez == date(2026, 7, 31)
        assert anterior.origem_perda_prenhez == "reinseminacao"


class TestExcluirServicoCausadorRevertePerdaPrenhez:
    """Gauntlet A-10: a perda automática (acima) gravava tudo no serviço
    ANTERIOR sem guardar qual serviço NOVO a causou — excluir essa nova
    inseminação (ex.: lançamento em duplicidade) não tinha como desfazer a
    perda que ela mesma disparou. `Servico.perda_causada_por_servico_id`
    fecha esse vínculo; `exclusoes.py` usa-o para reverter."""

    def test_excluir_causador_com_motivo_pendente_reverte_a_perda(self, client):
        c, engine = client
        _add_animal(engine, "700")
        _add_servico(engine, "700", date(2026, 3, 1), diagnostico="POSITIVO")

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": "2026-08-01", "tipo_servico": "IA", "forcar": True,
        })
        assert r.status_code == 200, r.text
        causador_id = r.json()["id"]

        with Session(engine) as s:
            anterior = s.exec(
                select(Servico).where(Servico.numero_matriz == "700", Servico.data_servico == date(2026, 3, 1))
            ).first()
            assert anterior.data_perda_prenhez == date(2026, 7, 31)
            assert anterior.perda_causada_por_servico_id == causador_id
            anterior_id = anterior.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "servico", "id": str(causador_id)})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            anterior = s.get(Servico, anterior_id)
            assert anterior.data_perda_prenhez is None, \
                "excluir a IA causadora deve desfazer a perda automática ainda pendente de motivo"
            assert anterior.origem_perda_prenhez is None
            assert anterior.perda_causada_por_servico_id is None
            assert anterior.diagnostico == "POSITIVO", "a vaca volta a estar prenha vigente"

    def test_excluir_causador_com_motivo_ja_confirmado_preserva_a_perda(self, client):
        """Depois que alguém confirmou o motivo (a perda deixou de ser só uma
        inferência), excluir o causador não pode apagar um fato já
        registrado — só desvincula a referência ao serviço que não existe
        mais."""
        c, engine = client
        _add_animal(engine, "701")
        _add_servico(engine, "701", date(2026, 3, 1), diagnostico="POSITIVO")

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "701", "data_servico": "2026-08-01", "tipo_servico": "IA", "forcar": True,
        })
        assert r.status_code == 200, r.text
        causador_id = r.json()["id"]

        with Session(engine) as s:
            anterior_id = s.exec(
                select(Servico).where(Servico.numero_matriz == "701", Servico.data_servico == date(2026, 3, 1))
            ).first().id

        c.put(f"/reproducao/servicos/{anterior_id}", json={"motivo_perda_prenhez": "aborto"})

        r = c.post("/exclusoes/confirmar", json={"tipo": "servico", "id": str(causador_id)})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            anterior = s.get(Servico, anterior_id)
            assert anterior.data_perda_prenhez == date(2026, 7, 31), "motivo já confirmado — a perda é um fato"
            assert anterior.motivo_perda_prenhez == "aborto"
            assert anterior.perda_causada_por_servico_id is None, "referência ao serviço apagado é desvinculada"
