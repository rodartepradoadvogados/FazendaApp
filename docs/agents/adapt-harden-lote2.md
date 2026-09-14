# Análise e proposta — `/impeccable adapt` + `/impeccable harden` (lote 2, 11 telas)

> Base: `docs/agents/critique-lote2-consolidado.md` (11 superfícies, 22 avaliações).
> Lentes aplicadas agora: **adapt** (responsivo, device/contexto) e **harden** (erros, i18n, edge cases).
> Regra de ouro do projeto: **toda proposta vira mockup HTML standalone antes de tocar código real**. Transversais primeiro.
> Escopo: **refinamento, não redesign** — identidade "Institucional" preservada (2px cantos, marinho `#0E2A47`/ouro `#8A6D2F`, Barlow Condensed, Gold-Is-Action, No-Lift, Almost-Square).

---

## 0. Critérios das duas lentes

**adapt** — breakpoints `320–767` (mobile) / `768–1023` (tablet) / `1024+` (desktop); alvos de toque ≥44px; `clamp()` para tipografia fluida; `env(safe-area-inset-*)`; `@media (hover:none)/(pointer:coarse)`; sem hover-only em touch; navegação colapsada.

**harden** — overflow/truncate/`line-clamp`; i18n (orçamento de expansão 30–40% do pt-BR); erros por status-code (401→login, 403→permissão, 404→não encontrado, 429→rate limit, 500→genérico+suporte); estados vazio/loading/concorrente/dataset grande; validação de entrada; a11y; performance.

---

## 1. Transversais (tratar primeiro)

### T1 — Sidebar quebra no mobile · `adapt` · P0

**Onde está (confirmado no código):**
- `frontend/components/AuthShell.tsx:362` → `className="md:flex farm-shell-h bg-fazenda-bg md:overflow-hidden"`
- `frontend/app/globals.css:966-970` → `.farm-shell-h { height: calc(100vh - var(--faixas-topo-h, 0px)) }` **só dentro de** `@media (min-width:768px)`.

**O que acontece:** abaixo de 768px a sidebar fica `relative` e empurra o conteúdo ~850–870px abaixo da dobra (reportado de forma aguda em Estoque, mas afeta **todas** as telas).

**Proposta (refinamento):**
- <768px: sidebar vira **off-canvas** (drawer) + top bar fixa com gatilho hambúrguer; conteúdo ocupa 100% da largura.
- Altura do shell em mobile: `min-height: 100dvh` (não `100vh`) + `env(safe-area-inset-top/bottom)`.
- Drawer acessível: `aria-expanded`, `aria-controls`, focus-trap, `Esc` fecha, `role="dialog"`, overlay `position:fixed`.
- ≥768px: comportamento atual preservado (sem mudança visual/estrutural).

**Resultado:** elimina o "conteúdo abaixo da dobra" em todas as 11 telas, sem redesenhar o layout desktop.

### T2 — Falha de rede mascarada como logout · `harden` · P0

**Onde está (confirmado no código):**
- `frontend/components/AuthShell.tsx:110-118` → guard redireciona para `/login` quando `!getToken()` (ausência de token).
- `frontend/lib/api.ts:1281-1319` → `authFetch` só chama `logout()` em **HTTP 401 explícito** (e trata 409 de fazenda não selecionada); **rejeição de rede (fetch lança) não é capturada**.

**O que acontece:** uma falha de rede é indistinguível de "sessão perdida" — o guard que só olha `!getToken()` não vê o erro, e nenhuma camada converte a rejeição em estado de "offline/retry". O usuário fica sem feedback acionável.

**Proposta (refinamento):**
- Separar três estados: **(a)** sem token → redirect `/login` (mantém); **(b)** 401 explícito → `logout()` + redirect (mantém); **(c)** falha de rede (fetch rejeitado) → **não** deslogar, expor erro tipado.
- `authFetch` captura rejeição de rede e a re-propaga como erro tipado (`NetworkError`), sem tocar no token.
- `AuthShell` exibe banner "sem conexão / tentar novamente" com retry quando detecta o erro tipado.
- 403/404/429/500: hoje raw em várias telas → padronizar (ver §3).

**Resultado:** usuário nunca é deslogado por uma queda de rede; erro vira estado recuperável, não tela em branco.

---

## 2. `adapt` por tela (responsivo / device)

| Tela | Score | Achado adapt | Proposta |
|---|---|---|---|
| **Agenda** | 22/40 | Timeline sempre expandida; 8 KPIs sem chunking; 4 filtros sem rótulo | Mobile: timeline colapsada (acordeão por dia); KPIs em carrossel horizontal ou empilhados; filtros empilhados com `label` + `id` (também harden/a11y) |
| **Lançamentos** | 31/40 | Drawer lateral "Salvar e próximo" em mobile; grade de 14 tipos | Mobile: drawer vira bottom-sheet full-screen (safe-area); grid de tipos 2 col com alvo ≥44px |
| **Central Protocolos + Sanidade** | 27/40 | `WizardProtocolo` `borderRadius:14`+sombra pesada; nav 3 níveis | Mobile: wizard vira passos 1-por-1 full-width; nav aninhada colapsa em `<details>`/accordion; cantos → 2px (Almost-Square) |
| **Rebanho** | 27/40 | Painel de filtro todo dourado; badge "Vazia/Não apta" inconsistente | Mobile: filtros em collapsible; dourado só em ação (Gold-Is-Action); badge unificado |
| **Histórico+Reprodução+Produção** | 24/40 | Troca de token de cor no KPI (`var(--blue)`); tabs | Mobile: KPI com token correto; tabs com scroll horizontal + `aria-selected` |
| **Ciclo 21d** | 22/40 | Tooltips dependem de hover (mortos em touch); modal | Mobile: tooltip → texto inline/`title`; modal full-screen com `Esc` + `role="dialog"` |
| **Alimentação** | 24/40 | Tabs | Mobile: tabs scrolláveis; consistência de estado entre tabs |
| **Estoque** | 24/40 | **Sidebar mobile (T1)** confirmado ~870px; sem ponto de entrada p/ novo item | T1 resolve; botão "Novo item" visível em mobile (FAB ou topo) |
| **Insights** | 25/40 | Sub-tabs não endereçáveis por URL | Deep-link das sub-tabs (`?tab=`), habilitando voltar/atualizar no mobile |
| **Administração** | 22/40 | `type="text"` em senha (autofill/teclado mobile); módulos pré-marcados | `type="password"` + `autocomplete`; seleção de módulos com toggle ≥44px |
| **Formulação de Dietas** | 25/40 | Wizard passos 8–9 bloqueados; passos 5–7 var técnico cru | Mobile: wizard 1-passo-por-vez; passos 8–9 habilitar ou marcar "em breve" de forma honesta |

---

## 3. `harden` por tela (erros / i18n / edge cases / a11y)

| Tela | Score | Achado harden | Proposta |
|---|---|---|---|
| **Agenda** | 22/40 | Guard de auth mascara falha de rede (**T2**) | T2: estado offline/retry, sem logout por rede |
| **Lançamentos** | 31/40 | `FormFinanceiro` 20+ campos sem disclosure; `Campo` sem `htmlFor`/`id`; empty-state drawer fora do DESIGN | Progressive disclosure (seções colapsáveis); `label` vinculado; empty-state conforme DESIGN |
| **Central Protocolos + Sanidade** | 27/40 | `FormProtocoloIatf` "Salvar" único sem recap; busca sem `label`/`id` | Recap antes de salvar (confirmar); busca rotulada; validação no submit |
| **Rebanho** | 27/40 | Badge inconsistente; overload (estado concorrente) | Badge unificado; estado de carregamento/erro explícito ao filtrar |
| **Histórico+Reprodução+Produção** | 24/40 | Erro fragmentado em 3+ variações; drift de copy | Um componente único de erro por status-code; copy centralizada |
| **Ciclo 21d** | 22/40 | Erro "Failed to fetch" cru e dead-end | Mapear erro p/ status-code + ação (retry) — padrão T2 |
| **Alimentação** | 24/40 | **BUG REAL**: banner de erro duplicado (`page.tsx:256-258`); `error.message` cru em 3/4 tabs | Corrigir `aba === "consumo" \|\| aba === "lote"`; erro tipado em todas as tabs |
| **Estoque** | 24/40 | Estados de erro/vazio abaixo do padrão | Estados conforme DESIGN (vazio → ação; erro → retry) |
| **Insights** | 25/40 | "Indicadores" sem indicadores; "Listas de trabalho" vs "Situação reprodutiva" duplicam resposta; `borderRadius:12` | Remover/redirecionar tab morta; unificar tabs duplicadas; cantos 2px |
| **Administração** | 22/40 | **BUG REAL**: `AuthShell.tsx:100` `ROTAS_INSIGHTS` omite `/documentos-central` (sidebar dupla/tela branca); desativar usuário sem `confirm()`; senha `type="text"`; Portal engole erro (`.catch(()=>{})`) | Adicionar `/documentos-central` ao array; `confirm()` antes de desativar; `type="password"`; propagar erro do Portal |
| **Formulação de Dietas** | 25/40 | **BUG REAL**: `dietas/page.tsx:118` `itens` nunca vira `[]` no catch (lista presa em "Carregando…"); "Failed to fetch" cru; proporção ≠100% não bloqueia | Setar `itens = []` no catch; erro tipado; validar soma=100% antes de prosseguir |

---

## 4. Próximos passos (na ordem)

1. **Mockups HTML standalone** — para as 2 transversais + as 11 telas (cada proposta vira um `.html` autossuficiente, usando os tokens Institucional), *antes de qualquer edição em `.tsx`/`.css`*.
2. **Re-score** dos mockups via `critique` contra o baseline do lote 2 (alvo: subir cada tela sem quebrar a identidade).
3. **Implementar** apenas depois do mockup aprovado, começando pelos transversais T1 (AuthShell+globals) e T2 (api+AuthShell).

> Ordem de implementação sugerida quando os mockups forem aprovados: T1 → T2 → bug-reais (Alimentação banner, Administração `ROTAS_INSIGHTS`, Dietas `itens=[]`) → demais P0/P1 por tela.
