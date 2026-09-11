"""
Checklist da Ocorrência (Fase 1, passos 7-8 do redesenho do evento
sanitário) — fazenda.rules.checklist_sanitario, direto sobre uma sessão
sqlite em memória, sem HTTP.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import CalendarioSanitario, ChecklistTemplateItem, CronogramaSanitario, EventoSanitario
from fazenda.rules.checklist_sanitario import (
    ChecklistError,
    checklist_completo,
    confirmado,
    confirmar_horario,
    desconsiderar_cronograma,
    marcar_cumprido,
    marcar_lotes_revisado,
    marcar_pulado,
    materializar_checklist,
    responder_veterinario,
    tipo_template_do_evento,
)

AGORA = datetime(2026, 9, 11, 9, 0)

_TEMPLATE_VACINA = [
    (1, "estoque", "Estoque suficiente?"),
    (2, "vet", "Confirmação com o veterinário selecionado"),
    (3, "horario", "Horário da aplicação"),
    (4, "lotes", "Lotes de manejo atuais"),
    (5, "financeiro", "Lançamento financeiro"),
]
_TEMPLATE_EXAME = [
    (1, "vet", "Confirmação com o veterinário selecionado"),
    (2, "horario", "Horário da coleta/realização do exame"),
    (3, "lotes", "Lotes de manejo atuais"),
    (4, "financeiro", "Lançamento financeiro"),
]


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for ordem, chave, nome in _TEMPLATE_VACINA:
            s.add(ChecklistTemplateItem(tipo="vacina", chave=chave, nome=nome, ordem=ordem, fazenda_id=None))
        for ordem, chave, nome in _TEMPLATE_EXAME:
            s.add(ChecklistTemplateItem(tipo="exame", chave=chave, nome=nome, ordem=ordem, fazenda_id=None))
        s.commit()
        yield s


def _cronograma_vacina(session: Session) -> tuple[CronogramaSanitario, EventoSanitario]:
    evento = EventoSanitario(nome="Brucelose B19", tipo_agendamento="evento", categoria_preventiva="vacina")
    session.add(evento)
    session.commit()
    session.refresh(evento)
    regra = CalendarioSanitario(
        evento_sanitario_id=evento.id, categoria_alvo="Aleitamento", frequencia_valor=30, frequencia_unidade="dias",
        data_evento=date(2026, 9, 24),
    )
    session.add(regra)
    session.commit()
    session.refresh(regra)
    cron = CronogramaSanitario(calendario_sanitario_id=regra.id, data_evento=date(2026, 9, 24))
    session.add(cron)
    session.commit()
    session.refresh(cron)
    return cron, evento


def _cronograma_exame(session: Session) -> tuple[CronogramaSanitario, EventoSanitario]:
    evento = EventoSanitario(nome="Tuberculose", tipo_agendamento="epoca", categoria_preventiva="exame")
    session.add(evento)
    session.commit()
    session.refresh(evento)
    regra = CalendarioSanitario(
        evento_sanitario_id=evento.id, categoria_alvo="Rebanho todo", frequencia_valor=12, frequencia_unidade="meses",
        data_evento=date(2027, 7, 13),
    )
    session.add(regra)
    session.commit()
    session.refresh(regra)
    cron = CronogramaSanitario(calendario_sanitario_id=regra.id, data_evento=date(2027, 7, 13))
    session.add(cron)
    session.commit()
    session.refresh(cron)
    return cron, evento


class TestMaterializarChecklist:
    def test_vacina_ganha_5_itens_na_ordem_certa(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        assert [i.chave for i in itens] == ["estoque", "vet", "horario", "lotes", "financeiro"]
        assert all(i.status == "pendente" for i in itens)

    def test_exame_ganha_4_itens_sem_estoque(self, session):
        cron, evento = _cronograma_exame(session)
        itens = materializar_checklist(session, cron, evento)
        assert [i.chave for i in itens] == ["vet", "horario", "lotes", "financeiro"]

    def test_tratamento_usa_template_de_vacina(self, session):
        evento = EventoSanitario(nome="Vermífugo", tipo_agendamento="epoca", categoria_preventiva="tratamento")
        session.add(evento)
        session.commit()
        session.refresh(evento)
        assert tipo_template_do_evento(evento) == "vacina"

    def test_idempotente_nao_duplica_nem_reseta(self, session):
        cron, evento = _cronograma_vacina(session)
        itens1 = materializar_checklist(session, cron, evento)
        marcar_cumprido(session, itens1[0].id, usuario_id=1, hoje=AGORA)
        itens2 = materializar_checklist(session, cron, evento)
        assert len(itens2) == 5
        assert itens2[0].status == "cumprido"  # não voltou a "pendente"


class TestItensComComportamentoEspecial:
    def test_item_vet_sim_marca_cumprido(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        vet = next(i for i in itens if i.chave == "vet")
        atualizado = responder_veterinario(session, vet.id, "sim", None, usuario_id=1, hoje=AGORA)
        assert atualizado.status == "cumprido"
        assert atualizado.resposta == "sim"

    def test_item_vet_nao_exige_justificativa(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        vet = next(i for i in itens if i.chave == "vet")
        with pytest.raises(ChecklistError, match="Justificativa"):
            responder_veterinario(session, vet.id, "nao", None, usuario_id=1, hoje=AGORA)

    def test_item_vet_nao_com_justificativa_fica_cumprido_mas_com_alerta(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        vet = next(i for i in itens if i.chave == "vet")
        atualizado = responder_veterinario(session, vet.id, "nao", "vacina em falta no distribuidor", usuario_id=1, hoje=AGORA)
        assert atualizado.status == "cumprido"  # conta como cumprido — não bloqueia
        assert atualizado.observacao == "vacina em falta no distribuidor"
        from fazenda.rules.checklist_sanitario import alerta_clinico_ativo
        assert alerta_clinico_ativo(session, cron.id) is True

    def test_item_vet_resposta_invalida_rejeitada(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        vet = next(i for i in itens if i.chave == "vet")
        with pytest.raises(ChecklistError):
            responder_veterinario(session, vet.id, "talvez", None, usuario_id=1, hoje=AGORA)

    def test_item_horario_exige_valor_nao_vazio(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        horario = next(i for i in itens if i.chave == "horario")
        with pytest.raises(ChecklistError):
            confirmar_horario(session, horario.id, "", usuario_id=1, hoje=AGORA)
        atualizado = confirmar_horario(session, horario.id, "09:30", usuario_id=1, hoje=AGORA)
        assert atualizado.status == "cumprido"
        assert atualizado.resposta == "09:30"

    def test_item_lotes_marcar_revisado(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        lotes = next(i for i in itens if i.chave == "lotes")
        atualizado = marcar_lotes_revisado(session, lotes.id, usuario_id=1, hoje=AGORA)
        assert atualizado.status == "cumprido"

    def test_confirmar_horario_no_item_errado_e_rejeitado(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        estoque = next(i for i in itens if i.chave == "estoque")
        with pytest.raises(ChecklistError, match='"horario"'):
            confirmar_horario(session, estoque.id, "09:30", usuario_id=1, hoje=AGORA)

    def test_pular_disponivel_em_qualquer_item_inclusive_financeiro(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        financeiro = next(i for i in itens if i.chave == "financeiro")
        atualizado = marcar_pulado(session, financeiro.id, "sem custo nesta aplicação", usuario_id=1, hoje=AGORA)
        assert atualizado.status == "pulado"
        assert atualizado.observacao == "sem custo nesta aplicação"


class TestChecklistCompletoEConfirmado:
    def test_vazio_nao_conta_como_completo(self, session):
        cron, _ = _cronograma_vacina(session)
        assert checklist_completo(session, cron.id) is False

    def test_completo_só_quando_tudo_cumprido_ou_pulado(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        for item in itens[:-1]:
            marcar_cumprido(session, item.id, usuario_id=1, hoje=AGORA)
        assert checklist_completo(session, cron.id) is False
        marcar_pulado(session, itens[-1].id, None, usuario_id=1, hoje=AGORA)
        assert checklist_completo(session, cron.id) is True

    def test_confirmado_via_checklist_completo(self, session):
        cron, evento = _cronograma_vacina(session)
        itens = materializar_checklist(session, cron, evento)
        for item in itens:
            marcar_pulado(session, item.id, None, usuario_id=1, hoje=AGORA)
        assert confirmado(session, cron) is True

    def test_confirmado_via_desconsiderar_sem_checklist(self, session):
        cron, evento = _cronograma_vacina(session)
        materializar_checklist(session, cron, evento)  # nasce, nada respondido
        assert confirmado(session, cron) is False
        desconsiderar_cronograma(session, cron, "cliente pediu urgência", AGORA)
        assert confirmado(session, cron) is True

    def test_desconsiderar_bloqueado_apos_realizado(self, session):
        cron, _ = _cronograma_vacina(session)
        cron.status = "concluido"
        session.add(cron)
        session.commit()
        with pytest.raises(ChecklistError, match="já foi realizada"):
            desconsiderar_cronograma(session, cron, None, AGORA)
