"""lancamento_pendente: registro_criado (G17 - desfazer aprovacao)

Coluna aditiva e nula, usada só pelo fluxo "Desfazer aprovação" (Configurações
› Aprovações — ver Parte 3, G17, do plano de fechamento dos 17 gaps de
editar/excluir). Guarda em JSON o(s) registro(s) que a aprovação de um
LancamentoPendente do Telegram materializou de fato, no formato
`[{"tipo": "<id do tipo no motor de exclusões>", "id": <pk>}, ...]`, ou
`{"reversivel": false, "motivo": "..."}` para fluxos que não criam entidade
com id (ex.: diagnóstico, morte/descarte). `aprovacoes.aprovar` passa a gravar
esse campo antes do commit; `POST /aprovacoes/{id}/desfazer` o lê para saber
o que reverter.

Revision ID: 20dc777765f9
Revises: e2f3a4b5c6d7
Create Date: 2026-08-07 20:19:21.358328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20dc777765f9'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lancamento_pendente', sa.Column('registro_criado', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('lancamento_pendente', 'registro_criado')
