# Auditoria — Protocolo preventivo / calendário de vacina e Agenda

> Method: dual-agent (Assessment A = revisão de design isolada · Assessment B = detector + navegador isolado), mais 4 lentes de análise (audit · adapt · harden · optimize · distill · clarify · layout · typeset · colorize · onboard · delight · quieter/bolder) por alvo. Nenhum código de produto foi alterado nesta etapa.
> Alvo 1: **Sanidade › Preventiva + Central de Protocolos** (tratados como um módulo só, como pedido).
> Alvo 2: **Agenda**.
> Materiais brutos: mapas de código, relatórios A/B/L1/L2 (guardados na sessão; os fatos-chave estão reproduzidos abaixo com `arquivo:linha`).
> Limite honesto: o detector estático encontrou muito pouco (1 achado em cada alvo). Os problemas graves são de **arquitetura de informação, vocabulário e comportamento**, que detector nenhum vê.

---

## 0. Placar

| Alvo | Nielsen (A) | Carga cognitiva | Audit | Adapt | Harden | Optimize |
|---|---|---|---|---|---|---|
| Preventivo + Protocolos | **15/40 (Poor)** | 7 de 8 itens falham | a11y 1 · perf 2 · tema 3 · responsivo 2 | 2 | 1 | 2 |
| Agenda | **19/40** (rodada anterior 22) | 5 de 8 falham | 1 | 2 | 1 | 1 |

Veredito de especificidade (ambos): a **casca visual é autoral** (tokens, cantos de 2px, filetes de categoria, caixa-alta nos rótulos leem como CowData); a **estrutura e o vocabulário são do modelo de dados, não da fazenda**. O problema não é skin — é arquitetura e texto.

---

## 1. Diagnóstico-raiz (uma frase por alvo)

**Preventivo + Protocolos** — *uma única coisa do mundo real (a vacina que precisa ser dada a um grupo numa data) está espalhada em 6 nomes, 4 telas de leitura, 5 portas de escrita e 3 tabelas.* E a Sanidade, onde o usuário procura, **não tem "o que fazer agora" nem "registrar aplicação"**.

**Agenda** — *a tela que devia responder "o que faço hoje, em qual lote, com qual insumo" abre com 8 contadores, legenda, listas e comunicados; a lista "Hoje" começa ~3 telas abaixo do topo.* Cada clique em "Realizado" apaga a lista (skeleton total) e o usuário perde o lugar.

---

## 2. Achados de maior peso — Sanidade › Preventiva + Central de Protocolos

### P0
1. **Falta a tarefa central.** Sanidade abre em *Curativa* (`sanidade/page.tsx:2850`); a Preventiva abre num relatório passivo de Aplicações (KPI "0", 8 filtros). Não há botão **Registrar aplicação** no calendário nem no cronograma (o detalhe não conclui a aplicação — o "loop" para dar baixa é Agenda → Sanidade → Agenda).
2. **Um objeto, 4–6 nomes, 5 casas.** Regra = "Protocolo cadastrado" = "Calendário sanitário"; Cronograma = Ocorrência = Evento = Janela; a mesma escrita `POST /sanidade/calendario/cadastrar-preventivo` tem **cinco portas** (Lançamentos › Avulso, Lançamentos › Calendário sanitário, Central › Lançamento, baixa inline da Agenda, drill-down "Ver animais"). O texto de `sanidade/page.tsx:1380` manda "usar Lançamentos" mesmo quando o usuário está dentro da Central.
3. **Isolamento entre fazendas (segurança de dados):** cache offline do app com chave fixa `mob_cache_*` sem fazenda/usuário e não limpo no logout (`lib/offline.ts:206-218`); rascunho do wizard em `localStorage` sem escopo, restaurado em silêncio, vale para 6 cadastros (`WizardProtocolo.tsx:73-93,136-146`).
4. **Escrita dupla sem rollback:** salvar regra do calendário faz 2 escritas (evento e depois regra) (`FormCalendarioSanitario.tsx:289-311`). Falha na segunda deixa evento órfão; o retry duplica; editar regra sobrescreve o evento compartilhado.

### P1
5. **Protocolo Customizado some da própria Central:** nasce com *Tipo* vazio (`CadastroProtocolosCustomizados.tsx:26`) e o backend descarta lançamentos sem tipo do Acompanhamento/Histórico (`central_protocolos.py:181-183`).
6. **Baixa que "engole" erro:** `FormPreventivoAplicacao.tsx:270-276` tem `.catch(() => {})` — a aplicação é gravada e a pendência continua, permitindo **reaplicar a vacina**.
7. **Navegação sem URL e com nível invisível:** Sanidade tem 3 filhos de Preventiva (Aplicações · Calendário · Histórico) + um 3º nível dentro de Calendário (Calendário · Regras · Cronogramas · Resultados de exames) que não está na Sidebar nem na URL. A Central lê `?aba=` só na montagem e nunca grava — F5 volta ao default. Profundidade até "regra de vacina": ~7–9 cliques.
8. **Calendário sem atrasados:** só de hoje a +180 dias (`sanidade/page.tsx:689-692`); o único KPI "Vencidas" mora em `OcorrenciasView`, **inalcançável** (`:916`, `:1389-1407`).
9. **Falha de API vira "lista vazia"** (`protocolos/page.tsx:240,1122`, `FormAplicarCalendarioSanitario.tsx:30`): o usuário acha que perdeu cadastros.
10. **Datas em UTC** (`toISOString().slice(0,10)`, ~7 pontos): depois das ~21h locais vira "amanhã" e grava data errada.
11. **Mobile diverge do site:** no app, "Calendário" (em Lançar) *cria regra*; no site, é consulta. Cronogramas mobile é online-only, botões de ~26px (piso do app: 56px).
12. **A11y estrutural:** 0 `aria-*`, 0 `role=`, 0 `htmlFor` no módulo; `<tr onClick>` sem teclado (`sanidade/page.tsx:328,1636`); ~20 `window.confirm/prompt/alert`.

### P2/P3 (resumo)
- Vazamento de texto de desenvolvimento para o usuário: "Fase 2" (`:1283`), "não cria lançamento financeiro de verdade" (`:1288`), "em construção" (`:941`), `usa_cronograma` (`:1606`), "Desconsiderar cronograma", "gatilho".
- Lápis "Editar regra" leva à lista, sem id, visível só para admin (`:1476`).
- Título da Central diz "4 tipos"; há 5 cards (`protocolos/page.tsx:1150`). Legenda da Preventiva fala de BST.
- `WizardProtocolo` com `borderRadius:14` + sombra (`:202`) contra DESIGN.md (2px, sem sombra); passo "Critérios" vazio em 3 wizards; rgba de vinho hardcoded.
- Rolagem aninhada `calc(100vh-220px)` em 10 pontos; grid fixo de 7 colunas no IATF.
- Carga: rebanho inteiro baixado em `protocolos/page.tsx:1122` e `HistoricoPreventivoView.tsx:39`; `/sanidade/aplicacoes` sem paginação em 4 telas; `estoque` até 3×, `principios-ativos` até 5×.
- Detector: `layout-transition` em `sanidade/page.tsx:1218` (`transition: width` na barra do checklist) — verdadeiro, baixo impacto.

### Funcionalidades ausentes para um calendário vacinal *funcional*
Atrasadas e "esta semana" · registrar aplicação da linha (com baixa de estoque) · **cobertura vacinal** por vacina/lote · **carteira do animal** · **carência de leite/carne** (dado já existe no Catálogo, `api.ts:5632`) · reforço/multidose · folha de campo impressa · visão anual · lembretes · estoque previsto × necessário · lote/validade do frasco · exames pendentes (TB/brucelose) · custo previsto × realizado.

### O que já é bom (preservar)
- O **modal de detalhe do protocolo** (grade animal × dia, baixa com frasco FIFO, Encerrar/Cancelar/Reabrir inline, folha de campo PDF/Excel).
- O **motor de regras por evento de vida** e a projeção por época.
- A engenharia do wizard (rascunho, idempotência, reduced-motion, preview de cronograma) — só o escopo do rascunho e o visual precisam corrigir.
- O banner de conclusão do IATF: é o melhor "fim" do produto e deveria ser padrão.

---

## 3. Achados de maior peso — Agenda

### P0
1. **Desfazer que estorna pela metade:** `DELETE /agenda/realizados` (`agenda.py:2817-2870`) não estorna `protocolo_sanitario_`, `aplic_agendada_` nem `vacina_pre_parto_`. O evento volta a pendente e o próximo "Realizado" **baixa estoque e aplicação em dobro**. O card "Concluídos" oferece esse Desfazer (`agenda/page.tsx:2455-2465`).
2. **Falha de rede tratada como logout** (`AuthShell.tsx:110-118` + `lib/api.ts:1281-1288`), pendente desde a rodada anterior — com erro cru "Agenda error: 500" e `setAgenda(null)` apagando a tela mesmo após ação bem-sucedida (`:404-411`).
3. **`GET /agenda/` escreve no banco** (`agenda.py:462-463, 304-334, 337+`): `_gerar_agenda_recorrente` e `_gerar_auditorias_diarias` sem escopo de fazenda, N+1, commit por linha — recorrentes podem duplicar sob concorrência.

### P1
4. **"Hoje" está enterrado.** Ordem real: filtros → cabeçalho → 8 KPIs em 3 grupos → legenda → listas expansíveis (+ `PainelLancarBst`) → Concluídos → Comunicados → **só então a timeline** (`:2510`). O app mobile já acerta (Lista/Semana/Mês, atrasadas primeiro).
5. **Skeleton total após cada ação:** `carregar()` (`:403-408`) recomputa o motor inteiro (≥62 queries; tabelas inteiras) e troca a lista por `TelaSkeleton` (`:2522`). Medido no navegador: ~26 requests na carga (13 endpoints ×2 em dev/StrictMode), **6,7 s até conteúdo útil**, `/animais/?` (rebanho inteiro) e `/estoque/` já no início.
6. **Remount confirmado no navegador:** `BotaoRealizado` (`:904`), `BotaoDescartar` (`:924`), `PainelConfirmarBaixa` (`:951`), `BotaoAgendar` (`:2077`), `ExportarAgendaBotoes` (`:2087`) são definidos *dentro* do render: Enter em "Realizado" → nó antigo sai do DOM, foco vai para `BODY`. Inferência forte: o painel de baixa perde o foco a cada tecla.
7. **Tipos de evento sem caminho de resolução:** `patrimonio_*` mostra "Realizado" e o backend responde 400 (`agenda.py:2479-2482`) — parece bug; `pesagem_rebanho` diz "Toque para lançar" sem botão; `lida` sem UI (foto/insumo ignorados); `dieta_analise` só "Ir para Dieta" e nunca sai; `colostragem/igg/aviso_exame_veterinario` só link. Qualquer `e.link` é rotulado **"Importar agora"** (`:1241`).
8. **Baixa em lote e "incluir fora da janela" = N chamadas sequenciais**, sem progresso nem retomada (`:741-748`, `:249`); `marcar_realizado` grava o `EventoRealizado` *antes* da baixa (`agenda.py:2531-2545`): baixa que falha some da agenda; duplo POST estoura `IntegrityError`, e a fila offline reenvia.
9. **Datas em UTC:** `today()` (`lib/api.ts:8359`) e o backend `date.today()`/`utcnow` (13 pontos) — a partir de ~21h locais o dia vira; `data: date = date.today()` como default de parâmetro (`agenda.py:453`) é avaliado **no import** (agenda "do dia do deploy" para Capa/sino).
10. **Sem estado na URL nem persistência:** ~60 `useState`; F5 zera filtros, dias abertos, doses digitadas. Único deep-link: `?abrir_sugestao=`. Sem visão Semana no site; "Novo evento" só existe dentro do overlay do Calendário; não há Adiar genérico nem editar/excluir evento manual.
11. **Alvos de toque:** 89 elementos <44px na `main` desktop, 54 no mobile-web (Excel 83×34, "Sim" da confirmação 38×26, busca 19px de altura, sidebar 28px) contra o compromisso "sol, luva" do PRODUCT.md. O `/app` real tem 0 abaixo de 44px.

### P2/P3 (resumo)
- **5 verbos para "fiz"**: Realizado · Cumpriu? · Confirmar baixa · Dar baixa · Descartar. Coluna "Origem" incoerente ("manual" para IATF, "auto" para cronograma).
- Jargão sem glossário: IATF, D0/D7, PEV, DEL, BST, Retoque, Scratch.
- A11y: `<tr onClick>` sem teclado em 7 linhas, 3 modais próprios sem `role=dialog`/Esc, toasts sem `aria-live`, categoria só por cor; `outline:none`; ~140 usos de fonte <0.8rem (piso 0.66rem) e 329 estilos inline; `borderRadius:6` remanescente (`:949`, `:1141`, `:1413`).
- "Dia fechado" (o melhor momento da tela) é frágil: `totalHojeRef` guarda o maior N visto na sessão — recarregar depois de 6 de 9 mostra "3 de 3".
- `fazenda_id IN (id, NULL)` em `EventoRealizado` (vazamento entre tenants); hash de evento colide em eventos manuais idênticos.
- Detector: `side-tab` em `:2537` (borda esquerda 3px no aviso "Dia fechado") — verdadeiro, baixo.
- Monólito de 2.816 linhas (achado P1 da rodada anterior *não* foi feito).
- Do mockup anterior (`agenda.html`) ficou pendente: grupos Rebanho/Produção, badge "N itens • N críticos" por dia.

### O que já é bom (preservar)
Regra de negócio como interface (IATF por subconjunto de animais e frasco; D11 abre a gaveta de Inseminação com prefill) · baixa em lote com "Cumpriu? Sim/Não" · "Hoje" aberto · **Fechar o dia** (dispara só na transição >0→0, tom seco, respeita reduced-motion) · exportar Excel/PDF · a agenda mobile (offline, otimista, Lista/Semana/Mês) como referência.

---

## 4. Arquitetura de informação: dividir · juntar · alterar

### 4.1 Preventivo + Protocolos

Modelo mental canônico (proposto): **Regra gera Rodadas; a Rodada tem animais e termina em Baixa. Protocolo é uma sequência de dias/etapas num grupo de animais.** Vacina é recorrente e por grupo; protocolo é sequência e por animal/lote. São objetos diferentes e **não devem viver no mesmo cartão**.

| Decisão | Ação |
|---|---|
| **Dividir** | Tirar "Preventivo" de dentro da Central. Preventivo (vacinas/exames do calendário) vira módulo próprio **Vacinas e exames**; a Central fica só com protocolos de ciclo (IATF, Indução, Curativo, Customizado) + Lida como "Tarefa da fazenda". |
| **Juntar** | As 5 portas de escrita → **um** painel "Registrar aplicação". Aplicações + Histórico + Resultados de exames → **um** Histórico. Cronogramas + Ocorrências + Calendário → **uma** lista/calendário com estado único. Regra e Evento → um cadastro "Vacinas do calendário" (wizard de 3 passos). Cadastro duplicado em Configurações → redireciona. |
| **Alterar** | Sanidade abre no que exige ação (Atrasadas/Esta semana). URL real em cada nível. Central: 4 abas × 5 tipos → **Em andamento · Novo protocolo · Modelos**, tipo vira filtro. Vocabulário único (glossário no doc 02). |
| **Sai** | `OcorrenciasView`, aba "Ocorrências (novo modelo)", Cronogramas/Aplicações/Resultados como abas, "Ver animais" como painel de rodapé, coluna Tipo produtivo/reprodutivo, `window.prompt/confirm/alert`, textos "Fase 2", passo "Critérios" vazio. |

### 4.2 Agenda

| Decisão | Ação |
|---|---|
| **Dividir** | Três trilhos: **Tarefas de campo** (as únicas que contam para "Dia fechado"), **Alertas e decisões** (candidatas IATF, BST, análise de dieta, sugestão de movimentação), **Gestão** (financeiro, estoque, patrimônio) — este último sai da lista de campo. |
| **Juntar** | Timeline + mini-calendário + overlay do Calendário → **uma** visão com seletor Hoje · Semana · Mês (na URL). Os 5 verbos → **"Feito"**, com "Adiar" e "Não vou fazer". `PainelLancarBst` fica num só lugar (gaveta). |
| **Alterar** | "Hoje" primeiro (atrasadas dentro, com "há N dias"); 8 KPIs → 3 números (Atrasadas · Hoje N de M · Próx. 7 dias); agrupamento **Tarefa / Lote / Categoria**; ação primária por linha + menu ⋯; atualização otimista (some a linha, não a lista); contrato do evento com `resolucao: realizar | navegar | informativo`. |
| **Sai** | KPI "Pendências", legenda, nota de pendências, coluna "Origem", card de Estoque de rodapé, "Importar agora" genérico, checkbox "abrir lançamento", modais sem a11y. |

---

## 5. Ordem de ataque sugerida (custo × ganho)

1. **Correções de integridade (antes de qualquer redesenho):** Desfazer que estorna, idempotência da baixa, escopo de fazenda em cache/rascunho, fuso local, `.catch(() => {})`, escrita evento+regra transacional, rede ≠ logout.
2. **Estrutura sem risco de dados:** URLs reais, Atrasadas, estados/cores unificados, glossário/textos, código morto, "Hoje primeiro" + atualização otimista.
3. **Registrar aplicação unificado** + fusão Aplicações/Histórico/Exames.
4. **Funcionalidade nova:** Cobertura, carteira do animal, carência, multidose, folha de campo.
5. **Reestruturar a Central** e retirar o Preventivo dela; quebrar o monólito da Agenda.

Próximo documento: **`02-proposta.md`** (nova proposta) e os **mockups clicáveis** validados pelo gauntlet-loop.
