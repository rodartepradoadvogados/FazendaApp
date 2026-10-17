# FazendaApp — Software de Gestão da Fazenda Estreito Ponte de Pedra

## Estrutura do projeto

```
FazendaApp/
├── backend/                    # FastAPI + SQLModel
│   ├── fazenda/
│   │   ├── models/             # Modelos de banco (Animal, Servico, Parto, ...)
│   │   ├── parsers/            # Parsers dos CSV do Ideagri
│   │   │   ├── utils.py        # Utilitários (Win-1252, datas, decimais)
│   │   │   ├── geral.py        # GERAL.csv
│   │   │   ├── reprodutivo.py  # Consulta_SQL_v8.csv
│   │   │   ├── conta_gerencial.py
│   │   │   └── estoque.py
│   │   ├── rules/              # Regras de negócio (puras, testáveis)
│   │   │   ├── gestation.py    # Gestação por raça
│   │   │   ├── dry_off.py      # Secagem (60d, só vacas)
│   │   │   ├── scratch_pev.py  # Scratch (14d) + PEV (45d)
│   │   │   ├── iatf.py         # IATF — candidatas + doses
│   │   │   ├── bst.py          # BST — elegibilidade
│   │   │   └── agenda_engine.py # Motor da agenda
│   │   ├── api/routers/        # Endpoints FastAPI
│   │   │   ├── animais.py
│   │   │   ├── upload.py
│   │   │   ├── agenda.py
│   │   │   └── financeiro.py
│   │   ├── config.py           # Configurações (lê .env)
│   │   └── database.py         # Engine SQLite/PostgreSQL
│   ├── tests/
│   │   └── test_rules.py       # 27 testes das regras de negócio
│   ├── main.py                 # Ponto de entrada FastAPI
│   ├── requirements.txt
│   └── .env                    # DATABASE_URL (SQLite local)
├── frontend/                   # Next.js 14 + Tailwind
└── run_dev.py                  # Inicia backend em modo dev
```

## Como rodar o backend

### 1. Instalar dependências
```powershell
python -m pip install -r backend/requirements.txt
```

### 2. Rodar os testes
```powershell
python -m pytest backend/tests/ -v
```

### 3. Iniciar o servidor
```powershell
python run_dev.py
```
Acesse: http://localhost:8000/docs (Swagger UI interativo)

### 4. Carregar dados (CSV do Ideagri)
Use o Swagger em `/docs` ou a tela `/upload` do frontend.

**Ordem recomendada de upload:**
1. `GERAL.csv` → POST /upload/geral
2. `Consulta_SQL_v8.csv` → POST /upload/reprodutivo
3. `ESTOQUE.csv` → POST /upload/estoque
4. `CONTA_GERENCIAL.csv` → POST /upload/conta_gerencial

### 4.1. Sincronização automática (sem upload manual)

`sync_agent.py` vigia uma pasta local e envia os CSV sozinho — elimina o
arrastar-e-soltar e resolve o problema de cache do Google Drive (Seção 7 do
`CONTEXTO_PROJETO_FAZENDA.md`). Só usa a biblioteca padrão do Python.

```powershell
# No Ideagri: agendar a exportação diária dos relatórios para uma pasta, ex. C:\FazendaApp\ideagri
python sync_agent.py --dir C:\FazendaApp\ideagri --api https://SEU-BACKEND.up.railway.app
```

Ele detecta cada arquivo pelo nome, espera terminar de ser escrito, envia na
ordem correta e só reenvia quando o conteúdo muda (hash em `.sync_state.json`).
Use `--once` para rodar uma vez ou deixe rodando (varre a cada `--intervalo` s).

### 5. Consultar a agenda
```
GET http://localhost:8000/agenda/
GET http://localhost:8000/agenda/?data=2026-07-10
```

## Como rodar o frontend

```powershell
cd frontend
npm run dev
```
Acesse: http://localhost:3000

## Variáveis de ambiente (backend/.env)

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./fazenda.db` | URL do banco. Trocar por `postgresql://...` no deploy |
| `SECRET_KEY` | `change-me` | Chave secreta para JWT (futuro) |
| `ENVIRONMENT` | `development` | `development` ou `production` |
| `FIRECRAWL_API_KEY` | (vazio) | Busca na web / leitura de páginas públicas (`fazenda/rules/firecrawl.py`). Vazio = desligado (fail-closed) |
| `TYPESAFE_JEV_KEY` | (vazio) | API da TypeSafe/Jev (julgamentos tipados: classificação, pontuação, extração). Chave de console.typesafe.ai/keys, não do OpenRouter; passar explícita ao SDK (o padrão dele é TYPESAFE_API_KEY). Ainda sem uso no código; só no backend (Railway > Variables). Integração futura deve ser fail-closed sem ela |

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/animais/` | Lista animais (filtros: grupo, sit_rep) |
| GET | `/animais/{numero}` | Busca animal |
| POST | `/upload/{tipo}` | Upload CSV (geral/reprodutivo/estoque/conta_gerencial) |
| GET | `/agenda/` | Agenda preditiva (param: `?data=YYYY-MM-DD`) |
| POST | `/agenda/manual` | Adicionar evento manual |
| PUT | `/reproducao/visita-reprodutiva` | Define (ou limpa, com `null`) a próxima visita (`data`, < hoje → 400) e/ou a data da última visita (`ultima`, > hoje → 400); só o campo enviado muda |
| POST | `/reproducao/agenda-reprodutiva/card` | Um card configurável (situação, lotes, períodos). Cada item traz o diagnóstico do serviço vigente e a **fase** (`a_tocar` / `a_reconfirmar` / `reconfirmada`) com o prazo AINDA NÃO (`ainda_nao`, `dias_para_prazo`, `prazo_tipo`); a resposta traz `parametros` (`dias_toque`, `dias_reconfirmacao`) |
| POST | `/reproducao/agenda-reprodutiva/cards` | Vários cards numa chamada (`{"cards":[{"id","config"}]}`, máx. 40): o estado do rebanho é calculado uma vez; devolve `resultados[id]` igual ao do card avulso |
| GET | `/financeiro/dre` | DRE por período e regime |
| GET | `/financeiro/contas-a-pagar` | Contas próximas |

## Planos comerciais e módulos contratados

Cada fazenda (tenant) tem um contrato (`contrato_fazenda`) com módulos ativos (`contrato_fazenda_modulo`). A trava é dupla:
a permissão do **usuário** (`exigir_modulo`) e o módulo **contratado pela fazenda** (`exigir_modulo_contratado`, `main.py`). Fazenda nova
nasce `aguardando_aprovacao` e sem módulo até o dono da plataforma aprovar o contrato (Painel CowData > Fazendas).

| Plano | Módulos | Preço inicial/mês |
|---|---|---|
| Standard | rebanho, reprodutivo | R$ 250 |
| Silver | + produtivo, sanitário, financeiro | R$ 350 |
| Gold | + planejamento, pedidos, estoque, alimentação, agricultura | R$ 420 |
| Diamond | Gold + consultor | R$ 500 |
| **Financeiro** | financeiro, pedidos (sem rebanho) | R$ 200 |
| Sob medida | módulos avulsos, respeitando as dependências | soma dos módulos |

- **Dependências** (`DEPENDENCIAS_MODULOS`, `fazenda/models/planos.py`): estoque ⇒ rebanho + financeiro; pedidos e planejamento ⇒ financeiro;
  reprodutivo, produtivo, sanitário e alimentação ⇒ rebanho. Todo contrato precisa de um módulo base (rebanho ou financeiro). Contratos antigos não são revalidados.
- **Preço**: o preço de cada plano é editável no Painel CowData (`PUT /fazendas/catalogo/precos-plano/{plano}`, tabela `preco_plano`). O preço do contrato **fecha na
  aprovação** (`contrato_fazenda.preco_mensal_fechado`); mudar o catálogo depois não altera contrato já fechado nem a cobrança (Asaas/boleto).
- **Estoque**: sem o módulo `estoque` contratado, nenhum efeito colateral (Pedidos, lançamentos do Financeiro) grava estoque (`rules/estoque_baixa.py`).
- **Custo do estoque (15/10/2026)**: toda compra de produto estocável pelo Financeiro grava o **último custo por unidade de estoque** em
  `Estoque.valor_unitario` (valor unitário da linha ÷ tamanho da embalagem, quando a compra é por embalagem; ou valor total ÷ quantidade).
  É esse campo que dá custo à aplicação de medicamento (`rules/aplicacao_preventiva.py`). Só atualiza quando a unidade é segura e a compra é a mais recente (não mexe em item de sêmen, nem em item com embalagem padrão comprado sem escolher a embalagem, nem com data anterior à última compra). `LoteEstoque.valor_unitario` guarda o preço de
  **uma embalagem**, como digitado — nenhum relatório lê esse campo hoje. Política = último custo; média ponderada é decisão pendente.
- **Lançamento financeiro (15/10/2026)**: despesa por **embalagem** (`apresentacao_id` por item, nº de embalagens × tamanho = unidade do estoque);
  fornecedor sugere o resto pelo último lançamento dele (só campos vazios); confirmação com **Desfazer** (usa o fluxo de Excluir lançamento) e
  "Lançar outro igual". **Faturas › Lançar notas** e **Pedidos em aberto › Finalizar pedido** abrem em **gaveta de 75% da tela**;
  `responsavel` opcional em `LoteIn`/`NotasNaFaturaIn`/`NotasAvulsasIn` (devolvido por nota). Detalhes: `docs/auditoria-faturas-lancar-notas.md`
  e `docs/mockups/lancamento-financeiro/COMPARACAO_tela_real.md`.
- **Lançamento financeiro — colunas (15/10/2026)**: as duas colunas de despesa/receita têm **rolagem própria** (classe `.fin-coluna` em `globals.css`; só a partir de `lg`, altura = janela − cabeçalho/barra de salvar; dentro de modal e gaveta sobra menos).
- **Visita reprodutiva (15/10/2026)**: UMA regra (`rules/visita_reprodutiva.py`) para a data da próxima visita: **data definida por você** (parâmetro `proxima_visita_reprodutiva_data`, enquanto não passou) > âncora + `intervalo_visita_reprodutiva` > nenhuma, onde a âncora é a mais recente entre a **data da última visita** (parâmetro `ultima_visita_reprodutiva_data`, informada em Insights › Listas › Agenda Reprodutiva, no diálogo da Agenda ou em Parâmetros) e o último serviço do rebanho. Com a última visita informada como âncora o ciclo é fixo: se já venceu, avança de intervalo em intervalo até a próxima data futura (assim o comunicado de véspera/dia não some se ninguém atualizar). Os dois campos são o componente `components/reproducao/CamposVisitaReprodutiva.tsx`.
  Quem lê: motor da Agenda, **comunicado da Agenda** ("Amanhã: visita reprodutiva" na véspera, "Visita reprodutiva" no dia — vem em `GET /agenda/` e `/agenda/painel` (`comunicados`) e, no Dia a dia, em `GET /agenda/dia` (`comunicados_dia`); `data` = dia do aviso, `data_visita` = a visita),
  a projeção da **Insights › Listas › Agenda Reprodutiva** (nota "Cenário projetado para …" tem a data clicável) e as candidatas de IATF. Dois lugares mudam a data com o mesmo diálogo
  (`components/reproducao/DefinirDataVisitaModal.tsx` → `PUT /reproducao/visita-reprodutiva`): o comunicado da Agenda ("Definir nova data da visita") e a nota do cenário projetado; também dá para editar em Configurações › Parâmetros.
  O comunicado leva a `/relatorios?sub=vet` (a página aplica `?sub=vet` depois de ler a permissão `vet`) e, no app do celular, a `/app/menu#agenda-reprodutiva`. Data definida que já passou volta sozinha ao cálculo automático.
- **Fase do diagnóstico e selo AINDA NÃO (17/10/2026)**: `rules/fase_toque.py` é a regra única de **a tocar** (inseminada sem diagnóstico, inclusive toque indefinido), **a reconfirmar** (toque positivo marcado para retoque — `Servico.retoque` —, ou vaca importada sem marca) e **reconfirmada** (reconfirmação positiva, reconfirmada direto ou novilha sem marca de retoque).
  **AINDA NÃO** = dentro do prazo de Parâmetros: `dias_toque − dias da IA` (a tocar) e `dias_toque + dias_reconfirmacao − dias da IA` (a reconfirmar). Nunca usa o intervalo entre visitas e nunca bloqueia lançamento.
  Cards e tabelas da Agenda Reprodutiva (site e app) ganham as colunas Toque/confirmação e Retoque/reconfirmação (data + P/V/I), a Situação, o selo dourado (pulsa só com ≤ 3 dias) e o filtro A tocar / A reconfirmar / Reconfirmadas (`components/reproducao/FaseToque.tsx`, `lib/fasesToque.ts`). Os cards carregam por `POST /agenda-reprodutiva/cards` (uma chamada, em vez de uma por card).
- **Notificações push (15/10/2026)**: o app **não repete aviso**. À noite (a partir das 18h de Brasília, `HORA_RESUMO_NOITE` em `routers/push.py`) sai UM push "Compromissos de amanhã" por usuário (`despachar_resumo_da_noite`; substitui o "Agenda do dia" da manhã). Depois disso só avisa o que for **novo**, **uma vez por evento**: a identidade do evento (`_chave_evento`) não leva a data de hoje — antes a chave era conteúdo + dia, então todo alerta que a Agenda recria diariamente (atrasadas, estoque abaixo do mínimo, conta vencida…) voltava a avisar todo dia, um push por item. A marca vale enquanto o evento existe e é esquecida quando ele some da varredura (problema resolvido que volta = evento novo). Mais de 3 novidades numa varredura viram um push agrupado; aviso de amanhã durante o dia fica para o resumo; a visita reprodutiva conta como um evento só (véspera e dia). "Hoje" nas varreduras é o de Brasília (`rules/datas.py`), não o UTC do servidor.
- **Fazenda só-financeiro**: sem Capa/indicadores, a página inicial é a Agenda (`lib/modulos.ts::rotaInicial`). A visibilidade de menu/rotas vem de uma tabela única em `frontend/lib/modulos.ts`.
- **Preparar financeiro**: `POST /fazendas/{id}/financeiro/preparar` (dono, idempotente) carrega um *rascunho* de plano de contas (validar com o contador) e liga as regras v2 só se a fazenda não tem lançamentos.
- Detalhes e decisões: `docs/planos-plano-financeiro/` (`PLANO_v2.md`, `CONTRATO_API.md`).

## Regras de negócio implementadas

Todas as regras da Seção 5 do `CONTEXTO_PROJETO_FAZENDA.md` estão em `backend/fazenda/rules/`:

| Módulo | Regra | Critério |
|---|---|---|
| `gestation.py` | Gestação | Holandês 280d / Girolando 287d / Gir+Zebu 295d |
| `dry_off.py` | Secagem | 60d antes do parto; só vacas (ordem_parto > 0) |
| `scratch_pev.py` | Scratch | 14d pós serviço; NEGATIVO cancela |
| `scratch_pev.py` | PEV | 45d pós parto |
| `iatf.py` | IATF | Vaz. apt. / Vaz. atr. / Diag. NEGATIVO; calcula doses |
| `bst.py` | BST | Grupos 01/02/03; DEL≥60; >15d p/ secar |
| `agenda_engine.py` | Motor agenda | Orquestra tudo → lista cronológica |

## Deploy (produção)

**Railway** (recomendado — une backend + banco num projeto):
1. Criar projeto Railway
2. Add service: PostgreSQL → copiar `DATABASE_URL`
3. Add service: GitHub repo → `backend/` → `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add service: GitHub repo → `frontend/` → Next.js auto-detected

**Vercel** (alternativa para o frontend):
- Deploy `frontend/` no Vercel
- Setar `NEXT_PUBLIC_API_URL` apontando para o Railway
