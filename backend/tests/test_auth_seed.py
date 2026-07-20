"""
Seed do admin inicial e backfill do e-mail do proprietário — a aba "Acessos e
Auditoria" (site e app) e outras permissões restritas a EMAIL_DONO (ex.:
publicar matérias no blog) dependem do e-mail do usuário bater exatamente com
EMAIL_DONO (fazenda.auth.exigir_dono/eh_dono). Bancos criados antes desta
mudança tinham o admin inicial sem e-mail, deixando essas telas invisíveis
mesmo sendo o único usuário do sistema — ver seed_email_dono_backfill.
"""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import EMAIL_DONO, hash_senha, seed_admin, seed_email_dono_backfill
from fazenda.models import SeedFlag, Usuario


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_seed_admin_ja_nasce_com_email_dono():
    engine = _engine()
    with Session(engine) as s:
        seed_admin(s)

    with Session(engine) as s:
        admin = s.exec(select(Usuario)).first()
        assert admin.email == EMAIL_DONO


def test_backfill_preenche_email_de_usuario_unico_sem_email():
    engine = _engine()
    with Session(engine) as s:
        s.add(Usuario(username="AlexandreRodarte", nome="Alexandre Rodarte", senha_hash=hash_senha("x"), papel="admin"))
        s.commit()

    with Session(engine) as s:
        seed_email_dono_backfill(s)

    with Session(engine) as s:
        admin = s.exec(select(Usuario)).first()
        assert admin.email == EMAIL_DONO


def test_backfill_nao_roda_de_novo_se_email_for_trocado_depois():
    """Uma vez aplicado (SeedFlag), a migração nunca reaplica — o proprietário
    pode trocar o próprio e-mail depois sem que o backfill reverta."""
    engine = _engine()
    with Session(engine) as s:
        s.add(Usuario(username="AlexandreRodarte", nome="Alexandre Rodarte", senha_hash=hash_senha("x"), papel="admin"))
        s.commit()

    with Session(engine) as s:
        seed_email_dono_backfill(s)

    with Session(engine) as s:
        admin = s.exec(select(Usuario)).first()
        admin.email = "outro@exemplo.com"
        s.add(admin)
        s.commit()

    with Session(engine) as s:
        seed_email_dono_backfill(s)

    with Session(engine) as s:
        admin = s.exec(select(Usuario)).first()
        assert admin.email == "outro@exemplo.com"


def test_backfill_preenche_mesmo_com_varios_usuarios_cadastrados():
    """Um sistema em produção real já tem vários usuários (operadores,
    veterinário, funcionários) — o backfill precisa identificar o dono pelo
    `username` (ADMIN_USER), não pela contagem total de usuários."""
    engine = _engine()
    with Session(engine) as s:
        s.add(Usuario(username="AlexandreRodarte", nome="Alexandre Rodarte", senha_hash=hash_senha("x"), papel="admin"))
        s.add(Usuario(username="operador", nome="Operador", senha_hash=hash_senha("x"), papel="operador"))
        s.commit()

    with Session(engine) as s:
        seed_email_dono_backfill(s)

    with Session(engine) as s:
        admin = s.exec(select(Usuario).where(Usuario.username == "AlexandreRodarte")).first()
        assert admin.email == EMAIL_DONO
        operador = s.exec(select(Usuario).where(Usuario.username == "operador")).first()
        assert operador.email is None


def test_backfill_nao_sobrescreve_email_ja_preenchido():
    engine = _engine()
    with Session(engine) as s:
        s.add(Usuario(username="AlexandreRodarte", nome="Alexandre Rodarte", senha_hash=hash_senha("x"), papel="admin", email="ja@tinha.com"))
        s.commit()

    with Session(engine) as s:
        seed_email_dono_backfill(s)

    with Session(engine) as s:
        admin = s.exec(select(Usuario)).first()
        assert admin.email == "ja@tinha.com"


def test_backfill_grava_seedflag_e_nao_reaplica():
    engine = _engine()
    with Session(engine) as s:
        s.add(Usuario(username="AlexandreRodarte", nome="Alexandre Rodarte", senha_hash=hash_senha("x"), papel="admin"))
        s.commit()

    with Session(engine) as s:
        seed_email_dono_backfill(s)
        assert s.get(SeedFlag, "email_dono_backfill_por_username_202607b") is not None
