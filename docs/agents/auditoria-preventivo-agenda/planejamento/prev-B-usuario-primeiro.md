# Planejador B — Protocolo sanitário preventivo (vacina e exame): USUÁRIO-PRIMEIRO, fluxo e telas

> Ponto de partida: o que o dono vê e faz, tela a tela. Fonte da verdade: `00-PEDIDO-DO-DONO.md`. Compatível com `docs/redesenho-evento-sanitario.md` (Ocorrência, 4 estados, checklist, incluir fora da janela) e com a identidade visual dos mockups atuais (tokens CowData, marinho/ouro, cantos 2px, drawers, tabelas, estado = ícone + texto, botão primário marinho, ouro só para confirmar). Só leitura no repo; este é o único arquivo escrito.
> Relógio dos mockups: terça 29/09/2026, 14:05. Fazenda Estreito Ponte de Pedra. Usuário: Jairo Nasser.

---

## 0. Diagnóstico rápido do mockup atual (por que o dono "não visualizou o fluxo")

Olhei `vacinas-protocolos.html` e `agenda.html` renderizados. O que existe é bonito, mas conta **outra história** que a do dono:

| O dono pediu | O mockup atual mostra | Consequência |
|---|---|---|
| Cadastrar, aplicar/agendar, acompanhar e ver concluídos **dentro de Protocolos** | Preventivo foi **tirado** de Protocolos e virou "Sanidade › Vacinas e exames" (Calendário, Cobertura, Histórico, Cadastro de vacinas). Protocolos ficou só com IATF, indução, curativo, próprio (abas Em andamento · Novo protocolo · Modelos · Concluídos) | O dono não acha "onde cadastro o preventivo" nem "onde aplico" |
| **Janela de aplicação → lista de espera** | Não existe lista de espera. O Calendário lista "aplicações previstas" e as **atrasadas vão para a Agenda** | Animal na janela aparece na Agenda (o que o dono proíbe) |
| **Cronograma + agendamento** que "entra na Agenda no dia" | Botão único "Registrar" na linha; não há passo de montar/agendar | Falta o meio do fluxo |
| Incluir animais **dentro e fora** da janela | Só existe como aba dentro do drawer "Aplicação prevista" | Não é um passo visível |
| **Sanidade somente leitura** | Sanidade tem "+ Registrar aplicação" e "Cadastrar vacina" | Quebra a regra "aplicação só por Protocolos e Agenda" |
| Cruzar veterinário/estoque/data/compra/pagamento/conta a pagar | Checklist existe só no drawer, sem compra nem vínculo de pagamento | Cruzamentos não aparecem |

Conclusão: o mockup atual **não contempla** o fluxo do dono. A identidade visual fica; a **arquitetura de informação e as telas** precisam ser refeitas conforme abaixo. Isto **reverte** a decisão minha anterior ("o Preventivo sai da Central de Protocolos").

---

## 1. O fluxo do dono em uma página

### 1.1 Ciclo completo

```
 PROTOCOLOS > CADASTRO                       (uma vez por protocolo: B19, Raiva, Aftosa, Exame TB...)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ Protocolo preventivo: vacina ou exame · produto/dose/via · carência ·        │
 │ quem entra (categoria/idade/lote) · JANELA DE APLICAÇÃO · repete? · checklist│
 └───────────────┬──────────────────────────────────────────────────────────────┘
                 │ o sistema vigia o rebanho todo dia
                 ▼
 ANIMAL ENTRA NA JANELA DE APLICAÇÃO  (automático: completou idade, chegou a data, mudou de lote)
                 │  revisão opcional: "não se aplica a este animal" (remover, com motivo)
                 ▼
 ┌──────────────────────────── LISTA DE ESPERA ───────────────────────────────┐
 │ PROTOCOLOS > APLICAR / AGENDAR      (aqui o animal FICA. Nunca vai à Agenda) │
 │ agrupada por protocolo · "Atrasado na janela" sobe para o topo               │
 └───────────────┬───────────────────────────────────────────────────────────────┘
                 │ [Montar cronograma]  (marca animais da espera)
                 │ + [Incluir de FORA da janela]  (por conta da fazenda, com motivo)
                 ▼
 MONTAR CRONOGRAMA  (rascunho: "Em montagem")
   1 Animais  →  2 Data, hora e veterinário  →  3 Checklist  →  4 Conferir e Agendar
                                   │ Checklist cruza dados:
                                   │   veterinário confirmado · estoque (vincular frasco OU desconsiderar)
                                   │   data · comunicação de compra/cotação · vincular pagamento já feito
                                   │   ou lançar conta a pagar · horário · lotes de manejo
                 ▼
 AGENDADO   (os animais SAEM da lista de espera; ficam "no agendamento")
    ├──────────────► PROTOCOLOS > ACOMPANHAMENTO  = "o que já está agendado" (lista/calendário)
    └──────────────► AGENDA no dia da aplicação   = 1 linha por agendamento (nunca por animal)
                 │
                 ▼
 APLICAR  ── mesma tela (drawer "Aplicar") aberta por DOIS caminhos:
              (a) Protocolos > Acompanhamento > [Aplicar]
              (b) Agenda, no dia > [Aplicar]
                 │  por animal: aplicou? · frasco/lote (validade) · dose/via · quem aplicou · data/hora
                 │  baixa estoque · calcula carência · cria conta a pagar/vínculo · agenda a próxima dose
                 ▼
 CONCLUÍDO   (PROTOCOLOS > CONCLUÍDOS = histórico; SANIDADE > Concluídos = espelho só leitura)
                 │
                 └─ animais não aplicados voltam à lista de espera (ou saem, com motivo)
                 └─ próxima dose/reforço reabre a janela (Clostridioses dose 2 = +30 d; Raiva = +1 ano)
```

### 1.2 As regras que o mockup precisa deixar **visíveis** (não só existirem)

1. **Animal na janela aparece somente na lista de espera. Nunca na Agenda.** A Agenda só recebe um **agendamento** (grupo de animais + data + responsável), e só a partir do momento em que ele é confirmado.
2. **Lançamentos não faz preventivo.** Em Lançamentos › Sanitário fica só o curativo (e BST). No lugar do preventivo, um aviso com link "Vacinas e exames agora ficam em Protocolos".
3. **Sanidade só lê.** Calendário, Em andamento, Concluídos (e Cobertura). Cada linha tem links "Abrir em Protocolos" ou "Abrir na Agenda". Nenhum botão de escrever.
4. **Aplicar só existe em dois lugares:** Protocolos › Acompanhamento e Agenda (no dia). É o **mesmo drawer**, com o mesmo resultado.
5. **Fora da janela é permitido** (por conta da fazenda), sempre com motivo escolhido e marca visível "Fora da janela" em toda a vida do agendamento.
6. **Nada bloqueia o campo:** estoque, veterinário pendente e data fora da janela avisam; quem decide é o dono. Única trava dura: lote **vencido** ao aplicar e exame/B19 que exigem veterinário sem veterinário habilitado (aviso forte, exige ciência registrada).
7. Um mesmo protocolo pode ter **mais de um agendamento por janela** (ex.: Recria 2 em dois dias); a lista de espera guarda quem sobrou.

### 1.3 Correspondência com o modelo já decidido (`redesenho-evento-sanitario.md`)

| Linguagem do dono / tela | Estado do modelo | Observação |
|---|---|---|
| Animal **na lista de espera** (janela aberta) | Ocorrência **Provável** (animais "Sugerido automático") | a lista de espera é a leitura das Prováveis, agrupada por protocolo |
| **Cronograma em montagem** | **Em edição** | checklist e animais editáveis |
| **Agendado** | **Confirmado** | só neste estado o item chega à Agenda |
| **Aplicado / Concluído** | **Realizado** | terminal; só observação aditiva |
| Reabrir cronograma | Confirmado → Em edição | mantido |
| Incluir fora da janela | "Incluído manual fora da janela" | mantido (flag + motivo) |
| Desconsiderar checklist | "Desconsiderar cronograma" | mantido, por rodada |

---

## 2. Arquitetura de informação

### 2.1 Mapa (o que muda em relação ao mockup atual)

```
PROTOCOLOS  (#/protocolos/…)                 abas de topo — as mesmas para todos os tipos
 ├─ Visão geral          #/protocolos/visao            (Central: painel de tudo que está vivo)
 ├─ Cadastro             #/protocolos/cadastro         chips de tipo: Preventivo · Curativo · IATF · Indução · Próprio
 ├─ Aplicar / Agendar    #/protocolos/agendar          Preventivo = LISTA DE ESPERA + montar cronograma
 │                                                     (IATF/indução/curativo = "lançar protocolo", como hoje)
 ├─ Acompanhamento       #/protocolos/acompanhamento   Preventivo = o que já está agendado + Aplicar
 └─ Concluídos           #/protocolos/concluidos       histórico (Preventivo inclui exames e comprovantes)

SANIDADE > Vacinas e exames  (somente leitura)
 ├─ Calendário           #/sanidade/vacinas/calendario
 ├─ Em andamento         #/sanidade/vacinas/andamento
 ├─ Concluídos           #/sanidade/vacinas/concluidos
 └─ Cobertura            #/sanidade/vacinas/cobertura   (carteira por animal; o dono gostou; mantida como 4ª leitura)
 (saem de Sanidade: "Cadastro de vacinas" e "+ Registrar aplicação")

AGENDA      (agenda.html#/agenda)   mostra AGENDAMENTOS do dia, jamais lista de espera
LANÇAMENTOS (#/lancamentos/sanitario) só Curativo (+ BST); preventivo: aviso com link
```

Confirmação/ajuste do que o dono listou: **Cadastro · Aplicar/Agendar · Acompanhamento · Concluídos — confirmado**, com **um ajuste**: acrescento **"Visão geral"** como primeira aba porque o dono pediu ver a **central de protocolos** na sequência. Ela é a porta de entrada e não muda nenhuma outra aba. A profundidade máxima é: aba › (chip de tipo) › linha › drawer, sem 3 níveis de abas (problema hoje, `central-protocolos.md` §6).

Estado na URL: aba, chip de tipo, filtro e drawer aberto (`?agendamento=`, `?aplicar=`) sobrevivem ao F5 e ao "voltar do navegador" (hoje a Central não faz isso).

### 2.2 O que cada lugar mostra e NÃO mostra

| Lugar | Mostra | NÃO mostra |
|---|---|---|
| **Protocolos › Cadastro** | protocolos preventivos (vacina/exame), janela, checklist-padrão, quantos animais estão hoje na janela | animais individuais, agendamentos |
| **Protocolos › Aplicar/Agendar** | **lista de espera** por protocolo; botão Montar cronograma; Aplicação avulsa | agendamentos já feitos (estão em Acompanhamento) |
| **Protocolos › Acompanhamento** | cronogramas: Em montagem · Agendado · Hoje · Atrasado · Adiado; Aplicar; Adiar; Cancelar; Reabrir | lista de espera (só um contador com link) |
| **Protocolos › Concluídos** | histórico: aplicações e exames, por agendamento e por animal, comprovante, exportar | pendências |
| **Sanidade** | calendário (datas e janelas), em andamento, concluídos, cobertura — leitura | qualquer botão de escrever (aplicar, cadastrar, agendar) |
| **Agenda** | **agendamento do dia** (1 linha por agendamento: o quê, quem/onde, quantos, responsável, hora, Aplicar); atrasados **agendados**; aba gerencial: agendamentos futuros | animal na janela, lista de espera, cronograma em montagem, rascunhos |
| **Lançamentos** | curativo, BST, reprodutivo etc. | vacina e exame preventivos |

Nota sobre a Agenda (importante): o dono quer, na 2ª sub-aba (gerencial), "programação projetada de vacinas, exames". Recomendo mostrar aí **somente agendamentos futuros já marcados** (datas fixadas) e "protocolos com janela abrindo em breve" como **uma linha com contagem e link para Protocolos › Aplicar/Agendar**, sem listar animais. Ver ambiguidade A6.

### 2.3 Onde o Lançamentos deixa de contemplar o preventivo
- `Lançamentos › Sanitário`: sub-abas deixam de ter "Preventiva › Calendário sanitário" e "Preventiva › Avulso". Ficam **Curativo** (e BST, se já estiver aí).
- Em seu lugar, faixa informativa azul-aço: "Vacinas e exames (protocolo preventivo) são agendados e aplicados em **Protocolos**. [Ir para Protocolos › Aplicar/Agendar]".
- Aplicação avulsa/emergência (vacinar hoje sem protocolo) passa a ser um botão em Protocolos › Aplicar/Agendar (cria cronograma + aplica no mesmo fluxo).
- O botão "$ Financeiro" solto do calendário e o popup pós-aplicação são substituídos pelo item de checklist e pelo bloco financeiro do cronograma.

### 2.4 Vocabulário em linguagem de fazenda — o que MUDA em relação ao que eu impus antes

| Antes (eu impus) | Agora | Por quê |
|---|---|---|
| "Aplicação prevista" | **Lista de espera** (animais na janela) e **Cronograma** (a rodada montada) | os dois termos do dono; eu tinha fundido tudo em um só |
| "Vacina do calendário" / "Cadastro de vacinas" | **Protocolo preventivo** (tipo: vacina ou exame) | o dono fala "protocolo de sanidade preventivo" |
| "Registrar aplicação" | **Aplicar** | verbo do dono |
| "Agendar aplicação" (só verbo) | **Agendar** = fixar data/hora/responsável do cronograma; o resultado é um **agendamento** | o dono distingue cronograma e agendamento |
| "Marco do animal" | **Entrada na janela** (regra: idade, categoria, data, evento) | mais claro |
| Prevista → Confirmada → Registrada | **Na lista de espera → Em montagem → Agendado → Aplicado**; exceções: Atrasado · Adiado · Pulado · Cancelado | casa com os 4 estados do modelo |
| "Histórico" (Sanidade e Protocolos) | **Concluídos** | palavra do dono |
| "Pular esta aplicação" | **Pular esta rodada** | rodada = 1 cronograma |
| "Cadastro de vacinas" dentro de Sanidade | sai; cadastro só em **Protocolos › Cadastro** | Sanidade só lê |
| Preventivo "sai da Central de Protocolos" | **volta e é o tipo principal** | pedido do dono |
| Mantidos | Aplicar/Adiar/"Não vou fazer", Dia 0/Dia 7…, carência, "há N dias", checklist, "Atrasada" (nunca "vencida") | já aprovados |

Termos proibidos em tela: Ocorrência, Provável, materialização, gatilho, usa_cronograma, janela de agrupamento (jargão interno).

---

## 3. STORYBOARD (33 telas)

**Como ler.** Rotas são hash do mockup único (as de Protocolos/Sanidade em `vacinas-protocolos.html`; as da Agenda em `agenda.html`). "→" = para onde a ação leva. Todas as telas usam a casca atual (sidebar, sub-nav, faixa de 3 números, tabela de bordas 2px, drawer à direita, badge = ícone + texto). Fio condutor: **B19** (dose única, veterinário obrigatório), com **Raiva, Clostridioses, Vermifugação, Aftosa, Leptospirose e Exame TB** nas cenas em que fazem mais sentido. Cenário do mockup: as cenas 2–6 rodam no cenário **"Fazenda nova / sem B19 cadastrado"** e as demais no **"Dia normal"**.

Legenda de estados usada nas telas: `[cinza tracejado] Na lista de espera` · `[azul-aço] Em montagem` · `[azul] Agendado` · `[âmbar] Hoje / Vence ≤ 7 d` · `[vermelho + triângulo] Atrasado` · `[verde] Aplicado` · `[riscado] Pulado/Cancelado`.

---

### BLOCO A — Central e cadastro do protocolo

#### Tela 1 — Central de Protocolos · Visão geral
- **Rota:** `#/protocolos/visao`
- **Objetivo:** dar ao dono, em uma olhada, o que está vivo em todos os tipos e onde agir no preventivo.
- **O que aparece:** título "Protocolos" + botões `+ Novo protocolo` (ouro) e `Folha de campo`. Abas: **Visão geral** (ativa) · Cadastro · Aplicar / Agendar · Acompanhamento · Concluídos. Faixa de 3 números clicáveis: **Na lista de espera 51** (âmbar; "3 grupos atrasados na janela") · **Agendados 4** (2 hoje) · **Em andamento 5** (IATF, mastite, pré-parto, indução). Abaixo, uma tabela "Por tipo" (linhas: Preventivo — vacina e exame · Curativo · IATF · Indução · Protocolo próprio) com colunas `Tipo · Na espera · Em montagem · Agendado · Hoje · Atrasado · [Abrir]`. A linha do **Preventivo** vem primeiro e destacada. Bloco "Precisa de você hoje" (3 linhas): "Raiva — reforço · 6 vacas atrasadas na janela · [Montar cronograma]", "Clostridioses — dose 2 · 22 novilhas atrasadas · [Montar cronograma]", "Vermifugação — Recria 1 · agendada para hoje · [Aplicar]".
- **Dados:** espera 51 = 22 Clostridioses + 6 Raiva + 3 TB reteste + 14 IBR/BVD + 6 B19 (calculado pelos mesmos dados, nunca digitado; atrasados na janela = 22+6+3 = 31). Agendados 4: Vermifugação Recria 1 (hoje), IATF Recria 2 Dia 9 (hoje), mastite, B19 02/10.
- **Ações →** linha Preventivo `[Abrir]` → tela 8 · "Montar cronograma" → tela 11 (com o protocolo pré-escolhido) · "Aplicar" → tela 22 · `+ Novo protocolo` → tela 3.
- **Estados especiais:** fazenda nova (vazio): "Ainda não há protocolos. [Usar modelo padrão brasileiro] [Criar o primeiro]". Erro de carga: faixa vermelha "Não consegui atualizar · [Tentar de novo]" mantendo os últimos dados. **Sem skeleton artificial** (render imediato).

#### Tela 2 — Cadastro › lista de protocolos preventivos
- **Rota:** `#/protocolos/cadastro?tipo=preventivo`
- **Objetivo:** ver e gerir os protocolos preventivos cadastrados e começar um novo.
- **O que aparece:** aba Cadastro ativa; chips de tipo (Preventivo ativo · Curativo · IATF · Indução · Próprio); botão `+ Novo protocolo preventivo` (ouro). Tabela: `Protocolo · Tipo (ícone vacina/exame) · Quem entra · Janela de aplicação · Repete · Na janela agora · Checklist · Estado (Ativo/Inativo) · ⋯`. Linhas: Aftosa (anual; data da defesa estadual editável), B19, Clostridioses (dose 1 → +30 d → anual), Raiva, IBR/BVD, Leptospirose, Vermifugação (a cada 90 d), Exame TB (anual; reteste 60 d), Exame brucelose. Coluna "Na janela agora" tem número clicável que leva à lista de espera filtrada.
- **Dados:** B19 · Vacina · "Fêmeas de 3 a 8 meses" · "Abre aos 3 meses, fecha aos 8" · "Dose única" · **6 na janela** · Checklist com veterinário obrigatório.
- **Ações →** `+ Novo` → tela 3 · Editar → wizard preenchido (tela 3) · ⋯ Duplicar / Inativar (pede motivo) / Ver cronogramas que usam → tela 19 filtrada · número "Na janela agora" → tela 8.
- **Estados:** fazenda nova (vazio): cartão "Monte seus protocolos em 2 minutos · [Usar modelo padrão brasileiro] (B19, aftosa, clostridioses, raiva, IBR/BVD, lepto, vermífugo, TB, brucelose) — ajuste com seu veterinário e com a defesa sanitária estadual". Protocolo inativo: linha esmaecida, sem entrar na janela.

#### Tela 3 — Cadastro · Wizard passo 1 "O que é"
- **Rota:** `#/protocolos/cadastro?tipo=preventivo&nova=1&passo=1` (drawer largo, 3 passos + conferir; rascunho por fazenda+usuário com faixa "Retomamos seu rascunho [Descartar]")
- **Objetivo:** dizer se é vacina ou exame e qual produto/exame.
- **O que aparece:** stepper `1 O que é · 2 Quem e quando · 3 Checklist · 4 Conferir` (só volta clicando). Dois cartões grandes de escolha: **Vacina** (seringa) e **Exame** (tubo). Vacina: nome, doença combatida, produto padrão (do Catálogo/estoque), dose, via (SC/IM…; via travada pelo produto), **carência leite e carne** (dias), **exige veterinário habilitado?** (liga sozinho para B19 e TB, com o aviso). Exame: nome, tipo de resultado (positivo/negativo/inconclusivo ou numérico com faixa), **leitura em N horas** (TB = 72 h), quem coleta.
- **Dados:** "Brucelose B19" · doença: Brucelose · produto: B19 · 2 mL SC · carência leite 0 d / carne 0 d · **Exige veterinário: sim** · custo/dose R$ 6,40.
- **Ações →** Continuar → tela 4 · Cancelar (sem `window.confirm`; cartão inline "Descartar o que foi preenchido?").
- **Estados:** campo obrigatório em falta destaca só o campo (não bloqueia o stepper); produto sem estoque cadastrado mostra "Sem saldo hoje — o cronograma vai avisar, não vai travar".

#### Tela 4 — Cadastro · Wizard passo 2 "Quem entra e quando (janela de aplicação)"
- **Rota:** `#/protocolos/cadastro?tipo=preventivo&nova=1&passo=2`
- **Objetivo:** definir **quem** entra na janela e **quando** ela abre/fecha e se repete.
- **O que aparece:** bloco **Quem entra**: categoria (fêmea/macho/todos), faixa de idade (de/até em meses), lotes (multi), condição extra (ex.: "só prenhes", "só secas"). Bloco **Janela de aplicação** com uma régua desenhada (linha do tempo): "abre **quando** [completa 3 meses] · fecha **quando** [completa 8 meses]" ou "abre [15] dias antes / fecha [30] dias depois da data devida". Bloco **Repete**: `Dose única · A cada N dias/meses · Anual em data fixa (editável — ex.: aftosa pela defesa estadual) · Multidose: dose 1 → +30 dias dose 2 → reforço anual`. À direita, **pré-visualização viva**: "Hoje esta janela alcança **6 animais** (6104–6109)" com link "ver quais".
- **Dados:** B19: fêmeas · 3 a 8 meses · Bezerreiro · abre aos 3 meses / fecha aos 8 · dose única · pré-visualização "6 animais hoje; +2 completam 3 meses até 17/10".
- **Ações →** Voltar → 3 · Continuar → tela 5.
- **Estados:** janela sem ninguém: "Nenhum animal alcançado hoje — normal; eles entram sozinhos quando cumprirem a regra". Regra contraditória (fecha antes de abrir): erro inline vermelho.

#### Tela 5 — Cadastro · Wizard passo 3 "Checklist" + passo 4 "Conferir"
- **Rota:** `#/protocolos/cadastro?tipo=preventivo&nova=1&passo=3` (e `passo=4`)
- **Objetivo:** escolher o que **todo cronograma deste protocolo** precisará conferir, e revisar antes de salvar.
- **O que aparece (passo 3):** lista de itens já ligados por padrão ao tipo, cada um com interruptor "Usar neste protocolo": **Confirmação do veterinário** (ligado; obrigatório neste protocolo), **Estoque vinculado (frasco/lote) ou desconsiderar**, **Data**, **Horário da aplicação**, **Lotes de manejo atuais**, **Comunicação de compra/cotação** (aparece se o estoque não cobrir), **Vincular a pagamento já realizado**, **Lançar conta a pagar** (custo do protocolo: produto, honorário do veterinário), + "Adicionar item da fazenda". Cada item tem a nota "pulável na hora". Passo 4 "Conferir": resumo em linguagem de fazenda: "Vacina B19 · 2 mL SC · dose única · fêmeas de 3 a 8 meses · janela abre aos 3 meses · veterinário obrigatório · **6 animais entram hoje na lista de espera** · checklist com 7 itens" + as "próximas 3 datas". Botão ouro `Salvar protocolo`.
- **Ações →** Salvar → tela 6 · Voltar.
- **Estados:** salvar grava vacina + regra numa só operação; se falhar, "Nada foi salvo · [Tentar de novo]" (nunca deixa metade).

#### Tela 6 — Protocolo salvo · primeira entrada de animais
- **Rota:** `#/protocolos/cadastro?tipo=preventivo&salvo=b19`
- **Objetivo:** fechar o cadastro e mostrar, sem o dono procurar, o que acontece agora.
- **O que aparece:** faixa verde "Protocolo **B19** salvo." Cartão "O que acontece agora": ① "**6 bezerras já estão na janela** e foram para a **lista de espera**" ② "Você monta o cronograma quando quiser (a visita do veterinário)" ③ "Nada vai para a Agenda até você agendar". Botões: `Ver lista de espera` (marinho) e `Montar cronograma agora` (ouro).
- **Ações →** Ver lista de espera → tela 8 (filtrada em B19) · Montar cronograma → tela 11 · Voltar à lista → tela 2.
- **Estados:** protocolo salvo com 0 animais na janela: cartão troca para "Ninguém na janela ainda. Vamos avisar quando o primeiro animal entrar."

---

### BLOCO B — Entrada na janela e lista de espera

#### Tela 7 — Entrada automática na janela · revisão
- **Rota:** `#/protocolos/agendar?tipo=preventivo&revisar=b19` (drawer) — abre pelo aviso do sino/Visão geral
- **Objetivo:** mostrar **por que** cada animal entrou na janela e permitir tirar quem não se aplica.
- **O que aparece:** sino com item "6 animais entraram na janela de **B19**". Drawer "Entraram hoje na janela · B19": tabela `Brinco · Nome · Lote · Idade · Por que entrou · Entrou em · [Não se aplica]`. Rodapé: `Manter todos na lista de espera` (primário) · "Remover selecionados" (abre motivo: Já vacinada em outra fazenda · Não é fêmea de reposição · Vai ser descartada · Outro).
- **Dados:** 6104 Neblina · Bezerreiro · 3 m 4 d · "completou 3 meses em 25/09"; 6105…6109 idem (idades 3 m 0 d a 3 m 20 d).
- **Ações →** Manter → tela 8 · Remover → o animal sai da espera e vai para o Histórico do protocolo como "Não se aplica — motivo" (reversível em 10 s via toast Desfazer).
- **Estados:** nenhum animal novo: "Nada novo desde ontem". Animal já vacinado com registro válido: o sistema **nem entra na janela** (aparece só no relatório "já em dia").

#### Tela 8 — Aplicar / Agendar · Lista de espera
- **Rota:** `#/protocolos/agendar?tipo=preventivo`
- **Objetivo:** ver todos os animais que esperam por vacina/exame e escolher qual grupo vai virar cronograma.
- **O que aparece:** aba **Aplicar / Agendar** ativa, chip Preventivo. Título "Lista de espera" com subtítulo "Animais na janela de aplicação. Aqui eles ficam até serem agendados — não aparecem na Agenda." Faixa de 3 números: **Aguardando 51** · **Atrasados na janela 31** (vermelho) · **Fecham em 7 dias 3**. Barra: `Todos os protocolos ▾ · Todos os lotes ▾ · Buscar…` + botão `Aplicação avulsa` (secundário). Tabela **agrupada por protocolo**, atrasados primeiro (mais antigo primeiro), cada grupo com cabeçalho recolhível: `Protocolo · Para quem · Janela (abre–fecha) · Situação · Na espera · [Montar cronograma]`. Linhas:
  - `Exame TB — reteste · Lote 02 – Média · 21/09 → 21/10 · ▲ Atrasado há 8 dias · 3`
  - `Clostridioses — dose 2 · Recria 2 · 25/09 → 25/10 · ▲ Atrasado há 4 dias · 22`
  - `Raiva — reforço · Lote 03 – Baixa · 12/09 → 27/10 · ▲ Atrasado há 2 dias · 6`
  - `IBR/BVD · Secas · 24/09 → 01/11 · ⏱ Devida 01/10 · 14`
  - `B19 · Bezerreiro · abre aos 3 m → 8 m · Na janela · 6 (+2 em 10 dias)`
  - `Aftosa · todo o rebanho · abre 21/10 · Janela ainda fechada · 0 (136 vão entrar)`
- **Ações →** `[Montar cronograma]` (por grupo) → tela 11 com o grupo inteiro já marcado · clicar na linha → tela 9 (detalhe) · `Aplicação avulsa` → tela 11 em modo "aplicar hoje".
- **Estados:** vazio: "Ninguém na lista de espera. Tudo em dia." com "Ver próximas janelas". Erro: faixa "Sem conexão — mostrando dados de 14:05". Grupo cuja janela **fecha** sem agendamento: selo âmbar "Fecha em 3 dias — o animal continua aqui, marcado Atrasado". Animal **nunca some sozinho** da espera.

#### Tela 9 — Lista de espera · detalhe de um protocolo
- **Rota:** `#/protocolos/agendar?tipo=preventivo&protocolo=raiva`
- **Objetivo:** escolher exatamente quais animais do grupo entram no cronograma.
- **O que aparece:** cabeçalho "Raiva — reforço · Lote 03 – Baixa · 6 na espera · janela 12/09 → 27/10". Tabela com caixa de seleção: `☐ Brinco · Nome · Lote · Motivo da entrada ("reforço anual venceu em 27/09") · Última dose · Situação (Atrasado há 2 d) · Carência (leite hoje? "vaca em lactação: sem carência") · ⋯ (Ver ficha · Não se aplica)`. Barra de ações fixa embaixo: "6 selecionados de 6 · `Marcar todos` · `Montar cronograma com os selecionados` (ouro)". Bloco lateral "Quem está de fora": lista dos que **ainda não entraram** ("2 completam 3 meses até 17/10") com aviso "Você pode incluir mesmo assim ↗ (fora da janela)".
- **Dados:** 2101, 2117, 2133, 2140, 2152, 2166 (Lote 03 – Baixa).
- **Ações →** Montar cronograma → tela 11 (só os selecionados) · "Não se aplica" (motivo) · Ver ficha → Rebanho.
- **Estados:** selecionar zero: botão desabilitado com texto "Marque pelo menos 1 animal". Animal vendido/morto desde a entrada: linha riscada "Saiu do rebanho — removido da espera" (tela 33d).

#### Tela 10 — Lista de espera · situações que precisam ficar claras
- **Rota:** `#/protocolos/agendar?tipo=preventivo` (variações de estado)
- **Objetivo:** definir a aparência das 4 situações da lista de espera para evitar dúvida.
- **O que aparece (quatro faixas de exemplo):** ① **Na janela** (cinza tracejado, "Na janela — dias restantes: 34") ② **Atrasado na janela** (vermelho + ▲, "Atrasado há 4 dias") ③ **Fecha em breve** (âmbar, "Fecha em 3 dias") ④ **Janela fechou** (vermelho escuro + ⏹, "Fechou em 21/10 · continua aqui — decida: agendar ou Não se aplica"). Legenda de uma linha no rodapé da lista. Um cartão explicativo permanente (dispensável) à direita: "**Lista de espera ≠ Agenda.** A Agenda só recebe o que você agenda."
- **Ações →** as mesmas da tela 8.
- **Estados:** desligar o cartão explicativo grava preferência (por usuário) — volta pelo "?".

---

### BLOCO C — Montar cronograma e agendar

#### Tela 11 — Montar cronograma · passo 1 "Animais"
- **Rota:** `#/protocolos/agendar/montar?protocolo=b19&passo=1` (página cheia, não drawer)
- **Objetivo:** decidir quem entra neste cronograma: quem está na janela e quem está fora, por conta da fazenda.
- **O que aparece:** cabeçalho "Cronograma · B19 · Bezerreiro" com estado `Em montagem` (azul-aço) e stepper `1 Animais · 2 Quando e quem · 3 Checklist · 4 Conferir e agendar`. Duas listas lado a lado:
  - **Esquerda — Na lista de espera (na janela)**: os animais do grupo, marcados, com contador "6 de 6".
  - **Direita — Neste cronograma**: os escolhidos, com marca `Na janela` (verde-claro) ou `Fora da janela` (âmbar + ícone + motivo abreviado). Botão `+ Incluir animal de fora da janela` (secundário). Contador "6 na janela · 2 fora da janela · **8 animais**".
  Rodapé: `Salvar rascunho` (fica "Em montagem" em Acompanhamento) · `Continuar` (marinho).
- **Dados:** 6104–6109 (na janela) + 6110 (2 m 20 d) e 6112 (2 m 12 d) fora da janela — extensão dos dados canônicos.
- **Ações →** Incluir de fora → tela 12 · Continuar → tela 13 · Salvar rascunho → tela 19 (estado Em montagem).
- **Estados:** nenhum animal → Continuar desabilitado. Animal já em outro cronograma agendado: linha cinza "Já agendado em 02/10 (Raiva)" — não pode ser marcado duas vezes no mesmo protocolo.

#### Tela 12 — Incluir animal fora da janela (com motivo)
- **Rota:** `#/protocolos/agendar/montar?protocolo=b19&passo=1&fora=1` (drawer sobre a tela 11)
- **Objetivo:** incluir animal que **não está na janela**, com motivo claro, sem bloquear.
- **O que aparece:** busca por brinco/nome/lote (teclado numérico no celular). Cartão do animal encontrado: "6110 Aurora · Bezerreiro · fêmea · **2 meses e 20 dias** · janela abre em 09/10 (faltam 10 dias) · sem B19 registrada". **Motivo (escolha obrigatória, nada pré-marcado):** `Aproveitar a visita do veterinário` · `Exigência de venda / GTA` · `Exposição ou leilão` · `Risco na região (surto)` · `Catch-up de categoria atrasada` · `Decisão do veterinário` · `Outro (texto)`. Caixa obrigatória "Incluir mesmo fora da janela". Aviso amarelo de consequência (não bloqueia): "B19 só vale de 3 a 8 meses; aplicar antes pode exigir revisão pelo veterinário." Botões `Incluir` (ouro) · `Cancelar`. Permite incluir vários seguidos ("Incluir e adicionar outro").
- **Dados:** motivo "Aproveitar a visita do veterinário — só volta em novembro". 6112 Serena idem.
- **Ações →** Incluir → volta à tela 11 com o animal marcado `Fora da janela` · a marca e o motivo acompanham o animal em **todas** as telas (Acompanhamento, Agenda, Concluídos, Sanidade).
- **Estados:** animal já na lista de espera de outro grupo: "Este animal já está na espera (Raiva) — incluir aqui não o tira de lá". Animal inativo/vendido: aviso vermelho, não deixa incluir. Após a aplicação, o animal fora da janela **conta como vacinado** (o ciclo dele avança normalmente).

#### Tela 13 — Montar cronograma · passo 2 "Quando e com quem" (agendamento)
- **Rota:** `#/protocolos/agendar/montar?protocolo=b19&passo=2`
- **Objetivo:** fixar o agendamento: data, hora, veterinário e aplicador.
- **O que aparece:** **Data** (seletor com a **janela desenhada em régua** e a data marcada; ao lado, "sugerida: 02/10, dia da visita" quando há veterinário na Agenda) · **Hora** · **Veterinário** (lista de cadastrados, nome + CRMV sempre visível; B19: campo obrigatório com selo "Exigido para B19") · **Quem aplica** (Jairo Nasser, Dr. Paulo Menezes, Cícero Alves, Marcos Lima; se vet obrigatório, só habilitados) · **Onde** (curral/lote) · observação. Cartão à direita "Como fica na Agenda": prévia de uma linha "Sex 02/10 · 09:00 · Vacinação B19 — Bezerreiro · 8 bezerras · Dr. Paulo Menezes · [Aplicar]".
- **Dados:** 02/10/2026 (sexta) 09:00 · Dr. Paulo Menezes (CRMV-MG 12345) · Marcos Lima assiste.
- **Ações →** Continuar → tela 14 · Voltar → 11.
- **Estados:** data **fora da janela** do protocolo (ex.: 20/10) = faixa âmbar "Fora da janela do protocolo — permitido, ficará registrado" (não bloqueia). Data passada: "Vai entrar como atrasado na Agenda". Conflito de agenda do veterinário: aviso "Dr. Paulo já tem IATF Recria 2 nessa hora — mudar a hora?" (não bloqueia).

#### Tela 14 — Montar cronograma · passo 3 "Checklist"
- **Rota:** `#/protocolos/agendar/montar?protocolo=b19&passo=3`
- **Objetivo:** cruzar veterinário, estoque, data, compra e financeiro **numa lista só**, com status claro de cada item.
- **O que aparece:** barra de progresso "3 de 7 itens resolvidos". Cada item é um cartão com ícone + texto de estado (**Pendente · Cumprido · Pulado · Desconsiderado**) e uma única ação principal:
  1. **Veterinário confirmou?** — nome + CRMV; botões `Sim` `Não` `Pular`. "Não" abre justificativa obrigatória e marca o cronograma com o selo vermelho "Veterinário não confirmou" (propaga a Acompanhamento, Agenda, Sanidade).
  2. **Estoque** — "8 doses de B19 · saldo 20 doses (BR-2604, validade 30/06/2027)". Botões `Vincular frasco` (abre o seletor de lote, FIFO sugerido) · `Desconsiderar estoque` · `Pular`.
  3. **Data** — "02/10/2026 09:00 · dentro da janela / fora da janela" (cumprido automaticamente pela tela 13).
  4. **Comunicação de compra/cotação** — aparece **só se** o estoque não cobre; senão mostra "Não necessária — estoque cobre".
  5. **Pagamento** — `Vincular a pagamento já realizado` · `Lançar conta a pagar` · `Pular` (tela 16).
  6. **Horário e lotes de manejo** — "Bezerreiro 8 animais" com `Marcar como revisado`.
  7. Itens da fazenda adicionados no cadastro.
  Rodapé: `Desconsiderar checklist (agendar direto)` (link discreto; pede confirmação de uma linha; texto reforçado para programa oficial como B19/aftosa) · `Continuar`.
- **Ações →** cada botão abre o drawer correspondente (telas 15/16) e volta marcando o item · Continuar → tela 17.
- **Estados:** o botão Continuar só habilita com tudo **Cumprido/Pulado/Desconsiderado** (nada Pendente); Pular abre uma linha "Confirme que não se aplica" (motivo opcional). Item do veterinário pulado em B19 mostra aviso "B19 exige aplicação de veterinário cadastrado — responsabilidade técnica".

#### Tela 15 — Checklist · estoque e comunicação de compra
- **Rota:** `#/protocolos/agendar/montar?protocolo=lepto&passo=3&item=estoque` (drawer)
- **Objetivo:** tratar o caso em que o estoque **não cobre** e comunicar a compra sem sair do fluxo.
- **O que aparece:** exemplo **Leptospirose (15/11, 151 animais)**: "Precisa de 151 doses · saldo **0** · faltam **151**". Bloco "Frascos disponíveis" (vazio) e três saídas: **① Comunicar compra** (abre mini-formulário: fornecedor sugerido Agro Vet, 151 doses, "necessário até 15/11", `Enviar pedido de cotação` → cria em Pedidos/Cotações e marca o item **Cumprido — cotação enviada em 29/09**), **② Já comprei** (vincular pedido/nota existente), **③ Aplicar mesmo sem estoque / Desconsiderar estoque** (aviso, não bloqueia). Mostra estimativa "R$ 317,10 (151 × R$ 2,10)". Se vários frascos: divide (Aftosa: 60 AF-2609 vence 15/10 ⚠ + 76 AF-2611) e **nunca mostra saldo negativo**; frasco vencido (IV-2605) nunca vem pré-selecionado.
- **Ações →** Enviar cotação → item vira Cumprido com link "Ver cotação" · Já comprei → escolhe pedido · Desconsiderar → item Desconsiderado.
- **Estados:** frasco a vencer ≤ 7 dias: aviso âmbar com escolha. Sem produto vinculado ao protocolo: "Escolha o produto" (não deixa item mudo).

#### Tela 16 — Checklist · financeiro (pagamento já feito ou conta a pagar)
- **Rota:** `#/protocolos/agendar/montar?protocolo=b19&passo=3&item=financeiro` (drawer)
- **Objetivo:** ligar o custo do protocolo ao financeiro, sem duplicar lançamento.
- **O que aparece:** duas abas no drawer.
  - **Vincular pagamento já realizado:** lista de contas **já pagas** do Financeiro filtradas por fornecedor/produto: "Agro Vet · 12/09 · R$ 128,00 · vacinas B19 (20 doses) · pago". Selecionar → mostra "Cobre 20 doses; este cronograma usa 8 (R$ 51,20, 40%)" e opção "Vincular o valor inteiro / só o proporcional".
  - **Lançar conta a pagar:** formulário pré-preenchido — fornecedor/serviço "Dr. Paulo Menezes — honorários da visita", descrição "Vacinação B19 — Bezerreiro 02/10", **valor R$ 350,00**, vencimento (sugere 10 dias depois), centro de custo "Sanidade", forma de pagamento. `Salvar e vincular` (ouro).
  Bloco persistente "Financeiro deste cronograma" no cabeçalho dos passos: `Pendente` (âmbar) / `Vinculado — R$ 51,20` / `Conta a pagar — R$ 350,00 vence 12/10` + link "Ver lançamento".
- **Ações →** Salvar e vincular / Vincular → item Cumprido · Pular → item Pulado (o convite permanece no bloco persistente).
- **Estados:** sem pagamento encontrado: "Nenhuma compra paga encontrada para B19. [Lançar conta a pagar]". Pagamento já vinculado a outro cronograma: aviso "Já usa 100% em 01/09".

#### Tela 17 — Montar cronograma · passo 4 "Conferir e agendar"
- **Rota:** `#/protocolos/agendar/montar?protocolo=b19&passo=4`
- **Objetivo:** mostrar as **consequências** antes de agendar.
- **O que aparece:** resumo em frases + tabela: "**Vacinação B19 — Bezerreiro** · sexta 02/10/2026, 09:00 · Dr. Paulo Menezes (CRMV-MG 12345)". Consequências (checklist visual): ✔ "8 animais saem da lista de espera (6 na janela, **2 fora da janela**: 6110, 6112)" · ✔ "vai aparecer na **Agenda** em 02/10 como 1 tarefa" · ✔ "8 doses vinculadas ao frasco BR-2604 (saldo depois: 12)" · ✔ "custo R$ 51,20 vinculado ao pagamento de 12/09; honorário R$ 350,00 a pagar em 12/10" · ⚠ "carência: nenhuma". Estado do checklist: "7 de 7 resolvidos (1 pulado: horário)". Botões: `Agendar` (ouro, principal), `Voltar e ajustar`, `Salvar como rascunho`.
- **Ações →** Agendar → tela 18 · Salvar rascunho → tela 19.
- **Estados:** se qualquer item ficou Pendente: `Agendar` fica desabilitado e a linha do item aparece em vermelho com link "resolver". Falha ao gravar: "Nada foi agendado · [Tentar de novo]" (operação atômica).

#### Tela 18 — Agendado! · o que acontece agora
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo&agendamento=b19-0210&novo=1`
- **Objetivo:** confirmar e mostrar onde o dono vai ver o agendamento; fecha o "meio" do fluxo.
- **O que aparece:** faixa verde "**Agendado** para sexta 02/10 às 09:00". Cartão de 3 setas: "Foi para a **Agenda** de 02/10 ▸ [Ver na Agenda]" · "Você acompanha em **Protocolos › Acompanhamento** ▸" · "Os 2 animais que sobraram na espera (nenhum) continuam na **Lista de espera**". Toast **Desfazer (10 s)** que devolve os animais à espera e apaga o agendamento.
- **Ações →** Ver na Agenda → `agenda.html#/agenda?visao=semana&dia=02-10` (tela 21b) · Ver em Acompanhamento → tela 19 · Voltar à lista de espera → tela 8 (B19 agora com 0).
- **Estados:** falha de sincronização (offline): "Salvo neste aparelho — envia quando voltar a conexão" com selo "N pendentes".

---

### BLOCO D — Acompanhamento, Agenda e aplicar

#### Tela 19 — Acompanhamento · o que já está agendado
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo` (visões `?visao=lista|calendario`)
- **Objetivo:** ver todos os cronogramas do preventivo em um lugar e agir.
- **O que aparece:** aba Acompanhamento ativa, chip Preventivo. Faixa de 3 números: **Hoje 1** · **Atrasados 0** · **Agendados 3 (próximos 30 d)** + link "Na lista de espera: 51 ▸". Barra: `Lista | Calendário` · `Todos os protocolos ▾` · `Todos os estados ▾` · busca. Tabela (atrasados e hoje primeiro): `Estado · Protocolo · Para quem (n animais) · Data e hora · Veterinário (CRMV) · Estoque · Financeiro · Checklist (5/7) · [Aplicar] ⋯`. Linhas:
  - `⏱ Hoje · Vermifugação (ivermectina) · Recria 1 · 20 novilhas · 29/09 · Cícero Alves · IV-2610 · pendente · 7/7 · [Aplicar]`
  - `● Agendado · B19 · Bezerreiro · 8 bezerras (2 fora da janela) · 02/10 09:00 · Dr. Paulo Menezes · BR-2604 · vinculado · 7/7 · [Aplicar]` (desabilitado até o dia, com "Aplicar antes" em ⋯)
  - `● Em montagem · Clostridioses — dose 2 · Recria 2 · 22 novilhas · sem data · — · — · 2/6 · [Continuar montando]`
  - `● Agendado · IBR/BVD · Secas · 14 vacas · 05/10 · …`
  Modo Calendário: mês com pontos por dia e legenda; clicar no dia filtra a lista.
- **Ações →** Clicar na linha → drawer tela 20 · `[Aplicar]` → tela 22 · `Continuar montando` → tela 11/14 · ⋯ Adiar/Cancelar/Reabrir.
- **Estados:** vazio "Nada agendado. Veja a lista de espera ▸". Atrasado: vermelho + ▲ "Atrasado há 2 dias" (o agendamento passou e ninguém aplicou). Vet não confirmou: selo vermelho "Veterinário não confirmou" na linha.

#### Tela 20 — Detalhe do agendamento (drawer)
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo&agendamento=b19-0210`
- **Objetivo:** consultar/ajustar um agendamento sem sair da lista.
- **O que aparece:** cabeçalho "B19 · Bezerreiro · sex 02/10 09:00" + estado + botões `Aplicar` (primário) · `Adiar` · `Reabrir para editar` · ⋯ Cancelar. Bloco financeiro persistente e ficha de carência. Abas: **Animais** (8, com marcas `Na janela`/`Fora da janela` e motivo; remover/incluir mais) · **Checklist** (os 7 itens, editáveis) · **Histórico** (quem criou, quem incluiu fora da janela, itens pulados, mudanças de data — quem/quando).
- **Ações →** Aplicar → tela 22 · Adiar/Cancelar → tela 33 · incluir animal → tela 12 (volta ao drawer).
- **Estados:** já agendado e alguém incluiu animal depois do estoque vinculado → o item Estoque volta a "Revisar" (âmbar).

#### Tela 21 — Agenda · o agendamento no dia (e o que NÃO aparece)
- **Rota:** `agenda.html#/agenda?visao=hoje` e `…?visao=semana` (21b)
- **Objetivo:** mostrar o agendamento entrando na Agenda **no dia** e provar que a lista de espera não entra.
- **O que aparece:** Agenda como no mockup atual (faixa de 3 números, Hoje/Semana/Mês, calendário lateral). Na lista de **Hoje**, a linha de agendamento: ícone de sanidade + **"Vermifugação (ivermectina) — Recria 1"** · "20 novilhas · 4,6 mL por animal · 92 mL · frasco IV-2610" · responsável "Cícero Alves" · hora · **`Aplicar`** (marinho) · ⋯ (Adiar · Ver animais · Abrir em Protocolos). Na **Semana**, o B19 aparece somente em **sex 02/10 09:00** como **uma** linha ("8 bezerras · Dr. Paulo Menezes"). Uma linha informativa discreta no rodapé de Hoje: "Animais na janela de aplicação ficam em **Protocolos › Lista de espera** (51) — não entram aqui".
- **Dados:** Raiva (6 animais), Clostridioses (22) e Exame TB (3) **não** aparecem na Agenda enquanto forem só lista de espera. Efeito nos números canônicos: "Atrasadas da Agenda" cai de 4 para 1 (só a pesagem); "Hoje 15" mantém a Vermifugação porque **ela foi agendada** (ver §5, A0).
- **Ações →** Aplicar → tela 23 (mesmo drawer) · Abrir em Protocolos → tela 20.
- **Estados:** agendamento atrasado (data passou, ninguém aplicou): entra em **Atrasadas** da Agenda com "há N dias". Dia vazio: "Nada agendado hoje. Próximo: B19 em 02/10."

#### Tela 22 — Aplicar (aberto em Protocolos › Acompanhamento)
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo&aplicar=verm-2909`
- **Objetivo:** dar a baixa real da aplicação, animal por animal, com estoque, dose e responsável.
- **O que aparece:** drawer largo "Aplicar · Vermifugação — Recria 1 · 29/09". Topo: "Aberto de: Protocolos › Acompanhamento". Faixa "Marcar todos como aplicados ✓" (ação em massa). Tabela por animal: `☑ Brinco · Nome · Aplicou? (Sim/Não) · Dose (4,6 mL por 230 kg) · Frasco/lote (validade) · Via (SC, travada) · Observação`. Bloco comum: **Frasco** (IV-2610 pré-selecionado; **IV-2605 vencido nunca pré-selecionado**, com "vencido — exige ciência"), **Quem aplicou** (pré-preenchido, troca em 1 toque), **Data e hora reais** (agora). **Resumo de consequência** (antes de confirmar): "20 novilhas · 92 mL · frasco IV-2610 (restam 908 mL) · **carne: carência 35 dias, até 03/11** · leite: não usar em lactação (n/a Recria 1) · custo R$ 38,64 · vai para Concluídos". Botão ouro `Aplicar (20 animais)`.
- **Ações →** Aplicar → tela 25 · Cancelar.
- **Estados:** lote vencido: linha vermelha, não confirma (troque o lote). Lote a vencer ≤ 7 dias: 1 confirmação por lote. Estoque insuficiente: aviso âmbar, permite seguir ("aplicar mesmo assim" registra divergência). Vet obrigatório sem vet: tela 33f. **Animal marcado "Não"**: pede motivo (Vendido · Doente · Não localizado · Outro) e o pós-aplicação (tela 26).

#### Tela 23 — Aplicar (aberto pela Agenda, no dia)
- **Rota:** `agenda.html#/agenda?visao=hoje&aplicar=verm-2909`
- **Objetivo:** mostrar que é **a mesma aplicação**, com o mesmo resultado, a partir da Agenda.
- **O que aparece:** exatamente o drawer da tela 22, com "Aberto de: Agenda" e o link `Ver cronograma em Protocolos ▸`. Ao confirmar, a linha some da Agenda com toast **"Feito · Desfazer (10 s)"**; no Acompanhamento o cronograma vai a Concluídos. Se a aplicação foi feita em Protocolos, a Agenda já não mostra a tarefa (mesma fonte).
- **Ações →** Aplicar → tela 25 · Desfazer estorna estoque e volta o cronograma a Agendado.
- **Estados:** duplo clique/offline não duplica (idempotente). Aplicação já feita por outro usuário: "Já aplicada por Cícero às 13:50" e a linha some.

#### Tela 24 — Aplicar exame (TB): inoculação e leitura em 72 h
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo&aplicar=tb-2909`
- **Objetivo:** cobrir o exame, que tem duas etapas (inocular hoje, ler em 72 h) e resultado por animal.
- **O que aparece:** "Aplicar · Exame TB — reteste · Lote 02 – Média · 3 animais". **Etapa 1 — Inoculação (hoje):** tuberculina **TU-2608** (validade 31/01/2027, saldo 100 doses), via intradérmica (travada), aplicador **veterinário habilitado** (aviso). `Confirmar inoculação` cria automaticamente o **agendamento da leitura**: "Leitura em 02/10 às 14:05 (72 h) — vai para a Agenda". **Etapa 2 — Leitura:** por animal `Negativo · Positivo (reagente) · Inconclusivo`; leitura só habilita a partir de 72 h (ou justificativa). Positivo grava por animal com nº do laudo opcional e mostra **banner persistente** "Reagente — notificar serviço veterinário oficial [☐ Notificação registrada — quem/quando]"; o "animal em dia" fica bloqueado para ele.
- **Dados:** 4201 Serena, 4207 Estrela, 4215 Bonita; 4207 reagente no exemplo.
- **Ações →** Confirmar inoculação → some da lista de espera/entra em Agendado (leitura) · Confirmar leitura → Concluídos (tela 27).
- **Estados:** leitura antes das 72 h: bloqueia com aviso e opção "Justificar". Exame sem baixa de estoque de vacina (usa tuberculina como insumo do exame).

#### Tela 25 — Aplicação concluída · resumo do que foi feito
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo&concluido=verm-2909`
- **Objetivo:** dar fecho e mostrar o que o sistema fez sozinho.
- **O que aparece:** faixa verde "**Aplicado** · Vermifugação — Recria 1 · 20 animais · 29/09/2026 14:20". Lista de efeitos: ✔ "Estoque baixado: IV-2610 −92 mL (restam 908 mL)" ✔ "Carência de carne até 03/11 registrada nos 20 animais" ✔ "Custo R$ 38,64 vinculado ao pagamento de 12/09" ✔ "**Próxima janela criada:** Vermifugação de novo em 28/12 (a cada 90 dias)" ✔ "Foi para **Concluídos**". Botões: `Ver em Concluídos` · `Imprimir comprovante` · `Voltar ao Acompanhamento`.
- **Estados:** aplicação parcial (18 de 20): mostra "2 não aplicados → **decida**" e abre a tela 26. Falha ao baixar estoque: aplicação **fica registrada** e o item de estoque vira "Revisar" (nunca perde o registro).

#### Tela 26 — Pendências pós-aplicação (quem não foi aplicado)
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo&pendencias=verm-2909`
- **Objetivo:** decidir o destino de quem ficou de fora, sem sumir com o animal.
- **O que aparece:** "2 animais não foram aplicados" com tabela `Brinco · Motivo · O que fazer`: `5109 · Não localizado · ( ) Voltar para a lista de espera (padrão) ( ) Não se aplica`; `5114 · Doente · ( ) Voltar para a lista de espera ( ) Não se aplica`. Botão `Confirmar`.
- **Ações →** Confirmar → os "voltar" reaparecem na lista de espera com o selo "Não aplicado em 29/09 — motivo" (tela 8) · "Não se aplica" vai a Concluídos como "Não se aplica — motivo".
- **Estados:** todos aplicados: a tela nem aparece.

---

### BLOCO E — Concluídos, Sanidade e Lançamentos

#### Tela 27 — Concluídos (histórico)
- **Rota:** `#/protocolos/concluidos?tipo=preventivo`
- **Objetivo:** ver o que já foi aplicado/lido, por cronograma e por animal, e exportar.
- **O que aparece:** aba Concluídos, chip Preventivo. Faixa de 3 números: **Concluídos no ano 38** · **Animais atendidos 412** · **Reagentes 1** (vermelho, "1 aguarda notificação"). Filtros: período, protocolo, produto/lote, animal, veterinário, `Fora da janela apenas`. Tabela: `Data · Protocolo · Para quem (n) · Aplicados/Não aplicados · Fora da janela (n) · Veterinário/aplicador · Frasco/lote · Custo · [Ver] [Comprovante]`. Botão `Exportar Excel/PDF`. Alternar `Por cronograma | Por animal` (carteira do animal).
- **Dados:** 29/09 · Vermifugação — Recria 1 · 20 · 0 · — · Cícero Alves · IV-2610 · R$ 38,64.
- **Ações →** Ver → tela 28 · Comprovante ("animal em dia": bloqueado para o reagente) · Exportar.
- **Estados:** vazio "Nada concluído neste período". Desfazer só até a janela de correção (10 s no toast; depois é correção auditada por admin).

#### Tela 28 — Detalhe de um concluído (imutável, só observação)
- **Rota:** `#/protocolos/concluidos?tipo=preventivo&item=b19-0210`
- **Objetivo:** ter o registro completo e auditável.
- **O que aparece:** cabeçalho "B19 · Bezerreiro · 02/10 · Aplicado" com selo **Fora da janela: 2** (âmbar). Abas: Animais (8, com dose, frasco, hora, quem aplicou) · Checklist (como ficou) · Financeiro (vínculos) · Histórico (linha do tempo) . Botões: `Adicionar observação` (aditivo) · `Imprimir comprovante` · `Exportar histórico (PDF)`.
- **Estados:** correção de aplicação errada: "Corrigir (admin)" abre caminho auditado com motivo, nunca edita silenciosamente.

#### Tela 29 — Sanidade › Vacinas e exames › Calendário (somente leitura)
- **Rota:** `#/sanidade/vacinas/calendario`
- **Objetivo:** visão temporal de tudo o que é preventivo, sem poder escrever.
- **O que aparece:** faixa "**Somente leitura** — aplicar e agendar em Protocolos ou na Agenda" (com links). Sub-abas: **Calendário · Em andamento · Concluídos · Cobertura**. Faixa de 3 números: Na janela **51** · Agendados **4** · Cobertura **79%**. Visões `Lista | Mês | Ano` (ano = matriz protocolo × mês). Cada linha ou dia traz **estado** (na janela · agendado · hoje · atrasado · concluído) e o link **`Abrir em Protocolos ▸`** (na espera) ou **`Abrir na Agenda ▸`** (agendado). Nenhum botão de escrever. Legenda de uma linha.
- **Dados:** 29/09 Vermifugação (Hoje, agendada) · 01/10 IBR/BVD (janela, 14 vacas) · 02/10 B19 (agendada, 8) · 05/11 Aftosa (janela abre 21/10; 136 animais).
- **Ações →** links de "agir" → telas 8/19/21 · Cobertura → tela 31.
- **Estados:** vazio (fazenda nova): "Sem protocolos. Cadastre em Protocolos ▸".

#### Tela 30 — Sanidade › Em andamento (somente leitura)
- **Rota:** `#/sanidade/vacinas/andamento`
- **Objetivo:** ver o que está em curso agora (na espera, em montagem, agendado, atrasado).
- **O que aparece:** tabela `Estado · Protocolo · Para quem · Data · Responsável · Estoque · Financeiro` com os estados da legenda; ordem: atrasados, hoje, próximos. Cada linha com `Abrir em Protocolos ▸`/`Abrir na Agenda ▸`. Sem `Aplicar`.
- **Estados:** vazio "Nada em andamento".

#### Tela 31 — Sanidade › Concluídos e Cobertura (somente leitura)
- **Rota:** `#/sanidade/vacinas/concluidos` e `#/sanidade/vacinas/cobertura`
- **Objetivo:** consultar histórico e cobertura do rebanho (a carteira que o dono elogiou).
- **O que aparece:** Concluídos = espelho enxuto da tela 27 (sem comprovante editável). Cobertura: faixa "Rebanho em dia 79% — 119 de 151 animais · 32 com pendência atrasada (22 + 6 + 3 + 1)", tabela protocolo × lote com %, "quem falta" (drill), carteira por animal, bloco Carência ("leite em carência: N vacas até dd/mm"). "Quem falta" leva a `Protocolos › Lista de espera` filtrada.
- **Ações →** Abrir em Protocolos.
- **Estados:** reagente TB (4207) marcado na cobertura e no comprovante bloqueado.

#### Tela 32 — Lançamentos · Sanitário (sem preventivo)
- **Rota:** `#/lancamentos/sanitario/curativo`
- **Objetivo:** mostrar que Lançamentos **não** contempla vacina/exame preventivos e para onde ir.
- **O que aparece:** Lançamentos › Sanitário com sub-abas **Curativo** (ativa) e **BST**. Faixa azul-aço: "**Vacinas e exames** (protocolo preventivo) são agendados e aplicados em **Protocolos**. [Ir para Protocolos › Aplicar/Agendar]". Formulário de curativo como hoje. A antiga sub-aba "Preventiva" **não existe**.
- **Ações →** link → tela 8.
- **Estados:** quem chega por link antigo `#/lancamentos/sanitario/preventivo` é redirecionado à tela 8 com faixa "Mudou de lugar".

---

### BLOCO F — Estados de exceção

#### Tela 33 — Exceções (seis cenas; cada uma é um pequeno drawer/cartão)
- **Rota:** `#/protocolos/acompanhamento?tipo=preventivo&agendamento=…&acao=adiar|pular|cancelar|…`
- **Objetivo:** deixar claro o que acontece quando o plano não sai como o previsto, sem perder animal nem estoque.

**33a — Adiar.** Botão `Adiar` (Acompanhamento e Agenda): "Nova data" (amanhã / +7 dias / data) · motivo **opcional** (grava "sem motivo informado" se vazio). Cronograma mantém checklist e animais, muda a data; a Agenda acompanha. Aviso se a nova data sai da janela ("fora da janela — permitido"). Adiar 3 vezes destaca "adiado 3×". Item crítico (leitura de exame): não adia em lote.

**33b — Pular esta rodada.** Motivo **obrigatório** (chips: Vacina já feita em outro lugar · Campanha oficial cobre · Não vamos fazer · Outro). Animais **voltam à lista de espera** (ou "Não se aplica" se escolhido). Fica em Concluídos como "Pulado".

**33c — Cancelar agendamento.** Confirmação inline (nada de `window.confirm`): "Cancelar devolve os animais à lista de espera, libera o estoque vinculado e mantém o histórico." Se já houve aplicação parcial, mostra o que é estornado.

**33d — Animal removido (vendido, morto, transferido).** Selo "Saiu do rebanho" na linha; some da contagem automática mantendo o histórico; **inclusão manual fora da janela** também sai (com aviso). Se saiu depois de aplicado: registro permanece.

**33e — Estoque insuficiente.** Tela 15: pode **comunicar compra**, **aplicar assim mesmo** (divergência registrada, "Divergência de estoque a revisar") ou **reduzir o grupo** (o excedente volta à lista de espera). Nunca bloqueia; nunca mostra saldo negativo.

**33f — Veterinário pendente.** Cronograma sem confirmação do veterinário mostra selo vermelho "Veterinário não confirmou" na Acompanhamento, Agenda e Sanidade. Em B19/TB (exigem vet): ao aplicar sem vet habilitado, aviso forte + ciência obrigatória registrada ("Aplicação sem médico veterinário habilitado — responsabilidade técnica") — não trava a fazenda, mas o comprovante fica marcado.

- **Ações →** todas voltam à tela de origem (19/20/21) com toast Desfazer (10 s) quando reversível.
- **Estados:** falha de rede: ação entra numa fila "N pendentes" e mostra "Salvo neste aparelho".

---

### Resumo da cobertura pedida pelo dono

| Pedido | Telas |
|---|---|
| Cadastro do protocolo | 2, 3, 4, 5, 6 |
| Entrada de animais na janela (automática e revisão) | 4 (prévia), 6, 7 |
| Lista de espera | 8, 9, 10 |
| Inserir animais na janela **e fora** (com motivo) | 11, 12 |
| Montar cronograma / agendamento | 11–18 |
| Checklist (vet, estoque/desconsiderar, data, compra/cotação, pagamento já feito, conta a pagar, outros) | 14, 15, 16 |
| Acompanhamento (o que já está agendado) | 19, 20 |
| Agenda no dia | 21 |
| Aplicar em Protocolos / mesma aplicação pela Agenda | 22, 23 (+ exame 24) |
| Conclusão e pendências | 25, 26 |
| Concluídos (histórico) | 27, 28 |
| Sanidade somente leitura (calendário, em andamento, concluídos) | 29, 30, 31 |
| Central de Protocolos | 1 |
| Lançamentos sem preventivo | 32 |
| Exceções | 33 (a–f) |

---

## 4. Princípios para ficar fácil e intuitivo — e onde reduzir cliques

1. **Cada tela responde uma pergunta só.** Lista de espera = "quem está esperando?"; Acompanhamento = "o que já está agendado?"; Agenda = "o que faço hoje?"; Concluídos = "o que já foi feito?"; Sanidade = "como está o rebanho?".
2. **O animal tem uma casa por vez.** Na espera **ou** num agendamento **ou** concluído. Uma etiqueta de estado na ficha do animal diz onde ele está.
3. **Um verbo por momento.** Montar cronograma → Agendar → Aplicar. O botão primário de cada tela é o próximo passo natural, e só um por tela.
4. **Pré-preenchimento agressivo.** Ao clicar `Montar cronograma`, os animais da janela já vêm marcados; a data sugerida vem da visita do veterinário; o veterinário, o aplicador e o checklist vêm do protocolo; o frasco vem por FIFO (nunca vencido).
5. **O sistema mostra a consequência antes de confirmar** (telas 17 e 22): quantos animais saem da espera, o que vai para a Agenda, quanto de estoque baixa, carência e custo.
6. **Nada bloqueia o campo.** Estoque, data fora da janela, veterinário pendente: avisam e registram. Trava dura só em lote vencido.
7. **Estado = ícone + texto + cor.** Nunca só cor. Mesma legenda em todas as telas.
8. **Toda ação reversível tem Desfazer de 10 s**; exceções irreversíveis explicam antes.
9. **Links, não instruções escritas.** Em lugar de "vá a Lançamentos › X", sempre um botão que leva lá.
10. **O que entra no sistema é visível de imediato.** Sem skeleton artificial (defeito relatado no mockup da Agenda); render direto; erro de rede mostra os últimos dados com aviso.
11. **Estado na URL:** aba, tipo, filtro e drawer sobrevivem ao F5 e podem ser enviados por link.
12. **Alvos ≥ 44 px e corpo de texto 16 px** (campo/celular); o app móvel só aplica e acompanha, nunca cadastra.

Onde reduzir cliques (comparado ao caminho atual de 5 a 10 cliques):
- **Montar em 3 cliques:** `Montar cronograma` (na lista de espera) → `Continuar` (data sugerida já preenchida) → `Agendar` (checklist do protocolo já ligado). Se o protocolo permite, `Agendar direto` no card da lista de espera usando os padrões (com opção "Desconsiderar checklist", uma linha de confirmação).
- **Aplicar em 2 cliques na Agenda:** `Aplicar` → `Aplicar (N animais)`, com "Marcar todos" já ativo e frasco pré-selecionado.
- **Agendar e aplicar hoje** em um fluxo só (Aplicação avulsa): passos 1 a 4 mais Aplicar contínuo, sem voltar à lista.
- **Ação em massa por padrão** (todos os animais marcados; desmarca quem foge da regra).
- **"Incluir e adicionar outro"** ao incluir animais fora da janela.
- **Checklist com atalhos:** `Sim` do veterinário e `Vincular frasco (FIFO)` são um clique; `Pular tudo que não se aplica` é um link único que abre uma confirmação só.
- **Um clique de "Ver na Agenda/Ver no Acompanhamento"** no fechamento, para o dono ver o resultado do que fez.

---

## 5. AMBIGUIDADES no pedido do dono — e minha recomendação

| # | Ambiguidade | Recomendação |
|---|---|---|
| **A0** | O mockup atual mostra Raiva/Clostridioses/TB atrasadas **na Agenda** (Agenda "Atrasadas 4"). Pela regra do dono, quem está na janela só aparece na lista de espera. | Aceitar a regra: essas 3 saem da Agenda e vão para a **lista de espera** (Atrasado na janela). **Atualizar `DADOS-CANONICOS.md`**: Agenda Atrasadas 4 → 1 (só a pesagem) enquanto ninguém agendar; M1 "Atrasadas 3" vira "Atrasados na janela". Só entram na Agenda quando agendados. |
| **A1** | "**Aplicar**" tem dois sentidos: "em Protocolos, aplicar transformaria em agendamento" e "em Acompanhamento, aplicar". | Nomear as duas ações diferentes: em **Aplicar/Agendar** o botão é **Montar cronograma → Agendar**; em **Acompanhamento** e na Agenda o botão é **Aplicar** (dar a baixa real). O nome da aba pode continuar "Aplicar / Agendar" (palavra do dono). |
| **A2** | **Cronograma × agendamento**: dois objetos ou um só? | Um objeto na tela: o **cronograma** (rodada com animais e checklist). O **agendamento** é o ato/estado de fixar data e responsável; o cartão que vai à Agenda chama-se "agendamento". Estados: Em montagem → Agendado. |
| **A3** | Lista de espera é **por protocolo** ou **uma só**? | Uma só tela agrupada por protocolo, com filtro global (protocolo, lote, situação). Também alcançável por protocolo (`?protocolo=`). |
| **A4** | O que acontece com o animal cuja **janela fecha** sem agendamento? | Continua na lista de espera como "Janela fechou — decida", nunca some sozinho. O dono agenda ou marca "Não se aplica". |
| **A5** | **Vários agendamentos** a partir da mesma janela (dividir o grupo em dois dias)? | Sim, permitido: quem não foi marcado fica na espera. Requer que a lista de espera seja por animal (não por ocorrência inteira). |
| **A6** | Na 2ª sub-aba da Agenda ("gerencial") o dono quer "programação projetada de… vacinas, exames", mas animais na janela **não podem** aparecer na Agenda. | Mostrar só **agendamentos futuros** e **datas de protocolo** (ex.: "Aftosa — janela abre 21/10 · 136 animais no futuro") como linha agregada com link para Protocolos; **nunca lista de animais na janela**. Pedir confirmação do dono. |
| **A7** | Animal incluído **fora da janela** e que **depois** entra na janela: aplicar antes conta? | Sim: a aplicação registrada vale; o animal entra no ciclo normal a partir da data aplicada e sai da espera futura. O motivo fica no histórico. |
| **A8** | **"Lançamentos serve para lançar, mas não contemplaria os protocolos preventivos."** Isso remove também a **aplicação avulsa** (vacinar hoje sem protocolo)? | Sim. A avulsa vira botão em Protocolos › Aplicar/Agendar (cria cronograma e aplica na hora). Lançamentos mantém curativo e BST. |
| **A9** | Exame tem **duas etapas** (inoculação e leitura em 72 h; coleta e resultado). Uma linha ou duas na Agenda? | Duas: ao confirmar a inoculação, o sistema cria o agendamento da leitura (+72 h). Uma linha por etapa; o resultado é lançado em Aplicar (leitura). |
| **A10** | O checklist **bloqueia** o agendamento? | Não bloqueia por conteúdo, mas nenhum item pode ficar **Pendente**: ou Cumprido, ou Pulado, ou Desconsiderado. Há também "Desconsiderar checklist" (uma linha de confirmação, com texto reforçado para programa oficial). |
| **A11** | "Vincular a **pagamento já realizado**": a compra costuma cobrir muitas doses; um cronograma usa parte. | Vincular **proporcional** (doses usadas × custo/dose) com opção de valor inteiro; um pagamento pode atender vários cronogramas; alerta se ultrapassa 100%. |
| **A12** | "**Lançar contas a pagar decorrente do protocolo**": qual valor? (vacina, honorário, ambos) | Formulário pré-preenchido com **duas sugestões** independentes: custo do produto e honorário do veterinário; o dono escolhe uma ou as duas. |
| **A13** | **Sanidade somente leitura**: como corrigir um registro errado? | Só em **Protocolos › Concluídos**, "Corrigir (admin)" com motivo e trilha de auditoria; Sanidade tem um link para lá. |
| **A14** | Sanidade tem **Cobertura**? O dono listou só "calendário, em andamento e concluídos". | Manter como 4ª leitura (ele elogiou o resultado geral; a carteira e a % em dia são a resposta gerencial). Pode ser ocultada se ele preferir só 3. |
| **A15** | A palavra **"protocolo"**: hoje é sequência de dias (IATF, curativo). Aqui, "protocolo preventivo" é recorrente e por grupo. | Manter "Protocolo preventivo" (é o vocabulário do dono) e explicar no cadastro com uma linha ("repete sozinho; entra por janela"). Não misturar com curativo na mesma tabela; o chip de tipo separa. |
| **A16** | **Aplicação pelo app móvel**: fora do escopo do pedido. | Recomendar app com a mesma lógica (lista de hoje + Aplicar; cadastro nunca), a definir depois. |
| **A17** | Papéis: quem pode montar/agendar/aplicar/corrigir? | Proposta: gestor monta e agenda; tratador/veterinário aplica; correção só admin. Confirmar com o dono. |

---

## 6. Compatibilidade com o que já existe (para o consolidador)

- **Reaproveita:** `Ocorrência`/cronograma (estados, checklist, incluir fora da janela, desconsiderar), `PopupVinculoFinanceiro` (vira item + bloco), `DetalheProtocolo` (grade animal × dia — para IATF etc.), `RelatorioEventosVidaView` (base da lista de espera e da seleção de animais), mobile `Cronogramas.tsx` (padrão cartão + decisão inline).
- **Muda de lugar:** cadastro preventivo (fica em Protocolos, como hoje, agora como o tipo Preventivo com 3 passos + conferir); aplicação (sai de Lançamentos/Sanidade; fica em Protocolos e Agenda); Sanidade preventiva (só leitura).
- **Novo:** lista de espera como leitura por animal (janelas com "abre/fecha"), agendamento que só vai à Agenda no dia, item de checklist de compra/cotação e vínculo de pagamento, botão Aplicação avulsa.
- **Visual:** nenhum token novo. Novos componentes usam os existentes: faixa de 3 números, tabela com cabeçalho de grupo, drawer, badge ícone+texto, stepper, régua de janela (linha fina marinho com marcador ouro).
