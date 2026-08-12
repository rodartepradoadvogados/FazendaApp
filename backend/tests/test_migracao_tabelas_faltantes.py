"""
Migração 4ede0ee68b09 (cria as tabelas que só existiam via
`SQLModel.metadata.create_all`) — ver ENTREGA A do PR
claude/migracoes-e-varredura-fazenda-id.

Este é o teste de garantia contra o drift relatado pela migração de backfill
anterior (029227481e9e): sete tabelas do model (`protocolo_iatf`,
`protocolo_iatf_etapa`, `safra`, `diaria_auditoria`, `guia_folha_encargo`,
`parametro_diaria_padrao`, `parametro_sugestao_movimentacao`) mais uma oitava
achada nesta varredura (`nota_capa`, sem fazenda_id — não aparecia no aviso
da 029227481e9e porque aquele backfill só varre tabelas com essa coluna)
nunca tiveram `op.create_table` — só existiam num banco de dev/teste porque
a subida da aplicação chama `create_all` como rede de segurança. Um banco
montado só pelo Alembic (restauração, ambiente novo) nunca as teria.

Roda `alembic upgrade head` de verdade, em subprocesso contra um SQLite
descartável — mesmo motivo do test_migracao_fazenda_id_backfill.py: o
Alembic lê DATABASE_URL de fazenda.database no import, então só um
subprocesso com env var própria isola o banco deste teste do resto da
suíte (que já fixou DATABASE_URL em tests/conftest.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parent.parent


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


class TestSchemaAlembicIgualAoSchemaDosModelos:
    """A garantia central: depois de `alembic upgrade head` num banco vazio,
    o conjunto de tabelas que o Alembic criou é EXATAMENTE o conjunto de
    tabelas declaradas em fazenda/models/ — nem uma tabela do model faltando
    (o bug desta migração) nem uma tabela "fantasma" só do Alembic (migração
    de criação duplicada/renomeada sem atualizar o model)."""

    def test_upgrade_head_em_banco_vazio_cria_todas_as_tabelas_do_model(self, tmp_path):
        db_path = tmp_path / "schema_completo.db"
        _rodar_alembic(db_path, "upgrade", "head")

        # Import tardio (depois do subprocesso rodar) só para ler o metadata
        # dos modelos — não abre conexão nenhuma com o banco do teste.
        from fazenda.models import SQLModel

        engine = sa.create_engine(f"sqlite:///{db_path}")
        tabelas_alembic = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
        tabelas_model = set(SQLModel.metadata.tables.keys())
        engine.dispose()

        faltando_no_alembic = sorted(tabelas_model - tabelas_alembic)
        sobrando_no_alembic = sorted(tabelas_alembic - tabelas_model)
        assert not faltando_no_alembic, (
            f"tabela(s) do model sem migração de criação (drift — voltou o bug da "
            f"ENTREGA A): {faltando_no_alembic}"
        )
        assert not sobrando_no_alembic, (
            f"tabela(s) só no Alembic, sem model correspondente (migração órfã ou "
            f"model renomeado sem atualizar a migração): {sobrando_no_alembic}"
        )

    def test_tabelas_antes_sem_migracao_de_criacao_existem_e_com_as_colunas_certas(self, tmp_path):
        """Prova pontual das 8 tabelas desta migração — não só "a tabela
        existe", mas que uma coluna central de cada uma está lá com o tipo
        certo, contra regressão de um create_table copiado errado."""
        db_path = tmp_path / "colunas.db"
        _rodar_alembic(db_path, "upgrade", "head")

        engine = sa.create_engine(f"sqlite:///{db_path}")
        insp = sa.inspect(engine)

        esperado: dict[str, set[str]] = {
            "protocolo_iatf": {"id", "nome", "observacao", "ativo", "criado_em", "fazenda_id"},
            "protocolo_iatf_etapa": {
                "id", "protocolo_id", "dia", "criterio_tipo", "principio_ativo_id",
                "produto", "dose", "unidade", "via", "fazenda_id",
            },
            "safra": {
                "id", "nome", "fazenda_id", "centro_custo", "data_inicio", "data_fim",
                "hectares", "toneladas_produzidas", "observacao", "ativo", "criado_em", "atualizado_em",
            },
            "diaria_auditoria": {
                "id", "diaria_id", "periodo_inicio", "periodo_fim", "dias_trabalhados",
                "confirmado_em", "usuario_id", "criado_em", "fazenda_id",
            },
            "guia_folha_encargo": {
                "id", "fazenda_id", "tipo", "competencia", "codigo_receita", "valor_principal",
                "valor_multa", "valor_juros", "valor_total", "data_vencimento", "linha_digitavel",
                "numero_lancamento", "origem", "usuario_id", "criado_em",
            },
            "parametro_diaria_padrao": {
                "id", "auditar_periodicamente", "frequencia_auditoria", "dia_semana_auditoria",
                "intervalo_dias_auditoria", "atualizado_em", "fazenda_id",
            },
            "parametro_sugestao_movimentacao": {"id", "fazenda_id", "modo", "dia_semana", "atualizado_em"},
            # nota_capa não tem fazenda_id de propósito — aviso global da Capa,
            # editável só pelo dono da plataforma (ver fazenda/models/sistema.py).
            "nota_capa": {"id", "titulo", "texto", "ativa", "criado_em", "atualizado_em"},
        }

        for tabela, colunas_esperadas in esperado.items():
            assert insp.has_table(tabela), f"tabela {tabela!r} não foi criada por `alembic upgrade head`"
            colunas_reais = {c["name"] for c in insp.get_columns(tabela)}
            assert colunas_reais == colunas_esperadas, (
                f"colunas de {tabela!r} divergem do model: "
                f"faltando={sorted(colunas_esperadas - colunas_reais)} "
                f"sobrando={sorted(colunas_reais - colunas_esperadas)}"
            )

        engine.dispose()

    def test_migracao_e_idempotente_em_banco_que_ja_tem_as_tabelas(self, tmp_path):
        """Simula produção: as 7 tabelas originais já existem (criadas por
        `create_all` na subida da app, como é hoje) quando esta migração
        roda — precisa pular a criação sem duplicar nem quebrar, e ainda
        criar só a que falta de verdade (`nota_capa`)."""
        db_path = tmp_path / "producao_simulada.db"
        # Sobe só até a migração ANTERIOR a esta, para poder simular o
        # `create_all` de produção rodando por cima de um schema sem elas.
        _rodar_alembic(db_path, "upgrade", "029227481e9e")

        from fazenda.models import SQLModel

        engine = sa.create_engine(f"sqlite:///{db_path}")
        SQLModel.metadata.create_all(engine)  # a mesma rede de segurança de database.py
        engine.dispose()

        saida = _rodar_alembic(db_path, "upgrade", "head")
        assert "falhou" not in saida.lower()

        engine = sa.create_engine(f"sqlite:///{db_path}")
        tabelas = set(sa.inspect(engine).get_table_names())
        engine.dispose()
        for tabela in (
            "protocolo_iatf", "protocolo_iatf_etapa", "safra", "diaria_auditoria",
            "guia_folha_encargo", "parametro_diaria_padrao",
            "parametro_sugestao_movimentacao", "nota_capa",
        ):
            assert tabela in tabelas
