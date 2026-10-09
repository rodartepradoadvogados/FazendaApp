# Financeiro — Fechamento do mês, Conciliação bancária e Pacote do contador (Fase C5)

Relatórios › **Entrega ao contador** ("Está pronto para o contador?"), três telas no molde
único dos Relatórios (`RelatorioShell`), conforme o mockup aprovado e o PLANO.md §8:

| Tela | id (`?sub=`) | Pergunta | Componente |
|------|--------------|----------|------------|
| Pacote do contador | `pacote_contador` | O que entrego ao contador? | `components/financeiro/relatorios/PacoteContadorView.tsx` |
| Fechamento do mês | `fechamento_mes` | Setembro/2026 está pronto para fechar? | `components/financeiro/relatorios/FechamentoMesView.tsx` |
| Conciliação bancária | `conciliacao` | O banco bate com o sistema? | `components/financeiro/relatorios/ConciliacaoView.tsx` |

Backend: `fazenda/api/routers/fechamento_conciliacao.py` (prefixo `/financeiro`, montado em
`main.py` com as MESMAS travas do router do Financeiro: módulo `financeiro`, plano contratado,
fazenda selecionada e `bloquear_escrita_contador`). Regras: `fazenda/rules/fechamento_mes.py`,
`conciliacao.py` (pura), `conciliacao_banco.py`, `extrato_bancario.py` (pura) e
`pacote_contador.py`. Modelos: `fazenda/models/fechamento.py`. Testes:
`backend/tests/test_fechamento_conciliacao.py` e `frontend/lib/relatorioFechamento.test.ts`.

## 1. Flag e o que NÃO muda

- Nenhuma das três telas muda número de relatório. Fechar grava uma linha na trilha; conciliar
  marca o que o banco confirmou; o pacote lê.
- A **trava do mês fechado** só existe com a flag `financeiro_regras_v2` **ligada** na fazenda.
  Desligada (ou sem fechamento nenhum), `fechamento_mes.exigir_meses_abertos` sai na primeira
  linha: as rotas de lançamento se comportam exatamente como antes e os goldens
  (`tests/dados/*.json`) continuam valendo (`test_relatorios_cenario_auditoria.py` passa sem
  mudança). Com a flag desligada, fechar responde 409 `regras_v2_desligadas`; a tela mostra o
  checklist como lista do que falta.
- Conciliação e pacote funcionam com a flag desligada; o pacote sai com a DRE das regras antigas
  e o livro caixa sem natureza (a nota de método diz isso).

## 2. Fechamento do mês

**Modelo** `fechamento_mes_evento` (APPEND-ONLY): `fazenda_id`, `mes` ("AAAA-MM"), `acao`
("fechar" | "reabrir"), `motivo`, `usuario_id`, `usuario_nome` (copiado: prova não muda se o
cadastro mudar), `retrato_json` + `retrato_sha256` (só no fechar), `pendencias_no_fechamento`,
`criado_em` (UTC). O estado do mês = o último evento. Imutável em duas camadas, como
`juridico.py`: `before_flush`/`do_orm_execute` recusam UPDATE/DELETE (RegistroImutavelError) e
gatilhos no banco (`cowdata_bloquear_append_only()` em PostgreSQL; RAISE(ABORT) em SQLite).

**Checklist** (`GET /financeiro/fechamento/{mes}`, ao vivo; todos bloqueiam o "Fechar"):

| id | Conferência | Fonte |
|----|-------------|-------|
| `sem_conta` | Lançamentos sem conta ou sem linha da DRE | `nao_classificado.contas` da DRE de competência do mês |
| `natureza` | Natureza a revisar | `pendencias_natureza` da DRE (investimento sem bem) |
| `contas_automaticas` | Contas automáticas configuradas | `pendencias_contas_automaticas` da DRE |
| `saldo_abertura` | Saldo de abertura das contas correntes | conta ativa sem `saldo_abertura`/`data_saldo_abertura` |
| `cartao` | Faturas do cartão fechadas | `fatura_cartao.status = aberta` com `data_fechamento` ≤ fim do mês |
| `folha` | Folha do mês fechada e paga | `folha_pagamento` da competência com status ≠ pago |
| `conciliacao` | Conciliação bancária feita | conta com movimento no mês sem extrato importado ou com linha pendente |
| `depreciacao` | Depreciação do mês calculada | `depreciacao_periodo.inconsistencias` (bem sem data/vida útil) |

**Retrato**: DRE de competência e de caixa do mês (linhas da cascata, não classificado, fora da
DRE), entradas e saídas de caixa (data de caixa, valor pago) e saldo de cada conta no fim do mês
(regra do saldo novo). JSON canônico (chaves ordenadas) → SHA-256. A tela compara o retrato de
agora com o do fechamento e avisa "os totais mudaram depois do fechamento" (mudança que passou
por fora da trava, ex.: linha da DRE de uma conta no plano).

**Rotas**

| Método e rota | Quem | Contrato |
|---------------|------|----------|
| `GET /financeiro/fechamento/meses?ate=AAAA-MM&quantidade=24` | quem lê o Financeiro (inclui contador) | `{regras_v2, hoje, meses:[{mes,status:aberto|fechado|em_curso,fechado_em,fechado_por,reaberto}], trilha:[evento]}` |
| `GET /financeiro/fechamento/{mes}` | idem | `{mes, inicio, fim, regras_v2, status, pode_fechar_a_partir_de, evento_atual, trilha_do_mes, checklist:[{id,nome,txt,ok,bloqueia,quantidade,itens,destino,rotulo_acao,resumo}], pendencias, retrato_atual, retrato_atual_sha256, retrato_fechamento?, mudou_desde_o_fechamento?}` |
| `POST /financeiro/fechamento/{mes}/fechar` `{motivo?, forcar}` | administrador (`exigir_admin`), `get_fazenda_id_escrita` | 201 `{evento, retrato}`. 409 `regras_v2_desligadas` · `mes_em_curso` (só depois do último dia) · `ja_fechado` · `pendencias` (sem `forcar`). 422 sem motivo quando há pendência. |
| `POST /financeiro/fechamento/{mes}/reabrir` `{motivo}` | administrador | 201 `{evento}`. 422 motivo < 5 caracteres; 409 `nao_fechado`. |

**Trava** (`exigir_meses_abertos(session, fazenda_id, datas, acao)`): 409 com
`detail = {codigo: "mes_fechado", meses: [...], mensagem: "Setembro/2026 está fechado: para
editar um lançamento ... reabrir com motivo em Relatórios › Fechamento do mês ..."}` (o
`mensagemErroApi` do front já mostra `mensagem`). Pontos travados:

- `POST /financeiro/lancamentos` (competência, pagamento na criação e de cada parcela);
- `PUT /financeiro/lancamentos/{id}` (datas atuais e as novas);
- `PUT /financeiro/lancamentos/{id}/pagar`, `baixa-lote`, `baixa-lote-detalhada` (data do
  pagamento nova, baixa anterior e, se a diferença for **abatimento**, a competência — porque o
  abatimento muda o valor da competência);
- `POST /financeiro/lancamentos/{id}/estornar` (data de caixa da baixa);
- `PUT /financeiro/lancamentos/{numero}/natureza` (competência);
- exclusão pelo motor genérico (`/exclusoes/impacto` e `/confirmar`, tipo "financeiro", todas as
  parcelas).

Baixa de conta de mês fechado com pagamento em mês aberto passa (o resultado da competência não
muda; juros/desconto vão para o mês do pagamento).

**Limites conscientes**: não travam (ainda) os caminhos que escrevem lançamento por fora dessas
rotas — folha (lançar/pagar/estornar), cartão (fatura), compra/venda de animal e de sêmen,
diárias, contratos, caixa do funcionário, recorrentes, importação de CSV — nem a classificação
do plano de contas (vale para todos os meses). Para todos eles o retrato SHA-256 mostra depois
que o número mudou. Próximo passo: levar `exigir_meses_abertos` a esses routers.

## 3. Conciliação bancária

**Modelos** `extrato_importacao` (conta, formato, período, saldo final e data do saldo, linhas
novas/repetidas, quem) e `extrato_linha` (conta, data, valor com sinal, histórico até 120
caracteres, nº do documento, `chave_dedup`, `status` pendente|pareado|sem_lancamento,
`lancamento_id` OU `transferencia_id`, observação, quem/quando conciliou). Único por
`(fazenda_id, conta_corrente_id, chave_dedup)`. O arquivo do extrato **não** é guardado (LGPD).

**Leitura do extrato** (`rules/extrato_bancario.py`, parser próprio, sem dependência nova):
OFX 1.x (SGML, sem fechamento de tag) e 2.x (XML); CSV com `;`, `,` ou tab, cabeçalho achado nas
20 primeiras linhas pelos nomes (data; histórico/descrição/lançamento/detalhes; valor OU
crédito+débito; documento; saldo; tipo D/C ou Entrada/Saída). Números "1.234,56", "-68,00",
"68,00 D", "(68,00)", "20,00-", "1234.56". Linhas "Saldo anterior"/"S A L D O"/"Saldo do dia" não
são movimento: viram o saldo informado (o "anterior" é ignorado). Chave: FITID+data+valor no OFX;
hash de (data, valor, histórico, documento) + ordem da ocorrência no CSV — reimportar ou importar
período sobreposto não duplica. Limite de 5 MB; XLS/PDF recusados com mensagem.

**Casamento** (`rules/conciliacao.py`, puro): mesmo sinal; valor igual ao centavo ("exata") ou
até 10% de diferença ("valor diferente", só alternativa, nunca em lote); data ± 3 dias;
pontuação = 100 − 10×dias + 20×semelhança do texto (palavras em comum, sem as vazias de banco)
− 40 se não exata. Atribuição gulosa, cada movimento do sistema casa com uma linha só.

**Lado do sistema** (`rules/conciliacao_banco.py`): o mesmo dinheiro do saldo da conta —
lançamento pago com data de caixa no período, casado pela FK `conta_corrente_id` (ou rótulo
exato no histórico sem FK), pelo valor pago; transferências entre contas. Saldo do sistema na
data do saldo do extrato pela regra do saldo novo (abertura + movimento), qualquer que seja a
flag (tela nova).

**Rotas**

| Método e rota | Contrato |
|---------------|----------|
| `GET /financeiro/conciliacao?mes=AAAA-MM&conta_corrente_id=` | `{mes, contas, resumo:[por conta: importado, pendentes, so_no_sistema, saldos, movimento, conciliada], situacao:{linhas:[...com par, sugestao, alternativas], so_no_sistema, contagem, movimento, saldos:{saldo_extrato, saldo_sistema, diferenca, bate, data, pendente_saldo_abertura}}, importacoes}` |
| `POST /financeiro/conciliacao/importar` (multipart `conta_corrente_id`, `arquivo`) | 201 `{formato, linhas_novas, linhas_repetidas, data_inicio, data_fim, saldo_final, data_saldo}`; 422 arquivo não reconhecido; 413 > 5 MB; 404 conta de outra fazenda |
| `POST /financeiro/conciliacao/linhas/{id}/parear` `{lancamento_id | transferencia_id}` | 409 se a linha não está pendente, lançamento não pago, de outra conta, sinal trocado ou já pareado |
| `POST /financeiro/conciliacao/linhas/{id}/sem-lancamento` `{observacao?}` | marca "sem lançamento" |
| `POST /financeiro/conciliacao/linhas/{id}/desfazer` | volta a pendente |
| `POST /financeiro/conciliacao/confirmar-sugestoes` `{conta_corrente_id, mes, linha_ids?}` | confirma as sugestões EXATAS (a fila) |

Toda escrita usa `get_fazenda_id_escrita`; o contador só lê (403 nas escritas). O atalho
"Lançar no sistema" da tela cria o lançamento pago pelo `POST /financeiro/lancamentos` de sempre
(com Idempotency-Key) e pareia em seguida.

## 4. Pacote do contador

`GET /financeiro/pacote-contador?data_inicio&data_fim` (o que vai no pacote, para a tela),
`/pacote-contador/zip` e `/pacote-contador/pdf` (download). Período até 13 meses (o
ano-calendário é o comum). Também sai pelo e-mail do Portal (`POST /portal/email` com
`relatorio: "pacote_contador"` → anexo ZIP), reaproveitando o motor de e-mail e o mesmo recorte
de destinatários. O Painel do Contador (`/contador`, aba "Pacote do contador") baixa pelo GET.
Cada geração do ZIP/PDF grava `exportacao_relatorio_log` (quem, quando, formato).

**ZIP**: `pacote-contador_<fazenda>_<ini>_<fim>.pdf` (cabeçalho do cliente: fazenda, CPF/CNPJ do
cadastro, período, regime, centro, data e quem gerou; DRE competência e caixa, livro caixa,
não classificados e pendências, patrimônio e depreciação, conciliação e fechamento, nota de
método), `.xlsx` (uma aba por bloco, números reais), `dre_competencia.csv` e `dre_caixa.csv`
(pelo `_dre_para_csv` do Portal), `livro_caixa.csv`, `livro_caixa_mensal.csv`,
`nao_classificados.csv`, `pendencias.csv`, `patrimonio_depreciacao.csv`, `conciliacao.csv`,
`fechamentos.csv` (trilha com SHA-256), `lcdpr_apoio_Q100.csv`, `lcdpr_apoio_Q200.csv` e
`LEIA-ME.txt`.

**Livro caixa**: o que passou pelo caixa no período (data de caixa, valor pago; nota de
classificação do backfill do cartão fora; transferências entre contas próprias fora). Com a
flag, cada linha leva a natureza e "entra no resultado da atividade" (operacional ou
investimento). Saldo inicial = soma dos saldos das contas no dia anterior (regra do saldo novo);
sem saldo de abertura, avisa.

**LGPD**: vai o CPF/CNPJ da própria fazenda (o contador precisa); dos participantes, só o nome
como está no lançamento; da folha, só totais e o nº da folha (sem nome de funcionário); nada de
saúde, endereço ou contato.

## 5. LCDPR (apoio, não transmissão)

`lcdpr_apoio_Q100.csv` e `Q200.csv` (separador `|`, decimal com vírgula) no leiaute do Livro
Caixa Digital do Produtor Rural: DATA (ddmmaaaa), COD_CONTA (id da conta corrente no sistema),
NUM_DOC, TIPO_DOC (1 NF, 2 fatura, 3 recibo, 4 contrato, 5 folha, 6 outros — conferir no manual
vigente), HIST, TIPO_LANC (1 receita, 2 despesa de custeio/investimento), VL_ENTRADA, VL_SAIDA,
SLD_FIN, NAT_SLD_FIN; Q200 por mês. Só com a flag (precisa da natureza). **Falta** (fica em
branco, listado no LEIA-ME; nada é inventado): registros 0000/0010/0030 (CPF do produtor, forma
de apuração, cadastro), 0040/0045 (imóveis: CAFIR/CIB, participação → `COD_IMOVEL`), 0050
(contas bancárias), `ID_PARTIC` (CPF/CNPJ dos participantes), tipos especiais de lançamento
(adiantamento de recursos) e o 9999 + transmissão. Próximo passo: cadastro do imóvel rural e do
CPF/CNPJ do participante, e o TXT de transmissão.

## 6. Frontend

- Árvore: grupo `rg-contador` "Entrega ao contador" em `lib/relatoriosNavegacao.ts` (ids
  `pacote_contador`, `fechamento_mes`, `conciliacao`), registrados em `app/financeiro/page.tsx`.
- Contexto na URL como os outros relatórios; Fechamento e Conciliação são sempre de UM mês e da
  fazenda inteira: usam de `TravasContexto` o `cmp: "nada"` (sem comparação, o mesmo valor do
  Cenários), `tiposPeriodo` (só mês) e `perSugerido`; `useContextoMensal` (entregaComum.tsx) mostra
  o último mês fechável quando a URL traz outro tipo de período, sem reescrever a URL e sem travar
  a barra (`per` com valor TRAVA o período, `perSugerido` só preenche — integração da Fase C).
  Contagens (linhas conciliadas) usam o formato `num`. A conta da conciliação vai em `?conta=`.
- Resumo do Financeiro: selo discreto "setembro/2026 fechado/aberto" (só com a flag), link para o
  Fechamento.
- Funções puras e testes: `lib/relatorioFechamento.ts` (+ `.test.ts`); chamadas: `lib/fechamentoApi.ts`.

## 7. Como reverter

1. Desligar a flag `financeiro_regras_v2` da fazenda: a trava some na hora (os eventos ficam).
2. Tirar as telas: remover o grupo `rg-contador` de `relatoriosNavegacao.ts` e as três linhas
   de `page.tsx`; a página volta como antes.
3. Tirar o backend: remover o `include_router(fechamento_conciliacao.router…)` de `main.py`, as
   chamadas `fechamento_mes.exigir_meses_abertos(...)` de `financeiro.py`/`exclusoes.py` e a
   opção `pacote_contador` do Portal.
4. Banco: `alembic downgrade c6f2a9d4e817` (migração `d4e8b1c7a2f5`, aditiva). ATENÇÃO: apaga a
   trilha dos fechamentos e as conciliações — gere o Pacote do contador antes.
