"""backfill complementar fazenda_id: movimento_estoque via estoque pai

Complemento pontual à 029227481e9e, achado na varredura da ENTREGA B (PR
claude/migracoes-e-varredura-fazenda-id): `fazenda.api.routers.farmacia::
inicializar_estoque` (POST /farmacia/estoque/{id}/inicializar — "Estoque
Inicial / Primeira Compra") criava o `MovimentoEstoque` do lançamento SEM
`fazenda_id` nenhum (nem carimbava, nem tinha o parâmetro no endpoint) — bug
distinto do fechado no Passo 1 do PR claude/fazenda-id-raiz (que corrigiu o
resolvedor tolerante devolvendo None; aqui o campo simplesmente nunca era
passado pro construtor). `movimento_estoque` já está em `_TABELAS_SEM_PAI`
da 029227481e9e (que rodou o fallback de fazenda única antes desta correção
de código existir), então qualquer linha órfã criada por este bug DEPOIS
daquela migração e ANTES do deploy desta continuaria nula sem este
complemento.

Deriva do pai de verdade (`estoque.fazenda_id`, via `estoque_id`) em vez de
só repetir o fallback de fazenda única — mais preciso: o movimento pertence
à fazenda DONA do item de estoque movimentado, não a "a única fazenda que
existe hoje" (o que já dá no mesmo na instalação atual, mas é o dado
correto, não uma coincidência). O que sobrar sem `estoque_id` resolvível
cai no mesmo fallback de fazenda única da 029227481e9e; o que ainda assim
ficar nulo não é adivinhado — só reportado.

Revision ID: d1cbcec3b276
Revises: 4ede0ee68b09
Create Date: 2026-08-11 23:28:13.793241

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1cbcec3b276'
down_revision: Union[str, Sequence[str], None] = '4ede0ee68b09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fazenda_real_unica(conn) -> int | None:
    """Mesma lógica da 029227481e9e — id da única fazenda REAL cadastrada
    (ignora a fazenda "lógica" da CowData, eh_empresa_cowdata=True), ou None
    se não houver exatamente uma."""
    linhas = conn.execute(sa.text(
        "SELECT id FROM fazenda WHERE eh_empresa_cowdata IS NOT TRUE"
    )).fetchall()
    return linhas[0][0] if len(linhas) == 1 else None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('movimento_estoque') or not insp.has_table('estoque'):
        # Drift pré-existente (mesmo caso da 029227481e9e) — nada a fazer
        # num banco tão novo que nem essas tabelas de baseline existem ainda.
        print("[fazenda_id backfill complementar] movimento_estoque/estoque ausentes — pulado")
        return

    via_pai = conn.execute(sa.text(
        "UPDATE movimento_estoque SET fazenda_id = ("
        "  SELECT e.fazenda_id FROM estoque e WHERE e.id = movimento_estoque.estoque_id"
        ") WHERE fazenda_id IS NULL AND estoque_id IS NOT NULL AND EXISTS ("
        "  SELECT 1 FROM estoque e WHERE e.id = movimento_estoque.estoque_id AND e.fazenda_id IS NOT NULL"
        ")"
    )).rowcount or 0

    fazenda_unica_id = _fazenda_real_unica(conn)
    via_fallback = 0
    if fazenda_unica_id is not None:
        via_fallback = conn.execute(
            sa.text("UPDATE movimento_estoque SET fazenda_id = :fid WHERE fazenda_id IS NULL"),
            {"fid": fazenda_unica_id},
        ).rowcount or 0

    pendente = conn.execute(sa.text("SELECT COUNT(*) FROM movimento_estoque WHERE fazenda_id IS NULL")).scalar() or 0

    print(f"[fazenda_id backfill complementar] movimento_estoque via PAI (estoque): {via_pai} linha(s)")
    print(f"[fazenda_id backfill complementar] movimento_estoque via FAZENDA ÚNICA ({fazenda_unica_id!r}): {via_fallback} linha(s)")
    if pendente:
        print(f"[fazenda_id backfill complementar] movimento_estoque AINDA NULO (não adivinhado): {pendente} linha(s) — "
              "revisar manualmente (2+ fazendas reais e sem estoque_id resolvível)")
    else:
        print("[fazenda_id backfill complementar] movimento_estoque: nenhuma linha ficou nula.")


def downgrade() -> None:
    """Downgrade schema."""
    # Mesmo motivo da 029227481e9e: não há como distinguir "já vinha
    # preenchido" de "preenchido por este backfill" para reverter só o que
    # foi tocado, e desfazer voltaria a introduzir o próprio bug corrigido
    # aqui. No-op de propósito.
    pass
