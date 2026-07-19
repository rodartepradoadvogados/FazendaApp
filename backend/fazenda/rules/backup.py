"""
Backup automatizado do banco de dados — antes só existia exportação manual
sob demanda (ver fazenda.api.routers.portal, EXPORT_CATALOG). Este módulo
gera um ZIP com um CSV por TABELA do schema atual (SQLModel.metadata —
schema inteiro, não só uma lista curada de tabelas "de negócio") e envia por
e-mail ao proprietário (EMAIL_DONO) via Resend, uma vez por semana.

Limitação conhecida: Resend tem limite de tamanho de anexo por e-mail (documentado
em ~40MB); se o banco crescer além disso, este mecanismo para de funcionar e
seria preciso migrar para backup em armazenamento externo (S3 ou equivalente,
que tem custo). O próprio e-mail de erro (ver `executar_backup_se_necessario`)
avisa nesse caso, em vez de falhar silenciosamente.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta

from sqlmodel import Session, select

from fazenda.auth import EMAIL_DONO
from fazenda.models import BackupAutomatico, SQLModel
from fazenda.rules.email import enviar_email

INTERVALO_DIAS = 7


def _linhas_para_csv(linhas: list[dict]) -> str:
    if not linhas:
        return ""
    colunas = list(linhas[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=colunas, extrasaction="ignore")
    writer.writeheader()
    for linha in linhas:
        writer.writerow(linha)
    return buffer.getvalue()


def gerar_backup_zip(session: Session) -> bytes:
    """Um CSV por tabela do schema atual, zipado. Usa SELECT direto na Table
    (SQLAlchemy Core) em vez dos modelos ORM — funciona igual para qualquer
    tabela nova, sem precisar manter uma lista manual atualizada."""
    buffer_zip = io.BytesIO()
    with zipfile.ZipFile(buffer_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for tabela in SQLModel.metadata.sorted_tables:
            colunas = [c.name for c in tabela.columns]
            linhas = [dict(row) for row in session.execute(select(tabela)).mappings().all()]
            zf.writestr(f"{tabela.name}.csv", _linhas_para_csv(linhas).encode("utf-8-sig"))
    return buffer_zip.getvalue()


def executar_backup_se_necessario(session: Session) -> bool:
    """Roda o backup e envia por e-mail se já se passaram `INTERVALO_DIAS`
    desde o último backup COM SUCESSO (uma falha não atrasa a próxima
    tentativa). Retorna True se rodou (com sucesso ou não), False se ainda
    não é hora."""
    ultimo_ok = session.exec(
        select(BackupAutomatico).where(BackupAutomatico.sucesso == True)  # noqa: E712
        .order_by(BackupAutomatico.executado_em.desc())
    ).first()
    if ultimo_ok and datetime.utcnow() - ultimo_ok.executado_em < timedelta(days=INTERVALO_DIAS):
        return False

    try:
        zip_bytes = gerar_backup_zip(session)
        nome_arquivo = f"backup_fazenda_{datetime.utcnow():%Y-%m-%d}.zip"
        enviar_email(
            EMAIL_DONO,
            f"Backup automático da fazenda — {datetime.utcnow():%d/%m/%Y}",
            "<p>Segue em anexo o backup semanal completo do banco de dados "
            "(uma planilha CSV por tabela do sistema, dentro do ZIP).</p>",
            nome_arquivo,
            zip_bytes,
        )
        session.add(BackupAutomatico(sucesso=True))
        session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — nunca deixa o boot da aplicação cair por causa do backup
        session.add(BackupAutomatico(sucesso=False, erro=str(exc)[:500]))
        session.commit()
        return False
