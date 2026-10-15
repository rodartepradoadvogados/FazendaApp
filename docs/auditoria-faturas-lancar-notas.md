# Auditoria — Lançamentos › Financeiro › Contas a pagar › Faturas › "Lançar notas na fatura"

**Data:** 15/10/2026 · **Branch:** `claude/farm-app-access-bikeej` · **Ambiente de teste:** fazenda fictícia "Vale Verde", SQLite descartável.
**Código:** `frontend/components/FaturasView.tsx`, `FormLancamentoLote.tsx` (modo fatura), `financeiro/UnidadeCompra.tsx`,
`financeiro/CadastroRapidoModais.tsx`, `lancamentos/GavetaLancamento.tsx`; backend `faturas_fornecedor.py`.

> Pedido do dono: não perder informação nem o visual da tela (a forma compilada, com linha-resumo); poder trocar conta,
> centro de custo e responsável na própria linha; abrir fora da tela principal; e auditar o que a tela perdeu em relação ao lançamento normal.

## 1. O que a tela é

"Lançar notas nesta fatura" reaproveita o formulário de **lançamento em lote** (`FormLancamentoLote`) com a prop `fatura`.
Isso explica as perdas: o lote nasceu como atalho para colar muitas notas simples e não herdou os recursos do lançamento normal.
Fornecedor, conta e centro vinham da fatura (somente leitura), o responsável era sempre o usuário logado.

## 2. O que a tela tinha perdido (comparado ao lançamento normal)

| # | Recurso do lançamento normal | Na tela de faturas (antes) | Agora |
|---|---|---|---|
| 1 | Produto **do estoque ou texto livre** | só seletor do estoque (serviço: texto) | tipo do item com 3 opções: *produto · estoque*, *produto · texto livre*, *serviço* |
| 2 | **Cadastrar produto/serviço/conta novo** | não existia | botão "Novo produto, serviço ou conta" por item (mesmo diálogo do lançamento normal) |
| 3 | **Associar item sem cadastro a um existente** | não existia | "Associar a existente" por item; e aviso automático quando o item veio de XML/planilha e não bate com o cadastro |
| 4 | Confirmar "produto/serviço não cadastrado" antes de gravar | não existia | confirmação antes de lançar ("Lançar mesmo assim" / "Voltar e cadastrar") |
| 5 | **Unidade de compra** (frasco, saca, ml…) | não existia | seletor "Comprado em", conversão para a unidade do estoque, saldo antes/depois, custo por unidade; envia `apresentacao_id` |
| 6 | Descrição e **centro de custo só do item** | não existia | "Detalhes do item" por item |
| 7 | Responsável escolhível | sempre o usuário logado | escolhível na linha-resumo (backend aceita `responsavel`) |
| 8 | Rótulos acessíveis | datas e tipo de documento sem rótulo associado; `aside` com `role=dialog` | corrigido; axe-core: **0 violações** na gaveta |
| 9 | Lista de produtos do histórico no texto livre | — | sugestões do histórico (datalist) |

**Ainda diferente do lançamento normal (de propósito, ou por decisão pendente):** natureza e classificação por nota,
nº de OS/orçamento, boleto, data prevista de entrada, vínculo com pedido, "É vale de funcionário?", leitura automática de PDF/foto
(a fatura aceita **XML** e planilha), contexto do fornecedor e último preço. Cada nota entra com o cronograma da fatura, por isso
vencimento e pagamento não existem por nota — isso é regra da fatura, não perda.

## 3. Como ficou (decisões)

- **Gaveta de 75% da tela** (não pop-up central). Motivo: o formulário é largo (uma linha por item com 7 colunas e, abaixo, unidade de
  compra e detalhes); um pop-up de 820 px espremeria tudo, e a gaveta deixa a fatura à vista nos 25% restantes. Em tela estreita (≤ ~960 px)
  vira largura total. Mede 75,0% em 2000 px e 100% em 390 px, sem rolagem horizontal. Reaproveita `GavetaLancamento` (foco preso, Esc, scrim).
- **Fechar com algo digitado pergunta antes** (mesma mensagem dos outros lançamentos). Clicar fora não fecha.
- **Linha-resumo preservada** (Fornecedor · Conta · Centro de custo · Período · Responsável). **Conta, Centro de custo e Responsável** são
  `<select>` nativos "vestidos" de texto: ao passar o mouse (ou focar) ganham borda e fundo de campo e o lápis fica forte; sem mouse
  (celular) o pontilhado indica que dá para tocar. Funciona por teclado e leitor de tela.
  - **Conta e centro de custo** gravam no **cadastro da fatura** (`PUT /financeiro/faturas/{id}`): valem para as próximas notas; as já
    lançadas ficam como estão (a tela avisa).
  - **Responsável** vai em cada lançamento. Se o servidor for antigo e ignorar o campo, a tela **avisa** ("ficaram em nome de …") em vez de fingir.

## 4. Verificação (app real, Chromium, 2000×1125 e 390×844)

| Teste | Resultado |
|---|---|
| Abrir a gaveta; largura | 0,75 da tela (desktop) / 1,0 (celular) |
| Passar o mouse em Conta | campo destacado (captura `fat_02`); trocar a conta chama `PUT /faturas/1` e confirma na tela |
| Lançar nota com produto em frasco de 100 ml (3 frascos) + item em texto livre | `POST /faturas/1/notas` 201 com `apresentacao_id: 2`, quantidade 3; saldo previsto 1.050 → 1.350 ml |
| XML com produto desconhecido | aviso de "não cadastrado", "Associar a existente" abre, "Lançar" pede confirmação |
| Esc com formulário sujo | pergunta antes de fechar |
| Nota **fora do período** da fatura | aviso com as 3 saídas (nesta fatura / nova fatura / sem fatura); "sem fatura" gravou por `POST /faturas/notas-avulsas` 201 |
| Nota **duplicada** (mesmo tipo e nº) | `POST /faturas/1/notas` 409 → aviso "Notas que parecem já lançadas" (nada gravado) |
| axe-core na gaveta | 0 violações (após corrigir 4: rótulos, `role`, contraste) |
| Backend: responsável (ida e volta) | `test_responsavel_escolhido_vai_para_a_nota_e_volta_na_resposta` |

## 5. Não verificado nesta sessão

Leitor de tela real, Safari/iOS e teclado virtual; importação de **planilha** pela gaveta (só o caminho do XML foi exercitado);
fatura **fechada/paga** (a gaveta só existe para fatura aberta); `next build` local.
