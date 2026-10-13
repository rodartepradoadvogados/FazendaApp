# CONTRATO DE API backend -> front — Plano Financeiro (fixo)

Implementado pelas trilhas B1/B2 (backend); consumido pelas trilhas F-* (frontend). Nomes exatos.
Chaves comerciais de módulo: rebanho, reprodutivo, produtivo, sanitario, financeiro, planejamento, pedidos, estoque, alimentacao, agricultura, consultor, formulacao_dietas.

## A. Catálogo de planos
`GET /fazendas/catalogo/planos` (dono) ->
`{ "<plano>": { nome, preco (efetivo), preco_padrao, modulos:[...], atualizado_em: iso|null, atualizado_por: string|null } }`
para `standard`, `silver`, `gold`, `diamond` e **`financeiro`**.

## B. Preço do plano
`PUT /fazendas/catalogo/precos-plano/{plano}` body `{preco:number>=0}` ->
`{plano, preco, preco_padrao, atualizado_em, atualizado_por}`; 400 plano inválido / preço negativo; 403 não-dono.

## C. Dependências entre módulos
`GET /fazendas/catalogo/dependencias` (dono) ->
`{ "dependencias": {"estoque":["rebanho","financeiro"],"pedidos":["financeiro"],"planejamento":["financeiro"],"reprodutivo":["rebanho"],"produtivo":["rebanho"],"sanitario":["rebanho"],"alimentacao":["rebanho"]}, "modulos_base":["rebanho","financeiro"] }`

## D. Contrato da fazenda
`GET/PUT /fazendas/{id}/contrato`: a resposta ganha `preco_mensal_fechado:number|null` e `preco_catalogo_hoje:number|null`.
PUT sem módulo base (rebanho ou financeiro) ou com dependência faltando -> 400 com texto em português
(ex.: "Estoque exige Rebanho e Financeiro"). Rebanho deixa de ser obrigatório.

## E. Status do contrato no objeto fazenda
Objeto `fazenda` de `/auth/login`, `/auth/me` e `selecionar-fazenda` ganha
`contrato_status: "ativo"|"aguardando_aprovacao"|"suspenso"|null` (além de `modulos_contratados`).

## F. Agenda: contas a receber
`GET /agenda/` (e `/agenda/painel` onde existir `contas_a_pagar`) ganha `contas_a_receber:[...]` com o MESMO formato dos itens
de `contas_a_pagar`, só com módulo financeiro contratado+permitido.

## G. Preparar financeiro
`POST /fazendas/{id}/financeiro/preparar` (dono) ->
`{ plano_contas_carregado:bool, contas_criadas:int, regras_v2_ligadas:bool, ja_preparado:bool, mensagens:[string] }` (idempotente).

## Notas de implementação (B1)
- O preço do plano vive na tabela `preco_plano` (não em `PrecoModulo`); o preço do contrato fecha em `contrato_fazenda.preco_mensal_fechado`
  na aprovação e quando o plano muda em contrato ativo. Re-salvar o mesmo plano não recongela.
- `preco_mensal` (já existente na resposta do contrato) passa a ser o preço fechado quando houver; `preco_catalogo_hoje` é o preço de catálogo vigente do plano (null em sob medida).

## Notas de implementação (B2)
- `contas_a_receber` (F): receitas (`tipo == "receita"`) com saldo em aberto, vencidas até 30 dias atrás (a janela de vencidas NÃO mudou) e a vencer em `dias`; ordenadas por vencimento; `totais.contas_a_receber` traz a contagem. Chave própria — não vira evento da Agenda nem entra em `contas_a_pagar`. `[]` sem o módulo financeiro.
- `preparar` (G): `plano_contas_carregado` e `regras_v2_ligadas` são ESTADO ao final da chamada; `contas_criadas` é o que esta chamada criou (plano padrão + Retenções/Vales); `ja_preparado` = nada precisou ser feito (2ª chamada = true). 400 se a fazenda não tem o módulo `financeiro` ativo no contrato; 404 se a fazenda não existe; regras v2 só ligam em fazenda SEM lançamentos. O plano padrão é RASCUNHO (validar com o contador).
- `/indicadores/*` passa a exigir algum de {rebanho, reprodutivo, produtivo} contratado: 403 "Módulo não contratado por esta fazenda (...)" na fazenda só-Financeiro.
- `GET /onboarding` devolve passos por contrato: sem `rebanho` mas com `financeiro` = 5 passos (`contas_bancarias`, `plano_de_contas`, `primeira_conta_a_pagar`, `convidar_contador`, `conferir_agenda`); com rebanho = os 4 de sempre.
