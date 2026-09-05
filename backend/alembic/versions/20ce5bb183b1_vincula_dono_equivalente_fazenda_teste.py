"""vincula dono-equivalente à Fazenda Teste

Problema relatado pelo proprietário: a tela de escolha de fazenda no login
(POST /auth/login, ver fazenda/api/routers/auth.py::_fazendas_vinculadas)
só lista fazendas com vínculo em `usuario_fazenda` — e ninguém tem vínculo
com a "Fazenda Teste" (eh_teste=True, sandbox que recebe cópia da fazenda
real via fazenda/rules/replicacao_fazenda.py). Resultado: a tela mostrava
só "Jairo Nasser" + "Painel CowData", sem nenhum caminho até o sandbox.

Quem precisa entrar: o dono e o sócio, isto é, quem `fazenda.auth.
eh_email_dono_equivalente` já reconhece hoje (EMAILS_DONO_EQUIVALENTE) — o
MESMO critério usado em toda checagem de acesso equivalente ao proprietário
no resto do sistema. Por isso esta migração IMPORTA a constante de
`fazenda.auth` em vez de copiar os e-mails à mão: um nome de usuário muda
(já mudou antes — ver seed_email_dono_correcao_202607c em fazenda/auth.py),
o critério por e-mail é que é a fonte de verdade, e duplicar a lista aqui
seria só mais um lugar pra esquecer de atualizar. O import é seguro dentro
de uma migração: `fazenda/auth.py` é só constantes/funções puras (nenhum
efeito colateral de import) e `alembic/env.py` já importa `fazenda.database`/
`fazenda.models` de qualquer forma para o autogenerate funcionar.

Papel do vínculo: `contratante=True`, NÃO `consultor`/`contador` e nem os
três flags em False. Motivo (ver a docstring de UsuarioFazenda em
fazenda/models/multitenant.py): `consultor` e `contador` são vínculos
RESTRITOS por desenho — o primeiro é acesso de funcionário comum (não
administra a fazenda), o segundo cai direto no Painel do Contador em modo
só-leitura. Nenhum dos dois seria fiel ao objetivo do sandbox: o dono/sócio
precisam poder ADMINISTRAR a Fazenda Teste (vincular/desvincular usuário,
etc.) exatamente como administram a fazenda real, senão o teste deixa de
ser representativo. `contratante` é o único papel de UsuarioFazenda que
significa "usuário mestre desta fazenda" — é o que corresponde. (Vale notar
que `eh_email_dono_equivalente` já dá bypass total nas dependências de
autorização compartilhadas — exigir_dono, exigir_admin_ou_dono,
exigir_contratante_ou_dono — mas o vínculo em si também alimenta campos
públicos como `vinculo_contratante` em _fazenda_publica, consumidos pelo
frontend; sem o vínculo, esses campos ficam incorretamente False mesmo para
quem administra a fazenda de verdade.)

Idempotente e tolerante: verifica antes de inserir (a UniqueConstraint
uq_usuario_fazenda barraria de qualquer forma, mas sem estourar exceção);
se a tabela `fazenda` não tiver nenhuma linha com eh_teste=True, ou nenhum
`usuario.email` bater com EMAILS_DONO_EQUIVALENTE, não quebra — só reporta
no relatório final (mesmo estilo de 029227481e9e_backfill_fazenda_id_nulo).

Revision ID: 20ce5bb183b1
Revises: 697b23118c3c
Create Date: 2026-09-05 00:00:03.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20ce5bb183b1'
down_revision: Union[str, Sequence[str], None] = '697b23118c3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _emails_dono_equivalente() -> set[str]:
    """Import tardio (dentro da função, não no topo do módulo): só é chamado
    de fato quando `upgrade()`/`downgrade()` rodam, então um problema de
    import nesta constante nunca impede o `alembic` de sequer carregar o
    arquivo de versões (mesmo cuidado de fazenda/alembic/env.py ao importar
    fazenda.database)."""
    from fazenda.auth import EMAILS_DONO_EQUIVALENTE
    return EMAILS_DONO_EQUIVALENTE


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tabelas = set(insp.get_table_names())
    if 'fazenda' not in tabelas or 'usuario' not in tabelas or 'usuario_fazenda' not in tabelas:
        # Banco parcial (migração rodando fora de ordem, ou ambiente de teste
        # que não monta o schema inteiro) — nada a fazer, sem quebrar.
        print("[vincula_dono_fazenda_teste] tabela(s) ausente(s) (fazenda/usuario/usuario_fazenda) — pulando.")
        return

    fazendas_teste = conn.execute(sa.text(
        "SELECT id, nome FROM fazenda WHERE eh_teste = TRUE"
    )).fetchall()
    if not fazendas_teste:
        print("[vincula_dono_fazenda_teste] nenhuma fazenda com eh_teste=True encontrada — nenhum vínculo criado.")
        return

    emails = _emails_dono_equivalente()
    if not emails:
        # Nunca deveria acontecer (a constante sempre tem pelo menos o
        # e-mail do proprietário) — mas é exatamente o tipo de situação que
        # esta migração precisa tolerar em vez de estourar.
        print("[vincula_dono_fazenda_teste] EMAILS_DONO_EQUIVALENTE está vazia — nenhum vínculo criado.")
        return

    usuarios = conn.execute(
        sa.text("SELECT id, username, email FROM usuario WHERE lower(trim(email)) IN :emails").bindparams(
            sa.bindparam("emails", expanding=True)
        ),
        {"emails": sorted(e.lower() for e in emails)},
    ).fetchall()
    if not usuarios:
        print(f"[vincula_dono_fazenda_teste] nenhum usuário com e-mail em {sorted(emails)} encontrado — nenhum vínculo criado.")
        return

    criados: list[str] = []
    ja_existiam: list[str] = []
    for fazenda_id, fazenda_nome in fazendas_teste:
        for usuario_id, username, _email in usuarios:
            existe = conn.execute(
                sa.text(
                    "SELECT 1 FROM usuario_fazenda WHERE usuario_id = :uid AND fazenda_id = :fid"
                ),
                {"uid": usuario_id, "fid": fazenda_id},
            ).first()
            if existe:
                ja_existiam.append(f"{username} <-> {fazenda_nome}")
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO usuario_fazenda (usuario_id, fazenda_id, contratante, consultor, contador, criado_em) "
                    "VALUES (:uid, :fid, TRUE, FALSE, FALSE, CURRENT_TIMESTAMP)"
                ),
                {"uid": usuario_id, "fid": fazenda_id},
            )
            criados.append(f"{username} <-> {fazenda_nome}")

    print(f"[vincula_dono_fazenda_teste] vínculo(s) criado(s) (contratante=True): {len(criados)}")
    for linha in criados:
        print(f"  - {linha}")
    if ja_existiam:
        print(f"[vincula_dono_fazenda_teste] já existia(m) (pulado, idempotente): {len(ja_existiam)}")
        for linha in ja_existiam:
            print(f"  - {linha}")


def downgrade() -> None:
    """Remove só os vínculos que esta migração poderia ter criado — dono-
    equivalente + fazenda eh_teste=True, e só o vínculo `contratante`
    verdadeiro sem consultor/contador (a mesma combinação que o upgrade
    grava) — nunca um vínculo pré-existente com outro papel que porventura
    já existisse antes desta migração rodar."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tabelas = set(insp.get_table_names())
    if 'fazenda' not in tabelas or 'usuario' not in tabelas or 'usuario_fazenda' not in tabelas:
        return

    emails = _emails_dono_equivalente()
    if not emails:
        return

    resultado = conn.execute(
        sa.text(
            "DELETE FROM usuario_fazenda WHERE contratante = TRUE AND consultor = FALSE AND contador = FALSE "
            "AND fazenda_id IN (SELECT id FROM fazenda WHERE eh_teste = TRUE) "
            "AND usuario_id IN (SELECT id FROM usuario WHERE lower(trim(email)) IN :emails)"
        ).bindparams(sa.bindparam("emails", expanding=True)),
        {"emails": sorted(e.lower() for e in emails)},
    )
    print(f"[vincula_dono_fazenda_teste] downgrade: {resultado.rowcount or 0} vínculo(s) removido(s).")
