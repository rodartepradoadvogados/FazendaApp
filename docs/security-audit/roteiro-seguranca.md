# Roteiro de segurança — tudo que temos pela frente

Registrado em 09/09/2026, no início da etapa de RLS, a pedido do dono: "de
antemão, registrado logo de início tudo o que temos pela frente". Este
documento é o mapa — atualizado a cada PR — de onde estamos e o que falta,
cruzando os documentos já existentes (`rls-proposta.md`, `fks-compostas.md`,
`railway-staging-passos.md`) em vez de repeti-los.

## Feito e em produção

| Etapa | PR | O que fechou |
|---|---|---|
| Backup sob conexão de dono | #731 | `gerar_backup_zip` conta linhas de fazenda; backup vazio falha alto |
| `fazenda_id` NOT NULL | #738 | 151 tabelas travadas — banco recusa registro sem dono |
| Sincronização da Fazenda Teste | #739 | HTTP 500 na diária corrigido |
| Migrações e seeds pela conexão de dono | #740 | `create_db_and_tables()` inteira roda por `engine_manutencao` |
| 120 FKs entre tabelas de fazenda, compostas | #742 | referência cruzada e oráculo de existência fechados nas relações que já tinham FK |
| `SET LOCAL app.fazenda_id` por requisição | #744 | `get_session()` marca `session.info["fazenda_id"]`; listener `after_begin` reaplica a cada transação — inócuo até a política de RLS entrar |
| Rotinas de fundo sem contexto de fazenda | #745 | `push.py`/`manual_fazenda.py` passam a usar `engine_manutencao`; `parametros.py`/`portal.py` marcam `session.info["fazenda_id"]` na abertura |
| `alembic/env.py` usava a conexão errada nas migrações | #752 | causa raiz do bloqueio do Staging — `env.py` sobrescrevia `DATABASE_URL_MANUTENCAO` com `DATABASE_URL`; deploy do Staging confirmado saudável depois |

## Feito no Staging (ação do dono, fora de código)

- Roteiro `railway-staging-passos.md` (28 passos) executado: `cowdata_app`
  criado sem superusuário e sem ownership, `DATABASE_URL` do Staging trocada
  para ele, `DATABASE_URL_MANUTENCAO` apontando para o role dono. Conferido:
  `rolsuper=false`, `rolbypassrls=false`.

## Em aberto — a etapa de RLS em si (`rls-proposta.md`, seção 5, item 6)

A ordem de pré-requisitos da proposta está cumprida (NOT NULL, FKs compostas,
role de aplicação no Staging). O que falta é o que a seção 4 e a seção 7 da
proposta descrevem:

### 1. O mecanismo — `SET LOCAL app.fazenda_id` por requisição — FEITO (este PR)

`database.py::get_session()` agora lê o token (via
`auth.py::get_fazenda_atual_id()`, chamada direta, sem `Depends` — ciclo de
import resolvido com um parâmetro `Header` cru) e marca
`session.info["fazenda_id"]`. Um listener novo, `_aplicar_contexto_de_fazenda`
(SQLAlchemy `after_begin`), aplica `set_config('app.fazenda_id', ...)` a cada
transação nova da MESMA sessão — não só na abertura.

**Por que não um `SET LOCAL` direto, uma vez, dentro de `get_session()`:**
`SET LOCAL` só vale até o fim da transação, e o padrão do projeto é
`session.commit()` várias vezes dentro de uma mesma rota (462 ocorrências nos
routers) — cada commit fecha a transação e abre outra por trás (autobegin do
SQLAlchemy). Um disparo único valeria só para a primeira leva de queries.
`after_begin` dispara de novo a cada transação nova, então o contexto é
reaplicado a cada commit — testado explicitamente em
`tests/test_contexto_fazenda_sessao.py`.

Sem RLS ligado em lugar nenhum ainda, esta mudança é **inócua**: nenhuma
política existe para ler `current_setting('app.fazenda_id', ...)`. É o mesmo
desenho de `engine_manutencao` — construído antes de precisar, sem efeito até
o dia em que a política entrar.

Ainda em aberto, de propósito fora deste PR (constam abaixo, na ordem de
trabalho): as rotinas de fundo (item 2) e o `RESET`/nova conexão no retorno ao
pool como segunda linha de defesa contra o vazamento por `SET` sem `LOCAL`
citado na seção 4 de `rls-proposta.md` — o listener já usa `set_config(...,
true)` (o `LOCAL` da função), o que cobre o risco medido lá; reavaliar se
sobra algo quando a política entrar em produção.

### 2. As três rotinas de fundo que operam em laço sobre várias fazendas — FEITO (próximo PR)

Ao implementar, a análise mudou o diagnóstico em dois dos cinco pontos:
`despachar_agenda_do_dia`/`despachar_push_pendentes` e
`enviar_manual_semanal_todas_fazendas` não são apenas "sem `SET LOCAL`" —
elas **enumeram usuários/fazendas de TODO o sistema antes de saber qual
fazenda é de quem** (`usuarios_com_canal_push` lê `PushSubscription`/
`PushTokenFcm` sem filtro nenhum; `_fazenda_do_usuario` só descobre a
fazenda DEPOIS, consultando `Pessoa`, que tem `fazenda_id` e seria
RLS-scoped). Setar `session.info["fazenda_id"]` por iteração não resolve
isso: a PRIMEIRA leitura (a enumeração, e a própria busca de "qual é a
fazenda deste usuário") não tem contexto nenhum para usar ainda — é um
problema de ovo-e-galinha, não de sequência.

A correção real, consistente com o desenho já aprovado (`rls-proposta.md`,
seção 8): estas rotinas sempre filtraram por fazenda **explicitamente em
Python** (nunca dependeram de RLS para isolar) — então a conexão certa é a
`engine_manutencao` (dono das tabelas, enxerga tudo, mesmo desenho de
`_loop_backup_automatico`/boot desde #731/#740), não um contexto por
iteração. RLS ali seria redundante e, pior, cego — nunca a defesa real.

| Onde | Como estava | O que mudou |
|---|---|---|
| `push.py::despachar_agenda_do_dia` | `Session(engine)` em `main.py::_loop_despacho_push` | `Session(engine_manutencao)` — enumera globalmente, filtra em Python (sem mudança dentro de push.py) |
| `push.py::despachar_push_pendentes` | mesma sessão do loop acima | mesmo conserto |
| `manual_fazenda.py::enviar_manual_semanal_todas_fazendas` | `Session(engine)` em `main.py::_loop_manual_fazenda_semanal` | `Session(engine_manutencao)` — `fazendas_do_envio_semanal` enumera todas antes de filtrar |
| `rules/parametros.py::_linha()` | abre `Session(engine)` PRÓPRIA, sem contexto | já sabe o `fid` (ou `None`) ANTES da primeira query — marca `session.info["fazenda_id"] = fid` logo na abertura; usa `engine` normal (não precisa do bypass, é a política de catálogo — `fazenda_id = atual OR NULL` — que resolve os dois casos) |
| `portal.py::_executar_exportacao` | já recebe `fazenda_id` como parâmetro, sem contexto na sessão | mesmo padrão: `session.info["fazenda_id"] = fazenda_id` logo na abertura; filtro em Python continua sendo a defesa real |

**Já resolvidos antes, sem trabalho novo:**
- `main.py::_loop_backup_automatico` — usa `engine_manutencao` desde #731.
- `main.py::lifespan` (os ~50 seeds) e as migrações do boot — usam
  `engine_manutencao` desde #740.

### 3. As políticas em si (`rls-migracao-proposta.sql`) — RLS ATIVO no Staging desde 10/09/2026

**Reconferência feita**: a lista de 18 tabelas de catálogo global do DDL foi
comparada contra o esquema real reconstruído via `alembic upgrade head` num
Postgres descartável — bate exatamente com
`c8e2a4f70b13_fazenda_id_not_null.py::_CATALOGO_GLOBAL`, nenhuma tabela nova
nem removida. O único ajuste foi um comentário desatualizado no próprio
arquivo (dizia "14 tabelas", já eram 18 desde a correção da migração NOT
NULL).

**Testado localmente**: o DDL (passo 1 + passo 2 de conferência) rodou limpo
contra essa réplica do esquema real — 185 tabelas, 18 de catálogo + 167 de
dado, `com_rls_ligada=185, sem_rls_ligada=0`. A reversão (`NO FORCE` +
`DISABLE`) também testada, volta ao estado original.

**Aplicado no Staging de verdade** (via `railway-agent`, a sessão não tem
saída TCP direta — só HTTPS via proxy; o agente do próprio Railway rodou o
SQL com a `DATABASE_URL_MANUTENCAO` que o dono forneceu): resultado
`com_rls_ligada=189, sem_rls_ligada=0` — 18 de catálogo + 171 de dado (as +4
são tabelas `ckpt_a4f8c1d92e07_*`, checkpoints de downgrade da migração de
backfill de órfãos que só existem no Staging porque ele tem dado real com
órfãos passados; confirmado que nenhum código de aplicação as lê, só o
`downgrade()` daquela migração — RLS nelas é inofensivo).

**REVERTIDO na hora, por precaução** — ver "BLOQUEIO" abaixo: a réplica que
estava de fato servindo tráfego no Staging naquele momento era anterior aos
PRs #744/#745, sem o mecanismo de `session.info["fazenda_id"]`; RLS ligado
sobre esse binário teria deixado toda consulta muda, em silêncio.

**REAPLICADO em 10/09/2026, depois do bloqueio resolvido (PR #752) e com
autorização do dono** ("sim para os dois", junto com o merge do PR #753):
mesmo script, mesma `DATABASE_URL_MANUTENCAO`, via `railway-agent` — resultado
idêntico ao da primeira aplicação, `com_rls_ligada=189, sem_rls_ligada=0`.
Desta vez **não foi revertido**. Checagem de saúde imediatamente depois,
igual à da primeira tentativa:

- o deploy que já estava servindo no momento da reaplicação (`b01d2e4f`,
  ativo desde 10:12 UTC, já com o código dos PRs #744/#745/#752) seguiu
  online, sem erro novo nos logs;
- o merge do PR #753 (só documentação) disparou um redeploy novo
  (`780cedf0`) logo em seguida — **subiu com o RLS já ativo no banco**:
  `Application startup complete`, `/health` 200, sem nenhum
  `InsufficientPrivilege` ou erro de contexto ausente. É a confirmação mais
  forte que temos até agora: um boot inteiro (migrações + seeds pela
  `engine_manutencao`, depois a aplicação normal) completou do zero com a
  política já valendo.

Não foi feito ainda (fica para a seção 4, Validação): um teste de leitura
autenticado de verdade (login + tela com dado de fazenda), que é o único
jeito de pegar o cenário "RLS nega tudo em silêncio, sem erro" — `/health`
não passa por nenhuma tabela com política.

De propósito continua um `.sql` avulso, não uma revisão Alembic — a razão
está escrita no próprio arquivo: uma revisão em `alembic/versions/` seria
aplicada em produção no próximo deploy, sozinha.

### ⚠️ BLOQUEIO — RESOLVIDO em 10/09/2026, PR #752

Ao aplicar o DDL acima, a checagem de saúde do FazendaApp no Staging revelou
que os deploys estavam falhando desde pelo menos o PR #747 (de outra sessão,
**nada a ver com este trabalho de RLS**): toda migração que precisa de
`ALTER TABLE` numa tabela que já existia antes do `cowdata_app` ser criado
falhava com `psycopg2.errors.InsufficientPrivilege: must be owner of table X`.

**Causa raiz encontrada (não era a variável)**: `alembic/env.py` importava e
usava `DATABASE_URL` (o role de aplicação) em vez de `DATABASE_URL_MANUTENCAO`
(o role dono). Como `config` dentro de `env.py` é o MESMO objeto que
`_aplicar_alembic()` monta com a URL de dono antes de `command.upgrade(cfg,
"head")`, a linha `config.set_main_option("sqlalchemy.url", DATABASE_URL)` de
`env.py` sobrescrevia essa URL silenciosamente assim que era carregada —
anulando por completo a proteção do PR #740 para qualquer migração real.
`DATABASE_URL_MANUTENCAO` estava correta o tempo todo (confirmado: testada
direto, tem privilégio de dono); passou despercebido porque
`create_all(engine_manutencao)`, rodado logo depois como rede de segurança,
cobre CRIAR tabela nova (o único cenário que `test_boot_conexao_dono.py`
media até então), nunca ALTERAR uma que já existe.

**Correção**: PR #752 — `env.py` agora usa `DATABASE_URL_MANUTENCAO`, com
teste de regressão novo (`test_alembic_usa_a_conexao_de_dono_nao_a_da_
aplicacao`) que reproduz o erro real sem a correção e passa com ela.
Confirmado no Railway: o deploy seguinte ao merge (09:37 UTC) subiu limpo —
"Application startup complete", `/health` respondendo 200, sem o erro de
privilégio nos logs.

**Consequência que isso resolve**: antes da correção, a réplica que estava DE
FATO servindo tráfego no Staging era de 09/09 09:50 UTC — anterior aos PRs
#744 e #745, sem o mecanismo de `session.info["fazenda_id"]`. Reaplicar o RLS
com esse binário rodando teria deixado toda consulta muda (RLS nega tudo sem
contexto, sem erro). Agora o Staging roda o código certo — o pré-requisito
para reaplicar as políticas está atendido.

**Produção nunca teve este problema** (conferido): o deploy da mesma mudança
(#745) subiu limpo em produção no mesmo instante em que falhava no Staging —
porque produção ainda usa a `DATABASE_URL` de dono direto (não migrou para o
`cowdata_app` ainda), então `engine_manutencao` já caía no fallback trivial
(mesma conexão de sempre), mascarando o bug por lá.

### 4. Validação no Staging

Só depois do bloqueio acima resolvido e do DDL reaplicado:

- ~~os oito ataques da seção 10 de `rls-proposta.md`, reproduzidos contra o
  Staging de verdade~~ — **7 de 8 FEITO em 10/09/2026**, ver abaixo;
- um teste de fumaça manual do dono: entrar, abrir uma tela que lê dado de
  fazenda, gravar algo — igual ao que já foi feito na troca de credencial.
  **Ainda pendente — ver nota abaixo**;
- ~~custo de desempenho da política, medido com volume real do Staging~~ —
  **verificado no nível estrutural em 10/09/2026**, ver abaixo.

**Os 7 ataques reproduzidos contra o Staging real (10/09/2026)**: o roteiro
`rls-experimento.sql` original **não podia** ser apontado direto para lá —
ele faz `DROP TABLE`/`CREATE TABLE` de propósito (é para Postgres
descartável; `sanidade`, um dos nomes que ele usa, é tabela real de
produção). Foi escrito `rls-validacao-staging.sql`, sem nenhum DDL, contra
a tabela real `estoque` (dado da fazenda, não catálogo): insere duas
linhas de teste com nome inconfundível (`__RLS_TESTE_VALIDACAO...`) como
dono, roda os ataques como `cowdata_app` (`SET ROLE`, mesma conexão), e
termina com `ROLLBACK` — nada persiste. **Testado antes localmente**,
contra um Postgres descartável com o mesmo schema/role/DDL do Staging
(achou e corrigiu um bug do próprio script de teste:
`estoque.atualizado_em` é `NOT NULL` sem default no banco). Rodado depois
contra o Staging via `railway-agent`, com verificação independente
(conexão nova) de que nenhuma linha de teste sobrou:

| Ataque | Resultado no Staging |
|---|---|
| 1. Ler sem contexto | 0 linhas |
| 2. Fazenda 1 lê fazenda 2 | só a própria |
| 3. Fazenda 1 grava em nome da fazenda 2 | `ERROR: new row violates row-level security policy` |
| 4. Fazenda 1 muda a dona do próprio registro | mesmo erro |
| 5. Fazenda 1 grava registro órfão | mesmo erro |
| 6. Contexto forjado (`1 OR true`) | `ERROR: invalid input syntax for type integer` |
| 7. DELETE da fazenda 1 mirando linha da fazenda 2 | `DELETE 0` |
| 8. `SET` sem `LOCAL` vazando entre requisições | **fora de escopo aqui** — provar exigiria um `COMMIT` real no Staging; já coberto contra Postgres de verdade em `test_contexto_fazenda_sessao.py::test_contexto_reaplicado_apos_commit_no_meio_da_sessao` (suíte de CI) |

Achado incidental, não um risco: só existem 2 fazendas reais no Staging
hoje (1 = Jairo Nasser, com dado; 2 = CowData/empresa, sem dado ainda nas
tabelas de tenant) — por isso os ataques usam linha de teste própria em
vez de dado pré-existente da fazenda 2.

**Custo de desempenho — verificado no nível estrutural (10/09/2026)**:
`EXPLAIN` (sem `ANALYZE`, só leitura) comparando o plano de consulta como
dono (filtro `fazenda_id` escrito à mão) contra o mesmo `SELECT` como
`cowdata_app` com o contexto setado (a política injeta o filtro sozinha):

| Tabela | Como dono (filtro manual) | Como `cowdata_app` (RLS injeta) |
|---|---|---|
| `estoque` (dado da fazenda) | `Index Scan using ix_estoque_fazenda_id` | **mesmo** `Index Scan using ix_estoque_fazenda_id` |
| `principio_ativo` (catálogo, `OR fazenda_id IS NULL`) | `Seq Scan` (tabela pequena, plano do Postgres) | **mesmo** `Seq Scan` |

A política usa o índice de `fazenda_id` do mesmo jeito que um `WHERE`
escrito à mão usaria — o predicado injetado pelo RLS não muda a forma do
plano em nenhum dos dois casos (o `Seq Scan` do catálogo acontece nos
DOIS lados, é o otimizador escolhendo por causa do tamanho pequeno da
tabela, não algo que a política piora). **O que isso NÃO prova**: custo
real sob volume/carga de produção — o Staging hoje tem ~20 linhas no
total nas tabelas de tenant, longe do "volume real" que a seção 11 da
proposta pedia para medir. Essa medição de carga de verdade só faz
sentido com dado em escala (produção, ou uma carga sintética grande em
Staging) — fica registrada como pendência separada, não bloqueia o RLS
(a única coisa que uma medição de carga poderia revelar é a necessidade
de um índice a mais, nunca "desligar a política").

**Teste de fumaça manual — ainda pendente, e por quê**: diferente dos
passos acima, este exige uma sessão de usuário de verdade (login com
credencial real do Staging). Deliberadamente não fui atrás do segredo que
assina os tokens de sessão (`AUTH_SECRET`, variável do Staging) para
forjar um token sozinho — é uma chave mestra (quem a tem assina sessão de
qualquer usuário, de qualquer fazenda) e não fazia parte do que foi
compartilhado para este trabalho (diferente de `DATABASE_URL_MANUTENCAO`,
passada explicitamente pelo dono). Este passo continua esperando o dono
entrar de verdade no Staging (ou uma decisão explícita de liberar outro
caminho).

### 5. Produção

**Só depois do Staging validado, e com autorização explícita.**

- roteiro Railway de novo (`railway-staging-passos.md`), com o seletor de
  ambiente em `production` em vez de `Staging`.

**Regra do aviso prévio à sessão principal — revista em 11/09/2026.** A
regra original ("nada que ative RLS em produção é mergeado sem avisar a
sessão principal antes") supunha uma sessão-mãe acompanhando este trabalho
em paralelo. O dono se desvinculou dela — `ListAgents` confirma que não há
nenhuma outra sessão Claude alcançável — e decidiu, explicitamente, seguir
só por aqui: "Mude o roteiro para não precisar avisar a sessão mãe, pois
desvinculei de lá, então sigamos por aqui." A partir daqui, a autorização
do dono nesta própria conversa é suficiente para produção — não há mais
"aviso prévio" separado para dar, porque não há mais quem avisar.

**Roteiro Railway (28 passos) executado pelo dono em 11/09/2026.** Duas
travas do próprio Railway atrapalharam a execução, resolvidas em tempo
real, registradas aqui para quem repetir isto num quarto ambiente:
- a aba **Data** do console Postgres injeta um `LIMIT` sozinha (é um
  navegador de tabelas, não aceita DDL) — o `CREATE ROLE`/`GRANT` teve que
  ser rodado pela aba **Console** (`psql` de verdade);
- colar uma consulta na aba **Console** enquanto o buffer do `psql` estava
  em modo de continuação (prompt `railway-#`) produzia lixo de bracketed
  paste (`^[[200~`); resolvido com `\r` (limpa o buffer) antes de colar de
  novo.

Conferido ao final: `cowdata_app` criado com `rolsuper=false,
rolbypassrls=false`; `DATABASE_URL` do FazendaApp em `production` trocada
para ele; `DATABASE_URL_MANUTENCAO` mantendo o role dono; deploy seguinte
`Active`, log de build e deploy sem `permission denied`, requisições reais
(`/animais/`, `/producao/`, `/financeiro/...`, `/estoque/`, etc.) com
`200 OK`.

**DDL de RLS aplicado em produção em 11/09/2026**, mesmo padrão do
Staging: via `railway-agent` (a sessão não tem saída TCP direta), conectado
com a `DATABASE_URL_MANUTENCAO` (role dono — conferido antes de rodar:
`current_user=postgres`, não `cowdata_app`). Resultado:
`com_rls_ligada=198, sem_rls_ligada=0` — 18 de catálogo global + 180 de
dado da fazenda (produção não tem as +4 tabelas de checkpoint de downgrade
que só existiam no Staging — coerente, aquelas eram resíduo específico do
histórico de órfãos do Staging). Nenhum erro durante a aplicação.

**Checagem de saúde imediata**: logs do deploy ativo (janela 09:45–10:16
UTC, cobrindo o momento da aplicação do DDL) sem nenhum
`permission denied`/`InsufficientPrivilege`; requisições reais de usuário
em produção (`/agenda/`, `/cadastro/principios-ativos`,
`/notificacoes/`, `/aprovacoes/contagem`) respondendo `200 OK` depois da
ativação. Os únicos avisos nos logs HTTP da janela são de outra natureza —
um `499` (cliente fechou a conexão antes da resposta) e dois `403`
(autorização de aplicação, não de banco) — nenhum dos dois relacionado a
RLS.

### ⚠️ INCIDENTE em 11/09/2026 — teste de fumaça em produção pegou o RLS negando o login em silêncio, REVERTIDO na hora

O teste de fumaça manual pendente acima foi feito minutos depois da
ativação: o dono entrou no app de produção e reportou "a fazenda real
sumiu!" — a tela de troca de fazenda (`/escolher-conta`) só mostrava
"Fazenda Teste" (de um token antigo, de uma sessão de teste anterior) e
"Painel CowData"; a fazenda real do cliente tinha desaparecido da lista.
**Revertido imediatamente** (mesmo `railway-agent`, mesma
`DATABASE_URL_MANUTENCAO`): `DROP POLICY` + `NO FORCE` + `DISABLE` em
todas as 198 tabelas — confirmado `com_rls_ligada=0, sem_rls_ligada=198`.
Produção rodou o resto do incidente SEM RLS.

**Causa raiz — um `ovo-e-galinha` que a seção 2 já tinha nomeado, mas não
nesta ponta**: `POST /auth/login` decide quais fazendas oferecer lendo
`UsuarioFazenda` ANTES de qualquer fazenda estar selecionada — o token de
um login que está acontecendo agora não tem "fid" nenhum ainda. Sob a
política (`fazenda_id = current_setting('app.fazenda_id', ...)`), essa
consulta nega TUDO em silêncio: sem contexto, nenhuma linha bate — não é
"a fazenda errada", é "nenhuma fazenda". Isso derrubava o login de
QUALQUER usuário (não só multi-fazenda): `_fazendas_vinculadas` sempre
voltava vazia, `fazenda_auto` nunca era escolhido, e o token saía sem
"fid" para todo mundo. A tela mostrou "Fazenda Teste" e não uma lista
vazia porque o dono tinha um token ANTIGO no navegador (de um teste
anterior, com "fid" da Fazenda Teste) — `GET /auth/contas-disponiveis` usa
ESSE token, então a política filtrou a lista para só o vínculo que batia
com aquele contexto velho, escondendo a fazenda real.

O mesmo mecanismo quebrava `POST /auth/selecionar-fazenda` (o token do
login ainda não tem a fazenda que a pessoa está tentando escolher — 403
"Você não está vinculado a esta fazenda" para quem estava genuinamente
vinculado) e as duas checagens de identidade da Equipe CowData
(`eh_membro_equipe_cowdata`/`eh_consultor_cowdata`, que leem a `Pessoa` do
usuário na fazenda INTERNA da CowData — quase sempre diferente da fazenda-
cliente hoje selecionada, quando há uma).

**Correção aplicada e testada** (`fazenda/auth.py`,
`fazenda/api/routers/auth.py`, `fazenda/api/routers/fazendas.py`): as
leituras de enumeração/identidade acima passam por
`database.py::sessao_sem_recorte_de_fazenda(session)` — um context manager
novo que só troca para a conexão de dono (`engine_manutencao`, sem RLS)
quando o dialeto é `postgresql`; fora disso (a suíte inteira, SQLite, sem
RLS) devolve a própria `session` recebida, sem abrir nada. Mesmo
raciocínio já registrado na seção 2 para as rotinas de fundo: o filtro de
segurança real é `usuario_id`/`pessoa_id`/`fazenda_id` explícito em
Python, nunca dependeu de RLS, e RLS aqui só cegava. Pool da
`engine_manutencao` ampliado de 1+1 para 5+10 (`database.py`) — deixou de
ser só uma rotina de meia em meia hora, passou a atender caminho de
login/troca de fazenda em toda requisição.

**Regressão pega e corrigida**: a primeira versão desta correção trocava a
conexão sem checar o dialeto — quebrou 71 testes existentes, porque a
suíte roda em SQLite com um engine ISOLADO por teste
(`dependency_overrides[get_session]`), nunca o engine global do módulo, e
`engine_manutencao` sem `DATABASE_URL_MANUTENCAO` é só um nome a mais para
esse engine global. A guarda de dialeto acima resolveu: suíte ampla
filtrada (`-k "auth or login or fazenda or consultor or cowdata or equipe
or vinculo"`) voltou a **972 passed, 0 failed**.

Regressão nova, `tests/test_login_sob_rls.py`, contra PostgreSQL real com
a mesma política do DDL: prova que a consulta pela sessão da requisição
nega o vínculo em silêncio (reprodução do bug), e que `POST /auth/login`/
`GET /auth/contas-disponiveis` voltam a ver a fazenda real com a correção
— testado **sem** a correção (falha, `2 failed`) e **com** ela (passa,
`3 passed`), mesmo rigor do teste do bug de `session.commit()` (PR #760).
Registrada em `ARQUIVOS_POSTGRES` no CI.

**Achado maior — auditoria do Painel CowData concluída em 11/09/2026,
correção AINDA NÃO FEITA.** Login não era o único lugar: TODA rota do
Painel CowData (`painel_cowdata.py`, `painel_cowdata_cadastros.py`,
`painel_cowdata_farmacia.py`, `painel_cowdata_parametros.py`,
`painel_cowdata_sincronizacao.py`, `painel_cowdata_touros.py`,
`painel_cowdata_usuarios.py`) opera **sem fazenda selecionada por
definição** (token sem "fid", de propósito — é um painel cross-tenant) e
várias leem/escrevem tabelas de fazenda filtrando EXPLICITAMENTE por um
`fazenda_id` que vem do PATH/BODY da requisição, não do token.

**Mecanismo exato, mapeado por tabela**: das ~185 tabelas com
`fazenda_id`, 18 são "catálogo global" (`rls-migracao-proposta.sql`) e têm
`USING (fazenda_id = ctx OR fazenda_id IS NULL)` na LEITURA — linhas
globais (`fazenda_id IS NULL`) continuam visíveis mesmo sem contexto.
Todas as outras (~167, "dado de fazenda") são estritas nos dois sentidos.
**Achado extra, não previsto antes desta auditoria**: o `WITH CHECK` de
TODA tabela (mesmo as 18 globais) é sempre `fazenda_id = ctx`, **sem** a
cláusula `OR IS NULL` — ou seja, mesmo a ESCRITA "certa" de uma linha
global (`fazenda_id=None`) falha sob RLS sem contexto, com erro 500 HTTP
duro (`new row violates row-level security policy`), não em silêncio.
Resumindo o padrão de falha do Painel CowData inteiro:
- leitura filtrada por `fazenda_id` real → **0 linhas, sem erro** (nega calado);
- escrita em linha global OU de fazenda real → **500 duro** (`WITH CHECK`).

**PORTÃO de entrada continua são**: `exigir_area_painel_cowdata`/
`exigir_permissao_painel_cowdata` dependem de `PermissaoEquipeCowData`,
que não tem `fazenda_id` — RLS não alcança, ninguém fica trancado do lado
de fora. O problema é só o que cada rota lê/escreve DEPOIS de entrar.

**Achados por gravidade** (mapa completo de endpoint→tabela na auditoria
em si, não repetido aqui — ver histórico desta sessão):

*Mais graves — botão "aplicar em todas as fazendas de uma vez" quebra, ou
sucesso falso sem nenhum erro visível:*
1. **`painel_cowdata_sincronizacao.py` + `rules/replicacao_fazenda.py`**
   ("Sincronizar Fazenda Teste") — o MAIS crítico: sob RLS, `_apagar_destino`
   apaga 0 linhas e `_copiar_tabela` lê 0 linhas da origem (ambos usam a
   conexão da requisição via `session.connection()`, sujeita à política
   igual a qualquer outra), mas **nenhuma dessas operações viola
   `WITH CHECK`** (não há linha pra inserir) — `session.commit()` passa
   limpo e a rota devolve **HTTP 200 "status": "ok"** com
   `"linhas_copiadas": 0`. Reproduz o EXATO sintoma do bug de 11/09/2026 já
   corrigido (PR #760), por uma causa nova — e pior, porque não há
   exceção nenhuma que denuncie.
2. **Fan-out/propagação em massa**: `painel_cowdata_farmacia.py::
   _fan_out_medicamento`/`_criar_item_fanout` (ativar medicamento em toda
   fazenda), `painel_cowdata_cadastros.py::aplicar_item`/`renomear_item`/
   `desativar_item`/`aplicar_metodo` (aplicar cadastro em toda fazenda),
   `painel_cowdata_parametros.py::aplicar_parametro` (aplicar parâmetro em
   toda fazenda, padrão = TODAS) — todos fazem loop sobre as fazendas
   ativas; sob RLS, o `INSERT`/`UPDATE` da primeira fazenda do loop já viola
   `WITH CHECK` → **erro 500 duro, transação inteira aborta**. São os
   botões de propagação em massa do Painel — uso frequente por desenho.
3. **`painel_cowdata_farmacia.py`, escritas do catálogo global**
   (`criar_categoria_global`, `criar_principio_global`,
   `criar_medicamento_global`, `restaurar_catalogo_principios`, etc.) — 500
   duro mesmo fazendo a coisa CERTA (`fazenda_id=None`), por causa do
   `WITH CHECK` sem exceção de NULL citado acima. Cadastro do catálogo
   padrão é operação corriqueira da equipe.

*Graves, uso mais pontual — leitura vazia/404 falso, menos visível mas
ainda quebra:*
4. **`painel_cowdata.py`** — `listar_equipe`/`listar_consultores_cowdata`/
   `listar_folha_membro` vêm vazias; `_pessoa_equipe_ou_404`/
   `_folha_equipe_ou_404` (usadas por editar/excluir membro e folha) caem
   em 404 falso; e **`_movimentos_periodo`** (usada por
   `resumo_financeiro`/`livro_caixa`/`fluxo_caixa`/`dre`) some com a
   receita de assinatura (`CobrancaAsaas`) e a despesa de folha
   (`FolhaPagamento`) — **relatório financeiro da CowData reporta valores
   plausíveis, mas sistematicamente incompletos**, sem erro nenhum.
5. **`painel_cowdata_usuarios.py`** — `listar_pessoas_da_fazenda`/
   `listar_usuarios_da_fazenda` vêm vazias; `criar_usuario_da_fazenda`/
   `editar_usuario_da_fazenda` caem em 404 falso (`session.get(Pessoa,...)`
   nega) ou 500 na escrita do vínculo (`UsuarioFazenda`).
6. **`painel_cowdata_farmacia.py::diagnostico_farmacia`** — todo
   medicamento aparece como "Ausente" mesmo já ativado na fazenda;
   `_montar_medicamento_dict` sempre reporta `fan_out_fazendas: 0`.
7. **`painel_cowdata_cadastros.py::listar_item_agregado`/
   `listar_metodos_agregado`** — visão agregada sempre vazia.
8. **`painel_cowdata_parametros.py::listar_parametros`** — perde a
   informação de quais fazendas já personalizaram um parâmetro.

**Confirmados SEM problema, não precisa mexer:**
- **`painel_cowdata_touros.py`** inteiro — `Touro` não tem `fazenda_id`.
- Leituras do catálogo global em `painel_cowdata_farmacia.py`
  (`listar_categorias_globais`, `listar_principios_globais`,
  `listar_medicamentos_globais`, etc.) — a cláusula `OR fazenda_id IS NULL`
  da LEITURA já cobre.
- Rotas de `LancamentoCowData` (não tem `fazenda_id`) e qualquer rota que
  só consulte `Fazenda` por id/flags próprias.

**CORRIGIDO em 11/09/2026, mesmo dia da auditoria.** Os 8 grupos acima
foram todos corrigidos. Introduzido `database.py::get_session_manutencao`
— uma dependency nova, análoga a `sessao_sem_recorte_de_fazenda` do login,
mas para o ciclo de vida INTEIRO de uma rota (leitura E escrita, não só
uma leitura pontual): depende de `Depends(get_session)` (assim os ~1500
testes que só fazem `dependency_overrides[get_session]` já cobrem esta
também, sem precisar saber que ela existe — FastAPI resolve o override
através da cadeia de `Depends`) e só troca para `engine_manutencao` sob
Postgres de verdade; fora dele (a suíte inteira, SQLite) é a MESMA sessão
que `get_session` já entrega.

Aplicado `Depends(get_session_manutencao)` em vez de `Depends(get_session)`
em toda rota afetada dos 6 arquivos com problema real
(`painel_cowdata.py`, `painel_cowdata_cadastros.py`,
`painel_cowdata_farmacia.py`, `painel_cowdata_parametros.py`,
`painel_cowdata_sincronizacao.py`, `painel_cowdata_usuarios.py`) —
`painel_cowdata_touros.py` confirmado sem necessidade de mudança nenhuma.

**Testado**: dois testes de regressão novos contra PostgreSQL real, com a
mesma política do DDL de produção — `tests/test_sincronizacao_sob_rls.py`
(prova que a Sincronização volta a copiar dado de verdade, não `"status":
"ok"` com 0 linhas) e `tests/test_painel_cowdata_massa_sob_rls.py`
(representante do padrão "aplicar em todas as fazendas de uma vez" —
mecanismo idêntico nos 3 botões, não repetido teste por teste). Suíte
Postgres/RLS completa: **17 passed**. Suíte SQLite filtrada por
`painel_cowdata`/`cowdata`: **182 passed, 1 skipped**. Suíte SQLite
completa (~5.400 testes, 13 lotes): confirmação final em andamento no
momento deste registro — nenhuma falha nos lotes concluídos até aqui.

**O que ainda falta antes de religar RLS em qualquer ambiente:**
- Staging está com RLS ligado desde 10/09/2026 — o Painel CowData lá
  segue rodando com o código ANTIGO (sem esta correção) até o deploy do
  PR desta correção acontecer; até lá, tratar as funcionalidades do
  Painel CowData no Staging como suspeitas.
- Produção continua REVERTIDA (sem RLS) — segura, mas o item "5. Produção"
  ainda não pode ser considerado fechado: falta reaplicar o DDL (a
  infraestrutura — role `cowdata_app`, `DATABASE_URL_MANUTENCAO` — já está
  pronta) e um teste de fumaça que desta vez cubra Painel CowData também,
  não só login.

## Achados novos, registrados como pendência (não bloqueiam o RLS)

Encontrados ao escrever a migração de FKs compostas (#742), documentados em
`fks-compostas.md`, achado 3:

| | Tamanho | Por que não é urgente |
|---|---|---|
| `tabela.fazenda_id → fazenda.id` sem FK nenhuma | **113 tabelas** | lacuna de integridade referencial — não afeta o isolamento por RLS, que não depende dessa FK |
| Pares entre tabelas de fazenda sem FK nenhuma (nem simples) | **10 pares** | mesma causa-raiz; compor exigiria checar órfão antes, uma migração própria |

Cada uma merece sua própria auditoria e migração, no mesmo padrão de rigor
das anteriores (savepoint, nunca aborta o boot, teste contra Postgres real).
Nenhuma delas precisa vir antes do RLS — são achados paralelos, não
pré-requisitos.

## Parado a pedido do dono

- **Telegram** (achado 61): `TELEGRAM_CHAT_FAZENDA` vazio no Railway faz todo
  documento do robô nascer sem fazenda. O dono pediu para deixar em espera.

## Fora do escopo desta sessão — arquivos de outra sessão

Achado em `cadastro/pessoas.py`, `exclusoes.py`, `pedidos.py`,
`financeiro.py`, `rh_folha.py`, `rh_contratos.py`, `documentos.py`,
`fotos.py` → relatar ao dono, nunca editar (são território de outra sessão
de trabalho em paralelo).

## A ordem de trabalho a partir daqui

1. ~~`SET LOCAL app.fazenda_id` em `get_session()`~~ — **feito, PR #744
   (mergeado 09/09/2026).**
2. ~~As rotinas de fundo (seção 2 acima)~~ — **feito, PR #745 (mergeado
   09/09/2026).**
3. ~~Reconferir e aplicar o DDL das políticas no Staging~~ — **feito e
   REVERTIDO em 10/09/2026 por precaução** (ver seção 3 acima). O DDL em si
   estava pronto e testado.
3.1. ~~Bloqueio: `DATABASE_URL_MANUTENCAO` do Staging não estava dando
   privilégio de dono~~ — **RESOLVIDO, PR #752 (mergeado 10/09/2026)**: o bug
   era em `alembic/env.py`, não na variável. Deploy do Staging confirmado
   saudável depois do merge.
3.2. ~~Reaplicar o DDL de RLS no Staging~~ — **FEITO em 10/09/2026, com
   autorização do dono, e desta vez MANTIDO** (ver seção 3 acima). Checagem de
   saúde pós-ativação: deploy em curso e o deploy seguinte (via merge do
   PR #753) subiram limpos.
4. ~~Validar no Staging (seção 4): os oito ataques~~ — **7 de 8 FEITO em
   10/09/2026** (ver seção 4 acima; o 8º já está coberto pela suíte de CI).
   ~~Custo de desempenho com volume real~~ — **nível estrutural verificado
   em 10/09/2026** (mesmo índice usado com e sem a política; medição de
   carga de verdade fica para quando houver volume em escala). O teste de
   fumaça manual (login + leitura de dado de fazenda) **acabou sendo feito
   em PRODUÇÃO, não no Staging** (ver item 5) — e achou um bug real.
5. Produção — **FEITO E REVERTIDO em 11/09/2026** (ver seção 5 acima,
   "INCIDENTE"). Roteiro Railway (28 passos) executado, DDL de RLS
   aplicado, teste de fumaça manual do dono pegou o login negando a
   fazenda real em silêncio — revertido na hora. Causa raiz encontrada e
   corrigida (`_fazendas_vinculadas`/`_vinculo`/`eh_membro_equipe_cowdata`/
   `eh_consultor_cowdata`/`minhas_fazendas` agora leem por
   `engine_manutencao`, com teste de regressão contra Postgres real). Ao
   investigar, achado um problema MAIOR e ainda não corrigido: as 7 rotas
   do Painel CowData (leitura/escrita por `fazenda_id` explícito, sem
   token de fazenda) estão expostas ao mesmo padrão de bug — PRÉ-REQUISITO
   NOVO antes de religar RLS em qualquer ambiente (ver seção 5).
5.1. **NOVO, ainda não feito**: auditar as 7 rotas do Painel CowData
   (`painel_cowdata*.py`) e migrar cada leitura/escrita de tabela com
   `fazenda_id` para `engine_manutencao` (ou `SET LOCAL` explícito por
   request), com teste de regressão contra Postgres real por rota — mesmo
   padrão do item acima. Staging continua com RLS ligado desde 10/09 e
   NÃO tem esta parte validada — tratar as funcionalidades do Painel
   CowData lá como suspeitas até a auditoria fechar.
5.2. Só depois de 5.1: repetir o roteiro Railway + DDL em produção (a
   parte de infraestrutura já está pronta — role `cowdata_app`,
   `DATABASE_URL_MANUTENCAO` — só falta religar o DDL) e refazer o teste
   de fumaça manual, desta vez cobrindo também o Painel CowData.

Cada item, ao ser fechado, deve atualizar este documento — é o registro
vivo, não uma foto de hoje.
