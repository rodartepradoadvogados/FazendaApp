# Reflexos do programa reprodutivo

Mapa de onde o motor `backend/fazenda/rules/programa_reprodutivo.py` (regras
R1–R9) já manda, onde ainda não manda, e o que muda para quem usa o sistema.

Este documento é o inventário que a migração do resto do sistema vai consumir.
Levantado por três varreduras independentes do código, com cada achado
conferido contra o arquivo antes de entrar aqui.

**Última atualização:** 19/08/2026 (candidatas a IATF, "PEV encerra", as 8 listas de trabalho + `fluxo_lactacao`, os denominadores de `taxa_prenhez_pct`/`perc_vazias_pct`/`perc_vacas_prenhas` e a série mensal de concepção).

---

## 1. O que o motor decide

Três perguntas, e só o motor responde as três de forma consistente:

1. **Este animal está no programa reprodutivo hoje?** (R1 — atingiu puberdade,
   não marcado a descartar, não baixado)
2. **Ele conta como apto neste dia?** (R2/R4 — PEV e gestação suspendem;
   apto é vazia ou inseminada-sem-DG)
3. **Este serviço já pode entrar numa taxa?** (R7 — 28 dias, ou desfecho
   conhecido)

Toda superfície que responde alguma dessas por conta própria vai divergir da
Capa e da tela de Ciclos de 21 dias. A lista dessas superfícies é a seção 5.

---

## 2. Já alinhado ao motor

| Superfície | Caminho | Observação |
|---|---|---|
| Ciclos de 21 dias | `/reproducao/ciclos-21-dias` | R1–R9 completos; único lugar que reconstrói a baixa pela data |
| Recria — taxa de prenhez | `/recria/reproducao/taxa-prenhez` | motor filtrado em novilha |
| Dossiê Zootécnico | `/recria/dossie` | herda de Recria |
| Situação reprodutiva ao vivo | `/indicadores/estados-reprodutivos` | usa `classificar_animal`; falta o corte de `a_descartar` |
| Medidores da Capa | `indicadores._repro_benchmark` | `ESTADOS_APTOS` + `conta_em_taxa` + `a_descartar`; ver ressalva em 3.2 |

---

## 3. Onde o motor foi aplicado pela metade

### 3.1 `a_descartar` no benchmark da Capa — CORRIGIDO

Ficou pela metade por um tempo: `_repro_benchmark` filtrava o denominador por
`ESTADOS_APTOS` mas não consultava `a_descartar`, porque `classificar_animal`
não recebe esse campo — só `estado_no_dia` faz o corte de R1.

Corrigido. `_repro_benchmark` recebe `descartar_nums` e tira esses animais do
denominador **e** do numerador. Dois detalhes que valem para quem for repetir o
corte em outro módulo:

- **Cortar só o denominador quebra a conta.** A vaca marcada *depois* de ter
  sido inseminada continuaria no numerador, e a taxa de serviço podia passar de
  100%.
- **O conjunto vem do rebanho inteiro**, não do recorte da categoria. Os animais
  são separados em vaca/novilha por `vacas_nums` e os serviços por
  `ordem_parto` — dois cortes independentes. Derivar o conjunto dentro de cada
  painel deixaria escapar o serviço de uma novilha descartada que caísse no
  painel de vacas.
- **`perc_vacas_prenhas` continua sobre o rebanho inteiro**, de propósito: é
  inventário ("quantas fêmeas estão prenhes"), não taxa do programa. A vaca
  marcada para descarte que está prenhe continua prenhe e continua comendo.

### 3.2 Denominador instantâneo contra numerador acumulado

Na mesma função, `aptas` é um retrato de **hoje**, enquanto `avaliaveis` cobre
todo o período desde `data_corte_taxa_concepcao`. Defensável como aproximação —
mas não é o que R8 descreve, e quem comparar a Capa com a tela de Ciclos vai
achar diferença sem entender por quê.

---

## 4. Denominadores legados — CORRIGIDOS

Estes números **não batiam** com a Capa nem com Ciclos de 21 dias, e estavam em
telas que o produtor abre no mesmo dia.

| Onde | Denominador ANTES | Denominador AGORA |
|---|---|---|
| `taxa_prenhez_pct` / `perc_vazias_pct` (`rules/indicadores.py`) | `prenhes + vazias + inseminadas`, com `else: vazias += 1` engolindo PEV, `nao_apta`, bezerra e `em_protocolo` | `rebanho_programa` (R1): sem impúbere, sem `a_descartar` (exceto gestante — inventário), sem baixada. Alimenta **os alertas**, o Manual da Fazenda e o Relatório personalizado |
| `perc_vacas_prenhas` (`rules/indicadores.py`) | `total = len(animais)` — bezerras no denominador | mesmo corte R1 |
| `taxa_concepcao` mensal (`rules/reproducao_analise.py`) | universo = tabela `Servico`, sem janela de DG | `conta_em_taxa` (R7) + `janela_dg_completa` por mês na série |

Dois detalhes que a correção obrigou:

- **Os numeradores também precisaram do corte.** Deixar `vazias`/`prenhes` crus
  sobre um denominador menor passaria de 100%. Por isso `perc_vazias_pct` pode
  **cair** quando a população excluída é majoritariamente vazia.
- **`vazias_programa` não conta inseminada.** O card é rotulado "Vazias" e o
  drill-down abre a lista filtrada por `sit_rep` "Vaz." — sem as inseminadas.
  Contá-las faria o card divergir da lista que ele abre. As contagens cruas
  (`prenhes`/`vazias`/`inseminadas`) continuam sobre o rebanho inteiro, porque
  outros consumidores (card "Vazias" do mobile) dependem delas.

---

## 5. Sem a regra dos 28 dias

| Onde | Efeito |
|---|---|
| `rules/indicadores.py:623-626` | `taxa_concepcao_pct` sem `conta_em_taxa`, **no mesmo JSON** que a versão correta do benchmark — dois números de "taxa de concepção" na mesma resposta |
| ~~`rules/reproducao_analise.py` (séries mensais)~~ | **CORRIGIDO** — `agregar_mensal` recebe `hoje`/`dias_resultado` e devolve `janela_dg_completa: list[bool]` |
| ~~`rules/manual_fazenda.py:141`~~ | **CORRIGIDO** — `METRICAS_DEPENDEM_DE_DG` faz `_insights` descartar o mês em apuração só para as métricas que dependem de DG. O sistema parou de inventar a "queda de concepção" |
| `api/routers/reproducao.py:558` | O front agrega concepção no cliente, sem janela |
| `rules/indicadores.py:271-272` | `taxa_perda_prenhez` mistura numerador sem janela com denominador com janela |
| `api/routers/indicadores.py:257` | `percentual_perda_prenhez_pct` |

---

## 6. Decisão reprodutiva por `sit_rep`

`sit_rep` é o texto congelado do CSV do Ideagri: só muda no próximo upload. Uma
vaca que engravidasse pelo app continuava sendo tratada como vazia até o próximo
arquivo chegar.

**Nenhuma decisão de caminho principal lê mais `sit_rep`.** O que sobrou são
fallbacks, que só ativam quando não há registros carregados (listados no fim
desta seção).

**Migrados:**

| Onde | O que passou a decidir |
|---|---|
| `rules/iatf.py` | Candidatas a IATF: estado ao vivo ∈ {APTA, ATRASADA}, avaliado numa data. Fecha cinco furos do critério antigo — PEV, protocolo em andamento, inseminada em aberto, aptidão de novilha e `a_descartar` |
| `rules/agenda_engine.py` | "PEV encerra" exclui gestante/inseminada pelo estado ao vivo |
| `rules/relatorios_gerenciais.py` (`relatorios_manejo`) | As 8 listas de trabalho: gestante/inseminada/"vazia" (disponível para serviço) vêm de `estados_ao_vivo`, não mais dos três booleanos por `sit_rep`. `a_descartar` só corta a lista "a inseminar" — as demais (prenhes, secagem, previsão de partos) continuam biológicas, de propósito (ver seção 7.1) |
| `rules/relatorios_gerenciais.py` (`fluxo_lactacao`) | Projeção de partos/secagens: filtro `"Vaz."` removido (`ups` já é o sinal ao vivo de gestação); "em lactação" passou a usar a mesma secagem ao vivo de `relatorios_manejo`, não `Animal.del_dias` congelado |
| `rules/relatorios_gerenciais.py` (`taxa_servico_prenhez`) | `prenhas` da curva acumulada por faixa de DEL: vem de `_ultimo_servico_positivo`, o mesmo predicado do estado GESTANTE |

Fallbacks (ativam quando faltam registros): `indicadores.py:228-236,462,487,594-601`,
`recria.py:411-489`, `lote_criterios.py:238`, e no front
`mobile/menu/Indicadores.tsx:62-65`, `FormDiagnostico.tsx:40`.

---

## 7. Motivos de aparição na agenda

### 7.1 Quem respeita R1 (`a_descartar`)

**Cinco lugares:** o motor (`programa_reprodutivo.py:381`), a agenda do
veterinário (`agenda_veterinario.py:122`), o benchmark da Capa
(`indicadores.py:_repro_benchmark`), o painel de candidatas a IATF da Agenda
(`agenda_engine.py`, via o recorte `no_programa`) e os dois endpoints de
protocolo em `reproducao.py`, via `estado_no_dia`.

**Não respeitam** — o animal marcado para descarte continua sendo cobrado:
retoque, parto provável, pré-parto, secagem, Scratch, BST, indução de cio,
vacina pré-parto, motivo de perda de prenhez, sugestão de lote, eventos
sanitários, e 7 das 8 listas de trabalho — só "a inseminar" corta
`a_descartar` (de propósito: é a única lista que pede uma ação que contradiz
o descarte já decidido; as demais são biológicas — vaca a descartar prenhe
ainda pare e ainda seca). Note que é um corte parcial de R1: só `a_descartar`,
sem `data_baixa`.

### 7.2 Motivos e o que os dispara

| Motivo | Origem | Respeita gestação ao vivo? |
|---|---|---|
| Candidata IATF | `agenda_engine.py` → `iatf.py` | **Sim** — estado ao vivo, com R1 |
| Retoque | `agenda_engine.py:252` | Sim (via perda/pré-parto) |
| Parto provável | `agenda_engine.py:396` | Sim |
| Pré-parto | `agenda_engine.py:415` | Sim |
| Secagem | `agenda_engine.py:433` → `dry_off.py` | Sim, com DEL ao vivo |
| Aplicar Scratch | `agenda_engine.py:448` | Sim |
| PEV encerra | `agenda_engine.py` | **Sim** — estado ao vivo |
| BST (aptas/inaptas/reanálise) | `agenda_engine.py:490` → `bst.py` | N/A (critério de lactação) |
| Observar cio pós-indução | `agenda_engine.py:542` | Parcial |
| Protocolo IATF D0/D7/D9/D11 | `agenda.py:638` | N/A (execução) |
| Vacina pré-parto | `agenda.py:766` | Sim |
| Motivo da perda de prenhez | `agenda.py:1066` | N/A |
| Sugestão de lote | `agenda.py:951` → `lote_criterios.py` | Misto |
| Eventos sanitários (`novilha_apta`…) | `eventos_sanitarios.py:137` | **Não** — só idade |

### 7.3 Ponto conferido e absolvido

`agenda_veterinario.py:274-283` lista vaca dentro do PEV em "vazias por
diagnóstico" **com os dias restantes de PEV anexados**. Isso parece violar R2,
mas está certo: R2 diz que suspensa **não sai** do programa. É divergência de
vocabulário com a tela, não defeito.

---

## 8. Definições concorrentes de "apta" — checklist da unificação

Quatro definições de apta e três limiares de aptidão de novilha coexistem.
Nenhuma delas exclui `EM_PROTOCOLO`, que é justamente o estado criado para não
listar animal em protocolo como apto.

| # | Onde | "Apta" significa |
|---|---|---|
| 1 | `programa_reprodutivo.py` (R4) | disponível ∧ ¬gestante ∧ (vazia ⊻ inseminada-sem-DG) — **o canônico** |
| 2 | `agenda_veterinario.py:251` | idade ≥ mín **e** peso ≥ mín |
| 3 | `agenda_veterinario.py:133` | terceiro limiar, mais baixo: "verificar aptidão" |
| 4 | `indicadores.py:329,483-497` | `DEL_APTA_MIN = 45` hard-coded (não `pev_dias()`); novilha só por **peso** |
| 5 | `recria.py:411-419` | por eliminação sobre `sit_rep` |
| 6 | `eventos_sanitarios.py:137-141` | só **idade**, sem peso |
| 7 | `api/routers/indicadores.py:206-210` | idade **menor** que N meses — sentido invertido |
| 8 | `recria.py:1257` | semente de lote com PEV fixo de 46 dias, paralelo a `pev_dias()` |
| 9 | `bst.py:28` | "elegível" com semântica de lactação — não conflita, mas divide o vocabulário |

---

## 9. Rótulos e paridade no frontend

| Item | Onde |
|---|---|
| "Taxa de prenhez" rotulando `taxa_prenhez_pct` (indicador de **estoque**, não a taxa do programa) | `RelatorioPersonalizado.tsx:21`, `ManualFazendaModal.tsx:185`, `manual_fazenda_pdf.py:78`, `alertas_indicador.py:27` — enquanto a Capa chama o mesmo campo de "Fêmeas prenhas" |
| Menu mobile sem a rota `/ciclos-21-dias` | `app/app/menu/page.tsx` |
| Ficha mobile sem o card de curva de lactação (o dado já chega no payload) | `components/mobile/rebanho/Ficha.tsx:44` |
| `/ciclos-21-dias` fora do `SectionBackground` | `components/SectionBackground.tsx:8-14` |

---

## 10. Consumidores que degradam o cálculo

`api/routers/indicadores.py:202` e `rules/manual_fazenda.py:227` chamam
`calcular_indicadores(...)` **sem** `peso_por_animal`, `aplicacoes_iatf` e
`lotes`. O estado ao vivo degrada: novilha sem peso vira `nao_apta`, vaca em
protocolo vira `apta`. **O denominador muda conforme a tela.** O único chamador
completo é `calcular_indicadores_fazenda`.

---

## 11. Armadilhas de leitura do próprio motor

Coisas que o motor faz de propósito e que confundem quem lê o número sem o
contexto:

1. **Ciclo em apuração.** Enquanto não passam os dias de "resultado conhecido"
   desde o fim do ciclo, PG ELIG já está cheio e PREG ainda não. A taxa de
   prenhez sai subestimada por construção. `ResultadoCiclo.janela_dg_completa`
   sinaliza isso, e as telas marcam a linha como *em apuração*, sem comparar com
   a meta. **Nunca leia um ciclo em apuração como piora de manejo.**
2. **`servicos_com_resultado` conta serviço antigo sem DG.** Serviço com 28 dias
   ou mais entra na concepção mesmo que ninguém tenha diagnosticado — e entra
   como fracasso. É deliberado (a fazenda que não lança DG tem que ver a
   concepção cair), mas o nome do campo sugere o contrário.
3. **`a_descartar` retroage.** Sem data na marcação, a vaca marcada hoje some de
   todos os ciclos passados, inclusive dos denominadores. Isso **infla a taxa de
   serviço histórica**. Quanto mais antigo o ciclo, menos confiável. A correção
   de verdade é uma coluna `a_descartar_em` + backfill.
4. **BR ELIG usa `APTA*`, não `APTA`** (R5a): os serviços do próprio ciclo são
   removidos antes de contar os dias aptos. Sem isso, a vaca que concebeu no
   dia 5 do ciclo seria excluída **por ter dado certo**.
5. **Dependência da rapidez do DG.** Uma vaca inseminada perto do fim de um
   ciclo e ainda sem diagnóstico segue apta no ciclo seguinte, e entra no BR
   ELIG dele. Duas fazendas com manejo idêntico, diagnosticando aos 30 e aos 60
   dias, terão taxas de serviço diferentes.

---

## 12. Ordem sugerida da migração

Do que mais dói para o que menos dói:

1. **`taxa_concepcao_pct` de `indicadores.py`** — é a última definição
   concorrente de concepção: DG bruto (`pos/(pos+neg)`) **no mesmo JSON** que a
   versão correta do benchmark. A série mensal já migrou; este campo não.
2. **Paridade mobile** — menu sem `/ciclos-21-dias`, ficha sem a curva de
   lactação.
3. **`a_descartar_em` + backfill** — o único que resolve a armadilha 11.3, e a
   única migração de schema da fila.

Já feito: candidatas a IATF, "PEV encerra", **todo** o
`relatorios_gerenciais.py` (as 8 listas de trabalho, a projeção de partos e
secagens, a curva de prenhas por faixa de DEL — seção 6), os denominadores da
seção 4, a série mensal de concepção (seção 5) e a unificação de "apta" da
seção 8.
