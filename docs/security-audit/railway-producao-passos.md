# Railway: preparar a Produção para o RLS — 28 passos

Adaptação de `railway-staging-passos.md` para o ambiente `production`. Mesmo
roteiro, mesma ordem, mesmos motivos — só o ambiente muda. Execução pelo
**dono**, cliques no Railway e SQL colado no console do banco. Nenhum passo é
feito por código.

**Autorização:** dada explicitamente pelo dono em 11/09/2026, depois do
Staging validado (RLS ativo, teste de fumaça e ataques de segurança
passando) e da correção do bug de `session.commit()` (PR #760). Não há mais
"aviso prévio à sessão principal" a dar — ver `roteiro-seguranca.md`, seção
5.

**Custo: R$ 0,00.** Este roteiro **não cria** projeto, ambiente, serviço nem
banco de dados. Usa o que já existe no ambiente `production` do projeto
`ravishing-smile` e acrescenta um usuário de banco e uma variável de
ambiente. Nenhum dos dois é cobrado pelo Railway.

## O que este roteiro faz, em uma frase

Cria um usuário de banco **sem poderes de dono** (`cowdata_app`) e faz a
aplicação de produção passar a conectar com ele, mantendo o usuário atual
(dono das tabelas) reservado para o backup automático.

## Por que isso é pré-requisito do RLS

- **superusuário ignora RLS por completo**, mesmo com `FORCE`. A
  `DATABASE_URL` padrão do Postgres do Railway usa o usuário `postgres`, que
  é superusuário — ligar políticas sem trocar isso não entrega proteção
  nenhuma;
- **o dono das tabelas também escapa**, e pode desligar a própria política
  com um comando — por isso a aplicação não pode ser dona;
- **o backup precisa do contrário**: ler o banco inteiro, sem recorte — daí
  existir a conexão de manutenção em vez de um role `BYPASSRLS`.

Isto é exatamente o que já foi feito e validado no Staging. Nada aqui é
novo — é a mesma operação, repetida no ambiente que falta.

## Ordem, e por que ela é esta

A troca da `DATABASE_URL` acontece **antes** de qualquer política de RLS
existir em produção. Se faltar um `GRANT`, o erro aparece sozinho e é óbvio;
se as duas mudanças entrassem juntas, um app quebrado não diria qual das
duas causou.

## Coordenadas do ambiente

| | |
|---|---|
| Projeto | `ravishing-smile` |
| Ambiente | **`production`** (não `Staging` — confirme na tela) |
| Serviços | `FazendaApp`, `Postgres` (confira o nome exato do serviço de banco no passo 4 — em alguns projetos Railway aparece sufixado, ex. `Postgres-05rk`) |
| Variável que ainda não existe em produção | `DATABASE_URL_MANUTENCAO` |

---

## Parte 1 — Abrir o ambiente certo

> ⚠️ **O passo 2 é o que mais importa nesta parte.** Este roteiro É para
> produção — mas confirme mesmo assim antes de seguir, porque uma troca de
> credencial no ambiente errado é o tipo de engano que só aparece depois.

1. Entre em **railway.com** e abra o projeto **ravishing-smile**.
2. No seletor de ambiente, no topo da tela, clique e escolha **production**.
3. **Confirme na tela que está escrito `production`** antes de seguir.

## Parte 2 — Copiar a URL do banco (nada muda ainda)

4. Clique no serviço do banco (**Postgres**, ou o nome equivalente em
   produção — confira antes de clicar).
5. Abra a aba **Variables**.
6. Localize `DATABASE_URL`. Clique no ícone de **olho** para revelar e
   depois no de **copiar**.
7. Cole num bloco de notas e **guarde**. Formato:
   `postgresql://postgres:SENHA@hostname.proxy.rlwy.net:PORTA/railway`
   Esse valor é o seu caminho de volta — não o perca até o fim do roteiro.
   **Esta é a `DATABASE_URL` de produção atual — trate com o mesmo cuidado
   de uma senha de produção, porque é uma.**
8. Anote à parte o **nome do banco**: é o que vem depois da última barra,
   normalmente `railway`. Será usado no passo 18.

## Parte 3 — Dar ao backup a conexão de manutenção

9. Clique no serviço **FazendaApp**.
10. Abra a aba **Variables** e clique em **+ New Variable**.
11. Nome: `DATABASE_URL_MANUTENCAO`
12. Valor: **exatamente o que foi copiado no passo 7** (a URL atual, do
    usuário dono das tabelas).
13. Confirme (**Add** / **Deploy**).

Esta variável vem antes da troca de propósito: é por ela que o backup
automático, as migrações e os seeds do boot continuam enxergando o banco
inteiro (`backend/fazenda/database.py`, `_montar_engine_manutencao()`).
Enquanto ela não existir, a aplicação usa a conexão de sempre — nenhum
efeito colateral neste passo.

## Parte 4 — Abrir o console SQL

14. Volte ao serviço do banco.
15. Abra a aba **Data** (em algumas contas o nome é **Query**).
16. Você verá uma caixa para digitar SQL.

## Parte 5 — Criar o usuário da aplicação

17. Gere uma senha forte, com 30 caracteres ou mais, **sem os caracteres
    `@`, `:`, `/` e `#`** — eles têm significado próprio numa URL de conexão
    e quebram a string. Guarde-a junto com o valor do passo 7. **Use uma
    senha diferente da que o Staging usa** — são ambientes distintos, uma
    credencial não deve valer para os dois.
18. Cole o bloco abaixo, trocando `COLOQUE_A_SENHA_AQUI` pela senha e, se o
    nome do banco anotado no passo 8 não for `railway`, trocando também esse
    nome:

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

As duas últimas instruções não são acabamento: sem elas, toda tabela criada
por uma migração futura nasceria invisível para a aplicação, e o sistema
quebraria num deploy seguinte, longe da causa.

Repare no que o `cowdata_app` **não** recebeu: não é dono de nenhuma tabela
e não é superusuário. É exatamente isso que fará a política de RLS valer
para ele mais tarde.

## Parte 6 — Conferir que o usuário nasceu contido

20. Na mesma caixa, rode:

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles WHERE rolname = 'cowdata_app';
```

21. As duas últimas colunas **têm que vir `false`**. Se qualquer uma vier
    `true`, **pare o roteiro** e avise — com qualquer uma delas verdadeira,
    o RLS não valeria para a aplicação, e o resto do trabalho seria inútil.

## Parte 7 — Trocar a aplicação para o usuário novo

> ⚠️ **Este é o passo que muda o comportamento do ambiente de produção de
> verdade.** É reversível pelo passo 28, e nenhum dado é apagado — mas,
> entre a troca e a conferência, a produção está rodando com a credencial
> nova. Faça a Parte 8 (verificação) imediatamente depois de salvar, sem
> pausa.

22. Volte ao serviço **FazendaApp** → aba **Variables**.
23. Clique em `DATABASE_URL` para editar.
24. Troque **apenas o usuário e a senha**, mantendo host, porta e nome do
    banco exatamente iguais:

```
postgresql://cowdata_app:SUA_SENHA@mesmo-host:mesma-porta/railway
```

25. Salve. O Railway dispara o deploy sozinho.

## Parte 8 — Verificar

26. Em **FazendaApp** → aba **Deployments**, abra o deploy mais recente e
    clique em **View Logs**. A aplicação precisa subir sem `permission
    denied`.
27. Abra o app de produção (o de verdade, com dado real de cliente) e faça
    um teste leve e não destrutivo: entre, abra a lista de animais de uma
    fazenda e confirme que os dados aparecem normalmente. Se puder, grave
    algo reversível (ex. um lançamento que depois se apague) para confirmar
    escrita — combine com o dono antes de gravar qualquer coisa em dado de
    cliente real.

### Se aparecer `permission denied for table ...`

Pare e informe **o nome da tabela** que apareceu no erro. É um `GRANT`
faltando e o conserto é de uma linha, mas convém saber qual antes de rodar
mais SQL.

## Parte 9 — Como voltar atrás

28. A qualquer momento: edite a `DATABASE_URL` do **FazendaApp** de volta
    para o valor guardado no passo 7 e salve. O deploy anterior volta em
    cerca de um minuto. **Nada neste roteiro apaga dado** — o `CREATE ROLE`
    e os `GRANT` acrescentam permissões; a troca da `DATABASE_URL` só muda
    com qual usuário a aplicação conecta. O usuário antigo continua
    existindo e continua dono das tabelas.

---

## Depois destes 28 passos: o que falta, e quem faz

Com produção rodando sob `cowdata_app` (passo 27 confirmado sem
`permission denied`), avise nesta conversa. O passo seguinte — aplicar o
DDL de `rls-migracao-proposta.sql` em produção e validar — é feito por
código/SQL a partir daqui, no mesmo padrão já usado no Staging: aplicar,
checar saúde do serviço imediatamente, e reverter (`DROP POLICY` /
`ALTER TABLE ... NO FORCE ROW LEVEL SECURITY`) se algo parecer errado.

Este roteiro (Railway) **não muda nada de código** — é só operação na
infraestrutura, exatamente como no Staging.
