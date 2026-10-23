"""
Migração B s1n2o3v4o5m6 — tabelas do Sanitário v2, catálogo central e padrão
de fábrica. Em SQLite, por subprocesso (mesmo desenho de
test_migracao_arquivo_sanitario.py):

  - upgrade cria as 18 tabelas, o catálogo (B19 4–8 m, RB51 reforço a cada 4
    anos com ano-base 2026, reprodutiva jan/jun–jul/dez, vermífugo por peso,
    aftosa inativa...) e, para cada fazenda, o padrão de fábrica INATIVO
    (B19, exame TB, exame brucelose) + parâmetros + seed_flag;
  - rodar de novo (downgrade -> upgrade) não duplica; downgrade derruba tudo;
  - o padrão de fábrica de fazenda nova nasce uma vez e não volta depois de
    apagado (nunca no boot).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

BACKEND = Path(__file__).resolve().parent.parent
TABELAS = (
    "sanitario_catalogo", "sanitario_catalogo_versao", "sanitario_norma", "sanitario_caixa",
    "sanitario_caixa_versao", "sanitario_caixa_versao_categoria", "sanitario_dispositivo", "sanitario_dia",
    "sanitario_log", "sanitario_carencia_aceite", "sanitario_dia_caixa", "sanitario_dia_item",
    "sanitario_registro", "sanitario_situacao", "sanitario_prazo_legal", "sanitario_nota_agenda",
    "sanitario_parametros", "sanitario_job_estado",
)


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url, "FAZENDA_TESTING": "1"}
    env.pop("DATABASE_URL_MANUTENCAO", None)
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"


def _json(v):
    return json.loads(v) if isinstance(v, str) else v


def test_upgrade_downgrade_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    _alembic(url, "upgrade", "head")
    eng = sa.create_engine(url)
    try:
        nomes = set(sa.inspect(eng).get_table_names())
        assert set(TABELAS) <= nomes
        with eng.connect() as c:
            cat = {r.chave: r for r in c.execute(sa.text("SELECT * FROM sanitario_catalogo"))}
            assert {"b19", "rb51_reforco", "reprodutiva_reforco", "vermifugo", "leptospirose", "raiva",
                    "exame_tuberculose", "exame_brucelose", "aftosa"} <= set(cat)
            assert not cat["aftosa"].ativo
            defs = {r.chave: _json(r.definicao) for r in c.execute(sa.text(
                "SELECT c.chave, v.definicao FROM sanitario_catalogo c JOIN sanitario_catalogo_versao v "
                "ON v.catalogo_id = c.id"))}
            assert (defs["b19"]["evento_de_dias"], defs["b19"]["evento_ate_dias"]) == (120, 240)
            assert defs["b19"]["legal_atestado"]["quando"] == "primeiro"
            assert defs["b19"]["legal_comprovacao"]["dias"] == 180
            assert (defs["rb51_reforco"]["periodo_anos"], defs["rb51_reforco"]["periodo_ano_base"]) == (4, 2026)
            assert defs["reprodutiva_reforco"]["periodo_grupos"] == [[0], [5, 6], [11]]
            assert defs["vermifugo"]["dose_unidade"] == "mL_por_x_kg" and defs["vermifugo"]["dose_x_kg"] == 50.0
            assert defs["exame_tuberculose"]["legal_leitura"]["modo"] == "so_resultado"
            assert defs["clostridiose_pre_parto"]["evento_tipo"] == "pre_parto"

            fazendas = [r[0] for r in c.execute(sa.text("SELECT id FROM fazenda"))]
            assert fazendas, "as migrações semeiam ao menos uma fazenda"
            caixas = c.execute(sa.text("SELECT fazenda_id, nome, estado, padrao_fabrica FROM sanitario_caixa")).all()
            for fid in fazendas:
                desta = {r.nome for r in caixas if r.fazenda_id == fid}
                assert desta == {"Brucelose B19", "Exame de tuberculose", "Exame de brucelose"}
            assert all(r.estado == "inativa" and r.padrao_fabrica for r in caixas)
            flags = {r[0] for r in c.execute(sa.text("SELECT chave FROM seed_flag WHERE chave LIKE 'sanitario_padrao_v1:%'"))}
            assert flags == {f"sanitario_padrao_v1:{f}" for f in fazendas}
            assert c.execute(sa.text("SELECT count(*) FROM sanitario_parametros")).scalar() == len(fazendas)
            tb = c.execute(sa.text(
                "SELECT v.pub_cat_modo, v.periodo_grupos FROM sanitario_caixa c JOIN sanitario_caixa_versao v "
                "ON v.id = c.versao_atual_id WHERE c.nome = 'Exame de tuberculose'")).first()
            assert tb.pub_cat_modo == "excluir" and _json(tb.periodo_grupos) == [[3]]
    finally:
        eng.dispose()

    _alembic(url, "downgrade", "s0a1r2q3v4o5")
    eng = sa.create_engine(url)
    try:
        assert not (set(TABELAS) & set(sa.inspect(eng).get_table_names()))
        with eng.connect() as c:
            assert c.execute(sa.text("SELECT count(*) FROM seed_flag WHERE chave LIKE 'sanitario_padrao_v1:%'")).scalar() == 0
    finally:
        eng.dispose()

    _alembic(url, "upgrade", "head")  # sobe de novo sem erro e sem duplicar
    eng = sa.create_engine(url)
    try:
        with eng.connect() as c:
            assert c.execute(sa.text("SELECT count(*) FROM sanitario_catalogo")).scalar() == len(cat)
            n_faz = c.execute(sa.text("SELECT count(*) FROM fazenda")).scalar()
            assert c.execute(sa.text("SELECT count(*) FROM sanitario_caixa")).scalar() == 3 * n_faz
    finally:
        eng.dispose()


def test_padrao_de_fabrica_de_fazenda_nova_nasce_uma_vez():
    """Fazenda nova (provisionamento) recebe o padrão do catálogo, inativo;
    apagado, não volta — nem chamando de novo (seed_flag), nem no boot."""
    from fazenda.models import (
        CategoriaManejo, Fazenda, SanitarioCaixa, SanitarioCaixaVersao, SanitarioCaixaVersaoCategoria,
        SanitarioCatalogo, SanitarioCatalogoVersao, SanitarioParametros,
    )
    from fazenda.rules.sanitario.definicao import criar_padrao_fabrica

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=7, nome="Nova", uf="GO"))
        for nome in ("Aleitamento", "Recria 1", "Em lactação"):
            s.add(CategoriaManejo(fazenda_id=7, nome=nome, dia_min=0))
        assert criar_padrao_fabrica(s, 7) == 0  # catálogo vazio: não marca a flag
        for chave, nome, tipo, definicao in (
            ("b19", "Brucelose B19", "vacina", {"nome": "Brucelose B19", "nome_curto": "B19", "pub_sexo": "F"}),
            ("exame_tuberculose", "Exame de tuberculose", "exame",
             {"nome": "Exame de tuberculose", "tipo": "exame", "pub_cat_modo": "excluir",
              "categorias_ref": ["aleitamento", "bezerr"], "fallback_idade_min_dias": 90}),
        ):
            cat = SanitarioCatalogo(chave=chave, nome=nome, tipo=tipo, padrao_fabrica=True)
            s.add(cat)
            s.flush()
            s.add(SanitarioCatalogoVersao(catalogo_id=cat.id, versao=1, definicao=definicao))
        s.commit()

        assert criar_padrao_fabrica(s, 7) == 2
        s.commit()
        caixas = s.exec(select(SanitarioCaixa).where(SanitarioCaixa.fazenda_id == 7)).all()
        assert {c.nome for c in caixas} == {"Brucelose B19", "Exame de tuberculose"}
        assert all(c.estado == "inativa" and c.padrao_fabrica for c in caixas)
        tb = next(c for c in caixas if c.tipo == "exame")
        cats = s.exec(select(SanitarioCaixaVersaoCategoria).where(
            SanitarioCaixaVersaoCategoria.versao_id == tb.versao_atual_id)).all()
        aleit = s.exec(select(CategoriaManejo.id).where(CategoriaManejo.nome == "Aleitamento")).one()
        assert [c.categoria_manejo_id for c in cats] == [aleit]  # categoria por ID, resolvida na ativação
        assert s.get(SanitarioCaixaVersao, tb.versao_atual_id).pub_cat_modo == "excluir"
        assert s.exec(select(SanitarioParametros).where(SanitarioParametros.fazenda_id == 7)).one().uf == "GO"

        for c in caixas:  # o dono apaga (arquiva) o padrão
            c.estado = "arquivada"
            s.add(c)
        s.commit()
        assert criar_padrao_fabrica(s, 7) == 0  # não recria
        assert len(s.exec(select(SanitarioCaixa).where(SanitarioCaixa.fazenda_id == 7)).all()) == 2
    eng.dispose()


def test_boot_nao_cria_padrao_de_fabrica():
    """`create_db_and_tables`/lifespan não chamam o padrão de fábrica."""
    fonte_main = (BACKEND / "main.py").read_text()
    fonte_db = (BACKEND / "fazenda" / "database.py").read_text()
    assert "criar_padrao_fabrica" not in fonte_main and "criar_padrao_fabrica" not in fonte_db
