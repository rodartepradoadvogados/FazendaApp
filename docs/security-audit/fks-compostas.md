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
depois de `fazenda_id` deixar de aceitar nulo. Feita antes, entrega dezenas de
constraints trocadas e o buraco aberto para toda linha que nasça sem fazenda.

O backfill do PR #717 já limpou as órfãs que existiam, mas a **coluna** continua
aceitando nulo — e é a coluna que decide o comportamento da FK, não o conteúdo
de hoje.

## O tamanho, medido contra `create_all` (banco hipotético)

| | Plano original | Medido |
|---|---|---|
| FKs a virar compostas | 161 | **130** |
| `UNIQUE (id, fazenda_id)` novas | 61 | **53** |
| FKs que permanecem simples, justificadas | — | **31** (8 pais de catálogo) |

Números úteis para entender a forma do problema — **não são os que a
migração usa**. O achado 3, mais abaixo, mede a mesma coisa contra o banco de
produção de verdade, e o número muda: **120** FKs, **51** `UNIQUE`.

## A ordem que decorre disso

1. `fazenda_id` **NOT NULL** nas tabelas que não têm direito a nulo — era a
   etapa 4 da proposta original e passa a ser pré-requisito desta;
2. as FKs compostas + `UNIQUE` (o número certo é o do achado 3, mais abaixo:
   **120** + **51**, não 130/53 — essa contagem inicial usava um banco
   hipotético);
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

## Achado 3: o banco de produção não é o que `create_all` produz

Medido em 09/09/2026, ao escrever a migração do passo 2
(`472f92e0860b_fks_compostas_tenant.py`). Os números 434/161/31/130/53 acima
saem de `SQLModel.metadata.create_all` — um banco hipotético, criado direto
dos models. **O banco real nasce por Alembic**, e os dois divergem.

Comparando as duas versões do mesmo esquema (tabelas idênticas, 206 delas):

| | `create_all` | Alembic (produção) |
|---|---|---|
| FKs no total | 434 | **306** |
| a compor (achado desta migração) | 130 | **120** |
| `UNIQUE` novas | 53 | **51** |

**A causa:** `animal.fazenda_id`, por exemplo, foi acrescentada em 2024 pelo
piloto multi-fazenda (`f1a2b3c4d5e6_piloto_multi_fazenda.py`) como
`op.add_column(nullable=True)` — só a coluna, sem `ForeignKeyConstraint`. Os
models declaram `foreign_key="fazenda.id"` (ou apontam para outra tabela de
fazenda), o SQLAlchemy usa isso para montar `JOIN`s em Python, mas **o banco
nunca ganhou a constraint** — porque a migração que criou a coluna não a
levava, e nenhuma migração posterior fechou essa lacuna.

**O tamanho do gap, por categoria:**

- **113 tabelas** com `tabela.fazenda_id` sem FK nenhuma para `fazenda.id`.
  Não são candidatas a composição — `fazenda` não tem `fazenda_id`, não há o
  que compor — mas são uma lacuna de integridade à parte: nada impede
  `fazenda_id` apontar para uma fazenda que não existe (ou que foi apagada).
  Consertar isso é uma frente própria, de escopo bem maior que esta (113
  tabelas contra as 51 daqui), e cada uma precisa do mesmo cuidado de
  detecção de órfão que `fazenda_id NOT NULL` teve — **registrado aqui como
  pendência, fora desta migração.**
- **10 pares** entre tabelas de fazenda (`alimento→estoque`,
  `foto_campo→animal`, `lancamento_item→vale_avulso`/`vale_funcionario`,
  `decimo_terceiro→rescisao_funcionario`,
  `ferias_funcionario→rescisao_funcionario`,
  `estoque→categoria_alimento`, `portal_mensagem→foto_campo`,
  `protocolo_iatf_lancamento→protocolo_iatf`,
  `sanidade→protocolo_inducao_lancamento`) que os models declaram e que
  SERIAM candidatas a composição — mas não têm FK nenhuma hoje, nem simples.
  Mesma causa-raiz das 113. Compor do zero uma relação nunca imposta exige
  primeiro conferir se o dado de produção já a viola — o que seria, por si,
  um vazamento entre fazendas achado no processo — e por isso **também
  ficam de fora desta migração**, registradas como pendência.
- **120 FKs** já existem de verdade no banco de produção — essas, e só
  essas, são compostas por `472f92e0860b_fks_compostas_tenant.py`.

O número de pares de catálogo global que ficam simples também mudou (31 → 26)
pelo mesmo motivo indireto: o esquema evoluiu entre uma medição e outra (duas
tabelas do catálogo, por exemplo, deixaram de ter filha nova desde a auditoria
original). Não é um achado novo, só reflexo do tempo passado.

## O tamanho corrigido (medido contra o banco de produção real)

| | Plano original (`create_all`) | Medido contra Alembic (produção) |
|---|---|---|
| FKs a virar compostas | 161 | **120** |
| `UNIQUE (id, fazenda_id)` novas | 61 | **51** |
| FKs que permanecem simples, justificadas (catálogo global) | — | **26** |
| Pares sem FK nenhuma hoje (pendência, fora desta migração) | — | **10** |
| `tabela.fazenda_id → fazenda.id` sem FK (pendência, frente própria) | — | **113** |

## Como reproduzir

O roteiro dos dois primeiros achados está em `fks-compostas-experimento.sql`,
e roda inteiro num `psql` contra um Postgres descartável — os números lá
(434/161/31/130/53) são os do `create_all`, mantidos como estavam porque o
script reproduz especificamente essa comparação. Os números do achado 3 (o
banco real) saem de rodar `alembic upgrade head` num banco descartável e
comparar `pg_constraint` contra o que `SQLModel.metadata.create_all` produziria
no mesmo esquema — é o que `test_migracao_fks_compostas.py` mede em miniatura,
com um par saudável e um violado de propósito.
