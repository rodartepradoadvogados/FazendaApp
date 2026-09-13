# Sessão 3 — Lançamento de consumo diário e sobra

A maior da rodada. Cada requisito é numerado para a revisão conferir um a um.

## Pedido original (verbatim, para não haver descompasso)

> Em lançamentos - Alimentação: tirar alimentação e colocar dentro de Insumos e
> Sanidade - Alimentação, mas com o nome de Lançar nova dieta - em aba, antes de
> Consumo diario. Em lançamentos - Alimentação, colocar: lançamento de consumo.
> Nesse lançamento, o funcionario irá lançar a quantidade de cada alimento
> fornecido para cada lote, sendo disponibilizado para selecionar apenas os
> alimentos da dieta cadastrada para aquele lote, podendo marcar para preencher
> a quantidade de animais ou de alimento, em kg. Se animais, então se deve lançar
> o valor de acordo com a dieta cadastrada, mutiplicando o valor por cabeça pela
> quantidade de animais do lote. Em todo caso, ter uma flag em cada lote de
> permitir alimentos fora da dieta e uma flag de permitir alimentos sem estoque.
> Ainda, precisa de um segundo card para lançar a sobra. A sobra se lança em
> quilos, e respeita o percentual da dieta cadastrada, para fins de relatório de
> sobra por alimento. O relatório de sobra deve considerar por alimento e por
> quantidade total. O foco ideal é a sobra de 5%. O que se aceita de variação,
> por padrao, é de 3% a 7% de sobra. Sendo abaixo de 3% a sobra lançada, emitir
> alerta na central de alertas e na agenda do mesmo dia, apenas como comunicado,
> sem botão de lançamento, apenas botão de Check, avisando que sobrou menos do
> que o aceitável, e que, para atingir a margem de 5% de sobra, deverá ser
> acrescentada determinada quantidade de cada alimento, e dê quantos quilos de
> cada alimento, calculando o necessario para chegar em 5% de sobra. Se sobrar
> mais que 7%, mesma ação anterior, mas mandando reduzir e dando os valores.
> Coloque em texto extremamente curto, pouquíssimas palavras, apenas o necessario
> para entender. Esses parãmetros percentuais de margem aceitável de sobra deve
> ser configuravel em parãmetros, e la em parãmetros, tem que ter uma flag de
> marcar se deseja lançar o fornecido x sobra ou baixa automatica diária de
> acrdo com a dieta cadastrada ou se não deseja lançar.

## Decisões suas já tomadas

Lançar no **site e no app de campo** · sobra em **kg total, rateada pela dieta** ·
lançamentos do mesmo dia **somam** · consumo **dá baixa em estoque**.

---

## O que o levantamento achou (e que muda o desenho)

Verificado no código, com linha. Três coisas importam para quem for implementar:

**1. A dieta que o app lança não afeta a baixa de estoque.** `_dietas_e_animais`
(`alimentacao.py:45-56`) faz `select(Dieta)` — a tabela **legada** do CSV — e é
ela que alimenta `_dar_baixa_automatica` (`:141`, baixa em `:187-192`).
`DietaLancamento`/`DietaItemProgramado`, que é o que a tela usa hoje, não
aparecem em nenhum ponto desse caminho.

**2. Saca não vira kg em lugar nenhum.** `_quantidade_fisica`
(`alimentacao.py:971-978`) só converte matéria seca para natural, e só em kg/g.
`vagao_kg_dia` (`:1161-1169`) soma apenas `unidade in ("kg","g")`. Item em
"saca 30kg", litro ou dose fica fora de qualquer total em quilos — apesar de o
fator de conversão da saca estar literalmente escrito no nome da unidade.

**3. "Lote" tem quatro representações incompatíveis.** `Lote.codigo` (str de 2
dígitos, `animais.py:136`), `Animal.grupo_primario` (str composta "01 - Nome",
`animais.py:33`), `int` nas dietas (`alimentacao.py:77,98`) e str livre em
Recria/Sanidade (`recria.py:149`, `sanidade.py:36`). A ponte que já existe é
`f"{dieta.lote:02d}"` (`alimentacao.py:1143`).

---

## Frente A — Modelos, migração e parâmetros
**JÁ ENTREGUE** — é o contrato de que as outras quatro frentes dependem, então
foi escrito antes delas para nenhuma precisar esperar. Consumam; não reescrevam.

**Dono exclusivo:** `backend/fazenda/models/alimentacao.py`,
`backend/fazenda/models/animais.py`, `backend/fazenda/rules/parametros.py`,
`backend/alembic/versions/` (arquivo novo)

- **A1.** Modelo novo `ConsumoAlimento`: o que foi **fornecido** de um alimento
  a um lote num dia. Campos mínimos: `fazenda_id`, `data`, `lote: int` (mesma
  representação de `DietaLancamento.lote` — é a dieta que ancora o lançamento),
  `alimento: str`, `alimento_id: Optional[int]`, `quantidade: float`,
  `unidade: str`, `num_animais: Optional[int]`, `origem: str`
  (`"animais"` quando derivado do nº de cabeças, `"kg"` quando digitado direto),
  `fora_da_dieta: bool`, `usuario_id`, `criado_em`.
- **A2.** Modelo novo `ConsumoSobra`: a sobra do lote no dia, **em kg totais**.
  Campos: `fazenda_id`, `data`, `lote: int`, `kg_sobra: float`, `usuario_id`,
  `criado_em`. A sobra é **por lote e dia**, não por alimento — o rateio é
  calculado, nunca gravado.
- **A3.** `Lote` ganha duas flags, com padrão **False** (o comportamento
  restritivo é o seguro): `permitir_fora_da_dieta: bool = False` e
  `permitir_sem_estoque: bool = False`.
- **A4.** Migração aditiva, sem backfill. Confira o head com `alembic heads`,
  não chute. Rode **upgrade e downgrade** contra SQLite descartável.
  ⚠ `DATABASE_URL` deste shell aponta para **produção** — troque antes.
- **A5.** Grupo novo `alimentacao` em `GRUPO_TITULOS`
  (`rules/parametros.py:23-36`) com quatro entradas em `DEFINICOES` (`:40-166`):
  `sobra_alvo_pct` (5), `sobra_min_pct` (3), `sobra_max_pct` (7) e
  `modo_lancamento_alimentacao`, este último com três valores
  (`fornecido_sobra` · `baixa_automatica` · `nao_lancar`), padrão
  `fornecido_sobra`.
- **A6.** Função pura nova `kg_equivalente(quantidade, unidade) -> float | None`
  em `backend/fazenda/rules/` — dona única da conversão para quilos. Converte
  kg, g, **saca 30kg e saca 60kg**; devolve **None** para litro, dose e unidade,
  que não têm conversão possível sem densidade. `None` é resposta legítima e tem
  de ser tratada por quem chama, nunca virar zero.
- **A7.** Testes da função pura, incluindo os casos que devolvem `None`.

## Frente B — Endpoints de consumo, baixa e relatório
**Dono exclusivo:** `backend/fazenda/api/routers/alimentacao.py`,
`backend/tests/test_consumo_alimento.py` (novo)

- **B1.** `POST /alimentacao/consumo` grava um ou mais `ConsumoAlimento` de um
  lote num dia.
- **B2.** `GET /alimentacao/consumo?lote=&data=` devolve o que já foi lançado
  naquele lote naquele dia, **somado por alimento** — lançamentos do mesmo dia
  somam, e a tela precisa mostrar o acumulado.
- **B3.** Os alimentos oferecidos para escolha são **só os da dieta ativa** do
  lote (`DietaItemProgramado` da `DietaLancamento` vigente).
- **B4.** Modo "por número de animais": a quantidade de cada alimento é a
  quantidade **por cabeça** da dieta multiplicada pelo nº de animais informado.
  ⚠ `DietaLancamento.base_quantidade` distingue `"total"` de `"animal"`
  (`alimentacao.py:987`) — respeite, senão o cálculo multiplica duas vezes.
- **B5.** Alimento fora da dieta só é aceito se `Lote.permitir_fora_da_dieta`;
  caso contrário **409** com mensagem clara.
- **B6.** Alimento sem saldo em estoque só é aceito se
  `Lote.permitir_sem_estoque`; caso contrário **409**. ⚠ Isto **não** contradiz
  a decisão de produto de `movimentar()` nunca bloquear por saldo: a checagem
  é feita **antes**, na entrada do lançamento, e é opcional por lote.
- **B7.** Cada lançamento dá **baixa em estoque** por
  `estoque_baixa.movimentar()` (`rules/estoque_baixa.py:237`) — ponto único do
  sistema —, com `origem_tipo="consumo_alimento"` e `origem_id` do registro,
  para a baixa ser rastreável e reversível.
- **B8.** Os **avisos** devolvidos por `movimentar()` (lista de str) são
  **propagados na resposta** do POST. Hoje os avisos da baixa de alimentação são
  jogados fora pelo chamador (`obter_alimentacao`, `alimentacao.py:205`, e
  `necessidade_mensal`, `:216`, ambos ignoram o retorno) — com lançamento manual
  eles passam a ter destinatário.
- **B9.** Excluir um lançamento de consumo **devolve** o produto ao estoque,
  pelo mesmo motor.
- **B10.** `POST /alimentacao/sobra` grava a sobra do lote no dia (kg totais).
  Relançar no mesmo dia **substitui**, não soma — sobra é uma medição do dia,
  não um acúmulo. (Diferente do consumo, que soma. A spec afirma os dois
  comportamentos de propósito.)
- **B11.** `GET /alimentacao/sobra/relatorio?de=&ate=&lote=` devolve a sobra
  **por alimento** e o **total**, no período.
- **B12.** O rateio da sobra por alimento usa a proporção de cada alimento na
  dieta, calculada com `kg_equivalente` (A6). Itens cuja unidade não converte
  para kg **ficam fora do rateio** e são **listados na resposta** num campo
  próprio (ex.: `itens_sem_conversao`) — o relatório tem de dizer o que não
  entrou na conta em vez de silenciar.
- **B13.** Se **nenhum** item da dieta converte para kg, o rateio não é
  possível: devolve o total e a lista de excluídos, sem inventar distribuição.
- **B14.** O percentual de sobra é `kg_sobra / kg_fornecido_total`, com o
  fornecido também convertido por `kg_equivalente`.
- **B15.** Testes cobrindo, no mínimo: soma no mesmo dia; substituição da sobra;
  baixa e devolução em estoque; 409 nas duas flags e o caminho liberado por
  elas; rateio com unidades mistas; rateio impossível; isolamento por fazenda.

## Frente C — Alerta de sobra fora da faixa
**Dono exclusivo:** `backend/fazenda/api/routers/agenda.py`,
`backend/fazenda/api/routers/notificacoes.py`,
`backend/tests/test_alerta_sobra.py` (novo)

- **C1.** Sobra **abaixo** de `sobra_min_pct` ou **acima** de `sobra_max_pct`
  gera alerta **no mesmo dia**, na Agenda e na central de alertas.
- **C2.** Na Agenda é **comunicado**, não atividade: acrescente o prefixo novo a
  `COMUNICADO_PREFIXOS` (`agenda.py:95`, hoje só `("nova_dieta_",)`). Isso já
  dá, de graça, a imunidade a "dar baixa" (`:1910-1911`) e a exclusão
  (`:2215-2216`), e a seção própria no front (`agenda/page.tsx:2194-2200`).
- **C3.** Na central de alertas é `PortalMensagem` com **`pede_retorno=False`**
  (`models/sistema.py:420`), que é o padrão de "some com um check" — some ao ser
  lida (`notificacoes.py:93`). **Sem botão de lançamento.**
- **C4.** O texto diz quantos **kg de cada alimento** acrescentar (sobra baixa)
  ou reduzir (sobra alta) para chegar no alvo de `sobra_alvo_pct`.
- **C5.** Texto **extremamente curto**. Poucas palavras, só o necessário para
  entender. Sem saudação, sem explicação do indicador, sem repetir o nome do
  lote em toda linha.
- **C6.** Alimento que não converte para kg **não** entra na instrução — não dá
  para mandar acrescentar quilos de algo medido em dose.
- **C7.** Um alerta por lote e por dia. Relançar a sobra no mesmo dia
  **atualiza** o alerta em vez de criar outro.
- **C8.** Sobra **dentro** da faixa não gera alerta nenhum — nem "está tudo
  certo". Silêncio é a mensagem.

## Frente D — Telas do site
**Dono exclusivo:** `frontend/app/lancamentos/page.tsx`,
`frontend/app/alimentacao/page.tsx`,
`frontend/components/lancamentos/ConsumoAlimento.tsx` (novo),
`frontend/components/lancamentos/FormAlimentacaoDieta.tsx`

- **D1.** `Insumos e sanidade > Alimentação` ganha a aba **"Lançar nova dieta"**,
  **antes** de "Consumo Diário". As abas de hoje são `["consumo", "lote",
  "mensal"]` (`app/alimentacao/page.tsx:215-219`).
- **D2.** `Lançamentos > Alimentação` deixa de ser o lançamento de dieta e passa
  a ser o **lançamento de consumo**. ⚠ `CadastrarNovaDieta` é definida em
  `CadastroAlimentacao.tsx:654` e hoje tem **um único** consumidor —
  `FormAlimentacaoDieta.tsx:11,102`. Mover a aba não quebra uma segunda tela,
  ao contrário do que o plano inicial supunha.
- **D3.** A tela de consumo: escolhe o lote, mostra **só os alimentos da dieta
  ativa**, e alterna entre **informar nº de animais** e **kg direto**.
- **D4.** Mostra o que **já foi lançado hoje** naquele lote, acumulado.
- **D5.** **Card separado** para lançar a sobra, em kg totais.
- **D6.** O card de sobra mostra o **percentual calculado** e se está dentro da
  faixa — o usuário entende o alerta antes de recebê-lo.
- **D7.** Os avisos de estoque devolvidos pelo POST (B8) aparecem na tela.
- **D8.** As duas flags do lote são editáveis onde o lote é cadastrado, e a tela
  de consumo **explica** por que um alimento foi recusado quando o 409 vier.
- **D9.** Itens da dieta sem conversão para kg aparecem marcados na tela, com a
  informação de que ficam fora do rateio da sobra.
- **D10.** Quando o parâmetro de modo for `nao_lancar`, a aba de consumo não
  aparece; quando for `baixa_automatica`, a tela explica que a baixa é diária e
  automática e não pede lançamento.

## Frente E — App de campo
**Dono exclusivo:** `frontend/components/mobile/lancar/FormAlimentacao.tsx`,
`frontend/components/mobile/lancar/LancarTela.tsx`

- **E1.** O lançamento de consumo e o de sobra existem no app de campo, com a
  mesma regra de negócio da tela do site.
- **E2.** Usa a **fila offline** por `enviarOuEnfileirar` (`lib/offline.ts:432`),
  como as telas migradas mais recentes — não `fetch` direto.
- **E3.** A idempotência vem do `Idempotency-Key` que a própria fila gera
  (`lib/offline.ts:434-437,452`), tratado pelo middleware global
  (`backend/main.py:574-586`). Não invente mecanismo novo.
- **E4.** Tela de campo é para quem está de bota no curral: poucos toques,
  números grandes, nada de tabela larga.

---

## Verificação da sessão

```
ruff check --select F821 backend/
cd frontend && npx tsc --noEmit && cd ..
python -m pytest -q backend/tests
```

⚠ A suíte inteira de uma vez é morta por falta de memória quando há vários
agentes na máquina. Rode **em lotes** de ~40 arquivos e some os resultados.
Referência atual: **3505 passed, 1 xfailed**.

Ao final, revisão requisito a requisito.
