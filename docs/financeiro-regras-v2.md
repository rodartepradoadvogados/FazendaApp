# Financeiro — regras novas dos relatórios (Fase A)

Correção dos números dos Relatórios do Financeiro em PRs pequenos, cada um ligado
**fazenda a fazenda** por uma flag. Este arquivo cobre o PR 0 (rede de segurança),
o PR 1 (natureza do lançamento), o PR 7 (juros e descontos da baixa), o PR 4
(receita do leite), o PR 2 (contas automáticas) e o PR 3 (folha pelo bruto). A auditoria completa, com causa-raiz e a ordem
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

## 6. Juros e descontos da baixa (PR 7)

A diferença apurada na baixa (`conta_gerencial.desconto_acrescimo` = valor
pago − valor da conta) passa a ter destino na DRE. Regras em
`fazenda/rules/juros_descontos.py`; registros em
`financeiro._registros_diferenca_baixa`.

- **Padrão "financeiro"** (decisão do dono, Q1): a linha da conta continua com
  o valor **contratado** e a diferença vira um registro em *Outras receitas e
  despesas*, datado na **data do pagamento**, nos **dois regimes**. Nota de
  despesa: pagou a mais = "(juros e multas pagos)", a menos = "(descontos
  obtidos)". Nota de receita: o inverso ("(juros recebidos)", "(descontos
  concedidos)"). Na DRE de caixa, linha + Outras = `valor_pago` (fecha com o
  Fluxo). A resposta da DRE ganha `diferencas_baixa` (de onde veio cada um).
- **"Abatimento"** (opção no painel de baixa e na baixa em lote detalhada,
  campo `natureza_diferenca` de `PUT /financeiro/lancamentos/{id}/pagar`): o
  desconto reduz o valor da **própria conta** (a parcela passa a valer o pago),
  em DRE, custos, RMCA, custo por litro e orçamento; nada vai para Outras. Só
  para desconto resolvido na baixa (acréscimo ou diferença reparcelada → 400).
  Grava `conta_gerencial.diferenca_tipo` (NULL = financeiro; migração aditiva
  `f3b8d1c6a9e2`). O estorno limpa o campo.
- **Não geram nada**: baixa parcial reparcelada (a diferença virou parcela
  nova, `desconto_acrescimo = 0`), e pago sem `valor_pago` (dado legado; o
  `valor_pago` obrigatório é o PR 6).
- **Natureza**: o juro/desconto é resultado financeiro mesmo quando a nota
  está fora da DRE (juros pagos com o principal do financiamento, multa de
  guia) — exceto aporte/retirada de sócio e transferência, que continuam fora.
- Fatura de fornecedor paga com diferença: o rateio por nota (já existente)
  chega a Outras por nota. A baixa pela fatura não oferece "abatimento" (fica
  financeiro).
- **Fonte única (R4)**: com a flag, RMCA, custo por litro e **orçado ×
  realizado** somam os registros da DRE de competência
  (`financeiro.registros_competencia_v2`), não mais `LancamentoItem.valor_total`
  cru: o desconto da nota de despesa sai rateado nos itens. Juros/descontos da
  baixa não entram em custo nenhum (são resultado financeiro).
- Os campos legados da DRE (`receitas_total`/`despesas_total`/`resultado`) não
  mudam, nem com abatimento: são o PR 8.

## 7. Receita do leite (PR 4)

- **kg → litro**: `fazenda/rules/unidades.py::leite_em_litros` é o helper único
  (`leite_para_kg ÷ 1,029`). Com a flag, o custo por litro converte a entrega
  lançada em kg (antes, 10.320 kg entravam como 10.320 L) e responde
  `unidade_origem` e `litros_convertidos_de_kg`. O RMCA já convertia (o preço
  médio do litro passa pelo mesmo helper, sem mudar número). Produção ›
  Controle × Entregue compara em kg e não muda.
- **Funrural/Senar na nota de venda = dedução** (Q6): na nota de **receita**
  com desconto, o item entra **bruto** em *Receita de vendas* e o desconto vai
  para *Deduções* como "(descontos na nota de venda)", rateado por item. A
  receita líquida não muda. Na nota de despesa, nada muda.
- **RMCA sobre a receita bruta** (Q7), com a líquida ao lado: `gerencial` ganha
  `deducoes_receita_leite`, `receita_leite_liquida` e `rmca_sobre_liquida`;
  `fisico` ganha `receita_leite_liquida` e `rmca_sobre_liquida`.
- **Custo por litro em mês fechado**: período parcial é estendido aos meses
  inteiros que toca (`periodo` = o efetivo, `periodo_solicitado`,
  `periodo_ajustado_para_mes_fechado`, `avisos`).

## 8. Contas automáticas e folha pelo bruto (PR 2 e PR 3)

Folha, férias, 13º, rescisão, guias de FGTS/DCTF, contratos, empreitas,
diárias (pagamento e acerto), vales (em dinheiro, avulso, devolução, assumido
pela fazenda) e o caixa do funcionário/do time (entrada, retenção, estorno)
nasciam sem conta e sem item: caíam em "não classificado" e a folha entrava
pelo líquido. Regras em `fazenda/rules/lancamento_automatico.py`.

- **Contas automáticas** (tabela `conta_padrao_origem`, migração aditiva
  `a7c4e2d9f1b3`; tela *Configurações > Parâmetros financeiros > Contas
  automáticas*, `GET/PUT /financeiro/contas-automaticas[/{origem}]`, só
  administrador): uma conta gerencial por origem (`folha_salario`,
  `folha_ferias`, `folha_13`, `rescisao`, `encargo_fgts`,
  `encargo_inss_patronal`, `obrigacao_inss_irrf_retidos`, `contrato`,
  `empreita`, `diaria`, `vale`, `caixa_entrada`, `caixa_retencao`). Férias, 13º,
  rescisão, encargos, prêmios e vale assumido sem conta própria usam a de
  salários; empreita e diária, a de contratos. A tela mostra uma **sugestão**
  pelo nome do plano ("Salários"...), que nunca é aplicada sozinha.
- **Com a flag ligada**, toda nota automática NOVA nasce com `codigo_conta` e um
  `LancamentoItem` por linha econômica (`gerado_por` = o papel), somando o
  `valor_total` (o que se paga). Quem cria e mantém os itens são os listeners
  de sessão do módulo (ponto único para os 15 pontos de criação e para os
  caminhos que reescrevem o líquido: edição, self-heals, rubricas, retenção no
  pagamento, estorno). Nota com item de gente (reclassificada no Financeiro) não
  é tocada; nota apagada leva os itens gerados.
- **Folha pelo bruto** (decisões do dono): `Salário e verbas` (bruto + verbas)
  em pessoal; `(−) Outros descontos` (cota de VT, coparticipação) abate o
  pessoal; `(−) INSS e IRRF retidos`, `(−) Vale descontado`, `(−) Retenção do
  caixa` e `(−) FGTS/DCTF a recolher` ficam fora da DRE (obrigação/adiantamento);
  `FGTS (provisão)` e `Encargos da DCTF (provisão)` entram em pessoal (encargo
  sem guia usa a provisão). Na DRE de caixa a folha inteira entra na data do
  pagamento do líquido. 13º e rescisão: bruto − retidos (− vale); o 13º cai na
  competência dele (sem provisão mensal, Q5).
- **Guias**: FGTS = provisionado nas folhas da competência (obrigação) +
  excedente (encargo) + multa/juros (*Outras*); DCTF = retidos de folha, 13º e
  rescisão do mês + provisionado (obrigação) + excedente patronal (encargo) +
  multa/juros. Nenhum real conta duas vezes.
- **Contrato, empreita, diária**: o custo é o valor **contratado**; o vale
  avulso abatido da parcela é adiantamento e a retenção do caixa no pagamento é
  obrigação (regras de domínio inalteradas: só administrador, só parcela de
  contrato/empreita/diária). Vale em dinheiro/avulso e devolução = adiantamento;
  entrada no caixa = pessoal; estorno espelha o original.
- **DRE (flag ligada)**: item redutor vira registro de magnitude com o tipo
  invertido (`redutor`); custos por ha/vaca/safra e orçado × realizado subtraem.
  Item gerado sem conta vai para *não classificado* como "(sem conta: …)" e a
  DRE/conferência listam `pendencias_contas_automaticas` /
  `contas_automaticas_pendentes`. **Não classificado e fora da DRE** passam a
  trazer `total_receita`, `total_despesa`, `liquido` (e por conta), em vez de
  só somar receita com despesa.
- **Flag desligada**: nada é criado e os relatórios antigos **ignoram** itens
  com `gerado_por` (RMCA, custo por litro, orçado × realizado e a DRE leem a
  nota como antes) — por isso o backfill pode rodar antes de ligar a flag sem
  mudar número.
- **Consultas** (decisão do dono): os lançamentos da folha aparecem, com
  `origem: "auto"`, o tipo de documento e os itens (`gerado_por`).

**Backfill do histórico** (`fazenda/rules/backfill_itens_automaticos.py`):

```
python -m scripts.backfill_itens_automaticos --fazenda N                      # simulação
python -m scripts.backfill_itens_automaticos --fazenda N --csv plano.csv
python -m scripts.backfill_itens_automaticos --fazenda N --aplicar            # imprime o LOTE
python -m scripts.backfill_itens_automaticos --fazenda N --reverter LOTE --aplicar
```

Só nota automática reconhecida, sem item e sem conta (a classificada à mão é
preservada e listada); cria os mesmos itens que a nota teria hoje e preenche a
conta de item gerado que nasceu sem conta. Nunca muda `valor_total`,
`valor_pago` nem a conta da nota. Cada item criado é uma linha
`__criado__` no `migracao_log_financeiro`; reverter apaga só o que ainda é do
lote. O `downgrade` da migração apaga todos os itens com `gerado_por`.

**Limites conscientes**: o vale de ITEM de nota continua fora do CMV do
fornecedor (não vira registro de adiantamento próprio; a folha mostra o
desconto); reembolso/indenização lançados como rubrica entram em "Salário e
verbas"; a guia é recomposta quando ela ou uma folha da competência muda, mas
não quando muda um 13º/rescisão; desligar a flag depois de ligada mantém os
itens (os relatórios antigos os ignoram).

## 9. O que fica para os próximos PRs

O teste do cenário marca cada número ainda errado com `xfail(strict=True)` e o
nome do PR que o corrige; o PR que acertar o número é obrigado a tirar o xfail.

| PR | O que resolve |
|---|---|
| 5 | cartão por item (CMV com a compra do cartão; fatura em Contas a pagar e no Caixa Real) |
| 6 | saldo de abertura, pagamento futuro como agendado, `valor_pago` obrigatório, Caixa Real sem desconto de vale |
| 8 | DRE única (campos legados, Portal, Capa) e orçamento com totais separados |
| 9 | COE/COT com rateio: "Todos" sem filtro, depreciação por centro |
