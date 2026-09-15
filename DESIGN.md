---
name: CowData
description: Painel de gestão de pecuária leiteira — direção "Institucional", lê como relatório, não como app genérico.
colors:
  marinho: "#0E2A47"
  azul-aco: "#416180"
  marinho-profundo: "#0A1F36"
  ouro-escurecido: "#8A6D2F"
  ouro-claro: "#C9A44C"
  bg: "#F4F6F9"
  surface: "#FFFFFF"
  surface-2: "#F9FAFB"
  border: "#DCE3EA"
  border-forte: "#C3CDD8"
  texto: "#1F2937"
  texto-mudo: "#6B7280"
  verde: "#2E7D52"
  verde-claro: "#4CAF80"
  vermelho: "#C0392B"
  ambar: "#D97706"
  azul-producao: "#1E6FA8"
  cat-reprodutivo: "#8B7FF0"
  cat-sanidade: "#4E7A5A"
  cat-alimentacao: "#E0A63C"
  cat-gestao: "#5B8FB0"
  cat-financeiro: "#7A2233"
  cat-estoque: "#C98A2A"
  cat-recria: "#B0894A"
  cat-acesso: "#9A5560"
typography:
  display:
    fontFamily: "Archivo, Inter, sans-serif"
    fontWeight: 700
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Archivo, Inter, sans-serif"
    fontWeight: 700
  body:
    fontFamily: "Archivo, Inter, sans-serif"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Archivo, Inter, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    letterSpacing: "0.13em"
rounded:
  sm: "2px"
  md: "2px"
  lg: "2px"
  pill: "999px"
spacing:
  sm: "0.5rem"
  md: "1rem"
  lg: "1.25rem"
components:
  button-primary:
    backgroundColor: "{colors.marinho}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.25rem"
  button-gold:
    backgroundColor: "{colors.ouro-escurecido}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.25rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.texto-mudo}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1rem"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "1.25rem"
  kpi-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "1.25rem"
---

# Design System: CowData

## Overview

**Creative North Star: "The Institutional Ledger"**

CowData troca a planilha Excel de uma fazenda leiteira por um software próprio — e o produto se recusa a parecer um "app de startup" por cima disso. A direção vigente (chamada de "Institucional" no próprio código) mira o oposto do dashboard genérico: cantos quase retos, sem gradiente, sem elevação no hover, tipografia condensada em maiúsculas nos rótulos, números tabulares alinhados. A régua é literal — cada tela deve **ler como um relatório impresso ou extrato bancário**, não como um produto de consumo. Marinho e azul-aço carregam a estrutura e os dados; ouro é reservado para o que importa confirmar (salvar, números de destaque).

O app de campo (`/app`, PWA/Capacitor) é um subsistema deliberadamente separado: onde o site é sóbrio e denso, o campo é grande, alto-contraste e touch-first, pensado para sol forte e dedos com luva — nunca uma versão "encolhida" do desktop.

**Key Characteristics:**
- Cantos quase retos (2px no site, 0px no app de campo) — a assinatura mais visível da direção Institucional.
- Sem gradiente, sem sombra elevada, sem deslocamento no hover — repouso é plano; estado muda só a cor.
- Ouro sólido é ação de confirmação, não decoração — usado com moderação.
- Cores de categoria fixas (8 módulos) atravessam todo o produto sem variar por tema/paleta.
- App de campo (`.mob`) sempre marinho/ouro, independente da paleta escolhida no site.

## Colors

Paleta padrão de fábrica (tema claro + paleta "azul", a direção Institucional vigente). O produto também expõe paletas alternativas selecionáveis pelo usuário (vinho — identidade histórica da Fazenda Jairo Nasser — e verde); a estrutura de papéis é a mesma, só os valores trocam. Documentado aqui: a paleta padrão.

### Primary
- **Marinho Institucional** (`#0E2A47`): navegação, títulos de card/tabela, sidebar ativa, botão primário. Carrega a estrutura da tela.
- **Azul-Aço** (`#416180`): série de dados primária em gráficos, estados de hover sobre marinho.
- **Marinho Profundo** (`#0A1F36`): selo/gradiente da marca, fundo do cabeçalho do app de campo.

### Secondary
- **Ouro Escurecido** (`#8A6D2F`): números de destaque, réguas finas, ação de "salvar/confirmar" (`.btn-primary-gold`) — nunca a cor padrão de todo botão.
- **Ouro Claro** (`#C9A44C`): texto sobre fundo marinho sólido (wordmark, aba ativa da sidebar).

### Neutral
- **Fundo** (`#F4F6F9`): fundo de página no tema claro.
- **Superfície** (`#FFFFFF`) / **Superfície 2** (`#F9FAFB`): cards e cabeçalhos de tabela.
- **Borda** (`#DCE3EA`) / **Borda Forte** (`#C3CDD8`): contorno padrão vs. contorno de campo/tabela que precisa de mais peso.
- **Texto** (`#1F2937`) / **Texto Mudo** (`#6B7280`): corpo vs. rótulo/legenda.

### Semantic
- **Verde** (`#2E7D52`) / **Verde Claro** (`#4CAF80`): positivo, meta batida, "concluído".
- **Vermelho** (`#C0392B`): alerta crítico, atraso.
- **Âmbar** (`#D97706`): atenção intermediária (ex. PEV, pendência).
- **Azul Produção** (`#1E6FA8`): única categoria de indicador que não segue a paleta de marca — "Produção" ficou azul por decisão explícita e não muda.

### Category (fixas em todo o produto)
Reprodutivo `#8B7FF0` · Sanidade `#4E7A5A` · Alimentação `#E0A63C` · Gestão/Financeiro-geral `#5B8FB0` · Financeiro `#7A2233` · Estoque `#C98A2A` · Recria `#B0894A` · Acesso `#9A5560` — mesma cor em Agenda, Indicadores, menu do app e landing; nunca redefinidas por tela.

### Named Rules
**The Gold-Is-Action Rule.** Ouro sólido preenchido só aparece em botões de salvar/confirmar ou em números que pedem destaque. Nunca é a cor padrão de um botão primário ou uma decoração de card.

## Typography

**Display/Heading Font:** Archivo (com fallback Inter, sans-serif)
**Body Font:** Archivo (com fallback Inter, sans-serif) — mesma família do heading; a hierarquia vem do peso, não de uma segunda família.
**Fontes de uso único:** Dancing Script (só o "milk" cursivo da marca d'água do login); Sora 700/800 (tipografia de manual de marca, hoje só no Milk News, disponível para expansão futura).
**App de campo:** Inter para tudo — deliberadamente diferente do site, sem herdar Archivo.

**Character:** Archivo em peso 700-800 nos títulos/rótulos/números dá o tom "relatório impresso" (maiúsculo, letter-spacing largo nos rótulos); o mesmo Archivo em peso 400 no corpo mantém legibilidade em tabelas densas sem competir com os rótulos — uma família única, hierarquia só por peso/tamanho/tracking.

### Hierarchy
- **Título de página** (700, 1.75rem, letter-spacing -0.02em): `h1` — Archivo.
- **Title** (700, `.card-header`/`h2-h4`, 0.8rem, +0.04em, caixa alta): título de card — Archivo.
- **KPI Value** (800, ~2rem, tabular-nums): valor de indicador — a maior ênfase numérica da tela.
- **Body** (400, ~0.875rem, entrelinha 1.5): texto de tabela e conteúdo corrido — Archivo, medida confortável (45–75ch) em parágrafos longos.
- **Label** (600, 0.6875rem, letter-spacing 0.13em, uppercase): cabeçalho de tabela e rótulo de KPI — sempre maiúsculo e espaçado, nunca peso menor que 600.
- **Metadata** (400, 0.75rem, cor mudo): timestamp, legenda secundária.
- Texto claro sobre fundo marinho sólido compensa nos 3 eixos: entrelinha um pouco maior, tracking um tiquinho a mais, um passo de peso acima do que teria sobre fundo claro.

### Named Rules
**The All-Caps Label Rule.** Todo rótulo estrutural (cabeçalho de tabela, label de KPI, seção) é maiúsculo, condensado e com letter-spacing largo (≥0.06em) — é o que empresta o "ar de relatório" à tela.

## Layout

Densidade de relatório: cards com padding 1.25rem, tabelas com linhas separadas por filete de 1px (zebra removida deliberadamente). Sidebar fixa à esquerda no desktop; no mobile/tablet (abaixo de 768px) vira barra superior fixa com menu hambúrguer. Abaixo de 767px: padding de página cai para ~1rem, títulos de página encolhem, tabelas ficam mais compactas (padding de célula 0.45rem/0.6rem) — nunca rolagem horizontal da página inteira, só a tabela dentro do próprio card rola lateralmente quando larga. Faixa fixa de ações do topo (tema, notificações) respeita `env(safe-area-inset-*)` para não cobrir notch/status bar.

## Elevation & Depth

Sistema quase plano por decisão explícita: um único `--shadow-sm` (`0 1px 4px rgba(20,30,45,0.10)`) em repouso, sem variação por elevação e **sem deslocamento (translateY) no hover** — nem em botão, nem em card. Profundidade real vem de cor (filete lateral de 3px no `.kpi-card`, fundo tingido nos badges), não de camadas de sombra.

### Named Rules
**The No-Lift Rule.** Nenhum componente se move ou ganha sombra maior ao passar o mouse. Hover muda cor (escurece ~15%), nunca posição ou elevação — é o que separa a estética de "relatório" da de "app de consumo".

## Shapes

Cantos quase retos em toda a superfície de dados: `--r-sm/md/lg = 2px` no site (era 8/12/16px antes da direção Institucional — reduzido deliberadamente porque "tira a sensação de app genérico"). Exceções propositais, não drift: pílulas de aba/filtro (`999px`) e ícones circulares de categoria (`50%`). O app de campo (`/app`) usa `--r-app: 0px` — reto puro nos cards/inputs, mesmas exceções de pílula/círculo para nav e chips de estado.

### Named Rules
**The Almost-Square Rule.** Se não é uma pílula de navegação/filtro ou um círculo de ícone, o raio é 2px (site) ou 0px (app de campo). Nunca um meio-termo "moderno" de 8-16px.

## Components

### Buttons
- **Shape:** 2px de raio, sem exceção por variante.
- **Primary:** `.btn-primary` — marinho sólido (`#0E2A47`), texto branco, padding `0.5rem 1.25rem`.
- **Gold:** `.btn-primary-gold` — mesma forma, ouro escurecido; reservado para salvar/confirmar.
- **Hover:** escurece ~15% em direção ao preto (`color-mix`); nunca sombra ou translateY.
- **Ghost/Secondary:** `.btn-ghost` (transparente, borda neutra, fundo `surface-2` no hover) e `.btn-secondary` (fundo `surface-2`, borda ouro no hover) — usados como ação secundária ao lado de um primário.

### Cards
- **Corner Style:** 2px.
- **Background:** `surface` sobre `bg`, borda 1px `border`.
- **Shadow:** `--shadow-sm` único, sem variação por estado.
- **KPI card (`.kpi-card`):** filete sólido de 3px à esquerda — marinho por padrão, ouro na variante `--destaque` (indicadores reprodutivos/IATF).

### Badges (categoria)
- Fundo tingido (`color-mix` 20-24% sobre a cor da categoria) + texto e borda na cor sólida da categoria — mesmo tratamento nas 5 categorias de indicador (reprodutivo, sanidade, produção, financeiro, atividades).

### Tables
- Cabeçalho com fundo em gradiente marinho→marinho-profundo, texto ouro-claro, maiúsculo, letter-spacing largo.
- Linhas separadas só por filete de 1px (zebra removida deliberadamente); hover tinge de `surface-2`.
- `.row-clickable` sinaliza linha interativa com filete lateral ouro no hover, não com cursor sozinho.

### Filters / Tabs
- **TabBar (pílula):** ativa = fundo/borda marinho, texto ouro-claro, peso 700; inativa = transparente, texto mudo.
- **MultiFiltro (dropdown de seleção múltipla):** botão mostra resumo ("Todos" / label / "N selecionados"); painel em portal com checkbox customizado (marcado = fundo/borda ouro).

### Empty / Dropzone
- **Estado vazio:** borda tracejada, ícone + texto mudo, fundo `surface-2` — nunca só texto solto.
- **Dropzone de upload:** borda tracejada 2px, destaca borda/fundo em `vinho-light` translúcido no hover/drag.

### Navigation
- Sidebar fixa (desktop) com logo em gradiente marinho, item ativo com borda ouro + fundo translúcido marinho.
- Foco de teclado (`:focus-visible`): anel duplo — contorno ouro-claro + miolo na cor de fundo da página, nunca em clique de mouse.

### App de campo — sistema à parte
Fonte Inter, cantos retos (0px, exceto pílulas/círculos), claro de alto contraste (sol) e escuro OLED verdadeiro. Ouro (`--mob-acao`) marca "ativo/ação" de forma consistente nos dois temas — diferente do site, onde o papel do ouro varia por tema. Botão central "Lançar" da nav inferior é um círculo ouro elevado acima da barra (único uso de elevação forte no produto, reservado a essa âncora). Estado de item (atrasado/normal/feito) é sempre um filete lateral colorido, nunca a cor de fundo inteira do cartão. Alvos de toque ≥44-48px; inputs com fonte ≥16px (evita zoom automático no iOS). **Não segue a paleta escolhida no site** — permanece marinho/ouro institucional mesmo se o usuário escolher a paleta verde ou vinho no site.

## Do's and Don'ts

### Do:
- **Do** manter cantos quase retos em toda superfície de dado (2px site / 0px app) — é a assinatura da direção Institucional.
- **Do** reservar ouro sólido para a ação de salvar/confirmar ou um número de destaque pontual.
- **Do** usar as 8 cores de categoria fixas em qualquer lugar que mostre a categoria (Agenda, Indicadores, menu do app, landing) — nunca remapear por tela.
- **Do** manter hover como troca de cor apenas — sem sombra maior, sem translateY.
- **Do** respeitar `prefers-reduced-motion` (desliga `.animate-in` e `.pulse-dot`).

### Don't:
- **Don't** arredondar cantos além de ~2px no desktop — lê como "app genérico", quebra a estética de relatório (raio de 8-16px já foi tentado e revertido).
- **Don't** adicionar gradiente de botão ou elevação/deslocamento no hover — rejeitado explicitamente na direção Institucional.
- **Don't** deixar o app de campo seguir a paleta do site (vinho/verde/azul) — ele é sempre marinho/ouro, por decisão de produto.
- **Don't** reintroduzir zebra striping nas tabelas — removida deliberadamente em favor do filete de 1px entre linhas.
