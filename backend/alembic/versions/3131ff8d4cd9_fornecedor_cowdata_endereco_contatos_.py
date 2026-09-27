"""fornecedor_cowdata: endereco/cidade/estado/cep/site, contatos, e fan-out inativo pra fazenda

Pedido do dono (set/2026): o cadastro de Fornecedores-padrão (Painel CowData)
ganha campos opcionais de localização (endereço/cidade/estado/CEP) e site, e
uma lista de contatos (vendedor/representante — nome/cargo/telefone/email,
zero ou mais por fornecedor).

Além disso, o dono pediu explicitamente para replicar aqui o MESMO padrão de
fan-out já usado pela Farmácia do Painel CowData
(`painel_cowdata_farmacia.py::_fan_out_medicamento`/`_criar_item_fanout`):
todo `FornecedorCowData` passa a existir também no cadastro de Fornecedor de
CADA fazenda-cliente ativa, sempre INATIVO (a fazenda decide se/quando
ativar para aparecer na lista dela e ficar disponível nas cotações próprias
dela). Confirmado explicitamente com o dono que isso é diferente da muralha
de PREÇO (PrecoBaseSugerido.fornecedor_escolhido_id) — aquela continua
intocada, nenhuma fazenda vê de qual fornecedor veio um preço-base sugerido;
esta migração é só sobre o CADASTRO do fornecedor em si, que passa a poder
ser conhecido/ativado por qualquer fazenda-cliente, com o dado que a própria
CowData já levantou (nome/CNPJ/telefone/e-mail) — nunca contatos/observações
internas do Painel CowData.

`Fornecedor` (fazenda) não tem colunas de endereço/cidade/estado/CEP/site —
diferente de `fornecedor_cowdata`, que ganhou essas colunas de verdade nesta
mesma migração. Por isso o fan-out compatibiliza essa parte dentro de
`observacoes` (mesmo espírito da migração 16e309720f31, que já fez isso pro
cadastro do Painel CowData antes de estas colunas existirem).

Casamento por NOME EXATO dentro da fazenda (mesma regra de
`_criar_item_fanout`) — nunca sobrescreve um Fornecedor que a fazenda já
tenha cadastrado com esse nome (mesmo risco de "Órfão" documentado na
Farmácia: nome digitado diferente não casa automaticamente; a fazenda pode
vincular manualmente depois via `Fornecedor.fornecedor_cowdata_id`, exposto
no cadastro dela).

Idempotente: casa por `Fornecedor.nome` normalizado dentro de cada
`fazenda_id`, e também por `Fornecedor.fornecedor_cowdata_id` já preenchido
(uma segunda rodada desta migração, ou o fan-out em runtime de um fornecedor
novo, nunca duplica).

Sem import de código da aplicação (mesmo padrão de sempre neste repo).

Revision ID: 3131ff8d4cd9
Revises: 16e309720f31
Create Date: 2026-09-27 09:00:00.000000

"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3131ff8d4cd9'
down_revision: Union[str, Sequence[str], None] = '16e309720f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ESPACOS = re.compile(r"\s+")


def _normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return _ESPACOS.sub(" ", sem_acento.lower()).strip()


def _montar_observacoes_fanout(row: dict) -> str:
    partes = []
    endereco_bits = [row.get("endereco"), row.get("cidade"), row.get("estado"), row.get("cep")]
    endereco_txt = ", ".join(b for b in endereco_bits if b)
    if endereco_txt:
        partes.append(f"Endereço: {endereco_txt}")
    if row.get("site"):
        partes.append(f"Site: {row['site']}")
    if row.get("observacoes"):
        partes.append(row["observacoes"])
    partes.append(
        "Cadastro sincronizado do catálogo de Fornecedores-padrão do Painel CowData — "
        "inativo por padrão; ative para usar nas suas próprias cotações."
    )
    return " | ".join(partes)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_fornecedor_cowdata = {c['name'] for c in insp.get_columns('fornecedor_cowdata')}
    for nome_coluna in ('site', 'endereco', 'cidade', 'estado', 'cep'):
        if nome_coluna not in colunas_fornecedor_cowdata:
            op.add_column('fornecedor_cowdata', sa.Column(nome_coluna, sa.String(), nullable=True))

    if 'fornecedor_cowdata_contato' not in insp.get_table_names():
        op.create_table(
            'fornecedor_cowdata_contato',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fornecedor_cowdata_id', sa.Integer(), nullable=False),
            sa.Column('nome', sa.String(), nullable=False),
            sa.Column('cargo', sa.String(), nullable=True),
            sa.Column('telefone', sa.String(), nullable=True),
            sa.Column('email', sa.String(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fornecedor_cowdata_id'], ['fornecedor_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            op.f('ix_fornecedor_cowdata_contato_fornecedor_cowdata_id'),
            'fornecedor_cowdata_contato', ['fornecedor_cowdata_id'],
        )

    colunas_fornecedor = {c['name'] for c in insp.get_columns('fornecedor')}
    if 'fornecedor_cowdata_id' not in colunas_fornecedor:
        op.add_column('fornecedor', sa.Column('fornecedor_cowdata_id', sa.Integer(), nullable=True))
        op.create_index(
            op.f('ix_fornecedor_fornecedor_cowdata_id'), 'fornecedor', ['fornecedor_cowdata_id'],
        )

    # --- Fan-out retroativo: todo fornecedor-padrão já cadastrado passa a
    # existir (inativo) no Fornecedor de cada fazenda-cliente ativa. ---
    fazendas = conn.execute(
        sa.text("SELECT id FROM fazenda WHERE eh_empresa_cowdata = false AND ativa = true")
    ).all()
    if not fazendas:
        print("[fan-out fornecedores] nenhuma fazenda-cliente ativa encontrada — nada a fazer.")
        return

    fornecedores_cowdata = conn.execute(
        sa.text(
            "SELECT id, nome, cnpj_cpf, telefone, email, site, endereco, cidade, estado, cep, observacoes "
            "FROM fornecedor_cowdata"
        )
    ).mappings().all()
    if not fornecedores_cowdata:
        print("[fan-out fornecedores] nenhum fornecedor-padrão cadastrado ainda — nada a fazer.")
        return

    agora = datetime.utcnow()
    fornecedor_tabela = sa.table(
        'fornecedor',
        sa.column('fazenda_id', sa.Integer()), sa.column('nome', sa.String()), sa.column('tipo', sa.String()),
        sa.column('cnpj_cpf', sa.String()), sa.column('telefone', sa.String()), sa.column('email', sa.String()),
        sa.column('observacoes', sa.Text()), sa.column('ativo', sa.Boolean()),
        sa.column('fornecedor_cowdata_id', sa.Integer()), sa.column('criado_em', sa.DateTime()),
    )

    criados_total, pulados_total = 0, 0
    for (fazenda_id,) in fazendas:
        existentes_nome = {
            _normalizar(n) for (n,) in conn.execute(
                sa.text("SELECT nome FROM fornecedor WHERE fazenda_id = :fid"), {"fid": fazenda_id}
            ).all()
        }
        existentes_vinculo = {
            fcid for (fcid,) in conn.execute(
                sa.text(
                    "SELECT fornecedor_cowdata_id FROM fornecedor "
                    "WHERE fazenda_id = :fid AND fornecedor_cowdata_id IS NOT NULL"
                ),
                {"fid": fazenda_id},
            ).all()
        }
        novos = []
        for row in fornecedores_cowdata:
            if row["id"] in existentes_vinculo or _normalizar(row["nome"]) in existentes_nome:
                pulados_total += 1
                continue
            novos.append({
                "fazenda_id": fazenda_id, "nome": row["nome"], "tipo": "fornecedor",
                "cnpj_cpf": row["cnpj_cpf"], "telefone": row["telefone"], "email": row["email"],
                "observacoes": _montar_observacoes_fanout(row), "ativo": False,
                "fornecedor_cowdata_id": row["id"], "criado_em": agora,
            })
            existentes_nome.add(_normalizar(row["nome"]))
        if novos:
            op.bulk_insert(fornecedor_tabela, novos)
        criados_total += len(novos)

    print(
        f"[fan-out fornecedores] {criados_total} vínculo(s) criado(s) inativo(s) em "
        f"{len(fazendas)} fazenda(s), {pulados_total} já existiam (pulados)."
    )


def downgrade() -> None:
    # Mesmo espírito de 9af2806b02ba/16e309720f31: reverter cadastros que a
    # fazenda já pode ter ativado/editado depois do fan-out é mais arriscado
    # do que deixar como está. Colunas/tabela ficam; sem tentativa de apagar
    # os vínculos criados.
    pass
