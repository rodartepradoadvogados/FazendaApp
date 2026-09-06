"""sete permissões de edição no Painel CowData (equipe)

Adiciona as sete colunas booleanas de PermissaoEquipeCowData que separam
CONSULTA de EDIÇÃO dentro do próprio Painel CowData — ver
PERMISSOES_EDICAO_PAINEL_COWDATA em fazenda/models/equipe_cowdata_acesso.py:

    pode_editar_cadastros_globais
    pode_editar_touros_naab
    pode_editar_farmacia
    pode_consultar_usuarios
    pode_editar_usuarios
    pode_controlar_acesso_usuarios
    pode_editar_news

O QUE ESTAVA ERRADO ANTES. O eixo `areas` (CSV) misturava as duas coisas:
ter a área "cadastros" ou "farmacia" dava VER e MEXER de uma vez. Não havia
como dar a um membro da equipe o catálogo de cadastros globais/farmácia/
touros só para consulta. A partir daqui `areas` responde só "ele vê esta
parte do painel?" e a coluna booleana responde "ele pode escrever aqui?";
toda rota de escrita exige as duas (fazenda.auth.exigir_permissao_painel_
cowdata), então a permissão nova é sempre camada A MAIS, nunca um desvio.

NINGUÉM GANHA NADA NESTA MIGRAÇÃO — decisão explícita do dono (set/2026:
"ninguém ganha nada; você libera depois"). As sete nascem FALSE para todo
membro que já existe, inclusive para quem hoje tem a área "cadastros" ou
"farmacia" e portanto HOJE consegue escrever: depois desta migração ele
passa a só consultar, até o dono marcar a permissão no cadastro de equipe.
Isso é uma perda de acesso deliberada, não um efeito colateral — é o pedido.
`server_default=sa.false()` cobre as linhas existentes sem UPDATE nenhum e,
por ser NOT NULL com default, também cobre qualquer linha escrita por código
antigo durante o deploy.

O dono-equivalente (EMAILS_DONO_EQUIVALENTE em fazenda/auth.py) nunca teve
linha nesta tabela e continua passando por cima de tudo — nada a migrar
para ele.

Revision ID: c3a91f4d20b7
Revises: b2f7c1a83d59
Create Date: 2026-09-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3a91f4d20b7"
down_revision: Union[str, Sequence[str], None] = "b2f7c1a83d59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUNAS = [
    "pode_editar_cadastros_globais",
    "pode_editar_touros_naab",
    "pode_editar_farmacia",
    "pode_consultar_usuarios",
    "pode_editar_usuarios",
    "pode_controlar_acesso_usuarios",
    "pode_editar_news",
]


def upgrade() -> None:
    """Upgrade schema."""
    for nome in COLUNAS:
        op.add_column(
            "permissao_equipe_cowdata",
            sa.Column(nome, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for nome in reversed(COLUNAS):
        op.drop_column("permissao_equipe_cowdata", nome)
