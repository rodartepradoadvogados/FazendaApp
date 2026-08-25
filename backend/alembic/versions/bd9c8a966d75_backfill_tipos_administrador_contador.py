"""backfill: TipoPessoa Administrador/Contador em toda fazenda existente

"Administrador" e "Contador" foram adicionados a `TIPOS_PESSOA`
(backend/fazenda/api/routers/cadastro/pessoas.py) na PR #602, junto com o
filtro de "papel funcional" em `usePessoasAtivas` — que passou a exigir
Funcionário/Veterinário/Zootecnista/Administrador/Contador para aparecer em
qualquer lista de "Responsável".

`seed_tipos_pessoa` só semeia os tipos padrão UMA VEZ por fazenda (guardado
por `SeedFlag`, chave `tipos_pessoa_v1_fazenda_{id}`) — toda fazenda que já
existia antes da PR #602 já tinha essa flag marcada, então os dois tipos
novos NUNCA foram criados para ela. Resultado prático: numa fazenda já
existente, "Administrador"/"Contador" não aparecem nem como opção no
cadastro de pessoa (só o botão "+" manual resolveria) — e qualquer pessoa
cujo único papel de fato era administrativo/geral (ex.: o próprio dono da
fazenda, cadastrado como "Geral") sumiu silenciosamente de toda lista de
Responsável assim que o filtro entrou em produção.

Este backfill corrige a PARTE ESTRUTURAL do problema: garante que
"Administrador" e "Contador" existam como `TipoPessoa` selecionável em toda
fazenda que já tinha `tipo_pessoa` (e no piloto legado, `fazenda_id IS
NULL`) — idempotente, nunca duplica, nunca mexe em `Pessoa.tipo` de
ninguém. NÃO resolve sozinho o caso de uma pessoa específica que sumiu da
lista: quem for o responsável de fato (ex. o dono da fazenda) precisa,
depois desta migração, ser editado em Cadastro > Pessoas para marcar
"Administrador" (a opção passa a existir) — isso é dado de produção, uma
migração de schema não deve adivinhar nem reatribuir.

Revision ID: bd9c8a966d75
Revises: 0bfa9fbc2926
Create Date: 2026-08-25 10:40:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd9c8a966d75'
down_revision: Union[str, Sequence[str], None] = '0bfa9fbc2926'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIPOS_NOVOS = ["Administrador", "Contador"]


def upgrade() -> None:
    conn = op.get_bind()
    metadata = sa.MetaData()
    tipo_pessoa = sa.Table("tipo_pessoa", metadata, autoload_with=conn)

    # Toda fazenda_id que já tem ALGUM tipo_pessoa cadastrado (ou seja, já
    # passou por seed_tipos_pessoa em algum momento) — inclui NULL (piloto
    # legado de fazenda única).
    fazendas = conn.execute(sa.select(tipo_pessoa.c.fazenda_id).distinct()).scalars().all()

    for fazenda_id in fazendas:
        existentes = set(conn.execute(
            sa.select(tipo_pessoa.c.nome).where(
                tipo_pessoa.c.fazenda_id == fazenda_id if fazenda_id is not None
                else tipo_pessoa.c.fazenda_id.is_(None)
            )
        ).scalars().all())
        for nome in TIPOS_NOVOS:
            if nome not in existentes:
                # ativo/criado_em têm default só no lado Python do SQLModel
                # (Field(default=...)) — não são server_default, então um
                # INSERT via SQL puro (fora do ORM) precisa passar os dois
                # explicitamente, senão vira NOT NULL violation.
                conn.execute(tipo_pessoa.insert().values(
                    nome=nome, fazenda_id=fazenda_id, ativo=True, criado_em=datetime.utcnow(),
                ))


def downgrade() -> None:
    conn = op.get_bind()
    metadata = sa.MetaData()
    tipo_pessoa = sa.Table("tipo_pessoa", metadata, autoload_with=conn)
    conn.execute(tipo_pessoa.delete().where(tipo_pessoa.c.nome.in_(TIPOS_NOVOS)))
