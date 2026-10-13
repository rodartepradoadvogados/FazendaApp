# Relatório bruto — revisão independente do PLANO v1 "Fazenda só-Financeiro" (CowData/Milk)

Revisor: contador de fazendas (pecuária leiteira) + execução da skill `impeccable` (critique e audit).
Base: HEAD c8fc20a, branch claude/farm-app-access-bikeej. Data: 2026-10-13.
Escopo de escrita: somente este scratchpad. Nada foi editado no repositório, nada foi enviado a serviços externos,
nenhum CSV/XLSM real foi lido ou copiado.

## 0. Como a análise foi feita (e o que NÃO foi possível)

- Análise ESTÁTICA do código. O app NÃO foi subido: o sandbox não tem as dependências do backend
  (`python -c "import fastapi"` falha; `pytest` ausente) e a migração `f6a7b8c9d0e1` quebra em SQLite vazio.
  Nenhum screenshot, nenhuma medição de contraste, nenhum teste de navegador. Toda nota de UI abaixo vem de ler JSX/CSS.
- `impeccable context` rodou (PRODUCT.md e DESIGN.md carregados). `impeccable detect --json` rodou em 10 arquivos.
- `frontend/node_modules` existe (Next 16.2.10); docs locais em `node_modules/next/dist/docs/01-app/03-api-reference/04-functions/`
  (`use-router.md`, `redirect.md`) e convenção `proxy` (substitui `middleware`). Não alterei código de rota, então só
  registrei o caminho para o implementador ler antes de editar (regra de `frontend/AGENTS.md`).
- Método do `critique`: ⚠️ DEGRADED: single-context (nenhuma ferramenta de sub-agente exposta nesta sessão; as Assessments
  A e B rodaram em sequência no mesmo contexto — A foi concluída antes de eu olhar a saída do detector). Perguntas
  finais do `critique`: não feitas — o enunciado proíbe pedir algo ao usuário. `Questions skipped: sem interlocutor
  (instrução explícita da tarefa); havia 5 Priority Issues, então em execução normal as perguntas seriam obrigatórias.`
- Snapshot em `.impeccable/critique/` NÃO gravado (somente leitura no repositório). Trend: primeira execução, sem histórico.

---

## (a) Saída resumida — `impeccable critique` (experiência de uma fazenda SÓ-Financeiro, estado ATUAL do código)

Alvos: Sidebar.tsx, AuthShell.tsx, login/page.tsx, app/page.tsx (Capa), agenda/page.tsx, financeiro/page.tsx, cotacoes, pedidos,
FazendasAdmin.tsx, FazendasMobile.tsx. Modo da superfície: Operate (ferramenta de trabalho diário; o contador/dono completa tarefas).

### Veredito de especificidade de design
O sistema visual (DESIGN.md "The Institutional Ledger": cantos de 2px, rótulos em caixa alta, ouro = ação, filete lateral
como estado) é autoral e coerente — não é intercambiável com um SaaS genérico. O problema NÃO é a pele; é que a
ARQUITETURA DE INFORMAÇÃO foi desenhada para o dono de rebanho e o produto "só-Financeiro" herda essa casca inteira.
Deterministic scan (detector): 6 achados, todos `side-tab` (borda lateral grossa): agenda/page.tsx:2381 e app/page.tsx:51, 376, 382, 387, 392.
Falso positivo: DESIGN.md oficializa o filete lateral de 3px (kpi-card, estado de item). Nenhum achado nos demais 8 arquivos.
Overlays no navegador: não gerados (app não sobe).

### Design Health Score (Nielsen) — 21/40 → 52% → "Acceptable" (precisa de trabalho significativo)

| # | Heurística | Nota | Achado principal |
|---|-----------|------|------------------|
| 1 | Visibilidade do estado | 2 | Contrato aguardando/suspenso não aparece em lugar nenhum: o front mostra o menu inteiro e cada tela dá 403 mudo (`.catch(() => {})` em agenda/page.tsx:502-505, pedidos/page.tsx:121-125, cotacoes/page.tsx:139-143). `modulos_contratados` fica em localStorage desde o login (lib/api.ts:415, 461, 1048) e nunca é relido de `/auth/me` — upgrade/downgrade só aparece no próximo login (sessão "manter conectado" = 90 dias). |
| 2 | Linguagem do mundo real | 2 | Grupo "Ciclo diário" para quem só tem Agenda; tooltips da Sidebar citam Estoque (Sidebar.tsx:101); texto de desenvolvedor exposto ao cliente: "o banco de produção não está persistindo — confira o Postgres no Railway" (financeiro/page.tsx ~l.775) e "v1.0.0 · Sprint 1" (Sidebar.tsx:460). |
| 3 | Controle e liberdade | 3 | Esc/duplo-clique/colapsar menu/gaveta travada bem resolvidos. Risco novo: redirect em laço se `rotaInicial` apontar para rota que o usuário não pode abrir (AuthShell.tsx:168 manda para `destinoRaiz`). |
| 4 | Consistência e padrões | 3 | Tokens e categorias consistentes. Fragilidade: a regra "o que a fazenda vê" está duplicada em 3 mapas (ROTA_MODULO, MODULO_CONTRATO, `links` da Sidebar) e na Agenda (backend). |
| 5 | Prevenção de erros | 1 | O Painel CowData deixa montar contrato inválido para o caso novo (rebanho forçado: FazendasAdmin.tsx:131,189,533; Mobile 139,186,530) e não impede combinações sem sentido (pedidos sem financeiro, estoque sem rebanho). O cliente é levado a telas que sabidamente falham (Registros > animais/sêmen, Plano > Orçamento). |
| 6 | Reconhecimento > memória | 2 | Menu mostra itens que a fazenda não comprou (Capa, Lançamentos, Central de Protocolos, Insights). Financeiro tem navegação em até 3 níveis (Relatórios > grupo > relatório) com 8 de 19 itens inúteis para essa fazenda. |
| 7 | Flexibilidade e eficiência | 3 | Duplo-clique abre aba, filtros salvos, busca global por nº de documento/LC, deep links `?ir=`. Bom para o power user (Alex). |
| 8 | Estética e minimalismo | 2 | Capa = 12 KPIs de rebanho; Agenda > Painel = 3 grupos (Reprodução, Sanidade, Estoque e gestão) com cartões zerados; menu com 7 itens dos quais 3 não servem. |
| 9 | Recuperação de erros | 1 | Pickers de produto ficam vazios sem explicação (GET /estoque/ = 403); "Novo produto (estoque)" faz POST /estoque/ = 403; Painel do Contador inteiro falha (P0 abaixo). |
| 10 | Ajuda e documentação | 2 | Checklist "Primeiros passos" só existe na Capa e fala de lote/rebanho (onboarding.py:20-23); ManualFazendaButton só na Capa (app/page.tsx:336). Sem ajuda de contexto para plano de contas, fechamento, conciliação. |
| **Total** | | **21/40** | **Acceptable** |

### O que funciona (preservar)
1. A casca Financeiro é madura e independente de rebanho no núcleo: Resumo, Contas a pagar/receber, baixa em lote, faturas de fornecedor,
   cartão, folha, recorrentes, Fechamento do mês, Conciliação bancária, Pacote do contador (DRE competência/caixa, Livro Caixa, patrimônio,
   apoio LCDPR Q100/Q200 — pacote_contador.py:286-306). É o ativo que justifica vender o plano.
2. Gaveta/Modal "travados" para baixa (DESIGN.md "Janelas"): previnem perda de dado em operação sensível — exatamente o que um contador quer.
3. A Agenda "Dia a dia" já entende Gestão/Financeiro (diárias, empreitada, contas a pagar com "Pagar" inline — agenda/page.tsx:216-233).

### Priority Issues
- **[P0] Painel do Contador quebra inteiro numa fazenda sem Rebanho.** `app/contador/page.tsx:178-181` chama `fetchRelatorioCompraVendaAnimais({})`
  dentro de um `Promise.all`; o router `/relatorio-compra-venda-animais` exige módulo `rebanho` contratado (main.py:1052). Um 403 rejeita o
  `Promise.all` → `setErro` → o contador não vê nada (lançamentos, DRE, folha, patrimônio). Por que importa: o contador é o stakeholder que valida
  o produto. Fix: carregar animais à parte com `.catch(() => [])`, esconder a seção "Compra/Venda de animais" se `rebanho` não está contratado.
  Comando: /impeccable harden.
- **[P1] Casca de navegação não conhece o contrato.** Sidebar (Capa, Lançamentos, Protocolos, Insights visíveis — MODULO_CONTRATO em api.ts:201 não cobre
  capa/lancamentos/indicadores/analise), primeira pintura mostra TODOS os itens (`useState(links)` — Sidebar.tsx:155) antes do efeito filtrar, Home
  sempre "/" (AuthShell.tsx:98, login/page.tsx:134, app/page.tsx:621), Capa de rebanho como destino. Fix: módulo único `lib/modulos.ts` (puro, testável com
  `node --test`), `rotaInicial()`, estado inicial vazio. Comando: /impeccable distill + /impeccable adapt.
- **[P1] Agenda como página inicial está desenhada para rebanho.** Visão "Painel" sempre renderiza grupos Reprodução/Sanidade/Estoque (agenda/page.tsx:2478-2546);
  formulário de evento manual oferece Reprodutivo/Sanidade/Produção + vínculo a animal/lote (l.69, 2901, 2880); ao abrir, dispara `fetchAnimais()` e
  `fetchEstoqueAtivos()` (l.502-505) = 2 chamadas garantidamente 403. A Agenda só mostra CONTAS A PAGAR (backend filtra `tipo == "despesa"`, agenda.py:~575-595;
  vencidas só até 30 dias, agenda_engine.py:74) — "a receber" NÃO existe, ao contrário do que o v1 (D3) afirma. Comando: /impeccable distill.
- **[P1] Financeiro, Pedidos e Cotações dependem do cadastro de Estoque para o seletor de produtos.** GET `/estoque/` (lib/api.ts:5498) é a fonte do
  EstoquePicker (FormFinanceiro.tsx:194, pedidos/page.tsx:121, cotacoes/page.tsx:139) e é gated por `estoque` (main.py:1030). Sem o módulo: picker vazio,
  "Novo produto" falha, `modoProduto` nasce "estoque" (FormFinanceiro.tsx:88). Há saída boa já pronta (modo "livre", l.67-90) — mas não é o padrão.
  Comando: /impeccable clarify + harden.
- **[P2] Tela de contratação (Painel CowData > Fazendas, web e mobile).** Planos hard-coded `["standard","silver","gold","diamond"]`
  (FazendasAdmin.tsx:490; Mobile:499; tipo `PlanoNome` api.ts:561), preço de plano somente leitura (FazendasAdmin.tsx:503 mostra `catalogo[p].preco`),
  Rebanho checkbox `disabled` e pré-marcado, nenhuma explicação de dependências, nenhum aviso de "o que some" ao tirar módulo, nenhum campo "preço fechado × catálogo".
  Comando: /impeccable shape + clarify.

### Persona red flags
- **Alex (power user / dono-gestor):** Capa ainda é o destino de "/" e do bounce de permissão; precisa clicar Agenda a cada abertura. O "Insights"
  abre /indicadores (KPIs de rebanho) em aba nova — vazio e sem explicação.
- **Sam (acessibilidade):** `<aside role="dialog" aria-modal="true">` é aplicado também no desktop (Sidebar.tsx:297), onde a barra é fixa — leitor de tela
  trata o resto da página como inerte. Links ativos só por cor/borda (sem `aria-current`). Fonte de 10px nos itens (Sidebar.tsx:58).
- **Jordan (primeira vez — o contador novo ou o gerente administrativo):** cai na Capa com checklist "Cadastre seu primeiro lote"; abre Financeiro e vê
  "Suba o CONTA_GERENCIAL.csv" (cliente que nunca usou Ideagri); abre Plano > Orçamento e leva 403.
- **Casey (mobile, no escritório/na cidade):** PWA instalado abre "/" → `ehAppDeCampo()` manda para `/app` (casca de curral, sem filtro de módulo:
  app/app/page.tsx não usa `podeModulo`); `Insights/Administração` abrem em nova aba.

### Observações menores
Rótulo "Financeiro (básico)" para o módulo (FazendasAdmin.tsx:21) contradiz o nome do novo plano "Financeiro"; `ID: n` da fazenda na Sidebar para o cliente;
"Trocar de conta" aparece até para quem tem uma conta só; tooltips muito longos (Sidebar l.89, 92, 93).

### Perguntas para considerar
Qual é a primeira coisa que o dono financeiro precisa ver às 7h — o que vence hoje ou a agenda de atividades? E se a página inicial fosse "o que vence
e o que atrasou", com atividades abaixo? O contador precisa mesmo entrar pelo Painel do Contador ou pode abrir o Financeiro em modo leitura?

---

## (b) Saída resumida — `impeccable audit` (aspectos técnicos, mesmos alvos; análise de código, sem navegador)

### Implementation Integrity Verdict: PASS com ressalvas
Sistema coerente e específico do produto (tokens `var(--…)`, categorias fixas, janelas padronizadas). Ressalva: a REGRA DE VISIBILIDADE POR CONTRATO
está implementada em quatro lugares divergentes (ROTA_MODULO, MODULO_CONTRATO, `links`, e no backend `MODULO_TECNICO_PARA_COMERCIAL`) e já divergiu
(reproducao/rebanho/capa/lancamentos ficam de fora "de propósito" — comentário api.ts:197-200 — o que é exatamente o furo do produto novo).

### Audit Health Score — 11/20 → "Acceptable"

| # | Dimensão | Nota | Achado principal |
|---|----------|------|------------------|
| 1 | Acessibilidade | 2 | `role="dialog" aria-modal` permanente na aside (Sidebar.tsx:297); sem `aria-current`; drawer fechado continua focável (só `-translate-x-full`, sem `inert`/`visibility`); mensagens de erro do login e do FazendasAdmin sem `role="alert"`/`aria-live` (login/page.tsx:48,84; 0 ocorrências em FazendasAdmin/Mobile/Cotações/Pedidos); itens de menu em 10px. Pontos fortes: labels com `htmlFor` no login, anel de foco duplo, `prefers-reduced-motion` tratado (globals.css:785, 804, 896, 913), focus-trap do drawer. |
| 2 | Performance | 2 | Páginas-monólito de cliente: agenda 3.005 linhas, financeiro 4.714, `lib/api.ts` 10.515 (módulo único importado por toda a app); Recharts importado estaticamente em financeiro. Agenda faz 2 requisições fadadas a 403 em fazenda sem rebanho/estoque (l.502-505). Sidebar faz ping de saúde a cada 30 s (ok). Não medi bundle. |
| 3 | Responsivo | 2 | Itens da Sidebar ≈ 28 px de altura (py-1.5 + 10px de fonte; estimativa por classes, não medido) < 44 px; Agenda tem `min-height:44px` dedicado (globals.css:1666-1799), a Sidebar não. ~41 ocorrências de `fontSize` < 0,7rem na Agenda, 11 no Financeiro. Cartões do Painel CowData com `minWidth:360px` ok em 390 px. |
| 4 | Theming | 3 | Quase tudo via `var(--…)`; hex residuais: financeiro 5, agenda 2, FazendasAdmin 2. Dark/paletas: não verificado visualmente. |
| 5 | Integridade de implementação | 2 | Regra de módulos duplicada (acima); contrato cacheado no cliente; texto de desenvolvedor em tela de cliente; 6 `side-tab` do detector = falsos positivos (DESIGN.md). |
| **Total** | | **11/20** | **Acceptable** |

### Resumo executivo
Issues: P0 ×1, P1 ×6, P2 ×6, P3 ×2. Top 5: (1) Painel do Contador falha sem Rebanho; (2) navegação ignora contrato (Capa/Lançamentos/Protocolos/Insights);
(3) contrato cacheado no localStorage nunca atualizado e sem estado "aguardando/suspenso"; (4) dependência de /estoque/ em Financeiro/Pedidos/Cotações;
(5) Agenda/Painel e formulário manual de rebanho para quem não tem rebanho.

### Achados por severidade
- **[P0] Painel do Contador** — app/contador/page.tsx:178-181 (ver critique). Categoria: Integridade. WCAG: n/a. Recomendação: isolar a chamada. /impeccable harden.
- **[P1] Sidebar não filtra Capa/Lançamentos/Protocolos/Insights; flash do menu completo** — Sidebar.tsx:84-102, 155, 178-195; api.ts:185-204. Integridade/Responsivo. /impeccable distill.
- **[P1] Cache de contrato obsoleto e contrato inativo invisível** — api.ts:415,461,1048; auth.py `_fazenda_publica` (≈l.282-293) não envia `contrato.status`. Integridade. /impeccable harden.
- **[P1] `role="dialog" aria-modal="true"` permanente + sem `aria-current` + drawer fechado focável** — Sidebar.tsx:297, 50-70, 298. A11y. WCAG 4.1.2, 2.4.3, 1.3.1. /impeccable adapt.
- **[P1] Agenda: requisições 403 garantidas e Painel com cartões de rebanho** — agenda/page.tsx:502-505, 2478-2546. Performance/Integridade. /impeccable optimize + distill.
- **[P1] Copy de desenvolvedor para cliente** — financeiro/page.tsx ~775 ("Postgres no Railway", "Importe os la…"), Sidebar.tsx:460. Integridade. /impeccable clarify.
- **[P1] Pickers de produto vazios, "Novo produto" falha** — EstoquePicker + NovoItemEstoque (financeiro, pedidos, cotações). Integridade. /impeccable harden.
- **[P2] Touch targets da Sidebar < 44 px; fonte 10px** — Sidebar.tsx:53-62. Responsivo/A11y (WCAG 2.5.8 AA = 24 px mínimo, alvo 44 px é a meta do próprio DESIGN.md). /impeccable adapt.
- **[P2] Erros sem `role="alert"`** — login/page.tsx:48,84; FazendasAdmin msg/erro. WCAG 4.1.3. /impeccable harden.
- **[P2] Planos hard-coded no seletor de contratação** — FazendasAdmin.tsx:490; Mobile:499. Integridade. /impeccable shape.
- **[P2] Relatórios do Financeiro sem filtro por módulo** — relatoriosNavegacao.ts:GRUPOS_RELATORIOS (Plano → /planejamento, gated por `planejamento`, main.py:977; Registros → rebanho). Integridade. /impeccable distill.
- **[P2] Onboarding não depende de contrato** — onboarding.py:20-23. Integridade. /impeccable onboard.
- **[P2] Contraste/dark mode do que for novo: não verificável sem navegador.**
- **[P3] Hex residuais; 6 detecções `side-tab` (falsos positivos); `FazendaId` visível ao cliente.**

### Padrões sistêmicos
(1) "Decisão de visibilidade tomada em cada arquivo" em vez de uma tabela única. (2) Chamadas de dados disparadas no mount sem checar contrato, engolidas por
`.catch(() => {})` — escondem falhas reais. (3) Textos escritos para o dono-desenvolvedor, não para o cliente.

### Positivos
Foco visível e `prefers-reduced-motion` tratados; janelas travadas e Esc aninhado; tokens e categorias; Agenda com alvos 44 px; testes de lógica pura em `lib/*.test.ts`
(padrão a seguir para `lib/modulos.ts`).

### Ações recomendadas (ordem)
1. [P0] /impeccable harden — Painel do Contador isolado de rebanho.
2. [P1] /impeccable distill — Sidebar/Home/Agenda/Financeiro guiados por tabela única de módulos.
3. [P1] /impeccable harden — contrato fresco (`/auth/me`) + tela de contrato aguardando/suspenso.
4. [P1] /impeccable adapt — a11y do menu (dialog só quando drawer, aria-current, inert, alvos 44 px).
5. [P1] /impeccable clarify — copy de cliente (vazios, erros, tooltips).
6. [P2] /impeccable onboard — checklist por contrato.
7. /impeccable polish ao final.

---

## (c) Críticas do contador ao plano (sob olhar de contador rural, 15+ anos)

Resumo: o plano v1 acerta a prioridade (Financeiro vendável sozinho) mas trata como "esconder telas" o que é, para um contador, um problema de
**integridade de registro**. Os pontos abaixo estão em ordem de gravidade para quem vai assinar números.

1. **Pedidos/Compras sem estoque: o que acontece com o item de produto entregue?** Hoje, marcar entrega de item `tipo_item == "produto"` dá entrada
   em Estoque (pedidos.py:491-503) e lançar nota de despesa com produto também (financeiro.py:4420-4475; ajuste na edição 5152-5163; 5250-5265).
   O v1 só tratou o Pedido. A forma segura é UM ponto de controle em `estoque_baixa.movimentar/abrir_lote`: sem módulo `estoque` contratado → não
   escreve nada. Sem isso há dois riscos contábeis: (i) com item cadastrado, estoque-fantasma de uma fazenda que não o contrata (e que depois,
   num upgrade, aparece como saldo "verdadeiro"); (ii) sem item cadastrado, cada compra devolve o aviso "não está no estoque desta fazenda — lançamento
   registrado sem baixa" (estoque_baixa.py:410-411), ruído que ensina o usuário a ignorar avisos.
   Do ponto de vista contábil o gasto continua correto (despesa pela nota, pelo regime de competência/caixa); o que se perde é só o controle físico.
   Exigências: (a) nada de saldo/valor de estoque em relatório quando o módulo não existe (nem "R$ 0,00" — mostrar "não contratado"); (b) manter a
   marcação de **recebimento** do item no Pedido (`quantidade_entregue`), que dá o par "recebido × faturado" — controle de corte (cut-off) que o
   contador usa para saber o que está em trânsito/sem nota (`_pendencias_fechamento_pedido`, pedidos.py:415-434 já lista "pagamento" e "data_emissao" faltantes).
2. **Plano de contas: a fazenda nova nasce SEM plano de contas.** `provisionar_fazenda_nova` (fazendas.py:60-100) cria contas correntes e centros de custo,
   mas o plano gerencial "vem do CSV do Ideagri" (rules/plano_padrao.py:5-9). Um cliente só-financeiro, sem Ideagri, não consegue classificar a primeira
   despesa. Pior: o aviso da tela é "Suba o CONTA_GERENCIAL.csv". Isso é bloqueio de venda, não de UX. Falta um plano padrão rural-leiteiro
   (receitas: leite, animais, outras; despesas: alimentação, sanidade, pessoal, energia/combustível, manutenção, impostos/taxas, financeiras;
   investimentos) já com `linha_dre` e `natureza_fin` herdadas por prefixo (rules/dre.py:107-135). Precisa ser validado pelo contador externo.
3. **Regras v2 desligadas por padrão.** `financeiro_regras_v2` é "padrão desligado" por fazenda (docs/financeiro-regras-v2.md §1; parametros.py:420-445).
   Desligada, DRE/Livro Caixa/custos usam a lógica antiga (empréstimo/principal e compra de bem podem entrar na DRE; litros de leite vêm do campo cru,
   não da nota do laticínio), e o item "Apoio ao LCDPR" do pacote do contador fica `ok: False` (pacote_contador.py:306). Para fazenda NOVA, sem histórico a
   proteger, deveria nascer LIGADA — a regra "rodar script de impacto num dump" só faz sentido para quem já tem dados. É decisão do Jairo + contador.
4. **Relatórios que dependem de Rebanho/Estoque e ficarão vazios ou quebrados.** Ver tabela §(d)-6. Em suma: "Custo por vaca/lote", "Compra/Venda de
   animais", "Compra de sêmen", "Réguas de referência" (a confirmar), RMCA físico, Orçamento/Cenários (módulo `planejamento`, que o plano Financeiro
   [financeiro, pedidos] NÃO contém → 403, hoje também para Silver). "Custo por hectare/safra" estão gated só por `financeiro` (main.py:957,963) mas
   dependem de área/safra (`agricultura`). Regra: relatório cuja fonte não existe não mostra zero — mostra "fonte não contratada" (zero é informação contábil falsa).
5. **Litros de leite → resultado por litro.** Com regras v2 ligadas, litros vêm da NOTA do laticínio (item de leite reconhecido por conta com
   `rmca_receita_leite` OU por item de Estoque marcado `produto_leite`, litros_leite_nota.py:1-20); a reserva é a "Venda mensal do leite"
   (`EntregaLeiteMensal`), cujo cadastro está em `/producao/entrega-leite` (api.ts:6677), router do módulo `produtivo`. Numa fazenda só-financeiro:
   o caminho "conta com rmca_receita_leite" funciona, o caminho "item de Estoque produto_leite" não (sem módulo estoque), e a reserva é inalcançável.
   Consequência prática: o plano padrão (item 2) PRECISA marcar a conta de receita do leite com `rmca_receita_leite`, senão "Resultado por litro" sai sem litros.
6. **Painel do Contador (/contador).** Quebra por completo sem Rebanho (P0). Fora isso é o melhor argumento de venda: Pacote do contador (PDF+ZIP, CSV, Excel),
   Fechamento do mês com trilha append-only (fechamento_conciliacao.py:131-185), Conciliação OFX/CSV, depreciação do patrimônio. O vínculo `contador` não tem gate
   de plano (fazendas.py:145-149) e é só leitura (auth.py `bloquear_escrita_contador`, com cadeado de senha para lançamentos extraordinários). Exigir um teste
   de ponta a ponta "contador abre /contador numa fazenda [financeiro, pedidos]".
7. **Centros de custo semeados.** "Pecuária Leiteira" e "Agricultura" (fazendas.py:74-75; main.py seed_centro_custo_agricultura) nascem em toda fazenda. Para
   uma fazenda sem módulo `agricultura`, "Agricultura" é ruído e convida a lançar custo de safra que nenhum relatório contratado consumirá. Manter "Pecuária Leiteira"
   (é a atividade rural principal do LCDPR), tornar "Agricultura" opcional/inativa por padrão (decisão do Jairo).
8. **Preço congelado × preço vivo.** O texto do model promete congelamento ("editar o catálogo ou o preço do pacote depois não muda contratos já fechados",
   planos.py ~l.107-110), mas o código lê o preço do pacote AO VIVO em ao menos quatro lugares: fazendas.py:389-391 (MRR/contrato), asaas.py:37-39 e cobranca.py:30-32
   (VALOR COBRADO do cliente). Hoje isso não aparece porque o preço do catálogo é uma constante em código. No instante em que o preço do plano virar editável (D2),
   editar R$200→R$230 reajustaria silenciosamente a cobrança de quem já assinou. Para o contador (e para o jurídico do escritório) isso é inaceitável:
   preço contratado é fato do contrato. Exigir: coluna `preco_mensal_fechado` no contrato, função única de preço, backfill dos contratos atuais pelo valor de hoje.
9. **Upgrade/downgrade de módulos e dados já lançados.** O modelo hoje é "linha `ativo=False`" (fazendas.py:466-472): dados permanecem, acesso some (403) — correto
   (retenção de registros por 5 anos+). Lacunas: (i) nada valida dependências ao tirar `rebanho` com `reprodutivo` ativo etc.; (ii) um downgrade deixa números
   cruzados (custo/vaca) sem fonte; (iii) um upgrade para `estoque` NÃO traz as compras de produto feitas antes (nenhuma entrada foi gravada — com o choke point) →
   exige inventário inicial em data de corte (o código já pede: "registre o estoque inicial", estoque_baixa.py:416-420); (iv) o front só percebe a mudança no
   próximo login (cache). Regra de ouro contábil: nada é apagado nem reescrito por mudança de plano; a contagem inicial é um lançamento datado e assinado.
10. **Dependência entre módulos (D1).** Concordo com "estoque ⇒ rebanho + financeiro". Acrescentar: `pedidos ⇒ financeiro` (Pedido sem Financeiro perde o par
    pedido×nota), `planejamento ⇒ financeiro`, `produtivo/reprodutivo/sanitario/alimentacao ⇒ rebanho`. Validar na API (400 com texto claro) e na tela. Fazenda #1 e contratos
    existentes são "grandfathered" (checar só ao SALVAR, nunca bloquear leitura).
11. **O que o v1 não diz sobre fiscal/trabalhista.** O módulo é gerencial + apoio: o pacote traz "Apoio ao LCDPR (Q100 e Q200)" em CSV — não é o arquivo oficial da Receita;
    a folha tem INSS/IRRF/FGTS/13º/férias (folha_rh.py) mas "integração com eSocial (envio) está fora" (folha_rh.py:3-5); não há emissão de NF-e/NFP-e. O texto comercial do plano
    "Financeiro" deve dizer isso (evita promessa fiscal que o produto não cumpre) — decisão do Jairo.
12. **LGPD.** Financeiro guarda CPF/CNPJ de fornecedores/pessoas, folha de diaristas e anexos de contrato/NF. O contador externo entra por vínculo `contador` (leitura) com log
    de exportação (`ExportacaoRelatorioLog`). Pedir: lista de dados pessoais tratados + base legal + prazo de retenção no contrato-modelo (contrato_cowdata.md) e garantir que a nota de sessão
    no cofre Obsidian NÃO traga CPF/valores reais (AGENTS.md).
13. **O que um contador exigiria para confiar:** (1) plano de contas validado por ele; (2) regras v2 ligadas desde o dia 1; (3) fechamento mensal travando o período (existe) e
    pendências visíveis antes de fechar (existe `pendencias_por_mes`); (4) conciliação bancária (existe); (5) trilha de quem mudou preço de plano/contrato (falta — registrar `atualizado_por`);
    (6) exportação reprodutível (zip com hash/data — parcialmente); (7) nenhum número zero "mentiroso" quando falta fonte; (8) política de retenção/backup documentada; (9) amostra de
    pacote real revisada por ele antes do primeiro cliente.
14. **Agenda "a receber".** Do ponto de vista de fluxo de caixa de leiteiro, o atraso do laticínio é o alerta mais caro. A Agenda não tem "a receber" (só despesa, e só 30 dias de vencidas):
    uma conta a pagar vencida há 45 dias SOME da Agenda. Para o contador isso é falha de controle. Propor: vencidas sem limite (ou 180 d) + cartão separado "A receber".

---

## (d) Correções factuais ao PLANO v1 (arquivo:linha)

| # | Afirmação do v1 | Fato verificado | Evidência |
|---|-----------------|-----------------|-----------|
| 1 | G1 "Rebanho obrigatório: fazendas.py:452 (400…)" | Correto. Mas também é premissa em: docstring de planos.py (l.1-20 "rebanho sempre incluso em todo plano"), docstring de `provisionar_fazenda_nova` (fazendas.py:65-67), `definir_contrato` pacote grava preço na linha rebanho (444). | fazendas.py:444,452-453; planos.py:1-20 |
| 2 | G1 UI "FazendasAdmin.tsx:131" | Há TRÊS pontos no web (131, 189, 533) e TRÊS no mobile (139, 186, 530), mais lista de planos hard-coded (490 / 499) e tipo `PlanoNome` (api.ts:561). | FazendasAdmin.tsx:131,189,490,533; FazendasMobile.tsx:139,186,499,530 |
| 3 | G1 "_preco_mensal_contrato (fazendas.py:389) lê PLANOS_CATALOGO AO VIVO" | Correto, mas INCOMPLETO: a mesma regra está copiada em `asaas.py:_valor_mensal` (l.30-39) e `cobranca.py:_valor_mensal` (l.24-33) — é o valor COBRADO. E o model afirma o contrário (congelado). | fazendas.py:389-391; asaas.py:37-39; cobranca.py:30-32; planos.py ≈107-110 |
| 4 | G6 "só preço por MÓDULO é editável (PrecoModulo + PUT)" | A API existe (fazendas.py:555-575) mas NÃO há UI: `atualizarPrecoModulo` (api.ts:643) e `fetchPrecosModulo` (api.ts:638) não têm nenhum chamador em .tsx. Nada no backend lê `PrecoModulo` além do próprio CRUD. Logo "editável no Painel CowData" exige tela nova também. | grep em frontend; fazendas.py:555-575 |
| 5 | G3 "agenda.py MODULO_TECNICO_PARA_COMERCIAL (~l.98)" | Está em agenda.py:103. O furo concreto é `tem_reproducao = "reproducao" in modulos_funcionario` (agenda.py:1736), que ignora o contrato; `tem_estoque` (1737) usa `modulos` (filtrado). agenda_v2.py:53-62 (`_modulos`) herda o mesmo mapa. | agenda.py:103-106, 1700-1707, 1736-1737; agenda_v2.py:53-62 |
| 6 | G5 "Pedidos dá entrada em estoque sem checar módulo: pedidos.py:~490" | Linhas 491-503. Mas NÃO é só Pedido: o Financeiro faz o mesmo ao lançar nota de despesa com produto (financeiro.py:4420-4475), ao editar quantidade (5152-5163) e na vinculação de produto (5250-5265). Sem item cadastrado NÃO bloqueia: devolve aviso (estoque_baixa.py:410-411). Item inativo bloqueia com 409 (estoque_baixa.py:132-145). | pedidos.py:491-503; financeiro.py:4420-4475,5152-5163,5250-5265 |
| 7 | D3 "Agenda: contas a pagar/receber vencidas/próximas" | A Agenda só traz contas a PAGAR (`tipo == "despesa"`, agenda.py:~575-595, com comentário explicando que receita foi removida por gerar alarme falso) e vencidas só até 30 dias (`DIAS_CONTAS_VENCIDAS_NA_AGENDA = 30`, agenda_engine.py:74). "A receber" é funcionalidade NOVA. | agenda.py:556-595; agenda_engine.py:74 |
| 8 | F2.2 / G4 Sidebar "só com Agenda, Controle Financeiro, Cotações, Pedidos, Configurações" | Configurações não está na Sidebar: vive no portal "Administração" (atalho que abre em NOVA ABA, Sidebar.tsx:402-415). Existe também o atalho "Insights" (386-401) e o rodapé "Trocar de conta". | Sidebar.tsx:84-102,386-415 |
| 9 | F3 "e2e Playwright já existente em frontend/e2e" | Existe um único script Python (`e2e/janela_travada.py`) que exige subir backend e frontend à mão; não é suíte. Testes automatizados do front = `node --experimental-strip-types --test lib/**/*.test.ts` (package.json:10), só lógica pura. | frontend/e2e; package.json |
| 10 | G7 "nenhum teste sobe o app" (migração f6a7b8c9d0e1) | Impreciso. `test_planos_contrato.py` sobe `TestClient(main.app)` com `create_all` + `FAZENDA_TESTING=1` (conftest.py:283), e `_aplicar_alembic` faz `stamp` quando o banco já tem tabelas (database.py:~500-507). O bug só aparece em `alembic upgrade head` de banco VAZIO em SQLite (testes `test_migracao_*` e uvicorn local com arquivo novo). Importante: em PRODUÇÃO toda migração nova roda no BOOT (database.py:507, via `create_db_and_tables` no lifespan) — migração ruim derruba a API. Não consegui rodar nada (sem dependências). | database.py:462-510; main.py:259-273 |
| 11 | F0 "corrigir a migração (batch_alter_table) — tarefa spawnada separada" | Concordo, mas a correção tem de ser NO LUGAR (mesmo `revision`/`down_revision`), senão o teste de cabeça única (`test_alembic_heads.py`) falha ao encadear a migração nova. O docstring da f6a7 diz "Revises: 78dbbd8c8c0f" mas o código usa `down_revision = 'g7h8i9j0k1l2'` (cabeça única hoje = f6a7b8c9d0e1, calculado por varredura). | alembic/versions/f6a7b8c9d0e1_*.py |
| 12 | G2 "/indicadores só exige contrato ativo (main.py:1001)" | Correto. Idem `alertas_indicador` (1004, só `_protegido`), `nao_conformidades` (1008), `exportacoes_relatorio` (1015), `assistente` (1102), `portal` (1067), `notificacoes` (1058): não foram inventariados quanto a dado de rebanho. | main.py:1001-1015,1058,1067,1102 |
| 13 | G4 "Home é sempre '/' ... login/page.tsx:134" | Correto (login/page.tsx:134; AuthShell.tsx:98; Sidebar.tsx:86; app/page.tsx:604-621). Faltou: (i) `ROTA_MODULO["/"]="capa"` e AuthShell.tsx:168 não checa `capa`; (ii) laço de redirect se `rotaInicial` for rota proibida; (iii) mobile `/app/page.tsx` não filtra por módulo; (iv) `/` é também a landing pública para anônimos — a troca só vale para logado. | api.ts:186; AuthShell.tsx:156-168; app/page.tsx:604-621 |
| 14 | "O que já foi PROVADO (sonda GET)" | Não reproduzido nesta revisão (sem ambiente). Tratar como hipótese até o teste de matriz do v2 (F3). | — |
| 15 | F4 Produção "fazenda eh_teste com plano Financeiro; SHA + deploy SUCCESS" | Criar fazenda e contrato em produção é escrita em dado real/SaaS: não cabe numa execução autônoma noturna. No v2 vira etapa humana (F5). | AGENTS.md "Disciplina de verificação" |

### Tabela de relatórios do Financeiro × fonte de dados (para a fase de UI)
| Relatório (relatoriosNavegacao.ts) | Depende de | Plano [financeiro, pedidos] |
|---|---|---|
| Painel do dono | a confirmar (PainelDonoView) | verificar |
| Resultado por litro | litros: nota do laticínio (conta rmca_receita_leite) ou EntregaLeiteMensal (produtivo) | funciona só com plano de contas padrão marcado |
| DRE, Classificar, Caixa real, Fluxo, Livro caixa | Financeiro | OK |
| Custos do leite (visões litro/lote/ha/safra) | litro: acima; lote: Animal+ControleLeiteiro (relatorio_custo_producao.py:22); ha: área; safra: agricultura | só "litro"; esconder lote/ha/safra sem fonte |
| RMCA | custo alimentação (contas) + litros; lado "físico" usa ConsumoAlimento/Estoque (relatorio_leite.py:30) | parcial |
| Réguas de referência | a confirmar | verificar |
| Orçamento, Cenários (+ telas anteriores) | `/planejamento/*` (main.py:977) → módulo `planejamento` | 403 → esconder |
| Compra/Venda de animais; Compra de sêmen | rebanho (main.py:1052-1053) | 403 → esconder |
| Pacote do contador, Fechamento, Conciliação | Financeiro + Patrimônio | OK |

---

## (e) O que NÃO foi verificado

- Nenhuma execução: sem pytest, sem backend, sem frontend, sem navegador, sem screenshots. Todas as notas de contraste, tamanho de alvo e layout são inferência por código/CSS.
- A "sonda" do v1 (200/403 por rota) não foi reproduzida; a matriz de status por rota do v2 precisa ser criada e executada.
- Se `test_migracao_*` hoje falham por causa da f6a7 (provável, não confirmado).
- Se há outras rotas que escrevem/leem dado de rebanho ou estoque sem gate de módulo: `alertas_indicador`, `nao_conformidades`, `exportacoes_relatorio`, `assistente`, `portal`, `notificacoes`, `central_documentos`, `cadastro` (Configurações > Cadastro > Itens de estoque — o router `cadastro` só exige contrato ativo, main.py:1042), `analise-relatorios`, `protocolos`. Só inspecionei os gates em main.py.
- Conteúdo de `PainelDonoView`, `ReguasReferenciaView` e `analise-relatorios` (podem depender de rebanho).
- Se `seed_tipos_documento_formas_pagamento` / formas de pagamento / tipos de documento são por fazenda ou globais (afeta o "dia 1" do cliente novo).
- Chaves exatas de `linha_dre` para um plano padrão (precisa ler rules/dre.py e `ParametroFazenda` inteiros).
- Comportamento real do PWA/Capacitor (`/app`) numa fazenda sem rebanho.
- Produção: Railway/Vercel/banco real; cofre Obsidian (sem conector nesta sessão — nenhuma nota gravada; ver "nota de sessão" entregue na resposta final).
- Next.js 16: não li as docs de `useRouter`/`redirect` (apenas localizei os arquivos); o plano v2 manda o implementador lê-las antes de tocar `app/page.tsx` e `AuthShell.tsx`.
- Dark mode e paletas alternativas dos componentes novos.
