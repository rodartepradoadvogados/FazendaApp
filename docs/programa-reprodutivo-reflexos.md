# Reflexos do programa reprodutivo

Mapa de onde o motor `backend/fazenda/rules/programa_reprodutivo.py` (regras
R1–R9) já manda, onde ainda não manda, e o que muda para quem usa o sistema.

Este documento é o inventário que a migração do resto do sistema vai consumir.
Levantado por três varreduras independentes do código, com cada achado
conferido contra o arquivo antes de entrar aqui.

**Última atualização:** 19/08/2026 (candidatas a IATF, "PEV encerra", as 8 listas de trabalho + `fluxo_lactacao`, os denominadores da Capa, a série mensal de concepção, a unificação de "apta", as taxas do painel de Eficiência Reprodutiva e a ligação card→lista).

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

| `api/routers/recria.py` (`_status_reprodutivo`, `_situacao_reprodutiva_3`, `classificar_categoria`) | Categoria de manejo e situação reprodutiva em 3 baldes: `classificar_animal`, sem cair mais no texto do CSV |
| `rules/lote_criterios.py` | O critério `situacao_reprodutiva` do lote e o teste de gestante: estado ao vivo. Era daqui que saía a sugestão de movimentação para o lote errado |

Fallbacks (ativam quando faltam registros): `indicadores.py:228-236,462,487,594-601`,
e no front
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

## 8. Definições concorrentes de "apta" — resolvido

O inventário original listava nove. A triagem mostrou que **quatro não eram
conflito**: eram perguntas diferentes que por acaso usam a mesma palavra.

**Corrigidos** (eram a mesma pergunta que R4/R7, respondida de outro jeito):

| Onde | Antes | Agora |
|---|---|---|
| `indicadores.py::_reproducao_categorias` (fallback) | `DEL_APTA_MIN = 45` hard-coded, paralelo a `pev_dias()`; novilha só por **peso** | `pev_dias()` para a vaca; **idade E peso** para a novilha, a dupla condição da regra 7 |
| `recria.py::_status_reprodutivo` / `_situacao_reprodutiva_3` | por eliminação sobre `sit_rep` | `classificar_animal` — "vazia" = APTA ∨ ATRASADA; PEV/EM_PROTOCOLO/NAO_APTA devolvem `None` (não casam com nenhum dos três critérios cadastráveis, e não devem inventar um balde) |
| `recria.py::_categorias_novas_padrao` (semente) | PEV fixo em 46, paralelo a `pev_dias()` | as duas pontas derivam do **mesmo** `pev_dias()`: "Pós-parto - PEV" vai até `pev`, "Liberada/apta" começa em `pev+1`. Só a semente — a categoria criada continua editável |
| `lote_criterios.py` | `_situacao_reprodutiva_3(sit_rep)` e um fallback para `sit_rep == "Ges."` | `ctx["estado_vivo"] == GESTANTE`; sem fallback, porque `classificar_animal` sempre devolve um estado |

**Não eram conflito** — conferidos contra o código e mantidos:

| Onde | Por quê |
|---|---|
| `agenda_veterinario.py:251` e `:133` | São **puberdade** (idade ∧ peso para a 1ª cobertura), não a disponibilidade-no-dia de R4. O `:133` é o limiar mais baixo de "verificar aptidão", deliberado e comentado no próprio arquivo |
| `bst.py:28` | "Elegível" de lactação — outro vocabulário, outra pergunta |
| `api/routers/indicadores.py:206-210` | O campo já se chama `novilhas_aptas_ate_meses` e o rótulo da tela é "até X meses": o `<=` está certo |
| `eventos_sanitarios.py` (gatilho `novilha_apta`) | Apesar do nome, **não** é aptidão reprodutiva: o rótulo da tela é "Aptidão (novilha atingir certa idade)", o cadastro exige `gatilho_idade_meses`, e a semente traz Brucelose RB51 aos **13** meses — abaixo do `idade_apta_min_meses()` padrão de 15. Amarrá-lo aos parâmetros de aptidão apagaria a vacina de brucelose da Agenda, e exigir peso apagaria o gatilho inteiro em fazenda que não pesa animal. O que **era** defeito e foi corrigido: o filtro era só "fêmea ativa com data de nascimento", então agendava manejo de novilha para vaca que já pariu e para animal marcado a descartar |

## 9. Rótulos e paridade no frontend

| Item | Onde |
|---|---|
| "Taxa de prenhez" rotulando `taxa_prenhez_pct` (indicador de **estoque**, não a taxa do programa) | `RelatorioPersonalizado.tsx:21`, `ManualFazendaModal.tsx:185`, `manual_fazenda_pdf.py:78`, `alertas_indicador.py:27` — enquanto a Capa chama o mesmo campo de "Fêmeas prenhas" |
| Menu mobile sem a rota `/ciclos-21-dias` | `app/app/menu/page.tsx` |
| Ficha mobile sem o card de curva de lactação (o dado já chega no payload) | `components/mobile/rebanho/Ficha.tsx:44` |
| `/ciclos-21-dias` fora do `SectionBackground` | `components/SectionBackground.tsx:8-14` |
| ~~Legenda "% das fêmeas aptas, hoje" no card `taxa_prenhez_pct`~~ | **CORRIGIDA** — o denominador é o rebanho no programa reprodutivo, e a legenda passou a dizer isso (`app/indicadores/page.tsx`) |

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

1. **Paridade mobile** — menu sem `/ciclos-21-dias`, ficha sem a curva de
   lactação.
2. **`a_descartar_em` + backfill** — o único que resolve a armadilha 11.3, e a
   única migração de schema da fila.
3. **Divergências de PRODUÇÃO entre card e lista** (a mesma doença da seção 13,
   fora do escopo reprodutivo): "Produção do dia" em Indicadores mistura datas
   e `ult_cl_kg` congelado enquanto a lista é de uma data só; "IEP médio" no
   mobile é média de todos os intervalos e a lista traz o último por matriz;
   "DEL médio / produção média" no mobile ignora o recorte de lote.

Já feito: candidatas a IATF, "PEV encerra", **todo** o
`relatorios_gerenciais.py` (as 8 listas de trabalho, a projeção de partos e
secagens, a curva de prenhas por faixa de DEL — seção 6), os denominadores da
seção 4, a série mensal de concepção (seção 5), a unificação de "apta" da
seção 8, as três taxas do painel de Eficiência Reprodutiva (seção 13) e a
ligação card→lista (seção 14).


---

## 13. Painel de Eficiência Reprodutiva — CORRIGIDO

Exibia em produção taxa de serviço de **241,9%** e prenhez de **161,3%** no
geral, e **687,5%** e **487,5%** nas novilhas. Dividia conjuntos ACUMULADOS
desde a data de corte (~7,6 meses) pela contagem INSTANTÂNEA das aptas de hoje:
toda fêmea que emprenha sai do denominador e permanece no numerador, então o
estouro de 100% era garantido por construção. Formalmente BRED ⊆ BR ELIG e
PREG ⊆ PG ELIG, logo o teto é 100%.

Agravante da própria migração: o denominador anterior era
`prenhes + vazias + inseminadas` = 127, e 75÷127 = 59% parecia plausível. Ao
corrigi-lo para as aptas (vaca prenhe não pode ser inseminada), o defeito
antigo saltou para a tela.

As três taxas passaram a sair de `programa_reprodutivo` (R1–R9), o mesmo motor
de `/reproducao/ciclos-21-dias`. Agregação por soma de numeradores e
denominadores; só ciclos com janela de DG fechada entram em prenhez e
concepção. Isso também alinha com as metas, que são **por ciclo de 21 dias**.

Medido com 127 animais: 20,4% de serviço, 40,2% de concepção, 9,6% de prenhez —
**abaixo** das metas, onde antes se lia desempenho excepcional.

`taxa_concepcao_pct` era o ÚNICO campo de `reproducao` que não era alias do
benchmark; passou a ser. O card "Concepção / serviço" e o medidor "Taxa de
Concepção" mostram o mesmo número.

**Custo e pagamento:** `calcular_indicadores` foi de milissegundos a ~1,0 s com
127 animais. Como a partição vaca/novilha é disjunta e os contadores são
aditivos, "todas" passou a ser derivada da soma — o motor roda 2× em vez de 3×.
Resultado: **0,31 s**. `TestTodasEDerivadaDeVacaMaisNovilha` é a condição da
otimização: se o derivado divergir do calculado direto, ela tem de sair.

---

## 14. Card e lista: a mesma conta — CORRIGIDO

Doze predicados de drill-down na web filtravam pelo `sit_rep` congelado do
GERAL.csv enquanto o número do card vinha do estado ao vivo — 7 na Capa, 5 em
Indicadores. O `AnimalModal` já exibia o rótulo ao vivo, então a lista aberta
pelo card "Prenhes" mostrava linhas rotuladas "PEV" ou "Apta". O mobile já
estava migrado.

A correção segue o padrão que **nunca** divergiu no repositório
(`aptas`/`aptas_nums`, `partos_previstos`/`partos_previstos_nums`): o backend
manda a lista de números junto do contador, de forma aditiva.
`_reproducao_categorias` passou a emitir `prenhes_nums`, `vazias_nums`,
`inseminadas_nums`, `pev_nums`, `a_inseminar_nums`, `nao_classificadas_nums` e
o balde novo `em_protocolo`/`em_protocolo_nums` — sem ele as fatias do donut
não somavam o rebanho. `taxa_prenhez_pct` e `perc_vazias_pct` ganharam
`prenhes_programa_nums` e `vazias_programa_nums`.

Efeito colateral bom: o recorte vaca/novilha passou a ser o do backend
(registro de `Parto`), e não `data_ult_parto` do CSV, que o front usava.

Verificado com rebanho do tamanho da fazenda (127 fêmeas): as 6 fatias somam
127 sem sobreposição, contador == len(lista) nos 3 recortes, e "todas" é
exatamente vaca + novilha fatia a fatia.

**Continua sem abstração que amarre valor e predicado.** Cada tela ainda
reimplementa a ligação; nada impede estruturalmente uma recaída. É o que a
seção 12 item 3 registra para produção.

---

## 15. As três divergências de produção — CORRIGIDO

A seção 12 registrava produção como o item seguinte da migração. Eram três
defeitos, e um quarto apareceu durante a correção.

### 15.1 Um bug de chave, silencioso em produção

`rules/indicadores.py::calcular_indicadores` lia a data do controle leiteiro
por `c.get("data")`. Quem chama em produção é `calcular_indicadores_fazenda`,
que passa `ControleLeiteiro.model_dump()` — cujo campo é **`data_controle`**.

`data_c` era sempre `None`, a comparação "qual o controle mais recente deste
animal" **nunca disparava**, e o valor que sobrava por animal era o que a
ordem de iteração do SELECT deixasse por último. Um controle de março podia
estar vencendo um de ontem.

Os testes não pegavam porque montavam os dicts à mão com a chave errada — a
mesma do código. É a forma mais barata de um teste concordar com o defeito:
quando o teste constrói a entrada, ele pode construí-la no formato que o bug
espera. Os testes agora usam o nome do modelo, e um caso isolado cobre o
apelido antigo.

### 15.2 "Produção do dia" não era a produção de dia nenhum

O card somava o último controle de **cada animal, em qualquer data**; o
drill-down do mesmo card listava **só as linhas do dia mais recente**. Dois
números diferentes com o mesmo nome — a seção 14 de novo, agora em produção.

A correção não é "fazer as duas contas baterem", é **remover a segunda
conta**. `producao_total_dia_kg` passa a ser somado sobre a própria lista
`controle_nums`; e a reconstrução que o navegador fazia (`abrirUltimoControle`
com seu `fetchControles` e seu Modal) saiu inteira do frontend. Enquanto ela
existisse, card e lista continuariam livres para divergir.

Entrou junto a **cobertura** (`vacas_no_controle` / `vacas_lactacao`): sem
ela, ordenha que faltou lançar se parece com queda de produção, que é a
leitura errada mais cara que este painel permite.

O acumulado antigo não sumiu — virou `ultimo_por_animal`, com `de_controle` e
`congelado` contados à parte.

### 15.3 DEL do card congelado contra DEL da lista ao vivo

O card usava `Animal.del_dias`, congelado no CSV; a lista de animais já era ao
vivo, via `_del_dias_ao_vivo` em `routers/animais.py`. E DEL alimenta dieta e
secagem.

A regra virou função **pura** em `rules/producao_leiteira.py`, com um dono só,
chamada pelos dois. `calcular_indicadores` ganhou `secagens` — sem esse dado
não dá para reproduzir a regra (vaca já seca não conta dias de lactação), e
sua ausência era o motivo real de o card nunca ter ido ao vivo. Sem
`secagens`, o comportamento é o de antes.

### 15.4 `ult_cl_kg`: campo morto, lido em 15 lugares

Ponto de escrita único: `parsers/geral.py`, o parser do Ideagri, aposentado.
Decisão do dono: manter o fallback, **mas mostrar a origem**. `GET /animais/`
passa a emitir `producao_kg`/`producao_data`/`producao_origem` (uma consulta
para o rebanho inteiro), e as sete telas leem de lá.

### 15.5 O que a paralelização ensinou

As três frentes foram particionadas por **dono de arquivo**, não por item —
as três divergências tocam todas o mesmo `rules/indicadores.py`. O contrato
de tipos foi escrito **antes**, em `lib/api.ts`, e ficou somente-leitura para
as três.

Ainda assim, as cinco telas nasceram cada uma com sua cópia do par
`producaoDe`/`origemDe`, e as cópias **divergiram no mesmo dia**: quatro
deduziam a origem do caminho do fallback, uma devolvia `null` sempre que o
backend não a afirmasse — apagando a marca de "dado parado" exatamente de
quem mais precisa dela. Viraram `lib/producaoAnimal.ts`.

É a seção 14 mais uma vez, uma camada acima: **a mesma pergunta respondida em
dois lugares diverge por construção, não por descuido.** A ausência da
abstração que amarra valor e predicado continua sendo a dívida estrutural
aberta — e agora há evidência de que ela reaparece mesmo com o contrato
fixado de antemão.

### 15.6 Mudança de significado com alerta configurável

`producao.producao_media_kg` (média do dia, não do último-por-animal) e
`producao.del_medio` (ao vivo, não congelado) mantêm nome e caminho —
`alertas_indicador.py` depende literalmente deles — mas mudam de significado.
Quem tiver limite configurado nesses dois verá o número mudar sem ter mexido
em nada. Mesmo tratamento dado às taxas reprodutivas: manter e avisar.
