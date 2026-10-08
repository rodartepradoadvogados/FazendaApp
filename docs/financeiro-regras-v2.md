# Financeiro — regras novas dos relatórios (Fase A)

Correção dos números dos Relatórios do Financeiro em PRs pequenos, cada um ligado
**fazenda a fazenda** por uma flag. Este arquivo cobre o PR 0 (rede de segurança)
e o PR 1 (natureza do lançamento). A auditoria completa, com causa-raiz e a ordem
dos PRs seguintes, ficou no relatório da Fase A (`SOLUCOES.md`, fora do repositório).

## 1. A flag `financeiro_regras_v2`

- Parâmetro da fazenda (tabela `parametro_fazenda`, grupo **Financeiro**), tipo
  sim/não, **padrão desligado**. Aparece em *Configurações > Parâmetros
  financeiros*; só administrador altera (`PUT /parametros/financeiro_regras_v2`).
- Só vale a linha **da própria fazenda**. A linha global (sem fazenda) é só o
  modelo que a tela mostra: mesmo editada pelo Painel CowData, não liga ninguém.
  Leitura: `fazenda/rules/parametros.py::regras_v2_ativas(session, fazenda_id)`.
- Desligada, **todo relatório sai como antes, chave por chave**. Isso é travado
  pelo teste `tests/test_relatorios_cenario_auditoria.py`, que compara o cenário
  da auditoria com o resultado do código original
  (`tests/dados/cenario_auditoria_golden_main.json`, gerado por
  `tests/dados/gerar_golden_cenario_auditoria.py`).
- Ligada, a DRE responde `regras_v2: true` e ganha `fora_da_dre.por_natureza`,
  `fora_da_dre.grupos`, `resultado_baixas_periodo` e `pendencias_natureza`; os
  custos ganham `depreciacao_periodo`, `cot` e `fora_por_natureza`.
  `GET /financeiro/regras-v2` diz se a fazenda atual está ligada.

**Ordem para ligar numa fazenda:** rodar o script de impacto num dump → revisar o
CSV com o dono → rodar o backfill (dry-run, depois `--aplicar`) → ligar a flag.

## 2. Natureza do lançamento (`natureza_fin`)

Coluna nova em `conta_gerencial` (a nota), `lancamento_item` (o item) e
`plano_conta_gerencial` (padrão da conta, herdado por prefixo). Não confundir com
`plano_conta_gerencial.natureza`, que diz só se a conta aceita serviço ou produto.

| Natureza | DRE (flag ligada) | Custos ha/vaca/safra |
|---|---|---|
| `OPERACIONAL` (padrão) | entra pela linha da conta | entra |
| `INVESTIMENTO` | fora; só a depreciação entra | fora (depreciação no COT) |
| `FINANCIAMENTO` | fora (empréstimo, principal) | fora |
| `CAPITAL` | fora (aporte, retirada de sócio) | fora |
| `TRANSFERENCIA` | fora | fora |
| `ADIANTAMENTO` | fora (vale a receber) | fora |
| `OBRIGACAO` | fora (quita algo já reconhecido) | fora |

Resolução (`fazenda/rules/natureza.py::resolver_natureza`): item → nota → receita
de bem baixado com venda (desinvestimento) → plano de contas (por prefixo) →
conta `NAO_ENTRA_NA_DRE` sem natureza (`NAO_INFORMADA`, continua fora) →
`OPERACIONAL`.

Quem grava a natureza:

- **criação com `criar_patrimonio`** (despesa) → `INVESTIMENTO`;
- **compra de animal** (`/compras-animais/`): matriz, reprodutor ou touro no nome
  da conta ou na descrição → `INVESTIMENTO` (recomendação do contador); campo
  `natureza_fin` aceita escolha explícita;
- **usuário**: seletor "Natureza do lançamento" no formulário e na edição do
  lançamento (`PUT /financeiro/lancamentos/{numero}/natureza`, nota inteira ou
  `item_id`); padrão da conta em `PUT /financeiro/plano-contas/{codigo}/natureza-fin`
  (admin);
- **backfill** (abaixo), com log.

Com a flag ligada:

- a DRE manda toda natureza ≠ operacional para "fora da DRE", agrupada por
  natureza; a **depreciação continua entrando**;
- o **ganho ou perda na baixa de bem** (`rules/patrimonio.py::resultado_baixa`)
  entra em *Outras receitas e despesas* na data da baixa, e a receita da venda
  ligada ao bem sai de "Receita de vendas";
- custos por hectare, por vaca/lote e por safra usam o mesmo numerador da DRE
  (`financeiro.custos_operacionais_periodo`): só o operacional, e o COT soma a
  depreciação do período;
- despesa `INVESTIMENTO` sem bem no Patrimônio vira pendência ("não vai
  depreciar") na DRE e aviso no formulário.

`patrimonio.centro_custo` também foi criado (aceito na API do patrimônio). A
depreciação **ainda não** é filtrada por centro: isso, com o rateio do bem sem
centro, é o PR 9.

## 3. Backfill (dry-run por padrão) e como reverter

```
python -m scripts.backfill_natureza_fin --fazenda N                      # só relata
python -m scripts.backfill_natureza_fin --fazenda N --csv plano.csv       # relata em CSV
python -m scripts.backfill_natureza_fin --fazenda N --aplicar             # grava; imprime o LOTE
python -m scripts.backfill_natureza_fin --fazenda N --reverter LOTE           # mostra o que voltaria
python -m scripts.backfill_natureza_fin --fazenda N --reverter LOTE --aplicar # desfaz o lote
```

Regras (conservadoras), em `fazenda/rules/backfill_natureza.py`:

- **A.** despesa ligada a bem, sem natureza: `INVESTIMENTO` só se a nota estiver a
  ±10% do valor do bem **e** a competência a até 60 dias da imobilização; o resto
  (ex.: manutenção ligada ao trator) vai para a **lista de revisão**;
- **B.** compra de animal: matriz/reprodutor → `INVESTIMENTO`; as demais vão para
  revisão;
- **C.** conta do plano cujo nome indica financiamento, capital, transferência ou
  investimento: aplica **só** se a conta já estiver fora da DRE
  (`NAO_ENTRA_NA_DRE`), onde a natureza só dá o motivo ao agrupamento. Nas demais
  é **sugestão** (também em `GET /financeiro/dre/conferencia`, campo
  `sugestoes_natureza`), nunca aplicação automática.

Nunca toca `valor_total`/`valor_pago` e nunca sobrescreve natureza já preenchida.
Cada campo gravado vira uma linha em `migracao_log_financeiro` (fazenda, lote,
migração, tabela, registro, campo, antes, depois, motivo). A reversão devolve o
valor de antes **só** onde o valor atual ainda é o que o backfill gravou; se
alguém mudou à mão depois, a linha sai como conflito e não é tocada. Um lote
nunca reverte dado de outra fazenda.

A migração Alembic `e5a9c3f1b742` só cria as colunas e a tabela (aditiva,
idempotente, reversível). O `downgrade` remove tudo, inclusive o que o backfill
tiver gravado nas colunas novas.

## 4. Script de impacto (somente leitura)

```
DATABASE_URL=sqlite:////caminho/dump.db \
  python -m scripts.impacto_relatorios_v2 --fazenda N --de 2026-01 --ate 2026-09 \
    --csv impacto.csv --csv-lancamentos lancamentos.csv
```

Para cada mês: as 15 linhas da DRE (competência e caixa), fora da DRE (total e
por natureza), não classificado, numeradores de custo por hectare e por vaca,
depreciação e, por safra, o numerador do custo da safra. Colunas: `antes`
(regras antigas), `depois` (regras novas com os dados de hoje), `depois_com_backfill`
(simulando o backfill sem gravá-lo) e os Δ. O CSV de lançamentos lista cada
registro que muda de lugar, com o motivo. A conexão abre em modo só leitura
(`PRAGMA query_only` / `SET TRANSACTION READ ONLY`) e termina em `rollback()`.
Mesmo assim: rode num dump restaurado, nunca na produção.

## 5. "Hoje" no fuso da fazenda

`fazenda/rules/datas.py::hoje_local()` devolve o dia em `America/Sao_Paulo`
(fallback UTC−3). Substitui `date.today()` (UTC no Railway) nos pontos de "hoje"
de `financeiro.py` e `cartao_credito.py`. O resto do sistema não mudou. Na suíte
de testes, `FAZENDA_HOJE_LOCAL_RELOGIO=relogio_local` (ligado no `conftest.py`)
faz o relógio seguir o da máquina, como o `date.today()` dos testes antigos.

## 6. O que fica para os próximos PRs

O teste do cenário marca cada número ainda errado com `xfail(strict=True)` e o
nome do PR que o corrige; o PR que acertar o número é obrigado a tirar o xfail.

| PR | O que resolve |
|---|---|
| 2 | folha, contratos, diárias e vales nascem com conta (não classificado = 0) |
| 3 | folha pelo bruto e encargos (pessoal de março = 4.840) |
| 4 | leite em kg convertido para litro; Funrural como dedução |
| 5 | cartão por item (CMV com a compra do cartão; fatura em Contas a pagar e no Caixa Real) |
| 6 | saldo de abertura, pagamento futuro como agendado, `valor_pago` obrigatório, Caixa Real sem desconto de vale |
| 7 | juros e descontos da baixa em Outras receitas e despesas |
| 8 | DRE única (campos legados, Portal, Capa) e orçamento com totais separados |
| 9 | COE/COT com rateio: "Todos" sem filtro, depreciação por centro |
