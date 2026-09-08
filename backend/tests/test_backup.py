"""
Testes do backup automatizado (fazenda.rules.backup) — item crítico da
auditoria: antes só existia exportação manual sob demanda (Portal >
Exportar). Cobre: geração do ZIP com um CSV por tabela, o intervalo semanal
(não roda de novo antes da hora), o registro de falha quando o envio de
e-mail dá erro (ex.: RESEND_API_KEY não configurada) e a guarda contra o
backup que sai vazio e se carimba de bem-sucedido.
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
    """Banco com UMA linha em tabela que tem `fazenda_id`.

    Isso não é detalhe de arrumação: desde a guarda do backup vazio, um banco
    sem nenhuma linha dessas é tratado como falha — e é isso que se quer, já
    que banco de produção nenhum está assim. Os testes de caminho feliz
    precisam, portanto, de um banco com dado, como o real."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        session.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", ativo=True, fazenda_id=1))
        session.commit()
    return eng


@pytest.fixture
def engine_vazio():
    """Banco com o schema montado e NENHUMA linha — o retrato do que o RLS
    produz quando a política nega tudo: SELECT sem erro, devolvendo vazio."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


def test_gerar_backup_zip_inclui_dados_reais(engine):
    with Session(engine) as session:
        session.add(Animal(numero="123", categoria_abrev="Vaca", sexo="F", ativo=True))
        session.commit()

    with Session(engine) as session:
        zip_bytes, linhas = backup_module.gerar_backup_zip(session)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        nomes = zf.namelist()
        assert "animal.csv" in nomes
        conteudo = zf.read("animal.csv").decode("utf-8-sig")
        assert "123" in conteudo

    # a contagem que a guarda usa: as duas linhas de `animal` (a da fixture e a
    # deste teste), ambas em tabela com `fazenda_id`
    assert linhas == 2


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


# ---------------------------------------------------------------------------
# A guarda do backup vazio.
#
# Este é o modo de falha que o RLS cria e que nenhum `except` pegaria: sob uma
# política que nega tudo, o SELECT não levanta exceção — devolve zero linha.
# Sem a guarda, o caminho feliz roda inteiro (e-mail enviado, `sucesso=True`
# gravado) e a próxima tentativa só viria daí a INTERVALO_DIAS. Backup vazio é
# pior que backup nenhum: dá falsa segurança até o dia de restaurar.
# ---------------------------------------------------------------------------


def test_backup_vazio_nao_e_enviado_e_registra_falha(engine_vazio, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        backup_module, "enviar_email",
        lambda destinatario, assunto, corpo, anexo_nome=None, anexo_bytes=None: enviados.append(
            (assunto, anexo_nome)
        ),
    )

    with Session(engine_vazio) as session:
        rodou = backup_module.executar_backup_se_necessario(session)

    assert rodou is True  # rodou, e falhou — não é "ainda não é hora"

    with Session(engine_vazio) as session:
        registros = session.exec(select_backup_automatico()).all()
        assert len(registros) == 1
        assert registros[0].sucesso is False, (
            "backup sem uma linha sequer não pode ser gravado como sucesso"
        )
        assert "vazio" in registros[0].erro.lower()

    assert len(enviados) == 1, "o dono precisa ser avisado — o silêncio é o problema"
    assunto, anexo_nome = enviados[0]
    assert "FALHOU" in assunto
    assert anexo_nome is None, "não se manda um ZIP oco como se fosse backup"


def test_backup_vazio_nao_atrasa_a_proxima_tentativa(engine_vazio, monkeypatch):
    """A falha por vazio não pode contar como rodada boa: se contasse, o
    intervalo de INTERVALO_DIAS seguraria a próxima tentativa e o sistema
    ficaria uma semana sem backup por causa de um problema que pode durar
    minutos."""
    monkeypatch.setattr(backup_module, "enviar_email", lambda *a, **k: None)

    with Session(engine_vazio) as session:
        backup_module.executar_backup_se_necessario(session)
        # o dado volta a aparecer (contexto restaurado, permissão corrigida...)
        session.add(Animal(numero="7", categoria_abrev="Vaca", sexo="F", ativo=True, fazenda_id=1))
        session.commit()

        rodou_de_novo = backup_module.executar_backup_se_necessario(session)

    assert rodou_de_novo is True

    with Session(engine_vazio) as session:
        registros = session.exec(select_backup_automatico()).all()
        assert [r.sucesso for r in registros] == [False, True]


def test_a_conta_ignora_tabela_sem_fazenda_id(engine_vazio, monkeypatch):
    """Detalhe que decide se a guarda funciona sob RLS de verdade.

    As políticas só entram nas tabelas COM `fazenda_id`; as outras (o próprio
    `backup_automatico`, entre elas) continuam visíveis. Se a conta fosse do
    total de linhas do banco, o registro da rodada anterior de backup já
    bastaria para o total não ser zero — e a guarda nunca dispararia justamente
    no cenário para o qual foi feita."""
    monkeypatch.setattr(backup_module, "enviar_email", lambda *a, **k: None)

    with Session(engine_vazio) as session:
        # linhas em tabela SEM fazenda_id não contam como conteúdo de backup
        session.add(BackupAutomatico(executado_em=datetime.utcnow() - timedelta(days=30), sucesso=False))
        session.commit()

        _, linhas = backup_module.gerar_backup_zip(session)
        assert linhas == 0

        backup_module.executar_backup_se_necessario(session)

    with Session(engine_vazio) as session:
        registros = session.exec(select_backup_automatico()).all()
        assert registros[-1].sucesso is False
