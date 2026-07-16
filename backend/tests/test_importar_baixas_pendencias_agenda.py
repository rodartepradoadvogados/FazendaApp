"""
Baixa em massa de pendências antigas da Agenda (Configurações > Importar dados >
"baixas_pendencias_agenda") — resolve pendências de sanidade antigas (evento
sanitário por gatilho, evento sanitário por época, calendário sanitário e
aplicação agendada) pelo mesmo caminho real de sempre (registrar_aplicacao /
_baixar_aplicacao_agendada), gravando a aplicação em Sanidade e dispensando a
pendência da Agenda (EventoRealizado) — sem criar nenhuma regra nova.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import AplicacaoAgendada, Animal, CalendarioSanitario, EventoRealizado, EventoSanitario, Sanidade


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


def _csv(linhas: list[list[str]]) -> bytes:
    colunas = [
        "tipo", "nome_evento", "numero_animal", "data_pendencia", "produto_aplicado", "dose", "unidade", "via",
        "responsavel", "observacao",
    ]
    texto = ";".join(colunas) + "\r\n" + "\r\n".join(";".join(l) for l in linhas) + "\r\n"
    return texto.encode("windows-1252")


def _upload(c, linhas: list[list[str]], data_corte: str = "") -> dict:
    r = c.post(
        "/importar/baixas_pendencias_agenda",
        files={"file": ("baixas.csv", _csv(linhas), "text/csv")},
        data={"data_corte": data_corte},
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestEventoSanitarioPorGatilho:
    def test_resolve_e_grava_aplicacao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="464", data_nasc=date(2026, 4, 10), sexo="F"))
            s.add(EventoSanitario(
                nome="Brucelose B19", tipo_agendamento="evento", gatilho="nascimento",
                produto_padrao="Vacina B19", dose_padrao=2, unidade_padrao="ml", via_padrao="Subcutânea",
            ))
            s.commit()

        d = _upload(c, [["evento_sanitario", "Brucelose B19", "464", "10/04/2026", "", "", "", "", "Carlos", ""]])
        assert d["criados"] == 1
        assert d["dispensados"] == 1
        assert not d["erros"]

        with Session(engine) as s:
            aplicacoes = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "464")).all()
            assert len(aplicacoes) == 1
            assert aplicacoes[0].produto == "Vacina B19"
            ev = s.exec(select(EventoSanitario).where(EventoSanitario.nome == "Brucelose B19")).first()
            realizado = s.exec(select(EventoRealizado).where(
                EventoRealizado.evento_id == f"evento_sanitario_{ev.id}__464__2026-04-10"
            )).first()
            assert realizado is not None

    def test_nao_duplica_ao_reenviar(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="465", data_nasc=date(2026, 4, 10), sexo="F"))
            s.add(EventoSanitario(
                nome="Leptospirose", tipo_agendamento="evento", gatilho="nascimento",
                produto_padrao="Vacina Lepto", dose_padrao=5, unidade_padrao="ml",
            ))
            s.commit()

        linhas = [["evento_sanitario", "Leptospirose", "465", "10/04/2026", "", "", "", "", "", ""]]
        d1 = _upload(c, linhas)
        assert d1["criados"] == 1 and d1["dispensados"] == 1

        d2 = _upload(c, linhas)
        assert d2["criados"] == 0
        assert d2["dispensados"] == 0

        with Session(engine) as s:
            aplicacoes = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "465")).all()
            assert len(aplicacoes) == 1

    def test_data_nao_confere_com_o_gatilho_da_erro(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="466", data_nasc=date(2026, 4, 10), sexo="F"))
            s.add(EventoSanitario(
                nome="Vacina X", tipo_agendamento="evento", gatilho="nascimento",
                produto_padrao="Produto X", dose_padrao=1, unidade_padrao="ml",
            ))
            s.commit()
        d = _upload(c, [["evento_sanitario", "Vacina X", "466", "01/01/2026", "", "", "", "", "", ""]])
        assert d["criados"] == 0
        assert len(d["erros"]) == 1


class TestEventoSanitarioPorEpoca:
    def test_resolve_rebanho_com_animais_informados(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="470", sexo="F"))
            s.add(Animal(numero="471", sexo="F"))
            s.add(EventoSanitario(
                nome="Vermífugo trimestral", tipo_agendamento="epoca",
                data_primeiro=date(2026, 1, 10), frequencia_valor=3, frequencia_unidade="meses",
                produto_padrao="Ivermectina", dose_padrao=10, unidade_padrao="ml",
            ))
            s.commit()

        # data_primeiro=10/01, +3 meses -> 10/04/2026 é uma ocorrência válida.
        d = _upload(c, [["evento_sanitario", "Vermífugo trimestral", "470,471", "10/04/2026", "", "", "", "", "", ""]])
        assert d["criados"] == 2
        assert d["dispensados"] == 1
        assert not d["erros"]

        with Session(engine) as s:
            numeros = {a.numero_matriz for a in s.exec(select(Sanidade)).all()}
            assert numeros == {"470", "471"}

    def test_sem_numero_animal_da_erro(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(EventoSanitario(
                nome="Vacina de rebanho", tipo_agendamento="epoca",
                data_primeiro=date(2026, 1, 10), frequencia_valor=3, frequencia_unidade="meses",
                produto_padrao="Produto Y", dose_padrao=1, unidade_padrao="ml",
            ))
            s.commit()
        d = _upload(c, [["evento_sanitario", "Vacina de rebanho", "", "10/04/2026", "", "", "", "", "", ""]])
        assert d["criados"] == 0
        assert len(d["erros"]) == 1


class TestCalendarioSanitario:
    def test_resolve_e_grava_aplicacao(self, client):
        c, engine = client
        with Session(engine) as s:
            ev = EventoSanitario(nome="Vacina pré-parto")
            s.add(ev)
            s.commit()
            s.refresh(ev)
            s.add(Animal(numero="480", sexo="F"))
            s.add(CalendarioSanitario(
                evento_sanitario_id=ev.id, categoria_alvo="Pré-parto", produto="Vacina P",
                dosagem="5 ml", unidade="ml", frequencia_valor=1, frequencia_unidade="anos",
                data_evento=date(2026, 1, 15),
            ))
            s.commit()

        d = _upload(c, [["calendario_sanitario", "Vacina pré-parto", "480", "15/01/2026", "Vacina P", "5", "ml", "", "", ""]])
        assert d["criados"] == 1
        assert d["dispensados"] == 1
        assert not d["erros"]

        with Session(engine) as s:
            aplicacoes = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "480")).all()
            assert len(aplicacoes) == 1
            assert aplicacoes[0].produto == "Vacina P"
            regra = s.exec(select(CalendarioSanitario)).first()
            realizado = s.exec(select(EventoRealizado).where(
                EventoRealizado.evento_id == f"calendario_sanitario_{regra.id}__2026-01-15"
            )).first()
            assert realizado is not None

    def test_evento_nao_cadastrado_da_erro(self, client):
        c, _ = client
        d = _upload(c, [["calendario_sanitario", "Não existe", "1", "15/01/2026", "", "", "", "", "", ""]])
        assert d["criados"] == 0
        assert len(d["erros"]) == 1


class TestAplicacaoAgendada:
    def test_resolve_e_grava_aplicacao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(AplicacaoAgendada(
                numero_matriz="490", data=date(2026, 2, 1), produto="Lactotropin",
                dose=500, unidade="mg", aplicado=False,
            ))
            s.commit()

        d = _upload(c, [["aplicacao_agendada", "", "490", "01/02/2026", "", "", "", "", "", ""]])
        assert d["criados"] == 1
        assert d["dispensados"] == 1
        assert not d["erros"]

        with Session(engine) as s:
            ag = s.exec(select(AplicacaoAgendada).where(AplicacaoAgendada.numero_matriz == "490")).first()
            assert ag.aplicado is True
            aplicacoes = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "490")).all()
            assert len(aplicacoes) == 1

    def test_nao_encontrada_da_erro(self, client):
        c, _ = client
        d = _upload(c, [["aplicacao_agendada", "", "999", "01/02/2026", "", "", "", "", "", ""]])
        assert d["criados"] == 0
        assert len(d["erros"]) == 1


class TestDataDeCorte:
    def test_pendencia_igual_ou_apos_corte_e_ignorada(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", data_nasc=date(2026, 7, 1), sexo="F"))
            s.add(EventoSanitario(
                nome="Vacina recente", tipo_agendamento="evento", gatilho="nascimento",
                produto_padrao="Produto Z", dose_padrao=1, unidade_padrao="ml",
            ))
            s.commit()

        d = _upload(
            c, [["evento_sanitario", "Vacina recente", "500", "01/07/2026", "", "", "", "", "", ""]],
            data_corte="2026-07-01",
        )
        assert d["criados"] == 0
        assert d["dispensados"] == 0
        assert len(d["erros"]) == 1

        with Session(engine) as s:
            assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "500")).first() is None

    def test_pendencia_antes_do_corte_e_resolvida(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="501", data_nasc=date(2026, 6, 1), sexo="F"))
            s.add(EventoSanitario(
                nome="Vacina antiga", tipo_agendamento="evento", gatilho="nascimento",
                produto_padrao="Produto W", dose_padrao=1, unidade_padrao="ml",
            ))
            s.commit()

        d = _upload(
            c, [["evento_sanitario", "Vacina antiga", "501", "01/06/2026", "", "", "", "", "", ""]],
            data_corte="2026-07-01",
        )
        assert d["criados"] == 1
        assert d["dispensados"] == 1
        assert not d["erros"]
