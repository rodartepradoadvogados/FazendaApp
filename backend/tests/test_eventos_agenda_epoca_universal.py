"""
`eventos_agenda()` (fazenda.rules.cronograma_sanitario) atrás da feature flag
`usar_ocorrencia_universal` (R-1, Fase 1 do redesenho do evento sanitário) —
regra por ÉPOCA sem `usa_cronograma=True` só ganha cronograma/sugestão
automática de animal quando a fazenda liga a flag; com a flag desligada
(padrão), o comportamento é idêntico ao de hoje.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, CalendarioSanitario, CategoriaManejo, CronogramaSanitarioAnimal, EventoSanitario, ParametroFazenda,
)
from fazenda.rules.cronograma_sanitario import eventos_agenda
from fazenda.rules.parametros import fazenda_atual

HOJE = date(2026, 9, 11)


@pytest.fixture
def cenario(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        # Bezerra com 100 dias hoje — bate a categoria "Novilha" (91-730 dias).
        s.add(Animal(numero="55", data_nasc=HOJE - timedelta(days=100), ativo=True, sexo="F"))
        s.add(CategoriaManejo(nome="Novilha", dia_min=91, dia_max=730, ordem=1))

        evento = EventoSanitario(nome="Vermífugo", tipo_agendamento="nenhum")  # nunca tocado pelo modo época
        s.add(evento)
        s.commit()
        s.refresh(evento)

        regra = CalendarioSanitario(
            evento_sanitario_id=evento.id, categoria_alvo="Novilha", frequencia_valor=4, frequencia_unidade="meses",
            data_evento=HOJE, usa_cronograma=False,  # nunca marcada — só a flag deve ligar isto
        )
        s.add(regra)
        s.commit()
        s.refresh(regra)
        regra_id = regra.id

    monkeypatch.setattr(database, "engine", engine)
    yield engine, regra_id
    fazenda_atual.set(None)


class TestEventosAgendaEpocaUniversal:
    def test_flag_desligada_regra_sem_cronograma_nao_aparece(self, cenario):
        engine, regra_id = cenario
        fazenda_atual.set(None)
        with Session(engine) as s:
            saida = eventos_agenda(s, HOJE, set())
        assert saida == []

    def test_flag_ligada_regra_ganha_cronograma_e_animal_sugerido(self, cenario):
        engine, regra_id = cenario
        with Session(engine) as s:
            s.add(ParametroFazenda(chave="usar_ocorrencia_universal", fazenda_id=None, grupo="sanidade",
                                    label="Universalizar Ocorrência", valor="true", tipo="bool"))
            s.commit()
        fazenda_atual.set(None)

        with Session(engine) as s:
            saida = eventos_agenda(s, HOJE, set())

        # Card de decisão de modo (trilha 2) tem que existir — a regra ganhou
        # cronograma mesmo sem usa_cronograma=True.
        assert any(e["tipo"] in ("cronograma_sanitario_modo", "cronograma_sanitario_urgente") for e in saida)
        # Animal 55 (Novilha, projeção só precisa da idade de hoje aqui) tem
        # que ter entrado "sugerido" — card da trilha 1.
        cards_animal = [e for e in saida if e["tipo"] == "cronograma_sanitario_animal"]
        assert any(c["numero_animal"] == "55" for c in cards_animal)

        with Session(engine) as s:
            linhas = s.exec(select(CronogramaSanitarioAnimal)).all()
        assert any(l.numero_matriz == "55" and l.status == "sugerido" for l in linhas)

    def test_flag_ligada_nao_toca_regra_por_evento_de_vida(self, cenario):
        """Regra por evento de vida (tipo_agendamento == "evento") não pode
        ganhar sugestão pelo caminho novo — continua exclusiva de
        fazenda.rules.eventos_sanitarios, mesmo com a flag ligada."""
        engine, _ = cenario
        with Session(engine) as s:
            s.add(ParametroFazenda(chave="usar_ocorrencia_universal", fazenda_id=None, grupo="sanidade",
                                    label="Universalizar Ocorrência", valor="true", tipo="bool"))
            evento_vida = EventoSanitario(nome="Brucelose B19", tipo_agendamento="evento", gatilho="nascimento")
            s.add(evento_vida)
            s.commit()
            s.refresh(evento_vida)
            regra_vida = CalendarioSanitario(
                evento_sanitario_id=evento_vida.id, categoria_alvo="Novilha",
                frequencia_valor=30, frequencia_unidade="dias", data_evento=HOJE, usa_cronograma=False,
            )
            s.add(regra_vida)
            s.commit()

        fazenda_atual.set(None)
        with Session(engine) as s:
            saida = eventos_agenda(s, HOJE, set())

        # A regra por evento de vida ganha o card de decisão de modo (a
        # generalização da flag vale pra ISSO), mas NENHUM animal sugerido
        # pelo caminho de projeção por época — o animal 55 só pode ter
        # entrado pela regra "Novilha" por época, não pela de Brucelose.
        cards_animal_brucelose = [
            e for e in saida
            if e["tipo"] == "cronograma_sanitario_animal" and "Brucelose" in e["descricao"]
        ]
        assert cards_animal_brucelose == []
