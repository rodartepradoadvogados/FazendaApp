"""
Quem pode o quê no Sanitário Preventivo v2 (plano, convenções gerais):

  - ADMINISTRADOR DA FAZENDA = `Usuario.papel == "admin"`, OU o vínculo
    `UsuarioFazenda.contratante` desta fazenda, OU o dono-equivalente. Só ele
    cadastra caixa, escolhe o modo de carência/aceite, estorna e resolve as
    notas de administrador.
  - VETERINÁRIO = o usuário cuja Pessoa (Cadastros › Pessoas) tem a função
    "Veterinário". Ele lança a leitura de exame; o administrador também pode,
    desde que informe o veterinário responsável.
  - Operador/veterinário lançam (registrar, dia, app).
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from fazenda.rules.sanitario.definicao import normalizar


def eh_admin_fazenda(session: Session, usuario, fazenda_id: Optional[int]) -> bool:
    from fazenda.auth import eh_email_dono_equivalente
    from fazenda.models import UsuarioFazenda

    if usuario is None:
        return False
    if getattr(usuario, "papel", None) == "admin" or eh_email_dono_equivalente(getattr(usuario, "email", None)):
        return True
    if fazenda_id is None:
        return False
    vinculo = session.exec(select(UsuarioFazenda).where(
        UsuarioFazenda.usuario_id == usuario.id, UsuarioFazenda.fazenda_id == fazenda_id,
    )).first()
    return bool(vinculo and vinculo.contratante)


def eh_tipo_veterinario(tipo: Optional[str]) -> bool:
    return "veterinari" in normalizar(tipo)


def pessoa_veterinaria_do_usuario(session: Session, usuario, fazenda_id: Optional[int]):
    """A Pessoa do usuário, se ela for veterinária (desta fazenda)."""
    from fazenda.models import Pessoa

    pid = getattr(usuario, "pessoa_id", None)
    if not pid:
        return None
    p = session.get(Pessoa, pid)
    if p is None or not eh_tipo_veterinario(p.tipo):
        return None
    if fazenda_id is not None and p.fazenda_id not in (None, fazenda_id):
        return None
    return p


def veterinarios_da_fazenda(session: Session, fazenda_id: int) -> list:
    from fazenda.models import Pessoa

    pessoas = session.exec(select(Pessoa).where(Pessoa.fazenda_id == fazenda_id, Pessoa.ativo == True)  # noqa: E712
                           .order_by(Pessoa.nome)).all()
    return [p for p in pessoas if eh_tipo_veterinario(p.tipo)]


def admins_da_fazenda(session: Session, fazenda_id: int) -> set[int]:
    """IDs dos usuários ATIVOS administradores desta fazenda (vinculados a ela)."""
    from fazenda.models import Usuario, UsuarioFazenda

    out: set[int] = set()
    for vinc, u in session.exec(select(UsuarioFazenda, Usuario).where(
        UsuarioFazenda.fazenda_id == fazenda_id, UsuarioFazenda.usuario_id == Usuario.id, Usuario.ativo == True,  # noqa: E712
    )).all():
        if vinc.contratante or u.papel == "admin":
            out.add(u.id)
    return out


def usuarios_da_fazenda(session: Session, fazenda_id: int) -> set[int]:
    """Todos os usuários ativos vinculados à fazenda (os "usuários do app")."""
    from fazenda.models import Usuario, UsuarioFazenda

    return set(session.exec(select(Usuario.id).where(
        UsuarioFazenda.fazenda_id == fazenda_id, UsuarioFazenda.usuario_id == Usuario.id,
        Usuario.ativo == True,  # noqa: E712
    )).all())
