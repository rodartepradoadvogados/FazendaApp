"""protocolo sanitario: cabecalho de lote (paridade com IATF/inducao/customizado/lida)

Cria `protocolo_sanitario_lote` — o "cabeçalho" que faltava para o Sanitário
entrar na Central de Protocolos com a mesma grade dia×animal e as mesmas
ações (marcar, desfazer, cancelar, encerrar) que IATF/Indução de
Lactação/Customizado/Lida já tinham. Até aqui, cada
`ProtocoloSanitarioLancamento` era uma linha solta por animal, sem estado
próprio — a Central AGRUPAVA por (protocolo_id, data_inicio) só para exibir
(ver `_linhas_sanitario` antes desta migração), o que confundia lançamentos
de fato distintos que caíssem coincidentemente na mesma data.

Também adiciona:
- `protocolo_sanitario_lancamento.lote_id` (FK para o novo cabeçalho).
- `protocolo_sanitario_aplicacao.dia` e `.numero_matriz` — denormalizados de
  `ProtocoloSanitarioEtapa.dia` e `ProtocoloSanitarioLancamento.numero_matriz`,
  só para dar a esta tabela o MESMO formato de
  ProtocoloIatfAplicacao/ProtocoloInducaoAplicacao/ProtocoloCustomizadoAplicacao/
  LidaAplicacao — o código genérico da Central (detalhe, dar baixa, desfazer,
  cancelar) lê `.dia`/`.numero_matriz` direto da aplicação sem precisar saber
  que o Sanitário tem uma camada extra por animal que os outros não têm.

## O backfill

Deliberadamente CONSERVADOR: cada `ProtocoloSanitarioLancamento` já existente
vira um "lote de 1" — um cabeçalho novo só para ele, nome gerado do mesmo
jeito que `gerar_nome_lancamento` monta na hora de lançar. NÃO tenta agrupar
lançamentos antigos que coincidam em (protocolo_id, data_inicio) num lote só
— seria adivinhar se aquilo foi uma chamada só (lote de verdade) ou duas
chamadas separadas que só caíram no mesmo dia, e essa distinção não dá para
recuperar do dado histórico (POST /sanidade/protocolos/lancamentos nunca
gravou essa informação). A partir desta migração, todo lançamento NOVO passa
a gravar o lote de verdade (ver `sanidade.lancar_protocolo`); só o histórico
pré-migração fica em lotes de 1.

Idempotente: só faz o backfill de linhas com `lote_id`/`numero_matriz`/`dia`
ainda nulos — reexecutar não duplica nem sobrescreve.

Revision ID: e3ad0b2a1c47
Revises: e3e87a1582e2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3ad0b2a1c47'
down_revision: Union[str, Sequence[str], None] = 'e3e87a1582e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Guardas de idempotência: em produção o `create_all` de subida (ver
    # database.py) já pode ter criado tabelas/colunas com o schema ATUAL dos
    # models antes desta migração rodar — mesmo padrão de
    # c1a2b3d4e5f6_lactacao.py. Sem isso, reexecutar (ou rodar por cima de um
    # banco pré-existente) quebra com "table/column already exists".
    if "protocolo_sanitario_lote" not in insp.get_table_names():
        op.create_table(
            "protocolo_sanitario_lote",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("protocolo_id", sa.Integer(), nullable=False),
            sa.Column("nome_protocolo", sa.String(), nullable=False),
            sa.Column("data_inicio", sa.Date(), nullable=False),
            sa.Column("responsavel", sa.String(), nullable=True),
            sa.Column("observacao", sa.String(), nullable=True),
            sa.Column("encerrado_em", sa.Date(), nullable=True),
            sa.Column("encerrado_motivo", sa.String(), nullable=True),
            sa.Column("ativo", sa.Boolean(), nullable=False),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("usuario_id", sa.Integer(), nullable=True),
            sa.Column("fazenda_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["protocolo_id"], ["protocolo_sanitario.id"]),
            sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
            sa.ForeignKeyConstraint(["fazenda_id"], ["fazenda.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_protocolo_sanitario_lote_ativo"), "protocolo_sanitario_lote", ["ativo"], unique=False)
        op.create_index(op.f("ix_protocolo_sanitario_lote_fazenda_id"), "protocolo_sanitario_lote", ["fazenda_id"], unique=False)
        insp = sa.inspect(conn)  # refresh: a tabela nova precisa aparecer nas checagens abaixo

    colunas_lancamento = {c["name"] for c in insp.get_columns("protocolo_sanitario_lancamento")}
    if "lote_id" not in colunas_lancamento:
        op.add_column(
            "protocolo_sanitario_lancamento",
            sa.Column("lote_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            op.f("ix_protocolo_sanitario_lancamento_lote_id"), "protocolo_sanitario_lancamento", ["lote_id"], unique=False,
        )
    nomes_fk_lancamento = {fk["name"] for fk in insp.get_foreign_keys("protocolo_sanitario_lancamento")}
    if "fk_protocolo_sanitario_lancamento_lote_id" not in nomes_fk_lancamento:
        # SQLite não suporta ADD CONSTRAINT direto (só via batch/copy-and-move) —
        # mesmo padrão de b20df48b733a_movimento_estoque_rastreabilidade.py.
        with op.batch_alter_table("protocolo_sanitario_lancamento") as batch_op:
            batch_op.create_foreign_key(
                "fk_protocolo_sanitario_lancamento_lote_id", "protocolo_sanitario_lote", ["lote_id"], ["id"],
            )

    colunas_aplicacao = {c["name"] for c in insp.get_columns("protocolo_sanitario_aplicacao")}
    if "dia" not in colunas_aplicacao:
        op.add_column("protocolo_sanitario_aplicacao", sa.Column("dia", sa.Integer(), nullable=True))
        op.create_index(op.f("ix_protocolo_sanitario_aplicacao_dia"), "protocolo_sanitario_aplicacao", ["dia"], unique=False)
    if "numero_matriz" not in colunas_aplicacao:
        op.add_column("protocolo_sanitario_aplicacao", sa.Column("numero_matriz", sa.String(), nullable=True))
        op.create_index(
            op.f("ix_protocolo_sanitario_aplicacao_numero_matriz"), "protocolo_sanitario_aplicacao", ["numero_matriz"], unique=False,
        )

    _backfill(conn)


def _backfill(conn) -> None:
    """Feito com Core + reflexão de tabela (`autoload_with`), nunca importando
    as classes ORM de `fazenda.models`: elas refletem o formato ATUAL do
    model, que pode ter colunas adicionadas por migrações POSTERIORES a esta
    (ex.: `ProtocoloSanitario.finalidade` — nasceu como campo de model puro
    numa onda anterior, sem migração própria). Rodando esta migração isolada
    (`alembic upgrade` a partir de um banco vazio) essa coluna ainda não
    existe neste ponto da cadeia, e uma query ORM que a inclui sem querer
    quebra com "no such column". Reflexão via `conn` só vê as colunas que
    REALMENTE existem no schema neste ponto — a mesma robustez que os testes
    (que sempre criam o schema completo via `create_all` antes de qualquer
    migração rodar) mascaram, mas que uma subida em banco genuinamente vazio
    exercita de verdade.
    """
    from datetime import date

    from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento

    meta = sa.MetaData()
    t_protocolo = sa.Table("protocolo_sanitario", meta, autoload_with=conn)
    t_etapa = sa.Table("protocolo_sanitario_etapa", meta, autoload_with=conn)
    t_lancamento = sa.Table("protocolo_sanitario_lancamento", meta, autoload_with=conn)
    t_aplicacao = sa.Table("protocolo_sanitario_aplicacao", meta, autoload_with=conn)
    t_lote = sa.Table("protocolo_sanitario_lote", meta, autoload_with=conn)

    moldes = {
        row.id: row for row in conn.execute(
            sa.select(t_protocolo.c.id, t_protocolo.c.nome, t_protocolo.c.dia_inicial)
        ).all()
    }
    etapas_por_protocolo: dict[int, list[int]] = {}
    etapa_dia_por_id: dict[int, int] = {}
    for row in conn.execute(sa.select(t_etapa.c.id, t_etapa.c.protocolo_id, t_etapa.c.dia)).all():
        etapas_por_protocolo.setdefault(row.protocolo_id, []).append(row.dia)
        etapa_dia_por_id[row.id] = row.dia

    pendentes = conn.execute(
        sa.select(
            t_lancamento.c.id, t_lancamento.c.protocolo_id, t_lancamento.c.numero_matriz,
            t_lancamento.c.data_inicio, t_lancamento.c.responsavel, t_lancamento.c.observacao,
            t_lancamento.c.criado_em, t_lancamento.c.usuario_id, t_lancamento.c.fazenda_id,
        ).where(t_lancamento.c.lote_id.is_(None))
    ).all()
    for lanc in pendentes:
        molde = moldes.get(lanc.protocolo_id)
        nome_base = molde.nome if molde else "Protocolo Sanitário"
        dia_inicial = molde.dia_inicial if molde else 0
        dias = etapas_por_protocolo.get(lanc.protocolo_id) or [dia_inicial]
        data_inicio = lanc.data_inicio if isinstance(lanc.data_inicio, date) else date.fromisoformat(str(lanc.data_inicio))
        resultado = conn.execute(
            t_lote.insert().values(
                protocolo_id=lanc.protocolo_id,
                nome_protocolo=gerar_nome_lancamento(nome_base, data_inicio, dia_inicial, max(dias)),
                data_inicio=lanc.data_inicio, responsavel=lanc.responsavel, observacao=lanc.observacao,
                ativo=True, criado_em=lanc.criado_em, usuario_id=lanc.usuario_id, fazenda_id=lanc.fazenda_id,
            )
        )
        lote_id = resultado.inserted_primary_key[0]
        conn.execute(t_lancamento.update().where(t_lancamento.c.id == lanc.id).values(lote_id=lote_id))

    aplicacoes_pendentes = conn.execute(
        sa.select(t_aplicacao.c.id, t_aplicacao.c.lancamento_id, t_aplicacao.c.etapa_id)
        .where(t_aplicacao.c.numero_matriz.is_(None))
    ).all()
    lancamentos_numero = {
        row.id: row.numero_matriz
        for row in conn.execute(sa.select(t_lancamento.c.id, t_lancamento.c.numero_matriz)).all()
    }
    for ap in aplicacoes_pendentes:
        conn.execute(
            t_aplicacao.update().where(t_aplicacao.c.id == ap.id).values(
                numero_matriz=lancamentos_numero.get(ap.lancamento_id),
                dia=etapa_dia_por_id.get(ap.etapa_id),
            )
        )
    # Sem commit explícito: a conexão é a da própria transação do Alembic
    # (`op.get_bind()`), que ele commita ao fim da migração.


def downgrade() -> None:
    op.drop_index(op.f("ix_protocolo_sanitario_aplicacao_numero_matriz"), table_name="protocolo_sanitario_aplicacao")
    op.drop_index(op.f("ix_protocolo_sanitario_aplicacao_dia"), table_name="protocolo_sanitario_aplicacao")
    op.drop_column("protocolo_sanitario_aplicacao", "numero_matriz")
    op.drop_column("protocolo_sanitario_aplicacao", "dia")

    with op.batch_alter_table("protocolo_sanitario_lancamento") as batch_op:
        batch_op.drop_constraint("fk_protocolo_sanitario_lancamento_lote_id", type_="foreignkey")
    op.drop_index(op.f("ix_protocolo_sanitario_lancamento_lote_id"), table_name="protocolo_sanitario_lancamento")
    op.drop_column("protocolo_sanitario_lancamento", "lote_id")

    op.drop_index(op.f("ix_protocolo_sanitario_lote_fazenda_id"), table_name="protocolo_sanitario_lote")
    op.drop_index(op.f("ix_protocolo_sanitario_lote_ativo"), table_name="protocolo_sanitario_lote")
    op.drop_table("protocolo_sanitario_lote")
