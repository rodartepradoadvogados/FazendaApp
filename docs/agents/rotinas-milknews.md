# Rotinas agendadas do Milknews

> Desenho aprovado pelo dono em 19/10/2026 (página "Rotinas Milknews", artefato do Claude).
> Este documento é o mapa: o que cada rotina faz, quando dispara, onde está o texto dela e o que
> ela não pode fazer. O texto completo de cada rotina vive no agendador da conta (claude.ai >
> Rotinas), não neste repositório. Se mudar o texto lá, atualize esta tabela.

## As cinco rotinas

Horários em Brasília. Desenho: sessão nova a cada disparo e aviso por **push**.

| Rotina | Quando | Trabalho | Entrega | ID | Estado em 19/10/2026 |
|---|---|---|---|---|---|
| **Milknews: matéria diária** | Todo dia, 05:00 (`0 8 * * *` UTC) | Pesquisa o setor leiteiro, escreve o lote de posts do blog | Lote em `backend/fazenda/seed_data/milknews_lotes/` + PR | `trig_01Qpm1wm4eD8x1wDrcjhFzpo` | **Ativa.** Texto novo pendente: só o dono edita (ver o fim deste documento) |
| **Milknews: conferência das entregas** | Segunda, 07:00 (`0 10 * * 1` UTC) | Só leitura. Confere se cada rotina entregou o que prometeu na semana anterior | Relatório curto ao dono | `trig_01LpDEv49546nvreHFBgS96D` | **Criada, desligada** até anexar o repositório |
| **Milknews: fontes do simulador de preço do leite** | Segunda, 09:00 (`0 12 * * 1` UTC) | Revalida as fontes do card do simulador (MAPA IN 76/2018 + apoio) | PR de `MilkPriceExplainer.tsx`, mescla sozinha (squash) | `trig_013E38QyXwKWCABVXCxX9RWH` | **Criada, desligada** até anexar o repositório |
| **Milknews: réguas de referência (1ª segunda do mês)** | Segunda, 09:30 (`30 12 * * 1` UTC); só trabalha se o dia do mês for 1 a 7 | Confere as réguas de referência (`docs/agents/reguas-referencia-mensal.md`) | PR + relatório "RÉGUAS DE REFERÊNCIA — CONFERÊNCIA DE AAAA-MM" | `trig_016AeerJeafn3JaazEw6i8QG` | **Criada, desligada** até anexar o repositório |
| **Milknews: catálogo de touros NAAB** | Terça, 09:00 (`CRON_TZ=America/Sao_Paulo 0 9 * * 2`) | Compara o catálogo oficial da NAAB com o banco, só leitura | Relatório no chat, **sem PR** | `trig_01UShspCeaDjNZG59CENiMR3` | **Ativa** (a rotina existente; texto corrigido em 19/10) |

Em cron, "dia do mês" e "dia da semana" juntos valem como **OU**. Por isso as réguas disparam toda
segunda e a regra "1ª segunda do mês" está no texto da rotina (primeiro passo: se o dia for maior
que 7, encerra em uma linha).

## Rotinas provisórias e duplicadas

| Rotina | Situação | ID |
|---|---|---|
| "Milknews: fontes do simulador + réguas (provisória)" (era "checar fontes do simulador de preço do leite (+ réguas de referência, 1ª segunda do mês)") | **Ativa.** Roda dentro da conversa que já tem o repositório e continua fazendo as duas partes, agora sem o `force-push`. **Desligue-a no dia em que ligar as três rotinas novas de segunda.** | `trig_01BPgD6Ng7FbJM3gmpRiy2cQ` |
| "Milknews: catálogo de touros NAAB (duplicada, desligada)" | **Desligada.** Foi criada por engano; a NAAB oficial é a de `trig_01UShspCeaDjNZG59CENiMR3`. Pode ser apagada na interface. | `trig_018jseB3ZQyiyc7BXaf1dmXd` |

A rotina de segunda antiga disparava **dentro de uma conversa específica** (`persist_session`), então
o histórico mostrava "sucesso" 12 ms depois do disparo, sem prova de que o trabalho foi feito. Foi
isso que motivou a rotina de conferência.

## O que falta o dono fazer (5 minutos, na interface do Claude)

O agendador permite criar e ajustar rotinas por API, mas **não** anexar repositório, mudar
`persist_session`, ligar o push de uma rotina já existente nem editar uma rotina criada pela
interface. Por isso restam estes passos, em claude.ai > Rotinas:

1. **Matéria diária:** trocar o texto pelo do fim deste documento (política do Firecrawl, checagem de
   duplicidade e padrão de título).
2. **Conferência, fontes e réguas:** em cada uma, "Executa com" > anexar o repositório
   `rodartepradoadvogados/FazendaApp` e **ligar** a rotina.
3. **Desligar** a rotina "fontes do simulador + réguas (provisória)".
4. **Push:** ligar o aviso por push na rotina de NAAB e na provisória, se ainda não estiver (a API
   não altera isso numa rotina existente).
5. Opcional: apagar a "NAAB (duplicada, desligada)".

Por quê (1) e (2): as rotinas criadas por API nascem sem repositório (`sources` vazio; sessões
marcadas `config:no-git-repo`) e só têm as ferramentas `add_repo`/`list_repos`, sem as do GitHub. Um
disparo de teste da conferência terminou limpo em cerca de 50 s, mas sem repositório anexado na
sessão, então não foi possível confirmar que ela leu o GitHub. Não ligamos as rotinas novas à
espera do repositório para não abrir uma lacuna na segunda-feira.

## Regras que valem para todas

- **Firecrawl:** principal só no Canal Rural; último recurso nos demais. Ver
  `docs/agents/milknews-firecrawl.md`, seção 1.1.
- **Sem `force-push`** e sem resetar branches de trabalho. O passo antigo de "resetar
  `claude/farm-app-access-bikeej` com `--force-with-lease`" foi removido.
- **Merge:** só as rotinas "fontes do simulador" e "réguas" (apenas o PR que altera somente
  `conferida_em` e `proxima_conferencia`) têm autorização do dono para mesclar sozinhas. A matéria
  diária abre PR e o dono mescla. Se um merge for bloqueado por permissão, o PR fica aberto e o
  relatório diz isso.
- **Matéria diária:** antes de abrir PR, confere se o lote do dia já tem PR ou arquivo em `main`
  (em 07/10 entraram dois commits idênticos). Título do commit e do PR:
  `MilkNews: lote AAAA-MM-DD (tema curto)`.

## O que a conferência semanal verifica (segunda, semana anterior)

1. Dia sem lote da matéria diária (e se há PR aberto, fechado ou inexistente).
2. Lote ou PR duplicado no mesmo dia; título fora do padrão.
3. PR "Milknews" aberto há mais de 24 h.
4. PR de fontes do simulador da segunda anterior e data de `FONTES_ATUALIZADO_EM`.
5. Rotinas habilitadas, `last_run` dentro da janela esperada e `last_run` suspeito (menos de 5 s
   entre disparo e fim).
6. Réguas: `conferida_em` do mês corrente na primeira segunda do mês.

## Texto novo da matéria diária (colar na rotina)

A rotina "Milknews: matéria diária" foi criada pela interface e **só o dono edita**
(claude.ai/code/routines/trig_01Qpm1wm4eD8x1wDrcjhFzpo). Troque o texto atual por este, sem mexer em
agenda, modelo, conectores ou repositório:

```
MODO NORMAL: não use o caveman nesta rotina. Se o modo caveman estiver ativo, desative-o ("stop caveman" / "normal mode") antes de começar e redija tudo em prosa completa, com frases inteiras. Escreva a matéria com acentuação completa.

Rode o ciclo diário do robô MilkNews no repositório rodartepradoadvogados/FazendaApp seguindo integralmente a skill .claude/skills/milknews/SKILL.md (invoque pela Skill tool; se não aparecer, leia o arquivo) e docs/agents/milknews-firecrawl.md.

POLÍTICA DO FIRECRAWL (decidida em 19/10/2026, seção 1.1 do milknews-firecrawl.md): leia primeiro pelos meios comuns (WebFetch, curl pelo proxy, PDF baixado e lido com pdftotext; WebSearch só para descobrir pauta). O Firecrawl (FIRECRAWL_API_KEY) é fonte PRINCIPAL somente no Canal Rural (canalrural.com.br), que devolve 403 na leitura comum: para ele vá direto ao /scrape do Firecrawl. Em TODOS os outros sites o Firecrawl é ÚLTIMO RECURSO, só depois de a leitura comum falhar de verdade (403, bloqueio, só JavaScript, PDF que não abre), e você registra no PR qual fonte falhou e com qual erro. Cepea: leitura comum, depois uma única tentativa com Firecrawl; se as duas falharem, o indicador fica "não lido nesta rodada" (nunca use snippet de busca). Nunca use o /search do Firecrawl. Sem a chave, sem créditos ou com a API fora do ar, não insista: o Canal Rural fica "não lido nesta rodada", as demais fontes seguem e o PR diz isso.

ANTES DE ABRIR O PR, confira se o lote de hoje já existe: veja se milknews_AAAAMMDD.json (data de hoje em Brasília) já está em origin/main e se já há PR aberto ou branch com o lote de hoje. Se já existir, NÃO abra outro: encerre dizendo isso em uma linha. (Em 07/10/2026 entraram dois commits idênticos do mesmo lote.) Título do commit e do PR, sempre neste padrão: "MilkNews: lote AAAA-MM-DD (tema curto)".

Tudo em português do Brasil com acentuação completa. Sessão nova a cada disparo.
```
