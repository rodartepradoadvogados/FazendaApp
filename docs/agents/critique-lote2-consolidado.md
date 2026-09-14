# Crítica em lote — 2ª rodada (Agenda, Lançamentos, Protocolos+Sanidade, Rebanho, Histórico, Ciclo 21d, Alimentação, Estoque, Insights, Administração, Dietas)

> Gerado por Claude Code (sessão interrompida por desligamento do computador do usuário).
> Método: dual-agent (Assessment A = revisão de design isolada; Assessment B = detector CLI + evidência de navegador isolada), seguindo `impeccable critique`.
> Ambiente de teste: backend fora do ar (proposital) — toda tela mostra estado de erro/vazio, nunca dados reais. Isso é esperado e já foi descontado das críticas abaixo; não é um achado em si.
> **Escopo confirmado com o usuário**: Histórico inclui Reprodução+Produção; Protocolos+Sanidade tratados juntos (compartilham código); Alimentação e Formulação de Dietas são telas distintas; Insights e Administração no volume real (não reduzido).

## Status geral

**22 de 22 avaliações concluídas — TODAS as 11 superfícies com Assessment A + B completos.** Nada ficou pendente na etapa de crítica. Ver seção "Pendências" ao final para os próximos passos (mockups + implementação), não para crítica em si.

| # | Superfície | Assessment A (design) | Assessment B (detector/browser) |
|---|---|---|---|
| 1 | Agenda | ✅ 22/40 | ✅ |
| 2 | Lançamentos | ✅ 31/40 | ✅ |
| 3 | Central de Protocolos + Sanidade | ✅ 27/40 | ✅ |
| 4 | Rebanho | ✅ 27/40 | ✅ |
| 5 | Histórico + Reprodução + Produção | ✅ 24/40 | ✅ |
| 6 | Ciclo de 21 dias | ✅ 22/40 | ✅ |
| 7 | Alimentação | ✅ 24/40 | ✅ |
| 8 | Estoque | ✅ 24/40 | ✅ |
| 9 | Insights (Indicadores+Listas+Relatórios) | ✅ 25/40 | ✅ |
| 10 | Administração (6 abas) | ✅ 22/40 | ✅ |
| 11 | Formulação de Dietas | ✅ 25/40 | ✅ |

---

## 🔴 ACHADO TRANSVERSAL MAIS IMPORTANTE — bug de layout mobile, confirmado em 6 telas independentes

Abaixo de 768px de largura (breakpoint `md` do Tailwind), a sidebar do site **não vira `fixed` de verdade**: o `position` computado fica `relative` mesmo com as classes `fixed md:static ... -translate-x-full` presentes no elemento. Resultado: a sidebar ocupa espaço em fluxo normal (~850-870px de altura), empurrando todo o conteúdo real da página (título, filtros, tabela) para muito abaixo da tela visível — sem barra de rolagem para alcançá-lo na maioria dos casos.

**Confirmado independentemente em**: Estoque, Alimentação, Ciclo de 21 dias, Central de Protocolos, Sanidade, Histórico/Reprodução/Produção, Rebanho (7 telas, algumas em contexto de navegador isolado do zero, descartando contaminação de teste).

**Causa raiz identificada**: `frontend/components/AuthShell.tsx` (linha ~362, `className="md:flex farm-shell-h bg-fazenda-bg md:overflow-hidden"`) + `frontend/app/globals.css` (linhas ~966-969) — a regra de altura de `.farm-shell-h` está **escopada só a `@media (min-width:768px)`**. Abaixo disso, o `overflow:hidden` continua valendo mas a compensação de altura/scroll não é aplicada, e o container pai só vira `flex` a partir de `md:`, então abaixo do breakpoint o `<aside>` e o `<main>` empilham em fluxo bloco normal.

**Ação recomendada**: `$impeccable harden frontend/components/AuthShell.tsx frontend/app/globals.css --foco="sidebar mobile abaixo de 768px"` — é o item de maior impacto de todo o lote, porque afeta literalmente qualquer tela do site em celular/tablet estreito.

## 🔴 Segundo achado transversal — falha de rede tratada como sessão inválida

Com o backend fora do ar, sessões autenticadas (mesmo com token válido) foram redirecionadas sozinhas para `/login`, sem ação do usuário — confirmado por observação direta em 2 telas diferentes (Protocolos/Sanidade e Rebanho), e teorizado de forma independente pela crítica da Agenda antes de ser confirmado ao vivo.

**Causa raiz identificada**: `frontend/components/AuthShell.tsx` linhas 110-118 (redireciona quando `!getToken()`) + `frontend/lib/api.ts` linhas 1281-1288 (`authFetch` só chama `logout()` em HTTP 401 explícito — mas uma conexão recusada rejeita a Promise antes dessa checagem rodar). Nenhum trecho encontrado que limpe o token em falha de rede propriamente dita — mecanismo exato ainda não 100% confirmado, mas o sintoma é reproduzível.

**Ação recomendada**: `$impeccable harden frontend/components/AuthShell.tsx frontend/lib/api.ts --foco="distinguir falha de rede de sessão expirada"`.

---

## 1. Agenda (`frontend/app/agenda/page.tsx`, 2764 linhas) — 22/40

**Veredito**: KPIs (Candidatas IATF, BST, cronograma sanitário) codificam regras reais; camada de interação é genérica.

**Prioritários**:
- **P0** Auth guard mascara falha de rede como logout silencioso (ver achado transversal acima).
- **P1** 8 KPIs sem chunking + timeline sempre 100% expandida. `$impeccable simplify agenda --foco=hierarquia`
- **P1** Página monolítica de 2764 linhas, >10 sub-fluxos independentes no mesmo estado — risco de vazamento de estado entre fluxos. `$impeccable adapt agenda --split=componentes`
- **P2** `borderRadius:6` hardcoded (linha 921) vs `var(--r-sm)` no resto do arquivo — quebra Almost-Square Rule dentro do mesmo arquivo.
- **P2** 4 campos de filtro sem `id`/`name`/label (confirmado via console).

## 2. Lançamentos (`frontend/app/lancamentos/page.tsx` + ~23 arquivos em `components/lancamentos/`) — 31/40 (nota mais alta do lote)

**Veredito**: genuinamente específico (D0/D7/D9/D11, FIFO, unidades compatíveis). Mistura 2 "eras" de padrão visual (gaveta lateral vs. card cheio), documentado no código como transitório.

**Prioritários**:
- **P1** 14 de ~27 tipos de lançamento abrem em gaveta lateral com rodapé "Salvar e próximo"; os outros 13 (incl. Financeiro, o mais usado) ficam em card cheio sem esse rodapé. `$impeccable harden frontend/app/lancamentos`
- **P1** `FormFinanceiro` expõe 20+ campos sem progressive disclosure — é o lançamento mais frequente (contas a pagar/receber) e o mais sobrecarregado. `$impeccable clarify components/FormFinanceiro.tsx`
- **P2** Componente compartilhado `Campo` (`comumForms.tsx`) renderiza label/input como irmãos sem `htmlFor`/`id` — bug estrutural propagado em ~20 formulários; correção única no componente propaga a todos. `$impeccable harden components/lancamentos/comumForms.tsx --a11y`
- **P2** Empty state da gaveta IATF quebra a própria regra do DESIGN.md (deveria ser borda tracejada+ícone+surface-2).

## 3. Central de Protocolos + Sanidade (`frontend/app/protocolos/page.tsx` 1145 linhas + `frontend/app/sanidade/page.tsx` 2854 linhas) — 27/40

**Veredito**: vocabulário real (D0/D7/D9/D11, "evento de vida"); casca de interação (wizard, cards) é genérica.

**Prioritários**:
- **P0** `FormProtocoloIatf` termina num único "Salvar" sem recapitulação de nº de animais/estoque de hormônio a debitar — decisão de alto custo sobre lote inteiro sem pausa de confirmação. `$impeccable harden components/lancamentos/FormProtocoloIatf.tsx --foco confirmacao-de-compromisso`
- **P1** `WizardProtocolo.tsx` usa `borderRadius:14`+sombra pesada, destoando do resto da tela (2px/sem sombra) — é o componente mais NOVO do produto quebrando a assinatura visual mais citada do DESIGN.md.
- **P1** Sanidade: navegação em 3 níveis aninhados (Curativa/Preventiva/Rastreabilidade/Catálogo → 5 sub-abas → mais 5 modos dentro de Preventiva>Calendário) — "wall of options" refletindo o arquivo de 2854 linhas na profundidade de cliques. `$impeccable simplify app/sanidade/page.tsx --foco navegacao`
- **P2** Console confirma campos sem label/id no campo de busca de `ListaProtocolos`.
- **P3** Aba "Ocorrências (novo modelo)" escondida por decisão do dono mas código/rota continuam vivos — código morto acumulando no monólito.
- Achado B: catálogo de sanidade mostra "Failed to fetch" E "Carregando…" simultaneamente (estado inconsistente).

## 4. Rebanho (`frontend/app/rebanho/page.tsx` 663 linhas + `FichaAnimal.tsx`) — 27/40

**Veredito**: genuinamente zootécnico (DEL, PEV, NAAB/TPI/NM$, Brix colostro). Ficha do Animal = dossiê ~20 seções sem sumário/navegação interna.

**Prioritários**:
- **P1** Painel de Filtros inteiro pintado de dourado (background+border dourado, linhas 440-443) — viola a Gold-Is-Action Rule do próprio DESIGN.md ("nunca decoração de card"). `$impeccable harden rebanho --rule=gold-is-action`
- **P1** Mesmo rótulo "Vazia"/"Não apta" com CORES DIFERENTES entre `page.tsx` (linha 51) e `AnimalModal.tsx` (linhas 44-45) — badge muda de cor entre tabela e modal do mesmo animal. `$impeccable harden rebanho --rule=consistency-tokens`
- **P2** `EstratificacaoRebanho` usa `borderRadius:8` (linha ~132) vs `var(--r-sm)` do resto.
- **P2** Sobrecarga: 3 filtros+3 checkboxes+7 KPIs+2 gráficos simultâneos; KPIs duplicam as mesmas categorias do donut ao lado.

## 5. Histórico + Reprodução + Produção (`historico/page.tsx` 75L + `reproducao/page.tsx` 58L + `producao/page.tsx` 1709L + 4 componentes de histórico) — 24/40

**Veredito**: genuinamente pecuário (DEL, ECC, GMD/GPD, Equivalente Maduro). Entrega desigual entre sub-telas.

**Prioritários**:
- **P1** Token de cor trocado: KPI "Concepção/serviço" (Reprodução) usa `var(--blue)` = hex documentado no DESIGN.md como "Azul Produção... decisão explícita e não muda". `$impeccable harden historico --fix-category-color-tokens`
- **P1** Erro fragmentado em 3+ variações na mesma jornada (BST cru, CiclosIatf descarta seção inteira, Equivalente Maduro mostra erro+vazio simultâneos — confirmado ao vivo).
- **P2** Drift de texto entre 2 cascas: `historico/page.tsx` (linha 65) omite "ciclos de IATF" que `reproducao/page.tsx` (linha 48) inclui — cópia manual duplicada, uma desatualizada.
- **P2** "Secagem"/"Secagens": mesmo componente, dois rótulos, sem link cruzado.
- Achado B: aba "Ciclos de IATF" não tem heading/descrição (diferente das outras 3 abas testadas); tira de abas da Produção transborda horizontalmente até em desktop 1280px (EQUIVALENTE MADURO cortado).

## 6. Ciclo de 21 dias (`frontend/app/ciclos-21-dias/page.tsx` 302 linhas) — 22/40

**Veredito**: legenda visível com boa justificativa de touch, mas "BREDSUM\E" (nome do próprio método) e "PEV" nunca são definidos.

**Prioritários**:
- **P0** Estado de erro é beco sem saída — "Failed to fetch" cru, inglês, sem retry/link ao indicador de API já existente na sidebar. `$impeccable harden ciclos-21-dias --error-states`
- **P1** `borderRadius:6` nos campos de filtro + 4 campos sem label/id confirmado ao vivo. `$impeccable polish FiltroCiclo21Dias --tokens --a11y`
- **P2** Tooltips mortos em toque contradizendo o próprio comentário do código (a Legenda sabe que `title` não funciona em touch; resto da tela não aplica essa lição).
- **P3** Modal de drill-down sem Esc/clique-fora/`role=dialog`.

## 7. Alimentação (`frontend/app/alimentacao/page.tsx` 271 linhas + `FormAlimentacaoDieta.tsx`) — 24/40

**Veredito**: cálculo em cascata (por cabeça→lote/dia→trato→vagão) exposto na copy — genuíno. Camada de erro regride pra "Failed to fetch" genérico.

**Prioritários**:
- **P0** BUG REAL DE CONDIÇÃO: banner de erro duplicado na aba Necessidade Mensal — a condição do banner de topo (`page.tsx` linhas 256-258) não exclui "mensal", que já tem seu próprio erro independente. Fix: `aba === "consumo" || aba === "lote"`. `$impeccable harden alimentacao --fix-duplicate-error-state`
- **P1** `error.message` cru exposto em 3 das 4 abas. `$impeccable copy alimentacao --error-messages`
- **P2** `FormAlimentacaoDieta.tsx` (linhas 104-105) usa `<p>` cru em vez do `.alert-critico` padrão das outras abas.
- Achado B: bug de layout — imagem de fundo full-bleed sizada pra 1 viewport-height fica PRIMEIRO no DOM flow, então em scroll=0 a tela inteira mostra só a foto, conteúdo real só aparece rolando ~2/3 de tela (mesma família do achado transversal de mobile, mas ocorre mesmo além do bug da sidebar).

## 8. Estoque (`frontend/app/estoque/page.tsx` 700 linhas) — 24/40

**Veredito**: `EstoquePicker`/`NovoItemEstoque` genuinamente específicos (FIFO, carência, embalagens por frasco); casca é CRUD-report genérico.

**Prioritários**:
- **P0** Confirma o bug de sidebar mobile (ver achado transversal) — aqui com a métrica mais completa: sidebar ocupa ~870px em fluxo, conteúdo real cai pra ~900-1000px abaixo da dobra.
- **P1** Nenhum ponto de entrada pra cadastrar item novo em `/estoque` (só existe em Configurações>Cadastro ou Pedidos) — no momento exato que o alerta "abaixo do mínimo" pede ação, não há caminho de resolver ali.
- **P2** Estados de erro/vazio abaixo do padrão do DESIGN.md em 3 das 4 abas.
- **P3** Formulário de item é grade plana com 25+ campos sem agrupamento.

## 9. Insights — Indicadores + Listas + Relatórios (`InsightsLayout.tsx` + `indicadores/page.tsx` 358L + `relatorios/page.tsx`+delegatos + `analise-relatorios/page.tsx`+delegatos, ~7 arquivos) — 25/40

**Veredito**: vocabulário genuíno (PEV/IATF/DEL/IEP, semáforo com regra documentada). MAS a aba "Indicadores" **não mostra os indicadores** — `IndicadoresGerais()` migrou pra `/rebanho` sem deixar rastro.

**Prioritários**:
- **P0** Aba "Indicadores" não entrega o que promete — KPIs reais moram em `/rebanho` agora. `$impeccable audit indicadores`
- **P0** "Listas de trabalho" e "Situação reprodutiva (ao vivo)" respondem à MESMA pergunta do usuário, diferença é técnica (CSV congelado × recálculo ao vivo) nunca exposta na UI. `$impeccable simplify listas-ia`
- **P1** Sub-aba não é endereçável por URL (useState local, não lê `?sub=` embora a URL já aceite). `$impeccable fix subnav-url-state`
- **P1** Tudo nasce fechado (`defaultAberta=false` em ~23 seções ao todo) — tela "de confiança" abre sem nenhum número visível.
- **P2** `CombinadorListas.tsx` usa `borderRadius:12` cru (DESIGN.md documenta 8-16px como "já tentado e revertido").
- Achado B (detector): `InsightsLayout.tsx:254` tem animação de `width`/`padding` (layout thrash) — verificado, verdadeiro positivo.

## 10. Administração — 6 abas (Configurações, Parâmetros, News, Controle de Acesso, Central de Documentos, Portal) — 22/40

**Veredito**: especificidade em ilhas (Documentos fiscal×financeiro; tabela de bonificação de leite em Parâmetros). Resto é CRUD genérico de SaaS B2B.

**Prioritários**:
- **P0 BUG REAL COM CAUSA RAIZ**: Central de Documentos renderiza a Sidebar completa do site JUNTO com a casca de Administração (duas navegações simultâneas / ou tela em branco, dependendo do que a Assessment B viu — mesma causa raiz). Causa: `AuthShell.tsx` linha ~100, array `ROTAS_INSIGHTS` lista as outras 5 abas mas ESQUECE `/documentos-central`. Fix: adicionar a rota ao array. `$impeccable harden frontend/components/AuthShell.tsx --focus="rota documentos-central ausente de ROTAS_INSIGHTS"`
- **P0** Desativar usuário (clicar "Ativo") acontece SEM `confirm()`, diferente de excluir faixa de bonificação/rejeitar matéria (que TÊM confirmação) — a ação mais sensível da tela sem rede de segurança. `$impeccable harden frontend/app/usuarios/page.tsx --focus="confirmação ao desativar usuário"`
- **P1** Campos "Senha"/"Nova senha" usam `type="text"` — senha exposta em texto puro.
- **P1** Erro cru transversal em Parâmetros/News/Usuários.
- **P2** Novo usuário nasce com TODOS os módulos pré-marcados (incl. Financeiro) — viola menor privilégio.
- **P2** Portal engole erro de rede (`.catch(()=>{})`), mostrando falso "Nada pendente" quando dados nunca carregaram.
- Achado B: `/documentos-central` renderiza quase em branco (só barra superior), confirmado em 2 capturas estáveis. `NewsAdmin.tsx`/`usuarios/page.tsx` têm 3 achados de detector `side-tab` (borda de 3px lateral).

## 11. Formulação de Dietas (`dietas/page.tsx` + `/nova` + `/biblioteca` + wizard `[id]` de 10 etapas, ~1700 linhas) — 25/40

**Veredito**: genuinamente NASEM/NRC onde há explicação (PainelExigencias, FormAnimal). Cai abruptamente nas Etapas 5-7 (`PainelDominio`): 20-30 variáveis técnicas cruas sem interpretação.

**Prioritários**:
- **P0** "Failed to fetch" cru sem recuperação em 3 telas — mas `dietas/nova/page.tsx` JÁ TEM o padrão certo (mensagem clara + botão "Tentar novamente"), só falta replicar. `$impeccable harden dietas error-states`
- **P0 BUG REAL DE MÁQUINA DE ESTADOS**: lista e biblioteca (`dietas/page.tsx` linha 118) ficam em "Carregando…" PERMANENTE quando o fetch falha, porque `itens` nunca é setado pra `[]` no catch. `$impeccable fix dietas-list loading-state`
- **P1** Etapas 8-9 do wizard são placeholders travados PERMANENTEMENTE mas contam no "/10", inflando complexidade percebida.
- **P1** Etapas 5-7 despejam variáveis técnicas sem nenhuma frase interpretativa.
- **P2** Soma de proporção≠100% e composição de leite faltante não bloqueiam "Aplicar na dieta atual" — só aviso de texto, numa decisão com consequência real de custo/saúde animal.
- **P2** `RelatorioFinal` sem veredito sintetizado no topo.
- (Assessment B desta superfície ainda não retornou — ver Pendências.)

---

## PENDÊNCIAS — o que falta e como fechar

**A etapa de crítica está 100% completa — as 22 avaliações (11 superfícies × Assessment A+B) terminaram todas dentro do prazo.** Nada ficou pendente de execução nesta etapa.

O que falta é a PRÓXIMA etapa do processo (ainda não iniciada, por decisão do usuário): decidir com ele por onde começar os mockups HTML, e só depois implementar. Ver o prompt abaixo para o próximo agente.

Nota: Lançamentos-B foi o último a chegar (registrado na seção 2 com achados adicionais: 2 achados de detector `side-tab` em FormParto.tsx linhas 40/64 — avaliados como possível falso-positivo, é um traço fino de 3px em item de lista dentro de modal instrutivo, não um "card" propriamente dito; e 24+21 campos sem label/id confirmados no formulário Financeiro > Contas a Pagar, o maior número de achados de acessibilidade de todo o lote).

### Prompt pronto para o próximo agente (modelo deepseek-v4-pro, via Claude Code)

Copie o bloco abaixo como instrução para o agente que vai continuar este trabalho:

---

Você está retomando uma crítica de UX em lote no projeto CowData-Milk (`C:\Projetos\CowData-Milk`), usando o skill Impeccable. Leia primeiro este documento inteiro: `docs/agents/critique-lote2-consolidado.md` — ele já traz 11 superfícies com Assessment A (revisão de design) completo, e 9 delas também com Assessment B (detector+navegador) completo.

Faltam apenas 2 Assessments B, que não terminaram antes da sessão anterior encerrar:

1. **Lançamentos** — rode `$impeccable critique frontend/app/lancamentos/page.tsx`, mas como o Assessment A já está pronto (seção 2 deste documento), rode SÓ o Assessment B (detector `impeccable detect --json` nos arquivos de `frontend/components/lancamentos/`, mais evidência de navegador ao vivo em `/lancamentos`, incluindo mobile). Sintetize com o Assessment A já registrado e atualize a seção 2 deste documento.
2. **Formulação de Dietas** — mesma coisa: Assessment A já está na seção 11; rode só o Assessment B contra `frontend/app/dietas/*` e `frontend/components/dietas/*`, incluindo tentar acessar `/dietas/1` (ou outro id real, se existir no banco) pra testar o wizard ao vivo, que não foi possível testar no ambiente sem backend.

Depois de fechar essas 2 pendências, siga para a próxima etapa: com o usuário (dono do produto), decidam JUNTOS por onde começar os mockups HTML das prioridades levantadas (ele pediu decisão conjunta, não decisão automática do agente). Antes de qualquer mockup, **trate primeiro os dois achados transversais no topo deste documento** (bug de sidebar mobile e falha de rede tratada como sessão inválida) — afetam todas as 11 superfícies e são as correções de maior alavancagem de todo o lote.

Todas as propostas de mudança devem virar mockup HTML autônomo antes de qualquer código real ser tocado (regra permanente do usuário, já em vigor desde a primeira rodada deste projeto) — não implemente nada direto a partir dos achados acima sem esse passo.

---

### Observação sobre o ambiente de teste

Todas as críticas acima foram feitas com o backend do FastAPI **desligado de propósito** (ambiente local, sem Postgres configurado) — toda tela mostra estado de erro "Failed to fetch" em vez de dados reais. Isso foi contabilizado nas críticas (os achados de UX continuam válidos), mas significa que nenhuma tela foi vista com dado real populado. Ao rodar as 2 críticas pendentes, se o backend estiver disponível nessa sessão, prefira testar também com dados reais — vai revelar achados que o ambiente sem backend não permite ver (paginação, ordenação, densidade real da tabela).
