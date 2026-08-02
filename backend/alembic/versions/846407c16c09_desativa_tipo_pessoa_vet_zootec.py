"""desativa_tipo_pessoa_vet_zootec

"Vet/Zootec." era um tipo de pessoa combinado, seedado por padrão em toda
fazenda (ver SEED_TIPOS_PESSOA), redundante com os dois tipos reais e já
existentes "Veterinário" e "Zootecnista" — sem uso real (já ficava de fora,
por exemplo, da lista TIPOS_DELEGAM_TAREFA em portal.py) e confuso no
seletor do Cadastro de Pessoas. Removido do código (não é mais seedado em
fazenda nova); esta migração desativa (sem apagar — preserva histórico de
qualquer Pessoa que porventura já tenha esse tipo marcado) qualquer linha
já existente em bancos antigos.

Revision ID: 846407c16c09
Revises: 97d68401d5b0
Create Date: 2026-08-02 16:48:03.502358

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '846407c16c09'
down_revision: Union[str, Sequence[str], None] = '97d68401d5b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("UPDATE tipo_pessoa SET ativo = 0 WHERE nome = 'Vet/Zootec.'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("UPDATE tipo_pessoa SET ativo = 1 WHERE nome = 'Vet/Zootec.'"))
