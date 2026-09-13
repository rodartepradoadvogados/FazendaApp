"""Alimento/Estoque Fase P1: alimento_id do laudo, categoria direta no
Estoque e estoque preferido do Alimento

Fase P1 do refactor Alimento/Estoque (P0 = testes de caracterização
golden-master, PR #588) — três gaps estruturais, aditivos e reversíveis,
identificados no escopo do P0 e fechados aqui:

1. `AnaliseBromatologica.alimento_id` (a coluna já existia no schema, mas
   nunca era escrita pela API — ver comentário em `relatorio_migracao` §
   divergência de nome, fazenda/api/routers/alimentacao.py). O vínculo real
   de um laudo com o Alimento sempre foi por igualdade exata de string entre
   `AnaliseBromatologica.alimento` e `Alimento.nome`: renomear o Alimento
   "perdia" o laudo em silêncio no braço bromatológico de Formulação de
   Dietas (`/formulacao/alimentos/{id}/resolver`, que já prioriza
   `alimento_id` quando presente — ver formulacao_dietas.py). Este backfill
   resolve, quando possível, todo laudo já existente por esse mesmo casamento
   de nome, escopado por fazenda_id (incluindo NULL, piloto legado) — a
   MESMA resolução que a API passa a aplicar na criação de um laudo novo a
   partir de agora (ver `criar_analise_bromatologica`).

2. `Estoque.categoria_alimento_id` — nova coluna aditiva que permite
   categorizar um item de Estoque DIRETO, sem precisar primeiro passar pelo
   cadastro de Alimento (até aqui a única via — ver seção
   `produtos_sem_categoria` do relatório de conferência). Backfill: para todo
   item de Estoque já vinculado a um Alimento com categoria cadastrada, copia
   essa categoria pro item — um retrato de UMA VEZ (não uma derivação viva;
   mudar a categoria do Alimento depois não recalcula os itens já vinculados,
   fora de escopo desta fase).

3. `Alimento.estoque_preferido_id` — nova coluna aditiva, SEM backfill (fica
   NULL para todo Alimento já cadastrado — não há como inferir com segurança
   qual dos itens vinculados seria o "certo"). Permite que uma fazenda marque
   explicitamente qual item de Estoque recebe a baixa automática/consumo
   manual quando um Alimento tem 2+ itens vinculados — a ambiguidade
   documentada em TestEscolhaArbitrariaDeCandidato (T11,
   tests/test_migracao_alimento.py). NULL preserva o comportamento arbitrário
   de hoje exatamente como está, para qualquer Alimento que não usar o
   mecanismo novo.

Nenhuma das três mudanças altera o comportamento de nenhuma fazenda hoje —
são aditivas e só entram em ação quando alguém usa explicitamente um dos
três endpoints novos (POST /analise-bromatologica com alimento_id, PUT
/alimentacao/estoque/{id}/categoria, PUT
/alimentacao/alimentos/{id}/estoque-preferido).

Revision ID: e3bc1c978262
Revises: bd9c8a966d75
Create Date: 2026-08-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3bc1c978262'
down_revision: Union[str, Sequence[str], None] = 'bd9c8a966d75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cond_fazenda(coluna, fazenda_id):
    """`coluna == fazenda_id`, mas tratando NULL como o piloto legado de
    fazenda única — mesmo idioma do resto do backfill (ver
    bd9c8a966d75_backfill_tipos_administrador_contador.py)."""
    return coluna == fazenda_id if fazenda_id is not None else coluna.is_(None)


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column('estoque', sa.Column('categoria_alimento_id', sa.Integer(), nullable=True))
    op.add_column('alimento', sa.Column('estoque_preferido_id', sa.Integer(), nullable=True))

    metadata = sa.MetaData()
    analise = sa.Table('analise_bromatologica', metadata, autoload_with=conn)
    alimento = sa.Table('alimento', metadata, autoload_with=conn)
    estoque = sa.Table('estoque', metadata, autoload_with=conn)

    # ── 1) Backfill AnaliseBromatologica.alimento_id ──────────────────────
    # Só laudos ainda sem alimento_id (idempotente — rodar duas vezes não
    # muda nada na segunda). Escopado por fazenda_id (incluindo NULL): um
    # laudo só pode casar com um Alimento da MESMA fazenda, nunca de outra.
    fazendas_laudo = conn.execute(sa.select(analise.c.fazenda_id).distinct()).scalars().all()
    for fazenda_id in fazendas_laudo:
        nome_para_id = dict(conn.execute(
            sa.select(alimento.c.nome, alimento.c.id).where(_cond_fazenda(alimento.c.fazenda_id, fazenda_id))
        ).all())
        if not nome_para_id:
            continue
        laudos = conn.execute(
            sa.select(analise.c.id, analise.c.alimento).where(
                _cond_fazenda(analise.c.fazenda_id, fazenda_id), analise.c.alimento_id.is_(None),
            )
        ).all()
        for laudo_id, nome in laudos:
            alimento_id = nome_para_id.get(nome)
            if alimento_id is not None:
                conn.execute(analise.update().where(analise.c.id == laudo_id).values(alimento_id=alimento_id))

    # ── 2) Backfill Estoque.categoria_alimento_id ─────────────────────────
    # Cópia de UMA VEZ da categoria do Alimento vinculado, só onde o item
    # ainda não tem categoria própria e o Alimento vinculado já tem uma.
    itens = conn.execute(
        sa.select(estoque.c.id, estoque.c.alimento_id).where(
            estoque.c.alimento_id.is_not(None), estoque.c.categoria_alimento_id.is_(None),
        )
    ).all()
    alimento_ids = {aid for _, aid in itens}
    if alimento_ids:
        categorias_por_alimento = dict(conn.execute(
            sa.select(alimento.c.id, alimento.c.categoria_alimento_id).where(
                alimento.c.id.in_(alimento_ids), alimento.c.categoria_alimento_id.is_not(None),
            )
        ).all())
        for estoque_id, aid in itens:
            categoria_id = categorias_por_alimento.get(aid)
            if categoria_id is not None:
                conn.execute(
                    estoque.update().where(estoque.c.id == estoque_id).values(categoria_alimento_id=categoria_id)
                )

    # 3) `alimento.estoque_preferido_id` fica NULL para todo mundo — sem
    # backfill, de propósito (ver docstring do módulo).


def downgrade() -> None:
    conn = op.get_bind()
    metadata = sa.MetaData()
    analise = sa.Table('analise_bromatologica', metadata, autoload_with=conn)
    alimento = sa.Table('alimento', metadata, autoload_with=conn)

    # Desfaz só o que o backfill 1) fez: todo laudo cujo alimento_id casa,
    # por nome, com um Alimento existente da mesma fazenda — reprodutível (o
    # upgrade é determinístico, então rodar de novo chega no mesmo estado).
    # As colunas 2)/3) simplesmente são derrubadas logo abaixo, levando o
    # backfill delas junto.
    fazendas_laudo = conn.execute(sa.select(analise.c.fazenda_id).distinct()).scalars().all()
    for fazenda_id in fazendas_laudo:
        nomes_validos = set(conn.execute(
            sa.select(alimento.c.nome).where(_cond_fazenda(alimento.c.fazenda_id, fazenda_id))
        ).scalars().all())
        laudos = conn.execute(
            sa.select(analise.c.id, analise.c.alimento).where(
                _cond_fazenda(analise.c.fazenda_id, fazenda_id), analise.c.alimento_id.is_not(None),
            )
        ).all()
        for laudo_id, nome in laudos:
            if nome in nomes_validos:
                conn.execute(analise.update().where(analise.c.id == laudo_id).values(alimento_id=None))

    op.drop_column('alimento', 'estoque_preferido_id')
    op.drop_column('estoque', 'categoria_alimento_id')
