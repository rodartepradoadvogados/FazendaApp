# Agenda — Planejador B (usuário-primeiro / design das telas)

> Rodada de 29/09/2026. Só leitura no repo. Base: `00-PEDIDO-DO-DONO.md` (fonte da verdade), `02-proposta.md` §5 (Agenda anterior), mapa da Agenda real (`page.tsx`, 2816 linhas), mockup `mockups/agenda.html` (identidade que o dono aprovou) e `DADOS-CANONICOS.md` (números idênticos nos dois mockups).
> Unidade de medida: px de CSS. "Dobra" = altura útil da janela (sem a barra de revisão do mockup, que não é do produto).

---

## 0. O problema, em uma frase (na voz do dono)

Os cards de cima (Atrasadas, Hoje, Próximos 7 dias e, na Agenda real, os 8 KPIs de Reprodução, Sanidade e Geral) **ocupam o espaço do que realmente interessa**. No mockup atual, medido em 1440x900, a primeira tarefa só começa em y=437 e cabem 1,5 tarefa acima da dobra. A Agenda real está pior: a lista "Hoje" começa cerca de 3 telas abaixo.

Solução pedida: **separar por intenção**. Quem está no dia a dia quer uma lista. Quem quer planejar quer ver o futuro em cards. São duas telas com o mesmo nome e dois usos.

---

## 1. Conceito das 2 sub-abas

### 1.1 Nomes (propostos)

| Sub-aba | Nome | Alternativas descartadas | Por quê |
|---|---|---|---|
| 1 | **Dia a dia** | "Lista", "Operação", "Tarefas" | O dono chamou de "dia a dia". É o que o vaqueiro e o gestor dizem na fazenda. "Lista" descreve a forma, não a intenção, e a aba também tem calendário. |
| 2 | **Painel** | "Planejamento", "Visão geral", "Indicadores" | Curto, cabe em 390 px, e o dono já falou "cards na tela para verificar o futuro". "Planejamento" conflita com "cronograma"/"protocolo" (outros assuntos deste projeto). "Indicadores" soa a relatório. |

Na frase de apoio (tooltip / subtítulo pequeno): **Dia a dia** = "o que fazer hoje e nos próximos dias"; **Painel** = "como está o rebanho e o que vem pela frente".

Recomendação: usar **"Painel"**. Se o dono preferir um nome que diga "futuro", a segunda opção é **"Panorama"** (vira decisão na seção 7, A1).

### 1.2 Posição e forma

- Ficam **no topo da página**, logo abaixo do título e da linha de ações, como **abas sublinhadas** (texto + filete de 3 px em dourado na ativa), não como botões grandes. Altura 44 px (alvo ≥44).
- São abas **da Agenda** (dentro do item de menu "Agenda"), não itens novos na Sidebar.
- Cada aba mostra ao lado do nome um **selo de contagem discreto** (12 px, texto + ícone, não só cor):
  - **Dia a dia** ⚠ 4 (atrasadas) — some quando é 0.
  - **Painel** ● 2 (alertas que exigem decisão: estoque e pendências de gestão) — some quando é 0.
  Isso substitui a necessidade de os cards ficarem no topo do Dia a dia.

### 1.3 Comportamento

| Regra | Definição |
|---|---|
| URL | `/agenda?aba=dia` e `/agenda?aba=painel`. Demais parâmetros vivem na mesma URL: `&visao=lista\|semana\|mes`, `&data=2026-09-29`, `&cat=...`, `&horizonte=7\|30\|60\|90`, `&gaveta=candidatas_iatf`, `&tarefa=ID`. F5 mantém tudo; link enviado por WhatsApp abre no mesmo lugar. |
| Entrada padrão | **Dia a dia** sempre que o usuário chega sem `?aba=` (menu, capa, sino, e-mail). |
| Lembrar a última usada | **Não** como padrão de entrada (o dono disse "gerencial ao extremo" para o dia a dia; abrir no Painel porque ontem ele estava lá é surpresa). **Lembrar a última visão dentro da aba** (Lista/Semana/Mês e horizonte 7/30/60/90) em `localStorage` por fazenda + usuário, com try/catch. Sugestão mais fina no A2. |
| Troca de aba | Sem recarregar dados já carregados; sem skeleton na volta; mantém rolagem de cada aba. |
| Deep-links de entrada | O sino/notificação de estoque abre `?aba=painel&gaveta=estoque`; "atrasada" abre `?aba=dia`; sugestão de movimentação mantém `?abrir_sugestao=`. |
| Teclado | `1` = Dia a dia, `2` = Painel (fora de campo de texto); setas ←/→ nas abas (padrão WAI-ARIA `tablist`). |
| Atalho entre abas | No Dia a dia: link fino **"Ver painel ›"**. No Painel: **"‹ Voltar ao dia a dia"**. |

---

## 2. Sub-aba 1 · Dia a dia

### 2.1 Princípios

1. **Só lista e calendário.** Nada de cards de indicador. Números aparecem em **uma linha fina de texto**.
2. **Uma ação primária por linha**: `Feito` (ou `Aplicar` quando a tarefa é aplicação preventiva, ver 2.6).
3. **Atrasadas moram dentro do bloco de Hoje** (grupo no topo, com filete vermelho + ícone + "há N dias"), não num card separado.
4. **Detalhe em gaveta** (direita no desktop, folha inferior no mobile). Nada de painel abrindo no meio da lista.
5. **Nenhuma lista de animais em janela** aparece aqui. Só o agendamento no dia (regra do dono).
6. **Primeira renderização sem atraso artificial**: dados de exemplo do mockup são síncronos; o skeleton só existe na tela de "Recarregar" real (>400 ms de rede) e nunca na 1ª carga do mockup.

### 2.2 Anatomia (de cima para baixo)

| # | Zona | Altura desktop | Altura mobile | Conteúdo |
|---|---|---|---|---|
| 1 | **Cabeçalho 1 linha** | 56 | 52 | `Agenda` (h1 24/22 px) · "ter, 29/09" · à direita **+ Nova tarefa** (primário marinho, 44 px) · **Exportar** (secundário; no mobile vira ícone dentro do menu ⋯) · "Atualizado 14:05" (só desktop, 13 px muted) |
| 2 | **Sub-abas** | 44 | 44 | `Dia a dia` (ativa) · `Painel` |
| 3 | **Barra de controles** (1 linha) | 52 | 48 | Alternador `Lista \| Semana \| Mês` (segmentado, 44 px) · `‹ Hoje ›` · chips de categoria (Reprodução, Sanidade, Produção, Gestão, Atividades; multi-seleção, ícone + texto) · busca (nº do animal, lote, tarefa) · no mobile: alternador + botão **Filtros** (44x44) |
| 4 | **Linha fina de contagens** | 32 | 28 | Texto de 14 px, sem caixa: `4 atrasadas · 15 de hoje · 20 nos próximos 7 dias · Ver painel ›`. Cada contagem é link/filtro. Atrasadas em vermelho-escuro **com ícone ⚠ e texto**, nunca só cor. |
| 5 | **Lista** (bloco Hoje, depois Amanhã…) | resto | resto | ver 2.4 |

Total antes da primeira tarefa: **desktop 56+44+52+32 = 184 px + 16 de respiro = 200** (no mockup atual: 437). **Mobile: 52+44+48+28 = 172 px + barra do app 56 = 228.**

### 2.3 Wireframe desktop 1440x900 (Lista, hoje)

Área útil de conteúdo: 1245 px (sidebar 195). Escala: 1 linha ASCII ≈ 12 px.

```
┌ Sidebar ┐┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ CowData ││ Agenda   ter, 29 de setembro de 2026        Atualizado 14:05  [Exportar]  [+ Nova tarefa]   │ 56
│         ││ ────────────────────────────────────────────────────────────────────────────────────────── │
│ Capa    ││  Dia a dia ⚠4 │ Painel ●2                                                                   │ 44
│ Agenda ◄││ ══════════════                                                                              │
│ Lançam. ││ [Lista|Semana|Mês]  ‹ Hoje ›  (Reprod.)(Sanid.)(Produção)(Gestão)(Ativid.)   🔍 Nº, lote…  │ 52
│ Protoc. ││ ⚠ 4 atrasadas · 15 de hoje · 20 nos próximos 7 dias                        Ver painel ›     │ 32
│ …       ││ ────────────────────────────────────────────────────────────────────────────────────────── │ ← y≈200
│         ││ ATRASADAS (4) · dentro de HOJE                                                        ▾    │ 36
│         ││ ▌⚠ Exame TB — reteste · 3 animais · Lote 02 – Média            há 8 dias    [ Feito ] [⋯] │ 68
│         ││ ▌⚠ Pesagem de leite (controle leiteiro)  · Lote 01 · 24 vacas   há 5 dias    [ Feito ] [⋯] │ 68
│         ││ ▌⚠ Clostridioses — dose 2 · Recria 2 · 22 animais · CL-2608 ✓   há 4 dias    [ Aplicar ][⋯]│ 68
│         ││ ▌⚠ Raiva — reforço · Lote 03 – Baixa · 6 animais                há 2 dias    [ Aplicar ][⋯]│ 68
│         ││ ────────────────────────────────────────────────────────────────────────────────────────── │
│         ││ HOJE · 15 tarefas · 0 feitas                                                          ▾    │ 36
│         ││ ▌ Vermifugação · Recria 1 · 20 novilhas · 92 mL IV-2610       14:00   [ Aplicar ] [⋯]     │ 68
│         ││ ▌ IATF Recria 2 — Dia 9 · 12 novilhas · Estron 2 mL, SincroCP     [ Feito ] [⋯]           │ 68
│         ││ ▌ Mastite — Dia 3 · 3 vacas · ceftiofur 15 mL (CF-5510)           [ Feito ] [⋯]           │ 68
│         ││ …                                                                                            │
└─────────┘└───────────────────────────────────────────────────────────────────────────────────────────┘
                                                                          ← dobra em y=900
```

**Medida acima da dobra (1440x900, sem barra de revisão):** 200 px de cabeçalho/controles + 700 px de lista = grupo Atrasadas (36 + 4x68 = 308) + cabeçalho Hoje (36) + **5 linhas de Hoje (5x68 = 340)** = 684 px. Ou seja, **4 atrasadas + 5 tarefas de hoje visíveis, sem rolar**. Comparação: mockup atual = 1,5 tarefa; Agenda real = 0 tarefa.

Se a viewport for 1440x800 (notebook comum com barra do navegador): 4 atrasadas + 3 de hoje. Ainda melhor do que hoje.

### 2.4 A linha de tarefa (componente único)

Altura fixa **68 px** (densidade "confortável"), **56 px** (densidade "compacta", opção do usuário no menu ⋯ do cabeçalho; não é padrão). Nunca abaixo de 56, para manter alvo de 44 px no botão.

```
▌ [ícone cat]  Título (16 px, 600)                        estado/insumo                  [ Feito ]  [⋯]
▌              Para quem · onde · insumo (14 px muted)     chip: ⚠ há 4 dias | ✓ pronto
```

| Coluna | Largura desktop | Conteúdo |
|---|---|---|
| Filete de categoria | 4 px | cor de categoria (fixa do produto). Nunca a única pista: o ícone do tipo e o texto também dizem |
| Ícone do tipo | 32 px | seringa, alvo, balança, gota, cifrão... dentro de quadrado com tinta da categoria |
| Texto | flex | linha 1: nome da tarefa. Linha 2: `para quem · onde · insumo` |
| Estado | 140 px | chip com ícone + texto: `⚠ há 4 dias`, `● hoje 14:00`, `✓ estoque ok`, `⚠ frasco vence 15/10` |
| Ação primária | 104 px | **[ Feito ]** ou **[ Aplicar ]**, 44 px de altura, marinho, sempre visível (sem hover) |
| Menu ⋯ | 44 px | Adiar · Não vou fazer · Ver animais · Abrir origem · Editar (manual) |

Clicar na linha (fora dos botões) abre a **gaveta da tarefa**. Linha inteira é `role="button"` com Enter/Espaço; `F` marca Feito na linha em foco (atalho já existente no mockup).

Tarefas que **não podem ser "Feito"** (contrato `resolucao` da proposta anterior):
- `navegar`: o botão vira `Ir para Dieta ›`, `Abrir pedido ›`, `Lançar pesagem ›`. Continua ocupando o mesmo lugar (1 ação primária).
- `informativo`: sem botão; `[ Entendi ]` discreto que dispensa.
- Nenhuma linha mostra "Feito" para o que o backend recusa.

Feito com toast: a linha sai com transição de 160 ms (respeita `prefers-reduced-motion`), **a lista não é redesenhada**, aparece toast no rodapé (desktop: canto inferior esquerdo; mobile: acima da navegação) **"Feito · Clostridioses — dose 2 · Desfazer"**, 10 s, `aria-live="polite"`. A linha desce para "Concluídos hoje" (grupo recolhido no fim, com contador).

### 2.5 Grupos da lista

1. **Atrasadas** (só aparece se houver; **dentro de Hoje**, primeira seção, filete vermelho + ícone ⚠).
2. **Hoje** (15).
3. **Amanhã** (recolhido: `Amanhã · 6 tarefas ▸`).
4. **Esta semana** (recolhido, chips por dia).
5. **Concluídos hoje** (recolhido, `Desfazer` por linha).

Agrupar por: seletor pequeno **Agrupar: Tarefa · Lote · Categoria** dentro do menu ⋯ do cabeçalho (fica fora do caminho; o padrão é por tarefa, porque é o que a lista "por horário/urgência" pede). Mantém a promessa de "cabeçalho mínimo".

Ordenação dentro do bloco: atrasadas (mais antigas primeiro) → com horário → sem horário por categoria (Reprodução, Sanidade, Produção, Gestão, Atividades).

**Dia fechado** (todas as tarefas de campo feitas): faixa verde de uma linha no topo da lista, `✓ Dia fechado · 15 de 15 feitas` (ícone + texto), total vindo do servidor. Substitui o banner grande.

### 2.6 Como aparece uma aplicação preventiva agendada (regra do dono)

**Só o agendamento no dia.** Nada de "22 animais na janela" como lista de espera; isso mora em Sanidade/Protocolos (o Painel só mostra o número da lista de espera, com link para lá; ver 3.6).

Linha (desktop):

```
▌💉 Clostridioses — dose 2 · Recria 2 · 22 animais agendados                     ⚠ há 4 dias
▌   Aplicação prevista 25/09 · Dr. Paulo Menezes · CL-2608 (5 mL SC)   ✓Vet ✓Estoque ✓Data ◌Conta   [ Aplicar ] [⋯]
```

- **Título:** `Vacina — esquema` (ex.: "Clostridioses — dose 2").
- **Para quem:** lote + **número de animais do agendamento** (não a lista).
- **Checklist resumido** em 4 mini-selos de 12 px com ícone + texto curto: `✓ Vet`, `✓ Estoque`, `✓ Data`, `◌ Conta a pagar` (pendente = círculo tracejado, dispensável). O dono pediu confirmação de veterinário, estoque vinculado (ou desconsiderar) e data. **Pendência no checklist não bloqueia** (avisa; regra "nada bloqueia o campo"): o selo fica âmbar com `⚠ Sem estoque vinculado`.
- **Botão `Aplicar`** (marinho). Abre a **gaveta "Registrar aplicação"** (a mesma porta única da proposta anterior), pré-preenchida: agendamento, produto/frasco/validade, dose, quem aplica, data real. Resumo de consequência antes de confirmar: "22 animais · 22 doses · estoque restante 98 · próxima dose anual · R$ 41,80". Confirmar → toast com Desfazer.
- **Menu ⋯:** `Ver animais do agendamento` (gaveta; lista só quem está agendado, com incluir/tirar animal, inclusive **fora da janela por decisão da fazenda**) · `Mudar data` · `Pular esta aplicação` · `Abrir em Protocolos ›` (leva ao acompanhamento do preventivo).

Por que **Aplicar** e não **Feito** aqui: aplicação de vacina exige conferir frasco/dose/animais, e o dono usa o verbo "aplicar". Para tarefa comum `Feito` é um clique. Dois verbos, ambos com uma ação primária. (A3 nas ambiguidades: proposta anterior queria só "Feito".)

Estado "só faltam confirmar dados" (checklist vazio): o botão continua `Aplicar`; a gaveta abre já no bloco que falta, com foco no primeiro campo pendente.

### 2.7 Calendário: alternador Lista | Semana | Mês

**Semana** (desktop): 7 colunas (seg–dom) de 170 px, hoje destacado com filete dourado + texto "Hoje". Cada coluna: cabeçalho `ter 29` + contagem `15`, depois até 6 **chips de tarefa** (24 px de altura, ícone + título truncado; atrasadas em vermelho no topo da coluna de hoje). "+3 mais" abre a gaveta do dia. Chip clicável abre a gaveta da tarefa. Sem arrastar (reagendar é pelo menu ⋯ → Mudar data). Dias com tarefa crítica (IATF, parto) ganham ícone ⚑ + texto no `aria-label`.

```
 seg 28        ter 29 (HOJE)   qua 30       qui 01/10     sex 02       sáb 03      dom 04
 3 tarefas     15 tarefas      6            5             3            1           2
 ┌────────┐    ┌───────────┐   ┌────────┐   ┌────────┐    …
 │💉Ivermc│    │⚠ Exame TB │   │💉 IBR/BVD│ │💉 IBR/BVD│
 │⚖ Pesag.│    │⚠ Pesagem  │   │IATF D11 │  │…
 └────────┘    │⚠ Clostr.  │   └────────┘
               │…+9 mais   │
```

**Mês:** grade 7 colunas, célula 100x92 px no desktop (contagem em número + até 3 pontos de categoria **com ícone pequeno**, não só cor; `aria-label="29 de setembro, 15 tarefas, 4 atrasadas"`). Clicar no dia abre a **gaveta do dia** (lista do dia com o mesmo componente de linha) e coloca `&data=` na URL. Setas ‹ › mudam o mês; "Hoje" volta.

**Mobile Semana:** faixa horizontal de 7 dias (cada dia 52x64 px, com bolinha de contagem), lista do dia selecionado abaixo (mesma linha de tarefa). **Mobile Mês:** grade compacta (célula 50x52), lista do dia selecionado abaixo; a grade recolhe para 1 semana ao rolar a lista (opção do A4).

Mini-calendário lateral e cartão "Precisa de insumo" **saem** do Dia a dia (viram parte do Painel; o lado direito não existe). A lista ganha a largura toda. Justificativa: eram a razão de a lista ficar comprimida; agora o alternador Semana/Mês cumpre o papel do mini-calendário.

### 2.8 Wireframe mobile 390x844 (Lista)

Barra do app 56 px (topo) + navegação inferior 64 px. Sobra para o conteúdo 844-56-64 = **724 px**.

```
┌──────────────────────────────┐
│ ☰  CowData      🔔3   ⚙     │ 56  barra do app
├──────────────────────────────┤
│ Agenda · ter 29/09    [＋]   │ 52  h1 22px · Nova tarefa = botão 44x44
├──────────────────────────────┤
│ Dia a dia ⚠4  │  Painel ●2   │ 44  sub-abas (metade da largura cada)
│ ═════════════                │
├──────────────────────────────┤
│ [Lista|Sem|Mês]      [Filtr.]│ 48
│ ⚠4 atrasadas · 15 hoje · Ver painel›  │ 28
├──────────────────────────────┤  ← y≈228
│ ATRASADAS (4)               ▾│ 36
│▌⚠ Exame TB — reteste         │
│  3 animais · Lote 02  há 8 d │ 76
│           [ Feito ]  [⋯]     │  (botão 44 px; a linha vira 2 níveis)
│▌⚠ Pesagem de leite …         │
│ …                            │
├──────────────────────────────┤
│ 🏠  📅  ➕  🐄  ≡            │ 64
└──────────────────────────────┘
```

No mobile a linha é **2 níveis**: texto (título + para quem/estado) em cima com 2 linhas; o botão `Feito`/`Aplicar` (largura mínima 96 px, altura 44) e o ⋯ ficam **na mesma linha, à direita, do título**, para não gastar altura: linha de **76 px** (título 16 px em até 2 linhas com corte; subtítulo 14 px 1 linha; botão flutuando à direita com altura 44). Acima da dobra: 36 + 2x76 + 36 ... = **≈ 4 tarefas** (2 atrasadas + cabeçalho Hoje + 3 de hoje conforme rolagem). Cálculo: 724 - (52+44+48+28 = 172) = 552 px de lista → grupo Atrasadas 36 + 4x76 = 340 → sobram 212 = cabeçalho Hoje 36 + **2 linhas de Hoje**. Ou seja: **4 atrasadas + 2 de hoje** sem rolar (mockup atual, medido no celular: 1 linha).

Mobile: gaveta = **folha inferior** cobrindo 88% da altura, com alça, fecha com Esc/arrastar/botão ✕ (44 px). Botão "Aplicar"/"Feito" **fixo no rodapé da folha** (largura total, 48 px) para uso com luva.

### 2.9 O que fica FORA do Dia a dia e como chega em 1 clique

| Saiu do topo | Onde vive agora | Como chegar |
|---|---|---|
| 3 cards de números (Atrasadas/Hoje/Próximos 7) | linha fina de contagens (2.2 #4) | já visível; clicar filtra |
| Reprodução (Candidatas IATF, IATF atual, Última IATF) | Painel > Reprodução | link **Ver painel ›** na linha fina; ou aba `Painel` |
| Sanidade (BST aptos, excluídos, incluir no próximo BST) | Painel > Sanidade | idem |
| Geral (Pendências, Alertas de estoque) | Painel > Estoque e gestão | idem; selo `Painel ●2` já avisa que há alerta |
| Legenda de categorias | rodapé da lista (1 linha, 12 px) e no chip de categoria | sempre visível nos chips |
| Concluídos no período | Painel (bloco próprio) + "Concluídos hoje" recolhido no Dia a dia | grupo no fim da lista / aba Painel |
| Comunicados (nova dieta, alerta de sobra) | Painel > Comunicados; no Dia a dia só uma **faixa dispensável de 40 px** quando há comunicado novo (`ℹ Nova dieta do Lote 01 · Ir para Dieta ›  [×]`) | faixa ou Painel |
| Cartão "Gestão: 1 conta vence hoje…" | linha comum da lista com categoria Gestão (uma linha, ação `Abrir pagamento ›`) + Painel | lista |
| "Precisa de insumo" | Painel > Estoque e gestão; nas linhas, o chip `⚠ falta insumo` | chip abre gaveta com "Comprar" |
| Mini-calendário | alternador Semana/Mês | 1 clique |

Todo item do Painel também tem o inverso: dentro da gaveta de um card há **"Ver no dia a dia"** que aplica filtro de categoria e horizonte na aba 1.

### 2.10 Estados (Dia a dia)

- **Primeira carga:** sem skeleton artificial. No produto real, enquanto a rede responde: cabeçalho, abas e controles **já renderizados**; a lista mostra 3 linhas-esqueleto **apenas se passar de 400 ms**, com `aria-busy`; nunca troca a tela inteira. No mockup: dados síncronos, sem `setTimeout` na primeira renderização (defeito registrado pelo dono).
- **Vazio do dia:** `✓ Nada para hoje. Próxima tarefa: quarta 30/09 — IBR/BVD (Secas).` + `[Ver semana]` `[+ Nova tarefa]`.
- **Vazio geral (fazenda nova):** `Sua agenda vai se preencher sozinha com IATF, BST, vacinas e estoque. Comece criando uma tarefa` + `[+ Nova tarefa]` `[Ver Painel]`.
- **Erro de rede:** faixa `⚠ Não consegui atualizar a agenda. Mostrando dados de 14:05.  [Tentar de novo]` acima da lista (lista continua visível com dados do cache), com `role="alert"`. Nunca "lista vazia" por erro.
- **Feito falhou:** a linha volta com chip `⚠ Não salvou · tentar de novo` (não some).
- **Offline (app):** chip `Sem sinal · será enviado`.
- **Filtro sem resultado:** `Nenhuma tarefa com esses filtros.  [Limpar filtros]`.

---

## 3. Sub-aba 2 · Painel

Objetivo: **"como está e o que vem pela frente"**. Aqui pode ter cards, mas **compactos**, agrupados, com horizonte e projeção. Tudo que estava no print do dono vem para cá.

### 3.1 Anatomia

| # | Zona | Altura desktop | Altura mobile |
|---|---|---|---|
| 1 | Cabeçalho + sub-abas (iguais ao Dia a dia; `+ Nova tarefa` e `Exportar` permanecem) | 56 + 44 | 52 + 44 |
| 2 | **Faixa de horizonte**: `Próximos [7] [30] [60] [90] dias` (segmentado) + `Início: hoje` + link "Como contamos" | 52 | 48 |
| 3 | **Carga futura** (linha do tempo/heatmap, 3 trilhos) | 148 | 132 (rolagem horizontal) |
| 4 | **Grupos de cards compactos**: Reprodução · Sanidade · Estoque e gestão | 3 x 128 = 384 | 3 x (32 + linhas de 2 cards) |
| 5 | **Programação projetada** (tabela por data/tipo) | ~ 320 | lista |
| 6 | **Concluídos no período** (recolhível) | 56 recolhido | 48 |
| 7 | **Comunicados** | 56 | 48 |

### 3.2 Card compacto (medidas)

| Item | Valor |
|---|---|
| Altura | **92 px** (variante com alerta: 92 px também; nada de card mais alto) |
| Largura | desktop 1440: **6 por linha**, coluna = (1197 - 5x12)/6 ≈ **189 px**; 1280: 5 por linha (≈ 200 px, com quebra); 1024: 4 por linha; tablet 768: 3; **mobile 390: 2 por linha, 173 px x 92 px**; 320: 1 por linha (linha compacta de 64 px) |
| Espaçamento | 12 px entre cards, 8 px no mobile |
| Canto | 2 px (regra do DESIGN.md), borda 1 px + filete esquerdo de 3 px na cor da categoria; sem sombra pesada |
| Rótulo | caixa-alta condensada 12 px (ex.: `CANDIDATAS À PRÓXIMA IATF`), 1 linha, corta com "…" e tooltip; o nome completo está na gaveta |
| Número | 32 px, 700, cor de texto normal (não colorir o número; o estado vai no chip) |
| Sublinha | 13 px muted: `próx. 02/10` ou `no horizonte: 18` |
| Micro-tendência | à direita do número: **mini-sparkline 56x20 px** (7 pontos) **ou** delta textual `▲ +3 em 7 d` / `▼ -2` (ícone + texto; escolha por tipo de dado, ver 3.4) |
| Estado | chip 12 px no canto direito superior: `⚠ Atenção`, `✓ Em dia`; só aparece quando há regra de estado; cor sempre acompanha ícone + texto |
| Clicável | card inteiro é botão (44+ px), foco visível de 2 px, abre **gaveta** |
| Seta | `›` discreta no canto inferior direito (12 px) indica que abre |

```
┌▌──────────────────────┐   189 x 92
│ CANDIDATAS À IATF  ⚠  │   rótulo 12px + chip
│ 11        ╱╲╱─ ▲ +3   │   número 32px + micro-tendência
│ próx. protocolo 02/10 ›│   sublinha 13px
└───────────────────────┘
```

### 3.3 Grupos e cards (todos os do print + novos)

Legenda: **[P]** = veio do print do dono, **[N]** = novo (programação projetada pedida), **A** = "agora" (foto de hoje), **H** = "segue o horizonte" (conta o que cai nos próximos 7/30/60/90 dias). Cards H mostram um pequeno relógio `◷` no rótulo.

**REPRODUÇÃO** (cor `--cat-reproducao`)

| Card | Tipo | Número (exemplo canônico) | Sublinha | Gaveta abre |
|---|---|---|---|---|
| Candidatas à próxima IATF [P] | A | 11 | "Lote 02 – Média" | tabela (DEL, estado, motivo, `Iniciar protocolo` que leva ao Novo protocolo com as vacas pré-selecionadas) |
| IATF atual [P] | A | 2 protocolos | "Recria 2 · Dia 9 hoje" | protocolos em andamento (etapa, data, `Abrir protocolo ›`) |
| Última IATF [P] | A | 12/09 | "8 vacas · resultado em 30 d" | última rodada e resultado do diagnóstico |
| Cio de repasse — adesivo [N] | H | 9 | "no horizonte · próx. 01/10" | animais com checagem prevista (Scratch, 14 d pós-IA) **se a fazenda ativou** (configurável); vazio: "Adesivo de cio desligado. `Configurar`" |
| Inseminações programadas [N] | H | 20 | "Dia 11 de Recria 2 em 01/10" | etapas por dia com insumo necessário |
| Partos e secagens [N] | H | 7 | "partos prov. 3 · secagem 4" | lista com datas |

**SANIDADE** (cor `--cat-sanidade`)

| Card | Tipo | Número | Sublinha | Gaveta |
|---|---|---|---|---|
| BST aptos [P] | A | 58 | "próx. aplicação 03/10" | tabela de aptas (DEL ≥ 60) |
| BST excluídos [P] | A | 2 | "4160 (DEL 40), 4124 (DEL 48)" | motivo de cada exclusão |
| Incluir no próximo BST [P] | A | 3 | "ind. lactação" | `PainelLancarBst` (form de lançar) |
| Vacinas previstas [N] | H | 5 | "aftosa 05/11 · 136 an." | aplicações agendadas por data (só **agendamentos**, ver 3.6) |
| Exames previstos [N] | H | 2 | "TB reteste, sorologia" | lista com leitura em 72 h |
| Lista de espera (janela) [N] | A | 22 | "aguardando agendamento" | **só número e link** `Abrir lista de espera em Sanidade ›` (animais em janela não aparecem na Agenda; regra do dono) |

**ESTOQUE E GESTÃO** (cores `--cat-estoque` e `--cat-gestao`)

| Card | Tipo | Número | Sublinha | Gaveta |
|---|---|---|---|---|
| Pendências [P] | A | 4 | "a mais antiga há 8 dias" | lista das atrasadas (mesma linha de tarefa, com `Feito`) |
| Alertas de estoque [P] | H | 3 | "1 vence 15/10 · 1 abaixo do mínimo" | ver 3.7 (com ação de compra) |
| Precisa de insumo [N] | H | 2 | "implantes, cloprostenol" | quanto falta versus programação do horizonte |
| Contas a pagar [N] | H | R$ 12,5 mil | "1 vence hoje" | resumo + `Abrir Financeiro ›` (Gestão fica fora da lista de campo) |
| Comunicados [P] | A | 1 | "nova dieta Lote 01" | comunicados (nova dieta, alerta de sobra) |

Totais: **Reprodução 6 · Sanidade 6 · Estoque e gestão 5 = 17 cards**, sendo os 8 do print + Pendências/Alertas (já contados) + 7 novos. Cada grupo cabe em **1 linha de 6 cards** em 1440.

### 3.4 Micro-tendência (regra)

- **Contagem que evolui no tempo** (pendências, alertas, candidatas): sparkline 7 dias, 56x20, traço 1,5 px; final em ponto; `aria-label` "subiu de 2 para 4 em 7 dias".
- **Contagem de projeção** (H): delta vs. o mesmo período anterior, texto `▲ +3 vs. 30 d anteriores` (cor + seta + texto; verde/vermelho depende do sentido "bom/ruim" de cada card; ex.: pendências subindo = vermelho, candidatas subindo = neutro).
- **Sem dado suficiente** (< 3 dias de histórico): não mostra tendência, mostra `novo`.
- Nada de gráfico maior no card.

### 3.5 Faixa de horizonte e carga futura

**Horizonte** `7 · 30 · 60 · 90 dias` (padrão **30**). Muda: (a) os cards H, (b) o heatmap, (c) a tabela "Programação projetada". Não muda os cards A. Vive na URL (`&horizonte=`).

**Carga futura (heatmap por trilho), desktop 148 px:**

```
Carga futura · próximos 30 dias                              ▮ 0   ▮ 1-4   ▮ 5-9   ▮ 10+   (números dentro das células)
                29/9  30   1/10  2   3   4   5 │ 6   7   8   9  10  11  12 │ 13 …
Reprodução  [ 5][ 2][ 4][ 1][ 3][ 0][ 0]│[ 6][ 0][ 3][ 4][ 0][ 0][ 0]│ …
Sanidade    [ 8][ 3][ 6][ 4][ 2][ 1][ 0]│[ 3][ 2][ 1][ 0][ 2][ 0][ 0]│ …
Estoque/gest[ 2][ 1][ 0][ 1][ 0][ 0][ 0]│[ 1][ 0][ 0][ 0][ 1][ 0][ 0]│ …
▲ Pico: semana de 05/10 (41 tarefas)   ·   Dia sem carga: 9/10   ·   [Ver semana no dia a dia ›]
```

- Linhas = 3 trilhos; colunas = dias (7 e 30 d) ou semanas (60 e 90 d, ~9 a 13 colunas). Célula: 36 x 28 px desktop; **número dentro** (não depende de cor), escala de intensidade em 4 degraus da cor da categoria; hoje com contorno dourado; fins de semana com fundo levemente diferente.
- Clique numa célula: abre a **gaveta do dia/semana** com a lista (mesma linha de tarefa, `Feito` só para hoje/atrasadas; futuras mostram `Mudar data`).
- **Faixa de pico** com texto ("Semana de 05/10: 41 tarefas") e botão `Ver no dia a dia` que abre a visão Semana naquele período.
- **Mobile:** grade rolável na horizontal (células 40x40 px, rótulo do trilho fixo na esquerda), 132 px de altura; 60/90 dias sempre agregados por semana.
- Alternativa em texto para leitor de tela: tabela oculta (`<table class="sr-only">`) com os mesmos números.

### 3.6 Programação projetada (tabela)

Abaixo dos cards. Uma linha por **evento agendado ou previsto no horizonte**, agrupada por tipo, ordenada por data. Colunas:

`Data · Tipo (ícone+texto) · O quê · Para quem (contagem, não lista) · Insumo necessário · Situação`

Situações (ícone + texto): `Agendada` (✓, já está na agenda no dia), `Prevista` (◷, regra da fazenda gerou, sem agendamento), `Falta insumo` (⚠), `Sem veterinário` (⚠).

Tipos listados (os pedidos pelo dono): **adesivo de cio de repasse** (só se ativado), **BST**, **IATF** (por etapa), **vacinas**, **exames**, **alertas de estoque** (quando o estoque projetado cruza o mínimo), **pendências** (as atrasadas).

Exemplos (dados canônicos):

```
02/10  💉 Vacina   B19 · Bezerreiro · 6 bezerras · Dr. Paulo (vet. obrigatório)  BR-2604 ✓        Agendada
03/10  🧬 BST      Aplicação quinzenal · 58 aptas · Lote 01/02                    Posilac …        Prevista
04/10  🎯 IATF     Lote 02 – Média · Dia 7 · 8 vacas · Estron 2 mL                ES-2607 ✓        Agendada
05/11  💉 Vacina   Aftosa · 136 animais · 136 doses = 60 AF-2609 + 76 AF-2611     ⚠ AF-2609 vence 15/10   Prevista
```

Regras:
- **Animais em janela de aplicação não são listados.** Um evento "Prevista" só vira "Agendada" quando alguém agenda (fluxo em Protocolos/Sanidade). Aqui aparece apenas o **número** de animais aguardando (`22 na lista de espera ›`, link para a lista em Sanidade).
- Clicar na linha abre a gaveta da tarefa (a mesma do Dia a dia).
- Filtro rápido por tipo (chips) e por situação.

### 3.7 Gaveta de um card (comportamento comum)

Desktop: gaveta à direita, **480 px** de largura, altura total, sem cobrir o cabeçalho e as abas (os cards continuam visíveis à esquerda; o card ativo fica com contorno). Mobile: folha inferior 88%.

Estrutura: título + número + `✕` · sublinha do horizonte · **ações em massa quando existirem** · lista (linhas de 64 px, mesmo componente) · rodapé fixo com a ação primária do card (ex.: `Iniciar protocolo`, `Lançar BST`, `Criar pedido de compra`) e `Ver no dia a dia`. Fecha com Esc/clique fora; URL `&gaveta=...`.

**Gaveta "Candidatas à próxima IATF":** cabeçalho `11 candidatas · Lote 02 – Média` · filtros `DEL ≥ 45 dias` · tabela (Nº, nome, DEL, estado reprodutivo, motivo, seleção) · rodapé `[Iniciar protocolo com as 11 selecionadas ›]` (leva ao Novo protocolo com lote e vacas pré-selecionados, conforme canônicos).

**Gaveta "BST":** 3 abas internas curtas (`Aptas 58 · Excluídas 2 · Incluir 3`), tabela de cada; `Excluídas` mostra o motivo textual ("4160 · DEL 40 · faltam 20 dias"); `Incluir no próximo BST` traz o form do `PainelLancarBst`. Rodapé `[Lançar aplicação de BST]`.

**Gaveta "Alertas de estoque":**

```
Alertas de estoque · 3
──────────────────────────────────────────────────────────
⚠ Aftosa AF-2609 · vence em 16 dias (15/10)
   Saldo 60 doses · uso previsto até 15/10: 0 · [Usar primeiro] [Descartar…]
⚠ Sincroforte (buserelina) · abaixo do mínimo
   Saldo 2 frascos · precisa de 4 até 12/10 · falta 2
   [Criar pedido de compra]  [Vincular compra já feita]  [Ver conta a pagar]
⚠ Ivermectina IV-2605 · vencido 20/09 · exige ciência   [Registrar descarte]
──────────────────────────────────────────────────────────
Rodapé: [Abrir Estoque ›]
```

Ação de compra: `Criar pedido de compra` (leva ao Pedidos com produto e quantidade sugerida), `Vincular compra já feita` (associa pedido/pagamento existente, cruzando com o checklist do preventivo que o dono pediu) e `Ver conta a pagar`. O que acontece depois (pagamento, comunicação de compra) é do outro assunto (protocolo preventivo); aqui só as **portas**.

### 3.8 Concluídos no período

Bloco recolhível (padrão recolhido) no fim: `Concluídos no período · 7 dias ▸` com De/Ate (labels com `htmlFor`), linha por item (`✓ Vermifugação · Recria 1 · 29/09 14:20 · Cícero Alves · Desfazer`). Mostra agora **todos os tipos, inclusive IATF**, com rótulo legível (nunca id em monospace) e **Desfazer** unificado (corrige achado 17 do mapa). Filtro por categoria e busca. `Exportar` em Excel/PDF.

### 3.9 Comunicados

Lista curta (nova dieta com `Ir para Dieta ›`, alerta de sobra). Cada um tem `Entendi` que dispensa (persistido no servidor). Se houver comunicado novo, o Dia a dia mostra a faixa de 40 px e o selo na aba.

### 3.10 Wireframe desktop 1440x900 (Painel, topo)

```
┌ Sidebar ┐┌────────────────────────────────────────────────────────────────────────────────────────────┐
│         ││ Agenda   ter, 29/09/2026                                  [Exportar]  [+ Nova tarefa]      │ 56
│         ││  Dia a dia ⚠4 │ Painel ●2                                                                   │ 44
│         ││                ═══════                                                                      │
│         ││ Próximos [7][●30][60][90] dias      Carga futura · Reprodução  Sanidade  Estoque           │ 52
│         ││ ┌ CARGA FUTURA ─────────────────────────────────────────────────────────────────────────┐ │
│         ││ │ Reprod [5][2][4][1][3][0][0]│[6][0][3][4][0]…                                          │ │ 148
│         ││ │ Sanid. [8][3][6][4][2][1][0]│[3][2][1][0][2]…      ▲ Pico: semana de 05/10 (41)       │ │
│         ││ │ Estoq. [2][1][0][1][0][0][0]│[1][0][0][0][1]…                                          │ │
│         ││ └────────────────────────────────────────────────────────────────────────────────────────┘ │
│         ││ REPRODUÇÃO                                                                                 │ 28
│         ││ [Candid.IATF][IATF atual][Última IATF][Cio repasse◷][IATF prog.◷][Partos/secagem◷]         │ 92
│         ││ SANIDADE                                                                                   │ 28
│         ││ [BST aptos][BST excluídos][Incluir BST][Vacinas◷][Exames◷][Lista de espera]                │ 92
│         ││ ESTOQUE E GESTÃO                                                                           │ 28
│         ││ [Pendências][Alertas estoque◷][Precisa insumo◷][Contas a pagar◷][Comunicados]              │ 92
│         ││ ▼ PROGRAMAÇÃO PROJETADA (30 dias)  …                          ← dobra em y=900 aprox.      │
└─────────┘└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Acima da dobra em 1440x900: 56+44+52+148+ (28+92)x3 + 3x12 (gaps) = 696 px.** Os **17 cards e o heatmap cabem sem rolar**, sobrando ~200 px para o início da Programação projetada. (Hoje os 8 cards ocupam ~430 px e empurram tudo.)

### 3.11 Wireframe mobile 390x844 (Painel)

```
┌──────────────────────────────┐
│ Agenda · ter 29/09     [＋]  │ 52
│ Dia a dia ⚠4 │ Painel ●2     │ 44
│ Próximos [7][●30][60][90]    │ 48
│ CARGA FUTURA  ◂ rola ▸       │ 132
│ Repr[5][2][4][1][3]…         │
│ San [8][3][6][4][2]…         │
│ Est [2][1][0][1][0]…         │
│ REPRODUÇÃO                   │ 32
│ [Candid. IATF ][IATF atual ] │ 92
│ [Última IATF  ][Cio repasse] │ 92
│ [IATF prog.   ][Partos/sec.] │ 92
│ SANIDADE …                   │
└──────────────────────────────┘
```
Acima da dobra (724 px úteis): 52+44+48+132+32+3x(92+8) = **608 px**; a 1ª linha de cards de Sanidade aparece na dobra. Grupos recolhíveis (`▾`), Reprodução aberto por padrão; o estado de cada grupo é lembrado.

### 3.12 Estados (Painel)

- **Primeira carga:** cabeçalho, abas, horizonte e cards renderizam **com o número** já disponíveis do resumo leve (`/agenda/resumo`, sem skeleton artificial); o que demora (heatmap, tabela) mostra bloco "Calculando…" de altura fixa (sem pulo de layout) só se passar de 400 ms.
- **Card com erro:** o card individual mostra `⚠ Não carregou · Tentar de novo` (falha de uma fonte não derruba o painel).
- **Card sem dado:** `—` + "sem dados" (nunca 0 falso).
- **Recurso desligado:** "Cio de repasse: desligado. `Configurar`" (respeita a decisão: Scratch/cio de repasse totalmente configurável).
- **Horizonte sem eventos:** tabela: "Nada previsto nos próximos 7 dias. Tente 30."

---

## 4. Storyboard (14 telas para imagens)

Todas na mesma fazenda e no mesmo relógio (ter 29/09/2026, 14:05), identidade do mockup atual (marinho `#0B2038`, dourado `#B9831F`, cantos 2 px, Archivo, estados com ícone + texto, alvos ≥44 px). Sem barra de revisão nas imagens (ou recortada). Tema claro por padrão; a tela 14 é escura.

| # | Tela | Viewport | O que mostra (dados canônicos) | Clique que leva à próxima |
|---|---|---|---|---|
| 1 | **Dia a dia · Lista** | 1440x900 | Cabeçalho 1 linha, abas, controles, linha fina de contagens `⚠ 4 atrasadas · 15 de hoje · 20 nos próximos 7 dias · Ver painel ›`. Atrasadas dentro de Hoje: Exame TB (Feito), Pesagem (Feito), Clostridioses dose 2 (Aplicar), Raiva (Aplicar); Hoje: Vermifugação (Aplicar), IATF Recria 2 Dia 9 (Feito), Mastite Dia 3, Adaptação pré-parto Dia 4, Indução Dia 7 | alternador Semana |
| 2 | **Dia a dia · Semana** | 1440x900 | 7 colunas, hoje destacado, chips de tarefa, "+3 mais" | "+9 mais" da coluna de hoje ou alternador Mês |
| 3 | **Dia a dia · Mês** | 1440x900 | Setembro/outubro com contagens e ícones; dia 29 selecionado; gaveta do dia aberta (lista do dia) | clicar na tarefa de vacina |
| 4 | **Aplicação preventiva agendada no dia** (linha + gaveta "Registrar aplicação") | 1440x900 | Linha da Clostridioses com selos `✓Vet ✓Estoque ✓Data ◌Conta`; gaveta com produto CL-2608, dose 5 mL SC, quem aplica, resumo "22 animais · 22 doses · estoque restante 98 · R$ 41,80", botão `Aplicar`. Não lista animais em janela | `Aplicar` |
| 5 | **Feito com toast** | 1440x900 | Linha saiu (lista não recarregou), toast `Aplicação registrada · Clostridioses — dose 2 · Desfazer` (10 s), contagem fina passa de 4 para 3, grupo `Concluídos hoje (1)` | link `Ver painel ›` |
| 6 | **Painel · topo** | 1440x900 | Abas, horizonte 30, heatmap 3 trilhos, 17 cards em 3 grupos, todos acima da dobra | mudar horizonte para 30 (já) / clicar no pico |
| 7 | **Painel com projeção 30 dias** | 1440x900 (rolado) | Heatmap com pico marcado + tabela "Programação projetada" (B19 02/10, BST 03/10, IATF Dia 7 04/10, Aftosa 05/11 com aviso do frasco AF-2609) | card Candidatas IATF |
| 8 | **Gaveta: Candidatas à IATF** | 1440x900 | 11 vacas do Lote 02 – Média (4219–4229), DEL, estado, seleção, rodapé `Iniciar protocolo` | fechar; card BST aptos |
| 9 | **Gaveta: BST** | 1440x900 | Abas Aptas 58 / Excluídas 2 (4160 DEL 40, 4124 DEL 48) / Incluir 3; form lançar BST | card Alertas de estoque |
| 10 | **Gaveta: Alertas de estoque + compra** | 1440x900 | 3 alertas (AF-2609 vence 15/10; Sincroforte abaixo do mínimo, falta 2; IV-2605 vencido) e ações `Criar pedido de compra` / `Vincular compra já feita` / `Ver conta a pagar` | `Concluídos no período` |
| 11 | **Concluídos no período** | 1440x900 | Bloco expandido: 7 dias, itens com rótulo legível (inclui IATF), quem fez, `Desfazer`; filtros De/Ate | mobile |
| 12 | **Mobile · Dia a dia** (2 quadros lado a lado: Lista e folha "Registrar aplicação") | 390x844 | 4 atrasadas + 2 de hoje acima da dobra; botão `Aplicar` 44 px; folha inferior com botão fixo no rodapé | aba Painel |
| 13 | **Mobile · Painel** (2 quadros: topo + gaveta de card em folha) | 390x844 | Horizonte, heatmap rolável, cards 2 por linha, grupos recolhíveis | estados |
| 14 | **Estados: vazio / erro / dia fechado / sem skeleton na 1ª carga** (grade de 4 quadros; um deles em tema escuro) | 1440x900 (recortes) | (a) Dia sem tarefas com "Próxima tarefa..." · (b) faixa de erro de rede com dados de 14:05 e `Tentar de novo` · (c) `✓ Dia fechado · 15 de 15` · (d) 1ª carga: cabeçalho e abas prontos, lista sem skeleton (dados síncronos) | — |

Cada imagem deve ter legenda curta (1 linha) com o **clique** que a liga à próxima, para o dono "ver o fluxo".

---

## 5. Decisões sobre KPIs (o que continua no Dia a dia)

Princípio: **1 linha fina, texto, sem caixa, sem gráfico**. Máximo de 3 números clicáveis.

| Número | Fica no Dia a dia? | Como aparece | Por quê |
|---|---|---|---|
| Atrasadas | **Sim** | `⚠ 4 atrasadas` (ícone + texto, vermelho-escuro) + selo na aba; clicar rola/foca o grupo Atrasadas | É ação imediata; o dono não quer card mas o número não pode sumir. |
| Hoje (N de M) | **Sim** | `15 de hoje · 0 feitas` | Mede o dia; vira `✓ Dia fechado` quando completo. |
| Próximos 7 dias | **Sim** | `20 nos próximos 7 dias` (clicar = visão Semana) | Dá horizonte curto sem card. |
| Candidatas IATF, IATF atual, Última IATF | Não | só Painel | Análise/planejamento, não tarefa. |
| BST aptos/excluídos/incluir | Não | Painel; a **tarefa** "Aplicação de BST" continua sendo linha na lista | Só a ação (a tarefa) é dia a dia. |
| Pendências | Não (é o mesmo que Atrasadas) | Painel mantém card só para ver a lista/tendência | Fim da duplicação KPI vs. seção "Atrasados". |
| Alertas de estoque | Só como **selo** `Painel ●2` na aba e chip `⚠ falta insumo` na linha afetada | Painel | Avisa sem ocupar espaço. |
| Cobertura vacinal, total de animais, qualquer % | Não | Sanidade > Vacinas e exames > Cobertura | Não é o assunto da Agenda. |

Regras de cor: número atrasado sempre com texto "atrasadas" e ícone; verde só em `✓ Dia fechado`.

---

## 6. Requisitos que este design impõe à implementação (para o time técnico)

1. **Endpoint leve de resumo** (`/agenda/resumo`: atrasadas, hoje, feitas, próximos 7 d, selos das abas) e **eventos paginados por intervalo** (`/agenda/eventos?de&ate&cat`) sem escrita em GET. O Painel usa `/agenda/painel?horizonte=` (cards + heatmap + projeção).
2. **Atualização otimista**: Feito remove a linha localmente; nunca `loading=true` global (corrige o skeleton total do mapa, item 6).
3. **Estado na URL** (`aba`, `visao`, `data`, `cat`, `horizonte`, `gaveta`, `tarefa`).
4. **Regra do dono no contrato:** o motor **não emite** eventos "animal em janela" para o Dia a dia; a lista de espera vem de outro endpoint e só o **número** entra no Painel.
5. **Fuso local** `America/Sao_Paulo` (achado P1 anterior), para "hoje/atrasada/há N dias".
6. **Acessibilidade:** `tablist`/`tab`/`tabpanel`, `<tr>`/linhas com teclado, gavetas com `role="dialog"`, Esc e trap de foco, `aria-live` nos toasts, `aria-label` em cada célula do calendário/heatmap, `label htmlFor` nos campos De/Ate.
7. **Componentização:** extrair a linha de tarefa e as gavetas de dentro do render (hoje `BotaoRealizado`, `PainelConfirmarBaixa` etc. são recriados a cada render).

---

## 7. AMBIGUIDADES (com recomendação)

| # | Ambiguidade | Recomendação |
|---|---|---|
| **A1** | Nome da 2ª aba: "Painel", "Planejamento" ou "Panorama". | **Painel** (curto, sem conflito). Trocar é só rótulo. |
| **A2** | "Lembrar a última usada": o dono quer "Dia a dia" ao entrar. Lembrar aba ou só a visão? | Entrada **sempre Dia a dia**; lembrar **visão (Lista/Semana/Mês) e horizonte**. Com URL `?aba=painel` o link funciona para quem compartilha. |
| **A3** | Verbo da ação: "Feito" para tudo (proposta anterior) versus "Aplicar" (dono). | **Feito** nas tarefas comuns; **Aplicar** nas aplicações preventivas (e BST). Ambos = 1 ação primária e mesmo toast/Desfazer. |
| **A4** | Mobile: grade do mês sempre aberta ou recolhe para 1 semana ao rolar? | Recolhe (economiza 160 px). Botão ▾ reabre. |
| **A5** | Onde ficam "Comunicados" no Dia a dia? | Faixa dispensável de 40 px só quando há novo + Painel. Não vira card. |
| **A6** | "Cio de repasse — adesivo": aparece no Painel se **desligado**? | Só aparece quando ativado em Configurações > Reprodução. Se desligado, o card aparece cinza com `Configurar` **apenas para admin** (descoberta), e some para os demais. |
| **A7** | Cards H mudam com o horizonte, mas cards A (candidatas, BST aptos) não. Confunde? | Marcar H com `◷` e legenda de uma linha "◷ segue o horizonte"; A sem marca. |
| **A8** | Heatmap: contar só tarefas de campo ou também Gestão? | 3 trilhos separados (Reprodução, Sanidade, Estoque e gestão). O total "Dia fechado" continua contando **só tarefas de campo** (proposta anterior, §5.2). |
| **A9** | Gaveta do card mostra animais em janela? | **Não.** Só número e link para a lista de espera (regra do dono). Animais **agendados** aparecem na gaveta da tarefa, com opção de incluir/tirar (inclusive fora da janela). |
| **A10** | Densidade da linha: 68 px é suficiente para luva/celular? | Sim, com botão de 44 px. Oferecer "compacta 56 px" no ⋯ (não padrão). No app de campo (`/app`) a linha permanece com o padrão próprio (Inter, 56+ px). |
| **A11** | "Ver painel ›" na linha fina: link ou botão? | Link de texto com alvo de 44 px de altura (padding), para não competir com `+ Nova tarefa`. |
| **A12** | Mockup: pode ter interação de dados reais (Feito realmente remove/atualiza contagens)? | Sim; contagens da linha fina, do selo da aba e do heatmap **derivam do mesmo array de dados**, para não divergirem (como nos canônicos). Sem `setTimeout` na 1ª renderização. |
| **A13** | O que acontece com o mini-calendário e o "Precisa de insumo" lateral? | O primeiro é substituído pelo alternador Semana/Mês; o segundo migra para o Painel (card + gaveta). Desktop do Dia a dia fica em coluna única. |
| **A14** | Vinculação de compra/pagamento (checklist do preventivo): onde nasce? | No protocolo/agendamento (outro planejador). A Agenda só expõe as **portas** (`Criar pedido de compra`, `Vincular compra já feita`). |

---

## 8. Resumo do ganho (números)

| Métrica | Agenda real hoje | Mockup atual | Nova (Dia a dia) |
|---|---|---|---|
| y da 1ª tarefa (1440x900) | ~ 3 telas (≈ 2000+) | 437 | **200** |
| Tarefas visíveis sem rolar | 0 | 1,5 | **9** (4 atrasadas + 5 de hoje) |
| Tarefas visíveis sem rolar (390x844) | 0–1 | 1 | **6** (4 atrasadas + 2 de hoje) |
| Cards de indicador no dia a dia | 8 | 3 | **0** (1 linha de texto) |
| Cards no Painel acima da dobra (1440x900) | 8 (empurram a lista) | — | **17 + heatmap** |
