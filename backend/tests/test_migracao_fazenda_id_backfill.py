"""
Migração 029227481e9e (backfill de fazenda_id nulo) — ver PR
claude/fazenda-id-raiz, Passo 2.

Roda o `alembic upgrade` de verdade, em processo separado, contra um SQLite
descartável — não dá pra chamar a migração como função Python direto porque
`alembic/env.py` lê `DATABASE_URL` de `fazenda.database` (fixado no import,
ver tests/conftest.py), então só um subprocesso com a env var própria
consegue apontar o Alembic para um banco isolado deste teste.

Cobre as duas pontas exigidas pelo PR:
- deriva corretamente do pai (ProtocoloInducaoAplicacao -> Lancamento;
  ProtocoloSanitarioEtapa -> ProtocoloSanitario — a mesma tabela "molde"
  citada no comentário de agenda.py sobre nunca gravar fazenda_id na prática)
  mesmo com DUAS fazendas reais cadastradas (onde o fallback de fazenda
  única não se aplicaria).
- com duas fazendas reais e SEM pai pra derivar, não adivinha: a linha
  continua NULA depois da migração.

IDs de fazenda usados aqui começam em 900 de propósito: a migração
f1a2b3c4d5e6 (piloto conservador de multi-fazenda), já aplicada pelo
`alembic upgrade 39bcd3f22a95` da fixture, semeia a fazenda #1 ("Jairo
Nasser") — usar um id baixo aqui colidiria com ela.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

FAZENDA_A = 900
FAZENDA_B = 901


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


def _inserir_fazenda(conn: sqlite3.Connection, id_: int, nome: str, eh_cowdata: bool = False) -> None:
    conn.execute(
        "INSERT INTO fazenda (id, nome, ativa, criado_em, eh_empresa_cowdata) VALUES (?, ?, 1, CURRENT_TIMESTAMP, ?)",
        (id_, nome, int(eh_cowdata)),
    )


def _inserir_animal_orfao(conn: sqlite3.Connection, id_: int) -> None:
    """`animal` não tem pai pra derivar fazenda_id — serve pra testar a
    estratégia (b)/(c) isolada da (a)."""
    conn.execute(
        "INSERT INTO animal (id, numero, eh_semen, ativo, atualizado_em, grupo_manual, a_descartar, "
        "excluir_bst, fazenda_id) VALUES (?, ?, 0, 1, CURRENT_TIMESTAMP, 0, 0, 0, NULL)",
        (id_, str(id_)),
    )


@pytest.fixture
def banco_pre_migracao(tmp_path):
    """Sobe o schema até a migração ANTERIOR a esta (39bcd3f22a95) — sem o
    backfill — pra este teste popular os dados NULOS manualmente antes de
    rodar `alembic upgrade head` de verdade."""
    db_path = tmp_path / "backfill.db"
    _rodar_alembic(db_path, "upgrade", "39bcd3f22a95")
    return db_path


class TestDerivaDoPai:
    def test_inducao_aplicacao_deriva_do_lancamento_mesmo_com_duas_fazendas(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        conn.execute(
            "INSERT INTO protocolo_inducao_lactacao (id, nome, dia_inicial, ativo, criado_em, fazenda_id) "
            "VALUES (1, 'Indução padrão', 0, 1, CURRENT_TIMESTAMP, ?)",
            (FAZENDA_B,),
        )
        conn.execute(
            "INSERT INTO protocolo_inducao_lancamento (id, protocolo_id, nome_protocolo, data_d0, criado_em, fazenda_id, ativo) "
            "VALUES (1, 1, 'INDUÇÃO — teste', '2026-08-01', CURRENT_TIMESTAMP, ?, 1)",
            (FAZENDA_B,),
        )
        # fazenda_id NULO de propósito — é o que a migração precisa preencher.
        conn.execute(
            "INSERT INTO protocolo_inducao_aplicacao "
            "(id, lancamento_id, numero_matriz, dia, descricao, data_prevista, realizada, fazenda_id) "
            "VALUES (1, 1, '100', 0, 'D0', '2026-08-01', 0, NULL)"
        )
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM protocolo_inducao_aplicacao WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id == FAZENDA_B, "deveria ter herdado o fazenda_id do lançamento-pai, não adivinhado outro valor"

    def test_protocolo_sanitario_etapa_deriva_do_protocolo_pai(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        conn.execute(
            "INSERT INTO protocolo_sanitario (id, nome, eh_mastite, ativo, criado_em, dia_inicial, fazenda_id) "
            "VALUES (1, 'Mastite clínica', 1, 1, CURRENT_TIMESTAMP, 1, ?)",
            (FAZENDA_B,),
        )
        # ProtocoloSanitarioEtapa é a tabela "molde" que agenda.py documenta
        # como nunca gravando fazenda_id na prática (ver comentário em
        # calcular_agenda) — mesmo assim a migração preenche o histórico.
        conn.execute(
            "INSERT INTO protocolo_sanitario_etapa "
            "(id, protocolo_id, dia, criterio_tipo, produto, dosagem, unidade, fazenda_id) "
            "VALUES (1, 1, 0, 'medicamento', 'Penicilina', 10, 'ml', NULL)"
        )
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM protocolo_sanitario_etapa WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id == FAZENDA_B


class TestNaoAdivinha:
    def test_tabela_sem_pai_com_duas_fazendas_fica_nula(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        # `animal` não tem pai pra derivar e a instalação tem DUAS fazendas
        # reais — a migração não pode chutar qual delas é a dona.
        _inserir_animal_orfao(conn, 1)
        conn.commit()
        conn.close()

        saida = _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM animal WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id is None
        assert "animal" in saida  # aparece no relatório de pendências impresso

    def test_fazenda_logica_da_cowdata_nao_conta_como_fazenda_unica(self, banco_pre_migracao):
        """Só a FAZENDA_B é real (eh_empresa_cowdata=0); a FAZENDA_A é a
        fazenda lógica da equipe CowData — não deve ser usada como "fazenda
        única" pro fallback (b), senão dado de cliente vira dono da CowData."""
        conn = sqlite3.connect(banco_pre_migracao)
        # Remove a fazenda #1 ("Jairo Nasser") que a própria fixture semeia
        # (migração do piloto) — senão este cenário teria DUAS fazendas
        # reais (a #1 e a FAZENDA_B) e o teste provaria a coisa errada.
        conn.execute("DELETE FROM usuario_fazenda WHERE fazenda_id = 1")
        conn.execute("DELETE FROM fazenda WHERE id = 1")
        _inserir_fazenda(conn, FAZENDA_A, "CowData (interno)", eh_cowdata=True)
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda Real", eh_cowdata=False)
        _inserir_animal_orfao(conn, 1)
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM animal WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id == FAZENDA_B


class TestFazendaUnica:
    def test_uma_so_fazenda_real_preenche_tudo_sem_ambiguidade(self, banco_pre_migracao):
        # A própria fixture já sobe com a fazenda #1 ("Jairo Nasser") semeada
        # pela migração do piloto — é a única fazenda real deste banco.
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_animal_orfao(conn, 1)
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM animal WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id == 1
