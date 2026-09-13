"""backfill dos 45 órfãos restantes: 38 atribuídos, 6 apagados, 1 intocado

Fecha o resíduo que a migração 029227481e9e deixou para trás — e o motivo de
ela ter deixado está no próprio critério dela:

    SELECT id FROM fazenda WHERE eh_empresa_cowdata IS NOT TRUE

Isso IGNORA `Fazenda.eh_teste`, a flag da fazenda sandbox que vive no mesmo
banco de produção. Com a sandbox contada como fazenda-cliente, aquela
migração enxergou "duas fazendas reais", caiu no ramo "não adivinha" (e fez
certo em não adivinhar) e os órfãos ficaram parados desde então.

A flag é levada a sério em outro ponto do sistema: `rules/replicacao_fazenda.py`
RECUSA com 409 qualquer destino sem ela, exatamente para a sincronização não
sobrescrever a fazenda-cliente real por engano. A migração de backfill
simplesmente não a conhecia. `_fazenda_cliente_unica()` abaixo corrige isso.

MEDIDO EM PRODUÇÃO (06/09/2026, banco `railway`) antes de escrever esta
migração: 3 fazendas — "Jairo Nasser" (real), "Fazenda Teste" (eh_teste) e
"CowData (empresa)" (eh_empresa_cowdata). UMA fazenda-cliente real. E a
sandbox está praticamente vazia: zero linhas em 11 das 14 tabelas com órfão,
o que descarta o único risco real de atribuir — que um órfão tivesse nascido
lá e fosse parar no dado da fazenda real.

As 14 tabelas foram classificadas pelo que CADA UMA é, não por um critério
único, porque em quatro casos atribuir seria PIOR que não fazer nada:

  A) NÃO É ÓRFÃO, É CATÁLOGO GLOBAL — `medicamento_categoria`. O modelo avisa
     contra exatamente isto: "inclusive quando NULO: um vínculo de medicamento
     GLOBAL tem que continuar global, senão ele passaria a 'pertencer' à
     primeira fazenda que o backfill encontrasse e sumiria do catálogo global
     de todas as outras". Esta migração NÃO TOCA nela — está aqui só para o
     próximo leitor não repetir o erro.

  B) RESÍDUO DE MIGRAÇÃO — `meta_recria` e os três `parametro_*`. O modelo de
     MetaRecria explica os quatro: "Era uma linha única (id=1) — passa a ser
     uma linha por fazenda". A órfã é a linha ANTIGA, e a fazenda real já tem
     a dela nas quatro. Atribuir criaria duplicata numa tabela cujo contrato é
     uma linha por fazenda (get-or-create). APAGA.

  C) LIXO TÉCNICO — `idempotencia_chave`, cache da fila offline do app de
     campo, "curto prazo, minutos a poucas horas até reconectar" (o próprio
     modelo já sugeria uma limpeza periódica, nunca implementada). APAGA.

  D) DADO REAL DA FAZENDA — as 8 tabelas restantes. ATRIBUI à fazenda-cliente
     única.

COLISÃO DE NOME: três tabelas do grupo D têm UNIQUE (nome, fazenda_id). Se uma
órfã tiver o mesmo nome de uma linha que a fazenda já tem, o UPDATE violaria a
constraint. Em vez de abortar a migração inteira, a órfã duplicada é APAGADA
(a linha da fazenda já é aquele mesmo cadastro) e o fato entra no relatório.

REVERSÍVEL, a pedido do dono: antes de tocar em qualquer linha, a migração
copia TODAS as órfãs de cada tabela afetada para uma tabela de checkpoint
(`ckpt_a4f8c1d92e07_<tabela>`, criada com `CREATE TABLE ... AS SELECT *`, que
preserva os tipos nativos em vez de serializar para texto). O `downgrade()`
reinsere as apagadas e devolve `fazenda_id = NULL` às atribuídas, pelo id.
As tabelas de checkpoint ficam no banco depois do upgrade, de propósito: são
elas o ponto de retorno, e ocupam algumas dezenas de linhas.

IDEMPOTENTE: roda de novo sem efeito — todo comando é condicionado a
`fazenda_id IS NULL`, e depois da primeira passada não sobra nenhuma.

SEGURA EM BANCO QUE NÃO É O DE PRODUÇÃO: se não houver exatamente UMA
fazenda-cliente (o caso da suíte de testes, que não monta multi-fazenda), o
grupo D é PULADO e nada é atribuído — nunca chuta um dono. Os grupos B e C,
que só apagam resíduo, também são pulados nesse caso, porque sem fazenda
provisionada não dá para saber se a linha nula é resíduo ou o dado normal
daquele ambiente.

Revision ID: a4f8c1d92e07
Revises: b7d41f6a2c93
Create Date: 2026-09-07 01:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4f8c1d92e07"
down_revision: Union[str, Sequence[str], None] = "b7d41f6a2c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (B) resíduo da época em que o parâmetro era uma linha única global.
_APAGAR_RESIDUO_DE_MIGRACAO: list[str] = [
    "meta_recria",
    "parametro_diaria_padrao",
    "parametro_manual_fazenda",
    "parametro_sugestao_movimentacao",
]

# (C) cache de curto prazo — linha órfã aqui é resto de requisição antiga.
_APAGAR_LIXO_TECNICO: list[str] = [
    "idempotencia_chave",
]

# (D) dado real: atribuir à fazenda-cliente única.
# `calendario_sanitario` vem antes de `cronograma_sanitario` de propósito: o
# cronograma é filho do calendário (FK), e a órfã do cronograma é a única
# linha da tabela — as duas são o mesmo evento e têm que acabar na mesma
# fazenda.
_ATRIBUIR: list[str] = [
    "calendario_sanitario",
    "cronograma_sanitario",
    "classificacao_lancamento",
    "conta_gerencial",
    "lancamento_anexo",
    "lancamento_item",
    "local_armazenamento",
    "tipo_documento",
]

# Do grupo D, as que têm UNIQUE (nome, fazenda_id) — ver COLISÃO DE NOME acima.
_COM_NOME_UNICO: list[str] = [
    "classificacao_lancamento",
    "local_armazenamento",
    "tipo_documento",
]


# Prefixo das tabelas de checkpoint. Uma por tabela afetada, com a cópia das
# órfãs ANTES da alteração — é por elas que o `downgrade()` volta atrás.
_CKPT = "ckpt_a4f8c1d92e07_"


def _tabelas_existentes(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _guardar_checkpoint(conn, tabela: str, existentes: set[str]) -> bool:
    """Copia as órfãs de `tabela` para a tabela de checkpoint, se ainda não houver uma.

    `CREATE TABLE ... AS SELECT *` funciona igual em PostgreSQL e SQLite e
    preserva os tipos das colunas — inclusive binário e data —, o que uma
    serialização para JSON não faria.

    O `IF NOT EXISTS` implícito (a checagem em `existentes`) é deliberado e
    importante: se esta migração for reaplicada depois de já ter rodado, não
    sobra nenhuma órfã, e recriar o checkpoint o substituiria por uma tabela
    VAZIA — destruindo justamente o ponto de retorno. O primeiro checkpoint é
    o que vale.

    Sem órfã, nenhum checkpoint é criado — e isso não é economia, é correção.
    Um banco montado só pelo Alembic (ambiente novo, restauração) chega aqui
    com a fazenda semeada e ZERO órfãs; criar 13 tabelas vazias ali deixaria
    no schema tabelas que não guardam nada e que nenhum model declara. A
    sentinela `test_migracao_tabelas_faltantes.py` exige que o schema depois
    de `upgrade head` seja exatamente o dos models, e é ela quem pegou isso.
    """
    if f"{_CKPT}{tabela}" in existentes:
        return False
    orfas = conn.execute(
        sa.text(f"SELECT count(*) FROM {tabela} WHERE fazenda_id IS NULL")  # noqa: S608 — nome vem das listas literais
    ).scalar()
    if not orfas:
        return False
    conn.execute(
        sa.text(  # noqa: S608 — nome vem das listas literais deste módulo
            f"CREATE TABLE {_CKPT}{tabela} AS "
            f"SELECT * FROM {tabela} WHERE fazenda_id IS NULL"
        )
    )
    return True


def _fazenda_cliente_unica(conn) -> int | None:
    """O id da única fazenda-CLIENTE, ou None se não houver exatamente uma.

    Descarta as duas que não são cliente:
      • `eh_empresa_cowdata` — a fazenda "lógica" da própria CowData;
      • `eh_teste` — a sandbox de demonstração, que vive no MESMO banco de
        produção. Foi justamente ela que a 029227481e9e contou como cliente,
        e por isso desistiu de atribuir.
    """
    if "fazenda" not in _tabelas_existentes(conn):
        return None
    colunas = {c["name"] for c in sa.inspect(conn).get_columns("fazenda")}
    condicoes = ["eh_empresa_cowdata IS NOT TRUE"]
    if "eh_teste" in colunas:  # banco antigo, anterior à flag: só ignora o filtro
        condicoes.append("eh_teste IS NOT TRUE")
    ids = [
        linha[0]
        for linha in conn.execute(sa.text(f"SELECT id FROM fazenda WHERE {' AND '.join(condicoes)}"))
    ]
    return ids[0] if len(ids) == 1 else None


def upgrade() -> None:
    conn = op.get_bind()
    existentes = _tabelas_existentes(conn)
    fazenda_id = _fazenda_cliente_unica(conn)

    if fazenda_id is None:
        print(
            "[backfill órfãos] Não há exatamente UMA fazenda-cliente neste banco "
            "(0, ou 2+ ignorando a CowData e a sandbox). Nada foi alterado — "
            "esta migração nunca chuta o dono de um registro."
        )
        return

    print(f"[backfill órfãos] fazenda-cliente única: id={fazenda_id}")

    # Checkpoint ANTES de qualquer alteração, para todas as tabelas que serão
    # tocadas — é o que torna o downgrade possível.
    afetadas = [
        tabela
        for tabela in _APAGAR_RESIDUO_DE_MIGRACAO + _APAGAR_LIXO_TECNICO + _ATRIBUIR
        if tabela in existentes
    ]
    guardadas = [t for t in afetadas if _guardar_checkpoint(conn, t, existentes)]
    print(
        f"[backfill órfãos] checkpoint guardado em {len(guardadas)} tabela(s) "
        f"`{_CKPT}*` — o downgrade volta por elas."
    )

    apagadas: dict[str, int] = {}
    for tabela in _APAGAR_RESIDUO_DE_MIGRACAO + _APAGAR_LIXO_TECNICO:
        if tabela not in existentes:
            continue
        n = conn.execute(
            sa.text(f"DELETE FROM {tabela} WHERE fazenda_id IS NULL")  # noqa: S608 — nome vem da lista literal acima
        ).rowcount
        if n:
            apagadas[tabela] = n

    duplicadas: dict[str, int] = {}
    for tabela in _COM_NOME_UNICO:
        if tabela not in existentes:
            continue
        # A órfã cujo nome a fazenda JÁ tem é a mesma coisa que a linha dela:
        # apagar em vez de deixar o UPDATE abaixo abortar a migração inteira.
        #
        # Escrito SEM alias na tabela do DELETE de propósito: `DELETE FROM t o
        # WHERE o.x` é aceito pelo PostgreSQL e recusado pelo SQLite com
        # "near o: syntax error" — e a suíte aplica as migrações em SQLite
        # (ver database.py::create_db_and_tables). A forma abaixo, com
        # subconsulta em vez de alias correlacionado, roda nos dois.
        n = conn.execute(
            sa.text(  # noqa: S608 — idem
                f"DELETE FROM {tabela} WHERE fazenda_id IS NULL"
                f"  AND lower(trim(nome)) IN ("
                f"    SELECT lower(trim(nome)) FROM {tabela} WHERE fazenda_id = :fid)"
            ),
            {"fid": fazenda_id},
        ).rowcount
        if n:
            duplicadas[tabela] = n

    atribuidas: dict[str, int] = {}
    for tabela in _ATRIBUIR:
        if tabela not in existentes:
            continue
        n = conn.execute(
            sa.text(f"UPDATE {tabela} SET fazenda_id = :fid WHERE fazenda_id IS NULL"),  # noqa: S608 — idem
            {"fid": fazenda_id},
        ).rowcount
        if n:
            atribuidas[tabela] = n

    print(f"[backfill órfãos] ATRIBUÍDAS à fazenda {fazenda_id}: {sum(atribuidas.values())} linha(s)")
    for tabela, n in sorted(atribuidas.items()):
        print(f"  - {tabela}: {n}")
    print(f"[backfill órfãos] APAGADAS (resíduo de migração e cache): {sum(apagadas.values())} linha(s)")
    for tabela, n in sorted(apagadas.items()):
        print(f"  - {tabela}: {n}")
    if duplicadas:
        print(
            f"[backfill órfãos] APAGADAS por nome já existente na fazenda: "
            f"{sum(duplicadas.values())} linha(s)"
        )
        for tabela, n in sorted(duplicadas.items()):
            print(f"  - {tabela}: {n}")
    print(
        "[backfill órfãos] NÃO TOCADAS: medicamento_categoria e "
        "medicamento_classificacao — o NULL nelas é catálogo global e tem que "
        "continuar global (ver models/sanidade.py::MedicamentoCategoria)."
    )


def downgrade() -> None:
    """Volta o dado ao estado anterior, pelas tabelas de checkpoint.

    Para cada tabela afetada, na ordem inversa da do upgrade (o filho antes do
    pai não pode ser reinserido, então o pai vem primeiro na volta também):

      1. reinsere as linhas do checkpoint que não estão mais lá — as apagadas
         por resíduo, por cache e por nome já existente na fazenda;
      2. devolve `fazenda_id = NULL` às que continuam lá — as atribuídas.

    O passo 2 é o que fecha o caso das três tabelas com nome único, onde parte
    das órfãs foi apagada e parte atribuída: o checkpoint tem as duas, e cada
    uma cai no passo que lhe cabe.

    Se não houver checkpoint (a migração rodou num banco sem fazenda-cliente
    única e não alterou nada), não há o que desfazer.
    """
    conn = op.get_bind()
    existentes = _tabelas_existentes(conn)

    restauradas: dict[str, int] = {}
    desatribuidas: dict[str, int] = {}
    # Pai antes de filho: `calendario_sanitario` antes de `cronograma_sanitario`,
    # a mesma razão da ordem em `_ATRIBUIR`.
    for tabela in _ATRIBUIR + _APAGAR_RESIDUO_DE_MIGRACAO + _APAGAR_LIXO_TECNICO:
        ckpt = f"{_CKPT}{tabela}"
        if ckpt not in existentes or tabela not in existentes:
            continue

        # Colunas listadas explicitamente, e só as que existem nos dois lados:
        # se o esquema tiver mudado entre o upgrade e o downgrade, o INSERT
        # ainda funciona em vez de errar por posição de coluna.
        cols_ckpt = [c["name"] for c in sa.inspect(conn).get_columns(ckpt)]
        cols_tab = {c["name"] for c in sa.inspect(conn).get_columns(tabela)}
        cols = [c for c in cols_ckpt if c in cols_tab]
        lista = ", ".join(cols)

        n = conn.execute(
            sa.text(  # noqa: S608 — nomes vêm das listas literais deste módulo
                f"INSERT INTO {tabela} ({lista}) SELECT {lista} FROM {ckpt} "
                f"WHERE id NOT IN (SELECT id FROM {tabela})"
            )
        ).rowcount
        if n:
            restauradas[tabela] = n

        n = conn.execute(
            sa.text(  # noqa: S608 — idem
                f"UPDATE {tabela} SET fazenda_id = NULL "
                f"WHERE id IN (SELECT id FROM {ckpt}) AND fazenda_id IS NOT NULL"
            )
        ).rowcount
        if n:
            desatribuidas[tabela] = n

        conn.execute(sa.text(f"DROP TABLE {ckpt}"))  # noqa: S608 — idem

    print(
        f"[backfill órfãos] downgrade: {sum(restauradas.values())} linha(s) "
        f"reinserida(s), {sum(desatribuidas.values())} devolvida(s) a fazenda_id NULL."
    )
    for tabela in sorted(set(restauradas) | set(desatribuidas)):
        print(
            f"  - {tabela}: {restauradas.get(tabela, 0)} reinserida(s), "
            f"{desatribuidas.get(tabela, 0)} desatribuída(s)"
        )
