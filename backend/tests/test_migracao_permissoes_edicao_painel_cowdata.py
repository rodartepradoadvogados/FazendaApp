"""
Migração c3a91f4d20b7 (sete permissões de edição no Painel CowData) —
decisão explícita do dono: "ninguém ganha nada; você libera depois".

O que este teste trava é a metade que só a migração pode garantir: um membro
da Equipe CowData que JÁ EXISTIA — inclusive um com a área "cadastros" ou
"farmacia", que até ontem escrevia à vontade nessas telas — atravessa o
deploy com as sete colunas em FALSE. É uma perda de acesso deliberada, não
um efeito colateral; abrir qualquer uma por omissão seria justamente o que
o dono pediu para não acontecer.

Mesma técnica de subprocesso das demais migrações desta fundação.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

COLUNAS_NOVAS = [
    "pode_editar_cadastros_globais",
    "pode_editar_touros_naab",
    "pode_editar_farmacia",
    "pode_consultar_usuarios",
    "pode_editar_usuarios",
    "pode_controlar_acesso_usuarios",
    "pode_editar_news",
]


def _rodar_alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )
    assert resultado.returncode == 0, (
        f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{resultado.stdout}\nSTDERR:\n{resultado.stderr}"
    )
    return resultado.stdout


@pytest.fixture
def banco_pre_migracao(tmp_path):
    """Banco na revisão IMEDIATAMENTE anterior (b2f7c1a83d59) — as sete
    colunas ainda não existem."""
    db_path = tmp_path / "permissoes_edicao.db"
    _rodar_alembic(db_path, "upgrade", "b2f7c1a83d59")
    return db_path


def _membros_existentes(conn) -> None:
    """Três linhas como as que existem hoje em produção: um membro com a
    área de baixo privilégio, um com Farmácia e um sem área nenhuma."""
    conn.execute(
        "INSERT INTO usuario (id, username, nome, senha_hash, papel, permissoes, ativo, criado_em, "
        "pode_publicar_materias_blog) VALUES "
        "(901, 'atendente', 'Atendente', 'x', 'operador', '', 1, CURRENT_TIMESTAMP, 0),"
        "(902, 'farmaceutico', 'Farmacêutico', 'x', 'operador', '', 1, CURRENT_TIMESTAMP, 0),"
        "(903, 'estagiario', 'Estagiário', 'x', 'operador', '', 1, CURRENT_TIMESTAMP, 0)"
    )
    conn.execute(
        "INSERT INTO permissao_equipe_cowdata "
        "(id, usuario_id, areas, nivel_sigilo, pode_suspender_assinatura, pode_acessar_fazendas, "
        " pode_alterar_cadastro, pode_modificar_suspender_plano, pode_emitir_auditar_contratos, "
        " pode_emitir_cobrancas, pode_vincular_usuarios, pode_cadastrar_usuarios, criado_em, atualizado_em) VALUES "
        "(901, 901, 'cadastros', 'basico', 0, 1, 1, 0, 0, 0, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),"
        "(902, 902, 'farmacia,cadastros', 'tecnico', 0, 0, 0, 0, 0, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),"
        "(903, 903, '', 'basico', 0, 0, 0, 0, 0, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    conn.commit()


def test_todo_membro_existente_fica_sem_as_sete_permissoes(banco_pre_migracao):
    conn = sqlite3.connect(banco_pre_migracao)
    _membros_existentes(conn)
    conn.close()

    _rodar_alembic(banco_pre_migracao, "upgrade", "head")

    conn = sqlite3.connect(banco_pre_migracao)
    linhas = conn.execute(
        f"SELECT usuario_id, {', '.join(COLUNAS_NOVAS)} FROM permissao_equipe_cowdata ORDER BY usuario_id"
    ).fetchall()
    conn.close()

    assert [l[0] for l in linhas] == [901, 902, 903]
    for linha in linhas:
        assert all(valor == 0 for valor in linha[1:]), (
            f"membro {linha[0]} ganhou permissão nova na migração — "
            "'ninguém ganha nada; você libera depois' é o pedido explícito do dono"
        )


def test_a_migracao_nao_mexe_nas_permissoes_que_ja_existiam(banco_pre_migracao):
    """Controle do outro lado: o eixo antigo (áreas, nível de sigilo e as 8
    sub-permissões de fazendas) atravessa intacto — a migração só acrescenta
    colunas."""
    conn = sqlite3.connect(banco_pre_migracao)
    _membros_existentes(conn)
    conn.close()

    _rodar_alembic(banco_pre_migracao, "upgrade", "head")

    conn = sqlite3.connect(banco_pre_migracao)
    linha = conn.execute(
        "SELECT areas, nivel_sigilo, pode_acessar_fazendas, pode_alterar_cadastro, pode_cadastrar_usuarios "
        "FROM permissao_equipe_cowdata WHERE usuario_id = 901"
    ).fetchone()
    farmaceutico = conn.execute(
        "SELECT areas, nivel_sigilo FROM permissao_equipe_cowdata WHERE usuario_id = 902"
    ).fetchone()
    conn.close()
    assert linha == ("cadastros", "basico", 1, 1, 1)
    assert farmaceutico == ("farmacia,cadastros", "tecnico")


def test_novo_membro_gravado_depois_da_migracao_tambem_nasce_desligado(banco_pre_migracao):
    """`server_default=sa.false()` cobre também quem for inserido por código
    antigo enquanto o deploy roda — nenhuma linha nasce com permissão."""
    _rodar_alembic(banco_pre_migracao, "upgrade", "head")

    conn = sqlite3.connect(banco_pre_migracao)
    conn.execute(
        "INSERT INTO usuario (id, username, nome, senha_hash, papel, permissoes, ativo, criado_em, "
        "pode_publicar_materias_blog) VALUES (904, 'novo', 'Novo', 'x', 'operador', '', 1, CURRENT_TIMESTAMP, 0)"
    )
    conn.execute(
        "INSERT INTO permissao_equipe_cowdata (id, usuario_id, areas, nivel_sigilo, criado_em, atualizado_em) "
        "VALUES (904, 904, 'cadastros', 'basico', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    conn.commit()
    linha = conn.execute(
        f"SELECT {', '.join(COLUNAS_NOVAS)} FROM permissao_equipe_cowdata WHERE usuario_id = 904"
    ).fetchone()
    conn.close()
    assert all(valor == 0 for valor in linha), linha
