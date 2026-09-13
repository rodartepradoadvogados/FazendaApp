# Design Implementation — CowData (handoff para o agente de implementação)

> Documento gerado ao final de uma sessão de design com o Claude Code + skill **Impeccable**.
> Nada do que está descrito aqui foi implementado no código real ainda — tudo existe como
> mockups HTML autônomos (aprovados pelo dono do produto) e documentação de contexto.
> Este arquivo é a fonte da verdade para quem for implementar.

## 1. Contexto e propósito

O objetivo desta sessão foi: (1) documentar o produto e o sistema de design existentes,
(2) rodar uma crítica de UX/UI formal nas 6 superfícies do produto, e (3) produzir, para
cada achado prioritário aprovado, uma proposta visual em HTML — sem tocar no código real
do `frontend/`. O dono do produto aprovou as propostas e agora quer implementá-las de
verdade, usando um agente separado (modelo `deepseek-v4-pro`, rodando via Claude Code no
terminal). Este documento existe para que esse agente — sem nenhuma memória desta
conversa — saiba **exatamente** o que reproduzir, onde, e com que ferramentas.

## 2. Artefatos de contexto já existentes (ground truth)

Leia estes três arquivos **antes de qualquer coisa** — eles são normativos, não sugestivos:

| Arquivo | O que é |
|---|---|
| `PRODUCT.md` (raiz) | Contexto de produto: usuários, propósito, posicionamento, princípios. |
| `DESIGN.md` (raiz) | Sistema de design "The Institutional Ledger": tokens de cor/tipografia/raio/sombra, regras nomeadas (No-Lift, Gold-Is-Action, Almost-Square, All-Caps Label), Do's/Don'ts. |
| `.impeccable/design.json` | Sidecar do DESIGN.md — metadados de cor (tonal ramps), componentes de referência (HTML/CSS prontos), narrativa. |

Todo mockup descrito abaixo foi desenhado **usando esses tokens reais** (não valores
inventados) — os hex/variáveis que aparecem nos mockups são os mesmos que já existem em
`frontend/app/globals.css`.

## 3. Comandos do Impeccable — o que foi usado e o que não foi

### Usados nesta sessão

| Comando | Quantas vezes | Para quê |
|---|---|---|
| `$impeccable init` | 1x | Criou `PRODUCT.md` (entrevista sobre produto, usuários, posicionamento). |
| `$impeccable document` | 1x | Criou `DESIGN.md` + `.impeccable/design.json` a partir do código existente (modo scan, não seed). |
| `$impeccable critique` | 6x | Uma crítica formal por superfície (dual-agent: revisão de design + detector/evidência de navegador). Cada rodada gravou um snapshot em `.impeccable/critique/` (tabela na seção 5). |

### Não usados — importante saber antes de continuar

Nenhum destes comandos foi executado nesta sessão. Eles apareceram **só como rótulo de
comando sugerido** dentro dos relatórios de crítica (ex.: "Suggested command: `$impeccable
harden`" ao lado de um achado específico) — isso é uma indicação de qual comando
*resolveria* aquele achado, não uma execução real:

- `$impeccable polish`
- `$impeccable animate`
- `$impeccable delight`
- `$impeccable overdrive`
- `$impeccable colorize`
- `$impeccable typeset`
- `$impeccable layout`, `$impeccable clarify`, `$impeccable harden`, `$impeccable audit`, `$impeccable adapt`, `$impeccable distill`, `$impeccable onboard`
- `$impeccable live`, `$impeccable hooks` (mencionados em conversa, nunca ativados)

Nota sobre nomenclatura: o dono do produto usou o termo **"Colortype"** em conversa — isso
não é um comando real do Impeccable. O mapeamento correto é **dois** comandos distintos:
`$impeccable colorize` (cor estratégica) e `$impeccable typeset` (hierarquia tipográfica).
Ver seção 7 para onde cada um se aplica.

**Por que nenhum desses foi rodado**: todos eles (`polish`, `animate`, `delight`,
`overdrive`, `colorize`, `typeset`, etc.) operam sobre uma **implementação real e
funcional** — o próprio `polish.md` do skill diz para "usar a feature você mesmo... andar
pelo caminho completo com mouse, teclado, toque" e só declarar pronto quando a feature
"estiver funcionalmente completa". Hoje não existe nenhuma linha do que foi aprovado
dentro do `frontend/` real — está tudo nos mockups HTML desta pasta. Rodar esses comandos
antes da implementação não teria alvo real pra inspecionar.

## 4. As 6 superfícies e suas críticas

Cada crítica rodou como dois sub-agentes isolados (revisão de design + detector/evidência
de navegador), pontuou as 10 heurísticas de Nielsen, e terminou com uma lista de
Problemas / Sugestões / Aformoseamento. O corpo completo de cada uma está gravado em
`.impeccable/critique/`:

| # | Superfície | Alvo (arquivo) | Snapshot da crítica | Nota | P0 | P1 |
|---|---|---|---|---|---|---|
| 1 | SaaS interno (painel da fazenda) | `frontend/app/page.tsx` | `.impeccable/critique/2026-09-12T19-41-52Z__frontend-app-page-tsx.md` | 27/40 | 1 | 2 |
| 2 | Página pública (login/marketing) | `frontend/app/login/page.tsx` | `.impeccable/critique/2026-09-12T21-17-55Z__frontend-app-login-page-tsx.md` | 20/32 | 2 | 2 |
| 3 | Painel CowData (cockpit do operador SaaS) | `frontend/app/painel-cowdata/page.tsx` | `.impeccable/critique/2026-09-12T22-13-58Z__frontend-app-painel-cowdata-page-tsx.md` | 25/40 | 1 | 1 |
| 4 | App mobile de campo | `frontend/app/app/page.tsx` | `.impeccable/critique/2026-09-12T22-28-41Z__frontend-app-app-page-tsx.md` | 34/40 | 1 | 1 |
| 5 | Blog (Milk News) | `frontend/app/news/page.tsx` | `.impeccable/critique/2026-09-12T22-40-26Z__frontend-app-news-page-tsx.md` | 17/32 | 1 | 1 |
| 6 | Painel do Contador | `frontend/app/contador/page.tsx` | `.impeccable/critique/2026-09-12T22-57-35Z__frontend-app-contador-page-tsx.md` | 22/40 | 1 | 1 |

## 5. Os mockups aprovados — a especificação exata a implementar

Todos os 13 arquivos abaixo estão nesta mesma pasta (`docs/agents/design-mockups/`),
**auto-contidos** (abrem direto no navegador, sem servidor) — são a especificação visual
exata a reproduzir. Cada um também foi publicado como Artifact (link ao lado, útil pra
comparar lado a lado ou testar interações, mas o arquivo local é a fonte durável — o link
pode expirar ou ficar inacessível pra outra ferramenta).

Convenção usada em todos: um toggle **Atual / Proposta** (ou 3 estados quando fazia
sentido) no topo da página — o estado "Proposta" é o que deve virar código real. A barra
cinza no topo de cada arquivo ("REVISÃO DE PROPOSTA...") é *chrome de revisão*, não faz
parte do produto — não implementar.

### Frente 1 — SaaS interno (`frontend/app/page.tsx` e componentes)

| Arquivo local | Artifact | O que implementar |
|---|---|---|
| `hoje-primeiro.html` | [Hoje Primeiro](https://claude.ai/code/artifact/e07b6e5d-4ceb-4c1d-a8da-178db9180bca) | Promover um módulo **"Hoje"** (agenda/alertas com severidade real: crítico/atenção/rotina/feito) acima da grade de KPIs. Reagrupar os KPIs por assunto (Rebanho/Reprodução/Produção/Financeiro) com peso visual menor. Perda financeira escala pra vermelho de verdade (hoje fica em âmbar). Inclui setas de tendência (▲▼) e um selo "META" discreto — isso já antecipa o item de `meta-batida.html`, ver abaixo. |
| `entrada-acessivel.html` | [Entrada Acessível](https://claude.ai/code/artifact/ea5ceb91-719c-46a5-9b30-4fc9a21b812c) | Em `frontend/app/login/page.tsx` (2 campos) e `frontend/components/login/MilkPriceExplainer.tsx` (6 campos): adicionar `htmlFor`/`id` ligando `<label>` a `<input>` — zero mudança visual. Recalibrar as duas cores de ajuste do simulador (vermelho/verde) que hoje falham contraste (2.2:1 e 4.4:1) contra o fundo fixo `#14385A` do hero — usar `#FF8A80` (5.3:1) e `#6BC79A` (5.9:1) no lugar de `--red`/`--green-light` **só nesse contexto de fundo escuro**. Nota lateral: auditar também o token `--alert-fg` (`#E07070`), que no mesmo fundo calcula ~3.9:1 (abaixo do piso). |
| `por-secao.html` | [Por Seção](https://claude.ai/code/artifact/d585c63e-a792-4b99-8082-6e564becf98a) | Substituir o texto solto "Carregando painel…" por esqueletos com o formato real de cada seção (Hoje/Indicadores/Financeiro). Trocar o banner de erro genérico por erro **por seção**, nomeando o endpoint que falhou, com botão de retry. Ao concluir o carregamento, entrada em fade + leve deslocamento vertical, escalonada por seção (nunca elevação/sombra — ver DESIGN.md No-Lift Rule). Respeitar `prefers-reduced-motion`. |
| `meta-batida.html` | [Meta Batida](https://claude.ai/code/artifact/6bfcf519-e3ec-4a81-af03-90156d309a9c) | Adicionar sparkline (10 dias) + delta (▲▼) a cada KPI, com linha pontilhada de meta onde existir. O card "Sanidade" vira um streak ("N dias sem baixa") com selo dourado "META". **Variante Ousada, aprovada explicitamente pelo dono do produto**: o card de meta batida ganha, só nele, uma exceção pontual e documentada às regras No-Lift e sem-gradiente — elevação de 3px + sombra dourada + um brilho (sheen) que passa uma vez ao carregar/recarregar. Essa exceção deve ser marcada com um comentário no código citando este documento, não generalizada pra outros componentes. |

### Frente 2 — Página pública (`frontend/app/login/page.tsx` e componentes)

| Arquivo local | Artifact | O que implementar |
|---|---|---|
| `o-motor-nao-o-painel.html` | [O Motor, Não o Painel](https://claude.ai/code/artifact/e6524cce-c47b-42d3-9e6f-47077ee91f9e) | Adicionar um banner novo em `frontend/components/login/banners.ts` citando o motor de regras real (gestação por raça, IATF, BST) — usar o texto exato do mockup ou equivalente aprovado pelo dono. Remover `transform: translateY(-3px)` e `box-shadow` do hover em `frontend/components/login/FeatureShowcase.tsx:104-107` (deixar só a mudança de `border-color`) — mesmo tratamento se `BannerGrid.tsx` tiver o mesmo padrão. Mudar a grade "Todos os temas do sistema" de 4 para 3 colunas (9 itens reais cabem exatos em 3×3). |
| `prova-e-acabamento.html` | [Prova e Acabamento](https://claude.ai/code/artifact/4cdf7b3c-11c7-4f6a-b018-f3e10ae8a83c) | Trocar o "side-tab" (borda esquerda sólida) dos 5 cards de `MilkPriceExplainer.tsx` (linha ~287) por um selo numerado. Adicionar `min`/validação nos 6 campos numéricos do simulador — bloquear/zerar a saída com entrada inválida e mostrar mensagem inline. Aumentar as setas do carrossel (`BannerCarousel.tsx`) de 34px pra 44px. Trocar o rodapé de uma linha por um rodapé com prova concreta ("27+ testes automatizados...", dados reais da fazenda) + links (Sobre/Contato/Termos). |
| — (ajuste trivial, sem mockup) | — | O callout do Milk News (`MilkNewsCallout` em `frontend/app/login/page.tsx`) usa o gradiente do token `--vinho`, que renderiza navy na paleta ativa — conferir se isso é intencional; se não, trocar pro token de paleta correto. |

### Frente 3 — Painel CowData (`frontend/app/painel-cowdata/`)

| Arquivo local | Artifact | O que implementar |
|---|---|---|
| `confirmar-antes-de-cortar.html` | [Confirmar Antes de Cortar](https://claude.ai/code/artifact/268736b8-cfb9-42f1-8fa8-f1c72a4699cf) | No Cockpit (`page.tsx`), o card "Aguardando aprovação" vira link real pra uma visão filtrada de `assinaturas/page.tsx`. A tabela de Assinaturas passa a ordenar pendentes primeiro. Ação de suspender contrato abre modal de confirmação nomeando a fazenda; ação de aprovar mostra um toast de sucesso. |
| `painel-consistente.html` | [Painel Consistente](https://claude.ai/code/artifact/13270d49-c639-4893-a05e-545354a8f45c) | Trocar raio hardcoded (`10px`/`8px`) por `var(--r-sm)` em `usuarios/page.tsx` e `parametros/page.tsx`. Reservar dourado só pro botão "Salvar"/confirmar — aba ativa e links comuns passam a usar destaque neutro. Status de contrato (Ativo/Suspenso) ganha ícone além da cor. Substituir `e.message` cru por mensagem traduzida + link de retry. Substituir o card "Atalhos" (que duplica a sidebar) por uma fila unificada juntando contratos pendentes + sessões de suporte pendentes. |

### Frente 4 — App mobile de campo (`frontend/app/app/`)

| Arquivo local | Artifact | O que implementar |
|---|---|---|
| `lancar-rapido.html` | [Lançar Rápido](https://claude.ai/code/artifact/24e12fcb-3106-4878-9409-3058e7d2f7f4) | Em `frontend/app/app/lancar/page.tsx`: reorganizar a grade de ações — promover as 2-3 mais frequentes (Produção, Sanidade, Reprodutivo) em blocos maiores no topo; demais ações rotineiras (Movimentar, Estoque, Financeiro) em linha secundária menor; "Baixar animal" e "Excluir lançamento" isoladas numa "zona de risco" com borda tracejada vermelha. Em `frontend/app/app/menu/page.tsx`: adicionar subtítulo em linguagem simples abaixo de cada sigla técnica (IATF, PEV, BST, etc.). |
| `acabamento-de-campo.html` | [Acabamento de Campo](https://claude.ai/code/artifact/cc0cac46-9019-44c8-b415-5b1c1710db85) | Persistir rascunho de formulário em andamento no mesmo mecanismo de fila offline já existente pros envios; mostrar aviso "rascunho salvo" quando houver conteúdo pendente. Corrigir a sobreposição das setas do carrossel de login em largura mobile (mesmo componente do item da Frente 2, mas confirmar em ~390-400px). Adicionar uma variante de alto contraste (preenchimento sólido, não só brilho) do estado "feito" (`.mob-check.feito`) pra uso sob sol forte — pode ser condicional a uma preferência do usuário ou sempre ativa, decisão do time. |

### Frente 5 — Blog / Milk News (`frontend/app/news/`)

| Arquivo local | Artifact | O que implementar |
|---|---|---|
| `a-materia-completa.html` | [A Matéria Completa](https://claude.ai/code/artifact/2027843a-813e-4b17-9517-d4d1d865b649) | **Criar a rota que hoje não existe**: `frontend/app/news/[slug]/page.tsx`, com corpo completo da matéria, coluna de leitura (~65-75ch, corpo maior, entrelinha generosa), assinatura visível (autor/revisor + data), fontes citadas, e uma matéria relacionada ao final. Em `frontend/app/news/page.tsx`, toda manchete vira `<Link>` pra essa rota (hoje só a matéria em destaque tem qualquer forma de expansão). |
| `milk-news-editorial.html` | [Milk News, Editorial](https://claude.ai/code/artifact/62de2c73-57cd-4da9-aa2f-67e48d9c13ae) | Trocar o erro cru ("Failed to fetch") por mensagem amigável + botão "Tentar novamente". Dar ao Milk News uma paleta de cor de seção própria, distinta das 8 cores fixas de categoria do produto (hoje reaproveita `--cat-financeiro`/`--cat-sanidade` com outro significado). Estado vazio ilustrado em vez de texto solto. Remover `text-transform: uppercase` do rótulo "Fontes que acompanhamos todo dia" (achado do detector: `call-caps-body`). |

### Frente 6 — Painel do Contador (`frontend/app/contador/`)

| Arquivo local | Artifact | O que implementar |
|---|---|---|
| `primeira-visita.html` | [Primeira Visita](https://claude.ai/code/artifact/f4f8ad7f-7b7a-43ca-9fe4-62155662d450) | Separar visualmente a aba "Ações extraordinárias" (a única que escreve dado) das outras 8 com um divisor + cor de aviso. Adicionar um cabeçalho contextual de uma linha por aba, explicando o que é e de onde vem o número (especialmente RMCA e GTA, que não são termos contábeis padrão). |
| — (pendente, sem mockup ainda) | — | Validação de intervalo de data, fechar popover de anexo ao clicar fora, mensagem de erro amigável, estado vazio menos terse. O dono do produto disse explicitamente que decide depois se quer mockup pra isso — **não implementar por conta própria sem confirmar**; se for tocar nessa tela, perguntar primeiro. |

## 5A. Sistemas de tema por superfície — leia antes de tocar em cor

O produto tem **três mecanismos de tema diferentes e independentes**, não um só. Isso foi
verificado no código real depois da sessão de design (não estava explícito nos mockups
originais) e corrige dois pontos específicos abaixo.

| Superfície | Modos reais | Mecanismo | Padrão |
|---|---|---|---|
| Site (SaaS interno + página pública) | claro / misto / escuro | `data-theme` no `<html>`, escolha manual do usuário salva em `localStorage`, já implementado em `globals.css` | claro |
| App mobile (`/app/*`) | claro / escuro (misto cai em claro) | mesmo atributo `data-theme`, mas o `.mob` só reage a `escuro`, ignora `misto` | claro |
| Painel CowData (`/painel-cowdata`) | escuro / misto / claro | **mecanismo próprio**, via `usePainelCowDataTema()`/`usePainelCowDataCor()` em `frontend/lib/painelCowDataTema.tsx` — objeto de cor por React Context + `localStorage` próprio (`tema_painel_cowdata`), não usa `data-theme` | **escuro** (pedido explícito do dono do produto) |
| Painel do Contador (`/contador`) | **um único, fixo** | `CORES_CONTADOR` em `frontend/app/contador/layout.tsx` — constante, sem seletor, deliberadamente fora dos dois sistemas acima | não se aplica |

### O que isso muda nos mockups desta pasta

- **Frentes 1, 2, 4 e 5** (Site e App mobile): nenhuma mudança de conteúdo. Os mockups usam
  os mesmos nomes de token do produto (`--vinho`, `--dourado`, `--bg`, `--cat-*` etc.). O
  bloco `:root`/`@media (prefers-color-scheme: dark)`/`:root[data-theme="dark"]` que
  aparece no `<style>` de cada arquivo HTML é **andaime só para o mockup rodar sozinho
  fora do app** — na implementação real, **não copiar esses valores**; os componentes
  devem apenas consumir `var(--vinho)` etc. e deixar o `globals.css` já existente resolver
  claro/misto/escuro, exatamente como o resto do produto já faz.

- **Frente 3 (Painel CowData) — correção real, não só nota.** `confirmar-antes-de-cortar.html`
  e `painel-consistente.html` foram desenhados com uma paleta `--op-*` **inventada por mim**,
  com claro como padrão e escuro só via preferência do sistema operacional. Isso está
  **errado nos dois sentidos**: o padrão real é escuro, e a troca é um seletor de 3 opções
  dentro do próprio painel (não a preferência do SO). **Ao implementar, ignore os valores
  hex desses dois mockups** e use `usePainelCowDataCor()` para pegar `cor.bg`, `cor.painel`,
  `cor.cartao`, `cor.borda`, `cor.texto`, `cor.mudo`, `cor.dourado`, `cor.verde`,
  `cor.vermelho` de verdade — a estrutura/layout/hierarquia propostas nos mockups continuam
  válidas, só a fonte da cor muda. Os valores reais das 3 paletas estão em `PALETAS` no
  mesmo arquivo (`painelCowDataTema.tsx`), reproduzidos aqui pra não precisar abrir o
  arquivo:

  | | escuro (padrão) | misto | claro |
  |---|---|---|---|
  | `bg` | `#1A2028` | `#262C34` | `#F4F6F8` |
  | `painel` | `#212832` | `#2E3540` | `#FFFFFF` |
  | `cartao` | `#262E39` | `#363E4A` | `#F1F3F6` |
  | `borda` | `#39424F` | `#4B5563` | `#DDE2E8` |
  | `texto` | `#F1F3F5` | `#F1F3F5` | `#1F2530` |
  | `mudo` | `#9CA6B4` | `#AEB6C2` | `#5B6472` |
  | `dourado` | `#6B7F99` | `#7C93AD` | `#3D5A80` |
  | `verde` | `#8faa7b` | `#8faa7b` | `#3F6B31` |
  | `vermelho` | `#b5544a` | `#c06860` | `#A23B32` |

- **Frente 6 (Painel do Contador) — correção menor.** `primeira-visita.html` acertou o
  instinto certo (identidade única e fixa, sem seletor de tema — o painel do contador
  nunca alterna) mas usou hex aproximados e a fonte serifada errada (Google Fonts
  "Source Serif 4"). Ao implementar, usar `CORES_CONTADOR` de
  `frontend/app/contador/layout.tsx` (`bg:#1A2028`, `painel:#212832`,
  `painelAlt:#262E39`, `borda:#39424F`, `bordaClara:#4B5563`, `texto:#F1F3F5`,
  `mudo:#9CA6B4`, `cobre:#6B7F99`, `cobreClaro:#8FA0B5`, `positivo:#8faa7b`,
  `negativo:#b5544a`) e o stack de fonte real: `'Iowan Old Style', 'Palatino Linotype',
  Georgia, serif` (não é um Google Font — são fontes do sistema, sem `<link>` a adicionar).
  A separação visual da aba de risco e o cabeçalho contextual por aba (o conteúdo real da
  proposta) continuam válidos como estão.

## 6. Regras que valem para TODA a implementação

1. **Refinamento, não redesign.** Preservar tudo que os mockups não mencionam. Não
   "aproveitar" a implementação pra mexer em mais nada.
2. **Reusar os tokens reais de `frontend/app/globals.css`** — todo hex usado nos mockups
   já existe como `var(--...)` no projeto (marinho, dourado, cores de categoria etc.). Não
   duplicar valores como literais quando o token já existe.
3. **A única exceção deliberada às regras do `DESIGN.md`** é o card de meta batida em
   `meta-batida.html` (variante Ousada) — qualquer outra tentação de adicionar
   elevação/gradiente/sombra fora do padrão deve ser tratada como bug, não como liberdade
   criativa.
4. **Testar todos os modos de tema da superfície tocada** — ver seção 5A pra saber qual
   sistema vale em cada frente (o site tem 3 modos + paleta vinho/verde/azul; o app móvel
   tem 2; o Painel CowData tem seu próprio seletor de 3, com escuro como padrão; o Painel
   do Contador não tem seletor nenhum, é uma paleta fixa). Não assuma que "claro/escuro"
   cobre todas as superfícies.
5. **Respeitar `prefers-reduced-motion`** em toda animação nova.
6. **Onde a proposta tem toggle Atual/Proposta**, implementar apenas o estado "Proposta" —
   o "Atual" nos mockups existe só pra comparação, não é uma opção A/B a manter no produto.
7. Se algo no mockup conflitar com a estrutura real do componente de um jeito que este
   documento não previu, **parar e perguntar** antes de improvisar uma solução diferente.

## 7. Depois da primeira implementação — plano dos próximos passos

Esta é a sequência recomendada, na ordem em que o dono do produto vai querer olhar:

1. **Implementar as 6 frentes**, na ordem 1→6 já usada nesta sessão (SaaS interno →
   página pública → Painel CowData → App mobile → Blog → Painel do Contador). Verificar
   cada frente (visual + funcional) antes de seguir pra próxima.
2. **`$impeccable polish` por frente**, depois que a frente estiver implementada. Esse
   comando lê automaticamente o snapshot de crítica já salvo (via
   `impeccable critique-storage latest "<alvo>" --json`), absorve os P0/P1 que restarem, e
   fecha o snapshot ao final (`impeccable critique-storage close "<alvo>" "<snapshot_file>"`).
   Não é preciso repassar o conteúdo da crítica manualmente — o comando já sabe onde
   procurar.
3. **`$impeccable colorize`** — usar especificamente onde a crítica já apontou problema de
   cor: o contraste vermelho/verde da Frente 1/2 (se `entrada-acessivel.html` não cobrir
   tudo) e a disciplina do dourado no Painel CowData (Frente 3, achado P3 — dourado usado
   como destaque genérico em vez de só confirmar ação).
4. **`$impeccable typeset`** — aplicar principalmente na Frente 5 (Blog), no artigo criado
   a partir de `a-materia-completa.html`: a crítica original (P3) pediu uma coluna de
   leitura de verdade (65-75ch, corpo maior, entrelinha generosa) — o mockup já mostra a
   direção, `typeset` formaliza a implementação.
5. **`$impeccable animate`** — só depois que a base estiver implementada e o `polish`
   tiver rodado. Focar primeiro na Frente 1 (o esqueleto de carregamento de
   `por-secao.html` e o brilho de `meta-batida.html` já são a tese de movimento; `animate`
   formaliza timing/easing/reduced-motion conforme a disciplina do comando).
6. **`$impeccable delight`** — pra ir além do que já foi desenhado, se o dono do produto
   quiser mais um momento de encantamento em alguma frente específica depois de ver tudo
   implementado.
7. **`$impeccable overdrive`** — só se o dono do produto pedir explicitamente mais
   ambição além da variante Ousada já aprovada em `meta-batida.html`. Não acionar por
   iniciativa própria.

Nenhum desses comandos deve rodar pulando a etapa 1 (implementação) — todos dependem de
código real funcionando pra ter o que inspecionar.

---

## 8. Prompt pronto para o agente de implementação

Copie o bloco abaixo (entre as linhas de `---`) e envie como primeira mensagem para o
agente (Claude Code no terminal, rodando com `deepseek-v4-pro`):

---

Você vai implementar, no código real do frontend do CowData, um conjunto de propostas de
UI/UX já aprovadas pelo dono do produto. Nada disso é uma decisão sua — é reprodução fiel
de um trabalho de design já fechado.

Leia, nesta ordem, antes de escrever qualquer código:
1. `docs/agents/design-implementation.md` — este é o documento mestre. Ele lista as 6
   frentes, os 13 mockups aprovados (em `docs/agents/design-mockups/*.html`, abra cada um
   no navegador pra ver exatamente o que reproduzir), quais comandos do Impeccable já
   rodaram nesta sessão e quais não rodaram, e o plano dos próximos passos.
2. `PRODUCT.md` e `DESIGN.md` (raiz do repo) — contexto de produto e o sistema de design
   ("The Institutional Ledger") cujos tokens você vai reutilizar.
3. Os 6 snapshots de crítica em `.impeccable/critique/` (caminhos exatos na seção 4 do
   documento mestre) — cada um tem a lista completa de heurísticas, personas e achados
   que motivaram os mockups.
4. **Seção 5A do documento mestre, com atenção redobrada.** O produto tem 3 sistemas de
   tema diferentes e independentes (site, Painel CowData, Painel do Contador — cada um do
   seu jeito). Os mockups das Frentes 3 e 6 usam cor **aproximada/inventada**, não a real —
   a seção 5A já traz os valores reais e diz exatamente o que corrigir em cada um. Não
   copiar os hex desses dois mockups sem passar por essa correção primeiro.

Depois de ler tudo:
- Implemente as 6 frentes **na ordem 1→6** descrita na seção 5 do documento mestre.
  Para cada frente, a tabela já diz qual arquivo real editar e o que exatamente mudar —
  siga a tabela à risca, não invente escopo adicional.
- Reproduza fielmente o estado "Proposta" de cada mockup (não o "Atual", que é só
  comparação). A barra cinza "REVISÃO DE PROPOSTA" no topo de cada HTML é ferramenta de
  revisão, não faz parte do produto.
- Use os tokens reais já existentes em `frontend/app/globals.css` — não invente valores
  novos quando um token já cobre o mesmo papel.
- A única exceção deliberada às regras do próprio `DESIGN.md` (No-Lift, sem gradiente) é o
  card de meta batida da Frente 1 (`meta-batida.html`, variante Ousada) — já aprovada
  explicitamente. Não estenda essa liberdade a nenhum outro componente.
- Depois de implementar cada frente, rode o app localmente (`npm run dev` em `frontend/`)
  e confira visualmente todos os modos de tema **daquela superfície específica** (seção
  5A diz quais valem onde — não é sempre "claro/escuro"), e — nas frentes 1, 2 e 4 —
  também largura mobile. Respeite `prefers-reduced-motion` em qualquer animação nova.
- Ao terminar uma frente, rode `/impeccable polish` nela (ou peça pro usuário rodar, se
  seu ambiente não tiver a skill Impeccable disponível) antes de seguir pra próxima —
  esse comando já sabe puxar o snapshot de crítica salvo e fechar o que for resolvido.
- Se algo no mockup não bater com a estrutura real do componente de um jeito que o
  documento mestre não previu, **pare e pergunte** em vez de decidir uma solução
  diferente por conta própria.
- Dois itens ficaram deliberadamente sem mockup ainda (o ajuste do gradiente do Milk News
  na Frente 2, e o polimento de erro/vazio/popover da Frente 6) — não implemente esses
  dois por conta própria; confirme com o usuário primeiro.

Ao final de cada frente, resuma o que foi alterado (arquivos tocados, o que mudou) antes
de seguir para a próxima.

---

## 9. Status de implementação (atualização de 2026-09-13)

**As 6 frentes foram implementadas de verdade**, nesta mesma sessão de Claude Code — não
pelo agente `deepseek-v4-pro` previsto na seção 8 (o dono do produto decidiu implementar
com o mesmo agente que fez o design, em vez de passar o bastão). O prompt da seção 8 fica
mantido no documento como registro histórico e para o caso de uma frente futura ser
delegada a outro agente, mas não reflete mais o que realmente aconteceu.

Duas peças ficaram propositalmente pendentes ao final da primeira rodada de implementação
e foram resolvidas numa segunda passada, a pedido explícito do dono do produto — registradas
aqui porque a técnica usada é reaproveitável e não deve ser redescoberta:

### 9.1 Rascunho salvo nos formulários de Lançar — concluído

Hook `useRascunho<T>(chave, valorInicial)` em `frontend/components/mobile/lancar/comum.tsx`:
persiste o estado do formulário em `localStorage` a cada mudança, com um componente
`<RascunhoAviso>` ("💾 Rascunho salvo") reaproveitado em todo lugar que o usa. Aceita tanto
um valor direto quanto uma função atualizadora `(atual: T) => T`, igual ao `setState` do
React — isso foi necessário porque vários formulários já chamavam os setters no formato
funcional (`adicionar`/`remover` de listas).

Formulários com rascunho ativo (10 no total, cobrindo os fluxos de maior custo de
re-digitação — seleção de animal/lote, listas de matrizes, quantidades):

- `FormReprodutivo.tsx`: `Inseminacao` (matriz), `Diagnostico` (matrizes selecionadas),
  `Parto` (matriz), `ProtocoloIatf` (matrizes).
- `FormProducao.tsx`: `ControleLeiteiro` (modo/animal/lote/produções).
- `FormSanidade.tsx`: `CurativaForm`, `PreventivoAplicacao`, `PreventivoCalendario`.
- `FormAlimentacao.tsx`: lote/dieta/alimento/quantidade.
- `FormProtocolos.tsx`: `ProtocoloCustomizadoApp` (protocolo/alvo/matriz).

Cada formulário preserva o comportamento original de limpeza pós-envio (alguns campos são
limpos ao salvar com sucesso, outros propositalmente não — ex.: `Parto` e
`ProtocoloCustomizadoApp` mantêm a matriz/protocolo pra permitir lançar em sequência no
mesmo contexto). Não inventar um comportamento de reset uniforme se for tocar nesses
arquivos depois.

**Pendência real, não implementada**: os sub-formulários de Financeiro, Estoque,
Movimentar, Baixar animal e Excluir lançamento (dentro de `LancarTela.tsx`) ainda não têm
`useRascunho` — são lançamentos mais raros/pontuais, priorizados como "menor custo de
perder o rascunho" na primeira rodada. Se o dono do produto quiser cobertura total, é o
mesmo padrão (`useRascunho` + `<RascunhoAviso>`), só falta aplicar.

### 9.2 Sparkline/delta real nos KPIs (vacas em lactação, prenhez, IATF) — concluído

Ficou pendente na primeira entrega porque a única forma óbvia de mostrar tendência exigiria
uma série histórica **inventada** (dados fictícios) — o que eu tinha recusado fazer. A
solução real, sem fabricar nada: os endpoints `/indicadores/` e `/agenda/` (ver
`fetchIndicadores`/`fetchAgenda` em `frontend/lib/api.ts` e
`calcular_indicadores_fazenda(session, fazenda_id, data)` em
`backend/fazenda/api/routers/indicadores.py`) já aceitam um parâmetro `data` opcional e
**recalculam de verdade** os indicadores como estavam naquela data de referência, a partir
dos registros reais do banco — não é cache, não é série simulada.

Em `frontend/app/page.tsx`, o `carregar()` agora também busca `fetchIndicadores`/
`fetchAgenda` com a data de 7 dias atrás (`Promise.allSettled`, não bloqueia o carregamento
principal se falhar) e guarda o resultado em `dAnterior`. Um componente `<Delta>` novo
compara `atual` vs. `anterior` e renderiza ▲/▼ com a diferença real, ligado em: Vacas em
lactação, Fêmeas prenhas, Concepção/serviço, Candidatas IATF, Produção/dia.

**Pendência real, não implementada**: isso é uma comparação **pontual** (hoje vs. 7 dias
atrás), não uma sparkline de série temporal completa — o mockup `meta-batida.html` mostrava
um gráfico de 10 pontos. Existe um caminho real pra isso também (`fetchIndicadoresMensais`
→ `GET /reproducao/indicadores-mensais` → `agregar_mensal()` em
`backend/fazenda/rules/reproducao_analise.py`, que já expõe séries mensais reais de
`taxa_concepcao`/`producao_leite`/`del_medio`), mas não foi implementado nesta rodada —
ficou só o delta pontual, que já resolve o pedido de "não fabricar número" com o menor
esforço real. Se o dono do produto quiser a sparkline completa de verdade, o dado mensal já
existe no backend, só falta consumir.

### 9.3 Outras pendências conhecidas, registradas para não serem esquecidas

- **Retry por seção em `page.tsx`**: a proposta de `por-secao.html` previa retry
  isolado por fonte de dado; a implementação atual do botão "Tentar novamente" ainda
  refaz o `carregar()` inteiro (todas as 5 fontes), não só a que falhou.
- **Painel do Contador**: os itens explicitamente deixados em aberto pelo dono do produto
  (validação de intervalo de data, popover de anexo que não fecha ao clicar fora, mensagem
  de erro amigável, estado vazio menos seco) continuam sem mockup e sem implementação —
  não tocar sem confirmar antes, conforme já registrado na seção 5.
- **Reescrita de mensagem de erro amigável**: aplicada nos pontos previstos nos mockups
  (Cockpit, Assinaturas, Blog); **não** aplicada em 6 telas do Painel CowData
  (`usuarios`, `parametros`, `financeiro`, `cofre` e formulários relacionados) onde as
  mensagens atuais são texto de validação legítimo vindo do backend, fora do escopo dos
  mockups aprovados — decisão deliberada, não descuido.

### 9.4 Merge com `main` (2026-09-13) — decisões que mudam o que está no ar

Entre o início desta sessão e a abertura do PR, `main` recebeu trabalho paralelo e
independente que tocou exatamente as mesmas telas das Frentes 1, 2 e 3 (outra sessão de
design/implementação, não coordenada com esta). O merge do PR #773 precisou reconciliar os
dois lados — registrado aqui porque muda o que efetivamente ficou no ar em relação ao que a
seção 5 descreve:

- **Frente 1 (`app/page.tsx`) — `main` já tinha um redesign próprio da Capa** ("Redesign T1",
  mockup 1b): busca de animal (⌘K), bloco "Hoje" reformulado (tarefas atrasadas/de hoje +
  "Fora do esperado"), grade de 12 KPIs em vez da grade agrupada por seção com cabeçalhos, e
  a página `/` dividida em `Capa()` (logado) vs. `LandingPublica()` (T8, deslogado). Resolução:
  manter a estrutura de `main` (mais completa e já testada) e reaplicar por cima só o que
  esta sessão trouxe de novo — `Delta` (setas de tendência de 7 dias) ligado nos 5 KPIs
  pedidos, os 3 `ErroSecao` por fonte, e o card de meta batida da Sanidade (Ousado, aprovado)
  — este último agora vive como um 7º item no fim da primeira grade de KPIs (antes tinha
  posição própria dentro de uma seção "Rebanho" que não existe mais nessa estrutura). O card
  "Eficiência Reprodutiva" (medidores/gauges + tabela de benchmark expansível) que existia
  nesta sessão foi **removido** — `main` já tinha migrado esse conteúdo para a página
  `/indicadores` antes do merge; manter os dois seria duplicar a mesma informação em dois
  lugares.
- **Frente 2 (`app/login/page.tsx`) — `main` já tinha o próprio redesign da página pública**
  ("Redesign T7: Login enxuto" + "T8 — Landing pública vira `/`"): a página de login virou só
  o cartão de entrar, e todo o conteúdo de marketing (carrossel, showcase de recursos, grid de
  banners, simulador de preço, callout do Milk News) saiu de `login/page.tsx` e hoje vive em
  `components/landing/LandingPublica.tsx`, com conteúdo **próprio**, escrito do zero — **não**
  reaproveita os componentes que esta sessão corrigiu (`BannerCarousel.tsx`,
  `FeatureShowcase.tsx`, `BannerGrid.tsx`, `MilkPriceExplainer.tsx`, `banners.ts`). Esses
  arquivos continuam no repo com as correções desta sessão (contraste, No-Lift, tamanho das
  setas, validação do simulador) mas **não são mais renderizados em lugar nenhum** — ficaram
  órfãos. O que sobreviveu e foi reaplicado: os `id`/`htmlFor` de acessibilidade nos campos
  Usuário/Senha do cartão de login (compatível com a estrutura nova de `main`). **Decisão
  pendente do dono do produto**: apagar os componentes órfãos, ou portar as mesmas correções
  para dentro de `LandingPublica.tsx` (que é quem precisa delas de verdade agora).
- **Frente 3 (`app/painel-cowdata/page.tsx`) — `main` também adicionou sparklines/tendência**
  nos cartões do Cockpit (`registrarLeituraKpisCowData`/`calcularTendencia`, armazenando
  leituras reais ao longo do tempo — mesmo espírito do `Delta` desta sessão, implementado de
  forma independente) e uma fila de aprovação rica com botão "Aprovar" inline. Resolução:
  mantida a fila rica de `main` + os sparklines; a fila de suporte pendente desta sessão
  (`fetchPedidosRecentesCofre`) virou uma seção própria "Suporte pendente" ao lado da fila de
  aprovação, em vez do card "Hoje" unificado original — o card "Atalhos" (que esta sessão
  queria remover por duplicar a sidebar) foi removido, como planejado.

Nenhuma dessas reconciliações foi testada via `$impeccable polish`/`critique` de novo — vale
uma passada nessas 3 telas antes de considerar as Frentes 1–3 definitivamente fechadas.

Nenhuma dessas três pendências bloqueia o merge desta rodada — são candidatas naturais para
uma passada futura de `$impeccable polish` ou `$impeccable harden` por frente, conforme o
plano da seção 7.

---
