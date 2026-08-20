# Sessão 1 — Ajustes de tela

Quatro frentes independentes, arquivos disjuntos, nenhuma espera a outra.
Cada requisito abaixo é numerado para o `/spec-review` conferir um a um.

## Pedido original (verbatim, para não haver descompasso)

> Em Configurações, cadastro, alimentação, alimentos: inverter colunas.
> Primeiro: produto do estoque; Segundo: categoria; Terceiro: alimento. Nessa
> tela, os cards de Visualizar dietas, 5 de matéria seca... Quando
> selecionados, estão em cor de difícil visualização. Ajuste.

> Em agenda, tirar cards de etapas concluídas, como a indução de lactação.
> Precisa de um pequeno card de etapas e atividades concluídas nos últimos:
> filtro de seleção de período - de x até y, com preenchimento padrão dos
> últimos 7 dias.

> Tirar botão de adicionar em agenda. No lugar do botão adicionar, substituir
> pelo botão Calendário. Se clicar em Calendário, ele sobrepõe os cards de
> CANDIDATAS À PRÓXIMA IATF, BST EXCLUÍDOS... E tirar o card de Calendário da
> lista da agenda que vem abaixo. Colocar filtro de agenda em primeiro lugar,
> acima de tudo, e tirar o local de Data de Referência.

> Em Lançamentos - abas - em determinado momento da navegação, ao clicar em uma
> aba, ele pede certeza para confirmar se deseja sair, pois perderá os dados,
> mesmo sem ter tido o prévio preenchimento de nenhum dado. Confira se isso
> ocorre.

> Em lançamentos - Balanço de estoque, coloque nota avisando que não é local de
> aplicação ou outros lançamentos, mas apenas ajustes, cortesias ou falta de
> lançamentos corretos.

> Em lançamentos - financeiro - contas a pagar, ao se selecionar um produto ou
> serviço, independentemente da quantidade ou valor, coloque uma
> mini-observação abaixo do produto selecionado, indicando o último valor
> unitário pago naquele serviço ou produto.

> Em lançamentos - produção - controle leiteiro, exclua o "Últimos controles
> lançados". Não é necessário. Igualmente, exclua em pesagem corporal as
> Últimas pesagens lançadas.

> Em lançamentos - produção - secagem - ao se selecionar por lote - seleção do
> lote, tem que mostrar os animais selecionados logo na sequência, para manter
> todos os animais selecionados, desmarcados ou ir ajustando. Por padrão, todos
> vem em branco, com botão de marcar todos e desmarcar todos, além das flags de
> seleção.

> Em Rebanho - tirar a aba Movimentações. Não é necessária.

> Em lançamento de vales, permitir anexar comprovante de pagamento.

---

## Frente A — Cadastro de alimentos
**Dono exclusivo:** `frontend/components/CadastroAlimentacao.tsx`

- **A1.** A tabela de alimentos passa a ter as colunas nesta ordem:
  **1º Produto do estoque · 2º Categoria · 3º Alimento**, seguidas da coluna de
  ações. Cabeçalho (`:339-347`) e corpo (`:349-365`) reordenados juntos.
- **A2.** A ordenação por clique continua funcionando em todas as três colunas.
- **A3.** As pílulas de sub-aba ("Visualizar dietas", "% Matéria seca",
  "Cadastro de tabela nutricional", "Análise bromatológica", "Categorias",
  "Alimentos") param de usar o literal `rgba(94,26,46,0.4)` (`:78-86`) e passam
  a usar os tokens `--pill-active-bg` / `--pill-active-fg` /
  `--pill-active-border`, que já existem em `globals.css` definidos por tema
  (`:96-98` escuro, `:150-152` claro, `:205-208` misto).
- **A4.** O contraste tem de ficar legível nos temas **claro, escuro e misto**,
  e nas paletas vinho e verde. A causa do problema é o literal vinho
  translúcido sobre fundo branco; usar o token resolve os três de uma vez.

## Frente B — Lançamentos: falso aviso, listas e nota
**Dono exclusivo:** `frontend/components/FormFinanceiro.tsx`,
`frontend/app/lancamentos/page.tsx`,
`frontend/components/lancamentos/FormControle.tsx`,
`frontend/components/FormPesagemCorporal.tsx`,
`backend/fazenda/api/routers/financeiro.py`

- **B1. (bug confirmado)** Abrir "Contas a pagar" ou "Contas a receber" e trocar
  de aba **sem digitar nada** NÃO pode mais pedir confirmação. Causa: o estado
  `centroCusto` nasce como `"Pecuária Leiteira"` (`FormFinanceiro.tsx:273`) e a
  condição de sujo (`:581-584`) o inclui num `Boolean(… || centroCusto || …)`,
  ficando verdadeira desde o primeiro render.
- **B2.** Valor padrão não conta como trabalho do usuário: a condição de "sujo"
  passa a comparar com o estado inicial, não a testar "é não-vazio".
- **B3. (defeito derivado)** O banner "Há um rascunho de lançamento não salvo"
  (`:1074`, condicionado a `!sujo`) volta a aparecer quando existe rascunho —
  hoje nunca aparece porque `sujo` nunca é falso. É a prova de que B1 pegou.
- **B4.** O aviso ao trocar de aba (`lancamentos/page.tsx:299`, `onChange` no
  `<div>` que embrulha todos os formulários) deixa de marcar sujo por
  "encostou num campo": apagar o que digitou volta ao estado limpo.
- **B5.** O aviso **continua aparecendo** quando há dado real preenchido — a
  correção não pode desligar a proteção.
- **B6.** Remover a seção "Últimos controles lançados"
  (`FormControle.tsx:270-281`), junto do estado e do `fetchControles` que só
  existiam para ela.
- **B7.** Remover "Últimas pesagens lançadas" (`FormPesagemCorporal.tsx:190-201`)
  e o `fetchPesagens` exclusivo dela. **Preservar `atualizarRelatorio()`**, que
  alimenta o relatório de GMD/GPD logo abaixo e não tem relação com a lista.
- **B8.** O banner do Balanço de estoque (`lancamentos/page.tsx:263-266`) passa
  a avisar que ali é lugar de **ajuste, cortesia ou lançamento que faltou** —
  não de aplicação nem de outros lançamentos. Vale para as duas folhas
  (`estoque_entradas_saidas` e `estoque_ajuste_saldo`).
- **B9.** Em Contas a pagar, ao selecionar um produto ou serviço, aparece
  **abaixo do item** uma mini-observação com o **último valor unitário pago**
  naquele produto/serviço, independentemente de quantidade e valor informados.
- **B10.** Sem histórico do item, não inventar número: a mini-observação
  simplesmente não aparece.
- **B11.** O endpoint novo é `GET /financeiro/ultimo-preco?produto=<nome>`,
  lendo `LancamentoItem.valor_unitario` (gravado em `financeiro.py:1786`),
  filtrado por `fazenda_id`, ordenado pela data mais recente. Devolve o valor,
  a data e o número do lançamento — ou vazio.
- **B12.** O wrapper `fetchUltimoPrecoProduto` **já existe** em
  `frontend/lib/api.ts`; consumir, não recriar. `lib/api.ts` é somente leitura.

## Frente C — Agenda
**Dono exclusivo:** `frontend/app/agenda/page.tsx`

- **C1.** O card de filtro (`:2102-2117`) passa a ser o **primeiro elemento** da
  página, acima dos indicadores.
- **C2.** O campo "Data de referência" (`:1862-1874`) sai da tela. A agenda
  passa a ancorar sempre em hoje.
- **C3.** O botão "Adicionar" do cabeçalho (`:1878-1880`) é substituído por um
  botão **"Calendário"**.
- **C4.** Clicar em "Calendário" **sobrepõe** os cards de indicadores
  ("Candidatas à próxima IATF", "BST excluídos" e os demais do grid `:1910-1961`).
  O calendário mensal já existe pronto (`renderCalendario`, `:1640-1721`) —
  reposicionar, não reescrever.
- **C5.** As pílulas "Linha do tempo / Calendário" (`:2154-2170`) saem do card
  da agenda de baixo.
- **C6.** O modal "Adicionar Evento Manual" (`:2288-2382`) e o endpoint
  `POST /agenda/manual` **continuam existindo** — some apenas o botão do
  cabeçalho. O atalho "Agendar" por linha (`:1789-1794`) permanece.
- **C7.** O card fixo "Indução de lactação — concluídas" (`:2071-2098`) é
  substituído por um card genérico **"Concluídos no período"**, cobrindo etapas
  e atividades de qualquer tipo.
- **C8.** Esse card tem filtro **de / até**, preenchido por padrão com os
  **últimos 7 dias**.
- **C9.** As fontes são `GET /agenda/protocolo-inducao-lactacao/concluidos`
  (já existe) e `EventoRealizado` (`models/sistema.py:151`), que é a marcação
  genérica de conclusão. Se faltar endpoint para a segunda, criar.
- **C10.** O card é pequeno e recolhível — não pode competir com os
  indicadores em destaque visual.

## Frente D — Secagem, vale e Rebanho
**Dono exclusivo:** `frontend/components/FormSecagem.tsx`,
`frontend/components/ValeAvulsoSection.tsx`,
`frontend/components/FolhaPagamentoView.tsx`,
`frontend/app/rebanho/page.tsx`,
`backend/fazenda/api/routers/cadastro/rh_folha.py`

- **D1.** Em Secagem, escolhido o lote, os animais aparecem **em lista visível
  logo na sequência** — não escondidos atrás do modal, como hoje
  (`FormSecagem.tsx:260-311`).
- **D2.** O estado inicial da seleção é **todos desmarcados**. Hoje o
  `useEffect` de `:67-69` marca todos.
- **D3.** Há botões **"Marcar todos"** e **"Desmarcar todos"** visíveis fora do
  modal (hoje existe só um botão que alterna, dentro dele —
  `AnimalPickerModal.tsx:121-124`).
- **D4.** Cada animal tem sua flag de seleção individual, e o contador de
  selecionados continua correto.
- **D5.** A aba "Movimentações" sai da tela de Rebanho
  (`rebanho/page.tsx:567-578` e `:607`). `HistoricoMovimentacoes.tsx` é usado
  **em exatamente um lugar** e sai junto.
- **D6.** Não confundir com `MovimentarAnimais.tsx` (lançamento de
  movimentação) nem `SugestoesMovimentacao.tsx` (outra aba) — os dois ficam.
- **D7.** No lançamento de vale, é possível **anexar comprovante de pagamento**.
- **D8.** Reaproveitar o padrão de anexo que já existe (`LancamentoAnexo`,
  endpoints `financeiro.py:2787+`, e o `ModalDivididoDocumento` de
  `FolhaPagamentoView.tsx:854-866`, que está no mesmo arquivo onde o vale é
  lançado). Não criar mecanismo novo de upload.
- **D9.** Vale tem **três** modelos no sistema (`ValeFuncionario`, `ValeAvulso`
  e item de lançamento marcado como vale). Esta sessão cobre
  **`ValeFuncionario` e `ValeAvulso`**; o terceiro já herda o anexo do próprio
  lançamento financeiro.
- **D10.** O wrapper de API do anexo de vale **já existe** em
  `frontend/lib/api.ts`; consumir, não recriar.

---

## Verificação da sessão

```
ruff check --select F821 backend/
cd frontend && npx tsc --noEmit && cd ..
python -m pytest -q backend/tests
```
Referência da suíte: **3250 passed, 1 xfailed**.

Conferência manual obrigatória de B1 (o bug): abrir Contas a pagar, não digitar
nada, trocar de aba — não pode pedir confirmação; depois digitar algo e trocar
de aba — tem de pedir.
