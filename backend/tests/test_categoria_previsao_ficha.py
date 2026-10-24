"""
Investigação (24/10/2026) do relatório do bot Hermes sobre o lote 13 ("o trigger de categoria não dispara ao concluir o IATF").

O que o código realmente faz:
  * `Animal.categoria_completa` é um TEXTO do GERAL.csv (Ideagri). Só o parto/aborto o reescreve (e só tira o
    "gestante"). Lançar protocolo, inseminação ou diagnóstico NÃO mexe nele — não existe "trigger" que falhou.
  * `previsao_parto` da Ficha vem do SERVIÇO (diagnóstico POSITIVO vigente), nunca da categoria nem do protocolo.
  * A situação reprodutiva que vale é a ao vivo (`rules/estado_reprodutivo.py`).

Estes testes fixam esse comportamento (casos A–C do relatório) e o único defeito de código achado: a Ficha dava previsão
de parto onde a situação ao vivo não é "gestante" (caso D).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Servico
from fazenda.rules.estado_reprodutivo import GESTANTE, INSEMINADA, classificar_animal


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


def _estado_ao_vivo(engine, numero: str) -> dict:
    with Session(engine) as s:
        servicos = s.exec(select(Servico).where(Servico.numero_matriz == numero)).all()
        return classificar_animal(
            numero, hoje=date.today(), partos=[], servicos=servicos, aplicacoes_iatf=[], pev_dias=45,
            del_max_1o_servico=None, eh_vaca=False, idade_dias=600,
        )


def _ficha(c, numero: str) -> dict:
    r = c.get(f"/animais/{numero}/ficha")
    assert r.status_code == 200
    return r.json()


def _lista(c, numero: str) -> dict:
    return next(a for a in c.get("/animais/").json() if a["numero"] == numero)


class TestCasoA_VaziaEmAtrasoComPrevisao:
    """43/460/467: texto "Novilha vazia em atraso" + previsão. A previsão vem do toque POSITIVO; o texto é o do CSV."""

    def test_toque_positivo_da_previsao_e_estado_gestante_mas_o_texto_do_csv_nao_muda(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="43", sexo="F", ativo=True, categoria_completa="Novilha vazia em atraso"))
            s.add(Servico(
                numero_matriz="43", data_servico=hoje - timedelta(days=36), tipo_servico="IA", protocolo="IATF",
                diagnostico="POSITIVO", data_diagnostico=hoje - timedelta(days=6), ult_ocorrencia=1,
            ))
            s.commit()
        assert _ficha(c, "43")["previsao_parto"] == (hoje - timedelta(days=36) + timedelta(days=280)).isoformat()
        assert _estado_ao_vivo(engine, "43")["estado"] == GESTANTE
        # O texto é do GERAL.csv: nenhum lançamento reprodutivo (exceto parto/aborto) o reescreve.
        assert _lista(c, "43")["categoria_completa"] == "Novilha vazia em atraso"

    def test_iatf_inseminada_sem_toque_nao_tem_previsao(self, client):
        """Regra do Jairo: inseminada tem expectativa, não previsão. Concluir o IATF (cria o Servico) não dá previsão."""
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="9321", sexo="F", ativo=True, categoria_completa="Novilha inseminada"))
            s.add(Servico(
                numero_matriz="9321", data_servico=hoje - timedelta(days=15), tipo_servico="IA", protocolo="IATF",
                ult_ocorrencia=1,
            ))
            s.commit()
        assert _ficha(c, "9321")["previsao_parto"] is None
        assert _estado_ao_vivo(engine, "9321")["estado"] == INSEMINADA


class TestCasoB_GestanteSemPrevisao:
    def test_texto_gestante_do_csv_sem_servico_positivo_no_app_nao_tem_previsao(self, client):
        """455: "Novilha gestante" vem do Ideagri; sem serviço POSITIVO no app não há de onde calcular a previsão."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="455", sexo="F", ativo=True, categoria_completa="Novilha gestante"))
            s.add(Servico(numero_matriz="455", data_servico=None, ult_ocorrencia=1))
            s.commit()
        assert _ficha(c, "455")["previsao_parto"] is None
        assert _lista(c, "455")["categoria_completa"] == "Novilha gestante"


class TestCasoC_SemCategoria:
    def test_animal_sem_texto_de_categoria_continua_sem_depois_de_inseminar(self, client):
        """10651/11415/11453: animal que nunca veio num GERAL.csv (cadastro/importação do app) não tem texto algum."""
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="10651", sexo="F", ativo=True, categoria_completa=None))
            s.add(Servico(
                numero_matriz="10651", data_servico=hoje - timedelta(days=15), tipo_servico="IA", protocolo="IATF",
                ult_ocorrencia=1,
            ))
            s.commit()
        assert _lista(c, "10651")["categoria_completa"] is None
        assert _estado_ao_vivo(engine, "10651")["estado"] == INSEMINADA


class TestCasoD_FichaDivergiaDoEstadoAoVivo:
    """Defeito de código: a Ficha usava "qualquer serviço do ciclo com toque POSITIVO" em vez do serviço vigente."""

    def test_reconfirmacao_negativa_sem_perda_nao_gera_previsao(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="D1", sexo="F", ativo=True, categoria_completa="Novilha gestante"))
            s.add(Servico(
                numero_matriz="D1", data_servico=hoje - timedelta(days=90), diagnostico="POSITIVO",
                data_diagnostico=hoje - timedelta(days=50), diagnostico_reconfirmacao="NEGATIVO",
                data_reconfirmacao=hoje - timedelta(days=10), ult_ocorrencia=1,
            ))
            s.commit()
        assert _estado_ao_vivo(engine, "D1")["estado"] != GESTANTE
        ficha = _ficha(c, "D1")
        assert ficha["previsao_parto"] is None
        assert ficha["precisao_parto"] is None

    def test_toque_positivo_antigo_com_servico_novo_sem_toque_nao_gera_previsao(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="D2", sexo="F", ativo=True, categoria_completa="Novilha inseminada"))
            s.add(Servico(
                numero_matriz="D2", data_servico=hoje - timedelta(days=90), diagnostico="POSITIVO",
                data_diagnostico=hoje - timedelta(days=50), ult_ocorrencia=0,
            ))
            s.add(Servico(numero_matriz="D2", data_servico=hoje - timedelta(days=20), ult_ocorrencia=1))
            s.commit()
        assert _estado_ao_vivo(engine, "D2")["estado"] == INSEMINADA
        assert _ficha(c, "D2")["previsao_parto"] is None

    def test_reconfirmacao_positiva_mantem_a_previsao(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="D3", sexo="F", ativo=True))
            s.add(Servico(
                numero_matriz="D3", data_servico=hoje - timedelta(days=70), diagnostico="POSITIVO",
                data_diagnostico=hoje - timedelta(days=35), diagnostico_reconfirmacao="POSITIVO",
                data_reconfirmacao=hoje - timedelta(days=5), ult_ocorrencia=1,
            ))
            s.commit()
        assert _estado_ao_vivo(engine, "D3")["estado"] == GESTANTE
        assert _ficha(c, "D3")["previsao_parto"] == (hoje - timedelta(days=70) + timedelta(days=280)).isoformat()

    def test_perda_registrada_nao_gera_previsao(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="D4", sexo="F", ativo=True))
            s.add(Servico(
                numero_matriz="D4", data_servico=hoje - timedelta(days=80), diagnostico="POSITIVO",
                data_diagnostico=hoje - timedelta(days=45), data_perda_prenhez=hoje - timedelta(days=3), ult_ocorrencia=1,
            ))
            s.commit()
        assert _ficha(c, "D4")["previsao_parto"] is None
