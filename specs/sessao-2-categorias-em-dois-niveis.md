# Sessão 2 — Categorias de alimento em dois níveis

Duas frentes independentes, arquivos disjuntos. Cada requisito é numerado para
o `/spec-review` conferir um a um.

## Pedido original (verbatim, para não haver descompasso)

> Em alimentação, categorias; permita abrir em subdivisões, por exemplo, para
> concentrado proteico ou concentrado energético, e que a coluna de Alimentos -
> e cadastro de alimentação - alimentos, puxe a subdivisão hierarquicamente
> inferior para a terceira coluna, e que, naquela tela, tudo seja editável,
> tanto categoria como subcategoria.

### Leitura das colunas (decisão registrada)

O pedido anterior (Sessão 1, A1) pôs **alimento** na terceira coluna; este põe
a **subdivisão** na terceira. A leitura conjunta é de **quatro** colunas:

**1º Produto do estoque · 2º Categoria · 3º Subcategoria · 4º Alimento**

Assim a subdivisão fica de fato em terceiro, e a ordem relativa que a Sessão 1
estabeleceu (estoque → categoria → … → alimento) permanece.

### Decisão de modelagem (vale para as duas frentes)

`Alimento.categoria_alimento_id` continua sendo **uma única FK** e passa a
poder apontar tanto para uma raiz quanto para uma subcategoria:

- aponta para **subcategoria** → coluna Categoria mostra o **pai**, coluna
  Subcategoria mostra ela mesma;
- aponta para **raiz** → coluna Categoria mostra ela mesma, Subcategoria
  fica **vazia** (estado legítimo, não erro).

Nada muda na tabela `alimento`, nenhum registro existente perde vínculo.

---

## Frente A — Backend: hierarquia, isolamento e semeadura
**Dono exclusivo:** `backend/fazenda/models/alimentacao.py`,
`backend/fazenda/api/routers/alimentacao.py`,
`backend/alembic/versions/` (arquivo novo),
`backend/tests/test_alimentacao.py` e testes novos

- **A1.** `CategoriaAlimento` ganha `categoria_pai_id: Optional[int]`, auto-FK
  para `categoria_alimento.id`, **opcional e indexada**. NULL = categoria raiz.
- **A2.** Migração Alembic **aditiva, sem backfill**: as categorias de hoje
  viram raízes. `down_revision` é a última revisão da cadeia — confira com
  `alembic heads` antes de escrever, não chute.
- **A3.** **Exatamente dois níveis.** Uma categoria que já tem `categoria_pai_id`
  não pode ser pai de outra: o POST/PUT recusa com **409** e mensagem clara.
  Também recusa uma categoria ser pai de si mesma.
- **A4.** A restrição de unicidade passa de `(nome, fazenda_id)` para
  `(nome, categoria_pai_id, fazenda_id)` — "Proteico" pode existir sob
  "Concentrado" e sob "Volumoso". Use `op.batch_alter_table` (SQLite não
  altera constraint no lugar).
- **A5.** Como NULL não colide em constraint de unicidade, a checagem de nome
  duplicado **em código** (que já existe no POST e no PUT) continua existindo e
  passa a ser **escopada pelo pai** — é ela que barra duas raízes com o mesmo
  nome.
- **A6.** `GET /alimentacao/categorias` devolve `categoria_pai_id` em cada item.
  A ordenação agrupa filha logo abaixo do pai (raízes por nome, e dentro de
  cada raiz as filhas por nome).
- **A7. (bug pré-existente)** `excluir_categoria_alimento`
  (`alimentacao.py:369`) **não filtra `fazenda_id`** — é o único endpoint do
  bloco sem o filtro, e hoje uma fazenda consegue apagar categoria de outra só
  sabendo o id. Passa a filtrar, devolvendo **404** para id de outra fazenda.
- **A8. (mesma classe de bug)** `atualizar_categoria_alimento` (`:346`) busca
  com `session.get(CategoriaAlimento, categoria_id)` sem conferir a fazenda do
  registro encontrado. Passa a conferir, também com **404**.
- **A9.** Excluir categoria **que tem subcategorias** é recusado com **409** e
  mensagem dizendo para mover ou excluir as filhas primeiro. A checagem já
  existente de "em uso por alimento" (`:373-375`) continua valendo.
- **A10. (bug pré-existente)** `_seed_categorias_alimento` (`:246`) roda a
  **cada** `GET /alimentacao/categorias` (`:319`) e ressuscita
  Volumoso/Concentrado/Mineral se o usuário apagar. Passa a semear **só quando
  a fazenda não tem nenhuma categoria** — primeira vez de verdade. Apagar uma
  padrão passa a ser definitivo, que é o que o usuário espera de um cadastro
  editável.
- **A11.** Testes novos cobrindo, no mínimo: criar subcategoria; recusar o
  terceiro nível; recusar ser pai de si mesma; mesmo nome sob pais diferentes é
  aceito; mesmo nome sob o mesmo pai é recusado; excluir categoria com filha é
  recusado; excluir/atualizar categoria de outra fazenda dá 404; semeadura não
  ressuscita categoria apagada.
- **A12.** A suíte existente de `test_alimentacao.py` continua passando. Se
  algum teste antigo dependia da semeadura a cada GET, **ajuste o teste e
  explique no comentário** por que o comportamento antigo era o errado.
- **A13.** Rodar migração **e reversão** contra SQLite descartável.
  ⚠ `DATABASE_URL` deste shell aponta para o banco de **produção** — troque a
  variável antes de qualquer comando Alembic. Nunca rode Alembic contra ela.

## Frente B — Frontend: árvore de categorias e quarta coluna
**Dono exclusivo:** `frontend/components/CadastroAlimentacao.tsx`

⚠ `frontend/lib/api.ts` é **somente leitura**: o contrato já está escrito lá
(`CategoriaAlimento.categoria_pai_id`, e `categoria_pai_id` aceito em
`criarCategoriaAlimento`/`atualizarCategoriaAlimento`). Consuma, não recrie.

- **B1.** A aba **Categorias** (`CadastroAlimentacao.tsx:108-187`) passa a
  mostrar as categorias em **dois níveis**, com a subcategoria visivelmente
  indentada/subordinada ao pai.
- **B2.** Cada categoria raiz tem uma ação **"Nova subcategoria"**.
- **B3.** **Tudo editável**: renomear e excluir funcionam igual em categoria e
  em subcategoria.
- **B4.** O erro vindo do backend (terceiro nível, nome duplicado sob o mesmo
  pai, exclusão com filhas) aparece na tela com a mensagem do backend — não
  engolir, não traduzir para texto genérico.
- **B5.** A tabela de **Alimentos** passa a ter quatro colunas:
  **Produto do estoque · Categoria · Subcategoria · Alimento**, seguidas da
  coluna de ações.
- **B6.** As colunas Categoria e Subcategoria são derivadas da FK única, pela
  regra da decisão de modelagem acima. Alimento ligado a raiz mostra
  Subcategoria **vazia** — sem "—" alarmante, sem aviso de pendência.
- **B7.** A ordenação por clique continua funcionando nas quatro colunas,
  inclusive nas duas derivadas (`:268-271` é onde as chaves derivadas são
  montadas).
- **B8.** No formulário de alimento, escolher categoria e subcategoria são
  **dois selects encadeados**: o de subcategoria lista só as filhas da
  categoria escolhida, e fica vazio/desabilitado quando a categoria não tem
  filhas. Gravar sem subcategoria é válido — manda a raiz na FK.
- **B9.** Trocar a categoria limpa a subcategoria escolhida, para não gravar
  uma filha de outro pai.
- **B10.** O `colSpan` do estado vazio da tabela acompanha o número novo de
  colunas.

---

## Verificação da sessão

```
ruff check --select F821 backend/
cd frontend && npx tsc --noEmit && cd ..
python -m pytest -q backend/tests
```

Ao final, `/spec-review` requisito a requisito.
