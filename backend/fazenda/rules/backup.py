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


def gerar_backup_zip(session: Session) -> tuple[bytes, int]:
    """Um CSV por tabela do schema atual, zipado. Usa SELECT direto na Table
    (SQLAlchemy Core) em vez dos modelos ORM — funciona igual para qualquer
    tabela nova, sem precisar manter uma lista manual atualizada.

    Devolve o ZIP e, junto, quantas linhas saíram das tabelas COM `fazenda_id`
    — a contagem que `executar_backup_se_necessario` usa para saber se o
    backup tem conteúdo ou é um monte de cabeçalho. São essas as tabelas que o
    RLS recorta, e por isso são elas que a conta olha: uma política que negue
    tudo deixa exatamente essas zeradas, sem erro nenhum.
    """
    buffer_zip = io.BytesIO()
    linhas_com_fazenda = 0
    with zipfile.ZipFile(buffer_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for tabela in SQLModel.metadata.sorted_tables:
            linhas = [dict(row) for row in session.execute(select(tabela)).mappings().all()]
            if "fazenda_id" in tabela.columns:
                linhas_com_fazenda += len(linhas)
            zf.writestr(f"{tabela.name}.csv", _linhas_para_csv(linhas).encode("utf-8-sig"))
    return buffer_zip.getvalue(), linhas_com_fazenda


ERRO_BACKUP_VAZIO = (
    "Backup vazio: nenhuma linha saiu das tabelas com fazenda_id. Um banco de "
    "produção nunca está assim. A causa mais provável é a sessão não estar "
    "enxergando o dado (permissão do usuário do banco, ou política de RLS "
    "negando por falta de contexto de fazenda) — o SELECT não dá erro, devolve "
    "vazio. Backup NÃO enviado."
)


def _registrar_backup_vazio(session: Session) -> bool:
    """O backup saiu só com cabeçalho — grava falha e avisa, em vez de mandar
    um ZIP oco carimbado de sucesso.

    Este é o modo de falha que o RLS cria e que o `except Exception` do loop de
    `main.py` NÃO pegaria: sob uma política que nega tudo, o `SELECT` não
    levanta exceção, devolve zero linha. Sem esta guarda, o caminho feliz roda
    inteiro — e-mail enviado, `sucesso=True` gravado — e a próxima tentativa só
    viria em `INTERVALO_DIAS`. Backup vazio é pior que backup nenhum, porque dá
    falsa segurança até o dia de restaurar.
    """
    session.add(BackupAutomatico(sucesso=False, erro=ERRO_BACKUP_VAZIO[:500]))
    session.commit()
    try:
        enviar_email(
            EMAIL_DONO,
            f"Backup automático FALHOU — banco veio vazio ({datetime.utcnow():%d/%m/%Y})",
            f"<p><strong>O backup automático não foi enviado.</strong></p><p>{ERRO_BACKUP_VAZIO}</p>",
        )
    except Exception:  # noqa: BLE001 — o registro da falha acima já foi gravado; o aviso é o extra
        pass
    return True


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
        zip_bytes, linhas = gerar_backup_zip(session)
        if linhas == 0:
            return _registrar_backup_vazio(session)
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
