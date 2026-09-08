# As FKs compostas: o que medir mudou no plano

Etapa 2 da ativação do RLS aprovada pelo dono. **Nenhuma migração foi escrita**
— este documento existe porque a etapa, como estava especificada, quebraria o
sistema, e isso só apareceu ao medir.

A seção 9 de `rls-proposta.md` dizia: das 434 chaves estrangeiras do banco,
**161** ligam duas tabelas que ambas têm `fazenda_id`; essas viram compostas,
com **61** `UNIQUE (id, fazenda_id)` novas nas tabelas pai. Os números estão
certos — conferidos de novo contra o esquema real. O que estava errado era
supor que as 161 podem ser tratadas do mesmo jeito.

## Achado 1: a FK composta recusa quem aponta para catálogo global

Medido em PostgreSQL 16, com pai e filha reais:

| O que a fazenda 1 faz | Resultado |
|---|---|
| grava filha apontando para o lote **da fazenda 2** | **recusado** — é para isso que a FK composta existe |
| grava filha apontando para o **próprio** lote | aceito |
| grava filha apontando para lote de **catálogo global** (`fazenda_id` NULL) | **recusado — e não devia** |

O terceiro caso é o problema: a chave da filha é `(30, 1)` e a do pai global é
`(30, NULL)`. `NULL` não casa com `1`, então a linha é rejeitada. Não é
detalhe de borda — é o funcionamento normal do catálogo compartilhado.

**Quantas FKs caem nesse caso: 31 das 161.** Elas apontam para 8 tabelas pai
de catálogo global, e o estrago seria imediato:

| Pai | Filhas que quebrariam | O que para de funcionar |
|---|---|---|
| `principio_ativo` | 9 | Farmácia, protocolos IATF e indução |
| `doenca` | 8 | sanitário, ocorrência clínica, calendário |
| `medicamento_comercial` | 5 | Farmácia e estoque |
| `alimento_nutricional` | 2 | biblioteca de alimentos, simulação de dieta |
| `categoria_medicamento`, `classificacao_medicamento_cad`, `indicacao_terapeutica`, `medicamento_principio_ativo` | 7 | vínculos do medicamento |

**Nove delas são auto-referência** (`doenca → doenca`,
`medicamento_comercial → medicamento_comercial`,
`alimento_nutricional → alimento_nutricional`, …): é o copy-on-write, em que a
cópia da fazenda aponta para a linha global de origem. Compor a chave ali
proíbe exatamente o mecanismo.

### E deixá-las simples não é concessão

O motivo da FK composta são dois problemas (seção 9): a referência cruzada
entre fazendas e o oráculo de existência. **Nenhum dos dois existe quando o pai
é catálogo global**:

- referência cruzada: apontar para o item global não é cruzar inquilino, é o
  uso correto — o item é de todos por desenho;
- oráculo: só é vazamento quando revela dado de outro inquilino. O catálogo
  global é legitimamente visível a todos, então descobrir que um princípio
  ativo existe não revela nada de ninguém.

As 31 ficam simples **de propósito**, e é isso que deve estar escrito na
migração — não omitido.

## Achado 2: com `fazenda_id` nulo, a FK composta é inerte

Medido, no mesmo cenário:

```
filha com fazenda_id = NULL  →  lote da fazenda 2      ACEITO
```

É o `MATCH SIMPLE`, o padrão do SQL: se **qualquer** coluna da chave
estrangeira é nula, a restrição não é verificada. Uma linha órfã continua
podendo apontar para o pai de qualquer fazenda, com a FK composta no lugar.

**Consequência para a ordem:** a etapa das FKs só fecha o furo de verdade
depois de `fazenda_id` deixar de aceitar nulo. Feita antes, entrega 130
constraints trocadas e o buraco aberto para toda linha que nasça sem fazenda.

O backfill do PR #717 já limpou as órfãs que existiam, mas a **coluna** continua
aceitando nulo — e é a coluna que decide o comportamento da FK, não o conteúdo
de hoje.

## O tamanho corrigido

| | Plano original | Medido |
|---|---|---|
| FKs a virar compostas | 161 | **130** |
| `UNIQUE (id, fazenda_id)` novas | 61 | **53** |
| FKs que permanecem simples, justificadas | — | **31** (8 pais de catálogo) |

## A ordem que decorre disso

1. `fazenda_id` **NOT NULL** nas tabelas que não têm direito a nulo — era a
   etapa 4 da proposta original e passa a ser pré-requisito desta;
2. as **130** FKs compostas + 53 `UNIQUE`;
3. as políticas de RLS.

Trocar 1 e 2 de lugar não é preferência de estilo: sem o `NOT NULL`, o passo 2
é caro e não fecha o que promete.

### Passo 1, medido no esquema real

A migração `c8e2a4f70b13_fazenda_id_not_null.py`, rodada contra as 206 tabelas
do esquema real (criado por `create_all`), com uma linha órfã semeada de
propósito em `sanidade`:

| | |
|---|---|
| tabelas com `fazenda_id` | 185 |
| já eram `NOT NULL` | 15 |
| catálogo global, não tocadas | 18 |
| alvos | 152 |
| **travadas** | **151** |
| puladas por ainda terem órfã | 1 (a semeada) |

Ao fim, 166 das 185 recusam nulo. O `downgrade` devolveu exatamente as 151 e
parou nas 15 originais — não afrouxou nada que já era estrito.

**O que isso significa para o passo 2:** tabela PULADA continua aceitando nulo,
e por causa do `MATCH SIMPLE` do achado 2 a FK composta dela nasce inerte. Antes
de compor as chaves, é preciso conferir a saída da migração no boot: cada tabela
listada como pulada é uma que o passo 2 não fecha. Em banco limpo a lista vem
vazia — o backfill do PR #717 tratou as órfãs que existiam.

## Como reproduzir

O roteiro dos dois achados está em `fks-compostas-experimento.sql`, e roda
inteiro num `psql` contra um Postgres descartável. Os números (434 / 161 / 31 /
130 / 53) saem do catálogo do banco, contra o esquema real criado por
`SQLModel.metadata.create_all` — a consulta está no fim do mesmo arquivo.
