# Railway: preparar o Staging para o RLS — 28 passos

Roteiro de operação para o **dono**, executável por quem não acompanhou a
conversa. Nada aqui é feito por código: são cliques no Railway e SQL colado no
console do banco.

**Custo: R$ 0,00.** Este roteiro **não cria** projeto, ambiente, serviço nem
banco de dados. Ele usa o que já existe — o ambiente `Staging` do projeto
`ravishing-smile`, que já tem banco próprio — e acrescenta um usuário de banco
e uma variável de ambiente. Nenhum dos dois é cobrado pelo Railway.

## O que este roteiro faz, em uma frase

Cria um usuário de banco **sem poderes de dono** (`cowdata_app`) e faz a
aplicação passar a conectar com ele, mantendo o usuário atual, que é dono das
tabelas, reservado para o backup automático.

## Por que isso é pré-requisito do RLS

Medido e registrado em `rls-proposta.md` (seções 3 e 8):

- **superusuário ignora RLS por completo**, mesmo com `FORCE`. O Postgres do
  Railway entrega, por padrão, uma `DATABASE_URL` com o usuário `postgres`, que
  é superusuário. Ligar políticas sem trocar isso paga o custo e não entrega
  proteção nenhuma;
- **o dono das tabelas também escapa** — e pode desligar a própria política com
  um comando. Por isso a aplicação não pode ser dona;
- **o backup precisa do contrário**: ler o banco inteiro, sem recorte. É para
  isso que a conexão de manutenção existe, em vez de um role `BYPASSRLS` que
  qualquer código da API poderia assumir.

## Ordem, e por que ela é esta

A troca da `DATABASE_URL` acontece **antes** de qualquer política de RLS
existir. Se faltar um `GRANT`, o erro aparece sozinho e é óbvio; se as duas
mudanças entrassem juntas, um app quebrado não diria qual das duas causou.

## Coordenadas do ambiente (conferidas em 08/09/2026)

| | |
|---|---|
| Projeto | `ravishing-smile` |
| Ambientes | `Staging` e `production` |
| Serviços | `FazendaApp`, `Postgres`, `Postgres-05rk` |
| Variável que ainda não existe em nenhum ambiente | `DATABASE_URL_MANUTENCAO` |

---

## Parte 1 — Abrir o ambiente certo

> ⚠️ **O passo 2 é o que mais importa nesta parte.** Executar o roteiro
> apontando para `production` por engano troca a credencial do sistema em uso.

1. Entre em **railway.com** e abra o projeto **ravishing-smile**.
2. No seletor de ambiente, no topo da tela (costuma vir escrito `production`),
   clique e escolha **Staging**.
3. **Confirme na tela que está escrito `Staging`** antes de seguir.

## Parte 2 — Copiar a URL do banco (nada muda ainda)

4. Clique no serviço **Postgres**.
5. Abra a aba **Variables**.
6. Localize `DATABASE_URL`. Clique no ícone de **olho** para revelar e depois no
   de **copiar**.
7. Cole num bloco de notas e **guarde**. O formato é:
   `postgresql://postgres:SENHA@hostname.proxy.rlwy.net:PORTA/railway`
   Esse valor é o seu caminho de volta — não o perca até o fim do roteiro.
8. Anote à parte o **nome do banco**: é o que vem depois da última barra,
   normalmente `railway`. Será usado no passo 18.

## Parte 3 — Dar ao backup a conexão de manutenção

9. Clique no serviço **FazendaApp**.
10. Abra a aba **Variables** e clique em **+ New Variable**.
11. Nome: `DATABASE_URL_MANUTENCAO`
12. Valor: **exatamente o que foi copiado no passo 7** (a URL atual, do usuário
    dono das tabelas).
13. Confirme (**Add** / **Deploy**).

Esta variável vem antes da troca de propósito: é por ela que o backup automático
enxerga o banco inteiro. Sem ela, haveria uma janela em que o backup rodaria com
o usuário restrito. O código já a lê — `backend/fazenda/database.py`,
`_montar_engine_manutencao()` —, e enquanto ela não existir a aplicação usa a
conexão de sempre.

## Parte 4 — Abrir o console SQL

14. Volte ao serviço **Postgres**.
15. Abra a aba **Data** (em algumas contas o nome é **Query**).
16. Você verá uma caixa para digitar SQL.

## Parte 5 — Criar o usuário da aplicação

17. Gere uma senha forte, com 30 caracteres ou mais, **sem os caracteres
    `@`, `:`, `/` e `#`** — eles têm significado próprio numa URL de conexão e
    quebram a string. Guarde-a junto com o valor do passo 7.
18. Cole o bloco abaixo, trocando `COLOQUE_A_SENHA_AQUI` pela senha e, se o nome
    do banco anotado no passo 8 não for `railway`, trocando também esse nome:

```sql
CREATE ROLE cowdata_app LOGIN PASSWORD 'COLOQUE_A_SENHA_AQUI';

GRANT CONNECT ON DATABASE railway TO cowdata_app;
GRANT USAGE ON SCHEMA public TO cowdata_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cowdata_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cowdata_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cowdata_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO cowdata_app;
```

19. Execute (**Run**).

As duas últimas instruções não são acabamento: sem elas, **toda tabela criada
por uma migração futura nasceria invisível para a aplicação**, e o sistema
quebraria num deploy seguinte, longe da causa.

Repare no que o `cowdata_app` **não** recebeu: ele não é dono de nenhuma tabela
e não é superusuário. É exatamente isso que fará a política de RLS valer para
ele mais tarde.

## Parte 6 — Conferir que o usuário nasceu contido

20. Na mesma caixa, rode:

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles WHERE rolname = 'cowdata_app';
```

21. As duas últimas colunas **têm que vir `false`**. Se qualquer uma vier
    `true`, **pare o roteiro** e avise — com qualquer uma delas verdadeira, o
    RLS não valeria para a aplicação, e o resto do trabalho seria inútil.

## Parte 7 — Trocar a aplicação para o usuário novo

> ⚠️ **Este é o passo que muda o comportamento do ambiente.** É reversível pelo
> passo 28, e nada de dado é apagado — mas, entre a troca e a conferência, o
> Staging está rodando com a credencial nova.

22. Volte ao serviço **FazendaApp** → aba **Variables**.
23. Clique em `DATABASE_URL` para editar.
24. Troque **apenas o usuário e a senha**, mantendo host, porta e nome do banco
    exatamente iguais:

```
postgresql://cowdata_app:SUA_SENHA@mesmo-host:mesma-porta/railway
```

25. Salve. O Railway dispara o deploy sozinho.

## Parte 8 — Verificar

26. Em **FazendaApp** → aba **Deployments**, abra o deploy mais recente e clique
    em **View Logs**. A aplicação precisa subir sem `permission denied`.
27. Abra o app do Staging e faça um teste de verdade: entre, abra a lista de
    animais e **grave alguma coisa** (uma sanidade, um lançamento financeiro).
    Precisa salvar normalmente.

### Se aparecer `permission denied for table ...`

Pare e informe **o nome da tabela** que apareceu no erro. É um `GRANT` faltando
e o conserto é de uma linha, mas convém saber qual antes de rodar mais SQL.

## Parte 9 — Como voltar atrás

28. A qualquer momento: edite a `DATABASE_URL` do **FazendaApp** de volta para o
    valor guardado no passo 7 e salve. O deploy anterior volta em cerca de um
    minuto.

**Nada neste roteiro apaga dado.** O `CREATE ROLE` e os `GRANT` acrescentam
permissões; a troca da `DATABASE_URL` muda com qual usuário a aplicação
conecta. O usuário antigo continua existindo e continua dono das tabelas.

---

## Produção

**Não repita este roteiro em produção ainda.** A ordem é: Staging funcionando
com o `cowdata_app` → políticas de RLS testadas no Staging → só então produção,
com os mesmos 28 passos e o seletor do passo 2 em `production`.

## O que fica pendente do lado do código, depois destes 28 passos

- os ~50 seeds do boot (`main.py::lifespan`) precisam da conexão de dono sob
  RLS — hoje usam a conexão comum, e isso só passa a fazer diferença depois do
  passo 25 (ver `rls-proposta.md`, seção 6);
- as políticas em si, que só entram depois de `fazenda_id NOT NULL` e das 130
  FKs compostas (ver `fks-compostas.md`).
