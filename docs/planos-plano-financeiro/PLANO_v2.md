# PLANO v2 — "Plano Financeiro": fazenda só com módulo Financeiro (CowData/Milk)
Data: 2026-10-13 · Base: HEAD c8fc20a (branch claude/farm-app-access-bikeej) · Status: revisado por contador + impeccable critique/audit
Substitui: PLANO_v1_fazenda_so_financeiro.md. Evidência e correções: RELATORIO_critique_audit.md (mesma pasta).
Leitura obrigatória do implementador antes de codar: AGENTS.md, README.md, CONTEXTO_PROJETO_FAZENDA.md, PRODUCT.md, DESIGN.md,
frontend/AGENTS.md (Next 16: ler `node_modules/next/dist/docs/01-app/03-api-reference/04-functions/use-router.md` e `redirect.md`
antes de mexer em `app/page.tsx`/`AuthShell.tsx`; `middleware` agora é `proxy` — este plano NÃO usa proxy).

## 1. Objetivo
Cadastrar uma fazenda cliente que contrata SÓ o Financeiro: Controle Financeiro + Cotações + Pedidos, Agenda como página inicial, sem Capa,
sem Estoque, sem Rebanho/Reprodutivo/Produtivo/Sanitário — e que o CONTADOR consiga confiar nos números. "Pronto" = (1) a fazenda navega sem
ver nem esbarrar em nada que não comprou; (2) nenhum módulo não contratado grava dado "por baixo"; (3) o preço contratado é fato do contrato;
(4) o contador abre o painel dele e baixa o pacote; (5) upgrade/downgrade não apaga nem reescreve nada.

## 2. Decisões do Jairo já FECHADAS (mantidas do v1)
D1. Pedidos só dá entrada em estoque se a fazenda tem `estoque` contratado. Estoque exige, no mínimo, rebanho + financeiro.
D2. Plano "Financeiro": R$ 200,00/mês inicial, EDITÁVEL no Painel CowData (não hard-coded).
D3. Agenda = página inicial; mostra contas e atividades/eventos manuais ("Atividades" e "Gestão/Financeiro"); sem cards de rebanho/reprodução/sanidade.
   (Interpretação v2: "contas a pagar/receber" = ver Decisão P10; hoje a Agenda só tem a pagar — RELATORIO §(d)-7.)

## 3. O que está PROVADO neste v2 (leitura de código) e o que NÃO está
Provado por leitura (arquivo:linha no RELATORIO §(d)): gates de rota (main.py:915-1053), mapeamentos de módulo no front (api.ts:185-231),
preço lido ao vivo em 3 lugares (fazendas.py:389, asaas.py:37, cobranca.py:30), efeitos colaterais de estoque em Financeiro e Pedidos,
Painel do Contador depende de rebanho (contador/page.tsx:178-181), Agenda só conta a pagar (agenda.py:~575-595), `tem_reproducao` sem filtro de
contrato (agenda.py:1736), contrato cacheado no cliente (api.ts:415,461,1048), fazenda nova sem plano de contas (fazendas.py:60-100).
NÃO provado (nada foi executado): sonda 200/403 do v1, qualquer tela no navegador, pytest, rotas listadas em RELATORIO §(e). Tratar toda linha
de "Aceite" abaixo como hipótese até o teste correspondente passar.

## 4. Lacunas (G) — v1 corrigido e ampliado
G1  Rebanho obrigatório (fazendas.py:452-453; teste test_contrato_sob_medida_exige_rebanho; UI FazendasAdmin 131/189/533, Mobile 139/186/530; docstrings planos.py:1-20, fazendas.py:65-67).
G2  Preço do plano: constante em código lida ao vivo por MRR/contrato, boleto (cobranca.py) e Asaas (asaas.py); sem congelamento; sem UI de preço (PrecoModulo sem chamador).
G3  Dependências entre módulos não validadas em lugar nenhum.
G4  Backend transversal sem gate de contrato: /indicadores (main.py:1001) e afins; Agenda não filtra "Reprodutivo"/"Rebanho" por contrato (agenda.py:103,1736).
G5  Efeito colateral em estoque sem checar módulo: pedidos.py:491-503 e financeiro.py:4420-4475, 5152-5163, 5250-5265 → ponto único `estoque_baixa.movimentar/abrir_lote`.
G6  Front: regra de visibilidade em 3 mapas divergentes; Capa/Lançamentos/Protocolos/Insights visíveis; flash do menu completo; Home sempre "/"; contrato cacheado e
    estado "aguardando/suspenso" invisível; pickers de produto dependem de GET /estoque/.
G7  Painel do Contador quebra sem Rebanho (P0).
G8  Agenda: Painel de rebanho, formulário manual de rebanho, 2 chamadas 403 no mount, sem "a receber", vencidas só 30 dias.
G9  Financeiro: árvore de relatórios sem filtro por módulo (Plano→planejamento; Registros→rebanho), copy de desenvolvedor, empty state manda importar CSV do Ideagri.
G10 Onboarding da fazenda nova: sem plano de contas, regras v2 desligadas, checklist de rebanho (onboarding.py:20-23).
G11 Migração: f6a7b8c9d0e1 quebra em SQLite vazio; migração nova roda no BOOT em produção (database.py:507).
G12 Mobile `/app` (casca de curral) sem filtro de módulo (app/app/page.tsx).

## 5. Fases (cada fase = um commit/PR pequeno; "Aceite" é observável)

### F0 — Rede de segurança (sem mudança de comportamento)
0.1 Preparar ambiente: `pip install -r backend/requirements.txt` (num venv no scratchpad/CI, nunca no repo); `cd frontend && npm test` roda.
    Aceite: `python -m pytest backend/tests/test_planos_contrato.py backend/tests/test_agenda_permissoes.py backend/tests/test_agenda_v2.py backend/tests/test_alembic_heads.py -q`
    executa. Registrar na nota de sessão o BASELINE (passa/falha) — não corrigir falhas fora de escopo.
0.2 Migração f6a7b8c9d0e1: corrigir NO LUGAR (`op.batch_alter_table` no `alter_column`; manter `revision`, `down_revision='g7h8i9j0k1l2'`, idempotência por inspector).
    NÃO criar revisão nova. Coordenar com a tarefa já spawnada (task_18b08455): se ela já entregou, apenas verificar; se não, fazer aqui e dispensá-la.
    Aceite: `pytest backend/tests/test_migracao_tabelas_faltantes.py backend/tests/test_alembic_heads.py` passa (upgrade head em SQLite vazio; uma cabeça só).
0.3 Teste "caracterização" (golden) ANTES de mudar gating: para contratos Standard, Silver, Gold e "fazenda #1 grandfathered", gravar a matriz status-por-rota
    (lista fixa de ~40 GETs: /animais/, /estoque/, /pedidos/, /cotacoes/, /financeiro/opcoes, /planejamento/orcamento, /indicadores/, /agenda/…, /relatorio-compra-venda-animais/).
    Aceite: `tests/test_matriz_modulos.py` passa no código ATUAL (documenta o comportamento de hoje) e é a rede de proteção das fases seguintes.

### F1 — Backend: contrato, dependências, preço (sem tocar tela)
1.1 `planos.py`: `DEPENDENCIAS_MODULOS` = {pedidos:[financeiro], planejamento:[financeiro], estoque:[rebanho, financeiro], reprodutivo:[rebanho], produtivo:[rebanho],
    sanitario:[rebanho], alimentacao:[rebanho]} (agricultura: sem dependência, ver P9). Função `validar_dependencias(modulos)->list[str]`.
    `definir_contrato`: remove a exigência fixa de Rebanho (fazendas.py:452-453) e exige "ao menos um módulo base (rebanho ou financeiro)" + dependências; erro 400 em português
    ("Estoque exige Rebanho e Financeiro"). Vale para plano de catálogo e sob medida. Contratos EXISTENTES não são revalidados na leitura (grandfather).
    Aceite: teste renomeado `test_contrato_sob_medida_exige_base_e_dependencias` (financeiro sozinho = 200; estoque sem rebanho = 400; pedidos sem financeiro = 400; sem nada = 400).
1.2 Plano `financeiro` em PLANOS_CATALOGO: nome "Financeiro", módulos [financeiro, pedidos], preço padrão 200.00. Preço do pacote gravado na linha `financeiro` (não `rebanho`) —
    regra: "primeira linha do pacote = rebanho se presente, senão a primeira" (fazendas.py:444).
    Aceite: PUT contrato plano="financeiro" → GET devolve 2 módulos ativos e `preco_mensal` 200.0.
1.3 PREÇO (um lugar só). Migração alembic NOVA (down_revision='f6a7b8c9d0e1'), idempotente (has_table/has_column), com: tabela `preco_plano` (plano PK, preco, atualizado_em,
    atualizado_por_usuario_id) semeada com os 5 preços atuais; coluna `contrato_fazenda.preco_mensal_fechado` (Float, nullable); backfill: contratos com `plano` e status `ativo`
    recebem o preço de catálogo de HOJE (não muda nenhum valor cobrado hoje). Função única `preco_mensal_do_contrato(session, contrato, modulos)` em `planos.py`:
    `preco_mensal_fechado` se houver → senão `preco_plano` → senão constante; sob medida = soma dos módulos ativos (como hoje). Substituir as 3 cópias:
    fazendas.py:389-391 (e o MRR em `resumo_cowdata`), asaas.py:30-39, cobranca.py:24-33. Congela em `aprovar_contrato` e quando o `plano` MUDA em contrato ativo;
    re-salvar o mesmo plano não recongela. `GET /fazendas/catalogo/planos` (fazendas.py:523) passa a devolver catálogo + overrides; novo `PUT /fazendas/catalogo/precos-plano/{plano}`
    (exigir_dono, preco >= 0, grava quem/quando). NÃO ler `PrecoModulo` para plano.
    Aceite (ida-e-volta, regra do AGENTS.md): PUT preço do plano financeiro 200→230 → GET catálogo mostra 230 → contrato JÁ aprovado continua `preco_mensal` 200 em GET contrato,
    em `asaas._valor_mensal`, em `cobranca._valor_mensal` e no MRR; contrato novo aprovado depois congela 230. Teste de migração: `alembic upgrade head` em SQLite vazio e em banco já na f6a7.
1.4 Contrato visível ao cliente: `_fazenda_publica` (auth.py) ganha `contrato_status` ("ativo"|"aguardando_aprovacao"|"suspenso"|null) além de `modulos_contratados`.
    Aceite (ida-e-volta): PUT/aprovar/suspender → `/auth/me` e `/auth/login` refletem o status e os módulos.
1.5 Gate genérico `exigir_algum_modulo_contratado(*modulos)` (auth.py, ao lado de exigir_modulo_contratado, mesmo bypass de suporte). Aplicar a `/indicadores` (main.py:1001) =
    algum de {rebanho, reprodutivo, produtivo}. Inventariar e anotar (sem alterar nesta fase) alertas_indicador, nao_conformidades, exportacoes_relatorio, assistente, portal, notificacoes.
    Aceite: matriz: fazenda [financeiro,pedidos] → /indicadores/ = 403 com texto "módulo não contratado"; Standard/Gold/#1 inalterados (golden da 0.3).
1.6 Agenda: em `MODULO_TECNICO_PARA_COMERCIAL` (agenda.py:103) incluir "reproducao":"reprodutivo" e "rebanho":"rebanho"; `tem_reproducao` (agenda.py:1736) passa a usar `modulos`
    (filtrado por contrato); atualizar o comentário falso (agenda.py:99-102, 1733-1735). Nova chave ADITIVA `contas_a_receber` (receitas em aberto vencidas e a vencer na janela `dias`,
    só com módulo financeiro; NÃO misturar com `contas_a_pagar`). Vencidas: janela maior (P11).
    Aceite: fazenda [financeiro,pedidos]: /agenda/ sem candidatas IATF/BST/estoque, com `contas_a_pagar` e `contas_a_receber`; fazenda Standard: igual ao golden.
1.7 Estoque — ponto único: em `estoque_baixa.movimentar` e `abrir_lote`, se `fazenda_id` não é None e `not fazenda_tem_modulo_contratado(session, fazenda_id, "estoque")` → retorna sem gravar
    e SEM aviso (`[]`/`(None, [])`). Cobre pedidos.py:491-503 e financeiro.py:4420-4475, 5152-5163, 5250-5265. Verificar (e travar, se existir) a criação de Estoque via
    Configurações > Cadastro (router `cadastro`, main.py:1042, hoje só contrato ativo).
    Aceite: com [financeiro,pedidos], (a) marcar entrega de item produto em Pedido grava `quantidade_entregue`, status calculado, ZERO linhas em `movimento_estoque`/`estoque`;
    (b) lançar nota de despesa com item produto salva e devolve `avisos_estoque == []`; (c) com Gold, mesmo teste gera movimento (sem regressão).
1.8 Preparar financeiro (idempotente, acionado por botão do dono, NÃO automático): `POST /fazendas/{id}/financeiro/preparar` (exigir_dono) → (i) carrega "plano de contas padrão rural-leiteiro"
    se a fazenda não tem plano (arquivo `fazenda/rules/plano_padrao_rural.py`, ver P6; conta de receita do leite com `rmca_receita_leite=True`; `linha_dre`/`natureza_fin` coerentes com rules/dre.py),
    (ii) liga `financeiro_regras_v2` SOMENTE se a fazenda não tem nenhum lançamento (P5), (iii) garante `garantir_contas_do_sistema` (plano_padrao.py), (iv) devolve o que fez.
    Aceite: 2 chamadas seguidas = mesmo resultado (idempotente); com lançamentos existentes NÃO liga a flag; DRE do mês de teste sem "não classificados" para as contas semeadas.
1.9 Onboarding por contrato: `PASSOS_ONBOARDING` (onboarding.py:20-23) vira função dos módulos contratados; para financeiro: "Cadastre suas contas bancárias", "Carregue o plano de contas",
    "Lance a primeira conta a pagar", "Convide seu contador", "Confira a Agenda". Aceite: GET /onboarding de fazenda [financeiro,pedidos] não cita lote/rebanho; de fazenda com rebanho = igual hoje.

### F2 — Frontend
2.1 `frontend/lib/modulos.ts` (PURO, sem localStorage) + `modulos.test.ts` (padrão `node --test`): tabela única rota→módulos (qualquer-de), `visivel(rota, ctx)`, `temCapaUtil(ctx)`,
    `rotaInicial(ctx)` (ordem: "/" se há rebanho/reprodutivo/produtivo; senão primeira permitida de /agenda, /financeiro, /cotacoes, /pedidos; último recurso /portal — NUNCA uma rota
    que o próprio usuário não abre), `relatoriosVisiveis(ctx)`. `ctx = {papel, permissoes, modulosContratados|null, contratoStatus, suporte}`. `podeModulo`/`moduloContratadoPelaFazenda` (api.ts:215-231)
    passam a delegar ao módulo; ROTA_MODULO e MODULO_CONTRATO viram derivados dessa tabela (um só lugar). Aceite: testes cobrem [financeiro,pedidos], Standard, Gold, null (sem dado = não restringe), operador sem permissão, contrato suspenso.
2.2 Contrato fresco: AuthShell e Sidebar leem `/auth/me` ao montar e no `visibilitychange` (máx. 1×/5 min), regravam `fazenda_atual` e disparam evento; Sidebar reavalia no evento.
    Aceite: mudar módulos no Painel CowData → em ≤5 min (ou ao reabrir a aba) o menu do cliente muda sem novo login.
2.3 Contrato aguardando/suspenso: tela sem menu ("Seu acesso está em análise" / "Acesso suspenso — fale com a CowData"), tom neutro, sem culpar; sessão de suporte e dono passam.
2.4 Sidebar: estado inicial VAZIO/esqueleto (sem flash do menu completo); itens vêm de `modulos.ts`; "Capa", "Lançamentos", "Central de Protocolos", "Insights" somem quando não se aplicam;
    rótulo de grupo omitido se o grupo tem 1 item; remover "v1.0.0 · Sprint 1" e mostrar `(ID: n)` só para dono/equipe CowData/suporte; a11y: `role="dialog" aria-modal` só quando o drawer mobile está
    aberto, `aria-current="page"` no ativo, drawer fechado com `inert`, fonte ≥12px e alvo ≥44px no mobile; tooltips curtos e sem citar módulos não contratados.
    Aceite (DOM/teste de lógica): com [financeiro,pedidos] o menu = Agenda, Controle Financeiro, Cotações, Pedidos (+ atalho Administração; sem Insights).
2.5 Página inicial: `app/page.tsx` Home — logado e `!temCapaUtil` → `router.replace(rotaInicial())` (anônimo continua vendo a landing); `AuthShell.tsx:98` (`destinoRaiz`), `login/page.tsx:134`
    e o `next` padrão de `EscolherConta` usam `rotaInicial()`. Guarda anti-laço: se destino === path atual, não redireciona. Aceite: login de usuário [financeiro,pedidos] cai em /agenda; acessar "/" cai em /agenda;
    acessar /rebanho (URL direta) cai em /agenda, sem laço; operador sem permissão de agenda cai em /financeiro ou /portal.
2.6 Agenda: Painel mostra só grupos cujos módulos existem (esconde Reprodução/Sanidade/Alertas de estoque); novo cartão "A receber" (separado de "Contas a pagar"); evento manual: categorias só
    Gestão/Financeiro + Atividades, sem vínculo animal/lote quando não há rebanho; `fetchAnimais`/`fetchEstoqueAtivos` (agenda/page.tsx:502-505) só se contratados; legenda (l.102) idem.
    Aceite: abrir /agenda com [financeiro,pedidos] não dispara GET /animais/ nem /estoque/ (verificar no log do servidor de teste ou mock) e não mostra cartões de rebanho.
2.7 Financeiro: `relatoriosVisiveis(ctx)` filtra GRUPOS_RELATORIOS (Registros sem rebanho; Plano sem planejamento; visões lote/ha/safra de "Custos do leite" sem fonte); relatório sem fonte mostra
    "fonte não contratada" (nunca R$ 0); `modoProduto` padrão = "livre" sem estoque e esconde "Novo produto (estoque)"; empty state: "Lance sua primeira conta" + atalho "Carregar plano de contas"
    (sem "CSV do Ideagri", sem "Postgres/Railway"); mensagens de erro de cliente. Aceite: nenhum item do menu do Financeiro leva a 403; abrir cada relatório visível devolve 200.
2.8 Pedidos/Cotações: sem estoque → EstoquePicker vira campo de texto livre com sugestões de histórico; textos "reflete em Estoque" omitidos; `MarcarEntregaItem` com rótulo "Recebido" e sem pré-visualização de saldo.
    Aceite: criar pedido com item produto, marcar recebimento, vincular nota, tudo sem 403.
2.9 Painel do Contador: isolar `fetchRelatorioCompraVendaAnimais` (contador/page.tsx:178-181) com `.catch(() => [])` e esconder a seção sem rebanho. Aceite: /contador renderiza lançamentos/DRE/folha com [financeiro,pedidos].
2.10 Painel CowData > Fazendas (web FazendasAdmin.tsx + mobile FazendasMobile.tsx — MESMA mudança nos dois): lista de planos vinda do catálogo (não hard-coded; tipo `PlanoNome` ampliado), plano "Financeiro";
    remover Rebanho forçado (web 131/189/533; mobile 139/186/530); marcar/desmarcar módulo aplica dependências com explicação ("Estoque exige Rebanho e Financeiro — marcamos para você");
    cartão "Preços dos planos" (editar R$ por plano, mostra "alterado por X em Y", aviso "não muda contratos já fechados"); no contrato mostra "Preço fechado R$ X · catálogo hoje R$ Y";
    ao remover módulo: diálogo "o que deixa de aparecer; os dados ficam guardados" + confirmação; botão "Preparar financeiro" (1.8). Aceite: criar fazenda → plano Financeiro → aprovar → entrar com usuário da fazenda mostra o menu esperado (2.4).
2.11 Mobile `/app`: decisão P8. Padrão do v2: fazenda sem rebanho NÃO é enviada a `/app` (Home/AuthShell/login usam `rotaInicial()`); o site já é responsivo. Aceite: PWA de fazenda [financeiro,pedidos] abre em /agenda.

### F3 — Testes (obrigatórios; rodar a suíte inteira do backend ao final, não só os novos)
Backend: matriz de módulos (0.3 + fazenda [financeiro,pedidos] + [rebanho,financeiro] + [rebanho,reprodutivo]); dependências; preço (ida-e-volta 1.3, migração SQLite vazia); `contrato_status` em /auth/me; Agenda filtrada
(`test_agenda_permissoes.py` estendido) incl. contas_a_receber; estoque ponto único (3 cenários: a, b, c de 1.7); Painel do Contador (GET dos endpoints que ele chama devolve 200 sem rebanho, exceto compra-venda que é 403 e tratado no front);
`preparar financeiro` idempotente. Frontend: `lib/modulos.test.ts`; `npm test`; `npx tsc --noEmit`; `npm run lint` nos arquivos tocados; `next build` (se a RAM permitir).
Navegador local (se F0.2 permitir subir o app): script Python/Playwright no molde de `frontend/e2e/janela_travada.py` — login em fazenda [financeiro,pedidos], capturas 1440 px e 390 px de /agenda, /financeiro, /pedidos, /cotacoes, /contador; asserts: menu esperado, sem laço, sem scroll horizontal, nenhum 403 inesperado no log. Chromium em /opt/pw-browsers (não rodar `playwright install`).
Se não subir: declarar "não verificado em navegador" na nota — não inventar.

### F4 — Documentação e memória (no mesmo PR de cada mudança de arquitetura, conforme AGENTS.md)
README.md (tabela de planos/módulos, nova rota de preço, regra de dependências) e CONTEXTO_PROJETO_FAZENDA.md se aplicável; `docs/` nota curta do plano Financeiro; nota de sessão datada
`04_CowData/Milk/Sessoes/2026-10-13_plano-financeiro.md` e ADR `ADR_plano-financeiro-modulos-e-preco.md` (dependências, preço congelado, ponto único de estoque, regras v2 desde o dia 1).
Cofre: sem conector confirmado nesta sessão → ENTREGAR O TEXTO ao Jairo; só dizer "gravada" se o conector confirmar o arquivo. Regra generalizável a registrar: "visibilidade por contrato nasce
de UMA tabela (lib/modulos.ts) + gates de rota no backend; módulo não contratado não grava dado por efeito colateral". Sem CPF/valores reais no cofre.

### F5 — Produção (ETAPA HUMANA, fora da execução autônoma)
Só depois de F0-F4 verdes e PR revisado/mesclado pelo Jairo: citar SHA, `git diff --stat` do PR, deploy SUCCESS no Railway (backend) e Vercel (front) — migração roda no boot (database.py:507): conferir log de boot.
Criar a fazenda `eh_teste` com plano Financeiro, usuário admin + operador + vínculo contador; clicar "Preparar financeiro"; percorrer o roteiro de aceite em produção. Nada disso é feito pela execução noturna.

## 6. Ordem de execução SEGURA para uma só madrugada (autônoma, sem produção)
Regras gerais: branch claude/farm-app-access-bikeej; um commit por passo; mensagem de commit termina com as linhas de atribuição do sistema; parar e relatar (não improvisar) nas condições de parada.
0. (10 min) Ler os 6 documentos; criar venv fora do repo; instalar dependências; rodar baseline (F0.1). Parar se o baseline tiver >5% de falhas não relacionadas — registrar e seguir só com testes alvo.
1. (30 min) F0.2 migração f6a7 no lugar + testes de migração. Parar se `alembic upgrade head` em SQLite vazio falhar por OUTRA migração (não é escopo; registrar).
2. (20 min) F0.3 matriz golden (só testes; nenhum código de produção muda).
3. (60 min) F1.1+F1.2 (planos, dependências, plano financeiro) + testes; commit.
4. (75 min) F1.3 preço (migração nova, função única, 3 substituições, endpoint) + teste ida-e-volta e migração; commit. Condição de parada: qualquer diferença no valor cobrado de contrato existente no teste golden.
5. (25 min) F1.4 `contrato_status`; F1.5 gate `/indicadores`; commit.
6. (40 min) F1.6 Agenda (filtro + `contas_a_receber`); testes; commit.
7. (30 min) F1.7 ponto único de estoque; 3 cenários; commit. Parar se algum teste existente de estoque/pedido/financeiro regredir: reverter este passo e relatar.
8. (60 min) F1.8 + F1.9 (preparar financeiro, plano padrão, onboarding por contrato); commit. O plano padrão é RASCUNHO: rotular "validar com o contador" no código e na nota.
9. (45 min) F2.1 `lib/modulos.ts` + testes; refatorar `podeModulo`; commit. `npm test` e `tsc` verdes.
10. (40 min) F2.2+F2.3 (contrato fresco, tela de contrato inativo); F2.9 (Painel do Contador); commit.
11. (60 min) F2.4+F2.5 (Sidebar, Home, login, anti-laço); commit. Ler docs do Next antes (use-router/redirect).
12. (75 min) F2.6 Agenda, F2.7 Financeiro, F2.8 Pedidos/Cotações; commits separados.
13. (60 min) F2.10 Painel CowData web+mobile; commit.
14. (45 min) F3 navegador local (se der), suíte completa do backend, `next build`; corrigir só regressões causadas por este trabalho.
15. (30 min) F4: README/CONTEXTO, nota de sessão e ADR (texto entregue ao Jairo se não houver conector).
16. Fim: um único PR (ou série) com descrição objetiva: o que mudou, o que ficou de fora, armadilhas, "não verificado". Sem push para main; sem produção.
Não fazer, em hipótese alguma: editar/copiar CSV/XLSM da raiz; escrever em Hermes/hermes_para_claude/06_Publicacao; gravar segredos; mexer em Railway/Vercel/Neon/Supabase; ligar `financeiro_regras_v2` em fazenda existente;
revogar/alterar preço de qualquer contrato existente.

## 7. Decisões que ainda dependem do Jairo (com recomendação do revisor)
P1  Quando o preço "fecha"? Recomendo: na APROVAÇÃO do contrato; trocar de plano recongela; reajuste futuro só por aditivo (aviso prévio em contrato-modelo).
P2  Backfill: congelar os contratos Standard/Silver/Gold/Diamond ativos pelo preço de hoje? Recomendo SIM (não muda valor, protege de reajuste acidental).
P3  Upgrade para Estoque depois: sem retroativo, com inventário inicial datado (recomendado) × reprocessar compras de produto do período (mais complexo; exige marca nos itens de nota).
P4  Downgrade: dados preservados e ocultos (recomendado); quem pode (só dono); exige exportação antes? E retenção mínima (5 anos?) no contrato.
P5  Regras v2 ligadas desde o dia 1 só em fazenda SEM lançamentos? Recomendo SIM; validar com o contador externo.
P6  Plano de contas padrão: (a) usar o plano da fazenda do Jairo como molde (dados reais — exige autorização expressa; AGENTS.md proíbe copiar os arquivos) ou (b) rascunho genérico nosso para o contador revisar. Recomendo (b) agora.
P7  Centro de custo "Agricultura" em fazenda sem agricultura: manter, inativar por padrão ou não criar? Recomendo inativar por padrão.
P8  Mobile `/app` para fazenda só-financeiro: usar o site responsivo (recomendado) ou criar menu financeiro no app de campo (escopo futuro).
P9  Dependências finais: confirmar tabela da 1.1 (pedidos⇒financeiro, planejamento⇒financeiro, produtivo/reprodutivo/sanitario/alimentacao⇒rebanho, estoque⇒rebanho+financeiro); agricultura⇒financeiro?
P10 "A receber" na Agenda: card separado, só vencidas + janela de 10 dias (recomendado) — é a leitura que o v2 faz de D3.
P11 Janela de contas VENCIDAS na Agenda: hoje 30 dias (agenda_engine.py:74). Contador pede sem limite (ou 180). Mudar para todos os planos ou só para Financeiro?
P12 Texto comercial/contratual do plano: "gerencial + apoio ao contador (LCDPR Q100/Q200 em CSV); não emite NF; não envia eSocial". Aprovar a redação.
P13 Limites do plano (usuários, lançamentos/mês, nº de contadores, retenção): hoje não há. Deixar ilimitado?
P14 "Financeiro (básico)" (NOME_MODULO em FazendasAdmin.tsx:21): renomear para evitar conflito com o plano "Financeiro".
P15 LGPD: aprovar lista de dados tratados e prazo de retenção para o contrato-modelo (contrato_cowdata.md) antes do 1º cliente.
P16 Quem cria a 1ª fazenda real e quando (F5), e quem é o contador de homologação.

## 8. Riscos remanescentes (resumo; detalhe na resposta final)
1. Rotas/telas não inventariadas ainda tocando rebanho/estoque (RELATORIO §e). 2. Migração roda no boot em produção. 3. Plano de contas/regras v2/LCDPR sem validação do contador.
4. Mudança de gating pode alterar fazendas sob medida/fazenda #1 em silêncio (mitigado pela matriz golden). 5. Nada foi executado nesta revisão (sem pytest, sem navegador); cache de contrato no cliente.
