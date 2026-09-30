# 12 — Já aplicado no ciclo, unidade da dose e estoque inativo

Correções do teste do dono no ar (set/2026). Código: `backend/fazenda/rules/ja_aplicado_preventivo.py`,
`cronograma_sanitario.py`, `aplicacao_preventiva.py`; front: `GavetaAplicar.tsx`, `ListaEsperaPreventivo.tsx`,
`FormCalendarioSanitario.tsx`.

## A) Animal que já recebeu o produto no ciclo

Fonte da verdade: qualquer linha de `Sanidade` (Lançamentos antigos, histórico importado, protocolo agrupado,
curral, aplicar do agendamento; o estorno apaga a linha). Casa por: nome do produto da regra (ou padrão do
protocolo, sem caixa/acento), itens de estoque do mesmo princípio ativo, ou observação de aplicação preventiva do
mesmo protocolo. Exame fica de fora (fluxo próprio, com reteste).

Janela: regra por época/frequência = (data devida da ocorrência − 1 frequência) até hoje; regra por evento de vida
= do gatilho do animal (nascimento, parto, secagem…) até hoje.

- Lista de espera: ao abrir (`GET /sanidade/cronogramas/lista-espera`) quem já tem aplicação no ciclo sai
  (`excluido`, motivo "Já aplicado em dd/mm/aaaa …", log do cronograma) e a resposta traz `reconciliados` (banner).
  O resumo da Agenda/Painel não conta esses animais (sem escrever em GET).
- Sugestão (rotina diária, materialização da Agenda, gatilho de evento de vida): `sugerir_animal[_em_lote]` não
  recoloca quem já recebeu.
- Criar agendamento: recusa e reconcilia quem já recebeu.
- Agendamento/Acompanhamento: selo "N animais já aplicados".
- Gaveta Aplicar: aviso destacado; por animal "Aplicar mesmo assim" (Dose extra | Reforço | Outro + descrição) ou
  "Tirar do agendamento" (vira Desconsiderar, motivo "Já aplicado em dd/mm/aaaa"). O servidor recusa aplicar sem a
  decisão (`ja_aplicados` no payload) e registra a exceção no comprovante e em `Sanidade.obs`.
- Limite conhecido: se a aplicação anterior for apagada depois, o animal reconciliado não volta sozinho à lista
  daquele ciclo (volta no próximo).

## C) Unidade da dose padrão

O passo Identificação do cadastro preventivo tem o seletor de unidade ao lado da dose (mL, dose, g, mg,
comprimido, aplicação, unidade do estoque, Outra…), gravado em `EventoSanitario.unidade_padrao` (coluna já
existia: sem migração). Default = unidade do produto no estoque. A gaveta Aplicar, o comprovante, os Concluídos e o
CSV mostram a unidade da dose e a do estoque.

Regra de baixa (não converte em silêncio): só há baixa automática quando unidade da dose = unidade do estoque
(`unidades_iguais`, sem caixa/sinônimos). Se diferem: aviso na gaveta e no wizard, exceção registrada, nenhuma baixa
("cadastre a equivalência") e o "restante" não é calculado. Unidade fora do grupo compatível do produto segue
recusada pelo servidor (use "Desconsiderar estoque" com motivo).

## D) Estoque inativo

Item `ativo = false` nunca gera: tarefa "Comprar X" (agenda_engine 5b), alertas negativo/abaixo do mínimo
(Agenda, Dia a dia, Painel, notificações/push derivados), manual da fazenda, assistente, aviso de mínimo na baixa,
contagem da Capa/Estoque, status da Farmácia (grupo só com itens inativos).
