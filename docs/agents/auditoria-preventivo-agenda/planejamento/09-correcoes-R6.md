# Fluxo completo — R6 (79,7%) e lista de correções da rodada final

## Resultado da R6 (2ª avaliação do `fluxo-completo.html`)
| Persona | R5 | R6 | P0 | P1 | Destaque |
|---|---|---|---|---|---|
| Zootecnista | 69% | **81%** | 0 | 0 | números fecham entre telas; sobram unidades do repasse e cobertura de B19 |
| Veterinário | 77% | **83%** | 0 | 3 | B19/TB só por veterinário funciona; **Desfazer do toast quebrado**; "Desconsiderar estoque" aceita vazio |
| Peão | 68% | **71%** | 0 | 1 | toque duplo e adiar crítico resolvidos; **Desfazer quebrado**; texto 14 px; "Quem aplicou" em branco |
| Produtor | 79% | **83%** | 0 | 0 | Painel legível; "Conferir" da Raiva sem custo; faixa sem conexão só em 2 etapas |
| Cooperativa | 58% | **84%** | 0 | 4 | P0 do estoque resolvido; conta cancelada continua "A pagar"; desconsiderar em bloco sem base |
| Pesquisador | 62% | **76%** | 0 | 1 | os 2 P0 resolvidos; "feitas hoje" incoerente depois de Aplicar na Agenda |
| **Média** | **69,2%** | **79,7%** | 0 | 9 | critério: ≥ 90% e nenhuma < 80% |

## Decisões
1. **Desfazer dentro de 10 s (toast) funciona sem pedir motivo.** Grava "Desfeito na hora (≤10 s)" com quem e hora — é um engano imediato e a trilha diz isso. **Depois dos 10 s**, só por **Estornar** em Concluídos, com motivo em chips (perfil administrador).
2. **Desconsiderar estoque exige um motivo em chips** ("Frasco do veterinário" · "Estoque não cadastrado" · "Outro") e, para "Frasco do veterinário", lote e validade informados. Nunca vem preenchido sozinho. **Desconsiderar em bloco** só desconsidera itens que tenham motivo escolhido.
3. **Adiar** em tarefa comum: 1 chip opcional (log "sem motivo informado" se pular). **Adiar/desconsiderar em agendamento preventivo** (veterinário, estoque, data): chip **obrigatório**.
4. **"Quem aplicou" é obrigatório** para habilitar Aplicar.
5. **Conta cancelada** sai de "A pagar" (estado Cancelada, fora dos totais).
6. **Texto no mobile (Agenda e gavetas):** linha principal ≥ 16 px, linha de apoio ≥ 15 px, selos ≥ 14 px; a linha de apoio nunca perde "N animais · hora" (o que se corta é o nome do lote, com título completo no toque); toast ≤ 2 linhas.

## P — Store, Protocolos, Sanidade, Lançamentos, apoio
- **P1** Desfazer do toast (decisão 1) em **Aplicar, Feito e Adiar**; teste automatizado dos três.
- **P1** Desconsiderar estoque/checklist em bloco (decisão 2); passo 4 e retroativo sem "saldo depois: 12" quando o estoque foi desconsiderado; custo não calculado de baixa quando é frasco do veterinário (custo do frasco informado ou "a informar"); item "Compra" vira **Não necessária** com estoque desconsiderado.
- **P1** Conta cancelada (decisão 5); estado consistente no card de resumo.
- **P1** Desconsiderar a confirmação do veterinário exige chip; adiar preventivo exige chip (decisão 3).
- Aplicador obrigatório (decisão 4); checkboxes com área de toque ≥ 44 px (linha inteira).
- **Vendido/baixado** (ex.: 5120) sai da lista de espera mesmo já marcado "Desconsiderar".
- Concluídos: **selo de exceção/ciência** na lista e colunas de exceção em **todas** as linhas do CSV; log de entradas na janela e de parâmetros do cadastro; "Estornar (administrador)" controlado por **perfil** (seletor "Perfil: Gestor / Administrador" na barra de revisão); marca de registro **offline** (fila).
- TB: campos **espessura de pele (mm)** e **tipo de teste**; comprovante bloqueado de verdade (botão desabilitado com motivo, não só texto); Estornada não mostra carência vigente; wizard trava **B19 em 3–8 meses e sexo F**; campos de **frasco aberto/descarte da sobra**; "reteste vencido" mostra **Reteste atrasado** (não "Inconclusivo").
- Cobertura/carteira: B19 **sem aplicação = Prevista/na janela** (nunca 100%); carteira mostra **"Agendado 02/10"** quando há agendamento; animal fora da janela que já tem a dose pede **dose extra/reforço** (não grava como "dose 2"); "janela vencida" removida de todo lugar (→ "Atrasada há N dias").
- Vocabulário: "Marcar como revisado" → **Desconsiderar**; "Aplicação avulsa/já realizada" agrupadas em "Outras formas ▾"; "Concluído" com no máximo 2 rótulos (Aplicado para vacinas/exames, Feito para tarefas); decimais com vírgula nos resumos ("−91,6 mL"); "Exame TB — reteste" sem repetir; **uma largura de gaveta** para o agendamento; motivos de "fora da janela" em **4 chips + Outro**; "Conferir" de **todos** os protocolos com custo, conta a pagar e pagamento; "14,7 mil" → "R$ 14,7 mil".
- Foco volta ao botão que abriu a gaveta (todas) e `inert` no fundo.

## Q — Agenda
- **P1** "Feitas hoje" e o contador incluem o que foi **aplicado hoje** (vindo do Store) e o toast de Aplicar aparece na hora, com Desfazer funcional (decisão 1); estado consistente após Aplicar/Feito.
- Mobile: cabeçalho compacto — **primeira ação a ≤ 380 px do topo** a 390×844; textos (decisão 6); linha de apoio com "N animais · hora"; checkboxes ≥ 44 px; toast ≤ 2 linhas; nome de lote cortado só com título completo no toque.
- **Faixa "sem conexão"** também ao ligar o interruptor (não só nas etapas 59/60) e a etapa "erro de rede" abre com ela; "Atualizado" coerente.
- "O que vem" **na 1ª dobra** no desktop (2–3 linhas nomeadas) e chip "Lista de espera" com número.
- Repasse: **Manter × Remover** produzem resultados diferentes na Agenda e no Painel; unidade única (**"2 checagens · 20 vacas"**); a prévia "primeira checagem 13/10" existe na projeção; cio de hoje coerente entre Dia a dia e Painel; "última 16/09 · 20 inseminações" coerente com "5 vacas da última IATF".
- Painel: card "Alertas de estoque" sem "3 · 4 precisam" (uma só contagem); "últimos 7 dias" × "23/09 a 29/09" com o mesmo período; brincos/nomes na gaveta de candidatas; pendências separadas de contas a pagar.
- Estados com a mesma cor/gênero ("Na janela", "Hoje", "Agendado/a", "Prevista"); selos ×/7 iguais ao contador; foco volta ao botão e `inert` nas gavetas da Agenda.
- Ação "Nova tarefa" persiste via nova action **`tarefaCriar`** (P publica) — Q usa com fallback.

## Critério de saída
Média ≥ 90%, nenhuma persona < 80%, zero P0. Esta é a última rodada de correção deste ciclo; o que sobrar vira pendência registrada.
