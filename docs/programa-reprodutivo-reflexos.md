# Reflexos do programa reprodutivo

Mapa de onde o motor `backend/fazenda/rules/programa_reprodutivo.py` (regras
R1–R9) já manda, onde ainda não manda, e o que muda para quem usa o sistema.

Este documento é o inventário que a migração do resto do sistema vai consumir.
Levantado por três varreduras independentes do código, com cada achado
conferido contra o arquivo antes de entrar aqui.

**Última atualização:** 19/08/2026.

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
| Ciclos de 21 dias | `/reproducao/ciclos-21-dias` | R1–R9 completos; único lugar com `a_descartar` e baixa datada |
| Recria — taxa de prenhez | `/recria/reproducao/taxa-prenhez` | motor filtrado em novilha |
| Dossiê Zootécnico | `/recria/dossie` | herda de Recria |
| Situação reprodutiva ao vivo | `/indicadores/estados-reprodutivos` | usa `classificar_animal`; falta o corte de `a_descartar` |
| Medidores da Capa | `indicadores._repro_benchmark` | `ESTADOS_APTOS` + `conta_em_taxa`; ver ressalva em 3.1 |

---

## 3. Onde o motor foi aplicado pela metade

### 3.1 `_repro_benchmark` não exclui `a_descartar`

`rules/indicadores.py:224` filtra o denominador por `ESTADOS_APTOS`, mas
`a_descartar` não é consultado em lugar nenhum do caminho: a string não existe
em `estado_reprodutivo.py` nem em `indicadores.py`, e `classificar_animal` não
recebe esse campo. Só `estado_no_dia` faz o corte de R1.

**Efeito:** vaca marcada para descarte continua no denominador da taxa de
serviço da Capa, inflando o "não inseminamos" com animais que ninguém pretende
inseminar.

### 3.2 Denominador instantâneo contra numerador acumulado

Na mesma função, `aptas` é um retrato de **hoje**, enquanto `avaliaveis` cobre
todo o período desde `data_corte_taxa_concepcao`. Defensável como aproximação —
mas não é o que R8 descreve, e quem comparar a Capa com a tela de Ciclos vai
achar diferença sem entender por quê.

---

## 4. Denominadores legados que ainda convivem

Estes números **não batem** com a Capa nem com Ciclos de 21 dias, e estão em
telas que o produtor abre no mesmo dia.

| Onde | Denominador | Consequência |
|---|---|---|
| `rules/indicadores.py:604-608` | `prenhes + vazias + inseminadas`, com `else: vazias += 1` engolindo PEV, `nao_apta`, bezerra e `em_protocolo` | É o `taxa_prenhez_pct` que alimenta **os alertas**, o Manual da Fazenda e o Relatório personalizado |
| `rules/indicadores.py:273` | `total = len(animais)` | `perc_vacas_prenhas` com bezerras no denominador |
| `rules/reproducao_analise.py:146` | universo = tabela `Servico` | O defeito nº 2 do motor, ainda vivo: quem não foi inseminada some da conta. Alimenta Análise Reprodutiva, Manual da Fazenda e o assistente |

---

## 5. Sem a regra dos 28 dias

| Onde | Efeito |
|---|---|
| `rules/indicadores.py:623-626` | `taxa_concepcao_pct` sem `conta_em_taxa`, **no mesmo JSON** que a versão correta do benchmark — dois números de "taxa de concepção" na mesma resposta |
| `rules/reproducao_analise.py` (séries mensais) | O mês corrente entra sem os DGs pendentes |
| `rules/manual_fazenda.py:141` | `_insights` gera **sugestão automática** de "queda de concepção" a partir dessa série. O sistema inventa um problema que não existe |
| `api/routers/reproducao.py:558` | O front agrega concepção no cliente, sem janela |
| `rules/indicadores.py:271-272` | `taxa_perda_prenhez` mistura numerador sem janela com denominador com janela |
| `api/routers/indicadores.py:257` | `percentual_perda_prenhez_pct` |

---

## 6. Decisão reprodutiva ainda por `sit_rep`

`sit_rep` é o texto congelado do CSV do Ideagri: só muda no próximo upload. Nos
pontos abaixo ele é o **caminho principal**, não um fallback — ou seja, uma vaca
que engravidou pelo app continua sendo tratada como vazia até o próximo arquivo
chegar.

| Onde | O que decide por `sit_rep` |
|---|---|
| `rules/iatf.py:97-107` | Candidatas a IATF (`"Vaz. apt."`, `"Vaz. atr."`). Alimenta a Agenda **e** `/reproducao/protocolo-iatf/candidatas` |
| `rules/relatorios_gerenciais.py:544` | `prenhas` do relatório por faixa de DEL |
| `rules/relatorios_gerenciais.py:573` | Exclusão `"Vaz."` na **projeção de partos e secagens** (`fluxo_lactacao`) |
| `rules/relatorios_gerenciais.py:167-181` | As 8 listas de trabalho |
| `rules/agenda_engine.py:463` | "PEV encerra" exclui gestante por `sit_rep not in ("Ges.","Ins.")` |

Fallbacks (ativam quando faltam registros): `indicadores.py:228-236,462,487,594-601`,
`recria.py:411-489`, `lote_criterios.py:238`, e no front
`mobile/menu/Indicadores.tsx:62-65`, `FormDiagnostico.tsx:40`.

---

## 7. Motivos de aparição na agenda

### 7.1 Quem respeita R1 (`a_descartar`)

**Exatamente dois lugares:** `programa_reprodutivo.py:381` e
`agenda_veterinario.py:122`.

**Não respeitam** — o animal marcado para descarte continua sendo cobrado:
candidata IATF, retoque, parto provável, pré-parto, secagem, Scratch, "PEV
encerra", BST, indução de cio, vacina pré-parto, motivo de perda de prenhez,
sugestão de lote, eventos sanitários, e as 8 listas de trabalho.

### 7.2 Motivos e o que os dispara

| Motivo | Origem | Respeita gestação ao vivo? |
|---|---|---|
| Candidata IATF | `agenda_engine.py:218` → `iatf.py:77` | Não — `sit_rep` |
| Retoque | `agenda_engine.py:252` | Sim (via perda/pré-parto) |
| Parto provável | `agenda_engine.py:396` | Sim |
| Pré-parto | `agenda_engine.py:415` | Sim |
| Secagem | `agenda_engine.py:433` → `dry_off.py` | Sim, com DEL ao vivo |
| Aplicar Scratch | `agenda_engine.py:448` | Sim |
| PEV encerra | `agenda_engine.py:462` | **Não** — `sit_rep` |
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

1. **`iatf.py`** — decide por `sit_rep` e alimenta a Agenda. É onde o produtor
   recebe a orientação errada sobre qual vaca inseminar hoje.
2. **`a_descartar` em `_repro_benchmark`** — muda o denominador da Capa.
3. **`relatorios_gerenciais.py`** — as 8 listas de trabalho e o `fluxo_lactacao`
   (projeção de partos e secagens por `sit_rep`).
4. **`reproducao_analise.py`** — remove a terceira definição de concepção e para
   de gerar insight falso no Manual.
5. **Unificar "apta"** na tabela da seção 8, um consumidor por vez.
6. **Paridade mobile** — menu e ficha.
7. **`a_descartar_em` + backfill** — o único que resolve a armadilha 11.3.
