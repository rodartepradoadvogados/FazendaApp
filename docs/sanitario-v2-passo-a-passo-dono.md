# Sanitário preventivo v2 (PR #948): passo a passo do dono antes do merge

Execução pelo **dono**. Nada aqui é feito por código nem por agente. Nenhuma
senha ou URL de banco vai escrita em arquivo: os comandos leem as variáveis
que o Railway já guarda.

**Por que o cuidado:** o deploy roda as migrações sozinho no boot
(`fazenda/database.py::_aplicar_alembic`). Assim que o merge sobe, a migração
`s0a1r2q3v4o5` move o sanitário preventivo antigo para o schema
`arquivo_sanitario_2026` e apaga essas linhas das tabelas compartilhadas
(`sanidade`, `aplicacao_agendada`, `evento_realizado`, `parametro_fazenda`,
`checklist_template_item`). Alimentação, BST, indução de cio e curativo não
são tocados. Os testes provam isso em SQLite e em Postgres, mas quem confirma
no banco real é você.

## O que você precisa

- Railway CLI instalado e logado (`railway login`), com a pasta do repositório
  ligada ao projeto `ravishing-smile`, ambiente **`production`**
  (`railway link`; confira com `railway status`).
- O repositório na branch do PR: `git fetch origin && git checkout ccr-7b4e2a62-42rst5`.
  O relatório e a migração só existem nessa branch. O container de produção
  roda a `main` e ainda não tem esses arquivos.
- Python 3.12+ com `pip install -r backend/requirements.txt`.
- `pg_dump`/`pg_restore` **versão 16 ou maior** (a do servidor).

Por que rodar da sua máquina com `railway run` e não no console do Railway:
o console abre o container da `main`, onde o script ainda não existe.
`railway run` injeta as variáveis do serviço na sua máquina sem você copiar
nada. Use a URL **pública** do Postgres (`DATABASE_PUBLIC_URL`), porque a
interna (`*.railway.internal`) só funciona dentro do Railway.

Use a conexão do **dono das tabelas**, não a da aplicação. A aplicação
conecta como `cowdata_app`, sob RLS, e lá um SELECT sem fazenda definida
devolve **zero linhas, sem erro**. Um relatório rodado com ela mostraria
"nada a apagar" e seria falso. As variáveis do serviço **Postgres**
(`DATABASE_PUBLIC_URL`) usam o usuário dono.

## 1. Backup do Postgres

Faça **as duas** formas.

**1a. Backup nativo do Railway.** Abra o projeto e entre em
**production › serviço Postgres › aba Backups**. Clique em **Create Backup** e
dê o nome `antes-pr-948`. Espere aparecer como concluído. Se a aba não
existir no seu plano, siga só com o 1b.

**1b. Dump lógico (arquivo seu, fora do Railway):**

```bash
railway run --service Postgres -- sh -c 'pg_dump "$DATABASE_PUBLIC_URL" -Fc --no-owner -f cowdata_antes_pr948.dump'
ls -lh cowdata_antes_pr948.dump        # não pode ser 0 nem poucos KB
```

Guarde o arquivo no Drive, numa pasta que **não** seja o cofre. Ele tem dado
de cliente (LGPD).

**Conferir que o backup restaura** (num Postgres descartável na sua máquina,
nunca no de produção):

```bash
docker run -d --name pgteste -e POSTGRES_PASSWORD=teste -p 55432:5432 postgres:16
sleep 5
docker exec pgteste createdb -U postgres restauro
docker cp cowdata_antes_pr948.dump pgteste:/tmp/b.dump
docker exec pgteste pg_restore -U postgres -d restauro --no-owner /tmp/b.dump
docker exec pgteste psql -U postgres -d restauro -c "SELECT
  (SELECT count(*) FROM animal) animais, (SELECT count(*) FROM sanidade) sanidade,
  (SELECT count(*) FROM consumo_alimento) consumo, (SELECT count(*) FROM controle_leiteiro) leite,
  (SELECT version_num FROM alembic_version) versao"
```

Rode a mesma consulta em produção, só leitura:

```bash
railway run --service Postgres -- sh -c 'psql "$DATABASE_PUBLIC_URL" -c "SELECT (SELECT count(*) FROM animal) animais, (SELECT count(*) FROM sanidade) sanidade, (SELECT count(*) FROM consumo_alimento) consumo, (SELECT count(*) FROM controle_leiteiro) leite, (SELECT version_num FROM alembic_version) versao"'
```

Os números têm de bater, e a versão tem de ser `n5o6p7q8r9s0`. Avisos de
`pg_restore` sobre roles ou extensões são normais; erro em tabela não é.
No fim, apague o container: `docker rm -f pgteste`.

## 2. Relatório do que a migração vai arquivar (só leitura)

```bash
railway run --service Postgres -- sh -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" python backend/scripts/relatorio_sanitario_legado.py --amostras 20'
```

O script abre a transação em `READ ONLY`: o Postgres recusa qualquer escrita.
Ele usa o **mesmo critério** da migração, importado do próprio arquivo dela.
Se quiser guardar o resultado: acrescente `--json > relatorio_pr948.json`.

## 3. Como ler o resultado

A primeira linha deve dizer **"antes da migração (lendo o public)"**.

| Seção | O que significa | Esperado |
|---|---|---|
| Tabelas exclusivas | Tabelas do módulo antigo que vão **inteiras** para o arquivo (não são apagadas) | Contagens por fazenda; qualquer número é aceitável |
| Linhas das tabelas compartilhadas | Linhas que **saem** de `sanidade`, `aplicacao_agendada` etc. (copiadas para o arquivo antes) | Só vacinas e exames preventivos |
| Sanidade por motivo | Por que cada linha sai: natureza preventivo, vínculo com cronograma, vacina pré-parto (D2), vacina Ideagri (D1) | Coerente com o que você lançou |
| **Ficam no public** | `sanidade_bst`, `sanidade_inducao_cio`, `sanidade_total_depois` | BST e indução com a contagem que você reconhece |
| D3 | Protocolos de etapas "preventivo" que viram "curativo" | Os que você conhece |
| Amostras | Linhas reais que vão para o arquivo | Só vacina/exame preventivo |

**Sinal de PARE.** Se aparecer qualquer linha de **BST** (produto Boostin,
Lactotropin, somatotropina, "bst") ou de **Indução de cio** nas **amostras**
ou em "Sanidade por motivo", não faça o merge. Também pare se o total de
`sanidade_bst` ou `sanidade_inducao_cio` for **menor** do que o que você
sabe que existe. Em qualquer desses casos, a migração arquivaria um dado que
deve ficar. Guarde a saída e mande para revisão. O critério precisa ser
ajustado no PR antes do merge. Não ajuste no banco à mão.

**Também pare se tudo vier zero** e você sabe que há vacinas lançadas: é
quase certo que a conexão usada foi a da aplicação (RLS). Confira que o
comando usou `--service Postgres` e `DATABASE_PUBLIC_URL`.

Linhas arquivadas **não somem**: ficam no schema `arquivo_sanitario_2026`,
fora do alcance da API. Para exportar em JSON depois da migração, use
`backend/scripts/exportar_arquivo_sanitario.py`.

## 4. Como reverter

**Antes do merge:** nada a reverter. Os passos 1 a 3 não escrevem no banco.

**Depois do merge, se algo der errado.** A ordem importa.

1. **Volte o banco primeiro, com o código do PR.** Os arquivos da migração só
   existem nele:
   ```bash
   git checkout ccr-7b4e2a62-42rst5
   railway run --service Postgres -- sh -c 'cd backend && DATABASE_URL="$DATABASE_PUBLIC_URL" python -m alembic downgrade n5o6p7q8r9s0'
   ```
   Isso devolve as tabelas e linhas antigas, a finalidade "preventivo" dos
   protocolos e as FKs. Também **apaga** as tabelas novas `sanitario_*` e as
   colunas `controle_leiteiro.destino_leite` e `sanitario_registro_id`, ou
   seja, o que foi lançado no módulo novo entre o deploy e a reversão. Os
   dados de alimentação não são tocados. A volta completa (subir, descer,
   subir) foi testada em Postgres 16 com dados de alimentação e com
   sanidade mista.
2. **Depois** reverta o código. No GitHub, abra o PR mesclado e clique em
   **Revert**. Mescle o PR de reversão. O Railway redeploya a `main` antiga,
   que já encontra o banco em `n5o6p7q8r9s0`.
3. **Último recurso:** restaure o backup do passo 1. Use o **Backups ›
   Restore** do Railway, ou `pg_restore` num banco novo. Atenção: isso perde
   **tudo** o que foi gravado em qualquer módulo depois do backup. Só use se
   o passo 1 falhar.

Se inverter a ordem (reverter o código antes do banco), a `main` antiga sobe
num banco já migrado, sem as tabelas antigas no public, e o próprio downgrade
fica sem os arquivos de migração. Por isso o banco vem primeiro.
