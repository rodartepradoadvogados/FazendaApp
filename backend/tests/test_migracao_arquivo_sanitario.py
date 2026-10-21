"""
Migração A s0a1r2q3v4o5 — arquivo do sanitário PREVENTIVO antigo.

Prova, num banco erguido pelas próprias migrações:
  - as 13 tabelas exclusivas saem do lugar (SQLite: renomeadas com prefixo;
    Postgres: SET SCHEMA arquivo_sanitario_2026) e nada é apagado de verdade;
  - nas tabelas compartilhadas só sai o preventivo de vacina/exame (inclui D1
    — vacina Ideagri natureza NULL — e D2 — vacina pré-parto da Secagem);
    BST (por atividade E pelo produto, que é como a Agenda grava), Indução de
    cio e o curativo FICAM;
  - D3: protocolo com finalidade 'preventivo' vira 'curativo';
  - o downgrade devolve tudo (linhas, tabelas, finalidade e, no Postgres, as
    FKs que cruzavam a fronteira).

SQLite sempre. Postgres só com `FAZENDA_TEST_PG_URL` apontando para um banco
VAZIO descartável (o teste roda `alembic upgrade` nele).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

BACKEND = Path(__file__).resolve().parent.parent
REV = "s0a1r2q3v4o5"
ANTERIOR = "n5o6p7q8r9s0"
_ARQUIVO = BACKEND / "alembic" / "versions" / "s0a1r2q3v4o5_arquivar_sanitario_preventivo.py"


def _mig():
    spec = importlib.util.spec_from_file_location("mig_arquivo_sanitario", _ARQUIVO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url, "FAZENDA_TESTING": "1"}
    env.pop("DATABASE_URL_MANUTENCAO", None)
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"


AGORA = datetime(2026, 10, 1, 8, 0)
D = date(2026, 9, 1)

# id -> (natureza, atividade, categoria, produto, obs, fica?)
SANIDADES = {
    1: ("preventivo", None, None, "Vacina Aftosa", "Preventivo: Aftosa", False),
    2: ("preventivo", "BST", None, "Boostin", None, True),
    3: ("preventivo", None, None, "Lactotropin 500", None, True),       # BST confirmado pela Agenda
    4: ("preventivo", "Indução de cio", None, "Estradiol", None, True),
    5: ("curativo", None, None, "Terramicina", None, True),
    6: (None, None, "Vacina", "Vacina Brucelose", None, False),        # D1 — Ideagri
    7: ("curativo", None, None, "Vacina X", None, False),              # vínculo com cronograma
    8: (None, "Vacina pré-parto", None, "Bovilis", None, False),       # D2 — Secagem na hora
    9: (None, None, None, "Bovilis", "Vacina pré-parto", False),       # D2 — confirmada pela Agenda
    10: (None, None, "Antibiótico", "Penicilina", None, True),          # Ideagri não-vacina
}
# id -> (natureza, observacao, produto, fica?)
AGENDADAS = {
    1: ("preventivo", "Preventivo: Aftosa", "Vacina Aftosa", False),
    2: ("preventivo", None, "Boostin", True),                          # BST programado
    3: (None, "Vacina pré-parto", "Bovilis", False),
    4: ("curativo", None, "Terramicina", True),
    5: ("preventivo", "Baixa retroativa: Raiva", "Vacina Raiva", False),
}
EVENTOS = {
    1: ("cronograma_sanitario_aplicar_1", False), 2: ("evento_sanitario_1_2026-09-01", False),
    3: ("calendario_sanitario_1__2026-09-01", False), 4: ("vacina_pre_parto_500_2026-09-02", False),
    5: ("bst_aplicacao_500_2026-09-01", True), 6: ("aplic_agendada_4", True),
}
PARAMETROS = {1: ("lista_espera_rotina_ativa", False), 2: ("cronograma_sanitario_dias_aviso", False), 3: ("intervalo_bst", True)}
# checklist_template_item fica no public: só o tipo do preventivo sai.
CHECKLIST = {1: ("vacina", False), 2: ("exame", False), 3: ("curativo", True)}


F = 901      # fazenda própria do teste (as migrações já semeiam a fazenda 1)
B = 90000    # base dos ids, longe de qualquer semente das migrações


def _semear(engine) -> None:
    p = {"t": True, "f": False, "a": AGORA, "d": D, "F": F, "B": B}
    with engine.begin() as c:
        if "finalidade" not in {col["name"] for col in inspect(c).get_columns("protocolo_sanitario")}:
            c.execute(text("ALTER TABLE protocolo_sanitario ADD COLUMN finalidade VARCHAR"))
        c.execute(text("INSERT INTO fazenda (id, nome, ativa, criado_em) VALUES (:F, 'F-teste', :t, :a)"), p)
        c.execute(text(
            "INSERT INTO pessoa (id, nome, tipo, ativo, criado_em, fazenda_id) VALUES (:B, 'Vet', 'veterinario', :t, :a, :F)"
        ), p)
        c.execute(text(
            "INSERT INTO evento_sanitario (id, nome, ativo, tipo_agendamento, criado_em, fazenda_id) "
            "VALUES (:B, 'Aftosa', :t, 'epoca', :a, :F)"
        ), p)
        c.execute(text(
            "INSERT INTO calendario_sanitario (id, evento_sanitario_id, frequencia_valor, frequencia_unidade, data_evento, "
            "ativo, criado_em, fazenda_id) VALUES (:B, :B, 6, 'meses', :d, :t, :a, :F)"
        ), p)
        c.execute(text(
            "INSERT INTO cronograma_sanitario (id, calendario_sanitario_id, data_evento, veterinario_pessoa_id, status, "
            "criado_em, atualizado_em, fazenda_id, checklist_desconsiderado) "
            "VALUES (:B, :B, :d, :B, 'concluido', :a, :a, :F, :f)"
        ), p)
        c.execute(text(
            "INSERT INTO cronograma_sanitario_aplicacao (id, fazenda_id, cronograma_id, estado, canal, data_aplicacao, "
            "frasco_vencido_ciente, estoque_desconsiderado, retroativo, registrado_em, leitura_fora_janela) "
            "VALUES (:B, :F, :B, 'aplicada', 'Protocolos', :d, :f, :f, :f, :a, :f)"
        ), p)
        c.execute(text(
            "INSERT INTO cronograma_sanitario_aplicacao_animal (id, aplicacao_id, fazenda_id, numero_matriz, sanidade_id) "
            "VALUES (:B, :B, :F, '500', :s)"
        ), {**p, "s": B + 7})
        for i, (nat, ativ, cat, prod, obs, _f) in SANIDADES.items():
            c.execute(text(
                "INSERT INTO sanidade (id, numero_matriz, data_aplicacao, produto, categoria, atividade, obs, natureza, "
                "atualizado_em, fazenda_id) VALUES (:i, '500', :d, :p, :c, :at, :o, :n, :a, :F)"
            ), {**p, "i": B + i, "p": prod, "c": cat, "at": ativ, "o": obs, "n": nat})
        for i, (nat, obs, prod, _f) in AGENDADAS.items():
            c.execute(text(
                "INSERT INTO aplicacao_agendada (id, numero_matriz, data, produto, observacao, aplicado, natureza, criado_em, "
                "fazenda_id) VALUES (:i, '500', :d, :p, :o, :f, :n, :a, :F)"
            ), {**p, "i": B + i, "p": prod, "o": obs, "n": nat})
        for i, (ev, _f) in EVENTOS.items():
            c.execute(text("INSERT INTO evento_realizado (id, evento_id, marcado_em, fazenda_id) VALUES (:i, :e, :a, :F)"),
                      {**p, "i": B + i, "e": ev})
        for i, (ch, _f) in PARAMETROS.items():
            c.execute(text(
                "INSERT INTO parametro_fazenda (id, chave, grupo, label, valor, tipo, atualizado_em, fazenda_id) "
                "VALUES (:i, :c, 'g', 'l', '1', 'int', :a, :F)"
            ), {**p, "i": B + i, "c": ch})
        for i, (tipo, _f) in CHECKLIST.items():
            c.execute(text(
                "INSERT INTO checklist_template_item (id, tipo, nome, chave, ordem, ativo, criado_em, fazenda_id) "
                "VALUES (:i, :tp, 'Item', 'custom', 1, :t, :a, :F)"
            ), {**p, "i": B + i, "tp": tipo})
        for i, fin in ((1, "preventivo"), (2, "curativo")):
            c.execute(text(
                "INSERT INTO protocolo_sanitario (id, nome, eh_mastite, ativo, criado_em, fazenda_id, finalidade) "
                "VALUES (:i, :n, :f, :t, :a, :F, :fin)"
            ), {**p, "i": B + i, "n": f"P{i}", "fin": fin})


def _ids(engine, tabela: str) -> set[int]:
    """Ids RELATIVOS (sem a base B) das linhas do teste."""
    with engine.connect() as c:
        return {r[0] - B for r in c.execute(text(f"SELECT id FROM {tabela} WHERE id >= :b"), {"b": B})}


def _esperado(dic: dict, fica: bool) -> set[int]:
    return {i for i, v in dic.items() if v[-1] is fica}


def _conferir_upgrade(engine, mig, pg: bool) -> None:
    insp = inspect(engine)
    publicas = set(insp.get_table_names())
    assert not publicas & set(mig.TABELAS_EXCLUSIVAS), "tabela antiga continua no public"
    arq = (lambda t: f"{mig.SCHEMA}.{t}") if pg else (lambda t: f"{mig.PREFIXO_SQLITE}{t}")
    for t in mig.TABELAS_EXCLUSIVAS:
        assert t in (set(insp.get_table_names(schema=mig.SCHEMA)) if pg else {
            x[len(mig.PREFIXO_SQLITE):] for x in publicas if x.startswith(mig.PREFIXO_SQLITE)
        })
    assert _ids(engine, arq("cronograma_sanitario")) == {0}  # nada apagado: só mudou de lugar

    assert _ids(engine, "sanidade") == _esperado(SANIDADES, True)
    assert _ids(engine, arq("sanidade_preventiva")) == _esperado(SANIDADES, False)
    assert _ids(engine, "aplicacao_agendada") == _esperado(AGENDADAS, True)
    assert _ids(engine, arq("aplicacao_agendada_preventiva")) == _esperado(AGENDADAS, False)
    assert _ids(engine, "evento_realizado") == _esperado(EVENTOS, True)
    assert _ids(engine, arq("evento_realizado_preventivo")) == _esperado(EVENTOS, False)
    assert _ids(engine, "parametro_fazenda") == _esperado(PARAMETROS, True)
    assert _ids(engine, "checklist_template_item") == _esperado(CHECKLIST, True)
    assert _ids(engine, arq("checklist_template_item_preventivo")) == _esperado(CHECKLIST, False)
    with engine.connect() as c:
        fins = {i - B: f for i, f in c.execute(text("SELECT id, finalidade FROM protocolo_sanitario WHERE id >= :b"), {"b": B})}
    assert fins == {1: "curativo", 2: "curativo"}


def _conferir_downgrade(engine, mig) -> None:
    insp = inspect(engine)
    publicas = set(insp.get_table_names())
    assert set(mig.TABELAS_EXCLUSIVAS) <= publicas
    assert not [t for t in publicas if t.startswith(mig.PREFIXO_SQLITE)]
    assert _ids(engine, "sanidade") == set(SANIDADES)
    assert _ids(engine, "aplicacao_agendada") == set(AGENDADAS)
    assert _ids(engine, "evento_realizado") == set(EVENTOS)
    assert _ids(engine, "parametro_fazenda") == set(PARAMETROS)
    assert _ids(engine, "checklist_template_item") == set(CHECKLIST)
    assert _ids(engine, "cronograma_sanitario") == {0}
    with engine.connect() as c:
        fins = {i - B: f for i, f in c.execute(text("SELECT id, finalidade FROM protocolo_sanitario WHERE id >= :b"), {"b": B})}
    assert fins == {1: "preventivo", 2: "curativo"}


def test_criterio_nunca_pega_bst_nem_inducao_nem_protocolo():
    mig = _mig()
    w = mig.criterio_sanidade(True)
    for trecho in ("'BST'", "'Indução de cio'", "%lactotropi%", "%boostin%", "%somatotropina%",
                   "protocolo_sanitario_lancamento_id IS NULL", "protocolo_iatf_lancamento_id IS NULL",
                   "protocolo_inducao_lancamento_id IS NULL"):
        assert trecho in w


def test_sqlite_sobe_arquiva_e_desce_devolvendo_tudo(tmp_path):
    mig = _mig()
    url = f"sqlite:///{tmp_path / 'arquivo.db'}"
    _alembic(url, "upgrade", ANTERIOR)
    engine = create_engine(url)
    _semear(engine)
    _alembic(url, "upgrade", REV)
    _conferir_upgrade(engine, mig, pg=False)
    _alembic(url, "downgrade", ANTERIOR)
    _conferir_downgrade(engine, mig)
    _alembic(url, "upgrade", "head")
    _conferir_upgrade(engine, mig, pg=False)


def test_relatorio_e_exportacao_leem_o_arquivo(tmp_path):
    """Os scripts da F0 rodam antes (public) e depois (arquivo) da migração."""
    sys.path.insert(0, str(BACKEND / "scripts"))
    try:
        import exportar_arquivo_sanitario as exp
        import relatorio_sanitario_legado as rel
    finally:
        sys.path.pop(0)
    url = f"sqlite:///{tmp_path / 'f0.db'}"
    _alembic(url, "upgrade", ANTERIOR)
    engine = create_engine(url)
    _semear(engine)
    antes = rel.montar_relatorio(engine)
    assert antes["linhas_compartilhadas"]["sanidade"][F] == len(_esperado(SANIDADES, False))
    assert antes["ficam_no_public"]["sanidade_inducao_cio"][F] == 1
    assert antes["ficam_no_public"]["sanidade_bst"][F] == 2
    assert antes["d3_protocolos_preventivo_para_curativo"][F] == 1
    _alembic(url, "upgrade", REV)
    engine.dispose()
    depois = rel.montar_relatorio(engine)
    assert depois["linhas_compartilhadas"]["sanidade"][F] == len(_esperado(SANIDADES, False))
    resumo = exp.exportar(engine, tmp_path / "saida", fazenda_id=F)
    assert resumo["sanidade_preventiva"] == len(_esperado(SANIDADES, False))
    assert resumo["cronograma_sanitario"] == 1
    assert (tmp_path / "saida" / "sanidade_preventiva.json").exists()


@pytest.mark.skipif(not os.environ.get("FAZENDA_TEST_PG_URL"), reason="defina FAZENDA_TEST_PG_URL (banco Postgres vazio)")
def test_postgres_set_schema_fks_e_downgrade():
    mig = _mig()
    url = os.environ["FAZENDA_TEST_PG_URL"]
    _alembic(url, "upgrade", ANTERIOR)
    engine = create_engine(url)
    _semear(engine)

    def fks_cruzando() -> set[str]:
        with engine.connect() as c:
            return {r[0] for r in c.execute(text(
                "SELECT c.conname FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid "
                "JOIN pg_class ref ON ref.oid = c.confrelid WHERE c.contype = 'f' "
                "AND cl.relname = 'cronograma_sanitario' AND ref.relname IN ('pessoa', 'fazenda')"
            ))}

    antes = fks_cruzando()
    assert antes
    _alembic(url, "upgrade", REV)
    _conferir_upgrade(engine, mig, pg=True)
    assert not fks_cruzando()
    with engine.connect() as c:
        guardadas = {r[0] for r in c.execute(text(f"SELECT nome FROM {mig.SCHEMA}._fks_removidas"))}
        # Arquivada, a pessoa pode ser apagada sem esbarrar no cronograma antigo.
    assert antes <= guardadas
    _alembic(url, "downgrade", ANTERIOR)
    _conferir_downgrade(engine, mig)
    assert fks_cruzando() == antes
    with engine.connect() as c:
        assert not c.execute(text(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"), {"s": mig.SCHEMA}).first()
