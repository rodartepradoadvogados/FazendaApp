---
projeto: 04_CowData/Milk
tipo: sessao
data: 2026-10-13
status: rascunho
autor: Claude Code (execução autônoma agendada)
---
# Plano Financeiro — fazenda só com Controle Financeiro + Cotações + Pedidos + Agenda

## O que mudou (branch `claude/farm-app-access-bikeej`, PR #906 aberto para `main`)
- Contrato: Rebanho deixou de ser obrigatório; todo contrato exige um módulo base (rebanho ou financeiro) e respeita dependências
  (estoque ⇒ rebanho+financeiro; pedidos/planejamento ⇒ financeiro; reprodutivo/produtivo/sanitário/alimentação ⇒ rebanho). Contratos antigos não são revalidados.
- Plano "Financeiro" (financeiro + pedidos) no catálogo a R$ 200/mês; preço editável no Painel CowData (tabela `preco_plano`); preço do contrato fecha na aprovação
  (`contrato_fazenda.preco_mensal_fechado`); Asaas/boleto/MRR passam por uma função única de preço. Backfill pelo preço de hoje (nenhum valor cobrado mudou).
- Sem o módulo `estoque`, Pedidos (entrega) e Financeiro (nota com item produto) não gravam estoque.
- `/indicadores` exige rebanho/reprodutivo/produtivo contratado; Agenda filtra Rebanho/Reprodutivo por contrato; novo `contas_a_receber`.
- Front: `lib/modulos.ts` é a tabela única de visibilidade; página inicial = Agenda quando não há Capa útil; contrato aguardando/suspenso tem tela própria;
  contrato relido de `/auth/me`; Sidebar sem flash; Painel do Contador não quebra sem Rebanho; Financeiro/Pedidos/Cotações sem 403 por estoque/planejamento.
- Painel CowData > Fazendas (web e mobile): plano Financeiro, dependências explicadas, cartão "Preços dos planos", "Preço fechado × catálogo hoje", botão "Preparar financeiro".
- `POST /fazendas/{id}/financeiro/preparar`: rascunho de plano de contas rural-leiteiro (VALIDAR COM O CONTADOR) + regras v2 só se não há lançamentos. Onboarding por contrato.
- Migrações: f6a7b8c9d0e1 corrigida no lugar (batch_alter_table); nova b8c9d0e1f2a3 (preco_plano + preco_mensal_fechado). Rodam no boot em produção.

## O que ficou de fora / pendências do Jairo
- P11 janela de contas vencidas na Agenda (30 dias, inalterada). P12–P16 (texto comercial, limites do plano, LGPD no contrato-modelo, 1ª fazenda real e contador de homologação).
- Rotas ainda sem gate de contrato: alertas_indicador, nao_conformidades, exportacoes_relatorio, assistente, portal, notificacoes, cadastro (cria itens de Estoque).
- F5 (produção) é etapa humana: SHA + deploy SUCCESS Railway/Vercel, log de boot da migração, grants de `preco_plano` ao role da aplicação em Postgres, fazenda `eh_teste`.

## Armadilhas
- Migração nova roda no boot da API: migração ruim derruba a produção. Conferir o log de boot.
- Plano de contas padrão é inventado por nós: não usar com cliente real sem revisão do contador.
- O gate de estoque é por parâmetro (`exigir_modulo_estoque`), NÃO global: um gate global mudaria Standard/Silver já em produção (decisão da integração).
- Contrato ativo com plano e `preco_mensal_fechado` nulo lê o catálogo ao vivo (só ocorre se o status for alterado direto no banco).

## Regra generalizável
Visibilidade por contrato nasce de UMA tabela (`frontend/lib/modulos.ts`) + gates de rota no backend; módulo não contratado não grava dado por efeito colateral;
preço contratado é fato do contrato (congelado), nunca leitura ao vivo do catálogo.
