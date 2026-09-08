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
| Catálogo global legítimo | **18** |
| **Aceitam NULL sem ter direito** | **152** |

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

## 5. A ordem — aprovada pelo dono em 06/09/2026

**O que foi aprovado é a ORDEM, não a execução.** Cada etapa abaixo continua
precisando de decisão própria antes de rodar: nenhuma delas está autorizada
por este documento.

O RLS não é a primeira etapa, e essa é a mudança em relação ao que estava
escrito aqui antes. Duas travas mais baratas vêm na frente, entregam a maior
parte do benefício, e **nenhuma delas mexe em infraestrutura** — enquanto o
RLS exige trocar o usuário do banco, mudar como a aplicação abre sessão, e
não perdoa erro em nenhum dos dois.

### 1. Contar os órfãos (`orfaos-railway.sql`)

Somente leitura. Responde "quantos são".

### 2. Triar (`orfaos-triagem.sql`)

Somente leitura, e é ela que decide o tamanho do trabalho: **quantos dá para
recuperar sem adivinhar**. Mil órfãos todos com um pai que sabe a fazenda são
um `UPDATE` determinístico; cinquenta sem pai nenhum são cinquenta decisões,
uma a uma.

A migração `029227481e9e` já fixou a estratégia certa — derivar do pai, senão
fazenda única, senão não adivinhar —, mas a lista de pais dela é escrita à
mão; a triagem tira a relação filha→pai do catálogo do banco, então nenhuma
FK fica de fora por esquecimento. Ela também responde se a estratégia
"fazenda única" ainda vale: deixa de valer no dia em que entra a segunda
fazenda-cliente.

### 3. Recuperar ou marcar

**Etapas 1 e 2, medidas em produção em 06/09/2026** (banco `railway`, 185
tabelas com `fazenda_id`):

| | Tabelas | Com nulos | Linhas |
|---|---|---|---|
| Catálogo global (NULL legítimo) | 14 | 12 | **486** |
| **Órfãos (NULL sem direito)** | 171 | **16** | **183** |

*(números da consulta como ela foi rodada, com a lista de 14; a correção vem logo abaixo)*

As 486 do catálogo são o esperado e não são problema: ali o NULL quer dizer
"é de todo produtor".

### A contagem revelou um erro na lista de catálogo — e ele era grave

Rodada a triagem, **nenhum dos 183 órfãos era recuperável pelo pai**. Isso não
fazia sentido, e ao investigar apareceu o motivo: **137 dos 183 não são órfãos.
São catálogo global, e a lista das 14 tabelas estava incompleta.**

| Tabela | Linhas | O que é de verdade |
|---|---|---|
| `medicamento_principio_ativo` | **125** | ligação N-N do catálogo. O próprio modelo diz: *"mesmo padrão de `IndicacaoTerapeutica` — clonagem por fazenda ao personalizar um medicamento do catálogo"*. E `indicacao_terapeutica` **está** na lista. |
| `alimento_nutricional` | **12** | *"Biblioteca MESTRE CowData + cópia por fazenda (copy-on-write): `fazenda_id=None` marca uma linha da biblioteca mestre, global, igual para todas as fazendas"* |

**Por que escaparam:** a lista original saiu de duas fontes — os `visivel()`
explícitos e a fábrica `_crud_nome_ativo(..., global_compartilhado=True)`.
Essas duas tabelas usam um **terceiro** mecanismo de catálogo, o
copy-on-write por coluna de origem (`origem_id`, `origem_mestre_id`), que a
varredura não cobria.

**Por que isso era pior que uma contagem errada.** Se o DDL parametrizado
tivesse rodado com a lista de 14, `medicamento_principio_ativo` receberia a
política **estrita** — e as 125 ligações do catálogo global ficariam
invisíveis para **todas** as fazendas. A Farmácia quebraria: medicamento
combinado perderia os princípios ativos. O mesmo valeria para a biblioteca de
alimentos. A ativação teria derrubado duas telas, e o erro só apareceria
depois, em produção.

O erro foi encontrado porque a contagem foi rodada **antes** de qualquer
ativação, e porque o resultado `recuperaveis_pelo_pai = 0` era estranho o
bastante para exigir explicação em vez de aceitação.

**Lista corrigida: 16 tabelas de catálogo global.** Os arquivos
`rls-migracao-proposta.sql` e `orfaos-triagem.sql` foram atualizados.

**Números corrigidos:**

| | Antes (lista de 14) | Corrigido (lista de 16) |
|---|---|---|
| Catálogo global | 486 linhas | **623 linhas** |
| **Órfãos de verdade** | 183 linhas | **46 linhas** |

Os 46 restantes são dado legado, não catálogo: `conta_gerencial` (12),
`tipo_documento` (9), `lancamento_anexo` (8) e mais 17 linhas espalhadas — os
modelos dizem, nas três, *"nulo para todo lançamento já existente antes da
migração de backfill"*.

**E nenhum deles tem pai que saiba a fazenda.** Com `fazendas_reais = 2`, os
46 são decisão do dono, um a um — mas 46 é uma lista que cabe numa conversa.

### A triagem, rodada: os 46 viraram 45, e a decisão são três, não 46

Rodada a consulta detalhada em produção, com a conferência de uso da sandbox,
cada uma das 14 tabelas com órfão foi classificada pelo que ELA É — não pela
data, que não discrimina nada aqui (a sandbox nasceu 33 horas depois da
fazenda real; quase todo dado do sistema é posterior a ela).

**As três fazendas, medidas:** `Jairo Nasser` (id 1, real), `Fazenda Teste`
(id 2, `eh_teste = true`) e `CowData (empresa)` (id 3, o painel). **Uma única
fazenda-cliente real.**

E a sandbox está **praticamente vazia**: zero linhas em 11 das 14 tabelas com
órfão. Ela mal foi usada, então os órfãos não vieram dela — que era o único
risco de atribuí-los à fazenda 1.

#### A — não é órfão, é catálogo global: não tocar (1 linha)

`medicamento_categoria`. O modelo **avisa explicitamente** contra o que
pareceria óbvio fazer:

> *"inclusive quando NULO: um vínculo de medicamento GLOBAL tem que continuar
> global, senão ele passaria a 'pertencer' à primeira fazenda que o backfill
> encontrasse e sumiria do catálogo global de todas as outras."*

A varredura sistemática (tabelas de ligação cujos pais são TODOS catálogo, com
a semântica confirmada no modelo) achou também `medicamento_classificacao`,
com a mesma regra. Ela não tem órfão hoje, **mas precisa entrar na lista do
DDL assim mesmo** — com política estrita, os vínculos globais dela sumiriam.

**Lista de catálogo global: 16 → 18 tabelas.**

#### B — resíduo de migração: apagar (4 linhas)

`meta_recria`, `parametro_manual_fazenda`, `parametro_sugestao_movimentacao`,
`parametro_diaria_padrao`, 1 cada. O modelo do primeiro explica todos:

> *"Era uma linha única (id=1) — passa a ser uma linha por fazenda."*

A órfã é a linha antiga, de quando o parâmetro era global. E a fazenda 1 **já
tem a sua** nas quatro. Atribuir aqui seria **pior que não fazer nada**:
criaria duplicata numa tabela cujo contrato é "uma linha por fazenda,
get-or-create".

#### C — lixo técnico: apagar (2 linhas)

`idempotencia_chave`. Cache da fila offline, *"curto prazo, minutos a poucas
horas até reconectar"*. A fazenda 1 tem 392 linhas vivas; essas 2 são resto.

#### D — dado real da fazenda 1: atribuir (38 linhas)

`conta_gerencial` (12), `tipo_documento` (9), `lancamento_anexo` (8),
`local_armazenamento` (4), `lancamento_item` (3), `calendario_sanitario` (1),
`classificacao_lancamento` (1), `cronograma_sanitario` (1).

A fazenda 1 tem volume grande nas mesmas tabelas (928, 17, 95, 7, 208, 13, 7)
e a sandbox tem zero em todas. `cronograma_sanitario` e `calendario_sanitario`
vão juntas: a órfã do cronograma é a única linha da tabela e depende da órfã
do calendário — são o mesmo evento.

#### Risco a conferir antes da migração

`tipo_documento`, `local_armazenamento` e `classificacao_lancamento` têm
`UNIQUE (nome, fazenda_id)`. Se alguma órfã tiver o mesmo nome de uma linha da
fazenda 1, o `UPDATE` **falha** por violação de unicidade — o que é o
comportamento certo, mas é melhor saber antes e decidir entre atribuir ou
apagar a duplicata.

**Balanço: 45 linhas a mexer — 38 atribuir, 6 apagar, 1 deixar em paz.**

**E o dado que muda a etapa 3: `fazendas_reais = 2`** (3 no total, uma delas a
fazenda lógica da CowData). A migração `029227481e9e` tem três estratégias, e
a segunda é *"se a instalação tem exatamente UMA fazenda real, atribui essa"*.
Com duas fazendas-cliente, **essa estratégia deixou de valer**.

**Só que esse número está errado, e o erro é da consulta — e da migração.**
A consulta contou como "real" tudo que não é o painel CowData, então a
**sandbox entrou na conta**. São 1 real + 1 sandbox + 1 painel.

E a migração `029227481e9e` tem exatamente o mesmo defeito: decide com
`WHERE eh_empresa_cowdata IS NOT TRUE` e **ignora `eh_teste`**. Foi por isso
que ela enxergou "duas fazendas", desistiu de atribuir, e deixou os órfãos
parados.

A flag de sandbox é levada a sério em outro ponto do sistema —
`rules/replicacao_fazenda.py` **recusa com 409** qualquer destino que não a
tenha, justamente para não sobrescrever a fazenda-cliente real por engano. A
migração de backfill simplesmente não a conhece. **Corrigir isso é uma linha**,
e faz a migração enxergar o que de fato existe: uma fazenda-cliente real.

É por isso que a consulta de triagem (`orfaos-triagem.sql`) deixou de ser
"bom saber" e passou a ser o que dimensiona a etapa 3.

**183 órfãos, concentrados em 16 tabelas, é um número pequeno e tratável** —
muda a natureza da etapa 3. Não é um mutirão de limpeza: é uma migração de
backfill com uma lista curta, e o que sobrar cabe numa conversa de minutos.
Falta rodar a triagem (`orfaos-triagem.sql`) para saber quantos desses 183
têm um pai que sabe a fazenda e podem ser reatribuídos sem adivinhar.

O backfill determinístico do que tem pai, e decisão explícita sobre o que
sobrar. **Decisão do dono, com os dois números na mão.**

### 4. `fazenda_id` deixa de aceitar nulo

`ALTER TABLE ... ALTER COLUMN fazenda_id SET NOT NULL` nas **156** tabelas que
aceitam NULL sem ter direito (as 14 de catálogo global ficam de fora, porque
ali o NULL é o que faz o catálogo ser de todos).

É a trava com melhor retorno pelo custo de todo este documento:

- **É trava de banco de verdade**, não convenção de código. Nenhuma rota, nem
  a mais distraída, consegue criar registro sem dono a partir daí.
- **Mata a família inteira de "órfão passa por qualquer fazenda"** na origem.
  O padrão tolerante `if registro.fazenda_id not in (None, fazenda_id)`, que
  a auditoria vem fechando rota a rota, deixa de ter caso a tratar: não
  existe mais registro com `fazenda_id` nulo para ser tolerado.
- **Não exige trocar usuário do banco nem tocar em `get_session`.** É uma
  migração Alembic comum.
- **É pré-requisito do RLS de qualquer forma** — a política de dado da
  fazenda nega toda linha com `fazenda_id` nulo, então essas linhas
  precisariam sumir antes, de um jeito ou de outro.

Só pode vir depois da etapa 3: a migração falha se ainda houver uma linha
nula, e é assim que tem que ser — falhar na migração é infinitamente melhor
que falhar em produção.

### 5. As 161 chaves estrangeiras compostas

`FOREIGN KEY (filho_id, fazenda_id) REFERENCES pai(id, fazenda_id)`, com a
`UNIQUE (id, fazenda_id)` correspondente em cada uma das **61** tabelas pai.

Fecha os dois problemas da seção 9: a referência cruzada entre fazendas, e o
oráculo de existência. Também não depende de RLS nem de infraestrutura.

### 6. RLS, por último

Só aqui entram as três exigências que nenhuma etapa anterior tem: role de
aplicação sem superusuário, `DATABASE_URL` trocada, e a aplicação emitindo
`SET LOCAL app.fazenda_id` por requisição. Primeiro no Staging (banco
próprio), depois em produção.

---

**Por que a ordem é dependência e não preferência.** Ligar RLS numa base que
ainda tem órfãos não "esconde" esses registros: torna cada um **inalcançável
por qualquer caminho da aplicação, inclusive o de recuperação**. Depois da
política ativa, a própria migração de backfill (`029227481e9e`) deixa de
enxergar o que precisa consertar — a menos que rode como owner ou com
`BYPASSRLS`, que é justamente a exceção que não se quer deixar de pé.

Pular direto para o 6 transforma cada órfão em perda de dado silenciosa.

## 6. O boot da API para de subir (achado ao revisar a proposta)

`main.py::lifespan` chama `create_db_and_tables()` **no boot**, e ela faz mais
do que aplicar migração:

| No boot | O que exige |
|---|---|
| `_aplicar_alembic()` → `upgrade head` | DDL |
| `SQLModel.metadata.create_all(engine)` | DDL |
| `_migrar_colunas()` → `ALTER TABLE ADD COLUMN` | DDL |
| `_migrar_tipos_bigint()` → `ALTER TABLE ALTER COLUMN TYPE` | DDL |
| `_inativar_animais_semen()` | UPDATE de dados |
| ~50 seeds (`seed_admin`, `seed_parametros`, …) | INSERT/UPDATE, **sem contexto de fazenda** |

O passo 0 desta proposta cria `cowdata_app` deliberadamente **sem ser dono das
tabelas**, e é isso mesmo que se quer. Mas `ALTER TABLE` e `CREATE` exigem
ownership.

**Consequência:** no dia em que a `DATABASE_URL` apontar para `cowdata_app`,
não é uma requisição que falha — **é a subida da API**. O sistema fica fora do
ar até alguém descobrir que o role não pode alterar tabela. E os seeds, que
rodam sem `app.fazenda_id`, seriam negados pela própria política.

### Por que dar ownership ao role da aplicação NÃO é saída

Medido: **o dono de uma tabela pode desligar a política dela**.

```
SET ROLE app_dono;
ALTER TABLE t NO FORCE ROW LEVEL SECURITY;   -- aceito
SELECT count(*) FROM t;                       -- 2 linhas: vê tudo
ALTER TABLE t DISABLE ROW LEVEL SECURITY;    -- aceito
```

E depois do `DISABLE`, a tabela fica aberta **para todos os roles**, não só
para o dono. Ownership não é "um pouco de permissão a mais": é a permissão de
revogar a proteção. Isso descarta o `GRANT` seletivo de ownership por tabela.

### As duas saídas reais

**(a) Duas URLs.** `DATABASE_URL_MIGRACAO` (role dono) usada só por
`create_db_and_tables()`; `DATABASE_URL` (role de aplicação) para o
`get_session()` das requisições. Mantém o boot idempotente que já funciona
hoje, e é a mudança menor.

**(b) Tirar a migração do boot.** Vira passo próprio do deploy, e a credencial
de dono nunca entra no ambiente de runtime da API.

**(b) é o desenho correto**; **(a) é o transitório aceitável**, e a diferença
entre as duas é uma só: em (a) a credencial de dono fica no ambiente do
serviço da API, então quem executar código lá dentro pode desligar a política.

Sobre esse risco, o registro honesto: **o RLS aqui protege contra BUG, não
contra invasor com execução de código na API**. Quem executa código no
processo já tem a sessão do banco aberta e o token de qualquer usuário que
passar; o RLS nunca foi desenhado para esse adversário. A credencial de dono
no ambiente reduz uma defesa que já não existia — não é motivo para descartar
(a), mas precisa estar escrito, não escondido.

**Recomendação:** ir de (a) na primeira ativação, com a `DATABASE_URL_MIGRACAO`
em variável separada e escopo mínimo, e migrar para (b) quando o Railway
tiver um passo de deploy próprio configurado. Decisão do dono.

## 7. As rotinas de fundo ficariam cegas — e em silêncio

Sob RLS, quem não seta `app.fazenda_id` não enxerga nada: é o comportamento
seguro por omissão da seção 4, e aqui ele vira o problema. Levantei **todos**
os caminhos que abrem sessão fora do ciclo de requisição:

| Onde | O que faz | Frequência |
|---|---|---|
| `main.py::_loop_backup_automatico` | backup automático | **a cada 30 min** |
| `main.py::_loop_despacho_push` | push pendente + agenda do dia | **a cada 30 min** |
| `main.py::_loop_manual_fazenda_semanal` | manual semanal | **a cada 30 min** |
| `main.py::lifespan` | ~50 seeds | todo boot |
| `portal.py::_executar_exportacao` | ZIP + e-mail, em BackgroundTask | por pedido |
| `push.py::enviar_push` | sessão própria quando não recebe uma | por alerta |
| `rules/parametros.py` | leitura de parâmetro | por chamada |
| `database.py` (3×) | rotinas do boot | todo boot |

**Os três loops de `main.py` são o pior caso, e não pelo motivo óbvio.** Eles
são multi-fazenda por natureza (fazem backup de todas, despacham push para
todos os usuários), rodam sozinhos a cada 30 minutos — e cada um está dentro
de:

```python
except Exception:
    pass  # nunca deixa essa tarefa de fundo derrubar o resto da aplicação
```

Esse `pass` existe por um bom motivo e não deve sair. Mas ele significa que,
sob RLS, uma negação de política **não apareceria nem no log**. O backup
automático passaria a gravar backup vazio, a cada 30 minutos, em silêncio — e
backup vazio é pior que backup nenhum, porque dá falsa segurança até o dia em
que for preciso restaurar.

### O que cada caminho precisa

Três naturezas diferentes, e só a primeira é resolvida com "setar o contexto":

1. **Por fazenda, conhecida** — `_executar_exportacao` já recebe `fazenda_id`
   como parâmetro (foi assim que o achado 49 foi fechado). Basta emitir
   `SET LOCAL app.fazenda_id` na sessão que ela abre.
2. **Por fazenda, em laço** — os loops de push e do manual semanal operam
   sobre várias fazendas. Podem passar a iterar as fazendas e abrir uma
   transação por fazenda, com o contexto setado em cada uma. É mais código,
   mas é o desenho honesto: a rotina passa a dizer de quem é cada operação.
3. **Legitimamente sem recorte** — backup automático e os seeds do boot
   precisam ver o banco inteiro por definição.

Para (3) a pergunta não é "como setar contexto", é **como conceder leitura sem
recorte sem abrir um `BYPASSRLS` de propósito geral**. Um role com `BYPASSRLS`
que a aplicação possa assumir anula o RLS pelo caminho mais curto. A seção 8
mede as saídas e fecha esse item.

## 8. A leitura sem recorte, medida e resolvida

Item deixado em aberto pela seção 7. Antes das saídas, um achado que muda a
gravidade do problema.

### O backup não falharia — ele mentiria

`rules/backup.py::gerar_backup_zip` faz um `SELECT` por tabela do schema.
**RLS não dá erro: devolve vazio** (medido — `app sem contexto` retornou 0
linhas, sem exceção). E `executar_backup_se_necessario` só grava
`sucesso=False` quando há **exceção**:

```python
try:
    zip_bytes = gerar_backup_zip(session)
    enviar_email(...)
    session.add(BackupAutomatico(sucesso=True))
except Exception as exc:
    session.add(BackupAutomatico(sucesso=False, erro=...))
```

Sem exceção, o caminho feliz roda inteiro: ZIP com um CSV por tabela contendo
só o cabeçalho, e-mail enviado ao dono, `sucesso=True` gravado — e, por causa
do `INTERVALO_DIAS = 7`, a próxima tentativa só em uma semana. O
`except Exception: pass` do loop de `main.py` nem chega a ser o problema aqui:
não existe exceção nenhuma para ele engolir.

### As quatro saídas, medidas

Cenário: tabela `sanidade` com 3 linhas (fazenda 1, fazenda 2, catálogo
global), RLS ligado, política estrita para `cowdata_app`. O roteiro completo
está em `docs/security-audit/rls-experimento-leitura-sem-recorte.sql` e roda
inteiro num `psql` só, contra um Postgres descartável.

| Quem lê | Vê as 3 linhas? | Tabela nova sem política | Escreve sem recorte? |
|---|---|---|---|
| `cowdata_app` (com contexto da fazenda 1) | não — 1 linha | contida | não (`INSERT` na fazenda 2 → erro de política) |
| dono das tabelas, **com** `FORCE` | **não — 0 linhas** | 0 linhas | — |
| dono das tabelas, **sem** `FORCE` | **sim — 3** | **sim** | sim |
| role com política `FOR SELECT ... USING (true)` | sim — 3 | **não — 0 linhas** | não (`UPDATE 0`, `DELETE 0`, `INSERT` → erro) |
| role com `BYPASSRLS` | sim — 3 | sim | **sim, sem nenhum limite** |

Duas linhas dessa tabela decidem:

**A política dedicada de leitura contém a escrita, mas cria um backup
incompleto em silêncio.** Foi medido: criei uma tabela nova com RLS ligado e
esqueci a política do role de backup — ele passou a ler **0 linhas ali**, sem
erro. É o mesmo modo de falha que se está tentando evitar, agora dependendo de
alguém lembrar de criar uma política por tabela nova, para sempre.

**`BYPASSRLS` cobre tabela nova, mas dá escrita irrestrita** — e um role que a
aplicação pode assumir devolve o RLS de presente a quem executar código na API.

### O `FORCE` contra o próprio dono é teatro

Sobra a terceira linha: **dono das tabelas, sem `FORCE`**. Abrir mão do
`FORCE` parece perder proteção, e não perde, porque:

1. O `FORCE` só muda o comportamento **do dono das tabelas**. A aplicação, por
   desenho do passo 0, não é dona — para ela nada muda.
2. O dono pode remover o `FORCE` com um comando. Medido:
   `ALTER TABLE ... NO FORCE ROW LEVEL SECURITY` → aceito, e as 3 linhas
   voltam a aparecer. Um `FORCE` que quem ele restringe pode desligar sozinho
   não restringe ninguém.

O `FORCE` valeria se o dono fosse a aplicação — e o passo 0 existe justamente
para que não seja.

### O desenho recomendado

**RLS ligado, sem `FORCE`; backup e seeds pela conexão de dono** — a mesma
`DATABASE_URL_MIGRACAO` da seção 6, sem nenhum role `BYPASSRLS` no sistema e
sem política por tabela para manter. Medido nesse desenho: o dono lê as 4
linhas e insere catálogo global sem obstáculo; a aplicação na fazenda 1 segue
vendo 1 linha e leva erro de política ao tentar gravar na fazenda 2.

O que ele **não** resolve, dito na cara: no desenho (a) da seção 6 a
credencial de dono fica no ambiente da API, e quem executar código lá dentro
lê o banco inteiro por essa conexão. É o mesmo trade-off já registrado na
seção 6 — este item não acrescenta risco novo, e ele desaparece no desenho
(b), com backup e migração como passos de deploy próprios.

### A guarda que o backup precisa — FEITA em 08/09/2026

Independente de RLS: um backup que sai vazio tem que falhar alto. Está no
código, e foi o primeiro passo da ativação aprovada pelo dono.

`gerar_backup_zip` passou a devolver, junto com o ZIP, **quantas linhas saíram
das tabelas com `fazenda_id`** — e não o total de linhas do banco. A diferença
decide se a guarda funciona: as políticas só entram nas tabelas com essa
coluna, então `backup_automatico` (que não a tem) continua visível sob RLS, e
uma contagem do total do banco nunca chegaria a zero por causa do registro da
rodada anterior. A guarda nunca dispararia justamente no cenário para o qual
existe. Há teste fixando isso.

Com o total zerado, `executar_backup_se_necessario` grava `sucesso=False`, **não
envia o ZIP** e manda ao dono um e-mail cujo assunto começa com "FALHOU". Como
só um sucesso conta para o intervalo de sete dias, a próxima tentativa continua
sendo em 30 minutos — um problema que dure minutos não custa uma semana sem
backup.

E a conexão: `main.py::_loop_backup_automatico` passou a usar
`database.py::engine_manutencao`, que sem `DATABASE_URL_MANUTENCAO` configurada
**é o mesmo objeto** de sempre. Nada muda hoje; no dia da ativação, é por ela
que o backup enxerga o banco inteiro, com o role dono, sem que exista nenhum
role `BYPASSRLS` para a API assumir.

`tests/test_backup_sob_rls.py` prova isso num PostgreSQL 16 real, com as duas
metades no mesmo cenário: pela conexão da aplicação o backup sai vazio e é
recusado; pela conexão de manutenção ele traz o dado. Roda no CI, no job
`backend-tests-postgres` — RLS não existe em SQLite, e a suíte principal é toda
SQLite.


## 9. Um furo que o RLS sozinho NÃO fecha: chave estrangeira

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

## 10. O que foi provado, e como reproduzir

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
inteiro num `psql` só, contra um Postgres descartável. O segundo experimento —
quem consegue ler o banco inteiro, da seção 8 — está em
`docs/security-audit/rls-experimento-leitura-sem-recorte.sql`, no mesmo
formato.

O DDL parametrizado da ativação está em
`docs/security-audit/rls-migracao-proposta.sql`. Ele percorre o catálogo do
banco em vez de uma lista escrita à mão, para que tabela nova com
`fazenda_id` entre sozinha em vez de ficar de fora em silêncio. Rodado
contra o esquema real deste repositório (206 tabelas criadas por
`SQLModel.metadata.create_all` num Postgres local): **185 políticas criadas,
18 de catálogo global e 167 de dado da fazenda, nenhuma tabela multi-tenant
de fora, e nenhuma delas com `FORCE`** (conferido em `pg_class`:
`relrowsecurity` em 185, `relforcerowsecurity` em 0 — ver seção 8).

Ele é um `.sql` avulso e **não** uma revisão Alembic de propósito:
`database.py::_aplicar_alembic()` roda `upgrade head` no boot da API, então
uma revisão em `alembic/versions/` seria aplicada em produção no próximo
deploy, sozinha, sem ninguém decidir nada. Vira migração no dia da decisão.

## 11. O que falta para decidir

### Fechado desde a primeira versão

| | |
|---|---|
| Número de órfãos em produção | **MEDIDO em 06/09/2026: 183 linhas, em 16 tabelas** |
| Quantos dá para recuperar sem adivinhar | **TRIADO: 45 restantes, em 13 tabelas** (seção 5) |
| O que fazer com cada bloco de órfão | **DECIDIDO com o dono: 38 atribuir, 6 apagar, 1 deixar** |
| Risco da seção 7: leitura sem recorte para backup e seeds | **RESOLVIDO na seção 8: RLS sem `FORCE`, pela conexão de dono** |

### Ainda na mesa

| | |
|---|---|
| Migração de backfill dos 45 órfãos (PR #717) | pronta e testada — **mergear aplica em produção no próximo deploy** |
| Risco da seção 6: (a) duas URLs ou (b) migração fora do boot | decisão do dono |
| Usuário do banco é superusuário? | consulta pronta (seção 3) |
| Criar role de aplicação e trocar DATABASE_URL | decisão de infraestrutura do dono |
| Etapa 4 (`NOT NULL`): autorizar a migração | depois do backfill |
| Etapa 5 (161 FKs compostas): autorizar | independente do RLS |
| Guarda do backup vazio (seção 8, fim) | dívida de hoje, independe da decisão de RLS |
| Custo de desempenho da política | medir no Staging, com volume real |
