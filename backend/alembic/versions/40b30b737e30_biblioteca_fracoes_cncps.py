"""Biblioteca de alimentos — fracionamento CNCPS (carboidrato/proteína) e marcação de campo editado

Prepara a biblioteca de alimentos (aba "Biblioteca de referência") para as
futuras Etapas 8 (Modelo ruminal) e 9 (Aminoácidos) do wizard — NENHUMA das
duas existe ainda, esta migração só guarda o dado. Duas mudanças em
`alimento_nutricional`:

1. 22 colunas novas, todas `Float` opcionais — 8 frações de carboidrato
   (CA1-CA4, CB1-CB3, CC, % da matéria seca) + 5 frações de proteína
   (PA1-PB2, PC, % da proteína bruta) + 9 taxas de degradação (kd, %/h) —
   uma por fração que tem taxa própria, ver docstring de
   `CAMPOS_CNCPS_FRACIONAMENTO`/`AlimentoNutricional` em
   fazenda/models/formulacao.py para a decisão de quais frações têm kd e a
   citação da fonte (CNCPS v6.5).
2. `campos_editados_json` (Text opcional) — reaproveita a MESMA convenção de
   `dieta_simulacao_item.campos_editados_json` (não é um mecanismo novo):
   marca quais campos deste item já foram digitados à mão pela fazenda, em
   oposição a ainda serem o valor puxado da linha mestre CowData.

Revision ID: 40b30b737e30
Revises: 029227481e9e
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40b30b737e30'
down_revision: Union[str, Sequence[str], None] = '029227481e9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (nome da coluna, comentário curto) — só para legibilidade deste arquivo;
# todas nullable=True, mesmo padrão do resto dos campos nutricionais
# opcionais desta tabela (a esmagadora maioria dos alimentos não vai ter
# laudo com fracionamento CNCPS — nulo aqui significa "não informado", não
# zero, e o motor/tela precisam continuar distinguindo os dois).
_COLUNAS_CNCPS: list[tuple[str, str]] = [
    ('cncps_ca1_pct', 'CA1 - ácidos orgânicos, % da MS'),
    ('cncps_ca2_pct', 'CA2 - ácido lático, % da MS'),
    ('cncps_kd_ca2_pct_h', 'kd de CA2, %/h'),
    ('cncps_ca3_pct', 'CA3 - outros solúveis, % da MS'),
    ('cncps_kd_ca3_pct_h', 'kd de CA3, %/h'),
    ('cncps_ca4_pct', 'CA4 - açúcares, % da MS'),
    ('cncps_kd_ca4_pct_h', 'kd de CA4, %/h'),
    ('cncps_cb1_pct', 'CB1 - amido, % da MS'),
    ('cncps_kd_cb1_pct_h', 'kd de CB1, %/h'),
    ('cncps_cb2_pct', 'CB2 - fibra solúvel, % da MS'),
    ('cncps_kd_cb2_pct_h', 'kd de CB2, %/h'),
    ('cncps_cb3_pct', 'CB3 - FDN digestível, % da MS'),
    ('cncps_kd_cb3_pct_h', 'kd de CB3, %/h'),
    ('cncps_cc_pct', 'CC - FDN indigestível, % da MS'),
    ('cncps_pa1_pct', 'PA1 - amônia, % da PB'),
    ('cncps_pa2_pct', 'PA2 - peptídeos solúveis, % da PB'),
    ('cncps_kd_pa2_pct_h', 'kd de PA2, %/h'),
    ('cncps_pb1_pct', 'PB1 - proteína rapidamente degradável, % da PB'),
    ('cncps_kd_pb1_pct_h', 'kd de PB1, %/h'),
    ('cncps_pb2_pct', 'PB2 - proteína lentamente degradável, % da PB'),
    ('cncps_kd_pb2_pct_h', 'kd de PB2, %/h'),
    ('cncps_pc_pct', 'PC - proteína indisponível, % da PB'),
]


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('alimento_nutricional') as batch_op:
        for coluna, _descricao in _COLUNAS_CNCPS:
            batch_op.add_column(sa.Column(coluna, sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('campos_editados_json', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('alimento_nutricional') as batch_op:
        batch_op.drop_column('campos_editados_json')
        for coluna, _descricao in reversed(_COLUNAS_CNCPS):
            batch_op.drop_column(coluna)
