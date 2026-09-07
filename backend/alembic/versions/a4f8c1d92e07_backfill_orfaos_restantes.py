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


def _tabelas_existentes(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


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
    """Sem volta, e de propósito.

    O que foi apagado era resíduo e cache, e o que foi atribuído perdeu a
    informação de que um dia foi nulo — devolver `fazenda_id = NULL` não
    restauraria estado nenhum, só recriaria o problema que esta migração
    fechou. Reverter de verdade se faz por backup, não por downgrade.
    """
    pass
