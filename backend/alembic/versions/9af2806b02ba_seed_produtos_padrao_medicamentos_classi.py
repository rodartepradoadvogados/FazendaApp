"""seed produtos-padrao de medicamentos + classificacoes/finalidades da fazenda-piloto

Três seeds aditivos ao catálogo do Painel CowData > Cotações
(fazenda/models/catalogo_cowdata.py), pedidos pelo dono depois de usar a
tela pela primeira vez:

1) Um `ProdutoPadrao` por `MedicamentoComercial` GLOBAL (`fazenda_id IS
   NULL` — mesmo padrão de `Touro`/`PrincipioAtivo`) que ainda não tem
   produto-padrão apontando pra ele: `nome=nome_comercial`,
   `medicamento_comercial_id=<seu id>`, `classificacao_id` = id de
   "Medicamentos e produtos veterinários" em `classificacao_cowdata`
   (buscado por nome, nunca hardcoded — essa linha já existe, semeada por
   d4f8a1c9e6b2), `ativo=True`. Idempotente: pula quem já tem
   ProdutoPadrao.medicamento_comercial_id apontando pra ele.

2) Toda `ClassificacaoCowData` que falte, comparada (por nome normalizado —
   minúsculas, sem acento, espaços colapsados) contra o cadastro PRÓPRIO da
   fazenda-piloto (Jairo Nasser / Fazenda Estreito Ponte de Pedra) em
   `CategoriaEstoque` (Administração > Configurações > Cadastro > Estoque >
   Classificação).

3) Mesma coisa para `FinalidadeCowData` × `FinalidadeEstoque` (Estoque >
   Finalidade) — NUNCA confundir com `rules.categorias.FINALIDADES_ESTOQUE`
   (enum fixo de 5 valores usado para validar `Estoque.finalidade`, sem
   relação nenhuma com este cadastro por fazenda).

A fazenda-piloto é achada por correspondência (case/acento-insensível) de
`Fazenda.nome` contra "Jairo Nasser" OU "Estreito Ponte de Pedra" — se achar
0 ou mais de 1 candidata (banco de dev/CI sem essa fazenda, ou nome
ambíguo), a etapa 2/3 é pulada sem erro (a 1 continua rodando normalmente,
não depende da fazenda). Tudo idempotente — seguro rodar de novo.

Sem import de código da aplicação (mesmo padrão de d4f8a1c9e6b2/
b3c1e9d24f07: migração nunca importa `fazenda.*`) — a normalização usada
pra comparar nomes abaixo é uma cópia local mínima de
`fazenda.rules.casamento_cadastro.normalizar` (só minúsculas/acento/espaço;
sem a lista de palavras-ruído de razão social — "ltda", "comercio" etc. —
que não faz sentido pra nome de categoria/finalidade de estoque).

Revision ID: 9af2806b02ba
Revises: d4f8a1c9e6b2
Create Date: 2026-09-25 23:30:00.000000

"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9af2806b02ba'
down_revision: Union[str, Sequence[str], None] = 'd4f8a1c9e6b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOME_CLASSIFICACAO_MEDICAMENTOS = "Medicamentos e produtos veterinários"
_PADROES_FAZENDA_PILOTO = ["Jairo Nasser", "Estreito Ponte de Pedra"]

_ESPACOS = re.compile(r"\s+")


def _normalizar(texto: str | None) -> str:
    """Cópia local mínima de casamento_cadastro.normalizar — ver docstring
    do módulo sobre por que não é importada da aplicação."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return _ESPACOS.sub(" ", sem_acento.lower()).strip()


def _seed_produtos_padrao_medicamentos(conn: sa.Connection) -> None:
    classificacao_id = conn.execute(
        sa.text("SELECT id FROM classificacao_cowdata WHERE nome = :nome"),
        {"nome": _NOME_CLASSIFICACAO_MEDICAMENTOS},
    ).scalar()
    if classificacao_id is None:
        print(
            f"[produtos-padrao medicamentos] classificação '{_NOME_CLASSIFICACAO_MEDICAMENTOS}' não "
            "encontrada em classificacao_cowdata — pulando (rode depois de d4f8a1c9e6b2 ter semeado)."
        )
        return

    medicamentos_globais = conn.execute(
        sa.text("SELECT id, nome_comercial FROM medicamento_comercial WHERE fazenda_id IS NULL")
    ).all()
    ja_vinculados = {
        row[0] for row in conn.execute(
            sa.text("SELECT medicamento_comercial_id FROM produto_padrao WHERE medicamento_comercial_id IS NOT NULL")
        ).all()
    }
    pendentes = [(med_id, nome) for med_id, nome in medicamentos_globais if med_id not in ja_vinculados]
    if not pendentes:
        print(f"[produtos-padrao medicamentos] nada a semear ({len(medicamentos_globais)} medicamento(s) global(is), todos já com produto-padrão).")
        return

    agora = datetime.utcnow()
    produto_padrao = sa.table(
        'produto_padrao',
        sa.column('nome', sa.String()), sa.column('unidade', sa.String()),
        sa.column('classificacao_id', sa.Integer()), sa.column('medicamento_comercial_id', sa.Integer()),
        sa.column('ativo', sa.Boolean()), sa.column('criado_em', sa.DateTime()),
    )
    op.bulk_insert(produto_padrao, [
        {
            "nome": nome_comercial, "unidade": None, "classificacao_id": classificacao_id,
            "medicamento_comercial_id": med_id, "ativo": True, "criado_em": agora,
        }
        for med_id, nome_comercial in pendentes
    ])
    print(f"[produtos-padrao medicamentos] {len(pendentes)} produto(s)-padrão criado(s) a partir de medicamento_comercial global.")


def _achar_fazenda_piloto(conn: sa.Connection) -> int | None:
    todas = conn.execute(sa.text("SELECT id, nome FROM fazenda")).all()
    padroes_normalizados = [_normalizar(p) for p in _PADROES_FAZENDA_PILOTO]
    candidatas = [
        (fid, nome) for fid, nome in todas
        if nome and any(padrao in _normalizar(nome) for padrao in padroes_normalizados)
    ]
    if len(candidatas) != 1:
        print(
            f"[classificacoes/finalidades cowdata] {len(candidatas)} fazenda(s) candidata(s) para "
            f"{_PADROES_FAZENDA_PILOTO!r} — pulando o seed de classificações/finalidades (precisa achar exatamente 1)."
        )
        return None
    fid, nome = candidatas[0]
    print(f"[classificacoes/finalidades cowdata] fazenda-piloto: id={fid} ({nome!r}).")
    return fid


def _seed_classificacoes_da_fazenda(conn: sa.Connection, fazenda_id: int) -> None:
    existentes = {_normalizar(n) for (n,) in conn.execute(sa.text("SELECT nome FROM classificacao_cowdata")).all()}
    categorias = conn.execute(
        sa.text("SELECT nome FROM categoria_estoque WHERE fazenda_id = :fid"), {"fid": fazenda_id}
    ).all()
    agora = datetime.utcnow()
    classificacao_cowdata = sa.table(
        'classificacao_cowdata',
        sa.column('nome', sa.String()), sa.column('ativo', sa.Boolean()), sa.column('criado_em', sa.DateTime()),
    )
    novas, vistos = [], set()
    for (nome,) in categorias:
        chave = _normalizar(nome)
        if not chave or chave in existentes or chave in vistos:
            continue
        vistos.add(chave)
        novas.append({"nome": nome, "ativo": True, "criado_em": agora})
    if novas:
        op.bulk_insert(classificacao_cowdata, novas)
    print(f"[classificacoes cowdata] {len(novas)} classificação(ões) nova(s) a partir do cadastro da fazenda-piloto ({len(categorias)} no total lá).")


def _seed_finalidades_da_fazenda(conn: sa.Connection, fazenda_id: int) -> None:
    existentes = {_normalizar(n) for (n,) in conn.execute(sa.text("SELECT nome FROM finalidade_cowdata")).all()}
    finalidades = conn.execute(
        sa.text("SELECT nome FROM finalidade_estoque WHERE fazenda_id = :fid"), {"fid": fazenda_id}
    ).all()
    agora = datetime.utcnow()
    finalidade_cowdata = sa.table(
        'finalidade_cowdata',
        sa.column('nome', sa.String()), sa.column('ativo', sa.Boolean()), sa.column('criado_em', sa.DateTime()),
    )
    novas, vistos = [], set()
    for (nome,) in finalidades:
        chave = _normalizar(nome)
        if not chave or chave in existentes or chave in vistos:
            continue
        vistos.add(chave)
        novas.append({"nome": nome, "ativo": True, "criado_em": agora})
    if novas:
        op.bulk_insert(finalidade_cowdata, novas)
    print(f"[finalidades cowdata] {len(novas)} finalidade(s) nova(s) a partir do cadastro da fazenda-piloto ({len(finalidades)} no total lá).")


def upgrade() -> None:
    conn = op.get_bind()

    _seed_produtos_padrao_medicamentos(conn)

    fazenda_id = _achar_fazenda_piloto(conn)
    if fazenda_id is not None:
        _seed_classificacoes_da_fazenda(conn, fazenda_id)
        _seed_finalidades_da_fazenda(conn, fazenda_id)


def downgrade() -> None:
    # Downgrade não tenta "adivinhar" quais linhas vieram deste seed pra
    # apagar de volta (mesmo espírito de outras migrações de seed neste
    # repo, ex.: b3c1e9d24f07/tourros_naab) — reverter um catálogo que pode
    # já ter sido editado/referenciado pela CowData depois do seed é mais
    # arriscado do que deixar as linhas paradas. No-op de propósito.
    pass
