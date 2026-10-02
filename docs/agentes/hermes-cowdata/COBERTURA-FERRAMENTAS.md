# Cobertura das ferramentas do agente × o que o site mostra

> Objetivo do dono: o agente (chat do site/app **e** Hermes via `/agente`) responde **tudo que o site mostra**,
> com os **mesmos números**. Este mapa liga cada tela/rota do site à ferramenta de leitura que a cobre
> e diz o que ainda falta. Todas as ferramentas vivem na **mesma lista compartilhada**
> (`backend/fazenda/rules/assistente.py` → `_TOOLS_DISPONIVEIS`); as novas são definidas em
> `backend/fazenda/rules/assistente_consultas.py`. A ponte MCP registra sozinha o que `/agente/ferramentas` devolver
> (`/reload-mcp` no Hermes depois de um deploy).

## Regras que valem para todas as ferramentas novas

- **Somente leitura** — nenhuma chama `add/commit/flush`; os testes rodam todas na sessão READ ONLY do `/agente`.
- **Mesma conta do site** — cada ferramenta chama a função/regra que a tela usa (coluna "Reuso"). Nenhum cálculo foi reimplementado,
  exceto onde o site calcula **no navegador** (Análise reprodutiva): a conta foi portada 1:1 para
  `rules/reproducao_analise.py::resumo_periodo` (inclui o arredondamento do `Math.round` do JavaScript) e testada contra o endpoint.
- **Isolamento por fazenda** em toda consulta (`fazenda_id` do token no site; `AGENTE_FAZENDA_ID` em `/agente`).
- **Permissão por módulo** (`_ferramentas_do_usuario` / `AGENTE_MODULOS`): o módulo de cada ferramenta aceita *uma tupla* (basta ter um).
  `executar_relatorio` ainda exige o módulo do relatório escolhido.
- **Validação com mensagem em português**: data inválida, período invertido, período > 5 anos, valor fora da lista, período obrigatório ausente
  (a resposta traz `erro` dizendo o que perguntar ao usuário). Datas: `AAAA-MM-DD` (também aceita `dd/mm/aaaa`).
- **Saída**: sanitizada (`agente_leitura.sanitizar`: sem senha/token/e-mail/dados bancários; CPF/CNPJ mascarados), paginada
  (`limite`/`offset`, `truncado`) e com teto de bytes (`AGENTE_MAX_BYTES`) — no `/agente` pelo roteador, no chat do site por
  `assistente_consultas.formatar_para_chat` (mesmo envelope).
- Nenhuma ferramenta nova declara `limite`/`offset` no schema (a ponte MCP já os acrescenta; repetir quebraria a assinatura).

## Ferramentas (antigas e novas)

| Ferramenta | Módulo(s) | Parâmetros | Status |
|---|---|---|---|
| `consultar_indicadores` | indicadores | — | antiga (foto de hoje) |
| `buscar_animal` | rebanho | `numero` | antiga (só cadastro) |
| `consultar_agenda_hoje` | agenda | — | antiga |
| `consultar_financeiro` | financeiro | — | antiga (totais) |
| `consultar_estoque` | estoque | — | antiga (abaixo do mínimo) |
| `consultar_calendario_sanitario` | sanidade | — | antiga (30 dias) |
| `consultar_analise_reprodutiva` | reproducao | — | antiga (12 meses) |
| `consultar_exames` | sanidade | `data`, `evento` | antiga |
| `listar_lotes` / `consultar_lote` | rebanho | `codigo` | antigas |
| **`consultar_indicadores_reprodutivos`** | reproducao ou analise | `data_inicio`, `data_fim` (obrigatórias), `tipo_servico`, `metodo_ia`, `touro`, `inseminador`, `ordem_parto`, `ordem_tentativa`, `agrupar_por` | nova |
| **`consultar_ciclos_21_dias`** | reproducao ou analise | `data_inicio`+`data_fim` ou `ancora`+`modo`+`n_ciclos`, `categoria` | nova |
| **`consultar_servicos_reprodutivos`** | reproducao ou analise | período, `numero`, `touro`, `metodo_ia`, `tipo_servico`, `inseminador`, `diagnostico` (POSITIVO/NEGATIVO/PENDENTE), `apenas_perdas` | nova |
| **`consultar_partos_secagens`** | reproducao ou analise | período, `tipo` (partos/secagens/ambos), `numero` | nova |
| **`listar_relatorios`** | qualquer área de relatório | `busca` | nova |
| **`executar_relatorio`** | módulo de cada relatório | `relatorio` (obrigatório) + parâmetros do catálogo | nova |
| **`consultar_protocolos_lancados`** | sanidade ou reproducao | `status` (andamento/concluido/encerrado/cancelado/todos), `tipo`, `origem`, `nome`, período, `origem_id` (detalhe + hormônios) | nova |
| **`consultar_bst`** | producao ou sanidade | período, `numero`, `lote` | nova |
| **`consultar_protocolos_cadastrados`** | sanidade ou reproducao | `tipo` (sanitario_curativo/sanitario_preventivo/iatf/inducao/proprio/todos), `nome`, `apenas_ativos` | nova |
| **`consultar_regras_preventivo`** | sanidade | `nome`, `categoria`, período (projeta ocorrências) | nova |
| **`consultar_lista_espera_preventivo`** | sanidade | `protocolo`, `calendario_id`, `detalhar_animais` | nova (sem escrita) |
| **`consultar_agendamentos_preventivo`** | sanidade | `situacao` (agendados/concluidos/todos), `protocolo`, `calendario_id`, período | nova |
| **`consultar_aplicacoes_sanitarias`** | sanidade | período, `numero`, `produto`, `natureza`, `atividade`, `categoria` (ao menos um filtro) | nova |
| **`consultar_pedidos`** | pedidos | `tipo`, `status`, `fornecedor`, `produto`, `numero_pedido`, período | nova |
| **`consultar_cotacoes`** | pedidos | `status`, `categoria`, `numero_cotacao` (detalhe com preços), período | nova |
| **`consultar_contas_financeiras`** | financeiro | período, `tipo`, `situacao`, `campo_data`, `fornecedor`, `categoria`, `centro_custo`, `texto` | nova |
| **`consultar_estoque_itens`** | estoque | `nome`, `categoria`, `finalidade`, `situacao`, `incluir_lotes`, `vencendo_em_dias`, `incluir_inativos` | nova |
| **`consultar_producao_leite`** | producao | `data_inicio`, `data_fim` (obrigatórias), `numero`, `lote`, `agrupar_por` | nova |

Catálogo de `executar_relatorio` (códigos): `manejo`, `distribuicao_del`, `prenhezes_por_del`, `dias_para_diagnostico`,
`intervalo_entre_servicos`, `dias_para_reinseminacao`, `taxa_servico_prenhez_por_del`, `fluxo_lactacao`, `acasalamento`,
`relatorio_personalizado`, `taxa_cura`, `rastreabilidade_sanitaria`, `compra_semen`, `compra_venda_animal`, `dre`,
`custo_litro_leite`, `custo_vaca_lote`, `custo_hectare`, `custo_safra`, `controle_x_entrega_leite`.

## Mapa tela/rota × ferramenta × lacuna

Legenda: **Feito** = coberto com o mesmo número do site; **Parcial** = coberto em parte; **Falta** = sem ferramenta.

### Reprodução

| O que o site mostra (tela → rota) | Reuso no backend | Ferramenta | Situação / lacuna |
|---|---|---|---|
| Relatórios › Análise reprodutiva (`/analise-relatorios` → `GET /reproducao/servicos`, conta no navegador): taxa de concepção, perdas, quebra por touro/método/inseminador/ordem | `listar_servicos_analise` + `reproducao_analise.resumo_periodo` (porta da conta do navegador) | `consultar_indicadores_reprodutivos` | **Feito** (KPI idêntico à tela, com os mesmos filtros) |
| Gráfico mensal da Análise (`GET /reproducao/indicadores-mensais`, critério R7) | `indicadores_mensais_analise` (chamada direta) | `consultar_indicadores_reprodutivos` → `serie_mensal_criterio_r7` | **Feito** |
| Reprodução › Ciclos de 21 dias (`/ciclos-21-dias`, `GET /reproducao/ciclos-21-dias`): taxa de serviço/prenhez/concepção | `ciclos_de_21_dias` (chamada direta, respeita Parâmetros) | `consultar_ciclos_21_dias` | **Feito** (listas nominais de animais ficam de fora) |
| Histórico › Reprodução › Serviços/IAs/Diagnósticos/Perda de prenhez (`/historico`) | `listar_servicos_analise` | `consultar_servicos_reprodutivos` | **Feito** |
| Histórico › Reprodução › Partos e Secagens (`GET /reproducao/partos`, `/secagens`) | `listar_partos_historico`, `listar_secagens_historico` | `consultar_partos_secagens` (+ contagens em `consultar_indicadores_reprodutivos`) | **Feito** |
| Indicadores gerais do rebanho (`GET /indicadores/`, com `data`) | `calcular_indicadores_fazenda` | `consultar_indicadores` (só hoje) | **Parcial** — falta o parâmetro de data de referência |
| Relatórios › Listas de trabalho (`GET /relatorios/manejo`) e gerenciais (`/relatorios/gerencial/*`) | funções do router `relatorios.py` | `executar_relatorio` (`manejo`, `distribuicao_del`, `prenhezes_por_del`, `dias_para_diagnostico`, `intervalo_entre_servicos`, `dias_para_reinseminacao`, `taxa_servico_prenhez_por_del`, `fluxo_lactacao`) | **Feito** |
| Relatório personalizado (`POST /indicadores/relatorio-personalizado`) | `relatorio_personalizado` | `executar_relatorio('relatorio_personalizado')` | **Feito** |
| Situação reprodutiva ao vivo (`GET /indicadores/estados-reprodutivos`) | `estados_reprodutivos` | — | **Falta** |
| Combinador de Listas (`GET /relatorios/combinador-listas`) | `combinador_listas` | — | **Falta** (saída enorme; precisa de filtros) |
| Agenda reprodutiva do veterinário (`GET /reproducao/agenda-veterinario`) | — | `consultar_agenda_hoje` (só o de hoje) | **Falta** |
| Acasalamento (sugestão de touro) | `sugestao_acasalamento` | `executar_relatorio('acasalamento')` | **Feito** |
| Protocolos IATF/indução lançados e Ciclos de IATF (`GET /reproducao/protocolo-iatf/*`, `/producao/inducao-lactacao/ativos`) | `central_protocolos` (mesma fonte do Acompanhamento/Histórico) | `consultar_protocolos_lancados` | **Parcial** — progresso/status/hormônios sim; "candidatas ao próximo repasse" e próxima visita reprodutiva não |
| Hormônios por dia de cada protocolo | `central_protocolos.detalhe` (`ProtocoloIatfHormonio`) | `consultar_protocolos_lancados` com `origem`+`origem_id` | **Feito** |
| Indução de cio (`GET /reproducao/inducao-cio`) | — | `consultar_aplicacoes_sanitarias(atividade='Indução de cio')` | **Parcial** (é gravada como aplicação de Sanidade) |
| Banco de touros / estoque de sêmen (`/rebanho › Touros`, `EstoqueSemen`) | — | `executar_relatorio('compra_semen')` (só compras) | **Falta** (saldo de doses por touro) |

### Sanidade e protocolos

| O que o site mostra | Reuso | Ferramenta | Situação / lacuna |
|---|---|---|---|
| Protocolos › Cadastro: sanitário curativo, preventivo, IATF, indução, próprios (`GET /cadastro/protocolos-sanitarios`, `-iatf`, `-inducao-lactacao`, `-customizados`) | as 4 funções `listar_protocolos_*` | `consultar_protocolos_cadastrados` | **Feito** |
| Protocolos › Acompanhamento e Histórico (`GET /central-protocolos/acompanhamento`, `/historico`), status andamento/concluído/encerrado/**cancelado** | `central_protocolos._todas_as_linhas` + `_filtrar` (inclui a correção de status cancelado) | `consultar_protocolos_lancados` | **Feito** |
| Sanidade › Preventiva › Regras cadastradas e Calendário (`GET /sanidade/calendario`, `/calendario/visao`) | `listar_calendario`, `montar_calendario_visual` | `consultar_regras_preventivo` | **Feito** |
| Protocolos › Aplicar › **Lista de espera** (`GET /sanidade/cronogramas/lista-espera` — **reconcilia e ESCREVE em GET**) | `cronograma_sanitario.lista_espera(..., reconciliar=False)` (novo parâmetro; padrão `True` preserva o site) | `consultar_lista_espera_preventivo` | **Feito, sem escrita** — devolve a lista que o site mostra *depois* de reconciliar, sem gravar a reconciliação |
| Protocolos › Acompanhamento (agendamentos) e Concluídos do preventivo (`GET /sanidade/cronogramas/acompanhamento`, `/concluidos`) | `aplicacao_preventiva.acompanhamento`, `.concluidos` | `consultar_agendamentos_preventivo` | **Feito** |
| Rotina da lista de espera (`GET /agenda/lista-espera-rotina/status`) | `rotina_lista_espera` | — | **Falta** |
| Sanidade › Curativa › aplicações / por doença (`GET /sanidade/aplicacoes`) | consulta direta ao modelo `Sanidade` (mesmos campos) | `consultar_aplicacoes_sanitarias` | **Feito** (sem coluna de carência) |
| Sanidade › Curativa › Protocolos sanitários lançados (`GET /sanidade/protocolos/lancamentos`) | `central_protocolos` | `consultar_protocolos_lancados(origem='sanitario')` | **Feito** |
| Sanidade › Taxa de cura (`GET /sanidade/taxa-cura`) | `relatorio_taxa_cura` | `executar_relatorio('taxa_cura')` | **Feito** (sem filtros de período; vem inteiro) |
| Sanidade › Rastreabilidade (`/relatorio-rastreabilidade-sanitaria`) | `relatorio` | `executar_relatorio('rastreabilidade_sanitaria')` | **Feito** |
| Resultados de exames preventivos (`GET /sanidade/exames/resultados`) | — | `consultar_exames` (antiga) | **Parcial** (data exata ou nome; sem período) |
| Catálogo de farmácia (princípios ativos, indicações, bula) (`/farmacia/*`) | — | — | **Falta** |
| Mastite/ocorrências clínicas, relatório de bezerras (`/sanidade/ocorrencias`, `/relatorio-bezerras`) | — | — | **Falta** |
| BST (Produção › BST, `GET /producao/relatorio-bst`) | `relatorio_bst` | `consultar_bst` | **Feito** (histórico; agenda de BST de hoje em `consultar_agenda_hoje`) |

### Pedidos e cotações

| O que o site mostra | Reuso | Ferramenta | Situação / lacuna |
|---|---|---|---|
| Pedidos (`/pedidos`, `GET /pedidos/`) | `listar_pedidos` | `consultar_pedidos` | **Feito** (itens e valores; anexos/lançamentos vinculados não) |
| Cotações (`/cotacoes`, `GET /cotacoes/`, `/{id}` com comparação) | `listar_cotacoes`, `obter_cotacao` | `consultar_cotacoes` | **Feito** (nunca expõe o `token_publico` do fornecedor) |
| Cotações do painel CowData (preço de referência) | — | — | **Falta** |

### Financeiro

| O que o site mostra | Reuso | Ferramenta | Situação / lacuna |
|---|---|---|---|
| Financeiro › Contas a pagar/receber/pagas/recebidas/extrato (`/financeiro`, `GET /financeiro/lancamentos`): em aberto = **sem data de pagamento**; período por emissão/vencimento/pagamento | mesma regra do front; oráculo = `listar_lancamentos` | `consultar_contas_financeiras` | **Feito** (totais, por categoria, lista) |
| DRE gerencial (`GET /financeiro/dre`) | `dre` | `executar_relatorio('dre')` | **Feito** |
| Custo por litro/vaca-lote/hectare/safra | funções dos routers `relatorio_custo_*`, `custo_litro_leite` | `executar_relatorio` | **Feito** |
| Compra/venda de animais, compra de sêmen | `relatorio` dos routers | `executar_relatorio` | **Feito** |
| Fluxo de caixa, Caixa real, Livro caixa, RMCA (`/financeiro/caixa-real`, `/rmca`) | — | — | **Falta** |
| Orçamento e Planejamento financeiro, recorrentes, patrimônio, cartão de crédito | — | — | **Falta** |
| Folha/RH, holerites, diárias, contratos | — | — | **Falta** (dados sensíveis; decidir antes) |
| Totais rápidos de hoje | `consultar_financeiro` (usa `valor_pago < valor_total`) | — | **Atenção**: critério diferente da tela (veja "Divergências conhecidas") |

### Estoque, leite e rebanho

| O que o site mostra | Reuso | Ferramenta | Situação / lacuna |
|---|---|---|---|
| Estoque › lista, abaixo do mínimo, inventário (`GET /estoque/`) | modelo `Estoque` (mesmos campos), itens inativos fora | `consultar_estoque_itens` | **Feito** |
| Estoque › lotes/frascos com validade (`GET /estoque/{id}/lotes`) | modelo `LoteEstoque` | `consultar_estoque_itens(incluir_lotes, vencendo_em_dias)` | **Feito** |
| Estoque › Mapa de entradas/saídas, por produto (`GET /estoque/movimentos`) | — | — | **Falta** |
| Produção › Controle leiteiro (`GET /producao/controles`) | `listar_controles` | `consultar_producao_leite` | **Feito** (agrupa por dia/mês/animal/lote) |
| Produção › Venda mensal do leite / controle × entregue (`/producao/relatorio-controle-entrega`) | `relatorio_controle_entrega` | `executar_relatorio('controle_x_entrega_leite')` | **Feito** (entrega mensal bruta: falta) |
| Produção › Qualidade do leite (CCS, CBT, gordura…) (`GET /producao/qualidade-leite`) | — | — | **Falta** |
| Produção › Pesagem corporal, Equivalente maduro, Indução de lactação | — | — | **Falta** |
| Rebanho › Ficha do animal (`GET /animais/{n}/ficha`), descarte, sugestões de movimentação | — | `buscar_animal` (só cadastro), `consultar_lote` | **Parcial** — ficha completa (histórico reprodutivo, sanitário, produção) falta |
| Agenda de outros dias (`GET /agenda/?data=&dias=`) | `calcular_agenda` | `consultar_agenda_hoje` (só hoje) | **Parcial** — falta parâmetro de data |
| Recria, Alimentação/dietas, Safra/agricultura, Não conformidades, Documentos | — | — | **Falta** |

## Divergências conhecidas (o agente informa; não "corrige" sozinho)

1. **Três definições de "taxa de concepção" convivem no site.** (a) Tela Análise reprodutiva: positivos ÷ **diagnosticados**.
   (b) Série mensal/gráfico e Indicadores: critério **R7** (28 dias, sem diagnóstico conta como fracasso). (c) Ciclos de 21 dias: R7 por ciclo.
   `consultar_indicadores_reprodutivos` devolve (a) como `taxa_concepcao_pct` e (b) como `serie_mensal_criterio_r7`; `consultar_ciclos_21_dias` devolve (c).
   O agente cita qual é qual. **Decisão pendente do dono**: unificar a definição no site.
2. **`consultar_financeiro` (antiga)** soma `valor_total` das contas com `valor_pago < valor_total`; a tela Contas considera "em aberto" quem **não tem data de pagamento**.
   Em dados consistentes dão o mesmo; um lançamento parcialmente pago com data de pagamento diverge. Para perguntas de contas, preferir `consultar_contas_financeiras`.
3. **Lista de espera**: o endpoint do site grava a reconciliação ao abrir (GET com escrita). A ferramenta não grava; o resultado é o mesmo que o site mostra depois de reconciliar.
4. **Critério de "abaixo do mínimo"** usa o campo `abaixo_minimo` gravado no item (como o site e a ferramenta antiga), não recalcula.
5. `consultar_calendario_sanitario` (antiga) olha só 30 dias; para "o que vence entre X e Y", use `consultar_regras_preventivo` com período.

## Ordem de entrega e o que ficou para depois

Entregue na ordem pedida: (a) reprodução por período + relatórios, (b) serviços/IATF/BST, (c) sanidade, (d) pedidos/cotações,
(e) financeiro/estoque, (f) leite. **Ficou:** ficha completa do animal, agenda por data, indicadores gerais por data, estado reprodutivo ao vivo,
estoque de sêmen/touros, movimentos de estoque, qualidade e entrega mensal de leite, pesagem corporal, fluxo/caixa real/RMCA/orçamento,
patrimônio, recria, alimentação/dietas, farmácia (catálogo), rotina da lista de espera, folha/RH.
