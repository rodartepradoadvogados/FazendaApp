"""
`reabrir()` — Fase 0, passo 4 do redesenho do evento sanitário (R "Confirmado
→ Em edição", sem limite, até Realizado — nunca a partir de "concluido").
Teste direto sobre `fazenda.rules.cronograma_sanitario`, sem HTTP: constrói
os objetos SQLModel na mão numa sessão sqlite em memória.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import CalendarioSanitario, CronogramaSanitario, EventoSanitario, Pessoa
from fazenda.rules.cronograma_sanitario import CronogramaError, adiar, decidir_modo, reabrir


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _regra_e_cronograma(session: Session, status: str = "aberto") -> CronogramaSanitario:
    evento = EventoSanitario(nome="Vermífugo", tipo_agendamento="epoca")
    session.add(evento)
    session.commit()
    session.refresh(evento)

    regra = CalendarioSanitario(
        evento_sanitario_id=evento.id, categoria_alvo="Bezerras", frequencia_valor=4, frequencia_unidade="meses",
        data_evento=date(2026, 9, 15), usa_cronograma=True,
    )
    session.add(regra)
    session.commit()
    session.refresh(regra)

    cron = CronogramaSanitario(calendario_sanitario_id=regra.id, data_evento=date(2026, 9, 15), status=status)
    session.add(cron)
    session.commit()
    session.refresh(cron)
    return cron


class TestReabrir:
    def test_reabre_agendado_para_aberto_sem_mudar_data(self, session):
        cron = _regra_e_cronograma(session, status="agendado")
        cron.modo_execucao = "propria"
        session.add(cron)
        session.commit()
        data_antes = cron.data_evento

        reaberto = reabrir(session, cron)

        assert reaberto.status == "aberto"
        assert reaberto.modo_execucao is None
        assert reaberto.veterinario_pessoa_id is None
        assert reaberto.data_evento == data_antes  # nunca muda a data — diferença chave vs. adiar()

    def test_reabrir_com_motivo_registra_na_observacao(self, session):
        cron = _regra_e_cronograma(session, status="agendado")
        reaberto = reabrir(session, cron, motivo="entrou mais um animal na janela")
        assert "Reaberto: entrou mais um animal na janela" in reaberto.observacao

    def test_reabrir_ja_aberto_e_idempotente(self, session):
        cron = _regra_e_cronograma(session, status="aberto")
        reaberto = reabrir(session, cron)
        assert reaberto.status == "aberto"
        assert reaberto is cron

    def test_reabrir_concluido_e_bloqueado(self, session):
        cron = _regra_e_cronograma(session, status="concluido")
        with pytest.raises(CronogramaError, match="não é possível reabrir"):
            reabrir(session, cron)
        assert cron.status == "concluido"  # nunca muda

    def test_reabrir_cancelado_e_bloqueado(self, session):
        cron = _regra_e_cronograma(session, status="cancelado")
        with pytest.raises(CronogramaError, match="não é possível reabrir"):
            reabrir(session, cron)

    def test_reabrir_preserva_veterinario_agendado_via_decidir_modo(self, session):
        # decidir_modo leva a "agendado"; reabrir devolve a "aberto" sem
        # mudar a data — cenário real: usuário confirmou veterinário, depois
        # precisou reabrir para ajustar o checklist antes da aplicação.
        cron = _regra_e_cronograma(session, status="aberto")
        vet = Pessoa(nome="Huerik Almeida", tipo="Veterinário")
        session.add(vet)
        session.commit()
        session.refresh(vet)

        cron = decidir_modo(session, cron, "veterinario", vet.id)
        assert cron.status == "agendado"

        cron = reabrir(session, cron)
        assert cron.status == "aberto"
        assert cron.veterinario_pessoa_id is None

    def test_diferenca_chave_vs_adiar_muda_data(self, session):
        cron = _regra_e_cronograma(session, status="agendado")
        nova_data = date(2026, 10, 1)
        adiado = adiar(session, cron, nova_data, motivo=None)
        assert adiado.status == "aberto"
        assert adiado.data_evento == nova_data
        assert adiado.data_original == date(2026, 9, 15)
