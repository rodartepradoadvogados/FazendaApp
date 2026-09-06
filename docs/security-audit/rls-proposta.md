# RLS (Row Level Security): proposta para decisão do dono

**Status: PROPOSTA. Nada foi aplicado a banco nenhum.** Este documento existe
para ser lido e decidido, não para ser executado. A migração que o acompanha
(`alembic/versions/`) só entra quando houver decisão explícita.

Data: 06/09/2026. Todas as afirmações abaixo foram MEDIDAS — no código do
repositório ou num PostgreSQL 16 real, com os comandos reproduzidos no fim.

---

## 1. O problema que o RLS resolve — e o que ele NÃO resolve

Hoje o isolamento entre fazendas existe só na aplicação: cada rota lembra (ou
esquece) de escrever `WHERE fazenda_id = :atual`. A auditoria fechada no PR
#703 encontrou dezenas de lugares onde esse `WHERE` faltava, e o padrão que
causa isso é sempre o mesmo:

```python
if fazenda_id is not None:              # ← se vier None, o filtro some
    query = query.where(Model.fazenda_id == fazenda_id)
```

Fechar um a um funciona, mas é uma corrida sem linha de chegada: cada rota
nova é uma chance nova de esquecer. O RLS inverte o ônus — o banco recusa a
linha alheia mesmo quando a aplicação esquece. É a diferença entre "todo
desenvolvedor precisa acertar sempre" e "o banco não deixa errar".

**O que o RLS não resolve:** ele não conserta dado já órfão, não substitui a
checagem de permissão por perfil (quem pode editar o quê dentro da PRÓPRIA
fazenda), e não protege nada se a aplicação conectar como superusuário — ver
a seção 3, que é a mais importante deste documento.

## 2. A superfície: dois tipos de tabela, não um

Medido em `backend/fazenda/models.py`:

| | |
|---|---|
| Tabelas com coluna `fazenda_id` | **185** |
| Aceitam NULL | **170** |
| Já são `NOT NULL` | **15** |
| Catálogo global legítimo | **14** |
| **Aceitam NULL sem ter direito** | **156** |

O `fazenda_id` nulo significa duas coisas incompatíveis no mesmo esquema:

- **Catálogo global** (14 tabelas) — NULL quer dizer "é de todo produtor".
  Semeado igual para todos; cada fazenda põe as suas linhas por cima. Filtro
  estrito aqui é bug: `fazenda_id = 1` exclui `IS NULL` em SQL, e a Farmácia
  aparece vazia. É o que `rules/visibilidade.py::visivel()` resolve.
- **Órfão** (as outras 156) — NULL quer dizer "perdeu o dono". Não deveria
  existir; quando existe, passa por qualquer inquilino no padrão tolerante
  `if registro.fazenda_id not in (None, fazenda_id)`.

As 14 de catálogo, levantadas do código (`visivel()` explícito e a fábrica
`_crud_nome_ativo(..., global_compartilhado=True)` em `cadastro/_comum.py`):

```
principio_ativo, doenca, indicacao_terapeutica, medicamento_comercial,
categoria_estoque, finalidade_estoque, unidade_estoque,
unidade_embalagem_estoque, unidade_medida_embalagem_estoque, laboratorio,
categoria_medicamento, classificacao_medicamento_cad, servico_cadastro,
parametro_fazenda
```

Por isso são **duas** políticas, não uma. Uma política única com
`OR fazenda_id IS NULL` para todas as tabelas gravaria a tolerância a NULL
DENTRO do banco — exatamente o anti-padrão que este trabalho está fechando na
aplicação.

## 3. O ponto que decide se vale a pena: o usuário do banco

**Superusuário do PostgreSQL ignora RLS por completo — inclusive com
`FORCE ROW LEVEL SECURITY`.** Medido:

| Quem conecta | Política ativa | O que enxerga |
|---|---|---|
| `postgres` (superusuário) | sim, com FORCE | **as 3 linhas, de todas as fazendas** |
| dono da tabela, não superusuário | sim, com FORCE | 0 linhas (contido) |
| role de aplicação comum | sim, com FORCE | só as da sua fazenda |

O Postgres do Railway entrega, por padrão, uma `DATABASE_URL` com o usuário
`postgres`, que é superusuário. Se a aplicação seguir conectando assim, ligar
RLS não protege absolutamente nada — o custo é pago e a proteção não chega.

**Consequência:** ativar RLS exige, antes, criar um role de aplicação sem
superusuário e sem ser dono das tabelas, e trocar a `DATABASE_URL` do serviço
para ele. Isso é mudança de infraestrutura, não de código, e é irreversível
sem downtime se feita errado (a aplicação para de subir se o role não tiver
os GRANTs certos).

Para conferir o usuário atual, uma consulta de leitura, sem segredo nenhum:

```sql
SELECT current_user, usesuper AS eh_superusuario
FROM pg_user WHERE usename = current_user;
```

## 4. Como o banco fica sabendo qual é a fazenda

A política lê uma variável de sessão que a aplicação escreve a cada
requisição:

```sql
USING (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int)
```

O segundo argumento `true` faz `current_setting` devolver NULL em vez de dar
erro quando a variável não existe. Como `coluna = NULL` é NULL (nunca
verdadeiro) em SQL, **sem contexto nenhum a política nega tudo** — o
comportamento seguro por omissão. Medido: uma consulta sem `SET` devolveu 0
linhas na tabela de dado da fazenda.

### O erro que precisa NÃO ser cometido: `SET` em vez de `SET LOCAL`

`SET LOCAL` vale até o fim da transação. `SET` sem `LOCAL` vale até o fim da
CONEXÃO — e a conexão volta para o pool e atende a próxima requisição, de
outra fazenda, com o contexto da anterior ainda montado. Medido:

```
Requisição A (fazenda 1) com SET:        vê "mastite da fazenda 1"
Requisição B na MESMA conexão, sem SET:  contexto_herdado = 1  ← vazou
```

Um vazamento entre inquilinos criado pela própria proteção. Por isso a
implementação precisa de `SET LOCAL` dentro de transação, e de um `RESET` no
retorno da conexão ao pool como segunda linha de defesa.

Onde isso entra no código: hoje `database.py::get_session()` abre a sessão sem
saber de fazenda nenhuma, e quem conhece o `fazenda_id` é
`auth.py::get_fazenda_atual_id()`, que só lê o token (não toca o banco, então
não há dependência circular). São as duas peças a costurar.

## 5. A ordem obrigatória — e por que ela não é preferência

Ligar RLS numa base que ainda tem órfãos não "esconde" esses registros: torna
cada um **inalcançável por qualquer caminho da aplicação, inclusive o de
recuperação**. Depois da política ativa, a própria migração de backfill (a
`029227481e9e`, que preenche `fazenda_id` nulo) deixa de enxergar o que
precisa consertar — a menos que rode como owner ou com `BYPASSRLS`, que é
justamente a exceção que não se quer deixar de pé.

Então a sequência é uma dependência, não uma escolha:

1. **Contar** os órfãos em produção (`orfaos-railway.sql`).
2. **Triar**: quantos desses dá para recuperar sem adivinhar
   (`orfaos-triagem.sql`). A migração `029227481e9e` já fixou a estratégia
   certa — derivar do pai, senão fazenda única, senão não adivinhar — mas a
   lista de pais dela é escrita à mão; a triagem tira a relação filha→pai do
   catálogo do banco, então nenhuma FK fica de fora por esquecimento. Ela
   também responde se a estratégia "fazenda única" ainda vale: deixa de valer
   no dia em que entra a segunda fazenda-cliente.
3. **Recuperar ou marcar** — o backfill determinístico do que tem pai, e
   decisão explícita sobre o que sobrar. **Decisão do dono, com os dois
   números na mão: quantos são, e quantos não têm saída.**
4. **Criar o role de aplicação** e trocar a `DATABASE_URL`.
5. **Ativar** a política, primeiro no Staging (banco próprio), depois em
   produção.

Pular direto para o 5 transforma cada órfão em perda de dado silenciosa.

## 6. Um furo que o RLS sozinho NÃO fecha: chave estrangeira

Este não estava na conta e apareceu ao testar o esquema real. A verificação
de chave estrangeira do PostgreSQL roda POR BAIXO da política — ela enxerga
linhas que o usuário não enxerga. Medido, com `lote` e `animal`:

| O que a fazenda 1 faz | Resultado |
|---|---|
| lê a lista de lotes | vê só o lote 10, o seu — a política funciona |
| grava um animal apontando para o lote **20, da fazenda 2** | **aceito** |
| grava um animal apontando para o lote 777, que não existe | recusado |

Duas consequências, e a segunda é pior que a primeira:

1. Nasce referência cruzada entre fazendas dentro do dado — um animal da
   fazenda 1 pendurado num lote da fazenda 2, que a fazenda 1 nem consegue
   ver para corrigir.
2. A diferença entre os dois últimos resultados é um **oráculo de
   existência**: por tentativa e erro, um inquilino descobre quais ids
   existem no sistema inteiro. É a mesma classe do "403 confirma que o id
   existe" que o projeto já combate respondendo sempre 404 — só que agora
   dita pelo banco, não pela rota.

A correção é a FK composta, o padrão canônico de multi-tenant: a chave passa
a carregar a fazenda dos dois lados.

```sql
ALTER TABLE lote   ADD CONSTRAINT lote_id_fazenda_uk UNIQUE (id, fazenda_id);
ALTER TABLE animal DROP CONSTRAINT animal_lote_id_fkey;
ALTER TABLE animal ADD CONSTRAINT animal_lote_fk
  FOREIGN KEY (lote_id, fazenda_id) REFERENCES lote(id, fazenda_id);
```

Medido depois da troca: a gravação apontando para o lote da outra fazenda
passa a ser recusada, a do próprio lote continua funcionando — e a mensagem
de erro fica **idêntica** nos dois casos ("Key is not present in table"),
o que fecha também o oráculo.

**O tamanho disto foi medido**, contra o esquema real: das **434** chaves
estrangeiras do banco, **161** ligam duas tabelas que ambas têm `fazenda_id`
— são essas que precisam virar compostas — e elas apontam para **61** tabelas
pai distintas, cada uma precisando de uma `UNIQUE (id, fazenda_id)` nova.

Ou seja: 161 constraints trocadas e 61 índices únicos novos. É trabalho de
porte comparável ao do RLS em si, e precisa entrar na conta antes da decisão
— não é detalhe de acabamento. Sem ele, o RLS entrega isolamento de leitura
mas deixa de pé tanto a referência cruzada quanto o oráculo de existência.

## 7. O que foi provado, e como reproduzir

Oito ataques contra um PostgreSQL 16 real, conectado como role de aplicação:

| Ataque | Resultado |
|---|---|
| Ler sem contexto de fazenda | 0 linhas (catálogo global segue visível, por definição) |
| Fazenda 1 lê os dados da fazenda 2 | só vê os seus + o catálogo global |
| Fazenda 1 INSERE registro com `fazenda_id = 2` | `ERROR: new row violates row-level security policy` |
| Fazenda 1 muda por UPDATE a dona do próprio registro | mesmo erro |
| Fazenda 1 grava registro órfão (`fazenda_id` NULL) | mesmo erro |
| Contexto forjado (`app.fazenda_id = '1 OR true'`) | `ERROR: invalid input syntax for type integer` |
| DELETE da fazenda 1 mirando linha da fazenda 2 | `DELETE 0` — não alcança |
| `SET` sem `LOCAL`, depois requisição na mesma conexão | contexto **vazou** para a requisição seguinte |

O roteiro completo está em `docs/security-audit/rls-experimento.sql` e roda
inteiro num `psql` só, contra um Postgres descartável.

O DDL parametrizado da ativação está em
`docs/security-audit/rls-migracao-proposta.sql`. Ele percorre o catálogo do
banco em vez de uma lista escrita à mão, para que tabela nova com
`fazenda_id` entre sozinha em vez de ficar de fora em silêncio. Rodado
contra o esquema real deste repositório (206 tabelas criadas por
`SQLModel.metadata.create_all` num Postgres local): **185 políticas criadas,
14 de catálogo global e 171 de dado da fazenda, nenhuma tabela multi-tenant
de fora.**

Ele é um `.sql` avulso e **não** uma revisão Alembic de propósito:
`database.py::_aplicar_alembic()` roda `upgrade head` no boot da API, então
uma revisão em `alembic/versions/` seria aplicada em produção no próximo
deploy, sozinha, sem ninguém decidir nada. Vira migração no dia da decisão.

## 8. O que falta para decidir

| | |
|---|---|
| Número de órfãos em produção | consulta pronta, aguardando execução |
| Quantos deles dá para recuperar sem adivinhar | consulta de triagem pronta (`orfaos-triagem.sql`) |
| Usuário do banco é superusuário? | consulta pronta (seção 3) |
| Criar role de aplicação e trocar DATABASE_URL | decisão de infraestrutura do dono |
| O que fazer com cada bloco de órfão | decisão do dono, depois da contagem |
| Fazer as 161 FKs compostas junto, ou em etapa própria? | decisão do dono (seção 6) |
| Custo de desempenho da política | medir no Staging, com volume real |
