"""Resolução de `usuario_id` (quem fez o lançamento) para nome de exibição.

Usado pelos endpoints de listagem para anexar `usuario_nome` em cada linha,
sem precisar de um join manual repetido em cada router.
"""
from __future__ import annotations

from sqlmodel import Session, select

from fazenda.models import Usuario


def mapa_usuarios(session: Session, ids: set) -> dict:
    """Retorna {usuario_id: nome_de_exibicao} para os ids informados.

    Usa `nome` quando cadastrado, senão cai para `username`.
    """
    ids_validos = {i for i in ids if i}
    if not ids_validos:
        return {}
    usuarios = session.exec(select(Usuario).where(Usuario.id.in_(ids_validos))).all()
    return {u.id: (u.nome or u.username) for u in usuarios}


def usuario_id_seguro(user) -> int | None:
    """Resolve o id do usuário logado para o carimbo de auditoria.

    Várias funções de criação também são chamadas diretamente (fora do ciclo
    de requisição do FastAPI) pela importação de CSV (importar.py) e pelos
    fluxos do bot do Telegram (telegram_fluxos.py), passando só `dados` e
    `session` — nesses casos `user` fica com o valor padrão não resolvido
    (`Depends(...)`), não uma instância real de `Usuario`. Sem usuário real,
    não há quem carimbar.
    """
    return user.id if isinstance(user, Usuario) else None
