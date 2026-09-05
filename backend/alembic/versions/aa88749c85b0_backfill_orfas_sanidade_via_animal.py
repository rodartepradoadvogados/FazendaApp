"""backfill fazenda_id orfao em sanidade/cronograma via animal.numero

Medido em produção (04/09/2026): 121 linhas em `sanidade` e 3 em
`cronograma_sanitario_animal` com `fazenda_id IS NULL` — resíduo que a
migração 029227481e9e (backfill geral) não conseguiu fechar na época porque
já existiam 2+ fazendas reais cadastradas (fazenda #1 "Jairo Nasser" e a
fazenda de teste), e essas duas tabelas estavam em `_TABELAS_SEM_PAI` (sem
estratégia de derivação melhor que a fazenda única, que não se aplicava).
Sob o filtro estrito de `fazenda_id` (Passo 3 do retrofit, ver
fazenda/rules/visibilidade.py), essas linhas somem da tela das duas
fazendas sem erro nenhum — o mesmo sintoma do PR original, só que estas
duas tabelas ficaram de fora do fechamento por falta de uma estratégia (a).

Esta migração fecha a lacuna com uma derivação que NÃO existia em
029227481e9e: `numero_matriz -> animal.numero -> animal.fazenda_id`.
Funciona sem ambiguidade HOJE porque:

  • `animal.numero` tem índice ÚNICO GLOBAL (`ix_animal_numero`, criado na
    baseline e nunca relaxado por nenhuma migração anterior a esta) — cada
    número casa com NO MÁXIMO um animal. A migração seguinte a esta
    (animal_numero_unico_por_fazenda) é que troca essa unicidade para
    (fazenda_id, numero) — por isso ela tem que vir DEPOIS: derivar por
    `numero_matriz` só é seguro enquanto o número ainda for globalmente
    único.
  • `animal` não tem nenhuma linha com `fazenda_id` nulo hoje (todo animal
    já tem dona) — então, quando o `numero_matriz` casa com um animal, a
    fazenda vem sempre preenchida.

Estratégia por tabela:

  `sanidade`: direto por `numero_matriz -> animal.numero`.

  `cronograma_sanitario_animal`: primeiro tenta o PAI
  (`cronograma_id -> cronograma_sanitario.fazenda_id`, mesma técnica de
  029227481e9e — mais confiável, não depende de quantas fazendas existem);
  o que sobrar nulo (pai também nulo, ou cronograma_id órfão) cai para
  `numero_matriz -> animal.numero`.

Mesma disciplina de 029227481e9e: só atualiza quando a derivação encontra
EXATAMENTE um dono; o que não casar com nenhum animal (numero_matriz
digitado errado, animal excluído, etc.) fica nulo mesmo — sem chutar — e
entra no relatório impresso ao final.

Revision ID: aa88749c85b0
Revises: a1c3e7f0b2d4
Create Date: 2026-09-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa88749c85b0'
down_revision: Union[str, Sequence[str], None] = 'a1c3e7f0b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _derivar_via_numero_matriz(conn, tabela: str) -> int:
    """Preenche `fazenda_id` de `tabela` a partir de `animal.numero`, só
    quando o `numero_matriz` da linha casa com EXATAMENTE um animal (índice
    único global de `animal.numero` garante isso hoje) e esse animal já tem
    `fazenda_id` preenchido. Devolve quantas linhas foram tocadas."""
    resultado = conn.execute(sa.text(
        f"UPDATE {tabela} SET fazenda_id = ("
        f"  SELECT a.fazenda_id FROM animal a WHERE a.numero = {tabela}.numero_matriz"
        f") WHERE fazenda_id IS NULL AND ("
        f"  SELECT COUNT(*) FROM animal a WHERE a.numero = {tabela}.numero_matriz"
        f") = 1 AND EXISTS ("
        f"  SELECT 1 FROM animal a WHERE a.numero = {tabela}.numero_matriz AND a.fazenda_id IS NOT NULL"
        f")"
    ))
    return resultado.rowcount or 0


def _derivar_do_pai_cronograma(conn) -> int:
    resultado = conn.execute(sa.text(
        "UPDATE cronograma_sanitario_animal SET fazenda_id = ("
        "  SELECT cs.fazenda_id FROM cronograma_sanitario cs WHERE cs.id = cronograma_sanitario_animal.cronograma_id"
        ") WHERE fazenda_id IS NULL AND EXISTS ("
        "  SELECT 1 FROM cronograma_sanitario cs"
        "  WHERE cs.id = cronograma_sanitario_animal.cronograma_id AND cs.fazenda_id IS NOT NULL"
        ")"
    ))
    return resultado.rowcount or 0


def _contar_nulos(conn, tabela: str) -> int:
    return conn.execute(sa.text(f"SELECT COUNT(*) FROM {tabela} WHERE fazenda_id IS NULL")).scalar() or 0


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Mesma cautela de 029227481e9e: nem todo ambiente rodou exatamente as
    # mesmas migrações de criação (drift pré-existente) — pula em silêncio
    # se a tabela não existir, em vez de derrubar a migração inteira.
    tem_sanidade = insp.has_table('sanidade')
    tem_cronograma_animal = insp.has_table('cronograma_sanitario_animal')
    tem_animal = insp.has_table('animal')

    via_pai_cronograma = 0
    via_numero_matriz_sanidade = 0
    via_numero_matriz_cronograma = 0

    if tem_sanidade and tem_animal:
        via_numero_matriz_sanidade = _derivar_via_numero_matriz(conn, 'sanidade')

    if tem_cronograma_animal:
        if insp.has_table('cronograma_sanitario'):
            via_pai_cronograma = _derivar_do_pai_cronograma(conn)
        if tem_animal:
            via_numero_matriz_cronograma = _derivar_via_numero_matriz(conn, 'cronograma_sanitario_animal')

    nulos_sanidade = _contar_nulos(conn, 'sanidade') if tem_sanidade else 0
    nulos_cronograma = _contar_nulos(conn, 'cronograma_sanitario_animal') if tem_cronograma_animal else 0

    # Relatório — mesma disciplina de 029227481e9e: stdout de upgrade() vai
    # direto pro terminal de quem roda `alembic upgrade head`, é o único
    # jeito de auditar depois o que foi recuperado e o que ficou pendente.
    print("[backfill sanidade/cronograma via animal] sanidade — via numero_matriz->animal: "
          f"{via_numero_matriz_sanidade} linha(s); AINDA NULO: {nulos_sanidade}")
    print("[backfill sanidade/cronograma via animal] cronograma_sanitario_animal — via PAI (cronograma): "
          f"{via_pai_cronograma} linha(s); via numero_matriz->animal: {via_numero_matriz_cronograma} linha(s); "
          f"AINDA NULO: {nulos_cronograma}")
    if nulos_sanidade or nulos_cronograma:
        print("[backfill sanidade/cronograma via animal] linhas pendentes não foram adivinhadas — "
              "numero_matriz não casou com nenhum animal (ou o animal casado também está sem fazenda_id, "
              "o que não deveria acontecer hoje). Revisar manualmente.")


def downgrade() -> None:
    # Não há como distinguir, depois do fato, "fazenda_id que já veio
    # preenchido" de "fazenda_id que esta migração preencheu" — reverter
    # devolveria a linha ao mesmo estado órfão que este backfill existe pra
    # corrigir. No-op documentado, mesma decisão de 029227481e9e.
    pass
