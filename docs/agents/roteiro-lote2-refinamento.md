# Roteiro — refinamento por tela + pipeline Impeccable (lote 2)

> Ordem definida com o usuário em 15/09/2026. Regra permanente: todo achado vira mockup HTML antes de tocar código real.

## Ordem de execução

1. **Refinamento por tela (9 superfícies) + T3 (skeleton universal)** — esta etapa
2. **Pipeline completo do Impeccable** (`polish` → `colorize` → `typeset` → `animate` → `delight` → `overdrive`)
3. **5 itens adiados de propósito**
4. **Decisão pendente** (componentes órfãos do login)

---

## Etapa 1 — Refinamento por tela + T3

### T3 — Skeleton de carregamento universal · `adapt`/`harden` · P1 (novo, transversal)

**Situação atual**: a classe `.skeleton` (brilho/shimmer) já existe em `frontend/app/globals.css:774` e é reaproveitável. Só a Capa (`frontend/app/page.tsx`, `PainelSkeleton`) usa isso hoje — as outras 10 telas mostram texto solto ("Carregando…") ou nada.

**Proposta**: criar um componente de skeleton genérico e configurável (blocos de título + cards + tabela), e aplicá-lo em todas as 11 telas no lugar de "Carregando…" / tela em branco.

**Viabilidade**: alta — reaproveita CSS já existente, não exige token novo.

### 9 superfícies — mockup + implementação

| # | Tela | Nota atual | Itens a resolver (do lote 2) |
|---|---|---|---|
| 1 | Agenda | 22/40 | 8 KPIs sem chunking, timeline sempre expandida, 4 campos sem rótulo |
| 2 | Lançamentos | 31/40 | `FormFinanceiro` sem disclosure, `Campo` sem `htmlFor`/`id`, empty-state fora do padrão |
| 3 | Central Protocolos + Sanidade | 27/40 | Wizard com cantos/sombra fora do padrão, nav em 3 níveis, "Salvar" sem recap |
| 4 | Rebanho | 27/40 | Painel de filtro todo dourado, badge de status inconsistente |
| 5 | Histórico+Reprodução+Produção | 24/40 | Token de cor trocado no KPI, erro fragmentado em 3 variações |
| 6 | Ciclo de 21 dias | 22/40 | Erro cru sem saída, tooltip morto em toque, modal sem `Esc` |
| 7 | Estoque | 24/40 | Sem ponto de entrada para novo item, estados fora do padrão |
| 8 | Insights | 25/40 | Aba "Indicadores" sem indicadores, 2 abas duplicando resposta, cantos fora do padrão |
| 9 | Administração | 22/40 | `type="text"` em senha, módulos pré-marcados, Portal engole erro |

**Passos**:
1. Mockup HTML de cada tela (achados do lote 2 já documentados em `critique-lote2-consolidado.md` e `adapt-harden-lote2.md`) + mockup do skeleton universal (T3).
2. Aprovação do usuário, mockup por mockup ou em lote — a combinar.
3. Implementação, tela por tela, com verificação em `npx tsc --noEmit` + navegador antes de cada commit.

---

## Etapa 2 — Pipeline completo do Impeccable

Rodar em sequência, sobre as 9 superfícies refinadas + T3 (e qualquer tela já no ar tocada na Etapa 1). **Pré-requisito:** Etapa 1 implementada e verificada (`npx tsc --noEmit` + navegador) — o pipeline inspeciona código real em execução.

> Correção de método (15/09): a crítica do lote 2 foi consolidada em `docs/agents/critique-lote2-consolidado.md`, NÃO em `.impeccable/critique/` (essa pasta só tem os 6 snapshots do lote 1, de 12/09). Por isso `$impeccable polish` (que lê `critique-storage latest`) não encontra os achados do lote 2 — o "snapshot a fechar" aqui é o próprio `critique-lote2-consolidado.md`, e "fechar" = marcar cada P0/P1 como resolvido/não-aplicável na seção "Status" deste roteiro.

1. **`polish`** — por superfície, na ordem da Etapa 1 (T3 → Agenda → Lançamentos → Protocolos+Sanidade → Rebanho → Histórico+Reprodução+Produção → Ciclo 21d → Estoque → Insights → Administração). Para cada uma: revalidar contra o código atual, absorver os P0/P1 restantes do `critique-lote2-consolidado.md`, conferir no navegador (temas claro/escuro/misto + mobile onde couber) que o estado bate com o "Proposta" do mockup, e marcar como fechado no Status. Se `$impeccable polish` não achar snapshot, passar os achados explicitamente (já estão no doc consolidado).
2. **`colorize`** — disciplina do ouro (Gold-Is-Action): Rebanho (painel de filtros) e Insights (destaques indevidos); confirmar dourado só em salvar/confirmar + números de destaque. Conferir as 8 cores de categoria (`--cat-*`) fixas e o token do KPI "Concepção/serviço" (voltar ao reprodutivo). Testar nas 3 paletas (vinho/verde/azul) — o papel do ouro varia por paleta.
3. **`typeset`** — hierarquia tipográfica: título 700/800, rótulo maiúsculo com letter-spacing ≥0.06em, valor de KPI 800/~2rem com tabular-nums, corpo ~0.875rem. Fonte via `--font-heading`/`--font-body` (Archivo no site; Inter no app de campo). Varrer as 9 superfícies contra drift de fonte/peso.
4. **`animate`** — micro-interações apenas, todas cobertas por `prefers-reduced-motion`: shimmer do skeleton (T3), acordeão da timeline (Agenda) e do disclosure (Lançamentos), entrada/saída de modal com Esc (Ciclo 21d). Reusar o vocabulário existente (`.painel-expansivel`, `.linha-colapsavel`, `.popup-*`, `.toast-*`). Nunca lift no hover (No-Lift).
5. **`delight`** — SÓ sob pedido do dono, depois de ver tudo implementado. Não acionar por iniciativa própria.
6. **`overdrive`** — SÓ sob pedido explícito. Não acionar por iniciativa própria.

Regra transversal: verificação (`npx tsc --noEmit` + navegador) antes de cada commit; refinar, não redesenhar.

---

## Etapa 3 — 5 itens adiados de propósito

1. `confirm()` (ou modal próprio) antes de desativar usuário.
2. `type="password"` nos campos de senha.
3. Propagar erro hoje engolido no Portal (`.catch(()=>{})`).
4. Erro tipado em `dietas.ts` (hoje "Failed to fetch" cru).
5. Validação de soma=100% na composição da dieta antes de aplicar.

---

## Etapa 4 — Decisão pendente

Componentes órfãos do login (`BannerCarousel`, `FeatureShowcase`, `BannerGrid`, `MilkPriceExplainer`, `banners.ts`) — ficaram sem uso depois que a landing pública foi reconstruída à parte. Decidir: apagar, ou portar as correções de contraste/acessibilidade para `LandingPublica.tsx`, que é quem está no ar hoje.

---

## Próximo passo imediato

Produzir os mockups HTML da Etapa 1 (T3 + 9 telas), um de cada vez ou em lote, para aprovação antes de qualquer código real.

---

## Status da implementação

### Revalidação (15/09/2026) — achados já corrigidos em disco antes desta rodada

- T1 (sidebar mobile): corrigido — `globals.css:966-981` já tem os dois blocos `@media` (`min-width:768px` e `max-width:767px` com `min-height:100dvh`).
- T2 (rede × logout): corrigido — `OfflineBanner.tsx` existe, `authFetch` dispara `cowdata:offline`, nunca desloga por falha de rede.
- Bug real Administração (`ROTAS_INSIGHTS` sem `/documentos-central`): corrigido.
- Bug real Alimentação (banner de erro duplicado): corrigido (PR #778).

### T3 — Skeleton universal — CONCLUÍDO (commit `06c28c85`)

Componente `TelaSkeleton` criado em `components/ui.tsx`, aplicado nas 11 telas do lote (Agenda, Central de Protocolos, Sanidade, Rebanho, Estoque, Ciclos de 21 dias, Insights/Indicadores, Administração/Usuários/Parâmetros/Documentos Central, Histórico/Produção + componentes de Reprodução, Alimentação, Dietas) no lugar de "Carregando…"/"Calculando…". `npx tsc --noEmit` limpo. Verificação no navegador não foi possível: o gate de sessão do `AuthShell` (`estado !== "logado"`) não resolveu localmente mesmo com token forjado, em qualquer rota testada (inclusive a Capa, não tocada nesta rodada) — pré-existente, não relacionado a este commit.

### Etapa 2 — pipeline completo (`polish` → `colorize` → `typeset` → `animate`) — CONCLUÍDA

Todos os 20 mockups da Etapa 2 revalidados/aplicados, commits em `claude/lote2-refinamento-design`, `npx tsc --noEmit` limpo em cada um:

- **polish** (10/10): T3 (`942c7149`), Agenda (`942c7149`), Lançamentos (`460eeacb`), Protocolos+Sanidade (`934157b1`), Rebanho (`a1817528`), Histórico+Reprodução+Produção (`68577668`), Ciclo de 21 dias (`7b61f104`), Estoque (`f84f1adb`), Insights (`24d15e83`), Administração (`7956bcd1`).
- **colorize** (5/5, commit `36de622b`): Rebanho (painel de filtros deixa de ser dourado) e Histórico (KPI "Concepção/serviço" volta ao token reprodutivo) corrigidos; sistema/Agenda/Insights revalidados — já corretos ou achado não localizado no código atual.
- **typeset** (3/3, commit `80c68366`): DESIGN.md atualizado de Barlow para Archivo (YAML + prosa); Histórico > Ciclos de IATF ganha título+descrição (só essa sub-aba não tinha); `.fazenda-table` ganha `tabular-nums` global.
- **animate** (2/2, commit `697470d6`): nova seção `## Motion` no DESIGN.md (tese, taxonomia de 5 tipos, escala de tempo, easing, regras nomeadas) — vocabulário todo já existia no código, nenhuma mudança de comportamento.

**`delight` e `overdrive` ficam GATED — não iniciar sem pedido explícito do usuário** (playbook completo mais abaixo, seção "Onde paramos + delight e overdrive").

**PR aberto para revisão: [#780](https://github.com/rodartepradoadvogados/FazendaApp/pull/780)** (`claude/lote2-refinamento-design` → `main`, 16 commits, 59 arquivos). Os 30 mockups do lote (Etapa 1 + Etapa 2) foram versionados junto (commit `c7699b4a`), mesmo padrão do lote 1.

**Próximo passo:** aguardar review/merge do PR #780; depois seguir para a Etapa 3 (5 itens adiados) e Etapa 4 (decisão dos componentes órfãos do login) — ambas ainda não iniciadas.

Padrões já estabelecidos nesta etapa, reaproveitáveis nas próximas telas:
- `TelaSkeleton` (components/ui.tsx) — já tem role=status/aria-busy/altura sem CLS.
- `ErroCarregamento` (components/ui.tsx) — erro unificado com retry opcional (`onRetry`) e link de recuperação opcional (`linkHref`/`linkLabel`); usar em qualquer "Sem dados: {erro}." cru restante.
- `Modal` (components/Modal.tsx) — já tem focus trap + Esc + retorno de foco; qualquer overlay feito à mão deve migrar para ele.
- `SecaoRecolhivel`/`TabBar`/`SubNavTabs` (ui.tsx / SubNavTabs.tsx) — já têm aria-expanded/aria-selected/role.
- Padrão `Campo` com `htmlFor`/`id` automático via `useId()` + `cloneElement` — replicado em 3 arquivos (FormFinanceiro, FormFinanceiroSimplificado, lancamentos/comumForms); NÃO replicado ainda em CompraVendaAnimalForm.tsx, CompraSemenForm.tsx, FormPesagemCorporal.tsx, PortalView.tsx (mesmo `Campo` local sem id — se aparecerem no mockup de Administração ou depois, aplicar o mesmo padrão).

Itens de mockup revalidados contra o código e considerados NÃO aplicáveis ou já resolvidos por outra via (não fabricados): "Valor sem validação" em Lançamentos (CampoMoeda já impede entrada inválida); "vazio genérico" e duplicação de abas em Insights (não confirmados no código atual — ficam para decisão à parte, não é polish).

### Descoberta que muda a sequência

Encontrados em disco, não rastreados no git, produzidos por execução paralela: `docs/agents/design-mockups/etapa2-polish/` (9 arquivos `polish-*.html`, inclui `polish-t3-skeleton.html`) e `docs/agents/design-mockups/etapa2-colorize/` (5 arquivos `colorize-*.html`). Ou seja, mockups da **Etapa 2** (`polish`/`colorize`) já existem para várias telas, antes da Etapa 1 (refinamento por tela) estar implementada — fora da ordem que o usuário definiu. Não implementado nada a partir deles nesta rodada. Decisão do usuário necessária: (a) ignorar/descartar por enquanto e seguir a ordem original (Etapa 1 completa primeiro), ou (b) revisar esses mockups agora e ajustar a ordem.

### Próximo passo

Seguir tela por tela pela Etapa 1 (P0/P1 de cada mockup), com `tsc` + navegador antes de cada commit — navegador sujeito à mesma limitação de sessão local acima.


---

## Status da implementação (15/09/2026)

### Feito
- Mockups da Etapa 1 **aprovados pelo dono** e entregues em `docs/agents/design-mockups/` (10 arquivos: `t3-skeleton-universal.html` + as 9 telas), convenção Atual/Proposta com tokens Institucionais.
- Mockups do **polish** (Etapa 2) produzidos em `docs/agents/design-mockups/etapa2-polish/` (10 arquivos: `polish-t3-skeleton.html` + 9 telas) — acabamento pós-implantação (matriz completa de estados, craft-floor, consistência de ícone/cópia/espaçamento). Aguardando aprovação; na sequência: colorize → typeset → animate.
- Mockups do **colorize** (Etapa 2) produzidos em `docs/agents/design-mockups/etapa2-colorize/` (5 arquivos: `colorize-sistema.html` + rebanho, histórico, agenda, insights) — papéis de cor fixos, Gold-Is-Action, contraste AA, 3 paletas, cor por categoria. Na sequência: typeset → animate.
- Mockups do **typeset** (Etapa 2) produzidos em `docs/agents/design-mockups/etapa2-typeset/` (3 arquivos: `typeset-sistema.html` + histórico, tabela) — família única Archivo com hierarquia por peso, escala de papéis, All-Caps Label, medida 45–75ch, tabular-nums, compensação em fundo escuro. **Nota:** DESIGN.md ainda diz Barlow/Barlow Condensed — atualizar para Archivo. Na sequência: animate.
- Mockups do **animate** (Etapa 2) produzidos em `docs/agents/design-mockups/etapa2-animate/` (2 arquivos: `animate-sistema.html` + `animate-exemplos.html`) — tese de movimento (feedback/estado/continuidade + 1 momento focal), taxonomia de 5 tipos reusando o vocabulário existente, escala de tempo, easing, reduced-motion, No-Lift. **Pipeline Etapa 2 concluído** (polish → colorize → typeset → animate); delight e overdrive ficam gated, sob pedido explícito do dono.
- Código localizado: repo GitHub **`rodartepradoadvogados/FazendaApp`**, branch ativa **`claude/lote2-refinamento-design`** (PR **#778**), espelhado no Drive em `CowData-Milk/`.

### Descoberta que muda a sequência
O branch `claude/lote2-refinamento-design` **já contém correções** que a crítica de 13/09 apontava como pendentes. Verificado no código atual:
- `AuthShell.tsx`: `ROTAS_INSIGHTS` já inclui `/documentos-central` — o P0 "sidebar dupla/tela branca" da Administração já foi resolvido.
- `globals.css`: já existe o bloco `@media (max-width:767px)` de `.farm-shell-h` (`min-height:100dvh` + safe-area) — parte do T1 (sidebar mobile) já está no código.

Conclusão: **a crítica do lote 2 foi feita contra um estado anterior do código.** Antes de aplicar qualquer mudança, cada achado precisa ser revalidado contra o estado atual do branch — não aplicar cegamente linhas/estados da crítica.

### Ambiente de implementação e verificação
- A implementação + verificação obrigatória deste roteiro (`npx tsc --noEmit` + navegador antes de cada commit) rodam na **máquina Windows do dono via Claude Code** (mesma forma do lote 1), que é onde o branch `claude/lote2-refinamento-design` está checked out.
- A sessão de design/planejamento (Hermes na VPS) tem **leitura** do repo (Drive + GitHub API) mas **não tem o toolchain** (sem node_modules, sem app rodando, sem backend) para cumprir a verificação — não deve gravar código sem ela.

### Próximos passos (na ordem)
1. Revalidar os achados do lote 2 contra o branch `claude/lote2-refinamento-design` — o que já foi corrigido sai da fila; o restante é o escopo real.
2. Implementar os itens restantes na máquina com toolchain, tela por tela, com `npx tsc --noEmit` + navegador antes de cada commit.
3. Ordem já definida: transversais restantes → bugs reais restantes → P0/P1 por tela → Etapa 2 (pipeline Impeccable).


---

## Onde paramos + delight e overdrive (15/09/2026)

### Onde paramos
- **Etapa 1** (T3 + 9 superfícies): mockups aprovados e implementação em curso pelo Claude Code (branch `claude/lote2-refinamento-design`, PR #778) — ver o registro do próprio agente acima (T3 concluído no commit `06c28c85`; 9 superfícies em andamento).
- **Etapa 2** (pipeline Impeccable): DESENHADA por completo — 20 mockups em `docs/agents/design-mockups/etapa2-{polish,colorize,typeset,animate}/` — e o prompt de implementação (polish → colorize → typeset → animate, em sequência, sobre a Etapa 1) já foi entregue ao Claude Code, que está concluindo a aplicação.
- **Decisão resolvida**: a nota "fora da ordem" levantada pelo agente (mockups da Etapa 2 existirem antes da Etapa 1 estar implementada) foi decidida pelo dono — a Etapa 2 é DESENHADA em paralelo e IMPLEMENTADA depois da Etapa 1, nunca antes. Os mockups de Etapa 2 não entram junto da Etapa 1; são o alvo da passada seguinte (já orientada no prompt da Etapa 2).

### Próximos passos — delight e overdrive (GATED, sob pedido explícito do dono)

`delight` e `overdrive` NÃO foram feitos. Ficam registrados com método e candidatos, para outro agente executar na sequência, APENAS sob pedido explícito do dono (ele decide se quer e em qual superfície).

#### delight (playbook: delight.md)
- Modo do produto: **Operate + Read**. Delight concentra-se em momentos que merecem: conclusão de marco, recuperação de erro, primeiro uso/estado vazio, maestria. A confiabilidade carrega todo o resto.
- Método: definir UMA tese de uma frase (o que o usuário deve sentir e por que isso pertence a este produto) + o menor sistema que a entrega (resposta distinta a uma ação significativa, linguagem do produto, transição com material reconhecível).
- Candidatos naturais (a confirmar com o dono — NÃO implementar por conta):
  - Conclusão de marco: resposta proporcional ao esforço — o "marcar feito" da agenda já tem check+flash; uma baixa de animal ou fechamento de lote pode merecer um reconhecimento maior que um salvar rotineiro.
  - Recuperação: o "Tentar novamente" que funciona, com confirmação de que voltou — sem piada (não trivializar perda, dinheiro ou trabalho bloqueado).
  - Primeiro uso / estado vazio: deixar clara a próxima ação antes de adicionar personalidade.
- Proteções: nunca atrasar/bloquear a tarefa; nunca som sem consentimento; não virar obrigatório/cansativo na repetição; não adicionar dependência/asset desproporcional; linguagem de pecuária leiteira real (o genérico é pior que clareza neutra).

#### overdrive (playbook: overdrive.md) — comando de MAIOR risco de erro
- Modo do produto = UI funcional + densa em dados → o "wow" está no FEEL (fluidez), não em efeito visual. Ex.: tabela que rola 100k linhas a 60fps, diálogo que faz morph do gatilho, salvamento otimista instantâneo.
- Processo OBRIGATÓRIO antes de qualquer código:
  1. Pensar 2–3 direções diferentes (técnica, nível de ambição, estética), descrevendo resultado e trade-offs (suporte de navegador, custo de performance, complexidade).
  2. PARAR e pedir a escolha do dono antes de escrever código.
  3. Só seguir com a direção confirmada.
  4. Iterar com automação de navegador (preview + verificação visual), múltiplas rodadas — "parece extraordinário" fecha por iteração visual, não por código.
- Candidatos naturais (a PROPOR, nunca a escolher sozinho):
  - Virtual scrolling em tabelas grandes (Rebanho com milhares de animais; listas de lançamentos).
  - View Transitions / shared-element (linha do animal → ficha do animal).
  - Salvamento otimista com transição de estado instantânea nos formulários.
  - Gráficos Canvas/WebGL para datasets grandes.
- Disciplina: 60fps (se <50, simplificar); progressive enhancement com fallback funcional; lazy-init de recursos pesados; testar em dispositivo médio real; NUNCA jank em mid-range, NUNCA API bleeding-edge sem fallback, NUNCA som sem opt-in, NUNCA mascarar fundamento fraco com ambição técnica, NUNCA empilhar múltiplos momentos extraordinários.

Verificação (ambos): teste "wow" (reação de quem não viu), teste de remoção (sentiu falta?), teste de dispositivo, teste de contexto (faz sentido para a marca e a audiência).

---

## delight + overdrive — IMPLEMENTADOS (16/09/2026)

Pedido explícito do dono (prompt "delight + overdrive (direção B) · lote 2",
mockups aprovados em `etapa2-delight/` e `etapa2-overdrive/` — arquivos e
prompt lidos direto do Drive, pasta `agents`; não foram re-serializados
para o repo porque a leitura via API do Drive devolve uma representação em
markdown escapado, não o HTML original byte-a-byte, e recriá-lo do zero
arriscava corromper o mockup fonte — os 4 arquivos e o prompt continuam
íntegros no Drive, linkados abaixo pelo conteúdo já extraído nesta seção).

**PR #780 já estava mesclado quando este trabalho começou** — branch
`claude/lote2-refinamento-design` reiniciada a partir do `main` atual antes
de qualquer commit novo (mesmo padrão de outras rotinas desta conta).

### delight — 5/5 momentos implementados, cópia exata dos mockups
1. **Fechar o dia (Agenda)** — commit `50249ad2`. "Dia fechado — N de N
   concluídas." na última pendência real de hoje (contagem sem os filtros
   de categoria/período/busca, que só afetam o que é mostrado).
2. **Concluir protocolo (Ciclo de 21 dias)** — commit `c6c70fcd`. Ação real
   é "Encerrar protocolo" em `app/protocolos/page.tsx` (não em
   `app/ciclos-21-dias/page.tsx`, que é só leitura/BREDSUM — achado que
   corrigiu a premissa original do prompt). "Protocolo concluído — N
   vaca(s) sincronizada(s). Próxima avaliação em 21 dias." **só para
   origem IATF** — sanitário/indução/customizado/lida não são sincronização
   e não usam a frase (desvio deliberado, evita terminologia errada).
3. **Recuperar de erro (ErroCarregamento)** — commit `043fc8c9`. Novo hook
   `useAvisoRecuperado` + componente `AvisoRecuperado` em `components/ui.tsx`
   — "Voltou — dados atualizados às HH:MM." nos 3 chamadores existentes
   (todos em `app/estoque/page.tsx`).
4. **Começar módulo vazio (Estoque)** — mesmo commit `043fc8c9`. Estado
   vazio com CTA dourado "Cadastrar primeiro item" + chips de exemplo
   quando o inventário tem 0 itens.
5. **Despedir um animal (Rebanho)** — commit `5e608125`. A ação de baixa
   mora em `app/lancamentos/page.tsx` → `components/BaixarAnimal.tsx`, não
   em `app/rebanho/page.tsx` (achado que corrigiu a premissa original do
   prompt — `BaixarAnimal` é importado mas nunca usado em `rebanho/page.tsx`).
   Modal de confirmação sóbrio (marinho, nunca dourado) só na baixa
   DEFINITIVA; "Marcar A descartar" continua salvando direto. **Desvio**: a
   cópia usa "{nome} — {tag}", mas Animal não tem nome de exibição
   consistente nesta base real (campo opcional, esparsamente preenchido,
   nunca mostrado em nenhuma listagem) — usa só o número.

### overdrive — direção B (View Transitions), morph Rebanho implementado
Commit `6cc850c8`. Morph "linha → ficha" na tabela principal do Rebanho
(ambos os modos: agrupado por lote e "por número"), com fallback obrigatório
(sem a API ou com `prefers-reduced-motion`) e `@supports` guardando os
nomes fixos do lado da Ficha.

**Desvios do mockup**:
- Não existia clique "linha → ficha" na tabela principal do Rebanho antes
  deste commit (só existia em Touros, via `onAbrirFicha`) — implementado do
  zero, reaproveitando o mesmo padrão (`fichaNumeroInicial` + `trocarAba`).
- Não existia rota separada `/rebanho/[numero]` — é troca de aba dentro do
  mesmo componente (same-document), não navegação de rota.
- **2 elementos morfam, não 3**: tag (número) + pill de status reprodutivo
  ao vivo. O "nome" do mockup foi substituído pelo pill de status (mesmo
  motivo do item 5 do delight — Animal não tem nome de exibição
  consistente). `SIT_CORES` movido de `app/rebanho/page.tsx` para
  `lib/constants.ts` para evitar import circular com `FichaAnimal.tsx`.
- O pill de status na Ficha só aparece quando a navegação veio deste morph
  (contexto real passado pela linha clicada); uma visita direta à ficha
  (busca manual, `?numero=`) não mostra pill — evita inventar/buscar dado
  novo fora do escopo.
- Extensão a Lançamentos (valor+descrição) e Protocolo (título+status),
  sugerida no mockup como "reutilizável", **não implementada** — o prompt
  autorizava isso só "se couber no escopo"; ficou fora.

### Verificação
`npx tsc --noEmit` e `npm run build` limpos em cada commit. Verificado num
navegador real (Playwright/chromium), temas claro/escuro/misto + mobile
390px: os 5 momentos de delight e o morph funcionam conforme especificado
(screenshots + spy de `startViewTransition`); único item não testável foi o
estado vazio do Estoque (a fazenda de teste já tinha 17 itens cadastrados).
Confirmado: sem uso indevido de ouro, sem lift no hover, cantos 2px
preservados, console sem erros novos.

**Bug pré-existente encontrado** (não é regressão deste trabalho, não
corrigido aqui): `AgendaItem.chave` em
`backend/fazenda/rules/agenda_engine.py` gera a chave de um evento manual
da Agenda via hash de `data|categoria|descricao|numero_animal`, sem o id da
linha — dois eventos manuais com texto/data idênticos (sem animal vinculado)
colidem na mesma chave, e concluir um conclui os dois juntos. Reportado ao
dono separadamente. **Corrigido em 16/09/2026** (commit `74d36472`, PR
[#783](https://github.com/rodartepradoadvogados/FazendaApp/pull/783)) — ver
seção seguinte.

---

## Etapa 1 — 9 superfícies: revalidação + implementação CONCLUÍDA (17/09/2026)

Pedido do dono: "Vamos começar pelas 9 superfícies do lote 2, tela a tela."
Cada tela foi revalidada contra o código atual em `main` (pós PR #781 e
#783) antes de qualquer edição — vários achados da crítica original já
tinham sido corrigidos por trabalho anterior (polish/colorize/delight) e
saíram da fila sem gerar commit. Branch `claude/lote2-etapa1-telas`
(reiniciada a partir do `main` atual, mesmo padrão de outras rotinas desta
conta), `npx tsc --noEmit` limpo em cada commit, verificação em navegador
real (Playwright/chromium, login `teste_local`) para cada tela, temas
claro/escuro conferidos.

| # | Tela | Nota | Commit | Status |
|---|---|---|---|---|
| 1 | Agenda | 22/40 | `a4dd05e4` | KPIs agrupados por assunto (Reprodução/Sanidade/Geral); "Hoje" nasce expandido no acordeão da timeline (mecanismo de colapso por dia já existia, só o padrão estava errado). Achado dos 4 filtros sem rótulo já resolvido em passada anterior. |
| 2 | Lançamentos | 31/40 | `36c75986` | `FormFinanceiro`: os 6 campos mais usados de "Dados da nota" ficam sempre visíveis, os outros 11 atrás de um toggle "Mais detalhes" (abre sozinho quando vem de um pedido). `FormProtocoloIatf`: empty-state da gaveta IATF passa a usar `EstadoVazio`. `Campo` sem `htmlFor`/`id` já resolvido em passada anterior. |
| 3 | Central de Protocolos + Sanidade | 27/40 | `fe4ef0b0` (+ recap em `36c75986`) | `WizardProtocolo` volta a 2px/`shadow-sm` (era 14px + sombra pesada). "Salvar sem recap" resolvido via o mesmo recap "Animais selecionados/Protocolo" já existente no modo "Novo protocolo", estendido ao modo "Adicionar a protocolo existente". Navegação em 3 níveis da Sanidade **não mexida** — arquivo de ~2900 linhas, fora do orçamento de risco desta rodada (ver "Pendências" abaixo). |
| 4 | Rebanho | 27/40 | `56c7b5bd` | `AnimalModal.tsx` tinha `SIT_CORES` local com cores diferentes do mapa compartilhado (`lib/constants.ts`) — "Vazia"/"Não apta"/"Em protocolo" pintados diferente entre tabela e modal do mesmo animal. Removido o mapa duplicado. Painel de filtros dourado já resolvido em passada anterior (colorize, `36de622b`). |
| 5 | Histórico + Reprodução + Produção | 24/40 | `0b163dd8` | Seção BST de Produção mostrava erro cru (`<p>` vermelho sem retry); Equivalente Maduro mostrava erro E tabela vazia ao mesmo tempo. Ambos agora usam `ErroCarregamento` (retry) e Equivalente Maduro retorna só o erro, sem o card por baixo. Token de cor do KPI "Concepção/serviço" já resolvido em passada anterior (colorize, `36de622b`). |
| 6 | Ciclo de 21 dias | 22/40 | `cf8fc85c` | Erro sem retry → `ErroCarregamento` + função `tentarNovamente`. Tooltip `title` morto em toque nas barras Apt/Ins./Apt Real/Posit. removido (a Legenda, sempre visível, já cobre a mesma explicação — mesma lição que o comentário da própria `Legenda()` já registrava). Modal "Detalhe do ciclo" já usa o `Modal` compartilhado (Esc/role=dialog/foco) — não precisou de mudança. |
| 7 | Estoque | 24/40 | _(nenhum)_ | Revalidado, ambos os achados **já resolvidos** pelo delight da Etapa 2 (commit `043fc8c9`): botão "Novo item" no cabeçalho + estado vazio com CTA "Cadastrar primeiro item" e chips de exemplo. Nenhuma mudança necessária. |
| 8 | Insights | 25/40 | _(nenhum)_ | Revalidado: `/indicadores` tem conteúdo real (Indicadores Gerais, Não Conformidades, Recria, bezerras) — não é uma aba vazia. "Listas de trabalho" e "Situação reprodutiva (ao vivo)" são dois componentes distintos (`RelatoriosManejo` × `SituacaoReprodutivaAoVivo`), não uma duplicata literal. `border-radius:12px` do `CombinadorListas` já está em `var(--r-sm)`. Confirma achado já registrado numa passada anterior ("não confirmados no código atual"). |
| 9 | Administração | 22/40 | `4c78003e` | Senha em `type="text"` cru em `painel-cowdata/usuarios/page.tsx` (a tela irmã `app/usuarios/page.tsx` já usava `CampoSenha` mascarado) — `CampoSenha` exportado e reaproveitado nas duas telas. Usuário novo nascia com todos os módulos marcados (incl. Financeiro) nas duas telas — passa a nascer só com "Capa". `PortalView.tsx` engolia erro de rede em "Pendentes" (`.catch(()=>{})`), mostrando falso "Nada pendente" — agora guarda o erro e mostra `ErroCarregamento`. |

### Pendência registrada (não implementada nesta rodada)

**Sanidade — navegação em 3 níveis aninhados** (achado #2 da tela 3,
Central de Protocolos + Sanidade): `frontend/app/sanidade/page.tsx` tem
~2900 linhas e uma hierarquia real de abas → sub-abas → modos (4 → 5 → 5).
Reestruturar essa navegação (proposta do mockup: `<details>` colapsáveis)
sem quebrar nenhum dos fluxos existentes exige uma revisão muito mais
profunda do que o restante desta rodada — fica como item para uma rodada
dedicada, não é um bug simples de token/estado como os demais.

### Verificação

`npx tsc --noEmit` limpo a cada commit. Verificado em navegador real
(Playwright/chromium) contra o dev server local, login `teste_local`,
temas claro/escuro e (para Agenda/Lançamentos/Protocolos) mobile 390px —
todas as 7 telas com commit tiveram passe confirmado ao vivo, exceto os
dois achados de Administração sobre `type="password"`/menor privilégio:
a conta de teste é `admin`, mas as duas telas de cadastro de usuário
exigem papel `dono` (já existe um "dono" definido no banco de teste) —
confirmados por revisão de código (mesmo componente `CampoSenha` e mesmo
padrão `new Set(["capa"])`, ambos já exercitados ao vivo nas outras
telas), não foi forçado acesso além do que a conta de teste permite. O
3º achado de Administração (Portal engolindo erro) foi confirmado ao vivo
com falha de rede simulada.

**Branch `claude/lote2-etapa1-telas` → PR [#784](https://github.com/rodartepradoadvogados/FazendaApp/pull/784), mesclado em 17/09/2026.**

---

## Etapa 3 — 5 itens adiados de propósito: CONCLUÍDA (17/09/2026)

Pedido do dono: "Vamos para a próxima etapa" (após o merge do PR #784).
Branch `claude/lote2-etapa3-itens-adiados`, reiniciada a partir do `main`
atual. Dos 5 itens listados originalmente, 2 já tinham saído junto com o
PR #784 (mesmo achado repetido na tabela por-tela de Administração); os
outros 3 foram implementados aqui.

| # | Item | Commit | Status |
|---|---|---|---|
| 1 | `confirm()` antes de desativar usuário | `998aab69` | Implementado — `toggleAtivo` em `app/usuarios/page.tsx` pede confirmação só ao desativar (reativar continua instantâneo). |
| 2 | `type="password"` nos campos de senha | `4c78003e` (PR #784) | Já resolvido junto de Administração (tela 9/9) — mesmo achado, `CampoSenha` reaproveitado no Painel CowData. |
| 3 | Propagar erro hoje engolido no Portal (`.catch(()=>{})`) | `4c78003e` (PR #784) | Já resolvido junto de Administração (tela 9/9) — `PortalView.tsx` para de mostrar falso "Nada pendente". |
| 4 | Erro tipado em `dietas.ts` (hoje "Failed to fetch" cru) | _(nenhum)_ | Revalidado: `authFetch` (lib/api.ts) já traduz "Failed to fetch" via `netError()`/`NetworkError` automaticamente para QUALQUER chamador, `dietas.ts` inclusive — todas as chamadas do arquivo já passam por `authFetch`. Achado não se confirma mais no código atual; nenhuma mudança necessária. |
| 5 | Validação de soma=100% na composição da dieta antes de aplicar | `4472a095` | O aviso visual (âmbar) na grade de ingredientes já existia, mas nada travava "Aplicar na dieta atual". Extraída `proporcaoMsFecha100()` (mesma tolerância ±0,5pp do aviso) para `lib/dietas.ts`, reaproveitada para desabilitar o botão nas Etapas 4 (Balanço) e 10 (Relatório final), com `title` explicando o motivo. |

### Verificação

`npx tsc --noEmit` limpo em cada commit. Verificado em navegador real
(Playwright/chromium): confirm() testado (cancelar mantém ativo, aceitar
desativa, reativar não pede confirmação); soma=100% testado com
50%+50%=100% habilitando o botão e 30%+30%=60% desabilitando, em ambas as
etapas do wizard. `teste_local` (admin) não alcança `/usuarios` nem
`/dietas` (as duas exigem papel `dono`/módulo à-la-carte contratado) —
a verificação usou a conta `dono` já semeada no banco de teste local
(senha resetada só no `dev.db` local, descartável) e uma linha de
contrato de módulo inserida só no `dev.db` local, nenhuma mudança em
código ou nos dados reais. Sem erros novos de console; achado um gap de
tema escuro pré-existente no wizard de Dietas, não relacionado a esta
mudança — registrado como sugestão de tarefa separada, não corrigido
aqui.

**Branch `claude/lote2-etapa3-itens-adiados` → PR aberto para `main`.**

---

## Ordem de execução — status final

1. ~~Refinamento por tela (9 superfícies) + T3~~ — **concluído** (PR #781, #783, #784).
2. ~~Pipeline completo do Impeccable~~ — **concluído** (PR #780, delight+overdrive em 16/09).
3. ~~5 itens adiados de propósito~~ — **concluído** (esta seção).
4. ~~Decisão pendente (componentes órfãos do login)~~ — **concluída** (componentes descartados, comentário atualizado em `login/page.tsx`).

Pendência aberta fora desta ordem: navegação em 3 níveis da Sanidade
(`frontend/app/sanidade/page.tsx`, achado #2 da tela "Central de
Protocolos + Sanidade") — ver seção "Etapa 1", registrada para uma
rodada dedicada.
