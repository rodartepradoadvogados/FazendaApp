# Financeiro — regras novas dos relatórios (Fase A)

Correção dos números dos Relatórios do Financeiro em PRs pequenos, cada um ligado
**fazenda a fazenda** por uma flag. Este arquivo cobre o PR 0 (rede de segurança),
o PR 1 (natureza do lançamento), o PR 7 (juros e descontos da baixa), o PR 4
(receita do leite), o PR 2 (contas automáticas), o PR 3 (folha pelo bruto), o PR 6
(saldo de abertura e Caixa Real), o PR 5 (cartão de crédito por item), o PR 8
(DRE única) e o PR 9 (custos com rateio por centro). A auditoria completa, com causa-raiz e a ordem dos PRs, ficou no
relatório da Fase A (`SOLUCOES.md`, fora do repositório).

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
depreciação por centro, com o rateio do bem sem centro, é o PR 9 (§12).

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
(simulando o backfill sem gravá-lo) e os Δ. A seção `saldo` (PR 6) traz, por
conta corrente, o saldo de hoje antigo × novo, os agendados, a falta de saldo
de abertura e quantos lançamentos o backfill do vínculo liga ou manda para revisão. O CSV de lançamentos lista cada
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
- Os campos legados da DRE (`receitas_total`/`despesas_total`/`resultado`)
  passaram a vir da cascata no PR 8 (§11) — com o abatimento dentro.

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

**Contas do sistema (3.03.01.16 e 3.03.01.17)**: o plano de contas passa a ter,
sob 3.03.01 (Pessoal), `3.03.01.16 Retenções` (`NAO_ENTRA_NA_DRE`, `OBRIGACAO`) e
`3.03.01.17 Vales e adiantamentos` (`NAO_ENTRA_NA_DRE`, `ADIANTAMENTO`), com
`linha_dre`/`natureza_fin` próprias (a herança por prefixo as jogaria em pessoal).
Regras em `fazenda/rules/plano_padrao.py`:

- a migração de dados `d8b3f6a1c294` cria as duas contas nas fazendas que já têm o
  grupo 3.03.01 (não cria o grupo, não sobrescreve conta existente, mesmo com outro
  nome); o downgrade remove só o que ela criou e que nada referencia;
- `garantir_contas_do_sistema(session, fazenda_id)` roda ao final da importação do
  CSV do plano (que apaga e reinsere tudo) e ao ligar a flag pela tela de
  parâmetros. **Conta do sistema tem de sobreviver à reimportação do plano.**
- os papéis de retenção (`folha_retencao_caixa`, `contrato_/empreita_/diaria_retencao`,
  `caixa_retencao`) usam 3.03.01.16 e os de vale (`folha_vale`, `rescisao_vale`,
  `contrato_/empreita_/diaria_vale`, `vale`, `vale_devolucao`) usam 3.03.01.17
  (`codigo_preferido`) **só quando a conta existe e está ativa e a origem não tem
  conta configurada** em *Contas automáticas*; a configuração à mão sempre vence.
  `GET /financeiro/contas-automaticas` mostra `conta_do_sistema` por origem.
  Com a flag desligada nada muda (itens automáticos são ignorados).
- histórico: `python -m scripts.backfill_contas_origem --fazenda N [--repintar-itens]
  [--csv x.csv] [--aplicar] [--reverter LOTE]` grava `ContaPadraoOrigem` de `vale` e
  `caixa_retencao` onde estiver vazia e, com `--repintar-itens`, dá conta aos itens
  gerados antigos de retenção/vale que estão sem conta (log em
  `migracao_log_financeiro`, reversível por lote).

**Limites conscientes**: o vale de ITEM de nota continua fora do CMV do
fornecedor (não vira registro de adiantamento próprio; a folha mostra o
desconto); reembolso/indenização lançados como rubrica entram em "Salário e
verbas"; a guia é recomposta quando ela ou uma folha da competência muda, mas
não quando muda um 13º/rescisão; desligar a flag depois de ligada mantém os
itens (os relatórios antigos os ignoram).

## 9. Saldo de abertura e Caixa Real (PR 6)

Regras em `fazenda/rules/saldo_conta.py`; Caixa Real em `financeiro._caixa_real_v2`.
Com a flag desligada, saldo, Caixa Real, fundo de reserva, Contas a pagar e o
fluxo do cartão saem como antes — travado por
`tests/dados/caixa_cartao_golden_pre_pr56.json` (gerado pelo código de antes,
com o relógio parado; `tests/dados/gerar_golden_caixa_cartao.py`).

- **Saldo de abertura** (decisão Q12: campo na conta, não lançamento):
  `conta_corrente.saldo_abertura` + `data_saldo_abertura`, gravados em
  `PUT /financeiro/contas-correntes/{id}/saldo-abertura` (só admin; os dois
  juntos; data não pode ser futura). Tela: Parâmetros financeiros › Conta
  corrente › Editar.
- **Saldo de hoje** = abertura + pagamentos/recebimentos com
  `data_saldo_abertura < data de caixa ≤ hoje` ± transferências no mesmo
  intervalo. Sem abertura, é a soma dos movimentos e a resposta traz
  `pendente_saldo_abertura` e o aviso "Informe o saldo de abertura" (o Caixa
  Real mostra a pendência no lugar do número). `GET /financeiro/contas-correntes`,
  `/caixa-real` e `/caixa-real/fundo-reserva-sugerido` aceitam `?hoje=` (o
  `hojeLocal()` do front); sem ele, `hoje_local()` (Brasília).
- **Vínculo por FK**: `conta_gerencial.conta_corrente_id`, gravado em toda
  baixa (individual, lote, lote detalhado, criação já paga, compra/venda de
  animal, compra de sêmen) quando o rótulo casa exatamente com uma conta da
  fazenda, ou pelo `conta_corrente_id` explícito (404 se for de outra
  fazenda). Linha sem FK ainda casa pelo rótulo exato (histórico).
  O histórico se liga pelo comando
  `python -m scripts.backfill_conta_corrente --fazenda N [--csv revisao.csv] [--aplicar] [--reverter LOTE]`
  (exato → normalizado: banco + dígitos da agência seguidos dos da conta →
  banco único: só o nome do banco e uma conta nele); o que sobra vai para a
  lista de revisão (`GET /financeiro/conta-corrente/revisao`) e se liga em lote
  (`PUT /financeiro/lancamentos/conta-corrente-lote`, admin). Log em
  `migracao_log_financeiro`, reversível por lote.
- **`valor_pago` obrigatório**: com a flag, lançamento que já nasce pago sem
  `valor_pago` grava o valor da parcela (antes: `None` e `desconto_acrescimo
  = −valor`, o L6); valor pago ≤ 0 → 400 (criação, baixa, lote detalhado). O
  histórico NÃO é reescrito: o saldo lê pago sem `valor_pago` pelo valor da
  parcela (igual ao Livro do front).
- **Pagamento com data futura = agendado** (Q13): não entra no saldo de hoje;
  aparece no Caixa Real na data dele com `agendado: true` (os que passam da
  janela ficam em `agendados_fora_da_janela`). A baixa responde `agendado`;
  a tela confirma antes ("Agendar pagamento para dd/mm?") e a lista mostra
  "Agendada para dd/mm" (`data_caixa`, só com a flag, em `GET /lancamentos`).
- **Cartão avulso** (`forma_pagamento="credito"`): a data de caixa é o
  vencimento do cartão — saldo, Caixa Real, DRE de caixa e `mes_caixa` da lista.
- **Retirada do caixa do funcionário pelo banco** (pix/transferência/débito
  com conta; dinheiro não): gera `ContaGerencial` despesa paga, natureza
  `OBRIGACAO` (fora da DRE e dos custos), `gerado_por="caixa_retirada"`,
  ligada ao movimento pelo `numero_lancamento`. Estorno = receita contrária na
  data do estorno; exclusão da retirada apaga o lançamento.
- **Caixa Real sem o desconto do vale** (P0-7): compromisso em aberto vale o
  que vai sair do banco (`vale_item.valor_caixa_parcela`): o boleto inteiro,
  com o vale de item dentro (o acerto é com o funcionário). O fundo de reserva
  sugerido soma o valor pago, na data de caixa, também sem o ajuste do vale.
- O Livro caixa (Consultas, com conta escolhida) parte do saldo de abertura.
- Migração `a7c4e2d9b351` (aditiva, idempotente, reversível): as colunas
  acima e `conta_gerencial.gerado_por`.

## 10. Cartão de crédito por item (PR 5)

Regras em `fazenda/rules/cartao_por_item.py`; rotas em `cartao_credito.py`.
Com a flag desligada, compra, fechamento e pagamento da fatura funcionam como
antes (nota genérica "Fatura X"), com as mesmas chaves de resposta (golden).

- **Uma nota por compra**, na hora da compra: `ContaGerencial` + item com a
  conta e o centro da compra, competência = data da compra, vencimento = o da
  fatura, `fatura_cartao_id` = a fatura (`lancamento_cartao.numero_lancamento`
  aponta a nota). IOF, anuidade e juros do rotativo são **compras próprias**
  (Q14), lançadas numa conta própria.
- **Contas a pagar e Caixa Real**: a nota em aberto entra no total a pagar
  (decisão a do dono) e na projeção, no vencimento da fatura (`fatura_cartao`
  no item do Caixa Real). A lista mostra "Em fatura do cartão" e o botão
  "Pagar pela fatura do cartão".
- **Só se paga pela fatura**: baixa individual, lote, lote detalhado e estorno
  de uma nota de cartão → 409. `POST /financeiro/cartoes/faturas/{id}/pagar`
  (fatura fechada) baixa TODAS as notas de uma vez (data, conta do cartão,
  comprovante); `valor_pago` diferente do total → a diferença é rateada em
  centavos entre as notas (a sobra na última), como na fatura de fornecedor, e
  vira juros/desconto em Outras (PR 7). A fatura guarda `valor_pago` e
  `desconto_acrescimo`; nenhuma nota genérica é criada. Compra lançada antes da
  flag ganha a nota no pagamento. `POST .../estornar-pagamento` desfaz (as
  notas voltam a aberto juntas).
- **DRE**: competência no mês da compra; caixa no mês do pagamento da fatura.
- **Histórico**: `python -m scripts.backfill_cartao_por_item --fazenda N
  [--csv x.csv] [--aplicar] [--reverter LOTE]` (exige a flag ligada). Compra
  de fatura aberta/fechada ganha a nota em aberto; compra de fatura já paga
  ganha a nota já paga na data da genérica, SEM conta bancária
  (`gerado_por="backfill_cartao"`: só classifica a DRE — saldo, Caixa Real,
  fundo de reserva e as somas do front a ignoram), e a genérica vira
  `OBRIGACAO` (fora da DRE; continua sendo o único movimento de dinheiro). O
  resto vai para revisão. A reversão apaga as notas criadas, salvo as que
  mudaram depois (conflito).
- Migração `b9d3f5a1c864` (aditiva, idempotente, reversível).

## 11. DRE única (PR 8)

Um número de resultado em todas as telas (R4). Com a flag desligada, nada
muda (golden: DRE, campos legados, Capa e o CSV do Portal byte a byte).

- **`resumo` da DRE** (`rules/dre.py::resumo_da_cascata`, só com a flag):
  `receita_bruta`, `receita_liquida`, `despesas` (= receita líquida −
  resultado), `ebitda`, `resultado_operacional`, `resultado_liquido`,
  `margem_liquida_pct` (só com receita líquida > 0), `fora_da_dre_total` e
  `nao_classificado` (com `_receita`/`_despesa`) — tudo tirado da cascata.
- **Campos legados derivados da cascata** (flag ligada): `receitas_total` =
  receita líquida, `resultado` = resultado líquido, `despesas_total` = a
  diferença, `por_conta` = só o que entrou nas linhas, por nível 1 do código
  (depreciação e baixa de bem como pseudocontas; Σ receitas − Σ despesas =
  resultado). Antes era a soma de todas as notas (trator, aporte, principal,
  vale e não classificado dentro; sem depreciação).
- **Capa** (`GET /financeiro/resultado-mes-recente`, flag ligada): o
  `resultado_liquido` da DRE de competência do mês mais recente com
  lançamento (`fonte: "dre_competencia"`), não mais a soma crua de
  `valor_total`.
- **CSV do Portal** (e-mail e Exportar): decisão do dono (Q16) — há cliente
  que importa o CSV numa planilha, então o arquivo antigo
  (`dre_<de>_<até>.csv`, mesmo formato `_dict_para_csv`, agora com os números
  da cascata) continua saindo **até 07/12/2026** (`portal.CSV_DRE_LEGADO_ATE`,
  60 dias) ao lado do novo `dre_<de>_<até>_cascata.csv`
  (`portal._dre_para_csv`: cabeçalho com fazenda, período, regime e centro;
  as 15 linhas; o detalhe por conta; o resumo; fora da DRE por natureza; não
  classificado com receita e despesa separadas). Depois da data, só o novo.
  O e-mail leva os dois anexos (`rules/email.py::enviar_email(...,
  anexos_extras=...)`) e explica no corpo; o ZIP do Exportar leva
  `dre.csv` + `dre_cascata.csv`.
- **Front (aba DRE)**: **um** seletor de regime no filtro do topo (também na
  URL, `?regime=caixa`) vale para indicadores, gráfico, cascata e
  detalhamento; a DRE é buscada uma vez pela página
  (`DreCascataView` não tem mais seletor próprio). Com o `resumo`, os KPIs
  (Receita líquida, Despesa, Resultado líquido, Margem) e o gráfico
  "Receita × Despesa × Resultado" leem o servidor (`lib/dreUnica.ts::kpisDre`)
  — natureza aplicada, depreciação dentro — e o "Detalhamento por conta
  gerencial" sai das contas de cada linha da cascata. Sem o `resumo` (flag
  desligada), a tela soma no cliente como antes. Com a flag, o centro de
  custo do filtro também filtra a cascata.
- **Orçado × realizado** (`rules/orcamento.py`, flag ligada): realizado pelos
  registros da DRE de competência; totais SEPARADOS em `totais.receita`,
  `totais.deducao`, `totais.despesa_operacional` e `totais.fora_do_resultado`
  (nunca receita somada com despesa); herança por prefixo (Q8): o orçamento de
  um grupo cobre as filhas **do mesmo tipo** sem orçamento próprio (`cobre`; a
  filha aparece como linha informativa com `coberta_por`, sem desvio e fora
  dos totais) e a filha com orçamento fica na dela; fora do resultado e
  deduções nunca sobem para um orçamento. Desvio só com orçado (`situacao`:
  `favoravel`/`desfavoravel`/`no_orcado`/`sem_orcamento`/
  `coberta_pelo_grupo`/`fora_do_resultado`): receita acima do orçado é
  favorável, despesa acima é desfavorável. `total_orcado`/`total_realizado`
  ficam como os de despesa operacional (compatibilidade). A tela mostra um
  quadro por grupo e pinta o desvio pela situação.
- Script de impacto: a seção da DRE ganha `dre.legado.receitas_total`,
  `dre.legado.despesas_total` e `dre.legado.resultado` (antes × depois).

## 12. Custos com rateio correto por centro (PR 9)

Com a flag desligada, nada muda (custo por vaca sem centro = Pecuária
Leiteira; depreciação inteira em qualquer filtro).

- **"Todos" no custo por vaca** (`GET /financeiro/custo-vaca-lote`): sem
  `centro_custo` na URL (é o que o "Todos" da tela manda) = todos os centros,
  como no custo por hectare e na DRE. Antes caía em "Pecuária Leiteira".
- **Depreciação por centro de custo** (`financeiro.depreciacao_periodo_v2`),
  na DRE (os dois regimes), no COT e nos custos por hectare, vaca/lote e
  safra. Sem filtro: a do patrimônio inteiro (igual a antes). Com o centro C:
  bem com `patrimonio.centro_custo` = C entra inteiro; bem de outro centro não
  entra; bem **sem centro é rateado** (decisão do contador, Q9) pela
  participação de C nas despesas operacionais do período (competência,
  natureza operacional, vale descontado, item redutor da folha abatendo —
  a mesma base do numerador dos custos). Os pedaços dos centros somam a
  depreciação da fazenda. Sem despesa operacional no período, a participação
  é 0 e a resposta avisa ("informe o centro no cadastro do bem").
  A DRE responde `depreciacao_periodo.rateio` e os custos
  `depreciacao_rateio` (bens do centro, sem centro, de outros centros,
  participação, base e o valor rateado).
- **Centro do bem**: campo "Centro de custo" no cadastro de Patrimônio (vazio =
  rateado). Com a flag, o bem criado junto com a compra (`criar_patrimonio`)
  nasce no centro da nota, salvo centro explícito. Bens antigos ficam sem
  centro (rateados) até alguém informar.
- **Front**: a cascata mostra como a depreciação foi repartida no filtro de
  centro; custos por hectare, vaca e safra mostram depreciação, COT (e COT por
  hectare/vaca) com as regras novas.
- Cenário (março/2031, só a flag, mais 2.915 de insumo e uma ensiladeira de
  12.000 no centro Agricultura): Pecuária 11.660 e Agricultura 2.915 de
  despesa operacional (80%/20%); trator (1.000, sem centro) rateado 800/200;
  ensiladeira (100) inteira na Agricultura → Pecuária 800, Agricultura 300,
  fazenda 1.100 (`test_pr9_depreciacao_rateada_entre_os_centros`).

## 13. Classificar: a fila e o lote (tela Relatórios › Resultado › Classificar)

A DRE deixa de fora o que não tem classificação (nunca finge que fecha). A tela
**Classificar** lista esse resíduo lançamento a lançamento e o resolve em lote,
com Desfazer. Regras em `fazenda/rules/classificacao_manual.py`; rotas em
`fazenda/api/routers/classificacao.py` (mesmas travas do router do Financeiro).

- **Fila** — `GET /financeiro/classificacao/pendencias?data_inicio&data_fim&regime&centro_custo`
  (`inicio`, `fim` e `centro` são apelidos). Lê os MESMOS registros da DRE
  (`_registros_dre_para_cascata`) e aplica as regras do motor, então a fila fecha com o
  “sem classificação” e o “fora da DRE sem motivo” da cascata. Uma linha por
  lançamento/item (as parcelas somam), com `conta_id`, `item_id`, `numero_lancamento`,
  fornecedor, descrição, valor, data (pelo regime), conta atual, `acoes` possíveis, `travas`
  (o porquê de cada ação travada) e `sugestao`. Também vem agrupada (`por_motivo`,
  `por_conta`), com `ultimo_lote` (o Desfazer) e `bloqueios`. Limite de 1.000 linhas
  (`resumo.truncado`); os totais contam todas.

  | motivo | o que é | como se resolve |
  |---|---|---|
  | `conta_sem_linha_dre` | a conta não tem linha da DRE (nem herdada) | `linha_dre` da conta (vale para todos os lançamentos dela) |
  | `sem_codigo_conta` | lançamento ou item sem conta gerencial | `conta` do item (ou da nota, se ela não tem itens) |
  | `item_sem_conta_automatica` | folha/contrato/diária gerado sem conta (**só v2**) | `conta` do item (ou configurar a origem em Contas automáticas) |
  | `natureza_nao_informada` | conta “não entra na DRE” sem dizer o motivo (**só v2**) | `natureza` (da conta do plano ou só do lançamento) |

- **Sugestões** (nunca aplicadas sozinhas; a tela as mostra e aceita com um clique): linha
  da DRE pelas contas irmãs (mesmo pai, todas na mesma linha) e, depois, pelo nome da conta;
  conta pelo histórico do fornecedor (≥ 50% das notas dele numa conta-folha ativa) ou pelo nome
  que combina com a origem automática; natureza pelo nome (`inferir_natureza_por_nome`).
- **Lote** — `POST /financeiro/classificacao/aplicar` (administrador; `get_fazenda_id_escrita`):
  `{"acoes":[{"tipo":"conta|natureza|linha_dre","alvo":{...},"valor":"..."}],"motivo":"..."}`.
  **Tudo ou nada**: valida todas as ações antes de gravar (422 com `erros[{indice,codigo,mensagem}]`).
  Cada campo mudado vira uma linha em `migracao_log_financeiro` (migração
  `classificacao_manual_v1`, lote `classificacao-…`, antes/depois, motivo). Nunca toca valor,
  data, pagamento nem conta bancária. Aplicar de novo o que já está assim não muda nada
  (`lote: null`).
- **Desfazer** — `POST /financeiro/classificacao/reverter/{lote}`: devolve o valor de antes **só**
  onde o valor de hoje ainda é o que o lote gravou (o resto vira `conflitos`, intocado). Só lotes
  desta tela e da própria fazenda (outra fazenda → 404).
- **Flag desligada** (nada muda de número): a fila lista só o que a regra antiga também enxerga
  (`conta_sem_linha_dre` e `sem_codigo_conta`); `natureza` e `item_sem_conta_automatica` vêm
  travados com o porquê, e uma ação `natureza` responde 409 `regras_v2_desligadas`. Uma nota com
  só itens gerados pelo sistema aceita a conta na nota (a regra antiga a lê) e a resposta avisa
  que, com as regras novas, vale a conta configurada em Contas automáticas.
- **Mês fechado** (só com a flag): ação sobre o **lançamento** (`conta`, `natureza` por lançamento)
  com competência ou pagamento em mês fechado → 409 `mes_fechado` (nada é gravado) e o Desfazer
  também. Ação sobre a **conta do plano** (`linha_dre`, natureza padrão) segue a regra já documentada
  do Fechamento — vale para todos os meses e não trava —, mas a resposta traz `avisos` com os meses
  fechados que mudam (o Fechamento mostra “mudou depois do fechamento”).
- O checklist do Fechamento do mês (`sem_conta`) agora leva para esta tela (`destino: "classificar"`).
  A DRE por conta (tela anterior, `dre_contas`) foi removida; `?sub=dre_contas` redireciona para cá.

## 14. O que fica

Com os PRs 0 a 9 ligados (contas automáticas, os backfills da folha e do
cartão, a natureza do plano e a flag), o cenário da auditoria em março/2031
fecha como o relatório previa: receita líquida 9.850, CMV 8.300, pessoal 4.840,
EBITDA −3.290, resultado −4.290 — o mesmo na cascata, no resumo (KPIs), nos
campos legados, nos dois CSVs do Portal (`test_pr8_um_resultado_em_todas_as_telas_com_tudo_ligado`)
—, numerador de custos 13.140 (COT 14.140) e custo por litro 0,8276. Não sobra
nenhum `xfail` da Fase A no teste do cenário.

Fora da Fase A (registrado para depois): fechamento/conciliação e LCDPR (feitos na Fase C5 — fechamento com trilha, conciliação bancária e pacote do contador com o apoio ao LCDPR; ver `docs/financeiro-fechamento-conciliacao.md`, inclusive o que falta para o TXT de transmissão do LCDPR); 13º
e férias com provisão mensal (Q5); vale de ITEM como adiantamento próprio na
nota do fornecedor; "Detalhamento por conta" da DRE com drill para Consultas
filtrada por conta; data de corte do CSV antigo do Portal (07/12/2026) — depois
dela, remover `_dict_para_csv` da DRE.
