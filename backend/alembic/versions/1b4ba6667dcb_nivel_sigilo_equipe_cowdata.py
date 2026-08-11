"""nível de sigilo por conta da Equipe CowData (#132)

Adiciona PermissaoEquipeCowData.nivel_sigilo (básico/técnico/total — quanto
de uma fazenda-cliente o membro enxerga numa sessão de suporte) e
SessaoAcessoSuporte.nivel_sigilo/AuditoriaAcessoSuporte.nivel_sigilo (o nível
vigente gravado na hora em que a sessão abre, para auditoria posterior).
Quem já existe recebe o nível MAIS restritivo ("basico") — nunca abrir
acesso retroativamente numa migração.

Também remove usuario.nivel_sigilo_maximo — o placeholder dormente criado em
d7e8f9a0b1c2 ("Próximo passo: nível de sigilo por conta", ver Confiança e
LGPD no Painel CowData) para este mesmo controle, nunca lido por nenhuma
rota. A implementação de verdade fica em PermissaoEquipeCowData (mesmo lugar
das outras permissões de um membro da Equipe CowData — areas,
pode_suspender_assinatura etc.), não em Usuario; manter os dois campos
seria dois conceitos concorrentes para a mesma coisa.

Revision ID: 1b4ba6667dcb
Revises: 810153450ce9
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b4ba6667dcb'
down_revision: Union[str, Sequence[str], None] = '810153450ce9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'permissao_equipe_cowdata',
        sa.Column('nivel_sigilo', sa.String(), nullable=False, server_default='basico'),
    )
    op.add_column(
        'sessao_acesso_suporte',
        sa.Column('nivel_sigilo', sa.String(), nullable=False, server_default='basico'),
    )
    op.add_column(
        'auditoria_acesso_suporte',
        sa.Column('nivel_sigilo', sa.String(), nullable=True),
    )
    op.drop_column('usuario', 'nivel_sigilo_maximo')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('usuario', sa.Column('nivel_sigilo_maximo', sa.String(), nullable=True))
    op.drop_column('auditoria_acesso_suporte', 'nivel_sigilo')
    op.drop_column('sessao_acesso_suporte', 'nivel_sigilo')
    op.drop_column('permissao_equipe_cowdata', 'nivel_sigilo')
