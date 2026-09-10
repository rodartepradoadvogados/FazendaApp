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

- os oito ataques da seção 10 de `rls-proposta.md`, reproduzidos contra o
  Staging de verdade (o roteiro `.sql` já existe, é só apontar para lá);
- um teste de fumaça manual do dono: entrar, abrir uma tela que lê dado de
  fazenda, gravar algo — igual ao que já foi feito na troca de credencial;
- custo de desempenho da política, medido com volume real do Staging —
  item que a proposta deixou em aberto (seção 11) e ninguém mediu ainda.

### 5. Produção

**Só depois do Staging validado, e com autorização explícita.** Duas coisas
valem para este passo, e são regra permanente deste projeto, não só desta
etapa:
- roteiro Railway de novo, com o seletor de ambiente em `production`;
- **nada que ative RLS em produção é mergeado sem avisar a sessão principal
  antes** — combinado com o dono, vale para todo o trabalho de RLS.

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
4. **Próximo passo real**: validar no Staging (seção 4) — os oito ataques da
   seção 10 de `rls-proposta.md`, um teste de fumaça manual do dono (login +
   leitura de dado de fazenda) e o custo de desempenho com volume real.
5. Produção — só com autorização e aviso prévio à sessão principal.

Cada item, ao ser fechado, deve atualizar este documento — é o registro
vivo, não uma foto de hoje.
