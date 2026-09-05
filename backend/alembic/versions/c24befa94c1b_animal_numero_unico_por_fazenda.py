"""animal.numero: unicidade passa a ser POR FAZENDA

`animal.numero` era único no banco INTEIRO (`ix_animal_numero`, criado na
baseline) — errado para multi-tenant: duas fazendas diferentes têm cada uma,
legitimamente, uma vaca "100". Além de errado, bloqueia a replicação da
fazenda #1 pra fazenda de teste (outra frente do retrofit) — não dá pra
copiar um animal "100" pra uma fazenda que já tem o dela.

Troca a unicidade global por composta `(fazenda_id, numero)` — duas fazendas
podem repetir o número, mas a MESMA fazenda continua barrada de duplicar.
Mantém um índice não-único em `numero` sozinho: várias buscas hoje ainda
casam só pelo número, sem filtrar fazenda (ver relatório da migração no
final da tarefa "fundação" — auditoria completa de quem assume `numero`
como identificador global; não é escopo desta migração corrigir essas
rotas, só preservar a performance da busca que elas já fazem).

PRÉ-REQUISITO (por isso esta migração só roda depois de aa88749c85b0): a
derivação de `sanidade`/`cronograma_sanitario_animal` via
`numero_matriz -> animal.numero` só é inequívoca ENQUANTO `animal.numero`
ainda for único globalmente — depois desta migração, o mesmo número pode
apontar para animais de fazendas diferentes e aquela derivação vira
ambígua. A ordem das duas migrações garante que o backfill aconteceu
enquanto a garantia ainda valia.

Trava de segurança: medimos hoje que NENHUMA linha de `animal` tem
`fazenda_id` nulo, mas essa migração não confia cegamente nisso — se
alguma linha nula aparecer (drift, ambiente diferente do medido), o banco
trataria cada `fazenda_id IS NULL` como um valor distinto no índice
composto (NULL nunca é igual a NULL) e deixaria passar duplicata de
`numero` entre linhas órfãs sem ninguém perceber; a migração prefere
FALHAR com mensagem clara a criar um índice que finge garantir o que não
garante.

Revision ID: c24befa94c1b
Revises: aa88749c85b0
Create Date: 2026-09-05 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c24befa94c1b'
down_revision: Union[str, Sequence[str], None] = 'aa88749c85b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mesmo nome do índice antigo — só troca unique=True por False (segue
# casando com o que `SQLModel.metadata` gera pro Field(index=True) sem
# unique, ver fazenda/models/animais.py). A constraint composta usa o nome
# declarado no model (uq_animal_numero_fazenda) — mesma convenção já usada
# em colostragem_bezerra/centro_custo/etc pra essa troca "unique(x) global"
# -> "unique(x, fazenda_id)".
NOME_INDICE_NUMERO = 'ix_animal_numero'
NOME_CONSTRAINT_COMPOSTA = 'uq_animal_numero_fazenda'


def upgrade() -> None:
    conn = op.get_bind()

    # Trava de segurança: unique(fazenda_id, numero) com fazenda_id nulo não
    # protege nada — em Postgres e SQLite, NULL nunca é igual a NULL, então
    # duas linhas com o MESMO numero e fazenda_id ambos nulos passariam pela
    # constraint como se fossem distintas. Medimos hoje que não existe
    # nenhuma; falha alto e claro se isso mudar, em vez de deixar a
    # constraint mentir sobre a garantia que promete.
    orfaos = conn.execute(sa.text("SELECT COUNT(*) FROM animal WHERE fazenda_id IS NULL")).scalar() or 0
    if orfaos:
        raise RuntimeError(
            f"animal_numero_unico_por_fazenda: {orfaos} linha(s) de 'animal' com fazenda_id NULO — "
            "rode o backfill (029227481e9e / aa88749c85b0) e resolva manualmente o que sobrar antes "
            "de trocar a unicidade de 'numero' para (fazenda_id, numero). Nada foi alterado."
        )

    # Ainda dá pra existir duplicata DENTRO da mesma fazenda hoje (o índice
    # antigo era único global, então isso é impossível por definição — mas
    # não custa checar antes de criar a constraint nova, pra falhar com
    # mensagem legível em vez de um erro cru de constraint do banco).
    duplicatas = conn.execute(sa.text(
        "SELECT fazenda_id, numero, COUNT(*) c FROM animal GROUP BY fazenda_id, numero HAVING COUNT(*) > 1"
    )).fetchall()
    if duplicatas:
        exemplos = ", ".join(f"(fazenda={f}, numero={n}, {c}x)" for f, n, c in duplicatas[:10])
        raise RuntimeError(
            f"animal_numero_unico_por_fazenda: {len(duplicatas)} par(es) (fazenda_id, numero) duplicado(s) — "
            f"ex.: {exemplos}. Resolva manualmente antes de criar a constraint única composta."
        )

    with op.batch_alter_table('animal', schema=None) as batch_op:
        try:
            batch_op.drop_index(NOME_INDICE_NUMERO)
        except Exception:
            pass
        batch_op.create_index(NOME_INDICE_NUMERO, ['numero'], unique=False)
        batch_op.create_unique_constraint(NOME_CONSTRAINT_COMPOSTA, ['numero', 'fazenda_id'])


def downgrade() -> None:
    with op.batch_alter_table('animal', schema=None) as batch_op:
        batch_op.drop_constraint(NOME_CONSTRAINT_COMPOSTA, type_='unique')
        batch_op.drop_index(NOME_INDICE_NUMERO)
        batch_op.create_index(NOME_INDICE_NUMERO, ['numero'], unique=True)
