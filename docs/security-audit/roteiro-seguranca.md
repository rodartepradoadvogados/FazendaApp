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
| Rotinas de fundo sem contexto de fazenda | (este PR) | `push.py`/`manual_fazenda.py` passam a usar `engine_manutencao`; `parametros.py`/`portal.py` marcam `session.info["fazenda_id"]` na abertura |

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

### 3. As políticas em si (`rls-migracao-proposta.sql`)

O DDL parametrizado já existe e é dinâmico (varre o catálogo do banco, não
lista escrita à mão) — mas foi escrito e medido em 06/09/2026, **antes** das
etapas 1 e 2 acima. Antes de rodar:

- reconferir a lista de 18 tabelas de catálogo global contra o esquema atual
  (a mesma lista já foi usada, verificada, em `c8e2a4f70b13` e
  `472f92e0860b` — deveria bater, mas confirmar antes de aplicar);
- **de propósito, continua um `.sql` avulso, não uma revisão Alembic** — a
  razão está escrita no próprio arquivo: uma revisão em `alembic/versions/`
  seria aplicada em produção no próximo deploy, sozinha. Aplicar primeiro no
  Staging, à mão, como os passos do roteiro Railway.

### 4. Validação no Staging

Depois de 1 e 2 mergeados e o DDL aplicado no Staging:

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
2. ~~As rotinas de fundo (seção 2 acima)~~ — **feito, este PR.**
3. Reconferir e aplicar o DDL das políticas no Staging (fora de PR — é SQL
   direto, como os 28 passos).
4. Validar no Staging (seção 4).
5. Produção — só com autorização e aviso prévio à sessão principal.

Cada item, ao ser fechado, deve atualizar este documento — é o registro
vivo, não uma foto de hoje.
