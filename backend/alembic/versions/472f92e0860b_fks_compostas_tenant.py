"""120 FKs entre tabelas de fazenda viram compostas (col, fazenda_id)

Etapa 2 do plano aprovado pelo dono, depois do `fazenda_id NOT NULL`
(c8e2a4f70b13) — pré-requisito medido em `docs/security-audit/fks-compostas.md`:
com `fazenda_id` nulo a FK composta é INERTE (`MATCH SIMPLE`), então esta etapa
só fecha o furo de verdade depois daquela.

O QUE UMA FK COMPOSTA FECHA. Hoje `animal.lote_id -> lote.id` só garante que o
lote existe — em QUALQUER fazenda. Nada impede a fazenda 1 gravar um animal
apontando para um lote da fazenda 2: é a "referência cruzada" e o "oráculo de
existência" da seção 9 de `rls-proposta.md`. A FK composta
`(lote_id, fazenda_id) REFERENCES lote(id, fazenda_id)` fecha os dois: o lote
citado tem que existir E ser da MESMA fazenda que está citando.

NÚMERO CORRIGIDO NESTA MIGRAÇÃO, e por quê. O plano aprovado falava em 130
FKs / 53 UNIQUE, medidos contra o esquema que `SQLModel.metadata.create_all`
produziria — um banco hipotético, criado direto dos models. O banco real nasce
por Alembic, e os dois DIVERGEM: `animal.fazenda_id`, por exemplo, foi
acrescentada em 2024 pelo piloto multi-fazenda
(`f1a2b3c4d5e6_piloto_multi_fazenda.py`) como `op.add_column(nullable=True)`
simples, sem `ForeignKeyConstraint` — o padrão se repete em outras ~113
tabelas antigas, todas com a MESMA lacuna: `tabela.fazenda_id` não tem FK
nenhuma para `fazenda.id`. Medido em 09/09/2026, comparando o banco erguido
por `alembic upgrade head` contra o hipotético do `create_all`:

  - 120 FKs (não 130) já existem HOJE entre duas tabelas de fazenda e viram
    compostas aqui — é o que esta migração faz, e são simples de verdade,
    conferidas em `pg_constraint`;
  - 51 UNIQUE (não 53) novas, uma por tabela pai distinta;
  - 10 pares (`alimento->estoque`, `foto_campo->animal`, entre outros) que o
    modelo declara com `foreign_key=` mas NÃO TÊM constraint nenhuma no banco
    — nem simples. Mesma causa-raiz das ~113: coluna nascida sem FK. FICAM DE
    FORA desta migração de propósito: compor do zero uma relação que nunca
    foi imposta exige primeiro conferir se o dado de produção já a viola (o
    que seria, por si, um vazamento entre fazendas achado no processo) — é
    trabalho carregado o bastante para merecer sua própria migração, e está
    registrado em `docs/security-audit/fks-compostas.md` como pendência.

As ~113 `tabela.fazenda_id -> fazenda.id` ausentes também ficam de fora: não
são candidatas a composição (`fazenda` não tem `fazenda_id` — não há o que
compor), e resolvê-las é uma frente própria, de escopo e risco diferentes
(são ~113 tabelas, contra as 51 daqui).

O QUE FICA SIMPLES, DE PROPÓSITO: as FKs cujo pai é catálogo global (26 nesta
medição, eram 31 antes — o esquema mudou entre uma medição e outra) continuam
como estavam. Ver achado 1 do documento: compor ali quebraria a Farmácia, a
biblioteca de alimentos e o sanitário, porque a chave do pai global é
`(id, NULL)` e não casa com `(id, <qualquer fazenda>)`.

DESCOBERTA DINÂMICA, e não uma lista escrita à mão — mesmo motivo da migração
anterior: tabela nova com uma FK entre duas tabelas de fazenda entra sozinha
na conta no próximo boot, em vez de ficar de fora até alguém lembrar.

NUNCA ABORTA O BOOT, pela mesma razão de sempre: esta migração roda dentro de
`_aplicar_alembic()`, chamada no lifespan da API. Cada UNIQUE e cada
composição de FK corre no seu próprio SAVEPOINT. A UNIQUE nunca deveria falhar
por dado duplicado (a coluna `id` já é chave primária — `(id, fazenda_id)` é
unicidade automática), mas o savepoint cobre lock/contenção mesmo assim. A
composição de FK É a que pode falhar de verdade: se alguma linha em produção
tem `filha.fazenda_id` diferente do `fazenda_id` do pai que ela referencia —
ou seja, uma referência cruzada entre fazendas ATIVA hoje — o
`ADD CONSTRAINT` valida o dado existente e recusa. Essa falha é justamente o
tipo de vazamento que a auditoria procura, e por isso é PULADA com o motivo
relatado, nunca escondida: a tabela continua com a FK simples de antes (o
savepoint desfaz o DROP junto com o ADD que falhou — nunca fica sem nenhuma
FK), e vira decisão de gente.

Revision ID: 472f92e0860b
Revises: c8e2a4f70b13
Create Date: 2026-09-09 08:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "472f92e0860b"
down_revision: Union[str, Sequence[str], None] = "c8e2a4f70b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mesma lista de `c8e2a4f70b13_fazenda_id_not_null.py`, duplicada de propósito
# — migrações não se importam entre si neste projeto (nenhuma outra faz, e
# uma migração antiga precisa continuar rodando sozinha mesmo que a lista
# mude depois). Onde o nulo é LEGÍTIMO ("de todas as fazendas"): compor uma FK
# contra um desses pais quebraria a Farmácia, a biblioteca de alimentos e o
# sanitário (achado 1, `fks-compostas.md`).
_CATALOGO_GLOBAL: frozenset[str] = frozenset({
    "principio_ativo",
    "doenca",
    "indicacao_terapeutica",
    "medicamento_comercial",
    "categoria_estoque",
    "finalidade_estoque",
    "unidade_estoque",
    "unidade_embalagem_estoque",
    "unidade_medida_embalagem_estoque",
    "laboratorio",
    "categoria_medicamento",
    "classificacao_medicamento_cad",
    "servico_cadastro",
    "parametro_fazenda",
    "medicamento_principio_ativo",
    "alimento_nutricional",
    "medicamento_categoria",
    "medicamento_classificacao",
})


class _Pular(Exception):
    """Motivo para deixar uma FK/UNIQUE como está — não é erro, é decisão."""


def _fks_simples_entre_tabelas_de_fazenda(conn) -> list[dict]:
    """FKs de UMA coluna, hoje simples, entre duas tabelas que têm
    `fazenda_id` e cujo pai não é catálogo global — as candidatas a compor.

    Sai do catálogo do banco (`pg_constraint`), e não de uma lista escrita à
    mão, pelo mesmo motivo do `c8e2a4f70b13`: tabela nova com uma FK dessas
    entra sozinha na conta no próximo boot.

    Só pega FK de UMA coluna: `MATCH SIMPLE`/dois-alvos não é o caso aqui —
    nenhuma das 120 medidas em 09/09/2026 é composta hoje —, e uma FK que já
    citasse `fazenda_id` na própria definição (a filha e o pai já compostos)
    não bate com o filtro de "exatamente 1 coluna" abaixo, então uma re-
    execução desta migração não tentaria compor de novo o que já compôs.
    """
    linhas = conn.execute(sa.text("""
        SELECT con.conname, filha.relname AS filha, pai.relname AS pai,
               array_agg(att.attname ORDER BY k.ord) AS colunas
        FROM pg_constraint con
        JOIN pg_class filha ON filha.oid = con.conrelid
        JOIN pg_class pai   ON pai.oid   = con.confrelid
        JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
        JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum
        WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace
        GROUP BY con.conname, filha.relname, pai.relname
        HAVING count(*) = 1
        ORDER BY filha.relname, con.conname
    """)).all()
    com_fazenda = {r[0] for r in conn.execute(sa.text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'fazenda_id'"
    ))}
    return [
        {"nome": l.conname, "filha": l.filha, "pai": l.pai, "coluna": l.colunas[0]}
        for l in linhas
        if l.filha in com_fazenda and l.pai in com_fazenda and l.pai not in _CATALOGO_GLOBAL
    ]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        print(
            "[FKs compostas] dialeto "
            f"{conn.dialect.name!r} — pulado. `ALTER TABLE ... ADD CONSTRAINT` "
            "com validação de dado existente é coisa de banco de verdade; "
            "produção é Postgres, e o efeito é testado contra um Postgres de "
            "verdade (tests/test_migracao_fks_compostas.py)."
        )
        return

    alvos = _fks_simples_entre_tabelas_de_fazenda(conn)
    pais_distintos = sorted({a["pai"] for a in alvos})

    # 1ª passada: UNIQUE(id, fazenda_id) em cada tabela pai distinta — tem que
    # existir ANTES de qualquer FK composta poder referenciá-la (inclusive
    # nas 4 auto-referências: a tabela é pai de si mesma).
    uniques_criadas: list[str] = []
    uniques_puladas: dict[str, str] = {}
    for pai in pais_distintos:
        nome_unique = f"uq_{pai}_id_fazenda_id"
        marca = conn.begin_nested()
        try:
            conn.execute(sa.text(
                f'ALTER TABLE "{pai}" ADD CONSTRAINT "{nome_unique}" UNIQUE (id, fazenda_id)'
            ))
        except sa.exc.SQLAlchemyError as erro:
            marca.rollback()
            uniques_puladas[pai] = f"{type(erro).__name__}: {str(erro.__cause__ or erro).strip()[:200]}"
            continue
        marca.commit()
        uniques_criadas.append(pai)

    # 2ª passada: compor as FKs cujo pai ganhou a UNIQUE acima. Pai que ficou
    # pulado não tem FK composta possível — as filhas dele entram no
    # relatório junto, com o motivo herdado.
    compostas: list[str] = []
    puladas: dict[str, str] = {}
    for alvo in alvos:
        if alvo["pai"] in uniques_puladas:
            puladas[alvo["nome"]] = f"UNIQUE do pai '{alvo['pai']}' não foi criada: {uniques_puladas[alvo['pai']]}"
            continue
        nome_novo = f"fk_{alvo['filha']}_{alvo['coluna']}_fazenda"
        marca = conn.begin_nested()
        try:
            conn.execute(sa.text(f'ALTER TABLE "{alvo["filha"]}" DROP CONSTRAINT "{alvo["nome"]}"'))
            conn.execute(sa.text(
                f'ALTER TABLE "{alvo["filha"]}" ADD CONSTRAINT "{nome_novo}" '
                f'FOREIGN KEY ({alvo["coluna"]}, fazenda_id) REFERENCES "{alvo["pai"]}" (id, fazenda_id)'
            ))
        except sa.exc.SQLAlchemyError as erro:
            # O savepoint desfaz o DROP junto com o ADD que falhou — a tabela
            # sai daqui com a FK SIMPLES de antes, nunca sem nenhuma. Uma
            # falha aqui quase sempre quer dizer uma linha cuja fazenda_id
            # diverge da do pai que ela referencia — uma referência cruzada
            # entre fazendas ativa hoje. É achado de auditoria, não bug desta
            # migração: relatado, não escondido.
            marca.rollback()
            puladas[alvo["nome"]] = f"{type(erro).__name__}: {str(erro.__cause__ or erro).strip()[:300]}"
            continue
        marca.commit()
        compostas.append(alvo["nome"])

    print(
        f"[FKs compostas] {len(uniques_criadas)} UNIQUE(id, fazenda_id) criada(s), "
        f"de {len(pais_distintos)} tabela(s) pai."
    )
    if uniques_puladas:
        print(f"[FKs compostas] {len(uniques_puladas)} UNIQUE PULADA(S):")
        for pai, motivo in sorted(uniques_puladas.items()):
            print(f"  - {pai}: {motivo}")
    print(f"[FKs compostas] {len(compostas)} FK(s) compostas, de {len(alvos)} alvo(s).")
    if puladas:
        print(
            f"[FKs compostas] {len(puladas)} FK(s) PULADA(S) — continuam simples, e cada "
            "uma precisa de decisão (investigar a referência cruzada, corrigir o dado, "
            "então rodar a composição à mão):"
        )
        for nome, motivo in sorted(puladas.items()):
            print(f"  - {nome}: {motivo}")
    print(
        "[FKs compostas] NÃO TOCADAS: as FKs cujo pai é catálogo global — ali o nulo "
        "de fazenda_id é legítimo e compor quebraria o compartilhamento."
    )


def downgrade() -> None:
    """Devolve cada FK composta por esta migração à forma simples, e solta as
    UNIQUE que ela criou — só o que ESTÁ composto/existe hoje, apurado no
    banco, não uma lista fixa: o downgrade roda num processo separado do
    upgrade, sem memória do que foi de fato aplicado ali (algumas podem ter
    sido puladas)."""
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        print(f"[FKs compostas] downgrade pulado — dialeto {conn.dialect.name!r}.")
        return

    compostas = conn.execute(sa.text("""
        SELECT con.conname, filha.relname AS filha, pai.relname AS pai,
               array_agg(att.attname ORDER BY k.ord) AS colunas
        FROM pg_constraint con
        JOIN pg_class filha ON filha.oid = con.conrelid
        JOIN pg_class pai   ON pai.oid   = con.confrelid
        JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
        JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum
        WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace
          AND con.conname LIKE 'fk\\_%\\_fazenda' ESCAPE '\\'
        GROUP BY con.conname, filha.relname, pai.relname
        HAVING count(*) = 2 AND 'fazenda_id' = ANY(array_agg(att.attname))
    """)).all()

    revertidas = 0
    for c in compostas:
        coluna = [col for col in c.colunas if col != "fazenda_id"][0]
        nome_simples = c.conname[: -len("_fazenda")]  # "fk_<filha>_<col>_fazenda" -> "fk_<filha>_<col>"
        conn.execute(sa.text(f'ALTER TABLE "{c.filha}" DROP CONSTRAINT "{c.conname}"'))
        conn.execute(sa.text(
            f'ALTER TABLE "{c.filha}" ADD CONSTRAINT "{nome_simples}" '
            f'FOREIGN KEY ({coluna}) REFERENCES "{c.pai}" (id)'
        ))
        revertidas += 1
    print(f"[FKs compostas] downgrade: {revertidas} FK(s) voltaram a ser simples.")

    pais = {c.pai for c in compostas}
    uniques_removidas = 0
    for pai in sorted(pais):
        nome_unique = f"uq_{pai}_id_fazenda_id"
        existe = conn.execute(sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = :n AND connamespace = 'public'::regnamespace"
        ), {"n": nome_unique}).first()
        if existe:
            conn.execute(sa.text(f'ALTER TABLE "{pai}" DROP CONSTRAINT "{nome_unique}"'))
            uniques_removidas += 1
    print(f"[FKs compostas] downgrade: {uniques_removidas} UNIQUE(id, fazenda_id) removida(s).")
