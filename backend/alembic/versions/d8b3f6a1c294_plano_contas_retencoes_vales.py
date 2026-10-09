"""plano de contas: 3.03.01.16 Retenções e 3.03.01.17 Vales e adiantamentos

Migração SÓ DE DADOS, aditiva e idempotente. Para cada fazenda que já tem o
plano de contas gerencial (existe a conta '3.03.01', Pessoal), insere duas
contas folha novas, com valores PRÓPRIOS de `linha_dre` e `natureza_fin` (a
herança por prefixo jogaria as duas na linha de gastos com pessoal):

    3.03.01.16  Retenções              NAO_ENTRA_NA_DRE  OBRIGACAO
                (retenção do caixa do funcionário; obrigação já reconhecida)
    3.03.01.17  Vales e adiantamentos  NAO_ENTRA_NA_DRE  ADIANTAMENTO
                (vales/adiantamentos a funcionários; valor a receber)

Regras:
  - só insere onde existe o grupo '3.03.01' (a migração NÃO cria o grupo);
  - se (codigo, fazenda_id) já existir, não toca — nem quando a conta tem
    OUTRO nome (só registra no log da migração);
  - não importa código da aplicação (os valores estão aqui, copiados de
    fazenda/rules/plano_padrao.py);
  - cada linha criada vira uma linha em `migracao_log_financeiro`
    (migracao='plano_contas_sistema_v1', campo='__criado__'): é por ela que o
    downgrade sabe o que foi criado por esta migração.

O downgrade remove SÓ as linhas que esta migração criou e que continuam como
ela as criou, e somente se nenhum lançamento, item, configuração de conta
automática, orçamento ou outra tabela com coluna de código de conta apontar
para elas (nesse caso a conta fica e o motivo vai para o log). O que o
plano de contas tinha antes (inclusive 16/17 criadas à mão) nunca é apagado.

Depois desta migração a reimportação do CSV do plano preserva as contas:
`upload.py::_upsert_plano_conta_gerencial` chama
`rules/plano_padrao.py::garantir_contas_do_sistema` ao final.

Revision ID: d8b3f6a1c294
Revises: d4e8b1c7a2f5
Create Date: 2026-10-09 15:00:00.000000

"""
import json
import logging
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8b3f6a1c294'
down_revision: Union[str, Sequence[str], None] = 'd4e8b1c7a2f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger('alembic.runtime.migration')

TABELA = 'plano_conta_gerencial'
LOG_TABELA = 'migracao_log_financeiro'
MIGRACAO = 'plano_contas_sistema_v1'
LOTE = 'alembic-d8b3f6a1c294'
GRUPO = '3.03.01'
# (codigo, nome, linha_dre, natureza_fin) — cópia deliberada de
# fazenda/rules/plano_padrao.py::CONTAS_DO_SISTEMA (migração não importa a aplicação).
CONTAS = (
    ('3.03.01.16', 'Retenções', 'NAO_ENTRA_NA_DRE', 'OBRIGACAO'),
    ('3.03.01.17', 'Vales e adiantamentos', 'NAO_ENTRA_NA_DRE', 'ADIANTAMENTO'),
)
COLUNAS_EXIGIDAS = {'id', 'fazenda_id', 'codigo', 'nome', 'ativa', 'atualizado_em', 'linha_dre', 'natureza_fin'}
COLUNAS_LOG = {'fazenda_id', 'lote', 'migracao', 'tabela', 'registro_id', 'campo',
               'valor_antes', 'valor_depois', 'motivo', 'criado_em', 'revertido_em'}
COLUNAS_DE_CODIGO = ('codigo_conta_gerencial', 'codigo_conta')


def _colunas(insp, tabela):
    return {c['name'] for c in insp.get_columns(tabela)}


def _plano_utilizavel(insp) -> bool:
    if not insp.has_table(TABELA):
        return False
    faltam = COLUNAS_EXIGIDAS - _colunas(insp, TABELA)
    if faltam:
        log.warning('%s: tabela %s sem as colunas %s; migração de dados ignorada.', revision, TABELA, sorted(faltam))
        return False
    return True


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _plano_utilizavel(insp):
        return
    com_log = insp.has_table(LOG_TABELA) and COLUNAS_LOG <= _colunas(insp, LOG_TABELA)
    agora = datetime.utcnow()

    fazendas = [r[0] for r in bind.execute(
        sa.text(f'SELECT DISTINCT fazenda_id FROM {TABELA} WHERE codigo = :g AND fazenda_id IS NOT NULL ORDER BY fazenda_id'),
        {'g': GRUPO},
    )]
    for fazenda_id in fazendas:
        for codigo, nome, linha_dre, natureza_fin in CONTAS:
            atual = bind.execute(
                sa.text(f'SELECT id, nome FROM {TABELA} WHERE codigo = :c AND fazenda_id = :f'),
                {'c': codigo, 'f': fazenda_id},
            ).first()
            if atual is not None:
                if (atual[1] or '').strip() != nome:
                    log.info('%s: fazenda %s já tem %s com o nome %r; não sobrescrevi.', revision, fazenda_id, codigo, atual[1])
                continue
            bind.execute(
                sa.text(
                    f'INSERT INTO {TABELA} (fazenda_id, codigo, nome, ativa, atualizado_em, linha_dre, natureza_fin) '
                    'VALUES (:f, :c, :n, :a, :t, :l, :nf)'
                ),
                {'f': fazenda_id, 'c': codigo, 'n': nome, 'a': True, 't': agora, 'l': linha_dre, 'nf': natureza_fin},
            )
            novo_id = bind.execute(
                sa.text(f'SELECT id FROM {TABELA} WHERE codigo = :c AND fazenda_id = :f'),
                {'c': codigo, 'f': fazenda_id},
            ).scalar()
            log.info('%s: fazenda %s ganhou %s (%s).', revision, fazenda_id, codigo, nome)
            if com_log and novo_id is not None:
                retrato = {'codigo': codigo, 'nome': nome, 'linha_dre': linha_dre, 'natureza_fin': natureza_fin}
                bind.execute(
                    sa.text(
                        f'INSERT INTO {LOG_TABELA} (fazenda_id, lote, migracao, tabela, registro_id, campo, '
                        'valor_antes, valor_depois, motivo, criado_em) '
                        'VALUES (:f, :lote, :mig, :tab, :rid, :campo, :antes, :depois, :motivo, :t)'
                    ),
                    {'f': fazenda_id, 'lote': LOTE, 'mig': MIGRACAO, 'tab': TABELA, 'rid': novo_id,
                     'campo': '__criado__', 'antes': 'null', 'depois': json.dumps({'retrato': retrato}, ensure_ascii=False),
                     'motivo': 'conta do sistema criada pela migração', 't': agora},
                )


def _referencias(bind, insp, codigo: str, fazenda_id) -> int:
    """Quantos registros, em qualquer tabela com coluna de código de conta,
    apontam para este código nesta fazenda."""
    total = 0
    for tabela in insp.get_table_names():
        if tabela == TABELA:
            continue
        colunas = _colunas(insp, tabela)
        for coluna in COLUNAS_DE_CODIGO:
            if coluna not in colunas:
                continue
            sql = f'SELECT COUNT(*) FROM "{tabela}" WHERE "{coluna}" = :c'
            params = {'c': codigo}
            if 'fazenda_id' in colunas and fazenda_id is not None:
                sql += ' AND fazenda_id = :f'
                params['f'] = fazenda_id
            total += bind.execute(sa.text(sql), params).scalar() or 0
    return total


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _plano_utilizavel(insp):
        return
    if not (insp.has_table(LOG_TABELA) and COLUNAS_LOG <= _colunas(insp, LOG_TABELA)):
        log.warning('%s: sem %s, não há como saber o que esta migração criou; nada removido.', revision, LOG_TABELA)
        return
    agora = datetime.utcnow()
    criadas = bind.execute(
        sa.text(
            f'SELECT id, fazenda_id, registro_id, valor_depois FROM {LOG_TABELA} '
            'WHERE migracao = :m AND tabela = :t AND campo = :c AND revertido_em IS NULL ORDER BY id'
        ),
        {'m': MIGRACAO, 't': TABELA, 'c': '__criado__'},
    ).fetchall()
    for log_id, fazenda_id, plano_id, depois in criadas:
        retrato = (json.loads(depois or 'null') or {}).get('retrato') or {}
        linha = bind.execute(
            sa.text(f'SELECT codigo, nome, linha_dre, natureza_fin, fazenda_id FROM {TABELA} WHERE id = :i'),
            {'i': plano_id},
        ).first()
        if linha is None:
            continue
        if linha[4] != fazenda_id or (linha[0], linha[1], linha[2], linha[3]) != (
            retrato.get('codigo'), retrato.get('nome'), retrato.get('linha_dre'), retrato.get('natureza_fin'),
        ):
            log.info('%s: conta %s da fazenda %s foi alterada depois; mantida.', revision, linha[0], fazenda_id)
            continue
        n = _referencias(bind, insp, linha[0], fazenda_id)
        if n:
            log.info('%s: conta %s da fazenda %s tem %s registro(s) apontando; mantida.', revision, linha[0], fazenda_id, n)
            continue
        bind.execute(sa.text(f'DELETE FROM {TABELA} WHERE id = :i'), {'i': plano_id})
        bind.execute(
            sa.text(f'UPDATE {LOG_TABELA} SET revertido_em = :t WHERE id = :i'),
            {'t': agora, 'i': log_id},
        )
        log.info('%s: conta %s da fazenda %s removida.', revision, linha[0], fazenda_id)
