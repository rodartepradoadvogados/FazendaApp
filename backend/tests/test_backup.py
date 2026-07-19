"""
Testes do backup automatizado (fazenda.rules.backup) — item crítico da
auditoria: antes só existia exportação manual sob demanda (Portal >
Exportar). Cobre: geração do ZIP com um CSV por tabela, o intervalo semanal
(não roda de novo antes da hora) e o registro de falha quando o envio de
e-mail dá erro (ex.: RESEND_API_KEY não configurada).
"""
from __future__ import annotations

import zipfile
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.rules.backup as backup_module
from fazenda.models import Animal, BackupAutomatico


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


def test_gerar_backup_zip_inclui_dados_reais(engine):
    with Session(engine) as session:
        session.add(Animal(numero="123", categoria_abrev="Vaca", sexo="F", ativo=True))
        session.commit()

    with Session(engine) as session:
        zip_bytes = backup_module.gerar_backup_zip(session)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        nomes = zf.namelist()
        assert "animal.csv" in nomes
        conteudo = zf.read("animal.csv").decode("utf-8-sig")
        assert "123" in conteudo


def test_executar_backup_roda_na_primeira_vez_e_envia_email(engine, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        backup_module, "enviar_email",
        lambda destinatario, assunto, corpo, anexo_nome, anexo_bytes: chamadas.append((destinatario, anexo_nome, anexo_bytes)),
    )

    with Session(engine) as session:
        rodou = backup_module.executar_backup_se_necessario(session)

    assert rodou is True
    assert len(chamadas) == 1
    destinatario, anexo_nome, anexo_bytes = chamadas[0]
    assert destinatario == backup_module.EMAIL_DONO
    assert anexo_nome.endswith(".zip")
    assert len(anexo_bytes) > 0

    with Session(engine) as session:
        registros = session.exec(select_backup_automatico()).all()
        assert len(registros) == 1
        assert registros[0].sucesso is True


def test_executar_backup_nao_roda_de_novo_antes_do_intervalo(engine, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        backup_module, "enviar_email",
        lambda *a, **k: chamadas.append(1),
    )

    with Session(engine) as session:
        session.add(BackupAutomatico(executado_em=datetime.utcnow() - timedelta(days=1), sucesso=True))
        session.commit()

        rodou = backup_module.executar_backup_se_necessario(session)

    assert rodou is False
    assert chamadas == []


def test_executar_backup_roda_de_novo_apos_o_intervalo(engine, monkeypatch):
    chamadas = []
    monkeypatch.setattr(backup_module, "enviar_email", lambda *a, **k: chamadas.append(1))

    with Session(engine) as session:
        session.add(BackupAutomatico(
            executado_em=datetime.utcnow() - timedelta(days=backup_module.INTERVALO_DIAS, hours=1), sucesso=True,
        ))
        session.commit()

        rodou = backup_module.executar_backup_se_necessario(session)

    assert rodou is True
    assert len(chamadas) == 1


def test_executar_backup_registra_falha_sem_derrubar_e_tenta_de_novo_na_proxima(engine, monkeypatch):
    def _falha(*a, **k):
        raise RuntimeError("RESEND_API_KEY não configurada")

    monkeypatch.setattr(backup_module, "enviar_email", _falha)

    with Session(engine) as session:
        rodou = backup_module.executar_backup_se_necessario(session)
        assert rodou is False  # não conseguiu completar

    with Session(engine) as session:
        registros = session.exec(select_backup_automatico()).all()
        assert len(registros) == 1
        assert registros[0].sucesso is False
        assert "RESEND_API_KEY" in registros[0].erro

        # Uma falha NÃO atrasa a próxima tentativa — só um sucesso conta pro intervalo.
        monkeypatch.setattr(backup_module, "enviar_email", lambda *a, **k: None)
        rodou_de_novo = backup_module.executar_backup_se_necessario(session)
        assert rodou_de_novo is True


def select_backup_automatico():
    from sqlmodel import select
    return select(BackupAutomatico)
