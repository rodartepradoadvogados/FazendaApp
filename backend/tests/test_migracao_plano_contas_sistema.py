"""
Migração d8b3f6a1c294 — contas do sistema 3.03.01.16 (Retenções) e 3.03.01.17
(Vales e adiantamentos) no plano de contas gerencial.

POR QUE ESTA MIGRAÇÃO PRECISA DE TESTE PRÓPRIO. `database.py::_aplicar_alembic`
roda `command.upgrade(cfg, "head")` NO BOOT da API: migração que aborta é API
que não sobe. Esta é SÓ DE DADOS (não cria coluna nem tabela) e roda contra o
plano de contas de produção de cada fazenda.

O QUE ESTES TESTES TRAVAM:
 - fazenda com o grupo 3.03.01 ganha 16 e 17, com linha_dre e natureza_fin
   próprias, ativas;
 - fazenda SEM o plano (ou sem o grupo) não ganha nada — a migração não cria
   o grupo;
 - rodar de novo (idempotência) não duplica nem altera;
 - conta já existente (mesmo código) NÃO é sobrescrita, nem quando tem outro
   nome;
 - tabela do plano ausente não aborta o upgrade;
 - o downgrade remove SÓ o que a migração criou, e só o que não tem
   lançamento/item/configuração apontando.

Mesma técnica de subprocesso das demais migrações (ver
test_migracao_vale_natureza_assuncao.py).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REVISAO_ANTERIOR = "d4e8b1c7a2f5"
REVISAO = "d8b3f6a1c294"


def _alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    return r.stdout + r.stderr


def _sql(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        linhas = conn.execute(sql, params).fetchall()
        conn.commit()
        return linhas
    finally:
        conn.close()


def _plano(db_path: Path, fazenda_id: int, codigos: tuple[str, ...]) -> list[tuple]:
    marcas = ",".join("?" for _ in codigos)
    return _sql(
        db_path,
        f"SELECT codigo, nome, ativa, linha_dre, natureza_fin FROM plano_conta_gerencial "
        f"WHERE fazenda_id = ? AND codigo IN ({marcas}) ORDER BY codigo",
        (fazenda_id, *codigos),
    )


def _inserir_conta(db_path: Path, fazenda_id: int, codigo: str, nome: str, **extra) -> None:
    campos = {"fazenda_id": fazenda_id, "codigo": codigo, "nome": nome, "ativa": 1,
              "atualizado_em": "2026-01-01 00:00:00", **extra}
    _sql(db_path, f"INSERT INTO plano_conta_gerencial ({', '.join(campos)}) VALUES ({', '.join('?' for _ in campos)})",
         tuple(campos.values()))


GRUPO_E_PESSOAL = (("3.03", "Despesas"), ("3.03.01", "Pessoal"), ("3.03.01.01", "Salários"), ("3.03.01.15", "Outros"))
NOVAS = ("3.03.01.16", "3.03.01.17")
CANONICAS = [
    ("3.03.01.16", "Retenções", 1, "NAO_ENTRA_NA_DRE", "OBRIGACAO"),
    ("3.03.01.17", "Vales e adiantamentos", 1, "NAO_ENTRA_NA_DRE", "ADIANTAMENTO"),
]


@pytest.fixture
def banco(tmp_path):
    """Banco na revisão anterior com 4 fazendas:
    1 = plano com Pessoal; 2 = plano SEM o grupo 3.03.01; 3 = Pessoal e 16
    pré-existente com outro nome; 4 = nenhuma conta de plano."""
    db = tmp_path / "plano.db"
    _alembic(db, "upgrade", REVISAO_ANTERIOR)
    for codigo, nome in GRUPO_E_PESSOAL:
        _inserir_conta(db, 1, codigo, nome, linha_dre="GASTOS_PESSOAL" if codigo == "3.03.01" else None)
    _inserir_conta(db, 2, "3.01", "Alimentação")
    _inserir_conta(db, 2, "3.03.01.01", "Salários (sem o grupo)")
    for codigo, nome in GRUPO_E_PESSOAL[:3]:
        _inserir_conta(db, 3, codigo, nome)
    _inserir_conta(db, 3, "3.03.01.16", "Retenção de ISS", linha_dre="DESPESAS_OPERACIONAIS")
    return db


def test_fazenda_com_pessoal_ganha_as_duas_contas_com_valores_proprios(banco):
    assert _plano(banco, 1, NOVAS) == []
    _alembic(banco, "upgrade", "head")
    assert _plano(banco, 1, NOVAS) == CANONICAS


def test_fazenda_sem_o_grupo_ou_sem_plano_nao_ganha_nada(banco):
    _alembic(banco, "upgrade", "head")
    assert _plano(banco, 2, NOVAS) == []          # tem plano, mas sem 3.03.01
    assert _plano(banco, 4, NOVAS) == []          # não tem plano nenhum
    assert _sql(banco, "SELECT COUNT(*) FROM plano_conta_gerencial WHERE codigo = '3.03.01' AND fazenda_id = 2") == [(0,)]


def test_conta_preexistente_nao_e_sobrescrita_mesmo_com_outro_nome(banco):
    _alembic(banco, "upgrade", "head")
    # 16 existia com outro nome e outra linha da DRE: fica exatamente como estava.
    assert _plano(banco, 3, ("3.03.01.16",)) == [("3.03.01.16", "Retenção de ISS", 1, "DESPESAS_OPERACIONAIS", None)]
    # 17 faltava: foi criada.
    assert _plano(banco, 3, ("3.03.01.17",)) == [CANONICAS[1]]


def test_idempotente_rodar_de_novo_nao_duplica_nem_altera(banco):
    _alembic(banco, "upgrade", "head")
    total_antes = _sql(banco, "SELECT COUNT(*) FROM plano_conta_gerencial")[0][0]
    # Reaplica a migração (desce e sobe): o resultado é o mesmo, sem duplicar.
    _alembic(banco, "downgrade", REVISAO_ANTERIOR)
    _alembic(banco, "upgrade", "head")
    depois = _sql(banco, "SELECT fazenda_id, codigo, nome, linha_dre, natureza_fin FROM plano_conta_gerencial ORDER BY fazenda_id, codigo")
    assert [d for d in depois if d[1] in NOVAS and d[0] == 1] == [
        (1, "3.03.01.16", "Retenções", "NAO_ENTRA_NA_DRE", "OBRIGACAO"),
        (1, "3.03.01.17", "Vales e adiantamentos", "NAO_ENTRA_NA_DRE", "ADIANTAMENTO"),
    ]
    assert len(depois) == len({(d[0], d[1]) for d in depois})
    assert len(depois) == total_antes  # fazenda 1: 2 novas; fazenda 3: 1 nova (a 16 dela não é da migração)
    # Um upgrade a mais com o banco já no head não muda nada.
    assert "d8b3f6a1c294" in _alembic(banco, "current")
    _alembic(banco, "upgrade", "head")
    assert _sql(banco, "SELECT COUNT(*) FROM plano_conta_gerencial") == [(len(depois),)]


def test_cabeca_unica_e_esta_revisao(banco):
    _alembic(banco, "upgrade", "head")
    assert REVISAO in _alembic(banco, "heads")


def test_sem_a_tabela_do_plano_o_upgrade_nao_aborta(tmp_path):
    db = tmp_path / "sem_plano.db"
    _alembic(db, "upgrade", REVISAO_ANTERIOR)
    _sql(db, "DROP TABLE plano_conta_gerencial")
    _alembic(db, "upgrade", "head")
    _alembic(db, "downgrade", REVISAO_ANTERIOR)


def test_downgrade_remove_so_o_que_a_migracao_criou(banco):
    _alembic(banco, "upgrade", "head")
    _alembic(banco, "downgrade", REVISAO_ANTERIOR)
    assert _plano(banco, 1, NOVAS) == []                              # criadas pela migração: saem
    assert _plano(banco, 3, NOVAS) == [("3.03.01.16", "Retenção de ISS", 1, "DESPESAS_OPERACIONAIS", None)]  # da fazenda: ficam
    # O resto do plano da fazenda 1 está intacto.
    assert [c[0] for c in _sql(banco, "SELECT codigo FROM plano_conta_gerencial WHERE fazenda_id = 1 ORDER BY codigo")] == \
        sorted(c for c, _ in GRUPO_E_PESSOAL)


def test_downgrade_mantem_conta_com_lancamento_item_ou_configuracao_apontando(banco):
    _alembic(banco, "upgrade", "head")
    _sql(banco, "INSERT INTO lancamento_item (fazenda_id, numero_lancamento, produto, valor_total, atualizado_em, "
                "codigo_conta_gerencial, gerado_por) VALUES (1, 'LC-1', 'Vale', 200.0, '2026-01-01', '3.03.01.17', 'vale')")
    _sql(banco, "INSERT INTO conta_padrao_origem (fazenda_id, origem, codigo_conta_gerencial, atualizado_em) "
                "VALUES (3, 'caixa_retencao', '3.03.01.17', '2026-01-01')")
    _alembic(banco, "downgrade", REVISAO_ANTERIOR)
    # 17 da fazenda 1 tem item apontando; 17 da fazenda 3 tem configuração apontando; 16 da fazenda 1 sai.
    assert [c[0] for c in _plano(banco, 1, NOVAS)] == ["3.03.01.17"]
    assert [c[0] for c in _plano(banco, 3, ("3.03.01.17",))] == ["3.03.01.17"]
    # Sobe de novo: nada duplica, e a conta mantida continua a mesma linha.
    _alembic(banco, "upgrade", "head")
    assert _sql(banco, "SELECT COUNT(*) FROM plano_conta_gerencial WHERE codigo = '3.03.01.17' AND fazenda_id = 1") == [(1,)]
    assert [c[0] for c in _plano(banco, 1, NOVAS)] == ["3.03.01.16", "3.03.01.17"]


def test_downgrade_mantem_conta_alterada_depois_pelo_usuario(banco):
    _alembic(banco, "upgrade", "head")
    _sql(banco, "UPDATE plano_conta_gerencial SET nome = 'Vales (renomeada)' WHERE fazenda_id = 1 AND codigo = '3.03.01.17'")
    _alembic(banco, "downgrade", REVISAO_ANTERIOR)
    assert [c[:2] for c in _plano(banco, 1, NOVAS)] == [("3.03.01.17", "Vales (renomeada)")]
