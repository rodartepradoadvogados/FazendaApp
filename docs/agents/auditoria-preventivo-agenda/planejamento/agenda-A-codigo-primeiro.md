# Agenda — Planejamento A (código-primeiro / dados e compatibilização)

> Planejador A. Ponto de partida: o que o código **já entrega** (dados, endpoints, componentes) e como reorganizar em **duas sub-abas** sem quebrar nada. Fonte da verdade do desejo: `00-PEDIDO-DO-DONO.md`. Somente leitura no repositório; nada foi editado além deste arquivo.
> Referências de código (relativas a `/home/user/FazendaApp`): `frontend/app/agenda/page.tsx` (2.816 l.), `frontend/app/app/page.tsx` (1.870 l., agenda mobile), `frontend/components/PainelLancarBst.tsx`, `frontend/components/ui.tsx` (`Indicador`), `backend/fazenda/api/routers/agenda.py` (2.904 l.), `backend/fazenda/rules/agenda_engine.py` (908 l.), `backend/fazenda/rules/cronograma_sanitario.py`, `backend/fazenda/rules/scratch_pev.py`, `backend/fazenda/rules/parametros.py`.
> Data de referência: 29/09/2026.

---

## 0. Tese em 6 linhas

1. **Sub-aba 1 "Dia a dia"** = só a lista de trabalho do dia (com atrasadas dentro) e o calendário (Semana/Mês). Sem cartões, sem KPI grande. Carrega **1 request**.
2. **Sub-aba 2 "Painel"** = tudo o que hoje está nos cards do print + Concluídos no período + **programação projetada** (repasse, BST, IATF, vacinas, exames, estoque, pendências) em cards **compactos** (56–72 px de altura, 6 por linha). Carrega **sob demanda** (só quando a aba é aberta), em 2 requests.
3. O motor atual (`GET /agenda/`) faz tudo de uma vez, **escreve no banco** e é chamado a cada ação. Ele vira 3 endpoints de **leitura pura**: `/agenda/dia`, `/agenda/painel`, `/agenda/projecao`.
4. Regra do fluxo preventivo: animal **na janela** de vacina/exame não aparece na Agenda; só o **agendamento no dia da aplicação** (`cronograma_sanitario_aplicar_*` e afins). Hoje o motor emite eventos de **decisão por animal** (`sugeridos_`, `animal_`, `modo_`, `incluir_manual_`, `checklist_`) que precisam **sair** da Agenda.
5. Projeção futura **não lista animais** (respeita a regra): mostra contagens por semana e por tipo, com link para a lista de espera/cronograma na Sanidade/Protocolos.
6. Mockup: o "vazio" veio de `boot()` renderizar **skeleton primeiro** e só trocar por dados após um `setTimeout` de 900 ms — se o visualizador do dono não avança timers, a tela nunca sai do skeleton (§6).

---

## 1. Mapa de conteúdo das duas sub-abas

Legenda de custo: **0** = já vem no payload do `/agenda/dia`; **B** = leve (1 consulta agregada); **M** = médio (consulta ao motor/tabelas); **A** = alto (hoje só existe dentro do `GET /agenda/` inteiro).

### 1.1 Tabela: cada card/lista/visão

| Item (hoje) | Sub-aba | Por quê | Fonte de dados / endpoint hoje → proposto | Custo |
|---|---|---|---|---|
| **Candidatas à próxima IATF** (KPI + tabela ordenável, `page.tsx` ~2244; `candidatas_iatf` no `GET /agenda/`) | **2 (Painel)** | É análise/planejamento de médio prazo, não tarefa do dia. Duplica Relatórios › "Situação reprodutiva ao vivo". | `candidatas_iatf` (engine, `agenda_engine.py`) → `/agenda/painel` (`reproducao.candidatas`). Botão "Iniciar protocolo" leva ao Novo protocolo (Protocolos) com as vacas pré-selecionadas (DADOS-CANÔNICOS: 11 vacas do Lote 02). | M |
| **IATF atual** (KPI + lista) | **2** | Visão de acompanhamento; a **etapa do dia** já aparece na sub-aba 1 como tarefa (Dia 0/7/9/11). | `GET /reproducao/protocolo-iatf/ativos` (hoje chamado no mount, `page.tsx` ~458) → `/agenda/painel` (`reproducao.iatf_atual`). | M |
| **Última IATF** (KPI + lista) | **2** | Histórico/consulta. | mesma fonte (`iatfAtivos`, último grupo concluído) → `/agenda/painel` (`reproducao.ultima_iatf`). | M |
| **BST aptos** (KPI "Próx. aplicação") | **2** (card) + evento "Aplicação de BST" na **1** | O **dia** da aplicação é tarefa de campo (evento `bst_aplicacao_{data}`); a **lista de aptas** é análise. | `bst_elegiveis`, `proxima_visita_bst`, `intervalo_bst` → `/agenda/painel` (`sanidade.bst`). Lançar: `PainelLancarBst` + `POST /agenda/bst/aplicar` (já existe). | M |
| **BST excluídos** | **2** | Análise (DEL < 60: 4160/4124 nos dados canônicos). | `bst_excluidos` → `/agenda/painel`. Ação "marcar inapta": `POST /agenda/bst/marcar-inapta`. | M |
| **Incluir no próximo BST** (`bst_nunca_aplicados`, indução de lactação) | **2** | Decisão de médio prazo. | `bst_nunca_aplicados` → `/agenda/painel`. | M |
| **Pendências** (KPI, mesma lista de "Atrasados" da timeline; `page.tsx` 2240–2308) | **1** (as linhas, dentro da lista) e **2** (contagem + por categoria) | **Duplicidade a eliminar:** hoje é KPI **e** seção "Atrasados". Na 1 vira **grupo no topo da lista de hoje**; na 2 vira card de contagem com quebra por categoria. Um só nome: **Atrasadas**. | `eventos` com `data < hoje` e não realizados → `/agenda/dia` (linhas) e `/agenda/painel` (`geral.atrasadas`). | 0 / B |
| **Alertas de estoque** (KPI + card final + eventos "Comprar X"; 3 lugares) | **2** (card + tabela "estoque previsto"); evento "Comprar X" só se for **tarefa** com data | Gestão. O card final do rodapé morre. | `estoque_negativo`, `estoque_abaixo_minimo` (`agenda.py` ~1739–1752) → `/agenda/painel` (`geral.estoque`) + `/agenda/projecao` (`estoque_previsto`). | B |
| **Concluídos no período** (`SecaoRecolhivel`, De/Até 7 d; `page.tsx` ~2416) | **2** (dono pediu explicitamente) | Histórico. **Na 1**, o que foi feito **hoje** continua na mesma lista como linha riscada com **Desfazer** (é estado da lista, não card). | `GET /agenda/realizados?de&ate` + `/agenda/protocolo-iatf/concluidos` + `/agenda/protocolo-inducao-lactacao/concluidos` → **unificar** em `GET /agenda/concluidos?de&ate` (hoje IATF concluído **não aparece** no card). | B |
| **Comunicados** (`nova_dieta`, `alerta_sobra`; ~2474) | **2** (seção "Avisos") ; na **1** só um **ponto/contador** no cabeçalho se houver não lido | Informativos sem ação; poluem a lista de trabalho. | `eventos` com `resolucao=informativo` → `/agenda/painel` (`avisos`). Dispensáveis. | 0 |
| **"Precisa de insumo"** (`hormonios_check`, card lateral 250 px) | **2** (card "Estoque previsto") + **inline na 1** como selo por linha (⚠ "faltam 2 frascos") | O selo na linha é dado da própria tarefa (não é card). O card lateral sai da 1. | `hormonios_check` + `necessidade_iatf` → `/agenda/painel` e campo `insumo` em cada linha do `/agenda/dia`. | 0 / M |
| **Mini-calendário** (lateral; filtra `de=ate=dia`) | **1** (vira a visão **Mês**) | Dono quer "lista, calendário". O calendário deixa de ser overlay que substitui KPIs. | `GET /agenda/calendario?mes=` (contagens por dia e categoria; novo, leve) — hoje o mini só conhece a janela de 10 d. | B |
| **Timeline** (Hoje / Próximos dias / Atrasados, acordeão por dia) | **1** (visão **Lista**) | É o coração do dia a dia. Reordenada: **Atrasadas + Hoje** no bloco dominante; Amanhã e demais dias recolhidos. | `/agenda/dia?de=&ate=` | 0 |
| **Semana** (só existe no app) | **1** (nova no site) | Planejar a semana sem KPI. | `/agenda/dia?de=seg&ate=dom` (contagem + itens) | 0 |
| **Mês** (overlay hoje) | **1** | idem. | `/agenda/calendario?mes=` + `/agenda/dia?data=` ao clicar no dia | B |
| **Legenda de categorias** (~2312) | **1** (vira **filtro em chips**, 1 linha) | Legenda separada ocupa altura sem função. | — | 0 |
| **"Próx. visita IATF / Próx. BST"** (legenda) | **2** (subtexto dos cards de IATF e BST) | Já são eventos ("Visita reprodutiva", "Aplicação de BST"). | `proxima_visita_iatf/bst` → `/agenda/painel` | 0 |
| **Nova tarefa** (só dentro do overlay Calendário, ~2231) | **1** (botão global no cabeçalho) | Ação primária do dia a dia. | `POST /agenda/manual` (existe) | — |
| **Exportar Excel/PDF** (~2087) | **1** (menu ⋯ do cabeçalho); exportar da projeção na **2** | | mesmo | — |
| **Sugestão de movimentação de lote** (modal + deep-link `?abrir_sugestao=`) | **1** (linha "Decisão", não conta no "Dia fechado") | O sino aponta para lá; precisa abrir sem passar pelo Painel. | evento `sugestao_movimentacao_*` | 0 |
| **Contas a pagar / gestão do dia** | **1**: uma linha recolhida "Gestão do dia (N) ▾"; completo na **2** | Evita perder o "vence hoje R$ 12.480,00" (dados canônicos) sem poluir o campo. | `contas_a_pagar` | 0 |
| **Cronograma sanitário — decisões por animal** (`sugeridos_`, `animal_`, `remover_`, `incluir_manual_`, `modo_`, `checklist_`, `desconsiderar_`) | **Nenhuma (sai da Agenda)** | Regra do dono: animais em janela ficam na **lista de espera** (Sanidade/Protocolos), não na Agenda. | `rules/cronograma_sanitario.py::eventos_agenda` (l. 327) hoje emite todos. | — |
| **Cronograma sanitário — `aplicar_`** (o agendamento no dia) | **1** | É exatamente "na agenda aparece o agendamento no dia da aplicação". Baixa pelo botão "Feito" → gaveta "Registrar aplicação". | evento `cronograma_sanitario_aplicar_*` → `POST /agenda/realizados` | 0 |

### 1.2 O que é NOVO (programação projetada) — de onde vem e horizonte

Horizonte selecionável **30 / 60 / 90 dias** (padrão 30). Todos os cards da projeção compartilham o mesmo seletor e o mesmo formato de resposta (§3.3). **Nenhum lista animais**; entregam `n_animais`, `n_doses/unidades`, `por_semana[]` e `link` para a lista/cronograma.

| Card de projeção | Origem do dado | Como se calcula | Observações |
|---|---|---|---|
| **Cio de repasse (adesivo/detector)** | Config decidida (bloco `REPASSE-CONFIG` de `mockups/vacinas-protocolos.html`, `REPASSE_PADRAO`: `usar, prod, quem, dias(14), repetir, cada, vezes|até diagnóstico, agenda, aviso, prio, baixa, cancelar`) + serviços de inseminação (`servicos` no engine; hoje `agenda_engine.py` ~592–606 usa `DIAS_SCRATCH = 14` fixo de `rules/scratch_pev.py:21`, com texto "Aplicar Scratch (0,5)") | Para cada serviço **real** sem diagnóstico negativo/gestante: data = serviço + `dias`; se `repetir`, + k·`cada` até `vezes`/diagnóstico. Para **inseminações ainda futuras** (Dia 11 de IATF em andamento, via `protocolo-iatf/ativos`): projeção **estimada** = Dia 11 + `dias` (selo "estimada"). | Existe hoje só o parâmetro booleano `usa_adesivo_deteccao_cio` (`rules/parametros.py:87`); a **regra configurável completa não existe no backend** — dependência (§4.6). Se `agenda=false`, o card aparece com selo "não aparece na Agenda do dia" (recomendação, ver §7-A5). Demanda de produto = n animais × 1 un. (se `baixa=true`), cruzada com o saldo do `prod`. |
| **BST** | `proxima_visita_bst`, `intervalo_bst`, `bst_elegiveis` (engine) e `_del_projetado_bst` (`agenda_engine.py:52`) | Datas = próxima visita + k·intervalo dentro do horizonte; n aptas **projetadas** = DEL_hoje + dias ≥ 60 na data. | `_del_projetado_bst` já existe; falta reaplicar por visita futura. |
| **IATF** | `GET /reproducao/protocolo-iatf/ativos` (etapas restantes D0/7/9/11 com datas), `candidatas_iatf`, `necessidade_iatf`, `proxima_visita_iatf` | Etapas remanescentes por data (n animais) + "próxima visita: dd/mm, ~N candidatas". | Demanda de hormônios por semana = etapas × doses (do protocolo). |
| **Vacinas** | Calendário sanitário: `Calendario Sanitario` + cronogramas (`rules/cronograma_sanitario.py`) + o novo "Aplicação prevista" do fluxo preventivo (planejamento irmão). | Contagem de **aplicações previstas** por data (agendadas) e, separada, "**janelas que abrem** na semana X: N animais" (só número). | Respeita a regra: animais em janela ≠ Agenda; a projeção mostra **números**, link "Ver lista de espera" (Sanidade). |
| **Exames** | Idem (TB/brucelose etc., leitura em 72 h) | Datas previstas + **leituras** (D+3 da inoculação) como marcos. | Leitura de exame é tarefa de campo com data certa. |
| **Alertas de estoque previstos** | `estoque` (saldo, `estoque_minimo`), validade de frasco, + **demandas projetadas** acima (repasse, BST, IATF, vacinas: doses/mL) | Saldo projetado por semana = saldo − Σ demanda; **data de ruptura** = 1ª semana em que saldo < mínimo (ou < 0). Também **validade** (ex.: Aftosa AF-2609 vence 15/10). | Hoje só há alerta do **presente** (`estoque_negativo/abaixo_minimo`). Vira o card mais valioso do futuro: "Faltará Sincroforte em 12 dias". |
| **Pendências previstas** | Contas a pagar (`contas_a_pagar`), entregas, documentos, descarte previsto (`DIAS_HORIZONTE_DESCARTE = 30`, `agenda_engine.py`), manutenção | Contagem/valor por semana. | Hoje a janela financeira é `dias` (10). Sobe para o horizonte escolhido. |

Fontes já existentes que **evitam recálculo**: o engine já gera eventos futuros para gestação, secagem, pré-parto, PEV, Scratch e desmama (`agenda_engine.py` 495–650) — a projeção **reagrupa** esses eventos por semana/tipo em vez de recomputar regra.

---

## 2. Regra de conteúdo da sub-aba 1 ("Dia a dia")

### 2.1 O que aparece (e só isto)

Ordem vertical, de cima para baixo:

1. **Barra de sub-abas** (`Dia a dia | Painel`) — fixa no topo, altura 44 px, primeira coisa abaixo do título da página.
2. **Uma linha de controle** (altura ≤ 48 px): navegação de data `‹ Ter 29/09 ›` + botão `Hoje` · seletor de visão `Lista | Semana | Mês` · chips de categoria (Reprodução, Sanidade, Produção, Gestão, Atividades — cor + ícone + texto) · busca · `+ Nova tarefa` · menu `⋯` (Exportar, Atualizar).
3. **Uma linha de contexto em texto** (≤ 32 px; **não é card**): "Hoje 7 de 15 · 4 atrasadas · Atualizado há 2 min". É o **único** número na aba. Vira "Dia fechado — 15 de 15" ao zerar (regra atual do banner, só que o total vem do servidor).
4. **Visão Lista**: bloco **Atrasadas** (no topo, "há 3 dias") → **Hoje** → **Amanhã ▸** e **Próximos dias ▸** recolhidos → linha **Gestão do dia (N) ▸** recolhida → **Feitas hoje (N) ▸** recolhida (com **Desfazer**).
5. **Visão Semana**: 7 colunas (seg–dom) com itens abreviados; dia atual destacado; clique abre o dia na Lista.
6. **Visão Mês**: grade com contagem por dia + pontos de categoria (com ícone/`aria-label`); clique filtra a Lista para o dia.

Cada linha de tarefa: ícone+cor da categoria · **o quê** ("Inseminação programada — Dia 9") · **para quem/onde** ("Recria 2 · 12 novilhas") · insumo (selo ⚠ só se faltar) · **[Feito]** (única ação primária) · `⋯` (Adiar, Não vou fazer, Ver animais, Abrir origem).

### 2.2 O que é PROIBIDO na sub-aba 1

- **KPIs/cards de qualquer tamanho** (nenhum `Indicador`), gráficos, sparklines, faixa de "3 números" grande.
- **Animais em janela / lista de espera / candidatas** (IATF, BST, vacina, exame). **Só agendamentos** com data.
- Decisões de cronograma por animal (`sugeridos_`, `animal_`, `modo_`, `incluir_manual_`, `checklist_`): pertencem à Sanidade/Protocolos.
- Legenda de categorias solta, nota "Pendências: tudo que não foi realizado até ontem" (vira `title` do chip), "Concluídos no período" com filtro De/Até, Comunicados como cartão, mini-calendário lateral, card "Precisa de insumo", card de alertas de estoque.
- Skeleton total após cada ação (§3.4) e `alert()/confirm()`.
- Projeções futuras (ficam no Painel).

### 2.3 Política de contagem — o que é "tarefa de campo"

Um evento **conta** para "Hoje N de M" e "Dia fechado" se, **simultaneamente**:

1. `resolucao = "realizar"` (existe botão **Feito** que o backend aceita);
2. `trilho = "campo"`: alguém precisa **fazer algo físico** no animal/curral/insumo — etapas de protocolo (IATF Dia 0/7/9/11, indução, mastite, pré-parto), **aplicação agendada** de vacina/exame (`aplicar_*`, `aplic_agendada_*`, `vacina_pre_parto_*`), leitura de exame, BST, detector/adesivo de cio de repasse (com `agenda=true`), secagem, parto provável, desmama, pesagem, `lida` (tarefa da fazenda);
3. `data ≤ hoje` e ainda não feita.

**Não contam** (aparecem, mas com tag): **Decisões** (`sugestao_movimentacao`, `perda_prenhez_motivo`, `confirmar_cura`, "Confirmar início de lactação" — precisam resposta, não execução física) e **Gestão** (contas a pagar, compras, documentos, patrimônio, diária, empreitada). **Informativos** (`nova_dieta`, `alerta_sobra`, `dieta_analise`) e **navegar** (link para outra tela: "Ir para Dieta") **não contam**. Candidatas e listas de espera **nunca são eventos**.

Consequências no código: campo novo `trilho: "campo"|"decisao"|"gestao"` e `resolucao: "realizar"|"navegar"|"informativo"` em **cada** evento (hoje o front infere por prefixo do `evento_id`, `page.tsx` 1069–1847). O total "M" vem do servidor (`resumo.hoje_total`), não do maior N visto na sessão (`totalHojeRef`).

---

## 3. Desempenho

### 3.1 Diagnóstico atual (medido/lido)

- Mount = **9 requests** (agenda, `fetchAnimais` rebanho inteiro, estoque, pessoas, princípios ativos, eventos sanitários, IATF ativos, indução concluídos, realizados) — `page.tsx` ~408–490 e ~189/621; ~**26 requests** em dev por StrictMode (13 endpoints × 2); **6,7 s** até conteúdo útil (crítica consolidada).
- `GET /agenda/` = `calcular_agenda` (`agenda.py:451–1832`, ≥62 consultas) **e escreve**: `_gerar_agenda_recorrente(session)` (l. 304) e `_gerar_auditorias_diarias(session)` (l. 337), sem escopo de fazenda (l. 462–463).
- Toda ação → `await carregar()` → `setLoading(true)` → `TelaSkeleton` no lugar da timeline (l. 404–411, 2521): perde o lugar do usuário.
- Capa (`frontend/app/page.tsx:176`) e badge do app (`frontend/app/app/layout.tsx:142`) também chamam `fetchAgenda()` só para contar.
- Default `data: date = date.today()` avaliado **no import** (`agenda.py:453`).

### 3.2 Carga por sub-aba (meta)

| Momento | Requests hoje | Meta |
|---|---|---|
| Abrir `/agenda` (sub-aba 1 Lista) | 9 | **1**: `GET /agenda/dia` (atrasadas + hoje + próximos 2 dias; ~30–80 linhas) |
| Abrir gaveta "Registrar/Feito" com dados ricos | 0 (tudo pré-carregado) | **1 por gaveta**: `GET /agenda/eventos/{id}/contexto` (frascos, animais do subconjunto, pessoas) — `animais`, `estoque`, `pessoas`, `principios`, `eventos sanitários` **só aqui**, sob demanda |
| Trocar para Semana/Mês | refaz o motor inteiro | **1**: `GET /agenda/calendario?mes=` (só contagens) ; Semana reaproveita `/agenda/dia?de&ate` |
| Abrir sub-aba 2 (Painel) | — (já pesado no mount) | **2** em paralelo: `GET /agenda/painel` + `GET /agenda/concluidos?de&ate`; a **projeção** só após o primeiro paint do Painel (`GET /agenda/projecao?dias=30`) e re-busca ao mudar 30→60→90 (cache por horizonte) |
| Concluir tarefa | `POST` + refetch total + skeleton | **1**: `POST /agenda/realizados` (resposta traz o delta) + atualização otimista; sem refetch |
| Capa e badge do app | `GET /agenda/` inteiro | `GET /agenda/resumo` (3 inteiros) |

Total em produção, primeira visita: **1 request** (aba Dia a dia), **3** ao abrir o Painel. Em dev, 2 e 6 (StrictMode) — **queda de ~26 para 2**.

Regras: (a) `useEffect` de dados de gaveta com `enabled` = gaveta aberta; (b) `AbortController` ao trocar de aba; (c) cache em memória por chave (`aba+data+cat`) com `stale-while-revalidate` (mostra o último dado, atualiza por baixo, **sem skeleton** quando há dado anterior); (d) `fetchComCache` do app mobile (já existe em `lib/offline.ts`) reaproveitado no site para a lista do dia.

### 3.3 Contratos JSON propostos (todos **somente leitura**; escopo por `fazenda_id`; data em America/Sao_Paulo)

**`GET /agenda/dia?data=2026-09-29&ate=2026-10-01&cat=Reprodutivo,Sanidade&q=`** (defaults: `data`=hoje local, `ate`=`data`+2)
```json
{
  "data_referencia": "2026-09-29",
  "gerado_em": "2026-09-29T14:05:11-03:00",
  "resumo": { "atrasadas": 4, "hoje_total": 15, "hoje_feitas": 7, "proximos_7d": 22, "avisos_nao_lidos": 2 },
  "atrasadas": [ /* Evento[] */ ],
  "dias": [ { "data": "2026-09-29", "eventos": [ /* Evento[] */ ] } ],
  "gestao_do_dia": { "n": 3, "itens": [ /* Evento[] com trilho=gestao */ ] },
  "feitas_hoje": [ { "id": "…", "rotulo": "…", "feito_em": "2026-09-29T08:12:00-03:00", "por": "Cícero Alves", "desfazivel": true } ]
}
```
`Evento` = `{ id, data, categoria, tipo_evento, descricao, numero_animal, lote, n_animais, observacao, origem: "auto"|"manual", trilho: "campo"|"decisao"|"gestao", resolucao: "realizar"|"navegar"|"informativo", destino_link, insumo: {ok: bool, aviso?: "faltam 2 frascos"}, atrasado_dias, contexto_url, cor, apenas_admin }`. O campo `id` mantém o formato atual (hash `sha1[:16]` e prefixos), para compatibilidade com `POST/DELETE /agenda/realizados`.

**`GET /agenda/calendario?mes=2026-09`**
```json
{ "mes": "2026-09", "dias": { "2026-09-29": { "total": 15, "por_categoria": { "Reprodutivo": 6, "Sanidade": 5, "Producao": 2, "Atividades": 2 }, "criticos": 3 } } }
```

**`GET /agenda/painel`** (estado **de agora**, sem futuro distante)
```json
{
  "reproducao": {
    "candidatas": { "n": 11, "proxima_visita": "2026-10-06", "amostra": [ { "numero_matriz": "4219", "del_dias": 96, "motivo": "PEV ok" } ] },
    "iatf_atual": { "n_animais": 20, "protocolos": [ { "nome": "IATF Recria 2", "n": 12, "etapa": "Dia 9", "proxima_data": "2026-10-01" } ] },
    "ultima_iatf": { "data_d0": "2026-09-13", "data_d11": "2026-09-24", "n": 14 }
  },
  "sanidade": {
    "bst": { "aptas": 41, "excluidas": 2, "nunca_aplicadas": 3, "proxima_aplicacao": "2026-10-07", "intervalo_dias": 14 }
  },
  "geral": {
    "atrasadas": { "n": 4, "por_categoria": { "Sanidade": 3, "Producao": 1 } },
    "estoque": { "negativo": [], "abaixo_minimo": [ { "nome": "Sincroforte", "quantidade": 2, "estoque_minimo": 3, "unidade": "frasco" } ] }
  },
  "avisos": [ { "id": "nova_dieta_…", "texto": "…", "link": "/alimentacao?lote=…" } ]
}
```
As listas longas (candidatas, aptas) trazem só **amostra + total**; o detalhe completo abre por `GET /agenda/painel/lista/{chave}` (paginado), pois hoje a lista inteira viaja no mount.

**`GET /agenda/projecao?dias=30|60|90`**
```json
{
  "de": "2026-09-29", "ate": "2026-10-29", "semanas": ["2026-09-28","2026-10-05","2026-10-12","2026-10-19","2026-10-26"],
  "cards": {
    "repasse":  { "usar": true, "agenda": true, "total": 26, "estimadas": 8, "por_semana": [0,6,10,6,4], "produto": { "nome": "Scratch", "demanda": 26, "saldo": 30 }, "link": "/protocolos" },
    "bst":      { "total": 41, "por_semana": [0,41,0,41,0], "datas": ["2026-10-07","2026-10-21"], "aptas_projetadas": [41,43] },
    "iatf":     { "etapas": 31, "por_semana": [12,8,11,0,0], "proxima_visita": "2026-10-06", "candidatas_previstas": 11 },
    "vacinas":  { "agendadas": 3, "por_semana": [1,2,0,0,0], "janelas_abrindo": [ { "semana": "2026-10-19", "vacina": "Aftosa", "n_animais": 136 } ], "link": "/sanidade/vacinas" },
    "exames":   { "agendados": 1, "leituras_72h": 1, "por_semana": [0,1,0,0,0] },
    "estoque":  { "rupturas": [ { "item": "Sincroforte", "unidade": "frasco", "data_ruptura": "2026-10-11", "saldo": 2, "demanda": 4 } ], "validades": [ { "item": "Aftosa AF-2609", "vence_em": "2026-10-15", "saldo": 60 } ] },
    "pendencias": { "n": 5, "valor_previsto": 18430.00, "por_semana": [2,1,1,1,0] }
  }
}
```
`por_semana[]` tem o **mesmo comprimento** de `semanas[]`. Nenhum card devolve número de brinco.

**`GET /agenda/resumo`** → `{ "atrasadas": 4, "hoje_total": 15, "hoje_feitas": 7 }` (Capa, sino, badge).

**`GET /agenda/concluidos?de=&ate=`** → `[ { id, rotulo, animal, lote, concluido_em, por, origem: "realizado"|"iatf"|"inducao"|"protocolo", desfazivel } ]` (une as 3 fontes atuais).

### 3.4 Atualização otimista e fim da escrita no GET

- **Otimista** (padrão já provado em `app/app/page.tsx::alternar`, l. 845–873): ao clicar **Feito**, a linha muda para riscada/some com transição curta, `resumo.hoje_feitas++`, toast "Feito · Desfazer (10 s)"; se o servidor recusar, reverte e mostra o erro **persistente** (`role="alert"`). **Nunca** `setLoading(true)` global; `carregar()` só em erro de conflito ou pull-to-refresh. Confirmações ricas (frasco, dose, subconjunto de animais) abrem **gaveta**; ao salvar, aplica-se o delta retornado.
- **Fim da escrita no GET**: mover `_gerar_agenda_recorrente` e `_gerar_auditorias_diarias` para **fora** do GET, de duas formas complementares: (1) **materialização preguiçosa idempotente** em `POST /agenda/manutencao` (por fazenda; chamada uma vez por dia por sessão, com `INSERT … ON CONFLICT DO NOTHING` na chave recorrência+data) e/ou job diário; (2) **recorrentes calculados em leitura** (função pura `ocorrencias_recorrentes(regra, de, ate)`), sem persistir. Recomendado: (2) para leitura + (1) só para gerar `EventoRealizado`/auditorias quando houver ação.
- **Cache de servidor** por `(fazenda_id, data, versao)` com `ETag` (`versao` = max(`updated_at`) das tabelas dependentes) → `304` barato quando nada mudou (Capa/sino/badge).
- Corrigir default `data: date = date.today()` (`agenda.py:453`): usar `None` e resolver dentro da função no fuso local.

---

## 4. Compatibilização

### 4.1 Extração de `frontend/app/agenda/page.tsx` (2.816 l.)

A página vira um **shell fino** (sub-abas + roteamento + estado de URL) e delega:

```
app/agenda/page.tsx                 → <AgendaShell/> (≤150 l.): lê ?aba, ?visao, ?data, ?cat, ?q
components/agenda/
  AgendaSubAbas.tsx                 (role="tablist", 2 abas, URL)
  dia/AgendaDia.tsx                 (barra + faixa de contexto + visão)
  dia/ListaDia.tsx, LinhaEvento.tsx (memo), GrupoDia.tsx
  dia/VisaoSemana.tsx, VisaoMes.tsx (hoje: renderCalendario 1873–1954, renderMiniCalendario 1962–2009)
  dia/BarraControles.tsx, NovaTarefaModal.tsx (hoje modal ~2660)
  eventos/                          um renderizador por tipo (IATF/indução/customizado/aplicar/bst/…);
                                    hoje tudo em renderEventos 1069–1847
  acoes/BotaoFeito.tsx, PainelConfirmarBaixa.tsx, BotaoAdiar.tsx, ExportarAgendaBotoes.tsx
                                    (hoje definidos DENTRO do render: 904, 924, 951, 2077, 2087 → remount/foco)
  painel/AgendaPainel.tsx           (lazy: next/dynamic)
  painel/CardCompacto.tsx           (novo; substitui Indicador na Agenda)
  painel/PainelReproducao.tsx, PainelSanidade.tsx (usa PainelLancarBst), PainelGeral.tsx
  painel/Projecao.tsx (+ seletor 30/60/90, faixa de semanas)
  painel/Concluidos.tsx, Avisos.tsx
  hooks/useAgendaDia.ts, useAgendaPainel.ts, useProjecao.ts, useFeito.ts (otimista)
```
Passos que **não mudam de comportamento**: `GavetaLancamento` (Preventivo/Inseminação) continua sendo aberta em gaveta; `PainelLancarBst` (`components/PainelLancarBst.tsx`, já usa o `Modal` compartilhado) é reusado **como está** dentro do Painel. `CardsAgendaReprodutivaConfiguraveis.tsx` **não é usado** pela `/agenda` (só Reprodução › Agenda do Veterinário e Relatórios) — **não tocar**; o Painel tem seus próprios cards fixos (evitar mistura com `localStorage agendaReprodutivaCardsV1`).
Modais próprios (sugestão de movimentação, evento manual, picker de lotes: `position:fixed` sem `role="dialog"`) migram para `components/Modal.tsx`.

### 4.2 Rotas/URL (estado na URL)

`/agenda?aba=dia|painel` (padrão `dia`) · `&visao=lista|semana|mes` (só `aba=dia`) · `&data=AAAA-MM-DD` · `&cat=` · `&q=` · `&horizonte=30|60|90` (só `aba=painel`) · `&abrir=<evento_id>` (abre gaveta/linha). Troca de aba/visão usa `router.replace` (sem empilhar histórico). Sem parâmetros = `aba=dia&visao=lista&data=hoje`.

### 4.3 Deep-links existentes e regras de migração

| Link existente | Origem | Comportamento novo |
|---|---|---|
| `/agenda?abrir_sugestao=<evento_id>` | `NotificationBell.tsx:30`, `push.py::url_destino` | Continua funcionando **sem alteração no emissor**: sem `aba` → força `aba=dia` → busca o evento em `/agenda/dia` (ampliando janela se necessário, ou `GET /agenda/eventos/{id}`) → abre o modal; se inexistente, aviso claro (hoje já é assim). Internamente vira alias de `?abrir=`. |
| `/agenda` (sino: demais alertas, `NotificationBell.tsx:42`) | sino | abre `aba=dia`, Lista, hoje. Recomendado: alertas de estoque/BST → `?aba=painel`. |
| Item de menu Sidebar (`Sidebar.tsx:87`) | Sidebar | `/agenda` = `aba=dia`. |
| Saídas: `/sanidade?ir=cronogramas&cronograma_id=`, `/financeiro?ir=a_pagar&ref=`, `/alimentacao?lote=` | Agenda → outras telas | Mantidos. `ir=cronogramas` passa a ser o destino da **lista de espera** (planejamento irmão); os eventos `sugeridos_` que o apontavam saem da Agenda. |
| Capa (`app/page.tsx:176`) | Capa | Troca `fetchAgenda()` por `fetchAgendaResumo()`; card da Capa linka `/agenda?aba=dia`. |
| Sanidade/Protocolos → Agenda | não existem | Novos: "Ver na Agenda" → `/agenda?aba=dia&data=<dia_da_aplicação>&abrir=<evento_id>`. |

### 4.4 Impacto no app mobile (`frontend/app/app/page.tsx`)

- O app **já é** a referência: Lista (hoje + atrasados) / Mês / Semana, "Amanhã" e "Depois" recolhidos, offline (`fetchComCache`, `enviarOuEnfileirar`), check circular otimista. **A sub-aba 1 do site espelha a estrutura do app.** Nenhuma mudança visual obrigatória no app.
- Mudanças mínimas: (1) migrar `fetchAgenda(hoje)` (l. 687, 716) para `GET /agenda/dia` (mesmos campos por evento; **manter o `id` e os prefixos**); (2) parar de tratar `sugeridos_/animal_/modo_/…` (saem do payload); (3) respeitar `trilho/resolucao` para a contagem do selo do app e do badge (`app/app/layout.tsx:142` → `/agenda/resumo`); (4) o Painel (sub-aba 2) **não** entra no app nesta fase (campo = "Dia a dia").
- Compatibilidade de payload: **manter `GET /agenda/` vivo** (deprecado) por 2 ciclos de release. Apps já instalados/PWA em cache continuam funcionando; novo campo é sempre **aditivo** (`trilho`, `resolucao`, `insumo`).
- Modo Curral (`ModoCurral.tsx`, `TIPOS_COMPLEXOS` → "abrir na Agenda completa") passa a apontar `?aba=dia&abrir=<id>`.

### 4.5 Sequência de migração sem quebrar (feature flag)

1. **Backend aditivo**: criar `/agenda/dia`, `/calendario`, `/painel`, `/projecao`, `/resumo`, `/concluidos` **ao lado** de `GET /agenda/`, extraindo funções puras do `calcular_agenda` (sem reescrever regras). Adicionar `trilho`/`resolucao` também no `GET /agenda/` antigo.
2. **Corrigir integridade** (Fase 0 do roteiro `05`): desfazer com estorno para `protocolo_sanitario_`, `aplic_agendada_`, `vacina_pre_parto_`; baixa idempotente; fuso; GET sem escrita.
3. **Front atrás de flag** `agenda_v2` (por fazenda): `AgendaShell` novo; a página antiga permanece atrás da flag desligada.
4. **Ordem de entrega no front**: (a) sub-aba 1 Lista (com otimista) → (b) Semana/Mês → (c) sub-aba 2 cards atuais → (d) projeção → (e) remoção do overlay Calendário e dos KPIs antigos.
5. **Retirar** eventos de decisão de cronograma do payload só quando a **lista de espera** da Sanidade estiver em produção (planejamento irmão); antes disso, marcá-los `trilho="decisao"` e escondê-los por padrão na Lista.
6. **Remover** `GET /agenda/` após 2 releases sem uso (verificar logs).

### 4.6 Dependências que o backend precisa de decisão/novo modelo

- **Configuração de repasse** (`REPASSE_PADRAO`: usar, produto/categoria própria, quem entra, primeira checagem `dias`, `repetir`/`cada`/`vezes|diagnóstico`, `agenda`, `aviso`, `prio`, `baixa`, `cancelar`): hoje só existe o parâmetro booleano `usa_adesivo_deteccao_cio` e a constante `DIAS_SCRATCH = 14`. Precisa de tabela/parâmetros por fazenda + categoria de produto "Detecção de cio de repasse" + **engine lendo a config** (`agenda_engine.py` ~592–606; descrição deixa de ser "Aplicar Scratch (0,5)" e passa a "Checar retorno ao cio").
- **Categoria/trilho/resolução** por tipo: tabela única de metadados (`TIPOS_EVENTO`) em `agenda_engine.py`, substituindo os `if startswith(...)` do front.
- **Ajustes no cronograma**: `eventos_agenda` (`cronograma_sanitario.py:327`) emitir **apenas** `aplicar_*` (e "checar/urgente" como alerta do sino), nunca decisão por animal.

---

## 5. Densidade dos cards do Painel

### 5.1 Medição de partida (print do dono + código)

- `Indicador` (`components/ui.tsx:31`) = `kpi-card` com **chip de ícone** (círculo 15 px + folga) + valor `1.4rem` + rótulo, empilhados; ~**120 px** de altura por card (medida informada pelo dono), em grade `grid-cols-2 md:grid-cols-4 gap-3`.
- 8 KPIs em **3 grupos** = 3 fileiras × 120 px = **360 px** + 3 rótulos de grupo (~24 px cada = 72) + gaps (3×12 = 36) ≈ **470 px**; somando filtros (~56), cabeçalho (~64), legenda (~32) e nota (~24), a lista "Hoje" começa em ~**650–700 px** (≈ 3 telas em 1080p com ~900 px úteis, como a crítica registrou). Em 1366×768 (~640 px úteis) **nenhuma linha de tarefa fica visível** sem rolar.

### 5.2 Especificação do card compacto (Painel)

| Propriedade | Valor | Justificativa |
|---|---|---|
| Altura | **mín. 56 px, máx. 72 px** (fixa por variante) | 120 → 64 px = **−47%** por card |
| Estrutura | 2 linhas: **L1** número (22 px/700) + rótulo (13 px, 1 linha, `ellipsis`); **L2** subtexto (12 px, muted, 1 linha: "próx. 04/10", "2 abaixo do mínimo") + à direita **sparkline 48×16 px** (só nos cards de projeção) | Cabe em 56 px: 8 (pad) + 22 + 4 + 14 + 8 |
| Ícone | 14 px, **inline à esquerda do rótulo** (sem círculo/chip) ; cor **e** ícone **e** texto para a categoria | Elimina o "chip" que custava ~30 px de altura |
| Padding | 8 px 12 px; raio 2 px (DESIGN.md Almost-Square); sem sombra | |
| Grade | `repeat(auto-fill, minmax(172px, 1fr))`, gap 8 px | Conteúdo útil ≈ 1.100 px em 1280 → **6 por linha**; 1024 → 5; tablet 768 → 4; celular 360 → **2** |
| Alvo de toque | o card inteiro é o botão (≥ 56 px de altura); no celular o card tem 64 px | Regra "sol, luva" (≥ 44 px) |
| Estados | normal · alerta (borda + texto `--vermelho`/âmbar **com ícone** ⚠) · zero (número em muted, sem clique) · carregando (skeleton **do card**, não da tela) | Cor nunca sozinha |
| Detalhe | clique abre **um** painel de detalhe **abaixo da fileira** (accordion único; abrir outro fecha o anterior) ou drawer no mobile | Evita a sanfona múltipla atual (`listaAtiva` como Set) |

### 5.3 Arranjo dos grupos (com números)

- **"Agora"**: 8 cards existentes em **2 fileiras de 4** ou **1 fileira de 6 + 1 de 2** (a 1.100 px) = 2 × 64 + 8 = **136 px** (vs. 360). Rótulos de grupo viram **cabeçalho inline de 20 px** (não linha própria de 24 + margem), ou some (a cor/ícone já identifica).
- **"Programação futura"**: 7 cards de projeção (repasse, BST, IATF, vacinas, exames, estoque previsto, pendências) + a **faixa de semanas** (1 linha de 5–13 colunas de 24 px cada, altura 96–120 px, com barras empilhadas por tipo) = 2 × 72 + 8 + 120 = **~270 px** cobrindo 90 dias.
- Total dos cards de cima do Painel ≈ **136 + 270 + cabeçalhos 56 = ~460 px**, **igual ao que hoje só mostra o presente** (470 px), agora **presente + futuro**. Concluídos no período começa em ~520 px (abaixo da dobra em 768 p, mas dentro em 1080 p).
- Painel usa `Indicador` **somente** nas telas que já o usam (Indicadores, etc.); na Agenda, novo `CardCompacto` (não alterar `ui.tsx` para não afetar outras telas).

---

## 6. Defeito do mockup e regra para o novo

### 6.1 Diagnóstico (`mockups/agenda.html`)

1. **Boot com skeleton obrigatório** (l. ~3190–3194):
   ```js
   ui.loading=true; renderAll();
   setTimeout(()=>{ ui.loading=false; renderAll() }, reduce()?100:900);
   ```
   `renderMain()` (l. 2266) faz `if(ui.loading){ m.innerHTML=viewSkeleton(); return }`; `renderLat` (l. 2292) e `renderComun` (l. 2075) também retornam vazio/skeleton com `loading`; os números (`renderNums`, l. 2039: `off=ui.loading`) ficam apagados. Ou seja, **a primeira e única pintura é um skeleton**, e o conteúdo depende de um **timer de 900 ms**.
2. Em visualizadores que **congelam/estrangulam timers** (pré-visualização em iframe sandbox, aba em segundo plano, captura sem event loop ativo), o `setTimeout` **não dispara** e a tela **fica no skeleton**. Coerente com o relato do dono ("não aparece nada direito, e só aparece quando clico em 1º skeleton"): a **interação** (o clique no botão `#rv-load` "Ver 1ª carga (skeleton)", l. 745, ou em qualquer ação que chame `renderAll()`) **força um novo render** e, com `loading` já falso (ou o timer finalmente rodando), aparece o conteúdo.
3. Agravantes: `carregar()` (l. 3152) usa o mesmo timer de 900 ms para "Atualizar" e para reconectar (`atualizar()`, 700 ms); `history.replaceState` no boot depende de `location.hash` (l. 3191) e pode falhar em `file://`/sandbox sem quebrar o resto, mas a **árvore principal só se completa depois do timer**.
4. Grau de certeza: a leitura do código mostra que o skeleton é o estado inicial e depende do timer; que o visualizador do dono não dispara timers é **inferência** coerente com o relato (não reproduzida em navegador). A correção (R1–R3 abaixo) elimina a dependência de qualquer forma.

### 6.2 Regra para o novo mockup (e para o produto)

- **R1 — Primeira renderização é síncrona e completa.** `boot()` monta a tela com dados no **mesmo tick** (`ui.loading=false` no estado inicial). Nenhum `setTimeout`, `requestAnimationFrame` nem `Promise` entre o `DOMContentLoaded` e o primeiro conteúdo útil.
- **R2 — Skeleton só por ação explícita**, e nunca por padrão: botão da barra de revisão "Simular 1ª carga" liga `ui.loading` por **duração limitada com botão "Concluir agora"** (e sempre com `prefers-reduced-motion` → sem skeleton). O skeleton **nunca** é estado de boot.
- **R3 — Sem dependência de timer para o conteúdo.** Toda temporização é apenas cosmética (animação de saída de linha) e **nunca** bloqueia renderização; se o timer não disparar, a tela continua **correta**.
- **R4 — Atualizar/erro de rede usam o estado atual** (mostram o dado anterior + banner), não substituem por skeleton.
- **R5 — Autoteste no próprio arquivo**: `console.assert(document.querySelector('.row'), 'Lista renderizada no boot')` e teste manual "abrir com timers pausados" (DevTools) como critério de aceite.
- Regra de produto equivalente: **stale-while-revalidate** (§3.2) — no produto, a lista do dia **nunca** desaparece por refetch.

---

## 7. Ambiguidades (com recomendação)

| # | Ambiguidade | Recomendação |
|---|---|---|
| A1 | "Somente a lista ou calendário": os **atrasados** ficam **dentro** da lista (sim) — e o **Concluídos de hoje**? | **Dentro da lista** como grupo recolhido "Feitas hoje ▸" (necessário para **Desfazer**). O **histórico por período** (De/Até) fica só no Painel. |
| A2 | A "linha de contexto" (Hoje 7 de 15 · 4 atrasadas) viola "sem KPI"? | Permitida por ser **texto de 1 linha** e o único número; sem card. Se o dono discordar, sai e o total aparece só no título do grupo ("Hoje · 15"). |
| A3 | **Decisões** (sugestão de movimentação, confirmar cura, perda de prenhez) e **Gestão do dia** na sub-aba 1? | Decisões **aparecem** na Lista (tag "Decisão", não contam no "Dia fechado") porque o sino/deep-link aponta para lá. Gestão: **1 linha recolhida** "Gestão do dia (N)". Completo no Painel. |
| A4 | **Projeção vs regra "animais em janela não aparecem"**: o dono quer ver vacinas/exames projetados em cards, mas a janela é lista de espera. | Cards mostram **agendamentos futuros** (data certa) e **contagem agregada** de janelas que abrem (sem brincos), com link "Ver lista de espera". Nunca animais. |
| A5 | Repasse com `agenda=false` na config: aparece na projeção? | **Sim**, com selo "Fora da Agenda do dia", pois afeta estoque e planejamento; some da Sub-aba 1. |
| A6 | Mini-calendário lateral: manter no desktop largo? | **Não**. O calendário é a visão **Mês**; o seletor `‹ data ›` cobre navegação. Evita coluna lateral e ganha largura para a lista. |
| A7 | "Precisa de insumo" e Alertas de estoque: só Painel? | Painel (card + estoque previsto). **Na Lista** só o selo ⚠ inline por tarefa (dado da tarefa, não card). |
| A8 | Horizonte padrão 30/60/90? | **30** (curral olha o mês); 60/90 ao toque; cache por horizonte. Vacinas anuais (aftosa) são o motivo do 90. |
| A9 | Onde vive o botão **+ Nova tarefa**? | Sub-aba 1, cabeçalho (hoje escondido no overlay). No Painel, ausente. |
| A10 | Contagem de `colostragem/igg` (link "Lançar" para ficha do animal): tarefa de campo? | **Sim**, é ação física; resolver como `resolucao=navegar` **com** `trilho=campo`, contando até ser lançada (o lançamento gera baixa automática). Exige o backend saber que foi lançada — se não der, tratar como "não conta" (documentar). |
| A11 | Dia fechado com atrasadas: conta? | Sim: "Dia fechado" = **atrasadas + hoje** de campo = 0. Atrasadas mostradas em vermelho. |
| A12 | Persistir última sub-aba? | Sim, em `localStorage` (conveniência); a URL prevalece sobre o storage. Padrão sempre `dia`. |
| A13 | Compatibilidade: quando remover `GET /agenda/`? | Após 2 releases + verificação de logs; manter `trilho/resolucao` aditivos no payload antigo para o PWA em cache. |
| A14 | Escopo mobile do Painel? | Fora desta fase; o app segue "Dia a dia". Painel responsivo no navegador móvel (2 cards por linha). |
