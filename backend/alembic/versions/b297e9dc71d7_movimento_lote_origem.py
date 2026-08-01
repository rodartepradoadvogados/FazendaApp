"""movimento_lote: rastreabilidade de origem (manual x sugestão x automática)

`MovimentoLote.motivo` é texto livre/cadastrável (ex.: "Secagem", "Parto") e
o MESMO texto pode vir de uma troca manual (Rebanho > Movimentar animais) ou
de uma sugestão automática confirmada via pop-up de evento — hoje é
impossível diferenciar os dois só olhando o histórico. Adiciona `origem`
("manual" | "sugestao_confirmada" | "sugestao_automatica" | "sugestao_passiva"
| "importacao"), preenchido pelo próprio código que chama
POST /movimentacoes/mover (ver fazenda.models.animais.MovimentoLote para o
significado de cada valor) — nunca inferido do texto de `motivo`.

Backfill: linhas já existentes não têm como ser reclassificadas
retroativamente (o pop-up de confirmação é recente), então ficam com
"desconhecida" em vez de uma origem forçada/adivinhada.

Revision ID: b297e9dc71d7
Revises: 0c6ee077a772
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b297e9dc71d7'
down_revision: Union[str, Sequence[str], None] = '0c6ee077a772'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('movimento_lote', sa.Column('origem', sa.String(), nullable=True))
    # Histórico anterior a este campo: marca explicitamente como
    # "desconhecida" (não dá pra inferir de volta se foi manual ou automática).
    op.execute("UPDATE movimento_lote SET origem = 'desconhecida' WHERE origem IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('movimento_lote', 'origem')
