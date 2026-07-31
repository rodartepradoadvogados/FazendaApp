"""
Cria (ou renova a senha de) um usuário de TESTE no banco LOCAL de desenvolvimento.

Existe para permitir a verificação visual das telas durante o desenvolvimento
sem que ninguém precise compartilhar a senha da conta real — o usuário criado
aqui é descartável e só existe na máquina de quem roda o script.

TRAVA DE SEGURANÇA: recusa-se a rodar se o banco não for SQLite. Em produção
(PostgreSQL, via DATABASE_URL) o script aborta sem tocar em nada — ele não tem
como criar ou alterar usuário em produção, por construção.

Uso (a partir de backend/):
    python scripts/criar_usuario_teste_local.py

Imprime no final o usuário e a senha gerada (senha aleatória a cada execução).
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from fazenda.auth import hash_senha  # noqa: E402
from fazenda.database import engine  # noqa: E402
from fazenda.models import Usuario  # noqa: E402

USERNAME = "teste_local"


def main() -> int:
    if engine.url.get_backend_name() != "sqlite":
        print(
            f"ABORTADO: o banco configurado nao e SQLite (e '{engine.url.get_backend_name()}').\n"
            "Este script so opera em banco local de desenvolvimento.",
            file=sys.stderr,
        )
        return 1

    senha = "teste-" + secrets.token_hex(8)
    with Session(engine) as session:
        usuario = session.exec(select(Usuario).where(Usuario.username == USERNAME)).first()
        if usuario is None:
            usuario = Usuario(username=USERNAME, nome="Usuario de teste (local)", papel="admin")
            acao = "criado"
        else:
            acao = "senha renovada"
        usuario.senha_hash = hash_senha(senha)
        usuario.papel = "admin"
        usuario.ativo = True
        session.add(usuario)
        session.commit()

    print(f"Usuario de teste {acao} no banco local ({engine.url}).")
    print(f"  usuario: {USERNAME}")
    print(f"  senha:   {senha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
